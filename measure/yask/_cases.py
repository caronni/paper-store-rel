"""Cases: which tiles, which capture, and the crop that carries them.

A case is a TILE RECTANGLE on a printed sheet plus a target
sub-rectangle inside it. The crop is the tile rectangle grown by a halo
and mapped to capture pixels through a global cell->pixel affine, which
is fitted from the archived harvest's own accepted poses — the same
construction ``crop_parity._geometry`` uses, reading ``PoseCommitted``
events instead of a holo1 state because holo3 keeps no state file.

WHY TILE RECTANGLES AND NOT A GAP SET. crop-parity cuts around the
addresses where two receivers disagree. Here the question is a BAND:
sheet H's yellow plane dies in whole columns, and the interesting
geometry is a dead column next to a live one. So the rectangles are
DECLARED, with the certified map recomputed at run time and reported
beside them — never inferred, so a case is reproducible from this file
alone.

Every capture is memmapped read-only and read through ONE window. No
sheet is ever loaded whole.

THE CROP HALF IS A FALLBACK, AND ITS LIMIT IS MEASURED. The battery
does not need a crop file: it reads windows straight off the full
capture at the archived poses, which is cheaper and uses production's
own poses rather than crop-perturbed ones. The crop writer stays for
the case where no archived harvest exists — and for the record of what
happened when it was tried first.

MEASURED NEGATIVE, 2026-08-30: an ordinary `holo3 decode` of an
INTERIOR crop of sheet H (case ``H-smoke``, 4143x5156 px at 2400 dpi,
64 MB) surveys into **21 fragments totalling 12,221 support cells** and
places nothing, in ~3 minutes at 3 workers — against one region of
8,053,285 cells on the same capture whole. The pitch is found
correctly (7.9996 px/cell, class 1/300); what fails is
``survey._adaptive_threshold``, an Otsu split on the tensor score. On a
whole sheet the two modes it separates are paper and print. On a crop
cut entirely inside the printed field there is no paper, so Otsu splits
*within* the print and the support mask shatters. Anyone cutting holo3
crops for a colour sheet should include real page margin — or, as here,
skip the decode and bring the poses.

Run ``python -m measure.yask._cases --case H-smoke`` to cut a crop and
print its record.
"""
from __future__ import annotations

import collections
import json
import lzma
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import _paths

TILE = 64

#: Fixed, carried from crop_parity: the pixel bbox is padded by this
#: many cells' worth of pixels before it is clipped to the capture, so
#: local pose deviation from the global fit cannot clip a target.
PX_PAD_CELLS = 32


@dataclass(frozen=True)
class Sheet:
    """A printed sheet: its identity, its generation record, its scans."""

    key: str
    format_ref: str
    #: The e033 generation directory (payload + emitted field).
    gen_dir: Path
    #: The archived harvest whose poses fit the affine and whose
    #: certificate map is the production baseline.
    events_xz: Path
    certified_tiles_json: Path
    tiles_yx: tuple[int, int]
    #: capture key -> (path, dpi, sha256).
    captures: dict[str, tuple[Path, float, str]]


