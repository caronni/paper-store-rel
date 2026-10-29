"""e041 S16 — the checks behind `ps_trigger.py --verify` (split along the build / verify seam).

(1) gs 10.08 ppmraw -r600 renders -- default ICC and -dUseFastColor -- against the page composed from the
manifest + npz alone (cell layouts, colours, states) and against the objects painted (lookups, masks);
(2) gs strict silent + a stub run logging every HP call, image and imagemask in sequence; (3) byte audit
against the printed S15 (wrapper, header shape, setpagedevice, prologue, tail, HP call lines per (neutral,
method)) and every imagemask block line for line against src/holo/gen/ps.py PSDoc.put_bitmap's own output;
(4) every window's states / planes against the rendered dots, the T3 / T9 / T13 / T14 specifics; (5) geometry;
(6) two builds identical; (7) S15, S14, S12 rebuilt unchanged; (8) novelty vs the printed S15 and S14 by a
tokenizer diff of the non-data text plus lookups, sizes and content patterns; (9) sizes; (10)
measure/e041_scale_readout.py and measure/e041_band_screen.py, unchanged, on an in-memory clean synthetic
(e041_scale_synth.page_raster, its toner colours, 4x4 px per dot, identity pose).
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
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import numpy as np

import ps_mixture as s12
import ps_reset as s15
import ps_scale as s14
import ps_trigger as s16
from holo.gen.ps import PSDoc
from pcl_planar import sha

PAGE_H_DOTS, PAGE_W_DOTS = s16.PAGE_H_DOTS, s16.PAGE_W_DOTS
IMAGEMASK_STUB = (b"/imagemask { (IMAGEMASK ) print 4 index =only ( ) print 3 index == "
                  b"systemdict /imagemask get exec } def\n")


# ------------------------------------------------------------------------------------------------ helpers

def data_len(r: dict) -> int:
    return int(r.get("data_bytes", r.get("data_bytes_ascii85", 0)))


def skeleton(job: bytes, records: list[dict]) -> bytes:
    """The job with every object's data span (ASCII85 or hex, end marker included) removed."""
    text, pos = [], 0
    for r in sorted(records, key=lambda r: r["data_offset"]):
        text.append(job[pos:r["data_offset"]])
        pos = r["data_offset"] + data_len(r)
    text.append(job[pos:])
    return b"".join(text)


def render(job_path: Path, fast: bool) -> tuple[np.ndarray, str, int]:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "s16.ppm"
        args = ["-q", *(["-dUseFastColor"] if fast else []), "-sDEVICE=ppmraw", "-r600",
                f"-g{PAGE_W_DOTS}x{PAGE_H_DOTS}", f"-sOutputFile={out}"]
        r = s12.gs(args, job_path)
        return s12.read_ppm(out), (r.stdout + r.stderr).strip(), r.returncode


def data_bands(man: dict) -> list[dict]:
    return [b for b in man["bands"] if b["alphabet"] is not None]


def composed(man: dict, arrays: dict[str, np.ndarray]) -> np.ndarray:
    """The page from the manifest + npz alone: fiducials, every band through its cell layouts and the
    colour table (K-mask black), the bars at their rgb."""
    page = np.full((PAGE_H_DOTS, PAGE_W_DOTS, 3), 255, np.uint8)
    for f in man["fiducials"]:
        x, y, w, h = f["xywh_dots"]
        page[y:y + h, x:x + w] = f["rgb"]
    for b in data_bands(man):
        tiles = np.array([[[man["colours"][c]["rgb"] for c in row] for row in b["cell_layouts"][s]]
                          for s in b["states"]], np.uint8)
        st = arrays[f"states_{b['name']}"]
        r, c = st.shape
        cd = b["cell_dots"]
        page[b["y_dots"]:b["y_dots"] + b["h_dots"], b["x_dots"]:b["x_dots"] + b["w_dots"]] = (
            tiles[st].transpose(0, 2, 1, 3, 4).reshape(r * cd, c * cd, 3))
    for bar in man["bars"]:
        x, y, w, h = bar["x_dots"], bar["y_dots"], bar["w_dots"], bar["h_dots"]
        page[y:y + h, x:x + w] = bar["rgb"]
    return page


def painted(objects: list[dict], mask_rgb: tuple[int, int, int] = (0, 0, 0)) -> np.ndarray:
    page = np.full((PAGE_H_DOTS, PAGE_W_DOTS, 3), 255, np.uint8)
    for o in objects:
        x, y, w, h = o["xywh"]
        if o["kind"] == "imagemask":
            page[y:y + h, x:x + w][o["bits"] == 1] = mask_rgb
        else:
            page[y:y + h, x:x + w] = o["palette"][o["raster"]]
    return page


def overlap_dots(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    """Shared area in dots of two (x, y, w, h) rectangles."""
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(w, 0) * max(h, 0)


def block_rect(man: dict) -> tuple[dict, dict, tuple[int, int, int, int]]:
    """T13's band record, its one gaps entry and the block's page rectangle (x, y, w, h)."""
    t13 = next(b for b in man["bands"] if b["name"] == "T13")
    g = t13["gaps"][0]
    return t13, g, (g["x_dots"], t13["y_dots"], g["w_dots"], t13["h_dots"])


def mask_union(objects: list[dict]) -> np.ndarray:
    m = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), bool)
    for o in objects:
        if o["kind"] == "imagemask":
            x, y, w, h = o["xywh"]
            m[y:y + h, x:x + w] |= o["bits"] == 1
    return m


# ------------------------------------------------------------------------------------------------ (1)

