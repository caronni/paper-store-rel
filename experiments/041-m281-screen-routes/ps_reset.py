"""e041 S15 — the RESET probe for the HP M281 on the production route (PostScript), on S14's footing.

THE QUESTION.  S14 (ps_scale.py, printed, page 3401) showed the engine's screen switching per COLUMN REGION
of a full-width noise band: cmy4 bands never screened; the cmy8 band (S9's palette) screened everywhere but
x 12-20 mm and 108-117 mm; the cmyk5 bands everywhere but x 12-35 mm and 108-142 mm; the state error follows
the screen column for column.  Hypothesis: a region starts unscreened at a fixed boundary (the image / page
left edge, ~108 mm) and a content-driven switch turns the screen on after a content-dependent distance.
Does something RESET the switch?  S15 asks it of three candidates, on cmy8 and cmyk5:
  a thin WHITE gap (one c3 cell column = 3 dots every 10 mm; eight cell columns = 24 dots every 20 mm),
  an OBJECT boundary (the band cut into 24 abutting images of 183 dots: the object split S14 lacked for
  cmy8), an IMAGE LEFT EDGE away from the page edge (a cmy8 band starting at x = 50 mm),
beside the production candidate cmy4 with the solid cyan (0, 208, 255) at c3 Smooth and c2 Detail.

BANDS (top to bottom = draw order, all section A = matching at the device default, all c3 Smooth unless
said; R1-R5 cmy8-engine under ProcBlack, R6-R7 cmyk5 under TonerBlack, R8-R9 cmy4-solidC under ProcBlack):
R1 control (one image) | R2 24 abutting tiles | R3 3-dot gap every 10 mm | R4 24-dot gap every 20 mm |
R5 one image from x 1182 dots (50 mm), the 12-50 mm span white | R6 cmyk5 3-dot gap every 10 mm |
R7 cmyk5 24 tiles | R8 cmy4 C-solid control | R9 cmy4 C-solid c2 Detail, height to fill.
A gap is whole CELL COLUMNS forced to the W state in the band's state map after the draw, so every cell
keeps a known state and the readout needs no special case.

ROUTE AND FOOTING = S14's: S1's PJL wrapper without BITSPERPIXEL / RET (JOB NAME "E041-S15-PS-RESET"), S14's
DSC header shape, F's setpagedevice line, S12's bare-name prologue byte for byte, then every image inside
gsave/grestore as an 8-bit [/Indexed /DeviceRGB hival <lookup>] image, ASCII85, 0.12 pt per dot, behind
`where` guards in S14's section-A order: <ProcBlack|TonerBlack> HPImageNeutralAxis, <Smooth|Detail>
ColorSmartImageHalftone, Off HPColorTrapping, false HPImageAdaptiveHalftoning.  No ColorSmartColorMatching
call anywhere (S14: no effect).  The five fiducials are S14's three fiducial images, drawn first.

STATES: per band iid uniform over the alphabet, numpy default_rng(52000 + band index).choice(len(alphabet),
size=(rows, cols)), band index = position in the table (R1 = 0 .. R9 = 8), cells row-major, THEN the gap
columns forced to W.  R2's and R7's tiles are slices of ONE band raster.

Outputs (beside --out): the job, <stem>.manifest.json in S14's schema (bands with "gaps" and "variant", an
empty bar list, windows of 31x31 c3 / 46x46 c2 cells tiling each band from its top-left) and
<stem>-bands.npz (states_<band>, planes_<band>), fixed zip timestamps.

--verify: (1) gs ppmraw -r600 render == the page composed from manifest + npz, fiducials black, white
elsewhere (R5's empty span and every gap included); (2) gs strict silent + the stub run's HP-call log, exact;
(3) byte audit against S14; (4) every window's states / planes against the render, gap columns W and white;
(5) geometry; (6) two builds identical; (7) S14 and S12 rebuilt unchanged; (8) novelty vs the printed S14 and
S12; (9) sizes; (10) readout compatibility: measure/e041_scale_readout.py and measure/e041_band_screen.py run
unchanged on an in-memory clean synthetic scan (e041_scale_synth.page_raster at 4x4 px per dot, identity
pose; no TIFF written).

    PYTHONPATH=src:. env/bin/python \\
        experiments/041-m281-screen-routes/ps_reset.py \\
        --out experiments/041-m281-screen-routes/build/S15-ps-reset.ps --verify
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import re
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import ps_mixture as s12
import ps_scale as s14
from pcl_planar import sha
from pclxl_probe import DPI, mm

TAG = "S15-ps-reset"
JOB_NAME = "E041-S15-PS-RESET"
S14_SHA256 = "6081414085e912573a970c5b1ab6c0c939373f2e0e751e21c6582958af3e0689"
PAGE_H_DOTS, PAGE_W_DOTS = s12.PAGE_HW_DOTS
WRAPPER_HEAD = s12.UEL + f'@PJL JOB NAME="{JOB_NAME}"\r\n@PJL ENTER LANGUAGE=POSTSCRIPT\r\n'.encode()
HEADER = s14.HEADER.replace(b"page-scale probe", b"reset probe").replace(b"ps_scale.py", b"ps_reset.py")
TAIL = s14.TAIL
SECTION = "A"                                   # every image: matching at the device default, no call

RGB = tuple[int, int, int]
PALETTE: dict[str, RGB] = s14.PALETTE | {"C-solid": (0, 208, 255)}
INK = s14.INK | {"C-solid": "C"}
ALPHABETS: dict[str, tuple[str, ...]] = {
    "cmy8-engine": s14.ALPHABETS["cmy8-engine"],
    "cmyk5": s14.ALPHABETS["cmyk5"],
    "cmy4-solidC": ("W", "C-solid", "M-solid", "Y")}
BAND_X_DOTS, BAND_W_DOTS = s14.BAND_X_DOTS, s14.BAND_W_DOTS
FIRST_Y_DOTS, GAP_DOTS, LAST_END_DOTS = s14.FIRST_Y_DOTS, s14.GAP_DOTS, s14.LAST_END_DOTS
TILES, TILE_W_DOTS = s14.B2_TILES, s14.B2_TILE_W_DOTS
OFFSET_X_DOTS, OFFSET_W_DOTS = 1182, 3492       # R5: 50.04 mm .. 197.86 mm
SEED_BASE = 52000
VARIANTS = ("control", "tiles", "gap3_10mm", "gap24_20mm", "offset50mm", "cmy4_solidC", "cmy4_solidC_c2")


@dataclass(frozen=True)
class GapSpec:
    first_cell: int          # first gap's leftmost cell column
    period_cells: int        # gap starts every period_cells cell columns
    cell_cols: int           # cell columns per gap


GAP3_10MM = GapSpec(39, 79, 1)      # 3 dots every 237 dots = 10.03 mm, the first at 4.95 mm
GAP24_20MM = GapSpec(79, 158, 8)    # 24 dots every 474 dots = 20.07 mm, the first at 10.03 mm


@dataclass(frozen=True)
class BandSpec:
    name: str
    variant: str
    alphabet: str
    cell_dots: int
    method: str
    neutral: str
    h_dots: int | None                   # None = fill to LAST_END_DOTS (a multiple of 6)
    tiles: int = 1
    x_dots: int = BAND_X_DOTS
    w_dots: int = BAND_W_DOTS
    gaps: GapSpec | None = None


BANDS: tuple[BandSpec, ...] = (
    BandSpec("R1", "control", "cmy8-engine", 3, "smooth", "process", 708),
    BandSpec("R2", "tiles", "cmy8-engine", 3, "smooth", "process", 708, tiles=TILES),
    BandSpec("R3", "gap3_10mm", "cmy8-engine", 3, "smooth", "process", 708, gaps=GAP3_10MM),
    BandSpec("R4", "gap24_20mm", "cmy8-engine", 3, "smooth", "process", 708, gaps=GAP24_20MM),
    BandSpec("R5", "offset50mm", "cmy8-engine", 3, "smooth", "process", 708, x_dots=OFFSET_X_DOTS,
             w_dots=OFFSET_W_DOTS),
    BandSpec("R6", "gap3_10mm", "cmyk5", 3, "smooth", "toner", 708, gaps=GAP3_10MM),
    BandSpec("R7", "tiles", "cmyk5", 3, "smooth", "toner", 708, tiles=TILES),
    BandSpec("R8", "cmy4_solidC", "cmy4-solidC", 3, "smooth", "process", 708),
    BandSpec("R9", "cmy4_solidC_c2", "cmy4-solidC", 2, "detail", "process", None))


# ------------------------------------------------------------------------------------------------ plan

def band_rows() -> list[tuple[int, BandSpec, int, int]]:
    """(band index, spec, y_dots, h_dots), top to bottom = draw order, 24 white dots between bands."""
    out, y = [], FIRST_Y_DOTS
    for k, b in enumerate(BANDS):
        h = b.h_dots if b.h_dots is not None else (LAST_END_DOTS - y) // 6 * 6
        out.append((k, b, y, h))
        y += h + GAP_DOTS
    return out


def ink_table(alphabet: tuple[str, ...]) -> np.ndarray:
    """(states, 4) uint8: which of C/M/Y/K each state lays."""
    return np.array([[int(p in INK[s]) for p in s14.PLANES_ORDER] for s in alphabet], np.uint8)


def gap_columns(g: GapSpec | None, cols: int) -> list[tuple[int, int]]:
    """(first cell column, cell columns) of every whole gap inside a band of `cols` cell columns."""
    if g is None:
        return []
    return [(c, g.cell_cols) for c in range(g.first_cell, cols - g.cell_cols + 1, g.period_cells)]


def plan() -> tuple[list[dict], list[dict], list[dict], dict[str, np.ndarray]]:
    """Fiducials, bands, images (draw order) and the npz arrays."""
    fids, images = s14.fiducial_plan()
    bands, arrays = [], {}
    for k, b, y, h in band_rows():
        alpha = ALPHABETS[b.alphabet]
        cd = b.cell_dots
        rows, cols = h // cd, b.w_dots // cd
        if rows * cd != h or cols * cd != b.w_dots:
            raise SystemExit(f"{b.name}: {h} x {b.w_dots} dots is not whole c{cd} cells")
        seed = SEED_BASE + k
        states = np.random.default_rng(seed).choice(len(alpha), size=(rows, cols)).astype(np.uint8)
        gaps = gap_columns(b.gaps, cols)
        for c0, n in gaps:
            states[:, c0:c0 + n] = alpha.index("W")
        arrays[f"states_{b.name}"] = states
        arrays[f"planes_{b.name}"] = np.ascontiguousarray(
            np.moveaxis(s14.expand(ink_table(alpha)[states], cd), 2, 0))
        raster = s14.expand(states, cd)
        pal = np.array([PALETTE[s] for s in alpha], np.uint8)
        if b.tiles == 1:
            imgs = [s14.image_rec(b.name, b.name, SECTION, b.method, b.neutral, (b.x_dots, y, b.w_dots, h),
                                  pal, raster, "band")]
        else:
            if b.tiles * TILE_W_DOTS != b.w_dots or TILE_W_DOTS % cd:
                raise SystemExit(f"{b.name}: {b.tiles} tiles x {TILE_W_DOTS} dots do not cut the band")
            imgs = [s14.image_rec(f"{b.name}-t{t:02d}", b.name, SECTION, b.method, b.neutral,
                                  (b.x_dots + t * TILE_W_DOTS, y, TILE_W_DOTS, h), pal,
                                  np.ascontiguousarray(raster[:, t * TILE_W_DOTS:(t + 1) * TILE_W_DOTS]),
                                  "band", tile=t)
                    for t in range(b.tiles)]
        rec = {"band": k, "name": b.name, "section": SECTION, "matching": s14.MATCHING[SECTION],
               "method": b.method, "neutral": b.neutral, "x_dots": b.x_dots, "y_dots": y, "w_dots": b.w_dots,
               "h_dots": h, "x_mm": mm(b.x_dots), "y_mm": mm(y), "w_mm": mm(b.w_dots), "h_mm": mm(h),
               "alphabet": b.alphabet, "states": list(alpha), "palette": {s: list(PALETTE[s]) for s in alpha},
               "planes": {s: INK[s] for s in alpha}, "cell_dots": cd, "cells_hw": [rows, cols], "seed": seed,
               "variant": b.variant,
               "gaps": [{"cell_col_start": c0, "cell_cols": n, "x_dots": b.x_dots + c0 * cd, "w_dots": n * cd,
                         "x_mm": mm(b.x_dots + c0 * cd)} for c0, n in gaps],
               "images": [{"image": i["name"], "x_dots": i["xywh"][0], "y_dots": i["xywh"][1],
                           "w_dots": i["xywh"][2], "h_dots": i["xywh"][3], "neutral": i["neutral"],
                           "tile": i["tile"]} for i in imgs]}
        bands.append(rec)
        images += imgs
    return fids, bands, images, arrays


def notes() -> list[str]:
    return [
        "WHY: S14's full-width bands switch the engine screen per column region: cmy4 never screened; cmy8 "
        "screened but x 12-20 and 108-117 mm; cmyk5 but x 12-35 and 108-142 mm; state error follows the "
        "screen (cmy8 6-16 % unscreened vs 34-36 % screened; cmyk5 1-7 % vs 21-26 %). S15 asks what resets "
        "the switch: a white gap (R3, R4, R6), an object boundary (R2, R7), an image left edge at 50 mm "
        "(R5).",
        "ROUTE = S14's: S1 PJL wrapper without BITSPERPIXEL/RET, F's setpagedevice, S12's bare-name prologue "
        "byte for byte, 8-bit Indexed DeviceRGB images in gsave, ASCII85, HP calls behind `where` guards in "
        "S14's section-A order; no ColorSmartColorMatching call anywhere (S14: no effect).",
        "GAPS: whole c3 cell columns forced to W after the draw (states_<band> carries them as W, the render "
        "is white there): R3/R6 one column (3 dots) at cell 39 + 79k (~10.03 mm period, first at 4.95 mm "
        "from the band edge); R4 eight columns (24 dots) at cell 79 + 158k (~20.07 mm period).",
        "R2/R7: ONE raster per band cut into 24 abutting images 183 dots (61 cells) wide; R1 and R7's "
        "neighbours R6 are the one-image references of the same alphabet (other seeds).",
        "R5: one cmy8 image from x 1182 dots (50.04 mm) to 4674 (197.86 mm); 283..1182 of its rows is white.",
        "R8/R9: cmy4 with the solid cyan C-solid (0, 208, 255) and M-solid (240, 0, 192), R8 c3 Smooth, R9 "
        "c2 Detail -- the production candidate.",
        "SEEDS: default_rng(52000 + band index), band index = table position (R1 = 0 .. R9 = 8); "
        ".choice(len(alphabet), size=(rows, cols)) row-major, then the gap columns forced to W.",
        "PLANES: 1 where that toner's solid colour is on the dot; CMY (0,0,0) under ProcBlack sets C, M and "
        "Y; K (0,0,0) under TonerBlack sets K only; C-solid sets C.",
        "No bars or strips on this sheet (the bar list is empty).",
        "gs knows none of the HP operators; its render shows the page, not what the engine does with them.",
    ]


def build() -> tuple[bytes, dict, bytes, list[dict], dict[str, np.ndarray], list[dict]]:
    """The job, the manifest (no verification, no generator line), the npz bytes, images, arrays, records."""
    fids, bands, images, arrays = plan()
    job, records = s14.emit_job(images, WRAPPER_HEAD, HEADER)
    nb = s14.npz_bytes(arrays)
    manifest = {
        "tag": TAG, "dpi": DPI, "page_dots": {"w": PAGE_W_DOTS, "h": PAGE_H_DOTS}, "bytes": len(job),
        "sha256": sha(job), "bands_npz": {"file": f"{TAG}-bands.npz", "sha256": sha(nb), "bytes": len(nb),
                                          "keys": sorted(arrays)},
        "planes_order": list(s14.PLANES_ORDER), "fiducials": fids, "bands": bands, "bars": [],
        "windows": s14.windows(bands), "palette": {k: list(v) for k, v in PALETTE.items()},
        "alphabets": {k: list(v) for k, v in ALPHABETS.items()}, "variants": list(VARIANTS),
        "ps_structure": {"wrapper_head": WRAPPER_HEAD.decode("latin1"), "header": HEADER.decode(),
                         "setpagedevice": s12.SETPAGEDEVICE.decode(), "prologue": s12.prologue().decode(),
                         "tail": TAIL.decode("latin1"), "data_filter": "ASCII85Decode",
                         "a85_columns": s12.A85_COLUMNS, "pt_per_dot": s12.PT_PER_DOT, "images": records},
        "notes": notes(),
    }
    return job, manifest, nb, images, arrays, records


# ------------------------------------------------------------------------------------------------ verify

def render_checks(img: np.ndarray, messages: str, rc: int, man: dict, arrays: dict[str, np.ndarray],
                  images: list[dict]) -> dict:
    page = s14.composed(man, arrays)
    covered = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), bool)
    fid_black = True
    for f in man["fiducials"]:
        x, y, w, h = f["xywh_dots"]
        fid_black &= bool((img[y:y + h, x:x + w] == 0).all())
        covered[y:y + h, x:x + w] = True
    gaps_white, n_gaps = True, 0
    for b in man["bands"]:
        covered[b["y_dots"]:b["y_dots"] + b["h_dots"], b["x_dots"]:b["x_dots"] + b["w_dots"]] = True
        for g in b["gaps"]:
            gaps_white &= bool((img[b["y_dots"]:b["y_dots"] + b["h_dots"],
                                    g["x_dots"]:g["x_dots"] + g["w_dots"]] == 255).all())
            n_gaps += 1
    r5 = next(b for b in man["bands"] if b["variant"] == "offset50mm")
    r5_span = img[r5["y_dots"]:r5["y_dots"] + r5["h_dots"], BAND_X_DOTS:r5["x_dots"]]
    res = {"gs_returncode": rc, "gs_messages": messages, "page_hw": list(img.shape[:2]),
           "render_sha256": sha(img.tobytes()),
           "differing_dots_vs_composed_from_manifest_npz": int((img != page).any(2).sum()),
           "differing_dots_vs_painted_images": int((img != s12.painted(images)).any(2).sum()),
           "fiducials_solid_black": fid_black,
           "non_white_outside_objects": int(((img != 255).any(2) & ~covered).sum()),
           "white_dots_outside_objects": int((~covered).sum()),
           "gap_rectangles": n_gaps, "gap_rectangles_all_white": gaps_white,
           "R5_left_span_dots_xy": [BAND_X_DOTS, r5["x_dots"], r5["y_dots"], r5["y_dots"] + r5["h_dots"]],
           "R5_left_span_all_white": bool((r5_span == 255).all()),
           "inked_dots": int((img != 255).any(2).sum()),
           "page_fraction_in_noise_bands": round(float(sum(b["w_dots"] * b["h_dots"] for b in man["bands"])
                                                       / (PAGE_W_DOTS * PAGE_H_DOTS)), 4)}
    res["pass"] = (rc == 0 and not messages and res["differing_dots_vs_composed_from_manifest_npz"] == 0
                   and res["differing_dots_vs_painted_images"] == 0 and fid_black
                   and res["non_white_outside_objects"] == 0 and gaps_white and res["R5_left_span_all_white"])
    return res


def hp_lines(ops: list[str]) -> list[str]:
    return [ln for ln in ops if " where " in ln]


def byte_audit(job: bytes, records: list[dict], s14_job: bytes, s14_man: dict) -> dict:
    i14, i15 = s14_job.index(b"%!PS"), job.index(b"%!PS")
    e14, e15 = s14_job.index(b"%%EndComments\n"), job.index(b"%%EndComments\n")
    k14, k15 = s14_job.index(b"%%Page: 1 1\n"), job.index(b"%%Page: 1 1\n")
    h14 = [ln for ln in s14_job[i14:e14].split(b"\n") if not ln.startswith((b"%%Title", b"%%Creator"))]
    h15 = [ln for ln in job[i15:e15].split(b"\n") if not ln.startswith((b"%%Title", b"%%Creator"))]
    lines = s14.skeleton(job, records).split(b"\n")
    # S14's HP lines per (neutral, method) with its section-B matching line removed: section A carried
    # (process|toner, Smooth), only section B carried Detail (B3), so R9's sequence is B3's minus that line
    s14_seq: dict[tuple[str, str], set[tuple[str, ...]]] = {}
    for r in s14_man["ps_structure"]["images"]:
        seq = tuple(ln for ln in hp_lines(r["operators"]) if "ColorSmartColorMatching" not in ln)
        s14_seq.setdefault((r["neutral"], r["method"]), set()).add(seq)
    hp_match = [s14_seq.get((r["neutral"], r["method"])) == {tuple(hp_lines(r["operators"]))}
                for r in records]
    end = b"~>\ngrestore\n"
    res = {"wrapper_head_equals_S14_name_aside": job[:i15] == s14_job[:i14].replace(
               f'JOB NAME="{s14.JOB_NAME}"'.encode(), f'JOB NAME="{JOB_NAME}"'.encode()),
           "header_shape_equals_S14_title_creator_aside": h14 == h15,
           "setpagedevice_equals_S14": (job[e15 + 14:].split(b"\n", 1)[0] + b"\n" == s12.SETPAGEDEVICE
                                        and s14_job.count(s12.SETPAGEDEVICE) == 1
                                        and job.count(s12.SETPAGEDEVICE) == 1),
           "prologue_equals_S14": s14_job[e14 + 14:k14] == job[e15 + 14:k15] == s12.SETPAGEDEVICE
           + s12.prologue(),
           "tail_equals_S14": job.endswith(TAIL) and s14_job[s14_job.rindex(end) + len(end):]
           == job[job.rindex(end) + len(end):],
           "hp_call_lines_equal_S14_per_neutral_and_method_matching_line_aside": all(hp_match),
           "hp_call_sequences_by_neutral_method": {f"{n}/{m}": [list(q) for q in sorted(v)]
                                                   for (n, m), v in sorted(s14_seq.items())},
           "ColorSmartColorMatching_occurrences": job.count(b"ColorSmartColorMatching"),
           "showpage_lines": lines.count(b"showpage"), "image_operators": lines.count(b">> image"),
           "gsave": lines.count(b"gsave"), "grestore": lines.count(b"grestore"),
           "non_ascii_bytes_after_wrapper": sum(1 for c in job[len(WRAPPER_HEAD):-len(s12.WRAPPER_TAIL)]
                                                if c > 126 or (c < 32 and c != 10)),
           "data_lines_starting_with_percent": sum(
               ln.startswith(b"%") for r in records
               for ln in job[r["data_offset"]:r["data_offset"] + r["data_bytes_ascii85"]].split(b"\n")),
           "skeleton_bytes": len(b"\n".join(lines))}
    n = len(records)
    res["pass"] = (all(res[k] for k in list(res)[:6]) and res["ColorSmartColorMatching_occurrences"] == 0
                   and all(len(v) == 1 for v in s14_seq.values())
                   and res["showpage_lines"] == 1
                   and res["image_operators"] == res["gsave"] == res["grestore"] == n
                   and res["non_ascii_bytes_after_wrapper"] == 0
                   and res["data_lines_starting_with_percent"] == 0)
    return res


def window_checks(img: np.ndarray, man: dict, npz_path: Path) -> dict:
    """Every window: states and planes sliced from the npz (as the readout does) against the render's dots
    decoded through the band palette, planes through the manifest's per-state ink; then every gap column:
    W in states_<band>, white in the render."""
    bands = {b["name"]: b for b in man["bands"]}
    ok, bad, per_band, gap_windows = 0, [], Counter(), 0
    with np.load(npz_path) as npz:
        arrays = {k: npz[k] for k in npz.files}
    for w in man["windows"]:
        b = bands[w["band"]]
        cd, wc = w["cell_dots"], w["cells"]
        cy, cx = w["cell_yx"]
        st = arrays[f"states_{b['name']}"][cy:cy + wc, cx:cx + wc]
        dy, dx = w["y_dots"] - b["y_dots"], w["x_dots"] - b["x_dots"]
        pl = arrays[f"planes_{b['name']}"][:, dy:dy + w["h_dots"], dx:dx + w["w_dots"]]
        win = img[w["y_dots"]:w["y_dots"] + w["h_dots"], w["x_dots"]:w["x_dots"] + w["w_dots"]]
        pal = np.array([b["palette"][s] for s in b["states"]], np.uint8)
        ink = np.array([[int(p in b["planes"][s]) for p in man["planes_order"]] for s in b["states"]],
                       np.uint8)
        match = (win[:, :, None, :] == pal[None, None]).all(3)
        decoded = match.argmax(2)
        good = (bool((match.sum(2) == 1).all()) and np.array_equal(decoded, s14.expand(st, cd))
                and np.array_equal(pl, np.moveaxis(ink[decoded], 2, 0)) and st.shape == (wc, wc))
        ok += good
        per_band[w["band"]] += 1
        gap_windows += any(cx < g["cell_col_start"] + g["cell_cols"] and g["cell_col_start"] < cx + wc
                           for g in b["gaps"])
        if not good:
            bad.append(w["id"])
    gap_cols, gap_ok = 0, True
    for b in man["bands"]:
        st = arrays[f"states_{b['name']}"]
        w_idx = b["states"].index("W")
        for g in b["gaps"]:
            c0, n = g["cell_col_start"], g["cell_cols"]
            gap_ok &= bool((st[:, c0:c0 + n] == w_idx).all())
            gap_ok &= bool((img[b["y_dots"]:b["y_dots"] + b["h_dots"],
                                g["x_dots"]:g["x_dots"] + g["w_dots"]] == 255).all())
            gap_ok &= g["x_dots"] == b["x_dots"] + c0 * b["cell_dots"] and g["w_dots"] == n * b["cell_dots"]
            gap_cols += n
    return {"windows": len(man["windows"]), "equal": ok, "per_band": dict(per_band), "first_bad": bad[:5],
            "windows_touching_a_gap": gap_windows, "gap_cell_columns": gap_cols,
            "gap_columns_W_in_states_and_white_in_render": gap_ok,
            "pass": ok == len(man["windows"]) and gap_ok}


def separation(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    """Chebyshev gap in dots between two rectangles (x, y, w, h); <= 0 = touching or overlapping."""
    dx = max(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]))
    dy = max(b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]))
    return max(dx, dy)


def geometry_checks(man: dict, images: list[dict]) -> dict:
    def inside(x: int, y: int, w: int, h: int) -> bool:
        return x >= 0 and y >= 0 and x + w <= PAGE_W_DOTS and y + h <= PAGE_H_DOTS

    fr = [tuple(f["xywh_dots"]) for f in man["fiducials"]]
    br = [(b["x_dots"], b["y_dots"], b["w_dots"], b["h_dots"]) for b in man["bands"]]
    count = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), np.uint8)
    for x, y, w, h in fr + br:
        count[y:y + h, x:x + w] += 1
    img_count = np.zeros_like(count)
    for i in images:
        x, y, w, h = i["xywh"]
        img_count[y:y + h, x:x + w] += 1
    bands = {b["name"]: b for b in man["bands"]}
    win_ok = all(bands[w["band"]]["x_dots"] <= w["x_dots"] and w["x_dots"] + w["w_dots"]
                 <= bands[w["band"]]["x_dots"] + bands[w["band"]]["w_dots"]
                 and bands[w["band"]]["y_dots"] <= w["y_dots"] and w["y_dots"] + w["h_dots"]
                 <= bands[w["band"]]["y_dots"] + bands[w["band"]]["h_dots"] for w in man["windows"])
    page = sorted(man["bands"], key=lambda b: b["y_dots"])
    gaps = [page[k + 1]["y_dots"] - page[k]["y_dots"] - page[k]["h_dots"] for k in range(len(page) - 1)]
    tiles_ok = {}
    for b in man["bands"]:
        if len(b["images"]) > 1:
            cov = sorted((i["x_dots"], i["w_dots"]) for i in b["images"])
            tiles_ok[b["name"]] = (len(cov) == TILES and cov[0][0] == b["x_dots"]
                                   and all(a[0] + a[1] == c[0] for a, c in zip(cov, cov[1:]))
                                   and cov[-1][0] + cov[-1][1] == b["x_dots"] + b["w_dots"])
    period = {b["name"]: sorted({g2["x_dots"] - g1["x_dots"] for g1, g2 in zip(b["gaps"], b["gaps"][1:])})
              for b in man["bands"] if b["gaps"]}
    res = {"all_inside_page": all(inside(*r) for r in fr + br) and all(inside(*i["xywh"]) for i in images),
           "fiducials_bands_overlap_dots": int((count > 1).sum()),
           "image_overlap_dots": int((img_count > 1).sum()),
           "windows_inside_their_band": win_ok, "band_gaps_dots": gaps,
           "fiducial_clearance_dots": min(separation(f, b) for f in fr for b in br),
           "tiles_cover_band_abutting": tiles_ok,
           "band_x_dots": {b["name"]: [b["x_dots"], b["x_dots"] + b["w_dots"]] for b in man["bands"]},
           "band_h_dots": {b["name"]: b["h_dots"] for b in man["bands"]},
           "gaps_per_band": {b["name"]: len(b["gaps"]) for b in man["bands"] if b["gaps"]},
           "gap_period_dots": period,
           "gap_first_x_mm_from_band_edge": {b["name"]: round(mm(b["gaps"][0]["x_dots"] - b["x_dots"]), 3)
                                             for b in man["bands"] if b["gaps"]},
           "last_band_end_dots": page[-1]["y_dots"] + page[-1]["h_dots"],
           "heights_multiple_of_6": all(b["h_dots"] % 6 == 0 for b in man["bands"]),
           "windows": len(man["windows"]),
           "windows_per_band": dict(Counter(w["band"] for w in man["windows"]))}
    res["pass"] = (res["all_inside_page"] and res["fiducials_bands_overlap_dots"] == 0
                   and res["image_overlap_dots"] == 0 and win_ok and all(g == GAP_DOTS for g in gaps)
                   and all(tiles_ok.values()) and len(tiles_ok) == 2
                   and res["last_band_end_dots"] <= LAST_END_DOTS and res["heights_multiple_of_6"]
                   and res["fiducial_clearance_dots"] > 0
                   and all(len(v) == 1 for v in period.values()))
    return res


def palettes(job: bytes) -> set[bytes]:
    return set(re.findall(rb"\[/Indexed /DeviceRGB \d+ <([0-9a-f]+)>\] setcolorspace", job))


def novelty(job: bytes, records: list[dict], man: dict, s14_job: bytes, s14_man: dict,
            s12_job: bytes) -> dict:
    c15, c14, c12 = s14.constructs(job), s14.constructs(s14_job), s14.constructs(s12_job)
    rgb_by = {tuple(v): k for k, v in PALETTE.items()}
    new_pal = sorted(palettes(job) - palettes(s14_job) - palettes(s12_job))
    noise_rgb_14 = {tuple(v) for b in s14_man["bands"] if b["alphabet"] for v in b["palette"].values()}
    noise_rgb_15 = {tuple(v) for b in man["bands"] for v in b["palette"].values()}
    return {
        "S15": c15, "S14": c14, "S12": c12,
        "hp_calls_new_vs_S14_and_S12": sorted(set(c15["hp_calls"]) - set(c14["hp_calls"])
                                              - set(c12["hp_calls"])),
        "colour_spaces_new_vs_S14_and_S12": sorted(set(c15["colour_spaces"]) - set(c14["colour_spaces"])
                                                   - set(c12["colour_spaces"])),
        "filters_new": sorted(set(c15["filters"]) - set(c14["filters"]) - set(c12["filters"])),
        "other_constructs_new": sorted(set(c15["other_constructs"]) - set(c14["other_constructs"])
                                       - set(c12["other_constructs"])),
        "image_sizes_new_vs_S14_and_S12": sorted(set(c15["image_sizes"]) - set(c14["image_sizes"])
                                                 - set(c12["image_sizes"])),
        "rgb_values_new_vs_S14_and_S12_lookups": [list(v) for v in sorted(
            s14.lookups(job) - s14.lookups(s14_job) - s14.lookups(s12_job))],
        "palettes_new_vs_S14_and_S12": [[rgb_by.get(tuple(lut[k:k + 3]), "?") for k in range(0, len(lut), 3)]
                                        for lut in (bytes.fromhex(p.decode()) for p in new_pal)],
        "noise_band_rgb_new_vs_S14_noise_bands": [[*v, rgb_by.get(v, "?")]
                                                  for v in sorted(noise_rgb_15 - noise_rgb_14)],
        "band_x_starts_dots": {"S15": sorted({b["x_dots"] for b in man["bands"]}),
                               "S14": sorted({b["x_dots"] for b in s14_man["bands"]})},
        "abutting_image_pairs": {"S15": s14.abutting_pairs([tuple(r["xywh_dots"]) for r in records]),
                                 "S14": s14.abutting_pairs([tuple(r["xywh_dots"])
                                                            for r in s14_man["ps_structure"]["images"]])},
        "summary": [
            "No new HP call, operand, guard form, colour-space form, filter or other construct: every image "
            "carries S14's section-A call sequence (no ColorSmartColorMatching anywhere).",
            "New image sizes: 183x708 (24 tiles per band; S14's tiles were 183x942), 3492x708 (R5) and "
            "4392x588 (the c2 band); 4392x708 was S14's A3 / B3.",
            "A noise band not starting at x 283: R5 at x 1182 (50.04 mm).",
            "C-solid (0, 208, 255) as a noise-alphabet value: S14 carried it only as a solid strip bar, so "
            "as a lookup value it is not new, the 4-entry palette W/C-solid/M-solid/Y is.",
            "White whole-cell columns inside a noise image (the gaps): a content pattern, not a construct "
            "(S14's strip image already held white gaps between bars).",
            "Object split on cmy8-engine and cmyk5 (S14 split only cmy4-solid).",
        ]}


class _MemScan:
    """measure.e041_probe_readout.Scan's interface over an in-memory RGB array (no TIFF)."""

    def __init__(self, arr: np.ndarray) -> None:
        from measure.e041_probe_readout import Scan
        self._scan = Scan.__new__(Scan)
        self._scan.img = arr
        self._scan.scale255 = 1.0
        self._scan.h, self._scan.w = arr.shape[:2]

    def __call__(self, path: Path) -> object:
        return self._scan