SHEET_H = Sheet(
    key="H",
    format_ref="L:c2-cmy8-r0850-p120-x1@3392x2368",
    gen_dir=_paths.E033 / "H-c2-cmy8r0850-q090-4mm",
    events_xz=_paths.OVERNIGHT / "sheetH-maxstack-events.jsonl.xz",
    certified_tiles_json=(_paths.OVERNIGHT
                          / "sheetH-maxstack-certified-tiles.json"),
    tiles_yx=(53, 37),
    # sha256 of the file IS the capture id holo3 mints
    # (``intake.ingest_capture``), so this table is self-checking: a
    # capture whose sha does not appear in the harvest's CaptureOpen
    # events is refused by name rather than silently mismatched.
    captures={
        "1200a": (_paths.SCRATCH_IN / ("xerox-canon-18.8-H-c2-cmy8-r850-"
                                       "q90-p120-4mm-1200dpi-a.tiff"),
                  1200.0,
                  "af580c3cf54f26488ef0a8dc956bf7222fa3195b4a1bc99c316"
                  "e0d68646d963c"),
        "1200b": (_paths.SCRATCH_IN / ("xerox-canon-18.8-H-c2-cmy8-r850-"
                                       "q90-p120-4mm-1200dpi-b.tiff"),
                  1200.0,
                  "d792e00a45e77cbf8da102db64397b5271fb605b0a4976dd686"
                  "6f5ba3069f3fb"),
        "2400a": (_paths.SCRATCH_IN / ("xerox-canon-18.8-H-c2-cmy8-r850-"
                                       "q90-p120-4mm-2400dpi-a.tiff"),
                  2400.0,
                  "68c16fcbf29b23d72765dbaaf96c88c8df162b90640b392f25b"
                  "cd1d03f3b0ed9"),
        "2400b": (_paths.SCRATCH_IN / ("xerox-canon-18.8-H-c2-cmy8-r850-"
                                       "q90-p120-4mm-2400dpi-b.tiff"),
                  2400.0,
                  "4fddac74cef1f0152d7ff1a066c9e13835bda51af1f5faaff02"
                  "d6e2a707d16be"),
        "4800a": (_paths.SCRATCH_IN / ("xerox-canon-18.8-H-c2-cmy8-r850-"
                                       "q90-p120-4mm-4800dpi-a.tiff"),
                  4800.0,
                  "f6920518c82a2ea2d50e438259ee7caf31bdc34eaae2547cc42"
                  "27b5e97c85680"),
        "4800b": (_paths.SCRATCH_IN / ("xerox-canon-18.8-H-c2-cmy8-r850-"
                                       "q90-p120-4mm-4800dpi-b.tiff"),
                  4800.0,
                  "9c022bd308aea90a09ff772c3f35f9c2ca873b7815cbb313924"
                  "d1cdb8be8901f"),
        "4800c": (_paths.SCRATCH_IN / ("xerox-canon-18.8-H-c2-cmy8-r850-"
                                       "q90-p120-4mm-4800dpi-c.tiff"),
                  4800.0,
                  "f642cab0416ccd8186fc2180c4ec3dcea0a38c45c7325ebf4fe"
                  "ccc4cb9da4e6d"),
    },
)

SHEETS = {SHEET_H.key: SHEET_H}


@dataclass(frozen=True)
class Case:
    """One crop and the tiles it is asked about."""

    case_id: str
    sheet: str
    capture: str
    #: Half-open tile rectangle the crop must carry: (ty0, ty1, tx0, tx1).
    crop_tiles: tuple[int, int, int, int]
    #: Half-open tile rectangle under test, inside ``crop_tiles``.
    target_tiles: tuple[int, int, int, int]
    halo_cells: int
    note: str

    @property
    def target_positions(self) -> tuple[tuple[int, int], ...]:
        ty0, ty1, tx0, tx1 = self.target_tiles
        return tuple((ty, tx) for ty in range(ty0, ty1)
                     for tx in range(tx0, tx1))


