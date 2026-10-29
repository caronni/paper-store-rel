"""The place row's lifecycle: subdivision, dormancy and the afterlife.

Split out of `test_h3_lifecycle` at the 1000-line seam (S7,
2026-10-03): that module keeps the laws that hold for EVERY row --
the generic engine, the push door, reads fixed at birth, every fact a
re-arm or terminal, retire monotone -- and this one the per-row
behaviour of `place`: the quartering rung, the parent/child settle the
store routes, the sleep a refusal stamps, and the afterlife.  Every
test here drives an in-memory engine through its own doors (`_ingest`,
`_push_worker`, `_fill`, `_merge`), never a decode.
"""
from __future__ import annotations

import ast
import dataclasses
import heapq
import tempfile
from concurrent.futures import Future
from pathlib import Path

import numpy as np

import pytest

from holo.receiver import data, engine
from holo.receiver.descriptor import KEY_PLACE_STAGE, KEY_WINDOW_DONE
from holo.receiver.plugins import place, place_pass, place_sched, refine
from holo.receiver.tests import _h3_facts

# ------------------------------------------- subdivision and the afterlife

def _place_engine() -> engine._Engine:
    request = data.DecodeRequest(
        scans=(Path("scan.tiff"),), dpis=(1200.0,),
        format_ref=_h3_facts.FORMAT_REF, max_pages=1, workers=1,
        complete=False, no_close=False, diag_port=None,
        run_dir=Path(tempfile.mkdtemp(prefix="h3-lifecycle-")))
    instance = engine._Engine(request, [])
    instance._ingest(_h3_facts.capture())
    # the shared survey supports an 85x85 corner, which leaves the one
    # full window with a single supported quarter; subdivision needs
    # four, so this fixture's region is supported edge to edge.
    instance._ingest(dataclasses.replace(
        _h3_facts.survey(),
        regions=(dataclasses.replace(_h3_facts.survey().regions[0],
                                     cells=np.ones((64, 64), bool)),)))
    return instance


def _exhaust(instance: engine._Engine, wid: tuple) -> None:
    """Spend every POSE rung this window's ladder offers, unplaced.

    `cold_armed` is deliberately NOT set: the wide pass is what arms the
    cold rungs in production, and leaving it false is what makes the
    afterlife's own arming visible below.  What may be left on the
    ladder afterwards is the quartering, which is a rung of its own
    since 2026-09-21 — and only for a window that can still take it.
    """
    state = instance.place_stage(wid)
    state.tried |= {seed.candidate_id for seed in
                    place_sched.untried_consult(instance, state, wide=True)}
    state.centre_spent = True
    state.rest_spent = True
    state.wide_spent = True
    assert place_sched.ladder_stage(instance, state, wid) == (
        place.STAGE_SUBDIVIDE if place_sched.subdivide_ready(state)
        else None)


def _fire(instance: engine._Engine, wid: tuple, stage: str) -> None:
    """One rung, through the ROW: prepare, run, fold what it returns.

    The quartering is work now, not a fold's side effect, so a test that
    wants children has to let the row do it.
    """
    job = place_sched.prepare_place(instance, wid, stage)
    assert job is not None, f"{stage} prepared nothing"
    for fact in job().facts:
        instance._ingest(fact)


def _refusal(instance: engine._Engine, wid: tuple) -> place_pass.WindowPassResult:
    """The pass outcome a spent ladder produces: nothing left to try."""
    return place_pass.WindowPassResult(
        outcome="nothing_to_try", route=None, placement=None,
        lattice_seed=None, tried_now=(), stage_spent=None,
        wide_spent=False, cold_spent=None, hypotheses=0, events=())


def _subdivide_to_four(instance: engine._Engine) -> tuple[tuple, tuple]:
    """One full window, quartered: the parent and its four children.

    Through the ROW, because the quartering is a RUNG: the spent ladder
    settles, `place.stage_of` answers `subdivide`, and the job returns
    four `Window` facts and the outcome that marks the parent.  No fold
    creates a fact.
    """
    parent_wid = instance.windows()[0]
    _exhaust(instance, parent_wid)
    instance._ingest(place_sched.PlaceOutcome(
        parent_wid, _refusal(instance, parent_wid)))
    assert place_sched.worker_stage(instance, parent_wid) == \
        place.STAGE_SUBDIVIDE, "the spent ladder's last rung"
    _fire(instance, parent_wid, place.STAGE_SUBDIVIDE)
    return parent_wid, instance.place_stage(parent_wid).children


