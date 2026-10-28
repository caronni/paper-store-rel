"""W9/W10 — capture-degradation checks must separate honest from degraded.

e031/W9: the `compression` check failed EVERY capture ever taken, across two
engines, on provably uncompressed files — the ≥1.0-count noise floor sat
above the scanner's real floor (honest captures: 0.46–0.84 counts).  The
floor was recalibrated to 0.30 from measurement with positive AND negative
controls.

W10 replaced the blank-paper spectral advisory (knee patch-unstable,
flatness fires on a legitimate averaging mode) with structured-feature
checks: a phase-invariant comb detector (JPEG at ANY internal resolution and
phase), and slanted-edge overshoot (capture sharpening — the one smoothing
signature whose attribution is clean on a single scan, because print physics
cannot overshoot its own plateaus).

A gate that has only ever been seen to fail is no more validated than one
that has only ever been seen to pass, so these tests pin BOTH directions.
"""
import io

import numpy as np
from PIL import Image
from scipy import ndimage

from holo.characterize.diagnostics import (
    blockiness,
    blockiness_comb,
    highpass_noise,
    level_occupancy,
    slanted_edge_mtf50,
)
from holo.characterize.summarize_physical import (
    SCANNER_BLOCKINESS_MAX,
    SCANNER_COMB_MAX,
    SCANNER_NOISE_MIN_8BIT,
    SCANNER_OVERSHOOT_MAX,
)

SIDE = 512


def _honest_capture(seed: int = 0, noise_counts: float = 0.7) -> np.ndarray:
    """Blank paper as a real scanner delivers it.

    Band-limited paper texture (the optics roll off well below Nyquist) plus
    WHITE per-pixel sensor noise added afterwards — the sensor sits behind
    the lens, so its noise is not band-limited even though the signal is.
    """
    rng = np.random.default_rng(seed)
    texture = ndimage.gaussian_filter(rng.normal(0.0, 1.0, (SIDE, SIDE)), 6.0)
    texture *= 0.012 / max(float(texture.std()), 1e-9)
    sensor = rng.normal(0.0, noise_counts / 255.0, (SIDE, SIDE))
    page = 0.93 + texture + sensor
    return np.clip(np.rint(page * 255.0) / 255.0, 0.0, 1.0)


def _jpeg(image: np.ndarray, quality: int) -> np.ndarray:
    buffer = io.BytesIO()
    Image.fromarray((image * 255.0).astype(np.uint8)).save(
        buffer, "JPEG", quality=quality
    )
    return np.asarray(
        Image.open(io.BytesIO(buffer.getvalue())), np.float64
    ) / 255.0


def _counts(image: np.ndarray) -> float:
    return highpass_noise(image) * 255.0


# ---------------------------------------------------------------- noise floor

def test_honest_capture_clears_the_noise_floor() -> None:
    """The regression that matters: a good capture must not be refused."""
    for seed in range(4):
        page = _honest_capture(seed)
        assert _counts(page) >= SCANNER_NOISE_MIN_8BIT, (seed, _counts(page))
        assert blockiness(page) < SCANNER_BLOCKINESS_MAX


def test_gaussian_blur_is_caught_by_the_noise_floor() -> None:
    """Blur leaves blockiness untouched — the noise floor is what catches it."""
    page = _honest_capture()
    for degraded, label in (
        (ndimage.gaussian_filter(page, 0.7), "gaussian 0.7"),
        (ndimage.gaussian_filter(page, 1.5), "gaussian 1.5"),
    ):
        assert _counts(degraded) < SCANNER_NOISE_MIN_8BIT, label
        assert blockiness(degraded) < SCANNER_BLOCKINESS_MAX, label


def test_median_filtering_is_only_caught_on_a_quiet_capture() -> None:
    """KNOWN GAP, pinned deliberately rather than tuned away.

    A 3x3 median roughly HALVES the high-pass noise (measured: real capture
    0.461 -> 0.226; a noisier synthetic 0.70 -> 0.32).  An absolute floor
    therefore catches median filtering only when the capture's own floor was
    already modest.  Blockiness does not see it either.  Recorded in
    CHARACTERIZE-WORKPLAN W9/W10 as an open weakness; a ratio-based test
    needs a per-scanner baseline the instrument does not carry.
    """
    quiet = _honest_capture(noise_counts=0.46)
    noisy = _honest_capture(noise_counts=0.90)
    caught = _counts(ndimage.median_filter(quiet, 3))
    missed = _counts(ndimage.median_filter(noisy, 3))
    assert caught < SCANNER_NOISE_MIN_8BIT, caught
    assert missed >= SCANNER_NOISE_MIN_8BIT, missed
    assert caught / _counts(quiet) < 0.75
    assert missed / _counts(noisy) < 0.75


