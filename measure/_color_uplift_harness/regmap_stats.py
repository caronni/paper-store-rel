"""Pure statistics for the PK6/A2 registration-field analysis.

Implements the pre-registered plan (stats review, 2026-08-10) with no
I/O and no state: robust per-window summaries, DerSimonian–Laird
between-window variance with a Q-profile lower bound, the placebo
lattice-translation null, the synchronized within-window bootstrap,
the min-separation thinning, and the deployed-arm ΔMSE gate formula.
Every stochastic routine takes an explicit seed (repo determinism law).
"""
from __future__ import annotations

import numpy as np

MEDIAN_VARIANCE_FACTOR = float(np.pi / 2.0)


def robust_scale(values: np.ndarray) -> float:
    """1.4826 * MAD; NaN below two observations."""
    data = np.asarray(values, np.float64)
    if data.size < 2:
        return float("nan")
    return float(1.4826 * np.median(np.abs(data - np.median(data))))


MEDIAN_BOOT_REPS = 200
MEDIAN_BOOT_SEED = 20260810


def window_summaries(
    z: np.ndarray,
    window_of: np.ndarray,
    n_windows: int,
    min_n: int = 4,
) -> dict:
    """Per-window median / robust scale / count; windows below min_n drop.

    Returns arrays over the KEPT windows plus the kept window ids.
    ``med_var`` is the BOOTSTRAP variance of the window median (seeded,
    200 reps): the asymptotic pi/2 formula underestimates it at
    realistic n_w, which inflates DL's Q on null data and pushes the
    Q-profile lower bound above zero with no effect present (measured
    on synthetic nulls: q/df 1.43 under the asymptotic formula).
    """
    medians, scales, counts, kept, med_var = [], [], [], [], []
    for window in range(n_windows):
        rows = z[window_of == window]
        if rows.size < min_n:
            continue
        kept.append(window)
        medians.append(float(np.median(rows)))
        scales.append(robust_scale(rows))
        counts.append(int(rows.size))
        rng = np.random.default_rng(MEDIAN_BOOT_SEED + window)
        draws = rows[rng.integers(0, rows.size,
                                  (MEDIAN_BOOT_REPS, rows.size))]
        med_var.append(float(np.var(np.median(draws, axis=1), ddof=1)))
    return {
        "window_ids": np.asarray(kept, np.int64),
        "medians": np.asarray(medians, np.float64),
        "scales": np.asarray(scales, np.float64),
        "counts": np.asarray(counts, np.int64),
        "med_var": np.asarray(med_var, np.float64),
        "dropped": int(n_windows - len(kept)),
    }


def median_variances(summary_or_scales, counts: np.ndarray | None = None
                     ) -> np.ndarray:
    """Bootstrap median variances from a ``window_summaries`` dict.

    The legacy two-array form (scales, counts) keeps the asymptotic
    pi/2 formula for callers that explicitly want it.
    """
    if isinstance(summary_or_scales, dict):
        return np.asarray(summary_or_scales["med_var"], np.float64)
    return (np.asarray(summary_or_scales, np.float64) ** 2
            * MEDIAN_VARIANCE_FACTOR
            / np.asarray(counts, np.float64))


def dersimonian_laird(
    means: np.ndarray,
    variances: np.ndarray,
) -> dict:
    """DL tau^2 over per-window means with known within-variances.

    Returns tau2, the Q statistic, its degrees of freedom, and the
    fixed-effect weights' normalizer needed by the Q-profile bound.
    """
    y = np.asarray(means, np.float64)
    v = np.asarray(variances, np.float64)
    keep = np.isfinite(y) & np.isfinite(v) & (v > 0)
    y, v = y[keep], v[keep]
    k = y.size
    if k < 3:
        return {"tau2": float("nan"), "q": float("nan"),
                "df": max(0, k - 1), "n_windows": k,
                "mu": float("nan")}
    w = 1.0 / v
    mu = float(np.sum(w * y) / np.sum(w))
    q = float(np.sum(w * (y - mu) ** 2))
    c = float(np.sum(w) - np.sum(w ** 2) / np.sum(w))
    tau2 = max(0.0, (q - (k - 1)) / c)
    return {"tau2": tau2, "q": q, "df": k - 1, "n_windows": k, "mu": mu}


