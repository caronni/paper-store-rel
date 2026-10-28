"""VERDICT 3 (run channel): the state survives, on COPIES of run channel's own.

Two durability claims, both read off the run the other verdicts already
paid for, and both operating on a COPY so run channel's state is never
disturbed (the verdicts' fixtures are session-scoped and shared).

**(a) The crash is re-earned, not lost.** Journal-authoritative
persistence puts the durable record and the durable memo in two files
with two cadences: the JOURNAL takes one batch id per commit and fsyncs
it there and then; the CACHE takes a delta frame every ``snapshot_every``
commits. A crash leaves the record AHEAD of the memo, and the gap is
re-earned by re-executing exactly the recorded batches and verifying each
against the id the journal holds for that position. Staged by cutting the
copy's last cache frame while leaving its journal whole — precisely what
a process killed between two frames leaves behind, and reproducible,
which a kill is not.

**(b) The resume needs no SCANS.** Evidence LLRs, regions, poses and
footings are durable, so the same cut copy re-opened with ZERO scans
re-earns its tail and closes byte-exact — the 2.29 GB TIFF is not read,
re-hashed or re-surveyed to learn facts the store already holds, proven
at both doors a raster can come through.

WHAT IT DOES NEED, AND WHERE THAT CAME FROM (2026-08-17). A crash-cut
tail is priced tail-first, and with payload below placement it always
ends in placement commits — passes over PIXELS. This file used to claim
those could be re-earned "with no pixels at all", and that claim was
false: the resume stalled at the raster gate and the close then committed
at a journal position already held, which the journal refuses. The pixels
a placement fire actually reads are not the scan, they are the region's
prepared plane in the ``<state-dir>.prepared`` sibling (§6.8/W1a), and
those files SURVIVE a crash — they were simply unnameable, because the
backing scalar in their digest was computed per session and recorded
nowhere. It rides ``CaptureRecord`` now, so the tail re-earns from the
derived pixels alone.

So (b) has two arms, and they are the two states a crashed directory can
actually be in:

* **in place** — the state and its ``.prepared`` sibling, which is what a
  killed process leaves on disk. Zero scans, both ingest doors nailed
  shut, closes VERIFIED byte-exact.
* **state only** — the sibling gone (or never carried along). Nothing can
  re-earn a pixel pass here, and the verdict is that the refusal SAYS so:
  which captures, and which two inputs would fix it, in front of the fold
  rather than as a raw divergence at the end of it.

WHAT H4 W2's START MARKERS CHANGED HERE: the journal records DISPATCHES
beside commits, so "the journal stands ahead of the memo" is a statement
about ENTRIES (``journal_position``) and the size of the tail to re-earn
is a statement about COMMITS (``commit_count``) — the two stopped being
one integer. And a cache frame is now taken only where NO dispatch is
outstanding, because a frame is a resume point: a serial run like this
one is unaffected (the pass that just committed is the only one there
was), and a pooled crash gets a boundary its replay can actually honour.

THE F-16 RE-EARN HOLE, NAMED AND WORKED AROUND, NOT FIXED. A recorded
commit can fail to re-earn when its descriptor is no longer ENUMERABLE at
the state the resume starts from — the known case is a payload spend that
wrote nothing, whose work key the resumed frontier does not offer again.
That hole is pre-existing, it is on the engine's ledger, and it is not
this wave's to close. What this file does about it is stage the cut on a
frame boundary that DOES re-earn (:data:`FRAMES_CUT`), and say so here:
if a future change moves the tail across such a commit, this file fails
with a stalled recovery and the fix is the ledger item, not a re-pin.

**IT FIRED, on the identity migration** (2026-08-22, RULINGS G5): the
page changed, so the run's commit sequence and its frame boundaries
changed, and the old one-frame cut landed across exactly the payload
spend the paragraph above names. The response is the one this file
already declared for a MOVED tail — re-measure the boundary, which
:data:`FRAMES_CUT` now records with its numbers — and NOT a weakened
assertion: the hole itself is untouched and still the engine's ledger
item. What the episode adds to the record is that the boundary is a
property of the PAGE and not only of the engine, which the constant now
says out loud.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import PageRun, copy_state, decode, open_state

from holo2.core.cache import CACHE_NAME
from holo2.core.journal import (JOURNAL_NAME, ReplayError, commit_count,
                                read_journal)
from holo2.solve.prepared import prepared_directory

#: How many cache frames the staging cuts — the SMALLEST cut whose tail
#: this arm can re-earn, measured on this page (see the F-16 note in the
#: module docstring: the constant exists to step around a named hole, so
#: it is a measurement and never a preference).
#:
#: RE-MEASURED 1 -> 3 by the identity migration (2026-08-22, RULINGS G5).
#: The verdicts' pages are v2 identities now, so run channel decodes a
#: different dot field, commits a different sequence and frames it in
#: different places; on this page the one- and two-frame cuts land across
#: a payload spend that wrote nothing — the named F-16 hole, verbatim,
#: reported as ``journal position N records <id> and this fold derived
#: >["payload",...]``. Cutting three re-earns. NOTHING WAS LOOSENED:
#: every assertion below is unchanged, the staging is still a real crash
#: (``frames > 1``, ``unearned > 0``, the journal standing ahead of the
#: memo), and a cut of four fails the ``.prepared`` arm — so three is the
#: boundary, not a margin.
FRAMES_CUT = 3


def cut_frames(state_dir: Path, frames: int = FRAMES_CUT) -> int:
    """Drop the cache's last ``frames`` delta frames; leave the journal whole.

    Frames are length-prefixed (``core.cache``), so "N frames back" is
    exact: walk the prefixes, keep every frame but the last N. Returns the
    number of frames the run wrote.
    """
    raw = (state_dir / CACHE_NAME).read_bytes()
    ends, offset = [0], 0
    while offset < len(raw):
        offset += 8 + int.from_bytes(raw[offset:offset + 8], "big")
        ends.append(offset)
    assert len(ends) >= frames + 2, (
        f"the run wrote {len(ends) - 1} frame(s); cutting {frames} would "
        "leave nothing")
    (state_dir / CACHE_NAME).write_bytes(raw[:ends[-1 - frames]])
    return len(ends) - 1


def copy_prepared(source: Path, target: Path) -> Path:
    """Carry the ``<state-dir>.prepared`` SIBLING across with the state.

    ``copy_state`` deliberately copies the state directory alone — that is
    the right default for a durability check, and it is what makes the
    "state only" arm below expressible. An in-place crash leaves both, so
    the realistic arm has to reconstruct both, and the sibling travels
    unchanged: a prepared plane is named by the capture, the support grid,
    the pitch, the aperture and the backing, and not one of those is a
    path — so the names stay valid under any state directory.
    """
    origin = prepared_directory(source)
    if origin.is_dir():
        shutil.copytree(origin, prepared_directory(target))
    return target


@pytest.fixture(scope="module")
def crashed(tmp_path_factory: pytest.TempPathFactory, run_channel: PageRun) -> Path:
    """A COPY of run channel's state with its last cache frame cut away."""
    copy = copy_state(run_channel.state_dir,
                      tmp_path_factory.mktemp("verdicts-crashed") / "state")
    copy_prepared(run_channel.state_dir, copy)
    frames = cut_frames(copy)
    assert frames > 1, "the staging cut the only frame there was"
    return copy


