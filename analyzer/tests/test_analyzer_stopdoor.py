"""The stop door: ctrl-C ends a pass in ORDER (2026-09-07).

Before it, `analyzer ladder` wrote its ledger at the end only, so a
ctrl-C at hour three threw away every certificate the pass had minted.
These pin the door the production receiver already had: the keys in
flight finish, the unstarted ones stay open and un-attempted, the ledger
is written through the same code path as an ordinary end with
`stop_reason = interrupted` and the two counts, the close and the facts
are written beside it, and a second signal hands the handler back so a
third one kills.

Everything here is synthetic and in-process: the driver runs over the
stubbed `blind_key` of `test_analyzer_progress`, and the products run
over a real `FormatRow` with an empty run.  No run dir, no pixels.
"""

from __future__ import annotations

import json
import signal
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

from analyzer import cli
from analyzer import export_facts as export_mod
from analyzer import fixedpoint as fp
from analyzer import ledger as ledger_mod
from analyzer import score as score_mod
from analyzer import stopdoor as doors
from analyzer.types import (VERDICT_CERTIFIED, VERDICT_OPEN, AnalyzerConfig,
                            Ledger, LedgerRow)

from ._synthetic import R0850, row_of
from .test_analyzer_progress import _FakeRun


# ------------------------------------------------------- the door alone

def _armed_over(handler, body):
    """Run `body(door)` with the stop door armed over `handler`.

    The handler standing before the door is restored whatever happens —
    a test that left the default one installed would turn the next stray
    ctrl-C into a killed pytest.
    """
    saved = {signum: signal.getsignal(signum) for signum in doors.STOP_SIGNALS}
    for signum in doors.STOP_SIGNALS:
        signal.signal(signum, handler)
    try:
        with doors.stop_door(lambda line: body.setdefault("lines", []).append(
                line)) as door:
            body["door"] = door
            body["run"](door)
    finally:
        for signum, original in saved.items():
            signal.signal(signum, original)


@pytest.mark.parametrize("signum", doors.STOP_SIGNALS,
                         ids=lambda item: signal.Signals(item).name)
def test_the_first_signal_asks_for_the_stop_and_says_so(signum):
    """Either door, the same stop and the same one line (2026-09-20)."""
    state: dict = {"run": lambda door: signal.raise_signal(signum)}
    _armed_over(signal.SIG_DFL, state)
    assert state["door"].requested is True
    assert len(state["lines"]) == 1                 # one line per signal
    assert state["lines"][0].startswith("stop: signal ")
    assert "the keys in flight finish" in state["lines"][0]


def test_the_second_signal_hands_the_handler_back():
    """holo3's convention: the second restores, so the third kills."""

    def twice(door):
        assert signal.getsignal(signal.SIGINT) == door._on_signal
        signal.raise_signal(signal.SIGINT)
        assert signal.getsignal(signal.SIGINT) == door._on_signal
        signal.raise_signal(signal.SIGINT)          # handled by the door…
        # …which gave the pre-door handler back on its way out.  The next
        # SIGINT is the operating system's business, not the pass's.
        assert signal.getsignal(signal.SIGINT) == signal.SIG_DFL

    state: dict = {"run": twice}
    _armed_over(signal.SIG_DFL, state)
    assert len(state["lines"]) == 2
    assert "again" in state["lines"][1] and "kills" in state["lines"][1]


def test_a_handler_that_cannot_speak_still_stops_the_pass():
    """A handler may not raise into the pass it is stopping.

    Measured in this interpreter (2026-09-07): a signal that lands while
    the main thread is inside a stderr write re-enters the buffered
    writer and Python raises `RuntimeError: reentrant call`, out of
    whatever the pass was doing — which would take the ledger with it,
    the exact loss this door exists to prevent.  The serial path makes
    the window real: there the main thread is the worker AND the
    printer.  The request is set before the line, so the stop survives
    and only the line is lost.
    """
    def angry(_line: str) -> None:
        raise RuntimeError("reentrant call inside <_io.BufferedWriter …>")

    saved = {signum: signal.getsignal(signum) for signum in doors.STOP_SIGNALS}
    try:
        with doors.stop_door(angry) as door:
            signal.raise_signal(signal.SIGINT)      # must not raise HERE
            assert door.requested is True           # and it still stopped
            signal.raise_signal(signal.SIGINT)      # nor on the second
            assert signal.getsignal(signal.SIGINT) == saved[signal.SIGINT]
    finally:
        for signum, original in saved.items():
            signal.signal(signum, original)
    # the status door shares the guard, for the same reason
    doors.Progress(angry, n_targets=1)._on_signal(0, None)


