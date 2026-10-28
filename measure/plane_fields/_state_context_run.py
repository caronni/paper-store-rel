"""The E3'/E4 run: setup, the per-capture pass, the union, the synthesis.

Split out of :mod:`state_context` so the measurement seams stay next to
each other and the driving stays here.  The setup is
``_residue_run.run``'s, function for function — same state, same lane,
same seed, same restricted-region fit, same withheld control certificates
— so configuration (a) of E4 is E1's REFIT arm and is asserted against
``p2/e1-refit.json`` rather than assumed to be it.
"""
from __future__ import annotations

import json
import resource
import time

import numpy as np

from . import _context_gt, _state_tables, _swim_inputs, _swim_region, _swim_truth
from ._swim_inputs import DEAD_BANDS, FORMAT_REF, QUAL_STATE
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
from .detector_residue import (
    CONTROL_TILES,
    DEAD_TILES,
    GT_AFFINE,
    geometry_for,
    mismatch,
    read_ceiling,
)

SCHEMA = "plane-fields-state-context-v1"
OUT_DIR = _swim_inputs.MAIN_SCRATCH / "plane-fields" / "p2" / "e3e4"
E1_REFIT = _swim_inputs.MAIN_SCRATCH / "plane-fields" / "p2" / "e1-refit.json"
GATE_BER = 0.0767
ARMS = ("bins", "bins+head")
Y_PLANE = _state_tables.Y_PLANE


def _mean(values):
    rows = [float(v) for v in values
            if v is not None and not isinstance(v, bool) and np.isfinite(v)]
    return float(np.mean(rows)) if rows else None


def _sd(values):
    rows = [float(v) for v in values
            if v is not None and not isinstance(v, bool) and np.isfinite(v)]
    return float(np.std(rows, ddof=1)) if len(rows) > 1 else None


def _select(targets, wanted, role: str):
    by_tile = {(row.tile_y, row.tile_x): row for row in targets
               if row.stream == "Y"}
    missing = [tile for tile in wanted if tile not in by_tile]
    if missing:
        raise SystemExit(
            f"the {role} tiles {missing} are not in this run's selection — "
            f"the seed or the selector moved and this is no longer the same "
            f"experiment as e1-refit.json")
    return [by_tile[tile] for tile in wanted]


# --------------------------------------------------------------------------
# one tile's deduplicated cells, at a stated geometry
# --------------------------------------------------------------------------
def _window_features_at(fit, raster, spec, ordinal, address, affines):
    """One window's features: the fit's own, or re-sampled at ``affines``."""
    if affines is None:
        return fit.features0[ordinal]
    from holo.receive.color_anchoring import _features_with_page_fraction

    from .gt_affine import affine_override

    row = fit.rows[ordinal]
    return _features_with_page_fraction(
        raster, row, fit.residuals, spec, fit.pitch_px, fit.divisor,
        offsets_override=affine_override(
            row, fit.residuals, spec, address, affines, fit.base_is_residual))


