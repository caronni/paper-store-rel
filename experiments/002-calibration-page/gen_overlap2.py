#!/usr/bin/env python
"""Experiment 002.2 — overlap-alphabet + separation-emission sheet (print side).

002.0c measured the 8-state CMY cell=3 alphabet through the screened
put_cmyk_bitmap path at MI 1.757 (Blahut-Arimoto capacity 1.893) and found the
best uniform alphabet is the 7-set {W,C,M,Y,CM,CY,MY} (1.890 — drop the CMY
triple); {7-set + K} scored 1.801 on the 16-state data. The RIP's ~3.6-dot
screen period aliases against 3-dot cells, so cell=4/6 mixtures may improve
markedly. This ONE A4 page measures that upside and, in a strictly ordered
error-contained tail, probes two Separation/DeviceN emission paths that could
beat the screened composite path:

Block A — screened-channel upside (put_cmyk_bitmap, known overlap-preserving
on the M281 per 002.0 canary A / 002.1):
  A1  7-state uniform fields, cell=3 20x20 mm, cell=4 24x24 mm, cell=6 30x30 mm
      (>=1.7k cells/state each, asserted on the drawn field)
  A2  8-state {7-set + pure K} at cell=4, 24x24 mm (K cells are K-plane only)
  A3  classic 3-plane 50% binary composites: cell=4 20x20 mm, cell=6 24x24 mm
      (per-plane composite BER ladder vs 002.0's cell=3)
  A4  single-plane imagemask references (bit-faithful clean-channel baselines):
      C,M,Y,K 50% at cell=4 12x12 mm; K at cell=6 12x12 mm

Block B — Separation/DeviceN overlap probes, LAST in the PS stream (a
mid-image fault can only cost later S-blocks, never Block A; the END sentinel
is the very last element). All three variants paint BYTE-IDENTICAL per-plane
content (one rng draw per patch slot; the emission path is the only variable):
  S1  per-plane imagemask in [/Separation (ink) /DeviceCMYK tint->plane]
      setcolorspace, 1 setcolor + true setoverprint inside each paint's gsave
  S2  S1 + the 002.1 OPM dance (integer form first, gs boolean fallback,
      each where/stopped-guarded)
  S3  one 3-component /DeviceN [(Cyan)(Magenta)(Yellow)] /DeviceCMYK
      tint-transform image, 1 bit/component — the DeviceN twin of
      put_cmyk_bitmap
All S-variant procedural code (setcolorspace/setcolor/setoverprint) is
stopped-guarded; inline imagemask/image data is not guardable (currentfile),
which is exactly why the S-blocks stream last.

Registration reuses the EXACT chiral corner-mark + plus-mark geometry of
gen_calpage.py (builders imported — single source, byte-identical), so
cal_core registers this page by manifest swap:

    mf = cal_core.load_manifest(cal_core.BUILD / "overlap2_manifest.json")

Outputs: build/overlap2.ps, build/overlap2_manifest.json, build/overlap2_gt/
*.npy. Everything regenerates byte-identically from SEED (sha256 gates reuse).
psgen is deliberately NOT modified: S-blocks are emitted via doc.put_raw with
hex data generated here. Print ONLY via the raw path after user confirmation
in-session (.claude/rules/hardware.md).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from paperholo.modulation import cells_to_dots, rng
from paperholo.psgen import A4_PT, CMYK, PSDoc, pack_bits_rows

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

# byte-identical mark builders (gen_calpage) + occupancy/label machinery
# (gen_composite_probe.ProbePage — subclassed below; attribution: exp 002.0/002.1)
import gen_calpage  # noqa: E402
import gen_composite_probe as gcp  # noqa: E402

SEED = b"paper-store/exp002-overlap2"
LAYOUT_VERSION = 1
JOBID = hashlib.sha256(SEED + b"/layout1").hexdigest()[:8]
HW_DPI = 600
OUT = _HERE / "build"
GT = OUT / "overlap2_gt"

# content bounds identical to the calibration page (6 mm margins on A4)
X_MIN, X_MAX, Y_MIN, Y_MAX = 6.0, 204.0, 6.0, 291.0

# 002.0c winning alphabet: uniform 7-set (CMY triple dropped); +K variant.
STATES7 = ("W", "C", "M", "Y", "CM", "CY", "MY")
STATES8K = STATES7 + ("K",)
MIN_CELLS_PER_STATE = 1700


def mm(v: float) -> int:
    return round(v / 25.4 * HW_DPI)


def pt(v_mm: float) -> float:
    return v_mm / 25.4 * 72.0


# ---------------------------------------------------------------------------
# pattern builders (pure; 1 = ink; all randomness via rng(SEED, label))
# ---------------------------------------------------------------------------

def uniform_state_field(size_mm: float, cell_dots: int, states: tuple[str, ...],
                        label: bytes) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Per-cell state i.i.d. uniform over `states`; returns (state array,
    per-plane dot bitmaps). State name spells its inked planes ('W' = none)."""
    n = mm(size_mm) // cell_dots
    st = rng(SEED, label).integers(0, len(states), size=(n, n), dtype=np.uint8)
    counts = np.bincount(st.ravel(), minlength=len(states))
    assert counts.min() >= MIN_CELLS_PER_STATE, \
        f"{label!r}: min {int(counts.min())} cells/state < {MIN_CELLS_PER_STATE}"
    planes: dict[str, np.ndarray] = {}
    for p in "CMYK":
        member = np.array([int(p in s) for s in states], np.uint8)
        if member.any():
            planes[p] = cells_to_dots(member[st], cell_dots)
    return st, planes


