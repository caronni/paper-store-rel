"""D16 report-only post-solve surplus-consistency audit at fountain close.

The payload GF(2) solver never checks dependent (surplus) equations: a
wrong certified symbol in a dependent row is silently masked, and in a
pivot row it produces a terminal unlocalized integrity failure.  The
close-time audit re-encodes every certified symbol of every SOLVED block
from the solved source rows and REPORTS disagreements — with the absolute
constraint that close status, payload bytes, and the durable CloseRecord
are byte-identical with and without it.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np
import pytest

import holo.core.fountain as fountain
from holo.core.fountain import VolumeCode
from holo.devices.profiles import make_spec
from holo.format.descriptor import FormatSpec
from holo.gen.compose import compose_page_cells
from holo.gen.emit import source_packed_for
from holo.gen.plan import plan_volume
from holo.receive import close_volume
from holo.receive.close_progress import (
    CloseProgress,
    CloseSurplusInconsistency,
    from_fountain_result,
)
from holo.receive.evidence import AttemptStage, AttemptState
from holo.receive.fountain_close import (
    CertifiedStreamSymbol,
    close_record_from_result,
)
from holo.receive.payload import attempt_k_tile
from holo.receive.records import certificate_for_close

_FRONTIER = "a" * 64


@dataclass(frozen=True)
class _AuditFixture:
    spec: FormatSpec
    payload: bytes
    k_total: int
    tiles_x: int
    clean: tuple[CertifiedStreamSymbol, ...]   # ESIs 0..62 of the clean page
    corrupted: dict  # ESI -> individually-valid certificate of a wrong symbol


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
        source_sha256=hashlib.sha256(b"surplus-audit-source").hexdigest(),
        lane_id="surplus-audit-fixture",
        component_block_ids=(
            hashlib.sha256(tag.encode("ascii")).hexdigest(),),
    )
    assert record.state is AttemptState.CERTIFIED and certificate is not None
    return certificate_for_close(certificate, spec)


@pytest.fixture(scope="module")
def audit_fixture() -> _AuditFixture:
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
    # Single-block volume on page 0: ESI == in-block row, so ESIs 0..60
    # are the systematic source rows and 61+ are dense repair rows.
    assert all(code.block_row_of(esi) == (0, esi) for esi in range(63))
    symbols = code.encode_symbols(
        source, np.arange(spec.tiles_per_page, dtype=np.int64)
    )
    clean_page = compose_page_cells(spec, 0, symbols, plan.k_total)
    clean = tuple(
        _certificate(spec, clean_page, index, f"clean-{index}")
        for index in range(63)
    )

    corrupted: dict[int, CertifiedStreamSymbol] = {}
    for esi in (0, 61, 62):
        wrong = symbols.copy()
        wrong[esi, 0] ^= np.uint8(1)
        page = compose_page_cells(spec, 0, wrong, plan.k_total)
        corrupted[esi] = _certificate(spec, page, esi, f"corrupted-{esi}")
        assert not np.array_equal(
            corrupted[esi].symbol, clean[esi].symbol)
    return _AuditFixture(
        spec, payload, plan.k_total, spec.layout.tiles_yx[1],
        clean, corrupted,
    )


def _entry(fixture: _AuditFixture, esi: int) -> CloseSurplusInconsistency:
    ty, tx = divmod(esi, fixture.tiles_x)
    return CloseSurplusInconsistency("main", esi, 0, ty, tx)


# --------------------------------------------------------- (a) clean close

def test_clean_close_verifies_with_empty_audit(
    audit_fixture: _AuditFixture,
) -> None:
    # 61 systematics + repair 61: systematic fast path, repair unconsulted.
    result = close_volume(audit_fixture.clean[0:62], audit_fixture.spec)

    assert result.verified and result.payload == audit_fixture.payload
    assert result.surplus_inconsistencies == ()
    assert from_fountain_result(result).surplus_inconsistencies == ()


# ------------------------------------- (b) dependent-row corruption masked

def test_fast_path_masked_repair_corruption_is_reported(
    audit_fixture: _AuditFixture,
) -> None:
    # All 61 source rows present -> systematic fast path; the corrupted
    # repair at ESI 61 is never consulted by the solve, so the close is
    # VERIFIED with the payload byte-identical to the clean decode — the
    # D16 masked-wrong-certificate case.  Only the audit names the tile.
    clean_result = close_volume(
        audit_fixture.clean[0:62], audit_fixture.spec)
    result = close_volume(
        (*audit_fixture.clean[0:61], audit_fixture.corrupted[61]),
        audit_fixture.spec,
    )

    assert result.verified
    assert result.payload == clean_result.payload == audit_fixture.payload
    assert result.surplus_inconsistencies == (_entry(audit_fixture, 61),)
    # The durable record is identical to the clean decode's: the audit is
    # advisory and never reaches persisted state.
    assert close_record_from_result(result, _FRONTIER) \
        == close_record_from_result(clean_result, _FRONTIER)


def test_ge_dependent_repair_corruption_is_reported(
    audit_fixture: _AuditFixture,
) -> None:
    # Source ESI 0 missing -> real Gauss-Jordan over 60 systematics + 2
    # repairs.  Keystream-frozen fact: repair row 61 carries coefficient
    # bit 0 and becomes the column-0 pivot, so repair 62 is the DEPENDENT
    # row; its corrupted certificate is masked and only audited.
    result = close_volume(
        (
            *audit_fixture.clean[1:61],
            audit_fixture.clean[61],
            audit_fixture.corrupted[62],
        ),
        audit_fixture.spec,
    )

    assert result.verified and result.payload == audit_fixture.payload
    assert result.symbols_used == 62
    assert result.surplus_inconsistencies == (_entry(audit_fixture, 62),)


# ---------------------------------------- (c) pivot corruption still fatal

def test_pivot_corruption_fails_identically_and_audit_localizes(
    audit_fixture: _AuditFixture,
) -> None:
    # Corrupted systematic ESI 0 is a pivot (fast path consumes it), so
    # the recovered stream is wrong and the SHA stop fires — exactly as
    # before the audit existed (pinned against the historical scenario
    # without any surplus equation).  The clean surplus repair at ESI 61
    # disagrees with the wrong reconstruction: that disagreement is the
    # postmortem localization data.
    historical = close_volume(
        (audit_fixture.corrupted[0], *audit_fixture.clean[1:61]),
        audit_fixture.spec,
    )
    result = close_volume(
        (
            audit_fixture.corrupted[0],
            *audit_fixture.clean[1:61],
            audit_fixture.clean[61],
        ),
        audit_fixture.spec,
    )

    for row in (historical, result):
        assert row.status == "integrity_failure"
        assert row.payload is None
        assert "SHA-256" in (row.reason or "")
    assert result.reason == historical.reason
    # With zero surplus equations there is nothing to observe: the exact-K
    # brick keeps an empty audit (the honest D16 limitation)...
    assert historical.surplus_inconsistencies == ()
    # ...but one surplus equation localizes the inconsistent system.
    assert result.surplus_inconsistencies == (_entry(audit_fixture, 61),)
    assert close_record_from_result(result, _FRONTIER) \
        == close_record_from_result(historical, _FRONTIER)


def test_pivot_repair_corruption_can_evade_surplus_observation(
    audit_fixture: _AuditFixture,
) -> None:
    # Corrupt the GE pivot repair (row 61) instead: the solve satisfies
    # every pivot by construction and the lone dependent row 62 happens
    # to be blind to this error direction (row62 . delta = 0, a frozen
    # keystream fact).  Outcome is the unchanged terminal failure with an
    # empty report — the audit promises observation, never detection.
    result = close_volume(
        (
            *audit_fixture.clean[1:61],
            audit_fixture.corrupted[61],
            audit_fixture.clean[62],
        ),
        audit_fixture.spec,
    )

    assert result.status == "integrity_failure"
    assert result.payload is None
    assert "SHA-256" in (result.reason or "")
    assert result.surplus_inconsistencies == ()


# ------------------------------------ (d) zero-outcome-change equivalence

def test_outcomes_identical_with_and_without_audit(
    audit_fixture: _AuditFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenarios = {
        "clean": audit_fixture.clean[0:62],
        "masked-fast-path": (
            *audit_fixture.clean[0:61], audit_fixture.corrupted[61]),
        "masked-ge": (
            *audit_fixture.clean[1:61],
            audit_fixture.clean[61],
            audit_fixture.corrupted[62],
        ),
        "pivot-brick": (
            audit_fixture.corrupted[0],
            *audit_fixture.clean[1:61],
            audit_fixture.clean[61],
        ),
        "open-shortfall": audit_fixture.clean[0:48],
    }
    with_audit = {
        name: close_volume(certs, audit_fixture.spec)
        for name, certs in scenarios.items()
    }
    monkeypatch.setattr(
        fountain.Decoder, "audit_solved_symbols", lambda self: ())
    without_audit = {
        name: close_volume(certs, audit_fixture.spec)
        for name, certs in scenarios.items()
    }

    expected_status = {
        "clean": "verified",
        "masked-fast-path": "verified",
        "masked-ge": "verified",
        "pivot-brick": "integrity_failure",
        "open-shortfall": "open",
    }
    audited = {"masked-fast-path", "masked-ge", "pivot-brick"}
    for name in scenarios:
        on, off = with_audit[name], without_audit[name]
        assert on.status == off.status == expected_status[name], name
        assert on.payload == off.payload, name
        if expected_status[name] == "verified":
            assert on.payload == audit_fixture.payload, name
        assert on.k_total == off.k_total, name
        assert on.blocks == off.blocks, name
        assert on.symbols_used == off.symbols_used, name
        assert on.reason == off.reason, name
        assert on.metadata_version == off.metadata_version, name
        assert on.diagnostics == off.diagnostics, name
        assert off.surplus_inconsistencies == (), name
        assert bool(on.surplus_inconsistencies) == (name in audited), name
        if on.status != "open":
            assert close_record_from_result(on, _FRONTIER) \
                == close_record_from_result(off, _FRONTIER), name


# --------------------------------------------- progress + CLI advisories

def test_progress_detaches_and_validates_surplus_entries(
    audit_fixture: _AuditFixture,
) -> None:
    result = close_volume(
        (*audit_fixture.clean[0:61], audit_fixture.corrupted[61]),
        audit_fixture.spec,
    )
    progress = from_fountain_result(result)
    assert progress.surplus_inconsistencies == (_entry(audit_fixture, 61),)

    with pytest.raises(TypeError, match="foreign surplus"):
        CloseProgress(None, 0, surplus_inconsistencies=("main",))
    with pytest.raises(ValueError, match="non-empty text"):
        CloseSurplusInconsistency("", 1, 0, 0, 1)
    with pytest.raises(ValueError, match="non-negative"):
        CloseSurplusInconsistency("main", -1, 0, 0, 1)


def test_cli_warning_lists_tiles_on_both_endings(capsys) -> None:
    from types import SimpleNamespace

    from holo.cli import _print_surplus_audit

    progress = CloseProgress(
        61, 62,
        surplus_inconsistencies=(
            CloseSurplusInconsistency("main", 61, 0, 2, 13),),
    )
    res = SimpleNamespace(close_progress=lambda: progress)

    _print_surplus_audit(res, verified=True)
    verified_out = capsys.readouterr().out
    assert "WARNING: surplus-consistency audit" in verified_out
    assert "1 certified symbol(s) disagree" in verified_out
    assert "stream main page 0 tile (2,13) counter 61" in verified_out
    assert "payload verified by SHA-256 and is unaffected" in verified_out

    _print_surplus_audit(res, verified=False)
    failed_out = capsys.readouterr().out
    assert "stream main page 0 tile (2,13) counter 61" in failed_out
    assert "postmortem" in failed_out


def test_cli_warning_silent_without_findings(capsys) -> None:
    from types import SimpleNamespace

    from holo.cli import _print_surplus_audit

    _print_surplus_audit(SimpleNamespace(), verified=False)
    _print_surplus_audit(
        SimpleNamespace(close_progress=lambda: None), verified=True)
    _print_surplus_audit(
        SimpleNamespace(
            close_progress=lambda: CloseProgress(None, 0)),
        verified=False,
    )

    def broken() -> CloseProgress:
        raise RuntimeError("advisory failure must never mask the exit path")

    _print_surplus_audit(
        SimpleNamespace(close_progress=broken), verified=True)
    assert capsys.readouterr().out == ""
