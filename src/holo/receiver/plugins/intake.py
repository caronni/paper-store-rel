from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path

import numpy as np

from ..data import (
    Capture,
    CaptureOpen,
    IntegrityError,
    Level,
    PlaneRaster,
    Region,
)
from ..format.identity import Family
from ..lib.decimate import (
    AreaPixelTransform,
    area_decimate_into,
    auto_ppc_levels,
    luma_f32,
    native_pixels_per_cell,
)
from .words import ADDRESSING_ON_R

HASH_CHUNK_BYTES: int = 1 << 22
COPY_CHUNK_ROWS: int = 1024
BORDER_PX: int = 32
PLANE_GREY: str = "g"
PLANE_LUMA: str = "y"
PLANES_RGB: tuple[str, str, str] = ("r", "g", "b")
TIFF_SUFFIXES: tuple[str, str] = (".tif", ".tiff")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_tiff(path: Path) -> np.ndarray:
    import tifffile

    with tifffile.TiffFile(path) as tiff:
        return tiff.pages[0].asarray(out="memmap")


def _read_image(path: Path) -> np.ndarray:
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    with Image.open(path) as image:
        return np.asarray(image)


def load_native(path: Path) -> np.ndarray:
    native = (_read_tiff(path) if path.suffix.lower() in TIFF_SUFFIXES
              else _read_image(path))
    if native.ndim == 3 and native.shape[2] == 1:
        native = native[..., 0]
    return native


def platen_backing(native: np.ndarray) -> float:
    height, width = int(native.shape[0]), int(native.shape[1])
    border = max(1, min(BORDER_PX, height, width))
    strips = (
        luma_f32(native[0:border, 0:width]).ravel(),
        luma_f32(native[height - border:height, 0:width]).ravel(),
        luma_f32(native[0:height, 0:border]).ravel(),
        luma_f32(native[0:height, width - border:width]).ravel(),
    )
    return float(np.median(np.concatenate(strips)))


def _fraction_token(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}-{value.denominator}"


def level_label(index: int, ppc: Fraction, dpi_level: Fraction) -> str:
    return (f"l{index:02d}-{_fraction_token(ppc)}ppc"
            f"-{_fraction_token(dpi_level)}dpi")


#: The ladder floors at 2 ppc, ends at native exactly once and never
#: upsamples.  The coarse rung is not a warm-up: e023c minted 671 of 754
#: and 1310 of 1438 certificates at the coarsest level, so 'start nearer
#: native' is a yield change, not an optimization (spec 06 §2.3, §4).
def build_levels(dpi: float, pitch_in: Fraction,
                 shape_px: tuple[int, int]) -> tuple[Level, ...]:
    native_ppc = native_pixels_per_cell(dpi, pitch_in)
    levels: list[Level] = []
    for index, ppc in enumerate(auto_ppc_levels(dpi, pitch_in)):
        scale = native_ppc / ppc
        transform = AreaPixelTransform(scale)
        levels.append(Level(
            index=index,
            ppc=ppc,
            scale=scale,
            shape_px=transform.output_shape(shape_px),
            label=level_label(index, ppc, ppc / pitch_in),
        ))
    return tuple(levels)


#: Strictly ascending means one lane per ppc per capture, which is what
#: makes tiles.union's own-capture exclusion STRUCTURAL rather than a
#: filter: a union subject is minted only where >= 2 distinct captures
#: hold evidence at the same exact rational ppc (MULTIRES-SPEC).
def assert_ascending_ladder(capture_id: str,
                            levels: tuple[Level, ...]) -> None:
    ppcs = tuple(level.ppc for level in levels)
    if all(lower < upper for lower, upper in zip(ppcs, ppcs[1:])):
        return
    raise IntegrityError(
        f"capture {capture_id} ladder {tuple(map(str, ppcs))} is not "
        f"strictly ascending: one lane per ppc per capture is the "
        f"union-pairing law")


def levels_ppc(levels: tuple[Level, ...]) -> tuple[str, ...]:
    return tuple(str(level.ppc) for level in levels)


def native_plane_names(channels: int) -> tuple[str, ...]:
    return PLANES_RGB if channels == 3 else (PLANE_GREY,)


