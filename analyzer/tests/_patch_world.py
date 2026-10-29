"""W8 B1 — the synthetic page the three `test_analyzer_patch*` modules read.

`_state_raster` paints a small page whose red channel carries the MEASURED
mechanism in miniature (MEASUREMENTS-2026-09-06-C-THIRD-LAYER §3): a C cell
whose siblings are both inked has NO dot core — a flat, wide, weak deficit —
while every other C cell is a dot; green carries M and blue carries Y.  A
0.7-cell box aperture reads the flat deficit at a fraction of its strength
and the learned filter must not.  `World` assembles lane, footprint, frame,
crops, read, mix and folds over that page; each module listed below builds
its own module-scoped instance, and nothing here touches truth.

Everything is synthetic and fast.  The modules that read it:
`test_analyzer_patch.py` (the grid, the extraction, the discriminant, the
score, the seams), `test_analyzer_patch_tiers.py` (B3's tiers, self-training
and the local5 scope) and `test_analyzer_patch_walk.py` (B7's auto walk and
B8's caches).
"""

from __future__ import annotations

from dataclasses import replace as dc_replace
from fractions import Fraction

import numpy as np

from holo.receiver.data import Placement
from holo.receiver.lib import spectral

from analyzer import calibrate as cal, patch as patch_mod, sample
from analyzer.types import KnownFrame, Lane, TileFootprint

PITCH_PX = 8.0
CELL_DOTS = 2
ORIGIN_Y, ORIGIN_X = 10.0, 12.0
PAGE_CELLS = 128
HALO = 32
TILE = 64
PAPER_RGB = (0.62, 0.90, 0.90)
NOISE_RGB = (0.08, 0.03, 0.03)


# ------------------------------------------------------- the synthetic page

def _bits(rng: np.random.Generator, shape: tuple[int, int],
          word_mask: np.ndarray) -> np.ndarray:
    """(H, W, 3) plane bits.  Y is correlated with M so that sibling
    state 3 (M+Y) is rich (~30%) and state 2 (Y only) is STARVED (~1.5%);
    a word site prints C == M == Y, the format's own skew."""
    c = rng.random(shape) < 0.5
    m = rng.random(shape) < 0.5
    y = np.where(m, rng.random(shape) < 0.6, rng.random(shape) < 0.03)
    word_bit = rng.random(shape) < 0.5
    c = np.where(word_mask, word_bit, c)
    m = np.where(word_mask, word_bit, m)
    y = np.where(word_mask, word_bit, y)
    return np.stack((c, m, y), axis=-1).astype(np.uint8)


def _flat_kernel(pitch: int) -> np.ndarray:
    """State 3: the third layer — 0.06 spread over 1.5 cells."""
    size = int(round(1.5 * pitch))
    return np.full((size, size), 0.06, np.float64)


def _dot_kernel(pitch: int) -> np.ndarray:
    """Every other state: a dot core, 0.30 over the central half cell."""
    size = int(round(0.5 * pitch))
    return np.full((size, size), 0.30, np.float64)


KERNELS = {0: _dot_kernel, 1: _dot_kernel, 2: _dot_kernel, 3: _flat_kernel}


def _paint(plane: np.ndarray, centres_yx: np.ndarray,
           kernel: np.ndarray) -> None:
    half = kernel.shape[0] // 2
    for cy, cx in centres_yx:
        y0, x0 = int(round(cy)) - half, int(round(cx)) - half
        plane[y0:y0 + kernel.shape[0], x0:x0 + kernel.shape[1]] -= kernel


