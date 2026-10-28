"""Carry-equivalence oracle: holo2's verified close == holo's, exactly.

WORKPLAN H2b.  ``holo2/src/holo2/{keystream,metadata,envelope,streamset,
fountain,fountain_close}.py`` are copy-and-adapt carries of
``src/holo/{core,format,receive}``; the firewall forbids importing the
original, so equivalence is pinned HERE, outside the holo2 tree, where
both packages may be imported.

The fixtures come from the REAL generator: ``plan_volume`` ->
``source_packed_for`` -> ``VolumeCode.encode_symbols`` ->
``compose_page_cells``, and the certified content is then read back by
the REAL v1 tile decode (``attempt_k_tile`` on the clean composed cells),
so what the close consumes is what a certified tile actually carries —
not a hand-built approximation of it.  ``test_gen_truth_is_the_certified
_content`` pins that binding before anything else compares closes.

The bar is DESIGN L9: canonical envelope + SHA-256 + unique minimal K +
zero source padding, total or nothing.  Byte-exact recovered payload,
identical open/shortfall shape, identical refusals.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

import numpy as np
import pytest

from holo.core import fountain as h_fountain
from holo.format.resolve import resolve_format_ref as h_resolve_format_ref
from holo.format import metadata as h_metadata
from holo.format import streamset as h_streamset
from holo.format.descriptor import FormatSpec
from holo.gen.color_compose import compose_color_page_cells  # noqa: F401
from holo.gen.compose import compose_page_cells
from holo.gen.emit import source_packed_for
from holo.gen.plan import plan_volume
from holo.receive import fountain_close as h_close
from holo.receive.evidence import AttemptStage, AttemptState
from holo.receive.payload import attempt_k_tile
from holo.receive.records import certificate_for_close
from holo.receive.types import CloseStatus as HoloDurableStatus

from holo2.format import close_spec as h2_close_spec
from holo2.format import family as h2_family
from holo2.format import fountain as h2_fountain
from holo2.format import fountain_close as h2_close
from holo2.format import metadata as h2_metadata
from holo2.format import streamset as h2_streamset

_SOURCE_SHA = hashlib.sha256(b"holo2-h2b-oracle-source").hexdigest()


# --------------------------------------------------------------- helpers

def close_spec_for(spec: FormatSpec) -> h2_close_spec.CloseSpec:
    """The holo2 close's view of one holo ``FormatSpec`` (H2c will build
    this from the session's format row; here it is derived so the two
    sides provably describe the same printed format).

    WP-1.1 (2026-08-22): the family crosses BY VALUE, not by identity —
    the two enums are separate objects in two trees, and their values are
    the format-frozen evidence-block kinds (``holo/format/profiles.py:32-41``).
    Mapping through the string is therefore the mapping the printed
    record itself defines; a value that did not round-trip would be a
    format fork, and ``Family(...)`` raises on it here.
    """
    return h2_close_spec.CloseSpec(
        codec_id=spec.codec_id,
        seed=spec.seed,
        tiles_yx=spec.layout.tiles_yx,
        stream_profiles=tuple(
            h2_close_spec.CloseStreamProfile(
                profile.stream_id, profile.symbol_bits, profile.fountain_aux)
            for profile in spec.stream_profiles
        ),
        spec_id=spec.spec_id,
        # C2 (2026-08-22): the OUTER-code axis crosses too, and it is a
        # separate field on purpose (P13) — pooling is a family fact in
        # the v2 space and is NOT one in v1, where the printed -v0 CMY8
        # sheets are unpooled and their -v1 twins pooled with the
        # identical tile codec. Derived from the coding rather than the
        # family, so this stays total when a pooled fixture arrives.
        pooled_fountain=spec.coding.pooled_fountain,
        codec_family=h2_family.Family(spec.codec_family.value),
    )


def mirror(cert: h_close.CertifiedStreamSymbol) -> h2_close.CertifiedStreamSymbol:
    """The same certified equation as a holo2 close input."""
    return h2_close.CertifiedStreamSymbol(
        counter=cert.counter, page=cert.page, ty=cert.ty, tx=cert.tx,
        stream_id=cert.stream_id, symbol=cert.symbol,
        metadata_bit=cert.metadata_bit,
    )


def make_pair(spec: FormatSpec, counter: int, stream_id: str,
              symbol: np.ndarray, metadata_bit: int):
    """One certified equation on both sides, from generator truth."""
    tiles_y, tiles_x = spec.layout.tiles_yx
    page, rem = divmod(counter, tiles_y * tiles_x)
    ty, tx = divmod(rem, tiles_x)
    holo_cert = h_close.CertifiedStreamSymbol(
        counter=counter, page=page, ty=ty, tx=tx, stream_id=stream_id,
        symbol=symbol, metadata_bit=int(metadata_bit))
    return holo_cert, mirror(holo_cert)


def block_rows(result) -> tuple[tuple, ...]:
    return tuple(
        (row.block, row.needed, row.have, row.rank, row.solved,
         row.stream_id, row.rank_shortfall)
        for row in result.blocks
    )


def assert_same_close(left, right) -> None:
    """Every observable of one numerical close, on both sides."""
    assert left.status == right.status
    assert left.payload == right.payload
    assert left.k_total == right.k_total
    assert left.symbols_used == right.symbols_used
    assert left.metadata_version == right.metadata_version
    assert left.reason == right.reason
    assert left.verified == right.verified
    assert block_rows(left) == block_rows(right)
    assert left.diagnostics == right.diagnostics
    assert tuple(
        (row.stream_id, row.counter, row.page, row.ty, row.tx)
        for row in left.surplus_inconsistencies
    ) == tuple(
        (row.stream_id, row.counter, row.page, row.ty, row.tx)
        for row in right.surplus_inconsistencies
    )


def assert_same_metadata(certs, spec, h2certs, h2spec) -> None:
    """Bits, rank and trust decision, or the identical refusal."""
    try:
        left = h_close.metadata_from_certificates(certs, spec)
    except h_close.MetadataIntegrityError as exc:
        with pytest.raises(h2_close.MetadataIntegrityError) as caught:
            h2_close.metadata_from_certificates(h2certs, h2spec)
        assert str(caught.value) == str(exc)
        assert caught.value.diagnostics == exc.diagnostics
        return
    right = h2_close.metadata_from_certificates(h2certs, h2spec)
    assert left[0] == right[0]          # version
    assert left[1] == right[1]          # K
    assert left[2] == right[2]          # every diagnostic, incl. rank/state


# ---------------------------------------------------------------- fixture

@dataclass(frozen=True)
class KFixture:
    spec: FormatSpec
    h2spec: h2_close_spec.CloseSpec
    payload: bytes
    k_total: int
    symbols: np.ndarray
    metadata_bits: np.ndarray
    certs: tuple
    h2certs: tuple
    corrupted_zero: tuple


N_CERTS = 100


@pytest.fixture(scope="module")
def k_fixture() -> KFixture:
    # THE IDENTITY, not a pseudo-printer (C4, 2026-08-22, RULINGS G5).
    # ``make_spec("c3-r0550", "default")`` resolved a printer/media
    # bundle to A4 at 6 mm and DERIVED 35x24 tiles; that geometry is the
    # printed fossil ``c3-r0550@2240x1536`` (e033 A2 and G), so the
    # string names it directly.  Byte-identical spec — same seed, same
    # layout, same ``tiles_per_page`` — which is why ``k_total == 61``
    # below is untouched.
    spec = h_resolve_format_ref("L:c3-r0550@2240x1536")
    payload = hashlib.sha256(b"holo2-h2b-oracle").digest() * 500
    plan = plan_volume(spec, len(payload), 0.75)
    assert plan.k_total == 61 and plan.n_pages == 1

    source = source_packed_for(payload, plan)
    code = h_fountain.VolumeCode(
        plan.k_total, plan.symbol_bits, spec.seed,
        tiles_per_page=spec.tiles_per_page)
    symbols = code.encode_symbols(
        source, np.arange(spec.tiles_per_page, dtype=np.int64))
    clean = compose_page_cells(spec, 0, symbols, plan.k_total)
    counters = np.arange(spec.tiles_per_page, dtype=np.int64)
    metadata_bits = h_metadata.tile_bits(
        h_metadata.encode_metadata(0, plan.k_total), counters)

    def certificate(field: np.ndarray, index: int, tag: str):
        _, tiles_x = spec.layout.tiles_yx
        ty, tx = divmod(index, tiles_x)
        tile = field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
        record, certified = attempt_k_tile(
            (tile.astype(np.float64) * 2.0 - 1.0) * 5.0,
            spec, (0, ty, tx), AttemptStage.SCAN,
            source_sha256=_SOURCE_SHA, lane_id="h2b-oracle",
            component_block_ids=(
                hashlib.sha256(tag.encode("ascii")).hexdigest(),))
        assert record.state is AttemptState.CERTIFIED
        assert certified is not None
        return certificate_for_close(certified, spec)

    certs = tuple(
        certificate(clean, index, f"clean-{index}")
        for index in range(N_CERTS))

    # ESI 0 is systematic here: recompose it after flipping one source bit,
    # so the certificate is individually valid but the recovered envelope is
    # wrong when it replaces the clean ESI 0 with no redundant equation.
    corrupted_symbols = symbols.copy()
    corrupted_symbols[0, 0] ^= np.uint8(1)
    corrupted_page = compose_page_cells(
        spec, 0, corrupted_symbols, plan.k_total)
    corrupted = certificate(corrupted_page, 0, "corrupted-0")
    assert not np.array_equal(corrupted.symbol, certs[0].symbol)

    return KFixture(
        spec=spec, h2spec=close_spec_for(spec), payload=payload,
        k_total=plan.k_total, symbols=symbols, metadata_bits=metadata_bits,
        certs=certs, h2certs=tuple(mirror(cert) for cert in certs),
        corrupted_zero=(corrupted, mirror(corrupted)),
    )


# ------------------------------------------------------- truth binding

def test_gen_truth_is_the_certified_content(k_fixture: KFixture) -> None:
    """What a real certified tile carries == the generator's own truth."""
    for index, cert in enumerate(k_fixture.certs):
        assert cert.counter == index
        assert cert.stream_id == "main"
        assert cert.metadata_bit == int(k_fixture.metadata_bits[index])
        assert np.array_equal(cert.symbol, k_fixture.symbols[index])


