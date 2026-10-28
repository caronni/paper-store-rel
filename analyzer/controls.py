"""Controls and parity — a run without these is not a result (DESIGN §8).

Five instruments, each answering a different way of being wrong:

* :func:`null_arm` — the pixels of a tile at least eight tiles away, read
  at THIS tile's address, climbing the FULL ladder at the same knobs.
  Any certificate is `wrong`.  Reported with its power denominator: the
  same tiles decoded truthfully, so "zero certificates" cannot be a
  claim about a battery that certifies nothing anyway.
* :func:`frame_null` — the right pixels and the right address, but the
  certified frame contributions taken from another tile.  Run on tiles
  that DO re-derive truthfully, so a zero here has power too.
* the oracle-permutation control is GONE from this module (2026-09-04).
  It measured that a run's columns do not move when truth is permuted;
  a run no longer HAS truth in the room, so the claim it defended is
  now structural, and what is left to test — that the offline scorer's
  blind columns are the ledger's own — is a test of `analyzer.score`
  (`test_analyzer_score.py`), not a control that decodes anything.
* :func:`positive_control` — withhold real certificates and try to win
  them back, with the frame, the plane fields and the pooled context
  rebuilt without them (B5).  Leave-one-out, stratified by source and
  band, Clopper-Pearson intervals, pre-registered bar.
* :func:`stratified_holdout` — DESIGN §8's Q1.7: production certificates
  withheld by (stream, source) in a deterministic seeded sample, all at
  once, then attacked by the default battery in ONE pass.  Reports the
  recovered fraction per (stream, source, band) with exact intervals and
  the R distribution of the misses.
* :func:`parity_sample` — production-certified tiles re-derived by the
  DEFAULT arm.  The re-derivation rate is THE acceptance gate (>= 80%
  per stream), and every re-derived certificate must equal PRODUCTION's
  own bits for that key — which is not ground truth but the fourth leg
  of the 2026-09-04 ruling: two independent paths certifying the same
  tile bit-for-bit.  A disagreement is a finding and fails the control.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy import stats

from . import arms as arms_mod
from . import calibrate as cal
from . import combine as combine_mod
from . import fixedpoint as fp
from . import frame as frame_mod
from . import inputs as inputs_mod
from . import ladder as ladder_mod
from . import residue as residue_mod
from .types import VERDICT_CERTIFIED, AnalyzerConfig, Key, LedgerRow

#: DESIGN §8: "at least eight tiles away" — beyond the registration
#: period, so the donor's pixels cannot be a shifted view of the target.
NULL_SHIFT_TILES = 8

#: The pre-registered bars.
POSITIVE_CONTROL_BAR = 0.70
POSITIVE_CONTROL_MIN_STRATUM = 20
PARITY_BAR = 0.80

#: The positive control refuses every arm whose input was fitted WITH the
#: withheld certificates (DESIGN §8, review finding B5).
FIELD_ARMS: tuple[str, ...] = ("subtract+field", "subtract+field+offset")


class ControlError(RuntimeError):
    """A control cannot be run as asked."""


def clopper_pearson(k: int, n: int, alpha: float = 0.05
                    ) -> tuple[float, float]:
    """Exact binomial interval; ``(0, 0)`` and ``(1, 1)`` at the ends."""
    if n <= 0:
        return (0.0, 1.0)
    low = 0.0 if k == 0 else float(stats.beta.ppf(alpha / 2, k, n - k + 1))
    high = 1.0 if k == n else float(
        stats.beta.ppf(1 - alpha / 2, k + 1, n - k))
    return (low, high)


# ------------------------------------------------------------ the sample

def _hash_rank(seed: int, key: Key) -> int:
    material = f"{int(seed)}|{key[0]}|{key[1]}|{key[2]}|{key[3]}"
    return int.from_bytes(
        hashlib.blake2b(material.encode("utf-8"), digest_size=8).digest(),
        "big")


def stratified_sample(rows: Sequence[LedgerRow], n_per_stream: int,
                      seed: int, *, streams: Sequence[str] | None = None
                      ) -> list[LedgerRow]:
    """`n_per_stream` rows per stream, spread over the bands.

    The draw is a hash of (seed, key), never an RNG whose state depends
    on the order rows arrive in (DESIGN §0 determinism).
    """
    by_stream: dict[str, dict[str, list[LedgerRow]]] = {}
    for row in rows:
        if streams is not None and row.stream_id not in streams:
            continue
        by_stream.setdefault(row.stream_id, {}).setdefault(
            row.band, []).append(row)
    out: list[LedgerRow] = []
    for stream in sorted(by_stream):
        bands = by_stream[stream]
        order = sorted(bands, key=lambda name: (-len(bands[name]), name))
        picked: list[LedgerRow] = []
        remaining = int(n_per_stream)
        for index, band in enumerate(order):
            share = -(-remaining // (len(order) - index))
            pool = sorted(bands[band], key=lambda row: _hash_rank(seed,
                                                                  row.key))
            take = pool[:share]
            picked.extend(take)
            remaining -= len(take)
        out.extend(sorted(picked, key=lambda row: row.key))
    return out


# --------------------------------------------------------- withhold sets

def withheld_keys(inputs: Any, *, run_mints: bool = False,
                  keys_file: Path | str | None = None,
                  sources: Sequence[str] = ()) -> tuple[Key, ...]:
    """The positive control's withhold set (DESIGN §8, B4).

    An EMPTY set is a hard error: a control that withholds nothing is a
    control that measures nothing.
    """
    keys: list[Key] = []
    if run_mints:
        keys.extend(inputs_mod.run_mint_keys(Path(inputs.run_dir)))
    if keys_file is not None:
        text = Path(keys_file).read_text("utf-8")
        try:
            loaded = json.loads(text)
            keys.extend((int(a), int(b), int(c), str(d))
                        for a, b, c, d in loaded)
        except json.JSONDecodeError:
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                page, ty, tx, stream = line.split(",")
                keys.append((int(page), int(ty), int(tx), stream.strip()))
    if sources:
        want = {str(name) for name in sources}
        keys.extend(key for key, cert in inputs.certificates.items()
                    if str(cert.source) in want)
    unique = sorted(set(keys))
    if not unique:
        raise ControlError(
            "the withhold set is EMPTY — --withhold-run-mints on a run "
            "with no certified TileOutcome, an empty key file, or a "
            "--withhold-source that matches no certificate source "
            "(DESIGN §8: an empty set is a hard error)")
    missing = [key for key in unique if key not in inputs.certificates]
    if missing:
        raise ControlError(
            f"{len(missing)} withheld key(s) are not certificates of this "
            f"run, e.g. {missing[0]}")
    return tuple(unique)


# ------------------------------------------------------------- null arm

def _donor(inputs: Any, key: Key, shift_tiles: int) -> Key | None:
    page, ty, tx, stream_id = key
    _tiles_y, tiles_x = inputs.tiles_yx
    for candidate in (tx + shift_tiles, tx - shift_tiles):
        if 0 <= candidate < tiles_x:
            return (page, ty, candidate, stream_id)
    return None


def _decode_at(inputs: Any, certs: Mapping[Key, Any], donor: Key,
               address: Key, config: AnalyzerConfig, exposure: Any,
               *, metadata_bit: int | None) -> dict:
    """Evidence taken at `donor`, decoded at `address` (DESIGN §8)."""
    page, ty, tx, stream_id = donor
    from . import sample as sample_mod
    lanes = sample_mod.lanes_for_tile(inputs, int(page), int(ty), int(tx),
                                      cover_fraction=config.cover_fraction)
    if not lanes:
        return {"refusal": "no_lane", "results": []}
    halo = fp._halo_for(config, str(stream_id))
    footprint = frame_mod.tile_footprint(inputs.row, int(page), int(ty),
                                         int(tx), halo,
                                         geometry=inputs.geometry)
    folds = cal.split_folds(footprint.page_cells_yx, int(config.seed))
    chosen = []
    for lane in lanes:
        knobs = fp._knobs_for(inputs, config, donor, lane, None, None)
        candidates = []
        for arm in config.battery_for(str(stream_id)):
            evidence = arms_mod.evidence_for(inputs, certs, donor, lane, arm,
                                             halo_cells=halo, knobs=knobs)
            if evidence.blind.get("refusal") is None and np.any(
                    evidence.observed):
                candidates.append(evidence)
        if not candidates:
            continue
        winner, _detail = cal.select_arm(candidates, folds)
        chosen.append(dc_replace(winner, key=address))
    if not chosen:
        return {"refusal": "every_arm_refused", "results": []}
    results = []
    for rule in config.rules:
        combined = combine_mod.combine(chosen, rule)
        results.extend(ladder_mod.run_ladder(
            combined, inputs.row, address, rungs=fp.expand_rungs(config.rungs),
            knobs=dict(config.knobs), exposure=exposure,
            metadata_bit=metadata_bit))
    return {"refusal": None, "results": results}


def null_arm(inputs: Any, keys: Sequence[Key],
             config: AnalyzerConfig | None = None, *,
             shift_tiles: int = NULL_SHIFT_TILES,
             exposure: Any = None) -> dict:
    """DESIGN §8's null arm, with its power denominator."""
    config = AnalyzerConfig() if config is None else config
    exposure = fp.shared_exposure() if exposure is None else exposure
    trials: list[dict] = []
    n_certificates = 0
    n_power = 0
    for key in keys:
        donor = _donor(inputs, key, shift_tiles)
        if donor is None:
            trials.append({"key": list(key), "skipped": "no_donor_tile"})
            continue
        bit = inputs_mod.metadata_bit(inputs, key)
        null = _decode_at(inputs, inputs.certificates, donor, key, config,
                          exposure, metadata_bit=bit)
        hits = [item for item in null["results"]
                if item.verdict == VERDICT_CERTIFIED]
        n_certificates += len(hits)
        # DESIGN §8: a certificate from the donor's pixels at this address
        # is a false accept by construction, and saying so needs no truth
        # column — the pixels are eight tiles away from the address they
        # were decoded at.  The count IS the finding.
        # power: the SAME tile decoded at its own address.
        live = fp.blind_key(inputs, inputs.certificates, key, config,
                            exposure, metadata_bit=bit)
        truthful = live.get("user_bits") is not None
        n_power += int(truthful)
        trials.append({
            "key": list(key), "donor": list(donor),
            "null_refusal": null["refusal"],
            "null_certificates": len(hits),
            "null_min_unsat": (
                None if not null["results"] else
                min(int(item.unsat_at_exit) for item in null["results"]
                    if item.unsat_at_exit >= 0)
                if any(item.unsat_at_exit >= 0 for item in null["results"])
                else None),
            "truthful_certifies": truthful,
        })
    return {
        "control": "null_arm",
        "shift_tiles": int(shift_tiles),
        "n_trials": len(keys),
        "n_certificates": int(n_certificates),
        "power_denominator": int(n_power),
        "exposure_distinct": int(exposure.distinct),
        "expected_false": float(exposure.expected_false),
        "passes": bool(n_certificates == 0),
        "trials": trials,
    }