def render_checks(job_path: Path, man: dict, arrays: dict[str, np.ndarray], objects: list[dict]) -> dict:
    fast, fmsg, frc = render(job_path, True)
    dflt, dmsg, drc = render(job_path, False)
    page = composed(man, arrays)
    masks = mask_union(objects)
    covered = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), bool)
    fid_black = True
    for f in man["fiducials"]:
        x, y, w, h = f["xywh_dots"]
        fid_black &= bool((fast[y:y + h, x:x + w] == 0).all())
        covered[y:y + h, x:x + w] = True
    for b in man["bands"]:
        covered[b["y_dots"]:b["y_dots"] + b["h_dots"], b["x_dots"]:b["x_dots"] + b["w_dots"]] = True
    block_white = True
    for b in data_bands(man):
        for g in b["gaps"]:
            block_white &= bool((fast[b["y_dots"]:b["y_dots"] + b["h_dots"],
                                      g["x_dots"]:g["x_dots"] + g["w_dots"]] == 255).all())
    diff_dm = (dflt != fast).any(2)
    dvals = Counter(tuple(int(v) for v in px) for px in dflt[masks][:200000])
    t9 = next(b for b in man["bands"] if b["name"] == "T9")
    t9_k = s14.expand(arrays["states_T9"] == t9["states"].index("K"), 3)
    t9_rect = fast[t9["y_dots"]:t9["y_dots"] + t9["h_dots"], t9["x_dots"]:t9["x_dots"] + t9["w_dots"]]
    bar_a = next(b for b in man["bars"] if b["kind"] == "imagemask")
    _, g13, gap = block_rect(man)
    gx, gy, gw, gh = gap
    in_gap = [o["name"] for o in objects if overlap_dots(o["xywh"], gap)]
    gap_white = {k: bool((r[gy:gy + gh, gx:gx + gw] == 255).all())
                 for k, r in (("fast", fast), ("default", dflt))}
    res = {"gs_fastcolor": {"returncode": frc, "messages": fmsg, "render_sha256": sha(fast.tobytes())},
           "gs_default_icc": {"returncode": drc, "messages": dmsg, "render_sha256": sha(dflt.tobytes())},
           "page_hw": list(fast.shape[:2]),
           "differing_dots_fast_vs_composed_from_manifest_npz": int((fast != page).any(2).sum()),
           "differing_dots_fast_vs_painted_objects": int((fast != painted(objects)).any(2).sum()),
           "default_vs_fast_differing_dots": int(diff_dm.sum()),
           "default_vs_fast_differ_exactly_on_mask_bits": bool(np.array_equal(diff_dm, masks)),
           "mask_bits_total": int(masks.sum()),
           "default_icc_values_on_mask_bits": {str(k): v for k, v in dvals.items()},
           "differing_dots_default_vs_painted_with_that_value": int(
               (dflt != painted(objects, next(iter(dvals)) if len(dvals) == 1 else (0, 0, 0))).any(2).sum()),
           "fiducials_solid_black": fid_black,
           "T9_K_cells_black_exactly": bool(np.array_equal((t9_rect == 0).all(2), t9_k)),
           "T9_K_cell_dots": int(t9_k.sum()),
           "bar_A_black": bool((fast[bar_a["y_dots"]:bar_a["y_dots"] + bar_a["h_dots"],
                                     bar_a["x_dots"]:bar_a["x_dots"] + bar_a["w_dots"]] == 0).all()),
           "non_white_outside_objects": int(((fast != 255).any(2) & ~covered).sum()),
           "T13_white_block_all_white": block_white,
           "T13_gap_rect_xywh_dots": list(gap), "T13_gap_mm": [g13["x_mm"], g13["x_end_mm"], g13["w_mm"]],
           "T13_objects_intersecting_gap": in_gap, "T13_gap_white_in_both_renders": gap_white,
           "inked_dots": int((fast != 255).any(2).sum())}
    res["pass"] = (frc == 0 and drc == 0 and not fmsg and not dmsg
                   and res["differing_dots_fast_vs_composed_from_manifest_npz"] == 0
                   and res["differing_dots_fast_vs_painted_objects"] == 0
                   and res["default_vs_fast_differ_exactly_on_mask_bits"] and len(dvals) == 1
                   and res["differing_dots_default_vs_painted_with_that_value"] == 0
                   and fid_black and res["T9_K_cells_black_exactly"] and res["bar_A_black"]
                   and res["non_white_outside_objects"] == 0 and block_white and not in_gap
                   and all(gap_white.values()))
    return res


def data_roundtrip(job: bytes, records: list[dict], objects: list[dict]) -> dict:
    import base64
    ok = 0
    for r, o in zip(records, objects):
        d = job[r["data_offset"]:r["data_offset"] + data_len(r)]
        if o["kind"] == "imagemask":
            ok += bytes.fromhex(d[:-2].decode().replace("\n", "")) == s16.pack_bits_rows(o["bits"])
        else:
            ok += base64.a85decode(d[:-3], adobe=False, ignorechars=b" \n") == o["raster"].tobytes()
    return {"objects": len(objects), "data_decodes_to_raster_or_bits": ok, "pass": ok == len(objects)}


# ------------------------------------------------------------------------------------------------ (2)

def hp_expect(o: dict) -> list[str]:
    if o["kind"] == "imagemask":
        return [f"IMAGEMASK {o['xywh'][2]} {o['xywh'][3]}"]
    return [f"HPCALL {op} {a if a == 'false' else '(' + a + ')'}" for op, a in s14.calls_of(o)] + [
        f"IMAGE {o['xywh'][2]} {o['xywh'][3]}"]


def guard_checks(job: bytes, objects: list[dict]) -> dict:
    with tempfile.TemporaryDirectory() as td:
        plain = Path(td) / "s16.ps"
        plain.write_bytes(job)
        strict = s12.gs(["-q", "-sDEVICE=nullpage"], plain)
        stubbed = Path(td) / "s16-stubs.ps"
        cut = job.index(b"%%EndComments\n") + len(b"%%EndComments\n")
        stubbed.write_bytes(job[:cut] + s12.stub_prologue() + IMAGEMASK_STUB + job[cut:])
        run = s12.gs(["-q", "-sDEVICE=nullpage"], stubbed)
    log = [ln for ln in run.stderr.splitlines() if ln.startswith(("HPCALL", "IMAGE", "SHOWPAGE"))]
    want = [ln for o in objects for ln in hp_expect(o)] + ["SHOWPAGE"]
    per_kind: dict[str, list[list[str]]] = {}
    for o in objects:
        key = f"{o['kind']}/{o['neutral']}/{o['method']}"
        seq = hp_expect(o)[:-1]
        if seq not in per_kind.setdefault(key, []):
            per_kind[key].append(seq)
    strict_text = (strict.stdout + strict.stderr).strip()
    per_obj: dict[str, list[str]] = {}
    at = 0
    for o in objects:                                   # the stub log cut per object, in draw order
        n = len(hp_expect(o))
        per_obj[o["name"]] = log[at:at + n]
        at += n
    toner = ["HPCALL HPImageNeutralAxis (TonerBlack)", "HPCALL ColorSmartImageHalftone (Smooth)",
             "HPCALL HPColorTrapping (Off)", "HPCALL HPImageAdaptiveHalftoning false"]
    shown = ("T8", "T9", "T9-mask", "T11", "T14")
    res = {"strict_returncode": strict.returncode, "strict_messages": strict_text,
           "stub_returncode": run.returncode, "stub_log_lines": len(log), "expected_lines": len(want),
           "stub_sequence_exact": log == want,
           "stub_calls": dict(Counter(ln.split()[1] for ln in log if ln.startswith("HPCALL"))),
           "stub_images": sum(ln.startswith("IMAGE ") for ln in log),
           "stub_imagemasks": sum(ln.startswith("IMAGEMASK ") for ln in log),
           "stub_other_output": "\n".join(ln for ln in run.stderr.splitlines() if ln not in set(log)).strip(),
           "hp_sequences_by_kind_neutral_method": per_kind,
           "stub_log_per_object": {k: per_obj[k] for k in shown},
           "T9_four_hp_calls_TonerBlack": per_obj["T9"][:4] == toner,
           "T14_four_hp_calls_TonerBlack": per_obj["T14"][:4] == toner,
           "neutral_per_image": {o["name"]: o["neutral"] for o in objects if o["kind"] != "imagemask"}}
    if log != want:
        res["first_mismatch"] = next(([k, a, b] for k, (a, b) in enumerate(zip(log, want)) if a != b),
                                     [min(len(log), len(want)), None, None])
    res["pass"] = (strict.returncode == 0 and not strict_text and run.returncode == 0 and log == want
                   and not res["stub_other_output"] and res["T9_four_hp_calls_TonerBlack"]
                   and res["T14_four_hp_calls_TonerBlack"])
    return res


