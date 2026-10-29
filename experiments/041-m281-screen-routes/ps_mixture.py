"""e041 S12 — route equivalence on the HP M281: does the S11 mixture page print the same through PostScript?

THE QUESTION.  S11 (pclxl_mixture.py) sent the mixture probe as PCL XL.  The production generator emits
PostScript, so S12 sends the SAME page -- the same 258 patches at the same dots, the same twelve band images
and three fiducial images, the same palette indices -- through the engine's PostScript interpreter, with the
HP image operators in the place of S11's PCL XL controls: a band of method default gets
`Smooth ColorSmartImageHalftone` (the PPD default, set explicitly), a band of method eHighLPI gets
`Detail ColorSmartImageHalftone` (the PostScript analogue of a finer screen; untested on this engine, a
witness in itself); neutral axis process -> `ProcBlack HPImageNeutralAxis`, toner ->
`TonerBlack HPImageNeutralAxis`.
The pair -- plus `Off HPColorTrapping` and `false HPImageAdaptiveHalftoning`, S11's two disables --
is set inside every image's gsave, after its setcolorspace (S11's order: colour space, then
controls, neutral axis before the halftone), the three fiducial images included (S11 drew them under
eProcessBlack and the default method: here ProcBlack + Smooth).

THE PAGE IS READ, NOT RE-DERIVED: the S11 manifest + its patterns npz are the only source of the rasters
(pclxl_mixture.composed: the arms table, colour table and per-patch states), the band rectangles come from
the manifest's band table, the palettes from its colour table; --verify checks the result against S11's own
plan() image by image.

THE JOB = S1's frame (F): the PJL wrapper with JOB NAME "E041-S12-PS-MIXTURE" and no BITSPERPIXEL / RET
lines, F's DSC header shape, F's setpagedevice line verbatim, a prologue that defines the four bare names
TonerBlack, ProcBlack, Smooth, Detail as strings only where they are undefined (the device has them; gs does
not), then per image: gsave, `[/Indexed /DeviceRGB hival <lookup>] setcolorspace`, the two HP calls each
behind a `where` guard (gs has neither operator: the guard skips them), `x y translate w h scale` in points
(1 dot = 0.12 pt), an ImageType 1 dictionary (BitsPerComponent 8, Decode [0 255], ImageMatrix
[W 0 0 -H 0 H], DataSource currentfile /ASCII85Decode filter), the data, grestore.  One showpage, EOJ.  hival
= the largest palette index the image uses; entries the image does not use are white, as in S11's 256-entry
palettes.  ASCII85 (not F's ASCIIHex): white is index 0, so every all-white 4-byte group is one 'z'; data
lines are 128 characters, a line that would begin with '%' gets a leading space (ASCII85Decode skips
whitespace).  No ColorSmartColorMatching / ColorSmartImageAdjustment change (the default helped on S6).

Outputs: the job and <stem>.manifest.json = S11's manifest with tag "S12-ps-mixture", method labels
"smooth" / "detail" (each patch and band keeps "pclxl_method", the S11 label), this job's bytes / sha256, a
"ps_structure" section, and the S11 patterns npz referenced by file name (beside the manifest; not copied).

--verify: (1) gs ppmraw render at 600 dpi (-g4960x7016) against the page painted from the images' palettes,
and against pclxl_mixture.composed() of the S11 manifest and of the S12 manifest (identical arrays), plus
S11's gpcl6 ppmraw render against this render; the images against S11's plan(); (2) gs strict run (no
PostScript error) and a stub run (the six measured HP operators defined as call loggers, image and showpage
wrapped): every image preceded by exactly one HPImageNeutralAxis and one ColorSmartImageHalftone call with
the intended operands, no other HP operator called; (3) byte audit of the PJL wrapper, the setpagedevice
line, one showpage, EOJ; (4) sizes; (5) two builds identical; (6) the readout's loaders on the S12 manifest.

    PYTHONPATH=src:. env/bin/python experiments/041-m281-screen-routes/ps_mixture.py \\
        --s11 experiments/041-m281-screen-routes/build/S11-pclxl-mixture.manifest.json \\
        --out experiments/041-m281-screen-routes/build/S12-ps-mixture.ps --verify
"""
from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np

import pclxl_bilevel as xl
import pclxl_mixture as s11
from pcl_planar import sha, stub_font
from pclxl_probe import DPI, dots
from pclxl_probe_sheets import FIDUCIAL_IMAGES
from pclxl_mixture_arms import PATCH_H_DOTS, PATTERN_DOTS

