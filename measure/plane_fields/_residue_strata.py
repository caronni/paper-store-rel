"""E2/E3 stratification: where the surviving Y error sits, cell by cell.

Two pure re-analyses of samples ``TileSampler`` already produces at a
FITTED geometry — no decode, no detector, no new pixels beyond the ones
``gt_affine`` read:

* **E2, DIRECTIONAL NEIGHBOURS** (docs/INDEPENDENT-PLANES §4.E(2)).  The
  2026-08-22 review READ the detector: Y's cross-plane context is an
  isotropic 0–8 neighbour ink COUNT and the same-cell crosstalk lives
  only in the 8-state QDA means, while the sampling aperture is 0.7 cell
  = 1.4 dots — so a 0.5–1.0 dot per-plane displacement slides that
  aperture 36–71 % of its own width TOWARD ONE NEIGHBOUR.  The leakage
  becomes anisotropic and neighbour-sourced, which neither term can
  express.  That model-class limit makes a falsifiable prediction: a
  dead-band tile's Y errors should concentrate on cells whose DOWNSTREAM
  neighbour — the one in the direction of the fitted Y translation —
  carries C or M ink, and a clear-band control should show no such
  split.  :func:`directional_table` measures it, with the UPSTREAM
  neighbour as the built-in falsifier and the SAME cell as the reference
  the review's other reading (same-cell mix compression) predicts.

* **E3, PER-STATE CONTRAST** (§4.E(3)).  The same samples split by the
  SAME cell's (C, M) ground-truth state.  If Y-under-M is optically
  compressed relative to Y-on-white, the ink/white separation collapses
  in the ``M`` and ``both`` states — measurable as a ratio of d' and of
  raw mean separation, on dead tiles AND on certified clean-column
  reference tiles.

Nothing here decides anything: these are descriptive tables over
outcome-selected groups, and every count is reported so the reader can
see what the effect sizes rest on.
"""
from __future__ import annotations

import numpy as np

from ._affine_fit import TILE_CELLS, oracle_threshold_ber, separation

#: (C ink, M ink) -> the stratum name every table uses.
STRATUM_NAMES = {(0, 0): "none", (0, 1): "M", (1, 0): "C", (1, 1): "both"}
STRATUM_ORDER = ("none", "C", "M", "both")


def translation_direction(tx: float, ty: float) -> dict:
    """The DOMINANT axis and sign of a fitted per-plane translation.

    Page dots: ``tx`` displaces the sampling grid along page x, ``ty``
    along page y.  The dominant axis is the larger magnitude; its sign
    picks which of the two neighbours is DOWNSTREAM (the one the aperture
    slides toward).
    """
    axis = "x" if abs(float(tx)) >= abs(float(ty)) else "y"
    value = float(tx) if axis == "x" else float(ty)
    sign = 1 if value >= 0.0 else -1
    return {"axis": axis, "sign": sign, "translation_dots_xy": [
        float(tx), float(ty)], "dominant_dots": value,
        "dominance_ratio": (
            float(abs(value) / max(abs(float(ty)), 1e-12)) if axis == "x"
            else float(abs(value) / max(abs(float(tx)), 1e-12)))}


def _page_cells(sampler, address) -> np.ndarray:
    _page, tile_y, tile_x = address
    return np.stack(
        (sampler.cell_yx[:, 0] + tile_y * TILE_CELLS,
         sampler.cell_yx[:, 1] + tile_x * TILE_CELLS), axis=1).astype(np.int64)


def _shifted_bits(page_bits: np.ndarray, page_cells: np.ndarray,
                  axis: str, sign: int) -> tuple[np.ndarray, np.ndarray]:
    """The (3,) GT bits of each cell's neighbour, plus a validity mask.

    A cell whose neighbour would fall off the page is dropped rather than
    clamped: a clamped neighbour is a fabricated stratum membership.
    """
    rows, columns = page_bits.shape[:2]
    shifted = page_cells.copy()
    if axis == "x":
        shifted[:, 1] += sign
    else:
        shifted[:, 0] += sign
    valid = ((shifted[:, 0] >= 0) & (shifted[:, 0] < rows)
             & (shifted[:, 1] >= 0) & (shifted[:, 1] < columns))
    safe = np.clip(shifted, 0, (rows - 1, columns - 1))
    return page_bits[safe[:, 0], safe[:, 1], :], valid


