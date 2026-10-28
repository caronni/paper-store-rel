from __future__ import annotations

import time
from dataclasses import dataclass, replace
from fractions import Fraction
from typing import Iterable, Mapping

import numpy as np
from scipy import ndimage

from ..data import ROUTE_REFINE, Certificate, JobResult, Placement
from ..data import RefineBasis, TileKey, WindowEvidence, WindowId
from ..descriptor import (
    FactKey,
    Job,
    KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ,
    KEY_POSE_AFFINE,
    KEY_POSE_ROUTE,
    KEY_TILE,
    PluginDescriptor,
    Subject,
)
from ..format.identity import Family, FormatRow, SiteGeometry
from . import calibrate
from ..lib.geometry import (
    TILE_CELLS,
    compose_from_native,
    compose_to_native,
    site_parity,
    tile_of_cell,
)
from ..lib.pava import calibration_llr
from .tiles import printed_cells_for

BLOCK_CELLS: int = 16
VALIDATION_MODULUS: int = 4
MIN_PAYLOAD_TRAIN: int = 64
MIN_PAYLOAD_VALIDATION: int = 32
MIN_TRAIN_PER_CLASS: int = 20
MIN_VALIDATION_PER_CLASS: int = 10
MIN_CERTIFIED_BLOCKS: int = 4
MIN_POSE_PILOTS: int = 30
MIN_HELDOUT_GAIN: float = 1e-4
PILOT_MISMATCH_SLACK: float = 0.005
ANGLE_LIMIT_DEG: float = 0.15
ANGLE_COARSE_STEP_DEG: float = 0.15
ANGLE_FINE_STEP_DEG: float = 0.05
PHASE_LIMIT_CELLS: float = 0.25
PHASE_COARSE_STEP_CELLS: float = 0.25
PHASE_FINE_STEP_CELLS: float = 0.0625
POSE_SITE_CAP_TRAIN: int = 2048
POSE_SITE_CAP_VALIDATION: int = 1024
SCORE_SPREAD_FLOOR: float = 1e-6

STRIPE_PAGE_COEFFICIENT: int = 104729
STRIPE_Y_COEFFICIENT: int = 1009
STRIPE_X_COEFFICIENT: int = 9177
CAP_HASH_Y: int = 11400714819323198485
CAP_HASH_X: int = 14029467366897019727
GRID_EPSILON: float = 1e-12
DEDUP_DECIMALS: int = 12
CONTRAST_TIE: float = 1e-9

OUTCOME_ADOPTED: str = "adopted"

STAGE_REFINE: str = "refine"
REFINE_COST: int = 200
PRICES: tuple[tuple[str, int], ...] = ((STAGE_REFINE, REFINE_COST),)


@dataclass(frozen=True)
class LocalPose:
    origin_yx: tuple[float, float]
    jacobian_yx: tuple[tuple[float, float], tuple[float, float]]
    phase_yx: tuple[float, float]
    pitch_px: float
    angle_deg: float

    def matrix(self) -> np.ndarray:
        return np.asarray(self.jacobian_yx, np.float64)

    def points(self, cells_yx: np.ndarray) -> np.ndarray:
        cells = np.asarray(cells_yx, np.float64)
        return cells @ self.matrix().T + np.asarray(self.origin_yx, np.float64)


@dataclass(frozen=True)
class SegmentLabels:
    rows: np.ndarray
    page_cells_yx: np.ndarray
    values: np.ndarray
    validation: np.ndarray
    weights: np.ndarray
    is_pilot: np.ndarray
    block_ids: np.ndarray

    @property
    def train(self) -> np.ndarray:
        return ~self.validation


@dataclass(frozen=True)
class Revision:
    adopted: bool
    reason: str
    affine: tuple[float, ...] | None = None
    dtheta_deg: float = 0.0
    du_cells: float = 0.0
    dv_cells: float = 0.0
    baseline_logloss: float | None = None
    candidate_logloss: float | None = None
    candidates: int = 0
    basis: RefineBasis = ()


