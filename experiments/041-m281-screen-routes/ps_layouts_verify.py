"""e041 S17 — the checks behind `ps_layouts.py --verify` (split along the build / verify seam).

(1) gs 10.08 ppmraw -r600 renders -- default ICC and -dUseFastColor -- against the page composed from the
manifest + npz alone, twice: states + layouts through each band's layout_catalogue, and the planes alone
(every dot one toner or none); against the objects painted; U14's mask black exactly on its K cells;
(2) gs strict silent + a stub run logging every HP call, image and imagemask in sequence, exact;
(3) byte audit against the printed S16 (wrapper, header shape, setpagedevice, prologue, tail, HP call lines
per (neutral, method)) and the imagemask block line for line against src/holo/gen/ps.py PSDoc.put_bitmap;
(4) every window's states / layouts / planes against the rendered dots; every catalogue entry against the
schema's formula (re-derived here, not imported) and its dot counts; the draws re-derived from the seed;
(5) geometry; (6) two builds identical; (7) S16, S15, S14, S12 rebuilt unchanged; (8) novelty vs the printed
S16 and S15; (9) sizes; (10) measure/e041_scale_readout.py and measure/e041_band_screen.py as they stand,
on an in-memory clean synthetic (e041_scale_synth.page_raster at 4x4 px per dot, or, where that module now
has page_planes + paint_scan instead, those at 2400 dpi, identity pose, no pad / blur / noise): passes when
both run, every window is read, cross and band state errors are 0 in every band, and leave-one-out errors
sit only in bands with a multi-layout state (U3-U7: a state reader sees a multi-modal class; reported).
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import re
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import numpy as np

import ps_layouts as s17
import ps_reset as s15
import ps_scale as s14
import ps_trigger as s16
import ps_trigger_verify as tv
import ps_mixture as s12
from pcl_planar import sha

PAGE_H_DOTS, PAGE_W_DOTS = s17.PAGE_H_DOTS, s17.PAGE_W_DOTS


def data_bands(man: dict) -> list[dict]:
    return [b for b in man["bands"] if b["alphabet"] is not None]


def band_tiles(b: dict, colours: list[str]) -> np.ndarray:
    """(states, max layouts, cd, cd) colour index from the manifest's catalogue; unused slots 255."""
    cat = b["layout_catalogue"]
    n_max = max(len(cat[s]) for s in b["states"])
    cd = b["cell_dots"]
    t = np.full((len(b["states"]), n_max, cd, cd), 255, np.uint8)
    for i, s in enumerate(b["states"]):
        for j, e in enumerate(cat[s]):
            t[i, j] = [[colours.index(c) for c in row] for row in e["grid"]]
    return t


def used_colours(man: dict, b: dict) -> list[str]:
    used = {c for es in b["layout_catalogue"].values() for e in es for row in e["grid"] for c in row}
    return [c for c in man["colours"] if c in used]


def paint_cells(st: np.ndarray, lay: np.ndarray, tiles: np.ndarray) -> np.ndarray:
    r, c = st.shape
    cd = tiles.shape[2]
    out = tiles[st, lay]
    return out.transpose(0, 2, 1, 3).reshape(r * cd, c * cd)


def composed(man: dict, arrays: dict[str, np.ndarray], from_planes: bool) -> tuple[np.ndarray, int]:
    """The page from the manifest + npz alone: fiducials, then every band through its catalogue (or from its
    planes: C -> C-solid, M -> M-solid, Y -> Y, K -> (0,0,0)); (page, dots carrying more than one toner)."""
    page = np.full((PAGE_H_DOTS, PAGE_W_DOTS, 3), 255, np.uint8)
    for f in man["fiducials"]:
        x, y, w, h = f["xywh_dots"]
        page[y:y + h, x:x + w] = f["rgb"]
    multi = 0
    col = man["colours"]
    plane_rgb = np.array([col["C-solid"]["rgb"], col["M-solid"]["rgb"], col["Y"]["rgb"], [0, 0, 0]], np.uint8)
    for b in data_bands(man):
        x, y, w, h = b["x_dots"], b["y_dots"], b["w_dots"], b["h_dots"]
        if from_planes:
            pl = arrays[f"planes_{b['name']}"]
            n = pl.sum(0)
            multi += int((n > 1).sum())
            rect = np.full((h, w, 3), 255, np.uint8)
            for k in range(4):
                rect[pl[k] == 1] = plane_rgb[k]
        else:
            colours = used_colours(man, b)
            rgb = np.array([[0, 0, 0] if c == "K-mask" else col[c]["rgb"] for c in colours], np.uint8)
            rect = rgb[paint_cells(arrays[f"states_{b['name']}"], arrays[f"layouts_{b['name']}"],
                                   band_tiles(b, colours))]
        page[y:y + h, x:x + w] = rect
    return page, multi


# ------------------------------------------------------------------------------------------------ (1)