# ----------------------------------------------------------- frame null

def _shifted_certificates(inputs: Any, shift_tiles: int) -> dict:
    """Every certificate moved `shift_tiles` columns along, cyclically.

    Addressing arithmetic stays correct (the projection is built for the
    address it is asked about); only the BITS are another tile's.
    """
    _tiles_y, tiles_x = inputs.tiles_yx
    out: dict[Key, Any] = {}
    for key, certificate in inputs.certificates.items():
        page, ty, tx, stream_id = key
        source = (page, ty, (tx + shift_tiles) % tiles_x, stream_id)
        donor = inputs.certificates.get(source)
        if donor is not None:
            out[key] = np.asarray(donor.user_bits, np.uint8)
    return out


def frame_null(inputs: Any, keys: Sequence[Key],
               config: AnalyzerConfig | None = None, *,
               shift_tiles: int = NULL_SHIFT_TILES,
               exposure: Any = None) -> dict:
    """Right pixels, right address, another tile's certified frame."""
    config = AnalyzerConfig() if config is None else config
    exposure = fp.shared_exposure() if exposure is None else exposure
    corrupted = _shifted_certificates(inputs, shift_tiles)
    trials: list[dict] = []
    n_certificates = 0
    n_power = 0
    for key in keys:
        bit = inputs_mod.metadata_bit(inputs, key)
        null = fp.blind_key(inputs, corrupted, key, config, exposure,
                            metadata_bit=bit)
        live = fp.blind_key(inputs, inputs.certificates, key, config,
                            exposure, metadata_bit=bit)
        certified = null.get("user_bits") is not None
        n_certificates += int(certified)
        n_power += int(live.get("user_bits") is not None)
        entry = {"key": list(key), "frame_null_certifies": certified,
                 "truthful_certifies": live.get("user_bits") is not None,
                 "refusal": null.get("refusal")}
        if certified:
            # Truth-free and stronger than a GT column here: the frame
            # null's certificate is compared with the run's OWN
            # certificate for this key when there is one, so a hit that
            # merely reproduces the right answer from a corrupted frame
            # is told apart from one that invents bits.
            standing = inputs.certificates.get(key)
            entry["matches_production"] = (
                None if standing is None else bool(np.array_equal(
                    np.asarray(null["user_bits"], np.uint8),
                    np.asarray(standing.user_bits, np.uint8))))
        trials.append(entry)
    return {
        "control": "frame_null",
        "shift_tiles": int(shift_tiles),
        "n_trials": len(keys),
        "n_certificates": int(n_certificates),
        "power_denominator": int(n_power),
        "passes": bool(n_certificates == 0),
        "trials": trials,
    }