class _Executor:
    """The engine's pool, made synchronous so one `_fill` is one step."""

    def __init__(self) -> None:
        self.jobs: list = []

    def submit(self, job: object) -> Future:
        future: Future = Future()
        self.jobs.append((job, future))
        return future

    def finish(self, index: int = 0) -> Future:
        job, future = self.jobs[index]
        future.set_result(job())
        return future


def test_the_subdivide_rung_seats_and_fires_through_the_engine_s_fill():
    """The rung through the POP GAUNTLET, not through `prepare` by hand.

    Every other subdivision test here fires the job directly, which
    cannot see the gauntlet the amendment made this stage ride: the
    seat, the `retire` consult at the pop, the version floor,
    `eligible`, and the RE-PRICING compare — where `subdivide` and
    `ring` are equal by construction, which is exactly why a window
    whose stage is re-read at the pop is fired rather than bounced back
    onto the frontier at a new price.  So this one seats a spent window
    through `_push_worker`, drives `engine._fill` one step, and merges
    what the job returned (review 2026-09-21, N2).
    """
    instance = _place_engine()
    parent_wid = instance.windows()[0]
    _exhaust(instance, parent_wid)
    instance._ingest(place_sched.PlaceOutcome(
        parent_wid, _refusal(instance, parent_wid)))
    worker = instance._bookmarks[("place", parent_wid)]
    # ONE row on the frontier: every other seat in this fixture belongs
    # to a row whose job wants pixels it has none of.  The seat itself
    # is the engine's own — `_push_worker` consults `retire`, `stage`
    # and `cost` exactly as a wake does.
    instance._frontier.clear()
    instance._queued.clear()
    worker.seat_seq = -1
    instance._sched_emitted.clear()
    instance._push_worker(worker)
    assert instance._frontier[0][3] == place.STAGE_SUBDIVIDE
    assert place.STAGE_COST[place.STAGE_SUBDIVIDE] == \
        place.STAGE_COST[place.STAGE_RING], (
        "the one new price literal, equal to the ring's: the pop's "
        "re-pricing compare is `>`, so an equal re-read never bounces")

    executor = _Executor()
    instance._fill(executor)
    assert [(plugin, stage) for plugin, _subject, _cost, _seq, stage
            in instance._inflight.values()] == \
        [("place", place.STAGE_SUBDIVIDE)], (
        "the rung fired; it was neither retired, floored nor repriced")
    future = executor.finish()
    assert sum(isinstance(fact, data.Window)
               for fact in future.result().facts) == 4, (
        "a pixel-free job: four child windows and the parent's outcome")
    instance._merge(future)

    state = instance.place_stage(parent_wid)
    assert state.subdivided is True and len(state.children) == 4
    assert all(instance.place_stage(kid).parent == parent_wid
               for kid in state.children), "the fold linked both ends"
    seated = [event for event in instance._events
              if isinstance(event, data.WorkerSeated)
              and event.stage == place.STAGE_SUBDIVIDE]
    assert [event.subject for event in seated] == [parent_wid]


def test_a_subdivided_parent_keeps_its_seat_while_a_child_lives():
    """The fold may not retire a BOOKMARK it will have to re-arm.

    Un-retiring a WindowState is a store write; un-retiring a bookmark
    would be an engine call from inside a fold, which is the thing this
    work removed.  So the ROW stays: the retire cause is held back by
    `afterlife_owed`, and the parent waits with `stage() -> None`,
    which seats nothing.
    """
    instance = _place_engine()
    parent_wid, kids = _subdivide_to_four(instance)
    state = instance.place_stage(parent_wid)
    assert state.subdivided is True and len(kids) == 4
    assert place_sched.afterlife_owed(state) is True
    assert place_sched.place_retire_cause(instance, parent_wid) is None
    assert place_sched.worker_stage(instance, parent_wid) is None
    assert instance._bookmarks[("place", parent_wid)].retired is False