def _state_raster(kernels, pitch_px: float, cells_yx_shape: tuple[int, int],
                  *, seed: int = 11, word_mask: np.ndarray | None = None,
                  affine: tuple[float, ...] | None = None,
                  ) -> tuple[tuple[np.ndarray, ...], np.ndarray]:
    """Paint one kernel per sibling state at every cell; return the bits.

    `affine` is the page-cell -> pixel affine (a, b, c, d, e, f) the
    cells are painted through — the default is axis-aligned, the pose
    test hands in a transposed one.
    """
    rng = np.random.default_rng(seed)
    shape = tuple(int(v) for v in cells_yx_shape)
    if word_mask is None:
        word_mask = np.zeros(shape, bool)
    bits = _bits(rng, shape, word_mask)
    pitch = int(round(pitch_px))
    if affine is None:
        affine = (pitch_px, 0.0, ORIGIN_Y, 0.0, pitch_px, ORIGIN_X)
    matrix = np.asarray(affine, np.float64).reshape(2, 3)
    gy, gx = np.meshgrid(np.arange(shape[0]), np.arange(shape[1]),
                         indexing="ij")
    cells = np.stack((gy.ravel(), gx.ravel()), axis=1).astype(np.float64)
    centres = (cells + 0.5) @ matrix[:, :2].T + matrix[:, 2]
    extent = int(np.ceil(centres.max())) + 4 * pitch
    planes = [np.full((extent, extent), level, np.float64)
              for level in PAPER_RGB]
    flat_bits = bits.reshape(-1, 3)
    state = flat_bits[:, 1].astype(int) + 2 * flat_bits[:, 2].astype(int)
    for index in range(4):
        pick = (flat_bits[:, 0] == 1) & (state == index)
        _paint(planes[0], centres[pick], kernels[index](pitch))
    _paint(planes[1], centres[flat_bits[:, 1] == 1], _dot_kernel(pitch))
    _paint(planes[2], centres[flat_bits[:, 2] == 1], _dot_kernel(pitch))
    rasters = []
    for channel, plane in enumerate(planes):
        plane = plane + rng.normal(0.0, NOISE_RGB[channel], plane.shape)
        rasters.append(np.clip(np.round(plane * 255.0), 0, 255)
                       .astype(np.uint8))
    return tuple(rasters), bits


def _placement(shape: tuple[int, int],
               affine: tuple[float, ...] | None = None) -> Placement:
    height, width = shape
    cy, cx = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")
    local = np.stack((cy.ravel(), cx.ravel()), axis=1).astype(np.int64)
    if affine is None:
        affine = (PITCH_PX, 0.0, ORIGIN_Y, 0.0, PITCH_PX, ORIGIN_X)
    return Placement(
        window_id=("cap0", 0, 0, (0, 0, height, width)), capture_id="cap0",
        level_index=0, region_index=0, patch_ordinal=0, page=0, rot_k=0,
        page_origin_yx=(0, 0), native_affine=tuple(float(v) for v in affine),
        pitch_px=PITCH_PX, route="place", local_cells_yx=local, quality=0.1)


def _lane(rasters, placement: Placement) -> Lane:
    return Lane(capture_id="cap0", ordinal=0, level_index=0, dpi=1200.0,
                ppc=Fraction(8), frame=Fraction(1),
                pitch_px_native=PITCH_PX, pitch_px_level=PITCH_PX,
                rasters=rasters, placements=(placement,))


def _footprint(y_range: tuple[int, int], x_range: tuple[int, int],
               page_shape: tuple[int, int], *, cargo: np.ndarray | None = None,
               ) -> TileFootprint:
    ys = np.arange(*y_range, dtype=np.int64)
    xs = np.arange(*x_range, dtype=np.int64)
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    cells = np.stack((gy.ravel(), gx.ravel()), axis=1)
    in_tile = (cells[:, 0] < TILE) & (cells[:, 1] < TILE)
    return TileFootprint(page=0, ty=0, tx=0, halo_cells=HALO,
                         page_cells_yx=cells, in_tile=in_tile,
                         cargo=(np.ones(cells.shape[0], bool)
                                if cargo is None else cargo),
                         page_shape_cells_yx=page_shape)


