"""Plane isolation: one printing plane read as a black-and-white page.

THE MODEL.  A cell's three sampled channel means are, to first order, a
paper level plus one mean shift per plane of ink present::

    v = m0 + mC*C + mM*M + mY*Y,    C, M, Y in {0, 1}

with ``coef`` the 3x3 matrix of channel-by-plane mean shifts.  The naive
"yellow absorbs blue, so B is the yellow channel" reading is WRONG and
the ablation that says so is measured (``measure/yask``, sheet H at
2400 dpi): magenta darkens blue by −23.0 against yellow's −38.6, so the
blue channel is a yellow-PLUS-magenta readout, and reading it raw
certifies nothing at all.  Cancelling the two sibling planes is what
makes the composition exist.

The module is plane-general because the mechanism is symmetric: cyan is
read off red and magenta off green by the same arithmetic.  Nothing here
privileges yellow, and nothing here knows what a certificate is.

TWO READOUTS, and the difference between them is worth five times the
yield (1 add -> 5 on the measured battery):

* ``project`` — one fixed linear functional per plane, ``w`` with
  ``w . m_sibling = 0`` for both siblings and ``w . m_plane = 1``,
  chosen among those to have minimum variance under the fitted residual
  covariance.  Siblings cancel IN THE MEAN, so nothing per-cell is
  needed and this readout works on every cell.
* ``subtract`` — where a cell's sibling bits are KNOWN (format
  furniture, or a certified neighbour's projected cells), their
  contribution is subtracted exactly and the residual is projected on
  the target plane's own shift.  That spends two fewer degrees of
  freedom and is strictly quieter; where the siblings are unknown it
  falls back to ``project``, cell by cell.

and one control, carried so an instrument can price the other two:

* ``raw`` — the complementary channel's own deficit, scaled so one ink
  layer reads as 1.

FILTERING COMMUTES, so the synthetic grey page is never materialised.
The channel means arrive already aperture-filtered by the sampler; the
filter and this unmixing are both linear, so unmixing the sampled means
IS sampling the unmixed plane.

Nothing here reads a clock, draws a random number or touches a raster.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

N_PLANES: int = 3

MODE_SUBTRACT: str = "subtract"
MODE_PROJECT: str = "project"
MODE_RAW: str = "raw"
MODES: tuple[str, ...] = (MODE_SUBTRACT, MODE_PROJECT, MODE_RAW)

#: A fit needs this many cells with all three plane bits known, and this
#: many in each class of each plane, before it is trusted.  Both are the
#: measured harness's values; a window that cannot reach them is a window
#: whose mixing model would be noise.
MIN_FULL_ROWS: int = 200
MIN_PER_CLASS: int = 25

#: Ridge added to the residual covariance before it is inverted, scaled
#: by its own trace so the guard is unit-free.
COVARIANCE_RIDGE: float = 1e-9

REASON_ACCEPTED: str = "accepted"
REASON_FEW_ROWS: str = "too_few_full_rows"
REASON_STARVED: str = "plane_class_starved"
REASON_SINGULAR: str = "singular_plane_gram"
REASON_DEGENERATE: str = "degenerate_plane_shift"


@dataclass(frozen=True)
class PlaneMix:
    """The fitted mixing model and the per-plane readouts it induces."""

    #: (3,) paper level per channel.
    m0: np.ndarray
    #: (3, 3) mean shift; column ``p`` is plane ``p``'s shift vector.
    coef: np.ndarray
    #: (3, 3) residual covariance of the fit.
    covariance: np.ndarray
    #: (3, 3); column ``p`` is the minimum-variance functional that
    #: annihilates the other two planes and gives plane ``p`` unit gain.
    projections: np.ndarray
    #: (3, 3); column ``p`` is the functional ``subtract`` projects a
    #: sibling-cleaned residual on.
    residual_functionals: np.ndarray
    n_full_rows: int
    class_counts: tuple[tuple[int, int], ...]
    accepted: bool
    reason: str

    def plane_snr(self) -> tuple[float, ...]:
        """|mean shift| / residual sd per plane — a coarse visibility."""
        sd = np.sqrt(np.diag(self.covariance))
        return tuple(float(np.linalg.norm(self.coef[:, plane] / sd))
                     for plane in range(N_PLANES))


def siblings_of(plane: int) -> tuple[int, ...]:
    """The two planes that are nuisance when ``plane`` is the target."""
    return tuple(other for other in range(N_PLANES) if other != plane)


def _refused(reason: str, n_full: int,
             counts: tuple[tuple[int, int], ...]) -> PlaneMix:
    zeros = np.zeros((N_PLANES, N_PLANES))
    return PlaneMix(m0=np.zeros(N_PLANES), coef=zeros,
                    covariance=np.eye(N_PLANES), projections=zeros,
                    residual_functionals=zeros, n_full_rows=n_full,
                    class_counts=counts, accepted=False, reason=reason)


def _class_counts(design_bits: np.ndarray) -> tuple[tuple[int, int], ...]:
    return tuple((int(design_bits.shape[0] - design_bits[:, plane].sum()),
                  int(design_bits[:, plane].sum()))
                 for plane in range(N_PLANES))


def fit_plane_mix(values: np.ndarray, bits: np.ndarray,
                  known: np.ndarray) -> PlaneMix:
    """Least squares on every cell whose three plane bits are known.

    ``values`` is (N, 3) sampled channel means, ``bits`` (N, 3) uint8
    plane presence and ``known`` (N, 3) bool.  Only rows known in all
    three planes carry a design row — those are the format's own word
    and dust sites plus the payload cells of tiles certified in every
    stream, which is ordinary receiver knowledge and never an oracle.
    """
    v = np.asarray(values, np.float64)
    b = np.asarray(bits, np.uint8)
    k = np.asarray(known, bool)
    full = k.all(axis=1)
    n_full = int(np.count_nonzero(full))
    design_bits = b[full].astype(np.float64)
    counts = _class_counts(design_bits)
    if n_full < MIN_FULL_ROWS:
        return _refused(REASON_FEW_ROWS, n_full, counts)
    if min(min(pair) for pair in counts) < MIN_PER_CLASS:
        return _refused(REASON_STARVED, n_full, counts)
    design = np.column_stack((np.ones(n_full), design_bits))
    solution, *_ = np.linalg.lstsq(design, v[full], rcond=None)
    m0 = solution[0]
    coef = solution[1:].T                       # (channel, plane)
    residual = v[full] - design @ solution
    covariance = np.atleast_2d(np.cov(residual, rowvar=False))
    covariance = covariance + np.eye(N_PLANES) * (
        COVARIANCE_RIDGE * (1.0 + float(np.trace(covariance))))
    inverse = np.linalg.inv(covariance)
    gram = coef.T @ inverse @ coef
    try:
        projections = inverse @ coef @ np.linalg.inv(gram)
    except np.linalg.LinAlgError:
        return _refused(REASON_SINGULAR, n_full, counts)
    denominators = np.einsum("cp,cd,dp->p", coef, inverse, coef)
    if not np.all(denominators > 0.0):
        return _refused(REASON_DEGENERATE, n_full, counts)
    residual_functionals = (inverse @ coef) / denominators[None, :]
    return PlaneMix(m0=m0, coef=coef, covariance=covariance,
                    projections=projections,
                    residual_functionals=residual_functionals,
                    n_full_rows=n_full, class_counts=counts, accepted=True,
                    reason=REASON_ACCEPTED)


def plane_score(mix: PlaneMix, values: np.ndarray, bits: np.ndarray,
                known: np.ndarray, plane: int,
                mode: str = MODE_SUBTRACT) -> np.ndarray:
    """One plane's presence in units of one ink layer; high = ink."""
    if mode not in MODES:
        raise ValueError(f"spectral: unknown mode {mode!r}; "
                         f"known: {list(MODES)}")
    v = np.asarray(values, np.float64)
    centred = v - mix.m0
    if mode == MODE_RAW:
        shift = float(mix.coef[plane, plane])
        if shift == 0.0:
            return np.zeros(v.shape[0])
        return centred[:, plane] / shift
    projected = centred @ mix.projections[:, plane]
    if mode == MODE_PROJECT:
        return projected
    b = np.asarray(bits, np.uint8).astype(np.float64)
    k = np.asarray(known, bool)
    left, right = siblings_of(plane)
    cleanable = k[:, left] & k[:, right]
    if not np.any(cleanable):
        return projected
    residual = (centred[cleanable]
                - b[cleanable, left, None] * mix.coef[:, left]
                - b[cleanable, right, None] * mix.coef[:, right])
    out = np.array(projected, copy=True)
    out[cleanable] = residual @ mix.residual_functionals[:, plane]
    return out


def sibling_coverage(known: np.ndarray, plane: int) -> dict[str, int]:
    """How much sibling knowledge a population actually carries."""
    k = np.asarray(known, bool)
    left, right = siblings_of(plane)
    return {"cells": int(k.shape[0]),
            "siblings_known": int(np.count_nonzero(k[:, left] & k[:, right])),
            "plane_known": int(np.count_nonzero(k[:, plane])),
            "all_known": int(np.count_nonzero(k.all(axis=1)))}