def test_carried_format_constants_match() -> None:
    """The frozen format surface the close stands on, side by side."""
    assert h2_metadata.METADATA_BITS == h_metadata.METADATA_BITS
    assert h2_metadata.K_BITS == h_metadata.K_BITS
    assert (h2_metadata.MIN_METADATA_EQUATIONS
            == h_metadata.MIN_METADATA_EQUATIONS == 48)
    assert h2_metadata.LFSR_FEEDBACK == h_metadata.LFSR_FEEDBACK
    assert h2_metadata.LFSR_INITIAL_STATE == h_metadata.LFSR_INITIAL_STATE
    assert h2_fountain.BLOCK_K_MAX == h_fountain.BLOCK_K_MAX
    assert h2_fountain.FOUNTAIN_VERSION == h_fountain.FOUNTAIN_VERSION
    assert (h2_close.SUPPORTED_METADATA_VERSIONS
            == h_close.SUPPORTED_METADATA_VERSIONS)
    counters = np.arange(0, 4096, dtype=np.int64)
    assert np.array_equal(h2_metadata.coefficient_masks(counters),
                          h_metadata.coefficient_masks(counters))


# ----------------------------------------------------- (a) metadata solve

@pytest.mark.parametrize("n", [0, 1, 24, 30, 47, 48, 49, 61, N_CERTS])
def test_metadata_solve_agrees_on_subsets(k_fixture: KFixture, n: int) -> None:
    """Full and degraded: same word, same rank, same trust decision.

    Below 48 distinct counters the word is algebraically recoverable at
    n >= 24 but must still be REFUSED (DESIGN L9); both sides refuse with
    the same reason and the same shortfall.
    """
    assert_same_metadata(k_fixture.certs[:n], k_fixture.spec,
                         k_fixture.h2certs[:n], k_fixture.h2spec)
    left = h_close.metadata_from_certificates(k_fixture.certs[:n],
                                              k_fixture.spec)
    if n < h_metadata.MIN_METADATA_EQUATIONS:
        assert left[1] is None and left[2]["ok"] is False
    else:
        assert left[1] == k_fixture.k_total


