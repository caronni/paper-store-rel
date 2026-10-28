"""PK6/A2 measure-first instrument: the per-window registration field.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.regmap run --capture xerox-c3-cmy7 \
            [--dense-budget 4096] [--census-lane auto] [--workers 8]

One ``run`` performs ONE committed-pose LIVE replay via
``ab_runner.run_replay`` with read-only spies installed around it:

* ``replay.build_address`` — pass-through; tracks the current lane so
  every captured record is lane-tagged (one ``_fit_registration`` call
  per (lane, region-group), serial, main thread — verified against
  every ``_parallel`` consumer: no pooled worker reaches these seams).
* ``color_payload._fit_registration`` — captures the production
  per-anchor field (the PK6 return-only change), then re-measures the
  SAME candidates at higher density in spy-side MEASUREMENT-ONLY
  passes: a DENSE pass (bin-left at ``--dense-budget``, an exact
  superset of production's selection because the budget is a multiple
  of ``_ANCHOR_BUDGET_PER_KIND``) on every lane, and a CENSUS pass
  (every word/dust candidate; certificate bucket capped by a seeded
  draw that still nests production's picks) on the census lanes.
  ``fit_plane_residual`` is stubbed during spy passes — no fit runs on
  the large anchor sets (a 4096-budget Theil–Sen would transiently
  allocate gigabytes), and the PRODUCTION result is returned verbatim,
  so the decode is bit-identical to an uninstrumented replay.
* ``color_anchoring._measure_anchor`` / ``_xcorr_offset_ncc`` — attempt
  accounting: why candidates were rejected (no 3x3 neighbourhood /
  uniform bits / out of crop / low quality) and a histogram of rejected
  NCC qualities.  This exists because the archived diags show
  whole-lane zero-anchor fits on three of the four captures; a field
  map that silently conditions on the lanes that worked would be a
  selection artifact.

The NPZ is flushed at every lane boundary and on the way out, so a
killed multi-hour run keeps every completed lane.  Output:
``<work>/regmap/<capture>-regmap.npz`` plus the standard run JSON via
the ab_runner ledger convention (mode ``replay``, arm ``regmap``; its
cost columns are labelled instrumentation-inflated).  Everything here
is DEVELOPMENT SIGNAL (the replay tier); nothing is a qualification
number.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np

from . import ab_runner, corpus, state_cache
from . import replay as replay_module

REGMAP_SCHEMA = "color-uplift-regmap-2"
DEFAULT_DENSE_BUDGET = 4096
CENSUS_CERT_CAP = 4096
CENSUS_SEED_BASE = 20260810
# Rejection accounting vocabulary (mirrors _measure_anchor's gate order).
REASON_OK = 0
REASON_NO_NEIGHBORHOOD = 1
REASON_UNIFORM_BITS = 2
REASON_OUT_OF_CROP = 3
REASON_LOW_QUALITY = 4
PASS_PROD = 0
PASS_DENSE = 1
PASS_CENSUS = 2
# Rejected-quality histogram bins: [0, _ANCHOR_MIN_Q) in 20 steps.
QUALITY_BIN_EDGES = np.linspace(0.0, 0.10, 21)


class _Collector:
    """Mutable capture-run state shared by the spies."""

    def __init__(self, dense_budget: int, census_lanes: tuple[str, ...],
                 flush) -> None:
        self.dense_budget = int(dense_budget)
        self.census_lanes = tuple(census_lanes)
        self.flush = flush
        self.lane_ids: list[str] = []
        self.current_lane = -1
        self.fit_ordinal = -1
        self.pass_tag = PASS_PROD
        self.census_calls = 0
        self.ncc_calls = 0
        self.last_ncc_quality = float("nan")
        self.anchors: list[tuple] = []
        self.fits: list[tuple] = []
        self.windows: list[tuple] = []
        self.accounting: dict[tuple, int] = {}
        self.rejected_quality: dict[tuple, int] = {}
        self.spy_pass_failures: list[list] = []

    def enter_lane(self, lane_id: str) -> None:
        if self.lane_ids:
            self.flush(self)
        self.lane_ids.append(lane_id)
        self.current_lane = len(self.lane_ids) - 1
        self.fit_ordinal = -1

    @property
    def census_here(self) -> bool:
        return (0 <= self.current_lane < len(self.lane_ids)
                and self.lane_ids[self.current_lane] in self.census_lanes)

    def count(self, plane: int, reason: int) -> None:
        key = (self.current_lane, self.fit_ordinal, self.pass_tag,
               int(plane), int(reason))
        self.accounting[key] = self.accounting.get(key, 0) + 1

    def count_rejected_quality(self, plane: int, quality: float) -> None:
        bin_index = int(np.clip(
            np.searchsorted(QUALITY_BIN_EDGES, quality, side="right") - 1,
            0, len(QUALITY_BIN_EDGES) - 2))
        key = (self.current_lane, self.fit_ordinal, self.pass_tag,
               int(plane), bin_index)
        self.rejected_quality[key] = self.rejected_quality.get(key, 0) + 1


def _census_select(candidates, seed: int, base_budget: int):
    """Census selection: all word/dust candidates, capped cert bucket.

    Buckets 0/1 (format furniture) are taken WHOLE — they are the
    certificate-independent, residue-unbiased anchor supply, and the
    production bin-left stride must not be reused for the census (a
    stride commensurate with the window pitch can alias window phase;
    stats review S10).  Bucket 2 (pre-lane certificates) explodes on
    heavily certified captures, so it is capped: production's own
    bin-left picks first (``base_budget`` is the UNPATCHED production
    constant, so the nesting is against what production selected),
    then a seeded uniform draw of the remainder up to
    ``CENSUS_CERT_CAP``.
    """
    selected: list[tuple] = []
    for bucket in (0, 1):
        ordered = tuple(sorted(candidates[bucket].items()))
        selected.extend(
            (key, window_index, row_index, bucket)
            for key, (window_index, row_index) in ordered)
    ordered = tuple(sorted(candidates[2].items()))
    if len(ordered) > CENSUS_CERT_CAP:
        production_picks = set(
            np.arange(base_budget, dtype=np.int64)
            * len(ordered) // base_budget
        ) if len(ordered) > base_budget else set(range(len(ordered)))
        remainder = np.asarray(sorted(
            set(range(len(ordered))) - production_picks), np.int64)
        rng = np.random.default_rng(seed)
        fill = rng.choice(
            remainder, CENSUS_CERT_CAP - len(production_picks),
            replace=False)
        keep = np.sort(np.concatenate((
            np.asarray(sorted(production_picks), np.int64), fill)))
        ordered = tuple(ordered[int(index)] for index in keep)
    selected.extend(
        (key, window_index, row_index, 2)
        for key, (window_index, row_index) in ordered)
    return tuple(selected)


def _record_windows(collector: _Collector, rows) -> None:
    lane = collector.current_lane
    ordinal = collector.fit_ordinal
    for index, window in enumerate(rows):
        cells = np.asarray(window.page_cells_yx, np.int64)
        pose = window.patch.segment.segment.pose
        collector.windows.append((
            lane, ordinal, index,
            int(window.patch.patch_id),
            int(window.patch.region_index),
            int(window.patch.candidate.page),
            int(window.patch.candidate.rot_k),
            int(cells[:, 0].min()), int(cells[:, 1].min()),
            int(cells[:, 0].max()), int(cells[:, 1].max()),
            int(cells.shape[0]),
            float(pose.pitch_px),
            float(pose.angle_deg),
            float(pose.origin_yx[0]), float(pose.origin_yx[1]),
            float(pose.phase_yx[0]), float(pose.phase_yx[1]),
        ))


def _record_anchors(collector: _Collector, pass_tag: int,
                    anchor_planes) -> None:
    lane = collector.current_lane
    ordinal = collector.fit_ordinal
    for plane in range(3):
        anchors = anchor_planes[plane]
        for row in range(int(anchors.quality.shape[0])):
            collector.anchors.append((
                lane, ordinal, pass_tag, plane,
                int(anchors.bucket[row]),
                int(anchors.page[row]),
                int(anchors.cell_yx[row, 0]), int(anchors.cell_yx[row, 1]),
                int(anchors.window_index[row]),
                float(anchors.offset_dots_xy[row, 0]),
                float(anchors.offset_dots_xy[row, 1]),
                float(anchors.quality[row]),
            ))


def _record_fits(collector: _Collector, rows, residuals,
                 anchor_planes) -> None:
    lane = collector.current_lane
    ordinal = collector.fit_ordinal
    page = int(rows[0].patch.candidate.page) if rows else -1
    region_index = int(rows[0].patch.region_index) if rows else -1
    for plane in range(3):
        residual = residuals[plane]
        collector.fits.append((
            lane, ordinal, PASS_PROD, plane, page, region_index,
            float(residual.intercept_xy[0]), float(residual.intercept_xy[1]),
            float(residual.slope_xy[0]), float(residual.slope_xy[1]),
            int(residual.n_anchors),
            int(anchor_planes[plane].quality.shape[0]),
        ))


def _install_spies(collector: _Collector) -> list[tuple]:
    from holo.receive import color_anchoring, color_payload
    from holo.receive.color_registration import PlaneResidual

    saved: list[tuple] = []

    real_build_address = replay_module.build_address

    def build_address_spy(*args, **kwargs):
        lane = kwargs.get("lane", args[2] if len(args) > 2 else None)
        collector.enter_lane(str(lane.lane_id))
        return real_build_address(*args, **kwargs)

    real_ncc = color_anchoring._xcorr_offset_ncc

    def ncc_spy(window, template, weight):
        out = real_ncc(window, template, weight)
        collector.ncc_calls += 1
        collector.last_ncc_quality = float(out[2])
        return out

    real_measure = color_anchoring._measure_anchor

    def measure_spy(raster, window, row_index, plane,
                    detected, confident, spec):
        calls_before = collector.ncc_calls
        result = real_measure(
            raster, window, row_index, plane, detected, confident, spec)
        if result is not None:
            collector.count(plane, REASON_OK)
            return result
        neighbor_indices = window.neighbor_indices[row_index]
        if np.any(neighbor_indices < 0):
            collector.count(plane, REASON_NO_NEIGHBORHOOD)
            return None
        bits = detected[neighbor_indices, plane].reshape(3, 3).copy()
        bits[1, 1] = 1
        if bits.min() == bits.max():
            collector.count(plane, REASON_UNIFORM_BITS)
            return None
        if collector.ncc_calls == calls_before:
            collector.count(plane, REASON_OUT_OF_CROP)
            return None
        collector.count(plane, REASON_LOW_QUALITY)
        collector.count_rejected_quality(plane, collector.last_ncc_quality)
        return None

    real_fit = color_payload._fit_registration
    zero_residual = PlaneResidual((0.0, 0.0), (0.0, 0.0), 0)

    def measurement_only(raster, rows, base_features, spec, pass_tag,
                         selector=None):
        """One spy-side re-measurement pass; never load-bearing."""
        collector.pass_tag = pass_tag
        saved_budget = color_anchoring._ANCHOR_BUDGET_PER_KIND
        saved_fit = color_anchoring.fit_plane_residual
        saved_select = color_anchoring._select_registration_candidates
        color_anchoring.fit_plane_residual = (
            lambda y_fraction, offsets, quality: zero_residual)
        if selector is not None:
            # The census selector replaces bin-left entirely; the budget
            # global stays at the production constant it nests against.
            color_anchoring._select_registration_candidates = selector
        else:
            color_anchoring._ANCHOR_BUDGET_PER_KIND = (
                collector.dense_budget)
        try:
            _residuals, anchor_planes = real_fit(
                raster, rows, base_features, spec)
        except Exception as exc:  # diagnostic pass: record, never abort
            collector.spy_pass_failures.append([
                collector.current_lane, collector.fit_ordinal,
                pass_tag, repr(exc)])
        else:
            _record_anchors(collector, pass_tag, anchor_planes)
        finally:
            color_anchoring._ANCHOR_BUDGET_PER_KIND = saved_budget
            color_anchoring.fit_plane_residual = saved_fit
            color_anchoring._select_registration_candidates = saved_select
            collector.pass_tag = PASS_PROD

    def fit_spy(raster, rows, base_features, spec):
        collector.fit_ordinal += 1
        _record_windows(collector, rows)
        collector.pass_tag = PASS_PROD
        production = real_fit(raster, rows, base_features, spec)
        _record_anchors(collector, PASS_PROD, production[1])
        _record_fits(collector, rows, production[0], production[1])
        measurement_only(raster, rows, base_features, spec, PASS_DENSE)
        if collector.census_here:
            collector.census_calls += 1
            seed = CENSUS_SEED_BASE + collector.census_calls
            base_budget = color_anchoring._ANCHOR_BUDGET_PER_KIND

            def selector(candidates, _seed=seed, _base=base_budget):
                return _census_select(candidates, _seed, _base)

            measurement_only(
                raster, rows, base_features, spec, PASS_CENSUS,
                selector=selector)
        return production

    for module, name, replacement in (
            (replay_module, "build_address", build_address_spy),
            (color_anchoring, "_xcorr_offset_ncc", ncc_spy),
            (color_anchoring, "_measure_anchor", measure_spy),
            (color_payload, "_fit_registration", fit_spy)):
        saved.append((module, name, getattr(module, name)))
        setattr(module, name, replacement)
    return saved


def _remove_spies(saved: list[tuple]) -> None:
    for module, name, original in reversed(saved):
        setattr(module, name, original)


def _save(collector: _Collector, path, meta_extra: dict) -> None:
    meta = {
        "schema": REGMAP_SCHEMA,
        "dense_budget": collector.dense_budget,
        "census_lanes": list(collector.census_lanes),
        "census_cert_cap": CENSUS_CERT_CAP,
        "census_seed_base": CENSUS_SEED_BASE,
        "lane_ids": collector.lane_ids,
        "pass_tags": {"prod": PASS_PROD, "dense": PASS_DENSE,
                      "census": PASS_CENSUS},
        "spy_pass_failures": collector.spy_pass_failures,
        "replay_is_development_signal": True,
        "anchors_columns": [
            "lane", "fit_ordinal", "pass", "plane", "bucket", "page",
            "cell_y", "cell_x", "window_index",
            "off_x_dots", "off_y_dots", "quality"],
        "fits_columns": [
            "lane", "fit_ordinal", "pass", "plane", "page", "region_index",
            "intercept_x", "intercept_y", "slope_x", "slope_y",
            "n_anchors", "n_measured"],
        "windows_columns": [
            "lane", "fit_ordinal", "window_index", "patch_id",
            "region_index", "page", "rot_k",
            "bbox_y0", "bbox_x0", "bbox_y1", "bbox_x1", "n_rows",
            "pitch_px", "angle_deg", "origin_y", "origin_x",
            "phase_y", "phase_x"],
        "accounting_columns": [
            "lane", "fit_ordinal", "pass", "plane", "reason", "count"],
        "rejected_quality_columns": [
            "lane", "fit_ordinal", "pass", "plane", "quality_bin", "count"],
        "quality_bin_edges": [float(v) for v in QUALITY_BIN_EDGES],
        "reason_codes": {
            "ok": REASON_OK,
            "no_neighborhood": REASON_NO_NEIGHBORHOOD,
            "uniform_bits": REASON_UNIFORM_BITS,
            "out_of_crop": REASON_OUT_OF_CROP,
            "low_quality": REASON_LOW_QUALITY},
    }
    meta.update(meta_extra)
    accounting = [key + (count,) for key, count
                  in sorted(collector.accounting.items())]
    rejected = [key + (count,) for key, count
                in sorted(collector.rejected_quality.items())]
    np.savez_compressed(
        path,
        meta=np.frombuffer(
            json.dumps(meta, sort_keys=True).encode(), np.uint8),
        anchors=np.asarray(collector.anchors, np.float64).reshape(-1, 12),
        fits=np.asarray(collector.fits, np.float64).reshape(-1, 12),
        windows=np.asarray(collector.windows, np.float64).reshape(-1, 18),
        accounting=np.asarray(accounting, np.float64).reshape(-1, 6),
        rejected_quality=np.asarray(rejected, np.float64).reshape(-1, 6),
    )


def load_regmap(path) -> dict:
    """Read one regmap NPZ back into named arrays + parsed meta."""
    with np.load(path) as archive:
        meta = json.loads(bytes(archive["meta"]).decode())
        return {
            "meta": meta,
            "anchors": archive["anchors"],
            "fits": archive["fits"],
            "windows": archive["windows"],
            "accounting": archive["accounting"],
            "rejected_quality": archive["rejected_quality"],
        }


def _census_lane_ids(row, requested: list[str]) -> tuple[str, ...]:
    """Resolve --census-lane; ``auto`` = first + last ordinary lane."""
    explicit = [name for name in requested if name != "auto"]
    if explicit and "auto" not in requested:
        return tuple(explicit)
    cache = state_cache.load(row, rebuild=False)
    spec = corpus.resolve_spec(row, cache.format_row_id)
    plan, _levels = replay_module.replay_plan(cache, spec)
    ordinary = [
        lane.lane_id for lane in plan
        if lane.mopup_of is None and lane.refine_of is None
        and lane.uplift_of is None]
    auto = ({ordinary[0], ordinary[-1]} if ordinary else set())
    return tuple(sorted(auto | set(explicit)))


def cmd_run(args: argparse.Namespace) -> int:
    from holo.receive import color_anchoring

    ab_runner._apply_force_null(False)
    base_budget = color_anchoring._ANCHOR_BUDGET_PER_KIND
    if args.dense_budget < base_budget or args.dense_budget % base_budget:
        raise SystemExit(
            f"--dense-budget must be a positive multiple of {base_budget} "
            "(bin-left selection only nests production's anchors at exact "
            "multiples; anything else compares disjoint populations)")
    row = corpus.capture(args.capture)
    census_lanes = _census_lane_ids(row, list(args.census_lane))
    out_dir = corpus.work_dir("regmap")
    npz_path = out_dir / f"{row.key}-regmap.npz"
    if npz_path.exists() and not args.overwrite:
        raise SystemExit(f"{npz_path} exists; pass --overwrite to replace")

    def flush(collector: _Collector) -> None:
        _save(collector, npz_path, {"partial": True, "capture": row.key})

    collector = _Collector(args.dense_budget, census_lanes, flush)
    saved = _install_spies(collector)
    started = time.perf_counter()
    report = None
    try:
        report = ab_runner.run_replay(
            row, arm="regmap", force_null=False,
            lanes=tuple(args.lane) if args.lane else None,
            close=False, rebuild_cache=False,
            workers=args.workers)
    finally:
        _remove_spies(saved)
        if report is None and collector.lane_ids:
            _save(collector, npz_path,
                  {"partial": True, "capture": row.key})
    if any(report["tree_state_before"].get(key)
           != report["tree_state_after"].get(key)
           for key in ("receiver_tree_sha256", "producer_identity",
                       "arm_identity")):
        print("!! THE TREE MOVED DURING THIS RUN — the result is VOID",
              file=sys.stderr, flush=True)
    _save(collector, npz_path, {
        "partial": False,
        "capture": report["capture"],
        "arm": report["arm"],
        "force_null": report["force_null"],
        "cells_yx": [
            int(value) for value in corpus.resolve_spec(
                row, report["format_row_id"]).layout.cells_yx],
        "cell_dots": int(corpus.resolve_spec(
            row, report["format_row_id"]).cell_dots),
        "codec_id": report["codec_id"],
        "format_row_id": report["format_row_id"],
        "capture_sha256": report["capture_sha256"],
        "state_sha256": report["state_sha256"],
        "color_payload_policy_id": report["color_payload_policy_id"],
        "tree_state": report["tree_state_after"],
    })
    report["instrumented"] = (
        "regmap dense/census measurement passes ran inside this replay — "
        "wall_s/cpu_s/peak_rss are NOT comparable to any arm row; "
        "certificate counts are unaffected (production result returned "
        "verbatim)")
    ab_runner._write(
        report, ab_runner._run_path(row, "replay", "regmap", False))
    print(json.dumps({
        "capture": row.key,
        "lanes": len(collector.lane_ids),
        "census_lanes": list(census_lanes),
        "anchor_rows": len(collector.anchors),
        "window_rows": len(collector.windows),
        "spy_pass_failures": len(collector.spy_pass_failures),
        "dense_budget": int(args.dense_budget),
        "wall_s": round(time.perf_counter() - started, 1),
        "npz": str(npz_path),
    }))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.regmap", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(
        "run", help="one instrumented LIVE replay -> regmap NPZ")
    run.add_argument("--capture", required=True,
                     help="corpus capture key, e.g. xerox-c2-cmy7")
    run.add_argument("--dense-budget", type=int,
                     default=DEFAULT_DENSE_BUDGET,
                     help="bin-left census budget for the spy-side dense "
                          "pass; must be a multiple of the production "
                          f"budget (default {DEFAULT_DENSE_BUDGET})")
    run.add_argument("--census-lane", action="append", default=["auto"],
                     help="lane ids for the full-furniture census pass "
                          "(repeatable; 'auto' = first + last ordinary "
                          "lane)")
    run.add_argument("--lane", action="append", default=[],
                     help="restrict the replay to these lane ids "
                          "(repeatable)")
    run.add_argument("--workers", type=int, default=None,
                     help="pooled-kernel worker count (execution-only)")
    run.add_argument("--overwrite", action="store_true")
    run.set_defaults(handler=cmd_run)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
