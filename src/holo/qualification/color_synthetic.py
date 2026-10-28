"""Independent deterministic color-channel fixtures.

This module deliberately does not import the production scale-lane,
registration, detector, or demapper implementations.  It is a small optical
forward model for qualification tests: known C/M/Y coverage is placed on a
scanner canvas, blurred and toned per printing plane, mixed subtractively
into RGB, cropped exactly, and given seeded additive scanner noise.

Coordinates use ``(x, y)`` homogeneous matrices.  ``shared_affine_xy`` maps
source coordinates into the uncropped scanner canvas.  A plane's residual is
added in scanner pixels as

``offset_xy + y_drift_xy * (source_y - source_y_center)``.
"""
from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.ndimage import affine_transform, gaussian_filter


FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

_IDENTITY_AFFINE: Final = (
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
)
_IDENTITY_MIX: Final = (
    (1.0, 0.0, 0.0),  # cyan subtracts red
    (0.0, 1.0, 0.0),  # magenta subtracts green
    (0.0, 0.0, 1.0),  # yellow subtracts blue
)
_XY_YX: Final[FloatArray] = np.asarray(
    ((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    dtype=np.float64,
)


@dataclass(frozen=True, slots=True)
class PlaneParameters:
    """Residual geometry and photometry for one printing plane."""

    offset_xy: tuple[float, float] = (0.0, 0.0)
    y_drift_xy: tuple[float, float] = (0.0, 0.0)
    blur_sigma: float = 0.0
    contrast: float = 1.0
    gamma: float = 1.0
    dropped: bool = False


@dataclass(frozen=True, slots=True)
class ColorChannelParameters:
    """Parameters of one synthetic print/scan realization."""

    shared_affine_xy: tuple[tuple[float, float, float], ...] = _IDENTITY_AFFINE
    planes: tuple[PlaneParameters, PlaneParameters, PlaneParameters] = (
        PlaneParameters(),
        PlaneParameters(),
        PlaneParameters(),
    )
    subtractive_rgb: tuple[tuple[float, float, float], ...] = _IDENTITY_MIX
    paper_rgb: tuple[float, float, float] = (1.0, 1.0, 1.0)
    output_shape: tuple[int, int] | None = None
    crop_yxhw: tuple[int, int, int, int] | None = None
    noise_std_rgb: tuple[float, float, float] = (0.0, 0.0, 0.0)
    seed: int = 0
    # Per-RGB-channel ``(y, x)`` fractional gain slope across the canvas:
    # the clean image is multiplied by ``1 + gy*u_y + gx*u_x`` with ``u``
    # running -1..1 edge to edge.  This is the illumination/development
    # half of the measured HP pathology (COLOR-UPLIFT-PLAN §1: cm-scale
    # C/M mottle plus process banding) in its simplest identifiable form —
    # a gain nearly constant WITHIN a window and different between
    # windows, which is exactly what a per-window photometric map can
    # absorb and a page-global model cannot.  All zeros (the default)
    # skips the multiplication entirely, so an unset gradient is a
    # bit-exact no-op on every existing fixture.
    gain_gradient: tuple[tuple[float, float], ...] = (
        (0.0, 0.0), (0.0, 0.0), (0.0, 0.0))
    # Per-RGB-channel UNIFORM gain, multiplied in alongside the gradient
    # (total gain = ``scale * (1 + gy*u_y + gx*u_x)``).  A page-wide
    # constant is the photometric pathology's null direction: it is real,
    # a per-window fit can find it, and a page-global model already
    # absorbs it — the channel A3's retired region dispersion floor was
    # built to refuse (COLOR-UPLIFT-MEASUREMENTS §12 R1), and still the
    # honest null direction for any successor.  All ones (the default)
    # skips the multiplication with
    # the gradient's, so an unset scale is a bit-exact no-op.
    gain_scale_rgb: tuple[float, float, float] = (1.0, 1.0, 1.0)


@dataclass(frozen=True, slots=True)
class ColorChannelTruth:
    """Inspectable ground truth for a rendered fixture.

    Channel order is C/M/Y for plane-valued arrays and R/G/B for image-valued
    arrays.  ``sampled_cmy`` is the geometric result before blur;
    ``blurred_cmy`` is before tone/contrast; and ``effective_cmy`` is the
    subtractive coverage used by the mixing matrix.
    """

    source_shape: tuple[int, int]
    canvas_shape: tuple[int, int]
    crop_yxhw: tuple[int, int, int, int]
    shared_affine_xy: FloatArray
    plane_offsets_xy: FloatArray
    plane_y_drift_xy: FloatArray
    plane_blur_sigma: FloatArray
    plane_contrast: FloatArray
    plane_gamma: FloatArray
    dropped_planes: BoolArray
    canvas_forward_affines_xy: FloatArray
    output_forward_affines_xy: FloatArray
    subtractive_rgb: FloatArray
    paper_rgb: FloatArray
    noise_std_rgb: FloatArray
    gain_gradient: FloatArray
    gain_scale_rgb: FloatArray
    noise_seed: int
    support_masks: BoolArray
    active_masks: BoolArray
    sampled_cmy: FloatArray
    blurred_cmy: FloatArray
    effective_cmy: FloatArray
    clean_rgb: FloatArray
    additive_noise_rgb: FloatArray
    clipped_rgb_mask: BoolArray


@dataclass(frozen=True, slots=True)
class SyntheticColorScan:
    rgb: FloatArray
    truth: ColorChannelTruth


def _readonly(array: NDArray) -> NDArray:
    result = np.ascontiguousarray(array)
    result.setflags(write=False)
    return result


def _finite_array(
    name: str,
    value: object,
    shape: tuple[int, ...],
) -> FloatArray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be finite")
    return array


def _nonnegative_scalar(name: str, value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite nonnegative number") from exc
    if not np.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return number


def _positive_shape(name: str, value: object) -> tuple[int, int]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise ValueError(f"{name} must be a (height, width) tuple")
    if any(
        isinstance(item, bool) or not isinstance(item, Integral) or item <= 0
        for item in value
    ):
        raise ValueError(f"{name} entries must be positive integers")
    return int(value[0]), int(value[1])


def _validate_parameters(
    source_shape: tuple[int, int],
    parameters: ColorChannelParameters,
) -> tuple[
    FloatArray,
    tuple[PlaneParameters, PlaneParameters, PlaneParameters],
    FloatArray,
    FloatArray,
    tuple[int, int],
    tuple[int, int, int, int],
    FloatArray,
    FloatArray,
    FloatArray,
]:
    if not isinstance(parameters, ColorChannelParameters):
        raise TypeError("parameters must be ColorChannelParameters")

    shared = _finite_array(
        "shared_affine_xy", parameters.shared_affine_xy, (3, 3))
    if not np.allclose(shared[2], (0.0, 0.0, 1.0), rtol=0.0, atol=1e-12):
        raise ValueError(
            "shared_affine_xy must be a two-dimensional homogeneous affine")
    if abs(float(np.linalg.det(shared))) <= 1e-12:
        raise ValueError("shared_affine_xy must be invertible")

    if not isinstance(parameters.planes, tuple) or len(parameters.planes) != 3:
        raise ValueError("planes must contain exactly C, M, and Y parameters")
    planes = parameters.planes
    for index, plane in enumerate(planes):
        if not isinstance(plane, PlaneParameters):
            raise TypeError(f"planes[{index}] must be PlaneParameters")
        _finite_array(f"planes[{index}].offset_xy", plane.offset_xy, (2,))
        _finite_array(
            f"planes[{index}].y_drift_xy", plane.y_drift_xy, (2,))
        _nonnegative_scalar(
            f"planes[{index}].blur_sigma", plane.blur_sigma)
        _nonnegative_scalar(f"planes[{index}].contrast", plane.contrast)
        gamma = _nonnegative_scalar(f"planes[{index}].gamma", plane.gamma)
        if gamma == 0.0:
            raise ValueError(f"planes[{index}].gamma must be positive")
        if not isinstance(plane.dropped, bool):
            raise ValueError(f"planes[{index}].dropped must be Boolean")

    mixing = _finite_array(
        "subtractive_rgb", parameters.subtractive_rgb, (3, 3))
    if np.any(mixing < 0.0):
        raise ValueError("subtractive_rgb coefficients must be nonnegative")
    paper = _finite_array("paper_rgb", parameters.paper_rgb, (3,))
    if np.any((paper < 0.0) | (paper > 1.0)):
        raise ValueError("paper_rgb values must lie in [0, 1]")

    canvas_shape = (
        source_shape
        if parameters.output_shape is None
        else _positive_shape("output_shape", parameters.output_shape)
    )
    if parameters.crop_yxhw is None:
        crop = (0, 0, canvas_shape[0], canvas_shape[1])
    else:
        raw_crop = parameters.crop_yxhw
        if not isinstance(raw_crop, tuple) or len(raw_crop) != 4:
            raise ValueError("crop_yxhw must be a (y, x, height, width) tuple")
        if any(
            isinstance(item, bool) or not isinstance(item, Integral)
            for item in raw_crop
        ):
            raise ValueError("crop_yxhw entries must be integers")
        crop = tuple(int(item) for item in raw_crop)
        y0, x0, height, width = crop
        if y0 < 0 or x0 < 0 or height <= 0 or width <= 0:
            raise ValueError(
                "crop_yxhw origin must be nonnegative and extent positive")
        if y0 + height > canvas_shape[0] or x0 + width > canvas_shape[1]:
            raise ValueError("crop_yxhw must lie inside output_shape")

    noise_std = _finite_array(
        "noise_std_rgb", parameters.noise_std_rgb, (3,))
    if np.any(noise_std < 0.0):
        raise ValueError("noise_std_rgb values must be nonnegative")
    gain_gradient = _finite_array(
        "gain_gradient", parameters.gain_gradient, (3, 2))
    if np.any(np.abs(gain_gradient).sum(axis=1) >= 1.0):
        raise ValueError(
            "gain_gradient must keep the canvas gain positive "
            "(|gy| + |gx| < 1 per channel)")
    gain_scale = _finite_array(
        "gain_scale_rgb", parameters.gain_scale_rgb, (3,))
    if np.any(gain_scale <= 0.0):
        raise ValueError("gain_scale_rgb values must be positive")
    if (
        isinstance(parameters.seed, bool)
        or not isinstance(parameters.seed, Integral)
        or parameters.seed < 0
    ):
        raise ValueError("seed must be a nonnegative integer")

    return (shared, planes, mixing, paper, canvas_shape, crop, noise_std,
            gain_gradient, gain_scale)


def _plane_forward_affine(
    shared: FloatArray,
    plane: PlaneParameters,
    source_height: int,
) -> FloatArray:
    offset = np.asarray(plane.offset_xy, dtype=np.float64)
    drift = np.asarray(plane.y_drift_xy, dtype=np.float64)
    source_y_center = (source_height - 1.0) / 2.0
    forward = shared.copy()
    forward[0, 1] += drift[0]
    forward[1, 1] += drift[1]
    forward[0, 2] += offset[0] - drift[0] * source_y_center
    forward[1, 2] += offset[1] - drift[1] * source_y_center
    if abs(float(np.linalg.det(forward))) <= 1e-12:
        raise ValueError("a plane residual makes its affine singular")
    return forward


def _sample_plane(
    source: FloatArray,
    forward_xy: FloatArray,
    output_shape: tuple[int, int],
) -> tuple[FloatArray, BoolArray]:
    inverse_xy = np.linalg.inv(forward_xy)
    inverse_yx = _XY_YX @ inverse_xy @ _XY_YX
    sampled = affine_transform(
        source,
        inverse_yx[:2, :2],
        offset=inverse_yx[:2, 2],
        output_shape=output_shape,
        order=1,
        mode="constant",
        cval=0.0,
        prefilter=False,
    )

    output_y, output_x = np.indices(output_shape, dtype=np.float64)
    source_x = (
        inverse_xy[0, 0] * output_x
        + inverse_xy[0, 1] * output_y
        + inverse_xy[0, 2]
    )
    source_y = (
        inverse_xy[1, 0] * output_x
        + inverse_xy[1, 1] * output_y
        + inverse_xy[1, 2]
    )
    support = (
        (source_x >= 0.0)
        & (source_x <= source.shape[1] - 1.0)
        & (source_y >= 0.0)
        & (source_y <= source.shape[0] - 1.0)
    )
    return sampled, support


def _gain_field(
    canvas_shape: tuple[int, int],
    gain_gradient: FloatArray,
    gain_scale: FloatArray,
) -> FloatArray:
    """``(H, W, 3)`` gain ``s * (1 + gy*u_y + gx*u_x)``, ``u`` in ±1.

    A single-row or single-column canvas has no extent to ramp across, so
    its normalized coordinate is 0 (the centre) rather than a division by
    zero.
    """
    height, width = canvas_shape
    unit_y = (
        np.zeros(height) if height < 2
        else np.linspace(-1.0, 1.0, height))
    unit_x = (
        np.zeros(width) if width < 2 else np.linspace(-1.0, 1.0, width))
    return gain_scale[np.newaxis, np.newaxis, :] * (
        1.0
        + gain_gradient[np.newaxis, np.newaxis, :, 0]
        * unit_y[:, np.newaxis, np.newaxis]
        + gain_gradient[np.newaxis, np.newaxis, :, 1]
        * unit_x[np.newaxis, :, np.newaxis]
    )


def render_color_scan(
    source_cmy: NDArray,
    parameters: ColorChannelParameters = ColorChannelParameters(),
) -> SyntheticColorScan:
    """Render a deterministic synthetic RGB scan from C/M/Y coverage.

    ``source_cmy`` has shape ``(height, width, 3)`` and finite coverage in
    ``[0, 1]``.  The returned arrays are read-only to keep qualification truth
    from being modified accidentally.
    """

    cmy = np.asarray(source_cmy, dtype=np.float64)
    if cmy.ndim != 3 or cmy.shape[2] != 3 or cmy.shape[:2] == (0, 0):
        raise ValueError("source_cmy must have shape (height, width, 3)")
    if cmy.shape[0] <= 0 or cmy.shape[1] <= 0:
        raise ValueError("source_cmy height and width must be positive")
    if not np.all(np.isfinite(cmy)):
        raise ValueError("source_cmy must be finite")
    if np.any((cmy < 0.0) | (cmy > 1.0)):
        raise ValueError("source_cmy values must lie in [0, 1]")

    (
        shared,
        planes,
        mixing,
        paper,
        canvas_shape,
        crop,
        noise_std,
        gain_gradient,
        gain_scale,
    ) = _validate_parameters(cmy.shape[:2], parameters)

    sampled = np.empty((*canvas_shape, 3), dtype=np.float64)
    blurred = np.empty_like(sampled)
    effective = np.empty_like(sampled)
    support = np.empty((*canvas_shape, 3), dtype=np.bool_)
    forward = np.empty((3, 3, 3), dtype=np.float64)

    for channel, plane in enumerate(planes):
        plane_forward = _plane_forward_affine(
            shared, plane, cmy.shape[0])
        forward[channel] = plane_forward
        sampled[..., channel], support[..., channel] = _sample_plane(
            cmy[..., channel], plane_forward, canvas_shape)
        sigma = float(plane.blur_sigma)
        blurred[..., channel] = (
            sampled[..., channel]
            if sigma == 0.0
            else gaussian_filter(
                sampled[..., channel],
                sigma=sigma,
                mode="constant",
                cval=0.0,
            )
        )
        toned = np.power(
            np.clip(float(plane.contrast) * blurred[..., channel], 0.0, 1.0),
            float(plane.gamma),
        )
        effective[..., channel] = 0.0 if plane.dropped else toned

    absorbed_rgb = np.einsum(
        "rc,hwc->hwr", mixing, effective, optimize=True)
    clean_canvas = np.clip(paper[np.newaxis, np.newaxis, :] - absorbed_rgb,
                           0.0, 1.0)
    if np.any(gain_gradient) or np.any(gain_scale != 1.0):
        # Multiplicative canvas gain, applied after mixing and before the
        # crop so a cropped fixture sees the same physical field a full
        # one does.  Guarded so the neutral default never even builds the
        # coordinate ramps: no gain is a bit-exact no-op.
        clean_canvas = np.clip(
            clean_canvas * _gain_field(
                canvas_shape, gain_gradient, gain_scale),
            0.0, 1.0)

    y0, x0, height, width = crop
    selection = np.s_[y0:y0 + height, x0:x0 + width]
    sampled_crop = sampled[selection]
    blurred_crop = blurred[selection]
    effective_crop = effective[selection]
    support_crop = support[selection]
    clean_rgb = clean_canvas[selection]

    rng = np.random.default_rng(int(parameters.seed))
    additive_noise = rng.normal(
        loc=0.0,
        scale=noise_std,
        size=clean_rgb.shape,
    )
    unclipped_rgb = clean_rgb + additive_noise
    clipped_mask = (unclipped_rgb < 0.0) | (unclipped_rgb > 1.0)
    rgb = np.clip(unclipped_rgb, 0.0, 1.0)

    crop_translation = np.asarray(
        ((1.0, 0.0, -float(x0)),
         (0.0, 1.0, -float(y0)),
         (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    output_forward = np.einsum(
        "ij,cjk->cik", crop_translation, forward, optimize=True)
    dropped = np.asarray(
        [plane.dropped for plane in planes], dtype=np.bool_)
    active_masks = support_crop & ~dropped[np.newaxis, np.newaxis, :]

    truth = ColorChannelTruth(
        source_shape=(int(cmy.shape[0]), int(cmy.shape[1])),
        canvas_shape=canvas_shape,
        crop_yxhw=crop,
        shared_affine_xy=_readonly(shared.copy()),
        plane_offsets_xy=_readonly(np.asarray(
            [plane.offset_xy for plane in planes], dtype=np.float64)),
        plane_y_drift_xy=_readonly(np.asarray(
            [plane.y_drift_xy for plane in planes], dtype=np.float64)),
        plane_blur_sigma=_readonly(np.asarray(
            [plane.blur_sigma for plane in planes], dtype=np.float64)),
        plane_contrast=_readonly(np.asarray(
            [plane.contrast for plane in planes], dtype=np.float64)),
        plane_gamma=_readonly(np.asarray(
            [plane.gamma for plane in planes], dtype=np.float64)),
        dropped_planes=_readonly(dropped),
        canvas_forward_affines_xy=_readonly(forward),
        output_forward_affines_xy=_readonly(output_forward),
        subtractive_rgb=_readonly(mixing.copy()),
        paper_rgb=_readonly(paper.copy()),
        noise_std_rgb=_readonly(noise_std.copy()),
        gain_gradient=_readonly(gain_gradient.copy()),
        gain_scale_rgb=_readonly(gain_scale.copy()),
        noise_seed=int(parameters.seed),
        support_masks=_readonly(support_crop),
        active_masks=_readonly(active_masks),
        sampled_cmy=_readonly(sampled_crop),
        blurred_cmy=_readonly(blurred_crop),
        effective_cmy=_readonly(effective_crop),
        clean_rgb=_readonly(clean_rgb),
        additive_noise_rgb=_readonly(additive_noise),
        clipped_rgb_mask=_readonly(clipped_mask),
    )
    return SyntheticColorScan(rgb=_readonly(rgb), truth=truth)


def area_decimate(image: NDArray, factor: int) -> FloatArray:
    """Return exact non-overlapping area averages for an integer scale lane.

    This is intentionally independent of the receiver's materializer.  It
    accepts a scalar raster ``(H, W)`` or channel-last raster ``(H, W, C)``;
    both dimensions must be exactly divisible by ``factor``.
    """

    if (
        isinstance(factor, bool)
        or not isinstance(factor, Integral)
        or factor <= 0
    ):
        raise ValueError("factor must be a positive integer")
    array = np.asarray(image, dtype=np.float64)
    if array.ndim not in (2, 3):
        raise ValueError("image must have shape (H, W) or (H, W, C)")
    if array.shape[0] <= 0 or array.shape[1] <= 0:
        raise ValueError("image height and width must be positive")
    if array.ndim == 3 and array.shape[2] <= 0:
        raise ValueError("image must have at least one channel")
    if not np.all(np.isfinite(array)):
        raise ValueError("image must be finite")
    divisor = int(factor)
    height, width = array.shape[:2]
    if height % divisor or width % divisor:
        raise ValueError("image dimensions must be divisible by factor")

    if array.ndim == 2:
        blocks = array.reshape(
            height // divisor, divisor, width // divisor, divisor)
    else:
        blocks = array.reshape(
            height // divisor,
            divisor,
            width // divisor,
            divisor,
            array.shape[2],
        )
    return np.mean(blocks, axis=(1, 3), dtype=np.float64)