# ------------------------------------------------------ positive control

def _closest_arm(row: LedgerRow) -> dict | None:
    best: tuple[float, str] | None = None
    for name, blind in row.evidence.items():
        if name == "_selected" or not isinstance(blind, Mapping):
            continue
        loss = blind.get("heldout_logloss_select")
        if loss is None:
            continue
        value = float(loss)
        if best is None or value < best[0]:
            best = (value, name)
    if best is None:
        return None
    return {"arm": best[1], "heldout_logloss_select": best[0]}


def positive_control(inputs: Any, withheld: Sequence[Key],
                     config: AnalyzerConfig | None = None, *,
                     census_rows: Sequence[LedgerRow] | None = None,
                     exposure: Any = None) -> dict:
    """Withhold real certificates and try to win them back (DESIGN §8)."""
    if not withheld:
        raise ControlError("positive_control: the withhold set is empty")
    config = AnalyzerConfig() if config is None else config
    refused = tuple(sorted(set(config.refused_arms) | set(FIELD_ARMS)))
    config = dc_replace(config, refused_arms=refused, max_generations=1,
                        targets_from="positive_control")
    keys = tuple(withheld)
    certs = {key: value for key, value in inputs.certificates.items()
             if key not in set(keys)}
    ledger = fp.run(inputs, list(keys), config,
                    census_rows=census_rows, exposure=exposure, certs=certs)

    by_key = {row.key: row for row in ledger.rows}
    per_key: list[dict] = []
    strata: dict[tuple[str, str], list[bool]] = {}
    for key in keys:
        row = by_key.get(key)
        recovered = bool(row is not None and row.verdict == VERDICT_CERTIFIED)
        certificate = inputs.certificates.get(key)
        source = "unknown" if certificate is None else str(certificate.source)
        band = "unclassified" if row is None else str(row.band)
        strata.setdefault((source, band), []).append(recovered)
        entry: dict[str, Any] = {
            "key": list(key), "recovered": recovered,
            "source": source, "band": band,
            "certifying_rule": None if row is None else row.certifying_rule,
            "certifying_rung": None if row is None else row.certifying_rung,
            "matches_production": _matches_production(inputs, key, row),
        }
        if not recovered and row is not None:
            entry["closest_arm"] = _closest_arm(row)
            entry["refusal"] = (row.diag or {}).get("refusal")
            entry["min_unsat"] = _min_unsat(row)
        per_key.append(entry)

    n_recovered = sum(1 for item in per_key if item["recovered"])
    n_disagreeing = sum(1 for item in per_key
                        if item["matches_production"] is False)
    stratum_rows = []
    passes = n_disagreeing == 0
    for (source, band), flags in sorted(strata.items()):
        k, n = sum(flags), len(flags)
        low, high = clopper_pearson(k, n)
        graded = n >= POSITIVE_CONTROL_MIN_STRATUM
        ok = (not graded) or (k / n) >= POSITIVE_CONTROL_BAR
        passes = passes and ok
        stratum_rows.append({
            "source": source, "band": band, "n": n, "recovered": k,
            "fraction": k / n if n else None,
            "clopper_pearson_95": [low, high],
            "graded": graded, "passes_bar": ok})
    return {
        "control": "positive_control",
        "n_withheld": len(keys),
        "n_recovered": int(n_recovered),
        "n_disagreeing_with_production": int(n_disagreeing),
        "fraction": n_recovered / len(keys),
        "bar": POSITIVE_CONTROL_BAR,
        "min_graded_stratum": POSITIVE_CONTROL_MIN_STRATUM,
        "refused_arms": list(refused),
        "control_inputs_refit": {
            "certificates": "withheld keys removed from the frame",
            "plane_fields": "refused (the `field` arms are not run)",
            "pooled_ctx": "not used (the analyzer's context is per-footprint,"
                          " refitted from this footprint's own cells)",
            "placements": "CONTAMINATED — placement search saw the withheld "
                          "tiles; bounded by a committed-only run",
        },
        "strata": stratum_rows,
        "passes": bool(passes),
        "per_key": per_key,
        "exposure_distinct": int(ledger.exposure.distinct)
        if ledger.exposure else None,
    }


