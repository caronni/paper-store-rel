from __future__ import annotations

import itertools

import numpy as np
import pytest

from holo.core import channel
from holo.format.registry import get_format_row
from holo.gen.color_compose import (
    color_cells_to_dot_planes,
    compose_color_tile,
)
from holo.qualification.color_synthetic import (
    M281_S14_BAR_MIX,
    ColorChannelParameters,
    PlaneParameters,
    area_decimate,
    cmy_channel_parameters,
    render_color_scan,
)


def _translation(x: float, y: float) -> tuple[tuple[float, ...], ...]:
    return (
        (1.0, 0.0, x),
        (0.0, 1.0, y),
        (0.0, 0.0, 1.0),
    )


def test_clean_canonical_cmy_states_have_exact_ideal_rgb() -> None:
    states = np.asarray(
        tuple(itertools.product((0.0, 1.0), repeat=3)),
        dtype=np.float64,
    ).reshape(2, 4, 3)

    scan = render_color_scan(states)

    np.testing.assert_array_equal(scan.rgb, 1.0 - states)
    np.testing.assert_array_equal(scan.truth.sampled_cmy, states)
    np.testing.assert_array_equal(scan.truth.effective_cmy, states)
    assert np.all(scan.truth.support_masks)
    assert np.all(scan.truth.active_masks)
    assert not np.any(scan.truth.clipped_rgb_mask)
    np.testing.assert_array_equal(
        scan.truth.canvas_forward_affines_xy,
        np.repeat(np.eye(3)[np.newaxis, ...], 3, axis=0),
    )


