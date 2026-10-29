#!/usr/bin/env python3
"""e039 — PWG Raster (PWG 5102.4) writer for the VersaLink C7130's
image/pwg-raster door: cmyk_8 (ColorSpace 6, 8 bits/colour, 32 bpp chunky,
0 = paper, 255 = toner) as the colour analogue of the Apple-raster W8 page
that printed bit-faithfully, and black_1 / sgray_8 for K.

    env/bin/python experiments/039-xerox-versalink/pwg_raster.py page.ps out.pwg \\
        --media legal --type cmyk_8|sgray_8|black_1 [--quality 4|5] [--optimize auto|graphics|text]

Header: the 1796-octet CUPS raster v2 page header that PWG 5102.4 Table 1
mirrors ("RaS2" sync, big-endian, Reserved = 0).  Line coding: PackBits
over whole pixels (1-bit types: over octets of 8 pixels) with a leading
line-repeat byte — identical to Apple raster's.  The written header is
read back through the system libcups (cupsRasterReadHeader2) and every
set field compared before the file is kept.  Nothing prints.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmyk_pdf import place_planes, render_cmyk  # noqa: E402
from urf_raster import urf_encode_pixels  # noqa: E402

HW_DPI = 600
SYNC = b"RaS2"
TYPES = {  # keyword: (BitsPerColor, BitsPerPixel, ColorSpace, NumColors)
    "black_1": (1, 1, 3, 1), "sgray_8": (8, 8, 18, 1), "cmyk_8": (8, 32, 6, 4),
}
OPTIMIZE = ("auto", "graphics", "text", "text-and-graphics", "photo")


def cstr(s: str, n: int = 64) -> bytes:
    b = s.encode("ascii")
    if len(b) >= n:
        raise ValueError(s)
    return b + b"\0" * (n - len(b))


def pwg_header(w: int, h: int, typ: str, quality: int, optimize: str,
               media_type: str = "stationery", page_name: str = "na_legal_8.5x14in") -> bytes:
    bpc, bpp, cs, nc = TYPES[typ]
    bytes_per_line = (w * bpp + 7) // 8
    pts = (w * 72 // HW_DPI, h * 72 // HW_DPI)
    hdr = bytearray()
    hdr += cstr("PwgRaster") + cstr("") + cstr(media_type) + cstr(optimize)  # 0..255
    u = lambda v: struct.pack(">I", v)                                       # noqa: E731
    hdr += u(0) * 3                       # AdvanceDistance, AdvanceMedia, Collate (reserved)
    hdr += u(0)                           # CutMedia: never
    hdr += u(0)                           # Duplex: false
    hdr += u(HW_DPI) + u(HW_DPI)          # HWResolution
    hdr += u(0) * 4                       # ImagingBoundingBox (reserved)
    hdr += u(0)                           # InsertSheet
    hdr += u(0)                           # Jog
    hdr += u(0)                           # LeadingEdge: short-edge-first
    hdr += u(0) * 2                       # Margins (reserved)
    hdr += u(0)                           # ManualFeed (reserved)
    hdr += u(0)                           # MediaPosition: auto
    hdr += u(0)                           # MediaWeight
    hdr += u(0) * 2                       # MirrorPrint, NegativePrint (reserved)
    hdr += u(1)                           # NumCopies
    hdr += u(0)                           # Orientation: portrait
    hdr += u(0)                           # OutputFaceUp (reserved)
    hdr += u(pts[0]) + u(pts[1])          # PageSize (points)
    hdr += u(0) * 3                       # Separations, TraySwitch (reserved), Tumble
    hdr += u(w) + u(h)                    # Width, Height
    hdr += u(0)                           # MediaType (reserved)
    hdr += u(bpc) + u(bpp) + u(bytes_per_line)
    hdr += u(0)                           # ColorOrder: chunky
    hdr += u(cs)                          # ColorSpace
    hdr += u(0) * 4                       # Compression, RowCount, RowFeed, RowStep (reserved)
    hdr += u(nc)                          # NumColors
    hdr += b"\0" * 4                      # BorderlessScalingFactor (reserved)
    hdr += b"\0" * 8 + b"\0" * 16         # PageSizeF, ImagingBBox (reserved)
    ints = [1, 1, 1, 0, 0, 0, 0, 0, quality, 0, 0, 0, 0, 0, 0, 0]  # TotalPageCount, CrossFeed/FeedTransform = 1, PrintQuality
    hdr += b"".join(u(v) for v in ints)
    hdr += b"\0" * 64                     # cupsReal (reserved)
    hdr += b"\0" * 1024                   # VendorData
    hdr += b"\0" * 64                     # cupsMarkerType (reserved)
    hdr += cstr("")                       # RenderingIntent
    hdr += cstr(page_name)                # PageSizeName
    assert len(hdr) == 1796, len(hdr)
    return bytes(hdr)


def pwg_file(planes: np.ndarray, typ: str, quality: int = 4, optimize: str = "auto") -> bytes:
    h, w = planes.shape[:2]
    if typ == "cmyk_8":
        img = planes.astype(np.uint8) * 255                     # (h, w, 4) C M Y K
        data = urf_encode_pixels(img, 4)
    elif typ == "sgray_8":
        k = planes[:, :, 3] if planes.ndim == 3 else planes
        img = np.where(k == 1, 0, 255).astype(np.uint8)[:, :, None]
        data = urf_encode_pixels(img, 1)
    elif typ == "black_1":
        k = planes[:, :, 3] if planes.ndim == 3 else planes
        packed = np.packbits(k.astype(np.uint8), axis=1)          # 1 = black, 8 px per octet
        data = urf_encode_pixels(packed[:, :, None], 1)
    else:
        raise ValueError(typ)
    return SYNC + pwg_header(w, h, typ, quality, optimize) + data


# --- validation through the system libcups ---------------------------------------
class _Hdr2(ctypes.Structure):
    _fields_ = ([(n, ctypes.c_char * 64) for n in ("MediaClass", "MediaColor", "MediaType", "OutputType")]
                + [(n, ctypes.c_uint) for n in (
                    "AdvanceDistance", "AdvanceMedia", "Collate", "CutMedia", "Duplex", "HWResolution0", "HWResolution1",
                    "IBB0", "IBB1", "IBB2", "IBB3", "InsertSheet", "Jog", "LeadingEdge", "Margins0", "Margins1", "ManualFeed",
                    "MediaPosition", "MediaWeight", "MirrorPrint", "NegativePrint", "NumCopies", "Orientation", "OutputFaceUp",
                    "PageSize0", "PageSize1", "Separations", "TraySwitch", "Tumble", "cupsWidth", "cupsHeight", "cupsMediaType",
                    "cupsBitsPerColor", "cupsBitsPerPixel", "cupsBytesPerLine", "cupsColorOrder", "cupsColorSpace",
                    "cupsCompression", "cupsRowCount", "cupsRowFeed", "cupsRowStep", "cupsNumColors")]
                + [("cupsBorderlessScalingFactor", ctypes.c_float), ("cupsPageSizeF", ctypes.c_float * 2),
                   ("cupsImagingBBox", ctypes.c_float * 4), ("cupsInteger", ctypes.c_uint * 16), ("cupsReal", ctypes.c_float * 16),
                   ("cupsString", (ctypes.c_char * 64) * 16), ("cupsMarkerType", ctypes.c_char * 64),
                   ("cupsRenderingIntent", ctypes.c_char * 64), ("cupsPageSizeName", ctypes.c_char * 64)])


def libcups_read(path: Path) -> dict:
    lib = ctypes.CDLL(ctypes.util.find_library("cups"))
    libc = ctypes.CDLL(ctypes.util.find_library("c"))
    libc.open.restype = ctypes.c_int
    fd = libc.open(str(path).encode(), 0)
    lib.cupsRasterOpen.restype = ctypes.c_void_p
    ras = lib.cupsRasterOpen(fd, 0)   # CUPS_RASTER_READ
    if not ras:
        raise SystemExit("libcups: cupsRasterOpen failed (sync word?)")
    hdr = _Hdr2()
    ok = lib.cupsRasterReadHeader2(ctypes.c_void_p(ras), ctypes.byref(hdr))
    lib.cupsRasterClose(ctypes.c_void_p(ras))
    libc.close(fd)
    if not ok:
        raise SystemExit("libcups: cupsRasterReadHeader2 rejected the header")
    return {"PwgRaster": hdr.MediaClass, "MediaType": hdr.MediaType, "PrintContentOptimize": hdr.OutputType,
            "HWResolution": (hdr.HWResolution0, hdr.HWResolution1), "Width": hdr.cupsWidth, "Height": hdr.cupsHeight,
            "BitsPerColor": hdr.cupsBitsPerColor, "BitsPerPixel": hdr.cupsBitsPerPixel, "BytesPerLine": hdr.cupsBytesPerLine,
            "ColorOrder": hdr.cupsColorOrder, "ColorSpace": hdr.cupsColorSpace, "NumColors": hdr.cupsNumColors,
            "PageSize": (hdr.PageSize0, hdr.PageSize1), "TotalPageCount": hdr.cupsInteger[0],
            "PrintQuality": hdr.cupsInteger[8], "PageSizeName": hdr.cupsPageSizeName, "Duplex": hdr.Duplex}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ps", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--media", choices=("legal", "letter-centered", "as-is"), default="legal")
    ap.add_argument("--type", choices=tuple(TYPES), default="cmyk_8")
    ap.add_argument("--quality", type=int, choices=(3, 4, 5), default=4)
    ap.add_argument("--optimize", choices=OPTIMIZE, default="auto")
    args = ap.parse_args()
    planes = place_planes(render_cmyk(args.ps), args.media)
    data = pwg_file(planes, args.type, args.quality, args.optimize)
    with tempfile.NamedTemporaryFile(suffix=".pwg", delete=False) as t:
        t.write(data)
        tmp = Path(t.name)
    got = libcups_read(tmp)
    tmp.unlink()
    bpc, bpp, cs, nc = TYPES[args.type]
    h, w = planes.shape[:2]
    want = {"Width": w, "Height": h, "BitsPerColor": bpc, "BitsPerPixel": bpp, "ColorSpace": cs, "NumColors": nc,
            "HWResolution": (HW_DPI, HW_DPI), "BytesPerLine": (w * bpp + 7) // 8, "TotalPageCount": 1,
            "PrintQuality": args.quality, "PwgRaster": b"PwgRaster", "PrintContentOptimize": args.optimize.encode()}
    bad = {k: (got[k], v) for k, v in want.items() if got[k] != v}
    if bad:
        raise SystemExit(f"libcups read-back disagrees: {bad}")
    args.out.write_bytes(data)
    print(f"{args.out}: PWG {args.type} {w}x{h} @600, quality {args.quality}, optimize {args.optimize}, "
          f"{len(data):,} B, sha256 {hashlib.sha256(data).hexdigest()}; libcups read-back: {got}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
