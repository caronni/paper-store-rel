"""e041 S9 — sheet F as one PCL XL (PCL 6) bilevel indexed-RGB image for the M281.

What is printed: sheet F's page (`L:c3-cmy8-p120-v1@2240x1536`, GT `page000_gt.npy`) as ONE
PCL XL image in eRGB, 4-bit indexed pixels through a palette whose used entries are the eight
RGB corners (index = C + 2M + 4Y, RGB = 255*(1-C), 255*(1-M), 255*(1-Y)), 600 dpi, 1:1,
uncompressed, at the field origin (148, 176) dots of the A4 page (PCL XL's origin is the
physical page's upper left corner, X20 p. 14).
Why: PCL XL has no CMYK space, but X20 p. 135 says "If the source pixel intensity is bi-level,
the dithering process is not performed", X21 adds SetColorTreatment eNoTreatment and X30 adds
SetAdaptiveHalftoning, SetColorTrapping, SetNeutralAxis and per-object SetHalftoneMethod.  The
hypothesis: a bilevel corner-palette image under those controls reaches the engine as device
values.  RGB black (C+M+Y) is the engine's to map, likely to K toner: a measurement, not a defect.
--variant base = S9 (SetHalftoneMethod eHighLPI for text, vector and raster objects);
--variant dither1x1 = S9b (a user 1x1 e8Bit dither matrix, threshold 128).  Every page control
is one row of controls(); --omit drops rows for ablations.

Sources (HP PCL XL Feature Reference; pages are the documents' printed footers): X20 = Protocol
Class 2.0 rev p2.2 (16 Mar 2000), X21 = Class 2.1 Supplement rev 1.0 (9 Aug 2000), X30 = Class
3.0 Supplement rev 0.90 (8 Jul 2002).

--verify: an independent decode of the job's own stream (operators, attributes, the palette, the
image blocks unpacked back to C/M/Y), then GhostPCL renders (gpcl6, 600 dpi) on ppmraw (contone)
and bitrgb (1 bit per RGB component, halftoned): every pixel must be an RGB corner, each plane
must equal the GT at (148, 176) dot for dot, nothing inked outside the field, and the job must
rebuild byte-identically.  gpcl6 needs a stub PCL font to start (pcl_planar.stub_font).

    PYTHONPATH=src env/bin/python experiments/041-m281-screen-routes/pclxl_bilevel.py \
        --gt <F gen dir>/page000_gt.npy --variant base \
        --out experiments/041-m281-screen-routes/build/S9-pclxl-bilevel.pclxl --verify
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from pcl_planar import (FIELD_YX, GPCL6, ORIGIN_YX, PAGE_DOTS_XY, UEL, first_ink_yx, load_gt,
                        placed, ps_placement, sha, stub_font)

# Data-type and attribute-prefix tags: X20 Appendix D p. 215-216 (also X21 p. 28-29, X30 p. 21-22).
UBYTE, UINT16, UBYTE_ARRAY, UINT16_XY, SINT16_XY = 0xC0, 0xC1, 0xC8, 0xD1, 0xD3
ATTR_UBYTE, EMBED, EMBED_BYTE = 0xF8, 0xFA, 0xFB
# Operator tags: X20 Appendix D p. 212-215, X21 p. 26-28, X30 p. 19-21.  X30's tag table itself
# marks 0x92 and 0x94 "Reserved for future use" beside the names its section 2.1 defines.
OP = {"BeginSession": 0x41, "EndSession": 0x42, "BeginPage": 0x43, "EndPage": 0x44,
      "OpenDataSource": 0x48, "CloseDataSource": 0x49, "SetColorTreatment": 0x58,
      "SetColorSpace": 0x6A, "SetCursor": 0x6B, "SetHalftoneMethod": 0x6D, "SetNeutralAxis": 0x7E,
      "SetColorTrapping": 0x92, "SetAdaptiveHalftoning": 0x94, "BeginImage": 0xB0,
      "ReadImage": 0xB1, "EndImage": 0xB2}
# Attribute ids: X20 Appendix E p. 219-220; 29-32 from X30 Appendix E p. 23; 120 from X21 p. 32 and
# X30 p. 25.  (X30 Appendix F p. 30 prints UnitsPerMeasure as 114: a typo, every Appendix E says 137.)
ATTR = {"PaletteDepth": 2, "ColorSpace": 3, "PaletteData": 6, "AllObjectTypes": 29,
        "TextObjects": 30, "VectorObjects": 31, "RasterObjects": 32, "DitherMatrixDataType": 34,
        "MediaSize": 37, "MediaSource": 38, "Orientation": 40, "DitherMatrixSize": 50,
        "DitherMatrixDepth": 51, "Point": 76, "ColorDepth": 98, "BlockHeight": 99,
        "ColorMapping": 100, "CompressMode": 101, "DestinationSize": 103, "SourceHeight": 107,
        "SourceWidth": 108, "StartLine": 109, "ColorTreatment": 120, "DataOrg": 130,
        "Measure": 134, "SourceType": 136, "UnitsPerMeasure": 137, "ErrorReport": 143}
# Enumerations: X20 Appendix G p. 226-227, X21 p. 38-40, X30 Appendix G p. 31-34.
E = {"eInch": 0, "eDefaultDataSource": 0, "eBinaryLowByteFirst": 1, "ePortraitOrientation": 0,
     "eA4Paper": 2, "eDefaultSource": 0, "eBackChAndErrPage": 3, "eRGB": 2, "e8Bit": 2, "e4Bit": 1,
     "eIndexedPixel": 1, "eNoCompression": 0, "eUByte": 0, "eNoTreatment": 0, "eDisable": 0,
     "eProcessBlack": 1, "eHighLPI": 0}
VARIANTS = {"base": ("E041-S9-PCLXL", "3;0"), "dither1x1": ("E041-S9B-PCLXL", "3;0")}
BLOCK_ROWS = 64  # ReadImage block height; 6720 = 105 x 64, 147,456 B per block at e4Bit
GPCL6_DEVICES = ("ppmraw", "bitrgb")  # bitrgb: raw rows, 4 bits per pixel, R = bit 2, G = 1, B = 0


def ub(value: int, attr: str) -> bytes:
    return bytes((UBYTE, value, ATTR_UBYTE, ATTR[attr]))


def u16(value: int, attr: str) -> bytes:
    return struct.pack("<BHBB", UINT16, value, ATTR_UBYTE, ATTR[attr])


def xy(x: int, y: int, attr: str, tag: int = UINT16_XY) -> bytes:
    return struct.pack("<B2HBB" if tag == UINT16_XY else "<B2hBB", tag, x, y, ATTR_UBYTE, ATTR[attr])


def op(name: str) -> bytes:
    return bytes((OP[name],))


def controls(variant: str) -> dict[str, tuple[str, str, bytes]]:
    """THE page controls, emitted in this order after SetColorSpace: name -> (class, source, bytes).
    Every hypothesis-bearing control of S9 lives here and nowhere else; --omit drops rows."""
    halftone = {
        "base": ("3.0", "SetHalftoneMethod 0x6d (X30 p. 7-8): TextObjects/VectorObjects/RasterObjects "
                 "(30/31/32, X30 p. 23) = eHighLPI (0, X30 p. 31)",
                 ub(E["eHighLPI"], "TextObjects") + ub(E["eHighLPI"], "VectorObjects")
                 + ub(E["eHighLPI"], "RasterObjects") + op("SetHalftoneMethod")),
        "dither1x1": ("2.0", "SetHalftoneMethod 0x6d (X20 p. 134-136, X30 p. 7-8): DitherMatrixSize "
                      "(50) uint16_xy 1 1, DitherMatrixDataType (34) = eUByte (0), DitherMatrixDepth "
                      "(51) = e8Bit (2); then embedded data 0xfb, 4 bytes: threshold 0x80, the row "
                      "padded to four bytes (X30 p. 7)",
                      xy(1, 1, "DitherMatrixSize") + ub(E["eUByte"], "DitherMatrixDataType")
                      + ub(E["e8Bit"], "DitherMatrixDepth") + op("SetHalftoneMethod")
                      + bytes((EMBED_BYTE, 4, 0x80, 0, 0, 0))),
    }
    return {
        "treatment": ("2.1", "SetColorTreatment 0x58 (X21 p. 22, tag p. 27): ColorTreatment (120, "
                      "X21 p. 32) = eNoTreatment (0, X21 p. 38)",
                      ub(E["eNoTreatment"], "ColorTreatment") + op("SetColorTreatment")),
        "adaptive": ("3.0", "SetAdaptiveHalftoning 0x94 (X30 p. 9, tag p. 21): AllObjectTypes (29, "
                     "X30 p. 23) = eDisable (0, X30 p. 31)",
                     ub(E["eDisable"], "AllObjectTypes") + op("SetAdaptiveHalftoning")),
        "trapping": ("3.0", "SetColorTrapping 0x92 (X30 p. 10, tag p. 21): AllObjectTypes (29) = "
                     "eDisable (0, X30 p. 31)",
                     ub(E["eDisable"], "AllObjectTypes") + op("SetColorTrapping")),
        "neutral": ("3.0", "SetNeutralAxis 0x7e (X30 p. 11, tag p. 20): AllObjectTypes (29) = "
                    "eProcessBlack (1, X30 p. 31)",
                    ub(E["eProcessBlack"], "AllObjectTypes") + op("SetNeutralAxis")),
        "halftone": halftone[variant],
    }


def palette() -> np.ndarray:
    """(16, 3) RGB: e4Bit pixels need 2**4 entries (X20 p. 85); index C+2M+4Y -> corner, 8-15 white."""
    k = np.arange(16)[:, None]
    return np.where(k < 8, 255 * (1 - (k >> np.arange(3) & 1)), 255).astype(np.uint8)


def index_raster(cmy: np.ndarray) -> np.ndarray:
    bits = np.unpackbits(cmy, axis=2, bitorder="big")
    return bits[0] | bits[1] << 1 | bits[2] << 2


def emit_job(cmy: np.ndarray, variant: str, omit: frozenset[str]) -> bytes:
    """PJL-framed PCL XL job: session, page, colour space, the controls, one indexed image."""
    rows, cols = FIELD_YX
    idx = index_raster(cmy)
    data = (idx[:, 0::2] << 4 | idx[:, 1::2]).astype(np.uint8)  # e4Bit, left pixel in the high nibble
    s = bytearray(xy(600, 600, "UnitsPerMeasure") + ub(E["eInch"], "Measure")
                  + ub(E["eBackChAndErrPage"], "ErrorReport") + op("BeginSession"))
    s += ub(E["eDefaultDataSource"], "SourceType") + ub(E["eBinaryLowByteFirst"], "DataOrg")
    s += op("OpenDataSource")
    s += ub(E["ePortraitOrientation"], "Orientation") + ub(E["eA4Paper"], "MediaSize")
    s += ub(E["eDefaultSource"], "MediaSource") + op("BeginPage")
    s += ub(E["eRGB"], "ColorSpace") + ub(E["e8Bit"], "PaletteDepth")
    s += bytes((UBYTE_ARRAY, UBYTE, 48)) + palette().tobytes() + bytes((ATTR_UBYTE, ATTR["PaletteData"]))
    s += op("SetColorSpace")
    for name, (_, _, code) in controls(variant).items():
        if name not in omit:
            s += code
    s += xy(ORIGIN_YX[1], ORIGIN_YX[0], "Point", SINT16_XY) + op("SetCursor")
    s += ub(E["eIndexedPixel"], "ColorMapping") + ub(E["e4Bit"], "ColorDepth")
    s += u16(cols, "SourceWidth") + u16(rows, "SourceHeight") + xy(cols, rows, "DestinationSize")
    s += op("BeginImage")
    for start in range(0, rows, BLOCK_ROWS):
        block = data[start:start + BLOCK_ROWS].tobytes()
        s += u16(start, "StartLine") + u16(min(BLOCK_ROWS, rows - start), "BlockHeight")
        s += ub(E["eNoCompression"], "CompressMode") + op("ReadImage")
        s += struct.pack("<BI", EMBED, len(block)) + block
    s += op("EndImage") + op("EndPage") + op("CloseDataSource") + op("EndSession")
    name, protocol = VARIANTS[variant]
    header = b") HP-PCL XL;%s;Comment e041 %s sheet F bilevel indexed RGB\n" % (
        protocol.encode(), name.encode())
    pjl = (b'@PJL JOB NAME="%s"\r\n@PJL SET RESOLUTION=600\r\n@PJL SET BITSPERPIXEL=1\r\n'
           b"@PJL ENTER LANGUAGE=PCLXL\r\n" % name.encode())
    return UEL + pjl + header + bytes(s) + UEL + b'@PJL EOJ NAME="%s"\r\n' % name.encode() + UEL


def stream_body(job: bytes) -> bytes:
    start = job.index(b"\n", job.index(b") HP-PCL XL;")) + 1
    return job[start:job.rindex(UEL + b"@PJL EOJ")]


def parse(stream: bytes) -> list[list]:
    """Independent decode of a little-endian PCL XL stream body: [operator, {attribute: value}, data]."""
    names, anames, fmt = {v: k for k, v in OP.items()}, {v: k for k, v in ATTR.items()}, "BHIhif"
    ops, attrs, value, i = [], {}, None, 0
    while i < len(stream):
        t, i = stream[i], i + 1
        if t & 0xF8 in (0xC0, 0xC8, 0xD0, 0xE0) and t & 7 <= 5:
            if t & 0xF8 == 0xC8:
                lf = "<" + fmt[stream[i] & 7]
                (n,), i = struct.unpack_from(lf, stream, i + 1), i + 1 + struct.calcsize(lf)
            else:
                n = {0xC0: 1, 0xD0: 2, 0xE0: 4}[t & 0xF8]
            f = "<%d%s" % (n, fmt[t & 7])
            value, i = struct.unpack_from(f, stream, i), i + struct.calcsize(f)
            value = bytes(value) if t == UBYTE_ARRAY else value[0] if t & 0xF8 == 0xC0 else list(value)
        elif t == ATTR_UBYTE:
            attrs[anames.get(stream[i], stream[i])], value, i = value, None, i + 1
        elif t in (EMBED, EMBED_BYTE):
            lf = "<I" if t == EMBED else "<B"
            (n,), i = struct.unpack_from(lf, stream, i), i + struct.calcsize(lf)
            ops[-1][2], i = stream[i:i + n], i + n
        elif 0x41 <= t <= 0xBF:
            ops.append([names.get(t, f"tag {t:#04x}"), attrs, b""])
            attrs = {}
        else:
            raise ValueError(f"unexpected tag {t:#04x} at stream offset {i - 1}")
    if attrs or value is not None:
        raise ValueError("attribute list left without an operator")
    return ops


def listing(ops: list[list]) -> list[str]:
    """Human-readable operator sequence; image blocks and long arrays summarised."""
    out, reads, summarised = [], [o for o in ops if o[0] == "ReadImage"], False
    for name, attrs, data in ops:
        if name == "ReadImage":
            if not summarised:
                summarised = True
                out.append(f"ReadImage x {len(reads)} (StartLine 0..{reads[-1][1]['StartLine']}, "
                           f"BlockHeight {attrs['BlockHeight']}, CompressMode {attrs['CompressMode']}, "
                           f"embedded {len(data)} B each)")
            continue
        shown = {k: (f"<{len(v)} B>" if isinstance(v, bytes) else v) for k, v in attrs.items()}
        out.append(f"{name} {shown}" + (f" + embedded {data.hex(' ')}" if data else ""))
    return out


def read_back(job: bytes, cmy: np.ndarray, variant: str, omit: frozenset[str]) -> dict:
    ops = parse(stream_body(job))
    ctl = [code for name, (_, _, code) in controls(variant).items() if name not in omit]
    want = (["BeginSession", "OpenDataSource", "BeginPage", "SetColorSpace"]
            + [parse(c)[0][0] for c in ctl] + ["SetCursor", "BeginImage"]
            + ["ReadImage"] * -(-FIELD_YX[0] // BLOCK_ROWS) + ["EndImage", "EndPage", "CloseDataSource", "EndSession"])
    begin = next(a for n, a, _ in ops if n == "BeginImage")
    reads = [(a, d) for n, a, d in ops if n == "ReadImage"]
    starts = [a["StartLine"] for a, _ in reads]
    heights = [a["BlockHeight"] for a, _ in reads]
    raw = np.frombuffer(b"".join(d for _, d in reads), np.uint8).reshape(sum(heights), -1)
    idx = np.stack([raw >> 4, raw & 15], axis=2).reshape(raw.shape[0], -1)[:, :begin["SourceWidth"]]
    pal = np.frombuffer(next(a for n, a, _ in ops if n == "SetColorSpace")["PaletteData"], np.uint8)
    bits = np.unpackbits(cmy, axis=2, bitorder="big")
    return {
        "operators_as_expected": [n for n, _, _ in ops] == want,
        "begin_image": begin, "set_cursor": next(a for n, a, _ in ops if n == "SetCursor"),
        "blocks_contiguous": starts == list(np.cumsum([0] + heights[:-1])),
        "max_index": int(idx.max()), "palette_rgb_by_index": pal.reshape(-1, 3)[:8].tolist(),
        "differing_dots_per_plane_vs_gt": {p: int(np.count_nonzero((idx >> c & 1) != bits[c]))
                                           for c, p in enumerate("CMY")},
        "operator_listing": listing(ops),
    }


def render(src: Path, out: Path, fonts: Path, device: str, hw: tuple[int, int] | None = None
           ) -> tuple[np.ndarray, str]:
    """gpcl6 render of one job as (h, w, 3) RGB; refuses anything but exactly one page.  ppmraw
    gives its own size; bitrgb has no header, so its page must have the size `hw` of the ppmraw."""
    run = subprocess.run([GPCL6, "-dNOPAUSE", "-dBATCH", f"-sDEVICE={device}", "-r600",
                          f"-sOutputFile={out}", str(src)], check=True, capture_output=True,
                         env=dict(os.environ, PCLFONTSOURCE=f"{fonts}/"))
    raw, tokens, pos = out.read_bytes(), [], 0
    messages = (run.stdout + run.stderr).decode("utf-8", "replace").strip()
    if device == "bitrgb":
        h, w = hw
        if len(raw) != h * w // 2:
            raise SystemExit(f"{out}: not exactly one {w}x{h} 4-bit page")
        nib = np.frombuffer(raw, np.uint8).reshape(h, w // 2)
        nib = np.stack([nib >> 4, nib & 15], axis=2).reshape(h, w)
        return (np.stack([nib >> 2 & 1, nib >> 1 & 1, nib & 1], axis=2) * 255).astype(np.uint8), messages
    while len(tokens) < 4:
        line = raw[pos:raw.index(b"\n", pos)]
        pos += len(line) + 1
        tokens += [] if line.startswith(b"#") else line.split()
    w, h = int(tokens[1]), int(tokens[2])
    if tokens[0] != b"P6" or len(raw) - pos != w * h * 3:
        raise SystemExit(f"{out}: not exactly one {w}x{h} P6 page")
    return np.frombuffer(raw, np.uint8, w * h * 3, pos).reshape(h, w, 3), messages


def verify(job_path: Path, job: bytes, cmy: np.ndarray, variant: str, omit: frozenset[str]) -> dict:
    result: dict = {"read_back": read_back(job, cmy, variant, omit),
                    "rebuild_byte_identical": sha(emit_job(cmy, variant, omit)) == sha(job)}
    bits = np.unpackbits(cmy, axis=2, bitorder="big").astype(bool)
    result["gt_ink_dots"] = {p: int(bits[c].sum()) for c, p in enumerate("CMY")}
    y0, x0 = ORIGIN_YX
    field = (slice(y0, y0 + FIELD_YX[0]), slice(x0, x0 + FIELD_YX[1]))
    with tempfile.TemporaryDirectory() as td:
        (fonts := Path(td) / "fonts").mkdir()
        (fonts / "stub.ttf").write_bytes(stub_font())
        hw = None
        for device in GPCL6_DEVICES:
            img, messages = render(job_path, Path(td) / f"{device}.out", fonts, device, hw)
            hw = img.shape[:2]
            ink = img < 128
            inside = np.zeros(ink.shape[:2], bool)
            inside[field] = True
            result[f"gpcl6_{device}"] = {
                "page_hw": list(img.shape[:2]), "render_sha256": sha(img.tobytes()),
                "non_corner_pixels": int(np.count_nonzero(((img != 0) & (img != 255)).any(2))),
                "differing_dots_per_plane_vs_gt": {
                    p: int(np.count_nonzero(ink[..., c] != placed(bits[c], ink.shape[:2])))
                    for c, p in enumerate("CMY")},
                "ink_dots_per_plane": {p: int(ink[..., c].sum()) for c, p in enumerate("CMY")},
                "ink_outside_field": int(np.count_nonzero(ink.any(2) & ~inside)),
                "first_ink_yx": first_ink_yx(ink.any(2)), "gpcl6_messages": messages}
    rb, gt = result["read_back"], result["gt_ink_dots"]
    result["pass"] = bool(
        rb["operators_as_expected"] and rb["blocks_contiguous"] and rb["max_index"] <= 7
        and not any(rb["differing_dots_per_plane_vs_gt"].values()) and result["rebuild_byte_identical"]
        and all(not r["non_corner_pixels"] and not any(r["differing_dots_per_plane_vs_gt"].values())
                and r["ink_dots_per_plane"] == gt and not r["ink_outside_field"] and not r["gpcl6_messages"]
                for r in (result[f"gpcl6_{d}"] for d in GPCL6_DEVICES)))
    result["command"] = (f"PCLFONTSOURCE=<tmp>/fonts/ {GPCL6} -dNOPAUSE -dBATCH -sDEVICE=<{'|'.join(GPCL6_DEVICES)}> "
                         f"-r600 -sOutputFile=<tmp>/<device>.out {job_path}")
    return result


UNVERIFIED = [
    "Whether the M281's PCL XL interpreter implements class 3.0 at all: the stream header says 3;0 and "
    "X30's own tag table marks 0x92/0x94 reserved; an unknown operator or protocol aborts with an error "
    "page (ErrorReport eBackChAndErrPage asks for one, plus warnings) rather than printing.",
    "Whether the firmware honours eNoTreatment, eDisable adaptive halftoning / trapping, eProcessBlack, "
    "eHighLPI or the 1x1 dither (X20 p. 134 and X30 p. 8 allow reading and ignoring a dither matrix); "
    "gpcl6 accepts them but its renders cannot show their effect.",
    "Whether @PJL SET BITSPERPIXEL=1 applies to this job (the PJL reference documents it 'for PCL 6 only', "
    "p. 6-13, for older engines; the M281 enumerates 1/2/4/8) and whether the engine still screens 0/255 RGB.",
    "What RGB black (index 7, C+M+Y) becomes: K toner or process CMY (SetNeutralAxis eProcessBlack asks "
    "for process black on every object type); RGB->CMYK is the engine's mapping, a measurement.",
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--gt", required=True, type=Path, help="page000_gt.npy (manifest.json beside it)")
    ap.add_argument("--ps", type=Path, help="PostScript job to cross-check placement against "
                    "(default: page000.ps beside the GT)")
    ap.add_argument("--variant", required=True, choices=sorted(VARIANTS),
                    help="base = S9 (eHighLPI per object type); dither1x1 = S9b (user 1x1 threshold 128)")
    ap.add_argument("--omit", action="append", default=[], choices=list(controls("base")),
                    help="drop one page control (repeatable) for an ablation job")
    ap.add_argument("--out", required=True, type=Path, help="job path; manifest written beside it")
    ap.add_argument("--verify", action="store_true", help="decode + render with gpcl6, compare to GT")
    args = ap.parse_args()
    cmy, gt = load_gt(args.gt)
    ps = ps_placement(args.ps or args.gt.parent / "page000.ps")
    ours = {"page_dots_xy": list(PAGE_DOTS_XY), "origin_yx": list(ORIGIN_YX), "field_yx": list(FIELD_YX)}
    if {k: ps[k] for k in ours} != ours:
        raise SystemExit(f"placement disagrees with the PostScript job: {ps} vs {ours}")
    omit = frozenset(args.omit)
    job = emit_job(cmy, args.variant, omit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(job)
    body = stream_body(job)
    manifest = {
        "tag": args.out.stem, "job": str(args.out), "bytes": len(job), "sha256": sha(job),
        "what": "PCL XL (PCL 6) job: one eRGB image, e4Bit indexed through the eight RGB corners "
                "(index C+2M+4Y), 4608x6720 at 600 dpi 1:1, eNoCompression, at (148,176) dots on A4",
        "variant": args.variant, "omitted_controls": sorted(omit),
        "pjl_and_stream_header": job[:job.index(b"\n", job.index(b") HP-PCL XL;")) + 1].decode("latin-1"),
        "controls": {n: {"protocol_class": c, "source": s, "bytes_hex": b.hex(" "), "emitted": n not in omit}
                     for n, (c, s, b) in controls(args.variant).items()},
        "sequence_note": "SetColorSpace precedes the controls: X21 p. 22 binds the treatment to the current "
                         "colour space, so a later SetColorSpace could restore the default eScreenMatch",
        "palette_note": "16 entries, not 8: X20 p. 85 sizes the palette by ColorDepth (2**4 x 3 = 48 "
                        "bytes), p. 237 ImagePaletteMismatch; gpcl6 refuses 8 entries (IllegalAttributeValue "
                        "at SetColorSpace). Indices 8-15 white, never used; e4Bit is the smallest depth "
                        "carrying 8 indices (e1Bit/e4Bit/e8Bit only, X20 p. 177)",
        "stream_bytes_before_image_data": body[:body.index(bytes((OP["ReadImage"], EMBED))) + 1].hex(" "),
        "unverified_on_printer": UNVERIFIED, "format_ref": "L:c3-cmy8-p120-v1@2240x1536", **gt,
        "placement": {**ours, "ps_cross_check": ps, "pclxl_cursor_xy": [ORIGIN_YX[1], ORIGIN_YX[0]]},
        "generator": " ".join(["PYTHONPATH=src", sys.executable, *sys.argv]),
        "verification": verify(args.out, job, cmy, args.variant, omit) if args.verify else "not run",
    }
    args.out.with_name(args.out.stem + ".manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"{args.out}: {len(job)} B sha {manifest['sha256']}")
    print(json.dumps(manifest["verification"], indent=1))


if __name__ == "__main__":
    main()