TAG = "S12-ps-mixture"
JOB_NAME = "E041-S12-PS-MIXTURE"
S1_NAME = "S1-pjl-bpp1.ps"  # F's frame, printed on this engine; default: beside --out
PS_METHOD = {"default": "smooth", "highlpi": "detail"}
HALFTONE = {"default": "Smooth", "highlpi": "Detail"}
NEUTRAL = {"process": "ProcBlack", "toner": "TonerBlack"}
BARE_NAMES = ("TonerBlack", "ProcBlack", "Smooth", "Detail", "Off")
HP_OPERATORS = ("HPImageNeutralAxis", "ColorSmartImageHalftone", "ColorSmartColorMatching",
                "ColorSmartImageAdjustment", "HPImageAdaptiveHalftoning", "HPColorTrapping")
PT_PER_DOT = 72 / DPI
PAGE_HW_DOTS = (7016, 4960)
A85_COLUMNS = 128
UEL = b"\x1b%-12345X"
WRAPPER_HEAD = UEL + f'@PJL JOB NAME="{JOB_NAME}"\r\n@PJL ENTER LANGUAGE=POSTSCRIPT\r\n'.encode()
WRAPPER_TAIL = b"%%EOF\n\r\n" + UEL + b"@PJL EOJ\r\n" + UEL
SETPAGEDEVICE = (b"{ << /PageSize [595.20 841.92] /HWResolution [600 600] /Duplex false >> setpagedevice }"
                 b" stopped { } if\n")
HEADER = (b"%!PS-Adobe-3.0\n%%Title: e041 S12 PostScript mixture probe (the S11 page)\n"
          b"%%Creator: experiments/041-m281-screen-routes/ps_mixture.py\n%%LanguageLevel: 2\n"
          b"%%DocumentData: Clean7Bit\n%%BoundingBox: 0 0 596 842\n%%Pages: 1\n%%EndComments\n")


# ------------------------------------------------------------------------------------------------ images

def load_s11(manifest_path: Path) -> tuple[dict, dict[str, np.ndarray], Path]:
    man = json.loads(manifest_path.read_text())
    if man.get("tag") != s11.TAG:
        raise SystemExit(f"{manifest_path}: tag {man.get('tag')!r}, {s11.TAG!r} expected")
    npz_path = manifest_path.with_name(man["patterns_npz"]["file"])
    raw = npz_path.read_bytes()
    if sha(raw) != man["patterns_npz"]["sha256"]:
        raise SystemExit(f"{npz_path}: sha256 differs from the S11 manifest")
    return man, s11.load_npz(npz_path), npz_path


def palette_of(raster: np.ndarray, rgb_by_index: np.ndarray) -> np.ndarray:
    """(hival + 1, 3) uint8: the used indices' colours, every other entry white."""
    used = np.unique(raster)
    pal = np.full((int(used.max()) + 1, 3), 255, np.uint8)
    pal[used] = rgb_by_index[used]
    return pal


def images_from_manifest(man: dict, npz: dict[str, np.ndarray]) -> list[dict]:
    """Every image in S11's draw order (the three fiducial images, then the bands by draw_position): its
    rectangle, raster of global colour indices, palette, method and neutral axis, from the manifest + npz."""
    _, per = s11.composed(man, npz, PAGE_HW_DOTS)
    rgb_by_index = np.array([c["rgb"] for c in sorted(man["colours"], key=lambda c: c["index"])], np.uint8)
    fids = {f["id"]: f for f in man["fiducials"]}
    images: list[dict] = []
    for name, ids in FIDUCIAL_IMAGES:
        boxes = []
        for i in ids:
            f = fids[i]
            if f.get("image") != name:
                raise SystemExit(f"fiducial {i}: image {f.get('image')!r}, {name!r} expected")
            boxes.append((dots(f["x_mm"]), dots(f["y_mm"]), dots(f["w_mm"]), dots(f["h_mm"])))
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[0] + b[2] for b in boxes), max(b[1] + b[3] for b in boxes)
        raster = np.zeros((y1 - y0, x1 - x0), np.uint8)
        for bx, by, bw, bh in boxes:
            raster[by - y0:by - y0 + bh, bx - x0:bx - x0 + bw] = 1
        pal = np.array([[255, 255, 255], [0, 0, 0]], np.uint8)
        images.append({"name": name, "kind": "fiducial", "band": None, "method": "default",
                       "neutral": "process", "xywh": (x0, y0, x1 - x0, y1 - y0), "raster": raster,
                       "palette": pal, "members": list(ids)})
    by_id = {p["id"]: p for p in man["patches"]}
    for b in sorted(man["bands"], key=lambda b: b["draw_position"]):
        x, y, w, h = b["x_dots"], b["y_dots"], b["w_dots"], b["h_dots"]
        raster = np.zeros((h, w), np.uint8)
        for pid in b["members"]:
            p = by_id[pid]
            px, py = dots(p["x_mm"]) - x, dots(p["y_mm"]) - y
            raster[py:py + PATCH_H_DOTS, px:px + PATTERN_DOTS] = per[pid]
        images.append({"name": f"band{b['band']}", "kind": "band", "band": b["band"], "method": b["method"],
                       "neutral": b["neutral"], "xywh": (x, y, w, h), "raster": raster,
                       "palette": palette_of(raster, rgb_by_index), "members": list(b["members"])})
    if [i["name"] for i in images] != [f"fid-{n}" for n in ("top", "left", "bottom")] + [
            f"band{b['band']}" for b in sorted(man["bands"], key=lambda b: b["draw_position"])]:
        raise SystemExit("image order is not S11's draw order")
    if sorted(b["draw_position"] for b in man["bands"]) != list(range(3, 3 + len(man["bands"]))):
        raise SystemExit("S11 band draw positions do not follow the three fiducial images")
    return images