def test_shared_affine_and_plane_residuals_remain_separate_truth() -> None:
    source = np.zeros((7, 9, 3), dtype=np.float64)
    source[1, 3, 0] = 1.0
    source[5, 3, 0] = 1.0
    source[3, 3, 1] = 1.0
    source[3, 3, 2] = 1.0
    parameters = ColorChannelParameters(
        shared_affine_xy=_translation(2.0, 1.0),
        planes=(
            PlaneParameters(y_drift_xy=(0.5, 0.0)),
            PlaneParameters(offset_xy=(1.0, -1.0)),
            PlaneParameters(),
        ),
        output_shape=(9, 10),
    )

    truth = render_color_scan(source, parameters).truth

    np.testing.assert_array_equal(
        truth.shared_affine_xy, np.asarray(_translation(2.0, 1.0)))
    assert truth.sampled_cmy[2, 4, 0] == 1.0
    assert truth.sampled_cmy[6, 6, 0] == 1.0
    assert truth.sampled_cmy[3, 6, 1] == 1.0
    assert truth.sampled_cmy[4, 5, 2] == 1.0
    assert np.count_nonzero(truth.sampled_cmy[..., 0]) == 2
    assert np.count_nonzero(truth.sampled_cmy[..., 1]) == 1
    assert np.count_nonzero(truth.sampled_cmy[..., 2]) == 1
    np.testing.assert_allclose(
        truth.canvas_forward_affines_xy[0],
        ((1.0, 0.5, 0.5), (0.0, 1.0, 1.0), (0.0, 0.0, 1.0)),
    )
    np.testing.assert_allclose(
        truth.canvas_forward_affines_xy[1],
        ((1.0, 0.0, 3.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    )


def test_seeded_noise_is_repeatable_but_rescans_are_independent() -> None:
    source = np.zeros((8, 7, 3), dtype=np.float64)

    def scan(seed: int):
        return render_color_scan(
            source,
            ColorChannelParameters(
                paper_rgb=(0.5, 0.5, 0.5),
                noise_std_rgb=(0.01, 0.02, 0.03),
                seed=seed,
            ),
        )

    first = scan(41)
    replay = scan(41)
    rescan = scan(42)

    np.testing.assert_array_equal(first.rgb, replay.rgb)
    np.testing.assert_array_equal(
        first.truth.additive_noise_rgb, replay.truth.additive_noise_rgb)
    np.testing.assert_array_equal(first.truth.clean_rgb, rescan.truth.clean_rgb)
    assert not np.array_equal(first.rgb, rescan.rgb)
    assert not np.array_equal(
        first.truth.additive_noise_rgb, rescan.truth.additive_noise_rgb)


def test_weak_toned_plane_and_absent_plane_are_explicit() -> None:
    source = np.ones((3, 4, 3), dtype=np.float64)
    parameters = ColorChannelParameters(
        planes=(
            PlaneParameters(contrast=0.5, gamma=2.0),
            PlaneParameters(dropped=True),
            PlaneParameters(),
        ),
    )

    scan = render_color_scan(source, parameters)

    np.testing.assert_allclose(scan.truth.effective_cmy[..., 0], 0.25)
    np.testing.assert_array_equal(scan.truth.effective_cmy[..., 1], 0.0)
    np.testing.assert_array_equal(scan.truth.effective_cmy[..., 2], 1.0)
    expected_rgb = np.empty_like(scan.rgb)
    expected_rgb[...] = (0.75, 1.0, 0.0)
    np.testing.assert_allclose(scan.rgb, expected_rgb)
    assert np.all(scan.truth.support_masks)
    assert np.all(scan.truth.active_masks[..., 0])
    assert not np.any(scan.truth.active_masks[..., 1])
    assert np.all(scan.truth.active_masks[..., 2])


def test_blur_and_subtractive_crosstalk_are_explicit_per_plane() -> None:
    source = np.zeros((9, 9, 3), dtype=np.float64)
    source[4, 4] = (1.0, 0.5, 0.25)
    mixing = (
        (0.8, 0.1, 0.2),
        (0.2, 0.9, 0.1),
        (0.1, 0.2, 0.7),
    )
    parameters = ColorChannelParameters(
        planes=(
            PlaneParameters(blur_sigma=0.8),
            PlaneParameters(),
            PlaneParameters(),
        ),
        subtractive_rgb=mixing,
        paper_rgb=(0.95, 0.9, 0.85),
    )

    scan = render_color_scan(source, parameters)
    truth = scan.truth

    assert 0.0 < truth.blurred_cmy[4, 4, 0] < 1.0
    assert truth.blurred_cmy[4, 5, 0] > 0.0
    assert truth.blurred_cmy[4, 4, 1] == 0.5
    assert truth.blurred_cmy[4, 5, 1] == 0.0
    expected_center = np.clip(
        np.asarray(parameters.paper_rgb)
        - np.asarray(mixing) @ truth.effective_cmy[4, 4],
        0.0,
        1.0,
    )
    np.testing.assert_allclose(scan.rgb[4, 4], expected_center)
    np.testing.assert_array_equal(truth.subtractive_rgb, mixing)
    np.testing.assert_array_equal(truth.plane_blur_sigma, (0.8, 0.0, 0.0))
    np.testing.assert_array_equal(truth.paper_rgb, parameters.paper_rgb)


def test_crop_is_exact_and_preserves_geometry_masks() -> None:
    source = np.zeros((4, 5, 3), dtype=np.float64)
    source[..., 0] = 1.0
    full_parameters = ColorChannelParameters(
        shared_affine_xy=_translation(2.0, 1.0),
        output_shape=(6, 8),
    )
    cropped_parameters = ColorChannelParameters(
        shared_affine_xy=_translation(2.0, 1.0),
        output_shape=(6, 8),
        crop_yxhw=(1, 1, 4, 5),
    )

    full = render_color_scan(source, full_parameters)
    cropped = render_color_scan(source, cropped_parameters)

    np.testing.assert_array_equal(cropped.rgb, full.rgb[1:5, 1:6])
    assert cropped.rgb.shape == (4, 5, 3)
    expected_support = np.zeros((4, 5), dtype=np.bool_)
    expected_support[:, 1:] = True
    for channel in range(3):
        np.testing.assert_array_equal(
            cropped.truth.support_masks[..., channel], expected_support)
    np.testing.assert_array_equal(
        cropped.truth.output_forward_affines_xy[0],
        ((1.0, 0.0, 1.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    )
    np.testing.assert_array_equal(cropped.rgb[:, 0], 1.0)
    np.testing.assert_array_equal(cropped.rgb[:, 1:, 0], 0.0)
    np.testing.assert_array_equal(cropped.rgb[:, 1:, 1:], 1.0)


def test_area_decimation_exactly_averages_c2_c3_and_other_integer_lanes() -> None:
    scalar = np.arange(36, dtype=np.float64).reshape(6, 6)
    np.testing.assert_array_equal(
        area_decimate(scalar, 2),
        ((3.5, 5.5, 7.5), (15.5, 17.5, 19.5), (27.5, 29.5, 31.5)),
    )
    np.testing.assert_array_equal(
        area_decimate(scalar, 3),
        ((7.0, 10.0), (25.0, 28.0)),
    )
    np.testing.assert_array_equal(area_decimate(scalar, 6), ((17.5,),))

    rgb = np.stack((scalar, scalar + 36.0, scalar + 72.0), axis=-1)
    expected = np.asarray(
        ((7.0, 10.0), (25.0, 28.0)), dtype=np.float64)[..., np.newaxis]
    expected = expected + (0.0, 36.0, 72.0)
    np.testing.assert_array_equal(area_decimate(rgb, 3), expected)


@pytest.mark.parametrize("row_id", (
    "c2-cmy7-p120-v0@3328x2304",
    "c3-cmy7-p120-v0@2240x1536",
    "c2-cmy8-p120-v0@3328x2304",
    "c3-cmy8-p120-v0@2240x1536",
))
def test_fixture_accepts_real_composed_color_tiles_and_decimates_exactly(
    row_id: str,
) -> None:
    spec = get_format_row(row_id)
    rng = np.random.default_rng(20260726)
    symbols = {
        stream.stream_id: rng.integers(
            0, 2, stream.symbol_bits, dtype=np.uint8)
        for stream in spec.stream_profiles
    }
    states = compose_color_tile(spec, 37, symbols, k_total=123)
    source_cmy = color_cells_to_dot_planes(states, spec.cell_dots)
    scan = render_color_scan(source_cmy)
    lane_rgb = area_decimate(scan.rgb, spec.cell_dots)

    expected_cmy = channel.states_to_planes(states)
    np.testing.assert_array_equal(lane_rgb, 1.0 - expected_cmy)
    np.testing.assert_array_equal(
        area_decimate(scan.truth.effective_cmy, spec.cell_dots),
        expected_cmy,
    )


@pytest.mark.parametrize(
    ("source", "parameters", "match"),
    (
        (np.zeros((3, 3)), ColorChannelParameters(), "shape"),
        (
            np.full((3, 3, 3), np.nan),
            ColorChannelParameters(),
            "finite",
        ),
        (
            np.full((3, 3, 3), 1.01),
            ColorChannelParameters(),
            r"\[0, 1\]",
        ),
        (
            np.zeros((3, 3, 3)),
            ColorChannelParameters(
                shared_affine_xy=((0.0, 0.0, 0.0),) * 3),
            "affine",
        ),
        (
            np.zeros((3, 3, 3)),
            ColorChannelParameters(planes=(PlaneParameters(),)),  # type: ignore[arg-type]
            "exactly C, M, and Y",
        ),
        (
            np.zeros((3, 3, 3)),
            ColorChannelParameters(
                planes=(
                    PlaneParameters(gamma=0.0),
                    PlaneParameters(),
                    PlaneParameters(),
                ),
            ),
            "gamma must be positive",
        ),
        (
            np.zeros((3, 3, 3)),
            ColorChannelParameters(crop_yxhw=(2, 2, 2, 2)),
            "inside",
        ),
        (
            np.zeros((3, 3, 3)),
            ColorChannelParameters(noise_std_rgb=(0.0, -0.1, 0.0)),
            "nonnegative",
        ),
    ),
)
def test_render_refuses_malformed_inputs(
    source: np.ndarray,
    parameters: ColorChannelParameters,
    match: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=match):
        render_color_scan(source, parameters)


@pytest.mark.parametrize(
    ("image", "factor", "match"),
    (
        (np.zeros((5, 6)), 2, "divisible"),
        (np.zeros((6, 6)), 0, "positive integer"),
        (np.zeros((6, 6)), 1.5, "positive integer"),
        (np.zeros((2, 2, 2, 2)), 2, "shape"),
        (np.full((2, 2), np.inf), 2, "finite"),
    ),
)
def test_area_decimation_refuses_malformed_inputs(
    image: np.ndarray,
    factor: object,
    match: str,
) -> None:
    with pytest.raises(ValueError, match=match):
        area_decimate(image, factor)  # type: ignore[arg-type]


def test_the_m281_bar_mix_renders_each_solid_bar_at_its_measured_value(
) -> None:
    """Paper and the three single-toner bars come back as e041 S14's
    8-bit means; whole-pixel offsets shift a plane without blurring it."""
    bars = np.zeros((1, 4, 3))
    bars[0, 1, 0] = bars[0, 2, 1] = bars[0, 3, 2] = 1.0
    scan = render_color_scan(bars, cmy_channel_parameters())
    np.testing.assert_allclose(
        scan.rgb[0] * 255,
        (M281_S14_BAR_MIX.paper_rgb, *M281_S14_BAR_MIX.toner_rgb),
        atol=1e-9)
    stripe = np.zeros((4, 8, 3))
    stripe[:, 3, :] = 1.0
    shifted = render_color_scan(stripe, cmy_channel_parameters(
        offsets_px=((0, 0), (2, 0), (-1, 1)))).truth.sampled_cmy
    assert np.flatnonzero(shifted[0, :, 0]).tolist() == [3]
    assert np.flatnonzero(shifted[0, :, 1]).tolist() == [5]
    assert np.flatnonzero(shifted[1, :, 2]).tolist() == [2]
    assert set(np.unique(shifted).tolist()) == {0.0, 1.0}
    with pytest.raises(ValueError, match="whole-pixel"):
        cmy_channel_parameters(offsets_px=((0, 0), (0.5, 0), (0, 0)))
