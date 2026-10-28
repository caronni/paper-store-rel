#!/usr/bin/env python
"""Experiment 008 — MSEL-1: portable MODE-SELECTION sheet for a NOVEL printer.

TWO pages, A4, LanguageLevel 2 portable (disc1 containment idioms). Unlike
DISC-1 there is NO resolution probing anywhere: the job never touches
/HWResolution — it measures the DEVICE-DEFAULT render path, which 007.6
showed is the only PS-reachable grid on the AltaLink class and the sane one
on the M281. PageSize [595 842] is requested inside a stopped guard only.

PAGE 1 (decision-critical, color): strips + chiral corners + plus lattice;
K portfolio (c2..c6 PN fields + RLL i2w3) at THREE page positions; CMY
portfolio (A3 7-state c3 + A4 {7+K} c4 put_cmyk composites) at three
positions; per-plane isolated C/M/Y c3 minis (x2); emission probe pair
(P0 put_cmyk vs P3 masks+setoverprint+OPM overlapping C+M solids — the
002.1 knockout/screen discriminator); crosstalk row (clean C/M/Y/K solids +
paper gap + cmyk-path CM/CY/MY); morphology minis (line ladders 1-4 H/V,
checkers, white holes 1-4, Nyquist 1-on/1-off, iso dots @8) + tone wedge;
scanner-adequacy block (known c3 + c2 fields, 2-on/2-off gratings, high-
entropy JPEG canary); 26x26 mm MIC quiet zone; END sentinel last.

PAGE 2 (K-ONLY replica, duplex-tolerant, self-contained): two more K
portfolio positions + 40x40 mm big anchors (c2, c3, RLL) + morphology
replica + its own quiet zone — the K-only page doubles as the MIC
color-content-gating control (007.8-C1). Strip payload preamble PHCAL1;PG=2;
(stripdec field parsing unchanged).

Error containment (exp002/007 idiom): device query + payload + strips
stream BEFORE any inline-data bitmap; masks small to large; put_cmyk
composites after all masks; END sentinel last-in-page. All randomness from
SEED via paperholo.modulation.rng; byte-identical regeneration (sha-gated).

Outputs: build/msel1.ps, build/msel1_manifest.json, build/msel1_gt/*.npy.
Protocol + PRE-REGISTERED decision rules: experiments/008-mode-select.md.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from paperholo.modulation import cells_to_dots, rng
from paperholo.psgen import A4_PT, CMYK

_HERE = Path(__file__).resolve().parent
_EXP002 = _HERE.parent / "002-calibration-page"
_EXP003 = _HERE.parent / "003-modulation-probes"
_EXP007 = _HERE.parent / "007-office-disc"
for _p in (str(_HERE), str(_EXP002), str(_EXP003), str(_EXP007)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# byte-identical builders + the portable doc class (pure; attribution:
# exp 002.0 marks, exp 003.0 row-DP sampler, exp 007 portable header/strips)
import gen_calpage  # noqa: E402
import gen_disc1  # noqa: E402
import gen_modprobe as gmp  # noqa: E402

SEED = b"paper-store/exp008-msel1"
LAYOUT_VERSION = 1
JOBID = hashlib.sha256(SEED + b"/layout1").hexdigest()[:8]
BASE_DPI = 600            # layout/manifest grid ONLY — never requested
STRIP_S_FIELD = "exp008-msel1"
OUT = _HERE / "build"
GT = OUT / "msel1_gt"
PS_BUDGET_BYTES = 16_000_000

# content bounds: >= 12 mm margins everywhere (unknown printable area)
X_MIN, X_MAX, Y_MIN, Y_MAX = 12.0, 198.0, 12.0, 285.0

STRIP_X_MM = 12.0
STRIP1_Y_MM, STRIP2_Y_MM = 18.0, 276.0
STRIP_W_MM = 724 * 6 * 25.4 / 600     # nominal at 600; scales with device dpi
STRIP_H_MM = 11 * 6 * 25.4 / 600

STATES7 = ("W", "C", "M", "Y", "CM", "CY", "MY")   # 002.0c winning alphabet
STATES8K = STATES7 + ("K",)
# ~3 sigma below uniform expectation for the 24x30 mm fields (see .md math)
MIN_PER_STATE = {"A3": 6000, "A4": 2900}


def mm6(v_mm: float) -> int:
    return round(v_mm / 25.4 * 600)


def pt(v_mm: float) -> float:
    return v_mm / 25.4 * 72.0


# ---------------------------------------------------------------------------
# pattern builders (pure; 1 = ink; all randomness via rng(SEED, label))
# ---------------------------------------------------------------------------

def pn_field(cell_dots: int, w_mm: float, h_mm: float, label: bytes) -> np.ndarray:
    """50% i.i.d. random cells, solid cell x cell dots, trimmed to whole cells."""
    nx, ny = mm6(w_mm) // cell_dots, mm6(h_mm) // cell_dots
    cells = rng(SEED, label).integers(0, 2, size=(ny, nx), dtype=np.uint8)
    return cells_to_dots(cells, cell_dots)


def dot_field(w_mm: float, h_mm: float, p: float, label: bytes) -> np.ndarray:
    """Seeded i.i.d. random DOTS at coverage p (high-entropy / tone steps)."""
    return (rng(SEED, label).random((mm6(h_mm), mm6(w_mm))) < p).astype(np.uint8)


def uniform_state_field(w_mm: float, h_mm: float, cell_dots: int,
                        states: tuple[str, ...], label: bytes,
                        min_per_state: int
                        ) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Per-cell state i.i.d. uniform over `states` (002.2 construction)."""
    nx, ny = mm6(w_mm) // cell_dots, mm6(h_mm) // cell_dots
    st = rng(SEED, label).integers(0, len(states), size=(ny, nx), dtype=np.uint8)
    counts = np.bincount(st.ravel(), minlength=len(states))
    assert counts.min() >= min_per_state, \
        f"{label!r}: min {int(counts.min())} cells/state < {min_per_state}"
    planes: dict[str, np.ndarray] = {}
    for p in "CMYK":
        member = np.array([int(p in s) for s in states], np.uint8)
        if member.any():
            planes[p] = cells_to_dots(member[st], cell_dots)
    return st, planes


