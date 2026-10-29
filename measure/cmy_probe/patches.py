"""e043 — the plateau-edge patch sheet: for every ladder of the probe, five scanned bar interiors at 1:1
scan pixels — just outside the lower edge, just inside it, the lowest-scoring (most solid) bar, just inside
the upper edge, just outside it — labelled with the device RGB, the lattice score and the verdict, so a
human eye can confirm the readout's edges.  Reads the readout's bars.csv (its scores) and the manifest (the
bar rectangles); the page is placed by the five fiducials.
    PYTHONPATH=src:. env/bin/python -m measure.cmy_probe.patches --scan <tiff> --manifest <json> \
        --bars <readout>/bars.csv --out <png>
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from measure.e041_probe_readout import Scan, fit_page

DOT_MM = 25.4 / 600
UNSCREENED_MAX = 18.0        # the white floor's top on e043
MARGINAL_MAX = 30.0          # 18-30: marginal (a weak foreign screen or floor noise); above: screened
PATCH_PX, PATCH_H_PX, GAP_PX = 640, 160, 24
#: a ladder end that is the device's own limit, not a measured edge
DEVICE_LIMIT = {("C", "B"): 255, ("C", "R"): 0, ("Y", "B"): 0, ("Y", "G"): 255, ("Y", "R"): 255,
                ("Y", "RG"): 255, ("M", "G"): 0}


def ladders(rows: list[dict[str, str]], geom: dict[str, dict[str, Any]]) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = collections.defaultdict(list)
    for r in rows:
        if r["kind"] != "sweep" or r["axis"] not in ("R", "G", "B", "RG"):
            continue
        g = geom[r["id"]]
        rgb = (int(r["r"]), int(r["g"]), int(r["b"]))
        ax = r["axis"]
        v = {"R": rgb[0], "G": rgb[1], "B": rgb[2], "RG": rgb[0]}[ax]
        fixed = " ".join(f"{'RGB'[i]}{c}" for i, c in enumerate(rgb) if "RGB"[i] not in ax)
        pre = "legacy_" if "legacy_score" in r else ""        # bars.csv since the stipple verdict (CMY-PROBE §9)
        rgb_scores = (tuple(float(r[pre + k]) for k in ("score_R", "score_G", "score_B")) if pre + "score_R" in r
                      else ())
        if pre and r.get("construct"):
            fixed += f" {r['construct']}"
        out[(r["toner"], ax, fixed)].append(dict(v=v, rgb=rgb, score=float(r[pre + "score"]), best=r[pre + "best_lattice"],
                                               rgb_scores=rgb_scores,
                                               x=g["x_dots"], y=g["y_dots"], w=g["w_dots"], h=g["h_dots"]))
    return out


def pick(ser: list[dict], toner: str, ax: str) -> list[tuple[str, dict | None]]:
    """The five patches of one ladder; the plateau is the longest run of values at or below MARGINAL_MAX
    (marginal values count as inside: the edge shown is the first clearly screened value)."""
    ser = sorted(ser, key=lambda b: b["v"])
    un = [b["score"] <= MARGINAL_MAX for b in ser]
    best, cur, start = (0, 0, 0), 0, 0
    for i, u in enumerate(un + [False]):
        if u:
            if cur == 0:
                start = i
            cur += 1
            if cur > best[0]:
                best = (cur, start, i)
        else:
            cur = 0
    n, s, e = best
    if n == 0:
        return [("no unscreened value", None)] * 5
    lo_out = ser[s - 1] if s > 0 else None
    hi_out = ser[e + 1] if e + 1 < len(ser) else None
    mid = min(ser[s:e + 1], key=lambda b: b["score"])
    lim_lo = s == 0 and DEVICE_LIMIT.get((toner, ax)) == ser[0]["v"]
    lim_hi = e == len(ser) - 1 and DEVICE_LIMIT.get((toner, ax)) == ser[-1]["v"]
    return [("just OUTSIDE lower edge" if lo_out else ("device limit" if lim_lo else "ladder start (open)"), lo_out),
            ("just inside lower edge", ser[s]), ("lowest score (most solid)", mid),
            ("just inside upper edge", ser[e]),
            ("just OUTSIDE upper edge" if hi_out else ("device limit" if lim_hi else "ladder end (open)"), hi_out)]


def crop(img: np.ndarray, A: np.ndarray, b: dict, inset_x: int = 16, inset_y: int = 4) -> Image.Image:
    xa, ya = (b["x"] + inset_x) * DOT_MM, (b["y"] + inset_y) * DOT_MM
    xb, yb = (b["x"] + b["w"] - inset_x) * DOT_MM, (b["y"] + b["h"] - inset_y) * DOT_MM
    c0, r0 = A @ np.array([xa, ya, 1.0])
    c1, r1 = A @ np.array([xb, yb, 1.0])
    return Image.fromarray(img[int(round(r0)):int(round(r1)), int(round(c0)):int(round(c1))])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--bars", required=True, help="the readout's bars.csv")
    ap.add_argument("--out", required=True, help="the PNG to write")
    args = ap.parse_args()
    man = json.load(open(args.manifest))
    geom = {b["id"]: b for b in man["bars"]}
    rows = list(csv.DictReader(open(args.bars)))
    scan = Scan(Path(args.scan))
    A, _ = fit_page(scan, {"fiducials": man["fiducials"]}, 0.3, 0.01)
    img = scan.img
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
        small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    except OSError:
        font = small = ImageFont.load_default()
    lad = ladders(rows, geom)
    order = sorted(lad, key=lambda k: ({"C": 0, "M": 1, "Y": 2}[k[0]], k[1], k[2]))
    width = 5 * (PATCH_PX + GAP_PX) + 40
    sheet = Image.new("RGB", (width, len(order) * (PATCH_H_PX + 110) + 60), "white")
    d = ImageDraw.Draw(sheet)
    y = 20
    for toner, ax, fixed in order:
        d.text((20, y), f"{toner}: swept {ax} at {fixed}   (per-channel known-lattice peak over ring median, the largest "
                        f"decides: <= {UNSCREENED_MAX:.0f} clear (white floor), <= {MARGINAL_MAX:.0f} marginal, "
                        f"above screened)", fill="black", font=font)
        y += 32
        for col, (role, b) in enumerate(pick(lad[(toner, ax, fixed)], toner, ax)):
            x = 20 + col * (PATCH_PX + GAP_PX)
            d.text((x, y), role, fill="black", font=small)
            if b is None:
                d.rectangle([x, y + 24, x + PATCH_PX, y + 24 + PATCH_H_PX], outline="grey")
                d.text((x + 10, y + 24 + 65), "(no bar beyond this end)", fill="grey", font=small)
                continue
            im = crop(img, A, b)
            if im.size != (PATCH_PX, PATCH_H_PX):
                im = im.resize((PATCH_PX, PATCH_H_PX))
            sheet.paste(im, (x, y + 24))
            sc = b["score"]
            tier = "clear" if sc <= UNSCREENED_MAX else ("MARGINAL" if sc <= MARGINAL_MAX else "SCREENED")
            colour = {"clear": "black", "MARGINAL": "darkorange", "SCREENED": "red"}[tier]
            chan = ("  R/G/B " + "/".join(f"{s:.0f}" for s in b["rgb_scores"])) if b["rgb_scores"] else ""
            d.text((x, y + 24 + PATCH_H_PX + 4),
                   f"RGB {b['rgb']}   max {sc:.1f} {tier}{chan}  ({b['best']})", fill=colour, font=small)
        y += 24 + PATCH_H_PX + 54
    sheet.crop((0, 0, width, y)).save(args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
