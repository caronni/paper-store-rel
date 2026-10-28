"""Stage-0 blind grid acquisition (paperholo.acquire) vs the measured-warp
channel simulator: synthetic c3 keystream content, print/scan through the
frozen M281 model, lock the lattice with no fiducials and no GT, and require
(a) sub-0.15-dot lock RMS on the geometry=False footing, (b) blind BER within
+2.5 pp of that footing under full geometry, (c) lock on a 90-degree-rotated
fragment, (d) pilot-anchor refinement to not regress the blind BER.

No compose.py / pilots-v2 dependency (Wave-1 isolation): content is built
directly from modulation.keystream -> cells_to_dots.

Runs under pytest, or standalone: python tests/test_acquire_grid.py
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paperholo import acquire  # noqa: E402
from paperholo.channel import ChannelParams, print_plane, scan_plane  # noqa: E402
from paperholo.modulation import cells_to_dots, keystream  # noqa: E402

SEED = b"paper-store/test-acquire-grid"
SHAPE_CELLS = (240, 240)          # 720x720 dots -> 1440x1440 px at 2 px/dot
CELL_DOTS = 3
OS = 2                            # scanner oversample (frozen M281 flatbed)
CELL_PX = CELL_DOTS * OS          # 6.0 px/cell nominal

_cache: dict = {}


def _cells() -> np.ndarray:
    if "cells" not in _cache:
        _cache["cells"] = keystream(SEED, 3, 0, SHAPE_CELLS)
    return _cache["cells"]


def _scan(geometry: bool) -> np.ndarray:
    key = f"scan_{geometry}"
    if key not in _cache:
        dots = cells_to_dots(_cells(), CELL_DOTS)
        p = ChannelParams(seed=101 if geometry else 201,
                          scan_seed=102 if geometry else 202,
                          geometry=geometry)
        _cache[key] = scan_plane(print_plane(dots, p), p)
    return _cache[key]


def _locked(geometry: bool) -> tuple[np.ndarray, acquire.GridModel]:
    key = f"grid_{geometry}"
    if key not in _cache:
        _cache[key] = acquire.lock_grid(_scan(geometry))
    return _scan(geometry), _cache[key]


def _hard_bits(geometry: bool) -> np.ndarray:
    key = f"hard_{geometry}"
    if key not in _cache:
        scan, grid = _locked(geometry)
        means = acquire.sample_cell_means(scan, grid)
        _cache[key] = acquire.cell_bits_blind(means)[0]
    return _cache[key]


def _aligned_ber(hard: np.ndarray, truth: np.ndarray, max_shift: int = 2,
                 border_cells: int = 4) -> tuple[float, tuple[int, int]]:
    """min-BER integer-cell alignment: hard[i, j] vs truth[i+ky, j+kx].

    The fragment cell origin is arbitrary modulo the seed window's wrapped
    phase (lock_grid contract); Stage A resolves it via the pilot word phase
    search — here a small shift search stands in for that."""
    hh, hw = hard.shape
    th, tw = truth.shape
    best, best_k = 1.0, (0, 0)
    for ky in range(-max_shift, max_shift + 1):
        y0 = max(0, -ky)
        y1 = min(hh, th - ky)
        for kx in range(-max_shift, max_shift + 1):
            x0 = max(0, -kx)
            x1 = min(hw, tw - kx)
            h = hard[y0 + border_cells:y1 - border_cells,
                     x0 + border_cells:x1 - border_cells]
            t = truth[y0 + ky + border_cells:y1 + ky - border_cells,
                      x0 + kx + border_cells:x1 + kx - border_cells]
            ber = float(np.mean(h != t))
            if ber < best:
                best, best_k = ber, (ky, kx)
    return best, best_k


def test_center_convention_geometry_false() -> None:
    """Derive the geometry=False cell-center convention (the contract's
    parenthetical '6k+3' guess is measured WRONG): scan px r samples dot r/os,
    so the 3-dot cell k (central dot 3k+1) centers at px 6k+2."""
    cells = np.zeros((11, 11), np.uint8)
    cells[5, 5] = 1
    dots = cells_to_dots(cells, CELL_DOTS)
    p = ChannelParams(seed=7, scan_seed=8, geometry=False)
    scan = scan_plane(print_plane(dots, p), p)
    dark = np.clip(scan.max() - scan, 0.0, None)
    k = 5 * CELL_PX + 2
    w = dark[k - 8:k + 9, k - 8:k + 9]          # local window: mottle-immune
    w = np.where(w > 0.3 * w.max(), w, 0.0)
    yy, xx = np.mgrid[0:w.shape[0], 0:w.shape[1]]
    cy = float((w * yy).sum() / w.sum()) + k - 8
    cx = float((w * xx).sum() / w.sum()) + k - 8
    assert abs(cy - k) < 0.35, f"y centroid {cy:.2f} != 6k+2 = {k}"
    assert abs(cx - k) < 0.35, f"x centroid {cx:.2f} != 6k+2 = {k}"
    print(f"  isolated-cell centroid ({cy:.2f}, {cx:.2f}) px, "
          f"6k+2 = {k} (6k+3 = {k + 1} rejected)")


def test_lock_grid_geometry_false_rms() -> None:
    scan, grid = _locked(False)
    assert abs(grid.pitch_v_px - CELL_PX) / CELL_PX < 0.003
    assert abs(grid.pitch_u_px - CELL_PX) / CELL_PX < 0.003
    assert abs(grid.angle_rad) < 0.01
    assert grid.shape_cells[0] >= SHAPE_CELLS[0] - 1
    # truth: cell (i, j) center at px (6i+2, 6j+2) — see the centroid test
    n = SHAPE_CELLS[0]
    ii = np.arange(4, n - 4, dtype=np.float64)[:, None]
    jj = np.arange(4, n - 4, dtype=np.float64)[None, :]
    y_px, x_px = grid.cell_centers_px(ii, jj)
    dy_dots = (y_px - (6.0 * ii + 2.0)) / OS
    dx_dots = (x_px - (6.0 * jj + 2.0)) / OS
    rms_y = float(np.sqrt(np.mean(dy_dots ** 2)))
    rms_x = float(np.sqrt(np.mean(dx_dots ** 2)))
    print(f"  geomF lock RMS: y {rms_y:.4f} dots, x {rms_x:.4f} dots "
          f"(pitch {grid.pitch_v_px:.4f}/{grid.pitch_u_px:.4f} px)")
    assert rms_y <= 0.15 and rms_x <= 0.15

    # determinism: byte-identical re-lock
    g2 = acquire.lock_grid(scan)
    assert np.array_equal(g2.phi_v_px, grid.phi_v_px)
    assert np.array_equal(g2.phi_u_px, grid.phi_u_px)
    assert g2.pitch_v_px == grid.pitch_v_px


def test_blind_ber_geometry_true_vs_footing() -> None:
    ber_f, k_f = _aligned_ber(_hard_bits(False), _cells())
    ber_t, k_t = _aligned_ber(_hard_bits(True), _cells())
    _cache["ber_t"] = ber_t
    _cache["shift_t"] = k_t
    print(f"  blind BER: geomF footing {100 * ber_f:.2f}% (shift {k_f}), "
          f"geomT {100 * ber_t:.2f}% (shift {k_t})")
    assert ber_f < 0.08, "geometry=False footing must be < 8%"
    assert ber_t < 0.08, "geometry=True blind BER must be < 8%"
    assert ber_t <= ber_f + 0.025, \
        f"geomT {100 * ber_t:.2f}% exceeds footing {100 * ber_f:.2f}% +2.5pp"


def test_rot90_fragment_locks() -> None:
    scan90 = np.rot90(_scan(True))
    grid = acquire.lock_grid(scan90)
    assert abs(grid.pitch_v_px - CELL_PX) / CELL_PX < 0.01
    assert abs(grid.angle_rad) < 0.01
    means = acquire.sample_cell_means(scan90, grid)
    hard, _ = acquire.cell_bits_blind(means)
    ber, k = _aligned_ber(hard, np.rot90(_cells()))
    print(f"  rot90 fragment: pitch {grid.pitch_v_px:.4f}/"
          f"{grid.pitch_u_px:.4f} px, BER {100 * ber:.2f}% (shift {k})")
    assert ber < 0.08


def test_pilot_anchors_and_resample() -> None:
    scan, grid = _locked(True)
    hard = _hard_bits(True)
    ber_t, (ky, kx) = _aligned_ber(hard, _cells())
    cells = _cells()
    # synthetic pilot sites: one known cell per 12x12-cell block (denser than
    # p60b6's 6x6-block lattice but same anchor character), interior only
    sy = np.arange(6, grid.shape_cells[0] - 6, 12)
    sx = np.arange(6, grid.shape_cells[1] - 6, 12)
    sites = np.stack(np.meshgrid(sy, sx, indexing="ij"), -1).reshape(-1, 2)
    ty = sites[:, 0] + ky
    tx = sites[:, 1] + kx
    ok = ((ty >= 0) & (ty < cells.shape[0])
          & (tx >= 0) & (tx < cells.shape[1]))
    sites = sites[ok]
    expected = cells[ty[ok], tx[ok]]

    anchors = acquire.measure_pilot_anchors(scan, grid, sites, expected,
                                            detected_bits=hard)
    lock_rate = float(np.isfinite(anchors["dy_dots"]).mean())
    dym = np.nanmean(np.abs(anchors["dy_dots"]))
    dxm = np.nanmean(np.abs(anchors["dx_dots"]))
    print(f"  anchors: {sites.shape[0]} sites, lock rate {lock_rate:.2f}, "
          f"mean |dy| {dym:.3f} / |dx| {dxm:.3f} dots")
    assert lock_rate > 0.7, "most pilot anchors must lock (min_q=0.10)"
    # residuals after grid lock must be sub-cell (no integer ambiguity left)
    assert dym < 1.0 and dxm < 1.0

    # genie-anchor lock RMS report (expected = truth at every site): the
    # anchor residual IS the grid error as seen by the NCC instrument
    rms_dy = float(np.sqrt(np.nanmean(anchors["dy_dots"] ** 2)))
    rms_dx = float(np.sqrt(np.nanmean(anchors["dx_dots"] ** 2)))
    print(f"  geomT anchor-measured lock RMS: y {rms_dy:.3f} dots, "
          f"x {rms_dx:.3f} dots")

    warp = acquire.anchor_warp_field(anchors, grid.shape_cells)
    means_r = acquire.resample_cell_means(scan, grid, warp)
    hard_r, llr_r = acquire.cell_bits_blind(means_r)
    assert llr_r.shape == hard_r.shape == means_r.shape
    ber_r, _ = _aligned_ber(hard_r, cells)
    print(f"  resample-after-anchors BER {100 * ber_r:.2f}% "
          f"(pre-anchor {100 * ber_t:.2f}%)")
    # on the sim the Stage-0 grid is already tight, so anchors only add
    # their own NCC noise — require they stay within +0.5 pp
    assert ber_r <= ber_t + 0.005, "anchor refinement must not regress BER"


def _apply_warp_grid(grid: acquire.GridModel, warp) -> acquire.GridModel:
    """Fold a (dy, dx) cell-domain warp field into a new GridModel's phase
    profiles so the anchor loop can iterate against the corrected grid."""
    import dataclasses

    y_cells = grid.v_centers_px / grid.pitch_v_px - 0.5
    x_cells = grid.u_centers_px / grid.pitch_u_px - 0.5
    dy_v, _ = warp(y_cells, np.zeros_like(y_cells))
    _, dx_u = warp(np.zeros_like(x_cells), x_cells)
    return dataclasses.replace(
        grid,
        phi_v_px=grid.phi_v_px + dy_v * grid.pitch_v_px / acquire.CELL_DOTS,
        phi_u_px=grid.phi_u_px + dx_u * grid.pitch_u_px / acquire.CELL_DOTS)


def test_anchor_warp_recovers_corrupted_grid() -> None:
    """The anchor path must do real WORK, not just not-regress: corrupt the
    locked grid's bottom half by +1 dot (the anchors' design regime is
    sub-cell residual warp, strip_tracker datum ~+-0.5-2 dots) and require
    two rounds of pilot anchors + separable warp field to recover it. A
    HALF-CELL (1.5-dot) corruption recovers only slowly (halo cells of the
    template are detected through the same bad grid — measured limitation,
    see measure_pilot_anchors docstring); that regime belongs to Stage A."""
    import dataclasses

    scan, grid = _locked(True)
    cells = _cells()
    _, (ky, kx) = _aligned_ber(_hard_bits(True), cells)

    def _ber(g: acquire.GridModel) -> float:
        hard, _ = acquire.cell_bits_blind(acquire.sample_cell_means(scan, g))
        return float(np.mean(
            hard[4:-4, 4:-4]
            != cells[4 + ky:hard.shape[0] - 4 + ky,
                     4 + kx:hard.shape[1] - 4 + kx]))

    v_mid = float(np.median(grid.v_centers_px))
    phi_bad = grid.phi_v_px + 2.0 * (grid.v_centers_px > v_mid)  # +1 dot
    grid_bad = dataclasses.replace(grid, phi_v_px=phi_bad)
    ber_bad = _ber(grid_bad)
    assert ber_bad > 0.05, "corruption must bite, else the test is vacuous"

    sy = np.arange(6, grid.shape_cells[0] - 6, 12)
    sx = np.arange(6, grid.shape_cells[1] - 6, 12)
    sites = np.stack(np.meshgrid(sy, sx, indexing="ij"), -1).reshape(-1, 2)
    expected = cells[sites[:, 0] + ky, sites[:, 1] + kx]

    g_cur = grid_bad
    ber_rec = ber_bad
    for _round in range(2):
        bits, llr = acquire.cell_bits_blind(
            acquire.sample_cell_means(scan, g_cur))
        anchors = acquire.measure_pilot_anchors(
            scan, g_cur, sites, expected,
            detected_bits=bits, detected_llr=llr)
        warp = acquire.anchor_warp_field(anchors, g_cur.shape_cells)
        g_cur = _apply_warp_grid(g_cur, warp)
        ber_rec = _ber(g_cur)
        print(f"  round {_round + 1}: recovered BER {100 * ber_rec:.2f}% "
              f"(corrupted {100 * ber_bad:.2f}%)")
    assert ber_rec < ber_bad / 2
    assert ber_rec < 0.08


def test_centers_uv_slip_fold_flat_grid() -> None:
    """Finding [0] mechanism regression: fold +-1-cell slip-step profiles
    into a flat GridModel via the exact acquire_and_decode path
    (_fold_warp_into_grid) and require EVERY cell's sampled center to be
    exactly (intended cell + shift) * pitch. Pre-fix, the _centers_uv
    fixed-point re-evaluation crossed the folded step at any negative-going
    one-cell transition (band start for -1 folds, band END for finite +1
    bands) and read the pre-step branch, un-doing the fold for that whole
    cell row/column (measured +6.0 px error at exactly the boundary cell)."""
    n = 120
    pitch = 6.0
    centers = (np.arange(n, dtype=np.float64) + 0.5) * pitch
    base = acquire.GridModel(
        shape_cells=(n, n), pitch_px=pitch, angle_rad=0.0,
        quality=np.ones((1, 1)), pitch_v_px=pitch, pitch_u_px=pitch,
        phi_v_px=np.zeros(n), v_centers_px=centers.copy(),
        phi_u_px=np.zeros(n), u_centers_px=centers.copy())
    ii = np.arange(n, dtype=np.float64)
    for sign in (-1, 1):
        for b0, b1 in ((60, n), (60, 80)):   # band-to-end and finite band
            slip = np.zeros(n, np.int64)
            slip[b0:b1] = sign

            def warp(y_cells: np.ndarray, x_cells: np.ndarray,
                     slip: np.ndarray = slip
                     ) -> tuple[np.ndarray, np.ndarray]:
                iy = np.clip(np.round(np.asarray(y_cells, np.float64)
                                      ).astype(int), 0, n - 1)
                ix = np.clip(np.round(np.asarray(x_cells, np.float64)
                                      ).astype(int), 0, n - 1)
                return ((slip[iy] * acquire.CELL_DOTS).astype(np.float64),
                        (slip[ix] * acquire.CELL_DOTS).astype(np.float64))

            g = acquire._fold_warp_into_grid(base, warp)
            v, u = g._centers_uv(ii, ii)
            want = (ii + slip + 0.5) * pitch
            err_v = np.abs(np.asarray(v).ravel() - want)
            err_u = np.abs(np.asarray(u).ravel() - want)
            assert err_v.max() < 1e-6 and err_u.max() < 1e-6, \
                (f"sign {sign:+d} band [{b0},{b1}): sampled centers off by "
                 f"up to {max(err_v.max(), err_u.max()):.3f} px "
                 f"(boundary-cell fold undo, finding [0])")
    print("  slip folds sample exactly (both polarities, finite + to-end "
          "bands, both axes)")


def test_normalization_invariance() -> None:
    """0-255 grey input must acquire identically to [0,1] reflectance."""
    scan = _scan(False)
    grid = acquire.lock_grid(scan * 255.0)
    means = acquire.sample_cell_means(scan * 255.0, grid)
    hard, _ = acquire.cell_bits_blind(means)
    agree = float(np.mean(hard == _hard_bits(False)))
    assert agree >= 0.999, f"grey-scale path diverges: agreement {agree:.4f}"


if __name__ == "__main__":
    for fn in (test_center_convention_geometry_false,
               test_lock_grid_geometry_false_rms,
               test_blind_ber_geometry_true_vs_footing,
               test_rot90_fragment_locks,
               test_pilot_anchors_and_resample,
               test_anchor_warp_recovers_corrupted_grid,
               test_centers_uv_slip_fold_flat_grid,
               test_normalization_invariance):
        t0 = time.time()
        fn()
        print(f"PASS {fn.__name__} ({time.time() - t0:.1f}s)")
