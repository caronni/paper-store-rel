"""VERDICT 4 (run banded): the ladder places windows the word code refuses.

The page carries a 16% cell error band over its right quarter — a channel
fact, not a staging knob (the M281's known horizontal banding produces
exactly this). The two admissions sit at very different error rates: a
Stage-A word is 100 sites under a t = 13 BCH code and dies past ~13%,
while the seeded search's gate is a weighted mismatch over every site of
the window against bars of 0.20/0.24 and survives to ~20%. So the band
bites the WORD in the columns it covers and leaves the seeded admission
intact.

What must then happen, and what this file asserts:

1. the word slots seed the page — some windows decode their own address;
2. an acceptance PINGS its ring (and the finer windows it covers), which
   is the entire message: no mailbox, no hint record, one bit;
3. a pinged window prices at the RING tier (cost 10, below the word tiers
   at 20/30), claims, consults the COMMITTED POSES around it at fire
   time, extrapolates, sorts by the ratified distance, and runs the
   carried 49-hypothesis local search on the best seeds;
4. the band DEFEATS the word admission where it lies and nowhere else,
   and every window under it is placed by the ladder instead;
5. and the volume still comes back byte-exact through the real close.

THE SPLIT IS EVIDENCE, THE PROBE IS THE DISCRIMINATOR. The route split is
asserted exactly, on the serial lane, because it is the migration
evidence — but by itself it says nothing about the band: under pull
pricing the ring tier (10) undercuts both word tiers, so the first
acceptance pings its ring and everything else arrives by chain whether or
not a band exists, and run channel measures the SAME split with no band
at all (``test_v1_parity``). MEASURED HERE, from this run's own pass
census: no
window under the band ever spent a word stage — the ladder reached them
first — so the band's bite has to be measured directly, and the last test
does exactly that against the same capture.

WHAT THAT PROBE MEASURED, so the verdict claims no more than it has: at
the stage the ladder spends FIRST (Stage A over the centre slots), the
word code refuses under the band and reads every window outside it. It is
a bite, not an execution — the same window decodes under the much wider
Stage-A REST sweep, which is one tier dearer and which no window of this
run ever reached. So the honest sentence is "the ladder places what the
word code refuses at the price the ladder was reached at", and a run that
had to buy the rest sweep for these windows would have paid for the band
twice over.

WHAT IS NOT HERE, and deliberately: the push era's durable half. A pull
job takes no spend row and writes no hint, so there is nothing to look up
in the ledger — which this file pins as an ABSENCE (see the last test),
because a scheduling fact that quietly came back would otherwise be
invisible.

RF1 IS LIVE ON THIS ARM SINCE W3 (2026-08-23, RULINGS I2/I3), and it is
the first verdict file where that shows: six of the eighteen placed
windows carry a committed pose REVISION beside their placement. So every
pose-keyed reading here splits the two — by EVIDENCE, since a placement
observed cells and a revision samples nothing — and "one pose per
window" becomes "one LIVE pose per window", which is the ruling itself.
No number in this file was relaxed to absorb it: the placements are
still exactly 18, the route split is still exactly the same dict, and
the revisions are counted rather than tolerated.
"""
from __future__ import annotations

from collections import Counter

import numpy as np

from conftest import PX_PER_DOT, PageRun, open_state

from holo2.capture import ingest_capture
from holo2.cli import real_source
from holo2.core import ProgressSink
from holo2.solve import (KIND_EVIDENCE, WindowStatus, parse_evidence_key,
                         parse_tile_key, parse_window_key)
from holo2.solve.place_shared import sample_window
from holo2.solve.placement import (FAMILY_PLACE, STAGE_CENTRE,
                                   decode_word_address)
from holo2.solve.tilemap import StoreIndex, TileMap

#: The per-window pose bar, in CELLS, evaluated at the corners of the
#: tiles a pose actually addressed. Half a cell is the point at which the
#: aperture would start reading a neighbour.
POSE_TOLERANCE_CELLS = 0.5

