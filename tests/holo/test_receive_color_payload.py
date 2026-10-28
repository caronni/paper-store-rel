"""BCH-gated color sampling, detector fitting, and owner selection."""
from __future__ import annotations

import hashlib

import numpy as np
import pytest

from holo.core import channel
from holo.format import pilots
from holo.format.registry import get_format_row
from holo.gen.color_compose import compose_color_tile
from holo.receive import (
    color_anchoring,
    color_detect,
    color_fitting,
    color_payload,
)
from holo.receive.color_payload import (
    ColorCaptureEvidence,
    ColorOwnedPageEvidence,
    ColorWindowEvidence,
    collect_color_evidence,
    color_blocks_from_frontier,
    color_reference_states,
)
from holo.receive.evidence_blocks import (
    EvidenceOrigin,
    block_from_rows,
    tile_attempt_view,
)
from holo.receive.payload_model import EvidenceSource
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
from holo.receive.scan import open_capture


def _grid(shape: tuple[int, int]) -> np.ndarray:
    yy, xx = np.meshgrid(
        np.arange(shape[0]), np.arange(shape[1]), indexing="ij")
    return np.stack((yy, xx), axis=-1).reshape(-1, 2).astype(np.int32)


def _candidate() -> CandidateScore:
    return CandidateScore(
        0, (0, 0), 0, 0.0, 0.0, 0, 0,
        1000, 1000, 20.0, True, "color-test")


def _fixture(row_id: str, tiles_yx: tuple[int, int]):
    spec = get_format_row(row_id)
    rng = np.random.default_rng(0xC0102)
    height, width = tiles_yx[0] * 64, tiles_yx[1] * 64
    field = np.empty((height, width), np.uint8)
    for ty in range(tiles_yx[0]):
        for tx in range(tiles_yx[1]):
            counter = spec.tile_counter(0, ty, tx)
            symbols = {
                stream.stream_id: rng.integers(
                    0, 2, stream.symbol_bits, dtype=np.uint8)
                for stream in spec.stream_profiles
            }
            field[
                ty * 64:(ty + 1) * 64,
                tx * 64:(tx + 1) * 64,
            ] = compose_color_tile(spec, counter, symbols, 1)
    planes = channel.states_to_planes(field)
    rgb = np.repeat(
        np.repeat((1 - planes) * np.uint8(255), 2, axis=0),
        2, axis=1,
    )
    raster = open_capture(rgb, 600.0)
    cells = _grid((height, width))
    pose = AffinePose(
        (0.5, 0.5), ((2.0, 0.0), (0.0, 2.0)),
        (0.5, 0.5), 2.0, 0.0)
    segment = PoseSegment(
        PoseWindow(0, 0, (0, 0), (height, width)),
        pose, cells.shape[0], 1.0, (2.0, 2.0), 0.0)
    placed = PlacedSegment(segment, (0, 0), 0, cells)
    patch = PlacedPatch(
        0, 0, 0, "color-test", _candidate(), (),
        placed, (), False, cells)
    address = AddressResult(
        (patch,), (), (), ((0, "placed"),), 1)
    source = EvidenceSource(raster.source.sha256, "ppc-2")
    return spec, field, raster, patch, address, source


def _owned_expected(field, page):
    return field[page.cells_yx[:, 0], page.cells_yx[:, 1]]


def _detector_fit(detector=None):
    return color_fitting._DetectorFit(
        object(), detector, 0.0, 0.0, 0.0, 1, 1, (1,) * 7)


