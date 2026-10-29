# Historical record of e017 (017.4, the Canon 4800 re-anchoring), retired from scratch/ 2026-10-09;
# inputs in the evidence archive. Regenerates build/probe17_out/canon-p2.json with:
#   PYTHONPATH=src:. env/bin/python experiments/017-color-channel/probes/probe17_canon_p2.py --evidence-root DIR [n_tiles]   (after probe17_canon_prep.py)
"""probe17_canon_p2: 017.4 P2-Canon — does the 8 px/dot footing resurrect the
M281 composite luma lattice lock? (THE GO/NO-GO for e017 blind decode on the
home engine.)

On A3 (7-state c3 composite) tile crops of the Canon 4800 dpi RGB scan of the
SAME sheet the 1200 dpi flatbed baseline measured (probes/probe17_out/
e004-home.json: cell_tight contrast median 14.7, blind pitch ID 2/16):

  per tile x footing {24 (native), 12, 8, 6 px/cell — box-mean decimations}:
    * scannorm.measure_cell_pitch (blind wide-band ID)
    * estimate_lattice narrow-band at the cell nominal (0.12 + tight 0.05
      octaves), the 165 lpi M281 screen line, and the dot lattice line
    * acquire.lock_grid at the cell nominal (win scaled to ~16 cells)
    * success flags: strict (mcp fundamental == cell pitch +-3%) and
      format-path (any credible strong line integer-divides the cell pitch
      +-3% — the paperholo.formats hypothesis enumeration).

Geometry via probe17_canon_reg.json (cal_core registration of the x4
decimation, scaled to native). Crops from the tifffile memmap only.

Usage: env/bin/python experiments/017-color-channel/probes/probe17_canon_p2.py --evidence-root DIR [n_tiles]
Writes experiments/017-color-channel/build/probe17_out/canon-p2.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import tifffile

REPO = Path(__file__).resolve().parents[3]
for rel in ("experiments/004-finalists-checkerboard",
            "experiments/002-calibration-page", "src"):
    p = str(REPO / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

import analyze_e004 as ae                            # noqa: E402
import cal_core as cc                                # noqa: E402
from paperholo import acquire as acq                 # noqa: E402
from paperholo.scannorm import measure_cell_pitch, ScanRefused  # noqa: E402
from paperholo.sync import estimate_lattice          # noqa: E402

SCAN_REL = "paper-store-evidence-paperholo-era/004-finalists-checkerboard/finalists/captures/finalists-canon-4800rgb.tiff"   # under --evidence-root
REG = json.loads((REPO / "experiments/017-color-channel/build" / "probe17_canon_reg.json").read_text())
OUT = REPO / "experiments/017-color-channel/build" / "probe17_out"
DPD = 600 / 25.4
CELL = 3
INSET_MM = 1.8
FOOTINGS = (1, 2, 3, 4)          # native /2 /3 /4 -> 24/12/8/6 px/cell
SCREEN_PX_NATIVE = 4800 / 165.0  # 29.09 px M281 composite screen
# spread pick over the 16 A3 tiles (by row/col): corners, edges, center
PICK_RC = [(0, 3), (0, 5), (1, 0), (2, 7), (4, 4), (5, 2), (7, 3), (7, 5)]


def crop_native_luma(mm: np.ndarray, coef: np.ndarray,
                     x0d: float, y0d: float, x1d: float, y1d: float
                     ) -> np.ndarray:
    corners = np.array([[x0d, y0d], [x1d, y0d], [x0d, y1d], [x1d, y1d]])
    px = cc.affine_apply(coef, corners)
    x0, y0 = int(np.ceil(px[:, 0].min())), int(np.ceil(px[:, 1].min()))
    x1, y1 = int(np.floor(px[:, 0].max())), int(np.floor(px[:, 1].max()))
    blk = np.asarray(mm[y0:y1, x0:x1], np.float32)
    return (blk[..., 0] + blk[..., 1] + blk[..., 2]) / (3.0 * 255.0)


def box_dec(a: np.ndarray, f: int) -> np.ndarray:
    if f == 1:
        return a
    h, w = a.shape[0] // f * f, a.shape[1] // f * f
    return a[:h, :w].reshape(h // f, f, w // f, f).mean(axis=(1, 3))


def probe_footing(luma: np.ndarray, cell_px_exp: float, dec: int) -> dict:
    out: dict = {"px_per_cell_expected": round(cell_px_exp, 4),
                 "shape": list(luma.shape)}
    t0 = time.time()
    # 1. blind wide-band pitch ID (scannorm verbatim)
    try:
        pm = measure_cell_pitch(luma)
        out["mcp"] = {"pitch_px": round(pm.pitch_px, 4),
                      "contrast": round(pm.contrast, 1),
                      "strong": [[round(p, 3), round(c, 1)]
                                 for p, c in pm.strong]}
        out["id_strict"] = bool(abs(pm.pitch_px / cell_px_exp - 1.0) <= 0.03)
        fmt_ok = False
        for p, c in pm.strong:
            k = max(1.0, round(cell_px_exp / p))
            if abs(cell_px_exp - k * p) <= 0.03 * cell_px_exp:
                fmt_ok = True
        out["id_format_path"] = fmt_ok
    except ScanRefused as e:
        out["mcp"] = {"refused": str(e)}
        out["id_strict"] = out["id_format_path"] = False
    # 2. narrow-band lines
    lines = {}
    probes = {"cell": (cell_px_exp, 0.12), "cell_tight": (cell_px_exp, 0.05),
              "screen165": (SCREEN_PX_NATIVE / dec, 0.05),
              "dot": (cell_px_exp / CELL, 0.05)}
    for name, (p, oct_) in probes.items():
        if p < 2.5 or min(luma.shape) < 8 * p:
            continue
        try:
            est = estimate_lattice(luma, pitch_px_nominal=p,
                                   search_octaves=oct_)
            lines[name] = {"probe_px": round(p, 3),
                           "pitch_px": round(float(est["pitch_px"]), 4),
                           "contrast": round(float(est["contrast"]), 1)}
        except Exception as e:
            lines[name] = {"probe_px": round(p, 3), "error": str(e)}
    out["lines"] = lines
    # 3. lock_grid at the cell nominal (window ~16 cells across)
    win = max(96, int(round(16 * cell_px_exp)))
    try:
        gm = acq.lock_grid(luma, cell_px_nominal=cell_px_exp,
                           win_px=win, step_px=win // 2)
        q = np.asarray(gm.quality, np.float64).ravel()
        out["lock"] = {
            "pitch_v_px": round(float(gm.pitch_v_px), 4),
            "pitch_u_px": round(float(gm.pitch_u_px), 4),
            "err_v_pct": round((gm.pitch_v_px / cell_px_exp - 1) * 100, 3),
            "err_u_pct": round((gm.pitch_u_px / cell_px_exp - 1) * 100, 3),
            "quality_mean": round(float(q.mean()), 4),
            "quality_p10": round(float(np.percentile(q, 10)), 4),
            "win_px": win}
    except Exception as e:
        out["lock"] = {"error": f"{type(e).__name__}: {e}", "win_px": win}
    out["seconds"] = round(time.time() - t0, 1)
    return out


def _scan_tiff() -> Path:
    """The e004 Canon 4800 capture under --evidence-root (strips the flag from argv)."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    import argparse
    from measure import _evidence
    ap = argparse.ArgumentParser()
    _evidence.add_argument(ap)
    a, sys.argv[1:] = ap.parse_known_args()
    scan = _evidence.resolve(a.evidence_root, tool=Path(__file__).stem) / SCAN_REL
    _evidence.need(scan, tool=Path(__file__).stem)
    return scan


