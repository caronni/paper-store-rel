"""R11 — the cmy evidence algebra: QDA scores, the bound, the demap, the four chains, the fold-back, the
state-balanced PAVA, the floors, the label-space collapse test and the erasure law.

What: pure functions on per-cell arrays.  States are the MANIFEST index W0 C1 M2 Y3 (= presence ids 0, 1, 2, 4
in that order); the label bits follow R2: W=00, Y=01, M=10, C=11, so hi = 1 on {C, M} and lo = 1 on {C, Y}.  The
raw W-relative scores r = (r_C, r_M, r_Y) = q_X - q_W come from the receiver's own 4-class QDA
(holo.receiver.plugins.color_model.fit_qda / qda_log_scores, no prior term, so equal priors hold by
construction).  The six consumer forms (CMY-DESIGN :572-575) in FORMS order:
    hi = lse(sC, sM) - lse(0, sY)        lo = lse(sC, sY) - lse(0, sM)
    hi|lo=0 = sM    hi|lo=1 = sC - sY    lo|hi=0 = sY    lo|hi=1 = sC - sM
Each of the six maps calibrates one form on its raw statistic (the form of the UNBOUNDED r, E017.5); the chains
fold three maps back into scores (lo-first: a = L_lo, b = L_{hi|lo=0}, c = L_{hi|lo=1}; hi-first: a = L_hi,
b = L_{lo|hi=0}, c = L_{lo|hi=1}), six-maps keeps all six forms, the fallback emits the bounded raw triple
r~ = r / max(1, max|r| / 20).  Why: CMY-DESIGN §2.7 / §7c, the R11 ruling row.  How: the fold identities are
exact for any real a, b, c (1 / (1 - sigma(b)) = 1 + e^b), proved in the protocol and checked numerically by the
selfcheck stage; log sigma(x) = -logaddexp(0, -x) keeps them finite at the bound.
The state-balanced PAVA mirrors fit_component_pava (color_model.py:260-328) with per-STRATUM weights: each binary
class carries N/2 split equally over its present strata (w = N / (2 k_c n_s)); with strata = the labels it is
fit_component_pava bit for bit (pinned in selfcheck and smoke); with strata = the four states and both states of
each class present it is the protocol's w_i = 1/(K n_s) scaled to sum N.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from holo.receiver.plugins.color_model import (CMY8_CALIBRATION_MIN_CLASS_LABELS,
                                               CMY8_CALIBRATION_MIN_LABELS_PER_STATE,
                                               CMY8_CALIBRATION_MIN_STATES_PER_CLASS, QDA_COLLAPSE_DIST, QDA_RIDGE,
                                               PavaMap, QdaModel, fit_component_pava, fit_qda, qda_log_scores)
from holo.receiver.plugins.color_conditioning import (CONDITIONED_MIN_CLASS_LABELS, CONDITIONED_MIN_LABELS,
                                                      CONDITIONED_MIN_VALIDATION)
from holo.receiver.plugins.color_region_head import CMY7_RELATIVE_SCORE_BOUND

W, C, M, Y = 0, 1, 2, 3
STATE_NAMES = ("W", "C", "M", "Y")
HI = np.array([0, 1, 1, 0], np.uint8)
LO = np.array([0, 1, 0, 1], np.uint8)
FORMS = ("hi", "lo", "hi|lo=0", "hi|lo=1", "lo|hi=0", "lo|hi=1")
BOUND = float(CMY7_RELATIVE_SCORE_BOUND)


@dataclass(frozen=True)
class MapSpec:
    name: str
    form: int
    neg: tuple[int, ...]
    pos: tuple[int, ...]
    marginal: bool

    @property
    def states(self) -> tuple[int, ...]:
        return self.neg + self.pos


MAP_SPECS: tuple[MapSpec, ...] = (
    MapSpec("L_hi", 0, (W, Y), (C, M), True),
    MapSpec("L_lo", 1, (W, M), (C, Y), True),
    MapSpec("L_hi|lo=0", 2, (W,), (M,), False),
    MapSpec("L_hi|lo=1", 3, (Y,), (C,), False),
    MapSpec("L_lo|hi=0", 4, (W,), (Y,), False),
    MapSpec("L_lo|hi=1", 5, (M,), (C,), False),
)
CHAIN_MAPS: dict[str, tuple[int, ...]] = {"fallback": (), "lo-first": (1, 2, 3), "hi-first": (0, 4, 5),
                                          "six-maps": (0, 1, 2, 3, 4, 5)}
STORED_COLUMNS = {"fallback": 3, "lo-first": 3, "hi-first": 3, "six-maps": 6}


# ---------------------------------------------------------------- scores and the bound

def fit_model(X: np.ndarray, states: np.ndarray) -> QdaModel | None:
    """The receiver's QDA over the four cmy states in manifest order; None when the fit fails
    (np.linalg.LinAlgError is a ValueError, as fit_detector maps it to detector_fit_failed)."""
    try:
        return fit_qda(np.asarray(X, np.float64), np.asarray(states, np.int64), 4)
    except ValueError:
        return None


def raw_scores(model: QdaModel, X: np.ndarray) -> np.ndarray:
    """(N, 3) W-relative raw scores (r_C, r_M, r_Y)."""
    q = qda_log_scores(model, np.asarray(X, np.float64))
    return q[:, 1:] - q[:, :1]


def bound_triple(s: np.ndarray, bound: float = BOUND) -> tuple[np.ndarray, np.ndarray]:
    """cmy7's per-cell uniform divisor (color_region_head.py:322-327), applied last: (s / d, d > 1)."""
    d = np.maximum(1.0, np.max(np.abs(s), axis=1, keepdims=True) / bound)
    return s / d, d[:, 0] > 1.0


