"""P3-1: the incremental close state, pinned equivalent to the carried gate.

The consult's derived state (``solve/close.py``) answers the same three
questions the carried functions recompute from scratch — is the count
gate open, what is K, what does the counting report say — so the pin is
EQUIVALENCE AT EVERY PREFIX of a growing certificate set, against
``close_count_status`` / ``metadata_from_certificates`` themselves, on
the corners that matter: multi-stream counters, agreeing and opposite
duplicates, a contradiction after rank 24, a malformed word, an
unsupported version, and the rank-24-before-48-distinct window where K
is known but not yet trusted.

Everything here drives the state through its per-certificate seam
(``_ingest`` + ``_settle``) with lightweight equations; no plane and no
payload blobs — which is the point (the gate never touches them).
"""
from __future__ import annotations

import numpy as np
import pytest

from holo2.format import (MIN_METADATA_EQUATIONS, metadata,
                          metadata_from_certificates)
from holo2.format.close_spec import CloseSpec, CloseStreamProfile
from holo2.format.family import Family
from holo2.format.fountain_close import (CertifiedStreamSymbol,
                                         CloseBlockProgress, CloseResult,
                                         MetadataIntegrityError,
                                         close_count_status)
from holo2.solve.close import _CloseState
from holo2.solve.tilemap import TileMapError

SEED = b"holo/v1/test-close-state"
K_SPEC = CloseSpec(
    codec_id="k-v1", seed=SEED, tiles_yx=(16, 16),
    stream_profiles=(CloseStreamProfile("main", 64),),
    spec_id="close-state-k@unit")
CMY8_SPEC = CloseSpec(
    codec_id="cmy8-presence-p120-v0", seed=SEED, tiles_yx=(16, 16),
    stream_profiles=(
        CloseStreamProfile("C", 64, 1),
        CloseStreamProfile("M", 64, 2),
        CloseStreamProfile("Y", 64, 3),
    ),
    spec_id="close-state-cmy8@unit",
    codec_family=Family.CMY8)

K_TOTAL = 61


def _equations(spec: CloseSpec, k_total: int = K_TOTAL, n: int = 100,
               word=None) -> list[CertifiedStreamSymbol]:
    """One lightweight certified equation per (counter, stream).

    Symbols are zeros of the declared shape: the count gate and the
    metadata channel never read them, and feeding real codewords here
    would only obscure what is under test.
    """
    if word is None:
        word = metadata.encode_metadata(0, k_total)
    counters = np.arange(n, dtype=np.int64)
    bits = metadata.tile_bits(word, counters)
    _tiles_y, tiles_x = spec.tiles_yx
    out = []
    for profile in spec.stream_profiles:
        for index, counter in enumerate(counters):
            page, rem = divmod(int(counter), spec.tiles_per_page)
            ty, tx = divmod(rem, tiles_x)
            out.append(CertifiedStreamSymbol(
                counter=int(counter), page=page, ty=ty, tx=tx,
                stream_id=profile.stream_id,
                symbol=np.zeros(profile.symbol_bits, np.uint8),
                metadata_bit=int(bits[index])))
    return out


def _feed(state: _CloseState,
          certs: list[CertifiedStreamSymbol]) -> _CloseState:
    for cert in certs:
        state._ingest((cert.stream_id, cert.counter), cert.stream_id,
                      cert.counter, cert.metadata_bit)
    state._settle()
    return state


def _batch_gate(certs, spec):
    """(ready, counts, k_total, rank, unique) from the carried functions."""
    ready, counts = close_count_status(certs, spec)
    try:
        _version, k_total, diag = metadata_from_certificates(certs, spec)
        rank, unique = diag["metadata_rank"], diag["n_unique_metadata_counters"]
    except MetadataIntegrityError:
        k_total, rank, unique = None, None, None
    return ready, counts, k_total, rank, unique


def _state_counts(state: _CloseState):
    if state.counts is None:
        return None
    return {(stream_id, block): counts.have[block]
            for stream_id, counts in state.counts.items()
            for block in range(counts.code.n_blocks)}


@pytest.mark.parametrize("spec", (K_SPEC, CMY8_SPEC),
                         ids=("k-v1", "cmy8"))
def test_state_equals_the_carried_gate_at_every_prefix(spec) -> None:
    """The load-bearing pin: incremental == batch, certificate by
    certificate, through the rank-24 and 48-distinct transitions and
    into count-ready."""
    rng = np.random.default_rng(20260813)
    certs = _equations(spec)
    rng.shuffle(certs)                              # arrival order is free
    state = _CloseState(spec)
    for i, cert in enumerate(certs):
        _feed(state, [cert])
        prefix = certs[:i + 1]
        ready, counts, k_total, rank, unique = _batch_gate(prefix, spec)
        assert state.ready == ready, f"gate diverged at prefix {i + 1}"
        assert state.metadata.k_total == k_total
        if rank is not None:
            assert state.metadata.rank == rank
            assert state.metadata.unique == unique
        if counts is not None:
            assert _state_counts(state) == counts
        assert len(state.processed) == i + 1


