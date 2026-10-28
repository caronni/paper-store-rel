"""Minimal Level-2 PostScript writer owned by the scratch-sheet instrument."""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np


A4_PT = (210.0 / 25.4 * 72.0, 297.0 / 25.4 * 72.0)
PLANE_CMYK = {
    "C": (1.0, 0.0, 0.0, 0.0),
    "M": (0.0, 1.0, 0.0, 0.0),
    "Y": (0.0, 0.0, 1.0, 0.0),
    "K": (0.0, 0.0, 0.0, 1.0),
}


def _dpi_pair(value: tuple[int, int]) -> tuple[int, int]:
    pair = int(value[0]), int(value[1])
    if min(pair) <= 0:
        raise ValueError("DPI must be positive")
    return pair


def _run_length_encode(payload: bytes) -> bytes:
    """PostScript RunLengthDecode stream, including the 128 EOD marker."""

    output = bytearray()
    index = 0
    while index < len(payload):
        run = 1
        while (
            index + run < len(payload)
            and run < 128
            and payload[index + run] == payload[index]
        ):
            run += 1
        if run >= 3:
            output.extend((257 - run, payload[index]))
            index += run
            continue
        start = index
        index += run
        while index < len(payload) and index - start < 128:
            next_run = 1
            while (
                index + next_run < len(payload)
                and next_run < 128
                and payload[index + next_run] == payload[index]
            ):
                next_run += 1
            if next_run >= 3:
                break
            if index - start + next_run > 128:
                break
            index += next_run
        literal = payload[start:index]
        output.append(len(literal) - 1)
        output.extend(literal)
    output.append(128)
    return bytes(output)


def _ascii85_rows(payload: bytes, width: int = 120) -> Iterable[str]:
    text = base64.a85encode(
        _run_length_encode(payload), adobe=False, wrapcol=0
    ).decode("ascii")
    for start in range(0, len(text), width):
        yield text[start:start + width]


def _pack_rows(bits: np.ndarray) -> bytes:
    values = np.asarray(bits, dtype=np.uint8)
    if values.ndim != 2:
        raise ValueError("bitmap must be two-dimensional")
    return np.packbits(values, axis=1).tobytes()


