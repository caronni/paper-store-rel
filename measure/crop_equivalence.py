from __future__ import annotations

import sys
import time
from collections import Counter

import numpy as np

from holo.receiver.plugins import calibrate as cal

RNG = np.random.default_rng(20260829)

FAILURES: list[str] = []
COUNTS: Counter[str] = Counter()
CASES: Counter[str] = Counter()


def branch_label(points: np.ndarray, raster_shape: tuple[int, int],
                 pitch_px: float) -> str:
    pts = np.asarray(points, np.float64)
    y0, x0, y1, x1 = cal._crop_bounds(pts, raster_shape, pitch_px)
    size = cal._aperture_px(pitch_px)
    local = pts - np.asarray((y0, x0), np.float64)
    rows = cal._lattice_indices(local[:, 0], y1 - y0)
    cols = cal._lattice_indices(local[:, 1], x1 - x0)
    sparse = (rows.size * size * ((x1 - x0) + cols.size)
              < 2 * (y1 - y0) * (x1 - x0))
    return "sparse" if sparse else "dense"


def compare(tag: str, planes: list[np.ndarray], points: np.ndarray,
            raster_shape: tuple[int, int], pitch_px: float) -> None:
    want = cal.sample_points(
        cal.window_crop(planes, points, raster_shape, pitch_px), points)
    got = cal.sampled_window_means(planes, points, raster_shape, pitch_px)
    COUNTS[f"branch:{branch_label(points, raster_shape, pitch_px)}"] += 1
    COUNTS[f"planes:{len(planes)}"] += 1
    CASES[tag] += 1
    same = (got.shape == want.shape and got.dtype == want.dtype
            and got.tobytes() == want.tobytes())
    if not same:
        COUNTS["MISMATCH"] += 1
        if len(FAILURES) < 12:
            bad = np.flatnonzero(got.ravel() != want.ravel())
            FAILURES.append(
                f"{tag} n={points.shape[0]} pitch={pitch_px} "
                f"raster={raster_shape} planes={len(planes)} "
                f"n_bad={bad.size}\n"
                f"  first_bad={bad[:6]!r}\n"
                f"  want={want.ravel()[bad[:6]]!r}\n"
                f"  got={got.ravel()[bad[:6]]!r}")


def make_planes(shape_yx: tuple[int, int], rgb: bool) -> list[np.ndarray]:
    if rgb:
        return [RNG.integers(0, 256, size=shape_yx, dtype=np.uint8)
                for _ in range(3)]
    return [RNG.integers(0, 256, size=shape_yx, dtype=np.uint8)]


