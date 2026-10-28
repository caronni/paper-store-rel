"""The pull model's job: the ratified distance, the consult, and the ladder.

Split out of ``test_place_sched.py`` on 2026-08-17 under the cap-as-seam-
signal ruling (1000 lines marks a split-here point, never a budget to
squeeze prose against); the scheduler's own queue mechanics (admission,
the flag protocol, pricing and pings) moved to ``test_place_sched.py``.
This half keeps what a claimed job itself computes and the ladder that
drives it (the JOB's arithmetic is the carried kernel and is gated end to
end by the decode batteries — ``holo2/measure/``, the wall among them —
what is pinned here is the machinery the 2026-08-16 redesign introduced,
because a page-level gate cannot say which of these moved):

* **the lazy covered-exit**, including the never-posed-again law: a
  window whose area certified through NEIGHBOURS' poses retires and
  never returns. The admission-side refusal (a covered window never
  enters) is pinned in ``test_place_sched.py``; this is the OTHER exit;
* **the tried set and the floor it prices** — dedup by candidate at the
  job's own claim, and a declared domain that only ever grows (L7b);
* **the ratified distance** — the score the consult sorts by and the
  priority ranks on, whose two anchors (adjacent exactly 1.0, colocated
  exactly 0.0) are the ruling itself; it moved here with the functions
  when the hint family was deleted;
* **the wide tier's extra candidate** (ruling R-B, the regional affine);
* **the ladder itself, from the claim onward** (the last section): the
  covered exit's durable retirement, the word stage's if-and-only-if, the
  floor the pass threads into every gate, and one run of the whole climb
  into the wide tier — driven through the real scheduler and the real job
  with the PIXELS stubbed, which is the one boundary a unit fixture has.

The fake plane is ``test_placement``'s. The admitted-plane builders
(``_scheduler``, ``_pose``, ``_placed``, ``_priced``) and the
sparse/confetti gapped lattice (``_gapped``) are shared with
``test_place_sched.py`` and live in ``place_sched_support.py`` so neither
test module restates them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
import pytest

from holo2.capture import FootingFrame
from holo2.core import ProgressSink, WorkResult, Write
from holo2.solve import place_job, place_sched
from holo2.solve.geometry import WINDOW_STEP_CELLS
from holo2.solve.place_model import AffinePose
from holo2.solve.pose_audit import ScoreMemo
from holo2.solve.place_shared import Emission
from holo2.solve.place_sched import (TIER_WIDE,
                                     TIER_WORD_CENTRE, TIER_WORD_REST,
                                     PlacementScheduler)
from holo2.solve.placement import STAGE_CENTRE, STAGE_REST
from holo2.solve.records import PoseRecord, WindowStatus, pose_key, window_key
from conftest import FOOTING, REGION
from test_placement import (COARSE, PLAN_A, PLAN_B, ROW, WINDOW_A, WINDOW_B,
                            _Plane, _plan)
from place_sched_support import (AFFINE, FAR_C, FAR_D, FINE_LANE_TERM,
                                 _gapped, _placed, _pose, _priced, _scheduler)

# ------------------------------------------------------ the ratified distance
#
# The score itself, at the callable. It was ``hint_state``'s until the
# clean-slate sweep deleted that family and moved the two functions to
# ``place_job``, where the consult that sorts by them lives; these are
# that file's own anchor pins, carried over unchanged because the RULING
# they encode (user, 2026-08-16) did not move with the code.

def test_the_two_scoring_anchors_are_exact() -> None:
    """An adjacent window scores 1.0; a colocated donor scores 0.0.

    The ratified definition (H4-W2-PLAN item 4), asserted with ``==``
    because both anchors are exact in floating point: ``hypot(s, 0)`` is
    ``s`` and ``s / s`` is 1.0 for every finite stride, and a donor
    inherited at the same location differs from its target by nothing at
    all.
    """
    from holo2.solve.geometry import WINDOW_CELLS

    here = place_job.window_centre_cells(
        (0, 0, WINDOW_CELLS, WINDOW_CELLS))
    for axis in range(2):
        extent = [0, 0, WINDOW_CELLS, WINDOW_CELLS]
        extent[axis] += WINDOW_STEP_CELLS
        extent[axis + 2] += WINDOW_STEP_CELLS
        neighbour = place_job.window_centre_cells(
            (extent[0], extent[1], extent[2], extent[3]))
        assert place_job.hint_distance(
            neighbour, here, WINDOW_STEP_CELLS) == 1.0
        assert place_job.hint_distance(
            here, neighbour, WINDOW_STEP_CELLS) == 1.0

    # The cross-footing donor of item 6: a pose committed at a coarser
    # footing covers this window's extent exactly, so in the FINER
    # footing's cell frame the two centres coincide.
    assert place_job.hint_distance(here, here, WINDOW_STEP_CELLS) == 0.0


def test_the_score_is_one_currency_scaled_by_the_stride() -> None:
    """No class prefix: everything between the anchors is plain distance."""
    here = (0.0, 0.0)
    stride = float(WINDOW_STEP_CELLS)
    assert place_job.hint_distance(here, (0.0, 2 * stride), stride) == 2.0
    assert place_job.hint_distance(here, (0.0, stride / 2), stride) == 0.5
    assert place_job.hint_distance(
        here, (stride, stride), stride) == math.sqrt(2.0)
    # a donor at zero outranks every neighbour, which is the ruling's point
    assert place_job.hint_distance(here, here, stride) < \
        place_job.hint_distance(here, (0.0, stride), stride)


def test_the_score_refuses_a_stride_that_is_not_a_stride() -> None:
    for bad in (0.0, -160.0, math.nan):
        with pytest.raises(ValueError, match="stride_cells"):
            place_job.hint_distance((0.0, 0.0), (0.0, 1.0), bad)


# ------------------------------------------------ the job's own scheduling

def test_the_claim_hands_the_job_its_stage_and_its_tried_set() -> None:
    scheduler = _scheduler(_Plane())
    slot = scheduler._slots[WINDOW_A]
    slot.tried.add("pose/a")
    slot.centre_spent = True
    scheduler._enqueue(slot)
    job = scheduler.claim(_Plane(), WINDOW_A)
    assert job is not None
    assert job.stage == place_sched.STAGE_REST
    assert job._tried == frozenset({"pose/a"})
    assert job._words_spent == 1 and not job.wide


def test_the_wide_claim_spends_no_word_stage() -> None:
    scheduler = _scheduler(_Plane())
    slot = scheduler._slots[WINDOW_A]
    slot.centre_spent = slot.rest_spent = True
    scheduler._enqueue(slot)
    job = scheduler.claim(_Plane(), WINDOW_A)
    assert job is not None and job.wide and job.stage is None


def test_the_tried_set_grows_only_with_new_candidates() -> None:
    """Q1: dedup by candidate, because a repeated fire is one trial."""
    scheduler = _scheduler(_Plane())
    job = scheduler.claim(_Plane(), WINDOW_A)
    assert job is not None
    job.tried_now = ("pose/a", "pose/b")
    scheduler.settle(_Plane(), WINDOW_A, WorkResult(outcome="consult_refused"))
    assert scheduler._slots[WINDOW_A].tried == {"pose/a", "pose/b"}
    again = scheduler.claim(_Plane(), WINDOW_A)
    assert again is not None
    again.tried_now = ("pose/b", "pose/c")
    scheduler.settle(_Plane(), WINDOW_A, WorkResult(outcome="consult_refused"))
    assert scheduler._slots[WINDOW_A].tried == {"pose/a", "pose/b", "pose/c"}


# ------------------------------------------------------------- the consult

def test_the_consult_reads_the_committed_poses_around_this_window() -> None:
    """The pull, whole: no record, no retention, no staleness."""
    plane = _placed({}, WINDOW_B)
    seeds = place_job.consult(plane, PLAN_A, ROW)
    assert [seed.candidate_id for seed in seeds] == [
        str(pose_key(WINDOW_B, 0, AFFINE))]
    assert seeds[0].distance == 1.0 and seeds[0].affine == AFFINE
    assert seeds[0].page == 0
    assert not place_job.consult(_Plane(), PLAN_A, ROW), (
        "a window with no placed neighbour has nothing to try")


def test_the_consult_never_offers_a_quarantined_pose() -> None:
    """W5's never-return, in the pull model's own voice (ruling 2).

    v1 removes a condemned placement's continuation HINTS
    (``promoted_continuation_hints``, ``receive/place.py:1693``). The
    pull model has no hints to revoke, so the SAME consumer sits on the
    query that replaced them: the pose is retained as a record — the
    contradiction fact names it, and an audit can read it back — and it
    is never offered as a steer again.
    """
    plane = _placed({}, WINDOW_B)
    key = pose_key(WINDOW_B, 0, AFFINE)
    assert place_job.consult(plane, PLAN_A, ROW), "the fixture steers nothing"

    condemned = _Plane(records={key: replace(plane.record(key),
                                             quarantined=True)},
                       poses={WINDOW_B: (key,)})
    assert condemned.record(key) is not None, "the record is RETAINED"
    assert place_job.consult(condemned, PLAN_A, ROW) == ()
    # And page-wide, at the wide tier, which is the other reach a steer
    # can arrive by.
    assert place_job.consult(condemned, PLAN_A, ROW, wide=True) == ()
    assert place_job.regional_seed(condemned, PLAN_A, ROW) is None


def _crowded(count: int) -> tuple[_Plane, tuple[str, ...]]:
    """``count`` placed ANCHOR WINDOWS around ``PLAN_A``, one pose each.

    RE-PINNED W3 (2026-08-23, RULING I3). It used to be one neighbour
    carrying ``count`` distinct poses, which is no longer a way to make
    ``count`` candidates at all: the consult reads the LIVE pose of an
    anchor window and nothing else, so a window with twelve poses now
    offers exactly one seed (pinned below). The candidates are therefore
    twelve WINDOWS — ``PLAN_A``'s ring neighbour plus eleven coarse-lane
    donors whose extents contain it — which is the shape the truncation
    was always about.

    The donors' extents differ, so their centres do and their distances
    do: the sort is by (distance, candidate id) rather than by id alone.
    What makes the truncation observable is unchanged — the eight the
    consult keeps are a FUNCTION of what is visible, not of arrival.
    """
    donors = tuple(_plan(window_key(COARSE, REGION, (0, 0, 200, 200 + step)),
                         (0, 0, 200, 200 + step), footing=COARSE)
                   for step in range(count - 1))
    anchors = (PLAN_B, *donors)
    records: dict = {}
    poses: dict = {}
    for order, anchor in enumerate(anchors):
        affine = (6.0, 0.0, float(order), 0.0, 6.0, 2.0)
        record = PoseRecord(window_id=anchor.window_id,
                            footing_id=anchor.footing_id, page=0,
                            native_affine=affine)
        key = record.resource_key()
        records[key] = record
        poses[anchor.window_id] = (key,)
    plane = _Plane(records=records, plans=(PLAN_A, *anchors), poses=poses)
    return plane, tuple(str(poses[anchor.window_id][0]) for anchor in anchors)


def test_the_consult_truncates_before_the_tried_set_is_subtracted() -> None:
    """The ruling's own order: sort, keep 8, THEN subtract.

    Twelve candidates are visible and the consult keeps eight of them. A
    window that has tried those eight has nothing left to try — the
    portfolio it may ever try is bounded by WHAT IT CAN SEE, not by how
    often it has been woken. Subtract first and the same wake would hand
    it the four the truncation is supposed to have cut, every time.
    """
    plane, visible = _crowded(12)
    seeds = place_job.consult(plane, PLAN_A, ROW)
    kept = tuple(seed.candidate_id for seed in seeds)
    assert len(kept) == place_job.CONSULT_KEEP == 8
    assert set(kept) < set(visible), "twelve visible, eight kept"

    scheduler = _scheduler(plane)
    scheduler._slots[WINDOW_A].tried.update(kept)
    job = scheduler.claim(plane, WINDOW_A)
    assert job is not None and job._seeds(plane) == (), (
        "the four candidates the truncation cut came back as fresh ones")

    fresh = _scheduler(plane)
    fresh._slots[WINDOW_A].tried.update(kept[1:])
    offered = fresh.claim(plane, WINDOW_A)._seeds(plane)
    assert tuple(seed.candidate_id for seed in offered) == kept[:1], (
        "only the untried member of the KEPT eight is offered")


def test_a_revised_anchor_offers_ONE_seed_and_it_is_the_live_one() -> None:
    """Choice 8 at the consult (RULING I3, W3 2026-08-23).

    THE FORK: iterating ``poses_of_window``. An anchor RF1 has revised
    carries two committed poses, and offering both spends two of the
    eight ``CONSULT_KEEP`` slots on ONE neighbour and weights it twice in
    a ranking whose whole content is one prediction per nearby window.
    Worse, ``Seed.order_key`` breaks ties on the candidate id, so which
    of the two wins is an unpredictable property of the affine's DIGITS
    — in THIS fixture the revision happens to sort first, and a fixture
    one digit away would give the superseded parent the tie. The ruling
    removes the question rather than answering it (corrected by the W3
    review, 2026-08-23, which caught this docstring claiming the fixture
    demonstrated the opposite of what it asserts).

    The revision is committed second and is the one offered; the parent
    is still in the store, untouched, which is what a proposal-shaped
    revision means.
    """
    parent = _pose(WINDOW_B)
    revised = PoseRecord(window_id=WINDOW_B, footing_id=FOOTING, page=0,
                         native_affine=(6.0, 0.0, 0.5, 0.0, 6.0, 2.0))
    keys = (parent.resource_key(), revised.resource_key())
    assert keys[1] < keys[0], (
        "the fixture needs the revision to SORT FIRST, so 'last committed' "
        "and 'last by id' disagree")
    plane = _Plane(records={keys[0]: parent, keys[1]: revised},
                  poses={WINDOW_B: keys})
    seeds = place_job.consult(plane, PLAN_A, ROW)
    assert tuple(seed.candidate_id for seed in seeds) == (str(keys[1]),)
    assert seeds[0].affine == tuple(revised.native_affine)


def test_the_wide_consult_adds_the_regional_affine() -> None:
    """R-B: ONE extra candidate, fitted over the region's placed poses."""
    plane = _placed({}, WINDOW_B)
    assert place_job.regional_seed(plane, PLAN_A, ROW) is None, (
        "one pose IS its own affine; averaging it is not a second opinion")

    third = _plan(window_key(FOOTING, REGION, (0, 320, 200, 520)),
                  (0, 320, 200, 520))
    poses = {WINDOW_B: (pose_key(WINDOW_B, 0, AFFINE),),
             third.window_id: (pose_key(third.window_id, 0, AFFINE),)}
    two = _Plane(plans=(PLAN_A, PLAN_B, third),
                 records={key[0]: _pose(window)
                          for window, key in poses.items()},
                 poses=poses)
    seed = place_job.regional_seed(two, PLAN_A, ROW)
    assert seed is not None
    assert seed.candidate_id.startswith(place_job.REGIONAL_SEED)
    assert seed.page == 0 and math.isinf(seed.distance)
    assert len(seed.affine) == 6


