"""The P2 run: setup, the per-capture pass, the union, the synthesis.

Split out of :mod:`detector_residue` so the measurement seams (the two
E1 arms, the two stratifications) stay readable next to each other and
the driving stays here.  The setup is ``_gt_affine_run.run``'s, function
for function — same state, same lane, same seed, same restricted-region
fit, same withheld control certificates — so E1's FROZEN arm is directly
comparable with ``gt-affine-final2.json`` and the comparison is reported
as a reproduction check rather than assumed.
"""
from __future__ import annotations

import json
import resource
import time

import numpy as np

from . import _residue_figures, _residue_strata, _swim_inputs, _swim_truth
from ._swim_inputs import CAPTURE_DPI, DEAD_BANDS, FORMAT_REF, QUAL_STATE
from ._swim_setup import (
    certified_index,
    choose_lane,
    residue_by_column,
    select_controls,
    select_targets,
)
from .detector_residue import (
    CONTROL_TILES,
    DEAD_TILES,
    GT_AFFINE,
    OUT_DIR,
    SCHEMA,
    capture_pass,
    mismatch,
    read_ceiling,
)

GATE_BER = 0.0767


def _numbers(values) -> list[float]:
    """Only the real numbers in a heterogeneous column.

    Contrast rows carry strings (``ber_worst_inked``) and lists
    (``inked_strata_present``) beside their numbers; a mean over the
    whole row used to raise 40 minutes into a run.  Skipping the
    non-numeric entries is the honest reduction — every summary states
    its own ``n``.
    """
    rows: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if np.isfinite(value):
            rows.append(float(value))
    return rows


def _mean(values):
    rows = _numbers(values)
    return float(np.mean(rows)) if rows else None


def _sd(values):
    rows = _numbers(values)
    return float(np.std(rows, ddof=1)) if len(rows) > 1 else None


def _select(targets, wanted, role: str):
    """The named tiles, ASSERTED present rather than substituted for."""
    by_tile = {(row.tile_y, row.tile_x): row for row in targets
               if row.stream == "Y"}
    missing = [tile for tile in wanted if tile not in by_tile]
    if missing:
        raise SystemExit(
            f"the {role} tiles {missing} are not in this run's selection — "
            f"the seed or the selector moved and this is no longer the same "
            f"experiment as gt-affine-final2.json")
    return [by_tile[tile] for tile in wanted]


