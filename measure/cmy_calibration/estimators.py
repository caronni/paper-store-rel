"""R11 — the estimators: calibrated information, log-loss, hard error, ECE, reliability slope, and their intervals.

What: per form (FORMS) and the two combined conditionals "hi|lo" / "lo|hi", state-balanced means (each state 1/4
of the mass, or 1/2 within a sibling-conditioned subpopulation: hi|lo=0 on W u M, hi|lo=1 on Y u C, lo|hi=0 on
W u Y, lo|hi=1 on M u C; "hi|lo" = the equal-weight mean of its halves, i.e. every state through the form of its
own sibling):
    I = 1 - mean log2(1 + exp(-(2b - 1) L))     (unclamped; L = 0 contributes 0)
    log-loss (nats) = mean softplus(-(2b - 1) L); hard error (L > 0) != b with L = 0 half an error;
    ECE over 10 equal-width bins of sigma(L); reliability slope (a, c) of b ~ sigma(a L + c) by weighted Newton.
Intervals: percentile bootstrap over WINDOWS (page; one multinomial count matrix per (band-capture, regime) so
arms are paired), over CLUSTER ORIGINS (cold start, draws carried with their origin), Wilson 95 % for LDPC
success, and the exact McNemar test on discordant pairs.
Why: the protocol's 'Estimators' section.  How: per-group (window x state x form) sums, so a bootstrap resample is
one matrix product; the slope interval aggregates cells by (window, state, L rounded to 0.05 nats) — an
approximation stated in the report, the point estimate is exact.
"""
from __future__ import annotations

import math

import numpy as np

from measure.cmy_calibration.chains import HI, LO

LN2 = math.log(2.0)
ROWS = ("hi", "lo", "hi|lo=0", "hi|lo=1", "lo|hi=0", "lo|hi=1", "hi|lo", "lo|hi")
#: ROW_FORM[row, state] = the form a cell of that state is scored through in that row (-1 = not in the row).
ROW_FORM = np.array([[0, 0, 0, 0], [1, 1, 1, 1], [2, -1, 2, -1], [-1, 3, -1, 3], [4, -1, -1, 4], [-1, 5, 5, -1],
                     [2, 3, 2, 3], [4, 5, 5, 4]], np.int64)
ROW_BIT = np.array([0, 1, 0, 0, 1, 1, 0, 1])          # 0 = the hi bit is the target, 1 = the lo bit
Z95 = 1.959963984540054


def row_target(row: int, state: np.ndarray) -> np.ndarray:
    return (HI if ROW_BIT[row] == 0 else LO)[state]