def _generalized_q(y: np.ndarray, v: np.ndarray, tau2: float) -> float:
    w = 1.0 / (v + tau2)
    mu = np.sum(w * y) / np.sum(w)
    return float(np.sum(w * (y - mu) ** 2))


def q_profile_lower_bound(
    means: np.ndarray,
    variances: np.ndarray,
    level: float = 0.99,
    threshold: float | None = None,
) -> float:
    """One-sided lower confidence bound on tau^2 (Q-profile method).

    Finds tau2 such that the generalized Q statistic equals
    ``threshold``.  The chi-square quantile default assumes KNOWN
    within variances — with estimated (bootstrap) variances it has a
    measured ~26% null false-positive rate on ragged data, so gate
    consumers must pass a resampling-calibrated threshold
    (``calibrated_tau2_lower_bound``).
    """
    from scipy import stats

    y = np.asarray(means, np.float64)
    v = np.asarray(variances, np.float64)
    keep = np.isfinite(y) & np.isfinite(v) & (v > 0)
    y, v = y[keep], v[keep]
    k = y.size
    if k < 3:
        return float("nan")
    if threshold is None:
        threshold = float(stats.chi2.ppf(level, k - 1))
    if _generalized_q(y, v, 0.0) <= threshold:
        return 0.0
    low, high = 0.0, 1.0
    while _generalized_q(y, v, high) > threshold:
        high *= 4.0
        if high >= 1e6:
            return float("nan")
    for _ in range(80):
        mid = 0.5 * (low + high)
        if _generalized_q(y, v, mid) > threshold:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def half_split_design_effect(
    groups: list[np.ndarray],
    cells: list[np.ndarray],
    naive_variances: np.ndarray,
    min_n: int = 8,
) -> float:
    """Empirical inflation of the window-median variance (review M6).

    Each window's anchors are split into two spatial halves (by cell y,
    ties by x); ``(m1-m2)^2/4`` estimates the median's true sampling
    variance under within-window correlation the iid bootstrap cannot
    see.  Returns pooled(half-split) / pooled(naive), floored at 1 —
    positively correlated halves make this an UNDERestimate, and
    sub-window smooth structure lands in the noise (both conservative
    for the between-window effect under test).
    """
    split_terms, naive_terms = [], []
    for values, cell_yx, naive in zip(groups, cells, naive_variances):
        if values.size < min_n or not np.isfinite(naive):
            continue
        order = np.lexsort((cell_yx[:, 1], cell_yx[:, 0]))
        half = values.size // 2
        first = values[order[:half]]
        second = values[order[half:]]
        delta = float(np.median(first) - np.median(second))
        split_terms.append(delta * delta / 4.0)
        naive_terms.append(float(naive))
    if len(split_terms) < 6:
        return 1.0
    return max(1.0, float(np.sum(split_terms) / np.sum(naive_terms)))


