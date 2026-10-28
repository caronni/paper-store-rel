"""The gt-affine run: setup, the per-target loop, the cross-tile synthesis.

Split out of :mod:`gt_affine` so the measurement seams (the per-cell
affine override, the mismatch map, the configuration comparison) stay
readable next to each other and the driving stays here.  The setup is the
swim pilot's, function for function — same state, same lane, same
restricted-region fit, same targets on the same seed — so every number
this instrument reports is directly comparable with
``swim-pilot-final.json``.
"""
from __future__ import annotations

import json
import resource
import time

import numpy as np

from . import _affine_fit, _swim_inputs, _swim_region, _swim_truth
from ._swim_inputs import CAPTURE_DPI, DEAD_BANDS, FORMAT_REF, QUAL_STATE
from ._swim_setup import (
    PAGE,
    LaneRasters,
    build_placements,
    certified_index,
    choose_lane,
    residue_by_column,
    restricted_placements,
    select_controls,
    select_targets,
)

PLANE_NAMES = ("C", "M", "Y")


def _fit_for(fits, capture_sha256, address):
    best = None
    for _region, fit in sorted(fits.get(capture_sha256, {}).items()):
        if fit.selected_fit is None:
            continue
        ordinals = fit.tile_rows.get(address, ())
        if ordinals and (best is None or len(ordinals) > len(best[1])):
            best = (fit, ordinals)
    return best


def _mean(values):
    values = [float(v) for v in values if v is not None and np.isfinite(v)]
    return float(np.mean(values)) if values else None


# --------------------------------------------------------------------------
# cross-tile synthesis
# --------------------------------------------------------------------------
def _jacobian_table(rows: list[dict]) -> dict:
    """Systematic or idiosyncratic?  Per plane, across tiles and captures.

    Two spreads decide it.  ``sd_across_captures`` is the same tile fitted
    on three INDEPENDENT captures of the same paper: a real geometric
    error reproduces there, measurement noise does not.  ``sd_across_
    tiles`` is the spread of the per-tile means.  A term is SYSTEMATIC
    when its mean is large against the across-tile spread AND reproduces
    across captures; it is idiosyncratic when the two spreads are
    comparable and the mean is not.
    """
    keys = ("scale_x_pct", "scale_y_pct", "rotation_deg", "shear_deg")
    out: dict[str, dict] = {}
    for plane in PLANE_NAMES:
        per_key: dict[str, dict] = {}
        for key in keys:
            per_tile_means: list[float] = []
            within: list[float] = []
            for row in rows:
                values = [
                    entry[plane]["affine_fit"]["parameters"][key]
                    for entry in row["fits"]["by_capture"].values()
                    if plane in entry]
                if len(values) < 2:
                    continue
                per_tile_means.append(float(np.mean(values)))
                within.append(float(np.std(values, ddof=1)))
            if not per_tile_means:
                continue
            mean = float(np.mean(per_tile_means))
            across = float(np.std(per_tile_means, ddof=1)) if len(
                per_tile_means) > 1 else float("nan")
            per_key[key] = {
                "mean": mean,
                "sd_across_tiles": across,
                "sd_across_captures": float(np.mean(within)),
                "n_tiles": len(per_tile_means),
                "mean_over_sd_across_tiles": (
                    None if not np.isfinite(across) or across == 0.0
                    else float(mean / across)),
                "reproducibility_ratio": (
                    None if not np.isfinite(across) or np.mean(within) == 0.0
                    else float(across / np.mean(within))),
            }
        out[plane] = per_key
    return out


