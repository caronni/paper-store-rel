#!/usr/bin/env python
"""Is the coarse-lane rotation sign recoverable?  Both receivers, probed.

    PYTHONPATH=src:. env/bin/python -m measure.angle_residue_nyquist

Synthesises a printed cell lattice at a given pixels-per-cell, rotates it
by +/-theta, and asks holo3's ``lattice_reciprocal`` what rotation it
sees.  Until 2026-09-05 the same probe ran holo2's fit beside it (both
trees ran the same rfft2 fit, so the mirror below was inherited, not a
holo3 defect); that column went with holo2.

WHAT IT IS TESTING.  At 2 px/cell the cell fundamental sits on the
Nyquist bin, and ``np.fft.rfft2``'s last column is Hermitian-symmetric:
|X[+ky, N/2]| == |X[-ky, N/2]|.  A magnitude argmax there cannot tell
+theta from -theta.  Both trees run the same rfft2 fit, so if the mirror
is real it is inherited from the shared rfft2 fit, not a holo3 defect.
"""
from __future__ import annotations

import argparse

import numpy as np
from scipy import ndimage


def lattice(ppc: float, cells: int, theta_deg: float, seed: int,
            duty: float = 0.5) -> np.ndarray:
    """A rotated binary cell lattice, rendered at 8x then area-decimated."""
    over = 8
    n = int(round(cells * ppc * over))
    rng = np.random.default_rng(seed)
    # Random per-cell ink, so the lattice is a real modulated grid rather
    # than a pure grating: the fundamental is there either way.
    grid = (rng.random((cells + 8, cells + 8)) < duty).astype(np.float32)
    step = ppc * over
    ys = (np.arange(n) / step).astype(np.int64)
    xs = (np.arange(n) / step).astype(np.int64)
    image = grid[np.ix_(ys % grid.shape[0], xs % grid.shape[1])]
    if theta_deg:
        image = ndimage.rotate(image, theta_deg, reshape=False, order=1,
                               mode="nearest")
    # Area decimation back to native ppc.
    trimmed = image[: (n // over) * over, : (n // over) * over]
    small = trimmed.reshape(n // over, over, n // over, over).mean((1, 3))
    return np.asarray(small, np.float32)


def angle_of(rows: np.ndarray | None) -> float | None:
    if rows is None:
        return None
    jacobian = np.linalg.inv(np.asarray(rows, np.float64))
    horizontal = jacobian[:, 1]
    return float(np.degrees(np.arctan2(horizontal[0], horizontal[1])))


def probe(ppc: float, cells: int, thetas: tuple[float, ...],
          trials: int) -> None:
    from holo.receiver.plugins import pose as h3pose

    print(f"\nppc={ppc}  window={cells} cells "
          f"({int(cells * ppc)} px)  trials={trials}")
    print(f"{'theta':>7} | {'holo3 fitted':>28}")
    print("-" * 40)
    for theta in thetas:
        h3 = []
        for trial in range(trials):
            image = lattice(ppc, cells, theta, seed=1000 + trial)
            a3 = angle_of(h3pose.lattice_reciprocal(image, ppc))
            if a3 is not None:
                h3.append(a3)

        def summary(values: list[float]) -> str:
            if not values:
                return "no fit"
            arr = np.asarray(values)
            # ``ndimage.rotate(+theta)`` turns the array one way and the
            # fit reports the other, so the CORRECT fitted sign is the
            # opposite of the requested one.  Verified at ppc 4 and 8,
            # where it holds for every trial.
            right = int((np.sign(arr) == -np.sign(theta)).sum()) if theta \
                else len(arr)
            return (f"med {np.median(arr):+7.3f}  sign-ok "
                    f"{right}/{len(arr)}")

        print(f"{theta:+7.2f} | {summary(h3):>28}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cells", type=int, default=200)
    parser.add_argument("--trials", type=int, default=8)
    args = parser.parse_args(argv)
    thetas = (-0.80, -0.40, 0.00, 0.40, 0.80)
    for ppc in (2.0, 4.0, 8.0):
        probe(ppc, args.cells, thetas, args.trials)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
