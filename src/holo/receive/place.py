"""Production E022: independent affine windows plus v1 addressing.

This module is the narrow public surface over the numerical seams in
``receive.placement``.  It retains E022-v2's native sampler, parity split,
local propagation/re-anchor behavior, eroded/audited cores, site-granular
pending state, redundant payload geometry, and loser ledger.  Format v1's
pilot/payload colocation removes the legacy pilot-tile/payload-tile atlas
conversion; it does not change E022's measured 200/40 observation windows.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable

import numpy as np
from scipy import ndimage

from ..format.descriptor import FormatSpec
from .placement.geometry import (
    AddressPatch,
    RegionContext,
    fit_window_pose,
    layout_pose_windows,
    make_address_patch,
    platen_backing,
    prepare_region,
    refresh_address_patch,
    sample_segment,
    subdivide_pose_window,
)
from .placement.model import (
    AddressResult,
    AffinePose,
    AttemptBudget,
    CandidateScore,
    HISTORICAL_MIN_SUPPORT,
    MAX_LOWER_HINTS,
    ParkedWindowFacts,
    PlacementHint,
    PlacementBudgets,
    PlacementConfig,
    PlacedPatch,
    PlacedSegment,
    PoseSegment,
    PoseWindow,
    UnresolvedPatch,
    WindowAttempt,
    promoted_continuation_hints,
)
from .placement.reference import (
    V1ReferenceField,
    rotate_points,
    rotation_affine,
)
from .placement.search import (
    ScoreMemo,
    SearchOutcome,
    WindowRefinementOutcome,
    audit_segment,
    correlate_patch,
    local_search,
    observations_for_segment,
    predict_from_anchor,
    refine_patch_pose,
)
from .scan import Raster
from .survey import PayloadSurvey, SurveyDiagnostics, region_from_record
from .types import Detail, ParkedWindowRecord, PoseRecord, SurveyRegionRecord
from .words import WordAttemptBudget, known_position_words, stage_a_patch


Progress: type = Callable[[str, tuple[Detail, ...]], None]
AddressProgress: type = Callable[
    [WindowAttempt, PlacedPatch | None, int, int, int], None
]
AddressPhaseProgress: type = Callable[
    [int, PoseWindow, str, PoseSegment | None, tuple[str, ...],
     CandidateScore | None, int | None, int, int, int],
    None,
]
AddressRegionProgress: type = Callable[
    [int, str, tuple[PlacedPatch, ...], tuple[WindowAttempt, ...],
     tuple[tuple[int, str], ...], int],
    None,
]


class FormatHypothesisRejected(ValueError):
    """The observed physical lattice is incompatible with one trial row."""


LOWER_RUNNER_UP_RESERVE = 2
LOWER_RUNNERS_PER_REGION = 2


def _lower_hint_attempt_count(n_retained: int) -> int:
    """Historical E022 portfolio size for a retained lower-hint ledger."""
    if type(n_retained) is not int or n_retained < 0:
        raise ValueError("retained lower-hint count must be nonnegative")
    return min(n_retained, MAX_LOWER_HINTS)


def _emit(
    progress: Progress | None,
    name: str,
    *details: Detail,
) -> None:
    if progress is not None:
        progress(name, tuple(details))


def _core(mask: np.ndarray, erode_cells: int) -> np.ndarray:
    if erode_cells <= 0:
        return np.asarray(mask, bool)
    eroded = ndimage.binary_erosion(mask, iterations=erode_cells)
    return eroded if eroded.any() else np.asarray(mask, bool)


def _anchor_frame(placed: PlacedPatch) -> AffinePose:
    """Return an accepted observation window's native pose."""
    segment = placed.segment
    return segment.segment.pose


def _scan_bbox(
    pose: AffinePose, shape_yx: tuple[int, int]
) -> tuple[float, float, float, float]:
    """Half-open current-raster box enclosing one local cell-centre field."""
    height, width = shape_yx
    corners = pose.points(np.asarray([
        (0.0, 0.0), (0.0, max(0, width - 1)),
        (max(0, height - 1), 0.0),
        (max(0, height - 1), max(0, width - 1)),
    ]))
    radius = 0.5 * max(
        float(np.linalg.norm(pose.matrix()[:, 0])),
        float(np.linalg.norm(pose.matrix()[:, 1])),
    )
    minimum = corners.min(axis=0) - radius
    maximum = corners.max(axis=0) + radius
    return (
        float(minimum[0]), float(minimum[1]),
        float(maximum[0]), float(maximum[1]),
    )


def _rank_lower_hints(
    hints: tuple[PlacementHint, ...], patch: AddressPatch
) -> tuple[PlacementHint, ...]:
    """Return the historical bounded 6-accepted/2-runner portfolio.

    Both classes first receive the same physical-distance ordering.  Missing
    entries in either class are backfilled from the other, up to eight total.
    A hint's native provenance box is descriptive, not a correctness filter:
    every selected centre is still revalidated against the current pixels.
    """
    target = np.asarray(patch.frame_pose.origin_yx, np.float64)
    ranked = sorted(
        enumerate(hints),
        key=lambda row: (
            float(np.linalg.norm(
                np.asarray(row[1].scan_pose_origin_yx, np.float64) - target
            )),
            row[1].page,
            row[1].rot_k,
            row[0],
        ),
    )
    accepted = [row for row in ranked if row[1].kind == "accepted"]
    runners = [row for row in ranked if row[1].kind == "runner_up"]
    n_runners = min(
        len(runners), LOWER_RUNNER_UP_RESERVE, MAX_LOWER_HINTS)
    n_accepted = min(len(accepted), MAX_LOWER_HINTS - n_runners)
    chosen = accepted[:n_accepted] + runners[:n_runners]
    remaining = MAX_LOWER_HINTS - len(chosen)
    if remaining:
        extra = accepted[n_accepted:n_accepted + remaining]
        chosen.extend(extra)
        remaining -= len(extra)
    if remaining:
        chosen.extend(runners[n_runners:n_runners + remaining])
    return tuple(row[1] for row in chosen)


def _chain_search(
    anchors: list[PlacedPatch],
    patch: AddressPatch,
    budget: AttemptBudget,
    memo: ScoreMemo,
    *,
    sample_key: int,
    config: PlacementConfig,
) -> tuple[SearchOutcome | None, int | None, int]:
    """Try accepted anchors once, in their historical insertion order."""
    aggregate = _chain_budget(budget, len(anchors), config)
    if aggregate is None:
        return None, None, 0
    hypotheses = 0
    for anchor in anchors:
        predicted = predict_from_anchor(
            _anchor_frame(anchor),
            anchor.segment.segment.window.shape_yx_cells,
            anchor.candidate.origin_yx, anchor.candidate.rot_k,
            patch.frame_pose, patch.shape_yx,
        )
        local = local_search(
            patch, anchor.candidate.page,
            anchor.candidate.rot_k, predicted, aggregate, memo,
            sample_key=sample_key, config=config,
        )
        hypotheses += local.hypotheses
        if local.accepted:
            return local, anchor.component, hypotheses
    return None, None, hypotheses


def _chain_budget(
    budget: AttemptBudget,
    n_anchors: int,
    config: PlacementConfig,
) -> AttemptBudget | None:
    """Declare the complete local-propagation domain for one window.

    ``PlacementBudgets.local`` establishes the qualified per-anchor search
    shape.  A window may try every accepted anchor, so its statistical domain
    is the exact neighborhood size times the full anchor inventory.  The
    inventory is never truncated; the derived support floor grows with it.
    """
    if isinstance(n_anchors, (bool, np.bool_)) or not isinstance(
            n_anchors, (int, np.integer)) or int(n_anchors) < 1:
        raise ValueError("chain budget needs a positive anchor count")
    per_anchor = (2 * config.neighbor_radius_cells + 1) ** 2
    if per_anchor > budget.max_hypotheses:
        return None
    domain = per_anchor * int(n_anchors)
    return replace(
        budget,
        max_hypotheses=domain,
        qualification_id=(
            f"{budget.qualification_id}/aggregate-{int(n_anchors)}-anchors"
        ),
    )


