"""e041 S10p2 — the S10p RGB probe rebuilt as a few large indexed images, for the M281's PCL XL interpreter.

S10p (pclxl_probe.py: 1,168 small images each with its own SetColorSpace and control block, PushGS/PopGS,
vector Rectangles, ColorSpace 6, eDirectPixel images) rendered perfectly in gpcl6, but the M281 first spent
two minutes on it and discarded the page without an error sheet, then crashed with "49 SERVICE ERROR" and had
to be power-cycled.  S10p2 carries the same scientific content in the structure of the two PCL XL jobs that
DID print on this engine (S9, S9b: one eRGB indexed image in 64-row ReadImage blocks after S9's preamble):
337 swept RGB values x three halftone methods (1,011 patterns) plus the 14-patch treatment witness, as
thirteen e8Bit indexed images.

Layout: the S10p slot grid (29 columns x 42 rows, 5.5 x 6.5 mm pitch, x in [12, 98] U [118, 198] mm, y in
[12, 285] mm).  Slot row 0 = the witness band, ONE image drawn first after BeginPage with SetColorSpace,
SetAdaptiveHalftoning, SetColorTrapping, SetNeutralAxis and NO SetColorTreatment.  Then the fiducials as three
e8Bit indexed images (entry 1 black): F0+F1 in one strip image, F4 alone, F2+F3 in one strip image.  Then nine
band images of four slot rows each (slot rows 1-36), each spanning the band's full slot area (both zones, the
white stripe column and the white gaps between patches), methods by band D,H,M, M,D,H, H,M,D, drawn by
METHOD: the three default bands, the three highlpi bands, the three matrix bands.  EVERY image after the
witness carries S9's preamble in S9's order: SetColorSpace (eRGB + its 768-byte palette), SetColorTreatment
eNoTreatment, SetAdaptiveHalftoning eDisable, SetColorTrapping eDisable, SetNeutralAxis eProcessBlack, then
for a highlpi band SetHalftoneMethod eHighLPI x3 (S9's bytes), for a matrix band the 1x1 matrix (S9b's bytes,
one 4-byte download per matrix band), then SetCursor and the image; fiducials and default bands carry no
SetHalftoneMethod.  So the state at every image is its band's method whether the firmware keeps these
settings as graphics state or resets them on SetColorSpace (X21 p. 22, X30 p. 9-11: "the current color
space").  A patch = the 93 x 93-dot seeded 31 x 31-cell pattern over a 93 x 24 solid bar, its colour one
palette entry of its band's image (entry 0 white, the band's colours in slot order, the rest white, 768
bytes).  Slot rows 37-41 are empty.

--only M (the fallback form, S10p2M; printed only if the full sheet fails): the 84 magenta sweep values plus
the C corner and W as controls under each method (258 patterns), one band image per method in page order
default (slot rows 1-4), highlpi (5-8), matrix (9-12), and the witness reduced to the M corner, (192,0,192)
and the C corner; same slot pitch, zones, fiducials, preamble rule and manifest contract (own ids from 0).

The two sheets' plans live in pclxl_probe_sheets.py; sweep, pattern, slot-grid, rounding and control-byte
helpers in pclxl_probe.py, the encoders, tables and gpcl6 render in pclxl_bilevel.py.  Sources: X20 = PCL XL
Feature Reference Protocol Class 2.0 rev p2.2, X21 = Class 2.1 Supplement rev 1.0, X30 = Class 3.0
Supplement rev 0.90 (pages = printed footers).

--verify: (a) the stream read back by this file's own tokenizer and interpreter (operator sequence, every
palette 768 bytes, every image e8Bit indexed with DestinationSize == source size, ReadImage blocks of 64 rows
with embedded lengths = rows x the four-byte-rounded stride of X20 p. 179, zero padding, every control
operator's tokens equal to S9's / S9b's, the control and halftone state in force at every image under BOTH
models -- persistent graphics state, and reset on SetColorSpace --, the decoded rasters through their
palettes against the manifest); (b) a gpcl6 ppmraw render at 600 dpi against the page the manifest
describes, dot for dot, rings white, no ink outside objects; (c) pattern shas from seeds; (d) zones,
overlaps, fiducial clearance; (e) two builds byte-identical; (f) the novelty list against S9 and S9b,
tokenized by the same parser (tokens, operator bigrams, structure).  --smoke DIR adds (g): the synthetic scan
(measure/e041_probe_synth.py: posed, blur 3, noise 8) read by measure/e041_probe_readout.py; the TIFF is
deleted afterwards.

    PYTHONPATH=src:. env/bin/python experiments/041-m281-screen-routes/pclxl_probe_banded.py \\
        --out experiments/041-m281-screen-routes/build/S10p2-pclxl-rgb-probe.pclxl --verify --smoke <work dir>
    PYTHONPATH=src:. env/bin/python experiments/041-m281-screen-routes/pclxl_probe_banded.py --only M \\
        --out experiments/041-m281-screen-routes/build/S10p2M-pclxl-rgb-probe-M.pclxl --verify --smoke <work dir>
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Protocol

import numpy as np

import pclxl_bilevel as xl
from pcl_planar import UEL, sha, stub_font
from pclxl_bilevel import (ATTR, ATTR_UBYTE, E, EMBED, EMBED_BYTE, OP, SINT16_XY, UBYTE_ARRAY, UINT16, op,
                           stream_body, u16, ub, xy)
from pclxl_probe import (CELL_DOTS, CELLS, CONTROL, DPI, LAYOUT_SEED, METHODS, PAGE_MM, PATCH_H_DOTS,
                         PATTERN_DOTS, PATTERN_SEED_BASE, SLOT_PITCH_MM, SLOT_X_ZONES_MM, SLOT_Y_ZONE_MM,
                         SOLID_DOTS, dots, mm, patch_raster, pattern, row_bytes)
from pclxl_probe_sheets import FULL, PALETTE_ENTRIES, SHEETS, Sheet, plan

REPO = Path(__file__).resolve().parents[2]
S9_JOBS = {"S9": "S9-pclxl-bilevel.pclxl", "S9b": "S9b-pclxl-dither1x1.pclxl"}  # default: beside --out
S9_COMMENT = b"sheet F bilevel indexed RGB"
BLOCK_ROWS = xl.BLOCK_ROWS  # 64, as S9
HEAD_OPS = ["SetColorTreatment", "SetAdaptiveHalftoning", "SetColorTrapping", "SetNeutralAxis"]
WITNESS_OPS = HEAD_OPS[1:]


# ------------------------------------------------------------------------------------------------ emit

class Frame(Protocol):
    """What the PJL frame and the stream header take from a sheet (Sheet, or another sheet's record)."""
    job_name: str
    comment: bytes


def image_bytes(img: dict) -> bytes:
    """SetColorSpace eRGB + the image's 768-byte e8Bit palette (array length as uint16: 768 > 255), the
    image's control block (the witness: adaptive, trapping, neutral; every other image S9's four + its band's
    SetHalftoneMethod if not default), SetCursor, BeginImage eIndexedPixel e8Bit (DestinationSize = source
    size),
    ReadImage blocks of BLOCK_ROWS rows eNoCompression (rows padded to four bytes, X20 p. 179), EndImage."""
    x, y, w, h = img["xywh"]
    pal = img["palette"].tobytes()
    s = ub(E["eRGB"], "ColorSpace") + ub(E["e8Bit"], "PaletteDepth")
    s += bytes((UBYTE_ARRAY, UINT16)) + struct.pack("<H", len(pal)) + pal
    s += bytes((ATTR_UBYTE, ATTR["PaletteData"]))
    s += op("SetColorSpace") + b"".join(CONTROL[c] for c in img["block"])
    s += xy(x, y, "Point", SINT16_XY) + op("SetCursor")
    s += ub(E["eIndexedPixel"], "ColorMapping") + ub(E["e8Bit"], "ColorDepth")
    s += u16(w, "SourceWidth") + u16(h, "SourceHeight") + xy(w, h, "DestinationSize") + op("BeginImage")
    data = np.pad(img["raster"], ((0, 0), (0, row_bytes(w, 8) - w)))
    for start in range(0, h, BLOCK_ROWS):
        block = data[start:start + BLOCK_ROWS].tobytes()
        s += u16(start, "StartLine") + u16(min(BLOCK_ROWS, h - start), "BlockHeight")
        s += ub(E["eNoCompression"], "CompressMode") + op("ReadImage")
        s += struct.pack("<BI", EMBED, len(block)) + block
    return s + op("EndImage")


def emit_job(images: list[dict], sheet: Frame) -> bytes:
    """S9's session/page frame; the images in plan order, each with its own preamble (image_bytes)."""
    s = bytearray(xy(DPI, DPI, "UnitsPerMeasure") + ub(E["eInch"], "Measure")
                  + ub(E["eBackChAndErrPage"], "ErrorReport") + op("BeginSession"))
    s += ub(E["eDefaultDataSource"], "SourceType") + ub(E["eBinaryLowByteFirst"], "DataOrg")
    s += op("OpenDataSource")
    s += ub(E["ePortraitOrientation"], "Orientation") + ub(E["eA4Paper"], "MediaSize")
    s += ub(E["eDefaultSource"], "MediaSource") + op("BeginPage")
    for img in images:
        s += image_bytes(img)
    s += op("EndPage") + op("CloseDataSource") + op("EndSession")
    name = sheet.job_name.encode()
    header = b") HP-PCL XL;3;0;Comment e041 %s %s\n" % (name, sheet.comment)
    pjl = (b'@PJL JOB NAME="%s"\r\n@PJL SET RESOLUTION=600\r\n@PJL SET BITSPERPIXEL=1\r\n'
           b"@PJL ENTER LANGUAGE=PCLXL\r\n" % name)
    return UEL + pjl + header + bytes(s) + UEL + b'@PJL EOJ NAME="%s"\r\n' % name + UEL


# ------------------------------------------------------------------------------------------------ read back

TYPE_FMT = {0: "B", 1: "H", 2: "I", 3: "h", 4: "i", 5: "f"}
TYPE_NAME = {0xC0: "ubyte", 0xC1: "uint16", 0xC2: "uint32", 0xC3: "sint16", 0xC4: "sint32", 0xC5: "real32",
             0xC8: "ubyte_array", 0xC9: "uint16_array", 0xD0: "ubyte_xy", 0xD1: "uint16_xy",
             0xD3: "sint16_xy", 0xE0: "ubyte_box", 0xE1: "uint16_box"}


def tokenize(body: bytes) -> list[dict]:
    """This file's own reading of a little-endian PCL XL stream body (X20 Appendix B-D): one dict per
    operator with its attributes, their data types (array length type included) and embedded data."""
    names, anames = {v: k for k, v in OP.items()}, {v: k for k, v in ATTR.items()}
    ops: list[dict] = []
    attrs: dict = {}
    types: dict = {}
    pending = None
    i = 0
    while i < len(body):
        t = body[i]
        i += 1
        base, sub = t & 0xF8, t & 7
        if base in (0xC0, 0xC8, 0xD0, 0xE0) and sub <= 5:
            length_type = None
            if base == 0xC8:
                length_type = body[i]
                if length_type not in (0xC0, 0xC1):
                    raise ValueError(f"array length type {length_type:#04x} at {i}")
                lf = "<" + TYPE_FMT[length_type & 7]
                (n,) = struct.unpack_from(lf, body, i + 1)
                i += 1 + struct.calcsize(lf)
            else:
                n = {0xC0: 1, 0xD0: 2, 0xE0: 4}[base]
            f = "<%d%s" % (n, TYPE_FMT[sub])
            vals = struct.unpack_from(f, body, i)
            i += struct.calcsize(f)
            value = (bytes(vals) if base == 0xC8 and sub == 0 else vals[0] if base == 0xC0 else list(vals))
            pending = (value, TYPE_NAME.get(t, hex(t)), TYPE_NAME.get(length_type) if length_type else None)
        elif t == ATTR_UBYTE:
            if pending is None:
                raise ValueError(f"attribute id without a value at {i - 1}")
            a = anames.get(body[i], body[i])
            attrs[a], types[a] = pending[0], pending[1:]
            pending, i = None, i + 1
        elif t in (EMBED, EMBED_BYTE):
            lf = "<I" if t == EMBED else "<B"
            (n,) = struct.unpack_from(lf, body, i)
            i += struct.calcsize(lf)
            ops[-1]["data"] = body[i:i + n]
            ops[-1]["embed"] = "dataLength" if t == EMBED else "dataLengthByte"
            i += n
        elif 0x41 <= t <= 0xBF:
            ops.append({"op": names.get(t, f"tag {t:#04x}"), "attrs": attrs, "types": types, "data": b"",
                        "embed": None})
            attrs, types = {}, {}
        else:
            raise ValueError(f"unexpected tag {t:#04x} at stream offset {i - 1}")
    if attrs or pending is not None:
        raise ValueError("attribute list left without an operator")
    return ops


PAGE_DEFAULT = {"treatment": "page-default", "adaptive": "page-default", "trapping": "page-default",
                "neutral": "page-default", "halftone": "default"}
STATE_NAMES = {"SetColorTreatment": ("treatment", "ColorTreatment", {0: "eNoTreatment", 1: "eScreenMatch"}),
               "SetAdaptiveHalftoning": ("adaptive", "AllObjectTypes", {0: "eDisable", 1: "eEnable"}),
               "SetColorTrapping": ("trapping", "AllObjectTypes", {0: "eDisable"}),
               "SetNeutralAxis": ("neutral", "AllObjectTypes", {0: "eTonerBlack", 1: "eProcessBlack"})}
CONTROL_OPS = (*STATE_NAMES, "SetHalftoneMethod")


def halftone_name(o: dict) -> str:
    a = o["attrs"]
    if a == {"DitherMatrixSize": [1, 1], "DitherMatrixDataType": E["eUByte"],
             "DitherMatrixDepth": E["e8Bit"]} and o["data"] == b"\x80\x00\x00\x00":
        return "matrix1x1"
    if a == {k: E["eHighLPI"] for k in ("TextObjects", "VectorObjects", "RasterObjects")}:
        return "highlpi"
    return f"other {a} {o['data'].hex()}"


def interpret(ops: list[dict], reset_on_space: bool = False) -> list[dict]:
    """Images with what is in force at their BeginImage: colour space and palette, the control state
    (graphics state initialised at BeginPage, X20 p. 47; set only by its own operator; no PushGS/PopGS
    is expected here and any would show up in the operator check), the cursor, the control operators since
    the image's SetColorSpace, and the ReadImage blocks.  reset_on_space: the other reading of X21 p. 22 /
    X30 p. 9-11, every control and the halftone method back to the page default at each SetColorSpace."""
    images: list[dict] = []
    gs: dict = dict(PAGE_DEFAULT)
    space: dict = {}
    cursor = None
    since_space: list[str] = []
    img: dict | None = None
    for k, o in enumerate(ops):
        n, a = o["op"], o["attrs"]
        if n in CONTROL_OPS:
            since_space.append(n)
        if n == "BeginPage":
            gs = dict(PAGE_DEFAULT)
        elif n == "SetColorSpace":
            space = {"ColorSpace": a.get("ColorSpace"), "PaletteDepth": a.get("PaletteDepth"),
                     "palette": a.get("PaletteData"), "palette_type": o["types"].get("PaletteData")}
            since_space = []
            if reset_on_space:
                gs = dict(PAGE_DEFAULT)
        elif n in STATE_NAMES:
            key, attr, table = STATE_NAMES[n]
            gs[key] = table.get(a[attr], f"{attr}={a[attr]}") if set(a) == {attr} else f"other {a}"
        elif n == "SetHalftoneMethod":
            gs["halftone"] = halftone_name(o)
        elif n == "SetCursor":
            cursor = tuple(a["Point"])
        elif n == "BeginImage":
            img = {"begin": a, "cursor": cursor, "space": dict(space), "state": dict(gs), "op_index": k,
                   "since_space": list(since_space), "blocks": []}
        elif n == "ReadImage" and img is not None:
            img["blocks"].append({**a, "data": o["data"]})
        elif n == "EndImage" and img is not None:
            images.append(img)
            img = None
    return images


def decode(img: dict) -> np.ndarray | str:
    """(h, w) samples of one indexed image, or why not: ColorDepth bits per pixel (e1Bit/e4Bit/e8Bit,
    X20 p. 177), rows MSB-first, each row padded with zeros to a multiple of four bytes (X20 p. 179);
    blocks contiguous from StartLine 0, each embedded length = BlockHeight x stride, CompressMode 0."""
    b = img["begin"]
    w, h = b["SourceWidth"], b["SourceHeight"]
    bits = {E["e1Bit"]: 1, E["e4Bit"]: 4, E["e8Bit"]: 8}.get(b["ColorDepth"])
    if b.get("ColorMapping") != E["eIndexedPixel"] or bits is None:
        return f"ColorMapping {b.get('ColorMapping')} ColorDepth {b['ColorDepth']}"
    stride = 4 * -(-w * bits // 32)
    start = 0
    for blk in img["blocks"]:
        if blk["StartLine"] != start or blk.get("CompressMode") != E["eNoCompression"]:
            return (f"block at StartLine {blk['StartLine']} (expected {start}) "
                    f"CompressMode {blk.get('CompressMode')}")
        if len(blk["data"]) != blk["BlockHeight"] * stride:
            return f"block {start}: {len(blk['data'])} B for {blk['BlockHeight']} rows of {stride} B"
        start += blk["BlockHeight"]
    if start != h:
        return f"blocks cover {start} of {h} rows"
    raw = np.frombuffer(b"".join(k["data"] for k in img["blocks"]), np.uint8)
    bitmat = np.unpackbits(raw.reshape(h, stride), axis=1)
    if bitmat[:, w * bits:].any():
        return "nonzero row padding"
    return (bitmat[:, :w * bits].reshape(h, w, bits) @ (1 << np.arange(bits - 1, -1, -1))).astype(np.uint8)


def expected_ops(images: list[dict]) -> list[str]:
    """The operator sequence the brief demands, from the plan's image kinds and methods alone: the witness
    first with its three controls, the fiducials, then the bands by method (METHODS order); every image after
    the witness S9's four controls after its SetColorSpace, plus SetHalftoneMethod for a non-default band."""
    def one(img: dict, controls: list[str]) -> list[str]:
        h = img["xywh"][3]
        return (["SetColorSpace", *controls, "SetCursor", "BeginImage"] + ["ReadImage"] * -(-h // BLOCK_ROWS)
                + ["EndImage"])
    witness = [i for i in images if i["kind"] == "witness"]
    fids = [i for i in images if i["kind"] == "fiducial"]
    seq = ["BeginSession", "OpenDataSource", "BeginPage"]
    seq += one(witness[0], WITNESS_OPS)
    for f in fids:
        seq += one(f, HEAD_OPS)
    for method in METHODS:
        controls = HEAD_OPS + ([] if method == "default" else ["SetHalftoneMethod"])
        seq += [o for b in images if b["kind"] == "band" and b["method"] == method for o in one(b, controls)]
    return seq + ["EndPage", "CloseDataSource", "EndSession"]


def want_state(img: dict) -> dict:
    treated = "page-default" if img["kind"] == "witness" else "eNoTreatment"
    return {"treatment": treated, "adaptive": "eDisable", "trapping": "eDisable", "neutral": "eProcessBlack",
            "halftone": img["method"]}


def want_rgb(img: dict, patches: list[dict], fids: list[dict]) -> np.ndarray:
    """The image rectangle's RGB as the MANIFEST states it (positions from x_mm/y_mm, patterns from seeds)."""
    x, y, w, h = img["xywh"]
    out = np.full((h, w, 3), 255, np.uint8)
    if img["kind"] == "fiducial":
        for f in fids:
            if f["id"] in img["members"]:
                fx, fy = dots(f["x_mm"]), dots(f["y_mm"])
                out[fy - y:fy - y + dots(f["h_mm"]), fx - x:fx - x + dots(f["w_mm"])] = f["rgb"]
        return out
    for p in patches:
        if p["band"] == img["band"]:
            px, py = dots(p["x_mm"]) - x, dots(p["y_mm"]) - y
            pat = np.random.default_rng(p["seed"]).integers(0, 2, size=(CELLS, CELLS), dtype=np.uint8)
            ink = np.vstack([np.kron(pat, np.ones((CELL_DOTS, CELL_DOTS), np.uint8)),
                             np.ones((SOLID_DOTS, PATTERN_DOTS), np.uint8)]).astype(bool)
            out[py:py + PATCH_H_DOTS, px:px + PATTERN_DOTS][ink] = p["rgb"]
    return out


def control_tokens(ops: list[dict]) -> list[tuple]:
    return [(o["op"], list(o["attrs"].items()), sorted(o["types"].items()), o["data"]) for o in ops
            if o["op"] in CONTROL_OPS]


def controls_vs_s9(ops: list[dict], refs: dict[str, bytes]) -> dict:
    """Every control operator of the job token-identical to one in S9 or S9b, and every control byte string
    the emitter uses present in S9's (or, the matrix, S9b's) stream body."""
    ref_tok = [t for v in refs.values() for t in control_tokens(tokenize(stream_body(v)))]
    mine = control_tokens(ops)
    bodies = {k: stream_body(v) for k, v in refs.items()}
    in_body = {c: next((k for k, b in bodies.items() if CONTROL[c] in b), None) for c in CONTROL_NAME}
    return {"control_operators": len(mine), "not_in_S9_or_S9b": sum(1 for t in mine if t not in ref_tok),
            "control_bytes_found_in": in_body,
            "pass": all(t in ref_tok for t in mine) and all(in_body.values())}


def read_back(job: bytes, images: list[dict], patches: list[dict], fids: list[dict],
              refs: dict[str, bytes]) -> dict:
    body = stream_body(job)
    ops = tokenize(body)
    names = [o["op"] for o in ops]
    got = interpret(ops)
    got_reset = interpret(ops, reset_on_space=True)
    problems: list[str] = []
    if [n for n, _, _ in xl.parse(body)] != names:
        problems.append("pclxl_bilevel.parse and this tokenizer disagree on the operator sequence")
    spaces = [o for o in ops if o["op"] == "SetColorSpace"]
    palettes_ok = all(o["attrs"].get("ColorSpace") == E["eRGB"]
                      and o["attrs"].get("PaletteDepth") == E["e8Bit"]
                      and len(o["attrs"].get("PaletteData", b"")) == 3 * PALETTE_ENTRIES for o in spaces)
    per_image = []
    for plan_img, g, gr in zip(images, got, got_reset):
        x, y, w, h = plan_img["xywh"]
        b = g["begin"]
        heights = [k["BlockHeight"] for k in g["blocks"]]
        raster = decode(g)
        row = {"name": plan_img["name"], "cursor": list(g["cursor"]),
               "wh": [b["SourceWidth"], b["SourceHeight"]],
               "blocks": len(heights), "block_heights": sorted(set(heights)),
               "embedded_bytes_per_full_block": BLOCK_ROWS * row_bytes(w, 8),
               "state": g["state"], "state_reset_on_SetColorSpace": gr["state"],
               "controls_after_SetColorSpace": g["since_space"]}
        checks = {
            "position_size": g["cursor"] == (x, y) and [b["SourceWidth"], b["SourceHeight"]] == [w, h],
            "indexed_e8Bit": b.get("ColorMapping") == E["eIndexedPixel"] and b["ColorDepth"] == E["e8Bit"],
            "destination_equals_source": b.get("DestinationSize") == [b["SourceWidth"], b["SourceHeight"]],
            "blocks_of_64": all(v == BLOCK_ROWS for v in heights[:-1]) and 0 < heights[-1] <= BLOCK_ROWS,
            "state_persistent": g["state"] == want_state(plan_img),
            "state_reset_on_SetColorSpace": gr["state"] == want_state(plan_img),
            "palette_768_uint16_length": g["space"]["palette"] is not None
            and len(g["space"]["palette"]) == 768 and g["space"]["palette_type"] == ("ubyte_array", "uint16"),
        }
        if isinstance(raster, str):
            checks["decoded"] = False
            problems.append(f"{plan_img['name']}: {raster}")
        else:
            pal = np.frombuffer(g["space"]["palette"], np.uint8).reshape(-1, 3)
            used = np.unique(raster)
            n_members = len(plan_img["members"]) if plan_img["kind"] != "fiducial" else 1
            want = want_rgb(plan_img, patches, fids)
            background = plan_img["kind"] != "fiducial" or bool((want == 255).all(2).any())
            checks["decoded"] = True
            checks["rgb_equals_manifest"] = bool(np.array_equal(pal[raster], want))
            checks["palette_entry0_white_rest_white"] = bool((pal[0] == 255).all()
                                                             and (pal[n_members + 1:] == 255).all())
            want_used = list(range(0 if background else 1, n_members + 1))
            checks["indices_used_0_to_n"] = used.tolist() == want_used
            row["palette_entries_used"] = int(used.size)
            if plan_img["kind"] != "fiducial":
                shas = {}
                for p in patches:
                    if p["band"] == plan_img["band"]:
                        px, py = dots(p["x_mm"]) - x, dots(p["y_mm"]) - y
                        sub = raster[py:py + PATTERN_DOTS, px:px + PATTERN_DOTS]
                        cells = (sub[1::CELL_DOTS, 1::CELL_DOTS] != 0).astype(np.uint8)
                        shas[p["id"]] = sha(cells.tobytes()) == p["pattern_sha256"]
                checks["stream_pattern_shas"] = all(shas.values()) and len(shas) == len(plan_img["members"])
        row["checks"] = checks
        if not all(checks.values()):
            problems.append(f"{plan_img['name']}: failed {[k for k, v in checks.items() if not v]}")
        per_image.append(row)
    controls = controls_vs_s9(ops, refs)
    verdicts = {
        "operator_sequence_exact": names == expected_ops(images),
        "controls_token_identical_to_S9_S9b": controls["pass"],
        "images_counted": len(got) == len(images),
        "every_palette_768_eRGB_e8Bit": palettes_ok and len(spaces) == len(images),
        "every_image_ok": all(all(r["checks"].values()) for r in per_image),
        "no_problems": not problems,
    }
    return {"operators": len(names), "operator_counts": dict(sorted(Counter(names).items())),
            "controls_vs_S9": controls, "images": per_image, "verdicts": verdicts,
            "pass": all(verdicts.values()), "problems": problems,
            "listing": listing(ops)}


def listing(ops: list[dict]) -> list[str]:
    """Operator sequence with ReadImage runs and long arrays summarised."""
    out: list[str] = []
    for o in ops:
        if o["op"] == "ReadImage":
            if out and out[-1].startswith("ReadImage"):
                n = int(out[-1].split(" x ")[1].split()[0]) + 1
                out[-1] = f"ReadImage x {n} (last BlockHeight {o['attrs']['BlockHeight']})"
            else:
                out.append(f"ReadImage x 1 (last BlockHeight {o['attrs']['BlockHeight']})")
            continue
        shown = {k: (f"<{len(v)} B>" if isinstance(v, bytes) else v) for k, v in o["attrs"].items()}
        out.append(f"{o['op']} {shown}" + (f" + embedded {o['data'].hex(' ')}" if o["data"] else ""))
    return out


# ------------------------------------------------------------------------------------------------ novelty

ENUM_ATTRS = {"Measure", "ErrorReport", "SourceType", "DataOrg", "Orientation", "MediaSize", "MediaSource",
              "ColorSpace", "PaletteDepth", "ColorTreatment", "AllObjectTypes", "TextObjects",
              "VectorObjects", "RasterObjects", "DitherMatrixDataType", "DitherMatrixDepth", "ColorMapping",
              "ColorDepth", "CompressMode"}
DEPTH = {0: "e1Bit", 1: "e4Bit", 2: "e8Bit"}


def tokens(ops: list[dict]) -> dict[str, set]:
    return {
        "operator": {o["op"] for o in ops},
        "operator+attribute": {(o["op"], a) for o in ops for a in o["attrs"]},
        "attribute=enum value": {(a, DEPTH[v] if a in ("ColorDepth", "PaletteDepth") else v)
                                 for o in ops for a, v in o["attrs"].items() if a in ENUM_ATTRS},
        "attribute data type": {(a, *t) if t[1] else (a, t[0]) for o in ops for a, t in o["types"].items()},
        "embedded data form": {(o["op"], o["embed"]) for o in ops if o["embed"]},
        "operator bigram": {(a["op"], b["op"]) for a, b in zip(ops, ops[1:])},
    }


def structure(ops: list[dict]) -> dict:
    """Structural features of a stream (scalars and sets) that the novelty diff compares."""
    names = [o["op"] for o in ops]
    imgs = interpret(ops)
    imgs_reset = interpret(ops, reset_on_space=True)
    first_treat = names.index("SetColorTreatment") if "SetColorTreatment" in names else len(names)
    first_img = names.index("BeginImage") if "BeginImage" in names else len(names)
    loose = sum(1 for k, n in enumerate(names) if n in CONTROL_OPS
                and names[k - 1] not in ("SetColorSpace", *CONTROL_OPS))
    heights = [[b["BlockHeight"] for b in i["blocks"]] for i in imgs]
    return {
        "pages": names.count("BeginPage"),
        "images": len(imgs),
        "SetColorSpace count": names.count("SetColorSpace"),
        "SetHalftoneMethod count": names.count("SetHalftoneMethod"),
        "SetColorTreatment count": names.count("SetColorTreatment"),
        "control runs not directly after a SetColorSpace": loose,
        "images with no control operator after their SetColorSpace": sum(1 for i in imgs
                                                                          if not i["since_space"]),
        "palette bytes": {len(i["space"]["palette"] or b"") for i in imgs},
        "image dimensions (w, h)": {(i["begin"]["SourceWidth"], i["begin"]["SourceHeight"]) for i in imgs},
        "ReadImage block heights": {h for hs in heights for h in hs},
        "ReadImage blocks per image": {len(hs) for hs in heights},
        "ReadImage largest embedded block (B)": max((len(b["data"]) for i in imgs for b in i["blocks"]),
                                                    default=0),
        "a short last ReadImage block": any(hs[-1] != hs[0] for hs in heights),
        "halftone methods in force at images": {i["state"]["halftone"] for i in imgs},
        "treatment in force at images": {i["state"]["treatment"] for i in imgs},
        "halftone methods in force at images (reset on SetColorSpace)": {i["state"]["halftone"]
                                                                        for i in imgs_reset},
        "treatment in force at images (reset on SetColorSpace)": {i["state"]["treatment"]
                                                                  for i in imgs_reset},
        "images before the first SetColorTreatment": sum(1 for i in imgs if i["op_index"] < first_treat),
        "SetHalftoneMethod after an image": any(n == "SetHalftoneMethod" for n in names[first_img:]),
    }


def novelty(job: bytes, refs: dict[str, bytes]) -> tuple[list[str], dict]:
    """Every token and structural feature of the job absent from every reference stream."""
    new_ops = tokenize(stream_body(job))
    ref_ops = {k: tokenize(stream_body(v)) for k, v in refs.items()}
    out: list[str] = []
    tk_new = tokens(new_ops)
    tk_ref = {k: tokens(v) for k, v in ref_ops.items()}
    for cls, items in tk_new.items():
        for item in sorted(items - set().union(*(t[cls] for t in tk_ref.values())), key=repr):
            out.append(f"{cls}: {item}")
    st_new = structure(new_ops)
    st_ref = {k: structure(v) for k, v in ref_ops.items()}
    for key, v in st_new.items():
        refs_v = {k: s[key] for k, s in st_ref.items()}
        if isinstance(v, set):
            extra = v - set().union(*refs_v.values())
            if extra:
                shown = {k: sorted(r, key=repr) for k, r in refs_v.items()}
                out.append(f"{key}: {sorted(extra, key=repr)} (S9/S9b: {shown})")
        elif v not in refs_v.values():
            out.append(f"{key}: {v} (S9/S9b: {refs_v})")
    def plain(d: dict) -> dict:
        return {k: (sorted(v, key=repr) if isinstance(v, set) else v) for k, v in d.items()}
    return out, {"job": plain(st_new), **{k: plain(s) for k, s in st_ref.items()}}


# ------------------------------------------------------------------------------------------------ verify

def geometry_checks(patches: list[dict], fids: list[dict], images: list[dict]) -> dict:
    """Zones, overlaps (with a 1-dot ring), fiducial clearance, patches inside their own image."""
    zones_x = [(dots(lo), dots(hi)) for lo, hi in SLOT_X_ZONES_MM]
    zy = (dots(SLOT_Y_ZONE_MM[0]), dots(SLOT_Y_ZONE_MM[1]))
    page = np.zeros((dots(PAGE_MM[1]), dots(PAGE_MM[0])), np.int32)
    outside, cross = [], []
    for p in patches:
        x, y = dots(p["x_mm"]), dots(p["y_mm"])
        if not any(lo <= x and x + PATTERN_DOTS <= hi for lo, hi in zones_x) or not (
                zy[0] <= y and y + PATCH_H_DOTS <= zy[1]):
            outside.append(p["id"])
        page[y - 1:y + PATCH_H_DOTS + 1, x - 1:x + PATTERN_DOTS + 1] += 1
        img = next(i for i in images if i["kind"] != "fiducial" and i["band"] == p["band"])
        ix, iy, iw, ih = img["xywh"]
        if not (ix <= x and x + PATTERN_DOTS <= ix + iw and iy <= y and y + PATCH_H_DOTS <= iy + ih):
            cross.append(p["id"])
    ring_overlaps = int((page > 1).sum())
    fid_hits = []
    for f in fids:
        x, y, w, h = f["_xywh"]
        if page[y - 1:y + h + 1, x - 1:x + w + 1].any():
            fid_hits.append(f["id"])
        for img in images:
            if img["kind"] != "fiducial":
                ix, iy, iw, ih = img["xywh"]
                if x < ix + iw and ix < x + w and y < iy + ih and iy < y + h:
                    fid_hits.append(f"{f['id']} in {img['name']}")
    occ = np.zeros(page.shape, np.int32)
    for img in images:
        x, y, w, h = img["xywh"]
        occ[y:y + h, x:x + w] += 1
    return {"patches_outside_zones": outside, "patch_ring_overlap_dots": ring_overlaps,
            "patches_outside_their_image": cross, "fiducials_touching_patches_or_band_images": fid_hits,
            "image_overlap_dots": int((occ > 1).sum()),
            "pass": not outside and not ring_overlaps and not cross and not fid_hits and not (occ > 1).any()}


def expected_page(patches: list[dict], fids: list[dict], hw: tuple[int, int]) -> np.ndarray:
    page = np.full((*hw, 3), 255, np.uint8)
    for f in fids:
        x, y, w, h = f["_xywh"]
        page[y:y + h, x:x + w] = f["rgb"]
    for p in patches:
        x, y = dots(p["x_mm"]), dots(p["y_mm"])
        page[y:y + PATCH_H_DOTS, x:x + PATTERN_DOTS][patch_raster(pattern(p["seed"])).astype(bool)] = p["rgb"]
    return page


def render_checks(job_path: Path, patches: list[dict], fids: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as td:
        (fonts := Path(td) / "fonts").mkdir()
        (fonts / "stub.ttf").write_bytes(stub_font())
        img, messages = xl.render(job_path, Path(td) / "ppmraw.out", fonts, "ppmraw")
    diff = (img != expected_page(patches, fids, img.shape[:2])).any(2)
    inked = (img != 255).any(2)
    covered = np.zeros(diff.shape, bool)
    rings = []
    for p in patches:
        x, y = dots(p["x_mm"]), dots(p["y_mm"])
        ring = np.zeros(diff.shape, bool)
        ring[y - 1:y + PATCH_H_DOTS + 1, x - 1:x + PATTERN_DOTS + 1] = True
        ring[y:y + PATCH_H_DOTS, x:x + PATTERN_DOTS] = False
        covered[y:y + PATCH_H_DOTS, x:x + PATTERN_DOTS] = True
        if inked[ring].any():
            rings.append(p["id"])
    for f in fids:
        x, y, w, h = f["_xywh"]
        covered[y:y + h, x:x + w] = True
        if inked[y - 1:y + h + 1, x - 1:x + w + 1].sum() != w * h:
            rings.append(f["id"])
    r = {"page_hw": list(img.shape[:2]), "render_sha256": sha(img.tobytes()), "gpcl6_messages": messages,
         "differing_dots_total": int(diff.sum()), "objects_with_ink_in_1dot_ring": rings,
         "ink_outside_objects": int((inked & ~covered).sum()),
         "inked_dots": int(inked.sum()), "patches_checked": len(patches), "fiducials_checked": len(fids)}
    r["pass"] = not messages and not r["differing_dots_total"] and not rings and not r["ink_outside_objects"]
    return r


def smoke(manifest_path: Path, workdir: Path, sheet: Sheet, n_patches: int) -> dict:
    """(g): paint the manifest into a posed, blurred, noisy 2400 dpi scan; read it back; delete the TIFF."""
    workdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PYTHONPATH=f"{REPO / 'src'}:{REPO}")
    pose = ["--shift-mm", "3.2", "-2.1", "--rot-deg", "0.3", "--scale", "1.004", "--blur-px", "3",
            "--noise-sd", "8"]
    tiff = workdir / f"{sheet.tag}-smoke.tiff"
    try:
        subprocess.run([sys.executable, "-m", "measure.e041_probe_synth", "--manifest", str(manifest_path),
                        "--out", str(workdir), "--name", f"{sheet.tag}-smoke", *pose], check=True, cwd=REPO,
                       env=env,
                       capture_output=True)
        run = subprocess.run([sys.executable, "-m", "measure.e041_probe_readout", "--scan", str(tiff),
                              "--manifest", str(manifest_path), "--out", str(workdir / "readout")],
                             check=True, cwd=REPO, env=env, capture_output=True, text=True)
    finally:
        tiff.unlink(missing_ok=True)
    summ = json.loads((workdir / "readout" / f"{sheet.tag}-summary.json").read_text())
    rows = summ["patches"]
    inked = [r for r in rows if r["target"] != "W"]
    errs = [r["own_hard_err"] for r in inked]
    out = {"pose": " ".join(pose), "fit": {k: summ["fit"][k] for k in summ["fit"] if not isinstance(
        summ["fit"][k], (list, dict))}, "patches_read": len(rows),
        "registration_fallbacks_non_W": sum(1 for r in inked if not r["reg_ok"]),
        "own_channel_hard_error_max": max(errs), "patches_with_own_hard_error": sum(1 for e in errs if e > 0),
        "skipped_lines": [ln for ln in run.stdout.splitlines() if "skipped" in ln],
        "tiff_deleted": not tiff.exists(), "readout_dir": str(workdir / "readout")}
    out["pass"] = (out["patches_read"] == n_patches and not out["registration_fallbacks_non_W"]
                   and out["own_channel_hard_error_max"] == 0 and not out["skipped_lines"]
                   and out["tiff_deleted"])
    return out


def frame_checks(job: bytes, ref: bytes, sheet: Frame) -> dict:
    """PJL frame + stream header = S9's with the job name and the comment swapped; session/page head bytes
    (BeginSession .. BeginPage) identical to S9's."""
    s9_name = b"E041-S9-PCLXL"
    head = job[:job.index(b"\n", job.index(b") HP-PCL XL;")) + 1]
    ref_head = ref[:ref.index(b"\n", ref.index(b") HP-PCL XL;")) + 1]
    tail = job[job.rindex(UEL + b"@PJL EOJ"):]
    ref_tail = ref[ref.rindex(UEL + b"@PJL EOJ"):]
    swap = ref_head.replace(s9_name, sheet.job_name.encode()).replace(S9_COMMENT, sheet.comment)
    begin_page = bytes((OP["BeginPage"],))
    body, ref_body = stream_body(job), stream_body(ref)
    return {"pjl_and_header_equal_S9_but_name_and_comment": head == swap,
            "eoj_equal_S9_but_name": tail == ref_tail.replace(s9_name, sheet.job_name.encode()),
            "session_page_head_bytes_equal_S9": body[:body.index(begin_page) + 1]
            == ref_body[:ref_body.index(begin_page) + 1]}


# ------------------------------------------------------------------------------------------------ manifest

def counts(patches: list[dict], images: list[dict]) -> dict:
    by = Counter((p["method"], p["kind"], p["target"]) for p in patches)
    return {"total": len(patches), "by_method": dict(Counter(p["method"] for p in patches)),
            "by_kind": dict(Counter(p["kind"] for p in patches)),
            "by_target": dict(sorted(Counter(p["target"] for p in patches).items())),
            "by_method_kind_target": {f"{m}/{k}/{t}": n for (m, k, t), n in sorted(by.items())},
            "by_band": {str(b): n for b, n in sorted(Counter(p["band"] for p in patches).items())},
            "palette_entries_used_by_image": {i["name"]: entries_used(i) for i in images}}


def entries_used(img: dict) -> int:
    """Palette entries an image uses: white + one per patch; a fiducial image white (if any) + black."""
    if img["kind"] != "fiducial":
        return len(img["members"]) + 1
    return int(np.unique(img["raster"]).size)


def image_table(images: list[dict]) -> list[dict]:
    return [{"name": i["name"], "kind": i["kind"], "band": i["band"], "method": i["method"],
             "slot_rows": i["slot_rows"], "x_dots": i["xywh"][0], "y_dots": i["xywh"][1],
             "w_dots": i["xywh"][2], "h_dots": i["xywh"][3], "x_mm": mm(i["xywh"][0]),
             "y_mm": mm(i["xywh"][1]), "w_mm": mm(i["xywh"][2]), "h_mm": mm(i["xywh"][3]),
             "row_bytes": row_bytes(i["xywh"][2], 8),
             "readimage_blocks": -(-i["xywh"][3] // BLOCK_ROWS), "palette_entries_used": entries_used(i),
             "members": i["members"], "controls_after_SetColorSpace": [CONTROL_NAME[c] for c in i["block"]]}
            for i in images]


CONTROL_NAME = {"treatment": "SetColorTreatment eNoTreatment", "adaptive": "SetAdaptiveHalftoning eDisable",
                "trapping": "SetColorTrapping eDisable", "neutral": "SetNeutralAxis eProcessBlack",
                "highlpi": "SetHalftoneMethod eHighLPI x3 (S9's bytes)",
                "matrix1x1": "SetHalftoneMethod 1x1 matrix 0x80 (S9b's bytes)"}


def notes(record: dict, sheet: Sheet) -> list[str]:
    changed = (
        "CHANGED 2026-10-05 (owner's decision after the independent refutation of the previous build, sha "
        "5d1f52c0..., 23,473,452 B): that build drew S9's control block ONCE after the witness and each "
        "SetHalftoneMethod once per method, so twelve images had a SetColorSpace followed by no control "
        "operator. X21 p. 22 and X30 p. 9-11 tie treatment, trapping and neutral axis to 'the current "
        "color space', and S9's own order was SetColorSpace -> controls -> image: had the firmware reset "
        "them on SetColorSpace, every band would have printed under the defaults and the treatment witness "
        "would read null. Now every image after the witness carries S9's preamble in S9's order "
        "(SetColorSpace, SetColorTreatment eNoTreatment, SetAdaptiveHalftoning eDisable, SetColorTrapping "
        "eDisable, SetNeutralAxis eProcessBlack, then SetHalftoneMethod eHighLPI x3 for a highlpi band or "
        "the 1x1 matrix for a matrix band, then SetCursor and the image); the standalone head block is "
        "gone. The state in force at every image is its band's method under both readings -- persistent "
        "graphics state (X21 p. 24, X30 p. 5; SetColorSpace resets only pen and brush, X20 p. 85) and "
        "reset on SetColorSpace -- and --verify checks both. Patches, ids, seeds, slots, bands, palettes, "
        "fiducials and the PJL frame are unchanged.")
    if sheet is FULL:
        specific = [
            "WHY THIS SHEET: S10p (sha in S10p-pclxl-rgb-probe.manifest.json, left in place) sent twice to "
            "the M281: the first time the formatter worked two minutes and discarded the page without an "
            "error sheet, the second time 49 SERVICE ERROR and a power cycle; gpcl6 renders it perfectly. "
            "S10p2 = the same 1,011 sweep patterns + the 14-patch treatment witness in S9/S9b's structure "
            "(one eRGB indexed image per band, 64-row ReadImage blocks, S9's preamble and control bytes), "
            "no position replicates, none of S10p's riders (vector, eSRGB, eTonerBlack, encoding riders).",
            "Emission order: BeginPage; the witness image (SetColorSpace, SetAdaptiveHalftoning eDisable, "
            "SetColorTrapping eDisable, SetNeutralAxis eProcessBlack, NO SetColorTreatment: drawn under "
            "the BeginPage default treatment, X20 p. 47, default eScreenMatch X21 p. 24 / X30 p. 5); the "
            "three fiducial images and the default bands 0, 4, 8, each with S9's four controls and no "
            "SetHalftoneMethod; the highlpi bands 1, 5, 6, each with the four + SetHalftoneMethod eHighLPI "
            "x3 (S9's bytes); the matrix bands 2, 3, 7, each with the four + the 1x1 matrix 0x80 (S9b's "
            "bytes, one 4-byte download per band, three in the job); EndPage. No PushGS/PopGS.",
            "Assignment (one generator, default_rng(41)): per method the permutation of the 337 values "
            "split 113/112/112 over its bands in band order; per band the permutation of its 116 slots; "
            "then the witness row's permutation of 29 slots (14 used). Every band has 3 or 4 empty slots. "
            "Pattern patch id = method index x 337 + sweep index, the same ids, seeds and patterns as "
            "S10p's pattern patches; witness ids 1011-1024 (S10p: 1133-1146, other seeds). Slot rows "
            f"{record['empty_slot_rows']} are empty.",
            "Target label = the channels below 64 (C = R low, M = G low, Y = B low); W = none. Value grid: "
            "C/M/Y singles own 0 x foreign 255,240..128 (81) + own 16/32/48 (3); CM/CY/MY free channel "
            "255,240..128 x both zero channels 0/16/32 (27); CMY 0/16/32; W. 337 values x 3 methods. "
            "Witness: the eight corners + (0,192,192), (192,0,192), (192,192,0), (0,0,192), (0,192,0), "
            "(192,0,0), each comparable with its default-method eNoTreatment twin in the default bands.",
        ]
    else:
        specific = [
            "WHY THIS SHEET: the FALLBACK form of S10p2 (owner's request 2026-10-05), NOT to be printed "
            "unless the full sheet fails: the magenta sweep alone in the same structure, so that a failure "
            "of the full sheet's thirteen images can be retried with four.",
            "Emission order: BeginPage; the witness image (three patches: the M corner (255,0,255), "
            "(192,0,192), the C corner; SetColorSpace + adaptive, trapping, neutral, NO "
            "SetColorTreatment); the three fiducial images (S9's four controls); band 0 = default (the "
            "four), band 1 = highlpi (the four + SetHalftoneMethod eHighLPI x3, S9's bytes), band 2 = "
            "matrix (the four + the 1x1 matrix, S9b's bytes, one download); EndPage. One band per method, "
            "top to bottom in that order, so no interleaving.",
            "Assignment (one generator, default_rng(41)): per band (default, highlpi, matrix) the "
            "permutation of its 116 slots, patch k of the band taking slot perm[k], where patch k = the "
            "k-th of the 84 M sweep values in sweep order, then the C corner (0,255,255) and W as controls "
            "(kind 'pattern', targets C and W); then the witness row's permutation of 29 slots (3 used). "
            "30 empty slots per band. Patch id = method index x 86 + k (0-257), witness ids 258-260; seed "
            "= 41000 + id, so the patterns are NOT the full sheet's for the same values. Slot rows "
            f"{record['empty_slot_rows']} are empty.",
            "Target label = the channels below 64; the 84 M values: G = 0 x R, B in 255,240..128 (81) + "
            "(255, 16/32/48, 255) (3). Witness compared with its default-method eNoTreatment twins (M "
            "corner, C corner) in band 0.",
        ]
    common = [
        changed,
        "Fiducials: three separate e8Bit indexed images, palette entry 0 white, 1 black, the rest white: "
        "'fid-top' = F0 + F1 in one 4583 x 71-dot strip (white between), 'fid-left' = F4 alone (71 x 142), "
        "'fid-bottom' = F2 + F3 in one strip. Not folded into a band: no band image reaches them, and the "
        "witness image carries its patches and white only. Each carries S9's four controls and no "
        "SetHalftoneMethod: the default halftone method. Positions as S10p (FIDUCIALS_MM).",
        "Band images: each spans its four slot rows' bounding box over all 29 columns (x 283..4569 dots: "
        "both zones, the 98-118 mm stripe as white, the gaps between patches as white), 4286 x 577 or 578 "
        "dots (the slot rows' y rounds to whole dots), rows 4288 B (X20 p. 179: a multiple of four), 10 "
        "ReadImage blocks (9 x 64 + 1 or 2 rows). The witness image is the same width, 117 rows (64 + 53). "
        "Images never overlap; a patch's 1-dot ring is white inside its image.",
        "Palettes: 768 bytes each (2**8 x 3, X20 p. 85), PaletteData ubyte_array with a uint16 length (768 "
        "> 255; S9's 48-byte palette used a ubyte length). Entry 0 white; entries 1..n the band's patches "
        "in slot order (row-major); the rest white. The W patch (255,255,255) has its own entry, so its "
        "pattern is carried in the stream (it prints as white). 'palette_index' per patch.",
        "Patch = one 93 x 117-dot region inside its band image: the 93 x 93 pattern (31 x 31 cells of 3 x "
        "3 dots, default_rng(41000 + id).integers(0, 2, (31, 31), uint8), 1 = ink) over the 93 x 24 solid "
        "bar, both in the patch colour. Positions are whole 600-dpi dots, the manifest's mm = dots x 25.4 "
        "/ 600 (6 decimals), floor(mm x 600 / 25.4 + 0.5) gives the dot back.",
        "X30 p. 5: the per-object default halftone for raster is LowLPI, so a 'default' patch is nominally "
        "eLowLPI. gpcl6 accepts every control here but its ppmraw render cannot show their effect.",
        "gpcl6's A4 page at 600 dpi is 4960 x 7014 dots; nothing is placed below 289.0 mm.",
    ]
    return specific[:2] + common[:1] + specific[2:] + common[1:]


def build(sheet: Sheet) -> tuple[list[dict], list[dict], list[dict], dict, bytes]:
    patches, fids, images, record = plan(sheet)
    return patches, fids, images, record, emit_job(images, sheet)


def public(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path,
                    help="job path (.pclxl); <stem>.manifest.json is written beside it")
    ap.add_argument("--s9", type=Path, default=None, help=f"S9 job (default: {S9_JOBS['S9']} beside --out)")
    ap.add_argument("--s9b", type=Path, default=None,
                    help=f"S9b job (default: {S9_JOBS['S9b']} beside --out)")
    ap.add_argument("--verify", action="store_true",
                    help="checks (a)-(f): read back, gpcl6, geometry, determinism, novelty")
    ap.add_argument("--smoke", type=Path, default=None, metavar="DIR",
                    help="check (g): synthetic posed scan + readout in DIR (TIFF deleted afterwards)")
    ap.add_argument("--only", choices=["M"], default=None,
                    help="M = the fallback form S10p2M: the magenta sweep alone, one band per method")
    args = ap.parse_args()
    sheet = SHEETS[args.only or "full"]
    patches, fids, images, record, job = build(sheet)
    refs = {k: (getattr(args, k.lower()) or args.out.parent / name).read_bytes()
            for k, name in S9_JOBS.items()}
    novel, features = novelty(job, refs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(job)
    manifest_path = args.out.with_name(args.out.stem + ".manifest.json")
    manifest = {
        "tag": sheet.tag, "sheet": sheet.key, "dpi": DPI, "page_mm": list(PAGE_MM), "bytes": len(job),
        "sha256": sha(job),
        "fiducials": [public(f) for f in fids],
        "patch_px": {"pattern_dots": PATTERN_DOTS, "solid_dots": SOLID_DOTS, "cell_dots": CELL_DOTS,
                     "cells": CELLS},
        "patches": [public(p) for p in patches],
        "layout_seed": LAYOUT_SEED,
        "excluded_zones_mm": {
            "engine_rendering_stripe_x": [98.0, 118.0], "top_y": [0.0, 12.0], "bottom_y": [285.0, 297.0],
            "left_x": [0.0, 12.0], "right_x": [198.0, 210.0],
            "note": "patch slots only inside x [12, 98] U [118, 198], y [12, 285]; the measured print clip "
                    "is ~4.2 mm on every edge and the 3 mm edge strip lies inside it; the fiducials sit "
                    "deliberately in the margins just outside the slot area, never in the stripe; the band "
                    "images span the stripe as white"},
        "slot_grid": {"pitch_mm": list(SLOT_PITCH_MM), **record},
        "band_methods": list(sheet.band_methods),
        "band_note": "band = slot rows 1+4b..4+4b; -1 = the witness band (slot row 0)",
        "images": image_table(images),
        "novelty": novel,
        "novelty_features": features,
        "notes": notes(record, sheet),
        "counts": counts(patches, images),
        "generator": " ".join(["PYTHONPATH=src:.", sys.executable, *sys.argv]),
    }
    manifest_path.write_text(json.dumps({**manifest, "verification": "not run"}, indent=1) + "\n")
    if args.verify or args.smoke:
        v: dict = {}
        if args.verify:
            again = build(sheet)
            m2 = [public(p) for p in again[0]]
            v["a_read_back"] = read_back(job, images, patches, fids, refs)
            v["a_frame_vs_S9"] = frame_checks(job, refs["S9"], sheet)
            v["b_gpcl6_ppmraw"] = render_checks(args.out, patches, fids)
            v["c_pattern_shas_from_seeds"] = all(
                sha(pattern(p["seed"]).tobytes()) == p["pattern_sha256"]
                and p["seed"] == PATTERN_SEED_BASE + p["id"] for p in patches)
            v["d_geometry"] = geometry_checks(patches, fids, images)
            v["e_two_builds_identical"] = again[4] == job and m2 == manifest["patches"] and image_table(
                again[2]) == manifest["images"]
            v["f_novelty_computed"] = novel
        if args.smoke:
            v["g_readout_smoke"] = smoke(manifest_path, args.smoke, sheet, len(patches))
        checks = ([v["a_read_back"]["pass"], all(v["a_frame_vs_S9"].values()), v["b_gpcl6_ppmraw"]["pass"],
                   v["c_pattern_shas_from_seeds"], v["d_geometry"]["pass"], v["e_two_builds_identical"]]
                  if args.verify else [])
        v["pass"] = all(checks) and (v["g_readout_smoke"]["pass"] if args.smoke else True)
        manifest["verification"] = v
        manifest_path.write_text(json.dumps(manifest, indent=1, default=list) + "\n")
    print(f"{args.out}: {len(job)} B sha {manifest['sha256']}")
    print(json.dumps(manifest["counts"], indent=1))
    print("novelty:\n  " + "\n  ".join(novel))
    if isinstance(manifest.get("verification"), dict):
        shown = dict(manifest["verification"])
        if "a_read_back" in shown:
            shown["a_read_back"] = {k: v for k, v in shown["a_read_back"].items() if k != "images"}
        print(json.dumps(shown, indent=1, default=list))


if __name__ == "__main__":
    main()
