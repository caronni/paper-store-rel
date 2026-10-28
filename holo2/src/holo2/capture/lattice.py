"""Local lattice measurement used by the E021 survey (carried leaf).

Copied unchanged from ``src/holo/receive/lattice.py`` under the holo2
firewall (copy-and-adapt, never import).  :mod:`holo2.capture.survey` needs
it for the printed-cell-pitch vote, so it travels with the survey carry
even though DESIGN §13 lists it only implicitly.

The printed field is non-return-to-zero: its raw image spectrum has a null at
the cell rate.  Measuring the gradient magnitude first regenerates the cell
comb.  This production-local implementation follows ``paperholo.sync`` and
``paperholo.scannorm.measure_cell_pitch`` and is pinned to them by
source-local differential qualification.

All transforms are local (at most :data:`MEASURE_WINDOW_PX` square).  The
module neither opens captures nor normalizes intensity; callers pass a 2-D
crop from :mod:`holo2.capture.scan`.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


PITCH_PROBES_PX = (2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 16.0, 24.0, 32.0)
"""Half-octave-ish probe ladder qualified by E021/E022."""

CONTRAST_FLOOR = 30.0
"""Per-band peak/median credibility floor from acquire-v2 qualification."""

MEASURE_WINDOW_PX = 2048
"""Maximum local FFT side; provides 64 periods at the widest probe."""

RATIO_TOLERANCE = 0.08
"""Relative tolerance used to recognize harmonics of one fundamental."""

DEDUPE_TOLERANCE = 0.02


class LatticeNotFound(ValueError):
    """The crop contains no credible line in the requested pitch bands."""

    def __init__(self, message: str, *, pitch_px: float | None = None) -> None:
        super().__init__(message)
        self.pitch_px = pitch_px


@dataclass(frozen=True)
class LatticeEstimate:
    """One band-limited gradient-comb measurement."""

    pitch_px: float
    angle_rad: float
    contrast: float


@dataclass(frozen=True)
class PitchMeasurement:
    """Fundamental selected from all credible spectral lines.

    ``candidates`` records every usable probe result; ``strong`` contains
    de-duplicated lines above :data:`CONTRAST_FLOOR`.  They are retained so
    E021 can map all credible lines to integer print-cell hypotheses instead
    of trusting the strongest harmonic.
    """

    pitch_px: float
    angle_rad: float
    contrast: float
    candidates: tuple[tuple[float, float], ...]
    strong: tuple[tuple[float, float], ...]


def estimate_lattice(
    crop: np.ndarray,
    *,
    pitch_px_nominal: float | None = None,
    search_octaves: float = 1.0,
) -> LatticeEstimate:
    """Estimate cell pitch and mod-90 rotation from a local 2-D crop.

    The search is normally band-limited around a probe.  An unrestricted
    search remains available for a caller that already controls the crop,
    but production survey/geometry code uses explicit probes.
    """
    image = np.asarray(crop)
    if image.ndim != 2:
        raise ValueError(f"lattice crop must be 2-D, got {image.shape}")
    if min(image.shape, default=0) < 3:
        raise LatticeNotFound("lattice crop is too small")
    if pitch_px_nominal is not None and pitch_px_nominal <= 0:
        raise ValueError("pitch_px_nominal must be positive")
    if search_octaves <= 0:
        raise ValueError("search_octaves must be positive")

    # float64 is intentional here.  Phase/frequency resolution governs an
    # absolute geometry decision, while the crop is bounded to 2048 upstream.
    f = image.astype(np.float64)
    gy, gx = np.gradient(f)
    magnitude = np.hypot(gy, gx)
    magnitude -= magnitude.mean()
    window_y = np.hanning(magnitude.shape[0])[:, None]
    window_x = np.hanning(magnitude.shape[1])[None, :]
    spectrum = np.abs(np.fft.rfft2(magnitude * window_y * window_x))

    fy = np.fft.fftfreq(magnitude.shape[0])[:, None]
    fx = np.fft.rfftfreq(magnitude.shape[1])[None, :]
    radial = np.hypot(fy, fx)
    eligible = radial >= 0.01  # reject periods longer than 100 pixels
    if pitch_px_nominal is not None:
        centre = 1.0 / pitch_px_nominal
        band = 2.0**search_octaves
        eligible &= (radial >= centre / band) & (radial <= centre * band)

    spectrum[~eligible] = 0.0
    iy, ix = np.unravel_index(int(np.argmax(spectrum)), spectrum.shape)
    peak_fy = float(fy[iy, 0])
    peak_fx = float(fx[0, ix])
    peak_frequency = float(np.hypot(peak_fy, peak_fx))
    if peak_frequency <= 0:
        raise LatticeNotFound("no lattice line found")

    # The qualified contrast denominator excludes exact zero bins after the
    # band mask.  Including them can turn sparse spectra into false lines.
    in_band = spectrum[spectrum > 0]
    if in_band.size > 65_536:
        stride = in_band.size // 65_536
        in_band = in_band[::stride]
    median = float(np.median(in_band)) if in_band.size else 0.0
    contrast = float(spectrum[iy, ix] / median) if median > 0 else 0.0
    return LatticeEstimate(
        pitch_px=1.0 / peak_frequency,
        angle_rad=float(np.arctan2(peak_fy, peak_fx)) % (np.pi / 2.0),
        contrast=float(contrast),
    )


def measure_cell_pitch(
    crop: np.ndarray,
    *,
    probes_px: tuple[float, ...] = PITCH_PROBES_PX,
) -> PitchMeasurement:
    """Measure the largest harmonic-consistent credible lattice period.

    Per-probe contrasts are not comparable because every band has a distinct
    noise floor, and harmonics can be stronger than the cell fundamental.
    Selection therefore starts at the largest credible pitch and accepts the
    first line for which every other credible line is an integer division.
    This is the known-best E021/E022 rule, not a strongest-peak shortcut.
    """
    image = np.asarray(crop)
    if image.ndim != 2:
        raise ValueError(f"pitch crop must be 2-D, got {image.shape}")
    if any(probe <= 0 for probe in probes_px):
        raise ValueError("pitch probes must be positive")

    if min(image.shape, default=0) > MEASURE_WINDOW_PX:
        cy, cx = image.shape[0] // 2, image.shape[1] // 2
        half = MEASURE_WINDOW_PX // 2
        image = np.ascontiguousarray(
            image[cy - half : cy + half, cx - half : cx + half],
            np.float64,
        )
    # NOTE (2026-07-30): the period-count contrast law (128 periods -> ~15,
    # 512 -> ~48) means coarse probes are starved here; a naive 512*probe
    # window measured QUADRATIC cost (16k-px FFTs). The affordable form is
    # decimate-then-measure at a canonical footing (scannorm doctrine) —
    # workplan residue; placement rides the declared-pitch fallback.
    raw: list[tuple[float, float, float]] = []
    for probe in probes_px:
        if min(image.shape, default=0) < 8.0 * probe:
            continue
        try:
            estimate = estimate_lattice(image, pitch_px_nominal=float(probe))
        # A single failed probe is historically a miss, not a survey error.
        except Exception:
            continue
        raw.append((estimate.pitch_px, estimate.contrast, estimate.angle_rad))

    strong: list[tuple[float, float, float]] = []
    for pitch, contrast, angle in raw:
        if contrast < CONTRAST_FLOOR:
            continue
        for index, (prior_pitch, prior_contrast, _) in enumerate(strong):
            if abs(pitch / prior_pitch - 1.0) < DEDUPE_TOLERANCE:
                if contrast > prior_contrast:
                    strong[index] = (pitch, contrast, angle)
                break
        else:
            strong.append((pitch, contrast, angle))

    if not strong:
        best = max(raw, key=lambda candidate: candidate[1], default=None)
        if best is None:
            raise LatticeNotFound("no lattice line found at any probe pitch")
        raise LatticeNotFound(
            "no credible lattice line at any probe pitch "
            f"(best contrast {best[1]:.1f} at {best[0]:.2f} px; "
            f"floor {CONTRAST_FLOOR:g})",
            pitch_px=best[0],
        )

    strong.sort(key=lambda candidate: -candidate[0])
    chosen: tuple[float, float, float] | None = None
    for pitch, contrast, angle in strong:
        if all(
            abs(pitch / other_pitch - max(1.0, round(pitch / other_pitch)))
            <= RATIO_TOLERANCE
            * max(1.0, round(pitch / other_pitch))
            for other_pitch, _, _ in strong
        ):
            chosen = (pitch, contrast, angle)
            break
    if chosen is None:
        # A mixed spectrum cannot name a fundamental.  Preserve the old
        # courtesy fallback; downstream BCH validation still owns truth.
        chosen = max(strong, key=lambda candidate: candidate[1])

    pitch, contrast, angle = chosen
    if angle > np.pi / 4.0:
        angle -= np.pi / 2.0
    return PitchMeasurement(
        pitch_px=float(pitch),
        angle_rad=float(angle),
        contrast=float(contrast),
        candidates=tuple((float(p), float(c)) for p, c, _ in raw),
        strong=tuple((float(p), float(c)) for p, c, _ in strong),
    )
