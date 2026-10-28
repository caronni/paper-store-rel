"""Sha-validated, read-only access to the E9 (K instance) inputs.

The subject is the e029 volume: `hp-m281-ink` c2-r0700@3392x2368 printed
on the HP CLJ M281fdw, scanned once on the Canon at 4800 dpi grey, closed
VERIFIED at 1940/1961 tiles.  Three files, all opened read-only:

* the receive state (8.2 MB — `load_session` costs ~1.4 s, so nothing is
  cached);
* the 2.29 GB capture TIFF (streamed once per lane and decimated into a
  temporary memmap, exactly as `cascade._derive_level` does);
* `page000_gt.npy`, the emitted DOT raster, which is the only truth for
  the 21 uncertified tiles and is VALIDATED against every one of the
  1940 certificates before it is used (truth-path discipline).

Nothing is ever written next to the state or the scan; artifacts land
under `scratch/plane-fields/p2/e9/`.
"""
from __future__ import annotations

import gc
import hashlib
import subprocess
import tempfile
import warnings
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
SRC_HOLO = REPO / "src" / "holo"
MAIN_SCRATCH = Path("scratch")
OUT_DIR = MAIN_SCRATCH / "plane-fields" / "p2" / "e9"

VOLUME_DIR = MAIN_SCRATCH / "e028" / "holo-c2-r0700-q07-ink-counting"
STATE_PATH = VOLUME_DIR / "receive.state"
GT_PATH = VOLUME_DIR / "page000_gt.npy"
PAYLOAD_PATH = VOLUME_DIR / "payload-counting.bin"
SCAN_PATH = MAIN_SCRATCH / "e028" / "hp-canon-c2-ink-counting.tiff"

# experiments/029-holo-v1-first-print.md, run 029.0s + the volume manifest.
SCAN_SHA256 = "d9c4e932b904b8173ef0bf08165f384ed2ce644105f58965d2dca14165672c22"
PAYLOAD_SHA256 = (
    "e5021f8d099587c38c95185d51e82ab7cab29db0dfe68e502f1ab9dd165787af")
GT_SHA256 = "3e48560378b5613ec58a7948934512091ba9baff878393f1543a09e4751cb2f8"
CODING_ID = "c2-r0700"
PRINTER_ID = "hp-m281-ink"
SCAN_DPI = 4800.0
CELL_DOTS = 2


