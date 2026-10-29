#!/usr/bin/env python3
"""e040 — `discover analyze` placed from EVERY visible registration mark.

Letter stock under an A4 page trims one edge: the Canon's 1200x2400-request
sheet lost its top pair of chiral corners, its default-request sheet the
bottom pair and the end sentinel.  Production refuses both (three corners
needed; end sentinel unresolved).  But the page carries four chiral
corners and ten internal `geometry_plus` marks at known layout positions,
so whatever is still on paper can be placed.  This harness, around the
production analyzer and touching nothing else:

1. registration — the production `register_blind`; when it finds only TWO
   corners, a similarity (scale, rotation, translation) through them;
2. refinement, always — `plus_residuals` measures every plus mark against
   the current pose (24-dot search on the first pass, 12 on the second);
   the full affine is refitted over the corners plus every resolved mark
   (layout point -> where the mark was actually found), twice;
3. integrity — when the end sentinel is unresolved, the gate is let
   through and the override is written into the report's integrity
   record (`trimmed_sentinel_override`); everything else is the gate's.

DIAGNOSTIC, not the production path — its reports are not promotable.

    PYTHONPATH=src env/bin/python experiments/040-canon-iradv/analyze_visible_marks.py \
        <discover analyze arguments…>
"""
from __future__ import annotations

import sys

import numpy as np

from holo.characterize import analyze, geometry
from holo.cli import main

_register = geometry.register_blind
_integrity = analyze._required_integrity_visible


def _similarity(layout: np.ndarray, scan: np.ndarray) -> np.ndarray:
    """2x3 layout(x, y) -> scan(x, y) similarity through two points."""
    zl = layout[:, 0] + 1j * layout[:, 1]
    zs = scan[:, 0] + 1j * scan[:, 1]
    a = (zs[1] - zs[0]) / (zl[1] - zl[0])
    b = zs[0] - a * zl[0]
    return np.array([[a.real, -a.imag, b.real], [a.imag, a.real, b.imag]])


def _two_corner_pose(source, scan_dpi_x, scan_dpi_y, corner_layout, target_dpi):
    grey, fx, fy = source.thumbnail_grey(scan_dpi_x, scan_dpi_y, target_dpi)
    detected = {int(r["satellites"]): r for r in geometry.detect_chiral_corners(
        grey, target_dpi=target_dpi, dpi_x=float(scan_dpi_x) / fx,
        dpi_y=float(scan_dpi_y) / fy)}
    expected = geometry._layout_corner_centres(corner_layout)
    common = sorted(set(expected) & set(detected))
    if len(common) != 2:
        raise geometry.GeometryError(
            f"found chiral corners {sorted(detected)}; need at least 2")
    layout = np.asarray([expected[k] for k in common], np.float64)
    scan = np.asarray([((float(detected[k]["x_thumb"]) + 0.5) * fx - 0.5,
                        (float(detected[k]["y_thumb"]) + 0.5) * fy - 0.5)
                       for k in common], np.float64)
    record = {"corners_found": [], "corner_satellite_counts": common,
              "corners_missing": sorted(set(expected) - set(common)),
              "two_corner_similarity": True,
              "thumbnail": {"shape": list(grey.shape), "factor_x": fx,
                            "factor_y": fy}}
    return _similarity(layout, scan), record, layout, scan


def _register_visible(source, scan_dpi_x, scan_dpi_y, *, corner_layout,
                      target_dpi=300.0, min_corners=3):
    if not isinstance(source, geometry.RasterSource):
        source = geometry.RasterSource(source)
    try:
        coef, record = _register(source, scan_dpi_x, scan_dpi_y,
                                 corner_layout=corner_layout,
                                 target_dpi=target_dpi, min_corners=min_corners)
        layout_c = np.asarray([[c["x_layout_dots"], c["y_layout_dots"]]
                               for c in record["corners_found"]], np.float64)
        scan_c = np.asarray([[c["x_scan"], c["y_scan"]]
                             for c in record["corners_found"]], np.float64)
    except geometry.GeometryError as exc:
        if "found chiral corners" not in str(exc):
            raise
        coef, record, layout_c, scan_c = _two_corner_pose(
            source, scan_dpi_x, scan_dpi_y, corner_layout, target_dpi)
    passes = []
    for search in (24.0, 12.0):
        plus = geometry.plus_residuals(source, coef, corner_layout,
                                       search_layout_dots=search)
        ok = [m for m in plus["marks"] if m.get("ok")]
        found_layout = np.asarray([[m["x_layout_dots"] + m["dx_layout_dots"],
                                    m["y_layout_dots"] + m["dy_layout_dots"]]
                                   for m in ok], np.float64).reshape(-1, 2)
        layout_p = np.asarray([[m["x_layout_dots"], m["y_layout_dots"]]
                               for m in ok], np.float64).reshape(-1, 2)
        scan_p = np.asarray(geometry.apply_affine(coef, found_layout)).reshape(-1, 2)
        layout_all = np.vstack([layout_c, layout_p])
        scan_all = np.vstack([scan_c, scan_p])
        if len(layout_all) >= 3:
            coef, rms = geometry.fit_affine(layout_all, scan_all)
        else:
            rms = None
        passes.append({"search_layout_dots": search, "plus_resolved": len(ok),
                       "plus_expected": plus["n_expected"],
                       "points": int(len(layout_all)),
                       "fit_rms_px": None if rms is None else float(rms)})
    record["affine_layout_to_scan"] = np.asarray(coef).tolist()
    record["visible_marks_refit"] = passes
    record.update(geometry.affine_metrics(coef, scan_dpi_x=scan_dpi_x,
                                          scan_dpi_y=scan_dpi_y))
    return coef, record


def _integrity_trimmed(source, affine, page):
    ok, reason, detail = _integrity(source, affine, page)
    if not ok and reason and "end sentinel" in reason:
        detail = dict(detail)
        detail["trimmed_sentinel_override"] = reason
        return True, None, detail
    return ok, reason, detail


geometry.register_blind = _register_visible
analyze.register_blind = _register_visible            # analyze imports the name
analyze._required_integrity_visible = _integrity_trimmed

if __name__ == "__main__":
    sys.exit(main(["discover", "analyze", *sys.argv[1:]]))
