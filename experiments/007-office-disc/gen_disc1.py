#!/usr/bin/env python
"""Experiment 007 — DISC-1: portable discovery job for an UNKNOWN office
printer (unknown native dpi, unknown driver path, possibly mono). TWO pages.

PAGE 1 (passive, portable): unlike every home-printer job (M281:
/HWResolution [600 600], raw 9100), it requests NOTHING resolution-shaped:
LanguageLevel 2 only, NO /HWResolution operation before its showpage (the
device default rules — the strips REPORT it), PageSize [595 842] inside a
stopped guard only, >= 12 mm margins on all sides (unknown printable area;
the margin probes deliberately march past 12 mm to FIND the boundary).

PAGE 2 (active resolution probe, blast-radius-isolated by the page boundary:
page 1 is complete and shipped before any resolution operation executes):
after page 1's showpage, a guarded resolution ENUMERATION — for each r in
300/600/1200/2400, request /HWResolution [r r] inside a stopped guard and
read back the granted value (recorded as RQ300..RQ2400 in page 2's strip
payload preamble) — then the definitive guarded [1200 1200] request that
page 2's content prints under. Three outcomes, all informative: refused
(RE = RD default), granted-clean, granted-but-corrupt (vs the page-1
no-request control). Page 2 carries its own strip pair (payload preamble
adds PG=2 + RQ* BEFORE the first stripdec-known key, so field parsing is
unchanged), corner marks, 1200/2400 gratings + dot/line-pair probes, a
1200 line-width ladder, PN c2/c3/c4 @1200, and a fresh-label 600-addressed
c3 PN control (cross-page comparator).

PAGE 1 content, top to bottom: header labels; TWO exp002-format machine strips
(print-time device self-report, stripdec.py-compatible: magic PHCAL1, 390-byte
payload, CRC-16/CCITT-FALSE); chiral corner marks + plus-mark lattice;
resolution ladder at 300/600/1200 addressing (gratings, isolated dots, line
pairs — put_bitmap(dpi=...) places every grid in device-independent points);
morphology ladders at 600 + 1200; PN cell fields c1..c6 @600 and c2/c3 @1200;
seeded random-dot tone wedge (no ordered dither — avoids beating against
unknown device screens); emission canaries (C/M/Y/K single-plane masks, one
CMY c3 put_cmyk_bitmap composite, one C+M overlapping-mask pair — on a mono
engine these degrade gracefully, which is itself the datum); r(y)/r(x)
3-on/3-off grating strips; margin probes to 4 mm; END sentinel last.

Error containment (exp002 idiom): the procedural self-description (device
query, payload, strips) streams BEFORE any inline-data bitmap; bitmaps stream
small to large; the END sentinel is last. All randomness derives from SEED via
paperholo.modulation.rng; outputs regenerate byte-identically (sha-gated).

Outputs: build/disc1.ps, build/disc1_manifest.json, build/disc1_gt/*.npy.
Print at the OFFICE per experiments/007-office-disc.md — NOT via
scripts/print_plane.sh (that path is the home M281).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from paperholo.modulation import cells_to_dots, rng
from paperholo.psgen import A4_PT, CMYK, PSDoc

_HERE = Path(__file__).resolve().parent
_EXP002 = _HERE.parent / "002-calibration-page"
if str(_EXP002) not in sys.path:
    sys.path.insert(0, str(_EXP002))

# byte-identical mark/pattern builders (pure functions; attribution: exp 002.0)
import gen_calpage  # noqa: E402

SEED = b"paper-store/exp007-disc1"
LAYOUT_VERSION = 1
JOBID = hashlib.sha256(SEED + b"/layout1").hexdigest()[:8]
BASE_DPI = 600            # layout/manifest base grid ONLY — never requested
STRIP_S_FIELD = "exp007-disc1"
OUT = _HERE / "build"
GT = OUT / "disc1_gt"
PS_BUDGET_BYTES = 10_000_000

# content bounds: >= 12 mm margins everywhere (unknown printable area)
X_MIN, X_MAX, Y_MIN, Y_MAX = 12.0, 198.0, 12.0, 285.0
# margin probes only: ticks march from 12 mm down to 4 mm off each edge
MARGIN_PROBE_LIMIT_MM = 3.5

STRIP_X_MM = 12.0
STRIP1_Y_MM, STRIP2_Y_MM = 18.0, 276.0
STRIP_W_MM = 724 * 6 * 25.4 / 600     # nominal at 600; scales with granted dpi
STRIP_H_MM = 11 * 6 * 25.4 / 600


def mmd(v_mm: float, dpi: int) -> int:
    return round(v_mm / 25.4 * dpi)


def mm6(v_mm: float) -> int:
    return mmd(v_mm, 600)


U_DPI = 2400   # occupancy grid: lcm of the 300/600/1200/2400 address grids


def umm(v_mm: float) -> int:
    """Occupancy unit: U_DPI-grid dots."""
    return mmd(v_mm, U_DPI)


def pt(v_mm: float) -> float:
    return v_mm / 25.4 * 72.0


CONTENT_U = (umm(X_MIN), umm(Y_MIN), umm(X_MAX), umm(Y_MAX))
MARGIN_U = (umm(MARGIN_PROBE_LIMIT_MM), umm(MARGIN_PROBE_LIMIT_MM),
            umm(210.0 - MARGIN_PROBE_LIMIT_MM), umm(297.0 - MARGIN_PROBE_LIMIT_MM))
BOUNDS_TOL_U = 4   # cross-grid rounding slack (0.04 mm)
S600 = U_DPI // 600   # 600-grid dots -> occupancy units

# page-2 resolution enumeration (trials, in request order) + definitive grant
RQ_TRIALS = (300, 600, 1200, 2400)
P2_DEFINITIVE_DPI = 1200


# ---------------------------------------------------------------------------
# pattern builders (pure; 1 = ink; all randomness via rng(SEED, label))
# ---------------------------------------------------------------------------

def grating(pitch_dots: int, size_dots: int, horizontal: bool) -> np.ndarray:
    """pitch-on/pitch-off square grating (gen_calpage.stripes, square)."""
    on = (np.arange(size_dots) // pitch_dots) % 2 == 0
    a = on[:, None] if horizontal else on[None, :]
    return np.broadcast_to(a, (size_dots, size_dots)).astype(np.uint8)


def lines_w(width_dots: int, size_dots: int, horizontal: bool) -> np.ndarray:
    """width-dot lines at 4*width pitch (25% duty — isolated-line morphology)."""
    on = (np.arange(size_dots) % (4 * width_dots)) < width_dots
    a = on[:, None] if horizontal else on[None, :]
    return np.broadcast_to(a, (size_dots, size_dots)).astype(np.uint8)


def line_pairs(size_dots: int, horizontal: bool) -> np.ndarray:
    """Pairs of single-width lines, 1-dot gap inside a pair, 12-dot pair pitch."""
    r = np.arange(size_dots) % 12
    on = (r == 4) | (r == 6)
    a = on[:, None] if horizontal else on[None, :]
    return np.broadcast_to(a, (size_dots, size_dots)).astype(np.uint8)


def iso_dots(size_dots: int, pitch_dots: int = 8) -> np.ndarray:
    """Isolated 1-dot marks on a pitch_dots-spaced grid."""
    a = np.zeros((size_dots, size_dots), np.uint8)
    a[pitch_dots // 2:: pitch_dots, pitch_dots // 2:: pitch_dots] = 1
    return a


def pn_field(cell: int, size_dots: int, label: bytes) -> np.ndarray:
    """50% i.i.d. random cells, solid cell x cell dots."""
    n = size_dots // cell
    cells = rng(SEED, label).integers(0, 2, size=(n, n), dtype=np.uint8)
    return cells_to_dots(cells, cell)


def tone_field(h_dots: int, w_dots: int, p: float, label: bytes) -> np.ndarray:
    """Seeded random-dot dither at coverage p (NOT ordered: an unknown device
    screen cannot beat against a stochastic pattern)."""
    return (rng(SEED, label).random((h_dots, w_dots)) < p).astype(np.uint8)


def cmy_c3_field(size_dots: int, label: bytes) -> dict[str, np.ndarray]:
    """Three independent 50% c3 planes (simple overlay — no STATES7 needed)."""
    n = size_dots // 3
    return {p: cells_to_dots(
        rng(SEED, label + b"/" + p.encode()).integers(0, 2, size=(n, n),
                                                      dtype=np.uint8), 3)
        for p in "CMY"}


# ---------------------------------------------------------------------------
# print-time PostScript blocks (adapted from gen_calpage, exp002 — the strip
# row/CRC format is UNCHANGED so stripdec.decode_image works verbatim)
# ---------------------------------------------------------------------------

def ps_prolog() -> list[str]:
    """P0/P1: namespace + guards + DEFAULT pagedevice snapshot (pre-request)."""
    return [
        "% exp007 prolog: snapshot the DEFAULT pagedevice (before the guarded",
        "% PageSize request; RD below therefore reads the engine's native default)",
        "/PHC 128 dict def PHC begin",
        "/BUF 128 string def",
        "/TRY { /DFLT exch def mark exch stopped",
        "  { cleartomark DFLT }",
        "  { counttomark 1 eq { exch pop } { cleartomark DFLT } ifelse } ifelse } bind def",
        "/PDD { currentpagedevice } 1 dict TRY def",
        "/LL { languagelevel } 1 TRY def",
    ]


def ps_page2_enum() -> list[str]:
    """Page-2 resolution enumeration + definitive request. ALL /HWResolution
    operations in the job live here, AFTER page 1's showpage: a RIP that
    misbehaves on any of them has already shipped page 1. Each trial is
    guarded (mark/stopped/cleartomark) and its read-back stored for the
    RQ<r> payload fields; the definitive [1200 1200] request (original
    stopped {} if guard form) is what page 2's content prints under."""
    lines = [
        "% ==== PAGE 2: active resolution probe -- the ONLY resolution",
        "% operations in the job; page 1 is complete before these execute ====",
        "PHC begin",
        "/RQGET { { currentpagedevice /HWResolution get 0 get round cvi }"
        " 0 TRY } bind def",
    ]
    for r in RQ_TRIALS:
        lines.append(f"mark {{ << /HWResolution [{r} {r}] >> setpagedevice }}"
                     f" stopped cleartomark /RQ{r} RQGET def")
    lines += [
        "% definitive request: page-2 content prints at the 1200 grant if any",
        f"{{ << /HWResolution [{P2_DEFINITIVE_DPI} {P2_DEFINITIVE_DPI}] >>"
        " setpagedevice } stopped { } if",
    ]
    return lines


