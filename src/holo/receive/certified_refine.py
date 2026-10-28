"""Certified-field pose refinement for the Track-3 scale cascade.

This is the numerical E023c forward-refinement seam.  It intentionally owns
no scheduling or persistence: generation zero must already have completed,
the caller supplies a snapshot of certificates from earlier barriers, and an
adopted proposal must be followed by one ordinary E023b rerun from pixels.

The algorithm is E023c's qualified single forward pose proposal, expressed
through Track 3's local ``PoseSegment`` ownership.  It is not the iterative
E024 feedback loop.  Page, integer page origin, orientation, audited cells,
detector, and every other segment remain frozen.  Candidate geometry is a
bounded rotation and sub-cell translation of one segment only.  It is trained
on authoritative pilots plus re-encoded certified printed cargo and adopted
only on held-out detector gain and two pilot non-regression gates.

All photometry is raw luma.  ``mid - raw_luma`` is merely the historical
ink-positive detector score; there is no normalized-darkness transform.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Iterable, Mapping

import numpy as np
from scipy import ndimage

from ..format.descriptor import FormatSpec
from . import detect, tiles
from ._payload_sampling import SCORE_SPREAD_FLOOR
from .payload import APERTURE_CELLS, format_reference_values
from .payload_model import (
    CONTEXT_PROFILE,
    PAVA_PROFILE,
    ContextDecision,
    RawLumaRaster,
    WindowEvidence,
)
from .placement.model import AffinePose, PlacedSegment, PoseSegment
from .placement.reference import rotate_points
from .evidence import TileCertificateRecord
from .records import printed_cells_from_record


BLOCK_CELLS = 16
VALIDATION_MODULUS = 4
MIN_PAYLOAD_TRAIN = 64
MIN_PAYLOAD_VALIDATION = 32
MIN_TRAIN_PER_CLASS = 20
MIN_VALIDATION_PER_CLASS = 10
MIN_CERTIFIED_BLOCKS = 4
# E023c called the historical arm with SearchConfig.min_support=30.  This is
# deliberately not lowered merely because Track 3 owns shorter local poses.
MIN_POSE_PILOTS = 30
MIN_HELDOUT_GAIN = 1e-4
PILOT_MISMATCH_SLACK = 0.005
ANGLE_LIMIT_DEG = 0.15
ANGLE_COARSE_STEP_DEG = 0.15
ANGLE_FINE_STEP_DEG = 0.05
PHASE_LIMIT_CELLS = 0.25
PHASE_COARSE_STEP_CELLS = 0.25
PHASE_FINE_STEP_CELLS = 0.0625
POSE_SITE_CAP_TRAIN = 2048
POSE_SITE_CAP_VALIDATION = 1024


class RefinementIntegrityError(ValueError):
    """Frozen E022/E023b substrate cannot be replayed exactly."""


def _readonly(value: np.ndarray, dtype: np.dtype | type) -> np.ndarray:
    array = np.ascontiguousarray(value, dtype=dtype)
    return np.frombuffer(array.tobytes(), dtype=np.dtype(dtype)).reshape(
        array.shape
    )


@dataclass(frozen=True, slots=True)
class CertifiedTileLabels:
    """One validated certificate's exact printed 64x64 field."""

    address: tuple[int, int, int]
    certificate_id: str
    printed_cells: np.ndarray

    def __post_init__(self) -> None:
        if (len(self.address) != 3 or any(
                isinstance(value, (bool, np.bool_))
                or not isinstance(value, (int, np.integer))
                or int(value) < 0 for value in self.address)):
            raise ValueError("certified labels need a non-negative tile address")
        if (len(self.certificate_id) != 64 or any(
                char not in "0123456789abcdef"
                for char in self.certificate_id)):
            raise ValueError("certificate identity must be lowercase SHA-256")
        cells = np.asarray(self.printed_cells)
        if cells.shape != (64, 64) or not np.all((cells == 0) | (cells == 1)):
            raise ValueError("certified printed field must be a 64x64 bit array")
        object.__setattr__(self, "address", tuple(int(v) for v in self.address))
        object.__setattr__(self, "printed_cells", _readonly(cells, np.uint8))


