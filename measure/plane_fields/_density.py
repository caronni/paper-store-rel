"""E5 machinery: the production probe pass at three declared densities.

INDEPENDENT-PLANES §6 P2b E5 ("measure, don't assume").  The subject is
:meth:`holo.receive.color_field.PlaneFieldBuilder.add_certified_probes`
itself -- this module RE-DERIVES the inputs the production pass gets on
one archived ``(capture, lane)`` of the W6 qualification state and then
calls the production method, once per :class:`ProbeMode`.  Nothing here
re-implements a measurement; the only thing it owns is the plumbing that
``collect_color_evidence`` would otherwise have built around it.

The plumbing is the pool-law window classification (``color_pool``): a
window is LABEL-ONLY when none of its payload cells lies on a tile with
an open stream -- certified-complete, contributing no anchors at all
(§6.1 pitfall 3) -- and MIXED otherwise.  That predicate is imported,
not restated.  Until 2026-08-23 it was also the probe pass's eligibility
rule; E5b measures what dropping it buys, so every region here carries
BOTH sets and each run declares which kind it is offered.

Two deviations from a live lane, both deliberate and both identical
across the three densities being compared:

* ANCHORS ARE NOT COLLECTED.  ``add_anchors`` needs the whole photometric
  path (known-field derivation, crops, ``_fit_registration``), which is
  most of a decode; E5 varies probe density, so the field here is
  probes-only and the numbers are about the probe pass alone.
* ONE SOLVE, at the end.  Production re-solves per region so an early
  region sees less evidence; there is one payload region per lane on this
  sheet, so the difference is nil here and the adoption verdicts are
  read off the finished field.

READ-ONLY: the state, the scan TIFFs and the regmap-gt JSON are opened;
nothing is ever written outside ``scratch/plane-fields/p2/e5/``.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ._swim_inputs import DEAD_BANDS, PLANES


@dataclass(frozen=True, slots=True)
class _RowStub:
    """What ``region_offsets`` reads off a row: its cells and its patch.

    The production call passes ``_Rows``; the adoption path touches
    ``page_cells_yx`` and ``patch.segment.rot_k`` and nothing else, and
    building real ``_Rows`` would mean running the known-field
    derivation this instrument deliberately skips.  Same stub the
    module's own tests use (``tests/holo/test_color_field.py``).
    """

    page_cells_yx: np.ndarray
    patch: object


#: The two window kinds a region's placements split into under the pool
#: law.  ``label-only`` = certified-complete, the E5 footing; ``mixed`` =
#: still owes payload work, and was REFUSED by the probe pass until
#: 2026-08-23 (INDEPENDENT-PLANES §4.G).  ``all`` is the union, which is
#: what production offers now.
WINDOW_KINDS = ("label-only", "mixed")


@dataclass(frozen=True, slots=True)
class RegionWindows:
    """One region's classified windows, ready for the probe pass."""

    region_index: int
    page: int
    windows: tuple
    is_open: tuple[bool, ...]
    rows: tuple[_RowStub, ...]

    @property
    def n_open(self) -> int:
        return int(sum(self.is_open))

    def select(self, kind: str) -> tuple:
        """The windows of one kind, in the caller's canonical order."""
        if kind == "all":
            return self.windows
        if kind not in WINDOW_KINDS:
            raise ValueError(f"unknown window kind {kind!r}")
        want = kind == "mixed"
        return tuple(
            window for window, is_open in zip(self.windows, self.is_open)
            if is_open == want)

    def kind_of(self, ordinal: int, kind: str) -> str:
        """The KIND of the ``ordinal``-th window of a selected set."""
        if kind != "all":
            return kind
        return "mixed" if self.is_open[ordinal] else "label-only"


def pick_lane(capture, forced: str | None):
    """The finest ORDINARY lane with committed poses -- the W0 pose rule.

    Ordinary first (a mop-up or refinement lane re-poses only what it was
    handed), then the finest sampling, because the probe pass measures
    subpixel registration and a 2 px/cell lane has half a print dot of
    it to work with.
    """
    from holo.receive.cascade import lane_kind

    ordered = sorted(
        capture.plan,
        key=lambda lane: (0 if lane_kind(lane) == "ordinary" else 1,
                          -lane.target_ppc_num / lane.target_ppc_den))
    for lane in ordered:
        if forced is not None:
            if lane.lane_id == forced:
                return lane
            continue
        return lane
    raise SystemExit(f"no lane {forced!r} in the archived plan")


