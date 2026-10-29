"""Page-scope vs per-footprint context offsets on sheet H's C plane.

Production fits its 9-bin context correction once per REGION over every
window of a lane-page (`src/holo/receiver/plugins/color_region_ctx.py`); the analyzer
fits it per FOOTPRINT (`analyzer.calibrate._apply_context`).  This
measures the difference: one pooled fit per (lane, page) over the
labelled cells of many tiles, evaluated on each tile's SELECT fold —
the fold neither fit ever sees — and applied to the missed keys' cargo.

Run:
    PYTHONPATH=src:. env/bin/python -m analyzer.sweeps.c_ctx_scope \
        --run-dir RUN --gt-dir GEN --payload PAYLOAD \
        --phase-a OUT/phase-A.json --out OUT

Historical record (sheet H, 2026-09-03; the inputs are
`c_parity_gap`'s, in the evidence archive; `--phase-a` is that sweep's
phase-A output).

2026-09-04 NOTE.  This sweep is the RECORD of a finished measurement.
The ruling that took ground truth out of the run moved the metadata bit
to `analyzer.inputs` (it was blind all along) and emptied the oracle
columns a ledger row used to carry; the call sites below follow the
move.  Re-measuring anything oracle-shaped now means `analyzer score
--ledger … --payload … --run-dir …` beside the pass, not a truth
argument to the driver.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from holo.receiver.lib import pava
from holo.receiver.plugins.calibrate import (apply_context_offsets, context_decision,
                                     site_weights)
from holo.receiver.plugins import color_sites

from analyzer import arms as arms_mod
from analyzer import calibrate as cal
from analyzer import combine as combine_mod
from analyzer import controls as ctl
from analyzer import fixedpoint as fp
from analyzer import frame as frame_mod
from analyzer import inputs as inputs_mod
from analyzer import ladder as ladder_mod
from analyzer import sample as sample_mod
from analyzer.types import Evidence, VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST

from .c_parity_gap import SEED, load, write

HALO = 16
N_POOL_TILES = 120
WORKERS = 6


def harvest(run, certs, key, lane) -> dict | None:
    """One (tile, lane) row of the pool: pre-context LLR, bins, labels."""
    page, ty, tx, stream_id = key
    plane = 0
    footprint = frame_mod.tile_footprint(run.row, page, ty, tx, HALO,
                                         geometry=run.geometry)
    folds = cal.split_folds(footprint.page_cells_yx, SEED)
    lfp = sample_mod.lane_footprint(lane, footprint)
    if lfp is None or not np.any(lfp.observed):
        return None
    cell_dots = color_sites.cell_dots_of(run.row)
    bound = max(abs(arms_mod.OFFSET_X_MIN), abs(arms_mod.OFFSET_X_MAX),
                float(cell_dots)) + 0.5
    try:
        crops = sample_mod.open_crops(lane, lfp, bound_dots=bound,
                                      cell_dots=cell_dots)
    except sample_mod.SampleError:
        return None
    bit = inputs_mod.metadata_bit(run, key)
    frame = frame_mod.known_frame(run, certs, footprint, key,
                                  metadata_known=bit is not None,
                                  metadata_bit=bit)
    frame = arms_mod._with_format(frame, run)
    committed = sample_mod.read_rgb(crops, lfp, arm="reference")
    mix, _scope = arms_mod.fit_mix(
        committed.values_rgb, frame, scope_ladder=("footprint",),
        lane_mix=None, cells_yx=footprint.page_cells_yx,
        usable=np.asarray(lfp.observed, bool))
    if not mix.accepted:
        return None
    read, _detail = arms_mod.register(
        "offset", lane, crops, lfp, frame, plane, "subtract", folds,
        mix=mix, cell_dots=cell_dots)
    if read.refusal is not None:
        return None
    score = arms_mod.unmix_score("subtract", plane, mix, read.values_rgb,
                                 frame, fit_mask=folds.fit)
    llr, detail = cal.calibrate(score, frame, plane, lfp, folds,
                               branches="subtract", ctx_mode="none",
                               stream_id="C")
    usable = np.asarray(lfp.observed, bool) & np.isfinite(
        np.asarray(score, np.float64))
    masks = cal.branch_masks(frame, plane, "subtract", usable)
    covered = np.zeros(llr.size, bool)
    for name, mask in masks.items():
        if detail["branches"].get(name, {}).get("accepted"):
            covered |= mask
    cells = cal.frame_cells(frame, lfp)
    bins, _n = cal._production_bins(cells, llr)
    bins = np.where(covered, bins, np.int8(-1)).astype(np.int8)
    ids = cells[:, 0] * int(run.cells_yx[1]) + cells[:, 1]
    labels = (np.asarray(frame.known[:, plane], bool) & covered
              & (bins >= 0))
    fold = np.where(folds.fit, 0, np.where(folds.search, 1, 2)).astype(np.int8)
    cargo = (np.asarray(lfp.tile.in_tile, bool)
             & np.asarray(lfp.tile.cargo, bool) & covered & (bins >= 0))
    return {
        "key": key, "lane": lane.lane_id,
        "llr": np.asarray(llr, np.float64), "bins": bins,
        "values": np.asarray(frame.bits[:, plane], bool),
        "ids": ids.astype(np.int64), "labels": labels, "fold": fold,
        "cargo": cargo, "lfp": lfp, "footprint": footprint,
        "n_labels": int(np.count_nonzero(labels)),
    }


def side(rec: dict, fold_id: int) -> tuple:
    mask = rec["labels"] & (rec["fold"] == fold_id)
    return (rec["llr"][mask], rec["bins"][mask], rec["values"][mask],
            rec["ids"][mask])


def pool(parts: list[tuple]) -> tuple:
    return (np.concatenate([p[0] for p in parts]),
            np.concatenate([p[1] for p in parts]),
            np.concatenate([p[2] for p in parts]),
            np.concatenate([p[3] for p in parts]))


def loss_of(rec: dict, offsets: np.ndarray | None, fold_id: int = 2) -> float:
    llr, bins, values, ids = side(rec, fold_id)
    if llr.size == 0:
        return float("nan")
    if offsets is not None:
        llr = apply_context_offsets(llr, bins, offsets)
    return float(pava._binary_logloss(llr, values, site_weights(ids)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--gt-dir", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--phase-a", type=Path, required=True,
                        help="c_parity_gap's phase-A.json")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    run, truth, rows = load(args.run_dir, args.gt_dir, args.payload)
    certs = dict(run.certificates)
    missed = [tuple(k) for k in json.loads(
        args.phase_a.read_text())["missed"]]
    certified_c = [row for row in rows
                   if row.certified_by_production and row.stream_id == "C"]
    pool_rows = sorted(certified_c,
                       key=lambda row: ctl._hash_rank(SEED + 1, row.key)
                       )[:N_POOL_TILES]
    keys = [row.key for row in pool_rows]
    for key in missed:
        if key not in keys:
            keys.append(key)
    jobs: list[tuple] = []
    for key in keys:
        for lane in sample_mod.lanes_for_tile(run, key[0], key[1], key[2],
                                              cover_fraction=0.9):
            jobs.append((key, lane))
    print(f"{len(keys)} tiles, {len(jobs)} (tile, lane) reads", flush=True)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool_exec:
        futures = [pool_exec.submit(harvest, run, certs, key, lane)
                   for key, lane in jobs]
        records = [f.result() for f in futures]
    records = [r for r in records if r is not None]
    print(f"harvested {len(records)} in {time.perf_counter()-started:.0f}s",
          flush=True)

    by_lane: dict[Any, list[dict]] = {}
    for rec in records:
        by_lane.setdefault(rec["lane"], []).append(rec)

    out: dict[str, Any] = {"n_pool_tiles": len(keys), "lanes": {},
                           "per_key": {}, "certify": {}}
    page_offsets: dict[tuple, dict] = {}
    for lane_id, recs in sorted(by_lane.items()):
        name = f"{lane_id[0][:12]}/l{lane_id[1]}"
        entry: dict[str, Any] = {"n_tiles": len(recs), "per_key": {}}
        # ONE fit over every tile but the evaluated one (leave-one-tile-out)
        for rec in recs:
            others = [r for r in recs if r["key"] != rec["key"]]
            if not others:
                continue
            offsets, adopted, reason, base, cand = context_decision(
                pool([side(r, 0) for r in others]),
                pool([side(r, 1) for r in others]))
            page_offsets[(lane_id, rec["key"])] = {
                "offsets": offsets, "adopted": adopted}
            fp_off, fp_adopt, fp_reason, fp_base, fp_cand = context_decision(
                side(rec, 0), side(rec, 1))
            cargo = rec["cargo"]
            b = rec["bins"][cargo]
            shift = (offsets[b] if adopted else np.zeros(b.size)) - (
                fp_off[b] if fp_adopt else np.zeros(b.size))
            base_llr = rec["llr"][cargo]
            flipped = np.count_nonzero(
                ((base_llr + (offsets[b] if adopted else 0.0)) > 0)
                != ((base_llr + (fp_off[b] if fp_adopt else 0.0)) > 0))
            entry["per_key"][str(rec["key"])] = {
                "n_labels": rec["n_labels"],
                "page_adopted": bool(adopted), "page_reason": reason,
                "page_validation_baseline": base,
                "page_validation_candidate": cand,
                "footprint_adopted": bool(fp_adopt),
                "footprint_reason": fp_reason,
                "footprint_validation_baseline": fp_base,
                "footprint_validation_candidate": fp_cand,
                "page_offsets": offsets, "footprint_offsets": fp_off,
                "select_logloss_none": loss_of(rec, None),
                "select_logloss_footprint": loss_of(
                    rec, fp_off if fp_adopt else None),
                "select_logloss_page": loss_of(
                    rec, offsets if adopted else None),
                "select_logloss_footprint_forced": loss_of(rec, fp_off),
                "select_logloss_page_forced": loss_of(rec, offsets),
                "n_cargo": int(np.count_nonzero(cargo)),
                "llr_shift_mean_abs": float(np.mean(np.abs(shift)))
                if shift.size else None,
                "llr_shift_mean": float(np.mean(shift)) if shift.size else None,
                "cargo_sign_flips": int(flipped),
            }
        out["lanes"][name] = entry
    print(f"fits done in {time.perf_counter()-started:.0f}s", flush=True)

    # Does the page-scope context certify any missed key?
    exposure = fp.shared_exposure()
    for key in missed:
        evidences = []
        for lane_id, recs in by_lane.items():
            rec = next((r for r in recs if r["key"] == key), None)
            if rec is None:
                continue
            entry = page_offsets.get((lane_id, key))
            llr = np.asarray(rec["llr"], np.float64)
            if entry is not None and entry["adopted"]:
                llr = apply_context_offsets(llr, rec["bins"],
                                            entry["offsets"])
            seq, obs = cal.to_sequential(llr, rec["lfp"], run.row,
                                         run.geometry, key)
            evidences.append(Evidence(key=key, lane=lane_id,
                                      arm="subtract+offset",
                                      llr_sequential=seq, observed=obs))
        if not evidences:
            continue
        combined = combine_mod.combine(evidences, "sum")
        results = ladder_mod.run_ladder(
            combined, run.row, key, rungs=("L0", "L1"),
            knobs={"keep_hard": True}, exposure=exposure,
            metadata_bit=inputs_mod.metadata_bit(run, key))
        hit = next((r for r in results
                    if r.verdict in (VERDICT_CERTIFIED,
                                     VERDICT_CERTIFIED_LIST)), None)
        gt = truth.user_bits.get(key)
        out["certify"][str(key)] = {
            "n_lanes": len(evidences),
            "certified": hit is not None,
            "rung": None if hit is None else hit.rung,
            "matches_gt": (None if hit is None or gt is None else
                           bool(np.array_equal(
                               np.asarray(hit.user_bits, np.uint8),
                               np.asarray(gt, np.uint8)))),
            "unsat": [int(r.unsat_at_exit) for r in results],
        }
    out["seconds"] = time.perf_counter() - started
    write("phase-D.json", out, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
