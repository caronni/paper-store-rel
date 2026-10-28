#!/usr/bin/env python
"""THE SELF-CHECK — the pure geometry, and the frame on a synthetic case.

    cd <checkout>
    PYTHONPATH=. env314t/bin/python -m measure.crop_parity._selfcheck
    …                                          --skip-decodes   # pure only
    …                                          --with-holo1     # both sides

TWO PARTS.

**Pure** (no I/O, milliseconds): the clustering gap semantics, the
split's conservation law, the cell/pixel bbox arithmetic including a
180-degree capture, the control rim rule and its target exclusion, and
the manifest schema's refusal of a drifted key.

**The frame, on a synthetic case** (real decodes, ~30 s): THE claim this
harness rests on is that a crop decodes into the FULL-SHEET address
frame with no origin shift applied, because a printed tile carries its
own absolute address word. That claim is checked here where the answer
is known: the K simulation page (``_distill/verify/sim/sim-k-1200dpi.
tiff``, 7x7 tiles, its payload on disk) is decoded whole; a crop is cut
around one interior tile using the same affine machinery the real cases
use (fitted from the sim's own archived holo1 oracle state); the crop is
decoded; and then

* every crop certificate's address must also be a full-page certificate
  address — same (page, ty, tx, stream), no shift;
* every crop certificate must address a tile inside the crop's cell
  rectangle;
* every crop certificate's BITS must equal ground truth re-encoded from
  the sim payload — a frame shift of one tile would put a real
  certificate at a wrong address, and this is what would catch it;
* the crop must certify at least one interior tile, or the check
  reports that it proved nothing rather than passing vacuously.

The holo3 arm runs by DEFAULT and takes ~50 s. The holo1 arm is
``--with-holo1`` and opt-in for a measured reason (2026-08-29): holo1
decoding this ideal sim page whole, with the ``--mopup --refine`` ladder
the battery uses, passed 20 minutes and 7.9 GiB RSS without finishing —
a self-check nobody will run is not a self-check. holo1's frame is
covered anyway by the battery itself: the e029 case minted 40 holo1
certificates with ZERO out-of-bbox and ZERO GT mismatches, and a shifted
frame cannot produce that. Both arms go through the SAME
``harness.build_command`` the battery uses, so either one also pins the
invocation shapes.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from . import _geometry, _gt, _paths, _state, cases, harness

_paths.install_holo1_src()

SIM_TIFF = _paths.WORKTREE / "_distill/verify/sim/sim-k-1200dpi.tiff"
SIM_PAYLOAD = _paths.WORKTREE / "_distill/verify/sim/sim-k-payload.bin"
SIM_STATE = _paths.WORKTREE / "_distill/verify/sim/k-oracle.state"
SIM_FORMAT = "c3-k-r0550@7x7"
SIM_DPI = 1200.0
SIM_TARGET = (3, 3)                     # the interior tile under study


class SelfCheckError(AssertionError):
    """A self-check failed — the harness's own footing is not sound."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SelfCheckError(message)


# --------------------------------------------------------------------
# part 1 — the pure geometry
# --------------------------------------------------------------------


def check_pure() -> list[str]:
    notes: list[str] = []

    # clustering: the gap is EMPTY TILES between members, so adjacent
    # tiles (gap 0) merge at any gap setting, and two tiles three apart
    # merge at gap 2 but not at gap 1.
    near = [(10, 10), (10, 11)]
    far = [(10, 10), (10, 13)]
    _require(len(_geometry.cluster_tiles(near, 0)) == 1,
             "adjacent tiles must share a cluster at gap 0")
    _require(len(_geometry.cluster_tiles(far, 1)) == 2,
             "tiles three apart must not merge at gap 1")
    _require(len(_geometry.cluster_tiles(far, 2)) == 1,
             "tiles three apart must merge at gap 2")
    notes.append("clustering: gap semantics hold (0/1/2)")

    # splitting conserves every target, and the pieces fit the cap.
    wide = _geometry.cluster_tiles([(5, tx) for tx in range(0, 30, 2)], 2)
    pieces = _geometry.split_clusters(wide, 256)
    _require(sorted(t for c in pieces for t in c.members)
             == sorted(t for c in wide for t in c.members),
             "split lost or duplicated a target")
    _require(all(max(c.span_cells_yx) <= 256 for c in pieces),
             "split left a cluster over the span cap")
    notes.append(f"splitting: {len(wide)} cluster(s) -> {len(pieces)} "
                 "case(s), every target conserved, all within the cap")

    # the cell bbox clips to the page and the halo is symmetric.
    cluster = _geometry.Cluster.of([(0, 0)])
    bbox = _geometry.cell_bbox_for(cluster, 240, (3392, 2368))
    _require(bbox == (0, 0, 304, 304),
             f"cell bbox at the page corner clipped wrong: {bbox}")
    notes.append("cell bbox: halo clipped to the page at the corner")

    # a 180-degree capture: the AABB of the transformed rectangle must
    # still contain the rectangle, and the pad must be applied.
    flipped = _geometry.GlobalAffine(
        rows=((-16.0, 0.0, 40000.0), (0.0, -16.0, 56000.0)),
        n_poses=9, residual_median_px=0.0, residual_p99_px=0.0,
        residual_max_px=0.0)
    px = _geometry.px_bbox_for((100, 100, 200, 200), flipped,
                               (56128, 40832))
    pad = _geometry.PX_PAD_CELLS * 16
    _require(px[0] <= 40000 - 200 * 16 - pad + 1
             and px[2] >= 40000 - 100 * 16 + pad - 1,
             f"180-degree AABB is wrong: {px}")
    notes.append("pixel bbox: 180-degree capture maps to the right AABB, "
                 f"with {_geometry.PX_PAD_CELLS} cells of pad")

    # controls: rim rule, and a target's tile position never doubles as
    # a control (not even another stream of it).
    both = frozenset({(0, 5, 5, "C"), (0, 5, 5, "Y"), (0, 9, 9, "C"),
                      (0, 0, 0, "C")})
    controls = _geometry.controls_for((0, 0, 1024, 1024), both,
                                      frozenset({(9, 9)}))
    _require((0, 9, 9, "C") not in controls,
             "a target tile position must never be a control")
    _require((0, 0, 0, "C") not in controls,
             "a tile inside the 32-cell rim must not be a control")
    _require({(0, 5, 5, "C"), (0, 5, 5, "Y")} == set(controls),
             f"control set is wrong: {controls}")
    notes.append("controls: rim rule and target exclusion hold, per stream")

    # the manifest schema refuses a drifted key.
    drifted = {"volume": "x"}
    try:
        cases.validate_manifest(drifted)
    except ValueError:
        notes.append("manifest schema: a drifted manifest is refused")
    else:
        raise SelfCheckError("manifest schema accepted a drifted manifest")
    return notes


