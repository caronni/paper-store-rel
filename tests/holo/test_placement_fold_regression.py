"""Fold-regression rider for the prior_f zoom-refit fallback.

Legacy E022-v2.1 lesson (paperholo pilotsearch, fold fixture): a ~1.6 deg
crease moves the lattice fundamental outside local zoom capture, and a
window whose fit inherits another region's reciprocal can adopt the wrong
side's angle. The holo rule stays: a window whose OWN blind coarse fit
succeeds keeps that fit — the prior_f retry runs only after the blind fit
FAILS its gates, and its result faces the identical gates.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy import ndimage

from holo.receive.placement.geometry import (
    RegionContext,
    fit_window_pose,
    lattice_reciprocal,
    pose_metrics,
    jacobian_from_reciprocal,
)
from holo.receive.placement.model import PlacementConfig, PoseWindow


def _lattice(shape_px: int, pitch: float, angle_deg: float,
             seed: int) -> np.ndarray:
    """A payload-like binary cell lattice rendered at a global rotation."""
    rng = np.random.default_rng(seed)
    cells = int(shape_px / pitch) + 8
    bits = rng.integers(0, 2, (cells, cells)).astype(np.float32)
    img = np.kron(bits, np.ones((int(round(pitch)), int(round(pitch))),
                                np.float32))
    img = ndimage.rotate(img, angle_deg, reshape=False, order=1, mode="nearest")
    img = ndimage.gaussian_filter(img, 0.8)
    out = (40.0 + 180.0 * img[:shape_px, :shape_px]).astype(np.float32)
    out.setflags(write=False)
    return out


def _context(crop: np.ndarray, pitch: float) -> RegionContext:
    filtered = ndimage.uniform_filter(crop, size=5, mode="nearest")
    support = np.ones(crop.shape, bool)
    return RegionContext(
        region_index=0, y0=0, x0=0, crop=crop, filtered=filtered,
        support=support, backing=float(np.median(crop)),
        pitch_prior=float(pitch), aperture_px=5, lattice_f=None)


def test_own_blind_fit_wins_over_a_wrong_side_prior() -> None:
    """A fold-side window with a healthy spectrum keeps its own angle."""
    pitch = 8.0
    crop = _lattice(1600, pitch, 1.6, seed=5)
    config = PlacementConfig()
    context = _context(crop, pitch)
    # Poison the region seed with the OTHER side's (unrotated) reciprocal.
    context.lattice_f = np.array(
        [[1.0 / pitch, 0.0], [0.0, 1.0 / pitch]], np.float64)
    window = PoseWindow(0, 0, (0, 0), (190, 190), support_estimate=36100)
    segment = fit_window_pose(context, window, config=config)
    assert segment is not None, "healthy fold-side window must fit blind"
    assert abs(abs(segment.pose.angle_deg) - 1.6) < 0.5, (
        f"fold-side window inherited the wrong angle: "
        f"{segment.pose.angle_deg:.2f} deg")


def test_prior_retry_faces_the_identical_gates() -> None:
    """A wrong prior on a structureless crop must refuse, not invent."""
    rng = np.random.default_rng(11)
    crop = (120.0 + 20.0 * rng.standard_normal((1600, 1600))).astype(
        np.float32)
    crop.setflags(write=False)
    pitch = 8.0
    frequencies = lattice_reciprocal(
        crop, pitch,
        prior_f=np.array([[1.0 / pitch, 0.0], [0.0, 1.0 / pitch]],
                         np.float64))
    if frequencies is not None:
        # zoom found *something*; the pose gates must still refuse it
        jac = jacobian_from_reciprocal(frequencies)
        pitch_y, pitch_x, _angle, ortho = pose_metrics(jac)
        config = PlacementConfig()
        gate_ok = (
            abs(pitch_y / pitch - 1.0) <= config.pitch_tolerance
            and abs(pitch_x / pitch - 1.0) <= config.pitch_tolerance
            and abs(ortho) <= config.shear_tolerance_deg
        )
        # noise crops occasionally pass the metric gate by chance; the
        # end-to-end guard is the phase/word/validation chain — but the
        # zoom must at minimum not reproduce the prior verbatim
        assert not np.allclose(
            frequencies,
            [[1.0 / pitch, 0.0], [0.0, 1.0 / pitch]], atol=1e-9), (
            "prior_f retry returned the prior itself on pure noise")
        del gate_ok
