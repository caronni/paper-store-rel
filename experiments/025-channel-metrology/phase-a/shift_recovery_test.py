#!/usr/bin/env python3
# Historical record of e025 (Phase A, lattice slip vs print banding), retired from scratch/ 2026-10-09;
# inputs in the evidence archive. Regenerates build/phase-a/shift_recovery.json with:
#   PYTHONPATH=src:. env/bin/python experiments/025-channel-metrology/phase-a/shift_recovery_test.py --evidence-root DIR
"""E025 Phase A — DECISIVE test: lattice slip vs real print banding.

Competing hypotheses for the horizontal BER bands seen in the trace maps:

  H_geom  the sampler is reading the wrong CELL in those bands (accumulated
          y-warp exceeded the constant per-field phase).  Prediction: within a
          bad band, comparing the predicted states against the truth map
          SHIFTED by a small integer number of cells recovers a low BER, and
          the required shift varies smoothly with y.

  H_print the toner really is degraded in those bands (M281 gear ripple /
          density banding is documented).  Prediction: NO integer shift
          recovers the band; the best shift stays 0 and BER stays high.

The test is decisive because a shift is a pure relabelling: if a nonzero shift
makes ~all cells agree, the ink pattern was intact and only the address was
wrong.

Read-only.  Writes build/phase-a/shift_recovery.json.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
E025 = "paper-store-evidence-paperholo-era/025-channel-metrology"
# The detector traces are this test's only input and are not in the published
# archive (tier delete, regenerable): they are read from build/, where the
# recipe writes them from the published captures.
TRACES = ROOT / "experiments/025-channel-metrology/build"
TRACE_RECIPE = (
    "experiments/025-channel-metrology/analyze_e025.py on the published capture "
    "(<root>/" + E025 + "/bw-01/captures/bw-01-canon-4800grey-rot180.tiff, "
    "<root>/" + E025 + "/color-01/captures/color-01-canon-4800rgb.tiff) with every "
    "option mirrored from the published rerun report's own metadata "
    "(WORKPLAN-analyzer-v2.md §3 step 1) plus "
    "--trace-dir experiments/025-channel-metrology/build/trace-{bw,color}")
OUT = ROOT / "experiments/025-channel-metrology/build/phase-a"
VALIDATION = 2
MAX_SHIFT = 4


def band_shift_scan(truth: np.ndarray, pred: np.ndarray, valid: np.ndarray,
                    n_bands: int = 20) -> list[dict]:
    """Per horizontal band: BER at zero shift vs best integer (dy, dx) shift."""
    ny, nx = truth.shape
    step = max(1, math.ceil(ny / n_bands))
    rows = []
    for start in range(0, ny, step):
        stop = min(ny, start + step)
        # Work in a haloed window so shifts stay inside the field.
        lo = max(0, start - MAX_SHIFT)
        hi = min(ny, stop + MAX_SHIFT)
        t_win, p_win, v_win = truth[lo:hi], pred[lo:hi], valid[lo:hi]
        y0, y1 = start - lo, stop - lo
        best = None
        zero = None
        for dy in range(-MAX_SHIFT, MAX_SHIFT + 1):
            for dx in range(-MAX_SHIFT, MAX_SHIFT + 1):
                ys0, ys1 = y0 + dy, y1 + dy
                if ys0 < 0 or ys1 > t_win.shape[0]:
                    continue
                xs0, xs1 = max(0, dx), min(nx, nx + dx)
                xp0, xp1 = xs0 - dx, xs1 - dx
                if xs1 - xs0 < nx // 2:
                    continue
                t = t_win[ys0:ys1, xs0:xs1]
                p = p_win[y0:y1, xp0:xp1]
                v = v_win[y0:y1, xp0:xp1]
                n = int(v.sum())
                if n < 100:
                    continue
                ber = float((t[v] != p[v]).mean())
                if dy == 0 and dx == 0:
                    zero = ber
                if best is None or ber < best[0]:
                    best = (ber, dy, dx, n)
        if best is None or zero is None:
            continue
        rows.append({
            "row_start": int(start), "row_stop": int(stop),
            "ber_zero_shift": zero, "ber_best_shift": best[0],
            "best_dy_cells": best[1], "best_dx_cells": best[2],
            "n_validation": best[3],
            "recovered": bool(zero > 0.15 and best[0] < 0.05),
        })
    return rows


def _require_traces() -> None:
    """--evidence-root resolved (the recipe's captures live under it), then a
    refusal by name unless at least one regenerated trace index is in build/."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import argparse
    from measure import _evidence
    ap = argparse.ArgumentParser()
    _evidence.add_argument(ap)
    tool = Path(__file__).stem
    root = _evidence.resolve(ap.parse_args().evidence_root, tool=tool)
    indexes = [TRACES / name / "index.json" for name in ("trace-bw", "trace-color")]
    if not any(path.exists() for path in indexes):
        _evidence.need(*indexes, tool=tool,
                       regenerate=TRACE_RECIPE.replace("<root>", str(root)))


def main() -> int:
    _require_traces()
    OUT.mkdir(parents=True, exist_ok=True)
    out: dict[str, dict] = {}
    for kind, trace_name in (("bw", "trace-bw"), ("color", "trace-color")):
        index_path = TRACES / trace_name / "index.json"
        if not index_path.exists():
            continue
        index = json.loads(index_path.read_text())
        entries = index["fields"] if isinstance(index, dict) else index
        for entry in entries:
            fid = entry["field_id"]
            nx, ny = int(entry["nx"]), int(entry["ny"])
            if nx * ny < 40_000:      # need a field tall enough to band
                continue
            data = np.load(TRACES / trace_name / entry["file"])
            n = nx * ny
            if data["true_state"].size < n:
                continue
            truth = data["true_state"][:n].reshape(ny, nx)
            pred = data["predicted_state"][:n].reshape(ny, nx)
            valid = (data["split"][:n] == VALIDATION).reshape(ny, nx)
            rows = band_shift_scan(truth, pred, valid)
            if not rows:
                continue
            bad = [r for r in rows if r["ber_zero_shift"] > 0.15]
            rec = [r for r in bad if r["recovered"]]
            shifts = sorted({(r["best_dy_cells"], r["best_dx_cells"]) for r in rows})
            key = f"{kind}/{fid}"
            out[key] = {
                "bands": rows,
                "n_bands": len(rows),
                "n_bands_bad": len(bad),
                "n_bad_recovered_by_shift": len(rec),
                "distinct_shifts": [list(s) for s in shifts],
                "mean_ber_zero": float(np.mean([r["ber_zero_shift"] for r in rows])),
                "mean_ber_best": float(np.mean([r["ber_best_shift"] for r in rows])),
            }
            print(f"{key:44s} bands {len(rows):3d} bad {len(bad):3d} "
                  f"recovered-by-shift {len(rec):3d} | "
                  f"BER {out[key]['mean_ber_zero']*100:6.2f}% -> "
                  f"{out[key]['mean_ber_best']*100:6.2f}% | shifts {shifts[:8]}")
    (OUT / "shift_recovery.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {OUT / 'shift_recovery.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