def _translation_agreement(rows: list[dict]) -> dict:
    """The affine's translation against the swim's and the neighbours'."""
    from scipy import stats

    pairs = []
    for row in rows:
        if row["stream"] != "Y":
            continue
        plane = row["stream"]
        values = [
            entry[plane]["affine_fit"]["parameters"]["translation_dots_xy"][0]
            for entry in row["fits"]["by_capture"].values() if plane in entry]
        translation_only = [
            entry[plane]["translation_fit"]["parameters"][
                "translation_dots_xy"][0]
            for entry in row["fits"]["by_capture"].values() if plane in entry]
        swim = row.get("swim") or {}
        pairs.append({
            "tile_y": row["tile_y"], "tile_x": row["tile_x"],
            "role": row["role"], "band": row["band"],
            "affine_tx_mean": _mean(values),
            "affine_tx_sd": (float(np.std(values, ddof=1))
                             if len(values) > 1 else None),
            "translation_only_tx_mean": _mean(translation_only),
            "swim_ber_argmin_dx": swim.get("ber_argmin_dx"),
            "neighbour_dx": swim.get("delta_neighbour_dx"),
            "regmap_dx": swim.get("regmap_dY_rel_x_centred"),
        })

    def correlate(left: str, right: str):
        rows_ = [(row[left], row[right]) for row in pairs
                 if row.get(left) is not None and row.get(right) is not None]
        if len(rows_) < 4:
            return None
        a = [value for value, _ in rows_]
        b = [value for _, value in rows_]
        pearson = stats.pearsonr(a, b)
        spearman = stats.spearmanr(a, b)
        return {"n": len(rows_), "pearson_r": float(pearson.statistic),
                "pearson_p": float(pearson.pvalue),
                "spearman_rho": float(spearman.statistic),
                "spearman_p": float(spearman.pvalue),
                "mean_abs_gap": float(np.mean(
                    [abs(x - y) for x, y in rows_]))}

    return {
        "per_tile": pairs,
        "affine_vs_swim": correlate("affine_tx_mean", "swim_ber_argmin_dx"),
        "affine_vs_neighbour": correlate("affine_tx_mean", "neighbour_dx"),
        "affine_vs_regmap": correlate("affine_tx_mean", "regmap_dx"),
        "affine_vs_translation_only": correlate(
            "affine_tx_mean", "translation_only_tx_mean"),
    }


def _dof_ladder(rows: list[dict]) -> dict:
    """The 0 -> 2 -> 6 degree-of-freedom chain, on the union decision."""
    def chain(subset: list[dict]) -> dict:
        return {
            "n": len(subset),
            "ber_delta0": _mean(
                row["configurations"]["zero"]["union_ber"] for row in subset),
            "ber_swim_translation_grid": _mean(
                (row.get("swim") or {}).get("ber_min_translation")
                for row in subset),
            "ber_translation_fit": _mean(
                row["configurations"]["translation"]["union_ber"]
                for row in subset),
            "ber_affine_fit": _mean(
                row["configurations"]["affine"]["union_ber"]
                for row in subset),
            "ber_affine_plus_ber_polish": _mean(
                row["configurations"].get("polish", {}).get("union_ber")
                for row in subset),
            "ber_best_known_geometry": _mean(
                min(v for v in (
                    row["configurations"]["affine"]["union_ber"],
                    row["configurations"].get("polish", {}).get("union_ber"),
                    (row.get("swim") or {}).get("ber_min_translation"))
                    if v is not None)
                for row in subset),
            "oracle_threshold_at_affine": _mean(
                np.mean([entry[row["stream"]][
                    "oracle_threshold_at_affine"]["ber"]
                    for entry in row["fits"]["by_capture"].values()])
                for row in subset),
            "oracle_stratified_at_affine": _mean(
                np.mean([entry[row["stream"]][
                    "oracle_stratified_at_affine"]["ber"]
                    for entry in row["fits"]["by_capture"].values()])
                for row in subset),
        }
    targets = [row for row in rows if row["role"] == "target"]
    return {
        "all_targets": chain(targets),
        "dead_band_targets": chain(
            [row for row in targets if row["band"] == "dead"]),
        "clear_band_targets": chain(
            [row for row in targets if row["band"] == "clear"]),
        "reproduction_controls": chain(
            [row for row in rows if row["role"] != "target"]),
    }