def test_a_fresh_subdivision_keeps_the_parent_one_more_ring_pass():
    """The franchise the base gave a window that has just quartered itself.

    `engine._place_repush` returned WITHOUT latching `state.retired`
    when a spent ladder had just produced children, and
    `place.stage_of` answers STAGE_RING again the moment
    `untried_consult` is non-empty — so a neighbour that places LATER
    hands this window a new seed and one more ring pass, and only the
    settle after that retires it.  Latching on the first settle closed
    that door for ever (2026-09-21 review): a window that ran out of
    rungs before any neighbour placed would never place at all.  Both
    halves are pinned here, because the latch is what `ladder_stage`
    and `_place_eligible` short-circuit on.
    """
    instance = _place_engine()
    parent_wid, _kids = _subdivide_to_four(instance)
    state = instance.place_stage(parent_wid)
    assert state.subdivided is True and state.retired is False, (
        "a fresh subdivision keeps the ladder's franchise: a later "
        "neighbour pose is a new consult seed and a new ring pass")
    assert place_sched._place_eligible(instance, parent_wid) is True
    # the NEXT spent settle, with `subdivided` already true, latches —
    # exactly where `_place_repush` latched it
    instance._ingest(place_sched.PlaceOutcome(
        parent_wid, _refusal(instance, parent_wid)))
    assert instance.place_stage(parent_wid).retired is True
    assert place_sched._place_eligible(instance, parent_wid) is False
    assert instance._bookmarks[("place", parent_wid)].retired is False, (
        "the bookmark still waits on the afterlife")


@pytest.mark.parametrize("outcome", ["nothing_to_try",
                                     "insufficient_support"])
def test_the_afterlife_reaches_a_worker_not_only_a_window_state(outcome):
    """The parent's BOOKMARK survives both spent paths, and fires.

    `insufficient_support` latches `retired` straight out of the fold
    without consulting the ladder, so it is the path that used to retire
    the bookmark one wake later and lose the afterlife silently: the
    WindowState came back live and there was nothing subscribed to it.
    A WindowState assertion cannot see that, so this drives the engine's
    own push door and asserts on the bookmark and the index.
    """
    instance = _place_engine()
    parent_wid, kids = _subdivide_to_four(instance)
    if outcome == "insufficient_support":
        instance._ingest(place_sched.PlaceOutcome(
            parent_wid, dataclasses.replace(
                _refusal(instance, parent_wid),
                outcome="insufficient_support")))
    worker = instance._bookmarks[("place", parent_wid)]
    assert worker.retired is False, (
        "the fold's own key reaches the push door, which consults "
        "`retire` -- and the afterlife is still owed")
    for kid in kids:
        _exhaust(instance, kid)
        instance._ingest(place_sched.PlaceOutcome(
            kid, _refusal(instance, kid)))
    assert instance.place_stage(parent_wid).cold_armed is True
    assert worker.retired is False
    assert any(("place", parent_wid) in subscribers
               for subscribers in instance._index.values()), (
        "a retired bookmark is unsubscribed; this one was never retired")
    assert place_sched.worker_stage(instance, parent_wid) in \
        place.COLD_STAGES


def test_a_parent_that_spends_its_afterlife_retires_exhausted():
    """And the waiting row is not immortal.

    `afterlife_owed` goes false the moment the afterlife is USED, so the
    cold rungs it bought are the last ones: the next spent ladder
    retires the bookmark with the ordinary cause and unsubscribes it.
    """
    instance = _place_engine()
    parent_wid, kids = _subdivide_to_four(instance)
    for kid in kids:
        _exhaust(instance, kid)
        instance._ingest(place_sched.PlaceOutcome(
            kid, _refusal(instance, kid)))
    state = instance.place_stage(parent_wid)
    assert state.afterlife_used is True and state.retired is False
    state.cold_live_spent = True
    state.cold_rest_spent = True
    instance._ingest(place_sched.PlaceOutcome(
        parent_wid, _refusal(instance, parent_wid)))
    assert state.retired is True
    assert place_sched.afterlife_owed(state) is False
    assert place_sched.place_retire_cause(instance, parent_wid) == \
        place_sched.RETIRE_EXHAUSTED
    assert instance._bookmarks[("place", parent_wid)].retired is True


