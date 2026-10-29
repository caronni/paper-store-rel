"""e041 S16 — the TRIGGER probe for the HP M281 on the production route (PostScript), on S15's footing.

THE QUESTION.  S14 + S15 (041.5i, 041.5k) measured the engine's screen switching per PAGE-FIXED column region
(boundaries at the page left and ~107 mm): a region starts unscreened and content turns screening on after a
content-dependent distance -- cmy8 (4 of 8 states are toner overlaps) ~8-10 mm, cmyk5 (1 of 5 is K)
~25-35 mm, cmy4 (single toners only) never over 186 mm; nothing resets it once on; white BEFORE the content
lengthens the run (~0.9 mm per mm).  Two readings fit: (a) the COLOUR COUNT of the image (4 colours never
screen, 5 and more do), (b) a running budget per region spent by overlap / K PIXELS and refilled by white.
S16 separates them, measures the budget law, asks whether an object OUTSIDE the image's palette counts, and
prints the first composite-cell alphabets (dot-mixed overlaps, amplitude levels).

BANDS (top to bottom = draw order, k = 0..13, all section A, c3 Smooth unless said, 4392 x 432 dots each =
144 c3 / 216 c2 cell rows = 4 window rows of 31 / 46 cells, 47 windows across; "cmy4-solidC" = states W,
C-solid (0,208,255), M-solid (240,0,192), Y; "budget" = reading (b) at ~5 overlap-or-K-cell-mm per region,
from S14/S15: cmy8 50 % x ~10 mm, cmyk5 20 % x ~25 mm):
  T1  cmy8-engine (S9's palette), ProcBlack -- the screen-behaviour control (= S15 R1, other seed)
  T2  cmy8-DOTMIX, ProcBlack: W, C, M, Y solid cells, CM / CY / MY / CMY as DOTMIX3 single-toner dot
      layouts; the image lookup = W, C-solid, M-solid, Y only (byte-identical to T11's) -- colour count
  T3  cmy4-solidC + an UNUSED fifth lookup entry red (255,0,0), hival 4 -- does the lookup size count?
  T4  cmy4-solidC + 0.5 % red (MY engine overlap) cells, ProcBlack -- budget: never
  T5  cmy4-solidC + 20 % red cells, ProcBlack -- the red twin of T8's 20 % K; budget: ~25 mm
  T6  cmy4-solidC + 0.5 % K cells, TonerBlack -- budget: never
  T7  cmy4-solidC + 10 % K cells, TonerBlack -- budget: ~50 mm, inside region 1
  T8  cmyk5-solidC (W, C-solid, M-solid, Y, K uniform = 20 % K), TonerBlack -- the one-image cmyk5 control
  T9  cmy4-solidC image under TonerBlack (its lookup holds no (0,0,0): TonerBlack changes nothing in the
      data) whose 20 % K cells are W in the image and painted by ONE K IMAGEMASK (src/holo/gen/ps.py
      put_bitmap idiom) over the band rectangle, drawn right after the image -- comparable to T8
      (TonerBlack, one object) and to T14 (TonerBlack, no K)
  T10 AMPLITUDE alphabet, ProcBlack: W + C/M/Y at 3 (middle dot column), 6 (left + middle), 9 (full) dots
  T11 cmy4-solidC, ProcBlack -- production control (= S15 R8)
  T12 cmy4-solidC c2 (2x2), Detail, ProcBlack -- production control at c2 (= S15 R9)
  T13 cmy8-engine, ProcBlack, as TWO images with nothing drawn between them: left x 283..1420 (cell columns
      0..378), right x 1891..4675 (536..1463); cell columns 379..535 (left edge at page x in [60, 80) mm)
      are W in the band's states and object-free on the page -- does object-free white refill the budget?
  T14 cmy4-solidC, TonerBlack, no K, one image, lookup byte-identical to T11's -- the K series' p = 0 under
      TonerBlack (041.5i named the TonerBlack image itself as a candidate trigger)
  strip (24 dots): bar A K imagemask 600x24 @ x 283 | bar B (0,0,0) TonerBlack image @ 1000 | bar C (0,0,0)
      ProcBlack image @ 1717 -- what the imagemask lays, toner K or process black.
  Bands at y 283 + 456 k (k = 0..13), the strip at 6667, last end 6691 (limit 6732), 24 white dots between.

ROUTE AND FOOTING = S15's (ps_reset.py, printed, page 3402): S1's PJL wrapper without BITSPERPIXEL / RET
(JOB NAME "E041-S16-PS-TRIGGER"), the DSC header shape, F's setpagedevice line, S12's bare-name prologue
byte for byte, 8-bit [/Indexed /DeviceRGB hival <lookup>] images in gsave/grestore, ASCII85, 0.12 pt per
dot, per image the HP calls behind `where` guards in S15's order, no ColorSmartColorMatching anywhere; the
five fiducials are S15's three fiducial images, drawn first.  ONE NEW CONSTRUCT: the K imagemask block of
src/holo/gen/ps.py put_bitmap (T9's overlay and bar A), behind a comment line, no HP call.

STATES: rng = numpy default_rng(53000 + k).  Plain alphabets (T1, T2, T8, T10-T14): rng.choice(len(alphabet),
size=(rows, cols)), row-major.  T3: rng.choice(4, ...).  T4-T7, T9: states = rng.choice(4, ...); extra =
rng.random((rows, cols)) < p; states[extra] = 4, in that order of rng calls.  T13: the block forced to W
after the draw, and no image covers it.

Outputs (beside --out): the job, <stem>.manifest.json in S15's schema (+ "colours", per band "cell_layouts",
"lookup", "variant", "extra_fraction", "overlay", "white_block_mm", "white_block_object_free", T13's "gaps"
entry with "object_free"; bars in S14's schema with "kind") and
<stem>-bands.npz (states_<band>, planes_<band> = dot-level C/M/Y/K truth over the whole band rectangle,
T13's object-free block included), fixed zip timestamps.
--verify runs checks (1)-(10) of ps_trigger_verify.py and exits 0 only on overall pass.

    PYTHONPATH=src:. env/bin/python \\
        experiments/041-m281-screen-routes/ps_trigger.py \\
        --out experiments/041-m281-screen-routes/build/S16-ps-trigger.ps --verify
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import ps_mixture as s12
import ps_reset as s15
import ps_scale as s14
from holo.gen.ps import pack_bits_rows
from pcl_planar import sha
from pclxl_mixture_arms import DOTMIX3
from pclxl_probe import DPI, mm

TAG = "S16-ps-trigger"
JOB_NAME = "E041-S16-PS-TRIGGER"
S15_SHA256 = "43c195288ab43e98387883ce9b5b1af6a66b08264ce9c27a9553c3094503206c"
PAGE_H_DOTS, PAGE_W_DOTS = s12.PAGE_HW_DOTS
WRAPPER_HEAD = s12.UEL + f'@PJL JOB NAME="{JOB_NAME}"\r\n@PJL ENTER LANGUAGE=POSTSCRIPT\r\n'.encode()
_S14_TITLE = b"%%Title: e041 S14 PostScript page-scale probe\n"
_S14_CREATOR = b"%%Creator: experiments/041-m281-screen-routes/ps_scale.py\n"
assert _S14_TITLE in s14.HEADER and _S14_CREATOR in s14.HEADER
HEADER = (s14.HEADER.replace(_S14_TITLE, b"%%Title: e041 S16 PostScript trigger probe\n")
          .replace(_S14_CREATOR, b"%%Creator: experiments/041-m281-screen-routes/ps_trigger.py\n"))
TAIL = s14.TAIL
SECTION = "A"
HEX_LINE_CHARS = 128                     # src/holo/gen/ps.py _HEX_LINE_CHARS
MASK_COLOUR_LINE = "0.000 0.000 0.000 1.000 setcmykcolor"
SEED_BASE = 53000
BAND_X_DOTS, BAND_W_DOTS = s14.BAND_X_DOTS, s14.BAND_W_DOTS
FIRST_Y_DOTS, GAP_DOTS, LAST_END_DOTS = s14.FIRST_Y_DOTS, s14.GAP_DOTS, s14.LAST_END_DOTS
BAND_H_DOTS, STRIP_H_DOTS = 432, 24
BAR_W_DOTS = 600
BAR_X_DOTS = {"A": 283, "B": 1000, "C": 1717}
WINDOW_CELLS = s14.WINDOW_CELLS

RGB = tuple[int, int, int]
Grid = tuple[tuple[str, ...], ...]
# colour name -> (device RGB sent, toner planes it is meant to lay).  K is (0,0,0) in a TonerBlack image, CMY
# (0,0,0) in a ProcBlack image, K-mask the imagemask's 0 0 0 1 setcmykcolor (gs's default ICC renders it
# (35,31,32) on an RGB device, -dUseFastColor (0,0,0)).
COLOURS: dict[str, tuple[RGB, str]] = {
    "W": (s14.PALETTE["W"], ""), "C-solid": (s15.PALETTE["C-solid"], "C"),
    "M-solid": (s14.PALETTE["M-solid"], "M"), "Y": (s14.PALETTE["Y"], "Y"), "K": (s14.PALETTE["K"], "K"),
    "MY": (s14.PALETTE["MY"], "MY"), "C": (s14.PALETTE["C"], "C"), "M-corner": (s14.PALETTE["M-corner"], "M"),
    "CM": (s14.PALETTE["CM"], "CM"), "CY": (s14.PALETTE["CY"], "CY"), "CMY": (s14.PALETTE["CMY"], "CMY"),
    "K-mask": ((0, 0, 0), "K")}
CMY4 = ("W", "C-solid", "M-solid", "Y")
ALPHABETS: dict[str, tuple[str, ...]] = {
    "cmy8-engine": s14.ALPHABETS["cmy8-engine"],
    "cmy8-dotmix": ("W", "C", "M", "Y", "CM", "CY", "MY", "CMY"),
    "cmy4-solidC": CMY4,
    "cmy4-solidC+red": CMY4 + ("MY",),
    "cmy4-solidC+K": CMY4 + ("K",),
    "cmyk5-solidC": CMY4 + ("K",),
    "cmy4-solidC+K-overlay": CMY4 + ("K",),
    "amplitude10": ("W", "C3", "C6", "C9", "M3", "M6", "M9", "Y3", "Y6", "Y9")}
LOOKUPS: dict[str, tuple[str, ...]] = {
    "cmy8-engine": s14.ALPHABETS["cmy8-engine"], "cmy4": CMY4, "cmy4+red": CMY4 + ("MY",),
    "cmy4+K": CMY4 + ("K",)}
SINGLE = {"C": "C-solid", "M": "M-solid", "Y": "Y"}
AMPLITUDE_COLUMNS = {3: (1,), 6: (0, 1), 9: (0, 1, 2)}


@dataclass(frozen=True)
class BandSpec:
    name: str
    variant: str
    alphabet: str
    lookup: str
    cell_dots: int
    method: str
    neutral: str
    draw: str                                    # "uniform" | "choice4" | "choice4+extra"
    asks: str
    extra_fraction: float | None = None
    overlay: bool = False
    white_block_mm: tuple[float, float] | None = None      # T13: these cell columns W and object-free


BANDS: tuple[BandSpec, ...] = (
    BandSpec("T1", "cmy8_control", "cmy8-engine", "cmy8-engine", 3, "smooth", "process", "uniform",
             "the screen-behaviour control (= S15 R1 / S14 A2, other seed): both readings predict screening "
             "after ~8-10 mm from the page left and again ~11 mm after ~107 mm."),
    BandSpec("T2", "cmy8_dotmix", "cmy8-dotmix", "cmy4", 3, "smooth", "process", "uniform",
             "colour count + capacity candidate: 8 states, 4 lookup colours, no toner-overlap pixel. (a) "
             "colour count: never screens; (b) overlap/K-pixel budget: never screens (no overlap pixel). "
             "Screening here refutes BOTH (a third trigger, e.g. local colour transitions); unscreened "
             "= 3 bits/cell at c3 if the dotmix states separate (S12 patch: 6-8 %)."),
    BandSpec("T3", "cmy4_unused_lookup_entry", "cmy4-solidC", "cmy4+red", 3, "smooth", "process", "choice4",
             "does the LOOKUP SIZE alone count: hival 4, red never used. (a) by lookup entries: screens like "
             "a 5-colour image (~25-35 mm); (a) by used colours and (b): never screens."),
    BandSpec("T4", "cmy4_red_0.5pct", "cmy4-solidC+red", "cmy4+red", 3, "smooth", "process", "choice4+extra",
             "budget law, overlap pixels: 0.5 % red (MY) cells. (a): screens like any 5-colour image "
             "(onset independent of the fraction); (b): drains ~100x slower than cmy8 (50 % overlap "
             "cells) -> never within a region.", extra_fraction=0.005),
    BandSpec("T5", "cmy4_red_20pct", "cmy4-solidC+red", "cmy4+red", 3, "smooth", "process",
             "choice4+extra",
             "budget law, overlap pixels: 20 % red (MY) cells, the red twin of T8's 20 % K. (a): screens "
             "like any 5-colour image (~25-35 mm, the same onset as T4); (b) at ~5 overlap-or-K-cell-mm per "
             "region (S14/S15: cmy8 50 % x ~10 mm, cmyk5 20 % x ~25 mm): onset ~25 mm, inside region 1 and "
             "again ~25 mm after ~107 mm; T5 = T8 if a red cell spends what a K cell spends.",
             extra_fraction=0.20),
    BandSpec("T6", "cmy4_K_0.5pct", "cmy4-solidC+K", "cmy4+K", 3, "smooth", "toner", "choice4+extra",
             "budget law, K pixels: 0.5 % K cells (TonerBlack). (a): screens like cmyk5 (~25-35 mm); "
             "(b): ~40x slower than cmyk5's 20 % -> never.", extra_fraction=0.005),
    BandSpec("T7", "cmy4_K_10pct", "cmy4-solidC+K", "cmy4+K", 3, "smooth", "toner", "choice4+extra",
             "budget law, K pixels: 10 % K cells (TonerBlack). (a): same as T6 (~25-35 mm); (b) at ~5 "
             "overlap-or-K-cell-mm per region: onset ~50 mm, inside region 1 (~95 mm), twice T8's distance; "
             "0.5 % (T4, T6) never.", extra_fraction=0.10),
    BandSpec("T8", "cmyk5_solidC", "cmyk5-solidC", "cmy4+K", 3, "smooth", "toner", "uniform",
             "the K series' top point (T14 0 %, T6 0.5 %, T7 10 %, T8 20 %) and the one-image cmyk5 control: "
             "both readings predict screening after ~25-35 mm (S14 A3 / S15 R6-R7, whose cyan was "
             "(0,255,255), here C-solid)."),
    BandSpec("T9", "cmy4_K_overlay_imagemask", "cmy4-solidC+K-overlay", "cmy4", 3, "smooth", "toner",
             "choice4+extra",
             "does an object OUTSIDE the image's palette count: T8's composed content as a 4-colour image "
             "under TonerBlack (as T8 and T14; no (0,0,0) in its lookup) + one K imagemask. (a) per image: "
             "unscreened, like T14; (b) per page region: screens like T8; (b) per object: unscreened.",
             extra_fraction=0.2, overlay=True),
    BandSpec("T10", "amplitude", "amplitude10", "cmy4", 3, "smooth", "process", "uniform",
             "composite cells, avenue C: one toner per cell at 3 / 6 / 9 dots, 4 lookup colours. Both "
             "readings: unscreened; the question is whether the levels separate."),
    BandSpec("T11", "cmy4_solidC", "cmy4-solidC", "cmy4", 3, "smooth", "process", "uniform",
             "production control (= S15 R8): unscreened under both readings."),
    BandSpec("T12", "cmy4_solidC_c2", "cmy4-solidC", "cmy4", 2, "detail", "process", "uniform",
             "production control at c2 Detail (= S15 R9): unscreened under both readings."),
    BandSpec("T13", "cmy8_white_block_60_80mm", "cmy8-engine", "cmy8-engine", 3, "smooth", "process",
             "uniform",
             "does white AFTER the switch refill the budget: cmy8 as two images with a ~20 mm OBJECT-FREE "
             "block between them at 60-80 mm (S15 R5's white credit was object-free page area; S15 R2: "
             "object edges do not matter). (b) with refill: unscreened for a while after 80 mm (~0.9 mm per "
             "mm of white, then a ~10 mm ramp); (a), or a latch: screened right after 80 mm (S15: gaps up "
             "to 1 mm inside an image changed nothing).", white_block_mm=(60.0, 80.0)),
    BandSpec("T14", "cmy4_solidC_tonerblack", "cmy4-solidC", "cmy4", 3, "smooth", "toner", "uniform",
             "the K series' p = 0 under TonerBlack: T11's content and lookup with the neutral axis "
             "TonerBlack (041.5i named the TonerBlack image itself as a candidate trigger). (a) and (b): "
             "unscreened; screened = the TonerBlack call alone is a trigger, and T6-T9 read against it."),
)


# ------------------------------------------------------------------------------------------------ cells

def solid(colour: str, cd: int) -> Grid:
    return tuple(tuple([colour] * cd) for _ in range(cd))


def layout_of(alphabet: str, state: str, cd: int) -> Grid:
    """The cd x cd grid of colour names one state paints."""
    if alphabet == "cmy8-dotmix":
        if len(state) > 1:
            if cd != 3:
                raise SystemExit("dotmix layouts are c3 (DOTMIX3)")
            return tuple(tuple(SINGLE[c] for c in row) for row in DOTMIX3[state])
        return solid(SINGLE.get(state, state), cd)
    if alphabet == "amplitude10":
        if state == "W":
            return solid("W", cd)
        if cd != 3:
            raise SystemExit("amplitude layouts are c3")
        cols = AMPLITUDE_COLUMNS[int(state[1:])]
        return tuple(tuple(SINGLE[state[0]] if c in cols else "W" for c in range(3)) for _ in range(3))
    if alphabet == "cmy4-solidC+K-overlay" and state == "K":
        return solid("K-mask", cd)
    if state not in COLOURS:
        raise SystemExit(f"{alphabet}: state {state} is no colour")
    return solid(state, cd)


def band_colours(layouts: dict[str, Grid]) -> list[str]:
    """Colour names used by a band's layouts, W first, then in COLOURS order."""
    used = {c for g in layouts.values() for row in g for c in row}
    return [c for c in COLOURS if c in used]