def rll_field(w_mm: float, h_mm: float, min_ink: int, min_white: int,
              label: bytes) -> tuple[np.ndarray, dict]:
    """2-D RLL field via gen_modprobe's row-DP internals (pure functions,
    seeded HERE with exp-008's SEED; gen_e004 rectangular-wrapper idiom)."""
    h_dots, w_dots = mm6(h_mm), mm6(w_mm)
    gen = rng(SEED, label)
    minr = np.array([min_white, min_ink], dtype=np.int64)
    a = np.zeros((h_dots, w_dots), dtype=np.uint8)
    col_color = np.zeros(w_dots, dtype=np.int64)
    col_run = np.zeros(w_dots, dtype=np.int64)
    log2_total = 0.0
    for y in range(h_dots):
        if y == 0:
            forced = np.full(w_dots, -1, dtype=np.int64)
        else:
            must_cont = (col_run < minr[col_color]) | \
                        (h_dots - y < minr[1 - col_color])
            forced = np.where(must_cont, col_color, -1)
        bits, l2 = gmp._sample_row(forced, min_white, min_ink, gen)
        log2_total += l2
        a[y] = bits
        if y == 0:
            col_color = bits.astype(np.int64)
            col_run = np.ones(w_dots, dtype=np.int64)
        else:
            same = bits.astype(np.int64) == col_color
            col_run = np.where(same, col_run + 1, 1)
            col_color = bits.astype(np.int64)
    gmp.assert_run_lengths(a, min_ink, min_white)
    stats = {
        "min_ink_run_dots": min_ink,
        "min_white_run_dots": min_white,
        "sampler": "gen_modprobe row-DP (rectangular wrapper, exp-008 seed)",
        "sampler_entropy_bits_per_dot": round(log2_total / (h_dots * w_dots), 6),
        "ink_fraction": round(float(a.mean()), 6),
    }
    return a, stats


def em_pair_bits(w_each_mm: float, overlap_mm: float, h_mm: float
                 ) -> tuple[np.ndarray, np.ndarray]:
    """C/M solids on ONE canvas: C fills the left w_each, M the right w_each,
    overlapping by overlap_mm in the middle. Returns (C bits, M bits)."""
    w_e, ov, h = mm6(w_each_mm), mm6(overlap_mm), mm6(h_mm)
    w = 2 * w_e - ov
    c = np.zeros((h, w), np.uint8)
    m = np.zeros((h, w), np.uint8)
    c[:, :w_e] = 1
    m[:, w_e - ov:] = 1
    return c, m


# ---------------------------------------------------------------------------
# print-time PostScript blocks (gen_disc1 idioms; strips drawer reused
# verbatim — it is a pure function of the payload names defined here)
# ---------------------------------------------------------------------------

def ps_device_and_payload(page: int) -> list[str]:
    """P3: effective device state + dot-space helpers. P4: payload + CRC.

    Identical structure to gen_disc1 (no R0 field — nothing is requested;
    module MX/MY = max(3, floor(dpi/100)) so the 724-module strip fits at
    12 mm margins down to 300 dpi). Page 2 prepends PG=2 in the payload
    free area before LAY, so stripdec field parsing is unchanged. There are
    NO RQ fields: MSEL-1 never touches /HWResolution (DISC-1's job)."""
    pay_head = ("(PHCAL1;LAY=1;) EMIT" if page == 1
                else "(PHCAL1;PG=2;LAY=1;) EMIT")
    return [
        "% ---- P3: effective device state, dot space, element guard ----",
        "/PDGET { 3 1 roll 2 copy known { get exch pop } { pop pop } ifelse } bind def",
        "/PDE { currentpagedevice } 1 dict TRY def",
        "/HWR PDE /HWResolution [72 72] PDGET def",   # READ-only, never set
        "/HWX HWR 0 get round cvi def",
        "/HWY HWR 1 get round cvi def",
        "/PGSZ PDE /PageSize [595 842] PDGET def",
        "/PAGEHD PGSZ 1 get 72 div HWY mul round cvi def",
        "/MMX { 25.4 div HWX mul round cvi } bind def",
        "/MMY { 25.4 div HWY mul round cvi } bind def",
        "/MX HWX 100 idiv dup 3 lt { pop 3 } if def",
        "/MY HWY 100 idiv dup 3 lt { pop 3 } if def",
        "/DOTSPACE { initmatrix 72 HWX div 72 HWY div scale 0 PAGEHD translate 1 -1 scale } bind def",
        "/ELEM { mark exch gsave stopped grestore cleartomark } bind def",
        "% ---- P4: 388-byte payload + CRC-16/CCITT-FALSE ----",
        "/PAY 512 string def /PLEN 0 def",
        "/EMIT { dup length /LT exch def",
        "  PLEN LT add PAY length le",
        "  { PAY PLEN 3 -1 roll putinterval /PLEN PLEN LT add def } { pop } ifelse } bind def",
        "/EMITN { BUF cvs EMIT } bind def",
        pay_head,
        f"(J={JOBID};S={STRIP_S_FIELD};) EMIT",
        "(LL=) EMIT LL EMITN",
        "(;RD=) EMIT PDD /HWResolution [0 0] PDGET dup 0 get round cvi EMITN",
        "  (x) EMIT 1 get round cvi EMITN",
        "(;RE=) EMIT HWX EMITN (x) EMIT HWY EMITN",
        "(;PS=) EMIT PGSZ 0 get round cvi EMITN (x) EMIT PGSZ 1 get round cvi EMITN",
        "(;IB=) EMIT PDE /ImagingBBox null PDGET",
        "  dup null eq { pop (null) EMIT } { { EMITN ( ) EMIT } forall } ifelse",
        "(;PR=) EMIT { /product where { /product get } { statusdict /product get } ifelse",
        "  dup length 40 gt { 0 40 getinterval } if } (unknown) TRY EMIT",
        "(;V=) EMIT { /version where { /version get } { statusdict /version get } ifelse",
        "  dup type /stringtype ne { BUF cvs } if } (unknown) TRY EMIT",
        "(;RV=) EMIT { /revision where { /revision get } { 0 } ifelse } 0 TRY EMITN",
        "(;SN=) EMIT { statusdict /serialnumber get exec } -1 TRY EMITN",
        "(;) EMIT",
        "PLEN 388 lt { PAY PLEN 0 put /PLEN PLEN 1 add def } if",
        "PLEN 1 387 { PAY exch 16#A5 put } for",
        "/CRC 16#FFFF def",
        "/CRCB { 8 bitshift CRC xor 16#FFFF and /CRC exch def",
        "  8 { CRC 16#8000 and 0 ne",
        "    { CRC 1 bitshift 16#1021 xor } { CRC 1 bitshift } ifelse",
        "    16#FFFF and /CRC exch def } repeat } bind def",
        "0 1 387 { PAY exch get CRCB } for",
        "PAY 388 CRC -8 bitshift 16#FF and put",
        "PAY 389 CRC 16#FF and put",
        "/PZ 388 def",
        "0 1 387 { dup PAY exch get 0 eq { /PZ exch def exit } { pop } ifelse } for",
    ]