def test_owner_freeze_keeps_loss_then_patch_priority_and_original_lineage():
    spec = get_format_row("c2-cmy7-p120-v0@3328x2304")
    source = EvidenceSource("0" * 64, "lane")
    flat = np.sort(
        pilots.color_payload_cell_indices(spec.family_seed))[:4]
    cells = np.column_stack((flat // 64, flat % 64)).astype(np.int32)

    def window(
        patch_id: int,
        loss: float,
        selected: np.ndarray,
        values: tuple[float, float],
    ) -> ColorWindowEvidence:
        return ColorWindowEvidence(
            source=source,
            placement_id=f"placement-{patch_id}",
            patch_id=patch_id,
            region_id="region",
            page=0,
            page_cells_yx=selected,
            evidence_values=np.repeat(
                np.asarray(values, np.float32)[:, None], 6, axis=1),
            heldout_logloss=loss,
            evidence_kind=color_payload.COLOR_CMY7_KIND,
        )

    low_priority = window(0, 2.0, cells[:2], (10.0, 11.0))
    tie_later = window(2, 1.0, cells[2:], (30.0, 31.0))
    winner = window(1, 1.0, cells[1:3], (20.0, 21.0))
    windows = (low_priority, tie_later, winner)

    pages = color_payload._freeze(source, spec, windows)
    capture = ColorCaptureEvidence(
        source,
        spec.spec_id,
        color_payload.COLOR_CMY7_KIND,
        windows,
        pages,
        (),
    )
    page = capture.pages[0]

    assert np.array_equal(page.cells_yx, cells)
    assert np.array_equal(
        page.evidence_values[:, 0],
        np.asarray((10.0, 20.0, 21.0, 31.0), np.float32),
    )
    assert np.array_equal(
        page.window_indices, np.asarray((0, 2, 2, 1), np.int32))
    assert np.array_equal(
        page.window_row_indices, np.asarray((0, 0, 1, 1), np.int32))


def test_fully_certified_tiles_are_absent_from_emitted_color_frontier():
    spec = get_format_row("c2-cmy8-p120-v0@3328x2304")
    cells = np.asarray((
        (0, 0),
        (63, 63),
        (0, 64),
        (64, 0),
        (127, 127),
    ), np.int32)
    certified_codes = {
        0: np.asarray((
            0,
            spec.layout.tiles_yx[1] + 1,
        ), np.int64),
    }

    emitted = color_payload._emission_mask(
        spec, 0, cells, certified_codes)

    assert np.array_equal(
        emitted,
        np.asarray((False, False, True, True, False)),
    )


def test_capture_reports_the_actual_bad_owner_provenance_row() -> None:
    source = EvidenceSource("0" * 64, "lane")
    cells = np.asarray(((0, 0), (0, 1)), np.int32)
    values = np.zeros((2, 6), np.float32)
    window = ColorWindowEvidence(
        source, "placement", 0, "region", 0, cells, values, 0.0,
        color_payload.COLOR_CMY7_KIND,
    )
    page = ColorOwnedPageEvidence(
        0,
        cells,
        values,
        np.zeros(2, np.int32),
        np.asarray((0, 99), np.int32),
    )

    with pytest.raises(
        ValueError,
        match=r"owner provenance is not replayable at row 1$",
    ):
        ColorCaptureEvidence(
            source,
            "spec",
            color_payload.COLOR_CMY7_KIND,
            (window,),
            (page,),
            (),
        )


def test_vectorized_neighbor_rows_matches_sparse_coordinate_lookup():
    local = np.asarray((
        (2, 2),
        (0, 1),
        (1, 2),
        (1, 0),
        (0, 0),
        (2, 1),
    ), np.int32)
    lookup = {
        tuple(int(value) for value in cell): index
        for index, cell in enumerate(local)
    }
    expected = np.asarray([
        [
            lookup.get((int(cell[0] + dy), int(cell[1] + dx)), -1)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
        ]
        for cell in local
    ], np.int32)

    assert np.array_equal(color_anchoring._neighbor_rows(local), expected)
    assert color_anchoring._neighbor_rows(
        np.empty((0, 2), np.int32)).shape == (0, 9)


def test_cmy7_adapter_bounds_pathological_finite_scores_but_not_cmy8(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    maximum = np.finfo(np.float64).max
    raw = np.asarray((
        (-maximum, -21.0, -20.0, 0.0, 20.0, maximum),
        (19.5, -19.5, 1.0, -1.0, 20.5, -20.5),
    ))
    monkeypatch.setattr(
        color_detect,
        "cmy7_relative_scores",
        lambda _model, _features: raw,
    )

    limit = color_payload.CMY7_RELATIVE_SCORE_BOUND
    bounded = _detector_fit().evidence(np.zeros((2, 3), np.float64))
    divisor = np.maximum(
        1.0,
        np.max(np.abs(raw), axis=1, keepdims=True) / limit,
    )

    assert limit == 20.0
    assert np.array_equal(bounded, raw / divisor)
    assert np.max(np.abs(bounded)) <= limit
    assert np.array_equal(np.signbit(bounded), np.signbit(raw))
    assert all(
        np.array_equal(np.argsort(row), np.argsort(raw_row))
        for row, raw_row in zip(bounded, raw, strict=True)
    )
    assert f"cmy7linf{limit:g}" in color_payload.COLOR_PAYLOAD_POLICY_ID
    assert "pava-tiepool-classbal-planezero" in (
        color_payload.COLOR_PAYLOAD_POLICY_ID)
    assert "localcrop" in color_payload.COLOR_PAYLOAD_POLICY_ID
    assert "nonzero-floor" in color_payload.COLOR_PAYLOAD_POLICY_ID

    class FakeCMY8:
        def llrs(self, _features):
            return raw[:, :3]

    assert np.array_equal(
        _detector_fit(FakeCMY8()).evidence(
            np.zeros((2, 3), np.float64)),
        raw[:, :3],
    )


def test_cmy7_union_sums_only_bounded_per_capture_contributions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = {
        1: np.asarray((
            (100.0, -100.0, 75.0, -75.0, 50.0, -50.0),
        )),
        2: np.asarray((
            (200.0, -200.0, -150.0, 150.0, 100.0, -100.0),
        )),
    }
    monkeypatch.setattr(
        color_detect,
        "cmy7_relative_scores",
        lambda _model, features: raw[int(features[0, 0])],
    )
    fit = _detector_fit()
    origin = EvidenceOrigin("placement", 0, 0.0)

    blocks = tuple(
        block_from_rows(
            hashlib.sha256(f"capture-{capture}".encode()).hexdigest(),
            "ppc-2",
            0,
            (0, 0),
            [(0, fit.evidence(
                np.asarray(((capture, 0.0, 0.0),)))[0], origin)],
            kind="cmy7",
        )
        for capture in (1, 2)
    )
    view = tile_attempt_view(blocks)
    limit = color_payload.CMY7_RELATIVE_SCORE_BOUND

    assert all(
        np.max(np.abs(block.printed_llr())) <= limit
        for block in blocks
    )
    assert np.array_equal(
        view.llr_cells_f64[0, 0],
        np.asarray((40.0, -40.0, 0.0, 0.0, 20.0, -20.0)),
    )
    assert np.max(np.abs(view.llr_cells_f64)) <= len(blocks) * limit


def test_color_reference_uses_word_and_dust_and_leaves_payload_unknown():
    spec, field, _raster, _patch, _address, _source = _fixture(
        "c2-cmy7-p120-v0@3328x2304", (1, 1))
    cells = _grid((64, 64))
    states, kinds = color_reference_states(spec, 0, cells)
    assert np.count_nonzero(kinds == 0) == 100
    assert np.count_nonzero(kinds == 1) == 20
    assert np.count_nonzero(kinds == -1) == 3976
    known = kinds >= 0
    assert np.array_equal(states[known], field.ravel()[known])
    assert np.all(states[~known] == -1)


@pytest.mark.parametrize(
    "row_id",
    (
        "c2-cmy7-p120-v0@3328x2304",
        "c3-cmy7-p120-v0@2240x1536",
    ),
)
def test_clean_cmy7_region_emits_joint_scores_and_exact_state_decisions(
    row_id: str,
):
    spec, field, raster, _patch, address, source = _fixture(
        row_id, (4, 4))
    evidence = collect_color_evidence(
        raster, source, address, spec)

    assert evidence.evidence_kind == "cmy7"
    assert len(evidence.windows) == 1
    assert len(evidence.pages) == 1
    assert evidence.regions[0].accepted
    page = evidence.pages[0]
    expected = _owned_expected(field, page)
    scores = np.column_stack((
        np.zeros(page.evidence_values.shape[0]),
        page.evidence_values,
    ))
    assert np.array_equal(np.argmax(scores, axis=1), expected)
    assert page.cells_yx.shape[0] == 16 * 3976
    blocks = color_blocks_from_frontier(evidence)
    assert len(blocks) == 16
    assert all(block.kind == "cmy7" and block.arity == 6
               for block in blocks)


@pytest.mark.parametrize(
    "row_id",
    (
        "c2-cmy8-p120-v0@3328x2304",
        "c3-cmy8-p120-v0@2240x1536",
    ),
)
def test_clean_cmy8_region_emits_three_calibrated_plane_llrs(
    row_id: str,
):
    spec, field, raster, _patch, address, source = _fixture(
        row_id, (4, 7))
    evidence = collect_color_evidence(
        raster, source, address, spec)

    assert evidence.evidence_kind == "cmy8"
    assert len(evidence.windows) == 1
    assert len(evidence.pages) == 1
    summary = evidence.regions[0]
    assert summary.accepted
    assert summary.n_train > 300
    assert all(value > 0 for value in summary.class_counts)
    page = evidence.pages[0]
    expected = channel.states_to_planes(_owned_expected(field, page))
    assert np.array_equal(page.evidence_values > 0.0, expected.astype(bool))
    assert page.cells_yx.shape[0] == 28 * 3976
    blocks = color_blocks_from_frontier(evidence)
    view = tile_attempt_view((blocks[0],))
    assert view.kind == "cmy8"
    assert view.llr_cells_f64.shape == (64, 64, 3)


def test_cmy8_region_can_emit_first_order_evidence_below_300_dust_labels():
    spec, field, raster, _patch, address, source = _fixture(
        "c2-cmy8-p120-v0@3328x2304", (2, 3))

    evidence = collect_color_evidence(
        raster, source, address, spec)

    summary = evidence.regions[0]
    assert summary.accepted
    assert 0 < summary.calibration_labels < 300
    assert summary.component_supported == (True, True, True)
    assert summary.component_support_reasons == (None, None, None)
    page = evidence.pages[0]
    expected = channel.states_to_planes(_owned_expected(field, page))
    assert np.array_equal(
        page.evidence_values > 0.0, expected.astype(bool))


@pytest.mark.parametrize(
    "row_id",
    (
        "c2-cmy8-p120-v0@3328x2304",
        "c3-cmy8-p120-v0@2240x1536",
    ),
)
def test_one_tile_cmy8_word_and_dust_start_first_order_payload(
    row_id: str,
) -> None:
    spec, field, raster, _patch, address, source = _fixture(
        row_id, (1, 1))

    evidence = collect_color_evidence(
        raster, source, address, spec)

    assert len(evidence.regions) == 1
    summary = evidence.regions[0]
    assert summary.accepted
    assert summary.calibration_labels == 20
    assert summary.component_supported == (True, True, True)
    page = evidence.pages[0]
    expected = channel.states_to_planes(_owned_expected(field, page))
    assert np.array_equal(
        page.evidence_values > 0.0, expected.astype(bool))


def test_constant_rgb_cmy8_region_emits_exactly_neutral_evidence() -> None:
    spec, _field, raster, _patch, address, _source = _fixture(
        "c2-cmy8-p120-v0@3328x2304", (4, 7))
    height, width = raster.shape
    constant = open_capture(
        np.full((height, width, 3), 127, dtype=np.uint8), 600.0)
    source = EvidenceSource(constant.source.sha256, "ppc-2")

    evidence = collect_color_evidence(
        constant, source, address, spec)

    assert len(evidence.regions) == 1
    assert evidence.regions[0].accepted
    assert len(evidence.pages) == 1
    np.testing.assert_array_equal(
        evidence.pages[0].evidence_values,
        np.zeros_like(evidence.pages[0].evidence_values),
    )
    blocks = color_blocks_from_frontier(evidence)
    assert blocks
    assert all(np.count_nonzero(block.printed_llr()) == 0
               for block in blocks)


@pytest.mark.parametrize(
    ("row_id", "tiles_yx"),
    (
        ("c2-cmy7-p120-v0@3328x2304", (4, 4)),
        ("c2-cmy8-p120-v0@3328x2304", (4, 7)),
    ),
)
def test_color_evidence_is_invariant_to_equivalent_u8_and_u16_rgb_scales(
    row_id: str,
    tiles_yx: tuple[int, int],
) -> None:
    spec, _field, raster8, _patch, address, source8 = _fixture(
        row_id, tiles_yx)
    height, width = raster8.shape
    rgb8 = raster8.crop_native(0, height, 0, width)
    raster16 = open_capture(
        rgb8.astype(np.uint16) * np.uint16(257), 600.0)
    source16 = EvidenceSource(raster16.source.sha256, "ppc-2")

    evidence8 = collect_color_evidence(
        raster8, source8, address, spec)
    evidence16 = collect_color_evidence(
        raster16, source16, address, spec)

    assert evidence8.evidence_kind == evidence16.evidence_kind
    assert len(evidence8.pages) == len(evidence16.pages) == 1
    assert np.array_equal(
        evidence8.pages[0].cells_yx,
        evidence16.pages[0].cells_yx,
    )
    np.testing.assert_allclose(
        evidence8.pages[0].evidence_values,
        evidence16.pages[0].evidence_values,
        rtol=1e-10,
        atol=1e-10,
    )


def test_registration_anchor_cap_is_per_kind_even_and_replay_stable():
    n_candidates = 1025

    def buckets(
        reverse: bool,
    ) -> dict[int, dict[tuple[int, int, int], tuple[int, int]]]:
        order = (
            range(n_candidates - 1, -1, -1)
            if reverse
            else range(n_candidates)
        )
        return {
            kind: {
                (0, index, kind): (kind, index)
                for index in order
            }
            for kind in (0, 1, 2)
        }

    forward = color_anchoring._select_registration_candidates(
        buckets(False))
    reverse = color_anchoring._select_registration_candidates(
        buckets(True))

    assert forward == reverse
    budget = color_anchoring._ANCHOR_BUDGET_PER_KIND
    assert budget == 512
    assert "anchor512-binleft" in color_payload.COLOR_PAYLOAD_POLICY_ID
    assert len(forward) == 3 * budget
    expected_indices = (
        np.arange(budget, dtype=np.int64)
        * n_candidates
        // budget
    )
    for kind in (0, 1, 2):
        selected = forward[kind * budget:(kind + 1) * budget]
        assert [key for key, _window, _row, _bucket in selected] == [
            (0, int(index), kind) for index in expected_indices
        ]
        assert [(_window, _row)
                for _key, _window, _row, _bucket in selected] == [
            (kind, int(index)) for index in expected_indices
        ]
        assert all(
            bucket == kind for _key, _window, _row, bucket in selected)


def test_bch_conflict_quarantines_the_only_color_placement():
    spec, _field, raster, patch, _address, source = _fixture(
        "c2-cmy7-p120-v0@3328x2304", (1, 1))
    conflict = KnownWord(
        page=0, tile_yx=(0, 0), expected_counter=0,
        decoded_counter=1, errors=0, erasures=0,
        contributor_patch_ids=(patch.patch_id,))
    address = AddressResult(
        (patch,), (), (conflict,), ((0, "placed"),), 1)
    evidence = collect_color_evidence(
        raster, source, address, spec)
    assert evidence.windows == ()
    assert evidence.pages == ()
    assert evidence.regions == ()


def test_greyscale_color_lane_can_address_but_emits_no_color_evidence():
    spec, _field, raster, _patch, address, source = _fixture(
        "c2-cmy7-p120-v0@3328x2304", (1, 1))
    height, width = raster.shape
    grey = raster.crop_luma(0, height, 0, width)
    grey_raster = open_capture(grey, 600.0)
    grey_source = EvidenceSource(grey_raster.source.sha256, "ppc-2")
    evidence = collect_color_evidence(
        grey_raster, grey_source, address, spec)
    assert evidence.windows == ()
    assert evidence.pages == ()