# --------------------------------------------------------------------------
# synthesis
# --------------------------------------------------------------------------
def _e1_rows(measured, per_capture, spec, ceiling, truth_bits,
             payload_indices) -> list[dict]:
    """Union the three captures' blocks and score both E1 arms."""
    from .swim_pilot import union_verdict

    rows: list[dict] = []
    for target in measured:
        key = f"{target.tile_y},{target.tile_x}/{target.stream}"
        entries = {sha: capture["e1"].get(key)
                   for sha, capture in per_capture.items()}
        entries = {sha: row for sha, row in entries.items()
                   if row and "error" not in row}
        if not entries:
            rows.append({"tile_y": target.tile_y, "tile_x": target.tile_x,
                         "stream": target.stream, "error": "not carried"})
            continue
        tile_bits = truth_bits[target.tile_y * 64:(target.tile_y + 1) * 64,
                               target.tile_x * 64:(target.tile_x + 1) * 64, :]
        truth = tile_bits.reshape(-1, 3)[payload_indices][:, target.plane]
        row = {
            "tile_y": target.tile_y, "tile_x": target.tile_x,
            "stream": target.stream, "plane": target.plane,
            "band": target.band, "role": target.role,
            "captures": sorted(entries),
            "geometry": next(iter(entries.values()))["geometry"],
        }
        for arm, blocks_key in (("frozen", "_frozen_blocks"),
                                ("refit", "_refit_blocks")):
            per = {sha: value.get(arm) for sha, value in entries.items()}
            if any(value is None or "ber" not in value
                   for value in per.values()):
                row[arm] = {"error": "arm missing on at least one capture",
                            "per_capture": per}
                continue
            blocks = [value[blocks_key] for value in entries.values()
                      if blocks_key in value]
            union = tuple(item for group in blocks for item in group)
            combined = mismatch(union, spec, target.address, target.plane,
                                payload_indices, truth)
            # A UNION attempt names at least two blocks by construction
            # (holo.receive.tiles.attempt_identity); a one-capture run is
            # a smoke test, not a verdict.
            verdict = (union_verdict(blocks, spec, target) if len(union) > 1
                       else {"certified": False,
                             "reason": f"{len(union)} block(s): a union "
                                       f"attempt names at least two"})
            row[arm] = {
                "per_capture": {
                    sha: {key_: value_ for key_, value_ in entry.items()
                          if key_ != "refit_probe"}
                    for sha, entry in per.items()},
                "refit_probe": {sha: entry.get("refit_probe")
                                for sha, entry in per.items()},
                "arm_by_capture": {sha: entry.get("arm")
                                   for sha, entry in per.items()},
                "heldout_logloss": {sha: entry.get("heldout_logloss")
                                    for sha, entry in per.items()},
                "union_ber": combined.get("ber"),
                "union_observed": combined.get("observed"),
                "union_errors": combined.get("errors"),
                "union_mean_abs_llr": combined.get("mean_abs_llr"),
                "certified": bool(verdict.get("certified")),
                "certificate_id": verdict.get("certificate_id"),
                "verdict": verdict,
                "crosses_gate": (combined.get("ber") is not None
                                 and combined["ber"] < GATE_BER),
            }
            if arm == "frozen":
                row[arm].pop("refit_probe")
        reference = ceiling["targets"].get(
            (target.tile_y, target.tile_x, target.stream)) or {}
        polish = (reference.get("configurations", {}) or {}).get("polish", {})
        row["gt_affine_polish"] = {
            "union_ber": polish.get("union_ber"),
            "certified": (polish.get("verdict") or {}).get("certified"),
            "extra_translation_dots_xy": polish.get(
                "extra_translation_dots_xy"),
        }
        if row.get("frozen", {}).get("union_ber") is not None and polish.get(
                "union_ber") is not None:
            row["reproduction_gap_vs_gt_affine"] = float(
                row["frozen"]["union_ber"] - polish["union_ber"])
        if (row.get("refit", {}).get("union_ber") is not None
                and row.get("frozen", {}).get("union_ber") is not None):
            row["refit_minus_frozen_ber"] = float(
                row["refit"]["union_ber"] - row["frozen"]["union_ber"])
        rows.append(row)
    return rows


def _e1_summary(rows: list[dict]) -> dict:
    def group(subset: list[dict]) -> dict:
        frozen = [row.get("frozen", {}).get("union_ber") for row in subset]
        refit = [row.get("refit", {}).get("union_ber") for row in subset]
        pairs = [(a, b) for a, b in zip(frozen, refit)
                 if a is not None and b is not None]
        return {
            "n_tiles": len(subset),
            "union_ber_frozen_mean": _mean(frozen),
            "union_ber_frozen_sd": _sd(frozen),
            "union_ber_refit_mean": _mean(refit),
            "union_ber_refit_sd": _sd(refit),
            "refit_minus_frozen_mean_pp": (
                None if not pairs else
                float(100.0 * np.mean([b - a for a, b in pairs]))),
            "refit_improved_tiles": sum(1 for a, b in pairs if b < a),
            "refit_worsened_tiles": sum(1 for a, b in pairs if b > a),
            "certified_frozen": sum(
                1 for row in subset if row.get("frozen", {}).get("certified")),
            "certified_refit": sum(
                1 for row in subset if row.get("refit", {}).get("certified")),
            "reproduction_gap_max_abs": max(
                (abs(row["reproduction_gap_vs_gt_affine"]) for row in subset
                 if "reproduction_gap_vs_gt_affine" in row), default=None),
        }
    good = [row for row in rows if "error" not in row]
    return {
        "all_measured": group(good),
        "dead_band": group([row for row in good if row["band"] == "dead"
                            and row["role"] == "target"]),
        "reproduction_controls": group(
            [row for row in good if row["role"] != "target"]),
        "gate_ber_measured": GATE_BER,
    }


