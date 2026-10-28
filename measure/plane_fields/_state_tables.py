"""E3' leaves: the production head's OWN numbers, per eight-state class.

docs/INDEPENDENT-PLANES §2.8's CORRECTION narrowed E3's open quantity to
this: not "would a per-state threshold help" (the production head already
carries a class per state) but **where the production head sits against a
per-state oracle, state by state, with the numbers the fit itself used**.

Four tables live here, all pure functions of one fitted region:

* :func:`qda_state_table` — per state ``k``: the TRAINING label count
  ``n_k`` the QDA was fitted on, the covariance-shrinkage factor
  ``a_k = min(1, (D+2)/n_k)`` it implies, the state's mean and covariance
  in the Y (blue) channel, the PAVA calibration population's count, and
  the held-out validation numbers the ladder's own gate reads (mean NLL,
  eight-way argmax error, and the CALIBRATED Y-bit error).
  ``n_k`` and ``a_k`` are pure functions of the ownership split, so they
  are identical for every arm and every refit of one capture's region.
* :func:`stratum_contrast` — the Y separation each ``(C, M)`` stratum
  offers the head, read off the same per-state means: the distance
  between the stratum's Y=0 and Y=1 means over the pooled Y sd.
* :func:`production_state_rows` / :func:`oracle_state_rows` — on one
  tile's cells at the fitted geometry, the production Y error and the
  per-(C, M)-stratum ORACLE THRESHOLD error, both split by the GT state
  of the SAME cell.  A stratum's threshold is fitted over both of its
  states, so the two rows it produces are that threshold's two class
  errors — the comparison is well posed, which a threshold fitted inside
  a single state would not be (it would score exactly zero).
* :func:`window_photometry_rows` — A3's per-window verdict, band by
  band.  A3 is OVERRIDE-ONLY in production (``color_stack``: reachable
  only from the ``u-a3`` supplemental lane), so this is a diagnostic of
  what that lane WOULD find on this region, never a report of what the
  archived decode did.

State names are C-M-Y bit strings, ``k`` = C + 2M + 4Y
(``core.channel.states_to_planes``): W = ``000``, CM = ``110``,
Y = ``001``.  Nothing here writes anything.
"""
from __future__ import annotations

import numpy as np

from holo.receive import color_detect
from holo.receive.color_fitting import _owner_selection
from holo.receive.color_locality import (
    WindowPhotometryConfig,
    fit_window_photometry,
)

from ._affine_fit import TILE_CELLS, oracle_threshold_ber

#: Y is read from the blue channel (features are reflected R/G/B means in
#: C/M/Y plane order — ``color_detect``'s module note).
Y_PLANE = 2
N_STATES = 8


def state_label(state: int) -> str:
    """``k`` -> its C-M-Y bit string (``3`` -> ``'110'``)."""
    return f"{state & 1}{(state >> 1) & 1}{(state >> 2) & 1}"


STATE_LABELS = tuple(state_label(state) for state in range(N_STATES))
#: (C, M) stratum -> the two states it contains, (Y=0, Y=1).
STRATA = {f"{c}{m}": (c + 2 * m, c + 2 * m + 4)
          for c in (0, 1) for m in (0, 1)}


def selection_of(fit):
    """The region's ownership/split — a pure function of its rows."""
    return _owner_selection(fit.rows)


def features_tuple(fit) -> tuple[np.ndarray, ...]:
    """The selected arm's per-row features, in row order.

    Requires the fit to have been built with ``keep_all_features=True``;
    a missing row is a caller error, not a silent hole, so this raises.
    """
    missing = [ordinal for ordinal in range(len(fit.rows))
               if ordinal not in fit.features0]
    if missing:
        raise KeyError(
            f"the region fit retained no features for rows {missing[:4]}… — "
            f"it must be built with keep_all_features=True")
    return tuple(fit.features0[ordinal] for ordinal in range(len(fit.rows)))


