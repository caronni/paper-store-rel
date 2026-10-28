"""Durable-record resume seed for the live view (RECEIVE-DESIGN v0.45).

A resumed invocation emits no survey/address events for levels committed by
earlier invocations, so the event-fed panes A (ACQUIRED) and C (ADDRESS)
started nearly empty while pane D rode the durable-state-fed barrier
snapshots.  The v0.45 declared ruling seeds both panes from the DURABLE
records the committed bootstrap already hands the viewer at
``session.open`` — the same records the D15 parked-inventory epilogue
derives from — before/alongside live events:

- pane A: ``SurveyRegionRecord`` support masks rebuilt through
  ``survey.region_from_record`` (the pinned reconstruction primitive) give
  the scrap outlines/boxes; region states derive exactly from
  ``PoseRecord`` rows (accepted/redundant -> placed), ``ParkedWindowRecord``
  rows (parked-for-mop-up), and the level artifact prefix (a committed
  address stage with neither -> unresolved); parked chips rebuild from the
  parked records' persisted lane-frame geometry.  No capture-preview
  underlay: preview pixels are not durable and are never re-read.
- pane C: durable ``BchConflictRecord`` rows seed exact sticky deep red;
  every tile covered by a committed placement's oriented window footprint
  seeds the v0.45 ``_WORD_SEEDED`` state (committed-addressed, word
  evidence not retained).  Neither green authority is durably provable —
  ``PoseRecord`` carries no route and ``KnownWord`` rows are transient —
  so the seed never fabricates a stronger state, and seeded tiles print
  no observed-site count (the count is a live fact; zero is never printed
  where the fact is unavailable).

Everything here is a pure function of the frozen durable records: no
pixels, no receiver objects, no clocks.  Builders run only inside the
viewer's ``session.open`` committed-snapshot branch, which exists only
when an observer opted in — headless runs and scalar-only observers never
reach this module (§10.6 timing neutrality).
"""
from __future__ import annotations

from ..survey import region_from_record
from ..types import ParkedWindowRecord, PoseRecord, SurveyRegionRecord
from .presentation import _WORD_CONFLICT, _WORD_SEEDED, PaneRenderer
from .scan_model import ScanFrame

# One colocated v1 tile is 64x64 cells (the format constant this package
# already assumes in `_paint_patch` and `_diagnostic_snapshots.payload`).
_TILE_CELLS = 64


def _region_index(region_id: str) -> int | None:
    """The survey-order region index carried by the durable region id.

    Region ids are minted as ``{capture}/{lane}/region-{index}`` and the
    M-level address product already relies on this suffix; live pane-A
    events (region open/complete, window facts) address regions by this
    index, so the seeded model must key identically.
    """
    _prefix, found, suffix = region_id.rpartition("region-")
    if not found or not suffix.isdigit():
        return None
    return int(suffix)