#: MEASURED on this fixture, serial (H4 W2's pull model). RE-DECLARED at
#: H4-LANES stage 2, once, with its cause: this run reads the DEFAULT
#: reading set now, which on c2 at 1200 dpi is a two-rung ladder, so the
#: nine window extents are eighteen window PLANS and the split is over
#: seventeen poses instead of nine. The mechanism is unchanged and is
#: what the number shows: one window seeds the page from its own address
#: word, and everything else — including every window of the finer lane —
#: arrives through the ladder, because a colocated coarse pose scores
#: distance 0 and is the strongest steer there is. Both halves must stay
#: non-zero or the arm is measuring something else. It is migration
#: evidence and NOT the band's verdict (module docstring): run channel
#: measures this same split, on one lane, with no band on the page.
#: RE-DECLARED AGAIN at H5 (2026-08-19) with the re-work aging, whose
#: cause is spelled out under ``EXPECTED_POSES``: the chain half gains the
#: one window that used to exit done-covered before its own pass fired.
EXPECTED_SPLIT = {"word": 1, "chain": 17}

#: The window PLANS this page lays down, and the poses they produce.
#: RE-DECLARED with the reading set (H4-LANES stage 2): nine extents on
#: each of two rungs.
#:
#: RE-DECLARED AGAIN at H5 (2026-08-19), and the cause is the RE-WORK
#: AGING. One finer-lane window used to be RETIRED done-covered — its
#: whole supported extent had certified through the coarse lane's poses
#: before its own pass fired. On THIS page the certificates that covered
#: it come from RE-attempts (that is what a 16% band buys: retries and
#: unions), and a re-attempt now prices into the band above every word
#: tier, so the window's own placement pass reaches it first and places
#: it. Every plan is placed here now.
#:
#: That is the ruled trade, stated in its own units: a re-decode waits
#: until the cheaper bands have drained, which buys it maximal
#: accumulated evidence and costs the done-exit a customer. It is a
#: SCHEDULE fact and nothing else — the volume still closes byte-exact
#: (the first test in this file) and no certificate moved.
EXPECTED_PLANS = 18
EXPECTED_POSES = 18
EXPECTED_EXTENTS = 9

#: RF1's own census on this arm, MEASURED at W3 (2026-08-23) when
#: ``revise`` became the default. A committed pose is either a PLACEMENT
#: (it observed cells and its evidence names them) or a REVISION (it
#: observed nothing — RF1 proposes geometry and samples no pixel), so the
#: two are told apart by evidence and never by a marking.
#:
#: This is a CENSUS, not a law: six of the eighteen placed windows had a
#: reach RF1 found eligible and a fit it adopted, and the number is
#: pinned so a change in what refinement does on a biting page is loud.
#: The LAW beside it is the one that must never move — one LIVE pose per
#: window, every revision on a window that already carries a placement.
EXPECTED_REVISIONS = 6

#: HOW MANY OF THOSE REVISIONS WERE RE-READ, MEASURED at F2a
#: (2026-08-23, ruling J2-3). Through F1 a revision bought nothing: it
#: was committed and no pass ever sampled through it. F2a re-reads a
#: revised window's own cells at its live pose, so a revision now owns
#: evidence — which is why ``_placements`` no longer splits on evidence.
#: A CENSUS, like the line above it, and the LAW beside it is that a
#: re-read revision owns pieces at its OWN pose while the parent's stay
#: committed and stop decoding (``solve.generation``).
EXPECTED_REREADS = 6

#: The first tile column the band covers. The band runs over the right
#: quarter of an 8-tile page, so a window that observed a tile at or past
#: this index read banded cells.
FIRST_BANDED_TX = 6


def test_the_volume_closes_byte_exact_through_the_band(
        run_banded: PageRun) -> None:
    """The bar is the wave's own: this tool works, on a page that bites."""
    outcome = run_banded.outcome
    assert outcome.status == "verified", outcome.reason
    assert outcome.payload == run_banded.page.payload
    # The corrupted columns are the FOUNTAIN's job, not placement's: the
    # page is fully placed and only partly certified, and it still closes.
    assert outcome.certified < run_banded.page.tiles_per_page, (
        "the band certified everything, so it is not biting at all")


def _placements(session) -> tuple[dict, dict]:
    """This run's poses split into PLACEMENTS and REVISIONS.

    RE-PINNED F2a (2026-08-23, ruling J2-3). W3 took the split off
    EVIDENCE — "a revision proposes geometry and samples nothing, so it
    owns no piece" — and that stopped being true the moment the re-read
    landed: a revised window is re-sampled through its live pose and the
    revision owns pieces like any other pose. The split now reads the
    thing that did not move, and it is still off the records with nothing
    marked: an extent carries at most two committed poses
    (``refine.Reach.revised``), so its LIVE pose is a revision exactly
    when the extent carries more than one.

    Returns ``{pose key: [tile column, ...]}`` for every pose that OWNS
    EVIDENCE — placements and re-read revisions alike — and
    ``{pose key: PoseRecord}`` for the revisions.
    """
    index = StoreIndex.build(session.store)
    columns: dict[object, list[int]] = {}
    for key in session.store.keys():
        if key.kind == KIND_EVIDENCE:
            _f, _p, _ty, tx, _s, pose_id = parse_evidence_key(key)
            columns.setdefault(pose_id, []).append(tx)
    revisions = {
        key: pose for key, pose in index.poses.items()
        if len(index.poses_by_window.get(pose.window_id, ())) > 1
        and index.live_pose(pose.window_id) == key}
    return columns, revisions


