#!/usr/bin/env python3
"""e041 S4 — one sheet as ONE PWG raster (PWG 5102.4) cmyk_8 page for the
HP Color LaserJet Pro MFP M281fdw over raw TCP 9100.

    env/bin/python experiments/041-m281-screen-routes/pwg_job.py \\
        <F gen dir> experiments/041-m281-screen-routes/build/S4-pwg-cmyk8

writes <stem>.pwg, <stem>.pjl (UEL, @PJL JOB, ENTER LANGUAGE=PWG_RASTER, the
.pwg, UEL, @PJL EOJ, UEL), <stem>.manifest.json: the ground truth (C/M/Y, 1 =
ink) by whole dots on blank A4 at the PostScript's own origin, K = 0, octets
0/255, in e039's header and line coding (A4 PageSizeName, AlternatePrimary as
libcups writes it).  Written only once the shas match the sheet manifest, the
gs bitcmyk render equals the page, libcups reads every header field back as
intended (all others zero), the header differs from libcups's own PWG writer
only in the named words, and both decoders (strict here, libcups's) return
the page exactly.  Nothing prints.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
import re
import struct
import sys
import tempfile
from pathlib import Path

import numpy as np

E039 = Path(__file__).resolve().parents[1] / "039-xerox-versalink"
sys.path.insert(0, str(E039))
from cmyk_pdf import render_cmyk  # noqa: E402
from pwg_raster import HW_DPI, OPTIMIZE, SYNC, _Hdr2, pwg_header  # noqa: E402
from urf_raster import A4_DOTS, urf_encode_pixels  # noqa: E402

PAGE_NAME = "iso_a4_210x297mm"
UEL = b"\x1b%-12345X"
HDR_OCTETS = 1796
ALT_PRIMARY_AT = 480                  # header octet of cupsInteger[7] = PWG AlternatePrimary
EXPECTED_VS_LIBCUPS = {               # header octet: why this word differs from libcups's PWG writer
    292: "ImagingBoundingBox[2]: PWG reserved, 0 (e039); libcups writes 595",
    296: "ImagingBoundingBox[3]: PWG reserved, 0 (e039); libcups writes 841",
    376: "Height: 7016 = the PostScript's 841.92 pt page; libcups truncates 297 mm to 7015",
    484: "PrintQuality: set here; libcups's writer does not carry cupsInteger[8]",
}
UNVERIFIED = (
    "@PJL ENTER LANGUAGE=PWG_RASTER: spelled as INFO CONFIG LANGUAGES lists it; PERSONALITY shows that slot as \"?\"",
    "whether the bare .pwg is auto-sensed on 9100 (PERSONALITY=AUTO) by its RaS2 sync word",
    "whether the M281 takes cmyk_8 as device colourants: the VersaLink C7130 printed PWG cmyk_8 as its K "
    "octet alone, as luminance (e039 039.3t a.tiff, K = 0 printed dark grey); pwg-raster-document-type-supported not queried",
    "whether 0/255 reaches the halftoner unconverted (no CMYK->CMYK conversion, ink limit or GCR on 200-300 % cells)",
)
_LIB = ctypes.CDLL(ctypes.util.find_library("cups"))
_LIB.cupsRasterOpen.restype = _LIB.pwgMediaForPWG.restype = ctypes.c_void_p


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_sheet(sheet: Path) -> tuple[dict, np.ndarray, Path]:
    page = json.loads((sheet / "manifest.json").read_text())["pages"][0]
    packed, ps = np.load(sheet / page["gt"]), sheet / page["ps"]
    got = {"gt_sha256": sha256(packed.tobytes()), "gt_plane_sha256": [sha256(p.tobytes()) for p in packed],
           "ps_sha256": sha256(ps.read_bytes()), "gt_packed_shape": list(packed.shape)}
    bad = [k for k, v in got.items() if v != page[k]]
    if bad or page["gt_plane_order"] != ["C", "M", "Y"] or page["gt_bitorder"] != "big":
        raise SystemExit(f"{sheet}: ground truth / PostScript disagree with the sheet manifest: {bad}")
    return got, np.unpackbits(packed, axis=2, bitorder="big"), ps


def ps_origin(ps: Path, field_hw: tuple[int, int]) -> tuple[int, int]:
    """(top, left) dots of the image on the page, from the PostScript's own numbers."""
    head = ps.open("rb").read(4096).decode("ascii", "replace")
    num = r"([\d.]+) ([\d.]+)"
    (pw, ph), (tx, ty), (sx, sy) = (map(float, re.search(p, head).groups()) for p in (
        rf"/PageSize \[{num}\]", rf"{num} translate", rf"{num} scale"))
    dots = [v * HW_DPI / 72 for v in (pw, ph, ty + sy, tx, sx, sy)]
    if any(abs(d - round(d)) > 1e-6 for d in dots):
        raise SystemExit(f"{ps}: page/translate/scale are not whole 600-dpi dots: {dots}")
    W, H, top_edge, left, w, h = (round(d) for d in dots)
    if (W, H) != A4_DOTS or (h, w) != field_hw:
        raise SystemExit(f"{ps}: page {(W, H)} / image {(h, w)} != A4 {A4_DOTS} / GT {field_hw}")
    return H - top_edge, left


