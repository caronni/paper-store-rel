"""e043b — the M281 cmy probe sheet 2 (docs/CMY-PROBE-M281.md §9): values at two-level steps in both constructs,
pairwise cell checkerboards, bands at the registry values, a dot-level set.

ONE plain PostScript job through holo.gen.ps.PSDoc, A4 at 600 dpi, e041's section geometry, sheet 1's conventions
(probe_sheet.py, imported): no PJL, no prologue, HP calls only in the I-ref band and bars, ASCIIHex/ASCII85 only.
Every value from the registry (holo.devices.registry PRINTERS["hp-m281"].rgb_solid; W = unpainted paper); --lookup
legacy-e043b restores the values the printed sheet 2 carried (C at G 184), so its job regenerates byte-identically.
Top to bottom, drawn in this order:

  fiducials      sheet 1's five K imagemasks (ASCIIHex)
  bands          B1-B6 at x 283, y 283 + k * 456, 432 x 4392 dots: the sheet-1 c2 field (default_rng(43), 216 x
                 2196 cells) as mask-a85 / I-2 / I-8 / I-ref, then a c3 field (default_rng(45), 144 x 1464 cells of
                 3 dots, uniform over {0, 1, 2, 4}) as mask-a85 / I-2; the I-ref band == e041's image block, asserted
  checkerboards  W/C W/M W/Y C/M C/Y M/Y, row 1 at c2 and row 2 at c3, 480 x 240 dots at a 732-dot pitch; cell
                 (i, j) is the pair's first colour when i + j is even; one ASCII85 mask per toner of the pair
  bars           192 x 48 dots, 20 per row at 221 x 72 from 24 dots below the checkerboards, value -> slot by
                 default_rng(46).permutation: cyan (0, G, 255) G 176..190 step 2, magenta (R, 0, B) R 236..242 x
                 B 188..198 step 2 (axis "grid"), yellow (255, 255, B) B 0/8/16/24, each as mask-a85 (put_bitmap) and
                 I-2 (lookup [W, value], every index 1); the registry C M Y as I-8 and I-ref (sheet 1's W C M Y
                 lookup); 4 white, 2 scrambled (C, M: 50 % dots at 1 dot per cell, drawn from the c2 cell generator
                 after the field, ASCII85 masks), 1 screened (8-bit Indexed [W, (128, 232, 255)])
  dots           per toner C M Y five 96 x 96-dot masks (single dots and 2 x 2 blocks on an 8-dot grid, 1-on/1-off
                 vertical and horizontal lines, 2-on/2-off vertical lines), one row of fifteen at a 288-dot pitch

Outputs (--out DIR, default build/e043b): E043b-m281-cmy-probe2.ps, .manifest.json, -gt.npz (states_c2, states_c3,
the scrambled bars, every dot patch under its id; fixed zip timestamps). --check as sheet 1: gs ppmraw -r600 with
the default ICC and -dUseFastColor, (R, G, B) < 128 -> (C, M, Y) against the plan per band, bar, checkerboard and
dot patch, nothing but white outside the painted rectangles, a strict nullpage run.

    PYTHONPATH=src:. env/bin/python experiments/043-m281-cmy-probe/probe_sheet2.py \\
        --out build/e043b --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_sheet as s1  # noqa: E402
from probe_sheet import RGB, Indexed, Mask, Paint  # noqa: E402

from holo.core.channel import states_to_planes  # noqa: E402
from holo.gen.ps import A4_DOTS_XY, PSDoc  # noqa: E402

TAG = "E043b-m281-cmy-probe2"
TITLE = "e043b M281 cmy probe 2"
SEED_C2, SEED_C3, SEED_LAYOUT = 43, 45, 46
SEED_STRING = f"{TAG} cells_c2={SEED_C2} cells_c3={SEED_C3} layout={SEED_LAYOUT}"
PAGE_DOTS_XY = s1.PAGE_DOTS_XY
X0, SECTION_W = s1.BAND_X_DOTS, s1.BAND_W_DOTS
FIRST_Y, GAP, LAST_END = s1.FIRST_Y_DOTS, s1.GAP_DOTS, s1.LAST_END_DOTS
BAND_H = 432
C3_ROWS, C3_COLS = 144, 1464
BANDS = (("mask-a85", 2), ("I-2", 2), ("I-8", 2), ("I-ref", 2), ("mask-a85", 3), ("I-2", 3))
STATE_OF = {"W": 0, "C": 1, "M": 2, "Y": 4}
PAIRS = ("WC", "WM", "WY", "CM", "CY", "MY")
CHECK_W, CHECK_H, CHECK_PITCH = 480, 240, 732
BAR_W, BAR_H, BARS_PER_ROW, BAR_PITCH_X, BAR_PITCH_Y = s1.BAR_W_DOTS, s1.BAR_H_DOTS, 20, 221, 72
SWEEP_CONSTRUCTS = ("mask-a85", "I-2")
REGISTRY_CONSTRUCTS = ("I-8", "I-ref")
N_WHITE = 4
SCREENED_TINT = s1.SCREENED_TINT
DOT_W = 96
DOT_PITCH = 288
DOT_PATTERNS = ("single8", "block2-8", "vlines1", "hlines1", "vlines2")


# ------------------------------------------------------------------------------------------------ plan

def sweep_values() -> list[tuple[str, str, RGB]]:
    """(toner, axis, rgb) for every swept value: cyan's G, magenta's R x B grid, yellow's B."""
    out = [("C", "G", (0, g, 255)) for g in range(176, 191, 2)]
    out += [("M", "grid", (r, 0, b)) for r in (236, 238, 240, 242) for b in range(188, 199, 2)]
    out += [("Y", "B", (255, 255, b)) for b in (0, 8, 16, 24)]
    return out