def sha256_file(path: Path, chunk: int = 1 << 24) -> str:
    """Stream one file's SHA-256 (multi-GB inputs are never slurped)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(("git", *args), cwd=REPO, check=True,
                              capture_output=True, text=True).stdout.strip()
    except Exception:                                      # noqa: BLE001
        return "unknown"


def receiver_tree_sha256(root: Path | None = None) -> str:
    """SHA-256 over every source file under the live ``holo`` package."""
    if root is None:
        import holo
        root = Path(holo.__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def provenance() -> dict[str, object]:
    """Tree/input identity recorded with every artifact."""
    import holo
    return {
        "git_head": _git("rev-parse", "HEAD"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "git_dirty_paths": _git("status", "--porcelain").splitlines(),
        "holo_package": str(Path(holo.__file__).resolve().parent),
        "receiver_tree_sha256": receiver_tree_sha256(),
        "state_path": str(STATE_PATH),
        "state_sha256": sha256_file(STATE_PATH),
        "scan_path": str(SCAN_PATH),
        "scan_sha256_expected": SCAN_SHA256,
        "gt_path": str(GT_PATH),
        "gt_sha256_expected": GT_SHA256,
        "payload_sha256_expected": PAYLOAD_SHA256,
    }


def load_state():
    """Open the archived e029 state read-only (VERIFIED, 1940 certs)."""
    from holo.receive.observer import ProvisionalReceiverWarning
    from holo.receive.session import load_session
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ProvisionalReceiverWarning)
        return load_session(STATE_PATH, defer_fountain_validation=True)


def format_spec():
    """The e029 spec — deliberately not a FORMAT_ROWS row (§029 header)."""
    from holo.devices.profiles import make_spec
    return make_spec(CODING_ID, PRINTER_ID)


@dataclass(frozen=True)
class Truth:
    """Printed cells for the whole page, and the certified subset of them.

    ``gt`` is the emitter's own page (from the sidecar) and is the only
    truth the 21 uncertified tiles have.  ``certified`` is the receiver's
    own certificate-derived truth (``records.printed_cells_from_record``)
    with -1 on every uncertified tile: it is what an ARM may use as a
    label, and the two are cross-checked cell for cell on all 1940
    certified tiles before either is returned.
    """

    gt: np.ndarray                  # (cells_y, cells_x) uint8
    certified: np.ndarray           # (cells_y, cells_x) int8, -1 = unknown
    n_certified_tiles: int
    n_checked_cells: int
    n_mismatched_cells: int


def load_truth(state, spec) -> Truth:
    """Load the GT sidecar and VALIDATE it against every certificate."""
    from holo.receive.records import printed_cells_from_record

    packed = np.load(GT_PATH)
    dots = np.unpackbits(packed, axis=1, bitorder="big")
    cells_y, cells_x = spec.layout.cells_yx
    block = dots[: cells_y * CELL_DOTS, : cells_x * CELL_DOTS].reshape(
        cells_y, CELL_DOTS, cells_x, CELL_DOTS)
    if not bool((block.min(axis=(1, 3)) == block.max(axis=(1, 3))).all()):
        raise SystemExit("GT sidecar: a cell's dot block is not uniform")
    gt = np.ascontiguousarray(block[:, 0, :, 0]).astype(np.uint8)
    del dots, block, packed

    certified = np.full((cells_y, cells_x), -1, np.int8)
    checked = 0
    mismatched = 0
    for record in state.certificates:
        printed = np.asarray(
            printed_cells_from_record(record, spec)).reshape(64, 64)
        ty, tx = record.tile_yx
        window = gt[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64]
        checked += printed.size
        mismatched += int(np.count_nonzero(
            printed.astype(np.uint8) != window))
        certified[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64] = (
            printed.astype(np.int8))
    if mismatched:
        raise SystemExit(
            f"truth path: {mismatched} of {checked} certified cells "
            "disagree between the certificates and the GT sidecar")
    return Truth(gt, certified, len(state.certificates), checked, mismatched)


def residue_addresses(state, spec) -> tuple[tuple[int, int, int], ...]:
    """The complete uncertified population — every tile of every page."""
    certified = {(row.page, *row.tile_yx) for row in state.certificates}
    tiles_y, tiles_x = spec.layout.tiles_yx
    return tuple(sorted(
        (0, ty, tx)
        for ty in range(tiles_y) for tx in range(tiles_x)
        if (0, ty, tx) not in certified
    ))


@dataclass
class LaneRaster:
    """One lane's view of the capture plus the temp file backing it."""

    raster: object
    lane_id: str
    native_per_view: Fraction
    dpi: float
    shape: tuple[int, int]
    _handle: object | None = None

    def release(self) -> None:
        self.raster = None
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        gc.collect()


def open_lane_raster(lane, capture, *, verify_sha: bool = True) -> LaneRaster:
    """Derive one ladder lane's raster exactly as ``cascade`` does.

    The native capture is opened, decimated into a temporary memmap by the
    registered exact-rational area transform, and then RELEASED — the
    2.29 GB native array is not held while the placement/payload stages
    run.  A native lane (``native_per_view == 1``) keeps the native
    object, which is why the 16 ppc lane costs what it costs.
    """
    from holo.receive.cascade import ScaleRaster
    from holo.receive.scale_space import AreaPixelTransform, area_decimate_into
    from holo.receive.scan import open_capture

    native = open_capture(SCAN_PATH, SCAN_DPI)
    if verify_sha and native.source_sha256 != SCAN_SHA256:
        raise SystemExit(
            f"capture sha {native.source_sha256[:12]}… is not the e029 scan")
    if native.source_sha256 != capture.source_sha256:
        raise SystemExit("capture sha does not match the archived state")
    scale = Fraction(lane.native_per_view_num, lane.native_per_view_den)
    dpi = SCAN_DPI * float(1 / scale)
    if scale == 1:
        return LaneRaster(native, lane.lane_id, scale, dpi, native.shape)
    transform = AreaPixelTransform(scale)
    source = native.crop_native(0, native.shape[0], 0, native.shape[1])
    shape = transform.output_shape(source.shape)
    handle = tempfile.NamedTemporaryFile(prefix="e9-scale-", suffix=".dat")
    pixels = np.memmap(handle, mode="w+", dtype=source.dtype, shape=shape)
    area_decimate_into(source, transform, pixels)
    raster = ScaleRaster(pixels, capture.source_sha256, dpi)
    del source, native
    gc.collect()
    return LaneRaster(raster, lane.lane_id, scale, dpi, shape, handle)


__all__ = [
    "CODING_ID", "GT_PATH", "LaneRaster", "MAIN_SCRATCH", "OUT_DIR",
    "PAYLOAD_SHA256", "PRINTER_ID", "REPO", "SCAN_PATH", "SCAN_SHA256",
    "STATE_PATH", "Truth", "VOLUME_DIR", "format_spec", "load_state",
    "load_truth", "open_lane_raster", "provenance", "receiver_tree_sha256",
    "residue_addresses", "sha256_file",
]
