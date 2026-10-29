"""e043 — the M281 cmy emission probe sheet (docs/CMY-PROBE-M281.md v0.2 §2-§3, workplan W1).

ONE plain PostScript job through holo.gen.ps.PSDoc (its DSC head, the guarded setpagedevice, %%EOF; no PJL,
no prologue, no HP operator outside the I-ref arm), A4 at 600 dpi, e041's section geometry:

  fiducials  the five of e041's fiducials() at their positions, drawn FIRST, each one K imagemask
             (put_bitmap's K construct), in FIDUCIAL_IMAGES order (F0 F1 F4 F2 F3)
  bands      five c2 bands (432 x 4392 dots at x 283, y 283 + k * 456), ONE four-state cell field
             (216 x 2196 cells of 2x2 dots, uniform over presence ids {0, 1, 2, 4}, default_rng(43)
             .choice(4)), identical in every band; arms in order M-hex (three put_bitmap masks at the
             registry values, ASCIIHex), M-a85 (the same, ASCII85), I-2 (put_indexed_image bpc 2, lookup
             W C M Y), I-8 (bpc 8), I-ref (bpc 8 behind e041's four guarded HP calls as S16 T12 used them;
             its block from gsave to grestore == e041's image_lines(...)[1:] + a85_lines(raw) + grestore,
             asserted)
  bars       192 x 48-dot bars: the §2 ladders as K-construct masks at device RGB (C's B ladder carries
             its registry end 255 so the table's 17 holds), the three registry values in each of the five
             constructs, four white bars (nothing painted), two scrambled bars (50 % dots at 1 dot per
             cell, C and M masks, drawn from the cell generator after the field), one screened control (an
             8-bit Indexed bar, hival 1, lookup [W, (128, 232, 255)], every index 1); 20 per row at pitch
             221 x 72 dots from 24 dots below the last band, value -> slot by default_rng(44).permutation,
             drawn in slot order

Outputs (--out DIR, default build/e043): E043-m281-cmy-probe.ps, .manifest.json (the frozen schema the
readout reads), -gt.npz ("states" + each scrambled bar's dots under its gt_key, fixed zip timestamps).
Values: the registry's hp-m281 rgb_solid (W = unpainted paper); --lookup legacy-e043a restores the printed
sheet's C (0, 208, 255) and regenerates its job byte for byte (sha d97a683f..., experiments/043 §043.1b).
--check: gs ppmraw -r600 twice (default ICC, -dUseFastColor), (R, G, B) < 128 -> (C, M, Y) against the
planned page dot for dot, nothing but white outside the painted rectangles, and a strict nullpage run.

    PYTHONPATH=src env/bin/python experiments/043-m281-cmy-probe/probe_sheet.py \\
        --out build/e043 --check
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

E041 = Path(__file__).resolve().parents[1] / "041-m281-screen-routes"
if str(E041) not in sys.path:
    sys.path.insert(0, str(E041))

import ps_mixture as s12  # noqa: E402
import ps_scale as s14  # noqa: E402
from pclxl_probe import DPI, FIDUCIALS_MM  # noqa: E402
from pclxl_probe_sheets import FIDUCIAL_IMAGES, fiducials  # noqa: E402

from holo.core.channel import states_to_planes  # noqa: E402
from holo.devices.registry import PRINTERS  # noqa: E402
from holo.gen.ps import A4_DOTS_XY, PSDoc  # noqa: E402

RGB = tuple[int, int, int]
TAG = "E043-m281-cmy-probe"
TITLE = "e043 M281 cmy probe"
SEED_CELLS, SEED_LAYOUT = 43, 44
SEED_STRING = f"{TAG} cells={SEED_CELLS} layout={SEED_LAYOUT}"
PAGE_DOTS_XY = (4960, 7016)
WHITE: RGB = (255, 255, 255)


def registry_lookup() -> dict[str, RGB]:
    """W (unpainted paper) + the registry's hp-m281 device-RGB solid points, C M Y."""
    solid = PRINTERS["hp-m281"].rgb_solid
    assert solid is not None and len(solid) == 3
    return {"W": WHITE, **dict(zip("CMY", solid))}


