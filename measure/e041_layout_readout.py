"""e041 S17 — layout reading for e041_scale_readout: which dot arrangement does a dot-mixed cell carry?

S17's overlap cells carry a LAYOUT symbol on top of their state: the orientation ("+" / "-") and phase of
their dot pattern (CMY stripes, two-toner oriented bands, c2 column / row pairs).  The manifest names, per
band, a "layout_catalogue" {state: [{"id", "orientation", "phase", "grid": cell_dots x cell_dots colour
names}, ...]} (every state has a list; the list order is the layout index) and the bands npz carries
"layouts_<band>" (per cell an index into that cell's state's list, 0 where the state has one entry).  This
module decides the layout of every cell whose state has more than one entry, WITHOUT the truth, and scores
it against layouts_<band>.

LAYOUT GIVEN STATE: the candidate set of a cell is its TRUE state's catalogue list — the figure is the layout
error given the state, beside (not compounded with) the state error the scale readout already reports.  What
enters a decision: the catalogue, the window's true states, the scan.  What never does: layouts_<band>, and
planes_<band> inside a multi-candidate cell (the dot planes are used once per band, by check_catalogue, as a
contract check that the catalogue reproduces them; the readout refuses on a mismatch).

Per window (decide_window):
1. the EXPECTED planes from the catalogue alone: single-candidate cells (solid states, W) exactly; a
   multi-candidate cell as its state's mean over the candidates (a fractional coverage, the same for every
   layout of that state);
2. POSES from the solid cells only, starting from the page fit's nominal window position (the window's own
   OR-ed pose is fitted with every cell's true dots, so it is not used): the OR-ed ink of the single-candidate
   cells registered against darkness within +/- SEARCH_MM, then per plane e041_mixture_readout.plane_poses on
   those cells' masks alone (its search radius 3 dots at any dpi).  The overlap cells stay out of the pose for
   two reasons: their dots are the unknown being decided (a template carrying them would put the truth into
   the pose), and a diagonal or stripe lattice can slip an own-mask correlation by one dot along its diagonal
   (the "-" stripes map onto themselves under a (1, -1) dot shift); a 3 x 3 block of one toner cannot slip.
   The multi-candidate cells' pixels (dilated by EXCLUDE_DOTS) are also taken out of the evidence of both
   correlations and of the unmixing fit (plane_poses' use_px), else their unmodelled ink pulls the peak (on
   the synthetic with M 1.2 px right of C: read 1.55-1.87 px with them in, 1.13-1.34 px with them out).  A
   plane whose pose comes back weak keeps the solid OR-ed pose;
3. the forward model, optical density per pixel D_ch = sum_k a_ch,k (g_sigma * t_k) + b_ch over the channels
   R, G, B, max(R, G, B) (e041_mixture_readout.density): t_k = the expected plane k rendered at its own pose,
   g_sigma a Gaussian PSF; (a, b) by least squares on the pixels of the single-candidate cells in the central
   FIT_CELLS x FIT_CELLS cells of the window (the multi-candidate cells' fractional rendering only feeds their
   neighbours' blur), sigma the best of LAYOUT_PSF_DOTS by that fit's residual;
4. per multi-candidate cell, in LAYOUT_PASSES passes: the whole window plus a one-cell ring of its band
   neighbours rendered through that model (pass 1: every multi-candidate cell at its state's candidate mean;
   later passes: the window's cells at the layout decided in the pass before, the ring at the mean), the
   residual O - prediction + the cell's own current contribution = the cell with its neighbours' modelled
   bleed removed, in its cell_px x cell_px box at the solid OR-ed pose, per-channel cell mean removed; against
   every candidate's own contribution (its dots at each plane's own pose offset inside the box, blurred by
   sigma, mixed by a, the same rendering; mean removed): the normalised correlation <R, P_j> / |P_j|, argmax.

Scores (window_scores / band_layout): layout error = decided entry != true entry; ORIENTATION error = the
decided entry's orientation differs from the true one, over cells whose state's list has more than one
orientation; PHASE error likewise over states with more than one phase value; per state the confusion over
its entries and its mutual information; the band's layout bits per cell = sum over states of MI_s x the
fraction of the band's cells in state s; combined discernible bits per cell = the state MI + that.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import ndimage

from measure.e041_gt_compare import xcorr_shift
from measure.e041_mixture_readout import PLANES, density, plane_poses, plane_search_px

LAYOUT_PSF_DOTS = (0.0, 0.5, 1.0, 1.5)   # candidate PSF sigmas of the forward model, printed dots
FIT_CELLS = 12                           # the PSF / mixing fit uses the central FIT_CELLS^2 cells of a window
EXCLUDE_DOTS = 1.0                       # multi-candidate cells leave the pose evidence dilated by this
LAYOUT_PASSES = 3                        # pass 1 neighbours at their state mean, then decision-directed
REG_MIN_PEAK = 0.25
POSE_FLAGS_USED = ("ok", "edge", "collinear")


@dataclass(frozen=True)
class Catalogue:
    """A band's layout catalogue in the band's state order: per state the candidates' ink (n, 4, cd, cd)."""
    states: tuple[str, ...]
    cell_dots: int
    masks: tuple[np.ndarray, ...]
    ids: tuple[tuple[str, ...], ...]
    orient: tuple[tuple[str | None, ...], ...]
    phase: tuple[tuple[int | None, ...], ...]

    @property
    def n_cand(self) -> np.ndarray:
        return np.array([len(m) for m in self.masks], np.int64)

    def has_axis(self) -> bool:
        return bool((self.n_cand > 1).any())

    def orient_axis(self, s: int) -> bool:
        return len(set(self.orient[s])) > 1

    def phase_axis(self, s: int) -> bool:
        return len(set(self.phase[s])) > 1


