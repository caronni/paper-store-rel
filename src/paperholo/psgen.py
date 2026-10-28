"""Raw PostScript emission for the print path (DESIGN.md §2.4, §9).

Hand-written Level-2 PostScript, no library: the archive print path must place
1-bit plane bitmaps on the device dot grid with zero driver interference, so the
job is DeviceCMYK `imagemask` data plus `setpagedevice`, sent raw (`lpr -o raw`).

Conventions:
- All geometry in *device dots* at `hw_dpi`, origin top-left, y down (raster
  order, matching numpy arrays). Conversion to PS's bottom-left/y-up point
  space happens at emission time.
- Bitmaps: uint8/bool arrays, 1 = ink. Emitted MSB-first per row, rows padded
  to byte boundaries (the `imagemask` convention) via ASCIIHexDecode.
- One bitmap = one plane color via `imagemask`. Content whose SET bits overlap
  across planes must go through `put_cmyk_bitmap` (a single 4-channel
  DeviceCMYK image, 1 bit/component): PostScript's paint model is opaque and
  `setoverprint`/OPM semantics vary across composite RIPs, so overlaps are
  composited here, not left to the interpreter.
  CAVEAT (exp 002 canary A): the M281 RIP re-screens `put_cmyk_bitmap` output
  (~165/212 lpi plane-angle screens) while `imagemask` is bit-faithful, so
  put_bitmap grew opt-in `overprint`/`opm` flags to probe sequential per-plane
  imagemask emission of overlapping content (exp 002.1 composite probe).
"""
from __future__ import annotations

from typing import TypeAlias

import numpy as np

A4_PT = (595, 842)  # PageSize for setpagedevice
GridDpi: TypeAlias = int | tuple[int, int]
_DEFAULT_HW_REQUEST = object()

CMYK = {
    "C": (1, 0, 0, 0),
    "M": (0, 1, 0, 0),
    "Y": (0, 0, 1, 0),
    "K": (0, 0, 0, 1),
}


def _hex_lines(packed: bytes, width: int = 128) -> list[str]:
    h = packed.hex()
    return [h[i : i + width] for i in range(0, len(h), width)]


def pack_bits_rows(bits: np.ndarray) -> bytes:
    """Pack a 2-D {0,1} array MSB-first per row, each row padded to a byte."""
    if bits.ndim != 2:
        raise ValueError(f"expected 2-D bit array, got shape {bits.shape}")
    return np.packbits(bits.astype(np.uint8), axis=1).tobytes()


def _dpi_xy(dpi: GridDpi) -> tuple[int, int]:
    """Return ``(dpi_x, dpi_y)`` for a scalar or anisotropic dot grid."""
    if isinstance(dpi, tuple):
        if len(dpi) != 2:
            raise ValueError("dpi tuple must be (dpi_x, dpi_y)")
        dpi_x, dpi_y = dpi
    else:
        dpi_x = dpi_y = dpi
    if dpi_x <= 0 or dpi_y <= 0:
        raise ValueError("dpi must be positive")
    return int(dpi_x), int(dpi_y)