# ------------------------------------------- the stratified sheet-I holdout

#: Q1.7's pass: the default battery, both cheap combination rules, and the
#: direct rungs.  ONE pass, generation 0 — a cascade would let a recovered
#: key help the next one and the measured number would no longer be "what
#: the analyzer does to a residue the receiver left", which is what H's
#: conversion rate is being predicted from.
HOLDOUT_RULES: tuple[str, ...] = ("sum", "best")
HOLDOUT_RUNGS: tuple[str, ...] = ("L0", "L1", "L2", "L7")


def parse_holdout_spec(spec: str) -> dict[tuple[str, str], int]:
    """`'Y:tiles/planek150=60,C:tiles/local150=20'` -> {(stream, source): n}.

    The source strings are the REAL ones (`tiles/<stage>`, PLAN §1.3); a
    stream/source pair that names no certificate simply contributes an
    empty stratum, which the report shows as ``n = 0`` rather than
    silently dropping.
    """
    out: dict[tuple[str, str], int] = {}
    for item in str(spec).split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item or ":" not in item.split("=")[0]:
            raise ControlError(
                f"holdout spec {item!r} is not '<stream>:<source>=<count>' "
                f"(e.g. 'Y:tiles/planek150=60')")
        left, count = item.rsplit("=", 1)
        stream, source = left.split(":", 1)
        try:
            n = int(count)
        except ValueError as error:
            raise ControlError(
                f"holdout spec {item!r}: {count!r} is not a count") from error
        if n <= 0:
            raise ControlError(f"holdout spec {item!r}: count must be > 0")
        out[(stream.strip(), source.strip())] = n
    if not out:
        raise ControlError("holdout spec is empty")
    return out


