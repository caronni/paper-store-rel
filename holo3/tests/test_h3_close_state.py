from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from holo3 import data
from holo3.format import close, metadata
from holo3.tests.test_h3_format_close import (
    SB,
    TILES_PER_PAGE,
    _bit,
    _cert,
    _cmy8_v0_volume,
    _k_volume,
    _pooled_volume,
    _systematic_esis,
    _word,
)

PAYLOAD_K = np.random.default_rng(31).integers(
    0, 256, 300, dtype=np.uint8).tobytes()
PAYLOAD_CMY8 = np.random.default_rng(32).integers(
    0, 256, 700, dtype=np.uint8).tobytes()
PAYLOAD_POOLED = np.random.default_rng(33).integers(
    0, 256, 320, dtype=np.uint8).tobytes()

SHUFFLE_SEED = 20260829


def _key(cert: data.Certificate) -> data.CertKey:
    return (cert.page, cert.ty, cert.tx, cert.stream_id)


def _feed(state: close.CloseProgress, certs: list) -> close.CloseProgress:
    state.absorb({_key(cert): cert for cert in certs})
    return state


def _k_fixture(word_fn=None):
    k, code, rows, certs, row = _k_volume(PAYLOAD_K)
    if word_fn is None:
        return k, list(certs), row
    word = word_fn(k)
    crafted = [_cert(esi, "main", _bit(word, esi), np.zeros(SB, np.uint8))
               for esi in _systematic_esis(code, 4 * TILES_PER_PAGE)]
    return k, crafted, row


def _batch_rank_unique(certs: list, row) -> tuple[int, int]:
    streams = tuple(row.streams)
    idx_of = {s.stream_id: i for i, s in enumerate(streams)}
    equations: dict[int, int] = {}
    for cert in certs:
        counter = close._tile_counter(row, cert)
        index = (metadata.equation_index(counter, idx_of[cert.stream_id],
                                         len(streams))
                 if row.pooled_fountain else counter)
        equations[index] = int(cert.user_bits[0])
    max_index = (metadata.max_equation_index(len(streams))
                 if row.pooled_fountain else metadata.MAX_COUNTER)
    decoded = metadata.decode_metadata(equations, max_index)
    return decoded.rank, decoded.n_unique


def _family(name: str) -> tuple[list, object]:
    if name == "k":
        _k, certs, row = _k_fixture()
        return certs, row
    if name == "cmy8":
        _k, certs, row = _cmy8_v0_volume(PAYLOAD_CMY8)
        return list(certs), row
    _km, _kt, certs, row = _pooled_volume(PAYLOAD_POOLED)
    return list(certs), row


@pytest.mark.parametrize("family", ("cmy8", "k", "pooled"))
def test_state_equals_the_batch_oracle_at_every_prefix(family: str) -> None:
    certs, row = _family(family)
    rng = np.random.default_rng(SHUFFLE_SEED)
    order = rng.permutation(len(certs))
    shuffled = [certs[int(index)] for index in order]
    state = close.CloseProgress(row)
    for i, cert in enumerate(shuffled):
        _feed(state, [cert])
        prefix = shuffled[:i + 1]
        expected = close.close_count_progress(prefix, row)
        assert state.count_progress() == expected, (
            f"{family}: state diverged from the batch oracle at prefix "
            f"{i + 1}")
        assert state.ready == close.close_count_status(prefix, row)[0]
        rank, unique = _batch_rank_unique(prefix, row)
        assert state.metadata_rank == rank
        assert state.metadata_n_unique == unique
    assert state.ready and state.count_ready


def test_a_fresh_state_equals_the_grown_state_at_any_prefix() -> None:
    _k, certs, row = _k_fixture()
    rng = np.random.default_rng(7)
    order = rng.permutation(len(certs))
    shuffled = [certs[int(index)] for index in order]
    grown = close.CloseProgress(row)
    fed = 0
    for prefix_end in (1, 23, 24, 47, metadata.MIN_METADATA_EQUATIONS,
                       60, len(shuffled)):
        while fed < prefix_end:
            _feed(grown, [shuffled[fed]])
            fed += 1
        fresh = _feed(close.CloseProgress(row), shuffled[:prefix_end])
        assert (grown.ready, grown.metadata_rank, grown.metadata_n_unique,
                grown.count_progress()) == (
            fresh.ready, fresh.metadata_rank, fresh.metadata_n_unique,
            fresh.count_progress())


def test_k_is_known_at_rank_24_and_trusted_only_at_48_distinct() -> None:
    k, certs, row = _k_fixture()
    state = _feed(close.CloseProgress(row), certs[:47])
    assert state.metadata_rank == metadata.METADATA_BITS
    assert state.metadata_n_unique == 47 < metadata.MIN_METADATA_EQUATIONS
    assert state.count_progress() == (False, None, ())
    assert not state.ready
    _feed(state, certs[47:metadata.MIN_METADATA_EQUATIONS])
    assert state.metadata_n_unique == metadata.MIN_METADATA_EQUATIONS
    ready, k_sum, rows = state.count_progress()
    assert rows and k_sum == k
    version, k_total, gate_state = close.metadata_from_certificates(
        certs[:metadata.MIN_METADATA_EQUATIONS], row)
    assert (version, k_total, gate_state) == (0, k, "ready")


