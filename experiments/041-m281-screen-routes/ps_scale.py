"""e041 S14 — the PAGE-SCALE probe for the HP M281 on the production route (PostScript).

THE QUESTION.  S11/S12 measured the alphabets in 3.9 mm patches on a mostly white page: cmy4-solid c3 0.36 %
state error, cmyk5 c3 0.53 %, cmy8 c3 (S9's construction) 4-8 %.  S9's FULL page of the same cmy8 content
read magenta 21 % / yellow 23 % per plane, 5-7x worse.  Something page-scale degrades a page covered edge to
edge with noise: physical toner supply at high coverage, or the formatter degrading a large incompressible
raster.  S14 lays full-width noise bands (x 12 .. ~197.9 mm, across the engine's 98-118 mm stripe on
purpose) over 74 % of the page area (81 % inside the band extent with strips and gaps), so every alphabet
sees page-scale conditions, and varies inside the sheet:
alphabet (cmy4-solid, cmy8-engine, cmyk5), ColorSmart colour matching (section A: device default = S12's
footing; section B: `false ColorSmartColorMatching` before every image), one image vs 24 abutting tile
images (B1 vs B2, statistically identical), c3 vs c2 (B3, Detail).  Two solid strips carry the single-toner
and overlap bars and twelve cyan candidates under each matching state, and a K bar under TonerBlack.

ROUTE AND FOOTING = S12 (ps_mixture.py, printed 2026-10-05): S1's PJL wrapper without BITSPERPIXEL / RET
(JOB NAME "E041-S14-PS-SCALE"), F's DSC header shape, F's setpagedevice line verbatim, S12's bare-name
prologue byte for byte (its comment still says S12: the bytes are the footing), then every image inside
gsave/grestore as an 8-bit [/Indexed /DeviceRGB hival <lookup>] image, ASCII85, 0.12 pt per dot, preceded by
the HP calls behind `where` guards in S12's order: <ProcBlack|TonerBlack> HPImageNeutralAxis, [section B:
false ColorSmartColorMatching], <Smooth|Detail> ColorSmartImageHalftone, Off HPColorTrapping,
false HPImageAdaptiveHalftoning.  The five fiducials are S12's three fiducial images (ProcBlack + Smooth,
no matching call), drawn first; the bands follow in section order (A, then B) but are PLACED by PAGE_ORDER
(A1, B1, B2, A2, A3, B4, B3, A-strip, B-strip) so matched pairs are neighbours on the page.

STATES: per data band iid uniform over the alphabet, numpy default_rng(51000 + band index) .choice, cells
row-major (band index = position in the nine-band table, strips included); B2's 24 tiles are slices of ONE
raster drawn from its own seed.

Outputs (beside --out): the job, <stem>.manifest.json (bands, bars, fiducials, readout windows of 31x31 c3
cells / 46x46 c2 cells, ps_structure, verification) and <stem>-bands.npz (states_<band>, planes_<band>:
4 x H x W C/M/Y/K ink per dot), written with fixed zip timestamps so its bytes are deterministic.

--verify: (1) gs ppmraw -r600 render == the page composed from the manifest + npz; (2) gs strict run silent
and a stub run logging every HP call and image in sequence; (3) byte audit against S12 (wrapper, header
shape, setpagedevice, prologue, tail); (4) every readout window's states and planes against the render;
(5) geometry; (6) two builds identical; (7) S12 rebuilt unchanged; (8) novelty against the printed S12 and
S6 jobs; (9) sizes.

    PYTHONPATH=src:. env/bin/python \\
        experiments/041-m281-screen-routes/ps_scale.py \\
        --out experiments/041-m281-screen-routes/build/S14-ps-scale.ps --verify
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import ps_mixture as s12
from pcl_planar import sha
from pclxl_probe import DPI, mm
from pclxl_probe_sheets import FIDUCIAL_IMAGES, fiducials

TAG = "S14-ps-scale"
JOB_NAME = "E041-S14-PS-SCALE"
S12_SHA256 = "3ec2a2ee040112dfdb1940d1cbac9f15f38bb8d41b88daa8ba40543cfd1a3826"
PAGE_H_DOTS, PAGE_W_DOTS = s12.PAGE_HW_DOTS
WRAPPER_HEAD = s12.UEL + f'@PJL JOB NAME="{JOB_NAME}"\r\n@PJL ENTER LANGUAGE=POSTSCRIPT\r\n'.encode()
HEADER = (b"%!PS-Adobe-3.0\n%%Title: e041 S14 PostScript page-scale probe\n"
          b"%%Creator: experiments/041-m281-screen-routes/ps_scale.py\n%%LanguageLevel: 2\n"
          b"%%DocumentData: Clean7Bit\n%%BoundingBox: 0 0 596 842\n%%Pages: 1\n%%EndComments\n")
TAIL = b"showpage\n%%Trailer\n" + s12.WRAPPER_TAIL
HALFTONE = {"smooth": "Smooth", "detail": "Detail"}
NEUTRAL = {"process": "ProcBlack", "toner": "TonerBlack"}
MATCHING = {"A": "default", "B": "off"}
PLANES_ORDER = ("C", "M", "Y", "K")

RGB = tuple[int, int, int]
PALETTE: dict[str, RGB] = {
    "W": (255, 255, 255), "C": (0, 255, 255), "M-solid": (240, 0, 192), "M-corner": (255, 0, 255),
    "Y": (255, 255, 0), "CM": (0, 0, 255), "CY": (0, 255, 0), "MY": (255, 0, 0), "CMY": (0, 0, 0),
    "K": (0, 0, 0)}
INK = {"W": "", "C": "C", "M-solid": "M", "M-corner": "M", "Y": "Y", "CM": "CM", "CY": "CY", "MY": "MY",
       "CMY": "CMY", "K": "K"}  # CMY is (0,0,0) under ProcBlack, K is (0,0,0) under TonerBlack
ALPHABETS: dict[str, tuple[str, ...]] = {
    "cmy4-solid": ("W", "C", "M-solid", "Y"),
    "cmy8-engine": ("W", "C", "M-corner", "Y", "CM", "CY", "MY", "CMY"),
    "cmyk5": ("W", "C", "M-solid", "Y", "K")}
CYAN_CANDIDATES: tuple[RGB, ...] = (
    (0, 255, 255), (0, 255, 240), (0, 240, 255), (0, 224, 255), (0, 255, 224), (0, 240, 240), (0, 224, 224),
    (16, 255, 255), (0, 255, 208), (0, 208, 255), (32, 255, 255), (0, 192, 255))
STRIP_BARS: tuple[tuple[str, RGB], ...] = (
    tuple((n, PALETTE[n]) for n in ("C", "M-solid", "M-corner", "Y", "CM", "CY", "MY", "CMY"))
    + tuple((f"cyan-{r}-{g}-{b}", (r, g, b)) for r, g, b in CYAN_CANDIDATES))
BAND_X_DOTS, BAND_W_DOTS, FIRST_Y_DOTS, GAP_DOTS = 283, 4392, 283, 24
BAR_W_DOTS, BAR_GAP_DOTS = 93, 24
B2_TILES, B2_TILE_W_DOTS = 24, 183
LAST_END_DOTS = 6732
WINDOW_CELLS = {3: 31, 2: 46}
SEED_BASE = 51000


@dataclass(frozen=True)
class BandSpec:
    name: str
    section: str
    alphabet: str | None  # None = a solid strip
    cell_dots: int | None
    method: str
    neutral: str
    h_dots: int
    tiles: int = 1


BANDS: tuple[BandSpec, ...] = (
    BandSpec("A1", "A", "cmy4-solid", 3, "smooth", "process", 942),
    BandSpec("A2", "A", "cmy8-engine", 3, "smooth", "process", 942),
    BandSpec("A3", "A", "cmyk5", 3, "smooth", "toner", 708),
    BandSpec("A-strip", "A", None, None, "smooth", "process", 186),
    BandSpec("B1", "B", "cmy4-solid", 3, "smooth", "process", 942),
    BandSpec("B2", "B", "cmy4-solid", 3, "smooth", "process", 942, B2_TILES),
    BandSpec("B3", "B", "cmy4-solid", 2, "detail", "process", 708),
    BandSpec("B4", "B", "cmyk5", 3, "smooth", "toner", 684),
    BandSpec("B-strip", "B", None, None, "smooth", "process", 186))


# ------------------------------------------------------------------------------------------------ plan

# Top-to-bottom placement, separate from the draw order (BANDS): the matched pairs sit next to each other
# so that position on the page does not stand in for matching (refuter, 2026-10-05): A1|B1|B2 (matching,
# tiles), A2 alone, A3|B4 (cmyk5 matching), B3, then the two strips side by side in y.  Section A is still
# drawn first, so a matching state that outlives grestore cannot reach back into section A.
PAGE_ORDER = ("A1", "B1", "B2", "A2", "A3", "B4", "B3", "A-strip", "B-strip")


def band_rows() -> list[tuple[int, BandSpec, int]]:
    """(band index, spec, y_dots) in DRAW order; y from PAGE_ORDER, 24 white dots between neighbours."""
    assert sorted(PAGE_ORDER) == sorted(b.name for b in BANDS)
    by_name = {b.name: b for b in BANDS}
    y_of, y = {}, FIRST_Y_DOTS
    for name in PAGE_ORDER:
        y_of[name] = y
        y += by_name[name].h_dots + GAP_DOTS
    return [(k, b, y_of[b.name]) for k, b in enumerate(BANDS)]


def ink_table(alphabet: tuple[str, ...]) -> np.ndarray:
    """(states, 4) uint8: which of C/M/Y/K each state lays."""
    return np.array([[int(p in INK[s]) for p in PLANES_ORDER] for s in alphabet], np.uint8)


def expand(cells: np.ndarray, cell_dots: int) -> np.ndarray:
    return np.repeat(np.repeat(cells, cell_dots, axis=0), cell_dots, axis=1)


def image_rec(name: str, band: str | None, section: str, method: str, neutral: str,
              xywh: tuple[int, int, int, int], palette: np.ndarray, raster: np.ndarray, kind: str,
              tile: int | None = None) -> dict:
    return {"name": name, "band": band, "section": section, "matching": MATCHING[section], "method": method,
            "neutral": neutral, "xywh": xywh, "palette": palette, "raster": raster, "kind": kind,
            "tile": tile}


def fiducial_plan() -> tuple[list[dict], list[dict]]:
    """S12's five fiducials and its three fiducial images (black on white, ProcBlack + Smooth, no matching
    call)."""
    fids = [{k: v for k, v in f.items() if k != "_xywh"} | {"xywh_dots": list(f["_xywh"])}
            for f in fiducials()]
    by_id = {f["id"]: f for f in fids}
    images = []
    for name, ids in FIDUCIAL_IMAGES:
        boxes = [by_id[i]["xywh_dots"] for i in ids]
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
        raster = np.zeros((y1 - y0, x1 - x0), np.uint8)
        for bx, by, bw, bh in boxes:
            raster[by - y0:by - y0 + bh, bx - x0:bx - x0 + bw] = 1
        images.append(image_rec(name, None, "A", "smooth", "process", (x0, y0, x1 - x0, y1 - y0),
                                np.array([[255, 255, 255], [0, 0, 0]], np.uint8), raster, "fiducial"))
        for i in ids:
            by_id[i]["image"] = name
    return fids, images


def plan() -> tuple[list[dict], list[dict], list[dict], list[dict], dict[str, np.ndarray]]:
    """Fiducials, bands, bars, images (draw order) and the npz arrays."""
    fids, images = fiducial_plan()
    bands, bars, arrays = [], [], {}
    for k, b, y in band_rows():
        rec = {"band": k, "name": b.name, "section": b.section, "matching": MATCHING[b.section],
               "method": b.method, "neutral": b.neutral, "x_dots": BAND_X_DOTS, "y_dots": y,
               "w_dots": BAND_W_DOTS, "h_dots": b.h_dots, "x_mm": mm(BAND_X_DOTS), "y_mm": mm(y),
               "w_mm": mm(BAND_W_DOTS), "h_mm": mm(b.h_dots)}
        if b.alphabet is None:
            pal = np.array([PALETTE["W"]] + [rgb for _, rgb in STRIP_BARS], np.uint8)
            strip_w_dots = len(STRIP_BARS) * (BAR_W_DOTS + BAR_GAP_DOTS) - BAR_GAP_DOTS
            raster = np.zeros((b.h_dots, strip_w_dots), np.uint8)
            for j, (colour, rgb) in enumerate(STRIP_BARS):
                x0 = j * (BAR_W_DOTS + BAR_GAP_DOTS)
                raster[:, x0:x0 + BAR_W_DOTS] = j + 1
                bars.append({"id": f"{b.section}-bar{j:02d}", "band": b.name, "colour": colour,
                             "rgb": list(rgb),
                             "section": b.section, "matching": MATCHING[b.section], "neutral": "process",
                             "image": f"{b.name}-process", "x_dots": BAND_X_DOTS + x0, "y_dots": y,
                             "w_dots": BAR_W_DOTS, "h_dots": b.h_dots})
            kx = BAND_X_DOTS + len(STRIP_BARS) * (BAR_W_DOTS + BAR_GAP_DOTS)
            bars.append({"id": f"{b.section}-bar{len(STRIP_BARS):02d}", "band": b.name, "colour": "K",
                         "rgb": list(PALETTE["K"]), "section": b.section, "matching": MATCHING[b.section],
                         "neutral": "toner", "image": f"{b.name}-K", "x_dots": kx, "y_dots": y,
                         "w_dots": BAR_W_DOTS, "h_dots": b.h_dots})
            imgs = [image_rec(f"{b.name}-process", b.name, b.section, b.method, "process",
                              (BAND_X_DOTS, y, raster.shape[1], b.h_dots), pal, raster, "strip"),
                    image_rec(f"{b.name}-K", b.name, b.section, b.method, "toner",
                              (kx, y, BAR_W_DOTS, b.h_dots),
                              np.array([PALETTE["W"], PALETTE["K"]], np.uint8),
                              np.ones((b.h_dots, BAR_W_DOTS), np.uint8), "strip")]
            rec |= {"alphabet": None, "palette": {c: list(rgb) for c, rgb in STRIP_BARS} | {"K": [0, 0, 0]},
                    "cell_dots": None, "seed": None}
        else:
            assert b.cell_dots is not None
            alpha = ALPHABETS[b.alphabet]
            rows, cols = b.h_dots // b.cell_dots, BAND_W_DOTS // b.cell_dots
            if rows * b.cell_dots != b.h_dots or cols * b.cell_dots != BAND_W_DOTS:
                raise SystemExit(f"{b.name}: {b.h_dots} x {BAND_W_DOTS} dots is not whole "
                                 f"c{b.cell_dots} cells")
            seed = SEED_BASE + k
            states = np.random.default_rng(seed).choice(len(alpha), size=(rows, cols)).astype(np.uint8)
            arrays[f"states_{b.name}"] = states
            arrays[f"planes_{b.name}"] = np.ascontiguousarray(
                np.moveaxis(expand(ink_table(alpha)[states], b.cell_dots), 2, 0))
            raster = expand(states, b.cell_dots)
            pal = np.array([PALETTE[s] for s in alpha], np.uint8)
            if b.tiles == 1:
                imgs = [image_rec(b.name, b.name, b.section, b.method, b.neutral,
                                  (BAND_X_DOTS, y, BAND_W_DOTS, b.h_dots), pal, raster, "band")]
            else:
                if b.tiles * B2_TILE_W_DOTS != BAND_W_DOTS or B2_TILE_W_DOTS % b.cell_dots:
                    raise SystemExit(f"{b.name}: {b.tiles} tiles x {B2_TILE_W_DOTS} dots do not cut the band")
                tw = B2_TILE_W_DOTS
                imgs = [image_rec(f"{b.name}-t{t:02d}", b.name, b.section, b.method, b.neutral,
                                  (BAND_X_DOTS + t * tw, y, tw, b.h_dots), pal,
                                  np.ascontiguousarray(raster[:, t * tw:(t + 1) * tw]), "band", tile=t)
                        for t in range(b.tiles)]
            rec |= {"alphabet": b.alphabet, "states": list(alpha),
                    "palette": {s: list(PALETTE[s]) for s in alpha},
                    "planes": {s: INK[s] for s in alpha}, "cell_dots": b.cell_dots, "cells_hw": [rows, cols],
                    "seed": seed}
        rec["images"] = [{"image": i["name"], "x_dots": i["xywh"][0], "y_dots": i["xywh"][1],
                          "w_dots": i["xywh"][2], "h_dots": i["xywh"][3], "neutral": i["neutral"],
                          "tile": i["tile"]} for i in imgs]
        bands.append(rec)
        images += imgs
    for bar in bars:
        bar |= {"x_mm": mm(bar["x_dots"]), "y_mm": mm(bar["y_dots"]), "w_mm": mm(bar["w_dots"]),
                "h_mm": mm(bar["h_dots"])}
    return fids, bands, bars, images, arrays


def windows(bands: list[dict]) -> list[dict]:
    """Each data band tiled into whole windows of 31x31 c3 / 46x46 c2 cells from its top-left."""
    out = []
    for b in bands:
        if b["alphabet"] is None:
            continue
        cd = b["cell_dots"]
        wc = WINDOW_CELLS[cd]
        rows, cols = b["cells_hw"]
        for iy in range(rows // wc):
            for ix in range(cols // wc):
                x, y = b["x_dots"] + ix * wc * cd, b["y_dots"] + iy * wc * cd
                tile = None
                if len(b["images"]) > 1:
                    tile = (x + wc * cd // 2 - b["x_dots"]) // B2_TILE_W_DOTS
                out.append({"id": f"{b['name']}-w{iy:02d}-{ix:02d}", "band": b["name"], "x_dots": x,
                            "y_dots": y,
                            "w_dots": wc * cd, "h_dots": wc * cd, "x_mm": mm(x), "y_mm": mm(y), "cells": wc,
                            "cell_dots": cd, "cell_yx": [iy * wc, ix * wc], "alphabet": b["alphabet"],
                            "palette": b["palette"], "method": b["method"], "neutral": b["neutral"],
                            "matching": b["matching"], "section": b["section"], "tile": tile})
    return out


# ------------------------------------------------------------------------------------------------ emission

def calls_of(img: dict) -> list[tuple[str, str]]:
    """(operator, operand) in S12's order, the matching call right after the neutral axis in section B."""
    calls = [("HPImageNeutralAxis", NEUTRAL[img["neutral"]])]
    if img["matching"] == "off":
        calls.append(("ColorSmartColorMatching", "false"))
    return calls + [("ColorSmartImageHalftone", HALFTONE[img["method"]]), ("HPColorTrapping", "Off"),
                    ("HPImageAdaptiveHalftoning", "false")]


