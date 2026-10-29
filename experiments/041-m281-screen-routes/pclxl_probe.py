"""e041 S10p — PCL XL RGB probe sheet: which device RGB lays each toner state down unscreened on the M281.

What is printed: ONE A4 page of 1,171 small patches.  A patch is one PCL XL eRGB image -- all but the 24
encoding riders e1Bit indexed through a 2-entry palette [white, the patch RGB] -- of a 93 x 93-dot pattern
square (31 x 31 cells of 3 x 3 dots, seeded pattern, 1 = ink) with a 93 x 24-dot solid bar of ink directly below
it, in the SAME image (93 x 117 dots, one ReadImage).  The RGB values sweep around every state corner (C/M/Y
singles: own 0, both foreign channels over 255..128 step 16, plus own 16/32/48; CM/CY/MY: the free channel
255..128 x both zero channels 0/16/32; CMY 0/16/32; W), each under three halftone methods: "default" (no
SetHalftoneMethod has been executed when these patches are drawn), "highlpi" (S9's eHighLPI for
text/vector/raster objects) and "matrix1x1" (S9b's downloaded 1 x 1 threshold 0x80).  Extras: the eight corners
four more times per method (position replicates), and default-method riders: the corners as vector rectangles;
black, (16,16,16) and the corners under SetNeutralAxis eTonerBlack; a treatment witness (kind "treatdefault":
the corners, the single-toner mids (0,192,192), (192,0,192), (192,192,0) and the overlap mids (0,0,192),
(0,192,0), (192,0,0), drawn WITHOUT SetColorTreatment as the FIRST objects on the page, before the page head, so
the treatment in force is the BeginPage default -- eScreenMatch, X20 p. 47, X21 p. 24, X30 p. 5 -- to test
whether eNoTreatment does anything at all); the ENCODING riders (kinds "enc4bit", "encdirect8", "encdirect1",
the eight corners each, drawn in the default group among the default patterns): the same patch as eIndexedPixel
e4Bit through S9's 16-entry corner palette (S9's own encoding), as eDirectPixel e8Bit (three bytes per pixel)
and as eDirectPixel e1Bit (three bits per pixel), so a corner that prints differently here than on S9 is not
ambiguous between the RGB value, the pixel encoding and the object size; and, LAST on the page, the corners in
eSRGB.  Five solid black fiducials outside the slot area.  Every position, value, method, encoding and pattern
is in the manifest (the e041 S10 manifest contract; per-patch "encoding" = indexed1 | indexed4 | direct8 |
direct1).
Control state: after EVERY SetColorSpace the object carries S9's whole control block in S9's order --
SetColorTreatment eNoTreatment, SetAdaptiveHalftoning eDisable, SetColorTrapping eDisable, SetNeutralAxis
eProcessBlack (eTonerBlack in the tonerblack group), then SetHalftoneMethod in the highlpi and matrix1x1
groups only -- the postconditions name the current colour space (X21 p. 22; X30 p. 10-11) and the current
object (X30 p. 9), so whatever the firmware reads into them, every object has the block right behind its own
SetColorSpace.  The settings themselves are graphics state (X21 p. 24, X30 p. 5): they persist until set
again or until PopGS restores them, and SetColorSpace resets only pen and brush (X20 p. 85).  So a treatment
once set stays in force: the treatment witness omits SetColorTreatment AND is emitted first, directly after
BeginPage (X20 p. 47: the graphics state is initialised there), before the page head and every other object,
when no SetColorTreatment and no SetHalftoneMethod has run on the page.  The eSRGB riders omit
SetColorTreatment too (its precondition is an eRGB colour space, X21 p. 22); they inherit eNoTreatment from
the last vector rider through the three PopGS.  The eSRGB group (ColorSpace 6, in no spec) is the last thing
on the page, so an engine error there costs only its 8 patches.
Why: S9 printed RGB cyan (0,255,255) nearly bit-faithfully but magenta and yellow partial and screened, and
S9b's dither matrix was ignored.  If the engine's device-RGB -> toner table gives M and Y their full toner
at some RGB other than the corner, the readout instrument finds it here: per target state, the value whose
cells print with the highest own-channel contrast, least foreign-channel contamination and least screen.

Job skeleton = S9's (pclxl_bilevel.py; its encoders, tables, parser and gpcl6 render are imported, and the
operator / attribute / enumeration tables are extended in place below with the names this sheet adds).
Sources (pages = the documents' printed footers): X20 = PCL XL Feature Reference Protocol Class 2.0 rev p2.2,
X21 = Class 2.1 Supplement rev 1.0, X30 = Class 3.0 Supplement rev 0.90.

--verify: an independent decode of the job's own stream (operator sequence; every object's cursor, palette,
colour space, PushGS depth and FULL control state in force -- treatment, adaptive halftoning, trapping,
neutral axis, halftone method, modelled to the spec: graphics state initialised at BeginPage, saved and
restored only by PushGS/PopGS, never cleared by SetColorSpace, which resets pen and brush to black -- plus
the exact control sequence between its own SetColorSpace and the object, all against what the manifest's
method/kind demands; by stream position: no SetColorTreatment and no SetHalftoneMethod before any treatment
witness, no SetHalftoneMethod before any other default-method object but the eSRGB riders, every
SetHalftoneMethod and eTonerBlack inside its own wrapped group; one SetColorSpace per object; the groups
contiguous, the treatment witness first and eSRGB last before EndPage; image data -- decoded under each
object's own ColorMapping / ColorDepth by the verifier's own unpacker, rows padded to four bytes (X20 p. 179),
indexed samples through the stream's palette -- and rectangles back to patterns; mutated jobs that must each
fail the stream checks), then a gpcl6 ppmraw render at 600 dpi compared to
the manifest dot for dot (every pattern, bar, 1-dot white ring, fiducial; nothing else inked), the solid bars'
first inked dot against the manifest positions, and a byte-identical rebuild.

    PYTHONPATH=src:. env/bin/python experiments/041-m281-screen-routes/pclxl_probe.py \\
        --out experiments/041-m281-screen-routes/build/S10p-pclxl-rgb-probe.pclxl --verify
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import tempfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np

import pclxl_bilevel as xl
from pcl_planar import UEL, sha, stub_font
from pclxl_bilevel import (ATTR, ATTR_UBYTE, E, EMBED, OP, SINT16_XY, UBYTE, UBYTE_ARRAY, controls, op, parse,
                           stream_body, u16, ub, xy)

# Names this sheet adds to S9's tables (in place, so S9's encoders and parser know them; S9's own bytes do not
# depend on them).  Operator tags X20 p. 213-214: PopGS 0x60, PushGS 0x61, SetBrushSource 0x63, SetPenSource
# 0x79, Rectangle 0xa0.  Attribute ids X20 Appendix E p. 219: NullPen 5, RGBColor 11, BoundingBox 66.
# Enumerations: e1Bit 0 (X30 Appendix G p. 31), eTonerBlack 0 (X30 p. 31).  eSRGB is in NONE of X20/X21/X30
# (their ColorSpace enumeration lists eGray 1 and eRGB 2 only: X20 p. 85, X21 p. 38, X30 p. 32); 6 is the
# value gpcl6 10.08 accepts (it refuses 3, 4, 5 with IllegalAttributeValue and 7, 8 with
# IllegalAttributeDataType, measured 2026-10-05) = GhostPCL's eSRGB.  Whether the M281 accepts it is a
# printer question.
_ADD_OP = {"PopGS": 0x60, "PushGS": 0x61, "SetBrushSource": 0x63, "SetPenSource": 0x79, "Rectangle": 0xA0}
_ADD_ATTR = {"NullPen": 5, "RGBColor": 11, "BoundingBox": 66}
assert not set(_ADD_OP.values()) & set(OP.values()) and not set(_ADD_ATTR.values()) & set(ATTR.values())
OP.update(_ADD_OP)
ATTR.update(_ADD_ATTR)
E.update({"e1Bit": 0, "eTonerBlack": 0, "eSRGB": 6, "eDirectPixel": 0})  # eDirectPixel: X20 App. G p. 226
UINT16_BOX = 0xE1  # X20 Appendix B p. 216

TAG = "S10p-pclxl-rgb-probe"
JOB_NAME = "E041-S10P-PCLXL-RGB-PROBE"
DPI = 600
PAGE_MM = (210, 297)
CELL_DOTS, CELLS, SOLID_DOTS = 3, 31, 24
PATTERN_DOTS = CELL_DOTS * CELLS  # 93
PATCH_H_DOTS = PATTERN_DOTS + SOLID_DOTS  # 117: pattern square + solid bar, one image
METHODS = ("default", "highlpi", "matrix1x1")
FOREIGN = (255, 240, 224, 208, 192, 176, 160, 144, 128)  # foreign channels of a single-toner state
FREE = FOREIGN  # the free channel of an overlap state
CORNERS = ((255, 255, 255), (0, 255, 255), (255, 0, 255), (255, 255, 0),  # W C M Y
           (0, 0, 255), (0, 255, 0), (255, 0, 0), (0, 0, 0))  # CM CY MY CMY
TREAT_WITNESS = CORNERS + ((0, 192, 192), (192, 0, 192), (192, 192, 0),  # single-toner mids
                           (0, 0, 192), (0, 192, 0), (192, 0, 0))  # overlap mids
REPLICATES = 4
LAYOUT_SEED = 41
PATTERN_SEED_BASE = 41_000  # patch seed = base + id
SLOT_X_ZONES_MM = ((12.0, 98.0), (118.0, 198.0))
SLOT_Y_ZONE_MM = (12.0, 285.0)
SLOT_PITCH_MM = (5.5, 6.5)
FIDUCIALS_MM = (("F0", 8.0, 8.0, 3.0, 3.0), ("F1", 199.0, 8.0, 3.0, 3.0), ("F2", 8.0, 286.0, 3.0, 3.0),
                ("F3", 199.0, 286.0, 3.0, 3.0), ("F4", 8.0, 12.0, 3.0, 6.0))  # id, x, y, w, h (mm)
LOW = 64  # a channel below this is "~0" for the target label
# Pixel encodings: name -> (ColorMapping, ColorDepth, components per pixel, bits per component).  ColorDepth
# is bits per COMPONENT (X20 p. 177), so a direct eRGB pixel carries three; an indexed pixel one, its
# palette sized by the depth (X20 p. 85: 2**depth entries x 3).
ENCODING = {"indexed1": ("eIndexedPixel", "e1Bit", 1, 1), "indexed4": ("eIndexedPixel", "e4Bit", 1, 4),
            "direct8": ("eDirectPixel", "e8Bit", 3, 8), "direct1": ("eDirectPixel", "e1Bit", 3, 1)}
ENC_KINDS = {"enc4bit": "indexed4", "encdirect8": "direct8", "encdirect1": "direct1"}  # default-group riders


def dots(mm: float) -> int:
    return int(np.floor(mm * DPI / 25.4 + 0.5))


def mm(n_dots: int) -> float:
    return round(n_dots * 25.4 / DPI, 6)


def target(rgb: tuple[int, int, int]) -> str:
    return "".join(t for t, v in zip("CMY", rgb) if v < LOW) or "W"


def sweep() -> list[tuple[int, int, int]]:
    """The 337 swept values in the brief's order: C, M, Y singles; CM, CY, MY; CMY; W."""
    out: list[tuple[int, int, int]] = []
    for own in range(3):
        f1, f2 = (c for c in range(3) if c != own)
        for a in FOREIGN:
            for b in FOREIGN:
                v = [0, 0, 0]
                v[f1], v[f2] = a, b
                out.append(tuple(v))
        for level in (16, 32, 48):
            v = [255, 255, 255]
            v[own] = level
            out.append(tuple(v))
    for free in (2, 1, 0):  # CM: B free, CY: G free, MY: R free
        for f in FREE:
            for z in (0, 16, 32):
                v = [z, z, z]
                v[free] = f
                out.append(tuple(v))
    out += [(0, 0, 0), (16, 16, 16), (32, 32, 32), (255, 255, 255)]
    if len(set(out)) != len(out) or len(out) != 337:
        raise SystemExit(f"sweep: {len(out)} values, {len(set(out))} distinct; 337 distinct expected")
    return out


