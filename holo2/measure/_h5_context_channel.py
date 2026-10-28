"""THE AUTHORED CONTEXT-CORRELATED CHANNEL — H5 P3's shared fixture.

Not a driver: a sibling module the P3 measurement drivers
(``h5_union_gain.py``, ``h5_aperture_ctx.py``) import, in the same
standing as ``bch_equivalence_populations.py``. It has no ``__main__``
and measures nothing by itself.

WHY IT EXISTS — the load-bearing fixture fact, measured at H5 P1 and NOT
re-discovered here
--------------------------------------------------------------------
On UNIFORM cell error the held-out ctx gate REFUSES every fit: P1's probe
fired three fits per decode and all three refused, and the volume closed
byte-exact anyway. That refusal is CORRECT — uniform error carries no
context signal, so the nine-bin ordered additive-logit correction has
nothing to learn and ``fit_context``'s validation gate says so. Any
measurement of the ctx arm (H5-PLAN P3 arms a and d) run on
``_fixtures.render``'s ``cell_error_rate`` alone is therefore VACUOUS by
construction: it measures a refusal, not a correction.

So this module authors a channel whose error IS context-correlated, and
states its parameters rather than hiding them inside a driver (the
"authored structure, not blank paper" rule: gate on ground truth you put
there on purpose).

THE MODEL — a point-spread function, not a flip rule
-----------------------------------------------------
The obvious authoring is a flip probability conditioned on the true
neighbour ink count. This module does something both simpler and more
faithful: it applies ONE GAUSSIAN PSF to the rendered sheet, standing for
the combined print spread and scanner aperture, and lets the error follow.

That is the actual mechanism behind E023b's context bias. A white cell
surrounded by ink reads DARKER than an isolated white cell, because the
spread pulls its neighbours' ink into it; an ink cell surrounded by paper
reads LIGHTER. The read's bias is therefore monotone in the eight-
neighbour ink count — which is exactly the shape ``detect``'s carried arm
assumes and enforces (``_ordered_context_offsets`` pools until the nine
offsets are NON-INCREASING in the bin index, and ``ContextFit`` refuses
any fit that is not). A flip rule would have to be hand-tuned to produce
that monotonicity; a PSF produces it because it is where it comes from.

MEASURED, at :data:`PSF_SIGMA_CELLS` on an 8x8 ``c3-r0550`` page (the
sweep is arm (d)'s own table): the fit ADOPTS at every rung with offsets
running about +2.9 at bin 0 to -3.4 at bin 8, and the correction cuts
payload cell BER by 2.4x to 6.4x. At sigma 0.35 cells the same page's
PAVA BER is already under 0.1% and the ctx arm ADOPTS AND MAKES IT WORSE
— recorded in arm (d) rather than tuned away, because the held-out gate
is on weighted LOG-LOSS over format-known sites and not on payload
hard-decision BER, and the two can disagree.

WHAT THIS IS NOT. :data:`PSF_SIGMA_CELLS` is SOFTER than the Canon
glass measured at e028 (knife-edge MTF10 ~17 lp/mm): see
:func:`mtf10_lp_per_mm`, which reports the equivalent so a reader can
judge the gap instead of taking the sigma on trust. This is a
deliberately context-STRESSED synthetic page — it stands for the whole
print-plus-scan spread chain, and it is set where the ctx arm is
non-vacuous — not a model of the scanner of record. No number produced
on it is a channel claim, a ladder rung, or a recoverability prediction
(the standing e031 law).

THE PRINT/SENSOR SPLIT is ``_fixtures.render``'s own (its ``print_seed``
vs ``noise_seed`` docstring) and it is what makes a multi-scan
measurement mean anything: the ink — the dot field, the cell errors, the
coverage ramp and this PSF — is what is ON THE PAPER and is IDENTICAL
across two scans of one sheet; the pose and the Gaussian sensor draw are
what the SCANNER did and differ per acquisition. The multi-scan law is
that errors are PRINT-correlated (CLAUDE.md, F1 o F6), so a fixture whose
whole error was resampled per scan would rig a union measurement in
favour of the union, and one whose whole error was frozen in the ink
would rig it against. This one carries both halves on purpose.
"""
from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

from _fixtures import Render, render

#: The PSF's width in printed CELLS (see the module docstring for why a
#: PSF and not a flip rule, and for the sweep this point was taken from).
PSF_SIGMA_CELLS = 0.55

