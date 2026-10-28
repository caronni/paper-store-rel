"""Layer 2 — geometric synchronization (DESIGN.md §5.1).

Implemented: single global lattice estimate (pitch + rotation) from FFT peaks of the
*gradient-magnitude* map. The nonlinearity is essential: random solid cells are
NRZ-like, and an NRZ spectrum has a NULL (not a line) at the symbol rate — edge
detection regenerates the discrete lattice line, the 2-D analog of a squaring
timing-recovery loop. (This was caught by tests/test_roundtrip_sim.py: the raw-FFT
version locked onto paper mottle instead.) Gradient also high-passes away mottle and
banding for free.

TODO(M1): tile-wise estimates stitched into a thin-plate-spline warp field,
coarse-to-fine refinement, resampling to the cell grid, and hand-off to the pilot
window decode (pilots.py) for absolute addressing.
"""
from __future__ import annotations

import numpy as np


def estimate_lattice(scan: np.ndarray, pitch_px_nominal: float | None = None,
                     search_octaves: float = 1.0) -> dict:
    """Estimate cell pitch (scan px) and lattice rotation from a scan patch.

    pitch_px_nominal band-limits the peak search to +/- search_octaves around
    the format's nominal pitch (cell_dots * scan_oversample — public constants
    per DESIGN.md §5.1: the decoder looks for the cell fundamental near
    ±400 cyc/in, it does not search octaves blindly). Without it the strongest
    peak anywhere above 0.01 cyc/px wins, which the measured channel's mottle
    can beat at low frequency.

    Returns {"pitch_px": float, "angle_rad": float, "contrast": float} with
    angle folded into [0, pi/2). contrast = peak magnitude over the median
    nonzero in-band magnitude — a dimensionless lattice-line confidence
    (acquire-v2 wide-band pitch search ranks probe nominals by it; ~1 means
    no line, kcell pages at a true probe measure >>1).
    """
    f = scan.astype(np.float64)
    gy, gx = np.gradient(f)
    g = np.hypot(gy, gx)
    g -= g.mean()
    wy = np.hanning(g.shape[0])[:, None]
    wx = np.hanning(g.shape[1])[None, :]
    F = np.abs(np.fft.rfft2(g * wy * wx))

    fy = np.fft.fftfreq(g.shape[0])[:, None]
    fx = np.fft.rfftfreq(g.shape[1])[None, :]
    fr = np.hypot(fy, fx)
    F[fr < 0.01] = 0.0  # kill residual DC/low-frequency content (period > 100 px)
    if pitch_px_nominal is not None:
        f0 = 1.0 / pitch_px_nominal
        band = 2.0 ** search_octaves
        F[(fr < f0 / band) | (fr > f0 * band)] = 0.0

    iy, ix = np.unravel_index(np.argmax(F), F.shape)
    peak_fy = float(fy[iy, 0])
    peak_fx = float(fx[0, ix])
    peak_fr = float(np.hypot(peak_fy, peak_fx))
    if peak_fr <= 0:
        raise ValueError("no lattice line found")
    band_vals = F[F > 0]
    if band_vals.size > 65536:          # full-page spectra: subsampled
        band_vals = band_vals[::band_vals.size // 65536]  # median is enough
    med = float(np.median(band_vals)) if band_vals.size else 0.0
    contrast = float(F[iy, ix] / med) if med > 0 else 0.0
    return {"pitch_px": 1.0 / peak_fr,
            "angle_rad": float(np.arctan2(peak_fy, peak_fx)) % (np.pi / 2),
            "contrast": contrast}
