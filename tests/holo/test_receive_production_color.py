"""Production color scheduling, selective streams, and retry provenance."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

from holo.format import pilots
from holo.format.registry import get_format_row
from holo.receive import payload_engine, production_color
from holo.receive.cascade import scale_plan
from holo.receive.color_attempts import ColorAttemptResult
from holo.receive.color_payload import (
    ColorCaptureEvidence,
    ColorRegionSummary,
)
from holo.receive.color_registration import PlaneResidual
from holo.receive.evidence import AttemptStage, AttemptState
from holo.receive.evidence_blocks import (
    EvidenceOrigin,
    block_from_rows,
)
from holo.receive.evidence_context import EvidenceContext
from holo.receive.fountain_close import (
    close_record_from_result,
    close_volume,
)
from holo.receive.payload_model import EvidenceSource
from holo.receive.placement.model import AddressResult
from holo.receive.records import (
    certificate_for_close,
    certificate_record_from_user_bits,
    stream_attempt_identity,
)
from holo.receive.runtime import LaneContext
from holo.receive.scan import open_capture
from holo.receive.session import (
    BarrierDelta,
    CaptureFacts,
    LevelRecord,
    SessionIndex,
    SessionState,
    apply_close,
    append_level_barrier,
    certificate_frontier_sha256,
    load_session,
    save_session,
)
from holo.receive.session_validation import validate_attempt
from holo.receive.types import (
    AddressArtifact,
    AddressProduct,
    LaneSpec,
    PayloadArtifact,
    Stage,
    SurveyArtifact,
    SurveyProduct,
    TileAttemptRecord,
)


LANE = "l00-2ppc-600dpi"
ADDRESS = (0, 0, 0)


def _source(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _block(spec, source: str, address=ADDRESS):
    origin = EvidenceOrigin(f"{source}/{LANE}/patch-0", 0, 0.1)
    payload = pilots.color_payload_cell_indices(spec.family_seed)
    kind = "cmy7" if spec.codec_id.startswith("cmy7-") else "cmy8"
    values = (
        np.asarray((2.0, -1.0, 0.5, 1.5, -0.5, 0.25))
        if kind == "cmy7"
        else np.asarray((2.0, -1.0, 0.5))
    )
    return block_from_rows(
        source,
        LANE,
        *address[:1],
        address[1:],
        (
            (int(flat), values, origin)
            for flat in payload
        ),
        kind=kind,
    )


def test_terminal_color_close_keeps_valid_live_frontier_through_replay(
    tmp_path,
) -> None:
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    source = _source("terminal-frontier")
    block = _block(spec, source)
    attempt_ids = {
        stream_id: stream_attempt_identity(
            spec,
            ADDRESS,
            stream_id,
            AttemptStage.SCAN,
            (block.block_id,),
        )
        for stream_id in spec.stream_ids
    }
    certificates = []
    for stream_id, metadata_bit in (("C", 0), ("M", 1)):
        profile = next(
            row for row in spec.stream_profiles
            if row.stream_id == stream_id)
        user_bits = np.zeros(profile.user_bits, np.uint8)
        user_bits[0] = metadata_bit
        certificates.append(certificate_record_from_user_bits(
            spec,
            page=ADDRESS[0],
            tile_yx=ADDRESS[1:],
            stream_id=stream_id,
            user_bits=user_bits,
            origin_attempt_id=attempt_ids[stream_id],
        ))
    certificate_by_stream = {
        row.stream_id: row for row in certificates}
    attempts = tuple(
        TileAttemptRecord(
            attempt_id=attempt_ids[stream_id],
            source_sha256=source,
            lane_id=LANE,
            page=ADDRESS[0],
            tile_yx=ADDRESS[1:],
            stage=AttemptStage.SCAN,
            state=(
                AttemptState.CERTIFIED
                if stream_id in certificate_by_stream
                else AttemptState.ATTEMPTED_FAILED
            ),
            n_informative=block.n_observed,
            n_iters=1 if stream_id in certificate_by_stream else 120,
            syndrome_ok=stream_id in certificate_by_stream,
            crc_ok=(
                True if stream_id in certificate_by_stream else None),
            component_block_ids=(block.block_id,),
            dependency_certificate_ids=(),
            certificate_id=(
                certificate_by_stream[stream_id].certificate_id
                if stream_id in certificate_by_stream
                else None
            ),
            stream_id=stream_id,
            child_outcomes=(
                ((1, True),)
                if stream_id in certificate_by_stream
                else ((120, False),)
            ),
        )
        for stream_id in spec.stream_ids
    )
    survey = SurveyArtifact("survey-terminal-frontier", ())
    address = AddressArtifact(
        "address-terminal-frontier", survey.survey_id, (), ())
    payload = PayloadArtifact(
        "payload-terminal-frontier",
        address.address_id,
        tuple(row.certificate_id for row in certificates),
        n_blocks=1,
        n_attempts=len(attempts),
    )
    # v0.33: persisted states re-derive the plan from format policy, so
    # the fixture plan must come from scale_plan (ladder + mop-up + R
    # entries, plus PK4.3's supplemental tail on a COLOR coding — hence
    # the codec_id, which is what `validate_state_for_spec` re-derives).
    plan = scale_plan(600.0, spec.cell_dots,
                      codec_family=spec.codec_family,
                      n_streams=spec.n_streams)
    assert plan[0].lane_id == LANE
    initial = SessionState.create(
        spec.spec_id,
        "test/terminal-frontier-v1",
        (0,),
    )
    state = append_level_barrier(
        initial,
        SessionIndex(initial),
        CaptureFacts(source, 600.0, "uint8", (2, 2), 3),
        plan,
        LevelRecord(survey, address, payload),
        BarrierDelta(
            blocks=(block,),
            attempts=attempts,
            certificates=tuple(certificates),
        ),
    )
    result = close_volume(
        tuple(certificate_for_close(row, spec) for row in certificates),
        spec,
    )
    assert result.status == "integrity_failure"
    closed = apply_close(
        state,
        close_record_from_result(
            result, certificate_frontier_sha256(state.certificates)),
    )
    assert closed.blocks == (block,)
    path = tmp_path / "terminal-color-live-frontier.json"
    assert save_session(path, closed)
    assert load_session(path) == closed


def _context(
    spec,
    current_source,
    prior_block,
    events,
    snapshot_factories=None,
    *,
    defer_fountain_close=False,
):
    raster = open_capture(np.zeros((2, 2, 3), np.uint8), 600.0)
    facts = CaptureFacts(
        current_source,
        raster.dpi,
        raster.source.dtype,
        raster.source.shape,
        raster.source.channels,
    )
    return LaneContext(
        Stage.PAYLOAD,
        LaneSpec(LANE, 2, 1, 1, 1),
        spec,
        raster,
        facts,
        EvidenceContext(
            prior_capture_blocks=(
                () if prior_block is None else (prior_block,)),
        ),
        lambda: True,
        lambda: snapshot_factories is not None,
        lambda name, *_args, **kwargs: (
            events.append((name, kwargs.get("details", ()))),
            (
                None
                if snapshot_factories is None
                else snapshot_factories.append(
                    kwargs.get("snapshot_factory"))
            ),
        ),
        lambda _name, callback: callback(),
        defer_fountain_close,
    )


def test_fully_certified_color_address_skips_attempt_view_materialization(
    monkeypatch,
) -> None:
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    current_source = _source("already-certified-color")
    block = _block(spec, current_source)
    certificates = []
    for stream_id in spec.stream_ids:
        profile = next(
            row for row in spec.stream_profiles
            if row.stream_id == stream_id)
        attempt_id = stream_attempt_identity(
            spec,
            ADDRESS,
            stream_id,
            AttemptStage.SCAN,
            (block.block_id,),
        )
        certificates.append(certificate_record_from_user_bits(
            spec,
            page=ADDRESS[0],
            tile_yx=ADDRESS[1:],
            stream_id=stream_id,
            user_bits=np.zeros(profile.user_bits, np.uint8),
            origin_attempt_id=attempt_id,
        ))

    events = []
    context = _context(spec, current_source, None, events)
    context = replace(
        context,
        evidence=EvidenceContext(certificates=tuple(certificates)),
    )
    empty = ColorCaptureEvidence(
        EvidenceSource(current_source, LANE),
        spec.spec_id,
        "cmy8",
        (),
        (),
        (),
    )
    collection_filters = []

    def collect_pruned(*_args, **kwargs):
        collection_filters.append(kwargs["certificates"])
        return empty

    monkeypatch.setattr(
        production_color,
        "collect_color_evidence",
        collect_pruned,
    )

    def forbidden_view(_blocks):
        raise AssertionError(
            "fully certified color address built an attempt view")

    monkeypatch.setattr(
        payload_engine, "tile_attempt_view", forbidden_view)
    survey = SurveyProduct(SurveyArtifact("survey-certified", ()), ())
    address_state = AddressResult((), (), (), (), 0)
    address = AddressProduct(
        AddressArtifact(
            "address-certified", "survey-certified", (), ()),
        (),
        (),
        transient=address_state,
    )

    execution = production_color.ProductionColorPayload().process(
        context, survey, address)

    product = execution.product
    assert product is not None
    assert collection_filters == [tuple(certificates)]
    assert product.blocks == ()
    assert product.attempts == ()
    assert product.certificates == ()
    assert product.divergences == ()


def test_partially_certified_color_address_attempts_only_missing_streams(
    monkeypatch,
) -> None:
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    current_source = _source("partially-certified-color")
    block = _block(spec, current_source)
    profile = next(
        row for row in spec.stream_profiles if row.stream_id == "C")
    prior_attempt_id = stream_attempt_identity(
        spec, ADDRESS, "C", AttemptStage.SCAN, (block.block_id,))
    prior_certificate = certificate_record_from_user_bits(
        spec,
        page=ADDRESS[0],
        tile_yx=ADDRESS[1:],
        stream_id="C",
        user_bits=np.zeros(profile.user_bits, np.uint8),
        origin_attempt_id=prior_attempt_id,
    )
    events = []
    context = replace(
        _context(spec, current_source, None, events),
        evidence=EvidenceContext(certificates=(prior_certificate,)),
    )
    empty = ColorCaptureEvidence(
        EvidenceSource(current_source, LANE),
        spec.spec_id,
        "cmy8",
        (),
        (),
        (),
    )
    filters = []
    monkeypatch.setattr(
        production_color,
        "collect_color_evidence",
        lambda *_args, **kwargs: (
            filters.append(kwargs["certificates"]),
            empty,
        )[1],
    )
    monkeypatch.setattr(
        production_color,
        "color_blocks_from_frontier",
        lambda *_args, **_kwargs: (block,),
    )
    attempted_streams = []

    def below_floor(
        view,
        actual_spec,
        stream_id,
        stage,
        *,
        source_sha256,
        lane_id,
    ):
        assert actual_spec is spec
        attempted_streams.append((stage, stream_id))
        return ColorAttemptResult(
            TileAttemptRecord(
                attempt_id=stream_attempt_identity(
                    spec,
                    view.address,
                    stream_id,
                    stage,
                    view.component_block_ids,
                ),
                source_sha256=source_sha256,
                lane_id=lane_id,
                page=view.address[0],
                tile_yx=view.address[1:],
                stage=stage,
                state=AttemptState.BELOW_ATTEMPT_FLOOR,
                n_informative=0,
                n_iters=0,
                syndrome_ok=None,
                crc_ok=None,
                component_block_ids=view.component_block_ids,
                dependency_certificate_ids=(),
                stream_id=stream_id,
            ),
            None,
        )

    monkeypatch.setattr(
        production_color, "attempt_color_tile", below_floor)
    monkeypatch.setattr(
        production_color,
        "certificate_divergence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("prior certified stream was divergence-audited")),
    )
    survey = SurveyProduct(SurveyArtifact("survey-partial", ()), ())
    address = AddressProduct(
        AddressArtifact(
            "address-partial", "survey-partial", (), ()),
        (),
        (),
        transient=AddressResult((), (), (), (), 0),
    )

    execution = production_color.ProductionColorPayload().process(
        context, survey, address)

    product = execution.product
    assert product is not None
    assert filters == [(prior_certificate,)]
    assert attempted_streams == [
        (AttemptStage.SCAN, "M"),
        (AttemptStage.SCAN, "Y"),
    ]
    assert product.blocks == (block,)
    assert product.divergences == ()


def test_region_event_reports_measured_registration_not_adoption() -> None:
    """P8: payload.region carries the measurement, not the adoption.

    A non-adopted region has still MEASURED its per-plane registration.
    The event reports that measurement under ``color.registration.*`` and
    keeps adoption on ``color.registration_adopted``; a zero appears only
    where registration genuinely found no anchors.
    """
    measured = (
        PlaneResidual((0.11, -0.07), (0.0, 0.0), 41),
        PlaneResidual((-0.09, 0.13), (0.01, 0.0), 37),
        PlaneResidual((0.0, 0.0), (0.0, 0.0), 0),
    )
    summary = ColorRegionSummary(
        region_id="region-p8",
        page=0,
        accepted=True,
        reason="accepted",
        n_patches=1,
        n_train=400,
        n_heldout=100,
        class_counts=(200, 100, 100),
        baseline_heldout_logloss=0.5,
        selected_heldout_logloss=0.5,
        registration_adopted=False,
        residuals=measured,
    )

    from holo.receive import _production_diagnostics

    details = {row.name: row.value
               for row in _production_diagnostics.color_region_details(
                   summary)}

    assert details["color.registration_adopted"] is False
    assert details["color.registration.c.intercept_x_dots"] == 0.11
    assert details["color.registration.c.intercept_y_dots"] == -0.07
    assert details["color.registration.c.anchors"] == 41
    assert details["color.registration.m.slope_x_dots"] == 0.01
    assert details["color.registration.m.anchors"] == 37
    # Y measured nothing: the one honest kind of zero left on this event.
    assert details["color.registration.y.anchors"] == 0
    assert details["color.registration.y.intercept_x_dots"] == 0.0


def test_new_crc_certificate_is_not_fed_back_before_barrier_commit(
    monkeypatch,
) -> None:
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    current_source = _source("bootstrap-color")
    first_block = _block(spec, current_source, ADDRESS)
    source = EvidenceSource(current_source, LANE)
    zero = tuple(
        PlaneResidual((0.0, 0.0), (0.0, 0.0), 0)
        for _ in range(3)
    )
    refused = ColorRegionSummary(
        "refused-region",
        0,
        False,
        "insufficient first-order support",
        1,
        0,
        0,
        (),
        None,
        None,
        False,
        zero,
    )
    first_capture = ColorCaptureEvidence(
        source, spec.spec_id, "cmy8", (), (), (refused,))
    collect_calls = []

    def collect_once(*_args, **kwargs):
        collect_calls.append(kwargs)
        if len(collect_calls) != 1:
            raise AssertionError(
                "same-barrier certificate triggered color replay")
        return first_capture

    monkeypatch.setattr(
        production_color, "collect_color_evidence", collect_once)
    monkeypatch.setattr(
        production_color,
        "color_blocks_from_frontier",
        lambda *_args, **_kwargs: (first_block,),
    )

    def first_c_certifies(
        view,
        actual_spec,
        stream_id,
        stage,
        *,
        source_sha256,
        lane_id,
    ):
        succeeds = (
            view.address == ADDRESS
            and stream_id == "C"
            and stage is AttemptStage.SCAN
        )
        attempt_id = stream_attempt_identity(
            actual_spec,
            view.address,
            stream_id,
            stage,
            view.component_block_ids,
        )
        certificate = None
        if succeeds:
            profile = next(
                row for row in actual_spec.stream_profiles
                if row.stream_id == stream_id)
            certificate = certificate_record_from_user_bits(
                actual_spec,
                page=view.address[0],
                tile_yx=view.address[1:],
                stream_id=stream_id,
                user_bits=np.zeros(profile.user_bits, np.uint8),
                origin_attempt_id=attempt_id,
            )
        return ColorAttemptResult(
            TileAttemptRecord(
                attempt_id=attempt_id,
                source_sha256=source_sha256,
                lane_id=lane_id,
                page=view.address[0],
                tile_yx=view.address[1:],
                stage=stage,
                state=(
                    AttemptState.CERTIFIED
                    if succeeds
                    else AttemptState.BELOW_ATTEMPT_FLOOR
                ),
                n_informative=0,
                n_iters=1 if succeeds else 0,
                syndrome_ok=True if succeeds else None,
                crc_ok=True if succeeds else None,
                component_block_ids=view.component_block_ids,
                dependency_certificate_ids=(),
                certificate_id=(
                    None if certificate is None
                    else certificate.certificate_id),
                stream_id=stream_id,
                child_outcomes=(
                    ((1, True),) if succeeds else ()),
            ),
            certificate,
        )

    monkeypatch.setattr(
        production_color, "attempt_color_tile", first_c_certifies)
    monkeypatch.setattr(
        production_color, "close_count_ready",
        lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        production_color, "certificate_divergence",
        lambda *_args, **_kwargs: ())
    events = []
    context = _context(spec, current_source, None, events)
    survey = SurveyProduct(SurveyArtifact("survey-bootstrap", ()), ())
    address = AddressProduct(
        AddressArtifact(
            "address-bootstrap", "survey-bootstrap", (), ()),
        (),
        (),
        transient=AddressResult((), (), (), (), 0),
    )

    execution = production_color.ProductionColorPayload().process(
        context, survey, address)

    product = execution.product
    assert product is not None
    assert len(collect_calls) == 1
    assert collect_calls[0]["certificates"] == ()
    assert product.blocks == (first_block,)
    assert tuple(
        (row.page, *row.tile_yx) for row in product.attempts
    ) == (
        ADDRESS,
        ADDRESS,
        ADDRESS,
    )
    assert all(
        not row.dependency_certificate_ids
        for row in product.attempts
    )
    assert not any(
        name.startswith("payload.color.bootstrap")
        for name, _details in events
    )


def test_color_attempt_event_builds_stream_snapshot_only_when_requested(
) -> None:
    """The SHARED attempt emitter builds fine snapshots lazily.

    Family unification: color emits payload.attempt through the same
    _production_diagnostics.attempt_progress_callback as K; the snapshot
    builder must run only when the observer requests the factory.
    """
    from holo.receive import _production_diagnostics as production_diagnostics

    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    current_source = _source("snapshot-current")
    block = _block(spec, current_source)
    events = []
    factories = []
    context = _context(
        spec, current_source, block, events, factories)
    view = payload_engine.tile_attempt_view((block,))
    record = TileAttemptRecord(
        attempt_id=stream_attempt_identity(
            spec, ADDRESS, "C", AttemptStage.SCAN,
            view.component_block_ids),
        source_sha256=current_source,
        lane_id=LANE,
        page=ADDRESS[0],
        tile_yx=ADDRESS[1:],
        stage=AttemptStage.SCAN,
        state=AttemptState.BELOW_ATTEMPT_FLOOR,
        n_informative=0,
        n_iters=0,
        syndrome_ok=None,
        crc_ok=None,
        component_block_ids=view.component_block_ids,
        dependency_certificate_ids=(),
        stream_id="C",
    )
    calls = []

    def snapshot_builder(row, evidence):
        calls.append((row, evidence))
        return None

    progress = production_diagnostics.attempt_progress_callback(
        context, "payload.attempt", [0], snapshot_builder)
    progress(record, view)

    assert events[-1][0] == "payload.attempt"
    details = dict(
        (row.name, row.value) for row in events[-1][1])
    assert details["payload.stream"] == "C"
    assert details["payload.attempt_state"] == "below_attempt_floor"
    assert calls == []
    factory = factories[-1]
    assert callable(factory)
    assert factory() is None
    assert calls == [(record, view)]


@pytest.mark.parametrize(
    ("spec_id", "terminal_stage", "terminal_status"),
    (
        (
            "c2-cmy7-p120-v0@3328x2304",
            AttemptStage.SCAN,
            "integrity_failure",
        ),
        (
            "c2-cmy8-p120-v0@3328x2304",
            AttemptStage.SCAN,
            "verified",
        ),
        (
            "c2-cmy8-p120-v0@3328x2304",
            AttemptStage.UNION,
            "verified",
        ),
    ),
)
def test_color_preclose_runs_once_after_complete_ordinary_batch(
    monkeypatch,
    spec_id,
    terminal_stage,
    terminal_status,
) -> None:
    """Ordinary work batches before one advisory close and no BP150."""
    spec = get_format_row(spec_id)
    successful_stream = spec.stream_ids[0]
    current_source = _source("terminal-shared-block")
    current_block = _block(spec, current_source)
    discarded_block = (
        _block(spec, current_source, (0, 0, 1))
        if terminal_stage is AttemptStage.SCAN
        else None
    )
    prior_block = (
        None if terminal_stage is AttemptStage.SCAN
        else _block(spec, _source("terminal-prior-block"))
    )
    events = []
    context = _context(spec, current_source, prior_block, events)
    empty = ColorCaptureEvidence(
        EvidenceSource(current_source, LANE),
        spec.spec_id,
        current_block.kind,
        (),
        (),
        (),
    )
    monkeypatch.setattr(
        production_color,
        "collect_color_evidence",
        lambda *_args, **_kwargs: empty,
    )
    monkeypatch.setattr(
        production_color,
        "color_blocks_from_frontier",
        lambda *_args, **_kwargs: (
            (current_block,)
            if discarded_block is None
            else (current_block, discarded_block)
        ),
    )

    def fake_attempt(
        view,
        actual_spec,
        stream_id,
        stage,
        *,
        source_sha256,
        lane_id,
    ):
        assert actual_spec is spec
        attempt_address = view.address
        succeeds = (
            attempt_address == ADDRESS
            and stream_id == successful_stream
            and stage is terminal_stage
        )
        attempt_id = stream_attempt_identity(
            spec, attempt_address, stream_id, stage,
            view.component_block_ids)
        certificate = None
        if succeeds:
            profile = next(
                row for row in spec.stream_profiles
                if row.stream_id == stream_id)
            certificate = certificate_record_from_user_bits(
                spec,
                page=attempt_address[0],
                tile_yx=attempt_address[1:],
                stream_id=stream_id,
                user_bits=np.zeros(profile.user_bits, np.uint8),
                origin_attempt_id=attempt_id,
            )
        record = TileAttemptRecord(
            attempt_id=attempt_id,
            source_sha256=source_sha256,
            lane_id=lane_id,
            page=attempt_address[0],
            tile_yx=attempt_address[1:],
            stage=stage,
            state=(AttemptState.CERTIFIED if succeeds
                   else AttemptState.ATTEMPTED_FAILED),
            n_informative=int(np.count_nonzero(view.observed_cells())),
            n_iters=1 if succeeds else 120,
            syndrome_ok=succeeds,
            crc_ok=True if succeeds else None,
            component_block_ids=view.component_block_ids,
            dependency_certificate_ids=(),
            certificate_id=(
                None if certificate is None else certificate.certificate_id),
            stream_id=stream_id,
            child_outcomes=((1, True),) if succeeds else ((120, False),),
        )
        return ColorAttemptResult(record, certificate)

    monkeypatch.setattr(
        production_color, "attempt_color_tile", fake_attempt)
    monkeypatch.setattr(
        production_color, "close_count_ready",
        lambda *_args, **_kwargs: True)
    close_calls = []
    monkeypatch.setattr(
        production_color,
        "close_volume",
        lambda *args, **_kwargs: (
            close_calls.append(args),
            SimpleNamespace(status=terminal_status),
        )[1],
    )
    survey = SurveyProduct(SurveyArtifact("survey-terminal", ()), ())
    address_state = AddressResult((), (), (), (), 0)
    address = AddressProduct(
        AddressArtifact("address-terminal", "survey-terminal", (), ()),
        (),
        (),
        transient=address_state,
    )

    execution = production_color.ProductionColorPayload().process(
        context, survey, address)
    product = execution.product
    assert product is not None
    expected_attempts = tuple(
        ("scan", stream_id)
        for _block_value in (
            (current_block,)
            if discarded_block is None
            else (current_block, discarded_block)
        )
        for stream_id in spec.stream_ids
    )
    if terminal_stage is AttemptStage.UNION:
        expected_attempts += tuple(
            ("union", stream_id) for stream_id in spec.stream_ids)
    assert tuple(
        (row.stage.value, row.stream_id)
        for row in product.attempts
    ) == expected_attempts
    assert tuple(row.stream_id for row in product.certificates) == (
        successful_stream,
    )
    assert product.blocks == (
        (current_block,)
        if discarded_block is None
        else (current_block, discarded_block)
    )
    assert len(close_calls) == 1
    assert all(row.stage is not AttemptStage.RETRY150
               for row in product.attempts)


@pytest.mark.parametrize("defer_fountain_close", (False, True))
def test_color_production_is_scan_then_union_then_selective_retry(
    monkeypatch,
    defer_fountain_close,
) -> None:
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    current_source = _source("current")
    prior_block = _block(spec, _source("prior"))
    current_block = _block(spec, current_source)
    events = []
    factories = []
    context = _context(
        spec,
        current_source,
        prior_block,
        events,
        factories,
        defer_fountain_close=defer_fountain_close,
    )
    empty = ColorCaptureEvidence(
        EvidenceSource(current_source, LANE),
        spec.spec_id,
        "cmy8",
        (),
        (),
        (),
    )
    monkeypatch.setattr(
        production_color,
        "collect_color_evidence",
        lambda *_args, **_kwargs: empty,
    )
    monkeypatch.setattr(
        production_color,
        "color_blocks_from_frontier",
        lambda *_args, **_kwargs: (current_block,),
    )

    def fake_attempt(
        view,
        actual_spec,
        stream_id,
        stage,
        *,
        source_sha256,
        lane_id,
    ):
        assert actual_spec is spec
        assert source_sha256 == current_source
        assert lane_id == LANE
        succeeds = (
            (stage is AttemptStage.SCAN and stream_id == "C")
            or (stage is AttemptStage.UNION and stream_id == "M")
            or (stage is AttemptStage.RETRY150 and stream_id == "Y")
        )
        attempt_id = stream_attempt_identity(
            spec,
            ADDRESS,
            stream_id,
            stage,
            view.component_block_ids,
        )
        certificate = None
        if succeeds:
            profile = next(
                row for row in spec.stream_profiles
                if row.stream_id == stream_id)
            certificate = certificate_record_from_user_bits(
                spec,
                page=ADDRESS[0],
                tile_yx=ADDRESS[1:],
                stream_id=stream_id,
                user_bits=np.zeros(profile.user_bits, np.uint8),
                origin_attempt_id=attempt_id,
            )
        record = TileAttemptRecord(
            attempt_id=attempt_id,
            source_sha256=source_sha256,
            lane_id=lane_id,
            page=ADDRESS[0],
            tile_yx=ADDRESS[1:],
            stage=stage,
            state=(AttemptState.CERTIFIED if succeeds
                   else AttemptState.ATTEMPTED_FAILED),
            n_informative=int(np.count_nonzero(view.observed_cells())),
            n_iters=1,
            syndrome_ok=succeeds,
            crc_ok=True if succeeds else None,
            component_block_ids=view.component_block_ids,
            dependency_certificate_ids=(),
            certificate_id=(
                None if certificate is None
                else certificate.certificate_id),
            stream_id=stream_id,
            child_outcomes=((1, succeeds),),
        )
        return ColorAttemptResult(record, certificate)

    monkeypatch.setattr(
        production_color, "attempt_color_tile", fake_attempt)
    if defer_fountain_close:
        def forbidden_close(*_args, **_kwargs):
            raise AssertionError(
                "deferred reception performed an advisory fountain check")

        monkeypatch.setattr(
            production_color, "close_count_ready", forbidden_close)
        monkeypatch.setattr(
            production_color, "close_volume", forbidden_close)
    survey = SurveyProduct(SurveyArtifact("survey", ()), ())
    address_state = AddressResult((), (), (), (), 0)
    address = AddressProduct(
        AddressArtifact("address", "survey", (), ()),
        (),
        (),
        transient=address_state,
    )

    execution = production_color.ProductionColorPayload().process(
        context, survey, address)
    product = execution.product
    assert product is not None
    assert tuple(
        (row.stage, row.stream_id)
        for row in product.attempts
    ) == (
        (AttemptStage.SCAN, "C"),
        (AttemptStage.SCAN, "M"),
        (AttemptStage.SCAN, "Y"),
        (AttemptStage.UNION, "M"),
        (AttemptStage.UNION, "Y"),
        (AttemptStage.RETRY150, "Y"),
    )
    assert tuple(row.stream_id for row in product.certificates) == (
        "C", "M", "Y")
    assert len(product.divergences) == 6
    assert {
        row.certificate_id for row in product.divergences
    } == {
        row.certificate_id for row in product.certificates
    }
    assert {
        row.evidence_block_id for row in product.divergences
    } == {
        prior_block.block_id,
        current_block.block_id,
    }
    assert product.attempts[-1].component_block_ids == (
        product.attempts[-2].component_block_ids)
    assert all(row.source_sha256 == current_source
               for row in product.attempts)
    event_names = [name for name, _details in events]
    assert event_names.index("payload.owner_frozen") < (
        event_names.index("payload.blocks_built")
    )
    assert event_names.index("payload.blocks_built") < (
        event_names.index("payload.attempt")
    )
    assert "payload.complete" in event_names
    # §10.4 event parity (rework 6.2): the forced max60 -> retry150
    # boundary milestone, mirroring ProductionPayload._retry exactly.
    assert (
        event_names.index("payload.retry_attempt")
        < event_names.index("payload.retry_complete")
        < event_names.index("payload.complete")
    )
    retry_details = dict(
        (row.name, row.value)
        for row in events[event_names.index("payload.retry_complete")][1])
    assert retry_details == {
        "lane.id": LANE,
        "payload.max60_attempts": 5,
        "payload.max60_decoder_calls": 5,
        "payload.max60_bp_iterations": 5,
        "payload.max60_certificates": 2,
        "payload.retry150_frontier": 1,
        "payload.retry150_eligible": 1,
        "payload.retry150_attempts": 1,
        "payload.retry150_decoder_calls": 1,
        "payload.retry150_bp_iterations": 1,
        "payload.retry150_certificates": 1,
        "payload.retry150_noop": False,
    }
    # §10.4 event parity (rework 6.2): the owner-frozen snapshot factory
    # is lazy and yields the generic payload_reach shape the viewer
    # already consumes for K.
    owner_factory = factories[event_names.index("payload.owner_frozen")]
    assert callable(owner_factory)
    reach = owner_factory()
    assert reach["kind"] == "payload_reach"
    assert reach["pages"] == {}

    blocks = {
        row.block_id: row for row in (prior_block, current_block)}
    certificates = {
        row.certificate_id: row for row in product.certificates}
    frontier = {row.key: row.block_id
                for row in (prior_block, current_block)}
    prior_attempts = []
    for attempt in product.attempts:
        validate_attempt(
            attempt,
            blocks,
            certificates,
            set(certificates),
            tuple(prior_attempts),
            frontier,
        )
        prior_attempts.append(attempt)
