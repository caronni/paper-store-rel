"""Color certified pose refinement: adoption gates, identity, R-lane leaf.

v0.42 stage C: the leaf-level pins (adoption gate, adversarial gate,
frozen discrete identity, crop-free cargo pre-gate) survive from the
inline era; the driver A/B is now an R-lane A/B — the ordinary color
barrier never refines, and the refinement level R(Lk) drives the codec
leaf over the base lane's committed poses through the SHARED
``place.place_committed`` audited reconstruction (K parity; the
window-rectangle shortcut it replaced crashed the R delta's sampling on
partial-coverage scrap material).
"""
from __future__ import annotations

import pickle
from dataclasses import replace

import numpy as np
import pytest
from scipy.ndimage import gaussian_filter

from holo.core import channel
from holo.format import metadata
from holo.format.registry import get_format_row
from holo.gen.color_compose import compose_color_tile
from holo.receive import (
    color_conditioning,
    color_context,
    color_locality,
    color_payload,
    color_refine,
    color_stack,
    production_color,
)
from holo.receive.color_payload import collect_color_evidence
from holo.receive.color_refine import (
    affected_color_patch_ids,
    refine_color_address_once,
)
from holo.receive.evidence_context import EvidenceContext
from holo.receive.payload_model import EvidenceSource, PlacementModelError
from holo.receive.place import place_committed
from holo.receive.placement.model import (
    AddressResult,
    AffinePose,
    CandidateScore,
    PlacedPatch,
    PlacedSegment,
    PoseSegment,
    PoseWindow,
)
from holo.receive.production import _address_product
from holo.receive.records import certificate_record_from_user_bits
from holo.receive.runtime import LaneContext
from holo.receive.scan import open_capture
from holo.receive.session import CaptureFacts
from holo.receive.types import (
    AddressArtifact,
    AddressProduct,
    LaneSpec,
    RefineAddressPlan,
    Stage,
    SupportRun,
    SurveyArtifact,
    SurveyProduct,
    SurveyRegionRecord,
)


ROW = "c2-cmy7-p120-v0@3328x2304"
LANE = "l00-2ppc-600dpi"
R_LANE = "r00-2ppc-600dpi"
PPC = 4
K_TOTAL = 837
BLUR_PX = 1.2


def _candidate() -> CandidateScore:
    return CandidateScore(
        0, (0, 0), 0, 0.0, 0.0, 0, 0, 1000, 1000, 20.0, True, "refine-test")