def image_ops(img: dict) -> list[str]:
    head = (f"% {img['name']}: {img['kind']}" + (f" of {img['band']}" if img["band"] else "")
            + f", section {img['section']}, matching {img['matching']}, {HALFTONE[img['method']]}, "
            f"{NEUTRAL[img['neutral']]}")
    return s12.image_lines(head, img["xywh"], img["palette"], [s12.hp_call(a, op) for op, a in calls_of(img)])


def emit_job(images: list[dict], wrapper_head: bytes = WRAPPER_HEAD,
             header: bytes = HEADER) -> tuple[bytes, list[dict]]:
    """The job: wrapper, header, S12's setpagedevice + prologue, every image, the tail (S15 passes its own
    wrapper head and header; the defaults are S14's)."""
    parts = [wrapper_head, header, s12.SETPAGEDEVICE, s12.prologue(), b"%%Page: 1 1\n"]
    records = []
    for img in images:
        ops = image_ops(img)
        text = ("\n".join(ops) + "\n").encode()
        raw = img["raster"].tobytes()
        data = s12.a85_lines(raw)
        offset = sum(len(p) for p in parts) + len(text)
        parts += [text, data, b"grestore\n"]
        records.append({"image": img["name"], "kind": img["kind"], "band": img["band"],
                        "section": img["section"],
                        "matching": img["matching"], "method": img["method"], "neutral": img["neutral"],
                        "tile": img["tile"], "xywh_dots": list(img["xywh"]), "operators": ops[1:],
                        "hival": len(img["palette"]) - 1, "data_offset": offset, "data_bytes_raw": len(raw),
                        "data_bytes_ascii85": len(data), "raster_sha256": sha(raw)})
    parts.append(TAIL)
    return b"".join(parts), records