def certified_fields(row: FormatRow, geometry: SiteGeometry,
                     certificates: Iterable[Certificate],
                     ) -> dict[tuple[int, int, int], np.ndarray]:
    fields: dict[tuple[int, int, int], np.ndarray] = {}
    for certificate in certificates:
        address = (certificate.page, certificate.ty, certificate.tx)
        if address not in fields:
            fields[address] = printed_cells_for(
                row, geometry, certificate.page, certificate.ty,
                certificate.tx, certificate.user_bits)
    return fields


def block_validation(page: int, cells_yx: np.ndarray) -> np.ndarray:
    block = np.asarray(cells_yx, np.int64) // BLOCK_CELLS
    token = (page * STRIPE_PAGE_COEFFICIENT
             + block[:, 0] * STRIPE_Y_COEFFICIENT
             + block[:, 1] * STRIPE_X_COEFFICIENT)
    return (token % VALIDATION_MODULUS) == 0


def block_weights(block_ids: np.ndarray) -> np.ndarray:
    ids = np.asarray(block_ids, np.int64)
    if ids.size == 0:
        return np.zeros(0, np.float64)
    _unique, inverse, counts = np.unique(
        ids, return_inverse=True, return_counts=True)
    return 1.0 / counts[inverse].astype(np.float64)


def collect_labels(page: int, page_cells_yx: np.ndarray,
                   reference_values: np.ndarray,
                   printed: Mapping[tuple[int, int, int], np.ndarray],
                   ) -> SegmentLabels:
    cells = np.asarray(page_cells_yx, np.int64)
    reference = np.asarray(reference_values)
    pilot_local = np.flatnonzero(reference >= 0)
    pilot_cells = cells[pilot_local]
    pilot_values = reference[pilot_local].astype(np.uint8)
    pilot_validation = site_parity(pilot_cells[:, 0],
                                   pilot_cells[:, 1]).astype(bool)

    cargo_candidates = np.flatnonzero(reference < 0)
    selected_parts: list[np.ndarray] = []
    value_parts: list[np.ndarray] = []
    if cargo_candidates.size:
        cargo_ty, cargo_tx = tile_of_cell(cells[cargo_candidates, 0],
                                          cells[cargo_candidates, 1])
        addresses = np.unique(np.stack((cargo_ty, cargo_tx), axis=1), axis=0)
        for address in addresses:
            ty, tx = int(address[0]), int(address[1])
            field = printed.get((page, ty, tx))
            if field is None:
                continue
            selected = cargo_candidates[(cargo_ty == ty) & (cargo_tx == tx)]
            coords = cells[selected]
            selected_parts.append(selected)
            value_parts.append(np.asarray(
                field[coords[:, 0] % TILE_CELLS, coords[:, 1] % TILE_CELLS],
                np.uint8))
    if selected_parts:
        selected_all = np.concatenate(selected_parts)
        order = np.argsort(selected_all, kind="stable")
        cargo_local = selected_all[order].astype(np.int64, copy=False)
        cargo_values = np.concatenate(value_parts)[order]
    else:
        cargo_local = np.zeros(0, np.int64)
        cargo_values = np.zeros(0, np.uint8)
    cargo_cells = cells[cargo_local]
    cargo_validation = block_validation(page, cargo_cells)

    rows = np.concatenate((pilot_local, cargo_local)).astype(np.int64)
    selected_cells = np.concatenate(
        (pilot_cells, cargo_cells), axis=0).astype(np.int64)
    values = np.concatenate((pilot_values, cargo_values))
    validation = np.concatenate((pilot_validation, cargo_validation))
    is_pilot = np.concatenate((np.ones(pilot_local.size, bool),
                               np.zeros(cargo_local.size, bool)))
    by = selected_cells[:, 0] // BLOCK_CELLS
    bx = selected_cells[:, 1] // BLOCK_CELLS
    block_ids = (is_pilot.astype(np.int64) * 10**12
                 + page * 10**9 + by * 10**4 + bx)
    weights = np.zeros(rows.size, np.float64)
    weights[~validation] = block_weights(block_ids[~validation])
    weights[validation] = block_weights(block_ids[validation])
    return SegmentLabels(rows, selected_cells, values, validation, weights,
                         is_pilot, block_ids)