def sentinel_lines(page: int) -> list[str]:
    text = f"END {JOBID} exp008 msel1" + (" p2" if page == 2 else "")
    return [
        "% ---- END sentinel: LAST element in the stream ----",
        "mark { initmatrix 0 0 0 1 setcmykcolor",
        f"  {pt(20.0):.2f} {A4_PT[1] - pt(283.1):.2f} {pt(2.5):.2f} {pt(2.5):.2f} rectfill",
        "  /Helvetica findfont 6 scalefont setfont",
        f"  {pt(24.5):.2f} {A4_PT[1] - pt(283.0):.2f} moveto"
        f" ({text}) show }} stopped cleartomark",
    ]


# ---------------------------------------------------------------------------
# page assembly (single 600-dot grid; per-page occupancy, emit lists, labels)
# ---------------------------------------------------------------------------

class MselPage:
    def __init__(self) -> None:
        self.doc = gen_disc1.Disc1Doc(
            hw_dpi=BASE_DPI,
            title=f"paper-store exp008 MSEL-1 LAY=1 J={JOBID}",
            prolog_lines=gen_disc1.ps_prolog())
        self.page = 1
        self.rects: dict[int, list[tuple[int, int, int, int, int, str]]] = \
            {1: [], 2: []}
        self.patches: list[dict] = []
        self.infra: list[dict] = []
        self.labels: list[dict] = []
        self._mask_emits: dict[int, list] = {1: [], 2: []}
        self._cmyk_emits: dict[int, list] = {1: [], 2: []}
        self._label_args: dict[int, list] = {1: [], 2: []}
        self._gt_files: set[str] = set()

    # -- occupancy -----------------------------------------------------------
    def _conflict(self, x0: int, y0: int, x1: int, y1: int, clr: int) -> str | None:
        for a0, b0, a1, b1, c2, nm in self.rects[self.page]:
            g = max(clr, c2)
            if x0 < a1 + g and a0 < x1 + g and y0 < b1 + g and b0 < y1 + g:
                return nm
        return None

    def _occupy(self, name: str, x: int, y: int, w: int, h: int,
                clr_mm: float) -> None:
        if not (mm6(X_MIN) <= x and x + w <= mm6(X_MAX)
                and mm6(Y_MIN) <= y and y + h <= mm6(Y_MAX)):
            raise AssertionError(f"p{self.page}/{name}: rect ({x},{y},{w},{h}) "
                                 "outside content bounds")
        clr = mm6(clr_mm)
        hit = self._conflict(x, y, x + w, y + h, clr)
        if hit is not None:
            raise AssertionError(f"p{self.page}/{name} overlaps {hit} "
                                 f"(clearance {clr_mm} mm)")
        self.rects[self.page].append((x, y, x + w, y + h, clr, name))

    def _save_gt(self, name: str, bits: np.ndarray) -> str:
        GT.mkdir(parents=True, exist_ok=True)
        rel = f"msel1_gt/{name.replace('/', '__')}.npy"
        if rel in self._gt_files:
            raise AssertionError(f"ground-truth filename collision: {rel}")
        self._gt_files.add(rel)
        np.save(OUT / rel, bits.astype(np.uint8))
        return rel

    # -- content ---------------------------------------------------------------
    def patch(self, name: str, bits: np.ndarray, x_mm: float, y_mm: float,
              plane: str, kind: str, params: dict | None = None,
              save_gt: bool = False, clearance_mm: float = 1.5,
              overprint: bool = False, opm: bool = False) -> None:
        x, y = mm6(x_mm), mm6(y_mm)
        h, w = bits.shape
        self._occupy(name, x, y, w, h, clearance_mm)
        self._mask_emits[self.page].append(
            (w * h, name, bits, plane, x, y, overprint, opm))
        gt = self._save_gt(name, bits) if save_gt else None
        self.patches.append({"name": name, "kind": kind, "planes": [plane],
                             "page": self.page, "dpi": 600,
                             "x_dots": x, "y_dots": y,
                             "w_dots": int(w), "h_dots": int(h),
                             "params": params or {}, "gt": gt})

    def patch_cmyk(self, name: str, planes: dict[str, np.ndarray], x_mm: float,
                   y_mm: float, kind: str, params: dict | None = None,
                   save_gt: bool = True, clearance_mm: float = 1.5) -> None:
        """Composite via put_cmyk_bitmap; streams after all masks."""
        x, y = mm6(x_mm), mm6(y_mm)
        (h, w), = {a.shape for a in planes.values()}
        self._occupy(name, x, y, w, h, clearance_mm)
        self._cmyk_emits[self.page].append((name, dict(planes), x, y))
        base = {"emission": "cmyk_image"}
        for p, bits in planes.items():
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind,
                                 "planes": [p], "page": self.page, "dpi": 600,
                                 "x_dots": x, "y_dots": y,
                                 "w_dots": int(w), "h_dots": int(h),
                                 "params": {**base, **(params or {})},
                                 "gt": gt, "composite_of": name})

    def mask_pair(self, name: str, bits_a: np.ndarray, plane_a: str,
                  bits_b: np.ndarray, plane_b: str, x_mm: float, y_mm: float,
                  kind: str, params: dict | None = None,
                  save_gt: bool = True, clearance_mm: float = 1.5,
                  overprint: bool = False, opm: bool = False) -> None:
        """Two same-canvas imagemasks whose SET bits deliberately overlap
        (002.1 emission probe; the union rect is occupied once)."""
        x, y = mm6(x_mm), mm6(y_mm)
        (h, w) = bits_a.shape
        assert bits_b.shape == (h, w)
        self._occupy(name, x, y, w, h, clearance_mm)
        base = {"emission": "imagemask_pair"
                           + ("_overprint" if overprint else "")
                           + ("_opm" if opm else ""),
                "paint_order": [plane_a, plane_b],
                "deliberate_overlap": True, **(params or {})}
        for p, bits in ((plane_a, bits_a), (plane_b, bits_b)):
            self._mask_emits[self.page].append(
                (w * h, f"{name}_{p}", bits, p, x, y, overprint, opm))
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind,
                                 "planes": [p], "page": self.page, "dpi": 600,
                                 "x_dots": x, "y_dots": y,
                                 "w_dots": int(w), "h_dots": int(h),
                                 "params": dict(base), "gt": gt,
                                 "composite_of": name})

    def rect_entry(self, name: str, x_mm: float, y_mm: float, w_mm: float,
                   h_mm: float, kind: str, params: dict | None = None,
                   clearance_mm: float = 0.5, as_patch: bool = False) -> None:
        """Reserve + record a print-time (or deliberately blank) rect."""
        x, y, w, h = mm6(x_mm), mm6(y_mm), mm6(w_mm), mm6(h_mm)
        self._occupy(name, x, y, w, h, clearance_mm)
        e = {"name": name, "kind": kind, "planes": [], "page": self.page,
             "dpi": 600, "x_dots": x, "y_dots": y, "w_dots": w, "h_dots": h,
             "params": params or {}, "gt": None}
        (self.patches if as_patch else self.infra).append(e)

    def label(self, text: str, x_mm: float, y_baseline_mm: float,
              size_pt: float = 4.0) -> None:
        x, yb = mm6(x_mm), mm6(y_baseline_mm)
        w = round(len(text) * 0.58 * size_pt / 72 * 600)
        asc = round(0.78 * size_pt / 72 * 600)
        desc = round(0.24 * size_pt / 72 * 600)
        self.labels.append({"text": text, "page": self.page, "x_dots": x,
                            "y_dots": yb - asc,
                            "w_dots": w, "h_dots": asc + desc})
        self._label_args[self.page].append((text, x, yb, size_pt))

    def assert_labels_clear(self) -> None:
        for lb in self.labels:
            lx0, ly0 = lb["x_dots"], lb["y_dots"]
            lx1, ly1 = lx0 + lb["w_dots"], ly0 + lb["h_dots"]
            for x0, y0, x1, y1, _, nm in self.rects[lb["page"]]:
                if lx0 < x1 and x0 < lx1 and ly0 < y1 and y0 < ly1:
                    raise AssertionError(f"label {lb['text']!r} intersects {nm}")

    def place_plus_lattice(self) -> int:
        """21x21-dot plus marks (gen_calpage builder, byte-identical) on the
        25.4 mm grid of the CURRENT page, whitespace only."""
        pm = gen_calpage.plus_mark()
        placed = 0
        for j in range(1, 12):
            for i in range(1, 8):
                cx, cy = 25.4 * i, 25.4 * j
                x, y = mm6(cx) - 10, mm6(cy) - 10
                if not (mm6(X_MIN) <= x and x + 21 <= mm6(X_MAX)
                        and mm6(Y_MIN) <= y and y + 21 <= mm6(Y_MAX)):
                    continue
                if self._conflict(x, y, x + 21, y + 21, mm6(1.5)) is not None:
                    continue
                pad = mm6(1.0)
                if any(lb["page"] == self.page
                       and lb["x_dots"] < x + 21 + pad
                       and x < lb["x_dots"] + lb["w_dots"] + pad
                       and lb["y_dots"] < y + 21 + pad
                       and y < lb["y_dots"] + lb["h_dots"] + pad
                       for lb in self.labels):
                    continue
                name = f"{'p2/' if self.page == 2 else ''}plus_{i}_{j}"
                self.rects[self.page].append((x, y, x + 21, y + 21,
                                              mm6(1.5), name))
                self._mask_emits[self.page].append(
                    (21 * 21, name, pm, "K", x, y, False, False))
                self.patches.append({"name": name, "kind": "plus_mark",
                                     "planes": ["K"], "page": self.page,
                                     "dpi": 600, "x_dots": x, "y_dots": y,
                                     "w_dots": 21, "h_dots": 21,
                                     "params": {"grid_node_inch": [i, j],
                                                "arm_dots": 3}, "gt": None})
                placed += 1
        return placed

    # -- emission: device/payload/strips first, labels, masks small->large,
    #    cmyk composites, dict close, END sentinel last-in-page ---------------
    def emit(self) -> None:
        d = self.doc
        for page in (1, 2):
            d.begin_page()
            if page == 2:
                d.put_raw(["PHC begin"])   # page 1 opened it in the prolog
            d.put_raw(ps_device_and_payload(page))
            d.put_raw(gen_disc1.ps_strips(STRIP1_Y_MM, STRIP2_Y_MM, STRIP_X_MM))
            for text, x, yb, size in self._label_args[page]:
                d.put_label(text, x, yb, CMYK["K"], size_pt=size)
            d.put_raw(["% ==== single-plane imagemask content"
                       " (small to large) ===="])
            for _, name, bits, plane, x, y, ovp, opm in sorted(
                    self._mask_emits[page], key=lambda t: (t[0], t[1])):
                d.put_bitmap(bits, x, y, CMYK[plane], overprint=ovp, opm=opm)
            d.put_raw(["% ==== put_cmyk_bitmap composites ===="])
            for name, planes, x, y in self._cmyk_emits[page]:
                d.put_raw([f"% ---- {name} cmyk-image ----"])
                d.put_cmyk_bitmap(planes, x, y)
            d.put_raw(["end"])   # close the PHC dict
            d.put_raw(sentinel_lines(page))
            d.end_page()


