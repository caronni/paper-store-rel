"""R11 stage 1 — one capture's cmy bands read cell by cell into a compact npz (the feature cache).

What: for every window of the selected cmy bands of one scan, the per-cell features the e041 page-scale readout
computes — the per-plane-pose RGB (x_pp = _X[:, 0, :]: R at C's pose, G at M's, B at Y's; a K-free alphabet
makes every hypothesis column equal, asserted), the single OR-ed pose RGB (x_1 = _X1), the whole-cell box at
the per-plane poses (x_wc = _XW[:, 0, :]) and optionally the 0.7-cell box (x_ap07, holo3's aperture size) —
with the truth (manifest index y, design label lab = [0, 3, 2, 1][y], hi, lo), the cell's place (band, window,
r, c, band_row, band_col) and a window table (registration, per-plane poses in px and dots).
Why: R11's calibration measurement (measure/cmy_calibration) works on cells with full truth; reading the scan
once per capture keeps every later stage scan-free.
How: the readout's own functions, imported — measure.e041_scale_readout.read_window over the manifest's windows,
page_frame / band_arrays / tile_windows / band_of, measure.e041_probe_readout.Scan / fit_page / page_white —
in the order of e041_scale_readout.main: page fit with the readout's defaults (0.3 mm, 0.01), page white from
rects over ALL bands, bars and fiducials (a white from the selected bands alone would move the unmixing and the
poses), windows serial, a ValueError skips the window (logged), a SystemExit (contract fork) aborts.
Gates: the bands npz sha256 against the manifest; the page white against the readout's log (warn); the PARITY
gate — per band the band-pooled nearest-mean state error per window on x_pp and on x_1 against the committed
readout CSV's state_err_band / state_err_band_singlepose at 4 decimals; a mismatch exits 2 (the npz is kept);
with --ap07 the re-composition must reproduce read_window's _X bit for bit, else the column is dropped.
Outputs: <out>.npz (np.savez; per-cell arrays, window table, meta as a 0-d string) and <out>.json (meta).

    PYTHONPATH=src:. /usr/bin/time -l env/bin/python -m measure.cmy_calibration.extract \\
        --capture S14-2400 --evidence-root DIR --scale-root DIR --out build/cmy-calibration/cells-S14-2400.npz
    (--capture names a row of config.CAPTURES: its published scan and manifest under --evidence-root, or
    $PAPER_EVIDENCE_ROOT, its parity CSV under --scale-root unless --parity-csv names one; or give --scan --manifest
    --scan-dpi --bands [--parity-csv].  2026-10-12: inputs by flag only, config's docstring; the run of record read
    scratch/e041/ and wrote scratch/cmy-calibration-20261010/.)
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

import numpy as np

from measure import _evidence
from measure.cmy_calibration.config import CAPTURES, WORKTREE
from measure.e041_mixture_readout import (class_means, classify, plane_poses, plane_search_px, sample_per_plane)
from measure.e041_probe_readout import Scan, fit_page, page_white, sample_rect, sub_px_per_dot
from measure.e041_scale_readout import (REG_MIN_PEAK, SEARCH_MM, band_arrays, band_of, dots, family_of,
                                        page_frame, read_window, rect_dots, register, states_of, tile_windows)

POSE_FLAGS = ("ok", "edge", "weak", "collinear", "absent")
LAB_OF_MANIFEST = np.array([0, 3, 2, 1], np.uint8)     # W C M Y -> design label W0 Y1 M2 C3
HI_OF_MANIFEST = np.array([0, 1, 1, 0], np.uint8)
LO_OF_MANIFEST = np.array([0, 1, 0, 1], np.uint8)
CMY_NAMES = ("W", "C", "M", "Y")


def sha256_file(path: Path, chunk_bytes: int = 1 << 24) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk_bytes):
            h.update(block)
    return h.hexdigest()


def git_head(root: Path = WORKTREE) -> str:
    try:
        return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def normalised_states(b: dict[str, Any]) -> list[str]:
    """The band's state names by first token ('C-solid' -> 'C'); refuses anything but the cmy alphabet W C M Y."""
    names = [s.split("-")[0] for s in states_of(b)]
    if names != list(CMY_NAMES):
        raise SystemExit(f"band {b['name']}: alphabet {states_of(b)} is not the cmy alphabet W, C, M, Y")
    return names