# ------------------------------------------------------------- the floor

def test_the_floor_prices_the_cumulative_domain() -> None:
    """Q1/L7b: tried x 49 — and it only grows."""
    scheduler = PlacementScheduler(ROW)
    local = scheduler.budgets.local
    first = place_job.pass_budget(local, tried=0, offered=1, words_spent=0)
    assert first.max_hypotheses == local.max_hypotheses
    later = place_job.pass_budget(local, tried=3, offered=2, words_spent=1)
    # RE-DECLARED 2026-08-18 (v1 parity, user ruling): was
    # ``local.max_hypotheses * 5 + words``.  The Stage-A term is withdrawn,
    # so a spent word stage no longer moves the domain — the candidate
    # count is the whole of it.  It still RIDES the id.
    assert later.max_hypotheses == local.max_hypotheses * 5
    assert later.min_support >= first.min_support, "a floor never shrinks"
    assert "5-candidates-1-words" in later.qualification_id
    # a pass that offers nothing still declares a domain of at least one
    empty = place_job.pass_budget(local, tried=0, offered=0, words_spent=0)
    assert empty.max_hypotheses == local.max_hypotheses


# ------------------------------------------------- v1 parity, hand-derived
#
# The numbers below are derived BY HAND from ``src/holo`` and are never
# read back off holo2.  v1 declares its placement domain PER ROUTE, and
# the pooled pass budget replaces all of them at once, so parity has to
# hold on each:
#
#   the route budget itself   49 = (2 * neighbor_radius_cells + 1) ** 2,
#                             with r = 3 (``PlacementConfig``), which is
#                             ``PlacementBudgets.local.max_hypotheses``;
#   chain   ``holo/receive/place.py:217`` ``_chain_budget`` declares
#           ``per_anchor * n_anchors`` = ``49 * n_anchors``; its one
#           caller is ``place.py:195``, inside ``_chain_search``;
#   word    ``holo/receive/place.py:1344`` hands ``_word_route``
#           ``budgets.local`` UNMODIFIED, so the per-candidate scoring at
#           ``place.py:438`` runs at domain 49.  The Stage-A domain never
#           enters an ``AttemptBudget`` at all: ``holo/receive/words.py:78``
#           prices it as a single-word union bound against
#           ``familywise_false_accept``, a false-accept currency, not the
#           identifiability site count.
#
# and the floor off that domain is ``AttemptBudget.min_support``
# (``holo/receive/placement/model.py:172-180``):
#
#   max(HISTORICAL_MIN_SUPPORT = 30,                   (model.py:24)
#       ceil(log2(domain) / (1 - h2(0.08))) + margin)  (model.py:98-118)
#   h2(0.08) = 0.4021791902022728, so 1 - h2 = 0.5978208097977272, and
#   the provisional margin is 0 (``PROVISIONAL_SUPPORT_MARGIN_SITES``).
#     domain 49   -> ceil( 5.6147 / 0.5978208) = ceil( 9.39) = 10
#     domain 245  -> ceil( 7.9366 / 0.5978208) = ceil(13.28) = 14
#     domain 1960 -> ceil(10.9366 / 0.5978208) = ceil(18.29) = 19
#   -> max(30, 10) = max(30, 14) = max(30, 19) = 30.
#
# So v1's derived floor is 30 on EVERY route, with or without a word
# stage spent.  The identifiability term only overtakes 30 at a domain
# above 2 ** (30 * 0.5978208) = 250,530.
V1_LOCAL_HYPOTHESES = 49
V1_FLOOR_SITES = 30

