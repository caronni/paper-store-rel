"""E043 — read the M281 cmy probe sheet (docs/CMY-PROBE-M281.md v0.2, §2 the arms, §4 readout and decision).

Inputs: one or more RGB scans of the printed sheet (2400 dpi nominal, --scan-dpi for another; each read on
its own, outputs carry a `scan` column), the emitter's manifest JSON (tag, dpi, page_dots_xy, lookup, five
K fiducials, five c2 bands, the bars, job) and its GT npz ("states": rows x cols presence ids C + 2M + 4Y, the
same field in every band; per scrambled bar its 0/1 dot pattern under the bar's gt_key).

Per scan:
1. page fit: the five K fiducials found and matched (as-is or turned 180 deg) and the mm -> scan affine fitted
   (measure.e041_probe_readout.fit_page, imported); refuses above --max-resid-mm (0.3 mm, e041's default),
   off-scale by more than --scale-tol, mirrored, or with fewer than four fiducials refined;
2. page white: the median of the page's gaps clear of every mark (e041_probe_readout.page_white);
3. per band (measure/cmy_probe/bands.py): hard cell decisions at per-plane poses with one colour table per
   band, cell error per plane and overall, the 4 x 4 confusion (W, C, M, Y), the M / Y pose offsets vs C in
   printed dots (|Y - C| on this print), the in-band lattice score (all three channels over the band) and
   its x-profile over N_SLICES slices with each slice's mean window cell error and mean RGB
   (measure/cmy_probe/profile.py: a screen switched on over SOME of the band's x extent);
   and (CMY-PROBE-M281 §9) the whole-band whitened families (measure/cmy_probe/stipples.py: a stipple riding
   inside the cells shows there and nowhere else);
4. per bar (measure/cmy_probe/bars.py): mean RGB over the interior (8 scan px margin at 2400), THE VERDICT —
   the whitened whole-bar families per ink density, clean / marginal / screened against the sheet's own
   white bars (bars.stipple_bar) — and, kept as legacy columns, the e041 lattice score per lattice, its best
   lattice and its verdict (unscreened iff score <= 18), the strongest off-band peak; the legacy floor
   (white + scrambled bars) and the screened control as the positive reference;
5. per toner and ladder: both edges with their transition values (clean bars), the midpoint, the cross-talk
   along the plateau; a proposed rgb_solid per toner from the single-axis midpoints; the registry bars per
   construct side by side; and per toner (measure/cmy_probe/series.py) the three named ratios along every
   series, the magenta grid (axis "grid") as a table per construct, and a proposed value = the clean bar
   with the smallest ratio sum;
6. when the manifest carries them (sheet 2): the checkerboards (measure/cmy_probe/checkerboards.py: ink
   fraction and dot gain per toner, the 10-90 % edge width, the plane offsets, the families off the
   pattern's harmonics; a composite PNG per pitch) and the dot-level set (measure/cmy_probe/dots.py: on /
   off density and contrast per pattern; a zoom PNG per toner).

Outputs in --out: bars.csv, bands.csv, bands_profile.csv, bands_profile.svg (one per scan, suffixed by the
scan's name when there are several), edges.json ({scan: {toner: {ladders, rgb_solid}}}), summary.json
(fit, white, floor, stipple floor, bands with confusion, profiles and families, bars, edges, registry table,
series, grids, proposals, checkerboards, dots, the manifest's job sizes), with sheet 2's sections
checkerboards.csv, checkerboards-c<cell>.png, dots.csv, dots-<toner>.png (suffixed per scan when several),
and with --spectra one PNG per bar window spectrum (spectra/<scan>/bar-<id>-spec.png).  A human summary on
stdout.

    PYTHONPATH=src:. env/bin/python -m measure.cmy_probe.readout \\
        --scan <captures>/E043-canon-2400rgb.tiff \\
        --manifest build/e043/E043-m281-cmy-probe.manifest.json --gt build/e043/E043-m281-cmy-probe-gt.npz \\
        --out build/e043/readout

The synthetic self-check: measure/cmy_probe/synth.py (plants edges, screens and cross-talk; asserts recovery).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from measure.cmy_probe.bands import band_report
from measure.cmy_probe.bars import (BAR_MARGIN_PX, apply_verdicts, bar_box_mm, edges_report, floor_report, read_bar,
                                    registry_table, white_reference)
from measure.cmy_probe.checkerboards import lattice_exclude, read_checkerboards
from measure.cmy_probe.dots import read_all as read_dots
from measure.cmy_probe.profile import (band_lattice_profile, profile_lines, profile_summary, profile_table,
                                       write_svg)
from measure.cmy_probe.series import (grid_lines, grid_tables, propose, proposal_lines, series_lines,
                                      series_report)
from measure.cmy_probe.stipples import CHANNELS as DENSITIES
from measure.cmy_probe.stipples import FAMILIES
from measure.cmy_probe.stipples import crop as stipple_crop
from measure.cmy_probe.stipples import families, families_local, worst
from measure.cmy_probe.tables import (bands_table, bars_table, checkerboard_lines, checkerboards_table,
                                      dots_table, fmt, write_csv)
from measure.e041_probe_readout import SCAN_DPI_NOMINAL, Scan, fit_page, jsonable, page_white, sub_px_per_dot
from measure.e041_scale_readout import LATTICES, UNSCREENED_MAX, lattice_score

MANIFEST_KEYS = ("tag", "dpi", "page_dots_xy", "lookup", "fiducials", "bands", "bars")
SIZE_KEYS = ("bytes", "data_bytes", "job_bytes")         # per-band job size, copied when the emitter writes one
BAND_INSET_DOTS = (24, 8)                                # the whole-band families' interior (x, y), stipples.py's
TONERS = ("C", "M", "Y")


# ---------------------------------------------------------------- manifest

def load_manifest(path: Path) -> dict[str, Any]:
    man = json.loads(path.read_text())
    missing = [k for k in MANIFEST_KEYS if k not in man]
    if missing:
        raise SystemExit(f"manifest {path} lacks {missing} — contract fork")
    return man


def frame_of(man: dict[str, Any]) -> dict[str, Any]:
    """The fit_page / page_white view: page and fiducials in mm, from the manifest's dots."""
    dpi = float(man["dpi"])
    mm = 25.4 / dpi
    fids = [{"id": f["id"], "x_mm": int(f["x_dots"]) * mm, "y_mm": int(f["y_dots"]) * mm,
             "w_mm": int(f["w_dots"]) * mm, "h_mm": int(f["h_dots"]) * mm} for f in man["fiducials"]]
    return {"dpi": dpi, "page_mm": [float(v) * mm for v in man["page_dots_xy"]], "fiducials": fids}


