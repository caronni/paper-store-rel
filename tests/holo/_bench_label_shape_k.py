"""A3 label-shape instrument: K sparse-vs-full label-row differential.

Provenance: PAYLOAD-REWORK-PLAN addendum A3 (chip task_45921656) —
candidate (b) of the K-vs-color label sampling shape re-evaluation;
measured record in docs/LABEL-SAMPLING-SHAPE-ANALYSIS.md. Standalone,
never pytest-collected.

Candidate (b) asks what happens if K label rows sample only the
format-known sites plus their 8-neighbourhoods instead of the full
window. This harness answers both halves WITHOUT touching src:

1. COST — component timing on the pool-law oracle fixture geometry
   (128x128-cell window, 8 px/cell): window crop+filter (paid by both
   shapes — the sites span the window, so the crop bounding box cannot
   shrink) vs order-1 sampling at 16384 points (full) vs at the
   site+halo subset (sparse) vs per-window PAVA calibration on each.

2. EXACTNESS — build the sparse label row for the certified-complete
   window, run the region context fit with it, and compare against the
   pooled single-pass oracle: which ContextDecision fields survive
   (fit-population counts — oracle case (c)) and which diverge
   (offsets / decision id — oracle case (b)'s byte-equality), plus the
   measured magnitude of the marginal-LLR perturbation at the label
   sites caused by the _scores median/spread normalization-population
   change.

Usage:
    PYTHONPATH=src:tests/holo env/bin/python \
        tests/holo/_bench_label_shape_k.py <out.json>
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy import ndimage

from _e023c_fixtures import _page_fixture
from test_pool_law_oracle import _patch, _COUNT_FIELDS

from holo.receive._payload_context import apply_region_context
from holo.receive._payload_sampling import (
    _WindowRows,
    _calibrate,
    _region_pitch,
    _sample_rows,
    _sample_window,
    _window_crop,
    _window_rows,
    format_reference_values,
)
from holo.receive.payload_model import EvidenceSource
from holo.receive import detect


def _sparse_keep_mask(rows: _WindowRows, labels: np.ndarray) -> np.ndarray:
    """Site cells plus their in-window 8-neighbourhoods (3x3 dilation)."""
    local = np.asarray(rows.local_cells_yx, np.int64)
    site = np.asarray(labels, np.int64) >= 0
    height = int(local[:, 0].max()) + 1
    width = int(local[:, 1].max()) + 1
    grid = np.zeros((height, width), np.uint8)
    grid[local[site, 0], local[site, 1]] = 1
    dilated = ndimage.convolve(
        grid, np.ones((3, 3), np.uint8), mode="constant", cval=0)
    return (dilated[local[:, 0], local[:, 1]] > 0)


def _subset_rows(rows: _WindowRows, keep: np.ndarray) -> _WindowRows:
    return _WindowRows(
        rows.segment_id,
        rows.local_cells_yx[keep],
        rows.page_cells_yx[keep],
        rows.scan_points_yx[keep],
    )


def main() -> None:
    out_path = Path(sys.argv[1])
    page = _page_fixture()
    source = EvidenceSource(
        hashlib.sha256(b"a3-label-shape").hexdigest(), "a3-lane")
    patch0 = _patch(0, 0, (0, 0))       # the certified-complete window
    patch1 = _patch(1, 0, (128, 0))     # open sibling
    spec = page.spec

    rows0 = _window_rows(patch0, spec)
    rows1 = _window_rows(patch1, spec)
    labels0 = format_reference_values(
        spec, 0, rows0.page_cells_yx)
    labels1 = format_reference_values(
        spec, 0, rows1.page_cells_yx)
    keep0 = _sparse_keep_mask(rows0, labels0)
    rows0_sparse = _subset_rows(rows0, keep0)
    labels0_sparse = labels0[keep0]
    pitch_px = _region_pitch((patch0, patch1))

    # ---- COST: component timing (median of repeats) ------------------
    def timed(function, repeats: int = 9) -> float:
        samples = []
        for _ in range(repeats):
            t0 = time.perf_counter()
            function()
            samples.append(time.perf_counter() - t0)
        return float(np.median(samples))

    crop = _window_crop(page.raster, patch0, pitch_px)
    cost = {
        "window_cells": int(rows0.page_cells_yx.shape[0]),
        "sparse_cells": int(rows0_sparse.page_cells_yx.shape[0]),
        "site_cells": int((labels0 >= 0).sum()),
        "crop_filter_s": timed(
            lambda: _window_crop(page.raster, patch0, pitch_px)),
        "sample_full_s": timed(
            lambda: _sample_rows(crop, rows0, page.raster.shape)),
        "sample_sparse_s": timed(
            lambda: _sample_rows(crop, rows0_sparse, page.raster.shape)),
    }
    means_full = _sample_window(page.raster, patch0, rows0, pitch_px)
    means_sparse = _sample_window(
        page.raster, patch0, rows0_sparse, pitch_px)
    cost["calibrate_full_s"] = timed(
        lambda: _calibrate(
            source, patch0, rows0, means_full, labels0, spec))
    cost["calibrate_sparse_s"] = timed(
        lambda: _calibrate(
            source, patch0, rows0_sparse, means_sparse,
            labels0_sparse, spec))
    cost["full_row_total_s"] = round(
        cost["crop_filter_s"] + cost["sample_full_s"]
        + cost["calibrate_full_s"], 6)
    cost["sparse_row_total_s"] = round(
        cost["crop_filter_s"] + cost["sample_sparse_s"]
        + cost["calibrate_sparse_s"], 6)

    # ---- EXACTNESS: sparse label row vs the pooled oracle ------------
    row0_full = _calibrate(source, patch0, rows0, means_full, labels0, spec)
    row0_sparse = _calibrate(
        source, patch0, rows0_sparse, means_sparse, labels0_sparse, spec)
    row1 = _calibrate(
        source, patch1, rows1,
        _sample_window(page.raster, patch1, rows1, pitch_px),
        labels1, spec)

    pooled_rows, pooled_decisions = apply_region_context((row0_full, row1))
    split_full_rows, split_full_decisions = apply_region_context(
        (row1,), (row0_full,))
    split_sparse_rows, split_sparse_decisions = apply_region_context(
        (row1,), (row0_sparse,))

    pooled = pooled_decisions[0]
    with_full = split_full_decisions[0]
    with_sparse = split_sparse_decisions[0]

    def counts(decision) -> dict[str, int]:
        return {name: int(getattr(decision, name))
                for name in _COUNT_FIELDS}

    # Marginal-LLR perturbation at the label row's known sites
    # (the _scores normalization-population question).
    def marginals(row) -> np.ndarray:
        calibration = detect.Calibration(
            row.placement_id, row.calibration_score_nodes,
            row.calibration_probability_nodes, row.n_search)
        return np.asarray(calibration.llr(row.scores), np.float64)
    known_full = row0_full.reference_values >= 0
    known_sparse = row0_sparse.reference_values >= 0
    marginal_full_at_sites = marginals(row0_full)[known_full]
    marginal_sparse_at_sites = marginals(row0_sparse)[known_sparse]
    assert marginal_full_at_sites.shape == marginal_sparse_at_sites.shape

    pooled_row1 = next(r for r in pooled_rows if r.patch_id == 1)
    full_row1 = next(r for r in split_full_rows if r.patch_id == 1)
    sparse_row1 = next(r for r in split_sparse_rows if r.patch_id == 1)

    exactness = {
        "score_normalization": {
            "full_midpoint": float(np.median(
                np.asarray(means_full, np.float32))),
            "sparse_midpoint": float(np.median(
                np.asarray(means_sparse, np.float32))),
            "full_spread": float(np.abs(
                np.asarray(means_full, np.float32)
                - np.float32(np.median(means_full))).mean()),
            "sparse_spread": float(np.abs(
                np.asarray(means_sparse, np.float32)
                - np.float32(np.median(means_sparse))).mean()),
        },
        "calibration_accepted": {
            "full": bool(row0_full.accepted),
            "sparse": bool(row0_sparse.accepted),
        },
        "marginal_llr_at_sites": {
            "max_abs_delta": float(np.max(np.abs(
                marginal_full_at_sites - marginal_sparse_at_sites))),
            "median_abs_delta": float(np.median(np.abs(
                marginal_full_at_sites - marginal_sparse_at_sites))),
            "max_abs_value": float(np.max(np.abs(marginal_full_at_sites))),
        },
        "fit_population_counts": {
            "pooled": counts(pooled),
            "split_full_label": counts(with_full),
            "split_sparse_label": counts(with_sparse),
            "sparse_counts_equal_pooled":
                counts(with_sparse) == counts(pooled),
        },
        "decision_vs_pooled": {
            "full_label_decision_id_equal":
                with_full.decision_id == pooled.decision_id,
            "sparse_label_decision_id_equal":
                with_sparse.decision_id == pooled.decision_id,
            "full_label_offsets_equal": bool(np.array_equal(
                with_full.offsets, pooled.offsets)),
            "sparse_label_offsets_equal": bool(np.array_equal(
                with_sparse.offsets, pooled.offsets)),
            "sparse_max_abs_offset_delta": float(np.max(np.abs(
                with_sparse.offsets - pooled.offsets))),
            "adopted": {
                "pooled": bool(pooled.adopted),
                "full": bool(with_full.adopted),
                "sparse": bool(with_sparse.adopted),
            },
        },
        "open_window_printed_llr": {
            "full_label_byte_equal": bool(np.array_equal(
                full_row1.printed_llr, pooled_row1.printed_llr)),
            "sparse_label_byte_equal": bool(np.array_equal(
                sparse_row1.printed_llr, pooled_row1.printed_llr)),
            "sparse_max_abs_delta": float(np.max(np.abs(
                sparse_row1.printed_llr.astype(np.float64)
                - pooled_row1.printed_llr.astype(np.float64)))),
        },
    }

    report = {"cost": cost, "exactness": exactness}
    out_path.write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
