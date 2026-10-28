"""Pure provisional CMY7 and CMY8 channel mappings.

This module owns only the small, format-defining mapping between binary
channel bits and physical CMY state IDs.  It deliberately does not own FEC,
scrambling, interleaving, tile placement, image rendering, or detector
calibration.

Frozen conventions
------------------

* Plane order is ``C, M, Y``.
* A state ID is the presence-bit integer ``C + 2*M + 4*Y``:

  ``W=0, C=1, M=2, CM=3, Y=4, CY=5, MY=6, CMY=7``.

* Plane arrays use a final axis of length three in ``C, M, Y`` order.
* A relative-score array uses a final state axis in increasing state-ID
  order with state 0 omitted.  Its implicit state-0 score is zero.
* LLRs use the Holo convention ``log P(bit=1) - log P(bit=0)``.
* CMY7 v0 converts an eleven-bit, MSB-first integer to four
  most-significant-first radix-7 digits.  Digits are state IDs 0..6.

The soft demappers sum over every legal state candidate with log-sum-exp.
They never hard-classify a cell and never admit CMY7's 353 unused tuples.
"""
from __future__ import annotations

from enum import IntEnum

import numpy as np


class CMYState(IntEnum):
    """Canonical physical state IDs (presence-bit integer)."""

    W = 0
    C = 1
    M = 2
    CM = 3
    Y = 4
    CY = 5
    MY = 6
    CMY = 7


PLANE_ORDER: tuple[str, ...] = ("C", "M", "Y")
STATE_NAMES: tuple[str, ...] = (
    "W", "C", "M", "CM", "Y", "CY", "MY", "CMY",
)
CMY7_STATE_NAMES: tuple[str, ...] = STATE_NAMES[:-1]

CMY7_BITS_PER_PACK = 11
CMY7_CELLS_PER_PACK = 4
CMY7_N_CANDIDATES = 1 << CMY7_BITS_PER_PACK
CMY7_N_TUPLES = 7 ** CMY7_CELLS_PER_PACK

_CMY7_RADIX_DIVISORS = np.asarray((7 ** 3, 7 ** 2, 7, 1), dtype=np.int64)
_CMY7_WORDS = np.arange(CMY7_N_CANDIDATES, dtype=np.int64)