def render_checks(job_path: Path, man: dict, arrays: dict[str, np.ndarray], objects: list[dict]) -> dict:
    fast, fmsg, frc = tv.render(job_path, True)
    dflt, dmsg, drc = tv.render(job_path, False)
    page_cat, _ = composed(man, arrays, False)
    page_pl, multi = composed(man, arrays, True)
    masks = tv.mask_union(objects)
    covered = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), bool)
    fid_black = True
    for f in man["fiducials"]:
        x, y, w, h = f["xywh_dots"]
        fid_black &= bool((fast[y:y + h, x:x + w] == 0).all())
        covered[y:y + h, x:x + w] = True
    for b in man["bands"]:
        covered[b["y_dots"]:b["y_dots"] + b["h_dots"], b["x_dots"]:b["x_dots"] + b["w_dots"]] = True
    diff_dm = (dflt != fast).any(2)
    dvals = Counter(tuple(int(v) for v in px) for px in dflt[masks][:200000])
    u14 = next(b for b in man["bands"] if b["name"] == "U14")
    k14 = s14.expand(arrays["states_U14"] == u14["states"].index("K"), u14["cell_dots"])
    r14 = fast[u14["y_dots"]:u14["y_dots"] + u14["h_dots"], u14["x_dots"]:u14["x_dots"] + u14["w_dots"]]
    res = {"gs_fastcolor": {"returncode": frc, "messages": fmsg, "render_sha256": sha(fast.tobytes())},
           "gs_default_icc": {"returncode": drc, "messages": dmsg, "render_sha256": sha(dflt.tobytes())},
           "page_hw": list(fast.shape[:2]),
           "differing_dots_fast_vs_composed_states_layouts_catalogue": int((fast != page_cat).any(2).sum()),
           "differing_dots_fast_vs_composed_from_planes": int((fast != page_pl).any(2).sum()),
           "dots_with_more_than_one_toner": multi,
           "differing_dots_fast_vs_painted_objects": int((fast != tv.painted(objects)).any(2).sum()),
           "default_vs_fast_differing_dots": int(diff_dm.sum()),
           "default_vs_fast_differ_exactly_on_mask_bits": bool(np.array_equal(diff_dm, masks)),
           "mask_bits_total": int(masks.sum()),
           "default_icc_values_on_mask_bits": {str(k): v for k, v in dvals.items()},
           "differing_dots_default_vs_painted_with_that_value": int((dflt != tv.painted(
               objects, next(iter(dvals)) if len(dvals) == 1 else (0, 0, 0))).any(2).sum()),
           "fiducials_solid_black": fid_black,
           "U14_black_exactly_on_K_cells": bool(np.array_equal((r14 == 0).all(2), k14)),
           "U14_white_elsewhere": bool((r14[~k14] == 255).all()),
           "U14_K_cell_dots": int(k14.sum()),
           "U14_mask_bits_equal_K_cells": int(masks.sum()) == int(k14.sum()),
           "non_white_outside_objects": int(((fast != 255).any(2) & ~covered).sum()),
           "inked_dots": int((fast != 255).any(2).sum())}
    res["pass"] = (frc == 0 and drc == 0 and not fmsg and not dmsg
                   and res["differing_dots_fast_vs_composed_states_layouts_catalogue"] == 0
                   and res["differing_dots_fast_vs_composed_from_planes"] == 0 and multi == 0
                   and res["differing_dots_fast_vs_painted_objects"] == 0
                   and res["default_vs_fast_differ_exactly_on_mask_bits"] and len(dvals) == 1
                   and res["differing_dots_default_vs_painted_with_that_value"] == 0
                   and fid_black and res["U14_black_exactly_on_K_cells"] and res["U14_white_elsewhere"]
                   and res["U14_mask_bits_equal_K_cells"] and res["non_white_outside_objects"] == 0)
    return res


# ------------------------------------------------------------------------------------------------ (2)

