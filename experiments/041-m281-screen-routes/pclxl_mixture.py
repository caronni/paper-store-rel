"""e041 S11 — the HP M281 mixture probe: which neighbours cost a cell, which alphabets survive a field.

THE QUESTION.  The S10p2 RGB probe (pclxl_probe_banded.py, printed 2026-10-05 11:27) showed this engine lays
a SINGLE toner solid (cyan at (0,255,255), yellow at (255,255,0), magenta not at its corner but at
(240,0,192) / (240,0,208)) and never a two-toner overlap (every overlap is screened partial toner); every
state read 0-2 % cell error in isolation while the same corners read 21-26 % on the full data page.  S11 asks
about the NEIGHBOURHOOD and the ALPHABET: which cells beside a cell cost it; whether an overlap-free alphabet
({W,C,M,Y}, subsets, {C,M} without white) survives a mixed field at c3 and c2; what dot-level mixtures
(overlaps built from single-toner dots inside a cell) cost against the engine's own overlaps; and whether K
(toner black, SetNeutralAxis eTonerBlack) joins as a fifth solid state (cmyk5).

THE CONSTRUCTION is S10p2's, the one that printed (S10p, one image per patch, crashed the formatter): A4
portrait, 600 dpi, the 29 x 42 slot grid (5.5 x 6.5 mm pitch, x in [12, 98] U [118, 198] mm, y in [12, 285]
mm), the five raster fiducials as S10p2's three fiducial images, then BAND IMAGES: one eIndexedPixel e8Bit
image per band (768-byte palette, entry 0 white, the global colour indices of pclxl_mixture_arms.COLOURS,
unused entries white), each after S9's preamble (SetColorSpace eRGB + palette, SetColorTreatment
eNoTreatment, SetAdaptiveHalftoning eDisable, SetColorTrapping eDisable, SetNeutralAxis eProcessBlack -- or
eTonerBlack, value 0, in a toner-black band --, SetHalftoneMethod eHighLPI x3 in a highlpi band), SetCursor,
BeginImage, 64-row ReadImage blocks, EndImage.  No witness band, no matrix bands.  Four band KINDS = (method
default | eHighLPI) x (neutral axis eProcessBlack | eTonerBlack), drawn in kind order (default process,
default toner, highlpi process, highlpi toner), each kind once in every page third: per third two
process-black bands of six slot rows and two toner-black bands of one slot row (the toner-black kinds get
the rows they need, the rest goes to process black), 3 x 14 = 42 slot rows.

A patch = a 93 x 93-dot pattern square (c3: 31 x 31 cells of 3 x 3 dots; c2: 46 x 46 cells of 2 x 2 dots,
last row and column white) over a 93 x 24-dot bar in the colour of its arm's first non-white state, composed
dot by dot from cell states drawn iid (default_rng(41000 + id).choice over the alphabet, row-major).  Arms,
alphabets, layouts: pclxl_mixture_arms.py.  Each (arm, fraction) under both methods, three replicates, one per
page third (a seeded permutation), positions a seeded permutation of the band's slots.

Outputs: the job, <stem>.manifest.json (the readout's contract) and S11-pclxl-mixture-patterns.npz
(states_<id>, planes_<id>; the readout never regenerates patterns).

--verify: (a) read-back by pclxl_probe_banded's tokenizer and interpreter (operator sequence and band order,
every preamble byte-identical to S9's operators -- a toner-black band differing in its SetNeutralAxis value
byte alone --, palettes 768 B, strides and padding, the state in force at every image under both state
models); (b) every band image decoded through its palette against the page composed from the manifest + npz,
every dots_sha256 / states_sha256 recomputed (from the stream, the manifest + npz and the seeds), planes;
(c) gpcl6 ppmraw render against the composed page, rings, fiducials, ink outside objects; (d) zones,
overlaps, fiducial clearance; (e) two builds identical; (f) novelty by tokenizer diff against S10p2 and
S9/S9b; (g) counts; (h) S10p2 rebuilt by its own generator, sha unchanged.

    PYTHONPATH=src:. env/bin/python experiments/041-m281-screen-routes/pclxl_mixture.py \\
        --out experiments/041-m281-screen-routes/build/S11-pclxl-mixture.pclxl --verify
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import pclxl_bilevel as xl
import pclxl_probe_banded as banded
from pcl_planar import sha, stub_font
from pclxl_bilevel import E, stream_body
from pclxl_probe import DPI, PAGE_MM, SLOT_PITCH_MM, dots, mm, row_bytes, slot_grid
from pclxl_probe_banded import (BLOCK_ROWS, decode, emit_job, frame_checks, geometry_checks, interpret,
                                listing, public, structure, tokenize, tokens)
from pclxl_probe_sheets import PALETTE_ENTRIES, fiducial_images, fiducials, rect_of_slots
from pclxl_mixture_arms import (ARM_BY_KEY, ARMS, CELLS_BY_DOTS, COLOUR_INDEX, COLOURS, PATCH_H_DOTS,
                                PATTERN_DOTS, PLANES, SOLID_DOTS, STATE_SEED_BASE, Arm, arms_table,
                                bar_colour, cell_layouts, colour_table, compose, draw_states, fractions,
                                plane_table, planes_of, solid_palette)

TAG = "S11-pclxl-mixture"
NPZ_NAME = "S11-pclxl-mixture-patterns.npz"
REFS = {"S9": "S9-pclxl-bilevel.pclxl", "S9b": "S9b-pclxl-dither1x1.pclxl",
        "S10p2": "S10p2-pclxl-rgb-probe.pclxl"}  # default: beside --out
S10P2_SHA = "3bfe4add94c3a493f9504155df6855bae13aff8547111b6d2ba1c5d274b744e1"
LAYOUT_SEED = 4111
METHODS = ("default", "highlpi")
REPLICATES = 3
KINDS = (("default", "process"), ("default", "toner"), ("highlpi", "process"), ("highlpi", "toner"))
KIND_ROWS = {"process": 6, "toner": 1}  # slot rows per band of the kind's neutral axis
# Page order of the bands in each third, as indices into KINDS: every kind once per third, positions rotated.
THIRDS = ((0, 1, 2, 3), (2, 3, 0, 1), (1, 0, 3, 2))
BLOCK_OPS = {"treatment": "SetColorTreatment", "adaptive": "SetAdaptiveHalftoning",
             "trapping": "SetColorTrapping", "neutral": "SetNeutralAxis", "tonerblack": "SetNeutralAxis",
             "highlpi": "SetHalftoneMethod"}
NEUTRAL_STATE = {"process": "eProcessBlack", "toner": "eTonerBlack"}
NOVELTY_ENUMS = banded.ENUM_ATTRS | {"PaletteDepth"}


@dataclass(frozen=True)
class JobFrame:
    job_name: str
    comment: bytes


FRAME = JobFrame("E041-S11-PCLXL-MIXTURE", b"mixture probe sheet")


# ------------------------------------------------------------------------------------------------ plan

def band_layout() -> list[dict]:
    """The twelve bands in page order: kind, method, neutral, slot rows."""
    out, row = [], 0
    for third, order in enumerate(THIRDS):
        for k in order:
            method, neutral = KINDS[k]
            n = KIND_ROWS[neutral]
            out.append({"band": len(out), "third": third, "kind": k, "method": method, "neutral": neutral,
                        "slot_rows": list(range(row, row + n))})
            row += n
    if row != 42:
        raise SystemExit(f"bands cover {row} slot rows, 42 expected")
    return out


def patch_specs() -> list[dict]:
    """Every patch in id order: arm, fraction, method, replicate (ids sequential over this order)."""
    out = []
    for arm in ARMS:
        for fraction in fractions(arm):
            for method in METHODS:
                for rep in range(REPLICATES):
                    out.append({"id": len(out), "arm": arm.key, "fraction": fraction, "method": method,
                                "neutral": arm.neutral, "replicate": rep})
    return out


def band_image(band: dict, mem: list[dict], xs: list[int], ys: list[int]) -> dict:
    region = [(x, ys[r]) for r in band["slot_rows"] for x in xs]
    x, y, w, h = rect_of_slots(region)
    pal = np.full((PALETTE_ENTRIES, 3), 255, np.uint8)
    raster = np.zeros((h, w), np.uint8)
    for p in mem:
        px, py = p["_xy"]
        raster[py - y:py - y + PATCH_H_DOTS, px - x:px - x + PATTERN_DOTS] = p["_dots"]
    for k in np.unique(raster):
        pal[k] = COLOURS[list(COLOURS)[k]][0]
    neutral = "neutral" if band["neutral"] == "process" else "tonerblack"
    block = ("treatment", "adaptive", "trapping", neutral) + (("highlpi",) if band["method"] == "highlpi"
                                                              else ())
    return {"name": f"band{band['band']}", "kind": "band", "band": band["band"], "method": band["method"],
            "neutral": band["neutral"], "slot_rows": band["slot_rows"], "xywh": (x, y, w, h), "palette": pal,
            "raster": raster, "members": [p["id"] for p in mem], "block": block}


def plan() -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    """Patches, fiducials, images (emission order), bands.  One generator, default_rng(LAYOUT_SEED), draws in
    this order: per kind (KINDS order), per (arm, fraction) of that kind in id order, a permutation of the
    three thirds (replicate r goes to the kind's band in third perm[r]); then per band in page order a
    permutation of its slots (the band's patches, in id order, take slots perm[0], perm[1], ...)."""
    slots = slot_grid()
    xs, ys = sorted({x for x, _ in slots}), sorted({y for _, y in slots})
    if (len(xs), len(ys)) != (29, 42):
        raise SystemExit(f"slot grid {len(xs)} x {len(ys)}, 29 x 42 expected")
    bands = band_layout()
    specs = patch_specs()
    rng = np.random.default_rng(LAYOUT_SEED)
    band_of: dict[int, int] = {}
    for k, (method, neutral) in enumerate(KINDS):
        kind_bands = {b["third"]: b["band"] for b in bands if b["kind"] == k}
        groups: dict[tuple[str, str], list[dict]] = {}
        for p in specs:
            if (p["method"], p["neutral"]) == (method, neutral):
                groups.setdefault((p["arm"], p["fraction"]), []).append(p)
        for group in groups.values():
            perm = rng.permutation(3)
            for p in group:
                band_of[p["id"]] = kind_bands[int(perm[p["replicate"]])]
    patches: list[dict] = []
    for b in bands:
        mem = [p for p in specs if band_of[p["id"]] == b["band"]]
        band_slots = [(x, ys[r]) for r in b["slot_rows"] for x in xs]
        if len(mem) > len(band_slots):
            raise SystemExit(f"band {b['band']}: {len(mem)} patches for {len(band_slots)} slots")
        perm = rng.permutation(len(band_slots))
        b["patches"], b["slots"] = len(mem), len(band_slots)
        for k, p in enumerate(mem):
            arm = ARM_BY_KEY[p["arm"]]
            seed = STATE_SEED_BASE + p["id"]
            states = draw_states(arm, p["fraction"], seed)
            dots_idx = compose(arm, states)
            xy_ = band_slots[int(perm[k])]
            patches.append({
                "id": p["id"], "x_mm": mm(xy_[0]), "y_mm": mm(xy_[1]), "arm": arm.key, "family": arm.family,
                "alphabet": list(arm.states), "palette": solid_palette(arm),
                "dot_masks": {s: g for s, g in cell_layouts(arm).items() if s not in solid_palette(arm)},
                "bar_colour": bar_colour(arm), "cell_dots": arm.cell_dots,
                "cells": CELLS_BY_DOTS[arm.cell_dots],
                "fraction": p["fraction"], "method": p["method"], "neutral": p["neutral"], "band": b["band"],
                "seed": seed, "replicate": p["replicate"], "states_sha256": sha(states.tobytes()),
                "dots_sha256": sha(dots_idx.tobytes()), "_xy": xy_, "_states": states, "_dots": dots_idx,
                "_planes": planes_of(dots_idx, p["neutral"])})
    patches.sort(key=lambda p: p["id"])
    fids = fiducials()
    images = fiducial_images(fids)
    for k in range(len(KINDS)):
        for b in bands:
            if b["kind"] == k:
                images.append(band_image(b, [p for p in patches if p["band"] == b["band"]], xs, ys))
    return patches, fids, images, bands


def build() -> tuple[list[dict], list[dict], list[dict], list[dict], bytes]:
    patches, fids, images, bands = plan()
    return patches, fids, images, bands, emit_job(images, FRAME)


def npz_bytes(patches: list[dict]) -> bytes:
    """The patterns npz, byte-deterministic (fixed zip member dates): states_<id>, planes_<id>."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in patches:
            for key, arr in ((f"states_{p['id']}", p["_states"]), (f"planes_{p['id']}", p["_planes"])):
                member = io.BytesIO()
                np.lib.format.write_array(member, np.ascontiguousarray(arr), allow_pickle=False)
                info = zipfile.ZipInfo(key + ".npy", date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                z.writestr(info, member.getvalue())
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------ verify

def split_ubyte_ops(pre: bytes) -> list[tuple[str, bytes]]:
    """A run of operators whose attributes are all ubyte (C0 value F8 id), as (operator, bytes) chunks."""
    names = {v: k for k, v in xl.OP.items()}
    out, start, i = [], 0, 0
    while i < len(pre):
        if pre[i] == xl.UBYTE:
            if pre[i + 2] != xl.ATTR_UBYTE:
                raise ValueError(f"not a ubyte attribute at {i}")
            i += 4
        else:
            out.append((names[pre[i]], pre[start:i + 1]))
            i += 1
            start = i
    if start != len(pre):
        raise ValueError("trailing attributes")
    return out


def preambles(body: bytes) -> list[bytes]:
    """The bytes between each SetColorSpace (after its PaletteData attribute) and the next SetCursor's
    Point."""
    out, i = [], 0
    head, cursor = bytes((xl.ATTR_UBYTE, xl.ATTR["PaletteData"], xl.OP["SetColorSpace"])), bytes(
        (xl.ATTR_UBYTE, xl.ATTR["Point"], xl.OP["SetCursor"]))
    while (i := body.find(head, i)) >= 0:
        j = body.find(cursor, i)
        out.append(body[i + len(head):j - 5])  # Point = one xy tag + four bytes
        i = j
    return out


def preamble_checks(job: bytes, images: list[dict], s9: bytes) -> dict:
    """Every image's control run against S9's operators, byte for byte; the toner-black SetNeutralAxis equal
    to S9's but its value byte (1 -> 0)."""
    s9_pre = preambles(stream_body(s9))
    if len(s9_pre) != 1:
        raise SystemExit(f"S9: {len(s9_pre)} SetColorSpace runs, 1 expected")
    s9_ops = dict(split_ubyte_ops(s9_pre[0]))
    toner = bytearray(s9_ops["SetNeutralAxis"])
    toner[1] = E["eTonerBlack"]
    chunk = {n: s9_ops[op] for n, op in BLOCK_OPS.items() if n != "tonerblack"}
    chunk["tonerblack"] = bytes(toner)
    mine = preambles(stream_body(job))
    rows, ok = [], len(mine) == len(images)
    for img, got in zip(images, mine):
        want = b"".join(chunk[c] for c in img["block"])
        process_twin = b"".join(chunk["neutral" if c == "tonerblack" else c] for c in img["block"])
        diff = [k for k, (a, b) in enumerate(zip(got, process_twin)) if a != b]
        row = {"image": img["name"], "bytes": len(got), "equal_to_S9_operators": got == want,
               "differing_bytes_vs_S9_process_black": len(diff) if len(got) == len(process_twin) else None}
        if "tonerblack" in img["block"]:
            row["only_the_neutral_value_differs"] = len(diff) == 1 and got[diff[0]] == 0 and process_twin[
                diff[0]] == 1
        ok &= got == want and (row.get("only_the_neutral_value_differs", len(diff) == 0))
        rows.append(row)
    return {"S9_control_run": s9_pre[0].hex(" "), "images": rows, "pass": ok}


def expected_ops(images: list[dict]) -> list[str]:
    seq = ["BeginSession", "OpenDataSource", "BeginPage"]
    for img in images:
        seq += ["SetColorSpace", *(BLOCK_OPS[c] for c in img["block"]), "SetCursor", "BeginImage"]
        seq += ["ReadImage"] * -(-img["xywh"][3] // BLOCK_ROWS) + ["EndImage"]
    return seq + ["EndPage", "CloseDataSource", "EndSession"]


def want_state(img: dict) -> dict:
    return {"treatment": "eNoTreatment", "adaptive": "eDisable", "trapping": "eDisable",
            "neutral": NEUTRAL_STATE.get(img.get("neutral", "process")), "halftone": img["method"]}


def load_npz(path: Path) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def composed(manifest: dict, npz: dict[str, np.ndarray], hw: tuple[int, int]) -> tuple[np.ndarray, dict]:
    """The page (RGB) and each patch's dot indices, from the manifest (arms table, colour table, positions,
    fiducials) and the npz states alone."""
    page = np.full((*hw, 3), 255, np.uint8)
    colours = {c["name"]: c for c in manifest["colours"]}
    arms = {a["arm"]: a for a in manifest["arms"]}
    for f in manifest["fiducials"]:
        x, y = dots(f["x_mm"]), dots(f["y_mm"])
        page[y:y + dots(f["h_mm"]), x:x + dots(f["w_mm"])] = f["rgb"]
    per: dict[int, np.ndarray] = {}
    rgb = np.array([c["rgb"] for c in sorted(colours.values(), key=lambda c: c["index"])], np.uint8)
    for p in manifest["patches"]:
        a = arms[p["arm"]]
        d, n = a["cell_dots"], a["cells"]
        st = npz[f"states_{p['id']}"]
        idx = np.zeros((PATCH_H_DOTS, PATTERN_DOTS), np.uint8)
        for r in range(n):
            for c in range(n):
                grid = a["cell_layouts"][a["alphabet"][st[r, c]]]
                for i in range(d):
                    for j in range(d):
                        idx[r * d + i, c * d + j] = colours[grid[i][j]]["index"]
        idx[PATTERN_DOTS:] = colours[a["bar_colour"]]["index"]
        per[p["id"]] = idx
        x, y = dots(p["x_mm"]), dots(p["y_mm"])
        page[y:y + PATCH_H_DOTS, x:x + PATTERN_DOTS] = rgb[idx]
    return page, per


def states_from_dots(arm: Arm, dots_idx: np.ndarray) -> np.ndarray | None:
    """Invert the composition: each cell's dots matched against the arm's layouts (None if any cell fails)."""
    d, n = arm.cell_dots, CELLS_BY_DOTS[arm.cell_dots]
    lay = {tuple(COLOUR_INDEX[c] for row in g for c in row): k
           for k, g in enumerate(cell_layouts(arm).values())}
    cells = dots_idx[:n * d, :n * d].reshape(n, d, n, d).transpose(0, 2, 1, 3).reshape(n, n, d * d)
    out = np.zeros((n, n), np.uint8)
    for r in range(n):
        for c in range(n):
            k = lay.get(tuple(int(v) for v in cells[r, c]))
            if k is None:
                return None
            out[r, c] = k
    return out


def read_back(job: bytes, images: list[dict], manifest: dict, npz: dict[str, np.ndarray],
              refs: dict[str, bytes]) -> tuple[dict, dict]:
    """(a) the stream and (b) the decoded images against the manifest + npz."""
    body = stream_body(job)
    ops = tokenize(body)
    names = [o["op"] for o in ops]
    got, got_reset = interpret(ops), interpret(ops, reset_on_space=True)
    page, per = composed(manifest, npz, (dots(PAGE_MM[1]), dots(PAGE_MM[0])))
    by_id = {p["id"]: p for p in manifest["patches"]}
    rows, problems = [], []
    shas = {"dots_from_stream": 0, "dots_from_manifest_npz": 0, "states_from_stream": 0,
            "states_from_npz": 0, "states_from_seed": 0, "planes_from_stream": 0, "checked": 0}
    for plan_img, g, gr in zip(images, got, got_reset):
        x, y, w, h = plan_img["xywh"]
        b = g["begin"]
        heights = [k["BlockHeight"] for k in g["blocks"]]
        raster = decode(g)
        checks = {
            "position_size": g["cursor"] == (x, y) and [b["SourceWidth"], b["SourceHeight"]] == [w, h],
            "indexed_e8Bit": b.get("ColorMapping") == E["eIndexedPixel"] and b["ColorDepth"] == E["e8Bit"],
            "destination_equals_source": b.get("DestinationSize") == [w, h],
            "blocks_of_64": all(v == BLOCK_ROWS for v in heights[:-1]) and 0 < heights[-1] <= BLOCK_ROWS,
            "stride_padding_decoded": not isinstance(raster, str),
            "state_persistent": g["state"] == want_state(plan_img),
            "state_reset_on_SetColorSpace": gr["state"] == want_state(plan_img),
            "palette_768_uint16_length": g["space"]["palette"] is not None
            and len(g["space"]["palette"]) == 768 and g["space"]["palette_type"] == ("ubyte_array", "uint16"),
        }
        row = {"name": plan_img["name"], "state": g["state"], "state_reset_on_SetColorSpace": gr["state"],
               "blocks": len(heights), "wh": [w, h]}
        if isinstance(raster, str):
            problems.append(f"{plan_img['name']}: {raster}")
        else:
            pal = np.frombuffer(g["space"]["palette"], np.uint8).reshape(-1, 3)
            used = np.unique(raster)
            checks["indices_equal_plan"] = bool(np.array_equal(raster, plan_img["raster"]))
            checks["unused_entries_white"] = bool((np.delete(pal, used, axis=0) == 255).all())
            if plan_img["kind"] == "band":
                checks["rgb_equals_composed_page"] = bool(np.array_equal(pal[raster], page[y:y + h, x:x + w]))
                rgb_ok = all((pal[k] == COLOURS[list(COLOURS)[k]][0]).all() for k in used)
                checks["used_entries_are_the_colour_table"] = bool(rgb_ok and pal[0].tolist() == [255] * 3)
                row["differing_dots_vs_composed"] = int((pal[raster] != page[y:y + h, x:x + w]).any(2).sum())
                row["palette_entries_used"] = [list(COLOURS)[k] for k in used]
                for pid in plan_img["members"]:
                    p = by_id[pid]
                    arm = ARM_BY_KEY[p["arm"]]
                    px, py = dots(p["x_mm"]) - x, dots(p["y_mm"]) - y
                    sub = raster[py:py + PATCH_H_DOTS, px:px + PATTERN_DOTS]
                    st = states_from_dots(arm, sub)
                    seed_st = draw_states(arm, p["fraction"], STATE_SEED_BASE + pid)
                    shas["checked"] += 1
                    shas["dots_from_stream"] += sha(sub.tobytes()) == p["dots_sha256"]
                    shas["dots_from_manifest_npz"] += sha(per[pid].tobytes()) == p["dots_sha256"]
                    shas["states_from_stream"] += st is not None and sha(st.tobytes()) == p["states_sha256"]
                    shas["states_from_npz"] += sha(npz[f"states_{pid}"].tobytes()) == p["states_sha256"]
                    shas["states_from_seed"] += sha(seed_st.tobytes()) == p["states_sha256"] and p[
                        "seed"] == STATE_SEED_BASE + pid
                    planes = plane_table(p["neutral"])[sub[:PATTERN_DOTS]].transpose(2, 0, 1)
                    shas["planes_from_stream"] += bool(np.array_equal(planes, npz[f"planes_{pid}"]))
        row["checks"] = checks
        if not all(checks.values()):
            problems.append(f"{plan_img['name']}: failed {[k for k, v in checks.items() if not v]}")
        rows.append(row)
    band_order = [i["name"] for i in images if i["kind"] == "band"]
    want_order = [f"band{b['band']}" for k in range(len(KINDS)) for b in manifest["bands"] if b["kind"] == k]
    pre = preamble_checks(job, images, refs["S9"])
    spaces = [o for o in ops if o["op"] == "SetColorSpace"]
    a = {"operators": len(names), "operator_counts": dict(sorted(Counter(names).items())),
         "verdicts": {
             "operator_sequence_exact": names == expected_ops(images),
             "pclxl_bilevel_parse_agrees": [n for n, _, _ in xl.parse(body)] == names,
             "band_order_is_kind_order": band_order == want_order,
             "preambles_equal_S9_operators": pre["pass"],
             "every_palette_768_eRGB_e8Bit": len(spaces) == len(images) and all(
                 o["attrs"].get("ColorSpace") == E["eRGB"] and o["attrs"].get("PaletteDepth") == E["e8Bit"]
                 and len(o["attrs"].get("PaletteData", b"")) == 3 * PALETTE_ENTRIES for o in spaces),
             "every_image_ok": all(all(r["checks"].values()) for r in rows) and len(got) == len(images)},
         "preambles": pre, "images": rows, "problems": problems, "listing": listing(ops)}
    a["pass"] = all(a["verdicts"].values()) and not problems
    n = len(manifest["patches"])
    b_ = {"patch_shas": shas,
          "differing_dots_total": sum(r.get("differing_dots_vs_composed", 0) for r in rows)}
    b_["pass"] = (b_["differing_dots_total"] == 0 and shas["checked"] == n
                  and all(v == n for v in shas.values()))
    return a, b_


def render_checks(job_path: Path, manifest: dict, npz: dict[str, np.ndarray]) -> dict:
    with tempfile.TemporaryDirectory() as td:
        (fonts := Path(td) / "fonts").mkdir()
        (fonts / "stub.ttf").write_bytes(stub_font())
        img, messages = xl.render(job_path, Path(td) / "ppmraw.out", fonts, "ppmraw")
    page, _ = composed(manifest, npz, img.shape[:2])
    diff = (img != page).any(2)
    inked = (img != 255).any(2)
    covered = np.zeros(diff.shape, bool)
    rings = []
    for p in manifest["patches"]:
        x, y = dots(p["x_mm"]), dots(p["y_mm"])
        ring = np.zeros(diff.shape, bool)
        ring[y - 1:y + PATCH_H_DOTS + 1, x - 1:x + PATTERN_DOTS + 1] = True
        ring[y:y + PATCH_H_DOTS, x:x + PATTERN_DOTS] = False
        covered[y:y + PATCH_H_DOTS, x:x + PATTERN_DOTS] = True
        if inked[ring].any():
            rings.append(p["id"])
    fid_ok = []
    for f in manifest["fiducials"]:
        x, y, w, h = dots(f["x_mm"]), dots(f["y_mm"]), dots(f["w_mm"]), dots(f["h_mm"])
        covered[y:y + h, x:x + w] = True
        whole = bool((img[y:y + h, x:x + w] == 0).all())
        if inked[y - 1:y + h + 1, x - 1:x + w + 1].sum() != w * h or not whole:
            rings.append(f["id"])
        fid_ok.append(f["id"] if whole else f"{f['id']} not solid black")
    r = {"page_hw": list(img.shape[:2]), "render_sha256": sha(img.tobytes()), "gpcl6_messages": messages,
         "differing_dots_total": int(diff.sum()), "objects_with_ink_in_1dot_ring": rings,
         "fiducials_solid_black": fid_ok, "ink_outside_objects": int((inked & ~covered).sum()),
         "inked_dots": int(inked.sum()), "patches_checked": len(manifest["patches"])}
    r["pass"] = not messages and not r["differing_dots_total"] and not rings and not r["ink_outside_objects"]
    return r


def novelty_tokens(ops: list[dict]) -> dict[str, set]:
    """pclxl_probe_banded.tokens plus the two classes it cannot see: an enum value per OPERATOR (eTonerBlack
    = 0 is already an AllObjectTypes value of SetAdaptiveHalftoning), and the palette colours."""
    t = tokens(ops)
    t["operator attribute=enum value"] = {(o["op"], a, v) for o in ops for a, v in o["attrs"].items()
                                          if a in NOVELTY_ENUMS}
    pals = [o["attrs"]["PaletteData"] for o in ops
            if o["op"] == "SetColorSpace" and o["attrs"].get("PaletteData")]
    t["palette colour"] = {tuple(rgb) for pal in pals
                           for rgb in np.frombuffer(pal, np.uint8).reshape(-1, 3).tolist()}
    return t


def extra_structure(ops: list[dict]) -> dict:
    imgs, imgs_reset = interpret(ops), interpret(ops, reset_on_space=True)
    return {"neutral axis in force at images": {i["state"]["neutral"] for i in imgs},
            "neutral axis in force at images (reset on SetColorSpace)": {i["state"]["neutral"]
                                                                        for i in imgs_reset},
            "SetNeutralAxis count": sum(1 for o in ops if o["op"] == "SetNeutralAxis")}


def novelty(job: bytes, refs: dict[str, bytes]) -> dict:
    """Every token and structural feature of the job absent from the union of the references, and per
    reference group (S10p2 alone; S9 + S9b)."""
    new_ops = tokenize(stream_body(job))
    ref_ops = {k: tokenize(stream_body(v)) for k, v in refs.items()}
    tk_new = novelty_tokens(new_ops)
    tk_ref = {k: novelty_tokens(v) for k, v in ref_ops.items()}
    st_new = {**structure(new_ops), **extra_structure(new_ops)}
    st_ref = {k: {**structure(v), **extra_structure(v)} for k, v in ref_ops.items()}

    def diff(group: tuple[str, ...]) -> list[str]:
        out = []
        for cls, items in tk_new.items():
            seen = set().union(*(tk_ref[k][cls] for k in group))
            out += [f"{cls}: {item}" for item in sorted(items - seen, key=repr)]
        for key, v in st_new.items():
            refs_v = {k: st_ref[k][key] for k in group}
            if isinstance(v, set):
                extra = v - set().union(*refs_v.values())
                if extra:
                    out.append(f"{key}: {sorted(extra, key=repr)} (refs: "
                               f"{ {k: sorted(r, key=repr) for k, r in refs_v.items()} })")
            elif v not in refs_v.values():
                out.append(f"{key}: {v} (refs: {refs_v})")
        return out
    return {"vs_union_S10p2_S9_S9b": diff(tuple(refs)), "vs_S10p2": diff(("S10p2",)),
            "vs_S9_S9b": diff(("S9", "S9b"))}


def counts(patches: list[dict], bands: list[dict]) -> dict:
    key = Counter((p["arm"], p["fraction"], p["method"], p["neutral"], p["cell_dots"]) for p in patches)
    return {"total": len(patches), "slots": 29 * 42,
            "by_arm_fraction_method_neutral_cell": {"/".join(map(str, k)): n for k, n in sorted(key.items())},
            "by_arm": dict(sorted(Counter(p["arm"] for p in patches).items())),
            "by_fraction": dict(Counter(p["fraction"] for p in patches)),
            "by_method": dict(Counter(p["method"] for p in patches)),
            "by_neutral": dict(Counter(p["neutral"] for p in patches)),
            "by_cell_dots": {str(k): n for k, n in sorted(Counter(p["cell_dots"] for p in patches).items())},
            "by_kind": {f"{m}/{n}": sum(1 for p in patches if (p["method"], p["neutral"]) == (m, n))
                        for m, n in KINDS},
            "by_band": {str(b["band"]): f"{b['patches']} of {b['slots']} slots "
                        f"({b['method']}/{b['neutral']}, third {b['third']})" for b in bands},
            "replicates_per_third_ok": all(
                len({next(b["third"] for b in bands if b["band"] == p["band"]) for p in patches
                     if (p["arm"], p["fraction"], p["method"]) == k[:3]}) == REPLICATES for k in key)}


# ------------------------------------------------------------------------------------------------ manifest

def band_table(bands: list[dict], images: list[dict]) -> list[dict]:
    by = {i["band"]: i for i in images if i["kind"] == "band"}
    return [{"band": b["band"], "third": b["third"], "kind": b["kind"], "method": b["method"],
             "neutral": b["neutral"], "slot_rows": b["slot_rows"], "x_dots": by[b["band"]]["xywh"][0],
             "y_dots": by[b["band"]]["xywh"][1], "w_dots": by[b["band"]]["xywh"][2],
             "h_dots": by[b["band"]]["xywh"][3], "y_mm": mm(by[b["band"]]["xywh"][1]),
             "row_bytes": row_bytes(by[b["band"]]["xywh"][2], 8),
             "readimage_blocks": -(-by[b["band"]]["xywh"][3] // BLOCK_ROWS),
             "draw_position": [i["name"] for i in images].index(f"band{b['band']}"),
             "controls_after_SetColorSpace": [BLOCK_OPS[c] + (" eTonerBlack" if c == "tonerblack" else "")
                                              for c in by[b["band"]]["block"]],
             "patches": b["patches"], "slots": b["slots"], "members": by[b["band"]]["members"]}
            for b in bands]


def notes() -> list[str]:
    return [
        "WHY: S10p2 (printed 2026-10-05 11:27) read every single-toner state at 0-2 % cell error in "
        "isolation and the same corners at 21-26 % on the full data page; the engine lays single-toner "
        "solids (C (0,255,255), Y (255,255,0), M at (240,0,192) / (240,0,208), not at its corner) and never "
        "a two-toner overlap. S11 = the neighbourhood and alphabet question, plus K (eTonerBlack) as a fifth "
        "solid state.",
        "CONSTRUCTION = S10p2's (the banded job that printed; the per-object S10p crashed the formatter): "
        "fiducial images first (S9's four controls, default method), then twelve band images in KIND order "
        "(default process, default toner, highlpi process, highlpi toner), each after S9's preamble; a "
        "toner-black band's SetNeutralAxis carries eTonerBlack (0) instead of eProcessBlack (1), nothing "
        "else differs. No witness, no matrix bands, no PushGS/PopGS.",
        "ROW ALLOCATION: band images are NOT all four slot rows high as in S10p2. Twelve bands (four kinds x "
        "three thirds) of four rows would need 48 slot rows of the 42; per the contract the toner-black "
        "kinds get the rows they need (one slot row = 29 slots for 8 patches) and the rest goes to process "
        "black (six rows = 174 slots for 35 patches): per third 6 + 6 + 1 + 1 = 14 rows. Process-black "
        "images are 885 dots high (14 ReadImage blocks), toner-black images 117 (2 blocks).",
        "PALETTE: one global colour index table (manifest 'colours') in every band image; a band's palette "
        "carries only the colours it uses, the rest of the 256 entries white. K (index 6) and CMY (index 10) "
        "are both RGB (0,0,0): K appears only in toner-black bands (meant: K toner), CMY only in "
        "process-black bands (the engine's three-toner composite).",
        "PATCHES: 93 x 117 dots = pattern square + 24-dot bar; c2 patterns fill the top-left 92 x 92 dots, "
        "the last pattern row and column are white (index 0). Cell states: default_rng(41000 + id).choice("
        "len(alphabet), size=cells*cells, p=probabilities).reshape(cells, cells) as uint8 (row-major). "
        "states_sha256 = sha256 of that array's bytes; dots_sha256 = sha256 of the 117 x 93 uint8 array of "
        "GLOBAL palette indices (pattern square and bar, row-major). npz planes_<id> = (4, 93, 93) uint8 C, "
        "M, Y, K over the pattern square only, by the colour table's planes for the patch's band kind.",
        "FRACTIONS: for a two-state arm with white ({W,M}, {W,C}, {W,Y}, {W,K}) 'uniform' and 'whiteheavy' "
        "are the SAME distribution (P(W) = 0.5); both are placed as the contract asks, so these arms carry "
        "six draws per method instead of three.",
        "DOTMIX layouts (manifest per patch 'dot_masks', arms table 'cell_layouts'): c3 CM/CY/MY = the 3x3 "
        "checker with the first ink on (r + c) even (5 dots) and the second on odd (4); c3 CMY = C, M, Y by "
        "(r + c) mod 3 (3 + 3 + 3); c2 CM/CY/MY = first ink on the main diagonal; c2 CMY = C on the "
        "diagonal, M top-right, Y bottom-left.",
        f"LAYOUT: default_rng({LAYOUT_SEED}): per kind, per (arm, fraction) a permutation of the three "
        "thirds (replicate r in third perm[r]); then per band in page order a permutation of its slots. So "
        "every (arm, fraction, method) has one replicate in each page third.",
        "The npz is written with fixed zip member dates (1980-01-01), so its sha is deterministic.",
        "gpcl6 accepts SetNeutralAxis eTonerBlack, but its ppmraw render cannot show what the engine does "
        "with it; (0,0,0) renders black either way.",
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, type=Path,
                    help="job path (.pclxl); <stem>.manifest.json and the patterns npz go beside it")
    for k, name in REFS.items():
        ap.add_argument(f"--{k.lower()}", type=Path, default=None,
                        help=f"{k} job (default: {name} beside --out)")
    ap.add_argument("--verify", action="store_true", help="checks (a)-(h)")
    args = ap.parse_args()
    patches, fids, images, bands, job = build()
    refs = {k: (getattr(args, k.lower()) or args.out.parent / name).read_bytes() for k, name in REFS.items()}
    novel = novelty(job, refs)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(job)
    npz_path = args.out.with_name(NPZ_NAME)
    npz_raw = npz_bytes(patches)
    npz_path.write_bytes(npz_raw)
    manifest_path = args.out.with_name(args.out.stem + ".manifest.json")
    manifest = {
        "tag": TAG, "dpi": DPI, "page_mm": list(PAGE_MM), "bytes": len(job), "sha256": sha(job),
        "patterns_npz": {"file": NPZ_NAME, "bytes": len(npz_raw), "sha256": sha(npz_raw)},
        "fiducials": [public(f) for f in fids],
        "patch_px": {"pattern_dots": PATTERN_DOTS, "solid_dots": SOLID_DOTS},
        "slot_grid": {"pitch_mm": list(SLOT_PITCH_MM), "columns": 29, "rows": 42},
        "bands": band_table(bands, images),
        "patches": [public(p) for p in patches],
        "arms": arms_table(), "colours": colour_table(), "planes_order": list(PLANES),
        "layout_seed": LAYOUT_SEED, "state_seed_base": STATE_SEED_BASE,
        "novelty": novel["vs_union_S10p2_S9_S9b"], "novelty_by_reference": novel,
        "notes": notes(), "counts": counts(patches, bands),
        "generator": " ".join(["PYTHONPATH=src:.", sys.executable, *sys.argv]),
    }
    manifest_path.write_text(json.dumps({**manifest, "verification": "not run"}, indent=1) + "\n")
    if args.verify:
        v: dict = {}
        npz = load_npz(npz_path)
        v["a_read_back"], v["b_decode_vs_manifest_npz"] = read_back(job, images, manifest, npz, refs)
        v["a_frame_vs_S9"] = frame_checks(job, refs["S9"], FRAME)
        v["c_gpcl6_ppmraw"] = render_checks(args.out, manifest, npz)
        v["d_geometry"] = geometry_checks(patches, fids, images)
        again = build()
        v["e_two_builds_identical"] = {
            "job": again[4] == job, "npz": npz_bytes(again[0]) == npz_raw,
            "patches": [public(p) for p in again[0]] == manifest["patches"],
            "bands": band_table(again[3], again[2]) == manifest["bands"]}
        v["f_novelty"] = novel
        v["g_counts"] = manifest["counts"]
        s10p2 = banded.emit_job(banded.plan(banded.FULL)[2], banded.FULL)
        v["h_S10p2_rebuilt"] = {"sha256": sha(s10p2), "unchanged": sha(s10p2) == S10P2_SHA}
        v["pass"] = all([v["a_read_back"]["pass"], v["b_decode_vs_manifest_npz"]["pass"],
                         all(v["a_frame_vs_S9"].values()), v["c_gpcl6_ppmraw"]["pass"],
                         v["d_geometry"]["pass"],
                         all(v["e_two_builds_identical"].values()), v["g_counts"]["replicates_per_third_ok"],
                         v["h_S10p2_rebuilt"]["unchanged"]])
        manifest["verification"] = v
        manifest_path.write_text(json.dumps(manifest, indent=1, default=list) + "\n")
    print(f"{args.out}: {len(job)} B sha {manifest['sha256']}")
    print(f"{npz_path}: {len(npz_raw)} B sha {manifest['patterns_npz']['sha256']}")
    print(json.dumps(manifest["counts"], indent=1))
    print("novelty (vs the union of S10p2, S9, S9b):\n  " + "\n  ".join(novel["vs_union_S10p2_S9_S9b"]))
    if isinstance(manifest.get("verification"), dict):
        shown = {k: v for k, v in manifest["verification"].items() if k not in ("g_counts", "f_novelty")}
        shown["a_read_back"] = {k: v for k, v in shown["a_read_back"].items()
                                if k not in ("images", "listing", "preambles")}
        print(json.dumps(shown, indent=1, default=list))


if __name__ == "__main__":
    main()
