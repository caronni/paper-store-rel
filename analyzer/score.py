"""`analyzer score` — the OFFLINE scorer (RULED 2026-09-04).

    analyzer score --ledger L [--ledger L2 …] --payload P
                   [--gt-dir G] [--run-dir R] --out DIR

A run knows nothing about any payload.  Everything that used to be an
oracle column of a ledger is computed HERE, afterwards, from the ledger
plus a payload — and the payload may be one nobody handed us:

* the EMITTED payload of the generation dir (with `--gt-dir` its
  manifest sha-gates it, and its emitted per-cell field enables the
  cell-level splits), or
* a payload a CLOSE recovered (`analyzer close` writes `payload.bin`).
  The envelope `{sha256}{len}{data}` is what says those bytes are the
  volume's, so scoring against them is scoring against the volume the
  instrument itself proved — no manifest, no generation dir, and it
  works on a sheet whose emission we no longer hold.

WHAT IT ANSWERS.

* **Every certificate, bit for bit.**  Each ledger row that carries user
  bits is compared with the payload's reconstruction of that key.  A
  mismatch is reported as `wrong` (a direct rung: nothing priced it) or
  `false_accept` (a list rung: the exposure bound did), it is COUNTED in
  the headline, and the report says which key.  Never silent.
* **Bits wrong at exit, per rung**, from the packed exit hard vectors the
  ledger carries (`detail.hard_packed_b64`), with all four denominators
  named — the histogram DESIGN §6's deferral rule reads, computed after
  the run instead of during it.
* **The detector columns** — soft information rate R with its bootstrap
  bound, cell error at the calibrated MAP decision and at the median
  threshold, d′, ROC AUC, the splits by true sibling state and context
  bin, capture agreement on the wrong cells — which need the per-cell
  LLRs and therefore need `--run-dir`: the evidence is RECOMPUTED there,
  blind, by the same `arms.evidence_for` the run called.
* **The waterfall** P(certify | R) per stream and rung, which needs R and
  so needs `--run-dir` too.

THE RECOMPUTED EVIDENCE IS LABELLED, and here is the honest caveat: the
run scored each key against the frame it had AT THAT GENERATION, while
this recomputation uses one frame for all of them — the run dir's own
certificates, plus (by default) every certificate the ledgers minted, so
the fixed point's FINAL state.  For a detector measurement that is the
right frame and a better one; for reproducing what a particular attempt
saw it is not, and the report says `evidence_frame` so no reader has to
guess.  `--limit` bounds the cost (a footprint read is 10-40 ms per lane
and there are thousands of rows).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from . import frame as frame_mod
from . import ledger as ledger_mod
from . import mother as mother_mod
from . import oracle as oracle_mod
from . import sample as sample_mod
from . import truth as truth_mod
from .types import (LIST_RUNGS, VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST,
                    VERDICT_FALSE_ACCEPT, VERDICT_UNSCOREABLE, VERDICT_WRONG,
                    AnalyzerConfig, Key, Truth)

SCORE_ROWS = "score.jsonl"
SCORE_REPORT = "score.md"

#: How many rows get their evidence recomputed when `--run-dir` is given
#: and `--limit` is not.  `None` = all of them.
DEFAULT_LIMIT: int | None = None


class ScoreError(RuntimeError):
    """The scorer refuses — nothing it would say could be trusted."""


# ------------------------------------------------------------- the inputs

def read_headers(paths: Sequence[Path | str]) -> list[tuple[str, dict]]:
    """Header lines only — the rows are STREAMED, never materialised.

    Sheet H's five passes are 2.6-5.8 GB of JSON each and 18 GB in
    total; a first cut of this tool called `ledger.read_rows` on all of
    them and reached 26 GB of RSS before it was killed.  Nothing here
    ever holds more than one raw row at a time.
    """
    out: list[tuple[str, dict]] = []
    for path in paths:
        path = Path(path)
        if not path.exists():
            raise ScoreError(f"ledger {path} is absent")
        out.append((str(path), ledger_mod.read_header(path)))
    if not out:
        raise ScoreError("no --ledger given")
    return out


def format_ref_of(headers: Sequence[tuple[str, Mapping[str, Any]]],
                  override: str | None) -> str:
    if override:
        return str(override)
    seen = {str(header["format_ref"]) for _name, header in headers
            if header.get("format_ref")}
    if not seen:
        raise ScoreError(
            "no ledger header declares a format ref; pass --format-ref")
    if len(seen) > 1:
        raise ScoreError(
            f"the ledgers declare different format refs {sorted(seen)}; "
            f"pass --format-ref to say which sheet this is")
    return sorted(seen)[0]


def key_of(row: Mapping[str, Any]) -> Key:
    return (int(row["page"]), int(row["ty"]), int(row["tx"]),
            str(row["stream_id"]))


#: Pages the GT reconstruction is built for when nothing says otherwise.
#: A run dir names its own live pages; without one this is the number,
#: and a row from a higher page REFUSES rather than being mis-scored
#: (sheet J is the two-page case, `--pages 2`).
DEFAULT_PAGES = 1


def row_user_bits(row: Mapping[str, Any]) -> np.ndarray | None:
    bits = (row.get("rungs") or {}).get("user_bits")
    if bits is None:
        return None
    bits = np.asarray(bits, np.uint8)
    return None if bits.size == 0 else bits


def _is_list_rung(rung: str | None) -> bool:
    return str(rung or "").split(":")[0] in LIST_RUNGS


# ------------------------------------------------------ scoring one row

def score_row(row: Mapping[str, Any], truth: Truth, row_format: Any,
              *, mother_cache: dict) -> dict:
    """One ledger row scored: the certificate, then every rung."""
    key = key_of(row)
    out: dict[str, Any] = {
        "page": key[0], "ty": key[1], "tx": key[2], "stream_id": key[3],
        "band": row.get("band"),
        "blind_verdict": row.get("verdict"),
        "certifying_rule": row.get("certifying_rule"),
        "certifying_rung": row.get("certifying_rung"),
        "certifying_arm": row.get("certifying_arm"),
        "generation": row.get("generation"),
        "scoreable": key in truth.user_bits,
        "rungs": {},
    }
    bits = row_user_bits(row)
    truth_bits = truth.user_bits.get(key)
    if bits is None:
        out["verdict"] = row.get("verdict")
    elif truth_bits is None:
        out["verdict"] = VERDICT_UNSCOREABLE
        out["reason"] = "address outside the GT domain"
    else:
        want = np.asarray(truth_bits, np.uint8).ravel()
        if want.size != bits.size:
            out["verdict"] = VERDICT_UNSCOREABLE
            out["reason"] = (f"GT carries {want.size} user bits, the "
                             f"certificate {bits.size}")
        else:
            n_bad = int(np.count_nonzero(want != bits))
            out["certificate_bits_wrong"] = n_bad
            out["certificate_matches_gt"] = n_bad == 0
            out["verdict"] = oracle_mod.verdict_against_truth(
                str(row.get("certifying_rung")),
                str(row.get("verdict")), n_bad)

    mother = mother_cache.get(key)
    if mother is None:
        mother = mother_mod.to_mother(
            np.zeros(int(row_format.payload_cells), np.float64),
            row_format, key, metadata_bit=None)
        mother_cache[key] = mother
    certifying = str(row.get("certifying_rung") or "")
    for rule, batch in (row.get("rungs") or {}).items():
        if rule == "user_bits" or not isinstance(batch, list):
            continue
        scored = []
        for item in batch:
            if not isinstance(item, dict):
                continue
            # Only the CERTIFYING rung of the CERTIFYING rule minted the
            # row's user bits; handing them to any other rung would score
            # a certificate that rung never produced.
            mine = (bits if (str(item.get("rung")) == certifying
                             and rule == row.get("certifying_rule"))
                    else None)
            scored.append(oracle_mod.score_rung(item, truth, key, mother,
                                                user_bits=mine))
        out["rungs"][str(rule)] = scored
    return out


# ------------------------------------------- the recomputed evidence leg

def evidence_for_row(inputs: Any, certs: Mapping[Key, Any], key: Key,
                     truth: Truth, config: AnalyzerConfig) -> dict:
    """Recompute the DEFAULT arm's evidence, blind, and score it.

    The battery's first arm is the pinned default (DESIGN §4.8); scoring
    the whole battery would multiply the cost of a column the default
    arm answers, and any other arm can be asked for by naming it first
    in `--arms`.
    """
    from . import arms as arms_mod
    from . import fixedpoint as fp

    page, ty, tx, stream_id = key
    battery = config.battery_for(str(stream_id))
    if not battery:
        return {"refusal": "no arm for this stream"}
    arm = battery[0]
    halo = fp._halo_for(config, str(stream_id))
    lanes = sample_mod.lanes_for_tile(inputs, int(page), int(ty), int(tx),
                                      cover_fraction=config.cover_fraction)
    if not lanes:
        return {"refusal": "no_lane_sees_this_tile"}
    footprint = frame_mod.tile_footprint(inputs.row, int(page), int(ty),
                                         int(tx), halo,
                                         geometry=inputs.geometry)
    from . import inputs as inputs_mod
    bit = inputs_mod.metadata_bit(inputs, key)
    known = frame_mod.known_frame(
        inputs, certs, footprint, key,
        metadata_known=bool(config.metadata_known and bit is not None),
        metadata_bit=bit)
    evidences = []
    for lane in lanes:
        knobs = fp._knobs_for(inputs, config, key, lane, bit, None)
        evidences.append(arms_mod.evidence_for(
            inputs, certs, key, lane, arm, halo_cells=halo, knobs=knobs))
    out: dict[str, Any] = {"arm": arm, "lanes": len(evidences)}
    for evidence in evidences:
        lane = inputs.lane(evidence.lane)
        lfp = sample_mod.lane_footprint(lane, footprint)
        if lfp is None:
            continue
        name = f"{evidence.lane[0][:12]}/l{evidence.lane[1]}"
        out[name] = oracle_mod.score_evidence(
            evidence, truth, known, lfp, inputs.row, key, others=evidences,
            seed=_evidence_seed(config.seed, key, name, arm))
    return out


def _evidence_seed(seed: int, key: Key, lane_name: str, arm: str) -> int:
    """DESIGN §0: a draw is a HASH of (seed, key, …), not the seed.

    The same spelling the run used for the same bootstrap, so a scorer
    run against the same seed resamples the same way.
    """
    import hashlib
    material = f"{int(seed)}|{key}|{lane_name}|{arm}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(material, digest_size=6).digest(),
                          "big")


# --------------------------------------------------------- the aggregates

def bits_wrong_histogram(scored_rows: Sequence[Mapping[str, Any]]) -> dict:
    """The oracle half of DESIGN §6's deferral input, per rung and total."""
    values: list[int] = []
    per_rung: dict[str, list[int]] = {}
    for row in scored_rows:
        for _rule, batch in (row.get("rungs") or {}).items():
            for item in batch:
                value = item.get("bits_wrong_active")
                if value is None:
                    continue
                values.append(int(value))
                per_rung.setdefault(str(item.get("rung")), []).append(
                    int(value))
    edges = list(ledger_mod.HISTOGRAM_EDGES)
    return {
        "bits_wrong_active": ledger_mod._histogram(values, edges),
        "n_samples": len(values),
        "by_rung": {name: ledger_mod._histogram(items, edges)
                    for name, items in sorted(per_rung.items())},
    }


