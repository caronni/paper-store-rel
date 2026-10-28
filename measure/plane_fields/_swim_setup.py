"""Target selection and committed geometry for the swim pilot.

Everything the pilot needs before a single pixel is sampled:

* which uncertified ``(tile, stream)`` slots to work on, and which
  CERTIFIED tiles to re-decode with one certificate withheld (the
  reproduction controls — see :func:`select_controls` for the
  fair-footing rule that makes a control mean something);
* which LANE to replay: a tile attempt unions blocks across CAPTURES
  within ONE lane (``tile_attempt_view`` refuses mixed lane ids), so the
  pilot commits to a single lane and reports it;
* the committed placements, re-derived through the production seam
  ``place.place_committed``, and the per-lane rasters, materialised
  through the production cascade.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import _swim_region
from ._swim_inputs import DEAD_BANDS, PLANES

PAGE = 0
#: The stream a reproduction control withholds and re-decodes.  Only that
#: ONE certificate is withheld, so the control tile presents to the
#: detector exactly as a Y-only residue tile does: C and M certified and
#: conditioning, Y open.
CONTROL_STREAM = "Y"


@dataclass(frozen=True, slots=True)
class Target:
    """One uncertified ``(tile, stream)`` slot the pilot will work on."""

    page: int
    tile_y: int
    tile_x: int
    stream: str
    plane: int
    band: str                    # dead | clear
    role: str                    # target | reproduction-control
    siblings_certified: tuple[str, ...]

    @property
    def address(self) -> tuple[int, int, int]:
        return (self.page, self.tile_y, self.tile_x)


def certified_index(certificates) -> dict[tuple[int, int, int], set[str]]:
    rows: dict[tuple[int, int, int], set[str]] = {}
    for record in certificates:
        rows.setdefault(
            (int(record.page), *(int(v) for v in record.tile_yx)),
            set()).add(record.stream_id)
    return rows


def residue_by_column(index, tiles_yx) -> dict[str, list[int]]:
    rows, columns = tiles_yx
    counts = {stream: [0] * columns for stream in PLANES}
    for tile_y in range(rows):
        for tile_x in range(columns):
            have = index.get((PAGE, tile_y, tile_x), set())
            for stream in PLANES:
                if stream not in have:
                    counts[stream][tile_x] += 1
    return counts


def select_targets(index, tiles_yx, *, n_tiles: int, n_clear: int,
                   n_controls: int, seed: int) -> tuple[Target, ...]:
    """Y-dominated residue slots, plus clear-band and reproduction controls.

    Deterministic: the residue is enumerated in canonical address order
    and sampled on an explicit seed, so a rerun picks the same tiles.
    """
    rows, columns = tiles_yx
    dead: list[Target] = []
    clear: list[Target] = []
    other: list[Target] = []
    certified: list[tuple[int, int, int]] = []
    for tile_y in range(rows):
        for tile_x in range(columns):
            address = (PAGE, tile_y, tile_x)
            have = index.get(address, set())
            missing = [row for row in PLANES if row not in have]
            if not missing:
                certified.append(address)
                continue
            band = "dead" if tile_x in DEAD_BANDS else "clear"
            for stream in missing:
                row = Target(
                    PAGE, tile_y, tile_x, stream, PLANES.index(stream),
                    band, "target", tuple(sorted(have)))
                if stream != "Y":
                    other.append(row)
                elif band == "dead":
                    dead.append(row)
                else:
                    clear.append(row)

    rng = np.random.default_rng(seed)

    def take(pool: list[Target], count: int) -> list[Target]:
        if count <= 0 or not pool:
            return []
        picks = rng.choice(len(pool), size=min(count, len(pool)),
                           replace=False)
        return [pool[int(index_)] for index_ in sorted(picks)]

    del certified, n_controls
    chosen = take(other, 1) if other else []
    chosen += take(clear, n_clear)
    chosen += take(dead, max(0, n_tiles - len(chosen)))
    return tuple(chosen)


def lane_of_certificate(facts) -> dict[str, str]:
    """certificate id -> the lane id that MINTED it (the level it landed at)."""
    rows: dict[str, str] = {}
    for capture in facts.captures:
        for lane_id, ids in zip(capture.level_lane_ids,
                                capture.level_certificate_ids, strict=True):
            for identity in ids:
                rows[identity] = lane_id
    return rows


def select_controls(facts, index, lane, targets, *, count: int, radius: int,
                    seed: int) -> tuple[Target, ...]:
    """Certified tiles the pilot re-decodes with their certificates WITHHELD.

    Fair-footing rule: a control must have been earned AT the lane the
    pilot replays (most of sheet I's certificates were minted at the
    COARSE ``l00`` level and were suppressed before ``l02`` ever sampled
    them, so those tiles would test the lane rather than the harness).
    Controls are also drawn from inside the restricted fit population, so
    they exercise exactly the detector the targets are judged by.
    """
    minted_at = lane_of_certificate(facts)
    stream_lanes: dict[tuple[int, int, int], set[str]] = {}
    for record in facts.certificates:
        if record.stream_id != CONTROL_STREAM:
            continue
        stream_lanes.setdefault(
            (int(record.page), *(int(v) for v in record.tile_yx)),
            set()).add(minted_at.get(record.certificate_id, ""))
    near = {
        (PAGE, ty, tx)
        for row in targets
        for ty in range(row.tile_y - radius, row.tile_y + radius + 1)
        for tx in range(row.tile_x - radius, row.tile_x + radius + 1)}
    eligible = [
        address for address in sorted(near)
        if len(index.get(address, set())) == len(PLANES)
        and lane.lane_id in stream_lanes.get(address, set())]
    fallback = False
    if not eligible:
        fallback = True
        eligible = [address for address in sorted(near)
                    if len(index.get(address, set())) == len(PLANES)]
    if not eligible or count <= 0:
        return ()
    rng = np.random.default_rng(seed + 1)
    picks = rng.choice(len(eligible), size=min(count, len(eligible)),
                       replace=False)
    return tuple(
        Target(*eligible[int(pick)], CONTROL_STREAM,
               PLANES.index(CONTROL_STREAM),
               "dead" if eligible[int(pick)][2] in DEAD_BANDS else "clear",
               ("reproduction-control-offlane" if fallback
                else "reproduction-control"),
               tuple(sorted(index.get(eligible[int(pick)], ()))))
        for pick in sorted(picks))


# --------------------------------------------------------------------------
# committed geometry
# --------------------------------------------------------------------------
def lane_rank(lane) -> tuple:
    """Ordinary lanes first, finest sampling first — the W0 pose rule."""
    from holo.receive.cascade import lane_kind

    kind = lane_kind(lane)
    return (0 if kind == "ordinary" else 1,
            -lane.target_ppc_num / lane.target_ppc_den)


def choose_lane(facts, targets, *, forced: str | None = None):
    """The lane whose committed poses cover the most targets in every capture.

    A tile attempt unions blocks across CAPTURES within ONE lane
    (``tile_attempt_view`` refuses mixed lane ids), so the pilot commits
    to a single lane and reports it.
    """
    plan = facts.captures[0].plan
    wanted = {row.address for row in targets}
    best = None
    for lane in sorted(plan, key=lane_rank):
        if forced is not None and lane.lane_id != forced:
            continue
        covered = []
        for capture in facts.captures:
            poses = facts.poses_for(capture.source_sha256, lane.lane_id)
            spans = set()
            for row in poses:
                if row.placement_outcome not in ("accepted", "redundant"):
                    continue
                spans |= pose_span(row)
            covered.append(len(wanted & spans))
        if min(covered) == 0:
            continue
        # FULL coverage first (a lane that carries every target in every
        # capture), then the W0 pose rule: ordinary lanes, finest first.
        score = (0 if min(covered) == len(wanted) else 1,
                 lane_rank(lane), -min(covered))
        if best is None or score < best[0]:
            best = (score, lane, tuple(covered))
    if best is None:
        raise SystemExit("no lane's committed poses cover every target")
    return best[1], best[2]


def pose_span(row) -> set[tuple[int, int, int]]:
    """The tile addresses one committed pose's window fully contains."""
    height, width = (int(value) for value in row.window_shape_yx_cells)
    if int(row.rot90) % 2:
        height, width = width, height
    y0, x0 = (int(value) for value in row.cell_origin_yx)
    y1, x1 = y0 + height, x0 + width
    return {
        (int(row.page), tile_y, tile_x)
        for tile_y in range(max(0, y0) // 64, (max(0, y1) + 63) // 64)
        for tile_x in range(max(0, x0) // 64, (max(0, x1) + 63) // 64)
        if y0 <= tile_y * 64 and y1 >= tile_y * 64 + 64
        and x0 <= tile_x * 64 and x1 >= tile_x * 64 + 64}


def build_placements(facts, spec, capture, lane, raster):
    """``place.place_committed`` over the lane's FULL committed pose set.

    The full set matters: ``place_committed`` derives the region aperture
    from the MEDIAN committed pose pitch, so a subset would re-derive a
    different aperture than the archived lane did.
    """
    from holo.receive.place import place_committed

    quarantined = set(capture.quarantined_by_lane.get(lane.lane_id, ()))
    poses = tuple(
        row for row in facts.poses_for(capture.source_sha256, lane.lane_id)
        if row.placement_outcome in ("accepted", "redundant")
        and int(row.patch_id) not in quarantined)
    regions = facts.regions_for(capture.source_sha256, lane.base_lane_id)
    if not poses or not regions:
        raise SystemExit(
            f"{capture.source_sha256[:12]}: lane {lane.lane_id} has no "
            f"committed geometry ({len(poses)} poses, {len(regions)} regions)")
    result = place_committed(raster, spec, poses=poses, regions=regions)
    by_patch = {int(row.patch_id): row for row in poses}
    return result.payload_placements, by_patch


class LaneRasters:
    """Exact per-lane derived rasters, the production cascade's own path."""

    def __init__(self, spec, capture, scan_path) -> None:
        from holo.receive.runtime_model import ScheduleContext
        from holo.receive.scale_space import ScaleSchedule
        from holo.receive.scan import open_capture
        from holo.receive.session import CaptureFacts

        native = open_capture(str(scan_path), capture.dpi)
        if native.source_sha256 != capture.source_sha256:
            raise SystemExit(
                f"{scan_path}: sha {native.source_sha256[:12]}… is not the "
                f"state's capture {capture.source_sha256[:12]}…")
        facts = CaptureFacts(
            capture.source_sha256, capture.dpi, capture.dtype,
            capture.shape_yx, capture.channels)
        self.native = native
        self._schedule = ScaleSchedule.auto(native.dpi, spec.cell_dots)
        self._levels = {level.label: level for level in self._schedule.levels}
        self._context = ScheduleContext(
            spec, native, facts, None, _unsupported, _unsupported,
            _unsupported, lambda *args, **kwargs: None, lambda: False)

    def for_lane(self, lane):
        from holo.receive.cascade import _materialize

        return _materialize(self._context, self._levels[lane.base_lane_id])

    def release(self) -> None:
        from holo.receive.cascade import release_derived_lanes

        release_derived_lanes(self.native)


def _unsupported(*args, **kwargs):
    raise RuntimeError("the swim pilot drives no lanes, evidence or barriers")


def restricted_placements(placements, targets, radius: int):
    """Placements within ``radius`` tiles of any target, grouped by region.

    ``radius < 0`` keeps the WHOLE region — the faithful production fit
    population, at its full memory and wall cost.
    """
    wanted = {row.address for row in targets}
    grouped: dict[int, list] = {}
    for patch in placements:
        if radius < 0:
            grouped.setdefault(int(patch.region_index), []).append(patch)
            continue
        tiles = _swim_region.patch_tiles(patch)
        near = any(
            abs(ty - wy) <= radius and abs(tx - wx) <= radius and pg == wp
            for pg, ty, tx in tiles for wp, wy, wx in wanted)
        if near:
            grouped.setdefault(int(patch.region_index), []).append(patch)
    return {key: tuple(value) for key, value in grouped.items()}


def best_pose_by_tile(poses, lane_id: str) -> dict:
    """Best committed pose per fully contained tile, one lane."""
    best: dict[tuple[int, int, int], object] = {}
    for row in poses:
        if row.lane_id != lane_id or row.placement_outcome not in (
                "accepted", "redundant"):
            continue
        for address in pose_span(row):
            current = best.get(address)
            if current is None or float(row.quality) > float(current.quality):
                best[address] = row
    return best


__all__ = [
    "CONTROL_STREAM", "LaneRasters", "PAGE", "Target", "build_placements",
    "certified_index", "choose_lane", "lane_of_certificate", "lane_rank",
    "residue_by_column", "restricted_placements", "select_controls",
    "select_targets", "best_pose_by_tile",
]
