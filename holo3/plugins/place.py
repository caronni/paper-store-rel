from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

from .. import data
from ..format import pilots
from ..format.identity import FormatRow
from ..lib import geometry
from ..lib.decimate import as_fraction, plane_mean_luma_f32
from . import cold, pose, words

E022_SUPPORT_FLOOR_SITES: int = 30
GATE_SEARCH_TRUE: float = 0.20
GATE_RIVAL_DECOY: float = 0.20
GATE_MINIMUM_GAP: float = 0.08
GATE_VALIDATION_TRUE: float = 0.24
BER_ENVELOPE: float = 0.08
SUPPORT_MARGIN_SITES: int = 0
NEIGHBOR_RADIUS_CELLS: int = 3
CONSISTENCY_CELLS: int = 2
LOCAL_HYPOTHESES: int = (2 * NEIGHBOR_RADIUS_CELLS + 1) ** 2
CONSULT_KEEP: int = 8
WIDE_ANCHORS: int = 8
WINDOW_CELLS: int = geometry.WINDOW_CELLS
WINDOW_STEP_CELLS: int = geometry.WINDOW_STEP_CELLS

ROUTE_CHAIN: str = "chain"
ROUTE_WORD: str = "word"
ROUTE_COLD: str = "correlation"

STAGE_RING: str = "ring"
STAGE_WORD_CENTRE: str = "word_centre"
STAGE_WORD_REST: str = "word_rest"
STAGE_WIDE: str = "wide"
STAGE_COLD_LIVE: str = "cold_live"
STAGE_COLD_REST: str = "cold_rest"
STAGE_COST: dict[str, int] = {
    STAGE_RING: 40,
    STAGE_WORD_CENTRE: 60,
    STAGE_WORD_REST: 80,
    STAGE_WIDE: 120,
    STAGE_COLD_LIVE: 250,
    STAGE_COLD_REST: 260,
}
COLD_STAGES: tuple[str, str] = (STAGE_COLD_LIVE, STAGE_COLD_REST)
LANE_COST_PER_RUNG: int = 2
COLD_COST_PER_RUNG: int = 20
CHILD_PREMIUM: int = 5

REGIONAL_SEED: str = "regional-affine"
TRIED_COLD: str = "cold-page"

SUBDIVISION_DIRECT: frozenset[str] = frozenset(
    {"pose_refused", "straddle_audit_refused"})
NEVER_SUBDIVIDES: frozenset[str] = frozenset({"insufficient_support"})


def identifiability_support_floor(hypotheses: int,
                                  max_true_error_rate: float) -> int:
    if hypotheses == 1:
        return 0
    error = float(max_true_error_rate)
    entropy = (
        0.0 if error == 0.0
        else -error * math.log2(error)
        - (1.0 - error) * math.log2(1.0 - error))
    return int(math.ceil(math.log2(hypotheses) / (1.0 - entropy)))


def min_support_for(hypotheses: int) -> int:
    return max(
        E022_SUPPORT_FLOOR_SITES,
        identifiability_support_floor(hypotheses, BER_ENVELOPE)
        + SUPPORT_MARGIN_SITES)


def pass_budget_hypotheses(tried: int, offered: int) -> int:
    return LOCAL_HYPOTHESES * max(1, int(tried) + int(offered))


def stage_price(stage: str, lane_depth: int, depth: int) -> int:
    rung = (COLD_COST_PER_RUNG if stage in COLD_STAGES
            else LANE_COST_PER_RUNG)
    return (STAGE_COST[stage] + rung * int(lane_depth)
            + (CHILD_PREMIUM if depth else 0))


def stage_of(offered: bool, centre_spent: bool, rest_spent: bool,
             wide_spent: bool, cold_armed: bool,
             cold_live_ready: bool, cold_live_spent: bool,
             cold_rest_ready: bool, cold_rest_spent: bool) -> str | None:
    if offered:
        return STAGE_RING
    if not centre_spent:
        return STAGE_WORD_CENTRE
    if not rest_spent:
        return STAGE_WORD_REST
    if not wide_spent:
        return STAGE_WIDE
    if cold_armed and cold_live_ready and not cold_live_spent:
        return STAGE_COLD_LIVE
    if cold_armed and cold_rest_ready and not cold_rest_spent:
        return STAGE_COLD_REST
    return None


def subdivides(outcome: str) -> bool:
    if outcome in SUBDIVISION_DIRECT:
        return True
    return outcome in (f"cold_refused_{flavour}" for flavour in COLD_STAGES)


