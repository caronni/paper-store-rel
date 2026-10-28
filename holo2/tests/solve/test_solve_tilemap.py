"""The tile map, its indexes, and the §6 done projection.

Everything here is derived state: the assertions are about what the
records *imply*, never about anything stored twice.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Callable

import numpy as np
import pytest

from holo2.core.blobs import stage_array
from holo2.core.commit import CommitBatch, CommitEngine, Write
from holo2.format.close_spec import CloseSpec, CloseStreamProfile
from holo2.solve.geometry import CellLattice, scale_translation_affine
from holo2.core.commit import CommitRefusal
from holo2.capture import (CaptureRecord, FootingSpec, RegionRecord,
                            capture_key, region_key)
from holo2.solve import (CalibrationRecord, EvidenceObservation, HeldoutGate,
                         MintRef, PoseRecord, TileRecord,
                         WindowRecord, WindowStatus,
                         calibration_key, evidence_key, pack_observed_cells,
                         tile_key, window_key)

from holo2.core.store import Store
from holo2.solve.close import certified_symbols
from holo2.solve.tilemap import (DoneProjection, StoreIndex, TileMap,
                                 TileMapError, TileState, project_done,
                                 tile_state)

IDENTITY = scale_translation_affine(1.0, (0.0, 0.0))
LATTICE = CellLattice((0, 0), Fraction(1), (8, 128))
SUPPORT = np.ones((8, 128), bool)

FOOTING = "cap:1/1"
CAPTURE = "ab" * 32
REGION = region_key(CAPTURE, (0, 0), 8, (8, 128))
OTHER_REGION = region_key(CAPTURE, (0, 256), 8, (8, 128))
WHOLE = (0, 0, 8, 128)

# The ground these records stand on (F-07's relational half): a region
# names its capture, a window its region, a piece its pose AND its
# calibration. The fixture calibration is scoped to the CAPTURE — an
# ideal fit over the whole acquisition — so it does not drag a particular
# window into every test that only wants a piece of evidence.
_MASK = stage_array(np.ones(8 * 128, np.uint8))
_PARAMS = stage_array(np.zeros(2, np.float64))
CALIBRATION = calibration_key(capture_key(CAPTURE), "pava-v1",
                              _PARAMS.ref.sha256)


def _ground() -> tuple[tuple[Write, ...], tuple[object, ...]]:
    """Capture, both regions and the calibration, as writes plus blobs."""
    writes = [
        Write(capture_key(CAPTURE), CaptureRecord(
            source_sha256=CAPTURE, dpi_true=1200.0, shape_px=(8, 1024),
            dtype="uint8", channels=1, platen_backing=200.0,
            footings=(FootingSpec(FOOTING, Fraction(1), CAPTURE),))),
        Write(CALIBRATION, CalibrationRecord(
            scope=capture_key(CAPTURE), algorithm="pava-v1",
            params_ref=_PARAMS.ref,
            heldout=HeldoutGate(adopted=True, logloss_delta=-0.1))),
    ]
    for origin in ((0, 0), (0, 256)):
        writes.append(Write(
            region_key(CAPTURE, origin, 8, (8, 128)),
            RegionRecord(capture_sha256=CAPTURE, support_mask_ref=_MASK.ref,
                         pitch_in_vote=Fraction(8, 600), support_origin_px=origin,
                         support_step_px=8, support_extent_px=(8, 128))))
    return tuple(writes), (_MASK, _PARAMS)


def _wkey(extent, region=REGION):
    """A window IS its footing, region and extent (the identity law)."""
    return window_key(FOOTING, region, extent)


def _window(extent, region=REGION) -> WindowRecord:
    return WindowRecord(FOOTING, region, extent, WindowStatus.ACTIVE)


def _pose(extent, page=0, affine=IDENTITY) -> PoseRecord:
    return PoseRecord(_wkey(extent), FOOTING, page, affine)


def _seed(engine: CommitEngine, *, certified=(), addressed=(),
          windows=(WHOLE,), poses=(WHOLE,), region=REGION,
          evidence=True, streams=("main",), page=0) -> None:
    """One pose over one window, with pieces and tiles as asked.

    Windows and poses are named by the EXTENT they cover, because that is
    what distinguishes them: a window is its footing, region and extent,
    and a pose is its window plus its fit.
    """
    ground_writes, ground_blobs = _ground()
    writes: list[Write] = list(ground_writes)
    for extent in windows:
        writes.append(Write(_wkey(extent, region), _window(extent, region)))
    pose_keys = []
    for extent in poses:
        pose = PoseRecord(_wkey(extent, region), FOOTING, page, IDENTITY)
        pose_keys.append(pose.resource_key())
        writes.append(Write(pose.resource_key(), pose))
    blob = stage_array(np.zeros(4, np.uint8))
    seen = stage_array(pack_observed_cells(np.ones(4, bool)))
    ref = blob.ref
    for tile_page, ty, tx in tuple(certified) + tuple(addressed):
        for stream in streams:
            if evidence:
                for pose_key_ in pose_keys:
                    writes.append(Write(
                        evidence_key(FOOTING, tile_page, ty, tx, stream,
                                     pose_key_),
                        EvidenceObservation(FOOTING, tile_page, ty, tx,
                                            stream, pose_key_, ref, seen.ref,
                                            CALIBRATION)))
    for page, ty, tx in certified:
        for stream in streams:
            writes.append(Write(tile_key(page, ty, tx, stream), TileRecord(
                # The mint names a pose this seed actually COMMITS (F-07):
                # a certificate's witness has to be a fact, and the first
                # pose of the seed is the one the freeze would pick.
                minting=MintRef(pose_keys[0], "scan", "fixture-decoder"),
                bits_ref=ref, metadata_bit=1, observed_by=(FOOTING,))))
    for page, ty, tx in addressed:
        for stream in streams:
            writes.append(Write(tile_key(page, ty, tx, stream), TileRecord(
                observed_by=("cap:1/1",))))
    engine.apply(CommitBatch(writes=tuple(writes),
                             blobs=(blob, seen) + tuple(ground_blobs)))


def _map(store: Store, streams=("main",), tiles_yx=(1, 2)) -> TileMap:
    return TileMap(StoreIndex.build(store), streams, tiles_yx)


class _TileView:
    """The three ``SolveView`` reads the close's materialisation needs."""

    def __init__(self, store: Store, streams=("main",),
                 tiles_yx=(1, 2)) -> None:
        self._store = store
        self._tiles = _map(store, streams, tiles_yx)

    def certified_work_keys(self):
        return self._tiles.certified_keys()

    def tile(self, key):
        return self._tiles.record(key)

    def read_array(self, ref):
        return self._store.read_array(ref)


