"""e041 S17 — the LAYOUT probe for the HP M281 on the production route (PostScript), on S16's footing.

THE QUESTION.  S16 (041.5m) showed that a cmy8 whose overlap cells are built from single-toner dots is never
screened and reads 3.2 % at c3 (the CMY cell the weak state, 85 %); its fixed layouts put a 283 lpi 45-degree
lattice on the page.  S17 asks whether the layout's ORIENTATION and PHASE can carry bits, whether a 7-state
alphabet (no CMY) is the better row, and whether c2 dot-mixed cells read with COLUMN / ROW pair layouts
instead of S12's diagonal pairs (S12 A21 c2: CM 30 %, CY 39 %, CMY 56 %, MY 11 %).  Scanned at 4800 dpi.

BANDS (top to bottom = draw order, k = 0..13, all section A, 4392 x 438 dots each = 146 c3 / 219 c2 cell rows
= 4 window rows of 31 / 46 cells, 47 windows across; at x 283, y 283 + 462 k, 24 white dots between, last
end 6727 <= 6732; fiducials exactly S16's, drawn first; no strip.  Dot-mixed bands Smooth ProcBlack, lookup
W, C-solid (0,208,255), M-solid (240,0,192), Y (255,255,0) = S16 T11's):
  U1  c3 cmy8 dot-mixed, S16 T2's layouts (X; stripes "-" phase 0) -- control (= S16 T2, other seed)
  U2  c3 cmy7 dot-mixed (W, C, M, Y, CM, CY, MY), X layouts -- the reduced-alphabet erasure-row candidate
  U3  c3 cmy8: two-toner X; CMY stripes, random orientation per cell (phase 0) -- one orientation bit on CMY
  U4  c3 cmy8: two-toner oriented bands, random orientation (phase 0); CMY stripes random orientation
      (phase 0) -- orientation on every overlap cell
  U5  c3 cmy8: orientation fixed "-"; random phase per overlap cell (bands {0,1}; CMY {0,1,2})
  U6  c3 cmy8: random orientation AND phase per overlap cell (two-toner 4 layouts, CMY 6) -- keystream-style
  U7  c3 cmy7: two-toner oriented bands, random orientation (phase 0) -- 7 states + orientation
  U8  c2 cmy7 dot-mixed, COLUMN pairs
  U9  c2 cmy7 dot-mixed, ROW pairs
  U10 c2 cmy8 dot-mixed, DIAGONAL pairs incl. the CMY cell (= S12 A21's construction at page scale)
  U11 c2 cmy7 dot-mixed, DIAGONAL pairs (U10 without CMY: the layout reference for U8 / U9)
  U12 cmyw c2 Detail ProcBlack -- production control (= S16 T12)
  U13 cmyw c3 Smooth ProcBlack -- production control (= S16 T11)
  U14 c2 K: ONE K imagemask of random 2x2 cells (W / K uniform) over the band, no Indexed image -- the
      archival row on the same sheet (src/holo/gen/ps.py put_bitmap idiom exactly as S16 T9 / bar A)

LAYOUTS.  In a 3x3 cell r = row 0..2 top to bottom, c = col 0..2, d = c - r, a = r + c; toners C -> C-solid,
M -> M-solid, Y -> Y; A = the first toner of a two-toner state's name (C in CM / CY, M in MY), B the second.
  X (c3, two-toner, orientation / phase null): A on (r + c) even (5 dots), B on odd (4) = S16 / DOTMIX3.
  CMY stripes (c3): "-" phase p: (C, M, Y)[((r + c) + p) mod 3]; "+" phase p: (C, M, Y)[((c - r) mod 3 + p)
      mod 3]; p in {0, 1, 2}; "-" phase 0 = S16's DOTMIX3 CMY.  3:3:3 dots.
  Oriented band (c3, two-toner, 5:4): "+" 0: A on d in {0, 1}; "+" 1: A on d in {-1, 0}; "-" 0: A on a in
      {2, 3}; "-" 1: A on a in {1, 2}; B on the other four, exactly one of them 4-isolated, a corner:
      (r, c) = (0,2), (2,0), (2,2), (0,0) for "+" 0, "+" 1, "-" 0, "-" 1.
  c2 (2x2) two-toner: diag = A on (0,0),(1,1), B on (0,1),(1,0) (S12 DOTMIX2); col = A column 0, B column 1;
      row = A row 0, B row 1.  c2 CMY (U10 only) = DOTMIX2's ((C, M), (Y, C)).  2:2 and 2:1:1 dots.
  Catalogue order (= the layout index): orientation "-" before "+", phase ascending within it.

DRAWS: rng = numpy default_rng(54000 + k); states = rng.choice(len(alphabet), size=(rows, cols)) row-major;
then, for bands with any multi-candidate state, u = rng.random((rows, cols)) and layout =
floor(u * n_candidates(state of that cell)) (0 where n = 1).  U14: alphabet (W, K), the same choice call, no
layout draw.

ROUTE AND FOOTING = S16's (ps_trigger.py, printed, page 3403, no error): S1's PJL wrapper without
BITSPERPIXEL / RET (JOB NAME "E041-S17-PS-LAYOUTS"), S16's header shape (title / creator aside), the
setpagedevice line, S12's bare-name prologue byte for byte, 8-bit [/Indexed /DeviceRGB 3 <lookup>] images in
gsave / grestore, ASCII85, S16's four HP calls per image in S16's order (no ColorSmartColorMatching), the K
imagemask block = S16's mask_lines (holo put_bitmap) behind its comment line, no HP call.

Outputs (beside --out): the job; <stem>.manifest.json (tag "S17-ps-layouts"; S16's band schema plus per band
"layout_catalogue" {state: [{"id", "orientation", "phase", "grid"}, ...]} -- every state has a list, solid
states and W one entry; no "cell_layouts": a state's grid is its catalogue entry); <stem>-bands.npz with
states_<band> (uint8 index into "states"), layouts_<band> (uint8 index into that cell's state's catalogue
list) and planes_<band> (4 x H x W uint8, C/M/Y/K ink per dot), fixed zip timestamps.
--verify runs checks (1)-(10) of ps_layouts_verify.py and exits 0 only on overall pass.

    PYTHONPATH=src:. env/bin/python \\
        experiments/041-m281-screen-routes/ps_layouts.py \\
        --out experiments/041-m281-screen-routes/build/S17-ps-layouts.ps --verify
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

import ps_mixture as s12
import ps_scale as s14
import ps_trigger as s16
from pcl_planar import sha
from pclxl_mixture_arms import DOTMIX2
from pclxl_probe import DPI

TAG = "S17-ps-layouts"
JOB_NAME = "E041-S17-PS-LAYOUTS"
S16_SHA256 = "1ccf884a64b13dc5fad7667af667861cd3179daf0ae23ead04658bf20638d2b8"
PAGE_H_DOTS, PAGE_W_DOTS = s16.PAGE_H_DOTS, s16.PAGE_W_DOTS
WRAPPER_HEAD = s12.UEL + f'@PJL JOB NAME="{JOB_NAME}"\r\n@PJL ENTER LANGUAGE=POSTSCRIPT\r\n'.encode()
_S16_TITLE = b"%%Title: e041 S16 PostScript trigger probe\n"
_S16_CREATOR = b"%%Creator: experiments/041-m281-screen-routes/ps_trigger.py\n"
assert _S16_TITLE in s16.HEADER and _S16_CREATOR in s16.HEADER
HEADER = (s16.HEADER.replace(_S16_TITLE, b"%%Title: e041 S17 PostScript layout probe\n")
          .replace(_S16_CREATOR, b"%%Creator: experiments/041-m281-screen-routes/ps_layouts.py\n"))
TAIL = s16.TAIL
SECTION = "A"
SEED_BASE = 54000
BAND_X_DOTS, BAND_W_DOTS = s16.BAND_X_DOTS, s16.BAND_W_DOTS
FIRST_Y_DOTS, GAP_DOTS, LAST_END_DOTS = s16.FIRST_Y_DOTS, s16.GAP_DOTS, s16.LAST_END_DOTS
BAND_H_DOTS = 438
WINDOW_CELLS = s16.WINDOW_CELLS

Grid = tuple[tuple[str, ...], ...]
COLOURS = s16.COLOURS                                      # colour name -> (device RGB, toner planes)
SINGLE = s16.SINGLE                                        # toner letter -> colour name
TONERS = ("C", "M", "Y")
CMY8 = ("W", "C", "M", "Y", "CM", "CY", "MY", "CMY")
CMY7 = ("W", "C", "M", "Y", "CM", "CY", "MY")
ALPHABETS: dict[str, tuple[str, ...]] = {
    "cmy8-dotmix": CMY8, "cmy7-dotmix": CMY7, "cmy4-solidC": s16.CMY4, "wk-mask": ("W", "K")}
LOOKUP = "cmy4"                                            # every image band's lookup = S16 T11's

# Layout families per band: (two-toner layouts, CMY layouts) as catalogue ids, in catalogue order.
X3, DIAG, COL, ROW = "X", "diag", "col", "row"
S_M0, S_M1, S_M2, S_P0, S_P1, S_P2 = "stripe-0", "stripe-1", "stripe-2", "stripe+0", "stripe+1", "stripe+2"
B_M0, B_M1, B_P0, B_P1 = "band-0", "band-1", "band+0", "band+1"


@dataclass(frozen=True)
class BandSpec:
    name: str
    variant: str
    alphabet: str
    cell_dots: int
    method: str | None                                     # None: U14, no image, no HP call
    two: tuple[str, ...]                                   # two-toner state layouts (catalogue order)
    cmy: tuple[str, ...]                                   # CMY state layouts (catalogue order)
    asks: str


BANDS: tuple[BandSpec, ...] = (
    BandSpec("U1", "cmy8_X_stripe-0_control", "cmy8-dotmix", 3, "smooth", (X3,), (S_M0,),
             "control = S16 T2 (other seed): fixed layouts, the 283 lpi 45-degree lattice; S16 read 3.2 % at "
             "c3, CMY the weak state."),
    BandSpec("U2", "cmy7_X", "cmy7-dotmix", 3, "smooth", (X3,), (),
             "the reduced-alphabet erasure-row candidate: 7 states without CMY, X layouts -- does dropping "
             "the weak CMY state lower the state error below U1's?"),
    BandSpec("U3", "cmy8_X_stripe_orient", "cmy8-dotmix", 3, "smooth", (X3,), (S_M0, S_P0),
             "one orientation bit on CMY cells: stripes '-' or '+' (phase 0) at random -- does orientation "
             "read (CMY x 2 = 9 classes) and does mixing orientations cost the other states?"),
    BandSpec("U4", "cmy8_band_orient_stripe_orient", "cmy8-dotmix", 3, "smooth", (B_M0, B_P0), (S_M0, S_P0),
             "orientation on every overlap cell: oriented bands (5:4) and stripes, '-' or '+' at random, "
             "phase 0 (12 classes)."),
    BandSpec("U5", "cmy8_phase", "cmy8-dotmix", 3, "smooth", (B_M0, B_M1), (S_M0, S_M1, S_M2),
             "phase readability: orientation fixed '-', random phase (bands 2, CMY 3; 13 classes)."),
    BandSpec("U6", "cmy8_orient_phase", "cmy8-dotmix", 3, "smooth", (B_M0, B_M1, B_P0, B_P1),
             (S_M0, S_M1, S_M2, S_P0, S_P1, S_P2),
             "the keystream-style candidate: random orientation and phase (two-toner 4, CMY 6; 22 classes)."),
    BandSpec("U7", "cmy7_band_orient", "cmy7-dotmix", 3, "smooth", (B_M0, B_P0), (),
             "7 states + orientation on the three two-toner states (10 classes): the likely production "
             "combination."),
    BandSpec("U8", "c2_cmy7_col", "cmy7-dotmix", 2, "smooth", (COL,), (),
             "c2 dot-mixed with COLUMN pairs (A column 0, B column 1) against U11's diagonal pairs."),
    BandSpec("U9", "c2_cmy7_row", "cmy7-dotmix", 2, "smooth", (ROW,), (),
             "c2 dot-mixed with ROW pairs (A row 0, B row 1) against U11's diagonal pairs."),
    BandSpec("U10", "c2_cmy8_diag", "cmy8-dotmix", 2, "smooth", (DIAG,), (DIAG,),
             "S12 A21's c2 dot-mixed construction at page scale (S12 patch: CM 30 %, CY 39 %, CMY 56 %, MY "
             "11 %)."),
    BandSpec("U11", "c2_cmy7_diag", "cmy7-dotmix", 2, "smooth", (DIAG,), (),
             "U10 without CMY: the diagonal layout reference for U8 / U9."),
    BandSpec("U12", "cmy4_solidC_c2_detail", "cmy4-solidC", 2, "detail", (), (),
             "production control at c2 Detail (= S16 T12)."),
    BandSpec("U13", "cmy4_solidC_c3", "cmy4-solidC", 3, "smooth", (), (),
             "production control at c3 Smooth (= S16 T11)."),
    BandSpec("U14", "c2_K_imagemask", "wk-mask", 2, None, (), (),
             "the archival row on the same sheet: random 2x2 K cells drawn by ONE K imagemask (holo "
             "put_bitmap), no Indexed image; K by toner on a sheet whose other bands are CMY."),
)


# ------------------------------------------------------------------------------------------------ layouts

def layout_grid(lid: str, state: str, cd: int) -> Grid:
    """The cd x cd grid of colour names of layout `lid` for an overlap state (the docstring's formulas)."""
    if state == "CMY":
        if cd == 2:
            if lid != DIAG:
                raise SystemExit(f"c2 CMY layout {lid}")
            return tuple(tuple(SINGLE[t] for t in row) for row in DOTMIX2["CMY"])
        orient, phase = lid[len("stripe")], int(lid[-1])
        return tuple(tuple(SINGLE[TONERS[(((r + c) if orient == "-" else (c - r) % 3) + phase) % 3]]
                           for c in range(3)) for r in range(3))
    a, b = SINGLE[state[0]], SINGLE[state[1]]
    if cd == 2:
        on = {DIAG: lambda r, c: r == c, COL: lambda r, c: c == 0, ROW: lambda r, c: r == 0}[lid]
        return tuple(tuple(a if on(r, c) else b for c in range(2)) for r in range(2))
    if lid == X3:
        return tuple(tuple(a if (r + c) % 2 == 0 else b for c in range(3)) for r in range(3))
    orient, phase = lid[len("band")], int(lid[-1])
    sel = ({0: (0, 1), 1: (-1, 0)} if orient == "+" else {0: (2, 3), 1: (1, 2)})[phase]
    return tuple(tuple(a if ((c - r) if orient == "+" else (r + c)) in sel else b for c in range(3))
                 for r in range(3))


def isolated_b(grid: Grid | list[list[str]], b_colour: str) -> list[tuple[int, int]]:
    """The B dots of a grid with no 4-neighbour B inside the cell."""
    n = len(grid)
    return [(r, c) for r in range(n) for c in range(n) if grid[r][c] == b_colour and not any(
        0 <= r + dr < n and 0 <= c + dc < n and grid[r + dr][c + dc] == b_colour
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)))]