def recompose_window(scan: Scan, A: np.ndarray, w: dict[str, Any], b: dict[str, Any], planes: np.ndarray,
                     dpi: float, white: np.ndarray, sub: int, box_px: int) -> tuple[np.ndarray, np.ndarray]:
    """read_window's rect, registration and per-plane poses re-composed from the same imported pieces; returns
    (vals at the default half-cell box, vals at box_px), both (cells*cells, 3) float64, R at C's pose etc."""
    bx, by, _, _ = rect_dots(b, dpi)
    cd, cells = int(w["cell_dots"]), int(w["cells"])
    xd, yd = dots(w, "x", dpi), dots(w, "y", dpi)
    n_dots = cells * cd
    pl = planes[:, yd - by:yd - by + n_dots, xd - bx:xd - bx + n_dots]
    dot_mm = 25.4 / dpi
    step = dot_mm / sub
    s_px = int(round(SEARCH_MM / step))
    p_px = plane_search_px(sub)
    m_px = s_px + p_px
    k = np.arange(n_dots * sub + 2 * m_px)
    rect = sample_rect(scan, A, xd * dot_mm + (k - m_px) * step, yd * dot_mm + (k - m_px) * step)
    ink = np.kron(pl.max(axis=0).astype(np.float32), np.ones((sub,) * 2, np.float32))
    oy, ox, peak, _ = register(rect, ink, s_px, p_px)
    if peak < REG_MIN_PEAK:
        oy = ox = float(m_px)
    poses = plane_poses(rect, pl, oy, ox, white, p_px, sub)
    cell_px = cd * sub
    v_half, _ = sample_per_plane(rect, poses, oy, ox, cells, cell_px)
    v_box, _ = sample_per_plane(rect, poses, oy, ox, cells, cell_px, box=box_px)
    return v_half.reshape(-1, 3).astype(np.float64), v_box.reshape(-1, 3).astype(np.float64)


def window_record(row: dict[str, Any], w: dict[str, Any], sub: int) -> dict[str, Any]:
    rec: dict[str, Any] = {k: row[k] for k in ("id", "band", "grid_row", "grid_col", "x_dots", "y_dots", "cells",
                                               "cell_dots", "reg_ok", "reg_edge", "reg_peak", "reg_dy_mm",
                                               "reg_dx_mm")}
    rec["tile"] = -1 if row.get("tile") is None else int(row["tile"])
    cy, cx = w.get("cell_yx", [row["grid_row"] * row["cells"], row["grid_col"] * row["cells"]])
    rec["cell_y0"], rec["cell_x0"] = int(cy), int(cx)
    for pl in "CMY":
        q = row["poses"][pl]
        rec[f"{pl}_flag"] = POSE_FLAGS.index(q["flag"])
        for k in ("peak", "dy_px", "dx_px", "dy_vs_C_px", "dx_vs_C_px"):
            rec[f"{pl}_{k}"] = float(q[k])
        for k in ("dy_px", "dx_px", "dy_vs_C_px", "dx_vs_C_px"):
            rec[f"{pl}_{k.replace('_px', '_dots')}"] = float(q[k]) / sub
    return rec


def same_rows(a: dict[str, Any], b: dict[str, Any]) -> bool:
    def canon(x: Any) -> str:
        return json.dumps(x, sort_keys=True, default=str)
    return all(np.array_equal(a[k], b[k]) for k in ("_X", "_X1", "_XW", "_y")) \
        and canon(a["poses"]) == canon(b["poses"]) and canon(a["reg_peak"]) == canon(b["reg_peak"])


