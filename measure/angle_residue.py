#!/usr/bin/env python
"""Platen-angle placement residue: holo2 vs holo3, on identical material.

Read-only on the repo tree.  Cuts one crop from a real K capture, makes
N copies that differ ONLY in synthetic platen rotation, and hands the
SAME tiff to both receivers.

    PYTHONPATH=. env/bin/python -m measure.angle_residue cut
    PYTHONPATH=. env/bin/python -m measure.angle_residue run --angle 0.00 --side holo3
    PYTHONPATH=. env/bin/python -m measure.angle_residue census

THE MATERIAL.  ``scratch/e028/hp-canon-c2-ink-counting.tiff`` is the
e029 HP K sheet, Canon 4800 dpi grey, format ``L:c2-r0700@3392x2368``,
16 px/cell.  Its own platen angle is 0.061 deg (from the crop-parity
record's fitted cell->px affine), i.e. the straight end of the
sheet-H angle ladder.  There is no ANGLED K capture on this machine,
so the angle is synthesised.

FAIRNESS.  Every arm — the 0.00 deg control included — goes through the
same order-3 spline ``affine_transform`` with the same half-pixel
sampling offset, so interpolation blur is a constant across arms and
the rotation angle is the only variable.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scratch" / "angle-residue"
CASES = ROOT / "measure" / "crop_parity" / "cases" / "e029" / "cases.json"

#: The cell box the crop covers, (cy0, cx0, cy1, cx1) in page cells.
CELL_BOX = (1200, 700, 2200, 1700)
#: Spare pixels read around the crop so a rotation never samples outside.
PAD_PX = 420
FORMAT_REF = "L:c2-r0700@3392x2368"
DPI = 4800.0
ANGLES = (0.00, 0.40, 0.80)


def _capture() -> dict:
    return json.loads(CASES.read_text())["captures"][0]


def _px_box(affine: list[list[float]]) -> tuple[int, int, int, int]:
    """The pixel bbox (y0, x0, y1, x1) of :data:`CELL_BOX`."""
    (a, b, c), (d, e, f) = affine
    cy0, cx0, cy1, cx1 = CELL_BOX
    xs, ys = [], []
    for cy in (cy0, cy1):
        for cx in (cx0, cx1):
            xs.append(a * cx + b * cy + c)
            ys.append(d * cx + e * cy + f)
    return (int(math.floor(min(ys))), int(math.floor(min(xs))),
            int(math.ceil(max(ys))), int(math.ceil(max(xs))))


def cut(angles: tuple[float, ...]) -> None:
    import tifffile
    from scipy import ndimage

    capture = _capture()
    y0, x0, y1, x1 = _px_box(capture["affine_cell_to_px"])
    src = tifffile.memmap(capture["path"], mode="r")
    sy0, sx0 = max(0, y0 - PAD_PX), max(0, x0 - PAD_PX)
    sy1 = min(src.shape[0], y1 + PAD_PX)
    sx1 = min(src.shape[1], x1 + PAD_PX)
    print(f"source {capture['path']} shape {src.shape}")
    print(f"cells {CELL_BOX} -> px y[{y0}:{y1}] x[{x0}:{x1}] "
          f"({y1 - y0}x{x1 - x0}); padded read y[{sy0}:{sy1}] x[{sx0}:{sx1}]")
    block = np.asarray(src[sy0:sy1, sx0:sx1], np.float32)
    del src
    out_shape = (y1 - y0, x1 - x0)
    # Where the output's own (0,0) sits inside the padded block.
    off_y, off_x = float(y0 - sy0), float(x0 - sx0)
    centre_out = np.array([(out_shape[0] - 1) / 2.0,
                           (out_shape[1] - 1) / 2.0])
    centre_in = centre_out + np.array([off_y, off_x])
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"source": capture["path"], "cell_box": list(CELL_BOX),
                "px_box": [y0, x0, y1, x1], "format": FORMAT_REF,
                "dpi": DPI, "native_angle_deg": math.degrees(math.atan2(
                    capture["affine_cell_to_px"][1][0],
                    capture["affine_cell_to_px"][0][0])),
                "arms": []}
    for angle in angles:
        theta = math.radians(angle)
        matrix = np.array([[math.cos(theta), -math.sin(theta)],
                           [math.sin(theta), math.cos(theta)]])
        # THE HALF-PIXEL OFFSET is common to every arm, control included:
        # it forces the same spline interpolation everywhere so blur is a
        # constant and the angle is the only variable.
        offset = centre_in + 0.5 - matrix @ centre_out
        warped = ndimage.affine_transform(
            block, matrix, offset=offset, output_shape=out_shape,
            order=3, mode="nearest", prefilter=True, output=np.float32)
        image = np.clip(np.rint(warped), 0, 255).astype(np.uint8)
        path = OUT / f"crop-a{angle:.2f}.tiff"
        tifffile.imwrite(str(path), image, photometric="minisblack")
        manifest["arms"].append(
            {"angle_deg": angle, "path": str(path),
             "shape_yx": list(image.shape), "mean": float(image.mean())})
        print(f"  wrote {path.name} angle {angle:+.2f} deg "
              f"mean {image.mean():.2f}")
        del warped, image
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def run(angle: float, side: str, workers: int, timeout: float) -> int:
    manifest = json.loads((OUT / "manifest.json").read_text())
    arm = next(a for a in manifest["arms"]
               if abs(a["angle_deg"] - angle) < 1e-9)
    crop = Path(arm["path"])
    run_dir = OUT / f"{side}-a{angle:.2f}"
    if run_dir.exists():
        import shutil
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    if side == "holo3":
        argv = [sys.executable, "-m", "holo3", "decode", str(crop),
                "--dpi", str(DPI), "--format", FORMAT_REF,
                "--out", str(run_dir / "payload.bin"), "--no-close",
                "--workers", str(workers), "--run-dir", str(run_dir)]
        env = dict(os.environ, PYTHONPATH=str(ROOT))
    else:
        argv = [sys.executable, "-m", "measure.angle_residue_h2",
                "--census-out", str(run_dir / "census.json"), "--",
                "--scan", str(crop), "--dpi", str(DPI),
                "--format", FORMAT_REF,
                "--state-dir", str(run_dir / "state"),
                "--output", str(run_dir / "payload.bin"), "--no-close",
                "--workers", str(workers), "--diag-port", "8061"]
        env = dict(os.environ,
                   PYTHONPATH=f"{ROOT / 'holo2' / 'src'}:{ROOT}")
    started = time.perf_counter()
    done = subprocess.run(argv, capture_output=True, text=True,
                          cwd=str(ROOT), env=env, timeout=timeout)
    wall = time.perf_counter() - started
    if side == "holo3":
        # ``cli.run_dir_for`` appends ``.<pid>`` to the base it is given,
        # so the products land beside the directory this function made.
        for extra in sorted(run_dir.parent.glob(f"{run_dir.name}.*")):
            if not extra.is_dir():
                continue
            for item in extra.iterdir():
                item.replace(run_dir / item.name)
            extra.rmdir()
    (run_dir / "stdout.txt").write_text(done.stdout)
    (run_dir / "stderr.txt").write_text(done.stderr)
    (run_dir / "sidecar.json").write_text(json.dumps(
        {"argv": argv, "returncode": done.returncode, "wall_seconds": wall,
         "angle_deg": angle, "side": side, "crop": str(crop)}, indent=2))
    print(f"{side} a{angle:+.2f}: rc={done.returncode} "
          f"wall={wall:.1f}s -> {run_dir}")
    return done.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cutp = sub.add_parser("cut")
    cutp.add_argument("--angles", type=float, nargs="+", default=list(ANGLES))
    runp = sub.add_parser("run")
    runp.add_argument("--angle", type=float, required=True)
    runp.add_argument("--side", choices=("holo2", "holo3"), required=True)
    runp.add_argument("--workers", type=int, default=1)
    runp.add_argument("--timeout", type=float, default=7200.0)
    args = parser.parse_args(argv)
    if args.command == "cut":
        cut(tuple(args.angles))
        return 0
    return run(args.angle, args.side, args.workers, args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