def affine_points(pitch_px: float, angle_deg: float, shear: float,
                  cells_yx: tuple[int, int],
                  origin: tuple[float, float]) -> np.ndarray:
    theta = np.deg2rad(angle_deg)
    matrix = pitch_px * np.asarray(
        ((np.cos(theta), -np.sin(theta) + shear),
         (np.sin(theta), np.cos(theta))), np.float64)
    ny, nx = cells_yx
    cells = np.stack(np.meshgrid(np.arange(ny, dtype=np.float64),
                                 np.arange(nx, dtype=np.float64),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    return (cells + 0.5) @ matrix.T + np.asarray(origin, np.float64)


def clip_inside(points: np.ndarray,
                raster_shape: tuple[int, int]) -> np.ndarray:
    out = np.array(points, np.float64, copy=True)
    out[:, 0] = np.clip(out[:, 0], 0.0, raster_shape[0] - 1)
    out[:, 1] = np.clip(out[:, 1], 0.0, raster_shape[1] - 1)
    return out


def population_affine_grid(trials: int) -> None:
    for trial in range(trials):
        pitch = float(RNG.uniform(2.0, 12.0))
        side = int(RNG.integers(4, 25))
        angle = float(RNG.uniform(-2.0, 2.0))
        shear = float(RNG.uniform(-0.02, 0.02))
        extent = int(side * pitch + 60)
        shape = (extent + int(RNG.integers(0, 40)),
                 extent + int(RNG.integers(0, 40)))
        origin = (float(RNG.uniform(20.0, 40.0)),
                  float(RNG.uniform(20.0, 40.0)))
        points = clip_inside(
            affine_points(pitch, angle, shear, (side, side), origin), shape)
        compare("affine_grid", make_planes(shape, trial % 3 == 0), points,
                shape, pitch)


def population_integer_lattice(trials: int) -> None:
    for trial in range(trials):
        pitch = float(RNG.integers(2, 11))
        side = int(RNG.integers(3, 17))
        shift = (0.0, 0.5, 0.25)[trial % 3]
        origin = (float(RNG.integers(10, 30)) + shift,
                  float(RNG.integers(10, 30)) + shift)
        extent = int(side * pitch + 70)
        shape = (extent, extent)
        points = clip_inside(
            affine_points(pitch, 0.0, 0.0, (side, side), origin), shape)
        compare("integer_lattice", make_planes(shape, trial % 4 == 0), points,
                shape, pitch)


def population_edge_points(trials: int) -> None:
    for trial in range(trials):
        shape = (int(RNG.integers(40, 160)), int(RNG.integers(40, 160)))
        n = int(RNG.integers(1, 120))
        points = np.stack((RNG.uniform(0.0, shape[0] - 1, size=n),
                           RNG.uniform(0.0, shape[1] - 1, size=n)), axis=1)
        pin = RNG.integers(0, 4)
        if pin == 0:
            points[0] = (0.0, 0.0)
        elif pin == 1:
            points[0] = (float(shape[0] - 1), float(shape[1] - 1))
        elif pin == 2:
            points[0] = (float(shape[0] - 1), 0.0)
        whole = RNG.random(n) < 0.3
        points[whole] = np.floor(points[whole])
        pitch = float(RNG.uniform(2.0, 9.0))
        compare("edge_points", make_planes(shape, trial % 3 == 0), points,
                shape, pitch)


def population_aperture_sweep(trials: int) -> None:
    for trial in range(trials):
        aperture = int(RNG.integers(1, 21))
        pitch = aperture / cal.APERTURE_CELLS + float(RNG.uniform(-0.4, 0.4))
        pitch = max(1.5, pitch)
        side = int(RNG.integers(3, 9))
        extent = int(side * pitch + 3 * aperture + 40)
        shape = (extent, extent)
        origin = (float(RNG.uniform(15.0, 25.0)),
                  float(RNG.uniform(15.0, 25.0)))
        points = clip_inside(
            affine_points(pitch, float(RNG.uniform(-1.0, 1.0)), 0.0,
                          (side, side), origin), shape)
        compare("aperture_sweep", make_planes(shape, trial % 2 == 0), points,
                shape, pitch)


def population_degenerate(trials: int) -> None:
    for trial in range(trials):
        kind = trial % 4
        pitch = float(RNG.uniform(2.0, 10.0))
        if kind == 3:
            shape = (int(RNG.integers(3, 14)), int(RNG.integers(3, 14)))
        else:
            shape = (int(RNG.integers(40, 90)), int(RNG.integers(40, 90)))
        if kind == 0:
            n = 1
        elif kind == 1:
            n = 2
        else:
            n = int(RNG.integers(3, 20))
        points = np.stack((RNG.uniform(0.0, shape[0] - 1, size=n),
                           RNG.uniform(0.0, shape[1] - 1, size=n)), axis=1)
        if kind == 2:
            points[:, 0] = points[0, 0]
        compare("degenerate", make_planes(shape, trial % 3 == 0), points,
                shape, pitch)


def population_value_families(trials: int) -> None:
    for trial in range(trials):
        shape = (int(RNG.integers(50, 120)), int(RNG.integers(50, 120)))
        family = trial % 5
        if family == 0:
            image = np.zeros(shape, np.uint8)
        elif family == 1:
            image = np.full(shape, 255, np.uint8)
        elif family == 2:
            step = int(RNG.integers(2, 9))
            yy, xx = np.meshgrid(np.arange(shape[0]) // step,
                                 np.arange(shape[1]) // step, indexing="ij")
            image = np.where((yy + xx) % 2 == 0, 0, 255).astype(np.uint8)
        elif family == 3:
            step = int(RNG.integers(2, 9))
            image = np.where((np.arange(shape[1]) // step) % 2 == 0, 30, 220
                             ).astype(np.uint8) * np.ones(
                                 (shape[0], 1), np.uint8)
        else:
            image = RNG.integers(0, 3, size=shape).astype(np.uint8) * 127
        planes = ([image] if trial % 3 else
                  [image, np.flipud(image).copy(), np.fliplr(image).copy()])
        n = int(RNG.integers(4, 80))
        points = np.stack((RNG.uniform(0.0, shape[0] - 1, size=n),
                           RNG.uniform(0.0, shape[1] - 1, size=n)), axis=1)
        pitch = float(RNG.uniform(2.0, 10.0))
        compare("value_families", planes, points, shape, pitch)


def population_dense_guard(trials: int) -> None:
    for trial in range(trials):
        pitch = float(RNG.uniform(2.0, 2.6))
        side = int(RNG.integers(8, 40))
        extent = int(side * pitch + 30)
        shape = (extent, extent)
        origin = (12.0 + float(RNG.uniform(0.0, 2.0)),
                  12.0 + float(RNG.uniform(0.0, 2.0)))
        points = clip_inside(
            affine_points(pitch, float(RNG.uniform(-0.5, 0.5)), 0.0,
                          (side, side), origin), shape)
        compare("dense_guard", make_planes(shape, trial % 3 == 0), points,
                shape, pitch)


def population_large_realistic(trials: int) -> None:
    for trial in range(trials):
        pitch = (5.0, 8.0)[trial % 2]
        side = 200
        extent = int(side * pitch + 80)
        shape = (extent, extent)
        origin = (37.25, 23.75)
        points = clip_inside(
            affine_points(pitch, 0.3, 0.005, (side, side), origin), shape)
        compare("large_realistic", make_planes(shape, trial % 3 == 0), points,
                shape, pitch)


PLAN = (
    ("affine_grid", population_affine_grid, 2400),
    ("integer_lattice", population_integer_lattice, 2400),
    ("edge_points", population_edge_points, 2400),
    ("aperture_sweep", population_aperture_sweep, 1600),
    ("degenerate", population_degenerate, 3000),
    ("value_families", population_value_families, 1500),
    ("dense_guard", population_dense_guard, 600),
    ("large_realistic", population_large_realistic, 6),
)

if __name__ == "__main__":
    scale = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    started = time.perf_counter()
    for name, fn, trials in PLAN:
        t0 = time.perf_counter()
        fn(max(1, int(trials * scale)))
        print(f"  {name:<18} {CASES[name]:>7} cases  "
              f"{time.perf_counter() - t0:>7.1f}s")
    total = sum(CASES.values())
    print(f"\ntotal cases {total}  elapsed {time.perf_counter() - started:.1f}s")
    print("coverage:")
    for key in sorted(COUNTS):
        if key != "MISMATCH":
            print(f"  {key:<16} {COUNTS[key]}")
    if FAILURES:
        print(f"\nMISMATCHES {COUNTS['MISMATCH']}")
        for item in FAILURES:
            print(item)
        raise SystemExit(1)
    print(f"\nEQUIVALENCE GREEN: {total} cases, 0 mismatches "
          f"(bitwise, sampled_window_means vs window_crop+sample_points)")
