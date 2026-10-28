"""The placement family's DECISIONS, localised (H4 W1, W2).

The ROUTE is gated end to end in ``holo2/measure/verdicts/`` (where a real
generator may be imported and a real page rendered). What is pinned here
is everything that is a DECISION rather than arithmetic, because a
page-level gate cannot say which of them moved:

* R5's transition law — a lattice seed is replaced only by a
  better-supported source, and the tie-break is a value, not a schedule;
* the shared emission block: which records one accepted placement
  proposes, that a tile's LLRs are its own cells' (the slicing that
  would otherwise be invisible until a certificate came back wrong), and
  — since the pull model — that it writes NO scheduling state at all;
* **the ring/donor geometry and the frame bridge** — ``place_shared``'s
  other half, which package 2 built for the push and pinned in
  ``test_place_chain.py``. The clean-slate sweep deleted that route and
  its file; the geometry outlived both, because the two questions it
  answers (who does an acceptance PING, whose frame may a window
  INHERIT) are the pull model's consult and ping.

This file also owns the ``_Plane`` fake the scheduling pins read through
(``test_place_sched``), which is why its window plans live here.

The carried arithmetic itself (fit, sample, Stage A, gate, audit) used to
be pinned by ``test_differential_placement.py`` against ``src/holo``; that
harness is history — deleted with the measure cleanup — and the route's
end-to-end gate is now ``holo2/measure/verdicts/`` (v1 parity + the
seeded verdict). The two-spends-per-window staging
this file used to pin is GONE with the descriptor routes (H4 W2, ruling
Q2): the stage memory is the scheduler's, and its pins are its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo2.capture import FootingFrame
from holo2.core import CommitRefusal, ProgressSink, ResourceKey
from holo2.core.commit import CommitBatch, CommitEngine, Write
from holo2.core.store import Store
from holo2.format.registry_rows import tile_format_for
from holo2.solve import place_job, placement, place_shared
from holo2.solve.geometry import (WINDOW_CELLS, WINDOW_STEP_CELLS,
                                  window_starts)
from holo2.solve.lattice_seed import (LatticeSeedRecord, lattice_seed_key,
                                      seed_rank, supersedes)
from holo2.solve.place_model import AffinePose
from holo2.solve.plans import WindowPlan
from holo2.solve.records import (KIND_CALIBRATION, KIND_EVIDENCE, KIND_POSE,
                                 KIND_TILE, PoseRecord, TileRecord,
                                 parse_evidence_key, unpack_observed_cells,
                                 window_key)
from holo2.solve.reference import V1ReferenceField
from holo2.solve.tilemap import StoreIndex
from holo2.format.registry_rows import format_row
from conftest import (CAPTURE_SHA, FOOTING, REGION, make_session, registry)

#: One printed row is all a placement worker needs of the format; a 2x2
#: tile page keeps the reference field small enough to assert over.
ROW = format_row("c2-k-r0700", (2, 2))
SPEC = tile_format_for(ROW)

WINDOW_A = window_key(FOOTING, REGION, (0, 0, 200, 200))
WINDOW_B = window_key(FOOTING, REGION, (0, 160, 200, 360))
COARSE = "cap:2/1"


def _plan(window_id: ResourceKey, extent: tuple[int, int, int, int], *,
          footing: str = FOOTING, supported: int = 40_000) -> WindowPlan:
    return WindowPlan(window_id=window_id, footing_id=footing,
                      region_id=REGION, capture_sha256=CAPTURE_SHA,
                      extent_cells=extent, supported_cells=supported)


PLAN_A = _plan(WINDOW_A, (0, 0, 200, 200))
PLAN_B = _plan(WINDOW_B, (0, 160, 200, 360), supported=30_000)


@dataclass(frozen=True)
class _Footing:
    footing_id: str
    ppc: Fraction
    capture_sha256: str


@dataclass(frozen=True)
class _Lattice:
    """What the ring geometry and the regional fit read of a lattice.

    ``geometry.CellLattice``'s two accessors, verbatim: the regional
    affine (R-B) needs cell centres in native pixels, and a fake that
    answered them differently would fit a different page.
    """

    shape_cells: tuple[int, int]
    pitch_px: float = 6.0
    origin_yx: tuple[float, float] = (0.0, 0.0)

    def centres_y(self, cy0: int, cy1: int) -> np.ndarray:
        return self.origin_yx[0] + self.pitch_px * (np.arange(cy0, cy1) + 0.5)

    def centres_x(self, cx0: int, cx1: int) -> np.ndarray:
        return self.origin_yx[1] + self.pitch_px * (np.arange(cx0, cx1) + 0.5)


@dataclass(frozen=True)
class _RegionView:
    """The region as the ring enumeration sees it.

    (200, 360) cells is the lattice PLAN_A and PLAN_B come off:
    ``window_starts`` lays one start on y and two on x (0 and 160, the
    second flush against the far edge), which is exactly their extents.

    ``support`` joined at W3: subdivision counts a child's supported
    cells on the region's own grid, exactly as ``plans.window_plans_for``
    counts a laid-out window's. Fully supported, which is what every
    scenario in this file already assumes of its plans.
    """

    lattice: _Lattice = _Lattice((200, 360))
    schedulable: bool = True
    support: np.ndarray = field(
        default_factory=lambda: np.ones((200, 360), bool))


class _Plane:
    """Exactly the ``PlaneView`` reads these decisions make, and no more."""

    def __init__(self, *, records: dict[ResourceKey, object] | None = None,
                 plans: tuple[WindowPlan, ...] = (PLAN_A, PLAN_B),
                 shape_cells: tuple[int, int] = (200, 360),
                 raster: object | None = object(), done: bool = False,
                 prepared: object | None = None,
                 poses: dict[ResourceKey, tuple] | None = None,
                 read_poses: tuple[ResourceKey, ...] = ()) -> None:
        self._records = dict(records or {})
        self._plans = plans
        self._shape = shape_cells
        self._raster = raster
        #: The SECOND pixel source (2026-08-17): a prepared plane already
        #: on disk. Absent by default, so a ``raster=None`` double still
        #: means "no pixels at all", which is what M12's admission tests
        #: have always been about.
        self._prepared = prepared
        self._done = done
        self._poses = poses or {}
        #: WHICH POSES OWN EVIDENCE (F2a, 2026-08-23), the arrow
        #: ``StoreIndex.evidence_by_pose`` maintains and the re-read
        #: door asks. EMPTY by default and deliberately so: every scenario in
        #: this suite that hands in poses is about SCHEDULING, and the
        #: re-read is offered only where one generation has been read and
        #: a newer one has not — a shape a test states on purpose.
        self._read_poses = frozenset(read_poses)
        self.footings = (_Footing(FOOTING, Fraction(8), CAPTURE_SHA),
                         _Footing(COARSE, Fraction(2), CAPTURE_SHA))

    def region(self, region_id: ResourceKey) -> _RegionView:
        return _RegionView(_Lattice(self._shape),
                           support=np.ones(self._shape, bool))

    # the frontier
    def footing_ids(self, selector: str) -> tuple[str, ...]:
        if selector == "coarsest":
            return (COARSE,)
        return tuple(sorted(footing.footing_id for footing in self.footings))

    def footing(self, footing_id: str) -> _Footing:
        return next(item for item in self.footings
                    if item.footing_id == footing_id)

    def footing_depth(self, footing_id: str) -> int:
        # ``SessionPlane.footing_depth``'s rule over this double's own
        # two-rung ladder: the index of the footing's ppc among the
        # capture's, coarsest first (H4-LANES stage 2's lane term).
        ladder = sorted({item.ppc for item in self.footings})
        return ladder.index(self.footing(footing_id).ppc)

    def footing_frame(self, footing_id: str) -> FootingFrame:
        # These decisions are about scheduling and emission, never about
        # pixels, so every lane answers the IDENTITY frame: it is the one
        # value under which the pose composition is provably a no-op, and
        # the frame arithmetic has its own tests
        # (``test_pose_frames.py``).
        return FootingFrame.native((4096, 4096))

    def window_plans(self, footing_id: str) -> tuple[WindowPlan, ...]:
        return tuple(plan for plan in self._plans
                     if plan.footing_id == footing_id)

    # the facts
    def record(self, key: ResourceKey) -> object | None:
        return self._records.get(key)

    def poses_of_window(self, window_id: ResourceKey) -> tuple:
        return self._poses.get(window_id, ())

    def index(self) -> StoreIndex:
        """The pose index W4's cold offer derives its LIVE PAGES from.

        Derived from this double's own two maps rather than stored beside
        them, so a test that hands in poses gets a consistent index for
        free and cannot set up a window map and an index that disagree.
        It is the same relation the real ``StoreIndex`` holds — the
        by-window view and the record map are two readings of one commit.

        ``live_poses`` is derived the same way (tilemap choice 8, W3
        2026-08-23): the LAST pose id this double was handed for a window
        is that window's live one, which is what a test that lists poses
        in commit order means by the order it wrote them in.
        """
        return StoreIndex(
            poses={
                pose_id: record
                for pose_ids in self._poses.values()
                for pose_id in pose_ids
                if isinstance(record := self._records.get(pose_id),
                              PoseRecord)},
            poses_by_window={window_id: tuple(pose_ids)
                             for window_id, pose_ids in self._poses.items()},
            evidence_by_pose={pose: () for pose in
                              sorted(self._read_poses)},
            live_poses={window_id: pose_ids[-1]
                        for window_id, pose_ids in self._poses.items()
                        if pose_ids})

    def window_is_done(self, plan: WindowPlan) -> bool:
        return self._done

    def has_region(self, region_id: ResourceKey) -> bool:
        return True

    def has_footing(self, footing_id: str) -> bool:
        return True

    def raster(self, capture_sha256: str) -> object | None:
        return self._raster

    def has_footing_pixels(self, footing_id: str) -> bool:
        # H4-LANES stage 1: the gate asks per RUNG. This double declares
        # one capture whose pixels are attached or not as a whole, which
        # is what every one of its scenarios is about, so the answer is
        # the raster's for every footing it holds.
        return self._raster is not None

    def prepared_region(self, region: object, *, config: object,
                        footing_id: str | None = None) -> object:
        return self._prepared


# ------------------------------------------------------- R5's transition law

def _seed(support: int, window: ResourceKey,
          rows=(0.25, 0.0, 0.0, 0.25)) -> LatticeSeedRecord:
    return LatticeSeedRecord(footing_id=FOOTING, region_id=REGION, rows=rows,
                             source_window_id=window,
                             source_support_cells=support)


def test_a_better_supported_source_supersedes_the_standing_seed() -> None:
    assert supersedes(_seed(200, WINDOW_B), _seed(100, WINDOW_A))
    assert not supersedes(_seed(100, WINDOW_A), _seed(200, WINDOW_B))
    assert supersedes(_seed(100, WINDOW_A), None)


def test_the_seed_tie_break_is_a_value_not_a_schedule() -> None:
    """Equal support: v1's own wave-front key, so the answer is the window."""
    assert seed_rank(100, WINDOW_A) < seed_rank(100, WINDOW_B) or (
        seed_rank(100, WINDOW_B) < seed_rank(100, WINDOW_A))
    smaller, larger = sorted((WINDOW_A, WINDOW_B))
    assert supersedes(_seed(100, smaller), _seed(100, larger))
    assert not supersedes(_seed(100, larger), _seed(100, smaller))
    assert seed_rank(100, WINDOW_A) > seed_rank(101, WINDOW_A), (
        "support dominates the tie-break")