# ---------------------------------------------------------------------------
# layout — page 1 (decision-critical, color)
# ---------------------------------------------------------------------------

K_CELLS_FULL = (2, 3, 4, 5, 6)   # positions with the full ladder
K_CELLS_SHORT = (2, 3, 4)        # third/fifth positions
FIELD_MM = 20.0
RLL_I, RLL_W = 2, 3              # i2w3 (003.0/B2 construction)


def build_header(pg: MselPage, page: int) -> None:
    tag = " PAGE 2 (K-only replica)" if page == 2 else ""
    pg.label(f"paper-store exp008 MSEL-1 mode-selection sheet{tag} LAY=1 "
             f"J={JOBID}", 21.0, 14.2, size_pt=7.0)
    pg.label(f"S={SEED.decode()}  regen: gen_msel1.py | PORTABLE LL2: no "
             "HWResolution anywhere - device default render path", 21.0, 22.9,
             size_pt=5.0)
    pg.label("print ONE job as raw as possible (lp -o raw / raw queue, else "
             "any PS driver 100% no-fit); HAND-NOTE model+queue/driver in pen",
             21.0, 25.0, size_pt=5.0)
    pg.label("scan 1200 dpi GREY and COLOR on a KNOWN scanner, descreen/"
             "sharpen/auto-contrast OFF, flat, include all edges; "
             "analyze_msel1.py", 21.0, 267.3, size_pt=5.0)
    pg.label("strips: 724x11 modules, module=max(3,floor(dpi/100)) dots; "
             "5 rows x 78B (8b MSB + even parity) + xor byte; 388B pad 0xA5 + "
             "CRC16-CCITT-F BE; decode: exp002 stripdec.py", 21.0, 275.4,
             size_pt=4.0)


