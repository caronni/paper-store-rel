#!/usr/bin/env python
"""E006 retrieval-loop pages: two full-area Layer-1 measurement sheets.

Both pages share ONE band skeleton (strips + corners are the landmarks — NO
plus-mark lattice): content x 12.0-197.9 mm (4392 dots, divisible by 2/3/4),
bands on a fixed vertical pitch of 360 dots (15.24 mm) from y0 = 20.0 mm.
Each band = a 6-dot SYNC STRIP (3 rows of known cell=2 cells, full width,
clean K imagemask) + a 354-dot PAYLOAD region, flush. 16 data bands, then a
CANARY band (B1 c2 + i2w3 fields, K/C/M/Y solids, labelled paper gap), the
E004 refs row (clean K/C/M/Y + cmyk C,M,Y,CM,CY,MY solids), END sentinel,
4 chiral corner marks at the gen_e004 positions.

  e006bw  clean-path K page: bands 0-9 B1 c2 encoding fields (pilot sites
          included, gen_e004 construction), 10-12 B2 RLL i2w3 free-form
          fields, 13-15 probe patches (i3w3, fill75 c2, anisotropic 2x3/3x2
          cells, 3-level grey at c3/c4).
  e006c   screened-path page: bands 0-15 7-state CMY alphabet cell=3
          uniform state fields (002.2 construction, put_cmyk_bitmap);
          bands 0/7/15 flagged "training" (identical construction).

Emission discipline (Layer-0 freeze, 002.0-003.0): all single-plane content
is K/C/M/Y imagemask (bit-faithful clean path); A3 bands are put_cmyk_bitmap
composites (region overlap => screened contone, ALWAYS). Masks stream before
any cmyk image; END sentinel last (002.2/003.0 idiom). Wide constrained
fields are row-DP sampled along the short axis and transposed (the i/w
constraint set is symmetric; the DP's float counts cap row width at 900).

Outputs: build/e006bw.ps + build/e006c.ps, one manifest each, ground truth
in build/e006_gt/. Byte-identical regeneration from SEED; sha256 gates
reuse. Print ONLY via scripts/print_plane.sh after user confirmation
in-session (.claude/rules/hardware.md).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

from paperholo.modulation import cells_to_dots, rng
from paperholo.pilots import pilot_sites
from paperholo.psgen import A4_PT, CMYK, PSDoc

_HERE = Path(__file__).resolve().parent
_EXP002 = _HERE.parent / "002-calibration-page"
_EXP003 = _HERE.parent / "003-modulation-probes"
for p in (str(_HERE), str(_EXP002), str(_EXP003)):
    if p not in sys.path:
        sys.path.insert(0, p)

# byte-identical mark builders + occupancy/label machinery + row-DP sampler
# internals (all pure functions / classes; attribution: exp 002.0/002.1/003.0)
import gen_calpage  # noqa: E402
import gen_composite_probe as gcp  # noqa: E402
import gen_modprobe as gmp  # noqa: E402

SEED = b"paper-store/exp006-loop"
LAYOUT_VERSION = 1
HW_DPI = 600
PAGES = ("bw", "c")
JOBID = {t: hashlib.sha256(SEED + f"/{t}".encode() + b"/layout1").hexdigest()[:8]
         for t in PAGES}
OUT = _HERE / "build"
GT = OUT / "e006_gt"

X_MIN, X_MAX, Y_MIN, Y_MAX = 6.0, 204.0, 6.0, 291.0

STATES7 = ("W", "C", "M", "Y", "CM", "CY", "MY")   # 002.0c winning alphabet
PS_BUDGET_BYTES = 30_000_000
ROW_DP_MAX_W = 900     # gen_modprobe._sample_row float-count cap


def mm(v: float) -> int:
    return round(v / 25.4 * HW_DPI)


def pt(v_mm: float) -> float:
    return v_mm / 25.4 * 72.0


def as_mm(d: int) -> float:
    """Exact dots -> mm for the mm()-based placement API (asserted lossless)."""
    v = d * 25.4 / HW_DPI
    assert mm(v) == d, (d, v)
    return v


# band skeleton (shared by both pages)
X0_DOTS = mm(12.0)                     # 283
CONTENT_W_DOTS = 4392                  # 185.93 mm; divisible by 2, 3, 4
Y0_DOTS = mm(20.0)                     # 472
STRIP_PITCH_DOTS = 360                 # 15.24 mm
STRIP_H_DOTS = 6                       # 3 rows of cell=2 known cells
PAYLOAD_H_DOTS = STRIP_PITCH_DOTS - STRIP_H_DOTS   # 354
N_DATA_BANDS = 16
CANARY_BAND = 16                       # one extra band after band 15
assert CONTENT_W_DOTS % 12 == 0


def strip_y(i: int) -> int:
    return Y0_DOTS + i * STRIP_PITCH_DOTS


def payload_y(i: int) -> int:
    return strip_y(i) + STRIP_H_DOTS


def min_count_3sigma(n_cells: int, n_states: int) -> int:
    """Per-state count floor: 3 sigma below the uniform expectation."""
    p = 1.0 / n_states
    return int(n_cells * p - 3.0 * math.sqrt(n_cells * p * (1.0 - p)))


A3_CELL_DOTS = 3
A3_NX = CONTENT_W_DOTS // A3_CELL_DOTS         # 1464 cells
A3_NY = PAYLOAD_H_DOTS // A3_CELL_DOTS         # 118 cells
MIN_PER_STATE_A3 = min_count_3sigma(A3_NX * A3_NY, len(STATES7))


# ---------------------------------------------------------------------------
# content builders (pure; 1 = ink; all randomness via rng(SEED, label);
# copied from gen_e004.py with the exp-006 seed — dot-exact signatures)
# ---------------------------------------------------------------------------

def uniform_state_field(w_dots: int, h_dots: int, cell_dots: int,
                        states: tuple[str, ...], label: bytes,
                        min_per_state: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Per-cell state i.i.d. uniform over `states` (002.2 construction);
    returns (state array, per-plane dot bitmaps). gen_e004 builder, taking
    exact dot dimensions instead of mm."""
    nx = w_dots // cell_dots
    ny = h_dots // cell_dots
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


