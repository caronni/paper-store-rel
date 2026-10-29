"""e042 X1 — the AltaLink DENSITY probe: states per cell at c2 on the engine that prints toner overlaps.

ENGINE.  Xerox AltaLink C8245 (office).  It prints toner OVERLAPS solid and unscreened (textbook overprint,
e031), cell=1 is dead both polarities (a single 600-dpi dot reads 0.06 contrast), its c2-cmy8 volumes close at
r0700 with the receiver and r0850 with the analyzer (e033/e036/e037, 285 b/mm^2 net), and e036 measured the
three-toner cell's third layer as the weak state (C under M+Y reads 2-4x worse).  c1 is dead, so c2 is the
pitch floor and the density lever is STATES PER CELL.

QUESTION.  e041 S16/S17 (M281) showed an overlap cell's dot LAYOUT can carry a symbol.  X1 asks here:
(1) do dot-mixed pairs (A on one half of the cell, B on the other) read as states DISTINCT from the solid
overlap of the same pair, at c2 and c3; (2) does their orientation (column vs row at c2, the oriented
diagonal band at c3) carry a bit; (3) does position (which half) read at c2; (4) is K a better eighth state
than the three-toner cell (cmy7 + K), and does K hurt its C/M/Y neighbours; (5) controls: cmy8 solid, cmy7
solid, cmyw, K -- and the per-plane registration across the page from the readout's poses.

FOOTING = holo's AltaLink emission (src/holo/gen/ps.py PSDoc, unmodified; every AltaLink sheet of record,
e033/e035/e036, was PSDoc output printed with lpr -o raw): PSDoc's header and guarded setpagedevice at 600 dpi
(no PJL wrapper: the holo .ps is sent as is), every data band ONE put_cmyk_bitmap block (one composite
1-bit/component DeviceCMYK image, Decode [0 1 0 1 0 1 0 1], ASCIIHex, 128 hex chars per line), reproduced
line for line with ONE content difference: the K sample is 1 on K cells (holo's packer always writes K = 0;
the local packer here interleaves C, M, Y, K per pixel in the same order and pads rows to a byte after the
interleave, exactly as holo.gen.ps.pack_cmyk_rows).  Fiducials = S17's five K squares as THREE put_bitmap K
imagemasks, grouped as S17 grouped its fiducial images (fid-top F0+F1, fid-left F4, fid-bottom F2+F3), drawn
first.  Title "e042 X1 AltaLink density probe J=<jobid>" (jobid = the first 8 hex of the bands npz's sha256),
Creator this file; no HP operator anywhere.

GEOMETRY = S17's: page 4960 x 7016 dots (A4 at 600 dpi); fourteen bands 4392 x 438 dots at x 283,
y 283 + 462 k (k = 0..13), 24 white dots between bands, last end 6727; windows 46 x 46 c2 / 31 x 31 c3 cells
from each band's top-left, 4 x 47 per band; fiducials exactly S17's.

BANDS (k = 0..13 top to bottom; c2 unless said):
  X1  c2 cmy8 solid (W, C, M, Y, CM, CY, MY, CMY) -- the production alphabet, control, per-plane poses
  X2  c2 cmy7 solid (W, C, M, Y, CM, CY, MY)
  X3  c2 cmy7 + K (W, C, M, Y, K, CM, CY, MY) -- K as the eighth state
  X4  c2 cmy8 + K (W, C, M, Y, K, CM, CY, MY, CMY) -- K vs CMY discrimination
  X5  c2 cmy8 + mixed pairs (.., CMx, CYx, MYx), each mixed state 2 layouts [col, row] -- orientation
  X6  c2 as X5, each mixed state 4 layouts [col, row, col1, row1] -- orientation + position
  X7  c3 cmy8 solid
  X8  c3 cmy8 + mixed pairs, 2 layouts [band-0, band+0] -- c3 orientation
  X9  c3 cmy7 + K
  X10 c2 cmyw (W, C, M, Y)
  X11 c3 cmyw
  X12 c2 K (W, K) -- the K reference, K samples of the same CMYK image construct, no separate mask
  X13 c2 as X5, other seed -- the key band twice (position on the page)
  X14 c2 everything (W, C, M, Y, K, CM, CY, MY, CMY, CMx, CYx, MYx), mixed states 2 layouts [col, row]

LAYOUTS.  Grids are rows (top to bottom) of TONER-PLANE names ("W" none, "C", "CM", "CMY", "K", ...).  Solid
state s: every dot of the cell lays the planes of s (CMY = all three planes on every dot; K = the K plane
only).
A mixed pair XYx: A = X (C in CMx, CYx; M in MYx), B = Y; every dot ONE toner.  c2 (2x2, r row, c col):
  col  A on c = 0, B on c = 1;   row  A on r = 0, B on r = 1;
  col1 A on c = 1, B on c = 0;   row1 A on r = 1, B on r = 0      (2:2 dots).
c3 (3x3), S17's oriented band 5:4: "+" phase 0 (band+0): A on d = c - r in {0, 1}; "-" phase 0 (band-0): A on
a = r + c in {2, 3}; B on the other four, one of them 4-isolated ((0,2) for band+0, (2,2) for band-0).
Catalogue entries: solid {id "solid", orientation None, phase None}; c2 mixed {id, orientation "col"|"row",
position 0|1}; c3 mixed {id, orientation "-"|"+", phase 0}.  The list order is the layout index: c2 [col, row]
or [col, row, col1, row1]; c3 [band-0, band+0].

DRAW RULE (= S17's): rng = numpy default_rng(55000 + k); states = rng.choice(len(alphabet), size=(rows, cols))
row-major; then, for bands with any multi-candidate state, u = rng.random((rows, cols)) and layout =
floor(u * n_candidates(state of the cell)) (0 where n = 1).  Uniform over each alphabet.

OUTPUTS (beside --out): the job; <stem>.manifest.json (S17's band schema, tag "X1-altalink-probe", plus
"engine", "route"; per band "palette" = the toner planes each solid state lays, "planes" per state, "rgb_hint"
per solid state for a synthetic, "layout_catalogue", "layout_draw", "asks"); <stem>-bands.npz with
states_<band> (uint8), layouts_<band> (uint8), planes_<band> (4 x H x W uint8, C/M/Y/K per dot), fixed zip
timestamps.
--verify runs ps_altalink_verify.py's checks (1)-(8) and exits 0 only on overall pass.

PRINT ROUTE: lpr -o raw on the AltaLink, as e035 (its own footing, never merged with raw9100) -- only with the
owner's go in the session (.claude/rules/hardware.md); this module never prints.

    PYTHONPATH=src:. env/bin/python \\
        experiments/042-altalink-cell-encodings/ps_altalink_probe.py \\
        --out experiments/042-altalink-cell-encodings/build/X1-altalink-probe.ps --verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "041-m281-screen-routes"))

import ps_layouts as s17  # noqa: E402
import ps_scale as s14  # noqa: E402
import ps_trigger as s16  # noqa: E402
from holo.gen.ps import A4_DOTS_XY, HW_DPI, pack_bits_rows  # noqa: E402

TAG = "X1-altalink-probe"
TITLE = "e042 X1 AltaLink density probe"
CREATOR = "experiments/042-altalink-cell-encodings/ps_altalink_probe.py"
ENGINE = "xerox-altalink-c8245"
ROUTE = "lpr -o raw"
DPI = HW_DPI
PAGE_W_DOTS, PAGE_H_DOTS = A4_DOTS_XY
SECTION = "X"
SEED_BASE = 55000
BAND_X_DOTS, BAND_W_DOTS, BAND_H_DOTS = s17.BAND_X_DOTS, s17.BAND_W_DOTS, s17.BAND_H_DOTS
FIRST_Y_DOTS, GAP_DOTS = s17.FIRST_Y_DOTS, s17.GAP_DOTS
WINDOW_CELLS = s17.WINDOW_CELLS
HEX_LINE_CHARS = 128                                    # src/holo/gen/ps.py _HEX_LINE_CHARS
PLANES_ORDER = ("C", "M", "Y", "K")
# toner-plane combinations a dot can carry; the rgb hint = e041_mixture_synth.TONER_RGB multiplied as
# reflectances (the synthetic's model), never sent to the engine
TONER_RGB_HINT = {"C": (30, 150, 225), "M": (215, 40, 120), "Y": (245, 225, 30), "K": (25, 25, 30)}
DOT_NAMES = ("W", "C", "M", "Y", "K", "CM", "CY", "MY", "CMY")

CMY8 = ("W", "C", "M", "Y", "CM", "CY", "MY", "CMY")
CMY7 = ("W", "C", "M", "Y", "CM", "CY", "MY")
MIXED = ("CMx", "CYx", "MYx")
ALPHABETS: dict[str, tuple[str, ...]] = {
    "cmy8-solid": CMY8, "cmy7-solid": CMY7,
    "cmy7+K": ("W", "C", "M", "Y", "K", "CM", "CY", "MY"),
    "cmy8+K": ("W", "C", "M", "Y", "K", "CM", "CY", "MY", "CMY"),
    "cmy8+mixed": CMY8 + MIXED, "cmyw": ("W", "C", "M", "Y"), "wk": ("W", "K"),
    "cmyk9+mixed": ("W", "C", "M", "Y", "K", "CM", "CY", "MY", "CMY") + MIXED}
C2_OR, C2_OR_POS, C3_OR = ("col", "row"), ("col", "row", "col1", "row1"), ("band-0", "band+0")

Grid = tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class BandSpec:
    name: str
    variant: str
    alphabet: str
    cell_dots: int
    mixed: tuple[str, ...]                              # mixed-state layouts (catalogue order); () = none
    asks: str


BANDS: tuple[BandSpec, ...] = (
    BandSpec("X1", "c2_cmy8_solid", "cmy8-solid", 2, (),
             "control: the production cmy8 alphabet at c2 (e036/e037's rung's channel); per-plane poses "
             "across the page; CMY's weak third layer (e036) as a state error."),
    BandSpec("X2", "c2_cmy7_solid", "cmy7-solid", 2, (),
             "cmy7 without the three-toner cell: does dropping CMY lower the c2 state error below X1's?"),
    BandSpec("X3", "c2_cmy7_K", "cmy7+K", 2, (),
             "K as the eighth state instead of CMY: X3 against X1 at the same 3 bits; do K cells hurt their "
             "C/M/Y neighbours (plane errors against X2)?"),
    BandSpec("X4", "c2_cmy8_K", "cmy8+K", 2, (),
             "K and CMY on one page of cells: do the K cell and the three-toner cell separate (K vs CMY "
             "confusion)?"),
    BandSpec("X5", "c2_cmy8_mixed_orient", "cmy8+mixed", 2, C2_OR,
             "dot-mixed pairs at c2 (A on one column or row, B on the other) as states distinct from the "
             "solid overlap of the same pair; orientation (col / row) as one bit on the mixed cells."),
    BandSpec("X6", "c2_cmy8_mixed_orient_pos", "cmy8+mixed", 2, C2_OR_POS,
             "orientation AND position (which half carries A) on the c2 mixed cells: 4 layouts; position is "
             "a one-dot phase at the registration limit."),
    BandSpec("X7", "c3_cmy8_solid", "cmy8-solid", 3, (),
             "control at c3: the cmy8 alphabet on 3x3 cells."),
    BandSpec("X8", "c3_cmy8_mixed_orient", "cmy8+mixed", 3, C3_OR,
             "dot-mixed pairs at c3 (S17's oriented band 5:4) distinct from solid overlaps; orientation "
             "('-' / '+') as one bit."),
    BandSpec("X9", "c3_cmy7_K", "cmy7+K", 3, (),
             "cmy7 + K at c3: K as the eighth state where the cell is large enough not to bleed."),
    BandSpec("X10", "c2_cmyw", "cmyw", 2, (),
             "single toners only at c2: the no-overlap floor."),
    BandSpec("X11", "c3_cmyw", "cmyw", 3, (),
             "single toners only at c3."),
    BandSpec("X12", "c2_K", "wk", 2, (),
             "the K reference at c2: random 2x2 K cells as K samples of the same composite CMYK image."),
    BandSpec("X13", "c2_cmy8_mixed_orient_b", "cmy8+mixed", 2, C2_OR,
             "X5 again with another seed lower on the page: the key band twice (position on the page)."),
    BandSpec("X14", "c2_everything", "cmyk9+mixed", 2, C2_OR,
             "everything at c2: 12 states (K, CMY, three solid and three mixed pairs, mixed orientation), "
             "log2 12 = 3.58 raw bits per cell + the orientation bit on the mixed quarter."),
)


# ------------------------------------------------------------------------------------------------ layouts

def solid_grid(state: str, cd: int) -> Grid:
    return tuple(tuple([state] * cd) for _ in range(cd))


def mixed_grid(state: str, lid: str, cd: int) -> Grid:
    """The docstring's formulas: a mixed pair's cd x cd grid of single-toner plane names."""
    a, b = state[0], state[1]
    rule = {"col": lambda r, c: c == 0, "row": lambda r, c: r == 0, "col1": lambda r, c: c == 1,
            "row1": lambda r, c: r == 1, "band+0": lambda r, c: (c - r) in (0, 1),
            "band-0": lambda r, c: (r + c) in (2, 3)}[lid]
    if (cd == 2) != (lid in C2_OR_POS):
        raise SystemExit(f"layout {lid} at c{cd}")
    return tuple(tuple(a if rule(r, c) else b for c in range(cd)) for r in range(cd))


def entry(state: str, lid: str, cd: int) -> dict[str, Any]:
    if lid == "solid":
        return {"id": "solid", "orientation": None, "phase": None,
                "grid": [list(r) for r in solid_grid(state, cd)]}
    g = [list(r) for r in mixed_grid(state, lid, cd)]
    if cd == 2:
        return {"id": lid, "orientation": lid.rstrip("1"), "position": int(lid.endswith("1")), "grid": g}
    return {"id": lid, "orientation": lid[-2], "phase": int(lid[-1]), "grid": g}


def catalogue(b: BandSpec) -> dict[str, list[dict[str, Any]]]:
    """Every state's candidate layouts in catalogue order (solid states and W: one 'solid' entry)."""
    cd = b.cell_dots
    return {s: ([entry(s, lid, cd) for lid in b.mixed] if s in MIXED else [entry(s, "solid", cd)])
            for s in ALPHABETS[b.alphabet]}


