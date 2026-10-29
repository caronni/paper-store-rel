"""e042 X1 — the checks behind `ps_altalink_probe.py --verify` (split along the build / verify seam).

(1) gs 10.08 -sDEVICE=bitcmyk -r600 -g4960x7016: all four 1-bit planes against the page composed from the
manifest + npz alone, twice (from planes_<band>, and from states_/layouts_ through each band's
layout_catalogue), fiducials K -- 0 differing dots per plane; a ppmraw render exists with no message; gs
strict (nullpage, -q) silent;
(2) byte audit: (a) against holo's own reference pages, generated here by `confetti.py generate` from a fixed
counting payload (c2-cmy8-r0700@53x37 and c2-k-r0700@53x37 on A4-4mm, q 0.8): header lines equal but Title
(same "<text> J=<8 hex>" form) and Creator, the guarded setpagedevice line byte-identical, the page / trailer
lines equal, the image block's operator lines equal to the cmy8 page's up to numbers, the imagemask block's
equal to the K page's up to numbers; (b) a PSDoc replay (src/holo/gen/ps.py, unmodified: put_bitmap for every
fiducial group, put_cmyk_bitmap for every band with its C/M/Y planes) rendered and compared line for line:
equal but the Creator line and hex lines of bands carrying K samples, and those hex lines equal PSDoc's once
the K samples are cleared; no PJL, no HP operator, ASCII only;
(3) every window's states / layouts / planes against the bitcmyk render (each cell's 4 x cd x cd dots decoded
through the band's catalogue, every (state, layout) pattern unique in its band); per-entry dot counts (solid:
each of the state's planes on all cd^2 dots; c2 mixed 2:2; c3 band 5:4 with one 4-isolated B dot; K cells K
only); every grid against the formula re-derived here, the c3 bands also against S17's ps_layouts.layout_grid;
the draws re-derived from the seed; no K dot outside K cells and fiducials;
(4) geometry; (5) two builds identical; (6) novelty vs the two holo reference pages, listed; (7) sizes;
(8) measure/e041_scale_readout.py and measure/e041_band_screen.py as they stand at --scan-dpi 2400 on a clean
in-memory synthetic (e041_scale_synth.page_planes + paint_scan, 4 px per dot, identity pose, toner colours
e041_mixture_synth.TONER_RGB incl. K): passes when both run, every window is read, cross and band state errors
are 0 in every band, leave-one-out errors sit only in bands with a layout axis, and the layout reader scored
all five layout bands (its errors are reported, not gated).
"""
from __future__ import annotations

import contextlib
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import numpy as np

import ps_altalink_probe as x1
import ps_layouts as s17
import ps_layouts_verify as lv
import ps_reset as s15
import ps_scale as s14
from holo.gen.ps import PSDoc

PAGE_H_DOTS, PAGE_W_DOTS = x1.PAGE_H_DOTS, x1.PAGE_W_DOTS
REPO = Path(__file__).resolve().parents[2]
REF_FORMATS = {"cmy8": "c2-cmy8-r0700@53x37", "k": "c2-k-r0700@53x37"}
REF_PAYLOAD = bytes((i + 0x39) % 256 for i in range(4096))
HEX_RE = re.compile(r"[0-9a-f]+")
NUM_RE = re.compile(r"(?<![\w])-?\d+(\.\d+)?")


def sha(b: bytes) -> str:
    import hashlib
    return hashlib.sha256(b).hexdigest()


def gs(args: list[str], job: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["gs", "-dBATCH", "-dNOPAUSE", "-dSAFER", "-sstdout=%stderr", *args, str(job)],
                          capture_output=True, text=True)


def data_bands(man: dict) -> list[dict]:
    return [b for b in man["bands"] if b["alphabet"] is not None]


def plane_index(cat: dict, states: list[str]) -> tuple[np.ndarray, int]:
    """(states, max layouts, 4, cd, cd) uint8 ink per plane from the manifest's catalogue (unused: 255)."""
    n_max = max(len(cat[s]) for s in states)
    cd = len(cat[states[0]][0]["grid"])
    t = np.full((len(states), n_max, 4, cd, cd), 255, np.uint8)
    for i, s in enumerate(states):
        for j, e in enumerate(cat[s]):
            for r, row in enumerate(e["grid"]):
                for c, name in enumerate(row):
                    t[i, j, :, r, c] = [int(p in name and name != "W") for p in x1.PLANES_ORDER]
    return t, cd


def paint_planes(st: np.ndarray, lay: np.ndarray, t: np.ndarray) -> np.ndarray:
    """(4, rows * cd, cols * cd) ink from states / layouts through the catalogue table."""
    rows, cols = st.shape
    cd = t.shape[-1]
    cells = t[st, lay]                                       # rows, cols, 4, cd, cd
    if (cells == 255).any():
        raise SystemExit("a cell indexes a layout its state does not have")
    return np.ascontiguousarray(cells.transpose(2, 0, 3, 1, 4).reshape(4, rows * cd, cols * cd))


def composed(man: dict, arrays: dict[str, np.ndarray], from_planes: bool) -> np.ndarray:
    """(4, H, W) page from the manifest + npz alone: fiducials K, then every band."""
    page = np.zeros((4, PAGE_H_DOTS, PAGE_W_DOTS), np.uint8)
    for f in man["fiducials"]:
        x, y, w, h = f["xywh_dots"]
        page[3, y:y + h, x:x + w] = 1
    for b in data_bands(man):
        x, y, w, h = b["x_dots"], b["y_dots"], b["w_dots"], b["h_dots"]
        if from_planes:
            page[:, y:y + h, x:x + w] = arrays[f"planes_{b['name']}"]
        else:
            t, _ = plane_index(b["layout_catalogue"], b["states"])
            page[:, y:y + h, x:x + w] = paint_planes(arrays[f"states_{b['name']}"],
                                                     arrays[f"layouts_{b['name']}"], t)
    return page


# ------------------------------------------------------------------------------------------------ (1)

