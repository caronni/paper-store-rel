#: Design record: SCHEDULE.md, row refine.color (labels, the frozen
#: per-plane calibration, the gate, the two crop-free pre-gates).
from __future__ import annotations

import time
from dataclasses import dataclass
from fractions import Fraction
from typing import Mapping

import numpy as np

from .. import sched_trace
from ..data import Certificate, FIELD_BASIS_KEY, JobResult, Placement
from ..data import RefineBasis, WindowId, basis_field_revision
from ..descriptor import (
    FactKey,
    Job,
    KEY_PLANE_FIELD,
    KEY_POSE_AFFINE,
    KEY_POSE_ROUTE,
    KEY_TILE,
    PluginDescriptor,
    RETIRE_REACH_EXHAUSTED,
    Subject,
)
from ..format.identity import Family, FormatRow, SiteGeometry
from ..lib import page_map
from ..lib.geometry import compose_to_native
from . import color_region
from . import color_region_anchor as anchor
from . import pose as pose_plugin
from .refine import (
    BLOCK_CELLS,
    CAP_HASH_X,
    CAP_HASH_Y,
    DEDUP_DECIMALS,
    LocalPose,
    MIN_CERTIFIED_BLOCKS,
    MIN_HELDOUT_GAIN,
    MIN_PAYLOAD_TRAIN,
    MIN_PAYLOAD_VALIDATION,
    MIN_POSE_PILOTS,
    MIN_TRAIN_PER_CLASS,
    MIN_VALIDATION_PER_CLASS,
    OUTCOME_ADOPTED,
    OUTCOME_ALREADY_STOOD,
    POSE_SITE_CAP_TRAIN,
    POSE_SITE_CAP_VALIDATION,
    REFINE_COST,
    STAGE_REFINE,
    RefineOutcome,
    Revision,
    SCORE_SPREAD_FLOOR,
    block_validation,
    block_weights,
    candidate_grid,
    fine_grid,
    pose_candidate,
    pose_key,
    pose_objective,
    select_best,
    stood_poses,
    weighted_logloss,
)

PLUGIN: str = "refine.color"
PRICES: tuple[tuple[str, int], ...] = ((STAGE_REFINE, REFINE_COST),)
#: The furniture (word/dust) leg is the colour pilot non-regression:
#: held-out furniture logloss under the frozen calibration must not
#: worsen.  The slack absorbs float re-association only, never a real
#: loss -- it is not a tolerance policy (SCHEDULE.md, row refine.color).
FURNITURE_LOSS_SLACK: float = 1e-9
#: Odd 64-bit mixing constant for the PLANE axis of the deterministic
#: cargo site cap.  K's cap hashes (y, x) alone; a colour observation is
#: (y, x, plane), and an unmixed plane term would leave one cell's three
#: observations adjacent in token order, so the cut takes them as a block.
PLANE_TOKEN_MIX: int = 0x9E3779B97F4A7C15

CertKey = tuple[int, int, int, str]
Planes = tuple[np.ndarray, np.ndarray, np.ndarray]


@dataclass(frozen=True)
class ColorLabels:
    row_indices: np.ndarray
    planes: np.ndarray
    page_cells_yx: np.ndarray
    bits: np.ndarray
    validation: np.ndarray
    weights: np.ndarray
    is_furniture: np.ndarray
    block_ids: np.ndarray

    @property
    def train(self) -> np.ndarray:
        return ~self.validation