# --------------------------------------------------------------------
# part 2 — the frame, on a synthetic case
# --------------------------------------------------------------------


def _read_side(side: str, run_dir: Path) -> dict | None:
    """What a finished decode left behind, or None."""
    paths = harness.side_paths(run_dir, side)
    if side == "holo1":
        return (harness.read_holo1(paths["state"])
                if paths["state"].is_file() else None)
    if not paths["certs"].is_file():
        return None
    rows, available = harness.read_holo3(paths["certs"])
    if not available:
        raise SelfCheckError("holo3 reported no certificate bits — the "
                             "store route is unavailable, so the frame "
                             "check cannot be made")
    return rows


def _decode(side: str, crops: list[Path], run_dir: Path, workers: int,
            timeout: float, fresh: bool = False) -> tuple[dict, float]:
    """One decode through the harness's own command builder.

    Sidecar adoption, on the harness's own predicate: a self-check
    re-run costs nothing when neither the input nor that side's
    receiver moved (the holo1 arm on this sim page is minutes).
    """
    sidecar_path = run_dir / f"{side}.selfcheck.json"
    current = harness.receiver_fingerprint(side, harness.crop_set_sha(crops))
    saved = (json.loads(sidecar_path.read_text(encoding="utf-8"))
             if sidecar_path.is_file() else None)
    ok, _reason = harness.adoption_verdict(saved, current, fresh)
    if ok:
        rows = _read_side(side, run_dir)
        if rows:
            return rows, float(saved.get("wall_seconds", 0.0))
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    argv, cwd, extra = harness.build_command(
        side, crops, [SIM_DPI] * len(crops), SIM_FORMAT, run_dir,
        workers=workers)
    environ = dict(os.environ)
    environ.update(extra)
    started = time.perf_counter()
    done = subprocess.run(argv, capture_output=True, text=True,
                          cwd=str(cwd), env=environ, timeout=timeout)
    wall = time.perf_counter() - started
    sidecar_path.write_text(
        json.dumps({**current, "wall_seconds": wall,
                    "exit": done.returncode,
                    "ran_at": time.strftime("%Y-%m-%d %H:%M:%S")},
                   indent=2) + "\n", encoding="utf-8")
    paths = harness.side_paths(run_dir, side)
    if side == "holo1":
        if not paths["state"].is_file():
            raise SelfCheckError(
                f"holo1 wrote no state for {run_dir.name} (exit "
                f"{done.returncode}): {done.stderr[-800:]}")
        return harness.read_holo1(paths["state"]), wall
    if not paths["certs"].is_file():
        raise SelfCheckError(
            f"holo3 wrote no certs sidecar for {run_dir.name} (exit "
            f"{done.returncode}): {done.stderr[-800:]}")
    rows, available = harness.read_holo3(paths["certs"])
    if not available:
        raise SelfCheckError("holo3 reported no certificate bits — the "
                             "store route is unavailable, so the frame "
                             "check cannot be made")
    return rows, wall


