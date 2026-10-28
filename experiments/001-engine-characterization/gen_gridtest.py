#!/usr/bin/env python
"""Run 001.2 stimulus — feature grid at 600/300/200/150 cpi, K only.

5 pattern families x 4 cell sizes (n = 1,2,3,4 dots at the 600 dpi grid):
  vlines   n-on/n-off vertical lines
  hlines   n-on/n-off horizontal lines
  checker  n x n checkerboard
  dots     isolated n x n BLACK squares on white (spacing 3n)
  holes    isolated n x n WHITE squares in black (spacing 3n)
plus representative scrambled encoding patches (cell=3 main, cell=2 comparison,
50% keystream + pilot lattice), a solid-K density reference, and 5 registration
crosses (3-dot arms — 2-dot features print, 1-dot don't, per run 001.1) with an
orientation square so analysis can register scans unambiguously.

Output: scratch/gridtest.ps (+ manifest + ground-truth .npy).
Print:  ../../scripts/print_plane.sh build/gridtest.ps   (JetDirect 9100)
Scan:   2400 dpi grey, no descreen/sharpen/auto-contrast.
"""
from __future__ import annotations

import hashlib
import sys
import json
from pathlib import Path

import numpy as np

from paperholo.modulation import cells_to_dots, rng
from paperholo.pilots import pilot_sites
from paperholo.psgen import CMYK, PSDoc

HW_DPI = 600
SEED = b"paper-store/exp001"
OUT = Path(__file__).parent / "build"
GT = OUT / "gridtest_gt"
CELLS = (1, 2, 3, 4)  # -> 600 / 300 / 200 / 150 cpi effective


def mm(v: float) -> int:
    return round(v / 25.4 * HW_DPI)