def half_field(size_mm: float, cell_dots: int, label: bytes) -> np.ndarray:
    """50% Bernoulli field at `cell_dots`, ink=1 (deterministic)."""
    n = mm(size_mm) // cell_dots
    cells = rng(SEED, label).integers(0, 2, size=(n, n), dtype=np.uint8)
    return cells_to_dots(cells, cell_dots)


# the SAME per-plane content for every S variant (one rng draw per patch slot;
# emission path is the only variable across S1/S2/S3):
def s_content() -> dict[str, list[tuple[str, np.ndarray]]]:
    solid = np.ones((mm(8.0), mm(8.0)), np.uint8)
    return {
        "field_cm": [(p, half_field(15.0, 3, b"s/field_cm/" + p.encode())) for p in "CM"],
        "field_cmy": [(p, half_field(15.0, 3, b"s/field_cmy/" + p.encode())) for p in "CMY"],
        "solid_cm": [(p, solid.copy()) for p in "CM"],
    }


S_VARIANTS: dict[str, dict] = {
    "S1": {"emission": "sep_imagemask", "overprint": True, "opm": False,
           "desc": "per-plane imagemask in [/Separation (ink) /DeviceCMYK "
                   "tint->plane] setcolorspace, 1 setcolor + true setoverprint "
                   "per paint (gsave-scoped; color setup stopped-guarded)"},
    "S2": {"emission": "sep_imagemask", "overprint": True, "opm": True,
           "desc": "S1 + guarded OPM-1 dance: `1 setoverprintmode` integer form "
                   "first, gs boolean-dialect fallback, each where/stopped-"
                   "guarded (the 002.1 psgen recipe, emitted raw here)"},
    "S3": {"emission": "devicen_image", "overprint": False, "opm": False,
           "desc": "one 3-component /DeviceN [(Cyan)(Magenta)(Yellow)] "
                   "/DeviceCMYK tint-transform image, 1 bit/component — the "
                   "DeviceN twin of put_cmyk_bitmap"},
}
S_ROW_LABEL = {
    "S1": "S1 sep masks + setoverprint",
    "S2": "S2 sep masks + ovp + OPM 1",
    "S3": "S3 DeviceN CMY image",
}


# ---------------------------------------------------------------------------
# raw-PS emitters for the S-blocks (psgen stays untouched; geometry mirrors
# psgen.put_bitmap / put_cmyk_bitmap exactly: top-left dot coords, y flipped)
# ---------------------------------------------------------------------------

def _hex_lines(packed: bytes, width: int = 128) -> list[str]:
    h = packed.hex()
    return [h[i: i + width] for i in range(0, len(h), width)]


# tint-transform procs: tint t on the stack -> c m y k for that ink only
SEP_TINT = {"C": ("Cyan", "0 0 0"),
            "M": ("Magenta", "0 exch 0 0"),
            "Y": ("Yellow", "0 0 3 -1 roll 0")}

