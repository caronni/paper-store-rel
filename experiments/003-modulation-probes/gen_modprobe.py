#!/usr/bin/env python
"""Experiment 003.0 — modulation probes sheet (print side).

ONE A4 page, four blocks, all feeding the modulation layer (DESIGN.md §4)
with measured channel facts from 001/002:

Block K — 2-D run-length-constrained K fields (single-plane imagemask, the
  bit-faithful path). K1 ink-run>=2 & white-run>=3 (both axes), K2 i2/w2,
  K3 i2/w4, each 22x22 mm, plus c2/c3 solid-cell encode incumbents (14x14 mm,
  gen_gridtest encoding_patch construction) for same-sheet comparison.
  The constrained sampler is row-by-row: each row drawn UNIFORMLY (completion-
  counting DP) from rows satisfying the horizontal constraint AND the vertical
  forcing of unfinished column runs (+ a no-new-run rule near the bottom edge
  so every vertical run completes). Uniform-per-row is NOT the 2-D maxentropic
  measure; delivered entropy is therefore MEASURED, not assumed: the manifest
  records the exact sampler entropy sum(log2 #row-completions)/dots and a
  causal 4-neighbor context-model estimate.

Block M — motif dictionary (K imagemask): 12 micro-feature motifs (ink 2x2,
  2x3, 3x2, domino-H/V = 2x4/4x2, L-tromino and T-tetromino of 2x2-dot blocks;
  white holes 2x2, 2x3, 3x3, 1x3/3x1 slots in a 4-dot solid-ink pad), each
  stamped 132x (>=120) into a 12x12 mm patch of 50% coarse (cell=3) background
  with >=4-dot clearance, seeded jitter +-1 dot. Instance coordinates in the
  manifest -> per-motif survival/response statistics -> trellis branch metrics.

Block D — dot-disjoint multi-plane probes (THE screening-trigger question:
  002.1/002.2 showed overlapping-REGION mask sequences get knocked out AND
  re-screened; does the contone path trigger on region overlap or dot overlap?)
  D1 C/M dot-disjoint interleave ({W,C,M} per cell, cell=3, 18x18 mm) as TWO
  whole-field imagemasks (same rect, overlapping bboxes, ZERO overlapping ink);
  D2 same content as per-cell tiny imagemasks (each cell its own mask object);
  D3 same content via put_cmyk_bitmap (screened control); D4 side-by-side
  C-only / M-only halves (disjoint rects, clean-path control); D5 mixture-free
  5-state {W,C,M,Y,K} uniform cell=3 20x20 mm as 4 whole-field imagemasks;
  D6 identical content via put_cmyk_bitmap.

Block S — white-void subchannel: S1 constrained K field (i2/w3) 20x20 mm BARE;
  S2 the IDENTICAL K field + C subchannel (2x2 C marks centered in 4x4-white
  eligible voids = 2x2 mark with >=1-dot white clearance to K ink; eligible
  sites = deterministic greedy raster independent set, ~50% filled by seeded
  rng); S3 colored-pilot demo: K 50% cell=3 field, pilot-site cells
  (paperholo.pilots.pilot_sites on the 157x157 cell grid, ~2.8% of cells,
  border sites excluded) replaced by enforced white voids (the 3x3-dot cell
  plus a 1-dot L-margin -> a 4x4-dot white window) each holding a 2x2 C mark.

Registration reuses the EXACT chiral corner-mark + plus-mark geometry of
gen_calpage.py (builders imported — single source, byte-identical) and the
gen_composite_probe.ProbePage occupancy/label machinery (subclassed), so
cal_core registers this page by manifest swap:

    mf = cal_core.load_manifest(EXP003 / "build" / "modprobe_manifest.json")

Stream order (error containment + path separation): labels, then ALL
single-plane imagemask content (clean path), then the put_cmyk_bitmap
controls (D3, D6), then the END sentinel LAST. Nothing exotic — no
Separation/DeviceN (002.2 closed that question). psgen is NOT modified.

Outputs: build/modprobe.ps, build/modprobe_manifest.json, build/modprobe_gt/
*.npy. Everything regenerates byte-identically from SEED (sha256 gates
reuse). Print ONLY via the raw path after user confirmation in-session
(.claude/rules/hardware.md); protocol: experiments/003-modulation-probes.md.
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
for p in (str(_HERE), str(_EXP002)):
    if p not in sys.path:
        sys.path.insert(0, p)

# byte-identical mark builders (gen_calpage) + occupancy/label machinery
# (gen_composite_probe.ProbePage — subclassed below; attribution: exp 002.0/002.1)
import gen_calpage  # noqa: E402
import gen_composite_probe as gcp  # noqa: E402

SEED = b"paper-store/exp003-modprobe"
LAYOUT_VERSION = 1
JOBID = hashlib.sha256(SEED + b"/layout1").hexdigest()[:8]
HW_DPI = 600
OUT = _HERE / "build"
GT = OUT / "modprobe_gt"

# content bounds identical to the calibration page (6 mm margins on A4)
X_MIN, X_MAX, Y_MIN, Y_MAX = 6.0, 204.0, 6.0, 291.0

CELL_DOTS = 3
MIN_CELLS_PER_STATE = 1700   # symmetric per-state statistics floor (002.2)
D2_PS_BUDGET_BYTES = 8_000_000  # per task spec: subsample D2 if exceeded


def mm(v: float) -> int:
    return round(v / 25.4 * HW_DPI)


def pt(v_mm: float) -> float:
    return v_mm / 25.4 * 72.0


# ---------------------------------------------------------------------------
# 2-D run-length-constrained field sampler (Block K / S)
# ---------------------------------------------------------------------------

def _sample_row(prev_forced: np.ndarray, min_white: int, min_ink: int,
                gen: np.random.Generator) -> tuple[np.ndarray, float]:
    """One row, uniform over {rows whose maximal runs satisfy white>=min_white,
    ink>=min_ink (border runs included) AND matching the forced positions}.

    forced[i] in {-1 free, 0 white, 1 ink}. Returns (bits, log2 #valid rows).
    Completion counts stay < 2**w <= float max for w <= 900 (no rescaling).
    """
    w = int(prev_forced.size)
    assert w <= 900, "row DP float counts would overflow"
    nw, ni = min_white, min_ink
    ns = nw + ni
    # state k = run ending at previous position: k<nw -> white run k+1 (capped
    # at nw); k>=nw -> ink run k-nw+1 (capped at ni). cont[k] = state after
    # extending; white cap flips to (ink,1)=nw, ink cap flips to (white,1)=0.
    cont = [min(r + 1, nw) - 1 for r in range(1, nw + 1)] + \
           [nw + min(r + 1, ni) - 1 for r in range(1, ni + 1)]
    wcap, icap = nw - 1, ns - 1
    forced = prev_forced.tolist()
    # backward DP: N[i][k] = #completions of positions i..w-1 given state k
    N: list[list[float]] = [[0.0] * ns for _ in range(w + 1)]
    N[w][wcap] = 1.0
    N[w][icap] = 1.0
    for i in range(w - 1, 0, -1):
        prev = N[i + 1]
        f = forced[i]
        if f < 0:
            cur = [prev[cont[k]] for k in range(ns)]
            cur[wcap] += prev[nw]   # white cap may flip to ink run 1
            cur[icap] += prev[0]    # ink cap may flip to white run 1
        elif f == 0:
            cur = [prev[cont[k]] if k < nw else 0.0 for k in range(ns)]
            cur[icap] = prev[0]
        else:
            cur = [prev[cont[k]] if k >= nw else 0.0 for k in range(ns)]
            cur[wcap] = prev[nw]
        N[i] = cur
    # position 0 has no prior state: choosing bit b starts run (b, 1)
    w_white = N[1][0] if forced[0] in (-1, 0) else 0.0
    w_ink = N[1][nw] if forced[0] in (-1, 1) else 0.0
    total = w_white + w_ink
    assert total > 0.0, "row DP dead end (copy-previous-row invariant violated)"
    bits = np.zeros(w, dtype=np.uint8)
    if w_white > 0.0 and w_ink > 0.0:
        b = 1 if gen.random() * total < w_ink else 0
    else:
        b = 1 if w_ink > 0.0 else 0
    bits[0] = b
    state = nw if b else 0
    for i in range(1, w):
        prev = N[i + 1]
        f = forced[i]
        c = 1 if state >= nw else 0
        w_cont = prev[cont[state]] if f in (-1, c) else 0.0
        w_flip = 0.0
        if f in (-1, 1 - c):
            if state == wcap:
                w_flip = prev[nw]
            elif state == icap:
                w_flip = prev[0]
        if w_cont > 0.0 and w_flip > 0.0:
            flip = gen.random() * (w_cont + w_flip) < w_flip
        else:
            flip = w_flip > 0.0
        if flip:
            state = 0 if c else nw
            bits[i] = 1 - c
        else:
            state = cont[state]
            bits[i] = c
    return bits, math.log2(total)


def constrained_field(n_dots: int, min_ink: int, min_white: int,
                      label: bytes) -> tuple[np.ndarray, dict]:
    """2-D RLL field: every maximal run of ink >= min_ink and of white >=
    min_white, BOTH axes, border runs included (asserted). Deterministic in
    (SEED, label). Returns (bits, stats dict for the manifest)."""
    gen = rng(SEED, label)
    minr = np.array([min_white, min_ink], dtype=np.int64)
    a = np.zeros((n_dots, n_dots), dtype=np.uint8)
    col_color = np.zeros(n_dots, dtype=np.int64)
    col_run = np.zeros(n_dots, dtype=np.int64)
    log2_total = 0.0
    for y in range(n_dots):
        if y == 0:
            forced = np.full(n_dots, -1, dtype=np.int64)
        else:
            # continue while the column run is unfinished, or when a flip could
            # no longer complete its minimum run before the bottom edge
            must_cont = (col_run < minr[col_color]) | \
                        (n_dots - y < minr[1 - col_color])
            forced = np.where(must_cont, col_color, -1)
        bits, l2 = _sample_row(forced, min_white, min_ink, gen)
        log2_total += l2
        a[y] = bits
        if y == 0:
            col_color = bits.astype(np.int64)
            col_run = np.ones(n_dots, dtype=np.int64)
        else:
            same = bits.astype(np.int64) == col_color
            col_run = np.where(same, col_run + 1, 1)
            col_color = bits.astype(np.int64)
    assert_run_lengths(a, min_ink, min_white)
    stats = {
        "min_ink_run_dots": min_ink,
        "min_white_run_dots": min_white,
        "sampler": "row-DP, uniform per row given vertical forcing "
                   "(approximate 2-D maxentropic; entropy measured, not assumed)",
        "sampler_entropy_bits_per_dot": round(log2_total / (n_dots * n_dots), 6),
        "ctx_model_entropy_bits_per_dot": round(context_entropy_bits(a), 6),
        "ink_fraction": round(float(a.mean()), 6),
    }
    return a, stats


def assert_run_lengths(a: np.ndarray, min_ink: int, min_white: int) -> None:
    """Every maximal run in every row AND column (borders included) obeys
    ink >= min_ink, white >= min_white."""
    for axis_name, b in (("rows", a), ("cols", a.T)):
        for i, line in enumerate(b):
            change = np.flatnonzero(np.diff(line.astype(np.int8))) + 1
            starts = np.concatenate(([0], change))
            ends = np.concatenate((change, [line.size]))
            vals, lens = line[starts], ends - starts
            bad_i = lens[vals == 1] < min_ink
            bad_w = lens[vals == 0] < min_white
            assert not bad_i.any() and not bad_w.any(), \
                f"run-length violation in {axis_name}[{i}]"


def context_entropy_bits(a: np.ndarray) -> float:
    """Empirical H(bit | W, NW, N, NE causal context), bits/dot (interior)."""
    x = a.astype(np.int64)
    b = x[1:, 1:-1]
    ctx = x[1:, :-2] * 8 + x[:-1, :-2] * 4 + x[:-1, 1:-1] * 2 + x[:-1, 2:]
    counts = np.bincount((ctx * 2 + b).ravel(), minlength=32).reshape(16, 2)
    n = counts.sum()
    h = 0.0
    for c0, c1 in counts:
        tot = c0 + c1
        if tot == 0:
            continue
        for c in (c0, c1):
            if c:
                h -= (c / n) * math.log2(c / tot)
    return h


# ---------------------------------------------------------------------------
# Block K incumbents — encoding_patch construction (attribution: gen_gridtest,
# experiment 001.2 / gen_calpage 002.0; re-seeded from THIS experiment's SEED
# per the determinism convention)
# ---------------------------------------------------------------------------

def encoding_patch(cell: int, size_dots: int, label: bytes) -> np.ndarray:
    n = size_dots // cell
    data = rng(SEED, label + b"/data").integers(0, 2, size=(n, n), dtype=np.uint8)
    pv = rng(SEED, label + b"/pilot-values").integers(0, 2, size=(n, n), dtype=np.uint8)
    m = pilot_sites((n, n), SEED)
    data[m] = pv[m]
    return cells_to_dots(data, cell)


# ---------------------------------------------------------------------------
# Block M — motif dictionary
# ---------------------------------------------------------------------------

def _blocks2(pattern: list[list[int]]) -> np.ndarray:
    """Polyomino of 2x2-dot blocks (min reliable ink feature, 001/002)."""
    return np.kron(np.array(pattern, dtype=np.uint8), np.ones((2, 2), np.uint8))


INK_MOTIFS: dict[str, np.ndarray] = {
    "ink_2x2": np.ones((2, 2), np.uint8),
    "ink_2x3": np.ones((2, 3), np.uint8),
    "ink_3x2": np.ones((3, 2), np.uint8),
    "ink_domino_h": np.ones((2, 4), np.uint8),
    "ink_domino_v": np.ones((4, 2), np.uint8),
    "ink_l_tromino": _blocks2([[1, 0], [1, 1]]),
    "ink_t_tetromino": _blocks2([[1, 1, 1], [0, 1, 0]]),
}
WHITE_MOTIFS: dict[str, tuple[int, int]] = {   # hole (h, w) in a solid pad
    "white_2x2": (2, 2),
    "white_2x3": (2, 3),
    "white_3x3": (3, 3),
    "white_slot_h": (1, 3),
    "white_slot_v": (3, 1),
}
MOTIF_ORDER = list(INK_MOTIFS) + list(WHITE_MOTIFS)
MOTIF_PATCH_MM = 12.0
MOTIF_PITCH_DOTS = 20      # instance lattice pitch (2 x 10-dot cells)
MOTIF_JITTER_DOTS = 1
MOTIF_CLEAR_DOTS = 4       # background clearance around motif / pad
MOTIF_PAD_INK_DOTS = 4     # solid ink context around white motifs
MOTIF_INSTANCES = 132      # >= 120 per task spec


def motif_patch(name: str) -> tuple[np.ndarray, dict]:
    """12x12 mm K patch: 50% cell=3 background, MOTIF_INSTANCES stamps of one
    motif on a jittered 20-dot lattice, each cleared to >=MOTIF_CLEAR_DOTS."""
    n = mm(MOTIF_PATCH_MM)                       # 283
    nb = n // CELL_DOTS                          # 94 background cells
    canvas = np.zeros((n, n), dtype=np.uint8)
    bg = rng(SEED, b"m/bg/" + name.encode()).integers(0, 2, size=(nb, nb),
                                                      dtype=np.uint8)
    canvas[: nb * CELL_DOTS, : nb * CELL_DOTS] = cells_to_dots(bg, CELL_DOTS)
    gen = rng(SEED, b"m/sites/" + name.encode())
    n_lat = 14                                   # 14x14 lattice, centers 15+20k
    jit = gen.integers(-MOTIF_JITTER_DOTS, MOTIF_JITTER_DOTS + 1,
                       size=(n_lat * n_lat, 2))
    chosen = np.sort(gen.permutation(n_lat * n_lat)[:MOTIF_INSTANCES])
    is_ink = name in INK_MOTIFS
    stamp = INK_MOTIFS[name] if is_ink else None
    hole = WHITE_MOTIFS.get(name)
    instances: list[list[int]] = []
    stamps: list[tuple[int, int, int, int]] = []  # cleared+verified regions
    for k in chosen.tolist():
        ky, kx = divmod(k, n_lat)
        cy = 15 + MOTIF_PITCH_DOTS * ky + int(jit[k, 0])
        cx = 15 + MOTIF_PITCH_DOTS * kx + int(jit[k, 1])
        if is_ink:
            h, w = stamp.shape
            y0, x0 = cy - h // 2, cx - w // 2
            gy0, gx0 = y0 - MOTIF_CLEAR_DOTS, x0 - MOTIF_CLEAR_DOTS
            gy1, gx1 = y0 + h + MOTIF_CLEAR_DOTS, x0 + w + MOTIF_CLEAR_DOTS
            canvas[max(0, gy0): gy1, max(0, gx0): gx1] = 0
            canvas[y0: y0 + h, x0: x0 + w] |= stamp
        else:
            hh, hw = hole
            ph, pw = hh + 2 * MOTIF_PAD_INK_DOTS, hw + 2 * MOTIF_PAD_INK_DOTS
            py0, px0 = cy - ph // 2, cx - pw // 2
            y0, x0 = py0 + MOTIF_PAD_INK_DOTS, px0 + MOTIF_PAD_INK_DOTS
            gy0, gx0 = py0 - MOTIF_CLEAR_DOTS, px0 - MOTIF_CLEAR_DOTS
            gy1, gx1 = py0 + ph + MOTIF_CLEAR_DOTS, px0 + pw + MOTIF_CLEAR_DOTS
            assert py0 >= 0 and px0 >= 0 and py0 + ph <= n and px0 + pw <= n, \
                f"{name}: pad out of patch at site {k}"
            canvas[max(0, gy0): gy1, max(0, gx0): gx1] = 0
            canvas[py0: py0 + ph, px0: px0 + pw] = 1
            canvas[y0: y0 + hh, x0: x0 + hw] = 0
        instances.append([int(y0), int(x0)])
        stamps.append((gy0, gx0, gy1, gx1))
    # verify: each instance's grown window holds ONLY its own stamp (clearance
    # to background AND to every other instance, Chebyshev >= MOTIF_CLEAR_DOTS)
    for (y0, x0), (gy0, gx0, gy1, gx1) in zip(instances, stamps):
        win = canvas[max(0, gy0): gy1, max(0, gx0): gx1]
        expect = np.zeros_like(win)
        if is_ink:
            h, w = stamp.shape
            expect[y0 - max(0, gy0): y0 - max(0, gy0) + h,
                   x0 - max(0, gx0): x0 - max(0, gx0) + w] = stamp
        else:
            hh, hw = hole
            ph, pw = hh + 2 * MOTIF_PAD_INK_DOTS, hw + 2 * MOTIF_PAD_INK_DOTS
            py0, px0 = y0 - MOTIF_PAD_INK_DOTS, x0 - MOTIF_PAD_INK_DOTS
            expect[py0 - max(0, gy0): py0 - max(0, gy0) + ph,
                   px0 - max(0, gx0): px0 - max(0, gx0) + pw] = 1
            expect[y0 - max(0, gy0): y0 - max(0, gy0) + hh,
                   x0 - max(0, gx0): x0 - max(0, gx0) + hw] = 0
        assert np.array_equal(win, expect), f"{name}: clearance violated at {y0},{x0}"
    params = {
        "motif": name,
        "motif_kind": "ink" if is_ink else "white_hole",
        "motif_shape": (stamp.tolist() if is_ink else None),
        "hole_h_w_dots": (list(hole) if hole else None),
        "pad_ink_dots": (None if is_ink else MOTIF_PAD_INK_DOTS),
        "n_instances": len(instances),
        "instance_origin": "top-left dot of the motif (hole for white), "
                           "patch-relative",
        "instances": instances,
        "clearance_dots": MOTIF_CLEAR_DOTS,
        "lattice_pitch_dots": MOTIF_PITCH_DOTS,
        "jitter_dots": MOTIF_JITTER_DOTS,
        "bg": {"p": 0.5, "cell_dots": CELL_DOTS},
    }
    return canvas, params


# ---------------------------------------------------------------------------
# Block D — dot-disjoint state fields
# ---------------------------------------------------------------------------

def state_field(size_mm: float, states: tuple[str, ...],
                label: bytes) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Per-cell state i.i.d. uniform over `states` (name spells inked plane,
    'W' none — mixture-free by construction: one plane per cell)."""
    n = mm(size_mm) // CELL_DOTS
    st = rng(SEED, label).integers(0, len(states), size=(n, n), dtype=np.uint8)
    counts = np.bincount(st.ravel(), minlength=len(states))
    assert counts.min() >= MIN_CELLS_PER_STATE, \
        f"{label!r}: min {int(counts.min())} cells/state < {MIN_CELLS_PER_STATE}"
    planes = {p: cells_to_dots((st == i).astype(np.uint8), CELL_DOTS)
              for i, p in enumerate(states) if p != "W"}
    return st, planes


# ---------------------------------------------------------------------------
# Block S — white-void C subchannel
# ---------------------------------------------------------------------------

def eligible_void_sites(field: np.ndarray) -> list[tuple[int, int]]:
    """Deterministic greedy raster-order independent set of 4x4 all-white
    windows (window = 2x2 C mark + 1-dot white ring); accepted origins are
    pairwise Chebyshev >= 3 apart, so marks never touch."""
    n = field.shape[0]
    c = np.zeros((n + 1, n + 1), dtype=np.int64)
    c[1:, 1:] = field.astype(np.int64).cumsum(0).cumsum(1)
    win = c[4:, 4:] - c[:-4, 4:] - c[4:, :-4] + c[:-4, :-4]
    elig = win == 0
    blocked = np.zeros_like(elig)
    sites: list[tuple[int, int]] = []
    for y, x in np.argwhere(elig):
        if blocked[y, x]:
            continue
        sites.append((int(y), int(x)))
        blocked[max(0, y - 2): y + 3, max(0, x - 2): x + 3] = True
    return sites


def c_subchannel_marks(field: np.ndarray, label: bytes) -> tuple[np.ndarray, dict]:
    """~50% of eligible void sites (seeded choice) get a 2x2 C mark."""
    sites = eligible_void_sites(field)
    n_pick = len(sites) // 2
    pick = rng(SEED, label).permutation(len(sites))[:n_pick]
    marks = sorted(sites[i] for i in pick.tolist())
    cbits = np.zeros_like(field)
    for y, x in marks:
        assert int(field[y: y + 4, x: x + 4].sum()) == 0, "void not white"
        cbits[y + 1: y + 3, x + 1: x + 3] = 1
    assert int(cbits.sum()) == 4 * n_pick, "C marks overlap"
    params = {
        "mark_dots": [2, 2],
        "white_ring_dots": 1,
        "site_rule": "4x4 all-white window; greedy raster independent set "
                     "(origins Chebyshev >= 3); ~50% filled by seeded rng",
        "n_eligible_sites": len(sites),
        "n_marks": n_pick,
        "fill_fraction_of_eligible": round(n_pick / max(1, len(sites)), 6),
        "mark_origin": "top-left dot of the 2x2 C mark, patch-relative "
                       "(= window origin + [1,1])",
        "marks": [[y + 1, x + 1] for y, x in marks],
    }
    return cbits, params


def pilot_void_field(size_mm: float, label: bytes) -> tuple[np.ndarray, np.ndarray,
                                                            np.ndarray, dict]:
    """S3: 50% cell=3 K field; each interior pilot-site cell (pilot_sites on
    the cell grid) becomes an enforced white void — the 3x3-dot cell plus a
    1-dot L-margin into its right/bottom neighbors (a 4x4-dot white window) —
    holding a 2x2 C mark with a full 1-dot white ring."""
    n_cells = mm(size_mm) // CELL_DOTS
    base = rng(SEED, label).integers(0, 2, size=(n_cells, n_cells), dtype=np.uint8)
    pm = pilot_sites((n_cells, n_cells), SEED)
    pm[0, :] = pm[-1, :] = False
    pm[:, 0] = pm[:, -1] = False
    kbits = cells_to_dots(base, CELL_DOTS)
    cbits = np.zeros_like(kbits)
    sites = [(int(y), int(x)) for y, x in np.argwhere(pm)]
    for ci, cj in sites:
        y0, x0 = CELL_DOTS * ci, CELL_DOTS * cj
        kbits[y0: y0 + 4, x0: x0 + 4] = 0
        cbits[y0 + 1: y0 + 3, x0 + 1: x0 + 3] = 1
    for ci, cj in sites:  # verify the ring survived overlapping voids
        y0, x0 = CELL_DOTS * ci, CELL_DOTS * cj
        assert int(kbits[y0: y0 + 4, x0: x0 + 4].sum()) == 0, "pilot ring inked"
    params = {
        "p": 0.5,
        "cell_dots": CELL_DOTS,
        "pilot_block": 6,
        "pilot_period": 64,
        "void_rule": "pilot-site cell forced white + 1-dot L-margin into "
                     "right/bottom neighbors (4x4-dot white window); border "
                     "pilot sites excluded (stay data cells)",
        "mark_dots": [2, 2],
        "mark_offset_in_window_dots": [1, 1],
        "n_pilot_sites": len(sites),
        "site_fraction_of_cells": round(len(sites) / (n_cells * n_cells), 6),
        "pilot_cells": [[ci, cj] for ci, cj in sites],
        "base_cells_gt": "modprobe_gt/S3_base_cells.npy",
    }
    return kbits, cbits, base, params


# ---------------------------------------------------------------------------
# page assembly: ProbePage machinery reused (occupancy, labels, plus lattice);
# emission overridden for the masks -> cmyk-controls -> END-sentinel order
# ---------------------------------------------------------------------------

class ModprobePage(gcp.ProbePage):
    def __init__(self) -> None:
        super().__init__()
        self.doc = PSDoc(hw_dpi=HW_DPI,
                         title=f"paper-store exp003.0 modprobe LAY=1 J={JOBID}",
                         guard_setpagedevice=True)
        # put_cmyk_bitmap controls stream AFTER all imagemask content
        self._cmyk_emits: list[tuple[str, dict[str, np.ndarray], int, int]] = []

    def _save_gt(self, name: str, bits: np.ndarray) -> str:
        GT.mkdir(parents=True, exist_ok=True)
        rel = f"modprobe_gt/{name.replace('/', '__')}.npy"
        if rel in self._gt_files:
            raise AssertionError(f"ground-truth filename collision: {rel}")
        self._gt_files.add(rel)
        np.save(OUT / rel, bits.astype(np.uint8))
        return rel

    def patch_pair(self, name: str, planes: list[tuple[str, np.ndarray]],
                   x_mm: float, y_mm: float, kind: str, emission: str,
                   params: dict | None = None, save_gt: bool = True,
                   clearance_mm: float = 1.5) -> None:
        """Multi-plane patch as whole-field per-plane imagemasks over ONE rect
        (overlapping bboxes; ink must be dot-disjoint — asserted)."""
        x, y = mm(x_mm), mm(y_mm)
        (h, w), = {b.shape for _, b in planes}
        tot = np.zeros((h, w), dtype=np.int64)
        for _, b in planes:
            tot += b.astype(np.int64)
        assert int(tot.max()) <= 1, f"{name}: planes overlap at dot level"
        self._occupy(name, x, y, w, h, clearance_mm)
        self._emits.append((name, "pair", planes, x, y))
        base = {"emission": emission, "paint_order": [p for p, _ in planes]}
        for p, bits in planes:
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind, "planes": [p],
                                 "x_dots": x, "y_dots": y, "w_dots": int(w),
                                 "h_dots": int(h), "params": {**base, **(params or {})},
                                 "gt": gt, "composite_of": name})

    def patch_cells(self, name: str, st: np.ndarray, states: tuple[str, ...],
                    x_mm: float, y_mm: float, kind: str,
                    params: dict | None = None, save_gt: bool = True,
                    clearance_mm: float = 1.5) -> int:
        """D2: every inked cell emitted as its OWN tiny imagemask object."""
        x, y = mm(x_mm), mm(y_mm)
        nc = st.shape[0]
        w = h = nc * CELL_DOTS
        self._occupy(name, x, y, w, h, clearance_mm)
        self._emits.append((name, "cells", (st.copy(), states), x, y))
        n_objects = int((st != 0).sum())
        base = {"emission": "imagemask_per_cell", "n_objects": n_objects,
                "object_order": "plane-major (C then M), raster within plane",
                **(params or {})}
        for i, p in enumerate(states):
            if p == "W":
                continue
            bits = cells_to_dots((st == i).astype(np.uint8), CELL_DOTS)
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind, "planes": [p],
                                 "x_dots": x, "y_dots": y, "w_dots": int(w),
                                 "h_dots": int(h), "params": dict(base),
                                 "gt": gt, "composite_of": name})
        return n_objects

    def patch_cmyk(self, name: str, planes: dict[str, np.ndarray], x_mm: float,
                   y_mm: float, kind: str, params: dict | None = None,
                   save_gt: bool = True, clearance_mm: float = 1.5) -> None:
        """Screened control via put_cmyk_bitmap; streams after all masks."""
        x, y = mm(x_mm), mm(y_mm)
        (h, w), = {a.shape for a in planes.values()}
        self._occupy(name, x, y, w, h, clearance_mm)
        self._cmyk_emits.append((name, dict(planes), x, y))
        base = {"emission": "cmyk_image"}
        for p, bits in planes.items():
            gt = self._save_gt(f"{name}_{p}", bits) if save_gt else None
            self.patches.append({"name": f"{name}_{p}", "kind": kind, "planes": [p],
                                 "x_dots": x, "y_dots": y, "w_dots": int(w),
                                 "h_dots": int(h), "params": {**base, **(params or {})},
                                 "gt": gt, "composite_of": name})

    # -- emission: labels, ALL imagemask content, cmyk controls, END sentinel --
    def emit(self) -> None:
        d = self.doc
        d.begin_page()
        for text, x, yb, size in self._label_args:
            d.put_label(text, x, yb, CMYK["K"], size_pt=size)
        d.put_raw(["% ==== BLOCK 1: single-plane mask content"
                   " (bit-faithful clean path) ===="])
        ones_cell = np.ones((CELL_DOTS, CELL_DOTS), dtype=np.uint8)
        for name, mode, payload, x, y in self._emits:
            if mode == "mask":
                bits, plane = payload
                d.put_bitmap(bits, x, y, CMYK[plane])
            elif mode == "pair":
                d.put_raw([f"% ---- {name} whole-field mask group ----"])
                for plane, bits in payload:
                    d.put_bitmap(bits, x, y, CMYK[plane])
            elif mode == "cells":
                st, states = payload
                d.put_raw([f"% ---- {name} per-cell masks begin ----"])
                for i, plane in enumerate(states):
                    if plane == "W":
                        continue
                    for cy, cx in np.argwhere(st == i):
                        d.put_bitmap(ones_cell, x + CELL_DOTS * int(cx),
                                     y + CELL_DOTS * int(cy), CMYK[plane])
                d.put_raw([f"% ---- {name} per-cell masks end ----"])
            else:
                raise AssertionError(f"unknown emission mode {mode!r}")
        d.put_raw(["% ==== BLOCK 2: put_cmyk_bitmap controls (screened path) ===="])
        for name, planes, x, y in self._cmyk_emits:
            d.put_raw([f"% ---- {name} cmyk-image ----"])
            d.put_cmyk_bitmap(planes, x, y)
        d.put_raw(sentinel_lines())
        d.end_page()