def npz_bytes(arrays: dict[str, np.ndarray]) -> bytes:
    """np.savez_compressed's layout with a fixed timestamp: deterministic bytes, np.load reads it."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for key in sorted(arrays):
            one = io.BytesIO()
            np.lib.format.write_array(one, np.ascontiguousarray(arrays[key]), allow_pickle=False)
            info = zipfile.ZipInfo(f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, one.getvalue())
    return buf.getvalue()


def notes() -> list[str]:
    return [
        "WHY: S11/S12 patches (3.9 mm, mostly white page) read cmy4-solid c3 0.36 %, cmyk5 c3 0.53 %, cmy8 "
        "c3 4-8 % state error; S9's full page of the same cmy8 content read M 21 % / Y 23 % per plane. S14 "
        "asks whether the collapse is page-scale: full-width noise bands over 74 % of the page area (81 % "
        "inside the band extent with strips and gaps).",
        "ROUTE = S12's: S1 PJL wrapper without BITSPERPIXEL/RET, F's setpagedevice verbatim, S12's bare-name"
        " prologue byte for byte (its comment line names S12), 8-bit Indexed DeviceRGB images in gsave, "
        "ASCII85, HP calls behind `where` guards in S12's order.",
        "SECTION A = matching at the device default (S12's footing, no ColorSmartColorMatching call); "
        "SECTION B = `false ColorSmartColorMatching` right after the neutral-axis call in every image "
        "(operator takes a boolean; printed page-level under DeviceCMYK in S6, never per image under Indexed"
        " DeviceRGB).",
        "B1 vs B2: the same alphabet, method, neutral, matching and height; B2 is ONE raster drawn from its "
        "own seed cut into 24 abutting images 183 dots (61 cells) wide -- only the object split differs.",
        "BANDS cross the engine's 98-118 mm stripe on purpose; windows carry x_mm so the stripe is a readout"
        " axis.",
        "PLANES: 1 where that toner's solid colour is on the dot; CMY (0,0,0) under ProcBlack sets C, M and "
        "Y; K (0,0,0) under TonerBlack sets K only. M-corner (255,0,255) is S9's magenta (cmy8-engine), "
        "M-solid (240,0,192) the solid magenta of cmy4-solid / cmyk5.",
        "SEEDS: default_rng(51000 + band index), band index = position in the nine-band table (strips "
        "included, so the data bands use 0,1,2,4,5,6,7); .choice(len(alphabet), size=(rows, cols)).",
        "STRIPS: twenty bars in one ProcBlack image (eight named colours, twelve cyan candidates) with white"
        " gaps inside the image, then the K bar as its own TonerBlack image; both Smooth.",
        "gs knows none of the HP operators; its render shows the page, not what the engine does with the "
        "controls.",
    ]


def build() -> tuple[bytes, dict, bytes, list[dict], dict[str, np.ndarray], list[dict]]:
    """The job, the manifest (no verification, no generator line), the npz bytes, images, arrays, records."""
    fids, bands, bars, images, arrays = plan()
    job, records = emit_job(images)
    nb = npz_bytes(arrays)
    manifest = {
        "tag": TAG, "dpi": DPI, "page_dots": {"w": PAGE_W_DOTS, "h": PAGE_H_DOTS}, "bytes": len(job),
        "sha256": sha(job), "bands_npz": {"file": f"{TAG}-bands.npz", "sha256": sha(nb), "bytes": len(nb),
                                          "keys": sorted(arrays)},
        "planes_order": list(PLANES_ORDER), "fiducials": fids, "bands": bands, "bars": bars,
        "windows": windows(bands), "palette": {k: list(v) for k, v in PALETTE.items()},
        "alphabets": {k: list(v) for k, v in ALPHABETS.items()},
        "ps_structure": {"wrapper_head": WRAPPER_HEAD.decode("latin1"), "header": HEADER.decode(),
                         "setpagedevice": s12.SETPAGEDEVICE.decode(), "prologue": s12.prologue().decode(),
                         "tail": TAIL.decode("latin1"), "data_filter": "ASCII85Decode",
                         "a85_columns": s12.A85_COLUMNS, "pt_per_dot": s12.PT_PER_DOT, "images": records},
        "notes": notes(),
    }
    return job, manifest, nb, images, arrays, records


# ------------------------------------------------------------------------------------------------ verify

def composed(man: dict, arrays: dict[str, np.ndarray]) -> np.ndarray:
    """The page from the manifest + npz alone (no image records)."""
    page = np.full((PAGE_H_DOTS, PAGE_W_DOTS, 3), 255, np.uint8)
    for f in man["fiducials"]:
        x, y, w, h = f["xywh_dots"]
        page[y:y + h, x:x + w] = f["rgb"]
    for b in man["bands"]:
        if b["alphabet"] is None:
            continue
        pal = np.array([b["palette"][s] for s in b["states"]], np.uint8)
        page[b["y_dots"]:b["y_dots"] + b["h_dots"], b["x_dots"]:b["x_dots"] + b["w_dots"]] = pal[
            expand(arrays[f"states_{b['name']}"], b["cell_dots"])]
    for bar in man["bars"]:
        x, y, w, h = bar["x_dots"], bar["y_dots"], bar["w_dots"], bar["h_dots"]
        page[y:y + h, x:x + w] = bar["rgb"]
    return page


def render(job_path: Path) -> tuple[np.ndarray, str, int]:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "s14.ppm"
        r = s12.gs(["-q", "-sDEVICE=ppmraw", "-r600", f"-g{PAGE_W_DOTS}x{PAGE_H_DOTS}",
                    f"-sOutputFile={out}"], job_path)
        return s12.read_ppm(out), (r.stdout + r.stderr).strip(), r.returncode


def render_checks(img: np.ndarray, messages: str, rc: int, man: dict, arrays: dict[str, np.ndarray],
                  images: list[dict]) -> dict:
    page = composed(man, arrays)
    covered = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), bool)
    fid_black = True
    for f in man["fiducials"]:
        x, y, w, h = f["xywh_dots"]
        fid_black &= bool((img[y:y + h, x:x + w] == 0).all())
        covered[y:y + h, x:x + w] = True
    bars_solid = []
    for bar in man["bars"]:
        x, y, w, h = bar["x_dots"], bar["y_dots"], bar["w_dots"], bar["h_dots"]
        bars_solid.append(bool((img[y:y + h, x:x + w] == np.array(bar["rgb"], np.uint8)).all()))
        covered[y:y + h, x:x + w] = True
    for b in man["bands"]:
        if b["alphabet"] is not None:
            covered[b["y_dots"]:b["y_dots"] + b["h_dots"], b["x_dots"]:b["x_dots"] + b["w_dots"]] = True
    painted = s12.painted(images)
    res = {"gs_returncode": rc, "gs_messages": messages, "page_hw": list(img.shape[:2]),
           "render_sha256": sha(img.tobytes()),
           "differing_dots_vs_composed_from_manifest_npz": int((img != page).any(2).sum()),
           "differing_dots_vs_painted_images": int((img != painted).any(2).sum()),
           "fiducials_solid_black": fid_black, "bars_solid": f"{sum(bars_solid)} of {len(bars_solid)}",
           "non_white_outside_objects": int(((img != 255).any(2) & ~covered).sum()),
           "white_dots_outside_objects": int((~covered).sum()),
           "inked_dots": int((img != 255).any(2).sum()),
           "page_fraction_in_noise_bands": round(float(sum(
               b["w_dots"] * b["h_dots"] for b in man["bands"] if b["alphabet"])
               / (PAGE_W_DOTS * PAGE_H_DOTS)), 4),
           "page_fraction_band_extent_incl_strips_and_gaps": round(float(
               (max(b["y_dots"] + b["h_dots"] for b in man["bands"]) - min(b["y_dots"] for b in man["bands"]))
               * BAND_W_DOTS / (PAGE_W_DOTS * PAGE_H_DOTS)), 4)}
    res["pass"] = (rc == 0 and not messages and res["differing_dots_vs_composed_from_manifest_npz"] == 0
                   and res["differing_dots_vs_painted_images"] == 0 and fid_black and all(bars_solid)
                   and res["non_white_outside_objects"] == 0)
    return res


def guard_checks(job: bytes, images: list[dict]) -> dict:
    """gs strict on the job as sent (guards silent); then S12's stub prologue after %%EndComments."""
    with tempfile.TemporaryDirectory() as td:
        plain = Path(td) / "s14.ps"
        plain.write_bytes(job)
        strict = s12.gs(["-q", "-sDEVICE=nullpage"], plain)
        stubbed = Path(td) / "s14-stubs.ps"
        cut = job.index(b"%%EndComments\n") + len(b"%%EndComments\n")
        stubbed.write_bytes(job[:cut] + s12.stub_prologue() + job[cut:])
        run = s12.gs(["-q", "-sDEVICE=nullpage"], stubbed)
    log = [ln for ln in run.stderr.splitlines() if ln.startswith(("HPCALL", "IMAGE", "SHOWPAGE"))]
    want: list[str] = []
    per_band: dict[str, dict] = {}
    for img in images:
        seq = [f"HPCALL {op} {a if a == 'false' else '(' + a + ')'}" for op, a in calls_of(img)]
        want += seq + [f"IMAGE {img['xywh'][2]} {img['xywh'][3]}"]
        key = img["band"] or "fiducials"
        pb = per_band.setdefault(key, {"images": 0, "sequences": []})
        pb["images"] += 1
        if seq not in pb["sequences"]:
            pb["sequences"].append(seq)
    want.append("SHOWPAGE")
    strict_text = (strict.stdout + strict.stderr).strip()
    res = {"strict_returncode": strict.returncode, "strict_messages": strict_text,
           "stub_returncode": run.returncode, "stub_log_lines": len(log), "expected_lines": len(want),
           "stub_sequence_exact": log == want,
           "stub_calls": dict(Counter(ln.split()[1] for ln in log if ln.startswith("HPCALL"))),
           "stub_other_output": "\n".join(ln for ln in run.stderr.splitlines() if ln not in set(log)).strip(),
           "per_band": per_band}
    if log != want:
        res["first_mismatch"] = next(([k, a, b] for k, (a, b) in enumerate(zip(log, want)) if a != b),
                                     [min(len(log), len(want)), None, None])
    res["pass"] = (strict.returncode == 0 and not strict_text and run.returncode == 0 and log == want
                   and not res["stub_other_output"])
    return res


