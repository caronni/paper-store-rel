#!/usr/bin/env python
"""E004 finalists sheet: the M2 four-cell matrix head-to-head, one A4 page.

Four modulation candidates, 16 tiles each, on an 8x8 balanced checkerboard
(every class exactly TWICE per grid row and TWICE per grid column, then
seeded row/column permutations — kills the page-x/page-y position confound
that a half/half or banded layout would bake into the verdict):

  A3  screened 7-state CMY alphabet {W,C,M,Y,CM,CY,MY}, cell=3
      (002.0c winning alphabet; put_cmyk_bitmap composite = the characterized
      screened channel; 002.2 construction)
  A4  screened 8-state {7+K} alphabet, cell=4 (K as a discrete 8th symbol —
      mixtures stay excluded; 002.2 c4 construction)
  B1  clean-path K solid cells, cell=2, gen_gridtest/003-incumbent
      construction (data + pilot values at pilot sites) — the measured
      leader after 003.0a (ctx 4.59%, recal MI 0.785 b/cell = 109 b/mm2)
  B2  clean-path K 2-D RLL i2w3 free-form field (003.0 construction; row-DP
      sampler reused from gen_modprobe — pure functions, own seed here)

Emission discipline (Layer-0 freeze, 002.0-003.0): B tiles are single-plane
K imagemasks (bit-faithful); A tiles are put_cmyk_bitmap composites (region
overlap => screened contone, ALWAYS — the screen is part of A's channel).
All tile bounding boxes are DISJOINT with >=1.5 mm clearance: 002.2 measured
that region-disjoint clean masks coexist with screened composites on one
page without contamination. Masks stream before any cmyk image; END sentinel
last (002.2/003.0 idiom).

Registration reuses the EXACT chiral corner-mark + plus-mark geometry of
gen_calpage.py (imported, byte-identical) and the gen_composite_probe
ProbePage occupancy/label machinery, so cal_core registers this page by
manifest swap. A reference row (clean K/C/M/Y solids + cmyk-path solids
C,M,Y,CM,CY,MY) anchors density/unmix priors per channel.

Outputs: build/e004.ps, build/e004_manifest.json, build/e004_gt/*.npy.
Byte-identical regeneration from SEED; sha256 gates reuse. Print ONLY via
scripts/print_plane.sh after user confirmation in-session
(.claude/rules/hardware.md). Protocol + pre-registered envelopes:
experiments/004-finalists-checkerboard.md.
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

SEED = b"paper-store/exp004-finalists"
LAYOUT_VERSION = 1
JOBID = hashlib.sha256(SEED + b"/layout1").hexdigest()[:8]
HW_DPI = 600
OUT = _HERE / "build"
GT = OUT / "e004_gt"

X_MIN, X_MAX, Y_MIN, Y_MAX = 6.0, 204.0, 6.0, 291.0

STATES7 = ("W", "C", "M", "Y", "CM", "CY", "MY")   # 002.0c winning alphabet
STATES8K = STATES7 + ("K",)

CLASSES = ("A3", "A4", "B1", "B2")
GRID_N = 8
GRID_X0_MM, GRID_Y0_MM = 12.0, 20.0
PITCH_X_MM, PITCH_Y_MM = 23.5, 32.5
TILE_W_MM, TILE_H_MM = 21.0, 30.0
PS_BUDGET_BYTES = 20_000_000

# per-state count floors (~3 sigma below uniform expectation per tile)
MIN_PER_STATE = {"A3": 5200, "A4": 2500}


def mm(v: float) -> int:
    return round(v / 25.4 * HW_DPI)


def pt(v_mm: float) -> float:
    return v_mm / 25.4 * 72.0


# ---------------------------------------------------------------------------
# content builders (pure; 1 = ink; all randomness via rng(SEED, label))
# ---------------------------------------------------------------------------

def class_map() -> list[list[str]]:
    """8x8 assignment, each class exactly 2x per row and 2x per column:
    cyclic base rows, then seeded row+column permutations (which preserve
    the balance and break the diagonal structure)."""
    base = ["A3", "B1", "A4", "B2"] * 2
    grid = [[base[(j - i) % GRID_N] for j in range(GRID_N)] for i in range(GRID_N)]
    g = rng(SEED, b"layout/classmap")
    rows = g.permutation(GRID_N)
    cols = g.permutation(GRID_N)
    grid = [[grid[r][c] for c in cols] for r in rows]
    for i in range(GRID_N):
        row = grid[i]
        col = [grid[j][i] for j in range(GRID_N)]
        for cls in CLASSES:
            assert row.count(cls) == 2 and col.count(cls) == 2, (i, cls)
    return grid


def uniform_state_field(w_mm: float, h_mm: float, cell_dots: int,
                        states: tuple[str, ...], label: bytes,
                        min_per_state: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Per-cell state i.i.d. uniform over `states` (002.2 construction);
    returns (state array, per-plane dot bitmaps)."""
    nx = mm(w_mm) // cell_dots
    ny = mm(h_mm) // cell_dots
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


