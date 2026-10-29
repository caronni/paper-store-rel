"""`confetti.py decode` is a door onto holo3's CLI (Gate E brief §3 step 2,
2026-09-05): it hands its whole argument vector to `holo.receiver.cli.main`, says so
in its own help, and carries no reference to the retired v1 receiver."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from holo import cli

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:            # holo3 sits beside src/, as in cli
    sys.path.insert(0, str(_ROOT))

import holo.receiver.cli  # noqa: E402


@pytest.fixture
def forwarded(monkeypatch) -> list[list[str]]:
    seen: list[list[str]] = []

    def fake_main(argv: list[str] | None = None) -> int:
        seen.append(list(argv or []))
        return 0

    monkeypatch.setattr(holo.receiver.cli, "main", fake_main)
    return seen


def test_decode_help_names_holo3_and_its_own_help(capsys) -> None:
    assert cli.main(["decode", "--help"]) == 0
    out = capsys.readouterr().out
    assert "holo3" in out
    assert "./confetti3.py decode --help" in out
    assert "--scan-dpi" in out and "--state" in out   # where the v1 flags went


@pytest.mark.parametrize("argv", [
    pytest.param(
        ["scan-a.tiff", "scan-b.tiff", "--dpi", "1200", "--dpi", "1200",
         "--format", "c3-k-r0550@7x7", "--out", "payload.bin",
         "--diag", "8023"],
        id="remainder_of_argv",
    ),
    # leading_option is the reason the split is taken on argv rather than
    # through an argparse.REMAINDER positional: REMAINDER refuses a leading
    # option, so this spelling would die with a holo1 parse error naming a
    # holo3 flag.
    pytest.param(
        ["--format", "c3-k-r0550@7x7", "--out", "p.bin",
         "scan.tiff", "--dpi", "1200"],
        id="leading_option",
    ),
])
def test_decode_forwards_argv_verbatim(forwarded, argv) -> None:
    assert cli.main(["decode", *argv]) == 0
    assert forwarded == [["decode", *argv]]


def test_decode_exit_code_is_holo3s(monkeypatch) -> None:
    monkeypatch.setattr(holo.receiver.cli, "main", lambda argv=None: 2)
    assert cli.main(["decode", "scan.tiff", "--dpi", "1200"]) == 2

