# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/de_engine.py
"""Density evolution for the systematic e-IRA ensemble of the search (scratch, Tier B1).

Ensemble (n = 4096 transmitted, no puncturing, BIAWGN, all-zero codeword):
  * info variable nodes: degree d with NODE fraction nu_d (a degree class = whole Z=64 block columns);
  * parity variable nodes: degree 2 (the dual-diagonal accumulator; the one degree-1 tail ignored);
  * check nodes: a info edges (NODE fraction w_a) + exactly 2 parity edges.
Two edge types: info edges (VN->CN mean vi, CN->VN mean ui) and parity edges (vp, up).

ga_threshold():  Chung's Gaussian approximation (consistent Gaussian, mean-only), vectorised over a batch
                 of profiles, bisection on Es/N0 [dB] (m0 = 2/sigma^2 = 4 Es/N0):
                   s_i = sum_d lam_d phi(m0 + (d-1) ui)          (lam = info EDGE fractions)
                   s_p = phi(m0 + up)
                   ui  = sum_a rho_a phi^-1(1 - (1-s_i)^(a-1) (1-s_p)^2)   (rho = info-edge-perspective)
                   up  = sum_a w_a   phi^-1(1 - (1-s_i)^a     (1-s_p))
                 phi(mu) = 1 - E tanh(L/2), L ~ N(mu, 2mu): numeric (quad) to mu = 40, asymptotic above,
                 held as a log-log table (cached next to this file).
mc_threshold():  population-dynamics (Monte-Carlo) density evolution of the same ensemble with exact
                 BP check updates (the "discretised DE" cross-check), bisection around a start point.
stability():     multi-edge stability of the degree-2 subgraph: spectral radius of
                 B [[lam2 (E_rho[a]-1), 2 lam2], [E_w[a], 1]] < 1, B = exp(-1/(2 sigma^2)).
                 With no degree-2 info column the radius is B < 1: always stable.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

_TABLE = Path(__file__).resolve().parent / "de_phi_table.npz"
MU_SPLICE = 40.0


def _phi_numeric(mu: float) -> float:
    from scipy import integrate
    s = math.sqrt(2 * mu)
    # E[2/(1+e^L)] = E[1 - tanh(L/2)]; 2/(1+e^L) = 2*expit(-L) computed stably
    f = lambda z: math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi) * 2.0 / (1.0 + math.exp(min(mu + s * z, 700.0)))
    lo, hi = -40.0, 40.0
    z0 = -mu / s
    pts = sorted({max(lo, min(hi, z0 + d)) for d in (-2.0, 0.0, 2.0)})
    v, _ = integrate.quad(f, lo, hi, points=pts, limit=400, epsabs=0, epsrel=1e-11)
    return v


def _phi_asym_log(mu):
    mu = np.asarray(mu, float)
    return 0.5 * np.log(np.pi / mu) - mu / 4 + np.log1p(-10.0 / (7.0 * mu))


def _build_table():
    lo_mu = np.logspace(-8, math.log10(MU_SPLICE), 900)
    lp_num = np.array([math.log(_phi_numeric(float(m))) for m in lo_mu])
    # splice: scale the asymptotic tail to meet the numeric value at MU_SPLICE (log offset -> 0 at inf)
    off = lp_num[-1] - float(_phi_asym_log(MU_SPLICE))
    hi_mu = np.logspace(math.log10(MU_SPLICE), 5, 700)[1:]
    lp_hi = _phi_asym_log(hi_mu) + off * (MU_SPLICE / hi_mu) ** 2
    mu = np.concatenate([[0.0], lo_mu, hi_mu])
    lphi = np.concatenate([[0.0], lp_num, lp_hi])
    return mu, lphi


def _load_table():
    if _TABLE.exists():
        z = np.load(_TABLE)
        return z["mu"], z["lphi"]
    mu, lphi = _build_table()
    try:
        np.savez(_TABLE, mu=mu, lphi=lphi)
    except OSError:
        pass
    return mu, lphi


_MU, _LPHI = _load_table()
_LMU = np.log(np.maximum(_MU, 1e-300))
# increasing axis for the inverse: -lphi increases with mu
_NEG_LPHI = -_LPHI


def log_phi(mu):
    """log phi(mu), vectorised; mu >= 0 (clipped to the table's top at 1e5)."""
    mu = np.clip(mu, 0.0, 1e5)
    out = np.interp(np.log(np.maximum(mu, 1e-300)), _LMU[1:], _LPHI[1:])
    return np.where(mu < 1e-8, mu * (_LPHI[1] / 1e-8), out)   # phi ~ 1 - c mu near 0


def phi_inv_log(ly):
    """phi^-1 from log y (y in (0, 1]); returns mu."""
    ly = np.minimum(ly, 0.0)
    return np.interp(-ly, _NEG_LPHI, _MU)


def esn0_db_to_m0(db):
    return 4.0 * 10 ** (np.asarray(db, float) / 10.0)


# ------------------------------------------------------------------ profile arrays
def profile_arrays(profiles, a_hist_list=None, mb=None):
    """profiles: list of dict {degree: n_block_columns}. Check info-degree distribution: from
    a_hist_list[i] (dict a -> count of checks) if given, else the BALANCED placement's
    concentrated one (E_b = sum d n_d block edges over mb block rows: x = E_b // mb, E_b % mb rows x+1).
    Returns (dvals, lam[P,D]), (avals, w[P,A], rho[P,A]), lam2[P]."""
    dvals = np.arange(1, 1 + max(max(p) for p in profiles), dtype=float)
    lam = np.zeros((len(profiles), dvals.size))
    for i, p in enumerate(profiles):
        for d, c in p.items():
            lam[i, d - 1] = d * c
    lam /= lam.sum(axis=1, keepdims=True)
    hists = []
    for i, p in enumerate(profiles):
        if a_hist_list is not None and a_hist_list[i] is not None:
            hists.append({int(a): float(c) for a, c in a_hist_list[i].items()})
        else:
            eb = sum(d * c for d, c in p.items())
            x, r = divmod(eb, mb)
            hists.append({x: float(mb - r), x + 1: float(r)} if r else {x: float(mb)})
    amax = max(max(h) for h in hists)
    avals = np.arange(0, amax + 1, dtype=float)
    w = np.zeros((len(profiles), avals.size))
    for i, h in enumerate(hists):
        for a, c in h.items():
            w[i, a] += c
    w /= w.sum(axis=1, keepdims=True)
    rho = w * avals[None, :]
    rho /= rho.sum(axis=1, keepdims=True)
    lam2 = lam[:, 1] if lam.shape[1] > 1 else np.zeros(len(profiles))
    return (dvals, lam), (avals, w, rho), lam2


def _ga_converges(m0, dvals, lam, avals, w, rho, max_iter, big=400.0):
    """Vectorised GA recursion; returns bool[P] (True = decoding succeeds)."""
    P = m0.size
    ui = np.zeros(P); up = np.zeros(P)
    ok = np.zeros(P, bool); dead = np.zeros(P, bool)
    am1 = np.maximum(avals - 1, 0)[None, :]
    live = np.arange(P)
    for _ in range(max_iter):
        m = m0[live]
        vi = m[:, None] + (dvals[None, :] - 1) * ui[live][:, None]
        s_i = (lam[live] * np.exp(log_phi(vi))).sum(axis=1)
        s_p = np.exp(log_phi(m + up[live]))
        lti = np.log1p(-np.minimum(s_i, 1 - 1e-16))[:, None]
        ltp = np.log1p(-np.minimum(s_p, 1 - 1e-16))[:, None]
        zi = am1 * lti + 2 * ltp
        zp = avals[None, :] * lti + ltp
        new_ui = (rho[live] * phi_inv_log(np.log(np.maximum(-np.expm1(zi), 1e-300)))).sum(axis=1)
        new_up = (w[live] * phi_inv_log(np.log(np.maximum(-np.expm1(zp), 1e-300)))).sum(axis=1)
        stuck = (np.abs(new_ui - ui[live]) < 1e-11 * (1 + new_ui)) & (np.abs(new_up - up[live]) < 1e-11 * (1 + new_up))
        ui[live], up[live] = new_ui, new_up
        win = (new_ui > big) & (new_up > big)
        ok[live[win]] = True
        dead[live[stuck & ~win]] = True
        live = live[~(win | stuck)]
        if live.size == 0:
            break
    return ok


def ga_threshold(profiles, mb, a_hist_list=None, lo=-8.0, hi=2.0, tol=0.002, max_iter=1500):
    """Batch GA threshold (Es/N0 dB) for a list of {degree: n_block_cols} profiles."""
    (dvals, lam), (avals, w, rho), _ = profile_arrays(profiles, a_hist_list, mb)
    P = len(profiles)
    lo_v = np.full(P, lo); hi_v = np.full(P, hi)
    while (hi_v - lo_v).max() > tol:
        mid = 0.5 * (lo_v + hi_v)
        ok = _ga_converges(esn0_db_to_m0(mid), dvals, lam, avals, w, rho, max_iter)
        hi_v = np.where(ok, mid, hi_v)
        lo_v = np.where(ok, lo_v, mid)
    return hi_v


def stability(profile, mb, esn0_db, a_hist=None):
    """Spectral radius of the degree-2 linearisation (< 1 = stable) at Es/N0 [dB]."""
    (dvals, lam), (avals, w, rho), lam2 = profile_arrays([profile], [a_hist] if a_hist else None, mb)
    sig2 = 1.0 / (2 * 10 ** (esn0_db / 10))
    B = math.exp(-1.0 / (2 * sig2))
    Er = float((rho[0] * avals).sum()); Ew = float((w[0] * avals).sum())
    M = B * np.array([[lam2[0] * (Er - 1), 2 * lam2[0]], [Ew, 1.0]])
    return float(max(abs(np.linalg.eigvals(M))))


# ------------------------------------------------------------------ Monte-Carlo DE
def _f(x):
    """f(x) = -log tanh(x/2), x > 0 (self-inverse)."""
    x = np.clip(x, 1e-12, 60.0)
    return -np.log(-np.expm1(-x)) + np.log1p(np.exp(-x))


def _mc_converges(profile, mb, esn0_db, a_hist, ns, max_iter, rng, cap=60.0):
    (dvals, lam), (avals, w, rho), _ = profile_arrays([profile], [a_hist] if a_hist else None, mb)
    lam, w, rho = lam[0], w[0], rho[0]
    sig2 = 1.0 / (2 * 10 ** (esn0_db / 10))
    mu = 2.0 / sig2
    ch = lambda n: mu + math.sqrt(2 * mu) * rng.standard_normal(n)
    Li = ch(ns); Lp = ch(ns)                       # VN->CN populations (first iteration: channel only)
    di = rng.choice(dvals.astype(int), size=ns, p=lam)
    ai_i = rng.choice(avals.astype(int), size=ns, p=rho)   # check info-degree seen from an info edge
    ai_p = rng.choice(avals.astype(int), size=ns, p=w)     # ... from a parity edge
    Dm = int(dvals.max())
    for it in range(max_iter):
        # CN -> info edge: (a-1) info + 2 parity inputs; CN -> parity edge: a info + 1 parity input
        def cn(n_info, n_par, size):
            kmax = int(n_info.max()) if n_info.size else 0
            idx_i = rng.integers(0, ns, size=(size, max(kmax, 1)))
            mask = np.arange(max(kmax, 1))[None, :] < n_info[:, None]
            xi = Li[idx_i]
            fs = np.where(mask, _f(np.abs(xi)), 0.0).sum(axis=1)
            sg = np.where(mask, np.sign(xi), 1.0).prod(axis=1)
            idx_p = rng.integers(0, ns, size=(size, n_par))
            xp = Lp[idx_p]
            fs += _f(np.abs(xp)).sum(axis=1)
            sg *= np.sign(xp).prod(axis=1)
            return sg * _f(fs)
        Ci = cn(np.maximum(ai_i - 1, 0), 2, ns)
        Cp = cn(ai_p, 1, ns)
        # VN -> CN
        idx = rng.integers(0, ns, size=(ns, Dm - 1)) if Dm > 1 else np.zeros((ns, 0), int)
        mask = np.arange(Dm - 1)[None, :] < (di - 1)[:, None]
        Li = np.clip(ch(ns) + np.where(mask, Ci[idx], 0.0).sum(axis=1), -cap, cap)
        Lp = np.clip(ch(ns) + Cp[rng.integers(0, ns, ns)], -cap, cap)
        pe = max(float((Li <= 0).mean()), float((Lp <= 0).mean()))
        if pe == 0.0 and float(np.median(Li)) > 0.8 * cap:
            return True
    return False


def mc_threshold(profile, mb, start_db, a_hist=None, ns=100_000, max_iter=300, tol=0.01, span=0.6, seed=1):
    """Population-dynamics DE threshold (Es/N0 dB) by bisection in [start-span, start+span]."""
    rng = np.random.default_rng(seed)
    lo, hi = start_db - span, start_db + span
    while not _mc_converges(profile, mb, hi, a_hist, ns, max_iter, rng):
        lo, hi = hi, hi + span
    while _mc_converges(profile, mb, lo, a_hist, ns, max_iter, rng):
        hi, lo = lo, lo - span
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if _mc_converges(profile, mb, mid, a_hist, ns, max_iter, rng):
            hi = mid
        else:
            lo = mid
    return hi