def encoding_cells_rect(cell: int, w_dots: int, h_dots: int,
                        label: bytes) -> np.ndarray:
    """Cell layer of the gen_gridtest/003-incumbent construction: 50% data
    cells, pilot values overwrite at pilot_sites (pilot cells scored as data
    by the incumbent analyzers — keep byte-comparable construction)."""
    ny, nx = h_dots // cell, w_dots // cell
    data = rng(SEED, label + b"/data").integers(0, 2, size=(ny, nx), dtype=np.uint8)
    pv = rng(SEED, label + b"/pilot-values").integers(0, 2, size=(ny, nx),
                                                      dtype=np.uint8)
    m = pilot_sites((ny, nx), SEED)
    data[m] = pv[m]
    return data


def encoding_patch_rect(cell: int, w_dots: int, h_dots: int,
                        label: bytes) -> np.ndarray:
    """gen_e004 B1 construction, rectangular (solid cells)."""
    return cells_to_dots(encoding_cells_rect(cell, w_dots, h_dots, label), cell)


def fill75_patch_rect(w_dots: int, h_dots: int, label: bytes) -> np.ndarray:
    """B1 c2 construction, but each INK cell drops one corner dot (75% fill).
    Dropped corner cycles deterministically by (cell_x + cell_y) % 4 over
    TL, TR, BR, BL — no extra randomness."""
    cell = 2
    cells = encoding_cells_rect(cell, w_dots, h_dots, label)
    ny, nx = cells.shape
    dots = cells_to_dots(cells, cell)
    corner = (np.arange(nx)[None, :] + np.arange(ny)[:, None]) % 4
    for k, (dy, dx) in enumerate(((0, 0), (0, 1), (1, 1), (1, 0))):
        yy, xx = np.nonzero((corner == k) & (cells == 1))
        dots[yy * cell + dy, xx * cell + dx] = 0
    return dots


