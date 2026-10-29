"""The operator's window on a pass (`fixedpoint.Progress`, 2026-09-04).

The first machine 4 run of `ladder --profile everything` printed its header and
then nothing for the whole pass.  These pin what the window shows — a
line per generation start and end, a tick every N finished keys, a status
line on SIGUSR1/SIGINFO — that the doors are armed for exactly the pass
and restored after, and that a run without a sink is untouched.
"""

from __future__ import annotations

import os
import re
import signal
import time
from dataclasses import dataclass, field

import numpy as np

from analyzer import fixedpoint as fp
from analyzer.types import AnalyzerConfig


# ------------------------------------------------------ the reporter

def test_the_lines_carry_generation_progress_and_certificates():
    seen: list[str] = []
    watch = fp.Progress(seen.append, n_targets=5, every=2)
    watch.generation_started(0, 5, 0)
    assert seen[-1].startswith("generation 0: 5 pending (0 re-attacks)")
    watch.key_done((0, 1, 1, "C"), True)
    assert len(seen) == 1                         # no tick at 1 of 2
    watch.key_done((0, 1, 2, "C"), False)
    assert len(seen) == 2
    assert "generation 0: 2/5 done, +1 certified" in seen[-1]
    assert "remaining ~" in seen[-1] and "(last (0, 1, 2, 'C'))" in seen[-1]
    for key in ((0, 1, 3, "C"), (0, 1, 4, "C")):
        watch.key_done(key, True)
    watch.key_done((0, 1, 5, "C"), False)           # the last one always ticks
    assert seen[-1].startswith("  generation 0: 5/5 done, +3 certified")
    watch.generation_finished(0, 3, 1)
    assert seen[-1].startswith("generation 0 done: +3 certificates (total 3), "
                               "1 refused")
    watch.generation_started(1, 4, 4)
    assert "4 pending (4 re-attacks), certificates so far 3" in seen[-1]
    watch.finished(2)
    assert seen[-1].startswith("pass done: 3 certificates over 2 generation(s)")


def test_the_status_line_reads_the_counters_and_the_exposure():
    seen: list[str] = []
    exposure = fp.shared_exposure()
    watch = fp.Progress(seen.append, n_targets=3, exposure=exposure)
    watch.generation_started(0, 3, 0)
    watch.key_done((0, 0, 0, "Y"), True)
    line = watch.status()
    assert line.startswith("status: generation 0, 1/3 done, certificates 1 "
                           "(+1 this generation), exposure 0 distinct, "
                           "elapsed ")


def test_hms_is_hours_minutes_seconds():
    assert fp._hms(0) == "0:00:00"
    assert fp._hms(59.9) == "0:00:59"
    assert fp._hms(3600 + 65) == "1:01:05"
    assert fp._hms(-3) == "0:00:00"


# ---------------------------------------------------------- the doors

def _deliver(signum: int, seen: list, before: int) -> None:
    os.kill(os.getpid(), signum)
    deadline = time.perf_counter() + 5.0
    while len(seen) == before and time.perf_counter() < deadline:
        time.sleep(0.01)                  # the handler runs between bytecodes


def test_sigusr1_prints_a_status_line_while_armed_and_not_after():
    seen: list[str] = []
    originals = {signum: signal.getsignal(signum)
                 for signum in fp.STATUS_SIGNALS}
    watch = fp.Progress(seen.append, n_targets=1)
    with fp._status_doors(watch):
        for signum in fp.STATUS_SIGNALS:
            assert signal.getsignal(signum) == watch._on_signal
        _deliver(signal.SIGUSR1, seen, 0)
    assert len(seen) == 1 and seen[0].startswith("status: generation 0")
    for signum in fp.STATUS_SIGNALS:
        assert signal.getsignal(signum) == originals[signum]


def test_the_doors_are_restored_when_the_pass_raises():
    originals = {signum: signal.getsignal(signum)
                 for signum in fp.STATUS_SIGNALS}
    watch = fp.Progress(lambda _line: None, n_targets=1)
    try:
        with fp._status_doors(watch):
            raise RuntimeError("the pass died")
    except RuntimeError:
        pass
    for signum in fp.STATUS_SIGNALS:
        assert signal.getsignal(signum) == originals[signum]