def test_metadata_solve_agrees_on_scattered_subset(
        k_fixture: KFixture) -> None:
    """Non-contiguous counters (the real receiver's arrival pattern)."""
    picked = tuple(k_fixture.certs[index] for index in range(1, N_CERTS, 2))
    assert len(picked) == 50
    assert_same_metadata(picked, k_fixture.spec,
                         tuple(mirror(cert) for cert in picked),
                         k_fixture.h2spec)


def test_metadata_inconsistency_agrees(k_fixture: KFixture) -> None:
    """One flipped certified bit is integrity-fatal on both sides."""
    flipped = h_close.CertifiedStreamSymbol(
        counter=k_fixture.certs[7].counter, page=0,
        ty=k_fixture.certs[7].ty, tx=k_fixture.certs[7].tx,
        stream_id="main", symbol=k_fixture.certs[7].symbol,
        metadata_bit=1 - k_fixture.certs[7].metadata_bit)
    certs = k_fixture.certs[:7] + (flipped,) + k_fixture.certs[8:]
    assert_same_metadata(certs, k_fixture.spec,
                         tuple(mirror(cert) for cert in certs),
                         k_fixture.h2spec)
    with pytest.raises(h2_close.MetadataIntegrityError):
        h2_close.metadata_from_certificates(
            tuple(mirror(cert) for cert in certs), k_fixture.h2spec)


