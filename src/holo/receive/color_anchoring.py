"""Registration anchoring for color payload sampling.

Format-reference truth and image-plane registration for one E022-placed
color window set:

* canonical word/dust reference states anchor every downstream fit (what
  the receiver additionally KNOWS from prior certificates is
  :mod:`holo.receive.known_field`'s single derivation); and
* historical weighted-NCC anchor measurement against known ink feeds a
  bounded, replay-stable per-plane residual registration fit.

Raster access lives in the sampling leaf
(:mod:`holo.receive.color_sampling`); this module reads pixels only
through it.

Everything here is transient: crops, anchors, and residual proposals
never cross into persistence.  :mod:`holo.receive.color_payload` owns
the durable evidence contract around these helpers.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import numpy as np
from scipy import ndimage
from scipy.fft import irfftn, next_fast_len, rfftn

from ..core import channel
from ..format import pilots
from ..format.descriptor import FormatSpec
from ..format.profiles import Family
from . import color_detect
from ._payload_sampling import _WindowRows
from .color_registration import PlaneResidual, fit_plane_residual
from .color_sampling import (
    RawRGBRaster,
    native_crop as _native_crop,
    points_crop as _points_crop,
)
from .evidence import TileCertificateRecord
from .evidence_blocks import evidence_arity
from .payload_model import _immutable
from .placement.model import PlacedPatch


COLOR_CMY7_KIND = "cmy7"
COLOR_CMY8_KIND = "cmy8"
_RECTIFIED_PX_PER_DOT = 2
_ANCHOR_MIN_Q = 0.10
_ANCHOR_MAX_SHIFT_PX = 5
_ANCHOR_BUDGET_PER_KIND = 512


def _readonly(value: np.ndarray, dtype: np.dtype | type) -> np.ndarray:
    return _immutable(np.asarray(value), dtype)


def _color_kind(spec: FormatSpec) -> tuple[str, int]:
    if spec.codec_family is Family.CMY7:
        kind = COLOR_CMY7_KIND
    elif spec.codec_family is Family.CMY8:
        kind = COLOR_CMY8_KIND
    else:
        raise ValueError(f"{spec.codec_id}: not a provisional color codec")
    return kind, evidence_arity(kind)


@dataclass(frozen=True, slots=True)
class _Rows:
    patch: PlacedPatch
    local_cells_yx: np.ndarray
    page_cells_yx: np.ndarray
    scan_points_yx: np.ndarray
    states: np.ndarray
    furniture_kind: np.ndarray
    known_component_bits: np.ndarray
    known_component_mask: np.ndarray
    neighbor_indices: np.ndarray
    dependency_certificate_ids: tuple[str, ...]


@cache
def _color_site_lookup(family_seed: bytes) -> np.ndarray:
    """Immutable p120 word/dust site index per family seed.

    The color analog of the K ``_site_lookup`` geometry cache
    (color-payload:04): the ``(64, 64)`` furniture lookup — word sites
    0..99, dust sites 100..119, payload -1 — is a pure function of the
    family seed and was previously re-derived on every reference-state
    call.
    """
    word, dust = pilots.color_site_cells_yx(family_seed)
    lookup = np.full((64, 64), -1, np.int16)
    lookup[word[:, 0], word[:, 1]] = np.arange(100, dtype=np.int16)
    lookup[dust[:, 0], dust[:, 1]] = (
        100 + np.arange(20, dtype=np.int16))
    return _readonly(lookup, np.int16)


def color_reference_states(
    spec: FormatSpec,
    page: int,
    cells_yx: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return canonical state and furniture kind for absolute page cells.

    State ``-1`` and kind ``-1`` identify payload.  Kinds 0 and 1 identify
    the BCH word and color dust respectively.
    """
    _color_kind(spec)
    cells = np.asarray(cells_yx, np.int64)
    if cells.ndim != 2 or cells.shape[1:] != (2,):
        raise ValueError("color payload: reference cells must have shape (N,2)")
    states = np.full(cells.shape[0], -1, np.int8)
    kinds = np.full(cells.shape[0], -1, np.int8)
    if not cells.size:
        return states, kinds
    lookup = _color_site_lookup(spec.family_seed)
    local_y = cells[:, 0] % 64
    local_x = cells[:, 1] % 64
    index = lookup[local_y, local_x]
    known = np.flatnonzero(index >= 0)
    if known.size:
        tys = cells[known, 0] // 64
        txs = cells[known, 1] // 64
        code = tys * spec.layout.tiles_yx[1] + txs
        for tile_code in np.unique(code):
            selected = known[code == tile_code]
            ty, tx = divmod(int(tile_code), spec.layout.tiles_yx[1])
            counter = spec.tile_counter(page, ty, tx)
            word_states = pilots.color_word_states(
                spec.seed, (counter,))[0]
            dust_states = pilots.dust_state_values(
                spec.seed, (counter,), spec.codec)[0]
            site = index[selected]
            is_word = site < 100
            if np.any(is_word):
                rows = selected[is_word]
                states[rows] = word_states[site[is_word]]
                kinds[rows] = 0
            if np.any(~is_word):
                rows = selected[~is_word]
                states[rows] = dust_states[site[~is_word] - 100]
                kinds[rows] = 1
    return states, kinds