def ps_device_and_payload(page: int) -> list[str]:
    """P3: effective device state + dot-space helpers. P4: payload + CRC.

    Deviations from gen_calpage (documented, format-compatible):
    - no R0 field (page 1 requests no resolution — nothing to echo);
    - module MX/MY = max(3, floor(dpi/100)) instead of max(4, round(dpi/100)):
      keeps the 724-module strip on-page at 12 mm margins down to 300 dpi
      (max(4,...) would be 245 mm wide at 300 dpi). stripdec self-scales off
      the printed geometry and never assumes the module formula.

    Page 2 prepends PG=2 and the RQ300..RQ2400 enumeration read-backs in the
    payload FREE AREA between the PHCAL1 magic and the first stripdec-known
    key (LAY): stripdec.parse_payload anchors on ';KEY=' for known keys only,
    so its field extraction is byte-for-byte unaffected. On page 2, PDD (the
    prolog snapshot) still holds the JOB-START default device — RD therefore
    reports the untouched engine default while RE reports the post-request
    grant: the probe's verdict pair, self-documented on the page.
    """
    if page == 1:
        pay_head = ["(PHCAL1;LAY=1;) EMIT"]
    else:
        pay_head = [
            "(PHCAL1;PG=2;) EMIT",
            "(RQ300=) EMIT RQ300 EMITN (;RQ600=) EMIT RQ600 EMITN",
            "(;RQ1200=) EMIT RQ1200 EMITN (;RQ2400=) EMIT RQ2400 EMITN",
            "(;LAY=1;) EMIT",
        ]
    return [
        "% ---- P3: effective device state, dot space, element guard ----",
        "/PDGET { 3 1 roll 2 copy known { get exch pop } { pop pop } ifelse } bind def",
        "/PDE { currentpagedevice } 1 dict TRY def",
        "/HWR PDE /HWResolution [72 72] PDGET def",
        "/HWX HWR 0 get round cvi def",
        "/HWY HWR 1 get round cvi def",
        "/PGSZ PDE /PageSize [595 842] PDGET def",
        "/PAGEHD PGSZ 1 get 72 div HWY mul round cvi def",
        "/MMX { 25.4 div HWX mul round cvi } bind def",
        "/MMY { 25.4 div HWY mul round cvi } bind def",
        "/MX HWX 100 idiv dup 3 lt { pop 3 } if def",
        "/MY HWY 100 idiv dup 3 lt { pop 3 } if def",
        # DOTSPACE starts from the absolute device matrix (initmatrix), so a
        # faulted element that leaked CTM state cannot displace later elements.
        "/DOTSPACE { initmatrix 72 HWX div 72 HWY div scale 0 PAGEHD translate 1 -1 scale } bind def",
        "/ELEM { mark exch gsave stopped grestore cleartomark } bind def",
        "% ---- P4: 388-byte payload + CRC-16/CCITT-FALSE ----",
        "/PAY 512 string def /PLEN 0 def",
        "/EMIT { dup length /LT exch def",
        "  PLEN LT add PAY length le",
        "  { PAY PLEN 3 -1 roll putinterval /PLEN PLEN LT add def } { pop } ifelse } bind def",
        "/EMITN { BUF cvs EMIT } bind def",
        *pay_head,
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


def ps_strips(y1_mm: float, y2_mm: float, x_mm: float) -> list[str]:
    """LAY=1 machine strip drawer (gen_calpage verbatim) + the two placements."""
    return [
        "% ---- machine strips (LAY=1): 724x11 modules, 5 rows x 78 bytes ----",
        "/NB 78 def /NR 5 def /WI 720 def /HI NR 2 add def",
        "/MODB { exch MX mul SX0 add exch MY mul SY0 add MX MY rectfill } bind def",
        "/PUTBIT { 1 eq { COL ROW 1 add MODB } if /COL COL 1 add def } bind def",
        "/PUTBYTE { /B exch def /PARITY 0 def",
        "  7 -1 0 { /I exch def",
        "    B I neg bitshift 1 and dup PARITY xor /PARITY exch def PUTBIT } for",
        "  PARITY PUTBIT } bind def",
        "/STRIP { MMY /SBY0 exch def MMX /SBX0 exch def",
        "  0 0 0 1 setcmykcolor",
        "  SBX0 SBY0 WI 4 add MX mul MY rectfill",
        "  SBX0 SBY0 HI 3 add MY mul add WI 4 add MX mul MY rectfill",
        "  SBX0 SBY0 MX HI 4 add MY mul rectfill",
        "  SBX0 WI 3 add MX mul add SBY0 MX HI 4 add MY mul rectfill",
        "  /SX0 SBX0 MX 2 mul add def /SY0 SBY0 MY 2 mul add def",
        "  0 2 WI 1 sub { 0 MODB } for",
        "  1 2 WI 1 sub { HI 1 sub MODB } for",
        "  0 1 NR 1 sub { /ROW exch def /COL 0 def",
        "    1 PUTBIT 0 PUTBIT 1 PUTBIT 1 PUTBIT",
        "    /RX 0 def",
        "    0 1 NB 1 sub { ROW NB mul add PAY exch get dup RX xor /RX exch def PUTBYTE } for",
        "    RX PUTBYTE } for } bind def",
        f"{{ DOTSPACE {x_mm} {y1_mm} STRIP }} ELEM",
        f"{{ DOTSPACE {x_mm} {y2_mm} STRIP }} ELEM",
    ]


def sentinel_lines(page: int) -> list[str]:
    text = f"END {JOBID} exp007 disc1" + (" p2" if page == 2 else "")
    return [
        "% ---- END sentinel: LAST element in the stream ----",
        "mark { initmatrix 0 0 0 1 setcmykcolor",
        f"  {pt(20.0):.2f} {A4_PT[1] - pt(283.1):.2f} {pt(2.5):.2f} {pt(2.5):.2f} rectfill",
        "  /Helvetica findfont 6 scalefont setfont",
        f"  {pt(24.5):.2f} {A4_PT[1] - pt(283.0):.2f} moveto"
        f" ({text}) show }} stopped cleartomark",
    ]


# ---------------------------------------------------------------------------
# portable document: PSDoc minus the /HWResolution request
# ---------------------------------------------------------------------------

class Disc1Doc(PSDoc):
    """PSDoc with the PORTABLE header: guarded PageSize-only request, no
    /HWResolution in the header or page 1 (unknown engine — the device
    default rules there; page 2's enumeration is emitted as page content).
    render() is overridden rather than psgen changed: every home-printer job
    keeps requesting [600 600] per the measured M281 channel."""

    def render(self) -> str:
        if self._cur is not None:
            raise RuntimeError("last page not ended")
        w_pt, h_pt = self.page_size_pt
        head = [
            "%!PS-Adobe-3.0",
            f"%%Title: {self.title}",
            "%%Creator: paperholo.psgen (exp007 portable header)",
            "%%LanguageLevel: 2",
            "%%DocumentData: Clean7Bit",
            f"%%BoundingBox: 0 0 {w_pt} {h_pt}",
            f"%%Pages: {len(self._pages)}",
            "%%EndComments",
        ]
        head += self.prolog_lines
        head.append(f"{{ << /PageSize [{w_pt} {h_pt}] >> setpagedevice }}"
                    " stopped { } if")
        body: list[str] = []
        for i, page in enumerate(self._pages, 1):
            body += [f"%%Page: {i} {i}", *page, "showpage"]
        return "\n".join(head + body + ["%%Trailer", "%%EOF", ""])


# ---------------------------------------------------------------------------
# page assembly (occupancy in U_DPI-grid units — the lcm of all address
# grids; separate occupancy space, emit lists and label lists per page)
# ---------------------------------------------------------------------------

class Disc1Page:
    def __init__(self) -> None:
        self.doc = Disc1Doc(hw_dpi=BASE_DPI,
                            title=f"paper-store exp007 DISC-1 LAY=1 J={JOBID}",
                            prolog_lines=ps_prolog())
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

    def _occupy(self, name: str, x0: int, y0: int, w: int, h: int,
                clr_mm: float, margin_ok: bool = False) -> None:
        bx0, by0, bx1, by1 = MARGIN_U if margin_ok else CONTENT_U
        t = BOUNDS_TOL_U
        if not (bx0 - t <= x0 and x0 + w <= bx1 + t
                and by0 - t <= y0 and y0 + h <= by1 + t):
            raise AssertionError(f"{name}: rect ({x0},{y0},{w},{h})u outside "
                                 f"{'margin' if margin_ok else 'content'} bounds")
        clr = umm(clr_mm)
        hit = self._conflict(x0, y0, x0 + w, y0 + h, clr)
        if hit is not None:
            raise AssertionError(f"{name} overlaps {hit} (clearance {clr_mm} mm)")
        self.rects[self.page].append((x0, y0, x0 + w, y0 + h, clr, name))

    def _save_gt(self, name: str, bits: np.ndarray) -> str:
        GT.mkdir(parents=True, exist_ok=True)
        rel = f"disc1_gt/{name.replace('/', '__')}.npy"
        if rel in self._gt_files:
            raise AssertionError(f"ground-truth filename collision: {rel}")
        self._gt_files.add(rel)
        np.save(OUT / rel, bits.astype(np.uint8))
        return rel

    # -- content ---------------------------------------------------------------
    def patch(self, name: str, bits: np.ndarray, x_mm: float, y_mm: float,
              plane: str, kind: str, dpi: int = 600, params: dict | None = None,
              save_gt: bool = False, clearance_mm: float = 1.5,
              margin_ok: bool = False) -> None:
        """Single-plane imagemask patch on the `dpi` addressing grid
        (put_bitmap(dpi=...) scales it in device-independent points).
        Manifest x/y/w/h are in that grid's dots; entry carries "dpi"."""
        x, y = mmd(x_mm, dpi), mmd(y_mm, dpi)
        h, w = bits.shape
        s = U_DPI // dpi
        self._occupy(name, x * s, y * s, w * s, h * s, clearance_mm, margin_ok)
        self._mask_emits[self.page].append(
            (w * s * h * s, name, bits, plane, x, y, dpi))
        gt = self._save_gt(name, bits) if save_gt else None
        self.patches.append({"name": name, "kind": kind, "planes": [plane],
                             "page": self.page, "dpi": dpi,
                             "x_dots": x, "y_dots": y,
                             "w_dots": int(w), "h_dots": int(h),
                             "params": params or {}, "gt": gt})

    def patch_cmyk(self, name: str, planes: dict[str, np.ndarray], x_mm: float,
                   y_mm: float, kind: str, params: dict | None = None,
                   save_gt: bool = True, clearance_mm: float = 1.5) -> None:
        """Composite via put_cmyk_bitmap (600 grid); streams after all masks."""
        x, y = mm6(x_mm), mm6(y_mm)
        (h, w), = {a.shape for a in planes.values()}
        self._occupy(name, S600 * x, S600 * y, S600 * w, S600 * h, clearance_mm)
        self._cmyk_emits[self.page].append((name, dict(planes), x, y))
        base = {"emission": "cmyk_image"}
        for p, bits in planes.items():
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind,
                                 "planes": [p], "page": self.page, "dpi": 600,
                                 "x_dots": x,
                                 "y_dots": y, "w_dots": int(w), "h_dots": int(h),
                                 "params": {**base, **(params or {})},
                                 "gt": gt, "composite_of": name})

    def overlap_pair(self, name: str, bits_a: np.ndarray, plane_a: str,
                     xa_mm: float, bits_b: np.ndarray, plane_b: str,
                     xb_mm: float, y_mm: float, kind: str,
                     params: dict | None = None, clearance_mm: float = 1.5) -> None:
        """Two DELIBERATELY overlapping imagemasks (canary; union occupied once).
        Region overlap => screened contone on the M281 class; what THIS engine
        does with it is the datum."""
        xa, xb, y = mm6(xa_mm), mm6(xb_mm), mm6(y_mm)
        (h, w) = bits_a.shape
        assert bits_b.shape == (h, w)
        x0, x1 = min(xa, xb), max(xa, xb) + w
        self._occupy(name, S600 * x0, S600 * y, S600 * (x1 - x0), S600 * h,
                     clearance_mm)
        base = {"emission": "imagemask_pair_overlapping",
                "paint_order": [plane_a, plane_b], "deliberate_overlap": True,
                **(params or {})}
        for p, bits, x in ((plane_a, bits_a, xa), (plane_b, bits_b, xb)):
            self._mask_emits[self.page].append(
                (w * h * S600 * S600, f"{name}_{p}", bits, p, x, y, 600))
            self.patches.append({"name": f"{name}_{p}", "kind": kind,
                                 "planes": [p], "page": self.page, "dpi": 600,
                                 "x_dots": x,
                                 "y_dots": y, "w_dots": int(w), "h_dots": int(h),
                                 "params": dict(base), "gt": None,
                                 "composite_of": name})

    def rect_entry(self, name: str, x_mm: float, y_mm: float, w_mm: float,
                   h_mm: float, kind: str, params: dict | None = None,
                   clearance_mm: float = 0.5, as_patch: bool = False) -> None:
        """Reserve + record a print-time (or deliberately blank) rect."""
        x, y, w, h = mm6(x_mm), mm6(y_mm), mm6(w_mm), mm6(h_mm)
        self._occupy(name, S600 * x, S600 * y, S600 * w, S600 * h, clearance_mm)
        e = {"name": name, "kind": kind, "planes": [], "page": self.page,
             "dpi": 600, "x_dots": x,
             "y_dots": y, "w_dots": w, "h_dots": h, "params": params or {},
             "gt": None}
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
            lx0, ly0 = S600 * lb["x_dots"], S600 * lb["y_dots"]
            lx1 = lx0 + S600 * lb["w_dots"]
            ly1 = ly0 + S600 * lb["h_dots"]
            for x0, y0, x1, y1, _, nm in self.rects[lb["page"]]:
                if lx0 < x1 and x0 < lx1 and ly0 < y1 and y0 < ly1:
                    raise AssertionError(f"label {lb['text']!r} intersects {nm}")

    def place_plus_lattice(self) -> int:
        """21x21-dot plus marks (gen_calpage builder, byte-identical) on the
        25.4 mm grid, whitespace only — scale/registration anchors that stay
        meaningful whatever the granted resolution (physical inch lattice)."""
        assert self.page == 1, "plus lattice is page-1 registration"
        pm = gen_calpage.plus_mark()
        mw = 21 * S600   # mark size in occupancy units
        placed = 0
        for j in range(1, 12):
            for i in range(1, 8):
                cx, cy = 25.4 * i, 25.4 * j
                x, y = mm6(cx) - 10, mm6(cy) - 10
                xu, yu = S600 * x, S600 * y
                bx0, by0, bx1, by1 = CONTENT_U
                if not (bx0 <= xu and xu + mw <= bx1 and by0 <= yu and yu + mw <= by1):
                    continue
                if self._conflict(xu, yu, xu + mw, yu + mw, umm(1.5)) is not None:
                    continue
                pad = umm(1.0)
                if any(lb["page"] == 1
                       and S600 * lb["x_dots"] < xu + mw + pad
                       and xu < S600 * (lb["x_dots"] + lb["w_dots"]) + pad
                       and S600 * lb["y_dots"] < yu + mw + pad
                       and yu < S600 * (lb["y_dots"] + lb["h_dots"]) + pad
                       for lb in self.labels):
                    continue
                name = f"plus_{i}_{j}"
                self.rects[1].append((xu, yu, xu + mw, yu + mw, umm(1.5), name))
                self._mask_emits[1].append((mw * mw, name, pm, "K", x, y, 600))
                self.patches.append({"name": name, "kind": "plus_mark",
                                     "planes": ["K"], "page": 1, "dpi": 600,
                                     "x_dots": x,
                                     "y_dots": y, "w_dots": 21, "h_dots": 21,
                                     "params": {"grid_node_inch": [i, j],
                                                "arm_dots": 3}, "gt": None})
                placed += 1
        return placed

    # -- emission per page: device/payload/strips, labels, masks small->large,
    #    cmyk, dict close, END sentinel last; page 2 opens with the resolution
    #    enumeration (the job's only /HWResolution ops, after showpage 1) ------
    def emit(self) -> None:
        d = self.doc
        # ---- PAGE 1 (byte-identical to the single-page DISC-1 build) ----
        d.begin_page()
        d.put_raw(ps_device_and_payload(1))
        d.put_raw(ps_strips(STRIP1_Y_MM, STRIP2_Y_MM, STRIP_X_MM))
        for text, x, yb, size in self._label_args[1]:
            d.put_label(text, x, yb, CMYK["K"], size_pt=size)
        d.put_raw(["% ==== single-plane imagemask content (small to large) ===="])
        for _, name, bits, plane, x, y, dpi in sorted(
                self._mask_emits[1], key=lambda t: (t[0], t[1])):
            d.put_bitmap(bits, x, y, CMYK[plane], dpi=dpi)
        d.put_raw(["% ==== put_cmyk_bitmap composites (screened on M281 class) ===="])
        for name, planes, x, y in self._cmyk_emits[1]:
            d.put_raw([f"% ---- {name} cmyk-image ----"])
            d.put_cmyk_bitmap(planes, x, y)
        d.put_raw(["end"])   # close the PHC dict opened in the prolog
        d.put_raw(sentinel_lines(1))
        d.end_page()
        # ---- PAGE 2: enumeration + definitive request, then content ----
        d.begin_page()
        d.put_raw(ps_page2_enum())
        d.put_raw(ps_device_and_payload(2))
        d.put_raw(ps_strips(STRIP1_Y_MM, STRIP2_Y_MM, STRIP_X_MM))
        for text, x, yb, size in self._label_args[2]:
            d.put_label(text, x, yb, CMYK["K"], size_pt=size)
        d.put_raw(["% ==== page-2 imagemask content (small to large) ===="])
        for _, name, bits, plane, x, y, dpi in sorted(
                self._mask_emits[2], key=lambda t: (t[0], t[1])):
            d.put_bitmap(bits, x, y, CMYK[plane], dpi=dpi)
        assert not self._cmyk_emits[2], "page 2 is mask-only by design"
        d.put_raw(["end"])   # close PHC (reopened by ps_page2_enum)
        d.put_raw(sentinel_lines(2))
        d.end_page()


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------

