"""One open session: the lineage it binds, and what resuming it costs.

R2 split ``engine/runtime.py``; these are the assertions of its test that
are the engine's — §5.1 identity, L10 no-op resumption, and §5.5
terminality. The session is composed through the composition root
(``cli.open_receiver``), because composing a lineage with a plane is
exactly what a composition root is for.
"""
from __future__ import annotations

from fractions import Fraction

from dataclasses import replace
from pathlib import Path

import pytest

from holo2 import cli
from holo2.core.commit import CommitBatch, Write
from holo2.core.records import CLOSE_KEY, CloseRecord, CloseStatus
from holo2.engine import POLICY_ID, RECIPE_V1
from holo2.format import FormatRowSpec
from holo2.format.close_spec import CloseStreamProfile

DPI = 600.0

ROW = FormatRowSpec(
    row_id="c3-test@128x128", codec_id="k-v1", seed=b"holo/v1/test/128x128",
    tiles_yx=(2, 2), pitch_in=Fraction(1, 200),
    streams=(CloseStreamProfile("main", 32),), n_pages=1)


def _request(tmp_path: Path, capture_path: Path) -> cli.DecodeRequest:
    return cli.parse_request([
        "--scan", str(capture_path), "--dpi", str(DPI),
        "--state-dir", str(tmp_path / "state"), "--output", "payload.bin"])


@pytest.fixture
def session(tmp_path: Path, synthetic_print: Path):
    context = cli.open_receiver(_request(tmp_path, synthetic_print), ROW,
                                recipe=RECIPE_V1, fsync=False)
    yield context
    context.close()


def test_lineage_is_the_declared_identity(session) -> None:
    identity = session.store.session
    assert identity.format_row_id == ROW.row_id
    assert identity.recipe_entries == RECIPE_V1.entries
    assert identity.providers == ()
    assert identity.receiver_policy_id == POLICY_ID
    assert identity.page_domain == (0,)


def test_the_session_hands_workers_its_plane(session) -> None:
    """One read-only view, and it is the derived plane (R1/R2)."""
    assert session.view() is session.plane


def test_reopening_the_same_state_changes_nothing(
        tmp_path: Path, synthetic_print: Path) -> None:
    request = _request(tmp_path, synthetic_print)
    with cli.open_receiver(request, ROW, recipe=RECIPE_V1, fsync=False) as first:
        before = first.store.state_bytes()
        seq = first.store.commit_seq
    with cli.open_receiver(request, ROW, recipe=RECIPE_V1, fsync=False) as second:
        assert second.store.state_bytes() == before
        assert second.store.commit_seq == seq


def test_a_terminal_session_is_opened_and_nothing_else(
        tmp_path: Path, synthetic_print: Path) -> None:
    request = _request(tmp_path, synthetic_print)
    with cli.open_receiver(request, ROW, recipe=RECIPE_V1, fsync=False) as first:
        first.apply(CommitBatch(writes=(Write(CLOSE_KEY, CloseRecord(
            CloseStatus.VERIFIED, "ab" * 32, None)),)))
    with cli.open_receiver(request, ROW, recipe=RECIPE_V1, fsync=False) as second:
        assert second.terminal
        assert second.plane.captures == ()
        assert second.close_record().status is CloseStatus.VERIFIED


def test_a_no_close_open_says_which_close_it_set_aside(
        tmp_path: Path, synthetic_print: Path,
        capsys: pytest.CaptureFixture) -> None:
    """The counterpart of the test above, and its operator line.

    Prevents a SILENT skip of a TERMINAL close (review fix, 2026-08-22).
    `src/holo` prints its notice at exactly this moment, and holo2's act
    is the stronger one: v1's detach was in-memory-first and left the file
    VERIFIED when no work followed, while this skip becomes durable — the
    close SUPERSEDED — the moment one commit lands. Nothing else in the
    run would say so: the epilogue speaks afterwards, and only about what
    this run itself did.
    """
    request = _request(tmp_path, synthetic_print)
    with cli.open_receiver(request, ROW, recipe=RECIPE_V1, fsync=False) as first:
        first.apply(CommitBatch(writes=(Write(CLOSE_KEY, CloseRecord(
            CloseStatus.VERIFIED, "ab" * 32, None)),)))
    capsys.readouterr()
    skipping = replace(request, no_close=True)
    with cli.open_receiver(skipping, ROW, recipe=RECIPE_V1,
                           fsync=False) as second:
        assert not second.terminal, "the fold admitted no close record"
        assert second.close_record() is None
    notice = capsys.readouterr().err
    assert "VERIFIED close is SKIPPED (--no-close)" in notice
    assert "SUPERSEDED" in notice
