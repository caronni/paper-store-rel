"""The two cheap offset estimators: NCC against what the receiver knows.

Both are the PLANE-FIELDS W4 tier-i probe (``_probe.probe_tile``) applied
to different templates, and both report in PAGE print dots relative to
the committed pose:

* :func:`neighbour_offsets` — estimator (a).  Every fully certified
  neighbour's exact printed cells, re-encoded from its certificate,
  NCC-locked against the scan, then INVERSE-DISTANCE interpolated to the
  failed tile.
* :func:`own_furniture_offset` — estimator (c).  The failed tile's OWN
  known cells only: word sites, dust, and any certified sibling plane.
  For a Y-only failure that is dust alone (~14 ink cells), which is
  exactly the "Y dust is noise" claim under test.

:func:`residual_page_dots` is the bridge between the two frames.  The
probes measure against the committed POSE; the swim sweeps offsets
relative to the arm's own ``PlaneResidual`` prediction.  Subtracting this
number turns a probe reading into the quantity the swim grid sweeps.
"""
from __future__ import annotations

import numpy as np

from . import _probe, _swim_region
from ._probe import PLANE_NAMES, TileJob
from ._swim_inputs import PLANES


def probe_job(spec, pose, address, records, *, planes, mask_unknown: bool):
    """One ``TileJob`` for the W4 probe at a committed pose.

    ``mask_unknown`` builds the OWN-FURNITURE template: cells whose
    component is not known (payload cells of an uncertified stream) are
    zeroed, so the model is exactly the ink the receiver already knows —
    word sites, dust, and any certified sibling plane.
    """
    from holo.receive.color_projection import project_certified_color_tile

    projection = project_certified_color_tile(records, spec, address)
    bits = np.asarray(projection.component_bits, np.uint8).copy()
    known = np.asarray(projection.known_mask, np.bool_)
    if mask_unknown:
        bits[~known] = 0
    return TileJob(
        page=address[0], tile_y=address[1], tile_x=address[2],
        planes=tuple(planes),
        native_affine=tuple(float(v) for v in pose.native_affine),
        bits=bits,
        known_all=bool(all(known[..., plane].all() for plane in planes)),
        pose_id=pose.pose_id, lane_id=pose.lane_id,
        pose_quality=float(pose.quality), cell_dots=int(spec.cell_dots))


def fit_crosstalk_for(spec, scan_path, pose_by_tile, certificates_by_address,
                      index, *, count: int = 24) -> tuple[float, float]:
    """The B-channel crosstalk coefficients, fitted from certified tiles.

    ``_probe.fit_crosstalk`` is regmap-gt's ``B ~ a*R + b*G`` least
    squares; it is re-fitted per capture from that capture's own
    certified tiles so the instrument imports no constant from the
    supervised measurement it is checked against.  The candidate tiles
    are spread across the page rather than taken from one corner.
    """
    addresses = [address for address in sorted(pose_by_tile)
                 if len(index.get(address, set())) == len(PLANES)]
    if not addresses:
        raise SystemExit("no fully certified tile carries a committed pose")
    step = max(1, len(addresses) // count)
    jobs = [probe_job(spec, pose_by_tile[address], address,
                      certificates_by_address.get(address, ()),
                      planes=(0, 1, 2), mask_unknown=False)
            for address in addresses[::step]][:count]
    return _probe.fit_crosstalk(jobs, str(scan_path))


def neighbour_offsets(spec, scan_path, crosstalk, pose_by_tile,
                      certificates_by_address, index, address, plane,
                      *, radius: int, min_neighbours: int) -> dict:
    """(a): certified neighbours probed, then inverse-distance interpolated.

    INTERPOLATOR (stated per the brief): inverse distance in TILE space,
    weight ``1 / d`` over every fully certified tile within ``radius``
    whose probe locked, radius grown one ring at a time until at least
    ``min_neighbours`` usable probes exist.
    """
    page, tile_y, tile_x = address
    samples: list[tuple[float, float, float]] = []
    used: list[dict] = []
    for ring in range(1, radius + 1):
        for dy in range(-ring, ring + 1):
            for dx in range(-ring, ring + 1):
                if max(abs(dy), abs(dx)) != ring:
                    continue
                neighbour = (page, tile_y + dy, tile_x + dx)
                if len(index.get(neighbour, set())) != len(PLANES):
                    continue
                pose = pose_by_tile.get(neighbour)
                if pose is None:
                    continue
                job = probe_job(
                    spec, pose, neighbour,
                    certificates_by_address.get(neighbour, ()),
                    planes=(0, 1, 2), mask_unknown=False)
                result = _probe.probe_tile(job, str(scan_path), crosstalk)
                entry = (result.get("planes") or {}).get(PLANE_NAMES[plane])
                if entry is None or "offset_dots_xy" not in entry:
                    continue
                distance = float(np.hypot(dy, dx))
                samples.append((distance, *entry["offset_dots_xy"]))
                used.append({
                    "tile_y": neighbour[1], "tile_x": neighbour[2],
                    "distance_tiles": distance,
                    "offset_dots_xy": entry["offset_dots_xy"],
                    "corr": entry["corr"], "ratio": entry["ratio"]})
        if len(samples) >= min_neighbours:
            break
    if not samples:
        return {"n_neighbours": 0, "offset_dots_xy": None, "used": []}
    weights = np.asarray([1.0 / row[0] for row in samples])
    values = np.asarray([[row[1], row[2]] for row in samples])
    offset = (weights[:, None] * values).sum(axis=0) / weights.sum()
    return {"n_neighbours": len(samples),
            "offset_dots_xy": [float(offset[0]), float(offset[1])],
            "used": used}


def own_furniture_offset(spec, scan_path, crosstalk, pose, address,
                         records, plane) -> dict:
    """(c): the failed tile's own KNOWN cells, NCC-locked."""
    job = probe_job(spec, pose, address, records,
                    planes=(0, 1, 2), mask_unknown=True)
    known_cells = int(np.count_nonzero(job.bits[..., plane]))
    result = _probe.probe_tile(job, str(scan_path), crosstalk)
    entry = (result.get("planes") or {}).get(PLANE_NAMES[plane])
    if entry is None or "offset_dots_xy" not in entry:
        return {"known_ink_cells": known_cells, "offset_dots_xy": None,
                "error": result.get("error") or entry}
    return {"known_ink_cells": known_cells,
            "offset_dots_xy": entry["offset_dots_xy"],
            "corr": entry["corr"], "ratio": entry["ratio"],
            "peak": entry["peak"], "src": entry["src"]}


def residual_page_dots(fit, spec, ordinal: int, plane: int) -> list[float]:
    """The delta = 0 sampling offset of one window/plane, in PAGE dots.

    The probes measure against the committed POSE; the swim measures
    against the arm's ``PlaneResidual`` prediction.  This is the bridge:
    a probe offset MINUS this number is the same quantity the swim grid
    sweeps.
    """
    if not fit.base_is_residual:
        return [0.0, 0.0]
    row = fit.rows[ordinal]
    fraction = (row.page_cells_yx[:, 0].astype(np.float64)
                / spec.layout.cells_yx[0])
    local = fit.residuals[plane].offsets(fraction).mean(axis=0)
    basis = np.linalg.inv(_swim_region.page_to_local_dots(row.patch))
    page = basis @ local
    return [float(page[0]), float(page[1])]


__all__ = ["fit_crosstalk_for", "neighbour_offsets",
           "own_furniture_offset", "probe_job", "residual_page_dots"]