def collect_labels(page: int, page_cells_yx: np.ndarray,
                   furniture_kind: np.ndarray,
                   known_component_bits: np.ndarray,
                   known_component_mask: np.ndarray) -> ColorLabels:
    kinds = np.asarray(furniture_kind, np.int8)
    bits_by_row = np.asarray(known_component_bits, np.uint8)
    mask_by_row = np.asarray(known_component_mask, bool)
    furniture_rows = np.flatnonzero(kinds >= 0).astype(np.int64)
    cargo_candidates = np.flatnonzero(kinds < 0).astype(np.int64)
    cargo_local, cargo_planes = np.nonzero(mask_by_row[cargo_candidates])
    cargo_rows = cargo_candidates[cargo_local]
    cargo_bits = bits_by_row[cargo_rows, cargo_planes]
    row_indices = np.concatenate((np.repeat(furniture_rows, 3), cargo_rows))
    planes = np.concatenate((
        np.tile(np.arange(3, dtype=np.int64), furniture_rows.size),
        cargo_planes.astype(np.int64)))
    bits = np.concatenate((
        bits_by_row[furniture_rows].reshape(-1), cargo_bits))
    is_furniture = np.concatenate((
        np.ones(furniture_rows.size * 3, bool),
        np.zeros(cargo_rows.size, bool)))
    label_cells = np.asarray(page_cells_yx, np.int64)[row_indices]
    # ONE shared holdout for furniture and cargo alike (K's diagonal-stripe
    # partition), but SEPARATE block weights: the leading is_furniture digit
    # keeps furniture and cargo in disjoint block-id spaces, so neither
    # population's block sizes can re-weight the other's.
    validation = block_validation(page, label_cells)
    by = label_cells[:, 0] // BLOCK_CELLS
    bx = label_cells[:, 1] // BLOCK_CELLS
    block_ids = (is_furniture.astype(np.int64) * 10**12
                 + page * 10**9 + by * 10**4 + bx)
    weights = np.zeros(row_indices.size, np.float64)
    weights[~validation] = block_weights(block_ids[~validation])
    weights[validation] = block_weights(block_ids[validation])
    return ColorLabels(row_indices, planes, label_cells, bits, validation,
                       weights, is_furniture, block_ids)


def support_metrics(labels: ColorLabels) -> tuple[bool, str]:
    cargo = ~labels.is_furniture
    cargo_train = int(np.count_nonzero(cargo & labels.train))
    cargo_validation = int(np.count_nonzero(cargo & labels.validation))
    blocks = int(np.unique(labels.block_ids[cargo]).size)
    if cargo_train < MIN_PAYLOAD_TRAIN:
        return False, "insufficient_payload_train"
    if cargo_validation < MIN_PAYLOAD_VALIDATION:
        return False, "insufficient_payload_validation"
    train_bits = labels.bits[labels.train]
    valid_bits = labels.bits[labels.validation]
    if min(int(np.count_nonzero(train_bits == 0)),
           int(np.count_nonzero(train_bits == 1))) < MIN_TRAIN_PER_CLASS:
        return False, "train_class_starved"
    if min(int(np.count_nonzero(valid_bits == 0)),
           int(np.count_nonzero(valid_bits == 1))
           ) < MIN_VALIDATION_PER_CLASS:
        return False, "validation_class_starved"
    if blocks < MIN_CERTIFIED_BLOCKS:
        return False, "insufficient_certified_blocks"
    return True, ""


def select_pose_sites(labels: ColorLabels, validation: bool) -> np.ndarray:
    side = labels.validation if validation else labels.train
    cap = POSE_SITE_CAP_VALIDATION if validation else POSE_SITE_CAP_TRAIN
    positions = np.flatnonzero(side)
    furniture = positions[labels.is_furniture[positions]]
    cargo = positions[~labels.is_furniture[positions]]
    budget = max(cap - furniture.size, 0)
    if cargo.size > budget:
        coords = labels.page_cells_yx[cargo]
        token = (coords[:, 0].astype(np.uint64) * np.uint64(CAP_HASH_Y)
                 ^ coords[:, 1].astype(np.uint64) * np.uint64(CAP_HASH_X)
                 ^ labels.planes[cargo].astype(np.uint64)
                 * np.uint64(PLANE_TOKEN_MIX))
        cargo = cargo[np.argsort(token, kind="stable")[:budget]]
    return np.sort(np.concatenate((furniture, cargo))).astype(
        np.int64, copy=False)


def window_pose(affine: anchor.Affine) -> LocalPose:
    matrix = np.asarray(((affine[0], affine[1]), (affine[3], affine[4])),
                        np.float64)
    return LocalPose(
        (float(affine[2]), float(affine[5])),
        ((float(affine[0]), float(affine[1])),
         (float(affine[3]), float(affine[4]))),
        (0.0, 0.0),
        0.5 * (float(np.hypot(*matrix[:, 0]))
               + float(np.hypot(*matrix[:, 1]))),
        float(np.degrees(np.arctan2(matrix[0, 1], matrix[1, 1]))))