def render_bitcmyk(job_path: Path) -> tuple[np.ndarray, str, int, int]:
    """(4, H, W) uint8 planes of gs's bitcmyk device (4 bits per pixel, C M Y K MSB first, rows padded to a
    byte), messages, return code, raw bytes."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "x1.cmyk"
        r = gs(["-q", "-sDEVICE=bitcmyk", "-r600", f"-g{PAGE_W_DOTS}x{PAGE_H_DOTS}", f"-sOutputFile={out}"],
               job_path)
        raw = out.read_bytes() if out.exists() else b""
    row = (PAGE_W_DOTS * 4 + 7) // 8
    if len(raw) != row * PAGE_H_DOTS:
        return np.zeros((4, PAGE_H_DOTS, PAGE_W_DOTS), np.uint8), (r.stdout + r.stderr).strip(), \
            r.returncode or -1, len(raw)
    bits = np.unpackbits(np.frombuffer(raw, np.uint8).reshape(PAGE_H_DOTS, row), axis=1)
    planes = np.ascontiguousarray(bits[:, :PAGE_W_DOTS * 4].reshape(PAGE_H_DOTS, PAGE_W_DOTS, 4)
                                  .transpose(2, 0, 1))
    return planes, (r.stdout + r.stderr).strip(), r.returncode, len(raw)


def render_checks(job_path: Path, man: dict, arrays: dict[str, np.ndarray], rend: np.ndarray, msg: str,
                  rc: int, nraw: int) -> dict:
    page_pl = composed(man, arrays, True)
    page_cat = composed(man, arrays, False)
    with tempfile.TemporaryDirectory() as td:
        ppm = Path(td) / "x1.ppm"
        rp = gs(["-q", "-sDEVICE=ppmraw", "-r600", f"-g{PAGE_W_DOTS}x{PAGE_H_DOTS}", f"-sOutputFile={ppm}"],
                job_path)
        ppm_bytes = ppm.stat().st_size if ppm.exists() else 0
    strict = gs(["-q", "-sDEVICE=nullpage"], job_path)
    strict_text = (strict.stdout + strict.stderr).strip()
    res = {"gs_version": subprocess.run(["gs", "--version"], capture_output=True, text=True).stdout.strip(),
           "bitcmyk": {"returncode": rc, "messages": msg, "raw_bytes": nraw,
                       "render_sha256": sha(rend.tobytes())},
           "differing_dots_per_plane_vs_composed_from_planes": {
               p: int((rend[k] != page_pl[k]).sum()) for k, p in enumerate(x1.PLANES_ORDER)},
           "differing_dots_per_plane_vs_composed_from_states_layouts_catalogue": {
               p: int((rend[k] != page_cat[k]).sum()) for k, p in enumerate(x1.PLANES_ORDER)},
           "inked_dots_per_plane": {p: int(rend[k].sum()) for k, p in enumerate(x1.PLANES_ORDER)},
           "ppmraw": {"returncode": rp.returncode, "messages": (rp.stdout + rp.stderr).strip(),
                      "bytes": ppm_bytes},
           "gs_strict_nullpage": {"returncode": strict.returncode, "messages": strict_text}}
    res["pass"] = (rc == 0 and not msg and nraw > 0
                   and all(v == 0 for v in res["differing_dots_per_plane_vs_composed_from_planes"].values())
                   and all(v == 0 for v in
                           res["differing_dots_per_plane_vs_composed_from_states_layouts_catalogue"].values())
                   and rp.returncode == 0 and not res["ppmraw"]["messages"] and ppm_bytes > 0
                   and strict.returncode == 0 and not strict_text)
    return res


# ------------------------------------------------------------------------------------------------ (2)

def reference_pages() -> dict[str, dict[str, Any]]:
    """holo's own pages (confetti.py generate, unmodified) from REF_PAYLOAD: {key: {format, lines, sha256,
    command}}."""
    out: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory() as td:
        pay = Path(td) / "payload.bin"
        pay.write_bytes(REF_PAYLOAD)
        env = dict(os.environ, PYTHONPATH=f"{REPO / 'src'}:{REPO}")
        for key, fmt in REF_FORMATS.items():
            d = Path(td) / key
            cmd = [sys.executable, str(REPO / "confetti.py"), "generate", "--format", fmt, "--paper",
                   "A4-4mm", "--source-fraction", "0.8", "-o", str(d), str(pay)]
            r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=REPO)
            ps = d / "page000.ps"
            if r.returncode != 0 or not ps.exists():
                raise SystemExit(f"reference page {fmt}: {r.stderr.strip()[-400:]}")
            raw = ps.read_bytes()
            out[key] = {"format": fmt, "lines": raw.decode("ascii").split("\n"), "sha256": sha(raw),
                        "bytes": len(raw),
                        "command": "confetti.py " + " ".join(cmd[2:-3]) + " -o DIR payload"}
    return out


def non_hex(lines: list[str]) -> list[str]:
    return [ln for ln in lines if not HEX_RE.fullmatch(ln)]


def blocks(lines: list[str], opener: str) -> list[list[str]]:
    """Each block's non-hex lines from its opener ('gsave...') up to and including 'grestore'."""
    out, cur = [], None
    for ln in non_hex(lines):
        if ln == opener:
            cur = [ln]
        elif cur is not None:
            cur.append(ln)
            if ln == "grestore":
                out.append(cur)
                cur = None
    return out


def template(ln: str) -> str:
    return NUM_RE.sub("N", ln)


def psdoc_replay(objects: list[dict], jobid: str) -> list[str]:
    doc = PSDoc(x1.A4_DOTS_XY, jobid, title=x1.TITLE)
    doc.begin_page()
    for o in objects:
        x, y = o["xywh"][:2]
        if o["kind"] == "imagemask":
            doc.put_bitmap(o["bits"], x, y)
        else:
            doc.put_cmyk_bitmap(np.ascontiguousarray(np.moveaxis(o["planes"][:3], 0, 2)), x, y)
    doc.end_page()
    return doc.render().split("\n")