def test_metadata_duplicate_disagreement_agrees(
        k_fixture: KFixture) -> None:
    """Two opposite bits at ONE counter: same refusal, same diagnostics."""
    zero = k_fixture.certs[0]
    twin = h_close.CertifiedStreamSymbol(
        counter=zero.counter, page=0, ty=zero.ty, tx=zero.tx,
        stream_id="main", symbol=zero.symbol,
        metadata_bit=1 - zero.metadata_bit)
    certs = k_fixture.certs + (twin,)
    assert_same_metadata(certs, k_fixture.spec,
                         tuple(mirror(cert) for cert in certs),
                         k_fixture.h2spec)


# ------------------------------------------------------ (b) close_volume

def test_close_verified_agrees_byte_exact(k_fixture: KFixture) -> None:
    """The complete set: verified stop, byte-identical recovered payload."""
    left = h_close.close_volume(k_fixture.certs, k_fixture.spec)
    right = h2_close.close_volume(k_fixture.h2certs, k_fixture.h2spec)
    assert left.verified and right.verified
    assert right.payload == k_fixture.payload   # bytes emitted == recovered
    assert_same_close(left, right)
    assert right.k_total == k_fixture.k_total


def test_close_repair_path_agrees_byte_exact(k_fixture: KFixture) -> None:
    """Dropping the first 20 ESIs forces the GE repair path on both sides."""
    certs = k_fixture.certs[20:N_CERTS]
    left = h_close.close_volume(certs, k_fixture.spec)
    right = h2_close.close_volume(
        tuple(mirror(cert) for cert in certs), k_fixture.h2spec)
    assert right.verified and right.payload == k_fixture.payload
    assert_same_close(left, right)


@pytest.mark.parametrize("n", [48, 55, 60])
def test_close_open_shape_agrees(k_fixture: KFixture, n: int) -> None:
    """Metadata trusted, rank short: identical open shape and reason."""
    certs = k_fixture.certs[:n]
    left = h_close.close_volume(certs, k_fixture.spec)
    right = h2_close.close_volume(
        tuple(mirror(cert) for cert in certs), k_fixture.h2spec)
    assert left.status == "open" and left.payload is None
    assert_same_close(left, right)


@pytest.mark.parametrize("n", [0, 24, 47])
def test_close_below_metadata_floor_agrees(k_fixture: KFixture,
                                           n: int) -> None:
    """Below the 48-counter floor the close is open with no K at all."""
    certs = k_fixture.certs[:n]
    left = h_close.close_volume(certs, k_fixture.spec)
    right = h2_close.close_volume(
        tuple(mirror(cert) for cert in certs), k_fixture.h2spec)
    assert left.status == "open" and left.k_total is None
    assert_same_close(left, right)


def test_close_wrong_bits_fail_the_sha_on_both_sides(
        k_fixture: KFixture) -> None:
    """Rank complete, digest wrong => integrity failure, never partial."""
    corrupted, h2corrupted = k_fixture.corrupted_zero
    certs = (corrupted,) + k_fixture.certs[1:61]
    left = h_close.close_volume(certs, k_fixture.spec)
    right = h2_close.close_volume(
        (h2corrupted,) + k_fixture.h2certs[1:61], k_fixture.h2spec)
    assert left.status == "integrity_failure"
    assert left.payload is None and right.payload is None
    assert "SHA-256" in (right.reason or "")
    assert_same_close(left, right)


def test_close_conflicting_symbols_agree(k_fixture: KFixture) -> None:
    """Two different certified values at one ESI: fatal on both sides."""
    zero = k_fixture.certs[0]
    conflicting = h_close.CertifiedStreamSymbol(
        counter=zero.counter, page=0, ty=zero.ty, tx=zero.tx,
        stream_id="main", symbol=(zero.symbol ^ np.uint8(1)),
        metadata_bit=zero.metadata_bit)
    certs = k_fixture.certs + (conflicting,)
    left = h_close.close_volume(certs, k_fixture.spec)
    right = h2_close.close_volume(
        tuple(mirror(cert) for cert in certs), k_fixture.h2spec)
    assert left.status == "integrity_failure"
    assert left.diagnostics["phase"] == "fountain"
    assert_same_close(left, right)


def test_close_unsupported_metadata_version_agrees(
        k_fixture: KFixture) -> None:
    """A structurally valid version 1 word is refused identically."""
    spec = k_fixture.spec
    counters = np.arange(N_CERTS, dtype=np.int64)
    bits = h_metadata.tile_bits(
        h_metadata.encode_metadata(1, k_fixture.k_total), counters)
    pairs = [
        make_pair(spec, int(counter), "main",
                  k_fixture.symbols[int(counter)], int(bits[index]))
        for index, counter in enumerate(counters)
    ]
    left = h_close.close_volume([pair[0] for pair in pairs], spec)
    right = h2_close.close_volume(
        [pair[1] for pair in pairs], k_fixture.h2spec)
    assert left.status == "unsupported" and left.metadata_version == 1
    assert_same_close(left, right)