def guard_checks(job: bytes, objects: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as td:
        plain = Path(td) / "s17.ps"
        plain.write_bytes(job)
        strict = s12.gs(["-q", "-sDEVICE=nullpage"], plain)
        stubbed = Path(td) / "s17-stubs.ps"
        cut = job.index(b"%%EndComments\n") + len(b"%%EndComments\n")
        stubbed.write_bytes(job[:cut] + s12.stub_prologue() + tv.IMAGEMASK_STUB + job[cut:])
        run = s12.gs(["-q", "-sDEVICE=nullpage"], stubbed)
    log = [ln for ln in run.stderr.splitlines() if ln.startswith(("HPCALL", "IMAGE", "SHOWPAGE"))]
    want = [ln for o in objects for ln in tv.hp_expect(o)] + ["SHOWPAGE"]
    per_obj: dict[str, list[str]] = {}
    at = 0
    for o in objects:
        n = len(tv.hp_expect(o))
        per_obj[o["name"]] = log[at:at + n]
        at += n
    strict_text = (strict.stdout + strict.stderr).strip()
    four = {m: ["HPCALL HPImageNeutralAxis (ProcBlack)", f"HPCALL ColorSmartImageHalftone ({h})",
                "HPCALL HPColorTrapping (Off)", "HPCALL HPImageAdaptiveHalftoning false"]
            for m, h in (("smooth", "Smooth"), ("detail", "Detail"))}
    images = [o for o in objects if o["kind"] != "imagemask"]
    four_ok = all(per_obj[o["name"]][:4] == four[o["method"]] and len(per_obj[o["name"]]) == 5
                  for o in images)
    res = {"strict_returncode": strict.returncode, "strict_messages": strict_text,
           "stub_returncode": run.returncode, "stub_log_lines": len(log), "expected_lines": len(want),
           "stub_sequence_exact": log == want,
           "stub_calls": dict(Counter(ln.split()[1] for ln in log if ln.startswith("HPCALL"))),
           "stub_images": sum(ln.startswith("IMAGE ") for ln in log),
           "stub_imagemasks": sum(ln.startswith("IMAGEMASK ") for ln in log),
           "stub_other_output": "\n".join(ln for ln in run.stderr.splitlines() if ln not in set(log)).strip(),
           "every_image_four_hp_calls_ProcBlack_in_S16_order": four_ok,
           "stub_log_per_object": {k: per_obj[k] for k in ("U1", "U12", "U13", "U14-mask")}}
    if log != want:
        res["first_mismatch"] = next(([k, a, b] for k, (a, b) in enumerate(zip(log, want)) if a != b),
                                     [min(len(log), len(want)), None, None])
    res["pass"] = (strict.returncode == 0 and not strict_text and run.returncode == 0 and log == want
                   and not res["stub_other_output"] and four_ok)
    return res


# ------------------------------------------------------------------------------------------------ (3)

def byte_audit(job: bytes, records: list[dict], objects: list[dict], s16_job: bytes, s16_man: dict) -> dict:
    i16, i17 = s16_job.index(b"%!PS"), job.index(b"%!PS")
    e16, e17 = s16_job.index(b"%%EndComments\n"), job.index(b"%%EndComments\n")
    k16, k17 = s16_job.index(b"%%Page: 1 1\n"), job.index(b"%%Page: 1 1\n")
    h16 = [ln for ln in s16_job[i16:e16].split(b"\n") if not ln.startswith((b"%%Title", b"%%Creator"))]
    h17 = [ln for ln in job[i17:e17].split(b"\n") if not ln.startswith((b"%%Title", b"%%Creator"))]
    lines = tv.skeleton(job, records).split(b"\n")
    s16_seq: dict[tuple[str, str], set[tuple[str, ...]]] = {}
    for r in s16_man["ps_structure"]["images"]:
        if r["kind"] != "imagemask":
            s16_seq.setdefault((r["neutral"], r["method"]), set()).add(tuple(tv.hp_lines(r["operators"])))
    imgs = [r for r in records if r["kind"] != "imagemask"]
    masks = [(r, o) for r, o in zip(records, objects) if r["kind"] == "imagemask"]
    hp_match = [s16_seq.get((r["neutral"], r["method"])) == {tuple(tv.hp_lines(r["operators"]))}
                for r in imgs]
    s16_head = re.search(rb"% T9-mask: [^\n]*", s16_job).group().decode()
    s16_masks = [r for r in s16_man["ps_structure"]["images"] if r["kind"] == "imagemask"]
    mask_rows = []
    for r, o in masks:
        start = r["data_offset"] - len(("\n".join(r["operators"]) + "\n").encode())
        end = r["data_offset"] + tv.data_len(r) + len(b"grestore\n")
        ours = job[start:end].decode().split("\n")[:-1]
        x, y, w, h = r["xywh_dots"]
        ref = tv.holo_block(o["bits"], x, y)
        head = job[:start].rsplit(b"\n", 2)[-2].decode()
        ops16 = [m["operators"] for m in s16_masks]
        mask_rows.append({"object": r["image"], "lines": len(ours), "equal_to_put_bitmap_lines": ours == ref,
                          "operator_lines": [a for a in ours if not re.fullmatch(r"[0-9a-f]+", a)],
                          "operator_templates_equal_S16_masks": all(
                              [tv.template(a) for a in r["operators"]] == [tv.template(a) for a in q]
                              for q in ops16),
                          "comment_head": head,
                          "comment_head_equals_S16_T9_mask_name_aside": head == s16_head.replace("T9", "U14"),
                          "hp_or_colorsmart_in_block": any("HP" in a or "ColorSmart" in a for a in ours)})
    end = b"grestore\n"
    res = {"wrapper_head_equals_S16_name_aside": job[:i17] == s16_job[:i16].replace(
               f'JOB NAME="{s16.JOB_NAME}"'.encode(), f'JOB NAME="{s17.JOB_NAME}"'.encode()),
           "header_shape_equals_S16_title_creator_aside": h16 == h17,
           "setpagedevice_equals_S16": (job[e17 + 14:].split(b"\n", 1)[0] + b"\n" == s12.SETPAGEDEVICE
                                        and s16_job.count(s12.SETPAGEDEVICE) == 1
                                        and job.count(s12.SETPAGEDEVICE) == 1),
           "prologue_equals_S16": s16_job[e16 + 14:k16] == job[e17 + 14:k17] == s12.SETPAGEDEVICE
           + s12.prologue(),
           "tail_equals_S16": job.endswith(s17.TAIL) and s16_job[s16_job.rindex(end) + len(end):]
           == job[job.rindex(end) + len(end):],
           "hp_call_lines_equal_S16_per_neutral_and_method": all(hp_match),
           "imagemask_block_equal_holo_put_bitmap": all(m["equal_to_put_bitmap_lines"] for m in mask_rows)
           and len(mask_rows) == 1,
           "header_lines": job[i17:e17].decode().split("\n"),
           "S16_hp_sequences_by_neutral_method": {f"{n}/{m}": [list(q) for q in sorted(v)]
                                                  for (n, m), v in sorted(s16_seq.items())},
           "imagemask_blocks": mask_rows,
           "ColorSmartColorMatching_occurrences": job.count(b"ColorSmartColorMatching"),
           "showpage_lines": lines.count(b"showpage"), "image_operators": lines.count(b">> image"),
           "imagemask_operators": sum(ln.endswith(b" imagemask") for ln in lines),
           "gsave": lines.count(b"gsave"), "grestore": lines.count(b"grestore"),
           "non_ascii_bytes_after_wrapper": sum(1 for c in job[len(s17.WRAPPER_HEAD):-len(s12.WRAPPER_TAIL)]
                                                if c > 126 or (c < 32 and c != 10)),
           "data_lines_starting_with_percent": sum(
               ln.startswith(b"%") for r in records
               for ln in job[r["data_offset"]:r["data_offset"] + tv.data_len(r)].split(b"\n")),
           "skeleton_bytes": len(b"\n".join(lines))}
    res["pass"] = (all(res[k] for k in list(res)[:7]) and res["ColorSmartColorMatching_occurrences"] == 0
                   and all(m["operator_templates_equal_S16_masks"]
                           and m["comment_head_equals_S16_T9_mask_name_aside"]
                           and not m["hp_or_colorsmart_in_block"] for m in mask_rows)
                   and all(len(v) == 1 for v in s16_seq.values()) and res["showpage_lines"] == 1
                   and res["image_operators"] == len(imgs) and res["imagemask_operators"] == len(masks)
                   and res["gsave"] == res["grestore"] == len(records)
                   and res["non_ascii_bytes_after_wrapper"] == 0
                   and res["data_lines_starting_with_percent"] == 0)
    return res


# ------------------------------------------------------------------------------------------------ (4)

SINGLE = {"C": "C-solid", "M": "M-solid", "Y": "Y"}


def formula_grid(state: str, e: dict, cd: int) -> list[list[str]] | None:
    """The schema's formula for a catalogue entry, written out independently of ps_layouts."""
    lid, o, p = e["id"], e["orientation"], e["phase"]
    rng = range(cd)
    if lid == "solid":
        return None
    if state == "CMY":
        if cd == 2:
            return [["C-solid", "M-solid"], ["Y", "C-solid"]] if lid == "diag" else []
        t = ("C-solid", "M-solid", "Y")
        if o == "-":
            return [[t[((r + c) + p) % 3] for c in rng] for r in rng]
        return [[t[((c - r) % 3 + p) % 3] for c in rng] for r in rng]
    a, b = SINGLE[state[0]], SINGLE[state[1]]
    if cd == 2:
        on = {"diag": [(0, 0), (1, 1)], "col": [(0, 0), (1, 0)], "row": [(0, 0), (0, 1)]}[lid]
        return [[a if (r, c) in on else b for c in rng] for r in rng]
    if lid == "X":
        return [[a if (r + c) % 2 == 0 else b for c in rng] for r in rng]
    if o == "+":
        sel = {0: (0, 1), 1: (-1, 0)}[p]
        return [[a if (c - r) in sel else b for c in rng] for r in rng]
    sel = {0: (2, 3), 1: (1, 2)}[p]
    return [[a if (r + c) in sel else b for c in rng] for r in rng]


def entry_checks(state: str, e: dict, cd: int) -> dict:
    g = e["grid"]
    cnt = Counter(c for row in g for c in row)
    lid = e["id"]
    if lid == "solid":
        ok = len(cnt) == 1 and len(g) == cd and all(len(row) == cd for row in g)
        return {"counts": dict(cnt), "formula": True, "counts_ok": ok, "isolated_B": None}
    want = formula_grid(state, e, cd)
    iso = None
    if state == "CMY":
        exp = {"C-solid": 3, "M-solid": 3, "Y": 3} if cd == 3 else {"C-solid": 2, "M-solid": 1, "Y": 1}
        ok = dict(cnt) == exp
    else:
        a, b = SINGLE[state[0]], SINGLE[state[1]]
        exp = {a: 5, b: 4} if cd == 3 else {a: 2, b: 2}
        ok = dict(cnt) == exp
        if lid.startswith("band"):
            iso = s17.isolated_b(g, b)
            ok &= len(iso) == 1
    meta = ((e["orientation"], e["phase"]) == (None, None) if lid in ("X", "diag", "col", "row")
            else (e["orientation"] == lid[-2] and e["phase"] == int(lid[-1])))
    return {"counts": dict(cnt), "formula": g == want and meta, "counts_ok": ok,
            "isolated_B": [list(t) for t in iso] if iso is not None else None}


EXPECTED_N = {"U3": {"CMY": 2}, "U4": {"CM": 2, "CY": 2, "MY": 2, "CMY": 2},
              "U5": {"CM": 2, "CY": 2, "MY": 2, "CMY": 3}, "U6": {"CM": 4, "CY": 4, "MY": 4, "CMY": 6},
              "U7": {"CM": 2, "CY": 2, "MY": 2}}


def catalogue_checks(man: dict, arrays: dict[str, np.ndarray]) -> dict:
    bad, per_entry, order_ok, n_ok, draw_ok, freq = [], {}, True, True, True, {}
    for b in data_bands(man):
        cd, cat = b["cell_dots"], b["layout_catalogue"]
        n_ok &= set(cat) == set(b["states"]) and all(len(cat[s]) >= 1 for s in b["states"])
        n_ok &= {s: len(v) for s, v in cat.items() if len(v) > 1} == EXPECTED_N.get(b["name"], {})
        for s, es in cat.items():
            ids = [e["id"] for e in es]
            key = [("+" == e["orientation"], e["phase"] or 0) for e in es]
            order_ok &= len(set(ids)) == len(ids) and key == sorted(key)
            for e in es:
                r = entry_checks(s, e, cd)
                per_entry.setdefault(f"c{cd} {s} {e['id']}", r["counts"] | (
                    {"isolated_B": r["isolated_B"]} if r["isolated_B"] else {}))
                if not (r["formula"] and r["counts_ok"]):
                    bad.append(f"{b['name']} {s} {e['id']}")
        n = np.array([len(cat[s]) for s in b["states"]], np.int64)
        rng = np.random.default_rng(b["seed"])
        st = rng.choice(len(b["states"]), size=tuple(b["cells_hw"]))
        lay = np.floor(rng.random(st.shape) * n[st]).astype(np.int64) if (n > 1).any() else np.zeros_like(st)
        draw_ok &= (np.array_equal(st, arrays[f"states_{b['name']}"])
                    and np.array_equal(lay, arrays[f"layouts_{b['name']}"])
                    and arrays[f"states_{b['name']}"].dtype == np.uint8
                    and arrays[f"layouts_{b['name']}"].dtype == np.uint8
                    and bool((arrays[f"layouts_{b['name']}"][n[st] == 1] == 0).all())
                    and b["layout_draw"] == bool((n > 1).any()))
        if (n > 1).any():
            freq[b["name"]] = {s: np.bincount(lay[st == i], minlength=n[i]).tolist()
                               for i, s in enumerate(b["states"]) if n[i] > 1}
    return {"entries_bad": bad, "entry_dot_counts": per_entry, "catalogue_order_minus_before_plus": order_ok,
            "candidate_counts_as_specified": n_ok, "draws_rederived_from_seed_equal_npz": draw_ok,
            "layout_frequencies_per_state": freq,
            "pass": not bad and order_ok and n_ok and draw_ok}


def window_checks(img: np.ndarray, man: dict, npz_path: Path, objects: list[dict]) -> dict:
    """Every window: states / layouts / planes sliced from the npz against the render's dots decoded through
    the band's colours (fast render)."""
    bands = {b["name"]: b for b in data_bands(man)}
    col = man["colours"]
    with np.load(npz_path) as npz:
        arrays = {k: npz[k] for k in npz.files}
    per_band, bad, ok, unique_rgb = Counter(), [], 0, True
    dec: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for name, b in bands.items():
        used = used_colours(man, b)
        rgb = np.array([[0, 0, 0] if c == "K-mask" else col[c]["rgb"] for c in used], np.uint8)
        unique_rgb &= len({tuple(v) for v in rgb}) == len(used)
        ink = np.array([[int(p in col[c]["planes"]) for p in man["planes_order"]] for c in used], np.uint8)
        dec[name] = (rgb, band_tiles(b, used), ink)
    for w in man["windows"]:
        b = bands[w["band"]]
        rgb, tiles, ink = dec[w["band"]]
        wc = w["cells"]
        cy, cx = w["cell_yx"]
        st = arrays[f"states_{b['name']}"][cy:cy + wc, cx:cx + wc]
        lay = arrays[f"layouts_{b['name']}"][cy:cy + wc, cx:cx + wc]
        dy, dx = w["y_dots"] - b["y_dots"], w["x_dots"] - b["x_dots"]
        pl = arrays[f"planes_{b['name']}"][:, dy:dy + w["h_dots"], dx:dx + w["w_dots"]]
        win = img[w["y_dots"]:w["y_dots"] + w["h_dots"], w["x_dots"]:w["x_dots"] + w["w_dots"]]
        match = (win[:, :, None, :] == rgb[None, None]).all(3)
        decoded = match.argmax(2)
        good = (bool((match.sum(2) == 1).all()) and np.array_equal(decoded, paint_cells(st, lay, tiles))
                and np.array_equal(pl, np.moveaxis(ink[decoded], 2, 0)) and st.shape == (wc, wc))
        ok += good
        per_band[w["band"]] += 1
        if not good:
            bad.append(w["id"])
    lut = {o["name"]: o["palette"].tobytes() for o in objects if o["kind"] == "band"}
    res = {"windows": len(man["windows"]), "equal": ok, "per_band": dict(per_band), "first_bad": bad[:5],
           "band_colour_rgb_unique": unique_rgb,
           "band_images": len(lut),
           "every_band_image_lookup_equals_S16_T11": all(v == s16.lookup_array("cmy4").tobytes()
                                                    for v in lut.values()),
           "state_counts": {n: np.bincount(arrays[f"states_{n}"].ravel(), minlength=len(b["states"])).tolist()
                            for n, b in bands.items()},
           "catalogue": catalogue_checks(man, arrays)}
    res["pass"] = (ok == len(man["windows"]) and unique_rgb and res["every_band_image_lookup_equals_S16_T11"]
                   and len(lut) == 13 and res["catalogue"]["pass"])
    return res


# ------------------------------------------------------------------------------------------------ (5)

def geometry_checks(man: dict, objects: list[dict]) -> dict:
    fr = [tuple(f["xywh_dots"]) for f in man["fiducials"]]
    br = [(b["x_dots"], b["y_dots"], b["w_dots"], b["h_dots"]) for b in man["bands"]]
    count = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), np.uint8)
    for x, y, w, h in fr + br:
        count[y:y + h, x:x + w] += 1
    img_count = np.zeros_like(count)
    for o in objects:
        x, y, w, h = o["xywh"]
        img_count[y:y + h, x:x + w] += 1
    bands = {b["name"]: b for b in man["bands"]}
    win_ok = all(bands[w["band"]]["x_dots"] <= w["x_dots"] and w["x_dots"] + w["w_dots"]
                 <= bands[w["band"]]["x_dots"] + bands[w["band"]]["w_dots"]
                 and bands[w["band"]]["y_dots"] <= w["y_dots"] and w["y_dots"] + w["h_dots"]
                 <= bands[w["band"]]["y_dots"] + bands[w["band"]]["h_dots"]
                 and w["w_dots"] == w["h_dots"] == w["cells"] * w["cell_dots"]
                 and w["cells"] == s17.WINDOW_CELLS[w["cell_dots"]]
                 and (w["x_dots"] - bands[w["band"]]["x_dots"]) % w["w_dots"] == 0
                 and (w["y_dots"] - bands[w["band"]]["y_dots"]) % w["h_dots"] == 0 for w in man["windows"])
    page = sorted(man["bands"], key=lambda b: b["y_dots"])
    gaps = [page[k + 1]["y_dots"] - page[k]["y_dots"] - page[k]["h_dots"] for k in range(len(page) - 1)]
    by_band = {b["name"]: [w for w in man["windows"] if w["band"] == b["name"]] for b in data_bands(man)}
    obj_rect = all(o["xywh"] == (bands[o["band"]]["x_dots"], bands[o["band"]]["y_dots"],
                                 bands[o["band"]]["w_dots"], bands[o["band"]]["h_dots"])
                   for o in objects if o["band"] is not None)
    y_law = all(b["y_dots"] == 283 + 462 * b["band"] and b["x_dots"] == 283 and b["w_dots"] == 4392
                and b["h_dots"] == 438 for b in man["bands"])
    res = {"all_inside_page": all(0 <= x and 0 <= y and x + w <= PAGE_W_DOTS and y + h <= PAGE_H_DOTS
                                  for x, y, w, h in fr + br + [o["xywh"] for o in objects]),
           "fiducials_bands_overlap_dots": int((count > 1).sum()),
           "object_overlap_dots": int((img_count > 1).sum()),
           "objects_equal_their_band_rect": obj_rect,
           "bands_at_x283_y283_plus_462k_4392x438": y_law,
           "windows_whole_inside_their_band_on_the_grid": win_ok, "band_gaps_dots": sorted(set(gaps)),
           "fiducial_clearance_dots": min(s15.separation(f, b) for f in fr for b in br),
           "fiducials_equal_S16": man["fiducials"] == s16.build()[1]["fiducials"],
           "first_band_y_dots": page[0]["y_dots"], "last_end_dots": page[-1]["y_dots"] + page[-1]["h_dots"],
           "last_end_limit_dots": s17.LAST_END_DOTS,
           "data_bands": len(data_bands(man)),
           "cells_hw": {b["name"]: b["cells_hw"] for b in data_bands(man)},
           "windows": len(man["windows"]),
           "window_grid_per_band": {nm: [len({w["y_dots"] for w in ws}), len({w["x_dots"] for w in ws})]
                                    for nm, ws in by_band.items()}}
    res["pass"] = (res["all_inside_page"] and res["fiducials_bands_overlap_dots"] == 0
                   and res["object_overlap_dots"] == 0 and obj_rect and y_law and win_ok
                   and all(g == 24 for g in gaps) and res["last_end_dots"] == 6727 <= s17.LAST_END_DOTS
                   and res["fiducial_clearance_dots"] > 0 and res["fiducials_equal_S16"]
                   and res["data_bands"] == 14
                   and all(v == [4, 47] for v in res["window_grid_per_band"].values()))
    return res