def skeleton(job: bytes, records: list[dict]) -> bytes:
    text, pos = [], 0
    for r in records:
        text.append(job[pos:r["data_offset"]])
        pos = r["data_offset"] + r["data_bytes_ascii85"]
    text.append(job[pos:])
    return b"".join(text)


def byte_audit(job: bytes, records: list[dict], s12_job: bytes) -> dict:
    i12, i14 = s12_job.index(b"%!PS"), job.index(b"%!PS")
    e12, e14 = s12_job.index(b"%%EndComments\n"), job.index(b"%%EndComments\n")
    h12 = [ln for ln in s12_job[i12:e12].split(b"\n") if not ln.startswith((b"%%Title", b"%%Creator"))]
    h14 = [ln for ln in job[i14:e14].split(b"\n") if not ln.startswith((b"%%Title", b"%%Creator"))]
    k12 = s12_job.index(b"%%Page: 1 1\n")
    k14 = job.index(b"%%Page: 1 1\n")
    lines = skeleton(job, records).split(b"\n")
    res = {"wrapper_head_equals_S12_name_aside": job[:i14] == s12_job[:i12].replace(
               b'JOB NAME="E041-S12-PS-MIXTURE"', f'JOB NAME="{JOB_NAME}"'.encode()),
           "header_shape_equals_S12_title_creator_aside": h12 == h14,
           "setpagedevice_equals_S12": (job[e14 + 14:].split(b"\n", 1)[0] + b"\n" == s12.SETPAGEDEVICE
                                        and s12_job.count(s12.SETPAGEDEVICE) == 1
                                        and job.count(s12.SETPAGEDEVICE) == 1),
           "prologue_equals_S12": (s12_job[e12 + 14:k12] == job[e14 + 14:k14]
                                   == s12.SETPAGEDEVICE + s12.prologue()),
           "tail_equals_S12": s12_job.endswith(TAIL) and job.endswith(TAIL)
           and s12_job[s12_job.rindex(b"~>\ngrestore\n") + 12:] == job[job.rindex(b"~>\ngrestore\n") + 12:],
           "showpage_lines": lines.count(b"showpage"), "image_operators": lines.count(b">> image"),
           "gsave": lines.count(b"gsave"), "grestore": lines.count(b"grestore"),
           "non_ascii_bytes_after_wrapper": sum(1 for c in job[len(WRAPPER_HEAD):-len(s12.WRAPPER_TAIL)]
                                                if c > 126 or (c < 32 and c != 10)),
           "data_lines_starting_with_percent": sum(
               ln.startswith(b"%") for r in records
               for ln in job[r["data_offset"]:r["data_offset"] + r["data_bytes_ascii85"]].split(b"\n")),
           "skeleton_bytes": len(b"\n".join(lines))}
    n = len(records)
    res["pass"] = (all(res[k] for k in list(res)[:5]) and res["showpage_lines"] == 1
                   and res["image_operators"] == res["gsave"] == res["grestore"] == n
                   and res["non_ascii_bytes_after_wrapper"] == 0
                   and res["data_lines_starting_with_percent"] == 0)
    return res