def test_a_child_s_ladder_noise_does_not_wake_its_parent():
    """A child's rungs are its own, and the reason that matters.

    A child spending a rung emits ITS `place_stage` key, which the
    parent has never held: the parent's reads are fixed at birth and
    name its own keys alone, and the store routes the one thing a
    parent cares about — a child SETTLING — to the parent's own key.
    Subscribing the parent to the child's key bumped its worker version
    on every child pass, which is the quantity `dormant()` compares:
    the §4 self-wake defect, on the parent edge.  (`place_settled`, the
    narrow per-child key, was the first answer; the amendment retired
    it — a derived relation is the store's.)
    """
    instance = _place_engine()
    parent_wid, kids = _subdivide_to_four(instance)
    worker = instance._bookmarks[("place", parent_wid)]
    child = instance.place_stage(kids[0])
    before = worker.version
    instance._ingest(place_sched.PlaceOutcome(
        kids[0], dataclasses.replace(
            _refusal(instance, kids[0]), outcome="consult_refused",
            tried_now=("seed/noise",))))
    assert "seed/noise" in child.tried, "the child's state moved"
    assert child.retired is False, "and it is not settled"
    assert worker.version == before, (
        "a rung the child spent cannot change what the parent would do")


def _place_job_returning(
        monkeypatch: pytest.MonkeyPatch,
        result: place_pass.WindowPassResult,
        fired: list[tuple[tuple, str]] | None = None) -> None:
    """Replace `place`'s job by one that returns `result` -- pixel-free.

    Everything else about the row is the production descriptor: the
    seat, the pop gauntlet, the stage and the folds.  `fired`, when
    given, records every (subject, stage) the row prepared.
    """
    def prepare(store: object, subject: tuple, stage: str) -> object:
        if fired is not None:
            fired.append((subject, stage))
        return lambda: data.JobResult(
            (place_sched.PlaceOutcome(subject, result),), (), 0.0)

    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", {
        **engine.DESCRIPTOR_BY_NAME,
        "place": dataclasses.replace(place_sched.PLACE_DESCRIPTOR,
                                     prepare=prepare)})


def _live_seat(instance: engine._Engine, wid: tuple) -> list[str]:
    """The stages `wid`'s place bookmark holds a LIVE seat at."""
    worker = instance._bookmarks[("place", wid)]
    return [entry[3] for entry in instance._frontier
            if entry[4] == wid and entry[1] == worker.seat_seq]


def _pass_through_engine(instance: engine._Engine, wid: tuple,
                         wake_mid_pass: tuple | None = None) -> None:
    """One pass of `wid`: seated alone, popped by `_fill`, merged.

    `wake_mid_pass` is a key `wid` reads, touched between the pop and
    the merge -- a neighbour's pose landing while the pass is in flight.
    """
    worker = instance._bookmarks[("place", wid)]
    instance._frontier.clear()
    instance._queued.clear()
    worker.seat_seq = -1
    instance._sched_emitted.clear()
    instance._push_worker(worker)
    executor = _Executor()
    instance._fill(executor)
    assert [(plugin, subject) for plugin, subject, _c, _s, _st
            in instance._inflight.values()] == [("place", wid)]
    if wake_mid_pass is not None:
        assert wake_mid_pass in worker.reads
        instance._touch((wake_mid_pass,))
        assert worker.pending is True, "in flight: the wake only marks"
    instance._merge(executor.finish())


def test_a_pose_refusal_sleeps_but_still_owes_its_quartering(monkeypatch):
    """`pose_refused` puts a window to sleep AND arms the rung.

    Two laws in one fold.  (1) `place` reads its own `place_stage` key,
    so the fold that records the sleep is the fact that wakes the
    sleeper: `dormant_since` is stamped at fold time and moved by the
    one own-subject key the fold emits, which is exactly what `_touch`
    will add.  Without it the window re-fires the identical refusal for
    ever (the colour sim at 750 % CPU, 2026-09-21).  (2) The quartering
    this refusal arms is work the window HOLDS, not work it waits for —
    it used to happen inside this very fold — so the sleeper takes that
    one rung, and goes back to sleep on the same terms afterwards.
    The refusal arrives through the engine's merge: a sleep is granted
    against the pass that was merged (S7, 2026-10-03), and outside a
    merge there is no pass to sleep on.
    """
    instance = _place_engine()
    parent_wid = instance.windows()[0]
    state = instance.place_stage(parent_wid)
    _place_job_returning(monkeypatch, dataclasses.replace(
        _refusal(instance, parent_wid), outcome="pose_refused"))
    _pass_through_engine(instance, parent_wid)
    assert state.dormant_since is not None and state.subdivide_armed is True
    assert place_sched.dormant(instance, state, parent_wid) is False
    assert place_sched.worker_stage(instance, parent_wid) == \
        place.STAGE_SUBDIVIDE, "a sleeping window still quarters"

    _fire(instance, parent_wid, place.STAGE_SUBDIVIDE)
    assert len(state.children) == 4 and state.subdivided is True
    assert place_sched.dormant(instance, state, parent_wid) is True, (
        "the version the sleep is stamped at counts this fold's own "
        "wake, the rung's included")
    assert place_sched.worker_stage(instance, parent_wid) is None