# "legacy-e043a" = the values sheet 1 was printed with (C at G 208), so its job regenerates byte-identically
LOOKUPS: dict[str, dict[str, RGB]] = {
    "registry": registry_lookup(),
    "legacy-e043a": {"W": WHITE, "C": (0, 208, 255), "M": (240, 0, 192), "Y": (255, 255, 0)},
    # "legacy-e043b" = the values sheet 2 was printed with (C at G 184; the registry until sheet 3)
    "legacy-e043b": {"W": WHITE, "C": (0, 184, 255), "M": (240, 0, 192), "Y": (255, 255, 0)},
}
PRESENCE_IDS = np.array((0, 1, 2, 4), np.uint8)
INDEX_OF_STATE = {0: 0, 1: 1, 2: 2, 4: 3}
CELL_DOTS, BAND_H_DOTS, CELL_ROWS, CELL_COLS = 2, 432, 216, 2196
BAND_X_DOTS, BAND_W_DOTS = s14.BAND_X_DOTS, s14.BAND_W_DOTS
FIRST_Y_DOTS, GAP_DOTS, LAST_END_DOTS = s14.FIRST_Y_DOTS, s14.GAP_DOTS, s14.LAST_END_DOTS
ARMS = ("M-hex", "M-a85", "I-2", "I-8", "I-ref")
CONSTRUCTS = ("mask-hex", "mask-a85", "I-2", "I-8", "I-ref")
BAR_W_DOTS, BAR_H_DOTS, BARS_PER_ROW, BAR_PITCH_X_DOTS, BAR_PITCH_Y_DOTS = 192, 48, 20, 221, 72
SCREENED_TINT: RGB = (128, 232, 255)
N_WHITE = 4
IREF_PRELUDE = (s12.hp_call(s12.NEUTRAL["process"], "HPImageNeutralAxis"),
                s12.hp_call(s12.HALFTONE["highlpi"], "ColorSmartImageHalftone"),
                s12.hp_call("Off", "HPColorTrapping"),
                s12.hp_call("false", "HPImageAdaptiveHalftoning"))
AXIS_CHANNELS = {"R": (0,), "G": (1,), "B": (2,), "RG": (0, 1)}


@dataclass(frozen=True)
class Ladder:
    name: str
    toner: str
    axis: str
    base: RGB  # the fixed channels; the swept ones are overwritten
    start: int
    stop: int
    step: int
    extra: tuple[int, ...] = ()

    def values(self) -> list[int]:
        return sorted(set(range(self.start, self.stop + 1, self.step)) | set(self.extra))

    def rgb(self, v: int) -> RGB:
        c = list(self.base)
        for i in AXIS_CHANNELS[self.axis]:
            c[i] = v
        return c[0], c[1], c[2]


# docs/CMY-PROBE-M281.md §2's table, row for row, with its bar counts
LADDERS = (
    (Ladder("C-G", "C", "G", (0, 0, 255), 160, 236, 2), 39),
    (Ladder("C-B", "C", "B", (0, 200, 0), 192, 255, 4, (255,)), 17),
    (Ladder("C-R", "C", "R", (0, 200, 255), 0, 32, 4), 9),
    (Ladder("M-R", "M", "R", (0, 0, 192), 220, 255, 2), 18),
    (Ladder("M-B2", "M", "B", (240, 0, 0), 150, 230, 2), 41),
    (Ladder("M-B4", "M", "B", (255, 0, 0), 150, 230, 4), 21),
    (Ladder("M-G", "M", "G", (240, 0, 192), 0, 32, 4), 9),
    (Ladder("Y-RG", "Y", "RG", (0, 0, 0), 200, 255, 4), 14),
    (Ladder("Y-B", "Y", "B", (255, 255, 0), 0, 48, 4), 13),
    (Ladder("Y-G", "Y", "G", (255, 0, 0), 192, 255, 4), 16),
    (Ladder("Y-R", "Y", "R", (0, 255, 0), 192, 255, 4), 16),
)


@dataclass(frozen=True)
class Mask:
    bits: np.ndarray
    x: int
    y: int
    rgb: RGB | None  # None = K, put_bitmap's setcmykcolor
    filt: str


@dataclass(frozen=True)
class Indexed:
    indices: np.ndarray
    lookup: tuple[RGB, ...]
    x: int
    y: int
    bpc: int
    prelude: tuple[str, ...]


Paint = Mask | Indexed


# ------------------------------------------------------------------------------------------------ plan

def expand(cells: np.ndarray, cell_dots: int) -> np.ndarray:
    return np.repeat(np.repeat(cells, cell_dots, axis=0), cell_dots, axis=1)