CASES: tuple[Case, ...] = (
    Case(case_id="H-smoke", sheet="H", capture="2400a",
         crop_tiles=(31, 34, 16, 21), target_tiles=(31, 34, 18, 21),
         halo_cells=128,
         note="timing/plumbing smoke: three rows of the tx 18-20 dead "
              "band with one live column (tx 16-17) beside them"),
    Case(case_id="H-a", sheet="H", capture="2400a",
         crop_tiles=(30, 36, 15, 22), target_tiles=(30, 36, 18, 22),
         halo_cells=192,
         note="the primary: 24 target tiles in the tx 18-21 dead band, "
              "18 fully certified tiles (tx 15-17) alongside them"),
    Case(case_id="H-b", sheet="H", capture="2400a",
         crop_tiles=(6, 12, 0, 8), target_tiles=(6, 12, 0, 4),
         halo_cells=192,
         note="the isolated band: tx 0-3 at the sheet's left edge, with "
              "no Y-certified tile inside the crop"),
    Case(case_id="H-c", sheet="H", capture="2400a",
         crop_tiles=(16, 22, 22, 29), target_tiles=(16, 22, 25, 28),
         halo_cells=192,
         note="tx 25-27, a band that dies at tx 25 (production Y 0/53) "
              "and recovers by tx 27 (45/53) — H-a's geometry on the "
              "other side of the sheet, with the gradient inside it"),
    Case(case_id="H-d", sheet="H", capture="2400a",
         crop_tiles=(6, 12, 7, 15), target_tiles=(6, 12, 8, 14),
         halo_cells=192,
         note="the MARGINAL band: tx 8-13, where production certifies "
              "yellow on roughly half the rows, so a failed tile is a "
              "near miss rather than a dead one — the place an additive "
              "arm converts first"),
    Case(case_id="H-e", sheet="H", capture="2400a",
         crop_tiles=(20, 26, 20, 27), target_tiles=(20, 26, 22, 26),
         halo_cells=192,
         note="a second marginal band (tx 22-25) on the other side of "
              "the sheet, live columns tx 20-21 and 26 beside it"),
    # The four rectangles below were CHOSEN BY RULE, not by result: the
    # first four disjoint 6x6 tile blocks whose 36 tiles are all
    # C+M-certified in production and whose production Y rate is closest
    # to 45% (`probe`: 25%-70% band, greedy non-overlapping, scanned in
    # (ty, tx) order). A block at 45% is where a failed yellow tile is a
    # near miss, so it is where an additive arm converts first.
    Case(case_id="H-m1", sheet="H", capture="2400a",
         crop_tiles=(7, 13, 22, 28), target_tiles=(7, 13, 22, 28),
         halo_cells=192, note="marginal block, production Y 16/36"),
    Case(case_id="H-m2", sheet="H", capture="2400a",
         crop_tiles=(12, 18, 8, 14), target_tiles=(12, 18, 8, 14),
         halo_cells=192, note="marginal block, production Y 16/36"),
    Case(case_id="H-m3", sheet="H", capture="2400a",
         crop_tiles=(18, 24, 10, 16), target_tiles=(18, 24, 10, 16),
         halo_cells=192, note="marginal block, production Y 16/36"),
    Case(case_id="H-m4", sheet="H", capture="2400a",
         crop_tiles=(28, 34, 7, 13), target_tiles=(28, 34, 7, 13),
         halo_cells=192, note="marginal block, production Y 16/36"),
    Case(case_id="H-a-b", sheet="H", capture="2400b",
         crop_tiles=(30, 36, 15, 22), target_tiles=(30, 36, 18, 22),
         halo_cells=192,
         note="H-a on the second 2400 dpi platen placement — the "
              "capture control (a dead band that is print-frozen must "
              "die identically on both)"),
)

CASES_BY_ID = {case.case_id: case for case in CASES}


# --------------------------------------------------------------------
# the archived harvest: poses and the certificate map
# --------------------------------------------------------------------


def read_harvest(sheet: Sheet) -> tuple[dict, dict]:
    """(poses by (capture, level), capture facts by capture id)."""
    poses: dict[tuple[str, int], list[dict]] = collections.defaultdict(list)
    captures: dict[str, dict] = {}
    with lzma.open(sheet.events_xz, "rt", encoding="utf-8") as handle:
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
    return dict(poses), captures


def certified_map(sheet: Sheet) -> dict[tuple[int, int], frozenset[str]]:
    """(ty, tx) -> the streams the production harvest certified."""
    rows = json.loads(sheet.certified_tiles_json.read_text("utf-8"))
    out: dict[tuple[int, int], set[str]] = {}
    for stream, ty, tx in rows:
        out.setdefault((int(ty), int(tx)), set()).add(str(stream))
    return {key: frozenset(value) for key, value in out.items()}