def build_registration(pg: MselPage, prefix: str = "") -> None:
    for tag, n_sat, inward, cx, cy in (("tl", 1, (1, 1), 14.7, 14.7),
                                       ("tr", 2, (1, -1), 195.3, 14.7),
                                       ("br", 3, (-1, -1), 195.3, 282.3),
                                       ("bl", 4, (-1, 1), 14.7, 282.3)):
        pg.patch(f"{prefix}corner_{tag}", gen_calpage.corner_mark(n_sat, inward),
                 cx - 61 * 25.4 / 600, cy - 61 * 25.4 / 600, "K", "corner_mark",
                 params={"satellites": n_sat, "inward": list(inward),
                         "arm_dots": 60, "width_dots": 3,
                         "cx_dots": mm6(cx), "cy_dots": mm6(cy)},
                 clearance_mm=0.4)


def build_k_row(pg: MselPage, pos: str, y0: float, cells: tuple[int, ...],
                with_rll: bool = True, x0: float = 13.0,
                pitch: float = 22.0) -> None:
    """One K-portfolio position: PN fields (given cells) + one RLL field."""
    x = x0
    for c in cells:
        bits = pn_field(c, FIELD_MM, FIELD_MM, f"{pos}/k_c{c}".encode())
        pg.patch(f"{pos}/k_c{c}", bits, x, y0, "K", "pn_field",
                 params={"cell_dots": c, "p": 0.5, "block": "portfolio",
                         "position": pos}, save_gt=True, clearance_mm=0.7)
        pg.label(f"c{c}", x, y0 + FIELD_MM + 1.9)
        x += pitch
    if with_rll:
        bits, stats = rll_field(FIELD_MM, FIELD_MM, RLL_I, RLL_W,
                                f"{pos}/k_rll".encode())
        pg.patch(f"{pos}/k_rll", bits, x, y0, "K", "constrained_field",
                 params={**stats, "block": "portfolio", "position": pos},
                 save_gt=True, clearance_mm=0.7)
        pg.label("rll", x, y0 + FIELD_MM + 1.9)


def build_a_row(pg: MselPage, pos: str, y0: float, x0: float = 13.0) -> None:
    """One CMY-portfolio position: A3 7-state c3 + A4 {7+K} c4 composites."""
    st3, pl3 = uniform_state_field(24.0, 30.0, 3, STATES7,
                                   f"{pos}/a3_c3".encode(),
                                   MIN_PER_STATE["A3"])
    rel3 = pg._save_gt(f"{pos}/a3_c3_states", st3)
    pg.patch_cmyk(f"{pos}/a3_c3", pl3, x0, y0, "state_field",
                  params={"cell_dots": 3, "n_states": 7,
                          "state_names": list(STATES7), "states_gt": rel3,
                          "block": "portfolio", "position": pos},
                  clearance_mm=0.7)
    pg.label("A3 7st c3", x0, y0 + 31.9)
    st4, pl4 = uniform_state_field(24.0, 30.0, 4, STATES8K,
                                   f"{pos}/a4_c4".encode(),
                                   MIN_PER_STATE["A4"])
    rel4 = pg._save_gt(f"{pos}/a4_c4_states", st4)
    pg.patch_cmyk(f"{pos}/a4_c4", pl4, x0 + 26.0, y0, "state_field",
                  params={"cell_dots": 4, "n_states": 8,
                          "state_names": list(STATES8K), "states_gt": rel4,
                          "block": "portfolio", "position": pos},
                  clearance_mm=0.7)
    pg.label("A4 7+K c4", x0 + 26.0, y0 + 31.9)


def build_iso_minis(pg: MselPage, pos: str, y0: float, x0: float) -> None:
    for k, p in enumerate("CMY"):
        x = x0 + 13.5 * k
        bits = pn_field(3, 12.0, 12.0, f"{pos}/iso_{p.lower()}_c3".encode())
        pg.patch(f"{pos}/iso_{p}_c3", bits, x, y0, p, "pn_field",
                 params={"cell_dots": 3, "p": 0.5, "block": "iso_plane",
                         "position": pos}, save_gt=True, clearance_mm=0.7)
        pg.label(f"{p}c3", x, y0 + 13.9)