def plane_table(colours: list[str]) -> np.ndarray:
    return np.array([[int(p in COLOURS[c][1]) for p in s14.PLANES_ORDER] for c in colours], np.uint8)


def dot_colours(states: np.ndarray, layouts: dict[str, Grid], alpha: tuple[str, ...],
                colours: list[str]) -> np.ndarray:
    """(rows * cd, cols * cd) uint8 index into `colours`: every cell painted through its state's layout."""
    tiles = np.array([[[colours.index(c) for c in row] for row in layouts[s]] for s in alpha], np.uint8)
    rows, cols = states.shape
    cd = tiles.shape[1]
    return np.ascontiguousarray(tiles[states].transpose(0, 2, 1, 3).reshape(rows * cd, cols * cd))


def white_block_columns(b: BandSpec, cols: int) -> list[int]:
    """Cell columns whose LEFT edge lies at page x in [lo, hi) mm."""
    if b.white_block_mm is None:
        return []
    lo, hi = b.white_block_mm
    return [c for c in range(cols) if lo <= (BAND_X_DOTS + c * b.cell_dots) * 25.4 / DPI < hi]


def draw_states(b: BandSpec, k: int, rows: int, cols: int) -> np.ndarray:
    rng = np.random.default_rng(SEED_BASE + k)
    if b.draw == "uniform":
        st = rng.choice(len(ALPHABETS[b.alphabet]), size=(rows, cols))
    elif b.draw == "choice4":
        st = rng.choice(4, size=(rows, cols))
    elif b.draw == "choice4+extra":
        assert b.extra_fraction is not None
        st = rng.choice(4, size=(rows, cols))
        extra = rng.random((rows, cols)) < b.extra_fraction
        st[extra] = 4
    else:
        raise SystemExit(f"{b.name}: draw {b.draw}")
    st = st.astype(np.uint8)
    block = white_block_columns(b, cols)
    if block:
        st[:, block[0]:block[-1] + 1] = ALPHABETS[b.alphabet].index("W")
    return st


