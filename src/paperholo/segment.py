"""Segmentation + alignment front end for fragment sessions (PILOTS-DESIGN
§15.2): split one glass image into de-rotated per-piece sub-images, each
then ingested as a tiny page by the unchanged per-scan pipeline.

Doctrine implemented here: backing-agnostic foreground statistic (the
~50%-coverage scrambled field reads mid-grey against either lid; backing
auto-estimated from the border), conservative-core + GROW-OUT masks
(over-include, never under-include), and lattice-angle alignment (the
gradient-spectrum annulus at the known cell pitch — torn shapes have no
meaningful rectangle angle).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

FG_DELTA = 25.0          # |cell-scale mean - backing| foreground threshold
GROW_CELLS = 3           # grow-out beyond the confident core (§15.2b)
MIN_AREA_MM2 = 9.0       # discard specks below ~3x3 mm (sub-floor anyway)

# ---- lattice-candidate acquisition (exp-019 texture detector) ----
# Detects cell-scale MODULATION, not brightness — a payload field is the only
# thing on the platen that varies at the cell pitch; blank paper margins and
# the backing are homogeneous and carry no bits by definition.
STD_WIN_CELLS = 2.0      # texture window in CELLS. Multi-cell = phase-
#                          independent (a solid c3 cell is uniform, so a 1-cell
#                          window only reads modulation via boundary misalign-
#                          ment; exp-019 measured field-std p10 10->32 going
#                          1->2 cells). Cost is flat in window size
#                          (uniform_filter is O(N)); the cost lever is dpi.
STD_HI = 22.0            # hysteresis STRICT seed  (definitely a lattice cell)
STD_LO = 8.0             # hysteresis LOOSE grow (joins iff connected to a
#                          seed). Calibrated on real e018 (native 24 px/cell):
#                          field std median 30 / p10 10; lid std median 1.1 /
#                          p90 8.7. Connectivity lets std_lo sit low without
#                          seeding lid noise.
GRAIN_MM = 6.0           # self-placement floor (016.7 correlation grain): a
#                          candidate smaller than this cannot be localized from
#                          its own pilots in isolation -> needs optical jigsaw.
SEED_ERODE = 2           # erode the strict seed before growth. A field's seed
#                          CORE is solid (~98% of cells > STD_HI on real toner)
#                          and survives; a thin high-std EDGE line (torn-paper
#                          margin, scrap-edge step) has no solid core and
#                          vanishes -> no thin-sliver false candidates. This is
#                          the SHAPE discriminant (field solid / edge thin) done
#                          in the seed domain. Scale with win_cells if changed.
MIN_MED_STD = 25.0       # signal-strength gate: a candidate's MEDIAN cell
#                          modulation must be field-like. Measured on confetti-1
#                          (native): 17 real fields 37.4-44.4, a lid/edge
#                          artifact 12.2 -> 25 sits in the gap with wide margin
#                          both ways. Kills weakly-modulated blobs seed_erode
#                          (a thin-shape gate) leaves behind.


@dataclass
class Piece:
    """One segmented, de-rotated fragment ready for per-piece ingestion."""
    img: np.ndarray          # float32 glass greys, counter-rotated
    mask: np.ndarray         # bool, counter-rotated, True = piece (grown)
    angle_deg: float         # lattice angle removed (mod 90, in (-45,45])
    bbox_glass: tuple[int, int, int, int]   # y0, x0, h, w pre-rotation
    area_mm2: float
    img_glass: np.ndarray | None = None     # UNROTATED crop — the refine
    mask_glass: np.ndarray | None = None    # chain samples original pixels


@dataclass
class LatticeCandidate:
    """One candidate payload-lattice region on the platen — a connected patch
    of cell-scale MODULATION (exp-019). Raw glass frame; NO angle/pitch/pilot
    processing (those are downstream stages). `mask` over-includes the field
    by the hysteresis boundary (~1 cell at the default 2-cell window)."""
    mask: np.ndarray                     # bool, glass-crop frame, True = lattice
    bbox: tuple[int, int, int, int]      # y0, x0, h, w in glass px
    area_mm2: float
    n_cells: int                         # detected lattice cells
    med_std: float                       # median cell modulation (real field ~40)
    sub_grain: bool                      # < GRAIN_MM: un-addressable in isolation


def estimate_backing(img: np.ndarray, border_px: int = 32) -> float:
    """Median grey of the image border = the backing (lid or sheet)."""
    b = np.concatenate([
        img[:border_px].ravel(), img[-border_px:].ravel(),
        img[:, :border_px].ravel(), img[:, -border_px:].ravel()])
    return float(np.median(b))


def lattice_angle(img: np.ndarray, mask: np.ndarray, cell_px: float,
                  band: float = 0.25) -> float:
    """Piece lattice orientation mod 90 deg, from the angular position of
    gradient-spectrum energy in an annulus at the cell-pitch frequency
    (DESIGN §5.1's rectified-spectrum line, turned sideways: instead of
    reading the peak's phase we read its angle)."""
    g = np.hypot(*np.gradient(img.astype(np.float32)))
    g = np.where(mask, g, 0.0)
    g -= g.mean()
    n = min(1024, min(g.shape))
    y0 = (g.shape[0] - n) // 2
    x0 = (g.shape[1] - n) // 2
    p = np.abs(np.fft.rfft2(g[y0:y0 + n, x0:x0 + n],
                            s=(n, n))) ** 2  # (n, n//2+1)
    fy = np.fft.fftfreq(n)[:, None]
    fx = np.fft.rfftfreq(n)[None, :]
    rad = np.hypot(fy, fx)
    f0 = 1.0 / cell_px
    ann = (rad > f0 * (1 - band)) & (rad < f0 * (1 + band))
    ang = (np.degrees(np.arctan2(fy, fx)) % 90.0)
    w = p[ann]
    a = ang[np.broadcast_to(ann, ang.shape) if ann.shape != ang.shape
            else ann]
    # circular mean over the 90-deg-periodic angle, weighted by power
    th = np.deg2rad(a * 4.0)
    mean = np.degrees(np.arctan2((w * np.sin(th)).sum(),
                                 (w * np.cos(th)).sum())) / 4.0
    mean %= 90.0
    return float(mean - 90.0 if mean > 45.0 else mean)


def piece_cell_bits(img: np.ndarray, mask: np.ndarray, cell_px: int
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Small-piece cell lock: de-rotated + pitch-normalized pieces have ONE
    unknown left — the grid phase. Search all cell_px x cell_px integer
    phases for max detection confidence on masked cells (threshold = the
    masked median: the scrambler pins coverage at ~50%, so the median
    splits ink/paper blind-legally), then ctx-detect on the locked means.
    Returns (hard bits, cell mask, cell LLRs).
    Rationale: lock_grid's windowed phase profiles mislock on
    backing-embedded sub-grain pieces (measured — its windows straddle
    lattice-free backing); this exhaustive phase search is the robust
    replacement at piece scale, O(cell_px^2) block-means."""
    mid = float(np.median(img[mask])) if mask.any() else float(np.median(img))
    c = int(cell_px)
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
                best = (conf, m, km)
    if best is None:
        return (np.zeros((0, 0), np.uint8), np.zeros((0, 0), bool),
                np.zeros((0, 0)))
    _, m, km = best
    # median threshold + distance LLR. NOTE (measured 2026-07-10): running
    # acquire.cell_bits_ctx on these masked piece grids DEGRADES detection
    # (fixture A/B: synth gate-PASS 80%->68%, scan 3/42->0/42) — the ICM
    # context stage misfires on mask-filled small grids; per-piece ctx
    # needs its own treatment (queued), median bits stand until then.
    spread = float(np.abs(m[km] - mid).mean()) if km.any() else 1.0
    llr = np.clip((mid - m) / max(spread, 1e-6), -8.0, 8.0) * 2.0
    return (m < mid).astype(np.uint8), km, llr


def rotate_transform(in_shape: tuple, angle_deg: float,
                     out_shape_ref: tuple | None = None
                     ) -> tuple[np.ndarray, np.ndarray, tuple]:
    """The exact output->input affine of scipy.ndimage.rotate(...,
    reshape=True): output coord o maps to input coord M @ o + offset.
    Mirrors scipy's construction; tests assert equivalence against
    ndimage.rotate so a scipy convention change can never silently skew
    the samplers below.

    out_shape_ref ANCHORS the output frame: pass a reference angle's
    out_shape so a family of candidate angles shares one center and a
    phase locked at the reference stays meaningful across candidates
    (each angle's own bbox center drifts laterally with the angle —
    caught by test_segment_refine on a large piece)."""
    a = np.deg2rad(angle_deg)
    c, s = np.cos(a), np.sin(a)
    M = np.array([[c, s], [-s, c]])
    if out_shape_ref is None:
        iy, ix = in_shape
        out_bounds = M @ np.array([[0, 0, iy, iy], [0, ix, 0, ix]],
                                  np.float64)
        out_shape = (np.ptp(out_bounds, axis=1) + 0.5).astype(int)
    else:
        out_shape = np.array(out_shape_ref, np.int64)
    in_center = (np.array(in_shape, np.float64) - 1) / 2
    out_center = M @ ((out_shape - 1) / 2)
    offset = in_center - out_center
    return M, offset, (int(out_shape[0]), int(out_shape[1]))


def phase_scan_glass(im: np.ndarray, mk: np.ndarray, mid: float,
                     backing: float, M: np.ndarray, off: np.ndarray,
                     out_shape: tuple, pitch_px: float,
                     phase_step: int = 1) -> tuple | None:
    """Best (conf, dy, dx) integer de-rotated-frame phase for one
    rotate_transform, reading ORIGINAL pixels (no image resample); the
    objective is piece_cell_bits' masked |mean - median| on a coarse
    cell subgrid."""
    p = float(pitch_px)
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


def sample_cells_at(glass: np.ndarray, gmask: np.ndarray, backing: float,
                    angle_deg: float, pitch_px: float, dy: float,
                    dx: float, n_sub: int = 3,
                    ref_angle_deg: float | None = None
                    ) -> tuple[np.ndarray, np.ndarray, float] | None:
    """Full cell-mean grid at a (possibly refined) angle and CONTINUOUS
    phase, order-3 area sampling of the original pixels (n_sub^2 in-cell
    offsets averaged). Returns (means, cell mask at 0.85 coverage, masked
    median). The P3.1 rotation-curve probe measured the counter-rotation
    RESAMPLE free at genie angle — this sampler exists so angle/phase can
    be searched (each candidate is a coordinate transform, not an image
    rotation), which is where the measured tax actually lives."""
    im = np.where(gmask, np.asarray(glass, np.float32), np.float32(backing))
    mk = np.asarray(gmask, np.float32)
    mid = float(np.median(im[gmask])) if gmask.any() else 128.0
    p = float(pitch_px)
    ref_shape = None
    if ref_angle_deg is not None:       # share the reference frame's center
        _, _, ref_shape = rotate_transform(im.shape, ref_angle_deg)
    M, off, out_shape = rotate_transform(im.shape, angle_deg, ref_shape)
    n_cy = int((out_shape[0] - dy) // p)
    n_cx = int((out_shape[1] - dx) // p)
    if n_cy < 2 or n_cx < 2:
        return None
    ycs = dy + np.arange(n_cy) * p
    xcs = dx + np.arange(n_cx) * p
    offs = (np.arange(n_sub) + 0.5) / n_sub * p
    means = np.zeros((n_cy, n_cx), np.float64)
    cover = np.zeros((n_cy, n_cx), np.float64)
    # prefilter and evaluation must share the boundary mode ('mirror' is
    # spline_filter's default; a 'constant' read of mirror-filtered
    # coefficients corrupts the outer ~4 px — caught by the axis-aligned
    # exact-recovery test)
    imf = ndimage.spline_filter(im, order=3, mode="mirror")
    for dv in offs:
        for du in offs:
            oy, ox = np.meshgrid(ycs + dv, xcs + du, indexing="ij")
            coords = M @ np.array([oy.ravel(), ox.ravel()]) + off[:, None]
            means += ndimage.map_coordinates(
                imf, coords, order=3, prefilter=False,
                mode="mirror").reshape(n_cy, n_cx)
            cover += ndimage.map_coordinates(
                mk, coords, order=1, cval=0.0).reshape(n_cy, n_cx)
    means /= n_sub * n_sub
    kmask = (cover / (n_sub * n_sub)) > 0.85
    if not kmask.any():
        return None
    return means, kmask, mid


def refine_on_sites(glass: np.ndarray, gmask: np.ndarray, backing: float,
                    angle0: float, pitch_px: float, dy0: int, dx0: int,
                    sites_ij: np.ndarray, site_vals: np.ndarray,
                    ang_span: float = 0.6, ang_step: float = 0.05,
                    ph_span: float = 0.5, ph_step: float = 0.125
                    ) -> tuple[float, float, float, dict]:
    """Pilot-supervised (angle, continuous sub-cell phase) refinement.

    Measured motivation (P3.1 + detector A/B round 2, 2026-07-11):
    lattice_angle delivers ~0.4-0.5 deg median error where <0.15 deg is
    free (+0.09..0.20 mismatch dose-response); refining on the placed
    pilot reference took held-out mismatch 0.091 -> 0.073 and
    refined+recal core BER to 0.109 on the white real-toner fixture.
    Sites come from a gate-passed placement (seed-derived pilot values —
    blind-legal, F10 at piece scale); the search minimizes TRAIN-half
    mismatch, the held-out half is reported in the meta for honesty."""
    im = np.where(gmask, np.asarray(glass, np.float32), np.float32(backing))
    mid = float(np.median(im[gmask])) if gmask.any() else 128.0
    p = float(pitch_px)
    tr = np.arange(sites_ij.shape[0]) % 2 == 0
    ho = ~tr
    # every candidate frame shares angle0's out_shape/center: the phase
    # (dy0, dx0) was locked in that frame, and per-candidate bbox centers
    # drift laterally with the angle (measured to run the search into its
    # boundary on large pieces)
    _, _, oshape0 = rotate_transform(im.shape, angle0)

    sgn = (2.0 * (site_vals > 0) - 1.0)      # +1 = ink (darker than mid)

    def eval_cand(ang, py, px):
        """(TRAIN objective, held-out HARD mismatch). The objective is
        the mean SIGNED MARGIN (mid - m)·sign — the hard-bit mismatch
        saturates to a zero plateau on clean channels (every site reads
        correctly across a ±0.5 deg band; measured on the synth-channel
        test), while the margin peaks where sites sit dead-center on
        their cells and stays informative at any BER."""
        M, off, _ = rotate_transform(im.shape, ang, oshape0)
        yc = dy0 + py * p + (sites_ij[:, 0] + 0.5) * p
        xc = dx0 + px * p + (sites_ij[:, 1] + 0.5) * p
        coords = M @ np.stack([yc, xc]) + off[:, None]
        m = ndimage.map_coordinates(im, coords, order=1, cval=backing)
        score = float(np.mean((mid - m[tr]) * sgn[tr]))
        mis_ho = float(np.mean((m[ho] < mid) != (site_vals[ho] > 0)))
        return score, mis_ho

    _, base_ho = eval_cand(angle0, 0.0, 0.0)
    best = None
    for da in np.arange(-ang_span, ang_span + 1e-9, ang_step):
        for py in np.arange(-ph_span, ph_span + 1e-9, ph_step):
            for px in np.arange(-ph_span, ph_span + 1e-9, ph_step):
                score, mis_ho = eval_cand(angle0 + da, py, px)
                if best is None or score > best[0]:
                    best = (score, angle0 + da, py * p, px * p, mis_ho)
    _, ang, oy_f, ox_f, mis_ho = best
    return ang, dy0 + oy_f, dx0 + ox_f, {
        "heldout_pre": base_ho, "heldout_post": mis_ho,
        "angle_moved": ang - angle0}


def recal_llrs_from_labels(means: np.ndarray, label_sel: np.ndarray,
                           label_vals: np.ndarray,
                           min_per_class: int = 20,
                           llr_clip: float = 12.0
                           ) -> np.ndarray | None:
    """Per-piece 2-class Gaussian LLRs from labeled cells (F10 at piece
    scale): fit ink/paper Gaussians on means[label_sel] with printed
    values label_vals, return calibrated LLRs for the WHOLE grid (house
    sign: positive = ink). None if labels are too few or the fit is
    degenerate (ink must be darker)."""
    y = label_vals.astype(bool)
    x = np.asarray(means[label_sel], np.float64)
    if y.sum() < min_per_class or (~y).sum() < min_per_class:
        return None
    mu1, mu0 = float(x[y].mean()), float(x[~y].mean())
    v1 = max(float(x[y].var()), 1e-4)
    v0 = max(float(x[~y].var()), 1e-4)
    if mu1 >= mu0:
        return None
    llr = (-0.5 * ((means - mu1) ** 2 / v1 - (means - mu0) ** 2 / v0)
           - 0.5 * np.log(v1 / v0))
    return np.clip(llr, -llr_clip, llr_clip)


def segment_pieces(img: np.ndarray, *, cell_px: float,
                   dpi: float, backing: float | None = None,
                   fg_delta: float = FG_DELTA,
                   min_area_mm2: float = MIN_AREA_MM2) -> list[Piece]:
    """Find every fragment on the glass; return de-rotated Pieces.

    cell_px = expected cell pitch on THIS image's footing (e.g. 8 at
    2400 dpi c2). Backing-agnostic by construction — dark sheet and white
    lid segment identically for printed-field pieces (tested)."""
    im = np.asarray(img, np.float32)
    if backing is None:
        backing = estimate_backing(im)
    d = max(2, int(round(cell_px)))              # ~1-cell overview blocks
    ov = ndimage.uniform_filter(im, size=d)[d // 2::d, d // 2::d]
    core = np.abs(ov - backing) > fg_delta
    core = ndimage.binary_opening(core, np.ones((2, 2)))
    core = ndimage.binary_closing(core, np.ones((3, 3)), iterations=2)
    grow = max(1, int(round(GROW_CELLS * cell_px / d)))
    grown = ndimage.binary_dilation(core, np.ones((3, 3)), iterations=grow)
    lab, n = ndimage.label(grown)
    pieces: list[Piece] = []
    px_mm = dpi / 25.4
    for li, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is None:
            continue
        # THIS label only (`== li`), never `> 0`: a tilted piece's bbox
        # slice can contain a bbox-intruding NEIGHBOR, and `> 0` absorbs
        # its clipped corner into this mask — the ride-along-poison root
        # cause (2026-07-12 scan-2 forensics: a −44.7° piece absorbed a
        # 162k-px corner of its neighbor, dragged to a wrong page location
        # by the rigid placement). find_objects is 1-indexed by label.
        comp = lab[sl] == li
        area = float(comp.sum()) * (d / px_mm) ** 2
        if area < min_area_mm2:
            continue
        y0 = sl[0].start * d
        x0 = sl[1].start * d
        h = comp.shape[0] * d
        w = comp.shape[1] * d
        sub = im[y0:min(y0 + h, im.shape[0]), x0:min(x0 + w, im.shape[1])]
        m = np.kron(comp, np.ones((d, d), bool))[:sub.shape[0],
                                                 :sub.shape[1]]
        ang = lattice_angle(sub, m, cell_px)
        rot = ndimage.rotate(np.where(m, sub, backing), ang,
                             reshape=True, order=3, cval=backing,
                             mode="constant")
        mrot = ndimage.rotate(m.astype(np.uint8), ang, reshape=True,
                              order=0, cval=0, mode="constant") > 0
        pieces.append(Piece(img=rot.astype(np.float32), mask=mrot,
                            angle_deg=ang, bbox_glass=(y0, x0, h, w),
                            area_mm2=area,
                            img_glass=sub.astype(np.float32),
                            mask_glass=m))
    pieces.sort(key=lambda p: -p.area_mm2)      # big pieces first (§15.1)
    return pieces


def _activity_map(im: np.ndarray, d: int, win_cells: float) -> np.ndarray:
    """Per-cell local std (the payload MODULATION), sampled on the 1-cell
    overview grid, measured over a `win_cells`-cell window. Cost is O(N) in
    the image and flat in the window (uniform_filter running sums)."""
    w = max(2, int(round(win_cells * d)))
    mean = ndimage.uniform_filter(im, size=w)
    var = ndimage.uniform_filter(im * im, size=w) - mean * mean
    return np.sqrt(np.clip(var, 0.0, None))[d // 2::d, d // 2::d]


def find_lattice_candidates(img: np.ndarray, *, cell_px: float, dpi: float,
                            win_cells: float = STD_WIN_CELLS,
                            std_lo: float = STD_LO, std_hi: float = STD_HI,
                            seed_erode: int = SEED_ERODE,
                            min_med_std: float = MIN_MED_STD,
                            grain_mm: float = GRAIN_MM,
                            min_area_mm2: float = MIN_AREA_MM2,
                            diagnostics: dict | None = None
                            ) -> list["LatticeCandidate"]:
    """Acquire candidate payload-lattice regions from a platen scan — the
    front stage of the fragment receiver, BEFORE angle/pitch/pilot/BCH.

    Detects cell-scale MODULATION (local std), not brightness-vs-backing, so
    it keeps only data-carrying fields and drops homogeneous patches — blank
    paper margins AND the backing — regardless of backing colour (dark sheet
    or white lid); it never reads `backing`, so the estimate_backing
    border-flip cannot occur.

    Growth is HYSTERESIS from an ERODED seed, not a blind dilate: the strict
    seed (act > std_hi) is eroded (seed_erode) so a thin high-std EDGE line
    (torn-paper margin / scrap-edge step, no solid core) vanishes while a
    field's solid seed core survives; binary_propagation grows it into
    connected loose cells (act > std_lo) — a signal-following boundary that
    keeps faint field joined without seeding lid noise; a light opening
    despeckles. A signal-strength gate then drops any candidate whose MEDIAN
    modulation is below min_med_std (a weakly-modulated lid/edge blob). NO
    fill_holes (see body). No angle correction — candidates stay in the raw
    glass frame (angle/pitch/pilots are downstream). Sub-grain candidates
    (< grain_mm) are flagged: too few pilot sites to self-place in isolation.
    """
    im = np.asarray(img, np.float32)
    if im.ndim != 2:
        raise ValueError(f"find_lattice_candidates needs a 2-D grey image, "
                         f"got shape {im.shape} — reduce RGB to luma first")
    if im.size and float(im.max()) > 512.0:      # true 16-bit -> 8-bit grey
        im = im / 256.0                          # units (thresholds assume
    #   8-bit; 512 clears 8-bit+noise, well below any real 16-bit content)
    d = max(2, int(round(cell_px)))
    act = _activity_map(im, d, win_cells)
    if min(act.shape) < 3:                        # image too small for the grid
        return []
    # hysteresis from an ERODED seed: eroding the strict seed deletes thin
    # high-std EDGE lines (a torn-paper margin or scrap-edge step has no solid
    # core) while a field's solid seed core survives; propagation then regrows
    # the field to the loose boundary. The scrap-edge ring dies here too.
    seed = ndimage.binary_erosion(act > std_hi, iterations=seed_erode)
    region = ndimage.binary_propagation(seed, mask=act > std_lo)
    region = ndimage.binary_opening(region, np.ones((3, 3)))    # despeckle
    # NO fill_holes: on a scrambled field interior low-modulation holes are
    # rare and, where real, are data-ABSENT (damage/dropout) -- claiming
    # lattice there is wrong; a hole is left as an honest erasure for the
    # downstream FEC. (Measured: fill changed 0.3% of cells, 0 candidates, on
    # confetti-1/2/3, and risks filling an enclosed lid region.) The field
    # stays one component via connectivity regardless.
    lab, _ = ndimage.label(region)
    px_mm = dpi / 25.4
    cands: list[LatticeCandidate] = []
    n_below_med = 0                     # sized blobs the med_std gate rejected
    for li, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sl is None:
            continue
        comp = lab[sl] == li            # THIS label only (bbox-absorption safe)
        n_cells = int(comp.sum())
        area = n_cells * (d / px_mm) ** 2
        if area < min_area_mm2:
            continue
        med = float(np.median(act[sl][comp]))
        if med < min_med_std:           # weakly-modulated blob, not a field
            n_below_med += 1
            continue
        y0, x0 = sl[0].start * d, sl[1].start * d
        mask = np.kron(comp, np.ones((d, d), bool))
        mask = mask[:im.shape[0] - y0, :im.shape[1] - x0]
        cands.append(LatticeCandidate(
            mask=mask, bbox=(y0, x0, mask.shape[0], mask.shape[1]),
            area_mm2=area, n_cells=n_cells, med_std=med,
            sub_grain=area ** 0.5 < grain_mm))
    cands.sort(key=lambda c: -c.area_mm2)
    if diagnostics is not None:          # surface silent med_std drops (a faint
        diagnostics["dropped_below_med_std"] = n_below_med   # field would show
    return cands