# ------------------------------------------------------------------------------------------------ emission

def a85_lines(data: bytes) -> bytes:
    """ASCII85 (no '<~'), 'z' for zero groups, 128-column lines, a leading space on a line starting '%',
    the '~>' end of data on the last line."""
    enc = base64.a85encode(data, wrapcol=A85_COLUMNS, adobe=False)
    lines = [(b" " + ln if ln.startswith(b"%") else ln) for ln in enc.split(b"\n")]
    return b"\n".join(lines) + b"~>\n"


def hp_call(operand: str, operator: str) -> str:
    return f"/{operator} where {{ pop {operand} {operator} }} if"


def image_lines(head: str, xywh: tuple[int, int, int, int], palette: np.ndarray,
                calls: list[str]) -> list[str]:
    """The PostScript lines of one image up to and including `>> image`: the comment head, gsave, the
    Indexed DeviceRGB colour space of the palette, the guarded HP calls, the placement and the image dict."""
    x, y, w, h = xywh
    lookup = palette.tobytes().hex()
    tx, ty = x * PT_PER_DOT, (PAGE_HW_DOTS[0] - y - h) * PT_PER_DOT
    return [head, "gsave",
            f"[/Indexed /DeviceRGB {len(palette) - 1} <{lookup}>] setcolorspace",
            *calls,
            f"{tx:.6f} {ty:.6f} translate",
            f"{w * PT_PER_DOT:.6f} {h * PT_PER_DOT:.6f} scale",
            "<< /ImageType 1",
            f"   /Width {w} /Height {h} /BitsPerComponent 8",
            "   /Decode [0 255]",
            f"   /ImageMatrix [{w} 0 0 -{h} 0 {h}]",
            "   /DataSource currentfile /ASCII85Decode filter",
            ">> image"]


def image_ops(img: dict) -> list[str]:
    """The PostScript lines of one image up to and including `>> image` (the data follows)."""
    head = (f"% {img['name']}: {img['kind']}" + (f" {img['band']}" if img["band"] is not None else "")
            + f", S11 method {img['method']} -> {HALFTONE[img['method']]}, neutral {img['neutral']} -> "
            f"{NEUTRAL[img['neutral']]}")
    return image_lines(head, img["xywh"], img["palette"],
                       [hp_call(NEUTRAL[img["neutral"]], "HPImageNeutralAxis"),
                        hp_call(HALFTONE[img["method"]], "ColorSmartImageHalftone"),
                        hp_call("Off", "HPColorTrapping"),
                        hp_call("false", "HPImageAdaptiveHalftoning")])


def prologue() -> bytes:
    lines = ["% e041 S12: the HP bare names, defined only where the interpreter lacks them (gs)"]
    lines += [f"/{n} where {{ pop }} {{ /{n} ({n}) def }} ifelse" for n in BARE_NAMES]
    return ("\n".join(lines) + "\n").encode()