def _photometry(rows: list[dict]) -> dict:
    """Same footing, three decisions: the discriminator for (2) vs (3).

    The union BER mixes three captures, so it cannot be compared with a
    single capture's threshold ceiling.  These three are all PER CAPTURE
    at the fitted affine: what the production detector scored, what the
    best single global threshold on the raw channel would have scored,
    and what a per-crosstalk-stratum threshold would have scored.  A
    detector far above its own stratified ceiling is a CALIBRATION
    finding; a stratified ceiling that is itself high is a SIGNAL
    finding, and no threshold rescues it.
    """
    def chain(subset: list[dict]) -> dict:
        detector, oracle, stratified, dprime, dprime_partial = (
            [], [], [], [], [])
        for row in subset:
            plane = row["stream"]
            entry = row["configurations"]["affine"]["per_capture"]
            for sha, capture in row["fits"]["by_capture"].items():
                detector.append(entry.get(sha, {}).get("ber"))
                oracle.append(
                    capture[plane]["oracle_threshold_at_affine"]["ber"])
                stratified.append(
                    capture[plane]["oracle_stratified_at_affine"]["ber"])
                dprime.append(
                    capture[plane]["separation_at_affine"].get("d_prime"))
                dprime_partial.append(capture[plane][
                    "separation_at_affine"].get("d_prime_partial"))
        return {
            "n_capture_tiles": len(detector),
            "detector_ber_per_capture": _mean(detector),
            "oracle_threshold_ber": _mean(oracle),
            "oracle_stratified_ber": _mean(stratified),
            "d_prime": _mean(dprime),
            "d_prime_partial": _mean(dprime_partial),
        }
    targets = [row for row in rows if row["role"] == "target"]
    return {
        "dead_band_targets": chain(
            [row for row in targets if row["band"] == "dead"]),
        "clear_band_targets": chain(
            [row for row in targets if row["band"] == "clear"]),
        "reproduction_controls": chain(
            [row for row in rows if row["role"] != "target"]),
    }


def _separation_by_plane(rows: list[dict]) -> dict:
    """Every target tile's own C and M next to its failing plane."""
    out: dict[str, dict] = {}
    for band in ("dead", "clear"):
        subset = [row for row in rows
                  if row["role"] == "target" and row["band"] == band]
        per_plane = {}
        for plane in PLANE_NAMES:
            values = [
                capture[plane]["separation_at_affine"].get("d_prime")
                for row in subset
                for capture in row["fits"]["by_capture"].values()]
            partial = [
                capture[plane]["separation_at_affine"].get("d_prime_partial")
                for row in subset
                for capture in row["fits"]["by_capture"].values()]
            per_plane[plane] = {"d_prime": _mean(values),
                                "d_prime_partial": _mean(partial),
                                "n": len([v for v in values if v is not None])}
        out[f"{band}_band_targets"] = per_plane
    return out