def classify_windows(spec, certificates, placements) -> tuple[
        tuple[RegionWindows, ...], frozenset]:
    """The pool-law split, verbatim from ``collect_color_evidence``.

    Returns the per-region window sets and the fully-certified address
    set (which is also what the builder reports as ``done_tiles``).
    """
    from holo.receive._payload_sampling import _window_rows
    from holo.receive.color_field import ProbeWindow
    from holo.receive.color_pool import (
        _emission_mask,
        _payload_cell_mask,
        fully_certified_color_addresses,
    )

    fully = fully_certified_color_addresses(certificates, spec)
    tiles_x = int(spec.layout.tiles_yx[1])
    suppressed = {
        page: np.asarray(sorted(
            ty * tiles_x + tx for pg, ty, tx in fully if pg == page),
            dtype=np.int64)
        for page in sorted({address[0] for address in fully})
    }
    grouped: dict[tuple[int, int], list] = {}
    for patch in placements:
        grouped.setdefault(
            (int(patch.region_index), int(patch.candidate.page)),
            []).append(patch)

    regions: list[RegionWindows] = []
    for (region_index, page), patch_rows in sorted(grouped.items()):
        patches = tuple(sorted(patch_rows, key=lambda row: int(row.patch_id)))
        windows = []
        open_flags = []
        rows = []
        for patch in patches:
            aligned = _window_rows(patch, spec)
            emit = _emission_mask(
                spec, page, aligned.page_cells_yx, suppressed)
            is_open = bool(np.any(
                _payload_cell_mask(spec, aligned.page_cells_yx) & emit))
            rows.append(_RowStub(aligned.page_cells_yx, patch))
            open_flags.append(is_open)
            windows.append(ProbeWindow(
                patch, page, aligned.local_cells_yx, aligned.page_cells_yx))
        regions.append(RegionWindows(
            region_index, page, tuple(windows), tuple(open_flags),
            tuple(rows)))
    return tuple(regions), fully


def projection_source(spec, certificates, allowed: frozenset | None = None):
    """The production GT source, optionally narrowed to a tile stratum.

    ``allowed`` is how E5 runs a density on a SUBSET of certified tiles
    without forking the production selection: a tile outside the stratum
    simply has no certified projection, which is the same refusal an
    uncertified tile gets.
    """
    from holo.receive.color_field import certified_projection_source
    from holo.receive.color_pool import fully_certified_color_addresses

    index: dict[tuple[int, int, int], list] = {}
    for record in certificates:
        index.setdefault(
            (int(record.page), *(int(v) for v in record.tile_yx)),
            []).append(record)
    fully = fully_certified_color_addresses(certificates, spec)
    if allowed is not None:
        fully = frozenset(fully & allowed)
    return certified_projection_source(
        spec, {key: tuple(value) for key, value in index.items()},
        {}, fully), fully


# --------------------------------------------------------------------------
# one density
# --------------------------------------------------------------------------
def run_density(spec, raster, regions, projection_for, config, done_tiles,
                kind: str = "label-only"):
    """Accumulate every region's probes, solve once, read the verdicts."""
    from holo.receive.color_field import PlaneFieldBuilder

    builder = PlaneFieldBuilder(spec, config, done_tiles=done_tiles)
    started = time.perf_counter()
    for region in regions:
        builder.add_certified_probes(
            raster, region.select(kind), projection_for)
    probe_wall_seconds = time.perf_counter() - started
    builder.solve()
    adoption = []
    for region in regions:
        _overrides, adopted = builder.region_offsets(region.page, region.rows)
        adoption.append(adopted)
    return builder, builder.report(), tuple(adoption), probe_wall_seconds