def test_a_fresh_state_equals_the_grown_state_at_any_prefix() -> None:
    """Rebuild-equals-incremental: what a resume pays, and gets."""
    rng = np.random.default_rng(7)
    certs = _equations(K_SPEC)
    rng.shuffle(certs)
    grown = _CloseState(K_SPEC)
    for prefix_end in (1, 23, 24, 47, MIN_METADATA_EQUATIONS, 80, 100):
        while len(grown.processed) < prefix_end:
            _feed(grown, [certs[len(grown.processed)]])
        fresh = _feed(_CloseState(K_SPEC), certs[:prefix_end])
        assert (grown.ready, grown.metadata.rank, grown.metadata.unique,
                grown.metadata.k_total, _state_counts(grown)) == (
            fresh.ready, fresh.metadata.rank, fresh.metadata.unique,
            fresh.metadata.k_total, _state_counts(fresh))


def test_k_is_known_at_rank_24_and_trusted_only_at_48_distinct() -> None:
    """The 24/48 window: the word is pinned by rank, K acts on trust.

    Between rank 24 and the 48-distinct floor the carried gate keeps
    k_total None (state ``incomplete``) — the floor is a false-accept
    budget of surplus parity checks, not a convergence wait — and the
    incremental state must neither act early nor lag."""
    certs = _equations(K_SPEC)
    state = _CloseState(K_SPEC)
    _feed(state, certs[:30])
    assert state.metadata.rank == 24, "30 consecutive counters reach rank 24"
    assert state.metadata.unique == 30 < MIN_METADATA_EQUATIONS
    assert state.metadata.k_total is None and not state.ready
    assert state.counts is None, "no VolumeCode before K is trusted"
    _feed(state, certs[30:MIN_METADATA_EQUATIONS])
    assert state.metadata.unique == MIN_METADATA_EQUATIONS
    assert state.metadata.k_total == K_TOTAL
    assert state.counts is not None, "K trusted: the block counters exist"


def test_an_opposite_duplicate_is_terminal_at_arrival() -> None:
    """Two certified bits disagreeing at one counter (the CMY8 shape:
    streams share tile counters) — inconsistent, terminal, same prefix
    as the carried gate."""
    certs = _equations(CMY8_SPEC, n=20)
    wrong = certs[25]                       # M#5: C#5 already said the bit
    assert wrong.stream_id == "M" and wrong.counter == certs[5].counter
    certs[25] = CertifiedStreamSymbol(
        counter=wrong.counter, page=wrong.page, ty=wrong.ty, tx=wrong.tx,
        stream_id=wrong.stream_id, symbol=wrong.symbol,
        metadata_bit=1 - wrong.metadata_bit)
    state = _feed(_CloseState(CMY8_SPEC), certs[:25])
    assert not state.metadata.inconsistent and not state.ready
    _feed(state, [certs[25]])
    assert state.metadata.inconsistent and state.metadata.terminal
    assert state.ready, "terminal metadata opens the gate for close_volume"
    ready, counts = close_count_status(certs[:26], CMY8_SPEC)
    assert ready and counts is None, "the carried gate agrees"


def test_a_contradiction_after_rank_24_is_terminal_not_a_revised_k() -> None:
    """Past rank 24 the word is unique; a lying equation cannot move K,
    only prove the set inconsistent (L5: terminal, never voted)."""
    certs = _equations(K_SPEC)
    liar = certs[60]
    certs[60] = CertifiedStreamSymbol(
        counter=liar.counter, page=liar.page, ty=liar.ty, tx=liar.tx,
        stream_id=liar.stream_id, symbol=liar.symbol,
        metadata_bit=1 - liar.metadata_bit)
    state = _feed(_CloseState(K_SPEC), certs[:60])
    assert state.metadata.k_total == K_TOTAL
    _feed(state, [certs[60]])
    assert state.metadata.inconsistent and state.ready
    assert state.metadata.k_total == K_TOTAL, (
        "the cached decode stands; the CONTRADICTION is the fact, and "
        "close_volume materialises the terminal answer from the full set")
    with pytest.raises(MetadataIntegrityError):
        metadata_from_certificates(certs[:61], K_SPEC)


def test_a_malformed_word_is_terminal_only_at_the_trust_floor() -> None:
    """Nonzero reserved bits: ``incomplete`` below 48 distinct equations,
    ``malformed`` (gate open, close_volume owes integrity_failure) at it."""
    word = metadata.encode_metadata(0, K_TOTAL)
    word[19 + 2] = 1                              # a reserved bit
    certs = _equations(K_SPEC, word=word)
    state = _feed(_CloseState(K_SPEC), certs[:47])
    assert state.metadata.rank == 24 and not state.ready
    _feed(state, [certs[47]])
    assert state.metadata.unique == MIN_METADATA_EQUATIONS
    assert state.metadata.terminal and state.ready
    assert state.metadata.k_total is None
    ready, counts = close_count_status(certs[:48], K_SPEC)
    assert ready and counts is None, "the carried gate agrees"


