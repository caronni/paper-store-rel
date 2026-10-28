"""Color-native divergence generation and replay."""
from __future__ import annotations

import dataclasses
import hashlib

import numpy as np
import pytest

from holo.core import channel
from holo.format import pilots
from holo.format.registry import get_format_row
from holo.receive.records import certificate_divergence
from holo.receive.color_divergence import color_divergence_counts
from holo.receive.cascade import scale_plan
from holo.receive.color_projection import project_certified_color_tile
from holo.receive.evidence import AttemptStage, AttemptState
from holo.receive.evidence_blocks import EvidenceOrigin, block_from_rows
from holo.receive.records import (
    certificate_record_from_user_bits,
    stream_attempt_identity,
)
from holo.receive.session import (
    BarrierDelta,
    CaptureFacts,
    LevelRecord,
    SessionIndex,
    SessionState,
    append_level_barrier,
    load_session,
    save_session,
)
from holo.receive.types import (
    AddressArtifact,
    PayloadArtifact,
    SurveyArtifact,
    TileAttemptRecord,
)


ADDRESS = (0, 0, 0)
LANE = "l00-2ppc-600dpi"


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _certificate(spec, stream_id: str, attempt_id: str = "attempt"):
    profile = next(
        row for row in spec.stream_profiles if row.stream_id == stream_id)
    return certificate_record_from_user_bits(
        spec,
        page=ADDRESS[0],
        tile_yx=ADDRESS[1:],
        stream_id=stream_id,
        user_bits=np.zeros(profile.user_bits, np.uint8),
        origin_attempt_id=attempt_id,
    )


def _cmy8_block(spec, certificate, *, one_mismatch: bool = True):
    projection = project_certified_color_tile(
        (certificate,), spec, ADDRESS)
    payload = pilots.color_payload_cell_indices(spec.family_seed)
    expected = projection.component_bits.reshape(4096, 3)[payload]
    values = np.where(expected != 0, 3.0, -3.0).astype(np.float64)
    if one_mismatch:
        plane = spec.stream_ids.index(certificate.stream_id)
        values[0, plane] *= -1.0
    origin = EvidenceOrigin("placement", 0, 0.1)
    return block_from_rows(
        _sha("cmy8-source"),
        LANE,
        ADDRESS[0],
        ADDRESS[1:],
        (
            (int(flat), row, origin)
            for flat, row in zip(payload, values, strict=True)
        ),
        kind="cmy8",
    )


def _cmy7_block(spec, certificate, *, one_mismatch: bool = True):
    projection = project_certified_color_tile(
        (certificate,), spec, ADDRESS)
    payload = pilots.color_payload_cell_indices(spec.family_seed)
    expected = channel.planes_to_states(
        projection.component_bits.reshape(4096, 3)[payload],
    ).astype(np.int64)
    values = np.full((payload.size, 6), -3.0, np.float64)
    nonwhite = np.flatnonzero(expected)
    values[nonwhite, expected[nonwhite] - 1] = 3.0
    if one_mismatch:
        if expected[0] == 0:
            values[0, 0] = 4.0
        else:
            values[0] = -3.0
    origin = EvidenceOrigin("placement", 0, 0.1)
    return block_from_rows(
        _sha("cmy7-source"),
        LANE,
        ADDRESS[0],
        ADDRESS[1:],
        (
            (int(flat), row, origin)
            for flat, row in zip(payload, values, strict=True)
        ),
        kind="cmy7",
    )


@pytest.mark.parametrize("stream_id", ("C", "M", "Y"))
def test_cmy8_divergence_selects_only_the_certificate_stream(stream_id):
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    certificate = _certificate(spec, stream_id)
    block = _cmy8_block(spec, certificate)

    rows = certificate_divergence(
        (block,), (certificate,), spec)

    assert len(rows) == 1
    assert rows[0].n_observed == spec.payload_cells
    assert rows[0].n_disagree == 1
    # Differential over the pairing seam: the ONE records pairing loop
    # produced exactly the kernel's counts for this pair.
    assert color_divergence_counts(block, certificate, spec) == (
        rows[0].n_observed, rows[0].n_disagree)


