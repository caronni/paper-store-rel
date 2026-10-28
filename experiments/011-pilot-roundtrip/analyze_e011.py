#!/usr/bin/env python
"""E011 measurement harness — M1 pilot-system round-trip on the measured
simulator (run 011.1, zero print).

Stages (all downstream sims consume windows of the RIP OUTPUT page_bits, never
the in-memory composed array — that is the point of the experiment):

1. RIP gate ("gs as printer"): render build/e011.ps via gs pnggray -r600, crop
   the manifest field rect, threshold < 128 -> page_bits; assert page_bits ==
   the GT npy EXACTLY (pixel diff must be 0; gs does not screen).
2. Footing gap: one 600x600-cell window at a fixed interior position, print
   seeds {0,1,2}: (a) geometry=False print_scan + aligned-grid blind detect
   (lock_grid -> sample_cell_means -> cell_bits_blind, the SAME detector the
   blind pipeline uses) -> footing BER vs the RIP cell grid; (b) geometry=True
   print_scan of the SAME window (same print seed, scan_seed=seed+1) through
   the full blind acquire_and_decode -> payload BER + null control.
3. Fragment grain curve: sizes {10,13,16,20,25,40,60} mm square, 8 trials each
   (random interior dot offset + random rot90, print seed = trial index,
   geometry=True). Success = ok AND orientation AND origin correct. Sizes
   below the addressing grain (a full 60-cell tile must fit: guaranteed only
   from 119 cells = 15.1 mm) are EXPECTED to fail at chance-of-placement rates
   — measured, not forced.
4. Extras: pilot-overhead accounting; R3 spot check (power spectrum of the RIP
   cell grid at the 1/60 cyc/cell site-pattern line and the 1/6 block line vs
   median background — the conceded §10.2 structure); multi-scan probe (print
   seed 314 = the adversarial fast-warp seed, 1 vs 3 scan_seeds, per-scan
   acquire + majority vote on absolute payload indices).

Writes build/e011_report.json + a human table. Deterministic given its inputs
(the *_s timing fields are the only wall-clock values; they are rounded and
informational). Runs from experiments/011-pilot-roundtrip/:

  ../../env/bin/python analyze_e011.py [--quick]

--quick: 2 trials/size, footing seed {0} only, multi-scan probe skipped
(CI-speed smoke; the report records quick=true).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

EXP = Path(__file__).resolve().parent
ROOT = EXP.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))
Image.MAX_IMAGE_PIXELS = None

from paperholo import acquire, compose  # noqa: E402
from paperholo.channel import (ChannelParams, print_plane, print_scan,  # noqa: E402
                               scan_plane)
from paperholo.modulation import rng  # noqa: E402

import gen_e011  # noqa: E402

SEED = gen_e011.SEED                       # format seed (page under test)
ASEED = b"paper-store/exp011-analysis"     # analysis-side placement draws
BUILD = EXP / "build"
CELL_DOTS = 3
FOOT_ORIGIN_CELLS = (810, 450)             # fixed interior, cell-aligned
FOOT_CELLS = 600
FOOT_PRINT_SEEDS = (0, 1, 2)
GRAIN_SIZES_MM = (10.0, 13.0, 16.0, 20.0, 25.0, 40.0, 60.0)
N_TRIALS_FULL = 8
BORDER_CELLS = 4                           # footing-BER border crop (wave-1 idiom)
NULL_STRIDE = 7919                         # null-control index shift (test idiom)
MULTISCAN_PRINT_SEED = 314                 # adversarial fast-warp seed (Stage-0
                                           # known limitation, wave-1 stage0)


def _fmt_pct(x: float) -> str:
    return f"{100.0 * x:.2f}%" if np.isfinite(x) else "--"


# ---------------------------------------------------------------------------
# 1. RIP gate
# ---------------------------------------------------------------------------

def rip_gate() -> tuple[dict, np.ndarray, np.ndarray, np.ndarray,
                        compose.ComposeSpec]:
    """gs-as-printer: render, crop, threshold, compare EXACTLY to the GT npy.
    Returns (report block, page_bits, cells, payload_gt, spec)."""
    if not (BUILD / "e011.ps").exists():
        print("build/e011.ps missing -> running gen_e011.py", flush=True)
        r = subprocess.run([sys.executable, str(EXP / "gen_e011.py")],
                           capture_output=True, text=True, timeout=600,
                           cwd=str(EXP))
        assert r.returncode == 0, f"gen_e011.py failed:\n{r.stdout}\n{r.stderr}"
    mf = json.loads((BUILD / "e011_manifest.json").read_text())
    import hashlib
    ps_sha = hashlib.sha256((BUILD / "e011.ps").read_bytes()).hexdigest()
    assert ps_sha == mf["ps_sha256"], "e011.ps does not match its manifest sha"

    png = BUILD / "e011_render600.png"
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                    "-sDEVICE=pnggray", "-r600", "-o", str(png),
                    str(BUILD / "e011.ps")], check=True, timeout=600)
    img = np.asarray(Image.open(png).convert("L"))
    (e,) = [p for p in mf["patches"] if p["name"] == "e011_field"]
    x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
    page_bits = (img[y:y + h, x:x + w] < 128).astype(np.uint8)

    gt = np.load(BUILD / e["gt"])
    assert page_bits.shape == gt.shape
    ndiff = int((page_bits != gt).sum())
    assert ndiff == 0, f"RIP gate FAILED: render != GT at {ndiff} dots"

    spec = compose.ComposeSpec()
    assert page_bits.shape == spec.field_dots_yx
    cells = page_bits[::CELL_DOTS, ::CELL_DOTS]
    # every cell must be a solid cell_dots^2 block (kcell-c3 constellation)
    assert np.array_equal(
        np.kron(cells, np.ones((CELL_DOTS, CELL_DOTS), np.uint8)), page_bits)
    # payload GT derived from the RIP output (not the composer's memory)
    payload_gt = compose.extract_payload(cells, spec, SEED, 0)
    block = {"ps_sha256": ps_sha, "jobid": mf["jobid"],
             "pixel_diff_vs_gt": ndiff,
             "field_dots_yx": [int(h), int(w)],
             "page_cells_yx": list(spec.page_cells_yx),
             "payload_capacity_bits": int(payload_gt.size)}
    print(f"RIP gate OK: sha {ps_sha[:16]}.. pixel diff {ndiff}, "
          f"{payload_gt.size} payload bits recovered from render", flush=True)
    return block, page_bits, cells, payload_gt, spec


# ---------------------------------------------------------------------------
# 2. Footing gap
# ---------------------------------------------------------------------------

def _aligned_footing_ber(det: np.ndarray, gt_win: np.ndarray,
                         mask_win: np.ndarray) -> dict:
    """Detected-vs-GT cell BER at the best +-1-cell shift (the lock's local
    cell 0 is legitimately phase-ambiguous at fragment corners; wave-1 stage0
    shift-aligned idiom), 4-cell border crop."""
    best: tuple | None = None
    hd, wd = det.shape
    hg, wg = gt_win.shape
    b = BORDER_CELLS
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            i0, i1 = max(0, -dy) + b, min(hd, hg - dy) - b
            j0, j1 = max(0, -dx) + b, min(wd, wg - dx) - b
            if i1 <= i0 or j1 <= j0:
                continue
            d = det[i0:i1, j0:j1]
            g = gt_win[i0 + dy:i1 + dy, j0 + dx:j1 + dx]
            err = d != g
            ber = float(err.mean())
            if best is None or ber < best[0]:
                m = mask_win[i0 + dy:i1 + dy, j0 + dx:j1 + dx]
                best = (ber, float(err[~m].mean()), (dy, dx), int(err.size))
    assert best is not None
    return {"ber_all": best[0], "ber_nonpilot": best[1],
            "shift_cells_yx": list(best[2]), "n_cells": best[3]}


def footing_gap(page_bits: np.ndarray, cells: np.ndarray,
                payload_gt: np.ndarray, spec: compose.ComposeSpec,
                print_seeds: tuple[int, ...]) -> dict:
    oy, ox = FOOT_ORIGIN_CELLS
    n = FOOT_CELLS
    crop = page_bits[oy * CELL_DOTS:(oy + n) * CELL_DOTS,
                     ox * CELL_DOTS:(ox + n) * CELL_DOTS]
    gt_win = cells[oy:oy + n, ox:ox + n]
    mask_win = compose._pilot_site_mask(spec.page_cells_yx, spec.pilot,
                                        SEED)[oy:oy + n, ox:ox + n]
    per_seed = []
    for s in print_seeds:
        # (a) geometry=False footing: same blind detector, aligned grid
        t0 = time.perf_counter()
        scan_f = print_scan(crop, ChannelParams(seed=s, scan_seed=s + 1,
                                                geometry=False))
        grid = acquire.lock_grid(scan_f)
        hard, _ = acquire.cell_bits_blind(
            acquire.sample_cell_means(scan_f, grid))
        foot = _aligned_footing_ber(hard, gt_win, mask_win)
        t_foot = time.perf_counter() - t0

        # (b) geometry=True, SAME window/print seed, full blind pipeline
        t0 = time.perf_counter()
        scan_t = print_scan(crop, ChannelParams(seed=s, scan_seed=s + 1,
                                                geometry=True))
        res = acquire.acquire_and_decode(scan_t, spec, SEED)
        t_blind = time.perf_counter() - t0
        row: dict = {"print_seed": s, "geomF": foot,
                     "geomF_s": round(t_foot, 1),
                     "geomT_s": round(t_blind, 1)}
        if res.ok:
            got = res.cell_origin_abs_yx
            addr_ok = (res.orientation_k == 0 and res.page == 0
                       and abs(got[0] - oy) <= 1 and abs(got[1] - ox) <= 1)
            idx = res.payload_cell_index
            ber = float(np.mean(res.payload_bits != payload_gt[idx]))
            null = float(np.mean(res.payload_bits != payload_gt[
                (idx + NULL_STRIDE) % payload_gt.size]))
            row["geomT"] = {
                "ok": True, "address_ok": bool(addr_ok),
                "origin_cells_yx": [int(got[0]), int(got[1])],
                "payload_ber": ber, "null": null,
                "stage_b_match": round(float(res.stage_b_match_rate), 4),
                "tiles_decoded": [res.n_tiles_decoded, res.n_tiles_attempted],
                "n_payload_bits": int(idx.size)}
            row["gap_pp"] = round(100.0 * (ber - foot["ber_nonpilot"]), 3)
        else:
            row["geomT"] = {"ok": False, "failed_stage":
                            res.diagnostics.get("failed_stage")}
            row["gap_pp"] = None
        per_seed.append(row)
        g = row["geomT"]
        print(f"  footing seed {s}: geomF {_fmt_pct(foot['ber_nonpilot'])} "
              f"(all {_fmt_pct(foot['ber_all'])}) | geomT "
              + (f"{_fmt_pct(g['payload_ber'])} null {g['null']:.3f} "
                 f"addr_ok={g['address_ok']} gap {row['gap_pp']:+.2f}pp "
                 f"[{row['geomF_s']:.0f}s/{row['geomT_s']:.0f}s]"
                 if g["ok"] else f"FAILED at {g['failed_stage']}"),
              flush=True)
    gaps = [r["gap_pp"] for r in per_seed if r["gap_pp"] is not None]
    return {"window_cells": n, "origin_cells_yx": list(FOOT_ORIGIN_CELLS),
            "print_seeds": list(print_seeds), "per_seed": per_seed,
            "mean_gap_pp": round(float(np.mean(gaps)), 3) if gaps else None}


# ---------------------------------------------------------------------------
# 3. Fragment grain curve
# ---------------------------------------------------------------------------

def grain_curve(page_bits: np.ndarray, payload_gt: np.ndarray,
                spec: compose.ComposeSpec, n_trials: int) -> dict:
    page_h_dots, page_w_dots = page_bits.shape
    sizes = []
    for mm in GRAIN_SIZES_MM:
        n_cells = round(mm / 25.4 * 600 / CELL_DOTS)
        size_dots = n_cells * CELL_DOTS
        trials = []
        for t in range(n_trials):
            r = rng(ASEED, f"grain/{mm:g}/{t}".encode())
            oy_d = int(r.integers(0, page_h_dots - size_dots + 1))
            ox_d = int(r.integers(0, page_w_dots - size_dots + 1))
            k = int(r.integers(0, 4))
            crop = page_bits[oy_d:oy_d + size_dots, ox_d:ox_d + size_dots]
            scan = print_scan(crop, ChannelParams(seed=t, scan_seed=t + 1,
                                                  geometry=True))
            frag = np.ascontiguousarray(np.rot90(scan, -k))
            t0 = time.perf_counter()
            try:
                res = acquire.acquire_and_decode(frag, spec, SEED)
                err = None
            except Exception as exc:   # a crash is a measurement, not a stop
                res, err = None, f"{type(exc).__name__}: {exc}"
            dt = time.perf_counter() - t0
            row: dict = {"trial": t, "offset_dots_yx": [oy_d, ox_d],
                         "rot_k": k, "runtime_s": round(dt, 1)}
            if err is not None:
                row.update(ok=False, address_ok=False, error=err)
            elif not res.ok:
                row.update(ok=False, address_ok=False,
                           failed_stage=res.diagnostics.get("failed_stage"))
            else:
                got = res.cell_origin_abs_yx
                exp_y, exp_x = oy_d / CELL_DOTS, ox_d / CELL_DOTS
                addr_ok = (res.orientation_k == k and res.page == 0
                           and abs(got[0] - exp_y) <= 1.0
                           and abs(got[1] - exp_x) <= 1.0)
                idx = res.payload_cell_index
                ber = float(np.mean(res.payload_bits != payload_gt[idx]))
                null = float(np.mean(res.payload_bits != payload_gt[
                    (idx + NULL_STRIDE) % payload_gt.size]))
                row.update(ok=True, address_ok=bool(addr_ok),
                           orientation_k=res.orientation_k,
                           origin_cells_yx=[int(got[0]), int(got[1])],
                           payload_ber=ber, null=null)
            trials.append(row)
        n_ok = sum(1 for x in trials if x["ok"])
        n_addr = sum(1 for x in trials if x["ok"] and x["address_ok"])
        bers = [x["payload_ber"] for x in trials
                if x["ok"] and x["address_ok"]]
        med_ber = float(np.median(bers)) if bers else None
        med_rt = float(np.median([x["runtime_s"] for x in trials]))
        sizes.append({"size_mm": mm, "size_cells": n_cells,
                      "n_trials": n_trials, "n_ok": n_ok,
                      "n_address_correct": n_addr,
                      "median_payload_ber": med_ber,
                      "median_runtime_s": round(med_rt, 1),
                      "trials": trials})
        print(f"  grain {mm:5.1f} mm ({n_cells:3d} cells): "
              f"ok {n_ok}/{n_trials}, addr {n_addr}/{n_trials}, "
              f"median BER {_fmt_pct(med_ber) if med_ber is not None else '--'}"
              f", median rt {med_rt:.1f}s", flush=True)
    return {"sizes_mm": list(GRAIN_SIZES_MM), "n_trials": n_trials,
            "per_size": sizes}


# ---------------------------------------------------------------------------
# 4a. overhead accounting + R3 spectrum spot check
# ---------------------------------------------------------------------------

def overhead_block(spec: compose.ComposeSpec) -> dict:
    h, w = spec.page_cells_yx
    p = spec.pilot.period_cells
    n_tiles = (h // p) * (w // p)
    sites = compose._sites_per_tile(spec.pilot)
    pilot_cells = n_tiles * sites
    total = h * w
    return {"total_cells": total, "pilot_tiles": n_tiles,
            "pilot_cells": pilot_cells,
            "pilot_fraction_pct": round(100.0 * pilot_cells / total, 4),
            "payload_capacity_bits": compose.payload_capacity(spec),
            "address_bits_carried": n_tiles * 36,
            "word_code": "BCH(127,64,t=10) shortened -> (100,37), d>=21",
            "overhead_per_payload_bit_pct": round(
                100.0 * pilot_cells / compose.payload_capacity(spec), 4)}


def spectrum_r3(cells: np.ndarray) -> dict:
    """Power spectrum of the RIP cell grid: relative height of the p60b6 site
    lattice lines. Site positions repeat with the 60-cell period (multiples
    of 1/60 cyc/cell = bin multiples of (H/60, W/60)); the 1/6 block line is
    the 10th-harmonic subset. Peak vs median background = the conceded
    macroscopic structure (DESIGN §10.2 trilemma; R3 forbids furniture, the
    lattice is the residue)."""
    z = cells.astype(np.float64) - float(cells.mean())
    P = np.abs(np.fft.fft2(z)) ** 2
    P[0, 0] = 0.0
    med = float(np.median(P))
    h, w = cells.shape
    ky = np.arange(0, h, h // 60)
    kx = np.arange(0, w, w // 60)
    g60 = P[np.ix_(ky, kx)].copy()
    g60[0, 0] = 0.0
    ky6 = np.arange(0, h, h // 6)
    kx6 = np.arange(0, w, w // 6)
    g6 = P[np.ix_(ky6, kx6)].copy()
    g6[0, 0] = 0.0
    out = {"median_background": med,
           "site_line_1_60": {"peak_rel": round(float(g60.max()) / med, 2),
                              "mean_rel": round(float(g60.mean()) / med, 3),
                              "n_bins": int(g60.size - 1)},
           "block_line_1_6": {"peak_rel": round(float(g6.max()) / med, 2),
                              "mean_rel": round(float(g6.mean()) / med, 3),
                              "n_bins": int(g6.size - 1)},
           "global_peak_rel": round(float(P.max()) / med, 2)}
    print(f"  R3 spectrum: 1/60 site line peak {out['site_line_1_60']['peak_rel']}x "
          f"(mean {out['site_line_1_60']['mean_rel']}x), 1/6 block line peak "
          f"{out['block_line_1_6']['peak_rel']}x, global peak "
          f"{out['global_peak_rel']}x median", flush=True)
    return out


# ---------------------------------------------------------------------------
# 4b. multi-scan probe (print once, scan 3x, majority on absolute indices)
# ---------------------------------------------------------------------------

def multiscan_probe(page_bits: np.ndarray, payload_gt: np.ndarray,
                    spec: compose.ComposeSpec) -> dict:
    oy, ox = FOOT_ORIGIN_CELLS
    n = FOOT_CELLS
    crop = page_bits[oy * CELL_DOTS:(oy + n) * CELL_DOTS,
                     ox * CELL_DOTS:(ox + n) * CELL_DOTS]
    s = MULTISCAN_PRINT_SEED
    printed = print_plane(crop, ChannelParams(seed=s, geometry=True))
    vote_sum = np.zeros(payload_gt.size, np.int16)
    vote_cnt = np.zeros(payload_gt.size, np.int16)
    first_bits = np.full(payload_gt.size, -1, np.int8)
    scans = []
    for ss in (s + 1, s + 2, s + 3):
        scan = scan_plane(printed, ChannelParams(seed=s, scan_seed=ss,
                                                 geometry=True))
        t0 = time.perf_counter()
        res = acquire.acquire_and_decode(scan, spec, SEED)
        dt = time.perf_counter() - t0
        row: dict = {"scan_seed": ss, "ok": bool(res.ok),
                     "runtime_s": round(dt, 1)}
        if res.ok:
            got = res.cell_origin_abs_yx
            addr_ok = (res.orientation_k == 0
                       and abs(got[0] - oy) <= 1 and abs(got[1] - ox) <= 1)
            idx = res.payload_cell_index
            ber = float(np.mean(res.payload_bits != payload_gt[idx]))
            row.update(address_ok=bool(addr_ok), payload_ber=ber)
            if addr_ok:
                np.add.at(vote_sum, idx, res.payload_bits.astype(np.int16))
                np.add.at(vote_cnt, idx, 1)
                fresh = first_bits[idx] < 0
                first_bits[idx[fresh]] = res.payload_bits[fresh]
        else:
            row["failed_stage"] = res.diagnostics.get("failed_stage")
        scans.append(row)
        print(f"  multiscan scan_seed {ss}: "
              + (f"BER {_fmt_pct(row['payload_ber'])}" if res.ok
                 else f"FAILED at {row.get('failed_stage')}"), flush=True)
    used = vote_cnt > 0
    if not used.any():
        return {"print_seed": s, "scans": scans,
                "note": "no scan produced an address-correct decode"}
    # majority; ties (even counts) fall back to the first scan's bit
    maj = np.where(2 * vote_sum[used] == vote_cnt[used],
                   first_bits[used],
                   (2 * vote_sum[used] > vote_cnt[used]).astype(np.int8))
    ber_comb = float(np.mean(maj != payload_gt[used]))
    ber_1 = next((r["payload_ber"] for r in scans
                  if r["ok"] and r.get("address_ok")), None)
    full = int((vote_cnt == 3).sum())
    out = {"print_seed": s, "scans": scans,
           "n_indices_combined": int(used.sum()),
           "n_indices_in_all_scans": full,
           "ber_1scan": ber_1, "ber_3scan_majority": ber_comb,
           "gain_pp": (round(100.0 * (ber_1 - ber_comb), 3)
                       if ber_1 is not None else None)}
    print(f"  multiscan: 1-scan {_fmt_pct(ber_1) if ber_1 is not None else '--'}"
          f" -> 3-scan majority {_fmt_pct(ber_comb)} "
          f"over {out['n_indices_combined']} bits", flush=True)
    return out


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def print_table(report: dict) -> None:
    print("\n=== E011 pilot round-trip (011.1, sim-only) ===")
    rg = report["rip_gate"]
    print(f"RIP gate: sha {rg['ps_sha256'][:16]}.. diff {rg['pixel_diff_vs_gt']} px")
    ov = report["overhead"]
    print(f"overhead: {ov['pilot_cells']} pilot cells / {ov['total_cells']} "
          f"= {ov['pilot_fraction_pct']}% ({ov['word_code']})")
    fg = report["footing_gap"]
    print(f"\nfooting gap (600x600 cells at {fg['origin_cells_yx']}):")
    print("  seed | geomF nonpilot | geomT payload |  null | gap(pp)")
    for r in fg["per_seed"]:
        g = r["geomT"]
        if g["ok"]:
            print(f"   {r['print_seed']:3d} | {_fmt_pct(r['geomF']['ber_nonpilot']):>13} "
                  f"| {_fmt_pct(g['payload_ber']):>13} | {g['null']:.3f} "
                  f"| {r['gap_pp']:+.2f}")
        else:
            print(f"   {r['print_seed']:3d} | {_fmt_pct(r['geomF']['ber_nonpilot']):>13} "
                  f"| FAILED ({g['failed_stage']})")
    if fg["mean_gap_pp"] is not None:
        print(f"  mean gap: {fg['mean_gap_pp']:+.2f} pp")
    gc = report["grain_curve"]
    print(f"\ngrain curve ({gc['n_trials']} trials/size):")
    print("   mm | cells |  ok | addr | med BER | med rt(s)")
    for szr in gc["per_size"]:
        mb = szr["median_payload_ber"]
        print(f" {szr['size_mm']:4.0f} | {szr['size_cells']:5d} "
              f"| {szr['n_ok']}/{szr['n_trials']} | {szr['n_address_correct']}"
              f"/{szr['n_trials']} | {_fmt_pct(mb) if mb is not None else '   --  '}"
              f" | {szr['median_runtime_s']:.1f}")
    sp = report["spectrum_r3"]
    print(f"\nR3 spectrum: 1/60 site line {sp['site_line_1_60']['peak_rel']}x, "
          f"1/6 block line {sp['block_line_1_6']['peak_rel']}x median background")
    ms = report.get("multiscan")
    if ms and "ber_3scan_majority" in ms:
        print(f"multiscan (print seed {ms['print_seed']}): 1-scan "
              f"{_fmt_pct(ms['ber_1scan'])} -> 3-scan {_fmt_pct(ms['ber_3scan_majority'])}"
              f" ({ms['gain_pp']:+.2f} pp)")
    elif ms:
        print(f"multiscan: {ms.get('note', 'skipped')}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true",
                    help="CI smoke: 2 trials/size, footing seed 0 only, "
                         "no multi-scan probe")
    args = ap.parse_args(argv)
    t_start = time.perf_counter()

    rip, page_bits, cells, payload_gt, spec = rip_gate()
    print("overhead + R3 spectrum:", flush=True)
    ov = overhead_block(spec)
    sp = spectrum_r3(cells)
    seeds = (FOOT_PRINT_SEEDS[:1] if args.quick else FOOT_PRINT_SEEDS)
    print(f"footing gap ({len(seeds)} print seeds):", flush=True)
    fg = footing_gap(page_bits, cells, payload_gt, spec, seeds)
    n_trials = 2 if args.quick else N_TRIALS_FULL
    print(f"grain curve ({n_trials} trials/size):", flush=True)
    gc = grain_curve(page_bits, payload_gt, spec, n_trials)
    if args.quick:
        ms: dict = {"note": "skipped (--quick)"}
    else:
        print("multi-scan probe:", flush=True)
        ms = multiscan_probe(page_bits, payload_gt, spec)

    report = {"experiment": "011-pilot-roundtrip", "run": "011.1",
              "seed": SEED.decode(), "analysis_seed": ASEED.decode(),
              "quick": bool(args.quick),
              "rip_gate": rip, "overhead": ov, "spectrum_r3": sp,
              "footing_gap": fg, "grain_curve": gc, "multiscan": ms,
              "total_runtime_s": round(time.perf_counter() - t_start, 1)}
    out = BUILD / "e011_report.json"
    out.write_text(json.dumps(report, indent=1))
    print_table(report)
    print(f"\nwrote {out.relative_to(EXP)} "
          f"({report['total_runtime_s']:.0f} s total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