# ---------------------------------------------------------------- catalogue

def colour_planes(name: str) -> tuple[int, ...]:
    """Plane indices a catalogue colour name inks: the letters C, M, Y, K of its name before any '-' suffix
    ("C-solid" -> C, "M-corner" -> M, "CM" -> C and M); "W" none.  A "K" is the K plane (toner black)."""
    base = str(name).split("-")[0].upper()
    if base in ("", "W"):
        return ()
    out = tuple(PLANES.index(ch) for ch in "CMYK" if ch in base)
    if not out:
        raise SystemExit(f"layout catalogue colour {name!r}: no C, M, Y or K in its name — contract fork")
    return out


def catalogue_of(b: dict[str, Any], states: list[str]) -> Catalogue | None:
    """The band's "layout_catalogue" (a dict, or its repr string) in state order; None when absent."""
    raw = b.get("layout_catalogue")
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = ast.literal_eval(raw)
    cd = int(b["cell_dots"])
    masks, ids, orient, phase = [], [], [], []
    for s in states:
        ents = raw.get(s)
        if not ents:
            raise SystemExit(f"band {b['name']}: layout_catalogue has no entry for state {s!r} — "
                             "contract fork")
        m = np.zeros((len(ents), 4, cd, cd), np.uint8)
        for j, e in enumerate(ents):
            g = e["grid"]
            if len(g) != cd or any(len(row) != cd for row in g):
                raise SystemExit(f"band {b['name']}: state {s} entry {j} grid is not {cd} x {cd}")
            for r in range(cd):
                for c in range(cd):
                    for k in colour_planes(g[r][c]):
                        m[j, k, r, c] = 1
        flat = m.reshape(len(ents), -1)
        if len({row.tobytes() for row in flat}) < len(ents):
            print(f"  warning: band {b['name']} state {s}: two catalogue entries print the same dots")
        masks.append(m)
        ids.append(tuple(str(e.get("id", j)) for j, e in enumerate(ents)))
        orient.append(tuple(e.get("orientation") for e in ents))
        phase.append(tuple(e.get("phase") for e in ents))
    return Catalogue(tuple(states), cd, tuple(masks), tuple(ids), tuple(orient), tuple(phase))


def layouts_of(npz: Any, b: dict[str, Any], shape: tuple[int, ...]) -> np.ndarray | None:
    for key in (b.get("band"), b.get("name")):
        if key is not None and f"layouts_{key}" in npz:
            arr = np.asarray(npz[f"layouts_{key}"], np.uint8)
            if arr.shape != tuple(shape):
                raise SystemExit(f"band {b['name']}: layouts {arr.shape} vs states {shape} — contract fork")
            return arr
    return None


