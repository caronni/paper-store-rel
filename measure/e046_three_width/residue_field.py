"""e046 — where the residue was, stage by stage, and the page field (2026-10-13).  MEASUREMENT ONLY.

Inputs: the receiver's fact snapshots of M1 and M2 (`Certificate`, `PlaneField`) and the analyzer passes'
`mints.jsonl` (A1, A2, A3 on M1's chain; A4 on M2's).  Per plane, the certified set on the 53x37 tile grid after
M1, A1, A2, A3, M2 and A4; per-column / per-row certified fractions after M1 and at the end with the bands that
fall below the page mean; where each pass's certificates landed; the final residue; the standing page fields of
M1 and M2 (cmy8's gauge F_C + F_M = 0, Y free: lib/field_gauge.py) — mean, spread, the dominant period along
each page axis — and the correlation of the per-column / per-row / per-tile certified state after M1 with the
field's magnitude.  Writes `residue_field.json` and `residue_field.png` (PIL) to --out.

    cd <repo> && PYTHONPATH=src:. env/bin/python -m measure.e046_three_width.residue_field \\
        --runs scratch/e046/runs --out scratch/e046/analysis/spatial
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.stats import pearsonr, spearmanr

from holo.receiver import data, snapshot
from measure.e044_cmy_truth.compare_page_fields import sinusoid

PLANES: tuple[str, ...] = ("C", "M", "Y")
TILES_YX: tuple[int, int] = (53, 37)
CELL_DOTS: int = 2
TILE_MM: float = 64 * CELL_DOTS * 25.4 / 600
ORIGIN_DOTS_YX: tuple[int, int] = (116, 112)            # build/e046/A/manifest.json
STAGES: tuple[str, ...] = ("M1", "A1", "A2", "A3", "M2", "A4")
PERIODS_MM: np.ndarray = np.arange(20.0, 300.5, 1.0)

Key = tuple[int, int, int]


def certs_of(facts: tuple[object, ...]) -> set[Key]:
    return {(c.ty, c.tx, PLANES.index(c.stream_id)) for c in facts
            if isinstance(c, data.Certificate) and c.page == 0}


def mints_of(path: Path) -> list[dict]:
    rows = [json.loads(line) for line in path.open()]
    return [r for r in rows if r.get("type") == "row" and r["verdict"] == "certified" and r["page"] == 0]


def grid(keys: set[Key], plane: int) -> np.ndarray:
    g = np.zeros(TILES_YX, bool)
    for ty, tx, p in keys:
        if p == plane:
            g[ty, tx] = True
    return g


def bands(frac: np.ndarray, n: int) -> tuple[float, float, list[dict]]:
    """Runs of indices whose certified fraction sits more than two binomial sds (at the page mean, n tiles per
    line) under the page mean."""
    mean = float(frac.mean())
    bar = mean - 2.0 * np.sqrt(max(mean * (1 - mean), 1e-9) / n)
    low = frac < bar
    out, i = [], 0
    while i < len(frac):
        if low[i]:
            j = i
            while j + 1 < len(frac) and low[j + 1]:
                j += 1
            out.append({"from": i, "to": j, "min": round(float(frac[i:j + 1].min()), 3),
                        "mean": round(float(frac[i:j + 1].mean()), 3),
                        "mm_from_matrix_origin": [round(i * TILE_MM, 1), round((j + 1) * TILE_MM, 1)]})
            i = j + 1
        else:
            i += 1
    return mean, bar, out


def best_period(coord_mm: np.ndarray, prof: np.ndarray, detrend: bool) -> dict:
    v = prof - prof.mean()
    if detrend:
        v = v - np.polyval(np.polyfit(coord_mm, v, 1), coord_mm)
    span = coord_mm[-1] - coord_mm[0] + TILE_MM
    fits = [(p, *sinusoid(coord_mm, v, p)) for p in PERIODS_MM if p <= 1.5 * span]
    p, amp, phase, r2 = max(fits, key=lambda t: t[3])
    return {"period_mm": float(p), "amplitude_dots": round(float(amp), 3), "phase_deg": round(float(phase), 1),
            "r2": round(float(r2), 3), "profile_rms_dots": round(float(np.sqrt((v ** 2).mean())), 3),
            "profile_ptp_dots": round(float(v.max() - v.min()), 3), "span_mm": round(float(span), 1)}


def field_summary(fields: dict[int, data.PlaneField]) -> dict:
    ys = (np.arange(TILES_YX[0]) + 0.5) * TILE_MM
    xs = (np.arange(TILES_YX[1]) + 0.5) * TILE_MM
    out = {}
    for p, f in sorted(fields.items()):
        d = np.asarray(f.delta_dots_xy, np.float64)
        m = np.asarray(f.support) > 0
        rec = {"n_observations": int(f.n_observations), "n_captures": int(f.n_captures),
               "ordinal": int(f.ordinal), "support_fraction": round(float(m.mean()), 4)}
        for c, name in ((0, "dx"), (1, "dy")):
            v = np.where(m, d[..., c], np.nan)
            rec[name] = {"mean": round(float(np.nanmean(v)), 3), "sd": round(float(np.nanstd(v)), 3),
                         "p05": round(float(np.nanpercentile(v, 5)), 3),
                         "p95": round(float(np.nanpercentile(v, 95)), 3)}
            along_x = np.nanmean(v, axis=0)
            along_y = np.nanmean(v, axis=1)
            rec[name]["along_x"] = {"raw": best_period(xs, along_x, False), "detrended": best_period(xs, along_x, True),
                                    "profile": [round(float(t), 3) for t in along_x]}
            rec[name]["along_y"] = {"raw": best_period(ys, along_y, False), "detrended": best_period(ys, along_y, True),
                                    "profile": [round(float(t), 3) for t in along_y]}
        mag = np.where(m, np.hypot(d[..., 0], d[..., 1]), np.nan)
        rec["mag"] = {"mean": round(float(np.nanmean(mag)), 3), "max": round(float(np.nanmax(mag)), 3)}
        out[PLANES[p]] = rec
    return out


def correlate(cert: np.ndarray, d: np.ndarray) -> dict:
    """Spearman of per-column / per-row certified fraction with the mean |dx|, |dy|, |d| over that line, and
    per tile (certified 0/1 vs the magnitude)."""
    out = {}
    comps = {"abs_dx": np.abs(d[..., 0]), "abs_dy": np.abs(d[..., 1]), "mag": np.hypot(d[..., 0], d[..., 1]),
             "dx": d[..., 0], "dy": d[..., 1]}
    for name, v in comps.items():
        rc, pc = spearmanr(cert.mean(0), v.mean(0))
        rr, pr = spearmanr(cert.mean(1), v.mean(1))
        rt, pt = spearmanr(cert.ravel().astype(float), v.ravel())
        out[name] = {"per_column": [round(float(rc), 3), float(f"{pc:.2g}")],
                     "per_row": [round(float(rr), 3), float(f"{pr:.2g}")],
                     "per_tile": [round(float(rt), 3), float(f"{pt:.2g}")],
                     "mean_uncert": round(float(v[~cert].mean()), 3) if (~cert).any() else None,
                     "mean_cert": round(float(v[cert].mean()), 3)}
    return out


def relative_offsets(cert: dict[int, np.ndarray], fields: dict[int, data.PlaneField]) -> dict:
    """Per plane, its certified state after M1 per tile against the gauge-free PAIRWISE offsets (C-M = 2 F_C,
    Y-C, Y-M, each axis): Spearman per tile and per column, and the certified fraction in quantile bins of the
    offset."""
    d = {p: np.asarray(f.delta_dots_xy, np.float64) for p, f in fields.items()}
    pairs = {"C-M": d[0] - d[1], "Y-C": d[2] - d[0], "Y-M": d[2] - d[1]}
    out = {}
    for p, name in enumerate(PLANES):
        rec = {}
        for pair, v in pairs.items():
            for c, axis in ((0, "x"), (1, "y")):
                comp = v[..., c]
                rt, pt = spearmanr(cert[p].ravel().astype(float), comp.ravel())
                rc, pc = spearmanr(cert[p].mean(0), comp.mean(0))
                edges = np.quantile(comp, np.linspace(0, 1, 9))
                idx = np.clip(np.searchsorted(edges, comp, side="right") - 1, 0, 7)
                rec[f"{pair} {axis}"] = {
                    "per_tile_spearman": [round(float(rt), 3), float(f"{pt:.2g}")],
                    "per_column_spearman": [round(float(rc), 3), float(f"{pc:.2g}")],
                    "octile_bins": [{"lo": round(float(edges[i]), 3), "hi": round(float(edges[i + 1]), 3),
                                     "certified": round(float(cert[p][idx == i].mean()), 3),
                                     "n": int((idx == i).sum())} for i in range(8)]}
        out[name] = rec
    cols = {f"{pair} {axis}": v[..., c].mean(0) for pair, v in pairs.items() for c, axis in ((0, "x"), (1, "y"))}
    names = sorted(cols)
    out["column_profile_spearman_between_offsets"] = {
        f"{a} ~ {b}": round(float(spearmanr(cols[a], cols[b])[0]), 3)
        for i, a in enumerate(names) for b in names[i + 1:]}
    return out


STAGE_RGB = {"M1": (215, 215, 215), "A1": (40, 90, 220), "A2": (0, 190, 220), "A3": (30, 160, 60),
             "M2": (240, 150, 0), "A4": (200, 0, 200), "open": (230, 0, 0)}
PX = 6


def tile_panel(colors: np.ndarray, title: str) -> Image.Image:
    h, w = TILES_YX
    img = Image.new("RGB", (w * PX + 2, h * PX + 16), "white")
    arr = np.kron(colors, np.ones((PX, PX, 1), np.uint8))
    img.paste(Image.fromarray(arr), (1, 15))
    ImageDraw.Draw(img).text((2, 2), title, fill="black")
    return img


def field_colors(v: np.ndarray, scale: float) -> np.ndarray:
    t = np.clip(v / scale, -1, 1)
    out = np.full(v.shape + (3,), 255, np.float64)
    pos, neg = t > 0, t < 0
    out[pos, 1] -= 255 * t[pos]
    out[pos, 2] -= 255 * t[pos]
    out[neg, 0] += 255 * t[neg]
    out[neg, 1] += 255 * t[neg]
    return out.astype(np.uint8)


def figure(stage_of: dict[Key, str], fields: dict[int, data.PlaneField], path: Path) -> None:
    panels: list[list[Image.Image]] = []
    for p, name in enumerate(PLANES):
        m1 = np.full(TILES_YX + (3,), 255, np.uint8)
        taken = np.full(TILES_YX + (3,), 255, np.uint8)
        resid = np.full(TILES_YX + (3,), 255, np.uint8)
        for ty in range(TILES_YX[0]):
            for tx in range(TILES_YX[1]):
                s = stage_of.get((ty, tx, p), "open")
                if s == "M1":
                    m1[ty, tx] = (60, 60, 60)
                    taken[ty, tx] = STAGE_RGB["M1"]
                else:
                    taken[ty, tx] = STAGE_RGB[s]
                if s == "open":
                    resid[ty, tx] = STAGE_RGB["open"]
        panels.append([tile_panel(m1, f"{name} after M1"), tile_panel(taken, f"{name} by stage"),
                       tile_panel(resid, f"{name} final open")])
    row = []
    for p in (1, 2):
        d = np.asarray(fields[p].delta_dots_xy, np.float64)
        scale = float(np.abs(d).max())
        for c, cname in ((0, "dx"), (1, "dy")):
            row.append(tile_panel(field_colors(d[..., c], scale), f"{PLANES[p]} {cname} +-{scale:.2f}"))
    panels.append(row)
    pw, ph = panels[0][0].size
    legend_h = 30
    sheet = Image.new("RGB", (4 * pw + 10, 4 * ph + legend_h), "white")
    for r, line in enumerate(panels):
        for c, im in enumerate(line):
            sheet.paste(im, (c * (pw + 2), r * ph))
    dr = ImageDraw.Draw(sheet)
    x = 4
    for k, rgb in STAGE_RGB.items():
        dr.rectangle((x, 4 * ph + 8, x + 10, 4 * ph + 18), fill=rgb)
        dr.text((x + 13, 4 * ph + 7), k, fill="black")
        x += 50
    dr.text((x, 4 * ph + 7), "field: red +, blue -; rows = y (long axis, 53), cols = x (short, 37)", fill="black")
    sheet.save(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    m1_facts = snapshot.read(next((args.runs / "M1").glob("rundir.*")) / "facts.npz")
    m2_facts = snapshot.read(next((args.runs / "M2").glob("rundir.*")) / "facts.npz")
    m1, m2 = certs_of(m1_facts), certs_of(m2_facts)
    mints = {a: mints_of(args.runs / a / "mints.jsonl") for a in ("A1", "A2", "A3", "A4")}
    keys = {a: {(r["ty"], r["tx"], PLANES.index(r["stream_id"])) for r in rows} for a, rows in mints.items()}

    stage_of: dict[Key, str] = {k: "M1" for k in m1}
    checks = {}
    for a in ("A1", "A2", "A3"):
        checks[f"{a}_overlap_with_prior"] = len(keys[a] & set(stage_of))
        checks[f"{a}_duplicate_rows"] = len(mints[a]) - len(keys[a])
        stage_of.update({k: a for k in keys[a]})
    checks["M2_minus_chain"] = sorted(map(list, m2 - set(stage_of)))
    checks["chain_minus_M2"] = sorted(map(list, set(stage_of) - m2))
    stage_of.update({k: "M2" for k in m2 - set(stage_of)})
    checks["A4_overlap_with_M2"] = len(keys["A4"] & m2)
    stage_of.update({k: "A4" for k in keys["A4"]})

    all_keys = {(ty, tx, p) for ty in range(TILES_YX[0]) for tx in range(TILES_YX[1]) for p in range(3)}
    final_open = sorted(all_keys - set(stage_of))
    order = {s: i for i, s in enumerate(STAGES)}

    counts = {}
    for s in STAGES:
        upto = {k for k, v in stage_of.items() if order[v] <= order[s]}
        counts[s] = {PLANES[p]: sum(1 for k in upto if k[2] == p) for p in range(3)} | {"total": len(upto)}

    per_plane = {}
    for p, name in enumerate(PLANES):
        g1 = grid(m1, p)
        gf = grid(set(stage_of), p)
        rec = {}
        for label, g in (("after_M1", g1), ("final", gf)):
            cm, cbar, cb = bands(g.mean(0), TILES_YX[0])
            rm, rbar, rb = bands(g.mean(1), TILES_YX[1])
            rec[label] = {"page_fraction": round(float(g.mean()), 4),
                          "by_column": [round(float(v), 3) for v in g.mean(0)],
                          "by_row": [round(float(v), 3) for v in g.mean(1)],
                          "column_bar": round(cbar, 3), "column_bands": cb,
                          "row_bar": round(rbar, 3), "row_bands": rb}
        residue = ~g1
        rec["M1_residue_by_column"] = [int(v) for v in residue.sum(0)]
        rec["M1_residue_by_row"] = [int(v) for v in residue.sum(1)]
        taken = {}
        for s in ("A1", "A2", "A3", "M2", "A4"):
            g = np.zeros(TILES_YX, bool)
            for (ty, tx, pp), v in stage_of.items():
                if v == s and pp == p:
                    g[ty, tx] = True
            taken[s] = {"n": int(g.sum()), "by_column": [int(v) for v in g.sum(0)],
                        "by_row": [int(v) for v in g.sum(1)]}
        rec["taken"] = taken
        rec["edge_share_of_M1_residue"] = round(float(
            (residue[[0, -1], :].sum() + residue[1:-1, [0, -1]].sum()) / max(residue.sum(), 1)), 3)
        per_plane[name] = rec

    by_pass = {}
    for a, rows in mints.items():
        rec = {}
        for r in rows:
            k = f'{r["stream_id"]}|{r["certifying_rung"]}|{r["certifying_arm"]}|g{r["generation"]}'
            rec[k] = rec.get(k, 0) + 1
        by_pass[a] = dict(sorted(rec.items(), key=lambda t: -t[1]))
    m2_new = [c for c in m2_facts if isinstance(c, data.Certificate)
              and (c.ty, c.tx, PLANES.index(c.stream_id)) in (m2 - (m1 | keys["A1"] | keys["A2"] | keys["A3"]))]

    f1 = {f.plane: f for f in m1_facts if isinstance(f, data.PlaneField) and f.page == 0}
    f2 = {f.plane: f for f in m2_facts if isinstance(f, data.PlaneField) and f.page == 0}
    gauge_check = {name: float(np.abs(np.asarray(ff[0].delta_dots_xy) + np.asarray(ff[1].delta_dots_xy)).max())
                   for name, ff in (("M1", f1), ("M2", f2))}
    m1_vs_m2 = {PLANES[p]: {c: round(float(np.sqrt(((np.asarray(f1[p].delta_dots_xy)[..., i]
                                                       - np.asarray(f2[p].delta_dots_xy)[..., i]) ** 2).mean())), 3)
                            for i, c in enumerate(("dx", "dy"))} for p in range(3)}
    m1_vs_m2_r = {PLANES[p]: {c: round(float(pearsonr(np.asarray(f1[p].delta_dots_xy)[..., i].ravel(),
                                                        np.asarray(f2[p].delta_dots_xy)[..., i].ravel())[0]), 3)
                              for i, c in enumerate(("dx", "dy"))} for p in range(3)}
    corr = {}
    for label, ff in (("M1_field", f1), ("M2_field", f2)):
        corr[label] = {PLANES[p]: correlate(grid(m1, p), np.asarray(ff[p].delta_dots_xy, np.float64))
                       for p in range(3)}

    cert1 = {p: grid(m1, p) for p in range(3)}
    rel = {"M1_field": relative_offsets(cert1, f1), "M2_field": relative_offsets(cert1, f2)}
    out = {
        "tile_mm": TILE_MM, "matrix_origin_mm_yx": [ORIGIN_DOTS_YX[0] * 25.4 / 600, ORIGIN_DOTS_YX[1] * 25.4 / 600],
        "axes": "ty = page y (long axis, 53 tiles, 287.2 mm); tx = page x (short axis, 37 tiles, 200.5 mm)",
        "checks": checks, "counts": counts, "per_plane": per_plane, "by_pass_plane_rung_arm_generation": by_pass,
        "M2_own_mints": [{"ty": c.ty, "tx": c.tx, "stream": c.stream_id, "source": c.source} for c in m2_new],
        "final_open": [{"ty": ty, "tx": tx, "plane": PLANES[p],
                        "mm_yx_from_matrix_origin": [round((ty + .5) * TILE_MM, 1), round((tx + .5) * TILE_MM, 1)],
                        "M1_neighbours_open_same_plane": int(sum(
                            1 for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                            if (dy or dx) and 0 <= ty + dy < TILES_YX[0] and 0 <= tx + dx < TILES_YX[1]
                            and (ty + dy, tx + dx, p) not in m1))}
                       for ty, tx, p in final_open],
        "gauge_max_abs_FC_plus_FM": gauge_check,
        "fields": {"M1": field_summary(f1), "M2": field_summary(f2)},
        "field_M1_vs_M2_rms_dots": m1_vs_m2, "field_M1_vs_M2_pearson": m1_vs_m2_r,
        "certified_after_M1_vs_field": corr,
        "certified_after_M1_vs_pairwise_offsets": rel,
    }
    (args.out / "residue_field.json").write_text(json.dumps(out, indent=1))
    figure(stage_of, f2, args.out / "residue_field.png")


if __name__ == "__main__":
    main()
