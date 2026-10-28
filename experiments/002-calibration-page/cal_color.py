"""cal_color — color separation & cell alphabet family (experiment 002).

Family analyzer built on the FROZEN cal_core contract (ANALYZER-CONTRACT.md).
Measures, from the REAL color scan of the printed CAL-1 page:

(a) overlay solids C,M,Y,K,CM,CY,MY,CMY,KCMY + paper white -> optical densities
    -> least-squares 3x4 crosstalk matrix A (d_RGB = A @ t_CMYK), residuals,
    condition number of the CMY 3x3 block (unmix feasibility gate ~8, panel
    cal:channel-measurement M2), Dmax per plane, and the K-vs-CMY-stack
    density-space colinearity margin (Mahalanobis over solid-patch pixel
    scatter, M4).
(b) 8-state CMY cell=3 field: per-cell 3-channel density means -> 8x8
    confusion matrix via a cross-validated Gaussian classifier -> mutual
    information bits/cell (the DESIGN.md 3-bit claim, measured; M3).
(c) 16-state CMYK field: 16x16 confusion + MI (the DESIGN.md 3.4 V-CMYK16
    rejection, measured; M4).
(d) multilevel K and C {0,3,6,9}-of-9 fields: 4-level separability, confusion,
    MI (the M-C verdict, panel rule: use 4-level only if MI4 > 1.15 * MI2).

Alignment strategy (why decode_patch, not cell_means): the contract mandates
dense-warp alignment for cell-accurate work. Every per-plane bitmap of the
state/multilevel fields is a square ground-truthed manifest patch, so each
plane is run through cc.decode_patch (scanlab v4 dense poly2 warp + stepped
y-profile, experiment-001 provenance) in that plane's own channel. The
decoder's `means` output is the per-cell channel mean sampled on the dense
warp — i.e. each channel is aligned to ITS OWN plane's printed lattice, which
is exactly right in the presence of the real per-plane misregistration
(M plane measured at ~+2.5 dots y). Means are converted to optical densities
with the cal_core white model.

Discipline (001.2): every BER carries the 8-cell-shift null control
(0.50 +- 0.02); every confusion/classification measurement carries a
shifted-GT null (accuracy must fall to chance = 1/n_states, MI to ~0);
verdicts are {pass|fail|indeterminate} + statistic + control, never bare
booleans.

Determinism: this module uses NO randomness. Cross-validation folds are a
deterministic interleave (cell_index % n_folds); if stochastic folds are ever
wanted they must flow from paperholo.modulation.rng(seed, label) (CLAUDE.md).

Entry point:  run(scan_bw, scan_color, core_ctx) -> payload dict shaped for
cc.report_merge (curated keys under 'color' and 'alphabet', raw detail under
families/density_color/color_alphabet).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import cal_core as cc  # noqa: E402  (frozen analyzer foundation)

# overlay combos exactly as generated (gen_calpage.build_page)
OVERLAY_COMBOS = ("C", "M", "Y", "K", "CM", "CY", "MY", "CMY", "KCMY")
PLANE_ORDER = ("C", "M", "Y", "K")          # crosstalk matrix column order
CHANNEL_ORDER = ("r", "g", "b")             # crosstalk matrix row order
PRIMARY_CHANNEL = {"C": "r", "M": "g", "Y": "b"}   # complementary channel
COND_GATE = 8.0                              # panel M2 unmix feasibility gate
MI4_OVER_MI2_GATE = 1.15                     # panel: 4-level only if MI4 > 1.15*MI2
NULL_TOL = 0.02


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------

def _central_crop(a: np.ndarray, view: cc.PatchView, trim_frac: float = 0.25
                  ) -> np.ndarray:
    """Central region of a full-raster array of `view` (margin + trim removed)."""
    m = view.margin_dots * view.sub
    h = view.entry["h_dots"] * view.sub
    w = view.entry["w_dots"] * view.sub
    ty, tx = int(h * trim_frac), int(w * trim_frac)
    return a[m + ty: m + h - ty, m + tx: m + w - tx]


def _block_mean(a: np.ndarray, f: int) -> np.ndarray:
    h, w = a.shape[0] // f, a.shape[1] // f
    return a[: h * f, : w * f].reshape(h, f, w, f).mean(axis=(1, 3))


def _mi_bits_from_counts(counts: np.ndarray) -> float:
    """Mutual information (bits) of the joint distribution given by a count
    matrix (rows = true, cols = predicted)."""
    P = counts.astype(np.float64) / max(counts.sum(), 1)
    px = P.sum(axis=1, keepdims=True)
    py = P.sum(axis=0, keepdims=True)
    nz = P > 0
    return float((P[nz] * np.log2(P[nz] / (px @ py)[nz])).sum())


def _confusion(y_true: np.ndarray, y_pred: np.ndarray, n_states: int) -> np.ndarray:
    conf = np.zeros((n_states, n_states), np.int64)
    np.add.at(conf, (y_true, y_pred), 1)
    return conf


def _gaussian_cv_classify(X: np.ndarray, y: np.ndarray, n_states: int,
                          n_folds: int = 5) -> dict:
    """Cross-validated Gaussian (QDA) classifier, deterministic interleaved
    folds (sample_index % n_folds — no randomness by design, CLAUDE.md).

    Caveat (verify pass, exp 002): interleaved folds put spatially adjacent
    cells (correlated mottle/warp noise) in train and test, so ABSOLUTE MI
    values carry a mild optimism bias; comparative verdicts (16<8-state,
    multilevel gates) are unaffected. Blocked folds would fix it if absolute
    numbers ever gate a decision.

    Per class: empirical mean + covariance (scale-aware ridge) + log prior.
    Returns {'pred', 'confusion', 'accuracy', 'mi_bits', 'class_means',
    'class_counts', 'n_folds'}.
    """
    X = np.asarray(X, np.float64)
    if X.ndim == 1:
        X = X[:, None]
    n, d = X.shape
    folds = np.arange(n) % n_folds
    pred = np.full(n, -1, np.int64)
    for f in range(n_folds):
        tr = folds != f
        te = ~tr
        Xtr, ytr = X[tr], y[tr]
        n_tr = len(ytr)
        logp = np.full((int(te.sum()), n_states), -np.inf)
        Xte = X[te]
        for k in range(n_states):
            sel = ytr == k
            nk = int(sel.sum())
            if nk < d + 2:
                continue
            mu = Xtr[sel].mean(axis=0)
            C = np.atleast_2d(np.cov(Xtr[sel], rowvar=False))
            C = C + (1e-4 * float(np.trace(C)) / d + 1e-12) * np.eye(d)
            sign, logdet = np.linalg.slogdet(C)
            diff = Xte - mu
            q = np.einsum("ij,ij->i", diff, np.linalg.solve(C, diff.T).T)
            logp[:, k] = -0.5 * q - 0.5 * logdet + np.log(nk / n_tr)
        pred[te] = np.argmax(logp, axis=1)
    conf = _confusion(y, pred, n_states)
    class_means = np.stack([X[y == k].mean(axis=0) if (y == k).any()
                            else np.full(d, np.nan) for k in range(n_states)])
    return {"pred": pred, "confusion": conf,
            "accuracy": float((pred == y).mean()),
            "mi_bits": _mi_bits_from_counts(conf),
            "class_means": class_means,
            "class_counts": np.bincount(y, minlength=n_states),
            "n_folds": n_folds}


def _classifier_null(pred: np.ndarray, y_2d: np.ndarray, n_states: int,
                     shift_cells: int = 8) -> dict:
    """Null control for a multiclass measurement: score the SAME predictions
    against an 8-cell-x-shifted GT. Labels are i.i.d. uniform by construction,
    so expected accuracy = 1/n_states and expected MI ~ 0."""
    y_null = np.roll(y_2d, shift_cells, axis=1).ravel()
    acc_null = float((pred == y_null).mean())
    mi_null = _mi_bits_from_counts(_confusion(y_null, pred, n_states))
    expected = 1.0 / n_states
    return {"accuracy_null": acc_null, "expected_chance": expected,
            "mi_bits_null": mi_null, "shift_cells": shift_cells,
            "null_ok": bool(abs(acc_null - expected) <= NULL_TOL
                            and mi_null < 0.02)}


# ---------------------------------------------------------------------------
# (a) overlay solids -> densities -> crosstalk matrix / Dmax / K-CMY margin
# ---------------------------------------------------------------------------

def _overlay_entry_name(combo: str) -> str:
    """patch_multi named the per-plane entries overlay_<combo>_<plane>; any of
    them addresses the same rect — use the first plane of the combo."""
    return f"overlay_{combo}_{combo[0]}"


def measure_overlays(scan_color: dict, wm: dict, *, trim_frac: float = 0.25
                     ) -> dict:
    """Median central densities of the 9 overlay solids + quiet-zone paper
    white, LSQ 3x4 crosstalk matrix, CMY condition number, Dmax, K-CMY margin."""
    obs: dict[str, dict] = {}
    pixel_D: dict[str, np.ndarray] = {}   # (n_px, 3) central density vectors
    for combo in OVERLAY_COMBOS:
        v = cc.patch_view(scan_color, _overlay_entry_name(combo))
        dens = cc.density(v, wm, channels=CHANNEL_ORDER)
        med = [float(np.median(_central_crop(dens[ch], v, trim_frac)))
               for ch in CHANNEL_ORDER]
        obs[combo] = {"t": [1 if p in combo else 0 for p in PLANE_ORDER],
                      "D_rgb": med, "lock_q": v.local_quality,
                      "locked": v.local_locked}
        if combo in ("K", "CMY"):
            pixel_D[combo] = np.stack(
                [_central_crop(dens[ch], v, trim_frac).ravel()
                 for ch in CHANNEL_ORDER], axis=1)
            pixel_D[combo + "_cell"] = np.stack(
                [_block_mean(_central_crop(dens[ch], v, trim_frac), 6).ravel()
                 for ch in CHANNEL_ORDER], axis=1)
    # paper white observation (t = 0): the guaranteed-blank quiet zone
    vq = cc.patch_view(scan_color, "quiet_zone")
    dens = cc.density(vq, wm, channels=CHANNEL_ORDER)
    obs["paper"] = {"t": [0, 0, 0, 0],
                    "D_rgb": [float(np.median(_central_crop(dens[ch], vq, trim_frac)))
                              for ch in CHANNEL_ORDER],
                    "lock_q": None, "locked": False}

    order = ["paper", *OVERLAY_COMBOS]
    T = np.array([obs[k]["t"] for k in order], np.float64)          # (10, 4)
    D = np.array([obs[k]["D_rgb"] for k in order], np.float64)      # (10, 3)
    coef, *_ = np.linalg.lstsq(T, D, rcond=None)                    # (4, 3)
    A = coef.T                                                      # (3, 4)
    fit = T @ coef
    resid = D - fit
    for i, k in enumerate(order):
        obs[k]["D_fit"] = [float(x) for x in fit[i]]
        obs[k]["resid"] = [float(x) for x in resid[i]]
    resid_rms = {ch: float(np.sqrt(np.mean(resid[:, j] ** 2)))
                 for j, ch in enumerate(CHANNEL_ORDER)}
    cond_cmy = float(np.linalg.cond(A[:, :3]))

    dmax_rgb = {p: obs[p]["D_rgb"] for p in PLANE_ORDER}
    # Dmax from the per-plane band solids (imagemask path — bit-faithful per
    # canary A; the overlay singles ride the re-screened composite path) and
    # scanner-floor-limited for K: report as a lower bound.
    dmax = {}
    for p in PLANE_ORDER:
        vs = cc.patch_view(scan_color, f"{p}/solid")
        ds = cc.density(vs, wm, channels=CHANNEL_ORDER)
        vals = [float(np.median(_central_crop(ds[ch], vs, trim_frac)))
                for ch in CHANNEL_ORDER]
        dmax[p] = (max(vals) if p == "K"
                   else vals[CHANNEL_ORDER.index(PRIMARY_CHANNEL[p])])
    dmax["K_floor_limited"] = True

    # K vs CMY-stack colinearity margin: Mahalanobis in 3-D density space
    # using pooled solid-patch pixel scatter (spec), plus a 3-dot-cell-level
    # aggregate (classification-relevant granularity).
    def _mahal(a: np.ndarray, b: np.ndarray) -> float:
        dmu = a.mean(axis=0) - b.mean(axis=0)
        Sp = (np.cov(a, rowvar=False) + np.cov(b, rowvar=False)) / 2.0
        Sp = Sp + 1e-9 * np.eye(3)
        return float(np.sqrt(dmu @ np.linalg.solve(Sp, dmu)))

    delta = np.array(obs["K"]["D_rgb"]) - np.array(obs["CMY"]["D_rgb"])
    k_cmy_margin = {
        "mahalanobis_px": _mahal(pixel_D["K"], pixel_D["CMY"]),
        "mahalanobis_cell3": _mahal(pixel_D["K_cell"], pixel_D["CMY_cell"]),
        "delta_D_rgb_K_minus_CMY": [float(x) for x in delta],
        "euclidean_D": float(np.linalg.norm(delta)),
    }

    # zero-crosstalk reference (control for the canary-style verdict): the
    # same primaries with off-diagonals zeroed — best case for this toner set.
    A_ideal = np.diag(np.diag(A[:, :3]))
    cond_ideal = float(np.linalg.cond(A_ideal))
    status = "pass" if cond_cmy < COND_GATE else "fail"
    verdict = cc.canary_verdict(
        "unmix_cond_gate", status, cond_cmy, cond_ideal,
        note=f"cond(A_cmy) vs gate {COND_GATE} (panel M2); control = "
             f"cond of the zero-crosstalk diagonal reference")

    return {"obs": obs, "order": order,
            "A": [[float(x) for x in row] for row in A],
            "resid_rms_D": resid_rms,
            "resid_max_abs_D": float(np.max(np.abs(resid))),
            "cond_cmy": cond_cmy, "dmax": dmax, "dmax_rgb": dmax_rgb,
            "k_cmy_margin": k_cmy_margin, "unmix_verdict": verdict}


# ---------------------------------------------------------------------------
# (b,c,d) aligned per-cell densities via the v4 decoder
# ---------------------------------------------------------------------------

def aligned_cell_densities(scan: dict, patch_name: str, wm: dict, *,
                           channel: str = "auto") -> tuple[np.ndarray, dict]:
    """Per-cell optical density means for one plane-bitmap patch, aligned by
    the v4 dense-warp decoder in the plane's own channel.

    Returns (D_cells (nc, nc) float64, summary dict). Falls back to the rigid
    patch_view lock (global affine + GT xcorr) if the dense warp cannot be
    established; the summary records which path was used.
    """
    e = cc.entry(scan["manifest"], patch_name)
    cell_dots = e["params"]["cell_dots"]
    summary: dict[str, Any] = {"patch": patch_name}
    try:
        out = cc.decode_patch(scan, e, channel=channel,
                              soft=False, diagnostics=False)
        used, total = out["warp_windows_used"], out["warp_windows_total"]
        if total == 0 or used < max(6, int(0.25 * total)):
            raise RuntimeError(f"dense warp weak: {used}/{total} windows")
        means = np.asarray(out["means"], np.float64)
        ch = out["channel"]
        summary.update(method="decode_v4", channel=ch,
                       ber=float(out["ber"]), ber_null=float(out["ber_null"]),
                       null_ok=bool(out["null_ok"]), n_cells=int(out["cells"]),
                       warp_windows=f"{used}/{total}",
                       poly_resid_rms_dots=float(out["poly_resid_rms_dots"]))
    except Exception as exc:  # honest fallback, recorded
        v = cc.patch_view(scan, e, channel=channel)
        means = np.asarray(cc.cell_means(v, cell_dots), np.float64)
        ch = v.reg_channel
        summary.update(method="rigid_patch_view", channel=ch,
                       fallback_reason=repr(exc),
                       lock_q=v.local_quality, locked=v.local_locked,
                       ber=None, ber_null=None, null_ok=None,
                       n_cells=int(means.size))
    nc_y, nc_x = means.shape
    xg, yg = np.meshgrid(e["x_dots"] + (np.arange(nc_x) + 0.5) * cell_dots,
                         e["y_dots"] + (np.arange(nc_y) + 0.5) * cell_dots)
    white = cc.white_at(wm, xg, yg, ch)
    D = -np.log10(np.maximum(means, 1.0) / np.maximum(white, 1e-3))
    return D, summary


def _check_state_gt_consistency(scan: dict, field: str, planes: str,
                                states: np.ndarray) -> None:
    """Manifest-semantics guard: each plane's cell GT must equal the state
    bit-plane (bit i of the state drives planes[i])."""
    for i, p in enumerate(planes):
        gc = cc.gt_cells(cc.entry(scan["manifest"], f"{field}_{p}"))
        if gc is None or not np.array_equal(gc, ((states >> i) & 1).astype(np.uint8)):
            raise RuntimeError(f"{field}_{p}: cell GT != state bit-plane {i} "
                               "(manifest semantics violated)")


def measure_state_field(scan_color: dict, wm: dict, field: str, planes: str,
                        n_states: int) -> dict:
    """8-state CMY / 16-state CMYK confusion + MI. Features: per-cell density
    in each plane's complementary channel, each aligned to its own plane
    (D_r <- C-plane warp, D_g <- M, D_b <- Y). For the 16-state field a
    K-aligned grey-density feature is measured too (4-D variant reported as
    raw; the curated MI uses the 3-channel density space of the spec)."""
    e = cc.entry(scan_color["manifest"], f"{field}_{planes[0]}")
    states = cc.load_gt_named(e["params"]["states_gt"]).astype(np.int64)
    _check_state_gt_consistency(scan_color, field, planes, states)

    feats: list[np.ndarray] = []
    feat_names: list[str] = []
    per_plane: dict[str, dict] = {}
    for p in "CMY":
        D, summ = aligned_cell_densities(scan_color, f"{field}_{p}", wm)
        if D.shape != states.shape:
            raise RuntimeError(f"{field}_{p}: cell grid {D.shape} != states "
                               f"{states.shape}")
        feats.append(D.ravel())
        feat_names.append(f"D_{PRIMARY_CHANNEL[p]}({p}-aligned)")
        per_plane[p] = summ
    X3 = np.stack(feats, axis=1)
    y = states.ravel()

    res = _gaussian_cv_classify(X3, y, n_states)
    null = _classifier_null(res["pred"], states, n_states)

    out = {
        "n_states": n_states, "n_cells": int(y.size),
        "cell_dots": int(e["params"]["cell_dots"]),
        "features": feat_names,
        "accuracy": res["accuracy"], "mi_bits": res["mi_bits"],
        "confusion": res["confusion"].tolist(),
        "class_counts": res["class_counts"].tolist(),
        "class_mean_D": res["class_means"].tolist(),
        "null": null,
        "per_plane_decode": per_plane,
    }

    # per-plane bit error rates implied by the classifier decisions (raw)
    bit_ber = {}
    for i, p in enumerate(planes):
        if p not in "CMY" and field == "state8":
            continue
        pred_bit = (res["pred"] >> i) & 1
        true_bit = (y >> i) & 1
        bit_ber[p] = float((pred_bit != true_bit).mean())
    out["classifier_bit_ber"] = bit_ber

    if field == "state16":
        # K-aligned grey-density feature -> 4-D variant (raw extra)
        D_k, summ_k = aligned_cell_densities(scan_color, "state16_K", wm)
        per_plane["K"] = summ_k
        if D_k.shape == states.shape:
            X4 = np.column_stack([X3, D_k.ravel()])
            res4 = _gaussian_cv_classify(X4, y, n_states)
            null4 = _classifier_null(res4["pred"], states, n_states)
            out["variant_4d"] = {
                "features": feat_names + ["D_grey(K-aligned)"],
                "accuracy": res4["accuracy"], "mi_bits": res4["mi_bits"],
                "null": null4,
            }
    return out


def measure_multilevel(scan: dict, wm: dict, patch_name: str, *,
                       density_channels: tuple[str, ...] | None = None) -> dict:
    """4-level {0,3,6,9}-of-9 field: 1-D density feature per cell, 4-class
    cross-validated Gaussian classifier, confusion, MI, level monotonicity."""
    e = cc.entry(scan["manifest"], patch_name)
    lv = cc.load_gt_named(e["params"]["levels_gt"]).astype(np.int64)
    D, summ = aligned_cell_densities(scan, patch_name, wm)
    if D.shape != lv.shape:
        raise RuntimeError(f"{patch_name}: cell grid {D.shape} != levels {lv.shape}")
    y = lv.ravel()
    res = _gaussian_cv_classify(D.ravel()[:, None], y, 4)
    null = _classifier_null(res["pred"], lv, 4)
    class_D = [float(m[0]) for m in res["class_means"]]
    return {
        "patch": patch_name, "n_cells": int(y.size),
        "levels_dots_of_9": e["params"]["levels"],
        "accuracy": res["accuracy"], "mi_bits": res["mi_bits"],
        "confusion": res["confusion"].tolist(),
        "class_mean_D": class_D,
        "levels_monotonic": bool(np.all(np.diff(class_D) > 0)),
        "null": null, "decode": summ,
    }


# ---------------------------------------------------------------------------
# verdict + family entry point
# ---------------------------------------------------------------------------

def _states_verdict(color: dict, s8: dict, s16: dict, m4: dict,
                    mi2: dict, comp_vs_iso: dict) -> str:
    """Decision logic (panel cal:scan-analyzability §10 rules)."""
    parts = []
    cond = color["cond_cmy"]
    parts.append(f"CMY unmix cond={cond:.2f} "
                 f"({'OK' if cond < COND_GATE else 'FAIL'} vs gate {COND_GATE:g})")
    parts.append(f"8-state CMY c3: MI={s8['mi_bits']:.3f} of 3.0 bits/cell "
                 f"(acc {s8['accuracy']:.3f})")
    if comp_vs_iso:
        parts.append("composite-vs-isolated c3 BER " + " ".join(
            f"{p}:{v['composite8_ber']:.1%}/{v['isolated_ber']:.1%}"
            for p, v in comp_vs_iso.items()))
    gain16 = s16["mi_bits"] - s8["mi_bits"]
    d_m = color["k_cmy_margin"]["mahalanobis_cell3"]
    if gain16 >= 0.5:
        parts.append(f"16-state CMYK: MI={s16['mi_bits']:.3f}, {gain16:+.3f} "
                     f"bits vs 8-state (K separable, cell-level "
                     f"d_M={d_m:.2f}) -> V-CMYK16 viable")
    else:
        parts.append(f"16-state CMYK: MI={s16['mi_bits']:.3f}, {gain16:+.3f} "
                     f"bits vs 8-state (ideal +1.0; K-vs-CMY cell-level "
                     f"d_M={d_m:.2f}) -> V-CMYK16 rejected, keep K as a "
                     "separate binary plane")
    for p in ("K", "C"):
        mi4 = m4[p]["mi_bits"]
        ref = mi2.get(p)
        if ref:
            gate = MI4_OVER_MI2_GATE * ref
            ok = mi4 > gate
            parts.append(f"4-level {p}: MI={mi4:.3f} of 2.0 vs best binary "
                         f"MI2={ref:.3f} (gate {gate:.3f}) -> "
                         f"{'ACCEPT multilevel' if ok else 'reject multilevel'}")
        else:
            parts.append(f"4-level {p}: MI={mi4:.3f} of 2.0 (no binary "
                         "reference measured)")
    return "; ".join(parts)


def run(scan_bw: dict | None, scan_color: dict,
        core_ctx: dict | None = None) -> dict:
    """Family entry point. Scans must be loaded (cc.load_scan); they are
    registered here if not already. Returns a cc.report_merge-shaped payload:
    curated keys under 'color' and 'alphabet', raw detail under
    families/density_color/color_alphabet."""
    core_ctx = core_ctx or {}
    if scan_color["kind"] != "color":
        raise ValueError("cal_color needs the COLOR scan as scan_color")
    if scan_color.get("affine") is None:
        cc.register(scan_color)
    if scan_bw is not None and scan_bw.get("affine") is None:
        cc.register(scan_bw)

    wm = core_ctx.get("white_model_color") or cc.white_model(scan_color)

    # (a) overlays -> crosstalk / Dmax / K-CMY margin
    ov = measure_overlays(scan_color, wm)

    # (b) 8-state CMY field, (c) 16-state CMYK field
    s8 = measure_state_field(scan_color, wm, "state8", "CMY", 8)
    s16 = measure_state_field(scan_color, wm, "state16", "CMYK", 16)

    # (d) multilevel K and C
    m4 = {"K": measure_multilevel(scan_color, wm, "mlvl_K"),
          "C": measure_multilevel(scan_color, wm, "mlvl_C")}

    # isolated binary references at cell=3, all four planes: hard BER +
    # hard-decision MI (2x2 confusion, like-for-like with the multilevel
    # decision MI) + soft MI (scanlab v4 soft stage). The multilevel gate
    # compares against the BEST binary reference — conservative direction:
    # multilevel must beat the best binary detector by the 1.15x panel gate.
    mi2: dict[str, float | None] = {}
    mi2_detail: dict[str, dict] = {}
    for p in ("K", "C", "M", "Y"):
        try:
            out = cc.decode_patch(scan_color, f"{p}/encode_c3", diagnostics=False)
            pred_bits = (out["gt_cells"] ^ out["err_map"].astype(np.uint8))
            conf2 = _confusion(out["gt_cells"].ravel().astype(np.int64),
                               pred_bits.ravel().astype(np.int64), 2)
            mi_hard = _mi_bits_from_counts(conf2)
            mi_soft = float(out["soft"]["mi_bits"])
            mi2[p] = max(mi_hard, mi_soft)
            mi2_detail[p] = {"ber": float(out["ber"]),
                             "ber_llr": float(out["soft"]["ber_llr"]),
                             "mi_bits_soft": mi_soft,
                             "mi_bits_hard_decision": mi_hard,
                             "mi2_best": mi2[p],
                             "soft_miscalibrated":
                                 bool(out["soft"]["ber_llr"] > out["ber"]),
                             "ber_null": float(out["ber_null"]),
                             "null_ok": bool(out["null_ok"])}
        except Exception as exc:
            mi2[p] = None
            mi2_detail[p] = {"error": repr(exc)}

    # composite penalty: per-plane BER inside the 8-state field (the real
    # 3-plane archive channel) vs the isolated per-plane c3 patches (M6)
    comp_vs_iso = {}
    for p in "CMY":
        iso = mi2_detail.get(p, {}).get("ber")
        comp = s8["per_plane_decode"].get(p, {}).get("ber")
        if iso is not None and comp is not None:
            comp_vs_iso[p] = {"isolated_ber": iso, "composite8_ber": comp,
                              "penalty_factor": float(comp / max(iso, 1e-9))}

    # optional cross-check: multilevel K measured again on the grey scan
    m4_k_bw = None
    if scan_bw is not None:
        try:
            wm_bw = core_ctx.get("white_model_bw") or cc.white_model(scan_bw)
            m4_k_bw = measure_multilevel(scan_bw, wm_bw, "mlvl_K")
        except Exception as exc:
            m4_k_bw = {"error": repr(exc)}

    verdict = _states_verdict(ov, s8, s16, m4, mi2, comp_vs_iso)

    color_curated = {
        "unmix_matrix": {"channels": list(CHANNEL_ORDER),
                         "planes": list(PLANE_ORDER),
                         "A_density_per_unit_ink": ov["A"],
                         "residual_rms_D": ov["resid_rms_D"],
                         "residual_max_abs_D": ov["resid_max_abs_D"]},
        "cond_cmy": ov["cond_cmy"],
        "dmax": ov["dmax"],
        "dmax_rgb": ov["dmax_rgb"],
        "k_cmy_margin": ov["k_cmy_margin"],
        "unmix_feasibility": ov["unmix_verdict"],
    }
    alphabet_curated = {
        "mi_8state": s8["mi_bits"],
        "confusion_8state": s8["confusion"],
        "accuracy_8state": s8["accuracy"],
        "mi_16state": s16["mi_bits"],
        "confusion_16state": s16["confusion"],
        "accuracy_16state": s16["accuracy"],
        "mi_4level_K": m4["K"]["mi_bits"],
        "mi_4level_C": m4["C"]["mi_bits"],
        "states_per_cell_verdict": verdict,
        "null_controls": {
            "state8": s8["null"], "state16": s16["null"],
            "mlvl_K": m4["K"]["null"], "mlvl_C": m4["C"]["null"],
        },
    }
    raw = {
        "overlays": {k: ov["obs"][k] for k in ov["order"]},
        "state8": s8, "state16": s16,
        "multilevel": m4, "multilevel_K_bw_crosscheck": m4_k_bw,
        "binary_isolated_refs": mi2_detail,
        "composite_vs_isolated_ber": comp_vs_iso,
        "notes": [
            "features are per-plane dense-warp-aligned densities "
            "(decode_cells v4 means); rigid fallback recorded per patch",
            "MI values are decision MI I(state; classifier output) from "
            "cross-validated confusion counts — a lower bound on the "
            "feature-space MI",
            "CV folds are a deterministic interleave (index % 5); "
            "no randomness in this module",
            "crosstalk fit residuals are dominated by density "
            "SUB-ADDITIVITY at solids (toner opacity/layering: e.g. M solid "
            "D_g=2.39 but CM stack D_g=1.15) — the linear density model is "
            "an approximation; cond(A_cmy) remains the unmix gate metric",
            "multilevel gate uses the BEST binary reference "
            "(max of hard-decision MI and soft MI) — conservative; "
            "soft_miscalibrated flags planes where ber_llr > ber_hard",
        ],
    }
    return {"color": color_curated, "alphabet": alphabet_curated,
            "families": {"density_color": {"color_alphabet": raw}}}


# ---------------------------------------------------------------------------
# smoke run on the real scans
# ---------------------------------------------------------------------------

def _print_report(payload: dict) -> None:
    c, a = payload["color"], payload["alphabet"]
    raw = payload["families"]["density_color"]["color_alphabet"]
    print("\n=== (a) color separation ===")
    print("crosstalk A (rows r,g,b x cols C,M,Y,K), D per unit ink:")
    for ch, row in zip(CHANNEL_ORDER, c["unmix_matrix"]["A_density_per_unit_ink"]):
        print(f"  {ch}: " + "  ".join(f"{v:+.3f}" for v in row))
    print(f"fit residual rms D: " + "  ".join(
        f"{ch}={v:.3f}" for ch, v in c['unmix_matrix']['residual_rms_D'].items())
        + f"  max|resid|={c['unmix_matrix']['residual_max_abs_D']:.3f}")
    print(f"cond(A_cmy) = {c['cond_cmy']:.3f}  -> {c['unmix_feasibility']['status']} "
          f"(gate {COND_GATE:g}, zero-crosstalk control "
          f"{c['unmix_feasibility']['control']:.3f})")
    print(f"Dmax: " + "  ".join(f"{p}={v:.2f}" for p, v in c["dmax"].items()))
    km = c["k_cmy_margin"]
    print(f"K-vs-CMY margin: Mahalanobis px={km['mahalanobis_px']:.2f} "
          f"cell3={km['mahalanobis_cell3']:.2f}  "
          f"deltaD(rgb)={[round(x, 3) for x in km['delta_D_rgb_K_minus_CMY']]}")
    print("\n=== (b) 8-state CMY cell=3 ===")
    s8 = raw["state8"]
    print(f"acc={a['accuracy_8state']:.4f}  MI={a['mi_8state']:.3f} of 3.0 bits/cell "
          f"({s8['n_cells']} cells)")
    print(f"null: acc={s8['null']['accuracy_null']:.4f} "
          f"(chance {s8['null']['expected_chance']:.4f}) "
          f"MI_null={s8['null']['mi_bits_null']:.4f} ok={s8['null']['null_ok']}")
    for p, d in s8["per_plane_decode"].items():
        print(f"  composite BER {p} ({d.get('channel')}, {d.get('method')}): "
              f"{d.get('ber')} null={d.get('ber_null')} ok={d.get('null_ok')}")
    print("\n=== (c) 16-state CMYK cell=3 ===")
    s16 = raw["state16"]
    print(f"acc={a['accuracy_16state']:.4f}  MI={a['mi_16state']:.3f} of 4.0 bits/cell")
    print(f"null: acc={s16['null']['accuracy_null']:.4f} "
          f"(chance {s16['null']['expected_chance']:.4f}) ok={s16['null']['null_ok']}")
    if "variant_4d" in s16:
        v4 = s16["variant_4d"]
        print(f"4-D (+K-aligned grey) variant: acc={v4['accuracy']:.4f} "
              f"MI={v4['mi_bits']:.3f} null_ok={v4['null']['null_ok']}")
    for p, d in s16["per_plane_decode"].items():
        print(f"  composite BER {p} ({d.get('channel')}, {d.get('method')}): "
              f"{d.get('ber')} null={d.get('ber_null')} ok={d.get('null_ok')}")
    print("\n=== (d) multilevel 4-level {0,3,6,9}/9 ===")
    for p in ("K", "C"):
        m = raw["multilevel"][p]
        print(f"mlvl_{p}: acc={m['accuracy']:.4f} MI={m['mi_bits']:.3f} of 2.0  "
              f"class D means={[round(v, 3) for v in m['class_mean_D']]} "
              f"monotonic={m['levels_monotonic']}")
        print(f"  null: acc={m['null']['accuracy_null']:.4f} "
              f"(chance 0.25) ok={m['null']['null_ok']}")
    if raw["multilevel_K_bw_crosscheck"]:
        mb = raw["multilevel_K_bw_crosscheck"]
        if "error" in mb:
            print(f"mlvl_K bw cross-check FAILED: {mb['error']}")
        else:
            print(f"mlvl_K on GREY scan: acc={mb['accuracy']:.4f} "
                  f"MI={mb['mi_bits']:.3f} null_ok={mb['null']['null_ok']}")
    print("\n=== isolated binary refs (cell=3, per plane) ===")
    for p, d in raw["binary_isolated_refs"].items():
        if "error" in d:
            print(f"  {p}: FAILED {d['error']}")
        else:
            print(f"  {p}: ber={d['ber']:.4f} ber_llr={d['ber_llr']:.4f} "
                  f"MI_hard={d['mi_bits_hard_decision']:.3f} "
                  f"MI_soft={d['mi_bits_soft']:.3f} "
                  f"(soft_miscal={d['soft_miscalibrated']}) "
                  f"null={d['ber_null']:.3f} ok={d['null_ok']}")
    if raw["composite_vs_isolated_ber"]:
        print("composite-vs-isolated BER: " + "  ".join(
            f"{p}: {v['composite8_ber']:.3f} vs {v['isolated_ber']:.3f} "
            f"(x{v['penalty_factor']:.1f})"
            for p, v in raw["composite_vs_isolated_ber"].items()))
    print("\nVERDICT: " + a["states_per_cell_verdict"])


def main() -> None:
    import argparse
    import time

    ap = argparse.ArgumentParser(description="cal_color family smoke run")
    ap.add_argument("--scan-color", default="scans/test-scan-calpage-color.png")
    ap.add_argument("--scan-bw", default="scans/test-scan-calpage-bw.png")
    ap.add_argument("--no-bw", action="store_true",
                    help="skip the grey-scan cross-check (halves memory)")
    ap.add_argument("--out", default=str(cc.BUILD / "cal_color_report.json"))
    args = ap.parse_args()

    t0 = time.time()
    scan_color = cc.load_scan(args.scan_color)
    reg_c = cc.register(scan_color)
    print(f"color scan registered: {reg_c['n_landmarks_used']}/"
          f"{reg_c['n_landmarks_total']} landmarks, "
          f"rms {reg_c['residual_rms_dots']:.3f} dots")
    scan_bw = None
    if not args.no_bw:
        scan_bw = cc.load_scan(args.scan_bw)
        reg_b = cc.register(scan_bw)
        print(f"grey scan registered: {reg_b['n_landmarks_used']}/"
              f"{reg_b['n_landmarks_total']} landmarks, "
              f"rms {reg_b['residual_rms_dots']:.3f} dots")

    payload = run(scan_bw, scan_color)
    _print_report(payload)
    cc.save_report(payload, args.out)
    print(f"\nwrote {args.out}  ({time.time() - t0:.0f} s total)")


if __name__ == "__main__":
    main()