def encoding_patch_rect(cell: int, w_dots: int, h_dots: int,
                        label: bytes) -> np.ndarray:
    """gen_gridtest/003-incumbent construction, rectangular: 50% data cells,
    pilot values overwrite at pilot_sites (pilot cells scored as data by the
    incumbent analyzers — keep byte-comparable construction)."""
    ny, nx = h_dots // cell, w_dots // cell
    data = rng(SEED, label + b"/data").integers(0, 2, size=(ny, nx), dtype=np.uint8)
    pv = rng(SEED, label + b"/pilot-values").integers(0, 2, size=(ny, nx),
                                                      dtype=np.uint8)
    m = pilot_sites((ny, nx), SEED)
    data[m] = pv[m]
    return cells_to_dots(data, cell)


def constrained_field_rect(h_dots: int, w_dots: int, min_ink: int,
                           min_white: int, label: bytes) -> tuple[np.ndarray, dict]:
    """Rectangular 2-D RLL field via gen_modprobe's row-DP internals
    (_sample_row / assert_run_lengths are pure — seeded HERE with exp-004's
    SEED). Every maximal run of ink >= min_ink and white >= min_white, both
    axes, border runs included (asserted)."""
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
        "sampler": "gen_modprobe row-DP (rectangular wrapper, exp-004 seed)",
        "sampler_entropy_bits_per_dot": round(log2_total / (h_dots * w_dots), 6),
        "ink_fraction": round(float(a.mean()), 6),
    }
    return a, stats


# ---------------------------------------------------------------------------
# page assembly
# ---------------------------------------------------------------------------

class E004Page(gcp.ProbePage):
    def __init__(self) -> None:
        super().__init__()
        self.doc = PSDoc(hw_dpi=HW_DPI,
                         title=f"paper-store exp004.0 finalists LAY=1 J={JOBID}",
                         guard_setpagedevice=True)
        self._cmyk_emits: list[tuple[str, dict[str, np.ndarray], int, int]] = []

    def _save_gt(self, name: str, bits: np.ndarray) -> str:
        GT.mkdir(parents=True, exist_ok=True)
        rel = f"e004_gt/{name.replace('/', '__')}.npy"
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

    def place_gap_plus_marks(self) -> int:
        """21x21-dot plus marks (gen_calpage builder, byte-identical) at the
        interior tile-grid gap crossings — the 25.4 mm default lattice cannot
        fit between tiles, but the 2.5 mm gap crossings can (mark 0.89 mm,
        occupancy clearance 0.45 mm; physical mark-to-tile distance 0.8 mm)."""
        pm = gen_calpage.plus_mark()
        placed = 0
        for gr in range(1, GRID_N):
            for gc in range(1, GRID_N):
                cx = GRID_X0_MM + gc * PITCH_X_MM - (PITCH_X_MM - TILE_W_MM) / 2
                cy = GRID_Y0_MM + gr * PITCH_Y_MM - (PITCH_Y_MM - TILE_H_MM) / 2
                x, y = mm(cx) - 10, mm(cy) - 10
                if self._conflict(x, y, x + 21, y + 21, mm(0.45)) is not None:
                    continue
                if any(lb["x_dots"] < x + 21 + mm(1.0)
                       and x < lb["x_dots"] + lb["w_dots"] + mm(1.0)
                       and lb["y_dots"] < y + 21 + mm(1.0)
                       and y < lb["y_dots"] + lb["h_dots"] + mm(1.0)
                       for lb in self.labels):
                    continue
                name = f"plusg_{gc}_{gr}"
                self.rects.append((x, y, x + 21, y + 21, mm(0.45), name))
                self._emits.append((name, "mask", (pm, "K"), x, y))
                self.patches.append({"name": name, "kind": "plus_mark",
                                     "planes": ["K"], "x_dots": x, "y_dots": y,
                                     "w_dots": 21, "h_dots": 21,
                                     "params": {"grid_gap_node": [gc, gr],
                                                "arm_dots": 3},
                                     "gt": None})
                placed += 1
        return placed

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
        d.put_raw(sentinel_lines())
        d.end_page()


