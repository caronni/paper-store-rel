"""Certified pose refinement for color payload lanes (§7 color arm).

This is the color counterpart of :mod:`certified_refine` (rework Phase 6.1,
ruling 10.6: "color needs it too").  One bounded forward pose proposal per
accepted E022 color window, labelled by prior-barrier certificates only:

* labels are exact printed per-plane presence bits reconstructed through the
  ONE color reconstruction primitive (`color_projection`, mint-once cached),
  flattened to (cell, plane) binary observations; word/dust furniture sites
  are the pilot analog and contribute all three planes;
* the fit mirrors K's two-stage structure exactly — a detector-free
  photometric contrast ranks the bounded candidate grid, and adoption is
  gated on held-out improvement through a calibration FROZEN from the
  baseline pose — with K's shared grid constants, diagonal-stripe cargo
  holdout, and block weight equalization imported, never copied;
* discrete identity is frozen: page, integer page origin, orientation, and
  the audited/authoritative cell set never change; only the continuous
  window pose moves, and `ColorWindowRefinement` enforces that structurally.

The color detector (region QDA/PAVA) is transient by design, so no
generation-zero detector can be replayed here.  The frozen per-plane affine
calibration ``score = (midpoint - value) / spread`` minted from the baseline
samples is the deterministic, pose-independent stand-in: both gate arms ride
the same transform, so the comparison measures pose, not calibration.  It
also makes the RGB scale (u8/u16, region divisor) cancel by construction,
which is why refinement samples the undivided filtered crop.

Scope is forward-only (no E024 loop).  Adoption granularity is the REGION:
the color detector, registration, pitch pool, and divisor probe are
region-scoped, so an adopted pose invalidates its whole (region, page) fit.

Since RECEIVE-DESIGN v0.42 (stage C) this leaf serves the refinement level
R(Lk), not an inline payload pass: the SHARED `place.place_committed`
reconstruction (K parity — audited cell sets re-derived on the base
aperture, never a window-rectangle inventory) rebuilds the base lane's
durable PoseRecords, `refine_color_address_once` with ``generation0=None``
drives the committed-pose domain behind two crop-free pre-gates (the
certified-cargo gate and the v0.42 no-uncertified-remainder gate), and
`affected_color_patch_ids` names the region-coupled delta domain that the
ordinary `collect_color_evidence` ``included_patch_ids`` seam recomputes.
The former generation-zero merge (`collect_refined_color_evidence`) is
gone with the inline pass: unaffected regions contribute NOTHING at the R
barrier — their base-lane evidence stands in its own namespace.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping

import numpy as np
from scipy import ndimage

from ..core import channel
from ..format.descriptor import FormatSpec
from . import _parallel, tiles
from ._payload_sampling import (
    SCORE_SPREAD_FLOOR,
    _WindowRows,
    _window_rows,
)
from .certified_cascade import _replace_hints
from .certified_refine import (
    ANGLE_COARSE_STEP_DEG,
    ANGLE_FINE_STEP_DEG,
    ANGLE_LIMIT_DEG,
    BLOCK_CELLS,
    MIN_CERTIFIED_BLOCKS,
    MIN_HELDOUT_GAIN,
    MIN_PAYLOAD_TRAIN,
    MIN_PAYLOAD_VALIDATION,
    MIN_POSE_PILOTS,
    MIN_TRAIN_PER_CLASS,
    MIN_VALIDATION_PER_CLASS,
    PHASE_COARSE_STEP_CELLS,
    PHASE_FINE_STEP_CELLS,
    PHASE_LIMIT_CELLS,
    POSE_SITE_CAP_TRAIN,
    POSE_SITE_CAP_VALIDATION,
    RefinementIntegrityError,
    _block_validation,
    _block_weights,
    _pose_candidate,
    _pose_objective,
    _weighted_logloss,
)
from .color_anchoring import (
    _readonly,
    color_reference_states,
)
from .color_sampling import (
    LocalCrop as _LocalCrop,
    RawRGBRaster,
    window_crop as _window_crop,
)
from .color_payload import ColorCaptureEvidence, ColorWindowEvidence
from .color_pool import (
    _emission_mask,
    _payload_cell_mask,
    fully_certified_color_addresses,
)
from .color_projection import cached_certified_color_projection
from .evidence import TileCertificateRecord
from .placement.model import AddressResult, PlacedPatch


# The furniture (word/dust) gate is the color pilot non-regression: held-out
# furniture logloss through the frozen calibration must not worsen.  The
# slack absorbs float re-association only; it is not a tolerance policy.
FURNITURE_LOSS_SLACK = 1e-9
# Odd 64-bit mixing constant for the plane axis of the deterministic cargo
# site cap (the K cap hashes (y, x); color observations add the plane).
_PLANE_TOKEN_MIX = np.uint64(0x9E3779B97F4A7C15)


@dataclass(frozen=True, slots=True)
class ColorRefinementLabels:
    """Flattened certified (cell, plane) presence-bit labels for one window.

    ``row_indices`` index the window's aligned rows (`_window_rows` order);
    ``planes`` select C/M/Y.  Furniture rows carry all three planes; cargo
    rows carry exactly the planes the certificate authority reconstructs
    (CMY7: all three from "main"; CMY8: one per certified stream).
    """

    row_indices: np.ndarray
    planes: np.ndarray
    page_cells_yx: np.ndarray
    bits: np.ndarray
    validation: np.ndarray
    weights: np.ndarray
    is_furniture: np.ndarray
    block_ids: np.ndarray
    dependency_certificate_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        n = np.asarray(self.row_indices).size
        fields = (
            ("row_indices", self.row_indices, np.int64, (n,)),
            ("planes", self.planes, np.int64, (n,)),
            ("page_cells_yx", self.page_cells_yx, np.int64, (n, 2)),
            ("bits", self.bits, np.uint8, (n,)),
            ("validation", self.validation, bool, (n,)),
            ("weights", self.weights, np.float64, (n,)),
            ("is_furniture", self.is_furniture, bool, (n,)),
            ("block_ids", self.block_ids, np.int64, (n,)),
        )
        for name, value, dtype, shape in fields:
            array = np.asarray(value)
            if array.shape != shape:
                raise ValueError(f"{name} must have shape {shape}")
            object.__setattr__(self, name, _readonly(array, dtype))
        if (not np.all(np.isin(self.planes, (0, 1, 2)))
                or not np.all(np.isin(self.bits, (0, 1)))
                or not np.all(np.isfinite(self.weights))
                or np.any(self.weights <= 0.0)):
            raise ValueError("malformed color refinement labels")
        dependencies = tuple(self.dependency_certificate_ids)
        if tuple(sorted(set(dependencies))) != dependencies:
            raise ValueError(
                "color refinement dependencies must be sorted unique")

    @property
    def train(self) -> np.ndarray:
        return ~self.validation


@dataclass(frozen=True, slots=True)
class ColorRefinementMetrics:
    eligible: bool
    adopted: bool
    reason: str
    candidates: int = 0
    dtheta_deg: float = 0.0
    du_cells: float = 0.0
    dv_cells: float = 0.0
    baseline_validation_logloss: float | None = None
    candidate_validation_logloss: float | None = None
    baseline_furniture_logloss: float | None = None
    candidate_furniture_logloss: float | None = None
    n_payload_train: int = 0
    n_payload_validation: int = 0
    n_certified_blocks: int = 0
    n_pose_train: int = 0
    n_pose_validation: int = 0
    n_furniture_train: int = 0
    n_furniture_validation: int = 0

    def __post_init__(self) -> None:
        if not self.reason or self.adopted and not self.eligible:
            raise ValueError("invalid color refinement outcome")


@dataclass(frozen=True, slots=True)
class ColorWindowRefinement:
    """Transient proposal; persistence belongs to the ordinary barrier.

    The constructor enforces the frozen discrete identity: an adopted
    revision replaces ONLY the continuous pose — page, orientation, integer
    page origin, audited cells, and the authoritative page-cell set are
    byte-identical between baseline and refined placement.
    """

    patch_id: int
    baseline: PlacedPatch
    refined: PlacedPatch
    dependency_certificate_ids: tuple[str, ...]
    frontier_id: str
    metrics: ColorRefinementMetrics

    def __post_init__(self) -> None:
        if self.patch_id != int(self.baseline.patch_id):
            raise ValueError("color refinement names the wrong placement")
        base, fitted = self.baseline, self.refined
        if self.metrics.adopted != (
                fitted.segment.segment.pose != base.segment.segment.pose):
            raise ValueError(
                "color refinement geometry/adoption mismatch")
        if (
            fitted.candidate != base.candidate
            or fitted.segment.rot_k != base.segment.rot_k
            or fitted.segment.page_origin_yx != base.segment.page_origin_yx
            or fitted.region_index != base.region_index
            or not np.array_equal(
                fitted.segment.audited_cells_yx,
                base.segment.audited_cells_yx)
            or not np.array_equal(fitted.page_cells_yx, base.page_cells_yx)
        ):
            raise ValueError(
                "color refinement changed frozen discrete identity")
        if tuple(sorted(set(self.dependency_certificate_ids))) \
                != self.dependency_certificate_ids:
            raise ValueError(
                "color refinement dependencies must be sorted unique")


@dataclass(frozen=True, slots=True)
class ColorForwardRefinement:
    """Final address geometry plus exact adopted certificate dependencies."""

    address: AddressResult
    summaries: tuple[ColorWindowRefinement, ...]
    patch_dependencies: tuple[tuple[int, tuple[str, ...]], ...]

    @property
    def eligible(self) -> int:
        return sum(1 for row in self.summaries if row.metrics.eligible)

    @property
    def adopted(self) -> int:
        return sum(1 for row in self.summaries if row.metrics.adopted)


def collect_color_refinement_labels(
    spec: FormatSpec,
    page: int,
    rows: _WindowRows,
    certificate_index: Mapping[
        tuple[int, int, int], tuple[TileCertificateRecord, ...]
    ],
) -> ColorRefinementLabels:
    """Join format furniture and certified cargo presence-bit labels."""
    cells = np.asarray(rows.page_cells_yx, np.int64)
    states, kinds = color_reference_states(spec, page, cells)

    furniture_rows = np.flatnonzero(kinds >= 0).astype(np.int64)
    furniture_bits = channel.states_to_planes(
        states[furniture_rows]).astype(np.uint8)

    cargo_candidates = np.flatnonzero(kinds < 0).astype(np.int64)
    tiles_x = spec.layout.tiles_yx[1]
    cargo_codes = (
        (cells[cargo_candidates, 0] // 64) * tiles_x
        + cells[cargo_candidates, 1] // 64
    )
    cargo_row_parts: list[np.ndarray] = []
    cargo_plane_parts: list[np.ndarray] = []
    cargo_bit_parts: list[np.ndarray] = []
    dependencies: set[str] = set()
    for code in np.unique(cargo_codes):
        ty, tx = divmod(int(code), tiles_x)
        records = certificate_index.get((page, ty, tx), ())
        if not records:
            continue
        projection = cached_certified_color_projection(
            records, spec, (page, ty, tx))
        selected = cargo_candidates[cargo_codes == code]
        local_y = cells[selected, 0] % 64
        local_x = cells[selected, 1] % 64
        known = projection.known_mask[local_y, local_x]
        bits = projection.component_bits[local_y, local_x]
        site, plane = np.nonzero(known)
        if not site.size:
            continue
        cargo_row_parts.append(selected[site])
        cargo_plane_parts.append(plane.astype(np.int64))
        cargo_bit_parts.append(bits[site, plane].astype(np.uint8))
        dependencies.update(projection.dependency_certificate_ids)
    if cargo_row_parts:
        cargo_rows = np.concatenate(cargo_row_parts)
        cargo_planes = np.concatenate(cargo_plane_parts)
        cargo_bits = np.concatenate(cargo_bit_parts)
        # Canonical order: ascending aligned row, then plane (per-tile parts
        # arrive in unique-code order; restore the one global order).
        order = np.argsort(cargo_rows * 4 + cargo_planes, kind="stable")
        cargo_rows = cargo_rows[order]
        cargo_planes = cargo_planes[order]
        cargo_bits = cargo_bits[order]
    else:
        cargo_rows = np.zeros(0, np.int64)
        cargo_planes = np.zeros(0, np.int64)
        cargo_bits = np.zeros(0, np.uint8)

    row_indices = np.concatenate((
        np.repeat(furniture_rows, 3), cargo_rows))
    planes = np.concatenate((
        np.tile(np.arange(3, dtype=np.int64), furniture_rows.size),
        cargo_planes,
    ))
    bits = np.concatenate((furniture_bits.reshape(-1), cargo_bits))
    is_furniture = np.concatenate((
        np.ones(furniture_rows.size * 3, bool),
        np.zeros(cargo_rows.size, bool),
    ))
    label_cells = cells[row_indices]
    # ONE shared holdout for furniture and cargo alike: the §7 diagonal
    # stripe partition (ruling 10.5 shared machinery).  Block weights keep
    # K's furniture/cargo block-id separation.
    validation = _block_validation(page, label_cells)
    by = label_cells[:, 0] // BLOCK_CELLS
    bx = label_cells[:, 1] // BLOCK_CELLS
    block_ids = (
        is_furniture.astype(np.int64) * 10**12
        + page * 10**9 + by * 10**4 + bx
    )
    weights = np.zeros(row_indices.size, np.float64)
    weights[~validation] = _block_weights(block_ids[~validation])
    weights[validation] = _block_weights(block_ids[validation])
    return ColorRefinementLabels(
        row_indices, planes, label_cells, bits, validation, weights,
        is_furniture, block_ids, tuple(sorted(dependencies)),
    )


def _support_metrics(
    labels: ColorRefinementLabels,
) -> tuple[bool, str, dict[str, int]]:
    """K's refinement support ladder over flattened observations."""
    cargo = ~labels.is_furniture
    cargo_train = int(np.count_nonzero(cargo & labels.train))
    cargo_validation = int(np.count_nonzero(cargo & labels.validation))
    blocks = int(np.unique(labels.block_ids[cargo]).size)
    counts = {
        "n_payload_train": cargo_train,
        "n_payload_validation": cargo_validation,
        "n_certified_blocks": blocks,
    }
    if cargo_train < MIN_PAYLOAD_TRAIN:
        return False, "insufficient_payload_train", counts
    if cargo_validation < MIN_PAYLOAD_VALIDATION:
        return False, "insufficient_payload_validation", counts
    train_bits = labels.bits[labels.train]
    valid_bits = labels.bits[labels.validation]
    if min(int(np.count_nonzero(train_bits == 0)),
           int(np.count_nonzero(train_bits == 1))) < MIN_TRAIN_PER_CLASS:
        return False, "train_class_starved", counts
    if min(int(np.count_nonzero(valid_bits == 0)),
           int(np.count_nonzero(valid_bits == 1))) < MIN_VALIDATION_PER_CLASS:
        return False, "validation_class_starved", counts
    if blocks < MIN_CERTIFIED_BLOCKS:
        return False, "insufficient_certified_blocks", counts
    return True, "", counts