def _separation_summary(rows: list[dict], references: list[dict]) -> dict:
    def collect(entries, plane_of):
        values = {"d_prime": [], "d_prime_partial": [], "auc": [],
                  "oracle_ber": []}
        for row in entries:
            plane = plane_of(row)
            for capture in row["fits"]["by_capture"].values() if (
                    "fits" in row) else row["by_capture"].values():
                if plane not in capture:
                    continue
                separation = capture[plane]["separation_at_affine"]
                values["d_prime"].append(separation.get("d_prime"))
                values["d_prime_partial"].append(
                    separation.get("d_prime_partial"))
                values["auc"].append(separation.get("auc"))
                values["oracle_ber"].append(
                    capture[plane]["oracle_threshold_at_affine"]["ber"])
        return {key: {"mean": _mean(value),
                      "sd": (float(np.nanstd([
                          v for v in value if v is not None], ddof=1))
                          if len([v for v in value if v is not None]) > 1
                          else None),
                      "n": len([v for v in value if v is not None])}
                for key, value in values.items()}

    targets = [row for row in rows if row["role"] == "target"]
    return {
        "dead_band_targets": collect(
            [row for row in targets if row["band"] == "dead"],
            lambda row: row["stream"]),
        "clear_band_targets": collect(
            [row for row in targets if row["band"] == "clear"],
            lambda row: row["stream"]),
        "reproduction_controls": collect(
            [row for row in rows if row["role"] != "target"],
            lambda row: row["stream"]),
        "certified_reference_Y": collect(references, lambda _row: "Y"),
        "certified_reference_C": collect(references, lambda _row: "C"),
        "certified_reference_M": collect(references, lambda _row: "M"),
    }


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def run(args) -> int:
    from holo.format import pilots
    from holo.format.resolve import resolve_format_ref
    from holo.receive.payload_model import EvidenceSource

    from . import gt_affine
    from .gt_affine import (
        GATE_BER,
        OUT_DIR,
        SCHEMA,
        ber_polish,
        configuration,
        fit_one_tile,
        reference_row,
        serialise_fit,
        tile_truth_planes,
    )

    started = time.time()
    tree_before = _swim_inputs.tree_state()
    facts = _swim_inputs.read_facts(rebuild=args.rebuild_cache)
    spec = resolve_format_ref(FORMAT_REF)
    scans = _swim_inputs.verified_scan_paths()
    index = certified_index(facts.certificates)
    residue = residue_by_column(index, spec.layout.tiles_yx)
    targets = select_targets(
        index, spec.layout.tiles_yx, n_tiles=args.tiles,
        n_clear=args.clear_band_targets,
        n_controls=args.reproduction_controls, seed=args.seed)
    lane, coverage = choose_lane(facts, targets, forced=args.lane)
    targets = targets + select_controls(
        facts, index, lane, targets, count=args.reproduction_controls,
        radius=args.fit_radius, seed=args.seed)
    if args.limit:
        targets = targets[:args.limit]
    withheld = frozenset(
        (*row.address, row.stream) for row in targets
        if row.role.startswith("reproduction-control"))
    fit_certificates = tuple(
        row for row in facts.certificates
        if (int(row.page), *(int(v) for v in row.tile_yx), row.stream_id)
        not in withheld)

    print(f"state {facts.state_sha256[:12]}… {facts.close_status} "
          f"certs {len(facts.certificates)} lane {lane.lane_id} "
          f"coverage {coverage}")
    print("targets: " + ", ".join(
        f"{row.tile_y},{row.tile_x}/{row.stream}[{row.band[:1]}"
        f"{'C' if row.role != 'target' else ''}]" for row in targets))

    rasters_by_capture: dict[str, LaneRasters] = {}
    rasters: dict[str, object] = {}
    fits: dict[str, dict] = {}
    setup: list[dict] = []
    for capture in facts.captures:
        mark = time.time()
        holder = LaneRasters(spec, capture, scans[capture.source_sha256])
        rasters_by_capture[capture.source_sha256] = holder
        raster = holder.for_lane(lane)
        placements, _poses = build_placements(facts, spec, capture, lane,
                                              raster)
        grouped = restricted_placements(placements, targets, args.fit_radius)
        source = EvidenceSource(capture.source_sha256, lane.lane_id)
        keep = frozenset(row.address for row in targets)
        by_region: dict[int, object] = {}
        for region_index, patches in sorted(grouped.items()):
            region_id = (f"{capture.source_sha256}/{lane.lane_id}/"
                         f"region-{region_index}/page-{PAGE}")
            by_region[region_index] = _swim_region.fit_region(
                spec, raster, source, patches, fit_certificates, PAGE,
                region_id, keep_features_for=keep)
        fits[capture.source_sha256] = by_region
        rasters[capture.source_sha256] = raster
        setup.append({
            "capture": capture.source_sha256,
            "placements": len(placements),
            "regions": {
                str(key): {"windows": value.n_windows,
                           "labels": value.n_labels,
                           "adopted_A1": value.adopted,
                           "heldout_logloss": value.heldout_loss,
                           "refusal": value.refusal}
                for key, value in by_region.items()},
            "setup_seconds": round(time.time() - mark, 1)})
        print(f"  {capture.source_sha256[:12]}… placements "
              f"{len(placements)}; regions "
              + ", ".join(f"{key}:{value.n_windows}w/{value.n_labels}l"
                          f"{'*' if value.adopted else ''}"
                          for key, value in sorted(by_region.items()))
              + f"; {time.time() - mark:.0f}s")

    payload = (QUAL_STATE.parent / "recovered.bin").read_bytes()
    mark = time.time()
    truth_bits, truth_report = _swim_truth.page_component_bits(
        spec, payload, args.q, PAGE)
    truth_report["validation"] = _swim_truth.validate_against_certificates(
        truth_bits, spec, facts.certificates, sample=24)
    truth_report["seconds"] = round(time.time() - mark, 1)
    if not truth_report["validation"].get("exact"):
        raise SystemExit(
            f"the reconstructed printed field does NOT match the "
            f"certificates: {truth_report['validation']} — REFUSING to "
            f"report a mismatch against it")
    print(f"truth field rebuilt in {truth_report['seconds']}s, exact on "
          f"{truth_report['validation']['checked']} certified tiles")

    swim_reference = gt_affine._swim_reference()
    payload_indices = pilots.color_payload_cell_indices(spec.family_seed)
    rows: list[dict] = []
    for target in targets:
        mark = time.time()
        states: dict[str, tuple] = {}
        for capture in facts.captures:
            found = _fit_for(fits, capture.source_sha256, target.address)
            if found is None:
                continue
            states[capture.source_sha256] = (
                found[0], rasters[capture.source_sha256], found[1])
        if not states:
            rows.append({"tile_y": target.tile_y, "tile_x": target.tile_x,
                         "stream": target.stream,
                         "error": "no restricted-region window carries it"})
            continue
        fitted = fit_one_tile(
            states, spec, target.address, truth_bits,
            coarse_max=args.coarse_max, coarse_step=args.coarse_step,
            raster_by_capture=rasters)
        tile_bits = tile_truth_planes(truth_bits, target.address)
        truth = tile_bits.reshape(-1, 3)[payload_indices][:, target.plane]

        def affines(kind: str) -> dict:
            out = {}
            for sha, per_plane in fitted["by_capture"].items():
                out[sha] = tuple(
                    per_plane[PLANE_NAMES[plane]][kind]["affine"]
                    for plane in range(3))
            return out

        def evaluate(by_capture, *, attempt):
            return configuration(states, spec, target, by_capture,
                                 payload_indices, truth, attempt=attempt)

        configurations = {
            "zero": evaluate({sha: (None, None, None) for sha in states},
                             attempt=True),
            "translation": evaluate(affines("translation_fit"),
                                    attempt=True),
            "affine": evaluate(affines("affine_fit"), attempt=True),
        }
        if args.polish_radius > 0.0:
            configurations["polish"] = ber_polish(
                states, spec, target, affines("affine_fit"),
                payload_indices, truth, radius=args.polish_radius,
                step=args.polish_step, evaluate=evaluate)
        structure = None
        entry = configurations["affine"]
        if entry.get("_grid") is not None:
            structure = _affine_fit.structure(
                entry["_grid"], entry["_valid"],
                permutations=args.permutations, seed=args.seed)
        for value in configurations.values():
            value.pop("_grid", None)
            value.pop("_valid", None)

        row = {
            "page": target.page, "tile_y": target.tile_y,
            "tile_x": target.tile_x, "stream": target.stream,
            "plane": target.plane, "band": target.band, "role": target.role,
            "captures": sorted(states),
            "windows_by_capture": {sha: len(value[2])
                                   for sha, value in states.items()},
            "null_proof_zero_affine": fitted["null_proof"],
            "fits": {"by_capture": {
                sha: {plane: serialise_fit(value, spec.cell_dots)
                      for plane, value in per_plane.items()}
                for sha, per_plane in fitted["by_capture"].items()}},
            "configurations": configurations,
            "residual_structure_at_affine": structure,
            "swim": swim_reference.get(
                (target.tile_y, target.tile_x, target.stream)),
            "crosses_gate_at_affine": (
                configurations["affine"]["union_ber"] is not None
                and configurations["affine"]["union_ber"] < GATE_BER),
            "seconds": round(time.time() - mark, 1),
        }
        rows.append(row)
        plane = target.stream
        params = [row["fits"]["by_capture"][sha][plane]["affine_fit"][
            "parameters"] for sha in sorted(states)]
        separations = [row["fits"]["by_capture"][sha][plane][
            "separation_at_affine"] for sha in sorted(states)]
        print(
            f"  {target.tile_y:>2},{target.tile_x:<2} {plane} "
            f"[{target.band[:4]}/{target.role[:6]}] "
            f"tx={_mean(p['translation_dots_xy'][0] for p in params):+.3f} "
            f"ty={_mean(p['translation_dots_xy'][1] for p in params):+.3f} "
            f"sx={_mean(p['scale_x_pct'] for p in params):+.2f}% "
            f"sy={_mean(p['scale_y_pct'] for p in params):+.2f}% "
            f"rot={_mean(p['rotation_deg'] for p in params):+.3f}° "
            f"sh={_mean(p['shear_deg'] for p in params):+.3f}° | "
            f"BER {configurations['zero']['union_ber']:.4f} -> "
            f"{configurations['translation']['union_ber']:.4f} -> "
            f"{configurations['affine']['union_ber']:.4f} | "
            f"d'={_mean(s.get('d_prime') for s in separations):.2f} "
            f"d'p={_mean(s.get('d_prime_partial') for s in separations):.2f} "
            f"| {'CERT' if configurations['affine']['verdict'].get('certified') else 'fail'}"
            + (f" pol {configurations['polish']['union_ber']:.4f}"
               f"{'/CERT' if configurations['polish'].get('verdict', {}).get('certified') else ''}"
               if 'polish' in configurations else "")
            + f" [{row['seconds']:.0f}s]")

    references = []
    for address in _reference_pool(fits, index, count=args.reference_tiles):
        mark = time.time()
        references.append(reference_row(
            fits, rasters, spec, address, truth_bits,
            coarse_max=args.coarse_max, coarse_step=args.coarse_step))
        entry = references[-1]
        y_rows = [value["Y"] for value in entry["by_capture"].values()]
        print(f"  reference {address[1]},{address[2]} Y "
              f"d'={_mean(r['separation_at_affine'].get('d_prime') for r in y_rows):.2f} "
              f"d'p={_mean(r['separation_at_affine'].get('d_prime_partial') for r in y_rows):.2f} "
              f"oracle={_mean(r['oracle_threshold_at_affine']['ber'] for r in y_rows):.4f} "
              f"[{time.time() - mark:.0f}s]")

    for holder in rasters_by_capture.values():
        holder.release()
    del truth_bits

    good = [row for row in rows if "error" not in row]
    tree_after = _swim_inputs.tree_state()
    out = {
        "schema": SCHEMA,
        "state": {"path": str(QUAL_STATE), "sha256": facts.state_sha256,
                  "close": facts.close_status,
                  "payload_sha256": facts.payload_sha256,
                  "certificates": len(facts.certificates)},
        "format": {"ref": FORMAT_REF, "spec_id": spec.spec_id,
                   "tiles_yx": list(spec.layout.tiles_yx),
                   "cell_dots": spec.cell_dots, "dpi": CAPTURE_DPI},
        "lane": {"lane_id": lane.lane_id,
                 "target_coverage_by_capture": list(coverage)},
        "inputs": {
            "scans": {sha: str(path) for sha, path in scans.items()},
            "swim_results": str(gt_affine.SWIM_RESULTS),
            "swim_results_sha256": (
                _swim_inputs.sha256_file(gt_affine.SWIM_RESULTS)
                if gt_affine.SWIM_RESULTS.is_file() else None),
            "recovered_payload": str(QUAL_STATE.parent / "recovered.bin"),
            "recovered_payload_sha256": _swim_inputs.sha256_file(
                QUAL_STATE.parent / "recovered.bin"),
        },
        "model": {
            "parameterisation":
                "(dx, dy) page dots = (tx, ty) + M @ (cx - 31.5, cy - 31.5), "
                "M in dots per cell; the sampling-grid Jacobian in dot "
                "space is J = I + M / cell_dots",
            "objective": "partial NCC: correlation of the sampled channel "
                         "with this plane's GT bits after projecting out "
                         "the other two planes' GT bits and an intercept",
            "search": f"coarse translation grid +/-{args.coarse_max} dots "
                      f"step {args.coarse_step}, then Nelder-Mead on 2 dof "
                      f"(translation ceiling) and on 6 dof (full affine)",
            "applied_to": "the target tile's cells only; the rest of each "
                          "window keeps the delta = 0 sampling",
            "gate_ber_measured": GATE_BER,
        },
        "approximations": [
            "restricted region: the detector is fitted over the windows "
            "within --fit-radius tiles of a target, exactly as the swim "
            "pilot did",
            "frozen detector: ONE fit at delta = 0 scores every geometry; "
            "the A5 context bins are reused unchanged",
            "delta = 0 is the PlaneResidual (dial-OFF) sampling, not the "
            "W6 state's dial-ON field sampling",
            "the fit is SUPERVISED on the printed truth: this is a "
            "ceiling, not a receiver",
        ],
        "residue_by_column": residue,
        "setup": setup,
        "truth_field": truth_report,
        "targets": rows,
        "references": references,
        "synthesis": {
            "dof_ladder": _dof_ladder(good),
            "jacobians": _jacobian_table(good),
            "jacobians_reference": _jacobian_table([
                {"fits": {"by_capture": row["by_capture"]},
                 "stream": "Y", "band": "clear", "role": "reference"}
                for row in references]),
            "translation_agreement": _translation_agreement(good),
            "photometry": _photometry(good),
            "separation": _separation_summary(good, references),
            "separation_by_plane": _separation_by_plane(good),
            "per_target": [
                {"tile_y": row["tile_y"], "tile_x": row["tile_x"],
                 "stream": row["stream"], "band": row["band"],
                 "role": row["role"],
                 "ber_delta0": row["configurations"]["zero"]["union_ber"],
                 "ber_swim_translation_grid": (row.get("swim") or {}).get(
                     "ber_min_translation"),
                 "ber_translation_fit": row["configurations"][
                     "translation"]["union_ber"],
                 "ber_affine_fit": row["configurations"]["affine"][
                     "union_ber"],
                 "ber_polish": row["configurations"].get(
                     "polish", {}).get("union_ber"),
                 "certified_at_polish": row["configurations"].get(
                     "polish", {}).get("verdict", {}).get("certified"),
                 "certified_at_affine": row["configurations"]["affine"][
                     "verdict"].get("certified"),
                 "certified_at_translation": row["configurations"][
                     "translation"]["verdict"].get("certified"),
                 "crosses_gate_at_affine": row["crosses_gate_at_affine"]}
                for row in good],
            "gate": {
                "gate_ber": GATE_BER,
                "targets_crossing_at_affine": [
                    {"tile_y": row["tile_y"], "tile_x": row["tile_x"],
                     "ber": row["configurations"]["affine"]["union_ber"],
                     "certified": row["configurations"]["affine"][
                         "verdict"].get("certified")}
                    for row in good if row["crosses_gate_at_affine"]],
                "certified_at_affine": sum(
                    1 for row in good
                    if row["configurations"]["affine"]["verdict"].get(
                        "certified")),
                "certified_at_translation": sum(
                    1 for row in good
                    if row["configurations"]["translation"]["verdict"].get(
                        "certified")),
                "certified_at_polish": sum(
                    1 for row in good
                    if row["configurations"].get("polish", {}).get(
                        "verdict", {}).get("certified")),
                "certified_at_zero": sum(
                    1 for row in good
                    if row["configurations"]["zero"]["verdict"].get(
                        "certified")),
            },
        },
        "tree_before": tree_before,
        "tree_after": tree_after,
        "tree_moved": _swim_inputs.tree_moved(tree_before, tree_after),
        "wall_seconds": round(time.time() - started, 1),
        "peak_rss_gb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30, 2),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"gt-affine-{args.tag}.json"
    path.write_text(json.dumps(out, indent=1, sort_keys=True, default=str))
    print(f"\nwrote {path}  ({out['wall_seconds']:.0f}s, "
          f"peak RSS {out['peak_rss_gb']} GB)")
    return 0


def _reference_pool(fits, index, *, count: int) -> list:
    """Certified tiles in CLEAR columns that every capture's fit carries."""
    common: set | None = None
    for by_region in fits.values():
        carried: set = set()
        for fit in by_region.values():
            if fit.selected_fit is not None:
                carried |= set(fit.tile_rows)
        common = carried if common is None else (common & carried)
    eligible = sorted(
        address for address in (common or set())
        if address[2] not in DEAD_BANDS
        and len(index.get(address, set())) == 3)
    if not eligible or count <= 0:
        return []
    step = max(1, len(eligible) // count)
    return eligible[::step][:count]


__all__ = ["run"]
