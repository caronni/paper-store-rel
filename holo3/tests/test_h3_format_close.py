from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

import numpy as np
import pytest

from holo3 import data
from holo3.format import close, fountain, identity, keystream, metadata

from holo3.tests import _h3_support

TILES_YX = (8, 8)
TILES_PER_PAGE = 64
SB = 40


@dataclass(frozen=True)
class Stream:
    stream_id: str
    symbol_bits: int
    fountain_aux: int | None


@dataclass(frozen=True)
class Row:
    seed: bytes
    tiles_yx: tuple[int, int]
    streams: tuple[Stream, ...]
    pooled_fountain: bool


def _envelope(payload: bytes) -> bytes:
    return (hashlib.sha256(payload).digest()
            + len(payload).to_bytes(4, "big") + payload)


def _source_rows(payload: bytes, n_rows: int, s_bits: int) -> np.ndarray:
    total = n_rows * s_bits
    buffer = np.zeros(-(-total // 8), dtype=np.uint8)
    envelope = np.frombuffer(_envelope(payload), dtype=np.uint8)
    buffer[:envelope.size] = envelope
    return np.unpackbits(buffer)[:total].reshape(n_rows, s_bits)


def _word(version: int, k: int) -> int:
    word = version & 1
    for i in range(metadata.K_BITS):
        word |= ((k >> (metadata.K_BITS - 1 - i)) & 1) << (1 + i)
    return word


def _bit(word: int, index: int,
         max_index: int = metadata.MAX_COUNTER) -> int:
    mask = int(metadata.coefficient_table(max_index)[index])
    return (mask & word).bit_count() & 1


def _cert(counter: int, stream_id: str, bit: int,
          symbol: np.ndarray) -> data.Certificate:
    page, local = divmod(int(counter), TILES_PER_PAGE)
    ty, tx = divmod(local, TILES_YX[1])
    return data.Certificate(
        page=page, ty=ty, tx=tx, stream_id=stream_id,
        user_bits=np.concatenate(([bit], symbol)).astype(np.uint8),
        source="test")


def _symbol(code: fountain.VolumeCode, source: np.ndarray,
            esi: int) -> np.ndarray:
    block, row = code.block_row_of(esi)
    offset = code.block_offsets[block]
    k_block = code.k_per_block[block]
    if row < k_block:
        return source[offset + row]
    if code.stream_id is None:
        coefficients = keystream.fountain_rows_bits(
            code.seed, block, [row], k_block)[0]
    else:
        coefficients = keystream.color_fountain_rows_bits(
            code.seed, code.stream_aux, block, [row], k_block)[0]
    rows = source[offset:offset + k_block][coefficients.astype(bool)]
    if rows.size == 0:
        return np.zeros(code.s_bits, dtype=np.uint8)
    return np.bitwise_xor.reduce(rows, axis=0).astype(np.uint8)


def _systematic_esis(code: fountain.VolumeCode, horizon: int) -> list[int]:
    out = []
    for esi in range(horizon):
        block, row = code.block_row_of(esi)
        if row < code.k_per_block[block]:
            out.append(esi)
    return out


def _k_volume(payload: bytes, seed: bytes = b"h3/close/K",
              k_override: int | None = None,
              source: np.ndarray | None = None):
    k = k_override or close.source_symbol_count(len(payload), SB)
    rows = _source_rows(payload, k, SB) if source is None else source
    code = fountain.VolumeCode(k, SB, seed, TILES_PER_PAGE)
    word = _word(0, k)
    certs = []
    for esi in _systematic_esis(code, 4 * TILES_PER_PAGE):
        block, row = code.block_row_of(esi)
        certs.append(_cert(esi, "main", _bit(word, esi),
                           rows[code.block_offsets[block] + row]))
    row_fact = Row(seed, TILES_YX, (Stream("main", SB, None),), False)
    return k, code, rows, certs, row_fact


def test_envelope_constants_and_wire_layout():
    assert close.SHA_BYTES == 32
    assert close.LEN_BYTES == 4
    assert close.OVERHEAD_BYTES == 36
    payload = bytes(range(11))
    wire = _envelope(payload)
    assert wire[:32] == hashlib.sha256(payload).digest()
    assert int.from_bytes(wire[32:36], "big") == 11
    assert wire[36:] == payload
    assert close.try_unwrap(wire) == payload


def test_trailing_padding_is_ignored_and_the_declared_length_rules():
    payload = b"holo3 envelope"
    wire = _envelope(payload) + bytes(64)
    assert close.try_unwrap(wire) == payload
    noisy = bytearray(_envelope(payload))
    noisy += b"\x01" * 8
    assert close.try_unwrap(bytes(noisy)) == payload


@pytest.mark.parametrize("mutation", [
    "sha", "data", "short", "length-beyond-stream"])
def test_the_four_unwrap_refusals(mutation: str):
    payload = b"holo3 envelope refusal"
    wire = bytearray(_envelope(payload))
    if mutation == "sha":
        wire[3] ^= 0x01
    elif mutation == "data":
        wire[40] ^= 0x01
    elif mutation == "short":
        wire = bytearray(_envelope(payload)[:35])
    else:
        wire[32:36] = (len(payload) + 1).to_bytes(4, "big")
    assert close.try_unwrap(bytes(wire)) is None


@pytest.mark.parametrize("payload_len,symbol_bits,k", [
    (0, 40, 8), (1, 40, 8), (4, 40, 8), (300, 40, 68),
    (465580, 2747, 1356), (700, 120, 50),
])
def test_source_symbol_count_is_the_canonical_minimum(
        payload_len: int, symbol_bits: int, k: int):
    assert close.source_symbol_count(payload_len, symbol_bits) == k
    assert k * symbol_bits >= (36 + payload_len) * 8
    assert (k - 1) * symbol_bits < (36 + payload_len) * 8


@pytest.mark.parametrize("ref,stream_index,aux", [
    ("L:c2-r0700@3392x2368", 0, None),
    ("L:c3-r0550@2240x1536", 0, None),
    ("L:c2-cmy7-p120-v0@3328x2304", 0, 0),
    ("L:c2-cmy8-p120-v0@3328x2304", 0, 1),
    ("L:c2-cmy8-p120-v0@3328x2304", 1, 2),
    ("L:c2-cmy8-p120-v0@3328x2304", 2, 3),
])
def test_volume_code_dispatches_on_is_none_not_on_a_falsy_aux(
        ref: str, stream_index: int, aux: int | None):
    row = identity.resolve_format_ref(ref)
    stream = row.streams[stream_index]
    assert stream.fountain_aux == aux
    code = close._volume_code(row, stream, 4096)
    if aux is None:
        assert code.stream_id is None
        assert code.fountain_row_domain == keystream.DOMAIN_FOUNTAIN_ROW
        assert code.stream_aux == 0
    else:
        assert code.stream_id == stream.stream_id
        assert code.fountain_row_domain == \
            keystream.DOMAIN_COLOR_FOUNTAIN_ROW
        assert code.stream_aux == aux


def test_a_zero_instead_of_none_would_reroute_k_through_the_colour_domain():
    row = identity.resolve_format_ref("L:c2-r0700@3392x2368")
    stream = row.streams[0]
    correct = close._volume_code(row, stream, 40000)
    mutant = close._volume_code(
        row, Stream(stream.stream_id, stream.symbol_bits, 0), 40000)
    assert correct.n_blocks == 3
    assert correct.fountain_row_domain != mutant.fountain_row_domain
    assert not np.array_equal(correct.page_assignment(0)[0],
                              mutant.page_assignment(0)[0])


def test_pooled_rows_use_one_unattributed_block_space():
    row = identity.resolve_format_ref("L:c2-cmy8-p120-v1@3392x2368")
    assert row.pooled_fountain
    code = close._pooled_volume_code(row, 3 * 1000)
    assert code.n_streams == 3
    assert code.stream_id is None
    assert code.symbols_per_page == 1961 * 3


def test_k_volume_closes_verified_and_byte_exact():
    payload = np.random.default_rng(7).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    k, _code, _rows, certs, row = _k_volume(payload)
    result = close.close_volume(certs, row)
    assert result.status == "verified"
    assert result.payload == payload
    assert result.k_total == k
    assert result.metadata_version == 0
    assert result.reason is None
    assert result.symbols_used == len(certs)
    assert all(block.solved and block.stream_id is None
               for block in result.blocks)
    assert close.close_count_ready(certs, row)


def test_a_single_colour_stream_labels_its_block_space():
    payload = np.random.default_rng(10).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    seed = b"h3/close/cmy7"
    k = close.source_symbol_count(len(payload), SB)
    rows = _source_rows(payload, k, SB)
    code = fountain.VolumeCode(k, SB, seed, TILES_PER_PAGE,
                               stream_id="main", fountain_aux=0)
    word = _word(0, k)
    certs = []
    for esi in _systematic_esis(code, 4 * TILES_PER_PAGE):
        block, row = code.block_row_of(esi)
        certs.append(_cert(esi, "main", _bit(word, esi),
                           rows[code.block_offsets[block] + row]))
    row_fact = Row(seed, TILES_YX, (Stream("main", SB, 0),), False)
    result = close.close_volume(certs, row_fact)
    assert result.status == "verified" and result.payload == payload
    assert all(block.stream_id == "main" for block in result.blocks)


def _cmy8_v0_volume(payload: bytes, seed: bytes = b"h3/close/cmy8-v0"):
    k = close.source_symbol_count(len(payload), 3 * SB)
    all_rows = _source_rows(payload, 3 * k, SB)
    per_stream = {"C": all_rows[:k], "M": all_rows[k:2 * k],
                  "Y": all_rows[2 * k:]}
    word = _word(0, k)
    certs = []
    for stream_id, aux in (("C", 1), ("M", 2), ("Y", 3)):
        code = fountain.VolumeCode(k, SB, seed, TILES_PER_PAGE,
                                   stream_id=stream_id, fountain_aux=aux)
        for esi in _systematic_esis(code, 4 * TILES_PER_PAGE):
            block, row = code.block_row_of(esi)
            certs.append(_cert(
                esi, stream_id, _bit(word, esi),
                per_stream[stream_id][code.block_offsets[block] + row]))
    row_fact = Row(seed, TILES_YX,
                   (Stream("C", SB, 1), Stream("M", SB, 2),
                    Stream("Y", SB, 3)), False)
    return k, certs, row_fact


def test_three_independent_streams_close_verified():
    payload = np.random.default_rng(11).integers(
        0, 256, 700, dtype=np.uint8).tobytes()
    k, certs, row = _cmy8_v0_volume(payload)
    result = close.close_volume(certs, row)
    assert result.status == "verified"
    assert result.payload == payload
    assert result.k_total == k
    assert sorted({block.stream_id for block in result.blocks}) == \
        ["C", "M", "Y"]
    assert close.close_count_ready(certs, row)


def test_one_dead_stream_leaves_the_volume_open_and_names_it():
    payload = np.random.default_rng(12).integers(
        0, 256, 700, dtype=np.uint8).tobytes()
    _k, certs, row = _cmy8_v0_volume(payload)
    without_y = [cert for cert in certs if cert.stream_id != "Y"]
    result = close.close_volume(without_y, row)
    assert result.status == "open"
    assert result.payload is None
    assert "streams ('Y',)" in (result.reason or "")
    assert not close.close_count_ready(without_y, row)


def _pooled_volume(payload: bytes, seed: bytes = b"h3/close/pooled",
                   n_streams: int = 3):
    k_meta = close.source_symbol_count(len(payload), n_streams * SB)
    k_total = n_streams * k_meta
    rows = _source_rows(payload, k_total, SB)
    code = fountain.VolumeCode(k_total, SB, seed, TILES_PER_PAGE,
                               n_streams=n_streams)
    word = _word(0, k_meta)
    max_index = metadata.max_equation_index(n_streams)
    stream_of = {0: "C", 1: "M", 2: "Y"}
    certs = []
    for esi in _systematic_esis(code, 4 * TILES_PER_PAGE * n_streams):
        block, row = code.block_row_of(esi)
        counter, index = divmod(esi, n_streams)
        certs.append(_cert(counter, stream_of[index],
                           _bit(word, esi, max_index),
                           rows[code.block_offsets[block] + row]))
    row_fact = Row(seed, TILES_YX,
                   (Stream("C", SB, 1), Stream("M", SB, 2),
                    Stream("Y", SB, 3)), True)
    return k_meta, k_total, certs, row_fact


def test_pooled_volume_closes_verified_with_one_block_space():
    payload = np.random.default_rng(13).integers(
        0, 256, 320, dtype=np.uint8).tobytes()
    k_meta, k_total, certs, row = _pooled_volume(payload)
    result = close.close_volume(certs, row)
    assert result.status == "verified"
    assert result.payload == payload
    assert result.k_total == k_total == 3 * k_meta
    assert all(block.stream_id is None for block in result.blocks)
    assert close.close_count_ready(certs, row)


def test_a_pooled_volume_survives_a_dead_plane():
    payload = np.random.default_rng(14).integers(
        0, 256, 864, dtype=np.uint8).tobytes()
    seed = b"h3/close/pooled-dead-y"
    k_meta = close.source_symbol_count(len(payload), 3 * SB)
    k_total = 3 * k_meta
    rows = _source_rows(payload, k_total, SB)
    code = fountain.VolumeCode(k_total, SB, seed, TILES_PER_PAGE,
                               n_streams=3)
    word = _word(0, k_meta)
    max_index = metadata.max_equation_index(3)
    stream_of = {0: "C", 1: "M", 2: "Y"}
    certs = []
    for esi in range(3 * TILES_PER_PAGE * 3):
        counter, index = divmod(esi, 3)
        certs.append(_cert(counter, stream_of[index],
                           _bit(word, esi, max_index),
                           _symbol(code, rows, esi)))
    row_fact = Row(seed, TILES_YX,
                   (Stream("C", SB, 1), Stream("M", SB, 2),
                    Stream("Y", SB, 3)), True)
    assert close.close_volume(certs, row_fact).payload == payload
    alive = [cert for cert in certs if cert.stream_id != "Y"]
    assert 0 < len(alive) < len(certs)
    result = close.close_volume(alive, row_fact)
    assert result.status == "verified"
    assert result.payload == payload
    assert result.k_total == k_total
    assert close.close_count_ready(alive, row_fact)


def test_metadata_from_certificates_honours_the_forty_eight_floor():
    payload = np.random.default_rng(15).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    k, _code, _rows, certs, row = _k_volume(payload)
    version, k_total, state = close.metadata_from_certificates(certs, row)
    assert (version, k_total, state) == (0, k, "ready")
    starved = close.metadata_from_certificates(certs[:47], row)
    assert starved == (0, None, "incomplete")
    at_the_bar = close.metadata_from_certificates(certs[:48], row)
    assert at_the_bar == (0, k, "ready")


def test_conflicting_metadata_bits_at_one_index_raise():
    payload = np.random.default_rng(16).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    _k, _code, _rows, certs, row = _k_volume(payload)
    flipped = certs[5].user_bits.copy()
    flipped[0] ^= 1
    conflicting = list(certs) + [replace(certs[5], user_bits=flipped)]
    with pytest.raises(data.IntegrityError,
                       match="conflicting certified metadata bits"):
        close.metadata_from_certificates(conflicting, row)
    result = close.close_volume(conflicting, row)
    assert result.status == "integrity_failure"
    assert "metadata integrity failure" in (result.reason or "")


def test_metadata_starvation_reports_open_not_a_guess():
    payload = np.random.default_rng(17).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    _k, _code, _rows, certs, row = _k_volume(payload)
    result = close.close_volume(certs[:30], row)
    assert result.status == "open"
    assert result.reason == "metadata incomplete"
    assert result.payload is None and result.k_total is None
    assert not close.close_count_ready(certs[:30], row)


def test_a_truncated_volume_reports_its_exact_shortfall():
    payload = np.random.default_rng(18).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    k, _code, _rows, certs, row = _k_volume(payload)
    truncated = certs[:50]
    result = close.close_volume(truncated, row)
    assert result.status == "open"
    assert result.k_total == k
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert not block.solved and block.have == 50 and block.needed == k
    assert block.rank is None and block.short == k - 50
    assert f"at least {k - 50} additional symbols" in result.reason
    assert not close.close_count_ready(truncated, row)


def test_an_unsupported_metadata_version_is_its_own_status():
    payload = np.random.default_rng(19).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    k, code, rows, _certs, row = _k_volume(payload)
    word = _word(1, k)
    certs = [
        _cert(esi, "main", _bit(word, esi),
              rows[code.block_offsets[code.block_row_of(esi)[0]]
                   + code.block_row_of(esi)[1]])
        for esi in _systematic_esis(code, 4 * TILES_PER_PAGE)]
    result = close.close_volume(certs, row)
    assert result.status == "unsupported"
    assert result.metadata_version == 1
    assert "unsupported metadata version 1" in (result.reason or "")
    assert result.payload is None


def test_a_malformed_metadata_word_is_an_integrity_failure():
    payload = np.random.default_rng(20).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    k, code, rows, _certs, row = _k_volume(payload)
    word = _word(0, k) | (1 << 20)
    certs = [
        _cert(esi, "main", _bit(word, esi),
              rows[code.block_offsets[code.block_row_of(esi)[0]]
                   + code.block_row_of(esi)[1]])
        for esi in _systematic_esis(code, 4 * TILES_PER_PAGE)]
    result = close.close_volume(certs, row)
    assert result.status == "integrity_failure"
    assert result.reason == "metadata malformed"


def test_a_corrupted_symbol_fails_the_envelope_sha_gate():
    payload = np.random.default_rng(21).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    _k, _code, _rows, certs, row = _k_volume(payload)
    damaged = list(certs)
    bits = damaged[5].user_bits.copy()
    bits[3] ^= 1
    damaged[5] = replace(damaged[5], user_bits=bits)
    result = close.close_volume(damaged, row)
    assert result.status == "integrity_failure"
    assert "envelope verification failed" in (result.reason or "")
    assert result.payload is None
    assert close.close_count_ready(damaged, row)


def test_a_noncanonical_k_fails_its_own_gate():
    payload = np.random.default_rng(22).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    canonical = close.source_symbol_count(len(payload), SB)
    rows = _source_rows(payload, canonical + 1, SB)
    _k, _code, _rows, certs, row = _k_volume(
        payload, k_override=canonical + 1, source=rows)
    result = close.close_volume(certs, row)
    assert result.k_total == canonical + 1
    assert result.status == "integrity_failure"
    assert "envelope verification failed" in (result.reason or "")


def test_nonzero_padding_fails_its_own_gate():
    payload = np.random.default_rng(23).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    k = close.source_symbol_count(len(payload), SB)
    rows = _source_rows(payload, k, SB)
    used_bits = (close.OVERHEAD_BYTES + len(payload)) * 8
    assert used_bits < k * SB
    row_index, local = divmod(used_bits, SB)
    padded = rows.copy()
    assert padded[row_index, local] == 0
    padded[row_index, local] = 1
    _k, _code, _rows, certs, row = _k_volume(payload, source=padded)
    result = close.close_volume(certs, row)
    assert result.status == "integrity_failure"
    assert "noncanonical K, or nonzero padding" in (result.reason or "")
    _k2, _c2, _r2, clean_certs, clean_row = _k_volume(payload, source=rows)
    assert close.close_volume(clean_certs, clean_row).status == "verified"


def test_a_conflicting_certified_symbol_is_fatal_never_voted():
    payload = np.random.default_rng(24).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    _k, _code, _rows, certs, row = _k_volume(payload)
    bits = certs[0].user_bits.copy()
    bits[7] ^= 1
    duplicate = replace(certs[0], user_bits=bits)
    result = close.close_volume(list(certs) + [duplicate], row)
    assert result.status == "integrity_failure"
    assert "certified-symbol integrity failure" in (result.reason or "")


def test_an_identical_duplicate_is_a_no_op():
    payload = np.random.default_rng(25).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    _k, _code, _rows, certs, row = _k_volume(payload)
    result = close.close_volume(list(certs) + [certs[0]], row)
    assert result.status == "verified"
    assert result.payload == payload
    assert result.symbols_used == len(certs)


def _scenarios():
    payload = np.random.default_rng(26).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    k, _code, _rows, certs, row = _k_volume(payload)
    damaged = list(certs)
    bits = damaged[5].user_bits.copy()
    bits[3] ^= 1
    damaged[5] = replace(damaged[5], user_bits=bits)
    return {
        "verified": (certs, row),
        "truncated": (certs[:50], row),
        "starved": (certs[:30], row),
        "corrupted": (damaged, row),
        "surplus": (list(certs) + [certs[0]], row),
    }, k


@pytest.mark.parametrize("name", sorted(_scenarios()[0]))
def test_the_count_gate_agrees_with_the_full_close(name: str):
    scenarios, _k = _scenarios()
    certs, row = scenarios[name]
    ready, counts = close.close_count_status(certs, row)
    result = close.close_volume(certs, row)
    assert ready == (result.status != "open")
    assert close.close_count_ready(certs, row) is ready
    if counts is None:
        assert result.status in ("open", "integrity_failure", "unsupported")
    else:
        assert set(counts) == {("main", 0)}


def test_the_verified_stop_is_total_or_nothing():
    payload = np.random.default_rng(27).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    k, _code, _rows, certs, row = _k_volume(payload)
    for n_certs in (k - 1, k):
        result = close.close_volume(certs[:n_certs], row)
        if n_certs < k:
            assert result.status == "open" and result.payload is None
        else:
            assert result.status == "verified"
            assert result.payload == payload


def test_close_result_shape_is_frozen():
    payload = np.random.default_rng(28).integers(
        0, 256, 300, dtype=np.uint8).tobytes()
    _k, _code, _rows, certs, row = _k_volume(payload)
    result = close.close_volume(certs, row)
    assert isinstance(result, close.CloseResult)
    _h3_support.assert_golden(
        "CloseResult fields", tuple(result.__dataclass_fields__),
        ("status", "payload", "k_total", "blocks", "symbols_used",
         "reason", "metadata_version"))
    assert isinstance(result.blocks[0], data.CloseBlockRow)
    _h3_support.assert_golden(
        "CloseBlockRow fields",
        tuple(data.CloseBlockRow.__dataclass_fields__),
        ("stream_id", "block", "have", "needed", "rank", "solved",
         "short", "groups_open", "n_groups"))