# ------------------------------------------------------------------------------------------------ (3)

def hp_lines(ops: list[str]) -> list[str]:
    return [ln for ln in ops if " where " in ln]


def holo_block(bits: np.ndarray, x: int, y: int) -> list[str]:
    """PSDoc.put_bitmap's own lines for this bitmap (src/holo/gen/ps.py), from its rendered page."""
    doc = PSDoc((PAGE_W_DOTS, PAGE_H_DOTS), "00000000", title="s16-audit")
    doc.begin_page()
    doc.put_bitmap(bits, x, y)
    doc.end_page()
    lines = doc.render().split("\n")
    return lines[lines.index("%%Page: 1 1") + 1:lines.index("showpage")]


def template(ln: str) -> str:
    return re.sub(r"\d+(\.\d+)?", "N", ln) if not re.fullmatch(r"[0-9a-f]+", ln) else "<hex>"


def byte_audit(job: bytes, records: list[dict], objects: list[dict], s15_job: bytes, s15_man: dict) -> dict:
    i15, i16 = s15_job.index(b"%!PS"), job.index(b"%!PS")
    e15, e16 = s15_job.index(b"%%EndComments\n"), job.index(b"%%EndComments\n")
    k15, k16 = s15_job.index(b"%%Page: 1 1\n"), job.index(b"%%Page: 1 1\n")
    h15 = [ln for ln in s15_job[i15:e15].split(b"\n") if not ln.startswith((b"%%Title", b"%%Creator"))]
    h16 = [ln for ln in job[i16:e16].split(b"\n") if not ln.startswith((b"%%Title", b"%%Creator"))]
    lines = skeleton(job, records).split(b"\n")
    s15_seq: dict[tuple[str, str], set[tuple[str, ...]]] = {}
    for r in s15_man["ps_structure"]["images"]:
        s15_seq.setdefault((r["neutral"], r["method"]), set()).add(tuple(hp_lines(r["operators"])))
    imgs = [r for r in records if r["kind"] != "imagemask"]
    masks = [(r, o) for r, o in zip(records, objects) if r["kind"] == "imagemask"]
    hp_match = [s15_seq.get((r["neutral"], r["method"])) == {tuple(hp_lines(r["operators"]))} for r in imgs]
    mask_rows = []
    for r, o in masks:
        start = r["data_offset"] - len(("\n".join(r["operators"]) + "\n").encode())
        end = r["data_offset"] + data_len(r) + len(b"grestore\n")
        ours = job[start:end].decode().split("\n")[:-1]
        x, y, w, h = r["xywh_dots"]
        ref = holo_block(o["bits"], x, y)
        head = job[:start].rsplit(b"\n", 2)[-2].decode()
        mask_rows.append({"object": r["image"], "lines": len(ours), "equal_to_put_bitmap_lines": ours == ref,
                          "template_equal": [template(a) for a in ours] == [template(a) for a in ref],
                          "operator_lines": [a for a in ours if not re.fullmatch(r"[0-9a-f]+", a)],
                          "comment_head": head, "hp_or_colorsmart_in_block": any(
                              "HP" in a or "ColorSmart" in a for a in ours)})
    end = b"grestore\n"
    res = {"wrapper_head_equals_S15_name_aside": job[:i16] == s15_job[:i15].replace(
               f'JOB NAME="{s15.JOB_NAME}"'.encode(), f'JOB NAME="{s16.JOB_NAME}"'.encode()),
           "header_shape_equals_S15_title_creator_aside": h15 == h16,
           "setpagedevice_equals_S15": (job[e16 + 14:].split(b"\n", 1)[0] + b"\n" == s12.SETPAGEDEVICE
                                        and s15_job.count(s12.SETPAGEDEVICE) == 1
                                        and job.count(s12.SETPAGEDEVICE) == 1),
           "prologue_equals_S15": s15_job[e15 + 14:k15] == job[e16 + 14:k16] == s12.SETPAGEDEVICE
           + s12.prologue(),
           "tail_equals_S15": job.endswith(s16.TAIL) and s15_job[s15_job.rindex(end) + len(end):]
           == job[job.rindex(end) + len(end):],
           "hp_call_lines_equal_S15_per_neutral_and_method": all(hp_match),
           "imagemask_blocks_equal_holo_put_bitmap": all(m["equal_to_put_bitmap_lines"] for m in mask_rows)
           and len(mask_rows) == 2,
           "S15_hp_sequences_by_neutral_method": {f"{n}/{m}": [list(q) for q in sorted(v)]
                                                  for (n, m), v in sorted(s15_seq.items())},
           "imagemask_blocks": mask_rows,
           "ColorSmartColorMatching_occurrences": job.count(b"ColorSmartColorMatching"),
           "showpage_lines": lines.count(b"showpage"), "image_operators": lines.count(b">> image"),
           "imagemask_operators": sum(ln.endswith(b" imagemask") for ln in lines),
           "gsave": lines.count(b"gsave"), "grestore": lines.count(b"grestore"),
           "non_ascii_bytes_after_wrapper": sum(1 for c in job[len(s16.WRAPPER_HEAD):-len(s12.WRAPPER_TAIL)]
                                                if c > 126 or (c < 32 and c != 10)),
           "data_lines_starting_with_percent": sum(
               ln.startswith(b"%") for r in records
               for ln in job[r["data_offset"]:r["data_offset"] + data_len(r)].split(b"\n")),
           "skeleton_bytes": len(b"\n".join(lines))}
    res["pass"] = (all(res[k] for k in list(res)[:7]) and res["ColorSmartColorMatching_occurrences"] == 0
                   and not any(m["hp_or_colorsmart_in_block"] for m in mask_rows)
                   and all(len(v) == 1 for v in s15_seq.values()) and res["showpage_lines"] == 1
                   and res["image_operators"] == len(imgs) and res["imagemask_operators"] == len(masks)
                   and res["gsave"] == res["grestore"] == len(records)
                   and res["non_ascii_bytes_after_wrapper"] == 0
                   and res["data_lines_starting_with_percent"] == 0)
    return res