def build_emission_probes(pg: MselPage, y0: float) -> None:
    """P0 put_cmyk vs P3 masks+setoverprint+OPM-1: overlapping C+M solids
    (002.1 paths P0/P3 — the knockout/preserve + screen discriminator)."""
    cb, mb = em_pair_bits(12.0, 6.0, 8.0)
    pg.patch_cmyk("em/p0_cm", {"C": cb, "M": mb}, 65.0, y0, "emission_probe",
                  params={"path": "P0_cmyk_image", "overlap_mm": 6.0,
                          "zones_mm": {"c_only": 6.0, "overlap": 6.0,
                                       "m_only": 6.0}}, clearance_mm=1.0)
    pg.label("P0 cmyk C+M", 65.0, y0 + 9.9)
    pg.mask_pair("em/p3_cm", cb, "C", mb, "M", 88.0, y0, "emission_probe",
                 params={"path": "P3_masks_overprint_opm", "overlap_mm": 6.0,
                         "zones_mm": {"c_only": 6.0, "overlap": 6.0,
                                      "m_only": 6.0}},
                 clearance_mm=1.0, overprint=True, opm=True)
    pg.label("P3 masks+OPM C+M", 88.0, y0 + 9.9)


def build_crosstalk_row(pg: MselPage, y0: float, x0: float = 110.0) -> None:
    solid = np.ones((mm6(8.0), mm6(8.0)), np.uint8)
    for k, p in enumerate("CMYK"):
        pg.patch(f"xr/clean_{p}", solid, x0 + 9.5 * k, y0, p, "ref_solid",
                 params={"emission": "imagemask_single", "block": "crosstalk"},
                 clearance_mm=1.0)
    pg.rect_entry("xr/paper", x0 + 38.0, y0, 8.0, 8.0, "paper_gap",
                  params={"coverage": 0.0, "block": "crosstalk"},
                  clearance_mm=1.0, as_patch=True)
    for k, combo in enumerate(("CM", "CY", "MY")):
        pg.patch_cmyk(f"xr/cmyk_{combo}", {p: solid for p in combo},
                      x0 + 9.5 * k, y0 + 10.0, "ref_solid_cmyk",
                      params={"block": "crosstalk"}, save_gt=False,
                      clearance_mm=1.0)
    pg.label("xr: C M Y K paper / CM CY MY", x0, y0 + 21.9)


def build_morphology(pg: MselPage, y0: float, prefix: str = "") -> None:
    s6 = mm6(6.0)
    items: list[tuple[str, np.ndarray, str, dict, str]] = []
    for o, horiz in (("h", True), ("v", False)):
        for w in (1, 2, 3, 4):
            items.append((f"lw{w}{o}", gen_disc1.lines_w(w, s6, horiz),
                          "line_width",
                          {"width_dots": w, "pitch_dots": 4 * w,
                           "orientation": f"{o}_lines"}, f"{w}{o.upper()}"))
    for n in (1, 2):
        items.append((f"chk{n}", gen_calpage.checker(n, s6), "checker",
                      {"n_dots": n}, f"k{n}"))
    for n in (1, 2, 3, 4):
        items.append((f"hole{n}", gen_calpage.squares(n, s6, True),
                      "white_holes", {"n_dots": n, "spacing_dots": 3 * n},
                      f"o{n}"))
    for o, horiz in (("h", True), ("v", False)):
        items.append((f"g1{o}", gen_disc1.grating(1, s6, horiz), "grating",
                      {"pitch_dots": 1, "orientation": f"{o}_lines"},
                      f"n{o.upper()}"))
    items.append(("dots8", gen_disc1.iso_dots(s6), "iso_dot_grid",
                  {"pitch_dots": 8}, "d8"))
    for k, (nm, bits, kind, params, short) in enumerate(items):
        x = 13.0 + 7.5 * k
        save = nm.startswith("chk")   # pixel-exact preflight anchors
        pg.patch(f"{prefix}morph/{nm}", bits, x, y0, "K", kind, params=params,
                 save_gt=save, clearance_mm=0.6)
        pg.label(short, x, y0 + 8.4)


def build_tone_wedge(pg: MselPage, y0: float, x0: float = 141.0) -> None:
    for k, pc in enumerate((10, 30, 50, 70, 90)):
        x = x0 + 7.5 * k
        pg.patch(f"tone/p{pc}", dot_field(6.0, 6.0, pc / 100, b"tone/p%d" % pc),
                 x, y0, "K", "tone_step",
                 params={"coverage": pc / 100, "dither": "seeded_random_dots"},
                 save_gt=True, clearance_mm=0.7)
        pg.label(str(pc), x, y0 + 8.4)
    pg.patch("tone/solid", np.ones((mm6(6.0), mm6(6.0)), np.uint8),
             x0 + 37.5, y0, "K", "tone_step",
             params={"coverage": 1.0, "dither": "solid"}, clearance_mm=0.7)
    pg.label("100", x0 + 37.5, y0 + 8.4)
    pg.rect_entry("tone/paper", x0 + 45.0, y0, 6.0, 6.0, "paper_gap",
                  params={"coverage": 0.0}, clearance_mm=0.7, as_patch=True)
    pg.label("pap", x0 + 45.0, y0 + 8.4)