# --------------------------------------------------------------------------
# the fit's own numbers
# --------------------------------------------------------------------------
def qda_state_table(fit, spec) -> dict:
    """Per-state ``n_k``, ``a_k``, Y moments, calibration and validation.

    ``spec`` is unused numerically and taken only so a caller cannot pass
    a CMY7 region here by accident (this table is eight-state).
    """
    detector_fit = fit.selected_fit
    detector = detector_fit.detector
    if detector is None:
        raise ValueError("E3': the per-state table is CMY8-only")
    del spec
    model = detector_fit.model
    n_features = int(model.n_features)
    selection = selection_of(fit)
    known = selection.gather(features_tuple(fit))
    states = np.asarray(selection.states, np.int64)
    kinds = np.asarray(selection.kinds, np.int8)
    search = np.asarray(selection.search, np.bool_)
    heldout = ~search

    train_counts = np.bincount(states[search], minlength=N_STATES)
    heldout_counts = np.bincount(states[heldout], minlength=N_STATES)
    calibration = (kinds == 1) | (kinds == -1)
    calibration_counts = np.bincount(states[calibration], minlength=N_STATES)
    word_counts = np.bincount(states[kinds == 0], minlength=N_STATES)
    dust_counts = np.bincount(states[kinds == 1], minlength=N_STATES)
    cert_counts = np.bincount(states[kinds < 0], minlength=N_STATES)

    scores = color_detect.qda_log_scores(model, known[heldout])
    from scipy.special import logsumexp

    normalized = scores - logsumexp(scores, axis=1, keepdims=True)
    heldout_states = states[heldout]
    nll = -normalized[np.arange(normalized.shape[0]), heldout_states]
    argmax_wrong = np.argmax(scores, axis=1) != heldout_states
    # The CALIBRATED head, exactly as the region emits it (unconditioned,
    # uncorrected — A5's bins are per-cell and this population is the
    # ownership's, not a window's).
    llrs = detector.llrs(known[heldout])
    y_truth = ((heldout_states >> Y_PLANE) & 1).astype(bool)
    y_wrong = (llrs[:, Y_PLANE] > 0.0) != y_truth

    rows = []
    for state in range(N_STATES):
        count = int(train_counts[state])
        shrinkage = (1.0 if count == 0
                     else min(1.0, (n_features + 2) / float(count)))
        covariance = (np.asarray(model.cholesky[state], np.float64)
                      @ np.asarray(model.cholesky[state], np.float64).T)
        selected = heldout_states == state
        rows.append({
            "state": state,
            "name": STATE_LABELS[state],
            "n_train": count,
            "a_k": float(shrinkage),
            "fully_shrunk_to_pooled": bool(count == 0
                                           or count < n_features + 2),
            "n_heldout": int(heldout_counts[state]),
            "n_calibration": int(calibration_counts[state]),
            "n_word": int(word_counts[state]),
            "n_dust": int(dust_counts[state]),
            "n_certified": int(cert_counts[state]),
            "mean_rgb": [float(value) for value in model.means[state]],
            "mean_y": float(model.means[state][Y_PLANE]),
            "sd_y": float(np.sqrt(covariance[Y_PLANE, Y_PLANE])),
            "cov_diag": [float(value) for value in np.diag(covariance)],
            "heldout_nll": (None if not selected.any()
                            else float(nll[selected].mean())),
            "heldout_argmax_error": (None if not selected.any()
                                     else float(argmax_wrong[selected].mean())),
            "heldout_y_bit_error": (None if not selected.any()
                                    else float(y_wrong[selected].mean())),
        })
    support = detector.calibration_support
    return {
        "n_features": n_features,
        "shrinkage_law": "a_k = min(1, (D+2)/n_k), D = n_features",
        "arm": "A1" if fit.adopted else "A0",
        "heldout_logloss": float(fit.heldout_loss),
        "n_owned": int(states.size),
        "n_train": int(search.sum()),
        "n_heldout": int(heldout.sum()),
        "calibration_labels": int(detector.calibration_labels),
        "calibration_state_counts": [int(v) for v in support.state_counts],
        "supported_planes": [bool(v) for v in detector.supported_planes],
        "unsupported_reasons": [None if v is None else str(v)
                                for v in detector.unsupported_reasons],
        "qda_degenerate": bool(model.degenerate),
        "qda_clipped_planes": [int(v) for v in model.clipped_planes],
        "qda_warnings": [str(v) for v in model.warnings],
        "states": rows,
        "stratum_contrast": stratum_contrast(rows),
    }