def stratum_rows(values: np.ndarray, truth_y: np.ndarray,
                 c_bits: np.ndarray, m_bits: np.ndarray,
                 valid: np.ndarray | None = None) -> dict:
    """One 4-stratum table, with TWO error rates that answer two questions.

    * ``ber_global`` is the stratum's error under the ONE threshold fitted
      on all this tile's cells — how the errors an actual (stratum-blind)
      decision makes are DISTRIBUTED.  ``lift`` is that stratum's share of
      the errors over its share of the cells: > 1 means the errors
      concentrate there.  This is the quantity "errors concentrate in
      cells whose downstream neighbour carries ink" is a claim about.
    * ``ber`` re-fits the threshold INSIDE the stratum — what survives a
      perfect stratum-conditional correction, i.e. what an anisotropic
      context term could NOT recover.  ``ber_global - ber`` is therefore
      the size of the prize such a term would compete for.
    """
    key = np.where(c_bits > 0.5, 1, 0) * 2 + np.where(m_bits > 0.5, 1, 0)
    mask_all = np.ones(values.shape[0], bool) if valid is None else valid
    pooled = oracle_threshold_ber(values[mask_all], truth_y[mask_all])
    global_threshold = float(pooled["threshold"])
    wrong = (values < global_threshold) != (truth_y > 0.5)
    total_errors = int(wrong[mask_all].sum())
    total_cells = int(mask_all.sum())
    rows: dict[str, dict] = {}
    for (c_bit, m_bit), name in STRATUM_NAMES.items():
        mask = mask_all & (key == (c_bit * 2 + m_bit))
        count = int(mask.sum())
        errors = int(wrong[mask].sum())
        if count < 16:
            rows[name] = {"n": count, "ber": None, "ber_global": None,
                          "d_prime": None, "lift": None,
                          "reason": "fewer than 16 cells"}
            continue
        subset = values[mask]
        truth = truth_y[mask]
        oracle = oracle_threshold_ber(subset, truth)
        split = separation(subset, truth)
        rows[name] = {
            "n": count,
            "n_ink": split["n_ink"], "n_white": split["n_white"],
            "ink_fraction": float((truth > 0.5).mean()),
            "ber": oracle["ber"], "threshold": oracle["threshold"],
            "ber_global": float(errors / count),
            "errors_global": errors,
            "error_share_global": (
                None if not total_errors else float(errors / total_errors)),
            "cell_share": float(count / total_cells),
            "lift": (None if not total_errors or not count else float(
                (errors / total_errors) / (count / total_cells))),
            "recoverable_pp": float(100.0 * (errors / count - oracle["ber"])),
            "d_prime": split["d_prime"], "auc": split["auc"],
            "mean_ink": split.get("mean_ink"),
            "mean_white": split.get("mean_white"),
            "sd_ink": split.get("sd_ink"), "sd_white": split.get("sd_white"),
            "mean_separation": (
                None if split.get("mean_white") is None
                else float(split["mean_white"] - split["mean_ink"])),
        }
    rows["_all"] = {"n": total_cells, "ber": pooled["ber"],
                    "ber_global": (float(total_errors / total_cells)
                                   if total_cells else None),
                    "threshold": global_threshold,
                    "errors_global": total_errors,
                    **{key_: value for key_, value in
                       separation(values[mask_all],
                                  truth_y[mask_all]).items()}}
    return rows


def _mean_or_none(values):
    rows = [float(v) for v in values if v is not None and np.isfinite(v)]
    return float(np.mean(rows)) if rows else None


def _contrast(rows: dict) -> dict:
    """Ink-present vs ink-absent halves of a 4-stratum table."""
    def value(name: str, key: str):
        row = rows.get(name) or {}
        return row.get(key)

    inked = [name for name in ("C", "M", "both")
             if value(name, "ber") is not None]
    clean = value("none", "ber")
    out = {
        "ber_none": clean,
        "ber_inked_mean": (
            None if not inked
            else float(np.mean([value(name, "ber") for name in inked]))),
        "ber_worst_inked": (
            None if not inked
            else max(inked, key=lambda name: value(name, "ber"))),
        "inked_strata_present": inked,
    }
    out["ber_gap_inked_minus_none"] = (
        None if clean is None or out["ber_inked_mean"] is None
        else float(out["ber_inked_mean"] - clean))
    # The stratum-blind view: where the errors an ordinary decision makes
    # actually LAND, and how much of that a stratum-aware term could take.
    global_none = value("none", "ber_global")
    global_inked = [value(name, "ber_global") for name in inked]
    out["ber_global_none"] = global_none
    out["ber_global_inked_mean"] = (
        None if not inked else float(np.mean(global_inked)))
    out["ber_global_gap_inked_minus_none"] = (
        None if global_none is None or not inked
        else float(np.mean(global_inked) - global_none))
    out["lift_none"] = value("none", "lift")
    out["lift_inked_mean"] = (
        None if not inked
        else _mean_or_none([value(name, "lift") for name in inked]))
    out["recoverable_pp_inked_mean"] = (
        None if not inked
        else _mean_or_none([value(name, "recoverable_pp")
                            for name in inked]))
    for name in ("C", "M", "both"):
        out[f"lift_{name}"] = value(name, "lift")
    for name in ("C", "M", "both"):
        left, right = value(name, "d_prime"), value("none", "d_prime")
        out[f"d_prime_ratio_{name}_over_none"] = (
            None if left is None or not right else float(left / right))
        left, right = (value(name, "mean_separation"),
                       value("none", "mean_separation"))
        out[f"separation_ratio_{name}_over_none"] = (
            None if left is None or not right else float(left / right))
    return out