def _group_of(key: str, measured) -> str:
    if key.startswith("ref "):
        return "certified_reference"
    by_key = {f"{row.tile_y},{row.tile_x}/{row.stream}": row
              for row in measured}
    row = by_key.get(key)
    if row is None:
        return "other"
    return ("dead_band" if row.band == "dead" and row.role == "target"
            else "reproduction_control" if row.role != "target"
            else "clear_band")


def _pool(per_capture, section: str, measured, path: tuple) -> dict:
    """Pool one stratum table over (tile, capture) rows, by group."""
    buckets: dict[str, list[dict]] = {}
    for sha, capture in per_capture.items():
        for key, entry in capture[section].items():
            row = entry
            for step in path:
                row = row.get(step, {}) if isinstance(row, dict) else {}
            if not row:
                continue
            buckets.setdefault(_group_of(key, measured), []).append(
                {"strata": row, "tile": key, "capture": sha})
    return {name: _residue_strata.pool_strata(rows)
            for name, rows in sorted(buckets.items())}


def _e2_summary(per_capture, measured) -> dict:
    out = {
        "downstream": _pool(per_capture, "e2", measured,
                            ("downstream", "strata")),
        "upstream": _pool(per_capture, "e2", measured,
                          ("upstream", "strata")),
        "same_cell": _pool(per_capture, "e2", measured,
                           ("same_cell", "strata")),
    }
    keys = ("ber_gap_inked_minus_none", "ber_global_gap_inked_minus_none",
            "lift_inked_mean", "lift_none", "recoverable_pp_inked_mean")
    gaps: dict[str, dict] = {}
    for capture in per_capture.values():
        for key, entry in capture["e2"].items():
            group = _group_of(key, measured)
            row = gaps.setdefault(group, {"tiles": set(), "difference": []})
            row["tiles"].add(key)
            for label in ("downstream", "upstream", "same_cell"):
                contrast = entry.get(label, {}).get("contrast") or {}
                for name in keys:
                    row.setdefault(f"{label}.{name}", []).append(
                        contrast.get(name))
            row["difference"].append(entry.get(
                "downstream_minus_upstream_gap"))

    def pp(values):
        return _mean(100.0 * v for v in values if v is not None)

    out["ink_gap_pp"] = {
        group: {
            **{f"{label}_{name}": (
                pp(row[f"{label}.{name}"]) if name.startswith("ber")
                else _mean(row[f"{label}.{name}"]) if name.startswith("lift")
                else _mean(v for v in row[f"{label}.{name}"]
                           if v is not None))
               for label in ("downstream", "upstream", "same_cell")
               for name in keys},
            "downstream_mean_pp": pp(
                row["downstream.ber_gap_inked_minus_none"]),
            "downstream_sd_pp": _sd(
                100.0 * v for v in row["downstream.ber_gap_inked_minus_none"]
                if v is not None),
            "upstream_mean_pp": pp(row["upstream.ber_gap_inked_minus_none"]),
            "same_cell_mean_pp": pp(
                row["same_cell.ber_gap_inked_minus_none"]),
            "downstream_minus_upstream_mean_pp": pp(row["difference"]),
            "downstream_minus_upstream_sd_pp": _sd(
                100.0 * v for v in row["difference"] if v is not None),
            "n_rows": len([v for v in row["downstream.lift_inked_mean"]
                           if v is not None]),
            "n_tiles": len(row["tiles"]),
        }
        for group, row in sorted(gaps.items())}
    return out


