"""e043c — the M281 cmy probe sheet 3 (docs/CMY-PROBE-M281.md §10): the candidate values inside full-width random
cmy cell fields at c2 and c3, one variable per band against one base, and the nine values as bars in three zones.

ONE plain PostScript job through holo.gen.ps.PSDoc, A4 at 600 dpi, e041's section geometry, sheets 1-2's
conventions (probe_sheet.py and probe_sheet2.py, imported): no PJL, no prologue, no HP operator, masks only
(mask-a85: single-toner imagemasks, ASCII85; W = unpainted paper). The values are §10's table, not the registry:
base C (0, 176, 255), M (240, 0, 192), Y (255, 255, 0). Top to bottom, drawn in this order:

  fiducials  sheet 1's five K imagemasks (ASCIIHex)
  bands      B1-B15 at x 283, y 283 + k * 384, 336 x 4392 dots, §10's table row for row, each its own lookup
             {W, C, M, Y}: the c2 field (default_rng(47), 168 x 2196 cells of 2 dots) in every c2 band, the c3
             field (default_rng(48), 112 x 1464 cells of 3 dots) in every c3 band, presence ids {0, 1, 2, 4}
             uniform; three ASCII85 masks per band (C, M, Y)
  bars       192 x 48-dot mask bars from 48 dots below the last band, rows at a 72-dot pitch: the nine values
             (C G 176 178 184 192 at (0, G, 255) axis "G", M (240, 0, 192) (240, 0, 194) (242, 0, 192)
             (238, 0, 192) axis "grid", Y (255, 255, 0) axis "B") and one white, in each of three zones (left
             x 12-47 mm, middle 97-131, right 158-182); per zone the columns at a 292-dot pitch centred in the
             zone (3, 3, 2), BAR_ROWS rows, value -> slot by default_rng(49).permutation (left, middle, right);
             construct "mask-a85@<x mm>" (white: "none"), drawn in (y, x) order

Outputs (--out DIR, default build/e043c): E043c-m281-cmy-probe3.ps, .manifest.json, -gt.npz (states_c2,
states_c3; fixed zip timestamps). --check as sheet 2: gs ppmraw -r600 with the default ICC and -dUseFastColor,
(R, G, B) < 128 -> (C, M, Y) against the plan per band and bar, nothing but white outside the painted
rectangles, a strict nullpage run, and a second build byte-identical.

    PYTHONPATH=src:. env/bin/python experiments/043-m281-cmy-probe/probe_sheet3.py \\
        --out build/e043c --check
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import probe_sheet as s1  # noqa: E402
import probe_sheet2 as s2  # noqa: E402
from probe_sheet import RGB, Mask, Paint  # noqa: E402
from probe_sheet2 import Plan  # noqa: E402

from holo.gen.ps import A4_DOTS_XY, PSDoc  # noqa: E402

TAG = "E043c-m281-cmy-probe3"
TITLE = "e043c M281 cmy probe 3"
SEED_C2, SEED_C3, SEED_LAYOUT = 47, 48, 49
SEED_STRING = f"{TAG} cells_c2={SEED_C2} cells_c3={SEED_C3} layout={SEED_LAYOUT}"
PAGE_DOTS_XY = s1.PAGE_DOTS_XY
X0, SECTION_W, FIRST_Y, LAST_END = s1.BAND_X_DOTS, s1.BAND_W_DOTS, s1.FIRST_Y_DOTS, s1.LAST_END_DOTS
BAND_H, GAP = 336, 48
ARM = "mask-a85"
BASE: dict[str, RGB] = {"W": s1.WHITE, "C": (0, 176, 255), "M": (240, 0, 192), "Y": (255, 255, 0)}
# §10's table row for row: (cell dots, cyan G, magenta (R, B), why); a blank why carries its c2 row's
BANDS: tuple[tuple[int, int, tuple[int, int], str], ...] = (
    (2, 176, (240, 192), "the base"),
    (3, 176, (240, 192), "the base"),
    (2, 178, (240, 192), "cyan candidate"),
    (3, 178, (240, 192), "cyan candidate"),
    (2, 184, (240, 192), "the registry today; sheet 2's bands"),
    (3, 184, (240, 192), "the registry today; sheet 2's bands"),
    (2, 192, (240, 192), "past the in-zone edge: the stipple's slope"),
    (3, 192, (240, 192), "past the in-zone edge: the stipple's slope"),
    (2, 176, (240, 194), "magenta candidate"),
    (3, 176, (240, 194), "magenta candidate"),
    (2, 176, (242, 192), "the eye's row"),
    (3, 176, (242, 192), "the eye's row"),
    (2, 176, (238, 192), "the speckled row: do cyan specks in M cells matter in a field"),
    (2, 176, (240, 192), "the base again, bottom of the page: drift along y"),
    (3, 176, (240, 192), "the base again, bottom of the page: drift along y"),
)
ZONES_MM: tuple[tuple[str, int, int], ...] = (("left", 12, 47), ("middle", 97, 131), ("right", 158, 182))
BAR_W, BAR_H, BAR_PITCH_X, BAR_PITCH_Y = s2.BAR_W, s2.BAR_H, 292, s2.BAR_PITCH_Y
PAGE_INSET_DOTS = math.ceil(4 * s1.DPI / 25.4)  # every rectangle inside the page less 4 mm


# ------------------------------------------------------------------------------------------------ plan

def mm_to_dots(mm: float) -> int:
    return round(mm * s1.DPI / 25.4)


def dots_to_mm(dots: int) -> float:
    return dots * 25.4 / s1.DPI


def band_lookup(c_g: int, m_rb: tuple[int, int]) -> dict[str, RGB]:
    return {"W": s1.WHITE, "C": (0, c_g, 255), "M": (m_rb[0], 0, m_rb[1]), "Y": BASE["Y"]}


def cell_field(seed: int, cell_dots: int) -> np.ndarray:
    """One seeded field: presence ids {0, 1, 2, 4} uniform, (BAND_H, SECTION_W) / cell_dots cells, row-major."""
    rows, cols = BAND_H // cell_dots, SECTION_W // cell_dots
    return s1.PRESENCE_IDS[np.random.default_rng(seed).choice(4, size=(rows, cols))]


def bar_values() -> list[tuple[str, str, RGB]]:
    """(toner, axis, rgb) of the nine values, in the table's first-appearance order: cyan, magenta, yellow."""
    cyan = sorted({g for _, g, _, _ in BANDS})
    magenta = list(dict.fromkeys(m for _, _, m, _ in BANDS))
    out = [("C", "G", (0, g, 255)) for g in cyan]
    out += [("M", "grid", (r, 0, b)) for r, b in magenta]
    return out + [("Y", "B", BASE["Y"])]


