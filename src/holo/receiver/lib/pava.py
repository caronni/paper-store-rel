from __future__ import annotations

import numpy as np

#: Frozen E023 marginal-calibration bars.  The held-out bar is a TOTAL
#: count; the search bar is PER CLASS, because a one-sided population
#: cannot identify a probability map.  09-detect-calibrate-k.md:84.
CAL_MIN_PER_CLASS: int = 10
CAL_MIN_HELDOUT: int = 10
#: The 018.7 floor for the one seam `clamp_for`'s by-construction bound
#: below does not reach: a node set whose probabilities are 0 or 1 --
#: never a `_pava_nodes` fit, but reachable through a stored row --
#: interpolates to an infinite LLR, and that infinity comes back as NaN
#: in the loss.  The floor is the probability whose log-odds is the
#: decoder's own clip (`LLR_CLIP` = 20.0 in lib/ldpc.py; the two may not
#: drift), so it cannot bite a fit: that clamp is 1/(n+2), and log(n+1)
#: reaches 20 only past half a billion search labels.
CAL_PROBABILITY_FLOOR: float = 1.0 / (1.0 + float(np.exp(20.0)))

#: Frozen ctx-pava-v1 constants, E023b.1: nine bins = 0..8 inked
#: neighbours, offsets bounded to +-4 and forced non-increasing (an
#: inkier neighbourhood may only move a cell toward white), one
#: synthetic label pair per bin as prior.  09-detect-calibrate-k.md:119.
N_CONTEXT_BINS: int = 9
CTX_OFFSET_LIMIT: float = 4.0
#: The ONE place a bounded-LLR clamp is explicit (018.7).  It is
#: applied at correction time in the calibrate plugin, not here, and
#: only to cells that HAVE a context bin.
CTX_LLR_CLAMP: float = 12.0
CTX_BIN_PRIOR: float = 1.0
CTX_MIN_SEARCH: int = 80
CTX_MIN_SEARCH_PER_CLASS: int = 20
CTX_MIN_VALIDATION: int = 40
CTX_MIN_VALIDATION_PER_CLASS: int = 10
CTX_ROOT_TOL: float = 1e-12

#: Dispatch only: the run-length pooling path is taken when label runs
#: average at least this many samples.  Both pooling paths must build
#: bit-identical blocks, so this number may never change a result.
PAVA_RUN_RATIO_DIVISOR: int = 3
#: The radix key packs an order-preserving float32 bit pattern above
#: the row index, which is what makes it stable.  The -0.0 and NaN
#: guards are exactly the two cases where that bit order and the float
#: comparison disagree; drop either and this becomes a DIFFERENT sort.
PAVA_INDEX_BITS: int = 32
PAVA_INDEX_LIMIT: int = 1 << PAVA_INDEX_BITS
F32_SIGN_BIT: int = 0x80000000
F32_MAGNITUDE_MASK: int = 0x7FFFFFFF
F32_INFINITY_BITS: int = 0x7F800000


def _stable_order(raw: np.ndarray, widened: np.ndarray) -> np.ndarray:
    if raw.dtype == np.float32 and raw.size < PAVA_INDEX_LIMIT:
        flat = raw.ravel()
        bits = flat.view(np.uint32)
        negative_zero = bits == np.uint32(F32_SIGN_BIT)
        not_finite = (bits & np.uint32(F32_MAGNITUDE_MASK)) > np.uint32(
            F32_INFINITY_BITS)
        if not negative_zero.any() and not not_finite.any():
            key = np.where(bits >> np.uint32(31), ~bits,
                           bits | np.uint32(F32_SIGN_BIT))
            packed = key.astype(np.uint64) << np.uint64(PAVA_INDEX_BITS)
            packed |= np.arange(flat.size, dtype=np.uint64)
            packed.sort(kind="stable")
            return (packed & np.uint64(PAVA_INDEX_LIMIT - 1)).astype(np.intp)
    return np.argsort(widened, kind="stable")


def _pooled_blocks_flat(
        sequence: list[float]) -> tuple[list[float], list[float]]:
    vals: list[float] = []
    wts: list[float] = []
    push_value = vals.append
    push_weight = wts.append
    pop_value = vals.pop
    pop_weight = wts.pop
    stream = iter(sequence)
    top_value = next(stream)
    top_weight = 1.0
    for value in stream:
        if top_value >= value:
            weight = top_weight + 1.0
            top_value = (value + top_value * top_weight) / weight
            top_weight = weight
            while vals and vals[-1] >= top_value:
                under_value = pop_value()
                under_weight = pop_weight()
                weight = top_weight + under_weight
                top_value = (top_value * top_weight
                             + under_value * under_weight) / weight
                top_weight = weight
        else:
            push_value(top_value)
            push_weight(top_weight)
            top_value = value
            top_weight = 1.0
    push_value(top_value)
    push_weight(top_weight)
    return vals, wts