def select_color_pose_sites(
    labels: ColorRefinementLabels, validation: bool
) -> np.ndarray:
    """K's deterministic cap: retain all furniture, hash cargo only."""
    side = labels.validation if validation else labels.train
    cap = POSE_SITE_CAP_VALIDATION if validation else POSE_SITE_CAP_TRAIN
    positions = np.flatnonzero(side)
    furniture = positions[labels.is_furniture[positions]]
    cargo = positions[~labels.is_furniture[positions]]
    budget = max(cap - furniture.size, 0)
    if cargo.size > budget:
        coords = labels.page_cells_yx[cargo]
        token = (
            coords[:, 0].astype(np.uint64) * np.uint64(11400714819323198485)
            ^ coords[:, 1].astype(np.uint64) * np.uint64(14029467366897019727)
            ^ labels.planes[cargo].astype(np.uint64) * _PLANE_TOKEN_MIX
        )
        cargo = cargo[np.argsort(token, kind="stable")[:budget]]
    selected = np.concatenate((furniture, cargo))
    return np.sort(selected).astype(np.int64, copy=False)


def _sample_planes(
    crop: _LocalCrop, points_yx: np.ndarray
) -> np.ndarray:
    """Sample the filtered crop without a bounds refusal.

    Baseline integrity is checked once by the caller.  A bounded candidate
    that leaves a raster-clipped crop clamps to the edge (nearest), which
    can only worsen its score — refusal-safe, mirroring K's fill-value
    candidate sampling.
    """
    local = np.asarray(points_yx, np.float64) - np.asarray(
        (crop.y0, crop.x0), np.float64)
    return np.stack(tuple(
        ndimage.map_coordinates(
            crop.filtered[..., plane], local.T, order=1, mode="nearest",
            output=np.float64)
        for plane in range(3)
    ), axis=1)