def _project(store: Store, streams=("main",), tiles_yx=(1, 2),
             extent_lattice: CellLattice = LATTICE,
             support: np.ndarray = SUPPORT) -> DoneProjection:
    index = StoreIndex.build(store)
    return project_done(
        index, TileMap(index, streams, tiles_yx), capture_sha256="ab" * 32,
        region_id=REGION, lattice=extent_lattice, support=support,
        pose_ids=tuple(index.poses))


# ------------------------------------------------------------------ index

def test_index_groups_every_kind(engine: CommitEngine) -> None:
    _seed(engine, certified=((0, 0, 0),), addressed=((0, 0, 1),))
    index = StoreIndex.build(engine.store)
    pose = _pose(WHOLE).resource_key()
    assert set(index.windows) == {_wkey(WHOLE)}
    assert set(index.poses) == {pose}
    assert index.poses_by_window == {_wkey(WHOLE): (pose,)}
    assert index.evidence_by_tile[tile_key(0, 0, 1, "main")] == (
        evidence_key(FOOTING, 0, 0, 1, "main", pose),)
    assert index.page_of_pose(pose) == 0
    assert index.page_of_pose(_pose(WHOLE, page=1).resource_key()) is None


def test_the_maintained_index_is_the_built_one_at_every_commit(
        engine: CommitEngine) -> None:
    """F-17's wiring pin: ``updated`` == ``build``, commit by commit.

    The full claim is measured BY PATH over real decodes
    (``holo2/measure/index_equivalence.py``, which also injects faults);
    what belongs in the fast lane is that the delta path is WIRED — that
    every kind the index buckets survives one commit's changed keys, and
    that a group comes out in the builder's own sorted order rather than
    in arrival order.
    """
    ground_writes, ground_blobs = _ground()
    blob = stage_array(np.zeros(4, np.uint8))
    seen = stage_array(pack_observed_cells(np.ones(4, bool)))
    tile = tile_key(0, 0, 1, "main")
    # Two fits of one window, committed HIGH KEY FIRST, so the second
    # piece has to be INSERTED ahead of the first rather than appended —
    # the case an order-blind delta would get wrong and the builder's own
    # ``sorted()`` would not.
    late, early = sorted(
        (_pose(WHOLE), _pose(WHOLE, affine=scale_translation_affine(
            1.0, (2.0, 3.0)))),
        key=lambda pose: pose.resource_key(), reverse=True)

    def piece(pose: PoseRecord) -> Write:
        pose_id = pose.resource_key()
        return Write(evidence_key(FOOTING, 0, 0, 1, "main", pose_id),
                     EvidenceObservation(FOOTING, 0, 0, 1, "main",
                                         pose_id, blob.ref, seen.ref,
                                         CALIBRATION))

    batches = [
        CommitBatch(writes=ground_writes, blobs=ground_blobs),
        CommitBatch(writes=(Write(_wkey(WHOLE), _window(WHOLE)),
                            Write(late.resource_key(), late))),
        CommitBatch(writes=(piece(late),), blobs=(blob, seen)),
        CommitBatch(writes=(Write(early.resource_key(), early),)),
        CommitBatch(writes=(piece(early),)),
        CommitBatch(writes=(Write(tile, TileRecord(observed_by=(FOOTING,))),)),
        CommitBatch(writes=(Write(tile, TileRecord(
            minting=MintRef(late.resource_key(), "scan", "fixture-decoder"),
            bits_ref=blob.ref, metadata_bit=1, observed_by=(FOOTING,))),)),
    ]
    maintained = StoreIndex()
    for batch in batches:
        result = engine.apply(batch)
        maintained = maintained.updated(engine.store, result.changed_keys)
        built = StoreIndex.build(engine.store)
        assert maintained.certified == built.certified
        assert maintained.certified_streams == built.certified_streams
        assert maintained.evidence_footings == built.evidence_footings
        for name in ("tiles", "windows", "poses", "regions", "captures",
                     "subjects", "evidence_by_tile", "poses_by_window",
                     "live_poses", "open_tiles", "certified_tiles"):
            assert getattr(maintained, name) == getattr(built, name), name
    assert maintained.certified == 1, "the run has to have MOVED the index"
    assert maintained.certified_streams == {(0, 0, 1): frozenset({"main"})}
    group = maintained.evidence_by_tile[tile]
    assert len(group) == 2 and group == tuple(sorted(group)), (
        "the later-arriving piece was inserted, not appended")
    assert maintained.open_tiles == () and maintained.certified_tiles == (
        tile,), "the work key crossed the partition when it certified"


