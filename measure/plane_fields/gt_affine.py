#!/usr/bin/env python
"""THE SUPERVISED AFFINE CEILING — how much geometry could ever buy.

The swim pilot (``swim_pilot``, docs/PLANE-FIELDS.md §6.5.5a) swept ONE
per-plane translation and found that a residue tile's ground-truth cell
error falls from ~17.5% to ~10.8% at the best offset — and stops there,
above the measured ~7.6% decode gate.  That leaves three hypotheses for
the ~10% floor, and the swim cannot separate them:

  (1) GEOMETRY WE DO NOT MODEL — scale, shear or rotation of the plane's
      sampling grid inside the tile, which a translation cannot absorb;
  (2) PHOTOMETRY — the samples land on the right ink and the DECISION is
      wrong (calibration, crosstalk, context);
  (3) IRREDUCIBLE — the Y signal is simply not there.

Sheet I closed VERIFIED, so for every one of these tiles we hold the
exact printed cells.  This instrument therefore fits the BEST POSSIBLE
per-plane geometry against that ground truth — a full 2-D affine, six
degrees of freedom per (tile, plane, capture) — and reports what
survives.  That is the CEILING of any registration-based correction: no
field, no swim, no local-affine search can beat a supervised fit of the
same model on the same pixels.

Per (tile, plane, capture) it reports

* the fitted affine in interpretable units (translation in print dots,
  per-cell scale error in %, rotation and shear in degrees, and the
  displacement each term produces across the 64-cell tile);
* the ground-truth CELL MISMATCH through the PRODUCTION detector at that
  fit, against delta = 0 and against the translation-only optimum — the
  0 -> 2 -> 6 degree-of-freedom ladder;
* an ordinary DECODE ATTEMPT at the fitted geometry (the swim's oracle:
  a certificate, or nothing);
* where the surviving mismatch sits inside the tile (quadrants, edge
  ring, Moran's I with a permutation p-value); and
* the CLASS SEPARATION between ground-truth ink and white cells in the
  sampled values (d', partial d', AUC) plus the ORACLE-THRESHOLD cell
  error, with certified tiles in clean columns as the reference — the
  discriminator between hypotheses (2) and (3).

Everything is READ-ONLY: the W6 state, the three archived 2400 dpi
captures and the swim's own results JSON are opened for reading and
nothing is written outside ``scratch/plane-fields/gt-affine/``.

    cd <repo>
    PYTHONPATH=src:measure env/bin/python \
        -m plane_fields.gt_affine --tag v1
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np

from . import _affine_fit, _swim_inputs, _swim_region
from ._affine_fit import HALF_TILE, TILE_CELLS, TileSampler
from ._swim_region import page_to_local_dots
from .swim_pilot import union_verdict

SCHEMA = "plane-fields-gt-affine-v1"
OUT_DIR = _swim_inputs.MAIN_SCRATCH / "plane-fields" / "gt-affine"
SWIM_RESULTS = (_swim_inputs.MAIN_SCRATCH / "plane-fields" / "swim-pilot"
                / "swim-pilot-final.json")
PLANE_NAMES = ("C", "M", "Y")
#: The measured decode gate: the swim's worst CERTIFIED candidate sat at
#: 7.67% cell error and its best FAILED one at 7.57%, so the gate is an
#: interval, not a constant.  Reported, never used to accept anything.
GATE_BER = 0.0767


# --------------------------------------------------------------------------
# the affine seam: a per-cell offsets_override, tile-local
# --------------------------------------------------------------------------
def affine_override(row, residuals, spec, address, affines,
                    base_is_residual: bool) -> tuple:
    """``offsets_override`` with a per-plane AFFINE on ONE tile's cells.

    ``_swim_region.override_offsets`` is the constant-delta form of this
    function; the only difference is that the correction varies per cell
    and applies to the target tile's cells alone.  Cells outside the tile
    keep the delta = 0 sampling exactly, so a window that spans several
    tiles cannot be dragged out of the raster by an affine extrapolated
    far past the region it was fitted on.

    ``residuals`` is read only when ``base_is_residual`` is true, so the
    A0 arm (whose zero is the bare committed pose) can be corrected
    before the registration fit exists.
    """
    page_cells = np.asarray(row.page_cells_yx, np.int64)
    count = page_cells.shape[0]
    fraction = (page_cells[:, 0].astype(np.float64)
                / spec.layout.cells_yx[0])
    _page, tile_y, tile_x = address
    select = np.nonzero((page_cells[:, 0] // TILE_CELLS == tile_y)
                        & (page_cells[:, 1] // TILE_CELLS == tile_x))[0]
    centred = np.stack(
        ((page_cells[select, 1] % TILE_CELLS) - HALF_TILE,
         (page_cells[select, 0] % TILE_CELLS) - HALF_TILE),
        axis=1).astype(np.float64)
    basis = page_to_local_dots(row.patch)
    out = []
    for plane in range(_swim_region.N_PLANES):
        base = np.array(
            residuals[plane].offsets(fraction) if base_is_residual
            else np.zeros((count, 2), np.float64), np.float64)
        affine = affines[plane]
        if affine is not None and select.size:
            base[select] += affine.offsets(centred) @ basis.T
        out.append(base)
    return tuple(out)


def affine_override_builder(address, affines):
    """A ``fit_region(refit_overrides=...)`` builder for a fitted affine.

    THE PER-CELL REFIT SEAM (docs/INDEPENDENT-PLANES §6 P2/E1).  Handing
    this to ``_swim_region.fit_region`` re-fits the whole restricted
    region — registration, QDA, PAVA and the A5 context BINS — with the
    target tile sampled at its fitted geometry, on both arms, instead of
    scoring the corrected samples through a detector cut at delta = 0.
    """
    def build(row, residuals, spec, base_is_residual: bool) -> tuple:
        return affine_override(row, residuals, spec, address, affines,
                               base_is_residual)

    return build


def capture_blocks_at(fit, raster, spec, address, ordinals, affines) -> tuple:
    """One capture's durable blocks with this tile sampled at ``affines``."""
    from holo.receive.color_anchoring import _features_with_page_fraction

    windows = []
    for ordinal in ordinals:
        row = fit.rows[ordinal]
        features = _features_with_page_fraction(
            raster, row, fit.residuals, spec, fit.pitch_px, fit.divisor,
            offsets_override=affine_override(
                row, fit.residuals, spec, address, affines,
                fit.base_is_residual))
        if features is None:
            continue
        windows.append(_swim_region.window_evidence(fit, ordinal, features))
    if not windows:
        return ()
    return _swim_region.capture_blocks(fit, spec, windows)