def emit_job(images: list[dict]) -> tuple[bytes, list[dict]]:
    """The job and, per image, its structure record (operators, offsets, data lengths)."""
    parts = [WRAPPER_HEAD, HEADER, SETPAGEDEVICE, prologue(), b"%%Page: 1 1\n"]
    records = []
    for img in images:
        ops = image_ops(img)
        text = ("\n".join(ops) + "\n").encode()
        raw = img["raster"].tobytes()
        data = a85_lines(raw)
        offset = sum(len(p) for p in parts) + len(text)
        parts += [text, data, b"grestore\n"]
        x, y, w, h = img["xywh"]
        records.append({"image": img["name"], "kind": img["kind"], "band": img["band"],
                        "pclxl_method": img["method"], "method": PS_METHOD[img["method"]],
                        "neutral": img["neutral"], "xywh_dots": [x, y, w, h], "operators": ops[1:],
                        "hival": len(img["palette"]) - 1, "data_offset": offset, "data_bytes_raw": len(raw),
                        "data_bytes_ascii85": len(data), "raster_sha256": sha(raw)})
    parts += [b"showpage\n%%Trailer\n", WRAPPER_TAIL]
    return b"".join(parts), records


def build(manifest_path: Path) -> tuple[dict, dict[str, np.ndarray], Path, list[dict], bytes, list[dict]]:
    man, npz, npz_path = load_s11(manifest_path)
    images = images_from_manifest(man, npz)
    job, records = emit_job(images)
    return man, npz, npz_path, images, job, records


# ------------------------------------------------------------------------------------------------ manifest

def relabel(d: dict) -> dict:
    return {**d, "method": PS_METHOD[d["method"]], "pclxl_method": d["method"]}


def counts(patches: list[dict], bands: list[dict]) -> dict:
    return {"total": len(patches), "by_method": dict(Counter(p["method"] for p in patches)),
            "by_kind": dict(Counter(f"{p['method']}/{p['neutral']}" for p in patches)),
            "by_band": {str(b["band"]): f"{b['patches']} of {b['slots']} slots "
                        f"({b['method']}/{b['neutral']}, third {b['third']})" for b in bands}}


def notes() -> list[str]:
    return [
        "WHY: route equivalence. S11 printed the mixture page as PCL XL; the production generator emits "
        "PostScript. S12 = the same page by construction (rasters read from the S11 manifest + npz) through "
        "the PostScript interpreter.",
        "CONTROLS: S11 eHighLPI -> Detail ColorSmartImageHalftone, S11 default -> Smooth (the PPD default, "
        "explicit); eProcessBlack -> ProcBlack HPImageNeutralAxis, eTonerBlack -> TonerBlack. Set inside "
        "each image's gsave after its setcolorspace, the fiducial images included (ProcBlack + Smooth, as "
        "S11 drew them under eProcessBlack / default). S11's SetColorTrapping eDisable and "
        "SetAdaptiveHalftoning eDisable are matched by `Off HPColorTrapping` and "
        "`false HPImageAdaptiveHalftoning` after the halftone call in every image (both accepted by query 4 "
        "and printed in S6; added 2026-10-05 on the refuter's finding that trapping acts on exactly the "
        "neighbourhood S11 asks about). S11's SetColorTreatment eNoTreatment has NO counterpart: ColorSmart "
        "colour matching and image adjustment stay at the device defaults (S10p2 measured eNoTreatment null "
        "on single-colour marks; S6 measured matching-off as worse under DeviceCMYK) -- recorded as the one "
        "control that differs between S11 and S12.",
        "PAGE DEVICE = F's setpagedevice line verbatim (no ProcessColorModel request; the device default "
        "applies). PJL = S1's wrapper without BITSPERPIXEL / RET.",
        "IMAGES: 8-bit Indexed DeviceRGB, hival = the largest index the image uses (unused entries white); "
        "the same global colour indices as S11 (manifest 'colours'). K (6) and CMY (10) are both (0,0,0): "
        "the band's neutral axis decides which toner lays them.",
        "DATA: ASCII85Decode ('z' for white groups), 128-column lines, '~>' end.",
        "PATTERNS: the S11 npz, referenced by file name, not copied; the readout resolves it from "
        "patterns_npz.file.",
        "gs knows neither HP operator; its render shows the page, not what the engine does with the "
        "controls.",
    ]