@pytest.mark.parametrize("woken", [True, False])
def test_a_wake_during_the_pass_is_not_swallowed_by_its_sleep(
        monkeypatch, woken):
    """S7 (2026-10-03): dormancy is stamped against what the pass READ.

    `_touch` bumps a bookmark even while its job is in flight, so the
    version at merge time already holds a neighbour's pose that landed
    mid-pass.  The stamp used to be taken there, and the own-key offset
    made the sleep stick: the window was refused for want of an anchor,
    the anchor arrived while it was being refused, and it never ran
    again.  A child (not subdividable, so the armed quartering does not
    hold it awake) is refused while its ring neighbour's pose key is
    touched: it must be seated again and fire.  Control: with no wake in
    flight it sleeps, as before.
    """
    instance = _place_engine()
    _parent, kids = _subdivide_to_four(instance)
    wid = kids[0]
    state = instance.place_stage(wid)
    assert not place_sched.subdivide_ready(state)
    neighbour_key = next(key for key in instance._bookmarks[
        ("place", wid)].reads if key[0] == "pose_affine")
    _place_job_returning(monkeypatch, dataclasses.replace(
        _refusal(instance, wid), outcome="pose_refused"))
    _pass_through_engine(instance, wid,
                         wake_mid_pass=neighbour_key if woken else None)
    assert state.subdivide_armed is True and state.retired is False
    if not woken:
        assert state.dormant_since is not None
        assert place_sched.dormant(instance, state, wid) is True
        assert _live_seat(instance, wid) == [], "asleep: no seat"
        return
    assert state.dormant_since is None, "a mid-pass wake keeps it awake"
    assert place_sched.dormant(instance, state, wid) is False
    assert _live_seat(instance, wid) == [place.STAGE_WORD_CENTRE], (
        "the pending push re-seated the window")
    executor = _Executor()
    instance._fill(executor)
    assert [(plugin, subject, stage) for plugin, subject, _c, _s, stage
            in instance._inflight.values()] == [
        ("place", wid, place.STAGE_WORD_CENTRE)], "and it fires again"


def test_store_folds_reads_no_engine_bookmark_by_plugin_name():
    """The fold stamps a sleep through the generic merging accessor.

    `self.worker_version("place", wid)` from inside a fold read the
    engine's bookmark by plugin name -- the coupling the 2026-10-03
    re-review flagged, and the stamp that swallowed mid-pass wakes.
    """
    from holo.receiver import store_folds
    path = Path(store_folds.__file__)
    tree = ast.parse(path.read_text(), filename=str(path))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute)
             and node.func.attr == "worker_version"]
    assert calls == []


def test_the_last_child_to_settle_re_arms_the_parent_cold():
    """The afterlife, end to end, through facts alone.

    Every child settles without a pose, the LAST one's fold re-arms the
    parent, and the parent hears about it on ITS OWN place_stage key --
    the key it has read since birth.  No repush, no bookmark surgery,
    and no subscription to a relation the store already knows.
    """
    instance = _place_engine()
    parent_wid, kids = _subdivide_to_four(instance)
    parent = instance.place_stage(parent_wid)

    worker = instance._bookmarks[("place", parent_wid)]
    assert (KEY_PLACE_STAGE, parent_wid) in worker.reads
    assert not any(key[1:] and key[1] in kids for key in worker.reads), (
        "THE PARENT SUBSCRIBES TO NOTHING OF ITS CHILDREN: its reads "
        "were fixed at birth, before the children existed, and a "
        "child's settle is routed by the STORE to the parent's own key")

    for index, kid in enumerate(kids):
        before = worker.version
        _exhaust(instance, kid)
        instance._ingest(place_sched.PlaceOutcome(
            kid, _refusal(instance, kid)))
        assert instance.place_stage(kid).retired is True
        assert (worker.version > before) is (index == len(kids) - 1), (
            "only the LAST settle moves anything the parent would do, "
            "so only it emits the parent's key -- the narrow-key law, "
            "kept without a narrow key")
        assert parent.afterlife_used is (index == len(kids) - 1), (
            "the parent re-arms only once every child has settled")

    assert parent.cold_armed is True
    assert parent.retired is False and parent.dormant_since is None
    assert place_sched.worker_stage(instance, parent_wid) in \
        place.COLD_STAGES, (
        "the afterlife's whole point: the parent's FULL extent gets one "
        "cold pass that its quarters could not give it")


