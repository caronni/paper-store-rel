#!/usr/bin/env python
"""Run experiment 020: structure-tensor acquisition versus e019."""
from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from paperholo import segment  # noqa: E402
import detector as tensor_detector  # noqa: E402

P = 8
DPI = 1600.0
BACK_DARK = 38.0
BACK_WHITE = 246.0
PAPER = 226.0


@dataclass(frozen=True)
class Scene:
    name: str
    image: np.ndarray
    truth: np.ndarray


def _paste_rotated(canvas, truth, patch, field_mask, centre, angle):
    backing = float(canvas[0, 0])
    rotated = ndimage.rotate(patch, angle, reshape=True, order=1,
                             mode="constant", cval=backing)
    paper_mask = ndimage.rotate(np.ones_like(patch, bool), angle, reshape=True,
                                order=0, mode="constant", cval=0)
    field_rot = ndimage.rotate(field_mask.astype(np.uint8), angle, reshape=True,
                               order=0, mode="constant", cval=0) > 0
    y0 = int(centre[0] - rotated.shape[0] // 2)
    x0 = int(centre[1] - rotated.shape[1] // 2)
    y1, x1 = y0 + rotated.shape[0], x0 + rotated.shape[1]
    sy0, sx0 = max(0, -y0), max(0, -x0)
    sy1 = rotated.shape[0] - max(0, y1 - canvas.shape[0])
    sx1 = rotated.shape[1] - max(0, x1 - canvas.shape[1])
    dy0, dx0 = max(0, y0), max(0, x0)
    dy1, dx1 = dy0 + (sy1 - sy0), dx0 + (sx1 - sx0)
    pm = paper_mask[sy0:sy1, sx0:sx1]
    target = canvas[dy0:dy1, dx0:dx1]
    target[pm] = rotated[sy0:sy1, sx0:sx1][pm]
    truth[dy0:dy1, dx0:dx1] |= field_rot[sy0:sy1, sx0:sx1]


def _piece(rng, field_cells, margin_cells, ink, *, blank=False,
           torn=False, quiet=False):
    fh, fw = field_cells
    margin = margin_cells * P
    bits = rng.random((fh, fw)) < 0.5
    field = np.where(np.kron(bits, np.ones((P, P), bool)), ink, PAPER)
    mask = np.ones_like(field, bool)
    if torn:
        yy, xx = np.mgrid[:field.shape[0], :field.shape[1]]
        cut = yy + 0.75 * xx < 0.30 * min(field.shape)
        field[cut] = PAPER
        mask[cut] = False
    if quiet:
        y0, x0 = field.shape[0] // 3, field.shape[1] // 3
        h, w = 5 * P, 7 * P
        field[y0:y0 + h, x0:x0 + w] = PAPER
        mask[y0:y0 + h, x0:x0 + w] = False
    patch = np.full((field.shape[0] + 2 * margin,
                     field.shape[1] + 2 * margin), PAPER, np.float32)
    field_mask = np.zeros_like(patch, bool)
    if not blank:
        patch[margin:margin + field.shape[0],
              margin:margin + field.shape[1]] = field
        field_mask[margin:margin + field.shape[0],
                   margin:margin + field.shape[1]] = mask
    return patch, field_mask


def make_scene(name: str, seed: int) -> Scene:
    rng = np.random.default_rng(seed)
    backing = BACK_WHITE if name == "white_lid" else BACK_DARK
    image = np.full((720, 960), backing, np.float32)
    truth = np.zeros_like(image, bool)

    if name == "edges_only":
        schedule = [((22, 24), 5, True, False, False, (230, 230), 17),
                    ((18, 30), 4, True, False, False, (470, 650), -24)]
    elif name == "dense":
        schedule = [((42, 43), 2, False, False, False, (265, 280), 13),
                    ((38, 42), 2, False, False, False, (470, 685), -21)]
    else:
        schedule = [((22, 27), 5, False, False, False, (205, 225), 17),
                    ((24, 26), 0, False, False, False, (210, 685), -26),
                    ((26, 31), 3, False, name == "torn_quiet",
                     name == "torn_quiet", (500, 355), -11),
                    ((18, 23), 5, True, False, False, (505, 760), 28)]

    ink = 132.0 if name == "faint_blurred" else 68.0
    for fc, margin, blank, torn, quiet, centre, angle in schedule:
        patch, field_mask = _piece(rng, fc, margin, ink, blank=blank,
                                   torn=torn, quiet=quiet)
        _paste_rotated(image, truth, patch, field_mask, centre, angle)

    blur = 3.5 if name == "faint_blurred" else 1.7
    image = ndimage.gaussian_filter(image, blur)
    image += rng.normal(0.0, 6.5, image.shape)
    return Scene(name, np.clip(image, 0, 255).astype(np.uint8), truth)


def _e019_mask(image):
    candidates = segment.find_lattice_candidates(
        image, cell_px=P, dpi=DPI, min_area_mm2=9.0
    )
    mask = np.zeros(image.shape, bool)
    for c in candidates:
        y, x, h, w = c.bbox
        target = mask[y:y + h, x:x + w]
        target[:c.mask.shape[0], :c.mask.shape[1]] |= c.mask[:target.shape[0],
                                                               :target.shape[1]]
    return mask, len(candidates)


def _metrics(mask, truth):
    tp = int((mask & truth).sum())
    fp = int((mask & ~truth).sum())
    fn = int((~mask & truth).sum())
    iou = tp / max(tp + fp + fn, 1)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    return iou, precision, recall, fp / mask.size


def _render(scene, masks, out):
    base = Image.fromarray(scene.image).convert("RGB")
    tiles = []
    colors = [(40, 180, 80), (60, 130, 255), (240, 90, 50)]
    labels = ["truth", "e019 local std", "e020 tensor minor eigenvalue"]
    for mask, color, label in zip(masks, colors, labels):
        tile = base.copy()
        overlay = Image.new("RGB", tile.size, color)
        alpha = Image.fromarray((mask.astype(np.uint8) * 105))
        tile.paste(overlay, mask=alpha)
        ImageDraw.Draw(tile).text((8, 8), label, fill=(255, 255, 255),
                                  stroke_width=2, stroke_fill=(0, 0, 0))
        tiles.append(tile)
    strip = Image.new("RGB", (base.width * len(tiles), base.height))
    for i, tile in enumerate(tiles):
        strip.paste(tile, (i * base.width, 0))
    strip.resize((1800, int(1800 * strip.height / strip.width))).save(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=8,
                        help="held-out seeds per scene")
    parser.add_argument("--seed-start", type=int, default=200,
                        help="first held-out seed (100-series was calibration)")
    parser.add_argument("--out", type=Path, default=HERE / "build")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    names = ["dark_margins", "white_lid", "faint_blurred", "torn_quiet",
             "edges_only", "dense"]
    rows = []
    started = time.perf_counter()
    for name in names:
        for seed in range(args.seed_start, args.seed_start + args.seeds):
            scene = make_scene(name, seed)
            e019, n019 = _e019_mask(scene.image)
            result = tensor_detector.detect(scene.image, cell_px=P, dpi=DPI)
            e020 = tensor_detector.rasterize(result, scene.image.shape)
            for detector_name, mask, count in (
                ("e019", e019, n019),
                ("e020", e020, len(result.candidates)),
            ):
                iou, precision, recall, false_area = _metrics(mask, scene.truth)
                rows.append({"scene": name, "seed": seed,
                             "detector": detector_name, "iou": iou,
                             "precision": precision, "recall": recall,
                             "false_area": false_area, "candidates": count,
                             "threshold": result.threshold
                             if detector_name == "e020" else ""})
            if seed == args.seed_start:
                _render(scene, (scene.truth, e019, e020),
                        args.out / f"{name}.png")

    with (args.out / "results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"{'scene':14s} {'detector':8s}  IoU       precision recall    "
          "false-area candidates")
    for name in names:
        for detector_name in ("e019", "e020"):
            subset = [r for r in rows if r["scene"] == name and
                      r["detector"] == detector_name]
            vals = lambda key: np.asarray([r[key] for r in subset], float)
            print(f"{name:14s} {detector_name:8s}  "
                  f"{vals('iou').mean():.3f}+/-{vals('iou').std():.3f}  "
                  f"{vals('precision').mean():.3f}     "
                  f"{vals('recall').mean():.3f}    "
                  f"{vals('false_area').mean():.4f}     "
                  f"{vals('candidates').mean():.1f}")
    print(f"wrote {args.out / 'results.csv'} and six overlays in "
          f"{time.perf_counter() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