def entry(lid: str, grid: Grid) -> dict[str, Any]:
    orient: str | None = None
    phase: int | None = None
    if lid.startswith(("stripe", "band")):
        orient, phase = lid[-2], int(lid[-1])
    return {"id": lid, "orientation": orient, "phase": phase, "grid": [list(row) for row in grid]}


def catalogue(b: BandSpec) -> dict[str, list[dict[str, Any]]]:
    """Every state's candidate layouts in catalogue order (solid states and W: one 'solid' entry)."""
    cd = b.cell_dots
    out: dict[str, list[dict[str, Any]]] = {}
    for s in ALPHABETS[b.alphabet]:
        if s == "CMY":
            out[s] = [entry(lid, layout_grid(lid, s, cd)) for lid in b.cmy]
        elif len(s) == 2:
            out[s] = [entry(lid, layout_grid(lid, s, cd)) for lid in b.two]
        else:
            colour = "K-mask" if b.alphabet == "wk-mask" and s == "K" else SINGLE.get(s, s)
            out[s] = [entry("solid", s16.solid(colour, cd))]
    return out


def band_colours(cat: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Colour names the band's catalogue uses, W first, then in COLOURS order."""
    used = {c for es in cat.values() for e in es for row in e["grid"] for c in row}
    return [c for c in COLOURS if c in used]


def tile_table(cat: dict[str, list[dict[str, Any]]], alpha: tuple[str, ...],
               colours: list[str]) -> np.ndarray:
    """(states, max layouts, cd, cd) uint8 colour index; unused slots 255."""
    n_max = max(len(cat[s]) for s in alpha)
    cd = len(cat[alpha[0]][0]["grid"])
    t = np.full((len(alpha), n_max, cd, cd), 255, np.uint8)
    for i, s in enumerate(alpha):
        for j, e in enumerate(cat[s]):
            t[i, j] = [[colours.index(c) for c in row] for row in e["grid"]]
    return t


def dot_colours(states: np.ndarray, layouts: np.ndarray, tiles: np.ndarray) -> np.ndarray:
    """(rows * cd, cols * cd) colour index: every cell painted through its (state, layout) grid."""
    rows, cols = states.shape
    cd = tiles.shape[2]
    out = tiles[states, layouts]
    if (out == 255).any():
        raise SystemExit("a cell indexes a layout its state does not have")
    return np.ascontiguousarray(out.transpose(0, 2, 1, 3).reshape(rows * cd, cols * cd))


def draw(b: BandSpec, k: int, rows: int, cols: int, n_layouts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(states, layouts) by the DRAWS rule of the docstring."""
    rng = np.random.default_rng(SEED_BASE + k)
    st = rng.choice(len(ALPHABETS[b.alphabet]), size=(rows, cols))
    if (n_layouts > 1).any():
        u = rng.random((rows, cols))
        lay = np.floor(u * n_layouts[st]).astype(np.int64)
    else:
        lay = np.zeros((rows, cols), np.int64)
    if (lay >= n_layouts[st]).any():
        raise SystemExit(f"{b.name}: layout index out of range")
    return st.astype(np.uint8), lay.astype(np.uint8)


# ------------------------------------------------------------------------------------------------ plan

def band_rows() -> list[tuple[int, BandSpec, int]]:
    """(band index, spec, y_dots), top to bottom = draw order, 24 white dots between bands."""
    return [(k, b, FIRST_Y_DOTS + k * (BAND_H_DOTS + GAP_DOTS)) for k, b in enumerate(BANDS)]


def plan() -> tuple[list[dict], list[dict], list[dict], dict[str, np.ndarray]]:
    """Fiducials, bands, objects (draw order) and the npz arrays."""
    fids, objects = s14.fiducial_plan()
    bands, arrays = [], {}
    lookup = s16.LOOKUPS[LOOKUP]
    for k, b, y in band_rows():
        alpha = ALPHABETS[b.alphabet]
        cd = b.cell_dots
        rows, cols = BAND_H_DOTS // cd, BAND_W_DOTS // cd
        if rows * cd != BAND_H_DOTS or cols * cd != BAND_W_DOTS:
            raise SystemExit(f"{b.name}: not whole c{cd} cells")
        cat = catalogue(b)
        n_layouts = np.array([len(cat[s]) for s in alpha], np.int64)
        states, layouts = draw(b, k, rows, cols, n_layouts)
        colours = band_colours(cat)
        dots_idx = dot_colours(states, layouts, tile_table(cat, alpha, colours))
        arrays[f"states_{b.name}"] = states
        arrays[f"layouts_{b.name}"] = layouts
        planes = np.moveaxis(s16.plane_table(colours)[dots_idx], 2, 0)
        arrays[f"planes_{b.name}"] = np.ascontiguousarray(planes)
        xywh = (BAND_X_DOTS, y, BAND_W_DOTS, BAND_H_DOTS)
        if b.method is None:
            objs = [s16.mask_rec(f"{b.name}-mask", b.name, xywh, dots_idx == colours.index("K-mask"))]
        else:
            if any(c not in lookup for c in colours):
                raise SystemExit(f"{b.name}: a colour outside the lookup")
            to_lut = np.array([lookup.index(c) for c in colours], np.uint8)
            objs = [s14.image_rec(b.name, b.name, SECTION, b.method, "process", xywh,
                                  s16.lookup_array(LOOKUP), np.ascontiguousarray(to_lut[dots_idx]), "band")]
        rec = {"band": k, "name": b.name, "section": SECTION, "matching": s14.MATCHING[SECTION],
               "method": b.method, "neutral": "process" if b.method else None, **s16.rect_mm(*xywh),
               "alphabet": b.alphabet, "states": list(alpha),
               "palette": {s: list(COLOURS[es[0]["grid"][0][0]][0]) for s, es in cat.items()
                           if len(es) == 1 and len({c for row in es[0]["grid"] for c in row}) == 1},
               "planes": {s: "".join(p for p in s14.PLANES_ORDER
                                     if any(p in COLOURS[c][1] for e in es for row in e["grid"] for c in row))
                          for s, es in cat.items()},
               "layout_catalogue": cat,
               "n_layouts": {s: len(es) for s, es in cat.items()},
               "layout_draw": bool((n_layouts > 1).any()),
               "lookup": ([{"index": i, "colour": c, "rgb": list(COLOURS[c][0])}
                           for i, c in enumerate(lookup)] if b.method else []),
               "lookup_name": LOOKUP if b.method else None, "variant": b.variant,
               "draw": "choice+layout" if (n_layouts > 1).any() else "choice",
               "cell_dots": cd, "cells_hw": [rows, cols], "seed": SEED_BASE + k, "gaps": [],
               "asks": b.asks, "images": [s16.object_entry(o) for o in objs]}
        bands.append(rec)
        objects += objs
    return fids, bands, objects, arrays


# ------------------------------------------------------------------------------------------------ emission

def emit_job(objects: list[dict]) -> tuple[bytes, list[dict]]:
    """Wrapper, header, S12's setpagedevice + prologue, every object in draw order, the tail (= S16's
    emit_job with S17's wrapper head and header)."""
    parts = [WRAPPER_HEAD, HEADER, s12.SETPAGEDEVICE, s12.prologue(), b"%%Page: 1 1\n"]
    records = []
    for o in objects:
        if o["kind"] == "imagemask":
            ops, data = s16.mask_lines(o)
            raw = s16.pack_bits_rows(o["bits"])
        else:
            ops = s14.image_ops(o)
            raw = o["raster"].tobytes()
            data = s12.a85_lines(raw)
        text = ("\n".join(ops) + "\n").encode()
        offset = sum(len(p) for p in parts) + len(text)
        parts += [text, data, b"grestore\n"]
        rec = {"image": o["name"], "kind": o["kind"], "band": o["band"], "section": o["section"],
               "matching": o["matching"], "method": o["method"], "neutral": o["neutral"], "tile": o["tile"],
               "xywh_dots": list(o["xywh"]), "operators": ops[1:], "data_offset": offset,
               "data_bytes_raw": len(raw), "raster_sha256": sha(raw)}
        if o["kind"] == "imagemask":
            rec |= {"data_filter": "ASCIIHexDecode", "data_bytes": len(data), "data_bytes_hex": len(data)}
        else:
            rec |= {"data_filter": "ASCII85Decode", "hival": len(o["palette"]) - 1, "data_bytes": len(data),
                    "data_bytes_ascii85": len(data)}
        records.append(rec)
    parts.append(TAIL)
    return b"".join(parts), records


def notes() -> list[str]:
    return [
        "WHY: S16 (041.5m): cmy8 with overlap cells built from single-toner dots is never screened and reads "
        "3.2 % at c3 (CMY cell the weak state, 85 %); its fixed layouts lay a 283 lpi 45-degree lattice. "
        "S17: can the layout's ORIENTATION and PHASE carry bits; is cmy7 (no CMY) the better row; do c2 "
        "dot-mixed cells read with COLUMN / ROW pairs instead of S12's diagonal pairs.",
        "ROUTE = S16's: S1 PJL wrapper without BITSPERPIXEL/RET, S16's header shape, setpagedevice, S12's "
        "bare-name prologue byte for byte, 8-bit Indexed DeviceRGB images in gsave, ASCII85, S16's four HP "
        "calls per image in S16's order (all ProcBlack, Smooth but U12 Detail), no ColorSmartColorMatching; "
        "U14 = one K imagemask in S16's put_bitmap block (no HP call), no image.",
        "LAYOUT: 14 data bands of 4392 x 438 dots (146 c3 / 219 c2 cell rows; windows 31x31 c3 / 46x46 c2 "
        "from the band's top-left, 4 rows x 47) at x 283, y 283 + 462 k, 24 white dots between, last end "
        "6727 (limit 6732); fiducials = S16's, drawn first; no strip, no bars.",
        "DRAWS: default_rng(54000 + k), k = band position U1 = 0 .. U14 = 13; states = "
        ".choice(len(alphabet), size=(rows, cols)) row-major; THEN, only for bands with a multi-candidate "
        "state (U3-U7), u = .random((rows, cols)) and layout = floor(u * n_candidates(state of the cell)), "
        "0 where n = 1. "
        "U14: alphabet (W, K), the same choice call, no layout draw.",
        "CATALOGUE ('layout_catalogue' per band): {state: [{id, orientation, phase, grid}]}, the list order "
        "= the layout index in layouts_<band>; grids are rows (top to bottom) of colour names ('colours' -> "
        "RGB, planes). Orientation '-' before '+', phase ascending. Solid states and W: one 'solid' entry.",
        "GEOMETRY in a 3x3 cell: r row 0..2 top to bottom, c col 0..2, d = c - r, a = r + c. A = first toner "
        "of the state name (C in CM, CY; M in MY), B = second; C -> C-solid, M -> M-solid, Y -> Y.",
        "X (c3): A on (r + c) even (5 dots), B on odd (4) = S16 DOTMIX3. CMY stripes: '-' phase p: (C, M, "
        "Y)[((r + c) + p) mod 3]; '+' phase p: (C, M, Y)[((c - r) mod 3 + p) mod 3]; '-' 0 = S16's.",
        "ORIENTED BAND (c3, 5:4): '+' 0: A on d in {0, 1}; '+' 1: A on d in {-1, 0}; '-' 0: A on a in {2, "
        "3}; '-' 1: A on a in {1, 2}; B on the other four dots, ONE of which is 4-isolated (no 4-neighbour "
        "in the cell is B), (r, c): " + ", ".join(
            f"'{lid[-2]}' {lid[-1]} {isolated_b(layout_grid(lid, 'CM', 3), SINGLE['M'])}"
            for lid in (B_P0, B_P1, B_M0, B_M1)) + ".",
        "c2: diag = A on (0,0),(1,1) (S12 DOTMIX2); col = A column 0; row = A row 0; c2 CMY (U10) = DOTMIX2 "
        "((C, M), (Y, C)): C 2, M 1, Y 1.",
        "LOOKUP: every image band W, C-solid (0,208,255), M-solid (240,0,192), Y (255,255,0) = S16 T11's, "
        "byte-identical; no toner overlap at any dot of the page (every dot one toner or none).",
        "PLANES (npz, per dot): 1 where that toner is laid; U14's K plane = the mask bits.",
        "RENDER: gs's default ICC renders 0 0 0 1 setcmykcolor as (35,31,32) on ppmraw, -dUseFastColor as "
        "(0,0,0); --verify compares both (identical but on the mask bits).",
        "gs knows none of the HP operators; its render shows the page, not what the engine does with them.",
    ] + [f"{b.name} ({b.variant}): {b.asks}" for b in BANDS]


def build() -> tuple[bytes, dict, bytes, list[dict], dict[str, np.ndarray], list[dict]]:
    """The job, the manifest (no verification, no generator line), npz bytes, objects, arrays, records."""
    fids, bands, objects, arrays = plan()
    job, records = emit_job(objects)
    nb = s14.npz_bytes(arrays)
    manifest = {
        "tag": TAG, "dpi": DPI, "page_dots": {"w": PAGE_W_DOTS, "h": PAGE_H_DOTS}, "bytes": len(job),
        "sha256": sha(job), "bands_npz": {"file": f"{TAG}-bands.npz", "sha256": sha(nb), "bytes": len(nb),
                                          "keys": sorted(arrays)},
        "planes_order": list(s14.PLANES_ORDER), "fiducials": fids, "bands": bands, "bars": [],
        "windows": s16.windows(bands),
        "colours": {k: {"rgb": list(v[0]), "planes": v[1]} for k, v in COLOURS.items()},
        "palette": {k: list(v[0]) for k, v in COLOURS.items()},
        "alphabets": {k: list(v) for k, v in ALPHABETS.items()},
        "lookups": {LOOKUP: list(s16.LOOKUPS[LOOKUP])},
        "variants": [b.variant for b in BANDS],
        "layout_rule": "states = default_rng(54000 + k).choice(len(alphabet), size=(rows, cols)); then, if "
                       "any state has n > 1 candidates, u = rng.random((rows, cols)), layout = "
                       "floor(u * n(state of the cell))",
        "ps_structure": {"wrapper_head": WRAPPER_HEAD.decode("latin1"), "header": HEADER.decode(),
                         "setpagedevice": s12.SETPAGEDEVICE.decode(), "prologue": s12.prologue().decode(),
                         "tail": TAIL.decode("latin1"),
                         "data_filter": "ASCII85Decode (images), ASCIIHexDecode (imagemasks)",
                         "a85_columns": s12.A85_COLUMNS, "hex_columns": s16.HEX_LINE_CHARS,
                         "pt_per_dot": s12.PT_PER_DOT, "images": records},
        "notes": notes(),
    }
    return job, manifest, nb, objects, arrays, records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="job path (.ps); manifest + npz beside it")
    for key, default in (("s16", "S16-ps-trigger.ps"), ("s15", "S15-ps-reset.ps"), ("s14", "S14-ps-scale.ps"),
                         ("s12", "S12-ps-mixture.ps"), ("s11", "S11-pclxl-mixture.manifest.json")):
        ap.add_argument(f"--{key}", type=Path, default=None, help=f"default: {default} beside --out")
    ap.add_argument("--verify", action="store_true", help="checks (1)-(10); exit 1 unless all pass")
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
        import ps_layouts_verify as lv
        paths = {k: getattr(args, k) or args.out.with_name(v) for k, v in (
            ("s16", "S16-ps-trigger.ps"), ("s15", "S15-ps-reset.ps"), ("s14", "S14-ps-scale.ps"),
            ("s12", "S12-ps-mixture.ps"), ("s11", "S11-pclxl-mixture.manifest.json"))}
        v = lv.verify(args.out, man_path, npz_path, job, manifest, nb, objects, arrays, records, build, paths)
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