def refine_color_window(
    crop: _LocalCrop,
    patch: PlacedPatch,
    window: ColorWindowEvidence | None,
    spec: FormatSpec,
    certificate_index: Mapping[
        tuple[int, int, int], tuple[TileCertificateRecord, ...]
    ],
    frontier_id: str,
) -> ColorWindowRefinement:
    """Propose at most one bounded pose revision for one color window.

    ``window`` is the base pass's generation-zero emission when one exists
    (the historical inline drive and its pins); ``None`` in the v0.42
    R-level drive, where the aligned cells are freshly re-derived from the
    committed pose itself so there is no generation-zero emission to
    replay-check against.
    """
    if window is not None and int(window.patch_id) != int(patch.patch_id):
        raise ValueError("color refinement window names another placement")
    page = int(patch.candidate.page)
    rows = _window_rows(patch, spec)
    if window is not None:
        # Structural generation-zero replay: color gen-0 retains detector
        # outputs, not raw samples, so the photometric replay K performs is
        # impossible here.  The emitted cells must still be a subset of the
        # frozen aligned cells the placement replays.
        width = np.int64(spec.layout.cells_yx[1])
        aligned_keys = (
            rows.page_cells_yx[:, 0] * width + rows.page_cells_yx[:, 1])
        emitted = np.asarray(window.page_cells_yx, np.int64)
        emitted_keys = emitted[:, 0] * width + emitted[:, 1]
        if not np.all(np.isin(emitted_keys, aligned_keys)):
            raise RefinementIntegrityError(
                "color generation zero does not replay its frozen placement")

    labels = collect_color_refinement_labels(
        spec, page, rows, certificate_index)
    supported, reason, support = _support_metrics(labels)
    if not supported:
        metrics = ColorRefinementMetrics(False, False, reason, **support)
        return ColorWindowRefinement(
            int(patch.patch_id), patch, patch,
            labels.dependency_certificate_ids, frontier_id, metrics)

    pose0 = patch.segment.segment.pose
    local_cells = np.asarray(rows.local_cells_yx, np.float64)
    baseline_points = pose0.points(local_cells)
    inside = (
        (baseline_points[:, 0] >= crop.y0)
        & (baseline_points[:, 1] >= crop.x0)
        & (baseline_points[:, 0] <= crop.y0 + crop.filtered.shape[0] - 1)
        & (baseline_points[:, 1] <= crop.x0 + crop.filtered.shape[1] - 1)
    )
    if not bool(np.all(inside)):
        raise RefinementIntegrityError(
            "color baseline pose leaves its own window crop")
    baseline_all = _sample_planes(crop, baseline_points)

    # Frozen per-plane calibration from the BASELINE pose over all aligned
    # cells: the deterministic, pose-independent detector stand-in.  Ink is
    # the darker complementary channel, so scores are ink-positive like K.
    midpoint = np.median(baseline_all, axis=0)
    spread = np.maximum(
        np.mean(np.abs(baseline_all - midpoint), axis=0),
        SCORE_SPREAD_FLOOR,
    )

    train_pos = select_color_pose_sites(labels, validation=False)
    valid_pos = select_color_pose_sites(labels, validation=True)
    train_furniture = train_pos[labels.is_furniture[train_pos]]
    valid_furniture = valid_pos[labels.is_furniture[valid_pos]]
    count_fields = dict(
        **support,
        n_pose_train=int(train_pos.size),
        n_pose_validation=int(valid_pos.size),
        n_furniture_train=int(train_furniture.size),
        n_furniture_validation=int(valid_furniture.size),
    )
    if (train_furniture.size < MIN_POSE_PILOTS
            or valid_furniture.size < MIN_POSE_PILOTS):
        metrics = ColorRefinementMetrics(
            False, False, "insufficient_pose_pilot_validation",
            **count_fields)
        return ColorWindowRefinement(
            int(patch.patch_id), patch, patch,
            labels.dependency_certificate_ids, frontier_id, metrics)

    def flat_scores(
        samples_by_row: np.ndarray,
        row_lookup: np.ndarray,
        positions: np.ndarray,
    ) -> np.ndarray:
        planes = labels.planes[positions]
        values = samples_by_row[row_lookup, planes]
        return (midpoint[planes] - values) / spread[planes]

    train_rows_idx = labels.row_indices[train_pos]
    train_unique, train_inverse = np.unique(
        train_rows_idx, return_inverse=True)
    train_local = local_cells[train_unique]
    train_bits = labels.bits[train_pos]
    train_weights = labels.weights[train_pos]
    valid_rows_idx = labels.row_indices[valid_pos]
    valid_bits = labels.bits[valid_pos]
    valid_weights = labels.weights[valid_pos]
    furniture_in_valid = labels.is_furniture[valid_pos]
    furniture_bits = valid_bits[furniture_in_valid]
    furniture_weights = labels.weights[valid_pos][furniture_in_valid]

    base_valid_scores = flat_scores(
        baseline_all, valid_rows_idx, valid_pos)
    base_loss = _weighted_logloss(base_valid_scores, valid_bits, valid_weights)
    base_furniture_loss = _weighted_logloss(
        base_valid_scores[furniture_in_valid],
        furniture_bits, furniture_weights)

    candidates: dict[tuple[float, float, float], tuple[float, float]] = {}

    def score_candidate(dtheta: float, du: float, dv: float) -> None:
        key = tuple(round(float(value), 12) for value in (dtheta, du, dv))
        if key in candidates:
            return
        pose = _pose_candidate(pose0, *key)
        samples = _sample_planes(crop, pose.points(train_local))
        scores = flat_scores(samples, train_inverse, train_pos)
        # K's contrast objective verbatim on negated ink-positive scores:
        # paper scores are low, ink scores high, exactly K's raw-luma sign.
        contrast = _pose_objective(-scores, train_bits, train_weights)
        loss = _weighted_logloss(scores, train_bits, train_weights)
        candidates[key] = contrast, loss

    def select_best(
        keys: Iterable[tuple[float, float, float]]
    ) -> tuple[float, float, float]:
        rows_ = tuple(keys)
        maximum_contrast = max(candidates[key][0] for key in rows_)
        near = [
            key for key in rows_
            if maximum_contrast - candidates[key][0] <= 1e-9
        ]
        return min(near, key=lambda key: (
            candidates[key][1],
            sum(value * value for value in key),
            tuple(abs(value) for value in key),
            key,
        ))

    coarse_angles = np.arange(
        -ANGLE_LIMIT_DEG, ANGLE_LIMIT_DEG + 1e-12, ANGLE_COARSE_STEP_DEG)
    coarse_phase = np.arange(
        -PHASE_LIMIT_CELLS, PHASE_LIMIT_CELLS + 1e-12,
        PHASE_COARSE_STEP_CELLS)
    for dtheta in coarse_angles:
        for du in coarse_phase:
            for dv in coarse_phase:
                score_candidate(float(dtheta), float(du), float(dv))
    best_coarse = select_best(candidates)
    fine_angles = np.arange(
        best_coarse[0] - ANGLE_COARSE_STEP_DEG,
        best_coarse[0] + ANGLE_COARSE_STEP_DEG + 1e-12,
        ANGLE_FINE_STEP_DEG)
    fine_du = np.arange(
        best_coarse[1] - PHASE_COARSE_STEP_CELLS,
        best_coarse[1] + PHASE_COARSE_STEP_CELLS + 1e-12,
        PHASE_FINE_STEP_CELLS)
    fine_dv = np.arange(
        best_coarse[2] - PHASE_COARSE_STEP_CELLS,
        best_coarse[2] + PHASE_COARSE_STEP_CELLS + 1e-12,
        PHASE_FINE_STEP_CELLS)
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
    pose = _pose_candidate(pose0, *best)
    if pose == pose0:
        metrics = ColorRefinementMetrics(
            True, False, "active_pose_selected", len(candidates),
            baseline_validation_logloss=base_loss,
            baseline_furniture_logloss=base_furniture_loss,
            **count_fields)
        return ColorWindowRefinement(
            int(patch.patch_id), patch, patch,
            labels.dependency_certificate_ids, frontier_id, metrics)

    valid_unique, valid_inverse = np.unique(
        valid_rows_idx, return_inverse=True)
    candidate_samples = _sample_planes(
        crop, pose.points(local_cells[valid_unique]))
    candidate_scores = flat_scores(
        candidate_samples, valid_inverse, valid_pos)
    candidate_loss = _weighted_logloss(
        candidate_scores, valid_bits, valid_weights)
    candidate_furniture_loss = _weighted_logloss(
        candidate_scores[furniture_in_valid],
        furniture_bits, furniture_weights)
    adopted = bool(
        candidate_loss + MIN_HELDOUT_GAIN < base_loss
        and candidate_furniture_loss
        <= base_furniture_loss + FURNITURE_LOSS_SLACK
    )
    metrics = ColorRefinementMetrics(
        True, adopted, "adopted" if adopted else "pose_gate_failed",
        len(candidates), float(best[0]), float(best[1]), float(best[2]),
        float(base_loss), float(candidate_loss),
        float(base_furniture_loss), float(candidate_furniture_loss),
        **count_fields)
    if adopted:
        refined_segment = replace(
            patch.segment,
            segment=replace(patch.segment.segment, pose=pose),
        )
        refined = replace(patch, segment=refined_segment)
    else:
        refined = patch
    return ColorWindowRefinement(
        int(patch.patch_id), patch, refined,
        labels.dependency_certificate_ids, frontier_id, metrics)


