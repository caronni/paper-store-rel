"""B2 trellis decoder: iterative row/column BCJR for the i2w3 2-D RLL field.

The sampler's row-DP state space IS the trellis: 5 states for (min_ink=2,
min_white=3) — w1, w2, w3+ (white run 1, 2, >=3) and i1, i2+ — with the
run-length constraint encoded in the allowed transitions:

    w1 -0-> w2      w2 -0-> w3+     w3+ -0-> w3+     w3+ -1-> i1
    i1 -1-> i2+     i2+ -1-> i2+    i2+ -0-> w1

Border runs obey the minimums (asserted at generation), so chains START in
{w1, i1} (first bit opens a run) and must END in {w3+, i2+} (completed
minimums) — the same boundary conditions as gen_modprobe._sample_row's DP.

Emissions: blind 2-component GMM on the tile's dot means (weights fixed at
the construction ink prior — a format constant), log-domain. The vertical
constraint enters as per-dot extrinsic priors from a column pass (the same
BCJR on the transpose), iterated turbo-style. Everything is vectorized
across the perpendicular axis (all rows decoded simultaneously).

Layer-1 status: the DETECTOR is fully blind; the WARP under it is genie
until E005's sync strips exist (free-form 1-dot fields sit at Nyquist for
self-clocking — dd_warp module docstring). Trellis-vs-naive is therefore
reported as a detector delta at fixed (genie) geometry.
"""
from __future__ import annotations

import numpy as np

# state indices
W1, W2, W3, I1, I2 = 0, 1, 2, 3, 4
N_STATES = 5
# transitions: (from_state, bit, to_state)
TRANS = [(W1, 0, W2), (W2, 0, W3), (W3, 0, W3), (W3, 1, I1),
         (I1, 1, I2), (I2, 1, I2), (I2, 0, W1)]
START = {W1: 0, I1: 1}          # state after the first bit: bit value
END_STATES = (W3, I2)
NEG = -1e30


def fit_emissions(means: np.ndarray, p_ink: float, n_iter: int = 50) -> dict:
    """Blind 2-GMM on dot means, weights fixed at the construction prior.
    Returns per-dot log-likelihoods (llw, lli) — ink is the DARK component."""
    z = means.ravel().astype(np.float64)
    q = np.quantile(z, (p_ink * 0.5, 1 - (1 - p_ink) * 0.5))
    mu = np.array([q[1], q[0]])                 # [white, ink]
    sg = np.array([z.std() * 0.5 + 1e-3] * 2)
    w = np.array([1 - p_ink, p_ink])
    for _ in range(n_iter):
        lp = np.stack([np.log(w[k]) - 0.5 * ((z - mu[k]) / sg[k]) ** 2
                       - np.log(sg[k]) for k in range(2)])
        m = lp.max(axis=0)
        r = np.exp(lp - m)
        r /= r.sum(axis=0)
        for k in range(2):
            tot = max(r[k].sum(), 1e-9)
            mu_new = (r[k] * z).sum() / tot
            sg[k] = np.sqrt(max((r[k] * (z - mu_new) ** 2).sum() / tot, 1e-6))
            mu[k] = mu_new
    if mu[1] > mu[0]:                            # enforce ink = dark
        mu, sg = mu[::-1].copy(), sg[::-1].copy()
    ll = np.stack([-0.5 * ((means - mu[k]) / sg[k]) ** 2 - np.log(sg[k])
                   for k in range(2)])
    return {"llw": ll[0], "lli": ll[1], "mu": mu.tolist(), "sigma": sg.tolist()}


def _logsumexp2(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    m = np.maximum(a, b)
    return m + np.log1p(np.exp(-np.abs(a - b)))


def bcjr_lines(llw: np.ndarray, lli: np.ndarray,
               prior_llr: np.ndarray | None) -> np.ndarray:
    """BCJR over the 5-state i2w3 chain for EVERY line at once.
    llw/lli: (n_lines, L) log-likelihoods; prior_llr: extrinsic ink-vs-white
    priors (n_lines, L) or None. Returns EXTRINSIC output LLRs (ink minus
    white), i.e. posterior minus channel minus prior."""
    n, L = llw.shape
    g = np.zeros((2, n, L))                      # per-bit log metric
    g[0] = llw
    g[1] = lli
    if prior_llr is not None:
        # symmetric prior split: +/- L/2 keeps extrinsic bookkeeping simple
        g[0] -= prior_llr / 2.0
        g[1] += prior_llr / 2.0

    alpha = np.full((L, n, N_STATES), NEG)
    for s, bit in START.items():
        alpha[0, :, s] = g[bit, :, 0]
    for t in range(1, L):
        a_prev = alpha[t - 1]
        a_new = np.full((n, N_STATES), NEG)
        for (fs, bit, ts) in TRANS:
            cand = a_prev[:, fs] + g[bit, :, t]
            a_new[:, ts] = _logsumexp2(a_new[:, ts], cand)
        alpha[t] = a_new

    beta = np.full((L, n, N_STATES), NEG)
    beta[L - 1, :, list(END_STATES)] = 0.0
    for t in range(L - 2, -1, -1):
        b_next = beta[t + 1]
        b_new = np.full((n, N_STATES), NEG)
        for (fs, bit, ts) in TRANS:
            cand = b_next[:, ts] + g[bit, :, t + 1]
            b_new[:, fs] = _logsumexp2(b_new[:, fs], cand)
        beta[t] = b_new

    # per-bit posteriors: bit at t == bit labeling the ARRIVING transition;
    # state s at time t implies bit(t) = 1 for s in {i1, i2+}, else 0
    post = alpha + beta                          # (L, n, S)
    ink_states = [I1, I2]
    white_states = [W1, W2, W3]
    li = post[:, :, ink_states].max(axis=2)
    lw = post[:, :, white_states].max(axis=2)
    # soft-max over remaining states (2 or 3) — logsumexp
    li = _logsumexp2(post[:, :, I1], post[:, :, I2])
    lw = _logsumexp2(_logsumexp2(post[:, :, W1], post[:, :, W2]),
                     post[:, :, W3])
    total = (li - lw).T                          # (n, L) posterior LLR
    ext = total - (lli - llw)
    if prior_llr is not None:
        ext = ext - prior_llr
    return np.clip(ext, -60.0, 60.0)


def decode_i2w3(means: np.ndarray, p_ink: float, n_turbo: int = 3) -> dict:
    """Iterative row/column BCJR on a dot-means field. Returns hard bits and
    the total posterior LLR after the final iteration."""
    em = fit_emissions(means, p_ink)
    llw, lli = em["llw"], em["lli"]
    ch_llr = lli - llw
    ext_row = np.zeros_like(ch_llr)
    ext_col = np.zeros_like(ch_llr)
    for _ in range(n_turbo):
        ext_row = bcjr_lines(llw, lli, ext_col)
        ext_col = bcjr_lines(llw.T, lli.T, ext_row.T).T
    total = ch_llr + ext_row + ext_col
    return {"bits": (total > 0).astype(np.uint8), "llr": total,
            "emissions": {"mu": em["mu"], "sigma": em["sigma"]}}


# ---------------------------------------------------------------------------
# v1: ISI-aware turbo detection — the measured channel is ISI-dominated
# (PSF sigma ~1 dot at 1-dot features), so per-dot independent emissions
# starve the trellis. Soft interference cancellation with blind, decision-
# directed 3x3 ISI taps + local-median background removal (the same
# background rule as the naive detector), then the RLL trellis on the
# cleaned channel. Classic turbo-ISI / PRML structure.
# ---------------------------------------------------------------------------

_SHIFTS = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]