def _e3_summary(per_capture, measured) -> dict:
    out = {"strata": _pool(per_capture, "e3", measured, ("strata",))}
    ratios: dict[str, dict] = {}
    for capture in per_capture.values():
        for key, entry in capture["e3"].items():
            group = _group_of(key, measured)
            row = ratios.setdefault(group, {"tiles": set()})
            row["tiles"].add(key)
            for name, value in (entry.get("contrast") or {}).items():
                # ``ber_worst_inked`` is a stratum NAME and
                # ``inked_strata_present`` a list; only the numbers get
                # averaged, and _mean skips the rest anyway.
                if isinstance(value, (int, float)) or value is None:
                    row.setdefault(name, []).append(value)
    out["ratios"] = {
        group: {
            **{name: _mean(values) for name, values in sorted(row.items())
               if name != "tiles"},
            "n_rows": len(row.get("d_prime_ratio_M_over_none", [])),
            "n_tiles": len(row["tiles"]),
        }
        for group, row in sorted(ratios.items())}
    return out


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------
def run(args) -> int:
    from holo.format import pilots
    from holo.format.resolve import resolve_format_ref
    from holo.receive import _parallel

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
    for row in _select(targets, DEAD_TILES, "dead-band"):
        if row.band != "dead" or row.role != "target":
            raise SystemExit(
                f"tile {row.tile_y},{row.tile_x} is {row.band}/{row.role}, "
                f"not a dead-band target")
    for row in _select(targets, CONTROL_TILES, "control"):
        if row.role == "target":
            raise SystemExit(
                f"tile {row.tile_y},{row.tile_x} is not a reproduction "
                f"control in this selection")
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
                  for tile_y, tile_x in sorted(ceiling["references"])]

    print(f"state {facts.state_sha256[:12]} {facts.close_status} certs "
          f"{len(facts.certificates)} lane {lane.lane_id} coverage {coverage}")
    print("measured: " + ", ".join(
        f"{row.tile_y},{row.tile_x}[{row.band[:1]}"
        f"{'C' if row.role != 'target' else ''}]" for row in measured))
    print("references: " + ", ".join(
        f"{ty},{tx}" for _pg, ty, tx in references))

    payload = (QUAL_STATE.parent / "recovered.bin").read_bytes()
    mark = time.time()
    truth_bits, truth_report = _swim_truth.page_component_bits(
        spec, payload, args.q, 0)
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
        raw = json.loads((OUT_DIR / "raw.json").read_text())
        per_capture, e1 = raw["per_capture"], raw["e1"]
        del truth_bits
        print(f"re-entered from {OUT_DIR / 'raw.json'}: "
              f"{len(per_capture)} captures, {len(e1)} E1 rows")
        return _summarise_and_write(
            args, facts, spec, lane, coverage, scans, ceiling, measured,
            references, residue, truth_report, per_capture, e1, tree_before,
            started)

    per_capture = {}
    for capture in facts.captures[:args.captures]:
        per_capture[capture.source_sha256] = capture_pass(
            capture, spec, scans, facts, lane, targets, measured, references,
            ceiling, fit_certificates, truth_bits, payload_indices,
            fit_radius=args.fit_radius, do_refit=not args.no_refit,
            log=print)
        print(f"  {capture.source_sha256[:12]} done in "
              f"{per_capture[capture.source_sha256]['seconds']:.0f}s; "
              f"RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.1f} GB")

    e1 = _e1_rows(measured, per_capture, spec, ceiling, truth_bits,
                  payload_indices)
    del truth_bits
    for capture in per_capture.values():
        for entry in capture["e1"].values():
            entry.pop("_frozen_blocks", None)
            entry.pop("_refit_blocks", None)
    for row in e1:
        for arm in ("frozen", "refit"):
            if arm in row and "per_capture" in row[arm]:
                for entry in row[arm]["per_capture"].values():
                    entry.pop("_frozen_blocks", None)
                    entry.pop("_refit_blocks", None)
    # THE MEASUREMENT IS ON DISK BEFORE ANY SUMMARY RUNS.  Forty minutes
    # of decoding once died on a `mean` over a column that contained a
    # string; the raw rows are the expensive part and nothing that comes
    # after them may be able to lose them.  `--from-raw` re-enters here.
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "raw.json").write_text(json.dumps(
        {"schema": SCHEMA + "-raw", "per_capture": per_capture, "e1": e1,
         "truth_field": truth_report},
        indent=1, sort_keys=True, default=str))
    print(f"raw rows written to {OUT_DIR / 'raw.json'}")
    return _summarise_and_write(
        args, facts, spec, lane, coverage, scans, ceiling, measured,
        references, residue, truth_report, per_capture, e1, tree_before,
        started)