RES_ROWS = ((300, 27.0), (600, 38.5), (1200, 50.0))
MORPH_ROWS = ((600, 63.0), (1200, 74.0))
PN_Y_MM = 86.0
TONE_Y_MM = 103.0
CANARY_Y_MM = 116.0

P2_RES_ROWS = ((1200, 27.0), (2400, 38.5))
P2_LW_Y_MM = 50.0
P2_PN_Y_MM = 63.0


def build_header(pg: Disc1Page) -> None:
    pg.label(f"paper-store exp007 DISC-1 office-printer discovery LAY=1 J={JOBID}",
             21.0, 14.2, size_pt=7.0)
    pg.label(f"S={SEED.decode()}  regen: gen_disc1.py | PORTABLE LL2: no "
             "HWResolution request - device default rules", 21.0, 22.9,
             size_pt=5.0)
    pg.label("print ONE sheet, as raw as possible (lp -o raw / raw queue, else "
             "any driver 100% no-fit); HAND-NOTE model+queue/driver in pen",
             21.0, 25.0, size_pt=5.0)
    pg.label("scan 1200 dpi COLOR and GREY, descreen/sharpen/auto-contrast OFF, "
             "flat, include all edges (office scanner too if available)",
             21.0, 267.3, size_pt=5.0)
    pg.label("strips: 724x11 modules, module=max(3,floor(dpi/100)) dots; "
             "5 rows x 78B (8b MSB + even parity) + xor byte; 388B pad 0xA5 + "
             "CRC16-CCITT-F BE; decode: exp002 stripdec.py", 21.0, 275.4,
             size_pt=4.0)


