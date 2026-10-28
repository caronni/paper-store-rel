#!/usr/bin/env python
"""Experiment 002.1 — composite emission probe (print side).

Run 002.0's canary A measured that the M281 RIP re-screens DeviceCMYK 1-bit
`image` composites (psgen.put_cmyk_bitmap; ~165/212 lpi plane-angle screens,
28.5 dB peaks) while single-plane `imagemask` output is bit-faithful. This one
A4 page probes emission paths for OVERLAPPING plane content to find one that
is bit-faithful AND overlap-preserving on the real RIP:

  P0  put_cmyk_bitmap 4-channel image           — control, known re-screened
  P1  sequential per-plane imagemask, overprint OFF (default paint model) —
      expected knockout: the later plane erases the earlier at overlap in the
      RIP's plane buffers (signature: C=0 errors exactly at M=1 sites)
  P2  P1 + `true setoverprint` during each paint (LanguageLevel 2)
  P3  P2 + guarded nonzero overprint mode (OPM 1; Adobe PS3 integer form with
      Ghostscript boolean-dialect fallback — see psgen.put_bitmap)
  P4  C-only / M-only / Y-only single-plane imagemask references (known-clean
      controls; the BER + spectrum baselines for the decision rule)

Each of P0-P3 renders the SAME per-plane content (one variable at a time —
only the emission path differs): a 2-plane C+M 50% random cell=3 field
15x15 mm, a 3-plane C+M+Y field 15x15 mm, and a C+M solid overlap 8x8 mm.
Per-plane INTENT ground truth is saved for every stochastic patch (GT is what
was asked for; knockout is measured as deviation from it).

Registration reuses the EXACT chiral corner-mark + plus-mark geometry of
gen_calpage.py (builders imported from it — single source, byte-identical),
so cal_core's registration machinery works unchanged by passing this page's
manifest explicitly (cal_core.load_manifest's path is a parameter, default
calpage — do NOT touch cal_core):

    mf = cal_core.load_manifest(cal_core.BUILD / "composite_probe_manifest.json")
    scan = cal_core.load_scan(path); cal_core.register(scan, mf)

Outputs: build/composite_probe.ps, build/composite_probe_manifest.json,
build/composite_probe_gt/*.npy. Everything regenerates byte-identically from
SEED (sha256 gates reuse). Print ONLY via the raw path after user
confirmation in-session (.claude/rules/hardware.md); run protocol:
build/PROTOCOL-002.1-draft.md.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from paperholo.modulation import cells_to_dots, rng
from paperholo.psgen import CMYK, PSDoc

# byte-identical mark builders + geometry constants (attribution: gen_calpage,
# experiment 002.0 — cal_core reconstructs registration templates from these
# same functions, which is what makes the manifest swap sufficient).
import gen_calpage

SEED = b"paper-store/exp002-composite-probe"
LAYOUT_VERSION = 1
JOBID = hashlib.sha256(SEED + b"/layout1").hexdigest()[:8]
HW_DPI = 600
OUT = Path(__file__).parent / "build"
GT = OUT / "composite_probe_gt"

# content bounds identical to the calibration page (6 mm margins on A4)
X_MIN, X_MAX, Y_MIN, Y_MAX = 6.0, 204.0, 6.0, 291.0

CELL_DOTS = 3
FIELD_MM = 15.0
SOLID_MM = 8.0


def mm(v: float) -> int:
    return round(v / 25.4 * HW_DPI)


def field_bits(label: bytes) -> np.ndarray:
    """50% Bernoulli cell=3 field, FIELD_MM square, ink=1 (deterministic)."""
    n = mm(FIELD_MM) // CELL_DOTS
    cells = rng(SEED, label).integers(0, 2, size=(n, n), dtype=np.uint8)
    return cells_to_dots(cells, CELL_DOTS)


# the SAME content bits for every emission variant P0-P3:
def variant_content() -> dict[str, list[tuple[str, np.ndarray]]]:
    solid = np.ones((mm(SOLID_MM), mm(SOLID_MM)), np.uint8)
    return {
        "field_cm": [(p, field_bits(b"field_cm/" + p.encode())) for p in "CM"],
        "field_cmy": [(p, field_bits(b"field_cmy/" + p.encode())) for p in "CMY"],
        "solid_cm": [(p, solid.copy()) for p in "CM"],
    }


VARIANTS: dict[str, dict] = {
    "P0": {"emission": "cmyk_image", "overprint": None, "opm": None,
           "desc": "put_cmyk_bitmap DeviceCMYK 1-bit image composite — control, "
                   "re-screened by the M281 RIP (002.0 canary A)"},
    "P1": {"emission": "imagemask_seq", "overprint": False, "opm": False,
           "desc": "sequential per-plane imagemask, overprint off — expect knockout "
                   "(later plane erases earlier at overlap)"},
    "P2": {"emission": "imagemask_seq", "overprint": True, "opm": False,
           "desc": "sequential imagemask + true setoverprint; strict PLRM DeviceCMYK "
                   "still knocks out zero components at OPM 0 (gs 10.07 does) — RIPs vary"},
    "P3": {"emission": "imagemask_seq", "overprint": True, "opm": True,
           "desc": "P2 + guarded OPM 1 (1 setoverprintmode, gs bool-dialect fallback): "
                   "zero components leave other plates unmarked"},
    "P4": {"emission": "imagemask_single", "overprint": None, "opm": None,
           "desc": "single-plane imagemask references (bit-faithful per 002.0)"},
}
PAINT_ORDER_NOTE = "planes painted in listed order (C first); later paints win at overlap without overprint"


# ---------------------------------------------------------------------------
# page assembly (occupancy/label machinery adapted from gen_calpage.CalPage,
# experiment 002.0 — emission differs: per-variant overprint modes)
# ---------------------------------------------------------------------------

class ProbePage:
    def __init__(self) -> None:
        self.doc = PSDoc(hw_dpi=HW_DPI,
                         title=f"paper-store exp002.1 composite-probe LAY=1 J={JOBID}",
                         guard_setpagedevice=True)
        self.rects: list[tuple[int, int, int, int, int, str]] = []  # x0,y0,x1,y1,clr,name
        self.patches: list[dict] = []
        self.infra: list[dict] = []
        self.labels: list[dict] = []
        self._emits: list[tuple[str, str, object, int, int]] = []
        self._label_args: list[tuple[str, int, int, float]] = []
        self._gt_files: set[str] = set()

    # -- occupancy (gen_calpage.CalPage pattern) ----------------------------
    def _conflict(self, x0: int, y0: int, x1: int, y1: int, clr: int) -> str | None:
        for a0, b0, a1, b1, c2, nm in self.rects:
            g = max(clr, c2)
            if x0 < a1 + g and a0 < x1 + g and y0 < b1 + g and b0 < y1 + g:
                return nm
        return None

    def _occupy(self, name: str, x: int, y: int, w: int, h: int, clr_mm: float) -> None:
        clr = mm(clr_mm)
        if not (mm(X_MIN) <= x and x + w <= mm(X_MAX) and mm(Y_MIN) <= y and y + h <= mm(Y_MAX)):
            raise AssertionError(f"{name}: rect ({x},{y},{w},{h}) outside content bounds")
        hit = self._conflict(x, y, x + w, y + h, clr)
        if hit is not None:
            raise AssertionError(f"{name} overlaps {hit} (clearance {clr_mm} mm)")
        self.rects.append((x, y, x + w, y + h, clr, name))

    def _save_gt(self, name: str, bits: np.ndarray) -> str:
        GT.mkdir(parents=True, exist_ok=True)
        rel = f"composite_probe_gt/{name.replace('/', '__')}.npy"
        if rel in self._gt_files:
            raise AssertionError(f"ground-truth filename collision: {rel}")
        self._gt_files.add(rel)
        np.save(OUT / rel, bits.astype(np.uint8))
        return rel

    # -- content -------------------------------------------------------------
    def patch_single(self, name: str, bits: np.ndarray, x_mm: float, y_mm: float,
                     plane: str, kind: str, params: dict | None = None,
                     save_gt: bool = False, clearance_mm: float = 1.5) -> None:
        x, y = mm(x_mm), mm(y_mm)
        h, w = bits.shape
        self._occupy(name, x, y, w, h, clearance_mm)
        self._emits.append((name, "mask", (bits, plane), x, y))
        gt = self._save_gt(name, bits) if save_gt else None
        self.patches.append({"name": name, "kind": kind, "planes": [plane],
                             "x_dots": x, "y_dots": y, "w_dots": int(w), "h_dots": int(h),
                             "params": params or {}, "gt": gt})

    def patch_composite(self, name: str, planes: list[tuple[str, np.ndarray]],
                        x_mm: float, y_mm: float, kind: str, variant: str,
                        params: dict | None = None, save_gt: bool = False,
                        clearance_mm: float = 1.5) -> None:
        """One overlapping-plane patch, emitted per VARIANTS[variant]."""
        v = VARIANTS[variant]
        x, y = mm(x_mm), mm(y_mm)
        (h, w), = {b.shape for _, b in planes}
        self._occupy(name, x, y, w, h, clearance_mm)
        if v["emission"] == "cmyk_image":
            self._emits.append((name, "cmyk", dict(planes), x, y))
        else:
            self._emits.append((name, "masks",
                                (planes, v["overprint"], v["opm"]), x, y))
        base = {"variant": variant, "emission": v["emission"],
                "overprint": v["overprint"], "opm": v["opm"],
                "paint_order": [p for p, _ in planes]}
        for p, bits in planes:
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind, "planes": [p],
                                 "x_dots": x, "y_dots": y, "w_dots": int(w), "h_dots": int(h),
                                 "params": {**base, **(params or {})}, "gt": gt,
                                 "composite_of": name})

    def rect_entry(self, name: str, x_mm: float, y_mm: float, w_mm: float, h_mm: float,
                   kind: str, params: dict | None = None, clearance_mm: float = 0.5) -> None:
        x, y, w, h = mm(x_mm), mm(y_mm), mm(w_mm), mm(h_mm)
        self._occupy(name, x, y, w, h, clearance_mm)
        self.infra.append({"name": name, "kind": kind, "planes": [], "x_dots": x,
                           "y_dots": y, "w_dots": w, "h_dots": h,
                           "params": params or {}, "gt": None})

    def label(self, text: str, x_mm: float, y_baseline_mm: float, size_pt: float = 4.0) -> None:
        x, yb = mm(x_mm), mm(y_baseline_mm)
        w = round(len(text) * 0.58 * size_pt / 72 * HW_DPI)
        asc = round(0.78 * size_pt / 72 * HW_DPI)
        desc = round(0.24 * size_pt / 72 * HW_DPI)
        self.labels.append({"text": text, "x_dots": x, "y_dots": yb - asc,
                            "w_dots": w, "h_dots": asc + desc})
        self._label_args.append((text, x, yb, size_pt))

    def assert_labels_clear(self) -> None:
        for lb in self.labels:
            lx0, ly0 = lb["x_dots"], lb["y_dots"]
            lx1, ly1 = lx0 + lb["w_dots"], ly0 + lb["h_dots"]
            for x0, y0, x1, y1, _, nm in self.rects:
                if lx0 < x1 and x0 < lx1 and ly0 < y1 and y0 < ly1:
                    raise AssertionError(f"label {lb['text']!r} intersects {nm}")

    def place_plus_lattice(self) -> int:
        """21x21-dot plus marks on the 25.4 mm grid, whitespace only
        (gen_calpage.CalPage.place_plus_lattice, byte-identical marks)."""
        pm = gen_calpage.plus_mark()
        placed = 0
        for j in range(1, 12):
            for i in range(1, 8):
                cx, cy = 25.4 * i, 25.4 * j
                x, y = mm(cx) - 10, mm(cy) - 10
                if not (mm(X_MIN) <= x and x + 21 <= mm(X_MAX)
                        and mm(Y_MIN) <= y and y + 21 <= mm(Y_MAX)):
                    continue
                if self._conflict(x, y, x + 21, y + 21, mm(1.5)) is not None:
                    continue
                if any(lb["x_dots"] < x + 21 + mm(1.0) and x < lb["x_dots"] + lb["w_dots"] + mm(1.0)
                       and lb["y_dots"] < y + 21 + mm(1.0) and y < lb["y_dots"] + lb["h_dots"] + mm(1.0)
                       for lb in self.labels):
                    continue
                self.rects.append((x, y, x + 21, y + 21, mm(1.5), f"plus_{i}_{j}"))
                self._emits.append((f"plus_{i}_{j}", "mask", (pm, "K"), x, y))
                self.patches.append({"name": f"plus_{i}_{j}", "kind": "plus_mark",
                                     "planes": ["K"], "x_dots": x, "y_dots": y,
                                     "w_dots": 21, "h_dots": 21,
                                     "params": {"grid_node_inch": [i, j], "arm_dots": 3},
                                     "gt": None})
                placed += 1
        return placed

    # -- emission --------------------------------------------------------------
    def emit(self) -> None:
        self.doc.begin_page()
        for text, x, yb, size in self._label_args:
            self.doc.put_label(text, x, yb, CMYK["K"], size_pt=size)
        for name, mode, payload, x, y in self._emits:
            if mode == "mask":
                bits, plane = payload
                self.doc.put_bitmap(bits, x, y, CMYK[plane])
            elif mode == "masks":
                planes, overprint, opm = payload
                for plane, bits in planes:  # listed order: later paint wins sans overprint
                    self.doc.put_bitmap(bits, x, y, CMYK[plane],
                                        overprint=overprint, opm=opm)
            elif mode == "cmyk":
                self.doc.put_cmyk_bitmap(payload, x, y)
            else:
                raise AssertionError(f"unknown emission mode {mode!r}")
        self.doc.end_page()


# ---------------------------------------------------------------------------
# layout: header, corner marks, 5 variant rows, quiet zone, plus lattice
# ---------------------------------------------------------------------------

ROW_Y = {"P0": 28.0, "P1": 52.0, "P2": 76.0, "P3": 100.0, "P4": 124.0}
COL_X = {"field_cm": 38.0, "field_cmy": 56.0, "solid_cm": 74.0}
ROW_LABEL = {
    "P0": "P0 cmyk image (screened ctrl)",
    "P1": "P1 masks, no overprint",
    "P2": "P2 masks, setoverprint",
    "P3": "P3 masks, ovp + OPM 1",
    "P4": "P4 single-plane refs",
}


def build_page(pp: ProbePage) -> dict:
    # header (title 7 pt + regen line 5 pt), clear of the TL/TR corner marks
    pp.label(f"paper-store exp002.1 COMPOSITE-PROBE LAY=1 J={JOBID} R0={HW_DPI}x{HW_DPI}dpi",
             16.0, 9.5, size_pt=7.0)
    pp.label(f"S={SEED.decode()}  regen: gen_composite_probe.py (byte-identical, sha256 "
             "gates reuse)  print: raw path only, one sheet  scan: 1200dpi RGB, "
             "enhancements OFF", 16.0, 13.5, size_pt=5.0)

    # chiral corner marks — EXACT gen_calpage geometry and positions
    for tag, n_sat, inward, cx, cy in (("tl", 1, (1, 1), 10.0, 10.0),
                                       ("tr", 2, (1, -1), 200.0, 10.0),
                                       ("br", 3, (-1, -1), 200.0, 288.0),
                                       ("bl", 4, (-1, 1), 10.0, 288.0)):
        pp.patch_single(f"corner_{tag}", gen_calpage.corner_mark(n_sat, inward),
                        cx - 61 * 25.4 / HW_DPI, cy - 61 * 25.4 / HW_DPI, "K",
                        "corner_mark",
                        {"satellites": n_sat, "inward": list(inward), "arm_dots": 60,
                         "width_dots": 3, "cx_dots": mm(cx), "cy_dots": mm(cy)},
                        clearance_mm=0.5)

    # column headers
    pp.label("CM c3 50%", COL_X["field_cm"], 26.0)
    pp.label("CMY c3 50%", COL_X["field_cmy"], 26.0)
    pp.label("CM solid", COL_X["solid_cm"], 26.0)

    # P0-P3: identical content, emission path is the ONE variable
    content = variant_content()
    for vid in ("P0", "P1", "P2", "P3"):
        y0 = ROW_Y[vid]
        pp.label(ROW_LABEL[vid], 8.0, y0 + 7.5)
        pp.patch_composite(f"{vid}/field_cm", content["field_cm"],
                           COL_X["field_cm"], y0, "density_field", vid,
                           {"p": 0.5, "cell_dots": CELL_DOTS}, save_gt=True)
        pp.patch_composite(f"{vid}/field_cmy", content["field_cmy"],
                           COL_X["field_cmy"], y0, "density_field", vid,
                           {"p": 0.5, "cell_dots": CELL_DOTS}, save_gt=True)
        pp.patch_composite(f"{vid}/solid_cm", content["solid_cm"],
                           COL_X["solid_cm"], y0, "overlay_solid", vid,
                           save_gt=True)

    # P4: single-plane references (fields + solids), independent keystream labels
    y0 = ROW_Y["P4"]
    pp.label(ROW_LABEL["P4"], 8.0, y0 + 7.5)
    for p, x in (("C", 38.0), ("M", 56.0), ("Y", 74.0)):
        pp.patch_single(f"P4/ref_{p}", field_bits(b"ref/" + p.encode()), x, y0, p,
                        "density_field",
                        {"variant": "P4", "emission": "imagemask_single",
                         "p": 0.5, "cell_dots": CELL_DOTS}, save_gt=True)
        pp.label(p, x, y0 + 16.8)
    for p, x in (("C", 92.0), ("M", 103.0), ("Y", 114.0)):
        pp.patch_single(f"P4/solid_{p}", np.ones((mm(SOLID_MM), mm(SOLID_MM)), np.uint8),
                        x, y0, p, "solid",
                        {"variant": "P4", "emission": "imagemask_single"}, save_gt=True)
        pp.label(f"{p}100", x, y0 + 9.8)

    # quiet zone: white reference + scanner noise floor for the spectra
    pp.rect_entry("quiet_zone", 38.0, 150.0, 25.0, 25.0, "quiet_zone",
                  {"purpose": "white ref + noise floor for screening spectra"},
                  clearance_mm=1.5)
    pp.label("quiet zone (blank)", 38.0, 177.0)

    n_plus = pp.place_plus_lattice()
    pp.assert_labels_clear()
    return {"n_plus_marks": n_plus}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GT.mkdir(parents=True, exist_ok=True)
    pp = ProbePage()
    extra = build_page(pp)
    pp.emit()
    ps = pp.doc.render()
    (OUT / "composite_probe.ps").write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()
    manifest = {
        "experiment": "002-calibration-page",
        "artifact": "composite_probe",
        "run": "002.1",
        "layout_version": LAYOUT_VERSION,
        "seed": SEED.decode(),
        "jobid": JOBID,
        "hw_dpi": HW_DPI,
        "ps_file": "composite_probe.ps",
        "ps_sha256": sha,
        "print_command": "../../scripts/print_plane.sh build/composite_probe.ps",
        "content_bounds_mm": [X_MIN, Y_MIN, X_MAX, Y_MAX],
        "variants": VARIANTS,
        "paint_order_note": PAINT_ORDER_NOTE,
        "n_plus_marks": extra["n_plus_marks"],
        "patches": pp.patches,
        "infrastructure": pp.infra,
        "labels": pp.labels,
    }
    (OUT / "composite_probe_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote build/composite_probe.ps ({len(ps) / 1e6:.2f} MB, "
          f"{len(pp.patches)} patches, {extra['n_plus_marks']} plus marks)")
    print(f"sha256 {sha}")


if __name__ == "__main__":
    main()
