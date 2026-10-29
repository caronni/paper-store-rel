"""The operator's doors on a running pass (`fixedpoint.run`), and what
it tells the operator while it runs.

Two kinds of door, one contract each, the products the second owes —
and, since the memory wave of 2026-09-13, the CHECKPOINT: a small JSON
file rewritten at the first key or generation boundary after each half
hour beside the ledger so that a pass killed
at hour three can be READ afterwards.  The progress lines carry the
same counters, memory included, because a pass that says nothing cannot
be explained after the fact either.

THE STATUS DOORS
 (SIGUSR1, and SIGINFO/ctrl-T where the platform has it)
answer with one line of counters and leave the pass alone.  They arrived
2026-09-04, after the first machine 4 run of `ladder --profile everything` sat
silent for its whole length.

THE STOP DOOR (SIGINT/ctrl-C, SIGTERM) asks for an ORDERLY STOP, the way
the production receiver's does (`holo.receiver.engine`
`_on_operator_signal`): a key no worker has started yet is SKIPPED, the
keys in flight finish, their rows fold exactly as they would have, the
generation loop breaks, and the ledger is written through the same code
path as an ordinary end — `stop_reason = "interrupted"` plus the two
counts `keys_done`/`keys_skipped`.  A skipped key is not a half-attempt:
it produces NO row, so the ledger says `open` about it by saying
nothing, which is what an unreached key is.  A second signal restores
the handler that was there before the door, so a third one kills.

Before this door a pass wrote its ledger at the end ONLY: ctrl-C at hour
three of a `--fixed-point` pass threw away every certificate it had
minted (the limit README §7 carried, owed since 2026-09-04).

THE PRODUCTS.  `interrupt_products` writes what the operator's loop
(ladder -> close -> export-facts -> holo3 resume) would have written at
exhaustion: the close (`close.json`, and `payload.bin` when the volume
verifies) and the fact snapshot a holo3 `--resume` reads (`facts.npz`
and its manifest).  Each step is GUARDED and prints its outcome: a
refusal — short of K, an absent snapshot — is a recorded outcome, and a
failure in one never costs the other.

The handlers run on the main thread between bytecodes and take NO lock,
for the reason `Progress` gives: in the serial path the main thread is
the worker thread, so a locking handler could deadlock the pass it is
stopping.  A handler here sets one bool and prints one line; the
counters it does not touch are locked, because the workers share them
and this interpreter is free-threaded.
"""

from __future__ import annotations

import json
import os
import resource
import signal
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .types import Exposure, Key


#: A progress tick every this many finished keys of a generation.  It
#: was 10 until 2026-09-13; a real pass is thousands of keys long and
#: the ticks are what the operator scrolls through to find the one line
#: that matters.
PROGRESS_EVERY = 50

#: How long a pass waits before its next checkpoint, in minutes — the
#: file is then written at the first key or generation boundary AFTER
#: that, because `Checkpointer.maybe` is called where work retires and
#: nothing here holds a timer thread.  Half an hour is the number the
#: wave asked for: short enough that a kill loses a readable amount of
#: history, long enough that the file is free.
CHECKPOINT_MINUTES = 30.0

#: The checkpoint's name, beside the ledger it describes.
CHECKPOINT_NAME = "checkpoint.json"


# --------------------------------------------------------- the memory line

def peak_rss_bytes() -> int:
    """The high-water RSS of this process, in bytes.

    `resource.getrusage` is the one door that needs nothing installed
    (psutil is not in this venv) and it reports `ru_maxrss` in BYTES on
    macOS and in KIBIBYTES on Linux — the one platform difference this
    file has to know.
    """
    usage = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return usage if sys.platform == "darwin" else usage * 1024


def current_rss_bytes() -> int | None:
    """RSS right now, where it is FREE — otherwise None.

    Linux publishes it in `/proc/self/statm`; macOS does not publish it
    anywhere a pure-Python reader can reach without a `mach` call or a
    subprocess, and a pass may not shell out per progress tick.  Peak is
    what a kill needs anyway: it is the number that says how close the
    pass came to the machine's 64 GB.
    """
    try:
        with open("/proc/self/statm", "r", encoding="ascii") as stream:
            pages = int(stream.read().split()[1])
    except (OSError, IndexError, ValueError):
        return None
    return pages * os.sysconf("SC_PAGE_SIZE")