OPM_DANCE = [
    "/setoverprintmode where { pop",
    "  mark { 1 setoverprintmode } stopped",
    "  { cleartomark mark { true setoverprintmode } stopped cleartomark }",
    "  { cleartomark } ifelse } if",
]


def sep_mask_lines(bits: np.ndarray, x_dots: int, y_dots: int, plane: str,
                   opm: bool) -> list[str]:
    """One imagemask paint in a Separation color space, overprint on."""
    h, w = bits.shape
    x_pt = x_dots * 72.0 / HW_DPI
    y_pt = A4_PT[1] - (y_dots + h) * 72.0 / HW_DPI
    ink, proc = SEP_TINT[plane]
    lines = [
        "gsave",
        "mark { [/Separation (" + ink + ") /DeviceCMYK { " + proc + " }] setcolorspace",
        "  1 setcolor true setoverprint } stopped cleartomark",
    ]
    if opm:
        lines += OPM_DANCE
    lines += [
        f"{x_pt:.6f} {y_pt:.6f} translate",
        f"{w * 72.0 / HW_DPI:.6f} {h * 72.0 / HW_DPI:.6f} scale",
        f"{w} {h} true [{w} 0 0 -{h} 0 {h}]",
        "currentfile /ASCIIHexDecode filter imagemask",
        *_hex_lines(pack_bits_rows(bits)),
        ">",
        "grestore",
    ]
    return lines


def devicen_image_lines(planes: dict[str, np.ndarray], x_dots: int,
                        y_dots: int) -> list[str]:
    """One 3-component DeviceN CMY image, 1 bit/component (missing planes = 0)."""
    (h, w), = {a.shape for a in planes.values()}
    px = np.zeros((h, w, 3), dtype=np.uint8)
    for i, p in enumerate("CMY"):
        if p in planes:
            px[:, :, i] = planes[p].astype(np.uint8)
    x_pt = x_dots * 72.0 / HW_DPI
    y_pt = A4_PT[1] - (y_dots + h) * 72.0 / HW_DPI
    return [
        "gsave",
        "mark { [/DeviceN [(Cyan) (Magenta) (Yellow)] /DeviceCMYK { 0 }]"
        " setcolorspace } stopped cleartomark",
        f"{x_pt:.6f} {y_pt:.6f} translate",
        f"{w * 72.0 / HW_DPI:.6f} {h * 72.0 / HW_DPI:.6f} scale",
        "<< /ImageType 1",
        f"   /Width {w} /Height {h} /BitsPerComponent 1",
        "   /Decode [0 1 0 1 0 1]",
        f"   /ImageMatrix [{w} 0 0 -{h} 0 {h}]",
        "   /DataSource currentfile /ASCIIHexDecode filter",
        ">> image",
        *_hex_lines(pack_bits_rows(px.reshape(h, w * 3))),
        ">",
        "grestore",
    ]


def sentinel_lines() -> list[str]:
    """END sentinel — the very last element in the stream (stopped-guarded)."""
    return [
        "% ---- END sentinel: LAST element in the stream ----",
        "mark { initmatrix 0 0 0 1 setcmykcolor",
        f"  {pt(18.0):.2f} {A4_PT[1] - pt(289.0):.2f} {pt(2.5):.2f} {pt(2.5):.2f} rectfill",
        "  /Helvetica findfont 6 scalefont setfont",
        f"  {pt(22.5):.2f} {A4_PT[1] - pt(289.2):.2f} moveto"
        f" (END {JOBID} exp002 overlap2) show }} stopped cleartomark",
    ]


# ---------------------------------------------------------------------------
# page assembly: ProbePage machinery reused (occupancy, labels, plus lattice);
# emission overridden for the strict Block-A -> S1 -> S2 -> S3 -> END order
# ---------------------------------------------------------------------------