def seed_words(
    state: object, tiles_yx: tuple[int, int]
) -> dict[tuple[int, int, int], int]:
    """Pane-C seed: exact durable conflicts + committed placement cover.

    ``_WORD_SEEDED`` claims exactly what the record proves: the tile lies
    inside a committed placement's oriented window footprint (page cell
    origin + rot90-oriented window shape), so it has an assigned address.
    Whether its word sites were read, validated, or refused is not durable
    (§10.7: pilot reads and other word states are cold-unavailable), so no
    stronger state and no site count is reconstructed.  Deep red conflicts
    ARE durable (``BchConflictRecord``) and win as always.
    """
    tiles_y, tiles_x = int(tiles_yx[0]), int(tiles_yx[1])
    seeded: dict[tuple[int, int, int], int] = {}
    for pose in getattr(state, "poses", ()) or ():
        if not isinstance(pose, PoseRecord):
            continue
        height, width = pose.window_shape_yx_cells
        if pose.rot90 % 2:
            height, width = width, height
        y0, x0 = pose.cell_origin_yx
        ty0 = max(0, y0 // _TILE_CELLS)
        tx0 = max(0, x0 // _TILE_CELLS)
        ty1 = min(tiles_y, -((y0 + height) // -_TILE_CELLS))
        tx1 = min(tiles_x, -((x0 + width) // -_TILE_CELLS))
        for ty in range(ty0, ty1):
            for tx in range(tx0, tx1):
                seeded[(int(pose.page), ty, tx)] = _WORD_SEEDED
    for capture in getattr(state, "captures", ()) or ():
        for level in getattr(capture, "levels", ()) or ():
            address = getattr(level, "address", None)
            for conflict in getattr(address, "bch_conflicts", ()) or ():
                key = (int(conflict.page), int(conflict.tile_yx[0]),
                       int(conflict.tile_yx[1]))
                if 0 <= key[1] < tiles_y and 0 <= key[2] < tiles_x:
                    seeded[key] = _WORD_CONFLICT
    return seeded


def _seed_lane(capture: object,
               lanes_with_regions: set[str]) -> str | None:
    """The lane whose landscape pane A shows for this capture at resume.

    Prefer the base lane of the next uncommitted level — that is where the
    resumed invocation's live events (mop-up windows, refinement plans)
    will land, so the seeded frame matches the incoming lane-px geometry.
    A capture with nothing left (or whose next base never surveyed) falls
    back to its finest committed lane that has regions.
    """
    plan = tuple(getattr(capture, "plan", ()) or ())
    levels = tuple(getattr(capture, "levels", ()) or ())
    if len(levels) < len(plan):
        base = plan[len(levels)].base_lane_id
        if base in lanes_with_regions:
            return base
    for lane in reversed(plan[:len(levels)]):
        if lane.lane_id in lanes_with_regions:
            return str(lane.lane_id)
    return None


def _address_committed(capture: object, lane_id: str) -> bool:
    """Whether ``lane_id``'s level committed an address artifact."""
    plan = tuple(getattr(capture, "plan", ()) or ())
    levels = tuple(getattr(capture, "levels", ()) or ())
    for ordinal, lane in enumerate(plan[:len(levels)]):
        if lane.lane_id == lane_id:
            return getattr(levels[ordinal], "address", None) is not None
    return False


def seed_scan_models(
    state: object, panes: PaneRenderer
) -> tuple[dict[str, ScanFrame],
           dict[tuple[str, str, int, int],
                tuple[tuple[int, int, int, int], str | None]]]:
    """Pane-A seed: per-capture display models plus durable parked chips.

    Returns ``(models, chips)``.  ``models`` maps capture sha to the
    ``LiveView._SCAN_FIELDS``-shaped model of that capture's seed lane —
    installed when ``capture.open`` re-opens the capture, and replaced
    wholesale by the next ordinary lane's live survey exactly like any
    prior model.  ``chips`` carries every durable ``ParkedWindowRecord``
    under its live identity key ``(capture, lane, region_index,
    window_id)`` (``origin_yx_px`` is region-crop-relative; the crop
    origin is the region record's support bbox origin; the box spans
    ``shape_yx_cells * cell_pitch_px`` — the exact live
    ``address.window_planned`` convention).

    Both the models' transforms and the chip boxes are lifted into
    CAPTURE-NATIVE pixels, matching what live ingest stores, so seeded and
    live geometry share one frame.  The multiplier comes from the durable
    ``LaneSpec`` in ``capture.plan`` — the seed runs at ``session.open``,
    before this invocation's first ``level.open`` publishes it on the
    wire, so the event stream cannot supply it here.
    """
    regions_by_lane: dict[tuple[str, str], list[SurveyRegionRecord]] = {}
    for record in getattr(state, "regions", ()) or ():
        if isinstance(record, SurveyRegionRecord):
            regions_by_lane.setdefault(
                (record.capture_id, record.lane_id), []).append(record)
    if not regions_by_lane:
        return {}, {}
    posed: dict[tuple[str, str], set[str]] = {}
    for pose in getattr(state, "poses", ()) or ():
        if isinstance(pose, PoseRecord):
            posed.setdefault(
                (pose.capture_id, pose.lane_id), set()).add(pose.region_id)
    parked_by_lane: dict[tuple[str, str], list[ParkedWindowRecord]] = {}
    for row in getattr(state, "parked", ()) or ():
        if isinstance(row, ParkedWindowRecord):
            parked_by_lane.setdefault(
                (row.capture_id, row.lane_id), []).append(row)

    frames: dict[tuple[str, str],
                 tuple[tuple[float, float, float], list]] = {}

    def lane_frame(key: tuple[str, str]):
        frame = frames.get(key)
        if frame is None:
            ordered = sorted(
                regions_by_lane[key],
                key=lambda row: (_region_index(row.region_id) is None,
                                 _region_index(row.region_id) or 0))
            transform, _corners, views = panes.scan_views(
                tuple(region_from_record(row) for row in ordered))
            frame = (transform, list(zip(ordered, views)))
            frames[key] = frame
        return frame

    models: dict[str, ScanFrame] = {}
    chips: dict[tuple[str, str, int, int],
                tuple[tuple[int, int, int, int], str | None]] = {}
    for capture in getattr(state, "captures", ()) or ():
        sha = str(getattr(capture, "source_sha256", "") or "")
        lanes_here = {lane for cap, lane in regions_by_lane if cap == sha}
        lane_id = _seed_lane(capture, lanes_here)
        plan = tuple(getattr(capture, "plan", ()) or ())
        ordinals = {lane.lane_id: ordinal
                    for ordinal, lane in enumerate(plan)}
        natives = {}
        for lane in plan:
            num = getattr(lane, "native_per_view_num", None)
            den = getattr(lane, "native_per_view_den", None)
            natives[getattr(lane, "lane_id", None)] = (
                num / den if type(num) is int and type(den) is int and den
                else 1.0)
        # Durable parked chips, lifted to native px like live ingest.
        for (cap, lane), rows in parked_by_lane.items():
            if cap != sha or (cap, lane) not in regions_by_lane:
                continue
            _transform, region_views = lane_frame((cap, lane))
            native = natives.get(lane, 1.0)
            origins = {row.region_id: row.origin_yx
                       for row, _view in region_views}
            ordinal = ordinals.get(lane)
            digit = None if ordinal is None else str(ordinal + 1)
            for row in rows:
                origin = origins.get(row.region_id)
                if origin is None:
                    continue
                y = origin[0] + row.origin_yx_px[0]
                x = origin[1] + row.origin_yx_px[1]
                h = max(1, round(row.shape_yx_cells[0] * row.cell_pitch_px))
                w = max(1, round(row.shape_yx_cells[1] * row.cell_pitch_px))
                chips[(cap, lane, int(row.region_index),
                       int(row.window_id))] = (
                    (round(y * native), round(x * native),
                     max(1, round(h * native)), max(1, round(w * native))),
                    digit)
        if lane_id is None:
            continue
        transform, region_views = lane_frame((sha, lane_id))
        native = natives.get(lane_id, 1.0)
        scale, y0, x0 = transform
        transform = (scale / native, y0 * native, x0 * native)
        placed = posed.get((sha, lane_id), set())
        parked_regions = {row.region_id
                          for row in parked_by_lane.get((sha, lane_id), ())}
        committed = _address_committed(capture, lane_id)
        views = []
        for record, view in region_views:
            if record.region_id in placed:
                view.state = "accepted"
            elif record.region_id in parked_regions:
                view.state = "parked"
            elif committed:
                view.state = "unresolved"
            views.append(view)
        models[sha] = ScanFrame(
            regions=views, transform=transform, lane=lane_id,
            active_window=None, underlay=None, lane_regions=len(views),
            survey_seen=True, queue_total=None, deferred=0, planned={},
            mopup_base=None, refine_base=None, uplift_arm=None)
    return models, chips


__all__ = ["seed_scan_models", "seed_words"]