def data_roundtrip(job: bytes, records: list[dict], images: list[dict]) -> dict:
    import base64
    ok = sum(base64.a85decode(job[r["data_offset"]:r["data_offset"] + r["data_bytes_ascii85"] - 3],
                              adobe=False, ignorechars=b" \n") == img["raster"].tobytes()
             for r, img in zip(records, images))
    return {"images": len(images), "ascii85_decodes_to_raster": ok, "pass": ok == len(images)}


def window_checks(img: np.ndarray, man: dict, npz_path: Path) -> dict:
    """Every window: the states and planes sliced from the npz (as the readout will) against the render's
    dots, decoded through the band palette."""
    bands = {b["name"]: b for b in man["bands"]}
    ok, bad, per_band = 0, [], Counter()
    with np.load(npz_path) as npz:
        arrays = {k: npz[k] for k in npz.files}
    for w in man["windows"]:
        b = bands[w["band"]]
        cd, wc = w["cell_dots"], w["cells"]
        cy, cx = w["cell_yx"]
        st = arrays[f"states_{b['name']}"][cy:cy + wc, cx:cx + wc]
        dy, dx = w["y_dots"] - b["y_dots"], w["x_dots"] - b["x_dots"]
        pl = arrays[f"planes_{b['name']}"][:, dy:dy + w["h_dots"], dx:dx + w["w_dots"]]
        win = img[w["y_dots"]:w["y_dots"] + w["h_dots"], w["x_dots"]:w["x_dots"] + w["w_dots"]]
        pal = np.array([b["palette"][s] for s in b["states"]], np.uint8)
        match = (win[:, :, None, :] == pal[None, None]).all(3)
        decoded = match.argmax(2)
        good = (bool((match.sum(2) == 1).all()) and np.array_equal(decoded, expand(st, cd))
                and np.array_equal(pl, np.moveaxis(ink_table(tuple(b["states"]))[decoded], 2, 0))
                and st.shape == (wc, wc))
        ok += good
        per_band[w["band"]] += 1
        if not good:
            bad.append(w["id"])
    return {"windows": len(man["windows"]), "checked": len(man["windows"]), "equal": ok,
            "per_band": dict(per_band), "first_bad": bad[:5], "pass": ok == len(man["windows"]) >= 200}


