"""CLI: one colour discovery capture -> build/mic/<engine>/.

    PYTHONPATH=src:. env/bin/python -m measure.mic_discovery \\
        --evidence-root DIR --capture \\
        paper-store-evidence-holo-2026-10/031-xerox-altalink-discovery/discovery/captures/discovery-color-canon-4800rgb.tiff \\
        --out build/mic/altalink-c8245

Writes ``lattice.json``, ``cell.png`` (with ``cell-tiled.png``, the
pattern over two cells each way), ``crop-1to1.png`` (with
``crop-deficit.png``, its blue deficit), ``decode.json`` and
``report-strip.json``.  Colour HCAL discovery captures ONLY (owner's
ruling D5, 2026-10-09): never point it at a payload sheet.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial import cKDTree

from measure import _evidence

from . import capture as cap
from . import docucolor, lattice, render, strip

WINDOW_MM: float = 20.0
WINDOW_STEP_MM: float = 10.0
BLANK_WINDOWS: int = 4
PRINTED_WINDOWS: int = 2
CROP_MM: float = 8.0

#: A printed lattice sits where its neighbours put it: 0.013-0.03 mm on
#: the Xerox and Canon captures, 0.05 on the HP ones (faint dots among
#: scatter); 0.15 was the M281 with the scatter admitted.  Above this
#: the "lattice" is a periodicity in noise, not a dot pattern.
LOCAL_RMS_MAX_MM: float = 0.08

#: Fewer indexed dots than this is not a lattice (a page of paper specks
#: indexes a handful by chance).
MIN_INDEXED: int = 30


def _windows(maps: cap.PageMaps) -> list[tuple[str, float, float, float]]:
    """(kind, x_mm, y_mm, blank fraction) — the blankest windows and the
    most printed ones, centres on a 10 mm grid, non-overlapping per kind."""
    nb = int(round(WINDOW_MM / maps.blocks_mm))
    step = int(round(WINDOW_STEP_MM / maps.blocks_mm))
    h, w = maps.blank.shape
    scored = []
    for y in range(0, h - nb + 1, step):
        for x in range(0, w - nb + 1, step):
            paper = maps.paper[y:y + nb, x:x + nb].mean()
            if paper < 0.95:
                continue
            blank = float(maps.blank[y:y + nb, x:x + nb].mean())
            scored.append((blank, (x + nb / 2) * maps.blocks_mm, (y + nb / 2) * maps.blocks_mm))
    out: list[tuple[str, float, float, float]] = []
    for kind, order in (("blank", sorted(scored, reverse=True)), ("printed", sorted(scored))):
        chosen: list[tuple[float, float]] = []
        limit = BLANK_WINDOWS if kind == "blank" else PRINTED_WINDOWS
        for blank, x, y in order:
            if all(max(abs(x - cx), abs(y - cy)) >= WINDOW_MM for cx, cy in chosen):
                chosen.append((x, y))
                out.append((kind, x, y, blank))
            if len(chosen) == limit:
                break
    return out


def window_lattice(capture: cap.Capture, stats: cap.YellowStats, kind: str,
                   x_mm: float, y_mm: float, blank: float) -> lattice.WindowLattice:
    f = cap.decimation_factor(capture.dpi)
    half = capture.px(WINDOW_MM / 2)
    cy, cx = capture.px(y_mm), capture.px(x_mm)
    native = capture.array[max(0, cy - half):cy + half, max(0, cx - half):cx + half]
    rgb = cap.box_decimate(native, f)
    wdpi = capture.dpi / f
    white = cap.block_white(rgb, int(round(cap.WHITE_BLOCK_MM / cap.MM_PER_INCH * wdpi)),
                            0.85 * np.asarray(stats.paper_white_rgb, np.float32))
    d, rg = cap.blue_deficit(rgb, white)
    sparse = np.where((d > stats.threshold_low) & (rg >= cap.INK_RG_REFLECTANCE),
                      d - stats.threshold_low, 0.0).astype(np.float64)
    vec, z = lattice.autocorrelation_peaks(sparse, wdpi / cap.MM_PER_INCH)
    basis = lattice.lattice_from_peaks(vec, z)
    return lattice.WindowLattice(
        centre_mm=(x_mm, y_mm), kind=kind, blank_fraction=blank, n_peaks=len(vec),
        a_mm=None if basis is None else (float(basis[0][0]), float(basis[0][1])),
        b_mm=None if basis is None else (float(basis[1][0]), float(basis[1][1])),
        peak_z=float(z.max()) if len(z) else 0.0)


def _densest(xy_mm: np.ndarray) -> tuple[float, float]:
    """The indexed dot with the most indexed dots within half a crop:
    the crop then shows the pattern, not a page edge."""
    counts = cKDTree(xy_mm).query_ball_point(xy_mm, CROP_MM / 2, return_length=True)
    k = int(np.argmax(counts))
    return float(xy_mm[k, 0]), float(xy_mm[k, 1])


def _dots600(v: np.ndarray) -> list[float]:
    return [round(float(c) / cap.MM_PER_INCH * 600.0, 3) for c in v]


def analyse(capture_path: Path, out: Path, label: str) -> dict[str, Any]:
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    capture = cap.open_capture(capture_path)
    stats = cap.yellow_stats(capture)
    maps = cap.band_pass(capture, stats)
    t_pass = time.time() - t0
    blank_mm2 = float(maps.blank.sum() * maps.blocks_mm ** 2)
    xy = np.column_stack([maps.blobs[:, 1], maps.blobs[:, 0]]) / maps.working_dpi * cap.MM_PER_INCH
    in_blank = maps.blank_at_mm(xy[:, 1], xy[:, 0]) if len(xy) else np.zeros(0, bool)
    dots_xy = xy[in_blank]
    windows = [window_lattice(capture, stats, *w) for w in _windows(maps)]
    lat: dict[str, Any] = {
        "label": label, "capture": str(capture_path), "capture_dpi": capture.dpi,
        "working_dpi": maps.working_dpi, "units": "capture mm (scanner nominal scale)",
        "yellow": {"paper_white_rgb": [round(v, 4) for v in stats.paper_white_rgb],
                   "deficit_median": round(stats.deficit_median, 5),
                   "deficit_sigma": round(stats.deficit_sigma, 5),
                   "threshold_high": round(stats.threshold_high, 5),
                   "threshold_low": round(stats.threshold_low, 5)},
        "blank_paper_mm2": round(blank_mm2, 1),
        "candidates_in_blank": int(in_blank.sum()),
        "candidate_density_per_mm2": round(in_blank.sum() / max(blank_mm2, 1e-9), 4),
        "windows": [w.to_dict() for w in windows],
    }
    decode: dict[str, Any] = {"scheme": "Xerox DocuColor 15x8 (EFF 2005), see docucolor.py"}
    page_vec, page_z = lattice.pair_vector_peaks(dots_xy)
    page_basis = lattice.lattice_from_peaks(page_vec, page_z)
    lat["page_pairs"] = {
        "n_candidates": int(len(dots_xy)), "n_peaks": int(len(page_vec)),
        "best_peak_z": round(float(page_z.max()), 1) if len(page_z) else 0.0,
        "a_mm_xy": None if page_basis is None else [round(float(v), 4) for v in page_basis[0]],
        "b_mm_xy": None if page_basis is None else [round(float(v), 4) for v in page_basis[1]],
    }
    good = [w for w in windows if w.kind == "blank" and w.a_mm is not None]
    fit = None
    folded = None
    occ = None
    page_centre = (capture.mm(capture.width_px / 2), capture.mm(capture.height_px / 2))
    anchor_xy = (max(good, key=lambda w: w.peak_z).centre_mm if good
                 else windows[0].centre_mm if windows else page_centre)
    if page_basis is not None and len(dots_xy) >= MIN_INDEXED:
        a, b = page_basis
        source = "page-wide pair histogram"
    elif good and len(dots_xy) >= MIN_INDEXED:
        best = max(good, key=lambda w: w.peak_z)
        a, b = np.array(best.a_mm), np.array(best.b_mm)
        source = f"window at {best.centre_mm}"
    else:
        a = b = None
    if a is not None:
        seed = lattice.best_seed(dots_xy, a, b)
        fit = lattice.fit_sites(dots_xy, a, b, seed)
        if len(fit.ij) < MIN_INDEXED:
            lat["lattice_refused"] = (f"{len(fit.ij)} candidates index onto the {source} lattice "
                                      f"(< {MIN_INDEXED}): no MIC lattice")
            fit = None
        elif not fit.local_rms_mm <= LOCAL_RMS_MAX_MM:
            lat["lattice_refused"] = (f"{len(fit.ij)} candidates index onto the {source} lattice "
                                      f"{list(np.round(a, 4))}, {list(np.round(b, 4))} mm but sit "
                                      f"{fit.local_rms_mm:.3f} mm rms off their sites "
                                      f"(> {LOCAL_RMS_MAX_MM}): a periodicity, not a dot lattice")
            fit = None
    if fit is not None:
        try:
            occ = lattice.occupancy(fit, lambda x, y: maps.blank_at_mm(y, x))
        except ValueError as exc:
            lat["lattice_refused"] = str(exc)
            fit = None
    if fit is not None:
        cross = abs(a[0] * b[1] - a[1] * b[0])
        known = occ.matrix >= 0
        lat["lattice"] = {
            "source": source,
            "a_mm_xy": [round(float(v), 4) for v in fit.a_mm],
            "b_mm_xy": [round(float(v), 4) for v in fit.b_mm],
            "a_len_mm": round(float(np.hypot(*a)), 4), "b_len_mm": round(float(np.hypot(*b)), 4),
            "a_dots600_xy": _dots600(a), "b_dots600_xy": _dots600(b),
            "angle_deg": round(float(np.degrees(np.arccos(a @ b / np.hypot(*a) / np.hypot(*b)))), 2),
            "site_density_per_mm2": round(1.0 / cross, 4),
            "fitted_a_mm_xy_at_seed": [round(float(fit.coef_x[1]), 5), round(float(fit.coef_y[1]), 5)],
            "fitted_b_mm_xy_at_seed": [round(float(fit.coef_x[2]), 5), round(float(fit.coef_y[2]), 5)],
            "dots_indexed": int(len(fit.ij)), "candidates_not_on_lattice": fit.n_rejected,
            "dot_density_per_mm2": round(len(fit.ij) / max(blank_mm2, 1e-9), 4),
            "local_rms_mm": round(fit.local_rms_mm, 4),
            "page_quadratic_rms_mm": round(fit.rms_mm, 4),
            "sites_known": int(known.sum()),
            "occupancy_fraction": round(float((occ.matrix == 1).sum() / max(1, known.sum())), 4),
        }
        rep, table = lattice.find_repeat(occ, a, b)
        lat["repeat_candidates"] = table
        if rep is not None:
            cell, transposed = lattice.best_cell(rep.r1, rep.r2)
            folded = lattice.fold(occ, cell, transposed)
            v1 = rep.r1[0] * a + rep.r1[1] * b
            v2 = rep.r2[0] * a + rep.r2[1] * b
            lat["repeat"] = {
                "r1_sites": list(rep.r1), "r2_sites": list(rep.r2),
                "r1_mm_xy": [round(float(c), 3) for c in v1], "r2_mm_xy": [round(float(c), 3) for c in v2],
                "agreement": [round(x, 4) for x in rep.agreement], "pairs": list(rep.pairs),
                "cell_hermite_a_b_c": list(cell),
                "cell_wraps_along": "columns (j)" if transposed else "rows (i)",
                "cell_page_shape_rows_cols": list(folded.page_value.shape),
                "cell_sites": cell[0] * cell[2],
                "cell_dots": int((folded.value == 1).sum()),
                "cell_unobserved": int((folded.value < 0).sum()),
                "observations_per_site_median": float(np.median(folded.seen)),
                "fold_consistency": round(folded.consistency, 4),
            }
            render.cell_png(folded.page_value, out / "cell.png")
            rows_p, cols_p = folded.page_value.shape
            render.cell_png(render.tiled(folded.at, 2 * cols_p, 2 * rows_p), out / "cell-tiled.png")
            jj, ii = np.mgrid[0:rows_p, 0:cols_p]
            origins = np.column_stack([ii.ravel(), jj.ravel()])
            hits, trials = docucolor.search(folded.at, origins, site_key=folded.key)
            decode["searched"] = "folded cell (toroidal)"
        else:
            m, (i0, j0) = occ.matrix, occ.origin

            def raw_at(i: np.ndarray, j: np.ndarray) -> np.ndarray:
                r, c = j - j0, i - i0
                ok = (r >= 0) & (c >= 0) & (r < m.shape[0]) & (c < m.shape[1])
                outv = np.full(np.shape(i), -1, np.int8)
                outv[ok] = m[r[ok], c[ok]]
                return outv

            jj, ii = np.nonzero(m >= 0)
            origins = np.column_stack([ii + i0, jj + j0])
            hits, trials = docucolor.search(raw_at, origins)
            decode["searched"] = "raw site matrix (no repeat found)"
        decode["trials"] = trials
        decode["expected_chance_hits"] = round(docucolor.expected_chance_hits(trials), 4)
        decode["hits"] = len(hits)
        distinct: dict[bytes, dict[str, Any]] = {}
        for h in hits:
            key = h.block.tobytes()
            if key not in distinct:
                distinct[key] = {"origin_ij": list(h.origin_ij), "orientation": h.orientation,
                                 "stride": h.stride, "parity": h.parity, "count": 0,
                                 "block_rows": ["".join(str(int(v)) for v in row) for row in h.block],
                                 **docucolor.decode(h.block)}
            distinct[key]["count"] += 1
        decode["distinct_blocks"] = list(distinct.values())[:20]
        plausible = [blk for blk in distinct.values() if blk["fields_plausible"]]
        if trials == 0:
            decode["verdict"] = (f"no 15x8 placement carries {docucolor.MIN_DATA_DOTS}+ data dots: "
                                 "too sparse for a DocuColor block")
        elif not hits:
            decode["verdict"] = "no parity-consistent block"
        elif not plausible:
            decode["verdict"] = (f"{len(distinct)} parity-consistent placement(s), fields implausible "
                                 f"under the DocuColor reading (chance expectation "
                                 f"{decode['expected_chance_hits']})")
        else:
            decode["verdict"] = (f"{len(plausible)} parity-consistent block(s) with plausible fields "
                                 f"(chance expectation {decode['expected_chance_hits']})")
        centre = _densest(fit.xy_mm)
    else:
        decode["verdict"] = "no MIC lattice found on blank paper"
        decode["trials"] = 0
        centre = anchor_xy
    lat["crop_box_px_y0x0y1x1"] = render.crop_pngs(
        capture, (float(centre[0]), float(centre[1])), CROP_MM, stats.paper_white_rgb,
        out / "crop-1to1.png", out / "crop-deficit.png")
    if folded is None:
        render.cell_png(np.full((1, 1), -1, np.int8), out / "cell.png")
    report = strip.find_strips(maps.luma600, maps.luma600_dpi)
    lat["wall_seconds"] = {"band_pass": round(t_pass, 1), "total": round(time.time() - t0, 1)}
    (out / "lattice.json").write_text(json.dumps(lat, indent=1) + "\n")
    (out / "decode.json").write_text(json.dumps(decode, indent=1) + "\n")
    (out / "report-strip.json").write_text(json.dumps(report, indent=1) + "\n")
    return {"lattice": lat, "decode": decode, "report": report}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m measure.mic_discovery", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    _evidence.add_argument(parser)
    parser.add_argument("--capture", required=True, type=Path,
                        help="the colour discovery capture, relative to the evidence root")
    parser.add_argument("--out", required=True, type=Path, help="output directory, e.g. build/mic/<engine>")
    parser.add_argument("--label", default=None, help="engine label for the JSON (default: --out's name)")
    args = parser.parse_args(argv)
    root = _evidence.resolve(args.evidence_root, tool="mic_discovery")
    result = analyse(root / args.capture, args.out, args.label or args.out.name)
    lat, dec = result["lattice"], result["decode"]
    print(f"{lat['label']}: lattice {lat.get('lattice', {}).get('a_len_mm')} x "
          f"{lat.get('lattice', {}).get('b_len_mm')} mm; repeat "
          f"{lat.get('repeat', {}).get('cell_page_shape_rows_cols')}; "
          f"decode: {dec['verdict']}; strips: {len(result['report']['strips'])}; "
          f"wall {lat['wall_seconds']['total']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