def sweep_id(toner: str, rgb: RGB, construct: str) -> str:
    r, g, b = rgb
    v = {"C": f"G{g:03d}", "M": f"R{r:03d}B{b:03d}", "Y": f"B{b:03d}"}[toner]
    return f"{toner}-{v}-{construct}"


def bar_specs(rng_cells: np.random.Generator, lookup: dict[str, RGB]) -> list[dict]:
    """Every bar in canonical order (sweeps x constructs, registry x constructs, controls), slots unassigned."""
    specs = [{"id": sweep_id(t, rgb, c), "kind": "sweep", "toner": t, "axis": axis, "rgb": rgb, "construct": c}
             for t, axis, rgb in sweep_values() for c in SWEEP_CONSTRUCTS]
    specs += [{"id": f"reg-{t}-{c}", "kind": "registry", "toner": t, "axis": None, "rgb": lookup[t],
               "construct": c} for t in "CMY" for c in REGISTRY_CONSTRUCTS]
    specs += [{"id": f"white-{k + 1}", "kind": "white", "toner": None, "axis": None, "rgb": None,
               "construct": "none"} for k in range(N_WHITE)]
    for t in "CM":
        bits = (rng_cells.random((BAR_H, BAR_W)) < 0.5).astype(np.uint8)
        specs.append({"id": f"scrambled-{t}", "kind": "scrambled", "toner": t, "axis": None, "rgb": lookup[t],
                      "construct": "mask-a85", "gt_key": f"bar_scrambled-{t}", "_bits": bits})
    specs.append({"id": "screened-C50", "kind": "screened", "toner": "C", "axis": None, "rgb": SCREENED_TINT,
                  "construct": "I-8"})
    return specs


def bar_paints(spec: dict, lookup: dict[str, RGB]) -> list[Paint]:
    x, y, kind, construct = spec["x_dots"], spec["y_dots"], spec["kind"], spec["construct"]
    ones = np.ones((BAR_H, BAR_W), np.uint8)
    if kind == "white":
        return []
    if kind == "scrambled":
        return [Mask(spec["_bits"], x, y, spec["rgb"], "ASCII85")]
    if kind == "screened":
        return [Indexed(ones, (lookup["W"], SCREENED_TINT), x, y, 8, ())]
    if construct == "mask-a85":
        return [Mask(ones, x, y, spec["rgb"], "ASCII85")]
    if construct == "I-2":
        return [Indexed(ones, (lookup["W"], spec["rgb"]), x, y, 2, ())]
    fill = np.full((BAR_H, BAR_W), "WCMY".index(spec["toner"]), np.uint8)
    return [s1.construct_paint(construct, fill, spec["rgb"], x, y, lookup)]