def _shifted(a: np.ndarray, dy: int, dx: int, fill: float) -> np.ndarray:
    out = np.full_like(a, fill, dtype=np.float64)
    ys = slice(max(dy, 0), a.shape[0] + min(dy, 0))
    yd = slice(max(-dy, 0), a.shape[0] + min(-dy, 0))
    xs = slice(max(dx, 0), a.shape[1] + min(dx, 0))
    xd = slice(max(-dx, 0), a.shape[1] + min(-dx, 0))
    out[yd, xd] = a[ys, xs]
    return out


def fit_isi_taps(resid: np.ndarray, bits: np.ndarray, p_ink: float
                 ) -> tuple[np.ndarray, float, float]:
    """LSQ fit resid ~ c + sum_k h_k * bit_k over the 3x3 neighborhood,
    using (decision-directed) bit estimates. Returns (h[9], c, sigma)."""
    cols = [_shifted(bits.astype(np.float64), dy, dx, p_ink).ravel()
            for dy, dx in _SHIFTS]
    A = np.stack(cols + [np.ones(resid.size)], axis=1)
    sol, *_ = np.linalg.lstsq(A, resid.ravel(), rcond=None)
    h, c = sol[:9], float(sol[9])
    pred = A @ sol
    sigma = float(np.std(resid.ravel() - pred)) + 1e-6
    return h, c, sigma


def decode_i2w3_isi(means: np.ndarray, p_ink: float, n_turbo: int = 4,
                    med_size: int = 31) -> dict:
    """Soft-interference-cancelling turbo RLL detection:
    resid = means - local median; fit 3x3 ISI taps on initial fixed-rate
    decisions; each iteration cancels the neighbors' expected contribution
    using the current soft bits, scores the center dot against its two
    hypotheses, and runs the row+column RLL BCJR for extrinsics."""
    from scipy import ndimage as _ndi

    m = np.asarray(means, np.float64)
    resid = m - _ndi.median_filter(m, size=med_size, mode="nearest")
    thr = np.quantile(resid, p_ink)
    bits0 = (resid < thr).astype(np.uint8)       # naive fixed-rate start
    h, c, sigma = fit_isi_taps(resid, bits0, p_ink)
    k_center = _SHIFTS.index((0, 0))

    pi = np.full_like(resid, p_ink)
    pi[bits0 == 1] = 0.9
    pi[bits0 == 0] = 0.1
    ext_row = np.zeros_like(resid)
    ext_col = np.zeros_like(resid)
    taps_refit = False
    for it in range(n_turbo):
        cancel = np.full_like(resid, c)
        for k, (dy, dx) in enumerate(_SHIFTS):
            if k == k_center:
                continue
            cancel += h[k] * _shifted(pi, dy, dx, p_ink)
        clean = resid - cancel
        llw = -0.5 * (clean / sigma) ** 2
        lli = -0.5 * ((clean - h[k_center]) / sigma) ** 2
        ext_row = bcjr_lines(llw, lli, ext_col)
        ext_col = bcjr_lines(llw.T, lli.T, ext_row.T).T
        total = (lli - llw) + ext_row + ext_col
        pi = 1.0 / (1.0 + np.exp(-np.clip(total, -30, 30)))
        if not taps_refit and it >= 1:           # one refit on better bits
            h, c, sigma = fit_isi_taps(resid, (total > 0).astype(np.uint8),
                                       p_ink)
            taps_refit = True
    return {"bits": (total > 0).astype(np.uint8), "llr": total,
            "isi_taps": h.tolist(), "isi_c": c, "sigma": sigma}
