"""A discovery sheet as an addressable object: layout dots -> scan pixels.

``blue_mtf`` pinned every e028 target as a raw pixel box, found once by
hand.  That does not port: the e031 AltaLink pair is the SAME authored
page (identical ``page_plan_semantic_sha256``) but a different impression
on a differently placed sheet, so every box moves by ~100 px and the
whole set would have to be re-pinned per capture.

This module replaces the pins with the two artefacts the repo already
produces for every discovery capture:

* the **page manifest** — every probe's authored box in layout dots
  (``hcal-discovery-*.manifest.json``, written by ``discover emit``);
* the **HCAL report** — ``geometry.affine_layout_to_scan``, the 2x3
  layout-dot -> scan-pixel affine that ``discover analyze`` fitted from
  the four chiral corner marks.

Compose them and any probe on any capture of that page has a predicted
box, good to the affine's own residual (~2-3 layout dots rms = 16-25 px
at 4800 dpi on these sheets), which every measurement here then refines
locally.  Validated against the hand-pinned e028 constants: ``tone/K/1``
predicts x [16557, 18067] against the pinned [16558, 18060].

The manifest is matched to the report by ``page_plan_semantic_sha256``,
so feeding a sheet the wrong page plan is a refusal, not a silent
mislocation.

Read-only on every capture: crops come off a memmap.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

import numpy as np
import tifffile

LAYOUT_DPI = 600.0
UM_PER_INCH = 25400.0
DOTS_PER_MM = LAYOUT_DPI / 25.4


@dataclass(frozen=True)
class SheetSpec:
    """One printed sheet, one capture, one analysis report."""

    key: str                # "e031-color"
    engine: str             # registry printer id
    engine_label: str       # human name, for figures
    capture: Path
    sha256: str
    report: Path
    manifest: Path
    record: str             # the experiment log that owns it
    scan_dpi: float = 4800.0
    channels: tuple[str, ...] = ("R", "G", "B")

    @property
    def um_per_px(self) -> float:
        return UM_PER_INCH / self.scan_dpi


class SheetMismatch(RuntimeError):
    """The manifest, the report and the capture do not describe one sheet."""


class Sheet:
    """Manifest + report + capture, with a layout-to-scan mapping."""

    def __init__(self, spec: SheetSpec) -> None:
        self.spec = spec
        report = json.loads(spec.report.read_text())
        manifest = json.loads(spec.manifest.read_text())["page"]
        plan_report = report.get("page_plan_semantic_sha256")
        plan_manifest = manifest.get("semantic_sha256")
        if plan_report != plan_manifest:
            raise SheetMismatch(
                f"{spec.key}: report page plan {plan_report!r} != manifest "
                f"{plan_manifest!r} — wrong page plan for this capture")
        capture = report["capture"]
        if capture.get("sha256") != spec.sha256:
            raise SheetMismatch(
                f"{spec.key}: report capture sha {capture.get('sha256')!r} "
                f"!= declared {spec.sha256!r}")
        scan_dpi = report["scan_dpi"]
        pair = ([float(value) for value in scan_dpi]
                if isinstance(scan_dpi, (list, tuple))
                else [float(scan_dpi), float(scan_dpi)])
        if pair != [spec.scan_dpi, spec.scan_dpi]:
            raise SheetMismatch(
                f"{spec.key}: report scan_dpi {scan_dpi} != declared "
                f"{spec.scan_dpi} on both axes")
        self.report = report
        self.page = manifest
        self.page_plan_sha256 = plan_manifest
        self.geometry = report["geometry"]
        self.affine = np.asarray(
            self.geometry["affine_layout_to_scan"], dtype=np.float64)
        self._inverse = np.linalg.inv(self.affine[:, :2])
        self.probes = {row["probe_id"]: row for row in manifest["probes"]}
        self.rectangles = {row["element_id"]: row
                           for row in manifest["layout_rectangles"]}
        self.spatial_shape = tuple(int(v) for v in capture["spatial_shape"])
        self._image: Any = None

    # -- context management -------------------------------------------------

    def __enter__(self) -> "Sheet":
        self._image = tifffile.memmap(self.spec.capture, mode="r")
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc: BaseException | None,
                 traceback: TracebackType | None) -> None:
        self._image = None

    @property
    def image(self) -> Any:
        if self._image is None:
            raise RuntimeError("use the Sheet as a context manager")
        return self._image

    # -- geometry -----------------------------------------------------------

    def to_scan(self, lx: float, ly: float) -> tuple[float, float]:
        a = self.affine
        return (a[0, 0] * lx + a[0, 1] * ly + a[0, 2],
                a[1, 0] * lx + a[1, 1] * ly + a[1, 2])

    def to_layout(self, sx: float, sy: float) -> tuple[float, float]:
        offset = np.array([sx - self.affine[0, 2], sy - self.affine[1, 2]])
        out = self._inverse @ offset
        return float(out[0]), float(out[1])

    @property
    def vertical_slope(self) -> float:
        """dx/dy in scan pixels along a line of constant layout x."""
        return float(self.affine[0, 1] / self.affine[1, 1])

    @property
    def horizontal_slope(self) -> float:
        """dy/dx in scan pixels along a line of constant layout y."""
        return float(self.affine[1, 0] / self.affine[0, 0])

    # -- targets ------------------------------------------------------------

    def probe_box(self, probe_id: str) -> dict[str, float]:
        """Authored probe box, in layout dots and predicted scan pixels."""
        probe = self.probes.get(probe_id)
        if probe is None:
            raise KeyError(f"{self.spec.key}: no probe {probe_id!r}")
        return self._box(probe["x_layout_dots"], probe["y_layout_dots"],
                         probe["w_layout_dots"], probe["h_layout_dots"])

    def rectangle_box(self, element_id: str) -> dict[str, float]:
        """Authored infrastructure rectangle, same shape as ``probe_box``."""
        rectangle = self.rectangles.get(element_id)
        if rectangle is None:
            raise KeyError(f"{self.spec.key}: no rectangle {element_id!r}")
        return self._box(rectangle["x_mm"] * DOTS_PER_MM,
                         rectangle["y_mm"] * DOTS_PER_MM,
                         rectangle["width_mm"] * DOTS_PER_MM,
                         rectangle["height_mm"] * DOTS_PER_MM)

    def _box(self, lx: float, ly: float, lw: float, lh: float
             ) -> dict[str, float]:
        x0, y0 = self.to_scan(lx, ly)
        x1, y1 = self.to_scan(lx + lw, ly + lh)
        cx, cy = self.to_scan(lx + lw / 2.0, ly + lh / 2.0)
        return {
            "lx": float(lx), "ly": float(ly),
            "lw": float(lw), "lh": float(lh),
            "x0": float(min(x0, x1)), "x1": float(max(x0, x1)),
            "y0": float(min(y0, y1)), "y1": float(max(y0, y1)),
            "cx": float(cx), "cy": float(cy),
        }

    # -- pixels -------------------------------------------------------------

    def crop_at(self, y0: float, y1: float, x0: float, x1: float,
                channel: int | None = None
                ) -> tuple[np.ndarray, int, int]:
        """A materialized crop plus its origin, clipped to the raster.

        The origin matters wherever a measured position is carried back
        into layout coordinates: the affine's scan frame is the pixel
        INDEX (a corner centre was fitted as ``(x_thumb+0.5)*factor-0.5``,
        which is the index at full resolution), so ``origin + column`` is
        directly a scan coordinate.  Always returns 3-D data, so grey and
        RGB captures take the same code path.
        """
        height, width = self.spatial_shape
        ya, yb = int(max(0, round(y0))), int(min(height, round(y1)))
        xa, xb = int(max(0, round(x0))), int(min(width, round(x1)))
        if yb - ya < 4 or xb - xa < 4:
            raise ValueError(
                f"{self.spec.key}: empty crop y[{y0:.0f},{y1:.0f}] "
                f"x[{x0:.0f},{x1:.0f}]")
        data = self.image[ya:yb, xa:xb]
        if data.ndim == 2:
            data = data[:, :, None]
        if channel is not None:
            data = data[:, :, channel:channel + 1]
        return np.asarray(data), ya, xa

    def crop(self, y0: float, y1: float, x0: float, x1: float,
             channel: int | None = None) -> np.ndarray:
        return self.crop_at(y0, y1, x0, x1, channel)[0]
