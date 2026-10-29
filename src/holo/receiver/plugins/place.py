"""THE PLACEMENT LAW: what a window may try next, and at what price.

The admission algebra (the E022 gates and the identifiability floor),
the rung LADDER with its prices, the region frame, the window plan and
its quartering geometry, and the consult portfolio -- all pure, all
read by the scheduling half (`place_sched`) and by the store folds.

The JOB this ladder schedules lives in `place_pass.py`, which was cut
out of here 2026-09-21 when the quartering became a rung and this file
passed the 1000-line seam signal.  That module reads this one; this one
never reads it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

from .. import data
from ..lib import geometry
from ..lib.decimate import as_fraction
from . import pose, words

#: E022-v2's measured floor, per DISJOINT parity population,
#: qualified 2026-07-14 (experiments/022-pilot-tile-search §11.2).
#: The score is an evidence-weighted mismatch, not a Binomial
#: hard-error count: no alpha and no BER tail may derive it.
E022_SUPPORT_FLOOR_SITES: int = 30
#: The exact strict E022-v2 bars (qualified 2026-07-14).  A
#: candidate passes on the search parity and is confirmed on the
#: held-out one; the decoy and gap are evaluated WHOLE-WORD, never
#: on the search class alone (pose.WHOLE_WORD_PARITY says why).
GATE_SEARCH_TRUE: float = 0.20
GATE_RIVAL_DECOY: float = 0.20
GATE_MINIMUM_GAP: float = 0.08
GATE_VALIDATION_TRUE: float = 0.24
#: The two PROVISIONAL numbers of the admission algebra: the
#: channel-BER envelope that feeds the identifiability floor, and a
#: safety margin still at zero.  Both owe the physical/null
#: false-accept gate (HOLO-DESIGN §9.3; 07-placement.md:76-79).
BER_ENVELOPE: float = 0.08
SUPPORT_MARGIN_SITES: int = 0
#: The chain is deliberately SHORT-RANGE: paper hygroexpansion
#: (~0.3%/day) drifts about half a cell over one 160-cell window
#: stride, so a neighbour's prediction is trustworthy only within a
#: couple of cells -- radius 3 searched, 2-cell consistency gate.
NEIGHBOR_RADIUS_CELLS: int = 3
CONSISTENCY_CELLS: int = 2
LOCAL_HYPOTHESES: int = (2 * NEIGHBOR_RADIUS_CELLS + 1) ** 2
#: v1's donor-portfolio cap, now a truncation of a fire-time query:
#: sort by distance, keep 8, and let the caller subtract the tried
#: set (place_sched.untried_consult) -- what a window may ever try
#: is bounded by what it can see, not by how often it is woken.
CONSULT_KEEP: int = 8
#: The same 8 as CONSULT_KEEP, deliberately: one number governs both
#: portfolios.  In holo3 ring and wide see the SAME anchor set (every
#: placed window of the region, nearest first); what wide adds is the
#: regional affine, and the tried set is what makes it a new offer.
WIDE_ANCHORS: int = 8
WINDOW_CELLS: int = geometry.WINDOW_CELLS
WINDOW_STEP_CELLS: int = geometry.WINDOW_STEP_CELLS

ROUTE_CHAIN: str = "chain"
ROUTE_WORD: str = "word"
#: "correlation", not "cold": v1's own name for the tier, kept so a
#: route census reads one word across trees.  cold.py spells the same
#: string as a literal (it may not import place -- circular), so a
#: rename has to touch both.
ROUTE_COLD: str = "correlation"

STAGE_RING: str = "ring"
#: THE QUARTERING IS A RUNG (2026-09-21).  It used to be a side effect
#: inside the place-outcome FOLD, which minted the four children and
#: ingested them itself; as a stage it is evaluated at the POP like
#: every other rung, so a seed that arrived meanwhile is seen first
#: (`stage_of` answers RING before it answers this) and no fold
#: creates facts.  Its job reads no pixels.
STAGE_SUBDIVIDE: str = "subdivide"
STAGE_WORD_CENTRE: str = "word_centre"
STAGE_WORD_REST: str = "word_rest"
STAGE_WIDE: str = "wide"
STAGE_COLD_LIVE: str = "cold_live"
STAGE_COLD_REST: str = "cold_rest"
#: Contract §E's table, with one deliberate change: cold moved
#: 140/150 -> 250/260 on 2026-09-01 when the dryness gate was
#: deleted.  Cold is now last BY PRICE alone -- above swim (240) and
#: refine (200) -- and an idle worker takes the cheapest ready job.
#: SUBDIVIDE is priced AT THE RING, deliberately and without a
#: measurement: it is the one price this ladder gained when the
#: quartering became a rung (2026-09-21), it fires at most once per
#: window, and it costs microseconds -- so the honest thing is to
#: charge it what the cheapest real pass costs rather than invent a
#: number the mandate excludes.
STAGE_COST: dict[str, int] = {
    STAGE_RING: 40,
    STAGE_SUBDIVIDE: 40,
    STAGE_WORD_CENTRE: 60,
    STAGE_WORD_REST: 80,
    STAGE_WIDE: 120,
    STAGE_COLD_LIVE: 250,
    STAGE_COLD_REST: 260,
}
COLD_STAGES: tuple[str, str] = (STAGE_COLD_LIVE, STAGE_COLD_REST)
#: A TIE-BREAK, not a tier: coarse before fine WITHIN one stage.
#: The deepest real ladder is five rungs (4800 dpi c3 lays
#: 2/4/8/12/24), so the term spans 8, and 8 + CHILD_PREMIUM = 13 is
#: inside the smallest gap between two ordinary stages, 20.
LANE_COST_PER_RUNG: int = 2
#: Cold's rung term is a PRICE, not a tie-break: every other stage
#: does the same 49-hypothesis work at any rung, while a cold fire
#: pays a transform per page.  At 20 the pair nests -- rest(d)
#: 260+20d < live(d+1) 270+20d -- so a rung's colds drain first.
COLD_COST_PER_RUNG: int = 20
#: Ruling 2026-08-17: work on a subdivided window costs a tad more
#: than work on a whole one -- exhaust the sheet before specializing.
#: It STACKS on the rung term, and 8 + 5 = 13 stays inside one
#: inter-stage gap, so a child never outranks a cheaper whole window.
CHILD_PREMIUM: int = 5

#: The fitted terms ride IN the candidate id on purpose: the
#: least-squares affine moves as poses land, so a re-fitted one is
#: genuinely a new hypothesis, while an unchanged one is the same
#: trial and must not be re-priced past the tried set.
REGIONAL_SEED: str = "regional-affine"
#: Per-PAGE dedup, and since the page domain went dynamic, per
#: FLAVOUR too: live and rest price different floors, so a page
#: swept as rest deserves a live re-sweep at the lower one.  The
#: flavourless mark was sound only under one shared floor.
TRIED_COLD: str = "cold-page"

#: v1's order, kept, and since 2026-09-21 this set is the WHOLE of it
#: that a fold decides: a window whose own fit refused, and one whose
#: straddle audit refused an address it had already accepted, ARM the
#: rung and quarter with rungs still on the ladder.  Every other
#: refusal reaches the same rung the LAZY way -- through a spent
#: ladder -- and `insufficient_support` (too little paper) spends every
#: rung but a quartering one of these two had ALREADY armed (base ran
#: it inside that refusal's fold; review 2026-10-17 D1), so it never
#: reaches the rung lazily.  `stage_of` is the law; there is no second
#: predicate to keep in step with it.
SUBDIVISION_DIRECT: frozenset[str] = frozenset(
    {"pose_refused", "straddle_audit_refused"})
#: The `subdivide` rung's own outcome -- the parent is quartered.  It
#: is not a pass verdict: no pixels were read.
OUTCOME_SUBDIVIDED: str = "subdivided"


# e026's site-count law, ceil(log2 H / (1 - h2(BER))): a NECESSARY
# information bound on how many sites identify one address among H,
# not a family-wise false-accept certificate (HOLO-DESIGN §9.3).
# Exactly int(math.ceil(...)); np.rint and int(np.ceil()) differ.
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


# 49 hypotheses per candidate ever OFFERED, and nothing else.
# Folding Stage A's word domain in here was tried and withdrawn:
# two spent 147,456-phase stages cross the 250,530 knee where the
# floor steps 30 -> 31 and refuse a 30-site window v1 admits.
def pass_budget_hypotheses(tried: int, offered: int) -> int:
    return LOCAL_HYPOTHESES * max(1, int(tried) + int(offered))


def stage_price(stage: str, lane_depth: int, depth: int) -> int:
    rung = (COLD_COST_PER_RUNG if stage in COLD_STAGES
            else LANE_COST_PER_RUNG)
    return (STAGE_COST[stage] + rung * int(lane_depth)
            + (CHILD_PREMIUM if depth else 0))


# THE WHOLE LADDER, subdivision included (2026-09-21).  The two ways a
# window quarters are `v1`'s own order, and both are rungs here:
# ARMED, where a refusal of this window's own fit or of an address it
# had already accepted quarters at once with rungs still on the ladder,
# and LAZY, where correlation is exhausted first and the quartering is
# the last thing the window does.  RING outranks both, so a seed that
# arrived while the window waited is tried before it is cut up --
# which is the race that kept this decision out of the pass job.
def stage_of(offered: bool, centre_spent: bool, rest_spent: bool,
             wide_spent: bool, cold_armed: bool,
             cold_live_ready: bool, cold_live_spent: bool,
             cold_rest_ready: bool, cold_rest_spent: bool, *,
             subdivide_armed: bool, subdivide_ready: bool,
             support_refused: bool) -> str | None:
    if support_refused:
        return (STAGE_SUBDIVIDE if subdivide_armed and subdivide_ready
                else None)
    if offered:
        return STAGE_RING
    if subdivide_armed and subdivide_ready:
        return STAGE_SUBDIVIDE
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
    if subdivide_ready:
        return STAGE_SUBDIVIDE
    return None


#: Whether a quartering is possible AT ALL -- the depth cap and the
#: minimum window.  A window under the floor has no children to mint,
#: so the ladder must not offer it the rung: a spent sub-floor window
#: is spent, and `exhausted` is its terminal clause.
def subdividable(window: data.Window) -> bool:
    return bool(pose.subdivision_child_extents(window.extent_cells,
                                               window.depth))


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


# This is the WAKE relation, not the consult reach: _place_reads
# subscribes a window to these eight poses, while the consult ranks
# every placed window of the region.  Starts come from the region's
# own lattice, never from surviving plans (a dropped plan skews it).
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
            ordinal=ordinal,
            parent=window.window_id))
        ordinal += 1
    return tuple(out)


# THE HALF-CELL CONVENTION: these affines map page-cell EDGES to
# native pixels (v1 mapped cell centres), which is what the
# -linear @ (0.5, 0.5) term is for -- dropping it is a silent
# half-cell error everywhere downstream.  Rescale via exact Fraction.
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


# rot_k is RECOVERED, not carried: the four candidates are 90 apart,
# so the argmin is exact and a wrong pick simply fails the gates.
# The origin rounds half-to-even on purpose -- rot90 transport lands
# exact halves here (07-placement.md:138-142).
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


# ONE currency, no class prefix: centre-to-centre cells over the
# window stride, so an adjacent window scores 1.0 and a colocated
# coarser-rung donor 0.0 -- which is what lets a donor outrank a
# stride-distant neighbour with no class label to say so.
def hint_distance(source_centre_cells: tuple[float, float],
                  hinted_centre_cells: tuple[float, float],
                  stride_cells: float) -> float:
    return math.hypot(
        hinted_centre_cells[0] - source_centre_cells[0],
        hinted_centre_cells[1] - source_centre_cells[1],
    ) / float(stride_cells)


# Sorted on VALUES -- distance, then candidate id, then affine --
# never on arrival order, so neither worker count nor merge order can
# move a result.  Truncate here; the caller subtracts the tried set.
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


# ONE page per fit, and one pose per anchor: poses of different pages
# pool into a correspondence that exists nowhere, and a revised
# anchor that contributed its four corners twice double-weighted
# itself in the least squares (07-placement.md:540-542).
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


# The rival set is the other decoded candidates PLUS the winner's
# own origin on every OTHER page of the domain -- the cross-page
# alias population the word decode cannot see -- and both sides are
# scored whole-word (pose.WHOLE_WORD_PARITY holds the reason).
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


# A candidate that fails the coupled gates is one-way evidence --
# try the next one.  One that PASSES and then loses the rival bar
# refuses the whole word pass (return None): the rival set says this
# window's word evidence is ambiguous, not that this word is wrong.
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


# R5: the best-SUPPORTED window's seed wins, never the first to fire
# -- order independence is the whole point.  Production applies that
# through data.lattice_seed_ordinal in store_folds._fold_lattice_seed;
# this pair is read only by the placement test, and ties differ.
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
