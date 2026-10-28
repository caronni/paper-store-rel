#!/usr/bin/env python3
"""e016 ARCH-3 hardware decode (run 016.2): Canon scans -> blind
page_decode (ctx + PAVA) -> tile map -> LDPC r0550 CRC certify ->
fountain volume_decode -> data sha vs golden 412b9256... .

Protocol: experiments/016-arch3-c2-volume.md "Decode protocol".
Footing: 4800 dpi scans are pre-decimated 2x2 box-mean to 2400 dpi =
8 px/cell BEFORE page_decode (its full-page float normalize is ~18 GB at
4800; the 2x box mean is the same area averaging the canonical-footing
resample applies going 16 -> 8 px/cell — probe with --quick to compare a
central window through both paths). Windows 300 cells = 25.4 mm (c2 wants
tight windows, 014.1), identification window likewise.

State accumulates across invocations (F6): build/e016_state.pkl. Run the
script again with the next scan file to fold it in; certified tiles are
never demoted. --fresh discards saved state.

Usage:
  env/bin/python decode_e016.py <scan.tiff> [<scan2.tiff> ...]
      [--quick] [--fresh] [--policy best_per_tile] [--report PATH]

GT (report-only, never fed to the receiver) is re-derived through the gen
module (the 012.3 ground-truth rule): gen_e016.make_data ->
fountain.encode_volume_pages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import tifffile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from paperholo import formats, fountain, tilemap  # noqa: E402
import gen_e016  # noqa: E402

BUILD = Path(__file__).resolve().parent / "build"
STATE_PKL = BUILD / "e016_state.pkl"
GOLD_DATA_SHA = ("412b9256829ece06243f16ab0456e4a817b1459d64625f28dd09eae2"
                 "6059bb90")
FMT = next(f for f in formats.FORMAT_REGISTRY if f.format_id == "e016-v3-c2")
WINDOW_CELLS = 300           # 25.4 mm at c2 — the measured-safe window size
OVERLAP_CELLS = 60
ID_WINDOW_PX = WINDOW_CELLS * 8   # identify on the same 25.4 mm footprint


def load_scan_2400(path: Path) -> tuple[np.ndarray, float]:
    """Raw Canon tiff -> float32 grey at 2400 dpi equivalent (8 px/cell).

    Accepts 4800 dpi (2x2 box mean) or native 2400 (pass-through). uint16
    input is fine — means are taken with a float32 accumulator; absolute
    level does not matter downstream (acquire normalizes reflectance).
    """
    img = tifffile.imread(str(path))
    if img.ndim == 3:
        img = img.mean(axis=2, dtype=np.float32)
    h, w = img.shape
    # decide 4800 vs 2400 by pixel count against the A4-ish page area
    long_side_in = max(h, w) / 4800.0
    if long_side_in > 8.0:            # plausibly a 4800 dpi page scan
        dec = img[: h // 2 * 2, : w // 2 * 2].reshape(
            h // 2, 2, w // 2, 2).mean(axis=(1, 3), dtype=np.float32)
        return dec, 2400.0
    return np.asarray(img, np.float32), 2400.0


def scan_report(state: tilemap.PageDecodeState, scan_id: str,
                gt_payload: np.ndarray) -> dict:
    """Report-only per-scan stats vs gen-module GT (llr>0 == bit 1;
    overlap cells appear multiple times in the raw observation — the BER
    is over raw samples, duplicates included, and says so)."""
    obs = state.scans[scan_id]
    llr = obs.payload_llr
    idx = obs.payload_cell_index
    measured = llr != 0.0
    hard = (llr > 0).astype(np.uint8)
    ber = float(np.mean(hard[measured] != gt_payload[idx[measured]]))
    return {"scan_id": scan_id,
            "n_windows": int(obs.n_windows),
            "pilot_ber_est": float(obs.pilot_ber_est),
            "n_obs_samples": int(idx.size),
            "n_cells_covered": int(np.unique(idx).size),
            "erasure_frac": float(np.mean(~measured)),
            "detection_ber_vs_gt": ber}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scans", nargs="+", type=Path)
    ap.add_argument("--quick", action="store_true",
                    help="one central 25.4 mm window per scan, no state")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--align", action="store_true",
                    help="align window grid to the printed field bbox")
    ap.add_argument("--mirror-pad", type=int, default=0, metavar="CELLS",
                    help="mirror this many cells of field content into "
                         "the margins post-scan (implies --align)")
    ap.add_argument("--policy", default="best_per_tile",
                    choices=tilemap.PageDecodeState._POLICIES)
    ap.add_argument("--state", type=Path, default=STATE_PKL)
    ap.add_argument("--report", type=Path,
                    default=BUILD / "e016_scan_report.json")
    args = ap.parse_args()

    t0 = time.time()
    vspec = gen_e016.make_vspec()
    data_gt = gen_e016.make_data(vspec)
    assert hashlib.sha256(data_gt).hexdigest() == GOLD_DATA_SHA
    framed = fountain.encode_volume_pages(data_gt, vspec)[0]
    gt_payload = np.asarray(framed["payload_bits"], np.uint8)
    print(f"[{time.time()-t0:6.1f}s] GT re-derived via gen module "
          f"({vspec.k_total}+{vspec.n_symbols_total - vspec.k_total} "
          f"symbols x {vspec.symbol_bits} bits)")

    if args.quick:
        for p in args.scans:
            img, dpi = load_scan_2400(p)
            h, w = img.shape
            s = WINDOW_CELLS * 8
            win = np.ascontiguousarray(
                img[(h - s) // 2:(h + s) // 2, (w - s) // 2:(w + s) // 2])
            r = formats.acquire_scan(win, candidates=[FMT], scan_dpi=dpi,
                                     detector="ctx", calibrate=True)
            if not r.ok:
                print(f"QUICK {p.name}: FAILED {r.tried} "
                      f"{r.diagnostics.get('failed_stage')}")
                continue
            res = r.result
            m = res.payload_llr != 0.0
            hard = (res.payload_llr > 0).astype(np.uint8)
            ber = float(np.mean(
                hard[m] != gt_payload[res.payload_cell_index[m]]))
            print(f"QUICK {p.name}: ok fmt={r.fmt.format_id} "
                  f"pitch={r.pitch_hyp_px:.3f}px "
                  f"words={sum(1 for v in res.tile_words.values() if v >= 0)}"
                  f"/{len(res.tile_words)} "
                  f"payload BER {100*ber:.2f}% on "
                  f"{int(m.sum())} cells geomY={r.geometry_confirmed}")
        return 0

    state: tilemap.PageDecodeState | None = None
    if args.state.exists() and not args.fresh:
        state = pickle.loads(args.state.read_bytes())
        print(f"resumed state: {state.summary()}")

    report: dict = {"scans": [], "format": FMT.format_id,
                    "window_cells": WINDOW_CELLS,
                    "overlap_cells": OVERLAP_CELLS, "policy": args.policy,
                    "align": bool(args.align or args.mirror_pad),
                    "mirror_pad_cells": args.mirror_pad}
    for p in args.scans:
        scan_id = p.stem
        if state is not None and scan_id in state.scans:
            print(f"scan {scan_id} already folded in — skipping")
            continue
        sha = hashlib.sha256(p.read_bytes()).hexdigest()
        img, dpi = load_scan_2400(p)
        print(f"[{time.time()-t0:6.1f}s] {scan_id}: {img.shape} "
              f"@{dpi:.0f}dpi sha {sha[:12]}…")
        ident, state = formats.page_decode(
            img, scan_id=scan_id, state=state, candidates=[FMT],
            scan_dpi=dpi, window_cells=WINDOW_CELLS,
            overlap_cells=OVERLAP_CELLS, id_window_px=ID_WINDOW_PX,
            align_to_field=args.align or args.mirror_pad > 0,
            mirror_pad_cells=args.mirror_pad,
            detector="ctx", calibrate=True)
        if "field_bbox_px" in ident.diagnostics:
            print(f"  field bbox: {ident.diagnostics['field_bbox_px']}"
                  + (f" padded -> "
                     f"{ident.diagnostics.get('field_bbox_padded_px')}"
                     if args.mirror_pad else ""))
        if not ident.ok:
            print(f"  IDENTIFICATION FAILED: {ident.tried} "
                  f"{ident.diagnostics.get('failed_stage')}")
            report["scans"].append({"scan_id": scan_id, "sha256": sha,
                                    "ok": False,
                                    "tried": ident.tried})
            continue
        sr = scan_report(state, scan_id, gt_payload)
        sr.update(sha256=sha, ok=True,
                  n_windows_ok=ident.diagnostics.get("n_windows_ok"),
                  n_windows_tried=ident.diagnostics.get("n_windows_tried"))
        report["scans"].append(sr)
        print(f"  [{time.time()-t0:6.1f}s] windows "
              f"{sr['n_windows_ok']}/{sr['n_windows_tried']} ok; "
              f"detection BER {100*sr['detection_ber_vs_gt']:.2f}% "
              f"(pilot est {100*sr['pilot_ber_est']:.2f}%), "
              f"coverage {sr['n_cells_covered']} cells")

        counts = state.decode_tiles("r0550", policy=args.policy)
        print(f"  [{time.time()-t0:6.1f}s] decode_tiles({args.policy}): "
              f"{counts}")
        print(f"  map: {state.summary()}")
        ask, why = state.more_scans_useful()
        print(f"  more_scans_useful: {ask} — {why}")

    if state is None:
        print("no evidence — nothing to decode")
        return 1

    syms = fountain.tiles_to_symbols(state.certified_results(), vspec)
    data_out, diag = fountain.volume_decode(syms, vspec)
    solved = len(diag.get("solved_blocks", []))
    report["tiles"] = state.summary()
    report["fountain"] = {"n_symbols_received": diag["n_symbols_received"],
                          "solved_blocks": solved,
                          "n_blocks": diag["n_blocks"]}
    wanted = tilemap.volume_scans_wanted({0: state}, vspec)
    report["volume_scans_wanted"] = [
        {"page": pg, **info} for pg, info in wanted]
    if data_out is not None:
        sha_out = hashlib.sha256(data_out).hexdigest()
        report["data_sha256"] = sha_out
        report["byte_exact"] = bool(sha_out == GOLD_DATA_SHA)
        print(f"\nVOLUME DECODED: {len(data_out)} bytes, sha {sha_out}")
        print("BYTE-EXACT MATCH" if report["byte_exact"] else
              "*** SHA MISMATCH — investigate before logging ***")
    else:
        report["byte_exact"] = False
        need = [(b["block"], b["needed"] - b["rank"])
                for b in diag["blocks"] if not b["solved"]]
        report["blocks_underranked"] = need
        print(f"\nvolume NOT yet decoded: {solved}/{diag['n_blocks']} "
              f"blocks solved; deficits {need[:10]}"
              f"{'…' if len(need) > 10 else ''}")
        print(f"volume_scans_wanted: {report['volume_scans_wanted']}")

    BUILD.mkdir(parents=True, exist_ok=True)
    args.state.write_bytes(pickle.dumps(state))
    args.report.write_text(json.dumps(report, indent=2))
    print(f"[{time.time()-t0:6.1f}s] state -> {args.state.name}, "
          f"report -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