def clear_k(hex_lines: list[str], w: int, h: int) -> str:
    raw = np.frombuffer(bytes.fromhex("".join(hex_lines)), np.uint8).reshape(h, -1)
    bits = np.unpackbits(raw, axis=1)[:, :w * 4].reshape(h, w, 4).copy()
    bits[..., 3] = 0
    return np.packbits(bits.reshape(h, w * 4), axis=1).tobytes().hex()


def byte_audit(job: bytes, man: dict, records: list[dict], objects: list[dict],
               refs: dict[str, dict[str, Any]]) -> dict:
    mine = job.decode("ascii").split("\n")
    end = mine.index("%%EndComments")
    rc8, rk = refs["cmy8"]["lines"], refs["k"]["lines"]
    head_ok, head_diff = True, []
    for ref in (rc8, rk):
        e = ref.index("%%EndComments")
        if e != end:
            head_ok = False
        for a, b in zip(ref[:e + 1], mine[:end + 1]):
            if a != b:
                head_diff.append([a, b])
                if not (a.startswith("%%Creator:") and b.startswith("%%Creator:")) and not (
                        re.fullmatch(r"%%Title: .+ J=[0-9a-f]{8}", a)
                        and re.fullmatch(r"%%Title: .+ J=[0-9a-f]{8}", b)):
                    head_ok = False
    spd = mine[end + 1]
    spd_ok = (all(r[r.index("%%EndComments") + 1] == spd for r in (rc8, rk))
              and spd.startswith("{ << /PageSize"))
    page_ok = all(r[r.index("%%EndComments") + 2] == "%%Page: 1 1" for r in (rc8, rk, mine))
    tail_ok = all(r[-4:] == ["showpage", "%%Trailer", "%%EOF", ""] for r in (rc8, rk, mine))
    ref_img = blocks(rc8, "gsave /DeviceCMYK setcolorspace")
    ref_msk = blocks(rk, "gsave")
    my_img = blocks(mine, "gsave /DeviceCMYK setcolorspace")
    my_msk = [b for b in blocks(mine, "gsave")]
    img_tmpl_ok = len(ref_img) == 1 and all([template(a) for a in b] == [template(a) for a in ref_img[0]]
                                            for b in my_img)
    msk_tmpl_ok = len(ref_msk) == 1 and all([template(a) for a in b] == [template(a) for a in ref_msk[0]]
                                            for b in my_msk)
    replay = psdoc_replay(objects, man["jobid"])
    diff_idx = [i for i, (a, b) in enumerate(zip(replay, mine)) if a != b]
    spans = {r["image"]: (r["data_line_first"], r["data_line_first"] + r["data_lines"]) for r in records}
    by_obj: Counter = Counter()
    stray = []
    for i in diff_idx:
        hit = next((n for n, (a, b) in spans.items() if a <= i < b), None)
        if hit is None and not mine[i].startswith("%%Creator:"):
            stray.append([i, replay[i][:80], mine[i][:80]])
        by_obj[hit or "creator"] += 1
    k_cleared_ok, per_band = True, {}
    for r, o in zip(records, objects):
        a, b = spans[r["image"]]
        if o["kind"] == "imagemask":
            continue
        w, h = r["xywh_dots"][2:]
        cleared = clear_k(mine[a:b], w, h)
        ok = cleared == "".join(replay[a:b])
        k_cleared_ok &= ok
        per_band[r["image"]] = {"k_samples": r["k_samples"], "differing_hex_lines": by_obj.get(r["image"], 0),
                                "equal_to_put_cmyk_bitmap_after_clearing_K": ok,
                                "operator_lines_equal_put_cmyk_bitmap": replay[a - len(r["operators"]):a]
                                == r["operators"]}
    no_k_band_equal = all(v["differing_hex_lines"] == 0 for v in per_band.values() if v["k_samples"] == 0)
    masks_equal = all(by_obj.get(r["image"], 0) == 0 for r in records if r["kind"] == "imagemask")
    text = job.decode("latin1")
    res = {"reference_pages": {k: {kk: v[kk] for kk in ("format", "sha256", "bytes", "command")}
                               for k, v in refs.items()},
           "header_equal_title_creator_aside": head_ok, "header_differences": head_diff,
           "header_lines": mine[:end + 1],
           "setpagedevice_byte_identical_to_holo": spd_ok, "setpagedevice": spd,
           "page_line_equal": page_ok, "trailer_equal": tail_ok,
           "image_block_operator_lines_equal_holo_cmy8_page_up_to_numbers": img_tmpl_ok,
           "imagemask_block_operator_lines_equal_holo_K_page_up_to_numbers": msk_tmpl_ok,
           "image_blocks": len(my_img), "imagemask_blocks": len(my_msk),
           "psdoc_replay_lines": len(replay), "job_lines": len(mine),
           "psdoc_replay_differing_lines": len(diff_idx),
           "psdoc_replay_differing_lines_by_object": dict(by_obj),
           "psdoc_replay_stray_differences": stray[:5],
           "fiducial_masks_equal_put_bitmap": masks_equal,
           "bands_without_K_equal_put_cmyk_bitmap": no_k_band_equal,
           "bands_equal_put_cmyk_bitmap_after_clearing_K": k_cleared_ok, "per_band": per_band,
           "pjl_or_uel": ("@PJL" in text) or ("\x1b" in text), "hp_tokens": len(re.findall(r"\bHP\w+", text)),
           "colorsmart_tokens": text.count("ColorSmart"), "non_ascii_bytes": sum(1 for c in job if c > 126),
           "starts_with": text[:15]}
    res["pass"] = (head_ok and spd_ok and page_ok and tail_ok and img_tmpl_ok and msk_tmpl_ok
                   and len(my_img) == 14 and len(my_msk) == 3 and len(replay) == len(mine) and not stray
                   and by_obj.get("creator", 0) == 1 and masks_equal and no_k_band_equal and k_cleared_ok
                   and all(v["operator_lines_equal_put_cmyk_bitmap"] for v in per_band.values())
                   and not res["pjl_or_uel"] and res["hp_tokens"] == 0 and res["colorsmart_tokens"] == 0
                   and res["non_ascii_bytes"] == 0 and text.startswith("%!PS-Adobe-3.0\n"))
    return res