def revised_native_affine(pose: LocalPose, rot_k: int,
                          shape_yx_cells: tuple[int, int],
                          page_origin_yx: tuple[int, int],
                          source_per_output: Fraction) -> tuple[float, ...]:
    rotation, translation = pose_plugin.rotation_affine(rot_k,
                                                        shape_yx_cells)
    linear = pose.matrix() @ np.linalg.inv(rotation)
    offset = (np.asarray(pose.origin_yx, np.float64)
              - linear @ (translation
                          + np.asarray(page_origin_yx, np.float64) + 0.5))
    return compose_to_native(
        (float(linear[0, 0]), float(linear[0, 1]), float(offset[0]),
         float(linear[1, 0]), float(linear[1, 1]), float(offset[1])),
        source_per_output)


def local_field_offsets(row: FormatRow,
                        fields: color_region.PlaneFields | None,
                        window: color_region.RegionWindow,
                        page_cells_yx: np.ndarray,
                        ) -> tuple[np.ndarray | None, ...] | None:
    """The page's standing per-plane deltas, in LOCAL CELL units.

    The pose maps local cells to scan points, so a per-cell shift of the
    local coordinate is exactly the per-plane sampling correction — and
    it stays correct for every candidate pose the refit tries, which is
    why the field rides both arms of the gate.  The field is PAGE-axis
    dots, so it comes down into this window's own frame through the one
    mapping first: at rot 1, 2 and 3 the two frames disagree and
    reversing the pair would move the sampler the wrong way.
    """
    offsets = color_region.field_offsets(fields, page_cells_yx)
    if offsets is None:
        return None
    cell_dots = float(color_region.cell_dots_of(row))
    return tuple(
        None if entry is None
        else page_map.local_axes(entry, window.rotation)[:, ::-1] / cell_dots
        for entry in offsets)


def sample_planes(filtered: np.ndarray, y0: int, x0: int, pose: LocalPose,
                  local_cells: np.ndarray,
                  offsets: tuple[np.ndarray | None, ...] | None,
                  ) -> np.ndarray:
    if offsets is None:
        return anchor.sample_rgb(filtered, y0, x0, pose.points(local_cells))
    out = np.empty((local_cells.shape[0], 3), np.float64)
    for plane, shift in enumerate(offsets):
        cells = local_cells if shift is None else local_cells + shift
        out[:, plane] = anchor.sample_plane(filtered, y0, x0,
                                            pose.points(cells), plane)
    return out


def _subset(offsets: tuple[np.ndarray | None, ...] | None,
            selected: np.ndarray) -> tuple[np.ndarray | None, ...] | None:
    if offsets is None:
        return None
    return tuple(None if entry is None else entry[selected]
                 for entry in offsets)