def check_catalogue(cat: Catalogue, states: np.ndarray, layouts: np.ndarray, planes: np.ndarray) -> int:
    """The contract check: cells whose catalogue entry (state, layout) does not reproduce planes_<band>."""
    n = cat.n_cand
    if (layouts.astype(np.int64) >= n[states]).any():
        raise SystemExit("layouts index beyond its state's catalogue list — contract fork")
    cd = cat.cell_dots
    lut = np.zeros((len(cat.states), int(n.max()), 4, cd, cd), np.uint8)
    for s, m in enumerate(cat.masks):
        lut[s, :len(m)] = m
    R, C = states.shape
    got = planes[:, :R * cd, :C * cd].reshape(4, R, cd, C, cd).transpose(1, 3, 0, 2, 4)
    return int((lut[states, layouts] != got).any(axis=(2, 3, 4)).sum())


def ring_states(states: np.ndarray, r0: int, c0: int, cells: int) -> np.ndarray:
    """The window's states with a one-cell ring of its band neighbours, (cells + 2)^2; -1 outside the band
    (white: the bands sit in white gaps)."""
    R, C = states.shape
    out = np.full((cells + 2, cells + 2), -1, np.int64)
    ya, yb, xa, xb = max(0, r0 - 1), min(R, r0 + cells + 1), max(0, c0 - 1), min(C, c0 + cells + 1)
    out[ya - r0 + 1:yb - r0 + 1, xa - c0 + 1:xb - c0 + 1] = states[ya:yb, xa:xb]
    return out


def cell_lut(cat: Catalogue) -> tuple[np.ndarray, np.ndarray]:
    """(mean (S + 1, 4, cd, cd): each state's mean over its candidates, row S = white for index -1;
    masks (S + 1, nmax, 4, cd, cd) float32: every candidate, padded with white)."""
    cd = cat.cell_dots
    S, nmax = len(cat.states), int(cat.n_cand.max())
    masks = np.zeros((S + 1, nmax, 4, cd, cd), np.float32)
    mean = np.zeros((S + 1, 4, cd, cd), np.float32)
    for s, m in enumerate(cat.masks):
        masks[s, :len(m)] = m
        mean[s] = m.mean(0)
    return mean, masks


def tile_cells(blk: np.ndarray) -> np.ndarray:
    """(R, C, 4, cd, cd) per-cell planes -> (4, R cd, C cd)."""
    R, C, _, cd, _ = blk.shape
    return blk.transpose(2, 0, 3, 1, 4).reshape(4, R * cd, C * cd)


def place_any(t: np.ndarray, py: float, px: float, size: int) -> np.ndarray:
    """t on a (size, size) zero canvas with its top-left at (py, px), any sign, bilinear sub-pixel (the same
    interpolation as e041_mixture_readout.place's order-1 shift, by four weighted slices), cropped."""
    iy, ix = int(np.floor(py)), int(np.floor(px))
    fy, fx = py - iy, px - ix
    h, w = t.shape
    tp = np.zeros((h + 1, w + 1), np.float32)
    tp[:h, :w] += (1 - fy) * (1 - fx) * t
    tp[1:, :w] += fy * (1 - fx) * t
    tp[:h, 1:] += (1 - fy) * fx * t
    tp[1:, 1:] += fy * fx * t
    canvas = np.zeros((size, size), np.float32)
    ya, yb, xa, xb = max(0, iy), min(size, iy + h + 1), max(0, ix), min(size, ix + w + 1)
    if ya < yb and xa < xb:
        canvas[ya:yb, xa:xb] = tp[ya - iy:yb - iy, xa - ix:xb - ix]
    return canvas


# ---------------------------------------------------------------- per window