class PSDoc:
    """Accumulates pages of dot-grid-aligned marks; renders to a .ps string."""

    def __init__(
        self,
        hw_dpi: int = 600,
        page_size_pt: tuple[int, int] = A4_PT,
        title: str = "paperholo",
        prolog_lines: list[str] | None = None,
        guard_setpagedevice: bool = False,
        request_hw_dpi: GridDpi | None | object = _DEFAULT_HW_REQUEST,
    ) -> None:
        self.hw_dpi = hw_dpi
        self.page_size_pt = page_size_pt
        self.title = title
        # Raw lines emitted after the DSC header and BEFORE setpagedevice —
        # a print-time prolog can snapshot the DEFAULT pagedevice (exp 002).
        self.prolog_lines: list[str] = list(prolog_lines) if prolog_lines else []
        # When True, wrap setpagedevice in { ... } stopped {} if so a rejecting
        # interpreter cannot kill the job (calibration sheets on unknown engines).
        self.guard_setpagedevice = guard_setpagedevice
        # Omitted preserves the historical byte stream: request [hw_dpi hw_dpi].
        # Explicit None omits /HWResolution entirely, which is the portable
        # device-default path.  A pair requests an anisotropic device grid.
        self.request_hw_dpi: GridDpi | None = (
            hw_dpi if request_hw_dpi is _DEFAULT_HW_REQUEST else request_hw_dpi
        )
        if self.request_hw_dpi is not None:
            _dpi_xy(self.request_hw_dpi)
        self.page_h_dots = round(page_size_pt[1] / 72 * hw_dpi)
        self.page_w_dots = round(page_size_pt[0] / 72 * hw_dpi)
        self._pages: list[list[str]] = []
        self._cur: list[str] | None = None

    # -- page management -------------------------------------------------
    def begin_page(self) -> None:
        if self._cur is not None:
            raise RuntimeError("previous page not ended")
        self._cur = []

    def end_page(self) -> None:
        if self._cur is None:
            raise RuntimeError("no page begun")
        self._pages.append(self._cur)
        self._cur = None

    def _pt(self, dots: float, dpi: int | None = None) -> float:
        return dots * 72.0 / (dpi or self.hw_dpi)

    def _pt_xy(self, x_dots: float, y_dots: float,
               dpi: GridDpi | None = None) -> tuple[float, float]:
        dpi_x, dpi_y = _dpi_xy(self.hw_dpi if dpi is None else dpi)
        return x_dots * 72.0 / dpi_x, y_dots * 72.0 / dpi_y

    # -- content ----------------------------------------------------------
    def put_bitmap(
        self,
        bits: np.ndarray,
        x_dots: int,
        y_dots: int,
        cmyk: tuple[float, float, float, float],
        dpi: GridDpi | None = None,
        overprint: bool = False,
        opm: bool = False,
    ) -> None:
        """Paint `bits` (1 = ink) with its top-left corner at (x_dots, y_dots).

        `dpi` overrides the placement/scale grid (e.g. a 1200 dpi probe on a
        600 dpi job); coordinates are then in *that* grid's dots.  A
        ``(dpi_x, dpi_y)`` pair supports anisotropic device/source grids.

        `overprint` emits `true setoverprint` inside this paint's gsave scope
        (LanguageLevel 2), so a later plane's paint leaves other separations
        unmarked on separation-capable RIPs. Note: for DeviceCMYK paints,
        strict PLRM semantics still knock out zero components unless nonzero
        overprint mode is also set — that is what `opm` does. `opm` emits a
        guarded OPM-1 request: Adobe PS3 integer form `1 setoverprintmode`
        first, falling back to Ghostscript's boolean dialect
        `true setoverprintmode` (measured: gs 10.07 typechecks the integer
        form), each wrapped in where/stopped so LanguageLevel-2 interpreters
        without the operator skip it instead of dying. Defaults (False, False)
        emit byte-identical output to the pre-flag psgen.
        """
        assert self._cur is not None, "begin_page first"
        h, w = bits.shape
        x_pt, _ = self._pt_xy(x_dots, 0, dpi)
        # PS y-up: bitmap bottom edge in point space
        _, y_from_top_pt = self._pt_xy(0, y_dots + h, dpi)
        y_pt = self.page_size_pt[1] - y_from_top_pt
        w_pt, h_pt = self._pt_xy(w, h, dpi)
        ovp: list[str] = []
        if overprint:
            ovp.append("true setoverprint")
        if opm:
            ovp += [
                "/setoverprintmode where { pop",
                "  mark { 1 setoverprintmode } stopped",
                "  { cleartomark mark { true setoverprintmode } stopped cleartomark }",
                "  { cleartomark } ifelse } if",
            ]
        self._cur += [
            "gsave",
            *ovp,
            f"{x_pt:.6f} {y_pt:.6f} translate",
            f"{w_pt:.6f} {h_pt:.6f} scale",
            "%.3f %.3f %.3f %.3f setcmykcolor" % cmyk,
            f"{w} {h} true [{w} 0 0 -{h} 0 {h}]",
            "currentfile /ASCIIHexDecode filter imagemask",
            *_hex_lines(pack_bits_rows(bits)),
            ">",
            "grestore",
        ]

    def put_cmyk_bitmap(
        self,
        planes: dict[str, np.ndarray],
        x_dots: int,
        y_dots: int,
        dpi: GridDpi | None = None,
    ) -> None:
        """Paint per-plane bit arrays whose set bits may overlap, as ONE image.

        `planes` maps "C"/"M"/"Y"/"K" to same-shaped {0,1} arrays (1 = ink).
        Emitted as a DeviceCMYK image, 1 bit per component, 4 bits per pixel —
        exact on any Level-2 interpreter, independent of overprint semantics.
        Unlike imagemask, this also paints 0 as explicit white; keep the rect
        clear of other content.
        """
        assert self._cur is not None, "begin_page first"
        shapes = {a.shape for a in planes.values()}
        if len(shapes) != 1:
            raise ValueError(f"plane shapes differ: {shapes}")
        (h, w), = shapes
        px = np.zeros((h, w, 4), dtype=np.uint8)
        for i, name in enumerate("CMYK"):
            if name in planes:
                px[:, :, i] = planes[name].astype(np.uint8)
        x_pt, _ = self._pt_xy(x_dots, 0, dpi)
        _, y_from_top_pt = self._pt_xy(0, y_dots + h, dpi)
        y_pt = self.page_size_pt[1] - y_from_top_pt
        w_pt, h_pt = self._pt_xy(w, h, dpi)
        self._cur += [
            "gsave /DeviceCMYK setcolorspace",
            f"{x_pt:.6f} {y_pt:.6f} translate",
            f"{w_pt:.6f} {h_pt:.6f} scale",
            "<< /ImageType 1",
            f"   /Width {w} /Height {h} /BitsPerComponent 1",
            "   /Decode [0 1 0 1 0 1 0 1]",
            f"   /ImageMatrix [{w} 0 0 -{h} 0 {h}]",
            "   /DataSource currentfile /ASCIIHexDecode filter",
            ">> image",
            *_hex_lines(pack_bits_rows(px.reshape(h, w * 4))),
            ">",
            "grestore",
        ]

    def put_raw(self, lines: list[str]) -> None:
        """Page-content escape hatch: raw PostScript lines, emitted verbatim.

        For procedural elements (device queries, rectfill strips, rulers) that
        psgen's bitmap/label API cannot express. Caller owns correctness; keep
        such blocks free of inline data and guarded (exp 002 ELEM convention).
        """
        assert self._cur is not None, "begin_page first"
        self._cur += list(lines)

    def put_label(
        self,
        text: str,
        x_dots: int,
        y_dots: int,
        cmyk: tuple[float, float, float, float],
        size_pt: float = 4.0,
    ) -> None:
        """Small annotation text, baseline at (x_dots, y_dots). Scratch sheets only."""
        assert self._cur is not None, "begin_page first"
        esc = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        x_pt = self._pt(x_dots)
        y_pt = self.page_size_pt[1] - self._pt(y_dots)
        self._cur += [
            "gsave",
            f"/Helvetica findfont {size_pt:.1f} scalefont setfont",
            "%.3f %.3f %.3f %.3f setcmykcolor" % cmyk,
            f"{x_pt:.6f} {y_pt:.6f} moveto ({esc}) show",
            "grestore",
        ]

    # -- output -----------------------------------------------------------
    def render(self) -> str:
        if self._cur is not None:
            raise RuntimeError("last page not ended")
        w_pt, h_pt = self.page_size_pt
        head = [
            "%!PS-Adobe-3.0",
            f"%%Title: {self.title}",
            "%%Creator: paperholo.psgen",
            "%%LanguageLevel: 2",
            "%%DocumentData: Clean7Bit",
            f"%%BoundingBox: 0 0 {w_pt} {h_pt}",
            f"%%Pages: {len(self._pages)}",
            "%%EndComments",
        ]
        head += self.prolog_lines
        # Raw path: geometry + duplex are always requested.  Resolution may be
        # omitted for a portable device-default job, or be anisotropic.
        resolution = ""
        if self.request_hw_dpi is not None:
            dpi_x, dpi_y = _dpi_xy(self.request_hw_dpi)
            resolution = f" /HWResolution [{dpi_x} {dpi_y}]"
        spd = f"<< /PageSize [{w_pt} {h_pt}]{resolution} /Duplex false >> setpagedevice"
        head.append("{ " + spd + " } stopped { } if" if self.guard_setpagedevice else spd)
        body: list[str] = []
        for i, page in enumerate(self._pages, 1):
            body += [f"%%Page: {i} {i}", *page, "showpage"]
        return "\n".join(head + body + ["%%Trailer", "%%EOF", ""])