def sentinel_lines() -> list[str]:
    """END sentinel — the very last element in the stream (stopped-guarded;
    attribution: gen_overlap2, exp 002.2)."""
    return [
        "% ---- END sentinel: LAST element in the stream ----",
        "mark { initmatrix 0 0 0 1 setcmykcolor",
        f"  {pt(18.0):.2f} {A4_PT[1] - pt(289.0):.2f} {pt(2.5):.2f} {pt(2.5):.2f} rectfill",
        "  /Helvetica findfont 6 scalefont setfont",
        f"  {pt(22.5):.2f} {A4_PT[1] - pt(289.2):.2f} moveto"
        f" (END {JOBID} exp003 modprobe) show }} stopped cleartomark",
    ]


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------

def build_page(pg: ModprobePage) -> dict:
    extra: dict = {}
    # header (7 pt title + 5 pt regen line), clear of the TL/TR corner marks
    pg.label(f"paper-store exp003.0 MODPROBE LAY=1 J={JOBID} R0={HW_DPI}x{HW_DPI}dpi",
             16.0, 9.5, size_pt=7.0)
    pg.label(f"S={SEED.decode()}  regen: gen_modprobe.py (byte-identical, sha256 "
             "gates reuse)  print: raw path only, one sheet  scan: 1200dpi RGB "
             "flat 0deg, enhancements OFF", 16.0, 13.5, size_pt=5.0)

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

    # -- Block K (y 20): constrained fields + incumbents + quiet zone ---------
    pg.label("K 2-D RLL K-fields i2w3/i2w2/i2w4 | K4 encode c2 c3 incumbents",
             14.0, 18.5)
    for name, mins, x in (("K1", (2, 3), 14.0), ("K2", (2, 2), 40.0),
                          ("K3", (2, 4), 66.0)):
        bits, stats = constrained_field(mm(22.0), mins[0], mins[1],
                                        name.lower().encode() + b"/field")
        pg.patch_single(name, bits, x, 20.0, "K", "constrained_field", stats,
                        save_gt=True)
        extra[f"{name}_stats"] = stats
        pg.label(f"{name} i{mins[0]}w{mins[1]}", x, 44.0)
    for cell, x in ((2, 92.0), (3, 110.0)):
        pg.patch_single(f"K4/encode_c{cell}",
                        encoding_patch(cell, mm(14.0), b"k4/encode%d" % cell),
                        x, 20.0, "K", "encoding_patch",
                        {"cell_dots": cell, "pilot_block": 6, "pilot_period": 64},
                        save_gt=True)
        pg.label(f"e{cell}", x, 44.0)
    pg.rect_entry("quiet_zone", 132.0, 20.0, 20.0, 20.0, "quiet_zone",
                  {"purpose": "white ref + noise floor for screening spectra"},
                  clearance_mm=1.5)
    pg.label("quiet zone (blank)", 132.0, 44.0)

    # -- Block D (y 52): dot-disjoint emission probes --------------------------
    pg.label("D dot-disjoint CM c3: D1 mask-pair D2 per-cell D3 cmyk-img "
             "D4 C|M split D5 5st masks D6 5st cmyk", 14.0, 50.5)
    st_cm, planes_cm = state_field(18.0, ("W", "C", "M"), b"d/state_cm")
    GT.mkdir(parents=True, exist_ok=True)
    np.save(GT / "D_cm_states.npy", st_cm)
    d_params = {"cell_dots": CELL_DOTS, "n_states": 3,
                "state_names": ["W", "C", "M"],
                "states_gt": "modprobe_gt/D_cm_states.npy"}
    pair_cm = [(p, planes_cm[p]) for p in ("C", "M")]
    pg.patch_pair("D1", pair_cm, 14.0, 52.0, "state_field",
                  "imagemask_wholefield_pair", d_params)
    pg.label("D1 pair", 14.0, 74.5)
    extra["d2_objects"] = pg.patch_cells("D2", st_cm, ("W", "C", "M"),
                                         36.0, 52.0, "state_field", d_params)
    pg.label("D2 cells", 36.0, 74.5)
    pg.patch_cmyk("D3", {p: planes_cm[p] for p in ("C", "M")}, 58.0, 52.0,
                  "state_field", d_params)
    pg.label("D3 cmyk", 58.0, 74.5)
    # D4: same state field, C-only left half / M-only right half, disjoint rects
    n_cm = st_cm.shape[0]
    half = n_cm // 2                     # 70 cells; center column 70 dropped
    d4_c = cells_to_dots((st_cm[:, :half] == 1).astype(np.uint8), CELL_DOTS)
    d4_m = cells_to_dots((st_cm[:, half + 1:] == 2).astype(np.uint8), CELL_DOTS)
    d4_note = {**d_params,
               "emission": "imagemask_single",
               "split": f"left = C plane of state cols [0,{half}), right = M "
                        f"plane of cols [{half + 1},{n_cm}); center col dropped"}
    pg.patch_single("D4_C", d4_c, 80.0, 52.0, "C", "state_field_half", d4_note,
                    save_gt=True, clearance_mm=0.5)
    x_d4r = 80.0 + (half * CELL_DOTS + 24) * 25.4 / HW_DPI   # 1.0 mm gap
    pg.patch_single("D4_M", d4_m, x_d4r, 52.0, "M", "state_field_half", d4_note,
                    save_gt=True, clearance_mm=0.5)
    pg.label("D4 C|M", 80.0, 74.5)
    st5, planes5 = state_field(20.0, ("W", "C", "M", "Y", "K"), b"d/state5")
    np.save(GT / "D5_states.npy", st5)
    d5_params = {"cell_dots": CELL_DOTS, "n_states": 5,
                 "state_names": ["W", "C", "M", "Y", "K"],
                 "states_gt": "modprobe_gt/D5_states.npy"}
    pg.patch_pair("D5", [(p, planes5[p]) for p in ("C", "M", "Y", "K")],
                  104.0, 52.0, "state_field", "imagemask_wholefield_pair",
                  d5_params)
    pg.label("D5 5st masks", 104.0, 74.5)
    pg.patch_cmyk("D6", planes5, 128.0, 52.0, "state_field", d5_params)
    pg.label("D6 5st cmyk", 128.0, 74.5)

    # -- Block M (y 80 + 95): motif dictionary ---------------------------------
    pg.label("M motif dictionary K: 132 inst/motif, 50% c3 bg, clr 4 dots",
             14.0, 78.5)
    xs = (14.0, 28.5, 43.0, 57.5, 72.0, 86.5)
    for i, name in enumerate(MOTIF_ORDER):
        row, col = divmod(i, len(xs))
        x, y = xs[col], 80.0 + 15.0 * row
        canvas, params = motif_patch(name)
        pg.patch_single(f"M/{name}", canvas, x, y, "K", "motif_patch", params,
                        save_gt=True)
        short = name.replace("ink_", "").replace("white_", "w").replace(
            "domino_", "dom").replace("l_tromino", "L").replace(
            "t_tetromino", "T").replace("slot_", "slot")
        pg.label(short, x, y + 13.8)

    # -- Block S (y 80, right): white-void C subchannel -------------------------
    pg.label("S white-void subchannel: S1 bare i2w3 | S2 +C 2x2 in voids | "
             "S3 c3 50% + C pilots", 110.0, 78.5)
    s_field, s_stats = constrained_field(mm(20.0), 2, 3, b"s1/field")
    pg.patch_single("S1", s_field, 110.0, 80.0, "K", "constrained_field",
                    s_stats, save_gt=True)
    pg.label("S1 bare", 110.0, 102.3)
    extra["S1_stats"] = s_stats
    cmarks, s2_params = c_subchannel_marks(s_field, b"s2/mark-choice")
    pg.patch_pair("S2", [("K", s_field), ("C", cmarks)], 134.0, 80.0,
                  "void_subchannel", "imagemask_wholefield_pair",
                  {**s_stats, **s2_params})
    pg.label("S2 +C voids", 134.0, 102.3)
    extra["s2_marks"] = s2_params["n_marks"]
    k3bits, c3bits, s3_base, s3_params = pilot_void_field(20.0, b"s3/base")
    np.save(GT / "S3_base_cells.npy", s3_base)
    pg.patch_pair("S3", [("K", k3bits), ("C", c3bits)], 158.0, 80.0,
                  "pilot_void_field", "imagemask_wholefield_pair", s3_params)
    pg.label("S3 c3+C pilots", 158.0, 102.3)
    extra["s3_pilots"] = s3_params["n_pilot_sites"]

    # END sentinel reserve (drawn print-time as the very last stream element)
    pg.rect_entry("end_sentinel", 18.0, 286.5, 42.0, 2.8, "end_sentinel",
                  {"text": f"END {JOBID} exp003 modprobe"})

    extra["n_plus_marks"] = pg.place_plus_lattice()
    pg.assert_labels_clear()
    return extra


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GT.mkdir(parents=True, exist_ok=True)
    pg = ModprobePage()
    extra = build_page(pg)
    pg.emit()
    ps = pg.doc.render()
    assert "%%Pages: 1" in ps and ps.count("%%Page:") == 1, "must be ONE page"
    # stream-order self-check: every imagemask precedes any cmyk-image control;
    # the END sentinel is the very last drawing element
    i_cmyk = ps.index("/Decode [0 1 0 1 0 1 0 1]")
    assert ps.rindex("imagemask") < i_cmyk, "masks must stream before cmyk images"
    i_sent = ps.index("% ---- END sentinel")
    assert i_sent > i_cmyk and "imagemask" not in ps[i_sent:] \
        and ">> image" not in ps[i_sent:], "END sentinel must be last"
    d2_bytes = ps.index("% ---- D2 per-cell masks end") - \
        ps.index("% ---- D2 per-cell masks begin")
    assert len(ps) <= D2_PS_BUDGET_BYTES, \
        f"ps {len(ps)/1e6:.1f} MB > 8 MB budget — subsample D2 per task spec"
    (OUT / "modprobe.ps").write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()
    manifest = {
        "experiment": "003-modulation-probes",
        "artifact": "modprobe",
        "run": "003.0",
        "layout_version": LAYOUT_VERSION,
        "seed": SEED.decode(),
        "jobid": JOBID,
        "hw_dpi": HW_DPI,
        "ps_file": "modprobe.ps",
        "ps_sha256": sha,
        "ps_bytes": len(ps),
        "print_command": "../../scripts/print_plane.sh build/modprobe.ps",
        "content_bounds_mm": [X_MIN, Y_MIN, X_MAX, Y_MAX],
        "hypotheses": {
            "H1": "dot-disjoint multi-plane mask content stays on the clean "
                  "path (screening triggers on dot overlap, not region "
                  "overlap): D1/D2/D5 clean vs D3/D6 screened, D4 bar",
            "H2": "a sparse C subchannel in white voids does not perturb K "
                  "development: K BER S2 vs S1; C-mark recovery; S3 pilots",
            "H3": "2-D RLL constrained fields are readable at 2 scan px/dot: "
                  "per-constraint BER/MI on K1/K2/K3 vs K4 c2/c3 incumbents",
            "H4": "motif survival library -> trellis branch metrics (block M)",
        },
        "stream_order": "labels, ALL single-plane imagemask content, "
                        "put_cmyk_bitmap controls (D3, D6), END sentinel last; "
                        "no Separation/DeviceN (002.2 closed that)",
        "d2_object_count": extra["d2_objects"],
        "d2_ps_bytes": d2_bytes,
        "n_plus_marks": extra["n_plus_marks"],
        "patches": pg.patches,
        "infrastructure": pg.infra,
        "labels": pg.labels,
    }
    (OUT / "modprobe_manifest.json").write_text(json.dumps(manifest, indent=1))
    print(f"wrote build/modprobe.ps ({len(ps) / 1e6:.2f} MB, "
          f"{len(pg.patches)} patches, {extra['n_plus_marks']} plus marks, "
          f"D2 {extra['d2_objects']} objects = {d2_bytes / 1e6:.2f} MB)")
    for k in ("K1", "K2", "K3", "S1"):
        s = extra[f"{k}_stats"] if k != "S1" else extra["S1_stats"]
        print(f"{k}: sampler {s['sampler_entropy_bits_per_dot']:.4f} b/dot, "
              f"ctx-model {s['ctx_model_entropy_bits_per_dot']:.4f}, "
              f"ink {s['ink_fraction']:.4f}")
    print(f"S2 marks {extra['s2_marks']}  S3 pilots {extra['s3_pilots']}")
    print(f"sha256 {sha}")


if __name__ == "__main__":
    main()