@dataclass(frozen=True, slots=True, init=False)
class CertificateFrontier:
    """Validated, conflict-free snapshot from prior level barriers only."""

    spec_id: str
    frontier_id: str
    certificate_ids: tuple[str, ...]
    tiles: tuple[CertifiedTileLabels, ...]
    _by_address: Mapping[
        tuple[int, int, int], CertifiedTileLabels
    ] = field(init=False, repr=False, compare=False)

    @classmethod
    def from_certificates(
        cls, spec: FormatSpec,
        certificates: "Iterable[TileCertificateRecord]",
    ) -> "CertificateFrontier":
        if not isinstance(spec, FormatSpec):
            raise TypeError("certificate frontier requires FormatSpec")
        by_address: dict[tuple[int, int, int], TileCertificateRecord] = {}
        for record in certificates:
            address = (record.page, *record.tile_yx)
            prior = by_address.get(address)
            if prior is not None:
                if prior.packed_user_bits != record.packed_user_bits:
                    raise tiles.CertificateConflict(
                        "conflicting certified printed fields at tile "
                        f"{address}"
                    )
                continue
            by_address[address] = record
        rows = tuple(
            # The certified user bits become the complete printed field,
            # including sites and absolute-address payload scramble; the
            # records-module mint-once cache means each certificate
            # LDPC-re-encodes at most once per process (Phase 3.2).
            CertifiedTileLabels(address, record.certificate_id,
                                printed_cells_from_record(record, spec))
            for address, record in sorted(by_address.items())
        )
        identities = tuple(sorted(row.certificate_id for row in rows))
        frontier = object.__new__(cls)
        object.__setattr__(frontier, "spec_id", spec.spec_id)
        object.__setattr__(
            frontier, "frontier_id", tiles.dependency_identity(identities)
        )
        object.__setattr__(frontier, "certificate_ids", identities)
        object.__setattr__(frontier, "tiles", rows)
        frontier.__post_init__()
        return frontier

    def __post_init__(self) -> None:
        if not self.spec_id:
            raise ValueError("certificate frontier needs a format identity")
        if (len(self.frontier_id) != 64 or any(
                char not in "0123456789abcdef" for char in self.frontier_id)):
            raise ValueError("certificate frontier needs a SHA-256 identity")
        if tuple(sorted(set(self.certificate_ids))) != self.certificate_ids:
            raise ValueError("certificate frontier identities must be sorted unique")
        addresses = tuple(row.address for row in self.tiles)
        identities = tuple(sorted(row.certificate_id for row in self.tiles))
        if (tuple(sorted(addresses)) != addresses
                or len(set(addresses)) != len(addresses)
                or identities != self.certificate_ids
                or tiles.dependency_identity(self.certificate_ids)
                != self.frontier_id):
            raise ValueError("certificate frontier is not canonical")
        object.__setattr__(self, "_by_address", MappingProxyType({
            row.address: row for row in self.tiles
        }))

    def by_address(self) -> Mapping[
        tuple[int, int, int], CertifiedTileLabels
    ]:
        return self._by_address


@dataclass(frozen=True, slots=True)
class RefinementRegionImage:
    """One current-E023 raw-luma crop after the 0.7-cell box aperture."""

    region_index: int
    y0: int
    x0: int
    raster_shape: tuple[int, int]
    filtered_luma: np.ndarray
    fill_luma: float

    def __post_init__(self) -> None:
        for name in ("region_index", "y0", "x0"):
            value = getattr(self, name)
            if (isinstance(value, (bool, np.bool_))
                    or not isinstance(value, (int, np.integer))
                    or int(value) < 0):
                raise ValueError(f"{name} must be a non-negative integer")
        if (len(self.raster_shape) != 2
                or min(self.raster_shape) < 1
                or self.y0 >= self.raster_shape[0]
                or self.x0 >= self.raster_shape[1]):
            raise ValueError("invalid refinement raster extent")
        image = np.asarray(self.filtered_luma)
        if (image.ndim != 2 or min(image.shape, default=0) < 1
                or self.y0 + image.shape[0] > self.raster_shape[0]
                or self.x0 + image.shape[1] > self.raster_shape[1]
                or not np.isfinite(image).all()
                or not np.isfinite(self.fill_luma)):
            raise ValueError("malformed refinement luma crop")
        object.__setattr__(self, "region_index", int(self.region_index))
        object.__setattr__(self, "y0", int(self.y0))
        object.__setattr__(self, "x0", int(self.x0))
        object.__setattr__(self, "raster_shape", tuple(
            int(v) for v in self.raster_shape
        ))
        object.__setattr__(self, "filtered_luma", _readonly(image, np.float32))
        object.__setattr__(self, "fill_luma", float(self.fill_luma))