def test_the_wall_refuses_a_worse_supported_seed(tmp_path: Path) -> None:
    """The invariant is the FACT's, not its writer's (F-08's discipline)."""
    from conftest import ground

    store = Store.create(tmp_path / "state", make_session(), registry())
    engine = CommitEngine(store)
    ground(engine, "region")
    key = lattice_seed_key(FOOTING, REGION)
    engine.apply(CommitBatch(writes=(Write(key, _seed(200, WINDOW_B)),)))
    assert store.get(key).source_support_cells == 200
    engine.apply(CommitBatch(writes=(Write(key, _seed(200, WINDOW_B)),)))
    with pytest.raises(CommitRefusal, match="better-supported"):
        engine.apply(CommitBatch(writes=(Write(key, _seed(100, WINDOW_A)),)))
    engine.apply(CommitBatch(writes=(Write(key, _seed(400, WINDOW_A)),)))
    assert store.get(key).source_support_cells == 400
    store.close()


# ------------------------------------------------------- the emission block

def _reference_placement(origin_yx=(0, 0), shape=(128, 128), rot_k=0,
                         affine=(4.0, 0.0, 1.0, 0.0, 4.0, 2.0)):
    """A synthetic accepted placement whose scores ARE the printed field.

    Ink sites score 1.0 and paper sites 0.0, which is the separable case:
    what is under test is the plumbing (which cells reach which tile,
    which records get written), not the detector.
    """
    field = V1ReferenceField(SPEC)
    page = field.page(0)
    scores = np.zeros(shape, np.float64)
    height, width = shape
    origin_y, origin_x = origin_yx
    for i in range(height):
        for j in range(width):
            y, x = origin_y + i, origin_x + j
            if 0 <= y < page.values.shape[0] and 0 <= x < page.values.shape[1]:
                scores[i, j] = float(page.values[y, x])
    scores = np.rot90(scores, -rot_k)
    return field, place_shared.AcceptedPlacement(
        page=0, rot_k=rot_k, page_origin_yx=origin_yx, scores=scores,
        observed=np.ones(scores.shape, bool), affine=affine)


