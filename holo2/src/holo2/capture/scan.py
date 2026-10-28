"""Immutable native-raster ingest (carried leaf; DESIGN §5.1, §13).

Copied and adapted from ``src/holo/receive/scan.py`` under the holo2
firewall (copy-and-adapt, never import).  The authentication semantics
are unchanged: the SHA-256 of the encoded source bytes IS the capture
identity (L1), the raster is frozen at ingest, and
``verify_source_unchanged`` keeps the stat-memo re-authentication with
cryptographic escalation.  Nothing here reads a clock or draws random
numbers, and this module knows nothing about the store — H2c wires
:class:`SourceId` onto ``records.CaptureRecord``.

``open_capture`` binds source bytes to an operator-supplied true DPI and
keeps scanner samples in their native dtype.  Consumers request bounded
float32 luma crops; ingest does not impose a photometric convention,
normalize contrast, rotate pixels, or manufacture decimated footings.

TIFFs are memory-mapped when the encoding permits it.  Source hashing and
array hashing are streamed, and returned crops cannot mutate the captured
pixels.  RGB input is reduced to raw scanner luma by the historical equal
channel mean required by the E019/E021 input contract.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import numpy as np


_HASH_CHUNK_BYTES = 1 << 22
_PIL_LIMIT_LOCK = Lock()


@dataclass(frozen=True, slots=True)
class SourceId:
    """Point-in-time identity of one encoded or in-memory raster source.

    The source SHA-256 is the receiver's acquisition identity.  This boundary
    therefore accepts only original scanner acquisitions: re-encoded,
    resized, cropped, or otherwise derived copies would have different byte
    identities but are correlated evidence and must not be submitted as
    independent acquisitions.  Internally derived scale views never cross
    this native-ingest boundary.
    """

    sha256: str
    dpi: float
    dtype: str
    shape: tuple[int, int]
    channels: int

    def __post_init__(self) -> None:
        if (len(self.sha256) != 64
                or any(ch not in "0123456789abcdef" for ch in self.sha256)):
            raise ValueError("source sha256 must be 64 lowercase hex digits")
        if (isinstance(self.dpi, (bool, np.bool_))
                or not np.isfinite(self.dpi) or self.dpi <= 0):
            raise ValueError("source dpi must be finite and positive")
        try:
            np.dtype(self.dtype)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid source dtype {self.dtype!r}") from exc
        if (len(self.shape) != 2 or any(
                isinstance(value, (bool, np.bool_))
                or int(value) != value or value <= 0
                for value in self.shape)):
            raise ValueError("source shape must contain two positive integers")
        if self.channels not in (1, 3):
            raise ValueError("source channels must be 1 or 3")

def _raw_luma(pixels: np.ndarray) -> np.ndarray:
    """Convert native grey/RGB samples to the E021 raw float32 plane."""
    if pixels.ndim == 3:
        return pixels[..., :3].mean(axis=2, dtype=np.float32)
    return pixels.astype(np.float32, copy=False)


def _validate_shape(shape: tuple[int, ...]) -> None:
    """Validate raster dimensionality without imposing a size policy."""
    if len(shape) not in (2, 3):
        raise ValueError(f"capture must be 2-D grey or 3-D RGB, got {shape}")
    if shape[0] < 1 or shape[1] < 1:
        raise ValueError(f"degenerate capture shape {shape}")


def _validate(native: np.ndarray) -> tuple[np.ndarray, int]:
    """Canonicalize singleton grey and validate the native sample type."""
    if native.ndim == 3 and native.shape[2] == 1:
        native = native[..., 0]
    if native.ndim == 2:
        channels = 1
    elif native.ndim == 3 and native.shape[2] == 3:
        channels = 3
    elif native.ndim == 3 and native.shape[2] == 4:
        raise ValueError(
            "4-channel capture is ambiguous (RGBA vs CMYK); reduce it to "
            "grey or RGB before ingest")
    else:
        raise ValueError(
            f"capture must be 2-D grey or 3-D RGB, got shape {native.shape}"
            + (" (a multi-page TIFF: pass one page)"
               if native.ndim == 3 and native.shape[0] <= 16 else ""))
    _validate_shape(tuple(int(value) for value in native.shape))
    if (not np.issubdtype(native.dtype, np.number)
            or np.issubdtype(native.dtype, np.complexfloating)
            or np.issubdtype(native.dtype, np.bool_)):
        raise ValueError(
            f"capture dtype must be real numeric, got {native.dtype}")
    return native, channels


def _freeze_native(native: np.ndarray, *, borrowed: bool) -> np.ndarray:
    """Freeze backing pixels without retaining a mutable caller alias.

    NumPy's writeable flag is not an ownership guarantee: a read-only view can
    still have a writeable base.  Every borrowed array is therefore detached.
    File-backed arrays remain zero-copy and are authenticated again before a
    retention barrier.
    """
    if borrowed:
        native = np.array(native, copy=True, order="K")
    try:
        native.setflags(write=False)
    except ValueError:
        if native.flags.writeable:
            native = np.array(native, copy=True, order="K")
            native.setflags(write=False)
    return native


def _scan_luma_max(native: np.ndarray) -> float:
    """Actual global raw-luma maximum, evaluated in bounded row strips."""
    rows = max(1, _HASH_CHUNK_BYTES // max(1, native[0:1].nbytes))
    maximum = -np.inf
    for row0 in range(0, native.shape[0], rows):
        luma = _raw_luma(native[row0:row0 + rows])
        if not np.isfinite(luma).all():
            raise ValueError("capture contains non-finite pixel values")
        maximum = max(maximum, float(np.max(luma)))
    return float(maximum)


class Raster:
    """An authenticated native raster with strict bounded crop access."""

    def __init__(
        self,
        native: np.ndarray,
        source: SourceId,
        *,
        luma_max: float,
        source_path: Path | None = None,
        source_stat: tuple[int, int, int, int] | None = None,
    ) -> None:
        expected = source.shape + (() if source.channels == 1 else (3,))
        if native.shape != expected or str(native.dtype) != source.dtype:
            raise ValueError(
                "native raster does not match authenticated source metadata")
        if not np.isfinite(luma_max):
            raise ValueError("global luma maximum must be finite")
        self._native = native
        self.source = source
        self.dpi = source.dpi
        self.shape = source.shape
        self.luma_max = float(luma_max)
        self._source_path = source_path
        # Re-auth stat memo (RECEIVE-DESIGN §8, v0.37): the ingest-verified
        # (dev, ino, size, mtime_ns) tuple.  ``None`` means every retention
        # barrier escalates to the full byte re-stream.
        self._source_stat = source_stat

    def __repr__(self) -> str:
        return (f"Raster(native, shape={self.shape}, dpi={self.dpi:g}, "
                f"dtype={self.source.dtype})")

    @property
    def source_sha256(self) -> str:
        return self.source.sha256

    @property
    def native_dtype(self) -> np.dtype:
        return self._native.dtype

    def contains(self, r0: int, r1: int, c0: int, c1: int) -> bool:
        """Whether a box is non-empty, integral, and inside this raster."""
        coordinates = (r0, r1, c0, c1)
        if any(isinstance(value, (bool, np.bool_)) or not isinstance(
                value, (int, np.integer)) for value in coordinates):
            return False
        return (0 <= r0 < r1 <= self.shape[0]
                and 0 <= c0 < c1 <= self.shape[1])

    def _require_crop(self, r0: int, r1: int, c0: int, c1: int) -> None:
        if not self.contains(r0, r1, c0, c1):
            raise ValueError(
                f"crop ({r0},{r1},{c0},{c1}) is not an in-bounds box of "
                f"raster {self.shape}")

    def crop_native(
        self, r0: int, r1: int, c0: int, c1: int
    ) -> np.ndarray:
        """Read-only native-dtype crop; no photometric conversion."""
        self._require_crop(r0, r1, c0, c1)
        crop = self._native[r0:r1, c0:c1]
        crop.setflags(write=False)
        return crop

    def crop_luma(
        self, r0: int, r1: int, c0: int, c1: int
    ) -> np.ndarray:
        """Read-only raw float32 luma for a strict in-bounds crop."""
        native = self.crop_native(r0, r1, c0, c1)
        out = _raw_luma(native)
        if np.shares_memory(out, self._native) or not out.flags.c_contiguous:
            out = np.array(out, dtype=np.float32, copy=True, order="C")
        out.setflags(write=False)
        return out

    def verify_source_unchanged(self) -> None:
        """Re-authenticate path bytes immediately before durable retention.

        In-memory inputs were detached at ingest and need no second check.
        For path inputs the per-barrier detector is stat-based with
        cryptographic escalation (RECEIVE-DESIGN §8, v0.37): a fresh stat
        tuple (dev, ino, size, mtime_ns) that exactly matches the retained
        ingest-verified tuple is a memo hit and skips the re-stream; ANY
        observable difference escalates to the full encoded-byte re-stream
        and SHA-256 comparison, as in E023b's commit gate, and the memo
        refreshes only after a passing full check.  Threat model on record:
        accidental mutation, not an adversary — a deliberate rewrite forging
        size and mtime_ns onto the same dev/ino is not detected by the stat
        probe (PAYLOAD-IMPROVEMENTS 7.2).  Moving a file is harmless only if
        the original path remains available with the exact authenticated
        bytes.
        """
        if self._source_path is None:
            return
        try:
            stat = self._source_path.stat()
        except OSError as exc:
            raise ValueError(
                f"capture source is unavailable at retention: "
                f"{self._source_path}"
            ) from exc
        current_stat = (stat.st_dev, stat.st_ino,
                        stat.st_size, stat.st_mtime_ns)
        if (self._source_stat is not None
                and current_stat == self._source_stat):
            return
        try:
            current = _sha256_file(self._source_path)
        except OSError as exc:
            raise ValueError(
                f"capture source is unavailable at retention: "
                f"{self._source_path}"
            ) from exc
        if current != self.source.sha256:
            raise ValueError(
                f"capture source changed while being processed: "
                f"{self._source_path}"
            )
        self._source_stat = current_stat


def _sha256_file(path: Path) -> str:
    """Hash encoded source bytes exactly once, in bounded chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_array(native: np.ndarray) -> str:
    """Hash array interpretation and content without a whole-array copy."""
    digest = hashlib.sha256()
    digest.update(f"holo-raster|{native.dtype.str}|{native.shape}|".encode())
    rows = max(1, _HASH_CHUNK_BYTES // max(1, native[0:1].nbytes))
    for row0 in range(0, native.shape[0], rows):
        digest.update(np.ascontiguousarray(native[row0:row0 + rows]))
    return digest.hexdigest()


def _read_tiff(path: Path) -> np.ndarray | None:
    """Read one TIFF page, preferring a direct native-dtype memory map."""
    try:
        import tifffile
    except ImportError:  # pragma: no cover - declared runtime dependency
        return None
    try:
        with tifffile.TiffFile(path) as tiff:
            if len(tiff.pages) != 1:
                raise ValueError(
                    f"multi-page TIFF has {len(tiff.pages)} pages; pass one "
                    "page as a separate source")
            page = tiff.pages[0]
            _validate_shape(tuple(int(value) for value in page.shape))
            try:
                return page.asarray(out="memmap")
            except Exception as exc:
                # A compressed TIFF may require decoding, but tifffile can
                # still decode it into a temporary memmap.  If that bounded-
                # RSS path is unavailable, do not silently materialize a
                # multi-gigabyte scanner page in RAM.
                raise ValueError(
                    "TIFF decoder could not provide a memory-mapped raster"
                ) from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"could not read TIFF capture {path}") from exc


