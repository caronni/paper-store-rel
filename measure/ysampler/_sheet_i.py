"""Sheet I's recorded evidence, opened read-only and never re-derived.

Sheet I is `L:c2-cmy8-r0700-p120-x1@3392x2368`, the 2026-08-18 AltaLink
print whose volume closed VERIFIED at 1,798,761 B (e033 sheet I).  It is
the one printed page in the record that carries BOTH halves of a
registration ground truth:

* `regmap-gt/plane-offsets.json` -- per-tile per-plane displacement,
  measured directly against the emitted dot field by the e033
  GT-correlation tool (`measure_plane_offsets.py`), on a page-global
  affine fitted from nine wide-search anchors.  `dY_rel_x` is the Y
  plane's x displacement relative to the C/M mean: THE recorded
  registration sinusoid (0.83 dot peak, ~100 mm period).
* `plane-fields/swim-pilot/swim-pilot-final.json` -- the DECODE-OPTIMAL
  x offset per target tile, found by scoring cell error against the
  emitted truth over a +-1 dot grid.  This is the reference the record's
  "direct estimators overshoot by 1.5-2.3x" is measured against
  (docs/INDEPENDENT-PLANES.md 2.3: neighbour-interpolated 0.93,
  supervised regmap-gt 1.47, own-furniture dust 2.33).

Everything here is a READ.  Nothing in this module writes, decodes, or
loads a receiver state; the scan is a memmap and only tile-sized windows
are ever materialized.

UNITS.  The GT tool works in SCAN PIXELS at `PX_PER_DOT` = 4 (a 2400 dpi
capture of a 600 dpi print).  This module converts to printed DOTS at the
boundary, because dots are the unit every field, anchor and swim offset
in the receiver is expressed in.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

#: Read-only recorded evidence.  Nothing here is written.
SCRATCH_IN = Path("scratch")
SCAN = SCRATCH_IN / (
    "xerox-canon-18.8-I-c2-cmy8-r700-q90-p120-4mm-2400dpi.tiff")
REGMAP_GT = SCRATCH_IN / "xerox-v1-20260818/regmap-gt/plane-offsets.json"
REGMAP_GT_COLUMNS = SCRATCH_IN / "xerox-v1-20260818/regmap-gt/per-column.json"
SWIM = SCRATCH_IN / "plane-fields/swim-pilot/swim-pilot-final.json"

FORMAT_REF = "L:c2-cmy8-r0700-p120-x1@3392x2368"
CELL_DOTS = 2
TILE_DOTS = 128
TILES_YX = (53, 37)
PX_PER_DOT = 4

# The page-global scan <- GT-dot affine the e033 tool fitted on nine
# wide-search anchors, copied from
# scratch/xerox-v1-20260818/regmap-gt/measure_plane_offsets.py.  Using
# the GT's own affine is what makes this measurement comparable to the
# GT: both sit on the same nominal page frame, and the per-patch common
# lock below removes what the global affine leaves.
#   y_scan = AY[0]*yd + AY[1]*xd + AY[2]
#   x_scan = AX[0]*yd + AX[1]*xd + AX[2]
AY = (4.005148, 0.003337, 273.43)
AX = (-0.001985, 4.002649, 451.74)

PLANE_NAMES = ("C", "M", "Y")


class MissingEvidence(RuntimeError):
    """A recorded input is absent; refuse rather than measure nothing."""


def require(paths: tuple[Path, ...]) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise MissingEvidence(
            "measure/ysampler: recorded input(s) absent: "
            + ", ".join(missing))


@dataclass(frozen=True)
class GroundTruthTile:
    """One GT patch: where the tile is, and where each plane landed.

    ``common_*`` is the plane-COMMON lock the GT tool applied before
    measuring any plane, in scan pixels.  ``d*_dots`` are per-plane
    displacements in printed dots on that same nominal frame, so
    ``dY_rel_dots = dY - (dC + dM) / 2`` is exactly the GT file's
    ``dY_rel_x / PX_PER_DOT``.
    """

    tile_y: int
    tile_x: int
    common_dy_px: float
    common_dx_px: float
    common_corr: float
    d_x_dots: tuple[float, float, float]
    d_y_dots: tuple[float, float, float]
    corr: tuple[float, float, float]

    @property
    def rel_x_dots(self) -> float:
        return self.d_x_dots[2] - 0.5 * (self.d_x_dots[0] + self.d_x_dots[1])

    @property
    def cm_x_dots(self) -> float:
        return self.d_x_dots[0] - self.d_x_dots[1]


def ground_truth_tiles() -> tuple[GroundTruthTile, ...]:
    """Every GT patch that measured cleanly, in canonical tile order."""
    require((REGMAP_GT,))
    record = json.loads(REGMAP_GT.read_text())
    if int(record["px_per_dot"]) != PX_PER_DOT:
        raise MissingEvidence(
            f"regmap-gt was measured at {record['px_per_dot']} px/dot, "
            f"not {PX_PER_DOT}: the dot conversion here would be wrong")
    out: list[GroundTruthTile] = []
    for patch in record["patches"]:
        if "error" in patch:
            continue
        out.append(GroundTruthTile(
            tile_y=int(patch["tile_y"]), tile_x=int(patch["tile_x"]),
            common_dy_px=float(patch["common_dy"]),
            common_dx_px=float(patch["common_dx"]),
            common_corr=float(patch["common_corr"]),
            d_x_dots=tuple(float(patch[f"d{name}_x"]) / PX_PER_DOT
                           for name in PLANE_NAMES),
            d_y_dots=tuple(float(patch[f"d{name}_y"]) / PX_PER_DOT
                           for name in PLANE_NAMES),
            corr=tuple(float(patch[f"{name}_corr"])
                       for name in PLANE_NAMES)))
    return tuple(sorted(out, key=lambda t: (t.tile_y, t.tile_x)))


def ground_truth_columns() -> dict[int, dict]:
    """The GT rolled up per tile column, in DOTS.

    The per-tile GT carries ~0.1 dot of measurement noise (the file's own
    ``dY_rel_x_sd`` is 0.36-0.42 px over 13 rows); the column mean is the
    precise form of the recorded sinusoid and is what a shape comparison
    should be scored against.
    """
    require((REGMAP_GT_COLUMNS,))
    rows = json.loads(REGMAP_GT_COLUMNS.read_text())
    return {
        int(row["tx"]): {
            "n": int(row["n"]),
            "residue": int(row["residue"]),
            "rel_x_dots": float(row["dY_rel_x"]) / PX_PER_DOT,
            "rel_x_sd_dots": float(row["dY_rel_x_sd"]) / PX_PER_DOT,
            "cm_x_dots": float(row["dCM_x"]) / PX_PER_DOT,
        }
        for row in rows}


def swim_targets() -> tuple[dict, ...]:
    """The recorded decode-optimal offsets, one row per (tile, stream).

    ``ber_argmin_dx`` is the offset that minimizes cell error against the
    emitted truth -- the "decode-optimal" the record's 1.5-2.3x overshoot
    is measured against.  Twelve targets only: this is a precise but very
    small reference, and every number derived from it says so.
    """
    require((SWIM,))
    record = json.loads(SWIM.read_text())
    rows = record["summary"]["offset_agreement_dots"]
    reachable = {
        (int(row["tile_y"]), int(row["tile_x"])): float(row["ber_argmin_dx"])
        for row in record["summary"]["ber_cliff"]["reachable_by_translation"]}
    out = []
    for row in rows:
        key = (int(row["tile_y"]), int(row["tile_x"]))
        out.append({
            "tile_y": key[0], "tile_x": key[1],
            "stream": row["stream"], "band": row["band"],
            "role": row["role"],
            "ber_argmin_dx": reachable.get(key),
            "surrogate_argmax_dx": row.get("surrogate_argmax_dx"),
            "own_dx": row.get("own_dx"),
            "neighbour_dx": row.get("neighbour_dx"),
            "regmap_rel_dx": row.get("regmap_dY_rel_x_centred"),
        })
    return tuple(out)


def nominal_scan_yx(dot_y: float, dot_x: float) -> tuple[float, float]:
    """The GT tool's own nominal page frame, dots -> scan pixels."""
    return (AY[0] * dot_y + AY[1] * dot_x + AY[2],
            AX[0] * dot_y + AX[1] * dot_x + AX[2])


