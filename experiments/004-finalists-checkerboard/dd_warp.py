"""Decision-directed warp: layer-1-legal tile decode (no ground-truth input).

The v4 dense warp (scanlab.decode_cells) templates its correlation windows on
the ground-truth bitmap — genie. This module replaces the template with the
detector's OWN decisions and iterates:

  pass 0: sample cell/dot means on the marks-only affine grid (no local
          warp, no GT anywhere), fixed-rate threshold at the construction
          prior -> initial decisions;
  pass k: scanlab.decode_cells with template := decisions (the machinery is
          reused unchanged; its GT argument becomes the decision bitmap, its
          internal scoring against that argument is discarded), fresh means
          -> fixed-rate threshold -> new decisions;
  output: final means + blind soft stage, scored against TRUE GT by the
          caller (GT = measuring instrument only).

Registration marks (corner + plus affine) are legitimate layer-1 furniture;
the construction prior (0.5 for B1 cells, the manifest ink fraction for B2,
per-plane state-membership fractions for A tiles) is a format constant known
to any decoder. Attribution: scanlab (001.4), fixed_rate_bits (003.0).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scipy import ndimage

_HERE = Path(__file__).resolve().parent
for rel in ("002-calibration-page", "003-modulation-probes",
            "001-engine-characterization"):
    p = str(_HERE.parent / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

import analyze_modprobe as amp  # noqa: E402  (fixed_rate_bits)
import cal_core as cc  # noqa: E402
import scanlab  # noqa: E402

from paperholo.modulation import cells_to_dots  # noqa: E402


def lattice_phase_field(scan: dict, e: dict, cell: int, channel: str,
                        win_px: int = 96, step_px: int = 48) -> dict:
    """Self-clocked local lattice offsets (DESIGN §5.1: the lattice is its
    own clock). The cell frequency is known from the format + marks affine
    (legal constants); the local PHASE is measured per window from the
    windowed DFT of the gradient-magnitude map — no template, no GT.

    Returns dot-space offset fields (dy, dx), each mod-cell unwrapped
    against the affine prediction (offsets are small: warp is ~±2 dots),
    plus per-window quality. Cell pitches at 2 px/dot: c2 -> 0.25 cyc/px,
    c3 -> 0.167, c4 -> 0.125 — all safely below Nyquist. (Free-form 1-dot
    fields sit AT Nyquist: self-clocking is unavailable for B2; that class
    needs sync furniture — E005 strips.)"""
    arr = cc._channel_f32(scan, channel)
    coef = np.asarray(scan["affine"], np.float64)
    # tile bounding box in scan px (affine of the 4 corners, plus margin)
    cs = np.array([[e["x_dots"], e["y_dots"]],
                   [e["x_dots"] + e["w_dots"], e["y_dots"]],
                   [e["x_dots"], e["y_dots"] + e["h_dots"]],
                   [e["x_dots"] + e["w_dots"], e["y_dots"] + e["h_dots"]]],
                  np.float64)
    sx = coef[0] * cs[:, 0] + coef[1] * cs[:, 1] + coef[2]
    sy = coef[3] * cs[:, 0] + coef[4] * cs[:, 1] + coef[5]
    x0, x1 = int(sx.min()) + 2, int(sx.max()) - 2
    y0, y1 = int(sy.min()) + 2, int(sy.max()) - 2
    g = arr[y0:y1, x0:x1]
    gy, gx = np.gradient(g)
    g = np.hypot(gy, gx)

    # phases are measured in INVERSE-AFFINE DOT coordinates: offset 0 means
    # "gradient edges sit on the affine cell grid" — no arbitrary reference
    inv = cc.affine_invert(coef)

    ny = max(1, (g.shape[0] - win_px) // step_px + 1)
    nx = max(1, (g.shape[1] - win_px) // step_px + 1)
    off_x = np.zeros((ny, nx))
    off_y = np.zeros((ny, nx))
    qual = np.zeros((ny, nx))
    cy_px = np.zeros(ny)
    cx_px = np.zeros(nx)
    hann = np.hanning(win_px)
    w2d = hann[:, None] * hann[None, :]
    yyy, xxx = np.mgrid[0:win_px, 0:win_px].astype(np.float64)
    for iy in range(ny):
        for ix in range(nx):
            oy, ox = iy * step_px, ix * step_px
            wnd = g[oy:oy + win_px, ox:ox + win_px]
            if wnd.shape != (win_px, win_px):
                continue
            wz = (wnd - wnd.mean()) * w2d
            px_abs = xxx + x0 + ox
            py_abs = yyy + y0 + oy
            xd = inv[0] * px_abs + inv[1] * py_abs + inv[2]
            yd = inv[3] * px_abs + inv[4] * py_abs + inv[5]
            Fx = np.sum(wz * np.exp(-2j * np.pi * xd / cell))
            Fy = np.sum(wz * np.exp(-2j * np.pi * yd / cell))
            # g ~ cos(2π xd/cell − θ) with edge maxima at xd = θ/2π·cell:
            # F ∝ e^{−iθ}  =>  printed-lattice offset δ = −angle(F)/2π · cell
            off_x[iy, ix] = (-np.angle(Fx) / (2 * np.pi)) * cell
            off_y[iy, ix] = (-np.angle(Fy) / (2 * np.pi)) * cell
            qual[iy, ix] = min(abs(Fx), abs(Fy)) / max(np.abs(wz).sum(), 1e-9)
            cy_px[iy] = y0 + oy + win_px / 2
            cx_px[ix] = x0 + ox + win_px / 2
    # unwrap to signed offsets around 0 (warp is small vs the cell pitch)
    off_x = (off_x + cell / 2) % cell - cell / 2
    off_y = (off_y + cell / 2) % cell - cell / 2
    return {"off_x_dots": off_x, "off_y_dots": off_y, "quality": qual,
            "cy_px": cy_px, "cx_px": cx_px}


def affine_cell_means(scan: dict, e: dict, cell: int, channel: str) -> np.ndarray:
    """Cell means sampled on the marks-only affine grid — pass-0 geometry.
    No GT, no local warp: bilinear samples at a sub-grid of 2x2 points per
    cell, averaged."""
    arr = cc._channel_f32(scan, channel)
    coef = np.asarray(scan["affine"], np.float64)
    ny, nx = e["h_dots"] // cell, e["w_dots"] // cell
    sub = np.arange(0.25, 1.0, 0.5) * cell            # 2 sample rows/cols per cell
    ys = e["y_dots"] + (np.arange(ny)[:, None] * cell + sub[None, :]).ravel()
    xs = e["x_dots"] + (np.arange(nx)[:, None] * cell + sub[None, :]).ravel()
    yy = np.repeat(ys[:, None], xs.size, axis=1)
    xx = np.repeat(xs[None, :], ys.size, axis=0)
    sx = coef[0] * xx + coef[1] * yy + coef[2]
    sy = coef[3] * xx + coef[4] * yy + coef[5]
    v = ndimage.map_coordinates(arr, [sy, sx], order=1, mode="nearest")
    v = v.reshape(ny, 2, nx * 2).reshape(ny, 2, nx, 2)
    return v.mean(axis=(1, 3))


def page_anchors(scan: dict) -> list[dict]:
    """Local warp measured at every registration mark (template xcorr of
    layout furniture — legal): the absolute anchors that resolve the
    integer-cell branch of the self-clocked phase profiles."""
    lms = cc._landmark_defs(scan["manifest"], use_quads=False)
    meas = cc._measure_landmarks(scan, np.asarray(scan["affine"]), lms)
    return [m for m in meas if m["ok"]]


def selfclock_profiles(scan: dict, e: dict, cell: int, channel: str,
                       anchors: list[dict], band_px: int = 32) -> dict:
    """Self-clocked separable warp profiles for one tile: off_y(y) from
    full-width y-bands, off_x(x) from full-height x-bands, phases measured
    in inverse-affine dot coordinates at the cell frequency, 1-D nearest-
    branch unwrapped, integer branch anchored on the nearest marks' measured
    residuals. Separable matches the measured physics: scanner steps and
    printer wander are y(y); the CCD comb is x(x)."""
    arr = cc._channel_f32(scan, channel)
    coef = np.asarray(scan["affine"], np.float64)
    inv = cc.affine_invert(coef)
    cs = np.array([[e["x_dots"], e["y_dots"]],
                   [e["x_dots"] + e["w_dots"], e["y_dots"] + e["h_dots"]]],
                  np.float64)
    sx = coef[0] * cs[:, 0] + coef[1] * cs[:, 1] + coef[2]
    sy = coef[3] * cs[:, 0] + coef[4] * cs[:, 1] + coef[5]
    x0, x1 = int(min(sx)) + 2, int(max(sx)) - 2
    y0, y1 = int(min(sy)) + 2, int(max(sy)) - 2
    g = arr[y0:y1, x0:x1]
    gy, gx = np.gradient(g)
    g = np.hypot(gy, gx)
    g = g - g.mean()
    yyy, xxx = np.mgrid[0:g.shape[0], 0:g.shape[1]].astype(np.float64)
    xd = inv[0] * (xxx + x0) + inv[1] * (yyy + y0) + inv[2]
    yd = inv[3] * (xxx + x0) + inv[4] * (yyy + y0) + inv[5]
    wy = np.exp(-2j * np.pi * yd / cell)
    wx = np.exp(-2j * np.pi * xd / cell)

    def profile(axis: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        n = g.shape[axis] // band_px
        offs, quals, cents = np.zeros(n), np.zeros(n), np.zeros(n)
        for i in range(n):
            sl = slice(i * band_px, (i + 1) * band_px)
            band = g[sl] if axis == 0 else g[:, sl]
            w = (wy[sl] if axis == 0 else wx[:, sl])
            dcoord = (yd[sl] if axis == 0 else xd[:, sl])
            F = np.sum(band * w)
            offs[i] = (-np.angle(F) / (2 * np.pi)) * cell
            quals[i] = abs(F) / max(np.abs(band).sum(), 1e-9)
            cents[i] = float(dcoord.mean())
        return offs, quals, cents

    def unwrap_dp(offs: np.ndarray, quals: np.ndarray, cents: np.ndarray,
                  key: str, w_anchor: float = 3.0, n_branch: int = 3
                  ) -> tuple[np.ndarray, int]:
        """Branch selection as a global optimization: each band's offset is
        base_i + k_i*cell (k integer); minimize quality-weighted total
        variation + anchor residuals at the marks' coordinates, by DP.
        Greedy nearest-branch fails at c2 because scanner steps (<=1.95
        dots) exceed cell/2; the DP with mark anchors does not."""
        n = len(offs)
        base = ((offs + cell / 2) % cell) - cell / 2
        ks = np.arange(-n_branch, n_branch + 1)
        vals = base[:, None] + ks[None, :] * cell        # (n, K)
        coord = {"dy_dots": "y", "dx_dots": "x"}[key]
        near = [a for a in anchors
                if e["x_dots"] - 700 < a["x"] < e["x_dots"] + e["w_dots"] + 700
                and e["y_dots"] - 700 < a["y"] < e["y_dots"] + e["h_dots"] + 700]
        a_cost = np.zeros_like(vals)
        for a in near:
            i = int(np.argmin(np.abs(cents - (a["y"] if coord == "y"
                                              else a["x"]))))
            a_cost[i] += w_anchor * np.abs(vals[i] - a[key])
        gate = 0.35 * float(np.median(quals))
        w_band = np.where(quals >= gate, 1.0, 0.15)      # weak bands cheap to bend
        cost = a_cost[0].copy()
        back = np.zeros((n, vals.shape[1]), np.int64)
        for i in range(1, n):
            step = np.abs(vals[i][None, :] - vals[i - 1][:, None]) \
                * min(w_band[i], w_band[i - 1])
            tot = cost[:, None] + step
            back[i] = np.argmin(tot, axis=0)
            cost = tot[back[i], np.arange(vals.shape[1])] + a_cost[i]
        out = np.empty(n)
        j = int(np.argmin(cost))
        for i in range(n - 1, -1, -1):
            out[i] = vals[i, j]
            j = back[i, j]
        return out, len(near)

    oy, qy, cy = profile(0)
    ox_, qx, cx = profile(1)
    oy, n_a = unwrap_dp(oy, qy, cy, "dy_dots")
    ox_, _ = unwrap_dp(ox_, qx, cx, "dx_dots")
    return {"off_y": oy, "y_dots": cy, "qual_y": qy,
            "off_x": ox_, "x_dots": cx, "qual_x": qx, "n_anchors": n_a}


TILE_CELL = {"A3": 3, "A4": 4, "B1": 2}     # B2 is free-form: no self-clock


def raw_band_phases(scan: dict, e: dict, cell: int, channel: str,
                    band_px: int = 32) -> dict:
    """Wrapped (mod cell) band phases for one tile, both axes — the
    per-tile measurement the page-pooled tracker consumes."""
    arr = cc._channel_f32(scan, channel)
    coef = np.asarray(scan["affine"], np.float64)
    inv = cc.affine_invert(coef)
    cs = np.array([[e["x_dots"], e["y_dots"]],
                   [e["x_dots"] + e["w_dots"], e["y_dots"] + e["h_dots"]]],
                  np.float64)
    sx = coef[0] * cs[:, 0] + coef[1] * cs[:, 1] + coef[2]
    sy = coef[3] * cs[:, 0] + coef[4] * cs[:, 1] + coef[5]
    x0, x1 = int(min(sx)) + 2, int(max(sx)) - 2
    y0, y1 = int(min(sy)) + 2, int(max(sy)) - 2
    g = arr[y0:y1, x0:x1]
    gy, gx = np.gradient(g)
    g = np.hypot(gy, gx)
    g = g - g.mean()
    yyy, xxx = np.mgrid[0:g.shape[0], 0:g.shape[1]].astype(np.float64)
    xd = inv[0] * (xxx + x0) + inv[1] * (yyy + y0) + inv[2]
    yd = inv[3] * (xxx + x0) + inv[4] * (yyy + y0) + inv[5]
    out = {"cell": cell}
    for axis, dcoord in ((0, yd), (1, xd)):
        w = np.exp(-2j * np.pi * dcoord / cell)
        n = g.shape[axis] // band_px
        offs, quals, cents = np.zeros(n), np.zeros(n), np.zeros(n)
        for i in range(n):
            sl = slice(i * band_px, (i + 1) * band_px)
            band = g[sl] if axis == 0 else g[:, sl]
            ww = w[sl] if axis == 0 else w[:, sl]
            dc = dcoord[sl] if axis == 0 else dcoord[:, sl]
            F = np.sum(band * ww)
            offs[i] = (-np.angle(F) / (2 * np.pi)) * cell
            quals[i] = abs(F) / max(np.abs(band).sum(), 1e-9)
            cents[i] = float(dc.mean())
        out["y" if axis == 0 else "x"] = (offs, quals, cents)
    return out


def page_profiles(scan: dict, manifest: dict, anchors: list[dict],
                  channel: str = "grey") -> dict:
    """EXPERIMENTAL — measured BROKEN as-is (004.0a): pooling phases across
    tile CLASSES corrupts the consensus, because each class's lattice rides
    its own plane registration (C/M/Y offsets up to ~2 dots vs K, with
    page-scale slopes) — the per-class bias must be solved jointly with the
    consensus before cross-class pooling helps. Kept for the record; the
    working tracker today is the per-tile selfclock_profiles(). The
    mixed-cell vernier idea (c2/c3/c4 wrapped phases resolve the integer
    branch CRT-style) remains attractive once biases are modeled.

    Original intent: per grid ROW an off_y(y) consensus and per grid COLUMN
    an off_x(x) consensus (scanner steps are full-row events, the comb a
    full-column event), anchors as absolute terms."""
    tiles = manifest["tiles"]
    grid = {}
    for t in tiles:
        cell = TILE_CELL.get(t["class"])
        if cell is None:
            continue
        e = cc.entry(scan["manifest"], t["name"] if t["class"].startswith("B")
                     else f"{t['name']}_C")
        grid[(t["row"], t["col"])] = (t, e, cell,
                                      raw_band_phases(scan, e, cell, channel))

    v_grid = np.arange(-4.5, 4.5001, 0.05)

    def consensus(measurements, anchor_list) -> tuple[np.ndarray, np.ndarray]:
        """measurements: list of (off_wrapped, qual, cent, cell) band arrays
        sharing a band grid (by index). Returns (offset, coordinate) arrays."""
        n = min(len(m[0]) for m in measurements)
        prof = np.zeros(n)
        cents = np.zeros(n)
        for i in range(n):
            cost = np.zeros_like(v_grid)
            for offs, quals, cts, cl in measurements:
                r = np.abs(((offs[i] - v_grid + cl / 2) % cl) - cl / 2)
                cost += quals[i] * np.minimum(r, 1.0)
            cents[i] = float(np.mean([m[2][i] for m in measurements]))
            for a_pos, a_val in anchor_list:
                if abs(a_pos - cents[i]) < 40:          # anchor near this band
                    cost += 0.5 * np.abs(v_grid - a_val)
            prof[i] = v_grid[int(np.argmin(cost))]
        # median filter kills isolated consensus glitches
        prof = ndimage.median_filter(prof, size=3, mode="nearest")
        return prof, cents

    rows, cols = {}, {}
    for r in range(8):
        ms, anch = [], []
        for c in range(8):
            if (r, c) not in grid:
                continue
            t, e, cell, ph = grid[(r, c)]
            offs, quals, cts = ph["y"]
            ms.append((offs, quals, cts, cell))
        y0 = min(e["y_dots"] for (t, e, _, _) in
                 [grid[k] for k in grid if k[0] == r])
        for a in anchors:
            if abs(a["y"] - y0) < 850 or abs(a["y"] - (y0 + 708)) < 250:
                anch.append((a["y"], a["dy_dots"]))
        rows[r] = consensus(ms, anch)
    for c in range(8):
        ms, anch = [], []
        for r in range(8):
            if (r, c) not in grid:
                continue
            t, e, cell, ph = grid[(r, c)]
            offs, quals, cts = ph["x"]
            ms.append((offs, quals, cts, cell))
        x0 = min(e["x_dots"] for (t, e, _, _) in
                 [grid[k] for k in grid if k[1] == c])
        for a in anchors:
            if abs(a["x"] - x0) < 700 or abs(a["x"] - (x0 + 496)) < 250:
                anch.append((a["x"], a["dx_dots"]))
        cols[c] = consensus(ms, anch)
    return {"rows": rows, "cols": cols}


def pooled_tile_profile(pp: dict, t: dict) -> dict:
    oy, cy = pp["rows"][t["row"]]
    ox, cx = pp["cols"][t["col"]]
    return {"off_y": oy, "y_dots": cy, "off_x": ox, "x_dots": cx}


def selfclock_cell_means(scan: dict, e: dict, cell: int, channel: str,
                         prof: dict) -> np.ndarray:
    """Cell means sampled at affine + self-clocked separable offsets."""
    arr = cc._channel_f32(scan, channel)
    coef = np.asarray(scan["affine"], np.float64)
    ny, nx = e["h_dots"] // cell, e["w_dots"] // cell
    xc = e["x_dots"] + (np.arange(nx) + 0.5) * cell
    yc = e["y_dots"] + (np.arange(ny) + 0.5) * cell
    dx = np.interp(xc, prof["x_dots"], prof["off_x"])
    dy = np.interp(yc, prof["y_dots"], prof["off_y"])
    xx = np.repeat((xc + dx)[None, :], ny, axis=0)
    yy = np.repeat((yc + dy)[:, None], nx, axis=1)
    out = np.zeros((ny, nx))
    for oy in (-0.25, 0.25):
        for ox in (-0.25, 0.25):
            xs = xx + ox * cell
            ys = yy + oy * cell
            sx = coef[0] * xs + coef[1] * ys + coef[2]
            sy = coef[3] * xs + coef[4] * ys + coef[5]
            out += ndimage.map_coordinates(arr, [sy, sx], order=1,
                                           mode="nearest")
    return out / 4.0


def phase_corrected_cell_means(scan: dict, e: dict, cell: int, channel: str,
                               pf: dict, sign: float = 1.0,
                               shift_frac: float = 0.0) -> np.ndarray:
    """Cell means sampled at affine + self-clocked lattice offsets. sign and
    shift_frac (fraction of a cell added to both axes) are FIXED geometric
    conventions of the phase estimator, calibrated once against genie warp
    and then frozen as code constants — they are not per-tile parameters."""
    from scipy.interpolate import RegularGridInterpolator

    arr = cc._channel_f32(scan, channel)
    coef = np.asarray(scan["affine"], np.float64)
    ny, nx = e["h_dots"] // cell, e["w_dots"] // cell
    xc = e["x_dots"] + (np.arange(nx) + 0.5) * cell
    yc = e["y_dots"] + (np.arange(ny) + 0.5) * cell
    xx = np.repeat(xc[None, :], ny, axis=0)
    yy = np.repeat(yc[:, None], nx, axis=1)
    px = coef[0] * xx + coef[1] * yy + coef[2]
    py = coef[3] * xx + coef[4] * yy + coef[5]
    q = np.maximum(pf["quality"], 1e-9)

    def interp(field):
        # quality-weighted smoothing then bilinear interp at cell centers
        f = ndimage.uniform_filter(field * q, size=3) / \
            ndimage.uniform_filter(q, size=3)
        gi = RegularGridInterpolator((pf["cy_px"], pf["cx_px"]), f,
                                     bounds_error=False, fill_value=None)
        return gi(np.stack([py.ravel(), px.ravel()], axis=1)).reshape(ny, nx)

    dx = sign * interp(pf["off_x_dots"]) + shift_frac * cell
    dy = sign * interp(pf["off_y_dots"]) + shift_frac * cell
    out = np.zeros((ny, nx))
    for oy in (-0.25, 0.25):                    # 2x2 subsamples per cell
        for ox in (-0.25, 0.25):
            xs = xx + dx + ox * cell
            ys = yy + dy + oy * cell
            sx = coef[0] * xs + coef[1] * ys + coef[2]
            sy = coef[3] * xs + coef[4] * ys + coef[5]
            out += ndimage.map_coordinates(arr, [sy, sx], order=1,
                                           mode="nearest")
    return out / 4.0


def dd_decode(scan: dict, e: dict, cell: int, channel: str, p_ink: float,
              n_iters: int = 2, soft: bool = True) -> dict:
    """Decision-directed decode of one (rectangular) tile region. Returns
    the final decode_cells outputs per square half plus stitched means/bits/
    llr_ctx — same stitch convention as analyze_e004.decode_rect_by_squares.

    NOTE on legality: every input is marks-affine, channel data, and the
    construction prior. GT never enters. The caller scores externally.
    """
    x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
    assert h >= w and (h - w) % cell == 0 and w % cell == 0

    # pass 0: affine-only means -> initial decisions (whole rect at once)
    m0 = affine_cell_means(scan, e, cell, channel)
    bits = amp.fixed_rate_bits(m0, p_ink)

    arr = cc._channel_f32(scan, channel)
    split = (h // 2) // cell
    off = (h - w) // cell
    sq_t = {"name": e["name"] + "#ddt", "x_dots": x, "y_dots": y,
            "w_dots": w, "h_dots": w}
    sq_b = {"name": e["name"] + "#ddb", "x_dots": x, "y_dots": y + h - w,
            "w_dots": w, "h_dots": w}
    out_t = out_b = None
    for _ in range(n_iters):
        template = cells_to_dots(bits.astype(np.uint8), cell) if cell > 1 \
            else bits.astype(np.uint8)
        kw = dict(soft=False, diagnostics=False)
        out_t = scanlab.decode_cells(arr, scan["affine"], sq_t,
                                     template[:w], cell, **kw)
        out_b = scanlab.decode_cells(arr, scan["affine"], sq_b,
                                     template[h - w:], cell, **kw)
        means = np.concatenate([np.asarray(out_t["means"])[:split],
                                np.asarray(out_b["means"])[split - off:]],
                               axis=0)
        bits = amp.fixed_rate_bits(means, p_ink)

    res = {"means": means, "bits": bits, "n_iters": n_iters}
    if soft:
        # final soft stage on the decision-templated warp (blind GMM + blind
        # 16-context detector — both label-free by construction)
        template = cells_to_dots(bits.astype(np.uint8), cell) if cell > 1 \
            else bits.astype(np.uint8)
        st = scanlab.decode_cells(arr, scan["affine"], sq_t, template[:w],
                                  cell, soft=True, diagnostics=False)
        sb = scanlab.decode_cells(arr, scan["affine"], sq_b, template[h - w:],
                                  cell, soft=True, diagnostics=False)
        res["llr_ctx"] = np.concatenate(
            [np.asarray(st["soft"]["llr_ctx"])[:split],
             np.asarray(sb["soft"]["llr_ctx"])[split - off:]], axis=0)
        res["llr"] = np.concatenate(
            [np.asarray(st["soft"]["llr"])[:split],
             np.asarray(sb["soft"]["llr"])[split - off:]], axis=0)
    return res
