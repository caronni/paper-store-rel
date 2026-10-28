"""Platen survey for experiment 021.

One job only:

* find independent regions that may carry the printed payload lattice;
* infer one common ``c`` for the platen from their scan-space pitch;
* attach a conservative approximate angle hint to each region, or ``None``.

Input configuration is the 2-D grey scan and its true scan DPI.  ``c`` is
defined on paper-store's frozen 600-dpi print grid, so

    c = measured_cell_pitch_px * 600 / scan_dpi

rounded only when the measured pitch is close to an integer-dot pitch.

There are deliberately no confidence tiers, pilot/BCH searches, addresses,
payload LLRs, full-page special cases, border exceptions, radial fallbacks, or
per-region ``c`` values.  All returned objects are survey candidates.  E022 is
the separate pass that scans them for BCH-addressed pilot tiles.

The detector is the sound core retained from experiments 020/021:

1. one coarse, physically denominated structure-tensor survey;
2. global pitch consensus across sufficiently large survey components;
3. pitch-matched boundary/gap refinement using that common pitch;
4. per-final-region angle measurement at the known pitch, with honest refusal.

Design and measured provenance: experiments/021-payload-regions.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from paperholo import scannorm
from paperholo.sync import estimate_lattice


PRINT_DPI = 600.0
SURVEY_CELL_UM = 340.0
WORK_CELL_PX = 4.0
DERIV_CELLS = 0.22
TENSOR_CELLS = 0.30
DENSITY_MIN = 5
MIN_AREA_MM2 = 9.0
C_SNAP_TOL = 0.04
MAX_C_DOTS = 12
MAX_ANGLE_WORK_CELLS = 16_000_000
SUPPORT_HOLE_RADIUS_CELLS = 3.0
REFINE_BOUNDARY_SURVEY_CELLS = 2
REFINE_VALLEY_FRACTION = 0.65
REFINE_VALLEY_RUN = 3
REFINE_VALLEY_MIN_SPAN_FRACTION = 0.25
REFINE_VALLEY_HALO_SURVEY_CELLS = 1
REFINE_TILE_CELLS = 128
REFINE_TILE_HALO_CELLS = 4
PITCH_PROBES_PX = (
    2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0,
    48.0, 64.0, 96.0, 128.0,
)


@dataclass
class PayloadRegion:
    """One candidate payload region in native scan coordinates."""

    bbox: tuple[int, int, int, int]  # y0, x0, h, w
    mask: np.ndarray                 # bool search support, bbox-local native px
    area_mm2: float
    angle_hint_deg: float | None
    score: float


@dataclass
class PayloadSurvey:
    """Complete e021 result: candidates plus one platen-wide cell pitch."""

    regions: tuple[PayloadRegion, ...]
    c_dots: int | None
    cell_pitch_px: float | None
    pitch_votes: tuple[tuple[int, float], ...] = ()
    diagnostics: dict = field(default_factory=dict)


@dataclass
class _Component:
    sl: tuple[slice, slice]
    mask: np.ndarray
    scores: np.ndarray
    score: float


@dataclass
class _Refinement:
    regions: list[tuple[int, int, np.ndarray, float]]
    tiles: int
    scored_cells: int
    grid_cells: int


def _as_grey(image: np.ndarray) -> np.ndarray:
    a = np.asarray(image)
    if a.ndim != 2:
        raise ValueError(f"platen scan must be 2-D grey, got {a.shape}")
    out = a.astype(np.float32, copy=False)
    if out.size and float(np.nanmax(out)) > 512.0:
        out = out / 256.0
    return out


def _block_mean(a: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return np.asarray(a, np.float32)
    h = a.shape[0] // factor * factor
    w = a.shape[1] // factor * factor
    if h == 0 or w == 0:
        return np.zeros((0, 0), np.float32)
    return np.asarray(a[:h, :w]).reshape(
        h // factor, factor, w // factor, factor
    ).mean(axis=(1, 3), dtype=np.float32)


def _tensor_geometry(cell_px: float) -> tuple[int, int, int]:
    """Return decimation, work-grid pitch and native output step."""
    decimation = max(1, int(round(cell_px / WORK_CELL_PX)))
    work_pitch = max(1, int(round(cell_px / decimation)))
    return decimation, work_pitch, decimation * work_pitch


def _minor_eigen_score(
    image: np.ndarray, cell_px: float
) -> tuple[np.ndarray, int]:
    """Structure-tensor sqrt(lambda_min) sampled at about one cell."""
    decimation, sample, step = _tensor_geometry(cell_px)
    work = _block_mean(image, decimation)
    if min(work.shape, default=0) < 3:
        return np.zeros((0, 0), np.float32), decimation
    pitch = cell_px / decimation
    derivative_sigma = max(0.6, DERIV_CELLS * pitch)
    gx = ndimage.gaussian_filter(
        work, derivative_sigma, order=(0, 1), mode="nearest"
    ) * derivative_sigma
    gy = ndimage.gaussian_filter(
        work, derivative_sigma, order=(1, 0), mode="nearest"
    ) * derivative_sigma
    tensor_sigma = max(1.0, TENSOR_CELLS * pitch)
    jxx = ndimage.gaussian_filter(gx * gx, tensor_sigma, mode="nearest")
    jyy = ndimage.gaussian_filter(gy * gy, tensor_sigma, mode="nearest")
    jxy = ndimage.gaussian_filter(gx * gy, tensor_sigma, mode="nearest")
    trace = jxx + jyy
    disc = np.sqrt(np.maximum((jxx - jyy) ** 2 + 4.0 * jxy * jxy, 0.0))
    minor = np.sqrt(np.maximum(0.5 * (trace - disc), 0.0))
    return _block_mean(minor, sample), step


def _adaptive_threshold(score: np.ndarray) -> float:
    """Single scan-adaptive threshold: log-space Otsu."""
    values = np.log1p(np.asarray(score, np.float64).ravel())
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.inf

    hist, edges = np.histogram(values, bins=256)
    probability = hist.astype(np.float64) / max(int(hist.sum()), 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    weight = np.cumsum(probability)
    mean = np.cumsum(probability * centres)
    variance = (mean[-1] * weight - mean) ** 2 / np.maximum(
        weight * (1.0 - weight), np.finfo(np.float64).eps
    )
    return float(np.expm1(centres[int(np.argmax(variance[:-1]))]))


def _active_mask(score: np.ndarray, threshold: float) -> np.ndarray:
    active = score > threshold
    neighbours = ndimage.convolve(
        active.astype(np.uint8), np.ones((3, 3), np.uint8),
        mode="constant", cval=0,
    )
    return active & (neighbours >= DENSITY_MIN)


def _components(
    score: np.ndarray,
    threshold: float,
    *,
    step_px: int,
    px_per_mm: float,
    min_area_mm2: float,
) -> list[_Component]:
    mask = _active_mask(score, threshold)
    labels, _ = ndimage.label(mask)
    cell_area_mm2 = (step_px / px_per_mm) ** 2
    out: list[_Component] = []
    for label_id, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        component = labels[sl] == label_id
        if int(component.sum()) * cell_area_mm2 < min_area_mm2:
            continue
        out.append(_Component(
            sl=sl,
            mask=component,
            scores=np.asarray(score[sl], np.float32),
            score=float(np.median(score[sl][component])),
        ))
    return out


def _interior_window(
    source: np.ndarray,
    component: _Component,
    step_px: int,
    *,
    max_half_px: int = 1024,
) -> np.ndarray | None:
    """Largest square centred inside a component; never enlarge past it."""
    distance = ndimage.distance_transform_edt(component.mask)
    iy, ix = np.unravel_index(int(np.argmax(distance)), distance.shape)
    half = min(int(distance[iy, ix] * step_px), max_half_px)
    if half < 16:
        return None
    cy = component.sl[0].start * step_px + iy * step_px + step_px // 2
    cx = component.sl[1].start * step_px + ix * step_px + step_px // 2
    y0, y1 = max(0, cy - half), min(source.shape[0], cy + half)
    x0, x1 = max(0, cx - half), min(source.shape[1], cx + half)
    crop = source[y0:y1, x0:x1]
    return crop if min(crop.shape) >= 32 else None


def _snap_c(pitch_px: float, dpi: float) -> int | None:
    c_float = pitch_px * PRINT_DPI / dpi
    c_dots = int(round(c_float))
    if not 1 <= c_dots <= MAX_C_DOTS:
        return None
    return c_dots if abs(c_float / c_dots - 1.0) <= C_SNAP_TOL else None


def _pitch_vote(crop: np.ndarray, dpi: float) -> tuple[int, float] | None:
    """One component contributes at most one global-c vote.

    Use every credible wide-band line and take the largest line that lands on
    an integer c. This retains the cell fundamental over its harmonics. A
    diagonal line such as c3/sqrt(2) does not land within the 4% c bar and
    cannot vote.
    """
    try:
        measurement = scannorm.measure_cell_pitch(
            crop, probes_px=PITCH_PROBES_PX
        )
    except (ValueError, scannorm.ScanRefused):
        return None
    candidates = list(measurement.strong)
    candidates.append((measurement.pitch_px, measurement.contrast))
    snapped = [
        (c, float(pitch))
        for pitch, _contrast in candidates
        if (c := _snap_c(float(pitch), dpi)) is not None
    ]
    return max(snapped, key=lambda item: item[0]) if snapped else None


def _global_pitch(
    source: np.ndarray,
    components: list[_Component],
    step_px: int,
    dpi: float,
) -> tuple[int | None, float | None, tuple[tuple[int, float], ...]]:
    votes: list[tuple[int, float]] = []
    for component in sorted(
        components, key=lambda c: int(c.mask.sum()), reverse=True
    ):
        # Pitch needs many periods, especially for coarse c. Use the whole
        # survey bbox rather than the deepest inscribed square. Under e021's
        # explicit one-c-per-platen contract, a nearby candidate cannot
        # introduce a conflicting valid pitch; the wider support is an asset.
        y0 = component.sl[0].start * step_px
        x0 = component.sl[1].start * step_px
        y1 = min(source.shape[0], component.sl[0].stop * step_px)
        x1 = min(source.shape[1], component.sl[1].stop * step_px)
        crop = source[y0:y1, x0:x1]
        if min(crop.shape, default=0) < 32:
            continue
        vote = _pitch_vote(crop, dpi)
        if vote is not None:
            votes.append(vote)

    if not votes:
        return None, None, ()
    counts: dict[int, int] = {}
    for c_dots, _ in votes:
        counts[c_dots] = counts.get(c_dots, 0) + 1
    ordered = sorted(counts.items(), key=lambda item: (-item[1], -item[0]))
    if len(ordered) > 1 and ordered[0][1] == ordered[1][1]:
        return None, None, tuple(votes)
    chosen_c = ordered[0][0]
    pitch = float(np.median([p for c, p in votes if c == chosen_c]))
    return chosen_c, pitch, tuple(votes)


def _raster_mask(
    component: np.ndarray,
    *,
    y0: int,
    x0: int,
    step_px: int,
    shape: tuple[int, int],
) -> np.ndarray:
    dense = np.repeat(np.repeat(component, step_px, axis=0), step_px, axis=1)
    return dense[:shape[0] - y0, :shape[1] - x0]


def _support_mask(
    activity: np.ndarray,
    max_radius_grid: float = SUPPORT_HOLE_RADIUS_CELLS,
) -> np.ndarray:
    """Fill small topologically enclosed inactivity.

    The tensor activity mask is evidence, not geometry: locally uniform or
    one-direction payload runs create false holes. E022 needs a conservative
    search envelope. Padding with known exterior background identifies the
    enclosed holes; only holes whose maximum inscribed radius is within the
    measured detector-dropout class are filled. Exterior concavities stay
    false, larger real voids stay open, and disconnected components can never
    merge. Work stays on the tensor grid; callers rasterize only the completed
    support mask.
    """
    activity = np.asarray(activity, bool)
    padded = np.pad(activity, 1, constant_values=False)
    enclosed = ndimage.binary_fill_holes(padded)[1:-1, 1:-1] & ~activity
    labels, count = ndimage.label(enclosed)
    if count == 0 or max_radius_grid < 1.0:
        return activity.copy()
    distance = ndimage.distance_transform_edt(enclosed)
    radii = ndimage.maximum(
        distance, labels, index=np.arange(1, count + 1)
    )
    fill_ids = np.flatnonzero(radii <= max_radius_grid) + 1
    return activity | np.isin(labels, fill_ids)


def _coherent_valleys(component: _Component) -> np.ndarray:
    """Low-score runs that may be a survey-fused material gap.

    Random payload produces isolated low tensor cells throughout its interior.
    A narrow physical gap instead produces a coherent low-score run. Retain
    only runs visible through a three-cell line in one of four orientations;
    those cells are worth pitch-scale inspection, while isolated interior
    speckles are not.
    """
    low = (
        component.mask
        & (component.scores <= REFINE_VALLEY_FRACTION * component.score)
    )
    run = REFINE_VALLEY_RUN
    structures = (
        np.ones((run, 1), bool),
        np.ones((1, run), bool),
        np.eye(run, dtype=bool),
        np.fliplr(np.eye(run, dtype=bool)),
    )
    coherent = np.zeros(low.shape, bool)
    for structure in structures:
        coherent |= ndimage.binary_opening(low, structure=structure)
    labels, _ = ndimage.label(
        coherent, structure=np.ones((3, 3), bool)
    )
    min_span = max(
        REFINE_VALLEY_RUN,
        int(np.ceil(
            REFINE_VALLEY_MIN_SPAN_FRACTION * min(component.mask.shape)
        )),
    )
    keep = np.zeros(coherent.shape, bool)
    for label_id, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        height = sl[0].stop - sl[0].start
        width = sl[1].stop - sl[1].start
        if max(height, width) >= min_span:
            keep[sl] |= labels[sl] == label_id
    coherent = keep
    if coherent.any() and REFINE_VALLEY_HALO_SURVEY_CELLS > 0:
        coherent = ndimage.binary_dilation(
            coherent,
            iterations=REFINE_VALLEY_HALO_SURVEY_CELLS,
        )
    return coherent


def _fine_geometry(
    survey: _Component,
    *,
    survey_step_px: int,
    pitch_px: float,
    y0: int,
    x0: int,
    shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray, int]:
    """Project coarse support and its refinement domain onto the fine grid."""
    _decimation, _sample, step = _tensor_geometry(pitch_px)
    fine_h = shape[0] // step
    fine_w = shape[1] // step
    if min(fine_h, fine_w) < 3:
        return (
            np.zeros((0, 0), bool),
            np.zeros((0, 0), bool),
            step,
        )

    hole_radius = max(
        1.0,
        SUPPORT_HOLE_RADIUS_CELLS * pitch_px / survey_step_px,
    )
    support = _support_mask(survey.mask, hole_radius)
    pad = REFINE_BOUNDARY_SURVEY_CELLS + 1
    padded = np.pad(support, pad, constant_values=False)
    exterior_band = (
        ndimage.binary_dilation(
            padded, iterations=REFINE_BOUNDARY_SURVEY_CELLS
        )
        & ~ndimage.binary_erosion(
            padded,
            iterations=REFINE_BOUNDARY_SURVEY_CELLS,
            border_value=0,
        )
    )
    valleys = np.pad(
        _coherent_valleys(survey), pad, constant_values=False
    )
    coarse_domain = exterior_band | valleys

    native_y = y0 + np.arange(fine_h, dtype=np.int64) * step + step // 2
    native_x = x0 + np.arange(fine_w, dtype=np.int64) * step + step // 2
    coarse_y = (
        native_y // survey_step_px - survey.sl[0].start + pad
    )
    coarse_x = (
        native_x // survey_step_px - survey.sl[1].start + pad
    )
    valid_y = (coarse_y >= 0) & (coarse_y < padded.shape[0])
    valid_x = (coarse_x >= 0) & (coarse_x < padded.shape[1])

    base = np.zeros((fine_h, fine_w), bool)
    domain = np.zeros_like(base)
    if valid_y.any() and valid_x.any():
        target_y = np.flatnonzero(valid_y)
        target_x = np.flatnonzero(valid_x)
        target = np.ix_(target_y, target_x)
        source = np.ix_(coarse_y[valid_y], coarse_x[valid_x])
        base[target] = padded[source]
        domain[target] = coarse_domain[source]
    return base, domain, step


def _tile_selection(domain: np.ndarray) -> np.ndarray:
    """Tiles covering the refinement domain plus one seam-safe neighbour."""
    tile = REFINE_TILE_CELLS
    rows = (domain.shape[0] + tile - 1) // tile
    cols = (domain.shape[1] + tile - 1) // tile
    selected = np.zeros((rows, cols), bool)
    for row in range(rows):
        y0 = row * tile
        y1 = min(domain.shape[0], y0 + tile)
        for col in range(cols):
            x0 = col * tile
            x1 = min(domain.shape[1], x0 + tile)
            selected[row, col] = bool(domain[y0:y1, x0:x1].any())
    if selected.any():
        selected = ndimage.binary_dilation(
            selected, structure=np.ones((3, 3), bool)
        )
    return selected


def _boundary_scores(
    source: np.ndarray,
    *,
    y0: int,
    x0: int,
    pitch_px: float,
    shape: tuple[int, int],
    selected: np.ndarray,
    step: int,
) -> tuple[np.ndarray, np.ndarray, int]:
    """Evaluate pitch-scale tensor scores only in selected aligned tiles."""
    score = np.zeros(shape, np.float32)
    known = np.zeros(shape, bool)
    tile = REFINE_TILE_CELLS
    halo = REFINE_TILE_HALO_CELLS
    tiles = 0
    for row, col in np.argwhere(selected):
        fy0 = int(row) * tile
        fx0 = int(col) * tile
        fy1 = min(shape[0], fy0 + tile)
        fx1 = min(shape[1], fx0 + tile)
        py0 = max(0, fy0 - halo)
        px0 = max(0, fx0 - halo)
        py1 = min(shape[0], fy1 + halo)
        px1 = min(shape[1], fx1 + halo)
        patch = source[
            y0 + py0 * step:y0 + py1 * step,
            x0 + px0 * step:x0 + px1 * step,
        ]
        local, local_step = _minor_eigen_score(patch, pitch_px)
        if local_step != step:
            raise RuntimeError("pitch-scale tensor grid changed within tile")
        oy0, ox0 = fy0 - py0, fx0 - px0
        oy1, ox1 = oy0 + fy1 - fy0, ox0 + fx1 - fx0
        central = local[oy0:oy1, ox0:ox1]
        if central.shape != (fy1 - fy0, fx1 - fx0):
            continue
        score[fy0:fy1, fx0:fx1] = central
        known[fy0:fy1, fx0:fx1] = True
        tiles += 1
    return score, known, tiles


def _merge_boundary_refinement(
    base: np.ndarray,
    domain: np.ndarray,
    active: np.ndarray,
    known: np.ndarray,
) -> np.ndarray:
    """Apply fine evidence at boundaries without carving coarse interiors."""
    # Positive pitch-scale evidence may complete coarse support wherever it
    # was measured. Negative evidence is much weaker: it may retract support
    # only inside the explicit exterior/gap domain.
    candidate = np.asarray(base, bool) | (
        np.asarray(active, bool) & np.asarray(known, bool)
    )
    replace = np.asarray(domain, bool) & np.asarray(known, bool)
    candidate[replace] = np.asarray(active, bool)[replace]

    # Fine tensor silence inside a coarse-supported field is uncertainty, not
    # evidence of missing paper. Restore only candidate holes that were
    # already coarse-supported. Exterior-connected gaps remain false and may
    # therefore split a survey-fused pair.
    enclosed = ndimage.binary_fill_holes(candidate) & ~candidate
    candidate |= enclosed & base
    return candidate


def _refine_component(
    source: np.ndarray,
    survey: _Component,
    *,
    survey_step_px: int,
    pitch_px: float,
    px_per_mm: float,
    min_area_mm2: float,
) -> _Refinement:
    """Refine coarse boundaries and coherent gaps on bounded aligned tiles."""
    halo = int(round(max(2.0 * pitch_px, 1.0 * px_per_mm)))
    y0 = max(0, survey.sl[0].start * survey_step_px - halo)
    x0 = max(0, survey.sl[1].start * survey_step_px - halo)
    y1 = min(source.shape[0], survey.sl[0].stop * survey_step_px + halo)
    x1 = min(source.shape[1], survey.sl[1].stop * survey_step_px + halo)
    shape = (y1 - y0, x1 - x0)
    if min(shape) < 4 * pitch_px:
        return _Refinement([], 0, 0, 0)
    base, domain, step = _fine_geometry(
        survey,
        survey_step_px=survey_step_px,
        pitch_px=pitch_px,
        y0=y0,
        x0=x0,
        shape=shape,
    )
    if not domain.any():
        return _Refinement([], 0, 0, int(base.size))
    selected = _tile_selection(domain)
    score, known, tiles = _boundary_scores(
        source,
        y0=y0,
        x0=x0,
        pitch_px=pitch_px,
        shape=base.shape,
        selected=selected,
        step=step,
    )
    if not known.any():
        return _Refinement([], tiles, 0, int(base.size))
    threshold = _adaptive_threshold(score[known])
    active = _active_mask(score, threshold) & known

    # Fine activity can expand a boundary, but unrelated texture in the halo
    # must not mint a candidate. Keep only activity connected to the coarse
    # support through at least one fine cell.
    labels, _ = ndimage.label(active)
    touching = np.unique(labels[active & base])
    touching = touching[touching != 0]
    if touching.size == 0:
        return _Refinement(
            [],
            tiles,
            int(known.sum()),
            int(base.size),
        )
    active = np.isin(labels, touching)
    candidate = _merge_boundary_refinement(base, domain, active, known)

    labels, _ = ndimage.label(candidate)
    cell_area_mm2 = (step / px_per_mm) ** 2
    out: list[tuple[int, int, np.ndarray, float]] = []
    for label_id, sl in enumerate(ndimage.find_objects(labels), start=1):
        if sl is None:
            continue
        component = labels[sl] == label_id
        area = int(component.sum()) * cell_area_mm2
        if area < min_area_mm2:
            continue
        support = _support_mask(
            component,
            SUPPORT_HOLE_RADIUS_CELLS * pitch_px / step,
        )
        ry0 = y0 + sl[0].start * step
        rx0 = x0 + sl[1].start * step
        mask = _raster_mask(
            support, y0=ry0, x0=rx0, step_px=step, shape=source.shape
        )
        evidence = component & known[sl] & active[sl]
        region_score = (
            float(np.median(score[sl][evidence]))
            if evidence.any() else survey.score
        )
        out.append((ry0, rx0, mask, region_score))
    return _Refinement(
        out,
        tiles,
        int(known.sum()),
        int(base.size),
    )


def _angle_hint(
    source: np.ndarray,
    *,
    y0: int,
    x0: int,
    mask: np.ndarray,
    pitch_px: float,
) -> float | None:
    """Measure angle at the known pitch on two scales; disagreement => None.

    Candidate texture has already been established by the tensor survey, so
    no second absolute contrast constant is needed. Scale agreement is the
    evidence that the spectral angle is a useful hint.
    """
    # Find an interior centre on a one-sample-per-cell mask. Operating on the
    # native mask made six real platens take ~12 minutes: binary_fill_holes +
    # EDT repeatedly traversed hundreds of millions of redundant block
    # pixels. The cell-grid operation is geometrically equivalent and leaves
    # the emitted native mask untouched.
    stride = max(1, int(round(pitch_px)))
    work_shape = (
        (mask.shape[0] + stride - 1) // stride,
        (mask.shape[1] + stride - 1) // stride,
    )
    if work_shape[0] * work_shape[1] > MAX_ANGLE_WORK_CELLS:
        return None
    support = ndimage.binary_fill_holes(mask[::stride, ::stride])
    distance = ndimage.distance_transform_edt(support)
    if not distance.any():
        return None
    iy, ix = np.unravel_index(int(np.argmax(distance)), distance.shape)
    depth_px = int(distance[iy, ix] * stride)
    cy = y0 + iy * stride + stride // 2
    cx = x0 + ix * stride + stride // 2
    crops = []
    for limit in (512, 256):
        half = min(depth_px, limit)
        if half < 4:
            return None
        crops.append(source[
            max(0, cy - half):min(source.shape[0], cy + half),
            max(0, cx - half):min(source.shape[1], cx + half),
        ])
    if any(crop is None or min(crop.shape) < 8 * pitch_px for crop in crops):
        return None
    if crops[0].shape == crops[1].shape:
        return None
    estimates = []
    for crop in crops:
        try:
            estimate = estimate_lattice(crop, pitch_px_nominal=pitch_px)
        except (ValueError, RuntimeError):
            return None
        measured = float(estimate["pitch_px"])
        if abs(measured / pitch_px - 1.0) > C_SNAP_TOL:
            return None
        angle = float(np.degrees(float(estimate["angle_rad"])))
        estimates.append(((angle + 45.0) % 90.0) - 45.0)
    delta = abs(((estimates[0] - estimates[1] + 45.0) % 90.0) - 45.0)
    if delta > 2.0:
        return None
    phase = np.exp(4j * np.deg2rad(estimates)).mean()
    return float(np.degrees(np.angle(phase)) / 4.0)


def detect_payload_regions(
    image: np.ndarray,
    *,
    dpi: float,
    min_area_mm2: float = MIN_AREA_MM2,
) -> PayloadSurvey:
    """Return candidate regions, one global c, and optional angle hints."""
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    if min_area_mm2 <= 0:
        raise ValueError("min_area_mm2 must be positive")
    source = _as_grey(image)
    px_per_mm = dpi / 25.4
    survey_pitch_px = SURVEY_CELL_UM / 1000.0 * px_per_mm
    if min(source.shape, default=0) < 4 * survey_pitch_px:
        return PayloadSurvey((), None, None)

    score, survey_step = _minor_eigen_score(source, survey_pitch_px)
    if min(score.shape, default=0) < 3:
        return PayloadSurvey((), None, None)
    threshold = _adaptive_threshold(score)
    surveyed = _components(
        score, threshold, step_px=survey_step, px_per_mm=px_per_mm,
        min_area_mm2=min_area_mm2,
    )
    c_dots, measured_pitch, votes = _global_pitch(
        source, surveyed, survey_step, dpi
    )

    # Use scanner-scale measured pitch when available; otherwise the exact
    # dpi/print-grid relationship. Both correspond to the same global c.
    pitch_px = measured_pitch
    if c_dots is not None and pitch_px is None:
        pitch_px = dpi * c_dots / PRINT_DPI

    raw_regions: list[tuple[int, int, np.ndarray, float]] = []
    refine_tiles = 0
    refine_scored_cells = 0
    refine_grid_cells = 0
    for component in surveyed:
        refinement = (
            _refine_component(
                source, component, survey_step_px=survey_step,
                pitch_px=pitch_px, px_per_mm=px_per_mm,
                min_area_mm2=min_area_mm2,
            )
            if pitch_px is not None else _Refinement([], 0, 0, 0)
        )
        refine_tiles += refinement.tiles
        refine_scored_cells += refinement.scored_cells
        refine_grid_cells += refinement.grid_cells
        if refinement.regions:
            raw_regions.extend(refinement.regions)
            continue
        y0 = component.sl[0].start * survey_step
        x0 = component.sl[1].start * survey_step
        raw_regions.append((
            y0, x0,
            _raster_mask(
                _support_mask(
                    component.mask,
                    max(
                        1.0,
                        SUPPORT_HOLE_RADIUS_CELLS
                        * (pitch_px / survey_step
                           if pitch_px is not None else 1.0),
                    ),
                ),
                y0=y0, x0=x0, step_px=survey_step,
                shape=source.shape,
            ),
            component.score,
        ))

    regions: list[PayloadRegion] = []
    for y0, x0, mask, region_score in raw_regions:
        if not mask.any():
            continue
        area = float(mask.sum()) / (px_per_mm * px_per_mm)
        angle = (
            _angle_hint(
                source, y0=y0, x0=x0, mask=mask, pitch_px=pitch_px
            )
            if pitch_px is not None else None
        )
        regions.append(PayloadRegion(
            bbox=(y0, x0, mask.shape[0], mask.shape[1]),
            mask=mask,
            area_mm2=area,
            angle_hint_deg=angle,
            score=region_score,
        ))
    regions.sort(key=lambda region: -region.area_mm2)

    return PayloadSurvey(
        regions=tuple(regions),
        c_dots=c_dots,
        cell_pitch_px=pitch_px,
        pitch_votes=votes,
        diagnostics={
            "survey_threshold": threshold,
            "survey_step_px": survey_step,
            "survey_scale_px": survey_pitch_px,
            "survey_components": len(surveyed),
            "refine_mode": "boundary-gap-tiles",
            "refine_tiles": refine_tiles,
            "refine_scored_cells": refine_scored_cells,
            "refine_grid_cells": refine_grid_cells,
            "refine_fraction": (
                refine_scored_cells / refine_grid_cells
                if refine_grid_cells else 0.0
            ),
        },
    )
