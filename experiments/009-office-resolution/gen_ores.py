"""ORES-1 — office resolution-unlock probe for the Xerox AltaLink C8245.

Background (measured, do not re-derive): 007.6 established the AltaLink is a
FIXED-600 PostScript device — every `/HWResolution [1200 1200] setpagedevice`
is silently refused and 1200-addressed PS content is point-sampled onto the
600 grid (c3@1200 -> ~24-26% deterministic alias floor). The spec is
1200x2400. The untested residue is the OTHER command languages the raw 9100
port accepts: PJL `@PJL SET RESOLUTION=` and native PCL raster
(`Esc*t<res>R`). This module composes jobs that tickle those paths.

Design: ONE logical K-only bitmap is emitted through several command paths at
several requested grids, so the ONLY variable is whether that path unlocked a
real >600 grid. Every sheet carries, side by side, each science field at BOTH
the requested grid AND a 600-equivalent CONTROL (same physical size, built
from real 600-dots by nearest-neighbour upsample). The 600 controls ALWAYS
survive (they are a genuine 600 grid); a requested-grid field survives IFF the
command path exposed the finer grid. analyze_ores.py reads that off.

Jobs written to build/:
  ores_query.pjl           J0  PJL capability query, prints NOTHING
  ores_pspjl1200.job       J1  @PJL SET RESOLUTION=1200 + PostScript@1200
  ores_pcl1200.pcl         J2  native PCL raster @ *t1200R
  ores_pcl1200_pjlres.pcl  J3  J2 + the @PJL SET RESOLUTION=1200 hint
  ores_pcl2400.pcl         J4  native PCL raster @ *t2400R

K-only / neutral throughout (no CMY -> no MIC lattice, grey-scannable).
Deterministic + sha-gated: byte-identical regeneration from the public seed.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from paperholo.modulation import rng
from paperholo.psgen import A4_PT, PSDoc

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
_SRC = _ROOT / "src"
_EXP002 = _ROOT / "experiments" / "002-calibration-page"
for _p in (_SRC, _EXP002):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import gen_calpage  # noqa: E402  (byte-identical corner_mark builder)

SEED = b"paper-store/exp009-ores"
BUILD = _HERE / "build"
GT_DIR = BUILD / "ores_gt"

UEL = b"\x1b%-12345X"
DPI600 = 600
K_CMYK = (0.0, 0.0, 0.0, 1.0)

# Active-area layout in millimetres (grid-independent); converted to dots per
# requested grid at build time. The margin is deliberately generous: PCL jobs
# start the raster at the page origin (no cursor offset), so the corner marks
# (placed at MARGIN_MM/2 from the bitmap edge = 8 mm) must clear the hardware
# unprintable border of an UNKNOWN novel printer, not just our measured <=4 mm.
MARGIN_MM = 16.0
LABEL_H_MM = 6.0
FIELD_MM = 12.0        # square PN / control field side
GRATING_MM = 7.0       # square grating patch side
GAP_MM = 3.0


def mm_to_dots(v_mm: float, dpi: int) -> int:
    return int(round(v_mm / 25.4 * dpi))


# ---------------------------------------------------------------------------
# 5x7 block-glyph label renderer (no fonts; drawn as filled dot rectangles)
# ---------------------------------------------------------------------------
_GLYPHS = {
    "0": ["111", "101", "101", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "010", "010", "111"],
    "2": ["111", "001", "001", "111", "100", "100", "111"],
    "4": ["101", "101", "101", "111", "001", "001", "001"],
    "P": ["110", "101", "101", "110", "100", "100", "100"],
    "C": ["011", "100", "100", "100", "100", "100", "011"],
    "L": ["100", "100", "100", "100", "100", "100", "111"],
    "S": ["011", "100", "100", "010", "001", "001", "110"],
    "J": ["001", "001", "001", "001", "101", "101", "010"],
    "R": ["110", "101", "101", "110", "110", "101", "101"],
    "E": ["111", "100", "100", "110", "100", "100", "111"],
    " ": ["000", "000", "000", "000", "000", "000", "000"],
    "+": ["000", "010", "010", "111", "010", "010", "000"],
}


def render_label(text: str, scale_dots: int) -> np.ndarray:
    """Filled-rectangle block text, 1 = ink. Each glyph 3x7 cells, 1-cell gap."""
    cols: list[np.ndarray] = []
    for ch in text.upper():
        g = _GLYPHS.get(ch, _GLYPHS[" "])
        block = np.array([[int(c) for c in row] for row in g], dtype=np.uint8)
        cols.append(np.kron(block, np.ones((scale_dots, scale_dots), np.uint8)))
        cols.append(np.zeros((7 * scale_dots, scale_dots), np.uint8))  # gap
    return np.hstack(cols) if cols else np.zeros((7 * scale_dots, 1), np.uint8)


# ---------------------------------------------------------------------------
# field builders — every field is a dot bitmap plus a GT record
# ---------------------------------------------------------------------------
def pn_cells(label: bytes, n_cells: int) -> np.ndarray:
    """Deterministic square PN cell-bit array (0/1), side n_cells."""
    g = rng(SEED, label)
    return g.integers(0, 2, size=(n_cells, n_cells), dtype=np.uint8)


def iso_dots(pitch_600_dots: int, dot_600_dots: int, dpi: int, upsample: int,
             side_mm: float) -> np.ndarray:
    """Isolated dots of dot_600_dots (in 600-grid dots) at pitch_600_dots pitch."""
    pitch = pitch_600_dots * upsample
    d = dot_600_dots * upsample
    n = mm_to_dots(side_mm, dpi)
    a = np.zeros((n, n), np.uint8)
    for y in range(pitch, n - pitch, pitch):
        for x in range(pitch, n - pitch, pitch):
            a[y:y + d, x:x + d] = 1
    return a


# ---------------------------------------------------------------------------
# page assembly
# ---------------------------------------------------------------------------
def build_page(requested_dpi: int) -> tuple[np.ndarray, dict]:
    """Compose the active-area dot bitmap at `requested_dpi` and its manifest.

    Returns (bitmap [H,W] uint8 ink=1, manifest). upsample = requested/600 is
    the pixels-per-600-dot factor used to build the 600-equivalent controls.
    """
    assert requested_dpi % DPI600 == 0, "requested grid must be a multiple of 600"
    up = requested_dpi // DPI600
    dpi = requested_dpi

    margin = mm_to_dots(MARGIN_MM, dpi)
    field_px = mm_to_dots(FIELD_MM, dpi)
    grat_px = mm_to_dots(GRATING_MM, dpi)
    gap = mm_to_dots(GAP_MM, dpi)

    fields: list[dict] = []

    # A PN field's cell spans `n_dots_cell` REQUESTED-grid px. @grid fields use
    # cell = N requested-dots (finest the path can carry); @600 controls use
    # cell = N*up px (= N genuine 600-dots), which always survive.
    def pn_grid(n_dots_cell: int, gt_key: bytes) -> tuple[np.ndarray, np.ndarray]:
        n_cells = max(1, field_px // n_dots_cell)
        gt = pn_cells(b"pn/" + gt_key, n_cells)
        bits = np.kron(gt, np.ones((n_dots_cell, n_dots_cell), np.uint8))
        return bits, gt

    total_w = mm_to_dots(4 * FIELD_MM + 3 * GAP_MM, dpi)
    total_h_est = mm_to_dots(LABEL_H_MM + GAP_MM + FIELD_MM + GAP_MM
                             + GRATING_MM + GAP_MM + GRATING_MM + GAP_MM, dpi)
    W = margin * 2 + max(total_w, mm_to_dots(60, dpi))
    H = margin * 2 + total_h_est
    bmp = np.zeros((H, W), np.uint8)

    y0 = margin

    # label
    lab = render_label(f"{requested_dpi}", scale_dots=max(1, mm_to_dots(1.2, dpi)))
    bmp[y0:y0 + lab.shape[0], margin:margin + lab.shape[1]] = lab
    fields.append({"name": "label", "kind": "label", "grid": requested_dpi,
                   "y_dots": int(y0), "x_dots": int(margin),
                   "h_dots": int(lab.shape[0]), "w_dots": int(lab.shape[1])})
    y0 += lab.shape[0] + gap

    # PN row: c3@grid | c3@600 | c2@grid | c2@600
    x = margin
    pn_defs = [
        ("pn_c3_grid", 3, f"c3@{requested_dpi}", b"c3g" + str(requested_dpi).encode()),
        ("pn_c3_600", 3 * up, "c3@600", b"c3c" + str(requested_dpi).encode()),
        ("pn_c2_grid", 2, f"c2@{requested_dpi}", b"c2g" + str(requested_dpi).encode()),
        ("pn_c2_600", 2 * up, "c2@600", b"c2c" + str(requested_dpi).encode()),
    ]
    for name, cell_dots, grid, gt_key in pn_defs:
        bits, gt = pn_grid(cell_dots, gt_key)
        gt_name = f"{name}_{requested_dpi}"   # namespace by grid: 1200/2400 share field names
        np.save(GT_DIR / f"{gt_name}.npy", gt)
        h, w = bits.shape
        bmp[y0:y0 + h, x:x + w] = bits
        fields.append({"name": name, "kind": "pn", "grid": grid,
                       "y_dots": int(y0), "x_dots": int(x), "h_dots": int(h),
                       "w_dots": int(w), "cell_px": int(cell_dots),
                       "n_cells": int(gt.shape[0]), "gt_file": f"ores_gt/{gt_name}.npy"})
        x += field_px + gap
    y0 += field_px + gap

    # grating rows: [1on1off@grid H][1on1off@600 H][2on2off@grid H][2on2off@600 H]
    #               [ ... V versions ... ]
    for horiz, ry in ((True, y0), (False, y0 + grat_px + gap)):
        x = margin
        # requested-grid grating uses 1 or 2 requested-dots; 600 uses up or 2*up.
        gspecs = [
            (1, f"g1_grid_{'h' if horiz else 'v'}", f"1x1@{requested_dpi}"),
            (up, f"g1_600_{'h' if horiz else 'v'}", "1x1@600"),
            (2, f"g2_grid_{'h' if horiz else 'v'}", f"2x2@{requested_dpi}"),
            (2 * up, f"g2_600_{'h' if horiz else 'v'}", "2x2@600"),
        ]
        for on_px, name, grid in gspecs:
            n = grat_px
            axis = (np.arange(n) // on_px) % 2 == 0
            if horiz:
                field = np.tile(axis.astype(np.uint8).reshape(-1, 1), (1, n))
            else:
                field = np.tile(axis.astype(np.uint8).reshape(1, -1), (n, 1))
            bmp[ry:ry + n, x:x + n] = field
            fields.append({"name": name, "kind": "grating", "grid": grid,
                           "y_dots": int(ry), "x_dots": int(x),
                           "h_dots": int(n), "w_dots": int(n),
                           "on_px": int(on_px), "horizontal": horiz})
            x += grat_px + gap
        # iso dots at the far right of the H row
        if horiz:
            iso = iso_dots(8, 1, dpi, up, GRATING_MM)
            bmp[ry:ry + iso.shape[0], x:x + iso.shape[1]] = iso
            fields.append({"name": "iso_grid", "kind": "iso", "grid": f"1dot@{requested_dpi}",
                           "y_dots": int(ry), "x_dots": int(x),
                           "h_dots": int(iso.shape[0]), "w_dots": int(iso.shape[1]),
                           "pitch_px": int(8)})

    # corner marks bracketing the active area (satellites 1=TL 2=TR 3=BR 4=BL)
    marks = [(1, (1, 1), margin // 2, margin // 2),
             (2, (1, -1), margin // 2, W - margin // 2 - 123),
             (3, (-1, -1), H - margin // 2 - 123, W - margin // 2 - 123),
             (4, (-1, 1), H - margin // 2 - 123, margin // 2)]
    for n_sat, inward, my, mx in marks:
        m = gen_calpage.corner_mark(n_sat, inward)
        my = max(0, min(my, H - 123)); mx = max(0, min(mx, W - 123))
        bmp[my:my + 123, mx:mx + 123] = m
        fields.append({"name": f"corner{n_sat}", "kind": "corner_mark",
                       "grid": requested_dpi, "satellites": n_sat,
                       "cy_dots": int(my + 61), "cx_dots": int(mx + 61),
                       "y_dots": int(my), "x_dots": int(mx),
                       "h_dots": 123, "w_dots": 123})

    manifest = {"requested_dpi": requested_dpi, "upsample": up,
                "page_h_dots": int(H), "page_w_dots": int(W),
                "margin_dots": int(margin), "seed": SEED.decode(),
                "fields": fields}
    return bmp, manifest


# ---------------------------------------------------------------------------
# emitters
# ---------------------------------------------------------------------------
def emit_ps_pjl(bmp: np.ndarray, requested_dpi: int, tag: str) -> bytes:
    """J1: PJL SET RESOLUTION + PostScript imagemask of the bitmap at the
    requested grid, with a pre-showpage backchannel HWResolution snapshot."""
    doc = PSDoc(hw_dpi=DPI600, title=f"ORES {tag}", guard_setpagedevice=True)
    doc.begin_page()
    x0 = mm_to_dots(6.0, requested_dpi)
    y0 = mm_to_dots(6.0, requested_dpi)
    doc.put_bitmap(bmp, x0, y0, K_CMYK, dpi=requested_dpi)
    doc.put_raw([
        "{ (== ORES HWResolution: ) print",
        "  currentpagedevice /HWResolution get dup 0 get 30 string cvs print",
        "  ( x ) print 1 get 30 string cvs print (\\n) print flush } stopped { } if",
    ])
    doc.end_page()
    ps = doc.render().encode("latin-1")
    head = (UEL + b"@PJL JOB NAME=\"ORES-" + tag.encode() + b"\"\r\n"
            + b"@PJL SET RESOLUTION=" + str(requested_dpi).encode() + b"\r\n"
            + b"@PJL SET RET=OFF\r\n"
            + b"@PJL ENTER LANGUAGE=POSTSCRIPT\r\n")
    return head + ps + b"\r\n" + UEL


def emit_pcl(bmp: np.ndarray, requested_dpi: int, tag: str,
             pjl_res: int | None) -> bytes:
    """J2/J3/J4: native PCL raster of the bitmap at *t<requested_dpi>R.

    Unencoded (mode 0) mono raster, rows packed MSB-first, ink(1)->bit 1
    (PCL source bit 1 = foreground/black by default). A full white leading
    margin is baked into the placement via the raster start at the left
    graphics margin; the active band sits at the top of the page."""
    rows, cols = bmp.shape
    nbytes = (cols + 7) // 8
    out = bytearray()
    out += UEL
    out += b"@PJL JOB NAME=\"ORES-" + tag.encode() + b"\"\r\n"
    if pjl_res is not None:
        out += b"@PJL SET RESOLUTION=" + str(pjl_res).encode() + b"\r\n"
    out += b"@PJL SET RET=OFF\r\n"
    out += b"@PJL ENTER LANGUAGE=PCL\r\n"
    out += b"\x1bE"                                   # printer reset
    out += b"\x1b*t%dR" % requested_dpi               # raster resolution
    out += b"\x1b*r0F"                                # presentation: logical page
    out += b"\x1b*b0M"                                # compression mode 0 (unencoded)
    out += b"\x1b*r1A"                                # start raster at left margin
    packed = np.packbits(bmp, axis=1)                 # MSB-first per row
    for i in range(rows):
        row = packed[i].tobytes()
        assert len(row) == nbytes
        out += b"\x1b*b%dW" % nbytes + row
    out += b"\x1b*rC"                                 # end raster
    out += b"\x0c"                                    # form feed
    out += UEL
    return bytes(out)


def emit_query() -> bytes:
    """J0: read-only PJL interrogation. No ENTER LANGUAGE, no raster, no
    showpage => prints nothing; the reply returns on the socket backchannel."""
    return (UEL + b"@PJL\r\n"
            + b"@PJL INFO ID\r\n"
            + b"@PJL INFO CONFIG\r\n"
            + b"@PJL INFO VARIABLES\r\n"
            + b"@PJL DINQUIRE RESOLUTION\r\n"
            + b"@PJL INFO PAGECOUNT\r\n"
            + b"@PJL INFO STATUS\r\n"
            + UEL)


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    GT_DIR.mkdir(parents=True, exist_ok=True)

    jobs: dict[str, bytes] = {}
    manifests: dict[str, dict] = {}

    bmp1200, man1200 = build_page(1200)
    bmp2400, man2400 = build_page(2400)
    np.save(BUILD / "ores_bitmap_1200.npy", bmp1200)
    np.save(BUILD / "ores_bitmap_2400.npy", bmp2400)
    manifests["1200"] = man1200
    manifests["2400"] = man2400

    jobs["ores_query.pjl"] = emit_query()
    jobs["ores_pspjl1200.job"] = emit_ps_pjl(bmp1200, 1200, "PSPJL1200")
    jobs["ores_pcl1200.pcl"] = emit_pcl(bmp1200, 1200, "PCL1200", pjl_res=None)
    jobs["ores_pcl1200_pjlres.pcl"] = emit_pcl(bmp1200, 1200, "PCL1200PJL", pjl_res=1200)
    jobs["ores_pcl2400.pcl"] = emit_pcl(bmp2400, 2400, "PCL2400", pjl_res=2400)

    index = {"seed": SEED.decode(), "jobs": {}, "manifests": manifests}
    for name, data in jobs.items():
        (BUILD / name).write_bytes(data)
        index["jobs"][name] = {"bytes": len(data), "sha256": _sha(data)}
    (BUILD / "ores_manifest.json").write_text(json.dumps(index, indent=1, sort_keys=True))

    for name, meta in index["jobs"].items():
        print(f"{name:28s} {meta['bytes']:>9d} B  {meta['sha256'][:16]}")


if __name__ == "__main__":
    main()
