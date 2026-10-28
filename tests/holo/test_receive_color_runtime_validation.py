"""Format-bound validation that generic multistream records cannot weaken K."""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from holo.format import pilots
from holo.format.registry import get_format_row
from holo.receive._runtime_validation import (
    validate_attempts,
    validate_blocks_for_spec,
)
from holo.receive.evidence import AttemptStage, AttemptState, TileAttemptRecord
from holo.receive.evidence_blocks import EvidenceOrigin, block_from_rows
from holo.receive.records import stream_attempt_identity
from holo.receive.state_codec import decode_typed, encode_typed
from holo.receive.tiles import k_eff_bits


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def test_color_state_refuses_a_scalar_k_evidence_block() -> None:
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    flat = int(pilots.color_payload_cell_indices(spec.family_seed)[0])
    block = block_from_rows(
        _hash("source"),
        "lane",
        0,
        (0, 0),
        ((flat, np.asarray((1.0,)), EvidenceOrigin("p", 0, 0.1)),),
        kind="k",
    )
    with pytest.raises(ValueError, match="evidence kind"):
        validate_blocks_for_spec((block,), spec)


def _k_failed_attempt(crc_ok: bool | None) -> TileAttemptRecord:
    spec = get_format_row("c2-r0550@3328x2304")
    block_id = _hash("block")
    address = (0, 0, 0)
    return TileAttemptRecord(
        attempt_id=stream_attempt_identity(
            spec, address, "main", AttemptStage.SCAN, (block_id,)),
        source_sha256=_hash("source"),
        lane_id="lane",
        page=0,
        tile_yx=(0, 0),
        stage=AttemptStage.SCAN,
        state=AttemptState.ATTEMPTED_FAILED,
        n_informative=k_eff_bits(spec),
        n_iters=120,
        syndrome_ok=False,
        crc_ok=crc_ok,
        component_block_ids=(block_id,),
        dependency_certificate_ids=(),
    )


@pytest.mark.parametrize("crc_ok", (False, True))
def test_k_failed_attempt_retains_either_recorded_crc_result(
    crc_ok: bool,
) -> None:
    spec = get_format_row("c2-r0550@3328x2304")
    validate_attempts((_k_failed_attempt(crc_ok),), spec)


def test_k_failed_attempt_refuses_an_omitted_crc_result() -> None:
    with pytest.raises(ValueError, match="inconsistent attempted_failed"):
        _k_failed_attempt(None)


def test_k_failed_attempt_omitted_crc_is_refused_on_typed_load() -> None:
    encoded = encode_typed(_k_failed_attempt(False))
    encoded["crc_ok"] = None
    with pytest.raises(ValueError, match="inconsistent attempted_failed"):
        decode_typed(encoded, TileAttemptRecord)


def test_color_failed_child_must_exhaust_its_registered_iteration_budget(
) -> None:
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    block_id = _hash("block")
    address = (0, 0, 0)
    record = TileAttemptRecord(
        attempt_id=stream_attempt_identity(
            spec, address, "C", AttemptStage.SCAN, (block_id,)),
        source_sha256=_hash("source"),
        lane_id="lane",
        page=0,
        tile_yx=(0, 0),
        stage=AttemptStage.SCAN,
        state=AttemptState.ATTEMPTED_FAILED,
        n_informative=spec.payload_cells,
        n_iters=1,
        syndrome_ok=False,
        crc_ok=None,
        component_block_ids=(block_id,),
        dependency_certificate_ids=(),
        stream_id="C",
        child_outcomes=((1, False),),
    )
    with pytest.raises(ValueError, match="child iteration"):
        validate_attempts((record,), spec)