def test_a_child_that_places_denies_its_parent_the_afterlife():
    """And the placement fold is where the store routes that settle.

    The quarter that carries the page is the answer the parent's full
    extent was going to look for, so `placed` cancels the afterlife for
    good — and it reaches the parent through the same door, its own
    key, which is what lets its bookmark retire.
    """
    instance = _place_engine()
    parent_wid, kids = _subdivide_to_four(instance)
    parent = instance.place_stage(parent_wid)
    worker = instance._bookmarks[("place", parent_wid)]
    before = worker.version
    instance._ingest(_h3_facts.placement(wid=kids[0]))
    assert instance.place_stage(kids[0]).placed is True
    assert parent.child_placed is True and worker.version > before
    for kid in kids[1:]:
        _exhaust(instance, kid)
        instance._ingest(place_sched.PlaceOutcome(
            kid, _refusal(instance, kid)))
    assert parent.afterlife_used is False and parent.cold_armed is False
    assert place_sched.afterlife_owed(parent) is False


def test_a_parent_judged_done_while_owed_its_afterlife_still_hears_it(
        monkeypatch):
    """The done gate may not strand an owed afterlife (2026-10-03).

    Until this date `place_retire_cause` checked done AFTER the
    afterlife hold, so a parent waiting on its last child could be
    retired `done_covered` -- for good -- and `_settle_child` later
    emitted its place_stage key to an unsubscribed bookmark: the
    afterlife never ran.  The gate suppresses through the stage now, so
    the parent judged done stays a live bookmark; when an anchor's
    revision re-opens its extent the store wakes it on its own done key,
    and when the last child settles its afterlife rung is SEATED and
    FIRES through the pop gauntlet.
    """
    instance = _place_engine()
    parent_wid, kids = _subdivide_to_four(instance)
    # An overlapping anchor, not a child: a placement whose projection
    # lands the parent's whole extent inside tile (0, 0).
    anchor = (_h3_facts.CAPTURE_ID, 0, 0, (0, 0, 220, 220))
    instance._ingest(_h3_facts.window(wid=anchor, ordinal=77))
    instance._ingest(dataclasses.replace(
        _h3_facts.placement(wid=anchor),
        native_affine=(40.0, 0.0, 0.0, 0.0, 40.0, 0.0)))
    _exhaust(instance, parent_wid)
    instance._ingest(place_sched.PlaceOutcome(
        parent_wid, _refusal(instance, parent_wid)))
    parent = instance.place_stage(parent_wid)
    assert parent.retired is True and place_sched.afterlife_owed(parent)
    for kid in kids[:-1]:
        _exhaust(instance, kid)
        instance._ingest(place_sched.PlaceOutcome(
            kid, _refusal(instance, kid)))

    instance._ingest(_h3_facts.certificate(0, 0, 0))
    worker = instance._bookmarks[("place", parent_wid)]
    instance._repush("place", parent_wid)
    assert instance.window_fully_done(parent_wid) is True
    assert place_sched.place_retire_cause(instance, parent_wid) is None, (
        "done is not a retire cause: the old clause retired this parent "
        "here and its afterlife with it")
    assert worker.retired is False
    assert place_sched.worker_stage(instance, parent_wid) is None

    revision = refine.RefineOutcome(
        window_id=anchor, revision=refine.Revision(
            adopted=True, reason="probe",
            affine=(40.0, 0.0, 0.0, 0.0, 40.0, -2400.0)))
    changed, keys, _kind = instance._fold(revision)
    assert changed and (KEY_WINDOW_DONE, parent_wid) in keys, (
        "the revision moves the projection off the certified tile, and "
        "the store routes that to the window it last judged done")
    before = worker.version
    instance._births(revision)
    instance._touch(keys)
    assert worker.version > before and worker.retired is False
    assert instance.window_fully_done(parent_wid) is False

    # the revised anchor is a fresh consult seed; spend it so the rung
    # the afterlife buys is the one on the seat
    _exhaust(instance, parent_wid)
    last = kids[-1]
    _exhaust(instance, last)
    instance._ingest(place_sched.PlaceOutcome(
        last, _refusal(instance, last)))
    assert parent.afterlife_used is True and parent.cold_armed is True
    seats = [entry for entry in instance._frontier
             if entry[4] == parent_wid and entry[1] == worker.seat_seq]
    assert [entry[3] for entry in seats] == [place.STAGE_COLD_LIVE], (
        "the last child's settle reached a SUBSCRIBED bookmark and seated "
        "the afterlife's cold rung")

    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", {
        **engine.DESCRIPTOR_BY_NAME,
        "place": dataclasses.replace(
            place_sched.PLACE_DESCRIPTOR,
            prepare=lambda store, subject, stage: (
                lambda: data.JobResult((), (), 0.0)))})
    instance._frontier = seats
    heapq.heapify(instance._frontier)
    instance._fill(_Executor())
    assert [(plugin, subject, stage) for plugin, subject, _cost, _seq, stage
            in instance._inflight.values()] == [
        ("place", parent_wid, place.STAGE_COLD_LIVE)], (
        "and the rung fired: neither retired, floored nor repriced")