#: The withdrawn deviation's own number, kept as the DISCRIMINATOR below:
#: W2's formula added ``147_456 * words_spent`` (the production Stage-A
#: domain, ``words.stage_a_hypotheses((200, 200))``), so a pass with both
#: word stages spent declared 294,961 — past the 250,530 knee, deriving
#: 31 where v1 derives 30.
WITHDRAWN_TWO_STAGE_DOMAIN = 49 + 147_456 * 2


def test_the_pass_budget_is_v1s_arithmetic_on_every_path() -> None:
    """PARITY (user ruling 2026-08-18, "we want parity to v1").

    Every path derives v1's 30, not 31: the domain is ``49 x candidates``
    and a spent word stage does not enter it.  The v1 values are the
    literals above, hand-derived from ``src/holo`` with citations.
    """
    scheduler = PlacementScheduler(ROW)
    local = scheduler.budgets.local
    assert local.max_hypotheses == V1_LOCAL_HYPOTHESES, (
        "the route budget itself is v1's (2r+1)**2")
    assert local.min_support == V1_FLOOR_SITES
    paths = {"no word stage": 0, "centre only": 1, "both stages": 2}
    for path, words_spent in paths.items():
        for candidates in (1, 5, 40):
            derived = place_job.pass_budget(
                local, tried=candidates - 1, offered=1,
                words_spent=words_spent)
            assert derived.max_hypotheses == (
                V1_LOCAL_HYPOTHESES * candidates), (
                f"path {path!r} at {candidates} candidates declares "
                f"{derived.max_hypotheses}; v1 declares "
                f"{V1_LOCAL_HYPOTHESES * candidates}")
            assert derived.min_support == V1_FLOOR_SITES, (
                f"path {path!r} at {candidates} candidates derives a floor "
                f"of {derived.min_support}; v1 derives {V1_FLOOR_SITES}")
    # And the withdrawn term's own domain is what 31 came from — so the
    # arithmetic above is not merely 30 by luck of the constants.
    assert replace(local, max_hypotheses=WITHDRAWN_TWO_STAGE_DOMAIN
                   ).min_support == 31