def test_close_record_mapping_agrees(k_fixture: KFixture) -> None:
    """The durable record: same status, same payload identity."""
    frontier = hashlib.sha256(b"frontier").hexdigest()
    verified_left = h_close.close_volume(k_fixture.certs, k_fixture.spec)
    verified_right = h2_close.close_volume(
        k_fixture.h2certs, k_fixture.h2spec)
    left_record = h_close.close_record_from_result(verified_left, frontier)
    right_record = h2_close.close_record_from_result(verified_right)
    assert left_record.status is HoloDurableStatus.VERIFIED
    assert right_record.status.value == left_record.status.value
    assert right_record.payload_sha256 == left_record.payload_sha256
    assert right_record.payload_sha256 == hashlib.sha256(
        k_fixture.payload).hexdigest()
    assert right_record.is_terminal

    open_left = h_close.close_volume(k_fixture.certs[:10], k_fixture.spec)
    open_right = h2_close.close_volume(
        k_fixture.h2certs[:10], k_fixture.h2spec)
    assert h_close.close_record_from_result(open_left, None).status.value \
        == h2_close.close_record_from_result(open_right).status.value \
        == "open"
    assert not h2_close.close_record_from_result(open_right).is_terminal


# --------------------------------------------------------- (c) count gate

@pytest.mark.parametrize("n", [0, 24, 47, 48, 60, 61, 62, N_CERTS])
def test_count_gate_agrees(k_fixture: KFixture, n: int) -> None:
    left_ready, left_counts = h_close.close_count_status(
        k_fixture.certs[:n], k_fixture.spec)
    right_ready, right_counts = h2_close.close_count_status(
        k_fixture.h2certs[:n], k_fixture.h2spec)
    assert left_ready == right_ready
    assert left_counts == right_counts
    assert h_close.close_count_ready(k_fixture.certs[:n], k_fixture.spec) \
        == h2_close.close_count_ready(k_fixture.h2certs[:n], k_fixture.h2spec)


def test_count_gate_agrees_on_metadata_terminal_states(
        k_fixture: KFixture) -> None:
    """Inconsistent and unsupported both report ready with no counts."""
    zero = k_fixture.certs[0]
    twin = h_close.CertifiedStreamSymbol(
        counter=zero.counter, page=0, ty=zero.ty, tx=zero.tx,
        stream_id="main", symbol=zero.symbol,
        metadata_bit=1 - zero.metadata_bit)
    certs = k_fixture.certs + (twin,)
    assert h_close.close_count_status(certs, k_fixture.spec) == (True, None)
    assert h2_close.close_count_status(
        tuple(mirror(cert) for cert in certs), k_fixture.h2spec) \
        == (True, None)


def test_distinct_esi_block_counts_agree(k_fixture: KFixture) -> None:
    counters = [int(cert.counter) for cert in k_fixture.certs]
    assert h_close.distinct_esi_block_counts(
        counters, k_fixture.spec, k_fixture.k_total, "main") \
        == h2_close.distinct_esi_block_counts(
            counters, k_fixture.h2spec, k_fixture.k_total, "main")


# -------------------------------------------------- multi-block algebra