def s12_manifest(man: dict, job: bytes, records: list[dict], s11_path: Path, npz_path: Path) -> dict:
    keep = ("dpi", "page_mm", "fiducials", "patch_px", "slot_grid", "arms", "colours", "planes_order",
            "layout_seed", "state_seed_base")
    drop_band = ("row_bytes", "readimage_blocks", "controls_after_SetColorSpace")
    rec = {r["band"]: r for r in records if r["kind"] == "band"}
    bands = [{**{k: v for k, v in relabel(b).items() if k not in drop_band},
              "ps_operators": rec[b["band"]]["operators"][:5]} for b in man["bands"]]
    patches = [relabel(p) for p in man["patches"]]
    return {
        "tag": TAG, **{k: man[k] for k in keep[:2]}, "bytes": len(job), "sha256": sha(job),
        "patterns_npz": {**man["patterns_npz"], "path": str(npz_path)},
        **{k: man[k] for k in keep[2:4]},
        "bands": bands, "patches": patches, **{k: man[k] for k in keep[4:]},
        "derived_from": {"s11_manifest": str(s11_path), "s11_manifest_sha256": sha(s11_path.read_bytes()),
                         "s11_job_sha256": man["sha256"], "s11_job_bytes": man["bytes"],
                         "s11_tag": man["tag"]},
        "ps_structure": {
            "wrapper_head": WRAPPER_HEAD.decode("latin1"), "wrapper_tail": WRAPPER_TAIL.decode("latin1"),
            "header": HEADER.decode(), "setpagedevice": SETPAGEDEVICE.decode(),
            "prologue": prologue().decode(),
            "data_filter": "ASCII85Decode", "a85_columns": A85_COLUMNS, "pt_per_dot": PT_PER_DOT,
            "page_hw_dots": list(PAGE_HW_DOTS), "method_map": {k: {"label": PS_METHOD[k], "operand": v}
                                                                for k, v in HALFTONE.items()},
            "neutral_map": NEUTRAL, "images": records},
        "notes": notes(), "counts": counts(patches, bands), "s11_counts": man["counts"],
        "generator": " ".join(["PYTHONPATH=src:.", sys.executable, *sys.argv]),
    }


# ------------------------------------------------------------------------------------------------ verify

def read_ppm(path: Path) -> np.ndarray:
    raw = path.read_bytes()
    fields, pos = [], 0
    while len(fields) < 4:
        while raw[pos:pos + 1].isspace():
            pos += 1
        if raw[pos:pos + 1] == b"#":
            pos = raw.index(b"\n", pos) + 1
            continue
        end = pos
        while not raw[end:end + 1].isspace():
            end += 1
        fields.append(raw[pos:end])
        pos = end
    if fields[0] != b"P6" or fields[3] != b"255":
        raise SystemExit(f"{path}: not an 8-bit P6")
    w, h = int(fields[1]), int(fields[2])
    return np.frombuffer(raw[pos + 1:pos + 1 + w * h * 3], np.uint8).reshape(h, w, 3)


def gs(args: list[str], job: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["gs", "-dBATCH", "-dNOPAUSE", "-dSAFER", "-sstdout=%stderr", *args, str(job)],
                          capture_output=True, text=True)


def painted(images: list[dict]) -> np.ndarray:
    page = np.full((*PAGE_HW_DOTS, 3), 255, np.uint8)
    for img in images:
        x, y, w, h = img["xywh"]
        page[y:y + h, x:x + w] = img["palette"][img["raster"]]
    return page


def against_s11_plan(images: list[dict]) -> dict:
    """Every image against S11's own plan(): name, rectangle, raster, used palette entries."""
    _, _, plan_images, _ = s11.plan()
    rows = []
    for a, b in zip(images, plan_images):
        used = np.unique(b["raster"])
        rows.append(a["name"] == b["name"] and tuple(a["xywh"]) == tuple(b["xywh"])
                    and np.array_equal(a["raster"], b["raster"])
                    and np.array_equal(a["palette"][used], b["palette"][used]))
    return {"images": len(images), "plan_images": len(plan_images), "equal": sum(rows),
            "pass": len(images) == len(plan_images) and all(rows)}