def solid_poses(rect: np.ndarray, solid: np.ndarray, multi_ext: np.ndarray, sub: int, s_px: int, p_px: int,
                white: np.ndarray, nominal: tuple[float, float]) -> tuple[float, float, float,
                                                                          dict[int, tuple[float, float]],
                                                                          dict[str, Any]]:
    """(oy, ox, peak, pose per plane index, flags): the solid cells' OR-ed pose and their per-plane poses,
    from the page fit's nominal window position (never the window's own OR-ed pose: that one is fitted
    with every cell's true dots).  The OR-ed correlation runs twice — on all pixels, then with the
    multi-candidate cells (multi_ext, with the one-cell ring; dilated by EXCLUDE_DOTS) placed at the first
    result and their pixels set to the image mean — and plane_poses takes the same exclusion at the final
    OR-ed pose (use_px): ink the solid template does not model would pull the peak toward it (measured on
    the synthetic: M - C read 1.55-1.87 px for a true 1.2 px with it in)."""
    cd = solid.shape[1] // (multi_ext.shape[0] - 2)
    cell_px = cd * sub
    size = rect.shape[0]

    def usable(oy: float, ox: float) -> np.ndarray:
        m = place_any(np.kron(multi_ext.astype(np.float32), np.ones((cell_px, cell_px), np.float32)),
                      oy - cell_px, ox - cell_px, size) > 0
        return ~ndimage.binary_dilation(m, iterations=int(round(EXCLUDE_DOTS * sub)))
    ink = np.kron(solid.max(0), np.ones((sub, sub), np.float32))
    dark0 = 255.0 - rect.min(axis=2)
    oy, ox, peak = nominal[0], nominal[1], float("nan")
    for use in (None, True):
        dark = dark0
        if use is not None:
            u = usable(oy, ox)
            dark = np.where(u, dark0, dark0[u].mean())
        if p_px:
            dark = dark[p_px:-p_px, p_px:-p_px]
        dy, dx, peak = xcorr_shift(dark, ink, s_px)
        oy, ox = (dy + p_px, dx + p_px) if peak >= REG_MIN_PEAK else nominal
    poses = plane_poses(rect, (solid > 0.5).astype(np.uint8), oy, ox, white, plane_search_px(sub), sub,
                        use_px=usable(oy, ox))
    out, flags = {}, {}
    for k, pl in enumerate(PLANES):
        q = poses.get(pl)
        flags[pl] = q["flag"] if q else "absent"
        out[k] = (q["oy"], q["ox"]) if q and q["flag"] in POSE_FLAGS_USED else (oy, ox)
    return oy, ox, float(peak), out, flags


def blurred(t: np.ndarray, sig_px: float) -> np.ndarray:
    return ndimage.gaussian_filter(t, sig_px, mode="constant") if sig_px > 0 else t


def fit_forward(D: np.ndarray, T: list[np.ndarray], sel: np.ndarray, sub: int) -> tuple[np.ndarray, float]:
    """(a (4, len(T)), sigma in dots): mixing matrix and PSF of D = sum_k a_k g_sigma * T_k + b by least
    squares on the pixels sel (all arrays already cropped to the fit box), sigma the best of
    LAYOUT_PSF_DOTS."""
    y = D[sel].astype(np.float64)
    best: tuple[float, np.ndarray, float] = (np.inf, np.zeros((4, len(T))), 0.0)
    for sig in LAYOUT_PSF_DOTS:
        cols = [blurred(t, sig * sub)[sel] for t in T]
        X = np.stack(cols + [np.ones(int(sel.sum()), np.float32)], 1).astype(np.float64)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        r = float(((X @ coef - y) ** 2).sum())
        if r < best[0]:
            best = (r, coef[:-1].T, sig)
    return best[1], best[2]


def candidate_patches(masks: np.ndarray, a: np.ndarray, model: list[int],
                      delta: dict[int, tuple[float, float]], sig: float, sub: int) -> np.ndarray:
    """(n, cell_px, cell_px, 4): each candidate's own density contribution inside its cell box (its dots at
    each plane's pose offset delta, blurred by sigma, mixed by a) — the same rendering as the window's."""
    n, _, cd, _ = masks.shape
    cell_px = cd * sub
    pad = int(np.ceil(4 * sig * sub + max(max(abs(v) for v in d) for d in delta.values()) + 2))
    size = cell_px + 2 * pad
    blk = np.ones((sub, sub), np.float32)
    out = np.zeros((n, cell_px, cell_px, 4), np.float64)
    for i in range(n):
        for j, k in enumerate(model):
            if masks[i, k].any():
                t = blurred(place_any(np.kron(masks[i, k], blk), pad + delta[k][0], pad + delta[k][1], size),
                            sig * sub)
                out[i] += t[pad:pad + cell_px, pad:pad + cell_px, None] * a[None, None, :, j]
    return out