def _predict_from_hint(
    hint: PlacementHint,
    target_pose: AffinePose,
    target_shape: tuple[int, int],
) -> tuple[int, tuple[int, int]]:
    """Recover rot90 and integer origin from canonical page geometry.

    The persisted affine maps absolute page cells to this view.  Its explicit
    discrete orientation selects the exact ``np.rot90`` frame; the integer
    centre is then solved geometrically and is merely the centre of the
    ordinary bounded local gate.
    """
    affine = hint.affine()
    page_jacobian = affine[:, :2]
    page_offset = affine[:, 2]
    rot_k = hint.rot_k
    _, translation = rotation_affine(rot_k, target_shape)
    page_at_local_zero = np.linalg.solve(
        page_jacobian,
        np.asarray(target_pose.origin_yx, np.float64) - page_offset,
    )
    origin = page_at_local_zero - translation
    return rot_k, (int(round(origin[0])), int(round(origin[1])))


def placement_hint(
    hint_id: str,
    candidate: CandidateScore,
    segment: PoseSegment,
    page_origin_yx: tuple[int, int],
    *,
    kind: str,
    patch_id: int | None = None,
) -> PlacementHint:
    """Express one fitted local pose as canonical page->scan geometry."""
    rotation, translation = rotation_affine(
        candidate.rot_k, segment.window.shape_yx_cells
    )
    page_jacobian = segment.pose.matrix() @ np.linalg.inv(rotation)
    absolute_offset = translation + np.asarray(page_origin_yx, np.float64)
    scan_offset = (
        np.asarray(segment.pose.origin_yx, np.float64)
        - page_jacobian @ absolute_offset
    )
    affine = (
        float(page_jacobian[0, 0]), float(page_jacobian[0, 1]),
        float(scan_offset[0]),
        float(page_jacobian[1, 0]), float(page_jacobian[1, 1]),
        float(scan_offset[1]),
    )
    return PlacementHint(
        hint_id, candidate.page, candidate.rot_k, affine,
        _scan_bbox(segment.pose, segment.window.shape_yx_cells),
        segment.pose.origin_yx,
        kind=kind,
        search_mismatch=candidate.search_mismatch,
        validation_mismatch=candidate.validation_mismatch,
        patch_id=patch_id,
    )


def _losing_hint(
    hint_id: str,
    patch_id: int,
    patch: AddressPatch,
    candidate: CandidateScore | None,
) -> PlacementHint | None:
    if candidate is None:
        return None
    return placement_hint(
        hint_id, candidate, patch.sample.segment, candidate.origin_yx,
        kind="runner_up", patch_id=patch_id,
    )


def _retained_losing_hints(
    rows: list[tuple[int, CandidateScore, PlacementHint]],
) -> list[PlacementHint]:
    """Apply E023c's qualified two-loser ledger independently per region."""
    retained: list[PlacementHint] = []
    by_region: dict[int, list[tuple[CandidateScore, PlacementHint]]] = {}
    for region_index, candidate, hint in rows:
        by_region.setdefault(region_index, []).append((candidate, hint))
    for region_index in sorted(by_region):
        ranked = sorted(
            by_region[region_index],
            key=lambda row: (
                (float("inf") if row[0].validation_mismatch is None
                 else float(row[0].validation_mismatch)),
                float(row[0].search_mismatch),
                -int(row[0].search_support),
                row[1].hint_id,
            ),
        )
        retained.extend(
            hint for _, hint in ranked[:LOWER_RUNNERS_PER_REGION])
    return retained


@dataclass(slots=True)
class _DeferredWindow:
    """A sampled window whose cold search is deferred (v0.23 frontier).

    Cheap routes ran and failed; the window waits while chain context
    accumulates.  ``tried_anchor_ids`` prevents re-scoring an anchor whose
    prediction already failed for this patch (re-passes only pay for
    anchors accepted since the last try; the memo makes even those cheap
    when neighborhoods overlap).
    """

    window: PoseWindow
    patch: AddressPatch
    patch_id: int
    sample_key: int
    attempted_routes: list[str]
    tried_anchor_ids: set[int] = field(default_factory=set)
    word_rest_done: bool = False


def _note_route(routes: list[str], name: str) -> None:
    """Routes record entry, once, in first-entered order (across passes)."""
    if name not in routes:
        routes.append(name)


def _anchor_distance_order(
    anchors: list[PlacedPatch],
    patch: AddressPatch,
    tried_anchor_ids: set[int],
) -> list[PlacedPatch]:
    """Untried anchors, nearest pose origin first (v0.23 frontier order).

    The prediction rides each anchor's own Jacobian, so its error grows
    with distance (hygroexpansion alone is ~0.3%: ~0.5 cells per 160-cell
    stride, several cells across a region) — the nearest anchor is the
    most likely to land inside the bounded local gate.
    """
    target = np.asarray(patch.frame_pose.origin_yx, np.float64)
    rows = [row for row in anchors if row.patch_id not in tried_anchor_ids]
    rows.sort(key=lambda row: (
        float(np.linalg.norm(
            np.asarray(row.segment.segment.pose.origin_yx, np.float64)
            - target
        )),
        row.patch_id,
    ))
    return rows


def _word_route(
    patch: AddressPatch,
    spec: FormatSpec,
    word_budget: WordAttemptBudget | None,
    placement_budget: AttemptBudget,
    memo: ScoreMemo,
    sample_key: int,
    pages: tuple[int, ...],
    *,
    slots: str = "centre",
    declare: bool = True,
) -> tuple[SearchOutcome | None, int]:
    if word_budget is None:
        return None, 0
    # v0.29 lazy slot staging (supersedes the v0.26 two-stage form): the
    # cheap ladder decodes only the historical centre slot; the remaining
    # slots run behind the deferral boundary — after chain re-passes, as
    # the last cheap alternative before any cold FFT is spent.  Global
    # errors-first ordering was dropped deliberately: trial order never
    # changes admission (every candidate ahead of the first pass is tried
    # under any order, against the identical gate), a truthful window's
    # slots all imply the same placement, and the only order-sensitive
    # corner — a false decode passing both gates — is priced by the
    # union bound regardless.  The declared domain is the full multi-slot
    # ceiling either way (declared >= attempted); ``declare`` guards the
    # hypotheses counter so one window declares its word domain once.
    #
    # Within a slot stage, candidates are errors-first; the route returns
    # the first one that passes the ordinary disjoint pilot-parity gate.
    # Slot damage is priced per phase by Stage A's >=90/100 visibility
    # floor — there is deliberately no window-wide mask-fraction gate,
    # which would refuse a window with one damaged corner even when
    # another slot is pristine.  A BCH miss or a failed candidate is
    # one-way evidence only: it never vetoes the independent correlation
    # lane and it does not create a novel multi-word/ambiguity policy.
    result = stage_a_patch(patch, spec, word_budget, slots=slots)
    hypotheses = result.hypotheses if declare else 0
    if result.reason == "attempt_budget_exceeded":
        return None, hypotheses
    for seed in result.candidates:
        if seed.page not in pages:
            continue
        candidate = memo.candidate(
            sample_key, patch.evidence, patch.bits, patch.mask,
            seed.page, seed.page_origin_yx, seed.rot_k,
            placement_budget, "word",
        )
        if candidate.passes:
            return SearchOutcome(
                True, candidate, (), 1, "accepted",
                bch_errors=int(seed.errors),
                support_floor=placement_budget.min_support,
                word_tile_yx=(int(seed.tile_yx[0]), int(seed.tile_yx[1])),
            ), hypotheses
    return None, hypotheses