def _pooled_blocks_runs(
        run_values: list[float],
        run_counts: list[int]) -> tuple[list[float], list[float]]:
    vals: list[float] = []
    wts: list[float] = []
    push_value = vals.append
    push_weight = wts.append
    pop_value = vals.pop
    pop_weight = wts.pop
    top_value = run_values[0]
    top_weight = 1.0
    first = True
    for value, run_count in zip(run_values, run_counts):
        count = run_count - 1 if first else run_count
        first = False
        if value == 1.0:
            if top_value == 1.0:
                top_weight += count
                continue
            if top_value < 1.0:
                push_value(top_value)
                push_weight(top_weight)
                top_value = 1.0
                top_weight = float(count)
                continue
        elif value == 0.0:
            if top_value == 0.0:
                top_weight += count
                continue
            if top_value < 0.0:
                push_value(top_value)
                push_weight(top_weight)
                top_value = 0.0
                top_weight = float(count)
                continue
        for _ in range(count):
            if top_value >= value:
                weight = top_weight + 1.0
                top_value = (value + top_value * top_weight) / weight
                top_weight = weight
                while vals and vals[-1] >= top_value:
                    under_value = pop_value()
                    under_weight = pop_weight()
                    weight = top_weight + under_weight
                    top_value = (top_value * top_weight
                                 + under_value * under_weight) / weight
                    top_weight = weight
            else:
                push_value(top_value)
                push_weight(top_weight)
                top_value = value
                top_weight = 1.0
    push_value(top_value)
    push_weight(top_weight)
    return vals, wts


def _pooled_blocks(y: np.ndarray) -> tuple[list[float], list[float]]:
    n_samples = int(y.size)
    edges = np.flatnonzero(y[1:] != y[:-1]) + 1
    if (edges.size + 1) * PAVA_RUN_RATIO_DIVISOR > n_samples:
        return _pooled_blocks_flat(y.tolist())
    starts = np.empty(edges.size + 1, np.int64)
    starts[0] = 0
    starts[1:] = edges
    bounds = np.empty(starts.size + 1, np.int64)
    bounds[:-1] = starts
    bounds[-1] = n_samples
    counts = np.diff(bounds)
    return _pooled_blocks_runs(y[starts].tolist(), counts.tolist())