def mark_rects_mm(man: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    mm = 25.4 / float(man["dpi"])
    return [(int(e["x_dots"]) * mm, int(e["y_dots"]) * mm, (int(e["x_dots"]) + int(e["w_dots"])) * mm,
             (int(e["y_dots"]) + int(e["h_dots"])) * mm)
            for e in [*man["bands"], *man["bars"], *man["fiducials"], *man.get("checkerboards", []), *man.get("dots", [])]]


def band_sizes(band: dict[str, Any], man: dict[str, Any]) -> dict[str, Any]:
    """The band's job size as printed (when the manifest carries one) and its full-page extrapolation: bytes x
    (the page's data field = the page less the band's x margin on every side) / (the band's area)."""
    size = next((band[k] for k in SIZE_KEYS if k in band), None)
    if size is None:
        return {}
    W, H = (int(v) for v in man["page_dots_xy"])
    m = int(band["x_dots"])
    field = (W - 2 * m) * (H - 2 * m)
    return {"bytes": int(size), "full_page_bytes": int(round(int(size) * field / (int(band["w_dots"]) * int(band["h_dots"]))))}


# ---------------------------------------------------------------- one scan

def band_lattice(scan: Scan, A: np.ndarray, band: dict[str, Any], dpi: float) -> dict[str, Any]:
    """The in-band lattice score: the bar method over the band's interior, all three channels."""
    margin_mm = BAR_MARGIN_PX * scan.dpi / SCAN_DPI_NOMINAL / scan.px_per_mm
    lat = lattice_score(scan, A, bar_box_mm(band, dpi, margin_mm), (0, 1, 2))
    return {"lattice_score": lat["score"], "lattice": lat["lattice"], "best_lattice": lat["best_lattice"],
            "lattice_windows": lat["windows"]}


def band_families(scan: Scan, A: np.ndarray, band: dict[str, Any], sub: int, rot_deg: float = 0.0) -> dict[str, Any]:
    """The whole-band whitened families over the band's interior: stipples.families (the radial median, as
    043.3c read sheet 1's bands) and stipples.families_local (the local median: a c3 cell field's anisotropic
    power reads ~60-90 at Y213@45 under the radial median with no stipple at all, ~20 under the local one;
    c2 fields read alike under both).  worst_* from the local form.  The cell lattice's own harmonics
    (checkerboards.lattice_exclude at the cell pitch, cell_dots x sub scan px) are excluded from both forms: a
    random field with any non-linear dot gain carries lines at every lattice harmonic, and a c3 field's
    200 lpi line at 0/90 deg sits inside lines196@90 (sheet 2's first read called it a screen; the refuter of
    2026-10-11 reproduced it on a synthetic field) — that family reads NaN on c3 bands when every searched bin is excluded, else the line's residual leakage (43–56 on sheet 2's c3 bands, 406–926 with the line in).  A c2 field's lattice
    (300 lpi on the axes, 424 lpi on the diagonals) touches no family: its Y213@45 stands, and the C and M
    densities' Y213@45 are its control (a lattice line would show in every density, the yellow stipple in Y)."""
    crop = stipple_crop(scan.img, A, band, *BAND_INSET_DOTS) * scan.scale255
    ex = lattice_exclude(crop.shape[:2], int(band.get("cell_dots", 2)) * sub, rot_deg=rot_deg)
    fam = families(crop, dpi=scan.dpi, exclude=ex)
    loc = families_local(crop, dpi=scan.dpi, exclude=ex)
    ch, f, v = worst(loc)
    return {"families": fam, "families_local": loc, "worst_channel": ch, "worst_family": f, "worst_ratio": v}


def toner_solids(bars: list[dict[str, Any]], lookup: dict[str, list[int]]) -> dict[str, np.ndarray]:
    """Per toner the mean scanned RGB of the sheet's bars at the registry value, a mask construct preferred."""
    out = {}
    for t in TONERS:
        reg = [int(v) for v in lookup.get(t, [])]
        cands = [b for b in bars if b.get("rgb") and [int(v) for v in b["rgb"]] == reg and b["kind"] in ("sweep", "registry")]
        cands.sort(key=lambda b: (not str(b.get("construct", "")).startswith("mask"), b["id"]))
        if cands:
            out[t] = np.asarray(cands[0]["mean_rgb"], np.float64)
    return out


def read_scan(path: Path, man: dict[str, Any], gt: Any, scan_dpi: float, max_resid_mm: float, scale_tol: float,
              spectra_dir: Path | None, png_dir: Path | None = None, suffix: str = "") -> dict[str, Any]:
    dpi = float(man["dpi"])
    sub = sub_px_per_dot(scan_dpi, dpi)
    scan = Scan(path, scan_dpi)
    print(f"{path.name}: {scan.w} x {scan.h} px at {scan_dpi:.0f} dpi ({sub} px per dot), "
          f"{len(man['bands'])} bands, {len(man['bars'])} bars")
    frame = frame_of(man)
    A, fit = fit_page(scan, frame, max_resid_mm, scale_tol)
    white = page_white(scan, A, frame, mark_rects_mm(man))
    print(f"  page white R {white[0]:.1f} G {white[1]:.1f} B {white[2]:.1f}")
    bands = []
    for b in man["bands"]:
        key = b.get("gt_key", "states")
        if key not in gt:
            raise SystemExit(f"band {b['name']}: GT npz lacks '{key}' — contract fork")
        rep = band_report(scan, A, b, np.asarray(gt[key]), dpi, white, sub)
        rep.update(band_lattice(scan, A, b, dpi))
        rep["profile"] = band_lattice_profile(scan, A, b, dpi, err_by_col=rep["window_err_by_col"])
        rep.update(profile_summary(rep["profile"]))
        rep.update(band_sizes(b, man))
        rep.update(band_families(scan, A, b, sub, float(fit.get("rotation_deg", 0.0))))
        rep["cell_dots"] = int(b.get("cell_dots", 2))
        bands.append(rep)
        print(f"  band {b['name']} {b.get('arm')} c{rep['cell_dots']}: cell error {100 * rep['state_err']:.3f} %, "
              f"worst family {rep['worst_family']} in {rep['worst_channel']} {rep['worst_ratio']:.0f}")
    if spectra_dir is not None:
        spectra_dir.mkdir(parents=True, exist_ok=True)
    bars = [read_bar(scan, A, bar, dpi, gt, spectra_dir) for bar in man["bars"]]
    stipple_floor = apply_verdicts(bars)
    cbs, dts = [], []
    pdir = None
    if png_dir is not None and suffix:
        pdir = png_dir / f"png-{suffix}"
        pdir.mkdir(parents=True, exist_ok=True)
    elif png_dir is not None:
        pdir = png_dir
    if man.get("checkerboards"):
        cbs = read_checkerboards(scan, A, man["checkerboards"], dpi, sub, white, toner_solids(bars, man["lookup"]), pdir)
    if man.get("dots"):
        dts = read_dots(scan, A, man["dots"], gt, dpi, white, pdir, toner_solids(bars, man["lookup"]))
    del scan
    wref = white_reference(bars, white)
    return {"scan": str(path), "name": path.stem, "scan_dpi": scan_dpi, "px_per_dot": sub, "fit": fit,
            "page_white": white.tolist(), "white_bars_rgb": wref.tolist(), "bands": bands, "bars": bars,
            "floor": floor_report(bars), "stipple_floor": stipple_floor,
            "edges": edges_report(bars, wref, man["lookup"]), "registry": registry_table(bars),
            "series": series_report(bars), "grids": grid_tables(bars), "proposals": propose(bars, man["lookup"]),
            "checkerboards": cbs, "dots": dts}


# ---------------------------------------------------------------- report

def print_scan_report(r: dict[str, Any], job: dict[str, Any] | None) -> None:
    print(f"\n=== {r['name']} ===")
    print("bands (cell error %: all / C / M / Y; |Y-C| dots; in-band lattice score):")
    for b in r["bands"]:
        pe = b["plane_err"]
        print(f"  {b['name']:4s} {str(b['arm']):6s} {100 * b['state_err']:7.3f} / {100 * pe['C']:6.3f} / "
              f"{100 * pe['M']:6.3f} / {100 * pe['Y']:6.3f}   M-C ({fmt(b['M_dy_vs_C_dots'], 2)}, "
              f"{fmt(b['M_dx_vs_C_dots'], 2)})  Y-C ({fmt(b['Y_dy_vs_C_dots'], 2)}, {fmt(b['Y_dx_vs_C_dots'], 2)})"
              f"  |Y-C| {fmt(b['Y_minus_C_abs_dots'], 2)}   lattice {fmt(b['lattice_score'])} ({b['best_lattice']})"
              + (f"   {b['bytes']} B -> {b['full_page_bytes']} B/page" if "bytes" in b else ""))
    print("whole-band whitened families, local median (the worst over channels per family; noise 10-25; the cell "
          "lattice's harmonics excluded); Y213@45 in Y local / radial, with the C and M densities as the lattice control:")
    for b in r["bands"]:
        per = {f: max((b["families_local"][ch][f] for ch in DENSITIES if np.isfinite(b["families_local"][ch][f])),
                      default=float("nan")) for f in FAMILIES}
        print(f"  {b['name']:4s} {str(b['arm']):6s} c{b['cell_dots']}  " + "  ".join(f"{f} {fmt(v, 0)}" for f, v in per.items())
              + f"   Y213@45 in Y {fmt(b['families_local']['Y']['Y213@45'], 0)} / {fmt(b['families']['Y']['Y213@45'], 0)}"
              + f"  (in C {fmt(b['families_local']['C']['Y213@45'], 0)}, in M {fmt(b['families_local']['M']['Y213@45'], 0)}; NaN = the lattice)")
    print("in-band lattice score per x-slice (page x left to right):")
    for line in profile_lines(r["bands"]):
        print(line)
    sf = r["stipple_floor"]
    print(f"SPECKS (sparse foreign dots, per mm2; clean needs <= {sf['specks_max']}): white bars {[round(v, 2) for v in sf['white_specks']]}")
    print(f"VERDICT bar: white bars' worst family {[round(v, 1) for v in sf['white']]} -> max {fmt(sf['white_max'])}; "
          f"clean <= {sf['clean_max']:.1f}, marginal <= {sf['marginal_max']:.1f}, else screened; scrambled "
          f"{[round(v, 1) for v in sf['scrambled']]}; screened control {[round(v, 1) for v in sf['screened']]} — "
          f"{'discriminating' if sf['discriminating'] else 'NOT DISCRIMINATING on this sheet'}")
    fl = r["floor"]
    print(f"legacy lattice floor: white {[round(v, 1) for v in fl['white']]}  scrambled {[round(v, 1) for v in fl['scrambled']]}"
          f"  max {fmt(fl['floor_max'])}; screened control {[round(v, 1) for v in fl['screened']]}; verdict bar "
          f"{UNSCREENED_MAX:g} — {'discriminating' if fl['discriminating'] else 'NOT DISCRIMINATING on this sheet'}")
    print("series (the three named ratios per toner by swept value; measure/cmy_probe/series.py):")
    for line in series_lines(r["series"]):
        print(line)
    if r["grids"]:
        print("magenta grid (rows R, columns B):")
        for line in grid_lines(r["grids"]):
            print(line)
    else:
        print("magenta grid: no axis-'grid' bars on this sheet")
    print("proposals (the registry value when any of its bars is clean, else the clean bar with the smallest ratio sum; per construct the smallest sum):")
    for line in proposal_lines(r["proposals"]):
        print(line)
    print("ladders (clean bars; swept value: lower edge [transition] .. upper edge [transition] -> midpoint; "
          "plateau cross-talk):")
    for toner, e in r["edges"].items():
        for key, L in e["ladders"].items():
            if L["midpoint"] is None:
                print(f"  {toner} {key:12s} no clean bar (worst ratios {fmt(min(L['scores']))}..{fmt(max(L['scores']))})")
                continue
            lt = "open" if L["lower_open"] else L["lower_transition"]
            ut = "open" if L["upper_open"] else L["upper_transition"]
            holes = f" holes {L['holes']}" if L["holes"] else ""
            print(f"  {toner} {key:12s} {L['lower']:3d} [{lt}] .. {L['upper']:3d} [{ut}] -> {L['midpoint']:3d}  "
                  f"xt {fmt(L['crosstalk_mean'])} (slope {fmt(L['crosstalk_slope_per_unit'], 3)}/unit){holes}")
        p = e["rgb_solid"]
        print(f"  {toner} proposed rgb_solid {tuple(p['rgb'])} (registry {tuple(p['registry'])})")
    print("registry bars per construct (worst family ratio, foreign specks per mm2, verdict; legacy lattice score):")
    for toner, cs in r["registry"].items():
        print(f"  {toner}: " + "  ".join(f"{c} {fmt(v['worst_ratio'], 0)} sp {fmt(v.get('specks_max'), 1)} {v['verdict']} ({fmt(v['legacy_score'])})"
                                         for c, v in sorted(cs.items())))
    if r["checkerboards"]:
        print("checkerboards (per toner: ink fraction (mean coverage), dot gain % area / edge growth dots, 10-90 edge um, "
              "offset vs manifest dots; relative offset pair[1] - pair[0]; worst family off the pattern):")
        for line in checkerboard_lines(r["checkerboards"]):
            print(line)
    if r["dots"]:
        print("dots (density on / off / white, contrast (on - off) / (on - white), on-dots above the midpoint):")
        for d in r["dots"]:
            print(f"  {d['toner']} {d['pattern']:8s} {d['mean_on']:6.1f} / {d['mean_off']:6.1f} / {d['white']:5.1f}  "
                  f"contrast {d['contrast']:.3f}  on>mid {d['on_above_mid']:.3f}  shift {d['shift_dots']} dots")
    if job:
        print(f"job: {job.get('file')} {job.get('bytes')} B sha256 {str(job.get('sha256'))[:16]}...")


def run(scans: list[Path], manifest: Path, gt_path: Path, out: Path, scan_dpi: float = SCAN_DPI_NOMINAL,
        spectra: bool = False, max_resid_mm: float = 0.3, scale_tol: float = 0.01) -> dict[str, Any]:
    """The readout end to end; returns the summary it writes."""
    man = load_manifest(manifest)
    gt = np.load(gt_path)
    out.mkdir(parents=True, exist_ok=True)
    res = [read_scan(p, man, gt, scan_dpi, max_resid_mm, scale_tol, (out / "spectra" / p.stem) if spectra else None,
                     out, p.stem if len(scans) > 1 else "") for p in scans]
    write_csv(out / "bars.csv", *bars_table(res))
    write_csv(out / "bands.csv", *bands_table(res))
    extra = []
    if any(r["checkerboards"] for r in res):
        write_csv(out / "checkerboards.csv", *checkerboards_table(res))
        extra.append("checkerboards.csv, checkerboards-c*.png")
    if any(r["dots"] for r in res):
        write_csv(out / "dots.csv", *dots_table(res))
        extra.append("dots.csv, dots-*.png")
    write_csv(out / "bands_profile.csv", *profile_table(res))
    for r in res:
        write_svg(out / ("bands_profile.svg" if len(res) == 1 else f"bands_profile-{r['name']}.svg"), r["bands"],
                  f"{man['tag']} {r['name']}")
    (out / "edges.json").write_text(json.dumps(jsonable({r["name"]: r["edges"] for r in res}), indent=1))
    summary = {"tag": man["tag"], "manifest": str(manifest), "gt": str(gt_path), "job": man.get("job"),
               "verdict": "whitened whole-bar families per ink density (measure/cmy_probe/stipples.py); clean iff "
                          "every family in every channel <= max(STIPPLE_NOISE_MIN, white-bar max + STIPPLE_MARGIN), "
                          "marginal up to MARGINAL_FACTOR x that (measure/cmy_probe/bars.py)",
               "families": {k: {"lpi": f, "angles_deg": list(a)} for k, (f, a) in FAMILIES.items()},
               "unscreened_max_legacy": UNSCREENED_MAX, "bar_margin_px_at_2400": BAR_MARGIN_PX,
               "lattices": {k: {"cycles_per_px_at_2400": f, "angles_deg": list(a)} for k, (f, a) in LATTICES.items()},
               "classifier": "one colour table per band: nearest class mean in RGB, means fitted on every read "
                             "cell of the band with its GT label (e041's 'band' classifier); R at C's pose, "
                             "G at M's, B at Y's (e041_mixture_readout.plane_poses)",
               "scans": res}
    (out / "summary.json").write_text(json.dumps(jsonable(summary), indent=1))
    for r in res:
        print_scan_report(r, man.get("job"))
    print(f"\nwrote {out}/bars.csv, bands.csv, bands_profile.csv, bands_profile*.svg, edges.json, summary.json"
          + (", spectra/" if spectra else "") + "".join(", " + e for e in extra))
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", required=True, nargs="+", help="RGB TIFF scan(s) of the printed sheet")
    ap.add_argument("--scan-dpi", type=float, default=SCAN_DPI_NOMINAL, help="the scans' resolution")
    ap.add_argument("--manifest", required=True, help="the emitter's <tag>.manifest.json")
    ap.add_argument("--gt", required=True, help="the emitter's <tag>-gt.npz")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--spectra", action="store_true", help="write one PNG per bar window spectrum")
    ap.add_argument("--max-resid-mm", type=float, default=0.3, help="refuse above this fiducial residual")
    ap.add_argument("--scale-tol", type=float, default=0.01, help="allowed relative scale error vs --scan-dpi")
    a = ap.parse_args()
    run([Path(s) for s in a.scan], Path(a.manifest), Path(a.gt), Path(a.out), a.scan_dpi, a.spectra,
        a.max_resid_mm, a.scale_tol)


if __name__ == "__main__":
    main()