def support_metrics(labels: SegmentLabels) -> tuple[bool, str, dict[str, int]]:
    payload = ~labels.is_pilot
    payload_train = int(np.count_nonzero(payload & labels.train))
    payload_validation = int(np.count_nonzero(payload & labels.validation))
    blocks = int(np.unique(labels.block_ids[payload]).size)
    counts = {"n_payload_train": payload_train,
              "n_payload_validation": payload_validation,
              "n_certified_blocks": blocks}
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
           int(np.count_nonzero(valid_values == 1))
           ) < MIN_VALIDATION_PER_CLASS:
        return False, "validation_class_starved", counts
    if blocks < MIN_CERTIFIED_BLOCKS:
        return False, "insufficient_certified_blocks", counts
    return True, "", counts


def deterministic_cap(positions: np.ndarray, cells_yx: np.ndarray,
                      cap: int) -> np.ndarray:
    rows = np.asarray(positions, np.int64)
    if rows.size <= cap:
        return rows
    coords = np.asarray(cells_yx, np.int64)[rows]
    token = (coords[:, 0].astype(np.uint64) * np.uint64(CAP_HASH_Y)
             ^ coords[:, 1].astype(np.uint64) * np.uint64(CAP_HASH_X))
    return rows[np.argsort(token, kind="stable")[:cap]]


def select_pose_sites(labels: SegmentLabels, validation: bool) -> np.ndarray:
    side = labels.validation if validation else labels.train
    cap = POSE_SITE_CAP_VALIDATION if validation else POSE_SITE_CAP_TRAIN
    positions = np.flatnonzero(side)
    pilots = positions[labels.is_pilot[positions]]
    cargo = positions[~labels.is_pilot[positions]]
    cargo = deterministic_cap(cargo, labels.page_cells_yx,
                              max(cap - pilots.size, 0))
    selected = np.concatenate((pilots, cargo))
    return selected[np.argsort(labels.rows[selected], kind="stable")].astype(
        np.int64, copy=False)


def pose_candidate(base: LocalPose, dtheta_deg: float, du_cells: float,
                   dv_cells: float) -> LocalPose:
    angle = np.deg2rad(float(dtheta_deg))
    rotation = np.asarray(((np.cos(angle), np.sin(angle)),
                           (-np.sin(angle), np.cos(angle))), np.float64)
    jacobian0 = base.matrix()
    jacobian = rotation @ jacobian0
    origin = (np.asarray(base.origin_yx, np.float64)
              + jacobian0 @ np.asarray((du_cells, dv_cells), np.float64))
    pitch_y = float(np.hypot(*jacobian[:, 0]))
    pitch_x = float(np.hypot(*jacobian[:, 1]))
    angle_deg = float(np.degrees(np.arctan2(jacobian[0, 1], jacobian[1, 1])))
    return LocalPose(
        (float(origin[0]), float(origin[1])),
        tuple(tuple(float(value) for value in row) for row in jacobian),
        base.phase_yx, 0.5 * (pitch_y + pitch_x), angle_deg)


def pose_objective(means: np.ndarray, values: np.ndarray,
                   weights: np.ndarray) -> float:
    raw = np.asarray(means, np.float64)
    labels = np.asarray(values, np.uint8)
    weight = np.asarray(weights, np.float64)
    paper, ink = labels == 0, labels == 1
    if not paper.any() or not ink.any():
        return -np.inf
    mean_paper = float(np.sum(weight[paper] * raw[paper])
                       / np.sum(weight[paper]))
    mean_ink = float(np.sum(weight[ink] * raw[ink]) / np.sum(weight[ink]))
    center = float(np.sum(weight * raw) / np.sum(weight))
    spread = max(float(np.sum(weight * np.abs(raw - center)) / np.sum(weight)),
                 SCORE_SPREAD_FLOOR)
    return (mean_paper - mean_ink) / spread


def weighted_logloss(logits: np.ndarray, values: np.ndarray,
                     weights: np.ndarray) -> float:
    x = np.asarray(logits, np.float64)
    y = np.asarray(values, np.float64)
    w = np.asarray(weights, np.float64)
    losses = np.logaddexp(0.0, x) - y * x
    return float(np.sum(w * losses) / np.sum(w))


