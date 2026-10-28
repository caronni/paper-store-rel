"""Following a RECORDED ordering: the ``--replay`` audit and recovery.

Split out of ``orchestrator.py`` at H4 W2 for the file cap, and the seam
is the tree's own: this is a second control loop, over a different
input. The live loop asks "what may run now?"; this one asks "what did
run, and in what order?", and its whole vocabulary — start markers, held
proposals, stranded dispatches, the settled id a commit is matched by —
means nothing to the live path and appears nowhere in it.

**Marker-driven since H4 W2** (the second concurrency ruling). The
journal records DISPATCHES beside commits, so a recorded pass is
re-launched at the position it was launched from instead of being
re-derived from a queue whose order was the pool's. That is what makes a
pooled recording replayable: a fire dispatched BEFORE a neighbouring
commit and landing AFTER it has no expression in commit order at all,
and the pre-marker loop met that shape as a ``ReplayError`` or as the
journal's tail refusal.

Both entry points take the running
:class:`~holo2.engine.orchestrator.Orchestrator` and drive its own
machinery — arming, proposing, committing, settling are all its, applied
in the recorded order rather than the scheduler's. Same contract as
``engine/observe.py``'s: main thread, one owner, nothing here holds
state of its own.

**THE REPLAY/AUDIT CONTRACT: a replay runs under the CLOSE POLICY the
journal was recorded under** (stated with the `--no-close` build,
2026-08-22). The close policy is a per-run argument and not part of
``SessionIdentity``, deliberately — one state directory accumulates
under `--no-close` and closes under an ordinary run later — so the
journal cannot say which policy wrote it, and the audit has to state the
requirement instead of checking it. Two consequences, both enforced in
:func:`_require_the_recorded_ordering_is_spent`:

* under `--no-close`, the recorded ordering's own CLOSE entry is the one
  line the policy SKIPS (the user's words: skip that journal line on
  ingestion and replay). In a recording whose close is still the LAST
  WORD it is the last entry, so the walk is allowed to end exactly one
  non-marker entry short. **The audit cannot PROVE the entry it leaves
  standing is that close** — proving it means computing the close's own
  verdict, which is deciding the close, which is what this policy
  forbids — so this exemption is a blind spot by construction: a
  recording whose LAST commit diverges is accepted here. Its cure is the
  contract itself, one line up: replay a recording under the policy it
  was recorded under, and the close entry is re-earned and matched like
  every other;
* a journal whose close was SUPERSEDED (commits recorded after it, which
  is what accumulating under `--no-close` leaves behind) cannot be
  replayed WHOLE under any policy, and the refusal says which halves are
  auditable. Under a CLOSING policy the close is re-earned at its
  recorded position, the session goes terminal there, and every entry
  after it is unreachable; under `--no-close` no PASS mints that close,
  the walk halts on it with its whole tail still standing, and the
  one-entry exemption above does not reach. Refused with the named
  diagnosis rather than as a bare "replay stopped at position N".

The same requirement reaches crash RECOVERY, which is the same machinery
(F-24), and one of its two directions is GUARDED here:

* a CLOSING resume of a state whose journal tail was accumulated past a
  SUPERSEDED close is refused up front by
  :func:`_require_a_superseded_tail_is_re_earned_without_deciding` —
  re-earning that tail greedily re-decides the close mid-walk, at a
  position the journal already holds, and the operator would meet it as
  the raw divergent-refold refusal whose named remedy (delete the state
  directory) would destroy the accumulation. The remedy is two runs, and
  the refusal names them;
* a `--no-close` resume of a state whose tail holds an UNMEMOISED close
  — a crash between the close commit and the cache frame — is STATED,
  not guarded: this policy re-earns no close, so the live run's next
  commit lands where the recorded close stands and meets the journal's
  divergent-refold refusal. Narrow (the frame follows the close commit
  immediately, at ``Store.close``) and left unguarded because the remedy
  is one ordinary run, and because recognising that entry as a close
  means deciding one.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..core import ReplayCursor, ReplayError, WorkId, is_marker, marker_work_id
from .consult import RunOutcome
from .worklist import Armed, Proposal

if TYPE_CHECKING:                                  # pragma: no cover
    from .orchestrator import Orchestrator


def audit(run: "Orchestrator") -> RunOutcome:
    """The ``--replay`` audit: follow a recorded ordering, whole.

    Auditing a state directory IS re-folding its journal and
    comparing batch ids (F-24, subsumed by F-16). Since H4 W2 the
    ordering it follows holds DISPATCHES as well as commits, so the
    audit re-launches each recorded pass at the position it was
    launched from rather than re-deriving an order of its own — which
    is what makes a POOLED recording auditable at all.

    A pass the ordering never committed is NOT a divergence, and since
    the tail-marker ruling it is not treated as one: the recording did
    not commit it either — a stale discard at the wall, or a fire the
    close preempted — so it is released exactly as the recording
    released it. What the audit verifies is the ORDER, entry by entry,
    and the id of every commit that landed in it.

    **THE EARLY-OUTCOME PATH LEAVES HELD MARKS OUTSTANDING, AND THAT IS
    TRUTHFUL** (ruled KEEP, H4 W6 — flagged when the dispatch-settle half
    was fixed). A terminal outcome mid-walk means the close consulted and
    decided: :meth:`~holo2.engine.orchestrator.Orchestrator._apply`
    returns non-``None`` there and nowhere else. The walk returns without
    releasing what it was still holding, so each held proposal keeps the
    unsettled ``mark_start`` its dispatch wrote. Settling them would
    assert a completion that never happened — those passes did not commit,
    were not discarded and were not handed back; the run ENDED under them.
    The count's only reader is the frame predicate (``core.store._frame``
    — a frame is a resume point), so the effect is that the verdict's own
    commit takes no cadence frame, which is the conservative answer and
    not an accident: markers with no commits genuinely do stand before
    that position. Nothing durable is lost either, because ``Store.close``
    flushes what the memo still owes on the way out. Waste at most, and on
    this path not even that — which is why the fix is to say so here
    rather than to add a release the truth does not support.
    """
    outcome, pending = _follow_recorded(run)
    if outcome is not None:
        # Held marks stay (see the docstring), but the CONTRACT is still
        # owed: a terminal outcome mid-walk is the greedy close being
        # re-earned at its recorded position, and a recording that holds
        # COMMITS past it is one that was accumulated under `--no-close`
        # afterwards.
        _require_the_recorded_ordering_is_spent(run, outcome, mid_walk=True)
        return outcome
    _release(run, pending)
    final = run._exhausted()        # the close is a recorded commit too
    assert run._replay is not None  # the audit path always holds one
    _require_the_recorded_ordering_is_spent(run, final)
    return final


def _require_the_recorded_ordering_is_spent(run: "Orchestrator",
                                            final: RunOutcome, *,
                                            mid_walk: bool = False) -> None:
    """The audit reached the end of the recording — or names why it did not.

    The replay/audit contract is the module docstring's; this is the one
    place it is enforced. Four answers, and the two middle ones are the
    whole reason this is a function rather than one ``if``:

    * nothing left — the ordinary end of an audit;
    * a TERMINAL outcome with COMMITS still standing — the recording
      committed past its own close, which one run cannot do (the wall
      refuses every batch after a terminal close). So it was accumulated
      under `--no-close` after closing, and its close is SUPERSEDED.
      Named, not left as "replay stopped at position N" — and the name
      is all it can offer, because a superseded recording is not
      walkable WHOLE under any policy: `--no-close` does not mint that
      close either, so it halts on the same entry with the same tail
      standing (measured, 2026-08-22). What the refusal offers instead
      is the auditable PREFIX. MARKERS past a terminal close are lawful
      and are not this: a close preempts the pool
      (``orchestrator._cancel``) and the fires it cancelled left their
      dispatches recorded;
    * one non-marker entry left under `--no-close` — the recorded CLOSE
      line, which this policy skips at replay exactly as the fold skips
      it at ingestion. **Not proven to be that close**, and it cannot be:
      the proof is the close's own settled batch id, which means
      consulting the close in a deciding mode — the one act this policy
      forbids and the one the epilogue promises did not happen. So the
      exemption is a stated blind spot (module docstring), and the audit
      that closes it is the same recording replayed under its own
      closing policy;
    * anything else — a real divergence, reported as it always was.
    """
    assert run._replay is not None
    store = run._ctx.store
    rest = run._replay.ordering[store.journal_position:]
    if not rest:
        return
    if final.status != "open" and any(
            not is_marker(entry) for entry in rest):
        close_at = store.journal_position - 1
        raise ReplayError(
            f"{store.state_dir}: this replay went {final.status.upper()} at "
            f"journal position {close_at} and the "
            f"recording holds {len(rest)} entries after it — commits past a "
            "close no single run can make. This journal was accumulated "
            "under --no-close AFTER its close, so that close is SUPERSEDED, "
            "and a superseded recording cannot be walked whole under ANY "
            "close policy: the close sits mid-ordering, no pass mints it, "
            "and --no-close halts on exactly this entry too. Audit the "
            f"PREFIX instead — the ordering through position {close_at}, "
            "under this same closing policy — and re-earn the tail by "
            "resuming the state directory itself (once under --no-close, "
            "then a closing run), which is the same machinery without the "
            "audit.")
    if mid_walk:
        return             # cancelled fires' markers: the H4 W6 ruling
    if (run._no_close and not is_marker(rest[0])
            and sum(1 for entry in rest if not is_marker(entry)) == 1):
        # The close line this policy skips — see the docstring for why
        # "the close line" is a claim this function cannot check. Markers
        # may trail it: the recording's close preempted its own pool.
        return
    raise ReplayError(
        f"replay stopped at journal position "
        f"{store.journal_position} of "
        f"{len(run._replay.ordering)} recorded")


def recover(run: "Orchestrator") -> RunOutcome | None:
    """Re-earn the journal tail the cache does not cover, then run live.

    The SAME machinery as the audit above (F-16); a clean exit leaves
    nothing to do. Serial while it lasts — the recorded order is the
    schedule, so a pool would only race to obey it.

    One tail this run's POLICY cannot re-earn is refused before the walk
    starts (see :func:`_require_a_superseded_tail_is_re_earned_without_deciding`);
    everything else the tail may lack is an INPUT question, and that one
    is asked at the end, where the walk knows what it could not arm.
    """
    ordering = run._ctx.store.ordering()
    if len(ordering) <= run._ctx.store.journal_position:
        return None
    _require_a_superseded_tail_is_re_earned_without_deciding(run, ordering)
    pool_size, run._pool_size = run._pool_size, 1
    run._replay = ReplayCursor(ordering)
    unarmed: list[WorkId] = []
    try:
        outcome, pending = _follow_recorded(run, unarmed)
    finally:
        run._replay, run._pool_size = None, pool_size
    _release(run, pending)                  # past the tail: it re-arms live
    if outcome is None:
        _require_the_inputs_the_tail_needs(run, unarmed)
    return outcome


def _require_a_superseded_tail_is_re_earned_without_deciding(
        run: "Orchestrator", ordering: tuple[str, ...]) -> None:
    """Refuse a re-earn this run's CLOSE POLICY cannot perform (2026-08-22).

    The mirror of the case the module docstring already stated, and the
    one with teeth, because its raw refusal names a DESTRUCTIVE remedy.
    Three facts, each ordinary alone:

    * this open dropped a SUPERSEDED close (``store.unadmitted_close``,
      and under a closing policy that is the only rule that sets it);
    * the journal holds COMMITS the cache never memoised — the state
      crashed part-way through the accumulation that superseded it;
    * and this run's policy DECIDES, so the first tail commit that moves
      the certified frontier re-opens the close consult, which closes on
      a frontier that already verified once.

    Together: the close is re-decided mid-tail and its commit lands at a
    position the journal already holds something else at, so the operator
    meets ``core.journal``'s divergent-refold refusal — true, unhelpful,
    and remedied there by deleting the state directory, which would throw
    away exactly the certificates the interrupted run was accumulating.
    MEASURED (2026-08-22): the two-run remedy below re-earns the tail and
    then closes byte-identically, so the refusal names it instead.

    This does NOT touch the divergent-refold law: that refusal stays
    where it is and still fires for every other cause. This one is
    upstream of it and strictly narrower.
    """
    if run._no_close:
        return                    # this policy re-earns the tail; that is it
    record = run._ctx.store.unadmitted_close
    if record is None:
        return
    store = run._ctx.store
    tail = ordering[store.journal_position:]
    if not any(not is_marker(entry) for entry in tail):
        return                    # trailing dispatches only: nothing to earn
    raise ReplayError(
        f"{store.state_dir}: this state's {record.status.value.upper()} close "
        f"is SUPERSEDED — the journal holds {len(tail)} entries the cache "
        "never memoised, accumulated under --no-close after that close — and "
        "re-earning them under a CLOSING policy would decide the close again "
        "part-way through them, at a position the journal already holds. "
        "Re-run once with --no-close: it re-earns the tail and decides "
        "nothing. Then close with a plain or --complete run — a close is a "
        "pure derivation, so the payload comes back byte-identical.")


def _require_the_inputs_the_tail_needs(run: "Orchestrator",
                                       unarmed: list[WorkId]) -> None:
    """Refuse a re-earn this run's INPUTS cannot perform, while it is legible.

    Three facts have to hold together, and each one alone is ordinary:

    * the walk met a recorded pass it could not offer at all (``unarmed``
      — see :func:`_replay_pass`: a lawful no-op on its own, because the
      commonest cause is a window another pass in this same tail has
      since placed);
    * it did not reach the end of the ordering, so entries this run must
      now produce LIVE are still standing (the healthy end of a recovery
      under a CLOSING policy is the close's own verdict, which no pass
      makes and which the live run commits at exactly the recorded
      position — a recording whose close sits MID-ordering is the
      superseded shape, refused above before the walk);
    * and the plane is holding captures BY RECORD ONLY — no scan file and
      no surviving prepared plane, so no pixels at all.

    Together they say one thing: the tail contains work over pixels this
    invocation does not have, the live run will therefore fold something
    else at a position the journal already holds, and the operator would
    meet that as a raw divergence refusal — technically true and useless,
    because the remedy is not "your state is corrupt", it is "hand me the
    files". So it is said HERE, in front of the fold, where the missing
    inputs still have names.

    This does NOT touch the divergent-refold law (``core.journal``): that
    refusal stays exactly where it was and still fires for every other
    cause. This one is upstream of it and strictly narrower.
    """
    if not unarmed:
        return
    store = run._ctx.store
    if store.journal_position >= len(store.ordering()):
        return
    detached = run._ctx.plane.detached_captures()
    if not detached:
        return
    shas = ", ".join(sha[:12] for sha in detached)
    raise ReplayError(
        f"{store.state_dir}: this state was interrupted mid-run and its "
        f"journal records {len(store.ordering()) - store.journal_position} "
        f"entries the cache never memoised, {len(unarmed)} of them passes "
        f"over pixels this invocation does not have. Capture(s) {shas} are "
        "attached BY RECORD only: no scan was declared for them and "
        f"{store.state_dir.name}.prepared holds no plane for them either. "
        "Re-run declaring those captures' scan files, or restore the intact "
        f"{store.state_dir.name}.prepared directory beside this state — "
        "either one re-earns the recorded tail. Deleting the state "
        "directory and decoding again is the other honest remedy.")


def _settle_mark(run: "Orchestrator") -> None:
    """One dispatch THIS walk marked is over: the store waits on one fewer.

    :meth:`~holo2.core.store.Store.mark_start` counts the dispatch as
    outstanding whether the entry it appends is new or is the recorded
    one verified in place, and that is deliberate — the marker positions
    ARE the snapshot-prefix law, so a walk that skipped the bump would
    be re-running each pass against an accounting the recorded run never
    had. What follows from it is that the walk owes the OTHER half too.
    It is not the live loop's to pay: ``orchestrator._close_dispatch``
    closes only the marks that loop's own ``_marked`` set holds, which
    is what keeps one dispatch from being decremented twice.

    The bookkeeping is structural rather than a second ledger, which is
    what lets this module keep holding no state of its own: **every held
    proposal carries exactly one unsettled mark**, so the settle rides
    the four ways a held pass leaves ``pending`` — reaped by its commit,
    applied as a no-op, dropped stale, or released at the end — and a
    marker that armed nothing settles where it is met, since nothing
    will ever hold it.

    Waste, never wrongness, is what the missing half cost: a cache frame
    is taken only where no dispatch is outstanding (a frame is a resume
    point, ``core.store._frame``), so a count stranded above the truth
    disabled the memo for the remainder of the run and left a SECOND
    crash re-earning the whole session tail instead of the one cadence
    window ``DEFAULT_SNAPSHOT_EVERY`` promises.
    """
    run._ctx.store.settle_start()


def _release(run: "Orchestrator", pending: list[Proposal]) -> None:
    """Hand back every pass the recorded ordering never committed.

    The tail-marker ruling, applied to the other end: a dispatch with no
    commit is a NON-COMMITTING pass, whether it sits mid-ordering (a
    failed pull pass), at the crashed tail, or here — held to the end
    because the recording discarded it at the wall or the close preempted
    it. Nothing durable is invented for it; the source takes its subject
    back (``settle(None)``, the abandoned-fire path) and a descriptor
    returns to the queue, so whatever work is genuinely still open
    re-arms LIVE afterwards.

    **THE LOOP BODY IS UNPINNED, AND ACCEPTED AS SUCH** (measured and
    ruled, H4 W6). This function is CALLED on every audit and recovery
    (nine times across the engine suite), but no fixture has ever left it
    a proposal to release: a pass that reaches the end of the walk still
    held is one whose marker stands, whose commit is absent, and which no
    later ``_drop_stale`` dropped — and every recording the suite makes
    resolves each of its passes before the ordering runs out.
    Constructing one means staging a tail marker whose pass still ARMS,
    which needs a cut through the memo AND a work key still open at that
    cut; that fought hard enough to be worth stating instead of forcing.
    What carries the risk is that the body is a strict subset of
    :func:`_drop_stale`'s, which IS pinned as of the same wave
    (``test_the_walk_re_makes_the_stale_discard_the_recording_made``):
    the same settle, the same ``_disarm``, the same source-less queue
    push, minus the staleness test. A defect here that is not also a
    defect there would have to live in three lines that appear
    identically twenty lines below.
    """
    for proposal in pending:
        _settle_mark(run)
        run._disarm(proposal.armed)
        if proposal.armed.source is None:
            run._queue.push(proposal.armed.worker_id)


def _follow_recorded(run: "Orchestrator", unarmed: list[WorkId] | None = None,
                     ) -> tuple[RunOutcome | None, list[Proposal]]:
    """Walk the recorded ENTRIES until they are exhausted (§10.3).

    Marker-driven since H4 W2, and the loop is the ruling verbatim:

    * a START MARKER launches the pass it NAMES against the store as
      of that position — one at a time, which is all a replay needs —
      and the result is HELD;
    * a COMMIT applies the held pass whose settled id matches it (the
      settled one, because the recorded id is post-merge);
    * a marker with NO matching commit is a non-committing pass, and it
      is one EVERYWHERE — a failed pull pass mid-ordering, and equally a
      pass at the crashed tail whose commit never became durable. It is
      replayed for its in-memory effects only (the tried set, the stage
      memory, the acceptance floor) and the work re-arms LIVE afterwards.
      Recovery never invents a commit the ordering did not record;
    * a commit no held pass produced is a SCHEDULER-side commit (a
      sleeping worker re-declaring its read-set), re-derived by
      :func:`_replay_scheduler_commit`.

    What it no longer does is re-derive the dispatch ORDER from its
    own queue. That is what could not reproduce a pooled run: a fire
    dispatched BEFORE a neighbouring commit and landing AFTER it has
    no expression in commit order, and the old loop met it as a
    ``ReplayError`` or as the journal's tail refusal.

    Why there is no "stranded marker" case at all: a cache frame is
    taken only where NO dispatch is outstanding (``core.store._frame`` —
    a frame is a resume point), so every marker before the position a
    resume starts at has already settled. The memo's boundary is a clean
    cut through the dispatches by construction, and this walk therefore
    only ever meets markers whose passes it is meant to run.

    ``unarmed`` collects the markers that could not be armed, for the one
    caller that has a use for them (:func:`recover`, whose refusal is
    built out of that list plus two other facts). The audit passes
    nothing and is unchanged: a marker it cannot arm stays a lawful
    no-op there.
    """
    assert run._replay is not None
    cursor, store = run._replay, run._ctx.store
    pending: list[Proposal] = []
    while not cursor.exhausted(store.journal_position):
        entry = cursor.at(store.journal_position)
        assert entry is not None
        if is_marker(entry):
            # BEFORE the dispatch, not only after a commit: the recorded
            # run discarded a stale proposal the moment its fire came
            # back, which is any point between two commits, and a held
            # pass keeps its subject IN FLIGHT at the source. A window
            # the recording discarded and re-dispatched would otherwise
            # meet a slot this walk is still holding, and the re-dispatch
            # would arm nothing.
            _drop_stale(run, pending)
            outcome = _replay_pass(run, marker_work_id(entry), pending,
                                   unarmed)
            if outcome is not None:
                return outcome, pending
            continue
        proposal = _take_pending(run, pending, entry)
        if proposal is None and _replay_scheduler_commit(run):
            continue                      # a sleep landed; the cursor moved
        if proposal is None:
            # Nothing this loop OWNS can earn it, and one such commit is
            # expected: the close's own verdict, which the orchestrator
            # makes out of band at the end of a run (``_exhausted``) and
            # not through any pass. So the walk stops here and the CALLER
            # finishes — the audit by consulting the close and then
            # re-checking that the cursor is exhausted, a recovery by
            # running live from this position. Neither is a soft landing
            # for a real divergence: the next entry this run writes lands
            # at THIS position, and the journal refuses an entry that
            # disagrees with the one already standing there.
            break
        _settle_mark(run)     # before the wall, so the frame sees a clean cut
        outcome = run._apply(proposal)
        _drop_stale(run, pending)
        if outcome is not None:
            return outcome, pending
    return None, pending


def _replay_pass(run: "Orchestrator", worker_id: WorkId,
                 pending: list[Proposal],
                 unarmed: list[WorkId] | None = None) -> RunOutcome | None:
    """Run the pass a marker NAMES, and hold what it proposed.

    A marker that cannot be ARMED is a lawful no-op, not an error
    (ruling, 2026-08-16). The two ways it happens are both ordinary: the
    recorded pass never committed and its window has since been placed
    or done-covered by another pass in this same tail, or the resume was
    handed fewer inputs than the recording had and the work is not
    offered at all (a pixel-free resume, where placement declines every
    window it cannot see). Neither says the ordering is wrong; both say
    this pass has nothing to contribute HERE, and the marker's only
    remaining job — being the position the entries after it fold from —
    is already done by recording it. Whatever work is genuinely still
    open re-arms live once the tail is re-earned.

    It is NOTED all the same (``unarmed``), because the two causes are
    only indistinguishable one marker at a time: a recovery that met such
    a marker AND ran out of ordering AND is holding a capture with no
    pixels is the second cause and nothing else
    (:func:`_require_the_inputs_the_tail_needs`).
    """
    run._ctx.store.mark_start(worker_id)     # verifies the record stands
    armed = _arm_named(run, worker_id)
    if armed is None:
        # No proposal will ever hold this mark, so it settles where it
        # is met — the marker's position is recorded either way, and
        # that was its only remaining job.
        _settle_mark(run)
        if unarmed is not None:
            unarmed.append(worker_id)
        return None
    proposal = run._propose(armed)
    if run._is_noop(proposal):
        # No commit follows a pass that produced nothing durable; it
        # is settled here, exactly where the recording settled it.
        _settle_mark(run)
        return run._apply(proposal)
    pending.append(proposal)
    return None


def _arm_named(run: "Orchestrator", worker_id: WorkId) -> Armed | None:
    """Bind the pass one marker names — by NAME, never by queue order.

    A descriptor first (the queue owns those names), then the work
    source, which is what a pull job's synthesised descriptor names.
    The enumeration is asked once if the name is unknown, because a
    replay reaches a marker only after every commit before it, and
    the frontier that mints the worker moves with those commits.
    """
    if worker_id not in run._workers:
        run._refresh()
    if worker_id in run._workers:
        return run._arm(worker_id)
    source = run._source
    if source is None or source.family != worker_id.family:
        return None
    return run._arm_job(worker_id.subject)


def _take_pending(run: "Orchestrator", pending: list[Proposal],
                  expected: str) -> Proposal | None:
    """The held pass that would commit exactly this batch, if any.

    SETTLED ids, not proposed ones: the journal records the batch as
    the wall merged it (H4 W2's first ruling), and a re-run fire
    proposes the pre-merge batch it proposed before. The two agree
    whenever no race intervened, which is exactly when comparing them
    naively would be safe — so the comparison is made on the value
    the wall would write.
    """
    for index, proposal in enumerate(pending):
        if run._ctx.engine.settled_id(proposal.batch) == expected:
            return pending.pop(index)
    return None


def _replay_scheduler_commit(run: "Orchestrator") -> bool:
    """Re-derive the one commit shape no DISPATCH produces.

    A sleeping worker's read-set re-declaration — from a decline
    (``_offer``) or from an idle pop (``_bind``). Neither is a pass,
    so neither has a marker; both are pure functions of the store at
    this position, so both are re-derivable here. The enumeration
    goes first because a decline's sleep rides it; the idle drain
    follows, and puts back everything it popped.

    MEASURED, and worth saying: the wall's own run channel holds no such
    commit at all (148 entries — 73 dispatches, 73 pass commits, one
    ingest, one close verdict), because a decline's sleep rides a
    refresh this loop already performs in place, inside ``_absorb``.
    This stays because ``_sleep`` is live code on the recorded side —
    an over-woken worker's idle pop makes exactly this commit — and
    because without it such a commit would leave the walk to the
    caller, where a live run that dispatched before re-deriving it
    would meet the journal's tail refusal instead of the fold.
    """
    before = run._ctx.store.journal_position
    run._refresh()
    if run._ctx.store.journal_position != before:
        return True
    popped: list[WorkId] = []
    try:
        while (worker_id := run._queue.pop()) is not None:
            popped.append(worker_id)
            descriptor, worker = run._workers[worker_id]
            keys = worker.read_keys(run._view)
            if not run._ctx.store.ledger.is_spent(
                    worker_id, descriptor.route,
                    run._ctx.engine.attempt_identity(keys)):
                continue                  # not idle: not this commit
            run._work.idle_pops += 1
            run._sleep(worker_id, keys)
            if run._ctx.store.journal_position != before:
                return True
    finally:
        for worker_id in popped:
            run._queue.push(worker_id)
    return False


def _drop_stale(run: "Orchestrator", pending: list[Proposal]) -> None:
    """Drop held passes whose read-set moved under them, as the wall does.

    The recorded run discarded them too — that is why the ordering holds
    no commit for them — so this is not a replay's own judgement, it is
    the same §7 test applied at the same points.
    """
    for proposal in list(pending):
        if not run._is_current(proposal.armed):
            pending.remove(proposal)
            _settle_mark(run)
            run._work.stale_discards += 1
            run._disarm(proposal.armed)
            if proposal.armed.source is None:
                run._queue.push(proposal.armed.worker_id)


__all__ = ["audit", "recover"]