def render_checks(job_path: Path, images: list[dict], man11: dict, man12: dict, npz: dict[str, np.ndarray],
                  s11_job: Path) -> dict:
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "s12.ppm"
        r = gs(["-q", "-sDEVICE=ppmraw", "-r600", "-g4960x7016", f"-sOutputFile={out}"], job_path)
        img = read_ppm(out)
        (fonts := Path(td) / "fonts").mkdir()
        (fonts / "stub.ttf").write_bytes(stub_font())
        pcl, pcl_messages = xl.render(s11_job, Path(td) / "s11.ppm", fonts, "ppmraw")
    page = painted(images)
    comp11, _ = s11.composed(man11, npz, PAGE_HW_DOTS)
    comp12, _ = s11.composed(man12, npz, PAGE_HW_DOTS)
    covered = np.zeros(PAGE_HW_DOTS, bool)
    fid_black = True
    for f in man11["fiducials"]:
        x, y, w, h = dots(f["x_mm"]), dots(f["y_mm"]), dots(f["w_mm"]), dots(f["h_mm"])
        covered[y:y + h, x:x + w] = True
        fid_black &= bool((img[y:y + h, x:x + w] == 0).all())
    for p in man11["patches"]:
        x, y = dots(p["x_mm"]), dots(p["y_mm"])
        covered[y:y + PATCH_H_DOTS, x:x + PATTERN_DOTS] = True
    res = {"gs_returncode": r.returncode, "gs_messages": (r.stdout + r.stderr).strip(),
           "page_hw": list(img.shape[:2]), "render_sha256": sha(img.tobytes()),
           "differing_dots_vs_painted": int((img != page).any(2).sum()),
           "painted_equals_composed_S11_manifest": bool(np.array_equal(page, comp11)),
           "composed_S11_equals_composed_S12_manifest": bool(np.array_equal(comp11, comp12)),
           "fiducials_solid_black": fid_black,
           "non_white_outside_objects": int(((img != 255).any(2) & ~covered).sum()),
           "inked_dots": int((img != 255).any(2).sum()),
           "S11_gpcl6_render_sha256": sha(pcl.tobytes()), "S11_gpcl6_messages": pcl_messages,
           "S11_gpcl6_page_hw": list(pcl.shape[:2])}
    rows = min(pcl.shape[0], img.shape[0])
    # gpcl6 lays PCL XL's A4 as 7014 rows; the PostScript page is 841.92 pt = 7016: compare the common rows,
    # the rest must be white on both sides.
    res["differing_dots_S12_gs_vs_S11_gpcl6"] = (int((img[:rows] != pcl[:rows]).any(2).sum())
                                                 if pcl.shape[1] == img.shape[1] else "width differs")
    res["rows_compared_vs_gpcl6"] = rows
    res["rows_beyond_common_all_white"] = bool((img[rows:] == 255).all() and (pcl[rows:] == 255).all())
    res["pass"] = (r.returncode == 0 and not res["gs_messages"] and res["differing_dots_vs_painted"] == 0
                   and res["painted_equals_composed_S11_manifest"]
                   and res["composed_S11_equals_composed_S12_manifest"] and fid_black
                   and res["non_white_outside_objects"] == 0
                   and res["differing_dots_S12_gs_vs_S11_gpcl6"] == 0 and res["rows_beyond_common_all_white"])
    return res


def stub_prologue() -> bytes:
    lines = ["% e041 S12 verify: HP operator stubs (call loggers), image and showpage wrapped"]
    lines += [f"/{op} {{ (HPCALL {op} ) print == }} def" for op in HP_OPERATORS]
    lines += ["/image { (IMAGE ) print dup /Width get =only ( ) print dup /Height get == "
              "systemdict /image get exec } def",
              "/showpage { (SHOWPAGE) = systemdict /showpage get exec } def"]
    return ("\n".join(lines) + "\n").encode()


def guard_checks(job: bytes, images: list[dict]) -> dict:
    """gs strict on the job as sent; then the job with the stub prologue after %%EndComments."""
    with tempfile.TemporaryDirectory() as td:
        plain = Path(td) / "s12.ps"
        plain.write_bytes(job)
        strict = gs(["-sDEVICE=nullpage"], plain)
        stubbed = Path(td) / "s12-stubs.ps"
        cut = job.index(b"%%EndComments\n") + len(b"%%EndComments\n")
        stubbed.write_bytes(job[:cut] + stub_prologue() + job[cut:])
        run = gs(["-q", "-sDEVICE=nullpage"], stubbed)
    log = [ln for ln in run.stderr.splitlines() if ln.startswith(("HPCALL", "IMAGE", "SHOWPAGE"))]
    want = []
    for img in images:
        x, y, w, h = img["xywh"]
        want += [f"HPCALL HPImageNeutralAxis ({NEUTRAL[img['neutral']]})",
                 f"HPCALL ColorSmartImageHalftone ({HALFTONE[img['method']]})",
                 "HPCALL HPColorTrapping (Off)", "HPCALL HPImageAdaptiveHalftoning false",
                 f"IMAGE {w} {h}"]
    want.append("SHOWPAGE")
    calls = Counter(ln.split()[1] for ln in log if ln.startswith("HPCALL"))
    other = (run.stderr.replace("\n".join(log), "").strip()) if log else run.stderr.strip()
    strict_text = (strict.stdout + strict.stderr).strip()
    res = {"strict_returncode": strict.returncode, "strict_messages": strict_text,
           "strict_has_error": "Error" in strict_text,
           "stub_returncode": run.returncode, "stub_log_lines": len(log), "stub_calls": dict(calls),
           "stub_sequence_exact": log == want, "stub_other_output": other,
           "operand_pairs": dict(Counter(f"{NEUTRAL[i['neutral']]}+{HALFTONE[i['method']]}" for i in images))}
    if log != want:
        res["first_mismatch"] = next(([k, a, b] for k, (a, b) in enumerate(zip(log, want)) if a != b),
                                     [min(len(log), len(want)), None, None])
    res["pass"] = (strict.returncode == 0 and not res["strict_has_error"] and run.returncode == 0
                   and log == want and set(calls) == {"HPImageNeutralAxis", "ColorSmartImageHalftone",
                                                      "HPColorTrapping", "HPImageAdaptiveHalftoning"})
    return res


