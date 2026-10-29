#!/usr/bin/env python3
# Historical record of e025 (Phase A, lattice slip vs print banding), retired from scratch/ 2026-10-09;
# inputs in the evidence archive. Regenerates build/phase-a/{maps/,phase_a_verdicts.json} with:
#   PYTHONPATH=src:. env/bin/python experiments/025-channel-metrology/phase-a/plot_field_maps.py --evidence-root DIR
"""E025 Phase A — within-field error cartography from analyzer traces.

Read-only, PIL-only (repo convention; matplotlib is not installed).  Consumes
the NPZ traces from `analyze_e025.py --trace-dir` plus the committed report and
stimulus manifest, and adjudicates the pre-registered Phase-A signatures:

  S1 drift    : within-field BER rises toward field extremes (constant phase
                is right in the middle and wrong at the ends)
  S2 transport: hot rows/bands align with the phase-rail wander series
  S3 slip     : BER ~ 0.5 nearly uniformly while the field still reports a
                finite separation score (lattice lost, reported as channel)
  S4 locality : cells near a self-calibrating coupon are cleaner than
                field-remote cells

Outputs per-field PNGs plus a page overview to build/phase-a/maps/ and the
machine-readable verdict table build/phase-a/phase_a_verdicts.json.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path()  # set in main(): --evidence-root, the published archive root
E025 = "paper-store-evidence-paperholo-era/025-channel-metrology"
# The detector traces are not in the published archive (tier delete,
# regenerable): they are read from build/, where the recipe writes them.
TRACES = ROOT / "experiments/025-channel-metrology/build"
TRACE_RECIPE = (
    "experiments/025-channel-metrology/analyze_e025.py on the published capture "
    "(<root>/" + E025 + "/bw-01/captures/bw-01-canon-4800grey-rot180.tiff, "
    "<root>/" + E025 + "/color-01/captures/color-01-canon-4800rgb.tiff) with every "
    "option mirrored from the published rerun report's own metadata "
    "(WORKPLAN-analyzer-v2.md §3 step 1) plus "
    "--trace-dir experiments/025-channel-metrology/build/trace-{bw,color}")
OUT = ROOT / "experiments/025-channel-metrology/build/phase-a"
MAPS = OUT / "maps"
VALIDATION = 2
PAGE_MM = (210.0, 297.0)

# inferno-ish anchors for BER in [0, 0.5]
_ANCHORS = [
    (0.00, (10, 12, 60)), (0.15, (120, 28, 109)), (0.30, (221, 81, 58)),
    (0.42, (252, 165, 10)), (0.50, (252, 255, 164)),
]


def colour(value: float) -> tuple[int, int, int]:
    if not np.isfinite(value):
        return (70, 70, 70)
    value = float(np.clip(value, 0.0, 0.5))
    for (a, ca), (b, cb) in zip(_ANCHORS, _ANCHORS[1:]):
        if value <= b:
            t = (value - a) / max(b - a, 1e-9)
            return tuple(int(round(ca[i] + t * (cb[i] - ca[i]))) for i in range(3))
    return _ANCHORS[-1][1]


def load_manifest(kind: str) -> tuple[dict, dict]:
    path = ROOT / "experiments/025-channel-metrology/build" / f"hp-m281-{kind}_manifest.json"
    page = json.loads(path.read_text())["pages"][0]
    return {f["field_id"]: f for f in page["fields"]}, page["candidates"]


def block_ber(err: np.ndarray, valid: np.ndarray, nblk: int = 24,
              min_cells: int = 25) -> np.ndarray:
    ny, nx = err.shape
    by, bx = max(1, math.ceil(ny / nblk)), max(1, math.ceil(nx / nblk))
    oy, ox = math.ceil(ny / by), math.ceil(nx / bx)
    out = np.full((oy, ox), np.nan)
    for j in range(oy):
        for i in range(ox):
            sl = (slice(j * by, (j + 1) * by), slice(i * bx, (i + 1) * bx))
            v = valid[sl]
            if int(v.sum()) >= min_cells:
                out[j, i] = float(err[sl][v].mean())
    return out


def marginal(err: np.ndarray, valid: np.ndarray, axis: int, nbin: int = 48,
             min_cells: int = 50) -> tuple[np.ndarray, np.ndarray]:
    n = err.shape[axis]
    step = max(1, math.ceil(n / nbin))
    pos, val = [], []
    for start in range(0, n, step):
        sl = ((slice(start, start + step), slice(None)) if axis == 0
              else (slice(None), slice(start, start + step)))
        v = valid[sl]
        if int(v.sum()) >= min_cells:
            pos.append(start + step / 2.0)
            val.append(float(err[sl][v].mean()))
    return np.asarray(pos), np.asarray(val)


def draw_series(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int],
                pos: np.ndarray, val: np.ndarray, n_total: int,
                label: str) -> None:
    x0, y0, x1, y1 = box
    draw.rectangle(box, outline=(90, 90, 90))
    draw.text((x0 + 4, y0 + 3), label, fill=(200, 200, 200))
    for level, col in ((0.5, (200, 60, 60)), (0.25, (90, 90, 90)),
                       (0.1, (60, 90, 60))):
        yy = y1 - int((y1 - y0 - 14) * (level / 0.55)) - 2
        draw.line([(x0 + 1, yy), (x1 - 1, yy)], fill=col)
    if pos.size < 2:
        return
    pts = []
    for p, v in zip(pos, val):
        xx = x0 + 2 + int((x1 - x0 - 4) * (p / max(n_total, 1)))
        yy = y1 - int((y1 - y0 - 14) * (min(v, 0.55) / 0.55)) - 2
        pts.append((xx, yy))
    draw.line(pts, fill=(120, 210, 255), width=2)


def classify(blk: np.ndarray, overall: float) -> dict:
    finite = blk[np.isfinite(blk)]
    out: dict[str, object] = {"overall_ber": overall, "n_blocks": int(finite.size)}
    if finite.size < 4:
        out["signature"] = "too-small"
        return out
    out.update({
        "block_ber_min": float(finite.min()), "block_ber_max": float(finite.max()),
        "block_ber_p05": float(np.percentile(finite, 5)),
        "block_ber_p50": float(np.percentile(finite, 50)),
        "block_ber_p95": float(np.percentile(finite, 95)),
        "block_spread": float(finite.max() - finite.min()),
        "fraction_blocks_near_half": float(np.mean(np.abs(finite - 0.5) < 0.06)),
        "fraction_blocks_below_10pct": float(np.mean(finite < 0.10)),
    })
    oy, ox = blk.shape
    yy, xx = np.mgrid[0:oy, 0:ox]
    cy, cx = (oy - 1) / 2.0, (ox - 1) / 2.0
    radius = np.sqrt(((yy - cy) / max(cy, 1e-9)) ** 2 + ((xx - cx) / max(cx, 1e-9)) ** 2)
    core = np.isfinite(blk) & (radius <= 0.6)
    rim = np.isfinite(blk) & (radius >= 1.0)
    if core.sum() >= 3 and rim.sum() >= 3:
        out["core_ber"] = float(blk[core].mean())
        out["rim_ber"] = float(blk[rim].mean())
        out["rim_minus_core"] = out["rim_ber"] - out["core_ber"]

    sig = []
    if out["fraction_blocks_near_half"] > 0.75:
        sig.append("S3-slip-uniform")
    if ("rim_minus_core" in out and out["rim_minus_core"] > 0.03
            and out["core_ber"] < 0.45):
        sig.append("S1-drift-rim-hot")
    if out["block_spread"] > 0.15 and out["fraction_blocks_near_half"] <= 0.75:
        sig.append("S1/S2-strong-spatial-structure")
    if out["block_spread"] <= 0.05 and overall < 0.05:
        sig.append("clean-uniform")
    if out["fraction_blocks_below_10pct"] > 0.05 and overall > 0.25:
        sig.append("bimodal-partial-lock")
    out["signature"] = ",".join(sig) if sig else "flat-elevated"
    return out


def render_field(fid: str, kind: str, blk: np.ndarray, err: np.ndarray,
                 valid: np.ndarray, verdict: dict, header: str) -> None:
    oy, ox = blk.shape
    cell = max(6, min(18, 380 // max(ox, oy)))
    map_w, map_h = ox * cell, oy * cell
    W, H = max(760, map_w + 400), max(300, map_h + 90)
    img = Image.new("RGB", (W, H), (18, 18, 22))
    d = ImageDraw.Draw(img)
    d.text((10, 8), f"{kind} | {fid}", fill=(235, 235, 235))
    d.text((10, 24), header, fill=(190, 190, 190))
    d.text((10, 40), f"signature: {verdict['signature']}", fill=(255, 210, 120))
    top = 60
    for j in range(oy):
        for i in range(ox):
            d.rectangle([10 + i * cell, top + j * cell,
                         10 + (i + 1) * cell - 1, top + (j + 1) * cell - 1],
                        fill=colour(blk[j, i]))
    d.text((10, top + map_h + 6), "block BER  0.0", fill=(140, 140, 140))
    for k in range(60):
        d.rectangle([120 + k * 3, top + map_h + 4, 122 + k * 3, top + map_h + 14],
                    fill=colour(k / 59 * 0.5))
    d.text((305, top + map_h + 6), "0.5", fill=(140, 140, 140))

    right = 10 + map_w + 20
    pr, vr = marginal(err, valid, axis=0)
    draw_series(d, (right, top, W - 12, top + (H - top - 30) // 2 - 6),
                pr, vr, err.shape[0], "BER vs row (top->bottom)")
    pc, vc = marginal(err, valid, axis=1)
    draw_series(d, (right, top + (H - top - 30) // 2 + 4, W - 12, H - 26),
                pc, vc, err.shape[1], "BER vs column (left->right)")
    img.save(MAPS / f"{kind}_{fid.replace('/', '_')}.png")


def render_overview(kind: str, rows: list[dict]) -> None:
    scale = 3.2
    W, H = int(PAGE_MM[0] * scale) + 260, int(PAGE_MM[1] * scale) + 40
    img = Image.new("RGB", (W, H), (16, 16, 20))
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, 10 + int(PAGE_MM[0] * scale), 10 + int(PAGE_MM[1] * scale)],
                outline=(120, 120, 120))
    for r in rows:
        if "x_mm" not in r:
            continue
        x0 = 10 + int(r["x_mm"] * scale)
        y0 = 10 + int(r["y_mm"] * scale)
        x1 = 10 + int((r["x_mm"] + r["field_w_mm"]) * scale)
        y1 = 10 + int((r["y_mm"] + r["field_h_mm"]) * scale)
        d.rectangle([x0, y0, max(x1, x0 + 2), max(y1, y0 + 2)],
                    fill=colour(r["overall_ber"]), outline=(40, 40, 40))
        if (x1 - x0) > 44 and (y1 - y0) > 12:
            d.text((x0 + 3, y0 + 3), f"{r['overall_ber']*100:.0f}%", fill=(255, 255, 255))
    d.text((20 + int(PAGE_MM[0] * scale), 14),
           f"E025 {kind}: field BER on the page", fill=(235, 235, 235))
    d.text((20 + int(PAGE_MM[0] * scale), 32),
           "dark=clean  bright=coin-flip", fill=(160, 160, 160))
    y = 56
    for r in sorted(rows, key=lambda z: -z["overall_ber"])[:34]:
        d.text((20 + int(PAGE_MM[0] * scale), y),
               f"{r['overall_ber']*100:5.1f}%  {r['field_id'][:30]}",
               fill=colour(r["overall_ber"]))
        y += 13
    img.save(MAPS / f"_overview_{kind}.png")


def _evidence_root(*published: str) -> Path:
    """--evidence-root (the published archive root), refused by name unless
    every ``published`` path under it exists and at least one regenerated
    trace index is in build/."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import argparse
    from measure import _evidence
    ap = argparse.ArgumentParser()
    _evidence.add_argument(ap)
    tool = Path(__file__).stem
    root = _evidence.resolve(ap.parse_args().evidence_root, tool=tool)
    _evidence.need(*(root / rel for rel in published), tool=tool)
    indexes = [TRACES / name / "index.json" for name in ("trace-bw", "trace-color")]
    if not any(path.exists() for path in indexes):
        _evidence.need(*indexes, tool=tool,
                       regenerate=TRACE_RECIPE.replace("<root>", str(root)))
    return root