def test_multi_block_close_agrees(k_fixture: KFixture,
                                  monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-page quotas + keystream shuffle + per-block GE, B = 8.

    A real B > 1 volume needs K > 16384 (a multi-megabyte, twenty-page
    encode), so BOTH sides get the same reduced block knee instead.  The
    parameterisation is synthetic; the algebra under test — quotas,
    shuffle, contiguous source mapping, per-block rank rows — is the
    frozen one, exercised identically on both sides.
    """
    monkeypatch.setattr(h_fountain, "BLOCK_K_MAX", 8)
    monkeypatch.setattr(h2_fountain, "BLOCK_K_MAX", 8)
    spec = k_fixture.spec
    code = h_fountain.VolumeCode(
        k_fixture.k_total, spec.symbol_bits, spec.seed,
        tiles_per_page=spec.tiles_per_page)
    assert code.n_blocks == 8
    source = h_fountain.pack_source(
        _wrap(k_fixture.payload), k_fixture.k_total, spec.symbol_bits)
    counters = np.arange(200, dtype=np.int64)
    symbols = code.encode_symbols(source, counters)
    pairs = [
        make_pair(spec, int(counter), "main", symbols[index],
                  int(k_fixture.metadata_bits[int(counter)]))
        for index, counter in enumerate(counters)
    ]
    left = h_close.close_volume([pair[0] for pair in pairs], spec)
    right = h2_close.close_volume(
        [pair[1] for pair in pairs], k_fixture.h2spec)
    assert left.verified and right.payload == k_fixture.payload
    assert len(left.blocks) == 8
    assert_same_close(left, right)

    partial = pairs[:40]
    left_open = h_close.close_volume([pair[0] for pair in partial], spec)
    right_open = h2_close.close_volume(
        [pair[1] for pair in partial], k_fixture.h2spec)
    assert left_open.status == "open"
    assert_same_close(left_open, right_open)


def _wrap(payload: bytes) -> bytes:
    from holo.format import envelope as h_envelope
    return h_envelope.wrap(payload)


# ----------------------------------------------------- multistream close

@pytest.fixture(scope="module")
def cmy8_fixture():
    """A CMY8 volume from generator truth (three independent streams)."""
    # Same move as the K fixture: the identity, not a pseudo-printer
    # (C4, RULINGS G5).  ``make_spec("c2-cmy8-p120-v0", "default")`` was
    # A4 at 6 mm deriving 52x36 tiles = the printed fossil
    # ``c2-cmy8-p120-v0@3328x2304``, byte-identical through the ``L:``
    # route.  It is one of the TWO identities holo2's own catalogue
    # deliberately does not hold (RULINGS G8, cmy8-v0 "goes away"), which
    # is exactly right here: this fixture builds ``src/holo``'s truth for
    # an UNPOOLED three-stream close and hand-builds holo2's side, so the
    # ``L:`` line makes the one-sided-ness visible instead of implying a
    # holo2 reader that does not exist.
    spec = h_resolve_format_ref("L:c2-cmy8-p120-v0@3328x2304")
    payload = hashlib.sha256(b"holo2-h2b-cmy8").digest() * 900
    plan = plan_volume(spec, len(payload), 0.5)
    assert plan.n_pages == 1 and len(spec.stream_profiles) == 3
    layout = h_streamset.StreamSet(tuple(
        (profile.stream_id, profile.symbol_bits)
        for profile in spec.stream_profiles))
    packed = h_streamset.pack_payload(payload, layout)
    assert packed.k_total == plan.k_total
    counters = np.arange(N_CERTS, dtype=np.int64)
    metadata_bits = h_metadata.tile_bits(
        h_metadata.encode_metadata(0, plan.k_total), counters)
    pairs = []
    for source in packed.streams:
        profile = spec.stream_profile(source.stream_id)
        code = h_fountain.VolumeCode(
            plan.k_total, profile.symbol_bits, spec.seed,
            tiles_per_page=spec.tiles_per_page,
            stream_id=profile.stream_id, fountain_aux=profile.fountain_aux)
        symbols = code.encode_symbols(source.rows, counters)
        pairs.extend(
            make_pair(spec, int(counter), source.stream_id, symbols[index],
                      int(metadata_bits[index]))
            for index, counter in enumerate(counters))
    return spec, close_spec_for(spec), payload, plan.k_total, tuple(pairs)


def test_cmy8_close_agrees_byte_exact(cmy8_fixture) -> None:
    """The multistream branch: stream-major reassembly, one envelope."""
    spec, h2spec, payload, k_total, pairs = cmy8_fixture
    left = h_close.close_volume([pair[0] for pair in pairs], spec)
    right = h2_close.close_volume([pair[1] for pair in pairs], h2spec)
    assert left.verified and right.payload == payload
    assert left.k_total == k_total
    assert len(left.blocks) == 3        # one block per stream
    assert {row.stream_id for row in right.blocks} == {"C", "M", "Y"}
    assert_same_close(left, right)


def test_cmy8_missing_stream_is_open_on_both_sides(cmy8_fixture) -> None:
    """One starved plane leaves the volume open, naming the same stream."""
    _spec, h2spec, _payload, _k, pairs = cmy8_fixture
    spec = cmy8_fixture[0]
    kept = [pair for pair in pairs if pair[0].stream_id != "Y"]
    left = h_close.close_volume([pair[0] for pair in kept], spec)
    right = h2_close.close_volume([pair[1] for pair in kept], h2spec)
    assert left.status == "open"
    assert left.diagnostics["unsolved_streams"] == ("Y",)
    assert_same_close(left, right)


def test_cmy8_stream_set_reassembly_agrees(cmy8_fixture) -> None:
    """The carried stream-major mapping itself, packed side by side."""
    spec, _h2spec, payload, _k, _pairs = cmy8_fixture
    streams = tuple(
        (profile.stream_id, profile.symbol_bits)
        for profile in spec.stream_profiles)
    left = h_streamset.pack_payload(
        payload, h_streamset.StreamSet(streams))
    right = h2_streamset.pack_payload(
        payload, h2_streamset.StreamSet(streams))
    assert left.k_total == right.k_total
    for left_source, right_source in zip(left.streams, right.streams,
                                         strict=True):
        assert left_source.stream_id == right_source.stream_id
        assert np.array_equal(left_source.rows, right_source.rows)


# ----------------------------------------------------- carry fidelity

CARRY_PAIRS = (
    ("holo.core.keystream", "holo2.format.keystream"),
    ("holo.format.metadata", "holo2.format.metadata"),
    ("holo.format.envelope", "holo2.format.envelope"),
    ("holo.format.streamset", "holo2.format.streamset"),
    ("holo.core.fountain", "holo2.format.fountain"),
    ("holo.receive.fountain_close", "holo2.format.fountain_close"),
    # B5 (RULED 2026-08-12): fountain_close.py is the carried side of a
    # SECOND origin — its two progress ROW types are a copy of v1's
    # ``close_progress`` module, which the fountain_close pair could only
    # ever see as holo2-original code.  Declared here so a future edit to
    # either row is a declared adaptation, never a silent divergence.
    ("holo.receive.close_progress", "holo2.format.fountain_close"),
)

# Deliberate, reviewed deviations (H2b).  A NEW entry appearing in a
# failure is a decision to make, not a line to add reflexively: either the
# carry drifted (fix it) or the divergence is intended (record it here).
NOT_CARRIED = {
    # COLOR draw forms (domains 9-13) and the whole-page generator helper.
    # H3bis added the six K tile-chain domains (1-6): ``bits``,
    # ``bounded_draws`` and ``slot_perm_params`` are now CARRIED and are
    # compared like every other shared function, so they left this list.
    # ``payload_bits`` stays out: it draws a whole page's scramble for the
    # generator, where a receiver descrambles one tile at a time.
    "holo.core.keystream": {
        "_color_stream_aux", "_item_permutation",
        "cmy7_dither_bits", "cmy7_interleave_permutation",
        "cmy8_dither_bits", "color_cell_permutation",
        "color_dust_permutation", "payload_bits"},
    # holo.core.fountain: its capacity arithmetic (the planning primitives
    # holo2 never carried) lives in holo.core.capacity since the
    # column-group round, so nothing is left to exempt there.
    # the v1 §10.4 observer projection; no close consults it
    "holo.receive.fountain_close": {"metadata_progress"},
    # B5: only the two accounting ROWS are carried out of close_progress.
    # ``CloseProgress`` and ``CloseMetadataProgress`` are the v1 §10.4
    # detached observer projection and ``from_fountain_result`` is its
    # detach helper — holo2's observer reads the close result directly.
    # Names here match a whole definition or a whole class (its members
    # match by their ``Class.`` prefix).
    "holo.receive.close_progress": {
        "CloseMetadataProgress", "CloseProgress", "from_fountain_result"},
}
# Definitions the CARRIED module holds that its origin does not, exempt
# from the "grew unreviewed code" check.  Keyed by origin because one
# carried module may serve two origins (B5).
HOLO2_ONLY_PREFIXES = {
    # WP-1.0 (2026-08-22): CloseSpec/CloseStreamProfile moved out to
    # holo2.format.close_spec (holo2-original, not part of this pair's
    # carried module any more), so this pair's only exemption left is B5's.
    "holo.receive.fountain_close": (
        # B5: these two are NOT holo2-original — they are the
        # close_progress carry declared above, pinned by that pair.
        "CloseBlockProgress.", "CloseSurplusInconsistency."),
}
# The members a pair pins, when its carried module holds more than this
# origin's code: everything outside the listed classes belongs to the
# other pair and is compared there (B5).
CARRIED_MEMBERS = {
    "holo.receive.close_progress": ("CloseBlockProgress.",
                                    "CloseSurplusInconsistency."),
}
HOLO2_ONLY_NAMES = {"color_stream_aux"}     # holo's _color_stream_aux
ADAPTED = {
    # holo2's §5.5 CloseRecord has no certificate frontier / metadata
    # version field; the status and payload identity mapping is unchanged.
    "holo.receive.fountain_close": {"close_record_from_result"},
}
RENAMED_SYMBOLS = {"FormatSpec": "CloseSpec",
                   "_color_stream_aux": "color_stream_aux",
                   # S1: holo's name collides with core.CertificateConflict
                   # (same-key content conflict at commit); the close's is
                   # a solver inconsistency across certified symbols.
                   "CertificateConflict": "CertifiedSymbolConflict"}


def _function_sources(module_name: str) -> dict[str, str]:
    """Every def in a module, unparsed, with docstrings removed."""
    import ast
    import copy
    import importlib
    import inspect

    tree = ast.parse(inspect.getsource(importlib.import_module(module_name)))
    out: dict[str, str] = {}

    def strip_doc(node):
        node = copy.deepcopy(node)
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            node.body = node.body[1:] or [ast.Pass()]
        return node

    def walk(parent, prefix=""):
        for child in parent.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out[prefix + child.name] = ast.unparse(strip_doc(child))
            elif isinstance(child, ast.ClassDef):
                walk(child, prefix + child.name + ".")

    walk(tree)
    return out


#: Origins that moved on main after holo2 carried them, mapped to the
#: reason. The mechanism is the STANDING TRIPWIRE for origin drift —
#: declare it here rather than letting the carry rot silently. Each
#: entry asserts the divergence still exists, so it retires itself the
#: day that sync lands. History: the FORMAT-SPACE P1 entry of 2026-08-19
#: (three close functions) retired when the catch-up wave's WP-1.1
#: landed the family enum (2026-08-22). DECLARED 2026-09-04: the
#: column-group pool (docs/CMY8-COLUMN-GROUPS.md) generalised the pooled
#: fountain and the pooled envelope law in src/holo; holo2 is ruled
#: UNTOUCHED (scope ruling 7 — it has no colour receive), so its
#: carries of both modules stay at the pre-column-group text.
ORIGIN_MOVED: dict[str, str] = {
    "holo.core.fountain":
        "column-group pool, ruling 2026-09-04 (docs/CMY8-COLUMN-GROUPS.md "
        "§8): VolumeCode grew groups/tile_slots and the capacity "
        "arithmetic moved to core/capacity.py (its reserve keyword is "
        "solves_per_block); holo2 keeps the frozen one-file text",
    "holo.format.streamset":
        "column-group pool, ruling 2026-09-04: pooled_symbol_bits is the "
        "widest stream and the pooled envelope counts n*S "
        "(pooled_source_symbol_count); holo2 keeps the equal-width text",
}

@pytest.mark.parametrize("origin,carried", CARRY_PAIRS,
                         ids=[f"{origin}->{carried}"
                              for origin, carried in CARRY_PAIRS])
def test_carried_code_is_the_original_code(origin: str, carried: str) -> None:
    """Every shared function is the ORIGINAL, character for character.

    The numerical tests above prove the two closes agree on the fixtures
    they run; this proves there is no third behaviour hiding on an
    untested branch.  Docstrings are stripped and the renamed types
    normalised; nothing else may differ.
    """
    left = _function_sources(origin)
    right = _function_sources(carried)
    adapted = ADAPTED.get(origin, set())
    members = CARRIED_MEMBERS.get(origin)
    if members is not None:
        right = {name: source for name, source in right.items()
                 if name.startswith(members)}

    not_carried = NOT_CARRIED.get(origin, set())
    missing = {
        name for name in set(left) - set(right)
        if name not in not_carried and name.split(".")[0] not in not_carried
    }

    exempt_prefixes = HOLO2_ONLY_PREFIXES.get(origin, ())
    extra = {
        name for name in set(right) - set(left)
        if not (exempt_prefixes and name.startswith(exempt_prefixes))
        and name not in HOLO2_ONLY_NAMES
    }

    drifted = []
    for name in sorted(set(left) & set(right) - adapted):
        source = left[name]
        for old, new in RENAMED_SYMBOLS.items():
            source = source.replace(old, new)
        if source != right[name]:
            drifted.append(name)

    # The tripwire gate reinterprets the SAME comparison — a declared-
    # moved origin must still show a divergence the oracle would flag,
    # otherwise the entry is stale and must retire loudly.  (Comparing
    # raw sources here would be wrong: a rename-bearing pair never goes
    # raw-equal, so a synced pair would skip forever.)
    if origin in ORIGIN_MOVED:
        assert missing or extra or drifted, (
            f"{origin} no longer diverges from {carried}: the sync has "
            "landed — delete this ORIGIN_MOVED entry and let the carry "
            "oracle re-arm")
        pytest.skip(f"origin moved ({ORIGIN_MOVED[origin]}); holo2 keeps "
                    "its carry until the declared sync lands")

    assert not missing, f"{carried} silently dropped {sorted(missing)}"
    assert not extra, f"{carried} grew unreviewed code {sorted(extra)}"
    assert not drifted, (
        f"{carried} diverged from {origin} in {drifted} — decide whether "
        "the carry drifted or the divergence is intended, then record it")
