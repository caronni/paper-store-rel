from __future__ import annotations

import hashlib
import heapq
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path

from . import data, operator, sched_trace, snapshot
from .data import DecodeRequest
from .descriptor import (
    FactKey,
    PluginDescriptor,
    Subject,
    WorkerBookmark,
)
from .format import close as format_close
from .format.identity import FormatRow
from .plugins import (
    calibrate,
    color_pooled,
    color_refine,
    color_region,
    fields,
    fields_collect,
    local_ctx,
    place_sched,
    plane_k,
    refine,
    survey,
    swim,
    tiles_sched,
    uplift,
)
from .store import _Store
from .store_folds import ADOPT_LAST, ENV_COLOR_ROW_ADOPT

__all__ = [
    "DESCRIPTORS", "DESCRIPTOR_BY_NAME", "DecodeRequest", "decode",
]


ATTEMPT_BUCKETS: tuple[tuple[int, str], ...] = (
    (1, "1"), (2, "2"), (5, "3-5"), (10, "6-10"))


def attempt_bucket(n_attempts: int) -> str:
    for limit, label in ATTEMPT_BUCKETS:
        if n_attempts <= limit:
            return label
    return ">10"


DESCRIPTORS: tuple[PluginDescriptor, ...] = (
    survey.SURVEY_DESCRIPTOR,
    place_sched.PLACE_DESCRIPTOR,
    calibrate.CALIBRATE_DESCRIPTOR,
    calibrate.CTX_DESCRIPTOR,
    color_region.COLOR_DESCRIPTOR,
    color_pooled.POOLED_CTX_DESCRIPTOR,
    tiles_sched.SCAN_DESCRIPTOR,
    tiles_sched.UNION_DESCRIPTOR,
    tiles_sched.RETRY_DESCRIPTOR,
    tiles_sched.COND_DESCRIPTOR,
    local_ctx.LOCAL_DESCRIPTOR,
    fields_collect.COLLECT_DESCRIPTOR,
    fields.FIELDS_DESCRIPTOR,
    refine.REFINE_DESCRIPTOR,
    color_refine.COLOR_REFINE_DESCRIPTOR,
    uplift.UPLIFT_DESCRIPTOR,
    plane_k.PLANEK_DESCRIPTOR,
    swim.SWIM_DESCRIPTOR,
)

DESCRIPTOR_BY_NAME: dict[str, PluginDescriptor] = {
    descriptor.name: descriptor for descriptor in DESCRIPTORS}

#: Single-writer-by-domain, checked at startup (DESCRIPTOR-PLAN D1) and
#: WITHOUT EXEMPTIONS since 2026-09-21.  `revisit` was the one: it
#: re-fired other rows' work as a subscription -- v1's M-pass without a
#: phase -- so it produced their fact types rather than owning one, and
#: `REARM_PLUGINS` named it here.  Dissolving that row emptied the set
#: and the set went with it, which is why this file now spells no
#: plugin name at all (`test_h3_lifecycle` asserts exactly that).
def check_single_writer(
        descriptors: tuple[PluginDescriptor, ...]) -> None:
    producers: dict[type, set[str]] = {}
    for descriptor in descriptors:
        for produced in descriptor.produces:
            producers.setdefault(produced, set()).add(descriptor.name)
    for produced in sorted(producers, key=lambda item: item.__name__):
        names = producers[produced]
        if len(names) < 2:
            continue
        if len({name.split(".")[0] for name in names}) <= 1:
            continue
        raise data.IntegrityError(
            f"fact type {produced.__name__} has multiple writer domains: "
            f"{sorted(names)}")


def _intake_run(
    request: DecodeRequest, row: FormatRow
) -> tuple[tuple[data.Capture, ...], tuple[data.PlaneRaster, ...],
           tuple[object, ...]]:
    from .plugins import intake

    forced = tuple(request.dpi_forced)
    forced += (False,) * (len(request.scans) - len(forced))
    return intake.ingest_captures(request.scans, request.dpis, row.pitch_in,
                                  row.family, request.run_dir, forced)