def adoption_detail(field, regions, config) -> list[dict]:
    """The three quantities the adoption gate actually tests, per plane.

    ``PlaneFieldBuilder._adoption`` returns booleans; a density that
    adopts one more plane than another has usually moved ONE of these
    three across ONE threshold, and the report should say which.  The
    arithmetic is restated here (coverage fraction, median posterior sd,
    median predicted magnitude, over the region's window centres)
    because the production method returns only the verdict.
    """
    rows: list[dict] = []
    for region in regions:
        lookups = []
        for row in region.rows:
            cells = np.asarray(row.page_cells_yx, np.float64)
            lookups.append(field.lookup_cells(
                region.page,
                (float(cells[:, 0].mean()), float(cells[:, 1].mean()))))
        entry: dict = {"region_index": region.region_index,
                       "page": region.page, "windows": len(lookups),
                       "planes": {}}
        for plane, name in enumerate(PLANES):
            affines = [look[plane] for look in lookups]
            covered = [a for a in affines if a.covered]
            fraction = len(covered) / max(1, len(affines))
            detail = {
                "coverage_fraction": round(fraction, 4),
                "coverage_gate": round(config.min_coverage_fraction, 3),
            }
            if covered:
                detail["median_uncertainty_dots"] = round(float(np.median(
                    [a.uncertainty_dots for a in covered])), 4)
                detail["median_magnitude_dots"] = round(float(np.median(
                    [float(np.hypot(*a.delta_dots_xy)) for a in covered])), 4)
            detail["uncertainty_gate"] = config.max_uncertainty_dots
            detail["magnitude_gate"] = config.min_delta_dots
            entry["planes"][name] = detail
        rows.append(entry)
    return rows


