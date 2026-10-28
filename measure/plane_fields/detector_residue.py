#!/usr/bin/env python
"""P2 — WHERE THE DEAD-BAND RESIDUE LIVES: recut bins, direction, contrast.

docs/INDEPENDENT-PLANES §6 P2 asks three questions of the sheet-I dead
bands, all of them answerable from the archived captures with no toner
and no new state.  This instrument answers all three in ONE pass over the
three 2400 dpi captures, because the expensive part — placing the
committed poses and fitting the restricted region — is shared:

**E1, THE RECUT-BINS REFIT.**  ``gt_affine`` scored its supervised
geometries through a detector CUT AT DELTA = 0, where dead tiles are
11–22 % wrong and controls ~8 % — so the staleness of the A5 context
bins correlated with the very grouping being compared, and the
"detector-created ~2.3 pp" reading was a hypothesis, not a measurement.
Here each target's fitted 6-dof affine (plus its BER-direct polish
translation) is fed to ``fit_region``'s REFIT seam instead: the whole
restricted region is re-fitted with that tile sampled at the corrected
geometry, so the registration fit, the QDA/PAVA stack, the A5 context
bins and the emission all see it.  Frozen and refit are then the same
tile, the same pixels, the same geometry, one variable.

**E2, DIRECTIONAL-NEIGHBOUR STRATIFICATION.**  Pure re-analysis of the
samples at the fitted geometry: every Y cell classified by whether the
neighbour in the direction of the fitted Y translation carries C or M
ink.  See ``_residue_strata`` for the mechanism this tests and for the
built-in falsifier (the UPSTREAM neighbour).

**E3, PER-STATE Y CONTRAST.**  The same samples split by the SAME cell's
(C, M) state, on dead tiles and on certified clean-column reference
tiles — the mix-compression question, which §2.7 lists as inferred and
unmeasured.

Everything is READ-ONLY: the W6 state, the three sha-pinned captures and
``gt-affine-final2.json`` are opened for reading, and nothing is written
outside ``scratch/plane-fields/p2/``.

    cd <repo>
    PYTHONPATH=src:measure env/bin/python -m plane_fields.detector_residue
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from . import _residue_strata, _swim_inputs, _swim_region
from ._affine_fit import Affine, TileSampler
from ._swim_setup import (
    PAGE,
    LaneRasters,
    build_placements,
    restricted_placements,
)

SCHEMA = "plane-fields-detector-residue-v1"
OUT_DIR = _swim_inputs.MAIN_SCRATCH / "plane-fields" / "p2"
GT_AFFINE = (_swim_inputs.MAIN_SCRATCH / "plane-fields" / "gt-affine"
             / "gt-affine-final2.json")
PLANE_NAMES = ("C", "M", "Y")

#: The six dead-band tiles and two reproduction controls the brief names.
#: They are ASSERTED against the selection rather than substituted for
#: it, so this run and ``gt-affine-final2.json`` are the same tiles.
DEAD_TILES = ((14, 9), (23, 18), (29, 8), (31, 15), (34, 27), (47, 28))
CONTROL_TILES = ((15, 7), (24, 20))


# --------------------------------------------------------------------------
# the geometries under test, read from the supervised ceiling run
# --------------------------------------------------------------------------
def affine_from(parameters: dict) -> Affine:
    """One ``Affine`` back out of its ``report()`` form."""
    tx, ty = parameters["translation_dots_xy"]
    matrix = parameters["m_dots_per_cell"]
    return Affine(float(tx), float(ty),
                  ((float(matrix[0][0]), float(matrix[0][1])),
                   (float(matrix[1][0]), float(matrix[1][1]))))


def geometry_for(row: dict, plane: int, *, polish: bool) -> dict:
    """Per capture, the (C, M, Y) affines this tile is to be sampled at.

    ``polish`` adds the BER-direct translation ``gt_affine`` searched on
    top of the NCC-fitted affine — the best geometry that run ever
    presented to the decoder, and therefore the one a refit has to be
    compared against.
    """
    from .gt_affine import shifted

    by_capture = row["fits"]["by_capture"] if "fits" in row else (
        row["by_capture"])
    extra = ((row.get("configurations", {}).get("polish", {}) or {})
             .get("extra_translation_dots_xy") or [0.0, 0.0]) if polish \
        else [0.0, 0.0]
    out = {}
    for sha, per_plane in by_capture.items():
        affines = tuple(
            affine_from(per_plane[name]["affine_fit"]["parameters"])
            for name in PLANE_NAMES)
        out[sha] = shifted(affines, plane, float(extra[0]), float(extra[1]))
    return {"by_capture": out, "polish_extra_dots_xy": [float(extra[0]),
                                                        float(extra[1])]}


def read_ceiling(path: Path) -> dict:
    """``gt-affine-final2.json`` reduced to what this run consumes."""
    document = json.loads(path.read_text())
    targets = {}
    for row in document["targets"]:
        if "error" in row:
            continue
        targets[(row["tile_y"], row["tile_x"], row["stream"])] = row
    references = {(row["tile_y"], row["tile_x"]): row
                  for row in document.get("references", ())}
    return {"targets": targets, "references": references,
            "state_sha256": document["state"]["sha256"],
            "lane": document["lane"]["lane_id"],
            "tree_before": document.get("tree_before"),
            "wall_seconds": document.get("wall_seconds")}


# --------------------------------------------------------------------------
# blocks
# --------------------------------------------------------------------------
def _for_address(blocks, address) -> tuple:
    return tuple(row for row in blocks if row.address == address)


def frozen_blocks(fit, raster, spec, address, affines) -> tuple:
    """The FROZEN arm: the delta = 0 detector scoring corrected samples."""
    from .gt_affine import capture_blocks_at

    ordinals = fit.tile_rows.get(address, ())
    if not ordinals:
        return ()
    return _for_address(
        capture_blocks_at(fit, raster, spec, address, ordinals, affines),
        address)


def refit_blocks(fit, spec, address) -> tuple:
    """The REFIT arm: the tile's own retained features, at the correction.

    ``fit_region(keep_features_for={address}, refit_overrides=...)`` keeps
    exactly the features the refitted detector was fitted on, so nothing
    is re-sampled here and the emission cannot drift between the fit and
    the evidence.
    """
    windows = []
    for ordinal in fit.tile_rows.get(address, ()):
        features = fit.features0.get(ordinal)
        if features is None:
            continue
        windows.append(_swim_region.window_evidence(fit, ordinal, features))
    if not windows:
        return ()
    return _for_address(_swim_region.capture_blocks(fit, spec, windows),
                        address)


def _e1_line(key: str, target, entry: dict) -> str:
    """One progress line, tolerant of a refused arm (never a TypeError)."""
    def rate(value) -> str:
        return "  n/a " if value is None else f"{value:.4f}"

    frozen = entry.get("frozen") or {}
    refit = entry.get("refit") or {}
    probe = refit.get("refit_probe") or {}
    band = "dead" if target.band == "dead" and target.role == "target" \
        else "ctrl"
    line = (f"    E1 {key:<12} {band}/{target.role[:6]} "
            f"arm={frozen.get('arm', '?')} frozen "
            f"{rate(frozen.get('ber'))}")
    if refit:
        line += (f" -> refit {rate(refit.get('ber'))} "
                 f"(logloss {frozen.get('heldout_logloss', float('nan')):.5f}"
                 f" -> {refit.get('heldout_logloss', float('nan')):.5f}, "
                 f"|Δfeature| {probe.get('min_abs_feature_delta', 0.0):.4f}"
                 f"..{probe.get('max_abs_feature_delta', 0.0):.4f}, "
                 f"{probe.get('arm', '?')})")
    return line + (f" [{entry.get('refit_seconds', 0.0) + entry.get('frozen_seconds', 0.0):.0f}s]")


def mismatch(blocks, spec, address, plane, payload_indices, truth) -> dict:
    from .gt_affine import mismatch_map

    row = mismatch_map(blocks, spec, address, plane, payload_indices, truth)
    return {key: value for key, value in row.items()
            if not key.startswith("_")}


# --------------------------------------------------------------------------
# one capture's work
# --------------------------------------------------------------------------
def capture_pass(capture, spec, scans, facts, lane, targets, measured,
                 references, ceiling, fit_certificates, truth_bits,
                 payload_indices, *, fit_radius: int, do_refit: bool,
                 log) -> dict:
    """Everything one capture contributes, then its raster is released.

    ONE capture is resident at a time — ``gt_affine`` held all three and
    peaked at 16.6 GB, which this machine cannot afford while another
    decode is running.  The evidence blocks that survive the release are
    a few tens of kilobytes each.
    """
    sha = capture.source_sha256
    started = time.time()
    holder = LaneRasters(spec, capture, scans[sha])
    try:
        raster = holder.for_lane(lane)
        placements, _poses = build_placements(facts, spec, capture, lane,
                                              raster)
        grouped = restricted_placements(placements, targets, fit_radius)
        del placements
        from holo.receive.payload_model import EvidenceSource

        source = EvidenceSource(sha, lane.lane_id)
        keep = frozenset(row.address for row in targets)
        fits: dict[int, object] = {}
        for region_index, patches in sorted(grouped.items()):
            region_id = (f"{sha}/{lane.lane_id}/region-{region_index}/"
                         f"page-{PAGE}")
            fits[region_index] = _swim_region.fit_region(
                spec, raster, source, patches, fit_certificates, PAGE,
                region_id, keep_features_for=keep)
        log(f"  {sha[:12]} regions "
            + ", ".join(f"{key}:{value.n_windows}w/{value.n_labels}l"
                        f"{'*A1' if value.adopted else ' A0'}"
                        for key, value in sorted(fits.items()))
            + f"; setup {time.time() - started:.0f}s")

        def carrier(address):
            best = None
            for region_index, fit in sorted(fits.items()):
                if fit.selected_fit is None:
                    continue
                ordinals = fit.tile_rows.get(address, ())
                if ordinals and (best is None or len(ordinals) > len(best[1])):
                    best = (fit, ordinals, region_index)
            return best

        out: dict = {"capture": sha, "e1": {}, "e2": {}, "e3": {},
                     "null_proof": {}, "region": {
                         str(key): {"windows": value.n_windows,
                                    "labels": value.n_labels,
                                    "adopted_A1": bool(value.adopted),
                                    "heldout_logloss": value.heldout_loss,
                                    "refusal": value.refusal}
                         for key, value in sorted(fits.items())}}

        # E1 -------------------------------------------------------------
        for target in measured:
            key = f"{target.tile_y},{target.tile_x}/{target.stream}"
            found = carrier(target.address)
            if found is None:
                out["e1"][key] = {"error": "no region window carries it"}
                continue
            fit, ordinals, region_index = found
            if sha not in out["null_proof"]:
                out["null_proof"][sha] = _swim_region.null_proof(
                    fit, raster, spec, ordinals[0])
            ceiling_row = ceiling["targets"][
                (target.tile_y, target.tile_x, target.stream)]
            geometry = geometry_for(ceiling_row, target.plane, polish=True)
            affines = geometry["by_capture"][sha]
            tile_bits = truth_bits[
                target.tile_y * 64:(target.tile_y + 1) * 64,
                target.tile_x * 64:(target.tile_x + 1) * 64, :]
            truth = tile_bits.reshape(-1, 3)[payload_indices][:, target.plane]
            mark = time.time()
            blocks = frozen_blocks(fit, raster, spec, target.address, affines)
            entry = {
                "geometry": {
                    "polish_extra_dots_xy": geometry["polish_extra_dots_xy"],
                    "affine_parameters": {
                        name: affines[plane].report(spec.cell_dots)
                        for plane, name in enumerate(PLANE_NAMES)}},
                "frozen": {
                    "arm": "A1" if fit.adopted else "A0",
                    "heldout_logloss": float(fit.heldout_loss),
                    **mismatch(blocks, spec, target.address, target.plane,
                               payload_indices, truth)},
                "_frozen_blocks": blocks,
                "frozen_seconds": round(time.time() - mark, 1),
            }
            if do_refit:
                from .gt_affine import affine_override_builder

                mark = time.time()
                patches = grouped.get(region_index, ())
                region_id = (f"{sha}/{lane.lane_id}/region-{region_index}/"
                             f"page-{PAGE}")
                refit = _swim_region.fit_region(
                    spec, raster, source, patches, fit_certificates, PAGE,
                    region_id,
                    keep_features_for=frozenset({target.address}),
                    refit_overrides={
                        target.address: affine_override_builder(
                            target.address, affines)})
                if refit.selected_fit is None:
                    entry["refit"] = {"error": refit.refusal}
                else:
                    blocks = refit_blocks(refit, spec, target.address)
                    entry["refit"] = {
                        "arm": "A1" if refit.adopted else "A0",
                        "heldout_logloss": float(refit.heldout_loss),
                        "refit_probe": refit.refit_probe,
                        **mismatch(blocks, spec, target.address,
                                   target.plane, payload_indices, truth)}
                    entry["_refit_blocks"] = blocks
                entry["refit_seconds"] = round(time.time() - mark, 1)
                del refit
            out["e1"][key] = entry
            log(_e1_line(key, target, entry))

        # E2 / E3 --------------------------------------------------------
        for target in measured:
            key = f"{target.tile_y},{target.tile_x}/{target.stream}"
            found = carrier(target.address)
            if found is None:
                continue
            fit, ordinals, _region = found
            ceiling_row = ceiling["targets"][
                (target.tile_y, target.tile_x, target.stream)]
            affines = geometry_for(
                ceiling_row, target.plane, polish=True)["by_capture"][sha]
            sampler = TileSampler(fit, raster, spec, target.address, ordinals)
            tile_bits = truth_bits[
                target.tile_y * 64:(target.tile_y + 1) * 64,
                target.tile_x * 64:(target.tile_x + 1) * 64, :]
            truth_by_plane = np.stack(
                [sampler.truth(tile_bits, plane) for plane in range(3)])
            values = sampler.sample(target.plane, affines[target.plane])
            out["e2"][key] = _residue_strata.directional_table(
                sampler, target.address, truth_bits, values, truth_by_plane,
                affines[target.plane].tx, affines[target.plane].ty)
            out["e3"][key] = _residue_strata.state_contrast(
                values, truth_by_plane)
            del sampler

        for address in references:
            found = carrier(address)
            reference = ceiling["references"].get((address[1], address[2]))
            if found is None or reference is None:
                continue
            fit, ordinals, _region = found
            affines = geometry_for(reference, 2, polish=False)["by_capture"][
                sha]
            sampler = TileSampler(fit, raster, spec, address, ordinals)
            tile_bits = truth_bits[address[1] * 64:(address[1] + 1) * 64,
                                   address[2] * 64:(address[2] + 1) * 64, :]
            truth_by_plane = np.stack(
                [sampler.truth(tile_bits, plane) for plane in range(3)])
            values = sampler.sample(2, affines[2])
            out["e3"][f"ref {address[1]},{address[2]}/Y"] = (
                _residue_strata.state_contrast(values, truth_by_plane))
            out["e2"][f"ref {address[1]},{address[2]}/Y"] = (
                _residue_strata.directional_table(
                    sampler, address, truth_bits, values, truth_by_plane,
                    affines[2].tx, affines[2].ty))
            del sampler
        out["seconds"] = round(time.time() - started, 1)
        return out
    finally:
        holder.release()


__all__ = ["CONTROL_TILES", "DEAD_TILES", "GT_AFFINE", "OUT_DIR",
           "PLANE_NAMES", "SCHEMA", "affine_from", "capture_pass",
           "frozen_blocks", "geometry_for", "main", "mismatch",
           "read_ceiling", "refit_blocks"]

# NOTE on E2/E3's geometry: the samples are taken AT the fitted affine —
# i.e. AFTER the per-plane displacement has been corrected — while the
# stratification DIRECTION is that same fitted translation.  The test is
# therefore whether a directional signature SURVIVES the correction.  It
# is not the "the aperture is currently sliding toward the neighbour"
# test, which would be run at delta = 0; a survivor implicates the ink
# and the optics rather than the sampling position.


def main(argv: list[str] | None = None) -> int:
    from ._residue_run import run

    parser = argparse.ArgumentParser(
        prog="plane_fields.detector_residue", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tiles", type=int, default=10)
    parser.add_argument("--clear-band-targets", type=int, default=3)
    parser.add_argument("--reproduction-controls", type=int, default=2)
    parser.add_argument("--fit-radius", type=int, default=3)
    parser.add_argument("--q", type=float, default=0.9)
    parser.add_argument("--lane", default=None)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--workers", type=int, default=1,
                        help="holo.receive worker threads; results are "
                             "bit-identical for any count (the _parallel "
                             "determinism contract) — 1 keeps this run "
                             "byte-comparable with gt-affine-final2")
    parser.add_argument("--no-refit", action="store_true",
                        help="E2/E3 only: skip the E1 refit arm")
    parser.add_argument("--limit", type=int, default=0,
                        help="measure only the first N of the eight tiles")
    parser.add_argument("--captures", type=int, default=3,
                        help="measure only the first N captures; a UNION "
                             "attempt names at least two blocks, so 1 is a "
                             "smoke test and never a verdict")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--from-raw", action="store_true",
                        help="skip the captures and rebuild the summaries, "
                             "files and figures from p2/raw.json — the "
                             "expensive rows are written there BEFORE any "
                             "summary runs")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
