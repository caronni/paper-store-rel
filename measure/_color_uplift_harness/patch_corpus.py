"""Specimen patches: physical windows cut out of the archived captures.

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.patch_corpus list
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.patch_corpus extract --name l00tax-a
    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.patch_corpus verify

A SPECIMEN is a small standalone mini-TIFF cut out of a
provenance-verified capture: a named tile neighbourhood plus a halo of
whole tiles, mounted on a paper-coloured margin.  The production receiver
decodes it as a SCRAP — survey, placement, BCH word solve, absolute
addresses, the full multi-lane payload ladder — in minutes rather than
the hour a whole capture costs, so a pathology the campaign measured once
on paper becomes a permanent end-to-end regression specimen.

WHAT A SPECIMEN IS NOT.  ``scan.SourceId`` states the acquisition law: a
cropped copy is CORRELATED evidence, never an independent acquisition.  A
patch therefore only ever runs ALONE, in its own fresh state; no pipeline
may put a patch and its parent capture (or two patches of one capture)
into one session.  ``patch_runner`` enforces the fresh state; this module
records the parent sha in every manifest row so a patch can always be
traced back to the capture it was cut from.

GEOMETRY.  Tile ``(ty, tx)`` owns page cells ``[64ty, 64ty+64) x
[64tx, 64tx+64)``, and the archived state's ``PoseRecord.native_affine``
is the committed map from absolute page cells to native pixel centres
(rotation included).  The crop rectangle is the bounding box of the tile
rectangle's corners mapped through the FOUR nearest committed poses, so
page warp and pose-to-pose disagreement are absorbed rather than assumed
away.  Every crop is clamped to the capture and the clamp is recorded.

THE MOUNT.  A crop out of the middle of a page has printed content
running off all four edges, which is not what the survey's log-Otsu
segmentation was qualified on (``test_receive_small_scrap`` mounts its
scrap on a white canvas for the same reason).  Each specimen is therefore
mounted on a constant margin whose colour is the crop's OWN per-channel
99.5th percentile — the patch's measured paper level, not an invented
white.  Margin width and fill are recorded per row; a specimen with
``mount_mm = 0`` is bit-exact capture pixels and nothing else.

Content-keyed and sha-gated: a row regenerates only when its inputs, this
module's ``PATCH_SCHEMA``, or the specimen definition move.  Deleting the
patch files is always safe.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from . import corpus, state_cache
from .corpus import CaptureRow

PATCH_SCHEMA = "color-uplift-patch-1"
MANIFEST_PATH = corpus.HARNESS_DIR / "patch_manifest.json"
TILE_CELLS = 64
# Mapping poses averaged per crop: enough to absorb pose-to-pose
# disagreement, few enough to stay local to the tile rectangle.
MAPPING_POSES = 4
# The mounted margin's colour: the crop's own paper level.  A percentile,
# not the maximum, so one specular pixel cannot set it.
PAPER_PERCENTILE = 99.5


@dataclass(frozen=True, slots=True)
class Specimen:
    """One named patch: a tile rectangle of one capture, plus a halo.

    ``tiles_y``/``tiles_x`` are half-open CORE tile ranges — the tiles the
    specimen is ABOUT.  ``halo_tiles`` whole tiles are added on every side
    (clamped at the page edge, and the clamp is recorded), so window
    placement and pilot context never have to reach outside the crop for
    the core tiles.
    """

    name: str
    capture: str
    theme: str
    tiles_y: tuple[int, int]
    tiles_x: tuple[int, int]
    halo_tiles: int
    note: str
    mount_mm: float = 3.0

    def core_tiles(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            (ty, tx)
            for ty in range(*self.tiles_y)
            for tx in range(*self.tiles_x))

    @property
    def core_shape(self) -> tuple[int, int]:
        return (self.tiles_y[1] - self.tiles_y[0],
                self.tiles_x[1] - self.tiles_x[0])


# ---------------------------------------------------------------------------
# The initial specimen set.  Every coordinate is read off the campaign's
# own measured record (COLOR-UPLIFT-MEASUREMENTS §4.5.1/§5/§6) or off the
# archived states, and the provenance is spelled out in each note.
# ---------------------------------------------------------------------------
SPECIMENS: tuple[Specimen, ...] = (
    # (s1) The §4.5.1 l00 tax.  The PK3 head, run at l00 on xerox
    # c3-cmy7, lost 38 addresses that the force-null arm certified; these
    # three patches cover the three tightest clusters of that loss list
    # (5, 3 and 2 of the 38 respectively).
    Specimen(
        name="l00tax-a", capture="xerox-c3-cmy7", theme="s1",
        tiles_y=(10, 13), tiles_x=(8, 12), halo_tiles=1,
        note="5 of the 38 §4.5.1 l00-tax addresses: (10,10) (10,11) "
             "(12,8) (12,10) (12,11)"),
    Specimen(
        name="l00tax-b", capture="xerox-c3-cmy7", theme="s1",
        tiles_y=(32, 34), tiles_x=(1, 4), halo_tiles=1,
        note="3 of the 38 §4.5.1 l00-tax addresses: (32,1) (33,1) (33,3)"),
    Specimen(
        name="l00tax-c", capture="xerox-c3-cmy7", theme="s1",
        tiles_y=(11, 14), tiles_x=(3, 8), halo_tiles=1,
        note="3 of the 38 §4.5.1 l00-tax addresses: (11,7) (12,5) (13,3)"),
    # (s2) A3's biggest wins on the uplift target (§5.7): the l01/l02
    # addresses PK4 gained over PK3 on hp c3-cmy8, in their two tightest
    # neighbourhoods.
    Specimen(
        name="a3gain-a", capture="hp-c3-cmy8", theme="s2",
        tiles_y=(30, 34), tiles_x=(6, 10), halo_tiles=1,
        note="5 PK4-gained C addresses (l01/l02): (30,8) (32,6) (32,8) "
             "(32,9) (33,6)"),
    Specimen(
        name="a3gain-b", capture="hp-c3-cmy8", theme="s2",
        tiles_y=(3, 5), tiles_x=(20, 22), halo_tiles=1,
        note="3 PK4-gained C addresses at l02: (3,21) (4,20) (4,21)"),
    # (s3) The page-column-0 pair PK4 lost against the archived set
    # (§5.6 finding 2 / §6.2): a one-tile-wide strip down the left page
    # edge, so the left halo CLAMPS and the specimen carries the
    # one-sided-support geometry the hypothesis is about.
    Specimen(
        name="edge-col0", capture="xerox-c3-cmy7", theme="s3",
        tiles_y=(6, 16), tiles_x=(0, 1), halo_tiles=1,
        note="the two column-0 addresses PK4 lost vs archived: (0,6,0) "
             "and (0,15,0); left halo clamps at the page edge"),
    # (s4) Clean controls, one per capture class.
    Specimen(
        name="clean-cmy7", capture="xerox-c3-cmy7", theme="s4",
        tiles_y=(2, 4), tiles_x=(2, 4), halo_tiles=1,
        note="healthy c3-cmy7 control: all four core tiles certified in "
             "the archived state"),
    Specimen(
        name="clean-cmy8", capture="xerox-c2-cmy8", theme="s4",
        tiles_y=(25, 27), tiles_x=(19, 21), halo_tiles=1,
        note="healthy c2-cmy8 control: all four core tiles carry C, M "
             "AND Y certificates in the archived state"),
    # (s5) The print-frozen negative control.
    Specimen(
        name="frozen-cmy7", capture="xerox-c2-cmy7", theme="s5",
        tiles_y=(26, 28), tiles_x=(1, 3), halo_tiles=1,
        note="xerox c2-cmy7 print-frozen junk: no tile within two of "
             "this rectangle certified in the archived 83-cert state"),
    # (s6) The M tail.  On hp c3-cmy8 M certifies in essentially ONE tile
    # column (tx=12, plus a few at tx=0); this specimen straddles that
    # column so one patch holds both M-certifying and M-failing tiles.
    Specimen(
        name="mtail-hp", capture="hp-c3-cmy8", theme="s6",
        tiles_y=(16, 19), tiles_x=(11, 14), halo_tiles=1,
        note="M certifies at (16,12) (17,12) (18,12) and nowhere else in "
             "this rectangle — the M-tail column, with its failing "
             "neighbours tx=11 and tx=13 in the same patch"),
)

SPECIMENS_BY_NAME = {row.name: row for row in SPECIMENS}


def specimen(name: str) -> Specimen:
    try:
        return SPECIMENS_BY_NAME[name]
    except KeyError:
        raise SystemExit(
            f"unknown specimen {name!r}; known: "
            + ", ".join(sorted(SPECIMENS_BY_NAME))) from None


def patch_dir() -> Path:
    return corpus.work_dir("patches")


def load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        return {"schema": PATCH_SCHEMA, "patches": {}}
    manifest = json.loads(MANIFEST_PATH.read_text())
    if manifest.get("schema") != PATCH_SCHEMA:
        return {"schema": PATCH_SCHEMA, "patches": {}}
    return manifest


def write_manifest(manifest: dict) -> None:
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n")


def manifest_row(name: str) -> dict:
    manifest = load_manifest()
    try:
        return manifest["patches"][name]
    except KeyError:
        raise SystemExit(
            f"specimen {name!r} is not extracted; run "
            f"`patch_corpus extract --name {name}`") from None


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------


def _ordinary_poses(cache: state_cache.CaptureCache) -> tuple:
    """Every committed pose of the ORDINARY lanes, in a flat tuple.

    Mop-up and refinement poses are minted against the same native frame,
    but the ordinary ladder is the one that placed the page, so its poses
    are the geometry of record here.
    """
    rows: list = []
    for lane in cache.plan:
        if lane.mopup_of is None and lane.refine_of is None:
            rows.extend(cache.poses_by_lane.get(lane.lane_id, ()))
    if not rows:
        raise SystemExit(
            "the archived state carries no ordinary-lane poses; a patch "
            "cannot be located without committed geometry")
    return tuple(rows)


def _pose_centre_cells(pose) -> np.ndarray:
    origin = np.asarray(pose.cell_origin_yx, np.float64)
    shape = np.asarray(pose.window_shape_yx_cells, np.float64)
    return origin + shape / 2.0


def _map_cells(pose, cells_yx: np.ndarray) -> np.ndarray:
    """Map page cells through one pose's committed native affine."""
    affine = np.asarray(pose.native_affine, np.float64).reshape(2, 3)
    homogeneous = np.concatenate(
        (np.asarray(cells_yx, np.float64),
         np.ones((len(cells_yx), 1), np.float64)), axis=1)
    return homogeneous @ affine.T