def _supported_at_exactly(sites_per_parity: int,
                          shape: tuple[int, int] = (16, 16)):
    """A page and a patch supported at EXACTLY ``sites_per_parity`` each.

    ``parity_mask`` at origin (0, 0) is ``(131*y + 17*x) & 1``, i.e. the
    two colours of the checkerboard, so a site count per parity is chosen
    by walking the grid and stopping each colour at its quota.  Every site
    carries value 0 against strictly positive evidence, so the weighted
    mismatch is exactly 0.0 and NOTHING but the support floor can decide
    the candidate.
    """
    values = np.zeros(shape, np.uint8)
    sites = np.zeros(shape, bool)
    taken = [0, 0]
    for y in range(shape[0]):
        for x in range(shape[1]):
            parity = (y * 131 + x * 17) & 1
            if taken[parity] == sites_per_parity:
                continue
            sites[y, x] = True
            taken[parity] += 1
    assert taken == [sites_per_parity, sites_per_parity], "grid too small"
    evidence = np.ones(shape, np.float32)
    bits = np.zeros(shape, np.uint8)
    mask = np.ones(shape, bool)
    return _ParityField(values, sites), evidence, bits, mask


class _ParityField:
    """The two arrays ``ScoreMemo`` reads off a reference-field provider."""

    def __init__(self, values: np.ndarray, sites: np.ndarray) -> None:
        self._page = _ParityPage(values, sites)

    def page(self, page: int) -> "_ParityPage":
        return self._page


