"""The declared-pitch line test: is the declared lattice on this crop?

The survey's blind vote (`plugins/survey._pitch_vote`) asks which pitch
a crop carries.  This module asks the narrower question a vote FINER
than the declared row raises (2026-10-02, the c2-at-4800 harmonic): is
there a lattice at exactly the declared pitch, two perpendicular lines
of it, at all?  A c2 sheet at 4800 dpi carries its 16 px cell line and
the engine's 8 px dot line; where the 16 px line sits under the vote's
per-band floor the 8 px line wins, snaps a whole class finer and used to
refuse the run, although the declared lattice was there all along.

One ring of the same gradient-magnitude spectrum the vote builds, at
the declared pitch alone: no band search, no ranking across bands.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np

#: 4% covers scanner scale plus spectral measurement error (e021 §7).
#: Adjacent candidate pitches are >= 25% apart, so a measurement inside
#: one 4% shell is nearest to that pitch unambiguously, and refusing an
#: out-of-set measurement is correct: no row spells that lattice.  The
#: survey's snap and the declared-line ring below are that one shell.
C_SNAP_TOLERANCE: float = 0.04
RADIAL_FLOOR: float = 0.01

#: Fewer ring bins than this is a scrap too small to judge: no verdict.
LINE_MIN_BINS: int = 64
#: A printed lattice is two perpendicular line families; one line alone
#: is a screen or a texture, not the declared grid.
LINE_PARTNER_DEG: float = 3.0
#: PROVISIONAL, calibrated for LINE_WINDOW_PX below.  Measured
#: 2026-10-02/03 on the Canon iR-ADV's 4800 captures (c2, one engine, one
#: scanner), five 4096 windows per capture: sheet H's declared line
#: 11.0-20.4, sheet G's 19.9-25.2; empty rings (20, 24, 40 px, and the
#: lattice's own 2P and 4P) at most 4.85.  At 2048 the same windows read
#: 5.7-11.5 against a null of at most 3.72 (136 rings), which is why
#: the test reads the larger window.  A region smaller than the window
#: is read whole and can only come out more conservative: sheet H at
#: 2048 reads 5.7-6.4 and would refuse; `--dpi-force` is that door.
#: A null to recalibrate on the next engine, not a frozen gate.
LINE_FLOOR: float = 7.0
#: The window the test reads, larger than the vote's MEASURE_WINDOW_PX:
#: a line's contrast grows with the periods under the window while an
#: empty ring's grows only with the log of its bins (sheet H's capture
#: a, centred windows 1024 / 1536 / 2048 / 3072 / 4096 px: 2.79 / 4.81
#: / 5.74 / 8.36 / 13.60; G's: 6.26 / 11.12 / 14.37 / 15.71 / 24.20).
#: The test runs only on a contradicted vote, so the one larger FFT is
#: free.
LINE_WINDOW_PX: int = 4096


@dataclass(frozen=True)
class LineVerdict:
    """The declared ring's weaker perpendicular line over its median."""
    pitch_px: float
    contrast: float

    @property
    def present(self) -> bool:
        return self.contrast >= LINE_FLOOR


def declared_line(image: np.ndarray, pitch_px: float) -> LineVerdict | None:
    f = np.asarray(image, np.float64)
    if min(f.shape, default=0) < 3:
        return None
    # The printed field is non-return-to-zero, so the cell comb lives in
    # the gradient magnitude, not in the image (survey._estimate_lattice).
    gy, gx = np.gradient(f)
    magnitude = np.hypot(gy, gx)
    magnitude -= magnitude.mean()
    window_y = np.hanning(magnitude.shape[0])[:, None]
    window_x = np.hanning(magnitude.shape[1])[None, :]
    spectrum = np.abs(np.fft.rfft2(magnitude * window_y * window_x))
    fy = np.fft.fftfreq(magnitude.shape[0])[:, None]
    fx = np.fft.rfftfreq(magnitude.shape[1])[None, :]
    radial = np.hypot(fy, fx)
    centre = 1.0 / float(pitch_px)
    ring = ((radial >= centre * (1.0 - C_SNAP_TOLERANCE))
            & (radial <= centre * (1.0 + C_SNAP_TOLERANCE))
            & (radial >= RADIAL_FLOOR))
    if int(ring.sum()) < LINE_MIN_BINS:
        return None
    angle = np.degrees(np.arctan2(fy, fx))
    loud = np.where(ring, spectrum, -1.0)
    iy, ix = np.unravel_index(int(np.argmax(loud)), loud.shape)
    perpendicular = angle[iy, ix] + 90.0
    off = np.abs((angle - perpendicular + 90.0) % 180.0 - 90.0)
    partner = ring & (off <= LINE_PARTNER_DEG)
    # A ring too coarse to hold the perpendicular arc cannot test the
    # second family, which is no verdict, never a pass.
    if not partner.any():
        return None
    median = float(np.median(spectrum[ring]))
    weaker = min(float(spectrum[iy, ix]), float(spectrum[partner].max()))
    return LineVerdict(pitch_px=1.0 / float(radial[iy, ix]),
                       contrast=weaker / median if median > 0 else 0.0)


def verdicts(crops: Iterable[np.ndarray | None], pitch_px: float,
             ) -> tuple[LineVerdict, ...]:
    """One verdict per crop that can give one: a missing crop and a
    ring too small to judge both drop out rather than count."""
    read = (declared_line(crop, pitch_px) for crop in crops
            if crop is not None)
    return tuple(verdict for verdict in read if verdict is not None)


def judge(verdicts: Sequence[LineVerdict]) -> tuple[bool, str]:
    """Present in a strict majority of the regions that gave a verdict,
    and at least one did; the detail names the loudest line and the count."""
    if not verdicts:
        return False, ("declared lattice untested: no region large enough "
                       "to judge")
    best = max(verdicts, key=lambda verdict: verdict.contrast)
    present = sum(1 for verdict in verdicts if verdict.present)
    detail = (f"line {best.contrast:.1f} at {best.pitch_px:.1f} px, present "
              f"in {present} of {len(verdicts)} regions")
    if 2 * present > len(verdicts):
        return True, f"declared lattice present: {detail}"
    return False, f"declared lattice absent: {detail}"