def test_an_opposite_duplicate_is_terminal_at_fold() -> None:
    certs, row = _family("cmy8")
    c_by_tile = {(cert.page, cert.ty, cert.tx): cert for cert in certs
                 if cert.stream_id == "C"}
    wrong = next(cert for cert in certs if cert.stream_id == "M"
                 and (cert.page, cert.ty, cert.tx) in c_by_tile)
    shared = c_by_tile[(wrong.page, wrong.ty, wrong.tx)]
    bits = wrong.user_bits.copy()
    bits[0] ^= 1
    flipped = replace(wrong, user_bits=bits)
    state = _feed(close.CloseProgress(row), [shared])
    with pytest.raises(data.IntegrityError,
                       match="conflicting certified metadata bits"):
        _feed(state, [flipped])


def test_a_contradiction_after_rank_24_is_terminal_not_a_revised_k() -> None:
    k, certs, row = _k_fixture()
    state = _feed(close.CloseProgress(row), certs[:60])
    assert state.count_progress()[1] == k
    liar_bits = certs[60].user_bits.copy()
    liar_bits[0] ^= 1
    liar = replace(certs[60], user_bits=liar_bits)
    with pytest.raises(data.IntegrityError, match="inconsistent"):
        _feed(state, [liar])
    assert state.count_progress()[1] == k


def test_a_malformed_word_is_terminal_only_at_the_trust_floor() -> None:
    _k, certs, row = _k_fixture(lambda k: _word(0, k) | (1 << 20))
    state = _feed(close.CloseProgress(row), certs[:47])
    assert state.metadata_rank == metadata.METADATA_BITS
    assert not state.ready
    _feed(state, [certs[47]])
    assert state.ready
    assert state.count_progress() == (True, None, ())
    assert close.close_count_status(certs[:48], row) == (True, None)


def test_an_unsupported_version_is_terminal_at_the_trust_floor() -> None:
    _k, certs, row = _k_fixture(lambda k: _word(1, k))
    state = _feed(close.CloseProgress(row),
                  certs[:metadata.MIN_METADATA_EQUATIONS])
    assert state.ready
    assert state.count_progress() == (True, None, ())
    assert close.close_count_status(
        certs[:metadata.MIN_METADATA_EQUATIONS], row) == (True, None)
    result = close.close_volume(
        certs[:metadata.MIN_METADATA_EQUATIONS], row)
    assert result.status == "unsupported"


def test_a_foreign_stream_is_refused_with_its_name() -> None:
    _k, certs, row = _k_fixture()
    ghost = replace(certs[0], stream_id="ghost")
    with pytest.raises(data.IntegrityError,
                       match="'ghost' is not declared by the printed row"):
        _feed(close.CloseProgress(row), [ghost])


def test_the_counting_rows_carry_the_block_counts() -> None:
    k, certs, row = _k_fixture()
    state = _feed(close.CloseProgress(row), certs[:50])
    ready, k_sum, rows = state.count_progress()
    assert not ready and k_sum == k
    assert rows
    assert all(block_row.stream_id is None for block_row in rows)
    assert all(block_row.rank is None and not block_row.solved
               for block_row in rows)
    assert sum(block_row.have for block_row in rows) == 50
    assert sum(block_row.needed for block_row in rows) == k
    assert sum(block_row.short for block_row in rows) == k - 50


def test_close_is_new_gates_reruns_on_unsolved_block_growth() -> None:
    k, certs, row = _k_fixture()
    assert len(certs) == k
    state = _feed(close.CloseProgress(row), certs[:k - 1])
    assert not state.count_ready
    assert state.close_is_new()
    open_result = state.close()
    assert open_result.status == "open"
    assert not state.close_is_new()
    _feed(state, [certs[k - 1]])
    assert state.close_is_new()
    solved_result = state.close()
    assert solved_result.status == "verified"
    word = _word(0, k)
    systematic = {close._tile_counter(row, cert) for cert in certs}
    surplus_esi = next(esi for esi in range(4 * TILES_PER_PAGE)
                       if esi not in systematic)
    surplus = _cert(surplus_esi, "main", _bit(word, surplus_esi),
                    np.zeros(SB, np.uint8))
    _feed(state, [surplus])
    assert not state.close_is_new()


def test_close_is_new_arms_on_the_metadata_terminal_transition() -> None:
    _k, certs, row = _k_fixture(lambda k: _word(0, k) | (1 << 20))
    state = _feed(close.CloseProgress(row), certs[:47])
    assert state.close().reason == "metadata incomplete"
    assert not state.close_is_new()
    _feed(state, [certs[47]])
    assert state.close_is_new()