@dataclass(frozen=True)
class _ParityPage:
    values: np.ndarray
    sites: np.ndarray


def test_a_window_supported_at_exactly_the_floor_is_admitted_on_every_path(
) -> None:
    """THE BOUNDARY (the review's flagged case), at 30 sites exactly.

    ``ScoreMemo.candidate`` compares ``support >= floor``, so a window
    supported at exactly ``E022_SUPPORT_FLOOR_SITES`` is the case that
    FLIPS between v1's 30 and the withdrawn 31.  It is admitted on all
    three paths here, and the last assertion shows the same window refused
    under the withdrawn arithmetic — the pin bites.
    """
    scheduler = PlacementScheduler(ROW)
    local = scheduler.budgets.local
    field, evidence, bits, mask = _supported_at_exactly(V1_FLOOR_SITES)
    memo = ScoreMemo(field)

    def score(budget):
        return memo.candidate(0, evidence, bits, mask, 0, (0, 0), 0,
                              budget, "word")

    for path, words_spent in (("no word stage", 0), ("centre only", 1),
                              ("both stages", 2)):
        budget = place_job.pass_budget(local, tried=0, offered=1,
                                       words_spent=words_spent)
        candidate = score(budget)
        assert candidate.search_support == V1_FLOOR_SITES
        assert candidate.validation_support == V1_FLOOR_SITES
        assert candidate.search_mismatch == 0.0
        assert candidate.passes, (
            f"a window supported at exactly {V1_FLOOR_SITES} sites — which "
            f"v1 admits on every route — was refused on path {path!r} at a "
            f"floor of {budget.min_support}")
    # THE DISCRIMINATOR: the identical window under the withdrawn W2
    # domain, whose floor is 31.  This is the behaviour the ruling removed.
    withdrawn = replace(local, max_hypotheses=WITHDRAWN_TWO_STAGE_DOMAIN)
    assert withdrawn.min_support == 31
    assert not score(withdrawn).passes