def _pava_nodes(scores: np.ndarray,
                labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    raw = np.asarray(scores).ravel()
    s = np.asarray(scores, np.float64).ravel()
    y = np.asarray(labels, np.float64).ravel()
    if s.size == 0:
        return np.empty(0), np.empty(0)
    order = _stable_order(raw, s)
    s, y = s[order], y[order]
    vals, wts = _pooled_blocks(y)
    nodes_s = np.empty(len(vals))
    nodes_p = np.empty(len(vals))
    start = 0
    pmin = 1.0 / (s.size + 2.0)
    for index, (value, weight) in enumerate(zip(vals, wts)):
        stop = start + int(round(weight))
        nodes_s[index] = s[start:min(stop, s.size)].mean()
        nodes_p[index] = min(max(value, pmin), 1.0 - pmin)
        start = stop
    return nodes_s, nodes_p


#: Equal knots are possible under the historical tie order, and
#: np.interp's rightmost-equal-knot answer is part of the pinned
#: result: keep np.interp.  09-detect-calibrate-k.md:104-105.
def calibration_probability(scores: np.ndarray, knots: np.ndarray,
                            probabilities: np.ndarray) -> np.ndarray:
    raw = np.asarray(scores, dtype=np.float64)
    return np.interp(raw, knots, probabilities)


def calibration_llr(scores: np.ndarray, knots: np.ndarray,
                    probabilities: np.ndarray) -> np.ndarray:
    p = np.clip(calibration_probability(scores, knots, probabilities),
                CAL_PROBABILITY_FLOOR, 1.0 - CAL_PROBABILITY_FLOOR)
    return np.log(p / (1.0 - p))


#: The 018.7 bounded-LLR invariant, by construction and not by a clip:
#: the fit clamps each block's probability into [1/(n+2), 1-1/(n+2)],
#: so |llr| <= log(n+1).  Change one of the two and the bound becomes
#: a lie.  09-detect-calibrate-k.md:106-108.
def clamp_for(n_search_labels: int) -> float:
    return float(np.log1p(int(n_search_labels)))


#: THE canonical two-branch sigmoid; scipy.special.expit is BANNED
#: (1-3 ulp apart on ~45% of negative inputs, v0.39 ruling 10.3) and
#: the offset bisection below reads its exact value.
def sigmoid(x: np.ndarray) -> np.ndarray:
    ex = np.exp(-np.abs(x))
    return np.where(x >= 0.0, 1.0, ex) / (1.0 + ex)


def _residual(llr: np.ndarray, weights: np.ndarray, offset: float,
              target: float, shifted: np.ndarray,
              ex: np.ndarray) -> float:
    np.add(llr, offset, out=shifted)
    np.abs(shifted, out=ex)
    np.negative(ex, out=ex)
    np.exp(ex, out=ex)
    probability = np.where(shifted >= 0.0, 1.0, ex)
    np.add(ex, 1.0, out=ex)
    np.divide(probability, ex, out=probability)
    np.multiply(weights, probability, out=probability)
    return float(np.add.reduce(probability) - target)


def _solve_offset(llr: np.ndarray, labels: np.ndarray,
                  weights: np.ndarray) -> float:
    target = float(np.sum(weights * labels))
    shifted = np.empty(llr.size, np.float64)
    ex = np.empty(llr.size, np.float64)
    lo, hi = -CTX_OFFSET_LIMIT, CTX_OFFSET_LIMIT
    if _residual(llr, weights, lo, target, shifted, ex) >= 0.0:
        return lo
    if _residual(llr, weights, hi, target, shifted, ex) <= 0.0:
        return hi
    if _residual(llr, weights, 0.0, target, shifted, ex) == 0.0:
        return 0.0
    while hi - lo > CTX_ROOT_TOL:
        mid = (lo + hi) * 0.5
        if _residual(llr, weights, mid, target, shifted, ex) < 0.0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def _ordered_context_offsets(baseline_llr: np.ndarray,
                             neighbour_count: np.ndarray,
                             labels: np.ndarray,
                             weights: np.ndarray) -> np.ndarray:
    blocks: list[dict[str, object]] = []
    for bin_index in range(N_CONTEXT_BINS):
        select = neighbour_count == bin_index
        logits = np.concatenate(
            (baseline_llr[select], np.array([0.0, 0.0])))
        block_labels = np.concatenate(
            (labels[select], np.array([False, True])))
        block_weights = np.concatenate(
            (weights[select],
             np.full(2, CTX_BIN_PRIOR, dtype=np.float64)))
        blocks.append({
            "bins": [bin_index], "llr": logits, "labels": block_labels,
            "weights": block_weights,
            "offset": _solve_offset(logits, block_labels, block_weights),
        })
        while (len(blocks) >= 2
               and float(blocks[-2]["offset"]) < float(blocks[-1]["offset"])):
            right = blocks.pop()
            left = blocks.pop()
            logits = np.concatenate((left["llr"], right["llr"]))
            block_labels = np.concatenate((left["labels"], right["labels"]))
            block_weights = np.concatenate((left["weights"], right["weights"]))
            blocks.append({
                "bins": list(left["bins"]) + list(right["bins"]),
                "llr": logits, "labels": block_labels,
                "weights": block_weights,
                "offset": _solve_offset(logits, block_labels, block_weights),
            })
    offsets = np.empty(N_CONTEXT_BINS, dtype=np.float64)
    for block in blocks:
        offsets[np.asarray(block["bins"], dtype=np.int64)] = float(
            block["offset"])
    return offsets


def _logloss(llr: np.ndarray, labels: np.ndarray,
             weights: np.ndarray) -> float:
    signed = np.where(labels, -llr, llr)
    losses = np.logaddexp(0.0, signed)
    return float(np.sum(weights * losses) / np.sum(weights))


def _binary_logloss(llr: np.ndarray, labels: np.ndarray,
                    weights: np.ndarray | None = None) -> float:
    x = np.asarray(llr, np.float64)
    y = np.asarray(labels, np.float64)
    losses = np.logaddexp(0.0, x) - y * x
    if weights is None:
        return float(np.mean(losses))
    w = np.asarray(weights, np.float64)
    return float(np.sum(w * losses) / np.sum(w))


def probability_logloss(probabilities: np.ndarray,
                        labels: np.ndarray) -> float:
    p = np.asarray(probabilities, np.float64)
    y = np.asarray(labels, np.float64)
    return float(-np.mean(y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))


#: Seven cmy7 states.  The head's fit population is furniture-heavy
#: (measured on the synthetic cmy7 field: 45% W, 39% one dust state), so
#: an unweighted NLL fits the furniture log-prior into the bias and makes
#: payload evidence worse; balancing keeps the head a CALIBRATION.
def class_balanced_weights(states: np.ndarray,
                           n_classes: int = 7) -> np.ndarray:
    labels = np.asarray(states, np.int64)
    counts = np.bincount(labels, minlength=n_classes)
    weights = np.where(counts[labels] > 0, 1.0 / counts[labels], 0.0)
    total = float(weights.sum())
    if total <= 0.0:
        return np.ones(labels.size, np.float64)
    return weights * (labels.size / total)
