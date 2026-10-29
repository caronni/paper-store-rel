#!/usr/bin/env python3
"""e039 — a PDF whose single page IS one full-page 1-bit-per-component
DeviceCMYK image: the colour route for the VersaLink C7130's PDF path.

    env/bin/python experiments/039-xerox-versalink/cmyk_pdf.py \\
        page.ps out.pdf --media legal [--preview out.png]

The page is rendered by ghostscript's `bitcmyk` device at 600 dpi (four
1-bit planes, C M Y K per pixel, rows byte-padded — the SAME sample layout
PDF prescribes for a /DeviceCMYK /BitsPerComponent 1 image, so the raster
bytes become the image stream after placement, Flate-compressed).  This is
the transcription of what the PostScript paints: the generator's colour
pages paint one 4-plane DeviceCMYK `image` (gen/ps.py put_cmyk_bitmap),
the discovery sheets per-plane image masks with pure setcmykcolor
primaries and, where declared, setoverprint — ghostscript follows the
language, and its bitcmyk render is the emission gate's own render.

Placement is by whole dots on the bitmap, never a PostScript translate
(039.3e).  MediaBox = the bitmap's size in points, the image covers the
page: a 600 dpi RIP maps one sample to one device dot with no arithmetic.
The written PDF is rendered back with ghostscript (bitcmyk) and compared
plane for plane before it is kept.  /Decode [0 1 ...]: a 1 bit = ink.

Whether the PRINTER treats DeviceCMYK as its own colourants (no colour
management, no K substitution) is the 039.4 question; this file only
guarantees the PDF says exactly what the PostScript said.  Nothing prints.
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from urf_raster import A4_DOTS, DOTS, read_pbm  # noqa: E402

HW_DPI = 600


def render_cmyk(ps: Path) -> np.ndarray:
    """(h, w, 4) uint8 planes C, M, Y, K of ghostscript's bitcmyk render, 1 = ink."""
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
    return np.ascontiguousarray(
        np.unpackbits(raw.reshape(h, rowbytes), axis=1)[:, :w * 4].reshape(h, w, 4))


def place_planes(planes: np.ndarray, media: str) -> np.ndarray:
    h, w = planes.shape[:2]
    if media == "as-is":
        return planes
    if (w, h) == (A4_DOTS[0] + 1, A4_DOTS[1]):
        planes, w = planes[:, :A4_DOTS[0]], A4_DOTS[0]   # gs's 4961st column, past the page edge
    if (w, h) != A4_DOTS:
        raise SystemExit(f"placement expects an A4 render {A4_DOTS}, got {(w, h)}")
    if media == "legal":
        W, H = DOTS["legal"]
        out = np.zeros((H, W, 4), np.uint8)
        out[0:h, 70:70 + w] = planes
        return out
    if media == "letter-centered":
        W, H = DOTS["letter"]
        out = np.zeros((H, W, 4), np.uint8)
        out[:, 70:70 + w] = planes[208:208 + H]
        return out
    raise SystemExit(f"unknown media {media!r}")


def pack_cmyk(planes: np.ndarray) -> bytes:
    h, w = planes.shape[:2]
    return np.packbits(planes.reshape(h, w * 4), axis=1).tobytes()


def cmyk_pdf(planes: np.ndarray) -> bytes:
    h, w = planes.shape[:2]
    data = zlib.compress(pack_cmyk(planes), 9)
    wpt, hpt = w * 72 / HW_DPI, h * 72 / HW_DPI
    content = f"q {wpt:.4f} 0 0 {hpt:.4f} 0 0 cm /Im0 Do Q".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {wpt:.4f} {hpt:.4f}] "
         f"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>").encode(),
        (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} "
         f"/ColorSpace /DeviceCMYK /BitsPerComponent 1 /Decode [0 1 0 1 0 1 0 1] "
         f"/Interpolate false /Filter /FlateDecode /Length {len(data)} >>\nstream\n").encode()
        + data + b"\nendstream",
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def verify(pdf: bytes, planes: np.ndarray) -> tuple[int, ...]:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.pdf"
        p.write_bytes(pdf)
        back = render_cmyk(p)
    if back.shape != planes.shape:
        raise SystemExit(f"render shape {back.shape} != planes {planes.shape}")
    return tuple(int((back[:, :, i] != planes[:, :, i]).sum()) for i in range(4))


def preview_rgb(planes: np.ndarray, scale: int = 1) -> np.ndarray:
    """Subtractive preview: white paper, C/M/Y/K inks (for eyeballing only)."""
    c, m, y, k = (planes[:, :, i].astype(np.float32) for i in range(4))
    r = (1 - c) * (1 - k)
    g = (1 - m) * (1 - k)
    b = (1 - y) * (1 - k)
    rgb = (np.stack([r, g, b], axis=-1) * 255).astype(np.uint8)
    return rgb[::scale, ::scale] if scale > 1 else rgb


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ps", type=Path, help="the page's .ps")
    ap.add_argument("out", type=Path, help="output .pdf")
    ap.add_argument("--media", choices=("legal", "letter-centered", "as-is"), default="legal")
    ap.add_argument("--preview", type=Path, default=None, help="write an RGB preview PNG (1/4 scale)")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()
    planes = place_planes(render_cmyk(args.ps), args.media)
    ink = [int(planes[:, :, i].sum()) for i in range(4)]
    pdf = cmyk_pdf(planes)
    if not args.no_verify:
        bad = verify(pdf, planes)
        if any(bad):
            raise SystemExit(f"round-trip FAILED: differing dots per plane C/M/Y/K = {bad}")
    args.out.write_bytes(pdf)
    if args.preview is not None:
        from PIL import Image
        Image.fromarray(preview_rgb(planes, 4)).save(args.preview, optimize=True)
    print(f"{args.out}: {planes.shape[1]}x{planes.shape[0]} DeviceCMYK 1-bpc image, ink dots C/M/Y/K = {ink}, "
          f"{len(pdf):,} B, sha256 {hashlib.sha256(pdf).hexdigest()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
