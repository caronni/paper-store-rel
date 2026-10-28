#!/usr/bin/env python
"""H5 P3 (c) THE DECIMATED APERTURE and (d) THE ctx-PER-RUNG PROFILE — BY PATH.

    env/bin/python holo2/measure/h5_aperture_ctx.py [--arms A,B]
                                                    [--px-per-dot N]
                                                    [--format ID]

NOT A TEST and not collectable as one: no ``test_`` name, no pytest
fixtures, a ``__main__`` entry point, and it lives outside ``testpaths``.
Same standing as ``or5_or7_census.py``.

Both arms are CELL-LEVEL and neither runs a decode. That is deliberate
and it is what makes them pair-matched: a decode's yield is a function of
placement, scheduling and the fountain as well as of the cell read, and
the two questions here are ONLY about the cell read. So the pose is not
searched, it is KNOWN — ``_fixtures.render`` returns the exact affine it
warped the page under — and every arm reads the SAME cells of the SAME
page through the SAME detector, changing exactly one thing at a time.
"Don't measure known quantities": the pitch and pose here are format and
render truth, never re-fitted from the page.

THE READ, spelled once. Every number below comes from production code
called on production terms:

* the cell centres are the page's own cell lattice pushed through
  ``Render.native_affine``;
* the sample is ``ndimage.map_coordinates(..., order=1)`` at those
  centres — literally ``pose_fit.sample_segment``'s aperture, an order-1
  cell-CENTRE read, which is the only aperture holo2's placement path
  has;
* the hard decision is ``pose_fit.median_radiometrics``, the carried E022
  median detector;
* the calibrated decision is ``detect.fit_calibration``'s exact PAVA over
  the reference field's format-known SEARCH-parity sites, evaluated
  everywhere — the same map ``place_shared`` writes into evidence;
* the context correction is ``detect.fit_context`` +
  ``detect.apply_context_offsets``, held-out gated, unmodified.

BER is reported over the PAYLOAD cells — the cells that are NOT
format-known — because those are what the LDPC decodes and because the
fit's own labels live on the format-known ones. The two populations are
disjoint by construction, so no number here is fitted on what it scores.

(c) THE DECIMATED-APERTURE QUESTION
------------------------------------
E023b measured, on pair-matched common payload observations of one real
sheet, PAVA BER **1.8002% decimated vs 2.4135% native** — decimation is
not pixel deletion, and its antialiasing aperture can beat a native
point read. holo2 has never had that number for its own sampler. This
arm produces it: the SAME cells read through the materialized decimated
raster of each ppc rung (``capture.scale_space.area_decimate`` with the
rung's own ``AreaPixelTransform`` — the production derivation, direct
from native and never recursive) against the same cells read through the
NATIVE raster with the bilinear centre aperture.

The native rung is the CONTROL and it is exact: its transform is the
identity, so the decimated arm and the native arm must agree to the bit
there. The driver checks it and fails if they do not.

(d) WHERE THE ctx GAIN LIVES ON THE LADDER
-------------------------------------------
E018's branch record measured the ctx gain as SAMPLING-dependent — 3.5x
at 16 px/cell against roughly nil at 8 — and concluded the gap to the
word path was upstream lock and sampling, not the detector. With the
ladder live that stops being a per-scan accident and becomes a per-rung
measurement.

It is reported over a SWEEP of the channel's softness as well as over the
rungs, because the one-parameter answer would be misleading: the gain is
a function of both, and the sweep is what shows the sign changing.

THE FIXTURE IS THE SIBLING MODULE'S and its non-vacuity is the point: on
UNIFORM cell error the held-out gate refuses every fit (measured at P1),
so a ctx measurement on ``render``'s own ``cell_error_rate`` alone would
report a refusal and call it a profile. ``_h5_context_channel`` authors a
PSF instead, because a point-spread function is where E023b's context
bias actually comes from, and it makes the fit adopt. The driver PROVES
adoption rather than assuming it: an arm in which no fit adopts SAYS so
and fails.

WHAT NEITHER ARM CLAIMS. One synthetic page, one authored spread, one
seed. These are DIRECTIONS and mechanisms — not channel numbers, not
ladder rungs, and emphatically not recoverability predictions (e031's
standing law: a discovery-tier number is not receiver performance).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage

# Self-locating, like ``./confetti.py`` and ``or5_or7_census.py``.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE, _HERE / "verdicts", _ROOT / "src",
              _ROOT / "holo2" / "src"):
    sys.path.insert(0, str(_path))

from _fixtures import PAPER, build_page                       # noqa: E402
from _h5_context_channel import (NOISE_SEED_A,                # noqa: E402
                                 PSF_SIGMA_CELLS, SENSOR_NOISE,
                                 channel_line, context_capture,
                                 mtf10_lp_per_mm, truth_cells)

from holo2.capture.scale_space import (AreaPixelTransform,    # noqa: E402
                                       area_decimate, auto_ppc_levels,
                                       native_pixels_per_cell)
from holo2.format import tile_format_for                      # noqa: E402
from holo2.solve import detect                                # noqa: E402
from holo2.solve.pose_fit import median_radiometrics          # noqa: E402
from holo2.solve.reference import V1ReferenceField            # noqa: E402

#: The page, as ONE v2 format id (C4, RULINGS G5, 2026-08-22; it was
#: ``CODING`` + ``TILES_YX``).  ``c3-k-r0550@8x8`` is ``_fixtures``'
#: spine page, and c3 is what lays a THREE-rung ppc ladder at 1200 dpi
#: (2, 3, 6) — a two-rung ladder would make "per rung" a pair rather
#: than a profile.
FORMAT = "c3-k-r0550@8x8"

#: The pose the sheet was warped under — the measured e032 warp. It is
#: TRUTH here, not a hypothesis: nothing in this driver searches for it.
POSE: dict[str, Any] = dict(rotation_deg=-0.13, pitch_scale=(1.0115, 1.0060))

#: Arm (d)'s channel-softness sweep, in PSF sigma (printed cells). The
#: span is chosen to cross the interesting boundary rather than to sit on
#: one side of it: at the sharp end the page is already almost error-free
#: and the correction has nothing to do, at the soft end the read is past
#: what the format tolerates.
SIGMA_SWEEP = (0.35, 0.45, 0.55, 0.65)

#: Arm (c)'s sensor-noise ladder, in 0-255 luma. It spans from a nearly
#: noiseless capture (where decimation can only cost aperture) to one
#: dominated by the sensor (where the area average's noise suppression is
#: the whole story) — the two ends of the trade the arm is about.
NOISE_SWEEP = (2.0, 8.0, 24.0, 48.0)

ARMS = ("aperture", "ctx")


# ------------------------------------------------------------- the read

@dataclass(frozen=True)
class Page:
    """One rendered page, its truth, and the geometry every read shares."""

    fixture: Any
    native: np.ndarray
    native_ppc: Fraction
    rungs: tuple[Fraction, ...]
    #: cell centres in NATIVE pixels, (N, 2), row-major over the cell grid
    centres_native: np.ndarray
    truth: np.ndarray            # (cy, cx) bool, printed ink
    known: np.ndarray            # (cy, cx) bool, format-known label sites
    labels: np.ndarray           # (cy, cx) bool, the reference's values
    heldout: np.ndarray          # (cy, cx) bool, v1's (131y + 17x) & 1
    site_ids: np.ndarray         # (cy, cx) int64, one id per physical cell

    @property
    def payload(self) -> np.ndarray:
        """The cells the LDPC decodes: everything not format-known."""
        return ~self.known


def build(format_ref: str, work: Path, *,
          px_per_dot: int, sigma_cells: float,
          noise_sigma: float = SENSOR_NOISE) -> Page:
    """Render one page through the authored channel and pin its geometry."""
    fixture = build_page(format_ref)
    capture = context_capture(fixture, work,
                              f"page-s{sigma_cells:g}-n{noise_sigma:g}",
                              px_per_dot=px_per_dot,
                              noise_seed=NOISE_SEED_A,
                              sigma_cells=sigma_cells,
                              noise_sigma=noise_sigma, **POSE)
    native = np.asarray(Image.open(capture.path), np.float64)
    truth = truth_cells(fixture)
    cells_y, cells_x = truth.shape
    gy, gx = np.meshgrid(np.arange(cells_y), np.arange(cells_x), indexing="ij")
    # Cell CENTRES: holo2's affines are continuous EDGE coordinates (cell
    # i covers [i, i+1)), which is the convention ``_fixtures._warp``
    # inverts, so the centre of cell i is i + 0.5 and not i.
    a, b, c, d, e, f = capture.native_affine
    centres = np.stack([
        a * (gy.ravel() + 0.5) + b * (gx.ravel() + 0.5) + c,
        d * (gy.ravel() + 0.5) + e * (gx.ravel() + 0.5) + f], axis=1)

    spec = tile_format_for(fixture.row)
    field = V1ReferenceField(spec).page(0)
    known = np.asarray(field.sites, bool)
    labels = np.asarray(field.values, np.uint8).astype(bool)
    # THE TRUTH CHECK, and it is not decoration: it proves the reference
    # field this driver labels with is the field the generator actually
    # PRINTED. A silent disagreement here would make every fit below a
    # fit against fiction.
    assert bool((labels[known] == truth[known]).all()), (
        "the reference field disagrees with the printed ink")

    dpi = Fraction(int(round(capture.dpi)))
    # The ladder takes the printed PITCH since C3 (RULINGS G4): dots are
    # the renderer's unit, and this instrument has both because it emits
    # its own sheet.
    pitch_in = fixture.row.pitch_in
    return Page(fixture=fixture, native=native,
                native_ppc=native_pixels_per_cell(dpi, pitch_in),
                rungs=auto_ppc_levels(dpi, pitch_in),
                centres_native=centres, truth=truth, known=known,
                labels=labels,
                heldout=(((131 * gy + 17 * gx) & 1) == 1),
                site_ids=(gy * cells_x + gx).astype(np.int64))


def read_means(page: Page, ppc: Fraction | None) -> np.ndarray:
    """Cell means through one aperture. ``ppc=None`` is the native read.

    THE DECIMATED ARM materializes the rung's view with the PRODUCTION
    derivation — ``AreaPixelTransform(native_ppc / ppc)`` and
    ``area_decimate``, direct from native, never recursively from another
    level (``capture/DESIGN.md``'s D1 rule) — and then reads the same
    cell centres through it. ``AreaPixelTransform`` documents its own
    pixel-centre map as ``source = scale * (view + 0.5) - 0.5``, so the
    inverse used here is its statement rearranged, not a guess.

    THE NATIVE ARM reads the identical centres straight off the native
    raster. Same cells, same interpolation order, same ``cval``; the ONLY
    difference is which pixels the value is built from, which is what
    "aperture" means.
    """
    if ppc is None or Fraction(page.native_ppc, 1) / ppc == 1:
        view, points = page.native, page.centres_native
    else:
        scale = Fraction(page.native_ppc, 1) / ppc
        view = area_decimate(
            np.clip(np.rint(page.native), 0, 255).astype(np.uint8),
            AreaPixelTransform(scale)).astype(np.float64)
        points = (page.centres_native + 0.5) / float(scale) - 0.5
    return ndimage.map_coordinates(
        view, points.T, order=1, cval=float(PAPER)).reshape(page.truth.shape)


@dataclass(frozen=True)
class Read:
    """One aperture's decisions on one page, and the fit behind them."""

    label: str
    raw_ber: float               # median detector, payload cells
    pava_ber: float | None       # calibrated, payload cells (v1's metric)
    pava_reason: str
    ctx_ber: float | None        # calibrated + context, payload cells
    ctx_adopted: bool
    ctx_reason: str
    offsets: np.ndarray
    n_search: int
    logloss_delta: float | None
    bits: np.ndarray             # the calibrated hard decisions, for pairing


def score(page: Page, means: np.ndarray, label: str) -> Read:
    """Detector, PAVA and ctx over one aperture's means. One call, one arm."""
    payload = page.payload
    _mid, raw_bits, _ev = median_radiometrics(means, np.ones_like(payload))
    raw_ber = float((raw_bits.astype(bool) != page.truth)[payload].mean())

    scores = -np.asarray(means, np.float64)      # negated luma: more = ink
    search = page.known & ~page.heldout
    heldout = page.known & page.heldout
    fit = detect.fit_calibration(
        detect.CalibrationObservations(label, scores[search],
                                       page.labels[search],
                                       page.site_ids[search]),
        detect.CalibrationObservations(label, scores[heldout],
                                       page.labels[heldout],
                                       page.site_ids[heldout]))
    if fit.calibration is None:
        return Read(label, raw_ber, None, fit.reason, None, False,
                    "no_marginal_fit", np.zeros(detect.N_CONTEXT_BINS),
                    0, None, raw_bits.astype(bool))
    llr = fit.calibration.llr(scores)
    pava_bits = llr > 0.0
    pava_ber = float((pava_bits != page.truth)[payload].mean())

    cells = np.stack([np.repeat(np.arange(page.truth.shape[0]),
                                page.truth.shape[1]),
                      np.tile(np.arange(page.truth.shape[1]),
                              page.truth.shape[0])], axis=1).astype(np.int64)
    counts, valid = detect.context_neighbour_counts(cells, pava_bits.ravel())
    counts = counts.reshape(page.truth.shape)
    valid = valid.reshape(page.truth.shape)
    fit_s = page.known & valid & ~page.heldout
    fit_v = page.known & valid & page.heldout
    context = detect.fit_context(
        detect.ContextObservations(label, llr[fit_s], counts[fit_s],
                                   page.labels[fit_s], page.site_ids[fit_s]),
        detect.ContextObservations(label, llr[fit_v], counts[fit_v],
                                   page.labels[fit_v], page.site_ids[fit_v]))
    corrected = detect.apply_context_offsets(
        llr, detect.context_bins(counts, valid=valid), context.offsets)
    delta = (None if context.baseline_validation_logloss is None
             else float(context.candidate_validation_logloss
                        - context.baseline_validation_logloss))
    return Read(label, raw_ber, pava_ber, fit.reason,
                float(((corrected > 0.0) != page.truth)[payload].mean()),
                bool(context.adopted), context.reason,
                np.asarray(context.offsets, np.float64),
                int(context.n_search), delta, pava_bits)


# ------------------------------------------------------------ the reports

def report_aperture(work: Path, format_ref: str,
                    px_per_dot: int, failures: list[str]) -> None:
    """(c) Pair-matched BER: each rung's decimated view vs native.

    OVER A SENSOR-NOISE LADDER, and that is the discriminating test, not
    decoration. Decimation trades two things against each other: an area
    average SUPPRESSES white sensor noise (by the square root of the
    pixels it pools) and WIDENS the aperture (pulling in neighbouring
    cells' ink, which is the very context contamination arm (d) is
    about). Which term wins is a property of the CAPTURE, not of the
    decimation — so a single-noise answer would be a number with its
    mechanism hidden inside. Sweeping the noise makes the crossover
    visible, and a crossover is the claim; one row is not.
    """
    print("\n  (c) DECIMATED APERTURE vs NATIVE BILINEAR — pair-matched, "
          "same cells, over a sensor-noise ladder")
    print("      ratio = native PAVA BER / decimated PAVA BER; >1 means "
          "DECIMATION WINS (v1 measured 2.4135/1.8002 = 1.34x on a real "
          "4800-dpi Canon scan)")
    checked_identity = False
    for noise in NOISE_SWEEP:
        page = build(format_ref, work, px_per_dot=px_per_dot,
                     sigma_cells=PSF_SIGMA_CELLS, noise_sigma=noise)
        native = score(page, read_means(page, None), "native")
        if native.pava_ber is None:
            print(f"    sensor sigma {noise:>5g}: the native arm's PAVA "
                  f"refused ({native.pava_reason}); nothing to compare")
            continue
        cells = []
        for ppc in page.rungs:
            read = score(page, read_means(page, ppc), f"ppc-{ppc}")
            is_native = Fraction(page.native_ppc, 1) / ppc == 1
            if read.pava_ber is None:
                cells.append(f"ppc {ppc}: refused")
                continue
            ratio = (native.pava_ber / read.pava_ber
                     if read.pava_ber > 0 else float("inf"))
            cells.append(f"ppc {str(ppc):>2} {read.pava_ber * 100:6.3f}% "
                         f"({ratio:5.2f}x)")
            if is_native:
                # THE EXACT CONTROL: at the native rung the transform is
                # the identity, so this must be the same read by
                # construction. A difference means the view-coordinate
                # inverse is wrong and every other row is untrustworthy.
                checked_identity = True
                if not np.array_equal(read.bits, native.bits):
                    failures.append(
                        "(c): the native rung's decimated arm disagrees "
                        "with the native arm — the identity control "
                        "FAILED, so the view-coordinate inverse is wrong")
        print(f"    sensor sigma {noise:>5g}: NATIVE(ppc {page.native_ppc}) "
              f"{native.pava_ber * 100:6.3f}%   " + "  ".join(cells))
    if not checked_identity:
        failures.append(
            "(c): the identity control never ran — no rung was the native "
            "one, so nothing proved the coordinate inverse")


def report_ctx(work: Path, format_ref: str,
               px_per_dot: int, failures: list[str]) -> None:
    """(d) Where the ctx gain lives: per rung, over a channel sweep."""
    print("\n  (d) ctx PER RUNG — adopted-fit offsets and the BER it buys")
    print("      (BER over payload cells; 'span' is offsets[0] - offsets[8], "
          "the correction's whole dynamic range)")
    adopted_any = False
    for sigma in SIGMA_SWEEP:
        page = build(format_ref, work, px_per_dot=px_per_dot,
                     sigma_cells=sigma)
        cell_dots = int(page.fixture.cell_dots)
        print(f"    PSF sigma {sigma:g} cells = {sigma * cell_dots:g} printed "
              f"dots, MTF10 {mtf10_lp_per_mm(sigma, cell_dots):.1f} lp/mm")
        for ppc in page.rungs:
            read = score(page, read_means(page, ppc), f"s{sigma}-ppc{ppc}")
            if read.pava_ber is None:
                print(f"      ppc {str(ppc):>4}: PAVA refused "
                      f"({read.pava_reason})")
                continue
            adopted_any |= read.ctx_adopted
            gain = (read.pava_ber / read.ctx_ber
                    if read.ctx_ber and read.ctx_ber > 0 else float("inf"))
            span = float(read.offsets[0] - read.offsets[-1])
            arrow = "->" if read.ctx_ber <= read.pava_ber else "-> WORSE"
            print(f"      ppc {str(ppc):>4}: PAVA {read.pava_ber * 100:7.4f}% "
                  f"{arrow} ctx {read.ctx_ber * 100:7.4f}%  "
                  f"({gain:5.2f}x)  adopted={read.ctx_adopted} "
                  f"span {span:5.2f} "
                  f"[{read.offsets[0]:+.2f} .. {read.offsets[-1]:+.2f}]  "
                  f"n_search {read.n_search}  "
                  f"held-out logloss delta "
                  f"{'n/a' if read.logloss_delta is None else f'{read.logloss_delta:+.5f}'}")
    if not adopted_any:
        failures.append(
            "(d): NO ctx FIT ADOPTED ANYWHERE in the sweep — the profile is "
            "a census of refusals, not of a correction, and must not be "
            "read as one.")


# ------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--arms", default=",".join(ARMS),
                        help=f"comma-separated arms ({', '.join(ARMS)})")
    parser.add_argument("--px-per-dot", type=int, default=2, metavar="N",
                        help="capture resolution as pixels per printed dot "
                             "(2 = 1200 dpi, the measure tree's footing; 4 = "
                             "2400 dpi, which lengthens the ppc ladder to "
                             "reach e018's 12-16 px/cell regime)")
    parser.add_argument("--format", default=FORMAT, dest="format_ref",
                        metavar="ID",
                        help=f"format reference — a v2 identity or an "
                             f"L: fossil line (default {FORMAT})")
    args = parser.parse_args(argv)
    names = tuple(n.strip() for n in args.arms.split(",") if n.strip())
    unknown = set(names) - set(ARMS)
    if unknown:
        parser.error(f"unknown arm(s): {', '.join(sorted(unknown))}")

    print("H5 P3 (c)/(d) — APERTURE and ctx PROFILE, cell-level, no decode.")
    failures: list[str] = []
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="h5-aperture-") as raw:
        work = Path(raw)
        page = build(args.format_ref, work,
                     px_per_dot=args.px_per_dot,
                     sigma_cells=PSF_SIGMA_CELLS)
        print(f"  page {args.format_ref}, cells {page.truth.shape}, "
              f"capture {page.native.shape} px at {args.px_per_dot} px/dot")
        print(f"  {channel_line(PSF_SIGMA_CELLS, int(page.fixture.cell_dots))}")
        print(f"  pose is TRUTH (not searched): {POSE}")
        print(f"  ppc ladder {[str(v) for v in page.rungs]} "
              f"(native {page.native_ppc}); format-known label sites "
              f"{int(page.known.sum())}, payload cells "
              f"{int(page.payload.sum())}")
        if "aperture" in names:
            report_aperture(work, args.format_ref, args.px_per_dot,
                            failures)
        if "ctx" in names:
            report_ctx(work, args.format_ref, args.px_per_dot, failures)
    print(f"\n  wall {time.perf_counter() - started:.1f} s")

    if failures:
        print("\nFAILED / FINDINGS:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("\nCOMPLETE — the identity control held and the ctx arm was live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
