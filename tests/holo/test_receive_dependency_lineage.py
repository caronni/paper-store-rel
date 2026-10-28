"""Focused regressions for typed E022 lineage materialisation."""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from holo.core import bch
from holo.devices.profiles import make_spec
from holo.receive import tiles
from holo.receive.evidence_context import EvidenceContext
from holo.receive.place import placement_hint
from holo.receive.placement.model import (
    AddressResult,
    AffinePose,
    CandidateScore,
    KnownWord,
    PlacedPatch,
    PlacedSegment,
    PoseSegment,
    PoseWindow,
)
from holo.receive.production import _address_product
from holo.receive.session import CaptureFacts
from holo.receive.types import (
    LaneSpec,
    PoseProposal,
    SupportRun,
    SurveyArtifact,
    SurveyProduct,
    SurveyRegionRecord,
)


_CAPTURE_ID = "a" * 64
_DEPENDENCY_ID = "b" * 64
_INHERITED_HINT_ID = "lower/hint"


def _candidate() -> CandidateScore:
    return CandidateScore(
        0, (0, 0), 0, 0.01, 0.02, 0, 0, 50, 50, 8.0, True,
        "lower")


def _patch(
    patch_id: int,
    *,
    component: int,
    inherited_hint_id: str | None,
    redundant: bool = False,
) -> PlacedPatch:
    pose = AffinePose(
        (8.0, 8.0), ((4.0, 0.0), (0.0, 4.0)), (0.5, 0.5),
        4.0, 0.0)
    window = PoseWindow(patch_id, 0, (0, 0), (64, 64))
    segment = PoseSegment(window, pose, 64 * 64, 1.0, (4.0, 4.0), 0.0)
    cells = np.asarray(((0, 0),), np.int32)
    return PlacedPatch(
        patch_id, 0, component, "lower", _candidate(), (),
        PlacedSegment(segment, (0, 0), 0, cells), (), redundant, cells,
        inherited_hint_id)


def _survey() -> SurveyProduct:
    region = SurveyRegionRecord(
        "region-0", _CAPTURE_ID, "fine", (0, 0), (512, 512), 1,
        (1, 1), (SupportRun(0, 1),), 1.0, 1.0)
    return SurveyProduct(
        SurveyArtifact("survey", (region.region_id,)), (region,))


def _context() -> SimpleNamespace:
    inherited = PoseProposal(
        _INHERITED_HINT_ID, _CAPTURE_ID, "coarse", 0, 0,
        (0, 0), (512, 512), (8.0, 8.0),
        (4.0, 0.0, 8.0, 0.0, 4.0, 8.0), (_DEPENDENCY_ID,))
    return SimpleNamespace(
        capture=CaptureFacts(_CAPTURE_ID, 600.0, "uint8", (512, 512), 1),
        lane=LaneSpec("fine", 4, 1, 1, 1, "coarse"),
        evidence=EvidenceContext(proposals=(inherited,)),
        lane_to_native_affine=lambda value: np.asarray(value, np.float64),
        lane_to_native_points=lambda value: np.asarray(value, np.float64),
    )


def _result(*patches: PlacedPatch) -> AddressResult:
    hints = tuple(
        placement_hint(
            f"fine/hint-{patch.patch_id}", patch.candidate,
            patch.segment.segment, patch.segment.page_origin_yx,
            kind="accepted", patch_id=patch.patch_id)
        for patch in patches
    )
    return AddressResult(
        tuple(patches), (), (), ((0, "accepted"),), len(patches), hints)


def test_typed_inherited_hint_carries_direct_dependency() -> None:
    patch = _patch(
        0, component=-1, inherited_hint_id=_INHERITED_HINT_ID,
        redundant=True)

    product = _address_product(_context(), _survey(), _result(patch))

    assert product.poses[0].dependency_certificate_ids == (_DEPENDENCY_ID,)
    assert product.proposals[0].dependency_certificate_ids == (
        _DEPENDENCY_ID,)


def test_component_chain_carries_seed_dependency() -> None:
    seed = _patch(
        0, component=4, inherited_hint_id=_INHERITED_HINT_ID)
    chained = _patch(1, component=4, inherited_hint_id=None)

    product = _address_product(
        _context(), _survey(), _result(seed, chained))

    assert tuple(row.dependency_certificate_ids for row in product.poses) == (
        (_DEPENDENCY_ID,), (_DEPENDENCY_ID,))
    assert tuple(
        row.dependency_certificate_ids for row in product.proposals
    ) == ((_DEPENDENCY_ID,), (_DEPENDENCY_ID,))


def test_unknown_typed_inherited_hint_fails_closed() -> None:
    patch = _patch(0, component=0, inherited_hint_id="missing/hint")

    with pytest.raises(ValueError, match="unknown lower-scale hint"):
        _address_product(_context(), _survey(), _result(patch))


def test_known_word_uses_canonical_bch_word_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bch, "N_WORD", 17)

    word = KnownWord(0, (0, 0), 0, None, None, 17)

    assert word.observed_sites == 0
    with pytest.raises(ValueError, match=r"\[0, 17\]"):
        KnownWord(0, (0, 0), 0, None, None, 18)


def test_engine_empty_retry_frontier_spends_no_budget() -> None:
    # Family unification 2026-07-30: the retry frontier is computed once by
    # the shared engine from its own recorded rows; with no work there is
    # no retry traversal and no leaf call at all.
    from holo.receive.payload_engine import run_attempts

    class _NoWorkLeaf:
        def unresolved_streams(self, _address):
            return ()

        def attempt(self, _view, _stream_id, _stage):
            pytest.fail("empty schedule invoked the leaf")

    run = run_attempts((), (), lane_id="lane", leaf=_NoWorkLeaf())
    assert run.attempts == ()
    assert run.retry_frontier == ()
    assert run.terminal_close is False