# ------------------------------------------------------------------------------------------------ (3)

def formula_grid(state: str, e: dict, cd: int) -> list[list[str]]:
    """The schema's formula for a catalogue entry, written out independently of ps_altalink_probe."""
    rng = range(cd)
    if e["id"] == "solid":
        return [[state] * cd for _ in rng]
    a, b = state[0], state[1]
    on = {"col": lambda r, c: c == 0, "row": lambda r, c: r == 0, "col1": lambda r, c: c == 1,
          "row1": lambda r, c: r == 1, "band+0": lambda r, c: c - r in (0, 1),
          "band-0": lambda r, c: r + c in (2, 3)}[e["id"]]
    return [[a if on(r, c) else b for c in rng] for r in rng]


EXPECTED_LAYOUTS = {"X5": ["col", "row"], "X6": ["col", "row", "col1", "row1"], "X8": ["band-0", "band+0"],
                    "X13": ["col", "row"], "X14": ["col", "row"]}
S17_NAME = {"C-solid": "C", "M-solid": "M", "Y": "Y"}


def entry_checks(state: str, e: dict, cd: int) -> dict:
    g = e["grid"]
    per_plane = {p: sum(p in n and n != "W" for row in g for n in row) for p in x1.PLANES_ORDER}
    multi = sum(len(n) > 1 and n != "W" for row in g for n in row)
    iso = None
    if e["id"] == "solid":
        want = {p: (cd * cd if p in state and state != "W" else 0) for p in x1.PLANES_ORDER}
        ok = per_plane == want
        meta = e["orientation"] is None and e["phase"] is None
    else:
        a, b = state[0], state[1]
        na, nb = (2, 2) if cd == 2 else (5, 4)
        want = {p: (na if p == a else nb if p == b else 0) for p in x1.PLANES_ORDER}
        ok = per_plane == want and multi == 0
        if cd == 3:
            iso = s17.isolated_b(g, b)
            ok &= len(iso) == 1
            s17g = [[S17_NAME[c] for c in row] for row in s17.layout_grid(e["id"], "CM", 3)]
            s17g = [[a if c == "C" else b for c in row] for row in s17g]
            ok &= s17g == g
            meta = e["orientation"] == e["id"][-2] and e["phase"] == int(e["id"][-1])
        else:
            meta = e["orientation"] == e["id"].rstrip("1") and e["position"] == int(e["id"].endswith("1"))
    return {"dots_per_plane": per_plane, "formula": g == formula_grid(state, e, cd) and meta, "counts_ok": ok,
            "isolated_B": [list(t) for t in iso] if iso is not None else None}


def catalogue_checks(man: dict, arrays: dict[str, np.ndarray]) -> dict:
    bad, per_entry, n_ok, draw_ok, freq, unique_ok = [], {}, True, True, {}, True
    for b in data_bands(man):
        cd, cat = b["cell_dots"], b["layout_catalogue"]
        n_ok &= set(cat) == set(b["states"])
        multi = {s: [e["id"] for e in v] for s, v in cat.items() if len(v) > 1}
        want = EXPECTED_LAYOUTS.get(b["name"])
        n_ok &= (multi == {s: want for s in x1.MIXED} if want else not multi)
        t, _ = plane_index(cat, b["states"])
        pats = [t[i, j].tobytes() for i, s in enumerate(b["states"]) for j in range(len(cat[s]))]
        unique_ok &= len(set(pats)) == len(pats)
        for s, es in cat.items():
            for e in es:
                r = entry_checks(s, e, cd)
                counts = {k: v for k, v in r["dots_per_plane"].items() if v}
                per_entry.setdefault(f"c{cd} {s} {e['id']}",
                                     counts | ({"isolated_B": r["isolated_B"]} if r["isolated_B"] else {}))
                if not (r["formula"] and r["counts_ok"]):
                    bad.append(f"{b['name']} {s} {e['id']}")
        n = np.array([len(cat[s]) for s in b["states"]], np.int64)
        rng = np.random.default_rng(b["seed"])
        st = rng.choice(len(b["states"]), size=tuple(b["cells_hw"]))
        lay = np.floor(rng.random(st.shape) * n[st]).astype(np.int64) if (n > 1).any() else np.zeros_like(st)
        draw_ok &= (b["seed"] == x1.SEED_BASE + b["band"]
                    and np.array_equal(st, arrays[f"states_{b['name']}"])
                    and np.array_equal(lay, arrays[f"layouts_{b['name']}"])
                    and arrays[f"states_{b['name']}"].dtype == np.uint8
                    and arrays[f"layouts_{b['name']}"].dtype == np.uint8
                    and b["layout_draw"] == bool((n > 1).any()))
        if (n > 1).any():
            freq[b["name"]] = {s: np.bincount(lay[st == i], minlength=n[i]).tolist()
                               for i, s in enumerate(b["states"]) if n[i] > 1}
    return {"entries_bad": bad, "entry_dot_counts": per_entry, "layouts_as_specified": n_ok,
            "patterns_unique_per_band": unique_ok, "draws_rederived_from_seed_equal_npz": draw_ok,
            "layout_frequencies_per_state": freq,
            "pass": not bad and n_ok and unique_ok and draw_ok}