def data_spans(records: list[dict]) -> list[tuple[int, int]]:
    return [(r["data_offset"], r["data_offset"] + r["data_bytes_ascii85"]) for r in records]


def byte_audit(job: bytes, records: list[dict], s1: bytes) -> dict:
    """The wrapper against S1's, the setpagedevice line against F's, the non-data text's operators."""
    i = s1.index(b"%!PS")
    s1_head, s1_tail = s1[:i], s1[s1.index(b"%%EOF"):]
    want_head = (s1_head.replace(b'JOB NAME="E041-S1-BPP1"', f'JOB NAME="{JOB_NAME}"'.encode())
                 .replace(b"@PJL SET BITSPERPIXEL=1\r\n", b"").replace(b"@PJL SET RET=OFF\r\n", b""))
    k = s1.index(b"{ <<")
    s1_spd = s1[k:s1.index(b"\n", k) + 1]
    spans = data_spans(records)
    text, pos = [], 0
    for a, b in spans:
        text.append(job[pos:a])
        pos = b
    text.append(job[pos:])
    skeleton = b"".join(text)
    lines = skeleton.split(b"\n")
    res = {"wrapper_head": job[:len(WRAPPER_HEAD)].decode("latin1"),
           "wrapper_head_equals_S1_minus_name_bpp_ret": job[:job.index(b"%!PS")] == want_head,
           "wrapper_tail_equals_S1": job[job.index(b"%%EOF"):] == s1_tail,
           "setpagedevice_equals_F": SETPAGEDEVICE == s1_spd and job.count(s1_spd) == 1,
           "showpage_lines": lines.count(b"showpage"), "image_operators": lines.count(b">> image"),
           "gsave": lines.count(b"gsave"), "grestore": lines.count(b"grestore"),
           "setcolorspace_lines": sum(ln.endswith(b"setcolorspace") for ln in lines),
           "EOJ": job.endswith(b"@PJL EOJ\r\n" + UEL), "non_ascii_bytes_after_wrapper": sum(
               1 for c in job[len(WRAPPER_HEAD):-len(WRAPPER_TAIL)] if c > 126 or (c < 32 and c != 10)),
           "data_lines_starting_with_percent": sum(
               ln.startswith(b"%") for a, b in spans for ln in job[a:b].split(b"\n")),
           "skeleton_bytes": len(skeleton)}
    n = len(records)
    res["pass"] = (res["wrapper_head_equals_S1_minus_name_bpp_ret"] and res["wrapper_tail_equals_S1"]
                   and res["setpagedevice_equals_F"] and res["showpage_lines"] == 1
                   and res["image_operators"] == n == res["gsave"] == res["grestore"]
                   == res["setcolorspace_lines"] and res["EOJ"] and res["non_ascii_bytes_after_wrapper"] == 0
                   and res["data_lines_starting_with_percent"] == 0)
    return res


def data_roundtrip(job: bytes, records: list[dict], images: list[dict]) -> dict:
    ok = 0
    for (a, b), img in zip(data_spans(records), images):
        ok += base64.a85decode(job[a:b - 3], adobe=False, ignorechars=b" \n") == img["raster"].tobytes()
    return {"images": len(images), "ascii85_decodes_to_raster": ok, "pass": ok == len(images)}


def sizes(job: bytes, records: list[dict]) -> dict:
    big = max(records, key=lambda r: r["data_bytes_ascii85"])
    return {"job_bytes": len(job), "images": len(records),
            "data_bytes_raw_total": sum(r["data_bytes_raw"] for r in records),
            "data_bytes_ascii85_total": sum(r["data_bytes_ascii85"] for r in records),
            "largest_image": {k: big[k] for k in ("image", "xywh_dots", "data_bytes_raw",
                                                  "data_bytes_ascii85")},
            "per_image_ascii85": {r["image"]: r["data_bytes_ascii85"] for r in records}}


