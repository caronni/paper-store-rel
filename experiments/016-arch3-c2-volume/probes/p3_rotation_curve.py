#!/usr/bin/env python
"""P3 item 1 — the rotation-loss curve (pre-registered zero-print probe).

PURPOSE: quantify piece-detection quality vs rotation angle on REAL toner
(the 016.4 session measured ~+4pp BER at random angles on placed pieces and
exonerated the fixture interpolation) and decompose the tax into
(a) angle-ESTIMATION error in the production path (segment.lattice_angle)
vs (b) intrinsic counter-rotation RESAMPLE loss — the headroom question for
rotation-free detection (016.4 next-levers list).

PRE-REGISTERED DESIGN (2026-07-10):
  - Source: scratch/e016c2hp-canon4800gray.tiff (Canon 4800 dpi grey scan
    of the e016 M281 print; run-table sha 593742f6..., verified at runtime).
  - N=12 axis-aligned 12 mm squares at seeded-random positions inside the
    printed field, avoiding the outer 10 mm rim. PAIRED: the SAME 12
    pieces at every angle in [0, 5, 15, 30, 45] deg.
  - Channel prep per (piece, angle): crop @4800, ndimage.rotate order-3
    cval=250 reshape=True, then 2x2 box-decimate to 2400 dpi (= the v2
    fixture recipe in gen_confetti_session.py). Angle 0 = NO rotate call
    (the unrotated anchor; 016.4 unrotated channel 9-10% BER).
  - Leg A (production): segment.lattice_angle on the rotated piece+mask,
    counter-rotate by the ESTIMATE (order-3), scannorm pitch +
    segment.piece_cell_bits. Records the angle-estimation error.
  - Leg B (genie angle): identical, counter-rotation by exactly -angle
    (angle 0 -> no rotate call at all) — isolates resample loss.
  - PRIMARY metric: paperholo.place.place_fragment mismatch vs a full-page
    pending set, gate_true=0.20/gate_decoy=0.20 + the >=0.08 gap rule (the
    session_decode.py gate; 016.4 baseline: rotated placed pieces median
    mismatch 0.134). Every ok-gated placement is verified against the
    known ground-truth rect (a wrong ok-gated placement = CRITICAL).
  - SECONDARY (on correctly placed pieces): detection BER vs the composed
    page cell_values (gen_e016 regeneration; paper==build dot-exact per
    016.2).

DECLARED DEVIATIONS (adaptations found necessary while building, none
changing the measurement design):
  1. field bbox: gen_confetti_session.field_bbox takes first..last
     above-threshold blocks; on THIS scan a dark strip at the extreme
     right image edge (scanner lid/edge, 3 overview columns) drags x1 to
     the image border (+17 mm past the field). Adapted to the LONGEST
     CONTIGUOUS run per axis — measured field 52832 x 35616 px = 16.01 /
     16.04 px/cell, matching the 3300x2220-cell page; the original x-bbox
     did not.
  2. piece sampling adds non-overlap rejection (statistical independence
     of the 12 pieces; not in the one-line pre-registration, conservative).
  3. ground-truth placement check: placed mask-centroid within
     GT_TOL_CELLS=10 cells of the bbox-mapped rect center (bbox edges are
     32-px quantized ~2 cells; bbox-scale mapping drift ~2-5 cells
     measured at build time — decoys sit 100s of cells away, BER ~0.5).
  4. angle-error is reported twice: RAW vs the applied rotation (the
     pre-registered "estimated vs true, mod 90") and SKEW-REFERENCED
     against the same piece's angle-0 estimate (the physical scan carries
     its own small skew, so the raw error absorbs a per-scan constant).
  5. leg A at angle 0 still estimates + counter-rotates (the production
     path always de-rotates); only leg B at angle 0 is rotate-free.

Runs from the repo root:  env/bin/python \
    experiments/016-arch3-c2-volume/probes/p3_rotation_curve.py
Output: experiments/016-arch3-c2-volume/build/p3_rotation_curve.json
Determinism: all randomness via modulation.rng(gen_e016.SEED,
b"e016/p3-rotcurve/v1"); scipy/numpy paths are deterministic.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/016-arch3-c2-volume"))

import gen_e016                                           # noqa: E402
from paperholo import fountain, place, scannorm, segment  # noqa: E402
from paperholo.compose import compose_page                # noqa: E402
from paperholo.modulation import rng                      # noqa: E402

SCAN_REL = "scratch/e016c2hp-canon4800gray.tiff"
SCAN_SHA = "593742f68ee81f4004c551c0128990ab278f41030e6ad26f10b19e8656ad96e4"
OUT_JSON = (ROOT / "experiments/016-arch3-c2-volume/build/"
            "p3_rotation_curve.json")
RNG_LABEL = b"e016/p3-rotcurve/v1"

SRC_DPI = 4800.0
MM_SRC = SRC_DPI / 25.4          # source px per mm
ANGLES_DEG = (0.0, 5.0, 15.0, 30.0, 45.0)
N_PIECES = 12
SIDE_MM = 12.0
RIM_MM = 10.0
BACKING = 250                    # white backing (the v2 fixture cval)
GATE_TRUE = 0.20                 # session_decode.py real-toner gate
GATE_DECOY = 0.20
GAP_MIN = 0.08                   # session_decode.py rival-best gap rule
GT_TOL_CELLS = 10.0              # deviation 3 (decoys are 100s of cells off)
CELL_DOTS = 2                    # kcell-c2


def field_bbox_longest_run(arr: np.ndarray) -> tuple[int, int, int, int]:
    """Printed-field bbox = the LONGEST contiguous above-threshold run per
    axis of the coarse darkness profile (deviation 1: the first..last rule
    in gen_confetti_session.field_bbox is dragged to the image border by a
    dark scanner-edge strip on this scan)."""
    ov = np.asarray(arr[::32, ::32], np.float32)
    ink = ov < 128

    def longest(prof: np.ndarray) -> tuple[int, int]:
        above = prof > 0.10
        best, s = (0, 0), None
        for i, a in enumerate(list(above) + [False]):
            if a and s is None:
                s = i
            elif not a and s is not None:
                if i - s > best[1] - best[0]:
                    best = (s, i)
                s = None
        if best == (0, 0):
            raise SystemExit("no printed field found on the scan")
        return best

    r0, r1 = longest(ink.mean(axis=1))
    c0, c1 = longest(ink.mean(axis=0))
    return r0 * 32, r1 * 32, c0 * 32, c1 * 32


def fold90(a_deg: float) -> float:
    """Fold an angle difference to [-45, 45) deg (the mod-90 metric)."""
    return float(((a_deg + 45.0) % 90.0) - 45.0)


def decimate2(a: np.ndarray) -> np.ndarray:
    """2x2 box decimate, 4800 -> 2400 dpi (the v2 fixture step)."""
    h = (a.shape[0] // 2) * 2
    w = (a.shape[1] // 2) * 2
    return a[:h, :w].reshape(h // 2, 2, w // 2, 2).mean(axis=(1, 3))


def sample_rects(gen: np.random.Generator, bbox: tuple[int, int, int, int]
                 ) -> list[tuple[int, int]]:
    """N_PIECES non-overlapping SIDE_MM squares (top-left source px),
    inside the field avoiding the outer RIM_MM rim (deviation 2)."""
    y0f, y1f, x0f, x1f = bbox
    rim = int(RIM_MM * MM_SRC)
    n = int(SIDE_MM * MM_SRC)
    ylo, yhi = y0f + rim, y1f - rim - n
    xlo, xhi = x0f + rim, x1f - rim - n
    rects: list[tuple[int, int]] = []
    tries = 0
    while len(rects) < N_PIECES:
        tries += 1
        if tries > 10_000:
            raise SystemExit("piece sampling failed (rejection exhausted)")
        y = int(ylo + gen.uniform() * (yhi - ylo))
        x = int(xlo + gen.uniform() * (xhi - xlo))
        if all(abs(y - ry) >= n or abs(x - rx) >= n for ry, rx in rects):
            rects.append((y, x))
    return rects


def prep_piece(crop: np.ndarray, angle_deg: float
               ) -> tuple[np.ndarray, np.ndarray]:
    """Channel prep at 2400 dpi: (img, mask). Angle 0 = no rotate call."""
    if angle_deg == 0.0:
        img = decimate2(crop)
        return img, np.ones(img.shape, bool)
    rot = ndimage.rotate(crop, angle_deg, reshape=True, order=3,
                         cval=BACKING, mode="constant")
    mrot = ndimage.rotate(np.ones(crop.shape, np.uint8), angle_deg,
                          reshape=True, order=0, cval=0, mode="constant")
    return decimate2(rot), decimate2(mrot.astype(np.float32)) > 0.5


def counter_rotate(img: np.ndarray, mask: np.ndarray, angle_deg: float
                   ) -> tuple[np.ndarray, np.ndarray]:
    """De-rotation exactly as segment.segment_pieces performs it."""
    if angle_deg == 0.0:
        return img, mask
    d_img = ndimage.rotate(np.where(mask, img, float(BACKING)), angle_deg,
                           reshape=True, order=3, cval=BACKING,
                           mode="constant")
    d_msk = ndimage.rotate(mask.astype(np.uint8), angle_deg, reshape=True,
                           order=0, cval=0, mode="constant") > 0
    return d_img, d_msk


def piece_bits(img: np.ndarray, mask: np.ndarray
               ) -> tuple[np.ndarray, np.ndarray, dict]:
    """scannorm pitch + canonical footing + segment.piece_cell_bits — the
    session_decode.piece_bits sub-grain path, verbatim conventions."""
    pit = scannorm.measure_cell_pitch(img)
    norm = scannorm.normalize_to_canonical(img, pit.pitch_px, CELL_DOTS)
    ms = mask
    if norm.img.shape != mask.shape:      # canonical resample moved px
        yy = (np.arange(norm.img.shape[0]) * mask.shape[0]
              // norm.img.shape[0])
        xx = (np.arange(norm.img.shape[1]) * mask.shape[1]
              // norm.img.shape[1])
        ms = mask[np.clip(yy, 0, mask.shape[0] - 1)][
            :, np.clip(xx, 0, mask.shape[1] - 1)]
    hard, mcell, _llr = segment.piece_cell_bits(
        norm.img, ms, int(round(norm.cell_px_est)))
    diag = {"pitch_px": round(float(pit.pitch_px), 4),
            "pitch_angle_deg": round(float(np.degrees(pit.angle_rad)), 3),
            "cell_px_est": round(float(norm.cell_px_est), 4),
            "rescale": [norm.scale_num, norm.scale_den]}
    return hard, mcell, diag


def main() -> int:
    t_start = time.time()
    src = ROOT / SCAN_REL
    sha = hashlib.sha256(src.read_bytes()).hexdigest()
    if sha != SCAN_SHA:
        raise SystemExit(f"source scan sha mismatch: {sha} != {SCAN_SHA}")
    arr = tifffile.TiffFile(str(src)).pages[0].asarray(out="memmap")

    y0f, y1f, x0f, x1f = field_bbox_longest_run(arr)
    spec = gen_e016.make_spec()
    H, W = spec.page_cells_yx
    print(f"field bbox @4800: rows {y0f}..{y1f} cols {x0f}..{x1f} "
          f"({(y1f - y0f) / 3300:.3f} / {(x1f - x0f) / 2220:.3f} px/cell)",
          flush=True)

    # GT page (regenerated; paper==build dot-exact per 016.2)
    vspec = gen_e016.make_vspec()
    data = gen_e016.make_data(vspec)
    framed = fountain.encode_volume_pages(data, vspec)[0]
    gt_cells = compose_page(framed["payload_bits"], spec, gen_e016.SEED,
                            page=0).cell_values

    gen = rng(gen_e016.SEED, RNG_LABEL)
    rects = sample_rects(gen, (y0f, y1f, x0f, x1f))
    n_px = int(SIDE_MM * MM_SRC)
    pend = {0: np.ones((H, W), bool)}
    rows: list[dict] = []
    est0_by_piece: dict[int, float] = {}
    critical: list[dict] = []

    for pi, (sy, sx) in enumerate(rects):
        crop = np.asarray(arr[sy:sy + n_px, sx:sx + n_px], np.float32)
        # GT rect center in page cells via the bbox-linear map (deviation 3)
        gy = (sy + n_px / 2 - y0f) / (y1f - y0f) * H
        gx = (sx + n_px / 2 - x0f) / (x1f - x0f) * W
        for ang in ANGLES_DEG:
            img_r, msk_r = prep_piece(crop, ang)
            genie_deg = fold90(-ang)
            for leg in ("A", "B"):
                t0 = time.time()
                row: dict = {"piece": pi, "src_yx_4800": [sy, sx],
                             "angle_deg": ang, "leg": leg}
                if leg == "A":
                    est = segment.lattice_angle(img_r, msk_r, 8.0)
                    row["angle_est_deg"] = round(est, 4)
                    row["angle_err_raw_deg"] = round(fold90(est + ang), 4)
                    if ang == 0.0:
                        est0_by_piece[pi] = est
                    if pi in est0_by_piece:
                        row["angle_err_skewref_deg"] = round(
                            fold90(est + ang - est0_by_piece[pi]), 4)
                    counter = est
                else:
                    counter = genie_deg
                d_img, d_msk = counter_rotate(img_r, msk_r, counter)
                try:
                    hard, mcell, diag = piece_bits(d_img, d_msk)
                except scannorm.ScanRefused as e:
                    row.update(status="scan_refused", error=str(e),
                               secs=round(time.time() - t0, 2))
                    rows.append(row)
                    continue
                row.update(diag, n_cells=int(mcell.sum()))
                if hard.size == 0 or not mcell.any():
                    row.update(status="no_cells",
                               secs=round(time.time() - t0, 2))
                    rows.append(row)
                    continue
                pl = place.place_fragment(hard, spec, gen_e016.SEED,
                                          mask=mcell,
                                          pending_cell_mask=pend,
                                          gate_true=GATE_TRUE,
                                          gate_decoy=GATE_DECOY)
                gap = pl.rival_mismatch - pl.mismatch
                gate_pass = bool(pl.ok and gap >= GAP_MIN)
                oy, ox = pl.origin_yx
                bk = np.rot90(hard, pl.rot_k)
                mk = np.rot90(mcell, pl.rot_k)
                hh = min(bk.shape[0], H - oy)
                ww = min(bk.shape[1], W - ox)
                sel = mk[:hh, :ww]
                ys, xs = np.nonzero(mk)
                dyx = (oy + ys.mean() - gy, ox + xs.mean() - gx)
                correct = bool(max(abs(dyx[0]), abs(dyx[1])) <= GT_TOL_CELLS)
                ber_best = float((bk[:hh, :ww][sel]
                                  != gt_cells[oy:oy + hh,
                                              ox:ox + ww][sel]).mean())
                row.update(status="placed",
                           mismatch=round(pl.mismatch, 4),
                           rival_mismatch=round(pl.rival_mismatch, 4),
                           gap=round(gap, 4), z=round(pl.z, 2),
                           support=pl.support, rot_k=pl.rot_k,
                           origin_yx=[oy, ox], gate_pass=gate_pass,
                           placed_correct=correct,
                           dcent_cells=[round(dyx[0], 1),
                                        round(dyx[1], 1)],
                           ber_at_best=round(ber_best, 4),
                           ber=round(ber_best, 4) if correct else None,
                           secs=round(time.time() - t0, 2))
                if gate_pass and not correct:
                    critical.append(row)     # a gated WRONG placement
                rows.append(row)
                print(f"p{pi:02d} a{ang:>4.0f} {leg}: mism "
                      f"{pl.mismatch:.3f} gap {gap:+.3f} "
                      f"gate={'PASS' if gate_pass else 'fail'} "
                      f"correct={correct} "
                      f"ber={ber_best:.3f} ({row['secs']}s)", flush=True)

    def med(vals: list[float]) -> float | None:
        return round(float(np.median(vals)), 4) if vals else None

    summary: dict = {}
    for ang in ANGLES_DEG:
        for leg in ("A", "B"):
            sub = [r for r in rows
                   if r["angle_deg"] == ang and r["leg"] == leg]
            plc = [r for r in sub if r.get("status") == "placed"]
            cor = [r for r in plc if r["placed_correct"]]
            key = f"a{ang:g}_{leg}"
            summary[key] = {
                "n": len(sub),
                "median_mismatch_correct": med(
                    [r["mismatch"] for r in cor]),
                "median_ber_correct": med([r["ber"] for r in cor]),
                "n_placed_correct": len(cor),
                "n_gate_pass": sum(r["gate_pass"] for r in plc),
                "n_gate_pass_correct": sum(
                    r["gate_pass"] and r["placed_correct"] for r in plc),
            }
            if leg == "A":
                errs = [abs(r["angle_err_raw_deg"]) for r in sub
                        if "angle_err_raw_deg" in r]
                errs_ref = [abs(r["angle_err_skewref_deg"]) for r in sub
                            if "angle_err_skewref_deg" in r]
                summary[key]["median_abs_angle_err_raw_deg"] = med(errs)
                summary[key]["median_abs_angle_err_skewref_deg"] = med(
                    errs_ref)

    report = {
        "probe": "p3_rotation_curve (P3 item 1: rotation-loss curve)",
        "date": "2026-07-10",
        "source_scan": SCAN_REL, "source_sha256": sha,
        "rng_label": RNG_LABEL.decode(),
        "design": {"n_pieces": N_PIECES, "side_mm": SIDE_MM,
                   "rim_mm": RIM_MM, "angles_deg": list(ANGLES_DEG),
                   "backing_grey": BACKING,
                   "gate": {"gate_true": GATE_TRUE,
                            "gate_decoy": GATE_DECOY, "gap_min": GAP_MIN},
                   "gt_tol_cells": GT_TOL_CELLS},
        "deviations": [
            "field_bbox: longest-run rule (first..last dragged to the "
            "image border by a dark scanner-edge strip on this scan)",
            "piece sampling: non-overlap rejection added",
            "GT placement check: bbox-mapped rect-center within 10 cells",
            "angle error also reported skew-referenced to the piece's "
            "angle-0 estimate (the scan carries its own small skew)",
            "leg A at angle 0 estimates + counter-rotates (production "
            "path); only leg B at angle 0 is rotate-free",
        ],
        "field_bbox_4800": [y0f, y1f, x0f, x1f],
        "critical_wrong_gated_placements": critical,
        "summary": summary,
        "rows": rows,
        "total_secs": round(time.time() - t_start, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=1))
    print(f"\nwrote {OUT_JSON.relative_to(ROOT)} "
          f"({report['total_secs']} s total)", flush=True)
    if critical:
        print(f"*** CRITICAL: {len(critical)} gate-passing WRONG "
              f"placements — see report ***", flush=True)
    for k, v in summary.items():
        print(f"{k:8s} mism={v['median_mismatch_correct']} "
              f"ber={v['median_ber_correct']} "
              f"correct={v['n_placed_correct']}/{v['n']} "
              f"gate={v['n_gate_pass']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