def demap(s: np.ndarray) -> np.ndarray:
    """(N, 6) label-bit LLRs in FORMS order from a score triple (sC, sM, sY), s_W = 0."""
    sC, sM, sY = s[:, 0], s[:, 1], s[:, 2]
    return np.stack([np.logaddexp(sC, sM) - np.logaddexp(0.0, sY), np.logaddexp(sC, sY) - np.logaddexp(0.0, sM),
                     sM, sC - sY, sY, sC - sM], 1)


def log_sigmoid(x: np.ndarray) -> np.ndarray:
    return -np.logaddexp(0.0, -x)


def fold(chain: str, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Three chain LLRs back into (sC, sM, sY) under equal priors (protocol 'Folds')."""
    lead = a - log_sigmoid(-b)
    if chain == "lo-first":
        return np.stack([lead + log_sigmoid(c), b, lead + log_sigmoid(-c)], 1)
    if chain == "hi-first":
        return np.stack([lead + log_sigmoid(c), lead + log_sigmoid(-c), b], 1)
    raise ValueError(chain)


def nll4(s: np.ndarray, state: np.ndarray) -> np.ndarray:
    """-ln softmax([0, sC, sM, sY])[true state] (fit_detector's held-out loss form)."""
    z = np.concatenate([np.zeros((s.shape[0], 1)), s], 1)
    zmax = z.max(1, keepdims=True)
    lse = zmax[:, 0] + np.log(np.exp(z - zmax).sum(1))
    return lse - z[np.arange(z.shape[0]), np.asarray(state, np.int64)]


# ---------------------------------------------------------------- PAVA

def _pav(unique_scores: np.ndarray, pos_w: np.ndarray, neg_w: np.ndarray, n_labels: int) -> PavaMap:
    """fit_component_pava's merge loop, clamp and score-0 node (color_model.py:279-328), on given group weights."""
    group_weights = pos_w + neg_w
    group_values = pos_w / group_weights
    values: list[float] = []
    weights: list[float] = []
    score_sums: list[float] = []
    for score, value, weight in zip(unique_scores, group_values, group_weights):
        values.append(float(value))
        weights.append(float(weight))
        score_sums.append(float(score) * float(weight))
        while len(values) > 1 and values[-2] >= values[-1]:
            weight = weights[-1] + weights[-2]
            values[-2] = (values[-1] * weights[-1] + values[-2] * weights[-2]) / weight
            weights[-2] = weight
            score_sums[-2] += score_sums[-1]
            values.pop()
            weights.pop()
            score_sums.pop()
    score_nodes = np.empty(len(values), dtype=np.float64)
    probability_nodes = np.empty(len(values), dtype=np.float64)
    pmin = 1.0 / (n_labels + 2.0)
    for index, (value, weight, score_sum) in enumerate(zip(values, weights, score_sums)):
        score_nodes[index] = score_sum / weight
        probability_nodes[index] = min(max(value, pmin), 1.0 - pmin)
    insertion = int(np.searchsorted(score_nodes, 0.0))
    if (0 < insertion < score_nodes.size and score_nodes[insertion - 1] < 0.0 < score_nodes[insertion]
            and probability_nodes[insertion - 1] <= 0.5 <= probability_nodes[insertion]):
        score_nodes = np.insert(score_nodes, insertion, 0.0)
        probability_nodes = np.insert(probability_nodes, insertion, 0.5)
    return PavaMap(score_nodes=score_nodes, probability_nodes=probability_nodes, n_labels=int(n_labels))


def fit_stratified_pava(scores: np.ndarray, labels: np.ndarray, strata: np.ndarray) -> PavaMap | None:
    """Weighted PAVA, each binary class N/2 split equally over its present strata; None if a class is empty.
    strata = labels reproduces fit_component_pava bit for bit; strata = states is the state-balanced entry."""
    raw_scores_ = np.asarray(scores, dtype=np.float64).ravel()
    raw_labels = np.asarray(labels, dtype=np.int64).ravel()
    raw_strata = np.asarray(strata, dtype=np.int64).ravel()
    if not (raw_labels == 0).any() or not (raw_labels == 1).any():
        return None
    order = np.argsort(raw_scores_, kind="stable")
    sorted_scores = raw_scores_[order]
    sorted_labels = raw_labels[order]
    sorted_strata = raw_strata[order]
    unique_scores, starts = np.unique(sorted_scores, return_index=True)
    total_weight = float(raw_labels.size)
    sums = {0: np.zeros(unique_scores.size), 1: np.zeros(unique_scores.size)}
    for cls in (0, 1):
        in_class = sorted_labels == cls
        present = np.unique(sorted_strata[in_class])
        k = float(present.size)
        for st in present:
            member = in_class & (sorted_strata == st)
            counts = np.add.reduceat(member.astype(np.float64), starts)
            sums[cls] = sums[cls] + counts * total_weight / (2.0 * k * float(member.sum()))
    return _pav(unique_scores, sums[1], sums[0], raw_labels.size)


def fit_class_balanced_pava(scores: np.ndarray, labels: np.ndarray) -> PavaMap | None:
    """The receiver's fit_component_pava itself, guarded against an empty class (it would divide by zero)."""
    lab = np.asarray(labels, np.int64)
    if not (lab == 0).any() or not (lab == 1).any():
        return None
    return fit_component_pava(scores, lab)


def map_population(spec: MapSpec, state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(member mask, binary label) of a map's population among cells of the given states."""
    member = np.isin(state, spec.states)
    return member, np.isin(state, spec.pos).astype(np.uint8)


def fit_map(spec: MapSpec, stat: np.ndarray, state: np.ndarray, weighting: str) -> PavaMap | None:
    """One map on its raw statistic over its population; 'w' = state-balanced, 'cb' = fit_component_pava.
    For a conditional map (one state per class) the two coincide by construction and 'w' calls the receiver."""
    member, label = map_population(spec, state)
    if weighting == "cb" or not spec.marginal:
        return fit_class_balanced_pava(stat[member], label[member])
    return fit_stratified_pava(stat[member], label[member], state[member])


# ---------------------------------------------------------------- floors

def qualify_marginal(spec: MapSpec, state: np.ndarray) -> tuple[bool, str | None]:
    """cmy8's rule (qualify_cmy8_support): >= 6 labels per class, >= 2 states with >= 3 labels in each class."""
    counts = np.bincount(np.asarray(state, np.int64), minlength=4)
    for cls, members in ((0, spec.neg), (1, spec.pos)):
        if int(counts[list(members)].sum()) < CMY8_CALIBRATION_MIN_CLASS_LABELS:
            return False, f"class_labels:{cls}"
    for cls, members in ((0, spec.neg), (1, spec.pos)):
        if int((counts[list(members)] >= CMY8_CALIBRATION_MIN_LABELS_PER_STATE).sum()) \
                < CMY8_CALIBRATION_MIN_STATES_PER_CLASS:
            return False, f"state_diversity:{cls}"
    return True, None


def qualify_conditional(spec: MapSpec, fit_state: np.ndarray, n_validation: int) -> tuple[bool, str | None]:
    """A4b's rule (_fit_stratum): >= 40 fit labels with >= 6 per class, and >= 20 validation rows."""
    counts = np.bincount(np.asarray(fit_state, np.int64), minlength=4)
    n_neg, n_pos = int(counts[list(spec.neg)].sum()), int(counts[list(spec.pos)].sum())
    if n_neg + n_pos < CONDITIONED_MIN_LABELS or min(n_neg, n_pos) < CONDITIONED_MIN_CLASS_LABELS:
        return False, "search_class_starved"
    if n_validation < CONDITIONED_MIN_VALIDATION:
        return False, "heldout_starved"
    return True, None


# ---------------------------------------------------------------- label-space collapse

def collapse_flags(X: np.ndarray, state: np.ndarray, model: QdaModel) -> dict[str, object]:
    """fit_qda's whitened-mean test (color_model.py:141-148, 173-189) recomputed here and keyed to LABEL space:
    (W,Y) or (C,M) close -> lo collapsed; (W,M) or (C,Y) -> hi; (W,C) or (M,Y) -> both streams."""
    x = np.asarray(X, np.float64)
    y = np.asarray(state, np.int64)
    n, d = x.shape
    counts = np.bincount(y, minlength=4)
    residual = x - model.means[y]
    pooled = residual.T @ residual / max(n - 4, 1)
    pooled = pooled + QDA_RIDGE * max(float(np.trace(pooled)) / d, 1e-12) * np.eye(d)
    wm = np.linalg.solve(np.linalg.cholesky(pooled), model.means.T).T
    pairs: list[str] = []
    lo = hi = False
    for a, b, streams in ((W, Y, "lo"), (C, M, "lo"), (W, M, "hi"), (C, Y, "hi"), (W, C, "both"),
                          (M, Y, "both")):
        if counts[a] == 0 or counts[b] == 0:
            continue
        thr = QDA_COLLAPSE_DIST + float(np.sqrt(d * (1.0 / counts[a] + 1.0 / counts[b])))
        if float(np.linalg.norm(wm[a] - wm[b])) < thr:
            pairs.append(f"{STATE_NAMES[a]}{STATE_NAMES[b]}")
            lo |= streams in ("lo", "both")
            hi |= streams in ("hi", "both")
    return {"lo": lo, "hi": hi, "pairs": pairs}


# ---------------------------------------------------------------- the chains

def erase_triple(s: np.ndarray, erase_lo: bool, erase_hi: bool, l_hi: np.ndarray | None,
                 l_lo: np.ndarray | None) -> np.ndarray:
    """§7c's erasure law in score space: unsupported lo -> (L_hi, L_hi, 0); unsupported hi -> (L_lo, 0, L_lo);
    both -> zeros."""
    if erase_lo and erase_hi:
        return np.zeros_like(s)
    if erase_lo:
        return np.stack([l_hi, l_hi, np.zeros_like(l_hi)], 1)
    if erase_hi:
        return np.stack([l_lo, np.zeros_like(l_lo), l_lo], 1)
    return s


@dataclass(frozen=True)
class ChainOut:
    forms: np.ndarray          # (N, 6) label LLRs as emitted (after the bound)
    stored: np.ndarray         # (N, 3) bounded triple, or (N, 6) forms for six-maps
    bind: np.ndarray           # (N,) bool: the bound changed the cell


def chain_output(chain: str, pieces: dict[int, np.ndarray | None], r: np.ndarray, erase_lo: bool = False,
                 erase_hi: bool = False) -> ChainOut:
    """The emitted evidence of one chain on cells with raw scores r: pieces[form] is a fitted map's LLR on the
    form's raw statistic, or None for the fallback piece (that form on the bounded raw triple).  Under an erased
    stream the surviving marginal comes from the chain's own map when it has one, else the bounded raw form."""
    rt, rbind = bound_triple(r)
    fb = demap(rt)

    def piece(k: int) -> np.ndarray:
        got = pieces.get(k)
        return fb[:, k] if got is None else got

    if chain == "six-maps":
        f = np.stack([piece(k) for k in range(6)], 1)
        if erase_lo or erase_hi:
            s = erase_triple(np.zeros((r.shape[0], 3)), erase_lo, erase_hi, f[:, 0], f[:, 1])
            f = demap(s)
        clipped = np.clip(f, -BOUND, BOUND)
        return ChainOut(clipped, clipped, (np.abs(f) > BOUND).any(1))
    if chain == "fallback":
        s = erase_triple(rt, erase_lo, erase_hi, fb[:, 0], fb[:, 1])
        if erase_lo or erase_hi:
            s, rbind = bound_triple(s)
        return ChainOut(demap(s), s, rbind)
    a, b, c = (piece(k) for k in CHAIN_MAPS[chain])
    s = erase_triple(fold(chain, a, b, c), erase_lo, erase_hi, piece(0), piece(1))
    s, bind = bound_triple(s)
    return ChainOut(demap(s), s, bind)


def gate_triple(chain: str, out: ChainOut) -> np.ndarray:
    """The score triple a region gate scores: the stored triple, or for six-maps its lo-first fold."""
    if chain != "six-maps":
        return out.stored
    f = out.forms
    return bound_triple(fold("lo-first", f[:, 1], f[:, 2], f[:, 3]))[0]