class OverlapPage(gcp.ProbePage):
    def __init__(self) -> None:
        super().__init__()
        self.doc = PSDoc(hw_dpi=HW_DPI,
                         title=f"paper-store exp002.2 overlap2 LAY=1 J={JOBID}",
                         guard_setpagedevice=True)
        # S-block emissions, kept apart from _emits so Block A always streams first
        self._s_emits: list[tuple[str, str, list[tuple[str, np.ndarray]], int, int]] = []

    def _save_gt(self, name: str, bits: np.ndarray) -> str:
        GT.mkdir(parents=True, exist_ok=True)
        rel = f"overlap2_gt/{name.replace('/', '__')}.npy"
        if rel in self._gt_files:
            raise AssertionError(f"ground-truth filename collision: {rel}")
        self._gt_files.add(rel)
        np.save(OUT / rel, bits.astype(np.uint8))
        return rel

    def patch_cmyk(self, name: str, planes: dict[str, np.ndarray], x_mm: float,
                   y_mm: float, kind: str, params: dict | None = None,
                   save_gt: bool = False, clearance_mm: float = 1.5) -> None:
        """Block-A overlapping-plane patch via put_cmyk_bitmap (screened path)."""
        x, y = mm(x_mm), mm(y_mm)
        (h, w), = {a.shape for a in planes.values()}
        self._occupy(name, x, y, w, h, clearance_mm)
        self._emits.append((name, "cmyk", dict(planes), x, y))
        base = {"block": "A", "emission": "cmyk_image"}
        for p, bits in planes.items():
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind, "planes": [p],
                                 "x_dots": x, "y_dots": y, "w_dots": int(w), "h_dots": int(h),
                                 "params": {**base, **(params or {})}, "gt": gt,
                                 "composite_of": name})

    def patch_sep(self, name: str, variant: str, planes: list[tuple[str, np.ndarray]],
                  x_mm: float, y_mm: float, kind: str, params: dict | None = None,
                  save_gt: bool = True, clearance_mm: float = 1.5) -> None:
        """Block-B patch, emitted per S_VARIANTS[variant] in the stream tail."""
        v = S_VARIANTS[variant]
        x, y = mm(x_mm), mm(y_mm)
        (h, w), = {b.shape for _, b in planes}
        self._occupy(name, x, y, w, h, clearance_mm)
        self._s_emits.append((name, variant, planes, x, y))
        base = {"block": "B", "variant": variant, "emission": v["emission"],
                "overprint": v["overprint"], "opm": v["opm"],
                "paint_order": [p for p, _ in planes]}
        for p, bits in planes:
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind, "planes": [p],
                                 "x_dots": x, "y_dots": y, "w_dots": int(w), "h_dots": int(h),
                                 "params": {**base, **(params or {})}, "gt": gt,
                                 "composite_of": name})

    # -- emission: labels, Block A bitmaps, S1/S2/S3 raw tail, END sentinel ---
    def emit(self) -> None:
        d = self.doc
        d.begin_page()
        for text, x, yb, size in self._label_args:
            d.put_label(text, x, yb, CMYK["K"], size_pt=size)
        d.put_raw(["% ==== BLOCK A: single-plane masks + DeviceCMYK 1-bit"
                   " image composites ===="])
        for name, mode, payload, x, y in self._emits:
            if mode == "mask":
                bits, plane = payload
                d.put_bitmap(bits, x, y, CMYK[plane])
            elif mode == "cmyk":
                d.put_cmyk_bitmap(payload, x, y)
            else:
                raise AssertionError(f"unknown emission mode {mode!r}")
        d.put_raw(["% ==== BLOCK B: separation + devicen overlap probes"
                   " (error-contained stream tail) ===="])
        for name, variant, planes, x, y in self._s_emits:
            v = S_VARIANTS[variant]
            if v["emission"] == "sep_imagemask":
                for plane, bits in planes:  # listed paint order (C first)
                    d.put_raw([f"% ---- {name} {plane} sep-mask"
                               f" opm={int(bool(v['opm']))} ----"])
                    d.put_raw(sep_mask_lines(bits, x, y, plane, v["opm"]))
            else:
                d.put_raw([f"% ---- {name} devicen-image ----"])
                d.put_raw(devicen_image_lines(dict(planes), x, y))
        d.put_raw(sentinel_lines())
        d.end_page()


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------

S_ROW_Y = {"S1": 100.0, "S2": 124.0, "S3": 148.0}
S_COL_X = {"field_cm": 38.0, "field_cmy": 58.0, "solid_cm": 78.0}


def add_state_field(pg: OverlapPage, name: str, size_mm: float, cell_dots: int,
                    states: tuple[str, ...], label: bytes,
                    x_mm: float, y_mm: float) -> None:
    st, planes = uniform_state_field(size_mm, cell_dots, states, label)
    GT.mkdir(parents=True, exist_ok=True)
    states_rel = f"overlap2_gt/{name.replace('/', '__')}_states.npy"
    np.save(OUT / states_rel, st)
    pg.patch_cmyk(name, planes, x_mm, y_mm, "state_field",
                  {"cell_dots": cell_dots, "n_states": len(states),
                   "state_names": list(states),
                   "state_encoding": "cell value = index into state_names; "
                                     "name spells inked planes, W = none",
                   "states_gt": states_rel},
                  save_gt=True)