def build_registration(pg: Disc1Page, prefix: str = "") -> None:
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


def res_items(dpi: int) -> tuple:
    """The 7 resolution-critical probes for one addressing grid."""
    s8 = mmd(8.0, dpi)
    return (
        ("g1h", grating(1, s8, True), "grating",
         {"pitch_dots": 1, "orientation": "h_lines"}, "1H"),
        ("g1v", grating(1, s8, False), "grating",
         {"pitch_dots": 1, "orientation": "v_lines"}, "1V"),
        ("g2h", grating(2, s8, True), "grating",
         {"pitch_dots": 2, "orientation": "h_lines"}, "2H"),
        ("g2v", grating(2, s8, False), "grating",
         {"pitch_dots": 2, "orientation": "v_lines"}, "2V"),
        ("dots8", iso_dots(s8), "iso_dot_grid", {"pitch_dots": 8}, "d8"),
        ("lph", line_pairs(s8, True), "line_pairs",
         {"pair_gap_dots": 1, "pair_pitch_dots": 12,
          "orientation": "h_lines"}, "pH"),
        ("lpv", line_pairs(s8, False), "line_pairs",
         {"pair_gap_dots": 1, "pair_pitch_dots": 12,
          "orientation": "v_lines"}, "pV"),
    )


def build_resolution_ladder(pg: Disc1Page, rows: tuple = RES_ROWS,
                            prefix: str = "") -> None:
    for dpi, y0 in rows:
        pg.label(str(dpi), 21.0, y0 + 4.5, size_pt=5.0)
        for k, (nm, bits, kind, params, short) in enumerate(res_items(dpi)):
            x = 34.0 + 9.7 * k
            pg.patch(f"{prefix}res{dpi}/{nm}", bits, x, y0, "K", kind, dpi=dpi,
                     params=params, clearance_mm=0.8)
            pg.label(short, x, y0 + 9.4)


