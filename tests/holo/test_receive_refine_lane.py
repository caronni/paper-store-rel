"""The v0.42 K refinement level R(Lk) leaf (RECEIVE-DESIGN v0.42 clause B).

Three pins over the new seam:

* the pixel-free pre-gates (no poses / no frontier / every committed span
  certified) commit an empty delta WITHOUT reading a single raster pixel —
  the lazy R-level raster stand-in never materializes;
* ``place_committed`` re-derives the base lane's committed pose inventory
  deterministically as payload-capable placements;
* an adopted refinement emits an affected-regions-ONLY delta in the R
  lane's OWN evidence namespace: blocks/attempts/certificates under the R
  lane id, adopted poses minted under the R lane id via the
  replacement-address seam with base-lineage-union-frontier dependencies,
  and NOTHING from unaffected regions.
"""
from __future__ import annotations

import hashlib
import pickle

import numpy as np
import pytest

from _e023c_fixtures import _page_fixture, _segment_fixture
from holo.receive import production_refine
from holo.receive.evidence_context import EvidenceContext
from holo.receive.place import place_committed
from holo.receive.production import _page_to_view_affine
from holo.receive.production_payload import ProductionPayload
from holo.receive.placement.model import (
    AddressResult,
    CandidateScore,
    PlacedPatch,
)
from holo.receive.runtime import LaneContext
from holo.receive.session import CaptureFacts
from holo.receive.types import (
    AddressArtifact,
    AddressProduct,
    LaneSpec,
    PoseRecord,
    RefineAddressPlan,
    Stage,
    SupportRun,
    SurveyArtifact,
    SurveyProduct,
    SurveyRegionRecord,
)


BASE_LANE = "l8p1"
R_LANE = "r8p1"
_SHA = hashlib.sha256(b"refine-lane").hexdigest()


class _ForbiddenRaster:
    """A raster stand-in that fails the test on any pixel read."""

    dpi = 1200.0
    shape = (4096, 4096)

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        raise AssertionError("pre-gated R-level read raster pixels")


