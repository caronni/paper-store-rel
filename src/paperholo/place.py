"""L2 fragment placement (edge F13): sub-grain confetti localization.

Places a fragment's oriented hard-bit grid on the volume by correlating its
pilot cells against the seed-PREDICTED pilot value field (PILOTS-DESIGN
§15.3) — blind-legal: predictions come from the pilot layer alone (site
pattern + window code + value keystream), never from payload content. One
FFT cross-correlation per (page, rotation) scores EVERY cell offset at
once; the support-aware normal deviate z = corr/sqrt(support) makes scores
comparable across partial-overlap offsets (§15.4). The decoy floor of the
mismatch statistic is the value layer's pairwise codeword-distance
spectrum (measured min 32/100, 014.4) — hence the §15.4 gate constants:
best mismatch < 0.15, every rival > 0.20.

Scope (v1): integer cell offsets x rot90 on-page ('valid' correlation —
fragments fully inside a page); fine angle/pitch must come from the
fragment's own lattice lock. Session pruning via pending_cell_mask
restricts candidate offsets to windows overlapping un-certified LDPC
tiles (F13's decode-state conditioning).

§15.6 amendment (2026-07-11, opt-in): allow_overhang=True pads the
pilot field per (page, rot) hypothesis so fragments overhanging the
page edge can place (018.2: a page-bottom-edge piece's true origin sat
outside the 'valid' search space BY CONSTRUCTION — real scissors always
produce margin-bearing edge pieces). Off-page cells carry zero pilot
sites, so score/support semantics are unchanged; origins may then be
negative — downstream consumers clip via overlap_slices(). Padding only
ENLARGES the rival candidate set (gate moves toward refusal, never
toward false accept); default stays False to preserve the frozen-gate
provenance of existing session drivers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np
from scipy.signal import fftconvolve

from .pilots import encode_word, site_positions_tile

if TYPE_CHECKING:  # pragma: no cover
    from .compose import ComposeSpec

_FIELD_CACHE: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}

EXCLUDE_RADIUS_CELLS = 3   # peak-shoulder exclusion when hunting the rival
GATE_TRUE = 0.15           # §15.4 (i): best candidate mismatch bar
GATE_DECOY = 0.20          # §15.4 (ii): every rival above this (d-floor aware)


def pilot_field(spec: "ComposeSpec", seed: bytes, page: int
                ) -> tuple[np.ndarray, np.ndarray]:
    """(values uint8, site mask bool) over the full page cell grid.

    Seed-derived only (site pattern + scrambled window codewords) — the
    fragment placer's reference is legal even for never-decoded regions.
    Pilot tiles whose v3 counter would overflow are left empty (mask 0),
    matching the composer. Cached per (seed, plane, page, layout, shape).
    """
    key = (seed, spec.plane, page, spec.pilot.version,
           tuple(spec.page_cells_yx))
    if key in _FIELD_CACHE:
        return _FIELD_CACHE[key]
    if len(_FIELD_CACHE) >= 16:   # ~15 MB/page measured — bound the cache
        _FIELD_CACHE.pop(next(iter(_FIELD_CACHE)))
    p = spec.pilot.period_cells
    ty_n = spec.page_cells_yx[0] // p
    tx_n = spec.page_cells_yx[1] // p
    geo = ({} if spec.pilot.version == 2
           else {"tiles_x": tx_n, "tiles_per_page": ty_n * tx_n})
    pos = site_positions_tile(spec.pilot, seed)
    vals = np.zeros(tuple(spec.page_cells_yx), np.uint8)
    mask = np.zeros(tuple(spec.page_cells_yx), bool)
    for ty in range(ty_n):
        for tx in range(tx_n):
            try:
                w = encode_word(spec.pilot, seed, spec.plane, page, ty, tx,
                                **geo)
            except ValueError:
                continue  # v3 last-page counter overflow: tile carries none
            yy = ty * p + pos[:, 0]
            xx = tx * p + pos[:, 1]
            vals[yy, xx] = w
            mask[yy, xx] = True
    _FIELD_CACHE[key] = (vals, mask)
    return vals, mask


def overlap_slices(origin_yx: tuple[int, int], rot_shape: tuple[int, int],
                   page_shape: tuple[int, int]
                   ) -> tuple[slice, slice, slice, slice] | None:
    """Clip a (possibly overhanging) placement to the page: returns
    (page_y, page_x, frag_y, frag_x) slices in the ROTATED fragment
    frame, or None when the overlap is empty. Handles negative origins
    (§15.6 padded search) and far-edge overhang uniformly — every
    consumer of origin_yx must go through this once overhang is legal."""
    oy, ox = origin_yx
    H, W = page_shape
    h, w = rot_shape
    py0, px0 = max(0, oy), max(0, ox)
    py1, px1 = min(H, oy + h), min(W, ox + w)
    if py0 >= py1 or px0 >= px1:
        return None
    return (slice(py0, py1), slice(px0, px1),
            slice(py0 - oy, py1 - oy), slice(px0 - ox, px1 - ox))


def fragment_pilot_sites(pl: "Placement", grid_shape: tuple,
                         kmask: np.ndarray, spec: "ComposeSpec",
                         seed: bytes) -> tuple[np.ndarray, np.ndarray]:
    """Pilot sites inside a placed fragment, in the FRAGMENT's own grid
    frame: (int (i, j) array, printed site values). The seed-predicted
    pilot field is the label source for post-placement refinement and
    recalibration (F10 at piece scale) — blind-legal, pilot layer only.
    Overhanging placements (§15.6) contribute only their on-page part."""
    vals, smask = pilot_field(spec, seed, pl.page)
    kr = np.rot90(kmask, pl.rot_k)
    sl = overlap_slices(pl.origin_yx, kr.shape, vals.shape)
    if sl is None:
        return np.zeros((0, 2), np.int64), np.zeros(0, np.uint8)
    pys, pxs, fys, fxs = sl
    sel = np.zeros(kr.shape, bool)
    sel[fys, fxs] = smask[pys, pxs] & kr[fys, fxs]
    ys, xs = np.nonzero(sel)
    vfull = np.zeros(kr.shape, np.uint8)
    vfull[fys, fxs] = vals[pys, pxs]
    v = vfull[ys, xs]
    vi = np.full(kr.shape, -1, np.int64)
    vi[ys, xs] = np.arange(ys.size)
    vb = np.rot90(vi, -pl.rot_k)
    iy, ix = np.nonzero(vb >= 0)
    order = vb[iy, ix]
    return np.stack([iy, ix], 1), v[order]


def _box_sum(a: np.ndarray, h: int, w: int) -> np.ndarray:
    """Sliding (h, w) window sums of a 2-D array, 'valid' footing (exact)."""
    c = np.cumsum(np.cumsum(np.asarray(a, np.float64), axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    return (c[h:, w:] - c[:-h, w:] - c[h:, :-w] + c[:-h, :-w])


@dataclass
class Placement:
    """place_fragment result. ok = passed the §15.4 gate."""
    ok: bool
    page: int | None = None
    origin_yx: tuple[int, int] | None = None
    rot_k: int | None = None
    mismatch: float = 1.0
    support: int = 0
    z: float = 0.0
    rival_mismatch: float = 1.0
    rival_z: float = 0.0
    z_gap: float = 0.0
    diagnostics: dict = field(default_factory=dict)


def place_fragment(bits: np.ndarray, spec: "ComposeSpec", seed: bytes, *,
                   mask: np.ndarray | None = None,
                   pages: tuple[int, ...] = (0,),
                   pending_cell_mask: dict[int, np.ndarray] | None = None,
                   min_support: int = 20,
                   gate_true: float = GATE_TRUE,
                   gate_decoy: float = GATE_DECOY,
                   allow_overhang: bool = False) -> Placement:
    """Place one fragment (oriented hard-bit grid, any rot90) on the volume.

    mask: optional bool grid (bits' shape) — True = piece interior; cells
    outside are ignored for both score and support (torn/irregular pieces,
    §15.2: without it, background inside the bounding box dilutes the
    mismatch past the gate). pending_cell_mask: optional {page: bool cell
    grid} — candidate offsets
    are kept only where the fragment window overlaps a pending cell (the
    F13 pruning; also what makes a wrong-region placement impossible by
    construction when the mask is trusted). Gate per §15.4: best mismatch
    < gate_true AND best rival (outside a ±3-cell shoulder, across all
    pages/rotations) > gate_decoy. z_gap is reported, not yet gated — its
    freeze needs the fresh-window validation (§15.4 iii).

    allow_overhang (§15.6, opt-in): zero-pad the pilot field per (page,
    rot) hypothesis so page-edge fragments place; origin_yx may then be
    NEGATIVE — consumers must clip via overlap_slices(). Off-page cells
    carry no sites (zero score, zero support), and min_support prunes
    mostly-off-page offsets. Default False: the frozen §15.4 gate
    provenance (016.4/016.7, 'valid' search) is preserved for existing
    drivers; padded-regime decoy behavior is validated separately.
    """
    b = np.asarray(bits, np.uint8)
    if b.ndim != 2:
        raise ValueError(f"bits must be 2-D, got {b.shape}")
    r = EXCLUDE_RADIUS_CELLS
    # Streaming top candidates: full-page score maps are transient per
    # hypothesis (a volume search must not retain 4*pages maps — measured
    # ~167 MB each on the e014 page; 2026-07-10 review finding). Per
    # hypothesis keep only its top peak and its second peak OUTSIDE a
    # +-EXCLUDE_RADIUS shoulder of the top — exactly what the rival rule
    # reads: the rival of the global best is the max of every other
    # hypothesis's top and the best hypothesis's own second peak.
    best: dict | None = None
    n_hyp = 0
    tops: list[dict] = []
    for page in pages:
        vals, smask = pilot_field(spec, seed, page)
        phat = np.where(smask, 1.0 - 2.0 * vals.astype(np.float32),
                        0.0).astype(np.float32)
        pend_ok = None
        for k in range(4):
            bk = np.rot90(b, k)
            ph = pw = 0
            phat_k, smask_k = phat, smask
            if allow_overhang:
                # §15.6 padded hypothesis: origins - pad .. H-1 legal
                ph, pw = bk.shape[0] - 1, bk.shape[1] - 1
                phat_k = np.pad(phat, ((ph, ph), (pw, pw)))
                smask_k = np.pad(smask, ((ph, ph), (pw, pw)))
            elif (bk.shape[0] > phat.shape[0]
                    or bk.shape[1] > phat.shape[1]):
                continue
            o = (1.0 - 2.0 * bk.astype(np.float32))
            if mask is not None:
                mk = np.rot90(mask, k).astype(np.float32)
                o = o * mk
                supp = np.round(fftconvolve(
                    smask_k.astype(np.float32), mk[::-1, ::-1],
                    mode="valid")).astype(np.float32)
            else:
                supp = _box_sum(smask_k, bk.shape[0], bk.shape[1]
                                ).astype(np.float32)
            corr = fftconvolve(phat_k, o[::-1, ::-1], mode="valid")
            with np.errstate(divide="ignore", invalid="ignore"):
                mism = (supp - corr) / (2.0 * supp)
                z = corr / np.sqrt(supp)
            bad = supp < min_support
            if pending_cell_mask is not None:
                pm = pending_cell_mask.get(page)
                if pm is None:
                    bad = np.ones_like(bad)
                else:
                    if pend_ok is None or pend_ok.shape != bad.shape:
                        pm_k = (np.pad(pm, ((ph, ph), (pw, pw)))
                                if allow_overhang else pm)
                        pend_ok = _box_sum(pm_k, bk.shape[0],
                                           bk.shape[1]) > 0
                    bad = bad | ~pend_ok
            z = np.where(bad, -np.inf, z)
            n_hyp += 1
            i = int(np.argmax(z))
            oy, ox = np.unravel_index(i, z.shape)
            if not np.isfinite(z[oy, ox]):
                continue
            top = {"page": page, "rot_k": k,
                   "oy": int(oy) - ph, "ox": int(ox) - pw,
                   "z": float(z[oy, ox]), "mism": float(mism[oy, ox]),
                   "supp": int(supp[oy, ox])}
            z[max(0, oy - r):oy + r + 1, max(0, ox - r):ox + r + 1] = -np.inf
            i2 = int(np.argmax(z))
            oy2, ox2 = np.unravel_index(i2, z.shape)
            if np.isfinite(z[oy2, ox2]):
                top["z2"] = float(z[oy2, ox2])
                top["mism2"] = float(mism[oy2, ox2])
            tops.append(top)
            if best is None or top["z"] > best["z"]:
                best = top
    if best is None:
        return Placement(ok=False, diagnostics={"reason": "no_candidates"})
    rival_z, rival_mism = -np.inf, 1.0
    for h in tops:
        if h is best:
            if "z2" in h and h["z2"] > rival_z:
                rival_z, rival_mism = h["z2"], h["mism2"]
        elif h["z"] > rival_z:
            rival_z, rival_mism = h["z"], h["mism"]
    ok = (best["mism"] < gate_true and rival_mism > gate_decoy)
    return Placement(
        ok=bool(ok), page=best["page"],
        origin_yx=(best["oy"], best["ox"]), rot_k=best["rot_k"],
        mismatch=best["mism"], support=best["supp"], z=best["z"],
        rival_mismatch=rival_mism, rival_z=rival_z,
        z_gap=best["z"] - rival_z if np.isfinite(rival_z) else float("inf"),
        diagnostics={"n_hypotheses": n_hyp,
                     "allow_overhang": bool(allow_overhang)})
