#!/usr/bin/env python
"""SCRATCH visualization — what the DESIGN.md §5.2 pilot lattice looks like.

The pilot lattice is the hidden addressing skeleton of an archive sheet: one
site per 6x6-cell block (pilots.BLOCK), in-block offsets repeating every 64
cells (pilots.PERIOD) => nominally ~2.8% of cells (1/36; as implemented,
PERIOD//BLOCK = 10 blocks/period-axis => 100 sites per 64x64 tile = 2.44% —
labels below report the computed density). Inside the scrambled 50% data field it
is statistically invisible (DESIGN.md R3); this sheet pulls it out on white so
a human can see the structure.

Uses the REAL site implementation (paperholo.pilots.pilot_sites) verbatim.
Pilot VALUES: the window-property coordinate code is M1 TODO
(pilots.coordinate_code raises), so value panels use the placeholder
convention from experiments/001-engine-characterization/gen_gridtest.py
encoding_patch: values drawn from rng(SEED, label + b"/pilot-values").

Panels (K plane only, cell = 3x3 dots @600 dpi = 200 cpi, A4):
  1  MAIN         ~170x130 mm, true scale, sites all black (~2.4% ink)
  2  ZOOM SITES   one full 64x64-cell period tile, 8x (1 cell -> 24x24 dots)
  3  ZOOM VALUES  same tile, placeholder values: only value=1 sites print
  4  ZOOM DATA    same tile as a real archive patch: 50% data + pilot values
  5  STRIP        40x40 mm of (4) vs 40x40 mm of (1), both true scale

Outputs (all under ./build/, deterministic — run twice, shas match):
  pilot_viz.ps                 the page (paperholo.psgen.PSDoc)
  pilot_viz-page.png           gs -r300 pnggray render of the page
  pilot_viz-zoom-sites.png     1:1 dot-resolution crops of panels 2-4
  pilot_viz-zoom-values.png    (saved straight from the numpy arrays via PIL
  pilot_viz-zoom-data.png       — crisper than gs for screen viewing)

Scratch sheet: labels allowed (archive sheets carry none, DESIGN.md R3).
NOT for printing via scripts/ without explicit say-so (.claude/rules/hardware.md).
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from paperholo.modulation import cells_to_dots, rng          # noqa: E402
from paperholo.pilots import BLOCK, PERIOD, pilot_sites      # noqa: E402
from paperholo.psgen import CMYK, PSDoc                      # noqa: E402

HW_DPI = 600
CELL_DOTS = 3        # true scale: 3x3 dots per cell = 200 cpi (exp 001: 4.7% BER)
ZOOM_CELL_DOTS = 24  # 8x magnification: 64 cells -> 1536 dots ~ 65.0 mm
SEED = b"paper-store/pilot-viz"
OUT = Path(__file__).resolve().parent / "build"
K = CMYK["K"]


def mm(v: float) -> int:
    """Millimetres -> device dots at HW_DPI."""
    return round(v / 25.4 * HW_DPI)


def pilot_value_cells(shape_cells: tuple[int, int], label: bytes) -> np.ndarray:
    """Placeholder pilot values, gen_gridtest.py encoding_patch convention."""
    return rng(SEED, label + b"/pilot-values").integers(0, 2, size=shape_cells, dtype=np.uint8)


def archive_patch_cells(n_cells: int, label: bytes) -> np.ndarray:
    """Real-archive-patch construction (gen_gridtest encoding_patch, cell grid):
    scrambled 50% data everywhere, placeholder pilot values at pilot sites."""
    shape = (n_cells, n_cells)
    data = rng(SEED, label + b"/data").integers(0, 2, size=shape, dtype=np.uint8)
    pv = pilot_value_cells(shape, label)
    m = pilot_sites(shape, SEED)
    data[m] = pv[m]
    return data


def save_png_1to1(bits: np.ndarray, path: Path) -> None:
    """1 = ink -> black pixel; saved at exact dot resolution."""
    Image.fromarray(((1 - bits) * 255).astype(np.uint8), mode="L").save(path)


def main() -> None:
    doc = PSDoc(hw_dpi=HW_DPI, title="paper-store pilot lattice viz")
    doc.begin_page()
    doc.put_label(
        f"paper-store pilot lattice viz  seed={SEED.decode()}  experiments/pilot-lattice-viz/pilot_viz.py"
        f"  cell={CELL_DOTS}x{CELL_DOTS} dots @600dpi (200cpi)"
        f"  BLOCK={BLOCK} PERIOD={PERIOD}  K plane  SCRATCH - not an archive sheet",
        mm(10), mm(6.5), K, size_pt=6.0)

    # -- 1  MAIN: pilot sites only, true scale, ~170x130 mm -------------------
    main_wh_cells = (mm(130) // CELL_DOTS, mm(170) // CELL_DOTS)  # (1023, 1338)
    mask_main = pilot_sites(main_wh_cells, SEED)
    doc.put_bitmap(cells_to_dots(mask_main.astype(np.uint8), CELL_DOTS), mm(10), mm(9), K)
    doc.put_label(
        f"1  pilot sites only, true scale, cell=3 @600dpi, {100 * mask_main.mean():.2f}% ink"
        " - arm's length: faint gray; up close: dust. Normally buried in the data field.",
        mm(10), mm(142.5), K, size_pt=5.0)

    # -- one 64x64-cell period tile, shared by panels 2-4 ---------------------
    tile_mask = pilot_sites((PERIOD, PERIOD), SEED)  # == top-left period of mask_main
    assert np.array_equal(tile_mask, mask_main[:PERIOD, :PERIOD])
    pv_tile = pilot_value_cells((PERIOD, PERIOD), b"tile64")

    # -- 2  ZOOM SITES ---------------------------------------------------------
    bits_zoom_sites = cells_to_dots(tile_mask.astype(np.uint8), ZOOM_CELL_DOTS)
    doc.put_bitmap(bits_zoom_sites, mm(10), mm(146), K)
    doc.put_label(
        f"2  one {PERIOD}x{PERIOD}-cell period tile, sites only, 8x zoom (1 cell -> 24x24 dots)",
        mm(10), mm(214.5), K, size_pt=5.0)
    doc.put_label(
        f"   one pilot per {BLOCK}x{BLOCK}-cell block, offsets seed-fixed, period {PERIOD} (5.2a)",
        mm(10), mm(217.8), K, size_pt=4.5)

    # -- 3  ZOOM VALUES ----------------------------------------------------------
    bits_zoom_values = cells_to_dots((tile_mask & (pv_tile == 1)).astype(np.uint8), ZOOM_CELL_DOTS)
    doc.put_bitmap(bits_zoom_values, mm(85), mm(146), K)
    doc.put_label(
        "3  same tile, sites carrying PLACEHOLDER random values - only value=1 sites print (~half the skeleton)",
        mm(85), mm(214.5), K, size_pt=5.0)
    doc.put_label(
        "   real values = 2-D window-property position code (M-array + BCH, M1 TODO):"
        " any clean window -> absolute (page,x,y)",
        mm(85), mm(217.8), K, size_pt=4.5)

    # -- 4  ZOOM DATA+PILOTS -----------------------------------------------------
    tile_patch_cells = archive_patch_cells(PERIOD, b"tile64")
    bits_zoom_data = cells_to_dots(tile_patch_cells, ZOOM_CELL_DOTS)
    doc.put_bitmap(bits_zoom_data, mm(10), mm(221.5), K)
    doc.put_label(
        "4  same tile as a REAL archive patch: scrambled 50% data everywhere,"
        " pilot values at pilot sites - uniform noise:",
        mm(10), mm(290), K, size_pt=5.0)
    doc.put_label(
        "   the pilots are statistically invisible (R3); compare with 3 to find them",
        mm(10), mm(293.3), K, size_pt=4.5)

    # -- 5  TRUE-SCALE COMPARISON STRIP ------------------------------------------
    strip_n_cells = mm(40) // CELL_DOTS  # 315 cells ~ 40 mm
    strip_patch = archive_patch_cells(strip_n_cells, b"strip40")
    doc.put_bitmap(cells_to_dots(strip_patch, CELL_DOTS), mm(85), mm(221.5), K)
    strip_mask = pilot_sites((strip_n_cells, strip_n_cells), SEED)
    doc.put_bitmap(cells_to_dots(strip_mask.astype(np.uint8), CELL_DOTS), mm(129), mm(221.5), K)
    doc.put_label(
        f"5  true scale, 40x40 mm each:  data+pilots, {100 * strip_patch.mean():.1f}% ink",
        mm(85), mm(265), K, size_pt=5.0)
    doc.put_label(
        f"   vs sites-only, {100 * strip_mask.mean():.2f}% - the density gap at print scale",
        mm(85), mm(268.3), K, size_pt=4.5)

    doc.end_page()
    ps = doc.render()
    ps_path = OUT / "pilot_viz.ps"
    ps_path.write_text(ps)
    print(f"wrote {ps_path} ({len(ps) / 1e6:.2f} MB)")
    print(f"sha256(pilot_viz.ps) {hashlib.sha256(ps.encode()).hexdigest()}")

    # 1:1 dot-resolution crops of the zoom panels (crisper than gs on screen)
    for name, bits in (("sites", bits_zoom_sites), ("values", bits_zoom_values), ("data", bits_zoom_data)):
        p = OUT / f"pilot_viz-zoom-{name}.png"
        save_png_1to1(bits, p)
        print(f"wrote {p} {bits.shape[1]}x{bits.shape[0]} px")

    # gs page render. Measured (tests/test_calpage.py): gs 10.07 keeps CLI -rN;
    # the job's /HWResolution [600 600] does not override it.
    page_png = OUT / "pilot_viz-page.png"
    r = subprocess.run(
        ["gs", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-r300", "-sDEVICE=pnggray",
         "-o", str(page_png), str(ps_path)],
        capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or "rror" in r.stderr:
        sys.exit(f"gs render FAILED (rc={r.returncode}):\n{r.stdout}\n{r.stderr}")
    print(f"wrote {page_png} (gs rc=0, no errors)")


if __name__ == "__main__":
    main()