def pattern(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 2, size=(CELLS, CELLS), dtype=np.uint8)


def slot_grid() -> list[tuple[int, int]]:
    """(x_dots, y_dots) of every slot, row-major; a slot holds a whole 93 x 117-dot patch inside its zone."""
    xs = []
    for lo, hi in SLOT_X_ZONES_MM:
        n = int((hi - lo - PATTERN_DOTS * 25.4 / DPI) // SLOT_PITCH_MM[0]) + 1
        xs += [dots(lo + i * SLOT_PITCH_MM[0]) for i in range(n)]
    lo, hi = SLOT_Y_ZONE_MM
    ny = int((hi - lo - PATCH_H_DOTS * 25.4 / DPI) // SLOT_PITCH_MM[1]) + 1
    ys = [dots(lo + j * SLOT_PITCH_MM[1]) for j in range(ny)]
    for zlo, zhi in SLOT_X_ZONES_MM:
        inside = [x for x in xs if dots(zlo) <= x < dots(zhi)]
        if inside[-1] + PATTERN_DOTS > dots(zhi):
            raise SystemExit("slot column crosses its zone's right edge")
    if ys[-1] + PATCH_H_DOTS > dots(hi):
        raise SystemExit("slot row crosses the zone's bottom edge")
    return [(x, y) for y in ys for x in xs]


def plan() -> tuple[list[dict], list[dict], dict]:
    """Patches (sweep x methods, replicates, riders) placed by the seeded shuffle; fiducials; the layout."""
    specs: list[tuple[tuple[int, int, int], str, str]] = []
    for method in METHODS:
        specs += [(v, method, "pattern") for v in sweep()]
    replicates = [(c, method, "pattern") for method in METHODS for c in CORNERS for _ in range(REPLICATES)]
    riders = ([(c, "default", "vector") for c in CORNERS] + [(c, "default", "srgb") for c in CORNERS]
              + [(c, "default", "tonerblack") for c in ((0, 0, 0), (16, 16, 16)) + CORNERS]
              + [(c, "default", "treatdefault") for c in TREAT_WITNESS]  # appended: earlier ids keep slots
              + [(c, "default", k) for k in ENC_KINDS for c in CORNERS])  # round 4, appended likewise
    slots = slot_grid()
    dropped = 0
    while len(specs) + len(replicates) + len(riders) > len(slots) and replicates:
        replicates.pop()
        dropped += 1
    specs += replicates + riders
    if len(specs) > len(slots):
        raise SystemExit(f"{len(specs)} patches without replicates exceed {len(slots)} slots")
    order = np.random.default_rng(LAYOUT_SEED).permutation(len(slots))
    patches = []
    for pid, (rgb, method, kind) in enumerate(specs):
        x, y = slots[int(order[pid])]
        seed = PATTERN_SEED_BASE + pid
        pat = pattern(seed)
        patches.append({"id": pid, "x_mm": mm(x), "y_mm": mm(y), "rgb": list(rgb), "method": method,
                        "kind": kind, "target": target(rgb), "encoding": ENC_KINDS.get(kind, "indexed1"),
                        "seed": seed,
                        "pattern_sha256": sha(pat.tobytes()),
                        "_xy": (x, y), "_pattern": pat, "_slot": int(order[pid])})
    fids = [{"id": f, "x_mm": mm(dots(x)), "y_mm": mm(dots(y)), "w_mm": w, "h_mm": h, "rgb": [0, 0, 0],
             "_xywh": (dots(x), dots(y), dots(w), dots(h))} for f, x, y, w, h in FIDUCIALS_MM]
    xs = sorted({x for x, _ in slots})
    ys = sorted({y for _, y in slots})
    record = {"slots": len(slots), "used": len(patches), "empty": len(slots) - len(patches),
              "replicates_dropped": dropped, "columns_x_dots": xs, "rows_y_dots": ys,
              "empty_slots": sorted(set(range(len(slots))) - {p["_slot"] for p in patches})}
    return patches, fids, record


def row_bytes(width_dots: int, bits_per_pixel: int = 1) -> int:
    """Image row length: whole bytes rounded up to a multiple of four (X20 p. 179: "The length of each line of
    image data within the image block must be a multiple of four bytes unless the PadBytesMultiple parameter
    is specified"; no PadBytesMultiple is sent)."""
    return 4 * -(-width_dots * bits_per_pixel // 32)


def s9_index(rgb: list[int]) -> int:
    """The entry of S9's 16-entry palette (pclxl_bilevel.palette()) that holds the corner rgb."""
    hit = np.flatnonzero((xl.palette()[:8] == np.asarray(rgb)).all(1))
    if hit.size != 1:
        raise SystemExit(f"{rgb} is not an RGB corner of S9's palette")
    return int(hit[0])


def samples(mask: np.ndarray, rgb: list[int], encoding: str) -> np.ndarray:
    """(h, w, components) source samples of a 0/1 ink mask in one encoding: indexed1 index 1 = ink through
    [white, rgb]; indexed4 S9's palette index of the corner, blank = index 0 (white); direct8 the RGB bytes,
    blank 255,255,255; direct1 one bit per component (corner channel 255 -> 1), blank 1,1,1."""
    ink = mask.astype(bool)[..., None]
    if encoding == "indexed1":
        return ink.astype(np.uint8)
    if encoding == "indexed4":
        return np.where(ink, s9_index(rgb), s9_index([255, 255, 255])).astype(np.uint8)
    if encoding == "direct8":
        return np.where(ink, np.asarray(rgb, np.uint8), np.uint8(255))
    if encoding == "direct1" and set(rgb) <= {0, 255}:
        return np.where(ink, np.asarray(rgb, np.uint8) // 255, np.uint8(1))
    raise SystemExit(f"no {encoding} samples for {rgb}")


def pack(smp: np.ndarray, bits: int) -> bytes:
    """Image data of (h, w, components) samples: per row the pixels left to right, each pixel's components in
    colour-space order (R, G, B: the 3-byte pixels of X20 p. 180's eDirectPixel e8Bit example), samples of
    `bits` packed contiguously from the most significant bit (no padding inside a row, a pixel may straddle a
    byte), the row padded with zero bytes to row_bytes (X20 p. 179)."""
    h, w, n = smp.shape
    flat = smp.reshape(h, w * n)
    if bits == 1:
        rows = np.packbits(flat, axis=1, bitorder="big")
    elif bits == 4:
        flat = np.pad(flat, ((0, 0), (0, flat.shape[1] % 2)))
        rows = (flat[:, 0::2] << 4 | flat[:, 1::2]).astype(np.uint8)
    elif bits == 8:
        rows = flat.astype(np.uint8)
    else:
        raise SystemExit(f"no packing for {bits} bits")
    return np.pad(rows, ((0, 0), (0, row_bytes(w, n * bits) - rows.shape[1]))).tobytes()


def image(x: int, y: int, rgb: list[int], mask: np.ndarray, group: str,
          block: Callable[[str], bytes] | None = None, encoding: str = "indexed1") -> bytes:
    """One image of the 0/1 ink mask at (x, y) dots in colour rgb, in one of the ENCODING pixel encodings
    (indexed1: e1Bit through [white, rgb]; indexed4: e4Bit through S9's 16-entry palette; direct8 / direct1:
    eDirectPixel, no palette); the group's colour space, then the group's control block."""
    h, w = mask.shape
    mapping, depth, _, bits = ENCODING[encoding]
    s = ub(E[expected_state(group)["space"]], "ColorSpace")
    if encoding == "indexed1":
        s += ub(E["e8Bit"], "PaletteDepth")
        s += bytes((UBYTE_ARRAY, UBYTE, 6, 255, 255, 255, *rgb, ATTR_UBYTE, ATTR["PaletteData"]))
    elif encoding == "indexed4":
        s += ub(E["e8Bit"], "PaletteDepth")
        s += bytes((UBYTE_ARRAY, UBYTE, 48)) + xl.palette().tobytes() + bytes((ATTR_UBYTE, ATTR["PaletteData"]))
    s += op("SetColorSpace") + (block or control_block)(group)
    s += xy(x, y, "Point", SINT16_XY) + op("SetCursor")
    s += ub(E[mapping], "ColorMapping") + ub(E[depth], "ColorDepth")
    s += u16(w, "SourceWidth") + u16(h, "SourceHeight") + xy(w, h, "DestinationSize") + op("BeginImage")
    s += u16(0, "StartLine") + u16(h, "BlockHeight") + ub(E["eNoCompression"], "CompressMode")
    s += op("ReadImage")
    data = pack(samples(mask, rgb, encoding), bits)
    return s + struct.pack("<BI", EMBED, len(data)) + data + op("EndImage")


def patch_raster(pat: np.ndarray) -> np.ndarray:
    """(117, 93) index raster: the pattern square, cells 3 x 3 dots, over the solid bar."""
    return np.vstack([np.kron(pat, np.ones((CELL_DOTS, CELL_DOTS), np.uint8)),
                      np.ones((SOLID_DOTS, PATTERN_DOTS), np.uint8)])


def vector_patch(x: int, y: int, rgb: list[int], pat: np.ndarray,
                 block: Callable[[str], bytes] | None = None) -> bytes:
    """The same patch as filled rectangles: per cell row one rectangle per horizontal run of inked cells,
    plus the bar.  X20 p. 211: PCL XL fills a vector box (x1, y1, x2, y2) on pixels x1..x2-1, y1..y2-1."""
    s = ub(E["eRGB"], "ColorSpace") + op("SetColorSpace") + (block or control_block)("vector")
    s += ub(0, "NullPen") + op("SetPenSource")  # SetColorSpace resets pen and brush to black (X20 p. 85)
    s += bytes((UBYTE_ARRAY, UBYTE, 3, *rgb, ATTR_UBYTE, ATTR["RGBColor"])) + op("SetBrushSource")
    boxes = []
    for r in range(CELLS):
        c = 0
        while c < CELLS:
            if pat[r, c]:
                e = c
                while e < CELLS and pat[r, e]:
                    e += 1
                top, bottom = y + r * CELL_DOTS, y + (r + 1) * CELL_DOTS
                boxes.append((x + c * CELL_DOTS, top, x + e * CELL_DOTS, bottom))
                c = e
            else:
                c += 1
    boxes.append((x, y + PATTERN_DOTS, x + PATTERN_DOTS, y + PATCH_H_DOTS))
    for box in boxes:
        s += struct.pack("<B4HBB", UINT16_BOX, *box, ATTR_UBYTE, ATTR["BoundingBox"]) + op("Rectangle")
    # Back to the page-default black brush (X20 p. 75).  gpcl6 10.08 keeps the brush across SetColorSpace,
    # against X20 p. 85, and under the default ROP3 252 a white brush paints every later image white.
    return s + bytes((UBYTE_ARRAY, UBYTE, 3, 0, 0, 0, ATTR_UBYTE, ATTR["RGBColor"])) + op("SetBrushSource")


_BASE = controls("base")
CONTROL = {name: code for name, (_, _, code) in _BASE.items()}
CONTROL["matrix1x1"] = controls("dither1x1")["halftone"][2]
CONTROL["highlpi"] = CONTROL.pop("halftone")
CONTROL["tonerblack"] = ub(E["eTonerBlack"], "AllObjectTypes") + op("SetNeutralAxis")
SOURCES = {name: src for name, (_, src, _) in _BASE.items()} | {
    "matrix1x1": controls("dither1x1")["halftone"][1], "highlpi": _BASE["halftone"][1],
    "tonerblack": "SetNeutralAxis 0x7e (X30 p. 11): AllObjectTypes (29) = eTonerBlack (0, X30 p. 31)",
    "pushgs_popgs": "PushGS 0x61 / PopGS 0x60 (X20 p. 79-80): every graphics-state attribute is copied; X20 "
                    "p. 75 and X30 p. 5 list HalftoneMethod (per object type), NeutralAxis, ColorTreatment, "
                    "AdaptiveHalftone, ColorTrapping and ColorSpace as graphics-state attributes",
    "vector": "SetPenSource NullPen (X20 p. 90-92), SetBrushSource RGBColor ubyte_array (X20 p. 87-89), "
              "Rectangle BoundingBox uint16_box (X20 p. 172; fill rule X20 p. 210-211)",
    "srgb": "SetColorSpace ColorSpace = 6 (eSRGB: not in X20/X21/X30, GhostPCL's value), palette as eRGB; "
            "no SetColorTreatment after it (precondition eRGB, X21 p. 22), the treatment in force is the "
            "eNoTreatment inherited through PopGS; the last group on the page",
    "treatdefault": "the FIRST objects on the page, directly after BeginPage and before the page head: "
                    "SetColorSpace eRGB, then the control block WITHOUT SetColorTreatment, so the treatment "
                    "in force is the BeginPage default (graphics state initialised at BeginPage, X20 p. 47; "
                    "default eScreenMatch, X21 p. 24 and X30 p. 5; ColorTreatment persists across "
                    "SetColorSpace, which resets only pen and brush, X20 p. 85)",
    "control_block": "after EVERY SetColorSpace, S9's order: SetColorTreatment eNoTreatment (not for "
                     "treatdefault/srgb), SetAdaptiveHalftoning eDisable, SetColorTrapping eDisable, "
                     "SetNeutralAxis eProcessBlack (eTonerBlack in the tonerblack group), "
                     "SetHalftoneMethod in the highlpi/matrix1x1 groups; postconditions X21 p. 22, "
                     "X30 p. 9, 10, 11",
    "image": "SetColorSpace (X20 p. 85-86) eRGB 2-entry e8Bit palette; BeginImage (X20 p. 177) eIndexedPixel "
             "e1Bit; ReadImage (X20 p. 179) one block, rows 12 bytes",
    "encodings": "BeginImage ColorDepth = bits per image COMPONENT, {e1Bit | e4Bit | e8Bit}, ColorMapping "
                 "{eDirectPixel | eIndexedPixel} (X20 p. 177; eDirectPixel 0, eIndexedPixel 1, e1Bit 0, e4Bit 1, "
                 "e8Bit 2, X20 Appendix G p. 226); an indexed palette holds 2**depth entries x 3 (X20 p. 85), "
                 "so enc4bit carries S9's 16-entry palette (48 B); the direct riders' SetColorSpace carries no "
                 "palette ({ColorSpace} alone, X20 p. 85). Row rule (X20 p. 179): 'The length of each line of "
                 "image data within the image block must be a multiple of four bytes unless the "
                 "PadBytesMultiple parameter is specified' (none is sent); the first byte is the left-most "
                 "(no byte swapping). Pixel layout: components in R, G, B order per pixel (X20 p. 180's "
                 "eDirectPixel e8Bit example: 3 bytes per pixel, 640 x 480 x 3 = 921,600 B), samples packed "
                 "back to back from the most significant bit with no padding inside a row (a direct e1Bit "
                 "pixel is 3 bits and straddles bytes); X20 states the bit order of sub-byte samples nowhere, "
                 "MSB-first is gpcl6's reading (0 differing dots). Rows: indexed1 93 bits -> 12 B, indexed4 "
                 "372 bits -> 47 -> 48 B, direct8 279 B -> 280 B, direct1 279 bits -> 35 -> 36 B",
}


GROUP_ORDER = ("treatdefault", "default", "vector", "tonerblack", "highlpi", "matrix1x1", "srgb")
PRE_HEAD = ("treatdefault",)  # drawn before the page head: no SetColorTreatment has run on the page yet
WRAPPED = ("tonerblack", "highlpi", "matrix1x1")  # PushGS ... PopGS
NO_TREATMENT = ("treatdefault", "srgb")  # groups drawn without SetColorTreatment
# The graphics state BeginPage installs (X20 p. 47; defaults X21 p. 24 and X30 p. 5: ColorTreatment
# eScreenMatch, AdaptiveHalftone enabled, ColorTrapping normal, NeutralAxis per object type, HalftoneMethod
# per object type); "page-default" marks a value no Set... operator has written on this page.
PAGE_DEFAULT = {"treatment": "page-default eScreenMatch", "adaptive": "page-default enabled",
                "trapping": "page-default normal", "neutral": "page-default per object type",
                "halftone": "default"}


def group_of(p: dict) -> str:
    """Emission group: the method for the pattern kind and the encoding riders (all 'default': drawn in the
    default group, among the default patterns in slot order), the kind for every other rider."""
    if p["kind"] != "pattern" and p["method"] != "default":
        raise SystemExit(f"patch {p['id']}: rider {p['kind']} under method {p['method']}")
    return p["method"] if p["kind"] == "pattern" or p["kind"] in ENC_KINDS else p["kind"]


def expected_state(group: str) -> dict:
    """What an object of the group must have in force: colour space, the four controls, the halftone method,
    the PushGS depth, and the exact control operators between its own SetColorSpace and the object.  The
    treatment witness sees the BeginPage default; the eSRGB riders the eNoTreatment PopGS restores."""
    neutral = "eTonerBlack" if group == "tonerblack" else "eProcessBlack"
    halftone = group if group in ("highlpi", "matrix1x1") else "default"
    block = (([] if group in NO_TREATMENT else ["SetColorTreatment"])
             + ["SetAdaptiveHalftoning", "SetColorTrapping", "SetNeutralAxis"]
             + (["SetHalftoneMethod"] if halftone != "default" else []))
    return {"space": "eSRGB" if group == "srgb" else "eRGB",
            "treatment": PAGE_DEFAULT["treatment"] if group == "treatdefault" else "eNoTreatment",
            "adaptive": "eDisable", "trapping": "eDisable", "neutral": neutral, "halftone": halftone,
            "depth": 1 if group in WRAPPED else 0, "block": block}


def control_block(group: str) -> bytes:
    """S9's control block in S9's order, sent after EVERY SetColorSpace (X21 p. 22, X30 p. 9-11)."""
    s = b"" if group in NO_TREATMENT else CONTROL["treatment"]
    s += CONTROL["adaptive"] + CONTROL["trapping"]
    s += CONTROL["tonerblack" if group == "tonerblack" else "neutral"]
    return s + (CONTROL[group] if group in ("highlpi", "matrix1x1") else b"")


def groups(patches: list[dict], order: tuple[str, ...] = GROUP_ORDER) -> list[tuple[str, list[dict]]]:
    """Emission groups in GROUP_ORDER; inside a group, slot order (top to bottom, left to right)."""
    by: dict[str, list[dict]] = {g: [] for g in order}
    for p in sorted(patches, key=lambda p: p["_slot"]):
        by[group_of(p)].append(p)
    return list(by.items())


def emit_job(patches: list[dict], fids: list[dict], order: tuple[str, ...] = GROUP_ORDER,
             block: Callable[[str], bytes] = control_block, wrapped: tuple[str, ...] = WRAPPED) -> bytes:
    """The job: BeginPage, the PRE_HEAD groups (the treatment witness), the page head and the fiducials, the
    other groups in order.  order / block / wrapped exist for the mutation tests only."""
    s = bytearray(xy(DPI, DPI, "UnitsPerMeasure") + ub(E["eInch"], "Measure")
                  + ub(E["eBackChAndErrPage"], "ErrorReport") + op("BeginSession"))
    s += ub(E["eDefaultDataSource"], "SourceType") + ub(E["eBinaryLowByteFirst"], "DataOrg")
    s += op("OpenDataSource")
    s += ub(E["ePortraitOrientation"], "Orientation") + ub(E["eA4Paper"], "MediaSize")
    s += ub(E["eDefaultSource"], "MediaSource") + op("BeginPage")
    head = ub(E["eRGB"], "ColorSpace") + op("SetColorSpace") + block("default")  # S9's page head
    for f in fids:
        x, y, w, h = f["_xywh"]
        head += image(x, y, [0, 0, 0], np.ones((h, w), np.uint8), "default", block)
    pending = True
    for name, members in groups(patches, order):
        if pending and name not in PRE_HEAD:
            s += head
            pending = False
        if name in wrapped:
            s += op("PushGS")
        for p in members:
            x, y = p["_xy"]
            if p["kind"] == "vector":
                s += vector_patch(x, y, p["rgb"], p["_pattern"], block)
            else:
                s += image(x, y, p["rgb"], patch_raster(p["_pattern"]), name, block, p["encoding"])
        if name in wrapped:
            s += op("PopGS")
    if pending:
        s += head
    s += op("EndPage") + op("CloseDataSource") + op("EndSession")
    header = b") HP-PCL XL;3;0;Comment e041 %s RGB probe sheet\n" % JOB_NAME.encode()
    pjl = (b'@PJL JOB NAME="%s"\r\n@PJL SET RESOLUTION=600\r\n@PJL SET BITSPERPIXEL=1\r\n'
           b"@PJL ENTER LANGUAGE=PCLXL\r\n" % JOB_NAME.encode())
    return UEL + pjl + header + bytes(s) + UEL + b'@PJL EOJ NAME="%s"\r\n' % JOB_NAME.encode() + UEL


CONTROL_OPS = ("SetColorTreatment", "SetAdaptiveHalftoning", "SetColorTrapping", "SetNeutralAxis",
               "SetHalftoneMethod", "PushGS", "PopGS")
STATE_KEYS = ("space", "treatment", "adaptive", "trapping", "neutral", "halftone", "depth", "block")
HEAD_BLOCK = ["SetColorTreatment", "SetAdaptiveHalftoning", "SetColorTrapping", "SetNeutralAxis"]


def enum(a: dict, key: str, table: dict[int, str]) -> str:
    """The enumeration name of a single-attribute control; anything else spelled out (and so a mismatch)."""
    return table.get(a[key], f"{key}={a[key]}") if set(a) == {key} else f"other {a}"


def decode_image(img: dict) -> tuple[str, np.ndarray, np.ndarray] | str:
    """The verifier's own image decoder (written apart from pack()): (encoding, samples (h, w, components),
    rgb (h, w, 3)) of one BeginImage..EndImage, or why it cannot be decoded.  Rule implemented: a pixel is
    ColorDepth bits per component (X20 p. 177), one component when indexed, three for an eRGB/eSRGB direct
    pixel in R, G, B order (X20 p. 180's 3-byte example); the row is the pixels' bits back to back from the
    most significant bit of its first byte, then zero padding to a whole byte and on to a multiple of four
    bytes (X20 p. 179, no PadBytesMultiple); one block, StartLine 0, BlockHeight = SourceHeight.  Indexed
    samples are looked up in the STREAM's palette, which must hold 2**depth entries (X20 p. 85); a direct
    sample s of d bits is s * 255 / (2**d - 1)."""
    b = img["begin"]
    w, h = b["SourceWidth"], b["SourceHeight"]
    direct = {E["eDirectPixel"]: True, E["eIndexedPixel"]: False}.get(b["ColorMapping"])
    bits = {E["e1Bit"]: 1, E["e4Bit"]: 4, E["e8Bit"]: 8}.get(b["ColorDepth"])
    if direct is None or bits is None:
        return f"ColorMapping {b['ColorMapping']} ColorDepth {b['ColorDepth']} not decoded"
    n = 3 if direct else 1
    bit_len = w * n * bits
    stride = (bit_len + 7) // 8
    stride += -stride % 4
    raw = b"".join(d for _, _, d in img["rows"])
    blocks = [(s, bh) for s, bh, _ in img["rows"]]
    if blocks != [(0, h)] or len(raw) != h * stride:
        return f"blocks {blocks}, {len(raw)} B where {h} rows of {stride} B are due"
    bitmat = np.unpackbits(np.frombuffer(raw, np.uint8).reshape(h, stride), axis=1)
    if bitmat[:, bit_len:].any():
        return "nonzero row padding"
    smp = bitmat[:, :bit_len].reshape(h, w, n, bits) @ (1 << np.arange(bits - 1, -1, -1))
    if direct:
        return f"direct{bits}", smp, smp * 255 // (2 ** bits - 1)
    pal = img["palette"]
    if pal is None or len(pal) != 3 * 2 ** bits:
        return f"indexed{bits} image under palette {pal} (2**{bits} entries due, X20 p. 85)"
    return f"indexed{bits}", smp, np.asarray(pal).reshape(-1, 3)[smp[..., 0]]


def want_samples(mask: np.ndarray, p: dict) -> np.ndarray:
    """The samples a patch must carry, stated apart from samples(): indexed1 the mask; indexed4 index
    C + 2M + 4Y of the corner (S9's rule, pclxl_bilevel) on ink, 0 on blank; direct8 the RGB on ink, 255 on
    blank; direct1 RGB / 255 on ink, 1 on blank."""
    r = np.asarray(p["rgb"])
    m = mask[..., None].astype(bool)
    return {"indexed1": m * 1, "indexed4": m * int(((r == 0) << np.arange(3)).sum()),
            "direct8": np.where(m, r, 255), "direct1": np.where(m, r // 255, 1)}[p["encoding"]]


BLANK_SAMPLE = {"indexed1": 0, "indexed4": 0, "direct8": 255, "direct1": 1}


def interpret(ops: list[list]) -> tuple[list[dict], list[str], dict[str, list[int]]]:
    """Walk the decoded stream with a graphics-state stack; one record per painted object (image or a run of
    Rectangles under one brush): cursor/origin, colour space, palette or brush, the control state in force,
    the PushGS depth, how many SetColorTreatment / SetHalftoneMethod the page has executed before it, the
    control operators executed since its SetColorSpace (block), and its index raster or box mask.
    Model (the spec's): BeginPage installs PAGE_DEFAULT (X20 p. 47; X21 p. 24, X30 p. 5); treatment,
    adaptive halftoning, trapping, neutral axis and halftone method are graphics state that persists until
    set again, saved and restored only by PushGS/PopGS (X20 p. 79-80); SetColorSpace sets the space and the
    palette and resets pen and brush to black (X20 p. 85) and nothing else.  brush_gpcl6 is the brush as
    gpcl6 10.08 keeps it (across SetColorSpace); images are checked under both."""
    gs: dict = {}
    stack: list[dict] = []
    objs: list[dict] = []
    problems: list[str] = []
    marks: dict[str, list[int]] = {"tonerblack": [], "halftone": [], "halftone_depth": [], "treatment": [],
                                   "treatment_non_rgb": []}
    cursor, img, space_op = None, None, None
    block: list[str] = []
    seen: Counter = Counter()  # control operators executed on the page so far
    for i, (name, a, data) in enumerate(ops):
        if name in CONTROL_OPS:
            block.append(name)
            seen[name] += 1
        if name == "BeginPage":
            gs = {"space": "eRGB", "palette": None, "pen": "black", "brush": [0, 0, 0],
                  "brush_gpcl6": [0, 0, 0], **PAGE_DEFAULT}
            stack, seen = [], Counter()
        elif name == "PushGS":
            stack.append(dict(gs))
        elif name == "PopGS":
            if stack:
                gs = stack.pop()
            else:
                problems.append(f"PopGS at op {i} without PushGS")
        elif name == "SetColorSpace":
            gs.update(space={2: "eRGB", 6: "eSRGB"}.get(a["ColorSpace"], a["ColorSpace"]),
                      palette=list(a["PaletteData"]) if "PaletteData" in a else None, pen="black",
                      brush=[0, 0, 0])
            block, space_op = [], i
        elif name == "SetColorTreatment":
            marks["treatment"].append(i)
            if gs["space"] != "eRGB":
                marks["treatment_non_rgb"].append(i)
                problems.append(f"SetColorTreatment at op {i} under colour space {gs['space']} (X21 p. 22)")
            gs["treatment"] = enum(a, "ColorTreatment", {0: "eNoTreatment", 1: "eScreenMatch", 2: "eVivid"})
        elif name == "SetAdaptiveHalftoning":
            gs["adaptive"] = enum(a, "AllObjectTypes", {0: "eDisable", 1: "eEnable"})
        elif name == "SetColorTrapping":
            gs["trapping"] = enum(a, "AllObjectTypes", {0: "eDisable"})
        elif name == "SetNeutralAxis":
            gs["neutral"] = enum(a, "AllObjectTypes", {0: "eTonerBlack", 1: "eProcessBlack"})
            if gs["neutral"] == "eTonerBlack":
                marks["tonerblack"].append(i)
        elif name == "SetHalftoneMethod":
            marks["halftone"].append(i)
            marks["halftone_depth"].append(len(stack))
            matrix = {"DitherMatrixSize": [1, 1], "DitherMatrixDataType": E["eUByte"],
                      "DitherMatrixDepth": E["e8Bit"]}
            if a == matrix and data == b"\x80\x00\x00\x00":
                gs["halftone"] = "matrix1x1"
            elif a == {k: E["eHighLPI"] for k in ("TextObjects", "VectorObjects", "RasterObjects")}:
                gs["halftone"] = "highlpi"
            else:
                gs["halftone"] = f"other {a} {data.hex()}"
        elif name == "SetPenSource":
            gs["pen"] = "null" if "NullPen" in a else "set"
        elif name == "SetBrushSource":
            gs["brush"] = gs["brush_gpcl6"] = list(a["RGBColor"])
            objs.append({"type": "rect", "boxes": [], "op": i, "end_op": i, "space_op": space_op,
                         "block": list(block), "depth": len(stack),
                         "treatments_before": seen["SetColorTreatment"],
                         "halftones_before": seen["SetHalftoneMethod"], **gs})
        elif name == "Rectangle":
            if not objs or objs[-1]["type"] != "rect" or objs[-1]["brush"] != gs["brush"]:
                problems.append("Rectangle without its own SetBrushSource")
                continue
            objs[-1]["boxes"].append(tuple(a["BoundingBox"]))
            objs[-1]["end_op"] = i
        elif name == "SetCursor":
            cursor = tuple(a["Point"])
        elif name == "BeginImage":
            img = {"type": "image", "cursor": cursor, "begin": a, "rows": [], "op": i, "space_op": space_op,
                   "block": list(block), "depth": len(stack), "treatments_before": seen["SetColorTreatment"],
                   "halftones_before": seen["SetHalftoneMethod"], **gs}
        elif name == "ReadImage":
            img["rows"].append((a["StartLine"], a["BlockHeight"], data))
        elif name == "EndImage":
            got = decode_image(img)
            if isinstance(got, str):
                problems.append(f"image at {cursor}: {got}")
                continue
            img["encoding"], img["samples"], img["rgb"] = got
            img["end_op"] = i
            objs.append(img)
    if stack:
        problems.append(f"{len(stack)} PushGS left open at the end")
    return objs, problems, marks


def state_mismatch(o: dict, group: str) -> list[str]:
    """The control-state fields of a decoded object that differ from what its group demands."""
    want = expected_state(group)
    return [f"{k}: {o[k]!r} != {want[k]!r}" for k in STATE_KEYS if o[k] != want[k]]


def runs(seq: list) -> list:
    """Run-length list [[item, count], ...] of a sequence."""
    out: list = []
    for v in seq:
        if out and out[-1][0] == v:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return out


def read_back(job: bytes, patches: list[dict], fids: list[dict]) -> dict:
    ops = parse(stream_body(job))
    names = [n for n, _, _ in ops]
    objs, problems, marks = interpret(ops)
    want_by_xy = {p["_xy"]: p for p in patches}
    fid_by_xy = {f["_xywh"][:2]: f for f in fids}
    checked, state_bad, blocks, encodings = Counter(), Counter(), Counter(), Counter()
    blank_riders: list[int] = []  # encoding riders of the W corner: ink == blank, no pattern in the stream
    sequence: list[tuple[str, dict]] = []  # (group or "fiducial", object) in stream order
    for o in objs:
        if o["type"] == "image":
            x, y = o["cursor"]
            pal = o["palette"]
            black = o["brush"] == [0, 0, 0] and o["brush_gpcl6"] == [0, 0, 0]
            if (x, y) in fid_by_xy:
                f = fid_by_xy.pop((x, y))
                bad = state_mismatch(o, "default")
                ok = (pal == [255, 255, 255, 0, 0, 0] and o["encoding"] == "indexed1"
                      and o["samples"].shape[:2] == f["_xywh"][:1:-1] and black and bool(o["samples"].all())
                      and not bad)
                checked["fiducials_ok" if ok else "fiducials_bad"] += 1
                state_bad.update(b.split(":")[0] for b in bad)
                blocks[("fiducial", ",".join(o["block"]))] += 1
                sequence.append(("fiducial", o))
                if not ok:
                    problems.append(f"fiducial {f['id']} disagrees with the stream {bad}")
                continue
            p = want_by_xy.pop((x, y), None)
            if p is None:
                problems.append(f"image at {(x, y)} matches no manifest entry")
                continue
            enc, mask = o["encoding"], patch_raster(p["_pattern"])
            encodings[enc] += 1
            want_pal = {"indexed1": [255, 255, 255, *p["rgb"]],
                        "indexed4": list(xl.palette().tobytes())}.get(p["encoding"])
            # The stream carries the pattern unless ink and blank are one sample: the W corner in indexed4
            # (index 0 both), direct8 and direct1 (white both); those are checked as all-white rasters.
            carries = enc == "indexed1" or p["rgb"] != [255, 255, 255]
            if not carries:
                blank_riders.append(p["id"])
            ink = (o["samples"] != BLANK_SAMPLE.get(enc)).any(-1)
            ok = (p["kind"] != "vector" and enc == p["encoding"] and pal == want_pal and black
                  and o["samples"].shape[:2] == (PATCH_H_DOTS, PATTERN_DOTS)
                  and np.array_equal(o["samples"], want_samples(mask, p))
                  and np.array_equal(o["rgb"], np.where(mask[..., None] == 1, np.asarray(p["rgb"]), 255))
                  and (not carries or sha(ink[1:PATTERN_DOTS:CELL_DOTS, 1::CELL_DOTS].astype(np.uint8).tobytes())
                       == p["pattern_sha256"]))
        else:
            if not o["boxes"]:
                if o["brush"] != [0, 0, 0]:  # a black brush without rectangles = the restore after a patch
                    problems.append("brush set without rectangles")
                continue
            x0, y0 = min(b[0] for b in o["boxes"]), min(b[1] for b in o["boxes"])
            p = want_by_xy.pop((x0, y0), None)
            if p is None:
                problems.append(f"rectangles at {(x0, y0)} match no manifest entry")
                continue
            mask = np.zeros((PATCH_H_DOTS, PATTERN_DOTS), np.uint8)
            for x1, y1, x2, y2 in o["boxes"]:
                mask[y1 - y0:y2 - y0, x1 - x0:x2 - x0] += 1
            ok = (o["brush"] == p["rgb"] and o["pen"] == "null" and p["kind"] == "vector"
                  and np.array_equal(mask, patch_raster(p["_pattern"])))
        group = group_of(p)
        bad = state_mismatch(o, group)
        state_bad.update(b.split(":")[0] for b in bad)
        blocks[(group, ",".join(o["block"]))] += 1
        sequence.append((group, o))
        ok = ok and not bad
        checked[f"{p['kind']}_{p['method']}_{'ok' if ok else 'bad'}"] += 1
        if not ok:
            problems.append(f"patch {p['id']} disagrees with the stream {bad}")
    problems += [f"manifest patch {p['id']} not in the stream" for p in want_by_xy.values()]
    problems += [f"fiducial {f['id']} not in the stream" for f in fid_by_xy.values()]

    by_group: dict[str, list[dict]] = {}
    for g, o in sequence:
        by_group.setdefault(g, []).append(o)
    span = {g: (min(o["space_op"] for o in os_), max(o["end_op"] for o in os_)) for g, os_ in by_group.items()}

    def inside(i: int, g: str) -> bool:
        return g in span and span[g][0] <= i <= span[g][1]

    witness = by_group.get("treatdefault", [])
    first_treatment = marks["treatment"][0] if marks["treatment"] else len(names)
    first_halftone = marks["halftone"][0] if marks["halftone"] else len(names)
    srgb = by_group.get("srgb", [])
    owned = {o["space_op"] for _, o in sequence}
    head_ops = [i for i, n in enumerate(names) if n == "SetColorSpace" and i not in owned]
    h = head_ops[0] if len(head_ops) == 1 else None
    expected_runs = [*PRE_HEAD, "fiducial", *(g for g in GROUP_ORDER if g not in PRE_HEAD)]
    group_runs = runs([g for g, _ in sequence])
    per_space = Counter(o["space_op"] for _, o in sequence)
    pushes = [i for i, n in enumerate(names) if n == "PushGS"]
    pops = [i for i, n in enumerate(names) if n == "PopGS"]
    position = {
        "treatment_witness_objects": len(witness),
        "first_SetColorTreatment_op": first_treatment,
        "first_SetHalftoneMethod_op": first_halftone,
        "witness_last_op": max((o["end_op"] for o in witness), default=None),
        "witness_after_a_SetColorTreatment": sum(
            1 for o in witness if o["treatments_before"] or o["op"] > first_treatment),
        "witness_after_a_SetHalftoneMethod": sum(
            1 for o in witness if o["halftones_before"] or o["op"] > first_halftone),
        "default_method_objects_after_a_SetHalftoneMethod_excluding_srgb": sum(
            1 for g in ("treatdefault", "fiducial", "default", "vector", "tonerblack")
            for o in by_group.get(g, []) if o["halftones_before"]),
        "srgb_treatment_in_force": dict(Counter(o["treatment"] for o in srgb)),
        "srgb_halftone_in_force": dict(Counter(o["halftone"] for o in srgb)),
        "srgb_objects_executing_SetColorTreatment": sum("SetColorTreatment" in o["block"] for o in srgb),
        "SetColorTreatment_under_a_non_eRGB_space": len(marks["treatment_non_rgb"]),
        "SetHalftoneMethod_outside_its_wrapped_group": sum(
            1 for i, d in zip(marks["halftone"], marks["halftone_depth"])
            if d != 1 or not (inside(i, "highlpi") or inside(i, "matrix1x1"))),
        "eTonerBlack_outside_its_group": sum(1 for i in marks["tonerblack"] if not inside(i, "tonerblack")),
        "PushGS_at": pushes, "PopGS_at": pops,
        "page_head_SetColorSpace_at": head_ops,
    }
    verdicts = {
        "head_BeginPage_then_witness": names[:4] == ["BeginSession", "OpenDataSource", "BeginPage",
                                                     "SetColorSpace"]
        and bool(witness) and witness[0]["space_op"] == 3,
        "tail_EndPage_CloseDataSource_EndSession": names[-3:] == ["EndPage", "CloseDataSource", "EndSession"],
        "page_head_after_witness_before_fiducials": h is not None and bool(witness) and "fiducial" in span
        and h > position["witness_last_op"] and names[h + 1:h + 5] == HEAD_BLOCK
        and h + 5 == span["fiducial"][0],
        "no_problems": not problems,
        "no_state_mismatches": not state_bad,
        "all_objects_ok": not any(k.endswith("bad") for k in checked)
        and sum(checked.values()) == len(patches) + len(fids),
        "witness_before_any_SetColorTreatment": len(witness) == len(TREAT_WITNESS)
        and not position["witness_after_a_SetColorTreatment"],
        "witness_before_any_SetHalftoneMethod": not position["witness_after_a_SetHalftoneMethod"],
        "default_method_before_any_SetHalftoneMethod": not position[
            "default_method_objects_after_a_SetHalftoneMethod_excluding_srgb"],
        "srgb_no_SetColorTreatment": not position["srgb_objects_executing_SetColorTreatment"]
        and not position["SetColorTreatment_under_a_non_eRGB_space"],
        "halftone_only_inside_its_wrapped_group": not position["SetHalftoneMethod_outside_its_wrapped_group"],
        "eTonerBlack_only_in_its_group": not position["eTonerBlack_outside_its_group"],
        "PushGS_PopGS_exactly_around_wrapped_groups": all(g in span for g in WRAPPED)
        and pushes == sorted(span[g][0] - 1 for g in WRAPPED)
        and pops == sorted(span[g][1] + 1 for g in WRAPPED),
        "groups_contiguous_in_order": [g for g, _ in group_runs] == expected_runs,
        "srgb_last_object_then_EndPage": bool(sequence) and sequence[-1][0] == "srgb"
        and names[sequence[-1][1]["end_op"] + 1] == "EndPage",
        "one_SetColorSpace_per_object_plus_head": names.count("SetColorSpace") == 1 + len(sequence)
        and not any(n > 1 for n in per_space.values()),
    }
    return {"operators": len(names), "operator_counts": dict(sorted(Counter(names).items())),
            "objects": len(sequence), "group_runs": group_runs,
            "objects_checked": dict(sorted(checked.items())), "state_mismatches": dict(state_bad),
            "patch_images_by_decoded_encoding": dict(sorted(encodings.items())),
            "white_encoding_riders_checked_as_all_white": blank_riders,
            "control_blocks_by_group": {f"{g}: {b or '(none)'}": n for (g, b), n in sorted(blocks.items())},
            "position": position, "verdicts": verdicts,
            "failed": [k for k, v in verdicts.items() if not v], "pass": all(verdicts.values()),
            "problems": problems,
            "gs_sequence_runs": runs([n for n in names if n in ("PushGS", "PopGS", "SetHalftoneMethod")])}


def mutation_tests(patches: list[dict], fids: list[dict]) -> dict:
    """Mutated jobs the stream checks must each refuse: name -> {caught, failed verdicts}."""
    def blk(**over: Callable[[str], bytes]) -> Callable[[str], bytes]:
        return lambda g: over[g](g) if g in over else control_block(g)

    def order_moving(g: str, after: str) -> tuple[str, ...]:
        rest = [x for x in GROUP_ORDER if x != g]
        return tuple(rest[:rest.index(after) + 1] + [g] + rest[rest.index(after) + 1:])

    mutants: dict[str, dict] = {
        "treatdefault moved behind the default group (after a SetColorTreatment)":
            {"order": order_moving("treatdefault", "default")},
        "treatdefault moved to just before srgb (the previous build's order)":
            {"order": order_moving("treatdefault", "matrix1x1")},
        "treatdefault with SetColorTreatment": {"block": blk(treatdefault=lambda g: CONTROL["treatment"]
                                                             + control_block(g))},
        "srgb with SetColorTreatment": {"block": blk(srgb=lambda g: CONTROL["treatment"] + control_block(g))},
        "srgb before matrix1x1": {"order": order_moving("srgb", "highlpi")},
        "SetHalftoneMethod eHighLPI in the default group": {"block": blk(default=lambda g: control_block(g)
                                                                         + CONTROL["highlpi"])},
        "eTonerBlack in the vector group": {"block": blk(vector=lambda g: control_block("tonerblack"))},
        "matrix1x1 not wrapped in PushGS/PopGS": {"wrapped": ("tonerblack", "highlpi")},
        "vector without SetColorTrapping": {"block": blk(vector=lambda g: control_block(g).replace(
            CONTROL["trapping"], b""))},
    }
    jobs = {name: emit_job(patches, fids, **kw) for name, kw in mutants.items()}
    # One witness object, its bytes unchanged, cut from the head of the page and pasted after the first
    # fiducial, i.e. behind the page head's SetColorTreatment.
    job = emit_job(patches, fids)
    w = next(p for p in sorted(patches, key=lambda p: p["_slot"]) if group_of(p) == "treatdefault")
    obj = image(*w["_xy"], w["rgb"], patch_raster(w["_pattern"]), "treatdefault")
    x, y, fw, fh = fids[0]["_xywh"]
    fid = image(x, y, [0, 0, 0], np.ones((fh, fw), np.uint8), "default")
    if job.count(obj) != 1 or job.count(fid) != 1:
        raise SystemExit("mutation: the witness or the fiducial bytes are not unique in the job")
    cut = job.replace(obj, b"")
    jobs[f"one treatdefault object (patch {w['id']}) moved behind the page head's SetColorTreatment"] = (
        cut.replace(fid, fid + obj))
    # Round 4: one direct1 patch with its rows padded to whole bytes only (35 B, not the four-byte multiple
    # 36 B of X20 p. 179), and one enc4bit patch whose ink index names another corner.
    def swapped(p: dict, data: Callable[[bytes], bytes]) -> bytes:
        mask = patch_raster(p["_pattern"])
        good = pack(samples(mask, p["rgb"], p["encoding"]), ENCODING[p["encoding"]][3])
        obj = image(*p["_xy"], p["rgb"], mask, "default", encoding=p["encoding"])
        bad = data(good)
        if job.count(obj) != 1 or obj.count(good) != 1 or bad == good:
            raise SystemExit(f"mutation: patch {p['id']}'s bytes are not unique or the mutation is void")
        frame = struct.pack("<BI", EMBED, len(good)) + good
        return job.replace(obj, obj.replace(frame, struct.pack("<BI", EMBED, len(bad)) + bad))

    def first(encoding: str) -> dict:
        return next(p for p in sorted(patches, key=lambda p: p["_slot"])
                    if p["encoding"] == encoding and p["rgb"] != [255, 255, 255])

    def unpadded(good: bytes) -> bytes:
        rows = np.frombuffer(good, np.uint8).reshape(PATCH_H_DOTS, -1)
        if rows.shape[1] - 1 != -(-PATTERN_DOTS * 3 // 8) or rows[:, -1].any():
            raise SystemExit("mutation: the direct1 row's last byte is not pure padding")
        return rows[:, :-1].tobytes()

    d1, e4 = first("direct1"), first("indexed4")
    k = s9_index(e4["rgb"])
    k2 = k % 7 + 1  # another inked corner (indices 1..7)

    def wrong_corner(good: bytes) -> bytes:
        a = np.frombuffer(good, np.uint8)
        hi, lo = a >> 4, a & 15
        return ((np.where(hi == k, k2, hi) << 4) | np.where(lo == k, k2, lo)).astype(np.uint8).tobytes()

    jobs[f"direct1 patch {d1['id']} with rows padded to whole bytes only (35 B, not 36)"] = swapped(d1, unpadded)
    jobs[f"enc4bit patch {e4['id']} {e4['rgb']} with ink index {k2} (another corner) for {k}"] = swapped(
        e4, wrong_corner)
    out = {}
    for name, mutated in jobs.items():
        rb = read_back(mutated, patches, fids)
        out[name] = {"caught": not rb["pass"], "failed": rb["failed"]}
    return out


def expected_page(patches: list[dict], fids: list[dict], hw: tuple[int, int]) -> np.ndarray:
    page = np.full((*hw, 3), 255, np.uint8)
    for f in fids:
        x, y, w, h = f["_xywh"]
        page[y:y + h, x:x + w] = 0
    for p in patches:
        x, y = p["_xy"]
        sub = page[y:y + PATCH_H_DOTS, x:x + PATTERN_DOTS]
        sub[patch_raster(p["_pattern"]).astype(bool)] = p["rgb"]
    return page


def verify(job_path: Path, job: bytes, patches: list[dict], fids: list[dict]) -> dict:
    result: dict = {"read_back": read_back(job, patches, fids),
                    "mutation_tests": mutation_tests(patches, fids),
                    "rebuild_byte_identical": sha(emit_job(*plan()[:2])) == sha(job),
                    "manifest_mm_round_trips_to_dots": all(
                        (dots(p["x_mm"]), dots(p["y_mm"])) == p["_xy"] for p in patches) and all(
                        (dots(f["x_mm"]), dots(f["y_mm"])) == f["_xywh"][:2] for f in fids)}
    with tempfile.TemporaryDirectory() as td:
        (fonts := Path(td) / "fonts").mkdir()
        (fonts / "stub.ttf").write_bytes(stub_font())
        img, messages = xl.render(job_path, Path(td) / "ppmraw.out", fonts, "ppmraw")
    r: dict = {"page_hw": list(img.shape[:2]), "render_sha256": sha(img.tobytes()),
               "gpcl6_messages": messages}
    want = expected_page(patches, fids, img.shape[:2])  # gpcl6's A4 is 4960 x 7014 dots, not the PS 7016
    diff = (img != want).any(2)
    covered = np.zeros(diff.shape, bool)
    bad_patches, bad_rings, bar_pos, bar_white = [], [], [], []
    for p in patches:
        x, y = p["_xy"]
        win = (slice(y, y + PATCH_H_DOTS), slice(x, x + PATTERN_DOTS))
        ring = (slice(y - 1, y + PATCH_H_DOTS + 1), slice(x - 1, x + PATTERN_DOTS + 1))
        n_patch = int(diff[win].sum())
        ring_ink = int((img[ring] != 255).any(2).sum() - (img[win] != 255).any(2).sum())
        covered[ring] = True
        if n_patch:
            bad_patches.append({"id": p["id"], "differing_dots": n_patch})
        if ring_ink:
            bad_rings.append({"id": p["id"], "ring_ink_dots": ring_ink})
        if p["rgb"] == [255, 255, 255]:
            bar_white.append(p["id"])
            continue
        bwin = img[y + PATTERN_DOTS - 3:y + PATCH_H_DOTS + 3, x - 3:x + PATTERN_DOTS + 3]
        ink = (bwin != 255).any(2)
        full = np.flatnonzero(ink.sum(1) >= PATTERN_DOTS)
        top = int(full[0]) + y + PATTERN_DOTS - 3 if full.size else None
        mid = ink[3 + SOLID_DOTS // 2]
        left = int(np.flatnonzero(mid)[0]) + x - 3 if mid.any() else None
        if (left, top) != (dots(p["x_mm"]), dots(p["y_mm"]) + PATTERN_DOTS):
            bar_pos.append({"id": p["id"], "render_xy": [left, top],
                            "manifest_bar_xy": [x, y + PATTERN_DOTS]})
    bad_fids = []
    for f in fids:
        x, y, w, h = f["_xywh"]
        covered[y - 1:y + h + 1, x - 1:x + w + 1] = True
        block = img[y:y + h, x:x + w]
        ring_ink = int((img[y - 1:y + h + 1, x - 1:x + w + 1] != 255).any(2).sum()) - w * h
        if (block != 0).any() or ring_ink or (dots(f["x_mm"]), dots(f["y_mm"])) != (x, y):
            bad_fids.append({"id": f["id"], "non_black": int((block != 0).any(2).sum()),
                             "ring_ink": ring_ink})
    r |= {"differing_dots_total": int(diff.sum()), "patches_with_differing_dots": bad_patches,
          "patches_with_ink_in_ring": bad_rings, "bar_positions_disagreeing": bar_pos,
          "bar_position_not_locatable_white_patches": bar_white, "fiducials_bad": bad_fids,
          "ink_outside_objects": int(((img != 255).any(2) & ~covered).sum()),
          "patches_checked": len(patches), "fiducials_checked": len(fids)}
    result["gpcl6_ppmraw"] = r
    rb = result["read_back"]
    result["pass"] = bool(
        rb["pass"] and all(m["caught"] for m in result["mutation_tests"].values())
        and result["rebuild_byte_identical"] and result["manifest_mm_round_trips_to_dots"] and not messages
        and not r["differing_dots_total"]
        and not bad_rings and not bar_pos and not bad_fids and not r["ink_outside_objects"])
    result["command"] = (f"PCLFONTSOURCE=<tmp>/fonts/ {xl.GPCL6} -dNOPAUSE -dBATCH -sDEVICE=ppmraw -r600 "
                         f"-sOutputFile=<tmp>/ppmraw.out {job_path}")
    return result


def counts(patches: list[dict]) -> dict:
    by = Counter((p["method"], p["kind"], p["target"]) for p in patches)
    return {"total": len(patches), "by_method": dict(Counter(p["method"] for p in patches)),
            "by_kind": dict(Counter(p["kind"] for p in patches)),
            "by_encoding": dict(Counter(p["encoding"] for p in patches)),
            "by_target": dict(sorted(Counter(p["target"] for p in patches).items())),
            "by_method_kind_target": {f"{m}/{k}/{t}": n for (m, k, t), n in sorted(by.items())}}


def notes(layout: dict) -> list[str]:
    """The manifest's notes: construction choices, every rounding, what the spec does and does not say."""
    xs, ys = layout["columns_x_dots"], layout["rows_y_dots"]
    nominal_x = [lo + i * SLOT_PITCH_MM[0] for lo, hi in SLOT_X_ZONES_MM
                 for i in range(sum(1 for x in xs if dots(lo) <= x < dots(hi)))]
    nominal_y = [SLOT_Y_ZONE_MM[0] + j * SLOT_PITCH_MM[1] for j in range(len(ys))]
    err = max(abs(n * 25.4 / DPI - v) for n, v in zip(xs + ys, nominal_x + nominal_y))
    fid_nominal = [(f, x, y) for f, x, y, _, _ in FIDUCIALS_MM]
    return [
        "CHANGED 2026-10-05 (round 4, the owner's decision on an outside reviewer's note; the build before it "
        "had sha d7dd4ac9..., 1,749,666 B, 1,147 patches, and passed three independent refutations): ADDED 24 "
        "ENCODING riders, ids 1147-1170 in 24 of the 71 free slots (slot = the same seeded permutation, "
        "pattern seed 41000 + id), method 'default', drawn in the default group (after the page head, among "
        "the default patterns in slot order, before the vector riders: eNoTreatment with the full control "
        "block, before any SetHalftoneMethod), the eight RGB corners each as: kind 'enc4bit' = eIndexedPixel "
        "e4Bit through S9's 16-entry palette (pclxl_bilevel.palette(): index C + 2M + 4Y, entries 8-15 white), "
        "ink = the corner's index, blank = index 0 (white); kind 'encdirect8' = eDirectPixel e8Bit, three "
        "bytes per pixel, blank 255,255,255; kind 'encdirect1' = eDirectPixel e1Bit, three bits per pixel "
        "(channel 255 -> 1), blank 1,1,1. ColorDepth is bits per component and may be e1Bit/e4Bit/e8Bit (X20 "
        "p. 177); an indexed palette is sized by the depth (X20 p. 85). Row padding (X20 p. 179): every row "
        "a multiple of four bytes, no PadBytesMultiple; pixels' components R, G, B back to back from the "
        "most significant bit, so a direct e1Bit row of 93 pixels is 279 bits = 35 bytes padded to 36. Why: "
        "S9 -- the only PCL XL footing measured on paper -- was ONE large e4Bit indexed image through the "
        "16-entry corner palette, while every other S10p patch is a small e1Bit indexed image through a "
        "2-entry palette, so a corner that printed differently here than on S9 would be ambiguous between "
        "the RGB value, the pixel ENCODING and the object size; enc4bit separates encoding from size (S9's "
        "encoding at S10p's size), the direct pair asks whether the engine treats direct pixels like "
        "indexed ones. Every per-patch dict now carries 'encoding' (indexed1 | indexed4 | direct8 | "
        "direct1; 'indexed1' on every earlier patch); every earlier patch keeps its id, slot, value, method, "
        "kind, target, seed and pattern. --verify decodes every image under its own ColorMapping / "
        "ColorDepth with its own unpacker and checks the samples, the RGB through the stream's palette and "
        "the pattern; two more mutated jobs it must refuse: a direct1 patch with 35-byte rows, an enc4bit "
        "patch whose ink index names another corner. The W corner's three encoding riders carry no pattern "
        "in the stream (ink and blank are one sample) and are checked as all-white rasters.",
        "CHANGED 2026-10-05 (second rebuild, after the second independent refutation of the build with sha "
        "f2d2f3fd..., 1,749,666 B): the treatment witness (kind 'treatdefault', 14 patches, ids 1133-1146) "
        "MOVED from just before the eSRGB group to the very head of the page, directly after BeginPage and "
        "before the page head's SetColorSpace / control block and every other object; each witness object "
        "carries its own SetColorSpace eRGB (2-entry palette), SetAdaptiveHalftoning eDisable, "
        "SetColorTrapping eDisable, SetNeutralAxis eProcessBlack and NO SetColorTreatment. Why: ColorTreatment"
        " is persistent graphics state (default eScreenMatch, X21 p. 24; X30 p. 5) and SetColorSpace resets "
        "only the pen and the brush (X20 p. 85), so in the previous order PopGS restored the eNoTreatment the "
        "last vector rider had set and every witness was drawn under eNoTreatment -- null by construction. "
        "The verifier had masked it by clearing the treatment on every SetColorSpace (the generator's own "
        "assumption written into its checker); its state model is now the spec's (graphics state "
        "initialised at BeginPage, X20 p. 47, saved and restored only by PushGS/PopGS, never cleared by "
        "SetColorSpace) and it asserts by stream position that no SetColorTreatment and no SetHalftoneMethod "
        "precedes any witness, plus ten mutated jobs it must refuse (the previous order among them). "
        "Nothing else moved: every patch keeps its id, slot, value, method, kind, seed and pattern; the "
        "other groups keep their order and the eSRGB group stays last. The eSRGB riders still inherit "
        "eNoTreatment through the three PopGS (read back: 8 of 8 under eNoTreatment, halftone default).",
        "CHANGED 2026-10-05, rebuild after the independent refutation of the first S10p build (sha "
        "8de30cfe..., 1,133 patches), three changes, every earlier patch keeping its id, slot, value and "
        "seed: (1) the eSRGB riders moved to the VERY END of the page (after the matrix1x1 PopGS, the last "
        "objects before EndPage) and carry NO SetColorTreatment: ColorSpace 6 is in no spec, "
        "SetColorTreatment's precondition is an eRGB colour space (X21 p. 22), and under ErrorReport "
        "eBackChAndErrPage an M281 error at the first eSRGB rider (then drawn before two thirds of the "
        "sheet) would have aborted the job and lost 748 patches scattered over the page; now an error there"
        " costs the 8 eSRGB patches only. (2) S9's full control block follows EVERY SetColorSpace, in S9's "
        "order: SetColorTreatment eNoTreatment, SetAdaptiveHalftoning eDisable, SetColorTrapping eDisable, "
        "SetNeutralAxis eProcessBlack (eTonerBlack in the tonerblack group), and in the highlpi / matrix1x1"
        " groups SetHalftoneMethod (eHighLPI on text/vector/raster; the 1x1 matrix with its 4 embedded "
        "bytes); the default-method groups carry no SetHalftoneMethod. Why: X30 gives SetColorTrapping (p. "
        "10) and SetNeutralAxis (p. 11) the same 'for the current color space' postcondition as "
        "SetColorTreatment (X21 p. 22), and SetAdaptiveHalftoning 'for the current object' (X30 p. 9); the "
        "first build set adaptive, trapping and neutral axis once per page and the halftone method / "
        "eTonerBlack once per group, then re-sent only SetColorTreatment after its 1,130 SetColorSpace "
        "calls. (3) Added a treatment witness (an outside reviewer's note, by the owner): kind "
        "'treatdefault', method 'default', 14 patches = the eight corners, the single-toner mids "
        "(0,192,192), (192,0,192), (192,192,0) and the overlap mids (0,0,192), (0,192,0), (192,0,0), eRGB "
        "with the control block MINUS SetColorTreatment (the engine's default treatment, whatever it is; "
        "the default graphics state says eScreenMatch, X21 p. 24, X30 p. 5), ids 1133-1146 in free slots, "
        "emitted right before the eSRGB group; they test whether eNoTreatment does anything at all. "
        "--verify now checks every object's full control state and its exact control sequence against "
        "its group.",
        "Each patch is ONE image: 93 x 117 dots = the 93 x 93 pattern square over the 93 x 24 solid "
        "bar, one ReadImage block, e1Bit (leftmost pixel = most significant bit, as the gpcl6 render "
        "shows), rows of 12 bytes; palette [255,255,255, r,g,b]. The encoding riders: enc4bit rows of 48 "
        "bytes (93 nibbles, left pixel in the high nibble, as S9) through S9's 48-byte palette; encdirect8 "
        "rows of 280 bytes (279 + 1 pad), no palette; encdirect1 rows of 36 bytes (279 bits + 5 zero bits + "
        "1 zero byte), no palette.",
        "Vector patches: the same 117 x 93 dots as filled Rectangles (one per horizontal run of inked "
        "cells in a cell row, 1,925 for the eight patterns, plus one per bar), NullPen, brush = the RGB; "
        "their seed and pattern_sha256 are real (the full pattern is drawn). After each vector patch the "
        "brush is set back to RGB black: gpcl6 10.08 keeps the brush across SetColorSpace (X20 p. 85 "
        "says SetColorSpace resets it) and, under the default ROP3 252, a white brush rendered every "
        "later image white (measured 2026-10-05 on the first build: 737 patches blank).",
        "Positions: every x/y is rounded to whole 600-dpi dots, floor(mm*600/25.4 + 0.5), and the "
        "manifest carries the rounded value back in mm (n*25.4/600, 6 decimals), so "
        f"round(x_mm*600/25.4) is the dot. Max |rounded - nominal| over the slot grid {err:.4f} mm. "
        f"Slot columns x dots {xs}; slot rows y dots {ys}. Fiducial nominal (id, x mm, y mm) "
        f"{fid_nominal}; w/h drawn as round(w_mm*600/25.4) dots (3.0 mm = 71, 6.0 mm = 142). The zone "
        "edges round too: 12 mm -> 283 dots = 11.980 mm, 118 mm -> 2787 dots = 117.983 mm, so the first "
        "row/column and the right zone's first column start up to 0.02 mm (0.47 dot) before the nominal "
        "edge. F0-F3 are 3 x 3 mm squares diagonally outside the four corners of the slot area (1 mm "
        "clear of it); F4, the 3 x 6 mm orientation bar, stands in the left margin directly below F0 "
        "(x as F0, y 12 mm, 23 dots below F0 and 23 dots left of the first slot column).",
        f"Slots: {layout['slots']} ({len(xs)} columns x {len(ys)} rows, pitch 5.5 x 6.5 mm; a slot "
        f"holds the whole 93 x 117-dot patch inside its zone), {layout['used']} used, {layout['empty']} "
        f"empty (row-major slot indices {layout['empty_slots']}); position replicates dropped for lack "
        f"of slots: {layout['replicates_dropped']}. Patch id k sits in slot "
        "default_rng(41).permutation(n_slots)[k]; its pattern seed is 41000 + k. Neighbouring patches "
        "are 36 or 37 dots apart, so the 1-dot ring of every patch is white.",
        "Emission order: BeginPage, the treatment witness, the page head (SetColorSpace eRGB + the default "
        "control block, S9's), the five fiducials, the default-method patterns with the encoding riders "
        "among them (one group, slot order), the vector riders, the "
        "tonerblack riders, the highlpi group, the matrix1x1 group, the eSRGB riders, EndPage; inside a "
        "group, slot order (top to bottom, left to right). tonerblack, highlpi and matrix1x1 are each "
        "wrapped in PushGS / ... / PopGS; the treatment witness and the eSRGB riders are not wrapped.",
        "Control block after EVERY SetColorSpace (fiducials, patches, vector riders), S9's order (under "
        "the spec the settings persist, X21 p. 24 / X30 p. 5, so after the first block the repeats are "
        "redundant; they stay so that no reading of the per-colour-space postconditions leaves an object "
        "without them): "
        "SetColorTreatment eNoTreatment (omitted for treatdefault and eSRGB), SetAdaptiveHalftoning "
        "eDisable, SetColorTrapping eDisable, SetNeutralAxis eProcessBlack (eTonerBlack for tonerblack), "
        "then SetHalftoneMethod in highlpi (eHighLPI x3) and matrix1x1 (1x1, threshold 0x80) only. One "
        "SetColorSpace per object.",
        "Method and treatment state: the treatment witness is drawn before ANY SetColorTreatment and ANY "
        "SetHalftoneMethod on the page (BeginPage defaults, X20 p. 47); the default-method patterns, vector "
        "and tonerblack riders before any SetHalftoneMethod, so they are default whatever the firmware does "
        "with PushGS/PopGS. The eSRGB riders (method 'default') come AFTER the matrix1x1 PopGS, as the "
        "eSRGB-last rule requires: their halftone is the default and their treatment eNoTreatment only "
        "because PopGS restores the graphics state (HalftoneMethod and ColorTreatment are graphics-state "
        "attributes, X20 p. 75, X21 p. 24, X30 p. 5; PopGS X20 p. 79-80); there is no 'set default' value to "
        "restore the halftone explicitly, and whether a treatment means anything under ColorSpace 6 no spec "
        "says. If the firmware did not restore the halftone, an eSRGB rider would carry the matrix1x1 "
        "group's (whose matrix S9b found ignored). "
        "gpcl6 accepts PushGS/PopGS, SetHalftoneMethod, the 1x1 matrix, SetNeutralAxis, trapping and "
        "adaptive halftoning, but its ppmraw render cannot show their effect.",
        "X30 HalftoneMethod enumerations (Appendix G p. 31, SetHalftoneMethod p. 7-8): eHighLPI 0 "
        "(class 1.1), eMediumLPI 1 and eLowLPI 2 (class 3.0). X30 p. 5 gives the per-object defaults "
        "text HighLPI, vector MediumLPI, raster LowLPI: a 'default' raster patch is nominally eLowLPI, "
        "a 'default' vector patch eMediumLPI. eMediumLPI/eLowLPI are NOT probed explicitly (three "
        "methods by design).",
        "tonerblack riders: (0,0,0), (16,16,16) and the eight corners = 10 patches; (0,0,0) is a corner, "
        "so it is drawn twice under eTonerBlack (the literal list; the second is a position replicate).",
        "treatdefault riders (the treatment witness): 14 patches, the eight corners plus (0,192,192), "
        "(192,0,192), (192,192,0), (0,0,192), (0,192,0), (192,0,0), drawn first on the page under the "
        "BeginPage default treatment (eScreenMatch); compare each with its eNoTreatment twin (the "
        "default-method pattern of the same RGB; the 192 mids are on the sweep grid). Both are drawn before "
        "any SetHalftoneMethod, so treatment is the one control-state difference between them.",
        "eSRGB = ColorSpace 6: not in X20/X21/X30 (they list eGray 1, eRGB 2); gpcl6 10.08 accepts 6 "
        "and refuses 3-5 and 7-8, and renders 6 like eRGB. Whether the M281 accepts it is a printer "
        "question; if it raises an error, ErrorReport eBackChAndErrPage asks for an error page and the "
        "job may stop there, which now is after every other patch (the eSRGB group is last).",
        "Target label = the channels below 64 (C = R low, M = G low, Y = B low); W = none. Value grid: "
        "C/M/Y singles own 0 x foreign 255,240..128 (81) + own 16/32/48 (3); CM/CY/MY free channel "
        "255,240..128 x both zero channels 0/16/32 (27); CMY 0/16/32; W. 337 values x 3 methods.",
        "gpcl6's A4 page at 600 dpi is 4960 x 7014 dots (the PostScript jobs' is 4960 x 7016); nothing "
        "is placed below y = 285 mm + 4.95 mm, so the two rows do not matter.",
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path,
                    help="job path (.pclxl); <stem>.manifest.json is written beside it")
    ap.add_argument("--verify", action="store_true", help="decode the stream, render with gpcl6, compare")
    args = ap.parse_args()
    patches, fids, layout = plan()
    job = emit_job(patches, fids)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(job)
    manifest = {
        "tag": TAG, "dpi": DPI, "page_mm": list(PAGE_MM), "bytes": len(job), "sha256": sha(job),
        "fiducials": [{k: v for k, v in f.items() if not k.startswith("_")} for f in fids],
        "patch_px": {"pattern_dots": PATTERN_DOTS, "solid_dots": SOLID_DOTS, "cell_dots": CELL_DOTS,
                     "cells": CELLS},
        "patches": [{k: v for k, v in p.items() if not k.startswith("_")} for p in patches],
        "layout_seed": LAYOUT_SEED,
        "excluded_zones_mm": {
            "engine_rendering_stripe_x": [98.0, 118.0], "top_y": [0.0, 12.0], "bottom_y": [285.0, 297.0],
            "left_x": [0.0, 12.0], "right_x": [198.0, 210.0],
            "note": "patch slots only inside x [12, 98] U [118, 198], y [12, 285]; the measured print clip "
                    "is ~4.2 mm on every edge and the 3 mm edge strip lies inside it; the fiducials sit "
                    "deliberately in the margins just outside the slot area, never in the stripe"},
        "notes": notes(layout),
        "sources": SOURCES,
        "counts": counts(patches),
        "generator": " ".join(["PYTHONPATH=src:.", sys.executable, *sys.argv]),
        "verification": verify(args.out, job, patches, fids) if args.verify else "not run",
    }
    args.out.with_name(args.out.stem + ".manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{args.out}: {len(job)} B sha {manifest['sha256']}")
    v = manifest["verification"]
    if isinstance(v, dict):
        v = {k: v[k] for k in v if k != "read_back"} | {
            "read_back": {k: v["read_back"][k] for k in v["read_back"] if k != "gs_sequence_runs"}}
    print(json.dumps(v, indent=1))
    print(json.dumps(manifest["counts"], indent=1))


if __name__ == "__main__":
    main()
