"""`--no-close`: the state x mode table, in holo2's vocabulary (2026-08-22).

The user's ruling: *the journal is never rewritten; the trick is to SKIP
the close journal line on ingestion and replay*. The lead's one added
rule makes the trailing journal lawful in every mode: *a close is
terminal only while it is the LAST WORD* — a ``CLOSE_KEY`` write with
commits recorded after it is SUPERSEDED, dropped at the fold under every
policy, and recomputed by the next closing run.

The table this file pins, `src/holo`'s ``tests/holo/test_no_close.py``
re-said in holo2's terms (there is no "detach" here — that word already
means a capture-without-pixels; a close is SKIPPED or SUPERSEDED)::

  state on disk           | default / --complete       | --no-close
  ------------------------+----------------------------+----------------------
  absent                  | greedy close, terminal     | OPEN, no CloseRecord
  OPEN resume             | close when the gate opens  | accumulate only
  terminal (LAST word)    | report it, run nothing     | close SKIPPED at the
                          |                            | fold; work resumes
  SUPERSEDED close        | drop it, recompute, APPEND | accumulate further
  (commits after it)      | a new CloseRecord          |
  integrity_failure       | report it, run nothing     | REFUSED at open

Everything here is one synthetic volume: a 64-tile K field whose workers
mint the ENCODER's own fountain symbols, so the close really verifies and
really reproduces the payload. That is what makes "byte-identical payload
on the recompute" an assertion rather than a hope.
"""
from __future__ import annotations

from fractions import Fraction

import hashlib
from pathlib import Path

import numpy as np
import pytest

from holo2.core.blobs import stage_array
from holo2.core.cache import CACHE_NAME
from holo2.core.commit import CommitBatch, CommitEngine, Write
from holo2.core.journal import ReplayError, is_marker
from holo2.core.records import CLOSE_KEY, CloseRecord, CloseStatus
from holo2.core.store import Store, StoreError
from holo2.core.trace import TraceWriter
from holo2.core.work import WorkResult
from holo2.engine.orchestrator import Orchestrator
from holo2.engine.session import SessionContext
from holo2.format import envelope, fountain, metadata
from holo2.format.close_spec import CloseStreamProfile
from holo2.format.registry_rows import FormatRowSpec
from holo2.solve import MintRef, TileRecord, parse_tile_key, tile_key
from holo2.solve.close import VolumeClose
from holo2.solve.plane import SessionPlane

from conftest import POSE, ground, make_session as make_identity, registry
from test_orchestrator import CertifyingWorker, Factories, RECIPE

# ------------------------------------------------------- the small volume

TILES_YX = (8, 8)
#: 64 tiles clears the 48-counter metadata trust floor with room to spare,
#: which is what lets a run close from a PREFIX of them (the greedy close
#: below stops well short of 64) and still leave work for the next one.
SYMBOL_BITS = 256
SEED = b"holo/v1/no-close-fixture/512x512"
ROW = FormatRowSpec(row_id="c3-noclose@512x512", codec_id="k-v1", seed=SEED,
                    tiles_yx=TILES_YX, pitch_in=Fraction(1, 200),
                    streams=(CloseStreamProfile("main", SYMBOL_BITS),))
SPEC = ROW.close_spec()
PAYLOAD = hashlib.sha256(b"holo2-no-close").digest() * 8
K_TOTAL = envelope.source_symbol_count(len(PAYLOAD), SYMBOL_BITS)
_COUNTERS = np.arange(SPEC.tiles_per_page, dtype=np.int64)
SYMBOLS = fountain.VolumeCode(
    K_TOTAL, SYMBOL_BITS, SEED, tiles_per_page=SPEC.tiles_per_page,
).encode_symbols(
    fountain.pack_source(envelope.wrap(PAYLOAD), K_TOTAL, SYMBOL_BITS),
    _COUNTERS)
META_BITS = metadata.tile_bits(
    metadata.encode_metadata(0, K_TOTAL), _COUNTERS)