def test_an_unsupported_version_is_terminal_at_the_trust_floor() -> None:
    """Version 1 is a VALID word this receiver does not implement:
    ready-for-terminal so close_volume can mint ``unsupported``."""
    certs = _equations(K_SPEC, word=metadata.encode_metadata(1, K_TOTAL))
    state = _feed(_CloseState(K_SPEC), certs[:MIN_METADATA_EQUATIONS])
    assert state.metadata.decode is not None
    assert state.metadata.decode.version == 1
    assert state.metadata.k_total is None
    assert state.metadata.terminal and state.ready
    ready, counts = close_count_status(
        certs[:MIN_METADATA_EQUATIONS], K_SPEC)
    assert ready and counts is None, "the carried gate agrees"


def test_a_foreign_stream_is_refused_with_its_name() -> None:
    state = _CloseState(K_SPEC)
    with pytest.raises(TileMapError, match="not declared by the printed"):
        state._ingest(("ghost", 0), "ghost", 0, 1)


def test_the_counting_report_carries_the_block_counts() -> None:
    certs = _equations(K_SPEC)
    state = _feed(_CloseState(K_SPEC), certs[:50])
    report = state.counting_report()
    assert report["status"] == "open" and report["reason"] == "counting"
    assert report["k_total"] == K_TOTAL
    assert report["metadata_rank"] == 24
    assert report["metadata_counters"] == 50
    assert report["certified"] == 50
    assert report["symbols_used"] is None
    assert "metadata_inconsistent" not in report
    rows = report["blocks"]
    assert rows and all(row["stream"] is None for row in rows), (
        "a K row names its blocks by index alone, as the close report does")
    assert sum(row["have"] for row in rows) == 50
    assert all(row["have"] <= 100 and row["needed"] >= 1 for row in rows)


def test_close_is_new_gates_reruns_on_unsolved_block_growth() -> None:
    """The exact re-close gate: a solved block stays solved, so only a
    distinct symbol landing in an unsolved block (or metadata turning
    terminal) can change ``close_volume``'s answer."""
    certs = _equations(K_SPEC)
    state = _feed(_CloseState(K_SPEC), certs[:60])
    assert not state.count_ready, "one block, needed 61, have 60"
    assert state.close_is_new(), "no attempt yet: the first close runs"
    counts = state.counts
    assert counts is not None and counts["main"].code.n_blocks == 1
    state.record_attempt(CloseResult(
        status="open", payload=None, k_total=K_TOTAL,
        blocks=(CloseBlockProgress(0, K_TOTAL, 60, 59, False,
                                   stream_id=None),)))
    assert not state.close_is_new(), "nothing moved: the rerun is skipped"
    _feed(state, [certs[60]])
    assert state.close_is_new(), "an unsolved block gained a symbol"
    state.record_attempt(CloseResult(
        status="open", payload=None, k_total=K_TOTAL,
        blocks=(CloseBlockProgress(0, K_TOTAL, 61, 61, True,
                                   stream_id=None),)))
    _feed(state, [certs[61]])
    assert not state.close_is_new(), (
        "a symbol landing in a SOLVED block cannot change the answer; "
        "its surplus audit rides the eventual deciding close")


def test_a_ready_state_names_why_it_is_not_deciding() -> None:
    """Review observation 2 (2026-08-13): "counting" only while counting.

    A count-ready state held back is not counting — the report says
    which of the two undecided cases it is: ``deferred`` (observe mode
    holds a ready state back) or ``no_new_answer`` (a close-mode
    re-attempt could not answer differently). Below ready, the reason
    stays ``counting`` in every mode.
    """
    import numpy as np
    from unittest import mock
    from holo2.solve.close import VolumeClose

    ready_state = _feed(_CloseState(K_SPEC), _equations(K_SPEC))
    assert ready_state.count_ready, "the fixture must reach count-ready"

    consumer = VolumeClose()
    consumer._state = ready_state
    with mock.patch.object(ready_state, "absorb"):
        observed = consumer.consult(mock.Mock(), mode="observe").report
        assert observed["reason"] == "deferred"
        ready_state.record_attempt(mock.Mock(blocks=()))
        assert not ready_state.close_is_new()
        gated = consumer.consult(mock.Mock(), mode="close").report
        assert gated["reason"] == "no_new_answer"

    counting = _feed(_CloseState(K_SPEC), _equations(K_SPEC, n=10))
    assert not counting.ready
    consumer2 = VolumeClose()
    consumer2._state = counting
    with mock.patch.object(counting, "absorb"):
        for mode in ("observe", "close"):
            report = consumer2.consult(mock.Mock(), mode=mode).report
            assert report["reason"] == "counting", mode