# ------------------------------------------------------------------------------------------------ (4)

def window_checks(img: np.ndarray, man: dict, npz_path: Path, objects: list[dict], s15_man: dict) -> dict:
    """Every window: states / planes sliced from the npz against the render's dots decoded through the band's
    colours (fast render); then T3 / T9 / T13 / lookup specifics."""
    bands = {b["name"]: b for b in data_bands(man)}
    colours = man["colours"]
    with np.load(npz_path) as npz:
        arrays = {k: npz[k] for k in npz.files}
    per_band, bad, ok, unique_rgb = Counter(), [], 0, True
    dec: dict[str, tuple[list[str], np.ndarray, np.ndarray, np.ndarray]] = {}
    for name, b in bands.items():
        used = [c for c in colours if any(c in row for g in b["cell_layouts"].values() for row in g)]
        rgb = np.array([colours[c]["rgb"] for c in used], np.uint8)
        unique_rgb &= len({tuple(v) for v in rgb}) == len(used)
        tiles = np.array([[[used.index(c) for c in row] for row in b["cell_layouts"][s]]
                          for s in b["states"]], np.uint8)
        ink = np.array([[int(p in colours[c]["planes"]) for p in man["planes_order"]] for c in used],
                       np.uint8)
        dec[name] = (used, rgb, tiles, ink)
    for w in man["windows"]:
        b = bands[w["band"]]
        used, rgb, tiles, ink = dec[w["band"]]
        cd, wc = w["cell_dots"], w["cells"]
        cy, cx = w["cell_yx"]
        st = arrays[f"states_{b['name']}"][cy:cy + wc, cx:cx + wc]
        dy, dx = w["y_dots"] - b["y_dots"], w["x_dots"] - b["x_dots"]
        pl = arrays[f"planes_{b['name']}"][:, dy:dy + w["h_dots"], dx:dx + w["w_dots"]]
        win = img[w["y_dots"]:w["y_dots"] + w["h_dots"], w["x_dots"]:w["x_dots"] + w["w_dots"]]
        match = (win[:, :, None, :] == rgb[None, None]).all(3)
        decoded = match.argmax(2)
        want = tiles[st].transpose(0, 2, 1, 3).reshape(wc * cd, wc * cd)
        good = (bool((match.sum(2) == 1).all()) and np.array_equal(decoded, want)
                and np.array_equal(pl, np.moveaxis(ink[decoded], 2, 0)) and st.shape == (wc, wc))
        ok += good
        per_band[w["band"]] += 1
        if not good:
            bad.append(w["id"])
    by_obj = {o["name"]: o for o in objects}
    t3 = by_obj["T3"]
    t9b, t9, t9m = bands["T9"], by_obj["T9"], by_obj["T9-mask"]
    k9 = arrays["states_T9"] == t9b["states"].index("K")
    t13, g, gap = block_rect(man)
    st13 = arrays["states_T13"]
    halves = sorted((o for o in objects if o["band"] == "T13"), key=lambda o: o["xywh"][0])
    lk13 = [c["colour"] for c in t13["lookup"]]
    to_lut = np.array([[[lk13.index(c) for c in row] for row in t13["cell_layouts"][s]]
                       for s in t13["states"]], np.uint8)
    want13 = to_lut[st13].transpose(0, 2, 1, 3).reshape(t13["h_dots"], t13["w_dots"])
    c0, c1 = g["cell_col_start"], g["cell_col_start"] + g["cell_cols"]
    cd13 = t13["cell_dots"]
    edges = [(o["xywh"][0], o["xywh"][0] + o["xywh"][2]) for o in halves]
    abut = (len(halves) == 2
            and edges == [(t13["x_dots"], gap[0]), (gap[0] + gap[2], t13["x_dots"] + t13["w_dots"])]
            and gap[0] == t13["x_dots"] + c0 * cd13 and gap[2] == (c1 - c0) * cd13
            and all(o["xywh"][1] == t13["y_dots"] and o["xywh"][3] == t13["h_dots"] for o in halves)
            and np.array_equal(halves[0]["raster"], want13[:, :c0 * cd13])
            and np.array_equal(halves[1]["raster"], want13[:, c1 * cd13:])
            and [i["image"] for i in t13["images"]] == [o["name"] for o in halves])
    spec: dict[str, Any] = {
        "T3_hival": len(t3["palette"]) - 1, "T3_index4_in_raster": int((t3["raster"] == 4).sum()),
        "T9_image_index_on_K_cells_all_0": bool((t9["raster"][s14.expand(k9, 3)] == 0).all()),
        "T9_mask_bits_equal_K_cells": bool(np.array_equal(t9m["bits"] == 1, s14.expand(k9, 3))),
        "T9_mask_rect_equals_band_rect": list(t9m["xywh"]) == [t9b["x_dots"], t9b["y_dots"], t9b["w_dots"],
                                                               t9b["h_dots"]],
        "T13_block_cells_W": bool((st13[:, c0:c1] == t13["states"].index("W")).all()),
        "T13_images": [{"object": o["name"], "xywh_dots": list(o["xywh"]),
                        "cell_cols": [(o["xywh"][0] - t13["x_dots"]) // cd13,
                                      (o["xywh"][0] + o["xywh"][2] - t13["x_dots"]) // cd13 - 1]}
                       for o in halves],
        "T13_images_abut_their_states_exactly": bool(abut),
        "T13_white_block_object_free_recorded": bool(g.get("object_free")) and t13["white_block_object_free"],
        "T13_white_block_mm": t13["white_block_mm"],
        "T13_block": {k: g[k] for k in ("cell_col_start", "cell_cols", "x_dots", "w_dots", "x_mm")}
        | {"x_end_mm": round((g["x_dots"] + g["w_dots"]) * 25.4 / 600, 3),
           "last_left_edge_mm": round((g["x_dots"] + g["w_dots"] - 3) * 25.4 / 600, 3)},
        "T13_block_white_in_render": bool((img[t13["y_dots"]:t13["y_dots"] + t13["h_dots"],
                                               g["x_dots"]:g["x_dots"] + g["w_dots"]] == 255).all()),
        "fifth_state_fraction": {n: round(float((arrays[f"states_{n}"] == 4).mean()), 5)
                                 for n in ("T3", "T4", "T5", "T6", "T7", "T8", "T9", "T14")},
        "extra_fraction_declared": {n: bands[n]["extra_fraction"] for n in ("T4", "T5", "T6", "T7", "T9")},
        "neutral": {n: by_obj[n]["neutral"] for n in ("T6", "T7", "T8", "T9", "T11", "T14")},
        "state_counts": {n: np.bincount(arrays[f"states_{n}"].ravel(), minlength=len(b["states"])).tolist()
                         for n, b in bands.items()}}
    lut = {o["name"]: o["palette"].tobytes() for o in objects if o["kind"] != "imagemask"}
    s15_lut = {r["image"]: re.search(r"<([0-9a-f]+)>", r["operators"][1]).group(1)
               for r in s15_man["ps_structure"]["images"]}
    spec["lookups_equal_T11"] = {n: lut[n] == lut["T11"] for n in ("T2", "T9", "T10", "T12", "T14")}
    spec["T11_lookup_equals_S15_R8"] = lut["T11"].hex() == s15_lut["R8"]
    spec["T1_T13_lookup_equal_S15_R1"] = (lut["T1"].hex() == lut["T13-left"].hex() == lut["T13-right"].hex()
                                          == s15_lut["R1"])
    t14_rgb = {tuple(int(c) for c in v) for v in by_obj["T14"]["palette"]}
    spec["T14_TonerBlack_T11_lookup_no_K"] = (by_obj["T14"]["neutral"] == "toner" and lut["T14"] == lut["T11"]
                                              and (0, 0, 0) not in t14_rgb
                                              and bands["T14"]["states"] == bands["T11"]["states"])
    spec["T9_TonerBlack_no_K_in_lookup"] = (by_obj["T9"]["neutral"] == "toner" and (0, 0, 0) not in {
        tuple(int(c) for c in v) for v in by_obj["T9"]["palette"]})
    spec["T3_T4_T5_lookup_identical"] = lut["T3"] == lut["T4"] == lut["T5"]
    res = {"windows": len(man["windows"]), "equal": ok, "per_band": dict(per_band), "first_bad": bad[:5],
           "band_colour_rgb_unique": unique_rgb, **spec}
    res["pass"] = (ok == len(man["windows"]) and unique_rgb and spec["T3_hival"] == 4
                   and spec["T3_index4_in_raster"] == 0 and spec["T9_image_index_on_K_cells_all_0"]
                   and spec["T9_mask_bits_equal_K_cells"] and spec["T9_mask_rect_equals_band_rect"]
                   and spec["T13_block_cells_W"] and spec["T13_block_white_in_render"]
                   and spec["T13_images_abut_their_states_exactly"]
                   and spec["T13_white_block_object_free_recorded"]
                   and spec["T14_TonerBlack_T11_lookup_no_K"] and spec["T9_TonerBlack_no_K_in_lookup"]
                   and spec["fifth_state_fraction"]["T14"] == 0
                   and all(spec["lookups_equal_T11"].values()) and spec["T11_lookup_equals_S15_R8"]
                   and spec["T1_T13_lookup_equal_S15_R1"] and spec["T3_T4_T5_lookup_identical"])
    return res


# ------------------------------------------------------------------------------------------------ (5)

def geometry_checks(man: dict, objects: list[dict]) -> dict:
    def inside(x: int, y: int, w: int, h: int) -> bool:
        return x >= 0 and y >= 0 and x + w <= PAGE_W_DOTS and y + h <= PAGE_H_DOTS

    fr = [tuple(f["xywh_dots"]) for f in man["fiducials"]]
    br = [(b["x_dots"], b["y_dots"], b["w_dots"], b["h_dots"]) for b in man["bands"]]
    count = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), np.uint8)
    for x, y, w, h in fr + br:
        count[y:y + h, x:x + w] += 1
    img_count = np.zeros_like(count)
    overlays = 0
    for o in objects:
        x, y, w, h = o["xywh"]
        if o["kind"] == "imagemask" and o["band"] != "strip":
            overlays += 1
            continue                                 # T9's declared overlay: the band rectangle by design
        img_count[y:y + h, x:x + w] += 1
    strip = next(b for b in man["bands"] if b["name"] == "strip")
    bars_in = all(strip["x_dots"] <= r["x_dots"] and r["x_dots"] + r["w_dots"] <= strip["x_dots"]
                  + strip["w_dots"] and r["y_dots"] == strip["y_dots"] and r["h_dots"] == strip["h_dots"]
                  for r in man["bars"])
    bx = sorted((r["x_dots"], r["w_dots"]) for r in man["bars"])
    bar_gaps = [b2[0] - b1[0] - b1[1] for b1, b2 in zip(bx, bx[1:])]
    bands = {b["name"]: b for b in man["bands"]}
    win_ok = all(bands[w["band"]]["x_dots"] <= w["x_dots"] and w["x_dots"] + w["w_dots"]
                 <= bands[w["band"]]["x_dots"] + bands[w["band"]]["w_dots"]
                 and bands[w["band"]]["y_dots"] <= w["y_dots"] and w["y_dots"] + w["h_dots"]
                 <= bands[w["band"]]["y_dots"] + bands[w["band"]]["h_dots"] for w in man["windows"])
    page = sorted(man["bands"], key=lambda b: b["y_dots"])
    gaps = [page[k + 1]["y_dots"] - page[k]["y_dots"] - page[k]["h_dots"] for k in range(len(page) - 1)]
    by_band = {b["name"]: [w for w in man["windows"] if w["band"] == b["name"]] for b in data_bands(man)}
    res = {"all_inside_page": all(inside(*r) for r in fr + br) and all(inside(*o["xywh"]) for o in objects),
           "fiducials_bands_overlap_dots": int((count > 1).sum()),
           "object_overlap_dots_declared_overlay_aside": int((img_count > 1).sum()),
           "declared_overlays": overlays, "bars_inside_strip": bars_in, "bar_gaps_dots": bar_gaps,
           "windows_inside_their_band": win_ok, "band_gaps_dots": sorted(set(gaps)),
           "fiducial_clearance_dots": min(s15.separation(f, b) for f in fr for b in br),
           "first_band_y_dots": page[0]["y_dots"], "last_end_dots": page[-1]["y_dots"] + page[-1]["h_dots"],
           "band_h_dots": {b["name"]: b["h_dots"] for b in man["bands"]},
           "heights_multiple_of_6": all(b["h_dots"] % 6 == 0 for b in man["bands"]),
           "band_y_dots": {b["name"]: b["y_dots"] for b in page},
           "data_bands": len(data_bands(man)),
           "cells_hw": {b["name"]: b["cells_hw"] for b in data_bands(man)},
           "windows": len(man["windows"]),
           "windows_per_band": dict(Counter(w["band"] for w in man["windows"])),
           "window_grid_per_band": {nm: [len({w["y_dots"] for w in ws}), len({w["x_dots"] for w in ws})]
                                    for nm, ws in by_band.items()}}
    n = len(s16.BANDS)
    layout_ok = (res["data_bands"] == n == 14 and res["first_band_y_dots"] == s16.FIRST_Y_DOTS
                 and all(b["h_dots"] == s16.BAND_H_DOTS == 432 for b in data_bands(man))
                 and strip["h_dots"] == s16.STRIP_H_DOTS
                 and res["last_end_dots"] == s16.FIRST_Y_DOTS + n * s16.BAND_H_DOTS + s16.STRIP_H_DOTS
                 + n * s16.GAP_DOTS
                 and all(v == [4, 47] for v in res["window_grid_per_band"].values()))
    res["layout_14x432_plus_strip"] = layout_ok
    res["pass"] = (res["all_inside_page"] and res["fiducials_bands_overlap_dots"] == 0
                   and res["object_overlap_dots_declared_overlay_aside"] == 0 and overlays == 1 and bars_in
                   and all(g > 0 for g in bar_gaps) and win_ok and all(g == s16.GAP_DOTS for g in gaps)
                   and res["last_end_dots"] <= s16.LAST_END_DOTS and res["heights_multiple_of_6"]
                   and res["fiducial_clearance_dots"] > 0 and layout_ok)
    return res