def _gb(value: float) -> str:
    return f"{value / (1 << 30):.2f} GB"


def memory_line() -> str:
    """`peak RSS 12.34 GB` (plus `now ...` where it is free)."""
    now = current_rss_bytes()
    return (f"peak RSS {_gb(peak_rss_bytes())}"
            + ("" if now is None else f" / now {_gb(now)}"))


def memory_report() -> dict:
    """The same two numbers, for the checkpoint."""
    now = current_rss_bytes()
    return {"peak_rss_bytes": peak_rss_bytes(),
            "current_rss_bytes": now,
            "line": memory_line()}


#: The status doors: SIGUSR1, and SIGINFO (ctrl-T) where the platform
#: has it.  They REPORT and nothing else; the two that end a pass are
#: `STOP_SIGNALS` below, and both halves stay armed for the drain.
STATUS_SIGNALS: tuple[int, ...] = tuple(
    getattr(signal, name) for name in ("SIGUSR1", "SIGINFO")
    if hasattr(signal, name))


@contextmanager
def _status_doors(watch: "Progress | None") -> Iterator[None]:
    """Arm the status signals for exactly the pass, and restore them."""
    if watch is not None:
        watch.arm()
    try:
        yield
    finally:
        if watch is not None:
            watch.disarm()


def _hms(seconds: float) -> str:
    whole = int(max(0.0, seconds))
    return f"{whole // 3600}:{whole // 60 % 60:02d}:{whole % 60:02d}"


def _say(emit: Callable[[str], None], line: str) -> None:
    """Emit an operator line FROM A SIGNAL HANDLER, which may not raise.

    A handler runs between bytecodes on the main thread, so a signal
    that lands while that same thread is inside a stderr write re-enters
    the buffered writer and Python raises `RuntimeError: reentrant call`
    — out of whatever the pass was doing, taking the ledger with it,
    which is the exact loss the stop door exists to prevent (measured in
    this interpreter, 2026-09-07).  The window is one tick's width but
    real: in the serial path the main thread is the worker AND the
    printer.  Both doors set their state BEFORE they speak, so the only
    thing a swallowed error costs is the line.
    """
    try:
        emit(line)
    except Exception:
        pass                    # a handler may not raise into its pass


