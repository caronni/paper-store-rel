from __future__ import annotations

import hashlib
import heapq
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path

from . import data, snapshot
from .data import DecodeRequest, WindowId
from .descriptor import (
    FactKey,
    KEY_POSE_AFFINE,
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
    local_ctx,
    place,
    place_sched,
    plane_k,
    refine,
    revisit,
    survey,
    swim,
    tiles,
    uplift,
)
from .store import _Store

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
    tiles.SCAN_DESCRIPTOR,
    tiles.UNION_DESCRIPTOR,
    tiles.RETRY_DESCRIPTOR,
    local_ctx.LOCAL_DESCRIPTOR,
    fields.FIELDS_DESCRIPTOR,
    refine.REFINE_DESCRIPTOR,
    color_refine.COLOR_REFINE_DESCRIPTOR,
    revisit.REVISIT_DESCRIPTOR,
    uplift.UPLIFT_DESCRIPTOR,
    plane_k.PLANEK_DESCRIPTOR,
    swim.SWIM_DESCRIPTOR,
)

DESCRIPTOR_BY_NAME: dict[str, PluginDescriptor] = {
    descriptor.name: descriptor for descriptor in DESCRIPTORS}

REARM_PLUGINS: frozenset[str] = frozenset({"revisit"})


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
        prefixes = {name.split(".")[0] for name in names
                    if name not in REARM_PLUGINS}
        if len(prefixes) <= 1:
            continue
        raise data.IntegrityError(
            f"fact type {produced.__name__} has multiple writer domains: "
            f"{sorted(names)}")


def _intake_run(
    request: DecodeRequest, row: FormatRow
) -> tuple[tuple[data.Capture, ...], tuple[data.PlaneRaster, ...],
           tuple[object, ...]]:
    from .plugins import intake

    return intake.ingest_captures(request.scans, request.dpis, row.pitch_in,
                                  row.family, request.run_dir)


def _diag_serve(port: int, events: list[data.Event],
                board: data.StatBoard) -> object | None:
    try:
        from .diag import server

        return server.serve(port, events, board)
    except Exception as exc:
        print(f"diag: viewer unavailable ({exc})", file=sys.stderr)
        return None


def _diag_stop(server: object | None) -> None:
    if server is None:
        return
    try:
        server.finish()
    except Exception:
        pass


OPERATOR_SIGNALS: tuple[int, ...] = tuple(
    getattr(signal, name) for name in ("SIGINT", "SIGTERM", "SIGUSR1",
                                       "SIGINFO")
    if hasattr(signal, name))


def status_rows(events: list[data.Event]) -> tuple[str, ...]:
    """The six status rows plus the plane split, folded from the events
    on demand — the shell's answer to ctrl-T / SIGINFO / SIGUSR1."""
    try:
        from .diag import model, readout

        folded = model.fold(model.empty(), events)
        rows = list(readout.all_rows(folded))
        splits = readout.plane_cert_counts(folded)
        if len(splits) > 1:
            rows.append("planes   certified [" + " · ".join(
                f"{stream}:{count}" for stream, count in splits) + "]")
        return tuple(rows)
    except Exception as exc:
        return (f"status   rows unavailable ({exc})",)


def _write_snapshot(path: Path, store: object) -> None:
    """The final fact dump, best effort.

    A run that recovered its payload has done its job; a full disk or a
    vanished run dir at exit does not take that away.  Only the OS error
    is caught — a fact the writer cannot encode is still a fatal bug
    (the reader could not rebuild it), and the failure is always named.

    The write is ATOMIC and KEEPS THE PREDECESSOR (2026-09-04): the facts
    go to `<name>.tmp` first, the standing file is moved to `<name>.bak`,
    and the temporary is renamed into place — an interrupted write can
    leave neither a half-written snapshot nor no snapshot at all, and the
    last good one survives one bad one.
    """
    tmp = path.with_name(path.name + ".tmp")
    bak = path.with_name(path.name + ".bak")
    try:
        snapshot.write(tmp, snapshot.collect(store))
        if path.exists():
            os.replace(path, bak)
        os.replace(tmp, path)
    except OSError as exc:
        print(f"snapshot: {path} not written ({exc})", file=sys.stderr)


