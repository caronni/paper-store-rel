#!/usr/bin/env python
"""Strict qualification for the simplified e021 platen survey.

Pass conditions measure the actual contract: one-to-one regions, exact
candidate count, mask IoU, global c, safe optional angle hints, and no extras.
Bbox overlap alone never passes.  Synthetic choices use untouched 300-series
seeds; the six real e018 platens are a separate physical count/c check.

  env/bin/python experiments/021-payload-regions/qualify_e021.py --scan-root <evidence>
  env/bin/python experiments/021-payload-regions/qualify_e021.py --skip-real

--scan-root stands for the old scratch/ root (e018/*.tiff and the two
full-sheet scans, in the evidence archive).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import tifffile
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from paperholo import platen  # noqa: E402


INK, PAPER, BACK = 68.0, 226.0, 40.0
REPORT: dict = {}


def field(cell_px: int, n_px: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = n_px // cell_px
    bits = rng.random((n, n)) < 0.5
    return np.where(
        np.kron(bits, np.ones((cell_px, cell_px), bool)), INK, PAPER
    ).astype(np.float32)


def scene(
    pieces: list[tuple[np.ndarray, np.ndarray, tuple[int, int]]],
    *,
    shape: tuple[int, int],
    blur: float,
    noise: float,
    seed: int,
) -> tuple[np.ndarray, list[np.ndarray]]:
    canvas = np.full(shape, BACK, np.float32)
    truths: list[np.ndarray] = []
    for image, payload_mask, (y0, x0) in pieces:
        h = min(image.shape[0], shape[0] - y0)
        w = min(image.shape[1], shape[1] - x0)
        canvas[y0:y0 + h, x0:x0 + w] = image[:h, :w]
        truth = np.zeros(shape, bool)
        truth[y0:y0 + h, x0:x0 + w] = payload_mask[:h, :w]
        truths.append(truth)
    rng = np.random.default_rng(seed)
    canvas = ndimage.gaussian_filter(canvas, blur)
    canvas += rng.normal(0.0, noise, canvas.shape)
    return np.clip(canvas, 0.0, 255.0), truths


def rotate_payload(
    payload: np.ndarray, angle_deg: float
) -> tuple[np.ndarray, np.ndarray]:
    image = ndimage.rotate(
        payload, angle_deg, reshape=True, order=1, mode="constant", cval=BACK
    )
    mask = ndimage.rotate(
        np.ones(payload.shape, np.uint8), angle_deg, reshape=True, order=0,
        mode="constant", cval=0,
    ) > 0
    return image, mask


def prediction_masks(
    survey: platen.PayloadSurvey, shape: tuple[int, int]
) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for region in survey.regions:
        dense = np.zeros(shape, bool)
        y0, x0, h, w = region.bbox
        dense[y0:y0 + h, x0:x0 + w] = region.mask[:h, :w]
        out.append(dense)
    return out


def assignment_metrics(
    survey: platen.PayloadSurvey, truths: list[np.ndarray]
) -> dict:
    predictions = prediction_masks(survey, truths[0].shape)
    iou = np.zeros((len(truths), len(predictions)), np.float64)
    for truth_index, truth in enumerate(truths):
        for pred_index, prediction in enumerate(predictions):
            union = int((truth | prediction).sum())
            iou[truth_index, pred_index] = (
                int((truth & prediction).sum()) / max(union, 1)
            )
    if truths and predictions:
        rows, cols = linear_sum_assignment(-iou)
        matched = [float(iou[row, col]) for row, col in zip(rows, cols)]
    else:
        matched = []
    fill_eligible_hole_pixels = 0
    for region in survey.regions:
        radius_px = (
            platen.SUPPORT_HOLE_RADIUS_CELLS * survey.cell_pitch_px
            if survey.cell_pitch_px is not None else 1.0
        )
        cleaned = platen._support_mask(region.mask, radius_px)
        fill_eligible_hole_pixels += int((cleaned & ~region.mask).sum())
    return {
        "truth_regions": len(truths),
        "returned_regions": len(predictions),
        "extras": max(0, len(predictions) - len(truths)),
        "misses": max(0, len(truths) - len(predictions)),
        "matched_iou": [round(value, 4) for value in matched],
        "min_iou": round(min(matched), 4) if matched else 0.0,
        "mean_iou": round(float(np.mean(matched)), 4) if matched else 0.0,
        "fill_eligible_hole_pixels": fill_eligible_hole_pixels,
    }


def exact_ok(metrics: dict, min_iou: float) -> bool:
    return (
        metrics["extras"] == 0
        and metrics["misses"] == 0
        and metrics["returned_regions"] == metrics["truth_regions"]
        and metrics["min_iou"] >= min_iou
        and metrics["fill_eligible_hole_pixels"] == 0
    )


def cell_grid_fill_eligible_holes(survey: platen.PayloadSurvey) -> int:
    """Cheap real-scan topology check at about one sample per measured cell."""
    if survey.cell_pitch_px is None:
        return 0
    stride = max(1, int(round(survey.cell_pitch_px)))
    holes = 0
    for region in survey.regions:
        sampled = region.mask[::stride, ::stride]
        cleaned = platen._support_mask(
            sampled, platen.SUPPORT_HOLE_RADIUS_CELLS
        )
        holes += int((cleaned & ~sampled).sum())
    return holes


def q1_heldout_masks() -> bool:
    """Held-out exact masks: margins, rotations, faintness, close pieces."""
    dpi = 1600.0
    rows = []

    payload = field(8, 1400, 301)
    margin = 40
    scrap = np.full(
        (payload.shape[0] + 2 * margin, payload.shape[1] + 2 * margin),
        PAPER, np.float32,
    )
    scrap[margin:-margin, margin:-margin] = payload
    payload_mask = np.zeros(scrap.shape, bool)
    payload_mask[margin:-margin, margin:-margin] = True
    canvas, truths = scene(
        [(scrap, payload_mask, (300, 300))], shape=(2400, 2400),
        blur=2.0, noise=5.0, seed=302,
    )
    survey = platen.detect_payload_regions(canvas, dpi=dpi)
    metrics = assignment_metrics(survey, truths)
    rows.append({
        "case": "white-margin-on-dark", **metrics,
        "c": survey.c_dots, "ok": exact_ok(metrics, 0.90)
        and survey.c_dots == 3,
    })

    pieces = []
    for index, (angle, position) in enumerate(zip(
        (7.0, 27.0, 41.0),
        ((250, 250), (250, 2300), (2300, 1100)),
    )):
        image, mask = rotate_payload(field(8, 1200, 303 + index), angle)
        pieces.append((image, mask, position))
    canvas, truths = scene(
        pieces, shape=(4400, 4400), blur=2.0, noise=5.0, seed=306
    )
    survey = platen.detect_payload_regions(canvas, dpi=dpi)
    metrics = assignment_metrics(survey, truths)
    rows.append({
        "case": "three-rotations", **metrics,
        "c": survey.c_dots, "ok": exact_ok(metrics, 0.82)
        and survey.c_dots == 3,
    })

    healthy = field(8, 1400, 307)
    faint = ndimage.gaussian_filter(
        133.0 + (field(8, 1400, 308) - 147.0) * 0.35, 4.0
    )
    canvas, truths = scene(
        [
            (healthy, np.ones(healthy.shape, bool), (300, 300)),
            (faint, np.ones(faint.shape, bool), (300, 2000)),
        ],
        shape=(2200, 3800), blur=1.5, noise=5.0, seed=309,
    )
    survey = platen.detect_payload_regions(canvas, dpi=dpi)
    metrics = assignment_metrics(survey, truths)
    rows.append({
        "case": "healthy-plus-faint", **metrics,
        "c": survey.c_dots, "ok": exact_ok(metrics, 0.80)
        and survey.c_dots == 3,
    })

    first = field(8, 1200, 310)
    second = field(8, 1200, 311)
    gap_px = int(round(0.4 * dpi / 25.4))
    canvas, truths = scene(
        [
            (first, np.ones(first.shape, bool), (400, 400)),
            (second, np.ones(second.shape, bool),
             (400, 400 + first.shape[1] + gap_px)),
        ],
        shape=(2200, 400 + first.shape[1] * 2 + gap_px + 800),
        blur=2.0, noise=5.0, seed=312,
    )
    survey = platen.detect_payload_regions(canvas, dpi=dpi)
    metrics = assignment_metrics(survey, truths)
    rows.append({
        "case": "0.4mm-gap", **metrics,
        "c": survey.c_dots, "ok": exact_ok(metrics, 0.80)
        and survey.c_dots == 3,
    })

    REPORT["q1_heldout_masks"] = rows
    ok = all(row["ok"] for row in rows)
    print("Q1 held-out one-to-one masks:", "PASS" if ok else "FAIL")
    for row in rows:
        print(
            f"  {row['case']:22s} n={row['returned_regions']}/"
            f"{row['truth_regions']} extra={row['extras']} "
            f"miss={row['misses']} minIoU={row['min_iou']:.3f} c={row['c']}"
        )
    return ok


def q2_c_and_angle_matrix() -> bool:
    """One common c per platen; every emitted hint must be right."""
    rows = []
    hint_count = 0
    for index, (c_dots, angle) in enumerate(
        ((1, 10.0), (2, 25.0), (3, 40.0), (8, 15.0), (12, 33.0))
    ):
        cell_px = c_dots * 8  # 4800 / 600
        image, mask = rotate_payload(
            field(cell_px, 1800, 320 + index), angle
        )
        blur = 2.0 if c_dots == 1 else 6.0
        canvas, truths = scene(
            [(image, mask, (300, 300))],
            shape=(image.shape[0] + 900, image.shape[1] + 900),
            blur=blur, noise=5.0, seed=330 + index,
        )
        survey = platen.detect_payload_regions(canvas, dpi=4800.0)
        metrics = assignment_metrics(survey, truths)
        hints = [
            region.angle_hint_deg for region in survey.regions
            if region.angle_hint_deg is not None
        ]
        hint_errors = [
            abs(((hint - (-angle) + 45.0) % 90.0) - 45.0)
            for hint in hints
        ]
        hint_count += len(hints)
        row_ok = (
            exact_ok(metrics, 0.75)
            and survey.c_dots == c_dots
            and all(error < 2.0 for error in hint_errors)
        )
        rows.append({
            "truth_c": c_dots,
            "returned_c": survey.c_dots,
            "pitch_px": survey.cell_pitch_px,
            "angle_hint_deg": hints[0] if hints else None,
            "angle_error_deg": hint_errors[0] if hint_errors else None,
            **metrics,
            "ok": row_ok,
        })
    ok = all(row["ok"] for row in rows) and hint_count > 0
    REPORT["q2_c_angle_matrix"] = {
        "rows": rows, "non_none_hints": hint_count, "ok": ok,
    }
    print("Q2 global c + safe optional angles:", "PASS" if ok else "FAIL")
    for row in rows:
        print(
            f"  c{row['truth_c']:2d}->c{row['returned_c']} "
            f"pitch={row['pitch_px']!s:>8s} IoU={row['min_iou']:.3f} "
            f"angle_err={row['angle_error_deg']}"
        )
    return ok


def q3_full_sheet_and_thin_region() -> bool:
    """No dominance branch; full sheet, adjacent piece and ribbon stay separate."""
    dpi = 1600.0
    page = field(8, 2500, 340)
    side = field(8, 350, 341)
    ribbon = field(8, 1200, 342)[:32, :]
    canvas, truths = scene(
        [
            (page, np.ones(page.shape, bool), (100, 100)),
            (side, np.ones(side.shape, bool), (2650, 100)),
            (ribbon, np.ones(ribbon.shape, bool), (2750, 800)),
        ],
        shape=(3000, 3000), blur=2.0, noise=5.0, seed=343,
    )
    survey = platen.detect_payload_regions(canvas, dpi=dpi)
    metrics = assignment_metrics(survey, truths)
    hints = [region.angle_hint_deg for region in survey.regions]
    ribbon_hint_none = any(
        hint is None and region.bbox[2] < 80
        for region, hint in zip(survey.regions, hints)
    )
    # The 32-px ribbon is only four c3 cells wide; a one-cell tensor boundary
    # uncertainty has an unavoidable large fractional IoU cost. It still must
    # be uniquely owned, with >=0.50 IoU; the two 2-D regions retain >=0.80.
    shape_ok = (
        metrics["extras"] == 0
        and metrics["misses"] == 0
        and metrics["returned_regions"] == 3
        and min(metrics["matched_iou"][:2]) >= 0.80
        and metrics["matched_iou"][2] >= 0.50
    )
    ok = shape_ok and survey.c_dots == 3 and ribbon_hint_none
    REPORT["q3_full_sheet_thin"] = {
        **metrics, "c": survey.c_dots,
        "ribbon_hint_none": ribbon_hint_none, "ok": ok,
    }
    print(
        "Q3 full sheet + side piece + thin ribbon:",
        "PASS" if ok else "FAIL",
        f"n={metrics['returned_regions']}/3 minIoU={metrics['min_iou']:.3f}",
    )
    return ok


def q4_nulls_and_mixed_c() -> bool:
    """No false regions; conflicting c hypotheses produce honest c=None."""
    dpi = 1600.0
    rng = np.random.default_rng(350)
    blank = np.full((2600, 2600), BACK, np.float32)
    blank[300:1800, 300:1800] = PAPER
    blank[2100:2130, 400:2200] = PAPER
    blank += rng.normal(0.0, 5.0, blank.shape)
    null = platen.detect_payload_regions(blank, dpi=dpi)

    c3 = field(8, 1400, 351)
    c6 = field(16, 1408, 352)
    canvas, truths = scene(
        [
            (c3, np.ones(c3.shape, bool), (300, 300)),
            (c6, np.ones(c6.shape, bool), (300, 1900)),
        ],
        shape=(2400, 3600), blur=2.0, noise=5.0, seed=353,
    )
    mixed = platen.detect_payload_regions(canvas, dpi=dpi)
    metrics = assignment_metrics(mixed, truths)
    ok = (
        len(null.regions) == 0
        and null.c_dots is None
        and exact_ok(metrics, 0.80)
        and mixed.c_dots is None
        and {vote[0] for vote in mixed.pitch_votes} == {3, 6}
    )
    REPORT["q4_nulls_mixed"] = {
        "null_regions": len(null.regions),
        "mixed": metrics,
        "mixed_c": mixed.c_dots,
        "mixed_votes": mixed.pitch_votes,
        "ok": ok,
    }
    print(
        "Q4 null controls + mixed-c refusal:", "PASS" if ok else "FAIL",
        f"null={len(null.regions)} mixed_c={mixed.c_dots}",
    )
    return ok


def _real_scan(path: Path) -> np.ndarray:
    array = tifffile.TiffFile(str(path)).pages[0].asarray(out="memmap")
    if array.ndim == 3:
        return np.asarray(array[..., :3].mean(2), np.float32)
    return np.asarray(array)


def q5_real_confetti(scan_root: Path) -> bool:
    rows = []
    scans = (
        ("confetti-1", "hp-e018-canon-4800-confetti-1.tiff", 17),
        ("confetti-2", "hp-e018-canon-4800-confetti-2.tiff", 10),
        # Eight physical pieces: e019's old count of seven was an accepted
        # merge of two close scraps (the user identified it by eye).
        ("confetti-3", "hp-e018-canon-4800-confetti-3.tiff", 8),
        ("confetti-1-2nd", "hp-e018-canon-4800-confetti-1-2ndtake.tiff", 17),
        ("confetti-2-2nd", "hp-e018-canon-4800-confetti-2-2ndtake.tiff", 10),
        ("confetti-3-2nd", "hp-e018-canon-4800-confetti-3-2ndtake.tiff", 8),
    )
    for name, filename, truth_count in scans:
        path = scan_root / "e018" / filename
        survey = platen.detect_payload_regions(_real_scan(path), dpi=4800.0)
        angles = sum(
            region.angle_hint_deg is not None for region in survey.regions
        )
        row_ok = len(survey.regions) == truth_count and survey.c_dots == 3
        holes = cell_grid_fill_eligible_holes(survey)
        row_ok = row_ok and holes == 0
        rows.append({
            "scan": name,
            "physical_pieces": truth_count,
            "regions": len(survey.regions),
            "c": survey.c_dots,
            "pitch_px": survey.cell_pitch_px,
            "angle_hints": angles,
            "fill_eligible_holes_cell_grid": holes,
            "ok": row_ok,
        })
    ok = all(row["ok"] for row in rows)
    REPORT["q5_real_confetti"] = rows
    print("Q5 six real confetti platens:", "PASS" if ok else "FAIL")
    for row in rows:
        print(
            f"  {row['scan']:18s} n={row['regions']}/"
            f"{row['physical_pieces']} c={row['c']} "
            f"pitch={row['pitch_px']:.2f} hints={row['angle_hints']} "
            f"holes={row['fill_eligible_holes_cell_grid']}"
        )
    return ok


def q6_real_full_sheets(scan_root: Path) -> bool:
    rows = []
    for name, path, expected_c in (
        (
            "e016 c2 K",
            scan_root / "e016c2hp-canon4800gray.tiff",
            2,
        ),
        (
            "e017 c3 CMY",
            scan_root / "hp-e017-arch-c-canon-4800rgb-take2.tiff",
            3,
        ),
    ):
        survey = platen.detect_payload_regions(_real_scan(path), dpi=4800.0)
        holes = cell_grid_fill_eligible_holes(survey)
        angle_hints = sum(
            region.angle_hint_deg is not None for region in survey.regions
        )
        row_ok = (
            len(survey.regions) == 1
            and survey.c_dots == expected_c
            and holes == 0
        )
        rows.append({
            "scan": name,
            "regions": len(survey.regions),
            "c": survey.c_dots,
            "pitch_px": survey.cell_pitch_px,
            "angle_hints": angle_hints,
            "fill_eligible_holes_cell_grid": holes,
            "refine_tiles": survey.diagnostics.get("refine_tiles"),
            "refine_scored_cells": survey.diagnostics.get(
                "refine_scored_cells"
            ),
            "refine_grid_cells": survey.diagnostics.get(
                "refine_grid_cells"
            ),
            "ok": row_ok,
        })
    ok = all(row["ok"] for row in rows)
    REPORT["q6_real_full_sheets"] = rows
    print("Q6 real full sheets:", "PASS" if ok else "FAIL")
    for row in rows:
        print(
            f"  {row['scan']:12s} n={row['regions']} c={row['c']} "
            f"pitch={row['pitch_px']} "
            f"hints={row['angle_hints']} "
            f"holes={row['fill_eligible_holes_cell_grid']}"
        )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-real", action="store_true",
        help="skip the six native confetti scans and two full-sheet scans",
    )
    parser.add_argument("--scan-root", type=Path,
                        help="evidence dir for the real scans; required "
                             "unless --skip-real")
    args = parser.parse_args()
    if not args.skip_real and args.scan_root is None:
        parser.error("--scan-root is required unless --skip-real")
    started = time.perf_counter()
    results = {
        "q1_heldout_masks": q1_heldout_masks(),
        "q2_c_angle_matrix": q2_c_and_angle_matrix(),
        "q3_full_sheet_thin": q3_full_sheet_and_thin_region(),
        "q4_nulls_mixed": q4_nulls_and_mixed_c(),
    }
    if not args.skip_real:
        results["q5_real_confetti"] = q5_real_confetti(args.scan_root)
        results["q6_real_full_sheets"] = q6_real_full_sheets(args.scan_root)
    REPORT["summary"] = results
    REPORT["elapsed_s"] = round(time.perf_counter() - started, 1)
    output = HERE / "build/qualify_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(REPORT, indent=2))
    passed = sum(results.values())
    print(
        f"\n{passed}/{len(results)} PASS in {REPORT['elapsed_s']}s -> {output}"
    )
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