def build_adequacy(pg: MselPage, y0: float, x0: float = 103.0) -> None:
    """Scanner-adequacy block (pre-registered criteria in the .md)."""
    bits = pn_field(3, 14.0, 14.0, b"adq/k_c3")
    pg.patch("adq/k_c3", bits, x0, y0, "K", "pn_field",
             params={"cell_dots": 3, "p": 0.5, "block": "adequacy"},
             save_gt=True, clearance_mm=0.7)
    pg.label("adq c3", x0, y0 + 15.9)
    bits = pn_field(2, 14.0, 14.0, b"adq/k_c2")
    pg.patch("adq/k_c2", bits, x0 + 16.0, y0, "K", "pn_field",
             params={"cell_dots": 2, "p": 0.5, "block": "adequacy"},
             save_gt=True, clearance_mm=0.7)
    pg.label("adq c2", x0 + 16.0, y0 + 15.9)
    s8 = mm6(8.0)
    for k, (o, horiz) in enumerate((("h", True), ("v", False))):
        pg.patch(f"adq/g2{o}", gen_disc1.grating(2, s8, horiz), x0 + 32.0 + 10.0 * k,
                 y0, "K", "grating",
                 params={"pitch_dots": 2, "orientation": f"{o}_lines",
                         "block": "adequacy"}, clearance_mm=0.7)
        pg.label(f"2{o.upper()}", x0 + 32.0 + 10.0 * k, y0 + 9.9)
    pg.patch("adq/entropy", dot_field(10.0, 10.0, 0.5, b"adq/entropy"),
             x0 + 52.0, y0, "K", "entropy_field",
             params={"p": 0.5, "dither": "seeded_random_dots",
                     "block": "adequacy",
                     "purpose": "JPEG/blockiness canary (007.2)"},
             save_gt=True, clearance_mm=0.7)
    pg.label("ent", x0 + 52.0, y0 + 11.9)


def build_page1(pg: MselPage) -> None:
    build_header(pg, 1)
    for n, ys in (("1", STRIP1_Y_MM), ("2", STRIP2_Y_MM)):
        pg.rect_entry(f"machine_strip_{n}", STRIP_X_MM, ys, STRIP_W_MM,
                      STRIP_H_MM, "machine_strip",
                      params={"modules": [724, 11], "rows": 5,
                              "bytes_per_row": 78, "payload_bytes": 390,
                              "module_dots_formula":
                                  "max(3, floor(hw_dpi/100)) per axis "
                                  "(exp007 formula; stripdec self-scales)",
                              "crc": "CRC-16/CCITT-FALSE big-endian",
                              "rect_is_nominal_600dpi": True},
                      clearance_mm=0.4)
    build_registration(pg)
    # -- row 1: K portfolio P1 + labels ------------------------------------
    build_k_row(pg, "pf1", 27.0, K_CELLS_FULL)
    # -- row 2: CMY portfolio P1 + minis + probes + crosstalk + quiet zone --
    build_a_row(pg, "pf1", 52.0)
    build_iso_minis(pg, "pf1", 52.0, 65.0)
    build_emission_probes(pg, 68.0)
    build_crosstalk_row(pg, 52.0)
    pg.rect_entry("quiet_zone", 170.0, 52.0, 26.0, 26.0, "quiet_zone",
                  params={"purpose": "MIC hunt on the COLOR page — pair with "
                                     "page 2's K-only quiet zone (007.8-C1 "
                                     "color-content gating discrimination)"},
                  clearance_mm=1.0)
    pg.label("quiet", 170.0, 80.4)
    # -- row 3: morphology minis + tone wedge -------------------------------
    build_morphology(pg, 86.0)
    build_tone_wedge(pg, 86.0)
    # -- row 4: K portfolio P2 ----------------------------------------------
    build_k_row(pg, "pf2", 98.0, K_CELLS_FULL)
    # -- row 5: CMY portfolio P2 + iso minis + big RLL -----------------------
    build_a_row(pg, "pf2", 123.0)
    build_iso_minis(pg, "pf2", 123.0, 67.0)
    bits, stats = rll_field(30.0, 30.0, RLL_I, RLL_W, b"big/k_rll")
    pg.patch("big/k_rll", bits, 111.0, 123.0, "K", "constrained_field",
             params={**stats, "block": "portfolio", "position": "big"},
             save_gt=True, clearance_mm=0.7)
    pg.label("rll 30x30", 111.0, 154.9)
    # -- row 6: K portfolio P3 + adequacy block ------------------------------
    build_k_row(pg, "pf3", 159.0, K_CELLS_SHORT)
    build_adequacy(pg, 159.0)
    # -- row 7: CMY portfolio P3 ---------------------------------------------
    build_a_row(pg, "pf3", 185.0)
    pg.rect_entry("end_sentinel", 20.0, 280.4, 42.0, 3.0, "end_sentinel",
                  params={"text": f"END {JOBID} exp008 msel1"})
    n_plus = pg.place_plus_lattice()
    assert n_plus >= 12, f"only {n_plus} plus marks on page 1"


