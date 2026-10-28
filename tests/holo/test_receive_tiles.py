"""Current Track-3 tile-attempt negative-channel qualification."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pytest

from holo.core.fountain import VolumeCode
from holo.devices.profiles import make_spec
from holo.format.descriptor import FormatSpec
from holo.gen.compose import compose_page_cells
from holo.gen.emit import source_packed_for
from holo.gen.plan import plan_volume
from holo.receive import payload, payload_engine, tiles
from holo.receive.evidence import (
    AttemptStage,
    AttemptState,
    TileAttemptRecord,
    TileCertificateRecord,
)
from holo.receive.evidence_blocks import (
    EvidenceBlock,
    EvidenceOrigin,
    TileAttemptView,
    _block_from_rows,
)
from holo.receive.payload_engine import run_attempts
from holo.receive.records import (
    certificate_divergence as records_certificate_divergence,
    CertificateStore,
    certificate_for_close,
    printed_cells_from_record,
    stream_attempt_identity,
)


@dataclass(frozen=True)
class _TileFixture:
    spec: FormatSpec
    page: np.ndarray
    symbols: np.ndarray


@pytest.fixture(scope="module")
def tile_fixture() -> _TileFixture:
    spec = make_spec("c3-r0550", "default")
    payload = hashlib.sha256(b"track3-tile-negative-channel").digest()
    plan = plan_volume(spec, len(payload), 0.5)
    source = source_packed_for(payload, plan)
    code = VolumeCode(
        plan.k_total,
        plan.symbol_bits,
        spec.seed,
        tiles_per_page=spec.tiles_per_page,
    )
    symbols = code.encode_symbols(
        source, np.arange(spec.tiles_per_page, dtype=np.int64)
    )
    return _TileFixture(
        spec,
        compose_page_cells(spec, 0, symbols, plan.k_total),
        symbols,
    )


def _tile(fixture: _TileFixture, index: int) -> np.ndarray:
    _, tiles_x = fixture.spec.layout.tiles_yx
    tile_y, tile_x = divmod(index, tiles_x)
    return fixture.page[
        tile_y * 64:(tile_y + 1) * 64,
        tile_x * 64:(tile_x + 1) * 64,
    ]


def _llr(bits: np.ndarray) -> np.ndarray:
    return (bits.astype(np.float64) * 2.0 - 1.0) * 5.0


def _source(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _attempt(
    fixture: _TileFixture, index: int, llr: np.ndarray, tag: str
) -> tuple[TileAttemptRecord, TileCertificateRecord | None]:
    _, tiles_x = fixture.spec.layout.tiles_yx
    tile_y, tile_x = divmod(index, tiles_x)
    return payload.attempt_k_tile(
        llr,
        fixture.spec,
        (0, tile_y, tile_x),
        AttemptStage.SCAN,
        source_sha256=_source(tag),
        lane_id="native",
        component_block_ids=(
            hashlib.sha256(tag.encode("ascii")).hexdigest(),
        ),
    )


def _block(
    fixture: _TileFixture,
    index: int,
    source_label: str,
    llr: np.ndarray,
    selected_flat: np.ndarray,
) -> EvidenceBlock:
    _, tiles_x = fixture.spec.layout.tiles_yx
    tile_y, tile_x = divmod(index, tiles_x)
    source = _source(source_label)
    origin = EvidenceOrigin(
        f"{source}/native/patch-{index}", index, 0.125)
    values = np.asarray(llr, np.float32).reshape(-1)
    return _block_from_rows(
        source,
        "native",
        0,
        (tile_y, tile_x),
        (
            (int(flat), values[int(flat)].tobytes(), origin)
            for flat in np.asarray(selected_flat).reshape(-1)
        ),
    )


def _payload_flats(spec: FormatSpec) -> np.ndarray:
    yy, xx = np.meshgrid(
        np.arange(64), np.arange(64), indexing="ij")
    cells = np.stack((yy, xx), axis=-1).reshape(-1, 2)
    return np.flatnonzero(payload.payload_cell_mask(spec, cells))


class _EngineLeaf:
    """Minimal K leaf mirroring production._KPayloadLeaf for engine tests."""

    def __init__(self, spec: FormatSpec, store: CertificateStore,
                 source_sha256: str, lane_id: str) -> None:
        self.spec = spec
        self.store = store
        self.source_sha256 = source_sha256
        self.lane_id = lane_id
        self.attempts: list[TileAttemptRecord] = []
        self.certificates: list[TileCertificateRecord] = []
        self._seen: set[str] = set()

    def unresolved_streams(
        self, address: tuple[int, int, int]) -> tuple[str, ...]:
        return self.store.unresolved_streams(address)

    def attempt(
        self,
        view: TileAttemptView,
        stream_id: str,
        stage: AttemptStage,
    ) -> TileAttemptRecord | None:
        del stream_id  # K has exactly one stream
        record, certificate = payload.attempt_k_tile(
            view.llr_cells_f64, self.spec, view.address, stage,
            source_sha256=self.source_sha256,
            lane_id=self.lane_id,
            component_block_ids=view.component_block_ids,
            dependency_certificate_ids=view.dependency_certificate_ids)
        if record.attempt_id in self._seen:
            return None
        self._seen.add(record.attempt_id)
        self.store.record_attempt(record, certificate)
        self.attempts.append(record)
        if certificate is not None:
            self.certificates.append(certificate)
        return record


def test_wrong_page_hypothesis_never_mints_a_certificate(
    tile_fixture: _TileFixture,
) -> None:
    spec = tile_fixture.spec
    record, certificate = payload.attempt_k_tile(
        _llr(_tile(tile_fixture, 0)),
        spec,
        (1, 0, 0),
        AttemptStage.SCAN,
        source_sha256=_source("wrong-page"),
        lane_id="native",
        component_block_ids=(
            hashlib.sha256(b"wrong-page").hexdigest(),
        ),
    )
    assert record.state is AttemptState.ATTEMPTED_FAILED
    assert record.decoder_invoked
    assert certificate is None
    assert record.certificate_id is None
    assert record.crc_ok is False


def test_deterministic_noise_sweep_has_zero_wrong_certificates(
    tile_fixture: _TileFixture,
) -> None:
    yields: dict[float, int] = {}
    fractions = (0.0, 0.02, 0.06, 0.08, 0.25)
    for fraction in fractions:
        rng = np.random.default_rng(1234)
        certified = 0
        for index in range(12):
            tile = _tile(tile_fixture, index)
            llr = _llr(tile)
            llr[rng.random(llr.shape) < fraction] *= -1.0
            record, certificate = _attempt(
                tile_fixture,
                index,
                llr,
                f"noise-{fraction:.2f}-{index}",
            )
            assert record.state is not AttemptState.BELOW_ATTEMPT_FLOOR
            if certificate is None:
                assert record.certificate_id is None
                continue
            certified += 1
            close_symbol = certificate_for_close(
                certificate, tile_fixture.spec)
            np.testing.assert_array_equal(
                close_symbol.symbol, tile_fixture.symbols[index]
            )
            np.testing.assert_array_equal(
                printed_cells_from_record(certificate, tile_fixture.spec),
                tile)
        yields[fraction] = certified

    # This is the historical r0550 deterministic cliff fixture.  Yield may
    # fall; a wrong CRC certificate may never appear on the way down.
    assert yields == {0.0: 12, 0.02: 12, 0.06: 12, 0.08: 6, 0.25: 0}


def test_partial_erasure_above_floor_still_certifies_exactly(
    tile_fixture: _TileFixture,
) -> None:
    spec = tile_fixture.spec
    index = 100
    tile = _tile(tile_fixture, index)
    llr = _llr(tile)
    rng = np.random.default_rng(3)
    llr[rng.random(llr.shape) < 0.08] = 0.0

    record, certificate = _attempt(
        tile_fixture, index, llr, "partial-erasure")
    assert record.state is AttemptState.CERTIFIED
    # Erasures really landed on cargo cells and the attempt stayed above
    # the counting floor (the record keeps only n_informative; erased =
    # cargo cells whose LLR is exactly 0.0).
    site_mask = tiles._geometry(spec).site_mask_yx
    n_live = int(np.count_nonzero((llr != 0.0) & ~site_mask))
    n_cargo = int(np.count_nonzero(~site_mask))
    assert n_live < n_cargo
    assert record.n_informative == n_live
    assert record.n_informative >= tiles.k_eff_bits(spec)
    assert certificate is not None
    close_symbol = certificate_for_close(certificate, spec)
    np.testing.assert_array_equal(
        close_symbol.symbol, tile_fixture.symbols[index]
    )
    np.testing.assert_array_equal(
        printed_cells_from_record(certificate, spec), tile)


def test_engine_never_materializes_certified_attempt_views(
    tile_fixture: _TileFixture,
    monkeypatch,
) -> None:
    """Certified blocks stay available for audit but never become attempts."""
    spec = tile_fixture.spec
    _record, certified_certificate = _attempt(
        tile_fixture, 0, _llr(_tile(tile_fixture, 0)), "terminal")
    assert certified_certificate is not None
    store = CertificateStore(spec)
    assert store.add(certified_certificate)

    payload_flats = _payload_flats(spec)
    certified_blocks = tuple(
        _block(
            tile_fixture,
            0,
            label,
            _llr(_tile(tile_fixture, 0)),
            payload_flats[offset:offset + 1],
        )
        for offset, label in enumerate(("terminal-a", "terminal-b"))
    )
    unresolved_blocks = tuple(
        _block(
            tile_fixture,
            1,
            label,
            np.ones((64, 64), np.float64),
            payload_flats[offset:offset + 1],
        )
        for offset, label in enumerate(("terminal-a", "terminal-b"))
    )
    blocks = (*certified_blocks, *unresolved_blocks)

    materialized: list[tuple[tuple[int, int, int], ...]] = []
    original = payload_engine.tile_attempt_view

    def counted(rows):
        selected = tuple(rows)
        materialized.append(tuple(row.address for row in selected))
        return original(selected)

    monkeypatch.setattr(payload_engine, "tile_attempt_view", counted)
    leaf = _EngineLeaf(spec, store, _source("engine-run"), "native")
    run = run_attempts(blocks, blocks, lane_id="native", leaf=leaf)

    unresolved_address = unresolved_blocks[0].address
    assert materialized == [
        (unresolved_address,),
        (unresolved_address,),
        (unresolved_address, unresolved_address),
    ]
    assert tuple(row.state for row in leaf.attempts) == (
        AttemptState.BELOW_ATTEMPT_FLOOR,
        AttemptState.BELOW_ATTEMPT_FLOOR,
        AttemptState.BELOW_ATTEMPT_FLOOR,
    )
    scan_ids = tuple(
        stream_attempt_identity(
            spec,
            unresolved_address,
            "main",
            AttemptStage.SCAN,
            (block.block_id,),
        )
        for block in sorted(
            unresolved_blocks, key=lambda value: value.source_sha256)
    )
    union_ids = (
        stream_attempt_identity(
            spec,
            unresolved_address,
            "main",
            AttemptStage.UNION,
            tuple(
                row.block_id for row in sorted(
                    unresolved_blocks,
                    key=lambda value: (value.source_sha256, value.block_id),
                )
            ),
        ),
    )
    assert tuple(row.attempt_id for row in leaf.attempts) == (
        *scan_ids, *union_ids)
    assert store.certificates() == (certified_certificate,)
    assert store.attempts() == tuple(leaf.attempts)
    assert not leaf.certificates
    # Below-floor rows never enter the selective retry frontier.
    assert run.retry_frontier == ()
    assert not any(
        row.stage is AttemptStage.RETRY150 for row in leaf.attempts)
    divergences = records_certificate_divergence(
        blocks, store.certificates(), spec)
    assert tuple(
        (row.evidence_block_id, row.n_observed, row.n_disagree)
        for row in divergences
    ) == tuple(
        (row.block_id, 1, 0)
        for row in sorted(
            certified_blocks,
            key=lambda value: (value.source_sha256, value.lane_id),
        )
    )


def test_engine_retries_failed_baseline_exactly_once(
    tile_fixture: _TileFixture,
) -> None:
    """One selective retry150 per (address, stream), on the exact baseline."""
    spec = tile_fixture.spec
    _record, prior_certificate = _attempt(
        tile_fixture, 0, _llr(_tile(tile_fixture, 0)), "prior-certificate")
    assert prior_certificate is not None
    store = CertificateStore(spec)
    assert store.add(prior_certificate)

    payload_flats = _payload_flats(spec)
    certified_block = _block(
        tile_fixture,
        0,
        "prior-divergence",
        _llr(_tile(tile_fixture, 0)),
        payload_flats[:1],
    )
    rng = np.random.default_rng(23_150)
    noisy = np.where(
        rng.integers(0, 2, (64, 64)), 0.2, -0.2)
    retry_block = _block(
        tile_fixture,
        31,
        "retry-evidence",
        noisy,
        np.arange(4096),
    )
    blocks = (certified_block, retry_block)

    leaf = _EngineLeaf(spec, store, _source("engine-run"), "native")
    run = run_attempts(blocks, blocks, lane_id="native", leaf=leaf)

    assert tuple(row.stage for row in leaf.attempts) == (
        AttemptStage.SCAN, AttemptStage.RETRY150)
    scan_row, retry_row = leaf.attempts
    assert scan_row.state is AttemptState.ATTEMPTED_FAILED
    assert run.retry_frontier == (scan_row,)
    # Never tunnelling: the retry decodes the exact baseline evidence.
    assert retry_row.work_key == scan_row.work_key
    assert retry_row.component_block_ids == scan_row.component_block_ids
    assert (retry_row.dependency_certificate_ids
            == scan_row.dependency_certificate_ids)
    assert retry_row.attempt_id == stream_attempt_identity(
        spec,
        retry_block.address,
        "main",
        AttemptStage.RETRY150,
        (retry_block.block_id,),
    )
    assert retry_row.state is AttemptState.ATTEMPTED_FAILED
    assert not leaf.certificates
    assert store.certificates() == (prior_certificate,)

    # The incremental audit: known divergence ids are never re-emitted.
    prior_divergences = records_certificate_divergence(
        blocks, store.certificates(), spec)
    assert tuple(
        (row.evidence_block_id, row.n_observed, row.n_disagree)
        for row in prior_divergences
    ) == ((certified_block.block_id, 1, 0),)

    # Replaying identical evidence is a true no-op: the exact attempt
    # identities were recorded, so no second retry can ever run.
    before = tuple(leaf.attempts)
    replay = run_attempts(blocks, blocks, lane_id="native", leaf=leaf)
    assert replay.attempts == ()
    assert replay.retry_frontier == ()
    assert tuple(leaf.attempts) == before
    assert store.attempts() == before


def test_below_floor_union_suppresses_retry_at_a_failed_address(
    tile_fixture: _TileFixture,
) -> None:
    """Anti-tunnelling pin: the LATEST row at a work key gates retry150.

    A failed scan followed by a below-floor union at the same address must
    not be retried — retry never tunnels past its latest baseline evidence.
    """
    spec = tile_fixture.spec
    rng = np.random.default_rng(23_150)
    noisy = np.where(
        rng.integers(0, 2, (64, 64)), 0.2, -0.2)
    block_a = _block(
        tile_fixture, 31, "cancel-a", noisy, np.arange(4096))
    block_b = _block(
        tile_fixture, 31, "cancel-b", -noisy, np.arange(4096))
    blocks = (block_a, block_b)

    store = CertificateStore(spec)
    leaf = _EngineLeaf(spec, store, _source("engine-run"), "native")
    run = run_attempts(blocks, blocks, lane_id="native", leaf=leaf)

    assert tuple(row.stage for row in leaf.attempts) == (
        AttemptStage.SCAN, AttemptStage.SCAN, AttemptStage.UNION)
    assert tuple(row.state for row in leaf.attempts) == (
        AttemptState.ATTEMPTED_FAILED,
        AttemptState.ATTEMPTED_FAILED,
        AttemptState.BELOW_ATTEMPT_FLOOR,
    )
    union_row = leaf.attempts[2]
    assert union_row.n_informative == 0
    assert len(union_row.component_block_ids) == 2
    assert run.retry_frontier == ()
    assert not any(
        row.stage is AttemptStage.RETRY150 for row in leaf.attempts)
    assert not leaf.certificates


def test_bp_alpha_signature_defaults_equal_the_identity_constant() -> None:
    """Ruling 3.4/§13a: identities spell alpha0.8; the decoder defaults and
    tiles.BP_ALPHA must be one value.  A future default change screams here
    before it can silently fork identity-from-executed-decoder."""
    import inspect

    from holo.core.ldpc import decode as ldpc_decode
    from holo.core.ldpc import frame as ldpc_frame
    from holo.core.ldpc import tile as ldpc_tile

    assert tiles.BP_ALPHA == 0.8
    for fn in (ldpc_decode.decode, ldpc_tile.decode_tile,
               ldpc_frame.decode_frame):
        default = inspect.signature(fn).parameters["alpha"].default
        assert default == tiles.BP_ALPHA, fn.__qualname__


def test_k_attempt_threads_bp_alpha_to_the_bp_loop(
    tile_fixture: _TileFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Call-threading pin: attempt_k_tile passes alpha=tiles.BP_ALPHA all
    the way to the core BP decode (not the signature default)."""
    from holo.core.ldpc import tile as ldpc_tile

    seen: list[float] = []
    original = ldpc_tile.decode

    def capturing_decode(llr, rate_id, max_iters=60, alpha=None):
        assert alpha is not None, "alpha must be threaded explicitly"
        seen.append(alpha)
        return original(llr, rate_id, max_iters=max_iters, alpha=alpha)

    monkeypatch.setattr(ldpc_tile, "decode", capturing_decode)
    record, certificate = _attempt(
        tile_fixture, 0, _llr(_tile(tile_fixture, 0)), "alpha-threading")
    assert record.decoder_invoked
    assert certificate is not None
    assert seen == [tiles.BP_ALPHA]
