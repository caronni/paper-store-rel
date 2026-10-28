"""Anchor supply and correlation-edge saturation, per plane and bucket.

    PYTHONPATH=src:measure \
        env/bin/python \
        -m ysampler.anchor_supply --name frozen-cmy7

**src/holo diff: zero — the ink-free variant exists only inside this
process.**  Standing rule from the project lead (2026-08-30): *v1
measurement needs are met by runtime composition inside a harness, never
by tree edits.*  :mod:`ysampler.composition` builds the variant from
production's own parts for the duration of one pass and restores every
substitution on the way out.

ONE bounded specimen-patch decode (``_color_uplift_harness.patch_runner``
-- the campaign's minutes-not-hours tier, never a whole capture), with a
read-only spy at the ``_fit_registration`` seam that records three
passes over the identical rows and features:

* PRODUCTION -- exactly what the residual fit consumed, the ``pass=prod``
  rows of the PK6/A2 field corpus.  Untouched production code.
* CONTROL -- the composed kernel with the polarity lift switched OFF.
  On the historical known-INK population the forced ink centre is
  provably a no-op, so this pass MUST come back bit-identical to
  production.  It is the proof that the composition did not diverge from
  the production kernel; a mismatch invalidates the ink-free numbers and
  is reported as such.
* INK-FREE -- the composed kernel on known INK-FREE centres, the
  population the known-INK candidate gate can never reach (the v1 colour
  word is drawn from states {0, 3}, so no word site carries Y).

The spy forwards the production return verbatim and never writes back,
so the decode is bit-identical to an uninstrumented patch run; only the
wall time moves (each composed pass adds roughly one production NCC
workload).

SATURATION is scored exactly as ``regmap_analyze.pregates`` scores
pre-gate G3, so the numbers are comparable to §15.4 line for line:
an anchor is saturated when ``max(|dx|, |dy|)`` reaches within
``SATURATION_MARGIN_DOTS`` of the sampler's own search radius.

Development signal from the replay tier.  A patch is a SCRAP and its
certificate counts are not capture-level numbers (patch_runner's own
caveat); anchor supply and saturation are properties of the sampler on
real printed cells, which is what this instrument claims and all it
claims.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from . import composition

# regmap_analyze's G3 constants, reused verbatim so §15.4's saturation
# rates and this instrument's are the same measurement.
SATURATION_MARGIN_DOTS = 0.26
MAX_SHIFT_DOTS_BY_CELL_DOTS = {2.0: 1.5, 3.0: 2.5}

PASS_PROD = "prod"
PASS_CONTROL = "control"
PASS_INK_FREE = "ink-free"
PASS_INK_FREE_WIDE = "ink-free-wide"
BUCKET_NAMES = ("word", "dust", "cert")
PLANE_NAMES = ("C", "M", "Y")
PLANE_Y = 2
# The ruled Y radius (project lead, 2026-08-31), a LOWER bound taken from
# §15.6's censored p95 argument; what the rectification can realize is
# reported next to it.
Y_RADIUS_DOTS = 2.2
# Columns of one dumped anchor row, in order.
ANCHOR_COLUMNS = ("plane", "bucket", "dx_dots", "dy_dots", "quality",
                  "page", "cell_y", "cell_x")


class _Collector:
    """Anchor rows accumulated across every region fit of the run."""

    def __init__(self) -> None:
        self.rows: list[tuple] = []
        self.fits = 0
        self.composition_failures: list[str] = []
        self.control_fits = 0
        self.control_mismatched_fits = 0

    def record(self, pass_tag: str, anchor_planes) -> None:
        for plane in range(3):
            anchors = anchor_planes[plane]
            n = int(anchors.quality.shape[0])
            for row in range(n):
                self.rows.append((
                    pass_tag, plane, int(anchors.bucket[row]),
                    float(anchors.offset_dots_xy[row, 0]),
                    float(anchors.offset_dots_xy[row, 1]),
                    float(anchors.quality[row]),
                    int(anchors.page[row]),
                    int(anchors.cell_yx[row, 0]),
                    int(anchors.cell_yx[row, 1]),
                ))


def _install_spy(collector: _Collector, *, run_control: bool,
                 y_radius_dots: float | None):
    """Wrap ``color_payload._fit_registration``; restore on exit."""
    from holo.receive import color_payload

    real_fit = color_payload._fit_registration
    wide = ({PLANE_Y: float(y_radius_dots)}
            if y_radius_dots is not None else None)

    def composed(raster, rows, base_features, spec, *, ink_free: bool,
                 radius=None):
        return composition.composed_anchor_planes(
            real_fit, raster, rows, base_features, spec,
            ink_free=ink_free, radius_dots_by_plane=radius)

    def fit_spy(raster, rows, base_features, spec):
        result = real_fit(raster, rows, base_features, spec)
        collector.fits += 1
        collector.record(PASS_PROD, result[1])
        if run_control:
            try:
                control = composed(
                    raster, rows, base_features, spec, ink_free=False)
            except Exception as exc:  # diagnostic: record, never abort
                collector.composition_failures.append(
                    f"{PASS_CONTROL}: {exc!r}")
            else:
                collector.control_fits += 1
                if not composition.anchor_planes_identical(
                        result[1], control):
                    collector.control_mismatched_fits += 1
                collector.record(PASS_CONTROL, control)
        passes = [(PASS_INK_FREE, None)]
        if wide is not None:
            passes.append((PASS_INK_FREE_WIDE, wide))
        for tag, radius in passes:
            try:
                anchors = composed(
                    raster, rows, base_features, spec, ink_free=True,
                    radius=radius)
            except Exception as exc:  # diagnostic: record, never abort
                collector.composition_failures.append(f"{tag}: {exc!r}")
            else:
                collector.record(tag, anchors)
        # The production return, forwarded verbatim and unread.
        return result

    color_payload._fit_registration = fit_spy
    return lambda: setattr(
        color_payload, "_fit_registration", real_fit)


def _summarize(rows, cell_dots: float, pass_tags, radius_of) -> dict:
    """Per (pass, plane, bucket) supply, quality and G3 saturation.

    ``radius_of(pass_tag, plane)`` is that cell's OWN search radius in
    dots -- saturation is measured against the radius the anchor was
    actually searched over, which the per-plane ruling makes a property
    of the cell rather than of the run.
    """
    table = np.asarray(
        [(r[1], r[2], r[3], r[4], r[5]) for r in rows], np.float64
    ) if rows else np.zeros((0, 5), np.float64)
    tags = [r[0] for r in rows]
    out: dict = {"by_pass_plane_bucket": []}
    for pass_tag in pass_tags:
        keep = np.asarray([t == pass_tag for t in tags], bool)
        for plane in range(3):
            max_shift_dots = radius_of(pass_tag, plane)
            edge = max_shift_dots - SATURATION_MARGIN_DOTS
            for bucket in range(3):
                sel = (
                    keep
                    & (table[:, 0] == plane)
                    & (table[:, 1] == bucket)
                ) if table.shape[0] else np.zeros(0, bool)
                n = int(sel.sum())
                row: dict = {
                    "pass": pass_tag,
                    "plane": PLANE_NAMES[plane],
                    "bucket": BUCKET_NAMES[bucket],
                    "anchors": n,
                    "max_shift_dots": max_shift_dots,
                    "saturation_edge_dots": edge,
                }
                if n:
                    magnitude = np.max(
                        np.abs(table[sel][:, 2:4]), axis=1)
                    row["saturation"] = float(
                        np.mean(magnitude >= edge))
                    row["median_quality"] = float(
                        np.median(table[sel][:, 4]))
                    row["rms_offset_dots"] = float(np.sqrt(
                        np.mean(table[sel][:, 2:4] ** 2)))
                    row["p95_abs_offset_dots"] = float(np.percentile(
                        magnitude, 95.0))
                out["by_pass_plane_bucket"].append(row)
    return out


def _plane_totals(summary: dict, pass_tags) -> list[dict]:
    """Word-bucket headline per plane: the record's measurability bar."""
    rows = summary["by_pass_plane_bucket"]
    totals = []
    for plane in PLANE_NAMES:
        entry: dict = {"plane": plane}
        for pass_tag in pass_tags:
            picked = [
                r for r in rows
                if r["plane"] == plane and r["pass"] == pass_tag]
            entry[f"{pass_tag}_word"] = next(
                r["anchors"] for r in picked if r["bucket"] == "word")
            entry[f"{pass_tag}_total"] = sum(
                r["anchors"] for r in picked)
        totals.append(entry)
    return totals