def cell_field(rng: np.random.Generator) -> np.ndarray:
    """The one c2 field: presence ids {0, 1, 2, 4} uniform, (216, 2196) cells, row-major."""
    return PRESENCE_IDS[rng.choice(4, size=(CELL_ROWS, CELL_COLS))]


def state_indices(states: np.ndarray) -> np.ndarray:
    out = np.zeros(states.shape, np.uint8)
    for s, i in INDEX_OF_STATE.items():
        out[states == s] = i
    return out


def wcmy(lookup: dict[str, RGB]) -> tuple[RGB, ...]:
    return tuple(lookup[k] for k in "WCMY")


def band_paints(arm: str, states: np.ndarray, x: int, y: int, lookup: dict[str, RGB]) -> list[Paint]:
    """One band's objects: three toner masks (M-*) or one Indexed image (I-*)."""
    if arm in ("M-hex", "M-a85"):
        planes = states_to_planes(states)
        filt = "ASCIIHex" if arm == "M-hex" else "ASCII85"
        return [Mask(expand(planes[..., p], CELL_DOTS), x, y, lookup[t], filt) for p, t in enumerate("CMY")]
    idx = expand(state_indices(states), CELL_DOTS)
    bpc = 2 if arm == "I-2" else 8
    return [Indexed(idx, wcmy(lookup), x, y, bpc, IREF_PRELUDE if arm == "I-ref" else ())]


def construct_paint(construct: str, fill: np.ndarray, rgb: RGB, x: int, y: int,
                    lookup: dict[str, RGB]) -> Paint:
    """A bar in one of the five constructs: `fill` = ink dots (masks) / lookup indices (Indexed)."""
    if construct in ("mask-hex", "mask-a85"):
        return Mask(fill, x, y, rgb, "ASCIIHex" if construct == "mask-hex" else "ASCII85")
    return Indexed(fill, wcmy(lookup), x, y, 2 if construct == "I-2" else 8,
                   IREF_PRELUDE if construct == "I-ref" else ())


def bar_specs(rng_cells: np.random.Generator, lookup: dict[str, RGB]) -> list[dict]:
    """Every bar in canonical order (ladders, registry x constructs, controls), slots not yet assigned."""
    specs: list[dict] = []
    for lad, n in LADDERS:
        vals = lad.values()
        if len(vals) != n:
            raise SystemExit(f"ladder {lad.name}: {len(vals)} bars, the table says {n}")
        specs += [{"id": f"{lad.name}-{v:03d}", "kind": "sweep", "toner": lad.toner, "axis": lad.axis,
                   "rgb": lad.rgb(v), "construct": "mask-hex"} for v in vals]
    for t in "CMY":
        specs += [{"id": f"reg-{t}-{c}", "kind": "registry", "toner": t, "axis": None, "rgb": lookup[t],
                   "construct": c} for c in CONSTRUCTS]
    specs += [{"id": f"white-{k + 1}", "kind": "white", "toner": None, "axis": None, "rgb": None,
               "construct": "none"} for k in range(N_WHITE)]
    for t in "CM":
        bits = (rng_cells.random((BAR_H_DOTS, BAR_W_DOTS)) < 0.5).astype(np.uint8)
        specs.append({"id": f"scrambled-{t}", "kind": "scrambled", "toner": t, "axis": None, "rgb": lookup[t],
                      "construct": "mask-hex", "gt_key": f"bar_scrambled-{t}", "_bits": bits})
    specs.append({"id": "screened-C50", "kind": "screened", "toner": "C", "axis": None, "rgb": SCREENED_TINT,
                  "construct": "I-8"})
    return specs


def bar_paints(spec: dict, lookup: dict[str, RGB]) -> list[Paint]:
    x, y = spec["x_dots"], spec["y_dots"]
    if spec["kind"] == "white":
        return []
    if spec["kind"] == "screened":
        return [Indexed(np.ones((BAR_H_DOTS, BAR_W_DOTS), np.uint8), (lookup["W"], SCREENED_TINT), x, y, 8, ())]
    if spec["kind"] == "scrambled":
        return [Mask(spec["_bits"], x, y, spec["rgb"], "ASCIIHex")]
    if spec["construct"].startswith("mask"):
        fill = np.ones((BAR_H_DOTS, BAR_W_DOTS), np.uint8)
    else:
        fill = np.full((BAR_H_DOTS, BAR_W_DOTS), "WCMY".index(spec["toner"]), np.uint8)
    return [construct_paint(spec["construct"], fill, spec["rgb"], x, y, lookup)]


