#!/usr/bin/env python
"""Minimum-feature / dot-gain / polarity probe (K plane, 600 dpi native).

Both polarities x several orientations x a width ladder, so a max-dpi scan reveals:
  * does a lone 1-dot BLACK line mark, and how much does toner gain fatten it?
  * does a lone 1-dot WHITE line survive, or does gain close the gap (invisible)?
  * how does that differ by orientation (fast-scan vs process vs diagonal)?
  * at what line width do both polarities stabilise? -> min reliable cell feature.

Emits build/linetest.ps (raw, 600 dpi) + build/linetest_manifest.json +
build/linetest_gt/*.npy ground truth. Print raw:
    ../../scripts/print_plane.sh build/linetest.ps   (JetDirect 9100)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from paperholo.psgen import CMYK, PSDoc

HW_DPI = 600
OUT = Path(__file__).parent / "build"
GT = OUT / "linetest_gt"


def mm(v: float) -> int:
    return round(v / 25.4 * HW_DPI)


def line_field(h: int, w: int, theta_deg: float, width_dots: int, pitch_dots: int) -> np.ndarray:
    """Parallel lines running at theta degrees, `width` dots thick, every `pitch` dots.

    1 = ink. theta=0 -> horizontal lines, 90 -> vertical, 45/135 -> diagonal.
    Axis-aligned and 45 deg are dot-exact; other angles are the honest staircase
    the engine would receive.
    """
    th = np.deg2rad(theta_deg)
    yy, xx = np.mgrid[0:h, 0:w]
    t = -xx * np.sin(th) + yy * np.cos(th)          # coordinate across the lines
    return ((np.rint(t).astype(int) % pitch_dots) < width_dots).astype(np.uint8)


def isolated(h: int, w: int, spacing: int, ink_bg: bool) -> np.ndarray:
    """Sparse single dots: lone ink dots on white (ink_bg=False) or lone white
    holes in an ink field (ink_bg=True). Tests the minimum mark / minimum void."""
    a = np.ones((h, w), np.uint8) if ink_bg else np.zeros((h, w), np.uint8)
    val = 0 if ink_bg else 1
    a[spacing // 2 :: spacing, spacing // 2 :: spacing] = val
    return a


def main() -> None:
    GT.mkdir(parents=True, exist_ok=True)
    doc = PSDoc(hw_dpi=HW_DPI, title="paper-store min-feature / dot-gain probe (K, 600dpi)")
    doc.begin_page()
    entries: list[dict] = []
    x_left, x_right = mm(8), mm(110)          # black-on-white | white-on-black columns
    P = mm(14)                                 # patch pitch AS PRINTED in run 001.1 (labels overlap next patch by 1 mm — known cosmetic bug, kept for byte-identity with the printed sheet sha 9f6e...; new sheets use gen_gridtest)
    patch = mm(12)                             # 12 mm square patches

    def place(name, x, y, bits, note):
        doc.put_bitmap(bits, x, y, CMYK["K"])
        np.save(GT / f"{name}.npy", bits)
        h, w = bits.shape
        entries.append({"name": name, "x_dots": x, "y_dots": y, "w_dots": int(w),
                        "h_dots": int(h), "note": note})
        doc.put_label(note, x, y + patch + mm(3), CMYK["K"], size_pt=5.0)

    doc.put_label("paper-store min-feature / dot-gain probe  K plane  600 dpi native  "
                  "(scan at max dpi)", x_left, mm(6), CMYK["K"], size_pt=9.0)
    doc.put_label("BLACK on white -- does a 1-dot line mark / fatten?", x_left, mm(12), CMYK["K"], 6.0)
    doc.put_label("WHITE on black -- does dot gain close the 1-dot gap?", x_right, mm(12), CMYK["K"], 6.0)

    y = mm(16)
    # isolated single dot / single hole
    place("bow_dot1", x_left, y, isolated(patch, patch, 12, ink_bg=False), "lone 1-dot INK on white")
    place("wob_hole1", x_right, y, isolated(patch, patch, 12, ink_bg=True), "lone 1-dot HOLE in black")
    y += P

    # 1-dot lines, isolated (pitch 6), four clean orientations
    for th in (0, 45, 90, 135):
        place(f"bow_1dot_{th}", x_left, y, line_field(patch, patch, th, 1, 6), f"1-dot ink lines  {th} deg")
        place(f"wob_1dot_{th}", x_right, y, 1 - line_field(patch, patch, th, 1, 6), f"1-dot white lines  {th} deg")
        y += P

    # Nyquist 1-on/1-off (pitch 2), horizontal + vertical -- worst-case smear/merge
    for th, tag in ((0, "H"), (90, "V")):
        place(f"bow_nyq_{tag}", x_left, y, line_field(patch, patch, th, 1, 2), f"1on/1off ink  {tag}")
        place(f"wob_nyq_{tag}", x_right, y, 1 - line_field(patch, patch, th, 1, 2), f"1on/1off white  {tag}")
        y += P

    # width ladder 1..4 dots (pitch = width*3), vertical lines, both polarities
    for wdt in (1, 2, 3, 4):
        place(f"bow_ladV_{wdt}", x_left, y, line_field(patch, patch, 90, wdt, wdt * 3), f"{wdt}-dot ink lines V")
        place(f"wob_ladV_{wdt}", x_right, y, 1 - line_field(patch, patch, 90, wdt, wdt * 3), f"{wdt}-dot white lines V")
        y += P

    doc.end_page()
    ps = doc.render()
    (OUT / "linetest.ps").write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()
    (OUT / "linetest_manifest.json").write_text(json.dumps(
        {"hw_dpi": HW_DPI, "ps_sha256": sha, "patches": entries}, indent=1))
    print(f"wrote build/linetest.ps ({len(ps)/1e3:.0f} kB, {len(entries)} patches)\nsha256 {sha}")


if __name__ == "__main__":
    main()