def test_a_delta_naming_a_key_the_store_lacks_is_refused(
        engine: CommitEngine) -> None:
    """A retirement would silently rot the index, so it is a refusal.

    ``Store.apply_committed`` only ever assigns, so a changed key the
    store cannot answer for means the invariant this maintenance rests on
    has moved — a loud stop, never a stale entry left standing.
    """
    with pytest.raises(TileMapError, match="cannot be maintained"):
        StoreIndex().updated(engine.store, (tile_key(0, 0, 0, "main"),))


def test_a_delta_of_unindexed_kinds_is_the_same_index(
        engine: CommitEngine) -> None:
    """Collections, closes and per-window calibrations move nothing here
    (and cost nothing): the index that comes back is the identical
    object. Since H5 the ADOPTED POOL fits are the one calibration shape
    that does move it (``StoreIndex.context_fits``); this fixture's is a
    window-scoped marginal fit, which is every placement emission's."""
    _seed(engine, certified=((0, 0, 0),))
    index = StoreIndex.build(engine.store)
    assert index.updated(engine.store, (CALIBRATION,)) is index


def test_a_pose_names_its_own_page(engine: CommitEngine) -> None:
    """R3: one pose is one page, and the page is ON the pose (§5.3)."""
    _seed(engine, certified=((1, 0, 0),), page=1)
    index = StoreIndex.build(engine.store)
    pose = _pose(WHOLE, page=1).resource_key()
    assert index.page_of_pose(pose) == 1
    assert index.poses[pose].page == 1