def cell_losses(forms: np.ndarray, state: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(bits loss (N, 6), hard wrong (N, 6)) of every form against its own target bit (hi forms -> hi)."""
    target = np.stack([HI[state] if b == 0 else LO[state] for b in (0, 1, 0, 0, 1, 1)], 1).astype(np.float64)
    sgn = 2.0 * target - 1.0
    loss = np.logaddexp(0.0, -sgn * forms) / LN2
    wrong = np.where(forms == 0.0, 0.5, ((forms > 0) != (target > 0.5)).astype(np.float64))
    return loss, wrong


def group_sums(values: np.ndarray, state: np.ndarray, group: np.ndarray, n_groups: int) -> np.ndarray:
    """(G, 4, F) sums of values over cells by (group, state)."""
    key = group.astype(np.int64) * 4 + state.astype(np.int64)
    return np.stack([np.bincount(key, weights=values[:, f], minlength=n_groups * 4) for f in range(values.shape[1])],
                    1).reshape(n_groups, 4, values.shape[1])


def group_counts(state: np.ndarray, group: np.ndarray, n_groups: int) -> np.ndarray:
    key = group.astype(np.int64) * 4 + state.astype(np.int64)
    return np.bincount(key, minlength=n_groups * 4).reshape(n_groups, 4).astype(np.float64)


def row_means(S: np.ndarray, N: np.ndarray) -> np.ndarray:
    """State-balanced mean per row from per-state sums S (..., 4, 6) and counts N (..., 4) -> (..., 8)."""
    out = []
    with np.errstate(invalid="ignore", divide="ignore"):
        per = S / N[..., None]
    for row in range(len(ROWS)):
        cols = np.stack([per[..., s, ROW_FORM[row, s]] for s in range(4) if ROW_FORM[row, s] >= 0], -1)
        n_ok = np.isfinite(cols).sum(-1)
        tot = np.where(np.isfinite(cols), cols, 0.0).sum(-1)
        with np.errstate(invalid="ignore", divide="ignore"):
            out.append(np.where(n_ok > 0, tot / np.maximum(n_ok, 1), np.nan))
    return np.stack(out, -1)


def info_rows(forms: np.ndarray, state: np.ndarray) -> dict[str, np.ndarray]:
    """Point estimates per row: I (bits), logloss (nats), hard error."""
    loss, wrong = cell_losses(forms, state)
    g = np.zeros(state.size, np.int64)
    N = group_counts(state, g, 1)[0]
    I = 1.0 - row_means(group_sums(loss, state, g, 1)[0], N)
    err = row_means(group_sums(wrong, state, g, 1)[0], N)
    return {"I": I, "logloss": (1.0 - I) * LN2, "hard_err": err}


class WindowBootstrap:
    """One multinomial resample-count matrix over groups (windows or cluster origins), shared by every arm."""

    def __init__(self, n_groups: int, B: int, rng: np.random.Generator) -> None:
        self.n_groups = n_groups
        self.counts = rng.multinomial(n_groups, np.full(n_groups, 1.0 / n_groups), size=B).astype(np.float64)

    def info(self, forms: np.ndarray, state: np.ndarray, group: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(point I per row (8,), bootstrap I (B, 8))."""
        loss, _ = cell_losses(forms, state)
        S = group_sums(loss, state, group, self.n_groups)
        N = group_counts(state, group, self.n_groups)
        point = 1.0 - row_means(S.sum(0), N.sum(0))
        Sb = (self.counts @ S.reshape(self.n_groups, -1)).reshape(-1, 4, 6)
        Nb = self.counts @ N
        return point, 1.0 - row_means(Sb, Nb)

    def mean(self, values: np.ndarray, group: np.ndarray) -> tuple[float, np.ndarray]:
        """Plain mean of per-item values (cold draws) with items carried by their group."""
        s = np.bincount(group, weights=values, minlength=self.n_groups)
        n = np.bincount(group, minlength=self.n_groups).astype(np.float64)
        return float(values.mean()), (self.counts @ s) / np.maximum(self.counts @ n, 1e-300)


def ci(boot: np.ndarray, axis: int = 0) -> tuple[np.ndarray, np.ndarray]:
    return np.nanpercentile(boot, 2.5, axis=axis), np.nanpercentile(boot, 97.5, axis=axis)


def est(point: float, boot: np.ndarray) -> dict[str, float]:
    lo, hi = ci(np.asarray(boot, np.float64))
    return {"est": float(point), "lo": float(lo), "hi": float(hi)}


def state_weights(state: np.ndarray, member: np.ndarray) -> np.ndarray:
    """1 / (K n_s) over the member cells' present states, 0 elsewhere; sums to 1 over members."""
    w = np.zeros(state.size)
    present = [s for s in range(4) if (member & (state == s)).any()]
    for s in present:
        sel = member & (state == s)
        w[sel] = 1.0 / (len(present) * sel.sum())
    return w


def row_cells(forms: np.ndarray, state: np.ndarray, row: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(L, b, w) of one row: each member cell's LLR through its row form, its target bit, state-balanced weight."""
    fidx = ROW_FORM[row][state]
    member = fidx >= 0
    L = np.where(member, forms[np.arange(state.size), np.maximum(fidx, 0)], 0.0)
    return L[member], row_target(row, state)[member].astype(np.float64), state_weights(state, member)[member]


def ece(L: np.ndarray, b: np.ndarray, w: np.ndarray, bins: int = 10) -> float:
    p = 1.0 / (1.0 + np.exp(-np.clip(L, -700, 700)))
    k = np.minimum((p * bins).astype(np.int64), bins - 1)
    W = np.bincount(k, weights=w, minlength=bins)
    Wb = np.bincount(k, weights=w * b, minlength=bins)
    Wp = np.bincount(k, weights=w * p, minlength=bins)
    tot = W.sum()
    ok = W > 0
    return float(np.sum(np.abs(Wb[ok] - Wp[ok])) / tot) if tot > 0 else float("nan")


def logistic_slope(L: np.ndarray, b: np.ndarray, w: np.ndarray, iters: int = 50) -> tuple[float, float]:
    """Weighted logistic regression b ~ sigma(a L + c) by Newton's method (<= iters steps)."""
    a, c = 1.0, 0.0
    if w.sum() <= 0 or L.size == 0:
        return float("nan"), float("nan")
    for _ in range(iters):
        z = np.clip(a * L + c, -700, 700)
        p = 1.0 / (1.0 + np.exp(-z))
        g = np.array([np.sum(w * (p - b) * L), np.sum(w * (p - b))])
        v = w * p * (1 - p)
        H = np.array([[np.sum(v * L * L), np.sum(v * L)], [np.sum(v * L), np.sum(v)]]) + 1e-12 * np.eye(2)
        step = np.linalg.solve(H, g)
        a, c = a - float(step[0]), c - float(step[1])
        if float(np.abs(step).max()) < 1e-10:
            break
    return a, c


def slope_ci(forms: np.ndarray, state: np.ndarray, group: np.ndarray, row: int, boot: WindowBootstrap,
             B: int) -> tuple[float, float, float, float]:
    """(a, c, a_lo, a_hi): exact point fit; interval from B resamples on cells aggregated by
    (group, state, L rounded to 0.05)."""
    L, b, w = row_cells(forms, state, row)
    a, c = logistic_slope(L, b, w)
    fidx = ROW_FORM[row][state]
    member = fidx >= 0
    g, st = group[member], state[member]
    q = np.round(L / 0.05).astype(np.int64)
    keys = np.stack([g, st, q, b.astype(np.int64)], 1)
    uniq, inv = np.unique(keys, axis=0, return_inverse=True)
    inv = inv.ravel()
    cnt = np.bincount(inv, minlength=uniq.shape[0]).astype(np.float64)
    Lu, bu, gu, su = uniq[:, 2] * 0.05, uniq[:, 3].astype(np.float64), uniq[:, 0], uniq[:, 1]
    slopes = []
    for k in range(min(B, boot.counts.shape[0])):
        mult = boot.counts[k][gu] * cnt
        per_state = np.bincount(su, weights=mult, minlength=4)
        present = per_state > 0
        if not present.any():
            continue
        ws = np.where(present[su], mult / (present.sum() * np.maximum(per_state[su], 1e-300)), 0.0)
        slopes.append(logistic_slope(Lu, bu, ws)[0])
    lo, hi = (np.nanpercentile(slopes, [2.5, 97.5]) if slopes else (float("nan"), float("nan")))
    return a, c, float(lo), float(hi)


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def mcnemar_exact(x: np.ndarray, y: np.ndarray) -> float:
    """Two-sided exact McNemar p on paired booleans."""
    b = int(np.sum(x & ~y))
    c = int(np.sum(~x & y))
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2.0 ** n
    return float(min(1.0, 2.0 * tail))