def check_frame(out_root: Path, *, halo_cells: int, sides: tuple[str, ...],
                workers: int, timeout: float,
                fresh: bool = False) -> list[str]:
    for path in (SIM_TIFF, SIM_PAYLOAD, SIM_STATE):
        if not path.is_file():
            raise SelfCheckError(f"self-check input absent: {path}")
    import tifffile

    notes: list[str] = []
    truth = _gt.reconstruct(SIM_FORMAT, SIM_PAYLOAD.read_bytes())
    oracle = _state.read_state(SIM_STATE)
    _gt.validate_bits(truth, oracle.certified_bits,
                      f"sim oracle state {SIM_STATE}")
    notes.append(f"ground truth validated on the sim oracle state "
                 f"({len(oracle.certified_bits)} certificates)")

    affine = _geometry.fit_global_affine(list(oracle.poses))
    cluster = _geometry.Cluster.of([SIM_TARGET])
    tiles_y, tiles_x = truth.tiles_yx
    cell_bbox = _geometry.cell_bbox_for(
        cluster, halo_cells,
        (tiles_y * _geometry.TILE_CELLS, tiles_x * _geometry.TILE_CELLS))
    with tifffile.TiffFile(str(SIM_TIFF)) as handle:
        shape = handle.pages[0].shape
    px_bbox = _geometry.px_bbox_for(cell_bbox, affine,
                                    (int(shape[0]), int(shape[1])))

    work = out_root / "_selfcheck"
    work.mkdir(parents=True, exist_ok=True)
    crop_path = work / "sim-crop.tiff"
    plane = tifffile.memmap(str(SIM_TIFF), mode="r")
    try:
        px0, py0, px1, py1 = px_bbox
        window = np.ascontiguousarray(plane[py0:py1, px0:px1])
    finally:
        del plane
    if crop_path.exists():
        crop_path.unlink()
    tifffile.imwrite(str(crop_path), window, photometric="minisblack")
    notes.append(f"synthetic case: target tile {SIM_TARGET}, cell bbox "
                 f"{cell_bbox}, crop {window.shape[0]}x{window.shape[1]} px "
                 f"({window.nbytes / 1e6:.1f} MB) out of "
                 f"{shape[0]}x{shape[1]}")

    for side in sides:
        full, wall_full = _decode(side, [SIM_TIFF], work / f"{side}-full",
                                  workers, timeout, fresh)
        crop, wall_crop = _decode(side, [crop_path], work / f"{side}-crop",
                                  workers, timeout, fresh)
        _require(bool(crop), f"{side}: the crop certified nothing — this "
                             "check proved nothing, it did not pass")
        shifted = sorted(set(crop) - set(full))
        _require(not shifted,
                 f"{side}: {len(shifted)} crop certificate(s) carry an "
                 f"address the full page never certified, e.g. "
                 f"{shifted[:3]} — the crop frame is SHIFTED")
        outside = sorted(a for a in crop
                         if not harness._in_cell_bbox(a, list(cell_bbox)))
        _require(not outside,
                 f"{side}: {len(outside)} crop certificate(s) address a "
                 f"tile outside the crop's cell rectangle, e.g. "
                 f"{outside[:3]}")
        wrong = [a for a in sorted(crop)
                 if not _gt.check_bits(truth, a, crop[a])[0]]
        _require(not wrong,
                 f"{side}: {len(wrong)} crop certificate(s) disagree with "
                 f"ground truth, e.g. {wrong[:3]}")
        target = (0, SIM_TARGET[0], SIM_TARGET[1], "main")
        notes.append(
            f"{side}: full page {len(full)} certs in {wall_full:.1f} s, "
            f"crop {len(crop)} certs in {wall_crop:.1f} s; every crop "
            f"address is a full-page address, inside the cell bbox, and "
            f"bit-exact against GT; target {SIM_TARGET} "
            f"{'certified' if target in crop else 'not certified'} on "
            f"the crop")
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-decodes", action="store_true",
                        help="pure geometry only")
    parser.add_argument("--with-holo1", action="store_true",
                        help="also run the holo1 arm — opt-in: measured "
                             "at >20 min / 7.9 GiB on this sim page")
    parser.add_argument("--refresh", action="store_true",
                        help="re-decode even where a self-check sidecar "
                             "matches (the holo1 arm is expensive)")
    parser.add_argument("--halo-cells", type=int, default=128,
                        help="halo for the synthetic crop (default 128 — "
                             "the sim page is only 448 cells wide)")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--out-root", type=Path, default=_paths.SCRATCH)
    args = parser.parse_args(argv)

    notes = check_pure()
    if not args.skip_decodes:
        sides = harness.SIDES if args.with_holo1 else ("holo3",)
        notes += check_frame(args.out_root, halo_cells=args.halo_cells,
                             sides=sides, workers=args.workers,
                             timeout=args.timeout, fresh=args.refresh)
    print("crop_parity self-check")
    for note in notes:
        print(f"  PASS  {note}")
    print(f"  {len(notes)} check(s) passed"
          + ("  (decodes skipped)" if args.skip_decodes else ""))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SelfCheckError as error:
        print(f"crop_parity self-check FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