def decide_window(rect: np.ndarray, st_ext: np.ndarray, cat: Catalogue, sub: int, s_px: int, p_px: int,
                  white: np.ndarray, nominal: tuple[float, float]) -> tuple[np.ndarray, dict[str, Any]]:
    """(decided layout per cell, -1 on single-candidate cells; info).  rect = the window resampled at sub px
    per dot with s_px + p_px of margin on every side (e041_scale_readout.read_window); st_ext = the window's
    true states with a one-cell ring of band neighbours (ring_states); nominal = the window's top-left in
    rect px by the page fit alone.

    Each pass renders the whole window (and its ring) through the forward model — pass 1 every
    multi-candidate cell at its state's candidate mean, later passes the window's own cells at the layout
    decided in the pass before (the ring stays at the mean) — and a cell is decided on the residual
    O - (prediction - the cell's own current contribution), i.e. its neighbours' modelled bleed removed;
    per-channel cell mean removed, normalised correlation with each candidate, argmax."""
    cd = cat.cell_dots
    cells = st_ext.shape[0] - 2
    cell_px = cd * sub
    size = rect.shape[0]
    st = st_ext[1:-1, 1:-1]
    mean_lut, mask_lut = cell_lut(cat)
    n_cand = np.append(cat.n_cand, 1)
    single_ext = n_cand[st_ext] == 1
    E = tile_cells(mean_lut[st_ext])                                            # (4, (cells+2) cd, ...)
    solid = (E * np.kron(single_ext, np.ones((cd, cd)))[None])[:, cd:-cd, cd:-cd]
    oy, ox, peak, pose, flags = solid_poses(rect, solid, ~single_ext, sub, s_px, p_px, white, nominal)
    D = density(rect, white)
    model = [k for k in range(4) if E[k].max() > 0]
    blk = np.ones((sub, sub), np.float32)

    def planes_at(E: np.ndarray) -> list[np.ndarray]:
        return [place_any(np.kron(E[k], blk), pose[k][0] - cell_px, pose[k][1] - cell_px, size)
                for k in model]
    T = planes_at(E)
    single_px = place_any(np.kron(single_ext.astype(np.float32), np.ones((cell_px, cell_px), np.float32)),
                          oy - cell_px, ox - cell_px, size) > 0.5
    i0 = max(0, (cells - FIT_CELLS) // 2)
    i1 = min(cells, i0 + FIT_CELLS)
    margin = int(np.ceil(4 * max(LAYOUT_PSF_DOTS) * sub)) + sub
    r0, r1 = max(0, int(oy) + i0 * cell_px - margin), min(size, int(oy) + i1 * cell_px + margin)
    c0, c1 = max(0, int(ox) + i0 * cell_px - margin), min(size, int(ox) + i1 * cell_px + margin)
    a, sig = fit_forward(D[r0:r1, c0:c1], [t[r0:r1, c0:c1] for t in T], single_px[r0:r1, c0:c1], sub)
    iy0, ix0 = int(round(oy)), int(round(ox))
    if iy0 < 0 or ix0 < 0 or iy0 + cells * cell_px > size or ix0 + cells * cell_px > size:
        raise ValueError("layout cell grid outside the resampled rect")
    delta = {k: (pose[k][0] - iy0, pose[k][1] - ix0) for k in model}
    multi = [s for s in range(len(cat.states)) if cat.n_cand[s] > 1 and (st == s).any()]
    cand = {s: candidate_patches(mask_lut[s, :cat.n_cand[s]], a, model, delta, sig, sub) for s in multi}
    unit = {}
    for s, P in cand.items():
        Pm = (P - P.mean(axis=(1, 2), keepdims=True)).reshape(len(P), -1)
        unit[s] = Pm / (np.linalg.norm(Pm, axis=1, keepdims=True) + 1e-12)
    dec = np.full(st.shape, -1, np.int16)
    changed = []
    for it in range(LAYOUT_PASSES):
        if it:
            blk_e = mean_lut[st_ext].copy()
            inner = blk_e[1:-1, 1:-1]
            own = dec >= 0
            inner[own] = mask_lut[st[own], dec[own]]
            T = planes_at(tile_cells(blk_e))
        pred = np.zeros((size, size, 4), np.float32)
        for j, t in enumerate(T):
            pred += blurred(t, sig * sub)[..., None] * a[:, j].astype(np.float32)
        res = (D - pred)[iy0:iy0 + cells * cell_px, ix0:ix0 + cells * cell_px].astype(np.float64)
        res = res.reshape(cells, cell_px, cells, cell_px, 4).transpose(0, 2, 1, 3, 4)
        new = dec.copy()
        for s in multi:
            sel = st == s
            P = cand[s]
            own_c = P.mean(0)[None] if it == 0 else P[dec[sel]]
            R = res[sel] + own_c
            R -= R.mean(axis=(1, 2), keepdims=True)
            new[sel] = np.argmax(R.reshape(len(R), -1) @ unit[s].T, axis=1)
        changed.append(int((new != dec).sum()) if it else 0)
        dec = new
    info = {"psf_dots": sig, "solid_reg_peak": peak, "solid_pose_flags": flags,
            "solid_dy_px": oy - nominal[0], "solid_dx_px": ox - nominal[1], "pass_changes": changed,
            "plane_delta_px": {PLANES[k]: [round(float(v), 3) for v in delta[k]] for k in model}}
    return dec, info


# ---------------------------------------------------------------- scores

def mutual_info_bits(conf: np.ndarray) -> float:
    """Empirical I(true; predicted) in bits per cell from a confusion matrix of counts."""
    p = conf / max(conf.sum(), 1)
    pt, pp = p.sum(1, keepdims=True), p.sum(0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(p > 0, p * np.log2(p / (pt @ pp)), 0.0)
    return float(t.sum())


def marginal_errors(cat: Catalogue, y_s: np.ndarray, y_l: np.ndarray, d: np.ndarray) -> dict[str, Any]:
    """Layout / orientation / phase error over multi-candidate cells (flat arrays), with their counts."""
    multi = cat.n_cand[y_s] > 1
    out: dict[str, Any] = {"n": int(multi.sum())}
    out["err"] = float((d[multi] != y_l[multi]).mean()) if out["n"] else float("nan")
    for key, axis, attr in (("orient", cat.orient_axis, cat.orient), ("phase", cat.phase_axis, cat.phase)):
        wrong = n = 0
        for s in range(len(cat.states)):
            sel = multi & (y_s == s)
            if not sel.any() or not axis(s):
                continue
            vals = np.array([str(v) for v in attr[s]], object)
            wrong += int((vals[d[sel]] != vals[y_l[sel]]).sum())
            n += int(sel.sum())
        out[f"n_{key}"] = n
        out[f"{key}_err"] = wrong / n if n else float("nan")
    return out


def window_scores(cat: Catalogue, st: np.ndarray, lt: np.ndarray, dec: np.ndarray) -> dict[str, Any]:
    y_s, y_l, d = st.ravel().astype(np.int64), lt.ravel().astype(np.int64), dec.ravel().astype(np.int64)
    m = marginal_errors(cat, y_s, y_l, d)
    multi = cat.n_cand[y_s] > 1
    return {"layout_err": m["err"], "orient_err": m["orient_err"], "phase_err": m["phase_err"],
            "n_layout_cells": m["n"], "_lay": (y_s[multi], y_l[multi], d[multi])}


def band_layout(cat: Catalogue, rows: list[dict[str, Any]], mi_state: dict[str, float],
                cells_per_mm2: float) -> dict[str, Any]:
    """Pooled over the band's windows: marginal errors, per state confusion and MI, layout bits per cell
    (sum_s MI_s x fraction of cells in s) and the combined bits per cell / mm^2 for every state MI given."""
    lay = [r for r in rows if "_lay" in r]
    y_s = np.concatenate([r["_lay"][0] for r in lay])
    y_l = np.concatenate([r["_lay"][1] for r in lay])
    d = np.concatenate([r["_lay"][2] for r in lay])
    all_states = np.concatenate([r["_y"] for r in lay])
    n_all = max(len(all_states), 1)
    out = marginal_errors(cat, y_s, y_l, d)
    per, bits = {}, 0.0
    for s, name in enumerate(cat.states):
        n = int(cat.n_cand[s])
        if n < 2:
            continue
        sel = y_s == s
        conf = np.zeros((n, n), np.int64)
        np.add.at(conf, (y_l[sel], d[sel]), 1)
        mi = mutual_info_bits(conf.astype(np.float64))
        frac = float((all_states == s).sum()) / n_all
        bits += mi * frac
        m = marginal_errors(cat, y_s[sel], y_l[sel], d[sel])
        per[name] = {"n": int(sel.sum()), "fraction_of_cells": frac, "err": m["err"],
                     "orient_err": m["orient_err"], "phase_err": m["phase_err"], "mi_bits": mi,
                     "raw_bits": float(np.log2(n)), "ids": list(cat.ids[s]), "confusion": conf.tolist()}
    out["per_state"] = per
    out["mi_layout_bits_per_cell"] = bits
    for key, mi in mi_state.items():
        out[f"combined_{key}_bits_per_cell"] = mi + bits
        out[f"combined_{key}_bits_per_mm2"] = (mi + bits) * cells_per_mm2
    out["windows"] = len(lay)
    out["psf_dots_median"] = float(np.median([r["layout_info"]["psf_dots"] for r in lay]))
    return out
