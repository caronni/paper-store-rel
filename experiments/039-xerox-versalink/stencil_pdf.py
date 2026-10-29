#!/usr/bin/env python3
"""e039 — colour PDFs built as LINE ART rather than a picture: one /ImageMask
stencil per plane, painted with a solid 100 % fill of one colourant, planes
overprinting (ExtGState /OP true /op true /OPM 1).  Two fill colour spaces:

    --space devicecmyk   fills 1 0 0 0 / 0 1 0 0 / 0 0 1 0 / 0 0 0 1 k
    --space separation   fills in /Separation /Cyan, /Magenta, /Yellow, /Black
                         (named process separations; tint transform to DeviceCMYK)

    env/bin/python experiments/039-xerox-versalink/stencil_pdf.py page.ps out.pdf --media legal --space devicecmyk

A RIP screens a *picture*; a stencil is a fill through a mask and many RIPs
route a 100 % single-colourant fill straight to the colourant with no
halftone (a screen at 100 % is solid) — that is the hypothesis this probe
tests against the composite-image PDF of cmyk_pdf.py (039.3j, screened).
Verified by ghostscript: the PDF renders (bitcmyk, overprint honoured) to
exactly the planes of the PostScript.  Nothing prints.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmyk_pdf import HW_DPI, place_planes, render_cmyk, verify  # noqa: E402

PLANES = ("C", "M", "Y", "K")
FILL_CMYK = {"C": "1 0 0 0", "M": "0 1 0 0", "Y": "0 0 1 0", "K": "0 0 0 1"}
SEP_NAME = {"C": "Cyan", "M": "Magenta", "Y": "Yellow", "K": "Black"}


def stencil_pdf(planes: np.ndarray, space: str) -> bytes:
    h, w = planes.shape[:2]
    wpt, hpt = w * 72 / HW_DPI, h * 72 / HW_DPI
    objs: list[bytes] = []

    def add(body: bytes) -> int:
        objs.append(body)
        return len(objs)

    add(b"")  # 1 catalog (filled later)
    add(b"")  # 2 pages
    add(b"")  # 3 page
    gs_id = add(b"<< /Type /ExtGState /OP true /op true /OPM 1 >>")
    masks, cs_objs, content = {}, {}, ["q /GSop gs"]
    for i, p in enumerate(PLANES):
        bits = planes[:, :, i]
        if not bits.any():
            continue
        data = zlib.compress(np.packbits(bits.astype(np.uint8), axis=1).tobytes(), 9)
        masks[p] = add((f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ImageMask true "
                        f"/Decode [1 0] /BitsPerComponent 1 /Interpolate false /Filter /FlateDecode "
                        f"/Length {len(data)} >>\nstream\n").encode() + data + b"\nendstream")
        if space == "separation":
            # tint transform: t -> the one DeviceCMYK component
            # PostScript calculator: input t on the stack, output c m y k
            fn = {"C": "{ 0 0 0 }", "M": "{ 0 exch 0 0 }", "Y": "{ 0 0 3 -1 roll 0 }", "K": "{ 0 0 0 4 -1 roll }"}[p]
            fn_id = add((f"<< /FunctionType 4 /Domain [0 1] /Range [0 1 0 1 0 1 0 1] /Length {len(fn)} >>\nstream\n"
                         f"{fn}\nendstream").encode())
            cs_objs[p] = add(f"[/Separation /{SEP_NAME[p]} /DeviceCMYK {fn_id} 0 R]".encode())
            content.append(f"/CS{p} cs 1 sc")
        else:
            content.append(f"{FILL_CMYK[p]} k")
        content.append(f"q {wpt:.4f} 0 0 {hpt:.4f} 0 0 cm /Im{p} Do Q")
    content.append("Q")
    cbytes = "\n".join(content).encode()
    cid = add(f"<< /Length {len(cbytes)} >>\nstream\n".encode() + cbytes + b"\nendstream")
    xobj = " ".join(f"/Im{p} {i} 0 R" for p, i in masks.items())
    csd = (" /ColorSpace << " + " ".join(f"/CS{p} {i} 0 R" for p, i in cs_objs.items()) + " >>") if cs_objs else ""
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    objs[2] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {wpt:.4f} {hpt:.4f}] "
               f"/Resources << /ExtGState << /GSop {gs_id} 0 R >> /XObject << {xobj} >>{csd} >> "
               f"/Contents {cid} 0 R >>").encode()
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ps", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--media", choices=("legal", "letter-centered", "as-is"), default="legal")
    ap.add_argument("--space", choices=("devicecmyk", "separation"), default="devicecmyk")
    ap.add_argument("--no-verify", action="store_true")
    args = ap.parse_args()
    planes = place_planes(render_cmyk(args.ps), args.media)
    pdf = stencil_pdf(planes, args.space)
    if not args.no_verify:
        bad = verify(pdf, planes)
        if any(bad):
            raise SystemExit(f"round-trip FAILED: differing dots per plane C/M/Y/K = {bad}")
    args.out.write_bytes(pdf)
    print(f"{args.out}: stencil PDF ({args.space}), {planes.shape[1]}x{planes.shape[0]}, {len(pdf):,} B, "
          f"sha256 {hashlib.sha256(pdf).hexdigest()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