def band_y(k: int) -> int:
    return FIRST_Y_DOTS + k * (BAND_H_DOTS + GAP_DOTS)


def grid_y0() -> int:
    return band_y(len(ARMS) - 1) + BAND_H_DOTS + GAP_DOTS


def place_bars(specs: list[dict], rng_layout: np.random.Generator) -> list[dict]:
    """Bar i takes slot perm[i]; returned in slot (= draw) order with x/y/w/h dots."""
    perm = rng_layout.permutation(len(specs))
    for spec, slot in zip(specs, perm):
        row, col = divmod(int(slot), BARS_PER_ROW)
        spec |= {"x_dots": BAND_X_DOTS + col * BAR_PITCH_X_DOTS, "y_dots": grid_y0() + row * BAR_PITCH_Y_DOTS,
                 "w_dots": BAR_W_DOTS, "h_dots": BAR_H_DOTS, "_slot": int(slot)}
    return sorted(specs, key=lambda s: s["_slot"])


def fiducial_records() -> list[dict]:
    order = [f for _, ids in FIDUCIAL_IMAGES for f in ids]
    assert sorted(order) == sorted(f[0] for f in FIDUCIALS_MM)
    by_id = {f["id"]: f for f in fiducials()}
    out = []
    for fid in order:
        f = by_id[fid]
        x, y, w, h = f["_xywh"]
        out.append({"id": fid, "x_mm": f["x_mm"], "y_mm": f["y_mm"], "w_mm": f["w_mm"], "h_mm": f["h_mm"],
                    "x_dots": x, "y_dots": y, "w_dots": w, "h_dots": h})
    return out


@dataclass(frozen=True)
class Plan:
    lookup: dict[str, RGB]
    states: np.ndarray
    fiducials: list[dict]
    bands: list[dict]
    bars: list[dict]
    paints: list[Paint]  # draw order


def plan(lookup: dict[str, RGB]) -> Plan:
    rng_cells, rng_layout = np.random.default_rng(SEED_CELLS), np.random.default_rng(SEED_LAYOUT)
    states = cell_field(rng_cells)
    fids = fiducial_records()
    paints: list[Paint] = [Mask(np.ones((f["h_dots"], f["w_dots"]), np.uint8), f["x_dots"], f["y_dots"], None,
                                "ASCIIHex") for f in fids]
    bands = []
    for k, arm in enumerate(ARMS):
        b = {"name": f"B{k + 1}", "arm": arm, "x_dots": BAND_X_DOTS, "y_dots": band_y(k), "w_dots": BAND_W_DOTS,
             "h_dots": BAND_H_DOTS, "cell_dots": CELL_DOTS, "rows": CELL_ROWS, "cols": CELL_COLS,
             "gt_key": "states"}
        bands.append(b)
        paints += band_paints(arm, states, b["x_dots"], b["y_dots"], lookup)
    bars = place_bars(bar_specs(rng_cells, lookup), rng_layout)
    for spec in bars:
        paints += bar_paints(spec, lookup)
    return Plan(lookup, states, fids, bands, bars, paints)


def geometry_checks(p: Plan) -> int:
    """Every band and bar inside the page and above e041's last line, no two rectangles overlapping, the
    band field the right size; returns the last y used by bands and bars."""
    rects = [(r["x_dots"], r["y_dots"], r["w_dots"], r["h_dots"]) for r in p.fiducials + p.bands + p.bars]
    occ = np.zeros(PAGE_DOTS_XY[::-1], np.uint16)
    for x, y, w, h in rects:
        assert x >= 0 and y >= 0 and x + w <= PAGE_DOTS_XY[0] and y + h <= PAGE_DOTS_XY[1], (x, y, w, h)
        occ[y:y + h, x:x + w] += 1
    assert int(occ.max()) == 1, "overlapping rectangles"
    last_y = max(r["y_dots"] + r["h_dots"] for r in p.bands + p.bars)
    assert last_y <= LAST_END_DOTS, f"content ends at {last_y} > {LAST_END_DOTS}"
    assert max(b["x_dots"] + b["w_dots"] for b in p.bars) <= BAND_X_DOTS + BAND_W_DOTS
    assert CELL_ROWS * CELL_DOTS == BAND_H_DOTS and CELL_COLS * CELL_DOTS == BAND_W_DOTS
    return last_y


