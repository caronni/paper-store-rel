"""Qualification pins for the clean E023c direct-native scale space."""
from __future__ import annotations

from fractions import Fraction
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023c-scale-space-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

from paperholo import pilotsearch  # noqa: E402
import scale_space  # noqa: E402


def _registered_integer_box(source: np.ndarray, factor: int) -> np.ndarray:
    image = source
    if image.ndim == 3:
        image = image[..., :3].mean(2)
    height, width = image.shape[:2]
    height -= height % factor
    width -= width % factor
    return (
        image[:height, :width].astype(np.float32)
        .reshape(height // factor, factor, width // factor, factor)
        .mean((1, 3)).round().clip(0, 255).astype(np.uint8)
    )


def _brute_area(source: np.ndarray, scale: Fraction) -> np.ndarray:
    """Slow exact-overlap reference, used only for tiny rational fixtures."""
    height = source.shape[0] * scale.denominator // scale.numerator
    width = source.shape[1] * scale.denominator // scale.numerator
    result = np.empty((height, width), np.uint8)
    for oy in range(height):
        y0, y1 = Fraction(oy) * scale, Fraction(oy + 1) * scale
        for ox in range(width):
            x0, x1 = Fraction(ox) * scale, Fraction(ox + 1) * scale
            total = Fraction(0)
            for sy in range(int(y0), int(np.ceil(float(y1)))):
                wy = max(Fraction(0), min(y1, sy + 1) - max(y0, sy))
                for sx in range(int(x0), int(np.ceil(float(x1)))):
                    wx = max(Fraction(0), min(x1, sx + 1) - max(x0, sx))
                    sample = source[sy, sx]
                    if source.ndim == 3:
                        value = Fraction(
                            sum(int(channel) for channel in sample[:3]), 3)
                    else:
                        value = Fraction(int(sample))
                    total += value * wy * wx
            result[oy, ox] = round(total / (scale * scale))
    return result


@pytest.mark.parametrize(
    ("cell_factor", "dpi", "expected"),
    [
        (2, 1200, (2, 4)),
        (3, 1200, (2, 3, 6)),
        (3, 4800, (2, 4, 8, 12, 24)),
        (3, 600, (2, 3)),
        (3, 400, (2,)),
        (2, 300, (1,)),
    ],
)
def test_auto_ppc_schedule(cell_factor, dpi, expected) -> None:
    assert scale_space.auto_ppc_levels(dpi, cell_factor) == tuple(
        Fraction(value) for value in expected)


def test_schedule_registers_exact_dpi_transforms_and_native_identity() -> None:
    schedule = scale_space.ScaleSchedule.auto(1200, 3)
    assert schedule.levels[-1].ppc == 6
    assert [level.dpi for level in schedule.levels] == [400, 600, 1200]
    assert [level.transform.source_per_output for level in schedule.levels] == [
        3, 2, 1]
    assert [level.is_native for level in schedule.levels] == [False, False, True]
    assert schedule.levels[-1].label == "l02-6ppc-1200dpi"


def test_schedule_uses_rational_floor_when_integer_box_is_impossible() -> None:
    schedule = scale_space.ScaleSchedule.auto(600, 3)
    assert [level.ppc for level in schedule.levels] == [2, 3]
    assert schedule.levels[0].transform.source_per_output == Fraction(3, 2)
    assert schedule.levels[0].dpi == 400


@pytest.mark.parametrize("factor", [1, 2, 3, 5])
@pytest.mark.parametrize("rgb", [False, True])
def test_integer_ratios_are_byte_identical_to_registered_e018_box(
    factor: int,
    rgb: bool,
) -> None:
    rng = np.random.default_rng(230_000 + factor + 100 * rgb)
    shape = (37, 43, 4) if rgb else (37, 43)
    source = rng.integers(0, 256, shape, dtype=np.uint8)
    expected = _registered_integer_box(source, factor)
    transform = scale_space.AreaPixelTransform(Fraction(factor))

    for rows, cols in ((1, 1), (3, 7), (128, 2048)):
        got = scale_space.area_decimate(
            source, transform, chunk_rows=rows, chunk_cols=cols)
        assert np.array_equal(got, expected)


@pytest.mark.parametrize(
    "scale",
    [Fraction(3, 2), Fraction(5, 2), Fraction(7, 3), Fraction(10, 7)],
)
def test_rational_area_matches_exact_overlap_reference(scale: Fraction) -> None:
    source = np.array(
        [[3, 40, 90, 17, 220, 61, 8, 131, 75],
         [201, 5, 33, 190, 12, 87, 149, 9, 250],
         [47, 99, 1, 72, 88, 200, 14, 166, 54],
         [8, 177, 60, 11, 143, 29, 230, 42, 100],
         [93, 2, 215, 64, 18, 155, 37, 80, 121],
         [51, 130, 7, 244, 76, 20, 111, 3, 197],
         [160, 25, 84, 6, 135, 49, 10, 222, 70]],
        np.uint8,
    )
    transform = scale_space.AreaPixelTransform(scale)
    expected = _brute_area(source, scale)
    assert np.array_equal(
        scale_space.area_decimate(
            source, transform, chunk_rows=1, chunk_cols=2),
        expected,
    )


def test_rational_exact_half_uses_round_to_even_for_every_chunking() -> None:
    # The first 10/7-by-10/7 footprint has exact weighted value 3/2.  A raw
    # separable float64 accumulation lands one ULP below that tie, so this
    # fixture pins the exact-overlap round-to-even contract explicitly.
    source = np.arange(8, dtype=np.uint8).reshape(2, 4)
    transform = scale_space.AreaPixelTransform(Fraction(10, 7))
    expected = _brute_area(source, transform.source_per_output)

    assert expected.tolist() == [[2, 3]]
    for rows, cols in ((1, 1), (1, 2), (8, 8)):
        got = scale_space.area_decimate(
            source, transform, chunk_rows=rows, chunk_cols=cols)
        assert np.array_equal(got, expected)


@pytest.mark.parametrize("rgb", [False, True])
def test_uint8_rational_area_exhaustive_tiny_random_against_exact_reference(
    rgb: bool,
) -> None:
    fractions = (
        Fraction(4, 3), Fraction(3, 2), Fraction(5, 3),
        Fraction(7, 4), Fraction(10, 7), Fraction(8, 3),
    )
    shapes = ((2, 3), (3, 4), (4, 5), (5, 7))
    for fraction_index, scale in enumerate(fractions):
        transform = scale_space.AreaPixelTransform(scale)
        for shape_index, (height, width) in enumerate(shapes):
            for seed in range(4):
                rng = np.random.default_rng(
                    230_200 + 1000 * rgb + 100 * fraction_index
                    + 10 * shape_index + seed)
                shape = ((height, width, 4) if rgb else (height, width))
                source = rng.integers(0, 256, shape, dtype=np.uint8)
                expected = _brute_area(source, scale)
                got = scale_space.area_decimate(
                    source, transform, chunk_rows=1, chunk_cols=2)
                assert np.array_equal(got, expected), (
                    rgb, scale, (height, width), seed, got, expected)


def test_exact_uint8_rational_path_refuses_int64_overflow() -> None:
    source = np.zeros((1, 1), np.uint8)
    maximum = np.iinfo(np.int64).max
    numerator = math.isqrt(maximum // 255) + 1
    with pytest.raises(OverflowError, match="int64"):
        scale_space._uint8_area_denominator(
            source, Fraction(numerator, numerator - 1))


def test_rational_result_is_chunk_invariant() -> None:
    rng = np.random.default_rng(230_100)
    source = rng.integers(0, 256, (59, 71), np.uint8)
    transform = scale_space.AreaPixelTransform(Fraction(8, 3))
    small = scale_space.area_decimate(
        source, transform, chunk_rows=1, chunk_cols=1)
    large = scale_space.area_decimate(
        source, transform, chunk_rows=100, chunk_cols=100)
    assert np.array_equal(small, large)


def test_identity_is_exact_and_does_not_alias_source() -> None:
    source = np.arange(13 * 17, dtype=np.uint8).reshape(13, 17)
    transform = scale_space.AreaPixelTransform(1)
    result = scale_space.area_decimate(
        source, transform, chunk_rows=4, chunk_cols=5)
    assert np.array_equal(result, source)
    assert result is not source
    result[0, 0] = 255
    assert source[0, 0] == 0


def test_area_decimate_into_writes_memmap_in_bounded_chunks(tmp_path: Path) -> None:
    rng = np.random.default_rng(230_101)
    source_path = tmp_path / "native.dat"
    source = np.memmap(source_path, mode="w+", dtype=np.uint8, shape=(47, 53))
    source[:] = rng.integers(0, 256, source.shape, np.uint8)
    transform = scale_space.AreaPixelTransform(Fraction(3, 2))
    shape = transform.output_shape(source.shape)
    target_path = tmp_path / "view.dat"
    target = np.memmap(target_path, mode="w+", dtype=np.uint8, shape=shape)

    returned = scale_space.area_decimate_into(
        source, transform, target, chunk_rows=2, chunk_cols=3)
    target.flush()
    assert returned is target
    assert np.array_equal(
        np.asarray(target),
        scale_space.area_decimate(
            np.asarray(source), transform, chunk_rows=100, chunk_cols=100),
    )


def test_derived_levels_are_all_direct_from_native() -> None:
    rng = np.random.default_rng(230_102)
    native = rng.integers(0, 256, (43, 51), np.uint8)
    schedule = scale_space.ScaleSchedule.auto(1200, 3)
    derived = list(scale_space.derive_scale_levels(
        native, schedule, chunk_rows=3, chunk_cols=5))
    assert len(derived) == 3
    for level, view in derived:
        assert np.array_equal(
            view,
            scale_space.area_decimate(native, level.transform),
        )
    assert np.array_equal(derived[-1][1], native)


def _pose() -> pilotsearch.AffinePose:
    return pilotsearch.AffinePose(
        origin_yx=(145.375, 902.625),
        jacobian_yx=((23.92, 0.71), (-0.63, 23.77)),
        angle_deg=-1.51,
        pitch_px=23.85,
        phase_yx=(0.625, 1.125),
        footing_factor=1,
    )


@pytest.mark.parametrize("scale", [Fraction(1), Fraction(3, 2), Fraction(3)])
def test_pixel_centres_and_affine_pose_transfer_are_exact(scale: Fraction) -> None:
    transform = scale_space.AreaPixelTransform(scale)
    view_points = np.array([[0.0, 0.0], [7.25, 9.5], [100.0, 200.0]])
    source_points = transform.view_to_source_points(view_points)
    assert np.allclose(
        source_points,
        (view_points + 0.5) * float(scale) - 0.5,
        rtol=0,
        atol=1e-14,
    )
    assert np.allclose(
        transform.source_to_view_points(source_points), view_points,
        rtol=0, atol=1e-13)

    source_pose = _pose()
    view_pose = transform.to_view_pose(source_pose)
    cells = np.array([[0.0, 0.0], [1.0, 2.0], [73.5, 41.25]])
    assert np.allclose(
        view_pose.points(cells),
        transform.source_to_view_points(source_pose.points(cells)),
        rtol=0,
        atol=1e-13,
    )
    restored = transform.from_view_pose(view_pose)
    assert np.allclose(restored.points(cells), source_pose.points(cells),
                       rtol=0, atol=2e-13)
    assert restored.angle_deg == source_pose.angle_deg
    assert restored.phase_yx == source_pose.phase_yx
    assert restored.footing_factor == source_pose.footing_factor


def test_native_pose_transfer_is_identity() -> None:
    pose = _pose()
    transform = scale_space.AreaPixelTransform(1)
    assert transform.to_view_pose(pose) == pose
    assert transform.from_view_pose(pose) == pose


@pytest.mark.parametrize("ratio", [0, -1, Fraction(2, 3), float("inf")])
def test_invalid_or_upsampling_transform_refuses(ratio) -> None:
    with pytest.raises(ValueError):
        scale_space.AreaPixelTransform(ratio)


def test_partial_source_edges_are_discarded() -> None:
    transform = scale_space.AreaPixelTransform(Fraction(3, 2))
    assert transform.output_shape((8, 11)) == (5, 7)
    source = np.arange(8 * 11, dtype=np.uint8).reshape(8, 11)
    result = scale_space.area_decimate(source, transform)
    assert result.shape == (5, 7)
