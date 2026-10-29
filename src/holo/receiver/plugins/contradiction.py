from __future__ import annotations

import sys

from .. import data
from ..data import WindowId
from ..lib import geometry
from . import place

#: Two placements disagree when their page-cell mappings differ by a
#: WHOLE cell at the shared paper point.  Measured 2026-09-04, local-patch
#: K sim: two honest fits of one paper agree to 0.41 cells worst case over
#: 100+ overlapping pairs — a half-cell rounding rule would be too tight.
DISAGREEMENT_CELLS: float = 1.0

#: The producer, per the ruling: a word that decoded legally and was
#: admitted by the rival bar.  A refused word never becomes a placement,
#: so v1's "accepted placements only" holds by construction here.
PRODUCING_ROUTES: frozenset[str] = frozenset({place.ROUTE_WORD})

Extent = tuple[int, int, int, int]


def neighbour_windows(store: object, wid: WindowId) -> tuple[WindowId, ...]:
    """Every window of this capture whose extent can overlap `wid`'s.

    The ring relation `place_sched._place_reads` already subscribes to —
    the eight lattice neighbours at every level of the capture, plus this
    extent at the other levels.  It keeps the check O(neighbours): the
    placement table is never walked, and subdivision children (off the
    lattice) are out of scope.
    """
    capture_id, level_index, region_index, extent = wid
    frame = store.frame((capture_id, level_index, region_index))
    capture = store.capture(capture_id)
    if frame is None or capture is None:
        return ()
    ring = place.ring_neighbour_extents(frame.shape_cells, extent)
    out: list[WindowId] = []
    for level in capture.levels:
        for other in ring:
            out.append((capture_id, level.index, region_index, other))
        if level.index != level_index:
            out.append((capture_id, level.index, region_index, extent))
    return tuple(out)


def overlap_cells(one: Extent, other: Extent) -> Extent | None:
    cy0, cx0 = max(one[0], other[0]), max(one[1], other[1])
    cy1, cx1 = min(one[2], other[2]), min(one[3], other[3])
    if cy1 <= cy0 or cx1 <= cx0:
        return None
    return (cy0, cx0, cy1, cx1)


def probe_native_yx(frame: place.RegionFrame,
                    overlap: Extent) -> tuple[float, float]:
    pitch = frame.pitch_native_px
    return (frame.origin_native_yx[0] + pitch * 0.5 * (overlap[0]
                                                       + overlap[2]),
            frame.origin_native_yx[1] + pitch * 0.5 * (overlap[1]
                                                       + overlap[3]))


def page_cell_at(inverse: tuple[float, ...], native_y: float,
                 native_x: float) -> tuple[float, float]:
    a, b, c, d, e, f = inverse
    return (a * native_y + b * native_x + c,
            d * native_y + e * native_x + f)


def _tile_of(cell_yx: tuple[float, float]) -> tuple[int, int]:
    return (int(cell_yx[0] // geometry.TILE_CELLS),
            int(cell_yx[1] // geometry.TILE_CELLS))


def find(store: object,
         placement: data.Placement) -> tuple[data.Contradiction, ...]:
    """The standing placements this word-routed one disagrees with.

    Reads nothing but poses and extents, mints nothing, and is called
    once per adopted placement from the place fold.  A diagnostic: the
    caller emits and warns, and no consumer may gate on the answer.
    """
    if placement.route not in PRODUCING_ROUTES:
        return ()
    wid: WindowId = placement.window_id
    frame = store.frame(wid[:3])
    if frame is None:
        return ()
    inverse = geometry.invert_affine(tuple(placement.native_affine))
    rows: list[data.Contradiction] = []
    for other_wid in neighbour_windows(store, wid):
        standing = store.placement(other_wid)
        if standing is None:
            continue
        overlap = overlap_cells(wid[3], other_wid[3])
        if overlap is None:
            continue
        native_y, native_x = probe_native_yx(frame, overlap)
        mine = page_cell_at(inverse, native_y, native_x)
        theirs = page_cell_at(
            geometry.invert_affine(tuple(standing.native_affine)),
            native_y, native_x)
        delta = (mine[0] - theirs[0], mine[1] - theirs[1])
        if (placement.page == standing.page
                and max(abs(delta[0]), abs(delta[1])) < DISAGREEMENT_CELLS):
            continue
        rows.append(data.Contradiction(
            capture=wid[0],
            window_id=wid,
            standing_window_id=other_wid,
            route=str(placement.route),
            standing_route=str(standing.route),
            page=int(placement.page),
            standing_page=int(standing.page),
            page_origin_yx=(int(placement.page_origin_yx[0]),
                            int(placement.page_origin_yx[1])),
            standing_page_origin_yx=(int(standing.page_origin_yx[0]),
                                     int(standing.page_origin_yx[1])),
            rot_k=int(placement.rot_k),
            standing_rot_k=int(standing.rot_k),
            tile_yx=_tile_of(mine),
            standing_tile_yx=_tile_of(theirs),
            overlap_cells=overlap,
            delta_cells_yx=(float(delta[0]), float(delta[1]))))
    return tuple(rows)


def warning_line(row: data.Contradiction) -> str:
    return (
        f"CONTRADICTION: capture {row.capture[:12]}… window "
        f"{row.window_id[1]}.{row.window_id[2]} {row.window_id[3]} decoded "
        f"page {row.page} tile {row.tile_yx[0]},{row.tile_yx[1]} rot "
        f"{row.rot_k} ({row.route}) but standing window "
        f"{row.standing_window_id[1]}.{row.standing_window_id[2]} "
        f"{row.standing_window_id[3]} asserts page {row.standing_page} tile "
        f"{row.standing_tile_yx[0]},{row.standing_tile_yx[1]} rot "
        f"{row.standing_rot_k} ({row.standing_route}) over the same cells "
        f"{row.overlap_cells}, apart by "
        f"{row.delta_cells_yx[0]:+.2f},{row.delta_cells_yx[1]:+.2f} cells "
        f"— quarantine is not built; the payload is unaffected")


def check(store: object, placement: data.Placement,
          events: list) -> int:
    """Detect, record, warn — and never fail the run for it.

    The guard is the diag law (`DIAG-DESIGN` §0): a defect in a
    diagnostic may not change a payload, a status or an exit code, so
    the failure is named on stderr and the fold carries on.
    """
    try:
        found = find(store, placement)
    except Exception as exc:
        print(f"contradiction: check failed ({exc})", file=sys.stderr,
              flush=True)
        return 0
    for row in found:
        events.append(row)
        print(warning_line(row), file=sys.stderr, flush=True)
    return len(found)
