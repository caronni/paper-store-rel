"""Phase-2 close-schedule pins (PAYLOAD-REWORK-PLAN 2.1-2.6).

Direct fixtures for the D8 branches the sole prior gate test never
executed (PAYLOAD-IMPROVEMENTS lens-coverage:03): the want_more shortfall
baseline (skip below gain, consult at gain), rewound/foreign baseline
reset, metadata-terminal precedence in BOTH its raising and non-raising
forms (the non-raising form crashed with ``VolumeCode(None, ...)`` before
the Phase-2 repair, fountain-close:02), the gated-skip count-only
progress shape (production-drivers:01 crash regression + fountain-
close:05 fake-rank repair), the ProductionClose conversion memo
(lens-efficiency:02), the K advisory preclose (ruling 6.6), the
reproduction-path close-progress sink (lens-doc-v33:09), and the D5
dropped-disagreement counter's fold + CLI epilogue (ruling 11.2).

Stub CloseResults drive ``_note``/``_gated`` per the plan's explicit
allowance; the certificates themselves are REAL durable records so the
conversion/memo path runs the production code.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from holo.devices.profiles import make_spec
from holo.gen.compose import compose_page_cells
from holo.gen.emit import source_packed_for
from holo.gen.plan import plan_volume
from holo.core.fountain import VolumeCode
from holo.receive import _diagnostic_snapshots as diagnostic_snapshots
from holo.receive import production_close, production_payload
from holo.receive.close_progress import CloseBlockProgress, CloseProgress
from holo.receive.diag.rows import close_row
from holo.receive.evidence import AttemptStage, AttemptState
from holo.receive.evidence_blocks import (
    EvidenceOrigin,
    block_from_rows,
)
from holo.receive.evidence_context import EvidenceContext
from holo.receive.fountain_close import (
    CloseResult,
    close_count_status,
)
from holo.receive import fountain_close
from holo.receive.payload import attempt_k_tile
from holo.receive.payload_model import CaptureEvidence, EvidenceSource
from holo.receive.placement.model import AddressResult
from holo.receive.records import (
    certificate_record_from_user_bits,
    stream_attempt_identity,
)
from holo.receive.runtime import (
    CloseContext,
    CloseExecution,
    LaneContext,
    _replay_deferred_close,
)
from holo.receive.scan import open_capture
from holo.receive.session import CaptureFacts, SessionStatus
from holo.receive.session_model import SessionCounters
from holo.receive.types import (
    AddressArtifact,
    AddressProduct,
    CloseRecord,
    CloseStatus,
    LaneSpec,
    Stage,
    SurveyArtifact,
    SurveyProduct,
    TileAttemptRecord,
    TileCertificateRecord,
)


LANE = "l00-2ppc-600dpi"


@pytest.fixture(scope="module")
def records_fixture() -> tuple[object, tuple[TileCertificateRecord, ...]]:
    """80 real durable K certificates of one c3 volume (K=61)."""
    spec = make_spec("c3-r0550", "default")
    payload = hashlib.sha256(b"close-schedule-pins").digest() * 500
    plan = plan_volume(spec, len(payload), 0.75)
    assert plan.k_total == 61
    source = source_packed_for(payload, plan)
    code = VolumeCode(
        plan.k_total, plan.symbol_bits, spec.seed,
        tiles_per_page=spec.tiles_per_page)
    symbols = code.encode_symbols(
        source, np.arange(spec.tiles_per_page, dtype=np.int64))
    page = compose_page_cells(spec, 0, symbols, plan.k_total)
    _tiles_y, tiles_x = spec.layout.tiles_yx
    rows = []
    for index in range(80):
        tile_y, tile_x = divmod(index, tiles_x)
        tile = page[tile_y * 64:(tile_y + 1) * 64,
                    tile_x * 64:(tile_x + 1) * 64]
        record, certificate = attempt_k_tile(
            (tile.astype(np.float64) * 2.0 - 1.0) * 5.0,
            spec,
            (0, tile_y, tile_x),
            AttemptStage.SCAN,
            source_sha256=hashlib.sha256(b"close-schedule").hexdigest(),
            lane_id=LANE,
            component_block_ids=(
                hashlib.sha256(f"c-{index}".encode()).hexdigest(),),
        )
        assert record.state is AttemptState.CERTIFIED
        assert certificate is not None
        rows.append(certificate)
    return spec, tuple(rows)


def _state(records: tuple) -> SimpleNamespace:
    return SimpleNamespace(certificates=tuple(records), close=CloseRecord())


def _open_result(k_total: int, have: int, rank: int) -> CloseResult:
    return CloseResult(
        status="open", payload=None, k_total=k_total,
        blocks=(CloseBlockProgress(0, k_total, have, rank, False),),
        symbols_used=have,
        reason="stub open",
        diagnostics={
            "metadata_rank": 24, "metadata_rank_shortfall": 0,
            "metadata_check_shortfall": 0, "metadata_inconsistent": False,
            "n_unique_metadata_counters": have,
        },
    )


def _counting_close(monkeypatch, results):
    """Install a close_volume stub yielding ``results`` in order."""
    calls: list[tuple] = []

    def stub(certs, spec):
        calls.append(tuple(certs))
        return results[len(calls) - 1]

    monkeypatch.setattr(production_close, "close_volume", stub)
    return calls


# --- (a) want_more shortfall baseline: skip below gain, consult at gain --


def test_baseline_skips_below_shortfall_and_consults_at_gain(
    records_fixture, monkeypatch,
) -> None:
    spec, records = records_fixture
    close = production_close.ProductionClose()
    # First consult: open at rank 48/61 (shortfall 13) with 61 distinct.
    calls = _counting_close(
        monkeypatch, [_open_result(61, 61, 48), _open_result(61, 74, 61)])
    first = close.process(CloseContext(spec, _state(records[:61])))
    assert len(calls) == 1
    assert first.record == CloseRecord()

    # +4 distinct ESIs < shortfall 13 -> provably-open skip, no consult.
    skipped = close.process(CloseContext(spec, _state(records[:65])))
    assert len(calls) == 1
    assert skipped.record == CloseRecord()
    assert skipped.payload is None

    # (f) crash regression: the gated skip's progress WORKS over >=1
    # certificate (it fed raw TileCertificateRecord rows before Phase 2)
    # and carries the count-only marking.
    progress = skipped.diagnostic_progress()
    assert type(progress) is CloseProgress
    assert progress.count_only is True
    assert progress.k_total == 61
    assert progress.blocks and progress.blocks[0].have == 65
    assert progress.metadata is not None
    assert progress.metadata.rank == 24

    # +13 distinct ESIs == shortfall -> the fountain must be asked.
    consulted = close.process(CloseContext(spec, _state(records[:74])))
    assert len(calls) == 2
    assert calls[1] and len(calls[1]) == 74
    assert consulted.diagnostic_progress().count_only is False


# --- (b) rewound/foreign baseline resets and consults ---------------------


def test_rewound_state_resets_baseline_and_consults(
    records_fixture, monkeypatch,
) -> None:
    spec, records = records_fixture
    close = production_close.ProductionClose()
    calls = _counting_close(
        monkeypatch, [_open_result(61, 65, 48), _open_result(61, 61, 48)])
    close.process(CloseContext(spec, _state(records[:65])))
    assert len(calls) == 1
    # A foreign/rewound frontier (61 < baseline 65) resets and consults.
    close.process(CloseContext(spec, _state(records[:61])))
    assert len(calls) == 2


# --- (c) metadata-terminal precedence, raising AND non-raising ------------


def test_close_count_status_metadata_terminal_forms(monkeypatch) -> None:
    """Non-raising terminal states are (ready, no counts); K=None never
    reaches VolumeCode (the fountain-close:02 TypeError)."""
    spec = make_spec("c3-r0550", "default")

    def terminal(state):
        return lambda certs, spec: (None, None, {"state": state})

    for state in ("malformed", "unsupported"):
        monkeypatch.setattr(
            fountain_close, "metadata_from_certificates", terminal(state))
        assert close_count_status((), spec) == (True, None)
    monkeypatch.setattr(
        fountain_close, "metadata_from_certificates", terminal("incomplete"))
    assert close_count_status((), spec) == (False, None)

    def raising(certs, spec):
        raise fountain_close.MetadataIntegrityError("stub", {})

    monkeypatch.setattr(
        fountain_close, "metadata_from_certificates", raising)
    assert close_count_status((), spec) == (True, None)


def test_metadata_terminal_consults_past_an_armed_baseline(
    records_fixture, monkeypatch,
) -> None:
    """(ready, counts=None) consults unconditionally — the documented
    precedence — even while a want_more baseline is armed."""
    spec, records = records_fixture
    close = production_close.ProductionClose()
    calls = _counting_close(
        monkeypatch, [_open_result(61, 61, 48), _open_result(61, 61, 48)])
    close.process(CloseContext(spec, _state(records[:61])))
    assert len(calls) == 1
    monkeypatch.setattr(
        production_close, "close_count_status",
        lambda certs, spec: (True, None))
    close.process(CloseContext(spec, _state(records[:61])))
    assert len(calls) == 2, "metadata-terminal state must consult"


# --- (d) gated-skip renders count-only, never a fake rank -----------------


def test_gated_skip_snapshot_and_cli_render_count_only(
    records_fixture, monkeypatch, capsys,
) -> None:
    spec, records = records_fixture
    close = production_close.ProductionClose()
    _counting_close(monkeypatch, [_open_result(61, 61, 48)])
    close.process(CloseContext(spec, _state(records[:61])))
    skipped = close.process(CloseContext(spec, _state(records[:62])))

    snapshot = diagnostic_snapshots.close_factory(
        None, skipped.record, skipped.diagnostic_progress, spec)()
    assert snapshot["deferred_counts"] is True
    row = close_row(snapshot)
    assert "rank/solve deferred" in row
    assert "rank 0/" not in row

    from holo.cli import _print_close_shortfall
    _print_close_shortfall(
        SimpleNamespace(close_progress=skipped.diagnostic_progress),
        suppress_rescan_hint=True)
    out = capsys.readouterr().out
    assert "rank/solve not computed" in out
    assert "distinct-symbol reach 62/61" in out
    assert "blocks solved" not in out
    assert "symbol-rank shortfall" not in out


# --- (e) reproduction paths populate the close-progress sink --------------


def test_replay_deferred_close_populates_progress_sink() -> None:
    progress = CloseProgress(61, 61, count_only=True)
    execution = CloseExecution(CloseRecord(), None, lambda: progress)
    pipeline = SimpleNamespace(
        close=SimpleNamespace(process=lambda context: execution))
    state = SimpleNamespace(
        certificates=(), close=CloseRecord(), status=SessionStatus.OPEN)
    events = SimpleNamespace(emit=lambda *args, **kwargs: None)
    sink: list = []
    payload, snapshot_factory = _replay_deferred_close(
        state, make_spec("c3-r0550", "default"), pipeline, events,
        close_progress_sink=sink)
    assert payload is None
    assert sink and sink[0]() is progress
    assert snapshot_factory()["deferred_counts"] is True


def test_gated_verified_state_asks_fountain_not_wrap_empty_payload(
    monkeypatch,
) -> None:
    """Verified resume must not build CloseExecution(verified, None).

    The skip object used to be constructed eagerly from ``state.close``.
    On a VERIFIED state that trips the payload invariant even when the
    gate would later return None / consult the fountain.
    """
    payload = b"verified-resume"
    sha = hashlib.sha256(payload).hexdigest()
    verified = CloseRecord(
        status=CloseStatus.VERIFIED,
        certificate_frontier_sha256="ab" * 32,
        payload_sha256=sha,
        payload_length=len(payload),
        metadata_version=0,
    )
    spec = make_spec("c3-r0550", "default")
    state = SimpleNamespace(close=verified, certificates=())
    close = production_close.ProductionClose()

    # Would have been the crash path: not-ready → return skip(verified, None).
    monkeypatch.setattr(
        production_close, "close_count_status",
        lambda certs, spec: (False, None))

    result = CloseResult(
        status="verified",
        payload=payload,
        metadata_version=0,
        k_total=1,
        blocks=(),
        reason="",
    )
    monkeypatch.setattr(production_close, "close_volume", lambda c, s: result)
    monkeypatch.setattr(
        production_close, "close_record_from_result",
        lambda result, frontier: verified)

    out = close.process(CloseContext(spec, state))
    assert out.record is verified
    assert out.payload == payload


# --- 2.2: the conversion memo (once per certificate_id, ever) -------------


def test_close_conversion_memo_converts_each_certificate_once(
    records_fixture, monkeypatch,
) -> None:
    spec, records = records_fixture
    conversions: list[str] = []
    real = production_close.certificate_for_close

    def counting(record, spec):
        conversions.append(record.certificate_id)
        return real(record, spec)

    monkeypatch.setattr(
        production_close, "certificate_for_close", counting)
    close = production_close.ProductionClose()
    _counting_close(monkeypatch, [_open_result(61, 61, 48)])
    state = _state(records[:61])
    first = close.process(CloseContext(spec, state))
    assert len(conversions) == 61
    # Second consult over the same frontier: gate skips AND no certificate
    # converts again (mint-once memo per certificate_id).
    second = close.process(CloseContext(spec, state))
    assert len(conversions) == 61
    assert second.record == first.record
    # A grown frontier converts only its novel rows.
    close.process(CloseContext(spec, _state(records[:63])))
    assert len(conversions) == 63


# --- 2.4: the K advisory preclose (ruling 6.6) ----------------------------


def _k_source(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _k_block(spec, source: str, address=(0, 0, 0)):
    origin = EvidenceOrigin(f"{source}/{LANE}/patch-0", 0, 0.1)
    return block_from_rows(
        source, LANE, address[0], address[1:],
        ((flat, np.asarray([1.5], np.float32), origin)
         for flat in (3, 9, 40)),
        kind="k")


def _k_context(spec, source: str, events, *, defer=False) -> LaneContext:
    raster = open_capture(np.zeros((2, 2), np.uint8), 600.0)
    facts = CaptureFacts(
        source, raster.dpi, raster.source.dtype, raster.source.shape,
        raster.source.channels)
    return LaneContext(
        Stage.PAYLOAD,
        LaneSpec(LANE, 2, 1, 1, 1),
        spec,
        raster,
        facts,
        EvidenceContext(),
        lambda: True,
        lambda: False,
        lambda name, *_args, **kwargs: events.append(
            (name, kwargs.get("details", ()))),
        lambda _name, callback: callback(),
        defer,
    )


def _drive_k_payload(monkeypatch, spec, *, defer: bool,
                     close_status: str, fail_second: bool = True):
    """Run ProductionPayload to completion over two stub addresses."""
    source = _k_source("k-preclose")
    blocks = (_k_block(spec, source, (0, 0, 0)),
              _k_block(spec, source, (0, 0, 1)))
    empty = CaptureEvidence(
        EvidenceSource(source, LANE), spec.spec_id, (), (), ())
    monkeypatch.setattr(
        production_payload.payload, "collect_capture_evidence",
        lambda *_args, **_kwargs: empty)
    address_state = AddressResult((), (), (), (), 0)
    # v0.42: no refinement stub — inline certified pose refinement moved
    # to the R(Lk) levels; ordinary lanes are generation-zero only.
    monkeypatch.setattr(
        production_payload, "blocks_from_frontier",
        lambda *_args, **_kwargs: blocks)

    def fake_attempt(_llr, actual_spec, address, stage, *,
                     source_sha256, lane_id, component_block_ids,
                     dependency_certificate_ids):
        assert actual_spec is spec
        succeeds = not (fail_second and address == (0, 0, 1))
        attempt_id = stream_attempt_identity(
            spec, address, "main", stage, component_block_ids)
        certificate = None
        if succeeds:
            profile = spec.stream_profiles[0]
            certificate = certificate_record_from_user_bits(
                spec, page=address[0], tile_yx=address[1:],
                stream_id="main",
                user_bits=np.zeros(profile.user_bits, np.uint8),
                origin_attempt_id=attempt_id)
        record = TileAttemptRecord(
            attempt_id=attempt_id,
            source_sha256=source_sha256,
            lane_id=lane_id,
            page=address[0],
            tile_yx=address[1:],
            stage=stage,
            state=(AttemptState.CERTIFIED if succeeds
                   else AttemptState.ATTEMPTED_FAILED),
            n_informative=3,
            n_iters=1 if succeeds else 120,
            syndrome_ok=succeeds,
            crc_ok=True if succeeds else None,
            component_block_ids=component_block_ids,
            dependency_certificate_ids=dependency_certificate_ids,
            certificate_id=(
                None if certificate is None
                else certificate.certificate_id),
            stream_id="main",
            child_outcomes=((1, True),) if succeeds else ((120, False),),
        )
        return record, certificate

    monkeypatch.setattr(
        production_payload.payload, "attempt_k_tile", fake_attempt)
    close_calls: list[tuple] = []
    count_ready_calls: list[bool] = []

    def fake_count_ready(certs, actual_spec):
        count_ready_calls.append(True)
        return True

    monkeypatch.setattr(
        production_payload, "close_count_ready", fake_count_ready)
    monkeypatch.setattr(
        production_payload, "close_volume",
        lambda certs, actual_spec: (
            close_calls.append(tuple(certs)),
            SimpleNamespace(status=close_status))[1])

    events: list = []
    context = _k_context(spec, source, events, defer=defer)
    survey = SurveyProduct(SurveyArtifact("survey-k", ()), ())
    address = AddressProduct(
        AddressArtifact("address-k", "survey-k", (), ()), (), (),
        transient=address_state)
    execution = production_payload.ProductionPayload().process(
        context, survey, address)
    return execution.product, close_calls, count_ready_calls, events


def test_k_preclose_terminal_suppresses_retry150(monkeypatch) -> None:
    """Ruling 6.6: K wires the same advisory preclose as color — one
    consult after the ordinary batch, converted certificates in, and a
    terminal answer spends zero retry150 budget on the failed baseline."""
    spec = make_spec("c3-r0550", "default")
    product, close_calls, _ready, events = _drive_k_payload(
        monkeypatch, spec, defer=False, close_status="verified")
    assert len(close_calls) == 1
    assert all(type(row) is fountain_close.CertifiedStreamSymbol
               for row in close_calls[0])
    # One address failed its SCAN baseline, yet no retry150 ran.
    assert any(row.state is AttemptState.ATTEMPTED_FAILED
               for row in product.attempts)
    assert all(row.stage is not AttemptStage.RETRY150
               for row in product.attempts)
    details = dict(
        (row.name, row.value)
        for name, rows in events if name == "payload.complete"
        for row in rows)
    assert details["payload.preclose_attempted"] is True
    assert details["payload.terminal_close"] is True
    assert details["payload.retry150_attempts"] == 0


def test_k_preclose_open_answer_still_spends_retry(monkeypatch) -> None:
    spec = make_spec("c3-r0550", "default")
    product, close_calls, _ready, _events = _drive_k_payload(
        monkeypatch, spec, defer=False, close_status="open")
    assert len(close_calls) == 1
    assert any(row.stage is AttemptStage.RETRY150
               for row in product.attempts)


def test_k_preclose_suppressed_under_deferred_close(monkeypatch) -> None:
    """--complete suppression is inherited through the engine flag: the
    fountain is never consulted mid-run and retry150 still runs."""
    spec = make_spec("c3-r0550", "default")
    product, close_calls, count_ready_calls, _events = _drive_k_payload(
        monkeypatch, spec, defer=True, close_status="verified")
    assert close_calls == []
    assert count_ready_calls == []
    assert any(row.stage is AttemptStage.RETRY150
               for row in product.attempts)


def test_k_payload_policy_literal_carries_preclose() -> None:
    assert production_payload.ProductionPayload.policy_id == (
        "holo/e023b-e023c-payload/paperholo-e023b-e023c-v12-r-lane/"
        "needmap-region-prune-label-rows-owner-prune-acquisition-"
        "components-max60-preclose-selective-retry150-unified-cert-identity-"
        "stripes-xy")


# --- the D5 drop tally reaches SessionCounters + the epilogue -------------
# (2026-08-02 ruling: dropped observations + winner flips replace the
# v0.36 byte-inequality disagreement count.)


def test_drop_tally_folds_into_session_counters() -> None:
    counters = SessionCounters()
    folded = counters.fold((), (), 3, 1)
    assert folded.mopup_dropped_observations == 3
    assert folded.mopup_winner_flips == 1
    folded = folded.fold((), (), 2, 2)
    assert folded.mopup_dropped_observations == 5
    assert folded.mopup_winner_flips == 3
    with pytest.raises(ValueError, match=">= 0"):
        counters.fold((), (), -1, 0)
    with pytest.raises(ValueError, match=">= 0"):
        counters.fold((), (), 0, -1)
    with pytest.raises(ValueError, match="cannot exceed"):
        counters.fold((), (), 1, 2)
    with pytest.raises(ValueError, match=">= 0"):
        SessionCounters(mopup_dropped_observations=-1)
    with pytest.raises(ValueError, match="cannot exceed"):
        SessionCounters(mopup_dropped_observations=1, mopup_winner_flips=2)


def test_mopup_drop_epilogue_prints_only_when_nonzero(
    capsys,
) -> None:
    from holo.cli import _print_mopup_drops
    silent = SimpleNamespace(state=SimpleNamespace(
        counters=SessionCounters()))
    _print_mopup_drops(silent)
    assert capsys.readouterr().out == ""
    noisy = SimpleNamespace(state=SimpleNamespace(
        counters=SessionCounters(
            mopup_dropped_observations=8, mopup_winner_flips=2)))
    _print_mopup_drops(noisy)
    out = capsys.readouterr().out
    assert "dropped 8 re-observation(s)" in out
    assert "winner flips 2 (25.0%)" in out
    assert "two-view consistency canary" in out