# ------------------------------------------------------------------------------------------------ (8)

def novelty(job: bytes, records: list[dict], man: dict, s16_job: bytes, s16_man: dict, s15_job: bytes,
            s15_man: dict) -> dict:
    sk17 = tv.skeleton(job, records)
    sk16 = tv.skeleton(s16_job, s16_man["ps_structure"]["images"])
    sk15 = s14.skeleton(s15_job, s15_man["ps_structure"]["images"])
    c17, c16, c15 = s14.constructs(job), s14.constructs(s16_job), s14.constructs(s15_job)
    (o17, l17), (o16, l16), (o15, l15) = tv.tokens(sk17), tv.tokens(sk16), tv.tokens(sk15)
    sh17, sh16, sh15 = tv.shapes(sk17), tv.shapes(sk16), tv.shapes(sk15)
    lk17, lk16, lk15 = tv.lookup_lists(job), tv.lookup_lists(s16_job), tv.lookup_lists(s15_job)
    masks = [r for r in records if r["kind"] == "imagemask"]
    m16 = [r for r in s16_man["ps_structure"]["images"] if r["kind"] == "imagemask"]
    old_alpha = ({tuple(b["states"]) for b in s16_man["bands"] if b.get("states")}
                 | {tuple(v) for v in s16_man["alphabets"].values()}
                 | {tuple(v) for v in s15_man.get("alphabets", {}).values()})
    alpha17 = {b["alphabet"]: b["states"] for b in data_bands(man)}

    def new(a: Any, *bs: Any) -> list:
        return sorted(set(a) - set().union(*[set(b) for b in bs]))
    return {
        "operators_new_vs_S16_and_S15": new(o17, o16, o15),
        "literal_names_new_vs_S16_and_S15": new(l17, l16, l15),
        "line_shapes_new_vs_S16_and_S15": {s: sh17[s] for s in new(sh17, sh16, sh15)},
        "hp_calls_new": new(c17["hp_calls"], c16["hp_calls"], c15["hp_calls"]),
        "colour_spaces_new": new(c17["colour_spaces"], c16["colour_spaces"], c15["colour_spaces"]),
        "filters_new": new(c17["filters"], c16["filters"], c15["filters"]),
        "other_constructs_new": new(c17["other_constructs"], c16["other_constructs"],
                                    c15["other_constructs"]),
        "image_sizes_new": new(c17["image_sizes"], c16["image_sizes"], c15["image_sizes"]),
        "image_sizes_S17": c17["image_sizes"],
        "imagemasks_S17": [{"object": r["image"], "w_h": r["xywh_dots"][2:], "hex_bytes": tv.data_len(r)}
                           for r in masks],
        "imagemasks_S16": [{"object": r["image"], "w_h": r["xywh_dots"][2:], "hex_bytes": tv.data_len(r)}
                           for r in m16],
        "lookups_new_vs_S16_and_S15": {k: lk17[k] for k in new(lk17, lk16, lk15)},
        "lookups_in_S17": dict(lk17),
        "hival_values": {"S17": sorted({r["hival"] for r in records if "hival" in r}),
                         "S16": sorted({r["hival"] for r in s16_man["ps_structure"]["images"]
                                        if "hival" in r})},
        "rgb_values_new_vs_S16_and_S15": [list(v) for v in sorted(
            s14.lookups(job) - s14.lookups(s16_job) - s14.lookups(s15_job))],
        "alphabets_new_vs_S16_and_S15": {k: v for k, v in alpha17.items() if tuple(v) not in old_alpha},
        "object_counts": {"S17": len(records), "S16": len(s16_man["ps_structure"]["images"]),
                          "S15": len(s15_man["ps_structure"]["images"])},
        "summary": [
            "No new HP call, operand, guard, colour space, filter or operator: the image blocks are S16's "
            "(hival 3, the cmy4 lookup = S16 T11's byte for byte, ProcBlack, Smooth / Detail) and the "
            "imagemask block is S16's put_bitmap block (check 3).",
            "New image size: " + ", ".join(new(c17["image_sizes"], c16["image_sizes"], c15["image_sizes"]))
            + " (S16's bands were 4392x432).",
            "The imagemask as a WHOLE DATA BAND: U14-mask " + ", ".join(
                f"{r['xywh_dots'][2]}x{r['xywh_dots'][3]}" for r in masks) + " with no image beneath (S16: "
            "T9-mask 4392x432 over a 4-colour image, bar A 600x24 solid) -- random 2x2 K cells at 50 %, "
            "the mask bits now carry data; " + str(len(masks)) + " mask, no K anywhere else.",
            "New content patterns: c3 oriented-band overlap cells (5:4 with one isolated B dot), CMY stripes "
            "in '+' orientation and phases 1, 2, layouts varying cell to cell (U3-U7), c2 column / row "
            "pairs, c2 dot-mixed at page scale (S12 A21 was a patch), a page of " + ", ".join(
                f"{n} c{cd} {kind}" for (cd, kind), n in sorted(Counter(
                    (b["cell_dots"], "image bands" if b["method"] else "K-mask band")
                    for b in data_bands(man)).items())) + ", no toner overlap at any dot, K only in U14 at "
            "50 % of its cells (S16 T9: 20 %).",
            "New alphabets: " + ", ".join(f"{k} {v}" for k, v in sorted(
                {k: v for k, v in alpha17.items() if tuple(v) not in old_alpha}.items())) + ".",
            f"Objects: {len(records)} (S16 {len(s16_man['ps_structure']['images'])}): 3 fiducial images, "
            f"{sum(r['kind'] == 'band' for r in records)} band images, {len(masks)} band mask; no bars."]}