def build_page2(pg: MselPage) -> None:
    pg.page = 2
    build_header(pg, 2)
    for n, ys in (("1", STRIP1_Y_MM), ("2", STRIP2_Y_MM)):
        pg.rect_entry(f"p2/machine_strip_{n}", STRIP_X_MM, ys, STRIP_W_MM,
                      STRIP_H_MM, "machine_strip",
                      params={"modules": [724, 11], "rows": 5,
                              "bytes_per_row": 78, "payload_bytes": 390,
                              "payload_preamble": "PG=2 (free area before "
                                                  "LAY; stripdec unchanged)",
                              "crc": "CRC-16/CCITT-FALSE big-endian",
                              "rect_is_nominal_600dpi": True},
                      clearance_mm=0.4)
    build_registration(pg, prefix="p2/")
    # -- row 1: K portfolio P4 ------------------------------------------------
    build_k_row(pg, "p2pf1", 27.0, K_CELLS_FULL)
    # -- row 2: big anchors + K-only quiet zone -------------------------------
    for nm, cell, x in (("p2big/k_c2", 2, 13.0), ("p2big/k_c3", 3, 57.0)):
        bits = pn_field(cell, 40.0, 40.0, nm.encode())
        pg.patch(nm, bits, x, 52.0, "K", "pn_field",
                 params={"cell_dots": cell, "p": 0.5, "block": "portfolio",
                         "position": "p2big"}, save_gt=True, clearance_mm=0.7)
        pg.label(f"c{cell} 40x40", x, 93.9)
    # 38 mm = 898 dots: the row-DP sampler's exact-count float path caps
    # rows at 900 dots (gen_modprobe) — 40 mm would overflow it.
    bits, stats = rll_field(38.0, 38.0, RLL_I, RLL_W, b"p2big/k_rll")
    pg.patch("p2big/k_rll", bits, 101.0, 52.0, "K", "constrained_field",
             params={**stats, "block": "portfolio", "position": "p2big"},
             save_gt=True, clearance_mm=0.7)
    pg.label("rll 38x38", 101.0, 93.9)
    pg.rect_entry("p2/quiet_zone", 147.0, 52.0, 26.0, 26.0, "quiet_zone",
                  params={"purpose": "K-ONLY page quiet zone = MIC "
                                     "color-content-gating control"},
                  clearance_mm=1.0)
    pg.label("quiet (K-only page)", 147.0, 80.4)
    # -- row 3: morphology replica --------------------------------------------
    build_morphology(pg, 99.0, prefix="p2/")
    # -- row 4: K portfolio P5 ------------------------------------------------
    build_k_row(pg, "p2pf2", 112.0, K_CELLS_SHORT)
    pg.rect_entry("p2/end_sentinel", 20.0, 280.4, 42.0, 3.0, "end_sentinel",
                  params={"text": f"END {JOBID} exp008 msel1 p2"})
    n_plus = pg.place_plus_lattice()
    assert n_plus >= 12, f"only {n_plus} plus marks on page 2"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GT.mkdir(parents=True, exist_ok=True)
    pg = MselPage()
    build_page1(pg)
    build_page2(pg)
    pg.assert_labels_clear()
    pg.emit()
    ps = pg.doc.render()

    # portability + stream-order invariants (belt and braces; tests re-check)
    assert ps.isascii(), "%%DocumentData: Clean7Bit violated (non-ASCII byte)"
    assert "%%Pages: 2" in ps and ps.count("%%Page:") == 2, "must be TWO pages"
    assert "%%LanguageLevel: 2" in ps
    lines = ps.splitlines()
    spd = [ln for ln in lines
           if "setpagedevice" in ln and not ln.lstrip().startswith("%")]
    assert spd == ["{ << /PageSize [595 842] >> setpagedevice }"
                   " stopped { } if"], spd
    # NO resolution operation anywhere: the strip PS only READS HWResolution
    # from currentpagedevice/PDD — it never appears next to setpagedevice.
    assert "HWResolution" not in "".join(spd)
    for page in (1, 2):
        lo = ps.index(f"%%Page: {page} {page}")
        hi = ps.index("%%Page: 2 2") if page == 1 else len(ps)
        seg = ps[lo:hi]
        assert "setpagedevice" not in seg, f"page {page} must be request-free"
        i_cmyk = seg.index("% ==== put_cmyk_bitmap composites")
        assert seg.rindex("imagemask") < i_cmyk, \
            f"p{page} masks must stream before cmyk"
        i_s = seg.index("% ---- END sentinel")
        assert i_s > i_cmyk and "imagemask" not in seg[i_s:] \
            and ">> image" not in seg[i_s:], f"p{page} sentinel must be last"
    assert f"(END {JOBID} exp008 msel1 p2) show" in ps[ps.rindex("% ---- END"):]
    assert len(ps) <= PS_BUDGET_BYTES, f"ps {len(ps) / 1e6:.1f} MB > budget"

    (OUT / "msel1.ps").write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()
    n_plus = sum(1 for p in pg.patches if p["kind"] == "plus_mark")
    manifest = {
        "experiment": "008-mode-select",
        "artifact": "msel1",
        "run": "008.0",
        "layout_version": LAYOUT_VERSION,
        "seed": SEED.decode(),
        "jobid": JOBID,
        "pages": 2,
        "hw_dpi": BASE_DPI,
        "hw_dpi_note": "layout/manifest grid only — the job requests NO "
                       "/HWResolution (device default render path rules; "
                       "mode selection is measured there by design)",
        "ps_file": "msel1.ps",
        "ps_sha256": sha,
        "ps_bytes": len(ps),
        "print_command": "portable: lp -d <queue> -o raw msel1.ps preferred; "
                         "nc <host> 9100 < msel1.ps; else any PS driver at "
                         "100%/no-fit; hand-note model+queue+driver in pen",
        "payload_prefix": f"PHCAL1;LAY=1;J={JOBID};S={STRIP_S_FIELD};",
        "payload_prefix_p2": f"PHCAL1;PG=2;LAY=1;J={JOBID};S={STRIP_S_FIELD};",
        "strip_s_field": STRIP_S_FIELD,
        "payload_fields_printtime": ["LL", "RD", "RE", "PS", "IB", "PR", "V",
                                     "RV", "SN"],
        "portability": {"language_level": 2,
                        "hwresolution_requests": 0,
                        "pagesize_request_pt": [595, 842],
                        "pagesize_guarded": True, "margins_mm": 12.0,
                        "strip_module_formula": "max(3, floor(dpi/100))"},
        "content_bounds_mm": [X_MIN, Y_MIN, X_MAX, Y_MAX],
        "portfolio": {
            "k_cells": list(K_CELLS_FULL),
            "k_positions": ["pf1", "pf2", "pf3", "p2pf1", "p2pf2",
                            "p2big (c2,c3)"],
            "rll": f"i{RLL_I}w{RLL_W} at pf1..p2pf2 + big 30x30 + p2big 40x40",
            "cmy": "A3 7-state c3 + A4 {7+K} c4 at pf1/pf2/pf3 (page 1 only "
                   "— page 2 is deliberately K-only: MIC gating control)",
            "decision_rules": "PRE-REGISTERED in experiments/008-mode-select"
                              ".md (R1-R7); analyze_msel1.py implements them",
        },
        "n_plus_marks": n_plus,
        "patches": pg.patches,
        "infrastructure": pg.infra,
        "labels": pg.labels,
    }
    (OUT / "msel1_manifest.json").write_text(json.dumps(manifest, indent=1))
    n1 = sum(1 for p in pg.patches if p["page"] == 1)
    n2 = sum(1 for p in pg.patches if p["page"] == 2)
    print(f"wrote build/msel1.ps ({len(ps) / 1e6:.2f} MB, {len(pg.patches)} "
          f"patches: {n1} p1 + {n2} p2, {n_plus} plus marks)")
    print(f"sha256 {sha}")


if __name__ == "__main__":
    main()
