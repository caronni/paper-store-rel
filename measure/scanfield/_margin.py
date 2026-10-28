"""The payload sheet's own field boundary, as a channel-registration probe.

The discovery-page arms answer the scanner question cleanly, because a K
mark is one physical object in every channel.  They cannot answer it on a
PAYLOAD sheet, because a CMY8 page has no black on it at all: red reads
cyan, green reads magenta, blue reads yellow, and those are three
different pieces of toner.

What a payload sheet does have is the boundary of its own confetti field
— a straight line 200 mm long on all four sides, where every plane's
cell grid starts at the same authored column, with paper on one side and
half-covered cells on the other.  Averaged along the boundary the random
cell pattern integrates away and each channel gets a well-defined step
whose position is that plane's grid origin as the scanner reads it.

**This arm is an UPPER BOUND, not a scanner measurement.** What it
returns is (scanner channel offset) + (printer per-plane registration at
that boundary), and nothing here separates them — that separation is
what the plane-field service exists to do.  It earns its place for two
reasons the discovery pages cannot supply: it is a real payload sheet at
the dpi payload is actually decoded at (2400), and sheet I was captured
three times with the sheet re-placed between scans, so the same physical
boundary is seen at three platen positions.  If the bound is small, the
scanner term inside it is smaller.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import tifffile

from scanner._edge import UM_PER_INCH, analyze_edge, compare_channels

PAD_MM: float = 0.55
PROFILE_ROWS: int = 400
SEARCH_FRACTION: float = 0.12     # look for the boundary in this end-band
END_TRIM: float = 0.06            # skip this fraction at each boundary end


@dataclass(frozen=True)
class MarginCapture:
    key: str
    path: Path
    scan_dpi: float
    record: str


def _profile(image: Any, axis: int, width: int) -> np.ndarray:
    """Mean over a central band, collapsed onto ``axis`` (0=rows, 1=cols)."""
    height, columns = image.shape[0], image.shape[1]
    if axis == 1:                       # profile ALONG columns -> average rows
        lo = max(0, height // 2 - width // 2)
        band = np.asarray(image[lo:lo + width], dtype=np.float64)
        return band.mean(axis=(0, 2))
    lo = max(0, columns // 2 - width // 2)
    band = np.asarray(image[:, lo:lo + width], dtype=np.float64)
    return band.mean(axis=(1, 2))


def _boundary(profile: np.ndarray, side: str) -> int:
    span = int(len(profile) * SEARCH_FRACTION)
    gradient = np.abs(np.diff(profile))
    if side in ("low",):
        return int(np.argmax(gradient[:span]))
    return int(np.argmax(gradient[-span:])) + len(gradient) - span


def field_box(image: Any) -> dict[str, int]:
    """The confetti field's bounding box in scan pixels."""
    across = _profile(image, 1, PROFILE_ROWS)
    down = _profile(image, 0, PROFILE_ROWS)
    return {
        "x0": _boundary(across, "low"), "x1": _boundary(across, "high"),
        "y0": _boundary(down, "low"), "y1": _boundary(down, "high"),
    }


def boundary_rows(capture: MarginCapture, *, segments: int = 10,
                  tone: str | None = None) -> list[dict[str, Any]]:
    """Per-channel offsets along all four field boundaries of one capture."""
    pad = int(round(PAD_MM / 25.4 * capture.scan_dpi))
    halfwidth = 40.0 * capture.scan_dpi / 4800.0
    image = tifffile.memmap(capture.path, mode="r")
    try:
        box = field_box(image)
        rows: list[dict[str, Any]] = []
        sides = (
            ("left", "x", "falling", box["x0"], box["y0"], box["y1"]),
            ("right", "x", "rising", box["x1"], box["y0"], box["y1"]),
            ("top", "y", "falling", box["y0"], box["x0"], box["x1"]),
            ("bottom", "y", "rising", box["y1"], box["x0"], box["x1"]),
        )
        for side, axis, polarity, cut, lo, hi in sides:
            trim = int((hi - lo) * END_TRIM)
            lo, hi = lo + trim, hi - trim
            step = (hi - lo) // segments
            if step < 64:
                continue
            for index in range(segments):
                a, b = lo + index * step, lo + (index + 1) * step
                if axis == "x":
                    patch = np.asarray(image[a:b, cut - pad:cut + pad])
                    orientation, x_px, y_px = "vertical", float(cut), (a + b) / 2
                else:
                    patch = np.asarray(image[cut - pad:cut + pad, a:b])
                    orientation, x_px, y_px = "horizontal", (a + b) / 2, float(cut)
                if patch.ndim != 3 or min(patch.shape[:2]) < 16:
                    continue
                result = analyze_edge(
                    patch, scan_dpi=capture.scan_dpi,
                    orientation=orientation, lsf_halfwidth_px=halfwidth,
                    centroid_window_px=max(6, int(round(halfwidth / 2))),
                    linearize=tone != "none",
                    plateau_guard_um=None)
                if "G" not in result.channels:
                    continue
                differentials = compare_channels(
                    result, scan_dpi=capture.scan_dpi)
                if not differentials:
                    continue
                rows.append({
                    "capture": capture.key, "side": side, "axis": axis,
                    "polarity": polarity, "segment": index,
                    "x_px": x_px, "y_px": y_px,
                    "x_mm": x_px * UM_PER_INCH / capture.scan_dpi / 1000.0,
                    "y_mm": y_px * UM_PER_INCH / capture.scan_dpi / 1000.0,
                    "contrast_G": result.channels["G"].contrast,
                    "angle_deg": result.angle_deg,
                    "shift_dots": {name: value["shift_dots"]
                                   for name, value in differentials.items()},
                })
                del patch
        return rows
    finally:
        del image