def _load_image(path: Path) -> np.ndarray:
    """Decode a path without coercing scanner dtype or imposing a size cap."""
    native: np.ndarray | None = None
    if path.suffix.lower() in (".tif", ".tiff"):
        native = _read_tiff(path)
    if native is None:
        from PIL import Image

        # Pillow's decompression limit is process-global.  Size policy belongs
        # to the caller, so disable it only while this image is decoded.
        with _PIL_LIMIT_LOCK:
            previous_limit = Image.MAX_IMAGE_PIXELS
            Image.MAX_IMAGE_PIXELS = None
            try:
                with Image.open(path) as image:
                    if image.mode not in {
                        "L", "I", "F", "RGB", "I;16", "I;16B", "I;16L",
                        "I;16N",
                    }:
                        raise ValueError(
                            f"image mode {image.mode!r} has no unambiguous "
                            "raw grey/RGB interpretation"
                        )
                    bands = len(image.getbands())
                    shape = ((int(image.height), int(image.width), bands)
                             if bands > 1
                             else (int(image.height), int(image.width)))
                    _validate_shape(shape)
                    native = np.asarray(image)
            finally:
                Image.MAX_IMAGE_PIXELS = previous_limit
    if native is None or native.size == 0:  # pragma: no cover - decoders raise
        raise ValueError(f"could not read a capture from {path}")
    return native