def sentinel_lines() -> list[str]:
    return [
        "% ---- END sentinel: LAST element in the stream ----",
        "mark { initmatrix 0 0 0 1 setcmykcolor",
        f"  {pt(18.0):.2f} {A4_PT[1] - pt(289.0):.2f} {pt(2.5):.2f} {pt(2.5):.2f} rectfill",
        "  /Helvetica findfont 6 scalefont setfont",
        f"  {pt(22.5):.2f} {A4_PT[1] - pt(289.2):.2f} moveto"
        f" (END {JOBID} exp004 finalists) show }} stopped cleartomark",
    ]


def build_tile(pg: E004Page, cls: str, r: int, c: int) -> dict:
    x_mm = GRID_X0_MM + c * PITCH_X_MM
    y_mm = GRID_Y0_MM + r * PITCH_Y_MM
    name = f"T{r}{c}/{cls}"
    label = f"t{r}{c}/{cls.lower()}".encode()
    w_dots, h_dots = mm(TILE_W_MM), mm(TILE_H_MM)
    info: dict = {"name": name, "class": cls, "row": r, "col": c,
                  "x_mm": x_mm, "y_mm": y_mm}
    if cls == "A3":
        st, planes = uniform_state_field(TILE_W_MM, TILE_H_MM, 3, STATES7,
                                         label, MIN_PER_STATE["A3"])
        rel = pg._save_gt(f"{name}_states", st)
        pg.patch_cmyk(name, planes, x_mm, y_mm, "state_field",
                      {"cell_dots": 3, "n_states": 7,
                       "state_names": list(STATES7), "states_gt": rel,
                       "class": cls}, clearance_mm=0.6)
        info["cells"] = int(st.size)
    elif cls == "A4":
        st, planes = uniform_state_field(TILE_W_MM, TILE_H_MM, 4, STATES8K,
                                         label, MIN_PER_STATE["A4"])
        rel = pg._save_gt(f"{name}_states", st)
        pg.patch_cmyk(name, planes, x_mm, y_mm, "state_field",
                      {"cell_dots": 4, "n_states": 8,
                       "state_names": list(STATES8K), "states_gt": rel,
                       "class": cls}, clearance_mm=0.6)
        info["cells"] = int(st.size)
    elif cls == "B1":
        bits = encoding_patch_rect(2, w_dots, h_dots, label)
        pg.patch_single(name, bits, x_mm, y_mm, "K", "encoding_patch",
                        {"cell_dots": 2, "pilot_block": 6, "pilot_period": 64,
                         "class": cls}, save_gt=True, clearance_mm=0.6)
        info["cells"] = (w_dots // 2) * (h_dots // 2)
    else:  # B2
        bits, stats = constrained_field_rect(h_dots, w_dots, 2, 3, label)
        pg.patch_single(name, bits, x_mm, y_mm, "K", "constrained_field",
                        {**stats, "class": cls}, save_gt=True,
                        clearance_mm=0.6)
        info["cells"] = int(w_dots * h_dots)   # dots are the channel uses
        info["stats"] = stats
    # label sits 3 mm right of the tile edge so the gap-crossing plus mark
    # to the tile's lower-left keeps its 1 mm label margin
    pg.label(cls, x_mm + 3.0, y_mm + TILE_H_MM + 1.9)
    return info


def build_page(pg: E004Page) -> dict:
    extra: dict = {}
    pg.label(f"paper-store exp004.0 FINALISTS LAY=1 J={JOBID} "
             f"R0={HW_DPI}x{HW_DPI}dpi 8x8 balanced", 16.0, 9.5, size_pt=7.0)
    pg.label(f"S={SEED.decode()}  regen: gen_e004.py (byte-identical) | "
             "A3=7st-c3 A4={7+K}-c4 B1=c2-K B2=RLL-i2w3", 16.0, 13.5,
             size_pt=5.0)
    pg.label("print: raw path only, ONE sheet | scan: 1200dpi grey (B) + "
             "1200dpi color (A), enhancements OFF", 16.0, 17.0, size_pt=5.0)

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

    grid = class_map()
    tiles = [build_tile(pg, grid[r][c], r, c)
             for r in range(GRID_N) for c in range(GRID_N)]
    extra["class_map"] = grid
    extra["tiles"] = tiles

    # reference row: clean-path solids (B anchors) + cmyk-path solids
    # (A-channel density/unmix anchors), y 280.0-284.8
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

    pg.rect_entry("end_sentinel", 18.0, 286.5, 42.0, 2.8, "end_sentinel",
                  {"text": f"END {JOBID} exp004 finalists"})
    extra["n_plus_marks"] = pg.place_gap_plus_marks() + pg.place_plus_lattice()
    assert extra["n_plus_marks"] >= 24, \
        f"only {extra['n_plus_marks']} plus marks placed — registration thin"
    pg.assert_labels_clear()
    return extra


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GT.mkdir(parents=True, exist_ok=True)
    pg = E004Page()
    extra = build_page(pg)
    pg.emit()
    ps = pg.doc.render()
    assert "%%Pages: 1" in ps and ps.count("%%Page:") == 1, "must be ONE page"
    i_cmyk = ps.index("% ==== BLOCK 2")
    assert ps.rindex("imagemask") < i_cmyk, "masks must stream before cmyk"
    i_sent = ps.index("% ---- END sentinel")
    assert i_sent > i_cmyk and "imagemask" not in ps[i_sent:] \
        and ">> image" not in ps[i_sent:], "END sentinel must be last"
    assert len(ps) <= PS_BUDGET_BYTES, f"ps {len(ps)/1e6:.1f} MB > budget"
    (OUT / "e004.ps").write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()
    per_class = {cls: sum(1 for t in extra["tiles"] if t["class"] == cls)
                 for cls in CLASSES}
    assert all(v == 16 for v in per_class.values()), per_class
    manifest = {
        "experiment": "004-finalists-checkerboard",
        "artifact": "e004",
        "run": "004.0",
        "layout_version": LAYOUT_VERSION,
        "seed": SEED.decode(),
        "jobid": JOBID,
        "hw_dpi": HW_DPI,
        "ps_file": "e004.ps",
        "ps_sha256": sha,
        "ps_bytes": len(ps),
        "print_command": "../../scripts/print_plane.sh build/e004.ps",
        "content_bounds_mm": [X_MIN, Y_MIN, X_MAX, Y_MAX],
        "grid": {"n": GRID_N, "x0_mm": GRID_X0_MM, "y0_mm": GRID_Y0_MM,
                 "pitch_x_mm": PITCH_X_MM, "pitch_y_mm": PITCH_Y_MM,
                 "tile_w_mm": TILE_W_MM, "tile_h_mm": TILE_H_MM,
                 "classes": list(CLASSES), "per_class_tiles": per_class,
                 "class_map": extra["class_map"],
                 "balance": "each class exactly 2x per row and 2x per column"},
        "four_cell_matrix": {
            "A3": "screened 7-state CMY alphabet cell=3 (002.2 construction)",
            "A4": "screened {7+K} 8-state alphabet cell=4",
            "B1": "clean K solid cells cell=2, incumbent construction "
                  "(003.0a: ctx 4.59%, recal MI 0.785 b/cell)",
            "B2": "clean K 2-D RLL i2w3 free-form (003.0 construction)",
        },
        "stream_order": "labels, ALL single-plane imagemask content, "
                        "put_cmyk_bitmap composites, END sentinel last",
        "tiles": extra["tiles"],
        "n_plus_marks": extra["n_plus_marks"],
        "patches": pg.patches,
        "infrastructure": pg.infra,
        "labels": pg.labels,
    }
    (OUT / "e004_manifest.json").write_text(json.dumps(manifest, indent=1))
    b2_ent = [t["stats"]["sampler_entropy_bits_per_dot"]
              for t in extra["tiles"] if t["class"] == "B2"]
    print(f"wrote build/e004.ps ({len(ps)/1e6:.2f} MB, {len(pg.patches)} "
          f"patches, {extra['n_plus_marks']} plus marks)")
    print(f"tiles/class: {per_class};  B2 sampler entropy "
          f"{min(b2_ent):.4f}-{max(b2_ent):.4f} b/dot")
    print(f"sha256 {sha}")


if __name__ == "__main__":
    main()