def refine_color_window(row: FormatRow, geometry: SiteGeometry,
                        window: color_region.RegionWindow, planes: Planes,
                        certificates: Mapping[CertKey, Certificate],
                        placement: Placement, source_per_output: Fraction,
                        pitch_px: float,
                        plane_fields: color_region.PlaneFields | None = None,
                        ) -> Revision:
    rows = color_region.build_window_rows(row, geometry, window,
                                          certificates, {})
    labels = collect_labels(window.page, rows.page_cells_yx,
                            rows.furniture_kind, rows.known_component_bits,
                            rows.known_component_mask)
    supported, reason = support_metrics(labels)
    if not supported:
        return Revision(False, reason)
    train = select_pose_sites(labels, validation=False)
    valid = select_pose_sites(labels, validation=True)
    train_furniture = train[labels.is_furniture[train]]
    valid_furniture = valid[labels.is_furniture[valid]]
    if (train_furniture.size < MIN_POSE_PILOTS
            or valid_furniture.size < MIN_POSE_PILOTS):
        return Revision(False, "insufficient_pose_pilot_validation")

    base = window_pose(window.affine)
    local_cells = np.asarray(window.local_cells_yx, np.float64)
    field_offsets = local_field_offsets(row, plane_fields, window,
                                        rows.page_cells_yx)
    crop_y0, crop_x0, raw = anchor.native_crop(
        planes, anchor.window_points(window.shape_yx_cells, window.affine),
        anchor.window_halo(pitch_px))
    filtered = anchor.filtered_rgb(raw, pitch_px, 1.0)
    baseline_points = base.points(local_cells)
    inside = ((baseline_points[:, 0] >= crop_y0)
              & (baseline_points[:, 1] >= crop_x0)
              & (baseline_points[:, 0] <= crop_y0 + filtered.shape[0] - 1)
              & (baseline_points[:, 1] <= crop_x0 + filtered.shape[1] - 1))
    if not bool(np.all(inside)):
        return Revision(False, "baseline_outside_crop")
    # The frozen per-plane calibration: midpoint and spread are minted once
    # from the BASELINE pose and reused for every candidate, so both arms of
    # the gate ride the same transform and the comparison measures POSE, not
    # calibration.  It also cancels the RGB scale -- hence the undivided crop.
    baseline_all = sample_planes(filtered, crop_y0, crop_x0, base,
                                 local_cells, field_offsets)
    midpoint = np.median(baseline_all, axis=0)
    spread = np.maximum(np.mean(np.abs(baseline_all - midpoint), axis=0),
                        SCORE_SPREAD_FLOOR)

    def flat_scores(samples_by_row: np.ndarray, row_lookup: np.ndarray,
                    positions: np.ndarray) -> np.ndarray:
        selected = labels.planes[positions]
        values = samples_by_row[row_lookup, selected]
        return (midpoint[selected] - values) / spread[selected]

    train_rows_idx = labels.row_indices[train]
    train_unique, train_inverse = np.unique(train_rows_idx,
                                            return_inverse=True)
    train_local = local_cells[train_unique]
    train_field = _subset(field_offsets, train_unique)
    train_bits = labels.bits[train]
    train_weights = labels.weights[train]
    valid_rows_idx = labels.row_indices[valid]
    valid_bits = labels.bits[valid]
    valid_weights = labels.weights[valid]
    furniture_in_valid = labels.is_furniture[valid]
    furniture_bits = valid_bits[furniture_in_valid]
    furniture_weights = valid_weights[furniture_in_valid]

    base_valid_scores = flat_scores(baseline_all, valid_rows_idx, valid)
    base_loss = weighted_logloss(base_valid_scores, valid_bits,
                                 valid_weights)
    base_furniture_loss = weighted_logloss(
        base_valid_scores[furniture_in_valid], furniture_bits,
        furniture_weights)

    candidates: dict[tuple[float, float, float], tuple[float, float]] = {}

    def score(dtheta_deg: float, du_cells: float, dv_cells: float) -> None:
        key = (round(float(dtheta_deg), DEDUP_DECIMALS),
               round(float(du_cells), DEDUP_DECIMALS),
               round(float(dv_cells), DEDUP_DECIMALS))
        if key in candidates:
            return
        pose = pose_candidate(base, *key)
        samples = sample_planes(filtered, crop_y0, crop_x0, pose,
                                train_local, train_field)
        scores = flat_scores(samples, train_inverse, train)
        # K's contrast objective maximizes mean(paper) - mean(ink), so it wants
        # PAPER-HIGH values; the frozen calibration is ink-positive, hence the
        # negation here and only here (the logloss below keeps the raw sign).
        # Drop the minus and the search silently maximizes the wrong direction.
        contrast = pose_objective(-scores, train_bits, train_weights)
        loss = weighted_logloss(scores, train_bits, train_weights)
        candidates[key] = contrast, loss

    for entry in candidate_grid():
        score(*entry)
    coarse = select_best(candidates, tuple(candidates))
    for entry in fine_grid(coarse):
        score(*entry)
    best = select_best(candidates, tuple(candidates))
    pose = pose_candidate(base, *best)
    if pose == base:
        return Revision(False, "active_pose_selected",
                        baseline_logloss=base_loss,
                        candidates=len(candidates))
    valid_unique, valid_inverse = np.unique(valid_rows_idx,
                                            return_inverse=True)
    samples = sample_planes(filtered, crop_y0, crop_x0, pose,
                            local_cells[valid_unique],
                            _subset(field_offsets, valid_unique))
    scores = flat_scores(samples, valid_inverse, valid)
    loss = weighted_logloss(scores, valid_bits, valid_weights)
    furniture_loss = weighted_logloss(scores[furniture_in_valid],
                                      furniture_bits, furniture_weights)
    if not (loss + MIN_HELDOUT_GAIN < base_loss
            and furniture_loss
            <= base_furniture_loss + FURNITURE_LOSS_SLACK):
        return Revision(False, "pose_gate_failed", None, *best, base_loss,
                        loss, len(candidates))
    affine = revised_native_affine(pose, placement.rot_k,
                                   window.shape_yx_cells,
                                   placement.page_origin_yx,
                                   source_per_output)
    if affine == tuple(float(term) for term in placement.native_affine):
        return Revision(False, "unchanged_affine", None, *best, base_loss,
                        loss, len(candidates))
    #: The already-stood guard, K's twin (D4) — an adoption here re-fires
    #: the whole colour lane, so a walked-back geometry is the dearest
    #: no-op in the schedule.
    if pose_key(affine) in stood_poses(placement):
        return Revision(False, OUTCOME_ALREADY_STOOD, None, *best, base_loss,
                        loss, len(candidates))
    return Revision(True, OUTCOME_ADOPTED, affine, *best, base_loss, loss,
                    len(candidates),
                    refine_basis(tuple(sorted(certificates)),
                                 color_region.field_revision_of(plane_fields)))