def calibrated_tau2_lower_bound(
    groups: list[np.ndarray],
    cells: list[np.ndarray],
    naive_variances: np.ndarray,
    level: float = 0.99,
    n_reps: int = 400,
    seed: int = 0,
) -> dict:
    """tau^2 lower bound with resampling-calibrated threshold + DEFF.

    Two corrections the plain Q-profile lacks (review B3/M6), both in
    the conservative direction for a build gate: (1) within-window
    variances are ESTIMATED, so the Q threshold comes from the null
    resampling distribution of the generalized Q (centered iid
    within-window draws, same estimator) instead of chi-square; (2)
    variances carry the half-split design effect so within-window
    spatial correlation cannot masquerade as between-window signal.
    The iid null cannot reproduce the correlation itself — DEFF-scaled
    weights are the documented approximation.
    """
    medians = np.asarray([np.median(g) for g in groups], np.float64)
    deff = half_split_design_effect(groups, cells, naive_variances)
    variances = np.asarray(naive_variances, np.float64) * deff
    keep = np.isfinite(medians) & np.isfinite(variances) & (variances > 0)
    if keep.sum() < 6:
        return {"tau2_lb": float("nan"), "deff": deff,
                "threshold": float("nan")}
    rng = np.random.default_rng(seed)
    null_q = np.empty(n_reps, np.float64)
    kept_groups = [g for g, k in zip(groups, keep) if k]
    kept_variances = variances[keep]
    for rep in range(n_reps):
        boot_medians = np.asarray([
            np.median((g - np.median(g))[rng.integers(0, g.size, g.size)])
            for g in kept_groups], np.float64)
        null_q[rep] = _generalized_q(boot_medians, kept_variances, 0.0)
    threshold = float(np.quantile(null_q, level))
    lb = q_profile_lower_bound(
        medians[keep], kept_variances, threshold=threshold)
    dl = dersimonian_laird(medians[keep], kept_variances)
    return {"tau2_lb": lb, "deff": deff, "threshold": threshold,
            "tau2_deff": dl["tau2"]}


def _plane_groups(window_of: np.ndarray, comps: list[np.ndarray],
                  min_n: int) -> list[list[np.ndarray]]:
    groups: list[list[np.ndarray]] = []
    for window in np.unique(window_of):
        rows = np.flatnonzero(window_of == window)
        if rows.size >= min_n:
            groups.append([z[rows] for z in comps])
    return groups


def _omnibus_total(plane_group_lists) -> tuple[float, int]:
    total, count = 0.0, 0
    for groups in plane_group_lists:
        if len(groups) >= 6:
            for comp in range(len(groups[0])):
                total += standardized_q([g[comp] for g in groups])
                count += 1
    return total, count


def grouping_zscore(plane_group_lists, n_reps: int, rng) -> float:
    """Self-normalized omnibus: (T - mean T*)/sd T* under the
    grouping's OWN centered within-group resampling null.  This is
    what makes groupings of different block counts and sizes
    commensurable (review B2: the raw standardized-Q sum is strongly
    group-size dependent, so a translated lattice's T cannot be
    compared to the true lattice's T directly).
    """
    observed, count = _omnibus_total(plane_group_lists)
    if count == 0:
        return float("nan")
    centered = [
        [[z - np.median(z) for z in window_comps]
         for window_comps in groups]
        for groups in plane_group_lists]
    nulls = np.empty(n_reps, np.float64)
    for rep in range(n_reps):
        resampled = []
        for groups in centered:
            rep_groups = []
            for window_comps in groups:
                draw = rng.integers(
                    0, window_comps[0].size, window_comps[0].size)
                rep_groups.append([z[draw] for z in window_comps])
            resampled.append(rep_groups)
        nulls[rep] = _omnibus_total(resampled)[0]
    spread = float(np.std(nulls, ddof=1))
    return float((observed - float(np.mean(nulls)))
                 / max(spread, 1e-12))