def _diag_products(run_dir: Path, events: list[data.Event]) -> None:
    try:
        from .diag import model, panes, report

        folded = model.fold(model.empty(), events)
        report.write_events_jsonl(run_dir / "events.jsonl", events)
        report.write_report(run_dir / "report.json", folded)
        for (pane, selector), png in sorted(panes.pin_panes(folded).items()):
            (run_dir / f"pane-{pane}-{selector}.png").write_bytes(png)
    except Exception as exc:
        print(f"diag: run-dir products failed ({exc})", file=sys.stderr)



class _Engine(_Store):

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
        self._sched_emitted: dict[Subject, tuple[str, int]] = {}
        self._wakes = 0
        self._stat_board = data.StatBoard()
        self._dump_wanted = False
        self._status_wanted = False
        self._stop_wanted = False
        self._snapshot_due: float | None = None
        self._saved_handlers: dict[int, object] = {}

    def run(self) -> data.RunResult:
        self._start()
        self._arm_operator_signals()
        verified: format_close.CloseResult | None = None
        executor = ThreadPoolExecutor(max_workers=self._request.workers)
        try:
            while True:
                if self._service_operator():
                    break
                self._fill(executor)
                if not self._inflight:
                    break
                done, _pending = wait(set(self._inflight),
                                      return_when=FIRST_COMPLETED)
                grew = False
                for future in sorted(done,
                                     key=lambda f: self._inflight[f][3]):
                    grew = self._merge(future) or grew
                self._stat_board.value = self._engine_stat()
                if grew:
                    result = self._close_consult(final=False)
                    if result is not None and result.status == "verified":
                        verified = result
                        break
            if verified is None and not self._stop_wanted:
                result = self._close_consult(final=True)
                if result is not None and result.status == "verified":
                    verified = result
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            self._disarm_operator_signals()
        return self._finish(verified)

    # The operator's three doors, all served at the loop top where the
    # store is consistent (the merge thread is this thread): SIGUSR1 dumps
    # the facts and prints the status rows; SIGINFO (ctrl-T on BSD/macOS)
    # prints the rows; SIGINT/SIGTERM ask for an ORDERLY stop — the loop
    # breaks and `_finish` writes every product the run would have written
    # at exhaustion.  A second SIGINT restores the default handler, so a
    # third one kills.  The safety snapshot every `snapshot_every_s`
    # seconds is the one licensed wall-clock site of this module: a
    # cadence, never an ordering or a gate.
    def _arm_operator_signals(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        for signum in OPERATOR_SIGNALS:
            self._saved_handlers[signum] = signal.signal(
                signum, self._on_operator_signal)

    def _disarm_operator_signals(self) -> None:
        for signum, handler in self._saved_handlers.items():
            signal.signal(signum, handler)
        self._saved_handlers = {}

    def _on_operator_signal(self, signum: int, _frame: object) -> None:
        if signum == getattr(signal, "SIGUSR1", None):
            self._dump_wanted = True
            self._status_wanted = True
        elif signum == getattr(signal, "SIGINFO", None):
            self._status_wanted = True
        else:
            if self._stop_wanted and signum == signal.SIGINT:
                signal.signal(signal.SIGINT, signal.default_int_handler)
            self._stop_wanted = True
            print(f"operator: signal {signum}, stopping at the next "
                  f"consistent point (a second ctrl-C kills)",
                  file=sys.stderr, flush=True)

    def _service_operator(self) -> bool:
        every = self._request.snapshot_every_s
        if every:
            now = time.monotonic()
            if self._snapshot_due is None:
                self._snapshot_due = now + float(every)
            elif now >= self._snapshot_due:
                self._dump_wanted = True
                self._snapshot_due = now + float(every)
        if self._dump_wanted:
            self._dump_wanted = False
            _write_snapshot(self._request.run_dir / snapshot.NAME, self)
            print(f"snapshot: {len(self._certificates)} certificates "
                  f"written to {self._request.run_dir / snapshot.NAME}",
                  file=sys.stderr, flush=True)
        if self._status_wanted:
            self._status_wanted = False
            for row in status_rows(self._events):
                print(row, file=sys.stderr, flush=True)
        return self._stop_wanted

    def _start(self) -> None:
        self._request.run_dir.mkdir(parents=True, exist_ok=True)
        (self._request.run_dir / "argv").write_text(
            " ".join(sys.argv) + "\n")
        try:
            described = subprocess.run(
                ["git", "-C", str(Path(__file__).resolve().parents[1]),
                 "describe", "--always", "--dirty", "--abbrev=40"],
                capture_output=True, text=True).stdout.strip()
            if described:
                (self._request.run_dir / "tree").write_text(described + "\n")
        except OSError:
            pass
        if self._request.diag_port is not None:
            self._diag_server = _diag_serve(self._request.diag_port,
                                            self._events, self._stat_board)
        captures, rasters, events = _intake_run(self._request, self.row)
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
            pitch_in=float(self.row.pitch_in),
            plane_fields=bool(self._request.plane_fields)))
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
        if worker.inflight:
            worker.pending = True
            return
        descriptor = DESCRIPTOR_BY_NAME[worker.plugin]
        stage = descriptor.stage(self, worker.subject)
        if stage is None:
            return
        cost = descriptor.cost(self, worker.subject, stage, worker.attempts,
                               worker.last_cost)
        worker.last_cost = cost
        if worker.seat_seq >= 0:
            if cost == worker.seat_cost:
                return
            self._queued[worker.plugin] -= 1
        self._seq += 1
        worker.seat_seq = self._seq
        worker.seat_cost = cost
        heapq.heappush(
            self._frontier,
            (cost, self._seq, worker.plugin, stage, worker.subject))
        self._queued[worker.plugin] = self._queued.get(worker.plugin, 0) + 1
        if worker.plugin == "place":
            if self._sched_emitted.get(worker.subject) != (stage, cost):
                self._sched_emitted[worker.subject] = (stage, cost)
                wid = worker.subject
                self._events.append(data.WindowScheduled(
                    capture=wid[0], level_index=wid[1], region_index=wid[2],
                    extent_cells=wid[3], stage=stage, cost=cost))

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

    def _rederive_reads(self, worker: WorkerBookmark) -> None:
        descriptor = DESCRIPTOR_BY_NAME[worker.plugin]
        keys = descriptor.reads(self, worker.subject)
        if keys == worker.reads:
            return
        key = (worker.plugin, worker.subject)
        held = set(keys)
        for read_key in worker.reads:
            if read_key in held:
                continue
            subscribers = self._index.get(read_key)
            if subscribers is None:
                continue
            subscribers.discard(key)
            if not subscribers:
                del self._index[read_key]
        worker.reads = keys
        self._register_reads(worker, keys)

    def _retire_worker(self, worker: WorkerBookmark) -> None:
        worker.retired = True
        self._retired_count += 1
        if worker.plugin == "place":
            self._sched_emitted.pop(worker.subject, None)
            wid = worker.subject
            # `_fill` reached here through `descriptor.retire`, which for
            # place IS `place_retire_cause(...) is not None`, asked in
            # this thread with no ingest between: the clause still stands
            # and is still the same one.  Re-asking keeps the cause out
            # of the retire contract the other sixteen plugins share.
            cause = (place_sched.place_retire_cause(self, wid)
                     or place_sched.RETIRE_UNKNOWN)
            self._retire_causes[cause] = self._retire_causes.get(
                cause, 0) + 1
            self._events.append(data.WindowRetired(
                capture=wid[0], level_index=wid[1], region_index=wid[2],
                extent_cells=wid[3], cause=cause))
        key = (worker.plugin, worker.subject)
        for read_key in worker.reads:
            subscribers = self._index.get(read_key)
            if subscribers is None:
                continue
            subscribers.discard(key)
            if not subscribers:
                del self._index[read_key]

    def _births(self, fact: object) -> None:
        for descriptor in DESCRIPTORS:
            if not isinstance(fact, descriptor.born_by):
                continue
            for subject in descriptor.subjects_of(self, fact):
                key = (descriptor.name, subject)
                standing = self._bookmarks.get(key)
                if standing is not None:
                    fresh = tuple(
                        read_key
                        for read_key in descriptor.reads(self, subject)
                        if key not in self._index.get(read_key, ()))
                    if fresh:
                        standing.reads += fresh
                        self._register_reads(standing, fresh)
                    continue
                worker = WorkerBookmark(
                    plugin=descriptor.name, subject=subject,
                    reads=descriptor.reads(self, subject))
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
                if (fact_key[0] == KEY_POSE_AFFINE
                        and fact_key[1] == worker.subject):
                    self._rederive_reads(worker)
                worker.version += 1
                self._wakes += 1
                self._push_worker(worker)

    def _ingest(self, fact: object) -> tuple[bool, str]:
        changed, keys, kind = self._fold(fact)
        if changed:
            self._births(fact)
            self._touch(keys)
        return changed, kind

    def _fill(self, executor: ThreadPoolExecutor) -> None:
        while (len(self._inflight) < self._request.workers
               and self._frontier):
            cost, seq, plugin, stage, subject = heapq.heappop(self._frontier)
            worker = self._bookmarks.get((plugin, subject))
            if worker is None or seq != worker.seat_seq:
                self._stale_skips += 1
                continue
            worker.seat_seq = -1
            self._queued[plugin] -= 1
            if worker.retired:
                continue
            if worker.inflight:
                worker.pending = True
                continue
            descriptor = DESCRIPTOR_BY_NAME[plugin]
            if descriptor.retire(self, subject):
                self._retire_worker(worker)
                continue
            if worker.tried_version == worker.version:
                self._stale_skips += 1
                continue
            worker.tried_version = worker.version
            if not descriptor.eligible(self, subject):
                continue
            fresh_stage = descriptor.stage(self, subject)
            if fresh_stage is None:
                continue
            if (descriptor.cost(self, subject, fresh_stage, worker.attempts,
                                worker.last_cost)
                    > descriptor.cost(self, subject, stage, worker.attempts,
                                      worker.last_cost)):
                self._repush(plugin, subject)
                continue
            job = descriptor.prepare(self, subject, fresh_stage)
            if job is None:
                continue
            worker.attempts += 1
            self._note_attempt(worker.attempts)
            worker.inflight = True
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
        certs_grew = False
        for fact in result.facts:
            changed, kind = self._ingest(fact)
            if not changed:
                continue
            if kind == "certificate":
                n_certificates += 1
                certs_grew = True
            elif kind == "pose":
                n_poses += 1
                if isinstance(fact, data.Placement) \
                        and fact.route == place.ROUTE_WORD:
                    n_words += 1
        account[2] += n_certificates
        account[3] += n_poses
        account[4] += n_words
        for event in result.events:
            self._events.append(event)
        self._events.append(data.JobDone(
            plugin=plugin, subject=subject, cost=cost,
            cpu_s=float(result.cpu_s), n_certificates=n_certificates,
            n_poses=n_poses, n_words=n_words))
        worker = self._bookmarks[(plugin, subject)]
        worker.inflight = False
        if worker.pending:
            worker.pending = False
            self._push_worker(worker)
        return certs_grew

    def _subdivide(self, state: place_sched.WindowState) -> None:
        if state.subdivided:
            return
        state.subdivided = True
        wid = state.window.window_id
        frame = self._frames.get(wid[:3])
        if frame is None:
            return
        first = (self._plan_total.get((wid[0], wid[1]), 0)
                 + state.window.ordinal * 4)
        children = place.child_windows(frame, state.window, first)
        ids: list[WindowId] = []
        for child in children:
            changed, _kind = self._ingest(child)
            if changed:
                ids.append(child.window_id)
                child_state = self._place_stages.get(child.window_id)
                if child_state is not None:
                    child_state.parent = wid
        state.children = tuple(ids)

    def _afterlife(self, state: place_sched.WindowState) -> None:
        parent_wid = state.parent
        if parent_wid is None:
            return
        parent = self._place_stages.get(parent_wid)
        if parent is None or parent.afterlife_used or parent.placed:
            return
        kids = parent.children
        if not kids:
            return
        states = [self._place_stages[kid] for kid in kids]
        if any(child.placed for child in states):
            return
        settled = all(
            child.retired or self._bookmarks[("place", kid)].retired
            for kid, child in zip(kids, states))
        if not settled:
            return
        parent.afterlife_used = True
        parent.cold_armed = True
        parent.dormant_since = None
        parent.retired = False
        worker = self._bookmarks.get(("place", parent_wid))
        if worker is not None and worker.retired:
            worker.retired = False
            self._retired_count -= 1
            self._register_reads(worker, worker.reads)
        self._repush("place", parent_wid)

    def _place_repush(self,
                      state: place_sched.WindowState) -> None:
        wid = state.window.window_id
        if place_sched.ladder_stage(self, state, wid) is not None:
            self._repush("place", wid)
            return
        if not state.subdivided:
            self._subdivide(state)
            if state.children:
                return
        state.retired = True
        self._afterlife(state)


    def _close_consult(
            self, final: bool) -> format_close.CloseResult | None:
        started = time.thread_time()
        try:
            return self._close_decide(final)
        finally:
            self._consult_cpu_s += time.thread_time() - started

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
        _write_snapshot(self._request.run_dir / snapshot.NAME, self)
        _diag_products(self._request.run_dir, self._events)
        _diag_stop(self._diag_server)
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
