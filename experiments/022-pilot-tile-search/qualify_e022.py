#!/usr/bin/env python
"""Qualification battery for E022 v2 pilot-field placement.

  env/bin/python experiments/022-pilot-tile-search/qualify_e022.py
  env/bin/python experiments/022-pilot-tile-search/qualify_e022.py --skip-real

Q1  exact-field straddles over a FOUR-page legal set + adversarial nulls
    (iid, periodic-lattice, constant, wrong-page-geometry) with false
    accepts accounted over the multiplied hypothesis count;
Q2  BCH fast-start timing on the real e018 page geometry;
Q3  pose battery: rotation x subpixel origin x anisotropy x shear at
    8 / 11.7 / 23.85 px per cell, end-to-end mapping error in cells
    (the arbitrary-resolution contract: NO predecimation path exists);
Q4  wrong-seed field refusal;
Q5  local-affine limits: scanner y-step AND paper fold — component
    split, correct mappings each side, and no wrong-address observation
    leakage past the straddle audit;
Q6  real e018 scans at BOTH footings: externally decimated 1600 dpi
    (scans 1 and 3) and native 4800 dpi (scan 1). Pre-registered bars:
    every E021 region accepted (v1 left dec-3's largest region and two
    native regions unresolved), zero contradictory known-position BCH
    reads, and native tiles above the v1-native baseline (248).
"""
from __future__ import annotations

import argparse
import json
import resource
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import ndimage

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from paperholo import pilotdiag, place, pilotsearch, platen  # noqa: E402
from paperholo.formats import FormatDescriptor  # noqa: E402
from paperholo.platen import PayloadRegion, PayloadSurvey  # noqa: E402
import run_e022  # noqa: E402


REPORT: dict = {}
INK, PAPER, BACK = 45.0, 205.0, 245.0


def _format(seed: bytes, shape: tuple[int, int] = (600, 480)
            ) -> FormatDescriptor:
    return FormatDescriptor("e022-qual", seed, 3, "kcell-c3", shape)


def _page_bits(descriptor: FormatDescriptor, seed: int) -> np.ndarray:
    spec = descriptor.spec()
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, spec.page_cells_yx, dtype=np.uint8)
    values, sites = place.pilot_field(spec, descriptor.seed, 0)
    bits[sites] = values[sites]
    return bits


def _gt_jacobian(pitch_v: float, pitch_u: float, angle_deg: float,
                 shear_deg: float = 0.0) -> np.ndarray:
    a = np.deg2rad(angle_deg)
    s = np.deg2rad(angle_deg + shear_deg)
    b_v = pitch_v * np.array([np.cos(a), -np.sin(a)])
    b_u = pitch_u * np.array([np.sin(s), np.cos(s)])
    return np.stack([b_v, b_u], axis=1)


def _render_affine(bits, jac, origin_px, out_shape, rng, *,
                   blur=1.1, noise=2.0):
    yy, xx = np.indices(out_shape)
    rel = (np.stack([yy.ravel(), xx.ravel()], axis=1).astype(np.float64)
           - np.asarray(origin_px, np.float64))
    cells = np.rint(rel @ np.linalg.inv(jac).T).astype(np.int64)
    inside = ((cells[:, 0] >= 0) & (cells[:, 0] < bits.shape[0])
              & (cells[:, 1] >= 0) & (cells[:, 1] < bits.shape[1]))
    flat = np.full(out_shape[0] * out_shape[1], BACK, np.float32)
    flat[inside] = np.where(
        bits[cells[inside, 0], cells[inside, 1]] > 0, INK, PAPER)
    img = ndimage.gaussian_filter(flat.reshape(out_shape), blur)
    img += rng.normal(0.0, noise, img.shape).astype(np.float32)
    return np.clip(img, 0.0, 255.0), inside.reshape(out_shape)


def _survey_for(shape, pitch, mask):
    region = PayloadRegion((0, 0, shape[0], shape[1]), mask,
                           area_mm2=1000.0, angle_hint_deg=None, score=40.0)
    return PayloadSurvey((region,), c_dots=3, cell_pitch_px=pitch)


