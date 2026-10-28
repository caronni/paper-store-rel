"""F-08: capture's transition laws — acquisition truth is frozen.

Q2 already refused a changed ``dpi_true`` at a standing capture key;
F-08 extends the freeze to the whole record (shape, dtype, channels, the
footing ladder — all deterministic functions of the authenticated bytes
and the session's row) and gives the region family the same law for its
survey content. B9's fresh-survey-wins rule stays intact: determinism
makes the lawful re-ingest EQUAL, and equal passes.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from holo2.capture import RECORD_FAMILIES, RegionRecord, region_key
from holo2.capture.records import CaptureRecord, FootingSpec
from holo2.core import CommitRefusal
from holo2.core.records import BlobRef

SHA = "a" * 64


def _family(kind: str):
    return {family.kind: family for family in RECORD_FAMILIES}[kind]


def _capture(dpi: float = 1200.0, channels: int = 1,
             platen_backing: float = 200.0) -> CaptureRecord:
    return CaptureRecord(
        source_sha256=SHA, dpi_true=dpi, shape_px=(256, 256), dtype="uint8",
        channels=channels, platen_backing=platen_backing,
        footings=(FootingSpec(f"f:{SHA[:12]}/{dpi:g}", Fraction(2),
                              capture_sha256=SHA),))


def _region(vote: Fraction | None = Fraction(1, 300),
            mask: str = "b") -> RegionRecord:
    return RegionRecord(
        capture_sha256=SHA,
        support_mask_ref=BlobRef(sha256=mask * 64, length_bytes=64),
        pitch_in_vote=vote, support_origin_px=(0, 0), support_step_px=16,
        support_extent_px=(128, 128))


def test_a_changed_dpi_keeps_its_named_refusal() -> None:
    transition = _family("capture").transition
    key = "unit"
    transition(key, _capture(), _capture())        # equal rewrite: no-op
    with pytest.raises(CommitRefusal, match="renames every footing"):
        transition(key, _capture(1200.0), _capture(1206.0))


def test_the_rest_of_the_capture_record_is_frozen_too() -> None:
    transition = _family("capture").transition
    with pytest.raises(CommitRefusal, match="acquisition truth"):
        transition("unit", _capture(channels=1), _capture(channels=3))


def test_region_survey_content_is_frozen() -> None:
    transition = _family("region").transition
    region = _region()
    key = region_key(SHA, (0, 0), 16, (128, 128))
    transition(key, region, _region())             # equal rewrite: no-op
    with pytest.raises(CommitRefusal, match="pitch_in_vote"):
        transition(key, region, _region(vote=Fraction(1, 200)))
    with pytest.raises(CommitRefusal, match="support_mask_ref"):
        transition(key, region, _region(mask="c"))
    with pytest.raises(CommitRefusal, match="pitch_in_vote"):
        transition(key, region, _region(vote=None))