def test_cmy7_divergence_uses_seven_state_argmax_with_implicit_white():
    spec = get_format_row("c2-cmy7-p120-v0@3328x2304")
    certificate = _certificate(spec, "main")
    block = _cmy7_block(spec, certificate)

    divergence, = certificate_divergence(
        (block,), (certificate,), spec)

    assert divergence.n_observed == spec.payload_cells
    assert divergence.n_disagree == 1
    assert color_divergence_counts(block, certificate, spec) == (
        divergence.n_observed, divergence.n_disagree)


def test_open_partial_cmy8_state_folds_divergence_to_counter(tmp_path):
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    source = _sha("cmy8-source")
    prototype = _certificate(spec, "C")
    block = _cmy8_block(spec, prototype, one_mismatch=True)
    attempt_id = stream_attempt_identity(
        spec,
        ADDRESS,
        "C",
        AttemptStage.SCAN,
        (block.block_id,),
    )
    certificate = _certificate(spec, "C", attempt_id)
    assert certificate.certificate_id == prototype.certificate_id
    divergence, = certificate_divergence(
        (block,), (certificate,), spec)
    c_attempt = TileAttemptRecord(
        attempt_id=attempt_id,
        source_sha256=source,
        lane_id=LANE,
        page=ADDRESS[0],
        tile_yx=ADDRESS[1:],
        stage=AttemptStage.SCAN,
        state=AttemptState.CERTIFIED,
        n_informative=block.n_observed,
        n_iters=1,
        syndrome_ok=True,
        crc_ok=True,
        component_block_ids=(block.block_id,),
        dependency_certificate_ids=(),
        certificate_id=certificate.certificate_id,
        stream_id="C",
        child_outcomes=((1, True),),
    )
    sibling_attempts = tuple(
        TileAttemptRecord(
            attempt_id=stream_attempt_identity(
                spec,
                ADDRESS,
                stream_id,
                AttemptStage.SCAN,
                (block.block_id,),
            ),
            source_sha256=source,
            lane_id=LANE,
            page=ADDRESS[0],
            tile_yx=ADDRESS[1:],
                stage=AttemptStage.SCAN,
                state=AttemptState.ATTEMPTED_FAILED,
                n_informative=block.n_observed,
                n_iters=120,
                syndrome_ok=False,
                crc_ok=None,
            component_block_ids=(block.block_id,),
            dependency_certificate_ids=(),
            stream_id=stream_id,
                child_outcomes=((120, False),),
        )
        for stream_id in ("M", "Y")
    )
    attempts = (c_attempt, *sibling_attempts)
    survey = SurveyArtifact("survey", ())
    address = AddressArtifact("address", survey.survey_id, (), ())
    payload = PayloadArtifact(
        "payload",
        address.address_id,
        (certificate.certificate_id,),
        n_blocks=1,
        n_attempts=len(attempts),
        n_divergences=1,
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
        "test/color-divergence-v1",
        (0,),
    )
    # Barrier replay runs the same color comparison kernel: a tampered
    # durable counter is refused before any state is produced.
    with pytest.raises(ValueError, match="not replayable"):
        append_level_barrier(
            initial,
            SessionIndex(initial),
            CaptureFacts(source, 600.0, "uint8", (2, 2), 3),
            plan,
            LevelRecord(survey, address, payload),
            BarrierDelta(
                blocks=(block,),
                attempts=attempts,
                certificates=(certificate,),
                divergences=(dataclasses.replace(
                    divergence, n_disagree=divergence.n_disagree + 1),),
            ),
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
            certificates=(certificate,),
            divergences=(divergence,),
        ),
    )
    # Divergence records are transient (kiss): the barrier folds them
    # into a durable counter and the state round-trips exactly.
    assert state.counters.divergences == 1
    assert state.counters.scan.evaluations == len(attempts)
    path = tmp_path / "valid.json"
    assert save_session(path, state)
    assert load_session(path) == state