def block_images(b: BandSpec, y: int, block: list[int], raster: np.ndarray, w_index: int) -> list[dict]:
    """T13: the band raster as two images, left and right of the white block, nothing drawn in between;
    each image edge on the block's cell edge."""
    cd = b.cell_dots
    if block != list(range(block[0], block[-1] + 1)) or not 0 < block[0] <= block[-1] < BAND_W_DOTS // cd - 1:
        raise SystemExit(f"{b.name}: the white block must be one inner run of cell columns")
    lo_dots, hi_dots = block[0] * cd, (block[-1] + 1) * cd
    if not (raster[:, lo_dots:hi_dots] == w_index).all():
        raise SystemExit(f"{b.name}: the white block is not W")
    return [s14.image_rec(f"{b.name}-{side}", b.name, SECTION, b.method, b.neutral,
                          (BAND_X_DOTS + x0, y, x1 - x0, BAND_H_DOTS), lookup_array(b.lookup),
                          np.ascontiguousarray(raster[:, x0:x1]), "band")
            for side, x0, x1 in (("left", 0, lo_dots), ("right", hi_dots, BAND_W_DOTS))]


# ------------------------------------------------------------------------------------------------ plan

def band_rows() -> list[tuple[int, BandSpec, int]]:
    """(band index, spec, y_dots), top to bottom = draw order, 24 white dots between bands."""
    return [(k, b, FIRST_Y_DOTS + k * (BAND_H_DOTS + GAP_DOTS)) for k, b in enumerate(BANDS)]