def _rows_array(rows, pass_tag: str) -> np.ndarray:
    picked = [tuple(r[1:]) for r in rows if r[0] == pass_tag]
    return (np.asarray(picked, np.float64) if picked
            else np.zeros((0, len(ANCHOR_COLUMNS)), np.float64))


def _cm_identity(rows) -> dict:
    """C and M must not move when only Y's radius does.

    The per-plane ruling leaves C and M on production's own arithmetic,
    so the widened pass has to reproduce the plain ink-free pass exactly
    on those two planes.  This is the pin: a byte comparison of the two
    passes' C and M anchor rows.  It is a structural property (a plane
    the override does not name never enters the override branch), and
    this checks that the structure held.
    """
    plain = _rows_array(rows, PASS_INK_FREE)
    wide = _rows_array(rows, PASS_INK_FREE_WIDE)
    if not wide.shape[0]:
        return {"ran": False, "verdict": "not run — no widened pass"}
    out: dict = {"ran": True}
    identical = True
    for plane, name in enumerate(PLANE_NAMES):
        left = plain[plane == plain[:, 0]]
        right = wide[plane == wide[:, 0]]
        same = (left.shape == right.shape
                and left.tobytes() == right.tobytes())
        out[name] = {"plain_rows": int(left.shape[0]),
                     "wide_rows": int(right.shape[0]),
                     "byte_identical": bool(same)}
        if name in ("C", "M"):
            identical = identical and same
    out["verdict"] = (
        "PASS — C and M are byte-identical across the radius change"
        if identical else
        "FAIL — the Y radius moved C or M; the override is not confined")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Anchor supply and G3 saturation on one specimen.")
    parser.add_argument("--name", required=True,
                        help="specimen key, e.g. frozen-cmy7")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None,
                        help="JSON report path (default: stdout only)")
    parser.add_argument("--anchors-npz", type=Path, default=None,
                        help="dump every anchor row for a bit-identity "
                             "comparison across trees")
    parser.add_argument(
        "--skip-identity-control", action="store_true",
        help="omit the composed known-INK control pass that proves the "
             "runtime composition matches the production kernel "
             "bit-for-bit; the ink-free numbers then carry no such proof")
    parser.add_argument(
        "--y-radius-dots", type=float, default=Y_RADIUS_DOTS,
        help="the Y plane's anchor search radius for the WIDE pass, in "
             "printed dots (project-lead ruling: 2.2; C and M keep "
             "production's own radius in every pass).  0 omits the "
             "wide pass entirely")
    args = parser.parse_args(argv)

    from _color_uplift_harness import patch_corpus, patch_runner
    from holo.receive import color_anchoring

    run_control = not args.skip_identity_control
    y_radius = args.y_radius_dots if args.y_radius_dots > 0.0 else None
    entry = patch_corpus.manifest_row(args.name)
    cell_dots = float(entry["coding_id"].split("-")[0][1:])
    production_radius = composition.production_radius_dots(
        color_anchoring, int(cell_dots))
    realized_constant, realized = (
        composition.realized_radius(color_anchoring, int(cell_dots),
                                    y_radius)
        if y_radius is not None else (None, None))

    collector = _Collector()
    restore = _install_spy(collector, run_control=run_control,
                           y_radius_dots=y_radius)
    try:
        report = patch_runner.run_patch(
            args.name, arm="ysampler-anchor-supply",
            workers=args.workers, verbose=False)
    finally:
        restore()

    pass_tags = [PASS_PROD]
    if run_control:
        pass_tags.append(PASS_CONTROL)
    pass_tags.append(PASS_INK_FREE)
    if y_radius is not None:
        pass_tags.append(PASS_INK_FREE_WIDE)
    pass_tags = tuple(pass_tags)

    def radius_of(pass_tag: str, plane: int) -> float:
        if pass_tag == PASS_INK_FREE_WIDE and plane == PLANE_Y:
            return realized
        return production_radius

    summary = _summarize(collector.rows, cell_dots, pass_tags, radius_of)
    summary["search_radius_dots"] = {
        "production": production_radius,
        "regmap_analyze_g3_constant": MAX_SHIFT_DOTS_BY_CELL_DOTS.get(
            cell_dots),
        "y_requested": y_radius,
        "y_realized": realized,
        "y_realized_constant": realized_constant,
        "note": "the rectification quantizes the radius to 1/"
                f"{color_anchoring._RECTIFIED_PX_PER_DOT} dot, so the "
                "request is honoured as a lower bound and the realized "
                "radius is what the numbers were measured at",
    }
    summary["c_m_untouched"] = _cm_identity(collector.rows)
    summary["specimen"] = args.name
    summary["capture"] = entry["capture"]
    summary["coding_id"] = entry["coding_id"]
    summary["cell_dots"] = cell_dots
    summary["region_fits"] = collector.fits
    summary["composition_failures"] = collector.composition_failures
    summary["identity_control"] = {
        "ran": run_control,
        "fits_compared": collector.control_fits,
        "fits_mismatched": collector.control_mismatched_fits,
        "verdict": (
            "not run" if not run_control
            else "PASS — composed known-INK pass is bit-identical to "
                 "production"
            if (collector.control_fits == collector.fits
                and collector.control_mismatched_fits == 0)
            else "FAIL — the composition diverged from the production "
                 "kernel; the ink-free numbers are NOT trustworthy"),
    }
    summary["certificates"] = report["totals"]["certificates"]
    summary["wrong_certificates"] = report["certificate_audit"][
        "disagreeing_addresses"]
    summary["plane_totals"] = _plane_totals(summary, pass_tags)

    if args.anchors_npz is not None:
        args.anchors_npz.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            args.anchors_npz,
            columns=np.asarray(ANCHOR_COLUMNS),
            prod=_rows_array(collector.rows, PASS_PROD),
            control=_rows_array(collector.rows, PASS_CONTROL),
            ink_free=_rows_array(collector.rows, PASS_INK_FREE),
            ink_free_wide=_rows_array(collector.rows,
                                      PASS_INK_FREE_WIDE))

    text = json.dumps(summary, indent=1, sort_keys=True)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
