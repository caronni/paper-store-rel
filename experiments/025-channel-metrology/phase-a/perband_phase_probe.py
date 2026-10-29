#!/usr/bin/env python3
# Historical record of e025 (Phase A, lattice slip vs print banding), retired from scratch/ 2026-10-09;
# inputs in the evidence archive. Regenerates build/phase-a/perband_probe.json with:
#   PYTHONPATH=src:. env/bin/python experiments/025-channel-metrology/phase-a/perband_phase_probe.py --evidence-root DIR
"""E025 Phase A/B seam — per-band geometry probe (the decisive experiment).

Re-samples the ORIGINAL scan pixels for selected fields using a per-horizontal-
band lattice phase instead of one constant phase per field, reusing the
analyzer's own sampling/QDA machinery so the only variable is geometry.

If per-band phase collapses the reported field BER, then the published E025
"channel" numbers for small-cell candidates are geometry artifacts and Phase B
(per-window pose) is justified with a quantified expected gain.

The band phase search is deliberately allowed to leave the +/-0.5-cell box: the
whole point is that the true offset exceeds one cell in places.

Read-only with respect to the repo; writes build/phase-a/perband_probe.json.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path()  # set in main(): --evidence-root, the published archive root
OUT = ROOT / "experiments/025-channel-metrology/build/phase-a"
EXP = ROOT / "experiments/025-channel-metrology"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))


def load_analyzer():
    spec = importlib.util.spec_from_file_location("analyze_e025", EXP / "analyze_e025.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["analyze_e025"] = module
    spec.loader.exec_module(module)
    return module


AZ = load_analyzer()
import e025_common as ec  # noqa: E402  (analyzer's own helper module)

TARGETS = {
    "bw": ["spatial/top/c3", "spatial/middle/c2", "spatial/top/c2",
           "spatial/bottom/c2", "spatial/middle/c1", "grid-control/600-c2",
           "spatial/middle/c4"],
    "color": ["pure/C/c2", "pure/K/c2", "states/middle/cmy8-c2",
              "states/bottom/cmy8-c3", "states/middle/cm4-c2"],
}
CAPTURE = {
    "bw": ("paper-store-evidence-paperholo-era/025-channel-metrology/bw-01/captures/bw-01-canon-4800grey-rot180.tiff",
           "hp-m281-bw",
           "paper-store-evidence-paperholo-era/025-channel-metrology/records/analysis/rerun-bw-report.json"),
    "color": ("paper-store-evidence-paperholo-era/025-channel-metrology/color-01/captures/color-01-canon-4800rgb.tiff",
              "hp-m281-color",
              "paper-store-evidence-paperholo-era/025-channel-metrology/records/analysis/rerun-color-report.json"),
}


def band_phase_search(source, coef, field, grid, states, definition,
                      idx_phase: np.ndarray, use_color: bool,
                      seed_x: float, seed_y: float) -> tuple[float, float, float]:
    """Coarse y sweep beyond one cell, then a local 2-D refine."""
    labels = states.ravel()[idx_phase]
    n_states = len(definition.states)
    if len(np.unique(labels)) < n_states:
        return seed_x, seed_y, -math.inf

    def score(px: float, py: float) -> float:
        rgb = AZ._sample_indices(source, coef, field, grid, idx_phase, px, py)
        return AZ._separation(AZ._features(rgb, use_color), labels, n_states)

    best = (-math.inf, seed_x, seed_y)
    for dy in np.arange(-2.5, 2.5 + 1e-9, 0.1):
        s = score(seed_x, float(dy))
        if s > best[0]:
            best = (s, seed_x, float(dy))
    for dx in np.arange(best[1] - 1.2, best[1] + 1.2 + 1e-9, 0.1):
        s = score(float(dx), best[2])
        if s > best[0]:
            best = (s, float(dx), best[2])
    for dy in np.arange(best[2] - 0.12, best[2] + 0.12 + 1e-9, 0.03):
        for dx in np.arange(best[1] - 0.12, best[1] + 0.12 + 1e-9, 0.03):
            s = score(float(dx), float(dy))
            if s > best[0]:
                best = (s, float(dx), float(dy))
    return best[1], best[2], best[0]


def probe_field(source, coef, page, field, kind, obs, n_bands: int = 20) -> dict:
    cand_raw = page["candidates"][field["candidate_key"]]
    candidate = AZ.CandidateSpec.from_dict(cand_raw)
    definition = ec.CHANNELS[cand_raw["definition_id"]]
    grid = candidate.grid
    states = ec.field_states(field, definition)
    nx, ny = int(field["nx"]), int(field["ny"])
    use_color = AZ._use_color_features(source, definition)
    n_states = len(definition.states)
    seed_x = obs["diagnostics"]["phase_x_cells"]
    seed_y = obs["diagnostics"]["phase_y_cells"]

    step = max(1, math.ceil(ny / n_bands))
    bands = []
    tot_val = tot_err_base = tot_err_band = 0
    for start in range(0, ny, step):
        stop = min(ny, start + step)
        rows = np.arange(start, stop, dtype=np.int64)
        idx = (rows[:, None] * nx + np.arange(nx, dtype=np.int64)[None, :]).ravel()
        phase_pool = idx[idx % 8 == 0]
        train_pool = idx[np.isin(idx % 8, (1, 2, 3))]
        val_pool = idx[np.isin(idx % 8, (4, 5, 6, 7))]
        if len(val_pool) < 400 or len(train_pool) < 400:
            continue
        flat = states.ravel()
        # bounded search population keeps the sweep affordable
        sub = phase_pool[np.linspace(0, len(phase_pool) - 1,
                                     min(len(phase_pool), 1600)).round().astype(int)]
        px, py, sep = band_phase_search(source, coef, field, grid, states,
                                        definition, sub, use_color, seed_x, seed_y)

        def evaluate(phx: float, phy: float) -> float:
            tr = AZ._features(AZ._sample_indices(source, coef, field, grid,
                                                 train_pool, phx, phy), use_color)
            va = AZ._features(AZ._sample_indices(source, coef, field, grid,
                                                 val_pool, phx, phy), use_color)
            try:
                model = AZ._fit_qda(tr, flat[train_pool], n_states)
            except RuntimeError:
                return float("nan")
            pred = np.argmax(model.scores(va), axis=1)
            return float(np.mean(pred != flat[val_pool]))

        ber_base = evaluate(seed_x, seed_y)
        ber_band = evaluate(px, py)
        bands.append({
            "row_start": int(start), "row_stop": int(stop),
            "phase_x": px, "phase_y": py, "separation": sep,
            "state_err_field_phase": ber_base, "state_err_band_phase": ber_band,
            "n_validation": int(len(val_pool)),
        })
        if np.isfinite(ber_base) and np.isfinite(ber_band):
            tot_val += len(val_pool)
            tot_err_base += ber_base * len(val_pool)
            tot_err_band += ber_band * len(val_pool)
        print(f"    rows {start:5d}-{stop:5d}  phase=({px:+.2f},{py:+.2f})  "
              f"field-phase {ber_base*100:6.2f}%  ->  band-phase {ber_band*100:6.2f}%")

    ys = [b["phase_y"] for b in bands]
    return {
        "field_id": field["field_id"],
        "seed_phase": [seed_x, seed_y],
        "bands": bands,
        "weighted_state_err_field_phase": tot_err_base / max(tot_val, 1),
        "weighted_state_err_band_phase": tot_err_band / max(tot_val, 1),
        "phase_y_span_cells": (max(ys) - min(ys)) if ys else None,
        "phase_y_min": min(ys) if ys else None,
        "phase_y_max": max(ys) if ys else None,
        "report_hard_error_rate": obs["hard_error_rate"],
    }


def _evidence_root(*published: str) -> Path:
    """--evidence-root (the published archive root), refused by name unless
    every ``published`` path under it exists."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import argparse
    from measure import _evidence
    ap = argparse.ArgumentParser()
    _evidence.add_argument(ap)
    root = _evidence.resolve(ap.parse_args().evidence_root, tool=Path(__file__).stem)
    _evidence.need(*(root / rel for rel in published), tool=Path(__file__).stem)
    return root