def strip_y_dots() -> int:
    return FIRST_Y_DOTS + len(BANDS) * (BAND_H_DOTS + GAP_DOTS)


def rect_mm(x: int, y: int, w: int, h: int) -> dict:
    return {"x_dots": x, "y_dots": y, "w_dots": w, "h_dots": h, "x_mm": mm(x), "y_mm": mm(y), "w_mm": mm(w),
            "h_mm": mm(h)}


def mask_rec(name: str, band: str, xywh: tuple[int, int, int, int], bits: np.ndarray) -> dict:
    return {"name": name, "band": band, "section": SECTION, "matching": s14.MATCHING[SECTION], "method": None,
            "neutral": None, "xywh": xywh, "bits": np.ascontiguousarray(bits.astype(np.uint8)),
            "kind": "imagemask", "tile": None}


def object_entry(o: dict) -> dict:
    return {"image": o["name"], "kind": o["kind"], "x_dots": o["xywh"][0], "y_dots": o["xywh"][1],
            "w_dots": o["xywh"][2], "h_dots": o["xywh"][3], "neutral": o["neutral"], "tile": o["tile"]}


def lookup_array(name: str) -> np.ndarray:
    return np.array([COLOURS[c][0] for c in LOOKUPS[name]], np.uint8)


def plan() -> tuple[list[dict], list[dict], list[dict], list[dict], dict[str, np.ndarray]]:
    """Fiducials, bands (the strip last), bars, objects (draw order) and the npz arrays."""
    fids, objects = s14.fiducial_plan()
    bands, arrays = [], {}
    for k, b, y in band_rows():
        alpha = ALPHABETS[b.alphabet]
        cd = b.cell_dots
        rows, cols = BAND_H_DOTS // cd, BAND_W_DOTS // cd
        if rows * cd != BAND_H_DOTS or cols * cd != BAND_W_DOTS:
            raise SystemExit(f"{b.name}: not whole c{cd} cells")
        states = draw_states(b, k, rows, cols)
        layouts = {s: layout_of(b.alphabet, s, cd) for s in alpha}
        colours = band_colours(layouts)
        dots_idx = dot_colours(states, layouts, alpha, colours)
        arrays[f"states_{b.name}"] = states
        arrays[f"planes_{b.name}"] = np.ascontiguousarray(np.moveaxis(plane_table(colours)[dots_idx], 2, 0))
        lookup = LOOKUPS[b.lookup]
        to_lut = np.array([lookup.index(c) if c in lookup else 0 for c in colours], np.uint8)
        if any(c not in lookup and c != "K-mask" for c in colours):
            raise SystemExit(f"{b.name}: a colour outside the lookup that no mask paints")
        xywh = (BAND_X_DOTS, y, BAND_W_DOTS, BAND_H_DOTS)
        raster = np.ascontiguousarray(to_lut[dots_idx])
        block = white_block_columns(b, cols)
        if block:
            objs = block_images(b, y, block, raster, LOOKUPS[b.lookup].index("W"))
        else:
            objs = [s14.image_rec(b.name, b.name, SECTION, b.method, b.neutral, xywh, lookup_array(b.lookup),
                                  raster, "band")]
        if b.overlay:
            objs.append(mask_rec(f"{b.name}-mask", b.name, xywh, dots_idx == colours.index("K-mask")))
        gaps = ([{"cell_col_start": block[0], "cell_cols": len(block), "x_dots": BAND_X_DOTS + block[0] * cd,
                  "w_dots": len(block) * cd, "x_mm": mm(BAND_X_DOTS + block[0] * cd),
                  "x_end_mm": mm(BAND_X_DOTS + (block[-1] + 1) * cd), "w_mm": mm(len(block) * cd),
                  "object_free": True}] if block else [])
        rec = {"band": k, "name": b.name, "section": SECTION, "matching": s14.MATCHING[SECTION],
               "method": b.method, "neutral": b.neutral, **rect_mm(*xywh), "alphabet": b.alphabet,
               "states": list(alpha),
               "palette": {s: list(COLOURS[g[0][0]][0]) for s, g in layouts.items()
                           if len({c for row in g for c in row}) == 1},
               "planes": {s: "".join(p for p in s14.PLANES_ORDER
                                     if any(p in COLOURS[c][1] for row in g for c in row))
                          for s, g in layouts.items()},
               "cell_layouts": {s: [list(row) for row in g] for s, g in layouts.items()},
               "lookup": [{"index": i, "colour": c, "rgb": list(COLOURS[c][0])}
                          for i, c in enumerate(lookup)],
               "lookup_name": b.lookup, "variant": b.variant, "draw": b.draw,
               "extra_fraction": b.extra_fraction,
               "overlay": {"kind": "imagemask", "fraction": b.extra_fraction, "state": "K",
                           "image_index_on_K_cells": 0, "object": f"{b.name}-mask"} if b.overlay else None,
               "white_block_mm": list(b.white_block_mm) if b.white_block_mm else None,
               "white_block_object_free": True if block else None,
               "cell_dots": cd, "cells_hw": [rows, cols], "seed": SEED_BASE + k, "gaps": gaps,
               "asks": b.asks, "images": [object_entry(o) for o in objs]}
        bands.append(rec)
        objects += objs
    sy = strip_y_dots()
    bars, strip_objs = [], []
    for key, colour, neutral, kind in (("A", "K-mask", "none", "imagemask"), ("B", "K", "toner", "image"),
                                       ("C", "CMY", "process", "image")):
        xywh = (BAR_X_DOTS[key], sy, BAR_W_DOTS, STRIP_H_DOTS)
        name = f"strip-bar{key}"
        if kind == "imagemask":
            o = mask_rec(name, "strip", xywh, np.ones((STRIP_H_DOTS, BAR_W_DOTS), np.uint8))
        else:
            o = s14.image_rec(name, "strip", SECTION, "smooth", neutral, xywh,
                              np.array([COLOURS["W"][0], COLOURS[colour][0]], np.uint8),
                              np.ones((STRIP_H_DOTS, BAR_W_DOTS), np.uint8), "bar")
        strip_objs.append(o)
        bars.append({"id": name, "band": "strip", "colour": colour, "rgb": list(COLOURS[colour][0]),
                     "section": SECTION, "matching": s14.MATCHING[SECTION], "neutral": neutral, "kind": kind,
                     "image": name, **rect_mm(*xywh)})
    bands.append({"band": len(BANDS), "name": "strip", "section": SECTION, "matching": s14.MATCHING[SECTION],
                  "method": "smooth", "neutral": "mixed",
                  **rect_mm(BAND_X_DOTS, sy, BAND_W_DOTS, STRIP_H_DOTS),
                  "alphabet": None, "palette": {b["colour"]: b["rgb"] for b in bars}, "cell_dots": None,
                  "seed": None, "gaps": [], "images": [object_entry(o) for o in strip_objs]})
    objects += strip_objs
    return fids, bands, bars, objects, arrays


