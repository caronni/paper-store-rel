from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

SLOW_LANE_ENV = "HOLO3_RUN_SLOW_TESTS"
ORACLE_SWEEPS_ENV = "HOLO3_RUN_ORACLE_SWEEPS"
FIXTURE_CACHE_ENV = "HOLO3_FIXTURE_CACHE"

WORKTREE_ROOT = Path(__file__).resolve().parents[4]   # src/holo/receiver/tests/
TESTS_DIR = Path(__file__).resolve().parent
HOLO3_ROOT = TESTS_DIR.parent

_FALSE = ("", "0", "false", "False", "no", "off")


def _flag(name: str) -> bool:
    return os.environ.get(name, "") not in _FALSE


def slow_lane() -> bool:
    return _flag(SLOW_LANE_ENV)


def oracle_sweeps() -> bool:
    return _flag(ORACLE_SWEEPS_ENV)


def skip_unless_slow_lane(what: str) -> None:
    if slow_lane():
        return
    pytest.skip(f"{what} needs the sim-decode lane: set {SLOW_LANE_ENV}=1")


def skip_unless_oracle_sweeps(what: str) -> None:
    if oracle_sweeps():
        return
    pytest.skip(f"{what} is the widened matrix: set {ORACLE_SWEEPS_ENV}=1")


def subsample(rng: object, items: object, n_fast: int) -> tuple:
    rows = tuple(items)
    if oracle_sweeps() or len(rows) <= n_fast:
        return rows
    picked = rng.choice(len(rows), size=n_fast, replace=False)
    return tuple(rows[int(index)] for index in sorted(picked))


def source_files(root: Path,
                 exclude_dirs: tuple[str, ...] = ("__pycache__",),
                 suffix: str = ".py") -> tuple[Path, ...]:
    root = Path(root)
    if not root.exists():
        return ()
    found = []
    for path in root.rglob(f"*{suffix}"):
        if not path.is_file():
            continue
        if any(part in exclude_dirs for part in path.parts):
            continue
        found.append(path)
    return tuple(sorted(found))


def assert_golden(name: str, actual: object, expected: object) -> None:
    if actual == expected:
        return
    raise AssertionError(
        f"{name}: frozen golden mismatch — a mismatch here is a "
        f"printed-format fork, never a test to update\n"
        f"  expected {expected!r}\n"
        f"  actual   {actual!r}")


def assert_measured(what: str, actual: object, pinned: object) -> None:
    """The same comparison as ``assert_golden``, told honestly.

    A printed-format golden may never move: a mismatch there is a format
    fork.  A RECEIVER-AXIS pin -- a certificate count, a fire count, a
    rescued set -- is a measurement of this tree on this stimulus, and it
    moves when the receiver does.  It still may not be edited to make a
    run green: the cause goes in the module's dated ledger first.
    """
    if actual == pinned:
        return
    raise AssertionError(
        f"{what}: measured pin moved — a measured receiver-axis pin: "
        f"re-pin only with the cause named in the module's dated ledger\n"
        f"  pinned {pinned!r}\n"
        f"  actual {actual!r}")


class Checks:

    def __init__(self, label: str) -> None:
        self.label = label
        self.passed: list[str] = []
        self.failures: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        if ok:
            self.passed.append(name)
        else:
            self.failures.append(f"{name}: {detail}" if detail else name)
        return bool(ok)

    def equal(self, name: str, actual: object, expected: object) -> bool:
        return self.check(name, actual == expected,
                          f"expected {expected!r}, got {actual!r}")

    def refuses(self, name: str, exc_types: object, call: object,
                reason: str = "") -> bool:
        try:
            call()
        except exc_types as exc:  # type: ignore[misc]
            if reason and reason not in str(exc):
                return self.check(
                    name, False,
                    f"refused with {str(exc)!r}, expected {reason!r} in it")
            return self.check(name, True)
        return self.check(name, False, "did not refuse")

    @property
    def n_total(self) -> int:
        return len(self.passed) + len(self.failures)

    def assert_clean(self) -> None:
        if not self.failures:
            return
        lines = [f"{self.label}: {len(self.failures)} of {self.n_total} "
                 f"checks failed"]
        lines.extend(f"  - {failure}" for failure in self.failures)
        raise AssertionError("\n".join(lines))


class Timer:

    def __init__(self) -> None:
        self.started_at = time.monotonic()

    def elapsed_s(self) -> float:
        return time.monotonic() - self.started_at