def read_windows(scan: Scan, A: np.ndarray, windows: list[dict[str, Any]], sel: list[dict[str, Any]],
                 arrays: dict[str, tuple[np.ndarray, np.ndarray]], dpi: float, white: np.ndarray, sub: int,
                 workers: int, log: Callable[[str], None]) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]],
                                                                    list[str], str]:
    """read_window over every window, serial, or on a thread pool after a serial-vs-threaded bit-identity check
    on the first windows (a mismatch falls back to serial).  Returns ((window, row) pairs, skipped ids, mode)."""
    def one(w: dict[str, Any]) -> dict[str, Any] | str:
        b = band_of(sel, w["band"])
        try:
            return read_window(scan, A, w, b, *arrays[b["name"]], dpi, white, sub, None)
        except ValueError as exc:
            return f"{exc}"
    mode = "serial"
    if workers > 1 and len(windows) >= 4:
        probe = windows[:min(len(windows), 2 * workers)]
        ser = [one(w) for w in probe]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            thr = list(pool.map(one, probe))
        if all(isinstance(a, str) and a == b or isinstance(a, dict) and isinstance(b, dict) and same_rows(a, b)
               for a, b in zip(ser, thr)):
            mode = f"threads x{workers} (bit-identical to serial on {len(probe)} windows)"
        else:
            log("  threaded read differs from serial — reading serially")
    if mode == "serial":
        got = [one(w) for w in windows]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            got = list(pool.map(one, windows))
    out, skipped = [], []
    for w, g in zip(windows, got):
        if isinstance(g, str):
            log(f"  window {w['id']}: skipped ({g})")
            skipped.append(str(w["id"]))
        else:
            out.append((w, g))
    return out, skipped, mode


def extract_capture(scan_path: Path, manifest_path: Path, scan_dpi: float, band_names: tuple[str, ...],
                    ap07: bool = False, log: Callable[[str], None] = print,
                    scan: Scan | None = None, workers: int = 1) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """The per-cell arrays and meta of one capture (see the module docstring)."""
    t0 = time.time()
    man = json.loads(manifest_path.read_text())
    dpi = float(man["dpi"])
    sub = sub_px_per_dot(scan_dpi, dpi)
    npz_path = manifest_path.parent / f"{man['tag']}-bands.npz"
    npz_sha = sha256_file(npz_path)
    want = (man.get("bands_npz") or {}).get("sha256")
    if want and want != npz_sha:
        raise SystemExit(f"{npz_path}: sha256 {npz_sha} != manifest {want}")
    npz = np.load(npz_path)
    frame = page_frame(man)
    sel = [b for b in man["bands"] if b["name"] in band_names]
    if sorted(b["name"] for b in sel) != sorted(band_names):
        raise SystemExit(f"bands {band_names} not all in the manifest ({[b['name'] for b in man['bands']]})")
    arrays = {}
    for b in sel:
        normalised_states(b)
        got = band_arrays(npz, b, dpi)
        if got is None:
            raise SystemExit(f"band {b['name']}: no arrays in {npz_path}")
        arrays[b["name"]] = got
        if got[1][3].any():
            raise SystemExit(f"band {b['name']}: the K plane carries ink — not a K-free cmy band")
    keys = {b["name"] for b in sel} | {b.get("band") for b in sel}
    windows = ([w for w in man["windows"] if w["band"] in keys] if man.get("windows")
               else [w for b in sel for w in tile_windows(b, dpi)])
    scan = scan if scan is not None else Scan(scan_path, scan_dpi)
    log(f"{man['tag']}: scan {scan.w} x {scan.h} px at {scan_dpi:.0f} dpi (sub {sub}), bands {band_names}, "
        f"{len(windows)} windows; load {time.time() - t0:.1f} s")
    A, fit = fit_page(scan, frame, 0.3, 0.01)
    dot_mm = 25.4 / dpi
    rects = [(x * dot_mm, y * dot_mm, (x + w) * dot_mm, (y + h) * dot_mm)
             for e in [*man["bands"], *man.get("bars", []), *man["fiducials"]] for x, y, w, h in [rect_dots(e, dpi)]]
    gwhite = page_white(scan, A, frame, rects)
    log(f"page white (margins) R {gwhite[0]:.1f} G {gwhite[1]:.1f} B {gwhite[2]:.1f}")
    band_index = {b["name"]: i for i, b in enumerate(sel)}
    cols: dict[str, list[np.ndarray]] = {k: [] for k in ("band", "win", "r", "c", "band_row", "band_col", "x_pp",
                                                         "x_1", "x_wc", "x_ap07", "y")}
    recs: list[dict[str, Any]] = []
    ap07_ok = ap07
    pairs, skipped, read_mode = read_windows(scan, A, windows, sel, arrays, dpi, gwhite, sub, workers, log)
    for w, row in pairs:
        b = band_of(sel, w["band"])
        X = row["_X"]
        if not (X == X[:, :1]).all() or not (row["_XW"] == row["_XW"][:, :1]).all():
            raise SystemExit(f"window {w['id']}: hypothesis columns differ — the band is not K-free")
        cells = int(row["cells"])
        n = cells * cells
        rr, cc = np.divmod(np.arange(n), cells)
        rec = window_record(row, w, sub)
        cols["band"].append(np.full(n, band_index[b["name"]], np.uint8))
        cols["win"].append(np.full(n, len(recs), np.int32))
        cols["r"].append(rr.astype(np.uint8))
        cols["c"].append(cc.astype(np.uint8))
        cols["band_row"].append((rec["cell_y0"] + rr).astype(np.int16))
        cols["band_col"].append((rec["cell_x0"] + cc).astype(np.int16))
        cols["x_pp"].append(X[:, 0, :].astype(np.float32))
        cols["x_1"].append(row["_X1"].astype(np.float32))
        cols["x_wc"].append(row["_XW"][:, 0, :].astype(np.float32))
        cols["y"].append(row["_y"].astype(np.uint8))
        if ap07_ok:
            box = int(round(0.7 * int(row["cell_dots"]) * sub))
            half, v07 = recompose_window(scan, A, w, b, arrays[b["name"]][1], dpi, gwhite, sub, box)
            if not np.array_equal(half, X[:, 0, :]):
                log(f"  window {w['id']}: re-composition differs from read_window — x_ap07 dropped")
                ap07_ok = False
            cols["x_ap07"].append(v07.astype(np.float32))
        recs.append(rec)
    del pairs
    out = {k: np.concatenate(v) for k, v in cols.items() if v and (k != "x_ap07" or ap07_ok)}
    out["lab"] = LAB_OF_MANIFEST[out["y"]]
    out["hi"] = HI_OF_MANIFEST[out["y"]]
    out["lo"] = LO_OF_MANIFEST[out["y"]]
    for k in recs[0] if recs else []:
        vals = [r[k] for r in recs]
        out[f"w_{k}"] = np.asarray(vals, dtype="<U16" if isinstance(vals[0], str) else None)
    meta = {"scan": str(scan_path), "scan_dpi": scan_dpi, "sub": sub, "fit": fit, "white": gwhite.tolist(),
            "manifest": str(manifest_path), "manifest_sha256": sha256_file(manifest_path),
            "bands_npz": str(npz_path), "bands_npz_sha256": npz_sha, "band_names": [b["name"] for b in sel],
            "bands": {b["name"]: {"states": states_of(b), "family": family_of(b), "cell_dots": int(b["cell_dots"]),
                                  "method": b.get("method")} for b in sel},
            "worktree_head": git_head(), "extract_sha256": sha256_file(Path(__file__)), "skipped": skipped,
            "n_windows": len(recs), "n_cells": int(out["y"].size), "x_ap07": bool(ap07_ok), "read_mode": read_mode,
            "wall_s": time.time() - t0}
    return out, meta