def build_morphology(pg: Disc1Page) -> None:
    for dpi, y0 in MORPH_ROWS:
        s6 = mmd(6.0, dpi)
        items: list[tuple[str, np.ndarray, str, dict, str]] = []
        for w in (1, 2, 3, 4):
            items.append((f"lw{w}h", lines_w(w, s6, True), "line_width",
                          {"width_dots": w, "pitch_dots": 4 * w,
                           "orientation": "h_lines"}, f"{w}H"))
        for w in (1, 2, 3, 4):
            items.append((f"lw{w}v", lines_w(w, s6, False), "line_width",
                          {"width_dots": w, "pitch_dots": 4 * w,
                           "orientation": "v_lines"}, f"{w}V"))
        for n in (1, 2):
            items.append((f"chk{n}", gen_calpage.checker(n, s6), "checker",
                          {"n_dots": n}, f"k{n}"))
        for n in (1, 2, 3, 4):
            items.append((f"hole{n}", gen_calpage.squares(n, s6, True),
                          "white_holes", {"n_dots": n, "spacing_dots": 3 * n},
                          f"o{n}"))
        pg.label(f"m{dpi}", 21.0, y0 + 4.0, size_pt=5.0)
        for k, (nm, bits, kind, params, short) in enumerate(items):
            x = 34.0 + 7.4 * k
            save = nm.startswith("chk")   # pixel-exact preflight anchors
            pg.patch(f"morph{dpi}/{nm}", bits, x, y0, "K", kind, dpi=dpi,
                     params=params, save_gt=save, clearance_mm=0.6)
            pg.label(short, x, y0 + 7.4)


