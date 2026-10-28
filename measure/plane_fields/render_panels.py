"""Render the dead-vs-ground-truth figures from panels.npz.

Stage 2 of 2: pure PIL/numpy, touches no state and no scan.  Reads and
writes only ``scratch/plane-fields/gt-affine/``.

    cd <repo>
    PYTHONPATH=measure env/bin/python -m plane_fields.render_panels
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path("scratch/plane-fields/gt-affine")

PANEL = 512
SUB = 8
GAP = 14
LABEL_W = 372
MARGIN = 36

#: One global linear map for the scanner panels: raw 8-bit levels to
#: display levels.  Pooled 0.5/99.5 percentiles over all four crops,
#: rounded; the SAME map for every channel and every row.
RAW_LO, RAW_HI = 39.0, 201.0
#: One global linear map per plane for the sampled-value panels, over
#: all four rows (pooled 0.5/99.5 percentiles of the sampled channel).
SAMPLED_RANGE = {"C": (0.26, 0.79), "M": (0.17, 0.71), "Y": (0.16, 0.66)}
#: the scanner channel each plane's ink absorbs
EVIDENCE_CHANNEL = {"C": 0, "M": 1, "Y": 2}
CHANNEL_NAME = {"C": "red", "M": "green", "Y": "blue"}

INK_CORRECT = (158, 158, 158)
WHITE_CORRECT = (236, 236, 236)
ERR_INK_AS_WHITE = (214, 39, 40)
ERR_WHITE_AS_INK = (255, 140, 0)
NOT_PAYLOAD = (150, 190, 230)

BG = (255, 255, 255)
FG = (20, 20, 20)
MUTED = (105, 105, 105)
RULE = (185, 185, 185)

COLUMNS = (
    ("1.  WHAT THE SCANNER SAW",
     "the tile's own pixels, RGB, native 8 px/cell"),
    ("2.  SCANNER, {P}-INK EVIDENCE",
     "raw {CH} channel ({P} absorbs it; C/M/paper also contribute)"),
    ("3.  EXPECTED GROUND TRUTH",
     "the printed {P} cells, 64x64; ink = black"),
    ("4.  WHAT THE RECEIVER SAMPLED",
     "{P} channel at the fitted affine, 64x64"),
    ("5.  MISMATCH vs GROUND TRUTH",
     "production hard decision, {P} plane"),
    ("6.  IS THE INK THERE?",
     "sampled {P} value, split by ground truth"),
)
#: the same headings when a figure mixes planes across its rows
GENERIC_COLUMNS = (
    ("1.  WHAT THE SCANNER SAW",
     "the tile's own pixels, RGB, native 8 px/cell"),
    ("2.  SCANNER, INK EVIDENCE",
     "the raw channel this row's ink absorbs"),
    ("3.  EXPECTED GROUND TRUTH",
     "this row's printed cells, 64x64; ink = black"),
    ("4.  WHAT THE RECEIVER SAMPLED",
     "this row's plane at the fitted affine, 64x64"),
    ("5.  MISMATCH vs GROUND TRUTH",
     "production hard decision, this row's plane"),
    ("6.  IS THE INK THERE?",
     "sampled value, split by ground truth"),
)
#: the 16 x 16-cell detail the zoom figure crops, identical on every row
ZOOM_ORIGIN = (24, 24)
ZOOM_CELLS = 16
ZOOM_PX = PANEL // ZOOM_CELLS
OUTLINE = (60, 200, 60)


def font(size: int):
    return ImageFont.load_default(size=size)


def upsample(grid: np.ndarray) -> np.ndarray:
    return np.repeat(np.repeat(grid, SUB, axis=0), SUB, axis=1)


def scanner_rgb(rgb: np.ndarray) -> Image.Image:
    scaled = (rgb - RAW_LO) / (RAW_HI - RAW_LO)
    return Image.fromarray(
        (np.clip(scaled, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8), "RGB")


def scanner_evidence(rgb: np.ndarray, plane: str) -> Image.Image:
    channel = rgb[..., EVIDENCE_CHANNEL[plane]]
    scaled = (channel - RAW_LO) / (RAW_HI - RAW_LO)
    grey = (np.clip(scaled, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(np.dstack([grey] * 3), "RGB")


def truth_panel(gt_plane: np.ndarray) -> Image.Image:
    grey = np.where(gt_plane > 0, 25, 250).astype(np.uint8)
    return Image.fromarray(np.dstack([upsample(grey)] * 3), "RGB")


def sampled_panel(grid: np.ndarray, plane: str) -> Image.Image:
    lo, hi = SAMPLED_RANGE[plane]
    scaled = (grid - lo) / (hi - lo)
    grey = (np.clip(np.nan_to_num(scaled, nan=1.0), 0.0, 1.0) * 255.0
            + 0.5).astype(np.uint8)
    return Image.fromarray(np.dstack([upsample(grey)] * 3), "RGB")


def mismatch_panel(err: np.ndarray, valid: np.ndarray,
                   gt_plane: np.ndarray) -> tuple[Image.Image, dict]:
    out = np.zeros((64, 64, 3), np.uint8)
    out[...] = NOT_PAYLOAD
    ink = gt_plane > 0
    wrong = valid & (err > 0)
    out[valid & ink & ~wrong] = INK_CORRECT
    out[valid & ~ink & ~wrong] = WHITE_CORRECT
    out[wrong & ink] = ERR_INK_AS_WHITE
    out[wrong & ~ink] = ERR_WHITE_AS_INK
    counts = {
        "evaluated": int(valid.sum()),
        "errors": int(wrong.sum()),
        "ink_as_white": int((wrong & ink).sum()),
        "white_as_ink": int((wrong & ~ink).sum()),
        "ink_cells": int((valid & ink).sum()),
        "white_cells": int((valid & ~ink).sum()),
    }
    return Image.fromarray(upsample(out), "RGB"), counts


HIST_INK = (200, 60, 30)
HIST_WHITE = (40, 100, 180)
HIST_BINS = 64


def histogram_counts(values: np.ndarray, gt_plane: np.ndarray,
                     valid: np.ndarray, plane: str):
    lo, hi = SAMPLED_RANGE[plane]
    edges = np.linspace(lo, hi, HIST_BINS + 1)
    good = valid & np.isfinite(values)
    ink = np.histogram(values[good & (gt_plane > 0)], bins=edges)[0]
    white = np.histogram(values[good & (gt_plane == 0)], bins=edges)[0]
    total = max(1, int(good.sum()))
    return ink / total, white / total


def histogram_panel(values: np.ndarray, gt_plane: np.ndarray,
                    valid: np.ndarray, plane: str, entry: dict,
                    ymax: float, fonts) -> Image.Image:
    """Conditional distribution of the sampled value, split by the truth."""
    small, tiny = fonts
    lo, hi = SAMPLED_RANGE[plane]
    ink, white = histogram_counts(values, gt_plane, valid, plane)
    left, right, top, bottom = 68, PANEL - 16, 54, PANEL - 66
    panel = Image.new("RGB", (PANEL, PANEL), (255, 255, 255))
    draw = ImageDraw.Draw(panel)
    width = (right - left) / HIST_BINS

    def bars(series, colour):
        layer = Image.new("RGBA", (PANEL, PANEL), (0, 0, 0, 0))
        pen = ImageDraw.Draw(layer)
        for index, value in enumerate(series):
            height = (bottom - top) * min(value / ymax, 1.0)
            x = left + index * width
            pen.rectangle([x, bottom - height, x + width, bottom],
                          fill=(*colour, 120), outline=(*colour, 220))
        panel.paste(Image.alpha_composite(
            panel.convert("RGBA"), layer).convert("RGB"), (0, 0))

    bars(white, HIST_WHITE)
    bars(ink, HIST_INK)
    draw = ImageDraw.Draw(panel)
    threshold = entry["oracle"]["threshold"]
    if lo <= threshold <= hi:
        x = left + (threshold - lo) / (hi - lo) * (right - left)
        for y in range(top, bottom, 12):
            draw.line([x, y, x, y + 6], fill=(30, 30, 30), width=2)
        draw.text((x + 6, top - 2), "oracle threshold", font=tiny,
                  fill=(30, 30, 30))
    draw.rectangle([left, top, right, bottom], outline=(120, 120, 120))
    for step in range(6):
        value = lo + step * (hi - lo) / 5.0
        x = left + step * (right - left) / 5.0
        draw.line([x, bottom, x, bottom + 6], fill=(120, 120, 120))
        draw.text((x - 14, bottom + 10), f"{value:.2f}", font=tiny,
                  fill=MUTED)
    draw.text((left, bottom + 34),
              f"sampled {plane} value  (low = ink)", font=small, fill=FG)
    draw.text((6, top - 2), f"{ymax * 100:.0f}%", font=tiny, fill=MUTED)
    draw.text((6, bottom - 16), "0", font=tiny, fill=MUTED)
    draw.text((left + 6, top + 6),
              f"d' = {entry['separation']['d_prime']:.2f}", font=small,
              fill=FG)
    draw.text((left + 6, top + 26),
              f"oracle BER = {entry['oracle']['ber'] * 100:.1f}%",
              font=small, fill=MUTED)
    draw.text((left + 6, top + 46), "ground truth = INK", font=small,
              fill=HIST_INK)
    draw.text((left + 6, top + 66), "ground truth = WHITE", font=small,
              fill=HIST_WHITE)
    return panel


def framed(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.rectangle([x - 1, y - 1, x + PANEL, y + PANEL], outline=(90, 90, 90))


_PLACEMENT: dict[tuple[str, str], dict] = {}


def placement_check(arrays, tag: str, plane: str, *, reach: int = 6) -> dict:
    """Where the ink actually is, measured from the PIXELS, no fit involved.

    The raw channel the plane's ink absorbs is cross-correlated against
    the ground-truth cell map over integer pixel shifts.  Ink is dark, so
    the match is the most NEGATIVE correlation; its offset says where the
    ink landed and its magnitude says how much of the truth the channel
    carries.  Nothing here uses the fitted affine, so it is an
    independent check on both placement and presence.
    """
    key = (tag, plane)
    if key in _PLACEMENT:
        return _PLACEMENT[key]
    channel = arrays[f"rgb_{tag}"][..., EVIDENCE_CHANNEL[plane]].astype(
        np.float64)
    truth = arrays[f"gt_{tag}"][..., "CMY".index(plane)].astype(np.float64)
    grid = np.repeat(np.repeat(truth, SUB, axis=0), SUB, axis=1)
    inner = (slice(SUB, -SUB), slice(SUB, -SUB))
    reference = grid[inner] - grid[inner].mean()
    norm = np.sqrt((reference * reference).sum())
    best = None
    zero = None
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            shifted = np.roll(np.roll(channel, -dy, axis=0), -dx,
                              axis=1)[inner]
            shifted = shifted - shifted.mean()
            value = float((shifted * reference).sum()
                          / (norm * np.sqrt((shifted * shifted).sum())))
            if dy == 0 and dx == 0:
                zero = value
            if best is None or value < best[0]:
                best = (value, dy, dx)
    out = {"r": best[0], "dy_px": best[1], "dx_px": best[2],
           "r_at_zero": zero, "dy_dots": best[1] / 4.0,
           "dx_dots": best[2] / 4.0}
    _PLACEMENT[key] = out
    return out


def row_label_lines(entry: dict, counts: dict, place: dict
                    ) -> list[tuple[str, tuple]]:
    plane = entry["plane"]
    sep = entry["separation"]
    params = entry["affine_parameters_all_planes"]
    delta = (params[plane]["translation_dots_xy"][0]
             - params["C"]["translation_dots_xy"][0])
    dead = entry["band"] == "dead"
    if entry["role"].startswith("reproduction-control"):
        certified = "YES  (state cert withheld; re-certifies)"
        role = "CERTIFIED CONTROL"
    else:
        certified = "NO   (never; still fails at the fit)"
        role = "residue target"
    lines: list[tuple[str, tuple]] = [
        (f"TILE ({entry['tile_y']}, {entry['tile_x']})", FG),
        (f"band: {'DEAD' if dead else 'CLEAR'}  (tile column "
         f"{entry['tile_x']})", (190, 40, 40) if dead else (20, 110, 40)),
        (f"role: {role}", FG),
        (f"plane: {plane}", FG),
        (f"certified: {certified}", FG),
        ("", FG),
        (f"BER at fitted affine   {entry['capture_ber_at_affine'] * 100:5.2f}%",
         FG),
        (f"  (this capture, {counts['errors']}/{counts['evaluated']} cells)",
         MUTED),
    ]
    if entry["union_ber_at_affine"] is not None:
        lines.append(
            (f"  3-scan union          "
             f"{entry['union_ber_at_affine'] * 100:5.2f}%", MUTED))
    lines += [
        (f"BER at delta = 0       "
         f"{entry['capture_ber_at_zero'] * 100:5.2f}%", MUTED),
        ("", FG),
        (f"d' = {sep['d_prime']:.2f}   partial {sep['d_prime_partial']:.2f}"
         f"   AUC {sep['auc']:.3f}", FG),
        (f"mean ink / white  {sep['mean_ink']:.3f} / "
         f"{sep['mean_white']:.3f}", MUTED),
        (f"sd   ink / white  {sep['sd_ink']:.3f} / "
         f"{sep['sd_white']:.3f}", MUTED),
        (f"oracle-threshold BER  {entry['oracle']['ber'] * 100:5.2f}%", MUTED),
        ("", FG),
        (f"errors: ink read white {counts['ink_as_white']}", ERR_INK_AS_WHITE),
        (f"        white read ink {counts['white_as_ink']}", (200, 110, 0)),
        ("", FG),
        (f"fitted {plane} shift  "
         f"tx={params[plane]['translation_dots_xy'][0]:+.2f} "
         f"ty={params[plane]['translation_dots_xy'][1]:+.2f} dot", FG),
        (f"{plane} minus C in x   {delta:+.2f} dot", MUTED),
        ("", FG),
        ("PIXEL-DOMAIN CHECK (no fit involved):", FG),
        ("  ink best matches truth at (dy,dx)", MUTED),
        (f"  = ({place['dy_px']:+d}, {place['dx_px']:+d}) px = "
         f"({place['dy_dots']:+.2f}, {place['dx_dots']:+.2f}) dot", MUTED),
        (f"  correlation there   {place['r']:+.3f}", FG),
    ]
    return lines


def outline_ink(panel: Image.Image, gt_window: np.ndarray) -> None:
    pen = ImageDraw.Draw(panel)
    for cy, cx in zip(*np.nonzero(gt_window)):
        x, y = int(cx) * ZOOM_PX, int(cy) * ZOOM_PX
        pen.rectangle([x, y, x + ZOOM_PX - 1, y + ZOOM_PX - 1],
                      outline=OUTLINE, width=2)


def zoom_panels(arrays, entry: dict) -> list[Image.Image]:
    """The same five panels over a 16 x 16-cell detail, with GT outlines."""
    tag, plane = entry["tag"], entry["plane"]
    plane_index = "CMY".index(plane)
    oy, ox = ZOOM_ORIGIN
    sl = (slice(oy, oy + ZOOM_CELLS), slice(ox, ox + ZOOM_CELLS))
    px = (slice(oy * SUB, (oy + ZOOM_CELLS) * SUB),
          slice(ox * SUB, (ox + ZOOM_CELLS) * SUB))
    rgb = arrays[f"rgb_{tag}"].astype(np.float64)[px[0], px[1]]
    gt_plane = arrays[f"gt_{tag}"][..., plane_index]
    gt_window = gt_plane[sl]
    factor = ZOOM_PX * ZOOM_CELLS * SUB // (ZOOM_CELLS * SUB)

    def blow(image: Image.Image) -> Image.Image:
        return image.resize((PANEL, PANEL), Image.NEAREST)

    del factor
    mism, _ = mismatch_panel(arrays[f"err_{tag}_{plane}"],
                             arrays[f"valid_{tag}_{plane}"], gt_plane)
    sampled = sampled_panel(
        arrays[f"sampled_{tag}_{plane}"].astype(np.float64), plane)
    panels = [
        blow(scanner_rgb(rgb)),
        blow(scanner_evidence(rgb, plane)),
        blow(Image.fromarray(
            np.dstack([np.where(gt_window > 0, 25, 250).astype(np.uint8)] * 3),
            "RGB")),
        blow(sampled.crop((ox * SUB, oy * SUB, (ox + ZOOM_CELLS) * SUB,
                           (oy + ZOOM_CELLS) * SUB))),
        blow(mism.crop((ox * SUB, oy * SUB, (ox + ZOOM_CELLS) * SUB,
                        (oy + ZOOM_CELLS) * SUB))),
    ]
    for index in (0, 1, 3):
        outline_ink(panels[index], gt_window)
    return panels


def draw_row(canvas: Image.Image, draw: ImageDraw.ImageDraw, y: int,
             arrays, entry: dict, small, *, ymax: float, fonts,
             zoom: bool = False) -> dict:
    tag = entry["tag"]
    plane = entry["plane"]
    plane_index = "CMY".index(plane)
    rgb = arrays[f"rgb_{tag}"].astype(np.float64)
    gt_plane = arrays[f"gt_{tag}"][..., plane_index]
    valid = arrays[f"valid_{tag}_{plane}"]
    mism, counts = mismatch_panel(arrays[f"err_{tag}_{plane}"], valid,
                                  gt_plane)
    if zoom:
        panels = zoom_panels(arrays, entry)
    else:
        panels = [
            scanner_rgb(rgb),
            scanner_evidence(rgb, plane),
            truth_panel(gt_plane),
            sampled_panel(arrays[f"sampled_{tag}_{plane}"].astype(np.float64),
                          plane),
            mism,
            histogram_panel(arrays[f"sampled_{tag}_{plane}"].astype(
                np.float64), gt_plane, valid, plane, entry, ymax, fonts),
        ]
    x0 = MARGIN + LABEL_W + 16
    for index, panel in enumerate(panels):
        x = x0 + index * (PANEL + GAP)
        canvas.paste(panel, (x, y))
        framed(draw, x, y)
    ly = y
    place = placement_check(arrays, tag, plane)
    for text, colour in row_label_lines(entry, counts, place):
        if text:
            draw.text((MARGIN, ly), text, font=small, fill=colour)
        ly += 19
    return counts


def wrap_columns(plane: str) -> list[tuple[str, str]]:
    return [(head.replace("{P}", plane),
             sub.replace("{P}", plane).replace("{CH}", CHANNEL_NAME[plane]))
            for head, sub in COLUMNS]


def caption_lines(meta: dict) -> list[str]:
    fmt = meta["format"]
    return [
        f"Sheet I, {fmt['ref']}  (page 0, {fmt['tiles_yx'][0]}x"
        f"{fmt['tiles_yx'][1]} tiles, cell = {fmt['cell_dots']} print dots)"
        f"   --   lane {meta['lane']} = {meta['px_per_cell']} px/cell",
        f"capture {meta['capture_sha256'][:12]}...  "
        f"({Path(meta['capture_path']).name}, Canon 4800 flatbed at "
        f"{fmt['dpi']:.0f} dpi)   --   state {meta['state_sha256'][:12]}... "
        f"VERIFIED, payload {meta['payload_sha256'][:12]}...",
        "GROUND TRUTH = the generator re-run on the RECOVERED payload "
        "(the volume closed byte-exact), validated cell-exact against "
        f"{meta['validation']['checked']} certified tiles before use.",
        "GEOMETRY = the supervised 6-dof per-plane sampling affine from "
        "gt-affine-final2.json, fitted AGAINST that ground truth: a "
        "ceiling on what any registration correction could buy, not a "
        "receiver.",
        "PIXEL-DOMAIN CHECK (row labels) = the raw absorbed channel "
        "cross-correlated with the ground-truth cell map over integer "
        "pixel shifts, +/- 6 px.  Ink is dark, so the match is the most "
        "NEGATIVE correlation: its offset is where the ink landed (4 px = "
        "1 print dot at this footing) and its magnitude is how much of "
        "the printed truth that raw channel carries.  No fit is involved.",
        f"NORMALIZATION, panels 1-2: one global linear map, raw 8-bit "
        f"{RAW_LO:.0f}..{RAW_HI:.0f} -> 0..255, identical for every "
        f"channel, every panel and every row.  No tone curve, no "
        f"sharpening, no per-tile stretch.",
        "NORMALIZATION, panel 4: one global linear map per plane over all "
        "rows -- Y 0.16..0.66, C 0.26..0.79 sampled channel value, low = "
        "ink.  Panel 3 is binary.",
        "Panel 1 is resampled ONLY by the tile's own committed pose "
        "(order-1, 8x8 px per cell, pose residual 0.000 px); every other "
        "pixel operation is the production receiver's.",
    ]


def legend(draw: ImageDraw.ImageDraw, x: int, y: int, small) -> int:
    entries = [
        (INK_CORRECT, "correct, ground truth = ink"),
        (WHITE_CORRECT, "correct, ground truth = white"),
        (ERR_INK_AS_WHITE, "ERROR: printed ink read as white"),
        (ERR_WHITE_AS_INK, "ERROR: printed white read as ink"),
        (NOT_PAYLOAD, "not a payload cell (pilot / address / metadata)"),
    ]
    draw.text((x, y), "panel 5 key:", font=small, fill=FG)
    cx = x + 130
    for colour, text in entries:
        draw.rectangle([cx, y + 2, cx + 18, y + 20], fill=colour,
                       outline=(90, 90, 90))
        draw.text((cx + 26, y), text, font=small, fill=FG)
        cx += 34 + int(draw.textlength(text, font=small))
    return y + 30


def build(meta: dict, arrays, entries: list[dict], path: Path, *,
          title: str, notes: list[str], ymax: float, zoom: bool = False,
          extra_caption: list[str] | None = None) -> None:
    title_font = font(30)
    cap_font = font(17)
    head_font = font(19)
    sub_font = font(16)
    small = font(16)
    tiny = font(14)
    fonts = (small, tiny)

    columns = COLUMNS[:5] if zoom else COLUMNS
    caption = caption_lines(meta) + list(extra_caption or ())
    header_h = 44 + len(caption) * 23 + 14
    colhead_h = 52
    row_h = PANEL + 26
    notes_h = 16 + len(notes) * 23
    separators = sum(30 for entry in entries if entry.get("_separator"))
    height = (MARGIN + header_h + colhead_h + len(entries) * row_h
              + separators + 40 + notes_h + MARGIN)
    width = (MARGIN + LABEL_W + 16 + len(columns) * PANEL
             + (len(columns) - 1) * GAP + MARGIN)
    canvas = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(canvas)

    y = MARGIN
    draw.text((MARGIN, y), title, font=title_font, fill=FG)
    y += 44
    for line in caption:
        draw.text((MARGIN, y), line, font=cap_font, fill=MUTED)
        y += 23
    y += 14
    draw.line([MARGIN, y, width - MARGIN, y], fill=RULE, width=2)
    y += 12

    x0 = MARGIN + LABEL_W + 16
    planes = {entry["plane"] for entry in entries}
    generic = wrap_columns(sorted(planes)[0]) if len(planes) == 1 else None
    for index in range(len(columns)):
        x = x0 + index * (PANEL + GAP)
        head, sub = (generic[index] if generic is not None
                     else GENERIC_COLUMNS[index])
        draw.text((x, y), head, font=head_font, fill=FG)
        draw.text((x, y + 24), sub, font=sub_font, fill=MUTED)
    y += colhead_h

    for entry in entries:
        if entry.get("_separator"):
            draw.line([MARGIN, y - 8, width - MARGIN, y - 8], fill=RULE,
                      width=2)
            draw.text((MARGIN, y - 2), entry["_separator"], font=head_font,
                      fill=FG)
            y += 30
        draw_row(canvas, draw, y, arrays, entry, small, ymax=ymax,
                 fonts=fonts, zoom=zoom)
        y += row_h

    y += 10
    draw.line([MARGIN, y, width - MARGIN, y], fill=RULE, width=2)
    y += 12
    y = legend(draw, MARGIN, y, small)
    for line in notes:
        draw.text((MARGIN, y), line, font=cap_font, fill=MUTED)
        y += 23
    canvas.save(path)
    print(f"wrote {path}  ({canvas.size[0]}x{canvas.size[1]})")


def global_hist_max(arrays, entries: list[dict]) -> float:
    peak = 0.0
    for entry in entries:
        tag, plane = entry["tag"], entry["plane"]
        ink, white = histogram_counts(
            arrays[f"sampled_{tag}_{plane}"].astype(np.float64),
            arrays[f"gt_{tag}"][..., "CMY".index(plane)],
            arrays[f"valid_{tag}_{plane}"], plane)
        peak = max(peak, float(ink.max()), float(white.max()))
    return float(np.ceil(peak * 200.0) / 200.0)


def main() -> int:
    meta = json.loads((OUT / "panels.json").read_text())
    arrays = np.load(OUT / "panels.npz")
    by_key = {(row["tile_y"], row["tile_x"], row["plane"]): row
              for row in meta["tiles"]}

    y_rows = [by_key[(14, 9, "Y")], by_key[(29, 8, "Y")],
              by_key[(47, 28, "Y")], by_key[(24, 20, "Y")]]
    ymax = global_hist_max(arrays, y_rows)
    hist_note = (
        "Panel 6 is the same population panel 5 scores (the evaluated "
        "payload cells), binned over the panel-4 range with one shared "
        "vertical scale for every row; the dashed line is the best "
        "threshold an oracle could pick on these very samples.")
    notes = [
        "Rows 1-3 are dead-band residue tiles whose Y stream NEVER "
        "certified -- not in the W6 state, and not at this supervised "
        "affine either.  Row 4 is a clear-column tile that IS certified: "
        "its certificate was withheld and it re-certifies from these very "
        "pixels.",
        "Read the rows against each other.  If the dead rows' scanner "
        "crops, sampled values and ink/white histograms look like the "
        "control's, the yellow ink is there and the failure is downstream "
        "of the pixels.",
    ]
    build(meta, arrays, y_rows, OUT / "dead-vs-gt.png",
          title="Dead cells vs ground truth -- sheet I, Y plane: three "
                "never-certified dead-band tiles and one certified control",
          notes=notes, ymax=ymax, extra_caption=[hist_note])

    build(meta, arrays, y_rows, OUT / "dead-vs-gt-zoom.png",
          title="Dead cells vs ground truth, 16 x 16-cell detail -- is the "
                "yellow ink where the format says it is?",
          notes=["Green outlines mark the cells the ground truth says "
                 "carry Y ink, drawn on the scanner pixels (1, 2) and on "
                 "the receiver's samples (4).  Ink sitting inside its "
                 "outline is correctly placed.",
                 "Every row crops the SAME 16 x 16 cells (rows 24-39, "
                 "columns 24-39 of the tile) so the rows are directly "
                 "comparable; each scan pixel is drawn as a 4 x 4 block, "
                 "nearest-neighbour, no smoothing."],
          ymax=ymax, zoom=True)

    companion = [dict(by_key[(14, 9, "C")],
                      _separator="COMPANION: the SAME tile, the SAME "
                                 "pixels -- healthy plane (C) above "
                                 "failing plane (Y)"),
                 by_key[(14, 9, "Y")]]
    build(meta, arrays, companion, OUT / "dead-vs-gt-c-plane.png",
          title="Same tile, same pixels, two planes -- tile (14, 9), dead "
                "band: C decodes at 0.28%, Y fails at 9.98%",
          notes=["Columns 2-6 follow each row's own plane: for C the "
                 "scanner evidence is the RED channel (cyan ink absorbs "
                 "red), for Y it is the BLUE channel.  Panel 4's grey "
                 "scale is per-plane (C 0.26..0.79, Y 0.16..0.66).",
                 "Identical pixels, identical geometry treatment, "
                 "identical detector.  The only difference is which "
                 "plane's ink the channel carries -- and how far apart "
                 "that ink puts the two classes.",
                 hist_note],
          ymax=ymax)

    for entry in meta["tiles"]:
        name = f"tile-{entry['tag']}-{entry['plane']}.png"
        build(meta, arrays, [entry], OUT / name,
              title=f"Tile ({entry['tile_y']}, {entry['tile_x']}), plane "
                    f"{entry['plane']} -- {entry['band']} band, "
                    f"{entry['role']}",
              notes=[hist_note], ymax=ymax)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
