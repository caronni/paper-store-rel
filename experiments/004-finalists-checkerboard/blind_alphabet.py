"""Blind (label-free) alphabet detection for the A-track — layer-1 legal.

The E004 QDA numbers train on same-sheet labels (genie training). The legal
detector clusters the per-cell density features with EM (full-covariance
Gaussians, weights FIXED uniform — the alphabet is uniform by construction),
initialized from the crosstalk-matrix-predicted state centroids. The
crosstalk matrix is DISC/CAL prior knowledge — engine calibration, not page
content — so the initialization is legitimate receiver knowledge, and the
cluster->state assignment comes with it (clusters keep the identity of the
centroid they grew from). GT is used by the CALLER for scoring only.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parents[1] / "src"))

from paperholo.channel.simulator import CROSSTALK_PLANES, M281_CROSSTALK_A  # noqa: E402

_CH_ROW = {"r": 0, "g": 1, "b": 2}


def predicted_centroids(state_names: list[str], feat_channels: list[str]
                        ) -> np.ndarray:
    """Density-domain centroid prediction per state from the measured
    crosstalk matrix: D[ch] = sum_p A[ch][p] * ink_p(state). The grey
    channel is approximated as the mean of r/g/b rows (init only — EM
    refines on the page itself)."""
    A = np.asarray(M281_CROSSTALK_A)
    rows = {**{c: A[i] for c, i in _CH_ROW.items()}, "grey": A.mean(axis=0)}
    mu = np.zeros((len(state_names), len(feat_channels)))
    for s, name in enumerate(state_names):
        ink = np.array([1.0 if p in name else 0.0 for p in CROSSTALK_PLANES])
        for f, ch in enumerate(feat_channels):
            mu[s, f] = float(rows[ch] @ ink)
    return mu


def em_gaussian_uniform(X: np.ndarray, mu0: np.ndarray, n_iter: int = 40,
                        ridge: float = 1e-6) -> dict:
    """EM for a uniform-weight full-covariance Gaussian mixture; returns
    responsibilities, means, covariances and the hard assignment."""
    n, d = X.shape
    k = mu0.shape[0]
    mu = mu0.copy()
    gcov = np.cov(X.T) + ridge * np.eye(d)
    cov = np.array([gcov / max(k, 2) for _ in range(k)])
    ll_prev = -np.inf
    for _ in range(n_iter):
        logp = np.empty((n, k))
        for s in range(k):
            dlt = X - mu[s]
            icov = np.linalg.inv(cov[s])
            _, ld = np.linalg.slogdet(cov[s])
            logp[:, s] = -0.5 * (np.einsum("ij,jk,ik->i", dlt, icov, dlt)
                                 + ld + d * np.log(2 * np.pi))
        m = logp.max(axis=1, keepdims=True)
        r = np.exp(logp - m)
        r /= r.sum(axis=1, keepdims=True)
        ll = float((m.ravel() + np.log(np.exp(logp - m).sum(axis=1))).mean())
        for s in range(k):
            w = r[:, s]
            tot = max(w.sum(), 1e-9)
            mu[s] = (w[:, None] * X).sum(axis=0) / tot
            dlt = X - mu[s]
            cov[s] = (w[:, None] * dlt).T @ dlt / tot + ridge * np.eye(d)
        if abs(ll - ll_prev) < 1e-7:
            break
        ll_prev = ll
    return {"resp": r, "mu": mu, "cov": cov,
            "pred": np.argmax(r, axis=1), "loglik": ll}