def test_an_afterlife_with_no_rung_left_retires_its_parent(monkeypatch):
    """S7 (2026-10-03): the afterlife re-latches when it buys nothing.

    A LAZY quartering comes after the cold rungs are spent, so the cold
    re-arm the last settle grants offers no rung.  Until this date the
    parent woke to `stage() -> None`, nothing latched it again, and its
    bookmark never retired: subscribed for good, consulted on every
    neighbour wake (SCHED-OPEN #8's "afterlife 0 of 319" on J).  Now the
    settle re-latches it, the wake it emits retires it `exhausted`, and
    a later neighbour wake reaches nothing.
    """
    instance = _place_engine()
    parent_wid, kids = _subdivide_to_four(instance)
    parent = instance.place_stage(parent_wid)
    # production's lazy order: every cold rung spent before the quartering
    parent.cold_armed = True
    parent.cold_live_spent = True
    parent.cold_rest_spent = True
    worker = instance._bookmarks[("place", parent_wid)]
    for kid in kids[:-1]:
        _exhaust(instance, kid)
        instance._ingest(place_sched.PlaceOutcome(
            kid, _refusal(instance, kid)))
    assert worker.retired is False, "the afterlife is still owed"
    exhausted_before = instance._retire_causes.get(
        place_sched.RETIRE_EXHAUSTED, 0)
    _exhaust(instance, kids[-1])
    instance._ingest(place_sched.PlaceOutcome(
        kids[-1], _refusal(instance, kids[-1])))
    assert parent.afterlife_used is True and parent.retired is True
    assert place_sched.afterlife_owed(parent) is False
    assert worker.retired is True
    assert instance._retire_causes[place_sched.RETIRE_EXHAUSTED] == \
        exhausted_before + 2, "the last child and its parent"
    assert not any(("place", parent_wid) in subscribers
                   for subscribers in instance._index.values()), (
        "retired, and unsubscribed with it")
    assert _live_seat(instance, parent_wid) == []
    version = worker.version
    lattice_key = next(key for key in worker.reads
                       if key[0] == "lattice_seed")
    instance._touch((lattice_key,))
    assert worker.version == version, "a neighbour wake reaches nothing"


def test_an_afterlife_with_a_cold_rung_left_fires_it_once(monkeypatch):
    """And a parent the refusal quartered EARLY keeps its rung.

    `pose_refused` on the wide pass arms cold and the quartering and
    puts the window to sleep; it quarters through the sleep; its four
    children settle unplaced; the afterlife wakes it, and the cold rung
    it never spent is seated and fires -- once -- after which the
    ladder is spent and the bookmark retires `exhausted`.
    """
    instance = _place_engine()
    parent_wid = instance.windows()[0]
    _exhaust(instance, parent_wid)
    parent = instance.place_stage(parent_wid)
    fired: list[tuple[tuple, str]] = []
    _place_job_returning(monkeypatch, dataclasses.replace(
        _refusal(instance, parent_wid), outcome="pose_refused",
        wide_spent=True), fired)
    _pass_through_engine(instance, parent_wid)
    assert parent.cold_armed is True and parent.dormant_since is not None
    _fire(instance, parent_wid, place.STAGE_SUBDIVIDE)
    assert place_sched.dormant(instance, parent, parent_wid) is True
    for kid in parent.children:
        _exhaust(instance, kid)
        instance._ingest(place_sched.PlaceOutcome(
            kid, _refusal(instance, kid)))
    assert parent.afterlife_used is True and parent.retired is False
    assert parent.dormant_since is None
    assert _live_seat(instance, parent_wid) == [place.STAGE_COLD_LIVE]

    worker = instance._bookmarks[("place", parent_wid)]
    fired.clear()
    _place_job_returning(monkeypatch, dataclasses.replace(
        _refusal(instance, parent_wid),
        cold_spent=place.STAGE_COLD_LIVE), fired)
    _pass_through_engine(instance, parent_wid)
    assert fired == [(parent_wid, place.STAGE_COLD_LIVE)]
    assert parent.retired is True and worker.retired is True
    assert place_sched.place_retire_cause(instance, parent_wid) == \
        place_sched.RETIRE_EXHAUSTED
    assert _live_seat(instance, parent_wid) == []


