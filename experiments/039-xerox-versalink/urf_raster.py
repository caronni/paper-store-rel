#!/usr/bin/env python3
"""e039 — Apple raster (URF) jobs for the `ipp-urf` footing.

The Xerox VersaLink C7130 (039.3b) exposes no PostScript: its only
network print path is IPP taking rasters at a fixed 600 dpi.  So the
raster IS the dot pattern.  This module turns a 1-bit 600 dpi render of
a page into a URF file the printer advertises support for: 8-bit luminance
grey (`W8`), black 0 / white 255, one page, simplex, print-quality
normal, 600 dpi — and places the A4 raster on the office's media by
exact integer offsets (no resampling).

    env/bin/python experiments/039-xerox-versalink/urf_raster.py \\
        page.ps out.urf --media legal            # A4 uncut on Legal, cut to 297 mm after
    env/bin/python experiments/039-xerox-versalink/urf_raster.py \\
        page.ps out.urf --media letter-centered  # 8.8 mm cut top and bottom
    env/bin/python experiments/039-xerox-versalink/urf_raster.py \\
        page.ps out.urf --media as-is            # the render's own page (A4 in a tray)

THE RENDER RULE (measured 2026-09-16, 039.3c): the K plane of a
`-sDEVICE=bitcmyk -r600` render, nothing else.  `pbmraw` HALFTONES: the
sheets paint with `setcmykcolor 0 0 0 1`, gs's ICC CMYK->grey makes 100 %
K a dark grey (pnggray shows it as 32), and a 1-bit device screens that
grey — plus-shaped single-dot holes on a staggered 4-row lattice in every
black area, the solid 8x8 corner satellites included.  That screened
render was printed as 039.3c and the print is INVALID as a
characterisation.  `bitcmyk` paints K=1 as a K dot with no colour
conversion at all (agrees with `pbmraw -dUseFastColor` and with
`pnggray < 128` to 0.02 % — vector-edge rounding, never a hole).  A
black-and-white sheet must carry NO C/M/Y ink: the render refuses if any
CMY plane has a dot ("real black, not warm black").  A .pbm input is
still accepted for the placement/encoding step alone.

Every write is decoded back and compared to the input before the file
is written (`--no-verify` skips it).  ghostscript's own `urfgray` device
is NOT used: measured 2026-09-16, it writes black as grey 32, which the
engine would halftone as an 87 % tone instead of solid ink.

Format (as ghostscript writes it and the printer reads it): magic
``UNIRAST\\0``, big-endian page count; per page a 32-byte header — bits
per pixel, colour space (0 = W luminance grey), duplex mode (1 =
one-sided), print quality (4 normal / 5 high), two reserved u32, width,
height, dpi, two reserved u32 — then the page's lines, each a repeat
byte (n = the line repeated n+1 times) followed by PackBits-style runs
of pixels: a count byte 0..127 repeats the next pixel count+1 times,
129..255 copies 257-count literal pixels, 128 fills the rest of the
line with white.  Nothing here prints — scripts/print_ipp_raster.sh
does, on the operator's go.
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

import numpy as np

HW_DPI = 600
DOTS = {"letter": (5100, 6600), "legal": (5100, 8400)}   # (width, height) at 600 dpi
A4_DOTS = (4960, 7016)


def read_pbm(path: Path) -> np.ndarray:
    """P4 (raw) PBM -> uint8 array of shape (h, w), 1 = black."""
    raw = path.read_bytes()
    if raw[:2] != b"P4":
        raise SystemExit(f"{path}: not a raw PBM (P4)")
    pos, toks = 2, []
    while len(toks) < 2:
        nl = raw.index(b"\n", pos)
        line = raw[pos:nl].strip()
        pos = nl + 1
        if line.startswith(b"#") or not line:
            continue
        toks += line.split()
    w, h = int(toks[0]), int(toks[1])
    rows = np.frombuffer(raw[pos:], dtype=np.uint8).reshape(h, -1)
    return np.unpackbits(rows, axis=1)[:, :w]


def render_k(ps: Path) -> np.ndarray:
    """K plane of ghostscript's bitcmyk render at 600 dpi, 1 = black.

    Two gs runs: bitcmyk (headerless 4 bits/pixel C,M,Y,K) for the dots and
    pbmraw for the page's pixel dimensions (same interpreter, same page).
    Refuses any C, M or Y ink."""
    import subprocess
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        cmyk, pbm = Path(tmp) / "p.bitcmyk", Path(tmp) / "p.pbm"
        for dev, out in (("bitcmyk", cmyk), ("pbmraw", pbm)):
            subprocess.run(["gs", "-q", "-dBATCH", "-dNOPAUSE", "-dSAFER", f"-r{HW_DPI}",
                            f"-sDEVICE={dev}", f"-sOutputFile={out}", str(ps)],
                           check=True, capture_output=True)
        h, w = read_pbm(pbm).shape
        raw = np.frombuffer(cmyk.read_bytes(), dtype=np.uint8)
    rowbytes = (w * 4 + 7) // 8
    if raw.size != rowbytes * h:
        raise SystemExit(f"{ps}: bitcmyk is {raw.size} B, expected {rowbytes * h} for {w}x{h}")
    planes = np.unpackbits(raw.reshape(h, rowbytes), axis=1)[:, :w * 4].reshape(h, w, 4)
    cmy = int(planes[:, :, :3].sum())
    if cmy:
        raise SystemExit(f"{ps}: {cmy} C/M/Y dots — a black-and-white sheet must be K only")
    return np.ascontiguousarray(planes[:, :, 3])


def load_page(path: Path) -> np.ndarray:
    return render_k(path) if path.suffix.lower() == ".ps" else read_pbm(path)


def place(bits: np.ndarray, media: str) -> np.ndarray:
    """Place an A4 1-bit page on the chosen media by whole dots only."""
    h, w = bits.shape
    if media == "as-is":
        return bits
    if (w, h) == (A4_DOTS[0] + 1, A4_DOTS[1]):
        # ghostscript rounds the true-A4 595.2756 pt discovery page to 4961
        # columns; the extra rightmost column lies past the 210 mm page edge
        bits, w = bits[:, :A4_DOTS[0]], A4_DOTS[0]
    if (w, h) != A4_DOTS:
        raise SystemExit(f"placement expects an A4 render {A4_DOTS}, got {(w, h)}")
    if media == "legal":
        W, H = DOTS["legal"]
        out = np.zeros((H, W), np.uint8)
        out[0:h, 70:70 + w] = bits            # top-aligned, x centred (70 dots = 2.96 mm)
        return out
    if media == "letter-centered":
        W, H = DOTS["letter"]
        out = np.zeros((H, W), np.uint8)
        out[:, 70:70 + w] = bits[208:208 + H, :]   # 208 dots = 8.8 mm cut top and bottom
        return out
    raise SystemExit(f"unknown media {media!r}")


def urf_encode_lines(img: np.ndarray) -> bytes:
    h, w = img.shape
    out = bytearray()
    y = 0
    while y < h:
        rep = 1
        while y + rep < h and rep < 256 and np.array_equal(img[y + rep], img[y]):
            rep += 1
        out.append(rep - 1)
        row = img[y].tobytes()
        n = len(row)
        x = 0
        while x < n:
            j = x + 1
            while j < n and j - x < 128 and row[j] == row[x]:
                j += 1
            if j - x >= 2:                       # repeat run
                out.append(j - x - 1)
                out.append(row[x])
                x = j
                continue
            j = x + 1                            # literal run up to the next repeat pair
            while j < n and j - x < 128 and not (j + 1 < n and row[j] == row[j + 1]):
                j += 1
            if j - x == 1:
                out.append(0)
                out.append(row[x])
            else:
                out.append(257 - (j - x))
                out += row[x:j]
            x = j
        y += rep
    return bytes(out)


def urf_decode_lines(data: bytes, w: int, h: int) -> tuple[np.ndarray, int]:
    i = 0
    out = np.empty((h, w), np.uint8)
    y = 0
    while y < h:
        rep = data[i] + 1
        i += 1
        line = bytearray()
        while len(line) < w:
            n = data[i]
            i += 1
            if n < 128:
                line += bytes([data[i]]) * (n + 1)
                i += 1
            elif n == 128:
                line += bytes([255]) * (w - len(line))
            else:
                cnt = 257 - n
                line += data[i:i + cnt]
                i += cnt
        out[y:y + rep] = np.frombuffer(bytes(line[:w]), np.uint8)
        y += rep
    return out, i


def urf_file(bits: np.ndarray, quality: int = 4) -> bytes:
    h, w = bits.shape
    img = np.where(bits == 1, 0, 255).astype(np.uint8)
    header = (b"UNIRAST\x00" + struct.pack(">I", 1)
              + struct.pack(">BBBBIIIIIII", 8, 0, 1, quality, 0, 0, w, h, HW_DPI, 0, 0))
    return header + urf_encode_lines(img)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pbm", type=Path, help="the page's .ps (rendered here, K plane of bitcmyk) or a 1-bit .pbm")
    ap.add_argument("out", type=Path, help="output .urf")
    ap.add_argument("--media", choices=("legal", "letter-centered", "as-is"), default="legal")
    ap.add_argument("--quality", type=int, choices=(4, 5), default=4)
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()
    bits = load_page(args.pbm)
    page = place(bits, args.media)
    data = urf_file(page, args.quality)
    if not args.no_verify:
        decoded, used = urf_decode_lines(data[44:], page.shape[1], page.shape[0])
        bad = int(((decoded == 0) != (page == 1)).sum())
        if bad or used != len(data) - 44:
            raise SystemExit(f"round-trip FAILED: {bad} mismatching pixels, "
                             f"{used} of {len(data) - 44} bytes consumed")
    args.out.write_bytes(data)
    print(f"{args.out}: {page.shape[1]}x{page.shape[0]} @ {HW_DPI} dpi W8, "
          f"{len(data):,} B, sha256 {hashlib.sha256(data).hexdigest()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# --- DeviceCMYK Apple raster (colour code 6, 32 bpp) — the unadvertised probe -------------
def urf_encode_pixels(img: np.ndarray, bpp_bytes: int) -> bytes:
    """URF line coding over WHOLE pixels of `bpp_bytes` octets (CUPS raster-stream.c):
    per line a repeat byte (count-1), then runs: 0..127 = next pixel repeated n+1
    times, 129..255 = 257-n literal pixels; 128 (fill) is never emitted."""
    h, w = img.shape[:2]
    flat = np.ascontiguousarray(img).reshape(h, w * bpp_bytes)
    out = bytearray()
    y = 0
    while y < h:
        rep = 1
        while y + rep < h and rep < 256 and np.array_equal(flat[y + rep], flat[y]):
            rep += 1
        out.append(rep - 1)
        row = flat[y].tobytes()
        px = [row[i:i + bpp_bytes] for i in range(0, len(row), bpp_bytes)]
        n = len(px)
        x = 0
        while x < n:
            j = x + 1
            while j < n and j - x < 128 and px[j] == px[x]:
                j += 1
            if j - x >= 2:
                out.append(j - x - 1)
                out += px[x]
                x = j
                continue
            j = x + 1
            while j < n and j - x < 128 and not (j + 1 < n and px[j] == px[j + 1]):
                j += 1
            if j - x == 1:
                out.append(0)
                out += px[x]
            else:
                out.append(257 - (j - x))
                out += b"".join(px[x:j])
            x = j
        y += rep
    return bytes(out)


def urf_decode_pixels(data: bytes, w: int, h: int, bpp_bytes: int) -> tuple[np.ndarray, int]:
    i = 0
    out = np.empty((h, w * bpp_bytes), np.uint8)
    y = 0
    while y < h:
        rep = data[i] + 1
        i += 1
        line = bytearray()
        while len(line) < w * bpp_bytes:
            n = data[i]
            i += 1
            if n < 128:
                line += data[i:i + bpp_bytes] * (n + 1)
                i += bpp_bytes
            elif n == 128:
                line += bytes([0]) * (w * bpp_bytes - len(line))
            else:
                cnt = (257 - n) * bpp_bytes
                line += data[i:i + cnt]
                i += cnt
        out[y:y + rep] = np.frombuffer(bytes(line[:w * bpp_bytes]), np.uint8)
        y += rep
    return out.reshape(h, w, bpp_bytes), i


def urf_cmyk_file(planes: np.ndarray, quality: int = 4) -> bytes:
    """planes (h, w, 4) uint8 C,M,Y,K with 1 = ink -> DEVCMYK32 URF, 0 = no ink, 255 = full."""
    h, w = planes.shape[:2]
    img = (planes.astype(np.uint8) * 255)
    header = (b"UNIRAST\x00" + struct.pack(">I", 1)
              + struct.pack(">BBBBIIIIIII", 32, 6, 1, quality, 0, 0, w, h, HW_DPI, 0, 0))
    return header + urf_encode_pixels(img, 4)
