#!/usr/bin/env python3
"""e039 — the labelled COLOUR ROUTE PROBE page: one Legal sheet, one test
pattern drawn by eight PDF constructions side by side, every panel and the
sheet itself labelled in plain text so the printouts can be told apart.

    env/bin/python experiments/039-xerox-versalink/probe_page.py OUTDIR \\
        --variant "quality normal, optimize auto" [--pwg]

Pattern (per panel, 700x700 dots ≈ 30 mm): a column per plane C, M, Y, K
with a solid block, a random 2x2-cell field, 1-on/1-off gratings (H and V),
isolated single dots on an 8-dot pitch; then overprint blocks C+M, C+Y,
M+Y, C+M+Y and overlapping random fields of C, M and Y (the payload case).
Constructions:
  1 image        one /DeviceCMYK /BitsPerComponent 1 image (cmyk_pdf.py's)
  2 image+HT     the same with an ExtGState /HT (600 lpi, 0°, /SimpleDot) and identity /TR
  3 stencil      per-plane /ImageMask, 100 % DeviceCMYK fill, /OP /OPM 1 (overprint)
  4 stencil-ko   the same WITHOUT overprint (knockout control)
  5 separation   per-plane /ImageMask filled in /Separation /Cyan /Magenta /Yellow /Black
  6 separation-ko the Separation fills WITHOUT overprint (knockout control for 5)
  7 vector       one filled rectangle per horizontal run of cells, per plane, overprint
  8 indexed      one /Indexed [/DeviceCMYK] image, 8-bit, palette = the 16 C/M/Y/K combinations
  9 state-cmyk   one /ImageMask per INK STATE (C, M, Y, CM, CY, MY, CMY, K — disjoint), each a pure
                 DeviceCMYK fill, painted once, NO overprint needed
 10 state-devn   the same disjoint state masks filled in /DeviceN [/Cyan /Magenta /Yellow] (K in DeviceCMYK)
--ht1x1 applies, page-wide, an ExtGState /HT of HalftoneType 5 whose every colourant is a
1x1 HalftoneType 6 threshold array (threshold 128) with /TR /Identity: if the RIP honours
job halftones, every colour-converted value is thresholded back to solid-or-nothing.
Labels are Helvetica in 100 % K.  Verified: ghostscript renders the PDF
(bitcmyk) and each panel is compared plane for plane to the pattern.
--pwg also writes the same page as a PWG raster cmyk_8 with the labels
rasterised.  Nothing prints.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cmyk_pdf import HW_DPI, preview_rgb, render_cmyk  # noqa: E402

PAGE = (5100, 8400)          # Legal at 600 dpi, (w, h)
PANEL = 700                  # dots
PLANE_IDX = {"C": 0, "M": 1, "Y": 2, "K": 3}
NAMES = {"C": "Cyan", "M": "Magenta", "Y": "Yellow", "K": "Black"}
FILL = {"C": (1, 0, 0, 0), "M": (0, 1, 0, 0), "Y": (0, 0, 1, 0), "K": (0, 0, 0, 1)}


def pattern(seed: int = 39) -> np.ndarray:
    rng = np.random.default_rng(seed)
    P = np.zeros((PANEL, PANEL, 4), np.uint8)
    B = 120
    for col, p in enumerate("CMYK"):
        x0 = 20 + col * 160
        i = PLANE_IDX[p]
        P[20:20 + B, x0:x0 + B, i] = 1                                            # solid
        cells = rng.integers(0, 2, (B // 2, B // 2)).astype(np.uint8)
        P[160:160 + B, x0:x0 + B, i] = np.kron(cells, np.ones((2, 2), np.uint8))   # random 2x2 cells
        P[300:300 + 56, x0:x0 + B, i] = (np.arange(56)[:, None] % 2 == 0)         # H grating 1-on/1-off
        P[364:364 + 56, x0:x0 + B, i] = (np.arange(B)[None, :] % 2 == 0)          # V grating
        d = np.zeros((B, B), np.uint8); d[4::8, 4::8] = 1
        P[440:440 + B, x0:x0 + B, i] = d                                          # isolated single dots
    # overprint row: C+M, C+Y, M+Y, C+M+Y solid; then overlapping random fields of C, M, Y
    y0 = 580
    for k, combo in enumerate(("CM", "CY", "MY", "CMY")):
        x0 = 20 + k * 100
        for p in combo:
            P[y0:y0 + 100, x0:x0 + 100, PLANE_IDX[p]] = 1
    for p in "CMY":
        cells = rng.integers(0, 2, (50, 100)).astype(np.uint8)
        P[y0:y0 + 100, 440:440 + 200, PLANE_IDX[p]] = np.kron(cells, np.ones((2, 2), np.uint8))
    return P


# --- PDF building blocks --------------------------------------------------------------
class PDF:
    def __init__(self) -> None:
        self.objs: list[bytes] = []

    def add(self, body: bytes) -> int:
        self.objs.append(body)
        return len(self.objs)

    def stream(self, dict_body: str, data: bytes) -> int:
        return self.add(f"<< {dict_body} /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream")

    def finish(self, root: int) -> bytes:
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offs = []
        for i, body in enumerate(self.objs, 1):
            offs.append(len(out))
            out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(self.objs) + 1}\n0000000000 65535 f \n".encode()
        for o in offs:
            out += f"{o:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(self.objs) + 1} /Root {root} 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)


def pt(d: float) -> float:
    return d * 72 / HW_DPI


def mask_xobj(pdf: PDF, bits: np.ndarray) -> int:
    h, w = bits.shape
    data = zlib.compress(np.packbits(bits.astype(np.uint8), axis=1).tobytes(), 9)
    return pdf.stream(f"/Type /XObject /Subtype /Image /Width {w} /Height {h} /ImageMask true /Decode [1 0] "
                      f"/BitsPerComponent 1 /Interpolate false /Filter /FlateDecode", data)


def cmyk_image_xobj(pdf: PDF, planes: np.ndarray) -> int:
    h, w = planes.shape[:2]
    data = zlib.compress(np.packbits(planes.reshape(h, w * 4), axis=1).tobytes(), 9)
    return pdf.stream(f"/Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceCMYK "
                      f"/BitsPerComponent 1 /Decode [0 1 0 1 0 1 0 1] /Interpolate false /Filter /FlateDecode", data)


def indexed_image_xobj(pdf: PDF, planes: np.ndarray) -> int:
    h, w = planes.shape[:2]
    idx = (planes[:, :, 0] * 8 + planes[:, :, 1] * 4 + planes[:, :, 2] * 2 + planes[:, :, 3]).astype(np.uint8)
    palette = bytes(255 * ((n >> s) & 1) for n in range(16) for s in (3, 2, 1, 0))
    data = zlib.compress(idx.tobytes(), 9)
    pal_hex = palette.hex()
    return pdf.stream(f"/Type /XObject /Subtype /Image /Width {w} /Height {h} "
                      f"/ColorSpace [/Indexed /DeviceCMYK 15 <{pal_hex}>] /BitsPerComponent 8 /Interpolate false /Filter /FlateDecode", data)


def draw_xobj(name: str, x: int, y_top: int, w: int, h: int) -> str:
    """content-stream fragment placing an XObject whose top-left is at (x, y_top) dots."""
    y_bot = PAGE[1] - y_top - h
    return f"q {pt(w):.4f} 0 0 {pt(h):.4f} {pt(x):.4f} {pt(y_bot):.4f} cm /{name} Do Q"


def runs(bits: np.ndarray):
    for r in range(bits.shape[0]):
        row = bits[r]
        x = 0
        n = len(row)
        while x < n:
            if row[x]:
                j = x
                while j < n and row[j]:
                    j += 1
                yield r, x, j - x
                x = j
            else:
                x += 1


def build_page(P: np.ndarray, variant: str, title_extra: str = "", ht1x1: bool = False) -> tuple[bytes, list[tuple[str, int, int]]]:
    pdf = PDF()
    pdf.add(b"")  # 1 catalog
    pdf.add(b"")  # 2 pages
    pdf.add(b"")  # 3 page
    font = pdf.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    gs_op = pdf.add(b"<< /Type /ExtGState /OP true /op true /OPM 1 >>")
    gs_ht = pdf.add(b"<< /Type /ExtGState /HT << /Type /Halftone /HalftoneType 1 /Frequency 600 /Angle 0 /SpotFunction /SimpleDot >> /TR /Identity >>")
    thr = pdf.stream("/Type /Halftone /HalftoneType 6 /Width 1 /Height 1", bytes([128]))
    gs_ht5 = pdf.add((f"<< /Type /ExtGState /HT << /Type /Halftone /HalftoneType 5 /Default {thr} 0 R "
                      f"/Cyan {thr} 0 R /Magenta {thr} 0 R /Yellow {thr} 0 R /Black {thr} 0 R >> /TR /Identity >>").encode())
    xobjs, cspaces, content = {}, {}, ([] if not ht1x1 else ["/GSht5 gs"])
    panels: list[tuple[str, int, int]] = []   # (name, x, y_top)
    cols = 2
    x_step, y_step = 2200, 1000
    x_org, y_org = 300, 700
    # per-state masks: disjoint by construction (K is its own state; the pattern keeps K apart from CMY)
    state = (P[:, :, 0] + 2 * P[:, :, 1] + 4 * P[:, :, 2]).astype(np.uint8)
    state_masks = {}
    for sidx in range(1, 8):
        m = (state == sidx) & (P[:, :, 3] == 0)
        if m.any():
            state_masks[f"S{sidx}"] = mask_xobj(pdf, m.astype(np.uint8))
    if P[:, :, 3].any():
        state_masks["SK"] = mask_xobj(pdf, P[:, :, 3])
    xobjs.update(state_masks)
    fidn = pdf.stream("/FunctionType 4 /Domain [0 1 0 1 0 1] /Range [0 1 0 1 0 1 0 1]", b"{ 0 }")
    cspaces["DevN3"] = pdf.add(f"[/DeviceN [/Cyan /Magenta /Yellow] /DeviceCMYK {fidn} 0 R]".encode())
    constructions = ["image", "image+HT", "stencil", "stencil-ko", "separation", "separation-ko", "vector", "indexed",
                     "state-cmyk", "state-devn"]
    h, w = P.shape[:2]
    masks = {p: mask_xobj(pdf, P[:, :, PLANE_IDX[p]]) for p in "CMYK"}
    for p in "CMYK":
        xobjs[f"M{p}"] = masks[p]
    xobjs["IMG"] = cmyk_image_xobj(pdf, P)
    xobjs["IDX"] = indexed_image_xobj(pdf, P)
    for p in "CMYK":
        fn = {"C": "{ 0 0 0 }", "M": "{ 0 exch 0 0 }", "Y": "{ 0 0 3 -1 roll 0 }", "K": "{ 0 0 0 4 -1 roll }"}[p]
        fid = pdf.stream("/FunctionType 4 /Domain [0 1] /Range [0 1 0 1 0 1 0 1]", fn.encode())
        cspaces[f"Sep{p}"] = pdf.add(f"[/Separation /{NAMES[p]} /DeviceCMYK {fid} 0 R]".encode())
    lines = [(24, "e039 COLOUR ROUTE PROBE  -  PDF" + ("  -  page-wide 1x1 threshold halftone" if ht1x1 else "")), (18, f"sent with: {variant}"),
             (11, "Xerox VersaLink C7130 over IPP, 2026-09-17.  Same pattern in every panel,"),
             (11, "different PDF construction.  Loupe the pure C / M / Y blocks: one toner each?")]
    if title_extra:
        lines.append((11, title_extra))
    yy = 200
    for size, text in lines:
        yy += int(size * HW_DPI / 72 * 1.35)
        content.append(f"BT /F1 {size} Tf {pt(300):.2f} {pt(PAGE[1] - yy):.2f} Td ({text}) Tj ET")
    for n, name in enumerate(constructions):
        x = x_org + (n % cols) * x_step
        y = y_org + (n // cols) * y_step
        panels.append((name, x, y))
        content.append(f"BT /F1 28 Tf {pt(x):.2f} {pt(PAGE[1] - y + 120):.2f} Td ({n + 1}  {name}) Tj ET")
        if name == "image":
            content.append(draw_xobj("IMG", x, y, w, h))
        elif name == "image+HT":
            content.append(f"q /GSht gs {draw_xobj('IMG', x, y, w, h)} Q")
        elif name in ("stencil", "stencil-ko"):
            content.append("q" + (" /GSop gs" if name == "stencil" else ""))
            for p in "CMYK":
                content.append("%d %d %d %d k %s" % (*FILL[p], draw_xobj(f"M{p}", x, y, w, h)))
            content.append("Q")
        elif name in ("separation", "separation-ko"):
            content.append("q" + (" /GSop gs" if name == "separation" else ""))
            for p in "CMYK":
                content.append(f"/Sep{p} cs 1 sc {draw_xobj(f'M{p}', x, y, w, h)}")
            content.append("Q")
        elif name == "vector":
            content.append("q /GSop gs")
            for p in "CMYK":
                bits = P[:, :, PLANE_IDX[p]]
                content.append("%d %d %d %d k" % FILL[p])
                for r, c, ln in runs(bits):
                    content.append(f"{pt(x + c):.4f} {pt(PAGE[1] - y - r - 1):.4f} {pt(ln):.4f} {pt(1):.4f} re")
                content.append("f")
            content.append("Q")
        elif name == "indexed":
            content.append(draw_xobj("IDX", x, y, w, h))
        elif name in ("state-cmyk", "state-devn"):
            content.append("q")
            for key in state_masks:
                if key == "SK":
                    content.append(f"0 0 0 1 k {draw_xobj('SK', x, y, w, h)}")
                    continue
                sidx = int(key[1:])
                c, m, yy_ = sidx & 1, (sidx >> 1) & 1, (sidx >> 2) & 1
                if name == "state-cmyk":
                    content.append(f"{c} {m} {yy_} 0 k {draw_xobj(key, x, y, w, h)}")
                else:
                    content.append(f"/DevN3 cs {c} {m} {yy_} sc {draw_xobj(key, x, y, w, h)}")
            content.append("Q")
    cbytes = "\n".join(content).encode()
    cid = pdf.stream("", cbytes)
    xo = " ".join(f"/{k} {v} 0 R" for k, v in xobjs.items())
    cs = " ".join(f"/{k} {v} 0 R" for k, v in cspaces.items())
    pdf.objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    pdf.objs[1] = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    pdf.objs[2] = (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {pt(PAGE[0]):.4f} {pt(PAGE[1]):.4f}] "
                   f"/Resources << /Font << /F1 {font} 0 R >> /ExtGState << /GSop {gs_op} 0 R /GSht {gs_ht} 0 R /GSht5 {gs_ht5} 0 R >> "
                   f"/XObject << {xo} >> /ColorSpace << {cs} >> >> /Contents {cid} 0 R >>").encode()
    return pdf.finish(1), panels


def knockout(P: np.ndarray) -> np.ndarray:
    """Expected planes when C, M, Y, K are painted in that order WITHOUT overprint:
    a later plane's dot clears the earlier planes there."""
    Q = P.copy()
    for i in range(4):
        later = P[:, :, i + 1:].any(axis=2)
        Q[:, :, i] &= ~later
    return Q


