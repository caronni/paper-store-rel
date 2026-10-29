"""The operator's doors: the signals, the status rows and the products.

`engine.py` is the SCHEDULE — the frontier, the bookmarks, the fill/merge
loop.  This module is everything that serves the PERSON watching it, and
the two are separated because the engine crossed the 1000-line
split-here signal: a run's operator surface is a coherent seam of its
own, and none of it takes part in a scheduling decision.

What lives here:

* `OPERATOR_SIGNALS` and `OperatorDoors` — arming, the handler, and the
  loop-top service that turns a signal into work done at a consistent
  point.
* the PRODUCTS a run leaves behind: the fact snapshot (`_write_snapshot`,
  `snapshot_traced`), the diag run-dir dump (`_diag_products`), the live
  viewer (`_diag_serve` / `_diag_stop`) and the status rows the shell
  prints (`status_rows`).

`OperatorDoors.service(engine)` and `snapshot_traced(engine)` are handed
the running `_Engine` and read five things off it — `_request`
(`snapshot_every_s`, `run_dir`), `_certificates`, `_events`, `_trace_on`
and `_trace`.  They write nothing back but the trace brackets; the stop
is returned, never set on the engine.
"""
from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

from . import data, snapshot

#: The orderly stop's drain wakes this often to look for a second
#: signal (`OperatorDoors.abandon_wanted`).  A wait timeout, never read
#: as a time, never an ordering: completed jobs still merge in seat
#: order whatever wakes the wait.
DRAIN_POLL_S: float = 0.25

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


def snapshot_traced(engine: object) -> None:
    """`_write_snapshot` into the run dir, inside the trace's bracket.

    The two callers are the cadence/SIGUSR1 dump and `_finish`, and both
    want the write charged to the trace's own `snapshot` category rather
    than to the loop's residue.
    """
    engine._trace.enter("snapshot")
    try:
        _write_snapshot(engine._request.run_dir / snapshot.NAME, engine)
    finally:
        engine._trace.leave()


#: Diag may never change payload, status or exit code, so every diag
#: door swallows to one stderr line and returns.  The bare excepts here
#: and in `_diag_products` are that rule, not laziness.
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


class OperatorDoors:
    """The operator's three doors, all served at the loop top where the
    store is consistent (the merge thread is this thread): SIGUSR1 dumps
    the facts and prints the status rows; SIGINFO (ctrl-T on BSD/macOS)
    prints the rows; SIGINT/SIGTERM ask for an ORDERLY stop — the loop
    stops scheduling, DRAINS every job already in flight into the store,
    runs the final close consult, and `_finish` writes every product the
    run would have written at exhaustion (2026-10-03, S8: the stop used
    to break with the in-flight jobs unmerged, write the snapshot
    without them, and then block at exit on concurrent.futures' join
    for exactly the work it had just thrown away).  A second
    SIGINT/SIGTERM ABANDONS the drain (`abandon_wanted`): the loop
    leaves at once and the in-flight jobs' facts stay out of the
    snapshot.  The second SIGINT also restores the default handler, so
    a third one kills, as it always did.  The safety snapshot every
    `snapshot_every_s` seconds is the one licensed wall-clock site of
    this module: a cadence, never an ordering or a gate.
    `DRAIN_POLL_S` is not a clock read but a wait timeout: the drain's
    `wait` wakes on it to look for that second signal, which a signal
    handler cannot deliver into a blocked `wait` itself.
    """

    def __init__(self) -> None:
        self._dump_wanted = False
        self._status_wanted = False
        self._stop_wanted = False
        self._abandon_wanted = False
        self._stop_traced = False
        self._snapshot_due: float | None = None
        self._saved_handlers: dict[int, object] = {}

    @property
    def stop_wanted(self) -> bool:
        return self._stop_wanted

    @property
    def abandon_wanted(self) -> bool:
        return self._abandon_wanted

    def arm(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        for signum in OPERATOR_SIGNALS:
            self._saved_handlers[signum] = signal.signal(
                signum, self._on_operator_signal)

    def disarm(self) -> None:
        for signum, handler in self._saved_handlers.items():
            signal.signal(signum, handler)
        self._saved_handlers = {}

    def _on_operator_signal(self, signum: int, _frame: object) -> None:
        if signum == getattr(signal, "SIGUSR1", None):
            self._dump_wanted = True
            self._status_wanted = True
        elif signum == getattr(signal, "SIGINFO", None):
            self._status_wanted = True
        elif self._stop_wanted:
            if signum == signal.SIGINT:
                signal.signal(signal.SIGINT, signal.default_int_handler)
            self._abandon_wanted = True
            print(f"operator: signal {signum} again, abandoning the drain "
                  f"(a third ctrl-C kills)", file=sys.stderr, flush=True)
        else:
            self._stop_wanted = True
            print(f"operator: signal {signum}, stopping at the next "
                  f"consistent point: in-flight jobs drain into the "
                  f"snapshot (a second ctrl-C abandons them)",
                  file=sys.stderr, flush=True)

    def service(self, engine: object) -> bool:
        """Cadence, snapshot, rows, trace dump — then the stop answer."""
        every = engine._request.snapshot_every_s
        if every:
            now = time.monotonic()
            if self._snapshot_due is None:
                self._snapshot_due = now + float(every)
            elif now >= self._snapshot_due:
                self._dump_wanted = True
                self._snapshot_due = now + float(every)
        dumping = self._dump_wanted
        if self._dump_wanted:
            self._dump_wanted = False
            snapshot_traced(engine)
            print(f"snapshot: {len(engine._certificates)} certificates "
                  f"written to {engine._request.run_dir / snapshot.NAME}",
                  file=sys.stderr, flush=True)
        if self._status_wanted:
            self._status_wanted = False
            for row in status_rows(engine._events):
                print(row, file=sys.stderr, flush=True)
        # The stop dumps the trace ONCE: the drain comes back here at
        # every merge, and a dump per merge would be the instrument's
        # cost, not the run's.
        stop_dump = self._stop_wanted and not self._stop_traced
        if engine._trace_on and (dumping or engine._trace.due()
                                 or stop_dump):
            self._stop_traced = self._stop_traced or stop_dump
            engine._trace.enter("operator")
            try:
                engine._trace.dump(engine)
            finally:
                engine._trace.leave()
        return self._stop_wanted