def main() -> None:
    scan_tiff = _scan_tiff()
    OUT.mkdir(parents=True, exist_ok=True)
    n_tiles = int(sys.argv[1]) if len(sys.argv) > 1 else len(PICK_RC)
    coef = np.asarray(REG["affine_native4800"], np.float64)
    st = cc.affine_stats(coef)
    mm = tifffile.memmap(scan_tiff, mode="r")
    manifest = cc.load_manifest(ae.MANIFEST_PATH)
    a3 = {(t["row"], t["col"]): t for t in manifest["tiles"]
          if t["class"] == "A3"}
    res: dict = {"probe": "P2-Canon", "date": "2026-07-10",
                 "scan_sha256": "e1f14f1c57ffcefeac25d66a236bdadf01765454"
                                "893d152856dcfefca360b4ba",
                 "px_per_dot": {"x": round(st["px_per_dot_x"], 5),
                                "y": round(st["px_per_dot_y"], 5)},
                 "baseline_1200dpi": {"cell_tight_contrast_median": 14.7,
                                      "blind_id_ok": "2/16"},
                 "tiles": []}
    for rc in PICK_RC[:n_tiles]:
        t = a3[rc]
        x0d = (t["x_mm"] + INSET_MM) * DPD
        y0d = (t["y_mm"] + INSET_MM) * DPD
        x1d = (t["x_mm"] + 21.0 - INSET_MM) * DPD
        y1d = (t["y_mm"] + 30.0 - INSET_MM) * DPD
        luma_native = crop_native_luma(mm, coef, x0d, y0d, x1d, y1d)
        rec: dict = {"tile": t["name"], "row": t["row"], "col": t["col"],
                     "footings": {}}
        for dec in FOOTINGS:
            cell_px_exp = CELL * (st["px_per_dot_x"] + st["px_per_dot_y"]) \
                / 2.0 / dec
            r = probe_footing(box_dec(luma_native, dec), cell_px_exp, dec)
            rec["footings"][f"{cell_px_exp:.1f}px"] = r
            mcp = r["mcp"]
            print(f"{t['name']} dec{dec} ({cell_px_exp:5.2f}px/cell): "
                  f"mcp={mcp.get('pitch_px', 'REFUSED')} "
                  f"c={mcp.get('contrast', 0)} "
                  f"strict={r['id_strict']} fmt={r['id_format_path']} "
                  f"cell_tight={r['lines'].get('cell_tight', {}).get('contrast')} "
                  f"lock v/u err {r['lock'].get('err_v_pct')}/"
                  f"{r['lock'].get('err_u_pct')}% "
                  f"q={r['lock'].get('quality_mean')}", flush=True)
        res["tiles"].append(rec)
    (OUT / "canon-p2.json").write_text(json.dumps(res, indent=1))
    print(f"-> {OUT / 'canon-p2.json'}", flush=True)


if __name__ == "__main__":
    main()