def test_the_door_is_restored_when_the_pass_raises():
    saved = {signum: signal.getsignal(signum) for signum in doors.STOP_SIGNALS}
    with pytest.raises(RuntimeError):
        with doors.stop_door(lambda _line: None):
            raise RuntimeError("the pass died")
    for signum, original in saved.items():
        assert signal.getsignal(signum) == original


def test_no_sink_means_no_stop_door():
    """A library caller's pass is untouched — the status doors' rule."""
    saved = {signum: signal.getsignal(signum) for signum in doors.STOP_SIGNALS}
    with doors.stop_door(None) as door:
        for signum in doors.STOP_SIGNALS:
            assert signal.getsignal(signum) == saved[signum]
        assert door.requested is False
        assert door.begin() is True                 # never shuts


def test_begin_claims_a_key_until_the_door_shuts():
    door = doors.StopDoor(lambda _line: None)
    assert door.begin() is True and door.begin() is True
    door.requested = True
    assert door.begin() is False and door.begin() is False
    assert door.counts == {"keys_done": 2, "keys_skipped": 2}


def test_the_counts_survive_concurrent_workers():
    """The counters are locked: this interpreter is free-threaded."""
    door = doors.StopDoor(lambda _line: None)
    threads = [threading.Thread(target=lambda: [door.begin()
                                                for _ in range(200)])
               for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert door.counts == {"keys_done": 1600, "keys_skipped": 0}


# ---------------------------------------------------- the door in a pass

def _driver(monkeypatch, *, fire_after: int | None,
            certify: bool = True) -> list:
    """`blind_key` certifies every key and raises SIGINT on the Nth.

    `signal.raise_signal` is the whole test knob: the handler is the
    door's, armed by the pass itself, and it runs on the main thread
    between bytecodes — which in the serial path IS the worker thread,
    so the stop lands deterministically after the Nth key.
    """
    seen: list = []

    def fake_blind_key(_inputs, _certs, key, *_args, **_kwargs):
        seen.append(key)
        if fire_after is not None and len(seen) == fire_after:
            signal.raise_signal(signal.SIGINT)
        out: dict = {"seconds": 0.0, "n_lanes": 1}
        if certify:
            out["user_bits"] = np.zeros(4, np.uint8)
            out["certifying_rule"] = "sum"
            out["certifying_rung"] = "L0"
        return out

    monkeypatch.setattr(fp, "blind_key", fake_blind_key)
    monkeypatch.setattr(fp, "_retarget", lambda *_args: [])
    monkeypatch.setattr(fp.inputs_mod, "metadata_bit", lambda _run, _key: 0)
    return seen


def _config(workers: int = 1) -> AnalyzerConfig:
    return AnalyzerConfig(workers=workers, max_generations=4,
                          rungs=("L0",), rules=("sum",))


def _run_pass(monkeypatch, keys, *, workers: int = 1, fire_after=None,
              lines: list | None = None) -> Ledger:
    _driver(monkeypatch, fire_after=fire_after)
    saved = {signum: signal.getsignal(signum) for signum in doors.STOP_SIGNALS}
    try:
        ledger = fp.run(_FakeRun(), keys, _config(workers),
                        progress=(lines.append if lines is not None
                                  else lambda _line: None),
                        progress_every=1000)
    finally:
        for signum, original in saved.items():
            signal.signal(signum, original)
    for signum, original in saved.items():          # armed for the pass only
        assert signal.getsignal(signum) == original
    return ledger


def test_a_signal_mid_pass_ends_it_in_order(monkeypatch):
    keys = [(0, 0, index, "C") for index in range(6)]
    lines: list = []
    ledger = _run_pass(monkeypatch, keys, fire_after=3, lines=lines)
    assert ledger.header["stop_reason"] == fp.STOP_INTERRUPTED
    assert ledger.header["keys_done"] == 3
    assert ledger.header["keys_skipped"] == 3
    # the three that ran are rows, complete ones; the three the door beat
    # are not there at all — an unreached key is an OPEN key, and the
    # ledger says so by saying nothing about it
    assert [row.key for row in ledger.rows] == keys[:3]
    assert ledger.header["n_rows"] == 3
    assert ledger.header["n_certified"] == 3
    for row in ledger.rows:
        assert row.verdict == VERDICT_CERTIFIED
        assert row.rungs.get("user_bits") is not None
        assert row.diag["attempts"] == 1 and "seconds" in row.diag
    assert any(line.startswith("stop: signal ") for line in lines)


def test_a_signal_stops_the_cascade_between_generations(monkeypatch):
    """The door beats the cap AND the fixed point: neither ended this."""
    keys = [(0, 0, 0, "C")]
    follow = (0, 1, 0, "C")
    _driver(monkeypatch, fire_after=2)
    monkeypatch.setattr(
        fp, "_retarget",
        lambda _run, key, *_rest: [follow] if key == keys[0] else [])
    saved = {signum: signal.getsignal(signum) for signum in doors.STOP_SIGNALS}
    try:
        ledger = fp.run(_FakeRun(), keys, _config(), progress=lambda _l: None)
    finally:
        for signum, original in saved.items():
            signal.signal(signum, original)
    assert ledger.header["stop_reason"] == fp.STOP_INTERRUPTED
    assert ledger.header["keys_done"] == 2       # generation 1 ran its key
    assert ledger.header["keys_skipped"] == 0
    assert [row.key for row in ledger.rows] == [keys[0], follow]


def test_the_keys_in_flight_finish_on_threads(monkeypatch):
    """Worker-count independence: the invariants hold whenever the
    handler lands, and a claimed key always produces its row.

    `_driver` stubs `_retarget` to nothing, so this pass is ONE
    generation over distinct keys and the two counts partition it.  That
    is a property of this pass, not of the counts — the cascade below
    says what they mean in general.
    """
    keys = [(0, 0, index, "C") for index in range(8)]
    ledger = _run_pass(monkeypatch, keys, workers=4, fire_after=1)
    header = ledger.header
    assert header["stop_reason"] == fp.STOP_INTERRUPTED
    assert header["keys_done"] + header["keys_skipped"] == len(keys)
    assert header["keys_done"] == len(ledger.rows) == header["n_rows"]
    for row in ledger.rows:
        assert row.verdict == VERDICT_CERTIFIED
        assert row.rungs.get("user_bits") is not None


def test_the_counts_are_attempts_not_distinct_keys(monkeypatch):
    """What `keys_done`/`keys_skipped` MEAN on a cascading pass.

    `begin` is called once per key per GENERATION, and the W3 cascade
    re-attacks a key whose neighbour has since certified.  A re-attack
    REPLACES that key's row, so the row count does not grow with it and
    `keys_done` runs ahead of `n_rows`.  Here A certifies and re-targets
    B, B stays open, and B is attacked twice: three attempts, two rows.
    """
    first, second = (0, 0, 0, "C"), (0, 0, 1, "C")
    seen: list = []

    def fake_blind_key(_inputs, _certs, key, *_args, **_kwargs):
        seen.append(key)
        if len(seen) == 3:                  # the RE-ATTACK of the second
            signal.raise_signal(signal.SIGINT)
        out: dict = {"seconds": 0.0, "n_lanes": 1}
        if key == first:                    # only the first certifies
            out["user_bits"] = np.zeros(4, np.uint8)
            out["certifying_rule"] = "sum"
            out["certifying_rung"] = "L0"
        return out

    monkeypatch.setattr(fp, "blind_key", fake_blind_key)
    monkeypatch.setattr(fp.inputs_mod, "metadata_bit", lambda _run, _key: 0)
    monkeypatch.setattr(
        fp, "_retarget",
        lambda _run, key, *_rest: [second] if key == first else [])
    saved = {signum: signal.getsignal(signum) for signum in doors.STOP_SIGNALS}
    try:
        ledger = fp.run(_FakeRun(), [first, second], _config(),
                        progress=lambda _line: None, progress_every=1000)
    finally:
        for signum, original in saved.items():
            signal.signal(signum, original)

    assert seen == [first, second, second]          # three attempts…
    assert ledger.header["keys_done"] == 3          # …and the count is of
    assert ledger.header["keys_skipped"] == 0       # attempts, not keys
    assert [row.key for row in ledger.rows] == [first, second]
    assert ledger.header["n_rows"] == 2             # the keys are HERE
    assert ledger.rows[1].diag["attempts"] == 2     # the replaced row


def test_a_normal_end_carries_no_stop_counts(monkeypatch):
    """The ledger of an un-interrupted pass is the one it always was."""
    keys = [(0, 0, index, "C") for index in range(3)]
    ledger = _run_pass(monkeypatch, keys, fire_after=None)
    assert ledger.header["stop_reason"] == fp.STOP_FIXED_POINT
    assert "keys_done" not in ledger.header
    assert "keys_skipped" not in ledger.header
    assert len(ledger.rows) == 3


def test_a_pass_without_a_sink_arms_no_stop_door(monkeypatch):
    armed: list = []
    real_arm = doors.StopDoor.arm
    monkeypatch.setattr(doors.StopDoor, "arm",
                        lambda self: armed.append(self) or real_arm(self))
    _driver(monkeypatch, fire_after=None)
    fp.run(_FakeRun(), [(0, 0, 0, "C")], _config())
    assert armed == []
    saved = {signum: signal.getsignal(signum) for signum in doors.STOP_SIGNALS}
    try:
        fp.run(_FakeRun(), [(0, 0, 0, "C")], _config(),
               progress=lambda _line: None)
    finally:
        for signum, original in saved.items():
            signal.signal(signum, original)
    assert len(armed) == 1                       # …and a sink arms exactly one


# ------------------------------------------------ what the stop then owes

REF = R0850


@dataclass
class _Run:
    """Just what the close and the export read off a run."""

    row: object
    run_dir: Path
    format_ref: str = REF
    certificates: dict = field(default_factory=dict)
    rank_report: object = None
    tiles_yx: tuple = (4, 4)


def _empty_run_dir(tmp_path: Path) -> Path:
    from holo.receiver import snapshot

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    snapshot.write(run_dir / snapshot.NAME, ())
    return run_dir


def _open_row() -> LedgerRow:
    return LedgerRow(page=0, ty=1, tx=2, stream_id="C", esi=102, covered=True,
                     certified_by_production=False, source=None, band="live",
                     band_any="live", neighbours_certified=3,
                     siblings_certified=("C",), known_cells_in_halo=1200,
                     n_discriminating_labels=13, production_attempts={},
                     metadata_known=True)


def _interrupted_ledger(out: Path, name: str = "ledger") -> Path:
    path = out / f"{name}.jsonl"
    ledger_mod.write_rows(path, [_open_row()],
                          {"format_ref": REF, "run_dir": "run",
                           "stop_reason": fp.STOP_INTERRUPTED,
                           "keys_done": 4, "keys_skipped": 11})
    return path


def test_the_products_land_beside_an_interrupted_ledger(tmp_path):
    run_dir = _empty_run_dir(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    ledger_path = _interrupted_ledger(out)
    lines: list = []
    close_row = doors.interrupt_products(
        _Run(row=row_of(REF), run_dir=run_dir), {}, out,
        ledger_path=ledger_path, emit=lines.append)
    # the close is a RECORDED OUTCOME, not an exception: this pass has no
    # certificates, so the volume is short of its metadata, and that is
    # exactly what close.json says
    assert close_row is not None and close_row["verified"] is False
    written = json.loads((out / "close.json").read_text("utf-8"))
    assert written["status"] == close_row["status"]
    assert (out / "facts.npz").exists()
    assert (out / "facts.npz.manifest.json").exists()
    assert [line.split(" ")[1] for line in lines] == ["close", "facts"]


def test_a_failing_close_does_not_cost_the_facts(tmp_path):
    """Each step prints its own outcome; neither can take the other."""
    run_dir = _empty_run_dir(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    ledger_path = _interrupted_ledger(out)
    lines: list = []
    close_row = doors.interrupt_products(
        _Run(row=None, run_dir=run_dir), {}, out,
        ledger_path=ledger_path, emit=lines.append)
    assert close_row is None
    assert not (out / "close.json").exists()
    assert any("the close FAILED" in line for line in lines)
    assert (out / "facts.npz").exists()


def test_an_absent_snapshot_is_a_refusal_the_close_survives(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    ledger_path = _interrupted_ledger(out)
    lines: list = []
    close_row = doors.interrupt_products(
        _Run(row=row_of(REF), run_dir=tmp_path / "absent"), {}, out,
        ledger_path=ledger_path, emit=lines.append)
    assert close_row is not None and (out / "close.json").exists()
    assert not (out / "facts.npz").exists()
    assert any("export-facts REFUSED" in line for line in lines)


# ------------------------------------------- the readers of that ledger

def test_the_readers_tolerate_the_interrupted_header(tmp_path):
    """Point 3 of the ask: one new header field, no reader changes.

    `close --ledger`, `export-facts` and `score` all read ROWS; the
    header they consult by name, and none of them validates
    `stop_reason`.  This is the pin, not the hope.
    """
    path = _interrupted_ledger(tmp_path)
    header, rows = ledger_mod.read_rows(path)
    assert header["stop_reason"] == fp.STOP_INTERRUPTED
    assert header["keys_done"] == 4 and header["keys_skipped"] == 11
    assert len(rows) == 1 and rows[0]["verdict"] == VERDICT_OPEN

    exported_header, exported_rows = export_mod.read_ledger(path)
    assert exported_header["stop_reason"] == fp.STOP_INTERRUPTED
    collected = export_mod.collect({}, [(str(path), exported_header,
                                         exported_rows)])
    assert collected.keys == ()                 # an open row adds nothing

    headers = score_mod.read_headers([path])
    assert headers[0][1]["stop_reason"] == fp.STOP_INTERRUPTED
    assert score_mod.format_ref_of(headers, None) == REF


def test_the_summary_says_the_pass_was_stopped(tmp_path):
    """`ledger.md` is what gets pasted into an experiment log, so it may
    not read like an exhausted pass (2026-09-07).

    One conditional row, and only for the interrupt: an ordinary summary
    is the one it always was, which the second half pins.
    """
    header, rows = ledger_mod.read_rows(_interrupted_ledger(tmp_path))
    stopped = ledger_mod.summarize(rows, header=header)
    assert "| stopped | interrupted — 4 attempt(s) done, 11 skipped |" \
        in stopped

    ordinary = dict(header)
    ordinary["stop_reason"] = fp.STOP_FIXED_POINT
    ordinary.pop("keys_done"), ordinary.pop("keys_skipped")
    assert "stopped" not in ledger_mod.summarize(rows, header=ordinary)


# --------------------------------------------------- the ladder's wiring

def _canned(monkeypatch, tmp_path, stop_reason: str):
    """`analyzer ladder` with the pass itself stubbed out.

    What is under test is the TAIL of `cli._pass`: which products an
    interrupted ledger gets that an ordinary one does not.
    """
    run_dir = _empty_run_dir(tmp_path)
    out = tmp_path / "out"
    run = _Run(row=row_of(REF), run_dir=run_dir)

    def fake_run(*_args, **_kwargs):
        ledger = Ledger(exposure=fp.shared_exposure())
        ledger.rows = [_open_row()]
        ledger.header = {"format_ref": REF, "run_dir": str(run_dir),
                         "stop_reason": stop_reason, "n_rows": 1,
                         "generations_run": 1, "seconds": 0.5}
        if stop_reason == fp.STOP_INTERRUPTED:
            ledger.header.update({"keys_done": 1, "keys_skipped": 2})
        return ledger

    monkeypatch.setattr(cli, "_load", lambda _args: run)
    monkeypatch.setattr(cli, "_census", lambda _run, _args: [])
    monkeypatch.setattr(cli, "_targets", lambda _rows, _spec: [_open_row()])
    monkeypatch.setattr(fp, "run", fake_run)
    args = cli.build_parser().parse_args(
        ["ladder", "--run-dir", str(run_dir), "--out", str(out), "--no-maps"])
    assert cli._pass(args) == 0
    return out


def test_an_interrupted_ladder_writes_the_close_and_the_facts(
        monkeypatch, tmp_path, capsys):
    out = _canned(monkeypatch, tmp_path, fp.STOP_INTERRUPTED)
    assert (out / "ledger.jsonl").exists() and (out / "ledger.md").exists()
    assert (out / "close.json").exists()
    assert (out / "facts.npz").exists()
    err = capsys.readouterr().err
    assert "stop: close" in err and "stop: facts" in err


def test_an_ordinary_ladder_is_what_it_always_was(
        monkeypatch, tmp_path, capsys):
    """At a normal end nothing changes: the close as always, no facts."""
    out = _canned(monkeypatch, tmp_path, fp.STOP_FIXED_POINT)
    assert (out / "close.json").exists()
    assert not (out / "facts.npz").exists()
    assert "stop: " not in capsys.readouterr().err
