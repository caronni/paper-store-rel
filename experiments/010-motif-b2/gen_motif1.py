#!/usr/bin/env python
"""E010 MOTIF-1: the Q2 go/no-go stimulus for a motif-based B2 (i2w3) mode.

One A4 page, single-plane K imagemask (raw clean path — the bit-faithful
emission of Layer-0's channel freeze). Tiles the page with B x B (B=7) motif
blocks from motif_codec's D=1170 border-legal dictionary (10 bits/motif,
0.204 b/dot ceiling = ~114 b/mm2 at perfect detection, ABOVE the 82-86 anchor).

THE DECISIVE QUESTION (Q2) this page is built to answer: 004.0a showed the
B2/RLL trellis gains ~zero because the dominant channel error is a
constraint-CONSISTENT whole-feature dropout (a 2-dot ink run fades to legal
white, and the trellis cannot even flag it). The motif frame trades a little
rate for LOCALITY and matched-filter detection over the WHOLE block: do the
other ~47 dots pin the symbol so a dropped 2-dot run is recovered, or does the
drop flip motif i to its legal dropout-twin j (the 788 confusion pairs)?

Three regions make that measurable:
  main     random motifs over the FULL 1170 dictionary — page-scale symbol
           error + MI, the headline capacity number under real detection.
  dropout  ONLY the 622 dropout-SOURCE motifs {i} (each has an isolated 2-dot
           ink run whose loss lands on a legal twin j). The load-bearing Q2
           field: how often does a sent i get DETECTED as its twin j?
  control  ONLY the 548 dropout-IMMUNE motifs (never a source i) — baseline
           symbol error with no dropout vulnerability, the discriminating
           control for the dropout number.

Registration reuses the EXACT chiral corner-mark geometry of gen_calpage.py
(imported, byte-identical); 4 corners with satellite counts TL=1 TR=2 BR=3
BL=4 so cal_core.register orients the page by manifest swap.

Outputs: build/motif1.ps, build/motif1_manifest.json, build/motif1_gt/*.npy.
Byte-identical regeneration from SEED; sha256 gates reuse. Simulation only —
NO printing/scanning here. Print (later, on user go) ONLY via
scripts/print_plane.sh after in-session confirmation (.claude/rules/hardware.md).
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

from paperholo.modulation import rng
from paperholo.psgen import A4_PT, CMYK, PSDoc

_HERE = Path(__file__).resolve().parent
_EXP002 = _HERE.parent / "002-calibration-page"
for _p in (str(_HERE), str(_EXP002)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gen_calpage  # noqa: E402  (byte-identical corner_mark builder)
import motif_codec as mc  # noqa: E402  (the shared, validated core)

SEED = b"paper-store/exp010-motif1"
LAYOUT_VERSION = 1
JOBID = hashlib.sha256(SEED + b"/layout1").hexdigest()[:8]
HW_DPI = 600
B = 7                       # motif side (motif_codec dictionary is B=7)
OUT = _HERE / "build"
GT = OUT / "motif1_gt"

# 8 mm margins on A4 (210 x 297 mm) — satellites/edges of every mark stay
# >= 8 mm from the paper edge.
X_MIN, X_MAX, Y_MIN, Y_MAX = 8.0, 202.0, 8.0, 289.0

# region nominal sizes (mm) — main leaves room for the two 40 mm blocks +
# gaps + header inside the 8 mm margins.
MAIN_W_MM, MAIN_H_MM = 110.0, 150.0
BLOCK_MM = 40.0
PS_BUDGET_BYTES = 40_000_000


def mm(v: float) -> int:
    return round(v / 25.4 * HW_DPI)


def pt(v_mm: float) -> float:
    return v_mm / 25.4 * 72.0


# ---------------------------------------------------------------------------
# region field builders (pure; 1 = ink; randomness via paperholo rng only)
# ---------------------------------------------------------------------------

def region_rows_cols(w_mm: float, h_mm: float) -> tuple[int, int]:
    """(rows, cols) of whole B x B motifs that fit in a w_mm x h_mm rect."""
    return mm(h_mm) // B, mm(w_mm) // B


def random_symbols(rows: int, cols: int, choices: np.ndarray,
                   label: bytes) -> np.ndarray:
    """(rows, cols) motif-index array, i.i.d. uniform over `choices` (a 1-D
    array of dictionary indices). Seeded from SEED via paperholo rng."""
    g = rng(SEED, label)
    pick = g.integers(0, len(choices), size=(rows, cols), dtype=np.int64)
    return choices[pick].astype(np.int64)


# ---------------------------------------------------------------------------
# page assembly
# ---------------------------------------------------------------------------

class Motif1Page:
    """Occupancy-checked single-plane-K page (mirrors CalPage discipline)."""

    def __init__(self) -> None:
        self.doc = PSDoc(
            hw_dpi=HW_DPI,
            title=f"paper-store exp010 motif1 LAY=1 J={JOBID}",
            guard_setpagedevice=True)
        self.rects: list[tuple[int, int, int, int, int, str]] = []
        self.patches: list[dict] = []
        self.labels: list[dict] = []
        self._emits: list[tuple[str, np.ndarray, int, int]] = []
        self._label_args: list[tuple[str, int, int, float]] = []
        self._gt_files: set[str] = set()

    # -- occupancy ---------------------------------------------------------
    def _conflict(self, x0: int, y0: int, x1: int, y1: int, clr: int) -> str | None:
        for a0, b0, a1, b1, c2, nm in self.rects:
            g = max(clr, c2)
            if x0 < a1 + g and a0 < x1 + g and y0 < b1 + g and b0 < y1 + g:
                return nm
        return None

    def _occupy(self, name: str, x: int, y: int, w: int, h: int,
                clr_mm: float) -> None:
        clr = mm(clr_mm)
        if not (mm(X_MIN) <= x and x + w <= mm(X_MAX)
                and mm(Y_MIN) <= y and y + h <= mm(Y_MAX)):
            raise AssertionError(
                f"{name}: rect ({x},{y},{w},{h}) outside content bounds")
        hit = self._conflict(x, y, x + w, y + h, clr)
        if hit is not None:
            raise AssertionError(
                f"{name} overlaps {hit} (clearance {clr_mm} mm)")
        self.rects.append((x, y, x + w, y + h, clr, name))

    def _save_gt(self, name: str, arr: np.ndarray) -> str:
        GT.mkdir(parents=True, exist_ok=True)
        rel = f"motif1_gt/{name.replace('/', '__')}.npy"
        if rel in self._gt_files:
            raise AssertionError(f"ground-truth filename collision: {rel}")
        self._gt_files.add(rel)
        np.save(OUT / rel, arr)
        return rel

    # -- content -----------------------------------------------------------
    def mask(self, name: str, bits: np.ndarray, x_mm: float, y_mm: float,
             kind: str, params: dict, gt_arr: np.ndarray | None,
             clearance_mm: float = 1.5) -> dict:
        x, y = mm(x_mm), mm(y_mm)
        h, w = bits.shape
        self._occupy(name, x, y, w, h, clearance_mm)
        self._emits.append((name, bits, x, y))
        gt = self._save_gt(name, gt_arr) if gt_arr is not None else None
        e = {"name": name, "kind": kind, "planes": ["K"],
             "x_dots": x, "y_dots": y, "w_dots": int(w), "h_dots": int(h),
             "params": params, "gt": gt}
        self.patches.append(e)
        return e

    def label(self, text: str, x_mm: float, y_baseline_mm: float,
              size_pt: float = 6.0) -> None:
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

    # -- emission: labels, then all K imagemask content, then sentinel -----
    def emit(self) -> None:
        d = self.doc
        d.begin_page()
        for text, x, yb, size in self._label_args:
            d.put_label(text, x, yb, CMYK["K"], size_pt=size)
        d.put_raw(["% ==== single-plane K imagemask content"
                   " (bit-faithful clean path) ===="])
        # deterministic emission order (name-sorted) for byte-identical output
        for name, bits, x, y in sorted(self._emits, key=lambda t: t[0]):
            d.put_raw([f"% ---- {name} ----"])
            d.put_bitmap(bits, x, y, CMYK["K"])
        d.put_raw(sentinel_lines())
        d.end_page()


def sentinel_lines() -> list[str]:
    return [
        "% ---- END sentinel: LAST element in the stream ----",
        "mark { initmatrix 0 0 0 1 setcmykcolor",
        f"  {pt(18.0):.2f} {A4_PT[1] - pt(287.0):.2f} {pt(2.5):.2f}"
        f" {pt(2.5):.2f} rectfill",
        "  /Helvetica findfont 6 scalefont setfont",
        f"  {pt(22.5):.2f} {A4_PT[1] - pt(287.2):.2f} moveto"
        f" (END {JOBID} exp010 motif1) show }} stopped cleartomark",
    ]


# ---------------------------------------------------------------------------
# layout
# ---------------------------------------------------------------------------

def build_page(pg: Motif1Page, dictionary: np.ndarray,
               pairs: list[tuple[int, int]]) -> dict:
    # dropout-source / dropout-immune index sets (Q2 subset definitions)
    src_idx = np.array(sorted({i for i, _ in pairs}), dtype=np.int64)
    immune_idx = np.array(
        sorted(set(range(len(dictionary))) - set(int(i) for i in src_idx)),
        dtype=np.int64)
    all_idx = np.arange(len(dictionary), dtype=np.int64)

    # header (two label lines)
    pg.label(f"paper-store exp010 MOTIF-1 LAY=1 J={JOBID} "
             f"R0={HW_DPI}x{HW_DPI}dpi  B={B} D={len(dictionary)} "
             f"({mc.bits_per_motif(dictionary)} bits/motif)", 16.0, 12.0,
             size_pt=7.0)
    pg.label(f"S={SEED.decode()}  regen: gen_motif1.py (byte-identical) | "
             "K imagemask raw path | Q2: matched-filter dropout recovery | "
             "scan 1200dpi grey, enhancements OFF", 16.0, 15.5, size_pt=5.0)

    # 4 chiral corner marks (satellites 1/2/3/4 = TL/TR/BR/BL; center at 61,61
    # of the 123-dot block, so an 8 mm center inset keeps the whole mark and
    # its inward satellites >= 8 mm from the paper edge).
    corner_marks: list[dict] = []
    for tag, n_sat, inward, cx, cy in (("tl", 1, (1, 1), 13.0, 13.0),
                                       ("tr", 2, (1, -1), 197.0, 13.0),
                                       ("br", 3, (-1, -1), 197.0, 284.0),
                                       ("bl", 4, (-1, 1), 13.0, 284.0)):
        bits = gen_calpage.corner_mark(n_sat, inward)
        h, w = bits.shape
        x0_mm = cx - 61 * 25.4 / HW_DPI
        y0_mm = cy - 61 * 25.4 / HW_DPI
        e = pg.mask(f"corner_{tag}", bits, x0_mm, y0_mm, "corner_mark",
                    {"satellites": n_sat, "inward": list(inward),
                     "arm_dots": 60, "width_dots": 3,
                     "cx_dots": mm(cx), "cy_dots": mm(cy)},
                    gt_arr=None, clearance_mm=0.5)
        corner_marks.append(
            {"satellites": n_sat, "cx_dots": mm(cx), "cy_dots": mm(cy),
             "x_dots": e["x_dots"], "y_dots": e["y_dots"],
             "h_dots": int(h), "w_dots": int(w)})

    regions: list[dict] = []

    def add_region(name: str, kind: str, x_mm: float, y_mm: float,
                   w_mm: float, h_mm: float, choices: np.ndarray,
                   extra: dict) -> None:
        rows, cols = region_rows_cols(w_mm, h_mm)
        syms = random_symbols(rows, cols, choices, f"region/{name}".encode())
        field = mc.symbols_to_field(syms, dictionary, B)
        assert mc.block_legal(field), f"{name}: assembled field not i2w3-legal"
        params = {"cell_dots": B, "kind": kind, "rows": rows, "cols": cols,
                  "n_choices": int(len(choices)), **extra}
        e = pg.mask(name, field, x_mm, y_mm, kind, params, gt_arr=syms,
                    clearance_mm=1.5)
        regions.append({
            "name": name, "kind": kind,
            "x_mm": round(e["x_dots"] * 25.4 / HW_DPI, 4),
            "y_mm": round(e["y_dots"] * 25.4 / HW_DPI, 4),
            "x_dots": e["x_dots"], "y_dots": e["y_dots"],
            "w_dots": e["w_dots"], "h_dots": e["h_dots"],
            "rows": rows, "cols": cols, "cell_dots": B,
            "gt_file": e["gt"], "n_choices": int(len(choices)), **extra})

    # main region: top-left, full 1170 dictionary
    add_region("main", "random", 16.0, 20.0, MAIN_W_MM, MAIN_H_MM,
               all_idx, {"choice_set": "full_dictionary"})

    # dropout region: 40 mm block, ONLY the dropout-source motifs {i}.
    # record the [i, j] pairs (the Q2 confusion set) as a kind-specific key.
    add_region("dropout", "dropout", 16.0, 176.0, BLOCK_MM, BLOCK_MM,
               src_idx,
               {"choice_set": "dropout_source_motifs",
                "dropout_pair_indices": [[int(i), int(j)] for i, j in pairs],
                "n_dropout_pairs": len(pairs),
                "n_dropout_source_motifs": int(len(src_idx)),
                "note": "each motif has an isolated 2-dot ink run whose loss "
                        "lands on the legal twin j"})

    # control region: 40 mm block, ONLY dropout-immune motifs (never a source)
    add_region("control", "control", 62.0, 176.0, BLOCK_MM, BLOCK_MM,
               immune_idx,
               {"choice_set": "dropout_immune_motifs",
                "n_immune_motifs": int(len(immune_idx)),
                "note": "no isolated 2-dot ink run -> no dropout twin"})

    # region labels (clear of the fields)
    pg.label("main: random over full D=1170", 16.0, 173.0, size_pt=5.0)
    pg.label("dropout: sources {i}", 16.0, 220.0, size_pt=5.0)
    pg.label("control: immune", 62.0, 220.0, size_pt=5.0)

    pg.assert_labels_clear()
    return {"regions": regions, "corner_marks": corner_marks,
            "n_dropout_pairs": len(pairs),
            "n_dropout_source_motifs": int(len(src_idx)),
            "n_immune_motifs": int(len(immune_idx))}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    GT.mkdir(parents=True, exist_ok=True)

    dictionary = mc.build_dictionary(B)
    dict_sha = hashlib.sha256(dictionary.tobytes()).hexdigest()
    pairs = mc.dropout_pairs(dictionary, B)

    pg = Motif1Page()
    extra = build_page(pg, dictionary, pairs)
    pg.emit()
    ps = pg.doc.render()

    assert "%%Pages: 1" in ps and ps.count("%%Page:") == 1, "must be ONE page"
    i_sent = ps.index("% ---- END sentinel")
    assert "imagemask" not in ps[i_sent:] and ">> image" not in ps[i_sent:], \
        "END sentinel must be last drawing op"
    assert ">> image" not in ps, "single-plane K path only (no cmyk image)"
    assert len(ps) <= PS_BUDGET_BYTES, f"ps {len(ps) / 1e6:.1f} MB > budget"

    (OUT / "motif1.ps").write_text(ps)
    sha = hashlib.sha256(ps.encode()).hexdigest()

    manifest = {
        "experiment": "010-motif-b2",
        "artifact": "motif1",
        "run": "010.0",
        "b": B,
        "seed": SEED.decode(),
        "jobid": JOBID,
        "layout_version": LAYOUT_VERSION,
        "ps_sha256": sha,
        "ps_bytes": len(ps),
        "dictionary_sha256": dict_sha,
        "dictionary_size": int(len(dictionary)),
        "bits_per_motif": int(mc.bits_per_motif(dictionary)),
        "hw_dpi": HW_DPI,
        "page_size_pt": list(A4_PT),
        "content_bounds_mm": [X_MIN, Y_MIN, X_MAX, Y_MAX],
        "ps_file": "motif1.ps",
        "print_command": "../../scripts/print_plane.sh build/motif1.ps",
        "n_dropout_pairs": extra["n_dropout_pairs"],
        "n_dropout_source_motifs": extra["n_dropout_source_motifs"],
        "n_immune_motifs": extra["n_immune_motifs"],
        "stream_order": "labels, ALL single-plane K imagemask content "
                        "(name-sorted), END sentinel last",
        "regions": extra["regions"],
        "corner_marks": extra["corner_marks"],
        "patches": pg.patches,
        "labels": pg.labels,
    }
    (OUT / "motif1_manifest.json").write_text(json.dumps(manifest, indent=1))

    rc = {r["name"]: (r["rows"], r["cols"], r["rows"] * r["cols"])
          for r in extra["regions"]}
    print(f"wrote build/motif1.ps ({len(ps) / 1e6:.2f} MB, "
          f"{len(pg.patches)} patches)")
    print(f"regions (rows x cols = motifs): "
          f"main {rc['main'][0]}x{rc['main'][1]}={rc['main'][2]}, "
          f"dropout {rc['dropout'][0]}x{rc['dropout'][1]}={rc['dropout'][2]}, "
          f"control {rc['control'][0]}x{rc['control'][1]}={rc['control'][2]}")
    print(f"dropout pairs={extra['n_dropout_pairs']}, "
          f"source motifs={extra['n_dropout_source_motifs']}, "
          f"immune motifs={extra['n_immune_motifs']}")
    print(f"dictionary_sha256 {dict_sha}")
    print(f"ps_sha256 {sha}")


if __name__ == "__main__":
    main()