def score_reference(means: np.ndarray) -> tuple[np.float32, np.float32]:
    raw = np.asarray(means, np.float32)
    midpoint = np.float32(np.median(raw))
    spread = max(np.float32(np.abs(raw - midpoint).mean()),
                 np.float32(SCORE_SPREAD_FLOOR))
    return midpoint, spread


def window_scores(means: np.ndarray, midpoint: np.float32,
                  spread: np.float32) -> np.ndarray:
    return (midpoint - np.asarray(means, np.float32)) / spread


def adoption_gate(baseline_loss: float, candidate_loss: float,
                  baseline_pilot_mismatch: float,
                  candidate_pilot_mismatch: float,
                  baseline_raw_pilot_mismatch: float,
                  candidate_raw_pilot_mismatch: float) -> bool:
    return bool(candidate_loss + MIN_HELDOUT_GAIN < baseline_loss
                and candidate_pilot_mismatch
                <= baseline_pilot_mismatch + PILOT_MISMATCH_SLACK
                and candidate_raw_pilot_mismatch
                <= baseline_raw_pilot_mismatch + PILOT_MISMATCH_SLACK)


def candidate_grid() -> tuple[tuple[float, float, float], ...]:
    angles = np.arange(-ANGLE_LIMIT_DEG, ANGLE_LIMIT_DEG + GRID_EPSILON,
                       ANGLE_COARSE_STEP_DEG)
    phase = np.arange(-PHASE_LIMIT_CELLS, PHASE_LIMIT_CELLS + GRID_EPSILON,
                      PHASE_COARSE_STEP_CELLS)
    return tuple((float(dtheta), float(du), float(dv))
                 for dtheta in angles for du in phase for dv in phase)


def fine_grid(best: tuple[float, float, float],
              ) -> tuple[tuple[float, float, float], ...]:
    angles = np.arange(best[0] - ANGLE_COARSE_STEP_DEG,
                       best[0] + ANGLE_COARSE_STEP_DEG + GRID_EPSILON,
                       ANGLE_FINE_STEP_DEG)
    du = np.arange(best[1] - PHASE_COARSE_STEP_CELLS,
                   best[1] + PHASE_COARSE_STEP_CELLS + GRID_EPSILON,
                   PHASE_FINE_STEP_CELLS)
    dv = np.arange(best[2] - PHASE_COARSE_STEP_CELLS,
                   best[2] + PHASE_COARSE_STEP_CELLS + GRID_EPSILON,
                   PHASE_FINE_STEP_CELLS)
    out: list[tuple[float, float, float]] = []
    for dtheta in angles:
        if abs(dtheta) > ANGLE_LIMIT_DEG + GRID_EPSILON:
            continue
        for one in du:
            if abs(one) > PHASE_LIMIT_CELLS + GRID_EPSILON:
                continue
            for other in dv:
                if abs(other) <= PHASE_LIMIT_CELLS + GRID_EPSILON:
                    out.append((float(dtheta), float(one), float(other)))
    return tuple(out)


def select_best(candidates: Mapping[tuple[float, float, float],
                                    tuple[float, float]],
                keys: Iterable[tuple[float, float, float]],
                ) -> tuple[float, float, float]:
    rows = tuple(keys)
    maximum = max(candidates[key][0] for key in rows)
    near = [key for key in rows if maximum - candidates[key][0] <= CONTRAST_TIE]
    return min(near, key=lambda key: (candidates[key][1],
                                      sum(value * value for value in key),
                                      tuple(abs(value) for value in key), key))


def local_segment(native_affine: tuple[float, ...],
                  source_per_output: Fraction, page_cells_yx: np.ndarray,
                  ) -> tuple[LocalPose, np.ndarray]:
    terms = compose_from_native(tuple(native_affine), source_per_output)
    matrix = np.asarray(terms, np.float64).reshape(2, 3)
    linear = matrix[:, :2]
    cells = np.asarray(page_cells_yx, np.int64)
    corner = cells.min(axis=0).astype(np.int64)
    origin = linear @ (corner.astype(np.float64) + 0.5) + matrix[:, 2]
    local = (cells - corner).astype(np.int64)
    pitch_px = 0.5 * (float(np.hypot(*linear[:, 0]))
                      + float(np.hypot(*linear[:, 1])))
    pose = LocalPose(
        (float(origin[0]), float(origin[1])),
        tuple(tuple(float(value) for value in row) for row in linear),
        (0.0, 0.0), pitch_px,
        float(np.degrees(np.arctan2(linear[0, 1], linear[1, 1]))))
    return pose, local