# The table, rather than its generating expression, is the mapper surface.
# Its byte digest is pinned externally in tests.
CMY7_CODEBOOK = (
    (_CMY7_WORDS[:, None] // _CMY7_RADIX_DIVISORS[None, :]) % 7
).astype(np.uint8)
CMY7_CODEBOOK.setflags(write=False)

CMY7_INVERSE = np.full((7, 7, 7, 7), -1, dtype=np.int16)
CMY7_INVERSE[tuple(CMY7_CODEBOOK.T)] = _CMY7_WORDS
CMY7_INVERSE.setflags(write=False)

_CMY7_BIT_SHIFTS = np.arange(CMY7_BITS_PER_PACK - 1, -1, -1,
                             dtype=np.int64)
_CMY7_CANDIDATE_BITS = (
    (_CMY7_WORDS[:, None] >> _CMY7_BIT_SHIFTS[None, :]) & 1
).astype(bool)
_CMY7_CANDIDATE_BITS.setflags(write=False)

# The same table as float, for folding a per-bit a-priori LLR vector into
# the candidate metric with one matrix product.
_CMY7_CANDIDATE_BITS_F = _CMY7_CANDIDATE_BITS.astype(np.float64)
_CMY7_CANDIDATE_BITS_F.setflags(write=False)

_CMY8_STATE_BITS = (
    (np.arange(8, dtype=np.uint8)[:, None]
     >> np.arange(3, dtype=np.uint8)[None, :]) & 1
).astype(bool)
_CMY8_STATE_BITS.setflags(write=False)


def _bits_last_axis(values: np.ndarray, width: int, name: str) -> np.ndarray:
    a = np.asarray(values)
    if a.ndim < 1 or a.shape[-1] != width:
        raise ValueError(f"{name} must have final axis {width}, got {a.shape}")
    if a.dtype.kind not in "buif" or not np.isfinite(a).all():
        raise ValueError(f"{name} must contain finite 0/1 values")
    if not np.isin(a, (0, 1)).all():
        raise ValueError(f"{name} must contain only 0/1")
    return a.astype(np.uint8, copy=False)


def _states(values: np.ndarray, max_state: int, name: str) -> np.ndarray:
    a = np.asarray(values)
    if a.dtype.kind not in "buif" or not np.isfinite(a).all():
        raise ValueError(f"{name} must contain finite integer state IDs")
    if not np.equal(a, np.floor(a)).all():
        raise ValueError(f"{name} must contain integer state IDs")
    if a.size and (int(a.min()) < 0 or int(a.max()) > max_state):
        raise ValueError(f"{name} state IDs must be in [0, {max_state}]")
    return a.astype(np.uint8, copy=False)


def _relative_scores(values: np.ndarray, n_relative: int,
                     tail: tuple[int, ...], name: str) -> np.ndarray:
    a = np.asarray(values)
    if a.ndim < len(tail) or a.shape[-len(tail):] != tail:
        suffix = ", ".join(str(v) for v in tail)
        raise ValueError(
            f"{name} must have trailing shape ({suffix}), got {a.shape}"
        )
    if a.dtype.kind not in "buif":
        raise ValueError(f"{name} must be a real numeric array")
    a = a.astype(np.float64, copy=False)
    if not np.isfinite(a).all():
        raise ValueError(f"{name} must contain only finite scores")
    assert tail[-1] == n_relative
    return a


def states_to_planes(states: np.ndarray) -> np.ndarray:
    """State IDs -> ``(..., 3)`` uint8 presence bits in C, M, Y order."""
    s = _states(states, int(CMYState.CMY), "states")
    return ((s[..., None] >> np.arange(3, dtype=np.uint8)) & 1).astype(
        np.uint8
    )


def planes_to_states(plane_bits: np.ndarray) -> np.ndarray:
    """``(..., 3)`` C/M/Y presence bits -> ``(...)`` uint8 state IDs."""
    b = _bits_last_axis(plane_bits, 3, "plane_bits")
    weights = np.asarray((1, 2, 4), dtype=np.uint8)
    return np.sum(b * weights, axis=-1, dtype=np.uint8)


def cmy8_map(bits_by_plane: np.ndarray) -> np.ndarray:
    """Direct CMY8 mapping: ``(..., 3)`` C/M/Y bits -> state IDs."""
    return planes_to_states(bits_by_plane)


def cmy8_inverse(states: np.ndarray) -> np.ndarray:
    """Inverse CMY8 mapping: state IDs -> ``(..., 3)`` C/M/Y bits."""
    return states_to_planes(states)


def cmy8_raw_marginal_llrs(
    relative_state_scores: np.ndarray,
) -> np.ndarray:
    """Raw CMY8 bit marginals from ``(..., 7)`` relative log scores.

    Score column ``s-1`` is ``log p(z|state=s) - log p(z|state=0)`` for
    state IDs 1..7.  The result has shape ``(..., 3)`` in C/M/Y order.
    Equal state priors are implicit.

    This is the exact joint-state marginalization *before* the historical
    per-component PAVA calibration.  It is a channel-math intermediate,
    not the final durable CMY8 evidence representation.
    """
    rel = _relative_scores(
        relative_state_scores, 7, (7,), "relative_state_scores"
    )
    scores = np.concatenate(
        (np.zeros(rel.shape[:-1] + (1,), dtype=np.float64), rel), axis=-1
    )
    out = np.empty(rel.shape[:-1] + (3,), dtype=np.float64)
    for plane in range(3):
        one = np.logaddexp.reduce(
            scores[..., _CMY8_STATE_BITS[:, plane]], axis=-1
        )
        zero = np.logaddexp.reduce(
            scores[..., ~_CMY8_STATE_BITS[:, plane]], axis=-1
        )
        out[..., plane] = one - zero
    return out


def cmy7_map(bits: np.ndarray) -> np.ndarray:
    """Map ``(..., 11)`` MSB-first bits to ``(..., 4)`` legal states."""
    b = _bits_last_axis(bits, CMY7_BITS_PER_PACK, "bits")
    powers = (1 << _CMY7_BIT_SHIFTS).astype(np.int64)
    words = np.sum(b.astype(np.int64) * powers, axis=-1, dtype=np.int64)
    return CMY7_CODEBOOK[words].copy()


def cmy7_inverse(states: np.ndarray) -> np.ndarray:
    """Invert complete ``(..., 4)`` CMY7 packs to MSB-first bits.

    The 353 radix-7 tuples outside the frozen 2,048-entry codebook are
    refused.  Incomplete packs are outside this provisional baseline.
    """
    s = _states(states, int(CMYState.MY), "states")
    if s.ndim < 1 or s.shape[-1] != CMY7_CELLS_PER_PACK:
        raise ValueError(
            f"states must have final axis {CMY7_CELLS_PER_PACK}, "
            f"got {s.shape}"
        )
    words = CMY7_INVERSE[s[..., 0], s[..., 1], s[..., 2], s[..., 3]]
    if np.any(words < 0):
        raise ValueError("states contain a tuple unused by CMY7 v0")
    return (
        (words[..., None].astype(np.int64)
         >> _CMY7_BIT_SHIFTS) & 1
    ).astype(np.uint8)


def state_score_margins(relative_state_scores: np.ndarray) -> np.ndarray:
    """Per-cell top1-minus-top2 over the seven CMY7 states.

    ``relative_state_scores`` is ``(..., 6)`` in the W-relative convention,
    so state 0 contributes its implicit zero.  The result is ``(...)`` and
    is always >= 0; exact ties (the all-planes-inked observation, whose
    three two-plane explanations score identically) give exactly 0.
    """
    rel = _relative_scores(
        relative_state_scores, 6, (6,), "relative_state_scores")
    scores = np.concatenate(
        (np.zeros(rel.shape[:-1] + (1,), dtype=np.float64), rel), axis=-1
    )
    ordered = np.partition(scores, -2, axis=-1)
    return ordered[..., -1] - ordered[..., -2]


def _prior_bit_llrs(values: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
    a = np.asarray(values)
    if a.shape != shape:
        raise ValueError(
            f"prior_bit_llrs must have shape {shape}, got {a.shape}")
    if a.dtype.kind not in "buif":
        raise ValueError("prior_bit_llrs must be a real numeric array")
    a = a.astype(np.float64, copy=False)
    if not np.isfinite(a).all():
        raise ValueError("prior_bit_llrs must contain only finite values")
    return a


def cmy7_soft_demap(relative_state_scores: np.ndarray,
                    prior_bit_llrs: np.ndarray | None = None) -> np.ndarray:
    """Exact CMY7 LLRs from complete-pack ``(..., 4, 6)`` state scores.

    The six score columns correspond to state IDs 1..6, relative to the
    implicit zero score of W/state 0.  Only the 2,048 codebook candidates
    participate.  Returns ``(..., 11)`` LLRs in the mapper's MSB-first bit
    order, with positive values favoring bit 1.

    ``prior_bit_llrs`` is the optional ``(..., 11)`` a-priori vector of an
    iterative (BICM-ID) demapper, in the same bit order and convention.  It
    is folded into every candidate's metric and then SUBTRACTED from the
    result, so the return value stays EXTRINSIC — the pack's own channel
    evidence about each bit, given what the prior says about its ten
    siblings, and never the prior fed back to itself.  Because the codebook
    realizes all 2,048 eleven-bit patterns, a prior alone (all scores zero)
    factorizes exactly and its extrinsic is zero, which is what keeps an
    unobserved pack silent.
    """
    rel = _relative_scores(
        relative_state_scores, 6, (CMY7_CELLS_PER_PACK, 6),
        "relative_state_scores",
    )
    prior = (
        None if prior_bit_llrs is None
        else _prior_bit_llrs(
            prior_bit_llrs, rel.shape[:-2] + (CMY7_BITS_PER_PACK,))
    )
    scores = np.concatenate(
        (np.zeros(rel.shape[:-1] + (1,), dtype=np.float64), rel), axis=-1
    )
    metric = np.zeros(rel.shape[:-2] + (CMY7_N_CANDIDATES,),
                      dtype=np.float64)
    for cell in range(CMY7_CELLS_PER_PACK):
        metric += np.take(
            scores[..., cell, :], CMY7_CODEBOOK[:, cell], axis=-1
        )
    if prior is not None:
        metric += prior @ _CMY7_CANDIDATE_BITS_F.T

    # Normalize once, then accumulate all eleven binary marginals in one
    # dense reduction.  A production tile has hundreds of packs, so eleven
    # separate masked logaddexp reductions needlessly revisit the same
    # 2,048 candidate metrics.  The normalized weights stay modest (roughly
    # 9--16 MiB for the current p120 rows) and make good use of the host's
    # vectorized matrix kernel.
    maximum = np.max(metric, axis=-1, keepdims=True)
    with np.errstate(under="ignore"):
        weights = np.exp(metric - maximum)
    one = weights @ _CMY7_CANDIDATE_BITS
    zero = weights @ (~_CMY7_CANDIDATE_BITS)
    with np.errstate(divide="ignore"):
        out = np.log(one) - np.log(zero)

    # Arbitrary finite callers may present a dynamic range large enough for
    # one normalized partition to underflow completely.  The durable CMY7
    # adapter is bounded far below that range, but retain the primitive's
    # robust behavior with a rare row-local log-domain fallback.
    # Sums near the subnormal frontier can remain positive while losing
    # material relative precision.  Each marginal contains 1,024 terms, so
    # keep the fast path only when both sums are comfortably normal.
    minimum_safe_sum = (
        (CMY7_N_CANDIDATES // 2) * np.finfo(np.float64).tiny)
    fallback = np.any(
        (one <= minimum_safe_sum) | (zero <= minimum_safe_sum),
        axis=-1,
    )
    if np.any(fallback):
        metric_rows = metric.reshape(-1, CMY7_N_CANDIDATES)
        out_rows = out.reshape(-1, CMY7_BITS_PER_PACK)
        selected = np.flatnonzero(fallback.reshape(-1))
        fallback_metric = metric_rows[selected]
        with np.errstate(under="ignore"):
            for bit in range(CMY7_BITS_PER_PACK):
                one_mask = _CMY7_CANDIDATE_BITS[:, bit]
                out_rows[selected, bit] = (
                    np.logaddexp.reduce(
                        fallback_metric[:, one_mask], axis=-1)
                    - np.logaddexp.reduce(
                        fallback_metric[:, ~one_mask], axis=-1)
                )
    if prior is not None:
        out -= prior
    return out
