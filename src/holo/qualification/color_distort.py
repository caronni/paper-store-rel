"""Standalone deterministic TIFF-in/TIFF-out print/scan distortion tool.

The tool has no generator, receiver, corpus, manifest, or device-registry
role.  It accepts one single-frame 600-dpi RGB TIFF and writes one TIFF
(RGB, except ``hp-m281-flatbed-k`` which writes grayscale).  Named profiles
are merely convenient parameter bundles.  With no profile, the synthetic
transform starts from an identity parameter set:

``nominal``
    Mild synthetic defects for ordinary receiver exercises.
``stress``
    Stronger synthetic defects for adversarial receiver exercises.
``hp-m281-flatbed-cmy``
    The frozen M281 + integrated-flatbed CAL-1 simulator, color path:
    threshold-separable C/M/Y planes through the measured
    ``screened_composite`` emission (any plane overlap re-screens).  This
    profile requires a clean C/M/Y RGB palette and emits 1200 dpi RGB.
``hp-m281-flatbed-k``
    The same frozen CAL-1 pair, K-only path: a black/white page as one K
    plane through the bit-faithful ``clean_mask`` imagemask emission (the
    real M281 b/w print path, Layer-0 freeze) and the measured flatbed
    scan model.  Emits 1200 dpi grayscale.

Synthetic profiles can emit either 1200 or 4800 dpi.  Effects are applied on
the physical 600-dpi printer-dot raster, then sampled into the requested scan
raster.  Full 4800-dpi pages are written strip-by-strip to an uncompressed
BigTIFF instead of being materialized in memory.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import tempfile
from dataclasses import dataclass, replace
from numbers import Integral, Real
from pathlib import Path
from typing import Final, Sequence

import numpy as np
import tifffile
from PIL import Image, ImageFilter


INPUT_DPI: Final = 600
OUTPUT_DPIS: Final = (1200, 4800)
SYNTHETIC_PROFILES: Final = ("nominal", "stress")
MEASURED_PROFILES: Final = ("hp-m281-flatbed-cmy", "hp-m281-flatbed-k")
PROFILES: Final = (*SYNTHETIC_PROFILES, *MEASURED_PROFILES)
_TIFF_SUFFIXES: Final = (".tif", ".tiff")

_CHUNK_ROWS: Final = 128
_INK_THRESHOLD: Final = 250
_UINT8_MAX: Final = 255


@dataclass(frozen=True, slots=True)
class DistortionParameters:
    """Physical-dot-domain parameters for one synthetic transformation."""

    seed: int
    shear_xy: tuple[float, float] = (0.0, 0.0)
    translation_xy: tuple[float, float] = (0.0, 0.0)
    canvas_margin_yx: tuple[int, int] = (0, 0)
    crop_yxhw: tuple[int, int, int, int] | None = None
    dropout_probability: float = 0.0
    speckle_probability: float = 0.0
    speckle_rgb: tuple[int, int, int] = (24, 20, 18)
    blur_radius_dots: float = 0.0
    noise_std_rgb: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        _seed("seed", self.seed)
        _finite_tuple("shear_xy", self.shear_xy, 2)
        _finite_tuple("translation_xy", self.translation_xy, 2)
        _integer_tuple(
            "canvas_margin_yx", self.canvas_margin_yx, 2, minimum=0)
        if self.crop_yxhw is not None:
            crop = _integer_tuple(
                "crop_yxhw", self.crop_yxhw, 4, minimum=0)
            if crop[2] <= 0 or crop[3] <= 0:
                raise ValueError("crop_yxhw height and width must be positive")
        _probability("dropout_probability", self.dropout_probability)
        _probability("speckle_probability", self.speckle_probability)
        rgb = _integer_tuple("speckle_rgb", self.speckle_rgb, 3, minimum=0)
        if any(value > _UINT8_MAX for value in rgb):
            raise ValueError("speckle_rgb entries must be in 0..255")
        _nonnegative("blur_radius_dots", self.blur_radius_dots)
        noise = _finite_tuple("noise_std_rgb", self.noise_std_rgb, 3)
        if any(value < 0.0 for value in noise):
            raise ValueError("noise_std_rgb entries must be nonnegative")
        sx, sy = (float(value) for value in self.shear_xy)
        if abs(1.0 - sx * sy) <= 1e-9:
            raise ValueError("shear_xy makes the affine singular")


def _seed(name: str, value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, Integral)
        or not 0 <= int(value) < 2**64
    ):
        raise ValueError(f"{name} must be an unsigned 64-bit integer")
    return int(value)


def _finite_tuple(name: str, value: object, length: int) -> tuple[float, ...]:
    if not isinstance(value, tuple) or len(value) != length:
        raise ValueError(f"{name} must be a {length}-tuple")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, Real):
            raise ValueError(f"{name} entries must be finite numbers")
        number = float(item)
        if not math.isfinite(number):
            raise ValueError(f"{name} entries must be finite numbers")
        result.append(number)
    return tuple(result)


def _integer_tuple(
    name: str,
    value: object,
    length: int,
    *,
    minimum: int,
) -> tuple[int, ...]:
    if not isinstance(value, tuple) or len(value) != length:
        raise ValueError(f"{name} must be a {length}-tuple")
    if any(
        isinstance(item, bool)
        or not isinstance(item, Integral)
        or int(item) < minimum
        for item in value
    ):
        raise ValueError(f"{name} entries must be integers >= {minimum}")
    return tuple(int(item) for item in value)


def _nonnegative(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite nonnegative number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return number


def _probability(name: str, value: object) -> float:
    number = _nonnegative(name, value)
    if number > 1.0:
        raise ValueError(f"{name} must be in [0, 1]")
    return number


def _output_dpi(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError("output_dpi must be 1200 or 4800")
    dpi = int(value)
    if dpi not in OUTPUT_DPIS:
        raise ValueError("output_dpi must be 1200 or 4800")
    return dpi


def profile_parameters(
    profile: str,
    seed: int,
    *,
    width: int,
    height: int,
) -> DistortionParameters:
    """Return a frozen synthetic profile for a 600-dpi source raster."""
    actual_seed = _seed("seed", seed)
    for label, value in (("width", width), ("height", height)):
        if (
            isinstance(value, bool)
            or not isinstance(value, Integral)
            or int(value) <= 0
        ):
            raise ValueError(f"{label} must be a positive integer")
    width = int(width)
    height = int(height)

    if profile == "nominal":
        return DistortionParameters(
            seed=actual_seed,
            shear_xy=(0.0025, -0.0008),
            translation_xy=(4.0, -3.0),
            canvas_margin_yx=(72, 72),
            crop_yxhw=(36, 42, height + 60, width + 54),
            dropout_probability=0.0025,
            speckle_probability=0.00020,
            blur_radius_dots=0.45,
            noise_std_rgb=(2.0, 2.5, 3.0),
        )
    if profile == "stress":
        return DistortionParameters(
            seed=actual_seed,
            shear_xy=(0.0080, -0.0025),
            translation_xy=(-11.0, 7.0),
            canvas_margin_yx=(128, 128),
            crop_yxhw=(82, 70, height + 100, width + 116),
            dropout_probability=0.012,
            speckle_probability=0.0008,
            speckle_rgb=(18, 16, 14),
            blur_radius_dots=0.85,
            noise_std_rgb=(5.0, 6.0, 7.0),
        )
    raise ValueError(
        f"unknown synthetic profile {profile!r}; "
        f"expected {' or '.join(SYNTHETIC_PROFILES)}"
    )


def _profile_overrides(
    parameters: DistortionParameters,
    arguments: argparse.Namespace,
) -> DistortionParameters:
    values: dict[str, object] = {}
    for argument, field in (
        ("shear", "shear_xy"),
        ("translate", "translation_xy"),
        ("margin", "canvas_margin_yx"),
        ("crop", "crop_yxhw"),
        ("dropout", "dropout_probability"),
        ("speckle", "speckle_probability"),
        ("speckle_rgb", "speckle_rgb"),
        ("blur", "blur_radius_dots"),
        ("noise_rgb", "noise_std_rgb"),
    ):
        value = getattr(arguments, argument)
        if value is not None:
            values[field] = tuple(value) if isinstance(value, list) else value
    return replace(parameters, **values)


def _source_pixels(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        if image.format != "TIFF":
            raise ValueError("source must be a TIFF file")
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("source TIFF must contain exactly one frame")
        if image.mode != "RGB":
            raise ValueError("source TIFF must contain an RGB raster")
        dpi = image.info.get("dpi")
        if dpi is None or len(dpi) != 2:
            raise ValueError("source TIFF must declare its pixel density")
        if any(abs(float(value) - INPUT_DPI) > 0.5 for value in dpi):
            raise ValueError(
                f"source TIFF must declare {INPUT_DPI}-dpi density")
        image.load()
        return np.asarray(image, dtype=np.uint8).copy()


def _domain_seed(seed: int, domain: str) -> int:
    material = (
        b"holo/color-distort/v1/"
        + int(seed).to_bytes(8, "big")
        + b"/"
        + domain.encode("ascii")
    )
    return int.from_bytes(hashlib.sha256(material).digest()[:8], "big")


def _apply_source_defects(
    pixels: np.ndarray,
    parameters: DistortionParameters,
) -> None:
    dropout_probability = float(parameters.dropout_probability)
    speckle_probability = float(parameters.speckle_probability)
    if dropout_probability == 0.0 and speckle_probability == 0.0:
        return
    dropout_rng = (
        np.random.default_rng(_domain_seed(parameters.seed, "dropout"))
        if dropout_probability
        else None
    )
    speckle_rng = (
        np.random.default_rng(_domain_seed(parameters.seed, "speckle"))
        if speckle_probability
        else None
    )
    height = pixels.shape[0]

    for y0 in range(0, height, _CHUNK_ROWS):
        y1 = min(y0 + _CHUNK_ROWS, height)
        chunk = pixels[y0:y1]
        ink = (
            np.any(chunk < _INK_THRESHOLD, axis=2)
            if dropout_rng is not None
            else None
        )
        paper = (
            np.all(chunk >= _INK_THRESHOLD, axis=2)
            if speckle_rng is not None
            else None
        )
        dropout = None
        speckle = None
        if dropout_rng is not None:
            assert ink is not None
            dropout = ink & (
                dropout_rng.random(ink.shape, dtype=np.float32)
                < dropout_probability
            )
        if speckle_rng is not None:
            assert paper is not None
            speckle = paper & (
                speckle_rng.random(paper.shape, dtype=np.float32)
                < speckle_probability
            )
        if dropout is not None:
            chunk[dropout] = _UINT8_MAX
        if speckle is not None:
            chunk[speckle] = parameters.speckle_rgb


def _translation(x: float, y: float) -> np.ndarray:
    return np.asarray(
        ((1.0, 0.0, x), (0.0, 1.0, y), (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )


def _geometry(
    source_size_xy: tuple[int, int],
    parameters: DistortionParameters,
) -> tuple[np.ndarray, tuple[int, int], tuple[int, int, int, int]]:
    width, height = source_size_xy
    margin_y, margin_x = parameters.canvas_margin_yx
    canvas_size_xy = (width + 2 * margin_x, height + 2 * margin_y)
    sx, sy = parameters.shear_xy
    tx, ty = parameters.translation_xy
    center_x = (width - 1.0) / 2.0
    center_y = (height - 1.0) / 2.0
    shear = np.asarray(
        ((1.0, sx, 0.0), (sy, 1.0, 0.0), (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    source_to_canvas = (
        _translation(margin_x + tx, margin_y + ty)
        @ _translation(center_x, center_y)
        @ shear
        @ _translation(-center_x, -center_y)
    )
    if parameters.crop_yxhw is None:
        crop = (0, 0, canvas_size_xy[1], canvas_size_xy[0])
    else:
        crop = tuple(int(value) for value in parameters.crop_yxhw)
    crop_y, crop_x, crop_h, crop_w = crop
    if (
        crop_y + crop_h > canvas_size_xy[1]
        or crop_x + crop_w > canvas_size_xy[0]
    ):
        raise ValueError("crop_yxhw must lie inside the transformed canvas")
    return source_to_canvas, canvas_size_xy, crop


def _affine_image(
    source: Image.Image,
    source_to_canvas_xy: np.ndarray,
    canvas_size_xy: tuple[int, int],
) -> Image.Image:
    inverse = np.linalg.inv(source_to_canvas_xy)
    coefficients = tuple(float(value) for value in (
        inverse[0, 0],
        inverse[0, 1],
        inverse[0, 2],
        inverse[1, 0],
        inverse[1, 1],
        inverse[1, 2],
    ))
    return source.transform(
        canvas_size_xy,
        Image.Transform.AFFINE,
        coefficients,
        resample=Image.Resampling.BILINEAR,
        fillcolor=(_UINT8_MAX, _UINT8_MAX, _UINT8_MAX),
    )


def _write_sampled_tiff(
    source: Image.Image,
    output: Path,
    *,
    output_dpi: int,
    parameters: DistortionParameters,
) -> None:
    scale = output_dpi // INPUT_DPI
    output_width = source.width * scale
    output_height = source.height * scale
    byte_count = output_width * output_height * 3
    target = tifffile.memmap(
        output,
        shape=(output_height, output_width, 3),
        dtype=np.uint8,
        photometric="rgb",
        bigtiff=byte_count >= 2**32,
        resolution=(output_dpi, output_dpi),
        resolutionunit="INCH",
        metadata=None,
    )
    rng = np.random.default_rng(
        _domain_seed(parameters.seed, "rgb-noise"))
    noise_std = np.asarray(parameters.noise_std_rgb, dtype=np.float32)

    try:
        for y0 in range(0, output_height, _CHUNK_ROWS):
            y1 = min(y0 + _CHUNK_ROWS, output_height)
            strip = source.transform(
                (output_width, y1 - y0),
                Image.Transform.AFFINE,
                (
                    1.0 / scale,
                    0.0,
                    0.0,
                    0.0,
                    1.0 / scale,
                    y0 / scale,
                ),
                resample=Image.Resampling.BICUBIC,
            )
            pixels = np.asarray(strip, dtype=np.uint8).astype(np.float32)
            strip.close()
            if np.any(noise_std):
                pixels += (
                    rng.normal(size=pixels.shape).astype(np.float32)
                    * noise_std
                )
            target[y0:y1] = np.rint(
                np.clip(pixels, 0.0, float(_UINT8_MAX))
            ).astype(np.uint8)
        target.flush()
    finally:
        del target


def _write_synthetic(
    source: Path,
    output: Path,
    *,
    parameters: DistortionParameters,
    output_dpi: int,
) -> None:
    pixels = _source_pixels(source)
    _apply_source_defects(pixels, parameters)
    defected = Image.fromarray(pixels, mode="RGB")
    del pixels
    identity_geometry = (
        parameters.shear_xy == (0.0, 0.0)
        and parameters.translation_xy == (0.0, 0.0)
        and parameters.canvas_margin_yx == (0, 0)
        and parameters.crop_yxhw is None
    )
    if identity_geometry:
        physical = defected
    else:
        source_to_canvas, canvas_size_xy, crop = _geometry(
            defected.size, parameters)
        transformed = _affine_image(
            defected, source_to_canvas, canvas_size_xy)
        defected.close()
        crop_y, crop_x, crop_h, crop_w = crop
        physical = transformed.crop(
            (crop_x, crop_y, crop_x + crop_w, crop_y + crop_h))
        transformed.close()
    if parameters.blur_radius_dots:
        blurred = physical.filter(
            ImageFilter.GaussianBlur(
                float(parameters.blur_radius_dots)))
        physical.close()
    else:
        blurred = physical
    try:
        _write_sampled_tiff(
            blurred,
            output,
            output_dpi=output_dpi,
            parameters=parameters,
        )
    finally:
        blurred.close()


def _threshold_plane_bits(pixels: np.ndarray, *, label: str) -> np.ndarray:
    palette_codes: set[int] = set()
    for y0 in range(0, pixels.shape[0], 256):
        stripe = pixels[y0:y0 + 256]
        codes = (
            (stripe[..., 0].astype(np.uint32) << 16)
            | (stripe[..., 1].astype(np.uint32) << 8)
            | stripe[..., 2].astype(np.uint32)
        )
        palette_codes.update(int(value) for value in np.unique(codes))
        if len(palette_codes) > 8:
            raise ValueError(
                f"{label} requires at most eight "
                "threshold-separable RGB colors"
            )
    palette = [
        (code >> 16, (code >> 8) & 255, code & 255)
        for code in sorted(palette_codes)
    ]
    if any(
        120 <= channel < 136
        for color in palette
        for channel in color
    ):
        raise ValueError(
            f"{label} found an ambiguous plane channel")
    signatures = {
        tuple(channel < 128 for channel in color)
        for color in palette
    }
    if len(signatures) != len(palette):
        raise ValueError(
            f"{label} requires one unique C/M/Y signature "
            "per RGB palette color"
        )
    return np.moveaxis(
        pixels < 128, 2, 0).astype(np.uint8, copy=False)


def _threshold_k_bits(pixels: np.ndarray) -> np.ndarray:
    """One K plane from a black/white page (ink = dark in all channels)."""
    planes = _threshold_plane_bits(pixels, label="hp-m281-flatbed-k")
    colored = (planes[0] != planes[1]) | (planes[0] != planes[2])
    if bool(colored.any()):
        raise ValueError(
            "hp-m281-flatbed-k requires a black/white page (every ink "
            "color dark in all three channels); colored ink belongs to "
            "hp-m281-flatbed-cmy"
        )
    return planes[0]


def _write_hp_m281_flatbed_cmy(
    source: Path,
    output: Path,
    *,
    seed: int,
) -> None:
    planes = _threshold_plane_bits(
        _source_pixels(source), label="hp-m281-flatbed-cmy")

    # Qualification-only reuse of the one existing characterized simulator.
    import paperholo.channel.simulator as simulator

    reflectance = simulator.print_scan_cmy(
        planes,
        simulator.ChannelParams(
            seed=seed,
            # Domain string predates the -cmy rename; kept for byte-stable
            # same-seed outputs.
            scan_seed=_domain_seed(seed, "hp-m281-flatbed-scan"),
            emission="screened_composite",
            geometry=True,
        ),
    )
    np.clip(reflectance, 0.0, 1.0, out=reflectance)
    reflectance *= 255.0
    np.rint(reflectance, out=reflectance)
    pixels = reflectance.astype(np.uint8)
    del reflectance
    tifffile.imwrite(
        output,
        pixels,
        photometric="rgb",
        compression=None,
        bigtiff=pixels.nbytes >= 2**32,
        resolution=(1200, 1200),
        resolutionunit="INCH",
        metadata=None,
    )


def _write_hp_m281_flatbed_k(
    source: Path,
    output: Path,
    *,
    seed: int,
) -> None:
    bits = _threshold_k_bits(_source_pixels(source))

    # Qualification-only reuse of the one existing characterized simulator.
    import paperholo.channel.simulator as simulator

    reflectance = simulator.print_scan(
        bits,
        simulator.ChannelParams(
            seed=seed,
            scan_seed=_domain_seed(seed, "hp-m281-flatbed-k-scan"),
            plane="K",
            emission="clean_mask",
            geometry=True,
        ),
    )
    np.clip(reflectance, 0.0, 1.0, out=reflectance)
    reflectance *= 255.0
    np.rint(reflectance, out=reflectance)
    pixels = reflectance.astype(np.uint8)
    del reflectance
    tifffile.imwrite(
        output,
        pixels,
        photometric="minisblack",
        compression=None,
        bigtiff=pixels.nbytes >= 2**32,
        resolution=(1200, 1200),
        resolutionunit="INCH",
        metadata=None,
    )


def _staging_path(output: Path) -> tuple[Path, Path]:
    if output.suffix.lower() not in _TIFF_SUFFIXES:
        raise ValueError("output must have a .tif or .tiff suffix")
    if os.path.lexists(output):
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    directory = Path(tempfile.mkdtemp(
        prefix=".holo-color-distort-",
        suffix=".staging",
        dir=output.parent,
    ))
    return directory, directory / output.name


def _publish(staged: Path, output: Path) -> None:
    # A hard link cannot overwrite an output raced into existence.
    os.link(staged, output)


def distort_with_parameters(
    source_tiff: Path,
    output_tiff: Path,
    parameters: DistortionParameters,
    *,
    output_dpi: int,
) -> Path:
    """Apply explicit synthetic parameters to one 600-dpi RGB TIFF."""
    source = Path(source_tiff)
    output = Path(output_tiff)
    if not source.is_file():
        raise FileNotFoundError(source)
    if not isinstance(parameters, DistortionParameters):
        raise TypeError("parameters must be DistortionParameters")
    dpi = _output_dpi(output_dpi)
    staging_directory, staged = _staging_path(output)
    try:
        _write_synthetic(
            source,
            staged,
            parameters=parameters,
            output_dpi=dpi,
        )
        _publish(staged, output)
    finally:
        staged.unlink(missing_ok=True)
        staging_directory.rmdir()
    return output


def distort_tiff(
    source_tiff: Path,
    output_tiff: Path,
    *,
    profile: str,
    seed: int,
    output_dpi: int = 1200,
) -> Path:
    """Apply one named profile to one 600-dpi RGB TIFF."""
    actual_seed = _seed("seed", seed)
    dpi = _output_dpi(output_dpi)
    source = Path(source_tiff)
    output = Path(output_tiff)
    if not source.is_file():
        raise FileNotFoundError(source)
    if profile not in PROFILES:
        raise ValueError(
            f"unknown profile {profile!r}; expected one of "
            + ", ".join(PROFILES)
        )

    if profile in SYNTHETIC_PROFILES:
        with Image.open(source) as image:
            width, height = image.size
        parameters = profile_parameters(
            profile, actual_seed, width=width, height=height)
        return distort_with_parameters(
            source,
            output,
            parameters,
            output_dpi=dpi,
        )

    if dpi != 1200:
        raise ValueError(f"{profile} emits only 1200 dpi")
    writer = (
        _write_hp_m281_flatbed_cmy if profile == "hp-m281-flatbed-cmy"
        else _write_hp_m281_flatbed_k)
    staging_directory, staged = _staging_path(output)
    try:
        writer(source, staged, seed=actual_seed)
        _publish(staged, output)
    finally:
        staged.unlink(missing_ok=True)
        staging_directory.rmdir()
    return output


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Transform one 600-dpi RGB TIFF into one 1200- or 4800-dpi "
            "scan TIFF (RGB, or grayscale for hp-m281-flatbed-k), using "
            "an optional profile or explicit effects."
        ),
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--profile",
        choices=PROFILES,
        help="optional distortion shortcut",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="unsigned 64-bit realization selector (default: 0)",
    )
    parser.add_argument(
        "--output-dpi",
        type=int,
        choices=OUTPUT_DPIS,
        default=1200,
        help="output scan density for synthetic profiles (default: 1200)",
    )
    parser.add_argument(
        "--shear",
        type=float,
        nargs=2,
        metavar=("X", "Y"),
        help="set x-by-y and y-by-x shear",
    )
    parser.add_argument(
        "--translate",
        type=float,
        nargs=2,
        metavar=("X", "Y"),
        help="set source translation in 600-dpi printer dots",
    )
    parser.add_argument(
        "--margin",
        type=int,
        nargs=2,
        metavar=("Y", "X"),
        help="set white canvas margin in printer dots",
    )
    parser.add_argument(
        "--crop",
        type=int,
        nargs=4,
        metavar=("Y", "X", "HEIGHT", "WIDTH"),
        help="set crop rectangle in printer dots",
    )
    parser.add_argument(
        "--dropout",
        type=float,
        help="set per-ink-dot dropout probability",
    )
    parser.add_argument(
        "--speckle",
        type=float,
        help="set per-paper-dot speckle probability",
    )
    parser.add_argument(
        "--speckle-rgb",
        type=int,
        nargs=3,
        metavar=("R", "G", "B"),
        help="set synthetic speckle color",
    )
    parser.add_argument(
        "--blur",
        type=float,
        help="set Gaussian blur radius in 600-dpi printer dots",
    )
    parser.add_argument(
        "--noise-rgb",
        type=float,
        nargs=3,
        metavar=("R", "G", "B"),
        help="set output RGB noise standard deviations",
    )
    arguments = parser.parse_args(argv)
    override_names = (
        "shear",
        "translate",
        "margin",
        "crop",
        "dropout",
        "speckle",
        "speckle_rgb",
        "blur",
        "noise_rgb",
    )
    has_overrides = any(
        getattr(arguments, name) is not None for name in override_names)
    if has_overrides and arguments.profile in MEASURED_PROFILES:
        parser.error(
            "explicit distortion options cannot be combined with "
            f"{arguments.profile}"
        )
    if arguments.profile in MEASURED_PROFILES:
        output = distort_tiff(
            arguments.source,
            arguments.output,
            profile=arguments.profile,
            seed=arguments.seed,
            output_dpi=arguments.output_dpi,
        )
    else:
        if arguments.profile is None:
            parameters = DistortionParameters(seed=arguments.seed)
        else:
            with Image.open(arguments.source) as image:
                width, height = image.size
            parameters = profile_parameters(
                arguments.profile,
                arguments.seed,
                width=width,
                height=height,
            )
        parameters = _profile_overrides(parameters, arguments)
        output = distort_with_parameters(
            arguments.source,
            arguments.output,
            parameters,
            output_dpi=arguments.output_dpi,
        )
    label = arguments.profile or "plain"
    print(f"{output} ({label}, {arguments.output_dpi} dpi)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