def place_bars(specs: list[dict], rng_layout: np.random.Generator, y0: int) -> list[dict]:
    """Bar i takes slot perm[i]; returned in slot (= draw) order with x/y/w/h dots."""
    perm = rng_layout.permutation(len(specs))
    for spec, slot in zip(specs, perm):
        row, col = divmod(int(slot), BARS_PER_ROW)
        spec |= {"x_dots": X0 + col * BAR_PITCH_X, "y_dots": y0 + row * BAR_PITCH_Y, "w_dots": BAR_W,
                 "h_dots": BAR_H, "_slot": int(slot)}
    return sorted(specs, key=lambda s: s["_slot"])


def c3_field(rng: np.random.Generator) -> np.ndarray:
    return s1.PRESENCE_IDS[rng.choice(4, size=(C3_ROWS, C3_COLS))]


def band_paints(arm: str, states: np.ndarray, cell_dots: int, x: int, y: int,
                lookup: dict[str, RGB]) -> list[Paint]:
    """One band: three ASCII85 toner masks (mask-a85) or one W C M Y Indexed image (I-*)."""
    if arm == "mask-a85":
        planes = states_to_planes(states)
        return [Mask(s1.expand(planes[..., p], cell_dots), x, y, lookup[t], "ASCII85") for p, t in enumerate("CMY")]
    idx = s1.expand(s1.state_indices(states), cell_dots)
    bpc = 2 if arm == "I-2" else 8
    return [Indexed(idx, s1.wcmy(lookup), x, y, bpc, s1.IREF_PRELUDE if arm == "I-ref" else ())]


def checker_states(pair: str, rows: int, cols: int) -> np.ndarray:
    """Presence ids of a pair checkerboard: cell (i, j) = pair[0] when i + j is even, else pair[1]."""
    even = (np.add.outer(np.arange(rows), np.arange(cols)) % 2) == 0
    return np.where(even, STATE_OF[pair[0]], STATE_OF[pair[1]]).astype(np.uint8)