def main() -> int:
    global EVIDENCE
    EVIDENCE = _evidence_root(E025 + "/records/analysis/rerun-bw-report.json",
                              E025 + "/records/analysis/rerun-color-report.json")
    OUT.mkdir(parents=True, exist_ok=True)
    MAPS.mkdir(parents=True, exist_ok=True)
    verdicts: dict[str, dict] = {}
    for kind, trace_name, report_name in (
        ("bw", "trace-bw", E025 + "/records/analysis/rerun-bw-report.json"),
        ("color", "trace-color", E025 + "/records/analysis/rerun-color-report.json"),
    ):
        trace_dir = TRACES / trace_name
        index_path = trace_dir / "index.json"
        if not index_path.exists():
            print(f"skip {kind}: missing {index_path}")
            continue
        index = json.loads(index_path.read_text())
        entries = index["fields"] if isinstance(index, dict) else index
        fields, cands = load_manifest(kind)
        report = json.loads((EVIDENCE / report_name).read_text())
        obs_by_id = {o["diagnostics"]["field_id"]: o for o in report["observations"]}
        overview: list[dict] = []

        for entry in entries:
            fid = entry["field_id"]
            nx, ny = int(entry["nx"]), int(entry["ny"])
            data = np.load(trace_dir / entry["file"])
            truth, pred, split = data["true_state"], data["predicted_state"], data["split"]
            n = nx * ny
            if truth.size < n:
                print(f"  {kind}/{fid}: trace {truth.size} < field {n}; skipped")
                continue
            err = (truth[:n] != pred[:n]).reshape(ny, nx)
            valid = (split[:n] == VALIDATION).reshape(ny, nx)
            if int(valid.sum()) < 200:
                continue
            overall = float(err[valid].mean())
            blk = block_ber(err, valid)
            verdict = classify(blk, overall)
            verdict["field_id"] = fid
            meta = fields.get(fid, {})
            grid = cands.get(meta.get("candidate_key"), {}).get("grid", {})
            if grid:
                px = 25.4 * grid["c_x"] / grid["dpi_x"]
                py = 25.4 * grid["c_y"] / grid["dpi_y"]
                verdict.update({
                    "pitch_x_mm": px, "pitch_y_mm": py,
                    "field_w_mm": nx * px, "field_h_mm": ny * py,
                    "c_x": grid["c_x"], "c_y": grid["c_y"],
                    "dpi_x": grid["dpi_x"],
                    "x_mm": meta.get("x_layout_dots", 0) * 25.4 / 600,
                    "y_mm": meta.get("y_layout_dots", 0) * 25.4 / 600,
                    "nx": nx, "ny": ny,
                })
            if fid in obs_by_id:
                dg = obs_by_id[fid]["diagnostics"]
                verdict.update({
                    "report_ber": obs_by_id[fid]["hard_error_rate"],
                    "report_mi": obs_by_id[fid]["mutual_information_bpc"],
                    "separation": dg["phase_separation_score"],
                    "phase_x": dg["phase_x_cells"], "phase_y": dg["phase_y_cells"],
                    "family": dg["family"], "role": dg["role"],
                    "scan_adequate": obs_by_id[fid]["scan_adequate"],
                })
            verdicts[f"{kind}/{fid}"] = verdict
            if "field_w_mm" in verdict:
                overview.append(verdict)
            header = (f"BER {overall*100:.2f}%  blocks[{verdict.get('block_ber_min', float('nan')):.3f}"
                      f"..{verdict.get('block_ber_max', float('nan')):.3f}]  "
                      f"sep {verdict.get('separation', float('nan')):.3f}  "
                      f"phase({verdict.get('phase_x')},{verdict.get('phase_y')})  "
                      f"{verdict.get('field_w_mm', 0):.0f}x{verdict.get('field_h_mm', 0):.0f}mm")
            render_field(fid, kind, blk, err, valid, verdict, header)
            print(f"  {kind}/{fid:36s} BER {overall*100:6.2f}%  "
                  f"blk[{verdict.get('block_ber_min', float('nan')):.3f},"
                  f"{verdict.get('block_ber_max', float('nan')):.3f}]  {verdict['signature']}")
        render_overview(kind, overview)

    (OUT / "phase_a_verdicts.json").write_text(
        json.dumps(verdicts, indent=2, sort_keys=True) + "\n")
    print(f"\n{len(verdicts)} verdicts -> {OUT / 'phase_a_verdicts.json'}")
    print(f"maps -> {MAPS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