def _emit(placement_, field, view=None, plan: WindowPlan = PLAN_A):
    pose = PoseRecord(window_id=plan.window_id, footing_id=FOOTING, page=0,
                      native_affine=placement_.affine)
    return pose, place_shared.emit_placement(
        view or _Plane(), row=ROW, plan=plan, pose=pose,
        placement=placement_, provider=field, progress=ProgressSink("unit"))


def test_one_accepted_placement_writes_the_records_payload_consumes() -> None:
    """The emission's shape is the payload family's input contract."""
    field, placed = _reference_placement()
    pose, emission = _emit(placed, field)
    assert emission.accepted and emission.tiles == 4
    kinds = [write.key.kind for write in emission.writes]
    assert kinds.count(KIND_CALIBRATION) == 1
    assert kinds.count(KIND_POSE) == 1
    assert kinds.count(KIND_EVIDENCE) == 4        # one piece per tile
    assert kinds.count(KIND_TILE) == 4
    calibration = next(write.record for write in emission.writes
                       if write.key.kind == KIND_CALIBRATION)
    assert calibration.algorithm == place_shared.CALIBRATION_ALGORITHM
    assert calibration.heldout.adopted
    assert calibration.scope == WINDOW_A
    for write in emission.writes:
        if write.key.kind != KIND_EVIDENCE:
            continue
        assert write.record.pose_id == pose.resource_key()
        assert write.record.calibration_id == calibration.resource_key()
        assert write.record.footing_id == FOOTING
        assert write.record.stream == ROW.stream_ids[0]
    for write in emission.writes:
        if write.key.kind == KIND_TILE:
            assert isinstance(write.record, TileRecord)
            assert write.record.observed_by == (FOOTING,)
            assert not write.record.certified


