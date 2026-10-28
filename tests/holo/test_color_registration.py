from __future__ import annotations

import numpy as np
import pytest

from holo.receive import color_registration
from paperholo import acquire as historical


def test_plane_residual_fit_is_differential_to_historical_leaf() -> None:
    rng = np.random.default_rng(20260726)
    y_fraction = np.linspace(0.02, 0.98, 64)
    offsets = np.column_stack((
        -0.31 + 0.42 * y_fraction,
        0.18 - 0.27 * y_fraction,
    ))
    offsets += rng.normal(0.0, 0.015, offsets.shape)
    offsets[[4, 19, 51], 0] += (1.2, -1.0, 0.9)
    offsets[[7, 23, 58], 1] += (-1.1, 1.3, -0.8)
    quality = np.ones(y_fraction.size)
    quality[[8, 35]] = 0.0
    offsets[11, 0] = np.nan
    offsets[42, 1] = np.nan

    expected_x = historical._fit_offset_model(
        y_fraction, offsets[:, 0], quality)
    expected_y = historical._fit_offset_model(
        y_fraction, offsets[:, 1], quality)
    got = color_registration.fit_plane_residual(
        y_fraction, offsets, quality)

    np.testing.assert_array_equal(
        got.intercept_xy, (expected_x[0], expected_y[0]))
    np.testing.assert_array_equal(
        got.slope_xy, (expected_x[1], expected_y[1]))
    assert got.n_anchors == min(expected_x[2], expected_y[2])


def test_residual_support_fallbacks_are_historical_and_explicit() -> None:
    y_fraction = np.linspace(0.1, 0.9, 7)
    offsets = np.column_stack((
        np.full(7, 0.3), np.full(7, -0.2)))
    unsupported = color_registration.fit_plane_residual(
        y_fraction, offsets, np.ones(7))
    assert unsupported.intercept_xy == (0.0, 0.0)
    assert unsupported.slope_xy == (0.0, 0.0)
    assert unsupported.n_anchors == 7
    assert not unsupported.supported

    y_fraction = np.linspace(0.40, 0.48, 12)
    offsets = np.column_stack((
        0.3 + y_fraction, -0.2 - y_fraction))
    constant_only = color_registration.fit_plane_residual(
        y_fraction, offsets, np.ones(12))
    np.testing.assert_allclose(
        constant_only.intercept_xy,
        np.median(offsets, axis=0),
    )
    assert constant_only.slope_xy == (0.0, 0.0)
    assert constant_only.supported


@pytest.mark.parametrize(
    ("call", "match"),
    (
        (
            lambda: color_registration.fit_plane_residual(
                np.zeros(3), np.zeros((4, 2)), np.ones(4)),
            "lengths differ",
        ),
    ),
)
def test_registration_boundary_validation(call, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        call()