def tile_affine(tile: GroundTruthTile) -> tuple[
        float, float, float, float, float, float]:
    """A holo3 ``Affine`` for one tile: LOCAL CELLS -> scan pixels.

    Built from the GT's own page affine, scaled from dots to cells, and
    translated by the patch's recorded plane-COMMON lock.  Measuring a
    plane's anchors on this frame makes the anchor's offset the same
    quantity the GT file calls ``d<plane>`` minus the common part -- so
    the plane-relative form ``Y - (C + M) / 2`` compares directly to
    ``dY_rel_x``, with the global affine's own error cancelling out of
    both sides.
    """
    origin_y_dots = tile.tile_y * TILE_DOTS
    origin_x_dots = tile.tile_x * TILE_DOTS
    base_y, base_x = nominal_scan_yx(origin_y_dots, origin_x_dots)
    # HALF-CELL.  The GT tool's affine maps a DOT COORDINATE to the
    # CORNER of that dot (its model renders each dot as a PX_PER_DOT
    # block starting there), so cell (ly, lx) starts at dot
    # (CELL_DOTS*ly, CELL_DOTS*lx) and its CENTRE is half a cell further
    # on.  Every sampler downstream -- holo3's rectified_ncc, its
    # pose_points, the field's probes -- takes an integral cell
    # coordinate to mean the cell's centre, so the half-cell belongs in
    # the affine.  Without it every plane reads a common +1 dot at c2,
    # which cancels out of the plane-relative comparison and quietly
    # eats the search radius.
    half_y, half_x = nominal_scan_yx(CELL_DOTS / 2.0, CELL_DOTS / 2.0)
    offset_y = half_y - AY[2]
    offset_x = half_x - AX[2]
    return (CELL_DOTS * AY[0], CELL_DOTS * AY[1],
            base_y + offset_y + tile.common_dy_px,
            CELL_DOTS * AX[0], CELL_DOTS * AX[1],
            base_x + offset_x + tile.common_dx_px)