# --------------------------------------------- the job, from the claim on
#
# What follows drives the REAL ladder — the scheduler's claim, the job's
# own consult, its budget, its staging, its emission decision and its
# settle — with stubs at exactly ONE boundary: the PIXELS. A unit fixture
# has no raster, so ``sample_window`` and the two kernels that read a patch
# are answered here, and what they were HANDED is what these tests read.
# The arithmetic behind that boundary is pinned by ``test_pose_audit``,
# ``test_placement`` and the differential harness; the ladder that decides
# which of it runs is pinned nowhere else.

FRAME = AffinePose(origin_yx=(0.0, 0.0), jacobian_yx=((6.0, 0.0), (0.0, 6.0)),
                   phase_yx=(0.0, 0.0), pitch_px=6.0, angle_deg=0.0)


@dataclass(frozen=True)
class _Patch:
    """The two members the consult's prediction reads off a patch."""

    frame_pose: AffinePose = FRAME
    shape_yx: tuple[int, int] = (200, 200)


@dataclass(frozen=True)
class _Sample:
    """``sample_window``'s answer, minus the pixels.

    ``frame`` is the rung the sample was read on (H4-LANES stage 2): the
    NATIVE one here, because these doubles are about the ladder's pricing
    and staging rather than about lanes, and the native frame is the
    identity member of the type — every conversion it takes part in is a
    no-op by construction.
    """

    patch: object
    region: object = "prepared-region"
    refusal: str | None = None
    retire: bool = False
    seed_writes: tuple = ()
    frame: object = FootingFrame.native((1024, 1024))


@dataclass(frozen=True)
class _Found:
    origin_yx: tuple[int, int] = (3, 5)


@dataclass(frozen=True)
class _Outcome:
    accepted: bool
    best: object | None = None


@dataclass(frozen=True)
class _Placed:
    """``place_addressed``'s answer: the affine the pose record carries."""

    affine: tuple[float, ...] = AFFINE


@dataclass
class _Seen:
    """What the job handed each gate, in the order it handed them."""

    search: list = field(default_factory=list)
    word: list = field(default_factory=list)
    placed: list = field(default_factory=list)


def _stub_pixels(monkeypatch, *, search, word=None) -> _Seen:
    """Answer the pixel readers; record what the JOB priced them with."""
    seen = _Seen()
    patch = _Patch()

    def sample(view, plan, *, config, progress):
        return _Sample(patch)

    def local_search(patch_, page, rot_k, predicted, budget, memo, *,
                     sample_key, config, route):
        seen.search.append(budget)
        return search(len(seen.search) - 1)

    def decode(patch_, spec, row, *, stage, word_budget, budget, reference,
               progress, config=None, batched_sweep=False):
        seen.word.append((stage, budget))
        return word

    def place(region, patch_, *, page, page_origin_yx, rot_k, reference,
              config, budget, progress, frame=None):
        seen.placed.append(budget)
        return _Placed()

    monkeypatch.setattr(place_job, "sample_window", sample)
    monkeypatch.setattr(place_job.pose_audit, "local_search", local_search)
    monkeypatch.setattr(place_job, "decode_word_address", decode)
    monkeypatch.setattr(place_job, "place_addressed", place)
    monkeypatch.setattr(place_job, "emit_placement", _emit)
    return seen