def _grid(shape: tuple[int, int]) -> np.ndarray:
    yy, xx = np.meshgrid(
        np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    return np.stack((yy, xx), axis=-1).reshape(-1, 2).astype(np.int32)


def _compose_field(spec, tiles_yx, seed):
    rng = np.random.default_rng(seed)
    height, width = tiles_yx[0] * 64, tiles_yx[1] * 64
    field = np.empty((height, width), np.uint8)
    symbols_by_tile = {}
    for ty in range(tiles_yx[0]):
        for tx in range(tiles_yx[1]):
            counter = spec.tile_counter(0, ty, tx)
            symbols = {
                stream.stream_id: rng.integers(
                    0, 2, stream.symbol_bits, dtype=np.uint8)
                for stream in spec.stream_profiles
            }
            symbols_by_tile[(ty, tx)] = symbols
            field[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = (
                compose_color_tile(spec, counter, symbols, K_TOTAL))
    return field, symbols_by_tile


def _raster_from_field(field: np.ndarray):
    planes = channel.states_to_planes(field)
    rgb = np.repeat(np.repeat(
        (1 - planes) * np.uint8(255), PPC, axis=0), PPC, axis=1)
    rgb = rgb.astype(np.float64)
    for plane in range(3):
        rgb[..., plane] = gaussian_filter(
            rgb[..., plane], BLUR_PX, mode="nearest")
    return open_capture(
        np.clip(np.round(rgb), 0, 255).astype(np.uint8), 600.0)


def _patch(
    patch_id: int,
    region_index: int,
    page_origin_yx: tuple[int, int],
    shape_cells: tuple[int, int],
    shift_cells: tuple[float, float],
) -> PlacedPatch:
    center = (PPC - 1.0) * 0.5
    true_origin = np.asarray((
        page_origin_yx[0] * PPC + center,
        page_origin_yx[1] * PPC + center,
    ), np.float64)
    jacobian = ((float(PPC), 0.0), (0.0, float(PPC)))
    origin = true_origin + np.asarray(jacobian) @ np.asarray(
        shift_cells, np.float64)
    pose = AffinePose(
        tuple(float(value) for value in origin), jacobian,
        (0.5, 0.5), float(PPC), 0.0)
    local = _grid(shape_cells)
    segment = PoseSegment(
        PoseWindow(patch_id, region_index, (0, 0), shape_cells),
        pose, local.shape[0], 1.0, (float(PPC), float(PPC)), 0.0)
    placed = PlacedSegment(segment, page_origin_yx, 0, local)
    page_cells = local.astype(np.int64) + np.asarray(
        page_origin_yx, np.int64)
    return PlacedPatch(
        patch_id, region_index, 0, "refine-test", _candidate(), (),
        placed, (), False, page_cells.astype(np.int32))


def _certificates(spec, symbols_by_tile, tiles):
    meta = metadata.encode_metadata(0, K_TOTAL)
    records = []
    for ty, tx in tiles:
        counter = spec.tile_counter(0, ty, tx)
        user = np.concatenate((
            np.asarray([metadata.tile_bit(meta, counter)], np.uint8),
            symbols_by_tile[(ty, tx)]["main"]))
        records.append(certificate_record_from_user_bits(
            spec, page=0, tile_yx=(ty, tx), stream_id="main",
            user_bits=user, origin_attempt_id=f"refine-fixture-{ty}-{tx}"))
    return tuple(records)


def _single_window_fixture(shift_cells=(0.15, -0.2)):
    spec = get_format_row(ROW)
    field, symbols = _compose_field(spec, (2, 3), 0xC0161)
    raster = _raster_from_field(field)
    patch = _patch(0, 0, (0, 0), (128, 192), shift_cells)
    address = AddressResult((patch,), (), (), ((0, "placed"),), 1)
    source = EvidenceSource(raster.source.sha256, LANE)
    certs = _certificates(
        spec, symbols, ((0, 0), (0, 1), (1, 0), (1, 2)))
    return spec, raster, address, source, certs


def _origin_error_px(pose: AffinePose, page_origin_yx=(0, 0)) -> float:
    center = (PPC - 1.0) * 0.5
    true_origin = (
        page_origin_yx[0] * PPC + center,
        page_origin_yx[1] * PPC + center,
    )
    return float(np.hypot(*(np.asarray(pose.origin_yx)
                            - np.asarray(true_origin, np.float64))))


def test_perturbed_color_pose_adopts_and_recovers_geometry() -> None:
    spec, raster, address, source, certs = _single_window_fixture()
    generation0 = collect_color_evidence(
        raster, source, address, spec, certificates=certs)
    assert len(generation0.windows) == 1

    refinement = refine_color_address_once(
        raster, address, generation0, spec, certs)

    assert refinement.eligible == 1
    assert refinement.adopted == 1
    summary = refinement.summaries[0]
    metrics = summary.metrics
    assert metrics.reason == "adopted"
    assert (metrics.candidate_validation_logloss
            < metrics.baseline_validation_logloss)
    assert (metrics.candidate_furniture_logloss
            <= metrics.baseline_furniture_logloss
            + color_refine.FURNITURE_LOSS_SLACK)
    assert metrics.n_certified_blocks >= 4
    before = _origin_error_px(
        address.placements[0].segment.segment.pose)
    after = _origin_error_px(
        refinement.address.placements[0].segment.segment.pose)
    # The bounded grid must move the pose toward the true geometry; the
    # exact recovered fraction is fixture-dependent (grid quantization).
    assert after <= before * 0.8
    # Adopted labels carry the certificate lineage.
    assert summary.dependency_certificate_ids == tuple(sorted(
        record.certificate_id for record in certs))
    assert refinement.patch_dependencies == (
        (0, summary.dependency_certificate_ids),)


def test_true_pose_baseline_keeps_active_pose_without_adoption() -> None:
    spec, raster, address, source, certs = _single_window_fixture(
        shift_cells=(0.0, 0.0))
    generation0 = collect_color_evidence(
        raster, source, address, spec, certificates=certs)

    refinement = refine_color_address_once(
        raster, address, generation0, spec, certs)

    assert refinement.eligible == 1
    assert refinement.adopted == 0
    # Blur asymmetry may rank a near-zero candidate above the exact active
    # pose on train contrast; either way the held-out gate must keep the
    # true-pose geometry unchanged.
    assert refinement.summaries[0].metrics.reason in (
        "active_pose_selected", "pose_gate_failed")
    assert refinement.address is address


def test_adversarial_search_cannot_force_adoption_past_heldout_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A search preferring misaligned candidates must fail the gate."""
    spec, raster, address, source, certs = _single_window_fixture(
        shift_cells=(0.0, 0.0))
    generation0 = collect_color_evidence(
        raster, source, address, spec, certificates=certs)
    baseline_objective = color_refine._pose_objective
    monkeypatch.setattr(
        color_refine, "_pose_objective",
        lambda raw, values, weights: -baseline_objective(
            raw, values, weights))

    refinement = refine_color_address_once(
        raster, address, generation0, spec, certs)

    assert refinement.eligible == 1
    assert refinement.adopted == 0
    metrics = refinement.summaries[0].metrics
    assert metrics.reason == "pose_gate_failed"
    assert (metrics.candidate_validation_logloss + 1e-4
            >= metrics.baseline_validation_logloss
            or metrics.candidate_furniture_logloss
            > metrics.baseline_furniture_logloss
            + color_refine.FURNITURE_LOSS_SLACK)
    assert refinement.address is address
    assert refinement.summaries[0].refined \
        is refinement.summaries[0].baseline


def test_adoption_never_changes_frozen_discrete_identity() -> None:
    spec, raster, address, source, certs = _single_window_fixture()
    generation0 = collect_color_evidence(
        raster, source, address, spec, certificates=certs)
    refinement = refine_color_address_once(
        raster, address, generation0, spec, certs)
    summary = refinement.summaries[0]
    assert summary.metrics.adopted

    base, fitted = summary.baseline, summary.refined
    assert fitted.segment.segment.pose != base.segment.segment.pose
    assert fitted.segment.rot_k == base.segment.rot_k
    assert fitted.segment.page_origin_yx == base.segment.page_origin_yx
    assert fitted.candidate == base.candidate
    assert np.array_equal(
        fitted.segment.audited_cells_yx, base.segment.audited_cells_yx)
    assert np.array_equal(fitted.page_cells_yx, base.page_cells_yx)

    # Tampering with the frozen discrete identity refuses at construction.
    rotated = replace(
        fitted, segment=replace(fitted.segment, page_origin_yx=(64, 0)))
    with pytest.raises(ValueError, match="frozen discrete identity"):
        color_refine.ColorWindowRefinement(
            summary.patch_id, base, rotated,
            summary.dependency_certificate_ids,
            summary.frontier_id, summary.metrics)


def test_r_delta_covers_exactly_the_affected_regions() -> None:
    """The v0.42 R delta: affected regions byte-equal to a forced full
    recompute; unaffected regions contribute NOTHING at the R barrier."""
    spec = get_format_row(ROW)
    field, symbols = _compose_field(spec, (2, 6), 0xC0162)
    raster = _raster_from_field(field)
    aligned = _patch(0, 0, (0, 0), (128, 192), (0.0, 0.0))
    perturbed = _patch(1, 1, (0, 192), (128, 192), (0.15, -0.2))
    address = AddressResult(
        (aligned, perturbed), (), (),
        ((0, "placed"), (1, "placed")), 2)
    source = EvidenceSource(raster.source.sha256, R_LANE)
    # Certificates only under the perturbed region: the aligned region has
    # no cargo labels (crop-free ineligible, never adopts) and must be
    # entirely absent from the delta.
    certs = _certificates(spec, symbols, (
        (0, 3), (0, 4), (1, 3), (1, 5),
    ))

    # R-level drive: no generation zero — the committed-pose domain.
    refinement = refine_color_address_once(
        raster, address, None, spec, certs)
    adopted_ids = tuple(
        row.patch_id for row in refinement.summaries
        if row.metrics.adopted)
    assert adopted_ids == (1,)
    by_patch = {row.patch_id: row.metrics for row in refinement.summaries}
    assert not by_patch[0].eligible
    assert by_patch[0].reason == "insufficient_payload_train"

    included = affected_color_patch_ids(refinement.address, adopted_ids)
    assert included == frozenset({1})
    delta = collect_color_evidence(
        raster, source, refinement.address, spec,
        certificates=certs, included_patch_ids=included)
    forced_full = collect_color_evidence(
        raster, source, refinement.address, spec, certificates=certs)

    # The delta names only the affected region.
    assert {row.patch_id for row in delta.windows} == {1}
    assert {row.patch_id for row in forced_full.windows} == {0, 1}
    expected = next(
        row for row in forced_full.windows if row.patch_id == 1)
    actual = next(row for row in delta.windows if row.patch_id == 1)
    assert actual.placement_id == expected.placement_id
    assert actual.region_id == expected.region_id
    assert actual.heldout_logloss == expected.heldout_logloss
    assert actual.dependency_certificate_ids \
        == expected.dependency_certificate_ids
    assert np.array_equal(actual.page_cells_yx, expected.page_cells_yx)
    assert np.array_equal(
        actual.evidence_values, expected.evidence_values)
    # Region summaries: exactly the affected (region, page) fit, equal to
    # the forced full recompute's.
    assert len(delta.regions) == 1
    full_by_id = {row.region_id: row for row in forced_full.regions}
    assert delta.regions[0] == full_by_id[delta.regions[0].region_id]
    # Owner pages carry only affected-window cells, byte-equal to the
    # forced recompute's rows owned by the affected window.
    assert len(delta.pages) == 1
    full_page = forced_full.pages[0]
    full_window_of = {
        index: row.patch_id
        for index, row in enumerate(forced_full.windows)}
    owned_by_affected = np.asarray(tuple(
        full_window_of[int(value)] == 1
        for value in full_page.window_indices), bool)
    assert np.array_equal(
        delta.pages[0].cells_yx, full_page.cells_yx[owned_by_affected])
    assert np.array_equal(
        delta.pages[0].evidence_values,
        full_page.evidence_values[owned_by_affected])


def test_affected_patch_ids_close_over_the_region() -> None:
    spec = get_format_row(ROW)
    first = _patch(0, 0, (0, 0), (64, 64), (0.0, 0.0))
    second = _patch(1, 0, (64, 0), (64, 64), (0.0, 0.0))
    other = _patch(2, 1, (0, 192), (64, 64), (0.0, 0.0))
    del spec
    address = AddressResult(
        (first, second, other), (), (),
        ((0, "placed"), (1, "placed")), 3)
    assert affected_color_patch_ids(address, (0,)) == frozenset({0, 1})
    with pytest.raises(ValueError, match="adopted placement"):
        affected_color_patch_ids(address, ())
    with pytest.raises(ValueError, match="promoted domain"):
        affected_color_patch_ids(address, (9,))


def _lane_context(spec, raster, events, evidence, lane=None):
    facts = CaptureFacts(
        raster.source.sha256,
        raster.dpi,
        raster.source.dtype,
        raster.source.shape,
        raster.source.channels,
    )
    return LaneContext(
        Stage.PAYLOAD,
        lane if lane is not None else LaneSpec(LANE, 2, 1, 1, 1),
        spec,
        raster,
        facts,
        evidence,
        lambda: True,
        lambda: False,
        lambda name, *_args, **kwargs: events.append(
            (name, kwargs.get("details", ()))),
        lambda _name, callback: callback(),
        False,
    )


def _detail_map(details):
    return {row.name: row.value for row in details}


def _region_record(raster, support_columns=None):
    """Full-support base-lane region over the raster (64 px support step).

    ``support_columns`` restricts support to the first N step-columns of
    every row — the partial-coverage (scrap) shape; ``None`` is full
    support.  The grid is consistent with ``region_from_record`` so the
    shared ``place_committed`` reconstruction can materialize it.
    """
    extent = tuple(int(value) for value in raster.shape)
    step = 64
    shape = (-(-extent[0] // step), -(-extent[1] // step))
    columns = shape[1] if support_columns is None else int(support_columns)
    runs = (
        (SupportRun(0, shape[0] * shape[1]),)
        if columns == shape[1]
        else tuple(
            SupportRun(row * shape[1], columns) for row in range(shape[0]))
    )
    return SurveyRegionRecord(
        f"{raster.source.sha256}/{LANE}/region-0",
        raster.source.sha256,
        LANE,
        (0, 0),
        extent,
        step,
        shape,
        runs,
        100.0,
        1.0,
    )


def _base_barrier(spec, raster, address, certs, events):
    """Run the ordinary (non-refining) color barrier; return its pieces."""
    context = _lane_context(
        spec, raster, events, EvidenceContext(certificates=certs))
    region_record = _region_record(raster)
    survey = SurveyProduct(
        SurveyArtifact("survey-refine", (region_record.region_id,)),
        (region_record,))
    address_product = _address_product(context, survey, address)
    output = production_color.ProductionColorPayload().process(
        context, survey, address_product)
    return context, region_record, address_product, output


def _r_level_products(raster, plan):
    survey = SurveyProduct(
        SurveyArtifact(f"{raster.source.sha256}/{R_LANE}/survey", ()), ())
    address = AddressProduct(
        AddressArtifact(
            f"{raster.source.sha256}/{R_LANE}/address",
            survey.artifact.survey_id, ()),
        (), transient=plan)
    return survey, address


def test_r_lane_ab_certificates_do_not_regress_and_events_fire() -> None:
    """The v0.42 A/B: arm A is the default invocation (ordinary ladder
    only — the color barrier NEVER refines inline); arm B extends the
    session through the refinement level (``--refine``), which must adopt
    from the committed poses and certify no fewer streams."""
    spec, raster, address, _source, certs = _single_window_fixture()

    # ---- Arm A: ordinary barrier, no refinement machinery at all. ----
    base_events: list = []
    _context, region_record, address_product, base_output = _base_barrier(
        spec, raster, address, certs, base_events)
    base_product = base_output.product
    assert base_product is not None
    baseline_certified = len(base_product.certificates)
    # Two open tiles, one stream each: the clean fixture certifies both.
    assert baseline_certified == 2
    base_names = [name for name, _details in base_events]
    assert "pose_refine.window_progress" not in base_names
    assert "address.final" not in base_names
    assert base_output.replacement_address is None
    base_complete = _detail_map(
        base_events[base_names.index("payload.complete")][1])
    assert "color.refinement_eligible" not in base_complete

    # ---- Arm B: the R(Lk) level over the committed base poses, with the
    # same pre-R certificate frontier (the base evidence never crosses —
    # only certificates do). ----
    plan = RefineAddressPlan(
        base_lane_id=LANE,
        poses=address_product.poses,
        regions=(region_record,),
        certificates=certs,
    )
    r_events: list = []
    r_lane = LaneSpec(R_LANE, 2, 1, 1, 1, refine_of=LANE)
    r_context = _lane_context(
        spec, raster, r_events,
        EvidenceContext(
            certificates=certs,
            regions=(region_record,),
            label_poses=address_product.poses),
        lane=r_lane)
    r_survey, r_address = _r_level_products(raster, plan)

    output = production_color.ProductionColorPayload().process(
        r_context, r_survey, r_address)

    product = output.product
    assert product is not None
    # The R level alone re-certifies the open tiles from its own delta:
    # no fewer streams than the arm-A baseline.
    assert len(product.certificates) >= baseline_certified
    names = [name for name, _details in r_events]
    assert "pose_refine.window_progress" in names
    final_index = names.index("address.final")
    assert names.index("pose_refine.window_progress") < final_index
    assert final_index < names.index("payload.owner_frozen")
    final_details = _detail_map(r_events[final_index][1])
    assert final_details["address.refined"] is True
    assert final_details["address.placements"] == 1
    refine_details = _detail_map(
        r_events[names.index("pose_refine.window_progress")][1])
    assert refine_details["refinement.adopted"] is True
    assert refine_details["refinement.reason"] == "adopted"
    complete_details = _detail_map(
        r_events[names.index("payload.complete")][1])
    assert complete_details["color.refinement_eligible"] == 1
    assert complete_details["color.refinement_adopted"] == 1
    assert complete_details["lane.id"] == R_LANE

    # Adopted refined poses are minted under the R lane's own namespace.
    replacement = output.replacement_address
    assert replacement is not None
    assert len(replacement.poses) == 1
    pose = replacement.poses[0]
    assert pose.lane_id == R_LANE
    assert pose.pose_id == (
        f"{raster.source.sha256}/{R_LANE}/patch-0/pose")
    assert pose.region_id == region_record.region_id
    assert pose.dependency_certificate_ids == tuple(sorted(
        record.certificate_id for record in certs))
    assert product.artifact.address_id \
        == replacement.artifact.address_id
    # Delta evidence keys on the R lane's own evidence namespace.
    assert all(row.lane_id == R_LANE for row in product.blocks)
    assert all(row.lane_id == R_LANE for row in product.attempts)


def test_committed_pose_reconstruction_replays_geometry() -> None:
    """The shared ``place_committed`` reconstruction replays the exact
    durable lane-frame pose, re-audits a payload-capable inventory inside
    the base window, and is deterministic (byte-identical re-derivation:
    the bit-exactness claim of the audited committed-pose domain)."""
    spec, raster, address, _source, certs = _single_window_fixture()
    events: list = []
    _context, region_record, address_product, _output = _base_barrier(
        spec, raster, address, certs, events)
    original = address.placements[0]

    rebuilt = place_committed(
        raster, spec, poses=address_product.poses,
        regions=(region_record,))

    assert len(rebuilt.payload_placements) == 1
    patch = rebuilt.payload_placements[0]
    assert patch.patch_id == original.patch_id
    assert patch.region_index == original.region_index
    assert patch.segment.segment.pose == original.segment.segment.pose
    assert patch.segment.rot_k == original.segment.rot_k
    assert patch.segment.page_origin_yx == original.segment.page_origin_yx
    assert patch.candidate.page == original.candidate.page
    assert patch.candidate.passes
    # The audited inventory is a substantial subset of the base window's
    # cells (the audit, not the rectangle, is the inventory).
    original_cells = {
        (int(y), int(x)) for y, x in np.asarray(original.page_cells_yx)}
    rebuilt_cells = {
        (int(y), int(x)) for y, x in np.asarray(patch.page_cells_yx)}
    assert rebuilt_cells <= original_cells
    assert len(rebuilt_cells) > 12000
    # Bit-exact: an independent reconstruction is byte-identical.
    again = place_committed(
        raster, spec, poses=address_product.poses,
        regions=(region_record,))
    assert pickle.dumps(rebuilt, protocol=5) \
        == pickle.dumps(again, protocol=5)


def _partial_coverage_fixture():
    """A scrap fixture: the page continues past both the support edge
    (x >= 512 px is bare platen paper) and the acquisition edge (the
    raster ends mid-window at x = 639 px)."""
    spec = get_format_row(ROW)
    field, symbols = _compose_field(spec, (2, 3), 0xC0165)
    planes = channel.states_to_planes(field)
    rgb = np.repeat(np.repeat(
        (1 - planes) * np.uint8(255), PPC, axis=0), PPC, axis=1)
    rgb = rgb.astype(np.float64)
    rgb[:, 512:, :] = 255.0
    for plane in range(3):
        rgb[..., plane] = gaussian_filter(
            rgb[..., plane], BLUR_PX, mode="nearest")
    raster = open_capture(
        np.clip(np.round(rgb), 0, 255).astype(np.uint8)[:, :639], 600.0)
    patch = _patch(0, 0, (0, 0), (128, 192), (0.0, 0.0))
    certs = _certificates(spec, symbols, ((0, 0), (0, 1), (1, 0)))
    return spec, raster, patch, certs


def _with_adopted_pose(patch: PlacedPatch) -> PlacedPatch:
    """A bounded adopted pose revision (+0.25 cells in x, K's grid)."""
    pose = patch.segment.segment.pose
    shifted = replace(
        pose, origin_yx=(pose.origin_yx[0], pose.origin_yx[1] + 0.25 * PPC))
    return replace(
        patch,
        segment=replace(
            patch.segment,
            segment=replace(patch.segment.segment, pose=shifted)))


def test_partial_coverage_rectangle_crashes_audited_domain_completes(
) -> None:
    """The real-corpus R-lane crash at fixture scale, by construction.

    Pre-fix, the color R leaf rebuilt each committed window as the FULL
    window rectangle clipped to page+raster bounds.  On scrap material
    the rectangle keeps off-support cells right up to the acquisition
    edge; once refinement adopts a bounded pose revision (frozen discrete
    identity: the cell set never changes), the R delta's
    ``collect_color_evidence`` sampling walks those cells past the
    raster-clipped window crop and the ``_sample`` trust boundary
    correctly refuses.  The shared ``place_committed`` reconstruction
    re-audits the base aperture instead: its inventory excludes the
    off-support cells, re-derives bit-exactly, and the same adopted-pose
    delta completes.
    """
    spec, raster, base_patch, certs = _partial_coverage_fixture()
    source = EvidenceSource(raster.source.sha256, R_LANE)

    # ---- The rectangle shortcut (the deleted reconstruction, verbatim
    # inventory law): full window rectangle, clipped to page and raster.
    pose0 = base_patch.segment.segment.pose
    local = _grid((128, 192)).astype(np.int64)
    points = pose0.points(local.astype(np.float64))
    keep = (
        (points[:, 0] >= 0.0)
        & (points[:, 0] <= float(raster.shape[0] - 1))
        & (points[:, 1] >= 0.0)
        & (points[:, 1] <= float(raster.shape[1] - 1))
    )
    rect_local = local[keep].astype(np.int32)
    rect_segment = PoseSegment(
        PoseWindow(0, 0, (0, 0), (128, 192)),
        pose0, int(rect_local.shape[0]), 1.0, (float(PPC), float(PPC)), 0.0)
    rect_patch = PlacedPatch(
        0, 0, 0, "refine-test", _candidate(), (),
        PlacedSegment(rect_segment, (0, 0), 0, rect_local),
        (), False, rect_local)
    # The rectangle keeps off-support cells (past the 128-cell support
    # edge) all the way to the acquisition edge.
    assert int(np.max(rect_patch.page_cells_yx[:, 1])) >= 128
    adopted_rect = _with_adopted_pose(rect_patch)
    with pytest.raises(PlacementModelError, match="leaves the region crop"):
        collect_color_evidence(
            raster, source,
            AddressResult(
                (adopted_rect,), (), (), ((0, "placed"),), 1),
            spec, certificates=certs, included_patch_ids=frozenset({0}))

    # ---- The shared audited reconstruction (the fix).
    region_record = _region_record(raster, support_columns=8)
    events: list = []
    context = _lane_context(
        spec, raster, events, EvidenceContext(certificates=certs))
    survey = SurveyProduct(
        SurveyArtifact("survey-partial", (region_record.region_id,)),
        (region_record,))
    poses = _address_product(
        context, survey,
        AddressResult((base_patch,), (), (), ((0, "placed"),), 1)).poses

    first = place_committed(
        raster, spec, poses=poses, regions=(region_record,))
    assert len(first.payload_placements) == 1
    rebuilt = first.payload_placements[0]
    # The audited inventory EXCLUDES the off-support cells: nothing at or
    # past the support edge, let alone the acquisition edge.
    assert int(np.max(rebuilt.page_cells_yx[:, 1])) < 128
    assert rebuilt.page_cells_yx.shape[0] > 8000
    # Bit-exact: an independent re-derivation is byte-identical.
    second = place_committed(
        raster, spec, poses=poses, regions=(region_record,))
    assert pickle.dumps(first, protocol=5) == pickle.dumps(
        second, protocol=5)
    # The SAME adopted-pose R delta completes on the audited inventory.
    adopted = _with_adopted_pose(rebuilt)
    delta = collect_color_evidence(
        raster, source,
        AddressResult((adopted,), (), (), ((0, "placed"),), 1),
        spec, certificates=certs, included_patch_ids=frozenset({0}))
    assert {int(row.patch_id) for row in delta.windows} == {0}


class _NoPixelRaster:
    """Metadata-complete stand-in that refuses every pixel read."""

    def __init__(self, source, shape, dpi=600.0):
        self.source = source
        self.shape = shape
        self.dpi = dpi

    def crop_native(self, *_args):
        raise AssertionError("R level read pixels without eligible work")

    def crop_luma(self, *_args):
        raise AssertionError("R level read pixels without eligible work")


def test_r_level_certified_complete_frontier_never_reads_pixels() -> None:
    """Every committed span fully certified => the pixel-free span
    pre-gate (K parity) commits the silent empty delta and the lazy
    raster stand-in never materializes."""
    spec, raster, address, _source, certs = _single_window_fixture()
    field_symbols = _compose_field(spec, (2, 3), 0xC0161)[1]
    all_certs = _certificates(
        spec, field_symbols,
        tuple((ty, tx) for ty in range(2) for tx in range(3)))
    events: list = []
    _context, region_record, address_product, _output = _base_barrier(
        spec, raster, address, certs, events)
    plan = RefineAddressPlan(
        base_lane_id=LANE,
        poses=address_product.poses,
        regions=(region_record,),
        certificates=all_certs,
    )
    sealed = _NoPixelRaster(raster.source, tuple(raster.shape), raster.dpi)
    r_events: list = []
    r_context = _lane_context(
        spec, sealed, r_events,
        EvidenceContext(
            certificates=all_certs,
            regions=(region_record,),
            label_poses=address_product.poses),
        lane=LaneSpec(R_LANE, 2, 1, 1, 1, refine_of=LANE))
    r_survey, r_address = _r_level_products(raster, plan)

    output = production_color.ProductionColorPayload().process(
        r_context, r_survey, r_address)

    product = output.product
    assert product is not None
    assert not product.blocks
    assert not product.attempts
    assert not product.certificates
    assert output.replacement_address is None
    # The empty delta is silent (mirroring the K leaf's pre-gates): no
    # payload milestones, no pose_refine events, no pixel read.
    assert r_events == []


def test_certified_complete_window_refuses_crop_free() -> None:
    """A window whose covered tiles are all fully certified refuses with
    ``certified_complete`` BEFORE any crop (the v0.42 per-window
    no-uncertified-remainder gate for mixed frontiers)."""
    spec = get_format_row(ROW)
    field, symbols = _compose_field(spec, (2, 3), 0xC0166)
    raster = _raster_from_field(field)
    patch = _patch(0, 0, (0, 0), (64, 64), (0.15, -0.2))
    address = AddressResult((patch,), (), (), ((0, "placed"),), 1)
    certs = _certificates(spec, symbols, ((0, 0), (1, 2)))

    sealed = _NoPixelRaster(raster.source, tuple(raster.shape), raster.dpi)
    refinement = refine_color_address_once(
        sealed, address, None, spec, certs)

    assert refinement.eligible == 0
    assert refinement.adopted == 0
    assert len(refinement.summaries) == 1
    assert refinement.summaries[0].metrics.reason == "certified_complete"
    assert refinement.address is address


def test_r_level_without_certificates_is_silent_and_empty() -> None:
    spec, raster, address, _source, certs = _single_window_fixture()
    events: list = []
    _context, region_record, address_product, _output = _base_barrier(
        spec, raster, address, certs, events)
    plan = RefineAddressPlan(
        base_lane_id=LANE,
        poses=address_product.poses,
        regions=(region_record,),
        certificates=(),
    )
    sealed = _NoPixelRaster(raster.source, tuple(raster.shape), raster.dpi)
    r_events: list = []
    r_context = _lane_context(
        spec, sealed, r_events,
        EvidenceContext(
            regions=(region_record,),
            label_poses=address_product.poses),
        lane=LaneSpec(R_LANE, 2, 1, 1, 1, refine_of=LANE))
    r_survey, r_address = _r_level_products(raster, plan)

    output = production_color.ProductionColorPayload().process(
        r_context, r_survey, r_address)

    product = output.product
    assert product is not None
    assert not product.blocks and not product.certificates
    assert not r_events  # the stage-A silent empty delta
    assert output.replacement_address is None


def test_color_payload_policy_literal_is_v8_r_lane() -> None:
    assert color_payload.COLOR_PAYLOAD_POLICY_ID == (
        "holo/e023b-e023c-color/provisional-v8-r-lane/"
        "rgb-furniture-qda-sparse-split-pava-tiepool-classbal-planezero-"
        "dust20-priorcert-label-rows-"
        "register-rect2-q010-shift5-localcrop-"
        "anchor512-binleft-"
        "winphot-gainoffset-adaptivehalo-shrink20-"
        "cmy7linf20-"
        "cmy7cal-temp7-heldout-subsplit-satfloor30-"
        "knownfield-conditioned-marginals-ulane-only-"
        "ctxmatrix-9bin-zeroanchor-sweeps3-floors80-20-40-10-"
        "union-lanes-a3-a4b-off-v4-zerofrontier-codingaware-"
        "certrefine-planecal-frozen-stripes-xy-furniture-nonregress-"
        "r-lane-audited-committed-pose-domain-affected-region-delta-"
        "nonzero-floor-max60-cmy7-demapiter3-preclose-selective-retry150"
    )
    assert production_color.ProductionColorPayload.policy_id \
        == color_payload.COLOR_PAYLOAD_POLICY_ID
    # PK8's segment sits in the DECODE-PROFILE tail, beside max60 and
    # retry150, because that is what it changes: the same evidence, more
    # BP work inside ONE attempt.  It is absent at the null, pinned
    # against the live constant by
    # `test_policy_id_names_the_cmy7_codec_leaf_constants`.
    assert ("nonzero-floor-max60-cmy7-demapiter3-preclose"
            in color_payload.COLOR_PAYLOAD_POLICY_ID)
    # PK10: A4b's token sits directly after the cmy7 head's — the two are
    # the halves of one ladder rung — and the identity block itself moved
    # to ``color_policy`` when this packet pushed ``color_payload`` past
    # the 1000-line rule.  ``color_payload`` re-exports the SAME object,
    # so every importer and every pin here is unchanged.  PK5's A5 token
    # follows BOTH: the neighbourhood corrector is the ladder's last rung
    # and corrects what A4/A4b leave.
    assert ("satfloor30-knownfield-conditioned-marginals-ulane-only-"
            "ctxmatrix-9bin-zeroanchor-sweeps3-floors80-20-40-10-"
            "union-lanes-a3-a4b-off-v4-zerofrontier-codingaware-certrefine"
            in color_payload.COLOR_PAYLOAD_POLICY_ID)
    # PK5's token is GENERATED from the effective config, so a swept run
    # cannot claim a variant or a floor it did not use.
    assert (f"{color_context.ContextConfig().policy_token}-"
            "union-lanes-a3-a4b-off-v4-zerofrontier-codingaware"
            in color_payload.COLOR_PAYLOAD_POLICY_ID)
    assert color_context.CONTEXT_VARIANT == (
        color_context.CONTEXT_VARIANT_MATRIX)
    from holo.receive import color_policy

    assert (color_payload.COLOR_PAYLOAD_POLICY_ID
            is color_policy.COLOR_PAYLOAD_POLICY_ID)
    # PK-CLEAN's token↔REACHABILITY cross-checks.  Three fragments named
    # states the tree no longer has, so they may never reappear: A3's two
    # retired region floors and A4b's retired park FLAG.  ``ulane-only``
    # is the truth that replaced ``parked0`` — the arm contributes on
    # every colour cmy8 capture, from its own lane, and nowhere else.
    for retired in ("dispfloor", "normdisp", "parked0", "halo025"):
        assert retired not in color_payload.COLOR_PAYLOAD_POLICY_ID
    # The v4 arm split (review disposition 2026-08-10) retires v3's whole
    # token the same way: a u-lane plan that refuses U(off)/U(a3) on an
    # empty frontier is a state shape this tree can no longer mint, so
    # the superseded string may never reappear either.
    assert ("union-lanes-a3-a4b-off-v3-codingaware"
            not in color_payload.COLOR_PAYLOAD_POLICY_ID)
    assert not hasattr(color_conditioning, "CONDITIONING_PARKED")
    assert not hasattr(color_locality, "A3_DISPERSION_FLOOR")
    assert not hasattr(color_locality, "A3_NORM_DISPERSION_FLOOR")
    from holo.receive import lane_uplift

    assert "a4b" in lane_uplift.UPLIFT_ARMS
    # PK4/PK4.1: the token names A3's ONE remaining swept constant (the
    # shrinkage prior — the halo is a starvation fallback, not a weight),
    # and it is GENERATED from it: the identity a decode declares cannot
    # drift from the number it fitted with.  It sits BEFORE the bound
    # because the maps change features, not scores.
    assert (f"{color_locality.WindowPhotometryConfig().policy_token}-"
            "cmy7linf20-" in color_payload.COLOR_PAYLOAD_POLICY_ID)
    assert (f"shrink{color_locality.WINDOW_PHOT_PRIOR_LABELS:g}-"
            in color_payload.COLOR_PAYLOAD_POLICY_ID)
    # P1's token names the head and its three load-bearing choices (the
    # 7-parameter temperature form; fitted out-of-sample on the nested
    # held-out sub-split; adopted only above PK3.1's deployment-population
    # saturation floor), and it sits AFTER the L-infinity bound because
    # the bound still applies — now to calibrated scores.
    assert "cmy7linf20-cmy7cal-temp7-heldout-subsplit-satfloor30-" in (
        color_payload.COLOR_PAYLOAD_POLICY_ID)
    # The token's floor and the constant it names cannot drift apart.
    assert (f"satfloor{round(color_stack.HEAD_SATURATION_FLOOR * 100):02d}-"
            in color_payload.COLOR_PAYLOAD_POLICY_ID)


def test_mint_once_projection_cache_serves_one_immutable_object() -> None:
    spec = get_format_row(ROW)
    _field, symbols = _compose_field(spec, (1, 1), 0xC0163)
    records = _certificates(spec, symbols, ((0, 0),))
    from holo.receive.color_projection import (
        cached_certified_color_projection,
        project_certified_color_tile,
    )

    first = cached_certified_color_projection(records, spec, (0, 0, 0))
    second = cached_certified_color_projection(records, spec, (0, 0, 0))
    naive = project_certified_color_tile(records, spec, (0, 0, 0))

    assert second is first
    assert not first.component_bits.flags.writeable
    assert np.array_equal(first.component_bits, naive.component_bits)
    assert np.array_equal(first.known_mask, naive.known_mask)
    assert first.dependency_certificate_ids \
        == naive.dependency_certificate_ids


def test_zero_cargo_overlap_window_refuses_without_cropping(
        monkeypatch) -> None:
    """v0.41 checkpoint fix: the crop-free pre-gate is byte-identical.

    A window whose covered tiles hold no certified cargo can never pass
    the ``_support_metrics`` ladder, so ``refine_color_address_once``
    must refuse it WITHOUT paying the native RGB crop+filter — and the
    refusal summary must equal the sampled path's exactly.
    """
    spec = get_format_row(ROW)
    field, symbols = _compose_field(spec, (2, 3), 0xC0164)
    raster = _raster_from_field(field)
    # Window covers tile (0, 0) only; certificates exist only on (1, 2).
    patch = _patch(0, 0, (0, 0), (64, 64), (0.15, -0.2))
    address = AddressResult((patch,), (), (), ((0, "placed"),), 1)
    source = EvidenceSource(raster.source.sha256, LANE)
    certs = _certificates(spec, symbols, ((1, 2),))
    generation0 = collect_color_evidence(
        raster, source, address, spec, certificates=certs)
    assert len(generation0.windows) == 1

    # The sampled-path oracle: drive refine_color_window directly with a
    # real crop (the pre-fix behavior for this window).
    window_row = generation0.windows[0]
    pitch_px = float(patch.segment.segment.pose.pitch_px)
    oracle_crop = color_refine._window_crop(raster, patch, pitch_px, 1.0)
    oracle = color_refine.refine_color_window(
        oracle_crop, patch, window_row, spec,
        {(record.page, *record.tile_yx): (record,) for record in certs},
        color_refine.tiles.dependency_identity(tuple(sorted(
            record.certificate_id for record in certs))))
    assert oracle.metrics.reason == "insufficient_payload_train"

    # The gated path: the crop must never be taken.
    def _no_crop(*_args, **_kwargs):
        raise AssertionError("pre-gated window paid the crop")

    monkeypatch.setattr(color_refine, "_window_crop", _no_crop)
    refinement = refine_color_address_once(
        raster, address, generation0, spec, certs)

    assert refinement.eligible == 0
    assert refinement.adopted == 0
    gated = refinement.summaries[0]
    assert gated.metrics == oracle.metrics
    assert gated.dependency_certificate_ids \
        == oracle.dependency_certificate_ids == ()
    assert gated.frontier_id == oracle.frontier_id
    assert gated.refined is gated.baseline
