"""Focused tests for hardwired production-receiver policy choices."""
from __future__ import annotations

import numpy as np
import pytest

from holo.devices.profiles import make_spec
from holo.receive import production_payload
from holo.receive.evidence_context import EvidenceContext
from holo.receive.payload_model import CONTEXT_PROFILE, EvidenceSource
from holo.receive.placement.model import AddressResult
from holo.receive.runtime import LaneContext
from holo.receive.scan import open_capture
from holo.receive.session import CaptureFacts
from holo.receive.types import (
    AddressArtifact,
    AddressProduct,
    LaneSpec,
    Stage,
    SurveyArtifact,
    SurveyProduct,
)


class _PayloadBoundaryReached(Exception):
    pass


def test_production_payload_passes_hardwired_context_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = make_spec("c3-r0550", "default")
    raster = open_capture(np.zeros((8, 8), np.uint8), 600.0)
    lane = LaneSpec("native", 3, 1, 1, 1)
    facts = CaptureFacts(
        raster.source.sha256,
        raster.dpi,
        raster.source.dtype,
        raster.source.shape,
        raster.source.channels,
    )
    context = LaneContext(
        Stage.PAYLOAD,
        lane,
        spec,
        raster,
        facts,
        EvidenceContext(),
        lambda: False,
        lambda: False,
        lambda *_args, **_kwargs: None,
        lambda _name, _callback: None,
    )
    survey = SurveyProduct(SurveyArtifact("survey", ()), ())
    address_state = AddressResult((), (), (), (), 0)
    address = AddressProduct(
        AddressArtifact("address", survey.artifact.survey_id, (), ()),
        (),
        (),
        transient=address_state,
    )
    observed: dict[str, object] = {}

    def collect_capture_evidence(
        actual_raster,
        source,
        actual_address,
        actual_spec,
        *,
        detector_profile,
        **_kwargs,
    ) -> None:
        observed.update(
            raster=actual_raster,
            source=source,
            address=actual_address,
            spec=actual_spec,
            detector_profile=detector_profile,
        )
        raise _PayloadBoundaryReached

    monkeypatch.setattr(
        production_payload.payload,
        "collect_capture_evidence",
        collect_capture_evidence,
    )

    with pytest.raises(_PayloadBoundaryReached):
        production_payload.ProductionPayload().process(
            context, survey, address)

    assert observed == {
        "raster": raster,
        "source": EvidenceSource(facts.source_sha256, lane.lane_id),
        "address": address_state,
        "spec": spec,
        "detector_profile": CONTEXT_PROFILE,
    }