class _Engine(_Store):

    #: The scheduler trace (sched_trace.py): DEFAULT OFF, armed only by
    #: `_start` under HOLO3_SCHED_TRACE, and MEASUREMENT ONLY -- no
    #: decision in this file reads it back.  `_trace_on` is the single
    #: attribute the hot paths check; class attributes, so an engine
    #: built by hand (contract tests, measure/) is traceless for free.
    _trace: sched_trace.NullTrace | sched_trace.SchedTrace = \
        sched_trace.NullTrace()
    _trace_on: bool = False

    def __init__(self, request: DecodeRequest,
                 events: list[data.Event]) -> None:
        check_single_writer(DESCRIPTORS)
        super().__init__(request, events)
        self._frontier: list[tuple[int, int, str, str, Subject]] = []
        self._seq = 0
        self._inflight: dict[Future, tuple[str, Subject, int, int, str]] = {}
        self._bookmarks: dict[tuple[str, Subject], WorkerBookmark] = {}
        self._index: dict[FactKey, set[tuple[str, Subject]]] = {}
        self._n_certs_at_last_consult = -1
        self._close_progress: format_close.CloseProgress | None = None
        self._consult_cpu_s = 0.0
        self._diag_server: object | None = None
        self._queued: dict[str, int] = {}
        self._stale_skips = 0
        self._retired_count = 0
        self._retire_causes: dict[str, int] = {}
        self._attempts_hist: dict[str, int] = {}
        self._sched_emitted: dict[tuple[str, Subject],
                                  tuple[str, int]] = {}
        self._wakes = 0
        self._stat_board = data.StatBoard()
        self._doors = operator.OperatorDoors()

    def run(self) -> data.RunResult:
        self._start()
        # A RESUME WHOSE FOLDED CERTIFICATES ALREADY CLOSE THE VOLUME
        # (2026-10-03, S8).  The in-loop consult runs only after a merge
        # that MINTED, so a snapshot that closes on replay -- the
        # analyzer's export-facts route resumes exactly those -- used to
        # schedule the whole residue until a new mint or exhaustion.  One
        # consult here, on the replayed set; the ordinary `_close_decide`
        # rules apply unchanged: `--complete` defers the decision to the
        # final consult, so there it COUNTS and the run proceeds (API.md:
        # "`--complete` defers the close until the frontier is
        # exhausted"), `--no-close` observes.  `_n_certs_at_last_consult`
        # de-duplicates the loop's next consult.
        if self._request.resume is not None and self._certificates:
            result = self._close_consult(final=False)
            if result is not None and result.status == "verified":
                return self._finish(result)
        self._doors.arm()
        verified: format_close.CloseResult | None = None
        draining = False
        abandoned = False
        executor = ThreadPoolExecutor(max_workers=self._request.workers)
        try:
            # This loop turns of the order of ten times a second, so the
            # trace's brackets are called unconditionally: on the null
            # object they are no-ops.  The hot paths -- `_push_worker`,
            # `_touch`, `_ingest`, `_fill` -- check `_trace_on` instead.
            trace = self._trace
            while True:
                trace.sample(self)
                # THE ORDERLY STOP DRAINS (2026-10-03, S8).  A stop stops
                # SCHEDULING, not merging: every job already in flight is
                # running (inflight <= workers, so `cancel_futures` never
                # had anything to cancel) and the process joins its
                # thread at exit anyway, so its facts are merged here
                # instead of thrown away after the wait.  A second signal
                # abandons the drain (operator.py).
                if self._doors.service(self) and not draining:
                    draining = True
                    print(f"stop requested: draining {len(self._inflight)} "
                          f"in-flight jobs", file=sys.stderr, flush=True)
                if self._doors.abandon_wanted:
                    abandoned = True
                    print(f"stop: abandoning {len(self._inflight)} "
                          f"in-flight jobs; their facts are not in the "
                          f"snapshot and the process exits when they "
                          f"return", file=sys.stderr, flush=True)
                    break
                if not draining:
                    trace.enter("fill")
                    try:
                        self._fill(executor)
                    finally:
                        trace.leave()
                if not self._inflight:
                    break
                trace.enter("wait")
                try:
                    done, _pending = wait(
                        set(self._inflight), return_when=FIRST_COMPLETED,
                        timeout=operator.DRAIN_POLL_S if draining else None)
                finally:
                    trace.leave()
                grew = False
                # Futures completing in one wait are folded in SEAT-SEQUENCE order --
                # the ordinal stamped when the job was queued, not the order threads
                # happened to finish (C-12: every ordering on values, never arrival
                # order).
                trace.enter("merge")
                try:
                    for future in sorted(done,
                                         key=lambda f: self._inflight[f][3]):
                        grew = self._merge(future) or grew
                finally:
                    trace.leave()
                trace.enter("stat")
                try:
                    self._stat_board.value = self._engine_stat()
                finally:
                    trace.leave()
                # A verified close preempts everything and is NOT a scheduler row: it
                # is consulted here, out of band, after any merge that grew the
                # certificate set, and skips the whole tail -- one of the two
                # mechanisms behind v1's 49.67 s -> 13.46 s bench (parking the other).
                if grew:
                    result = self._close_consult(final=False)
                    if result is not None and result.status == "verified":
                        verified = result
                        break
            # A drained stop ends like an exhausted frontier: the deciding
            # consult runs (under `--complete` it is the only one that
            # decides).  An abandoned one skips it -- the operator asked
            # to leave now.
            if verified is None and not abandoned:
                result = self._close_consult(final=True)
                if result is not None and result.status == "verified":
                    verified = result
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            self._doors.disarm()
        return self._finish(verified)

    def _start(self) -> None:
        self._request.run_dir.mkdir(parents=True, exist_ok=True)
        if sched_trace.enabled_by_env():
            self._trace = sched_trace.arm(self._request.run_dir,
                                          workers=self._request.workers)
            self._trace_on = True
            print(f"sched-trace: armed, writing "
                  f"{self._request.run_dir / sched_trace.DIR_NAME}",
                  file=sys.stderr, flush=True)
        (self._request.run_dir / "argv").write_text(
            " ".join(sys.argv) + "\n")
        described = ""
        try:
            described = subprocess.run(
                ["git", "-C", str(Path(__file__).resolve().parents[1]),
                 "describe", "--always", "--dirty", "--abbrev=40"],
                capture_output=True, text=True).stdout.strip()
        except OSError:
            pass
        # The colour-row adoption hatch is part of WHICH receiver ran
        # (store_folds: `improve`/`nonworse` adopt other rows than the
        # shipped `last`), and an environment variable leaves no trace in
        # argv -- so the tree record names it, always, and RunOpen
        # carries it (2026-10-03, S9).
        adopt = f"{ENV_COLOR_ROW_ADOPT}={self._color_row_adopt}"
        (self._request.run_dir / "tree").write_text(
            "".join(f"{line}\n" for line in (described, adopt) if line))
        if self._color_row_adopt != ADOPT_LAST:
            print(f"{adopt}: colour rows adopt by "
                  f"'{self._color_row_adopt}', not the shipped "
                  f"'{ADOPT_LAST}' -- a measurement receiver",
                  file=sys.stderr, flush=True)
        if self._request.diag_port is not None:
            self._diag_server = operator._diag_serve(
                self._request.diag_port, self._events, self._stat_board)
        self._trace.enter("intake")
        try:
            captures, rasters, events = _intake_run(self._request, self.row)
        finally:
            self._trace.leave()
        self._rasters = rasters
        for raster in rasters:
            lane = (raster.capture_id, raster.level_index)
            self._planes_by_lane.setdefault(lane, {})[raster.plane] = raster
        self._events.append(data.RunOpen(
            format_id=self.row.row_id,
            display_id=self.row.display_id,
            pages=len(self.page_domain),
            tiles_yx=self.row.tiles_yx,
            stream_ids=tuple(s.stream_id for s in self.row.streams),
            n_captures=len(captures),
            workers=self._request.workers,
            family=self.row.family.value,
            pitch_in=float(self.row.pitch_in),
            color_row_adopt=self._color_row_adopt))
        for event in events:
            self._events.append(event)
        for capture in sorted(captures, key=lambda c: c.capture_id):
            self._ingest(capture)
        if self._request.resume is not None:
            self._replay(snapshot.read(self._request.resume))

    def _replay(self, facts: tuple[object, ...]) -> None:
        """Fold a snapshot back in, and tell diag what came with it.

        The fold is the ordinary `_ingest`, fact by fact — there is no
        replay path.  The one addition is the event, and it is pure
        accounting: nothing in the engine, the store or the schedule
        reads it.
        """
        counts: dict[str, int] = {}
        for fact in facts:
            self._ingest(fact)
            name = type(fact).__name__
            counts[name] = counts.get(name, 0) + 1
        self._events.append(data.SnapshotReplayed(
            facts=tuple(sorted(counts.items())),
            certified=len(self._certificates)))

    def _note_attempt(self, n_attempts: int) -> None:
        bucket = attempt_bucket(n_attempts)
        previous = (None if n_attempts == 1
                    else attempt_bucket(n_attempts - 1))
        if previous == bucket:
            return
        if previous is not None:
            self._attempts_hist[previous] -= 1
        self._attempts_hist[bucket] = self._attempts_hist.get(bucket, 0) + 1

    def _engine_stat(self) -> data.EngineStat:
        return data.EngineStat(
            queued=tuple(sorted(
                (plugin, count)
                for plugin, count in self._queued.items() if count)),
            inflight=len(self._inflight),
            stale_skips=self._stale_skips,
            retired=self._retired_count,
            attempts_hist=tuple(sorted(
                (label, count)
                for label, count in self._attempts_hist.items() if count)),
            wakes=self._wakes,
            inflight_jobs=tuple(
                (plugin, subject, stage)
                for plugin, subject, _cost, _seq, stage
                in sorted(self._inflight.values(),
                          key=lambda row: row[3])),
            consult_cpu_s=self._consult_cpu_s,
            retire_causes=tuple(sorted(self._retire_causes.items())))

    def _push_worker(self, worker: WorkerBookmark) -> None:
        on = self._trace_on
        trace = self._trace
        if on:
            trace.enter("push")
        try:
            if worker.inflight:
                worker.pending = True
                if on:
                    trace.push(worker.plugin, worker.subject,
                               "inflight_pending")
                return
            descriptor = DESCRIPTOR_BY_NAME[worker.plugin]
            # RETIRE BEFORE STAGE, and on a standing seat too.  A wake
            # that leaves the price unchanged returns at `seat_stands`
            # and is never popped, so a row whose retire clause came
            # true while it sat on a standing seat used to wait for a
            # pop it might never get -- measured on sheet H, where
            # `place` took 35,418 wakes and retired 0 windows in 36
            # minutes because the frontier never reached its seats.
            # Asking here costs one predicate per wake and saves the
            # stage call below whenever it fires.
            cause = (trace.timed("retire", worker.plugin,
                                 descriptor.retire, self, worker.subject)
                     if on else descriptor.retire(self, worker.subject))
            if cause is not None:
                if on:
                    trace.push(worker.plugin, worker.subject,
                               "retire_at_push")
                self._retire_worker(worker, cause)
                return
            stage = (trace.timed("stage", worker.plugin, descriptor.stage,
                                 self, worker.subject) if on
                     else descriptor.stage(self, worker.subject))
            if stage is None:
                if on:
                    trace.push(worker.plugin, worker.subject, "stage_none")
                return
            if on:
                cost = trace.timed("cost", worker.plugin, descriptor.cost,
                                   self, worker.subject, stage,
                                   worker.attempts, worker.last_cost)
            else:
                cost = descriptor.cost(self, worker.subject, stage, worker.attempts,
                                       worker.last_cost)
            worker.last_cost = cost
            # A wake that leaves the price unchanged does not re-queue: the
            # standing heap entry stands, and the version floor is what makes
            # it fire again.  A wake that moves the price pushes a new seat
            # and the old entry is skipped at pop (lazy deletion).
            superseded = False
            if worker.seat_seq >= 0:
                if cost == worker.seat_cost:
                    if on:
                        trace.push(worker.plugin, worker.subject,
                                   "seat_stands")
                    return
                self._queued[worker.plugin] -= 1
                superseded = True
            self._seq += 1
            worker.seat_seq = self._seq
            worker.seat_cost = cost
            heapq.heappush(
                self._frontier,
                (cost, self._seq, worker.plugin, stage, worker.subject))
            self._queued[worker.plugin] = self._queued.get(
                worker.plugin, 0) + 1
            if on:
                trace.push(worker.plugin, worker.subject,
                           "reseat_price" if superseded else "first_seat")
                trace.seat(worker.plugin, worker.subject, stage, cost,
                           superseded, len(self._frontier))
            seat = (worker.plugin, worker.subject)
            if self._sched_emitted.get(seat) != (stage, cost):
                self._sched_emitted[seat] = (stage, cost)
                self._events.append(data.WorkerSeated(
                    plugin=worker.plugin, subject=worker.subject,
                    stage=stage, cost=cost))
        finally:
            if on:
                trace.leave()

    def _repush(self, plugin: str, subject: Subject) -> None:
        worker = self._bookmarks.get((plugin, subject))
        if worker is None:
            return
        worker.version += 1
        self._push_worker(worker)

    def _register_reads(self, worker: WorkerBookmark,
                        keys: tuple[FactKey, ...]) -> None:
        key = (worker.plugin, worker.subject)
        for read_key in keys:
            self._index.setdefault(read_key, set()).add(key)

    def _retire_worker(self, worker: WorkerBookmark,
                       cause: str) -> None:
        """One door out of the frontier, for every row, with its CAUSE.

        The cause travels from the one `descriptor.retire` consult that
        just said yes -- no row is re-asked, and the engine never reads
        the string it tallies.

        TWO DOORS REACH HERE -- the push and the pop -- so "a worker
        retires once" stopped being structural when the second one
        opened (2026-09-21).  `_retired_count`, the cause tally and the
        event stream all assume it, so the guard is asserted rather than
        argued.  The SEAT goes with the row: a standing heap entry for a
        retired worker is skipped at the pop, and leaving it counted
        until then overstated `EngineStat.queued` -- permanently for
        entries still in the heap at RunDone.
        """
        if worker.retired:
            return
        if worker.seat_seq >= 0:
            self._queued[worker.plugin] -= 1
            worker.seat_seq = -1
        worker.retired = True
        self._retired_count += 1
        self._retire_causes[cause] = self._retire_causes.get(cause, 0) + 1
        self._sched_emitted.pop((worker.plugin, worker.subject), None)
        self._events.append(data.WorkerRetired(
            plugin=worker.plugin, subject=worker.subject, cause=cause))
        if self._trace_on:
            self._trace.retire(worker.plugin, worker.subject, cause)
        key = (worker.plugin, worker.subject)
        for read_key in worker.reads:
            subscribers = self._index.get(read_key)
            if subscribers is None:
                continue
            subscribers.discard(key)
            if not subscribers:
                del self._index[read_key]

    def _births(self, fact: object) -> None:
        on = self._trace_on
        trace = self._trace
        for descriptor in DESCRIPTORS:
            if not isinstance(fact, descriptor.born_by):
                continue
            subjects = (trace.timed("subjects_of", descriptor.name,
                                    descriptor.subjects_of, self, fact) if on
                        else descriptor.subjects_of(self, fact))
            for subject in subjects:
                key = (descriptor.name, subject)
                standing = self._bookmarks.get(key)
                if standing is not None:
                    # THE ONE PATH BY WHICH A LIVE WORKER'S READS GROW,
                    # and it is a BIRTH: the fact that creates this
                    # row's work arrived again, so its inputs may have
                    # grown with it -- a re-placed window has a new
                    # reach and possibly a new page.  Nothing re-derives
                    # a standing worker's reads on a wake (2026-09-21):
                    # reads are fixed at birth, and every derived
                    # relation belongs to the store, which routes a
                    # change to the key its owner already holds.  Stale
                    # keys from an old reach stay subscribed -- over-
                    # declaring costs a wake, never a wrong answer --
                    # and go when the row retires.
                    if on:
                        trace.birth(descriptor.name, subject, True)
                    # A RETIRED row takes no new keys (review
                    # 2026-09-21).  `_retire_worker` dropped its whole
                    # read set from the index and `_touch` skips it, so
                    # re-subscribing here grows `_index` with entries
                    # nothing will ever read -- and makes "they go when
                    # the row retires" false in the letter.  The birth
                    # itself is still counted above: the fact arrived.
                    if standing.retired:
                        continue
                    declared = (
                        trace.timed("reads", descriptor.name,
                                    descriptor.reads, self, subject) if on
                        else descriptor.reads(self, subject))
                    fresh = tuple(
                        read_key for read_key in declared
                        if key not in self._index.get(read_key, ()))
                    if fresh:
                        standing.reads += fresh
                        self._register_reads(standing, fresh)
                    continue
                if on:
                    trace.birth(descriptor.name, subject, False)
                worker = WorkerBookmark(
                    plugin=descriptor.name, subject=subject,
                    reads=(trace.timed("reads", descriptor.name,
                                       descriptor.reads, self, subject)
                           if on else descriptor.reads(self, subject)))
                self._bookmarks[key] = worker
                self._register_reads(worker, worker.reads)
                self._push_worker(worker)

    def _touch(self, keys: tuple[FactKey, ...]) -> None:
        for fact_key in keys:
            subscribers = self._index.get(fact_key)
            if not subscribers:
                continue
            for worker_key in sorted(subscribers):
                worker = self._bookmarks.get(worker_key)
                if worker is None or worker.retired:
                    continue
                worker.version += 1
                self._wakes += 1
                if self._trace_on:
                    self._trace.wake(worker.plugin, worker.subject,
                                     fact_key[0])
                self._push_worker(worker)

    def _ingest(self, fact: object) -> tuple[bool, str]:
        if not self._trace_on:
            changed, keys, kind = self._fold(fact)
            if changed:
                self._births(fact)
                self._touch(keys)
            return changed, kind
        trace = self._trace
        trace.enter("fold")
        try:
            changed, keys, kind = self._fold(fact)
        finally:
            trace.leave()
        # The evidence folds record what the loss did; the subscriber
        # count those records want lives HERE, so they are written out
        # once the fold that produced them has returned.
        trace.folds.flush(self._index)
        if changed:
            trace.enter("births")
            try:
                self._births(fact)
            finally:
                trace.leave()
            trace.enter("touch")
            try:
                self._touch(keys)
            finally:
                trace.leave()
        return changed, kind

    def _fill(self, executor: ThreadPoolExecutor) -> None:
        on = self._trace_on
        trace = self._trace
        while (len(self._inflight) < self._request.workers
               and self._frontier):
            cost, seq, plugin, stage, subject = heapq.heappop(self._frontier)
            worker = self._bookmarks.get((plugin, subject))
            if worker is None or seq != worker.seat_seq:
                self._stale_skips += 1
                if on:
                    trace.pop(plugin, subject, "stale_seq")
                continue
            worker.seat_seq = -1
            self._queued[plugin] -= 1
            # UNREACHABLE since 799201c5: `_retire_worker` drops the seat (seat_seq -1),
            # so a retired worker's entry fails the seq test above first.  Kept: the
            # trace's exit law (`sched_trace.POP_CAUSES`, checked by AST) needs the label.
            if worker.retired:
                if on:
                    trace.pop(plugin, subject, "retired")
                continue
            # One job in flight per worker, at the POP as well as the push (D6
            # addendum 8a).  Without this door a stranded pre-fire entry plus one
            # wake fires a SECOND concurrent job for the same worker -- reproduced
            # at workers=2 before 2543bbe, attempts double-counted.
            if worker.inflight:
                worker.pending = True
                if on:
                    trace.pop(plugin, subject, "inflight_pending")
                continue
            descriptor = DESCRIPTOR_BY_NAME[plugin]
            cause = (trace.timed("retire", plugin, descriptor.retire, self,
                                 subject) if on
                     else descriptor.retire(self, subject))
            if cause is not None:
                if on:
                    trace.pop(plugin, subject, "retire_at_pop")
                self._retire_worker(worker, cause)
                continue
            # The version floor is the ENTIRE staleness story (D6 addendum 6):
            # bookmarks bump only on a real data change, so a worker that would
            # read exactly what it read last time is skipped here.  A worker that
            # needs a digest has the wrong key -- subscribe finer instead.
            if worker.tried_version == worker.version:
                self._stale_skips += 1
                if on:
                    trace.pop(plugin, subject, "version_floor")
                continue
            tried_version_before = worker.tried_version
            worker.tried_version = worker.version
            if not (trace.timed("eligible", plugin, descriptor.eligible,
                                self, subject) if on
                    else descriptor.eligible(self, subject)):
                if on:
                    trace.pop(plugin, subject, "not_eligible")
                continue
            fresh_stage = (trace.timed("stage", plugin, descriptor.stage,
                                       self, subject) if on
                           else descriptor.stage(self, subject))
            if fresh_stage is None:
                if on:
                    trace.pop(plugin, subject, "stage_none")
                continue
            if on:
                fresh_cost = trace.timed(
                    "cost", plugin, descriptor.cost, self, subject,
                    fresh_stage, worker.attempts, worker.last_cost)
                seat_cost = trace.timed(
                    "cost", plugin, descriptor.cost, self, subject, stage,
                    worker.attempts, worker.last_cost)
                repriced = fresh_cost > seat_cost
            else:
                repriced = (
                    descriptor.cost(self, subject, fresh_stage,
                                    worker.attempts, worker.last_cost)
                    > descriptor.cost(self, subject, stage, worker.attempts,
                                      worker.last_cost))
            if repriced:
                if on:
                    trace.pop(plugin, subject, "cost_repush")
                self._repush(plugin, subject)
                continue
            if on:
                trace.clear_input()
                job = trace.timed("prepare", plugin, descriptor.prepare,
                                  self, subject, fresh_stage)
            else:
                job = descriptor.prepare(self, subject, fresh_stage)
            if job is None:
                if on:
                    trace.pop(plugin, subject, "prepare_none")
                continue
            worker.attempts += 1
            self._note_attempt(worker.attempts)
            worker.inflight = True
            if on:
                trace.pop(plugin, subject, "fired")
                trace.fire(plugin, subject, seq, fresh_stage, cost,
                           worker.attempts, worker.version,
                           tried_version_before)
            future = executor.submit(job)
            self._inflight[future] = (plugin, subject, cost, seq, fresh_stage)

    def _merge(self, future: Future) -> bool:
        plugin, subject, cost, _seq, _stage = self._inflight.pop(future)
        result: data.JobResult = future.result()
        account = self._account.setdefault(plugin, [0, 0.0, 0, 0, 0])
        account[0] += 1
        account[1] += float(result.cpu_s)
        n_certificates = 0
        n_poses = 0
        n_words = 0
        n_refused = 0
        certs_grew = False
        worker = self._bookmarks[(plugin, subject)]
        # THE MERGING JOB, shown to the folds for the length of its own
        # facts (`_Store.merging_sleep_version`): a fold that would put
        # the job's subject to sleep has to know whether anything woke
        # the bookmark while the pass was in flight, and that is the
        # version the pass was PREPARED at against the version now.
        # Taken before the job's own facts fold, so their wakes are not
        # counted as somebody else's.
        self._merging = worker
        self._merging_woken = worker.version != worker.tried_version
        try:
            for fact in result.facts:
                changed, kind = self._ingest(fact)
                if not changed:
                    n_refused += 1
                    continue
                if kind == "certificate":
                    n_certificates += 1
                    certs_grew = True
                elif kind.startswith("pose"):
                    n_poses += 1
                    if kind == "pose_word":
                        n_words += 1
        finally:
            self._merging = None
            self._merging_woken = False
        account[2] += n_certificates
        account[3] += n_poses
        account[4] += n_words
        for event in result.events:
            self._events.append(event)
        self._events.append(data.JobDone(
            plugin=plugin, subject=subject, cost=cost,
            cpu_s=float(result.cpu_s), n_certificates=n_certificates,
            n_poses=n_poses, n_words=n_words))
        if self._trace_on:
            # `n_refused` = facts the folds discarded on a value compare:
            # work computed on superseded inputs, invisible in JobDone.
            self._trace.fire_done(
                plugin, subject, float(result.cpu_s), n_certificates,
                n_poses, n_words, n_facts=len(result.facts),
                n_facts_refused=n_refused,
                reason=self._trace.result_reasons(result.facts))
        worker.inflight = False
        if worker.pending:
            worker.pending = False
            self._push_worker(worker)
        return certs_grew

    def _close_consult(
            self, final: bool) -> format_close.CloseResult | None:
        started = time.thread_time()
        self._trace.enter("close")
        try:
            return self._close_decide(final)
        finally:
            self._consult_cpu_s += time.thread_time() - started
            self._trace.leave()

    def _close_decide(
            self, final: bool) -> format_close.CloseResult | None:
        n_certs = len(self._certificates)
        if not final and n_certs == self._n_certs_at_last_consult:
            return None
        self._n_certs_at_last_consult = n_certs
        if self._close_progress is None:
            self._close_progress = format_close.CloseProgress(self.row)
        progress = self._close_progress
        progress.absorb(self._certificates)
        ready, count_k, count_blocks = progress.count_progress()
        result: format_close.CloseResult | None = None
        # `--complete` defers the DECISION only.  The counting consult still
        # runs whenever the certificate set grows, so K, the metadata rank and
        # the per-block counts stay live; suppressing it once left the operator
        # watching certificates pile up beside "K unknown" (2026-08-13).
        solve = (not self._request.no_close and n_certs > 0
                 and (final if self._request.complete
                      else (ready or final))
                 and (final or progress.close_is_new()))
        if solve:
            result = progress.close()
        self._emit_close_check(n_certs, ready, result, progress,
                               count_k, count_blocks)
        if result is not None and result.status == "integrity_failure":
            raise data.IntegrityError(
                result.reason or "close integrity failure")
        return result

    def _emit_close_check(
            self, n_certs: int, ready: bool,
            result: format_close.CloseResult | None,
            progress: format_close.CloseProgress, count_k: int | None,
            count_blocks: tuple[data.CloseBlockRow, ...]) -> None:
        if result is not None:
            blocks = result.blocks
            symbols_used = result.symbols_used
            k_total = result.k_total
            status = result.status
        else:
            blocks = count_blocks
            symbols_used = sum(row.have for row in count_blocks)
            k_total = count_k
            if self._request.complete and not self._request.no_close:
                status = "deferred"
            else:
                status = "count_ready" if ready else "open"
        self._events.append(data.CloseCheck(
            certified=n_certs, symbols_used=symbols_used, k_total=k_total,
            metadata_rank=progress.metadata_rank,
            metadata_n_unique=progress.metadata_n_unique,
            blocks=blocks, status=status,
            blocks_counting=result is None))

    def _finish(
            self,
            verified: format_close.CloseResult | None) -> data.RunResult:
        payload = verified.payload if verified is not None else None
        sha = (hashlib.sha256(payload).hexdigest()
               if payload is not None else None)
        status = "verified" if payload is not None else "open"
        final_stat = self._engine_stat()
        self._stat_board.value = final_stat
        self._events.append(final_stat)
        self._events.append(data.RunDone(
            status=status, payload_sha256=sha,
            n_bytes=len(payload) if payload is not None else None,
            certified=len(self._certificates)))
        # The run's OWN products go down before the tracer's final dump:
        # a failed measurement may never cost the sheet it measures.  The
        # tracer no longer needs a guard here either — `SchedTrace.dump`
        # swallows its own failure and `finish` goes through it (review
        # 2026-09-17).
        operator.snapshot_traced(self)
        if self._trace_on:
            self._trace.finish(self)
            self._trace_on = False
            self._trace = sched_trace.NullTrace()
            sched_trace.disarm()
        operator._diag_products(self._request.run_dir, self._events)
        operator._diag_stop(self._diag_server)
        rows = tuple(
            data.PluginRow(plugin, int(values[0]), float(values[1]),
                           int(values[2]), int(values[3]), int(values[4]))
            for plugin, values in sorted(self._account.items()))
        return data.RunResult(
            status=status, payload=payload, payload_sha256=sha,
            certified=len(self._certificates), plugin_rows=rows)



def decode(request: DecodeRequest,
           events: list[data.Event] | None = None) -> data.RunResult:
    return _Engine(request, [] if events is None else events).run()