#: A DISPATCH MARKER of the placement source, as the journal spells it
#: (H4 W2's start markers: ``>`` then the work id as JSON). The arm that
#: needs one asks for the marker rather than for a frame count, so the
#: fixture below states its own subject instead of trusting a number that
#: the schedule can move under it — which is exactly what H5's re-work
#: aging did to the number that used to be enough.
PLACE_DISPATCH = '>["place"'


@pytest.fixture(scope="module")
def crashed_mid_placement(tmp_path_factory: pytest.TempPathFactory,
                          run_channel: PageRun) -> Path:
    """A crash cut back far enough to leave a PLACEMENT pass unearned.

    The minimal staging above is the right one for re-earning (it is the
    boundary (a) and (b) one measure), but it says nothing about WHAT is
    in the tail, and one arm needs a pass that cannot be re-executed
    without pixels. So this one deepens the cut until the tail holds a
    placement dispatch and stops there: the smallest crash that carries
    this arm's subject, found by looking rather than by declaring a
    frame count that the next scheduling ruling would silently invalidate.
    """
    base = tmp_path_factory.mktemp("verdicts-crashed-placement")
    frames = 1
    while True:
        copy = copy_state(run_channel.state_dir, base / f"cut-{frames}")
        total = cut_frames(copy, frames)
        with open_state(copy, run_channel.page.row, (),
                        run_channel.recipe) as session:
            tail = session.store.ordering()[session.store.journal_position:]
        if any(entry.startswith(PLACE_DISPATCH) for entry in tail):
            return copy
        frames += 1
        assert frames < total, (
            f"no cut of this run's {total} cache frames leaves a recorded "
            "placement pass unearned; the arm has lost its subject")


