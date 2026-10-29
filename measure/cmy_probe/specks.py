"""Sparse foreign dots in a bar — the owner's "C mottling" (e043 sheet 2, 2026-10-11 night).

The five screen families (stipples.py) see a developed lattice; a toner the pipeline adds at a few per cent
develops as SPARSE dots on that lattice, and the whitened peak stays at noise while the eye sees specks
(magenta at R 236–238: 6–18 cyan specks per mm², the 160 lpi family at 2–19).  Per ink density (C = 255 - R,
M = 255 - G, Y = 255 - B) of the bar's interior at the scan's resolution: the high-pass residual (minus a
SMOOTH_MM Gaussian), its robust sigma (1.4826 MAD), the skew of the standardised residual, the 99.9th
percentile in sigmas, and the specks per mm² = local maxima (9 x 9 px) above SPECK_SIGMAS sigmas.  Measured
on sheet 2 at 2400 dpi: paper and yellow bars 0–1.8 specks/mm², skew within ±0.3; the cyan specks 6–18/mm²,
skew +0.6 to +3.7.  A bar's speck figure is the maximum over its FOREIGN densities (the toner's own density
is its own texture; a control's three densities are all foreign); SPECKS_MAX is the verdict's bar.
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

SMOOTH_MM = 0.3                 # the high-pass: paper texture and shading below, specks above
SPECK_SIGMAS = 4.0              # a speck: a local maximum this many robust sigmas over the median
SPECKS_MAX = 3.0                # per mm²; paper 0–1.8 on sheet 2, foreign dots 6–18
DENSITIES = ("C", "M", "Y")
OWN = {"C": "C", "M": "M", "Y": "Y"}


def density_specks(dens: np.ndarray, px_per_mm: float) -> dict[str, float]:
    r = dens - ndimage.gaussian_filter(dens, SMOOTH_MM * px_per_mm)
    med = float(np.median(r))
    mad = 1.4826 * float(np.median(np.abs(r - med))) + 1e-9
    z = (r - med) / mad
    peaks = (r == ndimage.maximum_filter(r, size=9)) & (z > SPECK_SIGMAS)
    area_mm2 = r.size / px_per_mm ** 2
    return {"sigma": mad, "skew": float((z ** 3).mean()), "p999_sigmas": float(np.percentile(z, 99.9)),
            "specks_per_mm2": float(peaks.sum() / area_mm2)}


def specks(patch: np.ndarray, px_per_mm: float) -> dict[str, dict[str, float]]:
    """{density: metrics} for one RGB patch (float, 0-255 scale)."""
    return {nm: density_specks(255.0 - patch[..., k], px_per_mm) for k, nm in enumerate(DENSITIES)}


def foreign_max(sp: dict[str, dict[str, float]], toner: str | None) -> tuple[str, float]:
    """(density, specks per mm²) of the worst foreign density; every density is foreign to a control."""
    own = OWN.get(toner or "", None)
    cands = [(nm, m["specks_per_mm2"]) for nm, m in sp.items() if nm != own]
    return max(cands, key=lambda t: t[1])