def test_every_window_is_placed_and_the_ladder_placed_the_rest(
        run_banded: PageRun) -> None:
    """The migration, whole: word seeds, ping wakes, the seeded search lands.

    A WINDOW is a (footing, region, extent) since the lanes went live, so
    the counts below are over window plans and not over extents — the two
    were the same number while the receiver read one lane, and telling
    them apart is what makes "one live pose per window" still say
    something.

    RE-PINNED W3 (2026-08-23, RULINGS I2/I3): RF1 is on by default, so a
    window may carry more than one committed pose. "One pose per window"
    becomes **one LIVE pose per window** — the ruling, not a loosening —
    and the extra poses are accounted for as revisions rather than
    tolerated: each observed nothing, each sits on a window that already
    carries a placement, and each IS its window's live pose.
    """
    with run_banded.open() as session:
        index = StoreIndex.build(session.store)
        poses = tuple(index.poses.values())
        windows = {key for key in session.store.keys()
                   if key.kind == "window"}
        placed = {pose.window_id for pose in poses}
        columns, revisions = _placements(session)
    # ONE LIVE POSE PER WINDOW — the no-double-place law, at rest. Several
    # passes fired on most of these windows and exactly one of them ever
    # committed a PLACEMENT.
    assert len(placed) == EXPECTED_POSES, (
        f"poses over {len(placed)} windows, expected {EXPECTED_POSES}")
    # POSES THAT OWN EVIDENCE = placements + the revisions F2a re-read.
    assert len(columns) == EXPECTED_POSES + EXPECTED_REREADS, (
        f"{len(columns)} poses own evidence over {len(placed)} windows")
    assert len(index.live_poses) == EXPECTED_POSES, (
        f"{len(index.live_poses)} live poses over {EXPECTED_POSES} windows")
    # And every extra pose is a revision, on a placed window, and live.
    assert len(revisions) == len(poses) - EXPECTED_POSES == (
        EXPECTED_REVISIONS), f"{len(revisions)} revisions of {len(poses)} poses"
    for key, revision in revisions.items():
        assert revision.window_id in placed, (
            "a revision of a window nothing ever placed")
        assert index.live_pose(revision.window_id) == key, (
            "the revision is not its own extent's live pose")
    # F2a: a revision is READ, or it is still owed a re-read — and a
    # re-read revision owns pieces at its own geometry, so the two
    # generations coexist in the store and only the live one decodes
    # (``solve.generation``).
    assert len([key for key in revisions if key in columns]) == (
        EXPECTED_REREADS), (
        f"{len([key for key in revisions if key in columns])} of "
        f"{len(revisions)} revisions were re-read")
    assert len(windows) == EXPECTED_PLANS, (
        f"{len(windows)} window records for {EXPECTED_PLANS} plans — every "
        "plan records an outcome, placed or retired")
    # The same NINE printed extents, read through two rungs: the lanes
    # are extra trajectories over one page, not a bigger page.
    assert len({parse_window_key(key)[2] for key in windows}) == (
        EXPECTED_EXTENTS)
    assert len({parse_window_key(key)[0] for key in windows}) == 2, (
        "this run is supposed to read a two-rung ladder")

    # Attribution is over PLACEMENTS: ``routes`` observes the placement
    # job, and a revision is not one of its passes.
    attributed = Counter(run_banded.routes[key] for key in columns
                         if key not in revisions)
    assert attributed["word"] > 0, "the page was never seeded from nothing"
    assert attributed["chain"] > 0, (
        f"no window arrived through the ladder: {dict(attributed)} — the "
        "band is not biting, or the ping never reached anyone")
    assert dict(attributed) == EXPECTED_SPLIT, (
        f"the route split moved to {dict(attributed)}")