def calibrated_placebo_pvalue(
    plane_frames: list[dict],
    stride_cells: int,
    n_translations: int,
    n_reps: int,
    seed: int,
    min_n: int = 4,
) -> dict:
    """The lattice-translation placebo on self-normalized z-scores.

    ``plane_frames``: per plane {cells (n,2), z_by_comp, window_of}
    where window_of is the TRUE (recorded) grouping.  Each translation
    regroups every plane's anchors by a shifted stride lattice; every
    grouping (true and placebo) is reduced to its own resampling
    z-score, and p = (1 + #{Z_placebo >= Z_true}) / (n + 1).  A smooth
    field scores placebo-typical; a window-locked field scores extreme
    only at the true lattice.
    """
    rng = np.random.default_rng(seed)
    true_lists = [
        _plane_groups(np.asarray(frame["window_of"], np.int64),
                      [np.asarray(z, np.float64)
                       for z in frame["z_by_comp"]], min_n)
        for frame in plane_frames]
    z_true = grouping_zscore(true_lists, n_reps, rng)
    z_placebo = np.empty(n_translations, np.float64)
    for index in range(n_translations):
        offset = rng.integers(0, stride_cells, size=2)
        lists = []
        for frame in plane_frames:
            cells = np.asarray(frame["cells"], np.int64)
            block_yx = (cells + offset[None, :]) // stride_cells
            _unique, window_of = np.unique(
                block_yx[:, 0] * 100_000 + block_yx[:, 1],
                return_inverse=True)
            lists.append(_plane_groups(
                window_of,
                [np.asarray(z, np.float64)
                 for z in frame["z_by_comp"]], min_n))
        z_placebo[index] = grouping_zscore(lists, n_reps, rng)
    finite = z_placebo[np.isfinite(z_placebo)]
    p = float((1 + np.sum(finite >= z_true)) / (finite.size + 1))
    return {"p": p, "z_true": float(z_true),
            "z_placebo_mean": float(np.mean(finite)),
            "z_placebo_p99": float(np.percentile(finite, 99)),
            "n_effective": int(finite.size)}


def standardized_q(groups: list[np.ndarray]) -> float:
    """(Q - df)/sqrt(2 df) of the DL Q over per-group medians."""
    medians = np.asarray([np.median(g) for g in groups], np.float64)
    variances = np.asarray(
        [robust_scale(g) ** 2 * MEDIAN_VARIANCE_FACTOR / g.size
         for g in groups], np.float64)
    result = dersimonian_laird(medians, variances)
    q = result["q"] if np.isfinite(result["q"]) else 0.0
    df = max(1, result["df"])
    return float((q - df) / np.sqrt(2.0 * df))


def synchronized_bootstrap_pvalue(
    plane_frames: list[dict],
    n_windows: int,
    n_reps: int,
    seed: int,
    min_n: int = 4,
) -> dict:
    """Within-window null bootstrap of the omnibus statistic.

    ``plane_frames``: one dict per plane with ``window_of`` (window
    index per anchor) and ``z_by_comp`` (a list of per-component value
    arrays over the SAME anchors — x and y of one plane share its
    anchor set).  Under H0 each window's values are exchangeable draws
    around a common center, so each rep resamples every window's own
    CENTERED values with replacement — drawing indices ONCE per
    (plane, window) and applying them to every component of that plane
    (synchronized replicates, Westfall–Young-compatible).  Returns the
    omnibus p plus per-component null quantiles for max-T secondaries.
    """
    prepared = []
    raw = []
    for frame in plane_frames:
        window_of = np.asarray(frame["window_of"], np.int64)
        comps = [np.asarray(z, np.float64) for z in frame["z_by_comp"]]
        groups: list[list[np.ndarray]] = []
        raw_groups: list[list[np.ndarray]] = []
        for window in range(n_windows):
            rows = np.flatnonzero(window_of == window)
            if rows.size >= min_n:
                # Centered pools feed the NULL resampling only; the
                # observed statistic must see the uncentered values.
                groups.append([
                    z[rows] - np.median(z[rows]) for z in comps])
                raw_groups.append([z[rows] for z in comps])
        prepared.append(groups)
        raw.append(raw_groups)

    def omnibus(frames) -> tuple[float, list[float]]:
        total = 0.0
        per_component = []
        for groups in frames:
            if not groups:
                continue
            n_comps = len(groups[0])
            for comp in range(n_comps):
                value = standardized_q([g[comp] for g in groups])
                per_component.append(value)
                total += value
        return total, per_component

    observed, observed_components = omnibus(raw)
    rng = np.random.default_rng(seed)
    null_totals = np.empty(n_reps, np.float64)
    null_max = np.empty(n_reps, np.float64)
    for rep in range(n_reps):
        resampled = []
        for groups in prepared:
            rep_groups = []
            for window_comps in groups:
                size = window_comps[0].size
                draw = rng.integers(0, size, size)
                rep_groups.append([z[draw] for z in window_comps])
            resampled.append(rep_groups)
        total, components = omnibus(resampled)
        null_totals[rep] = total
        null_max[rep] = max(components) if components else float("nan")
    p = float((1 + np.sum(null_totals >= observed)) / (n_reps + 1))
    return {
        "p": p,
        "observed": float(observed),
        "observed_components": [float(v) for v in observed_components],
        "null_max_quantiles": {
            "q95": float(np.nanpercentile(null_max, 95)),
            "q99": float(np.nanpercentile(null_max, 99))},
    }


