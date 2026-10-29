"""OCR confusion test for the R1 data leaf (no hardware): which monospace face
and which glyph set does a phone-style OCR read with the fewest retries?

For each (font, alphabet) a synthetic data leaf of 48 lines is set in the
REAL data-page layout of render_pdf.py (CELL_MM 2.35 cells, the line number
right-aligned in two cells, groups of 5 with half a cell between them, one
full cell, the 4-glyph check in the fixed check column, line pitch 4.318 mm
from a 10 mm margin; the face sized so 'M' fills one cell, as
render_pdf.font_for_width does).  Each leaf is rendered at twice the shot's
resolution, put through a phone-capture model (rotation + perspective by a
homography, area downsample, Gaussian blur, illumination gradient, additive
noise, JPEG 85; the homography, blur and photometry of bootstrap/r2/camera.py)
and read by tesseract 5 (LSTM, psm 6), once with no whitelist (the primary
condition: a phone's OCR has none) and once whitelisted to the alphabet.

OCR text is aligned to the truth line by line (a monotone line matching by
difflib ratio, then a Levenshtein alignment per matched line) over the TYPED
string of a line: its glyphs and its check, spaces removed, the line number
dropped.  Metrics: substitutions (truth -> read), insertions, deletions,
glyph error rate, line error rate (a line with any error = one retry).
STRICT compares case-sensitively (a.py today: "a capital is a typo"); FOLDED
maps the read text to the alphabet's case first (what a case-folding loader
would accept).

Every seed is explicit: leaf content per alphabet (LEAF_SEED), geometry and
noise per shot (SHOT_SEED), the same across fonts and alphabets so the
comparison is paired.

Usage:  python3 ocr_confusion.py run   [--out DIR] [--workers 6] [--only FONT]
        python3 ocr_confusion.py report [--out DIR]
Outputs (derived, gitignored) under bootstrap/build/ocr/.
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
BOOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(BOOT, "r2"))
from camera import gauss_blur, homography  # noqa: E402

OUT_DEFAULT = os.path.join(BOOT, "build", "ocr")
TESSERACT = "/opt/homebrew/bin/tesseract"

FONTS: dict[str, tuple[str, int]] = {
    "Menlo": ("/System/Library/Fonts/Menlo.ttc", 0),
    "CourierNew": ("/System/Library/Fonts/Supplemental/Courier New.ttf", 0),
    "AndaleMono": ("/System/Library/Fonts/Supplemental/Andale Mono.ttf", 0),
    "PTMono": ("/System/Library/Fonts/Supplemental/PTMono.ttc", 0),
    "SFMono": ("/System/Library/Fonts/SFNSMono.ttf", 0),
    "OCRB": (os.path.join(OUT_DEFAULT, "fonts", "ocrb-2015-10-27", "OCR-B-Regular.otf"), 0),
    # the standard's own glyphs: Matthew Skala's Tsukurimashou OCR-B from Norbert Schwarz's
    # METAFONT (Debian fonts-ocr-b 0.3.1, public domain / permissive); outside git by path
    "OCRBstd": ("scratch/fonts/fonts-ocr-b-0.3.1/OCRB.otf", 0),
}
A32 = "0123456789abcdefghjkmnpqrstvwxyz"
B36 = "0123456789abcdefghijklmnopqrstuvwxyz"
ALPHABETS: dict[str, str] = {"A32L": A32, "A32U": A32.upper(), "B36U": B36.upper(), "B36L": B36}

# the data page's geometry (render_pdf.py, 300 dpi: MARGIN 118 px, pitch 51 px, cell 2.35 mm)
DPI_REF = 300
MARGIN_MM = int(10 / 25.4 * DPI_REF) / DPI_REF * 25.4
PITCH_MM = ((int(297 / 25.4 * DPI_REF) - 2 * int(10 / 25.4 * DPI_REF)) // 64) / DPI_REF * 25.4
CELL_MM = 2.35
PAGE_W_MM, PAGE_H_MM = 210.0, 297.0
N_LINES, GLYPHS_FULL, GLYPHS_LAST, CHECK_GLYPHS = 48, 60, 56, 4
LEAF_SEED = 20261021

# the capture model (camera.py "nominal" photometry; the whole-page phone-camera shot 3072 px / 210 mm)
SCALES_PX_PER_MM: dict[str, float] = {"whole": 3072 / 210.0, "half": 29.0}
BLURS_PX: tuple[float, ...] = (0.6, 1.0, 1.4)
OVERSAMPLE = 2
PAPER, INK, BACKGROUND = 0.80, 0.10, 0.30
ILLUM, NOISE_OF_255, JPEG_QUALITY = 0.20, 10.0, 85
ROTATE_DEG_RANGE, PERSP_FRAC_RANGE = (1.0, 2.0), (0.01, 0.02)
SHOT_SEED = 7100
PAD_MM = 6.0


@dataclass(frozen=True)
class Shot:
    font: str
    alphabet: str
    scale: str
    blur_px: float
    part: int            # 0 = whole page; 1/2 = upper/lower half (lines 1-24 / 25-48)
    whitelist: bool
    noise_of_255: float = NOISE_OF_255


def leaf_lines(alphabet: str) -> list[tuple[str, str]]:
    """48 (glyphs, check) pairs; each glyph of the alphabet drawn equally often
    (a seeded shuffle of the alphabet repeated)."""
    n_glyphs = (N_LINES - 1) * GLYPHS_FULL + GLYPHS_LAST + N_LINES * CHECK_GLYPHS
    rng = np.random.default_rng(LEAF_SEED + len(alphabet))
    reps = -(-n_glyphs // len(alphabet))
    pool = np.array(list(range(len(alphabet))) * reps, dtype=np.int64)
    rng.shuffle(pool)
    seq = "".join(alphabet[i] for i in pool[:n_glyphs])
    out, k = [], 0
    for i in range(N_LINES):
        n = GLYPHS_LAST if i == N_LINES - 1 else GLYPHS_FULL
        out.append((seq[k:k + n], seq[k + n:k + n + CHECK_GLYPHS]))
        k += n + CHECK_GLYPHS
    return out


def font_size_pt_ref(path: str, index: int) -> int:
    """render_pdf.font_for_width(cell px, 1) at 300 dpi: the largest size whose 'M' fits a cell."""
    cell_px = int(CELL_MM / 25.4 * DPI_REF)
    size = 10
    while ImageFont.truetype(path, size + 1, index=index).getlength("M") <= cell_px:
        size += 1
    return size


def line_cells(num: int, glyphs: str, check: str) -> list[tuple[float, str]]:
    """(x in cells from the margin, char) for one data line, render_pdf.data_page's layout."""
    out: list[tuple[float, str]] = []
    x = 0.0
    for ch in str(num).rjust(2):
        out.append((x, ch))
        x += 1
    x += 1
    for g in range(0, len(glyphs), 5):
        for ch in glyphs[g:g + 5]:
            out.append((x, ch))
            x += 1
        x += 0.5
    x = max(x + 0.5, 2 + 1 + 12 * 5.5 + 0.5)
    for ch in check:
        out.append((x, ch))
        x += 1
    return out