def geometry_checks(man: dict, images: list[dict]) -> dict:
    def inside(x: int, y: int, w: int, h: int) -> bool:
        return x >= 0 and y >= 0 and x + w <= PAGE_W_DOTS and y + h <= PAGE_H_DOTS

    rects = [("fid", f["id"], *f["xywh_dots"]) for f in man["fiducials"]]
    rects += [("band", b["name"], b["x_dots"], b["y_dots"], b["w_dots"], b["h_dots"]) for b in man["bands"]]
    count = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), np.uint8)
    for _, _, x, y, w, h in rects:
        count[y:y + h, x:x + w] += 1
    img_count = np.zeros_like(count)
    for i in images:
        x, y, w, h = i["xywh"]
        img_count[y:y + h, x:x + w] += 1
    bands = {b["name"]: b for b in man["bands"]}
    bars_in_strip = all(bands[r["band"]]["x_dots"] <= r["x_dots"] and r["x_dots"] + r["w_dots"]
                        <= bands[r["band"]]["x_dots"] + bands[r["band"]]["w_dots"]
                        and r["y_dots"] == bands[r["band"]]["y_dots"]
                        and r["h_dots"] == bands[r["band"]]["h_dots"]
                        for r in man["bars"])
    bar_count = np.zeros_like(count)
    for r in man["bars"]:
        bar_count[r["y_dots"]:r["y_dots"] + r["h_dots"], r["x_dots"]:r["x_dots"] + r["w_dots"]] += 1
    win_ok = all(bands[w["band"]]["x_dots"] <= w["x_dots"] and w["x_dots"] + w["w_dots"]
                 <= bands[w["band"]]["x_dots"] + bands[w["band"]]["w_dots"]
                 and bands[w["band"]]["y_dots"] <= w["y_dots"] and w["y_dots"] + w["h_dots"]
                 <= bands[w["band"]]["y_dots"] + bands[w["band"]]["h_dots"] for w in man["windows"])
    page = sorted(man["bands"], key=lambda b: b["y_dots"])
    gaps = [page[k + 1]["y_dots"] - page[k]["y_dots"] - page[k]["h_dots"]
            for k in range(len(man["bands"]) - 1)]
    b2 = bands["B2"]
    b2_cover = sorted((i["x_dots"], i["w_dots"]) for i in b2["images"])
    res = {"all_inside_page": all(inside(*r[2:]) for r in rects) and all(inside(*i["xywh"]) for i in images),
           "fiducials_bands_overlap_dots": int((count > 1).sum()),
           "image_overlap_dots": int((img_count > 1).sum()),
           "bars_inside_their_strip": bars_in_strip, "bar_overlap_dots": int((bar_count > 1).sum()),
           "windows_inside_their_band": win_ok, "band_gaps_dots": gaps,
           "fiducial_clearance_dots": min(
               min(abs(f["xywh_dots"][0] + f["xywh_dots"][2] - BAND_X_DOTS),
                   abs(f["xywh_dots"][0] - BAND_X_DOTS - BAND_W_DOTS),
                   abs(f["xywh_dots"][1] + f["xywh_dots"][3] - page[0]["y_dots"]),
                   abs(f["xywh_dots"][1] - page[-1]["y_dots"] - page[-1]["h_dots"]))
               for f in man["fiducials"]),
           "B2_tiles_cover_band_abutting": (
               len(b2_cover) == B2_TILES and b2_cover[0][0] == b2["x_dots"]
               and all(a[0] + a[1] == c[0] for a, c in zip(b2_cover, b2_cover[1:]))
               and b2_cover[-1][0] + b2_cover[-1][1] == b2["x_dots"] + b2["w_dots"]),
           "last_band_end_dots": page[-1]["y_dots"] + page[-1]["h_dots"],
           "band_x_mm": [mm(BAND_X_DOTS), mm(BAND_X_DOTS + BAND_W_DOTS)],
           "heights_multiple_of_6": all(b["h_dots"] % 6 == 0 for b in man["bands"]),
           "windows": len(man["windows"]),
           "windows_per_band": dict(Counter(w["band"] for w in man["windows"]))}
    res["pass"] = (res["all_inside_page"] and res["fiducials_bands_overlap_dots"] == 0
                   and res["image_overlap_dots"] == 0 and bars_in_strip and res["bar_overlap_dots"] == 0
                   and win_ok
                   and all(g == GAP_DOTS for g in gaps) and res["B2_tiles_cover_band_abutting"]
                   and res["last_band_end_dots"] <= LAST_END_DOTS and res["heights_multiple_of_6"]
                   and res["fiducial_clearance_dots"] > 0)
    return res


