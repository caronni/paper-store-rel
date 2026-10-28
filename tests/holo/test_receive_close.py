"""Current certificate-to-close integration beyond the K=1 smoke path."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

import numpy as np
import pytest

from holo.core.fountain import VolumeCode
from holo.devices.profiles import make_spec
from holo.format.descriptor import FormatSpec
from holo.gen.compose import compose_page_cells
from holo.gen.emit import source_packed_for
from holo.gen.plan import plan_volume
from holo.receive import close_volume
from holo.receive.fountain_close import CertifiedStreamSymbol
from holo.receive.close_progress import from_fountain_result
from holo.receive.evidence import AttemptStage, AttemptState
from holo.receive.payload import attempt_k_tile
from holo.receive.records import certificate_for_close
from holo.receive.types import CloseRecord, CloseStatus


@dataclass(frozen=True)
class _CloseFixture:
    spec: FormatSpec
    payload: bytes
    k_total: int
    certificates: tuple[CertifiedStreamSymbol, ...]
    corrupted_zero: CertifiedStreamSymbol


def _certificate(
    spec: FormatSpec,
    page: np.ndarray,
    index: int,
    tag: str,
) -> CertifiedStreamSymbol:
    _, tiles_x = spec.layout.tiles_yx
    tile_y, tile_x = divmod(index, tiles_x)
    tile = page[
        tile_y * 64:(tile_y + 1) * 64,
        tile_x * 64:(tile_x + 1) * 64,
    ]
    record, certificate = attempt_k_tile(
        (tile.astype(np.float64) * 2.0 - 1.0) * 5.0,
        spec,
        (0, tile_y, tile_x),
        AttemptStage.SCAN,
        source_sha256=hashlib.sha256(b"close-source").hexdigest(),
        lane_id="close-fixture",
        component_block_ids=(
            hashlib.sha256(tag.encode("ascii")).hexdigest(),),
    )
    assert record.state is AttemptState.CERTIFIED and certificate is not None
    return certificate_for_close(certificate, spec)


@pytest.fixture(scope="module")
def close_fixture() -> _CloseFixture:
    spec = make_spec("c3-r0550", "default")
    payload = hashlib.sha256(b"track3-current-close").digest() * 500
    plan = plan_volume(spec, len(payload), 0.75)
    assert plan.k_total == 61 and plan.n_pages == 1

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
    clean_page = compose_page_cells(spec, 0, symbols, plan.k_total)
    certificates = tuple(
        _certificate(spec, clean_page, index, f"clean-{index}")
        for index in range(100)
    )

    # ESI 0 is systematic.  Recompose it after changing one source bit so the
    # resulting certificate is individually valid, but the recovered envelope
    # is wrong when it replaces the clean ESI 0 without redundant equations.
    corrupted_symbols = symbols.copy()
    corrupted_symbols[0, 0] ^= np.uint8(1)
    corrupted_page = compose_page_cells(
        spec, 0, corrupted_symbols, plan.k_total
    )
    corrupted_zero = _certificate(spec, corrupted_page, 0, "corrupted-0")
    assert not np.array_equal(
        corrupted_zero.symbol, certificates[0].symbol
    )
    return _CloseFixture(
        spec, payload, plan.k_total, certificates, corrupted_zero
    )


def test_k_gt_one_close_recovers_missing_systematics_with_repairs(
    close_fixture: _CloseFixture,
) -> None:
    # Omit ESI 0..19.  Of these 80 equations only 41 are systematic, so a
    # verified result requires the fountain's actual repair-row GE path.
    certificates = close_fixture.certificates[20:100]
    result = close_volume(certificates, close_fixture.spec)

    assert result.verified and result.payload == close_fixture.payload
    assert result.k_total == close_fixture.k_total == 61
    assert result.symbols_used == 80
    assert sum(b.rank_shortfall for b in result.blocks) == 0
    assert len(result.blocks) == 1
    assert result.blocks[0].rank == result.blocks[0].needed == 61


def test_k_gt_one_shortfall_is_open_and_rank_exact(
    close_fixture: _CloseFixture,
) -> None:
    # Forty-eight consecutive counters are enough to trust metadata but not
    # enough to solve K=61, separating metadata readiness from payload rank.
    result = close_volume(
        close_fixture.certificates[20:68], close_fixture.spec
    )

    assert result.status == "open"
    assert result.payload is None and result.status == "open"
    assert result.k_total == close_fixture.k_total
    assert result.diagnostics["metadata_rank_shortfall"] == 0
    assert result.diagnostics["metadata_check_shortfall"] == 0
    assert result.symbols_used == 48
    assert sum(b.rank_shortfall for b in result.blocks) == 13
    assert result.reason == (
        "1 of 1 blocks unsolved "
        "(at least 13 additional symbols required)")
    assert "n_certificates_by_stream" not in result.diagnostics
    assert "unsolved_streams" not in result.diagnostics
    unsolved = tuple(b for b in result.blocks if not b.solved)
    assert len(unsolved) == 1
    block = unsolved[0]
    assert (block.needed, block.have, block.rank) == (61, 48, 48)
    assert block.rank_shortfall == 13
    assert asdict(block) == {
        "block": 0,
        "needed": 61,
        "have": 48,
        "rank": 48,
        "solved": False,
        "stream_id": None,
    }
    # One merged dataclass serves the close result and its detached
    # progress (the Phase-2 BlockStatus/CloseBlockProgress merge): the
    # progress projection passes the very same rows through.
    assert repr(block) == (
        "CloseBlockProgress(block=0, needed=61, have=48, rank=48, "
        "solved=False, stream_id=None)")

    progress = from_fountain_result(result)
    assert progress.blocks == result.blocks
    assert progress.blocks[0] is block
    assert progress.count_only is False


def test_solved_but_corrupted_stream_stops_at_envelope_sha(
    close_fixture: _CloseFixture,
) -> None:
    certificates = (
        close_fixture.corrupted_zero,
        *close_fixture.certificates[1:close_fixture.k_total],
    )
    result = close_volume(certificates, close_fixture.spec)

    assert result.status == "integrity_failure"
    assert result.payload is None and result.status != "open"
    assert result.k_total == close_fixture.k_total
    assert result.symbols_used == close_fixture.k_total
    assert sum(b.rank_shortfall for b in result.blocks) == 0
    assert all(block.solved for block in result.blocks)
    assert "SHA-256" in (result.reason or "")


def test_terminal_close_record_rejects_contradictory_payload_semantics() -> None:
    frontier = "a" * 64
    payload_sha256 = "b" * 64
    with pytest.raises(TypeError, match="status must be CloseStatus"):
        CloseRecord(  # type: ignore[arg-type]
            "verified", frontier, payload_sha256, 1)
    with pytest.raises(ValueError, match="failure reason"):
        CloseRecord(
            CloseStatus.VERIFIED, frontier, payload_sha256, 1,
            reason="contradiction")
    with pytest.raises(TypeError, match="reason must be text"):
        CloseRecord(
            CloseStatus.VERIFIED, frontier, payload_sha256, 1,
            reason=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="payload identity"):
        CloseRecord(
            CloseStatus.INTEGRITY_FAILURE, frontier, payload_sha256, 1,
            reason="contradiction")


def test_deferred_validation_suppresses_fountain_for_every_status(
    monkeypatch,
    tmp_path,
) -> None:
    import holo.receive.fountain_close as fountain_close
    from holo.format.registry import get_format_row
    from holo.receive.session import (
        SessionState,
        apply_close,
        certificate_frontier_sha256,
        load_session,
        save_session,
        validate_session,
    )
    from holo.receive.types import CloseRecord, CloseStatus

    spec = get_format_row("c3-r0550@2240x1536")
    opened = SessionState.create(
        spec.spec_id, "test/deferred-session-policy", None)
    frontier = certificate_frontier_sha256(())
    verified = apply_close(opened, CloseRecord(
        CloseStatus.VERIFIED,
        frontier,
        "b" * 64,
        1,
    ))
    integrity_failure = apply_close(opened, CloseRecord(
        CloseStatus.INTEGRITY_FAILURE,
        frontier,
        reason="synthetic integrity failure",
    ))
    unsupported = apply_close(opened, CloseRecord(
        CloseStatus.UNSUPPORTED,
        frontier,
        metadata_version=1,
        reason="synthetic future metadata",
    ))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("state validation ran the fountain")

    monkeypatch.setattr(fountain_close, "close_volume", forbidden)
    for state in (opened, verified, integrity_failure, unsupported):
        with pytest.raises(AssertionError, match="ran the fountain"):
            validate_session(state)
    for state in (opened, verified, integrity_failure, unsupported):
        validate_session(state, defer_fountain_validation=True)

    states = (
        ("open", opened),
        ("verified", verified),
        ("integrity-failure", integrity_failure),
        ("unsupported", unsupported),
    )
    for name, state in states:
        path = tmp_path / f"{name}.json"
        assert save_session(path, state, validate=False)
        with pytest.raises(AssertionError, match="ran the fountain"):
            load_session(path)
        assert load_session(
            path, defer_fountain_validation=True) == state