def render_window(font: str, alphabet: str, px_per_mm: float, y0_mm: float, y1_mm: float) -> np.ndarray:
    """The leaf's band y0..y1 mm across the full page width, ink = 0 / paper = 255."""
    path, index = FONTS[font]
    size = font_size_pt_ref(path, index) * px_per_mm / (DPI_REF / 25.4)
    f = ImageFont.truetype(path, size, index=index)
    w_px, h_px = int(round(PAGE_W_MM * px_per_mm)), int(round((y1_mm - y0_mm) * px_per_mm))
    im = Image.new("L", (w_px, h_px), 255)
    d = ImageDraw.Draw(im)
    cell_px = CELL_MM * px_per_mm
    for i, (glyphs, check) in enumerate(leaf_lines(ALPHABETS[alphabet])):
        y_mm = MARGIN_MM + (i + 1) * PITCH_MM
        if not (y0_mm - PITCH_MM <= y_mm <= y1_mm):
            continue
        y_px = (y_mm - y0_mm) * px_per_mm
        for xc, ch in line_cells(i + 1, glyphs, check):
            x_px = MARGIN_MM * px_per_mm + xc * cell_px + (cell_px - f.getlength(ch)) / 2
            d.text((x_px, y_px), ch, font=f, fill=0)
    return np.asarray(im)


def part_window_mm(part: int) -> tuple[float, float, range]:
    """(y0, y1) of the shot in page mm and the 0-based truth lines it holds."""
    top = MARGIN_MM + PITCH_MM - PAD_MM
    mid = MARGIN_MM + 24.5 * PITCH_MM + 0.5 * PITCH_MM
    bot = MARGIN_MM + 49 * PITCH_MM + PAD_MM
    if part == 0:
        return 0.0, PAGE_H_MM, range(0, 48)
    if part == 1:
        return top, mid, range(0, 24)
    return mid, bot, range(24, 48)


