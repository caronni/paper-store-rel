"""e045 — the left band's reading from a slices.csv / subwindows.csv pair (measure/e045_left_band/sheet3.py, page.py).

1. zones: per band (and pooled per cell pitch and cyan value, cell-weighted) the error of every arm and the
   per-plane separation over the zones LEFT [x_lo, LEFT_END), MID [LEFT_END + 2, MID_ZONE[0]), MIDZ MID_ZONE and
   RIGHT [MID_ZONE[1], x_hi); the excess = zone / MID;
2. edges: per band from profile_1mm.csv, where the left zone ENDS and the middle zone STARTS, for the error
   (E_slice_finex) and for the sub-window M - C and Y - C dy: the profile smoothed by a 3 mm running median,
   the first x in the search interval where it crosses halfway between the two plateaus (left: [x_lo, x_lo + 15)
   vs [40, 100) mm, searched in [20, 55); middle: [90, 105) vs [112, 127), searched in [100, 120)); NaN where the
   plateaus differ by less than EDGE_MIN (no edge to place);
3. offsets explain? per cell pitch, over every sub-window: OLS of the cross-fitted sub-window error on the
   zone indicators alone, then with the local inter-plane offsets added (|M - C|, |Y - C|, |M - Y| in y and in x,
   the sub-window's own all-cell poses, "ok" planes only); a zone coefficient that falls to ~0 once the offsets
   enter is an excess the offsets account for; standard errors by a bootstrap over windows (the sub-windows of
   one window resampled together).

    PYTHONPATH=src:. env/bin/python -m measure.e045_left_band.analyze --dir <out of sheet3/page>
Writes zones.csv, edges.json and regression.json beside the inputs; prints them.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

LEFT_END = 35.0
MID_ZONE = (107.0, 137.0)
ARMS = ("read", "win", "finex", "fine", "diff", "common")
N_BOOT = 400
EDGE_MIN = {"E_slice_finex": 0.5, "sub_MC_dy": 0.4, "sub_YC_dy": 0.4}    # % and dots
Rec = dict[str, Any]


def zone_of(x: float, x_lo: float) -> str | None:
    if x < LEFT_END:
        return "LEFT"
    if LEFT_END + 2 <= x < MID_ZONE[0]:
        return "MID"
    if MID_ZONE[0] <= x < MID_ZONE[1]:
        return "MIDZ"
    if x >= MID_ZONE[1]:
        return "RIGHT"
    return None


def fl(v: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def zones(rows: list[dict[str, str]]) -> list[Rec]:
    """Cell-weighted zone means per band and per (pitch, cyan) group."""
    keys = [f"E_slice_{a}" for a in ARMS] + ["E_band_read"] + [f"dp_{a}_{p}" for a in ("read", "win", "finex") for p in "CMY"] \
        + [f"mu_W_{p}" for p in "CMY"] + [f"mu_P_{p}" for p in "CMY"] + ["MC_dy", "YC_dy", "MC_dx", "YC_dx", "Y213_Y", "s165_max",
                                                                         "paper_R", "paper_G", "paper_B"]
    x_lo = min(fl(r["x0_mm"]) for r in rows)
    groups: dict[tuple, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        z = zone_of(0.5 * (fl(r["x0_mm"]) + fl(r["x1_mm"])), x_lo)
        if z is None:
            continue
        groups[(r["band"], r["cell_dots"], r["C_G"], r.get("M_RB", ""), z)].append(r)
        groups[("pooled", r["cell_dots"], r["C_G"], "", z)].append(r)
    out = []
    for (band, cd, cg, mrb, z), rs in groups.items():
        w = np.array([fl(r["n_cells"]) for r in rs])
        rec: Rec = {"band": band, "cell_dots": cd, "C_G": cg, "M_RB": mrb, "zone": z, "slices": len(rs)}
        for k in keys:
            v = np.array([fl(r.get(k, "")) for r in rs])
            ok = np.isfinite(v)
            rec[k] = float((v[ok] * w[ok]).sum() / w[ok].sum()) if ok.any() else float("nan")
        out.append(rec)
    return out


def edges(prof: list[dict[str, str]]) -> list[Rec]:
    """Per band the left-zone end and the middle-zone start of each EDGE_MIN quantity."""
    out = []
    for band in dict.fromkeys(r["band"] for r in prof):
        rs = [r for r in prof if r["band"] == band]
        x = np.array([0.5 * (fl(r["x0_mm"]) + fl(r["x1_mm"])) for r in rs])
        rec: Rec = {"band": band, "cell_dots": rs[0]["cell_dots"], "C_G": rs[0]["C_G"]}
        for key in EDGE_MIN:
            v = np.array([fl(r.get(key, "")) for r in rs])
            sm = np.array([np.nanmedian(v[max(0, i - 1):i + 2]) for i in range(len(v))])
            for tag, (pa, pb, sa) in (("left_end", ((x[0], x[0] + 15), (40, 100), (20, 55))),
                                      ("mid_start", ((90, 105), (112, 127), (100, 120)))):
                a = np.nanmedian(sm[(x >= pa[0]) & (x < pa[1])])
                b = np.nanmedian(sm[(x >= pb[0]) & (x < pb[1])])
                rec[f"{key}:{tag}:plateaus"] = [float(a), float(b)]
                if not abs(a - b) >= EDGE_MIN[key]:
                    rec[f"{key}:{tag}"] = float("nan")
                    continue
                half = 0.5 * (a + b)
                sel = np.flatnonzero((x >= sa[0]) & (x < sa[1]))
                hit = [i for i in sel if (sm[i] - half) * (a - half) <= 0]
                rec[f"{key}:{tag}"] = float(x[hit[0]]) if hit else float("nan")
        out.append(rec)
    return out


def regression(subs: list[dict[str, str]], cell_dots: str) -> Rec:
    s = [r for r in subs if r["cell_dots"] == cell_dots and all(r.get(f"{p}_flag") == "ok" for p in "CMY")]
    x = np.array([fl(r["x_mm"]) for r in s])
    zl = np.array([zone_of(v, 0) for v in x])
    keep = zl != None  # noqa: E711
    s, x, zl = [r for r, k in zip(s, keep) if k], x[keep], zl[keep]
    err = np.array([fl(r["err_finex"]) for r in s])
    d = {p: np.array([[fl(r[f"{p}_dy"]), fl(r[f"{p}_dx"])] for r in s]) for p in "CMY"}
    off = {"MC_dy": np.abs(d["M"][:, 0] - d["C"][:, 0]), "YC_dy": np.abs(d["Y"][:, 0] - d["C"][:, 0]),
           "MY_dy": np.abs(d["M"][:, 0] - d["Y"][:, 0]), "MC_dx": np.abs(d["M"][:, 1] - d["C"][:, 1]),
           "YC_dx": np.abs(d["Y"][:, 1] - d["C"][:, 1]), "MY_dx": np.abs(d["M"][:, 1] - d["Y"][:, 1])}
    Z = np.column_stack([(zl == z).astype(float) for z in ("LEFT", "MIDZ", "RIGHT")])
    names_z = ["const", "LEFT", "MIDZ", "RIGHT"]
    names_o = names_z + list(off)
    M0 = np.column_stack([np.ones(len(err)), Z])
    M1 = np.column_stack([M0] + [off[k] for k in off])
    clusters = np.array([f"{r['band']}:{(int(r['r0']) // 36)}:{(int(r['c0']) // 36)}" for r in s])
    uniq = np.unique(clusters)
    idx = {c: np.flatnonzero(clusters == c) for c in uniq}
    rng = np.random.default_rng(45)

    def fit(M: np.ndarray, ii: np.ndarray) -> np.ndarray:
        b, *_ = np.linalg.lstsq(M[ii], err[ii], rcond=None)
        return b
    allix = np.arange(len(err))
    b0, b1 = fit(M0, allix), fit(M1, allix)
    boots0, boots1 = [], []
    for _ in range(N_BOOT):
        ii = np.concatenate([idx[c] for c in rng.choice(uniq, len(uniq))])
        boots0.append(fit(M0, ii))
        boots1.append(fit(M1, ii))
    se0, se1 = np.std(boots0, 0), np.std(boots1, 0)
    r2 = 1 - ((err - M1 @ b1) ** 2).sum() / ((err - err.mean()) ** 2).sum()
    zone_means = {z: {"n": int((zl == z).sum()), "err": float(err[zl == z].mean()),
                      **{k: float(off[k][zl == z].mean()) for k in off}} for z in ("LEFT", "MID", "MIDZ", "RIGHT")}
    return {"cell_dots": cell_dots, "subwindows": len(err), "windows": len(uniq), "zone_means": zone_means,
            "zones_only": {n: [float(b), float(e)] for n, b, e in zip(names_z, b0, se0)},
            "zones_plus_offsets": {n: [float(b), float(e)] for n, b, e in zip(names_o, b1, se1)}, "r2_with_offsets": float(r2)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, type=Path, help="the directory holding slices.csv, subwindows.csv, profile_1mm.csv")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.dir / "slices.csv")))
    subs = list(csv.DictReader(open(a.dir / "subwindows.csv")))
    prof = list(csv.DictReader(open(a.dir / "profile_1mm.csv")))
    eds = edges(prof)
    (a.dir / "edges.json").write_text(json.dumps(eds, indent=1))
    zs = zones(rows)
    keys: list[str] = []
    for r in zs:
        keys += [k for k in r if k not in keys]
    with open(a.dir / "zones.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for r in zs:
            w.writerow({k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()})
    reg = {cd: regression(subs, cd) for cd in sorted({r["cell_dots"] for r in subs})}
    (a.dir / "regression.json").write_text(json.dumps(reg, indent=1))
    order = {"LEFT": 0, "MID": 1, "MIDZ": 2, "RIGHT": 3}
    cols = ["E_band_read", "E_slice_win", "E_slice_finex", "E_slice_diff", "dp_finex_C", "dp_finex_M", "dp_finex_Y",
            "mu_W_C", "mu_W_M", "mu_W_Y", "paper_R", "MC_dy", "YC_dy", "Y213_Y"]
    print("zone".ljust(28) + " ".join(f"{c[-11:]:>11}" for c in cols))
    for r in sorted(zs, key=lambda r: (r["band"] != "pooled", r["cell_dots"], r["C_G"], r["band"], order[r["zone"]])):
        print(f"{r['band']:>6} c{r['cell_dots']} C{r['C_G']} {r['M_RB']:>7} {r['zone']:5}" + " ".join(f"{r[c]:11.2f}" for c in cols))
    print("\nedges (mm): band c C_G | error left_end mid_start | M-C dy left_end mid_start | Y-C dy left_end mid_start")
    for e in eds:
        print(f"  {e['band']:>4} c{e['cell_dots']} C{e['C_G']} | " + " | ".join(
            " ".join(f"{e[f'{k}:{t}']:6.1f}" for t in ("left_end", "mid_start")) for k in EDGE_MIN))
    for cd, g in reg.items():
        print(f"\nc{cd}: {g['subwindows']} sub-windows in {g['windows']} windows; R^2 with offsets {g['r2_with_offsets']:.3f}")
        print("  zone means: " + json.dumps({z: {k: round(v, 2) for k, v in m.items()} for z, m in g["zone_means"].items()}))
        print("  zones only:        " + ", ".join(f"{n} {b:+.2f}±{e:.2f}" for n, (b, e) in g["zones_only"].items()))
        print("  zones + offsets:   " + ", ".join(f"{n} {b:+.2f}±{e:.2f}" for n, (b, e) in g["zones_plus_offsets"].items()))


if __name__ == "__main__":
    main()