def build_pn_fields(pg: Disc1Page) -> None:
    pg.label("PN50", 21.0, 91.0, size_pt=5.0)
    for k, cell in enumerate((1, 2, 3, 4, 5, 6)):
        x = 34.0 + 13.5 * k
        bits = pn_field(cell, mmd(12.0, 600), b"pn600/c%d" % cell)
        pg.patch(f"pn600/c{cell}", bits, x, PN_Y_MM, "K", "pn_field", dpi=600,
                 params={"cell_dots": cell, "p": 0.5}, save_gt=True,
                 clearance_mm=0.7)
        pg.label(f"c{cell}", x, PN_Y_MM + 13.6)
    for k, cell in enumerate((2, 3)):
        x = 115.0 + 13.5 * k
        bits = pn_field(cell, mmd(12.0, 1200), b"pn1200/c%d" % cell)
        pg.patch(f"pn1200/c{cell}", bits, x, PN_Y_MM, "K", "pn_field", dpi=1200,
                 params={"cell_dots": cell, "p": 0.5}, save_gt=True,
                 clearance_mm=0.7)
        pg.label(f"c{cell}@12", x, PN_Y_MM + 13.6)


def build_tone_wedge(pg: Disc1Page) -> None:
    pg.label("tone", 21.0, TONE_Y_MM + 4.5, size_pt=5.0)
    h, w = mmd(6.0, 600), mmd(12.0, 600)
    for k in range(9):
        p = (k + 1) / 10
        x = 34.0 + 13.5 * k
        pg.patch(f"tone/p{10 * (k + 1)}", tone_field(h, w, p, b"tone/p%d" % (10 * (k + 1))),
                 x, TONE_Y_MM, "K", "tone_step",
                 params={"coverage": p, "dither": "seeded_random_dots"},
                 save_gt=True, clearance_mm=0.7)
        pg.label(str(10 * (k + 1)), x, TONE_Y_MM + 7.6)
    pg.patch("tone/solid", np.ones((h, w), np.uint8), 155.5, TONE_Y_MM, "K",
             "tone_step", params={"coverage": 1.0, "dither": "solid"},
             clearance_mm=0.7)
    pg.label("100", 155.5, TONE_Y_MM + 7.6)
    pg.rect_entry("tone/paper", 169.0, TONE_Y_MM, 12.0, 6.0, "paper_gap",
                  params={"coverage": 0.0}, clearance_mm=0.7, as_patch=True)
    pg.label("paper", 169.0, TONE_Y_MM + 7.6)


def build_canaries(pg: Disc1Page) -> None:
    solid10 = np.ones((mm6(10.0), mm6(10.0)), np.uint8)
    for k, p in enumerate("KCMY"):
        pg.patch(f"canary/solid_{p}", solid10, 34.0 + 12.0 * k, CANARY_Y_MM, p,
                 "canary_solid", params={"emission": "imagemask_single"},
                 clearance_mm=1.0)
        pg.label(p, 34.0 + 12.0 * k, CANARY_Y_MM + 11.9)
    pg.patch_cmyk("canary/cmy_c3", cmy_c3_field(mm6(15.0), b"canary/cmy_c3"),
                  86.0, CANARY_Y_MM, "canary_composite",
                  params={"cell_dots": 3, "p": 0.5}, save_gt=True,
                  clearance_mm=1.0)
    pg.label("CMY c3 cmyk-image", 86.0, CANARY_Y_MM + 16.9)
    pg.overlap_pair("canary/cm_overlap", solid10, "C", 106.0, solid10, "M",
                    111.0, CANARY_Y_MM, "canary_overlap_pair",
                    params={"offset_mm": 5.0}, clearance_mm=1.0)
    pg.label("C+M overlap", 106.0, CANARY_Y_MM + 11.9)