GT_DOTS = SCRATCH_IN / (
    "xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm/page000_gt.npy")


def open_truth_dots() -> np.ndarray:
    """The emitted dot field, packed, as a memmap.

    ORACLE.  This is the page as it was SENT to the printer, and nothing
    a receiver can have.  It exists here only as a stand-in for the
    template a CERTIFIED tile supplies -- the question being whether an
    anchor's template has to come from truth at all.  It never touches a
    number that could be presented as blind.
    """
    require((GT_DOTS,))
    return np.load(GT_DOTS, mmap_mode="r")


def truth_cell_bits(packed: np.ndarray, tile_y: int,
                    tile_x: int) -> np.ndarray:
    """One tile's emitted CELL bits, (cells, cells, 3), from the dots.

    A cell is a solid ``CELL_DOTS``-square block of dots, so the dot at
    the block's origin IS the cell's bit; the assertion that it is solid
    is checked once by the caller (``_assert_cells_are_solid``).
    """
    y0 = tile_y * TILE_DOTS
    x0 = tile_x * TILE_DOTS
    byte0, byte1 = x0 // 8, (x0 + TILE_DOTS + 7) // 8
    raw = np.ascontiguousarray(packed[:, y0:y0 + TILE_DOTS, byte0:byte1])
    bits = np.unpackbits(raw, axis=2, bitorder="big")
    offset = x0 - byte0 * 8
    dots = bits[:, :, offset:offset + TILE_DOTS]
    return np.transpose(dots[:, ::CELL_DOTS, ::CELL_DOTS], (1, 2, 0))


def open_scan() -> np.ndarray:
    """The capture as a read-only memmap; only windows are materialized."""
    import tifffile

    require((SCAN,))
    return tifffile.imread(str(SCAN), out="memmap")


def scan_planes(scan: np.ndarray) -> tuple[np.ndarray, ...]:
    """The three channel views holo3's anchor kernel expects."""
    return tuple(scan[..., channel] for channel in range(3))