class World:
    """Lane, footprint, frame, crops, read, mix and folds — one object."""

    def __init__(self, *, seed: int = 11, bound_dots: float = 2.5,
                 keep_raw: bool = True):
        shape = (PAGE_CELLS, PAGE_CELLS)
        gy, gx = np.meshgrid(np.arange(PAGE_CELLS), np.arange(PAGE_CELLS),
                             indexing="ij")
        # ~100 word sites inside the target tile, ~12 dust cells
        word = (gy < TILE) & (gx < TILE) & ((gy * 7 + gx * 3) % 41 == 0)
        dust = (gy < TILE) & (gx < TILE) & ((gy * 5 + gx * 11) % 331 == 0)
        rasters, page_bits = _state_raster(KERNELS, PITCH_PX, shape,
                                           seed=seed, word_mask=word)
        self.page_bits = page_bits
        self.lane = _lane(rasters, _placement(shape))
        cells_y = (0, TILE + HALO)
        self.fp = _footprint(cells_y, cells_y, shape)
        cells = self.fp.page_cells_yx
        self.cells = cells
        n = cells.shape[0]
        bits = page_bits[cells[:, 0], cells[:, 1]].copy()
        in_tile = np.asarray(self.fp.in_tile, bool)
        word_rows = word[cells[:, 0], cells[:, 1]]
        dust_rows = dust[cells[:, 0], cells[:, 1]]
        kind = np.full(n, -1, np.int8)
        kind[word_rows] = 0
        kind[dust_rows] = 1
        furniture = kind >= 0
        known = np.ones((n, 3), bool)
        known[in_tile & ~furniture, 0] = False       # the target's cargo
        self.fp = dc_replace(self.fp, cargo=~furniture)
        self.frame = KnownFrame(
            bits=bits, known=known, furniture=furniture, metadata_cell=None,
            regressors=known.all(axis=1), labels=known[:, 0].copy(),
            siblings=known[:, 1] & known[:, 2], n_discriminating=0,
            furniture_kind=kind, target=(0, 0, 0, "C"), detail={})
        self.folds = cal.split_folds(cells, 20260906)
        self.lfp = sample.lane_footprint(self.lane, self.fp)
        assert self.lfp is not None and self.lfp.observed.all()
        self.crops = sample.open_crops(self.lane, self.lfp,
                                       bound_dots=bound_dots,
                                       cell_dots=CELL_DOTS, keep_raw=keep_raw)
        self.read = sample.read_rgb(self.crops, self.lfp)
        assert self.read.refusal is None
        self.mix = spectral.fit_plane_mix(self.read.values_rgb, bits, known)
        assert self.mix.accepted, self.mix.reason
        self.spec = patch_mod.PatchSpec()

    def score(self, spec=None, frame=None, **kwargs):
        return patch_mod.patch_score(
            self.spec if spec is None else spec, 0,
            self.frame if frame is None else frame, self.mix, self.crops,
            self.read, self.lfp, self.folds, **kwargs)

    def box_score(self) -> np.ndarray:
        return np.asarray(spectral.plane_score(
            self.mix, self.read.values_rgb, self.frame.bits,
            self.frame.known, 0, spectral.MODE_SUBTRACT), np.float64)

    def heldout(self, state: int) -> np.ndarray:
        """Ring rows of one sibling state with a TRUE C label, held out."""
        states = (self.frame.bits[:, 1].astype(int)
                  + 2 * self.frame.bits[:, 2].astype(int))
        return np.flatnonzero((states == state) & ~self.fp.in_tile
                              & ~self.folds.fit)


def d_prime(score: np.ndarray, target: np.ndarray) -> float:
    one, zero = score[target], score[~target]
    spread = np.sqrt(0.5 * (one.var() + zero.var()))
    return float((one.mean() - zero.mean()) / max(spread, 1e-12))


def _unknown_y(world: World) -> KnownFrame:
    """The open-Y tile in miniature: no cell of the tile proves Y.

    That is the live/marginal C row of MEAS §5b (`cargo_cleanable_fraction
    0.0` on 27 of 33): the target's siblings are not both certified, the
    sibling state is -1 there, and no per-state filter can reach it.
    """
    known = np.asarray(world.frame.known, bool).copy()
    known[np.asarray(world.fp.in_tile, bool), 2] = False
    return dc_replace(world.frame, known=known,
                      siblings=known[:, 1] & known[:, 2])


def _walk(value, path="detail"):
    if isinstance(value, np.ndarray):
        raise AssertionError(f"{path} is an ndarray")
    if isinstance(value, dict):
        for name, item in value.items():
            _walk(item, f"{path}.{name}")
    elif isinstance(value, (list, tuple)):
        assert len(value) <= 8, f"{path} has {len(value)} entries"
        for index, item in enumerate(value):
            _walk(item, f"{path}[{index}]")


#: B7's walk, with the three knobs of HALO-CHANNEL-2026-09-07 NAMED at
#: the values that reproduce it.  Two of them ship ON since §5's
#: isolation, and the pins over this bag are B7's, in
#: `test_analyzer_patch_walk.py` — the coordinate pass, the window axis,
#: the tie-break to the inherited value.  The shipped behaviour has its
#: own file (`test_analyzer_walkeval.py`), including what the richer
#: tie-break costs on this very stimulus.
AUTO_KNOBS = {
    "patch_samples_per_cell": "auto", "patch_window_cells": "auto",
    "patch_channels": "auto", "patch_features": "auto",
    "patch_shrinkage": "auto", "patch_min_labels_per_state": "auto",
    "patch_min_labels_agnostic": "auto", "aperture_cells": "auto",
    "walk_weighting": "none", "walk_franchise": "inherit",
    "walk_direction": "adopt-if-better"}


def _auto_spec(**overrides) -> patch_mod.PatchSpec:
    return patch_mod.spec_from_knobs({**AUTO_KNOBS, **overrides})