def readout_dry_run(manifest12: Path, man11_path: Path) -> dict:
    """The readout's loaders (no scan) on the S12 manifest, against the same loaders on S11's."""
    from measure.e041_mixture_readout import cell_fractions, load_manifest, patch_arrays, patterns_path
    from measure.e041_probe_readout import Geometry, footprints_mm
    out: dict = {}
    loaded = {}
    for name, path in (("S12", manifest12), ("S11", man11_path)):
        man = load_manifest(path)
        npz_path = patterns_path(path, man, None)
        pp = man["patch_px"]
        g = Geometry(25.4 / float(man["dpi"]), int(pp["pattern_dots"]), int(pp["solid_dots"]), 1, 1)
        with np.load(npz_path) as npz:
            arrs = {p["id"]: patch_arrays(npz, p, g.pattern_dots) for p in man["patches"]}
        fr = [cell_fractions(pl, int(p["cells"]), int(p["cell_dots"])).shape
              for p, (_, pl) in zip(man["patches"], arrs.values())]
        loaded[name] = arrs
        out[name] = {"patterns_path": str(npz_path), "patches": len(arrs),
                     "footprints": len(footprints_mm(man, g)),
                     "cell_fraction_shapes": sorted({str(s) for s in fr}),
                     "methods": sorted({p["method"] for p in man["patches"]})}
    same = all(np.array_equal(loaded["S12"][k][0], loaded["S11"][k][0])
               and np.array_equal(loaded["S12"][k][1], loaded["S11"][k][1]) for k in loaded["S11"])
    out["arrays_identical_S12_vs_S11"] = same and loaded["S12"].keys() == loaded["S11"].keys()
    out["pass"] = (out["arrays_identical_S12_vs_S11"]
                   and out["S12"]["patterns_path"] == out["S11"]["patterns_path"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--s11", required=True, type=Path, help="the S11 manifest (its patterns npz beside it)")
    ap.add_argument("--out", required=True, type=Path, help="job path (.ps); <stem>.manifest.json beside it")
    ap.add_argument("--s1", type=Path, default=None, help=f"S1 job for the byte audit (default: {S1_NAME} "
                    "beside --out)")
    ap.add_argument("--s11-job", type=Path, default=None,
                    help="S11 job for the gpcl6 comparison (default: the S11 manifest's stem + .pclxl)")
    ap.add_argument("--verify", action="store_true", help="checks (1)-(6)")
    args = ap.parse_args()
    s11_path = args.s11.resolve()
    man11, npz, npz_path, images, job, records = build(s11_path)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(job)
    manifest_path = args.out.with_name(args.out.stem + ".manifest.json")
    if manifest_path.parent.resolve() != npz_path.parent.resolve():
        raise SystemExit("the S12 manifest must sit beside the S11 patterns npz (referenced, not copied)")
    manifest = s12_manifest(man11, job, records, s11_path, npz_path)
    manifest_path.write_text(json.dumps({**manifest, "verification": "not run"}, indent=1) + "\n")
    if args.verify:
        s11_job = args.s11_job or s11_path.with_name(s11_path.name.replace(".manifest.json", ".pclxl"))
        if sha(s11_job.read_bytes()) != man11["sha256"]:
            raise SystemExit(f"{s11_job}: sha256 differs from the S11 manifest")
        v: dict = {}
        v["0_images_vs_S11_plan"] = against_s11_plan(images)
        v["1_render"] = render_checks(args.out, images, man11, manifest, npz, s11_job)
        v["1_ascii85_roundtrip"] = data_roundtrip(job, records, images)
        v["2_guards"] = guard_checks(job, images)
        v["3_byte_audit"] = byte_audit(job, records, (args.s1 or args.out.with_name(S1_NAME)).read_bytes())
        v["4_sizes"] = sizes(job, records)
        again = build(s11_path)
        v["5_two_builds_identical"] = {"job": again[4] == job, "records": again[5] == records,
                                       "manifest": s12_manifest(again[0], again[4], again[5], s11_path,
                                                                again[2]) == manifest}
        v["6_readout_loaders"] = readout_dry_run(manifest_path, s11_path)
        v["pass"] = all([v["0_images_vs_S11_plan"]["pass"], v["1_render"]["pass"],
                         v["1_ascii85_roundtrip"]["pass"], v["2_guards"]["pass"], v["3_byte_audit"]["pass"],
                         all(v["5_two_builds_identical"].values()), v["6_readout_loaders"]["pass"]])
        manifest["verification"] = v
        manifest_path.write_text(json.dumps(manifest, indent=1, default=list) + "\n")
        print(json.dumps(v, indent=1, default=list))
    print(f"{args.out}: {len(job)} B sha {manifest['sha256']}")
    print(f"{manifest_path}")


if __name__ == "__main__":
    main()