#: A K decode of an RGB scan gets ONE derived luma plane per SUB-NATIVE
#: level and none at native: native K luma is the float32 channel mean
#: taken at crop time, and storing it as u8 would re-round it away from
#: the registered E021 photometry (spec 06 §1, §2.2).
def derived_planes(channels: int,
                   family: Family) -> tuple[tuple[str, int | None], ...]:
    if channels == 1:
        return ((PLANE_GREY, None),)
    if family is Family.K:
        return ((PLANE_LUMA, None),)
    return tuple((name, index) for index, name in enumerate(PLANES_RGB))


def _open_target(path: Path, shape_px: tuple[int, int]) -> np.ndarray:
    return np.lib.format.open_memmap(
        path, mode="w+", dtype=np.uint8,
        shape=(int(shape_px[0]), int(shape_px[1])))


#: u8 in, u8 out: the whole acceptance corpus is 8-bit, so the target is
#: a uint8 memmap and the guard towers (dtype checks, the 16-bit /256
#: branch, luma_max) were dropped by ruling (spec 06 §1, §5).  A 16-bit
#: source therefore wraps here rather than being refused.
def _copy_plane(path: Path, native: np.ndarray, channel: int | None,
                shape_px: tuple[int, int]) -> None:
    target = _open_target(path, shape_px)
    height = int(shape_px[0])
    for y0 in range(0, height, COPY_CHUNK_ROWS):
        y1 = min(height, y0 + COPY_CHUNK_ROWS)
        source = (native[y0:y1] if channel is None
                  else native[y0:y1, :, channel])
        target[y0:y1] = source
    target.flush()


def _decimate_plane(path: Path, source: np.ndarray,
                    transform: AreaPixelTransform,
                    shape_px: tuple[int, int]) -> None:
    target = _open_target(path, shape_px)
    area_decimate_into(source, transform, target)
    target.flush()


def plane_path(plane_dir: Path, level_index: int, plane: str) -> Path:
    return plane_dir / f"l{level_index:02d}-{plane}.npy"


def ingest_capture(
    path: Path,
    dpi: float,
    pitch_in: Fraction,
    family: Family,
    run_dir: Path,
    ordinal: int = 0,
    dpi_forced: bool = False,
) -> tuple[Capture, tuple[PlaneRaster, ...], tuple[object, ...]]:
    # The source SHA is the ACQUISITION identity, not just a cache key: a
    # re-encoded, cropped or decimated copy hashes differently but is
    # correlated evidence, and submitting it as a second capture
    # double-counts it (e018/e023b; spec 06 §4).  Only the ladder decimates.
    capture_id = sha256_file(path)
    native = load_native(path)
    channels = 1 if native.ndim == 2 else 3
    shape_px = (int(native.shape[0]), int(native.shape[1]))
    # The backing fills placement's crops, so it is read in the channel
    # addressing reads: R for a family addressed on R (a view, no float
    # stack), equal-channel luma otherwise.
    backing = platen_backing(native[..., 0] if channels == 3
                             and family in ADDRESSING_ON_R else native)
    levels = build_levels(dpi, pitch_in, shape_px)
    assert_ascending_ladder(capture_id, levels)
    plane_dir = run_dir / capture_id[:12]
    plane_dir.mkdir(parents=True, exist_ok=True)
    rasters: list[PlaneRaster] = []
    native_index = levels[-1].index
    for channel, name in enumerate(native_plane_names(channels)):
        target = plane_path(plane_dir, native_index, name)
        _copy_plane(target, native, None if channels == 1 else channel,
                    shape_px)
        rasters.append(PlaneRaster(capture_id, native_index, name, target,
                                   shape_px))
    # Every sub-native plane is decimated from the NATIVE plane, never from
    # the level above it (spec 06 §2.4): ppc is the cross-capture
    # correspondence, and recursive resizing both accumulates rounding and
    # forks the evidence identity two captures are joined on.
    for level in levels[:-1]:
        transform = AreaPixelTransform(level.scale)
        for name, channel in derived_planes(channels, family):
            target = plane_path(plane_dir, level.index, name)
            source = native if channel is None else native[..., channel]
            _decimate_plane(target, source, transform, level.shape_px)
            rasters.append(PlaneRaster(capture_id, level.index, name, target,
                                       level.shape_px))
    capture = Capture(
        capture_id=capture_id,
        path=path,
        dpi=float(dpi),
        shape_px=shape_px,
        channels=channels,
        platen_backing=backing,
        levels=levels,
        plane_dir=plane_dir,
        dpi_forced=bool(dpi_forced),
    )
    event = CaptureOpen(capture=capture_id, dpi=float(dpi),
                        shape_yx=shape_px, channels=channels, duplicate=False,
                        ordinal=ordinal, levels_ppc=levels_ppc(levels))
    return capture, tuple(rasters), (event,)