def test_the_floor_sits_in_the_measured_empty_band() -> None:
    """0.30 counts separates two measured clusters: smoothed 0.079-0.226,
    honest 0.46-0.84.  The constant must stay inside that gap with margin."""
    assert 0.226 < SCANNER_NOISE_MIN_8BIT < 0.46
    assert SCANNER_NOISE_MIN_8BIT / 0.226 > 1.3
    assert 0.46 / SCANNER_NOISE_MIN_8BIT > 1.5


# ------------------------------------------------------------- JPEG/blocking

def test_jpeg_at_delivered_resolution_is_caught_by_blockiness() -> None:
    """The legacy aligned 8-px limb still earns its keep."""
    page = _honest_capture()
    for quality in (95, 75, 50):
        assert blockiness(_jpeg(page, quality)) >= SCANNER_BLOCKINESS_MAX, (
            quality
        )


def test_comb_is_phase_invariant_where_the_aligned_limb_is_not() -> None:
    """JPEG seams at an arbitrary phase must still be caught.

    Cropping the decoded JPEG at a 3-px offset moves every seam off the
    8-px grid the aligned detector assumes.
    """
    page = _honest_capture()
    shifted = _jpeg(page, 75)[3:-5, 3:-5]
    comb = blockiness_comb(shifted)
    assert comb is not None
    assert comb["max"] >= SCANNER_COMB_MAX, comb
    # a comb at 8 aliases into every multiple, so argmax may land on any of
    # them — the fundamental itself must be elevated
    assert comb["periods"]["8"] >= SCANNER_COMB_MAX, comb


def test_comb_catches_internal_low_resolution_jpeg() -> None:
    """The hole the fixed-8px limb cannot see: compress at half resolution,
    interpolate back up — seams land at 16 px, at whatever phase."""
    page = _honest_capture()
    half = page[::2, ::2]
    compressed = _jpeg(half, 60)
    upsampled = np.asarray(Image.fromarray(
        (compressed * 255.0).astype(np.uint8)
    ).resize((SIDE, SIDE), Image.BILINEAR), np.float64) / 255.0
    comb = blockiness_comb(upsampled[5:, 2:])
    assert comb is not None
    assert comb["max"] >= SCANNER_COMB_MAX, comb
    assert comb["periods"]["16"] >= SCANNER_COMB_MAX, comb


def test_comb_is_quiet_on_honest_captures() -> None:
    for seed in range(4):
        comb = blockiness_comb(_honest_capture(seed))
        assert comb is not None
        assert comb["max"] < SCANNER_COMB_MAX, (seed, comb)


# ---------------------------------------------------------------- sharpening

def _edge_page(sharpen: float = 0.0, seed: int = 0) -> np.ndarray:
    """A 5-degree slanted edge through optics blur, optionally unsharp-masked.

    Ink on the left (high density -> low reflectance).  Returned as an RGB
    reflectance crop, matching what the probe pipeline feeds the diagnostic.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.indices((SIDE, SIDE), dtype=np.float64)
    distance = (xx - SIDE / 2) + np.tan(np.radians(5.0)) * (yy - SIDE / 2)
    reflectance = np.where(distance > 0, 0.92, 0.18)
    blurred = ndimage.gaussian_filter(reflectance, 3.0)
    if sharpen > 0.0:
        blurred = blurred + sharpen * (
            blurred - ndimage.gaussian_filter(blurred, 4.0)
        )
    blurred = blurred + rng.normal(0.0, 0.003, (SIDE, SIDE))
    # density() expects reflectance in 0..1 (the probe pipeline's scale)
    return np.clip(blurred, 0.01, 1.0)[..., None] * np.ones(3)


def test_clean_edge_has_no_overshoot() -> None:
    result = slanted_edge_mtf50(_edge_page(), 4800.0, 4800.0, 5.0)
    assert result["resolved"], result
    assert result["overshoot_fraction"] < SCANNER_OVERSHOOT_MAX, result


def test_unsharp_masking_is_caught_as_overshoot() -> None:
    """Print physics cannot overshoot its own plateaus; sharpening can."""
    result = slanted_edge_mtf50(_edge_page(sharpen=1.0), 4800.0, 4800.0, 5.0)
    assert result["resolved"], result
    assert result["overshoot_fraction"] >= SCANNER_OVERSHOOT_MAX, result


# ------------------------------------------------------------- posterisation

def test_level_occupancy_is_recorded_as_a_null_detector() -> None:
    """It fired on nothing real.  Pinned so nobody re-gates it; kept only
    because it is the sole probe for posterisation, which it does catch."""
    page = _honest_capture()
    assert level_occupancy(page)["interior_gaps"] == 0
    for quality in (95, 75, 50):
        assert level_occupancy(_jpeg(page, quality))["interior_gaps"] == 0
    posterised = np.rint(page * 32.0) / 32.0
    assert level_occupancy(posterised)["interior_gaps"] > 0