def _adopt_refinement(
    patch: AddressPatch,
    refined: WindowRefinementOutcome | None,
    config: PlacementConfig,
) -> AddressPatch:
    """Adopt only a resample meeting E022's historical support floor."""
    if (
        refined is None
        or int(refined.sample.mask.sum()) < HISTORICAL_MIN_SUPPORT
    ):
        return patch
    core = _core(refined.sample.mask, config.erode_cells)
    return refresh_address_patch(patch, refined.sample, core)


def _finalize_patch(
    patch_id: int,
    patch: AddressPatch,
    context: RegionContext,
    outcome: SearchOutcome,
    component: int,
    provider: V1ReferenceField,
    config: PlacementConfig,
    observed_sites: set[tuple[int, int, int]],
    *,
    scan_id: str,
    inherited_hint_id: str | None,
) -> tuple[PlacedPatch | None, str, PoseSegment]:
    candidate = outcome.best
    if candidate is None:
        return None, outcome.reason, patch.sample.segment
    refined = refine_patch_pose(
        context, patch, provider, candidate.page, candidate.origin_yx,
        candidate.rot_k, config,
    )
    patch = _adopt_refinement(patch, refined, config)
    sample = patch.sample
    origin = candidate.origin_yx
    audited, refused, _, _ = audit_segment(
        sample, patch.mask, provider, candidate.page, origin,
        candidate.rot_k, config, min_support=outcome.support_floor,
    )
    if refused:
        return None, "straddle_audit_refused", sample.segment

    page_shape = provider.spec.layout.cells_yx
    local = np.argwhere(audited)
    rotated = rotate_points(local, sample.mask.shape, candidate.rot_k)
    absolute = rotated + np.asarray(origin, np.int64)
    inside = (
        (absolute[:, 0] >= 0) & (absolute[:, 0] < page_shape[0])
        & (absolute[:, 1] >= 0) & (absolute[:, 1] < page_shape[1])
    )
    union = absolute[inside].astype(np.int32, copy=False)
    placed_segment = PlacedSegment(
        sample.segment, origin, candidate.rot_k, local,
    )
    reference = provider.page(candidate.page)
    site_cells = (
        union[reference.sites[union[:, 0], union[:, 1]]]
        if union.size else np.zeros((0, 2), np.int32)
    )
    all_sites = {
        (candidate.page, int(cell[0]), int(cell[1]))
        for cell in site_cells
    }
    new_sites = all_sites - observed_sites
    redundant = not new_sites
    observed_sites.update(all_sites)
    observations = (() if redundant else observations_for_segment(
        sample, audited, provider, candidate.page, origin,
        candidate.rot_k, scan_id=scan_id, patch_id=patch_id,
    ))
    return PlacedPatch(
        patch_id, patch.region_index, int(component),
        candidate.route, candidate, outcome.runner_ups,
        placed_segment, tuple(observations), redundant, union,
        inherited_hint_id,
    ), "accepted", sample.segment


@dataclass(slots=True)
class _MopupDrive:
    """v0.33 M-level inputs: parked rows per region + the ordinal watermark.

    ``label_poses_by_region`` (D7) carries the base pass's accepted
    PoseRecords for regions that parked work: they reconstruct as
    calibration-label windows only.
    """

    parked_by_region: dict[int, list[ParkedWindowRecord]]
    start_patch_ordinal: int
    label_poses_by_region: dict[int, list[PoseRecord]] = field(
        default_factory=dict)


def _label_patch(
    row: PoseRecord,
    region_index: int,
    context: RegionContext,
    memo: ScoreMemo,
    provider: V1ReferenceField,
    budget: AttemptBudget,
    config: PlacementConfig,
    sample_key: int,
) -> PlacedPatch | None:
    """Reconstruct one base-accepted window as a calibration label (D7).

    The persisted lane-frame pose re-samples bit-exactly; the candidate
    re-scores identically on identical pixels; the audit re-derives the
    exact page/audited cell sets.  Labels carry no observations, own no
    cells, and never enter the firewall word pool — their sole consumer
    is the region calibration fit.
    """
    window = PoseWindow(
        int(row.window_id), region_index,
        tuple(int(value) for value in row.window_origin_yx_px),
        tuple(int(value) for value in row.window_shape_yx_cells),
        int(row.window_depth), 0)
    pose = AffinePose(
        tuple(float(value) for value in row.lane_pose_origin_yx),
        ((float(row.lane_pose_jacobian[0]),
          float(row.lane_pose_jacobian[1])),
         (float(row.lane_pose_jacobian[2]),
          float(row.lane_pose_jacobian[3]))),
        tuple(float(value) for value in row.lane_pose_phase_yx),
        float(row.lane_pose_pitch_px), float(row.lane_pose_angle_deg))
    segment = PoseSegment(
        window, pose, int(row.segment_support_cells),
        float(row.segment_phase_contrast),
        tuple(float(value) for value in row.segment_pitch_yx_px),
        float(row.segment_orthogonality_error_deg))
    sample = sample_segment(context, segment)
    if sample is None or int(sample.mask.sum()) < HISTORICAL_MIN_SUPPORT:
        return None
    patch = make_address_patch(sample, _core(sample.mask, config.erode_cells))
    origin = tuple(int(value) for value in row.cell_origin_yx)
    candidate = memo.candidate(
        sample_key, patch.evidence, patch.bits, patch.mask,
        int(row.page), origin, int(row.rot90), budget, "label",
    )
    if not candidate.passes:
        return None
    audited, refused, _, _ = audit_segment(
        sample, patch.mask, provider, int(row.page), origin,
        int(row.rot90), config, min_support=HISTORICAL_MIN_SUPPORT,
    )
    if refused:
        return None
    page_shape = provider.spec.layout.cells_yx
    local = np.argwhere(audited)
    rotated = rotate_points(local, sample.mask.shape, int(row.rot90))
    absolute = rotated + np.asarray(origin, np.int64)
    inside = (
        (absolute[:, 0] >= 0) & (absolute[:, 0] < page_shape[0])
        & (absolute[:, 1] >= 0) & (absolute[:, 1] < page_shape[1])
    )
    union = absolute[inside].astype(np.int32, copy=False)
    placed_segment = PlacedSegment(
        sample.segment, origin, int(row.rot90), local,
    )
    return PlacedPatch(
        int(row.patch_id), region_index, -1, "label", candidate, (),
        placed_segment, (), True, union, None,
    )


def mopup_survey(
    parked: tuple[ParkedWindowRecord, ...],
    regions: tuple[SurveyRegionRecord, ...],
) -> PayloadSurvey:
    """Re-derive the M-level's synthetic survey from durable records.

    ``parked`` are the evidence context's durable parked rows (non-empty);
    ``regions`` the base lane's durable survey-region rows.  Shared by the
    placement engine and the address diagnostics adapter so M-level
    window-progress snapshots carry exactly the geometry the mop-up drive
    places against (pitch from the parked rows, regions rebuilt from the
    base lane's records).
    """
    ordered = sorted(regions, key=lambda record: record.region_id)
    by_index: dict[int, SurveyRegionRecord] = {}
    for record in ordered:
        tail = record.region_id.rsplit("region-", 1)
        by_index[int(tail[1])] = record
    if not by_index or max(
            int(row.region_index) for row in parked) > max(by_index):
        raise ValueError("parked window references an unknown region index")
    rebuilt = tuple(
        region_from_record(by_index[index])
        for index in range(max(by_index) + 1))
    return PayloadSurvey(
        regions=rebuilt,
        c_dots=None,
        cell_pitch_px=float(parked[0].cell_pitch_px),
        pitch_votes=(),
        diagnostics=SurveyDiagnostics(
            threshold=None, survey_step_px=1, survey_scale_px=1.0,
            component_count=0, refinement_tiles=0,
            refinement_scored_cells=0, refinement_grid_cells=0),
    )


