"""E023/E023b payload-window sampling and per-window calibration.

This private module owns the bounded per-window photometric path: window
validation/row alignment, the region-pooled crop/filter aperture, format
reference labels, PAVA calibration, and the pool-law label routing of
``sample_and_calibrate``.  Split from ``_payload_windows.py`` in the
Phase 4 hammer batch (RECEIVE-DESIGN v0.38) together with
:mod:`_payload_context` (region context fit) and :mod:`_payload_reuse`
(refined-generation reuse); ``payload`` keeps the production-facing
evidence-freeze and tile-attempt orchestration surface.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from typing import Callable

import numpy as np
from scipy import ndimage

from ..core import keystream
from ..format import pilots
from ..format.descriptor import FormatSpec
from . import _parallel, detect
from .payload_model import (
    EvidenceSource,
    PlacementModelError,
    RawLumaRaster,
    WindowEvidence,
    _immutable,
    _nonnegative,
)
from .placement.model import AddressResult, PlacedPatch, PlacedSegment


APERTURE_CELLS = 0.7
SCORE_SPREAD_FLOOR = 1e-6


@dataclass(frozen=True, slots=True)
class _WindowCrop:
    y0: int
    x0: int
    filtered: np.ndarray
    fill: float


@dataclass(frozen=True, slots=True)
class _WindowRows:
    segment_id: int
    local_cells_yx: np.ndarray
    page_cells_yx: np.ndarray
    scan_points_yx: np.ndarray


def rotated_points(points_yx: np.ndarray, shape_yx: tuple[int, int],
                   rot_k: int) -> np.ndarray:
    """Exact integer ``np.rot90`` point map used by E022/E023."""
    points = np.asarray(points_yx)
    if points.ndim != 2 or points.shape[1:] != (2,):
        raise ValueError("payload: points must have shape (N,2)")
    if rot_k not in (0, 1, 2, 3):
        raise ValueError("payload: rot_k must be 0, 1, 2, or 3")
    y, x = points[:, 0], points[:, 1]
    height, width = shape_yx
    if rot_k == 0:
        return np.stack((y, x), axis=1)
    if rot_k == 1:
        return np.stack((width - 1 - x, y), axis=1)
    if rot_k == 2:
        return np.stack((height - 1 - y, width - 1 - x), axis=1)
    return np.stack((x, height - 1 - y), axis=1)


def _window_rows(patch: PlacedPatch, spec: FormatSpec) -> _WindowRows:
    """Validate one E022 window and align rows to its authoritative cells."""
    if not isinstance(patch, PlacedPatch):
        raise TypeError("payload: placement must be PlacedPatch")
    page = _nonnegative(patch.candidate.page, "placement page")
    if page >= spec.max_pages:
        raise PlacementModelError(f"patch {patch.patch_id} page is unaddressable")
    if not patch.candidate.passes:
        raise PlacementModelError(
            f"patch {patch.patch_id} carries a rejected address candidate")
    placed = patch.segment
    if not isinstance(placed, PlacedSegment):
        raise PlacementModelError("patch contains a non-PlacedSegment window")
    if placed.rot_k != patch.candidate.rot_k:
        raise PlacementModelError(
            f"patch {patch.patch_id} has inconsistent window orientation")
    if placed.segment.window.region_index != patch.region_index:
        raise PlacementModelError(
            f"patch {patch.patch_id} contains another region's window")
    segment_id = _nonnegative(
        placed.segment.window.window_id, "segment window id")
    height, width = spec.layout.cells_yx
    local = np.asarray(placed.audited_cells_yx, np.int64)
    sy, sx = placed.segment.window.shape_yx_cells
    if (local.ndim != 2 or local.shape[1:] != (2,)
            or np.any(local < 0)
            or np.any(local[:, 0] >= sy)
            or np.any(local[:, 1] >= sx)
            or np.unique(local, axis=0).shape[0] != local.shape[0]):
        raise PlacementModelError(
            f"patch {patch.patch_id} has malformed window audit cells")
    mapped = rotated_points(local, (sy, sx), placed.rot_k)
    mapped += np.asarray(placed.page_origin_yx, np.int64)
    points = placed.segment.pose.points(local.astype(np.float64))
    inside = ((mapped[:, 0] >= 0) & (mapped[:, 0] < height)
              & (mapped[:, 1] >= 0) & (mapped[:, 1] < width))
    mapped_inside = mapped[inside]
    local_inside = local[inside]
    points_inside = points[inside]
    mapped_keys = (
        mapped_inside[:, 0] * np.int64(width) + mapped_inside[:, 1])
    if np.unique(mapped_keys).size != mapped_keys.size:
        raise PlacementModelError(
            f"patch {patch.patch_id} maps two window cells to one page cell")
    authoritative = np.asarray(patch.page_cells_yx, np.int64)
    if (authoritative.ndim != 2 or authoritative.shape[1:] != (2,)
            or np.unique(authoritative, axis=0).shape[0]
            != authoritative.shape[0]):
        raise PlacementModelError(
            f"patch {patch.patch_id} authoritative cells are malformed")
    if authoritative.shape[0] == 0:
        raise PlacementModelError(
            f"patch {patch.patch_id} has no authoritative cells")
    authoritative_inside = (
        (authoritative[:, 0] >= 0)
        & (authoritative[:, 0] < height)
        & (authoritative[:, 1] >= 0)
        & (authoritative[:, 1] < width)
    )
    authoritative_keys = (
        authoritative[:, 0] * np.int64(width) + authoritative[:, 1])
    if (not np.all(authoritative_inside)
            or authoritative_keys.size != mapped_keys.size
            or not np.array_equal(
                np.sort(authoritative_keys), np.sort(mapped_keys))):
        # Preserve exact two-coordinate diagnostics on the malformed path;
        # flattened keys are only collision-free for in-page coordinates.
        authoritative_set = {
            (int(cell[0]), int(cell[1])) for cell in authoritative}
        mapped_set = {
            (int(cell[0]), int(cell[1])) for cell in mapped_inside}
        missing = len(authoritative_set - mapped_set)
        extra = len(mapped_set - authoritative_set)
        raise PlacementModelError(
            f"patch {patch.patch_id} window cell mismatch "
            f"(missing={missing}, extra={extra})")
    mapped_order = np.argsort(mapped_keys)
    source_rows = mapped_order[
        np.searchsorted(mapped_keys[mapped_order], authoritative_keys)]
    return _WindowRows(
        segment_id,
        _immutable(local_inside[source_rows], np.int32),
        _immutable(authoritative, np.int32),
        _immutable(points_inside[source_rows], np.float64),
    )


def _window_label_only(
    rows: _WindowRows,
    labels: np.ndarray,
    page: int,
    spec: "FormatSpec",
    terminal_addresses: frozenset[tuple[int, int, int]],
) -> bool:
    """True when the window owes no payload work under the pool law.

    Pool law (RECEIVE-DESIGN §8.2, v0.35): L4 — a zero-payload
    (all-reference) window is label-only ALWAYS, independent of any
    certificate's existence; L2 — a window whose payload cells all lie on
    certified tiles does no payload work (no owner rows, no blocks, no
    attempts).  Either way the window is routed through the label channel:
    its format-known word/filler sites still join the region context fit
    (the c7aa340 window-granular skip erased that contribution; the
    ownership/block/attempt savings stand).
    """
    payload = np.asarray(labels, np.int64) < 0
    if not payload.any():
        return True
    if not terminal_addresses:
        return False
    cells = np.asarray(rows.page_cells_yx, np.int64)
    tiles_x = spec.layout.tiles_yx[1]
    codes = (cells[payload, 0] // 64) * tiles_x + cells[payload, 1] // 64
    terminal_codes = np.asarray(sorted(
        ty * tiles_x + tx
        for tpage, ty, tx in terminal_addresses if tpage == page
    ), np.int64)
    if not terminal_codes.size:
        return False
    return bool(np.isin(codes, terminal_codes).all())


def _window_crop(
    raster: RawLumaRaster,
    patch: PlacedPatch,
    pitch_px: float,
) -> _WindowCrop:
    """Filter one E022 window without spanning the rest of its region."""
    placed = patch.segment
    height, width = placed.segment.window.shape_yx_cells
    local = np.asarray(
        ((0, 0), (0, width), (height, 0), (height, width)),
        np.float64)
    points = placed.segment.pose.points(local)
    halo = int(np.ceil(APERTURE_CELLS * pitch_px)) + 2
    y0 = max(0, int(np.floor(points[:, 0].min())) - halo)
    x0 = max(0, int(np.floor(points[:, 1].min())) - halo)
    y1 = min(int(raster.shape[0]), int(np.ceil(points[:, 0].max())) + halo)
    x1 = min(int(raster.shape[1]), int(np.ceil(points[:, 1].max())) + halo)
    if y1 <= y0 or x1 <= x0:
        raise PlacementModelError("payload region extent misses the raster")
    raw = np.asarray(raster.crop_luma(y0, y1, x0, x1), np.float32)
    if raw.shape != (y1 - y0, x1 - x0) or not np.isfinite(raw).all():
        raise ValueError("payload: raster returned malformed raw luma")
    aperture = max(1, int(round(APERTURE_CELLS * pitch_px)))
    filtered = ndimage.uniform_filter(raw, size=aperture, mode="nearest")
    return _WindowCrop(y0, x0, filtered, float(np.median(raw)))


def _sample_window(
    raster: RawLumaRaster,
    patch: PlacedPatch,
    rows: _WindowRows,
    pitch_px: float,
) -> np.ndarray:
    """Return samples while keeping the filtered window strictly transient."""
    crop = _window_crop(raster, patch, pitch_px)
    return _sample_rows(crop, rows, raster.shape)


def _sample_rows(crop: _WindowCrop, rows: _WindowRows,
                 raster_shape: tuple[int, int]) -> np.ndarray:
    points = np.asarray(rows.scan_points_yx, np.float64)
    if points.size and (np.any(points[:, 0] < 0.0)
                        or np.any(points[:, 1] < 0.0)
                        or np.any(points[:, 0] > raster_shape[0] - 1)
                        or np.any(points[:, 1] > raster_shape[1] - 1)):
        raise PlacementModelError(
            "audited payload cell maps outside the source raster")
    local = points - np.asarray((crop.y0, crop.x0), np.float64)
    means = ndimage.map_coordinates(
        crop.filtered, local.T, order=1, cval=crop.fill)
    return np.asarray(means, np.float32)


def _region_pitch(patches: tuple[PlacedPatch, ...]) -> float:
    """Return the exact E023b region aperture pitch (px/cell)."""
    if not patches:
        raise ValueError("payload: a sampled region cannot be empty")
    return float(np.median(tuple(
        row.segment.segment.pose.pitch_px for row in patches)))


def _filter_signature(patches: tuple[PlacedPatch, ...]) -> tuple[int, int]:
    """Integer crop/filter policy induced by a region's median pitch."""
    pitch_px = _region_pitch(patches)
    return (
        int(np.ceil(APERTURE_CELLS * pitch_px)) + 2,
        max(1, int(round(APERTURE_CELLS * pitch_px))),
    )