def _summarise_and_write(args, facts, spec, lane, coverage, scans, ceiling,
                         measured, references, residue, truth_report,
                         per_capture, e1, tree_before, started) -> int:
    """Everything downstream of the raw rows — replayable from raw.json."""
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
            "gt_affine": str(GT_AFFINE),
            "gt_affine_sha256": _swim_inputs.sha256_file(GT_AFFINE),
            "recovered_payload": str(QUAL_STATE.parent / "recovered.bin"),
            "recovered_payload_sha256": _swim_inputs.sha256_file(
                QUAL_STATE.parent / "recovered.bin"),
            "gt_affine_tree_before": ceiling.get("tree_before"),
        },
        "dead_bands": list(DEAD_BANDS),
        "measured_tiles": [
            {"tile_y": row.tile_y, "tile_x": row.tile_x,
             "stream": row.stream, "band": row.band, "role": row.role}
            for row in measured],
        "reference_tiles": [[ty, tx] for _pg, ty, tx in references],
        "residue_by_column": residue,
        "workers": int(args.workers),
        "approximations": [
            "restricted region: the detector is fitted over the windows "
            "within --fit-radius tiles of a target, exactly as gt_affine did",
            "E1 FROZEN is gt_affine's arm verbatim (one delta = 0 fit scores "
            "the corrected samples); E1 REFIT re-fits the whole restricted "
            "region with the target tile sampled at the correction, on BOTH "
            "arms, and asserts the features moved",
            "the geometry under test is SUPERVISED (fitted against the "
            "printed truth): a ceiling, not a receiver",
            "E2/E3 pool tile x capture rows as if independent; three "
            "captures of one physical tile are not — n_tiles is carried "
            "next to n_rows everywhere",
            "E2/E3 sample every window that carries the tile, so a cell "
            "covered by k windows contributes k rows",
            "the archived scale plan is a strict PREFIX of this tree's; the "
            "state loads with the session-level spec binding skipped",
        ],
        "truth_field": truth_report,
        "per_capture": per_capture,
        "e1": {"rows": e1, "summary": _e1_summary(e1)},
        "e2": _e2_summary(per_capture, measured),
        "e3": _e3_summary(per_capture, measured),
        "tree_before": tree_before,
        "tree_after": tree_after,
        "tree_moved": _swim_inputs.tree_moved(tree_before, tree_after),
        "wall_seconds": round(time.time() - started, 1),
        "peak_rss_gb": round(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30, 2),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "e1-refit.json").write_text(json.dumps(
        {key: value for key, value in out.items() if key not in ("e2", "e3")},
        indent=1, sort_keys=True, default=str))
    (OUT_DIR / "e2-directional.json").write_text(json.dumps(
        {**{key: value for key, value in out.items()
            if key in ("schema", "state", "format", "lane", "inputs",
                       "measured_tiles", "reference_tiles", "dead_bands",
                       "approximations", "tree_before", "tree_after",
                       "wall_seconds")},
         "e2": out["e2"],
         "per_tile": {sha: capture["e2"]
                      for sha, capture in per_capture.items()}},
        indent=1, sort_keys=True, default=str))
    (OUT_DIR / "e3-state-contrast.json").write_text(json.dumps(
        {**{key: value for key, value in out.items()
            if key in ("schema", "state", "format", "lane", "inputs",
                       "measured_tiles", "reference_tiles", "dead_bands",
                       "approximations", "tree_before", "tree_after",
                       "wall_seconds")},
         "e3": out["e3"],
         "per_tile": {sha: capture["e3"]
                      for sha, capture in per_capture.items()}},
        indent=1, sort_keys=True, default=str))
    _residue_figures.draw_e1(OUT_DIR / "e1-refit.png", e1, gate=GATE_BER)
    _residue_figures.draw_e2(OUT_DIR / "e2-directional.png", out["e2"])
    print(f"\nwrote {OUT_DIR}/e1-refit.json, e2-directional.json, "
          f"e3-state-contrast.json  ({out['wall_seconds']:.0f}s, peak RSS "
          f"{out['peak_rss_gb']} GB)")
    return 0


__all__ = ["GATE_BER", "run"]
