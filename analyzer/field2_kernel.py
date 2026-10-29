"""`field2`'s kernel smoother and its bound — the analyzer's own copy.

ADOPTED 2026-09-12 (PAGE-FIELD-PLAN A2).  These four constants and three
functions were `holo.receiver.lib.plane_field`'s, and the receiver
retired the estimator that used them: since the PAGE-FIELD line (design
of record `docs/PAGE-FIELD-DESIGN.md` v0.6) the production field is one
penalised robust solve per printed page whose unmeasured region is
governed by a PRIOR — curvature, gradient and a pull toward zero over
physical lengths — and not by a kernel and a bound.  Nothing in that
receiver smooths a field or clamps one any more (I6, I8); the names
survived there for this package's readers — `field2`, and
`arms.smooth_offsets` until A3 retired the `smooth` arm on 2026-09-12 —
with a comment saying so.  This module is now the SOLE carrier in this
package, so the receiver may delete its copies (the hand-back
`PAGE-FIELD-PLAN.md` A8 lists: `BANDWIDTH_TILES`, `KERNEL_TRUNCATION`,
`TWICING_PASSES`, `MAX_DELTA_DOTS`, `gaussian_kernel`, `smooth`,
`clamp`).

VERBATIM, and that is the point.  The bodies below are the receiver's
own (`lib/plane_field.py:882-914` at main `1d8cd832`), copied character
for character.  Two things are spelled differently and neither is code:
`clamp`'s default is named `BOUND_DOTS`, because the number is field2's
own argument and no longer a quotation of production's ceiling
(DESIGN §4.6), and `clamp`'s docstring is rewritten in this module's
voice — the receiver's spoke as the receiver, and says so where it is
replaced.  The values do not move, so the estimator does not move: the
planted-field pins in `test_analyzer_field2.py` hold at their old
numbers, and one test compares the taps against the receiver's for as
long as both exist.

What did NOT move, and must not: `tile_codes`, `evaluate` and
`median_magnitude_dots` are LIVE receiver code — `evaluate` is the one
mapping every reader of a field samples through — and `field2` keeps
importing them from `holo.receiver.lib.plane_field`.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

#: The kernel's bandwidth in TILES, and where its taps are cut off.  The
#: bar is in tiles and the physical length is not: a tile is 64 cells, so
#: two tiles are 10.8 mm at c2 and 16.3 mm at c3, and the AltaLink's
#: ~100 mm sinusoid is 18.5 tiles at c2 against 12.3 at c3 — the same
#: kernel, a different fraction of the wave.  Every corpus with a
#: `field2` fit on the record is c2 (H, I, J), where the residual path
#: returns 0.95-0.96 of a planted 100 mm wave; the c3 response is
#: measured (0.81-0.88) and describes no corpus that exists.  A
#: millimetre-based bandwidth is a model question, not a patch (review
#: §5.2, 2026-09-13), and `--knob field2_bandwidth_tiles=…` is the A/B.
BANDWIDTH_TILES: float = 2.0
KERNEL_TRUNCATION: float = 3.5

#: Twicing passes over the smoothed residual.  A local weighted mean
#: attenuates smooth structure — a 2-tile bandwidth damps a 16-tile
#: sinusoid by ~26% — and re-smoothing what the first pass left over
#: buys most of it back (measured on the planted field: median error
#: 0.152 -> 0.040 dots).
TWICING_PASSES: int = 1

#: The bound on `field2`'s own surface, in printed dots.  FIELD2'S OWN
#: RULE, not production's retired clip (A2, DESIGN §4.6): a degree-<=3
#: polynomial plus a kernel residual has no prior and no fade, so the
#: grid needs a magnitude past which it is not published as a
#: registration estimate.  The number is unchanged from the receiver's
#: recorded ceiling.
#:
#: IT IS NOT ONLY THE EXTRAPOLATING POLYNOMIAL THAT IT MOVES (review
#: §5.2, 2026-09-13).  The per-tile search box is x +-2 and y +-1
#: (`arms.OFFSET_X_MIN`/`OFFSET_Y_MIN`), so its own corner has norm
#: 2.236: a fully supported, fully search-admissible reading can be
#: pulled back by up to 0.236 dots.  `clamped_supported_tiles` is the
#: count that says when that happened — sheet J page 0 Y, 8 tiles, all
#: supported — beside `clamped_tiles` over the whole grid.  Neither is
#: silent, and the bound stands pending a model decision.
BOUND_DOTS: float = 2.0

__all__ = ["BANDWIDTH_TILES", "BOUND_DOTS", "KERNEL_TRUNCATION",
           "TWICING_PASSES", "clamp", "gaussian_kernel", "smooth"]


def gaussian_kernel(bandwidth_tiles: float = BANDWIDTH_TILES,
                    truncation: float = KERNEL_TRUNCATION) -> np.ndarray:
    """Unnormalised (peak 1) Gaussian taps: information adds, it never
    averages away."""
    radius = max(1, int(np.ceil(truncation * bandwidth_tiles)))
    offsets = np.arange(-radius, radius + 1, dtype=np.float64)
    return np.exp(-0.5 * (offsets / float(bandwidth_tiles)) ** 2)


def smooth(grid: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Separable correlation with one kernel on both tile axes,
    zero-padded."""
    values = np.asarray(grid, np.float64)
    for axis in (0, 1):
        values = ndimage.correlate1d(values, np.asarray(kernel, np.float64),
                                     axis=axis, mode="constant", cval=0.0)
    return values


def clamp(delta_dots_xy: np.ndarray,
          max_delta_dots: float = BOUND_DOTS) -> np.ndarray:
    """Bound a delta's magnitude at `field2`'s own bound.

    THE ONE PROSE CHANGE this module makes to what it adopted.  The
    receiver's version of this docstring said the function survived
    there "because `analyzer/field2` builds its own parametric surface
    and bounds it here, at production's own recorded ceiling"; on this
    side of the door the bound is field2's own argument and `BOUND_DOTS`
    is where it is made (see that constant, and DESIGN §4.6).  The
    receiver clamps no page field at all: its prior, not a bound, governs
    the unmeasured region (`docs/PAGE-FIELD-DESIGN.md` I6, I8).

    The arithmetic below is unchanged, to the character.
    """
    delta = np.asarray(delta_dots_xy, np.float64)
    magnitude = np.hypot(delta[..., 0], delta[..., 1])
    scale = np.where(magnitude > max_delta_dots,
                     max_delta_dots / np.maximum(magnitude, 1e-12), 1.0)
    return delta * scale[..., None]