def aniso_cell_field(w_dots: int, h_dots: int, cell_w: int, cell_h: int,
                     label: bytes) -> np.ndarray:
    """50% random cells of cell_w x cell_h dots (custom kron)."""
    ny, nx = h_dots // cell_h, w_dots // cell_w
    cells = rng(SEED, label).integers(0, 2, size=(ny, nx), dtype=np.uint8)
    return np.kron(cells, np.ones((cell_h, cell_w), dtype=np.uint8))


def grey_level_field(w_dots: int, h_dots: int, cell: int,
                     label: bytes) -> tuple[np.ndarray, np.ndarray]:
    """3-level per-cell field: 0 = blank, 1 = vertical cell x 2-dot bar
    (left-aligned), 2 = full cell. Per-cell level uniform over 3 via rng.
    Returns (level array, dot bitmap)."""
    ny, nx = h_dots // cell, w_dots // cell
    lv = rng(SEED, label).integers(0, 3, size=(ny, nx), dtype=np.uint8)
    glyph = np.zeros((3, cell, cell), np.uint8)
    glyph[1, :, :2] = 1
    glyph[2, :, :] = 1
    dots = glyph[lv].transpose(0, 2, 1, 3).reshape(ny * cell, nx * cell)
    return lv, dots


def constrained_field_rect(h_dots: int, w_dots: int, min_ink: int,
                           min_white: int, label: bytes) -> tuple[np.ndarray, dict]:
    """Rectangular 2-D RLL field via gen_modprobe's row-DP internals
    (_sample_row / assert_run_lengths are pure — seeded HERE with exp-006's
    SEED). Every maximal run of ink >= min_ink and white >= min_white, both
    axes, border runs included (asserted). Fields wider than the DP's 900-dot
    row cap are sampled transposed (rows along the short axis) — the
    constraint set is symmetric, so a transposed sample is a valid field."""
    transposed = w_dots > ROW_DP_MAX_W
    ny, nx = (w_dots, h_dots) if transposed else (h_dots, w_dots)
    assert nx <= ROW_DP_MAX_W, f"both axes exceed the row-DP cap: {h_dots}x{w_dots}"
    gen = rng(SEED, label)
    minr = np.array([min_white, min_ink], dtype=np.int64)
    a = np.zeros((ny, nx), dtype=np.uint8)
    col_color = np.zeros(nx, dtype=np.int64)
    col_run = np.zeros(nx, dtype=np.int64)
    log2_total = 0.0
    for y in range(ny):
        if y == 0:
            forced = np.full(nx, -1, dtype=np.int64)
        else:
            must_cont = (col_run < minr[col_color]) | \
                        (ny - y < minr[1 - col_color])
            forced = np.where(must_cont, col_color, -1)
        bits, l2 = gmp._sample_row(forced, min_white, min_ink, gen)
        log2_total += l2
        a[y] = bits
        if y == 0:
            col_color = bits.astype(np.int64)
            col_run = np.ones(nx, dtype=np.int64)
        else:
            same = bits.astype(np.int64) == col_color
            col_run = np.where(same, col_run + 1, 1)
            col_color = bits.astype(np.int64)
    if transposed:
        a = np.ascontiguousarray(a.T)
    gmp.assert_run_lengths(a, min_ink, min_white)
    stats = {
        "min_ink_run_dots": min_ink,
        "min_white_run_dots": min_white,
        "sampler": "gen_modprobe row-DP (rectangular wrapper, exp-006 seed"
                   + (", transposed" if transposed else "") + ")",
        "sampler_entropy_bits_per_dot": round(log2_total / (h_dots * w_dots), 6),
        "ink_fraction": round(float(a.mean()), 6),
    }
    return a, stats


