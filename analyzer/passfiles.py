"""What a pass WRITES beside its ledger, and how each product is shaped.

`fixedpoint` decides; this shapes what those decisions look like on
disk, and it exists because that file reached its 1,000-line seam when
the streamed ledger landed (2026-09-13).  Four products, one subject:

* `rung_dict` — a `RungResult` as a ledger row stores it, packed exit
  hard vector base64'd and included (the offline scorer's one input
  that nothing else can reconstruct);
* `mint_record` — one certificate as `mints.jsonl` carries it, row
  shaped so `export-facts`, `close --ledger` and `score --ledger` all
  read a killed pass's mint file with no special case;
* `_jsonable_knobs` — the knob bag as a header or a checkpoint spells
  it, a value it cannot spell degrading to its `repr`;
* the in-run `field2.json` (PAGE-FIELD-PLAN A2) — the pooled fields the
  run's own arms fitted, beside the production revision that STOOD for
  each (page, plane).

Every name is re-exported from `fixedpoint`, which is where the CLI and
the tests read them off, exactly as `Progress` and the stop door are
read off it and live in `stopdoor`.

BLIND like everything a run command can reach: no `truth`, no `oracle`,
not as an import and not as an argument (DESIGN §0, pinned by the
import-closure test).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from holo.receiver import data
from holo.receiver.format.identity import HW_DPI
from holo.receiver.plugins import color_sites

from . import arms as arms_mod
from . import field2 as field2_mod
from . import harmonic
from .types import (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST,
                    AnalyzerConfig, Key, RunInputs)


def rung_dict(result: Any) -> dict:
    """A RungResult as the ledger stores it, hard vector INCLUDED.

    `detail["hard_packed"]` is 512 bytes of blind decoder output (the
    exit hard vector) and it used to be stripped here, because the
    in-run oracle had already turned it into `bits_wrong_*`.  With
    scoring moved offline (2026-09-04) it is the thing the scorer needs
    and nothing else can reconstruct, so it is KEPT — base64 rather than
    the hex `ledger.jsonable` would give bytes, which is 683 characters
    instead of 1,024 per rung.
    """
    detail = {name: value for name, value in result.detail.items()
              if name != "hard_packed"}
    packed = result.detail.get("hard_packed")
    if packed is not None:
        detail["hard_packed_b64"] = base64.b64encode(bytes(packed)).decode()
    return {"rung": result.rung, "verdict": result.verdict,
            "n_iters": int(result.n_iters),
            "unsat_at_exit": int(result.unsat_at_exit),
            "syndrome_ok": bool(result.syndrome_ok),
            "posterior_summary": dict(result.posterior_summary),
            "crc_consults_distinct": int(result.crc_consults_distinct),
            "seconds": float(result.seconds), "detail": detail}


def _jsonable_knobs(knobs: Mapping[str, Any]) -> dict:
    """`ledger.jsonable` over the knob bag — a library caller may hand in
    an array; a value it cannot spell becomes its `repr`, never a crash."""
    from . import ledger as ledger_mod
    out: dict[str, Any] = {}
    for name, value in dict(knobs).items():
        try:
            out[str(name)] = ledger_mod.jsonable(value)
        except Exception:                    # pragma: no cover - defensive
            out[str(name)] = repr(value)
    return out

def _certifying_rung(work: Mapping[str, Any]) -> Any | None:
    """The `RungResult` that certified the key, or None."""
    batch = (work.get("rungs") or {}).get(work.get("certifying_rule"))
    for item in batch or ():
        if str(getattr(item, "rung", "")) != str(work.get("certifying_rung")):
            continue
        if getattr(item, "verdict", None) in (VERDICT_CERTIFIED,
                                              VERDICT_CERTIFIED_LIST):
            return item
    return None


def mint_record(key: Key, work: Mapping[str, Any], *, generation: int,
                verdict: str) -> dict:
    """One certificate as `mints.jsonl` carries it (memory wave item 2).

    ROW-SHAPED, and shaped that way for two readers.
    `export_facts.collect` reads the key, the verdict, the certifying
    rule and rung, the generation and the user bits under `rungs` — so a
    killed pass's mint file IS an input to `export-facts`, with no
    special case in that tool.  `analyzer score` reads the rung records
    under `rungs[rule]` and takes each one's packed exit hard vector out
    of its `detail` (`oracle.packed_hard`), so the CERTIFYING rung rides
    here in exactly the spelling the row gives it (`rung_dict`) and a
    mint file can be scored like the ledger it stands in for.  The other
    rungs are the row's alone: this file is about the certificate.

    `verdict` is the caller's, from the same `row_verdict` call the ROW
    makes — the mint and the row must never disagree about a key, and
    the way to guarantee that is one decision, not two.
    """
    page, ty, tx, stream_id = key
    rungs: dict[str, Any] = {
        "user_bits": np.asarray(work["user_bits"], np.uint8)}
    hit = _certifying_rung(work)
    if hit is not None:
        rungs[str(work.get("certifying_rule"))] = [rung_dict(hit)]
    return {
        "page": int(page), "ty": int(ty), "tx": int(tx),
        "stream_id": str(stream_id),
        "verdict": str(verdict),
        "certifying_rule": work.get("certifying_rule"),
        "certifying_rung": work.get("certifying_rung"),
        "certifying_arm": work.get("certifying_arm"),
        "generation": int(generation),
        "seconds": float(work.get("seconds", 0.0)),
        "rungs": rungs,
    }


# --------------------------------------------- the in-run field2 product

#: What the ladder writes beside its ledger (PAGE-FIELD-PLAN A2).
FIELD2_PRODUCT_NAME = "field2.json"

#: mm per tile on the page's x axis at c2 (64 cells x 2 dots at 600 dpi),
#: and the TWIN of `sweeps/field2_paper.MM_PER_TILE` — that sweep runs on
#: one c2 corpus and spells the 2.  A ladder does not: a c3 rung's tile is
#: 1.5x as wide, so the in-run product DERIVES the number per run
#: (:func:`_field2_mm_per_tile`) and this constant is only what the twin
#: test compares against.
FIELD2_MM_PER_TILE = 64.0 * 2.0 / HW_DPI * 25.4


def _field2_mm_per_tile(inputs: RunInputs) -> float:
    """mm per tile on the page's x axis, at THIS run's rung.

    64 cells of `cell_dots` printed dots at `HW_DPI` — the only thing
    `period_mm` needs, and the one part of the sinusoid that is not a
    pure function of the profile.
    """
    return 64.0 * color_sites.cell_dots_of(inputs.row) / HW_DPI * 25.4


def _field2_sinusoid(profile: np.ndarray, mm_per_tile: float) -> dict:
    """Least-squares amplitude and period of the best single sinusoid.

    THE TWIN of `analyzer.sweeps.field2_paper.sinusoid_fit`, and since
    the 2026-09-13 review's F7 the twinning is an IMPORT of the same
    module rather than a copy held in step by a test: `analyzer.harmonic`
    is truth-free, so the rule the copy existed to satisfy — no module a
    run command can reach may import `analyzer.truth` or
    `analyzer.oracle` (PLAN §0, pinned by
    `test_no_module_reachable_from_a_run_command_imports_truth_or_oracle`)
    — is met by importing it and not the sweep.  `mm_per_tile` is taken
    as an argument because a ladder runs on whatever rung it is given.
    """
    return harmonic.fit_sinusoid(profile,
                                 period_min_tiles=harmonic.PERIOD_MIN_TILES,
                                 period_step=harmonic.PERIOD_STEP_TILES,
                                 mm_per_tile=float(mm_per_tile))


def _field2_fit_wanted(inputs: RunInputs, config: AnalyzerConfig,
                       stream_id: str, page: int) -> dict:
    """The fit THIS pass would make for `stream_id` on `page`, in
    `PooledKey.fit`'s spelling.

    The same reading `field2.field_for` does off the knob bag a pass
    hands its arms (`fixedpoint._knobs_for`): the seed is the pass's, the
    halo is the pass's own per-stream one, and the rest are the `field2`
    knobs at their defaults.  Held against a memo key it answers the one
    question the product used to assume — is this held field a field
    THIS pass asked for, or an earlier pass's under other knobs.

    The ANCHOR SET and the LANE SET joined the comparison with
    `PooledKey.fit` (M2): both are things `fit_pooled_page_field` keys
    on, so both have to be spelled here, and the lane set is why this
    takes the page — `field2.lanes_for_page` is the default the fit
    itself would take, and `field2_lanes` is the knob that overrides it.
    """
    knobs = dict(config.knobs)
    halo = (arms_mod.HALO_CELLS[str(stream_id)] if config.halo_cells is None
            else config.halo_cells[str(stream_id)])
    lanes = knobs.get("field2_lanes")
    if lanes is None:
        lanes = field2_mod.lanes_for_page(inputs, int(page))
    return {
        "seed": int(config.seed),
        "anchors": field2_mod.ANCHORS_FURNITURE,
        "lane_ids": tuple(sorted((str(lane.lane_id[0]), int(lane.lane_id[1]))
                                 for lane in lanes)),
        "tile_sample": field2_mod.tile_sample_key(
            knobs.get("field2_pooled_tiles",
                      field2_mod.POOLED_FIT_TILES_DEFAULT)),
        "unmix_mode": str(knobs.get("field2_unmix_mode", "subtract")),
        "halo_cells": int(halo),
        "bandwidth_tiles": float(knobs.get("field2_bandwidth_tiles",
                                           field2_mod.BANDWIDTH_TILES)),
        "pool": str(knobs.get("field2_pool", field2_mod.POOL_WMEDIAN))}


def _field2_row(field: field2_mod.PageField, production: data.PlaneField | None,
                mm_per_tile: float, n_memo_entries: int,
                key: field2_mod.PooledKey, fitted_here: bool) -> dict:
    """One (page, plane) row: the pooled fit, and the fact beside it.

    `field2.summary` is the row's own producer — the same call
    `sweeps/field2_paper._pooled_entry` makes — so the two products
    spell a fit identically and `compare.py --analyzer` reads either
    unchanged.  A fit that stood on NO furniture anchor is a refusal,
    not a field of zeros, and says so under phase C's own reason string
    (`_empty_entry`): the comparator skips a refused row rather than
    scoring nan against it.

    What this row adds is the OTHER side of the pass:
    `production_field_ordinal` is the evidence revision that STOOD for
    this (page, plane) in the pass's inputs — what the `field` arms
    would have read — so a comparison says which revision of the
    production field it was against; `production_field_known` separates
    "no fact stood" from an ordinal that happens to be 0.

    `fit_seed` and `fit_knobs` are the FIT's own, off its memo key, not
    the pass header's (F12): the two agree by construction here, since
    the product publishes only fits this pass's seed and knobs match,
    and a row that carries its own provenance says so instead of
    inviting the reader to assume it.

    `fitted_here` is the half the knobs cannot answer (M2): TRUE when
    this pass's own arms filled the memo entry, FALSE when an earlier
    pass did and this one read it back.  Matching knobs made the two
    indistinguishable, so a re-run that fitted nothing published the
    first run's fields under its own header with no word about it.
    """
    entry = field2_mod.summary(field)
    if not field.tiles:
        entry["fit_refused"] = "no_furniture_anchors"
    entry["sinusoid_x"] = _field2_sinusoid(
        field2_mod.column_profile(field, axis=0), mm_per_tile)
    entry["sinusoid_y"] = _field2_sinusoid(
        field2_mod.column_profile(field, axis=1), mm_per_tile)
    entry["field_dots_xy"] = np.asarray(field.delta_dots_xy).tolist()
    entry["support"] = np.asarray(field.support).tolist()
    entry["production_field_known"] = production is not None
    entry["production_field_ordinal"] = (None if production is None
                                         else int(production.ordinal))
    entry["n_memo_entries"] = int(n_memo_entries)
    entry["fitted_here"] = bool(fitted_here)
    fit = key.fit()
    entry["fit_seed"] = fit.pop("seed")
    entry["fit_lane_ids"] = [list(lane) for lane in fit.pop("lane_ids")]
    entry["fit_knobs"] = fit
    return entry


def _field2_arms(config: AnalyzerConfig) -> list[str]:
    """The battery's `field2` arms — THE RE-ROLL'S INCLUDED (W8 B8).

    `reroll_only_arms` is where `everything+patch+pure` and
    `patch-then-pure` place `pure+field2`: it never appears in `arms`,
    it reaches `field2.field_for` all the same, and a header that read
    `arms` alone under-reported the battery and could call a pass that
    fitted nothing arm-less when it was not.
    """
    seen: list[str] = []
    for arm in (*config.arms, *getattr(config, "reroll_only_arms", ())):
        if arm.partition("+")[2] in arms_mod.FIELD2_ARMS and arm not in seen:
            seen.append(arm)
    return seen


def field2_product(inputs: RunInputs, config: AnalyzerConfig, *,
                   pass_token: Any = None) -> dict:
    """The pass's own blind cross-check, in the comparator's schema.

    One row per (page, plane) the run's `field2` arms ACTUALLY fitted —
    read back from the memo, never fitted here: a product that refits
    would be a second measurement, and an arm's field is the one the
    arm read or nothing.  A run whose battery names no `field2` arm
    therefore carries an empty `fields` list and a note saying so,
    which is the honest thing for a pass that made no such measurement.

    THE MEMO OUTLIVES THE PASS (F12, 2026-09-13).  It is process-wide and
    keyed by run dir, not by pass, so a second pass over the same inputs
    — which the sweeps do, one `fixedpoint.run` per arm — used to find
    the FIRST pass's fields there and publish them under its own seed and
    knobs, with an empty `field2_arms` beside them and no note.  Each
    held field is now held against what THIS pass's configuration would
    have fitted (`_field2_fit_wanted` against the key's own
    `PooledKey.fit`), and one that does not match is not this pass's
    measurement and is not reported.  The memo is NOT cleared: clearing
    it would trade a pass's reuse for its provenance, and the provenance
    was in the key all along.

    Where more than one fit still stands for one (page, plane) — a second
    lane set under the same knobs, which no ladder spells today — the row
    is the LAST one fitted and `n_memo_entries` says how many stood.

    AND MATCHING KNOBS ARE NOT AUTHORSHIP (M2, 2026-09-13).  Two passes
    over one run dir with the same knobs ask the memo for the same key,
    so the second one's held field matched `_field2_fit_wanted` exactly
    — and if its own `field2` arm reached no target, it published the
    FIRST pass's measurement under its own header, with a populated
    `field2_arms` and `note: null`, and nothing in the file said which
    pass had measured anything.  Every row now carries `fitted_here`
    off the memo entry's `pass_token`, and the note fires when NO row
    was fitted here whatever the battery names.  `pass_token=None` (a
    library caller, a test) matches the unstamped entries such a caller
    leaves, which is the honest reading of "no pass fitted this".
    """
    fitted = field2_mod.fitted_pooled_fields(inputs)
    mm_per_tile = _field2_mm_per_tile(inputs)
    rows = []
    for where in sorted(fitted):
        page = where[0]
        mine = [held for held in fitted[where]
                if held.key.fit() == _field2_fit_wanted(
                    inputs, config, held.field.stream_id, page)]
        if not mine:
            continue
        held = mine[-1]
        rows.append(_field2_row(held.field, inputs.plane_fields.get(where),
                                mm_per_tile, len(mine), held.key,
                                held.pass_token == pass_token))
    product: dict[str, Any] = {
        "seed": int(config.seed),
        "workers": int(config.workers),
        "knobs": _jsonable_knobs(config.knobs),
        "run_dir": str(inputs.run_dir),
        "format_ref": inputs.format_ref,
        "anchors": field2_mod.ANCHORS_FURNITURE,
        "field2_arms": _field2_arms(config),
        "mm_per_tile": float(mm_per_tile),
        "tiles_yx": [int(inputs.tiles_yx[0]), int(inputs.tiles_yx[1])],
        "fields": rows,
    }
    if not product["fields"]:
        product["note"] = (
            "the pass fitted no pooled field2 field; `field2_arms` names "
            "the arms of its battery — the re-roll's included — that "
            "would have")
    elif not any(row["fitted_here"] for row in product["fields"]):
        product["note"] = (
            "no row here was fitted by THIS pass: every one came from "
            "the process memo, under this pass's own seed and knobs, so "
            "an EARLIER pass over the same inputs fitted it and this one "
            "read it back (`fitted_here` is false on each)")
    return product


def write_field2_product(inputs: RunInputs, config: AnalyzerConfig,
                         path: Path | str, *,
                         pass_token: Any = None) -> dict:
    """Write :func:`field2_product` to `path`, and return what was written.

    Through `ledger.jsonable`, the way the sweep's writer goes: a NaN
    column (a plane the fit reached on no tile of it) becomes `null`
    rather than a token no JSON reader parses.  `indent=1` is
    `phase-C.json`'s spelling, and the grids dominate the file either
    way.
    """
    from . import ledger as ledger_mod
    product = ledger_mod.jsonable(
        field2_product(inputs, config, pass_token=pass_token))
    Path(path).write_text(json.dumps(product, indent=1), "utf-8")
    return product
