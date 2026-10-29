"""Cases: which page rectangle, and the three crops that carry it.

A case is a TILE RECTANGLE on sheet I, cut from ALL THREE 2400 dpi
captures at the same page addresses. That is the whole point: the
question is about multi-capture material, so a case that is not covered
by more than one lane cannot answer it.

WHY A CROP AND NOT ARCHIVED POSES. ``measure.yask`` reads windows
straight off the full captures at the archived harvest's poses, which is
cheaper. It cannot be done here: ``tiles.local`` needs a live holo3
STORE — covering lanes, committed placements, colour rows, the standing
certificate set — and the only honest way to get one is to let holo3
place and read the material itself.

THE CROP MUST CARRY REAL PAGE MARGIN. ``measure/yask/README.md`` records
the measured negative: an ordinary ``holo3 decode`` of a crop cut
ENTIRELY INSIDE the printed field surveys into fragments and places
nothing, because ``survey._adaptive_threshold`` is an Otsu split whose
two modes are paper and print. Every case here is therefore anchored on
a PAGE CORNER, so the crop contains both the top/bottom and the left
paper margin, and the fallback the yask record names ("cut crops that
include real page margin") is the route taken.

THE CELL->PIXEL MAP is one global affine per capture, least-squares
fitted from the archived harvest's own accepted ``PoseCommitted`` poses
(``crop_parity._geometry.fit_global_affine``, unchanged). It is used
ONLY to decide where to cut: the decode re-surveys, re-places and
re-addresses the crop from scratch, and a printed tile carries its own
absolute address word, so the crop's addresses are the page's addresses.
"""
from __future__ import annotations

import collections
import json
import lzma
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from measure import _evidence
from measure.crop_parity import _geometry

from . import _paths

TILE = 64

#: Sheet I: three 2400 dpi Canon captures of one AltaLink print
#: (e033, 2026-08-18), the pooled-fountain CMY8 volume that CLOSED.
FORMAT_REF = "L:c2-cmy8-r0700-p120-x1@3392x2368"
TILES_YX = (53, 37)
PAGE_CELLS = (TILES_YX[0] * TILE, TILES_YX[1] * TILE)

GEN_DIR = _paths.SHEET_I / "emission"
PAYLOAD = GEN_DIR / "payload-counting.bin"
PAYLOAD_SHA256 = ("2445b95db5b49bf3e05eb2538e9e247d289a48a4fed2e46e"
                  "b7ba78ab61e4350b")
PAYLOAD_BYTES = 1_798_761

EVENTS_XZ = _paths.OVERNIGHT / "sheet-I-events.jsonl.xz"


def evidence(path: Path) -> Path:
    """A declared input path joined onto the evidence root."""
    return _paths.evidence_root() / path


#: capture key -> (path, dpi, capture id), every path relative to the
#: evidence root. The capture id IS the file's sha256
#: (``intake.ingest_capture`` mints it that way), so this table is
#: self-checking: a capture whose id does not appear in the harvest's
#: ``CaptureOpen`` events is refused BY NAME rather than mismatched.
CAPTURES: dict[str, tuple[Path, float, str]] = {
    "a": (_paths.SHEET_I / "captures/I-canon-2400rgb.tiff", 2400.0,
          "269d81217ec48a5e57ae5736baf091f0afe3f66dd15539c0f39dfc6cffde"
          "a30c"),
    "b": (_paths.SHEET_I / "captures/I-canon-2400rgb-displaced.tiff", 2400.0,
          "a410631d6ff6a8519767a4cdb7c55bd6e5b90b549a7450d017e783064991"
          "e8dd"),
    "c": (_paths.SHEET_I / "captures/I-canon-2400rgb-displaced2.tiff", 2400.0,
          "36b90a50f272bb02982286b18657a8630eaa378eb7ac553e3a54461e548d"
          "55af"),
}


@dataclass(frozen=True)
class Case:
    """One page rectangle, cut from every capture."""

    case_id: str
    #: Half-open tile rectangle under test: (ty0, ty1, tx0, tx1).
    target_tiles: tuple[int, int, int, int]
    #: Cells of context around the target rectangle, clipped to the page.
    halo_cells: int
    note: str

    @property
    def target_positions(self) -> tuple[tuple[int, int], ...]:
        ty0, ty1, tx0, tx1 = self.target_tiles
        return tuple((ty, tx) for ty in range(ty0, ty1)
                     for tx in range(tx0, tx1))