def test_the_journal_stands_ahead_of_the_memo(crashed: Path,
                                              run_channel: PageRun) -> None:
    """The staging really is a crash: commits past the memo are RECORDED."""
    _header, ordering = read_journal(crashed / JOURNAL_NAME)
    with open_state(crashed, run_channel.page.row, run_channel.scans, run_channel.recipe) as session:
        assert session.store.journal_position < len(ordering), (
            "the cut removed no commits at all")
        assert session.store.ordering() == ordering
        assert not session.store.is_terminal(), (
            "the close rode the cut frame; a crash before it is not a "
            "closed session")
    # And the record itself is untouched by the cut — that is the point.
    assert ((crashed / JOURNAL_NAME).read_bytes()
            == (run_channel.state_dir / JOURNAL_NAME).read_bytes())


def test_the_tail_is_re_earned_onto_the_uncrashed_state(
        tmp_path: Path, crashed: Path, run_channel: PageRun) -> None:
    """(a) Same fold, same state, same payload — the strong form.

    Not merely an equivalent state: the SAME journal, byte for byte, and
    the same durable state bytes as the run that never crashed.
    """
    state_dir = copy_state(crashed, tmp_path / "re-earned")
    with open_state(state_dir, run_channel.page.row, run_channel.scans, run_channel.recipe) as session:
        unearned = (commit_count(session.store.ordering())
                    - session.store.commit_seq)
    assert unearned > 0

    outcome, _observer = decode(state_dir, run_channel.page.row, run_channel.scans, recipe=run_channel.recipe,
                                complete=True)
    assert outcome.status == "verified", outcome.reason
    assert outcome.payload == run_channel.page.payload
    assert outcome.commits <= unearned, (
        f"recovery committed {outcome.commits} for a tail of {unearned} — it "
        "re-decided rather than re-earned")

    with open_state(state_dir, run_channel.page.row, run_channel.scans, run_channel.recipe) as session:
        recovered = session.store.state_bytes()
    with run_channel.open() as original:
        assert recovered == original.store.state_bytes()
    assert ((state_dir / JOURNAL_NAME).read_bytes()
            == (run_channel.state_dir / JOURNAL_NAME).read_bytes())


def test_the_same_crash_re_earns_and_closes_with_no_scans_at_all(
        tmp_path: Path, crashed: Path, run_channel: PageRun,
        monkeypatch: pytest.MonkeyPatch) -> None:
    """(b) arm one: the in-place crash. Zero scans, and it still closes.

    The realistic shape — a killed process leaves the state directory AND
    its ``.prepared`` sibling — re-opened with no ``--scan`` at all. The
    captures are catalogued and their rasters absent, so the resume reads
    no acquisition; it re-earns its recorded placement tail out of the
    derived pixels that survived beside the state, and closes VERIFIED
    byte-exact on the same journal, byte for byte.

    BOTH scan doors are nailed shut for the duration, which is what turns
    "did not need the files" into "did not touch them": since streaming
    ingestion (H4) a capture can reach a session two ways — an ingest
    fire's derivation, and the plane's attach-by-reopen — and a run with
    no ``--scan`` declares nothing for either to open.
    """
    state_dir = copy_state(crashed, tmp_path / "no-scans")
    copy_prepared(crashed, state_dir)
    assert list(prepared_directory(state_dir).iterdir()), (
        "the staging carried no prepared planes; this arm would be arm two")
    with open_state(state_dir, run_channel.page.row, (), run_channel.recipe) as before:
        plane = before.plane
        assert plane.captures, "the catalog produced no capture"
        assert all(capture.raster is None for capture in plane.captures), (
            "a resume with no --scan attached a raster anyway")
        assert plane.raster(plane.captures[0].source_sha256) is None
        assert plane.detached_captures() == tuple(
            sorted(capture.source_sha256 for capture in plane.captures))
        unearned = (commit_count(before.store.ordering())
                    - before.store.commit_seq)
        recorded = len(before.store.ordering())
        position = before.store.journal_position
    assert unearned > 0 and position < recorded

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("a resume with no --scan opened a capture")

    monkeypatch.setattr("holo2.capture.ingest.capture_facts", refuse)
    monkeypatch.setattr("holo2.solve.plane.open_capture", refuse)
    outcome, _observer = decode(state_dir, run_channel.page.row, (), complete=True,
                                recipe=run_channel.recipe)
    assert outcome.status == "verified", outcome.reason
    assert outcome.payload == run_channel.page.payload
    assert outcome.commits <= unearned, (
        f"recovery committed {outcome.commits} for a tail of {unearned} — it "
        "re-decided rather than re-earned")

    with open_state(state_dir, run_channel.page.row, (), run_channel.recipe) as session:
        # A terminal session ingests nothing (§5.5), so its plane holds no
        # captures at all — which is itself the durable verdict standing
        # without a single scan behind it.
        assert session.terminal
        assert session.close_record() is not None
        assert session.store.journal_position == recorded
    # The strong form, as in (a): the SAME record, not an equivalent one.
    assert ((state_dir / JOURNAL_NAME).read_bytes()
            == (run_channel.state_dir / JOURNAL_NAME).read_bytes())