# ------------------------------------------------------------------------------------------------ (10)

class MemScan:
    """measure.e041_probe_readout.Scan's interface over an in-memory RGB array (no TIFF): S15's _MemScan
    plus the `dpi` / `px_per_mm` attributes the Scan class carries since the --scan-dpi extension; called
    with whatever the instrument passes (path, dpi)."""

    def __init__(self, arr: np.ndarray, dpi: float) -> None:
        from measure.e041_probe_readout import Scan
        self._scan = Scan.__new__(Scan)
        self._scan.img = arr
        self._scan.scale255 = 1.0
        self._scan.h, self._scan.w = arr.shape[:2]
        self._scan.dpi = float(dpi)
        self._scan.px_per_mm = float(dpi) / 25.4

    def __call__(self, *args: Any, **kwargs: Any) -> object:
        return self._scan


def window_audit(man: dict, rows: list[dict]) -> dict:
    """Which manifest windows the readout read, and its state errors per band (loo split by singleton
    states: a state with ONE cell in a window has no leave-one-out mean)."""
    read = {r["id"] for r in rows}
    skipped = sorted({w["id"] for w in man["windows"]} - read)
    errs = {b["name"]: {"windows_read": 0, "cells": 0, "loo": 0, "loo_non_singleton": 0, "singleton_cells": 0,
                        "cross": 0, "band": 0} for b in data_bands(man)}
    for r in rows:
        eb = errs[r["band"]]
        c = np.asarray(r["state_loo"]["confusion"])
        n = c.sum(1)
        off = n - np.diag(c)
        eb["windows_read"] += 1
        eb["cells"] += int(c.sum())
        eb["loo"] += int(off.sum())
        eb["loo_non_singleton"] += int(off[n > 1].sum())
        eb["singleton_cells"] += int((n == 1).sum())
        for k in ("cross", "band"):
            if r.get(f"state_{k}"):
                cc = np.asarray(r[f"state_{k}"]["confusion"])
                eb[k] += int(cc.sum() - np.trace(cc))
    return {"skipped": skipped, "per_band_state_errors": errs,
            "total": {k: sum(v[k] for v in errs.values())
                      for k in ("loo", "loo_non_singleton", "cross", "band")}}