@cache
def _site_lookup(family_seed: bytes, n_filler: int) -> tuple[np.ndarray,
                                                               np.ndarray]:
    word, filler = pilots.site_cells_yx(family_seed, n_filler)
    kind = np.full((64, 64), -1, np.int16)
    index = np.full((64, 64), -1, np.int16)
    kind[word[:, 0], word[:, 1]] = 0
    index[word[:, 0], word[:, 1]] = np.arange(word.shape[0], dtype=np.int16)
    if filler.size:
        kind[filler[:, 0], filler[:, 1]] = 1
        index[filler[:, 0], filler[:, 1]] = np.arange(
            filler.shape[0], dtype=np.int16)
    return _immutable(kind, np.int16), _immutable(index, np.int16)


def format_reference_values(spec: FormatSpec, page: int,
                            cells_yx: np.ndarray) -> np.ndarray:
    """Predict every colocated site value; cargo remains -1."""
    cells = np.asarray(cells_yx, np.int64)
    values = np.full(cells.shape[0], -1, np.int8)
    if cells.size == 0:
        return values
    kind, site_index = _site_lookup(spec.family_seed, spec.n_filler)
    local_y = cells[:, 0] % 64
    local_x = cells[:, 1] % 64
    classes = kind[local_y, local_x]
    word_rows = np.flatnonzero(classes == 0)
    if word_rows.size:
        tile_y = cells[word_rows, 0] // 64
        tile_x = cells[word_rows, 1] // 64
        tile_code = tile_y * spec.layout.tiles_yx[1] + tile_x
        for code in np.unique(tile_code):
            selected = word_rows[tile_code == code]
            ty, tx = divmod(int(code), spec.layout.tiles_yx[1])
            counter = spec.tile_counter(page, ty, tx)
            word = pilots.word_values(spec.seed, (counter,), spec.plane)[0]
            values[selected] = word[site_index[
                local_y[selected], local_x[selected]]]
    filler_rows = np.flatnonzero(classes == 1)
    if filler_rows.size:
        values[filler_rows] = keystream.bits(
            spec.seed, keystream.DOMAIN_FILLER_VALUES, spec.plane, page,
            cells[filler_rows, 0], cells[filler_rows, 1]).astype(np.int8)
    return values


