"""`field2` on paper: a page field per (page, plane), and what it buys.

DESIGN §13's field2 lead, measured. Blind throughout — the fit sees
labels only; truth appears in the ORACLE columns read back afterwards
(`R`, cell error) and in the certificate gate's own adjudication.

Phases:
  C  THE POOLED FURNITURE FIELD (ruling, 2026-09-03 late; generalised
     2026-09-12 at PAGE-FIELD-PLAN A2): ONE fit per (page, plane) over
     every lane of that page, for EVERY stream the run names and EVERY
     live page of it, labels from word and dust only.  Cost, the blind
     sinusoid, the per-tile lane count, `wmedian` against `wmean` on the
     SAME reads, and lane-to-lane agreement BY FOOTING (A4).  The product
     is `phase-C.json`, and its schema is the one
     `measure/page_field/compare.py --analyzer` reads: that harness is
     the ONLY comparator of production's field against this one, so
     nothing here scores against a published `PlaneField`.
  D  60 residue targets (40 Y dead+marginal, 20 C): `subtract+offset`
     against `subtract+field2+offset` (the pooled furniture field as the
     search's centre), held-out select-fold loss, R, and the L0/L1/L2
     ladder per arm.

Run:
    PYTHONPATH=src:. env/bin/python -m analyzer.sweeps.field2_paper \
        --phase C --run-dir RUN --gt-dir GEN --out OUT

Historical record; the 2026-09-03 products were measured on sheet H's
H7-mirror (since 2026-09-12 its converted sibling H7-mirror.page-field),
gen dir xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm, pass-2 ledger
analyzer/H7-pass2/ledger.jsonl; inputs in the evidence archive.

2026-09-12 NOTE (A2).  Phases A and B are GONE with `field2c`, the
per-lane certificate-anchored fit they measured: the page-field design
abolishes the per-lane object on both sides of the certificate door, and
`_versus_production`, which rotated a published per-lane delta into the
page frame, went with it — a published delta is page-frame at its source
now and `compare.py` is the comparator. Their measurements stand in
`FIELD2-2026-09-03.md` and in DESIGN §4.6; what this file still runs is
the pooled furniture fit and what it buys.

2026-09-04 NOTE.  This sweep is the RECORD of a finished measurement.
The ruling that took ground truth out of the run removed the oracle
columns it used to read off a ledger row (`R`, cell error, the GT
certificate check); the call sites below are kept running and the
oracle buckets simply come back EMPTY.  Re-measuring any of them now
means `analyzer score --ledger … --payload … --run-dir …` beside the
pass, not a truth argument to the driver.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace as dc_replace
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from analyzer import arms as arms_mod
from analyzer import controls as ctl
from analyzer import field2 as field2_mod
from analyzer import fixedpoint as fp
from analyzer import harmonic
from analyzer import inputs as inputs_mod
from analyzer import passfiles as passfiles_mod
from analyzer import residue as residue_mod
from analyzer import sample as sample_mod
from analyzer import truth as truth_mod
from analyzer.types import (AnalyzerConfig, PLANE_OF, VERDICT_CERTIFIED,
                            VERDICT_CERTIFIED_LIST, VERDICT_FALSE_ACCEPT,
                            VERDICT_WRONG)

from .c_parity_gap import jsonable

SEED = 20260903
WORKERS = 4                 # another decode is running (memory doctrine)
#: Phase C's per-lane tile sample.  22 lanes on sheet H, so the pooled
#: fit reads 22 x this many tiles per stream; 250 covers the page at
#: bandwidth 2 with room to spare and costs a few minutes at 4 threads.
#: A duplex run pays it per FACE.
POOLED_TILES = 250
#: Phase D: the ruling's comparison — the default against the POOLED
#: FURNITURE field as the search's centre.  The third arm was
#: `subtract+field2c+offset` and retired with `field2c` (A2).
ARMS_D = ("subtract+offset", "subtract+field2+offset")
#: mm per tile on the page's x axis at c2 (64 cells x 2 dots at 600 dpi).
#: NOT what this sweep reports any more (F11, 2026-09-13): `--run-dir`
#: and `--format` let it run on a rung whose tile is 1.5x as wide, so
#: `period_mm` is derived per run from the loaded `run.row` through the
#: in-run product's own helper — the import goes sweep -> `passfiles`
#: and never back, because `passfiles` is on the blind run path and this
#: module reads `truth`.  The constant survives as the twin test's c2
#: anchor and nothing else reads it.
MM_PER_TILE = 64.0 * 2.0 / 600.0 * 25.4


def load(run_dir: str | Path, gt_dir: str | Path,
         format_ref: str | None = None) -> tuple[Any, Any, list]:
    run = (inputs_mod.load_run(run_dir, format_ref=format_ref)
           if format_ref else inputs_mod.load_run(run_dir))
    truth = truth_mod.load_truth(gt_dir, str(Path(gt_dir) /
                                             "payload-counting.bin"),
                                 run.row, max(run.live_pages) + 1,
                                 format_ref=run.format_ref)
    rows = residue_mod.census(run, events=None, check_rank=False)
    return run, truth, rows


def write(name: str, payload: Any, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    path = out / name
    path.write_text(json.dumps(jsonable(payload), indent=1), "utf-8")
    print(f"wrote {path}", flush=True)


# ---------------------------------------------------------- the lanes

def modal_lanes(run: Any, page: int = 0) -> dict[str, Any]:
    """Per capture, the lane the analyzer's own policy picks most often.

    `finest-covering` is a per-TILE rule and a page field is per LANE, so
    the lane fitted is the one the battery will actually read on this
    page — not the finest level in the abstract.
    """
    counts: dict[Any, int] = {}
    height, width = run.tiles_yx
    for ty in range(height):
        for tx in range(width):
            for lane in sample_mod.lanes_for_tile(run, page, ty, tx):
                counts[lane.lane_id] = counts.get(lane.lane_id, 0) + 1
    best: dict[str, Any] = {}
    for lane_id, count in counts.items():
        capture = lane_id[0]
        if capture not in best or count > best[capture][1]:
            best[capture] = (lane_id, count)
    return {capture: {"lane_id": lane_id, "n_tiles": count}
            for capture, (lane_id, count) in best.items()}


def chosen_lanes(run: Any, page: int = 0) -> list[Any]:
    """Two 2400 lanes and one 4800 lane, by the modal rule, dpi-ordered.

    Per PAGE since A2: the modal rule counts tiles on one face, and on a
    duplex sheet the two faces are two different printed pages with two
    different lane sets.
    """
    modal = modal_lanes(run, int(page))
    by_dpi: dict[float, list] = {}
    for capture, entry in modal.items():
        lane = run.lane(entry["lane_id"])
        by_dpi.setdefault(float(lane.dpi), []).append((capture, lane))
    out = []
    for lane_dpi, want in ((2400.0, 2), (4800.0, 1)):
        pool = sorted(by_dpi.get(lane_dpi, ()), key=lambda item: item[0])
        out.extend(lane for _capture, lane in pool[:want])
    return out


def lanes_only(run: Any, lanes) -> Any:
    keep = {lane.lane_id for lane in lanes}
    cache = {k: v for k, v in run._cache.items()
             if k not in ("page_tile_coverage",)}
    return dc_replace(run,
                      lanes=tuple(lane for lane in run.lanes
                                  if lane.lane_id in keep),
                      _cache=cache)


# ------------------------------------------------------- the sinusoid

def sinusoid_fit(profile: np.ndarray, mm_per_tile: float) -> dict:
    """Least-squares amplitude and period of the best single sinusoid.

    `analyzer.harmonic` at the analyzer's own period grid — the
    arithmetic used to live here in a copy kept in step with
    `passfiles._field2_sinusoid` by a twin test, and since the 2026-09-13
    review's F7 there is one of it (a joint `[1, x, cos, sin]` fit; that
    module's header is the reasoning).  `mm_per_tile` is the caller's,
    from the run it loaded (`mm_per_tile_of`).
    """
    return harmonic.fit_sinusoid(profile,
                                 period_min_tiles=harmonic.PERIOD_MIN_TILES,
                                 period_step=harmonic.PERIOD_STEP_TILES,
                                 mm_per_tile=float(mm_per_tile))


def mm_per_tile_of(run: Any) -> float:
    """mm per tile on the page's x axis, at THIS run's rung.

    The in-run product's own helper, called rather than copied: the two
    products carry the same `period_mm` to the same reader
    (`compare.py`), so the arithmetic has to be one.
    """
    return passfiles_mod._field2_mm_per_tile(run)


# -------------------------------------- the pass-2 ledger's own offsets

def pass2_offsets(path: Path | None) -> dict:
    """(key, lane) -> offset the `subtract+offset` arm won in pass 2.

    Read straight off the ledger rows; the evidence key is
    ``"<capture12>/l<level>|<arm>"`` (`fixedpoint.run`'s own spelling).
    """
    out: dict[tuple, dict[str, list]] = {}
    if path is None or not path.exists():
        return out
    for line in path.read_text("utf-8").splitlines():
        row = json.loads(line)
        if row.get("type") == "header":
            continue
        # `LedgerRow` serialises its key as four FIELDS, not a `key`
        # tuple (`ledger.py`'s own spelling).
        key = (int(row["page"]), int(row["ty"]), int(row["tx"]),
               str(row["stream_id"]))
        for name, blind in (row.get("evidence") or {}).items():
            if not isinstance(blind, dict) or "|" not in name:
                continue
            lane, _, arm = name.partition("|")
            if arm != "subtract+offset":
                continue
            offset = blind.get("offset_dots_xy")
            if offset is None:
                continue
            out.setdefault(key, {})[lane] = [float(offset[0]),
                                             float(offset[1])]
    return out


# ------------------------------------------------- shared reporting

def _column_profile_of(delta: np.ndarray, support: np.ndarray, axis: int):
    values = np.asarray(delta, np.float64)[..., int(axis)]
    weight = np.asarray(support, np.float64)
    mass = weight.sum(axis=0)
    out = np.full(values.shape[1], np.nan, np.float64)
    live = mass > 0.0
    out[live] = (values * weight).sum(axis=0)[live] / mass[live]
    return out


def _versus_ledger(field, ledger_offsets: dict, residue: set, lane,
                   stream: str, page: int = 0) -> dict:
    """Median |field − pass-2 offset winner| on RESIDUE tiles, per axis.

    The PAGE is part of the ledger key and is filtered on since A2: a
    field belongs to one printed face, and a duplex run's two faces would
    otherwise be averaged into one comparison.
    """
    name = f"{lane.capture_id[:12]}/l{int(lane.level_index)}"
    deltas = []
    for key, by_lane in ledger_offsets.items():
        if len(key) != 4 or str(key[3]) != stream or tuple(key) not in residue:
            continue
        if int(key[0]) != int(page):
            continue
        offset = by_lane.get(name)
        if offset is None:
            continue
        mine = field.delta_at_tile(int(key[1]), int(key[2]))
        if not field.support_at_tile(int(key[1]), int(key[2])) > 0.0:
            continue
        deltas.append(np.asarray(offset, np.float64) - mine)
    if not deltas:
        return {"vs_pass2_n": 0}
    array = np.asarray(deltas, np.float64)
    return {
        "vs_pass2_n": int(array.shape[0]),
        "vs_pass2_median_abs_x": float(np.median(np.abs(array[:, 0]))),
        "vs_pass2_median_abs_y": float(np.median(np.abs(array[:, 1]))),
        "vs_pass2_median_signed_x": float(np.median(array[:, 0])),
        "vs_pass2_median_signed_y": float(np.median(array[:, 1])),
        "vs_pass2_p90_abs_x": float(np.quantile(np.abs(array[:, 0]), 0.9)),
    }


# --------------------------------- phase D: targets, digests and rows

def residue_sample(rows: list, stream: str, n_total: int) -> list:
    """Hash-ordered residue rows, HALF dead and half marginal.

    Both regimes have to be in the comparison: a page field is supposed
    to help exactly where a tile's own labels cannot centre the search
    (the dead bands), and it must not hurt where they can (marginal).
    """
    pool = [row for row in rows
            if row.stream_id == stream and not row.certified_by_production
            and row.covered]
    by_band: dict[str, list] = {}
    for row in pool:
        by_band.setdefault(row.band, []).append(
            row)
    order = ("dead", "marginal", "live", "unclassified")
    ranked = {band: sorted(by_band.get(band, ()),
                           key=lambda item: ctl._hash_rank(SEED, item.key))
              for band in order}
    picked: list = []
    want = {"dead": n_total // 2, "marginal": n_total - n_total // 2}
    for band in ("dead", "marginal"):
        picked.extend(ranked[band][:want[band]])
    for band in order:                       # top up in band order
        for row in ranked[band]:
            if len(picked) >= n_total:
                break
            if row not in picked:
                picked.append(row)
    return sorted(picked[:n_total], key=lambda row: row.key)


def _digest(ledger, seconds: float) -> dict:
    verdicts: dict[str, int] = {}
    for row in ledger.rows:
        verdicts[str(row.verdict)] = verdicts.get(str(row.verdict), 0) + 1
    certified = [row for row in ledger.rows
                 if row.verdict in (VERDICT_CERTIFIED,
                                    VERDICT_CERTIFIED_LIST)]
    return {
        "seconds": float(seconds),
        "n_rows": len(ledger.rows),
        "n_certified": len(certified),
        "certified": sorted([list(row.key) for row in certified]),
        "n_wrong": sum(1 for row in ledger.rows
                       if row.verdict == VERDICT_WRONG),
        "n_false_accept": sum(1 for row in ledger.rows
                              if row.verdict == VERDICT_FALSE_ACCEPT),
        "verdicts": verdicts,
        "by_stream": _by_stream(ledger),
        "loss_and_R": _loss_and_r(ledger),
    }


def _by_stream(ledger) -> dict:
    out: dict[str, dict] = {}
    for row in ledger.rows:
        entry = out.setdefault(str(row.key[3]), {"n": 0, "certified": 0})
        entry["n"] += 1
        entry["certified"] += int(row.verdict in (VERDICT_CERTIFIED,
                                                  VERDICT_CERTIFIED_LIST))
    return out


def _loss_and_r(ledger) -> dict:
    """Median held-out select-fold loss and median R, per stream."""
    per_stream: dict[str, dict[str, list]] = {}
    for row in ledger.rows:
        bucket = per_stream.setdefault(str(row.key[3]),
                                       {"loss": [], "R": [],
                                        "applied": [], "cell_error": []})
        for name, blind in (row.evidence or {}).items():
            if name == "_selected" or not isinstance(blind, dict):
                continue
            value = blind.get("heldout_logloss_select")
            if value is not None:
                bucket["loss"].append(float(value))
            if "field2_applied" in blind:
                bucket["applied"].append(bool(blind["field2_applied"]))
        for name, scored in (row.diag or {}).get("evidence", {}).items():
            if not isinstance(scored, dict):
                continue
            if scored.get("R") is not None:
                bucket["R"].append(float(scored["R"]))
            if scored.get("cell_error_map") is not None:
                bucket["cell_error"].append(float(scored["cell_error_map"]))
    out = {}
    for stream, bucket in per_stream.items():
        out[stream] = {
            "n_lane_rows": len(bucket["loss"]),
            "median_heldout_logloss_select": (
                float(np.median(bucket["loss"])) if bucket["loss"] else None),
            "median_R": (float(np.median(bucket["R"]))
                         if bucket["R"] else None),
            "max_R": float(np.max(bucket["R"])) if bucket["R"] else None,
            "median_cell_error": (float(np.median(bucket["cell_error"]))
                                  if bucket["cell_error"] else None),
            "field2_applied_fraction": (
                float(np.mean(bucket["applied"])) if bucket["applied"]
                else None),
        }
    return out


def _row(row) -> dict:
    lanes = {}
    for name, blind in (row.evidence or {}).items():
        if name == "_selected" or not isinstance(blind, dict):
            continue
        lanes[name] = {k: jsonable(v) for k, v in blind.items()
                       if k in ("refusal", "offset_dots_xy",
                                "offset_search_logloss", "offset_grid_dots",
                                "heldout_logloss_search",
                                "heldout_logloss_select", "n_labels",
                                "n_discriminating", "field2_applied",
                                "field2_reason", "field2_median_dots_xy",
                                "field2_support", "n_observed_cargo")}
    oracle = {}
    for name, scored in (row.diag or {}).get("evidence", {}).items():
        if isinstance(scored, dict):
            oracle[name] = {k: jsonable(v) for k, v in scored.items()
                            if k in ("R", "R_upper", "cell_error_map",
                                     "d_prime", "auc", "n_observed")}
    return {"verdict": row.verdict, "band": row.band,
            "certifying_rung": row.certifying_rung,
            "lanes": lanes, "oracle": oracle,
            "rungs": {rule: [{"rung": item.get("rung"),
                              "unsat_at_exit": item.get("unsat_at_exit")}
                             for item in batch]
                      for rule, batch in (row.rungs or {}).items()
                      if rule != "user_bits"}}


# --------------------------------------------- phase C: the pooled field

def phase_c(run: Any, truth: Any, rows: list,
            n_tiles: int | None = POOLED_TILES,
            workers: int = WORKERS,
            pass2_ledger: Path | None = None) -> dict:
    """ONE furniture-anchored field per (page, plane), over every lane.

    GENERALISED 2026-09-12 (PAGE-FIELD-PLAN A2).  This phase used to fit
    page 0 and the streams `("Y", "C")`, which is neither of the things
    its own docstring claimed: no field existed for M — the plane whose
    production value is `-C` to the bit under the gauge, so the analyzer's
    independently fitted M is the only test of that gauge outside the
    receiver's suite (A5) — and none for the second face of a duplex
    sheet, where the two faces are two different printed pages. It now
    fits every stream the run NAMES (`run.row.streams`) on every LIVE
    page of it.

    The product is `phase-C.json` in the schema
    `measure/page_field/compare.py --analyzer` reads: one entry per
    (page, plane) carrying `page`, `stream`, `plane`, the whole
    `field_dots_xy` grid, `support`, and `sinusoid_x`. A (page, plane)
    the fit cannot stand on REFUSES BY NAME in its own row
    (`fit_refused`) and carries a zero grid of the right shape rather
    than raising or vanishing, so a three-plane sheet writes three rows
    per printed face whatever the paper did — sheet H three, a duplex
    sheet J six.

    The header says WHICH CORPUS (F10, 2026-09-13): `run_dir` and
    `format_ref` in the in-run product's own spelling, so phase D can
    hold the fields it loads against the run it is applying them to.
    """
    streams = [fact.stream_id for fact in run.row.streams]
    pages = [int(page) for page in run.live_pages]
    census = {row.key: row for row in rows}
    residue = {key for key, row in census.items()
               if not row.certified_by_production}
    ledger_offsets = pass2_offsets(pass2_ledger)
    mm_per_tile = mm_per_tile_of(run)
    result: dict[str, Any] = {
        "seed": SEED,
        # `field2`'s own spelling: None is EVERY covered tile, an int is
        # a deterministic subsample of that size.
        "n_tiles_per_lane": None if n_tiles is None else int(n_tiles),
        "anchors": field2_mod.ANCHORS_FURNITURE, "workers": int(workers),
        "run_dir": str(run.run_dir), "format_ref": run.format_ref,
        "mm_per_tile": float(mm_per_tile),
        "pages": pages, "streams": list(streams),
        "tiles_yx": [int(run.tiles_yx[0]), int(run.tiles_yx[1])],
        "fields": []}
    for page in pages:
        lanes = field2_mod.lanes_for_page(run, page)
        record_lanes = chosen_lanes(run, page)
        print(f"page {page}: pooling {len(lanes)} lanes x "
              f"{'every' if n_tiles is None else n_tiles} tiles "
              f"over {len(streams)} streams, workers {workers}", flush=True)
        for stream in streams:
            result["fields"].append(_pooled_entry(
                run, page, stream, lanes, record_lanes, ledger_offsets,
                residue, n_tiles, workers, mm_per_tile))
    return result


def _empty_entry(run: Any, page: int, stream: str, reason: str,
                 mm_per_tile: float | None = None) -> dict:
    """A (page, plane) the fit cannot stand on, in the product's schema.

    `compare.py` SKIPS a row that names `fit_refused` (a refusal is not
    a field and is not scored); the grids are still carried, at the
    page's own tile shape with no support anywhere — which is exactly
    what is true — so every row of the product has one shape, and the
    row says why it stands empty.

    `mm_per_tile` is the phase's, and defaults to the c2 constant only
    for a caller that has no run to derive it from: every field of this
    row is empty and its sinusoid is the all-NaN refusal, so no number
    here depends on it.
    """
    tiles_yx = (int(run.tiles_yx[0]), int(run.tiles_yx[1]))
    scale = MM_PER_TILE if mm_per_tile is None else float(mm_per_tile)
    zeros = np.zeros(tiles_yx + (2,), np.float64)
    support = np.zeros(tiles_yx, np.float64)
    return {"page": int(page), "stream": str(stream),
            "plane": int(PLANE_OF.get(str(stream), -1)),
            "fit_refused": str(reason),
            "anchors": field2_mod.ANCHORS_FURNITURE,
            "median_delta_dots": 0.0, "residual_rms_dots": 0.0, "degree": 0,
            "sinusoid_x": sinusoid_fit(np.full(tiles_yx[1], np.nan), scale),
            "sinusoid_y": sinusoid_fit(np.full(tiles_yx[1], np.nan), scale),
            "field_dots_xy": zeros.tolist(), "support": support.tolist()}


def _pooled_entry(run: Any, page: int, stream: str, lanes, record_lanes,
                  ledger_offsets: dict, residue: set, n_tiles: int | None,
                  workers: int, mm_per_tile: float) -> dict:
    """One (page, plane) row: the pooled fit, its cost and its spreads."""
    if str(stream) not in PLANE_OF:
        return _empty_entry(run, page, stream, f"unknown_stream_{stream}",
                            mm_per_tile)
    plane = PLANE_OF[str(stream)]
    if not lanes:
        return _empty_entry(run, page, stream, "no_lane_on_page", mm_per_tile)
    halo = arms_mod.HALO_CELLS[stream]
    started = time.perf_counter()
    per_lane = field2_mod.records_by_lane(
        run, field2_mod.NO_CERTS, lanes, stream, int(page), n_tiles,
        SEED, halo, "subtract", workers=int(workers))
    by_tile = field2_mod.by_tile_from(per_lane)
    read_seconds = time.perf_counter() - started
    lane_ids = [lane.lane_id for lane in lanes]
    fields = {
        mode: field2_mod.field_from_pooled(
            by_tile, run, lane_ids, stream, plane, int(page),
            field2_mod.ANCHORS_FURNITURE, SEED, halo, "subtract", pool=mode)
        for mode in (field2_mod.POOL_WMEDIAN, field2_mod.POOL_WMEAN)}
    field = fields[field2_mod.POOL_WMEDIAN]
    if not field.tiles:
        entry = _empty_entry(run, page, stream, "no_furniture_anchors",
                             mm_per_tile)
        entry["read_seconds"] = read_seconds
        entry["n_lane_tile_reads"] = int(
            sum(len(items) for items in per_lane.values()))
        return entry

    entry = field2_mod.summary(field)
    entry["read_seconds"] = read_seconds
    entry["total_seconds"] = time.perf_counter() - started
    entry["seconds_per_lane_tile"] = read_seconds / max(
        sum(len(items) for items in by_tile.values()), 1)
    entry["mm_per_tile"] = float(mm_per_tile)
    entry["sinusoid_x"] = sinusoid_fit(
        field2_mod.column_profile(field, axis=0), mm_per_tile)
    entry["sinusoid_y"] = sinusoid_fit(
        field2_mod.column_profile(field, axis=1), mm_per_tile)
    entry["surface_only_sinusoid_x"] = sinusoid_fit(
        _column_profile_of(field.poly_dots_xy, field.support, 0), mm_per_tile)
    entry["n_lanes_per_tile"] = {
        "median": float(np.median([item.n_lanes for item in field.tiles])),
        "min": int(min(item.n_lanes for item in field.tiles)),
        "max": int(max(item.n_lanes for item in field.tiles))}
    entry["pool_wmedian_vs_wmean"] = _grid_delta(
        field, fields[field2_mod.POOL_WMEAN])
    entry.update(_by_footing(run, field, per_lane, lanes, stream, plane,
                             page, halo))
    entry["vs_pass2"] = {
        f"{lane.capture_id[:12]}/l{int(lane.level_index)}": _versus_ledger(
            field, ledger_offsets, residue, lane, stream, page)
        for lane in record_lanes}
    entry["per_tile"] = [
        {"ty": item.ty, "tx": item.tx,
         "offset": list(item.offset_dots_xy), "n_labels": item.n_labels,
         "n_lanes": item.n_lanes, "curvature": item.curvature,
         "weight": item.weight} for item in field.tiles]
    entry["field_dots_xy"] = field.delta_dots_xy.tolist()
    entry["support"] = field.support.tolist()
    print(f"pooled p{page} {stream}: {read_seconds:.0f}s read "
          f"({entry['seconds_per_lane_tile']:.2f}s/lane-tile) "
          f"median {field.median_delta_dots:.3f}d deg {field.degree} "
          f"clamped {entry['clamped_tiles']} "
          f"sin {entry['sinusoid_x']['amplitude_dots']} @ "
          f"{entry['sinusoid_x']['period_mm']}mm "
          f"r2 {entry['sinusoid_x']['r_squared']}", flush=True)
    return entry


def _by_footing(run: Any, pooled: Any, per_lane, lanes, stream: str,
                plane: int, page: int, halo: int) -> dict:
    """Each lane's OWN furniture field against the pool, grouped by dpi.

    PAGE-FIELD-PLAN A4.  The receiver publishes a per-capture residual
    over its own observations, which scores its estimator against its own
    evidence and cannot answer the analyzer's lane-choice question; what
    no instrument had was the ANALYZER's spread, lane against lane and
    footing against footing.  `lane_gauge` measured the receiver's:
    same-footing 2400 pairs agree to 0.013-0.044 dots and ALL 72
    cross-footing sheet-H C pairs sit 0.968-1.058 dots apart with
    Spearman -0.996...-0.858 (design §7.2).  If the pooled furniture fit
    reproduces that inversion it is the print or the scan; if it does
    not, it was the archived per-lane fitter.

    It costs nothing: the per-lane records are the reads the pool already
    paid for, and a single-lane field is the same pure `build_field` over
    that lane's own records.
    """
    lane_by_id = {lane.lane_id: lane for lane in lanes}
    per_lane_fields: dict[Any, Any] = {}
    for lane_id, records in per_lane.items():
        if not records:
            continue
        one = field2_mod.field_from_pooled(
            field2_mod.by_tile_from({lane_id: records}), run, [lane_id],
            stream, plane, int(page), field2_mod.ANCHORS_FURNITURE, SEED,
            halo, "subtract")
        if one.tiles:
            per_lane_fields[lane_id] = one

    def name(lane_id) -> str:
        return f"{str(lane_id[0])[:12]}/l{int(lane_id[1])}"

    vs_pool = {name(lane_id): dict(
        _grid_delta(pooled, one),
        dpi=float(lane_by_id[lane_id].dpi),
        n_tiles_read=len(per_lane[lane_id]))
        for lane_id, one in per_lane_fields.items()}
    by_footing: dict[str, list] = {}
    for lane_id in per_lane_fields:
        by_footing.setdefault(f"{float(lane_by_id[lane_id].dpi):.0f}",
                              []).append(lane_id)
    pairs: dict[str, list] = {}
    ids = list(per_lane_fields)
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            left_dpi = float(lane_by_id[left].dpi)
            right_dpi = float(lane_by_id[right].dpi)
            bucket = (f"same-{left_dpi:.0f}" if left_dpi == right_dpi
                      else f"cross-{min(left_dpi, right_dpi):.0f}-"
                           f"{max(left_dpi, right_dpi):.0f}")
            pairs.setdefault(bucket, []).append(dict(
                _grid_delta(per_lane_fields[left], per_lane_fields[right]),
                lanes=[name(left), name(right)]))
    return {"vs_lane_own_fields": vs_pool,
            "lanes_by_footing": {footing: [name(one) for one in group]
                                 for footing, group in by_footing.items()},
            "lane_pairs_by_footing": pairs,
            "lane_pair_summary": {
                footing: _pair_summary(group)
                for footing, group in pairs.items()}}


def _pair_summary(group: list) -> dict:
    """One footing bucket's pairs, summarised the way `lane_gauge` reads
    them: the median of the pairs' vector medians, of their |dx|
    medians, and of the Spearman of their column profiles — the last is
    the inversion statistic (design §7.2: cross-footing pairs at
    Spearman -0.996...-0.858 while same-footing pairs agree)."""
    live = [row for row in group if row.get("n")]
    def med(key: str):
        values = [row[key] for row in live if row.get(key) is not None]
        return float(np.median(values)) if values else None
    return {"n_pairs": len(group), "median_abs_dots": med("median_abs_dots"),
            "median_abs_x": med("median_abs_x"),
            "median_spearman_x": med("spearman_x")}


def _column_profile_over(delta: np.ndarray, live: np.ndarray,
                         axis: int) -> np.ndarray:
    """Per page-x column, the mean of one component over live tiles."""
    out = np.full(delta.shape[1], np.nan)
    for column in range(delta.shape[1]):
        rows = live[:, column]
        if np.any(rows):
            out[column] = float(np.mean(delta[rows, column, axis]))
    return out


def _grid_delta(field: Any, other: Any) -> dict:
    """Two fields over commonly supported tiles, in `lane_gauge`'s terms.

    The receiver's lane gauge scores a pair by the median of the vector
    difference, the median |dx|, and the Spearman of the two x column
    profiles — the last is what tells an INVERSION (two anti-correlated
    fields) from noise, since |dx| alone reads the same for both.  The
    same three here, so a by-footing bucket of the pooled furniture fit
    is comparable to design §7.2's numbers.
    """
    mine = np.asarray(field.delta_dots_xy, np.float64)
    theirs = np.asarray(other.delta_dots_xy, np.float64)
    live = (np.asarray(field.support, np.float64) > 0.0) \
        & (np.asarray(other.support, np.float64) > 0.0)
    if not np.any(live):
        return {"n": 0}
    difference = (mine - theirs)[live]
    left = _column_profile_over(mine, live, 0)
    right = _column_profile_over(theirs, live, 0)
    both = np.isfinite(left) & np.isfinite(right)
    spearman = None
    if np.count_nonzero(both) >= 3:
        rho = stats.spearmanr(left[both], right[both]).correlation
        spearman = float(rho) if np.isfinite(rho) else None
    return {"n": int(np.count_nonzero(live)),
            "median_abs_dots": float(np.median(np.hypot(difference[:, 0],
                                                         difference[:, 1]))),
            "spearman_x": spearman,
            "median_abs_x": float(np.median(np.abs(difference[:, 0]))),
            "median_abs_y": float(np.median(np.abs(difference[:, 1]))),
            "median_signed_x": float(np.median(difference[:, 0])),
            "p90_abs_x": float(np.quantile(np.abs(difference[:, 0]), 0.9)),
            "other_median_delta_dots": float(other.median_delta_dots)}


def pooled_fields_from_phase_c(path: Path, run: Any, *,
                               allow_unlabelled: bool = False) -> dict:
    """Phase C's pooled fields, rebuilt from its own JSON, keyed (page, s).

    Page-scope by construction (`lane=None`), so every lane of the page
    reads them — which is the ruling this phase exists to measure.  Since
    A2 the file carries one row per (page, plane) for EVERY live page, so
    this table is the whole sheet; a row that refused its fit carries no
    field and is skipped by name rather than rebuilt as a zero grid, which
    an arm would read as a real "no displacement here".

    THE PATH IS THE CALLER'S AND THE RUN IS CHECKED (F10, 2026-09-13).
    This read the module-global `OUT` and took whatever stood there,
    which on a `--run-dir`/`--out` run is another corpus's product — and
    since both sheets of record are 53x37 and `evaluate` clamps rather
    than raises, sheet H's fields would have gone onto sheet J with
    nothing to say so.  A product's `run_dir`/`format_ref` header must
    now name the run the fields are about to be applied to.  The
    2026-09-03 products predate that header; `allow_unlabelled` is the
    operator's word that an unlabelled file is the one he means, and it
    exists rather than a flat refusal so that measurement can still be
    re-run without a new phase C.
    """
    path = Path(path)
    if not path.exists():
        return {}
    data = json.loads(path.read_text("utf-8"))
    labelled_run = data.get("run_dir")
    labelled_format = data.get("format_ref")
    if labelled_run is None or labelled_format is None:
        if not allow_unlabelled:
            raise SystemExit(
                f"{path} carries no run_dir/format_ref header (the "
                f"2026-09-03 products predate it), so it cannot say which "
                f"corpus its fields are of: re-run --phase C, or pass "
                f"--allow-unlabelled-phase-c to apply it anyway")
        print(f"WARNING: {path} names no corpus; applying it to "
              f"{run.run_dir} on the operator's word", flush=True)
    elif (Path(labelled_run).resolve() != Path(run.run_dir).resolve()
            or str(labelled_format) != str(run.format_ref)):
        raise SystemExit(
            f"{path} holds the fields of {labelled_run} "
            f"({labelled_format}); this run is {run.run_dir} "
            f"({run.format_ref})")
    out: dict[tuple, Any] = {}
    for entry in data.get("fields", ()):
        if entry.get("fit_refused"):
            print(f"phase C refused ({entry['fit_refused']}) for page "
                  f"{entry['page']} {entry['stream']} — no field", flush=True)
            continue
        delta = np.asarray(entry["field_dots_xy"], np.float64)
        support = np.asarray(entry["support"], np.float64)
        lane_ids = tuple((str(one[0]), int(one[1]))
                         for one in entry.get("lanes", ()))
        out[(int(entry["page"]), entry["stream"])] = field2_mod.PageField(
            lane=None, stream_id=entry["stream"], page=int(entry["page"]),
            plane=int(entry.get("plane", PLANE_OF[entry["stream"]])),
            delta_dots_xy=delta, support=support, poly_dots_xy=delta,
            degree=int(entry["degree"]), tiles=(),
            median_delta_dots=float(entry["median_delta_dots"]),
            residual_rms_dots=float(entry["residual_rms_dots"]),
            lanes=lane_ids, anchors=str(entry["anchors"]),
            detail={"rebuilt_from": str(path)})
    return out


# ------------------------------ phase D: what the pooled field buys

def phase_d(run: Any, truth: Any, rows: list, n_y: int, n_c: int,
            phase_c_path: Path, *,
            allow_unlabelled: bool = False) -> dict:
    """What the pooled furniture field buys on 60 residue targets.

    The table handed to the arms is phase C's pooled fields and nothing
    else since A2: the per-lane certificate-anchored table this used to
    merge in was `field2c`'s, and it is retired.  It comes from the
    product `main` was pointed at, not from the default directory
    (F10) — and `phase_c_path` HAS no default, because the only one
    there could be is `OUT`, which is the directory F10 took it off.
    The lanes and the
    residue sample are PAGE 0's (`chosen_lanes(run)`, `residue_sample`
    has no page filter): on a duplex run phase C carries both faces and
    this phase still measures one; a `--page` is owed with the first
    duplex ladder that wants it.
    """
    lanes = chosen_lanes(run)
    small = lanes_only(run, lanes)
    targets = (residue_sample(rows, "Y", n_y)
               + residue_sample(rows, "C", n_c))
    table: dict[tuple, Any] = pooled_fields_from_phase_c(
        phase_c_path, run, allow_unlabelled=allow_unlabelled)
    if not table:
        raise SystemExit(f"phase D needs phase C's fields; {phase_c_path} "
                         f"holds none — run --phase C")
    print(f"targets Y {n_y} C {n_c}; {len(table)} pooled fields on lanes "
          f"{[(l.capture_id[:12], l.level_index) for l in lanes]}", flush=True)

    out: dict[str, Any] = {"arms": list(ARMS_D), "n_targets": len(targets),
                           "lanes": [(l.capture_id[:12], l.level_index)
                                     for l in lanes],
                           "by_arm": {}, "rows": {}}
    for arm in ARMS_D:
        config = AnalyzerConfig(
            arms=(arm,), rules=("sum",), rungs=("L0", "L1", "L2"),
            workers=WORKERS, seed=SEED, max_generations=1, all_rules=True,
            metadata_known=True, ctx_mode="production",
            mix_scope_ladder=("footprint", "lane"), lane_mix_tiles=12,
            reroll=False, targets_from="sweep:field2_paper",
            knobs={"page_field2": table})
        started = time.perf_counter()
        ledger = fp.run(small, targets, config, census_rows=rows,
                        exposure=fp.shared_exposure())
        out["by_arm"][arm] = _digest(ledger, time.perf_counter() - started)
        for row in ledger.rows:
            out["rows"].setdefault(str(list(row.key)), {})[arm] = _row(row)
        print(f"{arm}: {out['by_arm'][arm]['n_certified']} certs, "
              f"{out['by_arm'][arm]['seconds']:.0f}s, "
              f"wrong {out['by_arm'][arm]['n_wrong']}", flush=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("C", "D"), required=True)
    parser.add_argument("--pooled-tiles", default=POOLED_TILES,
                        type=lambda s: None if s == "all" else int(s),
                        help="tiles per lane, or 'all' for every covered")
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--n-y", type=int, default=40)
    parser.add_argument("--n-c", type=int, default=20)
    parser.add_argument("--run-dir", required=True,
                        help="a post-W2 or converted run dir")
    parser.add_argument("--gt-dir", required=True,
                        help="the generation dir with payload-counting.bin")
    parser.add_argument("--pass2-ledger", type=Path, default=None,
                        help="phase C: a pass-2 ledger whose subtract+offset "
                             "offsets the field is compared against "
                             "(none: that comparison is empty)")
    parser.add_argument("--format", dest="format_ref", default=None,
                        help="the fossil identity for a re-keyed archive "
                             "(sheet J needs L:c2-cmy8-r0547@53x37)")
    parser.add_argument("--out", type=Path, required=True,
                        help="product dir; a re-run on another corpus "
                             "writes beside the 2026-09-03 products, never "
                             "over them. Phase D reads its phase C from HERE")
    parser.add_argument("--allow-unlabelled-phase-c", action="store_true",
                        dest="allow_unlabelled",
                        help="apply a phase-C product that names no "
                             "run_dir/format_ref (the 2026-09-03 ones) to "
                             "this run anyway")
    args = parser.parse_args()
    started = time.perf_counter()
    run, truth, rows = load(args.run_dir, args.gt_dir, args.format_ref)
    print(f"loaded in {time.perf_counter() - started:.0f}s", flush=True)
    if args.phase == "C":
        write("phase-C.json", phase_c(run, truth, rows, args.pooled_tiles,
                                      args.workers, args.pass2_ledger),
              out=args.out)
    else:
        write("phase-D.json",
              phase_d(run, truth, rows, args.n_y, args.n_c,
                      args.out / "phase-C.json",
                      allow_unlabelled=args.allow_unlabelled),
              out=args.out)
    print(f"total {time.perf_counter() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