def build_geometry_instruments(pg: Disc1Page) -> None:
    vh, vw = mm6(247.0), mm6(4.0)
    vbits = np.broadcast_to(((np.arange(vh) // 3) % 2 == 0)[:, None],
                            (vh, vw)).astype(np.uint8)
    pg.patch("rY_strip_left", np.ascontiguousarray(vbits), 15.0, 27.0, "K",
             "phase_grating", params={"period_dots": 6,
                                      "orientation": "horizontal_lines",
                                      "instrument": "r(y)"}, clearance_mm=0.5)
    hw, hh = mm6(174.0), mm6(4.0)
    hbits = np.broadcast_to(((np.arange(hw) // 3) % 2 == 0)[None, :],
                            (hh, hw)).astype(np.uint8)
    pg.patch("rX_strip_bottom", np.ascontiguousarray(hbits), 21.0, 269.0, "K",
             "phase_grating", params={"period_dots": 6,
                                      "orientation": "vertical_lines",
                                      "instrument": "r(x)"}, clearance_mm=0.5)


def build_margin_probes(pg: Disc1Page) -> None:
    """2x2 mm ticks marching toward each edge, near-edge gap 12 -> 4 mm in
    1 mm steps (each tick at a different along-edge position): the outermost
    tick that survives printing brackets the true printable boundary."""
    tick = np.ones((mm6(2.0), mm6(2.0)), np.uint8)
    for i in range(9):
        d = 12 - i
        for edge, x_mm, y_mm in (("top", 152.0 + 4.5 * i, float(d)),
                                 ("bottom", 100.0 + 4.5 * i, 297.0 - d - 2.0),
                                 ("left", float(d), 120.0 + 4.5 * i),
                                 ("right", 210.0 - d - 2.0, 120.0 + 4.5 * i)):
            pg.patch(f"mt_{edge}_{d}", tick, x_mm, y_mm, "K", "margin_tick",
                     params={"edge": edge, "gap_mm": d}, clearance_mm=0.5,
                     margin_ok=True)


def build_page(pg: Disc1Page) -> dict:
    build_header(pg)
    for n, ys in (("1", STRIP1_Y_MM), ("2", STRIP2_Y_MM)):
        pg.rect_entry(f"machine_strip_{n}", STRIP_X_MM, ys, STRIP_W_MM,
                      STRIP_H_MM, "machine_strip",
                      params={"modules": [724, 11], "rows": 5,
                              "bytes_per_row": 78, "payload_bytes": 390,
                              "module_dots_formula":
                                  "max(3, floor(hw_dpi/100)) per axis "
                                  "(exp007 deviation from exp002: fits the "
                                  "page down to 300 dpi; stripdec self-scales)",
                              "crc": "CRC-16/CCITT-FALSE big-endian",
                              "row_format": "sync 1011 + 78x(8b MSB + even "
                                            "parity) + xor byte + 5 pad",
                              "rect_is_nominal_600dpi": True},
                      clearance_mm=0.4)
    build_registration(pg)
    build_resolution_ladder(pg)
    build_morphology(pg)
    build_pn_fields(pg)
    build_tone_wedge(pg)
    build_canaries(pg)
    build_geometry_instruments(pg)
    build_margin_probes(pg)
    pg.rect_entry("quiet_zone", 150.0, 136.0, 30.0, 30.0, "quiet_zone",
                  params={"purpose": "white ref + scanner noise floor + "
                                     "background contamination hunt"},
                  clearance_mm=1.0)
    pg.rect_entry("end_sentinel", 20.0, 280.4, 42.0, 3.0, "end_sentinel",
                  params={"text": f"END {JOBID} exp007 disc1"})
    n_plus = pg.place_plus_lattice()
    assert n_plus >= 15, f"only {n_plus} plus marks placed — registration thin"
    return {"n_plus_marks": n_plus}


def build_page2(pg: Disc1Page) -> None:
    pg.page = 2
    pg.label(f"paper-store exp007 DISC-1 PAGE 2 - active resolution probe "
             f"J={JOBID}", 21.0, 14.2, size_pt=7.0)
    pg.label("res enumeration 300/600/1200/2400 (guarded) precedes this page; "
             "granted values in strip payload RQ*; definitive request 1200",
             21.0, 22.9, size_pt=5.0)
    pg.label("outcomes all informative: refused (RE=RD default) / granted "
             "clean / granted corrupt - compare vs page-1 no-request control",
             21.0, 25.0, size_pt=5.0)
    pg.label("strip format = page 1; payload preamble adds PG=2 + "
             "RQ300/600/1200/2400 before LAY (stripdec field parse unchanged)",
             21.0, 275.4, size_pt=4.0)
    for n, ys in (("1", STRIP1_Y_MM), ("2", STRIP2_Y_MM)):
        pg.rect_entry(f"p2/machine_strip_{n}", STRIP_X_MM, ys, STRIP_W_MM,
                      STRIP_H_MM, "machine_strip",
                      params={"modules": [724, 11], "rows": 5,
                              "bytes_per_row": 78, "payload_bytes": 390,
                              "payload_preamble": "PG=2 + RQ300..RQ2400 "
                                                  "(free area before LAY)",
                              "crc": "CRC-16/CCITT-FALSE big-endian",
                              "rect_is_nominal_600dpi": True},
                      clearance_mm=0.4)
    build_registration(pg, prefix="p2/")
    build_resolution_ladder(pg, rows=P2_RES_ROWS, prefix="p2/")
    # line-width ladder 1..4 dots H+V at the definitive 1200 grid
    pg.label("lw1200", 21.0, P2_LW_Y_MM + 4.0, size_pt=5.0)
    s6 = mmd(6.0, 1200)
    k = 0
    for horiz in (True, False):
        for w in (1, 2, 3, 4):
            x = 34.0 + 7.4 * k
            o = "h" if horiz else "v"
            pg.patch(f"p2/lw1200/lw{w}{o}", lines_w(w, s6, horiz), x,
                     P2_LW_Y_MM, "K", "line_width", dpi=1200,
                     params={"width_dots": w, "pitch_dots": 4 * w,
                             "orientation": f"{o}_lines"}, clearance_mm=0.6)
            pg.label(f"{w}{o.upper()}", x, P2_LW_Y_MM + 7.4)
            k += 1
    # PN fields: c2/c3/c4 at the granted 1200 grid + fresh-label 600 control
    pg.label("PN50", 21.0, P2_PN_Y_MM + 5.0, size_pt=5.0)
    for k, cell in enumerate((2, 3, 4)):
        x = 34.0 + 13.5 * k
        bits = pn_field(cell, mmd(12.0, 1200), b"p2/pn1200/c%d" % cell)
        pg.patch(f"p2/pn1200/c{cell}", bits, x, P2_PN_Y_MM, "K", "pn_field",
                 dpi=1200, params={"cell_dots": cell, "p": 0.5}, save_gt=True,
                 clearance_mm=0.7)
        pg.label(f"c{cell}", x, P2_PN_Y_MM + 13.6)
    ctl = pn_field(3, mmd(12.0, 600), b"p2/pn600/c3-control")
    pg.patch("p2/pn600/c3_ctl", ctl, 74.5, P2_PN_Y_MM, "K", "pn_field",
             dpi=600, params={"cell_dots": 3, "p": 0.5,
                              "role": "cross-page control, fresh rng label"},
             save_gt=True, clearance_mm=0.7)
    pg.label("c3@6ctl", 74.5, P2_PN_Y_MM + 13.6)
    pg.rect_entry("p2/end_sentinel", 20.0, 280.4, 42.0, 3.0, "end_sentinel",
                  params={"text": f"END {JOBID} exp007 disc1 p2"})


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GT.mkdir(parents=True, exist_ok=True)
    pg = Disc1Page()
    extra = build_page(pg)
    build_page2(pg)
    pg.assert_labels_clear()
    pg.emit()
    ps = pg.doc.render()

    # portability + stream-order invariants (belt and braces; tests re-check)
    assert ps.isascii(), "%%DocumentData: Clean7Bit violated (non-ASCII byte)"
    lines = ps.splitlines()
    assert "%%Pages: 2" in ps and ps.count("%%Page:") == 2, "must be TWO pages"
    assert "%%LanguageLevel: 2" in ps
    spd = [ln for ln in lines
           if "setpagedevice" in ln and not ln.lstrip().startswith("%")]
    assert len(spd) == 2 + len(RQ_TRIALS), spd   # PageSize + 4 trials + final
    assert spd[0] == "{ << /PageSize [595 842] >> setpagedevice } stopped { } if"
    hw_req = [ln for ln in spd if "HWResolution" in ln]
    assert len(hw_req) == len(RQ_TRIALS) + 1, hw_req
    assert hw_req[-1] == ("{ << /HWResolution [1200 1200] >> setpagedevice }"
                          " stopped { } if")
    i_sp1 = ps.index("showpage")            # page 1 ships before ANY of them
    assert all(ps.index(ln) > i_sp1 for ln in hw_req), \
        "resolution operation leaked before page 1's showpage"
    p1 = ps[ps.index("%%Page: 1 1"): ps.index("%%Page: 2 2")]
    assert "setpagedevice" not in p1, "page 1 must stay request-free"
    i_cmyk = p1.index("% ==== put_cmyk_bitmap composites")
    assert p1.rindex("imagemask") < i_cmyk, "p1 masks must stream before cmyk"
    i_s1 = p1.index("% ---- END sentinel")
    assert i_s1 > i_cmyk and "imagemask" not in p1[i_s1:] \
        and ">> image" not in p1[i_s1:], "p1 END sentinel must be last"
    i_s2 = ps.rindex("% ---- END sentinel")
    assert i_s2 > ps.index("%%Page: 2 2") and "imagemask" not in ps[i_s2:] \
        and ">> image" not in ps[i_s2:], "p2 END sentinel must be last"
    assert f"(END {JOBID} exp007 disc1 p2) show" in ps[i_s2:]
    assert len(ps) <= PS_BUDGET_BYTES, f"ps {len(ps) / 1e6:.1f} MB > budget"

    (OUT / "disc1.ps").write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()
    manifest = {
        "experiment": "007-office-disc",
        "artifact": "disc1",
        "run": "007.0",
        "layout_version": LAYOUT_VERSION,
        "seed": SEED.decode(),
        "jobid": JOBID,
        "pages": 2,
        "base_dpi": BASE_DPI,
        "base_dpi_note": "layout/manifest grid only — page 1 requests NO "
                         "/HWResolution (unknown engine, device default rules); "
                         "each patch carries its own dpi + page keys",
        "ps_file": "disc1.ps",
        "ps_sha256": sha,
        "ps_bytes": len(ps),
        "print_command": "OFFICE printer, TWO sheets (one job): lp -d <queue> "
                         "-o raw disc1.ps preferred; any PS driver at "
                         "100%/no-fit as fallback; hand-note "
                         "model+queue+driver on sheet 1",
        "payload_prefix": f"PHCAL1;LAY=1;J={JOBID};S={STRIP_S_FIELD};",
        "payload_prefix_p2": "PHCAL1;PG=2;",
        "strip_s_field": STRIP_S_FIELD,
        "payload_fields_printtime": ["LL", "RD", "RE", "PS", "IB", "PR", "V",
                                     "RV", "SN"],
        "page2": {
            "purpose": "active resolution probe, isolated behind page 1's "
                       "showpage — refused / granted-clean / granted-corrupt "
                       "are all informative",
            "resolution_enumeration": list(RQ_TRIALS),
            "rq_fields": [f"RQ{r}" for r in RQ_TRIALS],
            "rq_fields_note": "granted x-resolution read back after each "
                              "guarded trial; recorded in the payload free "
                              "area before LAY so stripdec parsing is "
                              "unchanged (RD stays the job-start default)",
            "definitive_request": [P2_DEFINITIVE_DPI, P2_DEFINITIVE_DPI],
            "guarded": True,
        },
        "portability": {"language_level": 2,
                        "hwresolution_request_page1": None,
                        "hwresolution_request_page2": "enumeration "
                        "300/600/1200/2400 + definitive 1200, all guarded, "
                        "all after page 1 showpage",
                        "pagesize_request_pt": [595, 842],
                        "pagesize_guarded": True, "margins_mm": 12.0,
                        "margin_probe_min_mm": 4.0,
                        "strip_module_formula": "max(3, floor(dpi/100))"},
        "content_bounds_mm": [X_MIN, Y_MIN, X_MAX, Y_MAX],
        "n_plus_marks": extra["n_plus_marks"],
        "patches": pg.patches,
        "infrastructure": pg.infra,
        "labels": pg.labels,
    }
    (OUT / "disc1_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote build/disc1.ps ({len(ps) / 1e6:.2f} MB, {len(pg.patches)} "
          f"patches, {extra['n_plus_marks']} plus marks)")
    print(f"sha256 {sha}")


if __name__ == "__main__":
    main()