def zone_columns(lo_mm: int, hi_mm: int) -> list[int]:
    """x of every bar column in a zone: as many as fit at BAR_PITCH_X, the group centred in the zone."""
    lo, hi = mm_to_dots(lo_mm), mm_to_dots(hi_mm)
    n = (hi - lo - BAR_W) // BAR_PITCH_X + 1
    x0 = lo + (hi - lo - (n - 1) * BAR_PITCH_X - BAR_W) // 2
    return [x0 + k * BAR_PITCH_X for k in range(n)]


def bars_per_zone() -> int:
    return len(bar_values()) + 1


# the right zone (567 dots) holds two 192-dot bars per row at any pitch: its ten bars need five rows
BAR_ROWS = max(-(-bars_per_zone() // len(zone_columns(lo, hi))) for _, lo, hi in ZONES_MM)


def bar_specs(zone: str) -> list[dict]:
    """One zone's bars in canonical order (the nine values, then white), slots unassigned."""
    specs = [{"id": s2.sweep_id(t, rgb, zone), "kind": "sweep", "toner": t, "axis": axis, "rgb": rgb}
             for t, axis, rgb in bar_values()]
    return specs + [{"id": f"white-{zone}", "kind": "white", "toner": None, "axis": None, "rgb": None}]


def place_bars(rng_layout: np.random.Generator, y0: int) -> list[dict]:
    """Per zone (left, middle, right) bar i takes slot perm[i] of the zone's columns x BAR_ROWS; returned in
    (y, x) = draw order with construct, x/y/w/h dots, gt_key and zone."""
    bars = []
    for zone, lo, hi in ZONES_MM:
        cols = zone_columns(lo, hi)
        perm = rng_layout.permutation(len(cols) * BAR_ROWS)
        for spec, slot in zip(bar_specs(zone), perm):
            row, col = divmod(int(slot), len(cols))
            x = cols[col]
            construct = f"{ARM}@{round(dots_to_mm(x))}" if spec["kind"] == "sweep" else "none"
            bars.append({**spec, "construct": construct, "x_dots": x, "y_dots": y0 + row * BAR_PITCH_Y,
                         "w_dots": BAR_W, "h_dots": BAR_H, "gt_key": None, "zone": zone})
    return sorted(bars, key=lambda b: (b["y_dots"], b["x_dots"]))


def bar_paints(spec: dict) -> list[Paint]:
    """Dispatch on the construct's prefix: a mask bar is sheet 2's mask-a85 bar; white paints nothing."""
    if spec["kind"] == "white":
        return []
    assert spec["construct"].startswith("mask"), spec
    return s2.bar_paints({**spec, "construct": spec["construct"].split("@")[0]}, BASE)


def plan() -> Plan:
    states = {"states_c2": cell_field(SEED_C2, 2), "states_c3": cell_field(SEED_C3, 3)}
    fids = s1.fiducial_records()
    paints: list[Paint] = [Mask(np.ones((f["h_dots"], f["w_dots"]), np.uint8), f["x_dots"], f["y_dots"], None,
                                "ASCIIHex") for f in fids]
    bands = []
    for k, (cd, c_g, m_rb, note) in enumerate(BANDS):
        key, lookup = f"states_c{cd}", band_lookup(c_g, m_rb)
        rows, cols = states[key].shape
        b = {"name": f"B{k + 1}", "arm": ARM, "x_dots": X0, "y_dots": FIRST_Y + k * (BAND_H + GAP),
             "w_dots": SECTION_W, "h_dots": BAND_H, "cell_dots": cd, "rows": rows, "cols": cols, "gt_key": key,
             "lookup": {t: list(v) for t, v in lookup.items()}, "note": note}
        bands.append(b)
        paints += s2.band_paints(ARM, states[key], cd, X0, b["y_dots"], lookup)
    bars = place_bars(np.random.default_rng(SEED_LAYOUT), bands[-1]["y_dots"] + BAND_H + GAP)
    for spec in bars:
        paints += bar_paints(spec)
    return Plan(BASE, states, fids, bands, [], bars, [], paints)


def geometry_checks(p: Plan) -> int:
    """Every rectangle inside the page less 4 mm and none overlapping, bands and bars inside the section, every
    bar inside its zone, the fields the band size; returns the last y used."""
    content = p.bands + p.bars
    occ = np.zeros(PAGE_DOTS_XY[::-1], np.uint16)
    lo, hx, hy = PAGE_INSET_DOTS, PAGE_DOTS_XY[0] - PAGE_INSET_DOTS, PAGE_DOTS_XY[1] - PAGE_INSET_DOTS
    for r in p.fiducials + content:
        x, y, w, h = r["x_dots"], r["y_dots"], r["w_dots"], r["h_dots"]
        assert x >= lo and y >= lo and x + w <= hx and y + h <= hy, r
        occ[y:y + h, x:x + w] += 1
    assert int(occ.max()) == 1, "overlapping rectangles"
    assert all(X0 <= r["x_dots"] and r["x_dots"] + r["w_dots"] <= X0 + SECTION_W for r in content)
    zones = {z: (mm_to_dots(a), mm_to_dots(b)) for z, a, b in ZONES_MM}
    for b in p.bars:
        z0, z1 = zones[b["zone"]]
        assert z0 <= b["x_dots"] and b["x_dots"] + b["w_dots"] <= z1, b
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


def manifest(p: Plan, job_name: str, job: bytes) -> dict:
    bar_keys = ("id", "kind", "toner", "axis", "rgb", "construct", "x_dots", "y_dots", "w_dots", "h_dots",
                "gt_key", "zone")
    bars = [{**{k: b[k] for k in bar_keys}, "rgb": list(b["rgb"]) if b["rgb"] else None} for b in p.bars]
    return {"tag": TAG, "dpi": s1.DPI, "page_dots_xy": list(PAGE_DOTS_XY), "seed_cells": SEED_C2,
            "seed_cells_c3": SEED_C3, "seed_layout": SEED_LAYOUT,
            "lookup": {k: list(v) for k, v in p.lookup.items()}, "fiducials": p.fiducials, "bands": p.bands,
            "bars": bars, "job": {"file": job_name, "sha256": hashlib.sha256(job).hexdigest(), "bytes": len(job)}}


def build() -> tuple[Plan, bytes, dict, bytes, int]:
    p = plan()
    last_y = geometry_checks(p)
    job = job_text(p).encode("ascii")
    return p, job, manifest(p, f"{TAG}.ps", job), s1.npz_bytes(dict(p.states)), last_y


def manifest_bytes(man: dict) -> bytes:
    return (json.dumps(man, indent=1) + "\n").encode()


# ------------------------------------------------------------------------------------------------ check

def check(job_path: Path, p: Plan, job: bytes, man: dict, nb: bytes) -> dict:
    """Sheet 2's gs gate (both colour paths, nullpage) over bands and bars, plus a second build byte-identical."""
    res = s2.check(job_path, p)
    for label in ("default_icc", "fastcolor"):
        for key in ("differing_dots_checkerboards", "differing_dots_dots"):
            del res[label][key]
    _, job2, man2, nb2, _ = build()
    res["second_build_identical"] = job2 == job and manifest_bytes(man2) == manifest_bytes(man) and nb2 == nb
    res["pass"] = res.pop("pass") and res["second_build_identical"]
    return res


# ------------------------------------------------------------------------------------------------ main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path("build/e043c"), help="output directory")
    ap.add_argument("--check", action="store_true", help="gs renders + nullpage against the plan, a second build")
    a = ap.parse_args()
    p, job, man, nb, last_y = build()
    a.out.mkdir(parents=True, exist_ok=True)
    job_path = a.out / f"{TAG}.ps"
    job_path.write_bytes(job)
    (a.out / f"{TAG}.manifest.json").write_bytes(manifest_bytes(man))
    (a.out / f"{TAG}-gt.npz").write_bytes(nb)
    per_zone: dict[str, int] = {}
    for b in p.bars:
        per_zone[b["zone"]] = per_zone.get(b["zone"], 0) + 1
    print(f"{job_path}  sha256 {man['job']['sha256']}  {len(job)} bytes  J={jobid()}")
    print(f"bands {len(p.bands)}  bars {len(p.bars)} {per_zone} ({BAR_ROWS} rows)  objects {len(p.paints)}  "
          f"last y {last_y} (limit {LAST_END})")
    if a.check:
        res = check(job_path, p, job, man, nb)
        print(json.dumps(res, indent=1))
        if not res["pass"]:
            raise SystemExit("check FAILED")


if __name__ == "__main__":
    main()
