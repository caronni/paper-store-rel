#!/usr/bin/env python
"""P2 detector A/B on the real-toner confetti fixture (zero print).

The 016.4 measured binder: placed real-toner pieces detect at ~13-14% BER
(median threshold on de-rotated block means) — beyond LDPC r0550's reach
(501 tiles attempted-and-failed). Two ranked levers, prototyped HERE
self-contained and only wired into paperholo.segment if they win:

  ARM A  baseline: the exact 016.4 session path — scannorm pitch +
         normalize resample + segment.piece_cell_bits (median bits) on the
         segmenter-DE-ROTATED piece (two image resamples end to end).
  ARM B  A + piece-labeled recalibration (P2a / F10 at piece scale):
         after a gate-passing placement, the piece's pilot-site cells have
         seed-predicted values (place.pilot_field) — fit a per-piece
         1-D 2-class Gaussian (QDA) on the block means, re-detect, emit
         calibrated LLRs. NOTE cell_bits_ctx was MEASURED HARMFUL on
         mask-filled piece grids (016.4) — this is NOT that: no context
         model, just labeled class-conditional calibration.
  ARM C  rotation-free detection (P2b): sample cell means directly along
         the measured rotated lattice from the UNROTATED glass pixels
         (angle+pitch from the gradient-spectrum annulus, continuous
         phase + small angle refinement searched on a detection-
         confidence objective) — ZERO image resamples (the baseline pays
         two: counter-rotation + pitch normalization).
  ARM D  C + the arm-B recalibration.

Pre-registered metrics per piece per arm: placer mismatch (established
piece-quality metric; 016.4 baseline median 0.134), gap-gate admission
(best<0.20 AND rival-best>=0.08), placement correctness vs the fixture
manifest (ANY admitted-but-wrong placement = critical alarm), and — on
correctly placed pieces — detection BER vs the composed page GT. Recal
arms only exist post-placement, so BER/calibration deltas are reported on
the placed population (declared; that population IS the binder).

Population: sub-grain pieces (< 26 mm long side) of the white-lid
real-toner fixture confetti_session_white — the placer-path
population where the binder lives (big pieces go through the word path).

Usage (from experiments/016-arch3-c2-volume/):
  ../../env/bin/python probes/p2_detector_ab.py --fixture <confetti_session_white>
      [--limit N] [--out build/p2_detector_ab.json]
(the fixture is gen_confetti_session.py --backing white over scan A)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paperholo import compose, place, scannorm, segment  # noqa: E402
import gen_e016  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SEED = gen_e016.SEED
DPI = 2400.0
PX_MM = DPI / 25.4
SUB_GRAIN_MAX_MM = 26.0
GATE_TRUE, GATE_DECOY, GATE_GAP = 0.20, 0.20, 0.08   # the 016.4 session gate
MIN_LABELS_PER_CLASS = 20      # recal refuses below this (falls back to A/C)
VAR_FLOOR = 1e-4               # class-variance floor (means are 0..255 grey)


# ---------------------------------------------------------------- arms A/B

def arm_a_bits(piece: segment.Piece) -> tuple | None:
    """The exact session path: pitch -> canonical resample -> median bits."""
    try:
        pit = scannorm.measure_cell_pitch(piece.img)
        norm = scannorm.normalize_to_canonical(piece.img, pit.pitch_px, 2)
        mscaled = piece.mask
        if norm.img.shape != piece.mask.shape:
            zy = norm.img.shape[0] / piece.mask.shape[0]
            zx = norm.img.shape[1] / piece.mask.shape[1]
            yy = (np.arange(norm.img.shape[0]) / zy).astype(int)
            xx = (np.arange(norm.img.shape[1]) / zx).astype(int)
            mscaled = piece.mask[np.clip(yy, 0, piece.mask.shape[0] - 1)][
                :, np.clip(xx, 0, piece.mask.shape[1] - 1)]
        hard, kmask, llr = segment.piece_cell_bits(
            norm.img, mscaled, int(round(norm.cell_px_est)))
        if hard.size == 0:
            return None
        # re-derive the locked means for the recal arm: piece_cell_bits
        # does not return them, so repeat its winning-phase block mean
        # (same objective, same search — verified to reproduce its bits)
        means = _relock_means(norm.img, mscaled,
                              int(round(norm.cell_px_est)), hard)
        return hard, kmask, llr, means
    except Exception:
        return None


def _relock_means(img: np.ndarray, mask: np.ndarray, c: int,
                  want_bits: np.ndarray) -> np.ndarray | None:
    """Recover the block-mean grid behind piece_cell_bits' winning phase."""
    mid = float(np.median(img[mask])) if mask.any() else float(np.median(img))
    best = None
    for dy in range(c):
        for dx in range(c):
            h = ((img.shape[0] - dy) // c) * c
            w = ((img.shape[1] - dx) // c) * c
            if h < c or w < c:
                continue
            m = img[dy:dy + h, dx:dx + w].reshape(
                h // c, c, w // c, c).mean(axis=(1, 3))
            km = mask[dy:dy + h, dx:dx + w].reshape(
                h // c, c, w // c, c).mean(axis=(1, 3)) > 0.85
            conf = float(np.abs(m[km] - mid).mean()) if km.any() else 0.0
            if best is None or conf > best[0]:
                best = (conf, m)
    if best is None:
        return None
    m = best[1]
    if m.shape != want_bits.shape:      # defensive: must mirror the module
        return None
    return m


# ------------------------------------------------------------------- arm C

def _rotate_transform(in_shape: tuple, angle_deg: float
                      ) -> tuple[np.ndarray, np.ndarray, tuple]:
    """The exact output->input affine of scipy.ndimage.rotate(...,
    reshape=True): output coord o maps to input coord M @ o + offset.
    Mirrors scipy's construction (rot_matrix [[c,s],[-s,c]], out bounds
    from the un-decremented shape corners, centers at (shape-1)/2); the
    _selftest below asserts equivalence against ndimage.rotate at import
    so a scipy convention change can never silently skew arm C."""
    a = np.deg2rad(angle_deg)
    c, s = np.cos(a), np.sin(a)
    M = np.array([[c, s], [-s, c]])
    iy, ix = in_shape
    out_bounds = M @ np.array([[0, 0, iy, iy], [0, ix, 0, ix]], np.float64)
    out_shape = (np.ptp(out_bounds, axis=1) + 0.5).astype(int)
    in_center = (np.array(in_shape, np.float64) - 1) / 2
    out_center = M @ ((out_shape - 1) / 2)
    offset = in_center - out_center
    return M, offset, (int(out_shape[0]), int(out_shape[1]))


def _selftest_rotate_transform() -> None:
    rng = np.random.default_rng(0)          # test-only, not a codec path
    a = ndimage.gaussian_filter(rng.normal(size=(160, 130)), 3.0)
    ang = 17.3
    ref = ndimage.rotate(a, ang, reshape=True, order=1, cval=0.0,
                         mode="constant")
    M, off, out_shape = _rotate_transform(a.shape, ang)
    assert out_shape == ref.shape, (out_shape, ref.shape)
    oy, ox = np.meshgrid(np.arange(30, out_shape[0] - 30),
                         np.arange(30, out_shape[1] - 30), indexing="ij")
    coords = M @ np.array([oy.ravel(), ox.ravel()], np.float64) \
        + off[:, None]
    got = ndimage.map_coordinates(a, coords, order=1, cval=0.0)
    err = np.abs(got - ref[30:-30, 30:-30].ravel()).max()
    assert err < 1e-6, f"rotate-transform mismatch {err}"


def _phase_scan(im, mk, mid, backing, M, off, out_shape, p,
                phase_step: int = 1) -> tuple | None:
    """Best (conf, dy, dx) integer phase for one de-rotation transform."""
    n_ph = int(np.ceil(p))
    best = None
    for dy in range(0, n_ph, phase_step):
        n_cy = int((out_shape[0] - dy) // p)
        if n_cy < 2:
            continue
        ycs = dy + (np.arange(n_cy) + 0.5) * p
        for dx in range(0, n_ph, phase_step):
            n_cx = int((out_shape[1] - dx) // p)
            if n_cx < 2:
                continue
            xcs = dx + (np.arange(n_cx) + 0.5) * p
            # coarse objective: every k-th cell center, one sample each
            k = max(1, int(round(max(n_cy, n_cx) / 40)))
            oy, ox = np.meshgrid(ycs[::k], xcs[::k], indexing="ij")
            coords = M @ np.array([oy.ravel(), ox.ravel()]) + off[:, None]
            m = ndimage.map_coordinates(im, coords, order=1, cval=backing)
            q = ndimage.map_coordinates(mk, coords, order=1, cval=0.0)
            sel = q > 0.98
            if sel.sum() < 16:
                continue
            conf = float(np.abs(m[sel] - mid).mean())
            if best is None or conf > best[0]:
                best = (conf, dy, dx)
    return best


def rotfree_cell_means(glass: np.ndarray, gmask: np.ndarray,
                       corr_angle_deg: float, pitch_px: float,
                       backing: float, n_sub: int = 3,
                       refine_deg: float = 1.0) -> tuple | None:
    """Cell means sampled along the rotated lattice from UNROTATED pixels,
    with PIECE-LOCAL ANGLE REFINEMENT around the segmenter's estimate.

    The P3.1 rotation-curve probe measured the 016.4 "+4pp intrinsic
    rotation tax" to be ANGLE-ESTIMATION error, not resample loss (genie
    angle: mismatch 0.131 flat 0-45deg; dose-response zero below ~0.15deg
    error, +0.2 mismatch at >=0.5deg; lattice_angle delivers ~0.4-0.5deg
    median). So the lever is refining the angle on the lock-confidence
    objective — and coordinate-sampling makes each angle candidate cost a
    transform instead of a full image rotation. Geometry per candidate is
    the exact ndimage.rotate transform (self-tested), phase on the same
    integer grid and objective as piece_cell_bits.

    Two-stage search: angles est +- refine_deg step 0.2 with quarter
    phases, then best +- 0.2 step 0.05 with full phases; final read =
    n_sub^2 in-cell offsets averaged, order-3 spline (the baseline's
    interpolation class) on the once-prefiltered piece.
    """
    im = np.where(gmask, np.asarray(glass, np.float32),
                  np.float32(backing))       # parity: segmenter fills too
    mk = np.asarray(gmask, np.float32)
    mid = float(np.median(im[gmask])) if gmask.any() else float(np.median(im))
    p = float(pitch_px)
    best = None                              # (conf, angle, dy, dx)
    coarse = np.arange(-refine_deg, refine_deg + 1e-9, 0.2)
    for da in coarse:
        M, off, out_shape = _rotate_transform(im.shape,
                                              corr_angle_deg + da)
        got = _phase_scan(im, mk, mid, backing, M, off, out_shape, p,
                          phase_step=2)
        if got and (best is None or got[0] > best[0]):
            best = (got[0], corr_angle_deg + da, got[1], got[2])
    if best is None:
        return None
    fine = best[1] + np.arange(-0.2, 0.2 + 1e-9, 0.05)
    best2 = None
    for ang in fine:
        M, off, out_shape = _rotate_transform(im.shape, ang)
        got = _phase_scan(im, mk, mid, backing, M, off, out_shape, p,
                          phase_step=1)
        if got and (best2 is None or got[0] > best2[0]):
            best2 = (got[0], ang, got[1], got[2])
    if best2 is None:
        return None
    conf, ang, dy, dx = best2
    M, off, out_shape = _rotate_transform(im.shape, ang)
    n_cy = int((out_shape[0] - dy) // p)
    n_cx = int((out_shape[1] - dx) // p)
    ycs = dy + np.arange(n_cy) * p
    xcs = dx + np.arange(n_cx) * p
    offs = (np.arange(n_sub) + 0.5) / n_sub * p
    means = np.zeros((n_cy, n_cx), np.float64)
    cover = np.zeros((n_cy, n_cx), np.float64)
    imf = ndimage.spline_filter(im, order=3)   # once; order-3 = the
    for dv in offs:                            # baseline's interp class
        for du in offs:
            oy, ox = np.meshgrid(ycs + dv, xcs + du, indexing="ij")
            coords = (M @ np.array([oy.ravel(), ox.ravel()])
                      + off[:, None])
            means += ndimage.map_coordinates(
                imf, coords, order=3, prefilter=False,
                cval=backing).reshape(n_cy, n_cx)
            cover += ndimage.map_coordinates(
                mk, coords, order=1, cval=0.0).reshape(n_cy, n_cx)
    means /= n_sub * n_sub
    kmask = (cover / (n_sub * n_sub)) > 0.85
    if not kmask.any():
        return None
    ky = np.flatnonzero(kmask.any(axis=1))
    kx = np.flatnonzero(kmask.any(axis=0))
    sl = (slice(ky[0], ky[-1] + 1), slice(kx[0], kx[-1] + 1))
    means, kmask = means[sl], kmask[sl]
    spread = float(np.abs(means[kmask] - mid).mean()) if kmask.any() else 1.0
    llr = np.clip((mid - means) / max(spread, 1e-6), -8.0, 8.0) * 2.0
    hard = (means < mid).astype(np.uint8)
    return hard, kmask, llr, means, {"phase": (dy, dx), "conf": conf,
                                     "angle_refined": float(ang)}


# ------------------------------------------------------------- recal (B/D)

def qda_recal(means: np.ndarray, kmask: np.ndarray, pl: place.Placement,
              spec, seed: bytes) -> tuple | None:
    """Per-piece 2-class Gaussian recalibration from placed pilot labels."""
    vals, smask = place.pilot_field(spec, seed, pl.page)
    mk = np.rot90(kmask, pl.rot_k)
    mm = np.rot90(means, pl.rot_k)
    oy, ox = pl.origin_yx
    H, W = vals.shape
    hh, ww = min(mk.shape[0], H - oy), min(mk.shape[1], W - ox)
    sv = vals[oy:oy + hh, ox:ox + ww]
    sm = smask[oy:oy + hh, ox:ox + ww]
    lab_sel = sm & mk[:hh, :ww]
    y = sv[lab_sel].astype(bool)                # True = ink printed
    x = mm[:hh, :ww][lab_sel].astype(np.float64)
    if (y.sum() < MIN_LABELS_PER_CLASS
            or (~y).sum() < MIN_LABELS_PER_CLASS):
        return None
    mu1, mu0 = float(x[y].mean()), float(x[~y].mean())
    v1 = max(float(x[y].var()), VAR_FLOOR)
    v0 = max(float(x[~y].var()), VAR_FLOOR)
    if mu1 >= mu0:      # ink must be darker; refuse a degenerate fit
        return None
    m = mm[:hh, :ww]
    llr_rot = (-0.5 * ((m - mu1) ** 2 / v1 - (m - mu0) ** 2 / v0)
               - 0.5 * np.log(v1 / v0))
    llr_rot = np.clip(llr_rot, -12.0, 12.0)
    # back to the piece frame (undo the placement rotation) on full grids
    full = np.full(mm.shape, 0.0)
    full[:hh, :ww] = llr_rot
    llr = np.rot90(full, -pl.rot_k)
    hard = (llr > 0).astype(np.uint8)
    return hard, llr, {"n_ink": int(y.sum()), "n_paper": int((~y).sum()),
                       "mu": [mu0, mu1], "var": [v0, v1]}


# ---------------------------------------------------------------- plumbing

def gate(pl: place.Placement) -> bool:
    return bool(pl.ok and (pl.rival_mismatch - pl.mismatch) >= GATE_GAP)


def origin_delta(pl: place.Placement, gt_rect_cells: tuple) -> list:
    """Origin distance to the manifest rect — DIAGNOSTIC only: the real-scan
    manifest rect rides the coarse field bbox (±2-3 cell slop), so
    correctness is judged by GT bit agreement (016.4 audit precedent:
    admitted pieces read agreement 0.79-0.83; the d-floor pins false
    placements near 0.4-0.5 BER)."""
    gy, gx = gt_rect_cells[0], gt_rect_cells[1]
    oy, ox = pl.origin_yx
    return [int(oy - gy), int(ox - gx)]


WRONG_PLACEMENT_BER = 0.35   # admitted piece with GT-BER above this = wrong


def gt_ber(bits: np.ndarray, kmask: np.ndarray, pl: place.Placement,
           gt_cells: np.ndarray) -> float | None:
    bk = np.rot90(bits, pl.rot_k)
    mk = np.rot90(kmask, pl.rot_k)
    oy, ox = pl.origin_yx
    H, W = gt_cells.shape
    hh, ww = min(bk.shape[0], H - oy), min(bk.shape[1], W - ox)
    sel = mk[:hh, :ww]
    if not sel.any():
        return None
    return float(np.mean(bk[:hh, :ww][sel]
                         != gt_cells[oy:oy + hh, ox:ox + ww][sel]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=0,
                    help="cap pieces PER SCAN (0 = all sub-grain pieces); "
                         "per-scan so every size class is sampled — the "
                         "single-phase lock ceiling makes 25mm-class "
                         "pieces a different regime from the <=12mm "
                         "binder population")
    ap.add_argument("--out", type=Path,
                    default=Path(__file__).resolve().parents[1]
                    / "build/p2_detector_ab.json")
    args = ap.parse_args()

    spec = gen_e016.make_spec()
    gt_cells = None      # composed lazily (GT audit only, never fed to arms)
    manifest = json.loads((args.fixture / "session_manifest.json"
                           ).read_text())
    pend = {0: np.ones(tuple(spec.page_cells_yx), bool)}   # session-fresh
    rows = []
    t0 = time.time()
    _selftest_rotate_transform()
    for scan in manifest["scans"]:
        img = np.asarray(Image.open(args.fixture / f"{scan['scan']}.png"
                                    ).convert("L"), np.float32)
        pieces = segment.segment_pieces(img, cell_px=8.0, dpi=DPI)
        backing = segment.estimate_backing(img)   # arm C parity fill
        n_seen = 0        # per-scan cap: sample every size class
        # associate segmented pieces to manifest entries by canvas bbox
        for p in pieces:
            if max(p.bbox_glass[2], p.bbox_glass[3]) / PX_MM \
                    >= SUB_GRAIN_MAX_MM:
                continue
            ent = _match_manifest(p, scan["manifest"])
            if ent is None:
                continue
            if args.limit and n_seen >= args.limit:
                break
            n_seen += 1
            gt_rect = ent["cell_rect"] if "cell_rect" in ent else None
            if gt_rect is None:      # real-scan fixture: rect at 4800 px
                sy, sx, n, _ = ent["src_rect_4800"]
                fy0, _, fx0, _ = manifest["field_bbox_4800"]
                gt_rect = (round((sy - fy0) / 16.0), round((sx - fx0) / 16.0),
                           round(n / 16.0))   # 16 px/cell at 4800, c2
            row = {"scan": scan["scan"], "side_mm": ent["side_mm"],
                   "angle_deg": ent["angle_deg"], "gt_rect": gt_rect}

            # ---- ARM A
            got = arm_a_bits(p)
            if got is not None:
                hard, km, llr, means = got
                pl = place.place_fragment(hard, spec, SEED, mask=km,
                                          pending_cell_mask=pend,
                                          gate_true=GATE_TRUE,
                                          gate_decoy=GATE_DECOY)
                row["A"] = _score(pl, hard, km, gt_rect)
                # ---- ARM B (needs A's placement + means)
                if gate(pl) and means is not None:
                    rec = qda_recal(means, km, pl, spec, SEED)
                    if rec is not None:
                        hb, lb, meta = rec
                        row["B"] = _score(pl, hb, km, gt_rect) | {
                            "labels": [meta["n_paper"], meta["n_ink"]]}
            # ---- ARM C (unrotated glass crop + mask from the segmenter's
            # pre-rotation component; reconstruct from bbox_glass). Angle =
            # the SAME correction angle the segmenter applies (p.angle_deg);
            # pitch = the same scannorm measurement arm A rides (falls back
            # to the canonical 8.0 at declared dpi) — the resample is the
            # only remaining difference.
            y0, x0, h, w = p.bbox_glass
            glass = img[y0:y0 + h, x0:x0 + w]
            gm = _glass_mask(p, glass.shape)
            try:
                pit_c = float(scannorm.measure_cell_pitch(
                    p.img).pitch_px)
            except Exception:
                pit_c = 8.0
            try:
                got_c = rotfree_cell_means(glass, gm, p.angle_deg, pit_c,
                                           backing)
            except Exception:
                got_c = None
            if got_c is not None:
                hc, kc, lc, mc, meta_c = got_c
                plc = place.place_fragment(hc, spec, SEED, mask=kc,
                                           pending_cell_mask=pend,
                                           gate_true=GATE_TRUE,
                                           gate_decoy=GATE_DECOY)
                row["C"] = _score(plc, hc, kc, gt_rect) | {
                    "pitch": pit_c, "conf": meta_c["conf"],
                    "angle_refined": meta_c["angle_refined"],
                    "angle_seg": p.angle_deg}
                # ---- ARM D
                if gate(plc):
                    rec = qda_recal(mc, kc, plc, spec, SEED)
                    if rec is not None:
                        hd, ld, meta = rec
                        row["D"] = _score(plc, hd, kc, gt_rect) | {
                            "labels": [meta["n_paper"], meta["n_ink"]]}
            rows.append(row)

    # GT-BER audit pass (needs the composed page once)
    import paperholo.fountain as fountain
    vspec = gen_e016.make_vspec()
    framed = fountain.encode_volume_pages(gen_e016.make_data(vspec), vspec)[0]
    gt_cells = compose.compose_page(framed["payload_bits"], spec, SEED,
                                    page=0).cell_values
    for row in rows:
        for arm in ("A", "B", "C", "D"):
            if arm in row and row[arm].get("_bk") is not None:
                bits, km, pl = row[arm].pop("_bk")
                if row[arm]["placed_ok"]:
                    b = gt_ber(bits, km, pl, gt_cells)
                    row[arm]["gt_ber"] = b
                    row[arm]["placement_correct"] = (
                        b is not None and b < WRONG_PLACEMENT_BER)
            elif arm in row:
                row[arm].pop("_bk", None)

    out = {"fixture": str(args.fixture), "n_pieces": len(rows),
           "gates": {"true": GATE_TRUE, "decoy": GATE_DECOY,
                     "gap": GATE_GAP},
           "elapsed_s": round(time.time() - t0, 1), "rows": rows,
           "summary": _summarize(rows)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1, default=float))
    print(json.dumps(out["summary"], indent=1, default=float))
    print(f"-> {args.out}")
    return 0


def _score(pl, bits, kmask, gt_rect):
    ok = gate(pl)
    return {"mismatch": pl.mismatch, "rival": pl.rival_mismatch,
            "gap": pl.rival_mismatch - pl.mismatch, "placed_ok": ok,
            "origin_delta": origin_delta(pl, gt_rect) if ok else None,
            "placement_correct": None, "_bk": (bits, kmask, pl)}


def _match_manifest(p: segment.Piece, entries: list) -> dict | None:
    y0, x0, h, w = p.bbox_glass
    cy, cx = y0 + h / 2.0, x0 + w / 2.0
    best, bd = None, 1e18
    for e in entries:
        if "canvas_yx" not in e:
            continue
        ey, ex = e["canvas_yx"]
        side_px = e["side_mm"] * PX_MM
        d = (cy - (ey + side_px / 2)) ** 2 + (cx - (ex + side_px / 2)) ** 2
        if d < bd:
            best, bd = e, d
    if best is None or bd > (best["side_mm"] * PX_MM) ** 2:
        return None
    return best


def _glass_mask(p: segment.Piece, shape: tuple) -> np.ndarray:
    """Un-rotated mask: rotate the de-rotated mask back and crop/pad to the
    glass bbox shape (order-0; grow-out slack makes exactness uncritical)."""
    m = ndimage.rotate(p.mask.astype(np.uint8), -p.angle_deg,
                       reshape=True, order=0) > 0
    out = np.zeros(shape, bool)
    oy = max(0, (m.shape[0] - shape[0]) // 2)
    ox = max(0, (m.shape[1] - shape[1]) // 2)
    ty = max(0, (shape[0] - m.shape[0]) // 2)
    tx = max(0, (shape[1] - m.shape[1]) // 2)
    hh = min(shape[0] - ty, m.shape[0] - oy)
    ww = min(shape[1] - tx, m.shape[1] - ox)
    out[ty:ty + hh, tx:tx + ww] = m[oy:oy + hh, ox:ox + ww]
    return out


def _summarize(rows: list) -> dict:
    """Per-arm stats, stratified by piece size: the single-phase lock
    ceiling makes >16mm pieces a different regime (warp accumulates over
    the piece like 014.1's over-large windows) — the binder population
    is the <=16mm placer-path pieces."""
    s: dict = {}
    buckets = {"le16mm": lambda mm: mm <= 16,
               "gt16mm": lambda mm: mm > 16,
               "all": lambda mm: True}
    for bname, bsel in buckets.items():
        bs: dict = {}
        for arm in ("A", "B", "C", "D"):
            r = [x[arm] for x in rows if arm in x and bsel(x["side_mm"])]
            if not r:
                continue
            mis = [x["mismatch"] for x in r]
            adm = [x for x in r if x["placed_ok"]]
            wrong = [x for x in adm if x["placement_correct"] is False]
            bers = [x["gt_ber"] for x in adm
                    if x.get("gt_ber") is not None
                    and x["placement_correct"]]
            bs[arm] = {"n": len(r),
                       "mismatch_median": float(np.median(mis)),
                       "admitted": len(adm), "admitted_wrong": len(wrong),
                       "gt_ber_median": (float(np.median(bers)) if bers
                                         else None),
                       "gt_ber_n": len(bers)}
        s[bname] = bs
    return s


if __name__ == "__main__":
    sys.exit(main())
