"""The NOT-RECOVERED epilogue surfaces the live close shortfall + rescan hint."""
from __future__ import annotations

from types import SimpleNamespace

from holo.cli import _print_close_shortfall
from holo.receive.close_progress import (
    CloseBlockProgress,
    CloseMetadataProgress,
    CloseProgress,
)


def _result(progress) -> SimpleNamespace:
    return SimpleNamespace(close_progress=lambda: progress)


def test_shortfall_line_and_hint(capsys) -> None:
    progress = CloseProgress(
        k_total=100,
        symbols_used=91,
        blocks=(
            CloseBlockProgress(0, 50, 50, 50, True),
            CloseBlockProgress(1, 50, 43, 41, False),
        ),
        metadata=CloseMetadataProgress(20, 4, 0, False, 20),
    )
    _print_close_shortfall(_result(progress))
    out = capsys.readouterr().out
    assert "close progress: 1/2 fountain blocks solved" in out
    assert "symbol-rank shortfall 9" in out
    assert "metadata rank shortfall 4" in out
    assert "RE-PLACE" in out
    assert "docs/PRINT-DAY.md" in out


def test_silent_without_progress(capsys) -> None:
    _print_close_shortfall(_result(None))
    _print_close_shortfall(SimpleNamespace())  # discovery results lack the hook
    _print_close_shortfall(
        _result(CloseProgress(k_total=None, symbols_used=0)))

    def broken() -> CloseProgress:
        raise RuntimeError("factory failure must never mask the exit path")

    _print_close_shortfall(SimpleNamespace(close_progress=broken))
    assert capsys.readouterr().out == ""