@dataclass(frozen=True, slots=True)
class CropRect:
    """One specimen's native pixel rectangle and the cells it covers."""

    y0: int
    y1: int
    x0: int
    x1: int
    cells_y: tuple[int, int]
    cells_x: tuple[int, int]
    tiles_y: tuple[int, int]
    tiles_x: tuple[int, int]
    clamped: tuple[str, ...]
    px_per_cell: float
    poses_used: tuple[str, ...]

    @property
    def shape_yx(self) -> tuple[int, int]:
        return (self.y1 - self.y0, self.x1 - self.x0)


def crop_rect(cache: state_cache.CaptureCache, spec, row: Specimen) -> CropRect:
    """Locate one specimen in native pixels through the committed poses."""
    tiles_yx = spec.layout.tiles_yx
    clamped: list[str] = []
    ty0 = row.tiles_y[0] - row.halo_tiles
    ty1 = row.tiles_y[1] + row.halo_tiles
    tx0 = row.tiles_x[0] - row.halo_tiles
    tx1 = row.tiles_x[1] + row.halo_tiles
    for label, value, limit in (("top", ty0, 0), ("left", tx0, 0)):
        if value < limit:
            clamped.append(f"{label}-halo-clamped-at-page-edge")
    if ty1 > tiles_yx[0]:
        clamped.append("bottom-halo-clamped-at-page-edge")
    if tx1 > tiles_yx[1]:
        clamped.append("right-halo-clamped-at-page-edge")
    ty0, tx0 = max(0, ty0), max(0, tx0)
    ty1, tx1 = min(tiles_yx[0], ty1), min(tiles_yx[1], tx1)
    if ty1 - ty0 < row.core_shape[0] or tx1 - tx0 < row.core_shape[1]:
        raise SystemExit(f"{row.name}: tile rectangle leaves the page")
    if (ty0 > row.tiles_y[0] - 1 and row.tiles_y[0] > 0) or (
            tx0 > row.tiles_x[0] - 1 and row.tiles_x[0] > 0):
        raise SystemExit(f"{row.name}: halo was lost off the page interior")

    cells_y = (ty0 * TILE_CELLS, ty1 * TILE_CELLS)
    cells_x = (tx0 * TILE_CELLS, tx1 * TILE_CELLS)
    corners = np.asarray(
        [(cells_y[0], cells_x[0]), (cells_y[0], cells_x[1]),
         (cells_y[1], cells_x[0]), (cells_y[1], cells_x[1])], np.float64)
    centre = corners.mean(axis=0)
    poses = _ordinary_poses(cache)
    distance = np.asarray(
        [float(np.hypot(*(_pose_centre_cells(pose) - centre)))
         for pose in poses])
    order = np.argsort(distance, kind="stable")[:MAPPING_POSES]
    chosen = tuple(poses[int(index)] for index in order)
    mapped = np.concatenate(
        [_map_cells(pose, corners) for pose in chosen], axis=0)
    # One cell of slack on every side: the affines disagree by a fraction
    # of a cell and the aperture filter reads a little past its points.
    scale = float(np.median(np.abs(np.asarray(
        [np.asarray(pose.native_affine, np.float64).reshape(2, 3)[:, :2]
         for pose in chosen]))))
    pad = int(np.ceil(scale))
    height, width = cache.capture_shape_yx
    y0 = int(np.floor(mapped[:, 0].min())) - pad
    y1 = int(np.ceil(mapped[:, 0].max())) + pad
    x0 = int(np.floor(mapped[:, 1].min())) - pad
    x1 = int(np.ceil(mapped[:, 1].max())) + pad
    for label, low, high, limit in (("y", y0, y1, height), ("x", x0, x1, width)):
        if low < 0:
            clamped.append(f"{label}0-clamped-at-capture-edge")
        if high > limit:
            clamped.append(f"{label}1-clamped-at-capture-edge")
    y0, x0 = max(0, y0), max(0, x0)
    y1, x1 = min(height, y1), min(width, x1)
    if y1 - y0 < 2 or x1 - x0 < 2:
        raise SystemExit(f"{row.name}: crop rectangle is degenerate")
    return CropRect(
        y0=y0, y1=y1, x0=x0, x1=x1,
        cells_y=cells_y, cells_x=cells_x,
        tiles_y=(ty0, ty1), tiles_x=(tx0, tx1),
        clamped=tuple(dict.fromkeys(clamped)),
        px_per_cell=scale,
        poses_used=tuple(pose.pose_id for pose in chosen))