class Progress:
    """The operator's window on a pass (2026-09-04, after the first machine 4 run
    sat silent for its whole length).

    One line per generation start and end, a tick every `every` finished
    keys with the rate over that window, the mints so far, a
    remaining-time estimate and the peak RSS, and a status line on
    demand from SIGUSR1 or SIGINFO.  Lines go to `emit` (the CLI prints
    them to stderr); a run without a sink is byte-identical, and nothing
    here reaches the ledger.

    The counters are written by the worker threads under `_lock` and read
    by the signal handler WITHOUT it: the handler runs on the main thread,
    which in the serial path is the thread holding the lock inside
    `key_done`, so a locking handler could deadlock the pass it reports
    on.  A status line is therefore a snapshot of plain integers, which
    is all it needs to be.
    """

    def __init__(self, emit: Callable[[str], None], *, n_targets: int,
                 exposure: Exposure | None = None,
                 every: int = PROGRESS_EVERY) -> None:
        self._emit = emit
        self._every = max(1, int(every))
        self._exposure = exposure
        self._lock = threading.Lock()
        self._started = time.perf_counter()
        self._generation_started = self._started
        #: the TICK WINDOW: the rate an operator wants is the one the
        #: last N keys ran at, not the generation's mean — a pass that
        #: slows down says so a window later, not an hour later.
        self._window_started = self._started
        self._window_done = 0
        self._saved: dict[int, Any] = {}
        self.n_targets = int(n_targets)
        self.generation = 0
        self.pending = 0
        self.done = 0
        self.fresh = 0
        self.certified = 0

    # ---------------------------------------------------- the doors
    def arm(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        for signum in STATUS_SIGNALS:
            self._saved[signum] = signal.signal(signum, self._on_signal)

    def disarm(self) -> None:
        for signum, handler in self._saved.items():
            signal.signal(signum, handler)
        self._saved = {}

    def _on_signal(self, _signum: int, _frame: object) -> None:
        _say(self._emit, self.status())

    def status(self) -> str:
        exposure = ("" if self._exposure is None else
                    f", exposure {int(self._exposure.distinct):,} distinct")
        return (f"status: generation {self.generation}, "
                f"{self.done}/{self.pending} done, certificates "
                f"{self.certified} (+{self.fresh} this generation)"
                f"{exposure}, elapsed "
                f"{_hms(time.perf_counter() - self._started)}, "
                f"{memory_line()}")

    # ------------------------------------------------ the pass hooks
    def generation_started(self, generation: int, pending: int,
                           re_attacks: int) -> None:
        with self._lock:
            self.generation = int(generation)
            self.pending = int(pending)
            self.done = 0
            self.fresh = 0
            self._generation_started = time.perf_counter()
            self._window_started = self._generation_started
            self._window_done = 0
        self._emit(f"generation {generation}: {pending} pending "
                   f"({re_attacks} re-attacks), certificates so far "
                   f"{self.certified}, elapsed "
                   f"{_hms(time.perf_counter() - self._started)}, "
                   f"{memory_line()}")

    def key_done(self, key: Key, certified: bool) -> None:
        with self._lock:
            self.done += 1
            if certified:
                self.fresh += 1
                self.certified += 1
            done, fresh, pending = self.done, self.fresh, self.pending
            now = time.perf_counter()
            since = now - self._generation_started
            window = now - self._window_started
            in_window = done - self._window_done
            if not (done % self._every) or done == pending:
                self._window_started = now
                self._window_done = done
        if done % self._every and done != pending:
            return
        rate = done / since if since > 0 else 0.0
        remaining = (pending - done) / rate if rate > 0 else 0.0
        per_key = window / in_window if in_window > 0 else 0.0
        self._emit(f"  generation {self.generation}: {done}/{pending} done, "
                   f"+{fresh} certified ({self.certified} mints), "
                   f"{per_key:.1f} s/key, "
                   f"elapsed {_hms(time.perf_counter() - self._started)}, "
                   f"remaining ~{_hms(remaining)}, {memory_line()} "
                   f"(last {key})")

    def generation_finished(self, generation: int, fresh: int,
                            refused: int) -> None:
        self._emit(f"generation {generation} done: +{fresh} certificates "
                   f"(total {self.certified}), {refused} refused, "
                   f"{_hms(time.perf_counter() - self._generation_started)}, "
                   f"{memory_line()}")

    def finished(self, generations_run: int) -> None:
        self._emit(f"pass done: {self.certified} certificates over "
                   f"{generations_run} generation(s) in "
                   f"{_hms(time.perf_counter() - self._started)}; "
                   f"writing the ledger")


# ------------------------------------------------------- the stop door

#: The stop doors.  `SIGINFO` and `SIGUSR1` above report; these two ask
#: the pass to END — holo3's `OPERATOR_SIGNALS` split in half, with the
#: same second-signal convention (a second restores what was there
#: before, so a third kills).
STOP_SIGNALS: tuple[int, ...] = tuple(
    getattr(signal, name) for name in ("SIGINT", "SIGTERM")
    if hasattr(signal, name))

#: The ledger header's `stop_reason` for a pass the operator stopped.
#: It beats both of `fixedpoint`'s: neither the cap nor the fixed point
#: was reached, so neither may claim the pass.
STOP_INTERRUPTED = "interrupted"


class StopDoor:
    """The orderly stop: one bool the workers read, two counts they keep.

    `begin` is the door itself.  A worker calls it before it touches a
    key: `False` means the operator has asked to stop and the key is
    left OPEN and uncounted as work — no evidence is gathered, no rung
    runs, no row is folded.  `True` means the key is claimed, and a
    claimed key always finishes, so a row is never half-written.

    The two counts are ATTEMPTS, not distinct keys — see `counts`.

    `requested` is set by the signal handler WITHOUT the lock and read
    by every worker: one bool, one writer, and the pass may not deadlock
    on the door that stops it.  The counts are locked because the
    workers all write them under a free-threaded interpreter.
    """

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._lock = threading.Lock()
        self._saved: dict[int, Any] = {}
        self.requested = False
        self.keys_done = 0
        self.keys_skipped = 0

    # ---------------------------------------------------- the door
    def arm(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return
        for signum in STOP_SIGNALS:
            self._saved[signum] = signal.signal(signum, self._on_signal)

    def disarm(self) -> None:
        for signum, handler in self._saved.items():
            signal.signal(signum, handler)
        self._saved = {}

    def _on_signal(self, signum: int, _frame: object) -> None:
        if self.requested:            # the second one: hand the signal
            self.disarm()             # back and let the next one kill
            _say(self._emit,
                 f"stop: signal {signum} again — the handler that was here "
                 f"before is back; the next one kills the pass and its "
                 f"ledger with it")
            return
        self.requested = True         # the request first: `_say` may not
        _say(self._emit,              # raise, but it may still lose a line
             f"stop: signal {signum} — the keys in flight finish, the rest "
             f"stay open, and the ledger, the close and the facts are "
             f"written; again to restore the default handler")

    # -------------------------------------------------- the workers
    def begin(self) -> bool:
        """Claim a key for a worker; `False` = the door is shut."""
        with self._lock:
            if self.requested:
                self.keys_skipped += 1
                return False
            self.keys_done += 1
            return True

    @property
    def counts(self) -> dict[str, int]:
        """The two header counts of an interrupted pass: key ATTEMPTS
        claimed, and attempts the shut door turned away.

        Attempts, not distinct keys.  `begin` is called once per key per
        GENERATION, and the W3 cascade re-attacks a key whose neighbour
        has since certified — a re-attack REPLACES that key's row rather
        than adding one.  So on any cascading pass (`--fixed-point`, the
        case this door exists for) `keys_done` runs ahead of `n_rows`,
        and the two counts do not sum to the target count.  Which is the
        honest reading: they measure the WORK the pass got through and
        the work the stop turned away, and `n_rows` beside them in the
        same header measures the keys.
        """
        with self._lock:
            return {"keys_done": int(self.keys_done),
                    "keys_skipped": int(self.keys_skipped)}


@contextmanager
def stop_door(emit: Callable[[str], None] | None) -> Iterator[StopDoor]:
    """Arm the stop signals for exactly the pass, and restore them.

    `emit` None arms NOTHING and yields a door that is never asked to
    shut — the rule the status doors already follow, so a library
    caller's pass (the controls, the tests) is untouched and the driver
    still has one shape to write against.
    """
    door = StopDoor(emit if emit is not None else lambda _line: None)
    if emit is not None:
        door.arm()
    try:
        yield door
    finally:
        door.disarm()


# --------------------------------------- what an interrupted pass owes

def interrupt_products(inputs: Any, certs: Mapping[Key, Any],
                       out_dir: Path | str, *, ledger_path: Path | str,
                       emit: Callable[[str], None]) -> dict | None:
    """The close and the facts, written beside an interrupted ledger.

    The operator's loop is ladder -> close -> export-facts -> holo3
    `--resume`, and an interrupted pass runs the first two of those for
    them: `close.json` (plus `payload.bin` when the volume verifies)
    from the certificates the pass just wrote, and `<out>/facts.npz`
    (plus its manifest) from the run's own snapshot and this ledger.

    Both are GUARDED.  A close that is short of K is a status, not an
    exception; an export whose snapshot is absent REFUSES; and neither
    outcome may cost the other, so each is caught, printed and moved
    past.  Returns the close row, or None when the close itself failed.
    """
    from holo.receiver import snapshot

    from . import close as close_mod
    from . import export_facts as export_mod
    from . import ledger as ledger_mod

    out_dir = Path(out_dir)
    close_row: dict | None = None
    try:
        close_row = close_mod.close(inputs, certs, out_dir=out_dir)
        (out_dir / "close.json").write_text(
            json.dumps(ledger_mod.jsonable(close_row), indent=2), "utf-8")
        emit(f"stop: close {close_row['status']} over "
             f"{close_row['n_certificates']} certificates "
             f"({close_row['n_from_analyzer']} from this pass); payload "
             f"{close_row['payload_path'] or 'not written'}")
    except Exception as error:              # a product, never the pass
        emit(f"stop: the close FAILED ({type(error).__name__}: {error})")
    facts = out_dir / snapshot.NAME
    try:
        manifest = export_mod.export(
            Path(inputs.run_dir) / snapshot.NAME, [Path(ledger_path)], facts)
        counts = manifest["counts"]
        emit(f"stop: facts {facts} — {counts['snapshot_certificates']} + "
             f"{counts['added']} = {counts['total_after_export']} "
             f"certificates")
    except Exception as error:
        emit(f"stop: export-facts REFUSED ({type(error).__name__}: {error})")
    return close_row


# ------------------------------------------------ the periodic checkpoint

#: What an operator does with a killed pass — printed when a pass starts,
#: carried inside every checkpoint, and the reason there is no `--resume`.
#: The pass is NOT restarted: its certificates are folded into a new base
#: and the residue is attacked again, which is the loop the analyzer
#: already has (README §4) and which needs no new state to be trusted.
RECOVERY_RECIPE = (
    "recovery from a killed pass, in three commands: "
    "`export-facts --snapshot <run-dir>/facts.npz --ledger "
    "<out>/mints.jsonl --out <new>/facts.npz` folds the certificates it "
    "DID mint (the ledger's rows land a generation later, so the mint "
    "file is the one to hand it; a `read` pass spells it "
    "mints-read.jsonl); `union-base --run-dir <run-dir> --facts "
    "<new>/facts.npz --out <base>` builds the run dir over them; then "
    "the same pass again against `<base>`, which re-attacks only what "
    "is still open.  There is no --resume.")



class Checkpointer:
    """A small JSON file beside the ledger, rewritten at the first key
    or generation boundary after `minutes`.

    THAT IS THE CADENCE, and it is event-driven: `maybe` is called at
    the end of `work_one` on every worker and at the generation fold,
    so a pass retiring a key every 22 s writes within 22 s of the mark,
    and there is no timer thread to write one while the workers are all
    inside the same long call.  The gap that is real is the first fit —
    the key that needs the page field blocks about six minutes before
    any key retires (README §4) — and it is a late checkpoint, never a
    lost one: the previous file stands until this one lands.

    The 2026-09-10 pass was killed at 350 keys and 51 certificates after
    2 h 10 m, and nothing on disk said so — not what it had done, not
    what it had consulted, not how much memory it was holding when it
    died.  This is that file.  It is written to a temp name and renamed,
    so a kill during the write leaves the PREVIOUS checkpoint whole
    rather than a half one.

    `minutes` of 0 disables it entirely.  `clock` is injectable because
    the only honest test of a timer is one that controls it.

    Written from the worker threads (the fold of a generation can be
    hours away when the first one is still running), so the due check
    takes the lock; the state itself is gathered by the caller's
    `state` callable, which reads plain counters.
    """

    def __init__(self, path: Path | str, *,
                 minutes: float = CHECKPOINT_MINUTES,
                 emit: Callable[[str], None] | None = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.path = Path(path)
        self.minutes = float(minutes)
        self._emit = emit
        self._clock = clock
        self._lock = threading.Lock()
        self._last = clock()
        self.n_written = 0

    @property
    def enabled(self) -> bool:
        return self.minutes > 0

    def maybe(self, state: Callable[[], Mapping[str, Any]], *,
              reason: str = "timer") -> Path | None:
        """Write the checkpoint IF the interval has passed."""
        if not self.enabled:
            return None
        now = self._clock()
        if now - self._last < self.minutes * 60.0:
            return None
        with self._lock:                      # one writer per interval
            if now - self._last < self.minutes * 60.0:
                return None
            self._last = now
        try:
            gathered = state()
        except Exception as error:          # a product, never the pass
            if self._emit is not None:
                _say(self._emit, f"checkpoint state FAILED "
                                 f"({type(error).__name__}: {error})")
            return None
        return self.write(gathered, reason=reason)


    def write(self, state: Mapping[str, Any], *, reason: str) -> Path | None:
        """Write it now, whatever the timer says (the orderly stop does).

        GUARDED like every other product of a running pass: a checkpoint
        that cannot be written is a line on stderr, never the end of a
        multi-hour pass.
        """
        if not self.enabled:
            return None
        record = {"reason": str(reason),
                  "written_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                  "memory": memory_report(),
                  "recovery": RECOVERY_RECIPE,
                  **dict(state)}
        temp = self.path.with_name(self.path.name + ".tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp.write_text(json.dumps(record, indent=2, default=str),
                            "utf-8")
            temp.replace(self.path)
        except Exception as error:          # a product, never the pass
            if self._emit is not None:
                _say(self._emit, f"checkpoint FAILED "
                                 f"({type(error).__name__}: {error})")
            return None
        self.n_written += 1
        if self._emit is not None:
            _say(self._emit, f"checkpoint ({reason}): {self.path}")
        return self.path