def readout_dry_run(man_path: Path) -> dict:
    """Both instruments, as they stand, on the clean synthetic (no TIFF written; outputs in a temp dir)."""
    import measure.e041_band_screen as bs
    import measure.e041_scale_readout as ro
    import measure.e041_scale_synth as synth
    from measure.e041_mixture_synth import TONER_RGB
    man = json.loads(man_path.read_text())
    with np.load(man_path.with_name(man["bands_npz"]["file"])) as npz:
        if hasattr(synth, "page_raster"):              # S16's painter: 600 dpi raster, repeated 4 x 4
            painter = "e041_scale_synth.page_raster + np.repeat 4x4"
            page = synth.page_raster(man, npz, dict(TONER_RGB))
            img = np.repeat(np.repeat(page, 4, axis=0), 4, axis=1)
            del page
        else:                                          # its successor: the strip painter, identity pose
            painter = "e041_scale_synth.page_planes + paint_scan (2400 dpi, identity pose, no pad/blur/noise)"
            base, planes = synth.page_planes(man, npz)
            img = synth.paint_scan(base, planes, dict(TONER_RGB), {}, scan_dpi=2400.0, rot180=False,
                                   shift_mm=(0.0, 0.0), scale=1.0, rot_deg=0.0, pad_mm=0.0, blur_px=0.0,
                                   noise_sd=0.0, white=255.0, seed=0)
            del base, planes
    mem = MemScan(img, 2400.0)
    out: dict = {"painter": painter, "image_px_hw": list(img.shape[:2]), "toner_rgb": dict(TONER_RGB),
                 "instrument_sha256": {p: sha(Path(m.__file__).read_bytes()) for p, m in
                                       (("e041_scale_readout.py", ro), ("e041_band_screen.py", bs),
                                        ("e041_scale_synth.py", synth))}}
    del img
    saved = ro.Scan, bs.Scan, sys.argv
    try:
        ro.Scan = mem  # type: ignore[assignment,misc]
        bs.Scan = mem  # type: ignore[assignment,misc]
        with tempfile.TemporaryDirectory() as td:
            dpi_arg = {m: (["--scan-dpi", "2400"] if "--scan-dpi" in Path(m.__file__).read_text() else [])
                       for m in (ro, bs)}
            out["scan_dpi_flag_passed"] = {m.__name__: bool(v) for m, v in dpi_arg.items()}
            sys.argv = ["e041_scale_readout", "--scan", "in-memory", "--manifest", str(man_path), "--out", td,
                        *dpi_arg[ro]]
            buf, t0 = io.StringIO(), time.monotonic()
            try:
                with contextlib.redirect_stdout(buf):
                    ro.main()
                summ = json.loads((Path(td) / f"{s17.TAG}-summary.json").read_text())
                out["window_audit"] = window_audit(man, summ["windows"])
                out["scale_readout"] = {
                    "ran": True, "seconds": round(time.monotonic() - t0, 1),
                    "windows_read": summ["n_windows_read"], "windows_in_manifest": len(man["windows"]),
                    "reg_nominal": summ["n_reg_nominal"], "reg_edge": summ["n_reg_edge"],
                    "fit_residual_mm": summ["fit"].get("residual_mm"),
                    "bands": {s["name"]: {
                        "family": s["family"], "windows": s["windows"],
                        "state_err_loo_mean": s["state_err_loo"]["mean"],
                        "state_err_cross_mean": s["state_err_cross"]["mean"],
                        "state_err_band_mean": s["state_err_band"]["mean"],
                        "plane_hard_err_best": {p: s["plane"][p]["hard_err_best"] for p in s14.PLANES_ORDER
                                                if p in s["plane"]}} for s in summ["bands"]},
                    "log_head": buf.getvalue().splitlines()[:3]}
            except BaseException as exc:                     # report, never hide: the CLI as it stands
                out["scale_readout"] = {"ran": False, "error": f"{type(exc).__name__}: {exc}",
                                        "traceback_tail": traceback.format_exc().splitlines()[-8:],
                                        "log_tail": buf.getvalue().splitlines()[-5:]}
            sys.argv = ["e041_band_screen", "--scan", "in-memory", "--manifest", str(man_path), "--out", td,
                        *dpi_arg[bs]]
            buf, t0 = io.StringIO(), time.monotonic()
            try:
                with contextlib.redirect_stdout(buf):
                    bs.main()
                with open(Path(td) / f"{s17.TAG}-columns.csv", newline="") as fh:
                    cols = list(csv.DictReader(fh))
                names = [b["name"] for b in data_bands(man)]
                per = {nm: [r for r in cols if r["band"] == nm] for nm in names}
                out["band_screen"] = {"ran": True, "seconds": round(time.monotonic() - t0, 1),
                                      "columns": len(cols),
                                      "per_band_columns": {nm: len(v) for nm, v in per.items()},
                                      "log_tail": buf.getvalue().splitlines()[-3:]}
            except BaseException as exc:
                out["band_screen"] = {"ran": False, "error": f"{type(exc).__name__}: {exc}",
                                      "traceback_tail": traceback.format_exc().splitlines()[-8:]}
    finally:
        ro.Scan, bs.Scan, sys.argv = saved
    sr, bsr = out["scale_readout"], out["band_screen"]
    multi = sorted(b["name"] for b in data_bands(man) if b["layout_draw"])
    if "window_audit" in out:
        loo_bands = sorted(k for k, v in out["window_audit"]["per_band_state_errors"].items() if v["loo"])
        out["loo_error_bands"] = loo_bands
        out["loo_errors_only_in_multi_layout_bands"] = set(loo_bands) <= set(multi)
    out["notes"] = [
        "The instruments are STATE readers: a state with several layouts (U3-U7) is one class with a "
        "multi-modal colour, so a nearest-mean classifier can mislabel a layout whose centre-box colour sits "
        "near another state's mean. Analytic centre box (half the cell, 4 px per dot, the synth toner "
        "colours): U3's CMY '+' 0 cell is 37.5 from the mixed CMY mean and 43.9 from CY's (X) mean; in U4 "
        "CY is an oriented band, 54.1 away. Window-local loo means are noisy enough to cross that margin; "
        "the cross and band means are not. Layout-aware decoding is the instruments' extension, not done "
        "here.",
        "e041_scale_readout.py / e041_band_screen.py as they stand read the S17 manifest without a change: "
        "the new fields (layout_catalogue, n_layouts, layout_draw, layouts_<band>) are ignored, no bars, no "
        "strip; U14's band (no image, method / neutral None) reads as family wk-mask on K."]
    out["pass"] = bool(sr.get("ran") and bsr.get("ran") and out.get("loo_errors_only_in_multi_layout_bands")
                       and sr["windows_read"] + len(out["window_audit"]["skipped"])
                       == sr["windows_in_manifest"]
                       and out["window_audit"]["total"]["cross"] == 0
                       and out["window_audit"]["total"]["band"] == 0
                       and all(v > 0 for v in bsr["per_band_columns"].values()))
    return out