# ---------------------------------------------------------------------------
# extraction
# ---------------------------------------------------------------------------


def _memmap_capture(capture_row: CaptureRow) -> np.ndarray:
    """Memory-map one archived capture TIFF, read-only.

    The corpus root is never written.  ``tifffile`` gives a true memory
    map for these uncompressed scanner pages, so a 6.9 GB capture costs a
    page-cache read of the crop and nothing else.
    """
    import tifffile

    with tifffile.TiffFile(capture_row.tiff_path()) as handle:
        if len(handle.pages) != 1:
            raise SystemExit(
                f"{capture_row.key}: capture TIFF is multi-page")
        return handle.pages[0].asarray(out="memmap")


def _mount(crop: np.ndarray, mount_px: int) -> tuple[np.ndarray, list[int]]:
    """Mount a crop on a margin of its own measured paper colour."""
    fill = [int(round(float(np.percentile(crop[..., channel],
                                          PAPER_PERCENTILE))))
            for channel in range(crop.shape[2])]
    if mount_px <= 0:
        return np.ascontiguousarray(crop), fill
    height, width, channels = crop.shape
    canvas = np.empty(
        (height + 2 * mount_px, width + 2 * mount_px, channels), crop.dtype)
    for channel in range(channels):
        canvas[..., channel] = fill[channel]
    canvas[mount_px:mount_px + height, mount_px:mount_px + width] = crop
    return canvas, fill