def min_separation_thin(
    cells_yx: np.ndarray,
    window_of: np.ndarray,
    min_separation: int,
    seed: int,
) -> np.ndarray:
    """Greedy seeded thinning: within each window keep anchors pairwise
    >= min_separation cells apart (Chebyshev).  Returns a boolean mask.
    """
    cells = np.asarray(cells_yx, np.int64)
    window_of = np.asarray(window_of, np.int64)
    keep = np.zeros(cells.shape[0], np.bool_)
    if min_separation <= 0:
        keep[:] = True
        return keep
    rng = np.random.default_rng(seed)
    for window in np.unique(window_of):
        indices = np.flatnonzero(window_of == window)
        order = indices[rng.permutation(indices.size)]
        chosen: list[int] = []
        for index in order:
            cell = cells[index]
            ok = True
            for other in chosen:
                if (max(abs(int(cell[0]) - int(cells[other][0])),
                        abs(int(cell[1]) - int(cells[other][1])))
                        < min_separation):
                    ok = False
                    break
            if ok:
                chosen.append(int(index))
        keep[chosen] = True
    return keep


def correlogram(
    cells_yx: np.ndarray,
    z: np.ndarray,
    window_of: np.ndarray,
    max_distance: float = 12.0,
    bins: tuple = (1.5, 2.5, 3.5, 5.5, 8.5, 12.5),
) -> dict:
    """Within-window pair correlation of centered z vs cell distance."""
    cells = np.asarray(cells_yx, np.float64)
    z = np.asarray(z, np.float64)
    window_of = np.asarray(window_of, np.int64)
    centered = z.copy()
    for window in np.unique(window_of):
        rows = window_of == window
        if rows.sum() >= 4:
            centered[rows] = z[rows] - np.median(z[rows])
        else:
            centered[rows] = np.nan
    edges = (0.0,) + tuple(bins)
    sums = np.zeros(len(edges) - 1)
    squares_a = np.zeros(len(edges) - 1)
    squares_b = np.zeros(len(edges) - 1)
    counts = np.zeros(len(edges) - 1, np.int64)
    for window in np.unique(window_of):
        indices = np.flatnonzero(
            (window_of == window) & np.isfinite(centered))
        if indices.size < 2 or indices.size > 4000:
            continue
        sub_cells = cells[indices]
        sub_z = centered[indices]
        delta = sub_cells[:, None, :] - sub_cells[None, :, :]
        distance = np.sqrt((delta ** 2).sum(axis=2))
        upper = np.triu_indices(indices.size, 1)
        d = distance[upper]
        a = np.repeat(sub_z[:, None], indices.size, 1)[upper]
        b = np.repeat(sub_z[None, :], indices.size, 0)[upper]
        which = np.searchsorted(edges, d, side="right") - 1
        inside = (which >= 0) & (which < len(edges) - 1)
        np.add.at(sums, which[inside], (a * b)[inside])
        np.add.at(squares_a, which[inside], (a * a)[inside])
        np.add.at(squares_b, which[inside], (b * b)[inside])
        np.add.at(counts, which[inside], 1)
    rho = sums / np.sqrt(squares_a * squares_b + 1e-300)
    return {
        "bin_edges": [float(v) for v in edges],
        "rho": [float(v) for v in rho],
        "pairs": [int(v) for v in counts],
    }


