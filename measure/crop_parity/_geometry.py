"""Case geometry: clustering, the cell->pixel affine, bboxes, controls.

PURE over plain data (no I/O, no receiver imports) — the half the
self-check pins. Ported from ``holo2/measure/crop_cases.py``'s geometry
section with two changes: the affine is fitted PER CAPTURE (sheet I is
three captures of one page, each with its own paper pose), and the
target unit carries a stream id.

THE CELL->PIXEL MAP is one global affine per capture, least-squares
fitted from the holo1 state's ``accepted`` committed poses.
``native_affine`` is the canonical page-cell -> native-pixel-centre map;
five sample points per pose window (four corners + centre). It absorbs
whatever orientation the scan implies (a 180-degree scan comes out as
negative scale), and the crop is the AABB of the transformed cell
rectangle. Local deviation from the global fit is paper/scan warp —
measured 40.5 px worst case on e029, ~2.5 cells — which is why the
pixel bbox is padded by ``PX_PAD_CELLS`` = 32 cells' worth of pixels
before clipping to the capture.

CLUSTERING AND SPLITTING are SPEED knobs, never evidence caps (the "no
ceilings" rule): every target lands in exactly ONE case, asserted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

#: One tile is 64x64 cells in printed format v1.
TILE_CELLS = 64

#: Fixed, not knobs (the holo2 harness's mechanics 4 and 5).
PX_PAD_CELLS = 32
CONTROL_RIM_CELLS = 32

Address = tuple[int, int, int, str]
Tile = tuple[int, int]


# --------------------------------------------------------------------
# clustering + splitting
# --------------------------------------------------------------------


@dataclass(frozen=True)
class Cluster:
    """One case's tile-space content (half-open tile ranges)."""

    members: tuple[Tile, ...]
    ty0: int
    ty1: int
    tx0: int
    tx1: int

    @staticmethod
    def of(members: Iterable[Tile]) -> "Cluster":
        rows = tuple(sorted(set(members)))
        if not rows:
            raise ValueError("a cluster needs at least one target tile")
        tys = [ty for ty, _ in rows]
        txs = [tx for _, tx in rows]
        return Cluster(members=rows, ty0=min(tys), ty1=max(tys) + 1,
                       tx0=min(txs), tx1=max(txs) + 1)

    @property
    def span_cells_yx(self) -> tuple[int, int]:
        return ((self.ty1 - self.ty0) * TILE_CELLS,
                (self.tx1 - self.tx0) * TILE_CELLS)


def cluster_tiles(tiles: Iterable[Tile], merge_gap_tiles: int,
                  ) -> list[Cluster]:
    """Union-find over Chebyshev adjacency: two tiles share a cluster
    when the EMPTY-TILE GAP between them is <= ``merge_gap_tiles`` (so
    Chebyshev distance <= gap + 1; adjacent tiles have gap 0)."""
    rows = sorted(set(tiles))
    parent = {tile: tile for tile in rows}

    def find(tile: Tile) -> Tile:
        while parent[tile] != tile:
            parent[tile] = parent[parent[tile]]
            tile = parent[tile]
        return tile

    reach = merge_gap_tiles + 1
    for index, a in enumerate(rows):
        for b in rows[index + 1:]:
            if max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= reach:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb
    grouped: dict[Tile, list[Tile]] = {}
    for tile in rows:
        grouped.setdefault(find(tile), []).append(tile)
    return sorted((Cluster.of(members) for members in grouped.values()),
                  key=lambda c: (c.ty0, c.tx0, c.ty1, c.tx1))


