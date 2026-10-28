from __future__ import annotations

import dataclasses

import pytest

from holo3 import data, engine
from holo3.descriptor import (
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
from holo3.plugins import refine
from holo3.tests import _h3_facts, _h3_support

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
    "Placement": ("_place_stages", "_placements", "_page_cells", "_pose_gen",
                  "_live_pages", "_lanes_on_page", "_lane_poses",
                  "_region_pitch"),
    "PlaceOutcome": ("_place_stages",),
    "LatticeSeed": ("_lattice_seeds",),
    "WindowEvidence": ("_evidence", "_tile_cover_k", "_window_cover"),
    "CtxOutcome": ("_evidence", "_region_ctx", "_tile_cover_k",
                   "_window_cover"),
    "RefineOutcome": ("_placements", "_pose_gen", "_lane_poses"),
    "ColorEvidenceRow": ("_color_rows", "_tile_cover_color",
                         "_color_row_cover"),
    "ColorLaneFit": ("_color_lane_assembled", "_color_lane_head",
                     "_color_lane_head_fits"),
    "ColorCtxPopulation": ("_color_pops", "_pop_lanes"),
    "PooledColorCtx": ("_pooled_ctx",),
    "Certificate": ("_certificates", "_equations"),
    "AttemptFact": ("_attempt_outcomes",),
    "PlaneField": ("_plane_fields",),
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
    engine._retire_worker(worker)
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


@pytest.fixture(scope="module")
def revisit_reach() -> dict:
    row = engine.DESCRIPTOR_BY_NAME["revisit"]
    steps: dict = {}
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(engine, "DESCRIPTORS", (row,))
        monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", {"revisit": row})
        instance = _h3_facts.new_engine()
        instance._ingest(_h3_facts.capture())
        instance._ingest(_h3_facts.window(wid=REACH_WID))
        instance._ingest(_reach_placement(0, 1.0))
        instance._ingest(_h3_facts.evidence(wid=REACH_WID,
                                            cells=REACH_CELLS,
                                            accepted=False))
        instance._ingest(_h3_facts.certificate(0, 0, 0))
        worker = instance._bookmarks[("revisit", REACH_WID)]
        steps["born"] = _reach_probe(instance, worker)
        instance._ingest(_reach_placement(REACH_SHIFT, 0.5))
        steps["revised"] = _reach_probe(instance, worker)
        instance._ingest(_h3_facts.certificate(0, *NEW_REACH[0]))
        steps["new_reach"] = _reach_probe(instance, worker)
        instance._ingest(_h3_facts.certificate(0, *OLD_REACH[3]))
        steps["old_reach"] = _reach_probe(instance, worker)
    return steps


def test_the_revisit_bench_is_born_subscribed_to_the_reach_of_its_pose(
        revisit_reach):
    assert refine.reach_tiles(REACH_CELLS) == OLD_REACH
    assert revisit_reach["born"]["tiles"] == OLD_REACH
    assert revisit_reach["born"]["indexed"] == OLD_REACH


def test_a_revised_pose_moves_the_revisit_subscription_to_its_new_reach(
        revisit_reach):
    assert revisit_reach["revised"]["tiles"] == NEW_REACH, (
        "reach follows the pose at runtime: a subscription set materialized "
        "at birth cannot see where the window went")
    assert revisit_reach["revised"]["indexed"] == NEW_REACH


def test_a_certificate_in_the_new_reach_wakes_the_revised_worker(
        revisit_reach):
    assert (revisit_reach["new_reach"]["version"]
            > revisit_reach["revised"]["version"])


def test_a_certificate_in_the_abandoned_reach_wakes_it_no_longer(
        revisit_reach):
    assert (revisit_reach["old_reach"]["version"]
            == revisit_reach["new_reach"]["version"])


def test_a_pose_revision_reindexes_a_worker_even_while_it_is_in_flight():
    row = engine.DESCRIPTOR_BY_NAME["revisit"]
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(engine, "DESCRIPTORS", (row,))
        monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", {"revisit": row})
        instance = _h3_facts.new_engine()
        instance._ingest(_h3_facts.capture())
        instance._ingest(_h3_facts.window(wid=REACH_WID))
        instance._ingest(_reach_placement(0, 1.0))
        instance._ingest(_h3_facts.evidence(wid=REACH_WID,
                                            cells=REACH_CELLS,
                                            accepted=False))
        instance._ingest(_h3_facts.certificate(0, 0, 0))
        worker = instance._bookmarks[("revisit", REACH_WID)]
        instance._frontier.clear()
        worker.inflight = True
        instance._ingest(_reach_placement(REACH_SHIFT, 0.5))
        indexed = tuple(sorted({
            (read[2], read[3]) for read, subscribers
            in instance._index.items()
            if read[0] == KEY_TILE
            and ("revisit", REACH_WID) in subscribers}))
        assert indexed == NEW_REACH
        assert worker.pending is True
        assert instance._frontier == []
        version_after_revision = worker.version
        instance._ingest(_h3_facts.certificate(0, *NEW_REACH[0]))
        assert worker.version > version_after_revision
        assert instance._frontier == []
        held = worker.version
        instance._ingest(_h3_facts.certificate(0, *OLD_REACH[3]))
        assert worker.version == held


def test_an_unknown_fact_type_is_a_hard_error_and_never_a_silent_write():
    engine = _h3_facts.new_engine()
    with pytest.raises(data.IntegrityError, match="unknown fact type"):
        engine._fold(object())


@pytest.fixture(scope="module")
def write_map() -> dict[str, tuple[str, ...]]:
    return _h3_facts.fold_write_map()


def test_every_fact_type_writes_exactly_the_cells_it_is_pinned_to(write_map):
    _h3_support.assert_golden("fold write map", write_map, FOLD_WRITE_MAP)


def test_the_pinned_write_map_covers_every_fact_the_fold_dispatches():
    from holo3 import schedule

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
    assert theirs <= mine or mine <= theirs, (
        f"{delegator} and {delegate} write crossing cell sets: a delegation "
        f"nests, two independent writers cross")


def test_the_only_shared_cell_left_is_the_place_stage_record(write_map):
    producers = _producers(write_map)
    shared = {cell for cell, names in producers.items()
              if len(_collapsed(names)) > 1}
    _h3_support.assert_golden("cells with more than one producing fold",
                              tuple(sorted(shared)),
                              tuple(sorted(MULTI_WRITER_CELLS)))


def test_no_cell_is_written_by_a_fact_no_descriptor_and_no_fold_produces(
        write_map):
    written = {cell for cells in write_map.values() for cell in cells}
    unwritten = tuple(sorted(set(_h3_facts.STORE_CELLS) - written))
    _h3_support.assert_golden("store cells no fold writes", unwritten, ())
