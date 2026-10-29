#!/usr/bin/env python3
"""Recover the dot ground truth of a print job from the PostScript alone.

    env/bin/python util/ps_gt.py PAGE.ps [--out GT.npy] [--expect-sha256 HEX]
    env/bin/python util/ps_gt.py PAGE.ps --list

The holo generator (`src/holo/gen/ps.py`) and the paperholo writer
(`src/paperholo/psgen.py`) paint their bitmaps with two idioms, and both
carry the dots verbatim as ASCIIHex rows:

- a K (or one-colour) `imagemask`: rows packed MSB-first, each padded to a
  byte — the very bytes `np.packbits(dots, axis=1)` gives;
- one 1-bit/component DeviceCMYK `image`: C, M, Y, K interleaved per pixel,
  each row padded to a byte after interleaving.

`--out` writes what `holo.gen.emit` writes beside a page: the packed K
array `(h, ceil(w/8))` for a K page, the plane-major packed C/M/Y array
`(3, h, ceil(w/8))` for a colour page (refused if any K sample is set).
Exactly one bitmap per page is required for `--out`; `--list` shows every
bitmap the parser found, with its placement in device dots.  Sidecar facts
(seed, plan, payload sha) are not in the PostScript; the manifest keeps them.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_NUM = rb"-?[0-9.]+"
_PLACE = (rb"(?P<x>" + _NUM + rb") (?P<y>" + _NUM + rb") translate\n"
          rb"(?P<sw>" + _NUM + rb") (?P<sh>" + _NUM + rb") scale\n")
_MASK = re.compile(
    _PLACE + rb"(?:(?P<cmyk>(?:" + _NUM + rb" ){4})setcmykcolor\n)?"
    rb"(?P<w>\d+) (?P<h>\d+) (?P<pol>true|false) \[\d+ 0 0 -\d+ 0 \d+\]\n"
    rb"currentfile /ASCIIHexDecode filter imagemask\n")
_CMYK = re.compile(
    _PLACE + rb"<< /ImageType 1\n"
    rb"\s*/Width (?P<w>\d+) /Height (?P<h>\d+) /BitsPerComponent 1\n"
    rb"\s*/Decode \[0 1 0 1 0 1 0 1\]\n"
    rb"\s*/ImageMatrix \[\d+ 0 0 -\d+ 0 \d+\]\n"
    rb"\s*/DataSource currentfile /ASCIIHexDecode filter\n"
    rb">> image\n")
_PAGE = re.compile(rb"^%%Page: (\d+) \d+$", re.M)
_PAGESIZE = re.compile(rb"/PageSize \[(" + _NUM + rb") (" + _NUM + rb")\]")
_BBOX = re.compile(rb"^%%BoundingBox: 0 0 (" + _NUM + rb") (" + _NUM + rb")$", re.M)


@dataclass(frozen=True)
class PsBitmap:
    """One bitmap as the job paints it; ``packed`` is the decoded hex."""

    kind: str                  # "mask" (imagemask) | "cmyk" (DeviceCMYK image)
    page: int                  # 1-based %%Page ordinal, 0 before the first
    x_dots: int                # top-left corner, device dots from the page's
    y_dots: int                # top-left corner (raster order, y down)
    w_dots: int
    h_dots: int
    dpi_xy: tuple[int, int]
    cmyk: tuple[float, float, float, float] | None
    polarity: bool | None      # imagemask's paint-the-ones flag
    packed: bytes

    def rows(self) -> np.ndarray:
        """The packed rows, ``(h, row_bytes)`` uint8, exactly as in the job."""
        a = np.frombuffer(self.packed, np.uint8)
        return a.reshape(self.h_dots, -1)

    def bits(self) -> np.ndarray:
        """Unpacked samples: ``(h, w)`` for a mask, ``(h, w, 4)`` C/M/Y/K."""
        per_px = 1 if self.kind == "mask" else 4
        u = np.unpackbits(self.rows(), axis=1)[:, :self.w_dots * per_px]
        return u if self.kind == "mask" else u.reshape(self.h_dots, self.w_dots, 4)


def _hex_payload(text: bytes, start: int) -> tuple[bytes, int]:
    end = text.index(b">", start)          # '>' is never a hex digit: the EOD
    return bytes.fromhex(text[start:end].decode("ascii")), end


def _page_height_pt(text: bytes, pos: int) -> float:
    sizes = [m for m in _PAGESIZE.finditer(text, 0, pos)]
    if sizes:
        return float(sizes[-1].group(2))
    boxes = [m for m in _BBOX.finditer(text, 0, pos)]
    if boxes:
        return float(boxes[-1].group(2))
    raise ValueError("no /PageSize or %%BoundingBox before the bitmap")


def _place(m: re.Match, text: bytes, w: int, h: int) -> tuple[int, int, tuple[int, int]]:
    x_pt, y_pt, sw_pt, sh_pt = (float(m.group(k)) for k in ("x", "y", "sw", "sh"))
    dpi_x, dpi_y = round(72.0 * w / sw_pt), round(72.0 * h / sh_pt)
    top_pt = _page_height_pt(text, m.start()) - y_pt
    return round(x_pt * dpi_x / 72.0), round(top_pt * dpi_y / 72.0) - h, (dpi_x, dpi_y)


def parse_bitmaps(text: bytes) -> list[PsBitmap]:
    """Every imagemask / 1-bit DeviceCMYK image in ``text``, in job order."""
    pages = [(m.start(), int(m.group(1))) for m in _PAGE.finditer(text)]
    found: list[tuple[int, PsBitmap]] = []
    for m in _MASK.finditer(text):
        w, h = int(m.group("w")), int(m.group("h"))
        x, y, dpi = _place(m, text, w, h)
        packed, _ = _hex_payload(text, m.end())
        cmyk = (tuple(float(v) for v in m.group("cmyk").split())
                if m.group("cmyk") else None)       # None: a Separation fill set before
        found.append((m.start(), PsBitmap("mask", 0, x, y, w, h, dpi, cmyk,
                                          m.group("pol") == b"true", packed)))
    for m in _CMYK.finditer(text):
        w, h = int(m.group("w")), int(m.group("h"))
        x, y, dpi = _place(m, text, w, h)
        packed, _ = _hex_payload(text, m.end())
        found.append((m.start(), PsBitmap("cmyk", 0, x, y, w, h, dpi, None, None, packed)))
    found.sort(key=lambda t: t[0])
    out = []
    for pos, bm in found:
        page = max((p for s, p in pages if s < pos), default=0)
        out.append(PsBitmap(bm.kind, page, bm.x_dots, bm.y_dots, bm.w_dots, bm.h_dots,
                            bm.dpi_xy, bm.cmyk, bm.polarity, bm.packed))
    return out


def count_paint_operators(text: bytes) -> int:
    """Occurrences of `imagemask` / `>> image` — what the parser should account for."""
    return text.count(b"filter imagemask\n") + text.count(b">> image\n")


def holo_gt(bm: PsBitmap) -> np.ndarray:
    """The array `holo.gen.emit` saves as ``pageNNN_gt.npy`` for this bitmap."""
    if bm.kind == "mask":
        return bm.rows().copy()
    planes = bm.bits()
    if planes[..., 3].any():
        raise ValueError("K samples set in a DeviceCMYK page: not a holo colour page")
    return np.packbits(np.moveaxis(planes[..., :3], -1, 0), axis=2, bitorder="big")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ps", type=Path)
    ap.add_argument("--out", type=Path, default=None, help="write the holo-layout GT .npy")
    ap.add_argument("--expect-sha256", default=None,
                    help="refuse to write unless the GT array bytes have this sha256 "
                         "(the manifest's gt_sha256)")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args(argv)
    text = a.ps.read_bytes()
    bms = parse_bitmaps(text)
    if a.list or a.out is None:
        for bm in bms:
            print(f"page {bm.page} {bm.kind} {bm.w_dots}x{bm.h_dots} at "
                  f"({bm.x_dots},{bm.y_dots}) dpi {bm.dpi_xy} cmyk {bm.cmyk}")
        print(f"{len(bms)} bitmaps parsed, {count_paint_operators(text)} paint operators")
    if a.out is None:
        return 0
    if len(bms) != 1:
        print(f"refused: {len(bms)} bitmaps, --out needs exactly one", file=sys.stderr)
        return 1
    gt = holo_gt(bms[0])
    digest = hashlib.sha256(gt.tobytes(order="C")).hexdigest()
    if a.expect_sha256 and digest != a.expect_sha256:
        print(f"refused: GT sha256 {digest} != {a.expect_sha256}", file=sys.stderr)
        return 1
    np.save(a.out, gt)
    print(f"{a.out}: {gt.shape} uint8, array sha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