def _neighbor_rows(local_cells_yx: np.ndarray) -> np.ndarray:
    """Precompute each row's 3x3 neighborhood once per E022 window."""
    local = np.asarray(local_cells_yx, np.int64)
    output = np.full((local.shape[0], 9), -1, np.int32)
    if not local.shape[0]:
        return _readonly(output, np.int32)
    lookup = np.full(
        (int(local[:, 0].max()) + 1, int(local[:, 1].max()) + 1),
        -1,
        np.int32,
    )
    lookup[local[:, 0], local[:, 1]] = np.arange(
        local.shape[0], dtype=np.int32)
    ordinal = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            y = local[:, 0] + dy
            x = local[:, 1] + dx
            valid = (
                (y >= 0) & (y < lookup.shape[0])
                & (x >= 0) & (x < lookup.shape[1])
            )
            output[valid, ordinal] = lookup[y[valid], x[valid]]
            ordinal += 1
    return _readonly(output, np.int32)


def _label_site_rows(
    spec: FormatSpec,
    page: int,
    patch: PlacedPatch,
    aligned: _WindowRows,
    certificate_index: dict[
        tuple[int, int, int], tuple[TileCertificateRecord, ...]
    ],
) -> _Rows | None:
    """Build one observation-free label row over format-known sites only.

    Pool law (RECEIVE-DESIGN §8.2, v0.35) L2/L3/L6: a certified-complete
    window and a D7 label placement both contribute ONLY their word/dust
    furniture sites to the region QDA/PAVA fit — no payload-cell sampling,
    no owner rows, no evidence blocks, no attempts.  Dependencies record
    every covered tile's certificates directly (no projection is built:
    there are no payload cells to overlay) so the region fit population
    shaped by their authority stays on the certificate lineage.  ``None``
    when the window covers no format-known site (nothing can join the fit;
    the placement still joins the region pitch pool by pose).
    """
    states, kinds = color_reference_states(spec, page, aligned.page_cells_yx)
    keep = np.flatnonzero(kinds >= 0)
    if not keep.size:
        return None
    local_cells_yx = aligned.local_cells_yx[keep]
    page_cells_yx = aligned.page_cells_yx[keep]
    site_states = states[keep]
    tiles_x = spec.layout.tiles_yx[1]
    tile_codes = np.unique(
        (page_cells_yx[:, 0].astype(np.int64) // 64) * tiles_x
        + page_cells_yx[:, 1].astype(np.int64) // 64)
    dependencies = tuple(sorted({
        record.certificate_id
        for code in tile_codes
        for record in certificate_index.get(
            (page, *divmod(int(code), tiles_x)), ())
    }))
    return _Rows(
        patch,
        local_cells_yx,
        page_cells_yx,
        aligned.scan_points_yx[keep],
        _readonly(site_states, np.int8),
        _readonly(kinds[keep], np.int8),
        _readonly(channel.states_to_planes(site_states), np.uint8),
        _readonly(np.ones((keep.size, 3), np.bool_), np.bool_),
        _neighbor_rows(local_cells_yx),
        dependencies,
    )


def _valid_correlations(
    images: np.ndarray,
    kernels: np.ndarray,
    pairs: tuple[tuple[int, int], ...],
    valid_yx: tuple[int, int],
) -> np.ndarray:
    """``len(pairs)`` VALID cross-correlations, in one batched transform.

    ``images`` is ``(k, h, w)``, ``kernels`` is ``(m, th, tw)``, and each
    ``(image, kernel)`` pair in ``pairs`` yields one ``valid_yx`` map --
    so an image or a kernel used by several pairs is transformed ONCE.

    The transform length is the IMAGE's own ``next_fast_len``, not the
    full linear length ``h + th - 1``, and that is exact rather than a
    tolerance: circular wrap at length ``N >= h`` folds full-convolution
    index ``k >= N`` onto ``k - N``, which lands at or below ``th - 2``,
    strictly before the valid region's first index ``th - 1``.  Nothing
    the valid window reads was ever written by an aliased sample.
    """
    height, width = images.shape[-2:]
    kernel_h, kernel_w = kernels.shape[-2:]
    fshape = (next_fast_len(height, True), next_fast_len(width, True))
    image_spectra = rfftn(images, fshape, axes=(-2, -1))
    kernel_spectra = rfftn(kernels[:, ::-1, ::-1], fshape, axes=(-2, -1))
    products = np.stack([
        image_spectra[image] * kernel_spectra[kernel]
        for image, kernel in pairs])
    return irfftn(products, fshape, axes=(-2, -1))[
        :, kernel_h - 1:kernel_h - 1 + valid_yx[0],
        kernel_w - 1:kernel_w - 1 + valid_yx[1]]


def _weighted_ncc_surface(
    window: np.ndarray,
    template: np.ndarray,
    weight: np.ndarray,
) -> np.ndarray:
    """Weighted NCC of ``template`` against every valid shift of ``window``.

    The historical form of this was a sliding-window view: materialize
    every ``(th, tw)`` patch and contract three ``einsum``s over them.
    That is O(shifts x template) with the template read once per shift,
    and a TILE_FRAGMENT template is a whole 64-cell tile -- 384x384
    rectified pixels on a c3 sheet -- so the shipped density spent 12.12
    ms per probe there (INDEPENDENT-PLANES §2.9b).

    Written out, each shift's weighted NCC needs only three sums over the
    patch, and every one of them is a CORRELATION of the window (or its
    square) with a fixed kernel:

        A  = sum(P * Tw)          window   x weighted centred template
        S1 = sum(P * w)           window   x weights
        S2 = sum(P * P * w)       window^2 x weights

    from which ``mean = S1 / wsum``, ``numerator = A - mean * sum(Tw)``
    and ``norm^2 = S2 - 2*mean*S1 + mean^2 * sum(w)`` -- the same
    quantities the sliding form contracted, in raw rather than centred
    coordinates.  Two images and two kernels transform once each and the
    three products share one inverse (:func:`_valid_correlations`).

    The scalars around the correlations (the template's own centring and
    norm, the ``1e-9`` guards) are computed exactly as before, so the
    only difference from the sliding form is floating-point summation
    ORDER.

    THE WINDOW IS CENTRED FIRST, and that is arithmetic and not taste: a
    weighted NCC is exactly invariant to a constant added to the patch
    (it cancels in ``P - mean``), but the raw second moment is NOT --
    ``S2 - 2*mean*S1 + mean^2*W`` differences quantities of size
    ``mu^2 * W`` to recover a variance of size ``contrast^2 * W``, so it
    loses the patch's variation entirely once the contrast falls below
    about ``sqrt(eps)`` of the mean level.  Subtracting the window's own
    mean makes both sides the same size and the cancellation goes away;
    MEASURED, it is what carries the agreement with the sliding oracle
    from 1e-6 contrast (where the raw form is already wrong by 7e-4)
    down to 1e-12 and below.  Real scan patches never get there -- the
    sensor's own noise is thousands of times larger -- which is why the
    fix is cheap insurance rather than a discovered bug.

    MEASURED against the sliding oracle kept in
    ``tests/holo/test_color_ncc_fft.py``: identical integer peak on every
    randomized case (square and rectangular templates, both polarities,
    0/1 fragment masks, soft anchor weights, pure noise, contrast down to
    1e-9), surfaces agreeing to 3.4e-15 -- 3.1e-13 on a window with
    LITERALLY no variation, where the correlation is 0/0 and both forms
    return dust below q = 2e-3 that every caller's quality floor (0.10
    anchors, 0.30 probes) rejects.  And on the real W6 sheet-I lane
    (INDEPENDENT-PLANES §2.9c): same site and probe counts, every field
    and pose-residual statistic within 3.4e-15 dot, at 10.53 -> 3.86
    ms/probe.
    """
    wgt = np.asarray(weight, np.float64)
    wsum = float(wgt.sum()) + 1e-9
    centered_template = np.asarray(template, np.float64)
    centered_template = (
        centered_template
        - float((centered_template * wgt).sum()) / wsum
    )
    weighted_template = centered_template * wgt
    th, tw = template.shape
    n_y = window.shape[0] - th + 1
    n_x = window.shape[1] - tw + 1
    template_norm = np.sqrt(
        (centered_template * weighted_template).sum()) + 1e-9
    pixels = np.asarray(window, np.float64)
    pixels = pixels - float(pixels.mean())
    correlated = _valid_correlations(
        np.stack((pixels, pixels * pixels)),
        np.stack((weighted_template, wgt)),
        ((0, 0), (0, 1), (1, 1)),
        (n_y, n_x))
    means = correlated[1] / wsum
    numerator = correlated[0] - means * float(weighted_template.sum())
    # Algebraically a sum of weighted squares, so a negative value is
    # cancellation on a patch with no variation at all -- clamped, not
    # rescued: its numerator is the same size and the guarded denominator
    # carries both to a correlation of zero.
    norm = np.sqrt(np.maximum(
        correlated[2] - 2.0 * means * correlated[1]
        + means * means * float(wgt.sum()),
        0.0))
    return numerator / (norm * template_norm + 1e-9)


def _xcorr_offset_ncc(
    window: np.ndarray,
    template: np.ndarray,
    weight: np.ndarray,
) -> tuple[float, float, float]:
    """Weighted NCC peak with parabolic sub-pixel refinement."""
    th, tw = template.shape
    n_y = window.shape[0] - th + 1
    n_x = window.shape[1] - tw + 1
    corr = _weighted_ncc_surface(window, template, weight)
    iy, ix = np.unravel_index(int(np.argmax(corr)), corr.shape)

    def parabola(values: np.ndarray, index: int) -> float:
        if 0 < index < values.size - 1:
            left, center, right = values[
                index - 1:index + 2]
            denominator = left - 2.0 * center + right
            if abs(float(denominator)) > 1e-12:
                return float(np.clip(
                    (left - right) / (2.0 * denominator), -0.5, 0.5))
        return 0.0

    sy = parabola(corr[:, ix], iy)
    sx = parabola(corr[iy, :], ix)
    return (
        iy + sy - (n_y - 1) / 2.0,
        ix + sx - (n_x - 1) / 2.0,
        float(corr[iy, ix]),
    )


def _rectified_ncc(
    raster: RawRGBRaster,
    patch: PlacedPatch,
    spec: FormatSpec,
    centre_local_yx: tuple[float, float],
    bits: np.ndarray,
    weights: np.ndarray,
    plane: int,
) -> tuple[np.ndarray, float] | None:
    """Weighted NCC of one plane against a known-ink block, in print dots.

    The historical anchor measurement, generalized over the template
    SHAPE so one rectified frame serves every caller: ``_measure_anchor``'s
    3x3 detected-ink neighbourhood, the PLANE-FIELDS W4 square densities
    (5x5 block, 64x64 whole tile), and the TILE_FRAGMENT density, whose
    template is whatever rectangle of a certified tile one window covers
    (:mod:`holo.receive.color_probes`).  ``bits``/``weights`` share one
    ``(height, width)`` in CELLS; the template is centred at the LOCAL
    cell position ``centre_local_yx`` -- integral for an odd extent,
    half-integral for an even one.  A square template takes exactly the
    arithmetic it took while this function accepted squares only.  The
    returned offset is ``(dx, dy)`` in print dots along the window's
    LOCAL axes -- no quality gate is applied here, because the callers
    gate at different floors.
    """
    if bits.ndim != 2 or weights.shape != bits.shape:
        raise ValueError(
            "color payload: NCC template and weights must share one "
            "2-D cell shape")
    height, width = int(bits.shape[0]), int(bits.shape[1])
    cell_px = _RECTIFIED_PX_PER_DOT * spec.cell_dots
    max_shift = max(
        2, round(_ANCHOR_MAX_SHIFT_PX * cell_px / 6.0))
    window_rows = height * cell_px + 2 * max_shift
    window_columns = width * cell_px + 2 * max_shift
    local_y = (
        float(centre_local_yx[0]) - height / 2.0
        + (np.arange(window_rows, dtype=np.float64)[:, None]
           - max_shift + 0.5) / cell_px
    )
    local_x = (
        float(centre_local_yx[1]) - width / 2.0
        + (np.arange(window_columns, dtype=np.float64)[None, :]
           - max_shift + 0.5) / cell_px
    )
    local_y, local_x = np.broadcast_arrays(local_y, local_x)
    local_points = np.stack(
        (local_y.ravel(), local_x.ravel()), axis=1)
    scan = patch.segment.segment.pose.points(local_points)
    y0, x0, rgb = _native_crop(raster, scan, 2)
    crop_points = scan - np.asarray((y0, x0), np.float64)
    if (np.any(crop_points[:, 0] < 0.0)
            or np.any(crop_points[:, 1] < 0.0)
            or np.any(crop_points[:, 0] > rgb.shape[0] - 1)
            or np.any(crop_points[:, 1] > rgb.shape[1] - 1)):
        return None
    window = ndimage.map_coordinates(
        rgb[..., plane], crop_points.T,
        order=1, mode="nearest", output=np.float64,
    ).reshape(window_rows, window_columns)
    template = np.kron(
        1.0 - bits.astype(np.float64),
        np.ones((cell_px, cell_px), np.float64))
    pixel_weights = np.kron(
        weights, np.ones((cell_px, cell_px), np.float64))
    dy, dx, quality = _xcorr_offset_ncc(
        window, template, pixel_weights)
    # NCC runs on a fixed two-pixel-per-print-dot rectification.  Fit in
    # print-dot units so the historical 0.5 inlier gate means the same
    # thing at every receiver lane.
    offset_dots_xy = np.asarray(
        (dx / _RECTIFIED_PX_PER_DOT,
         dy / _RECTIFIED_PX_PER_DOT),
        np.float64,
    )
    return offset_dots_xy, quality


def _measure_anchor(
    raster: RawRGBRaster,
    rows: _Rows,
    row_index: int,
    plane: int,
    detected: np.ndarray,
    confident: np.ndarray,
    spec: FormatSpec,
) -> tuple[np.ndarray, float] | None:
    local = np.asarray(rows.local_cells_yx, np.int64)
    center = local[row_index]
    neighbor_indices = rows.neighbor_indices[row_index]
    if np.any(neighbor_indices < 0):
        return None
    bits = detected[neighbor_indices, plane].reshape(3, 3).copy()
    weights = np.where(
        confident[neighbor_indices, plane].reshape(3, 3),
        1.0, 0.05)
    bits[1, 1] = 1
    weights[1, 1] = 1.0
    if bits.min() == bits.max():
        return None
    measured = _rectified_ncc(
        raster, rows.patch, spec,
        (int(center[0]), int(center[1])), bits, weights, plane)
    if measured is None or measured[1] < _ANCHOR_MIN_Q:
        return None
    return measured


@dataclass(frozen=True, slots=True)
class RegistrationAnchors:
    """One plane's per-anchor NCC field behind ``_fit_registration``.

    The PK6/A2 measure-first return (COLOR-UPLIFT-PLAN §8): exactly the
    measurements the residual fit consumes, in canonical key order.  Rows
    align across arrays; ``window_index`` indexes the caller's row tuple
    and ``bucket`` is the anchor class (0 word, 1 dust, 2 pre-lane
    certificate).  Transient like every anchor product here — consumers
    are instrumentation and a future window-registration arm, never
    persistence.
    """

    page: np.ndarray
    cell_yx: np.ndarray
    window_index: np.ndarray
    offset_dots_xy: np.ndarray
    quality: np.ndarray
    bucket: np.ndarray

    @classmethod
    def empty(cls) -> "RegistrationAnchors":
        return cls(
            page=_readonly(np.zeros(0), np.int64),
            cell_yx=_readonly(np.zeros((0, 2)), np.int64),
            window_index=_readonly(np.zeros(0), np.int64),
            offset_dots_xy=_readonly(np.zeros((0, 2)), np.float64),
            quality=_readonly(np.zeros(0), np.float64),
            bucket=_readonly(np.zeros(0), np.int8),
        )


def _select_registration_candidates(
    candidates: dict[
        int,
        dict[tuple[int, int, int], tuple[int, int]],
    ],
) -> tuple[tuple[tuple[int, int, int], int, int, int], ...]:
    """Select a bounded, replay-stable NCC workload per anchor class.

    Word, dust, and pre-lane-certificate candidates remain distinct classes.
    Within each class canonical page/cell order is divided into
    ``_ANCHOR_BUDGET_PER_KIND`` equal-width bins and the left edge of every
    bin is selected.  Detector fitting still consumes every known site; this
    bound applies only to the substantially more expensive NCC registration
    measurements.  The anchor's class rides along for the per-anchor
    return; selection itself is untouched.
    """
    selected: list[tuple[tuple[int, int, int], int, int, int]] = []
    for bucket in (0, 1, 2):
        ordered = tuple(sorted(candidates[bucket].items()))
        if len(ordered) > _ANCHOR_BUDGET_PER_KIND:
            indices = (
                np.arange(_ANCHOR_BUDGET_PER_KIND, dtype=np.int64)
                * len(ordered)
                // _ANCHOR_BUDGET_PER_KIND
            )
            ordered = tuple(ordered[int(index)] for index in indices)
        selected.extend(
            (key, window_index, row_index, bucket)
            for key, (window_index, row_index) in ordered)
    return tuple(selected)


def _fit_registration(
    raster: RawRGBRaster,
    rows: tuple[_Rows, ...],
    base_features: tuple[np.ndarray, ...],
    spec: FormatSpec,
) -> tuple[
    tuple[PlaneResidual, PlaneResidual, PlaneResidual],
    tuple[RegistrationAnchors, RegistrationAnchors, RegistrationAnchors],
]:
    all_features = np.concatenate(base_features)
    blind_bits = np.empty(all_features.shape, np.bool_)
    blind_llr = np.empty(all_features.shape, np.float64)
    for plane in range(3):
        bits, llr = color_detect.blind_component_bits(
            all_features[:, plane])
        blind_bits[:, plane] = bits.astype(bool)
        blind_llr[:, plane] = llr
    stops = np.cumsum([row.shape[0] for row in base_features])
    starts = np.concatenate((np.asarray([0]), stops[:-1]))
    prepared: list[tuple[np.ndarray, np.ndarray]] = []
    for window, start, stop in zip(rows, starts, stops, strict=True):
        detected = blind_bits[int(start):int(stop)].copy()
        confident = (
            np.abs(blind_llr[int(start):int(stop)])
            >= color_detect.BLIND_CONFIDENT_LLR
        )
        detected[window.known_component_mask] = (
            window.known_component_bits[
                window.known_component_mask].astype(bool))
        confident[window.known_component_mask] = True
        prepared.append((detected, confident))
    residuals: list[PlaneResidual] = []
    anchor_planes: list[RegistrationAnchors] = []
    for plane in range(3):
        anchors: dict[
            tuple[int, int, int],
            tuple[np.ndarray, float, int, int],
        ] = {}
        candidates: dict[
            int,
            dict[tuple[int, int, int], tuple[int, int]],
        ] = {0: {}, 1: {}, 2: {}}
        for window_index, (window, (detected, confident)) in enumerate(
                zip(rows, prepared, strict=True)):
            search = (
                (131 * window.page_cells_yx[:, 0]
                 + 17 * window.page_cells_yx[:, 1]) & 1
            ) == 0
            known_ink = (
                window.known_component_mask[:, plane]
                & window.known_component_bits[:, plane].astype(bool)
                & search
            )
            for row_index in np.flatnonzero(known_ink):
                cell = window.page_cells_yx[row_index]
                key = (
                    window.patch.candidate.page,
                    int(cell[0]),
                    int(cell[1]),
                )
                furniture_kind = int(window.furniture_kind[row_index])
                bucket = (
                    furniture_kind if furniture_kind in (0, 1) else 2)
                candidates[bucket].setdefault(
                    key, (window_index, int(row_index)))

        for key, window_index, row_index, bucket in (
                _select_registration_candidates(candidates)):
            window = rows[window_index]
            detected, confident = prepared[window_index]
            measured = _measure_anchor(
                raster, window, row_index, plane,
                detected, confident, spec)
            if measured is None:
                continue
            # One measurement per canonical page cell by construction
            # (setdefault above dedupes candidates per key), so plain
            # assignment replaces the historically unreachable tie-break.
            anchors[key] = (measured[0], measured[1], window_index, bucket)
        if anchors:
            keys = sorted(anchors)
            ordered = [anchors[key] for key in keys]
            y_fraction = np.asarray(
                [key[1] / spec.layout.cells_yx[0] for key in keys],
                np.float64)
            offsets = np.asarray([row[0] for row in ordered], np.float64)
            quality = np.asarray([row[1] for row in ordered], np.float64)
            anchor_planes.append(RegistrationAnchors(
                page=_readonly([key[0] for key in keys], np.int64),
                cell_yx=_readonly([key[1:] for key in keys], np.int64),
                window_index=_readonly(
                    [row[2] for row in ordered], np.int64),
                offset_dots_xy=_readonly(offsets, np.float64),
                quality=_readonly(quality, np.float64),
                bucket=_readonly([row[3] for row in ordered], np.int8),
            ))
        else:
            y_fraction = np.zeros(0, np.float64)
            offsets = np.zeros((0, 2), np.float64)
            quality = np.zeros(0, np.float64)
            anchor_planes.append(RegistrationAnchors.empty())
        residuals.append(
            fit_plane_residual(y_fraction, offsets, quality))
    return (
        tuple(residuals),  # type: ignore[return-value]
        tuple(anchor_planes),  # type: ignore[return-value]
    )


def _features_with_page_fraction(
    raster: RawRGBRaster,
    rows: _Rows,
    residuals: tuple[PlaneResidual, PlaneResidual, PlaneResidual],
    spec: FormatSpec,
    pitch_px: float,
    divisor: float,
    *,
    offsets_override: tuple[np.ndarray | None, ...] | None = None,
) -> np.ndarray | None:
    """Sample this window's features on the registration-corrected grid.

    ``offsets_override`` is the PLANE-FIELDS W2 seam (docs/PLANE-FIELDS.md
    §6.2): per plane, an ``(N, 2)`` ``(dx, dy)`` print-dot array along
    this window's LOCAL axes that REPLACES the ``PlaneResidual``
    prediction for that plane.  ``None`` -- the whole argument or one
    plane's entry -- is the historical residual branch, bit for bit.
    """
    page_y_fraction = (
        rows.page_cells_yx[:, 0].astype(np.float64)
        / spec.layout.cells_yx[0])
    points_by_plane: list[np.ndarray] = []
    for plane, residual in enumerate(residuals):
        override = (
            None if offsets_override is None else offsets_override[plane])
        offset_dots_xy = (
            residual.offsets(page_y_fraction) if override is None
            else np.asarray(override, np.float64))
        local_delta_yx = (
            offset_dots_xy[:, ::-1] / spec.cell_dots)
        scan_delta_yx = (
            local_delta_yx
            @ rows.patch.segment.segment.pose.matrix().T)
        points = rows.scan_points_yx + scan_delta_yx
        if points.size and (
            np.any(points[:, 0] < 0.0)
            or np.any(points[:, 1] < 0.0)
            or np.any(points[:, 0] > raster.shape[0] - 1)
            or np.any(points[:, 1] > raster.shape[1] - 1)
        ):
            # The shared E022 pose remains usable.  A residual proposal that
            # leaves the available acquisition is simply ineligible.
            return None
        points_by_plane.append(points)
    crop = _points_crop(
        raster, np.concatenate(points_by_plane), pitch_px, divisor)
    result = np.empty((rows.page_cells_yx.shape[0], 3), np.float64)
    for plane, points in enumerate(points_by_plane):
        local = points - np.asarray((crop.y0, crop.x0), np.float64)
        result[:, plane] = ndimage.map_coordinates(
            crop.filtered[..., plane], local.T,
            order=1, mode="nearest")
    return result
