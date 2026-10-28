"""Shared synthetic fixtures for the holo2 carry-equivalence oracles.

These tests live OUTSIDE ``holo2/`` precisely so they may import both
packages (holo2/README.md: "equivalence where intended is pinned by
comparison tests outside this tree"). Nothing here is production code
and nothing here may be imported by ``holo2/src``.

NOT a ``conftest.py``: ``holo2/tests/conftest.py`` already claims that
top-level module name (both directories are import-rooted, neither is a
package), so a second one shadows it and breaks the H1 suite's
``from conftest import …``.  Test modules import the fixtures they need
by name instead — the ``tests/holo/_*_fixtures.py`` pattern.

Fixtures are seeded numpy — deterministic, and small enough (<=1200 px)
that a whole-platen survey of one is milliseconds, not seconds.
"""
from __future__ import annotations

import numpy as np
import pytest

# The synthetic "print": a random binary cell field on paper white, at a
# stated cell pitch in scan pixels.  Nothing about it is a channel claim;
# it exists to give the survey's structure tensor and pitch comb real,
# reproducible structure to find.
PAPER = 235
INK = 30


def cell_field(
    rows: int, cols: int, cell_px: int, seed: int, *, ink_fraction: float = 0.5
) -> np.ndarray:
    """A ``rows x cols``-cell binary field expanded to whole pixels."""
    rng = np.random.default_rng(seed)
    cells = rng.random((rows, cols)) < ink_fraction
    dense = np.kron(cells, np.ones((cell_px, cell_px), bool))
    return np.where(dense, INK, PAPER).astype(np.uint8)


def synthetic_page(
    shape_px: tuple[int, int] = (1024, 1024),
    *,
    cell_px: int = 4,
    seed: int = 20260809,
    patches: tuple[tuple[int, int, int, int], ...] = (
        (140, 620, 120, 600),
        (700, 940, 620, 900),
    ),
    noise: float = 3.0,
) -> np.ndarray:
    """A grey page: paper white, mild noise, and two printed scraps."""
    rng = np.random.default_rng(seed)
    page = np.full(shape_px, PAPER, np.float64)
    for index, (r0, r1, c0, c1) in enumerate(patches):
        field = cell_field(
            (r1 - r0) // cell_px, (c1 - c0) // cell_px, cell_px, seed + index
        )
        page[r0:r0 + field.shape[0], c0:c0 + field.shape[1]] = field
    page += rng.normal(0.0, noise, page.shape)
    return np.clip(page, 0, 255).astype(np.uint8)


def as_rgb(grey: np.ndarray, seed: int = 7) -> np.ndarray:
    """An RGB capture whose per-channel offsets make the luma mean matter."""
    rng = np.random.default_rng(seed)
    planes = [
        np.clip(
            grey.astype(np.int16) + offset
            + rng.integers(-2, 3, grey.shape, dtype=np.int16),
            0, 255,
        ).astype(np.uint8)
        for offset in (-6, 0, 9)
    ]
    return np.stack(planes, axis=2)


@pytest.fixture(scope="session")
def grey_page() -> np.ndarray:
    return synthetic_page()


@pytest.fixture(scope="session")
def rgb_page(grey_page: np.ndarray) -> np.ndarray:
    return as_rgb(grey_page)


@pytest.fixture(scope="session")
def small_grey() -> np.ndarray:
    """A 600 px page with one scrap (the cheap multi-case fixture)."""
    return synthetic_page(
        (600, 600), seed=4242, patches=((90, 500, 110, 520),)
    )


@pytest.fixture(scope="session")
def small_rgb(small_grey: np.ndarray) -> np.ndarray:
    return as_rgb(small_grey, seed=11)


@pytest.fixture(autouse=True)
def holo_sequential():
    """Pin holo's intra-stage pool to the sequential path for comparison.

    holo2 has no pool until H3, so the claim under test is equivalence to
    holo's ``--workers 1`` path.  holo's own
    ``tests/holo/test_parallel_exactness.py`` owns the separate claim that
    its pooled path is bit-identical to that one.
    """
    from holo.receive import _parallel

    _parallel.set_worker_count(1)
    try:
        yield
    finally:
        _parallel.set_worker_count(None)