def prepare_region_image(
    raster: RawLumaRaster,
    region_index: int,
    segments: Iterable[PoseSegment],
) -> RefinementRegionImage:
    """Prepare the same raw-luma/aperture substrate as current E023.

    Integration should pass every segment in the E021 region so the median
    aperture pitch and crop are identical to generation zero.
    """
    rows = tuple(segments)
    if not rows:
        raise ValueError("refinement region needs at least one pose segment")
    if any(row.window.region_index != region_index for row in rows):
        raise ValueError("refinement crop mixes E021 regions")
    corners: list[np.ndarray] = []
    pitches: list[float] = []
    for segment in rows:
        height, width = segment.window.shape_yx_cells
        local = np.asarray(
            ((0, 0), (0, width), (height, 0), (height, width)), np.float64
        )
        corners.append(segment.pose.points(local))
        pitches.append(float(segment.pose.pitch_px))
    points = np.concatenate(corners)
    pitch_px = float(np.median(pitches))
    halo = int(np.ceil(APERTURE_CELLS * pitch_px)) + 2
    y0 = max(0, int(np.floor(points[:, 0].min())) - halo)
    x0 = max(0, int(np.floor(points[:, 1].min())) - halo)
    y1 = min(int(raster.shape[0]), int(np.ceil(points[:, 0].max())) + halo)
    x1 = min(int(raster.shape[1]), int(np.ceil(points[:, 1].max())) + halo)
    if y1 <= y0 or x1 <= x0:
        raise ValueError("refinement pose extent misses the source raster")
    raw = np.asarray(raster.crop_luma(y0, y1, x0, x1), np.float32)
    if raw.shape != (y1 - y0, x1 - x0) or not np.isfinite(raw).all():
        raise ValueError("refinement raster returned malformed raw luma")
    aperture = max(1, int(round(APERTURE_CELLS * pitch_px)))
    filtered = ndimage.uniform_filter(raw, size=aperture, mode="nearest")
    return RefinementRegionImage(
        region_index, y0, x0, tuple(int(v) for v in raster.shape),
        filtered, float(np.median(raw)),
    )


@dataclass(frozen=True, slots=True)
class SegmentRefinementRequest:
    """Frozen discrete/address and generation-zero facts for one segment."""

    placed: PlacedSegment
    generation0: WindowEvidence
    context_decision: ContextDecision | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.placed, PlacedSegment):
            raise TypeError("refinement request needs PlacedSegment")
        if not isinstance(self.generation0, WindowEvidence):
            raise TypeError("refinement request needs generation-zero evidence")
        if not self.generation0.accepted:
            raise ValueError("refinement requires an accepted generation-zero detector")
        segment_id = self.placed.segment.window.window_id
        if self.generation0.segment_id != segment_id:
            raise ValueError("generation zero names another window")
        decision = self.context_decision
        if self.generation0.detector_profile == CONTEXT_PROFILE:
            if (not isinstance(decision, ContextDecision)
                    or not decision.adopted
                    or decision.decision_id
                    != self.generation0.context_decision_id
                    or decision.region_id != self.generation0.region_id):
                raise ValueError("context generation zero needs its adopted decision")
        elif self.generation0.detector_profile != PAVA_PROFILE:
            raise ValueError("unknown generation-zero detector profile")


@dataclass(frozen=True, slots=True)
class SegmentLabels:
    """Authoritative pilot and certified-cargo labels for one segment."""

    generation_rows: np.ndarray
    page_cells_yx: np.ndarray
    values: np.ndarray
    validation: np.ndarray
    weights: np.ndarray
    is_pilot: np.ndarray
    block_ids: np.ndarray
    certificate_ids: tuple[str | None, ...]

    def __post_init__(self) -> None:
        n = np.asarray(self.generation_rows).size
        fields = (
            ("generation_rows", self.generation_rows, np.int64, (n,)),
            ("page_cells_yx", self.page_cells_yx, np.int64, (n, 2)),
            ("values", self.values, np.uint8, (n,)),
            ("validation", self.validation, bool, (n,)),
            ("weights", self.weights, np.float64, (n,)),
            ("is_pilot", self.is_pilot, bool, (n,)),
            ("block_ids", self.block_ids, np.int64, (n,)),
        )
        for name, value, dtype, shape in fields:
            array = np.asarray(value)
            if array.shape != shape:
                raise ValueError(f"{name} must have shape {shape}")
            object.__setattr__(self, name, _readonly(array, dtype))
        if (len(self.certificate_ids) != n
                or not np.all(np.isfinite(self.weights))
                or np.any(self.weights <= 0.0)
                or not np.all(np.isin(self.values, (0, 1)))):
            raise ValueError("malformed segment labels")

    @property
    def train(self) -> np.ndarray:
        return ~self.validation

    @property
    def dependency_certificate_ids(self) -> tuple[str, ...]:
        return tuple(sorted({
            value for value in self.certificate_ids if value is not None
        }))


@dataclass(frozen=True, slots=True)
class RefinementMetrics:
    eligible: bool
    adopted: bool
    reason: str
    candidates: int = 0
    dtheta_deg: float = 0.0
    du_cells: float = 0.0
    dv_cells: float = 0.0
    baseline_validation_logloss: float | None = None
    candidate_validation_logloss: float | None = None
    baseline_pilot_mismatch: float | None = None
    candidate_pilot_mismatch: float | None = None
    generation0_e022_pilot_mismatch: float | None = None
    candidate_e022_pilot_mismatch: float | None = None
    n_payload_train: int = 0
    n_payload_validation: int = 0
    n_certified_blocks: int = 0
    n_pose_train: int = 0
    n_pose_validation: int = 0
    n_pose_pilot_train: int = 0
    n_pose_pilot_validation: int = 0

    def __post_init__(self) -> None:
        if not self.reason or self.adopted and not self.eligible:
            raise ValueError("invalid refinement outcome")