def main() -> int:
    global EVIDENCE
    EVIDENCE = _evidence_root(*(rel for tiff, _preset, report in CAPTURE.values()
                                for rel in (tiff, report)))
    OUT.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    for kind, names in TARGETS.items():
        tiff, preset, report_name = CAPTURE[kind]
        manifest = json.loads((EXP / "build" / f"{preset}_manifest.json").read_text())
        page = manifest["pages"][0]
        fields = {f["field_id"]: f for f in page["fields"]}
        report = json.loads((EVIDENCE / report_name).read_text())
        obs_by_id = {o["diagnostics"]["field_id"]: o for o in report["observations"]}
        coef = np.asarray(report["metadata"]["e025"]["geometry"]["affine_layout_to_scan"],
                          dtype=np.float64)
        source = AZ.RasterSource(EVIDENCE / tiff)
        print(f"== {kind}: {tiff}")
        for fid in names:
            if fid not in fields or fid not in obs_by_id:
                print(f"  {fid}: absent; skipped")
                continue
            print(f"  {fid} (report {obs_by_id[fid]['hard_error_rate']*100:.2f}%)")
            results[f"{kind}/{fid}"] = probe_field(
                source, coef, page, fields[fid], kind, obs_by_id[fid])
            r = results[f"{kind}/{fid}"]
            print(f"    => field-phase {r['weighted_state_err_field_phase']*100:.2f}%  "
                  f"band-phase {r['weighted_state_err_band_phase']*100:.2f}%  "
                  f"phase_y span {r['phase_y_span_cells']:.2f} cells")
    (OUT / "perband_probe.json").write_text(
        json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {OUT / 'perband_probe.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