# --------------------------------------------------------------------------
# ground-truth cell mismatch through the production detector
# --------------------------------------------------------------------------
def mismatch_map(blocks, spec, address, plane: int, payload_indices,
                 truth) -> dict:
    """Hard-decision mismatch against the printed truth, as a tile map."""
    from holo.receive.evidence_blocks import tile_attempt_view

    components = tuple(row for row in blocks if row.address == address)
    if not components:
        return {"observed": 0, "ber": None}
    view = tile_attempt_view(components)
    values = view.llr_cells_f64.reshape(
        TILE_CELLS * TILE_CELLS, view.arity)[payload_indices][:, plane]
    observed = view.observed_cells().reshape(
        TILE_CELLS * TILE_CELLS)[payload_indices]
    if not observed.any():
        return {"observed": 0, "ber": None}
    wrong = (values > 0.0) != (truth > 0.5)
    grid = np.zeros((TILE_CELLS, TILE_CELLS), np.float64)
    valid = np.zeros((TILE_CELLS, TILE_CELLS), bool)
    cells = np.asarray(payload_indices)[observed]
    grid[cells // TILE_CELLS, cells % TILE_CELLS] = wrong[observed]
    valid[cells // TILE_CELLS, cells % TILE_CELLS] = True
    return {
        "observed": int(observed.sum()),
        "errors": int(wrong[observed].sum()),
        "ber": float(wrong[observed].mean()),
        "mean_abs_llr": float(np.abs(values[observed]).mean()),
        "_grid": grid, "_valid": valid,
    }


def configuration(states, spec, target, affines_by_capture, payload_indices,
                  truth, *, attempt: bool) -> dict:
    """One geometry: per-capture blocks, per-capture and union mismatch."""
    per_capture = []
    rows = {}
    for sha, (fit, raster, ordinals) in states.items():
        blocks = capture_blocks_at(
            fit, raster, spec, target.address, ordinals,
            affines_by_capture.get(sha, (None, None, None)))
        per_capture.append(blocks)
        row = mismatch_map(blocks, spec, target.address, target.plane,
                           payload_indices, truth)
        rows[sha] = {key: value for key, value in row.items()
                     if not key.startswith("_")}
    union = tuple(row for blocks in per_capture for row in blocks)
    combined = mismatch_map(union, spec, target.address, target.plane,
                            payload_indices, truth)
    out = {
        "per_capture": rows,
        "union_ber": combined.get("ber"),
        "union_observed": combined.get("observed"),
        "union_mean_abs_llr": combined.get("mean_abs_llr"),
        "_grid": combined.get("_grid"), "_valid": combined.get("_valid"),
    }
    if attempt:
        out["verdict"] = union_verdict(per_capture, spec, target)
    return out


# --------------------------------------------------------------------------
# one tile
# --------------------------------------------------------------------------
def shifted(affines: tuple, plane: int, dx: float, dy: float) -> tuple:
    """One plane's affine translated by ``(dx, dy)`` page dots."""
    from ._affine_fit import Affine

    out = list(affines)
    base = out[plane] or Affine(0.0, 0.0)
    out[plane] = Affine(base.tx + dx, base.ty + dy, base.m)
    return tuple(out)


def ber_polish(states, spec, target, base_affines, payload_indices, truth,
               *, radius: float, step: float, evaluate) -> dict:
    """A BER-DIRECT local search around the fitted affine.

    The NCC objective is a proxy: it is what a real receiver could
    plausibly optimise, but the quantity that decides a tile is the CELL
    ERROR, and the two optima do not have to coincide (the swim's 1-D
    grid, which minimised BER directly, beats the NCC fit on some tiles).
    This closes that gap for the CEILING claim: the target plane's
    translation is swept on a small grid ON TOP of the fitted affine and
    the union cell error itself picks the winner — the most favourable
    geometry this model can present to the decoder, chosen with full
    knowledge of the answer.
    """
    count = int(round(radius / step))
    axis = np.round(np.arange(-count, count + 1) * step, 6)
    best = None
    curve = []
    for dx in axis:
        for dy in axis:
            affines = {sha: shifted(base_affines[sha], target.plane,
                                    float(dx), float(dy))
                       for sha in base_affines}
            row = evaluate(affines, attempt=False)
            curve.append({"dx": float(dx), "dy": float(dy),
                          "union_ber": row["union_ber"]})
            if row["union_ber"] is None:
                continue
            if best is None or row["union_ber"] < best[0]:
                best = (row["union_ber"], float(dx), float(dy), affines)
    if best is None:
        return {"searched": len(curve), "union_ber": None}
    out = evaluate(best[3], attempt=True)
    out["searched"] = len(curve)
    out["extra_translation_dots_xy"] = [best[1], best[2]]
    out["curve"] = curve
    return out


def tile_truth_planes(truth_bits, address) -> np.ndarray:
    _page, tile_y, tile_x = address
    return truth_bits[tile_y * TILE_CELLS:(tile_y + 1) * TILE_CELLS,
                      tile_x * TILE_CELLS:(tile_x + 1) * TILE_CELLS, :]


def fit_one_tile(states, spec, address, truth_bits, *, coarse_max: float,
                 coarse_step: float, raster_by_capture) -> dict:
    """Every (plane, capture) fit for one tile, 2-dof and 6-dof."""
    tile_bits = tile_truth_planes(truth_bits, address)
    rows: dict[str, dict] = {}
    null_proofs: dict[str, dict] = {}
    for sha, (fit, raster, ordinals) in states.items():
        sampler = TileSampler(fit, raster, spec, address, ordinals)
        null_proofs[sha] = sampler.null_proof(raster)
        truth_by_plane = np.stack(
            [sampler.truth(tile_bits, plane) for plane in range(3)])
        per_plane: dict[str, dict] = {}
        for plane in range(3):
            translation = _affine_fit.fit_affine(
                sampler, plane, truth_by_plane, coarse_max=coarse_max,
                coarse_step=coarse_step, dof=2)
            full = _affine_fit.fit_affine(
                sampler, plane, truth_by_plane, coarse_max=coarse_max,
                coarse_step=coarse_step, dof=6)
            values = sampler.sample(plane, full["affine"])
            values0 = sampler.sample(plane, None)
            per_plane[PLANE_NAMES[plane]] = {
                "translation_fit": translation,
                "affine_fit": full,
                "separation_at_affine": _affine_fit.separation(
                    values, truth_by_plane[plane], full["objective"]),
                "separation_at_zero": _affine_fit.separation(
                    values0, truth_by_plane[plane], full["objective"]),
                "oracle_threshold_at_affine": _affine_fit
                .oracle_threshold_ber(values, truth_by_plane[plane]),
                "oracle_threshold_at_zero": _affine_fit
                .oracle_threshold_ber(values0, truth_by_plane[plane]),
                "oracle_stratified_at_affine": _affine_fit
                .stratified_oracle_ber(values, truth_by_plane, plane),
                "ink_fraction": float((truth_by_plane[plane] > 0.5).mean()),
                "n_samples": int(sampler.n_samples),
            }
        rows[sha] = per_plane
    del raster_by_capture
    return {"by_capture": rows, "null_proof": null_proofs}


def serialise_fit(row: dict, cell_dots: int) -> dict:
    """One plane/capture fit without the live objective object."""
    def one(entry: dict) -> dict:
        return {
            "dof": entry["dof"],
            "parameters": entry["affine"].report(cell_dots),
            "partial_ncc": entry["partial_ncc"],
            "partial_ncc_at_zero": entry["partial_ncc_at_zero"],
            "raw_ncc": entry["raw_ncc"],
            "evaluations": entry["evaluations"],
            "optimiser_success": entry["optimiser_success"],
        }
    out = {key: value for key, value in row.items()
           if key not in ("translation_fit", "affine_fit")}
    out["translation_fit"] = one(row["translation_fit"])
    out["affine_fit"] = one(row["affine_fit"])
    return out


# --------------------------------------------------------------------------
# reference tiles: certified, clean column
# --------------------------------------------------------------------------
def reference_row(fits, rasters, spec, address, truth_bits, *, coarse_max,
                  coarse_step) -> dict:
    """The same measurement on a certified tile, minus the decode path.

    A fully certified tile is SUPPRESSED by the production emission mask,
    so it has no evidence blocks and no detector BER — but the sampled
    values, the fitted geometry and the class separation are all
    available, and those are exactly what the reference is for.
    """
    tile_bits = tile_truth_planes(truth_bits, address)
    rows: dict[str, dict] = {}
    for sha, by_region in fits.items():
        found = None
        for _region, fit in sorted(by_region.items()):
            ordinals = fit.tile_rows.get(address, ()) if (
                fit.selected_fit is not None) else ()
            if ordinals and (found is None or len(ordinals) > len(found[1])):
                found = (fit, ordinals)
        if found is None:
            continue
        fit, ordinals = found
        sampler = TileSampler(fit, rasters[sha], spec, address, ordinals)
        truth_by_plane = np.stack(
            [sampler.truth(tile_bits, plane) for plane in range(3)])
        per_plane = {}
        for plane in range(3):
            full = _affine_fit.fit_affine(
                sampler, plane, truth_by_plane, coarse_max=coarse_max,
                coarse_step=coarse_step, dof=6)
            values = sampler.sample(plane, full["affine"])
            per_plane[PLANE_NAMES[plane]] = {
                "affine_fit": {
                    "dof": 6,
                    "parameters": full["affine"].report(spec.cell_dots),
                    "partial_ncc": full["partial_ncc"],
                    "partial_ncc_at_zero": full["partial_ncc_at_zero"],
                    "raw_ncc": full["raw_ncc"],
                    "evaluations": full["evaluations"],
                    "optimiser_success": full["optimiser_success"]},
                "separation_at_affine": _affine_fit.separation(
                    values, truth_by_plane[plane], full["objective"]),
                "separation_at_zero": _affine_fit.separation(
                    sampler.sample(plane, None), truth_by_plane[plane],
                    full["objective"]),
                "oracle_threshold_at_affine": _affine_fit
                .oracle_threshold_ber(values, truth_by_plane[plane]),
                "oracle_stratified_at_affine": _affine_fit
                .stratified_oracle_ber(values, truth_by_plane, plane),
                "ink_fraction": float((truth_by_plane[plane] > 0.5).mean()),
            }
        rows[sha] = per_plane
    return {"page": address[0], "tile_y": address[1], "tile_x": address[2],
            "role": "certified-reference", "by_capture": rows}


__all__ = ["GATE_BER", "OUT_DIR", "SCHEMA", "SWIM_RESULTS",
           "affine_override", "affine_override_builder", "ber_polish",
           "capture_blocks_at", "configuration", "fit_one_tile", "main",
           "mismatch_map", "reference_row", "serialise_fit", "shifted",
           "tile_truth_planes"]


def _swim_reference() -> dict:
    """The swim pilot's own numbers, keyed by (tile_y, tile_x, stream)."""
    if not SWIM_RESULTS.is_file():
        return {}
    rows = json.loads(SWIM_RESULTS.read_text())
    out = {}
    for row in rows.get("targets", ()):
        if "error" in row:
            continue
        curve = row.get("ber_curve") or {}
        out[(row["tile_y"], row["tile_x"], row["stream"])] = {
            "ber_at_zero": curve.get("ber_at_zero"),
            "ber_min_translation": curve.get("ber_min"),
            "ber_argmin_dx": curve.get("ber_argmin_dx"),
            "delta_neighbour_dx": row.get("delta_neighbour_dx"),
            "delta_own_dx": row.get("delta_own_dx"),
            "regmap_dY_rel_x_centred":
                (row.get("regmap_gt") or {}).get("dY_rel_x_centred"),
            "swim_certified": row["swim"]["certified_any"],
        }
    return out


def main(argv: list[str] | None = None) -> int:
    from ._gt_affine_run import run

    parser = argparse.ArgumentParser(
        prog="plane_fields.gt_affine", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tiles", type=int, default=10)
    parser.add_argument("--clear-band-targets", type=int, default=3)
    parser.add_argument("--reproduction-controls", type=int, default=2)
    parser.add_argument("--fit-radius", type=int, default=3)
    parser.add_argument("--reference-tiles", type=int, default=6,
                        help="certified tiles in clear columns that get the "
                             "same separation measurement, as reference")
    parser.add_argument("--coarse-max", type=float, default=1.5,
                        help="half-width of the coarse translation grid, "
                             "print dots")
    parser.add_argument("--coarse-step", type=float, default=0.25)
    parser.add_argument("--limit", type=int, default=0,
                        help="stop after this many targets (0 = all)")
    parser.add_argument("--permutations", type=int, default=199)
    parser.add_argument("--polish-radius", type=float, default=0.375,
                        help="half-width of the BER-DIRECT translation "
                             "search around the fitted affine, print dots "
                             "(0 disables it)")
    parser.add_argument("--polish-step", type=float, default=0.125)
    parser.add_argument("--q", type=float, default=0.9)
    parser.add_argument("--lane", default=None)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--tag", default="v1")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