@dataclass(frozen=True, slots=True)
class SegmentRefinement:
    """Transient proposal; persistence belongs to the Track-3 barrier."""

    segment_id: int
    placed: PlacedSegment
    refined_segment: PoseSegment
    dependency_certificate_ids: tuple[str, ...]
    frontier_id: str
    metrics: RefinementMetrics

    def __post_init__(self) -> None:
        if self.segment_id != self.placed.segment.window.window_id:
            raise ValueError("refinement result names the wrong segment")
        if self.metrics.adopted != (
                self.refined_segment != self.placed.segment):
            raise ValueError("refinement proposal geometry/adoption mismatch")
        if tuple(sorted(set(self.dependency_certificate_ids))) \
                != self.dependency_certificate_ids:
            raise ValueError("refinement dependencies must be sorted unique")


def _request_rows(
    request: SegmentRefinementRequest, spec: FormatSpec
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    placed, generation0 = request.placed, request.generation0
    if placed.rot_k not in (0, 1, 2, 3):
        raise RefinementIntegrityError(
            "generation zero has an invalid frozen orientation")
    generation_rows = np.arange(
        generation0.page_cells_yx.shape[0], dtype=np.int64)
    local = np.asarray(generation0.segment_local_cells_yx, np.int64)
    if np.unique(local, axis=0).shape[0] != local.shape[0]:
        raise RefinementIntegrityError("generation zero repeats a segment cell")
    audited = np.asarray(placed.audited_cells_yx, np.int64)
    audited_mapped = rotate_points(
        audited, placed.segment.window.shape_yx_cells, placed.rot_k
    ) + np.asarray(placed.page_origin_yx, np.int64)
    page_shape = np.asarray(spec.layout.cells_yx, np.int64)
    audited_inside = np.all(
        (audited_mapped >= 0) & (audited_mapped < page_shape), axis=1
    )
    expected_local = audited[audited_inside]
    if ({tuple(int(v) for v in row) for row in local}
            != {tuple(int(v) for v in row) for row in expected_local}):
        raise RefinementIntegrityError(
            "generation zero changed the frozen audited support"
        )
    mapped = rotate_points(
        local, placed.segment.window.shape_yx_cells, placed.rot_k
    ) + np.asarray(placed.page_origin_yx, np.int64)
    inside = np.all((mapped >= 0) & (mapped < page_shape), axis=1)
    if not np.all(inside) or not np.array_equal(
            mapped, generation0.page_cells_yx[generation_rows]):
        raise RefinementIntegrityError(
            "generation zero changed the frozen page/origin/orientation map"
        )
    expected_points = placed.segment.pose.points(local)
    if not np.array_equal(
            expected_points, generation0.scan_points_yx[generation_rows]):
        raise RefinementIntegrityError(
            "generation zero changed the frozen pose/audited-cell map"
        )
    return generation_rows, local, mapped


def _block_validation(page: int, cells_yx: np.ndarray) -> np.ndarray:
    """Deterministic cargo-holdout stripe assignment (1/VALIDATION_MODULUS).

    Ruling 10.5 (refinement:07): the historical E024 x coefficient 9176 was
    ≡ 0 mod VALIDATION_MODULUS, degenerating the partition to y-only
    horizontal bands, so a y-correlated pose-error direction was
    over-represented in held-out evaluation.  No deliberate rationale exists
    anywhere in the E023c/E024 record; adjusted for health.  All three
    coefficients are now odd — coprime to the (power-of-two) modulus — so
    the holdout blocks form diagonal stripes: every axis-aligned run of
    VALIDATION_MODULUS blocks, horizontal or vertical, contains exactly one
    held-out block.  Same stripe fraction, same determinism.
    """
    block = np.asarray(cells_yx, np.int64) // BLOCK_CELLS
    token = page * 104729 + block[:, 0] * 1009 + block[:, 1] * 9177
    return (token % VALIDATION_MODULUS) == 0


def _block_weights(block_ids: np.ndarray) -> np.ndarray:
    ids = np.asarray(block_ids, np.int64)
    if ids.size == 0:
        return np.zeros(0, np.float64)
    _unique, inverse, counts = np.unique(
        ids, return_inverse=True, return_counts=True
    )
    return 1.0 / counts[inverse].astype(np.float64)


def collect_segment_labels(
    request: SegmentRefinementRequest,
    spec: FormatSpec,
    frontier: CertificateFrontier,
) -> SegmentLabels:
    """Join exact colocated pilots and certified printed cargo."""
    if frontier.spec_id != spec.spec_id:
        raise ValueError("certificate frontier belongs to another format")
    generation_rows, _local, page_cells = _request_rows(request, spec)
    page = int(request.generation0.page)
    reference = format_reference_values(spec, page, page_cells)
    retained_reference = request.generation0.reference_values[generation_rows]
    if not np.array_equal(reference, retained_reference):
        raise RefinementIntegrityError(
            "generation-zero format reference values do not replay"
        )
    pilot_local = np.flatnonzero(reference >= 0)
    pilot_rows = generation_rows[pilot_local]
    pilot_cells = page_cells[pilot_local]
    pilot_values = reference[pilot_local].astype(np.uint8)
    pilot_validation = (
        (pilot_cells[:, 0] * 131 + pilot_cells[:, 1] * 17) & 1
    ).astype(bool)

    certificates = frontier.by_address()
    cargo_candidates = np.flatnonzero(reference < 0)
    cargo_tile_yx = page_cells[cargo_candidates] // 64
    tile_codes = (
        cargo_tile_yx[:, 0] * spec.layout.tiles_yx[1] + cargo_tile_yx[:, 1]
    )
    selected_parts: list[np.ndarray] = []
    value_parts: list[np.ndarray] = []
    id_parts: list[np.ndarray] = []
    for tile_code in np.unique(tile_codes):
        ty, tx = divmod(int(tile_code), spec.layout.tiles_yx[1])
        certified = certificates.get((page, ty, tx))
        if certified is None:
            continue
        selected = cargo_candidates[tile_codes == tile_code]
        coords = page_cells[selected]
        values = certified.printed_cells[coords[:, 0] % 64, coords[:, 1] % 64]
        selected_parts.append(selected)
        value_parts.append(np.asarray(values, np.uint8))
        id_parts.append(np.full(selected.size, certified.certificate_id,
                                dtype=object))
    if selected_parts:
        selected_all = np.concatenate(selected_parts)
        order = np.argsort(selected_all, kind="stable")
        cargo_local_array = selected_all[order].astype(np.int64, copy=False)
        cargo_values = np.concatenate(value_parts)[order]
        cargo_ids = np.concatenate(id_parts)[order].tolist()
    else:
        cargo_local_array = np.zeros(0, np.int64)
        cargo_values = np.zeros(0, np.uint8)
        cargo_ids = []
    cargo_rows = generation_rows[cargo_local_array]
    cargo_cells = page_cells[cargo_local_array]
    cargo_validation = _block_validation(page, cargo_cells)

    rows = np.concatenate((pilot_rows, cargo_rows)).astype(np.int64)
    cells = np.concatenate((pilot_cells, cargo_cells), axis=0).astype(np.int64)
    values = np.concatenate((
        pilot_values, cargo_values
    ))
    validation = np.concatenate((pilot_validation, cargo_validation))
    is_pilot = np.concatenate((
        np.ones(pilot_rows.size, bool), np.zeros(cargo_rows.size, bool)
    ))
    by = cells[:, 0] // BLOCK_CELLS
    bx = cells[:, 1] // BLOCK_CELLS
    block_ids = (
        is_pilot.astype(np.int64) * 10**12
        + page * 10**9 + by * 10**4 + bx
    )
    weights = np.zeros(rows.size, np.float64)
    weights[~validation] = _block_weights(block_ids[~validation])
    weights[validation] = _block_weights(block_ids[validation])
    return SegmentLabels(
        rows, cells, values, validation, weights, is_pilot, block_ids,
        tuple([None] * pilot_rows.size + cargo_ids),
    )


def _support_metrics(labels: SegmentLabels) -> tuple[bool, str, dict[str, int]]:
    payload = ~labels.is_pilot
    payload_train = int(np.count_nonzero(payload & labels.train))
    payload_validation = int(np.count_nonzero(payload & labels.validation))
    blocks = int(np.unique(labels.block_ids[payload]).size)
    counts = {
        "n_payload_train": payload_train,
        "n_payload_validation": payload_validation,
        "n_certified_blocks": blocks,
    }
    if payload_train < MIN_PAYLOAD_TRAIN:
        return False, "insufficient_payload_train", counts
    if payload_validation < MIN_PAYLOAD_VALIDATION:
        return False, "insufficient_payload_validation", counts
    train_values = labels.values[labels.train]
    valid_values = labels.values[labels.validation]
    if min(int(np.count_nonzero(train_values == 0)),
           int(np.count_nonzero(train_values == 1))) < MIN_TRAIN_PER_CLASS:
        return False, "train_class_starved", counts
    if min(int(np.count_nonzero(valid_values == 0)),
           int(np.count_nonzero(valid_values == 1))) < MIN_VALIDATION_PER_CLASS:
        return False, "validation_class_starved", counts
    if blocks < MIN_CERTIFIED_BLOCKS:
        return False, "insufficient_certified_blocks", counts
    return True, "", counts


def _deterministic_cap(
    label_positions: np.ndarray, labels: SegmentLabels, cap: int
) -> np.ndarray:
    positions = np.asarray(label_positions, np.int64)
    if positions.size <= cap:
        return positions
    coords = labels.page_cells_yx[positions]
    token = (
        coords[:, 0].astype(np.uint64) * np.uint64(11400714819323198485)
        ^ coords[:, 1].astype(np.uint64) * np.uint64(14029467366897019727)
    )
    return positions[np.argsort(token, kind="stable")[:cap]]


def select_pose_sites(
    labels: SegmentLabels, validation: bool
) -> np.ndarray:
    """Historical deterministic cap: retain all pilots, hash cargo only."""
    side = labels.validation if validation else labels.train
    cap = POSE_SITE_CAP_VALIDATION if validation else POSE_SITE_CAP_TRAIN
    positions = np.flatnonzero(side)
    pilots = positions[labels.is_pilot[positions]]
    cargo = positions[~labels.is_pilot[positions]]
    cargo = _deterministic_cap(cargo, labels, max(cap - pilots.size, 0))
    selected = np.concatenate((pilots, cargo))
    return selected[np.argsort(
        labels.generation_rows[selected], kind="stable"
    )].astype(np.int64, copy=False)


def _sample(
    image: RefinementRegionImage,
    pose: AffinePose,
    local_cells: np.ndarray,
    *,
    require_in_bounds: bool = False,
) -> np.ndarray:
    points = pose.points(np.asarray(local_cells, np.float64))
    if require_in_bounds and points.size and (
        np.any(points[:, 0] < 0.0) or np.any(points[:, 1] < 0.0)
        or np.any(points[:, 0] > image.raster_shape[0] - 1)
        or np.any(points[:, 1] > image.raster_shape[1] - 1)
    ):
        raise RefinementIntegrityError("candidate maps audited cell off raster")
    local = points - np.asarray((image.y0, image.x0), np.float64)
    return np.asarray(ndimage.map_coordinates(
        image.filtered_luma, local.T, order=1, cval=image.fill_luma
    ), np.float32)


def _pose_candidate(
    base: AffinePose, dtheta_deg: float, du_cells: float, dv_cells: float
) -> AffinePose:
    angle = np.deg2rad(float(dtheta_deg))
    rotation = np.asarray((
        (np.cos(angle), np.sin(angle)),
        (-np.sin(angle), np.cos(angle)),
    ), np.float64)
    jacobian0 = base.matrix()
    jacobian = rotation @ jacobian0
    origin = (
        np.asarray(base.origin_yx, np.float64)
        + jacobian0 @ np.asarray((du_cells, dv_cells), np.float64)
    )
    pitch_y = float(np.hypot(*jacobian[:, 0]))
    pitch_x = float(np.hypot(*jacobian[:, 1]))
    angle_deg = float(np.degrees(np.arctan2(
        jacobian[0, 1], jacobian[1, 1]
    )))
    return AffinePose(
        (float(origin[0]), float(origin[1])),
        tuple(tuple(float(value) for value in row) for row in jacobian),
        base.phase_yx,
        0.5 * (pitch_y + pitch_x),
        angle_deg,
    )


def _pose_objective(
    means: np.ndarray, values: np.ndarray, weights: np.ndarray
) -> float:
    raw = np.asarray(means, np.float64)
    labels = np.asarray(values, np.uint8)
    weight = np.asarray(weights, np.float64)
    paper, ink = labels == 0, labels == 1
    if not paper.any() or not ink.any():
        return -np.inf
    mean_paper = float(np.sum(weight[paper] * raw[paper]) / np.sum(weight[paper]))
    mean_ink = float(np.sum(weight[ink] * raw[ink]) / np.sum(weight[ink]))
    center = float(np.sum(weight * raw) / np.sum(weight))
    spread = max(float(np.sum(weight * np.abs(raw - center))
                       / np.sum(weight)), SCORE_SPREAD_FLOOR)
    return (mean_paper - mean_ink) / spread


def _weighted_logloss(
    logits: np.ndarray, values: np.ndarray, weights: np.ndarray
) -> float:
    x = np.asarray(logits, np.float64)
    y = np.asarray(values, np.float64)
    w = np.asarray(weights, np.float64)
    losses = np.logaddexp(0.0, x) - y * x
    return float(np.sum(w * losses) / np.sum(w))


def _calibration(window: WindowEvidence) -> detect.Calibration:
    return detect.Calibration(
        window.placement_id,
        window.calibration_score_nodes,
        window.calibration_probability_nodes,
        window.n_search,
    )


def _fixed_marginal_logits(
    window: WindowEvidence, means: np.ndarray
) -> np.ndarray:
    raw = np.asarray(means, np.float32)
    if np.array_equal(raw, window.raw_means):
        scores = window.scores
    else:
        midpoint = float(np.median(window.raw_means))
        spread = max(float(np.abs(window.raw_means - midpoint).mean()),
                     SCORE_SPREAD_FLOOR)
        scores = ((np.float32(midpoint) - raw) / np.float32(spread)).astype(
            np.float32, copy=False
        )
    return _calibration(window).llr(scores)


def _fixed_detector_logits(
    request: SegmentRefinementRequest, means: np.ndarray
) -> np.ndarray:
    window = request.generation0
    logits = _fixed_marginal_logits(window, means)
    if window.detector_profile == CONTEXT_PROFILE:
        assert request.context_decision is not None
        counts, valid = detect.context_neighbour_counts(
            window.page_cells_yx, logits > 0.0
        )
        bins = np.where(valid, counts, -1)
        logits = detect.apply_context_offsets(
            logits, bins, request.context_decision.offsets)
    return np.asarray(logits, np.float64)


def _adoption_gate(
    baseline_loss: float,
    candidate_loss: float,
    baseline_pilot_mismatch: float,
    candidate_pilot_mismatch: float,
    generation0_raw_pilot_mismatch: float,
    candidate_raw_pilot_mismatch: float,
) -> bool:
    return bool(
        candidate_loss + MIN_HELDOUT_GAIN < baseline_loss
        and candidate_pilot_mismatch
        <= baseline_pilot_mismatch + PILOT_MISMATCH_SLACK
        and candidate_raw_pilot_mismatch
        <= generation0_raw_pilot_mismatch + PILOT_MISMATCH_SLACK
    )


def refine_segment(
    image: RefinementRegionImage,
    request: SegmentRefinementRequest,
    spec: FormatSpec,
    frontier: CertificateFrontier,
) -> SegmentRefinement:
    """Propose at most one bounded pose revision for one local segment."""
    segment = request.placed.segment
    if image.region_index != segment.window.region_index:
        raise ValueError("refinement image belongs to another E021 region")
    generation_rows, local, _page_cells = _request_rows(request, spec)
    baseline_sample = _sample(
        image, segment.pose, local, require_in_bounds=True
    )
    retained = request.generation0.raw_means[generation_rows]
    if not np.array_equal(baseline_sample, retained):
        raise RefinementIntegrityError(
            "generation-zero pose no longer reproduces retained raw luma"
        )
    labels = collect_segment_labels(request, spec, frontier)
    supported, reason, support = _support_metrics(labels)
    common_counts = dict(**support)
    if not supported:
        metrics = RefinementMetrics(False, False, reason, **common_counts)
        return SegmentRefinement(
            segment.window.window_id, request.placed, segment,
            labels.dependency_certificate_ids,
            frontier.frontier_id, metrics,
        )

    train_positions = select_pose_sites(labels, validation=False)
    valid_positions = select_pose_sites(labels, validation=True)
    train_rows = labels.generation_rows[train_positions]
    valid_rows = labels.generation_rows[valid_positions]
    train_local_lookup = {
        int(row): local[index] for index, row in enumerate(generation_rows)
    }
    train_local = np.asarray([train_local_lookup[int(row)] for row in train_rows])
    all_local = local
    train_values = labels.values[train_positions]
    train_weights = labels.weights[train_positions]
    valid_values = labels.values[valid_positions]
    valid_weights = labels.weights[valid_positions]
    train_pilots = train_positions[labels.is_pilot[train_positions]]
    valid_pilots = valid_positions[labels.is_pilot[valid_positions]]
    count_fields = dict(
        **support,
        n_pose_train=int(train_positions.size),
        n_pose_validation=int(valid_positions.size),
        n_pose_pilot_train=int(train_pilots.size),
        n_pose_pilot_validation=int(valid_pilots.size),
    )
    if (train_pilots.size < MIN_POSE_PILOTS
            or valid_pilots.size < MIN_POSE_PILOTS):
        metrics = RefinementMetrics(
            False, False, "insufficient_pose_pilot_validation", **count_fields
        )
        return SegmentRefinement(
            segment.window.window_id, request.placed, segment,
            labels.dependency_certificate_ids,
            frontier.frontier_id, metrics,
        )

    generation0 = request.generation0
    calibration = _calibration(generation0)
    base_logits = _fixed_detector_logits(request, generation0.raw_means)
    base_loss = _weighted_logloss(
        base_logits[valid_rows], valid_values, valid_weights
    )
    pilot_valid_rows = labels.generation_rows[valid_pilots]
    pilot_values = labels.values[valid_pilots]
    base_pilot_mismatch = float(np.mean(
        (base_logits[pilot_valid_rows] > 0.0) != (pilot_values > 0)
    ))
    midpoint = float(np.median(generation0.raw_means))
    spread = max(float(np.abs(generation0.raw_means - midpoint).mean()),
                 SCORE_SPREAD_FLOOR)
    generation0_raw_mismatch = float(np.mean(
        (generation0.raw_means[pilot_valid_rows] < midpoint)
        != (pilot_values > 0)
    ))

    candidates: dict[tuple[float, float, float], tuple[float, float]] = {}

    def score_candidate(dtheta: float, du: float, dv: float) -> None:
        key = tuple(round(float(value), 12) for value in (dtheta, du, dv))
        if key in candidates:
            return
        pose = _pose_candidate(segment.pose, *key)
        means = _sample(image, pose, train_local)
        contrast = _pose_objective(means, train_values, train_weights)
        # Historical candidate ranking kept these transient scores in native
        # floating precision.  Only the durable candidate replay below is
        # frozen to float32.
        scores = (midpoint - means) / spread
        logits = calibration.llr(scores)
        loss = _weighted_logloss(logits, train_values, train_weights)
        candidates[key] = contrast, loss

    def select_best(
        keys: Iterable[tuple[float, float, float]]
    ) -> tuple[float, float, float]:
        rows = tuple(keys)
        maximum_contrast = max(candidates[key][0] for key in rows)
        near = [
            key for key in rows
            if maximum_contrast - candidates[key][0] <= 1e-9
        ]
        return min(near, key=lambda key: (
            candidates[key][1],
            sum(value * value for value in key),
            tuple(abs(value) for value in key),
            key,
        ))

    coarse_angles = np.arange(
        -ANGLE_LIMIT_DEG, ANGLE_LIMIT_DEG + 1e-12, ANGLE_COARSE_STEP_DEG
    )
    coarse_phase = np.arange(
        -PHASE_LIMIT_CELLS, PHASE_LIMIT_CELLS + 1e-12,
        PHASE_COARSE_STEP_CELLS,
    )
    for dtheta in coarse_angles:
        for du in coarse_phase:
            for dv in coarse_phase:
                score_candidate(float(dtheta), float(du), float(dv))
    best_coarse = select_best(candidates)
    fine_angles = np.arange(
        best_coarse[0] - ANGLE_COARSE_STEP_DEG,
        best_coarse[0] + ANGLE_COARSE_STEP_DEG + 1e-12,
        ANGLE_FINE_STEP_DEG,
    )
    fine_du = np.arange(
        best_coarse[1] - PHASE_COARSE_STEP_CELLS,
        best_coarse[1] + PHASE_COARSE_STEP_CELLS + 1e-12,
        PHASE_FINE_STEP_CELLS,
    )
    fine_dv = np.arange(
        best_coarse[2] - PHASE_COARSE_STEP_CELLS,
        best_coarse[2] + PHASE_COARSE_STEP_CELLS + 1e-12,
        PHASE_FINE_STEP_CELLS,
    )
    for dtheta in fine_angles:
        if abs(dtheta) > ANGLE_LIMIT_DEG + 1e-12:
            continue
        for du in fine_du:
            if abs(du) > PHASE_LIMIT_CELLS + 1e-12:
                continue
            for dv in fine_dv:
                if abs(dv) <= PHASE_LIMIT_CELLS + 1e-12:
                    score_candidate(float(dtheta), float(du), float(dv))
    best = select_best(candidates)
    pose = _pose_candidate(segment.pose, *best)
    if pose == segment.pose:
        metrics = RefinementMetrics(
            True, False, "active_pose_selected", len(candidates),
            baseline_validation_logloss=base_loss, **count_fields,
        )
        return SegmentRefinement(
            segment.window.window_id, request.placed, segment,
            labels.dependency_certificate_ids,
            frontier.frontier_id, metrics,
        )

    candidate_target = _sample(image, pose, all_local)
    candidate_means = np.array(generation0.raw_means, np.float32, copy=True)
    candidate_means[generation_rows] = candidate_target
    candidate_logits = _fixed_detector_logits(request, candidate_means)
    candidate_loss = _weighted_logloss(
        candidate_logits[valid_rows], valid_values, valid_weights
    )
    candidate_pilot_mismatch = float(np.mean(
        (candidate_logits[pilot_valid_rows] > 0.0) != (pilot_values > 0)
    ))
    candidate_raw_mismatch = float(np.mean(
        (candidate_means[pilot_valid_rows] < midpoint) != (pilot_values > 0)
    ))
    adopted = _adoption_gate(
        base_loss, candidate_loss, base_pilot_mismatch,
        candidate_pilot_mismatch, generation0_raw_mismatch,
        candidate_raw_mismatch,
    )
    metrics = RefinementMetrics(
        True, adopted, "adopted" if adopted else "pose_gate_failed",
        len(candidates), float(best[0]), float(best[1]), float(best[2]),
        float(base_loss), float(candidate_loss),
        float(base_pilot_mismatch), float(candidate_pilot_mismatch),
        float(generation0_raw_mismatch), float(candidate_raw_mismatch),
        **count_fields,
    )
    refined = replace(segment, pose=pose) if adopted else segment
    return SegmentRefinement(
        segment.window.window_id, request.placed, refined,
        labels.dependency_certificate_ids,
        frontier.frontier_id,
        metrics,
    )


__all__ = [
    "CertificateFrontier",
    "CertifiedTileLabels",
    "RefinementIntegrityError",
    "RefinementMetrics",
    "RefinementRegionImage",
    "SegmentLabels",
    "SegmentRefinement",
    "SegmentRefinementRequest",
    "collect_segment_labels",
    "prepare_region_image",
    "refine_segment",
    "select_pose_sites",
]