def _emit(view, *, row, plan, pose, placement, provider, progress):
    """The emission block's answer: accepted, with the pose it was given."""
    return Emission("accepted", writes=(Write(pose.resource_key(), pose),))


def _run(job, plane) -> object:
    return job.run(plane, (), ProgressSink("unit"))


def test_a_covered_window_retires_durably_and_leaves_the_set(
        monkeypatch) -> None:
    """The LAZY covered-exit, asked at the fire and written down.

    The admission-side refusal (a covered window never enters) is pinned
    above; this is the other exit — a window that was already claimed
    when its whole extent certified through NEIGHBOURS' poses. It is
    asked before a pixel is read, it writes the window's own terminal
    outcome, and the record and the set membership move together.

    THIS IS ALSO THE REPLACEMENT FOR LATE BIRTH (pricing ruling,
    2026-08-17). The quiescent gate's stated point was that a finer
    window met the §6 done gate at CREATION time and was never created;
    with enumeration unconditional it is created early instead, so
    coverage has to catch it later — and it does, on a FINER-footing
    window (the lane term below is what says so), with no pose ever taken
    and exactly one write, the retirement.
    """
    scheduler = _scheduler(_Plane())
    assert scheduler._slots[WINDOW_A].price(place_sched.TIER_RING) == (
        place_sched.TIER_PRICE[place_sched.TIER_RING].cost + FINE_LANE_TERM), (
        "a finer-footing window, born before anything covered it")
    job = scheduler.claim(_Plane(), WINDOW_A)
    assert job is not None
    monkeypatch.setattr(place_job, "sample_window", _no_pixels)

    done = _Plane(done=True)
    result = _run(job, done)
    assert result.outcome == "done_covered" and result.retire
    (write,) = result.writes
    assert write.key == WINDOW_A
    assert write.record.status is WindowStatus.RETIRED
    assert write.record.retired_reason == "done_covered"

    scheduler.settle(done, WINDOW_A, result)
    assert WINDOW_A not in scheduler._slots
    assert scheduler._exited[WINDOW_A] == "done_covered"
    assert scheduler.counters()["retired"] == 1


def _no_pixels(view, plan, *, config, progress):
    raise AssertionError("the covered exit is asked BEFORE any pixel")


def test_the_word_stage_runs_only_when_the_consult_came_up_empty(
        monkeypatch) -> None:
    """Ladder step (d), which is the whole of what the staging is now.

    The scheduler hands a stage to every non-wide claim; whether it is
    SPENT is the job's own answer to "did the consult come up empty".
    A regression that spent it anyway would waste both word stages of
    every pinged window and still place the page — invisible in a route
    split, and expensive exactly where the ladder is cheap.
    """
    seen = _stub_pixels(monkeypatch, search=lambda index: _Outcome(False))

    steered = _placed({}, WINDOW_B)
    scheduler = _scheduler(steered)
    job = scheduler.claim(steered, WINDOW_A)
    assert job is not None and job.stage == STAGE_CENTRE
    result = _run(job, steered)
    assert not seen.word, "the consult had a seed; no word stage is owed"
    assert job.stage_spent is None and result.outcome == "consult_refused"
    assert len(seen.search) == 1, "the seed WAS searched"

    blind = _Plane()
    alone = _scheduler(blind)
    lone_job = alone.claim(blind, WINDOW_A)
    lone = _run(lone_job, blind)
    assert [stage for stage, _budget in seen.word] == [STAGE_CENTRE]
    assert lone_job.stage_spent == STAGE_CENTRE
    assert lone.outcome.startswith("no_word_candidate")
    assert len(seen.search) == 1, "an empty consult searches nothing"


