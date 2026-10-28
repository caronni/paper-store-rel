"""Memory-bounded access to characterization scan rasters.

The characterization analyzer deliberately keeps the capture in its native
dtype and layout.  Numerical conversion happens only for bounded crops (or
for the small, block-averaged registration thumbnail).  This matters for
4800-dpi A4 TIFFs, where a capture-wide RGB float array would require many
gigabytes.

Coordinates in this module use the image convention ``(x, y)`` when passed
as points and ``(y0, y1, x0, x1)`` for array crops.  A requested crop is
either wholly inside the raster or refused; it is never clipped to an edge.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


MAX_SCAN_PIXELS = 6_000_000_000
MAX_RESIDENT_FALLBACK_BYTES = 256 << 20
DEFAULT_MAX_CROP_PIXELS = 4_000_000
DEFAULT_MAX_THUMBNAIL_PIXELS = 16_000_000


def _integer_scale(dtype: np.dtype[Any]) -> float:
    if np.issubdtype(dtype, np.bool_):
        return 1.0
    if np.issubdtype(dtype, np.integer):
        return float(np.iinfo(dtype).max)
    return 1.0


class RasterSource:
    """A native scan plus strict, bounded conversion helpers.

    ``source`` may be a path or an already-open NumPy array.  TIFF paths are
    memory-mapped with :mod:`tifffile` when their encoding permits it.  The
    original array is exposed read-only by convention through ``native``;
    ``native_shape`` and ``native_dtype`` always describe the encoded raster,
    even when its channels are planar.
    """

    def __init__(
        self,
        source: str | Path | np.ndarray,
        *,
        max_crop_pixels: int = DEFAULT_MAX_CROP_PIXELS,
    ) -> None:
        if max_crop_pixels <= 0:
            raise ValueError("max_crop_pixels must be positive")
        self.max_crop_pixels = int(max_crop_pixels)
        self.path: Path | None = None
        self._axes = ""
        self._memmapped = False
        self._pil_image: Image.Image | None = None
        self.color_model = "array-untyped"

        if isinstance(source, (str, Path)):
            self.path = Path(source)
            self._array = self._open_path(self.path)
        else:
            self._array = np.asarray(source)

        if self._array.size == 0:
            raise ValueError("empty scan raster")
        self.native_shape = tuple(int(value) for value in self._array.shape)
        self.native_dtype = self._array.dtype
        # ``shape`` intentionally retains the encoded/native shape.  Spatial
        # consumers should use ``spatial_shape`` or ``height``/``width``.
        self.shape = self.native_shape
        self.dtype = self.native_dtype
        self._configure_layout()
        if self.path is None:
            self.color_model = (
                "array-assumed-RGB" if self.channels >= 3
                else "array-grayscale"
            )
        if self.height * self.width > MAX_SCAN_PIXELS:
            raise ValueError(
                f"scan has {self.height * self.width} pixels; "
                f"limit is {MAX_SCAN_PIXELS}"
            )
        self._scale = _integer_scale(self.native_dtype)
        self.scale = self._scale

    def _open_path(self, path: Path) -> np.ndarray:
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.suffix.lower() in {".tif", ".tiff"}:
            try:
                import tifffile
            except ImportError as exc:
                raise ValueError(
                    "TIFF characterization requires tifffile so page count, "
                    "color model, and memory mapping can be verified"
                ) from exc
            with tifffile.TiffFile(path) as tif:
                if len(tif.pages) != 1 or len(tif.series) != 1:
                    raise ValueError(
                        "characterization scans must be exactly one TIFF "
                        "page and one image series"
                    )
                series = tif.series[0]
                self._axes = str(series.axes)
                decoded_bytes = int(
                    np.prod(series.shape, dtype=np.int64)
                ) * int(np.dtype(series.dtype).itemsize)
                photometric = getattr(tif.pages[0], "photometric", None)
                model = str(
                    getattr(photometric, "name", photometric)
                ).upper()
                if model not in {"RGB", "MINISBLACK"}:
                    raise ValueError(
                        f"unsupported TIFF color model {model!r}; "
                        "supply RGB/RGBA or black-is-zero grayscale"
                    )
                self.color_model = (
                    "RGB" if model == "RGB" else "grayscale"
                )
            try:
                array = tifffile.memmap(path)
            except Exception as exc:
                if decoded_bytes > MAX_RESIDENT_FALLBACK_BYTES:
                    raise ValueError(
                        "compressed/tiled TIFF would require "
                        f"{decoded_bytes} decoded bytes in memory; use a "
                        "single-page contiguous uncompressed TIFF"
                    ) from exc
                # Pillow remains valid after structure and size were checked.
                self._memmapped = False
                self._axes = ""
            else:
                self._memmapped = isinstance(array, np.memmap)
                return array

        old_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = MAX_SCAN_PIXELS
        try:
            image = Image.open(path)
            mode = image.mode
            supported = (
                mode in {"1", "L", "LA", "I", "F", "RGB", "RGBA"}
                or mode.startswith("I;16")
            )
            if not supported:
                image.close()
                raise ValueError(
                    f"unsupported raster color model {mode!r}; "
                    "supply RGB/RGBA or grayscale reflectance"
                )
            width, height = image.size
            bytes_per_sample = (
                4 if mode in {"I", "F"}
                else 2 if mode.startswith("I;16")
                else 1
            )
            decoded_bytes = (
                int(width)
                * int(height)
                * len(image.getbands())
                * bytes_per_sample
            )
            if (
                width * height > MAX_SCAN_PIXELS
                or decoded_bytes > MAX_RESIDENT_FALLBACK_BYTES
            ):
                image.close()
                raise ValueError(
                    "non-memory-mappable raster would require "
                    f"{decoded_bytes} decoded bytes in memory; use a "
                    "single-page contiguous uncompressed TIFF"
                )
            self.color_model = (
                mode if mode in {"RGB", "RGBA"} else "grayscale"
            )
            self._pil_image = image
            return np.asarray(image)
        finally:
            Image.MAX_IMAGE_PIXELS = old_limit

    def _configure_layout(self) -> None:
        array = self._array
        axes = self._axes.upper()
        if array.ndim == 2:
            self.height, self.width = map(int, array.shape)
            self.channels = 1
            self._layout = "YX"
        elif array.ndim == 3 and (
            axes.endswith("YXS")
            or axes.endswith("YXC")
            or (not axes and array.shape[-1] in (1, 2, 3, 4))
        ):
            self.height, self.width, self.channels = map(int, array.shape)
            self._layout = "YXS"
        elif array.ndim == 3 and (
            axes.endswith("SYX")
            or axes.endswith("CYX")
            or (not axes and array.shape[0] in (1, 2, 3, 4))
        ):
            self.channels, self.height, self.width = map(int, array.shape)
            self._layout = "SYX"
        else:
            raise ValueError(
                f"unsupported scan shape {array.shape}, TIFF axes={self._axes!r}"
            )
        if self.channels not in (1, 2, 3, 4):
            raise ValueError(f"unsupported scan channel count {self.channels}")
        self.spatial_shape = (self.height, self.width)

    @property
    def native(self) -> np.ndarray:
        """The unconverted capture array (no copy)."""

        return self._array

    @property
    def memmapped(self) -> bool:
        return self._memmapped

    @property
    def is_color(self) -> bool:
        return self.channels >= 3

    def close(self) -> None:
        """Release a Pillow-backed input handle, if one is present."""

        if self._pil_image is not None:
            self._pil_image.close()
            self._pil_image = None

    def __enter__(self) -> "RasterSource":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def crop_is_visible(self, y0: int, y1: int, x0: int, x1: int) -> bool:
        """Whether the entire half-open integer crop is in the raster."""

        return bool(
            0 <= y0 < y1 <= self.height and 0 <= x0 < x1 <= self.width
        )

    def points_visible(
        self,
        x: np.ndarray | float,
        y: np.ndarray | float,
        *,
        margin: float = 0.0,
    ) -> np.ndarray:
        """Elementwise visibility for scan-pixel sample centres."""

        if margin < 0:
            raise ValueError("visibility margin must be nonnegative")
        xx, yy = np.broadcast_arrays(
            np.asarray(x, dtype=np.float64),
            np.asarray(y, dtype=np.float64),
        )
        return (
            np.isfinite(xx)
            & np.isfinite(yy)
            & (xx >= margin)
            & (yy >= margin)
            & (xx <= self.width - 1.0 - margin)
            & (yy <= self.height - 1.0 - margin)
        )

    def footprint_visibility(
        self,
        points_xy: np.ndarray,
        *,
        margin: float = 0.0,
    ) -> tuple[bool, float]:
        """Return full-footprint visibility and visible-vertex fraction.

        For an affine-mapped rectangle, pass its four vertices.  Raster and
        affine rectangles are convex, so all four vertices being visible is
        sufficient for the complete footprint to be visible.
        """

        points = np.asarray(points_xy, dtype=np.float64)
        if points.ndim < 2 or points.shape[-1] != 2 or points.size == 0:
            raise ValueError("points_xy must be a nonempty (..., 2) array")
        visible = self.points_visible(
            points[..., 0], points[..., 1], margin=margin
        )
        return bool(np.all(visible)), float(np.mean(visible))

    def _validate_crop(
        self,
        y0: int,
        y1: int,
        x0: int,
        x1: int,
        *,
        max_pixels: int | None,
    ) -> tuple[int, int, int, int]:
        values = (y0, y1, x0, x1)
        if any(isinstance(value, (bool, np.bool_)) for value in values):
            raise TypeError("crop coordinates must be integers")
        y0, y1, x0, x1 = (int(value) for value in values)
        if not self.crop_is_visible(y0, y1, x0, x1):
            raise ValueError(
                f"crop ({y0}, {y1}, {x0}, {x1}) is not wholly inside "
                f"raster {self.spatial_shape}"
            )
        limit = self.max_crop_pixels if max_pixels is None else int(max_pixels)
        if limit <= 0:
            raise ValueError("crop pixel limit must be positive")
        pixels = (y1 - y0) * (x1 - x0)
        if pixels > limit:
            raise ValueError(
                f"crop contains {pixels} pixels; bounded-crop limit is {limit}"
            )
        return y0, y1, x0, x1

    def crop_native(
        self,
        y0: int,
        y1: int,
        x0: int,
        x1: int,
        *,
        max_pixels: int | None = None,
    ) -> np.ndarray:
        """Return an in-bounds native-dtype view in its encoded layout."""

        y0, y1, x0, x1 = self._validate_crop(
            y0, y1, x0, x1, max_pixels=max_pixels
        )
        if self._layout == "YX":
            return self._array[y0:y1, x0:x1]
        if self._layout == "YXS":
            return self._array[y0:y1, x0:x1, :]
        return self._array[:, y0:y1, x0:x1]

    def _crop_channels_float32(
        self,
        y0: int,
        y1: int,
        x0: int,
        x1: int,
        *,
        max_pixels: int | None,
    ) -> np.ndarray:
        native = self.crop_native(
            y0, y1, x0, x1, max_pixels=max_pixels
        )
        if self._layout == "SYX":
            native = np.moveaxis(native, 0, -1)
        values = np.asarray(native, dtype=np.float32)
        if self._scale != 1.0:
            values /= np.float32(self._scale)
        # Scanner float formats are required to be reflectance-like.  Clipping
        # is per-crop and does not mutate or normalize the capture.
        return np.clip(values, np.float32(0.0), np.float32(1.0))

    def crop_rgb(
        self,
        y0: int,
        y1: int,
        x0: int,
        x1: int,
        *,
        max_pixels: int | None = None,
    ) -> np.ndarray:
        """Convert one bounded, fully visible crop to reflectance RGB float32."""

        values = self._crop_channels_float32(
            y0, y1, x0, x1, max_pixels=max_pixels
        )
        if values.ndim == 2:
            return np.repeat(values[..., None], 3, axis=2)
        if values.shape[-1] == 1:
            return np.repeat(values, 3, axis=2)
        if values.shape[-1] == 2:
            # Grey + alpha: alpha is capture plumbing, not a color channel.
            return np.repeat(values[..., :1], 3, axis=2)
        return values[..., :3]

    def crop_luma(
        self,
        y0: int,
        y1: int,
        x0: int,
        x1: int,
        *,
        max_pixels: int | None = None,
    ) -> np.ndarray:
        """Convert one bounded crop directly to float32 luma reflectance."""

        values = self._crop_channels_float32(
            y0, y1, x0, x1, max_pixels=max_pixels
        )
        if values.ndim == 2:
            return values
        if values.shape[-1] < 3:
            return values[..., 0]
        return (
            np.float32(0.2126) * values[..., 0]
            + np.float32(0.7152) * values[..., 1]
            + np.float32(0.0722) * values[..., 2]
        )

    def thumbnail_grey(
        self,
        scan_dpi_x: float | None = None,
        scan_dpi_y: float | None = None,
        target_dpi: float = 300.0,
        *,
        max_pixels: int = DEFAULT_MAX_THUMBNAIL_PIXELS,
    ) -> tuple[np.ndarray, float, float]:
        """Build a memory-safe block-mean registration thumbnail.

        The returned factors map each thumbnail pixel to an ``fx`` by ``fy``
        native block.  Trailing partial native blocks are deliberately
        omitted, making the pixel-centre map exact:

        ``x_native = (x_thumb + .5) * fx - .5``.
        """

        if target_dpi <= 0 or max_pixels <= 0:
            raise ValueError("target_dpi and max_pixels must be positive")
        if (scan_dpi_x is None) != (scan_dpi_y is None):
            raise ValueError("supply both scanner DPI values or neither")
        if scan_dpi_x is not None:
            if scan_dpi_x <= 0 or scan_dpi_y is None or scan_dpi_y <= 0:
                raise ValueError("scanner DPI must be positive")
            fx = max(1, int(round(float(scan_dpi_x) / target_dpi)))
            fy = max(1, int(round(float(scan_dpi_y) / target_dpi)))
        else:
            fx = fy = 1

        while (self.width // fx) * (self.height // fy) > max_pixels:
            factor = max(
                2,
                int(
                    math.ceil(
                        math.sqrt(
                            (self.width // fx)
                            * (self.height // fy)
                            / max_pixels
                        )
                    )
                ),
            )
            fx *= factor
            fy *= factor

        out_w, out_h = self.width // fx, self.height // fy
        if out_w <= 0 or out_h <= 0:
            raise ValueError("scan is smaller than one thumbnail block")
        out = np.empty((out_h, out_w), dtype=np.float32)

        # Two-dimensional tiling keeps every native conversion below the
        # crop bound even for unusually wide captures.
        rows_step = max(
            1, min(32, self.max_crop_pixels // max(fx * fy, 1))
        )
        for oy0 in range(0, out_h, rows_step):
            oy1 = min(out_h, oy0 + rows_step)
            native_rows = (oy1 - oy0) * fy
            max_out_cols = max(
                1, self.max_crop_pixels // max(native_rows * fx, 1)
            )
            for ox0 in range(0, out_w, max_out_cols):
                ox1 = min(out_w, ox0 + max_out_cols)
                luma = self.crop_luma(
                    oy0 * fy,
                    oy1 * fy,
                    ox0 * fx,
                    ox1 * fx,
                    max_pixels=self.max_crop_pixels,
                )
                out[oy0:oy1, ox0:ox1] = luma.reshape(
                    oy1 - oy0, fy, ox1 - ox0, fx
                ).mean(axis=(1, 3), dtype=np.float32)
        return out, float(fx), float(fy)

__all__ = [
    "DEFAULT_MAX_CROP_PIXELS",
    "DEFAULT_MAX_THUMBNAIL_PIXELS",
    "MAX_SCAN_PIXELS",
    "RasterSource",
]
