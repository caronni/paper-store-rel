from __future__ import annotations

import dataclasses
from fractions import Fraction

import numpy as np
import pytest

from holo.receiver import data, engine
from holo.receiver.descriptor import (
    KEY_ATTEMPT,
    KEY_EVIDENCE_FIT,
    KEY_EVIDENCE_READ,
    KEY_LANE_POSES,
    KEY_LATTICE_SEED,
    KEY_LIVE_PAGES,
    KEY_PAGE_CERTS,
    KEY_POSE_AFFINE,
    KEY_POSE_ROUTE,
    KEY_REGION_CTX,
    KEY_TILE,
    WorkerBookmark,
)
from holo.receiver.plugins import fields_collect, refine
from holo.receiver.tests import _h3_facts, _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_every_fact_type_writes_exactly_the_cells_it_is_pinned_to`,
# `test_no_cell_is_written_by_a_fact_no_descriptor_and_no_fold_produces`.

CAPTURE_ID = _h3_facts.CAPTURE_ID
WID = _h3_facts.WINDOW_ID
WID_B = (CAPTURE_ID, 0, 0, (64, 0, 128, 64))
REGION = (CAPTURE_ID, 0, 0)
NAN = float("nan")

REACH_WID = (CAPTURE_ID, 0, 0, (0, 0, 128, 128))
REACH_CELLS = _h3_facts.tile_cells(128)
REACH_SHIFT = 128
OLD_REACH = ((0, 0), (0, 1), (1, 0), (1, 1))
NEW_REACH = ((2, 2), (2, 3), (3, 2), (3, 3))

FOLD_WRITE_MAP = {
    "Capture": ("_captures", "_levels"),
    "CaptureSurvey": ("_surveys", "_frames", "_plan_total", "_windows",
                      "_ordinal_wid", "_place_stages"),
    "Window": ("_windows", "_ordinal_wid", "_place_stages"),
    # no lane-pose cell any more: the lane-page key is emitted from the
    # `affine_changed` predicate the fold already computes (R5)
    # `_region_sampling` 2026-10-03: the pitch key moves with the
    # (halo, aperture) pair the window reads take from the pitch
    "Placement": ("_place_stages", "_placements", "_page_cells", "_pose_gen",
                  "_live_pages", "_lanes_on_page",
                  "_region_pitch", "_region_sampling", "_evidence_revision"),
    "PlaceOutcome": ("_place_stages",),
    "LatticeSeed": ("_lattice_seeds",),
    "WindowEvidence": ("_evidence", "_tile_cover_k", "_window_cover",
                       "_tile_lane_generation", "_union_generation"),
    # the decision, then the catch-up over the region's STANDING rows
    # (2026-10-03): a correction moves the read half only, so the cover
    # cells a fresh fit writes are no longer this fold's
    "CtxOutcome": ("_evidence", "_region_ctx", "_tile_lane_generation",
                   "_union_generation"),
    "RefineOutcome": ("_placements", "_pose_gen", "_evidence_revision"),
    "ColorEvidenceRow": ("_color_rows", "_tile_cover_color",
                         "_color_row_cover", "_tile_lane_generation",
                         "_union_generation"),
    "ColorLaneFit": ("_color_lane_assembled", "_color_lane_head",
                     "_color_lane_head_fits"),
    "ColorCtxPopulation": ("_color_pops", "_pop_lanes"),
    "PooledColorCtx": ("_pooled_ctx",),
    "Certificate": ("_certificates", "_equations",
                    "_evidence_revision"),
    "AttemptFact": ("_attempt_outcomes", "_attempt_latest",
                    "_attempt_ever_failed_footing"),
    "PlaneField": ("_plane_fields",),
    "FieldObservations": ("_field_observations",),
    "EvidenceRevision": ("_evidence_revision",),
}

# a delegating fact folds through its delegate: the write it shares is the
# delegate's, not a second writer
FOLD_DELEGATIONS = {
    "CaptureSurvey": "Window",
    "CtxOutcome": "WindowEvidence",
    "RefineOutcome": "Placement",
}

# the one cell three folds still share (FAMILIES-AUDIT W3: WindowState is
# born with the window, flagged by the placement, aged by the outcome)
MULTI_WRITER_CELLS = {
    "_place_stages": ("PlaceOutcome", "Placement", "Window"),
    # the page field's evidence revision (I12) counts EVENTS from two
    # families — a placement's birth, change or removal and a
    # certificate on that face — and is restored by a third at the front
    # of a resume, because events do not survive the facts they left
    "_evidence_revision": ("Certificate", "EvidenceRevision", "Placement"),
    # the tile-lane GENERATION counts the same EVENT from both evidence
    # families -- a K window's read and a colour row's -- because a tile
    # cut is assembled from whichever of them covers it.  One meaning,
    # two producers of the raw evidence it counts (INV-G1)
    "_tile_lane_generation": ("ColorEvidenceRow", "WindowEvidence"),
    # and the footing counter beside it, for the same reason and from
    # the same two folds (store.union_generation)
    "_union_generation": ("ColorEvidenceRow", "WindowEvidence"),
}


def _collapsed(names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({FOLD_DELEGATIONS.get(name, name)
                         for name in names}))


class _Wakes:

    def __init__(self, engine: object) -> None:
        self.engine = engine
        self.pushed: list = []
        engine._push_worker = self.pushed.append

    def subscribe(self, *keys: tuple) -> WorkerBookmark:
        subject = ("probe", len(self.engine._bookmarks))
        worker = WorkerBookmark(plugin="probe", subject=subject, reads=keys)
        self.engine._bookmarks[("probe", subject)] = worker
        self.engine._register_reads(worker, keys)
        return worker


def _wakes(fact_name: str) -> tuple[object, _Wakes]:
    engine = _h3_facts.seeded_engine(fact_name)
    return engine, _Wakes(engine)


def test_a_real_change_bumps_the_version_of_every_subscriber_of_its_key():
    engine, wakes = _wakes("WindowEvidence")
    fit = wakes.subscribe((KEY_EVIDENCE_FIT, WID))
    read = wakes.subscribe((KEY_EVIDENCE_READ, WID))
    changed, _kind = engine._ingest(_h3_facts.evidence())
    assert changed is True
    assert fit.version == 1 and read.version == 1
    assert wakes.pushed.count(fit) == 1


def test_an_identical_rewrite_of_the_same_cell_wakes_nobody():
    engine, wakes = _wakes("WindowEvidence")
    fit = wakes.subscribe((KEY_EVIDENCE_FIT, WID))
    read = wakes.subscribe((KEY_EVIDENCE_READ, WID))
    engine._ingest(_h3_facts.evidence())
    before = (fit.version, read.version, len(wakes.pushed))
    changed, _kind = engine._ingest(_h3_facts.evidence())
    assert changed is False, (
        "a value-identical fact must fold to no change: version bumps only "
        "on real data change (D6 addendum 6)")
    assert (fit.version, read.version, len(wakes.pushed)) == before


def test_an_unchanged_fold_touches_no_key_at_all():
    engine = _h3_facts.seeded_engine("WindowEvidence")
    engine._fold(_h3_facts.evidence())
    changed, keys, _kind = engine._fold(_h3_facts.evidence())
    assert (changed, keys) == (False, ())


def test_a_fit_side_change_wakes_the_fit_half_and_leaves_the_read_half():
    engine, wakes = _wakes("WindowEvidence")
    fit = wakes.subscribe((KEY_EVIDENCE_FIT, WID))
    read = wakes.subscribe((KEY_EVIDENCE_READ, WID))
    engine._ingest(_h3_facts.evidence())
    engine._ingest(_h3_facts.evidence(score=0.5))
    assert (fit.version, read.version) == (2, 1)


def test_a_read_side_change_wakes_the_read_half_and_leaves_the_fit_half():
    engine, wakes = _wakes("WindowEvidence")
    fit = wakes.subscribe((KEY_EVIDENCE_FIT, WID))
    read = wakes.subscribe((KEY_EVIDENCE_READ, WID))
    engine._ingest(_h3_facts.evidence())
    engine._ingest(_h3_facts.evidence(printed=2.0))
    assert (fit.version, read.version) == (1, 2)


def test_an_array_cell_rewritten_with_the_same_nans_is_not_a_change():
    engine, wakes = _wakes("WindowEvidence")
    fit = wakes.subscribe((KEY_EVIDENCE_FIT, WID))
    read = wakes.subscribe((KEY_EVIDENCE_READ, WID))
    assert engine._ingest(_h3_facts.evidence(score=NAN, printed=NAN))[0]
    before = (fit.version, read.version)
    changed, _kind = engine._ingest(_h3_facts.evidence(score=NAN,
                                                       printed=NAN))
    assert changed is False, (
        "array cells compare with equal_nan=True: a NaN rewrite is not a "
        "change and must not wake anybody")
    assert (fit.version, read.version) == before


def test_a_route_only_write_wakes_the_route_key_and_not_the_affine_key():
    engine, wakes = _wakes("Placement")
    affine = wakes.subscribe((KEY_POSE_AFFINE, WID))
    route = wakes.subscribe((KEY_POSE_ROUTE, WID))
    engine._ingest(_h3_facts.placement(route="word", quality=1.0))
    engine._ingest(_h3_facts.placement(route="ring", quality=0.5))
    assert (affine.version, route.version) == (1, 2)


def test_an_affine_only_write_wakes_the_affine_key_and_not_the_route_key():
    engine, wakes = _wakes("Placement")
    affine = wakes.subscribe((KEY_POSE_AFFINE, WID))
    route = wakes.subscribe((KEY_POSE_ROUTE, WID))
    engine._ingest(_h3_facts.placement(quality=1.0))
    engine._ingest(_h3_facts.placement(origin_yx=(8.0, 8.0), quality=0.5))
    assert (affine.version, route.version) == (2, 1)


def test_a_window_moved_to_another_page_wakes_both_lane_pages():
    """The page a window LEAVES has changed, and only this fold knows.

    Added 2026-09-08 (W7): the move dropped the window from the old
    page's lane set and woke the new page alone, so a subscriber on the
    old lane-page — `fields.collect`, which stands on observations
    measured through exactly that window — kept a table it could no
    longer justify until some unrelated fact on that page woke it.
    """
    engine, wakes = _wakes("Placement")
    engine._ingest(_h3_facts.placement())
    page = engine.placement(WID).page
    left = wakes.subscribe((KEY_LANE_POSES, WID[0], WID[1], page))
    arrived = wakes.subscribe((KEY_LANE_POSES, WID[0], WID[1], page + 1))
    changed, _kind = engine._ingest(_h3_facts.placement(
        page=page + 1, route=data.ROUTE_REFINE))
    assert changed is True
    assert left.version == 1 and arrived.version == 1
    assert engine.lane_page_windows(WID[0], WID[1], page) == ()


def test_the_lane_page_key_these_tests_probe_is_the_collections_own_read():
    engine, _probe = _wakes("Placement")
    engine._ingest(_h3_facts.placement())
    page = engine.placement(WID).page
    reads = fields_collect._collect_reads(engine, (CAPTURE_ID, page))
    assert (KEY_LANE_POSES, WID[0], WID[1], page) in reads, (
        "the tests below stand on the real subscription: this key is the "
        "field collection's whole dependency on placement")


def test_a_page_origin_change_under_the_same_affine_wakes_the_collection():
    """Geometry is more than the native affine tuple.

    R5 (2026-09-09 review): the fold emitted this key from a cached
    per-window affine, so an adopted change of page origin, rot_k, pitch,
    patch ordinal or local cells advanced the page's evidence revision
    while the collection that measures through that window slept.
    """
    engine, wakes = _wakes("Placement")
    engine._ingest(_h3_facts.placement(quality=1.0))
    page = engine.placement(WID).page
    collect = wakes.subscribe((KEY_LANE_POSES, WID[0], WID[1], page))
    standing = engine.placement(WID)
    origin_y, origin_x = standing.page_origin_yx
    changed, _kind = engine._ingest(dataclasses.replace(
        standing, quality=0.5, page_origin_yx=(origin_y + 1, origin_x)))
    assert changed is True
    assert collect.version == 1
    assert tuple(engine.placement(WID).native_affine) == tuple(
        standing.native_affine)


def test_a_window_returning_to_a_page_wakes_that_collection_a_second_time():
    """A->B->A: the return is a change, however familiar the affine.

    R5: the cached affine still held A's pose while the window stood on
    B, so the return compared equal and woke nobody — and an empty
    replacement already collected for A stayed empty with the window
    back on it.  The versions here are the collector's: 0, 1 on the
    departure, 2 on the return.
    """
    engine, wakes = _wakes("Placement")
    engine._ingest(_h3_facts.placement(quality=1.0))
    home = engine.placement(WID).page
    collect = wakes.subscribe((KEY_LANE_POSES, WID[0], WID[1], home))
    assert collect.version == 0
    engine._ingest(_h3_facts.placement(page=home + 1, quality=0.5))
    assert collect.version == 1
    engine._ingest(_h3_facts.placement(page=home, quality=0.25))
    assert collect.version == 2
    assert engine.lane_page_windows(WID[0], WID[1], home) == (WID,)


def test_a_quality_only_adoption_moves_the_revision_and_no_geometry_key():
    """The evidence revision counts adoptions; the lane key counts moves.

    R5: deleting the pose cache must not hand a quality-only adoption a
    geometry wake.  It still advances the capture-page's evidence
    revision — PAGE-FIELD-DESIGN §2.7 — because the collection's ordinal
    counts events, not geometry.
    """
    engine, wakes = _wakes("Placement")
    engine._ingest(_h3_facts.placement(quality=1.0))
    page = engine.placement(WID).page
    collect = wakes.subscribe((KEY_LANE_POSES, WID[0], WID[1], page))
    affine = wakes.subscribe((KEY_POSE_AFFINE, WID))
    before = engine.evidence_revision(CAPTURE_ID, page)
    changed, _kind = engine._ingest(_h3_facts.placement(quality=0.5))
    assert changed is True
    assert (collect.version, affine.version) == (0, 0)
    assert engine.evidence_revision(CAPTURE_ID, page) == before + 1


def test_a_set_cell_wakes_on_key_presence_and_never_on_a_repeat_member():
    engine, wakes = _wakes("Placement")
    live = wakes.subscribe((KEY_LIVE_PAGES,))
    assert engine.live_pages() == frozenset({0})
    engine._ingest(_h3_facts.placement())
    assert live.version == 0, (
        "page 0 is the live prior: placing it does not grow the set")
    engine._ingest(_h3_facts.window(WID_B, ordinal=_h3_facts.PROBE_ORDINAL
                                    + 1))
    engine._ingest(_h3_facts.placement(wid=WID_B, page=1,
                                       origin_yx=(8.0, 8.0)))
    assert engine.live_pages() == frozenset({0, 1})
    assert live.version == 1
    engine._ingest(_h3_facts.placement(wid=WID_B, page=1,
                                       origin_yx=(16.0, 16.0)))
    assert live.version == 1, (
        "the page was already a member: a set cell bumps on key presence, "
        "not on every write that mentions it")


def test_a_monotone_merge_cell_refuses_the_weaker_write_without_a_wake():
    engine, wakes = _wakes("LatticeSeed")
    seed = wakes.subscribe((KEY_LATTICE_SEED,) + REGION)
    assert engine._ingest(_h3_facts.lattice_seed(support_cells=20))[0]
    assert seed.version == 1
    changed, _kind = engine._ingest(_h3_facts.lattice_seed(support_cells=5))
    assert changed is False and seed.version == 1


def test_a_duplicate_certificate_is_a_no_op_that_wakes_nobody():
    engine, wakes = _wakes("Certificate")
    tile = wakes.subscribe((KEY_TILE, 0, 0, 0, "main"))
    page = wakes.subscribe((KEY_PAGE_CERTS, 0))
    engine._ingest(_h3_facts.certificate())
    before = (tile.version, page.version)
    changed, _kind = engine._ingest(_h3_facts.certificate())
    assert changed is False and (tile.version, page.version) == before


def test_a_certificate_wakes_its_own_address_and_not_a_sibling_tile():
    engine, wakes = _wakes("Certificate")
    here = wakes.subscribe((KEY_TILE, 0, 0, 0, "main"))
    sibling = wakes.subscribe((KEY_TILE, 0, 1, 0, "main"))
    engine._ingest(_h3_facts.certificate(ty=0, tx=0))
    assert (here.version, sibling.version) == (1, 0)


def test_a_ctx_outcome_that_changes_nothing_still_wakes_no_ctx_subscriber():
    engine, wakes = _wakes("CtxOutcome")
    ctx = wakes.subscribe((KEY_REGION_CTX,) + REGION)
    engine._ingest(_h3_facts.ctx_outcome(validation_logloss=0.5))
    assert ctx.version == 1
    engine._ingest(_h3_facts.ctx_outcome(validation_logloss=0.5))
    assert ctx.version == 1
    engine._ingest(_h3_facts.ctx_outcome(offset=0.25,
                                         validation_logloss=0.4))
    assert ctx.version == 2
    engine._ingest(_h3_facts.ctx_outcome(offset=0.9,
                                         validation_logloss=0.4))
    assert ctx.version == 2


def test_an_unsubscribed_key_never_wakes_however_much_the_store_moves():
    engine, wakes = _wakes("Placement")
    deaf = wakes.subscribe((KEY_LANE_POSES, CAPTURE_ID, 9, 0))
    engine._ingest(_h3_facts.placement())
    engine._ingest(_h3_facts.evidence())
    engine._ingest(_h3_facts.certificate())
    assert deaf.version == 0


def test_a_retired_subscriber_leaves_the_index_and_stops_being_woken():
    engine, wakes = _wakes("WindowEvidence")
    worker = wakes.subscribe((KEY_EVIDENCE_FIT, WID))
    engine._ingest(_h3_facts.evidence())
    assert worker.version == 1
    engine._retire_worker(worker, "probed")
    engine._ingest(_h3_facts.evidence(score=0.5))
    assert worker.version == 1
    standing = engine._index.get((KEY_EVIDENCE_FIT, WID), set())
    assert ("probe", worker.subject) not in standing


def _reach_probe(instance: object, worker: WorkerBookmark) -> dict:
    key = (worker.plugin, worker.subject)
    return {
        "version": worker.version,
        "tiles": tuple(sorted({(read[2], read[3]) for read in worker.reads
                               if read[0] == KEY_TILE})),
        "indexed": tuple(sorted({
            (read[2], read[3]) for read, subscribers
            in instance._index.items()
            if read[0] == KEY_TILE and key in subscribers})),
    }


def _reach_placement(origin: int, quality: float) -> data.Placement:
    return dataclasses.replace(
        _h3_facts.placement(wid=REACH_WID, quality=quality),
        local_cells_yx=REACH_CELLS, page_origin_yx=(origin, origin))


#: THE REACH RE-SUBSCRIPTION, on `refine`, and it is a RE-BIRTH.
#: `refine` is born by `Placement`, every adopted revision folds one,
#: and `engine._births` finds the standing bookmark and appends the
#: read keys its new reach names.  That is the ONE path by which a live
#: worker's reads grow (2026-09-21 amendment): nothing re-derives them
#: on a wake, and the old reach's keys simply stay subscribed — an
#: extra wake, never a wrong answer, and gone when the row retires.
#: (It was benched on `revisit` until that row was dissolved, then on
#: `rederive_on` for one day.)
@pytest.fixture(scope="module")
def refine_reach() -> dict:
    row = engine.DESCRIPTOR_BY_NAME["refine"]
    steps: dict = {}
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(engine, "DESCRIPTORS", (row,))
        monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", {"refine": row})
        instance = _h3_facts.new_engine()
        instance._ingest(_h3_facts.capture())
        instance._ingest(_h3_facts.window(wid=REACH_WID))
        instance._ingest(_reach_placement(0, 1.0))
        instance._ingest(_h3_facts.evidence(wid=REACH_WID,
                                            cells=REACH_CELLS,
                                            accepted=False))
        instance._ingest(_h3_facts.certificate(0, 0, 0))
        worker = instance._bookmarks[("refine", REACH_WID)]
        steps["born"] = _reach_probe(instance, worker)
        instance._ingest(_reach_placement(REACH_SHIFT, 0.5))
        steps["revised"] = _reach_probe(instance, worker)
        instance._ingest(_h3_facts.certificate(0, *NEW_REACH[0]))
        steps["new_reach"] = _reach_probe(instance, worker)
        instance._ingest(_h3_facts.certificate(0, *OLD_REACH[3]))
        steps["old_reach"] = _reach_probe(instance, worker)
    return steps


def test_the_refine_bench_is_born_subscribed_to_the_reach_of_its_pose(
        refine_reach):
    assert refine.reach_tiles(REACH_CELLS) == OLD_REACH
    assert refine_reach["born"]["tiles"] == OLD_REACH
    assert refine_reach["born"]["indexed"] == OLD_REACH


def test_a_revised_pose_extends_the_refine_subscription_to_its_new_reach(
        refine_reach):
    """THE RE-BIRTH EXTENSION, which is what `rederive_on` was for.

    A subscription set materialized at birth cannot see where the
    window went — so the fact that CREATES this row's work, its
    `Placement`, arriving again is what grows its reads.  Superset, not
    equality: the engine never prunes, and the row's `eligible` and
    `prepare` read the live pose, so a key from the abandoned reach
    costs a wake and nothing else.
    """
    grew = set(refine_reach["revised"]["tiles"])
    assert set(NEW_REACH) <= grew, (
        "the re-placed window's new reach must be subscribed before the "
        "fold's own wake reaches the index")
    assert set(OLD_REACH) <= grew, "and the engine prunes nothing"
    assert set(NEW_REACH) <= set(refine_reach["revised"]["indexed"])


def test_a_certificate_in_the_new_reach_wakes_the_revised_worker(
        refine_reach):
    assert (refine_reach["new_reach"]["version"]
            > refine_reach["revised"]["version"])


def test_a_certificate_in_the_abandoned_reach_still_wakes_it_and_may(
        refine_reach):
    """Over-declaring is safe; under-declaring is a lost re-arm.

    Until 2026-09-21 the engine pruned this key when it re-derived the
    row's reads on a pose wake.  With reads fixed at birth and extended
    by re-birth it stays, and the cost is one wake on a tile the window
    no longer reaches — after which `refine` prices and prepares off the
    LIVE pose exactly as before.
    """
    assert (refine_reach["old_reach"]["version"]
            > refine_reach["new_reach"]["version"])


def test_a_pose_revision_extends_a_worker_s_reads_even_while_in_flight():
    row = engine.DESCRIPTOR_BY_NAME["refine"]
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(engine, "DESCRIPTORS", (row,))
        monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", {"refine": row})
        instance = _h3_facts.new_engine()
        instance._ingest(_h3_facts.capture())
        instance._ingest(_h3_facts.window(wid=REACH_WID))
        instance._ingest(_reach_placement(0, 1.0))
        instance._ingest(_h3_facts.evidence(wid=REACH_WID,
                                            cells=REACH_CELLS,
                                            accepted=False))
        instance._ingest(_h3_facts.certificate(0, 0, 0))
        worker = instance._bookmarks[("refine", REACH_WID)]
        instance._frontier.clear()
        worker.inflight = True
        instance._ingest(_reach_placement(REACH_SHIFT, 0.5))
        indexed = tuple(sorted({
            (read[2], read[3]) for read, subscribers
            in instance._index.items()
            if read[0] == KEY_TILE
            and ("refine", REACH_WID) in subscribers}))
        assert set(NEW_REACH) <= set(indexed), (
            "the re-birth appends the new reach's keys whatever the "
            "worker is doing: births run on the engine thread, in the "
            "fold's own ingest")
        assert worker.pending is True
        assert instance._frontier == []
        version_after_revision = worker.version
        instance._ingest(_h3_facts.certificate(0, *NEW_REACH[0]))
        assert worker.version > version_after_revision
        assert instance._frontier == []
        held = worker.version
        instance._ingest(_h3_facts.certificate(0, *OLD_REACH[3]))
        assert worker.version > held, (
            "the abandoned reach is still subscribed -- an extra wake, "
            "which the version floor and `eligible` absorb")


def test_a_retired_row_takes_no_new_keys_from_a_later_re_birth():
    """The other end of the read-set law: they GO when the row retires.

    `_retire_worker` drops the row's whole read set out of `_index`, and
    a birth fact folded afterwards used to put part of it straight back
    — `_births` found the standing bookmark and appended the fresh keys
    without asking whether it was still alive.  Harmless (`_touch` skips
    a retired subscriber) but the index never shrank again, and API.md's
    sentence was false in the letter (review 2026-09-21, N3).
    """
    row = engine.DESCRIPTOR_BY_NAME["refine"]
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(engine, "DESCRIPTORS", (row,))
        monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", {"refine": row})
        instance = _h3_facts.new_engine()
        instance._ingest(_h3_facts.capture())
        instance._ingest(_h3_facts.window(wid=REACH_WID))
        instance._ingest(_reach_placement(0, 1.0))
        instance._ingest(_h3_facts.evidence(wid=REACH_WID,
                                            cells=REACH_CELLS,
                                            accepted=False))
        instance._ingest(_h3_facts.certificate(0, 0, 0))
        worker = instance._bookmarks[("refine", REACH_WID)]
        assert _reach_probe(instance, worker)["indexed"] == OLD_REACH
        instance._retire_worker(worker, "probe")
        assert _reach_probe(instance, worker)["indexed"] == ()
        instance._ingest(_reach_placement(REACH_SHIFT, 0.5))
        assert _reach_probe(instance, worker)["indexed"] == (), (
            "a re-birth may grow a LIVE row's inputs; a retired row has "
            "no inputs to grow")
        held = worker.version
        instance._ingest(_h3_facts.certificate(0, *NEW_REACH[0]))
        assert worker.version == held, "and nothing wakes it"


#: THE REACH REPAIR (2026-10-03; external review claim 3, SCHED-OPEN
#: #5(b)).  The residue rows are born by a FAILED verdict; a new
#: covering window whose own read comes back below the attempt floor
#: births nothing there, so before the repair the standing bookmark
#: never subscribed to the new lane's verdicts, the new window's pose or
#: the tiles its reach added.  The two evidence folds that move the
#: cover now RE-birth the ARMED tile-lanes in their cover
#: (`local_ctx.COVER_BIRTH_FACTS`) -- extending, never creating.
CAPTURE_B = "decafbad" * 8
REACH_TILE = (0, 0)
NEW_NEIGHBOURS = ((0, 1), (1, 0), (1, 1))
RESIDUE_ROWS = ("tiles.local", "tiles.planek", "tiles.swim")
COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"


def _capture_b() -> data.Capture:
    return dataclasses.replace(_h3_facts.capture(), capture_id=CAPTURE_B)


def _verdict(stream_id: str, outcome: str,
             capture_id: str) -> data.AttemptFact:
    return dataclasses.replace(
        _h3_facts.attempt(outcome), stream_id=stream_id,
        components=((capture_id, 0),))


def _residue_engine(format_ref: str | None = None) -> engine._Engine:
    """A store with no executor: pushes are dropped, folds and births run."""
    instance = _h3_facts.new_engine()
    if format_ref is not None:
        instance = engine._Engine(dataclasses.replace(
            instance._request, format_ref=format_ref), [])
    instance._push_worker = lambda worker: None
    return instance


def _residue_rows(names: tuple[str, ...],
                  born_by: tuple[type, ...] | None) -> tuple:
    rows = tuple(engine.DESCRIPTOR_BY_NAME[name] for name in names)
    if born_by is not None:
        rows = tuple(dataclasses.replace(row, born_by=born_by)
                     for row in rows)
    return rows


def _k_reach(born_by: tuple[type, ...] | None = None) -> dict:
    """tiles.local on K: lane A fails tile (0, 0); lane B's wider window
    covers it and reads below the floor; then a certificate on a tile
    only lane B's reach adds."""
    rows = _residue_rows(("tiles.local",), born_by)
    steps: dict = {}
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(engine, "DESCRIPTORS", rows)
        monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                            {row.name: row for row in rows})
        instance = _residue_engine()
        wid_b = (CAPTURE_B, 0, 0, (0, 0, 128, 128))
        instance._ingest(_h3_facts.capture())
        instance._ingest(_capture_b())
        instance._ingest(_h3_facts.window())
        instance._ingest(_h3_facts.window(wid=wid_b))
        instance._ingest(_h3_facts.evidence())
        steps["before_failure"] = len(instance._bookmarks)
        instance._ingest(_verdict("main", "attempted_failed", CAPTURE_ID))
        worker = instance._bookmarks[("tiles.local",
                                      (0, *REACH_TILE, Fraction(4)))]
        steps["born"] = (worker.reads, worker.version)
        steps["bookmarks_born"] = tuple(sorted(instance._bookmarks))
        instance._ingest(_h3_facts.evidence(wid=wid_b, cells=REACH_CELLS))
        instance._ingest(_verdict("main", "below_attempt_floor",
                                  CAPTURE_B))
        steps["extended"] = (worker.reads, worker.version)
        steps["bookmarks_extended"] = tuple(sorted(instance._bookmarks))
        instance._ingest(_h3_facts.certificate(0, *NEW_NEIGHBOURS[-1]))
        steps["woken"] = worker.version
    return steps


@pytest.fixture(scope="module")
def k_reach() -> dict:
    return _k_reach()


def _attempt_keys(reads: tuple, capture_id: str) -> tuple:
    return tuple(read for read in reads if read[0] == KEY_ATTEMPT
                 and read[6] == (capture_id, 0))


def _tile_keys(reads: tuple) -> tuple:
    return tuple(sorted({(read[2], read[3]) for read in reads
                         if read[0] == KEY_TILE}))


def test_a_k_residue_bookmark_is_born_on_its_failed_lane_alone(k_reach):
    reads, _version = k_reach["born"]
    assert k_reach["before_failure"] == 0, (
        "evidence over a tile that never failed births no residue row")
    assert _attempt_keys(reads, CAPTURE_ID)
    assert not _attempt_keys(reads, CAPTURE_B)
    assert _tile_keys(reads) == (REACH_TILE,)


def test_a_new_covering_window_extends_the_standing_bookmark(k_reach):
    reads, _version = k_reach["extended"]
    assert _attempt_keys(reads, CAPTURE_B), (
        "the new lane's verdict keys, though its read was below floor")
    assert set(NEW_NEIGHBOURS) <= set(_tile_keys(reads)), (
        "the tiles the new window's reach adds")
    assert k_reach["bookmarks_extended"] == k_reach["bookmarks_born"], (
        "a cover change EXTENDS: the tiles lane B newly covers never "
        "failed, and no residue row is born for them")


def test_a_certificate_in_the_new_reach_wakes_the_residue_bookmark(k_reach):
    assert k_reach["woken"] > k_reach["extended"][1]


def test_without_the_cover_births_the_new_reach_is_never_heard():
    """The hole, kept as a control: born by the verdict alone, the
    bookmark's reads never see lane B, and the certificate there
    wakes nothing."""
    hole = _k_reach(born_by=(data.AttemptFact,))
    assert not _attempt_keys(hole["extended"][0], CAPTURE_B)
    assert hole["woken"] == hole["extended"][1]


def _footing_counters(instance: engine._Engine) -> tuple[int, int, int]:
    """(footing counter, tile-lane counter, covering K windows) at the
    K bench's tile (0, 0), capture A's level 0 (ppc 4)."""
    lane = (0, *REACH_TILE, CAPTURE_ID, 0)
    windows, _rows = instance.tile_cover(lane)
    return (instance.union_generation(0, *REACH_TILE, Fraction(4)),
            instance.tile_lane_generation(lane), len(windows))


def test_the_footing_counter_bumps_once_per_lane_event_and_never_falls():
    """LIFECYCLE-2026-09-21 §4b B2, probed then and pinned here (review
    2026-10-17 R5): accept / re-fit / refused re-fit reads 1 -> 2 -> 3.

    The refused re-fit empties the cover, so the lane LEAVES the tile.
    The pre-42a56405 footing generation was a sum over the CURRENT
    cover and read 1 -> 2 -> 0 there: a lane leaving took its whole
    term with it, and `tiles.retry`'s union arm compares a standing
    verdict's stamp with `==`.  The tile-lane counter moves in step,
    and a fold that changes nothing is no event."""
    instance = _residue_engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window())
    assert _footing_counters(instance) == (0, 0, 0)
    readings = []
    instance._fold(_h3_facts.evidence())
    readings.append(_footing_counters(instance))
    instance._fold(_h3_facts.evidence())
    readings.append(_footing_counters(instance))
    instance._fold(_h3_facts.evidence(score=0.5))
    readings.append(_footing_counters(instance))
    instance._fold(_h3_facts.evidence(score=0.5, accepted=False))
    readings.append(_footing_counters(instance))
    assert readings == [
        (1, 1, 1),  # accepted: the window joins the tile's cover
        (1, 1, 1),  # the identical re-fold: no lane event, no bump
        (2, 2, 1),  # re-fitted with a changed fit, same cover
        (3, 3, 0),  # refused: the lane leaves, and the counter RISES
    ]


def _color_streams() -> tuple[str, ...]:
    from holo.receiver.format import identity

    row = identity.resolve_format_ref(COLOR_FORMAT_REF)
    return tuple(stream.stream_id for stream in row.streams)


@pytest.fixture(scope="module")
def color_reach() -> dict:
    """The three residue rows on cmy8: stream C of tile (0, 0) fails on
    lane A; lane B's colour row (window B, a wider cover) arrives with a
    below-floor read; then a certificate on a newly reached neighbour."""
    streams = _color_streams()
    rows = _residue_rows(RESIDUE_ROWS, None)
    wid_a = (CAPTURE_ID, 0, 0, _h3_facts.EXTENT)
    wid_b = (CAPTURE_B, 0, 0, (0, 0, 128, 128))
    steps: dict = {"wid_a": wid_a, "wid_b": wid_b}
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(engine, "DESCRIPTORS", rows)
        monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                            {row.name: row for row in rows})
        instance = _residue_engine(COLOR_FORMAT_REF)
        instance._ingest(_h3_facts.capture())
        instance._ingest(_capture_b())
        instance._ingest(_h3_facts.window(wid=wid_a, ordinal=0))
        instance._ingest(_h3_facts.window(wid=wid_b, ordinal=0))
        instance._ingest(_h3_facts.color_row())
        steps["before_failure"] = len(instance._bookmarks)
        instance._ingest(_verdict(streams[0], "attempted_failed",
                                  CAPTURE_ID))
        subjects = {
            "tiles.local": (0, *REACH_TILE, Fraction(4)),
            "tiles.swim": (0, *REACH_TILE, Fraction(4)),
            "tiles.planek": (0, *REACH_TILE, streams[0], Fraction(4)),
        }
        workers = {name: instance._bookmarks[(name, subject)]
                   for name, subject in subjects.items()}
        steps["bookmarks_born"] = tuple(sorted(instance._bookmarks))
        steps["born"] = {name: worker.reads
                         for name, worker in workers.items()}
        instance._ingest(dataclasses.replace(
            _h3_facts.color_row(), capture_id=CAPTURE_B,
            page_cells_yx=REACH_CELLS,
            values=np.zeros((REACH_CELLS.shape[0], 3), np.float32)))
        instance._ingest(_verdict(streams[0], "below_attempt_floor",
                                  CAPTURE_B))
        steps["extended"] = {name: (worker.reads, worker.version)
                             for name, worker in workers.items()}
        steps["bookmarks_extended"] = tuple(sorted(instance._bookmarks))
        certificate = dataclasses.replace(
            _h3_facts.certificate(0, *NEW_NEIGHBOURS[-1]),
            stream_id=streams[1])
        instance._ingest(certificate)
        steps["woken"] = {name: worker.version
                          for name, worker in workers.items()}
    return steps


@pytest.mark.parametrize("name", RESIDUE_ROWS)
def test_a_new_colour_row_extends_every_residue_bookmark_it_covers(
        color_reach, name):
    born = color_reach["born"][name]
    reads, version = color_reach["extended"][name]
    assert color_reach["before_failure"] == 0
    assert not _attempt_keys(born, CAPTURE_B)
    assert _attempt_keys(reads, CAPTURE_B)
    assert set(NEW_NEIGHBOURS) <= set(_tile_keys(reads))
    assert not set(NEW_NEIGHBOURS) & set(_tile_keys(born))
    assert color_reach["woken"][name] > version
    assert (color_reach["bookmarks_extended"]
            == color_reach["bookmarks_born"])


@pytest.mark.parametrize("name", ("tiles.planek", "tiles.swim"))
def test_a_new_colour_row_brings_its_window_s_pose_to_the_sampling_rows(
        color_reach, name):
    reads, _version = color_reach["extended"][name]
    assert (KEY_POSE_AFFINE, color_reach["wid_b"]) in reads
    assert (KEY_POSE_AFFINE, color_reach["wid_b"]) \
        not in color_reach["born"][name]


@pytest.mark.parametrize("name", RESIDUE_ROWS)
def test_a_cover_change_names_only_tile_lanes_the_row_already_armed(name):
    """The guarantee the extension rests on: a cover subject is a
    subject this row's own failed verdict already births, so the
    engine's re-birth finds a bookmark and never makes one."""
    from holo.receiver.plugins import local_ctx

    streams = _color_streams()
    instance = _residue_engine(COLOR_FORMAT_REF)
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window(ordinal=0))
    row = engine.DESCRIPTOR_BY_NAME[name]
    covered = dataclasses.replace(_h3_facts.color_row(),
                                  page_cells_yx=REACH_CELLS,
                                  values=np.zeros((REACH_CELLS.shape[0], 3),
                                                  np.float32))
    instance._fold(covered)
    assert row.subjects_of(instance, covered) == ()
    failed = _verdict(streams[0], "attempted_failed", CAPTURE_ID)
    instance._fold(failed)
    assert set(row.subjects_of(instance, covered)) \
        == set(row.subjects_of(instance, failed))
    assert local_ctx.COVER_BIRTH_FACTS == (data.WindowEvidence,
                                           data.ColorEvidenceRow)


def test_an_unknown_fact_type_is_a_hard_error_and_never_a_silent_write():
    engine = _h3_facts.new_engine()
    with pytest.raises(data.IntegrityError, match="unknown fact type"):
        engine._fold(object())


@pytest.fixture(scope="module")
def write_map() -> dict[str, tuple[str, ...]]:
    return _h3_facts.fold_write_map()


def test_every_fact_type_writes_exactly_the_cells_it_is_pinned_to(write_map):
    _h3_support.assert_measured("fold write map", write_map, FOLD_WRITE_MAP)


def test_the_pinned_write_map_covers_every_fact_the_fold_dispatches():
    from holo.receiver import schedule

    assert set(schedule.fold_dispatch()) == set(FOLD_WRITE_MAP)


def _producers(write_map: dict[str, tuple[str, ...]]) -> dict[str, tuple]:
    found: dict[str, set[str]] = {}
    for fact_name, cells in write_map.items():
        for cell in cells:
            found.setdefault(cell, set()).add(fact_name)
    return {cell: tuple(sorted(names)) for cell, names in found.items()}


def test_each_store_cell_has_one_producing_fold_once_delegation_collapses(
        write_map):
    producers = _producers(write_map)
    checks = _h3_support.Checks("single writer by behaviour")
    for cell, names in sorted(producers.items()):
        collapsed = _collapsed(names)
        if cell in MULTI_WRITER_CELLS:
            checks.equal(f"{cell} keeps its declared writers", collapsed,
                         MULTI_WRITER_CELLS[cell])
            continue
        checks.equal(f"{cell} has exactly one producing fold", collapsed,
                     (collapsed[0],))
    checks.assert_clean()


@pytest.mark.parametrize("delegator,delegate", sorted(
    FOLD_DELEGATIONS.items()))
def test_a_declared_delegation_really_folds_through_its_delegate(
        write_map, delegator, delegate):
    theirs = set(write_map[delegate])
    mine = set(write_map[delegator])
    assert theirs & mine, (
        f"{delegator} is declared to fold through {delegate} and shares no "
        f"cell with it: the delegation is a fiction")
    # A delegation nests -- or, since 2026-10-03, the delegator re-folds
    # a HALF of its delegate's cells (the ctx catch-up corrects the read
    # side of standing rows and never re-covers a tile) beside cells
    # that are its alone.  Two independent writers cross on a cell some
    # third fold also writes, and that stays refused.
    own = mine - theirs
    others = {cell for name, cells in write_map.items()
              if name not in (delegator, delegate) for cell in cells}
    assert theirs <= mine or mine <= theirs or not own & others, (
        f"{delegator} and {delegate} write crossing cell sets: a delegation "
        f"nests, two independent writers cross")


def test_no_cell_is_written_by_a_fact_no_descriptor_and_no_fold_produces(
        write_map):
    written = {cell for cells in write_map.values() for cell in cells}
    unwritten = tuple(sorted(set(_h3_facts.STORE_CELLS) - written))
    _h3_support.assert_measured("store cells no fold writes", unwritten, ())