def delta_mse_gate(
    uncertified_weight: np.ndarray,
    n_production: np.ndarray,
    tau2_lower_bound: float,
    sigma2_window: np.ndarray,
    kappa: float = 8.0,
) -> dict:
    """The deployed-arm MSE gate (stats review S5, plan line 11-ii).

    DeltaMSE = sum_w u_w * [ (n_w^2 + 2 n_w kappa) tau2_LB - n_w sigma_w^2 ]
                         / (n_w + kappa)^2
    Positive means the kappa-shrunk per-window constant beats the exact
    region model in u-weighted MSE.  Windows with n_w = 0 contribute 0
    (the arm falls back to the region model there).
    """
    u = np.asarray(uncertified_weight, np.float64)
    n = np.asarray(n_production, np.float64)
    s2 = np.asarray(sigma2_window, np.float64)
    keep = np.isfinite(u) & np.isfinite(n) & np.isfinite(s2) & (n > 0)
    u, n, s2 = u[keep], n[keep], s2[keep]
    numerator = (n ** 2 + 2.0 * n * kappa) * tau2_lower_bound - n * s2
    terms = u * numerator / (n + kappa) ** 2
    return {
        "delta_mse": float(terms.sum()),
        "positive_windows": int(np.sum(terms > 0)),
        "windows": int(terms.size),
        "uncertified_weight_total": float(u.sum()),
    }


def shrunk_correction_rms(
    uncertified_weight: np.ndarray,
    n_production: np.ndarray,
    median_x: np.ndarray,
    median_y: np.ndarray,
    cell_dots: float,
    kappa: float = 8.0,
) -> float:
    """u-weighted RMS of the applied per-window correction, in CELLS."""
    u = np.asarray(uncertified_weight, np.float64)
    n = np.asarray(n_production, np.float64)
    mx = np.asarray(median_x, np.float64)
    my = np.asarray(median_y, np.float64)
    keep = (np.isfinite(u) & np.isfinite(n) & (n > 0)
            & np.isfinite(mx) & np.isfinite(my))
    u, n, mx, my = u[keep], n[keep], mx[keep], my[keep]
    if u.sum() <= 0:
        return float("nan")
    shrink = n / (n + kappa)
    magnitude2 = (shrink * mx) ** 2 + (shrink * my) ** 2
    return float(np.sqrt(np.sum(u * magnitude2) / (2.0 * u.sum()))
                 / cell_dots)


def ks_uniform_pvalue(fractional: np.ndarray) -> dict:
    """KS test of fractional parts against U[0,1) (peak-lock pre-gate)."""
    from scipy import stats

    data = np.asarray(fractional, np.float64)
    data = data[np.isfinite(data)]
    if data.size < 20:
        return {"statistic": float("nan"), "p": float("nan"),
                "n": int(data.size)}
    result = stats.kstest(data, "uniform")
    return {"statistic": float(result.statistic),
            "p": float(result.pvalue), "n": int(data.size)}


def rotate_offsets_to_page(
    off_xy: np.ndarray,
    rot_k: int,
) -> np.ndarray:
    """Window-local offset vectors -> page frame (rot90 Jacobian)."""
    off = np.asarray(off_xy, np.float64)
    dx, dy = off[:, 0], off[:, 1]
    if rot_k == 0:
        return np.stack((dx, dy), axis=1)
    if rot_k == 1:
        return np.stack((dy, -dx), axis=1)
    if rot_k == 2:
        return np.stack((-dx, -dy), axis=1)
    return np.stack((-dy, dx), axis=1)
