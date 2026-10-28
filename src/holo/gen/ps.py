"""Level-2 PostScript emission for the holo print path (HOLO-DESIGN F15).

Ported from paperholo (provenance: src/paperholo/psgen.py).  Existing K
pages retain the Layer-0-frozen whole-page ``imagemask`` idiom measured in
experiments 001/002.  Provisional color rows use the separately explicit
``put_cmyk_bitmap`` leaf: one 1-bit/component DeviceCMYK image, also ported
from the measured paperholo composite path.  The two operations do not
rewrite or emulate one another.

Geometry seam contract:
- All caller-facing geometry is in *device dots* on the document's engine
  grid (``engine_dpi``, default HW_DPI = 600), origin TOP-LEFT, y DOWN —
  raster order, matching numpy arrays: ``bits[0, 0]`` is the top-left dot
  of the placed bitmap, and a dot at ``(y_dots, x_dots)`` from the page's
  top-left corner lands at pixel row ``y_dots``, column ``x_dots`` of a
  render at that dpi.
- Conversion to PostScript's bottom-left-origin, y-UP point space happens
  only at emission time inside ``put_bitmap``: ``x_pt = x_dots*72/dpi``,
  ``y_pt = page_h_pt - (y_dots + h)*72/dpi`` (the bitmap's bottom edge),
  with the imagemask matrix ``[w 0 0 -h 0 h]`` restoring raster row order.
- ``/HWResolution`` requests the document's engine grid, and every
  measured engine is FIXED-600: requesting [1200 1200] corrupts raster
  placement on the M281 (experiment 001) and is point-sampled by the
  AltaLink (007.6/009).  ``engine_dpi`` exists for an engine whose grid
  actually is something else (FORMAT-SPACE §9); it is not a resolution
  request a 600-dpi engine will honor.

Bitmaps are bool/uint8 arrays, nonzero = ink. Rows are packed MSB-first,
each row padded to a byte boundary (the `imagemask` convention), emitted
through ASCIIHexDecode.

Job identity: the caller passes a sha256-derived 8-hex-char ``jobid``
(computed over whatever identifies the artifact — never computed here);
it is embedded in the DSC title as ``J=<jobid>``.
"""
from __future__ import annotations

import numpy as np

HW_DPI = 600        # the frozen device dot grid (Layer-0 freeze; F15)
A4_DOTS_XY = (4960, 7016)  # the layout A4 raster (x, y) at 600 dpi

_HEX_LINE_CHARS = 128
_JOBID_ALPHABET = set("0123456789abcdef")


def pack_bits_rows(bits: np.ndarray) -> bytes:
    """Pack a 2-D ink array MSB-first per row, each row padded to a byte."""
    if bits.ndim != 2:
        raise ValueError(f"expected 2-D bit array, got shape {bits.shape}")
    return np.packbits(bits != 0, axis=1).tobytes()


def pack_cmyk_rows(plane_bits: np.ndarray) -> bytes:
    """Pack ``(H,W,3)`` C/M/Y samples in CMYK pixel-component order.

    The PostScript image consumes four one-bit samples per pixel in C, M, Y,
    K order.  K is always inserted as zero: CMY7 and CMY8 do not define a K
    payload component.  Each raster row is padded to a byte boundary only
    after all four components have been interleaved.
    """
    raw = np.asarray(plane_bits)
    if raw.ndim != 3 or raw.shape[-1] != 3:
        raise ValueError(
            f"expected (H,W,3) C/M/Y bits, got shape {raw.shape}")
    if raw.shape[0] == 0 or raw.shape[1] == 0:
        raise ValueError("empty CMYK bitmap")
    if raw.dtype.kind not in "buif" or not np.isfinite(raw).all():
        raise ValueError("CMYK samples must be finite 0/1 values")
    if not np.isin(raw, (0, 1)).all():
        raise ValueError("C/M/Y samples must contain only 0 or 1")
    bits = raw.astype(np.uint8, copy=False)
    cmyk = np.zeros(bits.shape[:2] + (4,), dtype=np.uint8)
    cmyk[..., :3] = bits
    h, w, _ = cmyk.shape
    return pack_bits_rows(cmyk.reshape(h, w * 4))