def windows(bands: list[dict]) -> list[dict]:
    """Each data band tiled into whole windows of 31x31 c3 / 46x46 c2 cells from its top-left (S15's)."""
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
                out.append({"id": f"{b['name']}-w{iy:02d}-{ix:02d}", "band": b["name"], "x_dots": x,
                            "y_dots": y, "w_dots": wc * cd, "h_dots": wc * cd, "x_mm": mm(x), "y_mm": mm(y),
                            "cells": wc, "cell_dots": cd, "cell_yx": [iy * wc, ix * wc],
                            "alphabet": b["alphabet"], "palette": b["palette"], "method": b["method"],
                            "neutral": b["neutral"], "matching": b["matching"], "section": b["section"],
                            "tile": None})
    return out


# ------------------------------------------------------------------------------------------------ emission

def mask_lines(o: dict) -> tuple[list[str], bytes]:
    """The holo put_bitmap block (src/holo/gen/ps.py) behind one comment line: (lines up to and including
    the imagemask line, the data = hex rows + '>' line).  Point arithmetic as put_bitmap's."""
    x, y, w, h = o["xywh"]
    pt = 72.0 / DPI
    x_pt, y_pt = x * pt, PAGE_H_DOTS * pt - (y + h) * pt
    head = f"% {o['name']}: imagemask of {o['band']}, K 0 0 0 1, the holo put_bitmap idiom, no HP call"
    lines = [head, "gsave", f"{x_pt:.6f} {y_pt:.6f} translate", f"{w * pt:.6f} {h * pt:.6f} scale",
             MASK_COLOUR_LINE, f"{w} {h} true [{w} 0 0 -{h} 0 {h}]",
             "currentfile /ASCIIHexDecode filter imagemask"]
    hx = pack_bits_rows(o["bits"]).hex()
    rows = [hx[i:i + HEX_LINE_CHARS] for i in range(0, len(hx), HEX_LINE_CHARS)]
    return lines, ("\n".join(rows) + "\n>\n").encode()


