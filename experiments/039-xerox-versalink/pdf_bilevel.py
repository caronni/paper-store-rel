#!/usr/bin/env python3
"""e039 — a PDF whose single page IS one full-page 1-bit image mask, for the
VersaLink C7130's PDF path (039.3e).  Same placement law as urf_raster.py:
the bitmap already holds the page at 600 dpi (Legal 5100x8400, Letter
5100x6600, or the A4 render as-is); the PDF's MediaBox is that bitmap's
size in points (dots * 72/600, exact in binary for these sizes) and the
image mask is drawn over the whole page, so a 600 dpi RIP maps one sample
to one device dot with no placement arithmetic.  Flate-compressed, 1 bit
per sample, /Decode [1 0] so a 1 bit paints black (the PBM convention).

    env/bin/python experiments/039-xerox-versalink/pdf_bilevel.py \\
        page.ps out.pdf --media legal

The written PDF is rendered back with ghostscript at 600 dpi and compared
bit for bit to the bitmap before the file is kept (`--no-verify` skips).
Nothing here prints.
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
from urf_raster import load_page, place, read_pbm  # noqa: E402

HW_DPI = 600


def bilevel_pdf(bits: np.ndarray) -> bytes:
    h, w = bits.shape
    packed = np.packbits(bits.astype(np.uint8), axis=1).tobytes()
    data = zlib.compress(packed, 9)
    wpt, hpt = w * 72 / HW_DPI, h * 72 / HW_DPI
    content = f"q {wpt:.4f} 0 0 {hpt:.4f} 0 0 cm /Im0 Do Q".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {wpt:.4f} {hpt:.4f}] "
         f"/Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>").encode(),
        (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ImageMask true "
         f"/Decode [1 0] /BitsPerComponent 1 /Filter /FlateDecode /Length {len(data)} >>\n"
         "stream\n").encode() + data + b"\nendstream",
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
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    return bytes(out)


def verify(pdf: bytes, bits: np.ndarray) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.pdf"
        p.write_bytes(pdf)
        o = Path(tmp) / "x.pbm"
        subprocess.run(["gs", "-q", "-dBATCH", "-dNOPAUSE", "-dSAFER", "-r600",
                        "-sDEVICE=pbmraw", f"-sOutputFile={o}", str(p)], check=True)
        back = read_pbm(o)
    if back.shape != bits.shape:
        raise SystemExit(f"render shape {back.shape[::-1]} != bitmap {bits.shape[::-1]}")
    return int((back != bits).sum())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pbm", type=Path, help="the page's .ps (K plane of a bitcmyk render) or a 1-bit .pbm")
    ap.add_argument("out", type=Path)
    ap.add_argument("--media", choices=("legal", "letter-centered", "as-is"), default="legal")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()
    page = place(load_page(args.pbm), args.media)
    pdf = bilevel_pdf(page)
    if not args.no_verify:
        bad = verify(pdf, page)
        if bad:
            raise SystemExit(f"round-trip FAILED: {bad} mismatching dots after gs render")
    args.out.write_bytes(pdf)
    print(f"{args.out}: {page.shape[1]}x{page.shape[0]} 1-bit image mask, {len(pdf):,} B, "
          f"sha256 {hashlib.sha256(pdf).hexdigest()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