# ------------------------------------------------------------------------------------------------ emission

def jobid() -> str:
    return hashlib.sha256(SEED_STRING.encode()).hexdigest()[:8]


def emit(doc: PSDoc, paint: Paint) -> None:
    if isinstance(paint, Mask):
        doc.put_bitmap(paint.bits, paint.x, paint.y, rgb=paint.rgb, filt=paint.filt)
    else:
        doc.put_indexed_image(paint.indices, paint.lookup, paint.x, paint.y, bpc=paint.bpc,
                              prelude=paint.prelude)


def job_text(p: Plan) -> str:
    assert PAGE_DOTS_XY == A4_DOTS_XY == s12.PAGE_HW_DOTS[::-1] and DPI == 600
    doc = PSDoc(PAGE_DOTS_XY, jobid(), title=TITLE, engine_dpi=DPI)
    doc.begin_page()
    for paint in p.paints:
        emit(doc, paint)
    doc.end_page()
    return doc.render()


def iref_e041_block(band: dict, states: np.ndarray, lookup: dict[str, RGB]) -> str:
    """e041's own bytes for the I-ref band: image_lines(...)[1:] + a85_lines(raw) + grestore."""
    idx = expand(state_indices(states), CELL_DOTS)
    xywh = (band["x_dots"], band["y_dots"], band["w_dots"], band["h_dots"])
    lines = s12.image_lines("% I-ref", xywh, np.array(wcmy(lookup), np.uint8), list(IREF_PRELUDE))[1:]
    return "\n".join(lines) + "\n" + s12.a85_lines(idx.tobytes()).decode("ascii") + "grestore\n"


def iref_matches(job: str, p: Plan) -> bool:
    band = next(b for b in p.bands if b["arm"] == "I-ref")
    return job.count(iref_e041_block(band, p.states, p.lookup)) == 1


