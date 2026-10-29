"""e041 S10p — read the PCL XL RGB probe sheet: how did each patch's cells print?

The S10p sheet sweeps RGB values around every C/M/Y state corner under three halftone methods
(default, eHighLPI, a 1x1 matrix) and five emission kinds (pattern, vector, srgb, tonerblack, and
treatdefault = the treatment witness drawn without SetColorTreatment).
Every patch is a 93 x 93 dot square of 31 x 31 random 3 x 3 dot cells (1 = the patch RGB,
0 = white; bits from the manifest's seed) over a 93 x 24 dot solid bar.  This instrument reads a
2400 dpi RGB scan of the printed sheet against the generator's manifest
(m281-routes-20261004/S10p-pclxl-rgb-probe.manifest.json, the contract in the e041 log):

1. finds the five black fiducials (four 3 x 3 mm squares, one 3 x 6 mm bar) on a 1/8 block-mean
   min-channel image, matches them to the manifest by two-point similarity hypotheses (any
   placement, as-is or turned 180 deg), refines each centre at full resolution and fits the
   mm -> scan-pixel affine; refuses on residual > --max-resid-mm, scale off 2400/25.4 px/mm by more
   than --scale-tol, a rotation more than 3 deg from 0/180, or fewer than four fiducials (the shared
   helpers — Scan(path, dpi), fit_page, the fiducial finder, sub_px_per_dot — take any scan dpi:
   e041_scale_readout and e041_band_screen pass --scan-dpi, e.g. 4800; the fiducial finder's block
   factor and every px tolerance scale with it; this instrument's own main stays at 2400);
2. per patch: the solid bar's interior (eroded 0.3 mm) -> mean R, G, B; the pattern square plus a
   0.5 mm margin resampled into a page-aligned frame at 4 px per dot, the expected ink mask
   (12 px cells) registered against the target's own channel(s) by FFT cross-correlation within
   +/- 0.4 mm (measure.e041_gt_compare.xcorr_shift, imported), each cell's centre 0.5-cell box
   sampled (e041_gt_compare.sample_cells' box-filter logic, copied and generalised to 31 cells
   and sub-pixel centres), and per channel: inked and blank cell means, d' = (blank - inked) /
   pooled sd, hard error at the midpoint threshold;
3. contamination in each FOREIGN channel (C -> R, M -> G, Y -> B own; W has none, CMY no foreign):
   local page white minus the blank-cell mean and minus the inked-cell mean, page white = the
   median of a 0.4-0.9 mm frame around the patch clear of every other mark (the page-wide median
   of the gaps when the frame is empty);
4. lattice: the max off-axis peak in the 140-240 lpi annulus over the annulus median on a 256 px
   window of raw scan centred on the pattern, own channel(s), exactly e041_screen_fine's ratio
   (annulus_mask imported): ~7 noise, ~20 an unscreened print, 30-90 the engine's screens; beside
   it the same ratio on the window's pixels shuffled (seeded), the no-structure control.

Ranking rule: within each (target, method, kind) group -- so the riders rank among themselves, never
mixed into the pattern sweep -- patches are sorted by own-channel d' (the
minimum over the target's own channels) descending — W, which has no own channel, by its largest
ink darkening in any channel ascending — with lattice and contamination shown beside, never folded
into the sort.

Outputs in --out: <tag>-patches.csv, <tag>-summary.json; the ranking (top 8 per group plus the
corner anchor's row) on stdout.

    PYTHONPATH=src:. env/bin/python -m measure.e041_probe_readout \
        --scan <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S10p2/captures/S10p2-canon-2400rgb.tiff \
        --manifest <evidence>/paper-store-evidence-holo-2026-10/041-m281-screen-routes/S10p2/jobs/S10p2-pclxl-rgb-probe.manifest.json \
        --out build/e041/probe

Smoke test without printer or scanner: measure/e041_probe_synth.py paints synthetic scans to the
same contract.  Note: on ideal square 12 px cells the lattice ratio reads 60-120 (the cells' sinc
nulls at 200 lpi cross the annulus and pull its median down); the shuffled control reads 7-13.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage

from measure.e041_gt_compare import xcorr_shift
from measure.e041_screen_fine import annulus_mask

Image.MAX_IMAGE_PIXELS = None
SCAN_DPI_NOMINAL = 2400.0              # the default; Scan(path, dpi) carries any other scan resolution
PX_PER_MM_NOMINAL = SCAN_DPI_NOMINAL / 25.4
PRINT_DPI = 600
SUB_PX_PER_DOT = 4                     # the rectified frame at the default: 2400 / 600 (sub_px_per_dot)
COARSE_K = 8                           # block-mean factor of the fiducial search image at 2400 (coarse_k)
LOSSLESS_TIFF = (1, 5, 8, 32773, 32946)  # none, LZW, deflate, packbits: read by tifffile (read_rgb)
CHANNELS = ("R", "G", "B")
OWN = {"W": (), "C": (0,), "M": (1,), "Y": (2,), "CM": (0, 1), "CY": (0, 2), "MY": (1, 2),
       "CMY": (0, 1, 2)}
CORNER_RGB = {"W": (255, 255, 255), "C": (0, 255, 255), "M": (255, 0, 255), "Y": (255, 255, 0),
              "CM": (0, 0, 255), "CY": (0, 255, 0), "MY": (255, 0, 0), "CMY": (0, 0, 0)}
TARGET_ORDER = ("C", "M", "Y", "CM", "CY", "MY", "CMY", "W")
SOLID_ERODE_MM = 0.3
PATTERN_MARGIN_MM = 0.5
SEARCH_MM = 0.4
LATTICE_WINDOW_PX = 256
LATTICE_LPI = (140.0, 240.0)
LATTICE_AXIS_DEG = 8.0
REG_MIN_PEAK = 0.25


@dataclass(frozen=True)
class Geometry:
    dot_mm: float
    pattern_dots: int
    solid_dots: int
    cell_dots: int
    cells: int


# ---------------------------------------------------------------- manifest

def load_manifest(path: Path) -> dict[str, Any]:
    man = json.loads(path.read_text())
    for key in ("tag", "dpi", "page_mm", "fiducials", "patch_px", "patches"):
        if key not in man:
            raise SystemExit(f"manifest {path} lacks '{key}'")
    return man


def geometry(man: dict[str, Any]) -> Geometry:
    pp = man["patch_px"]
    g = Geometry(25.4 / float(man["dpi"]), int(pp["pattern_dots"]), int(pp["solid_dots"]),
                 int(pp["cell_dots"]), int(pp["cells"]))
    if g.cells * g.cell_dots != g.pattern_dots:
        raise SystemExit(f"patch_px inconsistent: {pp}")
    return g


def pattern_bits(seed: int, cells: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, 2, size=(cells, cells), dtype=np.uint8)


def checked_pattern(patch: dict[str, Any], cells: int) -> np.ndarray:
    pat = pattern_bits(int(patch["seed"]), cells)
    sha = hashlib.sha256(pat.tobytes()).hexdigest()
    if patch.get("pattern_sha256") not in (None, sha):
        raise SystemExit(f"patch {patch['id']}: pattern_sha256 mismatch (seed {patch['seed']})"
                         " — contract fork")
    return pat


def footprints_mm(man: dict[str, Any], g: Geometry) -> list[tuple[float, float, float, float]]:
    """(x0, y0, x1, y1) of every mark: patches (pattern + bar) and fiducials."""
    h_mm = (g.pattern_dots + g.solid_dots) * g.dot_mm
    w_mm = g.pattern_dots * g.dot_mm
    rects = [(p["x_mm"], p["y_mm"], p["x_mm"] + w_mm, p["y_mm"] + h_mm) for p in man["patches"]]
    rects += [(f["x_mm"], f["y_mm"], f["x_mm"] + f["w_mm"], f["y_mm"] + f["h_mm"]) for f in man["fiducials"]]
    return rects + excluded_rects(man.get("excluded_zones_mm", {}))


def excluded_rects(zones: Any) -> list[tuple[float, float, float, float]]:
    """Best-effort read of excluded_zones_mm: [x, y, w, h] lists or {x_mm, y_mm, w_mm, h_mm} dicts."""
    out: list[tuple[float, float, float, float]] = []
    items = zones.values() if isinstance(zones, dict) else zones if isinstance(zones, list) else []
    for z in items:
        if isinstance(z, list) and len(z) == 4 and all(isinstance(v, (int, float)) for v in z):
            out.append((z[0], z[1], z[0] + z[2], z[1] + z[3]))
        elif isinstance(z, dict) and {"x_mm", "y_mm", "w_mm", "h_mm"} <= set(z):
            out.append((z["x_mm"], z["y_mm"], z["x_mm"] + z["w_mm"], z["y_mm"] + z["h_mm"]))
    return out


# ---------------------------------------------------------------- scan access

def sub_px_per_dot(scan_dpi: float, print_dpi: float = PRINT_DPI) -> int:
    """Rectified px per printed dot: 4 at 2400 dpi, 8 at 4800; refuses a non-integer ratio."""
    sub = scan_dpi / print_dpi
    if sub < 1 or abs(sub - round(sub)) > 1e-9:
        raise SystemExit(f"scan dpi {scan_dpi} is not an integer multiple of the {print_dpi} dpi print")
    return int(round(sub))


def coarse_k(scan_dpi: float) -> int:
    """The fiducial search's block-mean factor: COARSE_K at 2400 dpi, scaled so a coarse pixel stays
    COARSE_K / 2400 inch (16 at 4800)."""
    return max(1, int(round(COARSE_K * scan_dpi / SCAN_DPI_NOMINAL)))


def read_rgb(path: Path) -> np.ndarray:
    """The scan's pixel array: tifffile for a single-page, interleaved, uncompressed or losslessly compressed
    TIFF (decoded straight into one array: peak ~1x the image), else PIL (whose RGB decode holds 4 bytes per
    pixel plus the packed copy: ~3.7x the image at peak — 6.4 GB on a 1.7 GB 2400 dpi scan, measured).  Both
    give the same pixels for those TIFFs."""
    if path.suffix.lower() in (".tif", ".tiff"):
        try:
            import tifffile
            with tifffile.TiffFile(path) as tf:
                page = tf.pages[0]
                if (len(tf.pages) == 1 and int(page.compression) in LOSSLESS_TIFF
                        and int(page.planarconfig) == 1):
                    return np.asarray(page.asarray())
        except Exception:                                   # anything tifffile cannot read goes to PIL
            pass
    return np.asarray(Image.open(path))


class Scan:
    """The scan as a uint8/uint16 RGB array at `dpi` (nominal scan resolution; the fiducial fit checks
    the measured scale against it); crops come back as float32 on a 0-255 scale.  The whole image is
    held once in its own dtype (a 4800 dpi A4 RGB uint8 scan: ~6.9 GB); nothing here makes a float copy
    of it (coarse_min works in row strips, crops and samples are local).  dpi / px_per_mm are class-level
    defaults too, for in-memory stand-ins built with Scan.__new__ (experiments/041 verifiers)."""

    dpi: float = SCAN_DPI_NOMINAL
    px_per_mm: float = PX_PER_MM_NOMINAL

    def __init__(self, path: Path, dpi: float = SCAN_DPI_NOMINAL) -> None:
        with Image.open(path) as im:                       # header only: the resolution tag
            tag = im.info.get("dpi")
        if tag and tag[0] and abs(float(tag[0]) / dpi - 1) > 0.01:
            print(f"warning: {path} carries a {float(tag[0]):.0f} dpi tag; reading it as {dpi:.0f} dpi")
        arr = read_rgb(path)
        if arr.ndim != 3 or arr.shape[2] < 3:
            raise SystemExit(f"{path}: need an RGB scan, got shape {arr.shape}")
        self.img = arr
        self.dpi = float(dpi)
        self.px_per_mm = self.dpi / 25.4
        self.scale255 = 255.0 / 65535.0 if arr.dtype == np.uint16 else 1.0
        self.h, self.w = arr.shape[:2]

    def crop(self, r0: int, r1: int, c0: int, c1: int, ch: int | None = None) -> np.ndarray:
        r0, c0 = max(r0, 0), max(c0, 0)
        r1, c1 = min(r1, self.h), min(c1, self.w)
        sl = self.img[r0:r1, c0:c1, :3] if ch is None else self.img[r0:r1, c0:c1, ch]
        return sl.astype(np.float32) * self.scale255

    def coarse_min(self, k: int) -> np.ndarray:
        H, W = (self.h // k) * k, (self.w // k) * k
        out = np.empty((H // k, W // k), np.float32)
        step = k * max(1, 2048 // k)                    # 2048 scan rows per strip (k = 8 at 2400, 16 at 4800)
        for r0 in range(0, H, step):
            r1 = min(r0 + step, H)
            m = self.img[r0:r1, :W, :3].min(axis=2).astype(np.float32) * self.scale255
            out[r0 // k:r1 // k] = m.reshape((r1 - r0) // k, k, W // k, k).mean((1, 3))
        return out


def sample_rect(scan: Scan, A: np.ndarray, xs_mm: np.ndarray, ys_mm: np.ndarray,
                order: int = 1) -> np.ndarray:
    """RGB at the mm grid (ys_mm x xs_mm) through the affine A (scan [col,row] = A @ [x,y,1]),
    as an (ny, nx, 3) float32 array."""
    X, Y = np.meshgrid(xs_mm, ys_mm)
    col = A[0, 0] * X + A[0, 1] * Y + A[0, 2]
    row = A[1, 0] * X + A[1, 1] * Y + A[1, 2]
    r0, r1 = int(np.floor(row.min())) - 2, int(np.ceil(row.max())) + 3
    c0, c1 = int(np.floor(col.min())) - 2, int(np.ceil(col.max())) + 3
    if r0 < 0 or c0 < 0 or r1 > scan.h or c1 > scan.w:
        raise ValueError("outside the scan")
    win = scan.crop(r0, r1, c0, c1)
    coords = np.stack([row - r0, col - c0])
    return np.stack([ndimage.map_coordinates(win[..., c], coords, order=order, mode="nearest")
                     for c in range(3)], -1).astype(np.float32)


# ---------------------------------------------------------------- fiducials

@dataclass(frozen=True)
class Blob:
    col: float
    row: float
    w_mm: float
    h_mm: float


def shape_ok(w_mm: float, h_mm: float, fid: dict[str, Any], tol: float = 0.2) -> bool:
    return abs(w_mm - fid["w_mm"]) < tol * fid["w_mm"] and abs(h_mm - fid["h_mm"]) < tol * fid["h_mm"]


def coarse_blobs(scan: Scan, fids: list[dict[str, Any]]) -> tuple[list[Blob], float]:
    k = coarse_k(scan.dpi)
    ds = scan.coarse_min(k)
    paper = float(np.median(ds))
    dark_level = float(np.quantile(ds, 0.0002))
    thr = 0.5 * (paper + dark_level)
    lab, n = ndimage.label(ds < thr)
    objs = ndimage.find_objects(lab)
    mm_per_ds = k / scan.px_per_mm
    blobs = []
    for i, sl in enumerate(objs):
        bh, bw = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        w_mm, h_mm = bw * mm_per_ds, bh * mm_per_ds
        if not any(shape_ok(w_mm, h_mm, f) for f in fids):
            continue
        comp = lab[sl] == i + 1
        if comp.mean() < 0.8:
            continue
        cy, cx = ndimage.center_of_mass(comp)
        blobs.append(Blob((sl[1].start + cx + 0.5) * k - 0.5,
                          (sl[0].start + cy + 0.5) * k - 0.5, w_mm, h_mm))
    return blobs, thr


def fid_centre_mm(f: dict[str, Any]) -> complex:
    return complex(f["x_mm"] + 0.5 * f["w_mm"], f["y_mm"] + 0.5 * f["h_mm"])


def similarity_search(blobs: list[Blob], fids: list[dict[str, Any]], scale_tol: float,
                      px_per_mm: float = PX_PER_MM_NOMINAL) -> tuple[complex, complex, int]:
    """Best two-point similarity mm -> scan (complex x+iy -> col+i row): (z, t, matches)."""
    P = [fid_centre_mm(f) for f in fids]
    C = [complex(b.col, b.row) for b in blobs]
    compat = [[j for j, b in enumerate(blobs) if shape_ok(b.w_mm, b.h_mm, f)] for f in fids]
    best: tuple[int, float, complex, complex] = (0, np.inf, 0j, 0j)
    tol_px = 1.5 * px_per_mm
    for i1 in range(len(fids)):
        for i2 in range(i1 + 1, len(fids)):
            for j1 in compat[i1]:
                for j2 in compat[i2]:
                    if j1 == j2:
                        continue
                    z = (C[j2] - C[j1]) / (P[i2] - P[i1])
                    if abs(abs(z) / px_per_mm - 1) > 1.5 * scale_tol:
                        continue
                    ang = abs(np.degrees(np.angle(z)))
                    if min(ang, 180 - ang) > 5:
                        continue
                    t = C[j1] - z * P[i1]
                    n, err = 0, 0.0
                    for i, p in enumerate(P):
                        q = z * p + t
                        d = min((abs(C[j] - q) for j in compat[i]), default=np.inf)
                        if d < tol_px:
                            n += 1; err += d
                    if (n, -err) > (best[0], -best[1]):
                        best = (n, err, z, t)
    if best[0] < 2:
        raise SystemExit(f"fiducials: no consistent placement among {len(blobs)} candidate blobs")
    return best[2], best[3], best[0]


def refine_fiducial(scan: Scan, q: complex, f: dict[str, Any]) -> Blob | None:
    half = int((0.5 * max(f["w_mm"], f["h_mm"]) + 1.0) * scan.px_per_mm)
    r0, c0 = int(q.imag) - half, int(q.real) - half
    if r0 < 0 or c0 < 0 or r0 + 2 * half > scan.h or c0 + 2 * half > scan.w:
        return None
    v = scan.crop(r0, r0 + 2 * half, c0, c0 + 2 * half).min(axis=2)
    lo, hi = np.quantile(v, 0.02), np.quantile(v, 0.98)
    lab, n = ndimage.label(v < 0.5 * (lo + hi))
    if n == 0:
        return None
    cy, cx = int(q.imag) - r0, int(q.real) - c0
    k = lab[cy, cx]
    if k == 0:
        coms = ndimage.center_of_mass(lab > 0, lab, range(1, n + 1))
        k = 1 + int(np.argmin([np.hypot(a - cy, b - cx) for a, b in coms]))
    comp = lab == k
    rows, cols = np.nonzero(comp)
    w_mm = (cols.max() - cols.min() + 1) / scan.px_per_mm
    h_mm = (rows.max() - rows.min() + 1) / scan.px_per_mm
    if not shape_ok(w_mm, h_mm, f):
        return None
    return Blob(c0 + float(cols.mean()), r0 + float(rows.mean()), w_mm, h_mm)


def fit_page(scan: Scan, man: dict[str, Any], max_resid_mm: float,
             scale_tol: float) -> tuple[np.ndarray, dict[str, Any]]:
    fids = man["fiducials"]
    blobs, thr = coarse_blobs(scan, fids)
    z, t, n_coarse = similarity_search(blobs, fids, scale_tol, scan.px_per_mm)
    found = []
    for f in fids:
        b = refine_fiducial(scan, z * fid_centre_mm(f) + t, f)
        if b is not None:
            found.append((f, b))
    if len(found) < 4:
        raise SystemExit(f"fiducials: only {len(found)} of {len(fids)} refined; refusing")
    src = np.array([[fid_centre_mm(f).real, fid_centre_mm(f).imag, 1.0] for f, _ in found])
    dst = np.array([[b.col, b.row] for _, b in found])
    M, *_ = np.linalg.lstsq(src, dst, rcond=None)
    A = M.T                                                     # (2, 3): [col, row] = A @ [x, y, 1]
    lin = A[:, :2]
    sv = np.linalg.svd(lin, compute_uv=False)
    scale = sv / scan.px_per_mm
    rot = float(np.degrees(np.arctan2(lin[1, 0] - lin[0, 1], lin[0, 0] + lin[1, 1])))
    resid = np.hypot(*(src @ M - dst).T) / sv.mean()
    info = {"coarse_threshold": thr, "candidate_blobs": len(blobs), "coarse_matches": n_coarse,
            "fiducials_found": [f["id"] for f, _ in found],
            "fiducials_missing": [f["id"] for f in fids if f not in [g for g, _ in found]],
            "fiducial_scan_px": {f["id"]: [round(b.col, 2), round(b.row, 2)] for f, b in found},
            "residual_mm": {f["id"]: round(float(r), 4) for (f, _), r in zip(found, resid)},
            "scale_rel": [round(float(s), 5) for s in scale], "rotation_deg": round(rot, 4),
            "px_per_mm": round(float(sv.mean()), 4), "affine_mm_to_colrow": A.round(6).tolist()}
    orient = "as-is" if abs(rot) < 3 else "rot180" if abs(abs(rot) - 180) < 3 else None
    info["orientation"] = orient
    per_fid = ", ".join(f"{k} {v:.3f}" for k, v in info["residual_mm"].items())
    print(f"fiducials: {len(found)}/{len(fids)} found ({len(blobs)} coarse candidates), "
          f"orientation {orient}, rotation {rot:+.3f} deg, scale {scale[0]:.4f}/{scale[1]:.4f}, "
          f"residual max {resid.max():.3f} mm ({per_fid})")
    if np.linalg.det(lin) <= 0:
        raise SystemExit("fiducials: mirrored fit; refusing")
    if orient is None:
        raise SystemExit(f"fiducials: rotation {rot:.2f} deg is neither as-is nor rot180; refusing")
    if np.any(np.abs(scale - 1) > scale_tol):
        raise SystemExit(f"fiducials: scale {scale} off nominal by more than {scale_tol}; refusing")
    if resid.max() > max_resid_mm:
        raise SystemExit(f"fiducials: residual {resid.max():.3f} mm > {max_resid_mm} mm; refusing")
    return A, info


# ---------------------------------------------------------------- page white

def outside(xs: np.ndarray, ys: np.ndarray, rects: list[tuple[float, float, float, float]],
            pad_mm: float) -> np.ndarray:
    ok = np.ones(xs.shape, bool)
    for x0, y0, x1, y1 in rects:
        ok &= ~((xs > x0 - pad_mm) & (xs < x1 + pad_mm) & (ys > y0 - pad_mm) & (ys < y1 + pad_mm))
    return ok


def sample_points(scan: Scan, A: np.ndarray, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
    col = np.round(A[0, 0] * xs + A[0, 1] * ys + A[0, 2]).astype(int)
    row = np.round(A[1, 0] * xs + A[1, 1] * ys + A[1, 2]).astype(int)
    ok = (row >= 0) & (row < scan.h) & (col >= 0) & (col < scan.w)
    return scan.img[row[ok], col[ok], :3].astype(np.float32) * scan.scale255


def page_white(scan: Scan, A: np.ndarray, man: dict[str, Any],
               rects: list[tuple[float, float, float, float]]) -> np.ndarray:
    W, H = man["page_mm"]
    X, Y = np.meshgrid(np.arange(5.0, W - 5.0, 0.5), np.arange(5.0, H - 5.0, 0.5))
    ok = outside(X, Y, rects, 0.5)
    v = sample_points(scan, A, X[ok], Y[ok])
    if len(v) == 0:
        raise SystemExit("page white: no gap sample on the scan")
    return np.median(v, axis=0)


def local_white(scan: Scan, A: np.ndarray, rect: tuple[float, float, float, float],
                rects: list[tuple[float, float, float, float]], fallback: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = rect
    X, Y = np.meshgrid(np.arange(x0 - 0.9, x1 + 0.9, 0.04), np.arange(y0 - 0.9, y1 + 0.9, 0.04))
    ring = ~((X > x0 - 0.4) & (X < x1 + 0.4) & (Y > y0 - 0.4) & (Y < y1 + 0.4))
    others = [r for r in rects if r != rect]
    ok = ring & outside(X, Y, others, 0.3)
    v = sample_points(scan, A, X[ok], Y[ok])
    return np.median(v, axis=0) if len(v) >= 50 else fallback


# ---------------------------------------------------------------- per patch

def cell_samples(rect_img: np.ndarray, oy: float, ox: float, cells: int, cell_px: int,
                 box: int | None = None) -> np.ndarray:
    """(cells, cells, 3) mean of a `box` px box at every cell centre (default cell_px/2, the cell's core;
    cell_px = the whole cell, for composite cells whose levels live at the cell's edges); offsets in
    rectified px."""
    box = cell_px // 2 if box is None else box
    filt = np.stack([ndimage.uniform_filter(rect_img[..., c], size=box, mode="nearest")
                     for c in range(3)], -1)
    # a size-`box` uniform filter at index j averages j - box//2 .. j + (box-1)//2: centre j - 0.5
    # for an even box
    centre = (np.arange(cells) * cell_px) + 0.5 * cell_px - 0.5 + (0.5 if box % 2 == 0 else 0.0)
    ys, xs = np.meshgrid(oy + centre, ox + centre, indexing="ij")
    coords = np.stack([ys, xs])
    return np.stack([ndimage.map_coordinates(filt[..., c], coords, order=1, mode="nearest")
                     for c in range(3)], -1)


def channel_stats(vals: np.ndarray, ink: np.ndarray) -> dict[str, float]:
    vi, vb = vals[ink], vals[~ink]
    mu_i, mu_b = float(vi.mean()), float(vb.mean())
    sd = float(np.sqrt(0.5 * (vi.var() + vb.var())))
    d = (mu_b - mu_i) / sd if sd > 1e-6 else (np.inf if mu_b > mu_i else 0.0)
    thr = 0.5 * (mu_i + mu_b)
    pred_ink = vals < thr if mu_i <= mu_b else vals > thr
    return {"inked": mu_i, "blank": mu_b, "dprime": float(d), "hard_err": float((pred_ink != ink).mean())}


def annulus_ratio(g: np.ndarray, mask: np.ndarray) -> float:
    g = g - g.mean()
    if g.std() < 0.5:                                   # a flat window has no spectrum to rank
        return float("nan")
    n = g.shape[0]
    hann = np.outer(np.hanning(n), np.hanning(n))
    ann = (np.abs(np.fft.fftshift(np.fft.fft2(g * hann))) ** 2)[mask]
    return float(ann.max() / (np.median(ann) + 1e-9))


def lattice_ratio(scan: Scan, A: np.ndarray, cx_mm: float, cy_mm: float, own: tuple[int, ...],
                  dpi: float, seed: int) -> tuple[float, float]:
    """(ratio, scrambled-control ratio): e041_screen_fine's number on the window, and on the same
    window's pixels shuffled (seeded), its no-structure floor."""
    col = A[0, 0] * cx_mm + A[0, 1] * cy_mm + A[0, 2]
    row = A[1, 0] * cx_mm + A[1, 1] * cy_mm + A[1, 2]
    n = LATTICE_WINDOW_PX
    r0, c0 = int(round(row)) - n // 2, int(round(col)) - n // 2
    win = scan.crop(r0, r0 + n, c0, c0 + n)
    if win.shape[:2] != (n, n):
        return float("nan"), float("nan")
    g = win[..., list(own or (0, 1, 2))].mean(axis=2)
    mask = annulus_mask(n, dpi, LATTICE_LPI[0], LATTICE_LPI[1], LATTICE_AXIS_DEG)
    shuffled = np.random.default_rng(seed).permutation(g.ravel()).reshape(n, n)
    return annulus_ratio(g, mask), annulus_ratio(shuffled, mask)


def read_patch(scan: Scan, A: np.ndarray, p: dict[str, Any], g: Geometry, white: np.ndarray,
               dpi: float) -> dict[str, Any]:
    pat = checked_pattern(p, g.cells)
    ink = pat.astype(bool)
    own = OWN[p["target"]]
    step = g.dot_mm / SUB_PX_PER_DOT
    cell_px = g.cell_dots * SUB_PX_PER_DOT
    n_pat = g.pattern_dots * SUB_PX_PER_DOT
    x0, y0 = float(p["x_mm"]), float(p["y_mm"])
    # solid bar interior
    bx = np.arange(x0 + SOLID_ERODE_MM, x0 + g.pattern_dots * g.dot_mm - SOLID_ERODE_MM, step)
    by0 = y0 + g.pattern_dots * g.dot_mm
    by = np.arange(by0 + SOLID_ERODE_MM, by0 + g.solid_dots * g.dot_mm - SOLID_ERODE_MM, step)
    solid = sample_rect(scan, A, bx, by, order=0).reshape(-1, 3)
    # pattern square, page-aligned at SUB_PX_PER_DOT px per dot; sample k sits at mm x0 - margin + k*step
    m_px = int(round(PATTERN_MARGIN_MM / step))
    s_px = int(round(SEARCH_MM / step))
    k = np.arange(n_pat + 2 * m_px)
    rect = sample_rect(scan, A, x0 + (k - m_px) * step, y0 + (k - m_px) * step)
    reg_ok = bool(own)
    oy = ox = float(m_px)
    peak = float("nan")
    if own:
        tmpl = np.kron(pat.astype(np.float32), np.ones((cell_px, cell_px), np.float32))
        sub = 255.0 - rect[m_px - s_px:, m_px - s_px:, list(own)].mean(axis=2)
        dy, dx, peak = xcorr_shift(sub, tmpl, s_px)
        if peak >= REG_MIN_PEAK:
            oy, ox = m_px - s_px + dy, m_px - s_px + dx
        else:
            reg_ok = False
    vals = cell_samples(rect, oy, ox, g.cells, cell_px)
    row: dict[str, Any] = {"id": p["id"], "x_mm": x0, "y_mm": y0, "rgb": list(p["rgb"]),
                           "method": p["method"], "kind": p["kind"], "target": p["target"], "seed": p["seed"],
                           "solid": solid.mean(0).tolist(), "solid_sd": solid.std(0).tolist(),
                           "white": white.tolist(), "reg_ok": reg_ok, "reg_peak": peak,
                           "reg_dy_mm": (oy - m_px) * step, "reg_dx_mm": (ox - m_px) * step}
    stats = [channel_stats(vals[..., c], ink) for c in range(3)]
    row["channels"] = {CHANNELS[c]: stats[c] for c in range(3)}
    foreign = [c for c in range(3) if c not in own]
    row["contam"] = {CHANNELS[c]: {"blank": float(white[c] - stats[c]["blank"]),
                                   "inked": float(white[c] - stats[c]["inked"])} for c in foreign}
    row["contam_blank_max"] = max((row["contam"][CHANNELS[c]]["blank"] for c in foreign), default=0.0)
    row["contam_inked_max"] = max((row["contam"][CHANNELS[c]]["inked"] for c in foreign), default=0.0)
    row["own_dprime"] = min((stats[c]["dprime"] for c in own), default=float("nan"))
    row["own_hard_err"] = max((stats[c]["hard_err"] for c in own), default=float("nan"))
    row["ink_darkening_max"] = max(float(white[c] - stats[c]["inked"]) for c in range(3))
    centre = 0.5 * g.pattern_dots * g.dot_mm
    row["lattice"], row["lattice_ctrl"] = lattice_ratio(scan, A, x0 + centre, y0 + centre, own, dpi,
                                                        int(p["seed"]))
    return row


# ---------------------------------------------------------------- outputs

def csv_rows(rows: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    head = ["id", "x_mm", "y_mm", "r", "g", "b", "method", "kind", "target", "solid_R", "solid_G", "solid_B"]
    for ch in CHANNELS:
        head += [f"{ch}_inked", f"{ch}_blank", f"{ch}_dprime", f"{ch}_hard_err"]
    head += ["own_dprime", "own_hard_err"]
    head += [f"contam_{w}_{ch}" for ch in CHANNELS for w in ("blank", "inked")]
    head += ["contam_blank_max", "contam_inked_max", "lattice", "lattice_ctrl",
             "white_R", "white_G", "white_B",
             "reg_ok", "reg_peak", "reg_dx_mm", "reg_dy_mm"]
    out = []
    for r in rows:
        line: list[Any] = [r["id"], f"{r['x_mm']:.4f}", f"{r['y_mm']:.4f}", *r["rgb"], r["method"], r["kind"],
                           r["target"], *(f"{v:.2f}" for v in r["solid"])]
        for ch in CHANNELS:
            s = r["channels"][ch]
            line += [f"{s['inked']:.2f}", f"{s['blank']:.2f}", f"{s['dprime']:.3f}", f"{s['hard_err']:.4f}"]
        line += [f"{r['own_dprime']:.3f}", f"{r['own_hard_err']:.4f}"]
        for ch in CHANNELS:
            c = r["contam"].get(ch)
            line += [f"{c['blank']:.2f}", f"{c['inked']:.2f}"] if c else ["", ""]
        line += [f"{r['contam_blank_max']:.2f}", f"{r['contam_inked_max']:.2f}",
                 f"{r['lattice']:.2f}", f"{r['lattice_ctrl']:.2f}",
                 *(f"{v:.2f}" for v in r["white"]), int(r["reg_ok"]), f"{r['reg_peak']:.3f}",
                 f"{r['reg_dx_mm']:+.4f}", f"{r['reg_dy_mm']:+.4f}"]
        out.append(line)
    return head, out


def rank_key(r: dict[str, Any]) -> float:
    if r["target"] == "W":
        return r["ink_darkening_max"]
    d = r["own_dprime"]
    return -d if np.isfinite(d) else (-1e9 if d > 0 else 1e9)


def fmt_row(r: dict[str, Any]) -> str:
    rgb = ",".join(f"{v:3d}" for v in r["rgb"])
    return (f"    {r['id']:>5} ({rgb}) {r['kind']:12s} d' {r['own_dprime']:7.2f}  err {r['own_hard_err']:.3f}"
            f"  lattice {r['lattice']:5.1f} (ctrl {r['lattice_ctrl']:4.1f})"
            f"  contam ink {r['contam_inked_max']:6.1f}"
            f" blank {r['contam_blank_max']:6.1f}"
            f"  dark {r['ink_darkening_max']:6.1f}  solid " + ",".join(f"{v:5.1f}" for v in r["solid"])
            + ("" if r["reg_ok"] or r["target"] == "W" else "  REG-NOMINAL"))


def ranking(rows: list[dict[str, Any]], top: int) -> dict[str, dict[str, dict[str, list[Any]]]]:
    """Rank per (target, method, kind); kinds in manifest order (any kind string the manifest carries)."""
    methods = list(dict.fromkeys(r["method"] for r in rows))
    kinds = list(dict.fromkeys(r["kind"] for r in rows))
    out: dict[str, dict[str, dict[str, list[Any]]]] = {}
    for tgt in TARGET_ORDER:
        for meth in methods:
            for kind in kinds:
                grp = sorted((r for r in rows if (r["target"], r["method"], r["kind"]) == (tgt, meth, kind)),
                             key=rank_key)
                if not grp:
                    continue
                print(f"\n{tgt} / {meth} / {kind}: {len(grp)} patches"
                      + (" (ranked by least ink darkening)" if tgt == "W" else " (ranked by own-channel d')"))
                for r in grp[:top]:
                    print(fmt_row(r))
                anchors = [r for r in grp if tuple(r["rgb"]) == CORNER_RGB[tgt]]
                if anchors:
                    pos = grp.index(anchors[0]) + 1
                    print(f"  corner anchor (rank {pos}):\n" + fmt_row(anchors[0]))
                out.setdefault(tgt, {}).setdefault(meth, {})[kind] = [r["id"] for r in grp]
    return out


def jsonable(x: Any) -> Any:
    if isinstance(x, float):
        return x if np.isfinite(x) else None
    if isinstance(x, dict):
        return {k: jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, np.generic):
        return jsonable(x.item())
    return x


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", required=True, help="2400 dpi RGB TIFF of the printed probe sheet")
    ap.add_argument("--manifest", required=True, help="the generator's S10p manifest JSON")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--tag", default=None, help="output file prefix (default: the manifest's tag)")
    ap.add_argument("--max-resid-mm", type=float, default=0.3, help="refuse above this fiducial residual")
    ap.add_argument("--scale-tol", type=float, default=0.01, help="allowed relative scale error vs 2400 dpi")
    ap.add_argument("--top", type=int, default=8, help="rows per ranking group")
    args = ap.parse_args()
    man = load_manifest(Path(args.manifest))
    g = geometry(man)
    tag = args.tag or man["tag"]
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    scan = Scan(Path(args.scan))
    print(f"{tag}: scan {scan.w} x {scan.h} px, {len(man['patches'])} patches, "
          f"{len(man['fiducials'])} fiducials")
    A, fit = fit_page(scan, man, args.max_resid_mm, args.scale_tol)
    dpi = fit["px_per_mm"] * 25.4
    rects = footprints_mm(man, g)
    gwhite = page_white(scan, A, man, rects)
    print(f"page white (gap median) R {gwhite[0]:.1f} G {gwhite[1]:.1f} B {gwhite[2]:.1f}")
    rows = []
    pw = g.pattern_dots * g.dot_mm
    ph = (g.pattern_dots + g.solid_dots) * g.dot_mm
    for p in man["patches"]:
        rect = (p["x_mm"], p["y_mm"], p["x_mm"] + pw, p["y_mm"] + ph)
        try:
            white = local_white(scan, A, rect, rects, gwhite)
            rows.append(read_patch(scan, A, p, g, white, dpi))
        except ValueError as exc:
            print(f"  patch {p['id']}: skipped ({exc})")
    head, lines = csv_rows(rows)
    with open(out / f"{tag}-patches.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(head); w.writerows(lines)
    print(f"\n{len(rows)} patches read; registration fell back to nominal on "
          f"{sum(1 for r in rows if not r['reg_ok'] and r['target'] != 'W')}")
    order = ranking(rows, args.top)
    summary = {"tag": tag, "scan": str(args.scan), "manifest": str(args.manifest),
               "job_sha256": man.get("sha256"), "job_bytes": man.get("bytes"), "fit": fit,
               "page_white": gwhite.tolist(), "n_patches_read": len(rows),
               "ranking_rule": "within each (target, method, kind) group: own-channel d' (min over own "
                               "channels) "
                               "descending; W by largest ink darkening ascending; lattice and contamination "
                               "shown, not folded in",
               "ranking": order, "patches": rows}
    (out / f"{tag}-summary.json").write_text(json.dumps(jsonable(summary), indent=1))
    print(f"\nwrote {out / (tag + '-patches.csv')} and {out / (tag + '-summary.json')}")


if __name__ == "__main__":
    main()