def test_a_ladder_placed_window_is_indistinguishable_from_a_word_one(
        run_banded: PageRun) -> None:
    """One job, two ways to an address — and nothing else differs.

    The ladder decides WHICH address a window is tested against and
    nothing else, so what a seeded acceptance leaves behind must be
    exactly what a word acceptance leaves behind: a pose inside the pose
    tolerance of the truth pose the page was rendered under, and evidence
    pieces citing it.
    """
    truth = np.array(run_banded.capture.native_affine)
    pitch = run_banded.page.cell_dots * PX_PER_DOT
    with run_banded.open() as session:
        index = StoreIndex.build(session.store)
        owned: dict[object, list[tuple[int, int]]] = {}
        for key in session.store.keys():
            if key.kind == KIND_EVIDENCE:
                _f, _p, ty, tx, _s, pose_id = parse_evidence_key(key)
                owned.setdefault(pose_id, []).append((ty, tx))
        # PLACEMENTS only. Through W3 that was implied ("a revision
        # emits no evidence"); since F2a a re-read revision DOES own
        # tiles, and it has no route — the placement job did not address
        # it, it re-read an address the job committed. ``routes.get``
        # is what tells the two apart, and it is the run's own record.
        ladder = [index.poses[key] for key in owned
                  if run_banded.routes.get(key) == "chain"]
        assert ladder
        for pose in ladder:
            tiles = owned.get(pose.resource_key(), [])
            assert tiles, "a seeded acceptance emits evidence like any other"
            got = np.array(pose.native_affine)
            worst = 0.0
            for ty, tx in tiles:
                for dy in (0, 64):
                    for dx in (0, 64):
                        cell = np.array([ty * 64 + dy, tx * 64 + dx, 1.0])
                        mine = np.array([got[:3] @ cell, got[3:] @ cell])
                        real = np.array([truth[:3] @ cell, truth[3:] @ cell])
                        worst = max(worst, float(np.max(np.abs(mine - real))))
            assert worst / pitch < POSE_TOLERANCE_CELLS, (
                f"seeded pose residual {worst / pitch:.3f} cells")


def test_the_certificates_the_band_left_standing_are_the_truth(
        run_banded: PageRun) -> None:
    """DESIGN §12 on the arm most likely to break it. Never relaxed."""
    page = run_banded.page
    with run_banded.open() as session:
        tiles = TileMap(StoreIndex.build(session.store),
                        page.row.stream_ids, page.tiles_yx)
        certified = tiles.certified_keys()
        assert certified
        for key in certified:
            _number, ty, tx, _stream = parse_tile_key(key)
            np.testing.assert_array_equal(
                session.store.read_array(tiles.record(key).bits_ref),
                page.truth_bits(ty, tx))


def _banded_windows(run: PageRun) -> tuple[dict, dict]:
    """Split the run's placed windows by whether the band covers them.

    The split is read off what each pose OBSERVED — the tile columns its
    evidence pieces name — so it is the run's own record of which windows
    read banded cells, not a geometry the test re-derives. Which is also
    why it walks the PLACEMENTS since W3: an RF1 revision observed
    nothing, so there is no side of the band for it to be on.
    """
    with run.open() as session:
        index = StoreIndex.build(session.store)
        columns, _revisions = _placements(session)
        banded, clear = {}, {}
        for key, seen in columns.items():
            if key in _revisions:
                continue           # F2a: a re-read has no route of its own
            side = banded if max(seen) >= FIRST_BANDED_TX else clear
            side[index.poses[key].window_id] = run.routes[key]
    return banded, clear