def test_a_pose_outside_the_declared_page_domain_is_refused(
        engine: CommitEngine) -> None:
    """The family's structural validator holds the §5.1 domain (R3)."""
    with pytest.raises(CommitRefusal, match="page domain"):
        outside = _pose(WHOLE, page=7)
        engine.apply(CommitBatch(writes=(
            Write(outside.resource_key(), outside),)))


# --------------------------------------------------------------- tile map

def test_counts_and_selections(engine: CommitEngine) -> None:
    """The two selections and the operator tally, over the same seed.

    ``open_keys`` is the eligibility domain — a record exists and is not
    certified — and the tally's ATTEMPTED rank is the caller's ledger
    fact, so the SAME store reads two ways depending on what a decoder
    has run on (tile family v4).
    """
    _seed(engine, certified=((0, 0, 0),), addressed=((0, 0, 1),))
    tiles = _map(engine.store)
    open_key = tile_key(0, 0, 1, "main")
    assert tiles.certified_keys() == (tile_key(0, 0, 0, "main"),)
    assert tiles.open_keys() == (open_key,)
    assert tiles.counts()["CERTIFIED"] == 1
    assert tiles.counts()["ADDRESSED"] == 1
    assert tiles.counts()["ATTEMPTED"] == 0
    exposed = tiles.counts((open_key,))
    assert exposed["ATTEMPTED"] == 1 and exposed["ADDRESSED"] == 0


def test_the_display_rank_is_derived_from_what_is_durable() -> None:
    """§5.2's four ranks, off the record plus the caller's ledger fact."""
    assert tile_state(None, attempted=False) is TileState.UNKNOWN
    assert tile_state(TileRecord(), attempted=False) is TileState.ADDRESSED
    assert tile_state(TileRecord(), attempted=True) is TileState.ATTEMPTED
    assert tile_state(TileRecord(baselined=("a:2/1",)),
                      attempted=False) is TileState.ATTEMPTED
    assert tile_state(TileRecord(minting=MintRef("p", "scan", "d")),
                      attempted=True) is TileState.CERTIFIED


def test_done_is_per_stream_terminal(engine: CommitEngine) -> None:
    """A CMY8-shaped tile with only one stream certified is NOT done (§2)."""
    _seed(engine, certified=((0, 0, 0),), streams=("C",))
    tiles = _map(engine.store, streams=("C", "M", "Y"))
    assert not tiles.tile_done(0, 0, 0)
    assert TileMap(StoreIndex.build(engine.store), ("C",),
                   (1, 2)).tile_done(0, 0, 0)


def test_certificates_carry_the_close_equation(engine: CommitEngine) -> None:
    """R1: certificate materialisation belongs to the close provider."""
    bits = np.array([1, 0, 1, 1], np.uint8)
    ref = engine.store.put_array(bits)
    _seed(engine)                       # the window and pose the mint names
    engine.apply(CommitBatch(writes=(
        Write(tile_key(0, 0, 1, "main"), TileRecord(
            minting=MintRef(_pose(WHOLE).resource_key(),
                                "scan", "fixture-decoder"),
            bits_ref=ref, metadata_bit=1, observed_by=(FOOTING,))),)))
    spec = CloseSpec("k-v1", b"seed", (1, 2),
                     (CloseStreamProfile("main", 4),))
    certificates = certified_symbols(_TileView(engine.store), spec)
    assert len(certificates) == 1
    assert certificates[0].counter == 1
    assert certificates[0].metadata_bit == 1
    np.testing.assert_array_equal(certificates[0].symbol, bits)