ADDRESSES = tuple((0, counter // TILES_YX[1], counter % TILES_YX[1])
                  for counter in range(SPEC.tiles_per_page))


class SymbolWorker(CertifyingWorker):
    """Certifies one tile with the ENCODER's symbol for its counter.

    ``test_orchestrator``'s worker mints a constant, which certifies but
    never closes. This one mints truth, so the volume close reaches
    ``verified`` and republishes the payload byte for byte.
    """

    route = "no-close-certify"

    def run(self, view, identity, progress):
        self.fires += 1
        progress.emit(1, "decode")
        page, ty, tx, _stream = parse_tile_key(self.key)
        counter = SPEC.tile_counter(page, ty, tx)
        bits = stage_array(np.ascontiguousarray(SYMBOLS[counter]))
        return WorkResult(
            outcome="certified", retire=True, blobs=(bits,),
            writes=(Write(self.key, TileRecord(
                minting=MintRef(POSE, "scan", "fixture-decoder"),
                bits_ref=bits.ref, metadata_bit=int(META_BITS[counter]),
                observed_by=("f:1/1",))),))


# ------------------------------------------------------------ scaffolding

def open_session(tmp_path: Path, name: str = "state", *,
                 no_close: bool = False) -> SessionContext:
    """One session over the small volume, opened under a close policy."""
    store = Store.open_or_create(tmp_path / name, make_identity(RECIPE),
                                 registry(), fsync=False, skip_close=no_close)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    ground(engine, "pose")           # the witness every certificate names
    return SessionContext(store, engine, SessionPlane(store, engine, ROW, ()))


def seed_addressed(session: SessionContext) -> None:
    session.apply(CommitBatch(writes=tuple(
        Write(tile_key(page, ty, tx, "main"), TileRecord(observed_by=("f:1/1",)))
        for page, ty, tx in ADDRESSES)))


def run(session: SessionContext, **kwargs):
    return Orchestrator(session, RECIPE, Factories(worker_class=SymbolWorker),
                        close=VolumeClose(), **kwargs).run()


def a_verified_state(tmp_path: Path, name: str = "state"):
    """The starting point of every resume below: one greedy run, closed.

    Returns the recorded ordering, so a test can ask where the close line
    stands afterwards.
    """
    with open_session(tmp_path, name) as session:
        seed_addressed(session)
        outcome = run(session)
        assert outcome.status == "verified"
        assert outcome.payload == PAYLOAD
        return session.store.ordering()


# ------------------------------------------------------------- the table

def test_a_fresh_no_close_run_ends_open_with_no_close_record(
        tmp_path: Path) -> None:
    """Row 1. Prevents: a run under `--no-close` writing a close anyway.

    Both consult sites must sit in ``observe`` — the DECISION is
    suppressed, the observation is not — so the certificates accumulate,
    the report stays live, and ``CLOSE_KEY`` is never written.
    """
    with open_session(tmp_path, no_close=True) as session:
        seed_addressed(session)
        outcome = run(session, no_close=True)
        assert outcome.status == "open"
        assert outcome.certified == len(ADDRESSES)     # nothing was preempted
        assert session.store.close_record() is None    # OPEN is not a record
        assert outcome.close is not None, "observe still reports"
        assert outcome.close["status"] == "open"
    # The table's OPEN-RESUME row under this policy — accumulate only, and
    # still no record. Pinned here rather than as a ninth test: it is the
    # same row's second invocation, and `src/holo` pins its own cell (b)
    # the same way (``tests/holo/test_no_close.py``).
    with open_session(tmp_path, no_close=True) as resumed:
        again = run(resumed, no_close=True)
        assert again.status == "open"
        assert again.certified == len(ADDRESSES)
        assert resumed.store.close_record() is None


def test_a_default_resume_of_a_no_close_state_closes(tmp_path: Path) -> None:
    """Row 2. Prevents: the skip leaking past the run that asked for it.

    ``--no-close`` is a READ-TIME policy of one run, not a property of
    the state directory: the next ordinary run closes what accumulated.
    """
    with open_session(tmp_path, no_close=True) as session:
        seed_addressed(session)
        run(session, no_close=True)
    with open_session(tmp_path) as resumed:
        outcome = run(resumed)
        assert outcome.status == "verified"
        assert outcome.payload == PAYLOAD
        record = resumed.store.close_record()
        assert record is not None and record.status is CloseStatus.VERIFIED


def test_a_no_close_resume_of_a_verified_state_accumulates(
        tmp_path: Path) -> None:
    """Row 3, the one motivation that survives into holo2 (e033 sheet I).

    Prevents: the terminal wall refusing the very accumulation the flag
    exists for. The greedy first run closes from a PREFIX of the field;
    the `--no-close` resume must ingest the rest — commits admitted,
    certificates grown — and write no close of its own.
    """
    a_verified_state(tmp_path)
    with open_session(tmp_path, no_close=True) as resumed:
        before = len(resumed.store.ordering())
        outcome = run(resumed, no_close=True)
        assert outcome.status == "open", "the skipped close reopens the run"
        assert outcome.commits > 0, "the wall admitted the accumulation"
        assert outcome.certified == len(ADDRESSES)
        assert resumed.store.close_record() is None
        assert len(resumed.store.ordering()) > before


def test_a_superseded_close_is_recomputed_and_appended(tmp_path: Path) -> None:
    """Row 4, the lead's rule. Prevents two forks at once.

    (a) reading a close that is no longer the last word as TERMINAL — the
    ordinary run after an accumulation would report a stale terminal
    state and refuse to work; (b) repairing that by rewriting the
    journal. The close is a pure derivation, so the recompute is
    byte-identical and the record is APPENDED: the old line stands
    exactly where it was written, forever.
    """
    recorded = a_verified_state(tmp_path)
    close_index = len(recorded) - 1              # the close committed last
    close_id = recorded[close_index]
    assert not is_marker(close_id)

    with open_session(tmp_path, no_close=True) as accumulating:
        run(accumulating, no_close=True)

    with open_session(tmp_path) as closing:
        # The fold dropped the superseded close: this session is OPEN and
        # the run really re-closes rather than replaying a record.
        assert closing.store.close_record() is None
        assert not closing.terminal
        outcome = run(closing)
        assert outcome.status == "verified"
        assert outcome.payload == PAYLOAD, "a close is a pure derivation"
        ordering = closing.store.ordering()

    assert ordering[close_index] == close_id, "the old close line stands"
    assert ordering[-1] == close_id, "and a NEW one was appended"
    assert ordering.count(close_id) == 2
    assert len(ordering) > len(recorded)


def test_an_integrity_failure_close_refuses_under_no_close(
        tmp_path: Path) -> None:
    """Row 5. Prevents: skipping the ONLY durable trace of a conflict.

    A verified or unsupported close is a derivation from the certificate
    set and costs nothing to drop. An integrity failure is not: the
    conflicting write was refused AT THE WALL and never became durable
    (F-11), so this record's reason is the whole surviving evidence. It
    refuses by name, with the remedy.
    """
    with open_session(tmp_path) as session:
        session.apply(CommitBatch(writes=(Write(CLOSE_KEY, CloseRecord(
            CloseStatus.INTEGRITY_FAILURE,
            reason="tile 0/1/2/main: certified bits differ")),)))
    with pytest.raises(StoreError) as refusal:
        open_session(tmp_path, no_close=True)
    message = str(refusal.value)
    assert "INTEGRITY FAILURE" in message and "--no-close" in message
    assert "certified bits differ" in message
    # And the ordinary policy still reads it: nothing was dropped.
    with open_session(tmp_path) as reopened:
        record = reopened.store.close_record()
        assert record is not None
        assert record.status is CloseStatus.INTEGRITY_FAILURE


def test_complete_alongside_no_close_is_legal_and_redundant(
        tmp_path: Path) -> None:
    """Prevents: treating the pair as a contradiction (the v1 correction).

    Three close policies, ONE axis: `--no-close` already implies the
    deferral, so `--complete` beside it changes nothing. Pinned as
    OUTCOME equality, not as "it does not crash".
    """
    with open_session(tmp_path, "a", no_close=True) as session:
        seed_addressed(session)
        alone = run(session, no_close=True)
        alone_state = session.store.state_bytes()
    with open_session(tmp_path, "b", no_close=True) as session:
        seed_addressed(session)
        both = run(session, no_close=True, complete=True)
        both_state = session.store.state_bytes()
    assert (alone.status, alone.certified) == (both.status, both.certified)
    assert alone_state == both_state


# -------------------------------------------------- the replay contract

def _replay(tmp_path: Path, name: str, ordering, **kwargs):
    """Re-fold a recorded ordering into a FRESH state directory."""
    with open_session(tmp_path, name, no_close=kwargs.get("no_close", False)
                      ) as session:
        seed_addressed(session)                 # the same starting ground
        return run(session, replay=tuple(ordering), **kwargs), session


def test_a_no_close_replay_skips_the_recorded_close_line(
        tmp_path: Path) -> None:
    """Prevents: a `--no-close` audit failing on the line it must skip.

    The user's ruling names ingestion AND replay. The recorded close is
    the one commit shape no PASS produces, so the walk leaves it
    standing; under this policy that is the contract, not a divergence.
    """
    recorded = a_verified_state(tmp_path, "recorded")
    outcome, session = _replay(tmp_path, "replayed", recorded, no_close=True)
    assert outcome.status == "open"
    assert session.store.close_record() is None
    assert session.store.journal_position == len(recorded) - 1


def test_a_superseded_journal_replayed_under_a_closing_policy_is_named(
        tmp_path: Path) -> None:
    """Prevents: "replay stopped at position N" as the whole diagnosis —
    and prevents the diagnosis naming a REMEDY THAT DOES NOT WORK.

    A journal accumulated under `--no-close` after its close holds
    commits past a close, which one run cannot make. Under a closing
    policy the replay re-earns that close, goes terminal there, and can
    follow nothing after it. The first cut of this message told the
    operator to "replay it under --no-close"; the second half below is
    why that sentence is gone — under `--no-close` no pass mints that
    close either, so the walk halts on the SAME entry with the whole
    tail still standing. A superseded recording is not walkable whole
    under any policy, and the message offers the auditable prefix.
    """
    a_verified_state(tmp_path, "recorded")
    with open_session(tmp_path, "recorded", no_close=True) as accumulating:
        run(accumulating, no_close=True)
        recorded = accumulating.store.ordering()

    with pytest.raises(ReplayError) as refusal:
        _replay(tmp_path, "replayed", recorded)
    message = str(refusal.value)
    assert "--no-close" in message and "SUPERSEDED" in message
    assert "PREFIX" in message
    assert "replay it under --no-close" not in message

    with pytest.raises(ReplayError) as under_the_named_policy:
        _replay(tmp_path, "replayed-nc", recorded, no_close=True)
    assert "replay stopped at journal position" in str(
        under_the_named_policy.value)


def test_a_no_close_replay_does_not_prove_the_entry_it_skips_is_a_close(
        tmp_path: Path) -> None:
    """The one-entry exemption's BLIND SPOT, pinned by name (review fix).

    Prevents: the docstrings, the ledger or the handoff claiming that the
    entry a `--no-close` audit leaves standing IS the recorded close. It
    is not checked and cannot be — the check is the close's own settled
    batch id, which means consulting the close in a deciding mode, the
    one act this policy forbids and the one the epilogue promises did not
    happen. A recording made under `--no-close` holds no close line at
    all, so a corrupted LAST commit falls into the exemption and is
    accepted. Stated in ``engine/replay.py``; pinned here so that nobody
    re-states the stronger claim without this test going red.
    """
    with open_session(tmp_path, "recorded", no_close=True) as session:
        seed_addressed(session)
        run(session, no_close=True)
        recorded = list(session.store.ordering())
    assert not is_marker(recorded[-1]), "the recording ends on a commit"
    corrupted = recorded[:-1] + ["0" * 64]

    outcome, replayed = _replay(tmp_path, "blind", corrupted, no_close=True)
    assert outcome.status == "open"
    assert replayed.store.journal_position == len(corrupted) - 1


def test_a_crashed_no_close_tail_refuses_a_closing_resume_by_name(
        tmp_path: Path) -> None:
    """Prevents a DESTRUCTIVE remedy on this flag's own workflow.

    An accumulation under `--no-close` that crashes before its frames
    land leaves a journal tail past a SUPERSEDED close. Re-earning that
    tail under a closing policy re-decides the close part-way through it,
    at a position the journal already holds — and the operator would meet
    ``core.journal``'s divergent-refold refusal, whose named remedy
    (delete the state directory) throws away the certificates the
    interrupted run was accumulating. The refusal names the two-run
    remedy instead, and the second half here is the measurement that
    entitles it to: the payload comes back byte-identical.
    """
    a_verified_state(tmp_path)
    memo = tmp_path / "state" / CACHE_NAME
    framed = memo.read_bytes()
    with open_session(tmp_path, no_close=True) as accumulating:
        assert run(accumulating, no_close=True).commits > 0
    memo.write_bytes(framed)         # the crash: those frames never landed

    with pytest.raises(ReplayError) as refusal:
        with open_session(tmp_path) as closing:
            run(closing)
    message = str(refusal.value)
    assert "SUPERSEDED" in message and "--no-close" in message
    assert "never memoised" in message

    with open_session(tmp_path, no_close=True) as re_earning:
        assert run(re_earning, no_close=True).status == "open"
    with open_session(tmp_path) as closing:
        outcome = run(closing)
        assert outcome.status == "verified"
        assert outcome.payload == PAYLOAD
