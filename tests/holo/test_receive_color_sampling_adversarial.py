"""Adversarial contracts for color sampling and certified refinement."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np
import pytest

from holo.core import channel
from holo.format import metadata
from holo.format.registry import get_format_row
from holo.gen.color_compose import compose_color_tile
from holo.receive import color_payload
from holo.receive.color_anchoring import RegistrationAnchors
from holo.receive.color_payload import (
    ColorCaptureEvidence,
    collect_color_evidence,
    color_blocks_from_frontier,
)
from holo.receive.color_registration import PlaneResidual
from holo.receive.evidence import TileCertificateRecord
from holo.receive.payload_model import EvidenceSource
from holo.receive.placement.model import (
    AddressResult,
    AffinePose,
    CandidateScore,
    PlacedPatch,
    PlacedSegment,
    PoseSegment,
    PoseWindow,
)
from holo.receive.records import certificate_record_from_user_bits
from holo.receive.scan import Raster, open_capture


_K_TOTAL = 1
_PLANTED_SHIFTS_YX = ((1, 2), (-2, 1), (1, -1))


@dataclass(frozen=True)
class _Fixture:
    spec: object
    states: np.ndarray
    raster: Raster
    address: AddressResult
    source: EvidenceSource
    symbols: dict[tuple[int, int], dict[str, np.ndarray]]


def _grid(shape: tuple[int, int]) -> np.ndarray:
    yy, xx = np.meshgrid(
        np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    return np.stack((yy, xx), axis=-1).reshape(-1, 2).astype(np.int32)


def _candidate() -> CandidateScore:
    return CandidateScore(
        0, (0, 0), 0, 0.0, 0.0, 0, 0,
        1000, 1000, 20.0, True, "color-adversarial-test")


def _fixture(
    row_id: str,
    tiles_yx: tuple[int, int],
    *,
    pixels_per_cell: int = 2,
    padding: int = 0,
    shifts_yx: tuple[tuple[int, int], ...] = ((0, 0),) * 3,
    collapse: bool = False,
) -> _Fixture:
    spec = get_format_row(row_id)
    rng = np.random.default_rng(0xC0102)
    height, width = tiles_yx[0] * 64, tiles_yx[1] * 64
    states = np.empty((height, width), np.uint8)
    symbols_by_tile: dict[
        tuple[int, int], dict[str, np.ndarray]
    ] = {}
    for ty in range(tiles_yx[0]):
        for tx in range(tiles_yx[1]):
            counter = spec.tile_counter(0, ty, tx)
            symbols = {
                stream.stream_id: rng.integers(
                    0, 2, stream.symbol_bits, dtype=np.uint8)
                for stream in spec.stream_profiles
            }
            symbols_by_tile[(ty, tx)] = symbols
            states[
                ty * 64:(ty + 1) * 64,
                tx * 64:(tx + 1) * 64,
            ] = compose_color_tile(
                spec, counter, symbols, k_total=_K_TOTAL)

    planes = channel.states_to_planes(states)
    reflected = np.repeat(
        np.repeat((1 - planes) * np.uint8(255),
                  pixels_per_cell, axis=0),
        pixels_per_cell, axis=1,
    )
    scan_height, scan_width = reflected.shape[:2]
    rgb = np.full(
        (scan_height + 2 * padding, scan_width + 2 * padding, 3),
        255, np.uint8,
    )
    for plane, (dy, dx) in enumerate(shifts_yx):
        y0 = padding + dy
        x0 = padding + dx
        rgb[y0:y0 + scan_height, x0:x0 + scan_width, plane] = (
            127 if collapse else reflected[..., plane]
        )
    raster = open_capture(rgb, 600.0)

    cells = _grid((height, width))
    center = padding + (pixels_per_cell - 1) / 2.0
    pose = AffinePose(
        (center, center),
        ((float(pixels_per_cell), 0.0),
         (0.0, float(pixels_per_cell))),
        (center, center),
        float(pixels_per_cell),
        0.0,
    )
    segment = PoseSegment(
        PoseWindow(0, 0, (0, 0), (height, width)),
        pose, cells.shape[0], 1.0,
        (float(pixels_per_cell), float(pixels_per_cell)), 0.0,
    )
    placed = PlacedSegment(segment, (0, 0), 0, cells)
    patch = PlacedPatch(
        0, 0, 0, "color-adversarial-test", _candidate(), (),
        placed, (), False, cells,
    )
    address = AddressResult(
        (patch,), (), (), ((0, "placed"),), 1)
    source = EvidenceSource(
        raster.source.sha256, f"ppc-{pixels_per_cell}")
    return _Fixture(
        spec, states, raster, address, source, symbols_by_tile)


def _certificates(
    fixture: _Fixture,
    tile_yx: tuple[int, int],
) -> dict[str, TileCertificateRecord]:
    spec = fixture.spec
    counter = spec.tile_counter(0, *tile_yx)
    bit = metadata.tile_bit(
        metadata.encode_metadata(0, _K_TOTAL), counter)
    return {
        profile.stream_id: certificate_record_from_user_bits(
            spec,
            page=0,
            tile_yx=tile_yx,
            stream_id=profile.stream_id,
            user_bits=np.concatenate((
                np.asarray([bit], np.uint8),
                fixture.symbols[tile_yx][profile.stream_id],
            )),
            origin_attempt_id=f"prior-{profile.stream_id}",
        )
        for profile in spec.stream_profiles
    }


def _assert_exact_payload_decisions(
    fixture: _Fixture,
    evidence: ColorCaptureEvidence,
) -> None:
    assert len(evidence.pages) == 1
    page = evidence.pages[0]
    expected_states = fixture.states[
        page.cells_yx[:, 0], page.cells_yx[:, 1]]
    if evidence.evidence_kind == "cmy7":
        scores = np.column_stack((
            np.zeros(page.evidence_values.shape[0]),
            page.evidence_values,
        ))
        assert np.array_equal(np.argmax(scores, axis=1), expected_states)
    else:
        expected_planes = channel.states_to_planes(expected_states)
        assert np.array_equal(
            page.evidence_values > 0.0, expected_planes.astype(bool))


def test_corrected_candidate_leaving_raster_falls_back_to_shared_pose(
    monkeypatch,
):
    fixture = _fixture(
        "c2-cmy7-p120-v0@3328x2304", (4, 4))
    outside = tuple(
        PlaneResidual((-8.0, -8.0), (0.0, 0.0), 20)
        for _ in range(3)
    )
    monkeypatch.setattr(
        color_payload, "_fit_registration",
        lambda _crop, _rows, _features, _spec: (
            outside,
            tuple(RegistrationAnchors.empty() for _ in range(3)),
        ),
    )

    evidence = collect_color_evidence(
        fixture.raster, fixture.source,
        fixture.address, fixture.spec,
    )

    assert evidence.regions[0].accepted
    assert not evidence.regions[0].registration_adopted
    assert evidence.regions[0].baseline_heldout_logloss == (
        evidence.regions[0].selected_heldout_logloss
    )
    # P8 (color-uplift): registration RAN and measured 20 anchors per
    # plane; the summary reports that measurement even though the
    # corrected arm lost.  Zeroing it here once made a live investigation
    # read real ~0.1-dot residuals as "registration never happened".
    assert evidence.regions[0].residuals == outside
    assert [residual.n_anchors
            for residual in evidence.regions[0].residuals] == [20, 20, 20]
    _assert_exact_payload_decisions(fixture, evidence)


@pytest.mark.parametrize(
    ("row_id", "tiles_yx"),
    (
        ("c2-cmy7-p120-v0@3328x2304", (4, 4)),
        ("c3-cmy8-p120-v0@2240x1536", (4, 7)),
    ),
)
def test_padded_per_plane_offsets_are_adopted_in_print_dot_units(
    row_id,
    tiles_yx,
    monkeypatch,
):
    fixture = _fixture(
        row_id,
        tiles_yx,
        pixels_per_cell=5,
        padding=16,
        shifts_yx=_PLANTED_SHIFTS_YX,
    )
    # P8 (color-uplift): record what registration measured, so the adopted
    # case pins measured == applied (the summary reports the very tuple the
    # corrected sampling consumed, not a re-derivation).
    fitted: list[tuple[PlaneResidual, ...]] = []
    anchor_fields: list[tuple[RegistrationAnchors, ...]] = []
    measure = color_payload._fit_registration

    def spy(*args: object):
        residuals, anchors = measure(*args)
        fitted.append(residuals)
        anchor_fields.append(anchors)
        return residuals, anchors

    monkeypatch.setattr(color_payload, "_fit_registration", spy)

    evidence = collect_color_evidence(
        fixture.raster, fixture.source,
        fixture.address, fixture.spec,
    )

    summary = evidence.regions[0]
    assert summary.accepted
    assert summary.registration_adopted
    assert len(fitted) == 1
    assert summary.residuals == fitted[0]
    # PK6 measure-first: the per-anchor field aligns with the fit it fed —
    # every plane's anchor count is at least the fit's inlier count, rows
    # are canonically ordered, and offsets stay in the bounded print-dot
    # domain.
    for residual, anchors in zip(
            fitted[0], anchor_fields[0], strict=True):
        n_rows = anchors.quality.shape[0]
        assert n_rows >= residual.n_anchors
        assert anchors.page.shape == (n_rows,)
        assert anchors.cell_yx.shape == (n_rows, 2)
        assert anchors.window_index.shape == (n_rows,)
        assert anchors.offset_dots_xy.shape == (n_rows, 2)
        assert anchors.bucket.shape == (n_rows,)
        keys = list(zip(
            anchors.page.tolist(),
            anchors.cell_yx[:, 0].tolist(),
            anchors.cell_yx[:, 1].tolist()))
        assert keys == sorted(keys)
        assert np.all(anchors.quality >= 0.10)
        assert np.all(np.isin(anchors.bucket, (0, 1, 2)))
    assert summary.selected_heldout_logloss < (
        summary.baseline_heldout_logloss
    )
    for residual, (dy, dx) in zip(
            summary.residuals, _PLANTED_SHIFTS_YX, strict=True):
        assert residual.supported
        # This fixture deliberately uses five scan pixels per cell and the
        # row uses five print dots per cell: native pixel and print-dot units
        # therefore coincide.  Binary-cell NCC need not estimate the literal
        # planted edge translation; it must recover a nonzero correction in
        # the right direction, expressed in the bounded print-dot domain.
        for observed, planted in zip(
                residual.intercept_xy, (dx, dy), strict=True):
            assert np.sign(observed) == np.sign(planted)
            assert 0.25 <= abs(observed) <= abs(planted) + 0.25
        assert residual.slope_xy == pytest.approx((0.0, 0.0), abs=0.05)
    _assert_exact_payload_decisions(fixture, evidence)


def test_collapsed_cmy7_photometry_refuses_region():
    fixture = _fixture(
        "c2-cmy7-p120-v0@3328x2304", (4, 4), collapse=True)

    evidence = collect_color_evidence(
        fixture.raster, fixture.source,
        fixture.address, fixture.spec,
    )

    assert evidence.windows == ()
    assert evidence.pages == ()
    assert len(evidence.regions) == 1
    assert not evidence.regions[0].accepted
    assert "collapsed color support" in evidence.regions[0].reason


def test_capture_rejects_nonreplayable_owner_provenance():
    fixture = _fixture(
        "c2-cmy7-p120-v0@3328x2304", (4, 4))
    evidence = collect_color_evidence(
        fixture.raster, fixture.source,
        fixture.address, fixture.spec,
    )
    page = evidence.pages[0]
    row_indices = np.asarray(page.window_row_indices).copy()
    row_indices[0] = row_indices[1]
    malformed = dataclasses.replace(
        page, window_row_indices=row_indices)

    with pytest.raises(ValueError, match="owner provenance is not replayable"):
        dataclasses.replace(evidence, pages=(malformed,))


@pytest.mark.parametrize(
    ("row_id", "tiles_yx", "selected_streams", "becomes_state_label"),
    (
        (
            "c2-cmy7-p120-v0@3328x2304",
            (4, 4),
            ("main",),
            True,
        ),
        (
            "c2-cmy8-p120-v0@3328x2304",
            (4, 7),
            ("C", "M", "Y"),
            True,
        ),
        (
            "c2-cmy8-p120-v0@3328x2304",
            (4, 7),
            ("C",),
            False,
        ),
    ),
)
def test_prior_certificate_labels_are_exact_partial_and_dependency_tracked(
    row_id,
    tiles_yx,
    selected_streams,
    becomes_state_label,
):
    fixture = _fixture(row_id, tiles_yx)
    baseline = collect_color_evidence(
        fixture.raster, fixture.source,
        fixture.address, fixture.spec,
    )
    records = _certificates(fixture, (0, 0))
    selected = tuple(records[stream] for stream in selected_streams)

    refined = collect_color_evidence(
        fixture.raster, fixture.source,
        fixture.address, fixture.spec,
        certificates=selected,
    )

    expected_dependencies = tuple(sorted(
        record.certificate_id for record in selected))
    if becomes_state_label:
        assert refined.regions[0].n_train > baseline.regions[0].n_train
        assert sum(refined.regions[0].class_counts) > sum(
            baseline.regions[0].class_counts)
    else:
        # One CMY8 component is an exact registration fact, not authority
        # to fabricate the other two components or a full state label.
        assert refined.regions[0].n_train == baseline.regions[0].n_train
        assert refined.regions[0].class_counts == (
            baseline.regions[0].class_counts)
    assert refined.regions[0].dependency_certificate_ids == (
        expected_dependencies)
    assert all(
        window.dependency_certificate_ids == expected_dependencies
        for window in refined.windows
    )
    blocks = color_blocks_from_frontier(refined)
    assert blocks
    assert all(
        origin.dependency_certificate_ids == expected_dependencies
        for block in blocks
        for origin in block.origins
    )


def test_fully_certified_region_is_pruned_before_color_sampling(
    monkeypatch,
):
    fixture = _fixture(
        "c2-cmy8-p120-v0@3328x2304", (1, 1))
    certificates = tuple(_certificates(
        fixture, (0, 0)).values())

    def forbidden_sampling(*_args, **_kwargs):
        raise AssertionError(
            "fully certified region reached RGB sampling")

    monkeypatch.setattr(
        color_payload, "window_raw_crops", forbidden_sampling)
    monkeypatch.setattr(
        type(fixture.raster), "crop_native", forbidden_sampling)
    progress = []

    evidence = collect_color_evidence(
        fixture.raster,
        fixture.source,
        fixture.address,
        fixture.spec,
        certificates=certificates,
        region_progress=progress.append,
    )

    assert evidence.windows == ()
    assert evidence.pages == ()
    assert progress == []
    assert len(evidence.regions) == 1
    assert evidence.regions[0].accepted
    assert evidence.regions[0].reason == "fully_certified_pruned"


def test_terminal_color_region_ignores_furniture_only_unresolved_reach(
    monkeypatch,
) -> None:
    fixture = _fixture(
        "c2-cmy8-p120-v0@3328x2304", (1, 2))
    patch = fixture.address.payload_placements[0]
    cells = np.asarray(patch.segment.audited_cells_yx)
    _states, furniture_kind = color_payload.color_reference_states(
        fixture.spec, 0, cells)
    selected = (
        (cells[:, 1] < 64)
        | ((cells[:, 1] >= 64) & (furniture_kind >= 0))
    )
    audited = cells[selected]
    placed = dataclasses.replace(
        patch.segment, audited_cells_yx=audited)
    selected_patch = dataclasses.replace(
        patch,
        segment=placed,
        page_cells_yx=audited,
    )
    address = dataclasses.replace(
        fixture.address,
        placements=(selected_patch,),
    )

    def forbidden_sampling(*_args, **_kwargs):
        raise AssertionError(
            "furniture-only unresolved reach triggered RGB sampling")

    monkeypatch.setattr(
        color_payload, "window_raw_crops", forbidden_sampling)
    monkeypatch.setattr(
        type(fixture.raster), "crop_native", forbidden_sampling)

    evidence = collect_color_evidence(
        fixture.raster,
        fixture.source,
        address,
        fixture.spec,
        certificates=tuple(_certificates(
            fixture, (0, 0)).values()),
    )

    assert evidence.windows == ()
    assert evidence.pages == ()
    assert [row.reason for row in evidence.regions] == [
        "fully_certified_pruned"]


def test_conflicting_stream_certificates_refuse_before_terminal_pruning(
    monkeypatch,
) -> None:
    fixture = _fixture(
        "c2-cmy8-p120-v0@3328x2304", (1, 1))
    records = _certificates(fixture, (0, 0))
    profile = next(
        row for row in fixture.spec.stream_profiles
        if row.stream_id == "C"
    )
    counter = fixture.spec.tile_counter(0, 0, 0)
    metadata_bit = metadata.tile_bit(
        metadata.encode_metadata(0, _K_TOTAL), counter)
    conflicting_bits = np.concatenate((
        np.asarray([metadata_bit], np.uint8),
        fixture.symbols[(0, 0)]["C"],
    )).copy()
    conflicting_bits[-1] ^= np.uint8(1)
    conflicting = certificate_record_from_user_bits(
        fixture.spec,
        page=0,
        tile_yx=(0, 0),
        stream_id=profile.stream_id,
        user_bits=conflicting_bits,
        origin_attempt_id="conflicting-C",
    )

    def forbidden_sampling(*_args, **_kwargs):
        raise AssertionError(
            "certificate conflict reached RGB sampling")

    monkeypatch.setattr(
        color_payload, "window_raw_crops", forbidden_sampling)

    with pytest.raises(
        ValueError,
        match="conflicting certificates for one tile stream",
    ):
        collect_color_evidence(
            fixture.raster,
            fixture.source,
            fixture.address,
            fixture.spec,
            certificates=(
                records["C"],
                conflicting,
                records["M"],
                records["Y"],
            ),
        )