def plane_bits(name: str) -> list[int]:
    return [int(p in name) for p in PLANES_ORDER]


def rgb_hint(name: str) -> list[int]:
    refl = np.ones(3)
    for p in name if name != "W" else "":
        refl *= np.array(TONER_RGB_HINT[p]) / 255.0
    return [int(v) for v in np.round(refl * 255)]


def draw(b: BandSpec, k: int, rows: int, cols: int, n_layouts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(states, layouts) by the DRAW RULE of the docstring (= S17's with seed 55000 + k)."""
    rng = np.random.default_rng(SEED_BASE + k)
    st = rng.choice(len(ALPHABETS[b.alphabet]), size=(rows, cols))
    if (n_layouts > 1).any():
        lay = np.floor(rng.random((rows, cols)) * n_layouts[st]).astype(np.int64)
    else:
        lay = np.zeros((rows, cols), np.int64)
    if (lay >= n_layouts[st]).any():
        raise SystemExit(f"{b.name}: layout index out of range")
    return st.astype(np.uint8), lay.astype(np.uint8)


# ------------------------------------------------------------------------------------------------ plan

def band_rows() -> list[tuple[int, BandSpec, int]]:
    return [(k, b, FIRST_Y_DOTS + k * (BAND_H_DOTS + GAP_DOTS)) for k, b in enumerate(BANDS)]


def fiducial_objects() -> tuple[list[dict], list[dict]]:
    """S17's five fiducials (s14.fiducial_plan) and its three fiducial groups as K imagemask objects."""
    fids, imgs = s14.fiducial_plan()
    for f in fids:
        f["planes"] = "K"
    objs = [{"name": im["name"], "kind": "imagemask", "band": None, "xywh": im["xywh"],
             "bits": np.ascontiguousarray(im["raster"].astype(np.uint8))} for im in imgs]
    return fids, objs


def plan() -> tuple[list[dict], list[dict], list[dict], dict[str, np.ndarray]]:
    """Fiducials, bands, objects (draw order: fiducial masks, then the bands top to bottom) and the npz."""
    fids, objects = fiducial_objects()
    colours = list(DOT_NAMES)
    ptab = np.array([plane_bits(c) for c in colours], np.uint8)
    bands, arrays = [], {}
    for k, b, y in band_rows():
        alpha = ALPHABETS[b.alphabet]
        cd = b.cell_dots
        rows, cols = BAND_H_DOTS // cd, BAND_W_DOTS // cd
        if rows * cd != BAND_H_DOTS or cols * cd != BAND_W_DOTS:
            raise SystemExit(f"{b.name}: not whole c{cd} cells")
        cat = catalogue(b)
        n_layouts = np.array([len(cat[s]) for s in alpha], np.int64)
        states, layouts = draw(b, k, rows, cols, n_layouts)
        dots_idx = s17.dot_colours(states, layouts, s17.tile_table(cat, alpha, colours))
        planes = np.ascontiguousarray(np.moveaxis(ptab[dots_idx], 2, 0))
        arrays[f"states_{b.name}"] = states
        arrays[f"layouts_{b.name}"] = layouts
        arrays[f"planes_{b.name}"] = planes
        xywh = (BAND_X_DOTS, y, BAND_W_DOTS, BAND_H_DOTS)
        obj = {"name": b.name, "kind": "cmyk-image", "band": b.name, "xywh": xywh, "planes": planes}
        solid = {s: es[0]["grid"][0][0] for s, es in cat.items() if es[0]["id"] == "solid"}
        rec = {"band": k, "name": b.name, "section": SECTION, "matching": None, "method": None,
               "neutral": None, **s16.rect_mm(*xywh), "alphabet": b.alphabet, "states": list(alpha),
               "palette": {s: ("" if g == "W" else g) for s, g in solid.items()},
               "planes": {s: "".join(p for p in PLANES_ORDER
                                     if any(p in c for e in es for row in e["grid"] for c in row if c != "W"))
                          for s, es in cat.items()},
               "rgb_hint": {s: rgb_hint(g) for s, g in solid.items()},
               "layout_catalogue": cat, "n_layouts": {s: len(es) for s, es in cat.items()},
               "layout_draw": bool((n_layouts > 1).any()), "lookup": [], "lookup_name": None,
               "variant": b.variant, "draw": "choice+layout" if (n_layouts > 1).any() else "choice",
               "cell_dots": cd, "cells_hw": [rows, cols], "seed": SEED_BASE + k, "gaps": [],
               "k_cells": int((states == alpha.index("K")).sum()) if "K" in alpha else 0,
               "asks": b.asks, "images": [{"image": b.name, "kind": "cmyk-image", "x_dots": xywh[0],
                                           "y_dots": xywh[1], "w_dots": xywh[2], "h_dots": xywh[3],
                                           "neutral": None, "tile": None}]}
        bands.append(rec)
        objects.append(obj)
    return fids, bands, objects, arrays


# ------------------------------------------------------------------------------------------------ emission

def pt(dots: float) -> float:
    return dots * 72.0 / DPI


def pack_cmyk_rows_k(planes: np.ndarray) -> bytes:
    """(4, H, W) C/M/Y/K bits -> holo.gen.ps.pack_cmyk_rows' byte layout with the K sample carried (C, M, Y, K
    per pixel, MSB first, each row padded to a byte after the interleave)."""
    if planes.ndim != 3 or planes.shape[0] != 4 or not np.isin(planes, (0, 1)).all():
        raise SystemExit(f"expected (4, H, W) 0/1 planes, got {planes.shape}")
    h, w = planes.shape[1:]
    cmyk = np.ascontiguousarray(np.moveaxis(planes.astype(np.uint8), 0, 2))
    return pack_bits_rows(cmyk.reshape(h, w * 4))


def hex_lines(packed: bytes) -> list[str]:
    hx = packed.hex()
    return [hx[i:i + HEX_LINE_CHARS] for i in range(0, len(hx), HEX_LINE_CHARS)]


def object_lines(o: dict) -> tuple[list[str], list[str], list[str], bytes]:
    """(operator lines before the data, hex data lines, lines after, raw packed bytes) of PSDoc.put_bitmap
    (imagemask) or PSDoc.put_cmyk_bitmap (cmyk-image), point arithmetic as theirs."""
    x, y, w, h = o["xywh"]
    x_pt, y_pt = pt(x), pt(PAGE_H_DOTS) - pt(y + h)
    if o["kind"] == "imagemask":
        raw = pack_bits_rows(o["bits"])
        head = ["gsave", f"{x_pt:.6f} {y_pt:.6f} translate", f"{pt(w):.6f} {pt(h):.6f} scale",
                "0.000 0.000 0.000 1.000 setcmykcolor", f"{w} {h} true [{w} 0 0 -{h} 0 {h}]",
                "currentfile /ASCIIHexDecode filter imagemask"]
    else:
        raw = pack_cmyk_rows_k(o["planes"])
        head = ["gsave /DeviceCMYK setcolorspace", f"{x_pt:.6f} {y_pt:.6f} translate",
                f"{pt(w):.6f} {pt(h):.6f} scale", "<< /ImageType 1",
                f"   /Width {w} /Height {h} /BitsPerComponent 1", "   /Decode [0 1 0 1 0 1 0 1]",
                f"   /ImageMatrix [{w} 0 0 -{h} 0 {h}]", "   /DataSource currentfile /ASCIIHexDecode filter",
                ">> image"]
    return head, hex_lines(raw), [">", "grestore"], raw


def header_lines(jobid: str) -> list[str]:
    """PSDoc.render's header for one A4 page at 600 dpi, guarded setpagedevice; Creator this file."""
    w_pt, h_pt = pt(PAGE_W_DOTS), pt(PAGE_H_DOTS)
    spd = (f"<< /PageSize [{w_pt:.2f} {h_pt:.2f}] /HWResolution [{DPI} {DPI}] /Duplex false >> "
           "setpagedevice")
    return ["%!PS-Adobe-3.0", f"%%Title: {TITLE} J={jobid}", f"%%Creator: {CREATOR}", "%%LanguageLevel: 2",
            "%%DocumentData: Clean7Bit", f"%%BoundingBox: 0 0 {-(-w_pt // 1):.0f} {-(-h_pt // 1):.0f}",
            "%%Pages: 1", "%%EndComments", "{ " + spd + " } stopped { } if"]


def emit_job(objects: list[dict], jobid: str) -> tuple[bytes, list[dict]]:
    """The job (PSDoc.render's shape) and one record per object (line spans, byte offsets of the data)."""
    lines = header_lines(jobid) + ["%%Page: 1 1"]
    records = []
    for o in objects:
        head, data, tail, raw = object_lines(o)
        lines += head
        first = len(lines)
        lines += data
        lines += tail
        k_samples = int(o["planes"][3].sum()) if o["kind"] == "cmyk-image" else 0
        records.append({"image": o["name"], "kind": o["kind"], "band": o["band"],
                        "xywh_dots": list(o["xywh"]), "operators": head, "data_filter": "ASCIIHexDecode",
                        "data_line_first": first,
                        "data_lines": len(data), "data_bytes_raw": len(raw),
                        "data_bytes_hex": sum(len(d) + 1 for d in data) + 2, "k_samples": k_samples,
                        "raster_sha256": hashlib.sha256(raw).hexdigest()})
    lines += ["showpage", "%%Trailer", "%%EOF", ""]
    text = "\n".join(lines).encode("ascii")
    offs = np.cumsum([0] + [len(ln) + 1 for ln in lines])
    for r in records:
        r["data_offset"] = int(offs[r["data_line_first"]])
        r["data_bytes"] = r["data_bytes_hex"]
    return text, records


def notes() -> list[str]:
    return [
        "FOOTING = holo's AltaLink emission: src/holo/gen/ps.py PSDoc's header, guarded setpagedevice and "
        "page frame; every band one put_cmyk_bitmap block; the fiducials put_bitmap K imagemasks; no PJL, no "
        "HP operator. ONE content difference: K samples are 1 on K cells (holo writes K = 0 always).",
        "GEOMETRY = S17's: 14 bands 4392 x 438 dots at x 283, y 283 + 462 k, 24 white dots between, last "
        "end 6727; windows 46x46 c2 / 31x31 c3 from each band's top-left (4 x 47); fiducials = S17's five, "
        "as three imagemasks (fid-top F0+F1, fid-left F4, fid-bottom F2+F3), drawn first.",
        "DRAWS: default_rng(55000 + k), k = band position X1 = 0 .. X14 = 13; states = "
        ".choice(len(alphabet), size=(rows, cols)); then, only for bands with a multi-candidate state "
        "(X5, X6, X8, X13, X14), u = .random((rows, cols)) and layout = floor(u * n_candidates(state)).",
        "GRIDS are toner-plane names per dot (W, C, M, Y, K, CM, CY, MY, CMY); planes_<band> is their "
        "C/M/Y/K expansion; a K dot lays K only.",
        "c2 mixed: col A on column 0, row A on row 0, col1 A on column 1, row1 A on row 1 (A = first toner "
        "of the pair, B the second, 2:2). c3 mixed: band+0 A on c - r in {0, 1}, band-0 A on r + c in {2, 3} "
        "(5:4, one isolated B dot) = S17's band+0 / band-0.",
        "rgb_hint = e041_mixture_synth.TONER_RGB multiplied as reflectances, for synthetics only; nothing in "
        "the job is RGB.",
        "PRINT: lpr -o raw on the AltaLink as e035, with the owner's go; this generator never prints.",
    ] + [f"{b.name} ({b.variant}): {b.asks}" for b in BANDS]


def build() -> tuple[bytes, dict, bytes, list[dict], dict[str, np.ndarray], list[dict]]:
    """The job, the manifest (no verification, no generator line), npz bytes, objects, arrays, records."""
    fids, bands, objects, arrays = plan()
    nb = s14.npz_bytes(arrays)
    jobid = hashlib.sha256(nb).hexdigest()[:8]
    job, records = emit_job(objects, jobid)
    manifest = {
        "tag": TAG, "engine": ENGINE, "route": ROUTE, "dpi": DPI,
        "page_dots": {"w": PAGE_W_DOTS, "h": PAGE_H_DOTS},
        "bytes": len(job), "sha256": hashlib.sha256(job).hexdigest(), "jobid": jobid,
        "bands_npz": {"file": f"{TAG}-bands.npz", "sha256": hashlib.sha256(nb).hexdigest(), "bytes": len(nb),
                      "keys": sorted(arrays)},
        "planes_order": list(PLANES_ORDER), "fiducials": fids, "bands": bands, "bars": [],
        "windows": s16.windows(bands),
        "colours": {c: {"rgb": rgb_hint(c), "planes": "" if c == "W" else c} for c in DOT_NAMES},
        "palette": {c: rgb_hint(c) for c in DOT_NAMES},
        "alphabets": {k: list(v) for k, v in ALPHABETS.items()},
        "variants": [b.variant for b in BANDS],
        "layout_rule": "states = default_rng(55000 + k).choice(len(alphabet), size=(rows, cols)); then, if "
                       "any state has n > 1 candidates, u = rng.random((rows, cols)), layout = "
                       "floor(u * n(state of the cell))",
        "ps_structure": {"footing": "src/holo/gen/ps.py PSDoc (put_cmyk_bitmap bands, put_bitmap fiducials)",
                         "header": header_lines(jobid), "data_filter": "ASCIIHexDecode",
                         "hex_columns": HEX_LINE_CHARS, "pt_per_dot": 72.0 / DPI, "images": records},
        "notes": notes(),
    }
    return job, manifest, nb, objects, arrays, records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="job path (.ps); manifest + npz beside it")
    ap.add_argument("--verify", action="store_true", help="checks (1)-(8); exit 1 unless all pass")
    args = ap.parse_args()
    job, manifest, nb, objects, arrays, records = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(job)
    man_path = args.out.with_name(args.out.stem + ".manifest.json")
    npz_path = args.out.with_name(manifest["bands_npz"]["file"])
    npz_path.write_bytes(nb)
    gen = {"generator": " ".join(["PYTHONPATH=src:.", sys.executable, *sys.argv])}
    man_path.write_text(json.dumps(manifest | gen | {"verification": "not run"}, indent=1) + "\n")
    ok = True
    if args.verify:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import ps_altalink_verify as av
        v = av.verify(args.out, man_path, npz_path, job, manifest, nb, objects, arrays, records, build)
        ok = bool(v["pass"])
        man_path.write_text(json.dumps(manifest | gen | {"verification": v}, indent=1) + "\n")
        print(json.dumps(v, indent=1))
    print(f"{args.out}: {len(job)} B sha {manifest['sha256']}")
    print(f"{man_path}\n{npz_path}: {len(nb)} B sha {manifest['bands_npz']['sha256']}")
    if not ok:
        print("VERIFY FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