KEYWORDS = re.compile(rb"HP\w+|ColorSmart\w+|setpagedevice|sethalftone|setscreen|setcolorspace|/Width|"
                      rb"rectfill|setcmykcolor|ProcessColorModel")


def constructs(job: bytes) -> dict:
    """Constructs of a PostScript job from its short keyword lines: HP calls with operand and guard form,
    colour spaces, image sizes and depths, filters."""
    lines = [ln for ln in job.split(b"\n")
             if len(ln) < 400 and not ln.startswith(b"%") and KEYWORDS.search(ln)]
    calls: Counter = Counter()
    sizes: list[tuple[int, int, int]] = []
    spaces: Counter = Counter()
    other: Counter = Counter()
    for ln in lines:
        s = ln.decode("latin1").strip()
        m = re.search(r"/(\w+) where \{ pop (\S+) (\w+) \} if", s)
        n = re.search(r"\{ (\S+) (\w+) \} stopped", s)
        if m and m.group(1) == m.group(3):
            calls[f"where: {m.group(2)} {m.group(3)}"] += 1
        elif n and not s.startswith("{ <<"):
            calls[f"stopped: {n.group(1)} {n.group(2)}"] += 1
        elif "/BitsPerComponent" in s:
            w, h, bpc = (int(v) for v in re.findall(r"/(?:Width|Height|BitsPerComponent) (\d+)", s))
            sizes.append((w, h, bpc))
        elif "setcolorspace" in s:
            s = re.sub(r"Indexed /DeviceRGB \d+", "Indexed /DeviceRGB n", s)
            spaces[re.sub(r"<[0-9a-f]*>", "<lookup>", s)] += 1
        elif s.startswith("/") and " where " in s and " def " in s:
            continue
        else:
            other[s[:160]] += 1
    filters = Counter(f.decode() for f in re.findall(
        rb"/(ASCII85Decode|ASCIIHexDecode|FlateDecode|RunLengthDecode) filter", job))
    big = max(sizes, key=lambda t: t[0] * t[1]) if sizes else None
    return {"hp_calls": dict(calls), "colour_spaces": dict(spaces), "images": len(sizes),
            "image_sizes": dict(Counter(f"{w}x{h}x{b}bpc" for w, h, b in sizes)),
            "largest_image": list(big) if big else None, "filters": dict(filters),
            "other_constructs": dict(other)}


def lookups(job: bytes) -> set[tuple[int, int, int]]:
    out = set()
    for hexs in re.findall(rb"\[/Indexed /DeviceRGB \d+ <([0-9a-f]+)>\] setcolorspace", job):
        b = bytes.fromhex(hexs.decode())
        out |= {tuple(b[k:k + 3]) for k in range(0, len(b), 3)}
    return out


def abutting_pairs(rects: list[tuple[int, int, int, int]]) -> int:
    n = 0
    for i, (x, y, w, h) in enumerate(rects):
        for (x2, y2, w2, h2) in rects[i + 1:]:
            vert = (x + w == x2 or x2 + w2 == x) and y < y2 + h2 and y2 < y + h
            horiz = (y + h == y2 or y2 + h2 == y) and x < x2 + w2 and x2 < x + w
            n += vert or horiz
    return n