def window_checks(rend: np.ndarray, man: dict, npz_path: Path) -> dict:
    """Every window: states / layouts / planes from the npz against the render's dots decoded through the
    band's catalogue (a cell's 4 x cd x cd bits must equal exactly one (state, layout) entry)."""
    bands = {b["name"]: b for b in data_bands(man)}
    with np.load(npz_path) as npz:
        arrays = {k: npz[k] for k in npz.files}
    lut = {}
    for name, b in bands.items():
        t, cd = plane_index(b["layout_catalogue"], b["states"])
        keys = {}
        for i, s in enumerate(b["states"]):
            for j in range(len(b["layout_catalogue"][s])):
                keys[t[i, j].tobytes()] = (i, j)
        lut[name] = (keys, cd)
    ok, bad, per_band = 0, [], Counter()
    for w in man["windows"]:
        b = bands[w["band"]]
        keys, cd = lut[w["band"]]
        wc = w["cells"]
        cy, cx = w["cell_yx"]
        st = arrays[f"states_{b['name']}"][cy:cy + wc, cx:cx + wc]
        lay = arrays[f"layouts_{b['name']}"][cy:cy + wc, cx:cx + wc]
        dy, dx = w["y_dots"] - b["y_dots"], w["x_dots"] - b["x_dots"]
        pl = arrays[f"planes_{b['name']}"][:, dy:dy + w["h_dots"], dx:dx + w["w_dots"]]
        win = rend[:, w["y_dots"]:w["y_dots"] + w["h_dots"], w["x_dots"]:w["x_dots"] + w["w_dots"]]
        cells = np.ascontiguousarray(win.reshape(4, wc, cd, wc, cd).transpose(1, 3, 0, 2, 4))
        dec = [keys.get(cells[r, c].tobytes(), (-1, -1)) for r in range(wc) for c in range(wc)]
        ds = np.array([d[0] for d in dec]).reshape(wc, wc)
        dl = np.array([d[1] for d in dec]).reshape(wc, wc)
        good = (np.array_equal(win, pl) and np.array_equal(ds, st) and np.array_equal(dl, lay)
                and st.shape == (wc, wc))
        ok += good
        per_band[w["band"]] += 1
        if not good:
            bad.append(w["id"])
    k_out = 0
    k_cells = {}
    for name, b in bands.items():
        st = arrays[f"states_{name}"]
        cd = b["cell_dots"]
        pl = arrays[f"planes_{name}"]
        kc = (s14.expand(st == b["states"].index("K"), cd) if "K" in b["states"]
              else np.zeros_like(pl[3], bool))
        k_out += int(pl[3][~kc].sum())
        if kc.any():
            k_cells[name] = {"K_cells": int((st == b["states"].index("K")).sum()),
                             "K_dots": int(pl[3].sum()), "CMY_dots_on_K_cells": int(pl[:3][:, kc].sum())}
    fid = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), bool)
    for f in man["fiducials"]:
        x, y, w, h = f["xywh_dots"]
        fid[y:y + h, x:x + w] = True
    band_mask = np.zeros_like(fid)
    for b in bands.values():
        band_mask[b["y_dots"]:b["y_dots"] + b["h_dots"], b["x_dots"]:b["x_dots"] + b["w_dots"]] = True
    k_page_out = int(rend[3][~fid & ~band_mask].sum())
    cmy_on_fid = int(rend[:3][:, fid].sum())
    res = {"windows": len(man["windows"]), "equal": ok, "per_band": dict(per_band), "first_bad": bad[:5],
           "K_dots_outside_K_cells_in_bands": k_out, "K_dots_outside_bands_and_fiducials": k_page_out,
           "CMY_dots_on_fiducials": cmy_on_fid, "fiducials_solid_K": bool(rend[3][fid].all()),
           "K_cells": k_cells,
           "state_counts": {n: np.bincount(arrays[f"states_{n}"].ravel(), minlength=len(b["states"])).tolist()
                            for n, b in bands.items()},
           "catalogue": catalogue_checks(man, arrays)}
    res["pass"] = (ok == len(man["windows"]) and k_out == 0 and k_page_out == 0 and cmy_on_fid == 0
                   and res["fiducials_solid_K"]
                   and all(v["CMY_dots_on_K_cells"] == 0 for v in k_cells.values())
                   and res["catalogue"]["pass"])
    return res


# ------------------------------------------------------------------------------------------------ (4)