def native_terms(pose: LocalPose, page_cells_yx: np.ndarray,
                 source_per_output: Fraction) -> tuple[float, ...]:
    linear = pose.matrix()
    corner = np.asarray(page_cells_yx, np.int64).min(axis=0).astype(np.float64)
    offset = np.asarray(pose.origin_yx, np.float64) - linear @ (corner + 0.5)
    return compose_to_native(
        (float(linear[0, 0]), float(linear[0, 1]), float(offset[0]),
         float(linear[1, 0]), float(linear[1, 1]), float(offset[1])),
        source_per_output)


def sample_at(filtered_luma: np.ndarray, crop_yx_px: tuple[int, int],
              backing_luma: float, pose: LocalPose, local_cells_yx: np.ndarray,
              offsets_px: np.ndarray | None = None) -> np.ndarray:
    points = pose.points(np.asarray(local_cells_yx, np.float64))
    if offsets_px is not None:
        points = points + np.asarray(offsets_px, np.float64)
    local = points - np.asarray(crop_yx_px, np.float64)
    return np.asarray(ndimage.map_coordinates(filtered_luma, local.T, order=1,
                                              cval=backing_luma), np.float64)


def refine_window(placement: Placement, evidence: WindowEvidence,
                  filtered_luma: np.ndarray, crop_yx_px: tuple[int, int],
                  backing_luma: float, source_per_output: Fraction,
                  printed: Mapping[tuple[int, int, int], np.ndarray],
                  offsets_px: np.ndarray | None = None) -> Revision:
    cells = np.asarray(evidence.page_cells_yx, np.int64)
    labels = collect_labels(placement.page, cells, evidence.reference_values,
                            printed)
    supported, reason, _counts = support_metrics(labels)
    if not supported:
        return Revision(False, reason)
    train = select_pose_sites(labels, validation=False)
    valid = select_pose_sites(labels, validation=True)
    train_pilots = train[labels.is_pilot[train]]
    valid_pilots = valid[labels.is_pilot[valid]]
    if (train_pilots.size < MIN_POSE_PILOTS
            or valid_pilots.size < MIN_POSE_PILOTS):
        return Revision(False, "insufficient_pose_pilot_validation")

    base_pose, local = local_segment(placement.native_affine,
                                     source_per_output, cells)
    baseline = sample_at(filtered_luma, crop_yx_px, backing_luma, base_pose,
                         local, offsets_px)
    midpoint, spread = score_reference(baseline)
    knots = np.asarray(evidence.knots, np.float64)
    probs = np.asarray(evidence.probs, np.float64)

    def logits_of(means: np.ndarray) -> np.ndarray:
        return np.asarray(calibration_llr(
            window_scores(means, midpoint, spread), knots, probs), np.float64)

    train_local = local[labels.rows[train]]
    train_values = labels.values[train]
    train_weights = labels.weights[train]
    valid_rows = labels.rows[valid]
    valid_values = labels.values[valid]
    valid_weights = labels.weights[valid]
    pilot_rows = labels.rows[valid_pilots]
    pilot_values = labels.values[valid_pilots]
    train_offsets = (None if offsets_px is None
                     else np.asarray(offsets_px,
                                     np.float64)[labels.rows[train]])

    base_logits = logits_of(baseline)
    base_loss = weighted_logloss(base_logits[valid_rows], valid_values,
                                 valid_weights)
    base_pilot_mismatch = float(np.mean(
        (base_logits[pilot_rows] > 0.0) != (pilot_values > 0)))
    base_raw = np.asarray(baseline, np.float32)
    base_raw_mismatch = float(np.mean(
        (base_raw[pilot_rows] < midpoint) != (pilot_values > 0)))

    candidates: dict[tuple[float, float, float], tuple[float, float]] = {}

    def score(dtheta_deg: float, du_cells: float, dv_cells: float) -> None:
        key = (round(float(dtheta_deg), DEDUP_DECIMALS),
               round(float(du_cells), DEDUP_DECIMALS),
               round(float(dv_cells), DEDUP_DECIMALS))
        if key in candidates:
            return
        pose = pose_candidate(base_pose, *key)
        means = sample_at(filtered_luma, crop_yx_px, backing_luma, pose,
                          train_local, train_offsets)
        contrast = pose_objective(means, train_values, train_weights)
        loss = weighted_logloss(logits_of(means), train_values, train_weights)
        candidates[key] = contrast, loss

    for row in candidate_grid():
        score(*row)
    coarse = select_best(candidates, tuple(candidates))
    for row in fine_grid(coarse):
        score(*row)
    best = select_best(candidates, tuple(candidates))

    pose = pose_candidate(base_pose, *best)
    if pose == base_pose:
        return Revision(False, "active_pose_selected",
                        baseline_logloss=base_loss,
                        candidates=len(candidates))
    means = sample_at(filtered_luma, crop_yx_px, backing_luma, pose, local,
                      offsets_px)
    logits = logits_of(means)
    loss = weighted_logloss(logits[valid_rows], valid_values, valid_weights)
    pilot_mismatch = float(np.mean(
        (logits[pilot_rows] > 0.0) != (pilot_values > 0)))
    raw = np.asarray(means, np.float32)
    raw_mismatch = float(np.mean(
        (raw[pilot_rows] < midpoint) != (pilot_values > 0)))
    if not adoption_gate(base_loss, loss, base_pilot_mismatch, pilot_mismatch,
                         base_raw_mismatch, raw_mismatch):
        return Revision(False, "pose_gate_failed", None, *best, base_loss,
                        loss, len(candidates))
    affine = native_terms(pose, cells, source_per_output)
    if affine == tuple(float(term) for term in placement.native_affine):
        return Revision(False, "unchanged_affine", None, *best, base_loss,
                        loss, len(candidates))
    return Revision(True, OUTCOME_ADOPTED, affine, *best, base_loss, loss,
                    len(candidates), tuple(sorted(printed)))