#: The SENSOR draw's standard deviation, in 0-255 luma — the ONE term
#: here that differs between two scans of one sheet.
SENSOR_NOISE = 8.0

#: THE PRINT CELL-ERROR BAND, and it is where the union arm's whole
#: subject comes from. ``verdicts/conftest.py``'s own mechanism (its
#: ``BAND_ERROR_RATE`` / ``BAND_COLUMNS``), at a rate this driver
#: measured for a DIFFERENT question than conftest measured its own.
#:
#: WHY A BAND AND NOT A RAMP — measured on this fixture, three times, and
#: recorded because it is a property of the RECEIVER and not of the knob:
#:
#: * a spatially UNIFORM channel gives an all-or-nothing page. At ramp 0,
#:   PSF 0.55: 64/64 tiles at sensor noise 16 and 0/64 at 22, and at
#:   sensor 8: 64/64 at PSF 0.63 and 0/64 at PSF 0.66. Every window sits
#:   at the same point of the same cliff, so there is no uniform setting
#:   that leaves a partial page.
#: * the cliff that binds is PLACEMENT, not payload: every collapse above
#:   is a run that commits no pose at all and ends in ~1 s. On this
#:   channel a window that places always certifies.
#: * so a coverage RAMP does produce a partial page — 40/64 at
#:   ``ink_ramp`` 0.65 — but it produces the WRONG one for a union: the
#:   40 are exactly the tiles whose ink is legible, the failures are
#:   whole windows that never placed, and MEASURED OVER THREE POSES
#:   (rotation -0.13, -0.05, +0.05) and two sensor seeds the certified
#:   set is byte-for-byte THE SAME 40. There is nothing to sum, because
#:   an unplaced window commits no evidence. A union arm on a ramp page
#:   is vacuous by construction, not by result.
#:
#: A print cell-error band is the shape that separates the two: the
#: seeded search's admission gate survives to ~20% cell error, so every
#: window still PLACES and every tile still carries evidence, while the
#: LDPC under the band dies. Measured here at :data:`BAND_ERROR_RATE`:
#: all 64 tiles carry evidence, one capture certifies 39 and the other
#: 36, and the two draws DISAGREE on 3 — a real de-correlated margin
#: sitting on top of a print-frozen residue. At 0.09 and 0.12 it
#: saturates at exactly 32 (the band is half the page) and the draws stop
#: disagreeing at all, which is the print-frozen limit.
#:
#: THE RATE WAS PRE-REGISTERED BY THAT CRITERION — a substantial
#: open-but-evidenced population AND a non-empty disagreement between the
#: two draws — and NOT by any union outcome, which had not been run.
BAND_ERROR_RATE = 0.06
BAND_COLUMNS = (0.5, 1.0)

#: The coverage ramp is OFF by default (see above); the knob is kept
#: because arm (d)'s channel sweep may want it and because the ramp
#: measurements above are reproducible from this module.
INK_RAMP = 0.0

#: The ink's own seed — ``verdicts/conftest.py``'s ``print_seed``,
#: reused so that "the same sheet" means the same bytes here as there.
PRINT_SEED = 20260809

#: The two sensor draws: one per acquisition of the one sheet.
NOISE_SEED_A = 20260819
NOISE_SEED_B = 20260820

#: ``_fixtures.ENGINE_DPI`` is the printed grid; a cell is ``cell_dots``
#: of it. Spelled here so the MTF conversion below needs no import.
_ENGINE_DPI = 600.0
_MM_PER_INCH = 25.4


def cell_mm(cell_dots: int) -> float:
    """One printed cell's pitch in millimetres on the engine grid."""
    return _MM_PER_INCH * cell_dots / _ENGINE_DPI


def mtf10_lp_per_mm(sigma_cells: float, cell_dots: int) -> float:
    """The spatial frequency where this PSF's MTF falls to 0.1, in lp/mm.

    A Gaussian PSF of width ``s`` has ``MTF(f) = exp(-2 pi^2 s^2 f^2)``,
    so ``MTF = 0.1`` at ``f = sqrt(ln 10) / (pi * s * sqrt 2)``. Reported
    beside every number this fixture produces so the softness is a stated
    quantity and not a hidden one: e028 measured the Canon's glass-level
    MTF10 at ~17 lp/mm, and this fixture is deliberately below it.
    """
    sigma_mm = float(sigma_cells) * cell_mm(cell_dots)
    return math.sqrt(math.log(10.0)) / (math.pi * sigma_mm * math.sqrt(2.0))