def _site_ids(spec: FormatSpec, page: int, cells_yx: np.ndarray) -> np.ndarray:
    height, width = spec.layout.cells_yx
    page_area = height * width
    largest = (page + 1) * page_area
    if largest > np.iinfo(np.int64).max:
        raise ValueError("payload: page identity exceeds int64")
    cells = np.asarray(cells_yx, np.int64)
    return page * page_area + cells[:, 0] * width + cells[:, 1]


def _scores(raw_means: np.ndarray) -> np.ndarray:
    """Float32-native window score transform (v0.39, ruling 10.2).

    The whole photometric path is float32 (crop, filter, sampled means),
    matching legacy E023b; the historical holo float64
    compute-then-quantize detour is gone — the stored scores ARE the
    computed scores.  Every constant is spelled ``np.float32`` so numpy's
    weak-scalar rules cannot silently re-widen the arithmetic.  PAVA
    itself (detect.fit_calibration) keeps its own float64 interior,
    exactly as legacy ``pava_calibrate`` consumed float32-valued scores.
    """
    means = np.asarray(raw_means, np.float32)
    midpoint = np.float32(np.median(means))
    spread = max(np.float32(np.abs(means - midpoint).mean()),
                 np.float32(SCORE_SPREAD_FLOOR))
    return (midpoint - means) / spread