def _hex_lines(packed: bytes) -> list[str]:
    h = packed.hex()
    return [h[i:i + _HEX_LINE_CHARS] for i in range(0, len(h), _HEX_LINE_CHARS)]


def _dots_to_pt(dots: float, engine_dpi: int = HW_DPI) -> float:
    return dots * 72.0 / engine_dpi


class PSDoc:
    """One raw print job: pages of dot-grid K imagemask content -> .ps text.

    `page_dots_xy` is the page raster in device dots, (w_dots, h_dots) —
    pass the layout's page_dots_xy so PS and layout share ONE geometry
    truth. /PageSize is derived exactly as dots * 72 / engine_dpi
    (fractional points are legal PostScript; A4 at 600 dpi becomes
    595.20 x 841.92 pt, within 0.1 mm of nominal A4 — deriving dots from
    whole points instead would disagree with the layout raster by 1-2
    dots and poison border qualification).

    `engine_dpi` is the dot grid the caller's geometry is expressed on
    (default 600, the measured class); it sets both the point conversion
    and the /HWResolution request.  Dots are a device fact, never a
    format fact (FORMAT-SPACE §5).

    `guard_setpagedevice=True` (the archive default) wraps setpagedevice
    in ``{ ... } stopped { } if`` so a rejecting interpreter prints at
    device defaults instead of killing the job; False emits it bare, so a
    refused request fails loudly (debugging stance).
    """

    def __init__(
        self,
        page_dots_xy: tuple[int, int],
        jobid: str,
        title: str = "holo",
        guard_setpagedevice: bool = True,
        engine_dpi: int = HW_DPI,
    ) -> None:
        w_dots, h_dots = (int(d) for d in page_dots_xy)
        if (w_dots, h_dots) != tuple(page_dots_xy) or w_dots <= 0 or h_dots <= 0:
            raise ValueError("page_dots_xy must be positive whole dots (w, h)")
        if len(jobid) != 8 or not set(jobid) <= _JOBID_ALPHABET:
            raise ValueError("jobid must be 8 lowercase hex chars (sha256-derived)")
        if "\n" in title or "\r" in title:
            raise ValueError("title must be a single line")
        if int(engine_dpi) != engine_dpi or engine_dpi <= 0:
            raise ValueError("engine_dpi must be a positive whole dpi")
        self.jobid = jobid
        self.title = title
        self.guard_setpagedevice = guard_setpagedevice
        self.engine_dpi = int(engine_dpi)
        self.page_w_dots = w_dots
        self.page_h_dots = h_dots
        self.page_size_pt = (self._pt(w_dots), self._pt(h_dots))
        self._pages: list[list[str]] = []
        self._cur: list[str] | None = None

    def _pt(self, dots: float) -> float:
        return _dots_to_pt(dots, self.engine_dpi)

    # -- page management ---------------------------------------------------
    def begin_page(self) -> None:
        if self._cur is not None:
            raise RuntimeError("previous page not ended")
        self._cur = []

    def end_page(self) -> None:
        if self._cur is None:
            raise RuntimeError("no page begun")
        self._pages.append(self._cur)
        self._cur = None

    # -- content -----------------------------------------------------------
    def put_bitmap(self, bits: np.ndarray, x_dots: int, y_dots: int) -> None:
        """Paint `bits` (nonzero = ink) as a K imagemask, top-left corner at
        (x_dots, y_dots) device dots from the page's top-left corner."""
        if self._cur is None:
            raise RuntimeError("begin_page first")
        if bits.ndim != 2:
            raise ValueError(f"expected 2-D bit array, got shape {bits.shape}")
        h, w = bits.shape
        if h == 0 or w == 0:
            raise ValueError("empty bitmap")
        if (x_dots < 0 or y_dots < 0 or x_dots + w > self.page_w_dots
                or y_dots + h > self.page_h_dots):
            raise ValueError(
                f"bitmap {w}x{h} at ({x_dots},{y_dots}) exceeds the "
                f"{self.page_w_dots}x{self.page_h_dots}-dot page")
        x_pt = self._pt(x_dots)
        y_pt = self.page_size_pt[1] - self._pt(y_dots + h)  # PS y-up: bottom edge
        self._cur += [
            "gsave",
            f"{x_pt:.6f} {y_pt:.6f} translate",
            f"{self._pt(w):.6f} {self._pt(h):.6f} scale",
            "0.000 0.000 0.000 1.000 setcmykcolor",
            f"{w} {h} true [{w} 0 0 -{h} 0 {h}]",
            "currentfile /ASCIIHexDecode filter imagemask",
            *_hex_lines(pack_bits_rows(bits)),
            ">",
            "grestore",
        ]

    def put_cmyk_bitmap(
        self,
        plane_bits: np.ndarray,
        x_dots: int,
        y_dots: int,
    ) -> None:
        """Paint one composite 1-bit/component DeviceCMYK image.

        ``plane_bits`` has shape ``(H,W,3)`` in canonical C/M/Y order; the
        emitted K samples are exactly zero.  This is one composite image
        rather than sequential plane overprints; zero components paint
        explicit white inside the addressed rectangle.
        """
        if self._cur is None:
            raise RuntimeError("begin_page first")
        raw = np.asarray(plane_bits)
        # pack_cmyk_rows owns value/order validation.  Validate geometry here
        # before constructing the PostScript operation.
        packed = pack_cmyk_rows(raw)
        h, w = raw.shape[:2]
        if (x_dots < 0 or y_dots < 0 or x_dots + w > self.page_w_dots
                or y_dots + h > self.page_h_dots):
            raise ValueError(
                f"CMYK bitmap {w}x{h} at ({x_dots},{y_dots}) exceeds the "
                f"{self.page_w_dots}x{self.page_h_dots}-dot page")
        x_pt = self._pt(x_dots)
        y_pt = self.page_size_pt[1] - self._pt(y_dots + h)
        self._cur += [
            "gsave /DeviceCMYK setcolorspace",
            f"{x_pt:.6f} {y_pt:.6f} translate",
            f"{self._pt(w):.6f} {self._pt(h):.6f} scale",
            "<< /ImageType 1",
            f"   /Width {w} /Height {h} /BitsPerComponent 1",
            "   /Decode [0 1 0 1 0 1 0 1]",
            f"   /ImageMatrix [{w} 0 0 -{h} 0 {h}]",
            "   /DataSource currentfile /ASCIIHexDecode filter",
            ">> image",
            *_hex_lines(packed),
            ">",
            "grestore",
        ]

    # -- output ------------------------------------------------------------
    def render(self) -> str:
        if self._cur is not None:
            raise RuntimeError("last page not ended")
        if not self._pages:
            raise RuntimeError("no pages")
        w_pt, h_pt = self.page_size_pt
        head = [
            "%!PS-Adobe-3.0",
            f"%%Title: {self.title} J={self.jobid}",
            "%%Creator: holo.gen.ps",
            "%%LanguageLevel: 2",
            "%%DocumentData: Clean7Bit",
            # DSC wants integer bbox; the exact page size lives in
            # setpagedevice (dots * 0.12 pt — at most 2 decimals, exact)
            f"%%BoundingBox: 0 0 {-(-w_pt // 1):.0f} {-(-h_pt // 1):.0f}",
            f"%%Pages: {len(self._pages)}",
            "%%EndComments",
        ]
        spd = (f"<< /PageSize [{w_pt:.2f} {h_pt:.2f}] "
               f"/HWResolution [{self.engine_dpi} {self.engine_dpi}]"
               " /Duplex false >> setpagedevice")
        head.append("{ " + spd + " } stopped { } if"
                    if self.guard_setpagedevice else spd)
        body: list[str] = []
        for i, page in enumerate(self._pages, 1):
            body += [f"%%Page: {i} {i}", *page, "showpage"]
        return "\n".join(head + body + ["%%Trailer", "%%EOF", ""])