def stratum_contrast(rows: list[dict]) -> dict:
    """Per-(C, M) stratum, the Y mean separation the QDA classes carry."""
    by_state = {row["state"]: row for row in rows}
    out: dict[str, dict] = {}
    for name, (white, ink) in STRATA.items():
        left, right = by_state[white], by_state[ink]
        pooled = float(np.sqrt(
            0.5 * (left["sd_y"] ** 2 + right["sd_y"] ** 2)))
        gap = float(left["mean_y"] - right["mean_y"])
        out[name] = {
            "state_white": left["name"], "state_ink": right["name"],
            "mean_y_white": left["mean_y"], "mean_y_ink": right["mean_y"],
            "mean_gap": gap,
            "pooled_sd_y": pooled,
            "d_prime_from_model": (None if pooled <= 0.0
                                   else float(gap / pooled)),
            "n_train_white": left["n_train"], "n_train_ink": right["n_train"],
            "a_k_white": left["a_k"], "a_k_ink": right["a_k"],
        }
    on_white = out["00"]["mean_gap"]
    for name, row in out.items():
        row["gap_ratio_over_00"] = (
            None if not on_white else float(row["mean_gap"] / on_white))
    return out


# --------------------------------------------------------------------------
# one tile: production vs the per-stratum oracle, split by GT state
# --------------------------------------------------------------------------
def gt_states_for(truth_bits: np.ndarray, page_cells: np.ndarray) -> np.ndarray:
    """``k = C + 2M + 4Y`` at each page cell, from the printed field."""
    bits = truth_bits[page_cells[:, 0], page_cells[:, 1], :].astype(np.int64)
    return bits[:, 0] + 2 * bits[:, 1] + 4 * bits[:, 2]


def _rows_by_state(wrong: np.ndarray, states: np.ndarray) -> list[dict]:
    rows = []
    for state in range(N_STATES):
        mask = states == state
        count = int(mask.sum())
        rows.append({
            "state": state, "name": STATE_LABELS[state], "n": count,
            "errors": int(wrong[mask].sum()) if count else 0,
            "error_rate": (None if not count
                           else float(wrong[mask].mean())),
        })
    return rows


def production_state_rows(decided_ink: np.ndarray, states: np.ndarray
                          ) -> list[dict]:
    """Per-state error of a hard Y decision against the GT state's Y bit."""
    truth = ((states >> Y_PLANE) & 1).astype(bool)
    return _rows_by_state(np.asarray(decided_ink, bool) != truth, states)


def oracle_state_rows(values: np.ndarray, states: np.ndarray) -> dict:
    """Per-(C, M)-stratum oracle threshold, reported per state.

    One threshold per stratum, fitted on that stratum's own cells with
    full knowledge of their Y bits; the two rows it produces are its two
    class errors.  Ink darkens the channel, so ``oracle_threshold_ber``'s
    ``value < threshold`` rule is the one used.
    """
    truth = ((np.asarray(states) >> Y_PLANE) & 1).astype(bool)
    wrong = np.zeros(values.shape[0], bool)
    strata: dict[str, dict] = {}
    for name, (white, ink) in STRATA.items():
        mask = (states == white) | (states == ink)
        count = int(mask.sum())
        if count < 16:
            strata[name] = {"n": count, "ber": None,
                            "reason": "fewer than 16 cells"}
            # A stratum too small to fit a threshold in: the honest fill
            # is the majority-class error, never a fitted one.
            if count:
                majority = truth[mask].mean() > 0.5
                wrong[mask] = truth[mask] != majority
            continue
        row = oracle_threshold_ber(values[mask], truth[mask].astype(float))
        threshold = float(row["threshold"])
        wrong[mask] = (values[mask] < threshold) != truth[mask]
        strata[name] = {
            "n": count, "ber": float(row["ber"]), "threshold": threshold,
            "n_white": int((states[mask] == white).sum()),
            "n_ink": int((states[mask] == ink).sum())}
    return {"by_state": _rows_by_state(wrong, states), "strata": strata,
            "ber": float(wrong.mean()) if wrong.size else None}