# ------------------------------------------------------------------------------------------------ driver

def verify(job_path: Path, man_path: Path, npz_path: Path, job: bytes, manifest: dict, nb: bytes,
           objects: list[dict], arrays: dict[str, np.ndarray], records: list[dict],
           build: Callable[[], tuple], paths: dict[str, Path]) -> dict:
    s16_job, s15_job, s14_job = (paths[k].read_bytes() for k in ("s16", "s15", "s14"))
    s16_man = json.loads(paths["s16"].with_name(paths["s16"].stem + ".manifest.json").read_text())
    s15_man = json.loads(paths["s15"].with_name(paths["s15"].stem + ".manifest.json").read_text())
    v: dict = {}
    v["1_render"] = render_checks(job_path, manifest, arrays, objects)
    v["1_data_roundtrip"] = tv.data_roundtrip(job, records, objects)
    v["2_guards"] = guard_checks(job, objects)
    v["3_byte_audit_vs_S16"] = byte_audit(job, records, objects, s16_job, s16_man)
    fast, _, _ = tv.render(job_path, True)
    v["4_windows"] = window_checks(fast, manifest, npz_path, objects)
    del fast
    v["5_geometry"] = geometry_checks(manifest, objects)
    again = build()
    v["6_two_builds_identical"] = {"job": again[0] == job, "manifest": again[1] == manifest,
                                   "npz": again[2] == nb}
    del again
    r16, r15, r14 = sha(s16.build()[0]), sha(s15.build()[0]), sha(s14.build()[0])
    v["7_rebuilt"] = {
        "S16": {"rebuilt_sha256": r16, "on_disk_sha256": sha(s16_job), "expected": s17.S16_SHA256,
                "pass": r16 == sha(s16_job) == s17.S16_SHA256},
        "S15": {"rebuilt_sha256": r15, "on_disk_sha256": sha(s15_job), "expected": s16.S15_SHA256,
                "pass": r15 == sha(s15_job) == s16.S15_SHA256},
        "S14": {"rebuilt_sha256": r14, "on_disk_sha256": sha(s14_job), "expected": s15.S14_SHA256,
                "pass": r14 == sha(s14_job) == s15.S14_SHA256},
        "S12": s14.s12_rebuild(paths["s11"], paths["s12"])}
    v["8_novelty"] = novelty(job, records, manifest, s16_job, s16_man, s15_job, s15_man)
    v["9_sizes"] = tv.sizes(job, records, nb, len(json.dumps(manifest, indent=1)))
    v["10_readout_dry_run"] = readout_dry_run(man_path)
    v["pass"] = all([v["1_render"]["pass"], v["1_data_roundtrip"]["pass"], v["2_guards"]["pass"],
                     v["3_byte_audit_vs_S16"]["pass"], v["4_windows"]["pass"], v["5_geometry"]["pass"],
                     all(v["6_two_builds_identical"].values()),
                     all(v["7_rebuilt"][k]["pass"] for k in ("S16", "S15", "S14", "S12")),
                     v["10_readout_dry_run"]["pass"]])
    return v