def place_mopup(
    raster: Raster,
    spec: FormatSpec,
    *,
    pages: tuple[int, ...],
    budgets: PlacementBudgets,
    word_budget: WordAttemptBudget | None,
    parked: tuple[ParkedWindowRecord, ...],
    regions: tuple[SurveyRegionRecord, ...],
    hints: tuple[PlacementHint, ...] = (),
    label_poses: tuple[PoseRecord, ...] = (),
    config: PlacementConfig = PlacementConfig(),
    scan_id: str = "",
    start_patch_ordinal: int = 0,
    progress: Progress | None = None,
    address_progress: AddressProgress | None = None,
    address_phase_progress: AddressPhaseProgress | None = None,
    address_region_progress: AddressRegionProgress | None = None,
    address_region_progress_enabled: Callable[[], bool] | None = None,
) -> AddressResult:
    """v0.33 M-level drive: consume parked windows at the base aperture.

    ``parked`` are durable :class:`ParkedWindowRecord` rows; ``regions``
    the base lane's durable :class:`SurveyRegionRecord` rows.  A synthetic
    ``PayloadSurvey`` reconstructed from the records (:func:`mopup_survey`)
    feeds the ordinary ``place_survey`` engine in mop-up mode: no fresh
    layout, the parked inventory as the deferred set, a hint pre-pass over
    the capture-wide pose/loser inventory, then the ordinary rest/cold
    ladder under the §3.5 price rule, chain re-pass, subdivision, and
    per-level firewall.
    """
    if not parked:
        return AddressResult((), (), (), (), 0)
    by_region: dict[int, list[ParkedWindowRecord]] = {}
    for row in parked:
        by_region.setdefault(int(row.region_index), []).append(row)
    synthetic = mopup_survey(parked, regions)
    region_id_to_index = {
        record.region_id: int(record.region_id.rsplit("region-", 1)[1])
        for record in regions}
    labels_by_region: dict[int, list[PoseRecord]] = {}
    for row in label_poses:
        index = region_id_to_index.get(row.region_id)
        if index is None or index not in by_region:
            # Labels only serve regions with parked work.
            continue
        labels_by_region.setdefault(index, []).append(row)
    return place_survey(
        raster, synthetic, spec,
        pages=pages, budgets=budgets, word_budget=word_budget,
        lower_hints=hints, config=config, scan_id=scan_id,
        progress=progress, address_progress=address_progress,
        address_phase_progress=address_phase_progress,
        address_region_progress=address_region_progress,
        address_region_progress_enabled=address_region_progress_enabled,
        _mopup=_MopupDrive(
            by_region, int(start_patch_ordinal), labels_by_region),
    )


def _committed_patch(
    row: PoseRecord,
    region_index: int,
    context: RegionContext,
    provider: V1ReferenceField,
    config: PlacementConfig,
) -> PlacedPatch | None:
    """Re-derive one committed base pose as a payload-capable placement.

    v0.42 R-level twin of :func:`_label_patch`: the persisted lane-frame
    pose re-samples bit-exactly on the re-derived base aperture and the
    audit re-derives the exact page/audited cell sets.  Unlike a label,
    the result keeps the durable placement outcome (``redundant`` flag)
    and synthesizes its :class:`CandidateScore` from the durable verdict
    (``passes=True``, ``validation_mismatch = 1 - quality``) — acceptance
    already happened at the base barrier, so no route re-scoring runs.
    Labels-only fields stay empty: no observations, no runner-ups, no
    component (committed poses never re-enter the firewall word pool).
    """
    window = PoseWindow(
        int(row.window_id), region_index,
        tuple(int(value) for value in row.window_origin_yx_px),
        tuple(int(value) for value in row.window_shape_yx_cells),
        int(row.window_depth), 0)
    pose = AffinePose(
        tuple(float(value) for value in row.lane_pose_origin_yx),
        ((float(row.lane_pose_jacobian[0]),
          float(row.lane_pose_jacobian[1])),
         (float(row.lane_pose_jacobian[2]),
          float(row.lane_pose_jacobian[3]))),
        tuple(float(value) for value in row.lane_pose_phase_yx),
        float(row.lane_pose_pitch_px), float(row.lane_pose_angle_deg))
    segment = PoseSegment(
        window, pose, int(row.segment_support_cells),
        float(row.segment_phase_contrast),
        tuple(float(value) for value in row.segment_pitch_yx_px),
        float(row.segment_orthogonality_error_deg))
    sample = sample_segment(context, segment)
    if sample is None or int(sample.mask.sum()) < HISTORICAL_MIN_SUPPORT:
        return None
    patch = make_address_patch(sample, _core(sample.mask, config.erode_cells))
    origin = tuple(int(value) for value in row.cell_origin_yx)
    audited, refused, _, _ = audit_segment(
        sample, patch.mask, provider, int(row.page), origin,
        int(row.rot90), config, min_support=HISTORICAL_MIN_SUPPORT,
    )
    if refused:
        return None
    page_shape = provider.spec.layout.cells_yx
    local = np.argwhere(audited)
    rotated = rotate_points(local, sample.mask.shape, int(row.rot90))
    absolute = rotated + np.asarray(origin, np.int64)
    inside = (
        (absolute[:, 0] >= 0) & (absolute[:, 0] < page_shape[0])
        & (absolute[:, 1] >= 0) & (absolute[:, 1] < page_shape[1])
    )
    union = absolute[inside].astype(np.int32, copy=False)
    if not union.size:
        return None
    placed_segment = PlacedSegment(
        sample.segment, origin, int(row.rot90), local,
    )
    support = int(local.shape[0])
    quality = min(1.0, max(0.0, float(row.quality)))
    candidate = CandidateScore(
        int(row.page), origin, int(row.rot90) % 4,
        0.0, 1.0 - quality, 0, 0, support, support, 0.0, True,
        "committed",
    )
    return PlacedPatch(
        int(row.patch_id), region_index, -1, "committed", candidate, (),
        placed_segment, (), str(row.placement_outcome) == "redundant",
        union, None,
    )


def place_committed(
    raster: Raster,
    spec: FormatSpec,
    *,
    poses: tuple[PoseRecord, ...],
    regions: tuple[SurveyRegionRecord, ...],
    config: PlacementConfig = PlacementConfig(),
) -> AddressResult:
    """v0.42 R-level inventory: the base lane's committed poses, re-derived.

    ``poses`` are one base ladder lane's durable :class:`PoseRecord` rows
    (accepted AND redundant placement outcomes — both trained the pooled
    fit; quarantined placements are excluded upstream, mirroring the base
    pass's payload pool); ``regions`` its durable
    :class:`SurveyRegionRecord` rows.  Deterministic and search-free:
    every committed
    pose re-samples on the re-derived base aperture and re-audits its
    support — no routes, no words, no firewall, no parking.  A window
    whose support or audit no longer re-derives is skipped: it simply is
    not a refinement candidate (its base-lane evidence stands).  The
    region aperture pitch is the median committed pose pitch — one pitch
    for the whole capture, mirroring the base survey's single global
    pitch estimate.
    """
    rows = tuple(poses)
    if not rows:
        return AddressResult((), (), (), (), 0)
    ordered = sorted(regions, key=lambda record: record.region_id)
    by_index: dict[int, SurveyRegionRecord] = {}
    for record in ordered:
        tail = record.region_id.rsplit("region-", 1)
        by_index[int(tail[1])] = record
    region_index_by_id = {
        record.region_id: index for index, record in by_index.items()}
    poses_by_region: dict[int, list[PoseRecord]] = {}
    for row in rows:
        index = region_index_by_id.get(row.region_id)
        if index is None:
            raise ValueError("committed pose references an unknown region")
        poses_by_region.setdefault(index, []).append(row)
    pitch = float(np.median(
        [float(row.lane_pose_pitch_px) for row in rows]))
    provider = V1ReferenceField(spec)
    backing = platen_backing(raster)
    placements: list[PlacedPatch] = []
    region_states: list[tuple[int, str]] = []
    for region_index in sorted(poses_by_region):
        context = prepare_region(
            raster, region_from_record(by_index[region_index]),
            region_index, pitch, config=config, backing=backing,
        )
        if context is None:
            region_states.append((region_index, "pose_refused"))
            continue
        rebuilt = 0
        for row in sorted(poses_by_region[region_index],
                          key=lambda record: int(record.patch_id)):
            committed = _committed_patch(
                row, region_index, context, provider, config)
            if committed is not None:
                placements.append(committed)
                rebuilt += 1
        region_states.append(
            (region_index, "committed" if rebuilt else "pose_refused"))
    return AddressResult(
        tuple(placements), (), (), tuple(region_states), 0)