def affected_color_patch_ids(
    refined_address: AddressResult,
    changed_patch_ids: Iterable[int],
) -> frozenset[int]:
    """Region-coupled closure of the adopted placements (the R delta).

    The color detector, registration, pitch pool, and divisor probe are
    region-scoped, so an adopted pose invalidates its whole (region, page)
    fit.  The v0.42 R-level payload delta therefore recomputes every
    placement sharing an adopted window's (region, page) key — through the
    ordinary ``collect_color_evidence`` ``included_patch_ids`` seam — and
    nothing else: unaffected regions contribute no windows, no owners, and
    no blocks at the R barrier (their base-lane evidence stands in its own
    namespace).
    """
    changed = frozenset(int(value) for value in changed_patch_ids)
    if not changed:
        raise ValueError(
            "color refinement delta requires an adopted placement")
    key_by_patch = {
        int(patch.patch_id):
        (int(patch.region_index), int(patch.candidate.page))
        for patch in refined_address.payload_placements
    }
    if not changed.issubset(key_by_patch):
        raise ValueError(
            "color refinement delta names a placement outside the "
            "promoted domain")
    affected_keys = frozenset(
        key_by_patch[patch_id] for patch_id in changed)
    return frozenset(
        patch_id for patch_id, key in key_by_patch.items()
        if key in affected_keys
    )