def test_no_sink_means_no_doors():
    originals = {signum: signal.getsignal(signum)
                 for signum in fp.STATUS_SIGNALS}
    with fp._status_doors(None):
        for signum in fp.STATUS_SIGNALS:
            assert signal.getsignal(signum) == originals[signum]


# ------------------------------------------- the hooks in the driver

@dataclass
class _Capture:
    capture_id: str = "cap-a"
    dpi: int = 2400
    shape_px: tuple = (10, 10)


@dataclass
class _FakeRun:
    """Just what `fixedpoint.run` reads off the inputs when every decision
    is stubbed: the header fields and the working certificates."""

    certificates: dict = field(default_factory=dict)
    format_ref: str = "fake"
    run_dir: str = "fake-run"
    captures: tuple = (_Capture(),)
    provenance: dict = field(default_factory=dict)
    tiles_yx: tuple = (4, 4)


def _stubbed_driver(monkeypatch, *, certify: set, follow_ups: dict):
    """`blind_key` certifies the keys in `certify`; `_retarget` hands each
    fresh certificate its `follow_ups` (once); the metadata bit is 0."""

    def fake_blind_key(_inputs, _certs, key, _config, _exposure, **_kw):
        out: dict = {"seconds": 0.0, "n_lanes": 1}
        if key in certify:
            out["user_bits"] = np.zeros(4, np.uint8)
            out["certifying_rule"] = "sum"
            out["certifying_rung"] = "L0"
        return out

    def fake_retarget(_inputs, key, _certified, _seen, _working):
        return list(follow_ups.pop(key, ()))

    monkeypatch.setattr(fp, "blind_key", fake_blind_key)
    monkeypatch.setattr(fp, "_retarget", fake_retarget)
    monkeypatch.setattr(fp.inputs_mod, "metadata_bit",
                        lambda _inputs, _key: 0)


def test_the_driver_reports_each_generation_through_the_sink(monkeypatch):
    first = [(0, 0, 0, "C"), (0, 0, 1, "C"), (0, 0, 2, "C")]
    second = (0, 1, 0, "C")
    _stubbed_driver(monkeypatch, certify={first[0], second},
                    follow_ups={first[0]: (second,)})
    seen: list[str] = []
    ledger = fp.run(_FakeRun(), first, AnalyzerConfig(
        workers=2, max_generations=4, rungs=("L0",), rules=("sum",)),
        progress=seen.append, progress_every=1)
    assert ledger.header["n_certified"] == 2
    assert ledger.header["generations_run"] == 2
    heads = [line.split(",")[0] for line in seen if not line.startswith("  ")]
    #: the last head carries the pass's WALL TIME, which is not a
    #: property of the driver: it read `0:00:00` on a fast machine and
    #: `0:00:01` on a slow one, so the lane was red at random (review
    #: 2026-09-06).  Pin the sentence and let the clock say what it says.
    elapsed = heads[-1].partition(" in ")[2]
    assert re.fullmatch(r"\d+:\d\d:\d\d; writing the ledger", elapsed), \
        heads[-1]
    assert heads[:-1] + [heads[-1].partition(" in ")[0]] == [
        "generation 0: 3 pending (0 re-attacks)",
        "generation 0 done: +1 certificates (total 1)",
        "generation 1: 1 pending (0 re-attacks)",
        "generation 1 done: +1 certificates (total 2)",
        "pass done: 2 certificates over 2 generation(s)",
    ]
    ticks = [line for line in seen if line.startswith("  ")]
    assert len(ticks) == 4                        # every key, both generations
    assert ticks[2].startswith("  generation 0: 3/3 done, +1 certified")


def test_the_driver_without_a_sink_arms_nothing_and_says_nothing(
        monkeypatch, capsys):
    keys = [(0, 0, 0, "C")]
    _stubbed_driver(monkeypatch, certify=set(), follow_ups={})
    originals = {signum: signal.getsignal(signum)
                 for signum in fp.STATUS_SIGNALS}
    armed: list = []
    real_arm = fp.Progress.arm
    monkeypatch.setattr(fp.Progress, "arm",
                        lambda self: armed.append(self) or real_arm(self))
    ledger = fp.run(_FakeRun(), keys, AnalyzerConfig(
        workers=1, rungs=("L0",), rules=("sum",)))
    assert ledger.header["n_certified"] == 0
    assert armed == []
    assert capsys.readouterr().err == ""
    for signum in fp.STATUS_SIGNALS:
        assert signal.getsignal(signum) == originals[signum]