def tile_view(fit, spec, raster, address, truth_bits, payload_indices,
              affines=None) -> dict | None:
    """One tile's cells, deduplicated by THE EMISSION'S OWN competition.

    ``payload_model.freeze_page_owners``: ascending
    ``(window heldout logloss, patch id)``, first window observing a cell
    owns it.  Using the same competition here is what makes the
    production column comparable with the block path the certificate gate
    reads — a different tie-break would silently measure a different set
    of pixels.  Returns the production head's Y LLR on those cells
    alongside the raw Y channel and the GT state, which is what E3'
    compares.
    """
    from holo.receive.color_fitting import _window_loss

    ordinals = fit.tile_rows.get(address, ())
    if not ordinals:
        return None
    payload = np.zeros(64 * 64, bool)
    payload[np.asarray(payload_indices, np.int64)] = True
    seen: set[int] = set()
    parts: list[dict] = []

    def competition(ordinal: int) -> tuple[float, int]:
        return (_window_loss(fit.selected_fit.model, fit.rows[ordinal],
                             np.asarray(fit.features0[ordinal], np.float64),
                             fit.selected_fit.heldout_loss),
                int(fit.rows[ordinal].patch.patch_id))

    for ordinal in sorted(ordinals, key=competition):
        row = fit.rows[ordinal]
        cells = np.asarray(row.page_cells_yx, np.int64)
        select = np.flatnonzero((cells[:, 0] // 64 == address[1])
                                & (cells[:, 1] // 64 == address[2]))
        if select.size == 0:
            continue
        keys = ((cells[select, 0] % 64) * 64 + (cells[select, 1] % 64))
        fresh = np.fromiter((int(key) not in seen for key in keys.tolist()),
                            bool, count=keys.size)
        seen.update(int(key) for key in keys[fresh].tolist())
        select = select[fresh]
        if select.size == 0:
            continue
        features = np.asarray(_window_features_at(
            fit, raster, spec, ordinal, address, affines), np.float64)[select]
        known = np.asarray(row.known_component_mask, np.bool_)[select]
        kind = np.asarray(row.furniture_kind, np.int8)[select]
        parts.append({
            "key": keys[fresh],
            "features": features,
            "bins": (None if fit.context_bins is None
                     else np.asarray(fit.context_bins[ordinal], np.int8)[select]),
            "certified": known & (kind < 0)[:, None],
            "known_bits": np.asarray(row.known_component_bits,
                                     np.uint8)[select],
            "emit": np.asarray(fit.emission_by_row[ordinal], bool)[select],
            "page_cells": cells[select],
        })
    if not parts:
        return None
    key = np.concatenate([part["key"] for part in parts])
    features = np.concatenate([part["features"] for part in parts])
    certified = np.concatenate([part["certified"] for part in parts])
    known_bits = np.concatenate([part["known_bits"] for part in parts])
    emit = np.concatenate([part["emit"] for part in parts])
    page_cells = np.concatenate([part["page_cells"] for part in parts])
    bins = (None if any(part["bins"] is None for part in parts)
            else np.concatenate([part["bins"] for part in parts]))
    values, _divisor = fit.selected_fit.evidence_with_divisor(
        features, certified, known_bits, bins)
    return {
        "key": key,
        "payload": payload[key],
        "emit": emit,
        "y_channel": features[:, Y_PLANE],
        "y_llr": np.asarray(values, np.float64)[:, Y_PLANE],
        "gt_state": _state_tables.gt_states_for(truth_bits, page_cells),
        "n": int(key.size),
    }


def _state_pair(view: dict, mask: np.ndarray) -> dict:
    """Production vs the per-stratum oracle on one cell population."""
    states = view["gt_state"][mask]
    production = _state_tables.production_state_rows(
        view["y_llr"][mask] > 0.0, states)
    oracle = _state_tables.oracle_state_rows(view["y_channel"][mask], states)
    rows = []
    for left, right in zip(production, oracle["by_state"], strict=True):
        gap = (None if left["error_rate"] is None or right["error_rate"] is None
               else float(left["error_rate"] - right["error_rate"]))
        rows.append({**left, "oracle_error_rate": right["error_rate"],
                     "oracle_errors": right["errors"], "gap": gap})
    truth = ((states >> Y_PLANE) & 1).astype(bool)
    return {
        "n": int(mask.sum()),
        "production_ber": (None if not mask.any()
                           else float(((view["y_llr"][mask] > 0.0)
                                       != truth).mean())),
        "oracle_ber": oracle["ber"],
        "strata": oracle["strata"],
        "by_state": rows,
    }


# --------------------------------------------------------------------------
# one capture
# --------------------------------------------------------------------------
def capture_pass(capture, spec, scans, facts, lane, targets, measured,
                 references, ceiling, fit_certificates, truth_bits,
                 payload_indices, *, fit_radius: int, log) -> dict:
    """Everything one capture contributes; its raster is then released.

    ONE capture is resident at a time (E1's rule — a second receiver runs
    on this machine).  What survives the release is a few tens of
    kilobytes of evidence blocks per (tile, configuration, arm).
    """
    from holo.receive.payload_model import EvidenceSource

    sha = capture.source_sha256
    started = time.time()
    holder = LaneRasters(spec, capture, scans[sha])
    try:
        raster = holder.for_lane(lane)
        placements, _poses = build_placements(facts, spec, capture, lane,
                                              raster)
        grouped = restricted_placements(placements, targets, fit_radius)
        del placements
        source = EvidenceSource(sha, lane.lane_id)
        keep = frozenset(row.address for row in targets)
        fits: dict[int, object] = {}
        for region_index, patches in sorted(grouped.items()):
            region_id = (f"{sha}/{lane.lane_id}/region-{region_index}/"
                         f"page-{PAGE}")
            fits[region_index] = _swim_region.fit_region(
                spec, raster, source, patches, fit_certificates, PAGE,
                region_id, keep_features_for=keep, keep_all_features=True)
        log(f"  {sha[:12]} regions "
            + ", ".join(f"{key}:{value.n_windows}w/{value.n_labels}l"
                        f"{'*A1' if value.adopted else ' A0'}"
                        f"{'+A5' if value.context_bins is not None else ''}"
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

        out: dict = {"capture": sha, "region": {}, "e3prime": {}, "e4": {},
                     "references": {}}
        for region_index, fit in sorted(fits.items()):
            if fit.selected_fit is None:
                out["region"][str(region_index)] = {"refusal": fit.refusal}
                continue
            mark = time.time()
            out["region"][str(region_index)] = {
                "windows": fit.n_windows, "labels": fit.n_labels,
                "adopted_A1": bool(fit.adopted),
                "heldout_logloss": float(fit.heldout_loss),
                "context_adopted": bool(fit.context_bins is not None),
                "context_reason": str(fit.selected_fit.context_reason),
                "qda": _state_tables.qda_state_table(fit, spec),
                "window_photometry": _state_tables.window_photometry_rows(
                    fit, DEAD_BANDS),
                "known_bit_agreement": _context_gt.known_bit_agreement(
                    fit, truth_bits),
                "seconds": round(time.time() - mark, 1)}
            log(f"    region {region_index}: QDA/A3 tables in "
                f"{time.time() - mark:.0f}s; A5 "
                f"{out['region'][str(region_index)]['context_reason'] or 'off'}")

        # ---- the eight measured tiles, at the E1 REFIT footing ----------
        for target in measured:
            key = f"{target.tile_y},{target.tile_x}/{target.stream}"
            found = carrier(target.address)
            if found is None:
                out["e3prime"][key] = {"error": "no region window carries it"}
                continue
            _fit, _ordinals, region_index = found
            mark = time.time()
            ceiling_row = ceiling["targets"][
                (target.tile_y, target.tile_x, target.stream)]
            geometry = geometry_for(ceiling_row, target.plane, polish=True)
            affines = geometry["by_capture"][sha]
            from .gt_affine import affine_override_builder

            region_id = (f"{sha}/{lane.lane_id}/region-{region_index}/"
                         f"page-{PAGE}")
            refit = _swim_region.fit_region(
                spec, raster, source, grouped.get(region_index, ()),
                fit_certificates, PAGE, region_id,
                keep_features_for=frozenset({target.address}),
                keep_all_features=True,
                refit_overrides={target.address: affine_override_builder(
                    target.address, affines)})
            if refit.selected_fit is None:
                out["e3prime"][key] = {"error": refit.refusal}
                continue
            fitted_seconds = time.time() - mark
            tile_bits = truth_bits[target.tile_y * 64:(target.tile_y + 1) * 64,
                                   target.tile_x * 64:(target.tile_x + 1) * 64,
                                   :]
            truth = tile_bits.reshape(-1, 3)[payload_indices][:, target.plane]
            out["e4"][key] = _e4_for_tile(
                refit, spec, target, truth_bits, truth, payload_indices, log)
            view = tile_view(refit, spec, raster, target.address, truth_bits,
                             payload_indices)
            population = view["payload"] & view["emit"]
            out["e3prime"][key] = {
                "arm": "A1" if refit.adopted else "A0",
                "heldout_logloss": float(refit.heldout_loss),
                "context_adopted": bool(refit.context_bins is not None),
                "band": target.band, "role": target.role,
                "n_cells": int(view["n"]),
                "n_payload_emitted": int(population.sum()),
                "emitted": _state_pair(view, population),
                "refit_probe": refit.refit_probe,
                "polish_extra_dots_xy": geometry["polish_extra_dots_xy"],
                # The same capture's error through the BLOCK path (the
                # ownership competition, float32 evidence, the certificate
                # gate's own input): a cross-check on the direct-head
                # column above, which is what the per-state table splits.
                "block_path_ber": ((out["e4"][key].get("configurations")
                                    or {}).get("a", {}).get("arms", {})
                                   .get("bins", {}).get("ber")),
                "seconds": round(fitted_seconds, 1)}
            log(f"    E3' {key:<12} {target.band[:4]}/{target.role[:6]} "
                f"prod {out['e3prime'][key]['emitted']['production_ber']:.4f} "
                f"oracle {out['e3prime'][key]['emitted']['oracle_ber']:.4f} "
                f"block {out['e3prime'][key]['block_path_ber']} "
                f"[{fitted_seconds:.0f}s]")
            del refit

        # ---- the certified clean-column references (E3' only) ----------
        for address in references:
            found = carrier(address)
            reference = ceiling["references"].get((address[1], address[2]))
            if found is None or reference is None:
                continue
            fit, _ordinals, _region = found
            affines = geometry_for(reference, Y_PLANE, polish=False)[
                "by_capture"][sha]
            view = tile_view(fit, spec, raster, address, truth_bits,
                             payload_indices, affines=affines)
            if view is None:
                continue
            out["references"][f"{address[1]},{address[2]}/Y"] = {
                "n_cells": int(view["n"]),
                "n_payload": int(view["payload"].sum()),
                "emitted_fraction": float(view["emit"].mean()),
                "payload": _state_pair(view, view["payload"])}
        out["seconds"] = round(time.time() - started, 1)
        return out
    finally:
        holder.release()


def _e4_for_tile(refit, spec, target, truth_bits, truth, payload_indices,
                 log) -> dict:
    """E4's four configurations x two arms on ONE tile of ONE capture."""
    address = target.address
    if refit.context_bins is None:
        return {"error": "A5 was not adopted on this region — no bins exist"}
    mark = time.time()
    evidence = _context_gt.region_evidence(refit)
    rebuilt = _context_gt.build_bins(refit, truth_bits, (), evidence)
    identical = all(np.array_equal(left, right) for left, right in
                    zip(refit.context_bins, rebuilt, strict=True))
    out: dict = {
        "null_proof_bins_bit_identical": bool(identical),
        "ink_disagreement": _context_gt.ink_disagreement(
            refit, truth_bits, address, evidence),
        "configurations": {},
    }
    if not identical:
        raise RuntimeError(
            f"{address}: rebuilding A5's bins through the instrument did not "
            f"reproduce the ladder's own — the override seam is not the "
            f"ladder's ink map and E4 would measure the instrument")
    for name, planes in _context_gt.CONFIGS.items():
        bins = (refit.context_bins if not planes
                else _context_gt.build_bins(refit, truth_bits, planes,
                                            evidence))
        head_fit, head_record = _context_gt.refit_context_head(refit, bins)
        row = {
            "gt_planes": [_context_gt.PLANE_NAMES[plane] for plane in planes],
            "description": _context_gt.CONFIG_NAMES[name],
            "bin_change": _context_gt.bin_change(
                refit.context_bins, bins, refit, address),
            "head_refit": head_record,
            "arms": {},
        }
        for arm, detector_fit in (("bins", None), ("bins+head", head_fit)):
            candidate = _context_gt.with_context(refit, bins, detector_fit)
            blocks = _context_gt.tile_blocks(candidate, spec, address)
            row["arms"][arm] = {
                **mismatch(blocks, spec, address, target.plane,
                           payload_indices, truth),
                "_blocks": blocks}
        out["configurations"][name] = row
    out["seconds"] = round(time.time() - mark, 1)
    for arm in ARMS:
        log(f"    E4 {target.tile_y},{target.tile_x}".ljust(17)
            + f" {arm:<9} " + " ".join(
                f"{name}:{out['configurations'][name]['arms'][arm]['ber']:.4f}"
                for name in _context_gt.CONFIGS)
            + ("  head " + ",".join(
                f"{name}:{out['configurations'][name]['head_refit']['reason']}"
                for name in _context_gt.CONFIGS)
               if arm == "bins+head" else "")
            + (f" [{out['seconds']:.0f}s]" if arm == ARMS[-1] else ""))
    return out


# --------------------------------------------------------------------------
# the union
# --------------------------------------------------------------------------
def union_rows(measured, per_capture, spec, truth_bits, payload_indices
               ) -> list[dict]:
    """Union each tile's blocks across captures, per configuration and arm."""
    from .swim_pilot import union_verdict

    rows: list[dict] = []
    for target in measured:
        key = f"{target.tile_y},{target.tile_x}/{target.stream}"
        entries = {sha: capture["e4"].get(key)
                   for sha, capture in per_capture.items()}
        entries = {sha: row for sha, row in entries.items()
                   if row and "error" not in row}
        if not entries:
            rows.append({"tile_y": target.tile_y, "tile_x": target.tile_x,
                         "band": target.band, "role": target.role,
                         "error": "not carried"})
            continue
        tile_bits = truth_bits[target.tile_y * 64:(target.tile_y + 1) * 64,
                               target.tile_x * 64:(target.tile_x + 1) * 64, :]
        truth = tile_bits.reshape(-1, 3)[payload_indices][:, target.plane]
        row = {"tile_y": target.tile_y, "tile_x": target.tile_x,
               "band": target.band, "role": target.role,
               "captures": sorted(entries), "configurations": {}}
        for name in _context_gt.CONFIGS:
            entry = {"description": _context_gt.CONFIG_NAMES[name], "arms": {}}
            for arm in ARMS:
                per = [value["configurations"][name]["arms"][arm]
                       for value in entries.values()]
                blocks = [tuple(value["_blocks"]) for value in per]
                union = tuple(block for group in blocks for block in group)
                # The receiver mints a UNION attempt over two or more
                # blocks and refuses below that; a one-capture smoke run
                # is short of the floor and says so rather than crashing.
                verdict = (union_verdict(blocks, spec, target)
                           if len(union) >= 2 else
                           {"certified": False,
                            "reason": "fewer than two blocks in the union"})
                entry["arms"][arm] = {
                    **mismatch(union, spec, target.address, target.plane,
                               payload_indices, truth),
                    "verdict": verdict,
                    "per_capture": {
                        sha: {k: v for k, v in
                              value["configurations"][name]["arms"][arm].items()
                              if not k.startswith("_")}
                        for sha, value in entries.items()},
                }
            row["configurations"][name] = entry
        rows.append(row)
    return rows


def _e4_summary(rows: list[dict]) -> dict:
    """The dead-vs-control gap under each configuration — E4's verdict."""
    good = [row for row in rows if "error" not in row]
    out: dict = {"by_configuration": {}, "n_tiles": len(good)}
    for name in _context_gt.CONFIGS:
        entry: dict = {"description": _context_gt.CONFIG_NAMES[name]}
        for arm in ARMS:
            groups: dict[str, list[float]] = {"dead": [], "control": []}
            certified = {"dead": 0, "control": 0}
            for row in good:
                group = "dead" if row["role"] == "target" else "control"
                value = row["configurations"][name]["arms"][arm]["ber"]
                if value is not None:
                    groups[group].append(float(value))
                if row["configurations"][name]["arms"][arm][
                        "verdict"].get("certified"):
                    certified[group] += 1
            entry[arm] = {
                "dead_mean": _mean(groups["dead"]),
                "dead_sd": _sd(groups["dead"]),
                "control_mean": _mean(groups["control"]),
                "control_sd": _sd(groups["control"]),
                "gap_pp": (
                    None if not groups["dead"] or not groups["control"]
                    else float(100.0 * (np.mean(groups["dead"])
                                        - np.mean(groups["control"])))),
                "certified_dead": certified["dead"],
                "certified_control": certified["control"],
                "n_dead": len(groups["dead"]),
                "n_control": len(groups["control"]),
            }
        out["by_configuration"][name] = entry
    baseline = out["by_configuration"]["a"]
    for name, entry in out["by_configuration"].items():
        for arm in ARMS:
            base = baseline[arm]["gap_pp"]
            here = entry[arm]["gap_pp"]
            entry[arm]["gap_closed_pp"] = (
                None if base is None or here is None else float(base - here))
            entry[arm]["gap_closed_fraction"] = (
                None if not base or here is None else float((base - here) / base))
            for group in ("dead", "control"):
                left = baseline[arm][f"{group}_mean"]
                right = entry[arm][f"{group}_mean"]
                entry[arm][f"{group}_delta_pp"] = (
                    None if left is None or right is None
                    else float(100.0 * (right - left)))
    return out


def _e3prime_summary(per_capture, measured, references) -> dict:
    """Pool the per-state tables over (tile, capture) rows, by group."""
    groups = {"dead": [], "control": [], "reference": []}
    for capture in per_capture.values():
        for target in measured:
            key = f"{target.tile_y},{target.tile_x}/{target.stream}"
            entry = capture["e3prime"].get(key)
            if not entry or "error" in entry:
                continue
            group = "dead" if target.role == "target" else "control"
            groups[group].append({"tile": (target.tile_y, target.tile_x),
                                  **entry["emitted"]})
        for name, entry in capture["references"].items():
            groups["reference"].append({"tile": name, **entry["payload"]})
    out: dict = {"by_group": {}}
    for group, entries in groups.items():
        if not entries:
            continue
        by_state = []
        for state in range(_state_tables.N_STATES):
            rows = [entry["by_state"][state] for entry in entries]
            counts = [row["n"] for row in rows]
            by_state.append({
                "state": state, "name": _state_tables.STATE_LABELS[state],
                "n_cells_total": int(sum(counts)),
                "n_per_row_mean": _mean(counts),
                "production_error": _mean(row["error_rate"] for row in rows),
                "production_error_sd": _sd(row["error_rate"] for row in rows),
                "oracle_error": _mean(row["oracle_error_rate"] for row in rows),
                "gap": _mean(row["gap"] for row in rows),
                "gap_sd": _sd(row["gap"] for row in rows),
                "error_share": (
                    None if not sum(
                        row["errors"] for row in rows) else float(
                            sum(row["errors"] for row in rows)
                            / sum(sum(other["errors"] for other in
                                      entry["by_state"]) for entry in entries))),
            })
        out["by_group"][group] = {
            "n_rows": len(entries),
            "n_tiles": len({entry["tile"] for entry in entries}),
            "production_ber": _mean(entry["production_ber"] for entry in entries),
            "oracle_ber": _mean(entry["oracle_ber"] for entry in entries),
            "gap_pp": (
                None if _mean(entry["production_ber"] for entry in entries) is None
                else float(100.0 * (
                    _mean(entry["production_ber"] for entry in entries)
                    - _mean(entry["oracle_ber"] for entry in entries)))),
            "by_state": by_state,
        }
    out["qda_by_capture"] = {
        sha: {index: {"n_train": [row["n_train"] for row in
                                  region["qda"]["states"]],
                      "a_k": [row["a_k"] for row in region["qda"]["states"]]}
              for index, region in capture["region"].items()
              if "qda" in region}
        for sha, capture in per_capture.items()}
    out["photometry_by_capture"] = {
        sha: {index: region["window_photometry"]["by_band"]
              for index, region in capture["region"].items()
              if "window_photometry" in region}
        for sha, capture in per_capture.items()}
    del references
    return out


def _reproduction_check(rows: list[dict]) -> dict:
    """Configuration (a) IS E1's refit arm — assert it, do not assume it."""
    if not E1_REFIT.is_file():
        return {"checked": 0, "reason": "e1-refit.json is not on disk"}
    document = json.loads(E1_REFIT.read_text())
    reference = {(row["tile_y"], row["tile_x"]): row
                 for row in document["e1"]["rows"] if "refit" in row
                 and "union_ber" in row.get("refit", {})}
    checked = 0
    worst = 0.0
    per_tile = {}
    for row in rows:
        if "error" in row:
            continue
        found = reference.get((row["tile_y"], row["tile_x"]))
        here = row["configurations"]["a"]["arms"]["bins"]["ber"]
        if found is None or here is None:
            continue
        gap = abs(float(found["refit"]["union_ber"]) - float(here))
        per_tile[f"{row['tile_y']},{row['tile_x']}"] = {
            "e1_refit_union_ber": float(found["refit"]["union_ber"]),
            "e4_configuration_a_ber": float(here), "abs_gap": gap}
        worst = max(worst, gap)
        checked += 1
    return {"checked": checked, "max_abs_gap": worst,
            "exact": bool(checked > 0 and worst == 0.0), "per_tile": per_tile}


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def run(args) -> int:
    from holo.format import pilots
    from holo.format.resolve import resolve_format_ref
    from holo.receive import _parallel

    from ._state_context_report import write_outputs

    started = time.time()
    _parallel.set_worker_count(max(1, int(args.workers)))
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
    withheld = frozenset(
        (*row.address, row.stream) for row in targets
        if row.role.startswith("reproduction-control"))
    fit_certificates = tuple(
        row for row in facts.certificates
        if (int(row.page), *(int(v) for v in row.tile_yx), row.stream_id)
        not in withheld)
    measured = (_select(targets, DEAD_TILES, "dead-band")
                + _select(targets, CONTROL_TILES, "control"))
    if args.limit:
        measured = measured[:args.limit]

    ceiling = read_ceiling(GT_AFFINE)
    if ceiling["state_sha256"] != facts.state_sha256:
        raise SystemExit(
            f"gt-affine-final2 was run against state "
            f"{ceiling['state_sha256'][:12]} and this is "
            f"{facts.state_sha256[:12]}")
    if ceiling["lane"] != lane.lane_id:
        raise SystemExit(f"lane moved: {ceiling['lane']} -> {lane.lane_id}")
    references = [(0, tile_y, tile_x)
                  for tile_y, tile_x in sorted(ceiling["references"])][
                      :args.reference_tiles]

    print(f"state {facts.state_sha256[:12]} {facts.close_status} certs "
          f"{len(facts.certificates)} lane {lane.lane_id} coverage {coverage}")
    print("measured: " + ", ".join(
        f"{row.tile_y},{row.tile_x}[{row.band[:1]}"
        f"{'C' if row.role != 'target' else ''}]" for row in measured))
    print("references: " + ", ".join(f"{ty},{tx}" for _pg, ty, tx in references))

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
            f"certificates: {truth_report['validation']}")
    print(f"truth field rebuilt in {truth_report['seconds']}s, exact on "
          f"{truth_report['validation']['checked']} certified tiles")
    payload_indices = pilots.color_payload_cell_indices(spec.family_seed)

    if args.from_raw:
        # THE MEASUREMENT IS ON DISK BEFORE ANY SUMMARY RUNS (the P2 rule).
        raw = json.loads((OUT_DIR / "raw.json").read_text())
        del truth_bits
        print(f"re-entered from {OUT_DIR / 'raw.json'}: "
              f"{len(raw['per_capture'])} captures, {len(raw['e4'])} E4 rows")
        return write_outputs(
            args, facts, spec, lane, coverage, scans, ceiling, measured,
            references, residue, raw["truth_field"], raw["per_capture"],
            raw["e4"], tree_before, started,
            summaries=(_e3prime_summary(raw["per_capture"], measured,
                                        references),
                       _e4_summary(raw["e4"]),
                       _reproduction_check(raw["e4"])))

    per_capture: dict[str, dict] = {}
    for capture in facts.captures[:args.captures]:
        per_capture[capture.source_sha256] = capture_pass(
            capture, spec, scans, facts, lane, targets, measured, references,
            ceiling, fit_certificates, truth_bits, payload_indices,
            fit_radius=args.fit_radius, log=print)
        print(f"  {capture.source_sha256[:12]} done in "
              f"{per_capture[capture.source_sha256]['seconds']:.0f}s; "
              f"RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.1f} GB")

    e4 = union_rows(measured, per_capture, spec, truth_bits, payload_indices)
    del truth_bits
    for capture in per_capture.values():
        for entry in capture["e4"].values():
            for row in (entry.get("configurations") or {}).values():
                for arm in row["arms"].values():
                    arm.pop("_blocks", None)
    for row in e4:
        for entry in (row.get("configurations") or {}).values():
            for arm in entry["arms"].values():
                arm.pop("_blocks", None)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "raw.json").write_text(json.dumps(
        {"schema": SCHEMA + "-raw", "per_capture": per_capture, "e4": e4,
         "truth_field": truth_report}, indent=1, sort_keys=True, default=str))
    print(f"raw rows written to {OUT_DIR / 'raw.json'}")

    return write_outputs(
        args, facts, spec, lane, coverage, scans, ceiling, measured,
        references, residue, truth_report, per_capture, e4, tree_before,
        started, summaries=(_e3prime_summary(per_capture, measured, references),
                            _e4_summary(e4), _reproduction_check(e4)))


__all__ = ["ARMS", "GATE_BER", "OUT_DIR", "SCHEMA", "capture_pass", "run",
           "tile_view", "union_rows"]