def test_a_certified_tile_without_bits_is_a_broken_record(
        engine: CommitEngine) -> None:
    _seed(engine)                       # the window and pose the mint names
    engine.apply(CommitBatch(writes=(
        Write(tile_key(0, 0, 0, "main"), TileRecord(
            minting=MintRef(_pose(WHOLE).resource_key(),
                            "scan", "fixture-decoder"))),)))
    spec = CloseSpec("k-v1", b"seed", (1, 2),
                     (CloseStreamProfile("main", 4),))
    with pytest.raises(TileMapError):
        certified_symbols(_TileView(engine.store), spec)


# ------------------------------------------------------- done projection

def test_certified_tiles_project_onto_their_capture_cells(
        engine: CommitEngine) -> None:
    _seed(engine, certified=((0, 0, 0),), addressed=((0, 0, 1),))
    projection = _project(engine.store)
    assert projection.cells[:, :64].all()          # tile (0,0) is certified
    assert not projection.cells[:, 64:].any()      # tile (0,1) is not
    assert projection.done_cells == 8 * 64
    assert projection.runs() == tuple((row, 0, 64) for row in range(8))


def test_nothing_is_done_without_a_certificate(engine: CommitEngine) -> None:
    _seed(engine, addressed=((0, 0, 0), (0, 0, 1)))
    assert not _project(engine.store).cells.any()


def test_a_pose_with_no_evidence_still_spends_its_certified_pixels(
        engine: CommitEngine) -> None:
    """§6 exactly: ANY committed pose over a certified key spends it.

    Before R3 the page was derived from the pose's observation pieces, so
    a pose with none was skipped — an under-estimate DESIGN §6 does not
    ask for. ``PoseRecord.page`` removed the reason for it.
    """
    _seed(engine, certified=((0, 0, 0),), evidence=False)
    assert _project(engine.store).cells[:, :64].all()


def test_unsupported_cells_are_never_done(engine: CommitEngine) -> None:
    _seed(engine, certified=((0, 0, 0),))
    support = SUPPORT.copy()
    support[3, 7] = False
    projection = _project(engine.store, support=support)
    assert not projection.cells[3, 7]
    assert projection.done_cells == 8 * 64 - 1


def test_the_gate_is_exact_over_supported_cells(engine: CommitEngine) -> None:
    _seed(engine, certified=((0, 0, 0),))
    projection = _project(engine.store)
    assert projection.covers((0, 0, 8, 64), SUPPORT)
    assert not projection.covers((0, 0, 8, 128), SUPPORT)
    assert not projection.covers((0, 64, 8, 128), SUPPORT)


def test_an_unsupported_window_is_dead_not_done(engine: CommitEngine) -> None:
    _seed(engine, certified=((0, 0, 0),))
    support = np.zeros((8, 128), bool)
    projection = _project(engine.store, support=support)
    assert not projection.covers((0, 0, 8, 64), support)


def test_the_gate_ignores_unsupported_cells_inside_the_extent(
        engine: CommitEngine) -> None:
    """An unsupported hole cannot keep a window from retiring (§6)."""
    _seed(engine, certified=((0, 0, 0),))
    support = SUPPORT.copy()
    support[2, 5] = False
    assert _project(engine.store, support=support).covers(
        (0, 0, 8, 64), support)


def test_every_committed_pose_projects_not_only_the_minting_one(
        engine: CommitEngine) -> None:
    """§6: freeze winners and losers alike spend their pixels."""
    first, second = (0, 0, 8, 64), (0, 32, 8, 128)
    _seed(engine, certified=((0, 0, 0),), windows=(first, second),
          poses=(first, second))
    projection = _project(engine.store)
    assert projection.cells[:, :64].all()
    index = StoreIndex.build(engine.store)
    assert index.poses_by_window == {
        _wkey(first): (_pose(first).resource_key(),),
        _wkey(second): (_pose(second).resource_key(),)}