def geometry_checks(man: dict, objects: list[dict]) -> dict:
    fr = [tuple(f["xywh_dots"]) for f in man["fiducials"]]
    br = [(b["x_dots"], b["y_dots"], b["w_dots"], b["h_dots"]) for b in man["bands"]]
    orr = [tuple(o["xywh"]) for o in objects]
    count = np.zeros((PAGE_H_DOTS, PAGE_W_DOTS), np.uint8)
    for x, y, w, h in fr + br:
        count[y:y + h, x:x + w] += 1
    ocount = np.zeros_like(count)
    for x, y, w, h in orr:
        ocount[y:y + h, x:x + w] += 1
    bands = {b["name"]: b for b in man["bands"]}
    win_ok = all(bands[w["band"]]["x_dots"] <= w["x_dots"] and w["x_dots"] + w["w_dots"]
                 <= bands[w["band"]]["x_dots"] + bands[w["band"]]["w_dots"]
                 and bands[w["band"]]["y_dots"] <= w["y_dots"] and w["y_dots"] + w["h_dots"]
                 <= bands[w["band"]]["y_dots"] + bands[w["band"]]["h_dots"]
                 and w["w_dots"] == w["h_dots"] == w["cells"] * w["cell_dots"]
                 and w["cells"] == x1.WINDOW_CELLS[w["cell_dots"]]
                 and (w["x_dots"] - bands[w["band"]]["x_dots"]) % w["w_dots"] == 0
                 and (w["y_dots"] - bands[w["band"]]["y_dots"]) % w["h_dots"] == 0 for w in man["windows"])
    page = sorted(man["bands"], key=lambda b: b["y_dots"])
    gaps = [page[k + 1]["y_dots"] - page[k]["y_dots"] - page[k]["h_dots"] for k in range(len(page) - 1)]
    by_band = {b["name"]: [w for w in man["windows"] if w["band"] == b["name"]] for b in data_bands(man)}
    y_law = all(b["y_dots"] == 283 + 462 * b["band"] and b["x_dots"] == 283 and b["w_dots"] == 4392
                and b["h_dots"] == 438 for b in man["bands"])
    fid_ref = [{k: v for k, v in f.items()} for f in s14.fiducial_plan()[0]]
    fid_mine = [{k: v for k, v in f.items() if k != "planes"} for f in man["fiducials"]]
    mask_cover = {o["name"]: [f["id"] for f in man["fiducials"] if f["image"] == o["name"]]
                  for o in objects if o["kind"] == "imagemask"}
    res = {"all_inside_page": all(0 <= x and 0 <= y and x + w <= PAGE_W_DOTS and y + h <= PAGE_H_DOTS
                                  for x, y, w, h in fr + br + orr),
           "fiducials_bands_overlap_dots": int((count > 1).sum()),
           "object_rect_overlap_dots": int((ocount > 1).sum()),
           "bands_at_x283_y283_plus_462k_4392x438": y_law,
           "windows_whole_inside_their_band_on_the_grid": win_ok, "band_gaps_dots": sorted(set(gaps)),
           "fiducial_clearance_dots": min(s15.separation(f, b) for f in fr for b in br),
           "fiducial_mask_rect_clearance_dots": min(s15.separation(o, b) for o in orr[:3] for b in br),
           "fiducials_equal_S17": fid_mine == fid_ref, "fiducial_masks": mask_cover,
           "first_band_y_dots": page[0]["y_dots"], "last_end_dots": page[-1]["y_dots"] + page[-1]["h_dots"],
           "data_bands": len(data_bands(man)),
           "cells_hw": {b["name"]: b["cells_hw"] for b in data_bands(man)},
           "windows": len(man["windows"]),
           "window_grid_per_band": {nm: [len({w["y_dots"] for w in ws}), len({w["x_dots"] for w in ws})]
                                    for nm, ws in by_band.items()}}
    res["pass"] = (res["all_inside_page"] and res["fiducials_bands_overlap_dots"] == 0
                   and res["object_rect_overlap_dots"] == 0 and y_law and win_ok and gaps
                   and all(g == 24 for g in gaps) and res["last_end_dots"] == 6727
                   and res["fiducial_clearance_dots"] > 0 and res["fiducial_mask_rect_clearance_dots"] > 0
                   and res["fiducials_equal_S17"] and res["data_bands"] == 14
                   and all(v == [4, 47] for v in res["window_grid_per_band"].values()))
    return res


# ------------------------------------------------------------------------------------------------ (6)

def skeleton_stats(lines: list[str]) -> dict[str, Counter]:
    sk = [ln for ln in non_hex(lines) if ln and not ln.startswith("%")]
    ops: Counter = Counter()
    lits: Counter = Counter()
    for ln in sk:
        for t in re.findall(r"/?[A-Za-z_][\w.-]*|<<|>>|\[|\]|\{|\}", ln):
            (lits if t.startswith("/") else ops)[t] += 1
    sizes = Counter(f"{w}x{h}" for w, h in re.findall(r"/Width (\d+) /Height (\d+)", "\n".join(sk)))
    sizes += Counter(f"{w}x{h} mask" for w, h in re.findall(r"^(\d+) (\d+) true \[", "\n".join(sk), re.M))
    return {"operators": ops, "literal_names": lits, "shapes": Counter(template(ln) for ln in sk),
            "dsc": Counter(ln for ln in non_hex(lines) if ln.startswith("%")), "sizes": sizes}


def novelty(job: bytes, records: list[dict], refs: dict[str, dict[str, Any]]) -> dict:
    mine = skeleton_stats(job.decode("ascii").split("\n"))
    rs = {k: skeleton_stats(v["lines"]) for k, v in refs.items()}

    def new(key: str) -> dict:
        both = rs["cmy8"][key] + rs["k"][key]
        return {s: n for s, n in mine[key].items() if s not in both}
    k_bands = {r["image"]: r["k_samples"] for r in records if r["kind"] == "cmyk-image" and r["k_samples"]}
    out = {"operators_new_vs_both_holo_pages": new("operators"),
           "literal_names_new_vs_both_holo_pages": new("literal_names"),
           "line_shapes_new_vs_both_holo_pages": new("shapes"),
           "dsc_lines_new_vs_both_holo_pages": new("dsc"),
           "constructs_new_vs_the_cmy8_page_alone": {s: n for s, n in mine["shapes"].items()
                                                     if s not in rs["cmy8"]["shapes"]},
           "image_sizes": {"X1": dict(mine["sizes"]), "holo_cmy8": dict(rs["cmy8"]["sizes"]),
                           "holo_k": dict(rs["k"]["sizes"])},
           "object_counts": {"X1": {"images": sum(r["kind"] == "cmyk-image" for r in records),
                                    "imagemasks": sum(r["kind"] == "imagemask" for r in records)},
                             "holo_cmy8": {"images": rs["cmy8"]["operators"].get("image", 0),
                                           "imagemasks": rs["cmy8"]["operators"].get("imagemask", 0)},
                             "holo_k": {"images": rs["k"]["operators"].get("image", 0),
                                        "imagemasks": rs["k"]["operators"].get("imagemask", 0)}},
           "nonzero_K_samples_per_band": k_bands}
    out["summary"] = [
        "No operator, literal name, colour space or filter outside holo's two pages: every image block is "
        "put_cmyk_bitmap's (/DeviceCMYK, 1 bpc, Decode [0 1 0 1 0 1 0 1], ASCIIHex) and every mask block "
        "put_bitmap's (0 0 0 1 setcmykcolor, imagemask, ASCIIHex) -- check (2b) holds the whole job to a "
        "PSDoc replay.",
        "New vs the holo cmy8 page: band-sized images (4392x438, 14 of them) instead of one whole-page "
        "4736x6784 image; three K imagemasks on a colour page (holo's K pages use the same block for the "
        "whole-page mask; on a holo colour page there is none); nonzero K samples in "
        + ", ".join(f"{k} ({v} dots)" for k, v in k_bands.items()) + " (holo: K = 0 always).",
        "New DSC: the Title text and the Creator line; no PJL wrapper on either (holo's .ps is sent as is)."]
    return out


# ------------------------------------------------------------------------------------------------ (7)