def open_capture(source: str | Path | np.ndarray, dpi: float) -> Raster:
    """Open native scan pixels at an explicit, operator-supplied true DPI."""
    if (isinstance(dpi, (bool, np.bool_))
            or not np.isfinite(dpi) or dpi <= 0):
        raise ValueError(f"dpi must be finite and positive, got {dpi}")

    path_source = isinstance(source, (str, Path))
    if path_source:
        path = Path(source).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"no capture at {path}")
        stat_before = path.stat()
        sha256 = _sha256_file(path)
        native = _load_image(path)
        borrowed = False
    else:
        native = np.asarray(source)
        borrowed = True

    native, channels = _validate(native)
    native = _freeze_native(native, borrowed=borrowed)
    luma_max = _scan_luma_max(native)
    if not path_source:
        sha256 = _sha256_array(native)
    else:
        stat_after = path.stat()
        before = (stat_before.st_dev, stat_before.st_ino,
                  stat_before.st_size, stat_before.st_mtime_ns)
        after = (stat_after.st_dev, stat_after.st_ino,
                 stat_after.st_size, stat_after.st_mtime_ns)
        if after != before:
            raise ValueError(f"capture source changed while opening: {path}")

    source_id = SourceId(
        sha256=sha256,
        dpi=float(dpi),
        dtype=str(native.dtype),
        shape=(int(native.shape[0]), int(native.shape[1])),
        channels=channels,
    )
    return Raster(
        native, source_id, luma_max=luma_max,
        source_path=path if path_source else None,
        source_stat=after if path_source else None,
    )