def waterfall_rows(scored_rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Flatten (R, rung, certified) for `oracle.waterfall`.

    R is the row's BEST lane — the best evidence the analyzer had — and
    a rung counts as certified when its scored verdict is a certificate
    that survived the payload comparison.
    """
    out: list[dict] = []
    for row in scored_rows:
        rates = [entry.get("R")
                 for entry in (row.get("evidence") or {}).values()
                 if isinstance(entry, Mapping) and entry.get("R") is not None]
        if not rates:
            continue
        rate = float(np.max(rates))
        for _rule, batch in (row.get("rungs") or {}).items():
            for item in batch:
                out.append({"stream_id": str(row.get("stream_id")),
                            "rung": str(item.get("rung")), "R": rate,
                            "certified": item.get("verdict") in (
                                VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST)})
    return out


def verdict_counts(scored_rows: Sequence[Mapping[str, Any]]) -> dict:
    out: dict[str, int] = {}
    for row in scored_rows:
        name = str(row.get("verdict"))
        out[name] = out.get(name, 0) + 1
    return dict(sorted(out.items()))


def wrong_keys(scored_rows: Sequence[Mapping[str, Any]]) -> list[dict]:
    """Every certificate that disagreed with the payload, named."""
    out = []
    for row in scored_rows:
        if row.get("verdict") not in (VERDICT_WRONG, VERDICT_FALSE_ACCEPT):
            continue
        out.append({"key": [row["page"], row["ty"], row["tx"],
                            row["stream_id"]],
                    "verdict": row["verdict"],
                    "certifying_rung": row.get("certifying_rung"),
                    "certifying_rule": row.get("certifying_rule"),
                    "list_rung": _is_list_rung(row.get("certifying_rung")),
                    "bits_wrong": row.get("certificate_bits_wrong")})
    return out


# ---------------------------------------------------------------- the run

def score(ledger_paths: Sequence[Path | str], payload: Path | str,
          out_dir: Path | str, *, gt_dir: Path | str | None = None,
          run_dir: Path | str | None = None,
          format_ref: str | None = None,
          config: AnalyzerConfig | None = None,
          limit: int | None = DEFAULT_LIMIT,
          n_pages: int | None = None,
          fold_ledger_certificates: bool = True) -> dict:
    """Score the ledgers against `payload`; writes score.jsonl + score.md.

    The ledgers are STREAMED (a sheet-H pass is gigabytes), so the peak
    memory is one raw row plus the scored rows, which carry summaries.
    """
    from holo3.format import identity

    config = AnalyzerConfig() if config is None else config
    headers = read_headers(ledger_paths)
    ref = format_ref_of(headers, format_ref)
    inputs = None
    if run_dir is not None:
        from . import inputs as inputs_mod
        inputs = inputs_mod.load_run(run_dir, format_ref=ref)
        row_format = inputs.row
        pages = max(inputs.live_pages) + 1 if n_pages is None else int(n_pages)
    else:
        try:
            row_format = identity.resolve_format_ref(ref)
        except ValueError as error:
            raise ScoreError(
                f"format ref {ref!r} does not resolve: {error}") from error
        pages = DEFAULT_PAGES if n_pages is None else int(n_pages)

    truth = truth_mod.load_truth(gt_dir, payload, row_format, pages,
                                 format_ref=ref)
    gates: dict[str, Any] = {}
    if inputs is not None:
        gates = truth_mod.validate_truth(truth, inputs, inputs.geometry)

    rows: list[dict] = []
    counts: list[dict] = []
    mother_cache: dict = {}
    minted: dict[Key, np.ndarray] = {}
    seen: set[Key] = set()
    for name, _header in headers:
        n_rows = 0
        for raw in ledger_mod.iter_rows(name):
            n_rows += 1
            key = key_of(raw)
            if int(key[0]) >= pages:
                raise ScoreError(
                    f"{name} carries a row on page {key[0]} but the GT "
                    f"reconstruction covers {pages} page(s): pass --pages "
                    f"{key[0] + 1} (sheet J is the two-page case)")
            bits = row_user_bits(raw)
            if bits is not None:
                minted.setdefault(key, bits)
            if key in seen and bits is None:
                continue                  # a later pass re-attacked it
            seen.add(key)
            scored = score_row(raw, truth, row_format,
                               mother_cache=mother_cache)
            scored["ledger"] = name
            rows.append(scored)
        counts.append({"path": name, "n_rows": n_rows})

    if inputs is not None:
        from . import close as close_mod
        certs = dict(inputs.certificates)
        if fold_ledger_certificates:
            for key, bits in minted.items():
                if key not in certs:
                    certs[key] = close_mod.as_certificate(key, bits)
        n_done = 0
        for scored in rows:
            if limit is not None and n_done >= int(limit):
                break
            key = (scored["page"], scored["ty"], scored["tx"],
                   scored["stream_id"])
            scored["evidence"] = evidence_for_row(inputs, certs, key, truth,
                                                  config)
            n_done += 1

    water = oracle_mod.waterfall(waterfall_rows(rows))
    n_rows_by_path = {item["path"]: item["n_rows"] for item in counts}
    header = {
        "tool": "analyzer score",
        "format_ref": ref,
        "payload": str(payload),
        "payload_sha256": truth.payload_sha256,
        "payload_bytes": int(truth.payload_bytes),
        "payload_source": ("generation manifest (sha-gated)"
                           if gt_dir is not None else
                           "given bytes (no manifest; a close's payload.bin "
                           "is verified by its own envelope)"),
        "gt_dir": None if gt_dir is None else str(gt_dir),
        "has_emitted_field": bool(truth.fields),
        "n_pages": int(pages),
        "run_dir": None if run_dir is None else str(run_dir),
        "evidence_frame": (
            None if inputs is None else
            ("run certificates + every certificate the ledgers minted "
             "(the fixed point's FINAL frame)" if fold_ledger_certificates
             else "the run dir's own certificates only")),
        "evidence_limit": None if limit is None else int(limit),
        "ledgers": [{"path": name, "n_rows": n_rows_by_path.get(name),
                     "seed": head.get("seed"),
                     "rules": head.get("rules"), "rungs": head.get("rungs"),
                     "exposure_distinct": head.get("exposure_distinct"),
                     "exposure_expected_false": head.get(
                         "exposure_expected_false")}
                    for name, head in headers],
        "gates": gates,
        "n_rows": len(rows),
        "verdicts": verdict_counts(rows),
        "n_certificates_checked": sum(
            1 for row in rows if row.get("certificate_matches_gt")
            is not None),
        "n_wrong": sum(1 for row in rows
                       if row.get("verdict") == VERDICT_WRONG),
        "n_false_accept": sum(1 for row in rows
                              if row.get("verdict") == VERDICT_FALSE_ACCEPT),
        "bits_wrong": bits_wrong_histogram(rows),
        "waterfall": water,
        "wrong_keys": wrong_keys(rows),
    }

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / SCORE_ROWS, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(
            {"type": "header", **ledger_mod.jsonable(header)}) + "\n")
        for row in rows:
            stream.write(json.dumps(
                {"type": "row", **ledger_mod.jsonable(row)}) + "\n")
    report = render(header, rows)
    (out_dir / SCORE_REPORT).write_text(report, "utf-8")
    header["report"] = report
    header["out_dir"] = str(out_dir)
    return header


# ------------------------------------------------------------- the report

def render(header: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
           ) -> str:
    table = ledger_mod._table
    parts: list[str] = ["# analyzer score", ""]
    parts.append(table(["field", "value"], [
        ["format", header.get("format_ref")],
        ["payload", header.get("payload")],
        ["payload sha256", header.get("payload_sha256")],
        ["payload bytes", header.get("payload_bytes")],
        ["payload source", header.get("payload_source")],
        ["emitted field", header.get("has_emitted_field")],
        ["run dir", header.get("run_dir")],
        ["evidence frame", header.get("evidence_frame")],
        ["ledgers", len(header.get("ledgers", []) or [])],
        ["rows", header.get("n_rows")]]))

    parts += ["", "## Certificates against the payload", ""]
    parts.append(table(
        ["field", "value"],
        [["certificates checked", header.get("n_certificates_checked")],
         ["WRONG (direct rung)", header.get("n_wrong")],
         ["false accepts (list rung)", header.get("n_false_accept")]]))
    if header.get("wrong_keys"):
        parts += ["", "**Disagreeing certificates — every one of them:**", ""]
        parts.append(table(
            ["key", "verdict", "rule", "rung", "bits wrong"],
            [[item["key"], item["verdict"], item["certifying_rule"],
              item["certifying_rung"], item["bits_wrong"]]
             for item in header["wrong_keys"]]))
    else:
        parts += ["", "No certificate disagreed with the payload.", ""]

    parts += ["", "## Verdicts", ""]
    parts.append(table(["verdict", "n"],
                       list((header.get("verdicts") or {}).items())))

    hist = header.get("bits_wrong") or {}
    parts += ["", "## Bits wrong at exit (over the ACTIVE bits)", "",
              f"{hist.get('n_samples', 0)} rung outcome(s), from the packed "
              f"exit hard vectors the ledger carries.", ""]
    parts.append(table(["bucket", "n"],
                       list((hist.get("bits_wrong_active") or {}).items())))

    parts += ["", "## Soft information rate", ""]
    water = header.get("waterfall") or {}
    if water:
        parts.append(table(
            ["stream/rung", "n", "certified", "R median", "R05", "R50"],
            [[name, body["n"], body["n_certified"],
              round(body["R_median"], 4),
              None if body["R05"] is None else round(body["R05"], 4),
              None if body["R50"] is None else round(body["R50"], 4)]
             for name, body in water.items()]))
    else:
        parts.append("no waterfall — R needs the per-cell LLRs, which need "
                     "`--run-dir` (the evidence is recomputed there).")

    parts += ["", "## Cell error, by lane", ""]
    body = []
    for row in rows:
        for name, entry in (row.get("evidence") or {}).items():
            if not isinstance(entry, Mapping) or entry.get("R") is None:
                continue
            body.append([f"{row['page']},{row['ty']},{row['tx']},"
                         f"{row['stream_id']}", name,
                         round(float(entry["cell_error_map"]), 5),
                         round(float(entry["cell_error_median_threshold"]), 5),
                         None if entry.get("d_prime") is None
                         else round(float(entry["d_prime"]), 3),
                         None if entry.get("auc") is None
                         else round(float(entry["auc"]), 4),
                         round(float(entry["R"]), 4)])
    parts.append(table(
        ["key", "lane", "cell error (MAP)", "cell error (median)", "d'",
         "AUC", "R"], body[:200] or [["—"] * 7]))
    if len(body) > 200:
        parts.append(f"\n({len(body)} lane rows; the first 200 are shown — "
                     f"score.jsonl carries them all.)")

    for field, title in (("by_sibling_state",
                          "Cell error by TRUE sibling state "
                          "(state/certified, DESIGN §7)"),
                         ("by_context_bin",
                          "Cell error by context bin (neighbour ink count)")):
        split = pooled_split(rows, field)
        parts += ["", f"## {title}", ""]
        if not split:
            parts.append("no emitted field — these splits need `--gt-dir` "
                         "(the per-cell field) beside `--run-dir`.")
            continue
        parts.append(table(
            ["stream", "group", "cells", "cell error"],
            [[stream, group, body["n"], round(body["cell_error"], 5)]
             for stream, groups in split.items()
             for group, body in groups.items()]))

    agreement = pooled_agreement(rows)
    parts += ["", "## Capture agreement on the wrong cells", "",
              "The fraction of the OTHER lanes that are also wrong where "
              "this one is: high means print-frozen, low means capture "
              "noise (the multi-scan law).", ""]
    parts.append(table(
        ["stream", "lanes scored", "mean agreement"],
        [[stream, body["n"], round(body["mean"], 4)]
         for stream, body in agreement.items()] or [["—"] * 3]))
    return "\n".join(parts) + "\n"


def _lane_entries(rows: Sequence[Mapping[str, Any]]):
    """(stream_id, lane entry) for every lane the scorer actually scored."""
    for row in rows:
        for _name, entry in (row.get("evidence") or {}).items():
            if isinstance(entry, Mapping) and entry.get("scoreable"):
                yield str(row.get("stream_id")), entry


def pooled_split(rows: Sequence[Mapping[str, Any]], field: str) -> dict:
    """One split table pooled over lanes and rows, per stream.

    Pooling is by CELL COUNT — the error of a group is its own wrong
    cells over its own cells, never a mean of per-lane rates, which
    would weight a lane that saw twelve cells like one that saw four
    thousand.
    """
    out: dict[str, dict[str, dict]] = {}
    for stream, entry in _lane_entries(rows):
        for group, stats in (entry.get(field) or {}).items():
            cell = out.setdefault(stream, {}).setdefault(
                str(group), {"n": 0, "n_wrong": 0.0})
            cell["n"] += int(stats["n"])
            cell["n_wrong"] += float(stats["cell_error"]) * int(stats["n"])
    return {stream: {group: {"n": body["n"],
                             "cell_error": body["n_wrong"] / body["n"]}
                     for group, body in sorted(groups.items())
                     if body["n"]}
            for stream, groups in sorted(out.items())}


def pooled_agreement(rows: Sequence[Mapping[str, Any]]) -> dict:
    """Mean capture agreement on wrong cells, per stream."""
    out: dict[str, list[float]] = {}
    for stream, entry in _lane_entries(rows):
        value = entry.get("capture_agreement_on_wrong")
        if value is not None:
            out.setdefault(stream, []).append(float(value))
    return {stream: {"n": len(values),
                     "mean": float(np.mean(values))}
            for stream, values in sorted(out.items()) if values}


# ---------------------------------------------------------------- the map

def render_maps(rows: Sequence[Mapping[str, Any]], out_dir: Path | str, *,
                tiles_yx: tuple[int, int] | None = None,
                scale: int = 6) -> list[Path]:
    """The bits-wrong map per plane — the ledger's verdict map's twin.

    It lives here because its input is an oracle column; the blind
    verdict map stays in `analyzer.ledger`.
    """
    from PIL import Image

    rows = [dict(row) for row in rows]
    if not rows:
        return []
    if tiles_yx is None:
        tiles_yx = (max(int(row["ty"]) for row in rows) + 1,
                    max(int(row["tx"]) for row in rows) + 1)
    height, width = int(tiles_yx[0]), int(tiles_yx[1])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for stream in sorted({str(row["stream_id"]) for row in rows}):
        wrong = np.full((height, width), np.nan, np.float64)
        for row in rows:
            if str(row["stream_id"]) != stream:
                continue
            best = None
            for batch in (row.get("rungs") or {}).values():
                for item in batch:
                    value = item.get("bits_wrong_active")
                    if value is None:
                        continue
                    best = int(value) if best is None else min(best,
                                                               int(value))
            if best is not None:
                wrong[int(row["ty"]), int(row["tx"])] = float(best)
        canvas = np.zeros((height, width, 3), np.uint8)
        live = np.isfinite(wrong)
        if np.any(live):
            top = float(np.percentile(wrong[live], 99)) or 1.0
            norm = np.clip(wrong / max(top, 1.0), 0.0, 1.0)
            canvas[..., 0] = np.where(live, (norm * 255), 0).astype(np.uint8)
            canvas[..., 1] = np.where(live & (wrong == 0),
                                      220, 0).astype(np.uint8)
            canvas[..., 2] = np.where(live, 40, 0).astype(np.uint8)
        path = out_dir / f"bits-wrong-{stream}.png"
        Image.fromarray(canvas).resize(
            (width * scale, height * scale), Image.NEAREST).save(path)
        written.append(path)
    return written
