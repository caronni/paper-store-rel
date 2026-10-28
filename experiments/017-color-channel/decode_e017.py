#!/usr/bin/env python3
"""e017 ARCH-C hardware decode driver: Canon 4800 dpi RGB scans -> blind
color page_decode (dust-QDA + PAVA) -> per-level tile map -> LDPC at the
frozen rungs (C r0550 / M r0550 / Y r0547) -> level-stratified fountain
volume_decode -> data sha vs golden 19a5cc15... .

Port of the proven experiments/016-arch3-c2-volume/decode_e016.py pattern
onto the color receiver (formats.page_decode threads RGB for n_levels==3;
tilemap keys ((ty,tx), level); fountain symbols keyed (level, block, i)).
Protocol: experiments/017-color-channel.md "Pre-registered decode protocol".

FOOTING (documented decisions):
- Input = native 4800 dpi RGB TIFF (uncompressed => tifffile memmap; the
  6.9 GB file is NEVER loaded whole). CHUNKED 3x3 box-mean pre-decimation
  per channel -> 1600 dpi = 8 px/cell EXACT integer for c3@600dpi print,
  float32 (~3.1 GB result). 8 px/cell is the P2-measured strongest blind-ID
  footing (017.4: format-path pitch ID 8/8 at >=8 px/cell; the box mean is
  the same area averaging scannorm's canonical resample applies).
  scan_dpi=1600.0 is passed through so the format shortlist prunes to the
  true absolute pitch.
- window_cells=600, overlap_cells=60, id_window_px=600*8=4800 px: the
  e012/016.3 c3 precedent — 600-cell (76.2 mm) windows worked at c3 on
  every hardware run (012.3, 016.3 field-aligned); the c2 25-mm shrink
  (014.1) was a c2 warp-accumulation fix and does not apply at c3. The
  identification crop is sized to one decode window so a veto-prone
  mid-size crop (014.1's 43 mm default) is never used.
- align_to_field=True default (016.3: image-anchored tiling leaves boundary
  windows ~40% margin -> Stage A evidence desert; field alignment took
  interior symbol yield 84% -> 97% on e016).
- detector="global" default + calibrate=True: color pages gate ctx K-only
  (017.2 — the site-fit word path + dust-QDA payload path are the color
  detectors); PAVA calibration is the 014.2-measured LLR fix.
- --features {rgb, rgb+luma}, default rgb. NOTE: the task-spec spelling
  "rgb+grey" is acquire's "rgb+luma" (P3's grey 4th feature: +0.041 b/cell
  home / -0.023 office — worth trying on this home-M281 print if Y tiles
  fall short).

State accumulates across invocations (F6): build/e017_state.pkl. Run the
script again with the next scan file to fold it in; certified (tile,level)
symbols are never demoted; already-folded scan_ids are skipped. --fresh
discards saved state. GT (report-only, never fed to the receiver) is
re-derived through the gen module (the 012.3 ground-truth rule):
gen_e017.make_data -> fountain.encode_volume_pages.

Usage:
  env/bin/python decode_e017.py <scan_tiff> [<scan2> ...]
      [--fresh] [--quick] [--policy best_per_tile] [--features rgb]
      [--detector global] [--no-align] [--state PATH] [--report PATH]
  env/bin/python decode_e017.py --selftest [--keep-synth]

--selftest (zero print, run before the real scan lands): composes the REAL
e017 page via gen_e017's modules, stream-renders a clean RGB reflectance
scan at 24 px/cell = 8 px/dot (np.repeat x8 per axis == np.kron with an
8x8 ones block; planes_to_rgb_refl measured-crosstalk compose; paper-white
margins) into a temporary BigTIFF, then runs the FULL driver path on it —
memmap read, chunked 3x3 decimation to 8 px/cell, blind page_decode,
per-level decode_tiles at the frozen rungs, state pickle round-trip,
fountain volume_decode — and asserts byte-exact recovery vs the golden
data sha. Also times one 600-cell window acquire and extrapolates the
full-page wall time.

Known library caveat handled here: tilemap.volume_scans_wanted reads
diag["blocks"], which does not exist on an UNSOLVED level-stratified
volume (diag carries per-level dicts under "levels") — this driver ships
an MLC-safe local twin (_volume_verdict) instead of calling it; a library
fix is queued as an out-of-scope item.
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

from paperholo import compose, formats, fountain, tilemap  # noqa: E402
import gen_e017  # noqa: E402

BUILD = Path(__file__).resolve().parent / "build"
STATE_PKL = BUILD / "e017_state.pkl"
REPORT_JSON = BUILD / "e017_scan_report.json"
GOLD_DATA_SHA = ("19a5cc15ba4f0b4bdd73cefcb7d1591e1154315417fca2a0abb2a53b"
                 "964ee13b")
FMT = next(f for f in formats.FORMAT_REGISTRY
           if f.format_id == "e017-v4-cmy8")
LEVEL_NAMES = "CMY"

# frozen footing constants (rationale in the module docstring)
NATIVE_SCAN_DPI = 4800.0
DEC_FACTOR = 3                       # 4800 -> 1600 dpi, 3x3 box mean
DEC_SCAN_DPI = NATIVE_SCAN_DPI / DEC_FACTOR          # 1600.0
CELL_PX = 8                          # 1600 dpi / 200 cpi = 8 px/cell exact
WINDOW_CELLS = 600                   # e012/016.3 c3 precedent (76.2 mm)
OVERLAP_CELLS = 60
ID_WINDOW_PX = WINDOW_CELLS * CELL_PX                # identify on one window

SELFTEST_SYNTH = ROOT / "scratch" / "e017_selftest_synth_8pxdot.tiff"
SELFTEST_MARGIN_DOTS = 192           # paper-white margin around the field


# ---------------------------------------------------------------------------
# input handling (memory discipline: the native file is never a float array)
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """Streaming sha256 (the 6.9 GB scan must not be read into memory)."""
    with path.open("rb") as fh:
        return hashlib.file_digest(fh, "sha256").hexdigest()


def decimate_rgb(path: Path, dec_factor: int,
                 chunk_rows_px: int = 1536) -> np.ndarray:
    """Native RGB TIFF -> (H//f, W//f, 3) float32 by EXACT f x f box mean
    per channel, processed in row blocks off a memmap. The native array is
    never materialized as float; the largest transient is one row block
    (chunk_rows_px x W x 3 float32 ~ 1.0 GB at the e017 scan width)."""
    try:
        mm = tifffile.memmap(str(path), mode="r")
    except ValueError as e:
        print(f"  memmap failed ({e}); falling back to tifffile.imread "
              f"(compressed input? expect a {path.stat().st_size/1e9:.1f} "
              f"GB resident array)")
        mm = tifffile.imread(str(path))
    if mm.ndim != 3 or mm.shape[2] < 3:
        raise ValueError(f"expected an RGB scan (H, W, >=3), got {mm.shape}")
    f = int(dec_factor)
    if f == 1:
        return np.ascontiguousarray(mm[..., :3], np.float32)
    h, w = mm.shape[0] // f * f, mm.shape[1] // f * f
    out = np.empty((h // f, w // f, 3), np.float32)
    step = max(f, chunk_rows_px // f * f)
    for y0 in range(0, h, step):
        y1 = min(y0 + step, h)
        blk = np.asarray(mm[y0:y1, :w, :3], np.float32)
        out[y0 // f:y1 // f] = blk.reshape(
            (y1 - y0) // f, f, w // f, f, 3).mean(axis=(1, 3),
                                                  dtype=np.float32)
    del mm
    return out


# ---------------------------------------------------------------------------
# GT (report-only; 012.3 rule: through the gen module, never retyped)
# ---------------------------------------------------------------------------


def rederive_gt() -> tuple[fountain.VolumeSpec, bytes, dict,
                           list[np.ndarray]]:
    """(vspec, data, framed page-0 dict, per-level GT payload bit vectors).
    The GT is used for REPORTING only — it is never fed to the receiver."""
    vspec = gen_e017.make_vspec()
    data = gen_e017.make_data(vspec)
    assert hashlib.sha256(data).hexdigest() == GOLD_DATA_SHA, \
        "gen_e017.make_data does not reproduce the golden data sha"
    assert FMT.spec() == gen_e017.make_spec() and FMT.seed == gen_e017.SEED
    framed = fountain.encode_volume_pages(data, vspec)[0]
    gt_levels = [np.asarray(b, np.uint8) for b in framed["payload_bits"]]
    return vspec, data, framed, gt_levels


# ---------------------------------------------------------------------------
# reporting helpers
# ---------------------------------------------------------------------------


def _json_safe(o: object) -> object:
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (bytes, Path)):
        return str(o)
    return str(o)


def scan_report(state: tilemap.PageDecodeState, scan_id: str,
                gt_levels: list[np.ndarray]) -> dict:
    """Report-only per-scan stats vs gen-module GT. Per level: llr>0 ==
    bit 1; the BER is over measured (llr != 0) cells of the accumulated
    observation (window overlaps already resolved by tilemap.extend's
    mean-|LLR| tie-break, so each covered cell appears once)."""
    obs = state.scans[scan_id]
    idx = obs.payload_cell_index
    llr3 = obs.payload_llr                     # (3, N)
    per_level = []
    for lv in range(3):
        measured = llr3[lv] != 0.0
        hard = (llr3[lv][measured] > 0).astype(np.uint8)
        ber = (float(np.mean(hard != gt_levels[lv][idx[measured]]))
               if measured.any() else float("nan"))
        per_level.append({
            "level": LEVEL_NAMES[lv],
            "detection_ber_vs_gt": ber,
            "n_measured": int(measured.sum()),
            "erasure_frac": float(np.mean(~measured))})
    return {"scan_id": scan_id,
            "n_windows": int(obs.n_windows),
            "pilot_ber_est": float(obs.pilot_ber_est),
            "n_cells_covered": int(idx.size),
            "coverage_frac": float(idx.size
                                   / compose.payload_capacity(state.spec)),
            "per_level": per_level}


def level_tile_summary(state: tilemap.PageDecodeState,
                       vspec: fountain.VolumeSpec) -> dict:
    """Per-level tile-status counts + certified INTERIOR (fountain-bearing)
    symbol counts vs the per-level need (k=626 of 782)."""
    interior = set(fountain.interior_tiles(state.spec))
    out: dict = {}
    for lv in range(3):
        by_status: dict[str, int] = {}
        n_int_cert = 0
        for (tyx, lv2), st in state.tiles.items():
            if lv2 != lv:
                continue
            by_status[st.status] = by_status.get(st.status, 0) + 1
            if st.status == "certified" and tyx in interior:
                n_int_cert += 1
        out[LEVEL_NAMES[lv]] = {
            "status": by_status,
            "interior_certified": n_int_cert,
            "interior_total": vspec.n_symbols_total,
            "k_needed": vspec.k_total_level(lv)}
    return out


def _volume_verdict(state: tilemap.PageDecodeState,
                    vspec: fountain.VolumeSpec
                    ) -> tuple[bytes | None, dict, list[tuple[int, dict]]]:
    """tiles_to_symbols -> volume_decode -> (data, fountain report block,
    scans-wanted ranking). MLC-safe twin of tilemap.volume_scans_wanted
    (which KeyErrors on an unsolved color volume's diag — see module
    docstring)."""
    syms = fountain.tiles_to_symbols(state.certified_results(), vspec)
    data_out, diag = fountain.volume_decode(syms, vspec)
    fblock: dict = {"n_symbols_received": diag["n_symbols_received"],
                    "per_level": []}
    deficit = 0
    for ld in diag["levels"]:
        need = [(b["block"], b["needed"] - b["rank"])
                for b in ld["blocks"] if not b["solved"]]
        deficit += sum(d for _, d in need)
        fblock["per_level"].append({
            "level": LEVEL_NAMES[ld["level"]],
            "n_symbols_received": ld["n_symbols_received"],
            "solved_blocks": len(ld["solved_blocks"]),
            "n_blocks": ld["n_blocks"],
            "blocks_underranked": need})
    fblock["solved_all"] = bool(diag["solved_all"])
    if data_out is not None:
        return data_out, fblock, []
    interior = set(fountain.interior_tiles(state.spec))
    n_unc = sum(1 for (tyx, lv), st in state.tiles.items()
                if tyx in interior and st.status != "certified")
    wanted = [(state.page, {"uncertified_interior": n_unc,
                            "volume_deficit_symbols": int(deficit)})]
    return None, fblock, wanted


# ---------------------------------------------------------------------------
# the decode loop (shared by the real-scan path and --selftest)
# ---------------------------------------------------------------------------


def decode_scans(scan_paths: list[Path],
                 state: tilemap.PageDecodeState | None,
                 args: argparse.Namespace,
                 vspec: fountain.VolumeSpec,
                 gt_levels: list[np.ndarray],
                 report: dict, t0: float
                 ) -> tilemap.PageDecodeState | None:
    """Fold each scan into the map: decimate -> page_decode -> report ->
    decode_tiles at the frozen rungs -> F6 verdicts. Skips already-folded
    scan_ids (resume semantics)."""
    for p in scan_paths:
        scan_id = p.stem
        if state is not None and scan_id in state.scans:
            print(f"scan {scan_id} already folded in — skipping")
            continue
        sha = sha256_file(p)
        td0 = time.time()
        img_dec = decimate_rgb(p, DEC_FACTOR)
        t_dec = time.time() - td0
        print(f"[{time.time()-t0:7.1f}s] {scan_id}: decimated {DEC_FACTOR}x"
              f"{DEC_FACTOR} -> {img_dec.shape} float32 @"
              f"{DEC_SCAN_DPI:.0f} dpi ({t_dec:.0f}s); sha {sha[:12]}…")
        tp0 = time.time()
        ident, state = formats.page_decode(
            img_dec, scan_id=scan_id, state=state, candidates=[FMT],
            scan_dpi=DEC_SCAN_DPI, window_cells=WINDOW_CELLS,
            overlap_cells=OVERLAP_CELLS, id_window_px=ID_WINDOW_PX,
            align_to_field=not args.no_align,
            detector=args.detector, calibrate=True,
            color_features=args.features)
        t_page = time.time() - tp0
        del img_dec
        if "field_bbox_px" in ident.diagnostics:
            print(f"  field bbox: {ident.diagnostics['field_bbox_px']}")
        if not ident.ok:
            print(f"  IDENTIFICATION FAILED: {ident.tried} "
                  f"{ident.diagnostics.get('failed_stage')}")
            report["scans"].append({"scan_id": scan_id, "sha256": sha,
                                    "ok": False, "tried": ident.tried})
            continue
        sr = scan_report(state, scan_id, gt_levels)
        n_ok = ident.diagnostics.get("n_windows_ok")
        n_tried = ident.diagnostics.get("n_windows_tried")
        cdiag = (ident.result.diagnostics.get("color", {})
                 if ident.result is not None else {})
        sr.update(sha256=sha, ok=True, n_windows_ok=n_ok,
                  n_windows_tried=n_tried,
                  geometry_confirmed=bool(ident.geometry_confirmed),
                  pitch_hyp_px=float(ident.pitch_hyp_px),
                  decimate_s=round(t_dec, 1),
                  page_decode_s=round(t_page, 1),
                  s_per_window=round(t_page / max(n_tried or 1, 1), 1),
                  color_diag={k: v for k, v in cdiag.items()
                              if isinstance(v, (str, bool, int, float))})
        report["scans"].append(sr)
        print(f"  [{time.time()-t0:7.1f}s] windows {n_ok}/{n_tried} ok "
              f"({t_page:.0f}s, ~{sr['s_per_window']:.1f}s/window); "
              f"pitch {ident.pitch_hyp_px:.3f}px "
              f"geomY={ident.geometry_confirmed}")
        for e in sr["per_level"]:
            print(f"    {e['level']}: detection BER "
                  f"{100*e['detection_ber_vs_gt']:.2f}% on "
                  f"{e['n_measured']} cells "
                  f"(erasures {100*e['erasure_frac']:.1f}%)")
        print(f"    pilot_ber_est {100*sr['pilot_ber_est']:.2f}%, coverage "
              f"{sr['n_cells_covered']} cells = "
              f"{100*sr['coverage_frac']:.1f}%")
        counts = state.decode_tiles(gen_e017.RUNGS, policy=args.policy)
        print(f"  [{time.time()-t0:7.1f}s] decode_tiles({args.policy}, "
              f"rungs {'/'.join(gen_e017.RUNGS)}): {counts}")
        lsum = level_tile_summary(state, vspec)
        for lv_name, e in lsum.items():
            print(f"    {lv_name}: interior certified "
                  f"{e['interior_certified']}/{e['interior_total']} "
                  f"(need {e['k_needed']}); {e['status']}")
        ask, why = state.more_scans_useful()
        print(f"  more_scans_useful (inner F6): {ask} — {why}")
        print("    (coded-volume stop rule = volume verdict below, "
              "016.2 F6 lesson)")
    return state


def finish(state: tilemap.PageDecodeState, vspec: fountain.VolumeSpec,
           report: dict, t0: float) -> bytes | None:
    """Fountain verdict + report block. Returns decoded data (or None)."""
    data_out, fblock, wanted = _volume_verdict(state, vspec)
    report["tiles"] = state.summary()
    report["per_level"] = level_tile_summary(state, vspec)
    report["fountain"] = fblock
    report["volume_scans_wanted"] = [
        {"page": pg, **info} for pg, info in wanted]
    if data_out is not None:
        sha_out = hashlib.sha256(data_out).hexdigest()
        report["data_sha256"] = sha_out
        report["byte_exact"] = bool(sha_out == GOLD_DATA_SHA)
        print(f"\n[{time.time()-t0:7.1f}s] VOLUME DECODED: {len(data_out)} "
              f"bytes, sha {sha_out}")
        print("BYTE-EXACT MATCH" if report["byte_exact"] else
              "*** SHA MISMATCH — investigate before logging ***")
    else:
        report["byte_exact"] = False
        print(f"\n[{time.time()-t0:7.1f}s] volume NOT yet decoded:")
        for e in fblock["per_level"]:
            print(f"  {e['level']}: {e['solved_blocks']}/{e['n_blocks']} "
                  f"blocks solved, {e['n_symbols_received']} symbols; "
                  f"deficits {e['blocks_underranked'][:8]}"
                  f"{'…' if len(e['blocks_underranked']) > 8 else ''}")
        print(f"volume_scans_wanted: {report['volume_scans_wanted']}")
    return data_out


# ---------------------------------------------------------------------------
# --selftest: the full driver path on a clean synthetic scan (zero print)
# ---------------------------------------------------------------------------


def render_selftest_scan(plane_bits: np.ndarray, out_path: Path,
                         px_per_dot: int = 8,
                         margin_dots: int = SELFTEST_MARGIN_DOTS,
                         chunk_dot_rows: int = 96) -> None:
    """Stream-render the composed page as a clean RGB uint8 BigTIFF at
    px_per_dot=8 (24 px/cell — the real Canon 4800 footing), chunk by
    dot-row block: upsample by np.repeat x8 per axis (== np.kron with an
    8x8 ones block), compose through the measured density-domain crosstalk
    (planes_to_rgb_refl), paper-white margins (zero ink coverage). NO noise,
    NO geometry — the clean-channel footing of the coded gate, at full-page
    scale and through the real file/decimation path."""
    from paperholo.channel import planes_to_rgb_refl
    n_pl, h_dots, w_dots = plane_bits.shape
    assert n_pl == 3
    h_tot_dots = h_dots + 2 * margin_dots
    w_tot_dots = w_dots + 2 * margin_dots
    shape_px = (h_tot_dots * px_per_dot, w_tot_dots * px_per_dot, 3)
    print(f"  rendering synthetic scan {shape_px} uint8 "
          f"({shape_px[0]*shape_px[1]*3/1e9:.2f} GB) -> {out_path.name}")
    mm = tifffile.memmap(str(out_path), shape=shape_px, dtype=np.uint8,
                         bigtiff=True)
    fy0, fy1 = margin_dots, margin_dots + h_dots
    for y0d in range(0, h_tot_dots, chunk_dot_rows):
        y1d = min(y0d + chunk_dot_rows, h_tot_dots)
        block = np.zeros((3, y1d - y0d, w_tot_dots), np.uint8)
        a, b = max(y0d, fy0), min(y1d, fy1)
        if a < b:
            block[:, a - y0d:b - y0d, margin_dots:margin_dots + w_dots] = \
                plane_bits[:, a - fy0:b - fy0, :]
        up = np.repeat(np.repeat(block, px_per_dot, axis=1),
                       px_per_dot, axis=2)
        rgb = planes_to_rgb_refl(
            {pl: up[lv] for lv, pl in enumerate(LEVEL_NAMES)})
        mm[y0d * px_per_dot:y1d * px_per_dot] = np.clip(
            rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
    mm.flush()
    del mm


def run_selftest(args: argparse.Namespace) -> int:
    t0 = time.time()
    print("SELFTEST: full driver path on a clean full-page synthetic scan")
    vspec, data, framed, gt_levels = rederive_gt()
    print(f"[{time.time()-t0:7.1f}s] GT re-derived via gen module "
          f"({vspec.data_len_bytes} bytes, 3 levels x "
          f"{vspec.k_total_level(0)}/{vspec.n_symbols_total} symbols)")
    cp = compose.compose_page(framed["payload_bits"], gen_e017.make_spec(),
                              gen_e017.SEED, page=0)
    plane_bits = np.asarray(cp.plane_bits, np.uint8)
    print(f"[{time.time()-t0:7.1f}s] composed page: plane_bits "
          f"{plane_bits.shape}")
    # cross-check vs the sha-gated build GT when present (paper==build rule)
    mf_path = BUILD / "e017_manifest.json"
    if mf_path.exists():
        mf = json.loads(mf_path.read_text())
        for lv, pl in enumerate(LEVEL_NAMES):
            (e,) = [q for q in mf["patches"] if q["planes"] == [pl]]
            gt = np.load(BUILD / e["gt"])
            assert np.array_equal(plane_bits[lv], gt), \
                f"composed {pl} plane != build GT — build/spec drift"
        print(f"[{time.time()-t0:7.1f}s] composed planes == build GT npys "
              "(dot-exact)")

    synth = args.synth_path
    synth.parent.mkdir(parents=True, exist_ok=True)
    if synth.exists():
        print(f"  {synth.name} exists — reusing (delete to re-render)")
    else:
        render_selftest_scan(plane_bits, synth)
        print(f"[{time.time()-t0:7.1f}s] synthetic scan written "
              f"({synth.stat().st_size/1e9:.2f} GB)")
    del plane_bits, cp

    # time ONE 600-cell window acquire on the decimated footing (the
    # wall-time anchor requested by the protocol), then run the real loop
    img_dec = decimate_rgb(synth, DEC_FACTOR)
    print(f"[{time.time()-t0:7.1f}s] decimated: {img_dec.shape} float32")
    H, W = img_dec.shape[:2]
    crop = np.ascontiguousarray(
        img_dec[(H - ID_WINDOW_PX) // 2:(H + ID_WINDOW_PX) // 2,
                (W - ID_WINDOW_PX) // 2:(W + ID_WINDOW_PX) // 2])
    tw0 = time.time()
    one = formats.acquire_scan(crop, candidates=[FMT],
                               scan_dpi=DEC_SCAN_DPI,
                               detector=args.detector, calibrate=True,
                               color_features=args.features)
    t_window = time.time() - tw0
    assert one.ok, f"single-window acquire failed: {one.tried}"
    print(f"[{time.time()-t0:7.1f}s] ONE {WINDOW_CELLS}-cell window "
          f"acquire: {t_window:.1f}s (fmt {one.fmt.format_id}, pitch "
          f"{one.pitch_hyp_px:.3f}px)")
    del img_dec, crop

    report: dict = {"selftest": True, "format": FMT.format_id,
                    "window_cells": WINDOW_CELLS,
                    "overlap_cells": OVERLAP_CELLS,
                    "id_window_px": ID_WINDOW_PX, "policy": args.policy,
                    "features": args.features, "detector": args.detector,
                    "scans": []}
    state = decode_scans([synth], None, args, vspec, gt_levels, report, t0)
    assert state is not None and report["scans"] and report["scans"][-1]["ok"]
    n_win = report["scans"][-1]["n_windows_tried"]
    print(f"  wall-time extrapolation: {n_win} windows x {t_window:.1f}s "
          f"~= {n_win*t_window/60:.1f} min acquire + decimation/normalize "
          f"overhead (measured page_decode "
          f"{report['scans'][-1]['page_decode_s']:.0f}s total this page)")

    # state pickle round-trip = the resume path, proven before hardware
    n_cert_before = sum(1 for st in state.tiles.values()
                        if st.status == "certified")
    state = pickle.loads(pickle.dumps(state))
    counts = state.decode_tiles(gen_e017.RUNGS, policy=args.policy)
    n_cert_after = sum(1 for st in state.tiles.values()
                       if st.status == "certified")
    del counts  # re-decode touches only pending tiles (worklist semantics)
    assert n_cert_after >= n_cert_before > 0, \
        (n_cert_before, n_cert_after)   # resume path: nothing demoted
    data_out = finish(state, vspec, report, t0)
    report_path = BUILD / "e017_selftest_report.json"
    BUILD.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=_json_safe))
    assert data_out is not None, "selftest volume did not decode"
    assert data_out == data and hashlib.sha256(
        data_out).hexdigest() == GOLD_DATA_SHA
    print(f"\nSELFTEST PASS: byte-exact volume recovery "
          f"({len(data_out)} bytes) through memmap -> chunked 3x3 "
          f"decimation -> blind page_decode -> per-level LDPC -> "
          f"fountain; report -> {report_path} "
          f"({time.time()-t0:.0f}s total)")
    if not args.keep_synth:
        synth.unlink()
        print(f"removed {synth} (pass --keep-synth to keep)")
    return 0


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="e017 ARCH-C color decode driver (see module docstring)")
    ap.add_argument("scans", nargs="*", type=Path,
                    help="native 4800 dpi RGB TIFF scan(s)")
    ap.add_argument("--selftest", action="store_true",
                    help="full driver path on a clean synthetic scan; "
                         "asserts byte-exact volume recovery")
    ap.add_argument("--keep-synth", action="store_true",
                    help="keep the selftest synthetic TIFF")
    ap.add_argument("--synth-path", type=Path, default=SELFTEST_SYNTH)
    ap.add_argument("--quick", action="store_true",
                    help="one central window per scan, no state")
    ap.add_argument("--fresh", action="store_true",
                    help="discard saved state")
    ap.add_argument("--no-align", action="store_true",
                    help="disable align_to_field (016.3 default is ON)")
    ap.add_argument("--policy", default="best_per_tile",
                    choices=tilemap.PageDecodeState._POLICIES)
    ap.add_argument("--features", default="rgb",
                    choices=("rgb", "rgb+luma"),
                    help="color QDA feature set (acquire spelling; "
                         "'rgb+luma' = P3's grey 4th feature)")
    ap.add_argument("--detector", default="global",
                    choices=("global", "ctx"),
                    help="ctx is gated K-only on color pages (017.2); "
                         "global is the color default")
    ap.add_argument("--state", type=Path, default=STATE_PKL)
    ap.add_argument("--report", type=Path, default=REPORT_JSON)
    args = ap.parse_args()

    if args.selftest:
        return run_selftest(args)
    if not args.scans:
        ap.error("no scans given (or use --selftest)")

    t0 = time.time()
    vspec, data, framed, gt_levels = rederive_gt()
    print(f"[{time.time()-t0:7.1f}s] GT re-derived via gen module "
          f"({vspec.data_len_bytes} bytes = 3 levels x "
          f"{vspec.k_total_level(0)}/{vspec.n_symbols_total} symbols x "
          f"{vspec.symbol_bits_level(0)} bits; rungs "
          f"{'/'.join(gen_e017.RUNGS)})")

    if args.quick:
        for p in args.scans:
            img_dec = decimate_rgb(p, DEC_FACTOR)
            H, W = img_dec.shape[:2]
            s = ID_WINDOW_PX
            win = np.ascontiguousarray(
                img_dec[(H - s) // 2:(H + s) // 2,
                        (W - s) // 2:(W + s) // 2])
            r = formats.acquire_scan(win, candidates=[FMT],
                                     scan_dpi=DEC_SCAN_DPI,
                                     detector=args.detector, calibrate=True,
                                     color_features=args.features)
            if not r.ok:
                print(f"QUICK {p.name}: FAILED {r.tried} "
                      f"{r.diagnostics.get('failed_stage')}")
                continue
            res = r.result
            idx = res.payload_cell_index
            bers = []
            for lv in range(3):
                llr = np.asarray(res.payload_llr[lv])
                m = llr != 0.0
                hard = (llr[m] > 0).astype(np.uint8)
                bers.append(float(np.mean(hard != gt_levels[lv][idx[m]])))
            print(f"QUICK {p.name}: ok fmt={r.fmt.format_id} "
                  f"pitch={r.pitch_hyp_px:.3f}px "
                  f"words={sum(1 for v in res.tile_words.values() if v >= 0)}"
                  f"/{len(res.tile_words)} payload BER C/M/Y "
                  f"{'/'.join(f'{100*b:.2f}' for b in bers)}% on "
                  f"{idx.size} cells geomY={r.geometry_confirmed}")
        return 0

    state: tilemap.PageDecodeState | None = None
    if args.state.exists() and not args.fresh:
        state = pickle.loads(args.state.read_bytes())
        print(f"resumed state: {state.summary()}")

    report: dict = {
        "format": FMT.format_id,
        "volume": {"data_len_bytes": vspec.data_len_bytes,
                   "rungs": list(gen_e017.RUNGS),
                   "n_symbols_per_level": vspec.n_symbols_total,
                   "k_per_level": vspec.k_total_level(0)},
        "footing": {"native_dpi": NATIVE_SCAN_DPI,
                    "dec_factor": DEC_FACTOR, "scan_dpi": DEC_SCAN_DPI,
                    "cell_px": CELL_PX, "window_cells": WINDOW_CELLS,
                    "overlap_cells": OVERLAP_CELLS,
                    "id_window_px": ID_WINDOW_PX,
                    "align_to_field": not args.no_align,
                    "detector": args.detector, "features": args.features,
                    "policy": args.policy},
        "scans": []}
    state = decode_scans(args.scans, state, args, vspec, gt_levels,
                         report, t0)
    if state is None:
        print("no evidence — nothing to decode")
        return 1
    finish(state, vspec, report, t0)
    BUILD.mkdir(parents=True, exist_ok=True)
    args.state.write_bytes(pickle.dumps(state))
    args.report.write_text(json.dumps(report, indent=2, default=_json_safe))
    print(f"[{time.time()-t0:7.1f}s] state -> {args.state}, "
          f"report -> {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