def sizes(job: bytes, records: list[dict], nb: bytes, man_bytes: int) -> dict:
    big = max(records, key=lambda r: r["data_bytes"])
    return {"job_bytes": len(job), "objects": len(records),
            "images": sum(r["kind"] == "cmyk-image" for r in records),
            "imagemasks": sum(r["kind"] == "imagemask" for r in records),
            "data_bytes_raw_total": sum(r["data_bytes_raw"] for r in records),
            "data_bytes_hex_total": sum(r["data_bytes"] for r in records),
            "largest_object": {"object": big["image"], "xywh_dots": big["xywh_dots"],
                               "data_bytes_raw": big["data_bytes_raw"], "data_bytes_hex": big["data_bytes"]},
            "per_object_hex_bytes": {r["image"]: r["data_bytes"] for r in records},
            "npz_bytes": len(nb), "manifest_bytes": man_bytes}


# ------------------------------------------------------------------------------------------------ (8)

def readout_dry_run(man_path: Path) -> dict:
    """Both instruments, as they stand, on the clean synthetic (no TIFF written; outputs in a temp dir)."""
    import measure.e041_band_screen as bs
    import measure.e041_scale_readout as ro
    import measure.e041_scale_synth as synth
    from measure.e041_mixture_readout import hypothesis_features, state_plane_sets
    from measure.e041_mixture_synth import TONER_RGB
    man = json.loads(man_path.read_text())
    with np.load(man_path.with_name(man["bands_npz"]["file"])) as npz:
        base, planes = synth.page_planes(man, npz)
        img = synth.paint_scan(base, planes, dict(TONER_RGB), {}, scan_dpi=2400.0, rot180=False,
                               shift_mm=(0.0, 0.0), scale=1.0, rot_deg=0.0, pad_mm=0.0, blur_px=0.0,
                               noise_sd=0.0, white=255.0, seed=0)
        del base, planes
    mem = lv.MemScan(img, 2400.0)
    out: dict = {"painter": "e041_scale_synth.page_planes + paint_scan (2400 dpi, identity pose, no "
                            "pad/blur/noise)", "image_px_hw": list(img.shape[:2]),
                 "toner_rgb": dict(TONER_RGB),
                 "instrument_sha256": {p: sha(Path(m.__file__).read_bytes()) for p, m in
                                       (("e041_scale_readout.py", ro), ("e041_band_screen.py", bs),
                                        ("e041_scale_synth.py", synth))}}
    del img
    saved = ro.Scan, bs.Scan, sys.argv
    summ = None
    try:
        ro.Scan = mem  # type: ignore[assignment,misc]
        bs.Scan = mem  # type: ignore[assignment,misc]
        with tempfile.TemporaryDirectory() as td:
            sys.argv = ["e041_scale_readout", "--scan", "in-memory", "--manifest", str(man_path), "--out", td,
                        "--scan-dpi", "2400"]
            buf, t0 = io.StringIO(), time.monotonic()
            try:
                with contextlib.redirect_stdout(buf):
                    ro.main()
                summ = json.loads((Path(td) / f"{x1.TAG}-summary.json").read_text())
                out["window_audit"] = lv.window_audit(man, summ["windows"])
                out["scale_readout"] = {"ran": True, "seconds": round(time.monotonic() - t0, 1),
                                        "windows_read": summ["n_windows_read"],
                                        "windows_in_manifest": len(man["windows"]),
                                        "reg_nominal": summ["n_reg_nominal"], "reg_edge": summ["n_reg_edge"],
                                        "fit_residual_mm": summ["fit"].get("residual_mm"),
                                        "log_head": buf.getvalue().splitlines()[:3],
                                        "layout_skips": [ln for ln in buf.getvalue().splitlines()
                                                         if "layout skipped" in ln][:5]}
            except BaseException as exc:                     # report, never hide: the CLI as it stands
                out["scale_readout"] = {"ran": False, "error": f"{type(exc).__name__}: {exc}",
                                        "traceback_tail": traceback.format_exc().splitlines()[-8:],
                                        "log_tail": buf.getvalue().splitlines()[-5:]}
            sys.argv = ["e041_band_screen", "--scan", "in-memory", "--manifest", str(man_path), "--out", td,
                        "--scan-dpi", "2400"]
            buf, t0 = io.StringIO(), time.monotonic()
            try:
                with contextlib.redirect_stdout(buf):
                    bs.main()
                with open(Path(td) / f"{x1.TAG}-columns.csv", newline="") as fh:
                    cols = list(csv.DictReader(fh))
                per = {b["name"]: sum(r["band"] == b["name"] for r in cols) for b in data_bands(man)}
                out["band_screen"] = {"ran": True, "seconds": round(time.monotonic() - t0, 1),
                                      "columns": len(cols), "per_band_columns": per,
                                      "log_tail": buf.getvalue().splitlines()[-3:]}
            except BaseException as exc:
                out["band_screen"] = {"ran": False, "error": f"{type(exc).__name__}: {exc}",
                                      "traceback_tail": traceback.format_exc().splitlines()[-8:]}
    finally:
        ro.Scan, bs.Scan, sys.argv = saved
    sr, bsr = out["scale_readout"], out["band_screen"]
    layout_bands = sorted(b["name"] for b in data_bands(man) if b["layout_draw"])
    if summ is not None:
        out["bands"] = {s["name"]: band_report(s, next(b for b in data_bands(man) if b["name"] == s["name"]))
                        for s in summ["bands"]}
        loo_bands = sorted(k for k, v in out["window_audit"]["per_band_state_errors"].items() if v["loo"])
        out["loo_error_bands"] = loo_bands
        out["loo_errors_only_in_layout_bands"] = set(loo_bands) <= set(layout_bands)
        out["layout_scored_bands"] = sorted(k for k, v in out["bands"].items() if v.get("layout"))
        # K handling, re-derived from the instruments' own functions on the truth fractions (as read_window)
        kh = {}
        npz = np.load(man_path.with_name(man["bands_npz"]["file"]))
        for b in data_bands(man):
            if "K" not in b["states"]:
                continue
            cd = b["cell_dots"]
            st = npz[f"states_{b['name']}"][:46, :46]
            pl = npz[f"planes_{b['name']}"][:, :46 * cd, :46 * cd]
            frac = pl.astype(np.float64).reshape(4, 46, cd, 46, cd).mean((2, 4))
            sets = state_plane_sets(frac, st.reshape(-1).astype(np.int64), len(b["states"]))
            v, vk = np.zeros((1, 3)), np.ones((1, 3))
            feats = hypothesis_features(v, vk, sets)[0]
            kh[b["name"]] = {
                "state_plane_sets": {s: "".join(p for p, on in zip(x1.PLANES_ORDER, sets[i]) if on)
                                     for i, s in enumerate(b["states"])},
                "states_read_at_K_pose": [s for i, s in enumerate(b["states"]) if feats[i].all()]}
        out["K_handling"] = kh
    out["notes"] = [
        "The state readers are nearest-mean classifiers over a centre box of half the cell (and the whole "
        "cell as *_wholecell); a mixed state with several layouts is one class, multi-modal only where its "
        "layouts differ inside the box (c2 col / row / col1 / row1 of a pair give the same centre-box mean: "
        "the 2 x 2 px box corner of each dot; c3 band-0 / band+0 do not).",
        "Layouts are decided GIVEN THE TRUE STATE by e041_layout_readout (no truth in the decision; the "
        "orientation axis is scored where a state's list has two orientations; X6's position is not a "
        "separate axis of that instrument -- its error is read here off the per-state confusion: a decision "
        "with the right orientation and the wrong entry).",
        "K: state_plane_sets puts K (and only K) in the K state's set, so hypothesis_features reads every "
        "channel of a K hypothesis at K's own pose; C/M/Y plane statistics leave out cells with K ink."]
    out["pass"] = bool(sr.get("ran") and bsr.get("ran") and out.get("loo_errors_only_in_layout_bands")
                       and sr["windows_read"] == sr["windows_in_manifest"]
                       and not out["window_audit"]["skipped"]
                       and out["window_audit"]["total"]["cross"] == 0
                       and out["window_audit"]["total"]["band"] == 0
                       and out.get("layout_scored_bands") == layout_bands
                       and all(v > 0 for v in bsr["per_band_columns"].values()))
    return out


