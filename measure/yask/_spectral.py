"""Spectral isolation: from an RGB scan to a yellow-only grey plane.

THE MODEL. A cell's three sampled channel means are, to first order,
a paper level plus one mean shift per plane of ink present:

    v = m0 + mC*C + mM*M + mY*Y + noise,   C, M, Y in {0, 1}

with ``m`` a 3x3 matrix of channel-by-plane mean shifts. Yellow toner
absorbs blue, so ``mY`` is large and negative in B and small in R and G
— but cyan and magenta absorb some blue too, so the raw B channel is a
MIXTURE, not a yellow readout. That is the whole reason this module
exists.

WHERE THE MODEL IS FITTED. On cells whose three plane bits are all
KNOWN: the format's own furniture (100 word sites at states {0, 3} and
20 dust sites cycling {1, 2, 4, 5, 6, 7} per tile) plus every payload
cell of a tile certified in all three streams. That is ordinary
receiver-side knowledge, not an oracle.

TWO READOUTS, and the difference between them is the experiment's
first lever:

* ``project`` — one fixed linear functional ``w`` with ``w·mC = 0``,
  ``w·mM = 0``, ``w·mY = 1``, chosen among those to have minimum
  variance under the fitted residual covariance (generalized least
  squares). Cyan and magenta cancel in the MEAN; nothing per-cell is
  needed, so this readout works everywhere.
* ``subtract`` — where a cell's C and M bits are KNOWN (certified
  siblings, or furniture), their contribution is subtracted from the
  observation exactly and the residual is projected on ``mY`` alone.
  This spends two fewer degrees of freedom than ``project`` and should
  be strictly quieter; where the siblings are unknown it falls back to
  ``project``, cell by cell.

and one control:

* ``rawb`` — the blue channel's own deficit, scaled so a unit of Y
  reads as 1. The naive "yellow absorbs blue" readout, carried so the
  report can say what the unmixing bought.

FILTERING COMMUTES. The channel means are sampled through holo3's own
aperture filter before they reach this module. Both the filter and the
unmixing are linear, so unmixing the sampled means is EXACTLY sampling
the unmixed plane — the synthetic "yellow as black on white" image is
never materialized, and nothing is lost by not materializing it.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PLANE_C, PLANE_M, PLANE_Y = 0, 1, 2
MODES = ("project", "subtract", "rawb")

#: A fit needs this many cells with all three plane bits known, and
#: this many in each class of each plane, before it is trusted.
MIN_FULL_ROWS = 200
MIN_PER_CLASS = 25


@dataclass(frozen=True)
class Unmix:
    """The fitted mixing model and the readouts derived from it."""

    #: (3,) paper level per channel.
    m0: np.ndarray
    #: (3, 3) mean shift; column ``p`` is plane ``p``'s shift vector.
    coef: np.ndarray
    #: (3, 3) residual covariance of the fit.
    covariance: np.ndarray
    #: (3,) the minimum-variance C/M-annihilating functional.
    projection: np.ndarray
    #: (3,) the residual-projection functional used by ``subtract``.
    residual_functional: np.ndarray
    n_full_rows: int
    class_counts: tuple[tuple[int, int], ...]
    accepted: bool
    reason: str

    def channel_snr(self) -> tuple[float, float, float]:
        """Per-plane |mean shift| / residual sd, in the B channel's own
        terms — a coarse 'how visible is this plane' number."""
        sd = np.sqrt(np.diag(self.covariance))
        return tuple(float(np.linalg.norm(self.coef[:, p] / sd))
                     for p in range(3))


def _refused(reason: str, n_full: int,
             counts: tuple[tuple[int, int], ...]) -> Unmix:
    eye = np.eye(3)
    return Unmix(m0=np.zeros(3), coef=np.zeros((3, 3)), covariance=eye,
                 projection=np.array([0.0, 0.0, -1.0]),
                 residual_functional=np.array([0.0, 0.0, -1.0]),
                 n_full_rows=n_full, class_counts=counts, accepted=False,
                 reason=reason)


def fit_unmix(values: np.ndarray, bits: np.ndarray,
              known: np.ndarray) -> Unmix:
    """Least squares on every cell whose three plane bits are known."""
    v = np.asarray(values, np.float64)
    b = np.asarray(bits, np.uint8)
    k = np.asarray(known, bool)
    full = k.all(axis=1)
    n_full = int(np.count_nonzero(full))
    design_bits = b[full].astype(np.float64)
    counts = tuple((int(design_bits.shape[0] - design_bits[:, p].sum()),
                    int(design_bits[:, p].sum())) for p in range(3))
    if n_full < MIN_FULL_ROWS:
        return _refused("too_few_full_rows", n_full, counts)
    if min(min(pair) for pair in counts) < MIN_PER_CLASS:
        return _refused("plane_class_starved", n_full, counts)
    design = np.column_stack((np.ones(n_full), design_bits))
    solution, *_ = np.linalg.lstsq(design, v[full], rcond=None)
    m0 = solution[0]
    coef = solution[1:].T                       # (channel, plane)
    residual = v[full] - design @ solution
    covariance = np.cov(residual, rowvar=False)
    covariance = np.atleast_2d(covariance)
    covariance += np.eye(3) * (1e-9 + 1e-9 * float(np.trace(covariance)))
    inverse = np.linalg.inv(covariance)
    unit = np.array([0.0, 0.0, 1.0])
    gram = coef.T @ inverse @ coef
    try:
        projection = inverse @ coef @ np.linalg.solve(gram, unit)
    except np.linalg.LinAlgError:
        return _refused("singular_plane_gram", n_full, counts)
    y_shift = coef[:, PLANE_Y]
    denominator = float(y_shift @ inverse @ y_shift)
    if denominator <= 0.0:
        return _refused("degenerate_y_shift", n_full, counts)
    residual_functional = (inverse @ y_shift) / denominator
    return Unmix(m0=m0, coef=coef, covariance=covariance,
                 projection=projection,
                 residual_functional=residual_functional,
                 n_full_rows=n_full, class_counts=counts, accepted=True,
                 reason="accepted")


def y_score(unmix: Unmix, values: np.ndarray, bits: np.ndarray,
            known: np.ndarray, mode: str) -> np.ndarray:
    """Yellow presence in units of one Y ink layer; high = yellow ink."""
    if mode not in MODES:
        raise ValueError(f"yask: unknown spectral mode {mode!r}; "
                         f"known: {list(MODES)}")
    v = np.asarray(values, np.float64)
    centred = v - unmix.m0
    if mode == "rawb":
        shift = float(unmix.coef[PLANE_Y, PLANE_Y])
        if shift == 0.0:
            return np.zeros(v.shape[0])
        return centred[:, PLANE_Y] / shift
    projected = centred @ unmix.projection
    if mode == "project":
        return projected
    b = np.asarray(bits, np.uint8).astype(np.float64)
    k = np.asarray(known, bool)
    siblings = k[:, PLANE_C] & k[:, PLANE_M]
    out = projected
    if np.any(siblings):
        residual = (centred[siblings]
                    - b[siblings, PLANE_C, None] * unmix.coef[:, PLANE_C]
                    - b[siblings, PLANE_M, None] * unmix.coef[:, PLANE_M])
        out = np.array(projected, copy=True)
        out[siblings] = residual @ unmix.residual_functional
    return out


def sibling_coverage(known: np.ndarray) -> dict:
    k = np.asarray(known, bool)
    n = int(k.shape[0])
    return {"cells": n,
            "c_and_m_known": int(np.count_nonzero(k[:, PLANE_C]
                                                  & k[:, PLANE_M])),
            "y_known": int(np.count_nonzero(k[:, PLANE_Y])),
            "all_known": int(np.count_nonzero(k.all(axis=1)))}


def separation(score: np.ndarray, y_bits: np.ndarray) -> dict:
    """d' and the hard-decision error rate of a scalar Y readout.

    MEASUREMENT ONLY: ``y_bits`` here is the emitted field, so this
    function never runs on a path that can mint a certificate.
    """
    s = np.asarray(score, np.float64)
    y = np.asarray(y_bits, bool)
    n1 = int(np.count_nonzero(y))
    n0 = int(y.size - n1)
    if n0 < 2 or n1 < 2:
        return {"n0": n0, "n1": n1, "dprime": None, "cell_error": None,
                "threshold": None}
    mean0, mean1 = float(s[~y].mean()), float(s[y].mean())
    var0, var1 = float(s[~y].var(ddof=1)), float(s[y].var(ddof=1))
    pooled = 0.5 * (var0 + var1)
    dprime = None if pooled <= 0.0 else (mean1 - mean0) / float(np.sqrt(pooled))
    threshold = float(np.median(s))
    hard = s > threshold
    return {"n0": n0, "n1": n1,
            "dprime": None if dprime is None else float(dprime),
            "cell_error": float(np.count_nonzero(hard != y) / y.size),
            "threshold": threshold,
            "mean0": mean0, "mean1": mean1,
            "sd0": float(np.sqrt(var0)), "sd1": float(np.sqrt(var1))}