def readout_dry_run(man_path: Path) -> dict:
    """e041_scale_readout.main and e041_band_screen.main, both unchanged, on a clean synthetic scan: the page
    painted from the manifest + npz by e041_scale_synth.page_raster (its toner colours, reflectances
    multiplied), at 4x4 px per dot (2400 dpi, identity pose, no blur, no noise -- the pose step is what costs
    the synth its 34 GB), their Scan class pointed at the array; outputs into a temporary directory."""
    import measure.e041_band_screen as bs
    import measure.e041_scale_readout as ro
    from measure.e041_mixture_synth import TONER_RGB
    from measure.e041_scale_synth import page_raster
    man = json.loads(man_path.read_text())
    with np.load(man_path.with_name(man["bands_npz"]["file"])) as npz:
        page = page_raster(man, npz, dict(TONER_RGB))
    mem = _MemScan(np.repeat(np.repeat(page, 4, axis=0), 4, axis=1))
    del page
    out: dict = {"image_px_hw": [4 * PAGE_H_DOTS, 4 * PAGE_W_DOTS], "toner_rgb": dict(TONER_RGB)}
    saved = ro.Scan, bs.Scan, sys.argv
    try:
        ro.Scan = mem  # type: ignore[assignment,misc]
        bs.Scan = mem  # type: ignore[assignment,misc]
        with tempfile.TemporaryDirectory() as td:
            sys.argv = ["e041_scale_readout", "--scan", "in-memory", "--manifest", str(man_path),
                        "--out", td]
            buf, t0 = io.StringIO(), time.monotonic()
            with contextlib.redirect_stdout(buf):
                ro.main()
            summ = json.loads((Path(td) / f"{TAG}-summary.json").read_text())
            log = buf.getvalue().splitlines()
            out["scale_readout"] = {
                "seconds": round(time.monotonic() - t0, 1), "windows_read": summ["n_windows_read"],
                "windows_in_manifest": len(man["windows"]), "reg_nominal": summ["n_reg_nominal"],
                "reg_edge": summ["n_reg_edge"], "fit_residual_mm": summ["fit"].get("residual_mm"),
                "bars": len(summ["bars"]),
                "witness": summ["comparisons"][-1].get("witness", {}).get("reading"),
                "bands": {s["name"]: {"windows": s["windows"], "objects": s["objects"],
                                      "state_err_loo_mean": s["state_err_loo"]["mean"],
                                      "state_err_band_mean": s["state_err_band"]["mean"],
                                      "profile_col_mm_first_last": [round(s["profile_col"][0]["mm"], 2),
                                                                    round(s["profile_col"][-1]["mm"], 2)]}
                          for s in summ["bands"]},
                "outputs": sorted(p.name for p in Path(td).iterdir()),
                "log_head": log[:3]}
            sys.argv = ["e041_band_screen", "--scan", "in-memory", "--manifest", str(man_path), "--out", td]
            buf, t0 = io.StringIO(), time.monotonic()
            with contextlib.redirect_stdout(buf):
                bs.main()
            with open(Path(td) / f"{TAG}-columns.csv", newline="") as fh:
                cols = list(csv.DictReader(fh))
            from PIL import Image
            heat = Image.open(Path(td) / f"{TAG}-heat-188.png").size
            per = {nm: [float(r["x_mm"]) for r in cols if r["band"] == nm] for nm in [b["name"] for b in
                                                                                       man["bands"]]}
            out["band_screen"] = {
                "seconds": round(time.monotonic() - t0, 1), "columns": len(cols),
                "per_band": {nm: {"columns": len(v), "x_mm_first": v[0] if v else None,
                                  "x_mm_last": v[-1] if v else None} for nm, v in per.items()},
                "heat_png_px": list(heat), "log_tail": buf.getvalue().splitlines()[-12:]}
    finally:
        ro.Scan, bs.Scan, sys.argv = saved
    sr, bsr = out["scale_readout"], out["band_screen"]
    r5 = bsr["per_band"]["R5"]
    out["changes_needed"] = [
        "e041_scale_readout.py: none (an empty bar list reads as no bars and a 'missing' matching witness; "
        "a band's own x_dots places its windows; S14's COMPARISONS name no S15 band, so none print).",
        "e041_band_screen.py: its heat maps cut every band to the SHORTEST band's column count from the "
        "left, so R5 (50 mm start) would have been drawn at the page edge and the right ~40 mm of every band "
        "dropped; fixed: each band's row is left-padded by (its first column - the leftmost first column) // "
        "STEP columns (score 1 = dark) before the cut. S14's bands start within 0.02 mm of each other "
        "(its columns CSV), so S14 pads nothing and its maps are unchanged."]
    out["pass"] = (sr["windows_read"] == sr["windows_in_manifest"] and sr["reg_nominal"] == 0
                   and sr["bars"] == 0 and len(sr["bands"]) == len(man["bands"])
                   and all(v["state_err_loo_mean"] == 0 for v in sr["bands"].values())
                   and all(v["columns"] > 0 for v in bsr["per_band"].values())
                   and r5["x_mm_first"] is not None and r5["x_mm_first"] > 50.0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path, help="job path (.ps); manifest + npz beside it")
    ap.add_argument("--s14", type=Path, default=None, help="S14 job (default: S14-ps-scale.ps beside --out)")
    ap.add_argument("--s12", type=Path, default=None,
                    help="S12 job (default: S12-ps-mixture.ps beside --out)")
    ap.add_argument("--s11", type=Path, default=None,
                    help="S11 manifest for the S12 rebuild (default: S11-pclxl-mixture.manifest.json beside "
                    "--out)")
    ap.add_argument("--verify", action="store_true", help="checks (1)-(10)")
    args = ap.parse_args()
    job, manifest, nb, images, arrays, records = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(job)
    man_path = args.out.with_name(args.out.stem + ".manifest.json")
    npz_path = args.out.with_name(manifest["bands_npz"]["file"])
    npz_path.write_bytes(nb)
    gen = {"generator": " ".join(["PYTHONPATH=src:.", sys.executable, *sys.argv])}
    man_path.write_text(json.dumps(manifest | gen | {"verification": "not run"}, indent=1) + "\n")
    if args.verify:
        s14_path = args.s14 or args.out.with_name("S14-ps-scale.ps")
        s12_path = args.s12 or args.out.with_name("S12-ps-mixture.ps")
        s14_job, s12_job = s14_path.read_bytes(), s12_path.read_bytes()
        s14_man = json.loads(s14_path.with_name(s14_path.stem + ".manifest.json").read_text())
        v: dict = {}
        img, messages, rc = s14.render(args.out)
        v["1_render"] = render_checks(img, messages, rc, manifest, arrays, images)
        v["1_ascii85_roundtrip"] = s14.data_roundtrip(job, records, images)
        v["2_guards"] = s14.guard_checks(job, images)
        v["3_byte_audit_vs_S14"] = byte_audit(job, records, s14_job, s14_man)
        v["4_windows"] = window_checks(img, manifest, npz_path)
        v["5_geometry"] = geometry_checks(manifest, images)
        again = build()
        v["6_two_builds_identical"] = {"job": again[0] == job, "manifest": again[1] == manifest,
                                       "npz": again[2] == nb}
        s14_rebuilt = sha(s14.build()[0])
        v["7_rebuilt"] = {
            "S14": {"rebuilt_sha256": s14_rebuilt, "on_disk_sha256": sha(s14_job), "expected": S14_SHA256,
                    "pass": s14_rebuilt == sha(s14_job) == S14_SHA256},
            "S12": s14.s12_rebuild(args.s11 or args.out.with_name("S11-pclxl-mixture.manifest.json"),
                                   s12_path)}
        v["8_novelty"] = novelty(job, records, manifest, s14_job, s14_man, s12_job)
        v["9_sizes"] = s14.sizes(job, records, nb, len(json.dumps(manifest, indent=1)))
        v["10_readout_compatibility"] = readout_dry_run(man_path)
        v["pass"] = all([v["1_render"]["pass"], v["1_ascii85_roundtrip"]["pass"], v["2_guards"]["pass"],
                         v["3_byte_audit_vs_S14"]["pass"], v["4_windows"]["pass"], v["5_geometry"]["pass"],
                         all(v["6_two_builds_identical"].values()), v["7_rebuilt"]["S14"]["pass"],
                         v["7_rebuilt"]["S12"]["pass"], v["10_readout_compatibility"]["pass"]])
        man_path.write_text(json.dumps(manifest | gen | {"verification": v}, indent=1) + "\n")
        print(json.dumps({k: (x if k not in ("8_novelty",) else {kk: vv for kk, vv in x.items()
                                                               if kk not in ("S15", "S14", "S12")})
                          for k, x in v.items()}, indent=1))
    print(f"{args.out}: {len(job)} B sha {manifest['sha256']}")
    print(f"{man_path}\n{npz_path}: {len(nb)} B sha {manifest['bands_npz']['sha256']}")


if __name__ == "__main__":
    main()
