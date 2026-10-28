#!/usr/bin/env python3
"""Experiment 013 — the first DECODED-BITS measurements (Layer 3, zero print).

Everything before this experiment was an MI proxy; here user bits go through
ldpc.encode_page -> compose_page (layout_version 3) -> the measured channel
-> the fully blind receiver -> per-tile LDPC decode -> CRC-32 certification,
and only CRC-certified user bits are counted.

Measurements (full mode ~10 min; --quick ~1 min):
  1. rate ladder: per LDPC_LADDER rate, page-class 600x600-cell interior
     windows, print seeds {0,1,2}, geometry=True blind vs geometry=False
     footing (same detector+pipeline): certified-tile BLER, mean iters,
     NET certified user density b/mm^2 (window area includes pilots).
  2. erasure/fragment curve at r0700 + r0550: partial-coverage tiles from a
     clipped fragment, success per coverage bin (PILOTS-DESIGN section 14's
     middle regime, quantified at the FEC level).
  3. F9 control: decode under a corrupted payload-index hypothesis -> zero
     certifications required; plus a global wrong-payload-certification
     count across every decode in the run (must be 0).
  4. multi-scan: adversarial print seed 314, 3 scans, LLR summation on
     absolute payload indices vs single-scan decode.

Writes build/e013_report.json. Deterministic modulo *_s timing fields.
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

from paperholo import acquire, compose, ldpc  # noqa: E402
from paperholo.channel import ChannelParams, print_plane, scan_plane  # noqa: E402
from paperholo.compose import ComposeSpec, compose_page  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402

SEED = b"paper-store/exp013"
BUILD = EXP / "build"

WIN_CELL_YX = (810, 450)          # e011/e012 footing-window convention
WIN_CELLS = 600
CELL = 3
MM_PER_DOT = 25.4 / 600.0

# fragment for the erasure bins: straddles tile boundaries on purpose
FRAG_CELL_YX = (823, 463)
FRAG_CELLS = 220


def make_spec() -> ComposeSpec:
    return ComposeSpec(layout_version=3, pilot=PilotLayout(version=3))


def build_page(spec: ComposeSpec, rate_id: str) -> tuple[np.ndarray, dict]:
    """Compose one full page whose payload is LDPC-framed user bits."""
    ls = ldpc.LDPC_LADDER[rate_id]
    cap = ldpc.page_user_capacity(spec, SEED, ls)
    user = rng(SEED, b"e013/user/" + rate_id.encode()).integers(
        0, 2, cap).astype(np.uint8)
    framed = ldpc.encode_page(user, spec, SEED, ls)
    page = compose_page(framed["payload_bits"], spec, SEED, page=0)
    return page.plane_bits, {"user": user, "framed": framed, "ls": ls,
                             "user_capacity_bits": int(cap)}


def window_scan(plane_bits: np.ndarray, print_seed: int, *,
                geometry: bool, cell_yx=WIN_CELL_YX, cells=WIN_CELLS,
                scan_seed: int | None = None) -> np.ndarray:
    y0, x0 = cell_yx[0] * CELL, cell_yx[1] * CELL
    n = cells * CELL
    win = plane_bits[y0:y0 + n, x0:x0 + n]
    p = ChannelParams(seed=print_seed, geometry=geometry,
                      scan_seed=scan_seed)
    return scan_plane(print_plane(win, p), p)


def certified_tiles(res, spec, ls, *, min_coverage=0.999):
    """Blind AcquireResult -> per-tile decode of complete tiles only."""
    if not res.ok:
        return []
    return ldpc.decode_page_tiles(res.payload_llr, res.payload_cell_index,
                                  spec, SEED, ls, min_coverage=min_coverage)


def check_certified(results, ctx: dict, user: np.ndarray, framed: dict):
    """F9 global control: every certified payload must equal GT exactly."""
    per_tile = {tuple(t["tile_yx"]): t for t in framed["per_tile"]}
    for r in results:
        if not r.ok:
            continue
        t = per_tile[tuple(r.tile_yx)]
        gt = user[t["user_offset"]:t["user_offset"] + t["user_bits"]]
        if not np.array_equal(r.payload_bits, gt):
            ctx["wrong_payload_certifications"] += 1


def rate_ladder(spec, rate_ids, print_seeds, ctx, quick=False) -> list[dict]:
    out = []
    area_mm2 = (WIN_CELLS * CELL * MM_PER_DOT) ** 2
    for rid in rate_ids:
        plane_bits, page = build_page(spec, rid)
        row = {"rate_id": rid, "rate": ldpc.LDPC_LADDER[rid].rate,
               "page_user_capacity_bits": page["user_capacity_bits"],
               "seeds": []}
        for ps in print_seeds:
            entry = {"print_seed": ps}
            for geom, tag in ((True, "blind"), (False, "footing")):
                scan = window_scan(plane_bits, ps, geometry=geom)
                res = acquire.acquire_and_decode(scan, spec, SEED)
                tiles = certified_tiles(res, spec, page["ls"])
                check_certified(tiles, ctx, page["user"], page["framed"])
                n = len(tiles)
                n_ok = sum(t.ok for t in tiles)
                bits = sum(t.payload_bits.size for t in tiles if t.ok)
                entry[tag] = {
                    "acquire_ok": bool(res.ok), "n_tiles": n, "n_ok": n_ok,
                    "tile_bler": (1.0 - n_ok / n) if n else None,
                    "mean_iters": (float(np.mean([t.n_iters for t in tiles]))
                                   if tiles else None),
                    "certified_user_bits": int(bits),
                    "net_b_per_mm2": bits / area_mm2,
                }
            row["seeds"].append(entry)
        out.append(row)
        b = [s["blind"] for s in row["seeds"]]
        print(f"  {rid} (R={row['rate']:.3f}): blind tiles "
              f"{sum(x['n_ok'] for x in b)}/{sum(x['n_tiles'] for x in b)}"
              f" ok, net {np.mean([x['net_b_per_mm2'] for x in b]):.1f}"
              f" b/mm2 | footing "
              f"{sum(s['footing']['n_ok'] for s in row['seeds'])}"
              f"/{sum(s['footing']['n_tiles'] for s in row['seeds'])}")
    return out


def erasure_bins(spec, rate_ids, ctx) -> list[dict]:
    """Partial-coverage tiles from a clipped fragment; success per bin."""
    bins = [(0.95, 1.01), (0.70, 0.95), (0.50, 0.70), (0.30, 0.50)]
    out = []
    for rid in rate_ids:
        plane_bits, page = build_page(spec, rid)
        scan = window_scan(plane_bits, 7, geometry=True,
                           cell_yx=FRAG_CELL_YX, cells=FRAG_CELLS)
        res = acquire.acquire_and_decode(scan, spec, SEED)
        row = {"rate_id": rid, "acquire_ok": bool(res.ok), "bins": []}
        if res.ok:
            for tile in ldpc.tile_grid(spec.page_cells_yx):
                llr, mask, cov = ldpc.gather_tile_llrs(
                    res.payload_llr, res.payload_cell_index, spec, SEED, tile)
                if cov <= 0.0:
                    continue
                r = ldpc.decode_tile(llr, mask, page["ls"], tile_yx=tile)
                check_certified([r], ctx, page["user"], page["framed"])
                row["bins"].append({"tile_yx": list(tile),
                                    "coverage": round(cov, 3),
                                    "ok": bool(r.ok)})
            summary = []
            for lo, hi in bins:
                sel = [b for b in row["bins"] if lo <= b["coverage"] < hi]
                summary.append({"bin": f"[{lo},{hi})", "n": len(sel),
                                "n_ok": sum(b["ok"] for b in sel)})
            row["summary"] = summary
            print(f"  {rid} fragment: " + "  ".join(
                f"{s['bin']}:{s['n_ok']}/{s['n']}" for s in summary))
        out.append(row)
    return out


def f9_wrong_address(spec, ctx) -> dict:
    """Corrupt the payload-index hypothesis; nothing may certify."""
    rid = "r0700"
    plane_bits, page = build_page(spec, rid)
    scan = window_scan(plane_bits, 0, geometry=True)
    res = acquire.acquire_and_decode(scan, spec, SEED)
    assert res.ok
    bad_idx = res.payload_cell_index + 3            # coherent mis-addressing
    cap = compose.payload_capacity(spec)
    keep = bad_idx < cap
    tiles = ldpc.decode_page_tiles(res.payload_llr[keep], bad_idx[keep],
                                   spec, SEED, ldpc.LDPC_LADDER[rid],
                                   min_coverage=0.999)
    n_cert = sum(t.ok for t in tiles)
    print(f"  F9 wrong-address: {n_cert}/{len(tiles)} certified "
          f"(must be 0)")
    return {"n_tiles": len(tiles), "n_certified": int(n_cert)}


def multiscan(spec, ctx) -> dict:
    """Adversarial print seed 314: LLR summation across 3 re-scans."""
    rid = "r0700"
    plane_bits, page = build_page(spec, rid)
    ls = page["ls"]
    cap = compose.payload_capacity(spec)
    acc = np.zeros(cap)
    npz = np.zeros(cap, np.int32)
    singles = []
    for k, ss in enumerate((1, 2, 3)):
        scan = window_scan(plane_bits, 314, geometry=True, scan_seed=ss)
        res = acquire.acquire_and_decode(scan, spec, SEED)
        tiles = certified_tiles(res, spec, ls)
        check_certified(tiles, ctx, page["user"], page["framed"])
        singles.append({"scan_seed": ss, "acquire_ok": bool(res.ok),
                        "n_tiles": len(tiles),
                        "n_ok": sum(t.ok for t in tiles)})
        if res.ok:
            acc[res.payload_cell_index] += res.payload_llr
            npz[res.payload_cell_index] += 1
    idx = np.flatnonzero(npz > 0)
    tiles = ldpc.decode_page_tiles(acc[idx], idx, spec, SEED, ls,
                                   min_coverage=0.999)
    check_certified(tiles, ctx, page["user"], page["framed"])
    combined = {"n_tiles": len(tiles), "n_ok": sum(t.ok for t in tiles)}
    print(f"  multiscan 314: singles "
          + " ".join(f"{s['n_ok']}/{s['n_tiles']}" for s in singles)
          + f" -> 3-scan LLR-sum {combined['n_ok']}/{combined['n_tiles']}")
    return {"singles": singles, "combined_llr_sum": combined}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    BUILD.mkdir(exist_ok=True)
    spec = make_spec()
    ctx = {"wrong_payload_certifications": 0}
    rate_ids = ["r0700"] if args.quick else list(ldpc.LDPC_LADDER)
    seeds = [0] if args.quick else [0, 1, 2]

    print("rate ladder (blind vs footing):")
    ladder = rate_ladder(spec, rate_ids, seeds, ctx, quick=args.quick)
    print("erasure/fragment bins:")
    eras = erasure_bins(spec, ["r0700"] if args.quick else ["r0700", "r0550"],
                        ctx)
    print("F9 controls:")
    f9 = f9_wrong_address(spec, ctx)
    ms = None
    if not args.quick:
        print("multi-scan:")
        ms = multiscan(spec, ctx)

    report = {
        "experiment": "013-ldpc-roundtrip", "seed": SEED.decode(),
        "layout_version": 3, "quick": bool(args.quick),
        "window": {"cell_yx": list(WIN_CELL_YX), "cells": WIN_CELLS},
        "rate_ladder": ladder, "erasure_bins": eras,
        "f9_wrong_address": f9, "multiscan": ms,
        "wrong_payload_certifications": ctx["wrong_payload_certifications"],
        "elapsed_s": round(time.time() - t0, 1),
    }
    out = BUILD / "e013_report.json"
    out.write_text(json.dumps(report, indent=1))
    print(f"wrong-payload certifications: "
          f"{ctx['wrong_payload_certifications']} (must be 0)")
    print(f"wrote {out} ({report['elapsed_s']} s)")
    return 0 if ctx["wrong_payload_certifications"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