def place_survey(
    raster: Raster,
    survey: PayloadSurvey,
    spec: FormatSpec,
    *,
    pages: tuple[int, ...],
    budgets: PlacementBudgets,
    word_budget: WordAttemptBudget | None,
    lower_hints: tuple[PlacementHint, ...] = (),
    config: PlacementConfig = PlacementConfig(),
    scan_id: str = "",
    progress: Progress | None = None,
    address_progress: AddressProgress | None = None,
    address_phase_progress: AddressPhaseProgress | None = None,
    address_region_progress: AddressRegionProgress | None = None,
    address_region_progress_enabled: Callable[[], bool] | None = None,
    park: bool = False,
    _mopup: "_MopupDrive | None" = None,
) -> AddressResult:
    """Run E022 over one E021 survey and one complete format hypothesis.

    ``park=True`` is the v0.33 phase-1 mode: when no cheap route (pose,
    chain, lower hint, centre-slot word) makes progress anywhere in a
    region, the fall-through windows PARK as durable facts for the
    capture's mop-up level instead of paying the remaining-slot sweep or
    a cold search here.  Admission bars are untouched — parking only
    moves when the costly routes run.

    ``word_budget`` is an explicit policy choice: a concrete envelope enables
    default Lane W; ``None`` deliberately disables it.  Lower-scale geometry
    is likewise disabled by default; hints require ``budgets.lower`` and are
    only bounded search centres for fresh pixels under the ordinary gate.
    There is no hidden production Stage-A probe/default budget.
    """
    if any(
        isinstance(page, (bool, np.bool_))
        or not isinstance(page, (int, np.integer))
        for page in pages
    ):
        raise TypeError("page hypotheses must be integers")
    pages = tuple(dict.fromkeys(int(page) for page in pages))
    if not pages:
        raise ValueError("E022 needs at least one page hypothesis")
    if any(page < 0 or page >= spec.max_pages for page in pages):
        raise ValueError("page hypothesis outside the format counter range")
    if lower_hints and budgets.lower is None:
        raise ValueError("lower-scale hints require an explicit route budget")
    if any(not isinstance(hint, PlacementHint) for hint in lower_hints):
        raise TypeError("lower_hints must contain PlacementHint records")
    if survey.c_dots is not None and survey.c_dots != spec.cell_dots:
        raise FormatHypothesisRejected(
            f"survey c{survey.c_dots} does not match {spec.spec_id}"
        )
    pitch = survey.cell_pitch_px
    if pitch is None:
        pitch = raster.dpi * spec.cell_dots / 600.0
    if not survey.regions:
        return AddressResult((), (), (), (), 0)

    provider = V1ReferenceField(spec)
    memo = ScoreMemo(provider)
    backing = platen_backing(raster)
    placements: list[PlacedPatch] = []
    unresolved: list[UnresolvedPatch] = []
    parked_windows: list[ParkedWindowFacts] = []
    label_placements: list[PlacedPatch] = []
    region_states: list[tuple[int, str]] = []
    observed_sites: set[tuple[int, int, int]] = set()
    hypotheses_total = 0
    accepted_hints: list[PlacementHint] = []
    losing_hints: list[tuple[int, CandidateScore, PlacementHint]] = []
    attempts: list[WindowAttempt] = []
    accepted_hint_keys: set[
        tuple[int, int, int, tuple[int, int], int]
    ] = set()
    # v0.33: an M-level continues its evidence lane's patch-ordinal
    # namespace — fresh work (subdivision children) mints strictly above
    # the durable watermark; parked entries keep their base-pass ordinals.
    patch_id = 0 if _mopup is None else _mopup.start_patch_ordinal
    next_sample_key = 0

    region_order = sorted(
        range(len(survey.regions)),
        key=lambda index: -survey.regions[index].area_mm2,
    )
    for region_index in region_order:
        if _mopup is not None and region_index not in _mopup.parked_by_region:
            continue
        region_placement_start = len(placements)
        region_attempt_start = len(attempts)
        _emit(
            progress, "address.region_open",
            Detail("address.region", region_index),
        )
        context = prepare_region(
            raster, survey.regions[region_index], region_index, float(pitch),
            config=config, backing=backing,
        )
        if context is None:
            region_states.append((region_index, "pose_refused"))
            if (address_region_progress is None
                    or (address_region_progress_enabled is not None
                        and not address_region_progress_enabled())):
                _emit(
                    progress, "address.region_complete",
                    Detail("address.region", region_index),
                    Detail("address.state", "pose_refused"),
                    Detail("address.region_placements",
                           len(placements) - region_placement_start),
                    Detail("address.hypotheses", hypotheses_total),
                )
            else:
                address_region_progress(
                    region_index, "pose_refused",
                    tuple(placements[region_placement_start:]),
                    tuple(attempts[region_attempt_start:]),
                    ((region_index, "pose_refused"),), hypotheses_total)
            continue
        region_accepted = 0
        region_placed = 0
        region_parked = 0
        next_component = 0
        anchors: list[PlacedPatch] = []
        if _mopup is not None:
            pending = []
            rows = _mopup.parked_by_region[region_index]
            seed = next(
                (row.lattice_f for row in rows
                 if row.lattice_f is not None), None)
            if seed is not None:
                # The base pass's order-dependent reciprocal seed: children
                # subdivided here refit under the same prior the base pass
                # would have used.
                context.lattice_f = np.asarray(
                    seed, np.float64).reshape(2, 2)
        else:
            pending = list(layout_pose_windows(context, config=config))
        deferred: list[_DeferredWindow] = []
        next_window_id = 1 + max(
            (window.window_id for window in pending), default=-1
        )
        windows_processed = 0

        def announce_planned(rows: list[PoseWindow]) -> None:
            """v0.27 pane-A work-in-flight overlay: geometry-only facts."""
            for row in rows:
                _emit(
                    progress, "address.window_planned",
                    Detail("address.region", region_index),
                    Detail("address.window", row.window_id),
                    Detail("address.box_y",
                           int(context.y0 + row.origin_yx_px[0])),
                    Detail("address.box_x",
                           int(context.x0 + row.origin_yx_px[1])),
                    Detail("address.box_h",
                           int(round(row.shape_yx_cells[0] * pitch))),
                    Detail("address.box_w",
                           int(round(row.shape_yx_cells[1] * pitch))),
                )

        announce_planned(pending)

        def windows_total() -> int:
            return windows_processed + len(pending) + len(deferred)

        def retain_attempt(
            attempt: WindowAttempt,
            placed: PlacedPatch | None = None,
        ) -> None:
            attempts.append(attempt)
            _emit(
                progress, "address.window_resolved",
                Detail("address.region", region_index),
                Detail("address.window", attempt.window.window_id),
                Detail("address.outcome", attempt.outcome),
            )
            if address_progress is not None:
                address_progress(
                    attempt, placed, windows_processed, windows_total(),
                    len(anchors))

        def emit_phase(
            window: PoseWindow,
            phase: str,
            segment: PoseSegment | None = None,
            attempted_routes: tuple[str, ...] = (),
            candidate: CandidateScore | None = None,
            patch: int | None = None,
        ) -> None:
            if address_phase_progress is not None:
                address_phase_progress(
                    region_index, window, phase, segment, attempted_routes,
                    candidate, patch, windows_processed, windows_total(),
                    len(anchors))

        def subdivide_into_pending(window: PoseWindow) -> None:
            nonlocal next_window_id
            children = subdivide_pose_window(
                window, context, config=config,
                first_window_id=next_window_id,
            )
            next_window_id += len(children)
            pending.extend(children)
            announce_planned(list(children))

        def pick_pending() -> PoseWindow:
            """v0.23 wave-front order: expand from accepted placements.

            With no anchors yet, the layout's richest-support-first order
            stands (it front-loads the most likely word-decode seeders).
            Once anchors exist, the window whose centre is nearest an
            accepted pose goes next, so chain predictions stay short-range
            where the anchor's Jacobian is still a good local warp model.
            """
            if not anchors:
                best = min(
                    pending,
                    key=lambda row: (-row.support_estimate, row.window_id),
                )
            else:
                origins = [
                    np.asarray(
                        row.segment.segment.pose.origin_yx, np.float64)
                    - np.asarray((context.y0, context.x0), np.float64)
                    for row in anchors
                ]

                def frontier_key(row: PoseWindow):
                    centre = (
                        np.asarray(row.origin_yx_px, np.float64)
                        + 0.5 * np.asarray(row.shape_yx_cells, np.float64)
                        * pitch
                    )
                    distance = min(
                        float(np.linalg.norm(centre - origin))
                        for origin in origins
                    )
                    return (distance, -row.support_estimate, row.window_id)

                best = min(pending, key=frontier_key)
            pending.remove(best)
            return best

        def refuse_unplaced(
            window: PoseWindow,
            patch: AddressPatch,
            current_id: int,
            outcome: SearchOutcome,
            attempted_routes: tuple[str, ...],
        ) -> None:
            losing = _losing_hint(
                f"{scan_id}|runner|{current_id}", current_id,
                patch, outcome.best,
            )
            if losing is not None:
                losing_hints.append((region_index, outcome.best, losing))
            unresolved.append(UnresolvedPatch(
                current_id, region_index, outcome.reason, outcome.best,
            ))
            retain_attempt(WindowAttempt(
                region_index, window, "unresolved",
                attempted_routes, current_id,
                patch.sample.segment, outcome.best, outcome.reason,
                predicted_origin_yx=outcome.predicted_origin_yx,
                predicted_residual_cells=outcome.predicted_residual_cells,
                bch_errors=outcome.bch_errors,
                rival=outcome.rival,
            ))
            subdivide_into_pending(window)
            _emit(
                progress, "address.patch_refused",
                Detail("address.region", region_index),
                Detail("address.patch", current_id),
                Detail("address.reason", outcome.reason),
            )

        def finalize_accept(
            window: PoseWindow,
            patch: AddressPatch,
            current_id: int,
            outcome: SearchOutcome,
            inherited_component: int | None,
            used_lower_hint: PlacementHint | None,
            attempted_routes: tuple[str, ...],
        ) -> bool:
            nonlocal next_component, region_placed, region_accepted
            component = inherited_component
            opened_component = component is None
            if component is None:
                component = next_component
            placed, reason, final_segment = _finalize_patch(
                current_id, patch, context, outcome, component,
                provider, config, observed_sites, scan_id=scan_id,
                inherited_hint_id=(
                    None if used_lower_hint is None
                    else used_lower_hint.hint_id
                ),
            )
            emit_phase(
                window, "refine_complete", final_segment,
                attempted_routes, outcome.best, current_id)
            if placed is None:
                unresolved.append(UnresolvedPatch(
                    current_id, region_index, reason, outcome.best,
                ))
                retain_attempt(WindowAttempt(
                    region_index, window, "audit_refused",
                    attempted_routes, current_id,
                    final_segment, outcome.best, reason,
                    predicted_origin_yx=outcome.predicted_origin_yx,
                    predicted_residual_cells=(
                        outcome.predicted_residual_cells),
                    bch_errors=outcome.bch_errors,
                    rival=outcome.rival,
                ))
                subdivide_into_pending(window)
                _emit(
                    progress, "address.patch_refused",
                    Detail("address.region", region_index),
                    Detail("address.patch", current_id),
                    Detail("address.reason", reason),
                )
                return False
            if opened_component and placed.redundant:
                placed = replace(placed, component=-1)
            elif opened_component:
                next_component += 1
            placements.append(placed)
            accepted_attempt = WindowAttempt(
                region_index, window,
                "redundant" if placed.redundant else "accepted",
                attempted_routes, current_id,
                placed.segment.segment, placed.candidate,
                component=placed.component,
                predicted_origin_yx=outcome.predicted_origin_yx,
                predicted_residual_cells=outcome.predicted_residual_cells,
                bch_errors=outcome.bch_errors,
                rival=outcome.rival,
            )
            retain_attempt(accepted_attempt, placed)
            segment = placed.segment
            key = (
                placed.region_index, segment.segment.window.window_id,
                placed.candidate.page, segment.page_origin_yx, segment.rot_k,
            )
            if key not in accepted_hint_keys:
                accepted_hint_keys.add(key)
                accepted_hints.append(placement_hint(
                    f"{scan_id}|accepted|{current_id}",
                    placed.candidate, segment.segment,
                    segment.page_origin_yx, kind="accepted",
                    patch_id=current_id,
                ))
            region_placed += 1
            if not placed.redundant:
                region_accepted += 1
                anchors.append(placed)
            # v0.43 pane-C authority tri-state: a word-route acceptance
            # names the tile whose BCH word the seeder decoded.  Two int
            # details on the existing event, observer-gated like its
            # neighbors; absent on chain/lower/correlation routes.
            solve_details = (
                () if outcome.word_tile_yx is None else (
                    Detail("address.word_tile_y",
                           int(outcome.word_tile_yx[0])),
                    Detail("address.word_tile_x",
                           int(outcome.word_tile_yx[1])),
                ))
            _emit(
                progress, "address.patch_accepted",
                Detail("address.region", region_index),
                Detail("address.patch", current_id),
                Detail("address.page", placed.candidate.page),
                Detail("address.route", placed.route),
                Detail("address.redundant", placed.redundant),
                *solve_details,
            )
            return True

        def attempt_cheap(window: PoseWindow) -> None:
            """Pose, sample, and the chain/lower/word ladder; defer cold."""
            nonlocal patch_id, next_sample_key, hypotheses_total
            attempted_routes: list[str] = []
            emit_phase(window, "open")
            segment = fit_window_pose(context, window, config=config)
            if segment is None:
                subdivide_into_pending(window)
                _emit(
                    progress, "address.pose_refused",
                    Detail("address.region", region_index),
                    Detail("address.window", window.window_id),
                    Detail("address.subdivision_depth", window.depth),
                )
                emit_phase(window, "pose_refused")
                retain_attempt(WindowAttempt(
                    region_index, window, "pose_refused", (),
                    reason="pose_refused",
                ))
                return
            emit_phase(window, "pose_fitted", segment)
            sample = sample_segment(context, segment)
            if (sample is None
                    or int(sample.mask.sum()) < HISTORICAL_MIN_SUPPORT):
                _emit(
                    progress, "address.insufficient_support",
                    Detail("address.region", region_index),
                    Detail("address.window", window.window_id),
                )
                emit_phase(window, "support_refused", segment)
                retain_attempt(WindowAttempt(
                    region_index, window, "insufficient_support", (),
                    segment=segment, reason="insufficient_support",
                ))
                return
            patch = make_address_patch(
                sample, _core(sample.mask, config.erode_cells)
            )
            current_id = patch_id
            patch_id += 1
            sample_key = next_sample_key
            next_sample_key += 1
            _emit(
                progress, "address.patch_open",
                Detail("address.region", region_index),
                Detail("address.patch", current_id),
                Detail("address.support_cells", int(patch.mask.sum())),
            )
            outcome: SearchOutcome | None = None
            inherited_component: int | None = None
            used_lower_hint: PlacementHint | None = None
            # Local propagation is the first/economic route.  Every neighbor
            # retains its own fitted pose, fresh pixels, and held-out gate.
            tried_anchor_ids: set[int] = set()
            if anchors:
                _note_route(attempted_routes, "chain")
                ordered = _anchor_distance_order(
                    anchors, patch, tried_anchor_ids)
                outcome, inherited_component, chain_hypotheses = (
                    _chain_search(
                        ordered, patch, budgets.local, memo,
                        sample_key=sample_key, config=config,
                    ))
                hypotheses_total += chain_hypotheses
                tried_anchor_ids.update(row.patch_id for row in ordered)
                emit_phase(
                    window, "route.chain", segment,
                    tuple(attempted_routes),
                    None if outcome is None else outcome.best, current_id)
            if outcome is None and lower_hints:
                _note_route(attempted_routes, "lower_hint")
                assert budgets.lower is not None
                ranked_hints = tuple(
                    hint for hint in _rank_lower_hints(lower_hints, patch)
                    if hint.page in pages
                )
                per_hint = (2 * config.neighbor_radius_cells + 1) ** 2
                lower_domain = per_hint * len(ranked_hints)
                if lower_domain <= budgets.lower.max_hypotheses:
                    for hint in ranked_hints:
                        rot_k, predicted = _predict_from_hint(
                            hint, patch.frame_pose, patch.shape_yx
                        )
                        local = local_search(
                            patch, hint.page, rot_k, predicted,
                            budgets.lower, memo, sample_key=sample_key,
                            config=config, route="lower_hint",
                        )
                        hypotheses_total += local.hypotheses
                        if local.accepted:
                            outcome, used_lower_hint = local, hint
                            break
                elif ranked_hints:
                    _emit(
                        progress, "address.lower_hint_budget_refused",
                        Detail("address.region", region_index),
                        Detail("address.patch", current_id),
                        Detail("address.hypotheses", lower_domain),
                    )
                emit_phase(
                    window, "route.lower_hint", segment,
                    tuple(attempted_routes),
                    None if outcome is None else outcome.best, current_id)
            if outcome is None:
                if word_budget is not None:
                    _note_route(attempted_routes, "word")
                outcome, word_hypotheses = _word_route(
                    patch, spec, word_budget, budgets.local,
                    memo, sample_key, pages,
                )
                hypotheses_total += word_hypotheses
                if word_budget is not None:
                    emit_phase(
                        window, "route.word", segment,
                        tuple(attempted_routes),
                        None if outcome is None else outcome.best, current_id)
            if outcome is None:
                # v0.23 deferred cold: park the sampled window; later cheap
                # acceptances may chain it before any cold work is spent.
                deferred.append(_DeferredWindow(
                    window, patch, current_id, sample_key,
                    attempted_routes, tried_anchor_ids,
                ))
                _emit(
                    progress, "address.cold_deferred",
                    Detail("address.region", region_index),
                    Detail("address.patch", current_id),
                    Detail("address.window", window.window_id),
                    Detail("address.deferred", len(deferred)),
                )
                return
            finalize_accept(
                window, patch, current_id, outcome, inherited_component,
                used_lower_hint, tuple(attempted_routes))

        def chain_repass() -> bool:
            """Retry chain over deferred windows with anchors added since.

            Already-tried anchors are excluded per entry, so a re-pass only
            pays 49 scores per NEW anchor; overlapping neighborhoods hit
            the memo.  Returns True when any entry left the deferred set.
            """
            nonlocal hypotheses_total
            for entry in list(deferred):
                ordered = _anchor_distance_order(
                    anchors, entry.patch, entry.tried_anchor_ids)
                if not ordered:
                    continue
                _note_route(entry.attempted_routes, "chain")
                outcome, inherited_component, chain_hypotheses = (
                    _chain_search(
                        ordered, entry.patch, budgets.local, memo,
                        sample_key=entry.sample_key, config=config,
                    ))
                hypotheses_total += chain_hypotheses
                entry.tried_anchor_ids.update(
                    row.patch_id for row in ordered)
                emit_phase(
                    entry.window, "route.chain", entry.patch.sample.segment,
                    tuple(entry.attempted_routes),
                    None if outcome is None else outcome.best,
                    entry.patch_id)
                if outcome is None:
                    continue
                deferred.remove(entry)
                finalize_accept(
                    entry.window, entry.patch, entry.patch_id, outcome,
                    inherited_component, None,
                    tuple(entry.attempted_routes))
                return True
            return False

        def try_word_rest(entry: _DeferredWindow) -> bool:
            """v0.29: decode the remaining slots — the last cheap route.

            Runs only for a window that survived every chain re-pass and is
            about to spend a cold sweep; its word domain was declared once
            by the centre-stage probe, so this adds no counted hypotheses.
            """
            nonlocal hypotheses_total
            if word_budget is None:
                return False
            # v0.27 overlay: the last cheap route is its own visible state —
            # a parked window decoding its remaining slots is working, not
            # waiting.
            _emit(
                progress, "address.word_rest_open",
                Detail("address.region", region_index),
                Detail("address.patch", entry.patch_id),
                Detail("address.window", entry.window.window_id),
            )
            outcome, extra = _word_route(
                entry.patch, spec, word_budget, budgets.local,
                memo, entry.sample_key, pages,
                slots="rest", declare=False,
            )
            hypotheses_total += extra
            if outcome is None:
                _emit(
                    progress, "address.word_rest_refused",
                    Detail("address.region", region_index),
                    Detail("address.patch", entry.patch_id),
                    Detail("address.window", entry.window.window_id),
                )
                return False
            emit_phase(
                entry.window, "route.word", entry.patch.sample.segment,
                tuple(entry.attempted_routes), outcome.best, entry.patch_id)
            finalize_accept(
                entry.window, entry.patch, entry.patch_id, outcome,
                None, None, tuple(entry.attempted_routes))
            return True

        def run_cold(entry: _DeferredWindow,
                     rest_fallback: bool = False) -> None:
            nonlocal hypotheses_total
            _note_route(entry.attempted_routes, "correlation")
            # Label the one genuinely event-silent span (~seconds/page of
            # declared domain) before entering it.
            _emit(
                progress, "address.cold_open",
                Detail("address.region", region_index),
                Detail("address.patch", entry.patch_id),
                Detail("address.window", entry.window.window_id),
                Detail("address.pages", len(pages)),
            )
            # v0.33 D14c heartbeat: a running cold emits at most 64
            # count-bounded ``address.cold_progress`` events per sweep
            # (never milestones, never snapshot).  A headless run
            # (``progress is None``) skips callback construction entirely,
            # so the numerical path sees ``None`` and does zero extra work.
            page_progress = None
            if progress is not None:
                def page_progress(page_ordinal: int, pages_total: int,
                                  ) -> None:
                    _emit(
                        progress, "address.cold_progress",
                        Detail("address.pages", pages_total),
                        Detail("address.page_ordinal", page_ordinal),
                    )
            outcome = correlate_patch(
                entry.patch, provider, pages, budgets.cold, memo,
                sample_key=entry.sample_key, config=config,
                page_progress=page_progress,
            )
            hypotheses_total += outcome.hypotheses
            emit_phase(
                entry.window, "route.correlation",
                entry.patch.sample.segment,
                tuple(entry.attempted_routes), outcome.best, entry.patch_id)
            if not outcome.accepted or outcome.best is None:
                if rest_fallback and not entry.word_rest_done:
                    # PLACEMENT-IMPROVEMENTS §3.5 small-domain inversion:
                    # the cold ran first; the remaining-slot sweep still
                    # runs before the window gives up.
                    entry.word_rest_done = True
                    if try_word_rest(entry):
                        return
                refuse_unplaced(
                    entry.window, entry.patch, entry.patch_id, outcome,
                    tuple(entry.attempted_routes))
                return
            finalize_accept(
                entry.window, entry.patch, entry.patch_id, outcome,
                None, None, tuple(entry.attempted_routes))

        if _mopup is not None:
            # v0.33 M-level: rebuild the parked inventory from durable
            # facts — bit-exact re-sampling through the persisted pose on
            # the re-derived lane raster; no pixels were stored.
            seeded_windows: list[PoseWindow] = []
            for row in sorted(
                    _mopup.parked_by_region[region_index],
                    key=lambda record: record.patch_ordinal):
                window = PoseWindow(
                    int(row.window_id), region_index,
                    tuple(int(v) for v in row.origin_yx_px),
                    tuple(int(v) for v in row.shape_yx_cells),
                    int(row.depth), int(row.support_estimate))
                pose = AffinePose(
                    tuple(float(v) for v in row.pose_origin_yx),
                    ((float(row.pose_jacobian[0]),
                      float(row.pose_jacobian[1])),
                     (float(row.pose_jacobian[2]),
                      float(row.pose_jacobian[3]))),
                    tuple(float(v) for v in row.pose_phase_yx),
                    float(row.pose_pitch_px), float(row.pose_angle_deg))
                segment = PoseSegment(
                    window, pose, int(row.support_cells),
                    float(row.phase_contrast),
                    tuple(float(v) for v in row.pitch_yx_px),
                    float(row.orthogonality_error_deg))
                sample = sample_segment(context, segment)
                if (sample is None
                        or int(sample.mask.sum()) < HISTORICAL_MIN_SUPPORT):
                    retain_attempt(WindowAttempt(
                        region_index, window, "insufficient_support",
                        tuple(row.attempted_routes), segment=segment,
                        reason="insufficient_support"))
                    continue
                patch = make_address_patch(
                    sample, _core(sample.mask, config.erode_cells))
                deferred.append(_DeferredWindow(
                    window, patch, int(row.patch_ordinal),
                    next_sample_key, list(row.attempted_routes), set()))
                next_sample_key += 1
                seeded_windows.append(window)
            announce_planned(seeded_windows)
            next_window_id = 1 + max(
                (window.window_id for window in seeded_windows),
                default=next_window_id - 1)
            # D7: reconstruct the base pass's accepted windows as
            # calibration labels for this region's payload fit.
            for row in sorted(
                    _mopup.label_poses_by_region.get(region_index, ()),
                    key=lambda record: record.patch_id):
                label = _label_patch(
                    row, region_index, context, memo, provider,
                    budgets.local, config, next_sample_key)
                next_sample_key += 1
                if label is not None:
                    label_placements.append(label)
            # Hint pre-pass: the mop-up inventory (every accepted pose and
            # losing hypothesis of the capture, all lanes) replaces the
            # cold for any parked window a 49-score local search resolves.
            if lower_hints and budgets.lower is not None:
                for entry in list(deferred):
                    _note_route(entry.attempted_routes, "lower_hint")
                    ranked = tuple(
                        hint for hint in _rank_lower_hints(
                            lower_hints, entry.patch)
                        if hint.page in pages)
                    per_hint = (2 * config.neighbor_radius_cells + 1) ** 2
                    if (not ranked or per_hint * len(ranked)
                            > budgets.lower.max_hypotheses):
                        continue
                    outcome = None
                    used_hint = None
                    for hint in ranked:
                        rot_k, predicted = _predict_from_hint(
                            hint, entry.patch.frame_pose,
                            entry.patch.shape_yx)
                        local = local_search(
                            entry.patch, hint.page, rot_k, predicted,
                            budgets.lower, memo,
                            sample_key=entry.sample_key,
                            config=config, route="lower_hint")
                        hypotheses_total += local.hypotheses
                        if local.accepted:
                            outcome, used_hint = local, hint
                            break
                    if outcome is not None:
                        deferred.remove(entry)
                        finalize_accept(
                            entry.window, entry.patch, entry.patch_id,
                            outcome, None, used_hint,
                            tuple(entry.attempted_routes))

        while pending or deferred:
            if pending:
                window = pick_pending()
                windows_processed += 1
                attempt_cheap(window)
                continue
            if chain_repass():
                continue
            if park:
                # v0.33 phase 1: no remaining-slot sweep, no cold — every
                # fall-through window parks durably for the mop-up level.
                seed = (None if context.lattice_f is None else tuple(
                    float(value) for value in
                    np.asarray(context.lattice_f, np.float64).ravel()))
                for entry in sorted(
                        deferred, key=lambda row: row.patch_id):
                    parked_windows.append(ParkedWindowFacts(
                        region_index, entry.window,
                        entry.patch.sample.segment, entry.patch_id,
                        tuple(entry.attempted_routes), float(pitch), seed))
                    retain_attempt(WindowAttempt(
                        region_index, entry.window, "parked",
                        tuple(entry.attempted_routes),
                        patch_id=entry.patch_id,
                        segment=entry.patch.sample.segment))
                region_parked += len(deferred)
                deferred.clear()
                continue
            # No chain progress remains.  PLACEMENT-IMPROVEMENTS §3.5
            # prices the boundary: above the threshold, decode remaining
            # word slots first (v0.29 — any rest-decode is cheaper than a
            # large cold sweep and re-opens the chain re-pass); at a small
            # declared domain the cold is the cheaper route, so it runs
            # first and the refused window still rest-decodes before
            # giving up.  Both routes run before any window gives up.
            rest_first = len(pages) > config.cold_first_max_pages
            if rest_first:
                rest_progress = False
                for entry in sorted(
                    deferred,
                    key=lambda row: (
                        -int(row.patch.mask.sum()), row.patch_id),
                ):
                    if entry.word_rest_done:
                        continue
                    entry.word_rest_done = True
                    if try_word_rest(entry):
                        deferred.remove(entry)
                        rest_progress = True
                        break
                if rest_progress:
                    continue
            # Spend exactly one cold search on the best-supported window.
            entry = max(
                deferred,
                key=lambda row: (int(row.patch.mask.sum()), -row.patch_id),
            )
            deferred.remove(entry)
            run_cold(entry, rest_fallback=not rest_first)
        if region_accepted:
            state = "accepted"
        elif region_placed:
            state = "redundant"
        elif region_parked:
            # v0.33 D19: parked is non-terminal — "unresolved" stays bound
            # to cold-refused-terminal, which cannot have happened here.
            state = "parked"
        else:
            state = "unresolved"
        region_states.append((region_index, state))
        if (address_region_progress is None
                or (address_region_progress_enabled is not None
                    and not address_region_progress_enabled())):
            _emit(
                progress, "address.region_complete",
                Detail("address.region", region_index),
                Detail("address.state", state),
                Detail("address.region_placements",
                       len(placements) - region_placement_start),
                Detail("address.hypotheses", hypotheses_total),
            )
        else:
            address_region_progress(
                region_index, state,
                tuple(placements[region_placement_start:]),
                tuple(attempts[region_attempt_start:]),
                ((region_index, state),), hypotheses_total)

    all_observations = tuple(
        observation
        for placement in placements
        for observation in placement.observations
    )
    words = known_position_words(all_observations, spec)
    # E023c retains only a small, deterministic losing-address tail.  This is
    # the historical per-region order: held-out mismatch first, then search
    # mismatch, greater search support, and finally stable hypothesis id.
    retained_losers = _retained_losing_hints(losing_hints)
    continuation_hints = promoted_continuation_hints(
        tuple(accepted_hints + retained_losers), words
    )
    return AddressResult(
        tuple(placements), tuple(unresolved), words,
        tuple(region_states), int(hypotheses_total),
        continuation_hints,
        tuple(attempts),
        parked_windows=tuple(parked_windows),
        label_placements=tuple(label_placements),
    )


__all__ = [
    "AddressResult", "AttemptBudget", "FormatHypothesisRejected",
    "PlacementBudgets", "PlacementConfig", "PlacementHint",
    "place_committed", "place_mopup", "place_survey", "placement_hint",
]