def cold_tried_id(page: int, flavour: str) -> str:
    return f"{TRIED_COLD}/{flavour}/{int(page)}"


def cold_flavour_pages(page_domain: tuple[int, ...], flavour: str,
                       live_pages: frozenset[int]) -> tuple[int, ...]:
    if flavour == STAGE_COLD_LIVE:
        return tuple(page for page in page_domain if page in live_pages)
    return tuple(page for page in page_domain if page not in live_pages)


@dataclass(frozen=True)
class RegionFrame:
    capture_id: str
    level_index: int
    region_index: int
    scale: int
    origin_native_yx: tuple[int, int]
    origin_level_yx: tuple[int, int]
    pitch_native_px: float
    pitch_level_px: float
    shape_cells: tuple[int, int]
    support_cells: np.ndarray
    survey_step_px: int
    survey_cells: np.ndarray
    survey_extent_px: tuple[int, int]
    backing: float


def _sample_support(region: data.Region, shape_cells: tuple[int, int],
                    pitch_native_px: float) -> np.ndarray:
    rows, cols = shape_cells
    centres_y = pitch_native_px * (np.arange(rows, dtype=np.float64) + 0.5)
    centres_x = pitch_native_px * (np.arange(cols, dtype=np.float64) + 0.5)
    iy = np.floor(centres_y / region.step_px).astype(np.int64)
    ix = np.floor(centres_x / region.step_px).astype(np.int64)
    valid_y = (iy >= 0) & (iy < region.cells.shape[0])
    valid_x = (ix >= 0) & (ix < region.cells.shape[1])
    support = np.zeros((rows, cols), bool)
    if not valid_y.any() or not valid_x.any():
        return support
    picked = region.cells[np.ix_(iy[valid_y], ix[valid_x])]
    support[np.ix_(np.flatnonzero(valid_y),
                   np.flatnonzero(valid_x))] = picked
    return support