def _calibrate(source: EvidenceSource, patch: PlacedPatch, rows: _WindowRows,
               means: np.ndarray, labels: np.ndarray,
               spec: FormatSpec) -> WindowEvidence:
    # Patch ordinals restart at every E023c lane.  Include the stable lane
    # identity so durable window/region identities cannot collide when the
    # same physical scan advances to a finer view.
    placement_id = (
        f"{source.source_sha256}/{source.lane_id}/"
        f"patch-{int(patch.patch_id)}")
    region_id = (
        f"{source.source_sha256}/{source.lane_id}/region-"
        f"{int(patch.region_index)}")
    scores = _scores(means)
    known = labels >= 0
    parity = ((131 * rows.page_cells_yx[:, 0]
               + 17 * rows.page_cells_yx[:, 1]) & 1).astype(bool)
    search_mask = known & ~parity
    heldout_mask = known & parity
    ids = _site_ids(spec, patch.candidate.page, rows.page_cells_yx)
    search = detect.CalibrationObservations(
        placement_id, scores[search_mask], labels[search_mask], ids[search_mask])
    heldout = detect.CalibrationObservations(
        placement_id, scores[heldout_mask], labels[heldout_mask],
        ids[heldout_mask])
    fit = detect.fit_calibration(search, heldout)
    common = dict(
        source=source, placement_id=placement_id, patch_id=int(patch.patch_id),
        region_id=region_id, page=int(patch.candidate.page),
        redundant=bool(patch.redundant), segment_id=rows.segment_id,
        segment_local_cells_yx=rows.local_cells_yx,
        page_cells_yx=rows.page_cells_yx,
        scan_points_yx=rows.scan_points_yx, raw_means=means, scores=scores,
        reference_values=labels, n_search_0=fit.n_search_0,
        n_search_1=fit.n_search_1, n_heldout=fit.n_heldout)
    if not fit.accepted:
        return WindowEvidence(
            calibration_score_nodes=np.zeros(0),
            calibration_probability_nodes=np.zeros(0),
            baseline_printed_llr=np.zeros(0, np.float32),
            printed_llr=np.zeros(0, np.float32), accepted=False,
            refusal_reason=fit.reason, heldout_logloss=None, **common)
    assert fit.calibration is not None and fit.heldout_logloss is not None
    llr = np.asarray(fit.calibration.llr(scores), np.float32)
    heldout_probability = fit.calibration.probability(scores[heldout_mask])
    heldout_labels = labels[heldout_mask].astype(np.float64)
    heldout_loss = float(-np.mean(
        heldout_labels * np.log(heldout_probability)
        + (1.0 - heldout_labels) * np.log(1.0 - heldout_probability)))
    return WindowEvidence(
        calibration_score_nodes=fit.calibration.knots,
        calibration_probability_nodes=fit.calibration.probabilities,
        baseline_printed_llr=llr, printed_llr=llr,
        accepted=True, refusal_reason="",
        heldout_logloss=heldout_loss, **common)