def holdout_selection(census_rows: Sequence[LedgerRow],
                      wanted: Mapping[tuple[str, str], int], seed: int,
                      ) -> tuple[tuple[Key, ...], list[dict]]:
    """The deterministic sample: per (stream, source), spread over bands.

    "If a source has fewer certificates than requested, take all" — the
    request is a ceiling, never a promise, and the shortfall is reported
    rather than made up from another source.
    """
    keys: list[Key] = []
    plan: list[dict] = []
    for (stream, source), n in sorted(wanted.items()):
        pool = [row for row in census_rows
                if row.certified_by_production
                and str(row.stream_id) == stream
                and str(row.source) == source]
        picked = stratified_sample(pool, int(n), int(seed), streams=(stream,))
        keys.extend(row.key for row in picked)
        plan.append({"stream": stream, "source": source, "requested": int(n),
                     "available": len(pool), "taken": len(picked),
                     "short": bool(len(picked) < int(n))})
    return tuple(sorted(set(keys))), plan


def _matches_production(inputs: Any, key: Key,
                        row: LedgerRow | None) -> bool | None:
    """Does the re-derived certificate equal PRODUCTION's own bits?

    The fourth leg of the 2026-09-04 ruling: two independent paths that
    certify one tile must agree bit-for-bit.  `None` when there is
    nothing to compare (no certificate here, or none there).
    """
    standing = inputs.certificates.get(key)
    bits = None if row is None else row.rungs.get("user_bits")
    if standing is None or bits is None:
        return None
    return bool(np.array_equal(np.asarray(bits, np.uint8),
                               np.asarray(standing.user_bits, np.uint8)))


def _distribution(values: Sequence[float]) -> dict:
    if not values:
        return {"n": 0}
    array = np.asarray(values, np.float64)
    quantiles = np.quantile(array, [0.0, 0.25, 0.5, 0.75, 1.0])
    return {"n": int(array.size),
            "min": float(quantiles[0]), "q25": float(quantiles[1]),
            "median": float(quantiles[2]), "q75": float(quantiles[3]),
            "max": float(quantiles[4]),
            "mean": float(array.mean()),
            "fraction_below_1": float(np.mean(array < 1.0))}


