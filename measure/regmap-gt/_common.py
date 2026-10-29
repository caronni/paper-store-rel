# Historical record of e033 (supervised per-plane registration on sheet I, the AltaLink Y sinusoid; PAGE-FIELD B3's
# reference), retired from scratch/xerox-v1-20260818/regmap-gt/ 2026-10-09; inputs in the evidence archive.
# Shared helpers, no output of their own; measure_plane_offsets.py and _anchor.py are the entry points.
"""Shared helpers: GT access, scan access, highpass, FFT correlation.

Read-only against the scan + GT sidecar.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import tifffile

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from measure import _evidence  # noqa: E402

# under --evidence-root (the published archive root)
SCAN_REL = "paper-store-evidence-holo-2026-10/033-xerox-rung-experiments/I/captures/I-canon-2400rgb.tiff"
PS_REL = "paper-store-evidence-holo-2026-10/033-xerox-rung-experiments/I/jobs/page000.ps"
OUT_DIR = _REPO / "build" / "regmap-gt"
# The GT field is not in the published archive (tier delete: it regenerates
# from the published PostScript); it is read from OUT_DIR, where
# util/ps_gt.py writes it, gated on the published manifest's gt_sha256.
GT_PATH = OUT_DIR / "page000_gt.npy"
GT_SHA256 = "26c76ca4e26b0c6558a86fee999add99d7eaaa7ec29469665c78208e441fa134"


def configure(evidence_root: Path | None) -> None:
    """Resolve the evidence root once and export it, so pool workers inherit it;
    refuse by name unless the capture and the regenerated GT are there."""
    root = _evidence.resolve(evidence_root, tool="regmap-gt")
    os.environ[_evidence.ENV] = str(root)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _evidence.need(root / SCAN_REL, tool="regmap-gt")
    _evidence.need(GT_PATH, tool="regmap-gt", regenerate=(
        f"env/bin/python util/ps_gt.py {root / PS_REL} --out {GT_PATH} "
        f"--expect-sha256 {GT_SHA256}"))


def _evidence_path(rel: str) -> str:
    return str(_evidence.resolve(None, tool="regmap-gt") / rel)

FIELD_DOTS_YX = (6784, 4736)      # 3392x2368 cells @ 2 dots/cell
TILE_DOTS = 128                    # 64 cells
TILES_YX = (53, 37)
PX_PER_DOT = 4                     # 2400 dpi scan / 600 dpi print

_gt_packed = None
_scan = None


def gt_packed() -> np.ndarray:
    global _gt_packed
    if _gt_packed is None:
        _gt_packed = np.load(GT_PATH, mmap_mode="r")
    return _gt_packed


def gt_patch(plane: int, y0: int, x0: int, h: int, w: int) -> np.ndarray:
    """Unpacked GT dots [0/1] for plane in [C,M,Y], dot coords."""
    p = gt_packed()
    b0, b1 = x0 // 8, (x0 + w + 7) // 8
    raw = np.ascontiguousarray(p[plane, y0:y0 + h, b0:b1])
    bits = np.unpackbits(raw, axis=1, bitorder="big")
    off = x0 - b0 * 8
    return bits[:, off:off + w]


def scan() -> np.ndarray:
    global _scan
    if _scan is None:
        _scan = tifffile.imread(_evidence_path(SCAN_REL), out="memmap")
    return _scan


def scan_patch(y0: int, x0: int, h: int, w: int) -> np.ndarray:
    im = scan()
    y0 = max(0, y0); x0 = max(0, x0)
    y1 = min(im.shape[0], y0 + h); x1 = min(im.shape[1], x0 + w)
    return np.asarray(im[y0:y1, x0:x1, :], dtype=np.float32)


def boxcar(a: np.ndarray, k: int) -> np.ndarray:
    """Separable boxcar via cumulative sums, 'same' with edge replication."""
    def one(x, axis):
        pad = [(0, 0)] * x.ndim
        pad[axis] = (k // 2, k - 1 - k // 2)
        xp = np.pad(x, pad, mode="edge")
        c = np.cumsum(xp, axis=axis)
        sl0 = [slice(None)] * x.ndim
        sl1 = [slice(None)] * x.ndim
        sl0[axis] = slice(k, None)
        sl1[axis] = slice(0, -k)
        first = [slice(None)] * x.ndim
        first[axis] = slice(k - 1, k)
        head = np.take(c, [k - 1], axis=axis)
        body = c[tuple(sl0)] - c[tuple(sl1)]
        return np.concatenate([head, body], axis=axis) / k
    return one(one(a, 0), 1)


def highpass(a: np.ndarray, k: int = 25) -> np.ndarray:
    return a - boxcar(a, k)


def xcorr_shift(ref: np.ndarray, tgt: np.ndarray, max_shift: int):
    """Normalised cross-correlation of equal-size zero-mean fields.

    Returns (dy, dx, peak, ratio) where (dy,dx) is the shift (subpixel) that
    best aligns tgt onto ref: tgt(y+dy, x+dx) ~ ref(y,x).
    peak = normalised correlation at the peak; ratio = peak / rms of the
    correlation surface outside a small exclusion disc (sharpness measure).
    """
    a = ref - ref.mean()
    b = tgt - tgt.mean()
    na = np.sqrt((a * a).sum())
    nb = np.sqrt((b * b).sum())
    if na == 0 or nb == 0:
        return 0.0, 0.0, 0.0, 0.0
    F = np.fft.rfft2(a) * np.conj(np.fft.rfft2(b))
    c = np.fft.irfft2(F, s=a.shape) / (na * nb)
    c = np.fft.fftshift(c)
    cy, cx = a.shape[0] // 2, a.shape[1] // 2
    m = max_shift
    win = c[cy - m:cy + m + 1, cx - m:cx + m + 1]
    iy, ix = np.unravel_index(np.argmax(win), win.shape)
    peak = float(win[iy, ix])
    # parabolic subpixel
    def para(vm, v0, vp):
        d = vm - 2 * v0 + vp
        return 0.0 if d == 0 else 0.5 * (vm - vp) / d
    sy = sx = 0.0
    if 0 < iy < win.shape[0] - 1:
        sy = para(win[iy - 1, ix], win[iy, ix], win[iy + 1, ix])
    if 0 < ix < win.shape[1] - 1:
        sx = para(win[iy, ix - 1], win[iy, ix], win[iy, ix + 1])
    dy = (iy - m) + sy
    dx = (ix - m) + sx
    # background rms excluding a 5px disc around the peak
    bg = win.copy()
    y0 = max(0, iy - 5); y1 = min(win.shape[0], iy + 6)
    x0 = max(0, ix - 5); x1 = min(win.shape[1], ix + 6)
    bg[y0:y1, x0:x1] = np.nan
    rms = float(np.sqrt(np.nanmean(bg ** 2)))
    ratio = peak / rms if rms > 0 else 0.0
    # note: shift convention -- c[dy,dx] peaks where b shifted by (dy,dx)
    # matches a, i.e. tgt[y-dy, x-dx] ~ ref[y,x]
    return dy, dx, peak, ratio