def region_frame(region: data.Region, level: data.Level,
                 pitch_in: Fraction, dpi: float,
                 backing: float) -> RegionFrame | None:
    pitch_native = as_fraction(dpi) * pitch_in
    scale = int(level.scale)
    pitch_level = pitch_native / scale
    rows = max(1, int(Fraction(region.extent_px[0]) / pitch_native))
    cols = max(1, int(Fraction(region.extent_px[1]) / pitch_native))
    support = _sample_support(region, (rows, cols), float(pitch_native))
    if not support.any():
        return None
    origin_native = (int(region.origin_yx[0]), int(region.origin_yx[1]))
    return RegionFrame(
        capture_id=region.capture_id,
        level_index=level.index,
        region_index=region.region_index,
        scale=scale,
        origin_native_yx=origin_native,
        origin_level_yx=(origin_native[0] // scale,
                         origin_native[1] // scale),
        pitch_native_px=float(pitch_native),
        pitch_level_px=float(pitch_level),
        shape_cells=(rows, cols),
        support_cells=support,
        survey_step_px=int(region.step_px),
        survey_cells=np.asarray(region.cells, bool),
        survey_extent_px=(int(region.extent_px[0]),
                          int(region.extent_px[1])),
        backing=float(backing))


def window_plan(frame: RegionFrame, lane_depth: int,
                first_ordinal: int = 0) -> tuple[data.Window, ...]:
    rows, cols = frame.shape_cells
    windows: list[data.Window] = []
    ordinal = int(first_ordinal)
    for cy0 in geometry.window_starts(rows):
        cy1 = min(rows, cy0 + WINDOW_CELLS)
        for cx0 in geometry.window_starts(cols):
            cx1 = min(cols, cx0 + WINDOW_CELLS)
            extent = (cy0, cx0, cy1, cx1)
            supported = int(np.count_nonzero(
                frame.support_cells[cy0:cy1, cx0:cx1]))
            if supported == 0:
                continue
            windows.append(data.Window(
                window_id=(frame.capture_id, frame.level_index,
                           frame.region_index, extent),
                capture_id=frame.capture_id,
                level_index=frame.level_index,
                region_index=frame.region_index,
                extent_cells=extent,
                supported_cells=supported,
                depth=0,
                lane_depth=int(lane_depth),
                ordinal=ordinal))
            ordinal += 1
    return tuple(windows)


def ring_neighbour_extents(
    shape_cells: tuple[int, int],
    extent_cells: tuple[int, int, int, int],
) -> tuple[tuple[int, int, int, int], ...]:
    rows, cols = shape_cells
    starts_y = geometry.window_starts(rows)
    starts_x = geometry.window_starts(cols)
    cy0, cx0 = extent_cells[0], extent_cells[1]
    if cy0 not in starts_y or cx0 not in starts_x:
        return ()
    iy = starts_y.index(cy0)
    ix = starts_x.index(cx0)
    out: list[tuple[int, int, int, int]] = []
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            jy, jx = iy + dy, ix + dx
            if 0 <= jy < len(starts_y) and 0 <= jx < len(starts_x):
                ny0, nx0 = starts_y[jy], starts_x[jx]
                out.append((ny0, nx0, min(rows, ny0 + WINDOW_CELLS),
                            min(cols, nx0 + WINDOW_CELLS)))
    return tuple(out)


def child_windows(frame: RegionFrame, window: data.Window,
                  first_ordinal: int) -> tuple[data.Window, ...]:
    rows, cols = frame.shape_cells
    out: list[data.Window] = []
    ordinal = int(first_ordinal)
    for extent in pose.subdivision_child_extents(
            window.extent_cells, window.depth):
        cy0, cx0, cy1, cx1 = extent
        if cy0 < 0 or cx0 < 0 or cy1 > rows or cx1 > cols:
            continue
        supported = int(np.count_nonzero(
            frame.support_cells[cy0:cy1, cx0:cx1]))
        if supported == 0:
            continue
        out.append(data.Window(
            window_id=(frame.capture_id, frame.level_index,
                       frame.region_index, extent),
            capture_id=frame.capture_id,
            level_index=frame.level_index,
            region_index=frame.region_index,
            extent_cells=extent,
            supported_cells=supported,
            depth=window.depth + 1,
            lane_depth=window.lane_depth,
            ordinal=ordinal))
        ordinal += 1
    return tuple(out)


def page_affine_terms(jacobian: np.ndarray,
                      origin_level_yx: tuple[float, float],
                      patch_shape_yx: tuple[int, int], rot_k: int,
                      page_origin_yx: tuple[int, int],
                      scale: int) -> tuple[float, ...]:
    rotation, translation = pose.rotation_affine(rot_k, patch_shape_yx)
    linear = jacobian @ rotation.T
    shift = translation + np.asarray(page_origin_yx, np.float64)
    offset = (np.asarray(origin_level_yx, np.float64) - linear @ shift
              - linear @ np.full(2, 0.5))
    terms = (float(linear[0, 0]), float(linear[0, 1]), float(offset[0]),
             float(linear[1, 0]), float(linear[1, 1]), float(offset[1]))
    return geometry.compose_to_native(terms, Fraction(scale))


def predict_from_page_affine(
    page_affine: tuple[float, ...],
    target_jacobian: np.ndarray,
    target_origin_level_yx: tuple[float, float],
    target_shape_yx: tuple[int, int],
    scale: int,
) -> tuple[int, tuple[int, int]]:
    affine = geometry.compose_from_native(page_affine, Fraction(scale))
    matrix = geometry.affine_matrix(affine)
    page_jacobian = matrix[:, :2]
    rotations = [pose.rotation_affine(rot_k, target_shape_yx)
                 for rot_k in range(4)]
    rot_k = min(range(4), key=lambda k: float(np.linalg.norm(
        target_jacobian @ rotations[k][0].T - page_jacobian)))
    page_offset = matrix[:, 2] + page_jacobian @ np.full(2, 0.5)
    page_at_local_zero = np.linalg.solve(
        page_jacobian,
        np.asarray(target_origin_level_yx, np.float64) - page_offset)
    origin = page_at_local_zero - rotations[rot_k][1]
    return rot_k, (int(round(origin[0])), int(round(origin[1])))


@dataclass(frozen=True)
class AnchorPose:
    pose_id: str
    extent_cells: tuple[int, int, int, int]
    page: int
    native_affine: tuple[float, ...]


@dataclass(frozen=True)
class Seed:
    candidate_id: str
    page: int
    distance: float
    affine: tuple[float, ...]


def window_centre_cells(
        extent_cells: tuple[int, int, int, int]) -> tuple[float, float]:
    return ((extent_cells[0] + extent_cells[2]) / 2.0,
            (extent_cells[1] + extent_cells[3]) / 2.0)


def hint_distance(source_centre_cells: tuple[float, float],
                  hinted_centre_cells: tuple[float, float],
                  stride_cells: float) -> float:
    return math.hypot(
        hinted_centre_cells[0] - source_centre_cells[0],
        hinted_centre_cells[1] - source_centre_cells[1],
    ) / float(stride_cells)


def consult_seeds(extent_cells: tuple[int, int, int, int],
                  anchors: tuple[AnchorPose, ...],
                  page_domain: tuple[int, ...],
                  wide: bool) -> tuple[Seed, ...]:
    here = window_centre_cells(extent_cells)
    stride = float(WINDOW_STEP_CELLS)
    seeds: list[Seed] = []
    for anchor in anchors:
        if anchor.page not in page_domain:
            continue
        distance = hint_distance(
            window_centre_cells(anchor.extent_cells), here, stride)
        seeds.append(Seed(anchor.pose_id, anchor.page, distance,
                          tuple(anchor.native_affine)))
    seeds.sort(key=lambda seed: (seed.distance, seed.candidate_id,
                                 seed.affine))
    return tuple(seeds[:(WIDE_ANCHORS if wide else CONSULT_KEEP)])


def regional_seed(frame: RegionFrame, anchors: tuple[AnchorPose, ...],
                  page_domain: tuple[int, ...]) -> Seed | None:
    by_page: dict[int, list[np.ndarray]] = {}
    for anchor in anchors:
        if anchor.page not in page_domain:
            continue
        cy0, cx0, cy1, cx1 = anchor.extent_cells
        pitch = frame.pitch_native_px
        corners_y = np.asarray(
            [frame.origin_native_yx[0] + pitch * (cy0 + 0.5),
             frame.origin_native_yx[0] + pitch * (cy1 - 1 + 0.5)],
            np.float64)
        corners_x = np.asarray(
            [frame.origin_native_yx[1] + pitch * (cx0 + 0.5),
             frame.origin_native_yx[1] + pitch * (cx1 - 1 + 0.5)],
            np.float64)
        native_y = np.repeat(corners_y, 2)
        native_x = np.tile(corners_x, 2)
        page_y, page_x = geometry.apply_affine(
            geometry.invert_affine(anchor.native_affine),
            native_y, native_x)
        by_page.setdefault(int(anchor.page), []).append(
            np.stack([page_y, page_x, native_y, native_x], axis=1))
    if not by_page:
        return None
    page = min(by_page,
               key=lambda candidate: (-len(by_page[candidate]), candidate))
    if len(by_page[page]) < 2:
        return None
    rows = np.concatenate(by_page[page], axis=0)
    design = np.stack([rows[:, 0], rows[:, 1],
                       np.ones(rows.shape[0], np.float64)], axis=1)
    solution, _residuals, rank, _singular = np.linalg.lstsq(
        design, rows[:, 2:4], rcond=None)
    if int(rank) < 3:
        return None
    terms = (float(solution[0, 0]), float(solution[1, 0]),
             float(solution[2, 0]), float(solution[0, 1]),
             float(solution[1, 1]), float(solution[2, 1]))
    if not bool(np.isfinite(terms).all()):
        return None
    return Seed(f"{REGIONAL_SEED}/{terms}", page, float("inf"), terms)


def local_search(memo: pose.ScoreMemo, evidence: np.ndarray,
                 bits: np.ndarray, mask: np.ndarray, page: int, rot_k: int,
                 predicted: tuple[int, int], min_support: int,
                 max_hypotheses: int,
                 route: str = ROUTE_CHAIN) -> pose.SearchOutcome:
    radius = NEIGHBOR_RADIUS_CELLS
    hypotheses = (2 * radius + 1) ** 2
    if hypotheses > max_hypotheses:
        return pose.SearchOutcome(
            False, None, (), hypotheses, "attempt_budget_exceeded")
    candidates = [
        memo.candidate(
            evidence, bits, mask, page,
            (predicted[0] + dy, predicted[1] + dx), rot_k,
            min_support, GATE_SEARCH_TRUE, GATE_VALIDATION_TRUE, route)
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
    ]
    candidates.sort(key=lambda row: (
        -row.soft_z, row.origin_yx[0], row.origin_yx[1]))
    if not candidates or not np.isfinite(candidates[0].soft_z):
        return pose.SearchOutcome(
            False, None, tuple(candidates), hypotheses,
            "insufficient_support")
    best = candidates[0]
    residual = max(abs(best.origin_yx[0] - predicted[0]),
                   abs(best.origin_yx[1] - predicted[1]))
    accepted = best.passes and residual <= CONSISTENCY_CELLS
    return pose.SearchOutcome(
        accepted, best, tuple(candidates[1:]), hypotheses,
        "accepted" if accepted else "local_validation_failed")


def _whole_word(memo: pose.ScoreMemo, evidence: np.ndarray,
                bits: np.ndarray, mask: np.ndarray, page: int,
                origin_yx: tuple[int, int], rot_k: int) -> float:
    return memo.parity_score(evidence, bits, mask, page, origin_yx, rot_k,
                             pose.WHOLE_WORD_PARITY)[0]


def _word_rival_bar(memo: pose.ScoreMemo, evidence: np.ndarray,
                    bits: np.ndarray, mask: np.ndarray,
                    winner: words.WordCandidate,
                    candidates: tuple[words.WordCandidate, ...],
                    page_domain: tuple[int, ...]) -> bool:
    rivals = words.word_rival_rows(winner, candidates, page_domain,
                                   NEIGHBOR_RADIUS_CELLS)
    if not rivals:
        return pose.rival_gate(
            memo.parity_score(evidence, bits, mask, winner.page,
                              winner.page_origin_yx, winner.rot_k, 0)[0],
            1.0, GATE_RIVAL_DECOY, GATE_MINIMUM_GAP)
    rival_mismatch = min(
        _whole_word(memo, evidence, bits, mask, page, origin_yx, rot_k)
        for page, origin_yx, rot_k in rivals)
    best_whole = _whole_word(memo, evidence, bits, mask, winner.page,
                             winner.page_origin_yx, winner.rot_k)
    return pose.rival_gate(best_whole, rival_mismatch, GATE_RIVAL_DECOY,
                           GATE_MINIMUM_GAP)


def word_address(memo: pose.ScoreMemo, evidence: np.ndarray,
                 bits: np.ndarray, mask: np.ndarray,
                 candidates: tuple[words.WordCandidate, ...],
                 page_domain: tuple[int, ...], min_support: int,
                 ) -> tuple[words.WordCandidate, float] | None:
    in_domain = tuple(candidate for candidate in candidates
                      if candidate.page in page_domain)
    for candidate in in_domain:
        scored = memo.candidate(
            evidence, bits, mask, candidate.page,
            candidate.page_origin_yx, candidate.rot_k,
            min_support, GATE_SEARCH_TRUE, GATE_VALIDATION_TRUE,
            ROUTE_WORD)
        if not scored.passes:
            continue
        if not _word_rival_bar(memo, evidence, bits, mask, candidate,
                               in_domain, page_domain):
            return None
        return candidate, scored.search_mismatch
    return None


def seed_rank(support_cells: int,
              window_id: tuple[str, int, int, tuple[int, int, int, int]],
              ) -> tuple[int, tuple[str, int, int,
                                    tuple[int, int, int, int]]]:
    return (-int(support_cells), window_id)


def seed_supersedes(
    proposed_support: int,
    proposed_window_id: tuple[str, int, int, tuple[int, int, int, int]],
    current_support: int,
    current_window_id: tuple[str, int, int, tuple[int, int, int, int]],
) -> bool:
    return (seed_rank(proposed_support, proposed_window_id)
            < seed_rank(current_support, current_window_id))


def done_covers(done_cells: np.ndarray, support_cells: np.ndarray,
                extent_cells: tuple[int, int, int, int]) -> bool:
    cy0, cx0, cy1, cx1 = extent_cells
    window_support = support_cells[cy0:cy1, cx0:cx1]
    if not window_support.any():
        return False
    return bool(np.all(done_cells[cy0:cy1, cx0:cx1][window_support]))


@dataclass(frozen=True)
class WindowPass:
    window: data.Window
    frame: RegionFrame
    planes: tuple[np.ndarray, ...]
    row: FormatRow
    reference: words.ReferenceField
    page_domain: tuple[int, ...]
    stage: str | None
    wide: bool
    cold_flavour: str | None
    cold_pages: tuple[int, ...]
    seeds: tuple[Seed, ...]
    tried_count: int
    lattice_seed: tuple[float, float, float, float] | None
    patch_ordinal: int
    cold_h_pages: int = 0


@dataclass(frozen=True)
class WindowPassResult:
    outcome: str
    route: str | None
    placement: data.Placement | None
    lattice_seed: data.LatticeSeed | None
    tried_now: tuple[str, ...]
    stage_spent: str | None
    wide_spent: bool
    cold_spent: str | None
    hypotheses: int
    events: tuple[object, ...]


def _crop_luma(planes: tuple[np.ndarray, ...], y0: int, y1: int,
               x0: int, x1: int) -> np.ndarray:
    if len(planes) == 3:
        return plane_mean_luma_f32(
            planes[0][y0:y1, x0:x1], planes[1][y0:y1, x0:x1],
            planes[2][y0:y1, x0:x1])
    return np.asarray(planes[0][y0:y1, x0:x1], np.float32)


def support_pixels(frame: RegionFrame, y0: int, y1: int, x0: int,
                   x1: int) -> np.ndarray:
    scale = frame.scale
    native_y = (np.arange(y0, y1, dtype=np.int64) * scale + scale // 2
                - frame.origin_native_yx[0])
    native_x = (np.arange(x0, x1, dtype=np.int64) * scale + scale // 2
                - frame.origin_native_yx[1])
    iy = native_y // frame.survey_step_px
    ix = native_x // frame.survey_step_px
    valid_y = ((native_y >= 0) & (native_y < frame.survey_extent_px[0])
               & (iy < frame.survey_cells.shape[0]))
    valid_x = ((native_x >= 0) & (native_x < frame.survey_extent_px[1])
               & (ix < frame.survey_cells.shape[1]))
    out = np.zeros((y1 - y0, x1 - x0), bool)
    if not valid_y.any() or not valid_x.any():
        return out
    picked = frame.survey_cells[np.ix_(iy[valid_y], ix[valid_x])]
    out[np.ix_(np.flatnonzero(valid_y), np.flatnonzero(valid_x))] = picked
    return out


def _window_crop(job: WindowPass) -> tuple[pose.WindowPixels,
                                           tuple[int, int]] | None:
    frame = job.frame
    cy0, cx0, cy1, cx1 = job.window.extent_cells
    cells = (cy1 - cy0, cx1 - cx0)
    pitch = frame.pitch_level_px
    wy = frame.origin_level_yx[0] + int(round(cy0 * pitch))
    wx = frame.origin_level_yx[1] + int(round(cx0 * pitch))
    halo = int(math.ceil(pose.HALO_CELLS * pitch))
    py1 = wy + int(round(cells[0] * pitch))
    px1 = wx + int(round(cells[1] * pitch))
    plane_shape = job.planes[0].shape
    y0 = max(0, wy - halo)
    y1 = min(int(plane_shape[0]), py1 + halo)
    x0 = max(0, wx - halo)
    x1 = min(int(plane_shape[1]), px1 + halo)
    if y1 <= y0 or x1 <= x0:
        return None
    luma = _crop_luma(job.planes, y0, y1, x0, x1)
    support = support_pixels(frame, y0, y1, x0, x1)
    pixels = pose.window_pixels(
        luma, support, (wy - y0, wx - x0), cells, pitch, frame.backing)
    if pixels is None:
        return None
    return pixels, (y0, x0)


def _seed_fact(job: WindowPass,
               fit: pose.WindowFit) -> data.LatticeSeed | None:
    if fit.unconditioned_seed is None:
        return None
    return data.LatticeSeed(
        capture_id=job.frame.capture_id,
        level_index=job.frame.level_index,
        region_index=job.frame.region_index,
        rows=np.asarray(fit.unconditioned_seed, np.float64),
        support_cells=job.window.supported_cells,
        window_ordinal=job.window.ordinal)


def _settled(job: WindowPass, outcome: str,
             seed_fact: data.LatticeSeed | None = None,
             tried_now: tuple[str, ...] = (),
             stage_spent: str | None = None,
             wide_spent: bool = False,
             cold_spent: str | None = None,
             hypotheses: int = 0) -> WindowPassResult:
    event = data.WindowSettled(
        capture=job.frame.capture_id,
        level_index=job.frame.level_index,
        region_index=job.frame.region_index,
        extent_cells=job.window.extent_cells,
        state=outcome)
    return WindowPassResult(
        outcome, None, None, seed_fact, tried_now, stage_spent,
        wide_spent, cold_spent, hypotheses, (event,))


def _address_coverage(placement: data.Placement,
                      local_shape_yx: tuple[int, int],
                      row: FormatRow) -> data.AddressCoverage | None:
    local = np.asarray(placement.local_cells_yx, np.int64)
    if not local.size:
        return None
    mapped = geometry.rotated_points(local, local_shape_yx, placement.rot_k)
    mapped = mapped + np.asarray(placement.page_origin_yx, np.int64)
    height, width = row.cells_yx
    inside = ((mapped[:, 0] >= 0) & (mapped[:, 0] < height)
              & (mapped[:, 1] >= 0) & (mapped[:, 1] < width))
    mapped = mapped[inside]
    if not mapped.size:
        return None
    period = pilots.TILE_CELLS
    site_index = words.word_site_index(row.sites_seed)
    sites = site_index[mapped[:, 0] % period, mapped[:, 1] % period]
    keep = sites >= 0
    if not bool(keep.any()):
        return None
    tiles_x = row.tiles_yx[1]
    flat = ((mapped[keep, 0] // period) * tiles_x
            + (mapped[keep, 1] // period))
    site_ids = sites[keep].astype(np.int64)
    rows_out: list[tuple[int, int, bytes]] = []
    for tile_flat in np.unique(flat):
        mask = np.zeros(pilots.N_WORD_SITES, bool)
        mask[site_ids[flat == tile_flat]] = True
        rows_out.append((int(tile_flat // tiles_x), int(tile_flat % tiles_x),
                         np.packbits(mask).tobytes()))
    return data.AddressCoverage(page=placement.page, tiles=tuple(rows_out))


def run_window_pass(job: WindowPass) -> WindowPassResult:
    """One placement pass over one window.

    NO DONE GATE HERE.  Done-geometry retires at the scheduler door
    (`place_sched.place_retire_cause`), which `engine._fill` consults
    before it builds this job — a done window never reaches this
    function, so a second copy of the test here would be unreachable by
    construction and was deleted with the evidence
    (`measure/donegeo_realstate.py`).
    """
    frame = job.frame
    extent = job.window.extent_cells
    seeds = job.seeds
    will_word = (not seeds) and job.stage is not None
    if not seeds and not will_word and not job.cold_pages:
        if job.cold_flavour is not None:
            return _settled(job, f"cold_refused_{job.cold_flavour}",
                            wide_spent=job.wide,
                            cold_spent=job.cold_flavour)
        return _settled(job, "nothing_to_try", wide_spent=job.wide)
    budget_hypotheses = pass_budget_hypotheses(job.tried_count, len(seeds))
    floor = min_support_for(budget_hypotheses)
    crop = _window_crop(job)
    if crop is None:
        return _settled(job, "insufficient_support")
    pixels, crop_origin = crop
    seed_rows = (None if job.lattice_seed is None
                 else np.asarray(job.lattice_seed,
                                 np.float64).reshape(2, 2))
    fit = pose.fit_window_pose(pixels, seed_rows)
    seed_fact = _seed_fact(job, fit)
    if fit.segment is None:
        return _settled(job, "pose_refused", seed_fact=seed_fact)
    sample = pose.sample_segment(pixels, fit.segment)
    if sample is None or int(sample.mask.sum()) < E022_SUPPORT_FLOOR_SITES:
        return _settled(job, "insufficient_support", seed_fact=seed_fact)
    core = pose.address_core(sample.mask)
    memo = pose.ScoreMemo(job.reference)
    tried_now: tuple[str, ...] = ()
    stage_spent: str | None = None
    cold_spent: str | None = None
    address: tuple[int, int, tuple[int, int]] | None = None
    route: str | None = None
    word_candidate: words.WordCandidate | None = None
    mismatch = 0.0
    hypotheses = budget_hypotheses
    audit_floor = floor
    if seeds:
        tried_now = tuple(seed.candidate_id for seed in seeds)
        for seed in seeds:
            rot_k, predicted = predict_from_page_affine(
                seed.affine, sample.segment.pose.matrix(),
                (crop_origin[0] + sample.segment.pose.origin_yx[0],
                 crop_origin[1] + sample.segment.pose.origin_yx[1]),
                pixels.shape_yx_cells, frame.scale)
            outcome = local_search(
                memo, sample.evidence, sample.bits, core, seed.page,
                rot_k, predicted, floor, budget_hypotheses)
            if outcome.accepted and outcome.best is not None:
                address = (seed.page, rot_k, outcome.best.origin_yx)
                route = ROUTE_CHAIN
                mismatch = outcome.best.search_mismatch
                break
    if address is None and will_word and job.stage is not None:
        result = words.stage_a(sample.bits, core, job.row, job.stage)
        stage_spent = job.stage
        hypotheses = result.hypotheses
        if result.reason != "attempt_budget_exceeded":
            admitted = word_address(
                memo, sample.evidence, sample.bits, core,
                result.candidates, job.page_domain, floor)
            if admitted is not None:
                word_candidate, mismatch = admitted
                address = (word_candidate.page, word_candidate.rot_k,
                           word_candidate.page_origin_yx)
                route = ROUTE_WORD
    if address is None and job.cold_pages:
        tried_now = tried_now + tuple(
            cold_tried_id(page, job.cold_flavour or "")
            for page in job.cold_pages)
        cold_spent = job.cold_flavour
        declared = cold.hypothesis_count(
            (WINDOW_CELLS, WINDOW_CELLS), job.row.cells_yx,
            job.cold_h_pages)
        cold_floor = min_support_for(declared)
        outcome = cold.correlate_patch(
            sample.evidence, sample.bits, core, job.reference,
            job.cold_pages, declared, cold_floor, memo,
            GATE_SEARCH_TRUE, GATE_VALIDATION_TRUE, GATE_RIVAL_DECOY,
            GATE_MINIMUM_GAP, NEIGHBOR_RADIUS_CELLS)
        hypotheses = outcome.hypotheses
        if outcome.accepted and outcome.best is not None:
            address = (outcome.best.page, outcome.best.rot_k,
                       outcome.best.origin_yx)
            route = ROUTE_COLD
            mismatch = outcome.best.search_mismatch
            audit_floor = cold_floor
    if address is None:
        if cold_spent is not None:
            reason = f"cold_refused_{cold_spent}"
        elif seeds:
            reason = "wide_refused" if job.wide else "consult_refused"
        else:
            reason = f"no_word_candidate_{stage_spent}"
        return _settled(job, reason, seed_fact=seed_fact,
                        tried_now=tried_now, stage_spent=stage_spent,
                        wide_spent=job.wide, cold_spent=cold_spent,
                        hypotheses=hypotheses)
    page, rot_k, origin_yx = address
    refined = pose.refine_patch_pose(
        pixels, sample, job.reference, page, origin_yx, rot_k)
    if (refined is not None
            and int(refined.sample.mask.sum()) >= E022_SUPPORT_FLOOR_SITES):
        sample = refined.sample
        core = pose.address_core(refined.sample.mask)
    audited, refused, _kept, _residual = pose.audit_segment(
        sample, core, job.reference, page, origin_yx, rot_k, audit_floor)
    if refused:
        return _settled(job, "straddle_audit_refused", seed_fact=seed_fact,
                        tried_now=tried_now, stage_spent=stage_spent,
                        wide_spent=job.wide, cold_spent=cold_spent,
                        hypotheses=hypotheses)
    final_pose = sample.segment.pose
    native = page_affine_terms(
        final_pose.matrix(),
        (crop_origin[0] + final_pose.origin_yx[0],
         crop_origin[1] + final_pose.origin_yx[1]),
        pixels.shape_yx_cells, rot_k, origin_yx, frame.scale)
    pitch_native = 0.5 * (float(np.hypot(native[0], native[3]))
                          + float(np.hypot(native[1], native[4])))
    local_cells = np.argwhere(np.asarray(audited, bool)).astype(
        np.int64, copy=False)
    placement = data.Placement(
        window_id=job.window.window_id,
        capture_id=frame.capture_id,
        level_index=frame.level_index,
        region_index=frame.region_index,
        patch_ordinal=job.patch_ordinal,
        page=int(page),
        rot_k=int(rot_k),
        page_origin_yx=(int(origin_yx[0]), int(origin_yx[1])),
        native_affine=native,
        pitch_px=pitch_native,
        route=str(route),
        local_cells_yx=local_cells,
        quality=float(mismatch))
    local_shape = (int(np.asarray(audited).shape[0]),
                   int(np.asarray(audited).shape[1]))
    event = data.PoseCommitted(
        capture=frame.capture_id,
        level_index=frame.level_index,
        region_index=frame.region_index,
        extent_cells=extent,
        page=int(page),
        route=str(route),
        mismatch=float(mismatch),
        accepted=True,
        page_origin_yx=(int(origin_yx[0]), int(origin_yx[1])),
        rot_k=int(rot_k),
        pitch_px=float(pitch_native),
        native_affine=native,
        shape_yx=local_shape)
    pass_events: list[object] = [event]
    try:
        if route == ROUTE_WORD and word_candidate is not None:
            pass_events.append(data.WordOutcome(
                page=int(word_candidate.page),
                ty=int(word_candidate.tile_yx[0]),
                tx=int(word_candidate.tile_yx[1]),
                errors=int(word_candidate.errors),
                sites=int(word_candidate.visible)))
        coverage = _address_coverage(placement, local_shape, job.row)
        if coverage is not None:
            pass_events.append(coverage)
    except Exception:
        pass
    return WindowPassResult(
        "accepted", route, placement, seed_fact, tried_now, stage_spent,
        job.wide, cold_spent, hypotheses, tuple(pass_events))