def stratified_holdout(inputs: Any,
                       census_rows: Sequence[LedgerRow], spec: str,
                       config: AnalyzerConfig | None = None, *,
                       exposure: Any = None) -> dict:
    """DESIGN §8's Q1.7 holdout: withhold by (stream, source), win back.

    Sheet H's dead bands are where the code has NO margin, so the
    conversion rate that matters is measured where it does: production
    certificates of sheet I, withheld ALL AT ONCE (the frame, and every
    input fitted with them, rebuilt without them), then attacked by the
    default battery in ONE pass.  The output is the recovered fraction per
    (stream, source, band) with exact intervals, plus the R distribution
    of the MISSES — the number that says whether a miss was a converse or
    a failure.
    """
    config = AnalyzerConfig() if config is None else config
    wanted = parse_holdout_spec(spec)
    keys, plan = holdout_selection(census_rows, wanted, int(config.seed))
    if not keys:
        raise ControlError(
            f"stratified holdout {spec!r} selected no certificate — check "
            f"the source strings against the run's own (PLAN §1.3)")
    refused = tuple(sorted(set(config.refused_arms) | set(FIELD_ARMS)))
    local = dc_replace(config, refused_arms=refused, max_generations=1,
                       rules=HOLDOUT_RULES, rungs=HOLDOUT_RUNGS,
                       targets_from=f"holdout_stratified:{spec}")
    certs = {key: value for key, value in inputs.certificates.items()
             if key not in set(keys)}
    ledger = fp.run(inputs, list(keys), local,
                    census_rows=census_rows, exposure=exposure, certs=certs)

    by_key = {row.key: row for row in ledger.rows}
    strata: dict[tuple[str, str, str], list[bool]] = {}
    misses: list[float] = []
    n_disagreeing = 0
    per_key: list[dict] = []
    for key in keys:
        row = by_key.get(key)
        recovered = bool(row is not None and row.verdict == VERDICT_CERTIFIED)
        certificate = inputs.certificates.get(key)
        source = "unknown" if certificate is None else str(certificate.source)
        band = "unclassified" if row is None else str(row.band)
        strata.setdefault((str(key[3]), source, band), []).append(recovered)
        entry: dict[str, Any] = {
            "key": list(key), "recovered": recovered, "source": source,
            "band": band,
            "certifying_rule": None if row is None else row.certifying_rule,
            "certifying_rung": None if row is None else row.certifying_rung,
            "matches_production": _matches_production(inputs, key, row)}
        n_disagreeing += int(entry["matches_production"] is False)
        if not recovered and row is not None:
            entry["closest_arm"] = _closest_arm(row)
            entry["refusal"] = (row.diag or {}).get("refusal")
            entry["min_unsat"] = _min_unsat(row)
            if entry["min_unsat"] is not None:
                misses.append(float(entry["min_unsat"]))
        per_key.append(entry)

    stratum_rows = []
    for (stream, source, band), flags in sorted(strata.items()):
        k, n = sum(flags), len(flags)
        low, high = clopper_pearson(k, n)
        stratum_rows.append({
            "stream": stream, "source": source, "band": band, "n": n,
            "recovered": k, "fraction": k / n if n else None,
            "clopper_pearson_95": [low, high]})
    n_recovered = sum(1 for item in per_key if item["recovered"])
    low, high = clopper_pearson(n_recovered, len(keys))
    return {
        "control": "stratified_holdout",
        "spec": str(spec),
        "plan": plan,
        "rules": list(HOLDOUT_RULES),
        "rungs": list(HOLDOUT_RUNGS),
        "generation": 0,
        "n_withheld": len(keys),
        "n_recovered": int(n_recovered),
        "n_disagreeing_with_production": int(n_disagreeing),
        "fraction": n_recovered / len(keys),
        "clopper_pearson_95": [low, high],
        "refused_arms": list(refused),
        "control_inputs_refit": {
            "certificates": "withheld keys removed from the frame",
            "plane_fields": "refused (the `field` arms are not run)",
            "pooled_ctx": "not used (the analyzer's context is per-footprint,"
                          " refitted from this footprint's own cells)",
            "placements": "CONTAMINATED — placement search saw the withheld "
                          "tiles; bounded by a committed-only run",
        },
        "strata": stratum_rows,
        # Was the R distribution of the misses; R is an oracle column and
        # left with truth.  The blind statistic that answers the same
        # question — "is this miss near the code's edge, or nowhere near
        # it" — is the unsatisfied-check count at exit.
        "miss_min_unsat_distribution": _distribution(misses),
        "per_key": per_key,
        "exposure_distinct": (int(ledger.exposure.distinct)
                              if ledger.exposure else None),
    }


