#!/usr/bin/env python
"""Confetti-session generator: carve ONE real e016 scan into a staged
sequence of synthetic scanner-glass PNGs (PILOTS-DESIGN §15 rehearsal).

Emulates the physical fragment-session protocol without cutting the sheet:
  - scan 1 = big pieces first (word-rich, seeds the session state);
  - every page region appears in EXACTLY ONE output PNG (pieces are
    scanned once and removed — the session must union across pieces, F13/
    tilemap, never average across scans);
  - successive scans carve progressively smaller confetti from the
    remaining area, each piece rotated by a random angle and spread out,
    non-overlapping, on a dark backing (segmentation-friendly, §15.2);
  - output footing 2400 dpi (= 8 px/cell at c2 — the 016.2 declared-
    equivalent decode footing), 8-bit grey PNG + a JSON manifest per scan
    carrying ground truth (source rect @4800 px, angle, canvas position)
    so every blind placement is auditable after the fact.

Declared fidelity limits vs a real confetti scan: razor-cut axis-aligned
rectangles (no torn edges — place.py v1 has no piece mask anyway), no
tilt/shadow/edge toner crush, and the rotation resample adds slight blur
a real scan would not have.

Usage (from repo root):
  env/bin/python experiments/016-arch3-c2-volume/gen_confetti_session.py \
      [--scan scratch/e016c2hp-canon4800gray.tiff] \
      [--out scratch/confetti_session] \
      [--schedule 45x6,25x14,12x40,8x60,6x80] [--gap-mm 6]

Determinism: all randomness flows from modulation.rng under the label
b"e016/confetti-session/v1" — same inputs => byte-identical PNGs.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from paperholo.modulation import rng  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
SRC_DPI = 4800.0
OUT_DPI = 2400.0            # 8 px/cell at c2 — the 016.2 decode footing
BACKINGS = {"dark": 40, "white": 250}
# dark = the §15.2 protocol backing sheet (paper ~200+, toner ~0-90 —
#   piece boundaries trivially separable); white = bare scanner lid (much
#   easier physical protocol; segmentation must key on INK DENSITY, since
#   piece paper ~ lid white — the harder, realistic receiver case). Same
#   rng label either way => byte-identical piece geometry, a controlled
#   A/B pair for the segmentation front end.
MM_SRC = SRC_DPI / 25.4     # source px per mm


def field_bbox(arr: np.ndarray) -> tuple[int, int, int, int]:
    """Printed-field bbox on the source scan (coarse darkness profile)."""
    ov = np.asarray(arr[::32, ::32], np.float32)
    ink = ov < 128
    rows = np.flatnonzero(ink.mean(axis=1) > 0.10)
    cols = np.flatnonzero(ink.mean(axis=0) > 0.10)
    if rows.size == 0 or cols.size == 0:
        raise SystemExit("no printed field found on the scan")
    return (int(rows[0]) * 32, int(rows[-1]) * 32 + 32, int(cols[0]) * 32,
            int(cols[-1]) * 32 + 32)


def carve(remaining: np.ndarray, s_mm: float, count: int,
          gen: np.random.Generator) -> list[tuple[int, int, int]]:
    """Carve up to `count` s_mm-square pieces (±15% jitter) from the 1-mm
    remaining mask; returns (y_mm, x_mm, side_mm) and consumes them.
    count -1 = legacy aligned raster sweep ('all', frozen: the on-disk
    real-toner fixtures regenerate byte-identically through it); -2 =
    dense 1-mm-stride greedy sweep ('sweep'): the aligned raster's
    origin-anchored grid misses every offset fit after the random stages
    fragment the field — the measured 67%-issuance binder."""
    out = []
    H, W = remaining.shape
    if count == -1:  # aligned raster sweep, stride = side
        side = max(4, int(round(s_mm)))
        for y in range(0, H - side, side):
            for x in range(0, W - side, side):
                if remaining[y:y + side, x:x + side].all():
                    remaining[y:y + side, x:x + side] = False
                    out.append((y, x, side))
        return out
    if count == -2:  # dense greedy sweep, 1-mm stride, alignment-free
        side = max(4, int(round(s_mm)))
        for y in range(0, H - side + 1):
            x = 0
            while x <= W - side:
                if remaining[y:y + side, x:x + side].all():
                    remaining[y:y + side, x:x + side] = False
                    out.append((y, x, side))
                    x += side
                else:
                    x += 1
        return out
    for _ in range(count):
        side = max(4, int(round(s_mm * (0.85 + 0.3 * gen.random()))))
        ok = None
        for _try in range(400):
            y = int(gen.integers(0, max(1, H - side)))
            x = int(gen.integers(0, max(1, W - side)))
            if remaining[y:y + side, x:x + side].all():
                ok = (y, x, side)
                break
        if ok is None:
            break
        y, x, side = ok
        remaining[y:y + side, x:x + side] = False
        out.append(ok)
    return out


def shelf_pack(sizes: list[tuple[int, int]], gap: int
               ) -> tuple[list[tuple[int, int]], int, int]:
    """Row-shelf packing of (h, w) boxes -> positions + canvas size."""
    width = max(int(1.15 * np.sqrt(sum((h + gap) * (w + gap)
                                       for h, w in sizes))),
                max(w for _, w in sizes) + 2 * gap)
    pos, x, y, shelf_h = [], gap, gap, 0
    for h, w in sizes:
        if x + w + gap > width:
            x, y = gap, y + shelf_h + gap
            shelf_h = 0
        pos.append((y, x))
        x += w + gap
        shelf_h = max(shelf_h, h)
    return pos, y + shelf_h + gap, width


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", default="scratch/e016c2hp-canon4800gray.tiff")
    ap.add_argument("--out", default="scratch/confetti_session")
    ap.add_argument("--schedule", default="45x6,25x14,12x40,8x60,8xall",
                    help="per-scan SIZEmm x COUNT (COUNT 'all' = aligned "
                         "raster-sweep, 'sweep' = dense 1-mm greedy sweep)"
                         ", comma-separated")
    ap.add_argument("--gap-mm", type=float, default=6.0)
    ap.add_argument("--backing", default="dark",
                    help="dark | white | 0-255 grey value")
    args = ap.parse_args()
    # (a --out-dpi 4800 variant was tried and MEASURED useless 2026-07-10:
    # rotated-piece mismatch 0.141 vs 0.134 at 2400 — the rotation loss on
    # real halftone is intrinsic, not a footing artifact; option removed)
    backing = (BACKINGS[args.backing] if args.backing in BACKINGS
               else int(args.backing))

    import tifffile
    src_path = ROOT / args.scan
    arr = tifffile.TiffFile(str(src_path)).pages[0].asarray(out="memmap")
    if arr.dtype == np.uint16:
        pass  # scaled at crop time
    y0f, y1f, x0f, x1f = field_bbox(arr)
    print(f"field bbox @4800: rows {y0f}..{y1f} cols {x0f}..{x1f} "
          f"({(y1f-y0f)/MM_SRC:.0f} x {(x1f-x0f)/MM_SRC:.0f} mm)",
          flush=True)
    H_mm = int((y1f - y0f) / MM_SRC)
    W_mm = int((x1f - x0f) / MM_SRC)
    remaining = np.ones((H_mm, W_mm), bool)
    gen = rng(b"paper-store/exp016-arch3", b"e016/confetti-session/v1")
    outdir = ROOT / args.out
    outdir.mkdir(parents=True, exist_ok=True)
    mm_out = OUT_DPI / 25.4
    gap_px = int(args.gap_mm * mm_out)
    session = []

    for si, part in enumerate(args.schedule.split(","), start=1):
        s_mm, cnt = part.strip().split("x")
        cnt_i = {"all": -1, "sweep": -2}.get(cnt)
        rects = carve(remaining, float(s_mm),
                      int(cnt) if cnt_i is None else cnt_i, gen)
        if not rects:
            print(f"scan {si}: nothing left to carve at {s_mm} mm — stop",
                  flush=True)
            break
        pieces, sizes, metas = [], [], []
        for (ym, xm, side) in rects:
            sy0 = y0f + int(ym * MM_SRC)
            sx0 = x0f + int(xm * MM_SRC)
            n = int(side * MM_SRC)
            crop = np.asarray(arr[sy0:sy0 + n, sx0:sx0 + n], np.float32)
            if arr.dtype == np.uint16:
                crop /= 257.0
            ang = float(gen.uniform(0.0, 360.0))
            # v2 fixture (2026-07-10 mitigation): rotate FIRST, at the
            # 4800 dpi source footing with cubic interpolation, THEN
            # box-decimate to the output footing — the lossy resample
            # happens where features are 2x larger relative to the
            # kernel, and the area-average launders interpolation noise.
            # (v1 decimated first and rotated order-1 at 8 px/cell — the
            # measured session-yield killer, 52/1387 symbols.)
            rot = ndimage.rotate(crop, ang, reshape=True, order=3,
                                 cval=backing, mode="constant")
            h2 = (rot.shape[0] // 2) * 2
            w2 = (rot.shape[1] // 2) * 2
            rot = rot[:h2, :w2].reshape(h2 // 2, 2, w2 // 2, 2
                                        ).mean(axis=(1, 3))  # 4800->2400
            pieces.append(np.clip(rot, 0, 255).astype(np.uint8))
            sizes.append(rot.shape)
            metas.append({"src_rect_4800": [sy0, sx0, n, n],
                          "side_mm": side, "angle_deg": round(ang, 2)})
        order = gen.permutation(len(pieces))
        pos, ch, cw = shelf_pack([sizes[i] for i in order], gap_px)
        canvas = np.full((ch, cw), backing, np.uint8)
        for (py, px), i in zip(pos, order):
            p = pieces[i]
            canvas[py:py + p.shape[0], px:px + p.shape[1]] = p
            metas[i]["canvas_yx"] = [int(py), int(px)]
        name = f"confetti_scan{si:02d}"
        Image.fromarray(canvas).save(outdir / f"{name}.png",
                                     dpi=(OUT_DPI, OUT_DPI))
        cov = 100 * (1 - remaining.mean())
        area = sum(m["side_mm"] ** 2 for m in metas)
        session.append({"scan": name, "pieces": len(metas),
                        "piece_mm_nominal": float(s_mm),
                        "area_mm2": area, "canvas_px": [ch, cw],
                        "manifest": metas})
        print(f"scan {si}: {len(metas)} pieces @~{s_mm}mm "
              f"({area} mm2), canvas {ch}x{cw}px, cumulative field "
              f"consumed {cov:.1f}%", flush=True)

    top = {"source_scan": str(args.scan),
           "source_sha256": hashlib.sha256(
               src_path.read_bytes()).hexdigest(),
           "out_dpi": OUT_DPI, "backing_grey": backing,
           "rotation": "v2: order-3 at 4800 dpi source, then 2x2 box "
                       "decimate (v1 = decimate-then-rotate order-1)",
           "field_bbox_4800": [y0f, y1f, x0f, x1f],
           "field_consumed_frac": round(1 - float(remaining.mean()), 4),
           "rng_label": "e016/confetti-session/v1", "scans": session}
    (outdir / "session_manifest.json").write_text(json.dumps(top, indent=1))
    print(f"\nmanifest -> {outdir/'session_manifest.json'}; field consumed "
          f"{100*top['field_consumed_frac']:.1f}% "
          f"(leftover stays un-issued — the fountain's problem)",
          flush=True)


if __name__ == "__main__":
    main()