# --------------------------------------------------------------------------
# A3's per-window verdict, by band
# --------------------------------------------------------------------------
def window_band(fit, ordinal: int, dead_bands) -> dict:
    """One window's dead-band exposure, as a cell fraction and a label."""
    cells = np.asarray(fit.rows[ordinal].page_cells_yx, np.int64)
    if cells.size == 0:
        return {"band": "empty", "dead_cell_fraction": None,
                "tile_x_min": None, "tile_x_max": None}
    columns = cells[:, 1] // TILE_CELLS
    dead = np.isin(columns, np.asarray(dead_bands, np.int64))
    fraction = float(dead.mean())
    label = ("clean" if fraction == 0.0
             else "dead" if fraction >= 0.5 else "mixed")
    return {"band": label, "dead_cell_fraction": fraction,
            "tile_x_min": int(columns.min()), "tile_x_max": int(columns.max())}


def window_photometry_rows(fit, dead_bands, *, config=None) -> dict:
    """A3's per-window fits on this region, split dead vs clean.

    DIAGNOSTIC.  A3 is override-only in production: an ordinary lane —
    which is what the archived W6 decode and every fit in this instrument
    run — never fits a window map at all.  What this measures is what the
    ``u-a3`` supplemental lane would find on this region's windows.
    """
    photometry = WindowPhotometryConfig() if config is None else config
    result = fit_window_photometry(
        fit.selected_fit.model, selection_of(fit), fit.rows,
        features_tuple(fit), photometry)
    rows = []
    for entry in result.fits:
        band = window_band(fit, entry.ordinal, dead_bands)
        rows.append({
            "ordinal": int(entry.ordinal),
            "patch_id": int(fit.rows[entry.ordinal].patch.patch_id),
            "is_payload_row": bool(entry.ordinal < fit.n_payload),
            "reason": entry.reason,
            "accepted": bool(entry.accepted),
            "n_own": int(entry.n_own),
            "n_halo": int(entry.n_halo),
            "n_states": int(entry.n_states),
            "n_heldout": int(entry.n_heldout),
            "n_effective": float(entry.n_effective),
            "identity_nll": (None if entry.identity_nll is None
                             else float(entry.identity_nll)),
            "candidate_nll": (None if entry.candidate_nll is None
                              else float(entry.candidate_nll)),
            "nll_gain": (None if entry.identity_nll is None
                         else float(entry.identity_nll - entry.candidate_nll)),
            **band,
        })
    return {
        "arm_is_override_only": True,
        "prior_labels": float(photometry.prior_labels),
        "arm_reason": result.arm_reason,
        "accepted": int(result.accepted),
        "refused": int(result.refused),
        "pooled": int(result.pooled),
        "reasons": {name: int(count) for name, count in result.reasons},
        "windows": rows,
        "by_band": summarize_photometry(rows),
    }


def summarize_photometry(rows: list[dict]) -> dict:
    """Reason histogram and label counts per band."""
    out: dict[str, dict] = {}
    for band in ("dead", "mixed", "clean", "empty"):
        subset = [row for row in rows if row["band"] == band]
        if not subset:
            continue
        reasons: dict[str, int] = {}
        for row in subset:
            reasons[row["reason"]] = reasons.get(row["reason"], 0) + 1
        gains = [row["nll_gain"] for row in subset
                 if row["nll_gain"] is not None]
        out[band] = {
            "n_windows": len(subset),
            "accepted": sum(1 for row in subset if row["accepted"]),
            "accepted_fraction": float(
                sum(1 for row in subset if row["accepted"]) / len(subset)),
            "reasons": dict(sorted(reasons.items())),
            "n_own_mean": float(np.mean([row["n_own"] for row in subset])),
            "n_halo_mean": float(np.mean([row["n_halo"] for row in subset])),
            "n_effective_mean": float(
                np.mean([row["n_effective"] for row in subset])),
            "n_heldout_mean": float(
                np.mean([row["n_heldout"] for row in subset])),
            "nll_gain_mean": float(np.mean(gains)) if gains else None,
        }
    return out


__all__ = [
    "N_STATES", "STATE_LABELS", "STRATA", "Y_PLANE", "features_tuple",
    "gt_states_for", "oracle_state_rows", "production_state_rows",
    "qda_state_table", "selection_of", "state_label", "stratum_contrast",
    "summarize_photometry", "window_band", "window_photometry_rows",
]