# ------------------------------------------------------------------------------------------------ (8)

def tokens(skel: bytes) -> tuple[Counter, Counter]:
    """(operator names, literal names) over the non-comment lines of a skeleton (lookups and numbers out)."""
    ops: Counter = Counter()
    lits: Counter = Counter()
    for ln in skel.decode("latin1").split("\n"):
        if ln.startswith("%") or ln.startswith("\x1b") or ln.startswith("@PJL"):
            continue
        ln = re.sub(r"<[0-9a-f]*>", " ", ln)
        for t in re.findall(r"/?[A-Za-z_][\w.-]*|<<|>>", ln):
            (lits if t.startswith("/") else ops)[t] += 1
    return ops, lits


def shapes(skel: bytes) -> Counter:
    out: Counter = Counter()
    for ln in skel.decode("latin1").split("\n"):
        if ln.startswith("%") or not ln.strip():
            continue
        out[re.sub(r"<[0-9a-f]*>", "<lookup>", re.sub(r"(?<![\w])-?\d+(\.\d+)?", "N", ln))] += 1
    return out


def lookup_lists(job: bytes) -> Counter:
    rgb_by = {tuple(v[0]): k for k, v in s16.COLOURS.items() if k not in ("K-mask", "CMY", "K")}
    rgb_by[(0, 0, 0)] = "black(0,0,0)"                     # K under TonerBlack, CMY under ProcBlack
    out: Counter = Counter()
    for hv, hexs in re.findall(rb"\[/Indexed /DeviceRGB (\d+) <([0-9a-f]+)>\] setcolorspace", job):
        b = bytes.fromhex(hexs.decode())
        out[f"hival {int(hv)}: " + " ".join(rgb_by.get(tuple(b[k:k + 3]), str(tuple(b[k:k + 3])))
                                            for k in range(0, len(b), 3))] += 1
    return out