def refine_color_address_once(
    raster: RawRGBRaster,
    address: AddressResult,
    generation0: ColorCaptureEvidence | None,
    spec: FormatSpec,
    prior_certificates: Iterable[TileCertificateRecord],
) -> ColorForwardRefinement:
    """Apply one prior-frontier pose proposal to each eligible color window.

    With ``generation0`` (the historical inline drive, kept for the leaf
    pins) the refine domain is generation zero's emitting windows:
    label-only and certified-complete windows carry no payload evidence to
    refine.  With ``generation0=None`` (the v0.42 R-level drive) the
    domain is every reconstructed committed placement, and the structural
    gen-0 replay check is vacuous — the aligned cells were just re-derived
    from the committed pose itself.

    Each sampled window uses its own probe/base crop footprint at the
    replayed L5 region pitch (placements UNION label placements); the crop
    is undivided — the frozen per-plane calibration makes the region
    divisor cancel exactly, so it is not replayed.

    Two crop-free pre-gates run BEFORE any pixel read, so a lane with no
    eligible window never materializes its raster: the v0.42
    no-uncertified-remainder gate (a window whose covered payload tiles
    are all fully certified refuses with reason ``certified_complete`` —
    the NeedMap analog: nothing left to gain) and the v0.41 certified-
    cargo gate (zero certified-cargo overlap can never pass the
    ``_support_metrics`` ladder; byte-identical refusal, pinned).
    """
    if not isinstance(address, AddressResult):
        raise TypeError("color forward refinement needs AddressResult")
    if generation0 is not None:
        if not isinstance(generation0, ColorCaptureEvidence):
            raise TypeError(
                "color forward refinement needs ColorCaptureEvidence")
        if generation0.spec_id != spec.spec_id:
            raise ValueError(
                "color generation zero belongs to another format")
    prior_rows = tuple(prior_certificates)
    if (not prior_rows
            or (generation0 is not None and not generation0.windows)
            or not address.payload_placements):
        return ColorForwardRefinement(address, (), ())
    windows_by_patch = (
        None if generation0 is None
        else {int(row.patch_id): row for row in generation0.windows})
    certificate_index: dict[
        tuple[int, int, int], list[TileCertificateRecord]
    ] = {}
    for record in prior_rows:
        certificate_index.setdefault(
            (record.page, *record.tile_yx), []).append(record)
    frozen_index = {
        key: tuple(rows) for key, rows in certificate_index.items()}
    frontier_id = tiles.dependency_identity(tuple(sorted(
        {record.certificate_id for record in prior_rows})))
    # v0.42 no-uncertified-remainder gate inputs: the tiles whose EVERY
    # stream certified, keyed per page as suppressed flat codes (the exact
    # ``collect_color_evidence`` emission-mask convention).
    fully_certified_addresses = fully_certified_color_addresses(
        prior_rows, spec)
    suppressed_codes_by_page = {
        selected_page: np.asarray(
            sorted(
                ty * spec.layout.tiles_yx[1] + tx
                for page, ty, tx in fully_certified_addresses
                if page == selected_page
            ),
            dtype=np.int64,
        )
        for selected_page in sorted({
            value[0] for value in fully_certified_addresses})
    }

    grouped: dict[tuple[int, int], list[PlacedPatch]] = {}
    for patch in address.payload_placements:
        grouped.setdefault(
            (int(patch.region_index), int(patch.candidate.page)), []
        ).append(patch)
    labels_grouped: dict[tuple[int, int], list[PlacedPatch]] = {}
    for patch in address.label_placements:
        labels_grouped.setdefault(
            (int(patch.region_index), int(patch.candidate.page)), []
        ).append(patch)

    def _refine_one(
        work: tuple[PlacedPatch, int, float],
    ) -> ColorWindowRefinement:
        """One window's gates + crop + grid fit: pure in (patch, page,
        region pitch) against the frozen certificate index, so the pooled
        ordered map below is value-identical to the sequential loop."""
        patch, page, pitch_px = work
        tiles_x = int(spec.layout.tiles_yx[1])
        window_row = (
            None if windows_by_patch is None
            else windows_by_patch[int(patch.patch_id)])
        # Full aligned footprint (geometry only, no crop): the emitted
        # cells exclude certified tiles by construction, so cargo
        # overlap must be judged on the window's whole cell coverage.
        footprint = np.asarray(
            _window_rows(patch, spec).page_cells_yx, np.int64)
        # v0.42 no-uncertified-remainder gate (crop-free): a window
        # whose covered payload tiles are all fully certified has
        # nothing left to gain from a better pose — refuse before any
        # pixel read.  Vacuous in the gen-0 drive (emitting windows
        # always carry an open payload cell by construction).
        if not bool(np.any(
            _payload_cell_mask(spec, footprint)
            & _emission_mask(
                spec, page, footprint, suppressed_codes_by_page)
        )):
            metrics = ColorRefinementMetrics(
                False, False, "certified_complete")
            return ColorWindowRefinement(
                int(patch.patch_id), patch, patch, (), frontier_id,
                metrics)
        covered_codes = np.unique(
            (footprint[:, 0] // 64) * tiles_x
            + footprint[:, 1] // 64)
        if not any(
                (page, int(code) // tiles_x, int(code) % tiles_x)
                in frozen_index
                for code in covered_codes):
            # Crop-free refusal (v0.41 checkpoint fix): a window with
            # zero certified-cargo overlap can never pass the
            # _support_metrics ladder (cargo_train >= MIN_PAYLOAD_TRAIN
            # with zero cargo labels), so the expensive native RGB
            # crop+filter is skipped and the summary below is
            # byte-identical to the sampled refusal: counts all zero,
            # no cargo dependencies, first ladder reason.
            metrics = ColorRefinementMetrics(
                False, False, "insufficient_payload_train",
                n_payload_train=0, n_payload_validation=0,
                n_certified_blocks=0)
            return ColorWindowRefinement(
                int(patch.patch_id), patch, patch, (), frontier_id,
                metrics)
        crop = _window_crop(raster, patch, pitch_px, 1.0)
        return refine_color_window(
            crop, patch, window_row, spec, frozen_index, frontier_id)

    work_items: list[tuple[PlacedPatch, int, float]] = []
    for (region_index, page), patch_rows in sorted(grouped.items()):
        patches = tuple(sorted(
            patch_rows, key=lambda row: int(row.patch_id)))
        emitting = tuple(
            patch for patch in patches
            if windows_by_patch is None
            or int(patch.patch_id) in windows_by_patch)
        if not emitting:
            continue
        label_patches = tuple(sorted(
            labels_grouped.get((region_index, page), ()),
            key=lambda row: int(row.patch_id)))
        # Pool law L5 replay: the region pitch pools placements UNION
        # label placements, exactly as generation zero derived it.
        pitch_px = float(np.median(tuple(
            row.segment.segment.pose.pitch_px
            for row in patches + label_patches)))
        work_items.extend(
            (patch, page, pitch_px) for patch in emitting)

    summaries: list[ColorWindowRefinement] = []
    replacements: dict[int, object] = {}
    revised_by_id: dict[int, PlacedPatch] = {}
    dependencies_by_patch: dict[int, tuple[str, ...]] = {}
    for (patch, _page, _pitch), fitted in zip(
            work_items,
            _parallel.ordered_map(_refine_one, work_items),
            strict=True):
        summaries.append(fitted)
        if fitted.metrics.adopted:
            replacements[int(patch.patch_id)] = fitted.refined.segment
            revised_by_id[int(patch.patch_id)] = fitted.refined
            dependencies_by_patch[int(patch.patch_id)] = (
                fitted.dependency_certificate_ids)

    patch_dependencies = tuple(sorted(dependencies_by_patch.items()))
    if not replacements:
        return ColorForwardRefinement(address, tuple(summaries), ())
    provisional = replace(address, placements=tuple(
        revised_by_id.get(int(patch.patch_id), patch)
        for patch in address.placements
    ))
    revised_address = replace(
        provisional,
        continuation_hints=_replace_hints(provisional, replacements),
    )
    return ColorForwardRefinement(
        revised_address, tuple(summaries), patch_dependencies)


__all__ = [
    "ColorForwardRefinement",
    "ColorRefinementLabels",
    "ColorRefinementMetrics",
    "ColorWindowRefinement",
    "FURNITURE_LOSS_SLACK",
    "affected_color_patch_ids",
    "collect_color_refinement_labels",
    "refine_color_address_once",
    "refine_color_window",
    "select_color_pose_sites",
]