#: The rectangles are DECLARED, not inferred, so a case is reproducible
#: from this file alone. Both are page CORNERS (the margin rule above)
#: and both straddle sheet I's yellow residue bands at tx 7-11: the
#: production harvest left 396 Y, 39 C and 3 M stream-residues on this
#: sheet, and those bands carry most of them.
CASES: tuple[Case, ...] = (
    Case(case_id="I-tl", target_tiles=(0, 9, 0, 13), halo_cells=192,
         note="top-left corner: top AND left paper margin in the crop; "
              "117 tile positions spanning the tx 7-11 yellow band, "
              "46 of them carrying a production residue"),
    Case(case_id="I-bl", target_tiles=(44, 53, 0, 13), halo_cells=192,
         note="bottom-left corner, the same bands at the other end of "
              "the process direction — the second, independent case"),
    # A compact corner. Same construction, ~1/9 the pixels: the two
    # cases above cost hours of decode on a loaded machine before the
    # A/B can start, and a smaller store answers the same question
    # sooner. The halo is 128 cells rather than 192, so targets sit two
    # tiles deep instead of three — shallower than crop_parity's rim
    # gradient would like, and stated rather than hidden.
    Case(case_id="I-nw", target_tiles=(0, 4, 0, 8), halo_cells=128,
         note="the compact top-left corner: 32 tile positions reaching "
              "the near edge of the tx 7-11 yellow band"),
)

CASES_BY_ID = {case.case_id: case for case in CASES}


# --------------------------------------------------------------------
# the archived harvest: poses, capture facts, the production baseline
# --------------------------------------------------------------------