def build_page(pg: OverlapPage) -> dict:
    # header (7 pt title + 5 pt regen line), clear of the TL/TR corner marks
    pg.label(f"paper-store exp002.2 OVERLAP2 LAY=1 J={JOBID} R0={HW_DPI}x{HW_DPI}dpi",
             16.0, 9.5, size_pt=7.0)
    pg.label(f"S={SEED.decode()}  regen: gen_overlap2.py (byte-identical, sha256 "
             "gates reuse)  print: raw path only, one sheet  scan: 1200dpi RGB, "
             "enhancements OFF", 16.0, 13.5, size_pt=5.0)

    # chiral corner marks — EXACT gen_calpage geometry and positions
    for tag, n_sat, inward, cx, cy in (("tl", 1, (1, 1), 10.0, 10.0),
                                       ("tr", 2, (1, -1), 200.0, 10.0),
                                       ("br", 3, (-1, -1), 200.0, 288.0),
                                       ("bl", 4, (-1, 1), 10.0, 288.0)):
        pg.patch_single(f"corner_{tag}", gen_calpage.corner_mark(n_sat, inward),
                        cx - 61 * 25.4 / HW_DPI, cy - 61 * 25.4 / HW_DPI, "K",
                        "corner_mark",
                        {"satellites": n_sat, "inward": list(inward), "arm_dots": 60,
                         "width_dots": 3, "cx_dots": mm(cx), "cy_dots": mm(cy)},
                        clearance_mm=0.5)

    # -- Block A row 1: 7-state fields (c3/c4/c6) + 8-state {7-set + K} c4 ----
    pg.label("A1 7-state {W C M Y CM CY MY} uniform + A2 {7set+K}, cmyk-image path",
             12.0, 18.0)
    add_state_field(pg, "A1/state7_c3", 20.0, 3, STATES7, b"a1/state7_c3", 12.0, 20.0)
    pg.label("7st c3", 12.0, 42.2)
    add_state_field(pg, "A1/state7_c4", 24.0, 4, STATES7, b"a1/state7_c4", 37.0, 20.0)
    pg.label("7st c4", 37.0, 46.2)
    add_state_field(pg, "A1/state7_c6", 30.0, 6, STATES7, b"a1/state7_c6", 66.0, 20.0)
    pg.label("7st c6", 66.0, 52.2)
    add_state_field(pg, "A2/state8k_c4", 24.0, 4, STATES8K, b"a2/state8k_c4", 101.0, 20.0)
    pg.label("8st+K c4", 101.0, 46.2)

    # -- Block A row 2: 50% composites + single-plane imagemask references ----
    pg.label("A3 3-plane 50% composites (cmyk-image)  |  A4 single-plane mask refs",
             12.0, 56.0)
    pg.patch_cmyk("A3/comp_c4",
                  {p: half_field(20.0, 4, b"a3/comp_c4/" + p.encode()) for p in "CMY"},
                  12.0, 58.0, "density_field", {"p": 0.5, "cell_dots": 4}, save_gt=True)
    pg.label("cmy50 c4", 12.0, 80.2)
    pg.patch_cmyk("A3/comp_c6",
                  {p: half_field(24.0, 6, b"a3/comp_c6/" + p.encode()) for p in "CMY"},
                  37.0, 58.0, "density_field", {"p": 0.5, "cell_dots": 6}, save_gt=True)
    pg.label("cmy50 c6", 37.0, 84.2)
    xr = 68.0
    for p in "CMYK":
        pg.patch_single(f"A4/ref_{p}_c4", half_field(12.0, 4, b"a4/ref_" + p.encode() + b"_c4"),
                        xr, 58.0, p, "density_field",
                        {"block": "A", "emission": "imagemask_single",
                         "p": 0.5, "cell_dots": 4}, save_gt=True)
        pg.label(f"{p} c4", xr, 72.2)
        xr += 16.0
    pg.patch_single("A4/ref_K_c6", half_field(12.0, 6, b"a4/ref_K_c6"),
                    xr, 58.0, "K", "density_field",
                    {"block": "A", "emission": "imagemask_single",
                     "p": 0.5, "cell_dots": 6}, save_gt=True)
    pg.label("K c6", xr, 72.2)

    # quiet zone: white reference + scanner noise floor for screening spectra
    pg.rect_entry("quiet_zone", 150.0, 56.0, 25.0, 25.0, "quiet_zone",
                  {"purpose": "white ref + noise floor for screening spectra"},
                  clearance_mm=1.5)
    pg.label("quiet zone (blank)", 150.0, 83.2)

    # -- Block B: S1/S2/S3, byte-identical content, stream tail ---------------
    pg.label("B separation + devicen overlap probes (stream tail, error-contained)",
             8.0, 94.0)
    pg.label("CM c3 50%", S_COL_X["field_cm"], 98.0)
    pg.label("CMY c3 50%", S_COL_X["field_cmy"], 98.0)
    pg.label("CM solid", S_COL_X["solid_cm"], 98.0)
    content = s_content()
    for vid in ("S1", "S2", "S3"):
        y0 = S_ROW_Y[vid]
        pg.label(S_ROW_LABEL[vid], 8.0, y0 + 8.0)
        pg.patch_sep(f"{vid}/field_cm", vid, content["field_cm"],
                     S_COL_X["field_cm"], y0, "density_field",
                     {"p": 0.5, "cell_dots": 3}, save_gt=True)
        pg.patch_sep(f"{vid}/field_cmy", vid, content["field_cmy"],
                     S_COL_X["field_cmy"], y0, "density_field",
                     {"p": 0.5, "cell_dots": 3}, save_gt=True)
        pg.patch_sep(f"{vid}/solid_cm", vid, content["solid_cm"],
                     S_COL_X["solid_cm"], y0, "overlay_solid", {}, save_gt=True)

    # END sentinel reserve (drawn print-time as the very last stream element)
    pg.rect_entry("end_sentinel", 18.0, 286.5, 42.0, 2.8, "end_sentinel",
                  {"text": f"END {JOBID} exp002 overlap2"})

    n_plus = pg.place_plus_lattice()
    pg.assert_labels_clear()
    return {"n_plus_marks": n_plus}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GT.mkdir(parents=True, exist_ok=True)
    pg = OverlapPage()
    extra = build_page(pg)
    pg.emit()
    ps = pg.doc.render()
    assert "%%Pages: 1" in ps and ps.count("%%Page:") == 1, "must be ONE page"
    # stream-order self-check: all Block-A content precedes any S-block
    assert ps.rindex("/Decode [0 1 0 1 0 1 0 1]") < ps.index("/Separation (") \
        < ps.index("/DeviceN ["), "Block A must stream before S1/S2 before S3"
    (OUT / "overlap2.ps").write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()
    manifest = {
        "experiment": "002-calibration-page",
        "artifact": "overlap2",
        "run": "002.2",
        "layout_version": LAYOUT_VERSION,
        "seed": SEED.decode(),
        "jobid": JOBID,
        "hw_dpi": HW_DPI,
        "ps_file": "overlap2.ps",
        "ps_sha256": sha,
        "print_command": "../../scripts/print_plane.sh build/overlap2.ps",
        "content_bounds_mm": [X_MIN, Y_MIN, X_MAX, Y_MAX],
        "alphabet_note": "002.0c: best uniform alphabet {W,C,M,Y,CM,CY,MY} MI 1.890 "
                         "vs BA capacity 1.893 at cell=3 through the screened path; "
                         "screen period ~3.6 dots aliases 3-dot cells -> c4/c6 probed",
        "s_variants": S_VARIANTS,
        "stream_order": "labels, Block-A bitmaps, S1, S2, S3, END sentinel "
                        "(mid-image faults only cost later S-blocks)",
        "n_plus_marks": extra["n_plus_marks"],
        "patches": pg.patches,
        "infrastructure": pg.infra,
        "labels": pg.labels,
    }
    (OUT / "overlap2_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote build/overlap2.ps ({len(ps) / 1e6:.2f} MB, "
          f"{len(pg.patches)} patches, {extra['n_plus_marks']} plus marks)")
    print(f"sha256 {sha}")


if __name__ == "__main__":
    main()