def sync_strip_bits(tag: str, i: int) -> np.ndarray:
    """SYNC STRIP i: 3 rows of known cell=2 cells, full content width."""
    cells = rng(SEED, f"strip/{tag}/{i}".encode()).integers(
        0, 2, size=(STRIP_H_DOTS // 2, CONTENT_W_DOTS // 2), dtype=np.uint8)
    return cells_to_dots(cells, 2)


# ---------------------------------------------------------------------------
# page assembly (gen_e004 E004Page pattern on gcp.ProbePage)
# ---------------------------------------------------------------------------

class E006Page(gcp.ProbePage):
    def __init__(self, tag: str) -> None:
        super().__init__()
        self.tag = tag
        self.doc = PSDoc(hw_dpi=HW_DPI,
                         title=f"paper-store exp006.0 loop-{tag} LAY=1 J={JOBID[tag]}",
                         guard_setpagedevice=True)
        self._cmyk_emits: list[tuple[str, dict[str, np.ndarray], int, int]] = []

    def _save_gt(self, name: str, bits: np.ndarray) -> str:
        GT.mkdir(parents=True, exist_ok=True)
        rel = f"e006_gt/{name.replace('/', '__')}.npy"
        if rel in self._gt_files:
            raise AssertionError(f"ground-truth filename collision: {rel}")
        self._gt_files.add(rel)
        np.save(OUT / rel, bits.astype(np.uint8))
        return rel

    def patch_cmyk(self, name: str, planes: dict[str, np.ndarray], x_mm: float,
                   y_mm: float, kind: str, params: dict | None = None,
                   save_gt: bool = True, clearance_mm: float = 1.5) -> None:
        """Screened composite via put_cmyk_bitmap; streams after all masks."""
        x, y = mm(x_mm), mm(y_mm)
        (h, w), = {a.shape for a in planes.values()}
        self._occupy(name, x, y, w, h, clearance_mm)
        self._cmyk_emits.append((name, dict(planes), x, y))
        base = {"emission": "cmyk_image"}
        for p, bits in planes.items():
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind,
                                 "planes": [p], "x_dots": x, "y_dots": y,
                                 "w_dots": int(w), "h_dots": int(h),
                                 "params": {**base, **(params or {})},
                                 "gt": gt, "composite_of": name})

    # emission order: labels, ALL imagemask content, cmyk composites, sentinel
    def emit(self) -> None:
        d = self.doc
        d.begin_page()
        for text, x, yb, size in self._label_args:
            d.put_label(text, x, yb, CMYK["K"], size_pt=size)
        d.put_raw(["% ==== BLOCK 1: single-plane mask content"
                   " (bit-faithful clean path) ===="])
        for name, mode, payload, x, y in self._emits:
            assert mode == "mask", f"unexpected emission mode {mode!r}"
            bits, plane = payload
            d.put_bitmap(bits, x, y, CMYK[plane])
        d.put_raw(["% ==== BLOCK 2: put_cmyk_bitmap composites"
                   " (screened path) ===="])
        for name, planes, x, y in self._cmyk_emits:
            d.put_raw([f"% ---- {name} cmyk-image ----"])
            d.put_cmyk_bitmap(planes, x, y)
        d.put_raw(sentinel_lines(self.tag))
        d.end_page()


def sentinel_lines(tag: str) -> list[str]:
    return [
        "% ---- END sentinel: LAST element in the stream ----",
        "mark { initmatrix 0 0 0 1 setcmykcolor",
        f"  {pt(18.0):.2f} {A4_PT[1] - pt(289.0):.2f} {pt(2.5):.2f} {pt(2.5):.2f} rectfill",
        "  /Helvetica findfont 6 scalefont setfont",
        f"  {pt(22.5):.2f} {A4_PT[1] - pt(289.2):.2f} moveto"
        f" (END {JOBID[tag]} exp006 {tag}) show }} stopped cleartomark",
    ]