def npz_bytes(arrays: dict[str, np.ndarray]) -> bytes:
    """np.savez_compressed's layout with a fixed timestamp (e041 ps_scale.npz_bytes)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for key in sorted(arrays):
            one = io.BytesIO()
            np.lib.format.write_array(one, np.ascontiguousarray(arrays[key]), allow_pickle=False)
            info = zipfile.ZipInfo(f"{key}.npy", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, one.getvalue())
    return buf.getvalue()


def gt_arrays(p: Plan) -> dict[str, np.ndarray]:
    out = {"states": p.states}
    out |= {b["gt_key"]: b["_bits"] for b in p.bars if b["kind"] == "scrambled"}
    return out


def manifest(p: Plan, job_name: str, job: bytes) -> dict:
    bar_keys = ("id", "kind", "toner", "axis", "rgb", "construct", "x_dots", "y_dots", "w_dots", "h_dots")
    bars = [{**{k: b[k] for k in bar_keys}, "rgb": list(b["rgb"]) if b["rgb"] else None,
             "gt_key": b.get("gt_key")} for b in p.bars]
    return {"tag": TAG, "dpi": DPI, "page_dots_xy": list(PAGE_DOTS_XY), "seed_cells": SEED_CELLS,
            "seed_layout": SEED_LAYOUT, "lookup": {k: list(v) for k, v in p.lookup.items()},
            "fiducials": p.fiducials, "bands": p.bands, "bars": bars,
            "job": {"file": job_name, "sha256": hashlib.sha256(job).hexdigest(), "bytes": len(job)}}


def build(lookup_name: str = "registry") -> tuple[Plan, bytes, dict, bytes, int]:
    p = plan(LOOKUPS[lookup_name])
    last_y = geometry_checks(p)
    text = job_text(p)
    if not iref_matches(text, p):
        raise SystemExit("I-ref band is not e041's image block byte for byte")
    job = text.encode("ascii")
    return p, job, manifest(p, f"{TAG}.ps", job), npz_bytes(gt_arrays(p)), last_y


# ------------------------------------------------------------------------------------------------ check

def planned_page(p: Plan) -> tuple[np.ndarray, np.ndarray]:
    """(the device RGB page as planned, K = (0, 0, 0); the union of painted rectangles)."""
    w, h = PAGE_DOTS_XY
    page = np.full((h, w, 3), 255, np.uint8)
    painted = np.zeros((h, w), bool)
    for q in p.paints:
        if isinstance(q, Mask):
            ph, pw = q.bits.shape
            region = page[q.y:q.y + ph, q.x:q.x + pw]
            region[q.bits != 0] = q.rgb or (0, 0, 0)
        else:
            ph, pw = q.indices.shape
            page[q.y:q.y + ph, q.x:q.x + pw] = np.array(q.lookup, np.uint8)[q.indices]
        painted[q.y:q.y + ph, q.x:q.x + pw] = True
    return page, painted


def render(job_path: Path, fast: bool) -> tuple[np.ndarray, str, int]:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "e043.ppm"
        args = ["-q", *(["-dUseFastColor"] if fast else []), "-sDEVICE=ppmraw", "-r600",
                f"-g{PAGE_DOTS_XY[0]}x{PAGE_DOTS_XY[1]}", f"-sOutputFile={out}"]
        r = s12.gs(args, job_path)
        return s12.read_ppm(out).copy(), (r.stdout + r.stderr).strip(), r.returncode


def rect_diff(got: np.ndarray, want: np.ndarray, r: dict) -> int:
    y, x, h, w = r["y_dots"], r["x_dots"], r["h_dots"], r["w_dots"]
    return int((got[y:y + h, x:x + w] != want[y:y + h, x:x + w]).any(axis=2).sum())


def check(job_path: Path, p: Plan) -> dict:
    page, painted = planned_page(p)
    want = (page < 128).astype(np.uint8)
    res: dict = {}
    for label, fast in (("default_icc", False), ("fastcolor", True)):
        img, msg, rc = render(job_path, fast)
        got = (img < 128).astype(np.uint8)
        res[label] = {
            "returncode": rc, "messages": msg,
            "rgb_inexact_dots_page": int((img != page).any(axis=2).sum()),
            "differing_dots_page": int((got != want).any(axis=2).sum()),
            "differing_dots_bands": {b["name"]: rect_diff(got, want, b) for b in p.bands},
            "differing_dots_bars": sum(rect_diff(got, want, b) for b in p.bars),
            "differing_dots_fiducials": sum(rect_diff(got, want, f) for f in p.fiducials),
            "non_white_outside_painted": int(((img != 255).any(axis=2) & ~painted).sum()),
        }
    strict = s12.gs(["-q", "-sDEVICE=nullpage"], job_path)
    res["nullpage"] = {"returncode": strict.returncode, "messages": (strict.stdout + strict.stderr).strip()}
    res["pass"] = (res["fastcolor"]["rgb_inexact_dots_page"] == 0
                   and all(res[k]["returncode"] == 0 and not res[k]["messages"] and res[k]["differing_dots_page"] == 0
                       and res[k]["non_white_outside_painted"] == 0 for k in ("default_icc", "fastcolor"))
                   and strict.returncode == 0 and not res["nullpage"]["messages"])
    return res


# ------------------------------------------------------------------------------------------------ main

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=Path("build/e043"), help="output directory")
    ap.add_argument("--check", action="store_true", help="gs renders + nullpage against the plan")
    ap.add_argument("--lookup", choices=sorted(LOOKUPS), default="registry",
                    help="device-RGB values: the registry's hp-m281 points, or legacy-e043a (the printed sheet "
                         "1, C (0, 208, 255), sha d97a683f...)")
    a = ap.parse_args()
    p, job, man, nb, last_y = build(a.lookup)
    a.out.mkdir(parents=True, exist_ok=True)
    job_path = a.out / f"{TAG}.ps"
    job_path.write_bytes(job)
    (a.out / f"{TAG}.manifest.json").write_text(json.dumps(man, indent=1) + "\n")
    (a.out / f"{TAG}-gt.npz").write_bytes(nb)
    kinds: dict[str, int] = {}
    for b in p.bars:
        kinds[b["kind"]] = kinds.get(b["kind"], 0) + 1
    print(f"{job_path}  sha256 {man['job']['sha256']}  {len(job)} bytes")
    print(f"bands {len(p.bands)}  bars {len(p.bars)} {kinds}  objects {len(p.paints)}  last y {last_y} "
          f"(limit {LAST_END_DOTS})  I-ref == e041 bytes")
    if a.check:
        res = check(job_path, p)
        print(json.dumps(res, indent=1))
        if not res["pass"]:
            raise SystemExit("check FAILED")


if __name__ == "__main__":
    main()