def build_page(gt: np.ndarray, top: int, left: int) -> np.ndarray:
    """(h, w, 4) uint8 C, M, Y, K with 1 = ink: the GT on blank A4, K = 0."""
    page = np.zeros((A4_DOTS[1], A4_DOTS[0], 4), np.uint8)
    page[top:top + gt.shape[1], left:left + gt.shape[2], :3] = np.moveaxis(gt, 0, -1)
    return page


def libcups_reference(quality: int, optimize: str) -> bytes:
    """The header libcups's own PWG writer emits for A4 cmyk_8 600x600 with the same job fields."""
    h = _Hdr2()
    if not _LIB.cupsRasterInitPWGHeader(ctypes.byref(h), ctypes.c_void_p(_LIB.pwgMediaForPWG(PAGE_NAME.encode())),
                                        b"cmyk_8", HW_DPI, HW_DPI, b"one-sided", None):
        raise SystemExit("libcups: cupsRasterInitPWGHeader refused A4 cmyk_8")
    h.MediaType, h.OutputType, h.NumCopies = b"stationery", optimize.encode(), 1
    h.cupsInteger[0], h.cupsInteger[8] = 1, quality
    with tempfile.TemporaryDirectory() as tmp:
        fd = os.open(path := Path(tmp) / "ref.pwg", os.O_WRONLY | os.O_CREAT, 0o600)
        ras = ctypes.c_void_p(_LIB.cupsRasterOpen(fd, 3))    # CUPS_RASTER_WRITE_PWG
        ok = _LIB.cupsRasterWriteHeader2(ras, ctypes.byref(h))
        _LIB.cupsRasterClose(ras)
        os.close(fd)
        ref = path.read_bytes()
    if not ok or ref[:4] != SYNC or len(ref) != 4 + HDR_OCTETS:
        raise SystemExit("libcups: the reference PWG header write failed")
    return ref[4:]


def _plain(v):
    return v.decode("ascii") if isinstance(v, bytes) else [_plain(x) for x in v] if isinstance(v, ctypes.Array) else v


def libcups_decode(path: Path) -> tuple[dict, np.ndarray, int]:
    """Every header field and the page's pixels as libcups reads them; 1 if a second page header follows."""
    fd = os.open(path, os.O_RDONLY)
    ras = ctypes.c_void_p(_LIB.cupsRasterOpen(fd, 0))    # CUPS_RASTER_READ
    hdr = _Hdr2()
    if not ras or not _LIB.cupsRasterReadHeader2(ras, ctypes.byref(hdr)):
        raise SystemExit("libcups: cupsRasterReadHeader2 rejected the header")
    fields = {n: _plain(getattr(hdr, n)) for n, _ in _Hdr2._fields_}
    bpl = hdr.cupsBytesPerLine
    px = np.empty((hdr.cupsHeight, bpl), np.uint8)
    for y in range(hdr.cupsHeight):
        if _LIB.cupsRasterReadPixels(ras, ctypes.c_void_p(px[y].ctypes.data), bpl) != bpl:
            raise SystemExit(f"libcups: short read at line {y}")
    more = int(bool(_LIB.cupsRasterReadHeader2(ras, ctypes.byref(hdr))))
    _LIB.cupsRasterClose(ras)
    os.close(fd)
    return fields, px.reshape(px.shape[0], -1, 4), more