def verify_panels(pdf: bytes, P: np.ndarray, panels: list[tuple[str, int, int]]) -> tuple[dict, np.ndarray]:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "p.pdf"
        f.write_bytes(pdf)
        planes = render_cmyk(f)
    out = {}
    h, w = P.shape[:2]
    KO = knockout(P)
    for name, x, y in panels:
        want = KO if name.endswith("-ko") else P
        r = planes[y:y + h, x:x + w]
        out[name] = tuple(int((r[:, :, i] != want[:, :, i]).sum()) for i in range(4))
    return out, planes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outdir", type=Path)
    ap.add_argument("--variant", default="quality normal, optimize auto", help="the job attributes this sheet will be sent with (goes into the title)")
    ap.add_argument("--tag", default="normal-auto", help="file name tag")
    ap.add_argument("--pwg", action="store_true", help="also write the page as PWG raster cmyk_8 with rasterised labels")
    ap.add_argument("--ht1x1", action="store_true", help="page-wide HalftoneType 5 with 1x1 threshold arrays (job-halftone probe)")
    args = ap.parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    P = pattern()
    pdf, panels = build_page(P, args.variant, ht1x1=args.ht1x1)
    mism, planes = verify_panels(pdf, P, panels)
    bad = {k: v for k, v in mism.items() if any(v)}
    if bad:
        raise SystemExit(f"gs round-trip: panels differ from the pattern: {bad}")
    out = args.outdir / f"probe-page-pdf-{args.tag}.pdf"
    out.write_bytes(pdf)
    from PIL import Image
    Image.fromarray(preview_rgb(planes, 4)).save(args.outdir / f"probe-page-pdf-{args.tag}-preview.png", optimize=True)
    print(f"{out}: {len(pdf):,} B, sha256 {hashlib.sha256(pdf).hexdigest()}; all {len(panels)} panels render exactly (knockout controls as knockout)", file=sys.stderr)
    if args.pwg:
        from PIL import ImageDraw, ImageFont
        from pwg_raster import libcups_read, pwg_file
        import tempfile
        # the same page as planes, labels rasterised into K
        page = np.zeros((PAGE[1], PAGE[0], 4), np.uint8)
        for name, x, y in panels:
            page[y:y + PANEL, x:x + PANEL] = P
        lab = Image.new("L", (PAGE[0], PAGE[1]), 0)
        d = ImageDraw.Draw(lab)
        try:
            big = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 150)
            small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 100)
        except Exception:
            big = small = ImageFont.load_default()
        d.text((300, 120), "e039 COLOUR ROUTE PROBE  -  PWG RASTER cmyk_8", fill=255, font=big)
        d.text((300, 300), "sent with: " + args.variant, fill=255, font=small)
        d.text((300, 430), "same 8 panels as the PDF sheet, but ONE raster: every panel is identical data here", fill=255, font=small)
        for n, (name, x, y) in enumerate(panels):
            d.text((x, y - 160), f"{n + 1}  {name}", fill=255, font=small)
        page[:, :, 3] |= (np.asarray(lab) > 128).astype(np.uint8)
        data = pwg_file(page, "cmyk_8", 4, "auto")
        with tempfile.NamedTemporaryFile(suffix=".pwg", delete=False) as t:
            t.write(data)
            tmp = Path(t.name)
        got = libcups_read(tmp)
        tmp.unlink()
        assert (got["Width"], got["Height"], got["ColorSpace"], got["BitsPerPixel"]) == (PAGE[0], PAGE[1], 6, 32), got
        outp = args.outdir / f"probe-page-pwg-cmyk8-{args.tag}.pwg"
        outp.write_bytes(data)
        Image.fromarray(preview_rgb(page, 4)).save(args.outdir / f"probe-page-pwg-cmyk8-{args.tag}-preview.png", optimize=True)
        print(f"{outp}: {len(data):,} B, sha256 {hashlib.sha256(data).hexdigest()}; libcups header OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
