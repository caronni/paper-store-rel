"""The HCAL-R1 self-report strips, found blind and read by the
characterize instrument's own decoder.

The discovery layout prints two identical strips (380 x 10 modules of
six layout dots, 56.75 mm from the left edge, at 14 mm and 280 mm), each
framed by two dark border bars nine modules apart.  No page registration
is needed: at ~600 dpi a bar is a dark run some 2,280 px long, so rows
whose dilated dark fraction over a strip-wide window clears
``BAR_FRACTION`` are candidates, and a window around each candidate goes
to ``holo.characterize.report_strips.decode_report_image`` — which finds
the bar pair, recovers the clocks, demodulates, checks CRC and handles
the 180-degree case itself.  A 90-degree capture is searched transposed.
"""
from __future__ import annotations

from typing import Any

import numpy as np
from scipy import ndimage

from holo.characterize.report import REPORT_HEIGHT_MODULES, REPORT_WIDTH_MODULES
from holo.characterize.report_strips import decode_report_image

MODULE_LAYOUT_DOTS: int = 6
BAR_FRACTION: float = 0.75
BAR_DILATE_PX: int = 11


def _candidates(luma: np.ndarray, width_px: int) -> list[tuple[int, int]]:
    white = float(np.percentile(luma, 90))
    black = float(np.percentile(luma, 2))
    dark = luma < 0.5 * (white + black)
    dil = ndimage.maximum_filter1d(dark, size=BAR_DILATE_PX, axis=0)
    cs = np.concatenate([np.zeros((dil.shape[0], 1), np.int32),
                         np.cumsum(dil, axis=1, dtype=np.int32)], axis=1)
    if cs.shape[1] - 1 < width_px:
        return []
    frac = (cs[:, width_px:] - cs[:, :-width_px]) / float(width_px)
    best_x = frac.argmax(axis=1)
    best = frac[np.arange(frac.shape[0]), best_x]
    rows = np.flatnonzero(best >= BAR_FRACTION)
    out: list[tuple[int, int]] = []
    for r in rows:
        if out and r - out[-1][0] < 3 * BAR_DILATE_PX:
            continue
        out.append((int(r), int(best_x[r])))
    return out


def find_strips(luma600: np.ndarray, dpi: float) -> dict[str, Any]:
    """Every CRC-checked strip payload, once, with the windows (scan mm,
    row/column in the orientation searched) that decoded it — the two
    printed strips and any overlapping candidate windows."""
    scale = dpi / 600.0
    width = int(round(REPORT_WIDTH_MODULES * MODULE_LAYOUT_DOTS * scale))
    height = int(round(REPORT_HEIGHT_MODULES * MODULE_LAYOUT_DOTS * scale))
    found: list[dict[str, Any]] = []
    seen: set[bytes] = set()
    attempts = 0
    for transposed in (False, True):
        view = luma600.T if transposed else luma600
        for row, col in _candidates(view, int(0.9 * width)):
            y0 = max(0, row - 2 * height)
            y1 = min(view.shape[0], row + 2 * height)
            x0 = max(0, col - width // 8)
            x1 = min(view.shape[1], col + width + width // 8)
            attempts += 1
            for obs in decode_report_image(np.ascontiguousarray(view[y0:y1, x0:x1])):
                if obs.status != "ok" or obs.report is None or obs.payload is None:
                    continue
                key = bytes(obs.payload)
                where = [round(y0 / dpi * 25.4, 1), round(x0 / dpi * 25.4, 1)]
                if key in seen:
                    for item in found:
                        if item["payload_hex"] == key.hex():
                            item["windows_mm_row_col"].append(where)
                    continue
                seen.add(key)
                found.append({
                    "status": obs.status,
                    "crc_ok": obs.crc_ok,
                    "transposed_search": transposed,
                    "rotated_180": obs.rotated_180,
                    "windows_mm_row_col": [where],
                    "identity": obs.report.identity.to_dict(),
                    "device_readback": obs.report.device_readback.to_dict(),
                    "payload_hex": key.hex(),
                })
    return {"candidate_windows": attempts, "strips": found}