def test_a_crash_with_neither_scans_nor_prepared_planes_says_so(
        tmp_path: Path, crashed_mid_placement: Path,
        run_channel: PageRun) -> None:
    """(b) arm two: state only. The refusal NAMES the missing inputs.

    Strip the sibling and nothing on this machine can re-execute a
    recorded placement pass. What that must not become is the raw
    divergence refusal at the end of the fold — true, and useless, because
    it describes the symptom (two batch ids disagree) rather than the
    cause (you did not hand me the pixels). So recovery refuses in front
    of the fold, naming the captures and both remedies.

    RE-DECLARED ONTO ITS OWN CRASH at H5 (2026-08-19, re-work aging), with
    its cause. This arm needs a recorded PLACEMENT pass in the unearned
    tail — that is the pass no machine can re-execute without pixels — and
    it used to get one from the shared minimal crash for free. It no
    longer does: re-attempts now price into the re-work band, so placement
    drains EARLIER and the last cache frame of this run is all payload.
    The remedy is a deeper cut rather than a deeper default: the shared
    :func:`crashed` stays the smallest honest staging, which is what arms
    (a) and (b) one measure, and this arm takes a crash cut back far
    enough to hold its own subject — proved by the fixture, not assumed.
    """
    state_dir = copy_state(crashed_mid_placement, tmp_path / "state-only")
    assert not prepared_directory(state_dir).exists()
    with open_state(state_dir, run_channel.page.row, (), run_channel.recipe) as before:
        # Read off the CRASHED state, not run channel's own: run channel is terminal
        # and a terminal session ingests nothing, so its plane is empty.
        shas = [sha[:12] for sha in before.plane.detached_captures()]
    with pytest.raises(ReplayError) as refusal:
        decode(state_dir, run_channel.page.row, (), complete=True,
                                recipe=run_channel.recipe)
    message = str(refusal.value)
    assert shas and all(sha in message for sha in shas), message
    assert "prepared" in message and "scan" in message, message
    assert "interrupted mid-run" in message, message
    # NOT the journal's divergence refusal — that law is untouched and
    # still downstream of this one.
    assert "cannot reproduce the recorded tail" not in message, message


def test_a_recovered_state_re_opens_as_an_exact_no_op(
        tmp_path: Path, crashed: Path, run_channel: PageRun) -> None:
    """Once re-earned, the memo covers the record again and stays there."""
    state_dir = copy_state(crashed, tmp_path / "settled")
    outcome, _observer = decode(state_dir, run_channel.page.row, run_channel.scans, recipe=run_channel.recipe,
                                complete=True)
    assert outcome.status == "verified"
    with open_state(state_dir, run_channel.page.row, run_channel.scans, run_channel.recipe) as session:
        assert (session.store.journal_position
                == len(session.store.ordering()))
        assert session.store.is_terminal()
    before = (state_dir / CACHE_NAME).read_bytes()
    again, _observer = decode(state_dir, run_channel.page.row, run_channel.scans, recipe=run_channel.recipe,
                              complete=True)
    assert again.status == "verified"
    assert again.resumed_terminal
    assert again.commits == 0 and again.fires == 0
    assert (state_dir / CACHE_NAME).read_bytes() == before