def checker_paints(pair: str, cell_dots: int, x: int, y: int, lookup: dict[str, RGB]) -> list[Paint]:
    planes = states_to_planes(checker_states(pair, CHECK_H // cell_dots, CHECK_W // cell_dots))
    return [Mask(s1.expand(planes[..., p], cell_dots), x, y, lookup[t], "ASCII85")
            for p, t in enumerate("CMY") if t in pair]


def dot_pattern(pattern: str) -> np.ndarray:
    yy, xx = np.mgrid[0:DOT_W, 0:DOT_W]
    bits = {"single8": (yy % 8 == 4) & (xx % 8 == 4),
            "block2-8": (yy % 8 // 2 == 2) & (xx % 8 // 2 == 2),
            "vlines1": xx % 2 == 0,
            "hlines1": yy % 2 == 0,
            "vlines2": xx % 4 < 2}[pattern]
    return bits.astype(np.uint8)


@dataclass(frozen=True)
class Plan:
    lookup: dict[str, RGB]
    states: dict[str, np.ndarray]  # gt_key -> cell field
    fiducials: list[dict]
    bands: list[dict]
    checkerboards: list[dict]
    bars: list[dict]
    dots: list[dict]
    paints: list[Paint]  # draw order


def plan(lookup: dict[str, RGB]) -> Plan:
    rng_c2 = np.random.default_rng(SEED_C2)
    states = {"states_c2": s1.cell_field(rng_c2), "states_c3": c3_field(np.random.default_rng(SEED_C3))}
    fids = s1.fiducial_records()
    paints: list[Paint] = [Mask(np.ones((f["h_dots"], f["w_dots"]), np.uint8), f["x_dots"], f["y_dots"], None,
                                "ASCIIHex") for f in fids]
    bands = []
    for k, (arm, cd) in enumerate(BANDS):
        key = f"states_c{cd}"
        rows, cols = states[key].shape
        b = {"name": f"B{k + 1}", "arm": arm, "x_dots": X0, "y_dots": FIRST_Y + k * (BAND_H + GAP),
             "w_dots": SECTION_W, "h_dots": BAND_H, "cell_dots": cd, "rows": rows, "cols": cols, "gt_key": key}
        bands.append(b)
        paints += band_paints(arm, states[key], cd, X0, b["y_dots"], lookup)
    y = bands[-1]["y_dots"] + BAND_H + GAP
    checks = []
    for r, cd in enumerate((2, 3)):
        for j, pair in enumerate(PAIRS):
            c = {"id": f"chk-{pair}-c{cd}", "pair": list(pair), "cell_dots": cd, "construct": "mask-a85",
                 "x_dots": X0 + j * CHECK_PITCH, "y_dots": y + r * (CHECK_H + GAP), "w_dots": CHECK_W,
                 "h_dots": CHECK_H}
            checks.append(c)
            paints += checker_paints(pair, cd, c["x_dots"], c["y_dots"], lookup)
    y += 2 * (CHECK_H + GAP)
    bars = place_bars(bar_specs(rng_c2, lookup), np.random.default_rng(SEED_LAYOUT), y)
    for spec in bars:
        paints += bar_paints(spec, lookup)
    y = max(b["y_dots"] for b in bars) + BAR_PITCH_Y
    dots = []
    for k, (t, pat) in enumerate((t, pat) for t in "CMY" for pat in DOT_PATTERNS):
        d = {"id": f"dot-{t}-{pat}", "toner": t, "pattern": pat, "x_dots": X0 + k * DOT_PITCH, "y_dots": y,
             "w_dots": DOT_W, "h_dots": DOT_W}
        dots.append(d)
        paints.append(Mask(dot_pattern(pat), d["x_dots"], y, lookup[t], "ASCII85"))
    return Plan(lookup, states, fids, bands, checks, bars, dots, paints)


def geometry_checks(p: Plan) -> int:
    """Every rectangle inside the page and the section, none overlapping, the fields the band size; returns the
    last y used."""
    content = p.bands + p.checkerboards + p.bars + p.dots
    occ = np.zeros(PAGE_DOTS_XY[::-1], np.uint16)
    for r in p.fiducials + content:
        x, y, w, h = r["x_dots"], r["y_dots"], r["w_dots"], r["h_dots"]
        assert x >= 0 and y >= 0 and x + w <= PAGE_DOTS_XY[0] and y + h <= PAGE_DOTS_XY[1], r
        occ[y:y + h, x:x + w] += 1
    assert int(occ.max()) == 1, "overlapping rectangles"
    assert all(X0 <= r["x_dots"] and r["x_dots"] + r["w_dots"] <= X0 + SECTION_W for r in content)
    for b in p.bands:
        assert b["rows"] * b["cell_dots"] == BAND_H and b["cols"] * b["cell_dots"] == SECTION_W
    last_y = max(r["y_dots"] + r["h_dots"] for r in content)
    assert last_y <= LAST_END, f"content ends at {last_y} > {LAST_END}"
    return last_y


# ------------------------------------------------------------------------------------------------ emission

def jobid() -> str:
    return hashlib.sha256(SEED_STRING.encode()).hexdigest()[:8]


def job_text(p: Plan) -> str:
    assert PAGE_DOTS_XY == A4_DOTS_XY and s1.DPI == 600
    doc = PSDoc(PAGE_DOTS_XY, jobid(), title=TITLE, engine_dpi=s1.DPI)
    doc.begin_page()
    for paint in p.paints:
        s1.emit(doc, paint)
    doc.end_page()
    return doc.render()


def iref_matches(job: str, p: Plan) -> bool:
    band = next(b for b in p.bands if b["arm"] == "I-ref")
    return job.count(s1.iref_e041_block(band, p.states[band["gt_key"]], p.lookup)) == 1


def gt_arrays(p: Plan) -> dict[str, np.ndarray]:
    out = dict(p.states)
    out |= {b["gt_key"]: b["_bits"] for b in p.bars if b["kind"] == "scrambled"}
    out |= {d["id"]: dot_pattern(d["pattern"]) for d in p.dots}
    return out


def manifest(p: Plan, job_name: str, job: bytes) -> dict:
    bar_keys = ("id", "kind", "toner", "axis", "rgb", "construct", "x_dots", "y_dots", "w_dots", "h_dots")
    bars = [{**{k: b[k] for k in bar_keys}, "rgb": list(b["rgb"]) if b["rgb"] else None,
             "gt_key": b.get("gt_key")} for b in p.bars]
    return {"tag": TAG, "dpi": s1.DPI, "page_dots_xy": list(PAGE_DOTS_XY), "seed_cells": SEED_C2,
            "seed_cells_c3": SEED_C3, "seed_layout": SEED_LAYOUT,
            "lookup": {k: list(v) for k, v in p.lookup.items()}, "fiducials": p.fiducials, "bands": p.bands,
            "checkerboards": p.checkerboards, "bars": bars, "dots": p.dots,
            "job": {"file": job_name, "sha256": hashlib.sha256(job).hexdigest(), "bytes": len(job)}}


def build(lookup: str = "registry") -> tuple[Plan, bytes, dict, bytes, int]:
    p = plan(s1.LOOKUPS[lookup])
    last_y = geometry_checks(p)
    text = job_text(p)
    if not iref_matches(text, p):
        raise SystemExit("I-ref band is not e041's image block byte for byte")
    job = text.encode("ascii")
    return p, job, manifest(p, f"{TAG}.ps", job), s1.npz_bytes(gt_arrays(p)), last_y


# ------------------------------------------------------------------------------------------------ check

def check(job_path: Path, p: Plan) -> dict:
    page, painted = s1.planned_page(p)
    want = (page < 128).astype(np.uint8)
    res: dict = {}
    for label, fast in (("default_icc", False), ("fastcolor", True)):
        img, msg, rc = s1.render(job_path, fast)
        got = (img < 128).astype(np.uint8)
        res[label] = {
            "returncode": rc, "messages": msg,
            "rgb_inexact_dots_page": int((img != page).any(axis=2).sum()),
            "differing_dots_page": int((got != want).any(axis=2).sum()),
            "differing_dots_bands": {b["name"]: s1.rect_diff(got, want, b) for b in p.bands},
            "differing_dots_bars": sum(s1.rect_diff(got, want, b) for b in p.bars),
            "differing_dots_checkerboards": sum(s1.rect_diff(got, want, c) for c in p.checkerboards),
            "differing_dots_dots": sum(s1.rect_diff(got, want, d) for d in p.dots),
            "differing_dots_fiducials": sum(s1.rect_diff(got, want, f) for f in p.fiducials),
            "non_white_outside_painted": int(((img != 255).any(axis=2) & ~painted).sum()),
        }
    strict = s1.s12.gs(["-q", "-sDEVICE=nullpage"], job_path)
    res["nullpage"] = {"returncode": strict.returncode, "messages": (strict.stdout + strict.stderr).strip()}
    res["pass"] = (res["fastcolor"]["rgb_inexact_dots_page"] == 0
                   and all(res[k]["returncode"] == 0 and not res[k]["messages"] and res[k]["differing_dots_page"] == 0
                       and res[k]["non_white_outside_painted"] == 0 for k in ("default_icc", "fastcolor"))
                   and strict.returncode == 0 and not res["nullpage"]["messages"])
    return res


# ------------------------------------------------------------------------------------------------ main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path("build/e043b"), help="output directory")
    ap.add_argument("--check", action="store_true", help="gs renders + nullpage against the plan")
    ap.add_argument("--lookup", choices=sorted(s1.LOOKUPS), default="registry",
                    help="colour values: the registry's, or legacy-e043b = the values sheet 2 was printed with")
    a = ap.parse_args()
    p, job, man, nb, last_y = build(a.lookup)
    a.out.mkdir(parents=True, exist_ok=True)
    job_path = a.out / f"{TAG}.ps"
    job_path.write_bytes(job)
    (a.out / f"{TAG}.manifest.json").write_text(json.dumps(man, indent=1) + "\n")
    (a.out / f"{TAG}-gt.npz").write_bytes(nb)
    per_construct: dict[str, int] = {}
    for b in p.bars:
        per_construct[b["construct"]] = per_construct.get(b["construct"], 0) + 1
    print(f"{job_path}  sha256 {man['job']['sha256']}  {len(job)} bytes  J={jobid()}")
    print(f"bands {len(p.bands)}  checkerboards {len(p.checkerboards)}  bars {len(p.bars)} {per_construct}  "
          f"dots {len(p.dots)}  objects {len(p.paints)}  last y {last_y} (limit {LAST_END})  I-ref == e041 bytes")
    if a.check:
        res = check(job_path, p)
        print(json.dumps(res, indent=1))
        if not res["pass"]:
            raise SystemExit("check FAILED")


if __name__ == "__main__":
    main()