def _min_unsat(row: LedgerRow) -> int | None:
    values = []
    for rule, batch in row.rungs.items():
        if rule == "user_bits" or not isinstance(batch, list):
            continue
        for item in batch:
            value = item.get("unsat_at_exit")
            if value is not None and int(value) >= 0:
                values.append(int(value))
    return min(values) if values else None


# ----------------------------------------------------------- parity sample

#: DESIGN §8's parity configurations: the DEFAULT arm is the gate; the
#: other two are REPORTED beside it, never gating.
PARITY_CONFIGURATIONS: tuple[tuple[str, str, str], ...] = (
    ("default", "subtract+offset", "production"),
    ("subtract+committed/ctx-none", "subtract+committed", "none"),
    ("head+offset", "head+offset", "production"),
)


def parity_sample(inputs: Any, census_rows: Sequence[LedgerRow],
                  config: AnalyzerConfig | None = None, *,
                  n_per_stream: int = 100,
                  configurations: Sequence[tuple[str, str, str]] | None = None,
                  exposure: Any = None) -> dict:
    """Re-derive production certificates with the default arm (DESIGN §8)."""
    config = AnalyzerConfig() if config is None else config
    certified = [row for row in census_rows if row.certified_by_production]
    sample = stratified_sample(certified, int(n_per_stream), config.seed)
    if not sample:
        raise ControlError("parity_sample: no production certificate to draw")
    out: dict[str, Any] = {
        "control": "parity_sample",
        "n_per_stream": int(n_per_stream),
        "n_sampled": len(sample),
        "bar": PARITY_BAR,
        "configurations": {},
    }
    for name, arm, ctx_mode in (configurations or PARITY_CONFIGURATIONS):
        # THE RE-ROLL IS OFF HERE (GAPS-2026-09-03 §7, RULED 2026-09-03).
        # A parity number means "what ONE configuration re-derives of
        # production's certificates"; a re-roll spends the rest of the
        # battery, which is exactly the attempt-count the number is
        # measuring the absence of.  Letting it run would make the bar
        # pass by changing the question.  `reroll` is ON for a decoding
        # pass, where yield is the point.
        local = dc_replace(config, arms=(arm,), ctx_mode=ctx_mode,
                           rules=("sum",), rungs=("L0", "L1"),
                           max_generations=1, refused_arms=(),
                           reroll=False,
                           targets_from=f"parity:{name}")
        ledger = fp.run(inputs, list(sample), local,
                        census_rows=census_rows,
                        exposure=exposure or fp.shared_exposure())
        by_stream: dict[str, list[bool]] = {}
        wrong = 0
        for row in ledger.rows:
            hit = row.verdict == VERDICT_CERTIFIED
            by_stream.setdefault(row.stream_id, []).append(hit)
            if hit and _matches_production(inputs, row.key, row) is False:
                wrong += 1
        table = {}
        gate = True
        for stream in sorted(by_stream):
            flags = by_stream[stream]
            k, n = sum(flags), len(flags)
            low, high = clopper_pearson(k, n)
            ok = (k / n) >= PARITY_BAR if n else False
            gate = gate and ok
            table[stream] = {"n": n, "re_derived": k,
                             "rate": k / n if n else None,
                             "clopper_pearson_95": [low, high],
                             "passes_bar": ok}
        out["configurations"][name] = {
            "arm": arm, "ctx_mode": ctx_mode, "by_stream": table,
            "n_disagreeing_with_production": int(wrong),
            "gating": name == "default",
            "passes": bool(gate and wrong == 0) if name == "default" else None,
        }
    out["passes"] = bool(out["configurations"]["default"]["passes"]) \
        if "default" in out["configurations"] else None
    return out


def residue_keys(census_rows: Sequence[LedgerRow]) -> list[Key]:
    return [row.key for row in residue_mod.residue_rows(census_rows)]
