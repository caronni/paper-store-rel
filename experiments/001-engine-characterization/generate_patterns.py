#!/usr/bin/env python
"""Experiment 001 — engine characterization sheets for the HP CLJ Pro MFP M281fdw.

Generates one raw PostScript job (build/001_patterns.ps) implementing the protocol in
../001-engine-characterization.md, plus build/manifest.json (every patch: page, plane,
device-dot rect, parameters, seed labels) and build/ground_truth/*.npy so the stage-2
scan analysis knows exactly what was printed where.

Print ONLY via:  lpr -P <queue> -o raw build/001_patterns.ps   (DESIGN.md §2.4 —
the job carries its own setpagedevice; CUPS must not re-rasterize or color-manage.)

Pages (scratch sheets — fiducials/test patterns allowed here, DESIGN.md R3 exempt):
  1-4  per-plane (K, C, M, Y): line pairs, isolated dots, checkerboards, density
       ladder, representative encoding patches (cells 1-4), mottle fields, banding
       strips. Single toner per page — one variable at a time.
  5    all planes: warp cross grid, inter-plane registration quads + verniers,
       overlay solids (crosstalk), 3-plane encoding patch, 1200 dpi addressability
       probe (engine is believed 600 dpi native; the probe falsifies or confirms).
  6    MIC hunt: intentionally blank color-mode page (tiny K corner label only).

Determinism: every random field derives from SEED via paperholo.modulation.rng with
a manifest-recorded label. The engine is 600x600 dpi addressable (ImageREt 3600 is
toner-level pulse modulation, not addressability); all geometry is in 600 dpi dots.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from paperholo.modulation import cells_to_dots, rng
from paperholo.pilots import pilot_sites
from paperholo.psgen import CMYK, PSDoc

SEED = b"paper-store/exp001"
HW_DPI = 600
PROBE_DPI = 1200
PLANES = ("K", "C", "M", "Y")  # page order 1..4
MARGIN_MM = 6.0  # engine minimum ~4.2 mm; keep clear of it

BUILD_DIR = Path(__file__).parent / "build"
GT_DIR = BUILD_DIR / "ground_truth"


def mm(v: float) -> int:
    """Millimetres -> device dots at HW_DPI."""
    return round(v / 25.4 * HW_DPI)


# ---------------------------------------------------------------------------
# pattern builders (pure; 1 = ink)
# ---------------------------------------------------------------------------

def line_pairs(pitch_dots: int, size_dots: int, horizontal: bool) -> np.ndarray:
    """pitch-on / pitch-off stripes; finest engine probe at pitch 1."""
    ramp = (np.arange(size_dots) // pitch_dots) % 2 == 0
    return np.broadcast_to(ramp[:, None] if horizontal else ramp[None, :], (size_dots, size_dots)).astype(np.uint8)


def isolated_dots(n_dots: int, size_dots: int, spacing_dots: int = 32) -> np.ndarray:
    """Sparse grid of n x n dot squares — minimum stable mark + PSF probes."""
    bits = np.zeros((size_dots, size_dots), dtype=np.uint8)
    for y in range(spacing_dots // 2, size_dots - n_dots, spacing_dots):
        for x in range(spacing_dots // 2, size_dots - n_dots, spacing_dots):
            bits[y : y + n_dots, x : x + n_dots] = 1
    return bits


def checkerboard(n_dots: int, size_dots: int) -> np.ndarray:
    """n x n checker — worst-case 2-D transition density at cell size n."""
    idx = np.arange(size_dots) // n_dots
    return ((idx[:, None] + idx[None, :]) % 2).astype(np.uint8)


def density_field(p: float, size_dots: int, cell_dots: int, label: bytes) -> np.ndarray:
    """Random cell field with ink probability p (dot gain / mottle vs density)."""
    n = size_dots // cell_dots
    cells = (rng(SEED, label).random((n, n)) < p).astype(np.uint8)
    return cells_to_dots(cells, cell_dots)


def encoding_patch(cell_dots: int, size_dots: int, label: bytes) -> np.ndarray:
    """Representative M-A modulation: scrambled 50% cells + pilot lattice (§4, §5.2).

    Statistics identical to a real archive tile (scrambler pins density at 50%,
    pilot values from a separate stream at the seed-fixed sites).
    """
    n = size_dots // cell_dots
    data = rng(SEED, label + b"/data").integers(0, 2, size=(n, n), dtype=np.uint8)
    pilots = rng(SEED, label + b"/pilot-values").integers(0, 2, size=(n, n), dtype=np.uint8)
    mask = pilot_sites((n, n), SEED)
    data[mask] = pilots[mask]
    return cells_to_dots(data, cell_dots)


def cross(arm_dots: int = 20, width_dots: int = 2) -> np.ndarray:
    """Registration/warp cross; centroid-fittable in a 4800 dpi scan."""
    s = 2 * arm_dots + width_dots
    bits = np.zeros((s, s), dtype=np.uint8)
    bits[arm_dots : arm_dots + width_dots, :] = 1
    bits[:, arm_dots : arm_dots + width_dots] = 1
    return bits


def vernier_comb(period_dots: int, teeth: int, tooth_len_dots: int, horizontal: bool) -> np.ndarray:
    """Comb of teeth (period/2 on); paired combs of period p and p+1 read sub-dot offset."""
    w = teeth * period_dots
    line = (np.arange(w) % period_dots) < period_dots // 2
    bits = np.broadcast_to(line[None, :], (tooth_len_dots, w)).astype(np.uint8)
    return bits if horizontal else bits.T


# ---------------------------------------------------------------------------
# job assembly
# ---------------------------------------------------------------------------

class Job:
    """PSDoc + manifest + ground-truth bookkeeping."""

    def __init__(self) -> None:
        self.doc = PSDoc(hw_dpi=HW_DPI, title="paper-store exp001 engine characterization")
        self.entries: list[dict] = []
        self.bitmaps: dict[str, tuple[np.ndarray, tuple[str, ...], tuple[int, int], int]] = {}
        self.page = 0

    def begin_page(self) -> None:
        self.page += 1
        self.doc.begin_page()

    def _record(
        self,
        name: str,
        bits: np.ndarray,
        x_dots: int,
        y_dots: int,
        planes: tuple[str, ...],
        kind: str,
        params: dict | None,
        dpi: int,
        save_gt: bool,
    ) -> None:
        key = f"p{self.page}/{name}"
        self.bitmaps[key] = (bits, planes, (x_dots, y_dots), dpi)
        gt_path = None
        if save_gt:
            GT_DIR.mkdir(parents=True, exist_ok=True)
            gt_path = f"ground_truth/{key.replace('/', '_')}.npy"
            np.save(BUILD_DIR / gt_path, bits)
        h, w = bits.shape
        self.entries.append(
            {
                "page": self.page,
                "name": name,
                "kind": kind,
                "planes": list(planes),
                "x_dots": int(x_dots),
                "y_dots": int(y_dots),
                "w_dots": int(w),
                "h_dots": int(h),
                "dpi": dpi,
                "params": params or {},
                "ground_truth": gt_path,
            }
        )

    def put(
        self,
        name: str,
        bits: np.ndarray,
        x_dots: int,
        y_dots: int,
        plane: str,
        kind: str,
        params: dict | None = None,
        dpi: int = HW_DPI,
        save_gt: bool = False,
    ) -> None:
        """Emit `bits` (1 = ink) in a single plane via imagemask + record."""
        self.doc.put_bitmap(bits, x_dots, y_dots, CMYK[plane], dpi=None if dpi == HW_DPI else dpi)
        self._record(name, bits, x_dots, y_dots, (plane,), kind, params, dpi, save_gt)

    def put_multi(
        self,
        name: str,
        plane_bits: dict[str, np.ndarray],
        x_dots: int,
        y_dots: int,
        kind: str,
        params: dict | None = None,
        save_gt: bool = False,
    ) -> None:
        """Emit per-plane bitmaps whose SET bits overlap, as one CMYK image.

        Opaque paint model: overlaps must be composited, not overprinted
        (psgen.put_cmyk_bitmap docstring). One manifest entry per plane.
        """
        self.doc.put_cmyk_bitmap(plane_bits, x_dots, y_dots)
        for p, bits in plane_bits.items():
            self._record(f"{name}_{p}", bits, x_dots, y_dots, (p,), kind, params, HW_DPI, save_gt)

    def label(self, text: str, x_dots: int, y_dots: int, plane: str, size_pt: float = 4.0) -> None:
        self.doc.put_label(text, x_dots, y_dots, CMYK[plane], size_pt=size_pt)


def build_plane_page(job: Job, plane: str) -> None:
    """Pages 1-4: everything single-plane the protocol asks for (steps 1-3, 6)."""
    job.begin_page()
    x0, y0 = mm(MARGIN_MM), mm(MARGIN_MM)
    lp = f"exp001/p{job.page}/{plane}".encode()

    job.label(f"paper-store exp001 p{job.page} plane={plane} 600dpi seed={SEED.decode()}", x0, y0 + mm(3), plane, 8)
    job.label(plane, x0 + mm(180), y0 + mm(6), plane, 24)

    # A: line pairs, pitch 1..8, horizontal then vertical (protocol step 1)
    y = y0 + mm(10)
    for i, pitch in enumerate(range(1, 9)):
        x = x0 + mm(12 * i)
        job.put(f"lines_h_pitch{pitch}", line_pairs(pitch, mm(10), True), x, y, plane, "line_pairs",
                {"pitch_dots": pitch, "horizontal": True})
        job.label(f"H{pitch}", x, y + mm(13), plane)
        x = x0 + mm(96 + 12 * i)
        job.put(f"lines_v_pitch{pitch}", line_pairs(pitch, mm(10), False), x, y, plane, "line_pairs",
                {"pitch_dots": pitch, "horizontal": False})
        job.label(f"V{pitch}", x, y + mm(13), plane)

    # B: isolated n x n dots (dot fidelity + PSF, steps 2-3)
    y = y0 + mm(26)
    for i, n in enumerate(range(1, 9)):
        x = x0 + mm(12 * i)
        job.put(f"dots_n{n}", isolated_dots(n, mm(10)), x, y, plane, "isolated_dots", {"n_dots": n})
        job.label(f"dot{n}", x, y + mm(13), plane)

    # C: checkerboards n=1..8 (dot gain vs feature size, step 3)
    y = y0 + mm(42)
    for i, n in enumerate(range(1, 9)):
        x = x0 + mm(12 * i)
        job.put(f"checker_n{n}", checkerboard(n, mm(10)), x, y, plane, "checkerboard", {"n_dots": n})
        job.label(f"chk{n}", x, y + mm(13), plane)

    # D: density ladder 10..100% at cell=3 (dot gain vs coverage)
    y = y0 + mm(58)
    for i, pct in enumerate(range(10, 101, 10)):
        x = x0 + mm(14 * i)
        name = f"density_{pct}"
        job.put(name, density_field(pct / 100, mm(12), 3, lp + f"/density{pct}".encode()), x, y,
                plane, "density_field", {"p": pct / 100, "cell_dots": 3}, save_gt=True)
        job.label(f"{pct}%", x, y + mm(15), plane)

    # E: representative encoding patches, cell 1/2/3/4 (protocol step 2)
    y = y0 + mm(76)
    for i, cell in enumerate((1, 2, 3, 4)):
        x = x0 + mm(46 * i)
        name = f"encode_cell{cell}"
        job.put(name, encoding_patch(cell, mm(40), lp + f"/encode{cell}".encode()), x, y,
                plane, "encoding_patch",
                {"cell_dots": cell, "pilot_block": 6, "pilot_period": 64}, save_gt=True)
        job.label(f"cell {cell}x{cell} @600dpi", x, y + mm(43), plane)

    # F: mottle fields at 25/50/75% (gain + spatial noise at realistic coverage)
    y = y0 + mm(124)
    for i, pct in enumerate((25, 50, 75)):
        x = x0 + mm(46 * i)
        job.put(f"mottle_{pct}", density_field(pct / 100, mm(40), 3, lp + f"/mottle{pct}".encode()),
                x, y, plane, "density_field", {"p": pct / 100, "cell_dots": 3}, save_gt=True)
        job.label(f"mottle {pct}%", x, y + mm(43), plane)

    # G: banding strips, left + right (process-direction ripple, step 6; scan-bar asymmetry)
    y = y0 + mm(172)
    for side, x in (("l", x0), ("r", x0 + mm(160))):
        job.put(f"banding_{side}", density_field(0.5, mm(25), 3, lp + f"/banding{side}".encode())[: mm(100), :],
                x, y, plane, "banding_strip", {"p": 0.5, "cell_dots": 3}, save_gt=True)
        job.label(f"banding {side}", x, y + mm(103), plane)

    job.doc.end_page()


def build_registration_page(job: Job) -> None:
    """Page 5: warp grid, inter-plane registration, overlays, 3-plane patch, 1200 probe."""
    job.begin_page()
    x0, y0 = mm(MARGIN_MM), mm(MARGIN_MM)
    job.label("paper-store exp001 p5 registration/overlay (all planes)", x0, y0 + mm(3), "K", 8)

    content: list[tuple[int, int, int, int]] = []  # occupied rects (x, y, w, h) in dots

    def occupy(x: int, y: int, w: int, h: int) -> None:
        content.append((x - mm(3), y - mm(3), w + mm(6), h + mm(6)))

    # verniers: pairs among C/M/Y, horizontal + vertical, center band (protocol step 4)
    vy = y0 + mm(110)
    pairs = (("C", "M"), ("C", "Y"), ("M", "Y"))
    for i, (pa, pb) in enumerate(pairs):
        x = x0 + mm(2 + 64 * i)
        a = vernier_comb(8, 24, mm(4), True)
        b = vernier_comb(9, 24, mm(4), True)
        job.put(f"vernier_h_{pa}{pb}_base", a, x, vy, pa, "vernier", {"period_dots": 8, "horizontal": True})
        job.put(f"vernier_h_{pa}{pb}_vern", b, x, vy + mm(4) + 4, pb, "vernier", {"period_dots": 9, "horizontal": True})
        job.label(f"{pa}/{pb} H", x, vy + mm(11), "K")
        av = vernier_comb(8, 24, mm(4), False)
        bv = vernier_comb(9, 24, mm(4), False)
        job.put(f"vernier_v_{pa}{pb}_base", av, x, vy + mm(14), pa, "vernier", {"period_dots": 8, "horizontal": False})
        job.put(f"vernier_v_{pa}{pb}_vern", bv, x + mm(4) + 4, vy + mm(14), pb, "vernier", {"period_dots": 9, "horizontal": False})
        job.label(f"{pa}/{pb} V", x + mm(10), vy + mm(26), "K")
        occupy(x, vy, mm(50), mm(52))

    # overlay solids: singles + pairwise + triple (crosstalk / unmixing matrix).
    # Overlaps composited into one CMYK image — overprint semantics vary by RIP.
    oy = y0 + mm(178)
    combos = (("C",), ("M",), ("Y",), ("C", "M"), ("C", "Y"), ("M", "Y"), ("C", "M", "Y"))
    solid = np.ones((mm(12), mm(12)), dtype=np.uint8)
    for i, planes in enumerate(combos):
        x = x0 + mm(16 * i)
        job.put_multi(f"overlay_{''.join(planes)}", {p: solid for p in planes}, x, oy, "overlay_solid", {})
        job.label("+".join(planes), x, oy + mm(15), "K")
    occupy(x0, oy, mm(16 * 7), mm(16))

    # 3-plane simultaneous encoding patch (the real archive channel, incl. registration)
    ey = y0 + mm(200)
    job.put_multi(
        "encode3",
        {p: encoding_patch(3, mm(50), f"exp001/p5/3plane/{p}".encode()) for p in ("C", "M", "Y")},
        x0, ey, "encoding_patch",
        {"cell_dots": 3, "pilot_block": 6, "pilot_period": 64}, save_gt=True)
    job.label("3-plane encode cell=3", x0, ey + mm(53), "K")
    occupy(x0, ey, mm(50), mm(56))

    # 1200 dpi addressability probe (K): if the engine is 600 native, the 1200-pitch
    # patch renders as unresolved ~50% gray while the 600 reference stays striped.
    # Probe coordinates are in PROBE_DPI dots: same physical position = 2x the value.
    px = x0 + mm(70)
    job.put("probe600_ref", line_pairs(1, mm(10), False), px, ey, "K", "line_pairs",
            {"pitch_dots": 1, "horizontal": False, "note": "600dpi reference"})
    job.put("probe1200", line_pairs(1, mm(10) * 2, False), (px + mm(14)) * 2, ey * 2, "K", "probe",
            {"pitch_dots": 1, "dpi": PROBE_DPI, "horizontal": False}, dpi=PROBE_DPI)
    job.put("probe1200_h", line_pairs(1, mm(10) * 2, True), (px + mm(28)) * 2, ey * 2, "K", "probe",
            {"pitch_dots": 1, "dpi": PROBE_DPI, "horizontal": True}, dpi=PROBE_DPI)
    job.label("600ref  1200V  1200H addressability probe", px, ey + mm(13), "K")
    occupy(px, ey, mm(42), mm(16))

    # warp / registration cross grid over remaining area: K cross at node, C/M/Y
    # crosses at fixed +5 mm offsets (registration frozen at fuse time — measure once)
    c = cross()
    quad_w = mm(5) + c.shape[1]
    step = mm(20)
    n = 0
    for gy in range(y0 + mm(8), y0 + mm(275) - quad_w, step):
        for gx in range(x0, x0 + mm(190) - quad_w, step):
            if any(gx < rx + rw and gx + quad_w > rx and gy < ry + rh and gy + quad_w > ry
                   for rx, ry, rw, rh in content):
                continue
            job.put(f"quad{n}_K", c, gx, gy, "K", "reg_cross", {"node": n, "offset_mm": [0, 0]})
            job.put(f"quad{n}_C", c, gx + mm(5), gy, "C", "reg_cross", {"node": n, "offset_mm": [5, 0]})
            job.put(f"quad{n}_M", c, gx, gy + mm(5), "M", "reg_cross", {"node": n, "offset_mm": [0, 5]})
            job.put(f"quad{n}_Y", c, gx + mm(5), gy + mm(5), "Y", "reg_cross", {"node": n, "offset_mm": [5, 5]})
            n += 1
    job.doc.end_page()


def build_mic_page(job: Job) -> None:
    """Page 6: MIC hunt — blank color-mode page (protocol step 5). No Y content at all."""
    job.begin_page()
    job.label("exp001 p6 MIC hunt - intentionally blank", mm(MARGIN_MM), mm(MARGIN_MM + 3), "K", 6)
    job.doc.end_page()


def build_job() -> Job:
    job = Job()
    for plane in PLANES:
        build_plane_page(job, plane)
    build_registration_page(job)
    build_mic_page(job)
    return job


def main() -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    job = build_job()
    ps = job.doc.render()
    ps_path = BUILD_DIR / "001_patterns.ps"
    ps_path.write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()
    manifest = {
        "experiment": "001-engine-characterization",
        "engine": "HP Color LaserJet Pro MFP M281fdw",
        "hw_dpi": HW_DPI,
        "seed": SEED.decode(),
        "ps_file": ps_path.name,
        "ps_sha256": sha,
        "print_command": "lpr -P <queue> -o raw 001_patterns.ps",
        "pages": job.page,
        "patches": job.entries,
    }
    (BUILD_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote {ps_path}  ({len(ps) / 1e6:.1f} MB, {job.page} pages, {len(job.entries)} patches)")
    print(f"sha256 {sha}")


if __name__ == "__main__":
    main()