def write_cells(path: Path, arrays: dict[str, np.ndarray], meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, meta=np.array(json.dumps(meta)), **arrays)
    path.with_suffix(".json").write_text(json.dumps(meta, indent=1))


def load_cells(path: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    with np.load(path) as z:
        arrays = {k: z[k] for k in z.files if k != "meta"}
        meta = json.loads(str(z["meta"]))
    return arrays, meta


def band_pooled_errors(X: np.ndarray, y: np.ndarray, win: np.ndarray) -> dict[int, float]:
    """Per window, the state error of a nearest-mean classifier with one set of means over the whole band
    (e041_scale_readout.classify_windows' 'band' reading)."""
    mu, _ = class_means(X.astype(np.float64), y.astype(np.int64), 4)
    pred = classify(X.astype(np.float64), y.astype(np.int64), mu, None)
    wrong = (pred != y).astype(np.float64)
    n = np.bincount(win, minlength=int(win.max()) + 1)
    e = np.bincount(win, weights=wrong, minlength=n.size)
    return {int(i): float(e[i] / n[i]) for i in np.flatnonzero(n)}


def parity_gate(arrays: dict[str, np.ndarray], meta: dict[str, Any], csv_path: Path) -> dict[str, Any]:
    """x_pp / x_1 band-pooled window errors against the committed readout CSV (4 decimals)."""
    ref: dict[str, dict[str, str]] = {}
    with open(csv_path, newline="") as fh:
        for line in csv.DictReader(fh):
            ref[line["id"]] = line
    ids = arrays["w_id"]
    out: dict[str, Any] = {"csv": str(csv_path), "bands": {}}
    ok = True
    for bi, name in enumerate(meta["band_names"]):
        sel = arrays["band"] == bi
        res = {}
        for key, col in (("x_pp", "state_err_band"), ("x_1", "state_err_band_singlepose")):
            errs = band_pooled_errors(arrays[key][sel], arrays["y"][sel], arrays["win"][sel])
            bad = [str(ids[w]) for w, e in errs.items() if str(ids[w]) not in ref
                   or f"{e:.4f}" != ref[str(ids[w])][col]]
            res[key] = {"windows": len(errs), "mismatches": len(bad), "first": bad[:5]}
            ok &= not bad
        out["bands"][name] = res
    out["pass"] = bool(ok)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capture", choices=sorted(CAPTURES), default=None)
    _evidence.add_argument(ap)
    ap.add_argument("--scale-root", type=Path, default=None,
                    help="with --capture: the e041 scale readouts, <dir>/<capture>/<tag>-windows.csv (the parity CSV)")
    ap.add_argument("--scan", default=None)
    ap.add_argument("--manifest", default=None)
    ap.add_argument("--scan-dpi", type=float, default=None)
    ap.add_argument("--bands", nargs="+", default=None)
    ap.add_argument("--parity-csv", default=None)
    ap.add_argument("--ap07", action="store_true", help="also the 0.7-cell box (doubles the pose work)")
    ap.add_argument("--workers", type=int, default=1,
                    help="threads for the windows (after a bit-identity check against serial); 1 = serial")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    cap = CAPTURES[args.capture] if args.capture else None
    root = (_evidence.resolve(args.evidence_root, tool="cmy_calibration.extract")
            if cap is not None and not (args.scan and args.manifest) else None)
    if cap is not None and args.parity_csv is None and args.scale_root is None:
        raise SystemExit("cmy_calibration.extract: --capture reads its parity CSV under --scale-root DIR "
                         "(or name it with --parity-csv)")
    scan = Path(args.scan) if args.scan else cap.scan_at(root) if cap else None
    manifest = Path(args.manifest) if args.manifest else cap.manifest_at(root) if cap else None
    dpi = args.scan_dpi or (cap.scan_dpi if cap else None)
    bands = tuple(args.bands) if args.bands else cap.bands if cap else None
    if scan is None or manifest is None or dpi is None or bands is None:
        raise SystemExit("need --capture, or --scan --manifest --scan-dpi --bands")
    pcsv = Path(args.parity_csv) if args.parity_csv else cap.windows_csv_at(args.scale_root) if cap else None
    _evidence.need(scan, manifest, tool="cmy_calibration.extract")
    if pcsv is not None:
        _evidence.need(pcsv, tool="cmy_calibration.extract",
                       regenerate=cap.readout_command(root, args.scale_root)
                       if cap is not None and root is not None and not args.parity_csv else "")
    arrays, meta = extract_capture(scan, manifest, float(dpi), bands, args.ap07, workers=args.workers)
    meta["scan_sha256"] = sha256_file(scan)
    meta["scan_bytes"] = scan.stat().st_size
    if cap is not None:
        meta["capture"] = cap.key
        meta["white_expected"] = list(cap.white_rgb)
        if [round(v, 1) for v in meta["white"]] != list(cap.white_rgb):
            print(f"WARNING: page white {meta['white']} != the readout's {cap.white_rgb}")
    if pcsv is not None:
        meta["parity"] = parity_gate(arrays, meta, pcsv)
        print(json.dumps(meta["parity"], indent=1))
    write_cells(Path(args.out), arrays, meta)
    print(f"wrote {args.out}: {meta['n_cells']} cells, {meta['n_windows']} windows, {len(meta['skipped'])} "
          f"skipped, {meta['wall_s']:.1f} s")
    if pcsv is not None and not meta["parity"]["pass"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
