#!/usr/bin/env python3
"""Experiment 015 — the R2 f-sweep: multi-page volume recovery vs area
fraction (Layer 4 fountain, sim, zero print).

An 8-page layout_version-3 volume (600x600-cell pages, r0550 fragment rung,
fill ~55%) is simulated page by page (geometry=True, distinct print/scan
seeds), then sampled as disjoint 200x200-cell fragment slots (3x3 per page,
72 total, each independently rot90'd and acquired FULLY BLIND). The sweep
selects random slot subsets of total area fraction f and asks: does the
volume decode EXACTLY?

R2 arithmetic under test: K/N = k_total/n_symbols; predicted threshold
f* ~ (K/N) / (symbol yield per unit area). Also: whole-pages-lost variant,
GE overhead at volume scale, and a global F9 wrong-certification counter.

Writes build/e015_report.json. Deterministic modulo *_s timings.
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

from paperholo import acquire, compose, fountain, ldpc  # noqa: E402
from paperholo.channel import ChannelParams, print_plane, scan_plane  # noqa: E402
from paperholo.compose import ComposeSpec  # noqa: E402
from paperholo.modulation import rng  # noqa: E402
from paperholo.pilots import PilotLayout  # noqa: E402

SEED = b"paper-store/exp015"
ASEED = b"paper-store/exp015-analysis"
BUILD = EXP / "build"

N_PAGES = 8
PAGE_CELLS = (600, 600)
RATE_ID = "r0550"                  # the fragment rung (013/F4)
FILL = 0.55                        # data / source capacity
SLOTS_PER_AXIS = 3                 # 3x3 slots of 200x200 cells per page
CELL_PX = 6                        # c3 at 2 px/dot


def make_vspec() -> fountain.VolumeSpec:
    cs = ComposeSpec(layout_version=3, pilot=PilotLayout(version=3),
                     page_cells_yx=PAGE_CELLS)
    probe = fountain.VolumeSpec(n_pages=N_PAGES, data_len_bytes=1,
                                seed=SEED, ldpc_rate_id=RATE_ID,
                                compose_spec=cs)
    data_len = int(probe.source_capacity_bits * FILL) // 8
    return fountain.VolumeSpec(n_pages=N_PAGES, data_len_bytes=data_len,
                               seed=SEED, ldpc_rate_id=RATE_ID,
                               compose_spec=cs)


def build_and_scan(vspec) -> tuple[bytes, list[np.ndarray], list[dict]]:
    """Encode the volume, compose + sim-scan every page."""
    data = bytes(rng(SEED, b"e015/data").integers(
        0, 256, vspec.data_len_bytes).astype(np.uint8))
    enc = fountain.volume_encode(data, vspec)
    scans, gt = [], []
    for p in range(vspec.n_pages):
        le = ldpc.encode_page(enc.page_user_bits[p], vspec.compose_spec,
                              SEED, vspec.ldpc_spec)
        page = compose.compose_page(le["payload_bits"], vspec.compose_spec,
                                    SEED, page=p)
        cp = ChannelParams(seed=500 + p, geometry=True, scan_seed=600 + p)
        scans.append(scan_plane(print_plane(page.plane_bits, cp), cp))
        gt.append(le)
    return data, scans, gt


def acquire_slots(vspec, scans, gt, ctx) -> list[dict]:
    """Blind-acquire every fragment slot once (cached across trials)."""
    slots = []
    n_cells = PAGE_CELLS[0] // SLOTS_PER_AXIS
    n_px = n_cells * CELL_PX
    sel = rng(ASEED, b"slot-rot")
    for p in range(vspec.n_pages):
        for sy in range(SLOTS_PER_AXIS):
            for sx in range(SLOTS_PER_AXIS):
                frag = scans[p][sy * n_px:(sy + 1) * n_px,
                                sx * n_px:(sx + 1) * n_px]
                k = int(sel.integers(0, 4))
                res = acquire.acquire_and_decode(np.rot90(frag, k),
                                                 vspec.compose_spec, SEED)
                entry = {"page": p, "slot": (sy, sx), "rot": k,
                         "ok": bool(res.ok), "tiles": []}
                if res.ok:
                    tiles = ldpc.decode_page_tiles(
                        res.payload_llr, res.payload_cell_index,
                        vspec.compose_spec, SEED, vspec.ldpc_spec,
                        min_coverage=0.3)
                    for t in tiles:
                        if t.ok:
                            exp_tile = next(
                                e for e in gt[res.page]["per_tile"]
                                if tuple(e["tile_yx"]) == tuple(t.tile_yx))
                            o = exp_tile["user_offset"]
                            nb = exp_tile["user_bits"]
                            if not np.array_equal(
                                    t.payload_bits,
                                    _user_cache[res.page][o:o + nb]):
                                ctx["wrong_certifications"] += 1
                    entry["tiles"] = [(res.page, t) for t in tiles if t.ok]
                slots.append(entry)
    return slots


_user_cache: dict = {}


def f_sweep(vspec, slots, data, n_trials: int, ladder) -> list[dict]:
    out = []
    usable = slots
    for n_sel in ladder:
        wins = 0
        recovered = []
        for t in range(n_trials):
            g = rng(ASEED, b"trial/%d/%d" % (n_sel, t))
            idx = g.permutation(len(usable))[:n_sel]
            pool = []
            for i in idx:
                pool.extend(usable[i]["tiles"])
            syms = fountain.tiles_to_symbols(pool, vspec)
            got, diag = fountain.volume_decode(syms, vspec)
            recovered.append(len(syms))
            if got == data:
                wins += 1
        out.append({"n_slots": n_sel, "f": round(n_sel / len(usable), 3),
                    "success": wins / n_trials,
                    "median_symbols": int(np.median(recovered)),
                    "k_needed": vspec.k_total})
        print(f"  f={n_sel / len(usable):.2f} ({n_sel}/{len(usable)} slots): "
              f"success {wins}/{n_trials}, median symbols "
              f"{int(np.median(recovered))}/{vspec.k_total} needed")
    return out


def lost_pages(vspec, slots, data) -> list[dict]:
    out = []
    for keep in range(vspec.n_pages, 2, -1):
        pool = []
        for s in slots:
            if s["page"] < keep:
                pool.extend(s["tiles"])
        syms = fountain.tiles_to_symbols(pool, vspec)
        got, diag = fountain.volume_decode(syms, vspec)
        ok = got == data
        out.append({"pages_kept": keep, "symbols": len(syms),
                    "success": bool(ok)})
        print(f"  pages 0..{keep - 1} only: {len(syms)} symbols -> "
              f"{'EXACT' if ok else 'insufficient'}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    BUILD.mkdir(parents=True, exist_ok=True)
    vspec = make_vspec()
    print(f"volume: {vspec.n_pages} pages, K={vspec.k_total}/"
          f"{vspec.n_symbols_total} symbols (K/N="
          f"{vspec.k_total / vspec.n_symbols_total:.3f}), S={vspec.symbol_bits}"
          f" bits, data {vspec.data_len_bytes:,} B")
    data, scans, gt = build_and_scan(vspec)
    # per-page user bits for the F9 cross-check
    enc = fountain.volume_encode(data, vspec)
    for p in range(vspec.n_pages):
        _user_cache[p] = enc.page_user_bits[p]

    ctx = {"wrong_certifications": 0}
    print("acquiring 72 fragment slots (blind, cached)...")
    slots = acquire_slots(vspec, scans, gt, ctx)
    n_ok = sum(s["ok"] for s in slots)
    n_sym = sum(len(s["tiles"]) for s in slots)
    pool_all = [t for s in slots for t in s["tiles"]]
    n_unique = len(fountain.tiles_to_symbols(pool_all, vspec))
    print(f"  slots acquired {n_ok}/{len(slots)}; certified tile results "
          f"{n_sym} (incl. straddle duplicates), UNIQUE symbols "
          f"{n_unique}/{vspec.n_symbols_total} printed")

    ladder = [32, 36, 40, 44, 48, 56, 64, 72] if not args.quick else [44, 72]
    trials = 8 if args.quick else 25
    print(f"f-sweep ({trials} trials/point):")
    sweep = f_sweep(vspec, slots, data, trials, ladder)
    print("lost-pages variant:")
    lp = lost_pages(vspec, slots, data)

    report = {
        "experiment": "015-volume-fsweep", "seed": SEED.decode(),
        "volume": {"n_pages": vspec.n_pages, "page_cells": PAGE_CELLS,
                   "rate_id": RATE_ID, "k_total": vspec.k_total,
                   "n_symbols": vspec.n_symbols_total,
                   "kn": vspec.k_total / vspec.n_symbols_total,
                   "symbol_bits": vspec.symbol_bits,
                   "data_len_bytes": vspec.data_len_bytes},
        "slots": {"total": len(slots), "acquired": n_ok,
                  "certified_symbols": n_sym},
        "f_sweep": sweep, "lost_pages": lp,
        "wrong_certifications": ctx["wrong_certifications"],
        "elapsed_s": round(time.time() - t0, 1),
    }
    (BUILD / "e015_report.json").write_text(json.dumps(report, indent=1))
    print(f"wrong certifications: {ctx['wrong_certifications']} (must be 0)")
    print(f"wrote build/e015_report.json ({report['elapsed_s']} s)")
    return 0 if ctx["wrong_certifications"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