@dataclass
class PageDocument:
    """One-page, top-left-coordinate PostScript job."""

    title: str
    request_dpi: tuple[int, int] | None
    page_size_pt: tuple[float, float] = A4_PT
    prolog_lines: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)

    def _physical(self, dots: float, dpi: int) -> float:
        return dots * 72.0 / dpi

    def _xy(self, x_dots: float, y_dots: float,
            dpi: tuple[int, int]) -> tuple[float, float]:
        dx, dy = _dpi_pair(dpi)
        return self._physical(x_dots, dx), self._physical(y_dots, dy)

    def bitmap(self, bits: np.ndarray, *, x_dots: int, y_dots: int,
               dpi: tuple[int, int], plane: str = "K",
               overprint: bool = False, opm: bool = False) -> None:
        values = np.asarray(bits, dtype=np.uint8)
        height, width = values.shape
        x_pt, _ = self._xy(x_dots, 0, dpi)
        _, bottom_from_top = self._xy(0, y_dots + height, dpi)
        width_pt, height_pt = self._xy(width, height, dpi)
        y_pt = self.page_size_pt[1] - bottom_from_top
        setup: list[str] = []
        if overprint:
            setup.append("true setoverprint")
        if opm:
            setup.extend([
                "/setoverprintmode where { pop",
                " mark { 1 setoverprintmode } stopped",
                " { cleartomark mark { true setoverprintmode } stopped "
                "cleartomark } { cleartomark } ifelse } if",
            ])
        self.lines.extend([
            "gsave",
            *setup,
            f"{x_pt:.6f} {y_pt:.6f} translate",
            f"{width_pt:.6f} {height_pt:.6f} scale",
            "%.3f %.3f %.3f %.3f setcmykcolor" % PLANE_CMYK[plane],
            f"{width} {height} true [{width} 0 0 -{height} 0 {height}]",
            "currentfile /ASCII85Decode filter /RunLengthDecode filter imagemask",
            *_ascii85_rows(_pack_rows(values)),
            "~>",
            "grestore",
        ])

    def cmyk_bitmap(self, planes: dict[str, np.ndarray], *,
                    x_dots: int, y_dots: int,
                    dpi: tuple[int, int]) -> None:
        if not planes:
            raise ValueError("at least one plane is required")
        shapes = {np.asarray(value).shape for value in planes.values()}
        if len(shapes) != 1:
            raise ValueError(f"plane shapes differ: {sorted(shapes)}")
        (height, width), = shapes
        pixels = np.zeros((height, width, 4), np.uint8)
        for index, plane in enumerate("CMYK"):
            if plane in planes:
                pixels[:, :, index] = np.asarray(planes[plane], np.uint8)
        x_pt, _ = self._xy(x_dots, 0, dpi)
        _, bottom_from_top = self._xy(0, y_dots + height, dpi)
        width_pt, height_pt = self._xy(width, height, dpi)
        y_pt = self.page_size_pt[1] - bottom_from_top
        self.lines.extend([
            "gsave /DeviceCMYK setcolorspace",
            f"{x_pt:.6f} {y_pt:.6f} translate",
            f"{width_pt:.6f} {height_pt:.6f} scale",
            "<< /ImageType 1",
            f" /Width {width} /Height {height} /BitsPerComponent 1",
            " /Decode [0 1 0 1 0 1 0 1]",
            f" /ImageMatrix [{width} 0 0 -{height} 0 {height}]",
            " /DataSource currentfile /ASCII85Decode filter "
            "/RunLengthDecode filter",
            ">> image",
            *_ascii85_rows(_pack_rows(pixels.reshape(height, width * 4))),
            "~>",
            "grestore",
        ])

    def label(self, text: str, *, x_mm: float, y_mm: float,
              size_pt: float = 5.0) -> None:
        escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        x_pt = x_mm / 25.4 * 72.0
        y_pt = self.page_size_pt[1] - y_mm / 25.4 * 72.0
        self.lines.extend([
            "gsave",
            f"/Helvetica findfont {size_pt:.2f} scalefont setfont",
            "%.3f %.3f %.3f %.3f setcmykcolor" % PLANE_CMYK["K"],
            f"{x_pt:.6f} {y_pt:.6f} moveto ({escaped}) show",
            "grestore",
        ])

    def rectangle(self, *, x_mm: float, y_mm: float,
                  width_mm: float, height_mm: float) -> None:
        stroke_mm = 0.15
        x = x_mm / 25.4 * 72.0
        y = self.page_size_pt[1] - (y_mm + height_mm) / 25.4 * 72.0
        w = width_mm / 25.4 * 72.0
        h = height_mm / 25.4 * 72.0
        stroke = stroke_mm / 25.4 * 72.0
        self.lines.extend([
            "gsave",
            "%.3f %.3f %.3f %.3f setcmykcolor" % PLANE_CMYK["K"],
            f"{stroke:.5f} setlinewidth",
            f"newpath {x:.6f} {y:.6f} moveto {w:.6f} 0 rlineto "
            f"0 {h:.6f} rlineto {-w:.6f} 0 rlineto closepath stroke",
            "grestore",
        ])

    def render(self) -> str:
        width, height = self.page_size_pt
        resolution = ""
        if self.request_dpi is not None:
            dx, dy = _dpi_pair(self.request_dpi)
            resolution = f" /HWResolution [{dx} {dy}]"
        set_device = (
            f"<< /PageSize [{width:.6f} {height:.6f}]"
            f"{resolution} /Duplex false >> "
            "setpagedevice"
        )
        header = [
            "%!PS-Adobe-3.0",
            f"%%Title: {self.title}",
            "%%Creator: holo.characterize",
            "%%LanguageLevel: 2",
            "%%DocumentData: Clean7Bit",
            f"%%BoundingBox: 0 0 {math.ceil(width)} {math.ceil(height)}",
            f"%%HiResBoundingBox: 0 0 {width:.6f} {height:.6f}",
            "%%Pages: 1",
            "%%EndComments",
            *self.prolog_lines,
            "{ " + set_device + " } stopped { } if",
            "%%Page: 1 1",
        ]
        return "\n".join(
            header + self.lines + ["showpage", "%%Trailer", "%%EOF", ""]
        )