def _mapping_error_cells(result, jac_gt, origin_gt, scrap_origin_cells,
                         pitch) -> float:
    worst = 0.0
    for placed in result.placements:
        if placed.rot_k != 0:
            return float("inf")
        sample = placed.page_cells_yx[
            :: max(1, len(placed.page_cells_yx) // 64)]
        window_cells = sample - np.asarray(placed.origin_yx, np.int64)
        got = placed.pose.points(window_cells)
        gt_rel = sample - np.asarray(scrap_origin_cells, np.int64)
        want = (gt_rel.astype(np.float64) @ np.asarray(jac_gt).T
                + np.asarray(origin_gt, np.float64))
        worst = max(worst, float(np.max(np.hypot(*(got - want).T))) / pitch)
    return worst


def q1_exact_field_and_nulls() -> bool:
    """Exact placements over a FOUR-page legal set (cross-page rivals must
    lose), plus an adversarial null battery with false accepts accounted
    over the full multiplied hypothesis count."""
    rows = []
    correct = 0
    total = 0
    pages = (0, 1, 2, 3)
    for case, (shape, origin, page_no) in enumerate((
        ((90, 90), (175, 177), 0),    # four-pilot-tile corner
        ((120, 150), (59, 241), 2),   # boundary mix, non-zero page
        ((160, 140), (360, 300), 3),  # large interior support
    )):
        descriptor = _format(f"paper-store/e022-q1-{case}".encode())
        spec = descriptor.spec()
        rng = np.random.default_rng(2300 + case)
        bits_page = rng.integers(0, 2, spec.page_cells_yx, dtype=np.uint8)
        values, sites = place.pilot_field(spec, descriptor.seed, page_no)
        bits_page[sites] = values[sites]
        for rot_k in range(4):
            y, x = origin
            h, w = shape
            bits = np.rot90(bits_page[y:y + h, x:x + w], -rot_k)
            config = pilotsearch.SearchConfig(
                min_support=8, gate_gap=0.06, allow_overhang=True
            )
            placed = pilotsearch.correlate_fragment(
                1.0 - 2.0 * bits.astype(np.float32),
                np.ones(bits.shape, bool), spec, descriptor.seed,
                pages=pages, pending_cell_mask=None, config=config,
            )
            ok = bool(
                placed.ok and placed.origin_yx == origin
                and placed.page == page_no
                and placed.rot_k == rot_k and placed.mismatch < 1e-5
            )
            correct += int(ok)
            total += 1
            rows.append({
                "case": case, "rot_k": rot_k, "page": page_no, "ok": ok,
                "got_page": placed.page,
                "origin": list(placed.origin_yx) if placed.origin_yx else None,
                "mismatch": placed.mismatch,
                "rival_mismatch": placed.rival_mismatch,
                "validation_mismatch": placed.diagnostics.get(
                    "validation_mismatch"),
            })

    # adversarial nulls: iid random bits at several shapes, a perfectly
    # periodic lattice with no pilot values (checkerboard), constant
    # fields, and a true fragment against a WRONG-page-geometry field
    # (the tiles_x-class hazard at field level)
    descriptor = _format(b"paper-store/e022-q1-null")
    rng = np.random.default_rng(2310)
    null_rows = []
    n_hypotheses = 0
    config = pilotsearch.SearchConfig(min_support=15)

    def _null(kind: str, bits: np.ndarray, spec, seed,
              null_pages=(0, 1, 2, 3)) -> None:
        nonlocal n_hypotheses
        placed = pilotsearch.correlate_fragment(
            1.0 - 2.0 * bits.astype(np.float32),
            np.ones(bits.shape, bool), spec, seed,
            pages=null_pages, pending_cell_mask=None, config=config,
        )
        n_hypotheses += placed.diagnostics.get("n_hypotheses", 0)
        null_rows.append({
            "kind": kind, "accepted": bool(placed.ok),
            "mismatch": placed.mismatch,
            "rival_mismatch": placed.rival_mismatch,
        })

    for trial in range(40):
        shape = ((90, 90), (120, 140), (160, 100))[trial % 3]
        _null("iid", rng.integers(0, 2, shape, dtype=np.uint8),
              descriptor.spec(), descriptor.seed)
    checker = np.indices((120, 120)).sum(axis=0) % 2
    _null("checkerboard", checker.astype(np.uint8),
          descriptor.spec(), descriptor.seed)
    _null("all_ink", np.ones((120, 120), np.uint8),
          descriptor.spec(), descriptor.seed)
    _null("all_paper", np.zeros((120, 120), np.uint8),
          descriptor.spec(), descriptor.seed)
    # wrong page WIDTH, right seed: same-seed field at (600, 420)
    true_fmt = _format(b"paper-store/e022-q1-geom")
    narrow = _format(b"paper-store/e022-q1-geom", shape=(600, 420))
    page = _page_bits(true_fmt, 2340)
    for trial in range(6):
        y = 60 + 70 * trial
        _null("wrong_page_geometry", page[y:y + 130, 97:237],
              narrow.spec(), narrow.seed)
    false_accepts = sum(row["accepted"] for row in null_rows)
    ok = correct == total and false_accepts == 0
    REPORT["q1_exact_field_and_nulls"] = {
        "correct": correct, "total": total,
        "false_accepts": false_accepts, "n_nulls": len(null_rows),
        "null_hypotheses": n_hypotheses,
        "rows": rows, "nulls": null_rows,
        "ok": ok,
    }
    print(f"Q1 exact field (4-page set) / nulls: {'PASS' if ok else 'FAIL'} "
          f"({correct}/{total}, FA={false_accepts}/{len(null_rows)} over "
          f"{n_hypotheses} hypotheses)")
    return ok


def q2_bch_fast_start() -> bool:
    descriptor = run_e022.E018
    spec = descriptor.spec()
    page = _page_bits(descriptor, 2320)
    origins = ((700, 500), (1200, 850), (300, 1050))
    config = pilotsearch.SearchConfig(
        min_support=20, bch_max_tiles=1, allow_overhang=True
    )
    rows = []
    values, sites = place.pilot_field(spec, descriptor.seed, 0)
    del values, sites
    for origin in origins:
        y, x = origin
        bits = page[y:y + 180, x:x + 180].copy()
        evidence = 1.0 - 2.0 * bits.astype(np.float32)
        mask = np.ones(bits.shape, bool)
        bch_placement, errors, bch_s = pilotsearch.try_bch_seed(
            bits, evidence, mask, spec, descriptor.seed,
            pages=(0,), config=config,
        )
        start = perf_counter()
        corr_placement = pilotsearch.correlate_fragment(
            evidence, mask, spec, descriptor.seed, pages=(0,),
            pending_cell_mask=None, config=config,
        )
        corr_s = perf_counter() - start
        rows.append({
            "origin": list(origin), "bch_s": bch_s, "correlation_s": corr_s,
            "speedup": corr_s / max(bch_s, 1e-9),
            "bch_errors": errors,
            "bch_ok": bool(bch_placement and bch_placement.ok
                           and bch_placement.origin_yx == origin),
            "correlation_ok": bool(corr_placement.ok
                                   and corr_placement.origin_yx == origin),
        })
    bch_median = float(np.median([row["bch_s"] for row in rows]))
    corr_median = float(np.median([row["correlation_s"] for row in rows]))
    speedup = corr_median / max(bch_median, 1e-9)
    use_as_starter = speedup >= 1.5
    ok = (all(row["bch_ok"] and row["correlation_ok"] for row in rows)
          and use_as_starter)
    REPORT["q2_bch_fast_start"] = {
        "rows": rows, "bch_median_s": bch_median,
        "correlation_median_s": corr_median,
        "speedup": speedup, "use_as_starter": use_as_starter, "ok": ok,
    }
    print(f"Q2 high-quality BCH starter: {'PASS' if ok else 'FAIL'} "
          f"({bch_median:.3f}s vs {corr_median:.3f}s, {speedup:.2f}x)")
    return ok


def q3_pose_battery() -> bool:
    """Rotation x subpixel x anisotropy x shear at three footings.

    The scrap has no angle hint; every recovered placement must be exact
    in address, subpixel in mapping (<0.35 cell), and affine-accurate
    (<1.2% of pitch per Jacobian entry)."""
    rows = []
    cases = [
        # (pitch, aniso_v, shear_deg, angle_deg, origin_frac)
        (8.0, 1.000, 0.00, 0.0, (0.00, 0.00)),
        (8.0, 1.003, 0.20, 17.3, (0.37, 0.61)),
        (8.0, 0.997, -0.25, -31.0, (0.71, 0.23)),
        (11.7, 1.004, 0.25, -3.6, (0.37, 0.61)),
        (11.7, 1.000, 0.00, 44.0, (0.11, 0.87)),
        (23.85, 0.997, 0.15, 2.4, (0.25, 0.75)),
        (23.85, 1.004, -0.20, -12.5, (0.50, 0.50)),
    ]
    for index, (pitch, aniso, shear, angle, frac) in enumerate(cases):
        descriptor = _format(f"paper-store/e022-q3-{index}".encode())
        rng = np.random.default_rng(2400 + index)
        page = _page_bits(descriptor, 2430 + index)
        n = 150 if pitch > 16 else 200
        scrap_origin = (120, 96)
        scrap = page[120:120 + n, 96:96 + n]
        jac_gt = _gt_jacobian(pitch * aniso, pitch, angle, shear_deg=shear)
        pad = 140
        span = int(np.ceil(n * pitch * 1.5)) + 2 * pad
        origin_gt = (pad + 40.0 + frac[0] + 0.35 * n * pitch * 0.4,
                     pad + 40.0 + frac[1] + 0.35 * n * pitch * 0.4)
        canvas, support = _render_affine(
            scrap, jac_gt, origin_gt, (span, span), rng,
            blur=(2.2 if pitch > 16 else 1.1))
        survey = _survey_for(canvas.shape, pitch, support)
        result = pilotsearch.search_survey(
            canvas, survey, descriptor,
            config=pilotsearch.SearchConfig(bch_first=False, min_support=20))
        placed = result.region_states.get(0) == "accepted"
        err = (_mapping_error_cells(result, jac_gt, origin_gt,
                                    scrap_origin, pitch)
               if placed and result.placements else float("inf"))
        jac_err = max(
            (float(np.max(np.abs(row.pose.matrix() - jac_gt)))
             for row in result.placements), default=float("inf"))
        wrong_component = any(row.rot_k != 0 for row in result.placements)
        row_ok = bool(placed and not wrong_component
                      and err < 0.35 and jac_err < 0.012 * pitch)
        rows.append({
            "pitch_px": pitch, "aniso": aniso, "shear_deg": shear,
            "angle_deg": angle, "placements": len(result.placements),
            "mapping_err_cells": err if np.isfinite(err) else None,
            "jac_err_px": jac_err if np.isfinite(jac_err) else None,
            "ok": row_ok,
        })
    ok = all(row["ok"] for row in rows)
    REPORT["q3_pose_battery"] = {"rows": rows, "ok": ok}
    print(f"Q3 pose battery (8/11.7/23.85 px/cell): "
          f"{'PASS' if ok else 'FAIL'}")
    for row in rows:
        err = row["mapping_err_cells"]
        print(f"  p={row['pitch_px']:6.2f} a={row['angle_deg']:6.1f} "
              f"aniso={row['aniso']:.3f} shear={row['shear_deg']:+.2f} "
              f"-> n={row['placements']} err="
              f"{err if err is None else round(err, 3)} "
              f"{'ok' if row['ok'] else 'FAIL'}")
    return ok


def q4_wrong_field_refusal() -> bool:
    right = _format(b"paper-store/e022-q4-right")
    wrong = _format(b"paper-store/e022-q4-wrong")
    page = _page_bits(right, 2340)
    bits = page[180:340, 140:300]
    evidence = 1.0 - 2.0 * bits.astype(np.float32)
    placed = pilotsearch.correlate_fragment(
        evidence, np.ones(bits.shape, bool), wrong.spec(), wrong.seed,
        pages=(0,), pending_cell_mask=None,
        config=pilotsearch.SearchConfig(min_support=20),
    )
    ok = not placed.ok
    REPORT["q4_wrong_field_refusal"] = {
        "accepted": bool(placed.ok), "mismatch": placed.mismatch,
        "rival_mismatch": placed.rival_mismatch, "ok": ok,
    }
    print(f"Q4 wrong seed/field refusal: {'PASS' if ok else 'FAIL'}")
    return ok


def _observation_agreement(result: pilotsearch.SearchResult
                           ) -> tuple[int, float]:
    agree = total = 0
    for tile in result.tiles.values():
        for observations in tile.observations.values():
            for obs in observations:
                agree += int(obs.bit == obs.expected)
                total += 1
    return total, agree / max(total, 1)


def q5_step_and_fold() -> bool:
    """Local-affine-limit fixtures: a scanner y-jump and a paper fold.

    Both must split into pose components, place each side correctly, and
    leak no wrong-address observations past the straddle audit."""
    pitch = 8.0
    rows = []

    # (a) 5-cell scanner y-jump, both sides axis-aligned
    descriptor = _format(b"paper-store/e022-q5-step")
    rng = np.random.default_rng(2350)
    page = _page_bits(descriptor, 2351)
    jac = _gt_jacobian(pitch, pitch, 0.0)
    top = page[60:180, 96:296]
    bottom = page[180:300, 96:296]
    step_cells = 5
    h_px = int((240 + step_cells) * pitch) + 160
    w_px = int(200 * pitch) + 160
    canvas = np.full((h_px, w_px), BACK, np.float32)
    img_top, sup_top = _render_affine(top, jac, (80.0, 80.0),
                                      canvas.shape, rng)
    split_px = int(80 + 120 * pitch)
    img_bot, sup_bot = _render_affine(
        bottom, jac, (80.0 + (120 + step_cells) * pitch, 80.0),
        canvas.shape, rng)
    canvas[:split_px] = img_top[:split_px]
    canvas[split_px:] = img_bot[split_px:]
    support = np.zeros(canvas.shape, bool)
    support[:split_px] = sup_top[:split_px]
    support[split_px:] = sup_bot[split_px:]
    result = pilotsearch.search_survey(
        canvas, _survey_for(canvas.shape, pitch, support), descriptor,
        config=pilotsearch.SearchConfig(bch_first=False, min_support=20))
    components = {row.component for row in result.placements
                  if not row.redundant}
    offsets = {
        int(round(row.origin_yx[0] - (row.pose.origin_yx[0] - 80.0) / pitch))
        for row in result.placements
    }
    total, rate = _observation_agreement(result)
    step_ok = bool(result.region_states.get(0) == "accepted"
                   and len(components) >= 2
                   and offsets == {60, 60 - step_cells}
                   and total > 300 and rate > 0.97)
    rows.append({"fixture": "y_step", "components": len(components),
                 "mapping_offsets": sorted(offsets), "observations": total,
                 "agreement": rate, "ok": step_ok})

    # (b) fold: the lower half of one paper rotates 1.6 deg about the
    # crease; page content is continuous, the pose field is not
    descriptor = _format(b"paper-store/e022-q5-fold")
    rng = np.random.default_rng(2360)
    page = _page_bits(descriptor, 2361)
    fold_px = 80.0 + 120 * pitch
    jac_bot = _gt_jacobian(pitch, pitch, 1.6)
    canvas = np.full((int(250 * pitch) + 240, int(210 * pitch) + 240),
                     BACK, np.float32)
    img_top, sup_top = _render_affine(page[60:180, 96:296], jac,
                                      (80.0, 80.0), canvas.shape, rng)
    img_bot, sup_bot = _render_affine(page[180:300, 96:296], jac_bot,
                                      (fold_px, 80.0), canvas.shape, rng)
    split = int(fold_px)
    canvas[:split] = img_top[:split]
    canvas[split:] = img_bot[split:]
    support = np.zeros(canvas.shape, bool)
    support[:split] = sup_top[:split]
    support[split:] = sup_bot[split:]
    result = pilotsearch.search_survey(
        canvas, _survey_for(canvas.shape, pitch, support), descriptor,
        config=pilotsearch.SearchConfig(bch_first=False, min_support=20))
    angles = [row.pose.angle_deg for row in result.placements]
    total, rate = _observation_agreement(result)
    covered_rows = {row.origin_yx[0] // 60 for row in result.placements}
    # near the crease the page mapping is continuous, so one pose
    # COMPONENT is legitimate; the fold must instead show up as two
    # measured pose angles (0 and ~1.6 deg) with no wrong-address leak
    fold_ok = bool(result.region_states.get(0) == "accepted"
                   and angles and max(angles) - min(angles) > 1.0
                   and max(angles) > 1.2
                   and len(covered_rows) >= 2
                   and total > 300 and rate > 0.97)
    rows.append({"fixture": "fold",
                 "components": len({row.component
                                    for row in result.placements
                                    if not row.redundant}),
                 "pose_angle_span_deg": (
                     [round(min(angles), 2), round(max(angles), 2)]
                     if angles else None),
                 "observations": total,
                 "agreement": rate, "ok": fold_ok})

    ok = step_ok and fold_ok
    REPORT["q5_step_and_fold"] = {"rows": rows, "ok": ok}
    for row in rows:
        print(f"Q5 {row['fixture']}: {'PASS' if row['ok'] else 'FAIL'} "
              f"(components={row['components']}, "
              f"agreement={row['agreement']:.4f})")
    return ok


def _real_row(path: Path, dpi: float, *, tag: str,
              frames_dir: Path | None = None) -> dict:
    image = run_e022.load_image(path)
    t0 = perf_counter()
    survey = platen.detect_payload_regions(image, dpi=dpi)
    survey_s = perf_counter() - t0
    frame_no = 0

    def on_region(result: pilotsearch.SearchResult, region_index: int) -> None:
        nonlocal frame_no
        if frames_dir is None:
            return
        frame_no += 1
        pilotdiag.render_diagnostic(
            image, survey, result, run_e022.E018,
            frames_dir / f"frame_{frame_no:04d}.png",
            active_region=region_index)

    if frames_dir is not None:
        frames_dir.mkdir(parents=True, exist_ok=True)
    result = pilotsearch.search_survey(
        image, survey, run_e022.E018,
        config=pilotsearch.SearchConfig(), on_region=on_region)
    png = HERE / "build" / f"{path.stem}_{tag}_e022.png"
    pilotdiag.render_diagnostic(image, survey, result, run_e022.E018, png)
    report_path = png.with_suffix(".json")
    report_path.write_text(json.dumps(
        run_e022.result_report(result, run_e022.E018, survey),
        indent=2, sort_keys=True, default=pilotdiag.json_default,
    ) + "\n")
    states = list(result.region_states.values())
    return {
        "path": str(path), "dpi": dpi, "survey_s": survey_s,
        "regions": len(survey.regions),
        "accepted": states.count("accepted"),
        "unresolved": states.count("unresolved")
        + states.count("pose_refused"),
        "placements": len(result.placements),
        "methods": {m: sum(1 for r in result.placements if r.method == m)
                    for m in ("chain", "bch_seed", "correlation")},
        "components": len({(r.region_index, r.component)
                           for r in result.placements}),
        "tiles": len(result.tiles),
        "bch_good": sum(t.bch_ok is True for t in result.tiles.values()),
        "bch_bad": sum(t.bch_ok is False for t in result.tiles.values()),
        "bch_refused": sum(t.bch_refused for t in result.tiles.values()),
        "timings": result.timings,
        "peak_rss_gb": resource.getrusage(
            resource.RUSAGE_SELF).ru_maxrss / 1e9,
        "png": str(png), "report": str(report_path),
    }


def q6_real_scans(skip_native: bool) -> bool:
    rows = []
    checks = [
        ("dec1", ROOT / "scratch/e018/decimated-1_1600.tiff", 1600.0, 17),
        ("dec3", ROOT / "scratch/e018/decimated-3_1600.tiff", 1600.0, 8),
    ]
    if not skip_native:
        checks.append(("nat1",
                       ROOT / "scratch/e018/hp-e018-canon-4800-confetti-1.tiff",
                       4800.0, 17))
    ok = True
    for tag, path, dpi, expected_regions in checks:
        if not path.exists():
            rows.append({"tag": tag, "skipped": True})
            continue
        row = _real_row(path, dpi, tag=tag,
                        frames_dir=HERE / "build" / f"real_diag_{tag}")
        row["tag"] = tag
        row_ok = bool(
            row["regions"] == expected_regions
            and row["accepted"] == expected_regions
            and row["bch_bad"] == 0
        )
        if tag == "nat1":
            row_ok = row_ok and row["tiles"] > 248   # v1 native baseline
        row["ok"] = row_ok
        ok = ok and row_ok
        rows.append(row)
        print(f"  {tag}: regions={row['regions']} accepted={row['accepted']} "
              f"placements={row['placements']} {row['methods']} "
              f"tiles={row['tiles']} "
              f"BCH={row['bch_good']}/{row['bch_bad']}/{row['bch_refused']} "
              f"total={row['timings'].get('total_s', 0):.0f}s "
              f"rss={row['peak_rss_gb']:.1f}GB "
              f"{'ok' if row_ok else 'FAIL'}")
    REPORT["q6_real_scans"] = {"rows": rows, "ok": ok}
    print(f"Q6 real scans (both footings): {'PASS' if ok else 'FAIL'}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-real", action="store_true")
    parser.add_argument("--skip-native", action="store_true")
    args = parser.parse_args()

    checks = [
        q1_exact_field_and_nulls(),
        q2_bch_fast_start(),
        q3_pose_battery(),
        q4_wrong_field_refusal(),
        q5_step_and_fold(),
    ]
    if not args.skip_real:
        checks.append(q6_real_scans(args.skip_native))
    ok = all(checks)
    REPORT["overall_ok"] = ok
    out = HERE / "build" / "qualify_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(REPORT, indent=2, sort_keys=True,
                              default=pilotdiag.json_default) + "\n")
    print(f"OVERALL: {'PASS' if ok else 'FAIL'}")
    print(f"  wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
