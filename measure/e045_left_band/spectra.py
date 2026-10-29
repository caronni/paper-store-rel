"""e045 — the engine's screen families per x slice of a cell field (the e043 stipple instrument at a slice width
of the caller's choosing).

Per slice: the field's interior (inset INSET_X, INSET_Y printed dots) between the slice's x edges, cropped
scan-aligned through the page affine (measure/cmy_probe/stipples.crop's corner rule), per ink density
(C = 255 - R, M = 255 - G, Y = 255 - B) the Hann-windowed power spectrum, every family's locally whitened peak
(stipples.peak_local), the cell lattice's harmonics excluded at the page rotation
(checkerboards.lattice_exclude).  Reported: the 212 lpi yellow stipple in the Y density and, as the lattice
control, in the C density; the 165 and 188 lpi screens as the maximum over the three densities; the two
unexpected families (dots160, lines196) as the slice's noise.  Noise of a 9.3 mm slice on sheet 3: 5-16 in the C
density (043.6); a 5 mm slice has about half the bins.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from measure.cmy_probe.checkerboards import lattice_exclude
from measure.cmy_probe.stipples import CHANNELS, FAMILIES, _grid, peak_local, power
from measure.e041_probe_readout import Scan

DOT_MM = 25.4 / 600.0
INSET_X, INSET_Y = 8, 8          # printed dots


def slice_families(scan: Scan, A: np.ndarray, field: tuple[float, float, float, float], edges_mm: np.ndarray,
                   cell_dots: int, sub: int, rot_deg: float) -> list[dict[str, Any]]:
    """field = (x0, y0, x1, y1) printed dots of the cell field; one record per slice [edges[i], edges[i+1])."""
    x0, y0, x1, y1 = field
    ya, yb = (y0 + INSET_Y) * DOT_MM, (y1 - INSET_Y) * DOT_MM
    small = ((rot_deg + 45) % 90) - 45
    out = []
    for a, b in zip(edges_mm[:-1], edges_mm[1:]):
        xa, xb = max(a, (x0 + INSET_X) * DOT_MM), min(b, (x1 - INSET_X) * DOT_MM)
        if xb - xa < 1.0:
            out.append({})
            continue
        P = A @ np.array([[xa, xb, xa, xb], [ya, ya, yb, yb], [1, 1, 1, 1]], float)
        r0, r1 = int(round(P[1].min())), int(round(P[1].max()))
        c0, c1 = int(round(P[0].min())), int(round(P[0].max()))
        patch = scan.img[r0:r1, c0:c1, :3].astype(np.float64) * scan.scale255
        h, w = patch.shape[:2]
        R, ang, _ = _grid(h, w)
        ex = lattice_exclude((h, w), cell_dots * sub, rot_deg=small)
        fam = {}
        for k, ch in enumerate(CHANNELS):
            Pw = power(255.0 - patch[..., k])
            fam[ch] = {f: peak_local(Pw, R, ang, *FAMILIES[f], dpi=scan.dpi, exclude=ex) for f in FAMILIES}
        out.append({"Y213_Y": fam["Y"]["Y213@45"], "Y213_C": fam["C"]["Y213@45"],
                    "s165_max": float(np.nanmax([fam[c]["165@14"] for c in CHANNELS])),
                    "s188_max": float(np.nanmax([fam[c]["188@71/19"] for c in CHANNELS])),
                    "noise_max": float(np.nanmax([fam[c][f] for c in CHANNELS for f in ("dots160@42", "lines196@90")])),
                    "families": fam})
    return out