def novelty(job: bytes, records: list[dict], s15_job: bytes, s15_man: dict, s14_job: bytes,
            s14_man: dict) -> dict:
    sk16 = skeleton(job, records)
    sk15 = s14.skeleton(s15_job, s15_man["ps_structure"]["images"])
    sk14 = s14.skeleton(s14_job, s14_man["ps_structure"]["images"])
    c16, c15, c14 = s14.constructs(job), s14.constructs(s15_job), s14.constructs(s14_job)
    (o16, l16), (o15, l15), (o14, l14) = tokens(sk16), tokens(sk15), tokens(sk14)
    sh16, sh15, sh14 = shapes(sk16), shapes(sk15), shapes(sk14)
    lk16, lk15, lk14 = lookup_lists(job), lookup_lists(s15_job), lookup_lists(s14_job)
    masks = [r for r in records if r["kind"] == "imagemask"]
    old_sizes = set(c15["image_sizes"]) | set(c14["image_sizes"])
    sizes_new = Counter((r["xywh_dots"][2], r["xywh_dots"][3]) for r in records if r["kind"] != "imagemask"
                        and f"{r['xywh_dots'][2]}x{r['xywh_dots'][3]}x8bpc" not in old_sizes)
    n_band_imgs = sum(r["kind"] == "band" for r in records)

    def new(a: dict, *bs: dict) -> list:
        return sorted(set(a) - set().union(*[set(b) for b in bs]))
    return {
        "S16": c16, "S15": c15, "S14": c14,
        "operators_new_vs_S15_and_S14": new(o16, o15, o14),
        "literal_names_new_vs_S15_and_S14": new(l16, l15, l14),
        "line_shapes_new_vs_S15_and_S14": {s: sh16[s] for s in new(sh16, sh15, sh14)},
        "hp_calls_new": new(c16["hp_calls"], c15["hp_calls"], c14["hp_calls"]),
        "colour_spaces_new": new(c16["colour_spaces"], c15["colour_spaces"], c14["colour_spaces"]),
        "filters_new": new(c16["filters"], c15["filters"], c14["filters"]),
        "other_constructs_new": new(c16["other_constructs"], c15["other_constructs"],
                                    c14["other_constructs"]),
        "image_sizes_new": new(c16["image_sizes"], c15["image_sizes"], c14["image_sizes"]),
        "imagemasks": [{"object": r["image"], "w_h": r["xywh_dots"][2:], "hex_bytes": data_len(r)}
                       for r in masks],
        "lookups_new_vs_S15_and_S14": {k: lk16[k] for k in new(lk16, lk15, lk14)},
        "lookups_in_S16": dict(lk16),
        "hival_values": {"S16": sorted({r["hival"] for r in records if "hival" in r}),
                         "S15": sorted({r["hival"] for r in s15_man["ps_structure"]["images"]}),
                         "S14": sorted({r["hival"] for r in s14_man["ps_structure"]["images"]})},
        "rgb_values_new_vs_S15_and_S14": [list(v) for v in sorted(
            s14.lookups(job) - s14.lookups(s15_job) - s14.lookups(s14_job))],
        "object_counts": {"S16": len(records), "S15": len(s15_man["ps_structure"]["images"]),
                          "S14": len(s14_man["ps_structure"]["images"])},
        "summary": [
            "NEW CONSTRUCT: two K imagemask blocks (" + ", ".join(
                f"{r['image']} {r['xywh_dots'][2]}x{r['xywh_dots'][3]}" for r in masks) + ") = the operators "
            "setcmykcolor and imagemask, the literal 'true', the filter ASCIIHexDecode and their line "
            "shapes; the block is src/holo/gen/ps.py put_bitmap's, line for line (check 3), never sent with "
            "this DeviceRGB prologue on this engine.",
            "A lookup with an entry no pixel uses (T3, hival 4, red unused) -- every S14/S15 lookup was "
            "exactly the used colours.",
            "New lookups: cmy4+red (W, C-solid, M-solid, Y, red) and cmy4+K (W, C-solid, M-solid, Y, K); "
            "the cmy4 lookup itself is S15 R8's (now also under TonerBlack: T9, T14), the cmy8-engine one "
            "S15 R1's, the 2-entry bar lookups S14's / the fiducials'.",
            "New image sizes: " + ", ".join(
                f"{w}x{h} ({n})" for (w, h), n in sorted(sizes_new.items())) + "; no new HP call, operand "
            "or guard (TonerBlack + Smooth is S15 R6/R7's sequence).",
            "New content patterns: dot-mixed overlap cells (T2), partial-cell amplitude levels (T10), sparse "
            "red / K cells at 0.5 %, 10 % and 20 % (T4-T7), a cmy8 band drawn as two images around a ~20 mm "
            "OBJECT-FREE block (T13), an image whose 20 % white cells are covered by a separate mask (T9), "
            "a 4-colour image without (0,0,0) under TonerBlack (T9, T14).",
            f"Objects: {len(records)} (S15 {len(s15_man['ps_structure']['images'])}, S14 "
            f"{len(s14_man['ps_structure']['images'])}): 3 fiducial images, {n_band_imgs} band images "
            f"(T13 two), {len(masks) - 1} band mask, 2 bar images, 1 bar mask -- no tiling.",
        ]}