def test_the_band_defeats_the_word_admission_where_it_lies(
        run_banded: PageRun) -> None:
    """THE DISCRIMINATOR: what the word code can actually read here.

    The route split cannot say this (module docstring) and neither can
    the run's pass census: no window under the band ever spent a word
    stage, because the ladder reached all of them first. So the bite is
    measured directly, on the SAME capture, through a fresh ingest of it
    — every window's own patch, and the word decode the ladder would have
    spent FIRST on it (Stage A over the centre slots, at the budget a
    first pass declares: ``pass_budget`` over one candidate is the base
    budget, so this is that pass exactly).

    Both halves are the verdict. The word code must refuse SOMEWHERE
    under the band, or the band is not biting the admission this arm is
    about; and it must read every window OUTSIDE the band, or something
    other than the band is what broke it.
    """
    banded, clear = _banded_windows(run_banded)
    # RE-DECLARED with the reading set (H4-LANES stage 2): the same three
    # banded extents, read through two rungs. The CLEAR half is stated
    # against ``EXPECTED_POSES`` rather than as a second literal, so H5's
    # extra placed window moves one number in one place — what this arm
    # is about is which side of the band a window sits on, and that split
    # is unchanged.
    assert len(banded) == 6, (
        f"the band covers {len(banded)} of {len(banded) + len(clear)} "
        "windows; the fixture's geometry moved")
    assert len(banded) + len(clear) == EXPECTED_POSES
    assert set(banded.values()) == {"chain"}, (
        f"a window under the band was placed by the word code: {banded}")

    scheduler = real_source(run_banded.page.row)
    fresh = open_state(run_banded.state_dir.parent / "word-probe", run_banded.page.row,
                       run_banded.scans)
    read: dict[object, bool] = {}
    with fresh as session:
        # A FRESH INGEST of the same capture, in the two halves streaming
        # ingestion split it into (H4): the derivation-plus-wall that
        # an ingest fire's proposal amounts to, and the attach-by-reopen
        # the committing thread takes when that capture record lands. A
        # brand-new state directory holds no capture records, so without
        # them this plane would have no windows to probe at all.
        capture = ingest_capture(session.engine, run_banded.capture.path,
                                 run_banded.capture.dpi,
                                 run_banded.page.row.pitch_in)
        session.plane.attach_captures([capture.source_sha256])
        plane = session.plane
        for footing_id in plane.footing_ids("all"):
            for plan in plane.window_plans(footing_id):
                if plan.window_id not in banded and plan.window_id not in clear:
                    continue
                sampled = sample_window(plane, plan, config=scheduler.config,
                                        progress=ProgressSink("word-probe"))
                assert sampled.patch is not None, sampled.refusal
                read[plan.window_id] = decode_word_address(
                    sampled.patch, scheduler.spec, run_banded.page.row,
                    stage=STAGE_CENTRE, word_budget=scheduler.word_budget,
                    budget=scheduler.budgets.local,
                    reference=scheduler.reference,
                    config=scheduler.config,
                    progress=ProgressSink("word-probe")) is not None

    assert set(read) == set(banded) | set(clear), "a window was never probed"
    assert not all(read[window] for window in banded), (
        "the word code read every banded window at the stage the ladder "
        "spends first — the band is not biting the word admission at all, "
        "and this arm is measuring pricing rather than the channel")
    assert all(read[window] for window in clear), (
        "the word code failed OUTSIDE the band, so the band is not what "
        "defeats it: this fixture no longer isolates the mechanism")


def test_placement_left_no_scheduling_state_behind(run_banded: PageRun) -> None:
    """Q1/Q2/Q4: readiness, seeds and the tried set never cross the wall.

    Three absences, each of which was a durable record before the pull
    model: a pull job takes NO spend row (repetition is bounded by the
    source's flag and its tried set, not by the ledger), it declares no
    subscription, and the window record it leaves is an OUTCOME — placed
    (``ACTIVE``, its pose the witness) or retired with a reason, never a
    scheduling status. A failed pass writes nothing at all.
    """
    with run_banded.open() as session:
        store = session.store
        place_spends = [row for row in store.ledger.entries()
                        if row.worker_id.family == FAMILY_PLACE]
        assert not place_spends, (
            f"{len(place_spends)} placement spend row(s) — a pull job is "
            "bounded by its source's flag, not by the ledger")
        place_subscriptions = [worker_id
                               for worker_id in store.subscriptions()
                               if worker_id.family == FAMILY_PLACE]
        assert not place_subscriptions, (
            "a pull job subscribes to nothing; the ping is the message")
        statuses = Counter(store.get(key).status
                           for key in store.keys() if key.kind == "window")
        assert set(statuses) <= {WindowStatus.ACTIVE, WindowStatus.RETIRED}
        # RE-DECLARED with the reading set, and again at H5 with the
        # re-work aging (``EXPECTED_POSES`` carries the cause): all
        # eighteen plans over two rungs are placed here now, where the
        # eighteenth used to be RETIRED done-covered. The property this
        # test is about is untouched — every plan records an OUTCOME and
        # never a scheduling status — and the arithmetic still says so
        # with the done-exit's customer count at zero.
        assert statuses[WindowStatus.ACTIVE] == EXPECTED_POSES, (
            "every placed window records its outcome, and only those")
        assert statuses[WindowStatus.RETIRED] == (
            EXPECTED_PLANS - EXPECTED_POSES)
        assert sum(statuses.values()) == EXPECTED_PLANS, (
            "a window plan left no record at all")