def novelty(job: bytes, records: list[dict], s12_job: bytes, s12_man: dict, s6_job: bytes) -> dict:
    c14, c12, c6 = constructs(job), constructs(s12_job), constructs(s6_job)
    printed_calls = set(c12["hp_calls"]) | set(c6["hp_calls"])
    s12_rects = [tuple(r["xywh_dots"]) for r in s12_man["ps_structure"]["images"]]
    new_rgb = sorted(lookups(job) - lookups(s12_job))
    return {
        "S14": c14, "S12": c12, "S6": c6,
        "hp_calls_new_vs_S12_and_S6": sorted(set(c14["hp_calls"]) - printed_calls),
        "hp_operators_new_vs_S12": sorted({k.split()[-1] for k in c14["hp_calls"]}
                                          - {k.split()[-1] for k in c12["hp_calls"]}),
        "image_sizes_new_vs_S12": sorted(set(c14["image_sizes"]) - set(c12["image_sizes"])),
        "rgb_values_new_vs_S12_lookups": [list(v) for v in new_rgb],
        "abutting_image_pairs": {"S14": abutting_pairs([tuple(r["xywh_dots"]) for r in records]),
                                 "S12": abutting_pairs(s12_rects)},
        "summary": [
            "`false ColorSmartColorMatching` per image, inside gsave, under an 8-bit Indexed DeviceRGB "
            "colour space and behind a `where` guard: never printed in this form (S6 printed it once page-"
            "level in a `stopped` guard under ProcessColorModel DeviceCMYK / PixelDepth 1, 1-bit DeviceCMYK "
            "image).",
            "Matching default and matching off on ONE sheet, same route, same alphabets, same palette.",
            "Full-width noise images 4392 dots wide and 684-942 tall (S12's largest band 4286x885 carried 35"
            " patches on white; S14's are dense noise edge to edge: 74 % of the page area in noise bands, 81"
            " % inside the band extent with strips and gaps).",
            "24 abutting images forming one band (B2), 183x942 each: no abutting images in S12.",
            "c2 cmy4-solid under Detail as one full-width band; cmy8-engine and cmyk5 at page scale on "
            "PostScript.",
            "Twelve displaced cyan candidates as solid bars under both matching states.",
        ]}


def sizes(job: bytes, records: list[dict], nb: bytes, man_bytes: int) -> dict:
    big = max(records, key=lambda r: r["data_bytes_ascii85"])
    return {"job_bytes": len(job), "images": len(records),
            "data_bytes_raw_total": sum(r["data_bytes_raw"] for r in records),
            "data_bytes_ascii85_total": sum(r["data_bytes_ascii85"] for r in records),
            "largest_image": {k: big[k] for k in ("image", "xywh_dots", "data_bytes_raw",
                                                  "data_bytes_ascii85")},
            "npz_bytes": len(nb), "manifest_bytes": man_bytes}


def s12_rebuild(s11_manifest: Path, s12_path: Path) -> dict:
    job = s12.build(s11_manifest.resolve())[4]
    on_disk = sha(s12_path.read_bytes())
    return {"rebuilt_sha256": sha(job), "on_disk_sha256": on_disk, "expected": S12_SHA256,
            "pass": sha(job) == on_disk == S12_SHA256}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="job path (.ps); manifest + npz beside it")
    ap.add_argument("--s12", type=Path, default=None,
                    help="S12 job (default: S12-ps-mixture.ps beside --out)")
    ap.add_argument("--s6", type=Path, default=None, help="S6 job (default: S6-maxescape.ps beside --out)")
    ap.add_argument("--s11", type=Path, default=None,
                    help="S11 manifest for the S12 rebuild (default: S11-pclxl-mixture.manifest.json "
                    "beside --out)")
    ap.add_argument("--verify", action="store_true", help="checks (1)-(9)")
    args = ap.parse_args()
    job, manifest, nb, images, arrays, records = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(job)
    man_path = args.out.with_name(args.out.stem + ".manifest.json")
    npz_path = args.out.with_name(manifest["bands_npz"]["file"])
    npz_path.write_bytes(nb)
    gen = {"generator": " ".join(["PYTHONPATH=src:.", sys.executable, *sys.argv])}
    man_path.write_text(json.dumps(manifest | gen | {"verification": "not run"}, indent=1) + "\n")
    if args.verify:
        s12_path = args.s12 or args.out.with_name("S12-ps-mixture.ps")
        s12_job = s12_path.read_bytes()
        s12_man = json.loads(s12_path.with_name(s12_path.stem + ".manifest.json").read_text())
        v: dict = {}
        img, messages, rc = render(args.out)
        v["1_render"] = render_checks(img, messages, rc, manifest, arrays, images)
        v["1_ascii85_roundtrip"] = data_roundtrip(job, records, images)
        v["2_guards"] = guard_checks(job, images)
        v["3_byte_audit_vs_S12"] = byte_audit(job, records, s12_job)
        v["4_windows"] = window_checks(img, manifest, npz_path)
        v["5_geometry"] = geometry_checks(manifest, images)
        again = build()
        v["6_two_builds_identical"] = {"job": again[0] == job, "manifest": again[1] == manifest,
                                       "npz": again[2] == nb}
        v["7_S12_rebuilt"] = s12_rebuild(args.s11 or args.out.with_name("S11-pclxl-mixture.manifest.json"),
                                         s12_path)
        v["8_novelty"] = novelty(job, records, s12_job, s12_man,
                                 (args.s6 or args.out.with_name("S6-maxescape.ps")).read_bytes())
        v["9_sizes"] = sizes(job, records, nb, len(json.dumps(manifest, indent=1)))
        v["pass"] = all([v["1_render"]["pass"], v["1_ascii85_roundtrip"]["pass"], v["2_guards"]["pass"],
                         v["3_byte_audit_vs_S12"]["pass"], v["4_windows"]["pass"], v["5_geometry"]["pass"],
                         all(v["6_two_builds_identical"].values()), v["7_S12_rebuilt"]["pass"]])
        man_path.write_text(json.dumps(manifest | gen | {"verification": v}, indent=1) + "\n")
        print(json.dumps(v, indent=1))
    print(f"{args.out}: {len(job)} B sha {manifest['sha256']}")
    print(f"{man_path}\n{npz_path}: {len(nb)} B sha {manifest['bands_npz']['sha256']}")


if __name__ == "__main__":
    main()