# --------------------------------------------------------------------------
# E2
# --------------------------------------------------------------------------
def directional_table(sampler, address, page_bits: np.ndarray,
                      values: np.ndarray, truth_by_plane: np.ndarray,
                      tx: float, ty: float) -> dict:
    """E2: Y strata by the DOWNSTREAM neighbour's C/M ink.

    ``values`` are the Y channel sampled at the fitted geometry and
    ``truth_by_plane`` the (3, n) GT bits aligned with them; ``page_bits``
    is the whole page's ``(cells_y, cells_x, 3)`` printed field, which is
    what makes a neighbour across the TILE boundary readable.
    """
    direction = translation_direction(tx, ty)
    page_cells = _page_cells(sampler, address)
    truth_y = truth_by_plane[2]
    out = {"direction": direction, "n_samples": int(values.shape[0])}
    for label, sign in (("downstream", direction["sign"]),
                        ("upstream", -direction["sign"])):
        bits, valid = _shifted_bits(
            page_bits, page_cells, direction["axis"], sign)
        rows = stratum_rows(values, truth_y, bits[:, 0], bits[:, 1], valid)
        out[label] = {"strata": rows, "n_valid": int(valid.sum()),
                      "contrast": _contrast(rows)}
    same = stratum_rows(values, truth_y, truth_by_plane[0], truth_by_plane[1])
    out["same_cell"] = {"strata": same, "contrast": _contrast(same)}
    out["downstream_minus_upstream_gap"] = (
        None
        if out["downstream"]["contrast"]["ber_gap_inked_minus_none"] is None
        or out["upstream"]["contrast"]["ber_gap_inked_minus_none"] is None
        else float(out["downstream"]["contrast"]["ber_gap_inked_minus_none"]
                   - out["upstream"]["contrast"]["ber_gap_inked_minus_none"]))
    return out


# --------------------------------------------------------------------------
# E3
# --------------------------------------------------------------------------
def state_contrast(values: np.ndarray, truth_by_plane: np.ndarray) -> dict:
    """E3: Y ink/white separation conditional on the SAME cell's (C, M)."""
    rows = stratum_rows(values, truth_by_plane[2],
                        truth_by_plane[0], truth_by_plane[1])
    return {"strata": rows, "contrast": _contrast(rows)}


def pool_strata(entries: list[dict]) -> dict:
    """Unweighted mean of a stratum table over (tile, capture) rows.

    Descriptive only: the rows are NOT independent (three captures of one
    physical tile), so both counts are carried — ``n_rows`` is
    tile x capture and ``n_tiles`` is the physical population the claim
    may actually be about.
    """
    out: dict[str, dict] = {}
    for name in STRATUM_ORDER:
        for key in ("ber", "ber_global", "lift", "recoverable_pp",
                    "error_share_global", "cell_share", "d_prime",
                    "mean_separation", "ink_fraction"):
            values = [row["strata"].get(name, {}).get(key) for row in entries]
            values = [float(v) for v in values if v is not None]
            out.setdefault(name, {})[key] = (
                float(np.mean(values)) if values else None)
            out[name][f"{key}_sd"] = (
                float(np.std(values, ddof=1)) if len(values) > 1 else None)
        counts = [row["strata"].get(name, {}).get("n") for row in entries]
        out[name]["n_cells_total"] = int(sum(
            int(v) for v in counts if v is not None))
    out["_rows"] = {"n_rows": len(entries),
                    "n_tiles": len({row.get("tile") for row in entries})}
    return out


__all__ = ["STRATUM_NAMES", "STRATUM_ORDER", "directional_table",
           "pool_strata", "state_contrast", "stratum_rows",
           "translation_direction"]