# ------------------------------------------------------------------------------------------------ (9)

def sizes(job: bytes, records: list[dict], nb: bytes, man_bytes: int) -> dict:
    big = max(records, key=data_len)
    return {"job_bytes": len(job), "objects": len(records),
            "images": sum(r["kind"] != "imagemask" for r in records),
            "imagemasks": sum(r["kind"] == "imagemask" for r in records),
            "data_bytes_raw_total": sum(r["data_bytes_raw"] for r in records),
            "data_bytes_encoded_total": sum(data_len(r) for r in records),
            "largest_object": {"object": big["image"], "kind": big["kind"], "xywh_dots": big["xywh_dots"],
                               "data_bytes_raw": big["data_bytes_raw"], "data_bytes_encoded": data_len(big)},
            "per_object_encoded_bytes": {r["image"]: data_len(r) for r in records},
            "npz_bytes": len(nb), "manifest_bytes": man_bytes}


# ------------------------------------------------------------------------------------------------ (10)

def window_audit(man: dict, man_path: Path, rows: list[dict]) -> dict:
    """Which manifest windows the readout skipped (vs the all-W windows), and where its errors sit: every
    loo error should be a state with a single cell in its window (no leave-one-out mean exists)."""
    bands = {b["name"]: b for b in data_bands(man)}
    with np.load(man_path.with_name(man["bands_npz"]["file"])) as npz:
        all_w = set()
        for w in man["windows"]:
            b = bands[w["band"]]
            cy, cx = w["cell_yx"]
            st = npz[f"states_{b['name']}"][cy:cy + w["cells"], cx:cx + w["cells"]]
            if (st == b["states"].index("W")).all():
                all_w.add(w["id"])
    read = {r["id"] for r in rows}
    skipped = sorted({w["id"] for w in man["windows"]} - read)
    loo = loo_ns = singles = cross = band = 0
    per_band: Counter = Counter()
    errs = {nm: {"windows_read": 0, "cells": 0, "loo": 0, "loo_non_singleton": 0, "singleton_cells": 0,
                 "cross": 0, "band": 0} for nm in bands}
    for r in rows:
        eb = errs[r["band"]]
        c = np.asarray(r["state_loo"]["confusion"])
        n = c.sum(1)
        off = n - np.diag(c)
        loo += int(off.sum())
        loo_ns += int(off[n > 1].sum())
        singles += int((n == 1).sum())
        per_band[r["band"]] += int(off.sum())
        eb["windows_read"] += 1
        eb["cells"] += int(c.sum())
        eb["loo"] += int(off.sum())
        eb["loo_non_singleton"] += int(off[n > 1].sum())
        eb["singleton_cells"] += int((n == 1).sum())
        for k in ("cross", "band"):
            if r[f"state_{k}"]:
                cc = np.asarray(r[f"state_{k}"]["confusion"])
                e = int(cc.sum() - np.trace(cc))
                eb[k] += e
                cross, band = (cross + e, band) if k == "cross" else (cross, band + e)
    return {"skipped": skipped, "skipped_count": len(skipped), "all_white_windows": len(all_w),
            "skipped_equal_all_white_windows": set(skipped) == all_w, "loo_errors": loo,
            "loo_errors_by_band": {k: v for k, v in per_band.items() if v},
            "loo_errors_only_in_T4_T6": set(k for k, v in per_band.items() if v) <= {"T4", "T6"},
            "loo_errors_on_non_singleton_states": loo_ns, "singleton_state_cells": singles,
            "cross_errors": cross, "band_errors": band, "per_band_state_errors": errs}


