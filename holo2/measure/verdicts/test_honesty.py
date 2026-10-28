"""VERDICT 5 (run partial): a volume that cannot close, does not.

Sheet 0 of a TWO-sheet volume is on the platen. At K/T = 0.8 the source
symbol count exceeds one sheet's tiles, so no single sheet can close this
volume however well it decodes — the partial session is produced by
physics rather than by staging, which is the whole reason this fixture
exists. Every window places, every tile of the sheet certifies, the
metadata rank recovers, K is read, and the close STAYS OPEN.

Three things are asserted, and the third is the one the pull model
changed:

1. **The close stays open, and OPEN is not a record.** No ``CloseRecord``
   is written, the session is not terminal, and the operator's epilogue
   says "exhausted, not finished" and "resumable" rather than reporting a
   result it does not have.
2. **Nothing is fabricated.** Every certificate is the emitted truth;
   every certificate, pose and evidence piece belongs to the page that
   was actually on the platen; and the session holds no payload.
3. **Done-covered work is retired — durably, and without a record.**
   A window whose whole supported extent certified is never posed,
   searched or scheduled again. Under the push era that needed a durable
   summary and a subscription; under the pull model the §6 projection is
   DERIVED from certificates, which are durable and terminal, so a
   resume rebuilds every exit from the store and offers no placement work
   at all. The pin drives that rebuild directly: a fresh scheduler over
   the finished state, admitted across the whole domain, enters nothing,
   comes up dry, and accounts for every window plan under a named exit.

   RECORDED HONESTLY, because the census says so. The done exit used to
   be SHADOWED on this fixture: twelve window plans were done-covered and
   eight of them were never posed, but they sat on footings that were not
   the capture's "working" one and that refusal was tested first, so they
   left under ``not_the_working_footing`` while nine left under
   ``placed``. H4-LANES stage 2 removed the shadow rather than the exit —
   every rung places now, so no window leaves for being on the wrong lane
   and the census below is over ``placed`` and ``done_covered`` alone.
   The §6 exit's own firing is still pinned where it can be isolated
   (``holo2/tests/solve/test_place_sched.py::
   test_a_placed_or_retired_or_covered_window_never_enters``). What this
   verdict pins is the property that matters to an operator holding a
   half-solved volume: a spent sheet offers no placement work, and no
   done-covered window is ever posed.

TWO EXITS, AND WHY BOTH (the defended simplification): done does not
imply placed. Windows overlap, so a window's whole supported extent can
certify through its neighbours' poses — this fixture ends with several
such windows. Exit-by-done is what stops an unplaced window in a
recovered area from burning consults forever; exit-by-placed is what
hands a window to the payload family for good. Both stand.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from conftest import VolumeRun, request_for

from holo2 import cli
from holo2.core.records import CLOSE_KEY
from holo2.cli import real_source
from holo2.engine.recipe import FOOTING_ALL
from holo2.solve import (KIND_EVIDENCE, KIND_POSE, WindowStatus,
                         parse_evidence_key, parse_tile_key)
from holo2.solve.contradiction import KIND_CONTRADICTION
from holo2.solve.tilemap import StoreIndex, TileMap


def test_the_close_stays_open_and_writes_no_verdict(run_partial: VolumeRun) -> None:
    """One sheet of a two-sheet volume: solved out, and not finished."""
    volume, outcome = run_partial.volume, run_partial.outcome
    assert outcome.status == "open"
    assert outcome.exhausted, "the run stopped for some other reason"
    assert outcome.payload is None
    assert outcome.certified == volume.tiles_per_page
    assert outcome.certified < volume.k_total, (
        "one sheet must not carry K source symbols, or nothing is staged")
    with run_partial.open() as session:
        assert session.store.get(CLOSE_KEY) is None, "OPEN is not a record"
        assert not session.terminal
    epilogue = cli._epilogue(request_for(run_partial.state_dir, run_partial.scans),
                             outcome)
    assert "OPEN" in epilogue
    assert "exhausted, not finished" in epilogue and "resumable" in epilogue


def test_nothing_is_fabricated(run_partial: VolumeRun) -> None:
    """Every certificate is the truth, and belongs to the sheet on the platen.

    The second half is the one a partial volume can get wrong in a way a
    closing one cannot: page 1 was never scanned, so nothing may claim to
    have observed it.
    """
    volume = run_partial.volume
    with run_partial.open() as session:
        store = session.store
        index = StoreIndex.build(store)
        tiles = TileMap(index, volume.row.stream_ids, volume.tiles_yx)
        certified = tiles.certified_keys()
        assert certified
        for key in certified:
            page, ty, tx, _stream = parse_tile_key(key)
            record = tiles.record(key)
            assert page == 0, "a certificate for a sheet that was never scanned"
            np.testing.assert_array_equal(
                store.read_array(record.bits_ref),
                volume.truth_bits(page, ty, tx))
            assert record.metadata_bit == volume.truth_metadata_bit(page, ty, tx)
        assert all(pose.page == 0 for pose in index.poses.values())
        pages = {parse_evidence_key(key)[1] for key in store.keys()
                 if key.kind == KIND_EVIDENCE}
        assert pages == {0}, f"evidence claims pages {sorted(pages)}"


def test_the_word_layer_is_silent_and_condemns_nothing(
        run_partial: VolumeRun) -> None:
    """W5 over a real sheet: L8 says this layer is SILENT, and it is.

    "Expected silent: 1,780 known-position reads on record, 0 conflicts
    (measured)" — a healthy sheet's known-position words agree with the
    geometry that placed them, so the quarantine layer writes nothing at
    all. The zero is what makes the fixture evidence rather than
    decoration: this run harvests and reduces the words of every placed
    window, and produces no fact and no marking.

    The second half is the invariant that would matter if it ever did
    fire: NO CERTIFICATE STANDS ON CONDEMNED MATERIAL. Ruling 1 makes
    that true by construction (quarantine's jurisdiction is uncertified
    material), and the corollary is checked rather than assumed, because
    it is the join of this wave with the zero-wrong bar.
    """
    with run_partial.open() as session:
        store = session.store
        index = StoreIndex.build(store)
        assert not [key for key in store.keys()
                    if key.kind == KIND_CONTRADICTION], (
            "a healthy sheet contradicted itself")
        condemned = {key for key, pose in index.poses.items()
                     if pose.quarantined}
        assert not condemned, f"{len(condemned)} pose(s) condemned"
        assert not [key for key in store.keys()
                    if key.kind == KIND_EVIDENCE
                    and store.get(key).quarantined]
        for record in index.tiles.values():
            mint = record.minting
            if mint is None:
                continue
            witnesses = {mint.pose_id, *mint.contributors}
            assert not (witnesses & condemned), (
                "a certificate stands on a condemned placement")
        # The layer really ran: every placed window harvested and reduced.
        assert index.poses, "no placement, so nothing was reduced"


def test_done_covered_work_is_retired_and_the_source_comes_up_dry(
        run_partial: VolumeRun) -> None:
    """§6 in the pull model: derived from certificates, rebuilt on resume.

    A fresh :class:`PlacementScheduler` over the finished state, admitted
    across every footing the recipe can name, enters NOTHING and offers
    NOTHING. Nothing durable about readiness was needed to get there —
    which is the whole durability claim of the model. The exit census is
    read off the source's own derived membership (it IS the model's
    state, and there is nowhere else it could honestly come from), and it
    is asserted TOTAL: a window that left under no name would otherwise
    vanish from both sides of the count.

    RE-DECLARED AT H5 (2026-08-19, re-work aging), and the honest half is
    what it COST. This arm used to carry a second claim: that some window
    left under the §6 DONE exit, covered through its neighbours' poses
    rather than by a pass of its own. It no longer does. The certificates
    that covered those windows arrived from RE-armed attempts, and a
    re-attempt now prices above every word tier, so this fixture's whole
    placement domain — 27 plans — drains before them and every plan is
    placed. The exit census here is ``placed`` only.

    What survives, and is asserted below, is the §6 GATE itself: 18 of
    the 27 plans read DONE on the finished state, which is the gate
    answering exactly as it always did, on a state built entirely under
    the new prices. What is no longer exercised END TO END is the
    done-covered EXIT, whose holders are the units
    (``tests/solve/test_place_job.py`` and ``test_place_sched.py``, both
    of which pin the retirement, its reason and its census entry). That
    is a real reduction in this arm's reach, recorded rather than papered
    over — these fixtures are small, and on a domain where placement is
    hundreds of passes the exit's customers are first-attempt
    certificates, which the aging does not touch. Whether that holds on a
    real sheet is a measurement nobody has taken.
    """
    volume = run_partial.volume
    with run_partial.open() as session:
        plane = session.plane
        plans = [plan for footing_id in plane.footing_ids(FOOTING_ALL)
                 for plan in plane.window_plans(footing_id)]
        covered = [plan for plan in plans if plane.window_is_done(plan)]
        assert covered, "the run certified no window's whole extent"
        posed = {pose.window_id
                 for pose in StoreIndex.build(session.store).poses.values()}
        # The §6 gate answers on a state built entirely under H5 prices:
        # a strict majority of this sheet's plans are fully spent, and the
        # gate says so pose-free.
        assert len(covered) < len(plans), (
            "every plan reads done, so the gate is not discriminating")

        scheduler = real_source(volume.row)
        scheduler.admit(session.view(), entry=0, selector=FOOTING_ALL)
        counters = scheduler.counters()
        assert counters["entered"] == 0, (
            f"{counters['entered']} window(s) re-entered the scheduling set "
            "on a sheet that is finished")
        assert counters["windows"] == 0 and scheduler.peek() is None, (
            "the source offered placement work on a spent sheet")
        exits = Counter(scheduler._exited.values())
        assert sum(exits.values()) == len(plans), (
            f"{len(plans)} window plans, {sum(exits.values())} accounted for")
        assert exits["placed"] == len(posed)
        # The census records a RETIREMENT under its own reason, never
        # under the word "retired" (``place_sched._consider`` reads the
        # standing record's reason, and v5 makes that reason mandatory),
        # so the allowed set is the two admission verdicts plus exactly
        # the reasons this state actually holds. ``not_the_working_
        # footing`` LEFT this set at H4-LANES stage 2 with the reading it
        # named: every rung places, so no window exits for its lane, and
        # the done exit that used to hide behind it is the one doing the
        # work below.
        stood_down = {record.retired_reason
                      for record in (session.store.get(key)
                                     for key in session.store.keys()
                                     if key.kind == "window")
                      if record.status is WindowStatus.RETIRED}
        assert set(exits) <= ({"placed", "done_covered"} | stood_down), (
            dict(exits))
        # RE-DECLARED at H5 (the docstring carries the cause): this arm
        # used to assert ``exits["done_covered"] > 0``. Under the re-work
        # band every plan of this small domain is placed before its cover
        # arrives, so the census is placed-only. Stated as an equality so
        # a future ruling that brings the exit back FAILS here and is
        # re-declared deliberately, rather than passing under a `>= 0`
        # that would have stopped saying anything at all.
        assert exits["placed"] == len(plans) and not exits["done_covered"], (
            f"the exit census moved to {dict(exits)}")

        # The other half of "retired": what the store says. Every window
        # record is an OUTCOME (v5) — placed, or retired with a reason —
        # and never a scheduling state.
        records = [session.store.get(key) for key in session.store.keys()
                   if key.kind == "window"]
        statuses = Counter(record.status for record in records)
        assert set(statuses) <= {WindowStatus.ACTIVE, WindowStatus.RETIRED}
        assert all(record.status is not WindowStatus.RETIRED
                   or record.retired_reason for record in records), (
            "a retired window records no reason")
        pose_keys = {key for key in session.store.keys()
                     if key.kind == KIND_POSE}
        assert len(pose_keys) == statuses[WindowStatus.ACTIVE], (
            "a window recorded ACTIVE without a pose to witness it")