def test_the_pass_carries_its_cumulative_floor_into_every_gate(
        monkeypatch) -> None:
    """Q1/L7b, THREADED: the budget the job computes is the one gates see.

    ``pass_budget`` is pinned in isolation above. What is pinned here is
    that ``run`` hands its OUTPUT — not the base budget it started from —
    to the seeded search, to the word decode and to the straddle audit.
    A regression to the base budget keeps the declared domain (and so the
    derived support floor) frozen as a window accumulates trials, which
    is the exact statistical honesty Q1 rules on, and every existing pin
    stays green.

    Since the 2026-08-18 parity ruling it also pins the OTHER direction at
    the word gate: a stage about to be spent moves the id and NOT the
    domain, so the derived floor is v1's on that path too.
    """
    seen = _stub_pixels(monkeypatch, search=lambda index: _Outcome(True,
                                                                   _Found()))
    base = PlacementScheduler(ROW).budgets.local

    steered = _placed({}, WINDOW_B)
    scheduler = _scheduler(steered)
    slot = scheduler._slots[WINDOW_A]
    slot.tried.update({"pose/x", "pose/y"})       # two trials already spent
    scheduler._enqueue(slot)
    job = scheduler.claim(steered, WINDOW_A)
    assert _run(job, steered).outcome == "accepted"
    priced = seen.search[0]
    assert priced.max_hypotheses == base.max_hypotheses * 3, (
        "two tried plus one offered is a three-candidate domain")
    assert "pull-3-candidates-0-words" in priced.qualification_id
    # The floor is DERIVED from that domain and never shrinks; at this
    # fixture's scale the E022 construction floor still dominates it, so
    # the domain is what this pin can state exactly.
    assert priced.min_support >= base.min_support
    assert seen.placed == [priced], "the audit gate is priced the same"

    blind = _Plane()
    alone = _scheduler(blind)
    alone._slots[WINDOW_A].tried.update({"pose/x", "pose/y"})
    _run(alone.claim(blind, WINDOW_A), blind)
    _stage, worded = seen.word[0]
    # RE-DECLARED 2026-08-18 (v1 parity, user ruling "we want parity to
    # v1"): was ``base.max_hypotheses * 2 + words``, the withdrawn Stage-A
    # term.  The THREADING this test exists for is unchanged and still
    # asserted — the word gate is handed the job's OUTPUT, two tried
    # candidates, not the base budget it started from.  What moved is the
    # stage's contribution: a word stage about to be spent no longer
    # prices the domain, it only rides the id, and the floor is v1's.
    assert worded.max_hypotheses == base.max_hypotheses * 2, (
        "the word gate carries the job's candidate count, not the base")
    assert "pull-2-candidates-1-words" in worded.qualification_id, (
        "the stage it is about to spend still RIDES the id")
    assert worded.min_support == base.min_support == V1_FLOOR_SITES


def test_the_ladder_climbs_to_the_wide_tier_and_the_regional_seed_places(
        monkeypatch) -> None:
    """R-B on the LIVE path: the gap-jumping case, end to end at unit scale.

    One window with an EMPTY ring (its only lattice neighbour is a start
    nothing sits on) and two placed windows two and three strides away —
    the sparse/confetti shape the wide tier exists for. The scheduler
    climbs the real ladder (word centre, word rest, then the gated wide
    tier), the wide claim's consult reaches page-wide as it must, R-B's
    regional affine is the extra candidate at the end of that portfolio,
    and an acceptance ON IT places the window and takes it out of the
    set. Everything here is the shipped code except the pixels.
    """
    plane = _gapped(FAR_C, FAR_D)
    scheduler = _scheduler(plane)
    assert set(scheduler._slots) == {WINDOW_A}, "the placed two never enter"
    assert scheduler._slots[WINDOW_A].offered is None, (
        "an empty ring offers nothing, however much the region holds")

    seen = _stub_pixels(monkeypatch, search=lambda index: _Outcome(False))
    for tier, stage in ((TIER_WORD_CENTRE, STAGE_CENTRE),
                        (TIER_WORD_REST, STAGE_REST)):
        head = scheduler.peek()
        assert head is not None and head.cost == _priced(tier)
        assert not head.gated, "the word tiers compete with everything"
        word_job = scheduler.claim(plane, WINDOW_A)
        assert word_job is not None and not word_job.wide
        result = _run(word_job, plane)
        assert word_job.stage_spent == stage and not seen.search
        scheduler.settle(plane, WINDOW_A, result)

    head = scheduler.peek()
    assert head is not None and head.cost == _priced(TIER_WIDE)
    assert head.gated, "wide waits for everything cheaper, payload included"
    job = scheduler.claim(plane, WINDOW_A)
    assert job is not None and job.wide and job.stage is None

    def accept_the_regional(index: int):
        candidate = job.tried_now[index]
        return _Outcome(candidate.startswith(place_job.REGIONAL_SEED), _Found())

    seen = _stub_pixels(monkeypatch, search=accept_the_regional)
    result = _run(job, plane)

    tried = job.tried_now
    assert len(tried) == 3 <= place_job.WIDE_ANCHORS
    assert tried[:2] == tuple(str(pose_key(window, 0, AFFINE))
                              for window in (FAR_C, FAR_D)), (
        "the wide consult reaches the anchors the ring cannot see, nearest "
        "first")
    assert tried[2].startswith(place_job.REGIONAL_SEED), "R-B's one extra"
    assert len(seen.search) == 3, "the portfolio is tried in that order"
    assert result.outcome == "accepted"
    assert job.route_taken == place_job.ROUTE_CONSULT

    scheduler.settle(plane, WINDOW_A, result)
    assert scheduler._exited[WINDOW_A] == "placed" and not scheduler._slots