def ingest_captures(
    paths: tuple[Path, ...],
    dpis: tuple[float, ...],
    pitch_in: Fraction,
    family: Family,
    run_dir: Path,
    forced: tuple[bool, ...] | None = None,
) -> tuple[tuple[Capture, ...], tuple[PlaneRaster, ...], tuple[object, ...]]:
    captures: list[Capture] = []
    rasters: list[PlaneRaster] = []
    events: list[object] = []
    seen: dict[str, Capture] = {}
    flags = (False,) * len(paths) if forced is None else tuple(forced)
    for path, dpi, dpi_forced in zip(paths, dpis, flags):
        capture_id = sha256_file(path)
        standing = seen.get(capture_id)
        if standing is not None:
            if float(dpi) != standing.dpi:
                raise ValueError(
                    f"same source declared at two DPIs in one run "
                    f"(the Q2 refusal): {path} sha {capture_id} at "
                    f"{standing.dpi} and {float(dpi)} dpi — a corrected "
                    f"DPI renames every lane the evidence cites")
            # The same contradiction in the other half of the declaration
            # (2026-10-02): one source cannot be both voted and trusted.
            if bool(dpi_forced) != standing.dpi_forced:
                raise ValueError(
                    f"same source declared both --dpi and --dpi-force in "
                    f"one run: {path} sha {capture_id} — one capture is "
                    f"surveyed one way")
            events.append(CaptureOpen(
                capture=capture_id, dpi=float(dpi),
                shape_yx=standing.shape_px, channels=standing.channels,
                duplicate=True, levels_ppc=levels_ppc(standing.levels)))
            continue
        capture, planes, opened = ingest_capture(
            path, dpi, pitch_in, family, run_dir, ordinal=len(captures),
            dpi_forced=bool(dpi_forced))
        seen[capture_id] = capture
        captures.append(capture)
        rasters.extend(planes)
        events.extend(opened)
    return tuple(captures), tuple(rasters), tuple(events)


def native_level(capture: Capture) -> Level:
    return capture.levels[-1]


def level_transform(level: Level) -> AreaPixelTransform:
    return AreaPixelTransform(level.scale)


def level_pitch_px(level: Level, native_pitch_px: float) -> float:
    return float(native_pitch_px) / float(level.scale)


def level_extent(level: Level, native_extent: tuple[int, int, int, int],
                 ) -> tuple[int, int, int, int] | None:
    y0, x0, y1, x1 = native_extent
    p, q = level.scale.numerator, level.scale.denominator
    fy0, fy1 = -(-y0 * q // p), y1 * q // p
    fx0, fx1 = -(-x0 * q // p), x1 * q // p
    if fy1 <= fy0 or fx1 <= fx0:
        return None
    return int(fy0), int(fx0), int(fy1), int(fx1)


#: Rung pixel j covers native [j*p/q, (j+1)*p/q); its centre is
#: (p(2j+1) - q) / 2q, taken in INTEGER arithmetic.  A float here would
#: make support a function of rounding at exactly the coarse rungs where
#: the boxes are widest (holo2's footing-frame rule; spec 06 §2.5).
def level_centres(level: Level, indices: np.ndarray) -> np.ndarray:
    p, q = level.scale.numerator, level.scale.denominator
    return (p * (2 * indices + 1) - q) // (2 * q)


def region_support_crop(region: Region, level: Level, r0: int, r1: int,
                        c0: int, c1: int) -> np.ndarray:
    rows = level_centres(level, np.arange(r0, r1, dtype=np.int64))
    cols = level_centres(level, np.arange(c0, c1, dtype=np.int64))
    origin_y, origin_x = region.origin_yx
    height, width = region.extent_px
    inside_y = (rows >= origin_y) & (rows < origin_y + height)
    inside_x = (cols >= origin_x) & (cols < origin_x + width)
    out = np.zeros((r1 - r0, c1 - c0), bool)
    if not inside_y.any() or not inside_x.any():
        return out
    grid_y = ((rows[inside_y] - origin_y) // region.step_px).astype(np.intp)
    grid_x = ((cols[inside_x] - origin_x) // region.step_px).astype(np.intp)
    out[np.ix_(np.flatnonzero(inside_y), np.flatnonzero(inside_x))] = (
        region.cells[np.ix_(grid_y, grid_x)])
    return out