def test_an_acceptance_pushes_nothing_at_its_neighbours() -> None:
    """H4 W2: hints are dead, and the emission block is where they died.

    Package 2 made every acceptance write a ``HintState`` at each ring
    neighbour, in this very batch. The pull model deleted the record and
    kept the question: a window consults the committed poses around it at
    fire time, and what an acceptance offers its neighbours is a FLAG the
    scheduler sets after this batch commits. So the emission's writes are
    facts and nothing else — no scheduling state crosses the wall.

    Asserted as a WHITELIST rather than against the dead kind's name: the
    hint family is gone from the registry (the clean-slate sweep), so
    ``"hint" not in kinds`` would be a test that can no longer fail. What
    can still go wrong is a future route smuggling some OTHER scheduling
    record in beside the evidence, and that is what this refuses.
    """
    from holo2.solve.records import KIND_WINDOW

    field, placed = _reference_placement()
    _pose, emission = _emit(placed, field)
    assert emission.accepted
    kinds = {write.key.kind for write in emission.writes}
    assert kinds <= {KIND_TILE, KIND_EVIDENCE, KIND_CALIBRATION, KIND_POSE}, (
        "the emission writes facts: tiles, evidence, its calibration — a "
        "scheduling annotation is not one of them (H4 W2)")
    assert KIND_WINDOW not in kinds, (
        "the window's own outcome record is the JOB's write, not the "
        "emission's — this block emits evidence")