def read_harvest() -> tuple[dict, dict, dict]:
    """(poses by (capture, level), capture facts, certified addresses).

    One pass over the archived event log. ``TileOutcome`` rows with
    ``result == "certified"`` give the PRODUCTION baseline this
    measurement's residue is defined against.
    """
    poses: dict[tuple[str, int], list[dict]] = collections.defaultdict(list)
    captures: dict[str, dict] = {}
    certified: set[tuple[int, int, int, str]] = set()
    _paths.refuse_if_withdrawn(evidence(EVENTS_XZ))
    with lzma.open(evidence(EVENTS_XZ), "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            event = json.loads(line)
            kind = event.get("type")
            if kind == "CaptureOpen":
                captures[str(event["capture"])] = {
                    "dpi": float(event["dpi"]),
                    "shape_yx": tuple(int(v) for v in event["shape_yx"]),
                    "channels": int(event["channels"]),
                    "ordinal": int(event["ordinal"]),
                    "levels_ppc": list(event["levels_ppc"])}
            elif kind == "PoseCommitted" and event.get("accepted"):
                y0, x0, y1, x1 = event["extent_cells"]
                poses[(str(event["capture"]),
                       int(event["level_index"]))].append({
                           "native_affine": event["native_affine"],
                           "window_shape_yx_cells": (y1 - y0, x1 - x0),
                           "rot90": int(event.get("rot_k", 0)),
                           "cell_origin_yx": tuple(event["page_origin_yx"])})
            elif kind == "TileOutcome" and event.get("result") == "certified":
                certified.add((int(event["page"]), int(event["ty"]),
                               int(event["tx"]), str(event["stream_id"])))
    return dict(poses), captures, {"certified": frozenset(certified)}


def native_affine_for(capture_id: str, poses: dict) -> _geometry.GlobalAffine:
    """The finest level's global cell->pixel affine for one capture.

    ``native_affine`` is a NATIVE-pixel map at every level, so any
    level's poses fit the same map; the finest level is chosen because
    its poses are the tightest.
    """
    levels = sorted(level for (cid, level) in poses if cid == capture_id)
    if not levels:
        raise SystemExit(f"local_ab: no accepted pose carries capture "
                         f"{capture_id[:12]}… in {EVENTS_XZ.name}")
    return _geometry.fit_global_affine(poses[(capture_id, levels[-1])])


# --------------------------------------------------------------------
# the crops
# --------------------------------------------------------------------


def cell_bbox(case: Case) -> tuple[int, int, int, int]:
    """X-first half-open ``(cx0, cy0, cx1, cy1)``, clipped to the page."""
    cells_y, cells_x = PAGE_CELLS
    ty0, ty1, tx0, tx1 = case.target_tiles
    return (max(0, tx0 * TILE - case.halo_cells),
            max(0, ty0 * TILE - case.halo_cells),
            min(cells_x, tx1 * TILE + case.halo_cells),
            min(cells_y, ty1 * TILE + case.halo_cells))


def write_crop(case: Case, capture_key: str, box: tuple[int, int, int, int],
               out_dir: Path) -> dict:
    """One windowed read off a read-only memmap; one crop tiff out."""
    import tifffile

    path, dpi, _capture_id = CAPTURES[capture_key]
    path = evidence(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{case.case_id}-{capture_key}.tiff"
    px0, py0, px1, py1 = box
    if target.is_file():
        with tifffile.TiffFile(str(target)) as handle:
            shape = handle.pages[0].shape
        return {"path": str(target), "reused": True,
                "shape_yx": [int(shape[0]), int(shape[1])],
                "px_bbox": [px0, py0, px1, py1], "dpi": dpi}
    plane = tifffile.memmap(str(path), mode="r")
    try:
        window = np.ascontiguousarray(plane[py0:py1, px0:px1])
    finally:
        del plane
    tifffile.imwrite(str(target), window,
                     photometric="rgb" if window.ndim == 3 else "minisblack")
    record = {"path": str(target), "reused": False,
              "shape_yx": [int(window.shape[0]), int(window.shape[1])],
              "px_bbox": [px0, py0, px1, py1], "dpi": dpi,
              "megabytes": round(window.nbytes / 1e6, 1)}
    del window
    return record


def prepare(case: Case, crop_dir: Path) -> dict:
    """Everything a run needs about a case: geometry, crops, baseline."""
    _paths.refuse_if_absent(tuple(
        evidence(path) for path in
        [path for path, _dpi, _cid in CAPTURES.values()]
        + [PAYLOAD]))
    poses, captures, baseline = read_harvest()
    cells = cell_bbox(case)
    crops: dict[str, dict] = {}
    fits: dict[str, dict] = {}
    for key, (path, _dpi, capture_id) in sorted(CAPTURES.items()):
        if capture_id not in captures:
            raise SystemExit(
                f"local_ab: capture {capture_id[:12]}… ({path.name}) is "
                f"not one of the captures {EVENTS_XZ.name} was harvested "
                "from")
        affine = native_affine_for(capture_id, poses)
        box = _geometry.px_bbox_for(cells, affine,
                                    captures[capture_id]["shape_yx"])
        crops[key] = write_crop(case, key, box, crop_dir)
        fits[key] = {"n_poses": affine.n_poses,
                     "px_per_cell": affine.px_per_cell,
                     "residual_median_px": affine.residual_median_px,
                     "residual_p99_px": affine.residual_p99_px,
                     "residual_max_px": affine.residual_max_px,
                     "rows": [list(row) for row in affine.rows]}
    certified = baseline["certified"]
    residue = tuple(sorted(
        (0, ty, tx, stream)
        for ty, tx in case.target_positions
        for stream in ("C", "M", "Y")
        if (0, ty, tx, stream) not in certified))
    return {"case": case.case_id, "format_ref": FORMAT_REF,
            "cell_bbox": list(cells), "crops": crops, "affine_fits": fits,
            "production_certified": len(certified),
            "target_tiles": len(case.target_positions),
            "production_residue_in_target": [list(a) for a in residue]}


def main(argv: list[str] | None = None) -> int:
    """Cut one case's three crops and print its geometry record."""
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--case", required=True,
                        help=f"one of {sorted(CASES_BY_ID)}")
    _evidence.add_argument(parser)
    parser.add_argument("--out", type=Path, required=True,
                        help="directory the crops are written to")
    args = parser.parse_args(argv)
    _paths.use_evidence_root(args.evidence_root)
    _paths.evidence_root()
    if args.case not in CASES_BY_ID:
        raise SystemExit(f"local_ab: unknown case {args.case!r}; declared: "
                         f"{sorted(CASES_BY_ID)}")
    record = prepare(CASES_BY_ID[args.case], args.out)
    residue = record.pop("production_residue_in_target")
    print(json.dumps({**record, "n_production_residue": len(residue)},
                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