def native_affine_for(sheet: Sheet, capture_id: str, poses: dict):
    """The finest level's global cell->pixel affine for one capture.

    ``native_affine`` is a NATIVE-pixel map at every level, so any
    level's poses fit the same map; the finest level is chosen because
    it has the tightest poses.
    """
    from measure.crop_parity import _geometry

    levels = sorted(level for (cid, level) in poses if cid == capture_id)
    if not levels:
        raise SystemExit(f"yask: no accepted pose carries capture "
                         f"{capture_id[:12]}… in {sheet.events_xz.name}")
    return _geometry.fit_global_affine(poses[(capture_id, levels[-1])])


# --------------------------------------------------------------------
# the crop
# --------------------------------------------------------------------


def cell_bbox(case: Case, page_cells_yx: tuple[int, int],
              ) -> tuple[int, int, int, int]:
    """X-first half-open ``(cx0, cy0, cx1, cy1)``, clipped to the page."""
    cells_y, cells_x = page_cells_yx
    ty0, ty1, tx0, tx1 = case.crop_tiles
    return (max(0, tx0 * TILE - case.halo_cells),
            max(0, ty0 * TILE - case.halo_cells),
            min(cells_x, tx1 * TILE + case.halo_cells),
            min(cells_y, ty1 * TILE + case.halo_cells))


def px_bbox(cells: tuple[int, int, int, int], affine,
            capture_shape_yx: tuple[int, int]) -> tuple[int, int, int, int]:
    from measure.crop_parity import _geometry

    return _geometry.px_bbox_for(cells, affine, capture_shape_yx)


def write_crop(case: Case, sheet: Sheet, box: tuple[int, int, int, int],
               out_dir: Path) -> dict:
    """One windowed read off a read-only memmap; one crop tiff out."""
    import tifffile

    path, dpi, sha = sheet.captures[case.capture]
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{case.case_id}.tiff"
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


def prepare(case: Case) -> dict:
    """Everything a run needs about a case's geometry and its crop."""
    sheet = SHEETS[case.sheet]
    path, dpi, sha = sheet.captures[case.capture]
    _paths.refuse_if_absent((path, sheet.events_xz, sheet.gen_dir,
                             sheet.certified_tiles_json))
    poses, captures = read_harvest(sheet)
    if sha not in captures:
        raise SystemExit(
            f"yask: capture {sha[:12]}… ({path.name}) is not one of the "
            f"captures {sheet.events_xz.name} was harvested from")
    facts = captures[sha]
    affine = native_affine_for(sheet, sha, poses)
    page_cells = (sheet.tiles_yx[0] * TILE, sheet.tiles_yx[1] * TILE)
    cells = cell_bbox(case, page_cells)
    box = px_bbox(cells, affine, facts["shape_yx"])
    crop = write_crop(case, sheet, box, _paths.SCRATCH / "crops")
    return {
        "case": case, "sheet": sheet, "capture_sha256": sha,
        "capture_path": str(path), "dpi": dpi,
        "capture_facts": facts,
        "cell_bbox": list(cells),
        "affine_cell_to_px": [list(r) for r in affine.rows],
        "affine_fit": {"n_poses": affine.n_poses,
                       "px_per_cell": affine.px_per_cell,
                       "residual_median_px": affine.residual_median_px,
                       "residual_p99_px": affine.residual_p99_px,
                       "residual_max_px": affine.residual_max_px},
        "crop": crop,
        "certified": certified_map(sheet),
    }


def main(argv: list[str] | None = None) -> int:
    """Cut one case's crop and print its geometry record."""
    import argparse

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--case", required=True,
                        help=f"one of {sorted(CASES_BY_ID)}")
    args = parser.parse_args(argv)
    if args.case not in CASES_BY_ID:
        raise SystemExit(f"yask: unknown case {args.case!r}; declared: "
                         f"{sorted(CASES_BY_ID)}")
    record = prepare(CASES_BY_ID[args.case])
    certified = record.pop("certified")
    record.pop("sheet")
    case = record.pop("case")
    census = {"target_tiles": len(case.target_positions),
              "target_with_production_y": sum(
                  1 for position in case.target_positions
                  if "Y" in certified.get(position, frozenset()))}
    print(json.dumps({**record, "case": case.case_id, "census": census},
                     indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