@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_every_tile_gets_its_own_cells(rot_k: int) -> None:
    """The slicing, pinned where a certificate would otherwise catch it.

    A tile's stored LLRs must be the tile's OWN cells under this pose,
    at every orientation: positive where the printed field says ink,
    negative where it says paper. A transposed or off-by-one slice
    survives every other assertion in this file.
    """
    field, placed = _reference_placement(rot_k=rot_k)
    _pose, emission = _emit(placed, field)
    blobs = {blob.ref.sha256: blob for blob in emission.blobs}
    page = field.page(0)
    seen = 0
    for write in emission.writes:
        if write.key.kind != KIND_EVIDENCE:
            continue
        _f, _p, ty, tx, _s, _pose_id = parse_evidence_key(write.key)
        llr = np.frombuffer(blobs[write.record.llr_ref.sha256].payload,
                            np.float32).reshape(64, 64)
        sites = page.sites[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
        values = page.values[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
        ink = sites & (values > 0)
        paper = sites & (values == 0)
        assert (llr[ink] > 0).all(), f"tile {(ty, tx)} ink LLRs"
        assert (llr[paper] < 0).all(), f"tile {(ty, tx)} paper LLRs"
        seen += 1
    assert seen == 4


def test_a_partly_observed_tile_carries_its_mask_and_nothing_else() -> None:
    """§5.4: unobserved is not the same fact as observed-with-zero-LLR."""
    field, placed = _reference_placement(shape=(128, 128))
    observed = np.zeros(placed.observed.shape, bool)
    observed[:100, :100] = True                   # tile (1,1) only partly seen
    partial = place_shared.AcceptedPlacement(
        page=placed.page, rot_k=placed.rot_k,
        page_origin_yx=placed.page_origin_yx, scores=placed.scores,
        observed=observed, affine=placed.affine)
    _pose, emission = _emit(partial, field)
    blobs = {blob.ref.sha256: blob for blob in emission.blobs}
    masks = {}
    for write in emission.writes:
        if write.key.kind != KIND_EVIDENCE:
            continue
        _f, _p, ty, tx, _s, _pid = parse_evidence_key(write.key)
        mask = unpack_observed_cells(
            np.frombuffer(blobs[write.record.observed_ref.sha256].payload,
                          np.uint8), (64, 64))
        llr = np.frombuffer(blobs[write.record.llr_ref.sha256].payload,
                            np.float32).reshape(64, 64)
        assert not (llr[~mask] != 0).any(), "an unobserved cell has no evidence"
        masks[(ty, tx)] = mask
    assert masks[(0, 0)].all(), "the wholly observed tile"
    assert masks[(1, 1)].sum() == 36 * 36, "the corner the mask kept"
    assert not masks[(1, 1)][36:, :].any()


def test_an_unlabelled_placement_refuses_instead_of_writing() -> None:
    """No labels, no calibration, no evidence — and a countable reason."""
    field, placed = _reference_placement(origin_yx=(4096, 4096))
    _pose, emission = _emit(placed, field)
    assert emission.outcome == "no_labels"
    assert not emission.writes and not emission.blobs


def test_the_evidence_of_two_windows_shares_one_tile_by_key() -> None:
    """Two poses, one work key: the payload side's merge is the point."""
    field, first = _reference_placement(origin_yx=(0, 0), shape=(128, 128))
    _pose_a, one = _emit(first, field)
    _field, second = _reference_placement(
        origin_yx=(32, 32), shape=(96, 96),
        affine=(4.0, 0.0, 129.0, 0.0, 4.0, 130.0))
    _pose_b, two = _emit(second, field)
    keys = {write.key for write in one.writes if write.key.kind == KIND_TILE}
    assert keys & {write.key for write in two.writes
                   if write.key.kind == KIND_TILE}
    evidence_a = {write.key for write in one.writes
                  if write.key.kind == KIND_EVIDENCE}
    evidence_b = {write.key for write in two.writes
                  if write.key.kind == KIND_EVIDENCE}
    assert not (evidence_a & evidence_b), (
        "one pose, one piece per tile — the pose is IN the evidence key")


# ---------------------------------------------------------- the frame bridge

def test_the_page_frame_inverts_the_rotation_and_the_half_cell() -> None:
    """``page_affine_terms`` against its own definition, at every rot90.

    A pose maps window-local cell INDEX to native pixels; the returned
    affine maps page-cell EDGE coordinates. So for every local cell, the
    page cell it occupies must map back to the same pixel — plus the half
    cell that turns an edge into a centre.
    """
    from holo2.solve.reference import rotation_affine

    pose = AffinePose((100.0, 200.0), ((4.0, 0.1), (-0.1, 4.0)), (0.5, 0.5),
                      4.0, 0.0)
    shape, origin = (37, 53), (7, 11)
    for rot_k in range(4):
        terms = place_shared.page_affine_terms(pose, shape, rot_k, origin)
        matrix = np.asarray(terms, np.float64).reshape(2, 3)
        rotation, translation = rotation_affine(rot_k, shape)
        for local in ((0, 0), (1, 0), (0, 1), (36, 52)):
            page = rotation @ np.asarray(local, np.float64) + translation \
                + np.asarray(origin, np.float64)
            edge = np.array([page[0] + 0.5, page[1] + 0.5, 1.0])
            got = np.array([matrix[0] @ edge, matrix[1] @ edge])
            want = pose.points(np.asarray([local], np.float64))[0]
            assert np.allclose(got, want, atol=1e-9), (rot_k, local)


# ------------------------------------------------ the ring/donor geometry
#
# Package 2 built this geometry for the PUSH and pinned it in
# ``test_place_chain.py``; the clean-slate sweep deleted that route and
# its file, and the geometry stayed — ``ring_targets`` + ``donor_targets``
# say who an acceptance PINGS (``place_sched``), ``ring_targets`` +
# ``donor_sources`` say who a consulting window may inherit a frame FROM
# (``place_job``). One implementation, two voices, and these are its pins.
#
# A 545-cell axis is the flush shift's own example (``window_starts``):
# starts 0 / 160 / 320 / 345, so the LAST step is 25 cells, not 160.

FLUSH_ROWS, FLUSH_COLS = 545, 360


def _lattice_plans(rows: int, cols: int, *,
                   footing: str = FOOTING) -> tuple[WindowPlan, ...]:
    """Every window ``plans.window_plans_for`` would lay on one lattice."""
    return tuple(
        _plan(window_key(footing, REGION,
                         (cy0, cx0, min(rows, cy0 + WINDOW_CELLS),
                          min(cols, cx0 + WINDOW_CELLS))),
              (cy0, cx0, min(rows, cy0 + WINDOW_CELLS),
               min(cols, cx0 + WINDOW_CELLS)), footing=footing)
        for cy0 in window_starts(rows) for cx0 in window_starts(cols))


def _flush_plane(plans=None) -> _Plane:
    return _Plane(plans=plans if plans is not None
                  else _lattice_plans(FLUSH_ROWS, FLUSH_COLS),
                  shape_cells=(FLUSH_ROWS, FLUSH_COLS))


def test_an_interior_window_sees_all_eight_neighbours() -> None:
    plans = _lattice_plans(FLUSH_ROWS, FLUSH_COLS)
    here = next(plan for plan in plans if plan.extent_cells[:2] == (160, 0))
    ring = place_shared.ring_targets(_flush_plane(plans), here)
    # starts are (0, 160, 320, 345) x (0, 160): this window has neighbours
    # on both y sides and one x side — five, and the missing ones are off
    # the lattice, not dropped.
    assert {plan.extent_cells[:2] for plan in ring} == {
        (0, 0), (0, 160), (160, 160), (320, 0), (320, 160)}
    assert here not in ring


def test_a_corner_window_has_the_three_neighbours_it_has() -> None:
    plans = _lattice_plans(FLUSH_ROWS, FLUSH_COLS)
    corner = next(plan for plan in plans if plan.extent_cells[:2] == (0, 0))
    ring = place_shared.ring_targets(_flush_plane(plans), corner)
    assert {plan.extent_cells[:2] for plan in ring} == {
        (0, 160), (160, 0), (160, 160)}


def test_the_flush_shifted_edge_makes_a_ring_asymmetric() -> None:
    """THE edge case: membership is by lattice INDEX, distance is not.

    ``window_starts(545)`` ends 320, 345 — the last window is pulled in so
    it finishes flush against the far edge, so the edge window sits 25
    cells from its predecessor and 185 from the one before that. It is
    still exactly one step away in the lattice (so it IS in the ring), and
    the ratified score says how near it really is, which is the entire
    reason that score is a distance and not a class.
    """
    assert window_starts(FLUSH_ROWS) == (0, 160, 320, 345)
    plans = _lattice_plans(FLUSH_ROWS, FLUSH_COLS)
    edge = next(plan for plan in plans if plan.extent_cells[:2] == (345, 0))
    ring = place_shared.ring_targets(_flush_plane(plans), edge)
    assert {plan.extent_cells[:2] for plan in ring} == {
        (320, 0), (320, 160), (345, 160)}
    here = place_job.window_centre_cells(edge.extent_cells)
    distances = sorted(place_job.hint_distance(
        place_job.window_centre_cells(plan.extent_cells), here,
        float(WINDOW_STEP_CELLS)) for plan in ring)
    assert distances[0] == pytest.approx(25.0 / WINDOW_STEP_CELLS)
    assert distances[1] == 1.0, "the x neighbour is a whole stride away"
    assert distances[0] < 1.0 < distances[2], (
        "the flush neighbour is nearer than a stride and the diagonal one "
        "further — asymmetric across ONE ring, and scored as such")


def test_a_window_the_region_never_planned_is_not_in_any_ring() -> None:
    """The ring is the LATTICE's, so a dropped window leaves a hole.

    Deriving neighbours from the surviving plans instead would promote
    the window two steps away to "immediate" — a silently longer reach
    exactly where support is thin.
    """
    plans = tuple(plan for plan in _lattice_plans(FLUSH_ROWS, FLUSH_COLS)
                  if plan.extent_cells[:2] != (160, 160))
    here = next(plan for plan in plans if plan.extent_cells[:2] == (160, 0))
    ring = place_shared.ring_targets(_flush_plane(plans), here)
    assert (160, 160) not in {plan.extent_cells[:2] for plan in ring}
    assert (320, 160) in {plan.extent_cells[:2] for plan in ring}


def test_the_ring_is_the_same_tuple_every_time() -> None:
    """Determinism: the enumeration is the lattice's, not a dict's."""
    plans = _lattice_plans(FLUSH_ROWS, FLUSH_COLS)
    here = next(plan for plan in plans if plan.extent_cells[:2] == (160, 160))
    first = place_shared.ring_targets(_flush_plane(plans), here)
    again = place_shared.ring_targets(_flush_plane(tuple(reversed(plans))),
                                      here)
    assert first == again
    assert len({plan.window_id for plan in first}) == len(first)


def test_a_coarse_pose_steers_the_finer_window_it_covers() -> None:
    """Item 6, and the score's other anchor: colocated is EXACTLY 0.0."""
    fine = _lattice_plans(FLUSH_ROWS, FLUSH_COLS)
    coarse = _lattice_plans(FLUSH_ROWS, FLUSH_COLS, footing=COARSE)
    plane = _flush_plane(fine + coarse)
    here = next(plan for plan in coarse if plan.extent_cells[:2] == (160, 0))
    donors = place_shared.donor_targets(plane, here)
    assert [plan.window_id for plan in donors] == [
        window_key(FOOTING, REGION, here.extent_cells)]
    assert place_job.hint_distance(
        place_job.window_centre_cells(here.extent_cells),
        place_job.window_centre_cells(donors[0].extent_cells),
        float(WINDOW_STEP_CELLS)) == 0.0
    # and the inverse voice names the same pair, roles swapped: the fine
    # window CONSULTS the coarse one it is covered by.
    assert [plan.window_id for plan in
            place_shared.donor_sources(plane, donors[0])] == [here.window_id]


def test_the_steer_never_goes_uphill_to_a_coarser_footing() -> None:
    """A donor is a coarse pose steering a fine window, never the reverse."""
    fine = _lattice_plans(FLUSH_ROWS, FLUSH_COLS)
    coarse = _lattice_plans(FLUSH_ROWS, FLUSH_COLS, footing=COARSE)
    plane = _flush_plane(fine + coarse)
    here = next(plan for plan in fine if plan.extent_cells[:2] == (160, 0))
    assert place_shared.donor_targets(plane, here) == ()
    assert all(plan.footing_id == COARSE
               for plan in place_shared.donor_sources(plane, here))


# ------------------------------------------- the frame bridge, inverted

@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
@pytest.mark.parametrize("origin", [(0, 0), (7, 11), (-3, 5), (160, -1)])
def test_the_predicted_origin_inverts_the_page_affine_exactly(
        rot_k: int, origin: tuple[int, int]) -> None:
    """What ``page_affine_terms`` composed, this takes apart.

    An anchor pose carries a page affine; the consulting window holds its
    OWN fitted pose and must recover where that pose sits on the page. If
    the two windows share a page frame — which is what a consult assumes —
    the recovered orientation and origin are the ones the frame was built
    from, exactly.
    """
    pose = AffinePose((100.0, 200.0), ((4.0, 0.1), (-0.1, 4.0)), (0.5, 0.5),
                      4.0, 0.0)
    shape = (37, 53)
    terms = place_shared.page_affine_terms(pose, shape, rot_k, origin)
    assert place_shared.predict_from_page_affine(terms, pose, shape) == (
        rot_k, origin)


def test_a_neighbours_pose_predicts_a_neighbours_origin() -> None:
    """The real use: the same page frame, a window one stride over.

    The seed's affine is the ANCHOR's; the target's own fit differs by
    the stride, and what comes back is the target's page origin — which
    is the centre v1's bounded local search is run around.
    """
    pitch = 4.0
    source = AffinePose((100.0, 200.0), ((pitch, 0.0), (0.0, pitch)),
                        (0.0, 0.0), pitch, 0.0)
    shape = (WINDOW_CELLS, WINDOW_CELLS)
    terms = place_shared.page_affine_terms(source, shape, 0, (64, 64))
    target = AffinePose(
        (100.0 + pitch * WINDOW_STEP_CELLS, 200.0),
        ((pitch, 0.0), (0.0, pitch)), (0.0, 0.0), pitch, 0.0)
    assert place_shared.predict_from_page_affine(terms, target, shape) == (
        0, (64 + WINDOW_STEP_CELLS, 64))
