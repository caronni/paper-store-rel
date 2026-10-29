#!/usr/bin/env python
"""E012 hardware scoring harness (run 012.3): blind-decode windows of the
Canon scans of the printed e012 sheet and score payload BER against the
frozen build's payload.

GROUND-TRUTH RULE (the 2026-07-09 phantom-payload lesson, run 012.3 log):
the payload reference is drawn EXACTLY as gen_e012.py draws it —
`rng(SEED, b"e012/payload").integers(0, 2, cap, dtype=np.uint8)`. The dtype
kwarg changes NumPy's bounded-integer stream; a hand-rolled reference
without it is a statistically independent bitstream that scores ~50% BER
with perfect pilots (the run 012.3 incident + retraction). Never retype
seeded draws: this script imports gen_e012 and re-derives via its module.

Per scan/position: full blind acquire_and_decode (lock -> Stage A/B ->
anchors -> absolute payload addressing), BER + null (idx+7919 stride).
Then an equal-weight 3-scan majority vote on the intersected absolute
payload indices of the center windows — kept as a MEASUREMENT of cross-scan
error correlation, not as a recommended combiner (012.3: it LOSES to the
best single scan on healthy c3; errors are print-frozen).

Run from experiments/012-pilot-print/:
    ../../env/bin/python score_canon_scans.py --scan-dir <evidence>/scans [--quick]
--quick: 1200 dpi scan only, center window only (smoke).
Scans expected in --scan-dir (evidence archive; shas in the 012.3 run
table). Missing files are skipped with a notice.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

EXP = Path(__file__).resolve().parent
ROOT = EXP.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))
from PIL import Image  # noqa: E402
Image.MAX_IMAGE_PIXELS = None

from paperholo import acquire, compose  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
import gen_e012  # noqa: E402

SEED = gen_e012.SEED
NULL_STRIDE = 7919
WIN_PX = 1884                       # window edge at 2 px/dot (~40 mm)

SCANS = [
    ("1200", "xerox-e012-A-canon-1200.png", 1,
     [(0.5, 0.5), (0.42, 0.42), (0.58, 0.58)]),
    ("2400", "xerox-e012-A-canon-2400bw.png", 2,
     [(0.5, 0.5), (0.42, 0.42)]),
    ("4800", "xerox-e012-A-canon-4800.tiff", 4,
     [(0.5, 0.5), (0.42, 0.42)]),
]


def _load(path: Path) -> np.ndarray:
    if path.suffix.lower() in (".tif", ".tiff"):
        import tifffile
        return tifffile.TiffFile(str(path)).pages[0].asarray(out="memmap")
    return np.asarray(Image.open(path).convert("L"))


def _crop_down(arr: np.ndarray, fy: float, fx: float, f: int) -> np.ndarray:
    """Center a WIN_PX*f source crop at fractional page position, box-average
    down to 2 px/dot."""
    H, W = arr.shape[:2]
    src = WIN_PX * f
    y0 = max(0, int(H * fy) - src // 2)
    x0 = max(0, int(W * fx) - src // 2)
    c = np.asarray(arr[y0:y0 + src, x0:x0 + src], dtype=np.float32)
    if f > 1:
        h = (c.shape[0] // f) * f
        w = (c.shape[1] // f) * f
        c = c[:h, :w].reshape(h // f, f, w // f, f).mean((1, 3))
    return c


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-dir", type=Path, required=True)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    spec = gen_e012.make_spec()
    payload_gt = rng(SEED, b"e012/payload").integers(
        0, 2, compose.payload_capacity(spec), dtype=np.uint8)
    cp = compose.compose_page(payload_gt, spec, SEED, page=0)
    assert np.array_equal(
        compose.extract_payload(cp.cell_values, spec, SEED, 0), payload_gt)

    scans = SCANS[:1] if args.quick else SCANS
    report: dict = {"quick": args.quick, "scans": {}, "majority": {}}
    center: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    for name, fname, f, positions in scans:
        path = args.scan_dir / fname
        if not path.exists():
            print(f"{name}: {path} missing — skipped (scans live in the evidence archive; "
                  f"shas in the 012.3 run table)", flush=True)
            continue
        if args.quick:
            positions = positions[:1]
        t0 = time.perf_counter()
        arr = _load(path)
        rows = []
        for i, (fy, fx) in enumerate(positions):
            img = _crop_down(arr, fy, fx, f)
            t1 = time.perf_counter()
            res = acquire.acquire_and_decode(img, spec, SEED)
            dt = time.perf_counter() - t1
            if not res.ok:
                rows.append({"pos": [fy, fx], "ok": False,
                             "failed": res.diagnostics.get("failed_stage")})
                print(f"{name} pos{i} FAIL "
                      f"{res.diagnostics.get('failed_stage')}", flush=True)
                continue
            idx = res.payload_cell_index
            ber = float(np.mean(res.payload_bits != payload_gt[idx]))
            null = float(np.mean(
                res.payload_bits
                != payload_gt[(idx + NULL_STRIDE) % payload_gt.size]))
            rows.append({"pos": [fy, fx], "ok": True,
                         "rot": res.orientation_k,
                         "origin": list(res.cell_origin_abs_yx),
                         "tiles": [res.n_tiles_attempted,
                                   res.n_tiles_decoded],
                         "werr": res.n_word_errors_corrected,
                         "stage_b": round(res.stage_b_match_rate, 4),
                         "payload_ber": round(ber, 5),
                         "null": round(null, 4),
                         "n_bits": int(idx.size),
                         "decode_s": round(dt, 1)})
            print(f"{name} pos{i} ({fy},{fx}): rot{res.orientation_k} "
                  f"tiles {res.n_tiles_decoded}/{res.n_tiles_attempted} "
                  f"werr {res.n_word_errors_corrected}  BER {100*ber:.2f}%  "
                  f"null {null:.3f}  n={idx.size}", flush=True)
            if i == 0:
                center[name] = (idx.copy(), res.payload_bits.copy())
        report["scans"][name] = {"file": str(path), "downsample": f,
                                 "load_s": round(time.perf_counter() - t0, 1),
                                 "positions": rows}

    if len(center) == 3:
        keys = list(center)
        common = center[keys[0]][0]
        for k in keys[1:]:
            common = np.intersect1d(common, center[k][0])
        aligned = {}
        for k in keys:                      # idx sorted -> searchsorted map
            idx, bits = center[k]
            order = np.argsort(idx)
            aligned[k] = bits[order][
                np.searchsorted(idx[order], common)].astype(np.int16)
        maj = (sum(aligned.values()) >= 2).astype(np.uint8)
        ber_m = float(np.mean(maj != payload_gt[common]))
        per = {k: round(float(np.mean(aligned[k].astype(np.uint8)
                                      != payload_gt[common])), 5)
               for k in keys}
        report["majority"] = {"n_common_bits": int(common.size),
                              "per_scan_ber_on_common": per,
                              "majority_ber": round(ber_m, 5)}
        print(f"\nMAJORITY VOTE ({common.size} common bits): per-scan {per} "
              f"-> voted BER {100*ber_m:.3f}%  "
              f"(012.3: loses to best single — print-frozen correlated "
              f"errors; kept as a correlation measurement)", flush=True)

    out = EXP / "build/e012_scan_report.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print(f"\nsaved {out}", flush=True)


if __name__ == "__main__":
    main()
