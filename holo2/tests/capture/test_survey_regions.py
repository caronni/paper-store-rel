"""The holo2-side adaptation of the carried survey: §5.3 typed output.

holo2-imports only (the equivalence of the carried ALGORITHM is pinned
outside this tree, in ``tests/holo2_oracles/``). What is tested here is the part
that has no holo counterpart: the typed candidates, the support mask's
blob bytes, the refusal to invent a pitch vote — and the region
KEY, which since the identity law is the capture plus the support grid
themselves (``capture.region_key``), not a digest of them.
"""
from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo2.core.blobs import BlobSidecar
from holo2.capture import (RegionRecord, parse_region_key, region_key)
from holo2.capture.survey import (PayloadSurvey, RegionCandidate, SupportMask,
                                  SurveyDiagnostics, SurveyRegion,
                                  region_candidates, support_mask_bytes)

CAPTURE = "ab" * 32
OTHER_CAPTURE = "cd" * 32


def key_of(capture: str, mask: SupportMask):
    """The region key a candidate on this mask is stored under."""
    return region_key(capture, mask.origin_yx, mask.step_px, mask.extent_px)


def make_mask(*, origin=(16, 32), step=8, rows=5, cols=7,
              extent=None, hole=(2, 3)) -> SupportMask:
    cells = np.ones((rows, cols), bool)
    cells[hole] = False
    return SupportMask(origin, step,
                       cells, extent or (rows * step, cols * step))


def make_survey(masks,
                pitch_in: Fraction | None = Fraction(1, 300)) -> PayloadSurvey:
    regions = tuple(
        SurveyRegion(mask, float(index + 1) * 10.0, 17.5 - index)
        for index, mask in enumerate(masks)
    )
    return PayloadSurvey(
        regions, pitch_in, None if pitch_in is None else 4.0, (),
        SurveyDiagnostics(None, 8, 8.0, len(regions), 0, 0, 0))


def test_the_region_key_is_its_values_and_parses_back() -> None:
    mask = make_mask()
    key = key_of(CAPTURE, mask)
    assert key == key_of(CAPTURE, make_mask())        # same values, same key
    assert parse_region_key(key) == (CAPTURE, mask.origin_yx, mask.step_px,
                                     mask.extent_px)


@pytest.mark.parametrize(
    "override",
    [dict(origin=(17, 32)), dict(origin=(16, 33)), dict(step=9),
     dict(rows=6), dict(cols=8), dict(extent=(5 * 8 - 3, 7 * 8))],
)
def test_the_region_key_separates_every_component(override: dict) -> None:
    assert key_of(CAPTURE, make_mask()) != key_of(
        CAPTURE, make_mask(**override))


def test_the_region_key_separates_captures() -> None:
    mask = make_mask()
    assert key_of(CAPTURE, mask) != key_of(OTHER_CAPTURE, mask)


def test_the_support_mask_is_its_own_blob(tmp_path: Path) -> None:
    """The mask is BULK: the sidecar addresses it, the key names geometry."""
    mask = make_mask()
    with BlobSidecar.open(tmp_path / "blobs.bin", fsync=False) as sidecar:
        ref = sidecar.put_array(mask.cells)
        assert ref.length_bytes == len(support_mask_bytes(mask))
        restored = sidecar.read_array(ref, verify=True)
        np.testing.assert_array_equal(restored, mask.cells)


def test_region_candidates_carry_the_survey_facts() -> None:
    masks = [make_mask(), make_mask(origin=(200, 300), rows=4, cols=4,
                                    extent=(32, 32))]
    survey = make_survey(masks)
    candidates = region_candidates(CAPTURE, survey)
    assert len(candidates) == 2
    assert all(isinstance(item, RegionCandidate) for item in candidates)
    for candidate, region in zip(candidates, survey.regions, strict=True):
        assert candidate.capture_sha256 == CAPTURE
        assert candidate.support is region.support
        assert candidate.bbox_px == region.support.bbox
        assert candidate.area_mm2 == region.area_mm2
        assert candidate.pitch_in_vote == Fraction(1, 300)
    assert len({key_of(CAPTURE, item.support)
                for item in candidates}) == 2


def test_region_candidates_do_not_invent_a_pitch_vote() -> None:
    """A tied or absent platen vote stays ``None`` (L4: no manufactured facts)."""
    candidates = region_candidates(CAPTURE, make_survey([make_mask()], None))
    assert candidates[0].pitch_in_vote is None


def test_region_candidates_of_an_empty_survey() -> None:
    assert region_candidates(CAPTURE, make_survey([])) == ()


def test_candidate_maps_onto_the_design_record(tmp_path: Path) -> None:
    """The shape H2c needs: candidate -> RegionRecord at its region key."""
    candidate = region_candidates(CAPTURE, make_survey([make_mask()]))[0]
    with BlobSidecar.open(tmp_path / "blobs.bin", fsync=False) as sidecar:
        record = RegionRecord(
            capture_sha256=candidate.capture_sha256,
            support_mask_ref=sidecar.put_array(candidate.support.cells),
            pitch_in_vote=candidate.pitch_in_vote,
            support_origin_px=candidate.support.origin_yx,
            support_step_px=candidate.support.step_px,
            support_extent_px=candidate.support.extent_px,
        )
    # OR-12: the record alone places the region's lattice — no re-survey.
    assert record.capture_sha256 == CAPTURE
    assert (record.support_origin_px, record.support_step_px,
            record.support_extent_px) == (candidate.support.origin_yx,
                                          candidate.support.step_px,
                                          candidate.support.extent_px)
    assert record.resource_key() == key_of(CAPTURE, candidate.support)


def test_candidates_are_frozen() -> None:
    candidate = region_candidates(CAPTURE, make_survey([make_mask()]))[0]
    with pytest.raises(Exception):
        candidate.capture_sha256 = OTHER_CAPTURE  # type: ignore[misc]
