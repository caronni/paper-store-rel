"""VERDICT 6 (run streaming): captures arrive DURING the run (H4 streaming ingestion).

Streaming ingestion's own verdict. Before it, a session opened by
surveying every declared scan in turn and the orchestrator's first fire
waited behind the last of them — the nine-platen scrap demo spent minutes
there. Reading an acquisition is WORK now: one spendable attempt per
declared scan, minted one at a time, and each capture record attaching on
the committing thread as it lands.

THREE declared scans since the run-union merge (2026-08-17): sheet 0,
sheet 1, then sheet 0 again (a rescan under run banded's own band, same
print seed, a different sensor draw — ``conftest.run_streaming``'s
docstring has the corruption; ``test_correlated_evidence`` is what reads
the union it makes legal). Four claims, in the order they matter, and
none of them about the third scan's own union — that is the OTHER
verdict's subject, this one just has to keep holding while a third
capture rides along:

1. **the volume still comes back byte-exact**, over three captures none
   of which existed when the session opened. The standing bar, on the
   arm that changed how captures come into being at all;
2. **THE POINT** — a placement commit for capture 1 PRECEDES capture 2's
   capture record in the ordering journal. Placement does not wait for
   the next acquisition; that is the whole card, and it is read off the
   durable record rather than off a counter — and the SAME thing holds
   one link further out, capture 2 to capture 3, checked as a bonus
   below;
3. **sequential by derivation** — capture N+1's ingest is never
   dispatched before capture N's record stands, so exactly one survey
   (the ~8x-raster transient) is ever in flight, and no gate mechanism
   was needed to arrange it. Three captures make three links in the
   chain now, not two;
4. **a resume re-ingests nothing** — pinned on run partial's OPEN state,
   which is the case that matters: a terminal session ingests nothing anyway,
   while an open one is handed its scan again and must attach by reopen
   instead of re-surveying.

WHAT THE JOURNAL CAN AND CANNOT SAY, stated because claim 2 rests on it:
an entry is a batch id or a start marker and carries no content, so the
identity of a commit is read off the run's own id-to-kinds map
(``conftest.record_commit_kinds``) while the ORDER is read off the
journal. The two are joined by the batch id, which is content-derived and
unique.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conftest import (STREAM_WORKERS, StreamRun, VolumeRun, copy_state,
                      decode)

from holo2.capture import KIND_CAPTURE, parse_scan_key
from holo2.core.journal import (JOURNAL_NAME, is_marker, marker_work_id,
                                read_journal)


def _entries(run: StreamRun) -> tuple[str, ...]:
    _header, ordering = read_journal(run.state_dir / JOURNAL_NAME)
    return ordering


def _commit_positions(run: StreamRun, kind: str) -> list[int]:
    """Where commits touching ``kind`` sit in the ordering journal."""
    return [position for position, entry in enumerate(_entries(run))
            if not is_marker(entry) and kind in run.commit_kinds.get(
                entry, frozenset())]


def _ingest_markers(run: StreamRun) -> list[tuple[int, Path]]:
    """Every ingest DISPATCH: its journal position and the scan it named."""
    found = []
    for position, entry in enumerate(_entries(run)):
        if not is_marker(entry):
            continue
        work_id = marker_work_id(entry)
        if work_id.family == "ingest":
            found.append((position, parse_scan_key(work_id.subject)[0]))
    return found


def test_a_streamed_three_capture_volume_comes_back_byte_exact(
        run_streaming: StreamRun, run_partial: VolumeRun) -> None:
    """The standing bar: this tool works when the captures arrive late.

    That all three captures really contributed pixels is not asserted
    off the plane — a terminal session opens empty (§5.5) — but off
    physics and the observer together: run partial is the same volume
    with one sheet and cannot close at K/T = 0.8 however well it
    decodes, and this run's catalog saw three acquisitions (sheet 0
    twice, sheet 1 once).
    """
    outcome = run_streaming.outcome
    assert outcome.status == "verified", outcome.reason
    assert outcome.payload == run_streaming.volume.payload
    assert run_partial.outcome.status == "open", (
        "the one-sheet control closed, so two sheets prove nothing")
    panes = run_streaming.observer.status().get("panes") or {}
    assert len(panes.get("captures") or ()) == 3, (
        "the run's catalog did not hold all three declared scans")


def test_placement_on_capture_one_precedes_capture_two(
        run_streaming: StreamRun) -> None:
    """THE POINT, read off the ordering journal.

    Two readings of the same interleave, and both are asserted because
    they fail for different reasons. The DISPATCH ordering is structural:
    the pool fills every free slot before it waits on any of them, so a
    placement pass is launched beside the second ingest — if that stops
    being true, the scheduling set was empty when it should not have
    been. The COMMIT ordering is the property itself: work on capture 1
    reached the durable record while capture 2 was still being surveyed.

    Three captures now (the run-union merge, 2026-08-17: sheet 0 rides a
    third scan for the union law's positive half — see
    ``conftest.run_streaming``). The chain is checked capture 1 -> 2
    exactly as before, PLUS one link further, capture 2 -> 3, so the
    claim does not quietly get weaker just because the fixture grew a
    capture: placement never waits on an acquisition it does not need,
    however many of them there end up being.
    """
    entries = _entries(run_streaming)
    captures = _commit_positions(run_streaming, KIND_CAPTURE)
    poses = _commit_positions(run_streaming, "pose")
    assert len(captures) == 3, f"{len(captures)} capture-record commits"
    assert poses, "the run placed nothing at all"

    dispatched = [position for position, entry in enumerate(entries)
                  if is_marker(entry)
                  and marker_work_id(entry).family == "place"]
    assert dispatched and dispatched[0] < captures[1], (
        "no placement pass was even DISPATCHED before capture 2's record "
        "landed — the pool had a free slot and nothing to put in it")
    assert poses[0] < captures[1], (
        f"the first pose committed at {poses[0]}, capture 2's record at "
        f"{captures[1]}: placement waited for the acquisition it did not "
        "need")
    # How much of the run happened inside that window — evidence that the
    # ordering is a mechanism and not a photo finish.
    overlapped = sum(1 for position in poses if position < captures[1])
    assert overlapped >= 2, (
        f"only {overlapped} pose(s) landed while capture 2 was being read")

    # THE BONUS LINK: the same property holds one acquisition further
    # out. Capture 3 (sheet 0's rescan) arrives long after the volume
    # could plausibly need it, so this is a weaker bar operationally —
    # but it is free to check and it is what "however many of them"
    # means literally rather than just for N=2.
    assert poses[0] < captures[2], (
        f"the first pose committed at {poses[0]}, capture 3's record at "
        f"{captures[2]}: placement waited for an acquisition three deep")
    overlapped_3 = sum(1 for position in poses if position < captures[2])
    assert overlapped_3 >= overlapped, (
        "fewer poses landed before capture 3 than before capture 2 — the "
        "run went backwards")


def test_the_second_scan_is_read_only_after_the_first_one_stands(
        run_streaming: StreamRun) -> None:
    """Point 2: sequential BY DERIVATION, which is what caps the RAM.

    The provider mints scan N+1 only once scan N's capture record stands,
    so the journal must show each ingest DISPATCH after the previous
    ingest's COMMIT — never two surveys in flight, at any pool width, and
    with no gate anywhere to arrange it. THREE scans now (the run-union
    merge: sheet 0, sheet 1, sheet 0's rescan, in that declared order),
    so the chain has two links to check instead of one — and the name
    stays literal: it is still the SECOND scan (sheet 1) whose ingest is
    being pinned to stand only after the first's record does; the third
    link is the same claim applied once more.
    """
    markers = _ingest_markers(run_streaming)
    captures = _commit_positions(run_streaming, KIND_CAPTURE)
    assert len(markers) == 3, f"{len(markers)} ingest dispatches, expected 3"
    assert [path for _position, path in markers] == [
        path for path, _dpi in run_streaming.scans], "ingest order is the declared one"
    assert (markers[0][0] < captures[0] < markers[1][0] < captures[1]
           < markers[2][0] < captures[2]), (
        f"markers {[position for position, _ in markers]} against capture "
        f"commits {captures}: two acquisitions were in flight at once")


def test_a_resumed_session_attaches_instead_of_re_ingesting(
        tmp_path: Path, run_partial: VolumeRun,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """Point 4, on the state where it matters: an OPEN session, resumed.

    Run partial's volume cannot close from one sheet, so its state is
    open and resumable — and re-decoding it with the SAME scan must not re-survey
    it. The ingest door is nailed shut for the duration; the reopen door
    is not, because attaching by reopen is exactly what should happen.
    """
    state_dir = copy_state(run_partial.state_dir, tmp_path / "resumed")

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a resume re-surveyed a capture it already holds")

    monkeypatch.setattr("holo2.capture.ingest.capture_facts", refuse)
    outcome, _observer = decode(state_dir, run_partial.volume.row, run_partial.scans)
    assert outcome.status == "open", outcome.reason
    assert not outcome.certified or outcome.certified > 0

    with run_partial.open() as session:
        # The pixels are there — the resume attached them by reopening
        # the declared scan, which is the half that must keep working.
        capture = session.plane.captures[0]
        assert capture.raster is not None
        assert session.plane.scan_capture(*run_partial.scans[0]) == (
            capture.source_sha256)


def test_the_ingest_ledger_holds_one_spend_per_declared_scan(
        run_streaming: StreamRun) -> None:
    """The durable half of "already read": one spend row, per scan, forever.

    The derivation drops an ingested scan from the frontier, and the
    ledger is the second belt underneath it — a work id whose identity is
    the EMPTY read-set, so the row one run leaves is the row a later
    run's spend-once test compares against. THREE declared scans now
    (sheet 0's rescan is a distinct path, so a distinct spend), not two.
    """
    with run_streaming.open() as session:
        rows = [row for row in session.store.ledger.entries()
                if row.worker_id.family == "ingest"]
    assert len(rows) == 3, f"{len(rows)} ingest spend rows for three scans"
    assert {parse_scan_key(row.worker_id.subject)[0] for row in rows} == {
        path for path, _dpi in run_streaming.scans}
    assert all(row.identity == () for row in rows), (
        "an ingest attempt reads no durable fact; its identity is empty")


def test_the_pool_width_is_the_one_this_verdict_declares(
        run_streaming: StreamRun) -> None:
    """A guard on the fixture, not on the receiver.

    Run streaming's claims are about concurrency, and a well-meaning edit that
    made this decode serial would leave every assertion above trivially
    true (nothing would ever be dispatched beside anything). The pool
    width is therefore asserted where the claims are.
    """
    assert STREAM_WORKERS >= 2
    assert run_streaming.outcome.fires > 3, "a three-capture decode barely fired"