def build_header(pg: E006Page, tag: str) -> None:
    band_desc = ("bands 0-9 B1 c2-K | 10-12 RLL-i2w3 | 13-15 probes" if tag == "bw"
                 else "bands 0-15 7-state CMY alphabet c3 (0,7,15 training)")
    scan = "1200dpi grey" if tag == "bw" else "1200dpi color"
    pg.label(f"paper-store exp006.0 LOOP-{tag.upper()} LAY=1 J={JOBID[tag]} "
             f"R0={HW_DPI}x{HW_DPI}dpi 16 bands + canary, pitch 15.24mm",
             16.0, 9.5, size_pt=7.0)
    pg.label(f"S={SEED.decode()}  regen: gen_e006.py (byte-identical) | "
             f"{band_desc}", 16.0, 13.5, size_pt=5.0)
    pg.label(f"print: raw path only, ONE sheet | scan: {scan}, enhancements OFF"
             " | landmarks: sync strips + chiral corners (no plus lattice)",
             16.0, 17.0, size_pt=5.0)


def build_corners(pg: E006Page) -> None:
    for tag, n_sat, inward, cx, cy in (("tl", 1, (1, 1), 10.0, 10.0),
                                       ("tr", 2, (1, -1), 200.0, 10.0),
                                       ("br", 3, (-1, -1), 200.0, 288.0),
                                       ("bl", 4, (-1, 1), 10.0, 288.0)):
        pg.patch_single(f"corner_{tag}", gen_calpage.corner_mark(n_sat, inward),
                        cx - 61 * 25.4 / HW_DPI, cy - 61 * 25.4 / HW_DPI, "K",
                        "corner_mark",
                        {"satellites": n_sat, "inward": list(inward),
                         "arm_dots": 60, "width_dots": 3,
                         "cx_dots": mm(cx), "cy_dots": mm(cy)},
                        clearance_mm=0.5)


