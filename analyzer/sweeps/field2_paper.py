"""`field2` on paper: sheet H's Y and C page fields, and what they buy.

DESIGN §13's field2 lead, measured. Blind throughout — the fit sees
labels only; truth appears in the ORACLE columns read back afterwards
(`R`, cell error) and in the certificate gate's own adjudication.

Phases:
  A  fit the Y and C page fields on three lanes (two 2400, one 4800),
     a deterministic tile subsample; report cost, the Y x-delta as a
     function of page x (amplitude and period of the blind sinusoid),
     agreement with the H7-pass2 ledger's per-tile offset winners on
     residue tiles, and the C field against production's published
     PlaneField for the same lane, rotated to the page frame.
  B  40 residue Y tiles (dead + marginal) and 20 residue C tiles:
     `subtract+offset` vs `subtract+field2c` vs `subtract+field2c+offset`,
     held-out select-fold loss, R, and the L0/L1/L2 ladder per arm.
     (Those two arms were spelled `field2`/`field2+offset` when §2.5 was
     measured; the names moved to the pooled form under the late ruling
     and the objects they name here are the ones §2.5 measured.)
  C  THE POOLED FURNITURE FIELD (ruling, 2026-09-03 late): one fit per
     (page, plane) over EVERY lane of the page, labels from word and
     dust only.  Cost, the blind Y sinusoid, the per-tile lane count,
     agreement with each single-lane certificate-anchored field of phase
     A, with production's published C PlaneField rotated to the page
     frame, and `wmedian` against `wmean` on the SAME reads.
  D  the same 60 targets as B: `subtract+offset` vs
     `subtract+field2+offset` (pooled furniture) vs
     `subtract+field2c+offset` (per-lane, certificate-anchored).

Run:
    PYTHONPATH=. env/bin/python -m analyzer.sweeps.field2_paper --phase A

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

from holo3.lib import plane_field as plane_field_lib

from analyzer import arms as arms_mod
from analyzer import controls as ctl
from analyzer import field2 as field2_mod
from analyzer import fixedpoint as fp
from analyzer import inputs as inputs_mod
from analyzer import residue as residue_mod
from analyzer import sample as sample_mod
from analyzer import truth as truth_mod
from analyzer.types import (AnalyzerConfig, VERDICT_CERTIFIED,
                            VERDICT_CERTIFIED_LIST, VERDICT_FALSE_ACCEPT,
                            VERDICT_WRONG)

from .c_parity_gap import GT_DIR, PAYLOAD, RUN_DIR, jsonable

OUT = Path("scratch/analyzer/sweeps/field2")
LEDGER_PASS2 = Path("scratch/analyzer/H7-pass2/ledger.jsonl")
SEED = 20260903
WORKERS = 4                 # another decode is running (memory doctrine)
FIT_TILES = 300
#: Phase C's per-lane tile sample.  22 lanes on sheet H, so the pooled
#: fit reads 22 x this many tiles per stream; 250 covers the page at
#: bandwidth 2 with room to spare and costs a few minutes at 4 threads.
POOLED_TILES = 250
ARMS = ("subtract+offset", "subtract+field2c", "subtract+field2c+offset")
#: Phase D: the ruling's comparison — the default, the POOLED FURNITURE
#: field as the search's centre, and the per-lane certificate-anchored
#: field as the search's centre.
ARMS_D = ("subtract+offset", "subtract+field2+offset",
          "subtract+field2c+offset")
#: mm per tile on the page's x axis (64 cells x 2 dots at 600 dpi).
MM_PER_TILE = 64.0 * 2.0 / 600.0 * 25.4


def load() -> tuple[Any, Any, list]:
    run = inputs_mod.load_run(RUN_DIR)
    truth = truth_mod.load_truth(GT_DIR, PAYLOAD, run.row,
                                 max(run.live_pages) + 1,
                                 format_ref=run.format_ref)
    rows = residue_mod.census(run, events=None, check_rank=False)
    return run, truth, rows


def write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
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


def chosen_lanes(run: Any) -> list[Any]:
    """Two 2400 lanes and one 4800 lane, by the modal rule, dpi-ordered."""
    modal = modal_lanes(run)
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

def sinusoid_fit(profile: np.ndarray) -> dict:
    """Least-squares amplitude and period of the best single sinusoid.

    A grid over period (in tiles) with a linear solve for the phase and
    amplitude at each — the profile is 37 points, so this is exact
    enough and needs no optimiser.  A linear trend is projected out
    first: a page-wide tilt is the SURFACE's business, not a sinusoid.
    """
    values = np.asarray(profile, np.float64)
    live = np.isfinite(values)
    if int(np.count_nonzero(live)) < 8:
        return {"amplitude_dots": None, "period_tiles": None,
                "period_mm": None, "r_squared": None}
    x = np.flatnonzero(live).astype(np.float64)
    y = values[live]
    trend = np.polynomial.polynomial.Polynomial.fit(x, y, 1)
    y = y - trend(x)
    total = float(np.sum(y ** 2))
    best = {"amplitude_dots": None, "period_tiles": None, "period_mm": None,
            "r_squared": 0.0}
    for period in np.arange(4.0, float(values.size) + 0.01, 0.25):
        design = np.column_stack((np.cos(2 * np.pi * x / period),
                                  np.sin(2 * np.pi * x / period)))
        solution, *_ = np.linalg.lstsq(design, y, rcond=None)
        residual = float(np.sum((y - design @ solution) ** 2))
        r_squared = 1.0 - residual / total if total > 0 else 0.0
        if r_squared > best["r_squared"]:
            best = {"amplitude_dots": float(np.hypot(*solution)),
                    "period_tiles": float(period),
                    "period_mm": float(period * MM_PER_TILE),
                    "r_squared": float(r_squared)}
    best["trend_dots_per_page"] = float(trend(x[-1]) - trend(x[0]))
    best["profile"] = [None if not np.isfinite(v) else float(v)
                       for v in values]
    return best


# -------------------------------------- the pass-2 ledger's own offsets

def pass2_offsets(path: Path = LEDGER_PASS2) -> dict:
    """(key, lane) -> offset the `subtract+offset` arm won in pass 2.

    Read straight off the ledger rows; the evidence key is
    ``"<capture12>/l<level>|<arm>"`` (`fixedpoint.run`'s own spelling).
    """
    out: dict[tuple, dict[str, list]] = {}
    if not path.exists():
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


# --------------------------------------------------------------- phase A

def phase_a(run: Any, truth: Any, rows: list, n_tiles: int = FIT_TILES,
            ) -> dict:
    lanes = chosen_lanes(run)
    print("lanes:", [(lane.capture_id[:12], lane.level_index, lane.dpi)
                     for lane in lanes], flush=True)
    census = {row.key: row for row in rows}
    residue = {key for key, row in census.items()
               if not row.certified_by_production}
    ledger_offsets = pass2_offsets()
    result: dict[str, Any] = {"lanes": [], "fields": [], "seed": SEED,
                              "n_tiles_fitted": int(n_tiles)}
    for lane in lanes:
        result["lanes"].append({"capture": lane.capture_id[:12],
                                "level": int(lane.level_index),
                                "dpi": float(lane.dpi),
                                "ppc": str(lane.ppc)})
    for lane in lanes:
        for stream in ("Y", "C"):
            started = time.perf_counter()
            field = field2_mod.fit_page_field(
                run, run.certificates, lane, stream, tiles=n_tiles,
                seed=SEED, memoise=False)
            seconds = time.perf_counter() - started
            entry = field2_mod.summary(field)
            entry["seconds"] = seconds
            covered = len(field2_mod.covered_tiles(run, lane, 0))
            entry["n_tiles_covered"] = covered
            entry["seconds_per_tile"] = seconds / max(len(field.tiles), 1)
            entry["full_page_seconds_estimate"] = (
                entry["seconds_per_tile"] * covered)
            entry["sinusoid_x"] = sinusoid_fit(
                field2_mod.column_profile(field, axis=0))
            entry["sinusoid_y"] = sinusoid_fit(
                field2_mod.column_profile(field, axis=1))
            entry["surface_only_sinusoid_x"] = sinusoid_fit(
                _column_profile_of(field.poly_dots_xy, field.support, 0))
            entry.update(_versus_ledger(field, ledger_offsets, residue,
                                        lane, stream))
            entry.update(_versus_production(run, field, lane, stream))
            entry["per_tile"] = [
                {"ty": item.ty, "tx": item.tx,
                 "offset": list(item.offset_dots_xy),
                 "n_labels": item.n_labels, "gain": item.gain,
                 "curvature": item.curvature, "weight": item.weight,
                 "refusal": item.refusal} for item in field.tiles]
            entry["field_dots_xy"] = field.delta_dots_xy.tolist()
            entry["support"] = field.support.tolist()
            result["fields"].append(entry)
            print(f"{lane.capture_id[:12]}/l{lane.level_index} {stream}: "
                  f"{seconds:.0f}s median {field.median_delta_dots:.3f}d "
                  f"deg {field.degree} "
                  f"sin {entry['sinusoid_x']['amplitude_dots']} @ "
                  f"{entry['sinusoid_x']['period_mm']}mm "
                  f"r2 {entry['sinusoid_x']['r_squared']}", flush=True)
    return result


def _column_profile_of(delta: np.ndarray, support: np.ndarray, axis: int):
    values = np.asarray(delta, np.float64)[..., int(axis)]
    weight = np.asarray(support, np.float64)
    mass = weight.sum(axis=0)
    out = np.full(values.shape[1], np.nan, np.float64)
    live = mass > 0.0
    out[live] = (values * weight).sum(axis=0)[live] / mass[live]
    return out


def _versus_ledger(field, ledger_offsets: dict, residue: set, lane,
                   stream: str) -> dict:
    """Median |field − pass-2 offset winner| on RESIDUE tiles, per axis."""
    name = f"{lane.capture_id[:12]}/l{int(lane.level_index)}"
    deltas = []
    for key, by_lane in ledger_offsets.items():
        if len(key) != 4 or str(key[3]) != stream or tuple(key) not in residue:
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


def _versus_production(run: Any, field, lane, stream: str) -> dict:
    """The published PlaneField for this (lane, plane), page frame.

    Production's delta is WINDOW-LOCAL (DESIGN §4.4); the rotation is the
    contributing placement's `rot_k`, so the comparison is made per TILE
    through the placement that owns the tile's centre.
    """
    plane = {"C": 0, "M": 1, "Y": 2}[stream]
    published = run.plane_fields.get(
        (str(lane.capture_id), int(lane.level_index), int(field.page),
         plane))
    if published is None:
        return {"vs_production": "no published field for this lane/plane"}
    theirs = np.asarray(published.delta_dots_xy, np.float64)
    support = np.asarray(published.support, np.float64)
    rot = _tile_rot_k(run, lane, field)
    deltas = []
    for (ty, tx), rot_k in rot.items():
        if not support[ty, tx] > 0.0 or not field.support_at_tile(ty, tx) > 0:
            continue
        page_frame = arms_mod.to_page_frame(theirs[ty, tx], int(rot_k))
        deltas.append(np.asarray(page_frame, np.float64)
                      - field.delta_at_tile(ty, tx))
    if not deltas:
        return {"vs_production": "no tile has both fields"}
    array = np.asarray(deltas, np.float64)
    return {
        "vs_production_n": int(array.shape[0]),
        "vs_production_median_abs_x": float(np.median(np.abs(array[:, 0]))),
        "vs_production_median_abs_y": float(np.median(np.abs(array[:, 1]))),
        "vs_production_median_signed_x": float(np.median(array[:, 0])),
        "vs_production_median_signed_y": float(np.median(array[:, 1])),
        "vs_production_median_delta_dots": float(
            plane_field_lib.median_magnitude_dots(theirs, support)),
        "vs_production_rot_k": sorted({int(k) for k in rot.values()}),
    }


def _tile_rot_k(run: Any, lane, field) -> dict:
    """(ty, tx) -> rot_k of the placement owning that tile's centre."""
    out: dict[tuple[int, int], int] = {}
    height, width = run.tiles_yx
    bounds = sample_mod._placement_bounds(lane, run.cells_yx)
    for ty in range(height):
        for tx in range(width):
            cy, cx = ty * 64 + 32, tx * 64 + 32
            for index, box in enumerate(bounds):
                if int(box[3]) < 0 or int(box[0]) != int(field.page):
                    continue
                if (int(box[1]) <= cy <= int(box[3])
                        and int(box[2]) <= cx <= int(box[4])):
                    out[(ty, tx)] = int(lane.placements[index].rot_k)
                    break
    return out


# --------------------------------------------------------------- phase B

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


def fields_from_phase_a(run: Any, lanes) -> dict:
    """Rebuild phase A's `PageField`s from its own JSON.

    The fit is a pure function of (lane, certificates, tile sample), and
    none of those depend on which OTHER lanes the `RunInputs` carries —
    so phase A's fields are phase B's, and B need not pay for them twice.
    Only the grids are needed here; the per-tile records are reporting.
    """
    path = OUT / "phase-A.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text("utf-8"))
    by_capture = {lane.capture_id[:12]: lane for lane in lanes}
    out: dict[tuple, Any] = {}
    for entry in data.get("fields", ()):
        capture, level = entry["lane"][0], int(entry["lane"][1])
        lane = by_capture.get(capture)
        if lane is None or int(lane.level_index) != level:
            continue
        delta = np.asarray(entry["field_dots_xy"], np.float64)
        support = np.asarray(entry["support"], np.float64)
        out[(lane.lane_id, entry["stream"])] = field2_mod.PageField(
            lane=lane.lane_id, stream_id=entry["stream"],
            page=int(entry["page"]),
            plane={"C": 0, "M": 1, "Y": 2}[entry["stream"]],
            delta_dots_xy=delta, support=support, poly_dots_xy=delta,
            degree=int(entry["degree"]), tiles=(),
            median_delta_dots=float(entry["median_delta_dots"]),
            residual_rms_dots=float(entry["residual_rms_dots"]),
            detail={"rebuilt_from": str(path)})
    return out


def phase_b(run: Any, truth: Any, rows: list, n_y: int = 40, n_c: int = 20,
            n_tiles: int = FIT_TILES) -> dict:
    lanes = chosen_lanes(run)
    small = lanes_only(run, lanes)
    targets = (residue_sample(rows, "Y", n_y)
               + residue_sample(rows, "C", n_c))
    print(f"targets Y {n_y} C {n_c}; lanes "
          f"{[(l.capture_id[:12], l.level_index) for l in lanes]}",
          flush=True)

    table: dict[tuple, Any] = fields_from_phase_a(small, lanes)
    print(f"reused {len(table)} fields from phase A", flush=True)
    for lane in lanes:
        for stream in ("Y", "C"):
            if (lane.lane_id, stream) in table:
                continue
            started = time.perf_counter()
            table[(lane.lane_id, stream)] = field2_mod.fit_page_field(
                small, small.certificates, lane, stream, tiles=n_tiles,
                seed=SEED, memoise=False)
            print(f"fitted {lane.capture_id[:12]}/l{lane.level_index} "
                  f"{stream} in {time.perf_counter() - started:.0f}s",
                  flush=True)

    out: dict[str, Any] = {"arms": list(ARMS), "n_targets": len(targets),
                           "lanes": [(l.capture_id[:12], l.level_index)
                                     for l in lanes],
                           "by_arm": {}, "rows": {}}
    for arm in ARMS:
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

def phase_c(run: Any, truth: Any, rows: list, n_tiles: int = POOLED_TILES,
            workers: int = WORKERS) -> dict:
    """ONE furniture-anchored field per (page, plane), over every lane."""
    lanes = field2_mod.lanes_for_page(run, 0)
    record_lanes = chosen_lanes(run)
    census = {row.key: row for row in rows}
    residue = {key for key, row in census.items()
               if not row.certified_by_production}
    ledger_offsets = pass2_offsets()
    per_lane_fields = fields_from_phase_a(run, record_lanes)
    print(f"pooling {len(lanes)} lanes x {n_tiles} tiles, workers {workers}; "
          f"{len(per_lane_fields)} phase-A fields to compare against",
          flush=True)
    result: dict[str, Any] = {
        "seed": SEED, "n_tiles_per_lane": int(n_tiles),
        "anchors": field2_mod.ANCHORS_FURNITURE, "workers": int(workers),
        "lanes": [{"capture": lane.capture_id[:12],
                   "level": int(lane.level_index), "dpi": float(lane.dpi),
                   "ppc": str(lane.ppc)} for lane in lanes],
        "fields": []}
    for stream in ("Y", "C"):
        plane = {"C": 0, "M": 1, "Y": 2}[stream]
        halo = arms_mod.HALO_CELLS[stream]
        started = time.perf_counter()
        by_tile = field2_mod.pooled_records(
            run, field2_mod.NO_CERTS, lanes, stream, 0, int(n_tiles), SEED,
            halo, "subtract", workers=int(workers))
        read_seconds = time.perf_counter() - started
        fields = {}
        for mode in (field2_mod.POOL_WMEDIAN, field2_mod.POOL_WMEAN):
            fields[mode] = field2_mod.field_from_pooled(
                by_tile, run, [lane.lane_id for lane in lanes], stream,
                plane, 0, field2_mod.ANCHORS_FURNITURE, SEED, halo,
                "subtract", pool=mode)
        field = fields[field2_mod.POOL_WMEDIAN]
        entry = field2_mod.summary(field)
        entry["read_seconds"] = read_seconds
        entry["total_seconds"] = time.perf_counter() - started
        entry["seconds_per_lane_tile"] = read_seconds / max(
            sum(len(items) for items in by_tile.values()), 1)
        entry["sinusoid_x"] = sinusoid_fit(
            field2_mod.column_profile(field, axis=0))
        entry["sinusoid_y"] = sinusoid_fit(
            field2_mod.column_profile(field, axis=1))
        entry["surface_only_sinusoid_x"] = sinusoid_fit(
            _column_profile_of(field.poly_dots_xy, field.support, 0))
        entry["n_lanes_per_tile"] = {
            "median": float(np.median([item.n_lanes
                                       for item in field.tiles])),
            "min": int(min(item.n_lanes for item in field.tiles)),
            "max": int(max(item.n_lanes for item in field.tiles))}
        entry["pool_wmedian_vs_wmean"] = _grid_delta(
            field, fields[field2_mod.POOL_WMEAN])
        entry["vs_per_lane_fields"] = {
            f"{lane_id[0][:12]}/l{lane_id[1]}": _grid_delta(field, other)
            for (lane_id, other_stream), other in per_lane_fields.items()
            if other_stream == stream}
        entry["vs_production"] = {}
        entry["vs_pass2"] = {}
        for lane in record_lanes:
            name = f"{lane.capture_id[:12]}/l{int(lane.level_index)}"
            entry["vs_production"][name] = _versus_production(
                run, field, lane, stream)
            entry["vs_pass2"][name] = _versus_ledger(
                field, ledger_offsets, residue, lane, stream)
        entry["per_tile"] = [
            {"ty": item.ty, "tx": item.tx,
             "offset": list(item.offset_dots_xy), "n_labels": item.n_labels,
             "n_lanes": item.n_lanes, "curvature": item.curvature,
             "weight": item.weight} for item in field.tiles]
        entry["field_dots_xy"] = field.delta_dots_xy.tolist()
        entry["support"] = field.support.tolist()
        result["fields"].append(entry)
        print(f"pooled {stream}: {read_seconds:.0f}s read "
              f"({entry['seconds_per_lane_tile']:.2f}s/lane-tile) "
              f"median {field.median_delta_dots:.3f}d deg {field.degree} "
              f"sin {entry['sinusoid_x']['amplitude_dots']} @ "
              f"{entry['sinusoid_x']['period_mm']}mm "
              f"r2 {entry['sinusoid_x']['r_squared']}", flush=True)
    return result


def _grid_delta(field: Any, other: Any) -> dict:
    """Median |difference| between two fields, over commonly supported."""
    mine = np.asarray(field.delta_dots_xy, np.float64)
    theirs = np.asarray(other.delta_dots_xy, np.float64)
    live = (np.asarray(field.support, np.float64) > 0.0) \
        & (np.asarray(other.support, np.float64) > 0.0)
    if not np.any(live):
        return {"n": 0}
    difference = (mine - theirs)[live]
    return {"n": int(np.count_nonzero(live)),
            "median_abs_x": float(np.median(np.abs(difference[:, 0]))),
            "median_abs_y": float(np.median(np.abs(difference[:, 1]))),
            "median_signed_x": float(np.median(difference[:, 0])),
            "p90_abs_x": float(np.quantile(np.abs(difference[:, 0]), 0.9)),
            "other_median_delta_dots": float(other.median_delta_dots)}


def pooled_fields_from_phase_c(run: Any) -> dict:
    """Phase C's pooled fields, rebuilt from its own JSON, keyed (page, s).

    Page-scope by construction (`lane=None`), so every lane of the page
    reads them — which is the ruling this phase exists to measure.
    """
    path = OUT / "phase-C.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text("utf-8"))
    lane_ids = tuple((str(entry["capture"]), int(entry["level"]))
                     for entry in data.get("lanes", ()))
    out: dict[tuple, Any] = {}
    for entry in data.get("fields", ()):
        delta = np.asarray(entry["field_dots_xy"], np.float64)
        support = np.asarray(entry["support"], np.float64)
        out[(int(entry["page"]), entry["stream"])] = field2_mod.PageField(
            lane=None, stream_id=entry["stream"], page=int(entry["page"]),
            plane={"C": 0, "M": 1, "Y": 2}[entry["stream"]],
            delta_dots_xy=delta, support=support, poly_dots_xy=delta,
            degree=int(entry["degree"]), tiles=(),
            median_delta_dots=float(entry["median_delta_dots"]),
            residual_rms_dots=float(entry["residual_rms_dots"]),
            lanes=lane_ids, anchors=str(entry["anchors"]),
            detail={"rebuilt_from": str(path)})
    return out


# ------------------------------ phase D: what the pooled field buys

def phase_d(run: Any, truth: Any, rows: list, n_y: int = 40, n_c: int = 20,
            n_tiles: int = FIT_TILES) -> dict:
    lanes = chosen_lanes(run)
    small = lanes_only(run, lanes)
    targets = (residue_sample(rows, "Y", n_y)
               + residue_sample(rows, "C", n_c))
    table: dict[tuple, Any] = dict(fields_from_phase_a(small, lanes))
    pooled = pooled_fields_from_phase_c(small)
    if not pooled:
        raise SystemExit("phase D needs phase C's fields; run --phase C")
    table.update(pooled)
    print(f"targets Y {n_y} C {n_c}; {len(table)} fields "
          f"({len(pooled)} pooled) on lanes "
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
    parser.add_argument("--phase", choices=("A", "B", "C", "D"),
                        required=True)
    parser.add_argument("--fit-tiles", type=int, default=FIT_TILES)
    parser.add_argument("--pooled-tiles", type=int, default=POOLED_TILES)
    parser.add_argument("--workers", type=int, default=WORKERS)
    parser.add_argument("--n-y", type=int, default=40)
    parser.add_argument("--n-c", type=int, default=20)
    args = parser.parse_args()
    started = time.perf_counter()
    run, truth, rows = load()
    print(f"loaded in {time.perf_counter() - started:.0f}s", flush=True)
    if args.phase == "A":
        write("phase-A.json", phase_a(run, truth, rows, args.fit_tiles))
    elif args.phase == "B":
        write("phase-B.json", phase_b(run, truth, rows, args.n_y, args.n_c,
                                      args.fit_tiles))
    elif args.phase == "C":
        write("phase-C.json", phase_c(run, truth, rows, args.pooled_tiles,
                                      args.workers))
    else:
        write("phase-D.json", phase_d(run, truth, rows, args.n_y, args.n_c,
                                      args.fit_tiles))
    print(f"total {time.perf_counter() - started:.0f}s", flush=True)


if __name__ == "__main__":
    main()