def decode_lines(data: bytes, w: int, h: int, nbytes: int) -> tuple[np.ndarray, int]:
    """Strict PWG 5102.4 line decoder: a line-repeat octet (n = n+1 lines), then per run a count
    0..127 (next pixel n+1 times) or 129..255 (257-n literal pixels); 128 and runs past the line refuse."""
    out, line_len = np.empty((h, w * nbytes), np.uint8), w * nbytes
    i = y = 0
    while y < h:
        rep, i = data[i] + 1, i + 1
        if y + rep > h:
            raise SystemExit(f"line {y}: repeat {rep} runs past the page")
        line = bytearray()
        while len(line) < line_len:
            n, i = data[i], i + 1
            if n == 128:
                raise SystemExit(f"line {y}: run count 128 at octet {i - 1}")
            k = nbytes if n < 128 else (257 - n) * nbytes
            line += data[i:i + k] * (n + 1) if n < 128 else data[i:i + k]
            i += k
        if len(line) != line_len:
            raise SystemExit(f"line {y}: runs end at {len(line)} of {line_len} octets")
        out[y:y + rep] = np.frombuffer(bytes(line), np.uint8)
        y += rep
    return out.reshape(h, w, nbytes), i


def compare(px: np.ndarray, page: np.ndarray) -> dict:
    return {"differing_px_C_M_Y_K": [int(((px[:, :, p] == 255) != (page[:, :, p] == 1)).sum()) for p in range(4)],
            "octets_not_0_or_255": int(((px != 0) & (px != 255)).sum()),
            "K_nonzero_px": int((px[:, :, 3] != 0).sum()),
            "ink_px_C_M_Y_K": [int((px[:, :, p] == 255).sum()) for p in range(4)]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("sheet", type=Path, help="sheet directory: manifest.json, page000.ps, page000_gt.npy")
    ap.add_argument("stem", type=Path, help="output stem: <stem>.pwg, <stem>.pjl, <stem>.manifest.json")
    ap.add_argument("--quality", type=int, choices=(3, 4, 5), default=4, help="PWG PrintQuality (4 = normal)")
    ap.add_argument("--optimize", choices=OPTIMIZE, default="auto", help="PWG PrintContentOptimize")
    ap.add_argument("--job-name", default="E041-S4-PWG")
    ap.add_argument("--no-render-check", action="store_true", help="skip the ghostscript render comparison")
    args = ap.parse_args()
    shas, gt, ps = load_sheet(args.sheet)
    top, left = ps_origin(ps, gt.shape[1:])
    page = build_page(gt, top, left)
    h, w = page.shape[:2]
    render = None
    if not args.no_render_check:
        r = render_cmyk(ps)
        render = [int((r[:, :, p] != page[:, :, p]).sum()) for p in range(4)] if r.shape == page.shape else None
        if render is None or any(render):
            raise SystemExit(f"the PostScript's render {r.shape} differs from the GT page, dots C/M/Y/K = {render}")
    hdr = bytearray(pwg_header(w, h, "cmyk_8", args.quality, args.optimize, page_name=PAGE_NAME))
    struct.pack_into(">I", hdr, ALT_PRIMARY_AT, 0x00FFFFFF)
    pwg = SYNC + bytes(hdr) + urf_encode_pixels(page * np.uint8(255), 4)
    ref = libcups_reference(args.quality, args.optimize)
    diff = {o: [struct.unpack_from(">I", ref, o)[0], struct.unpack_from(">I", hdr, o)[0]]
            for o in range(0, HDR_OCTETS, 4) if hdr[o:o + 4] != ref[o:o + 4]}
    if set(diff) - set(EXPECTED_VS_LIBCUPS):
        raise SystemExit(f"header differs from libcups's PWG writer beyond the named words: {diff}")
    with tempfile.TemporaryDirectory() as tmp:
        (path := Path(tmp) / "x.pwg").write_bytes(pwg)
        fields, cups_px, more = libcups_decode(path)
    want = {"MediaClass": "PwgRaster", "MediaType": "stationery", "OutputType": args.optimize, "NumCopies": 1,
            "HWResolution0": HW_DPI, "HWResolution1": HW_DPI, "PageSize0": w * 72 // HW_DPI, "PageSize1": h * 72 // HW_DPI,
            "cupsWidth": w, "cupsHeight": h, "cupsBitsPerColor": 8, "cupsBitsPerPixel": 32, "cupsBytesPerLine": w * 4,
            "cupsColorSpace": 6, "cupsNumColors": 4, "cupsPageSizeName": PAGE_NAME,
            "cupsInteger": [1, 1, 1, 0, 0, 0, 0, 0x00FFFFFF, args.quality] + [0] * 7}
    zero = {n: _plain(getattr(_Hdr2(), n)) for n, _ in _Hdr2._fields_}
    bad = {n: (v, want.get(n, zero[n])) for n, v in fields.items() if v != want.get(n, zero[n])}
    if bad or more:
        raise SystemExit(f"libcups read-back disagrees (got, want): {bad}; further pages {more}")
    own_px, used = decode_lines(pwg[4 + HDR_OCTETS:], w, h, 4)
    checks = {"own_decoder": compare(own_px, page), "libcups_decoder": compare(cups_px, page)}
    checks["own_decoder"]["octets_consumed_of"] = [used, len(pwg) - 4 - HDR_OCTETS]
    gt_ink = [int(gt[p].sum()) for p in range(3)] + [0]
    if any(any(c["differing_px_C_M_Y_K"]) or c["octets_not_0_or_255"] or c["ink_px_C_M_Y_K"] != gt_ink
           for c in checks.values()) or used != len(pwg) - 4 - HDR_OCTETS or UEL in pwg:
        raise SystemExit(f"decoded page differs from the ground truth: {checks}; UEL in the raster: {UEL in pwg}")
    name = args.job_name.encode("ascii")
    head = UEL + b'@PJL JOB NAME="' + name + b'"\r\n@PJL ENTER LANGUAGE=PWG_RASTER\r\n'
    tail = UEL + b'@PJL EOJ NAME="' + name + b'"\r\n' + UEL
    out = {ext: args.stem.with_name(f"{args.stem.name}.{ext}") for ext in ("pwg", "pjl", "manifest.json")}
    out["pwg"].parent.mkdir(parents=True, exist_ok=True)
    out["pwg"].write_bytes(pwg)
    out["pjl"].write_bytes(head + pwg + tail)
    src = [Path(__file__).resolve()] + [E039 / f for f in ("pwg_raster.py", "urf_raster.py", "cmyk_pdf.py")]
    esc = lambda b: b.decode("ascii").replace("\x1b", "<ESC>")  # noqa: E731
    manifest = {
        "experiment": "e041 S4", "engine": "HP Color LaserJet Pro MFP M281fdw", "path": "raw TCP 9100",
        "command": " ".join([sys.executable] + sys.argv), "cwd": os.getcwd(),
        "generator_sha256": {p.name: sha256(p.read_bytes()) for p in src},
        "sheet": {"dir": str(args.sheet), "ps": ps.name, **shas, "field_origin_top_left_dots": [top, left],
                  "field_hw_dots": list(gt.shape[1:]), "gt_ink_px_C_M_Y": gt_ink[:3]},
        "page": {"media": PAGE_NAME, "canvas_w_h_dots": [w, h], "dpi": HW_DPI, "type": "cmyk_8",
                 "octets": "C M Y K chunky, 0 = no toner, 255 = toner; K = 0 everywhere"},
        "outputs": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p.read_bytes())} for p in (out["pwg"], out["pjl"])},
        "pjl": {"prefix": esc(head), "suffix": esc(tail), "uel_inside_raster": False, "enter_language": "UNVERIFIED"},
        "header_readback_libcups_nonzero_fields": {n: v for n, v in fields.items() if v != zero[n]},
        "header_vs_libcups_pwg_writer": {str(o): {"libcups": v[0], "ours": v[1], "why": EXPECTED_VS_LIBCUPS[o]}
                                         for o, v in diff.items()},
        "verification": {"ghostscript_render_vs_page_dots_C_M_Y_K": render, **checks},
        "unverified": list(UNVERIFIED),
    }
    out["manifest.json"].write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps({"outputs": manifest["outputs"], "verification": manifest["verification"]}), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