def band_report(s: dict, b: dict) -> dict:
    """One band of the readout's summary: state errors, plane errors, K pose flags, layout errors (+ X6's
    position error from the per-state confusion)."""
    rep: dict[str, Any] = {
        "family": s["family"], "windows": s["windows"],
        "state_err_mean": {k: s[f"state_err_{k}"]["mean"] for k in ("loo", "cross", "band")},
        "state_err_wholecell_band_mean": s["state_err_band_wholecell"]["mean"],
        "mi_band_bits_per_cell": s["density"]["mi_band_bits_per_cell"],
        "raw_bits_per_cell": s["density"]["raw_bits_per_cell"],
        "plane_hard_err_best": {p: v["hard_err_best"] for p, v in s["plane"].items()
                                if v["hard_err_best"] == v["hard_err_best"]},
        "pose_flags": {p: {f: n for f, n in v["flags"].items() if n} for p, v in s["pose"].items()}}
    lay = s.get("layout")
    if lay:
        per = {}
        for st, v in lay["per_state"].items():
            ids = v["ids"]
            conf = np.asarray(v["confusion"])
            pos_err = None
            if any(i.endswith("1") for i in ids):
                ori = [i.rstrip("1") for i in ids]
                same = np.array([[ori[a] == ori[d] and a != d for d in range(len(ids))]
                                 for a in range(len(ids))])
                pos_err = float(conf[same].sum() / max(conf.sum(), 1))
            per[st] = {"n": v["n"], "err": v["err"], "orient_err": v["orient_err"],
                       "phase_err": v["phase_err"],
                       "position_err": pos_err, "mi_bits": v["mi_bits"], "raw_bits": v["raw_bits"]}
        rep["layout"] = {"err": lay.get("err"), "orient_err": lay.get("orient_err"),
                         "phase_err": lay.get("phase_err"), "windows": lay.get("windows"),
                         "mi_layout_bits_per_cell": lay.get("mi_layout_bits_per_cell"),
                         "combined_band_bits_per_cell": lay.get("combined_band_bits_per_cell"),
                         "psf_dots_median": lay.get("psf_dots_median"), "per_state": per}
    return rep


# ------------------------------------------------------------------------------------------------ driver

def verify(job_path: Path, man_path: Path, npz_path: Path, job: bytes, manifest: dict, nb: bytes,
           objects: list[dict], arrays: dict[str, np.ndarray], records: list[dict],
           build: Callable[[], tuple]) -> dict:
    v: dict = {}
    rend, msg, rc, nraw = render_bitcmyk(job_path)
    v["1_render"] = render_checks(job_path, manifest, arrays, rend, msg, rc, nraw)
    refs = reference_pages()
    v["2_byte_audit_vs_holo"] = byte_audit(job, manifest, records, objects, refs)
    v["3_windows"] = window_checks(rend, manifest, npz_path)
    del rend
    v["4_geometry"] = geometry_checks(manifest, objects)
    again = build()
    v["5_two_builds_identical"] = {"job": again[0] == job, "manifest": again[1] == manifest,
                                   "npz": again[2] == nb}
    del again
    v["6_novelty"] = novelty(job, records, refs)
    del refs
    v["7_sizes"] = sizes(job, records, nb, len(json.dumps(manifest, indent=1)))
    v["8_readout_dry_run"] = readout_dry_run(man_path)
    v["pass"] = all([v["1_render"]["pass"], v["2_byte_audit_vs_holo"]["pass"], v["3_windows"]["pass"],
                     v["4_geometry"]["pass"], all(v["5_two_builds_identical"].values()),
                     v["8_readout_dry_run"]["pass"]])
    return v