@pytest.mark.parametrize("armed", [True, False])
def test_an_armed_quartering_outlives_a_ring_pass_on_too_little_paper(
        monkeypatch, armed):
    """R1 (review 2026-10-17, D1): `insufficient_support` may not latch
    a quartering an earlier refusal ARMED.

    Base quartered inside the `pose_refused` fold, so the children
    existed before any later pass.  The rung that replaced it runs
    behind RING whenever a consult is untried, and a ring pass that
    finds too little paper (a neighbour placed and moved the region's
    lattice seed, say) used to latch the window on the spot: retired
    `exhausted`, its four children never minted.  Armed: the window is
    refused for want of a seed, a neighbour places, the ring pass
    returns `insufficient_support` -- and the subdivide rung is seated,
    fires through `_fill` and mints the children, after which the
    parent latches (base's end state) while its bookmark waits on the
    afterlife.  Control: an UNARMED window still latches and retires
    `exhausted` straight out of the same fold.
    """
    instance = _place_engine()
    parent_wid, neighbour_wid = instance.windows()[:2]
    state = instance.place_stage(parent_wid)
    worker = instance._bookmarks[("place", parent_wid)]
    production = engine.DESCRIPTOR_BY_NAME
    if armed:
        _place_job_returning(monkeypatch, dataclasses.replace(
            _refusal(instance, parent_wid), outcome="pose_refused"))
        _pass_through_engine(instance, parent_wid)
        assert state.subdivide_armed is True
        assert place_sched.worker_stage(instance, parent_wid) == \
            place.STAGE_SUBDIVIDE
    instance._ingest(_h3_facts.placement(wid=neighbour_wid))
    assert place_sched.worker_stage(instance, parent_wid) == \
        place.STAGE_RING, "an untried consult runs ahead of the rung"

    fired: list[tuple[tuple, str]] = []
    _place_job_returning(monkeypatch, dataclasses.replace(
        _refusal(instance, parent_wid), outcome="insufficient_support"),
        fired)
    exhausted_before = instance._retire_causes.get(
        place_sched.RETIRE_EXHAUSTED, 0)
    _pass_through_engine(instance, parent_wid)
    assert fired == [(parent_wid, place.STAGE_RING)]
    if not armed:
        assert state.retired is True and worker.retired is True
        assert instance._retire_causes[place_sched.RETIRE_EXHAUSTED] == \
            exhausted_before + 1
        assert state.children == () and _live_seat(instance,
                                                   parent_wid) == []
        return

    assert state.retired is False and worker.retired is False, (
        "the quartering an earlier refusal armed is still owed")
    assert _live_seat(instance, parent_wid) == [place.STAGE_SUBDIVIDE], (
        "the fold's own key re-seated the window at the rung, not the "
        "ring pass that just found too little paper")
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", production)
    executor = _Executor()
    instance._fill(executor)
    assert [(plugin, subject, stage) for plugin, subject, _c, _s, stage
            in instance._inflight.values()] == [
        ("place", parent_wid, place.STAGE_SUBDIVIDE)]
    instance._merge(executor.finish())
    assert state.subdivided is True and len(state.children) == 4
    assert state.retired is True, (
        "the rung was the last one the support refusal left: latched, "
        "as base latched it with its children already minted")
    assert place_sched.afterlife_owed(state) is True
    assert worker.retired is False, "the bookmark waits on the afterlife"
    assert place_sched.worker_stage(instance, parent_wid) is None
