"""Two derived-scan checks: e018's 1600-dpi decimations and the 2x Xerox-scan upsamples.

decimated: ``scratch/e018/decimated-*_1600.tiff`` against
`experiments/018-confetti-c3-play/decimate_scan.py` (--factor 3) over the
4800 captures beside them.  The 2.3 GB captures are memory-mapped and
reduced in row bands with the script's own arithmetic (float32 3x3 mean,
round, clip, uint8 — the sum of nine bytes is exact in float32, so banding
cannot change a value); the full-frame result is compared pixel for pixel
with the archived TIFF, and written with the script's `tifffile.imwrite`
call to compare the file sha too.

x2: ``scans/*-x2.png`` against a 2x upsample of the PNG without the suffix,
pixel for pixel (a byte-exact PNG re-encode is not expected): nearest
neighbour as the brief assumed, and the corner-aligned linear zoom the
files turned out to be (e007 007.2: "COLOR path needs 2x upsampling
before stripdec"; the kernel is recorded nowhere).
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import numpy as np
import tifffile
from PIL import Image

from .runner import sha256_file

SIDE_COLUMNS = ("derived", "source", "check", "verdict", "note")
E018 = "scratch/e018"
DECIMATED = (  # archived decimation: its 4800 capture
    ("decimated-1_1600.tiff", "hp-e018-canon-4800-confetti-1.tiff"),
    ("decimated-1-2nd_1600.tiff", "hp-e018-canon-4800-confetti-1-2ndtake.tiff"),
    ("decimated-2_1600.tiff", "hp-e018-canon-4800-confetti-2.tiff"),
    ("decimated-2-2nd_1600.tiff", "hp-e018-canon-4800-confetti-2-2ndtake.tiff"),
    ("decimated-3_1600.tiff", "hp-e018-canon-4800-confetti-3.tiff"),
    ("decimated-3-2nd_1600.tiff", "hp-e018-canon-4800-confetti-3-2ndtake.tiff"),
)
BAND_ROWS = 3 * 1024


def decimate_memmap(src: np.ndarray, factor: int = 3) -> np.ndarray:
    """decimate_scan.decimate on a (memory-mapped) grey frame, in row bands."""
    if src.ndim != 2:
        raise ValueError("grey frames only (the e018 captures are grey)")
    h, w = src.shape
    hc, wc = h - h % factor, w - w % factor
    out = np.empty((hc // factor, wc // factor), np.uint8)
    for y in range(0, hc, BAND_ROWS):
        band = np.asarray(src[y:min(y + BAND_ROWS, hc), :wc], dtype=np.float32)
        out[y // factor:(y + band.shape[0]) // factor] = (
            band.reshape(band.shape[0] // factor, factor, wc // factor, factor).mean((1, 3))
            .round().clip(0, 255).astype(np.uint8))
    return out


def check_decimated(root: Path) -> list[tuple[str, ...]]:
    rows = []
    for derived, source in DECIMATED:
        d, s = root / E018 / derived, root / E018 / source
        if not (d.is_file() and s.is_file()):
            rows.append((f"{E018}/{derived}", f"{E018}/{source}", "pixels", "not-checked", "file missing"))
            continue
        fresh = decimate_memmap(tifffile.memmap(str(s)))
        archived = tifffile.memmap(str(d))
        same = fresh.shape == archived.shape and np.array_equal(fresh, archived)
        n_diff = "" if same or fresh.shape != archived.shape else f"{int((fresh != archived).sum())} px differ"
        rows.append((f"{E018}/{derived}", f"{E018}/{source}", "pixels", "identical" if same else "differs",
                     n_diff or f"shape {fresh.shape}"))
        buf = io.BytesIO()
        tifffile.imwrite(buf, fresh)
        got = hashlib.sha256(buf.getvalue()).hexdigest()
        want = sha256_file(d)
        rows.append((f"{E018}/{derived}", f"{E018}/{source}", "file sha256",
                     "byte-identical" if got == want else "differs",
                     f"tifffile {tifffile.__version__}; got {got[:16]}…, archived {want[:16]}…"))
    return rows


def upsample_linear_x2(a: np.ndarray) -> np.ndarray:
    """The kernel the archived x2 files match: scipy.ndimage.zoom on float32, order 1,
    corner-aligned (grid_mode False), truncated to uint8 — found by search, no script records it."""
    from scipy import ndimage
    zoom = (2, 2) + (1,) * (a.ndim - 2)
    return ndimage.zoom(a.astype(np.float32), zoom, order=1, grid_mode=False).astype(np.uint8)


def check_x2(root: Path) -> list[tuple[str, ...]]:
    import scipy
    rows = []
    Image.MAX_IMAGE_PIXELS = None            # PNGs of 140 Mpx; the TIFF rule does not apply
    for up in sorted((root / "scans").glob("*-x2.png")):
        src = up.with_name(up.name.replace("-x2.png", ".png"))
        rel, srel = str(up.relative_to(root)), str(src.relative_to(root))
        if not src.is_file():
            rows.append((rel, srel, "pixels", "not-checked", "source PNG missing"))
            continue
        with Image.open(src) as a, Image.open(up) as b:
            mode = (a.mode, b.mode)
            sa, sb = np.asarray(a), np.asarray(b)
        for check, fresh in (("pixels, 2x nearest", lambda: sa.repeat(2, axis=0).repeat(2, axis=1)),
                             ("pixels, 2x linear (scipy zoom f32 order 1, corners, truncate)",
                              lambda: upsample_linear_x2(sa))):
            got = fresh()
            if mode[0] != mode[1] or got.shape != sb.shape:
                rows.append((rel, srel, check, "differs", f"mode {mode} shape {got.shape} vs {sb.shape}"))
                continue
            diff = got != sb
            n = int((diff.any(-1) if diff.ndim == 3 else diff).sum())
            rows.append((rel, srel, check, "identical" if n == 0 else "differs",
                         f"{mode[1]} {sb.shape}" + (f"; scipy {scipy.__version__}" if "scipy" in check else "")
                         + ("" if n == 0 else f"; {n} px differ")))
            del got, diff
    return rows


def write(path: Path, rows: list[tuple[str, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\t".join(SIDE_COLUMNS) + "\n" + "".join("\t".join(r) + "\n" for r in rows))