def site_census(spec, regions, projection_for, config, kind="all") -> dict:
    """Which certified tiles each density can even PLACE a probe on.

    Site selection only -- no NCC, no raster read.  A SQUARE density's
    reach is a property of the window geometry: an eligible block must
    lie wholly inside ONE window's audited cells and wholly inside ONE
    certified tile, so a template as wide as the tile itself needs the
    WHOLE tile inside one window, which a window that is not tile-aligned
    mostly does not offer.  A TILE_FRAGMENT has no such constraint --
    which is exactly what this census exists to price, before a probe is
    spent.

    Split by WINDOW KIND as well as totalled, so the effect of offering
    the pass MIXED windows (INDEPENDENT-PLANES §4.G, the predicate
    dropped 2026-08-23) is visible on its own.  Template AREAS come back
    too: a fragment's cost is its bounding box, not a fixed edge.
    """
    from holo.receive.color_probes import probe_sites_for_window

    tiles_x = int(spec.layout.tiles_yx[1])
    started = time.perf_counter()
    sites = 0
    areas: list[int] = []
    tiles: set[tuple[int, int, int]] = set()
    by_kind = {name: {"sites": 0, "tiles": set(), "windows": 0}
               for name in WINDOW_KINDS}
    for region in regions:
        for ordinal, window in enumerate(region.select(kind)):
            found = probe_sites_for_window(
                window, ordinal, config.probe_mode,
                lambda address: projection_for(address) is not None,
                tiles_x,
                block_cells=int(config.probe_block_cells),
                bins_per_tile=int(config.bins_per_tile))
            reached = {(site.page, site.page_y // 64, site.page_x // 64)
                       for site in found}
            sites += len(found)
            areas.extend(
                site.height_cells * site.width_cells for site in found)
            tiles |= reached
            row = by_kind[region.kind_of(ordinal, kind)]
            row["sites"] += len(found)
            row["tiles"] |= reached
            row["windows"] += 1
    return {
        "n_sites": sites,
        "tiles": frozenset(tiles),
        "template_cells": np.asarray(areas, np.int64),
        "by_kind": {
            name: {"sites": row["sites"], "tiles": frozenset(row["tiles"]),
                   "windows": row["windows"]}
            for name, row in by_kind.items()},
        "selection_seconds": time.perf_counter() - started,
    }


def pose_residual_summary(report) -> dict:
    """What the plane-COMMON probe residual would offer a pose writer.

    Per WINDOW: the median plane-common offset the certified probes
    measured in that window's own LOCAL frame, and the spread of the
    contributing sites around it.  A window whose tiles AGREE on a shift
    is a pose correction waiting to be fed back; a window whose tiles
    disagree is noise, and the ratio is the number that tells them apart.
    Nothing here is applied -- P5 writer work, deliberately not built
    (docs/COMPOSITE-POSE-DESIGN.md §6).
    """
    rows = report.window_pose_residuals
    if not rows:
        return {"windows": 0}
    magnitude = np.asarray([row.magnitude_dots for row in rows], np.float64)
    spread = np.asarray(
        [float(np.hypot(row.spread_dx_dots, row.spread_dy_dots))
         for row in rows], np.float64)
    sites = np.asarray([row.n_sites for row in rows], np.int64)
    multi = sites > 1
    consistent = (
        float(np.mean(spread[multi] < 0.5 * magnitude[multi]))
        if multi.any() else float("nan"))
    return {
        "windows": len(rows),
        "sites_total": int(sites.sum()),
        "sites_per_window_median": float(np.median(sites)),
        "magnitude_dots": _spread(magnitude),
        "within_window_spread_dots": _spread(spread),
        "dx_dots": _spread(
            np.asarray([row.median_dx_dots for row in rows], np.float64)),
        "dy_dots": _spread(
            np.asarray([row.median_dy_dots for row in rows], np.float64)),
        "windows_with_multiple_sites": int(multi.sum()),
        "fraction_consistent": consistent,
    }


def _spread(values: np.ndarray) -> dict:
    finite = values[np.isfinite(values)]
    if not finite.size:
        return {"n": 0}
    return {
        "n": int(finite.size),
        "median": float(np.median(finite)),
        "p10": float(np.percentile(finite, 10)),
        "p90": float(np.percentile(finite, 90)),
        "max": float(finite.max()),
        "mean": float(finite.mean()),
    }


def field_tile_relative(field, page: int, tiles_yx: tuple[int, int]) -> list:
    """``(tile_y, tile_x, dY_rel_x)`` wherever all three planes are covered.

    The per-TILE form of the column profile: on a sparse stratum a
    column median is built from one or two tiles and says little, while
    the tile-by-tile residual against the supervised column value stays
    meaningful at any density.
    """
    rows: list[tuple[int, int, float]] = []
    for tile_y in range(tiles_yx[0]):
        for tile_x in range(tiles_yx[1]):
            affines = field.lookup_tile_index(page, tile_y, tile_x)
            if not all(affine.covered for affine in affines):
                continue
            values = [float(affine.delta_dots_xy[0]) for affine in affines]
            rows.append((tile_y, tile_x,
                         values[2] - 0.5 * (values[0] + values[1])))
    return rows


def field_column_profile(field, page: int, tiles_yx: tuple[int, int]) -> dict:
    """Per-column medians of the SOLVED field -- the P1 worker's scoring.

    The V0 instrument scores raw per-column probe medians and never
    exercises ``PlaneDeltaField``; what E5 compares is what the receiver
    would actually apply, so every number here is a field LOOKUP at a
    tile centre, and only covered tiles count.
    """
    rows, columns = tiles_yx
    per_plane = {name: np.full(columns, np.nan) for name in PLANES}
    covered_count = {name: np.zeros(columns, np.int64) for name in PLANES}
    relative = np.full(columns, np.nan)
    for tile_x in range(columns):
        stacks: dict[str, list[float]] = {name: [] for name in PLANES}
        triples: list[tuple[float, float, float]] = []
        for tile_y in range(rows):
            affines = field.lookup_tile_index(page, tile_y, tile_x)
            values = []
            for plane, name in enumerate(PLANES):
                affine = affines[plane]
                if affine.covered:
                    stacks[name].append(float(affine.delta_dots_xy[0]))
                    covered_count[name][tile_x] += 1
                values.append(
                    float(affine.delta_dots_xy[0]) if affine.covered
                    else np.nan)
            if not any(np.isnan(values)):
                triples.append(tuple(values))
        for name in PLANES:
            if stacks[name]:
                per_plane[name][tile_x] = float(np.median(stacks[name]))
        if triples:
            block = np.asarray(triples, np.float64)
            relative[tile_x] = float(np.median(
                block[:, 2] - 0.5 * (block[:, 0] + block[:, 1])))
    return {
        "dC_x": per_plane["C"], "dM_x": per_plane["M"],
        "dY_x": per_plane["Y"], "dY_rel_x": relative,
        "covered_tiles": {name: covered_count[name].tolist()
                          for name in PLANES},
    }


# --------------------------------------------------------------------------
# the instrumented pass (what production discards)
# --------------------------------------------------------------------------
def instrumented_probes(spec, raster, regions, projection_for, config,
                        tiles: frozenset | None = None,
                        kind: str = "label-only") -> list[dict]:
    """Every probe's NCC quality and offset, floor rejections included.

    The SAME three production functions the pass calls, in the same
    order, with the results recorded instead of gated:
    ``probe_sites_for_window`` -> ``probe_template`` -> ``_rectified_ncc``.
    Restricted to ``tiles`` when the caller wants a matched subset (the
    per-probe precision comparison between densities).
    """
    from holo.receive.color_anchoring import _rectified_ncc
    from holo.receive.color_field import _rotate_delta_xy
    from holo.receive.color_probes import (
        probe_sites_for_window, probe_template, template_is_flat,
    )

    tiles_x = int(spec.layout.tiles_yx[1])
    block_cells = int(config.probe_block_cells)
    rows: list[dict] = []
    for region in regions:
        for ordinal, window in enumerate(region.select(kind)):
            sites = probe_sites_for_window(
                window, ordinal, config.probe_mode,
                lambda address: projection_for(address) is not None,
                tiles_x, block_cells=block_cells,
                bins_per_tile=int(config.bins_per_tile))
            for site in sites:
                address = site.address
                if tiles is not None and address not in tiles:
                    continue
                projected = projection_for(address)
                if projected is None:
                    continue
                template = probe_template(
                    window, site, projected, min_edge_cells=block_cells)
                if template is None:
                    rows.append({"page": address[0], "tile_y": address[1],
                                 "tile_x": address[2], "plane": -1,
                                 "outcome": "no_template"})
                    continue
                bits, weights = template
                inside = weights > 0.0
                cells = int(inside.sum())
                rot_k = int(window.patch.segment.rot_k)
                for plane in range(len(PLANES)):
                    entry = {"page": address[0], "tile_y": address[1],
                             "tile_x": address[2], "plane": plane,
                             "centre_y": site.centre_page_yx[0],
                             "centre_x": site.centre_page_yx[1],
                             "cells": cells,
                             "window_kind": region.kind_of(ordinal, kind)}
                    plane_bits = bits[..., plane]
                    if template_is_flat(plane_bits, inside):
                        entry["outcome"] = "constant_template"
                        rows.append(entry)
                        continue
                    measured = _rectified_ncc(
                        raster, window.patch, spec, site.centre_local_yx,
                        plane_bits, weights, plane)
                    if measured is None:
                        entry["outcome"] = "off_raster"
                        rows.append(entry)
                        continue
                    offset_dots_xy, quality = measured
                    page_offset = _rotate_delta_xy(
                        offset_dots_xy.reshape(1, 2), rot_k, inverse=False)[0]
                    entry["quality"] = float(quality)
                    entry["dx"] = float(page_offset[0])
                    entry["dy"] = float(page_offset[1])
                    entry["outcome"] = (
                        "accepted" if quality >= config.probe_min_quality
                        else "below_floor")
                    rows.append(entry)
    return rows


def per_site_relative(rows: list[dict]) -> list[dict]:
    """``dY_rel_x`` per SITE, from the three planes measured there.

    Reference-free by construction (the committed pose's own frame
    cancels), which is what makes a per-probe number comparable to the
    supervised per-column measurement.
    """
    sites: dict[tuple, dict] = {}
    for row in rows:
        if row.get("outcome") != "accepted":
            continue
        key = (row["page"], row["tile_y"], row["tile_x"],
               round(row["centre_y"], 3), round(row["centre_x"], 3))
        sites.setdefault(key, {})[row["plane"]] = row
    out: list[dict] = []
    for key, planes in sorted(sites.items()):
        if len(planes) != len(PLANES):
            continue
        out.append({
            "page": key[0], "tile_y": key[1], "tile_x": key[2],
            "dY_rel_x": (planes[2]["dx"]
                         - 0.5 * (planes[0]["dx"] + planes[1]["dx"])),
            "dCM_x": planes[0]["dx"] - planes[1]["dx"],
            "quality_min": min(planes[p]["quality"] for p in planes),
        })
    return out


def quality_summary(rows: list[dict], floor: float) -> dict:
    """The NCC-quality distribution a density produces, per plane."""
    summary: dict = {"outcomes": {}, "per_plane": {}}
    for row in rows:
        key = row["outcome"]
        summary["outcomes"][key] = summary["outcomes"].get(key, 0) + 1
    for plane, name in enumerate(PLANES):
        values = np.asarray(
            [row["quality"] for row in rows
             if row["plane"] == plane and "quality" in row], np.float64)
        measured = int(values.size)
        entry = {"measured": measured,
                 "below_floor": int((values < floor).sum()) if measured else 0}
        if measured:
            entry.update({
                "fraction_below_floor": float((values < floor).mean()),
                "min": float(values.min()),
                "p10": float(np.percentile(values, 10)),
                "median": float(np.median(values)),
                "p90": float(np.percentile(values, 90)),
                "max": float(values.max()),
            })
        summary["per_plane"][name] = entry
    return summary


__all__ = [
    "DEAD_BANDS", "WINDOW_KINDS", "RegionWindows", "adoption_detail",
    "classify_windows", "field_column_profile",
    "field_tile_relative", "instrumented_probes", "per_site_relative",
    "pick_lane", "pose_residual_summary", "projection_source",
    "quality_summary", "site_census", "run_density",
]