def test_projection_skips_poses_of_other_regions(
        new_store: Callable[..., Store]) -> None:
    """Choice 3: survey regions are disjoint, so a pose stays in its own."""
    store = new_store()
    engine = CommitEngine(store)
    # Everything committed in a DIFFERENT region of the same capture: the
    # projection of REGION sees a certified tile and no pose of its own.
    _seed(engine, certified=((0, 0, 0),), region=OTHER_REGION)
    assert not _project(store).cells.any()


# --------------------------------------------- choice 8: the live pose

def _revision(extent, term: float) -> PoseRecord:
    """A second pose of one extent, at a different affine (an RF1 shape)."""
    return PoseRecord(_wkey(extent), FOOTING, 0,
                      scale_translation_affine(1.0, (0.0, term)))


def test_the_live_pose_of_an_extent_is_the_latest_committed(
        engine: CommitEngine) -> None:
    """RULING I3 (user, 2026-08-23): "the latest committed pose wins".

    THE FORK: reading ``poses_by_window[-1]`` — a SORTED tuple — instead
    of the write-ordered derivation. The two revisions below are
    committed in descending affine order, so the sorted tuple's last
    member is the FIRST one committed and a sorted-order reader promotes
    a pose the run has already superseded. Nothing else distinguishes
    them: all three are ordinary poses of one window, and neither the
    standing pose nor the earlier revision is marked, mutated or removed.
    """
    _seed(engine, certified=((0, 0, 0),))
    parent = _pose(WHOLE).resource_key()
    first, second = _revision(WHOLE, 3.0), _revision(WHOLE, 1.0)
    for revision in (first, second):
        engine.apply(CommitBatch(writes=(
            Write(revision.resource_key(), revision),)))
    index = StoreIndex.build(engine.store)

    assert index.live_pose(_wkey(WHOLE)) == second.resource_key()
    assert index.poses_by_window[_wkey(WHOLE)][-1] != second.resource_key(), (
        "the fixture must make sorted-last and committed-last differ, or "
        "it cannot tell the two readings apart")
    assert set(index.poses_by_window[_wkey(WHOLE)]) == {
        parent, first.resource_key(), second.resource_key()}, (
        "a revision retracts nothing: all three poses still stand")
    assert index.live_pose(_wkey((0, 0, 4, 4))) is None


def test_a_re_written_pose_does_not_become_live_again(
        engine: CommitEngine) -> None:
    """Quarantine is the only re-write of a standing pose, and it is not
    a commit of new geometry: the extent's live pose stays where the
    revision put it, which is what ``build``'s first-write walk says too.
    """
    _seed(engine, certified=((0, 0, 0),))
    parent = _pose(WHOLE)
    revision = _revision(WHOLE, 3.0)
    engine.apply(CommitBatch(writes=(
        Write(revision.resource_key(), revision),)))
    before = StoreIndex.build(engine.store)
    condemned = PoseRecord(parent.window_id, FOOTING, 0,
                           parent.native_affine, quarantined=True)
    result = engine.apply(CommitBatch(writes=(
        Write(condemned.resource_key(), condemned),)))

    maintained = before.updated(engine.store, result.changed_keys)
    built = StoreIndex.build(engine.store)
    assert built.live_pose(_wkey(WHOLE)) == revision.resource_key()
    assert maintained.live_poses == built.live_poses
    assert maintained.poses[parent.resource_key()].quarantined, (
        "the re-write itself has to have landed, or the pin is vacuous")


def test_the_regions_live_poses_are_one_per_posed_window(
        engine: CommitEngine) -> None:
    """What :func:`project_done`'s production callers pass it (choice 8).

    THE FORK: the union the two callers used to build — every committed
    pose of every window here — which on the real sheets added done cells
    a revision bought without sampling a pixel (W2: +860 e029 / +588
    Xerox). One window, two poses, ONE contribution.
    """
    _seed(engine, certified=((0, 0, 0),))
    revision = _revision(WHOLE, 3.0)
    engine.apply(CommitBatch(writes=(
        Write(revision.resource_key(), revision),)))
    index = StoreIndex.build(engine.store)

    assert index.live_poses_of_region(REGION) == (revision.resource_key(),)
    assert len(index.poses) == 2, "the superseded pose is still committed"
    assert index.live_poses_of_region(OTHER_REGION) == ()