def reach_certified(store: object, page: int,
                    reach: tuple[tuple[int, int], ...],
                    ) -> tuple[CertKey, ...]:
    return tuple(sorted(
        (page, ty, tx, stream.stream_id)
        for ty, tx in reach
        for stream in store.row.streams
        if store.has_certificate((page, ty, tx, stream.stream_id))))


def refine_basis(reach: tuple[CertKey, ...],
                 field_revision: int) -> RefineBasis:
    """Everything a colour refinement of this window was fitted to.

    The certificates it read AND the page field it sampled through (W8
    R-D, design §2.7): the sampling geometry is an input like the labels
    are, and a basis that named only the labels called two different
    fits the same one (review F10).  The marker's KEY and the reader of
    it are `data`'s: `placement_ordinal` ranks on the revision, so the
    shape of a basis is the placement cell's schema, not this row's.
    """
    return tuple(reach) + ((FIELD_BASIS_KEY, int(field_revision)),)


def color_refine_eligible(reach: tuple[CertKey, ...], field_revision: int,
                          basis: RefineBasis) -> bool:
    """Is there anything new to fit this window's pose against?

    The anti-churn rule stands and is the first clause: a window whose
    certificate set has not grown has nothing new to say.  W8 R-D adds
    the other half of "the same inputs" — the page FIELD the sampler
    reads through.  A field-only change moves the sampling geometry
    under an adopted pose, so a partially decoded window is refinable
    again (review F10).
    """
    certified = tuple(key for key in basis if key[0] != FIELD_BASIS_KEY)
    return bool(reach) and (set(reach) > set(certified)
                            or field_revision != basis_field_revision(basis))


def color_refine_exhausted(n_tiles: int, n_streams: int,
                           reach: tuple[CertKey, ...]) -> bool:
    return bool(n_tiles) and len(reach) == n_tiles * n_streams


def prepare_color_refine(store: object, subject: Subject,
                         stage: str) -> Job | None:
    wid: WindowId = subject
    placement = store.placement(wid)
    if placement is None or store.row.family is Family.K:
        return None
    page_cells = store.page_cells(wid)
    if page_cells is None:
        return None
    page = placement.page
    reach_key = reach_certified(store, page, store.window_reach(wid))
    fields = store.page_plane_fields(page)
    if not color_refine_eligible(reach_key, store.field_revision(page),
                                 placement.refine_basis):
        return None
    suppressed = store.suppressed_codes(page)
    # Trace only (sched_trace, DEFAULT OFF), never acted on: the fit's
    # own inputs -- the certified reach it is fitted to and the page
    # field it samples through (the `refine_basis` of §2.7) plus the
    # suppression set and the pitch the crop uses.
    if sched_trace.TRACE.enabled:
        # `reach_key` is already a sorted tuple and `suppressed` a
        # sorted int64 array: both hash as they are.  Building ~2,000
        # reprs here charged ~1 ms per prepare to the engine thread,
        # outside the digest's own meter (review 2026-09-17, B-3).
        sched_trace.TRACE.note_input(
            "refine_basis",
            (stage, reach_key, int(store.field_revision(page)),
             suppressed))
    emit = color_region.emission_mask(store.row, page_cells, suppressed)
    cargo = color_region.cargo_cell_mask(
        color_region.cargo_site_mask(store.geometry), page_cells)
    if not bool(np.any(cargo & emit)):
        return None
    window = color_region.region_window(store, wid)
    scale = store.level(wid[0], wid[1]).scale
    pitch_values = tuple(
        store.placement(owid).pitch_px / float(scale)
        for owid in store.lane_page_windows(wid[0], wid[1], page))
    pitch_px = float(np.median(pitch_values))
    plane_rasters = store.rgb_planes((wid[0], wid[1]))
    reach_certs = {key: store.certificate(key) for key in reach_key}
    row = store.row
    site_geometry = store.geometry

    def job() -> JobResult:
        started = time.thread_time()
        planes = (plane_rasters[0].open(), plane_rasters[1].open(),
                  plane_rasters[2].open())
        revision = refine_color_window(row, site_geometry, window, planes,
                                       reach_certs, placement, scale,
                                       pitch_px, plane_fields=fields)
        return JobResult((RefineOutcome(wid, revision),), (),
                         time.thread_time() - started)

    return job