class _CountingRaster:
    def __init__(self, raster: object) -> None:
        self.raster = raster
        self.shape = raster.shape
        self.dpi = raster.dpi
        self.calls = 0

    def crop_luma(self, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        self.calls += 1
        return self.raster.crop_luma(r0, r1, c0, c1)


def _patch(fixture: object, patch_id: int, *, redundant: bool) -> PlacedPatch:
    placed = fixture.request.placed
    candidate = CandidateScore(
        0, placed.page_origin_yx, 0,
        0.0, 0.0, 0, 0, 100, 100, 10.0, True, "refine-lane-test",
    )
    cells = (
        placed.audited_cells_yx.astype(np.int64)
        + np.asarray(placed.page_origin_yx, np.int64)
    ).astype(np.int32)
    return PlacedPatch(
        patch_id,
        placed.segment.window.region_index,
        0,
        "refine-lane-test",
        candidate,
        (),
        placed,
        (),
        redundant,
        cells,
    )


def _fixture() -> tuple[object, AddressResult]:
    page = _page_fixture()
    segments = (
        _segment_fixture(
            page, window_id=0, region_index=0,
            page_origin_yx=(0, 0), shift_yx_cells=(0.125, -0.125)),
        _segment_fixture(
            page, window_id=1, region_index=0,
            page_origin_yx=(128, 0), shift_yx_cells=(0.0, 0.0)),
        _segment_fixture(
            page, window_id=2, region_index=1,
            page_origin_yx=(0, 128), shift_yx_cells=(0.0, 0.0)),
    )
    patches = tuple(
        _patch(row, index, redundant=index != 0)
        for index, row in enumerate(segments)
    )
    address = AddressResult(
        patches, (), (), ((0, "accepted"), (1, "accepted")), 3)
    return page, address


def _pose_record(patch: PlacedPatch, region_id: str) -> PoseRecord:
    """Durable base-lane row for one fixture placement (1:1 lane)."""
    segment = patch.segment
    fitted = segment.segment
    native = _page_to_view_affine(segment)
    return PoseRecord(
        pose_id=f"{_SHA}/{BASE_LANE}/patch-{int(patch.patch_id)}/pose",
        capture_id=_SHA,
        lane_id=BASE_LANE,
        region_id=region_id,
        patch_id=int(patch.patch_id),
        placement_outcome="redundant" if patch.redundant else "accepted",
        page=int(patch.candidate.page),
        cell_origin_yx=tuple(int(v) for v in segment.page_origin_yx),
        native_affine=tuple(float(v) for v in native.ravel()),
        rot90=int(segment.rot_k),
        quality=1.0,
        window_id=int(fitted.window.window_id),
        window_origin_yx_px=tuple(
            int(v) for v in fitted.window.origin_yx_px),
        window_shape_yx_cells=tuple(
            int(v) for v in fitted.window.shape_yx_cells),
        window_depth=int(fitted.window.depth),
        lane_pose_origin_yx=tuple(float(v) for v in fitted.pose.origin_yx),
        lane_pose_jacobian=tuple(
            float(v) for row in fitted.pose.jacobian_yx for v in row),
        lane_pose_phase_yx=tuple(float(v) for v in fitted.pose.phase_yx),
        lane_pose_pitch_px=float(fitted.pose.pitch_px),
        lane_pose_angle_deg=float(fitted.pose.angle_deg),
        segment_support_cells=int(fitted.support_cells),
        segment_phase_contrast=float(fitted.phase_contrast),
        segment_pitch_yx_px=tuple(
            float(v) for v in fitted.pitch_yx_px),
        segment_orthogonality_error_deg=float(
            fitted.orthogonality_error_deg),
    )


def _region_record(
    index: int, origin_yx: tuple[int, int], extent_yx: tuple[int, int],
) -> SurveyRegionRecord:
    """A full-support base-lane region over one pixel box (step 8)."""
    step = 8
    shape = (extent_yx[0] // step, extent_yx[1] // step)
    return SurveyRegionRecord(
        region_id=f"{_SHA}/{BASE_LANE}/region-{index}",
        capture_id=_SHA,
        lane_id=BASE_LANE,
        origin_yx=origin_yx,
        extent_yx=extent_yx,
        support_step_px=step,
        support_shape_yx=shape,
        support_runs=(SupportRun(0, shape[0] * shape[1]),),
        area_mm2=float(extent_yx[0]) * extent_yx[1] * (25.4 / 1200.0) ** 2,
        median_tensor_score=1.0,
    )


def _context(raster: object, events: list) -> LaneContext:
    return LaneContext(
        Stage.PAYLOAD,
        LaneSpec(R_LANE, 8, 1, 1, 1, parent_lane_id=BASE_LANE,
                 refine_of=BASE_LANE),
        _SPEC,
        raster,
        CaptureFacts(_SHA, 1200.0, "float32", raster.shape, 1),
        EvidenceContext(certificates=_CERTIFICATES),
        lambda: True,
        lambda: False,
        lambda name, *_args, **kwargs: events.append(
            (name, kwargs.get("details", ()))),
        lambda _name, callback: callback(),
        False,
    )


def _products() -> tuple[SurveyProduct, AddressProduct]:
    survey = SurveyProduct(
        SurveyArtifact(f"{_SHA}/{R_LANE}/survey", ()), ())
    address = AddressProduct(
        AddressArtifact(
            f"{_SHA}/{R_LANE}/address", f"{_SHA}/{R_LANE}/survey", ()),
        (),
        transient=RefineAddressPlan(
            base_lane_id=BASE_LANE,
            poses=_POSES,
            regions=_REGIONS,
            certificates=_CERTIFICATES,
        ))
    return survey, address


# One module-level fixture build (the page render is the expensive part).
_PAGE, _ADDRESS = _fixture()
_SPEC = _PAGE.spec
_REGIONS = (
    _region_record(0, (0, 0), (2048, 1024)),
    _region_record(1, (0, 1024), (1024, 1024)),
)
_POSES = tuple(
    _pose_record(patch, _REGIONS[patch.region_index].region_id)
    for patch in _ADDRESS.placements
)
# Partial frontier: patch 0's tiles minus (1, 1) — region 0 keeps an
# uncertified remainder, patches 1/2 train on no certified cargo.
_CERTIFICATES = tuple(
    row for row in _PAGE.certificates
    if row.tile_yx in ((0, 0), (0, 1), (1, 0)))


def test_pixel_free_pregates_commit_empty_without_reading_raster() -> None:
    events: list = []
    survey, address = _products()

    # (a) every committed span certified: the full fixture frontier
    # covers all tiles every window can touch.
    full = AddressProduct(
        address.artifact, (),
        transient=RefineAddressPlan(
            BASE_LANE, _POSES, _REGIONS, _PAGE.certificates))
    output = ProductionPayload().process(
        _context(_ForbiddenRaster(), events), survey, full)
    assert output.product.blocks == ()
    assert output.product.attempts == ()
    assert output.product.certificates == ()
    assert output.replacement_address is None

    # (b) no committed poses; (c) no frontier.
    for plan in (
        RefineAddressPlan(BASE_LANE, (), _REGIONS, _PAGE.certificates),
        RefineAddressPlan(BASE_LANE, _POSES, _REGIONS, ()),
    ):
        bare = AddressProduct(address.artifact, (), transient=plan)
        output = ProductionPayload().process(
            _context(_ForbiddenRaster(), events), survey, bare)
        assert output.product.blocks == ()
        assert output.product.certificates == ()
    # The empty delta is silent: no payload milestones, no pose_refine.
    assert events == []


def test_place_committed_rederives_the_committed_inventory() -> None:
    raster = _CountingRaster(_PAGE.raster)
    first = place_committed(
        raster, _SPEC, poses=_POSES, regions=_REGIONS)
    assert raster.calls > 0
    # All three committed poses re-derive, with their durable identities,
    # outcomes, and frozen discrete geometry.
    assert tuple(row.patch_id for row in first.placements) == (0, 1, 2)
    assert tuple(row.redundant for row in first.placements) == (
        False, True, True)
    assert tuple(row.region_index for row in first.placements) == (0, 0, 1)
    for patch, pose_row in zip(first.placements, _POSES, strict=True):
        assert patch.candidate.passes
        assert patch.candidate.page == pose_row.page
        assert patch.segment.rot_k == pose_row.rot90
        assert tuple(patch.segment.page_origin_yx) == tuple(
            pose_row.cell_origin_yx)
        assert (patch.segment.segment.pose.origin_yx
                == pose_row.lane_pose_origin_yx)
        # The audit re-derives a payload-capable support (the fixture
        # windows are fully on-page and clean).
        assert patch.page_cells_yx.shape[0] > 12000
    # Deterministic: a second reconstruction is byte-identical.
    second = place_committed(
        _CountingRaster(_PAGE.raster), _SPEC,
        poses=_POSES, regions=_REGIONS)
    assert pickle.dumps(first, protocol=5) == pickle.dumps(
        second, protocol=5)


def test_adoption_emits_only_the_affected_region_delta_in_own_namespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list = []
    survey, address = _products()
    # The reconstruction seam is pinned separately; here the leaf runs
    # from the fixture's exact placements.
    monkeypatch.setattr(
        production_refine, "place_committed",
        lambda *_args, **_kwargs: _ADDRESS)
    raster = _CountingRaster(_PAGE.raster)
    output = ProductionPayload().process(
        _context(raster, events), survey, address)
    product = output.product
    names = [name for name, _details in events]

    # Refinement ran over all three committed windows and adopted the
    # shifted one; its summaries publish at the R level now.
    assert names.count("pose_refine.window_progress") == 3
    refine_rows = [
        {row.name: row.value for row in details}
        for name, details in events
        if name == "pose_refine.window_progress"]
    adopted = [row for row in refine_rows if row["refinement.adopted"]]
    assert [row["refinement.patch"] for row in adopted] == [0]
    assert "payload.plan" in names
    plan_details = {
        row.name: row.value for name, details in events
        if name == "payload.plan" for row in details}
    assert plan_details["payload.refine_of"] == BASE_LANE
    assert plan_details["payload.needed_patches"] == 3

    # The adopted pose minted under the R lane's own namespace, with
    # base-lineage-union-frontier dependencies.
    replacement = output.replacement_address
    assert replacement is not None
    assert tuple(row.patch_id for row in replacement.poses) == (0,)
    minted = replacement.poses[0]
    assert minted.lane_id == R_LANE
    assert minted.pose_id == f"{_SHA}/{R_LANE}/patch-0/pose"
    assert minted.region_id == _REGIONS[0].region_id
    assert minted.placement_outcome == "accepted"
    certified_ids = {row.certificate_id for row in _CERTIFICATES}
    assert minted.dependency_certificate_ids
    assert set(minted.dependency_certificate_ids) <= certified_ids
    final_details = {
        row.name: row.value for name, details in events
        if name == "address.final" for row in details}
    assert final_details["address.refined"] is True

    # The delta covers ONLY the affected region (region 0): every block
    # sits on one of its uncertified tiles, owned by patches 0/1; region
    # 1 (patch 2, unadopted) contributes nothing.
    assert product.blocks
    region0_tiles = {
        (0, ty, tx) for ty in range(4) for tx in range(2)}
    certified_addresses = {
        (row.page, *row.tile_yx) for row in _CERTIFICATES}
    for block in product.blocks:
        assert block.lane_id == R_LANE
        assert block.source_sha256 == _SHA
        assert block.address in region0_tiles - certified_addresses
        assert {origin.patch_id for origin in block.origins} <= {0, 1}
    assert {row.lane_id for row in product.attempts} == {R_LANE}
    assert {(row.page, *row.tile_yx) for row in product.attempts} <= (
        region0_tiles - certified_addresses)
    # Freshly minted certificates stay within the delta's tile domain.
    assert {(row.page, *row.tile_yx) for row in product.certificates} <= (
        region0_tiles - certified_addresses)
    complete_details = {
        row.name: row.value for name, details in events
        if name == "payload.complete" for row in details}
    assert complete_details["payload.refinement_adopted"] == 1
    assert complete_details["payload.refinement_eligible"] >= 1
    assert product.mopup_dropped_observations == 0
    assert product.mopup_winner_flips == 0