def emit_job(objects: list[dict]) -> tuple[bytes, list[dict]]:
    """Wrapper, header, S12's setpagedevice + prologue, every object in draw order, the tail."""
    parts = [WRAPPER_HEAD, HEADER, s12.SETPAGEDEVICE, s12.prologue(), b"%%Page: 1 1\n"]
    records = []
    for o in objects:
        if o["kind"] == "imagemask":
            ops, data = mask_lines(o)
            raw = pack_bits_rows(o["bits"])
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
        "WHY: S14/S15 (041.5i, 041.5k): the screen switches per page-fixed column region (page left, ~107 "
        "mm); cmy8 screens after ~8-10 mm, cmyk5 after ~25-35 mm, cmy4 never; nothing resets it once on; "
        "white before the content lengthens the run ~0.9 mm per mm. Readings: (a) colour count of the image, "
        "(b) a per-region budget spent by overlap/K pixels and refilled by white. S16 separates them.",
        "ROUTE = S15's: S1 PJL wrapper without BITSPERPIXEL/RET, F's setpagedevice, S12's bare-name prologue "
        "byte for byte, 8-bit Indexed DeviceRGB images in gsave, ASCII85, HP calls behind `where` guards in "
        "S15's section-A order, no ColorSmartColorMatching anywhere.",
        "ONE NEW CONSTRUCT: the K imagemask of src/holo/gen/ps.py put_bitmap (gsave / translate / scale / "
        "0 0 0 1 setcmykcolor / w h true [w 0 0 -h 0 h] / currentfile /ASCIIHexDecode filter imagemask / hex "
        "rows padded to bytes / > / grestore) behind one comment line: T9's overlay and bar A. No HP call in "
        "an imagemask block. Printed bit-faithful as K on this engine (e029) but never under this prologue.",
        "LAYOUT: 14 data bands of 4392 x 432 dots (144 c3 / 216 c2 cell rows = 4 window rows of 31 / 46 "
        "cells, 47 windows across) at y 283 + 456 k, then the 24-dot strip at 6667 (last end 6691, limit "
        "6732), 24 white dots between; draw order = top to bottom, T9's mask right after T9's image.",
        "SEEDS: default_rng(53000 + k), k = band position T1 = 0 .. T14 = 13. Plain alphabets (T1, T2, T8, "
        "T10-T14): .choice(len(alphabet), size=(rows, cols)). T3: .choice(4, ...) (the fifth lookup entry "
        "never drawn). T4-T7, T9: states = .choice(4, ...); extra = .random((rows, cols)) < p; "
        "states[extra] = 4, in that order of calls. T13: the white block forced after the draw.",
        "FRACTIONS (extra_fraction p): T4 0.005 red, T5 0.20 red (T8's twin), T6 0.005 K, T7 0.10 K, T9 0.20 "
        "K by imagemask; T8 0.20 K by the uniform 5-state draw, T14 0 (the K series under TonerBlack: T14, "
        "T6, T7, T8). Budget reading at ~5 overlap-or-K-cell-mm per region (S14/S15): onset ~25 mm at 20 %, "
        "~50 mm at 10 %, never at 0.5 %.",
        "CELLS: every band's 'cell_layouts' gives each state's cd x cd grid of colour names (manifest "
        "'colours' -> RGB and planes). T2 dotmix overlaps = pclxl_mixture_arms.DOTMIX3 with C = C-solid, "
        "M = M-solid: CM/CY/MY (r+c) even = first ink (5 dots), odd = second (4 dots); CMY by (r+c) mod 3. "
        "T10 amplitude: 3 = the middle dot column, 6 = left and middle columns, 9 = the full cell.",
        "LOOKUPS ('lookup' per band, index order): cmy8-engine = S15 R1's; cmy4 = W, C-solid, M-solid, Y (= "
        "S15 R8's; T2, T9, T10, T11, T12, T14 byte-identical); cmy4+red = cmy4 + (255,0,0) (T3 unused, T4/T5 "
        "used); cmy4+K = cmy4 + (0,0,0) (T6, T7, T8 under TonerBlack).",
        "T8's cyan is C-solid (0,208,255); S14 A3's cmyk5 used C (0,255,255): not the same palette.",
        "NEUTRALS: TonerBlack on T6, T7, T8, T9, T14 and bar B; ProcBlack on every other image. T9's image "
        "and T14's carry no (0,0,0), so TonerBlack changes nothing in their data, only the HP call.",
        "T9: the K cells are index 0 (W) in the 4-colour TonerBlack image and 1 in ONE imagemask over the "
        "band rectangle drawn right after it; planes_T9's K plane = the mask bits.",
        "T13: cell columns 379..535 (left edge at page x in [60, 80) mm; x 1420..1891 dots = 60.11..80.05 "
        "mm) forced to W in states_T13, and OBJECT-FREE on the page: the band is two images, 'T13-left' x "
        "283..1420 (cell columns 0..378) and 'T13-right' x 1891..4675 (536..1463), nothing drawn between "
        "(the band's 'gaps' entry with object_free, 'white_block_mm', 'white_block_object_free'). S15 R5's "
        "white credit was object-free page area; S15 R2 showed object edges do not matter.",
        "PLANES (npz, per dot): 1 where that toner is laid: C-solid / C -> C; M-solid / M-corner -> M; red "
        "(MY) -> M and Y; CM, CY likewise; CMY (0,0,0) under ProcBlack -> C, M, Y; K (0,0,0) under "
        "TonerBlack -> K; K-mask -> K. Dotmix and amplitude cells are partial per plane.",
        "STRIP (24 dots): bar A = K imagemask 600x24 (holo idiom), bar B = (0,0,0) TonerBlack image, bar C "
        "= (0,0,0) ProcBlack image, all Smooth: what the imagemask lays, by colour and lattice.",
        "RENDER: gs's default ICC renders 0 0 0 1 setcmykcolor as (35,31,32) on ppmraw; -dUseFastColor as "
        "(0,0,0). --verify compares both (identical but on the mask bits).",
        "gs knows none of the HP operators; its render shows the page, not what the engine does with them.",
    ] + [f"{b.name} ({b.variant}): {b.asks}" for b in BANDS]