def _color_refine_subjects(store: object,
                           fact: object) -> tuple[Subject, ...]:
    if store.row.family is Family.K:
        return ()
    return (fact.window_id,)


def _color_refine_reads(store: object,
                        subject: Subject) -> tuple[FactKey, ...]:
    wid: WindowId = subject
    keys: list[FactKey] = [(KEY_POSE_AFFINE, wid), (KEY_POSE_ROUTE, wid)]
    placement = store.placement(wid)
    reach = store.window_reach(wid)
    if placement is not None and reach is not None:
        for plane in range(3):
            keys.append((KEY_PLANE_FIELD, placement.page, plane))
        for ty, tx in reach:
            for stream in store.row.streams:
                keys.append((KEY_TILE, placement.page, ty, tx,
                             stream.stream_id))
    return tuple(keys)


def _color_refine_eligible(store: object, subject: Subject) -> bool:
    placement = store.placement(subject)
    reach = store.window_reach(subject)
    if placement is None or reach is None:
        return False
    return color_refine_eligible(
        reach_certified(store, placement.page, reach),
        store.field_revision(placement.page),
        placement.refine_basis)


def _color_refine_retire(store: object, subject: Subject) -> str | None:
    """As `refine._refine_retire`, over `window_reach` and the streams.

    THE REACH IS NOT MONOTONE; THIS CLAUSE IS, AND HERE IS THE BOUND.
    `window_reach` moves with the pose, so "every stream of every
    tile in the reach is certified" could in principle go true and then
    false again -- and with the retire consult at every push
    (2026-09-21) a transiently exhausted reach would be terminal where
    the pop-only door merely sampled it.  It cannot happen, because
    after placement THIS ROW is the only writer of this window's pose:
    `place` retires on `placed`, the one other row that could re-place
    a placed window (`revisit`) was dissolved 2026-09-21, and `refine` /
    `refine.color` are born on disjoint families (`_refine_subjects`
    returns () off K, `_color_refine_subjects` returns () on it).  A
    retired refine writes no RefineOutcome, so its own reach is frozen
    and the clause stays true.
    """
    placement = store.placement(subject)
    reach = store.window_reach(subject)
    if placement is None or reach is None:
        return None
    if color_refine_exhausted(
            len(reach), len(store.row.streams),
            reach_certified(store, placement.page, reach)):
        return RETIRE_REACH_EXHAUSTED
    return None


def _color_refine_stage(store: object, subject: Subject) -> str | None:
    return STAGE_REFINE


def _color_refine_cost(store: object, subject: Subject, stage: str,
                       attempts: int, last_cost: int) -> int:
    return REFINE_COST


COLOR_REFINE_DESCRIPTOR = PluginDescriptor(
    name=PLUGIN,
    subject_kind="window",
    born_by=(Placement,),
    subjects_of=_color_refine_subjects,
    reads=_color_refine_reads,
    eligible=_color_refine_eligible,
    stage=_color_refine_stage,
    cost=_color_refine_cost,
    retire=_color_refine_retire,
    prepare=prepare_color_refine,
    produces=(RefineOutcome,),
    prices=PRICES,
)