def capture(ink01: np.ndarray, blur_px: float, seed: int,
            noise_of_255: float = NOISE_OF_255) -> tuple[np.ndarray, dict]:
    """Phone-capture model on a rendered window at OVERSAMPLE x the output scale:
    rotation + perspective (homography of the window's corners, camera.py's
    corner-in-a-disc displacement), area downsample, blur, gradient, noise."""
    rng = np.random.default_rng(seed)
    h, w = ink01.shape
    refl = (PAPER - (PAPER - INK) * (1.0 - ink01.astype(np.float32) / 255.0)).astype(np.float32)
    rot_deg = float(rng.uniform(*ROTATE_DEG_RANGE)) * (1 if rng.uniform() < 0.5 else -1)
    persp = float(rng.uniform(*PERSP_FRAC_RANGE))
    rot = math.radians(rot_deg)
    diag = math.hypot(w, h)
    pad = int(math.ceil(persp * diag + abs(math.sin(rot)) * max(w, h) * 0.5)) + 8
    cw, ch = w + 2 * pad, h + 2 * pad
    src = [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)]
    cx, cy = w / 2.0, h / 2.0
    dst = []
    for (x, y) in src:
        rx = cx + (x - cx) * math.cos(rot) - (y - cy) * math.sin(rot)
        ry = cy + (x - cx) * math.sin(rot) + (y - cy) * math.cos(rot)
        ang, rad = rng.uniform(0, 2 * math.pi), persp * diag * math.sqrt(rng.uniform())
        dst.append((pad + rx + rad * math.cos(ang), pad + ry + rad * math.sin(ang)))
    hm = homography(src, dst)
    hinv = np.linalg.inv(hm)
    coeffs = tuple((hinv / hinv[2, 2]).flatten()[:8])
    fim = Image.fromarray(refl, mode="F")
    warped = fim.transform((cw, ch), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BILINEAR,
                           fillcolor=BACKGROUND)
    a = np.asarray(warped, dtype=np.float32)
    a = a[: ch // OVERSAMPLE * OVERSAMPLE, : cw // OVERSAMPLE * OVERSAMPLE]
    a = a.reshape(a.shape[0] // OVERSAMPLE, OVERSAMPLE, a.shape[1] // OVERSAMPLE, OVERSAMPLE).mean(axis=(1, 3))
    a = gauss_blur(a.astype(np.float32), blur_px)
    vv, uu = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    gang = rng.uniform(0, 2 * math.pi)
    t = uu * math.cos(gang) + vv * math.sin(gang)
    t = (t - t.min()) / max(1e-9, float(t.max() - t.min()))
    a = a * (1.0 + ILLUM * (2.0 * t - 1.0)).astype(np.float32)
    a = a + rng.normal(0.0, noise_of_255 / 255.0, a.shape).astype(np.float32)
    out = np.clip(np.rint(a * 255.0), 0, 255).astype(np.uint8)
    return out, dict(seed=seed, rotate_deg=rot_deg, persp_frac_diag=persp, illum_dir_rad=gang,
                     blur_px=blur_px, noise_of_255=noise_of_255, size_px=[out.shape[1], out.shape[0]])


def shot_seed(scale: str, blur_px: float, part: int) -> int:
    return SHOT_SEED + 1000 * list(SCALES_PX_PER_MM).index(scale) + 100 * BLURS_PX.index(blur_px) + part


def shot_name(s: Shot) -> str:
    tail = "" if s.noise_of_255 == NOISE_OF_255 else f"_n{s.noise_of_255:g}"
    return f"{s.font}_{s.alphabet}_{s.scale}_b{s.blur_px:.1f}_p{s.part}{tail}"


def run_shot(args: tuple[Shot, str]) -> dict:
    s, out_dir = args
    jpg = os.path.join(out_dir, "img", shot_name(s) + ".jpg")
    meta_path = jpg[:-4] + ".json"
    if s.scale == "clean":
        jpg = jpg[:-4] + ".png"
        if not os.path.exists(jpg):
            win = render_window(s.font, s.alphabet, SCALES_PX_PER_MM["whole"], 0.0, PAGE_H_MM)
            Image.fromarray(win, mode="L").save(jpg)
            json.dump(dict(clean=True, px_per_mm=SCALES_PX_PER_MM["whole"]), open(meta_path, "w"))
    elif not os.path.exists(jpg):
        y0, y1, _ = part_window_mm(s.part)
        ppm = SCALES_PX_PER_MM[s.scale]
        win = render_window(s.font, s.alphabet, ppm * OVERSAMPLE, y0, y1)
        img, meta = capture(win, s.blur_px, shot_seed(s.scale, s.blur_px, s.part), s.noise_of_255)
        buf = io.BytesIO()
        Image.fromarray(img, mode="L").save(buf, format="JPEG", quality=JPEG_QUALITY)
        tmp = jpg + ".tmp"
        open(tmp, "wb").write(buf.getvalue())
        os.replace(tmp, jpg)
        meta.update(window_mm=[y0, y1], px_per_mm=ppm, jpeg_quality=JPEG_QUALITY)
        json.dump(meta, open(meta_path, "w"))
    cmd = [TESSERACT, jpg, "stdout", "--oem", "1", "--psm", "6", "-l", "eng",
           "--dpi", str(int(round(SCALES_PX_PER_MM.get(s.scale, SCALES_PX_PER_MM["whole"]) * 25.4)))]
    if s.whitelist:
        cmd += ["-c", "tessedit_char_whitelist=" + ALPHABETS[s.alphabet]]
    txt = subprocess.run(cmd, capture_output=True, text=True, check=True,
                         env=dict(os.environ, OMP_THREAD_LIMIT="1")).stdout
    tag = "wl" if s.whitelist else "nowl"
    open(os.path.join(out_dir, "txt", f"{shot_name(s)}_{tag}.txt"), "w").write(txt)
    return dict(shot=asdict(s), text=txt, capture=json.load(open(meta_path)))


# ---------------------------------------------------------------- alignment

def levenshtein_ops(t: str, r: str) -> list[tuple[str, str, str]]:
    """Alignment ops ('=', 'S', 'D', 'I', truth char, read char), unit costs."""
    n, m = len(t), len(r)
    dp = np.zeros((n + 1, m + 1), dtype=np.int32)
    dp[:, 0] = np.arange(n + 1)
    dp[0, :] = np.arange(m + 1)
    for i in range(1, n + 1):
        ti = t[i - 1]
        for j in range(1, m + 1):
            dp[i, j] = min(dp[i - 1, j - 1] + (ti != r[j - 1]), dp[i - 1, j] + 1, dp[i, j - 1] + 1)
    ops: list[tuple[str, str, str]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i, j] == dp[i - 1, j - 1] + (t[i - 1] != r[j - 1]):
            ops.append(("=" if t[i - 1] == r[j - 1] else "S", t[i - 1], r[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i, j] == dp[i - 1, j] + 1:
            ops.append(("D", t[i - 1], ""))
            i -= 1
        else:
            ops.append(("I", "", r[j - 1]))
            j -= 1
    return ops[::-1]


def typed_from_ocr(line: str) -> str:
    """The OCR line with every space removed (the line number stays: it is
    aligned against the truth's number and its errors are not counted)."""
    return "".join(line.split())


def line_errors(num: str, typed: str, read: str) -> list[tuple[str, str, str]]:
    """Error ops of `read` against num + typed, ops on the number and
    insertions before the first data glyph dropped (the typist does not type
    the number; a misread number is not a retry)."""
    out = []
    k = 0
    for op, a, b in levenshtein_ops(num + typed, read):
        in_num = k < len(num)
        at_boundary = op == "I" and k == len(num)
        if op != "I":
            k += 1
        if in_num or op == "=":
            continue
        # an insertion between the number and the first data glyph is counted
        # (as in the published tables) but tagged, so its share can be reported
        out.append(("IB" if at_boundary else op, a, b))
    return out


def match_lines(truth: list[str], reads: list[str]) -> list[int | None]:
    """Monotone matching of truth lines to OCR lines (cost 1 - difflib ratio;
    an unmatched truth line costs 1, an unmatched OCR line 0.3)."""
    n, m = len(truth), len(reads)
    cost = np.full((n + 1, m + 1), np.inf)
    back = np.zeros((n + 1, m + 1), dtype=np.int8)
    cost[0, :] = 0.3 * np.arange(m + 1)
    back[0, 1:] = 2
    cost[:, 0] = np.arange(n + 1)
    back[1:, 0] = 1
    sim = np.array([[difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() for b in reads]
                    for a in truth]).reshape(n, m)
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = (cost[i - 1, j - 1] + 1 - sim[i - 1, j - 1], cost[i - 1, j] + 1, cost[i, j - 1] + 0.3)
            k = int(np.argmin(c))
            cost[i, j], back[i, j] = c[k], k
    out: list[int | None] = [None] * n
    i, j = n, m
    while i > 0 and j > 0:
        k = back[i, j]
        if k == 0:
            out[i - 1] = j - 1 if sim[i - 1, j - 1] > 0.3 else None
            i, j = i - 1, j - 1
        elif k == 1:
            i -= 1
        else:
            j -= 1
    return out


MODES = ("strict", "folded", "mapped", "mapped_at")
# MAPPED_AT: mapped, and '@' -> '0' too ('@' is valid in no glyph set, so it is
# as free a look-alike as O -> 0; added on the refuter's M2, 2026-10-21).
# MAPPED: the case fold, then (base 32 only) the look-alikes the alphabet leaves
# out mapped to the glyph the leaf names ("what looks like i or l is 1, o is
# 0, u is v") -- what a loader with one str.translate would accept.  Base 36
# has no free look-alikes: its mapped mode = folded.
LOOKALIKE_LOWER = {"i": "1", "l": "1", "o": "0", "u": "v"}
LOOKALIKE_UPPER = {"I": "1", "L": "1", "O": "0", "U": "V"}


def score_text(alphabet: str, part: int, text: str) -> dict:
    """Per-shot score in each of MODES."""
    alpha = ALPHABETS[alphabet]
    upper = alpha.upper() == alpha and any(c.isalpha() for c in alpha)
    lines = leaf_lines(alpha)
    rows = list(part_window_mm(part)[2])
    typed = [lines[i][0] + lines[i][1] for i in rows]
    truth = [str(i + 1) + t for i, t in zip(rows, typed)]
    reads = [typed_from_ocr(l) for l in text.splitlines() if l.strip()]
    reads = [r for r in reads if r]
    res: dict = {}
    fold = (lambda r: r.upper()) if upper else (lambda r: r.lower())
    lookalike = str.maketrans(LOOKALIKE_UPPER if upper else LOOKALIKE_LOWER) if len(alpha) == 32 else {}
    for mode in MODES:
        rd = {"strict": reads, "folded": [fold(r) for r in reads],
              "mapped": [fold(r).translate(lookalike) for r in reads],
              "mapped_at": [fold(r).translate(lookalike).replace("@", "0") for r in reads]}[mode]
        match = match_lines(truth, rd)
        subs: dict[str, int] = {}
        n_s = n_d = n_i = n_glyph = n_ib = n_bad_ib_only = 0
        bad_lines: list[int] = []
        for k, t in enumerate(typed):
            n_glyph += len(t)
            r = rd[match[k]] if match[k] is not None else ""
            errs = line_errors(str(rows[k] + 1), t, r)
            if not errs:
                continue
            bad_lines.append(rows[k] + 1)
            n_bad_ib_only += all(op == "IB" for op, _, _ in errs)
            for op, a, b in errs:
                if op == "S":
                    n_s += 1
                    subs[a + b] = subs.get(a + b, 0) + 1
                elif op == "D":
                    n_d += 1
                elif op in ("I", "IB"):
                    n_i += 1
                    n_ib += op == "IB"
        res[mode] = dict(n_lines=len(truth), bad_lines=bad_lines, n_glyph=n_glyph, subs=subs,
                         n_sub=n_s, n_del=n_d, n_ins=n_i, n_ins_boundary=n_ib,
                         n_bad_boundary_only=n_bad_ib_only)
    res["glyph_counts"] = {c: sum(t.count(c) for t in typed) for c in alpha}
    return res


def all_shots(fonts: list[str], whitelist: bool, noise_of_255: float = NOISE_OF_255,
              scales: tuple[str, ...] = tuple(SCALES_PX_PER_MM)) -> list[Shot]:
    """The grid, plus one undegraded render per (font, alphabet): scale 'clean'
    (the whole-page scale, no capture model, lossless) = tesseract's own floor."""
    out = []
    for f in fonts:
        for a in ALPHABETS:
            if noise_of_255 == NOISE_OF_255:
                out.append(Shot(f, a, "clean", 0.0, 0, whitelist))
            for sc in scales:
                for b in BLURS_PX:
                    for p in ((0,) if sc == "whole" else (1, 2)):
                        out.append(Shot(f, a, sc, b, p, whitelist, noise_of_255))
    return out


def cmd_run(out_dir: str, workers: int, fonts: list[str], noise_of_255: float = NOISE_OF_255,
            scales: tuple[str, ...] = tuple(SCALES_PX_PER_MM)) -> None:
    for sub in ("img", "txt"):
        os.makedirs(os.path.join(out_dir, sub), exist_ok=True)
    fonts = [f for f in fonts if os.path.exists(FONTS[f][0])]
    shots = all_shots(fonts, False, noise_of_255, scales) + all_shots(fonts, True, noise_of_255, scales)
    # images first (no-whitelist pass renders), then whitelist pass reuses them
    results = []
    for batch in (shots[: len(shots) // 2], shots[len(shots) // 2:]):
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for r in ex.map(run_shot, [(s, out_dir) for s in batch]):
                r["score"] = score_text(r["shot"]["alphabet"], r["shot"]["part"], r["text"])
                results.append(r)
                print(shot_name(Shot(**r["shot"])), "wl" if r["shot"]["whitelist"] else "nowl",
                      len(r["score"]["strict"]["bad_lines"]), file=sys.stderr, flush=True)
    path = os.path.join(out_dir, "results.json")
    old = json.load(open(path)) if os.path.exists(path) else []
    new = {shot_name(Shot(**r["shot"])) + str(r["shot"]["whitelist"]) for r in results}
    keep = [r for r in old if shot_name(Shot(**r["shot"])) + str(r["shot"]["whitelist"]) not in new]
    json.dump(keep + results, open(path, "w"))
    json.dump(params(), open(os.path.join(out_dir, "params.json"), "w"), indent=1)


def params() -> dict:
    return dict(fonts={k: v[0] for k, v in FONTS.items()},
                font_size_pt_at_300dpi={k: font_size_pt_ref(*v) for k, v in FONTS.items() if os.path.exists(v[0])},
                alphabets=ALPHABETS, margin_mm=MARGIN_MM, pitch_mm=PITCH_MM, cell_mm=CELL_MM,
                leaf_seed=LEAF_SEED, shot_seed=SHOT_SEED, scales_px_per_mm=SCALES_PX_PER_MM,
                blurs_px=BLURS_PX, oversample=OVERSAMPLE, paper=PAPER, ink=INK, background=BACKGROUND,
                illum=ILLUM, noise_of_255=NOISE_OF_255, jpeg_quality=JPEG_QUALITY,
                rotate_deg_range=ROTATE_DEG_RANGE, persp_frac_range=PERSP_FRAC_RANGE, pad_mm=PAD_MM,
                tesseract=subprocess.run([TESSERACT, "--version"], capture_output=True,
                                         text=True).stdout.splitlines()[0],
                tesseract_args="--oem 1 --psm 6 -l eng --dpi <px/mm*25.4> [-c tessedit_char_whitelist=ALPHABET]")


# ---------------------------------------------------------------- report

def aggregate(results: list[dict], **key) -> dict:
    """Sum shots matching key (font, alphabet, scale, blur_px, whitelist) per mode."""
    sel = [r for r in results if all(r["shot"][k] == v for k, v in key.items())]
    agg: dict = {}
    for mode in MODES:
        a = dict(n_lines=0, n_bad=0, n_glyph=0, n_sub=0, n_del=0, n_ins=0, subs={})
        for r in sel:
            s = r["score"][mode]
            a["n_lines"] += s["n_lines"]
            a["n_bad"] += len(s["bad_lines"])
            for k in ("n_glyph", "n_sub", "n_del", "n_ins"):
                a[k] += s[k]
            for p, c in s["subs"].items():
                a["subs"][p] = a["subs"].get(p, 0) + c
        a["glyph_err"] = (a["n_sub"] + a["n_del"] + a["n_ins"]) / max(1, a["n_glyph"])
        a["line_err"] = a["n_bad"] / max(1, a["n_lines"])
        agg[mode] = a
    gc: dict[str, int] = {}
    for r in sel:
        for c, n in r["score"]["glyph_counts"].items():
            gc[c] = gc.get(c, 0) + n
    agg["glyph_counts"] = gc
    agg["n_shots"] = len(sel)
    return agg


def cmd_report(out_dir: str) -> None:
    results = json.load(open(os.path.join(out_dir, "results.json")))
    fonts = sorted({r["shot"]["font"] for r in results})
    table = []
    for wl in (False, True):
        for f in fonts:
            for a in ALPHABETS:
                for sc in ("clean",) + tuple(SCALES_PX_PER_MM):
                    for b in BLURS_PX + (None,):
                        key = dict(font=f, alphabet=a, scale=sc, whitelist=wl)
                        if b is not None:
                            key["blur_px"] = b
                        g = aggregate(results, **key)
                        if g["n_shots"]:
                            table.append(dict(key=key, agg=g))
                    g = aggregate(results, font=f, alphabet=a, whitelist=wl)
                    table.append(dict(key=dict(font=f, alphabet=a, whitelist=wl), agg=g))
    json.dump(table, open(os.path.join(out_dir, "summary.json"), "w"))
    for wl in (False, True):
        print(f"\n== whitelist={wl}: line error % (strict / folded), glyph error %, by scale/blur")
        for a in ALPHABETS:
            print(f"-- {a}")
            for f in fonts:
                cells = []
                for sc in SCALES_PX_PER_MM:
                    for b in BLURS_PX:
                        g = aggregate(results, font=f, alphabet=a, scale=sc, blur_px=b, whitelist=wl)
                        cells.append(f"{100*g['strict']['line_err']:5.1f}/{100*g['folded']['line_err']:5.1f}"
                                     f" ({100*g['strict']['glyph_err']:4.2f})")
                g = aggregate([r for r in results if r["shot"]["scale"] != "clean"],
                              font=f, alphabet=a, whitelist=wl)
                c = aggregate(results, font=f, alphabet=a, scale="clean", whitelist=wl)
                cells.insert(0, f"clean {100*c['strict']['line_err']:5.1f}/{100*c['folded']['line_err']:5.1f}")
                print(f"{f:11s} " + " | ".join(cells)
                      + f" || all {100*g['strict']['line_err']:5.1f}/{100*g['folded']['line_err']:5.1f}")


def cmd_rescore(out_dir: str) -> None:
    """Re-score results.json from the stored OCR text (no OCR run)."""
    path = os.path.join(out_dir, "results.json")
    results = json.load(open(path))
    with ProcessPoolExecutor(max_workers=6) as ex:
        scores = list(ex.map(_rescore_one, [(r["shot"]["alphabet"], r["shot"]["part"], r["text"])
                                            for r in results], chunksize=8))
    for r, sc in zip(results, scores):
        r["score"] = sc
    json.dump(results, open(path, "w"))


def _rescore_one(args: tuple[str, int, str]) -> dict:
    return score_text(*args)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("run", "report", "rescore", "tables", "compact"))
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only", nargs="*", default=list(FONTS))
    ap.add_argument("--noise", type=float, default=NOISE_OF_255, help="additive noise sigma, of 255")
    ap.add_argument("--scales", nargs="*", default=list(SCALES_PX_PER_MM))
    a = ap.parse_args(argv)
    if a.cmd == "run":
        cmd_run(a.out, a.workers, a.only, a.noise, tuple(a.scales))
    elif a.cmd == "compact":
        cmd_compact(a.out)
    elif a.cmd == "tables":
        cmd_tables(a.out)
    elif a.cmd == "rescore":
        cmd_rescore(a.out)
    else:
        cmd_report(a.out)



# ---------------------------------------------------------------- note tables

PHONE_LINES_BAD, PHONE_LINES = 17, 48           # PAPER-2026-10-20: Menlo A32L, phone OCR
TYPED_PER_LINE = GLYPHS_FULL + CHECK_GLYPHS      # a retry re-enters one line
PAIRS_LOWER = ["gq", "vy", "ij", "o0", "l1", "2z"]
PAIRS_UPPER = ["I1", "IL", "L1", "O0", "OQ", "OD", "0Q", "0D", "UV", "G6", "B8", "S5", "Z2"]


def pair_cells(agg: dict, pairs: list[str]) -> list[str]:
    s, gc = agg["strict"]["subs"], agg["glyph_counts"]
    out = []
    for p in pairs:
        a, b = p[0], p[1]
        ab, ba = s.get(a + b, 0), s.get(b + a, 0)
        na, nb = gc.get(a, 0), gc.get(b, 0)
        if not na and not nb:
            out.append("—")
            continue
        out.append(f"{ab}/{ba}" + ("" if na and nb else " (one side absent)"))
    return out


def est_line_err(eps_glyph: float, k: float) -> float:
    """ESTIMATE: line error of a 64-glyph line at per-glyph error k * eps, independent glyphs."""
    return 1.0 - (1.0 - min(1.0, k * eps_glyph)) ** TYPED_PER_LINE


def cmd_tables(out_dir: str) -> None:
    results = json.load(open(os.path.join(out_dir, "results.json")))
    for r in results:
        r["shot"].setdefault("noise_of_255", NOISE_OF_255)
    deg = [r for r in results if r["shot"]["scale"] != "clean" and r["shot"]["noise_of_255"] == NOISE_OF_255]
    n3 = [r for r in results if r["shot"]["noise_of_255"] == 3.0]
    fonts = sorted({r["shot"]["font"] for r in results})
    p_phone = PHONE_LINES_BAD / PHONE_LINES
    eps_phone = 1.0 - (1.0 - p_phone) ** (1.0 / TYPED_PER_LINE)
    ref = aggregate(deg, font="Menlo", alphabet="A32L", whitelist=False)["strict"]["glyph_err"]
    k = eps_phone / ref
    print(f"phone line err {p_phone:.3f} -> eps {eps_phone:.5f}; tesseract Menlo A32L glyph err {ref:.5f}; k {k:.4f}\n")
    for wl in (False, True):
        print(f"### whitelist={wl}\n")
        print("| alphabet | font | glyph err % (grid) | line err % (grid) | sub / del / ins | glyph err % clean | line err % clean "
              "| glyph err % noise 3 | line err % ESTIMATE (phone-scaled) |")
        print("|---|---|---|---|---|---|---|---|---|")
        for a in ALPHABETS:
            rows = []
            for f in fonts:
                g = aggregate(deg, font=f, alphabet=a, whitelist=wl)["strict"]
                c = aggregate(results, font=f, alphabet=a, scale="clean", whitelist=wl)["strict"]
                q = aggregate(n3, font=f, alphabet=a, whitelist=wl)["strict"]
                rows.append((g["glyph_err"], f, g, c, q))
            for e, f, g, c, q in sorted(rows, key=lambda x: x[0]):
                print(f"| {a} | {f} | {100*e:.2f} | {100*g['line_err']:.1f} | {g['n_sub']} / {g['n_del']} / {g['n_ins']} "
                      f"| {100*c['glyph_err']:.2f} | {100*c['line_err']:.1f} | {100*q['glyph_err']:.2f} "
                      f"| {100*est_line_err(e, k):.1f} |")
        print()
    print("### glyph err % (strict, no whitelist) per condition: whole b0.6/1.0/1.4 | half b0.6/1.0/1.4 | whole noise3 b0.6/1.0/1.4\n")
    print("| alphabet | font | " + " | ".join(f"{sc} {b}" for sc in ("whole", "half", "whole n3") for b in BLURS_PX) + " |")
    print("|---|---|" + "---|" * 9)
    for a in ALPHABETS:
        for f in fonts:
            cells = []
            for src, sc in ((deg, "whole"), (deg, "half"), (n3, "whole")):
                for b in BLURS_PX:
                    g = aggregate(src, font=f, alphabet=a, scale=sc, blur_px=b, whitelist=False)["strict"]
                    cells.append(f"{100*g['glyph_err']:.1f}")
            print(f"| {a} | {f} | " + " | ".join(cells) + " |")
    print("\n### known pairs, counts a->b / b->a (strict, no whitelist, the noise-10 grid, 9 shots' worth of lines per cell)\n")
    for a, pairs in (("A32L", PAIRS_LOWER), ("B36L", PAIRS_LOWER), ("A32U", PAIRS_UPPER), ("B36U", PAIRS_UPPER)):
        print(f"{a}: | font | " + " | ".join(pairs) + " |")
        for f in fonts:
            print(f"| {f} | " + " | ".join(pair_cells(aggregate(deg, font=f, alphabet=a, whitelist=False), pairs)) + " |")
        print()
    print("### top confusions per (font, alphabet), strict, no whitelist, noise-10 grid\n")
    for a in ALPHABETS:
        for f in fonts:
            s = aggregate(deg, font=f, alphabet=a, whitelist=False)["strict"]["subs"]
            top = sorted(s.items(), key=lambda x: -x[1])[:10]
            print(f"{a} {f}: " + ", ".join(f"{p[0]}→{p[1]} {n}" for p, n in top))
    print("\n### net typed characters, B36 vs A32 (ESTIMATE, phone-scaled line error; and raw tesseract)\n")
    a32_glyphs = (N_LINES - 1) * GLYPHS_FULL + GLYPHS_LAST
    bits = a32_glyphs * 5
    b36_glyphs = math.ceil(bits / math.log2(36))
    b36_lines = math.ceil(b36_glyphs / GLYPHS_FULL)
    print(f"A32: {a32_glyphs} glyphs + {N_LINES} x 4 check = {a32_glyphs + 4 * N_LINES}; "
          f"B36: {b36_glyphs} glyphs, {b36_lines} lines, + 4 x {b36_lines} = {b36_glyphs + 4 * b36_lines}\n")
    print("| font | case | A32 est line err % | B36 est line err % | A32 typed incl. retries | B36 typed incl. retries | B36 − A32 |")
    print("|---|---|---|---|---|---|---|")
    for f in fonts:
        for case, a32, b36 in (("upper", "A32U", "B36U"), ("lower", "A32L", "B36L")):
            pa = est_line_err(aggregate(deg, font=f, alphabet=a32, whitelist=False)["strict"]["glyph_err"], k)
            pb = est_line_err(aggregate(deg, font=f, alphabet=b36, whitelist=False)["strict"]["glyph_err"], k)
            ta = a32_glyphs + 4 * N_LINES + N_LINES * pa / (1 - pa) * TYPED_PER_LINE
            tb = b36_glyphs + 4 * b36_lines + b36_lines * pb / (1 - pb) * TYPED_PER_LINE
            print(f"| {f} | {case} | {100*pa:.1f} | {100*pb:.1f} | {ta:.0f} | {tb:.0f} | {tb-ta:+.0f} |")


def subsets(results: list[dict]) -> dict[str, list[dict]]:
    """GRID = the noise-10 grid (whole + half, three blurs); STABLE = the
    shots tesseract segments reliably: the clean render and every blur-1.4
    shot (noise 10 whole + half, noise 3 whole)."""
    for r in results:
        r["shot"].setdefault("noise_of_255", NOISE_OF_255)
    grid = [r for r in results if r["shot"]["scale"] != "clean" and r["shot"]["noise_of_255"] == NOISE_OF_255]
    stable = [r for r in results if r["shot"]["scale"] == "clean" or r["shot"]["blur_px"] == 1.4]
    return dict(grid=grid, stable=stable)


def cmd_compact(out_dir: str) -> None:
    results = json.load(open(os.path.join(out_dir, "results.json")))
    sub = subsets(results)
    fonts = sorted({r["shot"]["font"] for r in results})
    p_phone = PHONE_LINES_BAD / PHONE_LINES
    eps_phone = 1.0 - (1.0 - p_phone) ** (1.0 / TYPED_PER_LINE)
    a32_glyphs = (N_LINES - 1) * GLYPHS_FULL + GLYPHS_LAST
    b36_glyphs = math.ceil(a32_glyphs * 5 / math.log2(36))
    b36_lines = math.ceil(b36_glyphs / GLYPHS_FULL)
    for wl in (False, True):
        ks = {n: eps_phone / aggregate(rs, font="Menlo", alphabet="A32L", whitelist=wl)["strict"]["glyph_err"]
              for n, rs in sub.items()}
        print(f"\n#### whitelist={wl}; k (phone camera / tesseract, Menlo A32L strict): "
              + ", ".join(f"{n} {k:.4f}" for n, k in ks.items()) + "\n")
        print("| alphabet | font | GRID glyph err % strict / folded / mapped | GRID line err % strict / mapped "
              "| STABLE glyph err % strict / mapped | STABLE line err % strict / mapped "
              "| ESTIMATE line err % strict / mapped (STABLE, phone-scaled) |")
        print("|---|---|---|---|---|---|---|")
        for a in ALPHABETS:
            rows = []
            for f in fonts:
                g = aggregate(sub["grid"], font=f, alphabet=a, whitelist=wl)
                t = aggregate(sub["stable"], font=f, alphabet=a, whitelist=wl)
                rows.append((t["mapped"]["glyph_err"], f, g, t))
            for _, f, g, t in sorted(rows, key=lambda x: x[0]):
                print(f"| {a} | {f} | {100*g['strict']['glyph_err']:.2f} / {100*g['folded']['glyph_err']:.2f} / "
                      f"{100*g['mapped']['glyph_err']:.2f} | {100*g['strict']['line_err']:.0f} / {100*g['mapped']['line_err']:.0f} "
                      f"| {100*t['strict']['glyph_err']:.2f} / {100*t['mapped']['glyph_err']:.2f} "
                      f"| {100*t['strict']['line_err']:.0f} / {100*t['mapped']['line_err']:.0f} "
                      f"| {100*est_line_err(t['strict']['glyph_err'], ks['stable']):.0f} / "
                      f"{100*est_line_err(t['mapped']['glyph_err'], ks['stable']):.0f} |")
        if wl:
            continue
        print("\n#### B36 vs A32, typed characters incl. retries (ESTIMATE; STABLE, phone-scaled, mapped mode = "
              "each alphabet's best loader)\n")
        print(f"A32 {a32_glyphs} glyphs + 4 x {N_LINES} = {a32_glyphs + 4 * N_LINES}; "
              f"B36 {b36_glyphs} glyphs + 4 x {b36_lines} = {b36_glyphs + 4 * b36_lines}\n")
        print("| font | case | A32 line err % | B36 line err % | A32 typed | B36 typed | B36 − A32 |")
        print("|---|---|---|---|---|---|---|")
        for f in fonts:
            for case, a32, b36 in (("upper", "A32U", "B36U"), ("lower", "A32L", "B36L")):
                pa = est_line_err(aggregate(sub["stable"], font=f, alphabet=a32, whitelist=wl)["mapped"]["glyph_err"], ks["stable"])
                pb = est_line_err(aggregate(sub["stable"], font=f, alphabet=b36, whitelist=wl)["mapped"]["glyph_err"], ks["stable"])
                ta = a32_glyphs + 4 * N_LINES + N_LINES * pa / (1 - pa) * TYPED_PER_LINE
                tb = b36_glyphs + 4 * b36_lines + b36_lines * pb / (1 - pb) * TYPED_PER_LINE
                print(f"| {f} | {case} | {100*pa:.0f} | {100*pb:.0f} | {ta:.0f} | {tb:.0f} | {tb-ta:+.0f} |")
    print("\n#### per-glyph substitution rate %, STABLE, no whitelist, mapped (truth glyph -> any wrong read; "
          "opportunities = truth occurrences)\n")
    for a in ("A32U", "B36U"):
        for f in fonts:
            g = aggregate(sub["stable"], font=f, alphabet=a, whitelist=False)
            per: dict[str, int] = {}
            for pr, n in g["mapped"]["subs"].items():
                per[pr[0]] = per.get(pr[0], 0) + n
            worst = sorted(((per.get(c, 0) / max(1, g["glyph_counts"][c]), c) for c in ALPHABETS[a]), reverse=True)[:6]
            top = sorted(g["mapped"]["subs"].items(), key=lambda x: -x[1])[:8]
            print(f"- {a} {f}: worst glyphs " + ", ".join(f"{c} {100*r:.0f}" for r, c in worst)
                  + "; top pairs " + ", ".join(f"{p[0]}→{p[1]} {n}" for p, n in top))


if __name__ == "__main__":
    main()
