"""Hard work-set bounds for K and color payload sampling."""
from __future__ import annotations

from dataclasses import replace
import hashlib

import numpy as np
import pytest
from scipy import ndimage

from holo.devices.profiles import make_spec
from holo.receive import (
    _payload_sampling,
    color_anchoring,
    color_payload,
    color_sampling,
)
from holo.receive.color_registration import PlaneResidual
from holo.receive.payload_model import EvidenceSource, PlacementModelError
from holo.receive.placement.model import (
    AddressResult,
    AffinePose,
    CandidateScore,
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


def _patch(
    patch_id: int,
    scan_origin_yx: tuple[int, int],
    page_origin_yx: tuple[int, int],
    *,
    shape_yx: tuple[int, int] = (64, 64),
    pitch: float = 2.0,
) -> PlacedPatch:
    local = _grid(shape_yx)
    sy, sx = scan_origin_yx
    py, px = page_origin_yx
    pose = AffinePose(
        (sy + 0.5, sx + 0.5),
        ((pitch, 0.0), (0.0, pitch)),
        (0.5, 0.5),
        pitch,
        0.0,
    )
    window = PoseWindow(
        patch_id, 0, scan_origin_yx, shape_yx,
        support_estimate=local.shape[0])
    segment = PoseSegment(
        window, pose, local.shape[0], 1.0, (pitch, pitch), 0.0)
    placed = PlacedSegment(segment, page_origin_yx, 0, local)
    page_cells = local + np.asarray((py, px), np.int32)
    candidate = CandidateScore(
        0, page_origin_yx, 0, 0.0, 0.0, 0, 0,
        1000, 1000, 20.0, True, "bounded-sampling-test")
    return PlacedPatch(
        patch_id, 0, 0, "bounded-sampling-test", candidate, (),
        placed, (), False, page_cells)


class _CropSpy:
    def __init__(self, shape: tuple[int, int]) -> None:
        self.shape = shape
        self.luma_boxes: list[tuple[int, int, int, int]] = []
        self.rgb_boxes: list[tuple[int, int, int, int]] = []

    @staticmethod
    def _base(r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
        yy = np.arange(r0, r1, dtype=np.int64)[:, None]
        xx = np.arange(c0, c1, dtype=np.int64)[None, :]
        return ((17 * yy + 29 * xx) & 255).astype(np.uint8)

    def crop_luma(
        self, r0: int, r1: int, c0: int, c1: int
    ) -> np.ndarray:
        self.luma_boxes.append((r0, r1, c0, c1))
        return self._base(r0, r1, c0, c1).astype(np.float32)

    def crop_native(
        self, r0: int, r1: int, c0: int, c1: int
    ) -> np.ndarray:
        self.rgb_boxes.append((r0, r1, c0, c1))
        base = self._base(r0, r1, c0, c1)
        return np.stack(
            (base, base ^ np.uint8(0x55), base ^ np.uint8(0xAA)),
            axis=2,
        )


def _max_extent(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int]:
    return (
        max(r1 - r0 for r0, r1, _c0, _c1 in boxes),
        max(c1 - c0 for _r0, _r1, c0, c1 in boxes),
    )


def test_k_sampling_never_spans_far_apart_windows() -> None:
    spec = make_spec("c3-r0550")
    patches = (
        _patch(0, (20, 20), (0, 0)),
        _patch(1, (20, 100_020), (0, 64)),
    )
    raster = _CropSpy((512, 100_512))
    address = AddressResult(
        patches, (), (), ((0, "placed"),), 2)
    source = EvidenceSource(
        hashlib.sha256(b"bounded-k").hexdigest(), "native")

    windows = _payload_sampling.sample_and_calibrate(
        raster, source, address, spec)

    assert len(windows) == 2
    assert len(raster.luma_boxes) == 2
    assert _max_extent(raster.luma_boxes) <= (160, 160)
    assert all(c1 - c0 < 1000 for _r0, _r1, c0, c1 in raster.luma_boxes)


def test_window_rows_preserve_authoritative_lineage_order() -> None:
    spec = make_spec("c3-r0550")
    original = _patch(
        0, (20, 30), (64, 128), shape_yx=(7, 9), pitch=2.0)
    local = original.segment.audited_cells_yx
    rot_k = 1
    mapped = _payload_sampling.rotated_points(local, (7, 9), rot_k)
    mapped += np.asarray(original.segment.page_origin_yx, np.int32)
    order = np.random.default_rng(23023).permutation(local.shape[0])
    placed = replace(original.segment, rot_k=rot_k)
    patch = replace(
        original,
        candidate=replace(original.candidate, rot_k=rot_k),
        segment=placed,
        page_cells_yx=mapped[order],
    )

    rows = _payload_sampling._window_rows(patch, spec)

    assert np.array_equal(rows.page_cells_yx, mapped[order])
    assert np.array_equal(rows.local_cells_yx, local[order])
    assert np.array_equal(
        rows.scan_points_yx,
        placed.segment.pose.points(local[order].astype(np.float64)),
    )


def test_window_rows_reports_out_of_page_linear_alias_as_one_for_one() -> None:
    spec = make_spec("c3-r0550")
    patch = _patch(0, (20, 20), (0, 0))
    cells = np.asarray(patch.page_cells_yx).copy()
    cells[0] = (-1, spec.layout.cells_yx[1])

    with pytest.raises(
        PlacementModelError,
        match=r"window cell mismatch \(missing=1, extra=1\)",
    ):
        _payload_sampling._window_rows(
            replace(patch, page_cells_yx=cells), spec)


def test_color_sampling_never_spans_far_apart_windows(
    monkeypatch,
) -> None:
    spec = make_spec("c3-cmy7-p120-v0")
    patches = (
        _patch(0, (20, 20), (0, 0)),
        _patch(1, (20, 100_020), (0, 64)),
    )
    raster = _CropSpy((512, 100_512))
    address = AddressResult(
        patches, (), (), ((0, "placed"),), 2)
    source = EvidenceSource(
        hashlib.sha256(b"bounded-color").hexdigest(), "native")
    zero = (
        tuple(
            PlaneResidual((0.0, 0.0), (0.0, 0.0), 0)
            for _ in range(3)),
        tuple(
            color_anchoring.RegistrationAnchors.empty()
            for _ in range(3)),
    )
    monkeypatch.setattr(
        color_payload, "_fit_registration",
        lambda _raster, _rows, _features, _spec: zero)

    color_payload.collect_color_evidence(
        raster, source, address, spec)

    # Ignore the one-pixel RGB capability probe.
    boxes = [box for box in raster.rgb_boxes
             if box[1] - box[0] > 1 or box[3] - box[2] > 1]
    # Phase-3 crop hoist (color-upstream:07): the divisor probe and the
    # base features share ONE native read per window; corrected sampling
    # keeps its own footprint read.
    assert len(boxes) == 4  # shared probe/base + corrected: twice each
    assert _max_extent(boxes) <= (160, 160)
    assert all(c1 - c0 < 1000 for _r0, _r1, c0, c1 in boxes)


def test_corrected_sampling_crops_at_the_corrected_footprint() -> None:
    spec = make_spec("c3-cmy7-p120-v0")
    patch = _patch(0, (20, 20), (0, 0))
    aligned = _payload_sampling._window_rows(patch, spec)
    n_rows = aligned.page_cells_yx.shape[0]
    rows = color_anchoring._Rows(
        patch,
        aligned.local_cells_yx,
        aligned.page_cells_yx,
        aligned.scan_points_yx,
        np.full(n_rows, -1, np.int8),
        np.full(n_rows, -1, np.int8),
        np.zeros((n_rows, 3), np.uint8),
        np.zeros((n_rows, 3), bool),
        color_anchoring._neighbor_rows(aligned.local_cells_yx),
        (),
    )
    raster = _CropSpy((512, 100_512))
    # At pitch 2 and c3, 75,000 print dots move samples by 50,000 pixels.
    shifted = tuple(
        PlaneResidual((75_000.0, 0.0), (0.0, 0.0), 20)
        for _ in range(3))

    features = color_anchoring._features_with_page_fraction(
        raster, rows, shifted, spec, 2.0, 255.0)

    assert features is not None
    assert len(raster.rgb_boxes) == 1
    _r0, _r1, c0, c1 = raster.rgb_boxes[0]
    assert c0 > 49_000
    assert c1 - c0 < 200


def test_local_k_window_is_numerically_identical_to_region_reference() -> None:
    rng = np.random.default_rng(23023)
    image = rng.normal(127.0, 30.0, (180, 200)).astype(np.float32)
    raster = open_capture(image, 1200.0)
    patch = _patch(
        0, (17, 23), (0, 0), shape_yx=(16, 18), pitch=4.0)
    rows = _payload_sampling._window_rows(
        patch, make_spec("c3-r0550"))

    got_crop = _payload_sampling._window_crop(raster, patch, 4.0)
    got = _payload_sampling._sample_rows(got_crop, rows, raster.shape)

    points = patch.segment.segment.pose.points(np.asarray(
        ((0, 0), (0, 18), (16, 0), (16, 18)), np.float64))
    halo = int(np.ceil(_payload_sampling.APERTURE_CELLS * 4.0)) + 2
    y0 = max(0, int(np.floor(points[:, 0].min())) - halo)
    x0 = max(0, int(np.floor(points[:, 1].min())) - halo)
    y1 = min(raster.shape[0], int(np.ceil(points[:, 0].max())) + halo)
    x1 = min(raster.shape[1], int(np.ceil(points[:, 1].max())) + halo)
    raw = np.asarray(raster.crop_luma(y0, y1, x0, x1), np.float32)
    reference = ndimage.uniform_filter(
        raw, size=3, mode="nearest")
    local = rows.scan_points_yx - np.asarray((y0, x0), np.float64)
    expected = ndimage.map_coordinates(
        reference, local.T, order=1, cval=float(np.median(raw)))

    assert (got_crop.y0, got_crop.x0) == (y0, x0)
    assert np.array_equal(got_crop.filtered, reference)
    assert np.array_equal(got, expected.astype(np.float32))


def test_local_color_window_is_numerically_identical_to_region_reference(
) -> None:
    rng = np.random.default_rng(0xC0102)
    image = rng.integers(0, 256, (180, 200, 3), dtype=np.uint8)
    raster = open_capture(image, 1200.0)
    patch = _patch(
        0, (17, 23), (0, 0), shape_yx=(16, 18), pitch=4.0)
    rows = _payload_sampling._window_rows(
        patch, make_spec("c3-cmy7-p120-v0"))

    got_crop = color_sampling.window_crop(
        raster, patch, 4.0, 255.0)
    got = color_sampling.sample(
        got_crop.filtered, got_crop, rows.scan_points_yx)

    points = patch.segment.segment.pose.points(np.asarray(
        ((-2, -2), (-2, 20), (18, -2), (18, 20)), np.float64))
    halo = int(np.ceil(1.5 * 4.0)) + 3
    y0 = max(0, int(np.floor(points[:, 0].min())) - halo)
    x0 = max(0, int(np.floor(points[:, 1].min())) - halo)
    y1 = min(raster.shape[0], int(np.ceil(points[:, 0].max())) + halo)
    x1 = min(raster.shape[1], int(np.ceil(points[:, 1].max())) + halo)
    raw = np.asarray(raster.crop_native(y0, y1, x0, x1))
    filtered = np.empty(raw.shape, np.float32)
    for plane in range(3):
        ndimage.uniform_filter(
            raw[..., plane], size=3, output=filtered[..., plane],
            mode="nearest")
    filtered /= np.float32(255.0)
    local = rows.scan_points_yx - np.asarray((y0, x0), np.float64)
    expected = np.stack(tuple(
        ndimage.map_coordinates(
            filtered[..., plane], local.T, order=1, mode="nearest",
            output=np.float64)
        for plane in range(3)
    ), axis=1)

    assert (got_crop.y0, got_crop.x0) == (y0, x0)
    assert np.array_equal(got_crop.rgb, raw)
    assert np.array_equal(got_crop.filtered, filtered)
    assert np.array_equal(got, expected)