def split_clusters(clusters: Sequence[Cluster], max_span_cells: int,
                   ) -> list[Cluster]:
    """Split every cluster whose LONG side exceeds ``max_span_cells``
    along that axis, repeatedly, re-shrinking each segment to its own
    members. Every input tile lands in exactly one output cluster —
    asserted, not hoped."""
    queue = list(clusters)
    done: list[Cluster] = []
    while queue:
        cluster = queue.pop()
        span_y, span_x = cluster.span_cells_yx
        if max(span_y, span_x) <= max_span_cells:
            done.append(cluster)
            continue
        axis = 0 if span_y >= span_x else 1
        lo = cluster.ty0 if axis == 0 else cluster.tx0
        hi = cluster.ty1 if axis == 0 else cluster.tx1
        span_tiles = hi - lo
        pieces = -(max(span_y, span_x) // -max_span_cells)
        buckets: dict[int, list[Tile]] = {}
        for tile in cluster.members:
            offset = (tile[axis] - lo) * pieces // span_tiles
            buckets.setdefault(offset, []).append(tile)
        for members in buckets.values():
            queue.append(Cluster.of(members))
    result = sorted(done, key=lambda c: (c.ty0, c.tx0, c.ty1, c.tx1))
    wanted = sorted(t for c in clusters for t in c.members)
    got = sorted(t for c in result for t in c.members)
    if wanted != got:
        raise AssertionError("split lost or duplicated target tiles")
    return result


# --------------------------------------------------------------------
# the affine
# --------------------------------------------------------------------


@dataclass(frozen=True)
class GlobalAffine:
    """One capture's cell->pixel map, X-FIRST:
    ``px_x = a*cx + b*cy + c`` (row 0), ``px_y = d*cx + e*cy + f``
    (row 1); px_x is the capture COLUMN (numpy axis 1), px_y the ROW."""

    rows: tuple[tuple[float, float, float], tuple[float, float, float]]
    n_poses: int
    residual_median_px: float
    residual_p99_px: float
    residual_max_px: float

    def apply(self, cx: float, cy: float) -> tuple[float, float]:
        (a, b, c), (d, e, f) = self.rows
        return (a * cx + b * cy + c, d * cx + e * cy + f)

    @property
    def px_per_cell(self) -> float:
        (a, b, _), (d, e, _) = self.rows
        return float(np.sqrt(abs(a * e - b * d)))


def fit_global_affine(poses: Sequence[dict]) -> GlobalAffine:
    """Least-squares cell->pixel affine from accepted committed poses."""
    pts_cell: list[tuple[float, float]] = []
    pts_px: list[np.ndarray] = []
    for pose in poses:
        affine = np.asarray(pose["native_affine"], np.float64).reshape(2, 3)
        height, width = pose["window_shape_yx_cells"]
        if int(pose.get("rot90", 0)) % 2:
            height, width = width, height
        y0, x0 = pose["cell_origin_yx"]
        for cy, cx in ((y0, x0), (y0, x0 + width), (y0 + height, x0),
                       (y0 + height, x0 + width),
                       (y0 + height / 2, x0 + width / 2)):
            pts_cell.append((cy, cx))
            pts_px.append(affine[:, :2] @ (cy, cx) + affine[:, 2])
    if len(pts_cell) < 9:
        raise ValueError(f"too few accepted poses ({len(poses)}) to fit "
                         "a global affine")
    cell = np.asarray(pts_cell, np.float64)
    px_yx = np.asarray(pts_px, np.float64)
    design = np.column_stack([cell, np.ones(len(cell))])
    coef, *_ = np.linalg.lstsq(design, px_yx, rcond=None)      # (3, 2) y,x
    residual = np.abs(px_yx - design @ coef)
    (ayy, axy), (ayx, axx), (cy_c, cx_c) = coef
    return GlobalAffine(
        rows=((float(axx), float(axy), float(cx_c)),
              (float(ayx), float(ayy), float(cy_c))),
        n_poses=len(poses),
        residual_median_px=float(np.median(residual)),
        residual_p99_px=float(np.percentile(residual, 99)),
        residual_max_px=float(residual.max()))


# --------------------------------------------------------------------
# bboxes and controls
# --------------------------------------------------------------------


def cell_bbox_for(cluster: Cluster, halo_cells: int,
                  page_cells_yx: tuple[int, int],
                  ) -> tuple[int, int, int, int]:
    """The case's cell rectangle: cluster rect + halo, clipped to the
    page. X-FIRST half-open ``(cx0, cy0, cx1, cy1)``."""
    cells_y, cells_x = page_cells_yx
    cy0 = max(0, cluster.ty0 * TILE_CELLS - halo_cells)
    cy1 = min(cells_y, cluster.ty1 * TILE_CELLS + halo_cells)
    cx0 = max(0, cluster.tx0 * TILE_CELLS - halo_cells)
    cx1 = min(cells_x, cluster.tx1 * TILE_CELLS + halo_cells)
    return (cx0, cy0, cx1, cy1)


def px_bbox_for(cell_bbox: tuple[int, int, int, int], affine: GlobalAffine,
                capture_shape_yx: tuple[int, int],
                ) -> tuple[int, int, int, int]:
    """AABB of the transformed cell rectangle, padded by
    ``PX_PAD_CELLS`` worth of pixels and clipped to the CAPTURE (an
    off-page halo keeps real margin context). X-first half-open."""
    cx0, cy0, cx1, cy1 = cell_bbox
    corners = [affine.apply(cx, cy)
               for cx in (cx0, cx1) for cy in (cy0, cy1)]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    pad = PX_PAD_CELLS * affine.px_per_cell
    rows_n, cols_n = capture_shape_yx
    px0 = max(0, int(np.floor(min(xs) - pad)))
    px1 = min(cols_n, int(np.ceil(max(xs) + pad)))
    py0 = max(0, int(np.floor(min(ys) - pad)))
    py1 = min(rows_n, int(np.ceil(max(ys) + pad)))
    if px1 <= px0 or py1 <= py0:
        raise ValueError(f"empty pixel bbox from cell bbox {cell_bbox}")
    return (px0, py0, px1, py1)


def controls_for(cell_bbox: tuple[int, int, int, int],
                 both_certified: frozenset[Address],
                 target_tiles: frozenset[Tile]) -> tuple[Address, ...]:
    """Every both-certified address whose 64-cell tile extent lies FULLY
    inside the cell bbox shrunk by the 32-cell rim, excluding every TILE
    POSITION that carries a target in this volume.

    Two reasons for the tile-position exclusion rather than an
    address-level one: a control must be a tile whose reproduction is
    uninteresting, and on a colour volume the C plane of a tile whose Y
    plane is a target is not that tile.
    """
    cx0, cy0, cx1, cy1 = cell_bbox
    x_lo, x_hi = cx0 + CONTROL_RIM_CELLS, cx1 - CONTROL_RIM_CELLS
    y_lo, y_hi = cy0 + CONTROL_RIM_CELLS, cy1 - CONTROL_RIM_CELLS
    out: list[Address] = []
    for address in sorted(both_certified):
        _page, ty, tx, _stream = address
        if (ty, tx) in target_tiles:
            continue
        if (y_lo <= ty * TILE_CELLS and (ty + 1) * TILE_CELLS <= y_hi
                and x_lo <= tx * TILE_CELLS
                and (tx + 1) * TILE_CELLS <= x_hi):
            out.append(address)
    return tuple(out)