def build() -> tuple[bytes, dict, bytes, list[dict], dict[str, np.ndarray], list[dict]]:
    """The job, the manifest (no verification, no generator line), npz bytes, objects, arrays, records."""
    fids, bands, bars, objects, arrays = plan()
    job, records = emit_job(objects)
    nb = s14.npz_bytes(arrays)
    manifest = {
        "tag": TAG, "dpi": DPI, "page_dots": {"w": PAGE_W_DOTS, "h": PAGE_H_DOTS}, "bytes": len(job),
        "sha256": sha(job), "bands_npz": {"file": f"{TAG}-bands.npz", "sha256": sha(nb), "bytes": len(nb),
                                          "keys": sorted(arrays)},
        "planes_order": list(s14.PLANES_ORDER), "fiducials": fids, "bands": bands, "bars": bars,
        "windows": windows(bands),
        "colours": {k: {"rgb": list(v[0]), "planes": v[1]} for k, v in COLOURS.items()},
        "palette": {k: list(v[0]) for k, v in COLOURS.items()},
        "alphabets": {k: list(v) for k, v in ALPHABETS.items()},
        "lookups": {k: list(v) for k, v in LOOKUPS.items()},
        "variants": [b.variant for b in BANDS],
        "ps_structure": {"wrapper_head": WRAPPER_HEAD.decode("latin1"), "header": HEADER.decode(),
                         "setpagedevice": s12.SETPAGEDEVICE.decode(), "prologue": s12.prologue().decode(),
                         "tail": TAIL.decode("latin1"),
                         "data_filter": "ASCII85Decode (images), ASCIIHexDecode (imagemasks)",
                         "a85_columns": s12.A85_COLUMNS, "hex_columns": HEX_LINE_CHARS,
                         "pt_per_dot": s12.PT_PER_DOT, "images": records},
        "notes": notes(),
    }
    return job, manifest, nb, objects, arrays, records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="job path (.ps); manifest + npz beside it")
    ap.add_argument("--s15", type=Path, default=None, help="S15 job (default: S15-ps-reset.ps beside --out)")
    ap.add_argument("--s14", type=Path, default=None, help="S14 job (default: S14-ps-scale.ps beside --out)")
    ap.add_argument("--s12", type=Path, default=None,
                    help="S12 job (default: S12-ps-mixture.ps beside --out)")
    ap.add_argument("--s11", type=Path, default=None,
                    help="S11 manifest for the S12 rebuild (default: S11-pclxl-mixture.manifest.json beside "
                    "--out)")
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
        import ps_trigger_verify as tv
        paths = {k: getattr(args, k) or args.out.with_name(v) for k, v in (
            ("s15", "S15-ps-reset.ps"), ("s14", "S14-ps-scale.ps"), ("s12", "S12-ps-mixture.ps"),
            ("s11", "S11-pclxl-mixture.manifest.json"))}
        v = tv.verify(args.out, man_path, npz_path, job, manifest, nb, objects, arrays, records, build, paths)
        ok = bool(v["pass"])
        man_path.write_text(json.dumps(manifest | gen | {"verification": v}, indent=1) + "\n")
        print(json.dumps({k: (x if k != "8_novelty" else {kk: vv for kk, vv in x.items()
                                                          if kk not in ("S16", "S15", "S14")})
                          for k, x in v.items()}, indent=1))
    print(f"{args.out}: {len(job)} B sha {manifest['sha256']}")
    print(f"{man_path}\n{npz_path}: {len(nb)} B sha {manifest['bands_npz']['sha256']}")
    if not ok:
        print("VERIFY FAILED", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
