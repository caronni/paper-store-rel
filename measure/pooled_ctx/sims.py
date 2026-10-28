"""The complementary colour capture pair the pooled-context arm is for.

Both captures are derived from the frozen colour sim render, so the
printed page is the SAME page and every label is the same format truth.
They differ only in what a scanner could see:

* capture A keeps the whole page EXCEPT a band of tile columns, which is
  wiped to the render's own paper level — A can never certify a tile in
  that band;
* capture B keeps only that band, blurred and noised — B is the only
  witness of those tiles, and its own labelled population is one band
  wide.

That is the shape the arm exists for: the tiles only the weak capture
sees, with a strong capture on the same page to pool its labels with.
Every draw is seeded; the artefacts are re-derivable from the frozen
colour sim alone.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

TILE_CELLS = 64
SEED_A = 20260830
SEED_B = 20260831
NOISE_A_SD = 3.0
DEFAULT_NOISE_B_SD = 10.0
DEFAULT_BLUR_B_PX = 1.4
DEFAULT_BAND_TILES = 3
PAPER_BORDER_PX = 16


@dataclass(frozen=True)
class PairSpec:
    """B's degradation is a LADDER down the page, not one level.

    A single blur level is all-or-nothing on this sim — measured, blur
    3.0 px certifies the whole band and 3.2 px certifies none of it,
    because what fails first is placement, not readout.  Ramping the
    blur and the noise across B's tile rows puts the cliff INSIDE one
    capture, which is what a marginal-tile experiment needs.
    """
    band_tiles: int = DEFAULT_BAND_TILES
    band_rows: int | None = None
    blur_a_px: float = 0.0
    noise_b_sd: float = DEFAULT_NOISE_B_SD
    blur_b_px: float = DEFAULT_BLUR_B_PX
    contrast_b: float = 1.0
    noise_b_sd_top: float | None = None
    blur_b_px_top: float | None = None
    contrast_b_top: float | None = None
    tile_rows: int = 10

    @property
    def ramped(self) -> bool:
        return (self.noise_b_sd_top is not None
                or self.blur_b_px_top is not None
                or self.contrast_b_top is not None)

    @property
    def token(self) -> str:
        rows = "" if self.band_rows is None else f"x{self.band_rows}"
        rows += "" if self.blur_a_px == 0.0 else f"-a{self.blur_a_px:g}"
        if not self.ramped:
            return (f"band{self.band_tiles}{rows}"
                    f"-noise{self.noise_b_sd:g}"
                    f"-blur{self.blur_b_px:g}"
                    f"-contrast{self.contrast_b:g}")
        return (f"band{self.band_tiles}{rows}"
                f"-noise{self.noise_top:g}to{self.noise_b_sd:g}"
                f"-blur{self.blur_top:g}to{self.blur_b_px:g}"
                f"-contrast{self.contrast_top:g}to{self.contrast_b:g}")

    @property
    def noise_top(self) -> float:
        return (self.noise_b_sd if self.noise_b_sd_top is None
                else self.noise_b_sd_top)

    @property
    def blur_top(self) -> float:
        return (self.blur_b_px if self.blur_b_px_top is None
                else self.blur_b_px_top)

    @property
    def contrast_top(self) -> float:
        return (self.contrast_b if self.contrast_b_top is None
                else self.contrast_b_top)

    def rung(self, tile_row: int) -> tuple[float, float, float]:
        if self.tile_rows < 2:
            return self.blur_top, self.noise_top, self.contrast_top
        fraction = tile_row / (self.tile_rows - 1)
        return (self.blur_top + fraction * (self.blur_b_px - self.blur_top),
                self.noise_top
                + fraction * (self.noise_b_sd - self.noise_top),
                self.contrast_top
                + fraction * (self.contrast_b - self.contrast_top))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def paper_level(image: np.ndarray) -> np.ndarray:
    """The render's own paper, read off its border rather than assumed."""
    edge = np.concatenate((
        image[:PAPER_BORDER_PX].reshape(-1, image.shape[2]),
        image[-PAPER_BORDER_PX:].reshape(-1, image.shape[2])))
    return np.median(edge, axis=0)


def band_px(image: np.ndarray, cell_px: float, border_px: float,
            band_tiles: int) -> tuple[int, int]:
    width = band_tiles * TILE_CELLS * cell_px
    x0 = int(round(border_px))
    x1 = min(int(image.shape[1]), int(round(border_px + width)))
    return x0, x1


def capture_a(image: np.ndarray, x0: int, x1: int,
              blur_px: float = 0.0) -> np.ndarray:
    """A's own optics: the SAME blur B gets, when the experiment wants
    one channel seen twice rather than two different channels."""
    source = image.astype(np.float32)
    if blur_px > 0.0:
        from scipy import ndimage

        source = ndimage.gaussian_filter(source, (blur_px, blur_px, 0.0))
    rng = np.random.default_rng(SEED_A)
    kept = source + rng.normal(0.0, NOISE_A_SD, source.shape)
    kept[:, x0:x1] = paper_level(image)
    return np.round(np.clip(kept, 0, 255)).astype(np.uint8)


def row_bands(image: np.ndarray, cell_px: float, border_px: float,
              tile_rows: int) -> tuple[tuple[int, int], ...]:
    height = TILE_CELLS * cell_px
    bounds = []
    for tile_row in range(tile_rows):
        y0 = int(round(border_px + tile_row * height))
        y1 = int(round(border_px + (tile_row + 1) * height))
        bounds.append((max(0, y0), min(int(image.shape[0]), y1)))
    return tuple(bounds)


def capture_b(image: np.ndarray, x0: int, x1: int, spec: PairSpec,
              bands: tuple[tuple[int, int], ...]) -> np.ndarray:
    from scipy import ndimage

    paper = paper_level(image)
    out = np.broadcast_to(paper, image.shape).astype(np.float32).copy()
    source = image.astype(np.float32)
    for tile_row, (y0, y1) in enumerate(bands):
        if y1 <= y0:
            continue
        if spec.band_rows is not None and tile_row >= spec.band_rows:
            continue
        blur_px, noise_sd, contrast = spec.rung(tile_row)
        # blur the whole frame at this rung's sigma and take only this
        # band's rows, so no seam is introduced at a band boundary
        blurred = ndimage.gaussian_filter(source, (blur_px, blur_px, 0.0))
        rng = np.random.default_rng(SEED_B + tile_row)
        band = paper + contrast * (blurred[y0:y1, x0:x1] - paper)
        out[y0:y1, x0:x1] = band + rng.normal(0.0, noise_sd, band.shape)
    return np.round(np.clip(out, 0, 255)).astype(np.uint8)


def make_pair(base_tiff: Path, outdir: Path, cell_px: float,
              border_px: float, spec: PairSpec) -> tuple[Path, Path]:
    import tifffile

    outdir.mkdir(parents=True, exist_ok=True)
    image = np.asarray(tifffile.imread(base_tiff))
    x0, x1 = band_px(image, cell_px, border_px, spec.band_tiles)
    bands = row_bands(image, cell_px, border_px, spec.tile_rows)
    path_a = outdir / f"pair-a-{spec.token}.tiff"
    path_b = outdir / f"pair-b-{spec.token}.tiff"
    if not path_a.is_file():
        tifffile.imwrite(path_a, capture_a(image, x0, x1, spec.blur_a_px))
    if not path_b.is_file():
        tifffile.imwrite(path_b, capture_b(image, x0, x1, spec, bands))
    return path_a, path_b


def band_tiles_of(spec: PairSpec, tiles_x: int) -> tuple[int, ...]:
    return tuple(range(min(spec.band_tiles, tiles_x)))