def sample_and_calibrate(
    raster: RawLumaRaster,
    source: EvidenceSource,
    address: AddressResult,
    spec: FormatSpec,
    *,
    included_patch_ids: frozenset[int] | None = None,
    terminal_addresses: frozenset[tuple[int, int, int]] = frozenset(),
    region_progress: Callable[
        [tuple[WindowEvidence, ...], tuple[WindowEvidence, ...]],
        None] | None = None,
) -> tuple[WindowEvidence, ...]:
    """Sample payload-promoted E022 placements one bounded window at a time.

    v0.33 D7: ``address.label_placements`` sample alongside their region's
    promoted placements — the region crop pitch pools over BOTH
    populations, reproducing the single-pass pooled aperture bit-exactly —
    and reach ``region_progress`` as the second argument, never the
    returned evidence.

    Pool law (v0.35): a promoted window that owes no payload work — every
    payload cell on a certified tile (L2) or no payload cells at all
    (L4) — routes through the same label channel instead of vanishing,
    and D7 labels are never terminal-gated (L3).  The returned evidence
    carries payload rows only.
    """
    # Interior seam: typed inputs are trusted (kiss validation-boundary
    # ruling); only the placement-domain invariant is checked below.
    included = included_patch_ids
    all_patch_ids = {
        int(row.patch_id) for row in address.payload_placements
    }
    if included is not None and not included.issubset(all_patch_ids):
        raise ValueError(
            "payload: included patch ids name no promoted placement")
    by_region: dict[int, list[PlacedPatch]] = {}
    for patch in address.payload_placements:
        if included is not None and int(patch.patch_id) not in included:
            continue
        by_region.setdefault(int(patch.region_index), []).append(patch)
    labels_by_region: dict[int, list[PlacedPatch]] = {}
    for patch in address.label_placements:
        labels_by_region.setdefault(int(patch.region_index), []).append(patch)
    output: list[WindowEvidence] = []

    def _evaluate(
        work: tuple[PlacedPatch, float],
    ) -> tuple[bool, WindowEvidence]:
        """One window's sample+calibrate: pure in (patch, region pitch)."""
        patch, pitch_px = work
        is_label = patch.route == "label"
        rows = _window_rows(patch, spec)
        labels = format_reference_values(
            spec, int(patch.candidate.page), rows.page_cells_yx)
        if not is_label and _window_label_only(
                rows, labels, int(patch.candidate.page), spec,
                terminal_addresses):
            # Pool law L2/L4: a certified-complete or zero-payload
            # window does no payload work (no owner rows, no blocks,
            # no attempts) but its format-known sites still join the
            # region fit as a label row.  D7 labels themselves are
            # never terminal-gated (L3).
            is_label = True
        means = _sample_window(raster, patch, rows, pitch_px)
        evidence = _calibrate(source, patch, rows, means, labels, spec)
        return is_label, evidence

    # One flat work list across regions keeps the pooled map saturated
    # on few-window regions; collection is in submission order, so the
    # per-region output/label grouping, region_progress order, and the
    # returned row order are exactly the sequential loop's (pinned by
    # tests/holo/test_parallel_exactness.py).
    region_work: list[tuple[int, int]] = []
    work_items: list[tuple[PlacedPatch, float]] = []
    for region_index in sorted(by_region):
        patches = tuple(sorted(by_region[region_index],
                               key=lambda row: int(row.patch_id)))
        label_patches = tuple(sorted(
            labels_by_region.get(region_index, ()),
            key=lambda row: int(row.patch_id)))
        pitch_px = _region_pitch(patches + label_patches)
        region_work.append((region_index, len(patches + label_patches)))
        work_items.extend(
            (patch, pitch_px) for patch in patches + label_patches)
    evaluated = _parallel.ordered_map(_evaluate, work_items)
    cursor = 0
    for _region_index, n_windows in region_work:
        region_start = len(output)
        label_rows: list[WindowEvidence] = []
        for is_label, evidence in evaluated[cursor:cursor + n_windows]:
            if is_label:
                label_rows.append(evidence)
            else:
                output.append(evidence)
        cursor += n_windows
        if region_progress is not None:
            region_progress(
                tuple(output[region_start:]), tuple(label_rows))
    ids = [row.placement_id for row in output]
    if len(ids) != len(set(ids)):
        raise PlacementModelError("E022 patch ids are not stable/unique")
    return tuple(output)