def vlines(n: int, size: int) -> np.ndarray:
    return np.broadcast_to(((np.arange(size) // n) % 2 == 0)[None, :], (size, size)).astype(np.uint8)


def hlines(n: int, size: int) -> np.ndarray:
    return vlines(n, size).T.copy()


def checker(n: int, size: int) -> np.ndarray:
    idx = np.arange(size) // n
    return ((idx[:, None] + idx[None, :]) % 2).astype(np.uint8)


def squares(n: int, size: int, invert: bool) -> np.ndarray:
    """Isolated n x n squares, spacing 3n: black-on-white, or white-in-black."""
    a = np.zeros((size, size), np.uint8)
    for y in range(n, size - n, 3 * n):
        for x in range(n, size - n, 3 * n):
            a[y : y + n, x : x + n] = 1
    return (1 - a) if invert else a


def encoding_patch(cell: int, size: int, label: bytes) -> np.ndarray:
    n = size // cell
    data = rng(SEED, label + b"/data").integers(0, 2, size=(n, n), dtype=np.uint8)
    pv = rng(SEED, label + b"/pilot-values").integers(0, 2, size=(n, n), dtype=np.uint8)
    m = pilot_sites((n, n), SEED)
    data[m] = pv[m]
    return cells_to_dots(data, cell)


def fid_cross(arm: int = 30, w: int = 3) -> np.ndarray:
    s = 2 * arm + w
    a = np.zeros((s, s), np.uint8)
    a[arm : arm + w, :] = 1
    a[:, arm : arm + w] = 1
    return a


def main() -> None:
    GT.mkdir(parents=True, exist_ok=True)
    doc = PSDoc(hw_dpi=HW_DPI, title="paper-store 001.2 feature grid K 600dpi")
    doc.begin_page()
    entries: list[dict] = []

    def put(name: str, bits: np.ndarray, x: int, y: int, kind: str, params: dict) -> None:
        doc.put_bitmap(bits, x, y, CMYK["K"])
        np.save(GT / f"{name}.npy", bits)
        entries.append({"name": name, "kind": kind, "x_dots": x, "y_dots": y,
                        "w_dots": int(bits.shape[1]), "h_dots": int(bits.shape[0]), "params": params})

    # --- registration: 5 crosses (centres in manifest) + orientation square ----
    c = fid_cross()
    cw = c.shape[0]
    fids = {"tl": (mm(10), mm(10)), "tr": (mm(200), mm(10)), "bl": (mm(10), mm(287)),
            "br": (mm(200), mm(287)), "ctr": (mm(105), mm(150))}
    for tag, (cx, cy) in fids.items():
        put(f"fid_{tag}", c, cx - cw // 2, cy - cw // 2, "fiducial",
            {"cx_dots": cx, "cy_dots": cy, "arm_dots": 30, "width_dots": 3})
    put("orient_sq", np.ones((mm(3), mm(3)), np.uint8), mm(16), mm(10), "orientation", {})

    doc.put_label("paper-store 001.2 feature grid  K  600dpi grid  cells 1/2/3/4 = 600/300/200/150 cpi",
                  mm(24), mm(9), CMYK["K"], size_pt=8.0)

    # --- 5 x 4 pattern grid ----------------------------------------------------
    fams = (("vlines", lambda n, s: vlines(n, s)),
            ("hlines", lambda n, s: hlines(n, s)),
            ("checker", lambda n, s: checker(n, s)),
            ("dots", lambda n, s: squares(n, s, invert=False)),
            ("holes", lambda n, s: squares(n, s, invert=True)))
    ps_mm, pitch_mm, x0_mm, y0_mm = 15, 22, 15, 24
    size = mm(ps_mm)
    for r, (fam, gen) in enumerate(fams):
        for col, n in enumerate(CELLS):
            x, y = mm(x0_mm + col * pitch_mm), mm(y0_mm + r * pitch_mm)
            put(f"{fam}_n{n}", gen(n, size), x, y, fam, {"n_dots": n, "cpi": HW_DPI // n})
            doc.put_label(f"{fam} {HW_DPI // n}cpi", x, y + size + mm(2.5), CMYK["K"], size_pt=5.0)

    # --- representative encoding patches --------------------------------------
    # (skipped with --no-encode: bisect variant for the interpreter's suspected
    #  complex-page contone fallback, run 001.3)
    ex, ey = mm(115), mm(24)
    if "--no-encode" not in sys.argv:
        put("encode_c3", encoding_patch(3, mm(40), b"exp001.2/encode3"), ex, ey,
            "encoding_patch", {"cell_dots": 3, "pilot_block": 6, "pilot_period": 64})
        doc.put_label("encode cell=3 (200cpi) 50% + pilots", ex, ey + mm(40) + mm(2.5), CMYK["K"], 5.0)
        put("encode_c2", encoding_patch(2, mm(25), b"exp001.2/encode2"), ex, ey + mm(47),
            "encoding_patch", {"cell_dots": 2, "pilot_block": 6, "pilot_period": 64})
        doc.put_label("encode cell=2 (300cpi) - expected marginal", ex, ey + mm(47) + mm(25) + mm(2.5),
                      CMYK["K"], 5.0)

    # --- solid K density reference ---------------------------------------------
    put("solidK", np.ones((mm(10), mm(10)), np.uint8), ex, ey + mm(82), "solid", {})
    doc.put_label("solid K (white ref = bare paper)", ex, ey + mm(92) + mm(2.5), CMYK["K"], 5.0)

    doc.end_page()
    ps = doc.render()
    stem = "gridtest_noenc" if "--no-encode" in sys.argv else "gridtest"
    (OUT / f"{stem}.ps").write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()
    (OUT / f"{stem}_manifest.json").write_text(json.dumps(
        {"experiment": "001.2", "hw_dpi": HW_DPI, "seed": SEED.decode(), "ps_sha256": sha,
         "fiducials": {k: {"cx_dots": v[0], "cy_dots": v[1]} for k, v in fids.items()},
         "patches": entries}, indent=1))
    print(f"wrote build/{stem}.ps ({len(ps)/1e6:.2f} MB, {len(entries)} patches)")
    print(f"sha256 {sha}")


if __name__ == "__main__":
    main()