def _gt_slice(capture_row: CaptureRow, rect: CropRect) -> np.ndarray:
    """The emitted page GT for exactly this tile rectangle.

    Sliced out of ``gt_score.load_ground_truth`` — the same packing recipe
    and the same manifest checks — so a specimen carries truth for its own
    tiles without re-deriving anything.
    """
    from .gt_score import load_ground_truth

    truth = load_ground_truth(capture_row)
    block = truth.cell_bits[
        :, rect.cells_y[0]:rect.cells_y[1], rect.cells_x[0]:rect.cells_x[1]]
    return np.ascontiguousarray(block)


def _specimen_key(row: Specimen) -> dict:
    """The specimen definition in its stored (JSON) shape.

    ``asdict`` keeps tuples; JSON does not.  Comparing the two forms
    directly reported every row as "definition moved" and silently
    defeated the sha gate, so both sides are normalised here.
    """
    return json.loads(json.dumps(asdict(row), sort_keys=True))


def _sha_array(values: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update(f"holo-patch|{values.dtype.str}|{values.shape}|".encode())
    digest.update(np.ascontiguousarray(values))
    return digest.hexdigest()


def extract(row: Specimen, *, force: bool = False,
            native: np.ndarray | None = None,
            verbose: bool = True) -> dict:
    """Cut one specimen out of its capture and record its manifest row."""
    import tifffile

    capture_row = corpus.capture(row.capture)
    cache = state_cache.load(capture_row, verbose=False)
    state_cache.verify_against_provenance(capture_row, cache)
    recorded = corpus.provenance_row(capture_row.key)
    spec = corpus.resolve_spec(capture_row, cache.format_row_id)
    rect = crop_rect(cache, spec, row)
    tiff_path = patch_dir() / f"{row.name}.tiff"
    gt_path = patch_dir() / f"{row.name}-gt.npy"
    existing = load_manifest()["patches"].get(row.name)
    key = {
        "schema": PATCH_SCHEMA,
        "specimen": _specimen_key(row),
        "capture_sha256": recorded["artifacts"]["tiff"]["sha256"],
        "state_sha256": cache.state_sha256,
        "crop_native_yx": [rect.y0, rect.y1, rect.x0, rect.x1],
    }
    if (not force and existing is not None
            and existing.get("content_key") == key
            and tiff_path.is_file() and gt_path.is_file()
            and existing.get("tiff_sha256")
            == corpus.sha256_file(tiff_path)
            and existing.get("gt_sha256") == corpus.sha256_file(gt_path)):
        if verbose:
            print(f"{row.name}: up to date")
        return existing

    started = time.perf_counter()
    pixels = _memmap_capture(capture_row) if native is None else native
    if tuple(pixels.shape[:2]) != tuple(cache.capture_shape_yx):
        raise SystemExit(
            f"{row.name}: capture shape {pixels.shape[:2]} != archived "
            f"{cache.capture_shape_yx}")
    if pixels.ndim != 3 or pixels.shape[2] != 3:
        raise SystemExit(f"{row.name}: capture is not RGB")
    crop = np.array(pixels[rect.y0:rect.y1, rect.x0:rect.x1], copy=True)
    mount_px = int(round(row.mount_mm / 25.4 * capture_row.scan_dpi))
    canvas, fill = _mount(crop, mount_px)
    truth = _gt_slice(capture_row, rect)
    tifffile.imwrite(tiff_path, canvas, photometric="rgb")
    np.save(gt_path, truth)
    entry = {
        "schema": PATCH_SCHEMA,
        "name": row.name,
        "theme": row.theme,
        "note": row.note,
        "content_key": key,
        "capture": capture_row.key,
        "engine": capture_row.engine,
        "kind": capture_row.kind,
        "capture_sha256": recorded["artifacts"]["tiff"]["sha256"],
        "state_sha256": cache.state_sha256,
        "format_row_id": cache.format_row_id,
        "coding_id": capture_row.manifest()["coding_id"],
        "printer_id": capture_row.manifest()["printer_id"],
        "scan_dpi": capture_row.scan_dpi,
        "page": 0,
        "core_tiles_y": list(row.tiles_y),
        "core_tiles_x": list(row.tiles_x),
        "halo_tiles": row.halo_tiles,
        "domain_tiles_y": list(rect.tiles_y),
        "domain_tiles_x": list(rect.tiles_x),
        "domain_cells_y": list(rect.cells_y),
        "domain_cells_x": list(rect.cells_x),
        "crop_native_yx": [rect.y0, rect.y1, rect.x0, rect.x1],
        "crop_shape_yx": list(rect.shape_yx),
        "clamped": list(rect.clamped),
        "px_per_cell": round(rect.px_per_cell, 4),
        "mapping_pose_ids": list(rect.poses_used),
        "mount_mm": row.mount_mm,
        "mount_px": mount_px,
        "mount_fill_rgb": fill,
        "tiff": str(tiff_path),
        "tiff_shape_yx": [int(canvas.shape[0]), int(canvas.shape[1])],
        "tiff_bytes": int(tiff_path.stat().st_size),
        "tiff_sha256": corpus.sha256_file(tiff_path),
        "gt": str(gt_path),
        "gt_shape": list(truth.shape),
        "gt_array_sha256": _sha_array(truth),
        "gt_sha256": corpus.sha256_file(gt_path),
        "extract_seconds": round(time.perf_counter() - started, 1),
        "command": (
            "PYTHONPATH=src:measure python -m "
            f"_color_uplift_harness.patch_corpus extract --name {row.name}"),
    }
    manifest = load_manifest()
    manifest["patches"][row.name] = entry
    write_manifest(manifest)
    if verbose:
        print(json.dumps({
            "name": row.name, "capture": capture_row.key,
            "core_tiles": f"{row.core_shape[0]}x{row.core_shape[1]}",
            "crop_shape_yx": entry["tiff_shape_yx"],
            "mib": round(entry["tiff_bytes"] / 2**20, 1),
            "clamped": entry["clamped"],
            "seconds": entry["extract_seconds"]}))
    return entry


def extract_many(rows: tuple[Specimen, ...], *, force: bool = False) -> None:
    """Extract several specimens, memory-mapping each capture once."""
    by_capture: dict[str, list[Specimen]] = {}
    for row in rows:
        by_capture.setdefault(row.capture, []).append(row)
    for capture_key, group in sorted(by_capture.items()):
        native: np.ndarray | None = None
        for row in group:
            if native is None:
                native = _memmap_capture(corpus.capture(capture_key))
            extract(row, force=force, native=native)
        del native


def cmd_list(args: argparse.Namespace) -> int:
    manifest = load_manifest()["patches"]
    for row in SPECIMENS:
        entry = manifest.get(row.name)
        print(json.dumps({
            "name": row.name, "theme": row.theme, "capture": row.capture,
            "core_tiles_y": list(row.tiles_y),
            "core_tiles_x": list(row.tiles_x),
            "halo_tiles": row.halo_tiles,
            "extracted": entry is not None,
            "crop_shape_yx": None if entry is None
            else entry["tiff_shape_yx"],
            "mib": None if entry is None
            else round(entry["tiff_bytes"] / 2**20, 1),
            "note": row.note}))
    return 0


def cmd_extract(args: argparse.Namespace) -> int:
    rows = (tuple(specimen(name) for name in args.name) if args.name
            else SPECIMENS)
    extract_many(rows, force=bool(args.force))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Re-hash every extracted specimen against its manifest row."""
    manifest = load_manifest()["patches"]
    failures = 0
    for row in SPECIMENS:
        entry = manifest.get(row.name)
        if entry is None:
            print(f"{row.name}: NOT EXTRACTED")
            failures += 1
            continue
        problems = []
        if entry["content_key"]["specimen"] != _specimen_key(row):
            problems.append("specimen definition moved")
        for label, path_key, sha_key in (
                ("tiff", "tiff", "tiff_sha256"), ("gt", "gt", "gt_sha256")):
            path = Path(entry[path_key])
            if not path.is_file():
                problems.append(f"{label} missing")
            elif corpus.sha256_file(path) != entry[sha_key]:
                problems.append(f"{label} sha mismatch")
        recorded = corpus.provenance_row(entry["capture"])
        if recorded["artifacts"]["tiff"]["sha256"] != entry["capture_sha256"]:
            problems.append("parent capture sha moved")
        print(json.dumps({"name": row.name,
                          "ok": not problems, "problems": problems}))
        failures += bool(problems)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.patch_corpus", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    item = sub.add_parser("list")
    item.set_defaults(handler=cmd_list)

    item = sub.add_parser("extract")
    item.add_argument("--name", action="append", default=[],
                      help="specimen name (repeatable; default all)")
    item.add_argument("--force", action="store_true",
                      help="re-extract even when the content key matches")
    item.set_defaults(handler=cmd_extract)

    item = sub.add_parser("verify")
    item.set_defaults(handler=cmd_verify)

    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    from _color_uplift_harness import patch_corpus as _module

    raise SystemExit(_module.main())