def revised_placement(placement: Placement, revision: Revision) -> Placement:
    return replace(placement, native_affine=revision.affine,
                   route=ROUTE_REFINE, refine_basis=revision.basis)


def reach_tiles(page_cells_yx: np.ndarray) -> tuple[tuple[int, int], ...]:
    cells = np.asarray(page_cells_yx, np.int64)
    if not cells.shape[0]:
        return ()
    ty, tx = tile_of_cell(cells[:, 0], cells[:, 1])
    base_y, base_x = int(ty.min()), int(tx.min())
    span = int(tx.max()) - base_x + 1
    codes = np.unique((ty - base_y) * span + (tx - base_x))
    return tuple((base_y + int(code) // span, base_x + int(code) % span)
                 for code in codes)


def certified_reach(page: int, reach: tuple[tuple[int, int], ...],
                    certified: frozenset[tuple[int, int, int]],
                    ) -> tuple[tuple[int, int, int], ...]:
    return tuple(sorted(
        (page, ty, tx) for ty, tx in reach
        if (page, ty, tx) in certified))


def refine_eligible(page: int, reach: tuple[tuple[int, int], ...],
                    certified: frozenset[tuple[int, int, int]],
                    basis: RefineBasis) -> bool:
    current = certified_reach(page, reach, certified)
    return (0 < len(current) < len(reach)
            and set(current) > set(basis))


def refine_exhausted(page: int, reach: tuple[tuple[int, int], ...],
                     certified: frozenset[tuple[int, int, int]]) -> bool:
    return bool(reach) and len(
        certified_reach(page, reach, certified)) == len(reach)


def reach_certified(store: object, page: int,
                    reach: tuple[tuple[int, int], ...],
                    ) -> frozenset[TileKey]:
    streams = store.row.streams
    return frozenset(
        (page, ty, tx) for ty, tx in reach
        if any(store.has_certificate((page, ty, tx, stream.stream_id))
               for stream in streams))


@dataclass(frozen=True)
class RefineOutcome:
    window_id: WindowId
    revision: Revision


def prepare_refine(store: object, subject: Subject,
                   stage: str) -> Job | None:
    wid: WindowId = subject
    placement = store.placement(wid)
    evidence = store.evidence(wid)
    if placement is None or evidence is None or not evidence.accepted:
        return None
    if store.row.family is not Family.K:
        return None
    tiles_in_reach = store.evidence_reach(wid)
    reach = reach_certified(store, placement.page, tiles_in_reach)
    if not refine_eligible(placement.page, tiles_in_reach, reach,
                           placement.refine_basis):
        return None
    reach_certs = tuple(
        store.certificate(key) for key in sorted(
            (page, ty, tx, stream.stream_id)
            for page, ty, tx in reach
            for stream in store.row.streams
            if store.has_certificate((page, ty, tx, stream.stream_id))))
    pitch_native = store.region_pitch(wid[:3])
    if pitch_native is None:
        return None
    level = store.level(wid[0], wid[1])
    scale = level.scale
    pitch_level = pitch_native / float(scale)
    plane_rasters = store.sampling_planes((wid[0], wid[1]))
    row = store.row
    site_geometry = store.geometry

    def job() -> JobResult:
        started = time.thread_time()
        planes = tuple(raster.open() for raster in plane_rasters)
        points = calibrate.scan_points_yx(
            placement.native_affine, scale, evidence.page_cells_yx)
        raster_shape = (int(planes[0].shape[0]),
                        int(planes[0].shape[1]))
        crop = calibrate.window_crop(planes, points, raster_shape,
                                     pitch_level)
        printed = certified_fields(row, site_geometry, reach_certs)
        revision = refine_window(
            placement, evidence, crop.filtered, (crop.y0, crop.x0),
            crop.fill, scale, printed)
        return JobResult((RefineOutcome(wid, revision),), (),
                         time.thread_time() - started)

    return job


def _refine_subjects(store: object, fact: object) -> tuple[Subject, ...]:
    if store.row.family is not Family.K:
        return ()
    return (fact.window_id,)


def _refine_reads(store: object, subject: Subject) -> tuple[FactKey, ...]:
    wid: WindowId = subject
    keys: list[FactKey] = [(KEY_EVIDENCE_FIT, wid), (KEY_EVIDENCE_READ, wid),
                           (KEY_POSE_AFFINE, wid), (KEY_POSE_ROUTE, wid)]
    placement = store.placement(wid)
    reach = store.window_reach(wid)
    if placement is not None and reach is not None:
        for ty, tx in reach:
            for stream in store.row.streams:
                keys.append((KEY_TILE, placement.page, ty, tx,
                             stream.stream_id))
    return tuple(keys)


def _refine_eligible(store: object, subject: Subject) -> bool:
    placement = store.placement(subject)
    evidence = store.evidence(subject)
    if placement is None or evidence is None or not evidence.accepted:
        return False
    reach = store.evidence_reach(subject)
    return refine_eligible(
        placement.page, reach,
        reach_certified(store, placement.page, reach),
        placement.refine_basis)


def _refine_retire(store: object, subject: Subject) -> bool:
    placement = store.placement(subject)
    evidence = store.evidence(subject)
    if placement is None or evidence is None or not evidence.accepted:
        return False
    reach = store.evidence_reach(subject)
    return refine_exhausted(
        placement.page, reach,
        reach_certified(store, placement.page, reach))


def _refine_stage(store: object, subject: Subject) -> str | None:
    return STAGE_REFINE


def _refine_cost(store: object, subject: Subject, stage: str,
                 attempts: int, last_cost: int) -> int:
    return REFINE_COST


REFINE_DESCRIPTOR = PluginDescriptor(
    name="refine",
    subject_kind="window",
    born_by=(Placement,),
    subjects_of=_refine_subjects,
    reads=_refine_reads,
    eligible=_refine_eligible,
    stage=_refine_stage,
    cost=_refine_cost,
    retire=_refine_retire,
    prepare=prepare_refine,
    produces=(RefineOutcome,),
    prices=PRICES,
)