def build_strips(pg: E006Page, tag: str) -> list[dict]:
    entries = []
    for i in range(N_DATA_BANDS + 1):
        name = f"{tag}/strip{i:02d}"
        pg.patch_single(name, sync_strip_bits(tag, i), as_mm(X0_DOTS),
                        as_mm(strip_y(i)), "K", "sync_strip",
                        {"cell_dots": 2, "rows_cells": STRIP_H_DOTS // 2,
                         "cols_cells": CONTENT_W_DOTS // 2, "band": i},
                        save_gt=True, clearance_mm=0.0)
        entries.append({"name": name, "y_dots": strip_y(i)})
    return entries


def build_bw_payloads(pg: E006Page) -> list[dict]:
    bands: list[dict] = []
    for i in range(10):                       # B1: incumbent c2 encoding fields
        name = f"bw/band{i:02d}"
        bits = encoding_patch_rect(2, CONTENT_W_DOTS, PAYLOAD_H_DOTS,
                                   f"bw/band{i}".encode())
        params = {"cell_dots": 2, "pilot_block": 6, "pilot_period": 64, "band": i}
        pg.patch_single(name, bits, as_mm(X0_DOTS), as_mm(payload_y(i)), "K",
                        "encoding_patch", params, save_gt=True, clearance_mm=0.0)
        bands.append({"band": i, "name": name, "kind": "encoding_patch",
                      "y_dots": payload_y(i), "x_dots": X0_DOTS,
                      "w_dots": CONTENT_W_DOTS, "h_dots": PAYLOAD_H_DOTS,
                      "params": params})
    for i in range(10, 13):                   # B2: RLL i2w3 free-form fields
        name = f"bw/rll{i}"
        bits, stats = constrained_field_rect(PAYLOAD_H_DOTS, CONTENT_W_DOTS,
                                             2, 3, f"bw/rll{i}".encode())
        params = {**stats, "band": i}
        pg.patch_single(name, bits, as_mm(X0_DOTS), as_mm(payload_y(i)), "K",
                        "constrained_field", params, save_gt=True,
                        clearance_mm=0.0)
        bands.append({"band": i, "name": name, "kind": "constrained_field",
                      "y_dots": payload_y(i), "x_dots": X0_DOTS,
                      "w_dots": CONTENT_W_DOTS, "h_dots": PAYLOAD_H_DOTS,
                      "params": params})

    # probe bands 13-15: side-by-side patches, >= 2 mm gaps, 354 dots tall
    y13 = payload_y(13)
    bits, stats = constrained_field_rect(PAYLOAD_H_DOTS, mm(40.0), 3, 3,
                                         b"bw/probe/i3w3")
    pg.patch_single("bw/i3w3", bits, as_mm(X0_DOTS), as_mm(y13), "K",
                    "constrained_field", {**stats, "band": 13, "probe": "i3w3"},
                    save_gt=True, clearance_mm=0.0)
    f75 = fill75_patch_rect(mm(40.0), PAYLOAD_H_DOTS, b"bw/probe/fill75")
    pg.patch_single("bw/fill75", f75, 58.0, as_mm(y13), "K",
                    "encoding_patch_fill75",
                    {"cell_dots": 2, "pilot_block": 6, "pilot_period": 64,
                     "ink_cell_fill": 0.75,
                     "dropped_corner": "(cell_x+cell_y)%4 over TL,TR,BR,BL",
                     "band": 13, "probe": "fill75"},
                    save_gt=True, clearance_mm=0.0)
    pg.label("probes b13: i3w3 40mm | fill75 c2 40mm", 102.0, 226.0)

    y14 = payload_y(14)
    for nm, cw, ch, x in (("bw/aniso_w2h3", 2, 3, as_mm(X0_DOTS)),
                          ("bw/aniso_w3h2", 3, 2, 42.0)):
        a = aniso_cell_field(mm(25.0), PAYLOAD_H_DOTS, cw, ch, nm.encode())
        pg.patch_single(nm, a, x, as_mm(y14), "K", "aniso_cell_field",
                        {"cell_w_dots": cw, "cell_h_dots": ch, "p": 0.5,
                         "band": 14, "probe": "aniso"},
                        save_gt=True, clearance_mm=0.0)
    pg.label("probes b14: aniso cells 2x3 | 3x2 (50%, 25mm)", 70.0, 241.0)

    y15 = payload_y(15)
    for nm, cell, x in (("bw/grey_c3", 3, as_mm(X0_DOTS)),
                        ("bw/grey_c4", 4, 37.0)):
        lv, dots = grey_level_field(mm(20.0), PAYLOAD_H_DOTS, cell, nm.encode())
        rel = pg._save_gt(f"{nm}_levels", lv)
        pg.patch_single(nm, dots, x, as_mm(y15), "K", "grey3_field",
                        {"cell_dots": cell, "n_levels": 3,
                         "bar": f"{cell}x2 vertical, left-aligned",
                         "levels_gt": rel, "band": 15, "probe": "grey3"},
                        save_gt=True, clearance_mm=0.0)
    pg.label("probes b15: grey3 c3 | c4 (0 / 2-dot bar / full, 20mm)",
             60.0, 256.0)

    probe_patches = {13: ["bw/i3w3", "bw/fill75"],
                     14: ["bw/aniso_w2h3", "bw/aniso_w3h2"],
                     15: ["bw/grey_c3", "bw/grey_c4"]}
    for i in (13, 14, 15):
        bands.append({"band": i, "name": f"bw/probe{i}", "kind": "probe",
                      "y_dots": payload_y(i), "x_dots": X0_DOTS,
                      "w_dots": CONTENT_W_DOTS, "h_dots": PAYLOAD_H_DOTS,
                      "params": {"patches": probe_patches[i]}})
    return bands


def build_c_payloads(pg: E006Page) -> list[dict]:
    bands: list[dict] = []
    for i in range(N_DATA_BANDS):
        name = f"c/band{i:02d}"
        st, planes = uniform_state_field(CONTENT_W_DOTS, PAYLOAD_H_DOTS,
                                         A3_CELL_DOTS, STATES7,
                                         f"c/band{i}".encode(), MIN_PER_STATE_A3)
        rel = pg._save_gt(f"{name}_states", st)
        params = {"cell_dots": A3_CELL_DOTS, "n_states": 7,
                  "state_names": list(STATES7), "states_gt": rel, "band": i}
        if i in (0, 7, 15):
            params["purpose"] = "training"   # identical construction, flag only
        pg.patch_cmyk(name, planes, as_mm(X0_DOTS), as_mm(payload_y(i)),
                      "state_field", params, clearance_mm=0.0)
        bands.append({"band": i, "name": name, "kind": "state_field",
                      "y_dots": payload_y(i), "x_dots": X0_DOTS,
                      "w_dots": CONTENT_W_DOTS, "h_dots": PAYLOAD_H_DOTS,
                      "params": params})
    return bands


def build_canary(pg: E006Page, tag: str) -> dict:
    """One canary band after band 15: B1 c2 + i2w3 fields (40x12 mm), four
    6x6 mm K/C/M/Y solids (single-plane clean masks on BOTH pages), labelled
    paper gap."""
    y_mm = as_mm(payload_y(CANARY_BAND) + 10)   # 0.42 mm below the strip
    b1 = encoding_patch_rect(2, mm(40.0), mm(12.0), f"canary/{tag}/b1".encode())
    pg.patch_single(f"{tag}/canary_b1", b1, 14.0, y_mm, "K",
                    "canary_encoding_patch",
                    {"cell_dots": 2, "pilot_block": 6, "pilot_period": 64},
                    save_gt=True, clearance_mm=0.0)
    rll, stats = constrained_field_rect(mm(12.0), mm(40.0), 2, 3,
                                        f"canary/{tag}/rll".encode())
    pg.patch_single(f"{tag}/canary_rll", rll, 58.0, y_mm, "K",
                    "canary_constrained_field", stats, save_gt=True,
                    clearance_mm=0.0)
    for j, p in enumerate("KCMY"):
        pg.patch_single(f"{tag}/canary_solid_{p}",
                        np.ones((mm(6.0), mm(6.0)), np.uint8),
                        104.0 + 8.0 * j, y_mm, p, "canary_solid",
                        {"emission": "imagemask_single"}, save_gt=False,
                        clearance_mm=0.0)
    pg.rect_entry(f"{tag}/canary_gap", 140.0, y_mm, 30.0, 12.0, "canary_gap",
                  {"purpose": "labelled paper gap (blank reference)"},
                  clearance_mm=0.0)
    pg.label("canary: B1 c2 | i2w3 | K C M Y solids | paper gap", 14.0, 278.3)
    return {"band": CANARY_BAND, "name": f"{tag}/canary", "kind": "canary",
            "y_dots": payload_y(CANARY_BAND), "x_dots": X0_DOTS,
            "w_dots": CONTENT_W_DOTS, "h_dots": PAYLOAD_H_DOTS,
            "params": {"patches": [f"{tag}/canary_b1", f"{tag}/canary_rll",
                                   f"{tag}/canary_solid_K", f"{tag}/canary_solid_C",
                                   f"{tag}/canary_solid_M", f"{tag}/canary_solid_Y",
                                   f"{tag}/canary_gap"]}}


def build_refs(pg: E006Page) -> None:
    """E004 refs row: clean-path solids + cmyk-path solids, y 280.0-284.8."""
    solid = np.ones((mm(4.8), mm(8.0)), np.uint8)
    for i, p in enumerate("KCMY"):
        pg.patch_single(f"ref_clean_{p}", solid, 14.0 + 10.0 * i, 280.0, p,
                        "ref_solid", {"emission": "imagemask_single"},
                        save_gt=False, clearance_mm=1.0)
    for i, combo in enumerate(("C", "M", "Y", "CM", "CY", "MY")):
        planes = {p: solid for p in combo}
        pg.patch_cmyk(f"ref_cmyk_{combo}", planes, 58.0 + 10.0 * i, 280.0,
                      "ref_solid_cmyk", save_gt=False, clearance_mm=1.0)
    pg.label("refs: clean K C M Y | cmyk C M Y CM CY MY | paper = gaps",
             120.0, 283.0)


def build_page(tag: str) -> tuple[E006Page, list[dict]]:
    pg = E006Page(tag)
    build_header(pg, tag)
    build_corners(pg)
    strips = build_strips(pg, tag)
    payloads = build_bw_payloads(pg) if tag == "bw" else build_c_payloads(pg)
    bands = payloads + [build_canary(pg, tag)]
    build_refs(pg)
    pg.rect_entry("end_sentinel", 18.0, 286.5, 42.0, 2.8, "end_sentinel",
                  {"text": f"END {JOBID[tag]} exp006 {tag}"})
    pg.assert_labels_clear()
    assert len(strips) == N_DATA_BANDS + 1 and len(bands) == N_DATA_BANDS + 1
    for b, s in zip(bands, strips):
        assert s["y_dots"] == strip_y(b["band"]), (b["name"], s["name"])
        b["strip"] = s["name"]
        b["strip_y_dots"] = s["y_dots"]
    return pg, bands


def content_areas_mm2(pg: E006Page) -> dict[str, float]:
    dot2 = (25.4 / HW_DPI) ** 2
    areas: dict[str, float] = {}
    seen: set[str] = set()
    for p in pg.patches + pg.infra:
        key = p.get("composite_of", p["name"])
        if key in seen:
            continue
        seen.add(key)
        areas[p["kind"]] = areas.get(p["kind"], 0.0) + p["w_dots"] * p["h_dots"] * dot2
    return {k: round(v, 1) for k, v in sorted(areas.items())}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GT.mkdir(parents=True, exist_ok=True)
    for tag in PAGES:
        pg, bands = build_page(tag)
        pg.emit()
        ps = pg.doc.render()
        assert "%%Pages: 1" in ps and ps.count("%%Page:") == 1, "must be ONE page"
        i_cmyk = ps.index("% ==== BLOCK 2")
        assert ps.rindex("imagemask") < i_cmyk, "masks must stream before cmyk"
        i_sent = ps.index("% ---- END sentinel")
        assert i_sent > i_cmyk and "imagemask" not in ps[i_sent:] \
            and ">> image" not in ps[i_sent:], "END sentinel must be last"
        assert len(ps) <= PS_BUDGET_BYTES, f"ps {len(ps)/1e6:.1f} MB > budget"
        (OUT / f"e006{tag}.ps").write_text(ps)
        sha = hashlib.sha256(ps.encode()).hexdigest()
        areas = content_areas_mm2(pg)
        manifest = {
            "experiment": "006-loop-pages",
            "artifact": f"e006{tag}",
            "run": "006.0",
            "page": tag,
            "layout_version": LAYOUT_VERSION,
            "seed": SEED.decode(),
            "jobid": JOBID[tag],
            "hw_dpi": HW_DPI,
            "ps_file": f"e006{tag}.ps",
            "ps_sha256": sha,
            "ps_bytes": len(ps),
            "print_command": f"../../scripts/print_plane.sh build/e006{tag}.ps",
            "content_bounds_mm": [X_MIN, Y_MIN, X_MAX, Y_MAX],
            "band_geometry": {"x0_dots": X0_DOTS,
                              "content_w_dots": CONTENT_W_DOTS,
                              "y0_dots": Y0_DOTS,
                              "strip_pitch_dots": STRIP_PITCH_DOTS,
                              "strip_h_dots": STRIP_H_DOTS,
                              "payload_h_dots": PAYLOAD_H_DOTS,
                              "n_data_bands": N_DATA_BANDS,
                              "canary_band": CANARY_BAND},
            "landmarks": "sync strips + chiral corner marks (no plus lattice)",
            "stream_order": "labels, ALL single-plane imagemask content, "
                            "put_cmyk_bitmap composites, END sentinel last",
            "bands": bands,
            "content_area_mm2": areas,
            "patches": pg.patches,
            "infrastructure": pg.infra,
            "labels": pg.labels,
        }
        (OUT / f"e006{tag}_manifest.json").write_text(json.dumps(manifest, indent=1))
        print(f"wrote build/e006{tag}.ps ({len(ps)/1e6:.2f} MB, "
              f"{len(pg.patches)} patches)")
        print(f"  areas mm2: {areas}")
        print(f"  sha256 {sha}")


if __name__ == "__main__":
    main()