def truth_cells(page: object) -> np.ndarray:
    """The printed CELL field behind a page fixture, as booleans.

    ``gen.compose.cells_to_dots`` is a ``np.kron`` with a solid ones
    block, so every cell is a solid ``cell_dots`` square and taking every
    ``cell_dots``-th dot inverts it exactly. Derived rather than
    re-composed: re-running ``compose_page_cells`` would be a second
    spelling of the truth that could drift from the dots actually
    rendered.
    """
    dots = np.asarray(getattr(page, "dots"))
    step = int(getattr(page, "cell_dots"))
    return dots[::step, ::step].astype(bool)


def context_capture(page: object, work: Path, name: str, *,
                    px_per_dot: int,
                    rotation_deg: float,
                    pitch_scale: float | tuple[float, float],
                    noise_seed: int,
                    sigma_cells: float = PSF_SIGMA_CELLS,
                    noise_sigma: float = SENSOR_NOISE,
                    ink_ramp: float = INK_RAMP,
                    cell_error_rate: float = 0.0,
                    cell_error_band: tuple[float, float] | None = None
                    ) -> Render:
    """One acquisition of one sheet through the authored channel.

    THE ORDER IS THE PHYSICS and it is the whole reason this is not a
    ``render`` keyword: ink, then spread, then sensor. ``render`` lays
    the ink (dots, cell errors, the coverage ramp) and warps it to this
    acquisition's pose with ``noise_sigma=0``; the PSF is convolved over
    the WARPED sheet, because print spread and scanner aperture both act
    on the physical page and not on the ideal field; and the Gaussian
    sensor draw is added LAST and is NOT blurred, because sensor noise is
    downstream of every aperture in the chain. Adding the noise through
    ``render`` instead would blur it, which would make the sensor draw
    context-correlated too and quietly destroy the print/sensor split
    this fixture is built on.

    The returned :class:`~_fixtures.Render` carries the BLURRED file's
    path and the SHARP render's affine, which is exact: convolution with
    a symmetric kernel is shift-invariant, so it moves no cell centre.
    The sharp intermediate is rendered under ``_fixtures``' own content-
    addressed cache, so two arms asking for one pose pay for it once.
    """
    sharp = render(np.asarray(getattr(page, "dots")),
                   work / f"{name}-sharp.png",
                   px_per_dot=px_per_dot,
                   cell_dots=int(getattr(page, "cell_dots")),
                   rotation_deg=rotation_deg, pitch_scale=pitch_scale,
                   noise_sigma=0.0, cell_error_rate=cell_error_rate,
                   cell_error_band=cell_error_band,
                   ink_ramp=ink_ramp, print_seed=PRINT_SEED,
                   noise_seed=PRINT_SEED)
    pitch_px = float(int(getattr(page, "cell_dots")) * px_per_dot)
    pixels = np.asarray(Image.open(sharp.path), np.float32)
    spread = ndimage.gaussian_filter(pixels, float(sigma_cells) * pitch_px,
                                     mode="nearest")
    # SEEDED, and the seed IS the acquisition's identity here: two scans
    # of one sheet differ in exactly this draw and in the pose above.
    draw = np.random.default_rng(int(noise_seed)).normal(
        0.0, float(noise_sigma), spread.shape)
    out = work / f"{name}.png"
    Image.fromarray(np.clip(np.rint(spread + draw), 0, 255).astype(np.uint8)
                    ).save(out)
    return replace(sharp, path=out)


def channel_line(sigma_cells: float, cell_dots: int, *,
                 noise_sigma: float = SENSOR_NOISE,
                 ink_ramp: float = INK_RAMP,
                 band_rate: float | None = None,
                 band_columns: tuple[float, float] | None = None) -> str:
    """One line naming every authored parameter — every driver prints it."""
    band = ("" if band_rate is None else
            f", print cell-error band {band_rate:g} over columns "
            f"{band_columns}")
    return (f"authored channel: PSF sigma {sigma_cells:g} cells "
            f"(= {sigma_cells * cell_dots:g} printed dots, MTF10 "
            f"{mtf10_lp_per_mm(sigma_cells, cell_dots):.1f} lp/mm vs the "
            f"Canon's measured ~17), ink_ramp {ink_ramp:g}{band}, sensor "
            f"sigma {noise_sigma:g} luma, print seed {PRINT_SEED}")
