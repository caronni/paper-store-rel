#!/usr/bin/env python
"""Experiment 002 — self-describing calibration page (print side).

One A4 page that any Level-2 engine can print via scripts/print_plane.sh and one
1200 dpi scan can analyze: print-time device self-report (default + effective
pagedevice, product/version/serial), rendered as text and as TWO 390-byte
machine strips (CRC-16/CCITT-FALSE); chiral corner marks; dot-exact rulers with
machine-readable inch indices; left phase-grating strip (transport function);
per-plane structural + density + BER + slanted-edge bands; 8-state CMY and
16-state CMYK fields; multilevel K/C; overlay solids; canaries (contone setgray,
1-dot phase pairs, rectfill-vs-imagemask probe); MIC quiet zone; K banding
strip; warp/mottle fields; composite encode patches; END sentinel.

Error containment: the job's procedural self-description (device query, strips,
text, rulers) streams BEFORE any inline-data bitmap; bitmaps stream small to
large; the END sentinel is last. Every stochastic patch derives from SEED via
paperholo.modulation.rng; outputs regenerate byte-identically.

Outputs: build/calpage.ps, build/calpage_manifest.json, build/calpage_gt/*.npy.
Print ONLY via ../../scripts/print_plane.sh after user confirmation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from paperholo.modulation import cells_to_dots, rng
from paperholo.pilots import pilot_sites
from paperholo.psgen import CMYK, PSDoc

SEED = b"paper-store/exp002-calpage"
LAYOUT_VERSION = 1
JOBID = hashlib.sha256(SEED + b"/layout1").hexdigest()[:8]
DEFAULT_HW_DPI = 600
HW_DPI = DEFAULT_HW_DPI  # set by main(); layout grid + setpagedevice request
OUT = Path(__file__).parent / "build"
GT = OUT / "calpage_gt"

# Tier-0/1 content bounds, mm (6 mm margins on A4)
X_MIN, X_MAX, Y_MIN, Y_MAX = 6.0, 204.0, 6.0, 291.0


def mm(v: float) -> int:
    return round(v / 25.4 * HW_DPI)


def pt(v_mm: float) -> float:
    return v_mm / 25.4 * 72.0


# ---------------------------------------------------------------------------
# pattern builders (pure; 1 = ink)
# ---------------------------------------------------------------------------

def stripes(pitch_dots: int, size_dots: int, horizontal: bool) -> np.ndarray:
    ramp = (np.arange(size_dots) // pitch_dots) % 2 == 0
    a = ramp[:, None] if horizontal else ramp[None, :]
    return np.broadcast_to(a, (size_dots, size_dots)).astype(np.uint8)


def checker(n_dots: int, size_dots: int) -> np.ndarray:
    idx = np.arange(size_dots) // n_dots
    return ((idx[:, None] + idx[None, :]) % 2).astype(np.uint8)


def squares(n_dots: int, size_dots: int, invert: bool) -> np.ndarray:
    """Isolated n x n squares, spacing 3n: ink-on-white or white-in-ink."""
    a = np.zeros((size_dots, size_dots), np.uint8)
    for y in range(n_dots, size_dots - n_dots, 3 * n_dots):
        for x in range(n_dots, size_dots - n_dots, 3 * n_dots):
            a[y: y + n_dots, x: x + n_dots] = 1
    return (1 - a) if invert else a


def dot_grid1(size_dots: int) -> np.ndarray:
    """1-dot marks at 4-dot pitch (dead on the M281 — death is the datum)."""
    a = np.zeros((size_dots, size_dots), np.uint8)
    a[2::4, 2::4] = 1
    return a


def rand_field(h_dots: int, w_dots: int, cell: int, p: float, label: bytes) -> np.ndarray:
    ny, nx = h_dots // cell, w_dots // cell
    cells = (rng(SEED, label).random((ny, nx)) < p).astype(np.uint8)
    return cells_to_dots(cells, cell)


def encoding_patch(cell: int, size_dots: int, label: bytes) -> np.ndarray:
    """M-A modulation sample: scrambled 50% cells + pilot lattice (gen_gridtest)."""
    n = size_dots // cell
    data = rng(SEED, label + b"/data").integers(0, 2, size=(n, n), dtype=np.uint8)
    pv = rng(SEED, label + b"/pilot-values").integers(0, 2, size=(n, n), dtype=np.uint8)
    m = pilot_sites((n, n), SEED)
    data[m] = pv[m]
    return cells_to_dots(data, cell)


def multilevel_patch(size_dots: int, label: bytes) -> tuple[np.ndarray, np.ndarray]:
    """cell=3 field, per-cell level in {0,3,6,9}-of-9 dots, fixed intra-cell
    patterns: 3 = main diagonal, 6 = its complement, 9 = full."""
    n = size_dots // 3
    lv = rng(SEED, label).integers(0, 4, size=(n, n), dtype=np.uint8)
    eye = np.eye(3, dtype=np.uint8)
    pats = np.stack([np.zeros((3, 3), np.uint8), eye, 1 - eye, np.ones((3, 3), np.uint8)])
    bits = pats[lv].transpose(0, 2, 1, 3).reshape(3 * n, 3 * n)
    return lv, bits


def state_field(size_dots: int, planes: str, label: bytes) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """cell=3 field, per-cell state uniform over 2^len(planes) combos.
    Bit i of the state drives planes[i] (documented in the manifest)."""
    n = size_dots // 3
    st = rng(SEED, label).integers(0, 2 ** len(planes), size=(n, n), dtype=np.uint8)
    return st, {p: cells_to_dots((st >> i) & 1, 3) for i, p in enumerate(planes)}


def slant_edge(size_dots: int) -> np.ndarray:
    """Two 5-degree slanted edges (near-vertical upper, near-horizontal lower)."""
    t = math.tan(math.radians(5.0))
    a = np.zeros((size_dots, size_dots), np.uint8)
    h2 = size_dots // 2
    for y in range(0, h2 - 6):
        xe = int(round(size_dots * 0.55 + (y - (h2 - 6) / 2) * t))
        a[y, : max(0, min(size_dots, xe))] = 1
    y_mid = h2 + 6 + int((size_dots - h2 - 6) * 0.45)
    for x in range(size_dots):
        ye = y_mid + int(round((x - size_dots / 2) * t))
        a[max(h2 + 6, ye):, x] = 1
    return a


def phase_pair(vertical_lines: bool) -> np.ndarray:
    """Two pitch-2 gratings offset by exactly 1 dot (resolution-clamp canary)."""
    w_g, gap, h = 128, 14, 141
    a = np.zeros((h, 2 * w_g + gap), np.uint8)
    x = np.arange(2 * w_g + gap)
    a[:, ((x % 2 == 0) & (x < w_g)) | ((x % 2 == 1) & (x >= w_g + gap))] = 1
    return a if vertical_lines else a.T.copy()


def cm_comb(size_dots: int, horizontal: bool) -> dict[str, np.ndarray]:
    """C/M interleaved 1-on/1-off (Nyquist cross-plane phase; dead on M281)."""
    r = np.arange(size_dots)
    even = (r % 2 == 0)
    axis = (even[:, None] if horizontal else even[None, :])
    c = np.broadcast_to(axis, (size_dots, size_dots)).astype(np.uint8)
    return {"C": c, "M": (1 - c).astype(np.uint8)}


def lines1(size_dots: int, horizontal: bool) -> np.ndarray:
    """1-dot lines at pitch 6."""
    on = (np.arange(size_dots) % 6 == 0)
    a = on[:, None] if horizontal else on[None, :]
    return np.broadcast_to(a, (size_dots, size_dots)).astype(np.uint8)


def plus_mark() -> np.ndarray:
    a = np.zeros((21, 21), np.uint8)
    a[9:12, :] = 1
    a[:, 9:12] = 1
    return a


def corner_mark(n_sat: int, inward: tuple[int, int]) -> np.ndarray:
    """Cross (3-dot strokes, 60-dot arms) + n_sat 8x8 satellites at 12-dot pitch
    along the inward diagonal. Counts TL=1 TR=2 BR=3 BL=4 give rotation from any
    two adjacent corners; the 1-2-3-4 clockwise order is chiral (mirror flag)."""
    a = np.zeros((123, 123), np.uint8)
    a[60:63, :] = 1
    a[:, 60:63] = 1
    dy, dx = inward
    for k in range(n_sat):
        d = 18 + 12 * k
        cy, cx = 61 + dy * d, 61 + dx * d
        a[cy - 4: cy + 4, cx - 4: cx + 4] = 1
    return a


def quad_cross() -> np.ndarray:
    a = np.zeros((33, 33), np.uint8)
    a[15:18, :] = 1
    a[:, 15:18] = 1
    return a


# ---------------------------------------------------------------------------
# print-time PostScript blocks (procedural, no inline data, ELEM/TRY guarded)
# ---------------------------------------------------------------------------

def ps_prolog() -> list[str]:
    """P0/P1: namespace + guards + DEFAULT pagedevice snapshot (pre-setpagedevice)."""
    return [
        "% exp002 prolog: snapshot the DEFAULT pagedevice before our setpagedevice",
        "/PHC 128 dict def PHC begin",
        "/BUF 128 string def",
        "/TRY { /DFLT exch def mark exch stopped",
        "  { cleartomark DFLT }",
        "  { counttomark 1 eq { exch pop } { cleartomark DFLT } ifelse } ifelse } bind def",
        "/PDD { currentpagedevice } 1 dict TRY def",
        "/LL { languagelevel } 1 TRY def",
    ]


def ps_device_and_payload() -> list[str]:
    """P3: effective device state + dot-space helpers. P4: 390-byte payload + CRC."""
    hw = HW_DPI
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
        "/MX HWX 100 div round cvi dup 4 lt { pop 4 } if def",
        "/MY HWY 100 div round cvi dup 4 lt { pop 4 } if def",
        # DOTSPACE starts from the absolute device matrix (initmatrix), so a
        # faulted element that leaked CTM state cannot displace later elements.
        "/DOTSPACE { initmatrix 72 HWX div 72 HWY div scale 0 PAGEHD translate 1 -1 scale } bind def",
        # NOTE deviation from the panel design: no grestoreall/initgraphics in
        # ELEM. Measured on gs 10.07: grestoreall unwinds to the pre-setpagedevice
        # gstate and REVERTS the device to the default page size. gsave/grestore
        # around stopped stays; leaked gsaves only grow the gstate stack.
        "/ELEM { mark exch gsave stopped grestore cleartomark } bind def",
        "% ---- P4: 388-byte payload + CRC-16/CCITT-FALSE ----",
        "/PAY 512 string def /PLEN 0 def",
        "/EMIT { dup length /LT exch def",
        "  PLEN LT add PAY length le",
        "  { PAY PLEN 3 -1 roll putinterval /PLEN PLEN LT add def } { pop } ifelse } bind def",
        "/EMITN { BUF cvs EMIT } bind def",
        # Deviation from the panel payload spec: no G=<date> field — a date
        # literal would break byte-identical regeneration (CLAUDE.md
        # determinism); the print date lives in the experiment log instead.
        "(PHCAL1;LAY=1;) EMIT",
        f"(J={JOBID};S={SEED.decode()};R0={hw}x{hw};) EMIT",
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
    """LAY=1 machine strip drawer + the two placements (dot-exact rectfill)."""
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


def ps_text_block() -> list[str]:
    """Human self-report: title, 3x130-byte payload echo, scan protocol,
    bootstrap format lines. Default point space, guarded (font may be absent)."""
    hw = HW_DPI
    title = (f"paper-store exp002 CAL page LAY=1 J={JOBID} S={SEED.decode()} "
             f"R0={hw}x{hw}dpi (payload echo below = machine strip bytes)")
    proto = ("scan 1200 dpi RGB + grey, descreen/sharpen/auto-contrast OFF, full page "
             "incl corners; scan B rotated 90 deg; optional +24h rescan (hygro)")
    boot = [
        "strip 724x11 modules, module=max(4,round(dpi/100)) dots; rows: clock / 5 data / inv clock",
        "row = sync1011 + 78x(8bit MSB + even parity) + xor byte; 388B pad 0xA5 + CRC16-CCITT-F BE",
        f"regen: gen_calpage.py seed={SEED.decode()} layout={LAYOUT_VERSION}; decode: stripdec.py",
    ]

    def at(x_mm_v: float, y_mm_v: float) -> str:
        return f"{pt(x_mm_v):.2f} {842 - pt(y_mm_v):.2f} moveto"

    lines = [
        "% ---- human-readable self-report (no inline data) ----",
        "/SHOWLN { dup PZ lt",
        "  { PZ 1 index sub dup 130 gt { pop 130 } if PAY 3 1 roll getinterval show }",
        "  { pop } ifelse } bind def",
        "{ initmatrix 0 0 0 1 setcmykcolor",
        "  /Helvetica findfont 8 scalefont setfont",
        f"  {at(16.0, 9.5)} ({title}) show",
        "  /Helvetica findfont 6 scalefont setfont",
        f"  {at(16.0, 12.0)} 0 SHOWLN",
        f"  {at(16.0, 14.2)} 130 SHOWLN",
        f"  {at(16.0, 16.4)} 260 SHOWLN",
        f"  {at(16.0, 18.6)} ({proto}) show",
        "  /Helvetica findfont 5 scalefont setfont",
    ]
    for i, b in enumerate(boot):
        lines.append(f"  {at(82.0, 258.0 + 2.7 * i)} ({b}) show")
    lines.append("} ELEM")
    return lines


def ps_rulers() -> list[str]:
    """Dot-exact rulers with machine-readable inch indices at major ticks.
    Tick pitch = HWX/10 dots = 0.1 inch on any engine; index = 1 start module +
    4 index bits (LSB first) + even parity, 6x6-dot modules at 12-dot pitch."""
    idx_mods = (
        "      /KV I 10 idiv def",
        "      /PB KV dup -1 bitshift xor dup -2 bitshift xor 1 and def",
    )
    return [
        "% ---- rulers: top (indices 0-7) + left (0-9) ----",
        "{ DOTSPACE 0 0 0 1 setcmykcolor",
        "  /TKX HWX 10 idiv def",
        "  /RX0 10.0 MMX def /RY0 25.5 MMY def",
        "  RX0 RY0 TKX 74 mul 3 add 3 rectfill",
        "  0 1 74 { /I exch def",
        "    /TX RX0 I TKX mul add def",
        "    TX RY0 3 I 10 mod 0 eq { 50 } { I 5 mod 0 eq { 35 } { 20 } ifelse } ifelse rectfill",
        "    I 10 mod 0 eq {",
        *idx_mods,
        "      TX 6 add RY0 54 add 6 6 rectfill",
        "      0 1 3 { /BB exch def KV BB neg bitshift 1 and 1 eq",
        "        { TX 18 add BB 12 mul add RY0 54 add 6 6 rectfill } if } for",
        "      PB 1 eq { TX 66 add RY0 54 add 6 6 rectfill } if } if } for",
        "} ELEM",
        "{ DOTSPACE 0 0 0 1 setcmykcolor",
        "  /TKY HWY 10 idiv def",
        "  /RXL 6.0 MMX def /RY1 30.0 MMY def",
        "  RXL RY1 3 TKY 95 mul 3 add rectfill",
        "  0 1 95 { /I exch def",
        "    /TY RY1 I TKY mul add def",
        "    RXL TY I 10 mod 0 eq { 50 } { I 5 mod 0 eq { 35 } { 20 } ifelse } ifelse 3 rectfill",
        "    I 10 mod 0 eq {",
        *idx_mods,
        "      RXL 24 add TY 12 add 6 6 rectfill",
        "      0 1 3 { /BB exch def KV BB neg bitshift 1 and 1 eq",
        "        { RXL 24 add TY 24 add BB 12 mul add 6 6 rectfill } if } for",
        "      PB 1 eq { RXL 24 add TY 72 add 6 6 rectfill } if } if } for",
        "} ELEM",
    ]


def ps_contone(patches: list[tuple[float, float, float, float, float]]) -> list[str]:
    """(x_mm, y_mm, w_mm, h_mm, gray) setgray rectfills — device-screen canary."""
    lines = ["% ---- contone setgray canaries (device screen fingerprint) ----",
             "{ DOTSPACE"]
    for x, y, w, h, g in patches:
        lines.append(f"  {g} setgray {x} MMX {y} MMY {w} MMX {h} MMY rectfill")
    lines.append("} ELEM")
    return lines


def ps_rect_probe(x_mm_v: float, y_chk_mm: float, y_lin_mm: float) -> list[str]:
    """rectfill halves of the raster-consistency probe (imagemask twins are
    psgen bitmaps at the same nominal geometry, offset +14 mm in x)."""
    return [
        "% ---- raster-consistency probe, rectfill halves ----",
        "{ DOTSPACE 0 0 0 1 setcmykcolor",
        f"  /PX {x_mm_v} MMX def /PY {y_chk_mm} MMY def",
        "  0 1 93 { /RR exch def 0 1 93 { /QQ exch def",
        "    RR QQ add 2 mod 0 eq { PX QQ 3 mul add PY RR 3 mul add 3 3 rectfill } if } for } for",
        f"  /PY {y_lin_mm} MMY def",
        "  0 1 70 { /QQ exch def PX QQ 4 mul add PY 2 118 rectfill } for",
        "} ELEM",
    ]


def ps_sentinel() -> list[str]:
    return [
        "% ---- END sentinel: LAST element in the stream ----",
        "{ DOTSPACE 0 0 0 1 setcmykcolor 18.0 MMX 286.5 MMY 2.5 MMX 2.5 MMY rectfill } ELEM",
        "{ initmatrix 0 0 0 1 setcmykcolor /Helvetica findfont 6 scalefont setfont",
        f"  {pt(22.5):.2f} {842 - pt(289.2):.2f} moveto (END {JOBID} exp002 calpage) show }} ELEM",
    ]


# ---------------------------------------------------------------------------
# page assembly: occupancy, manifest, deferred small-to-large bitmap emission
# ---------------------------------------------------------------------------

class CalPage:
    def __init__(self) -> None:
        self.doc = PSDoc(hw_dpi=HW_DPI, title=f"paper-store exp002 calpage LAY=1 J={JOBID}",
                         prolog_lines=ps_prolog(), guard_setpagedevice=True)
        self.rects: list[tuple[int, int, int, int, int, str]] = []  # x0,y0,x1,y1,clr,name
        self.patches: list[dict] = []
        self.infra: list[dict] = []
        self.labels: list[dict] = []
        self.cuts: list[dict] = []
        self._bitmaps: list[tuple[int, str, str, object, int, int]] = []
        self._label_args: list[tuple[str, int, int, float]] = []
        self._gt_files: set[str] = set()

    # -- occupancy ---------------------------------------------------------
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

    # -- content -----------------------------------------------------------
    def patch(self, name: str, bits: np.ndarray, x_mm: float, y_mm: float, plane: str,
              kind: str, params: dict | None = None, save_gt: bool = False,
              clearance_mm: float = 1.5) -> None:
        x, y = mm(x_mm), mm(y_mm)
        h, w = bits.shape
        self._occupy(name, x, y, w, h, clearance_mm)
        self._bitmaps.append((h * w, name, "mask", (bits, plane), x, y))
        gt = self._save_gt(name, bits) if save_gt else None
        self.patches.append({"name": name, "kind": kind, "planes": [plane],
                             "x_dots": x, "y_dots": y, "w_dots": int(w), "h_dots": int(h),
                             "params": params or {}, "gt": gt})

    def patch_multi(self, name: str, planes: dict[str, np.ndarray], x_mm: float, y_mm: float,
                    kind: str, params: dict | None = None, save_gt: bool = False,
                    clearance_mm: float = 1.5) -> None:
        x, y = mm(x_mm), mm(y_mm)
        (h, w), = {a.shape for a in planes.values()}
        self._occupy(name, x, y, w, h, clearance_mm)
        self._bitmaps.append((h * w * len(planes), name, "cmyk", dict(planes), x, y))
        for p, bits in planes.items():
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind, "planes": [p],
                                 "x_dots": x, "y_dots": y, "w_dots": int(w), "h_dots": int(h),
                                 "params": params or {}, "gt": gt,
                                 "composite_of": name})

    def rect_entry(self, name: str, x_mm: float, y_mm: float, w_mm: float, h_mm: float,
                   kind: str, params: dict | None = None, clearance_mm: float = 0.5,
                   as_patch: bool = False) -> None:
        """Reserve + record a rect drawn print-time (or deliberately blank)."""
        x, y, w, h = mm(x_mm), mm(y_mm), mm(w_mm), mm(h_mm)
        self._occupy(name, x, y, w, h, clearance_mm)
        e = {"name": name, "kind": kind, "planes": [], "x_dots": x, "y_dots": y,
             "w_dots": w, "h_dots": h, "params": params or {}, "gt": None}
        (self.patches if as_patch else self.infra).append(e)

    def label(self, text: str, x_mm: float, y_baseline_mm: float, size_pt: float = 4.0) -> None:
        x, yb = mm(x_mm), mm(y_baseline_mm)
        w = round(len(text) * 0.58 * size_pt / 72 * HW_DPI)
        asc = round(0.78 * size_pt / 72 * HW_DPI)
        desc = round(0.24 * size_pt / 72 * HW_DPI)
        self.labels.append({"text": text, "x_dots": x, "y_dots": yb - asc,
                            "w_dots": w, "h_dots": asc + desc})
        self._label_args.append((text, x, yb, size_pt))

    def _save_gt(self, name: str, bits: np.ndarray) -> str:
        GT.mkdir(parents=True, exist_ok=True)
        # '__' keeps the mapping injective: 'Y/density_30' must not collide with
        # a patch literally named 'Y_density_30'.
        rel = f"calpage_gt/{name.replace('/', '__')}.npy"
        if rel in self._gt_files:
            raise AssertionError(f"ground-truth filename collision: {rel}")
        self._gt_files.add(rel)
        np.save(OUT / rel, bits.astype(np.uint8))
        return rel

    def assert_labels_clear(self) -> None:
        """The linetest label bug, made a checked constraint."""
        for lb in self.labels:
            lx0, ly0 = lb["x_dots"], lb["y_dots"]
            lx1, ly1 = lx0 + lb["w_dots"], ly0 + lb["h_dots"]
            for x0, y0, x1, y1, _, nm in self.rects:
                if lx0 < x1 and x0 < lx1 and ly0 < y1 and y0 < ly1:
                    raise AssertionError(f"label {lb['text']!r} intersects {nm}")

    def place_plus_lattice(self) -> int:
        """21x21-dot plus marks on the 25.4 mm grid, whitespace only."""
        pm = plus_mark()
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
                self._bitmaps.append((21 * 21, f"plus_{i}_{j}", "mask", (pm, "K"), x, y))
                self.patches.append({"name": f"plus_{i}_{j}", "kind": "plus_mark", "planes": ["K"],
                                     "x_dots": x, "y_dots": y, "w_dots": 21, "h_dots": 21,
                                     "params": {"grid_node_inch": [i, j], "arm_dots": 3}, "gt": None})
                placed += 1
        return placed

    # -- emission ----------------------------------------------------------
    def emit(self, raw_pre: list[list[str]], raw_post: list[list[str]]) -> None:
        self.doc.begin_page()
        for blk in raw_pre:
            self.doc.put_raw(blk)
        for text, x, yb, size in self._label_args:
            self.doc.put_label(text, x, yb, CMYK["K"], size_pt=size)
        for _, name, mode, payload, x, y in sorted(self._bitmaps, key=lambda t: (t[0], t[1])):
            if mode == "mask":
                bits, plane = payload
                self.doc.put_bitmap(bits, x, y, CMYK[plane])
            else:
                self.doc.put_cmyk_bitmap(payload, x, y)
        for blk in raw_post:
            self.doc.put_raw(blk)
        self.doc.put_raw(["end"])
        self.doc.end_page()


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------

BAND_Y = {"K": 30.0, "C": 58.0, "M": 86.0, "Y": 114.0}  # band pitch 28 mm


def build_band(cal: CalPage, plane: str, y0: float) -> None:
    lp = f"exp002/band/{plane}".encode()
    s8 = mm(8)
    row1: list[tuple[str, str, np.ndarray, dict]] = []
    for p in (1, 2, 3, 4):
        row1.append((f"lines_h_p{p}", f"H{p}", stripes(p, s8, True),
                     {"pitch_dots": p, "horizontal": True}))
    for p in (1, 2, 3, 4):
        row1.append((f"lines_v_p{p}", f"V{p}", stripes(p, s8, False),
                     {"pitch_dots": p, "horizontal": False}))
    for n in (1, 2, 3, 4):
        row1.append((f"checker_n{n}", f"k{n}", checker(n, s8), {"n_dots": n}))
    for n in (1, 2):
        row1.append((f"dots_n{n}", f"d{n}", squares(n, s8, False), {"n_dots": n}))
    for n in (1, 2, 3):
        row1.append((f"holes_n{n}", f"o{n}", squares(n, s8, True), {"n_dots": n}))
    for i, (nm, short, bits, params) in enumerate(row1):
        x = 18.0 + i * 9.7
        cal.patch(f"{plane}/{nm}", bits, x, y0, plane, nm.split("_")[0], params)
        cal.label(short, x, y0 + 9.7)
    cal.label(plane, 183.5, y0 + 6.0, size_pt=8.0)

    y2 = y0 + 11.0
    for i in range(9):
        p = (i + 1) * 10
        x = 18.0 + i * 9.7
        cal.patch(f"{plane}/density_{p}", rand_field(s8, s8, 3, p / 100, lp + b"/density%d" % p),
                  x, y2, plane, "density_field", {"p": p / 100, "cell_dots": 3}, save_gt=True)
        cal.label(str(p), x, y2 + 9.7)
    cal.patch(f"{plane}/solid", np.ones((mm(10), mm(10)), np.uint8), 106.0, y2, plane, "solid", {})
    cal.label("100", 106.0, y2 + 11.7)
    for nm, cell, sz, x in (("c1", 1, 8.0, 118.0), ("c2", 2, 12.0, 128.0),
                            ("c3", 3, 14.0, 142.0), ("c4", 4, 12.0, 158.0)):
        cal.patch(f"{plane}/encode_{nm}", encoding_patch(cell, mm(sz), lp + b"/encode%d" % cell),
                  x, y2, plane, "encoding_patch",
                  {"cell_dots": cell, "pilot_block": 6, "pilot_period": 64}, save_gt=True)
        cal.label(f"e{cell}", x, y2 + sz + 1.7)
    cal.patch(f"{plane}/slant", slant_edge(mm(12)), 172.0, y2, plane, "slant_edge",
              {"angle_deg": 5.0})
    cal.label("sl", 172.0, y2 + 13.7)


def build_page(cal: CalPage) -> dict:
    # -- Tier-0 infrastructure (print-time; nominal rects reserved) ----------
    cal.rect_entry("human_text", 16.0, 6.5, 180.0, 12.8, "text_block",
                   {"content": "title + 3x130B payload echo + scan protocol"})
    strip_w = 724 * 6 * 25.4 / 600  # nominal at 600; module scales with granted dpi
    strip_h = 11 * 6 * 25.4 / 600
    for n, ys in (("1", 20.0), ("2", 279.5)):
        cal.rect_entry(f"machine_strip_{n}", 8.0, ys, strip_w, strip_h, "machine_strip",
                       {"modules": [724, 11], "rows": 5, "bytes_per_row": 78,
                        "module_dots_formula": "max(4, round(hw_dpi/100)) per axis",
                        "payload_bytes": 390, "crc": "CRC-16/CCITT-FALSE big-endian",
                        "row_format": "sync 1011 + 78x(8b MSB + even parity) + xor byte + 5 pad",
                        "clocks": "top black-first, bottom white-first"})
    cal.rect_entry("ruler_top", 10.0, 25.5, 188.3, 2.6, "ruler",
                   {"tick_pitch": "hw_dpi/10 dots = 0.1 inch", "ticks": 75,
                    "index": "1 start + 4 bits LSB-first + even parity, 6x6-dot modules @12"})
    cal.rect_entry("ruler_left", 6.0, 30.0, 3.5, 241.5, "ruler",
                   {"tick_pitch": "hw_dpi/10 dots", "ticks": 96, "index": "as ruler_top"})
    for tag, n_sat, inward, cx, cy in (("tl", 1, (1, 1), 10.0, 10.0),
                                       ("tr", 2, (1, -1), 200.0, 10.0),
                                       ("br", 3, (-1, -1), 200.0, 288.0),
                                       ("bl", 4, (-1, 1), 10.0, 288.0)):
        cm_bits = corner_mark(n_sat, inward)
        cal.patch(f"corner_{tag}", cm_bits, cx - 61 * 25.4 / HW_DPI, cy - 61 * 25.4 / HW_DPI,
                  "K", "corner_mark",
                  {"satellites": n_sat, "inward": list(inward), "arm_dots": 60, "width_dots": 3,
                   "cx_dots": mm(cx) , "cy_dots": mm(cy)}, clearance_mm=0.5)

    # left phase-grating strip: 3-on/3-off horizontal K lines -> transport function
    ph = np.broadcast_to(((np.arange(5712) // 3) % 2 == 0)[:, None], (5712, 118)).astype(np.uint8)
    cal.patch("phase_strip_left", np.ascontiguousarray(ph), 10.5, 30.0, "K", "phase_grating",
              {"period_dots": 6, "orientation": "horizontal_lines"}, clearance_mm=0.5)

    # registration quads: K cross at node, C/M/Y at +5mm offsets, 5 stations
    qc = quad_cross()
    for qi, (qx, qy) in enumerate(((191.0, 30.0), (191.0, 86.0), (191.0, 142.0),
                                   (191.0, 198.0), (191.0, 254.0))):
        for p, (ox, oy) in (("K", (0.0, 0.0)), ("C", (5.0, 0.0)),
                            ("M", (0.0, 5.0)), ("Y", (5.0, 5.0))):
            cal.patch(f"quad{qi}_{p}", qc, qx + ox, qy + oy, p, "reg_cross",
                      {"station": qi, "offset_mm": [ox, oy], "arm_dots": 15, "width_dots": 3},
                      clearance_mm=1.0)

    # -- per-plane bands ------------------------------------------------------
    for p, y0 in BAND_Y.items():
        build_band(cal, p, y0)

    # -- overlay solids + canary block (y 143.5) ------------------------------
    solid10 = np.ones((mm(10), mm(10)), np.uint8)
    combos = (("C",), ("M",), ("Y",), ("K",), ("C", "M"), ("C", "Y"),
              ("M", "Y"), ("C", "M", "Y"), ("K", "C", "M", "Y"))
    for i, planes in enumerate(combos):
        x = 18.0 + 12.0 * i
        cal.patch_multi(f"overlay_{''.join(planes)}", {p: solid10 for p in planes},
                        x, 143.5, "overlay_solid", {})
        cal.label("+".join(planes), x, 155.4)
    for g, x in ((0.75, 128.0), (0.50, 138.0), (0.25, 148.0)):
        cal.rect_entry(f"contone_{int(g*100)}", x, 143.5, 8.0, 8.0, "contone_setgray",
                       {"setgray": g, "nominal_ink": round(1 - g, 2)},
                       clearance_mm=1.0, as_patch=True)
        cal.label(f"g{int(g*100)}", x, 153.4)
    cal.patch("phasepair_v", phase_pair(True), 160.0, 143.5, "K", "phase_pair",
              {"pitch_dots": 2, "offset_dots": 1, "lines": "vertical"})
    cal.label("ppV", 160.0, 151.4)
    cal.patch("phasepair_h", phase_pair(False), 173.0, 143.5, "K", "phase_pair",
              {"pitch_dots": 2, "offset_dots": 1, "lines": "horizontal"})
    cal.label("ppH", 173.0, 156.6)

    # -- row 6 (y 157.5): state fields, multilevel, encode references ---------
    st8, pl8 = state_field(mm(20), "CMY", b"exp002/state8")
    GT.mkdir(parents=True, exist_ok=True)
    np.save(GT / "state8_states.npy", st8)
    cal.patch_multi("state8", pl8, 18.0, 157.5, "state_field",
                    {"cell_dots": 3, "n_states": 8, "bit_planes": "bit0=C bit1=M bit2=Y",
                     "states_gt": "calpage_gt/state8_states.npy"}, save_gt=True)
    cal.label("8-state CMY c3", 18.0, 179.4)
    st16, pl16 = state_field(mm(20), "CMYK", b"exp002/state16")
    np.save(GT / "state16_states.npy", st16)
    cal.patch_multi("state16", pl16, 42.0, 157.5, "state_field",
                    {"cell_dots": 3, "n_states": 16, "bit_planes": "bit0=C bit1=M bit2=Y bit3=K",
                     "states_gt": "calpage_gt/state16_states.npy"}, save_gt=True)
    cal.label("16-state CMYK c3", 42.0, 179.4)
    for p, x in (("K", 66.0), ("C", 85.0)):
        lv, bits = multilevel_patch(mm(15), b"exp002/mlvl/" + p.encode())
        np.save(GT / f"mlvl_{p}_levels.npy", lv)
        cal.patch(f"mlvl_{p}", bits, x, 157.5, p, "multilevel_field",
                  {"cell_dots": 3, "levels": [0, 3, 6, 9],
                   "patterns": "0=empty 3=diag 6=inv-diag 9=full",
                   "levels_gt": f"calpage_gt/mlvl_{p}_levels.npy"}, save_gt=True)
        cal.label(f"mlvl {p} 0/3/6/9", x, 174.9)
    cal.patch("encode_K_ref", encoding_patch(3, mm(18), b"exp002/encode_K_ref"),
              104.0, 157.5, "K", "encoding_patch",
              {"cell_dots": 3, "pilot_block": 6, "pilot_period": 64}, save_gt=True)
    cal.label("K c3 ref", 104.0, 177.4)
    cal.patch_multi("composite_c2",
                    {p: encoding_patch(2, mm(18), b"exp002/composite_c2/" + p.encode())
                     for p in ("C", "M", "Y")}, 126.0, 157.5, "encoding_patch",
                    {"cell_dots": 2, "pilot_block": 6, "pilot_period": 64}, save_gt=True)
    cal.label("CMY c2", 126.0, 177.4)

    # -- row 7 (y 181.5): composite c3, raster probe, quiet zone, aggressive --
    cal.patch_multi("composite_c3",
                    {p: encoding_patch(3, mm(25), b"exp002/composite_c3/" + p.encode())
                     for p in ("C", "M", "Y")}, 18.0, 181.5, "encoding_patch",
                    {"cell_dots": 3, "pilot_block": 6, "pilot_period": 64}, save_gt=True)
    cal.label("CMY c3 composite", 18.0, 208.6)
    cal.rect_entry("probe_checker_rectfill", 47.5, 181.5, 94 * 3 * 25.4 / HW_DPI,
                   94 * 3 * 25.4 / HW_DPI, "raster_probe_rectfill",
                   {"n_dots": 3, "cells": 94}, clearance_mm=1.0, as_patch=True)
    cal.patch("probe_checker_imagemask", checker(3, 282), 61.5, 181.5, "K",
              "raster_probe_imagemask", {"n_dots": 3, "cells": 94}, clearance_mm=1.0)
    cal.rect_entry("probe_lines_rectfill", 47.5, 196.5, (70 * 4 + 2) * 25.4 / HW_DPI,
                   118 * 25.4 / HW_DPI, "raster_probe_rectfill",
                   {"line_w_dots": 2, "pitch_dots": 4}, clearance_mm=1.0, as_patch=True)
    lin2 = np.broadcast_to((np.arange(282) % 4 < 2)[None, :], (118, 282)).astype(np.uint8)
    cal.patch("probe_lines_imagemask", np.ascontiguousarray(lin2), 61.5, 196.5, "K",
              "raster_probe_imagemask", {"line_w_dots": 2, "pitch_dots": 4}, clearance_mm=1.0)
    cal.label("probe: rectfill | imagemask", 47.5, 209.4)
    cal.rect_entry("quiet_zone", 79.0, 181.5, 28.0, 28.0, "quiet_zone",
                   {"purpose": "white ref + mottle/noise + MIC hunt (blue channel)"},
                   clearance_mm=1.5)
    cal.label("quiet zone (blank)", 79.0, 211.4)
    cal.patch_multi("comb_cm_v", cm_comb(mm(8), False), 111.0, 181.5, "nyquist_comb",
                    {"axis": "vertical_lines", "planes": "C even, M odd"})
    cal.patch_multi("comb_cm_h", cm_comb(mm(8), True), 121.0, 181.5, "nyquist_comb",
                    {"axis": "horizontal_lines", "planes": "C even, M odd"})
    for p, x in (("C", 131.0), ("M", 141.0), ("Y", 151.0)):
        cal.patch(f"dotgrid1_{p}", dot_grid1(mm(8)), x, 181.5, p, "dot_grid_1dot",
                  {"pitch_dots": 4})
    cal.label("aggressive: CMcombV/H  1-dot C M Y", 111.0, 191.2)

    # -- row 8 (y 213.5): warp field, CMY mottle, Y stress, banding strip -----
    cal.patch("warp_field", rand_field(mm(60), mm(60), 3, 0.5, b"exp002/warp"),
              18.0, 213.5, "K", "warp_field", {"p": 0.5, "cell_dots": 3}, save_gt=True)
    cal.label("K 50% c3 warp/mottle", 18.0, 275.2)
    cal.patch_multi("mottle_cmy",
                    {p: rand_field(mm(40), mm(40), 3, 0.5, b"exp002/mottle/" + p.encode())
                     for p in ("C", "M", "Y")}, 82.0, 213.5, "mottle_field",
                    {"p": 0.5, "cell_dots": 3}, save_gt=True)
    cal.label("CMY 50% mottle", 82.0, 255.2)
    cal.patch("Y_encode_c3", encoding_patch(3, mm(20), b"exp002/ystress/encode"),
              126.0, 213.5, "Y", "encoding_patch",
              {"cell_dots": 3, "pilot_block": 6, "pilot_period": 64}, save_gt=True)
    cal.patch("Y_density_30", rand_field(mm(10), mm(10), 3, 0.3, b"exp002/ystress/d30"),
              148.0, 213.5, "Y", "density_field", {"p": 0.3, "cell_dots": 3}, save_gt=True)
    cal.patch("Y_density_70", rand_field(mm(10), mm(10), 3, 0.7, b"exp002/ystress/d70"),
              148.0, 225.5, "Y", "density_field", {"p": 0.7, "cell_dots": 3}, save_gt=True)
    cal.patch("Y_lines1_h", lines1(mm(8), True), 126.0, 235.5, "Y", "lines_1dot",
              {"pitch_dots": 6, "horizontal": True})
    cal.patch("Y_lines1_v", lines1(mm(8), False), 136.0, 235.5, "Y", "lines_1dot",
              {"pitch_dots": 6, "horizontal": False})
    cal.label("Y stress: c3 / 30 / 70 / 1-dot HV", 126.0, 245.9)
    cal.patch("banding_K", rand_field(mm(113.5), mm(20), 3, 0.5, b"exp002/banding"),
              168.0, 159.5, "K", "banding_strip", {"p": 0.5, "cell_dots": 3}, save_gt=True)
    cal.label("K banding", 168.0, 275.2)

    # -- END sentinel rect (drawn print-time, last in stream) -----------------
    cal.rect_entry("end_sentinel", 18.0, 286.5, 42.0, 2.8, "end_sentinel",
                   {"text": f"END {JOBID} exp002 calpage"})

    # -- plus-mark lattice in remaining whitespace ----------------------------
    n_plus = cal.place_plus_lattice()

    # -- labels checked, cuts recorded ----------------------------------------
    cal.assert_labels_clear()
    cal.cuts = [
        {"item": "verniers", "reason": "arbitration: quad centroids give ~0.1 dot; priority cut #1"},
        {"item": "multilevel M and Y", "reason": "priority cut #4: K+C suffice to accept/reject M-C as a class"},
        {"item": "bottom cell=3 replicas + K 40x40 rehearsal", "reason": "priority cut #2: stationarity partially recoverable from 113 mm banding strip; K c3 ref kept at 18x18"},
        {"item": "banding strips C/M/Y", "reason": "priority cut #7: coarse C/M/Y banding from field row means; K strip kept full height"},
        {"item": "orientation triangles", "reason": "chiral satellite counts already give rotation + mirror"},
        {"item": "top phase-grating strip (fast axis)", "reason": "arbitration: ONE left strip; fast-axis scale from rulers/quads"},
        {"item": "1200-grid stripe probes", "reason": "never probe above the requested grid (run 001.0); 1-dot phase pairs are the clamp canary"},
        {"item": "BER c1/c4 downsized to 8x8/12x12 mm", "reason": "space; c2>=12x12 and c3>=14x14 kept at full statistical size per arbitration"},
    ]
    return {"n_plus_marks": n_plus}


def main() -> None:
    global HW_DPI
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hwres", type=int, default=DEFAULT_HW_DPI,
                    help="requested /HWResolution and layout grid (default 600)")
    args = ap.parse_args()
    HW_DPI = args.hwres

    OUT.mkdir(parents=True, exist_ok=True)
    GT.mkdir(parents=True, exist_ok=True)
    cal = CalPage()
    extra = build_page(cal)
    raw_pre = [
        ps_device_and_payload(),
        ps_strips(20.0, 279.5, 8.0),
        ps_text_block(),
        ps_rulers(),
        ps_contone([(128.0, 143.5, 8.0, 8.0, 0.75), (138.0, 143.5, 8.0, 8.0, 0.50),
                    (148.0, 143.5, 8.0, 8.0, 0.25)]),
        ps_rect_probe(47.5, 181.5, 196.5),
    ]
    cal.emit(raw_pre, [ps_sentinel()])
    ps = cal.doc.render()
    (OUT / "calpage.ps").write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()
    manifest = {
        "experiment": "002-calibration-page",
        "layout_version": LAYOUT_VERSION,
        "seed": SEED.decode(),
        "jobid": JOBID,
        "hw_dpi": HW_DPI,
        "ps_file": "calpage.ps",
        "ps_sha256": sha,
        "print_command": "../../scripts/print_plane.sh build/calpage.ps",
        "payload_prefix": f"PHCAL1;LAY=1;J={JOBID};S={SEED.decode()};R0={HW_DPI}x{HW_DPI};",
        "payload_fields_printtime": ["LL", "RD", "RE", "PS", "IB", "PR", "V", "RV", "SN"],
        "content_bounds_mm": [X_MIN, Y_MIN, X_MAX, Y_MAX],
        "n_plus_marks": extra["n_plus_marks"],
        "cuts": cal.cuts,
        "patches": cal.patches,
        "infrastructure": cal.infra,
        "labels": cal.labels,
    }
    (OUT / "calpage_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote build/calpage.ps ({len(ps) / 1e6:.2f} MB, "
          f"{len(cal.patches)} patches, {extra['n_plus_marks']} plus marks)")
    print(f"sha256 {sha}")


if __name__ == "__main__":
    main()