def readout_dry_run(man_path: Path) -> dict:
    """Both instruments, unchanged, on the clean synthetic (no TIFF written; outputs in a temp dir)."""
    import measure.e041_band_screen as bs
    import measure.e041_scale_readout as ro
    from measure.e041_mixture_synth import TONER_RGB
    from measure.e041_scale_synth import page_raster
    man = json.loads(man_path.read_text())
    with np.load(man_path.with_name(man["bands_npz"]["file"])) as npz:
        page = page_raster(man, npz, dict(TONER_RGB))
    mem = s15._MemScan(np.repeat(np.repeat(page, 4, axis=0), 4, axis=1))
    del page
    out: dict = {"image_px_hw": [4 * PAGE_H_DOTS, 4 * PAGE_W_DOTS], "toner_rgb": dict(TONER_RGB)}
    saved = ro.Scan, bs.Scan, sys.argv
    try:
        ro.Scan = mem  # type: ignore[assignment,misc]
        bs.Scan = mem  # type: ignore[assignment,misc]
        with tempfile.TemporaryDirectory() as td:
            sys.argv = ["e041_scale_readout", "--scan", "in-memory", "--manifest", str(man_path), "--out", td]
            buf, t0 = io.StringIO(), time.monotonic()
            with contextlib.redirect_stdout(buf):
                ro.main()
            summ = json.loads((Path(td) / f"{s16.TAG}-summary.json").read_text())
            out["window_audit"] = window_audit(man, man_path, summ["windows"])
            out["scale_readout"] = {
                "seconds": round(time.monotonic() - t0, 1), "windows_read": summ["n_windows_read"],
                "windows_in_manifest": len(man["windows"]), "reg_nominal": summ["n_reg_nominal"],
                "reg_edge": summ["n_reg_edge"], "fit_residual_mm": summ["fit"].get("residual_mm"),
                "bands": {s["name"]: {
                    "family": s["family"], "windows": s["windows"], "objects": s["objects"],
                    "state_err_loo_mean": s["state_err_loo"]["mean"],
                    "state_err_cross_mean": s["state_err_cross"]["mean"],
                    "state_err_band_mean": s["state_err_band"]["mean"],
                    "state_err_loo_singlepose_mean": s["state_err_loo_singlepose"]["mean"],
                    "plane_hard_err_best": {p: s["plane"][p]["hard_err_best"] for p in s14.PLANES_ORDER},
                    "mi_band_bits_per_cell": s["density"]["mi_band_bits_per_cell"],
                    "raw_bits_per_cell": s["density"]["raw_bits_per_cell"]} for s in summ["bands"]},
                "bars": [{k: b[k] for k in ("id", "colour", "neutral", "rgb", "mean_rgb", "screen_score",
                                            "verdict")} for b in summ["bars"]],
                "witness": summ["comparisons"][-1].get("witness", {}).get("reading"),
                "outputs": sorted(p.name for p in Path(td).iterdir()),
                "log_head": buf.getvalue().splitlines()[:3]}
            sys.argv = ["e041_band_screen", "--scan", "in-memory", "--manifest", str(man_path), "--out", td]
            buf, t0 = io.StringIO(), time.monotonic()
            with contextlib.redirect_stdout(buf):
                bs.main()
            with open(Path(td) / f"{s16.TAG}-columns.csv", newline="") as fh:
                cols = list(csv.DictReader(fh))
            names = [b["name"] for b in data_bands(man)]
            per = {nm: [r for r in cols if r["band"] == nm] for nm in names}
            score = {nm: max((max(float(r[f"{lat}_{ch}"]) for lat in ("165", "188", "212") for ch in "RGB")
                              for r in v), default=float("nan")) for nm, v in per.items()}
            out["band_screen"] = {
                "seconds": round(time.monotonic() - t0, 1), "columns": len(cols),
                "per_band": {nm: {"columns": len(v), "x_mm_first": float(v[0]["x_mm"]) if v else None,
                                  "x_mm_last": float(v[-1]["x_mm"]) if v else None,
                                  "max_lattice_score": round(score[nm], 1)} for nm, v in per.items()},
                "log_tail": buf.getvalue().splitlines()[-3:]}
    finally:
        ro.Scan, bs.Scan, sys.argv = saved
    sr, bsr = out["scale_readout"], out["band_screen"]
    wa = out["window_audit"]
    out["changes_needed"] = [
        "e041_scale_readout.py: none. It skips a window with no ink at all (plane_poses stacks no plane: "
        "ValueError, printed 'skipped') -- T13's all-white windows inside the object-free block carry no "
        "state; the audit checks the skipped set equals the all-W windows exactly.",
        "e041_scale_readout.py loo: a state with ONE cell in a window has no leave-one-out mean (distance "
        "inf) and always reads wrong; the rare fifth states of T4/T6 (0.5 %) hit it. The audit checks "
        "every loo error is such a singleton; cross and band (other windows' means) are exact.",
        "e041_band_screen.py: none."]
    out["pass"] = (sr["windows_read"] + len(wa["skipped"]) == sr["windows_in_manifest"]
                   and wa["skipped_equal_all_white_windows"] and sr["reg_nominal"] == 0
                   and len(sr["bars"]) == len(man["bars"]) and len(sr["bands"]) == len(data_bands(man))
                   and wa["loo_errors_on_non_singleton_states"] == 0 and wa["cross_errors"] == 0
                   and wa["loo_errors_only_in_T4_T6"]
                   and wa["band_errors"] == 0
                   and all(v["state_err_band_mean"] == 0 and v["state_err_cross_mean"] == 0
                           for v in sr["bands"].values())
                   and all(v["columns"] > 0 for v in bsr["per_band"].values()))
    return out


# ------------------------------------------------------------------------------------------------ driver

def verify(job_path: Path, man_path: Path, npz_path: Path, job: bytes, manifest: dict, nb: bytes,
           objects: list[dict], arrays: dict[str, np.ndarray], records: list[dict],
           build: Callable[[], tuple], paths: dict[str, Path]) -> dict:
    s15_job, s14_job = paths["s15"].read_bytes(), paths["s14"].read_bytes()
    s15_man = json.loads(paths["s15"].with_name(paths["s15"].stem + ".manifest.json").read_text())
    s14_man = json.loads(paths["s14"].with_name(paths["s14"].stem + ".manifest.json").read_text())
    v: dict = {}
    v["1_render"] = render_checks(job_path, manifest, arrays, objects)
    v["1_data_roundtrip"] = data_roundtrip(job, records, objects)
    v["2_guards"] = guard_checks(job, objects)
    v["3_byte_audit_vs_S15"] = byte_audit(job, records, objects, s15_job, s15_man)
    fast, _, _ = render(job_path, True)
    v["4_windows"] = window_checks(fast, manifest, npz_path, objects, s15_man)
    del fast
    v["5_geometry"] = geometry_checks(manifest, objects)
    again = build()
    v["6_two_builds_identical"] = {"job": again[0] == job, "manifest": again[1] == manifest,
                                   "npz": again[2] == nb}
    del again
    s15_rebuilt, s14_rebuilt = sha(s15.build()[0]), sha(s14.build()[0])
    v["7_rebuilt"] = {
        "S15": {"rebuilt_sha256": s15_rebuilt, "on_disk_sha256": sha(s15_job), "expected": s16.S15_SHA256,
                "pass": s15_rebuilt == sha(s15_job) == s16.S15_SHA256},
        "S14": {"rebuilt_sha256": s14_rebuilt, "on_disk_sha256": sha(s14_job), "expected": s15.S14_SHA256,
                "pass": s14_rebuilt == sha(s14_job) == s15.S14_SHA256},
        "S12": s14.s12_rebuild(paths["s11"], paths["s12"])}
    v["8_novelty"] = novelty(job, records, s15_job, s15_man, s14_job, s14_man)
    v["9_sizes"] = sizes(job, records, nb, len(json.dumps(manifest, indent=1)))
    v["10_readout_compatibility"] = readout_dry_run(man_path)
    v["pass"] = all([v["1_render"]["pass"], v["1_data_roundtrip"]["pass"], v["2_guards"]["pass"],
                     v["3_byte_audit_vs_S15"]["pass"], v["4_windows"]["pass"], v["5_geometry"]["pass"],
                     all(v["6_two_builds_identical"].values()), v["7_rebuilt"]["S15"]["pass"],
                     v["7_rebuilt"]["S14"]["pass"], v["7_rebuilt"]["S12"]["pass"],
                     v["10_readout_compatibility"]["pass"]])
    return v
