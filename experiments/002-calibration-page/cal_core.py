"""cal_core — analyzer foundation for experiment 002 (CAL-1 page, real scans).

Core services shared by the five family analyzers (structural, density/color,
modulation, transport, meta). Families NEVER hand-roll registration or
resampling: everything goes through `register` + `patch_view`/`warp_channel`.
The frozen API is documented in ANALYZER-CONTRACT.md next to this file.

Coordinate conventions (normative):
- "layout dots": the 600-dpi generator grid of calpage_manifest.json, origin at
  the page top-left, x right, y down. All manifest x_dots/y_dots/w_dots/h_dots
  are in this frame.
- "scan px": pixel coordinates of the ORIENTED scan arrays (after `register`
  has applied rot90/mirror so the page is upright), x right, y down, array
  indexing [y, x].
- affine coef = np.array([a, b, c, d, e, f]):
      sx = a*x_dots + b*y_dots + c ;  sy = d*x_dots + e*y_dots + f
  (same convention as experiments/001-engine-characterization/scanlab.py).
- resampled rasters (warp_channel / patch_view): pixel [i, j] samples layout
  position (x0_dots + j/sub, y0_dots + i/sub) — corner-aligned, exactly like
  scanlab.warp_dots. Ink is DARK (low values) in every channel.

Reuse & attribution:
- scanlab.py (experiment 001) is imported via a documented sys.path insert and
  is the source of the proven decode machinery (decode_cells v4, xcorr_offset,
  residual_y_profile, detect_steps, level_fields, fit_gmm_z, llr_field).
  `levels` and the warp resampler are re-implemented here (warp needed channel
  selection + float32 output + sub-dot offsets; levels is 3 lines).
- gen_calpage.py (same directory) is imported for the byte-identical mark and
  pattern builders (corner_mark, plus_mark, quad_cross, stripes, ...), used as
  registration templates and `nominal_bits` reconstruction.

Determinism: cal_core uses NO randomness at all. (Any future stochastic step
must flow from paperholo.modulation.rng(seed, label) per CLAUDE.md.)
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.ndimage import map_coordinates

Image.MAX_IMAGE_PIXELS = None

_HERE = Path(__file__).resolve().parent
_SCANLAB_DIR = _HERE.parent / "001-engine-characterization"
for _p in (str(_HERE), str(_SCANLAB_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import gen_calpage  # noqa: E402  (pattern builders; import has no side effects)
import scanlab  # noqa: E402      (proven exp-001 decode/registration primitives)

# Re-exported proven primitives (families import them FROM cal_core so the
# provenance stays single-sourced):
xcorr_offset = scanlab.xcorr_offset
level_fields = scanlab.level_fields
fit_gmm_z = scanlab.fit_gmm_z
llr_field = scanlab.llr_field
residual_y_profile = scanlab.residual_y_profile
detect_steps = scanlab.detect_steps

SCAN_DPI = 1200
HW_DPI = 600
PX_PER_DOT = SCAN_DPI / HW_DPI  # nominal; measured value comes from register()
BUILD = _HERE / "build"
MANIFEST_PATH = BUILD / "calpage_manifest.json"

# registration channel per plane: the channel in which that ink is darkest.
REG_CHANNEL_FOR_PLANE = {"K": "grey", "C": "r", "M": "g", "Y": "b"}

# kinds whose printed bitmap is periodic (GT xcorr would lock to a wrong
# period multiple) -> local refinement falls back to the patch footprint.
PERIODIC_KINDS = frozenset({
    "lines", "checker", "dots", "holes", "nyquist_comb", "dot_grid_1dot",
    "lines_1dot", "phase_pair", "phase_grating", "raster_probe_imagemask",
})
# kinds with no reconstructible bitmap but a solid-ish footprint to lock on.
FOOTPRINT_KINDS = frozenset({
    "solid", "overlay_solid", "contone_setgray", "raster_probe_rectfill",
})


class RegistrationError(RuntimeError):
    """Global registration could not be established — NO downstream number is valid."""


# ---------------------------------------------------------------------------
# 1. scan loading
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def levels(a: np.ndarray) -> tuple[float, float, float]:
    """(white, black, midpoint threshold) from robust percentiles.

    Same definition as scanlab.levels (p90 / p1); re-stated here so families
    have one import point.
    """
    white = float(np.percentile(a, 90))
    black = float(np.percentile(a, 1))
    return white, black, (white + black) / 2


def load_scan(path: str | Path, *, compute_sha256: bool = True) -> dict:
    """Load a 1200-dpi scan (grey or color) into the shared scan dict.

    Returns dict with keys:
      path, sha256 (or None), kind ('grey'|'color'),
      grey        float32 (H, W)  — luma for color scans, ink dark,
      channels    {'grey': <same array>} plus {'r','g','b': uint8} when color,
      white, black, thresh  — robust global grey levels,
      scan_dpi=1200, hw_dpi=600, px_per_dot=2.0 (nominal).
    register() later adds: orientation, affine, registration, manifest.
    """
    p = Path(path)
    sha = _sha256_file(p) if compute_sha256 else None
    img = Image.open(p)
    if img.mode in ("L", "LA", "I", "I;16"):
        grey = np.asarray(img.convert("L"), dtype=np.float32)
        channels: dict[str, np.ndarray] = {"grey": grey}
        kind = "grey"
    else:
        rgb = np.asarray(img.convert("RGB"))
        r = np.ascontiguousarray(rgb[..., 0])
        g = np.ascontiguousarray(rgb[..., 1])
        b = np.ascontiguousarray(rgb[..., 2])
        del rgb
        grey = (0.299 * r.astype(np.float32) + 0.587 * g.astype(np.float32)
                + 0.114 * b.astype(np.float32))
        channels = {"grey": grey, "r": r, "g": g, "b": b}
        kind = "color"
    white, black, thresh = levels(grey)
    return {
        "path": str(p), "sha256": sha, "kind": kind,
        "grey": grey, "channels": channels,
        "white": white, "black": black, "thresh": thresh,
        "scan_dpi": SCAN_DPI, "hw_dpi": HW_DPI, "px_per_dot": PX_PER_DOT,
        "orientation": None, "affine": None, "registration": None,
        "manifest": None,
    }


def load_manifest(path: str | Path = MANIFEST_PATH) -> dict:
    """Load a page manifest, recording where its ground-truth files live.

    Manifest `gt` / `*_gt` paths are relative to the manifest's own build
    directory. Historically that was assumed to be cc.BUILD (exp 002); other
    experiments (003+) reuse cal_core with manifests in THEIR build dirs, so
    the manifest and every patch/infrastructure entry get a `_base_dir` tag
    here. load_gt/load_gt_named resolve against it, defaulting to BUILD —
    existing 002 flows are unchanged (their base dir IS BUILD).
    """
    p = Path(path)
    mf = json.loads(p.read_text())
    base = str(p.resolve().parent)
    mf["_base_dir"] = base
    for lst in ("patches", "infrastructure"):
        for e in mf.get(lst) or []:
            if isinstance(e, dict):
                e.setdefault("_base_dir", base)
    return mf


def entry(manifest: dict, name: str) -> dict:
    """Manifest entry (patch or infrastructure) by exact name. KeyError if absent."""
    for e in manifest["patches"]:
        if e["name"] == name:
            return e
    for e in manifest["infrastructure"]:
        if e["name"] == name:
            return e
    raise KeyError(f"no manifest entry named {name!r}")


# ---------------------------------------------------------------------------
# 2. orientation + global registration
# ---------------------------------------------------------------------------

_DS = 4  # downsample factor for corner-mark hunting


def _block_mean(a: np.ndarray, f: int) -> np.ndarray:
    h, w = a.shape[0] // f, a.shape[1] // f
    return a[: h * f, : w * f].reshape(h, f, w, f).mean(axis=(1, 3), dtype=np.float32)


def _orient_array(a: np.ndarray, rot90_ccw: int, mirrored: bool) -> np.ndarray:
    """Normative orientation op: mirror (fliplr) FIRST, then np.rot90(k)."""
    if mirrored:
        a = np.fliplr(a)
    if rot90_ccw % 4:
        a = np.rot90(a, rot90_ccw % 4)
    return a


def _detect_corners_in_ds(ds: np.ndarray) -> list[dict]:
    """Chiral corner marks in a x4-downsampled grey image.

    A corner mark is a 123-dot cross (3-dot strokes) + n in 1..4 satellite
    8x8-dot squares along the inward diagonal (gen_calpage.corner_mark).
    Returns [{'n_sat', 'x_px', 'y_px', 'inward', 'crossness'}] in full-res px.
    """
    white = float(np.percentile(ds, 90))
    black = float(np.percentile(ds, 1))
    thr = white - 0.4 * (white - black)
    lbl, _ = ndimage.label(ds < thr)
    slices = ndimage.find_objects(lbl)
    nominal = 123 * PX_PER_DOT / _DS  # ~61.5 ds px
    lo, hi = 0.7 * nominal, 1.4 * nominal
    found: dict[int, dict] = {}
    for i, s in enumerate(slices):
        if s is None:
            continue
        hh, ww = s[0].stop - s[0].start, s[1].stop - s[1].start
        if not (lo <= hh <= hi and lo <= ww <= hi):
            continue
        m = lbl[s] == (i + 1)
        fill = float(m.mean())
        if not (0.03 <= fill <= 0.15):
            continue
        y0, x0 = s[0].start, s[1].start
        cyl = int(np.argmax(m.sum(axis=1)))   # horizontal stroke row (local)
        cxl = int(np.argmax(m.sum(axis=0)))   # vertical stroke col (local)
        band = 3
        yy, xx = np.nonzero(m)
        crossness = float(np.mean((np.abs(yy - cyl) <= band) | (np.abs(xx - cxl) <= band)))
        if crossness < 0.7:
            continue
        cy, cx = y0 + cyl, x0 + cxl
        # satellites: separate small blobs inside the (expanded) bbox
        Y0, Y1 = max(0, y0 - 5), min(ds.shape[0], s[0].stop + 5)
        X0, X1 = max(0, x0 - 5), min(ds.shape[1], s[1].stop + 5)
        sub = lbl[Y0:Y1, X0:X1]
        n_sat, dys, dxs = 0, [], []
        for j in np.unique(sub):
            if j in (0, i + 1):
                continue
            mm = sub == j
            ys, xs = np.nonzero(mm)
            bh, bw = int(np.ptp(ys)) + 1, int(np.ptp(xs)) + 1
            if not (1 <= bh <= 8 and 1 <= bw <= 8 and mm.sum() >= 3):
                continue
            dy, dx = float(ys.mean() + Y0 - cy), float(xs.mean() + X0 - cx)
            if 4 <= math.hypot(dy, dx) <= 40:
                n_sat += 1
                dys.append(dy)
                dxs.append(dx)
        if not (1 <= n_sat <= 4):
            continue
        cand = {
            "n_sat": n_sat,
            "x_px": (cx + 0.5) * _DS, "y_px": (cy + 0.5) * _DS,
            "inward": (int(np.sign(np.mean(dys))), int(np.sign(np.mean(dxs)))),
            "crossness": crossness,
        }
        if n_sat not in found or crossness > found[n_sat]["crossness"]:
            found[n_sat] = cand
    return [found[k] for k in sorted(found)]


def _fit_affine(pts_dots: np.ndarray, pts_px: np.ndarray) -> tuple[np.ndarray, float]:
    """LSQ affine layout-dots -> scan-px. Returns (coef[a..f], rms_px)."""
    n = len(pts_dots)
    A = np.zeros((2 * n, 6))
    v = np.zeros(2 * n)
    for i, (px_, py_) in enumerate(pts_dots):
        A[2 * i, :3] = (px_, py_, 1.0)
        A[2 * i + 1, 3:] = (px_, py_, 1.0)
        v[2 * i], v[2 * i + 1] = pts_px[i]
    coef, *_ = np.linalg.lstsq(A, v, rcond=None)
    rms = float(np.sqrt(np.mean((A @ coef - v) ** 2)))
    return coef, rms


def affine_apply(coef: np.ndarray, xy_dots: np.ndarray) -> np.ndarray:
    """(N,2) or (2,) layout-dot points -> scan px."""
    p = np.atleast_2d(np.asarray(xy_dots, float))
    a, b, c, d, e, f = coef
    out = np.column_stack([a * p[:, 0] + b * p[:, 1] + c,
                           d * p[:, 0] + e * p[:, 1] + f])
    return out[0] if np.ndim(xy_dots) == 1 else out


def affine_invert(coef: np.ndarray) -> np.ndarray:
    """Inverse affine (scan px -> layout dots), same [a..f] convention."""
    a, b, c, d, e, f = coef
    M = np.array([[a, b], [d, e]])
    Mi = np.linalg.inv(M)
    ci, fi = -Mi @ np.array([c, f])
    return np.array([Mi[0, 0], Mi[0, 1], ci, Mi[1, 0], Mi[1, 1], fi])


def affine_stats(coef: np.ndarray) -> dict:
    """px/dot scales, rotation, shear, mirror flag derived from the linear part."""
    a, b, c, d, e, f = coef
    sx = math.hypot(a, d)
    sy = math.hypot(b, e)
    rot = math.degrees(math.atan2(d, a))
    det = a * e - b * d
    shear = math.degrees(math.atan2(a * b + d * e, sx * sy))  # 0 if orthogonal
    return {"px_per_dot_x": sx, "px_per_dot_y": sy, "rotation_deg": rot,
            "shear_deg": shear, "mirrored": bool(det < 0)}


def warp_channel(scan: dict, channel: str, x0_dots: float, y0_dots: float,
                 w_dots: int, h_dots: int, *, coef: np.ndarray | None = None,
                 sub: int = 2, offset_dots: tuple[float, float] = (0.0, 0.0)
                 ) -> np.ndarray:
    """Resample one scan channel onto the layout-dot grid (float32, ink dark).

    Adapted from scanlab.warp_dots (attribution: experiment 001) with channel
    selection, float32 output from uint8 sources, and a sub-dot sampling
    offset (dy_dots, dx_dots) used by local refinement: sampling happens at
    layout position + offset.
    Pixel [i, j] samples (x0_dots + j/sub + dx, y0_dots + i/sub + dy).
    """
    if coef is None:
        coef = scan["affine"]
    if coef is None:
        raise RegistrationError("scan is not registered — call register() first")
    a, b, c, d, e, f = coef
    gy, gx = np.mgrid[0: int(h_dots * sub), 0: int(w_dots * sub)]
    px = x0_dots + gx / sub + offset_dots[1]
    py = y0_dots + gy / sub + offset_dots[0]
    return map_coordinates(scan["channels"][channel], [d * px + e * py + f,
                                                       a * px + b * py + c],
                           order=1, mode="nearest", output=np.float32)


def _landmark_defs(manifest: dict, use_quads: bool = True) -> list[dict]:
    """Registration landmarks: 4 corner marks, plus-mark lattice, K reg-quads."""
    out = []
    for p in manifest["patches"]:
        if p["kind"] == "corner_mark":
            bits = gen_calpage.corner_mark(p["params"]["satellites"],
                                           tuple(p["params"]["inward"]))
            cls = "corner"
        elif p["kind"] == "plus_mark":
            bits, cls = gen_calpage.plus_mark(), "plus"
        elif use_quads and p["kind"] == "reg_cross" and p["name"].endswith("_K"):
            bits, cls = gen_calpage.quad_cross(), "quad"
        else:
            continue
        out.append({"name": p["name"], "class": cls, "bits": bits,
                    "x": p["x_dots"], "y": p["y_dots"]})
    return out


def _measure_landmarks(scan: dict, coef: np.ndarray, lms: list[dict], *,
                       sub: int = 2, margin_dots: int = 14,
                       max_shift_dots: float = 10.0, min_q: float = 0.03
                       ) -> list[dict]:
    """Template-xcorr each landmark against the grey channel under `coef`.

    Adds to each landmark dict: dy_dots, dx_dots (mark sits at layout+offset in
    the coef frame), q, ok.
    """
    out = []
    for lm in lms:
        h, w = lm["bits"].shape
        m = margin_dots
        win = warp_channel(scan, "grey", lm["x"] - m, lm["y"] - m,
                           w + 2 * m, h + 2 * m, coef=coef, sub=sub)
        canvas = np.zeros((h + 2 * m, w + 2 * m), np.float32)
        canvas[m: m + h, m: m + w] = lm["bits"]
        tpl = np.kron(1.0 - canvas, np.ones((sub, sub), np.float32)) * 255.0
        dy, dx, q = xcorr_offset(win, tpl, max_shift=int(max_shift_dots * sub))
        dy_d, dx_d = dy / sub, dx / sub
        ok = (q >= min_q and abs(dy_d) < max_shift_dots - 0.5
              and abs(dx_d) < max_shift_dots - 0.5)
        out.append({**{k: lm[k] for k in ("name", "class", "x", "y")},
                    "w": w, "h": h, "dy_dots": float(dy_d),
                    "dx_dots": float(dx_d), "q": float(q), "ok": bool(ok)})
    return out


def register(scan: dict, manifest: dict | None = None, *, refine: bool = True,
             use_quads: bool = True) -> dict:
    """Orientation + global affine (layout dots -> scan px). Mutates `scan`.

    Steps: (1) find chiral corner marks on a x4 downsample; (2) resolve
    rotation/mirror from the satellite counts (1..4 = TL,TR,BR,BL) and
    physically reorient the scan arrays so the page is upright; (3) fit the
    affine from corner blob centers; (4) refine with template xcorr on corner
    marks + plus lattice + K registration quads (2 passes); (5) cross-check
    against the ruler baselines.

    Returns the registration report dict (also stored as scan['registration']).
    Raises RegistrationError if fewer than 3 corners are found or fewer than
    6 landmarks survive refinement.
    """
    if manifest is None:
        manifest = load_manifest()
    corner_pages = {p["params"]["satellites"]: p for p in manifest["patches"]
                    if p["kind"] == "corner_mark"}

    ds = _block_mean(scan["grey"], _DS)
    det = _detect_corners_in_ds(ds)
    if len(det) < 3:
        raise RegistrationError(
            f"only {len(det)} corner marks found (need >=3 for orientation+mirror)")

    def fit_from(dets: list[dict]) -> tuple[np.ndarray, float]:
        P = np.array([[corner_pages[d["n_sat"]]["params"]["cx_dots"],
                       corner_pages[d["n_sat"]]["params"]["cy_dots"]] for d in dets])
        Q = np.array([[d["x_px"], d["y_px"]] for d in dets])
        return _fit_affine(P, Q)

    coef0, rms0 = fit_from(det)
    st = affine_stats(coef0)
    orientation = {"rot90_ccw": 0, "mirrored": False}
    if st["mirrored"] or abs(st["rotation_deg"]) > 45.0:
        # brute-force the 8 orientation hypotheses on the downsample, pick the
        # one that lands upright and unmirrored (satellite counts make the
        # correspondence unambiguous, so exactly one wins).
        best = None
        for mir in (False, True):
            for k in range(4):
                d2 = _detect_corners_in_ds(_orient_array(ds, k, mir))
                if len(d2) < 3:
                    continue
                c2, r2 = fit_from(d2)
                s2 = affine_stats(c2)
                if s2["mirrored"] or abs(s2["rotation_deg"]) > 45.0:
                    continue
                if best is None or r2 < best[0]:
                    best = (r2, k, mir)
        if best is None:
            raise RegistrationError("no orientation hypothesis fits the corner marks")
        _, k, mir = best
        orientation = {"rot90_ccw": k, "mirrored": mir}
        for name in list(scan["channels"]):
            scan["channels"][name] = np.ascontiguousarray(
                _orient_array(scan["channels"][name], k, mir))
        scan["grey"] = scan["channels"]["grey"]
        scan.pop("_f32", None)
        ds = _block_mean(scan["grey"], _DS)
        det = _detect_corners_in_ds(ds)
        if len(det) < 3:
            raise RegistrationError("corner marks lost after reorientation (bug)")
        coef0, rms0 = fit_from(det)
        st = affine_stats(coef0)
        if st["mirrored"] or abs(st["rotation_deg"]) > 45.0:
            raise RegistrationError("reorientation did not produce an upright page (bug)")
    scan["orientation"] = orientation

    # chirality cross-check: satellite inward diagonals must match the manifest
    inward_ok = all(tuple(d["inward"]) ==
                    tuple(corner_pages[d["n_sat"]]["params"]["inward"]) for d in det)

    # --- refinement passes -------------------------------------------------
    lms = _landmark_defs(manifest, use_quads=use_quads)
    coef = coef0
    meas: list[dict] = []
    if refine:
        for _pass in range(2):
            meas = _measure_landmarks(scan, coef, lms)
            good = [m for m in meas if m["ok"]]
            if len(good) < 6:
                raise RegistrationError(
                    f"only {len(good)} of {len(meas)} landmarks locked "
                    f"(qualities: {sorted(round(m['q'], 3) for m in meas)})")
            P = np.array([[m["x"] + m["w"] / 2, m["y"] + m["h"] / 2] for m in good])
            Q = affine_apply(coef, P + np.array([[m["dx_dots"], m["dy_dots"]]
                                                 for m in good]))
            coef, _ = _fit_affine(P, Q)
        # final residual measurement under the final affine
        meas = _measure_landmarks(scan, coef, lms)
        for m in meas:
            m["resid_dots"] = float(math.hypot(m["dx_dots"], m["dy_dots"]))
    st = affine_stats(coef)

    def rms_of(classes: tuple[str, ...]) -> float | None:
        r = [m["resid_dots"] for m in meas if m["ok"] and m["class"] in classes]
        return float(np.sqrt(np.mean(np.square(r)))) if r else None

    used = [m for m in meas if m["ok"]]
    reg = {
        "orientation": orientation,
        "corners_found": [{"n_sat": d["n_sat"], "x_px": d["x_px"], "y_px": d["y_px"],
                           "inward": list(d["inward"])} for d in det],
        "inward_diagonals_match": bool(inward_ok),
        "corner_blob_fit_rms_px": rms0,
        "affine": [float(v) for v in coef],
        **st,
        "n_landmarks_used": len(used),
        "n_landmarks_total": len(meas),
        "residual_rms_dots": rms_of(("corner", "plus", "quad")),
        "residual_rms_core_dots": rms_of(("corner", "plus")),  # the <3-dot gate
        "residual_max_dots": (max(m["resid_dots"] for m in used) if used else None),
        "landmarks": [{k: m[k] for k in ("name", "class", "dx_dots", "dy_dots",
                                         "q", "ok", *(("resid_dots",)
                                                      if "resid_dots" in m else ()))}
                      for m in meas],
        "ruler_check": None,
    }
    scan["affine"] = coef
    scan["manifest"] = manifest
    try:
        reg["ruler_check"] = _ruler_check(scan, coef, manifest)
    except Exception as exc:  # cross-check only — never blocks registration
        reg["ruler_check"] = {"error": repr(exc)}
    scan["registration"] = reg
    return reg


def _ruler_check(scan: dict, coef: np.ndarray, manifest: dict) -> dict:
    """Residual of the two ruler baselines vs the final affine (cross-check
    only; rulers are not part of the fit). Baselines are 3-dot bars starting
    at the manifest rect origin (gen_calpage.ps_rulers)."""
    top = entry(manifest, "ruler_top")
    band = warp_channel(scan, "grey", top["x_dots"] + 200, top["y_dots"] - 8,
                        top["w_dots"] - 400, 20, coef=coef, sub=1)
    prof = (255.0 - band).mean(axis=1)
    i = int(np.argmax(prof))
    if 0 < i < len(prof) - 1:
        den = prof[i - 1] - 2 * prof[i] + prof[i + 1]
        if abs(den) > 1e-9:
            i = i + 0.5 * (prof[i - 1] - prof[i + 1]) / den
    top_dy = float((top["y_dots"] - 8) + i + 0.5 - (top["y_dots"] + 1.5))

    left = entry(manifest, "ruler_left")
    band = warp_channel(scan, "grey", left["x_dots"] - 8, left["y_dots"] + 200,
                        20, left["h_dots"] - 400, coef=coef, sub=1)
    prof = (255.0 - band).mean(axis=0)
    j = int(np.argmax(prof))
    if 0 < j < len(prof) - 1:
        den = prof[j - 1] - 2 * prof[j] + prof[j + 1]
        if abs(den) > 1e-9:
            j = j + 0.5 * (prof[j - 1] - prof[j + 1]) / den
    left_dx = float((left["x_dots"] - 8) + j + 0.5 - (left["x_dots"] + 1.5))
    return {"top_baseline_dy_dots": top_dy, "left_baseline_dx_dots": left_dx}


# ---------------------------------------------------------------------------
# 3. patch views (families never hand-roll resampling)
# ---------------------------------------------------------------------------

@dataclass
class PatchView:
    """A patch resampled onto the layout-dot grid, optionally locally locked.

    channels[ch][i, j] samples layout position
        (x0_dots + j/sub + local_offset_dots[1],
         y0_dots + i/sub + local_offset_dots[0])
    i.e. when locked, the raster IS on the nominal dot grid (the local offset
    has already been applied to the sampling positions; you do not shift again).
    Ink is dark in every channel. x0/y0 include the margin:
    x0_dots = entry.x_dots - margin_dots.
    """
    name: str
    entry: dict
    x0_dots: float
    y0_dots: float
    w_dots: int              # raster width in dots incl. 2*margin
    h_dots: int
    margin_dots: int
    sub: int
    channels: dict[str, np.ndarray]
    reg_channel: str
    local_mode: str          # 'gt' | 'template' | 'footprint' | 'none'
    local_offset_dots: tuple[float, float]  # (dy, dx) applied to sampling
    local_quality: float | None
    local_locked: bool
    affine: np.ndarray = field(repr=False, default=None)

    def img(self, channel: str | None = None) -> np.ndarray:
        return self.channels[channel or self.reg_channel]

    def crop(self, channel: str | None = None) -> np.ndarray:
        """Patch-only raster (margin stripped): shape (h_dots*sub, w_dots*sub)
        of the manifest entry."""
        a = self.img(channel)
        m = self.margin_dots * self.sub
        return a[m: m + self.entry["h_dots"] * self.sub,
                 m: m + self.entry["w_dots"] * self.sub]


def reg_channel_for(scan: dict, e: dict) -> str:
    """Channel a patch registers/measures against: K->grey, C->r, M->g, Y->b.
    Grey scans always use 'grey' (Y is near-invisible there — measure color
    planes on the color scan)."""
    if scan["kind"] != "color":
        return "grey"
    planes = e.get("planes") or []
    if len(planes) == 1 and planes[0] in REG_CHANNEL_FOR_PLANE:
        return REG_CHANNEL_FOR_PLANE[planes[0]]
    return "grey"


def _resolve_entry(scan: dict, e: dict | str) -> dict:
    if isinstance(e, str):
        if scan.get("manifest") is None:
            raise RegistrationError("scan has no manifest — call register() first")
        return entry(scan["manifest"], e)
    return e


def patch_view(scan: dict, e: dict | str, *, margin_dots: int = 8, sub: int = 2,
               local: str = "auto", channel: str = "auto",
               template_dots: np.ndarray | None = None,
               max_shift_dots: float = 8.0, min_quality: float = 0.2
               ) -> PatchView:
    """Resample a manifest patch onto the dot grid with optional local lock.

    local: 'auto' (default) picks per kind: GT/nominal-bits template xcorr for
           aperiodic ground-truthed patches, footprint (solid-rectangle
           template) for periodic or solid kinds, none for blank/infra kinds.
           Explicit values: 'gt', 'footprint', 'none', or pass template_dots
           (ink=1 dot bitmap, patch-sized) for a custom template.
    channel: registration channel; 'auto' = by plane (K:grey C:r M:g Y:b).
    The local offset is measured by xcorr in the registration channel, then
    ALL channels are re-resampled with that offset applied, so the returned
    rasters sit on the nominal dot grid. local_locked=False (quality below
    min_quality or |offset| at the search edge) means the offset was NOT
    applied — rasters are then global-affine only.

    min_quality=0.2 default is calibrated on the real CAL-1 scans: true GT
    locks measure q = 0.70-0.97, a deliberately wrong (16-dot-rolled) template
    measures q = 0.10-0.16 (footprint-driven floor), dead/blank patches ~0.
    Lower it deliberately for sparse patterns (dots_n1 etc.) and treat the
    resulting lock as footprint-grade.
    """
    e = _resolve_entry(scan, e)
    ch = reg_channel_for(scan, e) if channel == "auto" else channel
    x0, y0 = e["x_dots"] - margin_dots, e["y_dots"] - margin_dots
    w, h = e["w_dots"] + 2 * margin_dots, e["h_dots"] + 2 * margin_dots

    tpl_bits, mode = None, "none"
    if template_dots is not None:
        tpl_bits, mode = np.asarray(template_dots, np.float32), "template"
    elif local in ("auto", "gt"):
        if e["kind"] not in PERIODIC_KINDS or local == "gt":
            nb = nominal_bits(e)
            if nb is not None:
                tpl_bits, mode = nb.astype(np.float32), "gt"
        if tpl_bits is None and local == "auto" and (
                e["kind"] in PERIODIC_KINDS or e["kind"] in FOOTPRINT_KINDS):
            tpl_bits, mode = np.ones((e["h_dots"], e["w_dots"]), np.float32), "footprint"
        if tpl_bits is None and local == "gt":
            raise ValueError(f"{e['name']}: local='gt' but no GT/nominal bits")
    elif local == "footprint":
        tpl_bits, mode = np.ones((e["h_dots"], e["w_dots"]), np.float32), "footprint"
    elif local != "none":
        raise ValueError(f"unknown local mode {local!r}")

    offset = (0.0, 0.0)
    q: float | None = None
    locked = False
    if tpl_bits is not None:
        if tpl_bits.shape != (e["h_dots"], e["w_dots"]):
            raise ValueError(f"{e['name']}: template shape {tpl_bits.shape} != "
                             f"({e['h_dots']}, {e['w_dots']})")
        win = warp_channel(scan, ch, x0, y0, w, h, sub=sub)
        canvas = np.zeros((h, w), np.float32)
        canvas[margin_dots: margin_dots + e["h_dots"],
               margin_dots: margin_dots + e["w_dots"]] = tpl_bits
        tpl = np.kron(1.0 - canvas, np.ones((sub, sub), np.float32)) * 255.0
        dy, dx, q = xcorr_offset(win, tpl, max_shift=int(max_shift_dots * sub))
        dy_d, dx_d = dy / sub, dx / sub
        q = float(q)
        locked = bool(q >= min_quality and abs(dy_d) < max_shift_dots - 0.5
                      and abs(dx_d) < max_shift_dots - 0.5)
        if locked:
            offset = (float(dy_d), float(dx_d))

    chans = {"grey": warp_channel(scan, "grey", x0, y0, w, h, sub=sub,
                                  offset_dots=offset)}
    if scan["kind"] == "color":
        for cname in ("r", "g", "b"):
            chans[cname] = warp_channel(scan, cname, x0, y0, w, h, sub=sub,
                                        offset_dots=offset)
    return PatchView(name=e["name"], entry=e, x0_dots=x0, y0_dots=y0,
                     w_dots=w, h_dots=h, margin_dots=margin_dots, sub=sub,
                     channels=chans, reg_channel=ch, local_mode=mode,
                     local_offset_dots=offset, local_quality=q,
                     local_locked=locked, affine=scan["affine"])


def cell_means(view: PatchView, cell_dots: int | None = None,
               channel: str | None = None) -> np.ndarray:
    """Block-mean the patch crop to per-cell means (float32, ink dark).

    cell_dots defaults to entry.params['cell_dots']. Trailing dots that do not
    fill a whole cell are dropped.
    """
    if cell_dots is None:
        cell_dots = view.entry["params"]["cell_dots"]
    a = view.crop(channel)
    cp = cell_dots * view.sub
    ny, nx = a.shape[0] // cp, a.shape[1] // cp
    return a[: ny * cp, : nx * cp].reshape(ny, cp, nx, cp).mean(axis=(1, 3))


# ---------------------------------------------------------------------------
# 4. ground truth
# ---------------------------------------------------------------------------

def load_gt(e: dict) -> np.ndarray | None:
    """Ground-truth dot bitmap (uint8, ink=1) from the entry's gt npy, or None.

    Resolves relative to the entry's `_base_dir` (stamped by load_manifest);
    entries built by hand without the tag keep the historical BUILD default.
    """
    if not e.get("gt"):
        return None
    return np.load(Path(e.get("_base_dir") or BUILD) / e["gt"]).astype(np.uint8)


def load_gt_named(rel: str, base_dir: str | Path | None = None) -> np.ndarray:
    """Auxiliary GT array by manifest-relative path (e.g. params['states_gt']).

    base_dir defaults to BUILD (exp-002 behavior); pass the manifest's or
    entry's `_base_dir` for manifests living outside cc.BUILD.
    """
    return np.load(Path(base_dir or BUILD) / rel)


def nominal_bits(e: dict) -> np.ndarray | None:
    """The printed dot bitmap of a patch: saved GT if present, else rebuilt
    byte-identically from the gen_calpage builders + manifest params.
    None for print-time-only content (contone, rectfill probes, strips,
    rulers, text, quiet zone, sentinel)."""
    gt = load_gt(e)
    if gt is not None:
        return gt
    k, p, w, h = e["kind"], e["params"], e["w_dots"], e["h_dots"]
    g = gen_calpage
    if k == "corner_mark":
        return g.corner_mark(p["satellites"], tuple(p["inward"]))
    if k == "plus_mark":
        return g.plus_mark()
    if k == "reg_cross":
        return g.quad_cross()
    if k == "lines":
        return g.stripes(p["pitch_dots"], w, p["horizontal"])
    if k == "checker":
        return g.checker(p["n_dots"], w)
    if k == "dots":
        return g.squares(p["n_dots"], w, False)
    if k == "holes":
        return g.squares(p["n_dots"], w, True)
    if k in ("solid", "overlay_solid"):
        return np.ones((h, w), np.uint8)
    if k == "slant_edge":
        return g.slant_edge(w)
    if k == "phase_pair":
        return g.phase_pair(p["lines"] == "vertical")
    if k == "nyquist_comb":
        return g.cm_comb(w, p["axis"] == "horizontal_lines")[e["planes"][0]]
    if k == "dot_grid_1dot":
        return g.dot_grid1(w)
    if k == "lines_1dot":
        return g.lines1(w, p["horizontal"])
    if k == "phase_grating":
        return np.ascontiguousarray(np.broadcast_to(
            ((np.arange(h) // (p["period_dots"] // 2)) % 2 == 0)[:, None],
            (h, w)).astype(np.uint8))
    if k == "raster_probe_imagemask":
        if "n_dots" in p:
            return g.checker(p["n_dots"], w)
        return np.ascontiguousarray(np.broadcast_to(
            (np.arange(w) % p["pitch_dots"] < p["line_w_dots"])[None, :],
            (h, w)).astype(np.uint8))
    return None


def gt_cells(e: dict) -> np.ndarray | None:
    """Cell-resolution GT (uint8, ink=1) for patches with params['cell_dots']."""
    gt = load_gt(e)
    if gt is None or "cell_dots" not in e.get("params", {}):
        return None
    c = e["params"]["cell_dots"]
    return gt[::c, ::c].astype(np.uint8)


# ---------------------------------------------------------------------------
# 5. density / paper-white (color measurements)
# ---------------------------------------------------------------------------

def _content_rects(manifest: dict, pad_dots: int) -> np.ndarray:
    rects = []
    for lst in (manifest["patches"], manifest["infrastructure"], manifest["labels"]):
        for r in lst:
            rects.append((r["x_dots"] - pad_dots, r["y_dots"] - pad_dots,
                          r["x_dots"] + r["w_dots"] + pad_dots,
                          r["y_dots"] + r["h_dots"] + pad_dots))
    return np.array(rects, float)


def white_model(scan: dict, *, grid_step_dots: int = 24, pad_dots: int = 10,
                clip_sigma: float = 3.0) -> dict:
    """Per-channel 2-D quadratic paper-white model from blank page areas.

    Samples a grid over the content bounds, keeps points outside every
    manifest rect (patches + infrastructure + labels, padded by pad_dots) —
    this includes the quiet zone and all patch surrounds — and LSQ-fits
    v = c0 + c1 x + c2 y + c3 xy + c4 x^2 + c5 y^2 per channel with two
    sigma-clipping rounds. Returns {'channels': {name: coef6-list}, 'n_samples',
    'rms': {name: rms}, 'grid_step_dots'}. Evaluate with white_at().
    """
    manifest = scan["manifest"]
    if manifest is None:
        raise RegistrationError("scan is not registered")
    x0mm, y0mm, x1mm, y1mm = manifest["content_bounds_mm"]
    to_d = manifest["hw_dpi"] / 25.4
    xs = np.arange(round(x0mm * to_d) + 8, round(x1mm * to_d) - 8, grid_step_dots)
    ys = np.arange(round(y0mm * to_d) + 8, round(y1mm * to_d) - 8, grid_step_dots)
    gx, gy = np.meshgrid(xs.astype(float), ys.astype(float))
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    keep = np.ones(len(pts), bool)
    for rx0, ry0, rx1, ry1 in _content_rects(manifest, pad_dots):
        keep &= ~((pts[:, 0] >= rx0) & (pts[:, 0] < rx1)
                  & (pts[:, 1] >= ry0) & (pts[:, 1] < ry1))
    pts = pts[keep]
    if len(pts) < 50:
        raise RuntimeError(f"only {len(pts)} blank samples — occupancy mask too tight")
    px = affine_apply(scan["affine"], pts)
    xn = pts[:, 0] / 4960.0
    yn = pts[:, 1] / 7016.0
    D = np.column_stack([np.ones_like(xn), xn, yn, xn * yn, xn * xn, yn * yn])
    model: dict = {"channels": {}, "rms": {}, "n_samples": int(len(pts)),
                   "grid_step_dots": grid_step_dots, "_norm": (4960.0, 7016.0)}
    for name, arr in scan["channels"].items():
        v = map_coordinates(arr, [px[:, 1], px[:, 0]], order=1, mode="nearest",
                            output=np.float32).astype(np.float64)
        good = np.ones(len(v), bool)
        coef = None
        for _ in range(3):
            coef, *_ = np.linalg.lstsq(D[good], v[good], rcond=None)
            r = v - D @ coef
            s = 1.4826 * np.median(np.abs(r[good] - np.median(r[good]))) + 1e-6
            good = np.abs(r) < clip_sigma * s
        model["channels"][name] = [float(c) for c in coef]
        model["rms"][name] = float(np.sqrt(np.mean((v[good] - D[good] @ coef) ** 2)))
    return model


def white_at(model: dict, x_dots: np.ndarray, y_dots: np.ndarray,
             channel: str) -> np.ndarray:
    """Evaluate the paper-white model at layout positions (vectorized)."""
    nx, ny = model["_norm"]
    xn = np.asarray(x_dots, float) / nx
    yn = np.asarray(y_dots, float) / ny
    c = model["channels"][channel]
    return (c[0] + c[1] * xn + c[2] * yn + c[3] * xn * yn
            + c[4] * xn * xn + c[5] * yn * yn)


def density(view: PatchView, model: dict,
            channels: tuple[str, ...] = ("r", "g", "b")) -> dict[str, np.ndarray]:
    """Optical density D = -log10(v / white_local) per channel for a PatchView.

    white_local is the white_model evaluated at each raster pixel's layout
    position. v is clipped to >= 1.0, so D is capped near log10(white).
    Default channels ('r','g','b') require a color scan; pass ('grey',) for
    the grey scan.
    """
    gy, gx = np.mgrid[0: view.h_dots * view.sub, 0: view.w_dots * view.sub]
    xd = view.x0_dots + gx / view.sub + view.local_offset_dots[1]
    yd = view.y0_dots + gy / view.sub + view.local_offset_dots[0]
    out = {}
    for ch in channels:
        w = np.maximum(white_at(model, xd, yd, ch), 1e-3)
        v = np.maximum(view.channels[ch].astype(np.float64), 1.0)
        out[ch] = (-np.log10(v / w)).astype(np.float32)
    return out


# ---------------------------------------------------------------------------
# 6. decode wrapper + null control (the 001.2 discipline)
# ---------------------------------------------------------------------------

def _channel_f32(scan: dict, name: str) -> np.ndarray:
    a = scan["channels"][name]
    if a.dtype == np.float32:
        return a
    cache = scan.setdefault("_f32", {})
    if name not in cache:
        cache[name] = a.astype(np.float32)
    return cache[name]


def null_control_ber(pred_cells: np.ndarray, gt_cells_arr: np.ndarray,
                     shift_cells: int = 8) -> float:
    """BER of the SAME decoded bits against an 8-cell-circularly-shifted GT.

    Must come out 0.50 +- 0.02 or the measurement pipeline is broken
    (run-001.2 false-alarm discipline). Shift is along axis 1 (x)."""
    if pred_cells.shape != gt_cells_arr.shape:
        raise ValueError(f"shape mismatch {pred_cells.shape} vs {gt_cells_arr.shape}")
    g = np.roll(gt_cells_arr.astype(bool), shift_cells, axis=1)
    return float((pred_cells.astype(bool) != g).mean())


def ber_with_null(pred_cells: np.ndarray, gt_cells_arr: np.ndarray,
                  shift_cells: int = 8, tol: float = 0.02) -> dict:
    """{'ber', 'n_cells', 'ber_null', 'null_ok', 'shift_cells'} in one call."""
    ber = float((pred_cells.astype(bool) != gt_cells_arr.astype(bool)).mean())
    bn = null_control_ber(pred_cells, gt_cells_arr, shift_cells)
    return {"ber": ber, "n_cells": int(pred_cells.size), "ber_null": bn,
            "null_ok": bool(abs(bn - 0.5) <= tol), "shift_cells": shift_cells}


def decode_patch(scan: dict, e: dict | str, *, channel: str = "auto",
                 null_shift_cells: int = 8, **decode_kw) -> dict:
    """scanlab.decode_cells v4 (dense warp + stepped y-profile + blind soft
    stage) on a SQUARE ground-truthed patch, plus the mandatory null control.

    Adds keys: 'ber_null', 'null_ok', 'channel'. GT is used for registration
    templates and scoring only (scanlab discipline). Non-square patches
    (banding_K) are rejected — use patch_view + family-specific row analysis.
    """
    e = _resolve_entry(scan, e)
    gt = load_gt(e)
    if gt is None:
        raise ValueError(f"{e['name']}: no ground truth — decode_patch needs GT")
    if e["w_dots"] != e["h_dots"]:
        raise ValueError(f"{e['name']}: decode_cells supports square patches only")
    cell = e["params"]["cell_dots"]
    ch = reg_channel_for(scan, e) if channel == "auto" else channel
    out = scanlab.decode_cells(_channel_f32(scan, ch), scan["affine"], e, gt,
                               cell, **decode_kw)
    bits = out["gt_cells"] ^ out["err_map"].astype(np.uint8)
    out["ber_null"] = null_control_ber(bits, out["gt_cells"], null_shift_cells)
    out["null_ok"] = bool(abs(out["ber_null"] - 0.5) <= 0.02)
    out["channel"] = ch
    return out


def canary_verdict(name: str, status: str, statistic: float, control: float,
                   note: str = "") -> dict:
    """Standard canary result: NEVER a bare boolean (001.2 rule).

    status must be 'pass', 'fail' or 'indeterminate'; statistic is the
    measured value, control the discriminating control value.
    """
    if status not in ("pass", "fail", "indeterminate"):
        raise ValueError(f"invalid canary status {status!r}")
    return {"name": name, "status": status, "statistic": float(statistic),
            "control": float(control), "note": note}


# ---------------------------------------------------------------------------
# 7. report shape
# ---------------------------------------------------------------------------

REPORT_FAMILIES = ("structural", "density_color", "modulation", "transport", "meta")


def report_init(scan: dict) -> dict:
    """The one report skeleton (channel-measurement panel §7 + scan/registration
    header + canaries + per-family raw sections). Families merge into it with
    report_merge; key collisions raise."""
    return {
        "scan": {"path": scan["path"], "sha256": scan["sha256"],
                 "kind": scan["kind"],
                 "shape_px": list(scan["grey"].shape),
                 "scan_dpi": scan["scan_dpi"], "hw_dpi": scan["hw_dpi"]},
        "registration": scan["registration"],
        "engine": {},           # product, serial, hwres claimed/measured, ...
        "geometry": {},         # margins, scale, shear, warp rms, plane offsets
        "channel_params": {},   # psf, gain, dev_threshold, tvi, banding, ...
        "modulation": {},       # ber{plane,cell}, mi_*, k_cmy_dprime, ...
        "recommendation": {},   # planes, cell_dots, alphabet, rates
        "canaries": {},         # canary_verdict dicts keyed by canary id
        "families": {f: {} for f in REPORT_FAMILIES},
    }


def report_merge(report: dict, payload: dict) -> dict:
    """Recursively merge payload into report. A collision on any non-dict leaf
    raises ValueError — that is the disjoint-keys guarantee between families."""
    def merge(dst: dict, src: dict, path: str) -> None:
        for k, v in src.items():
            here = f"{path}/{k}"
            if (k not in dst or dst[k] is None
                    or (isinstance(dst[k], dict) and not dst[k])):
                dst[k] = v
            elif isinstance(dst[k], dict) and isinstance(v, dict):
                merge(dst[k], v, here)
            else:
                raise ValueError(f"report key collision at {here}")
    merge(report, payload, "")
    return report


class _NpEncoder(json.JSONEncoder):
    def default(self, o):  # noqa: D102
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)


def save_report(report: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(report, indent=1, cls=_NpEncoder))


# ---------------------------------------------------------------------------
# CLI proof harness: registration + demo patch lock + null control
# ---------------------------------------------------------------------------

def _demo(scan_path: str, demo_patch: str = "K/encode_c3") -> dict:
    scan = load_scan(scan_path)
    reg = register(scan)
    print(f"== {scan_path}  ({scan['kind']}, sha256 {scan['sha256'][:12]}...)")
    print(f"orientation: rot90_ccw={reg['orientation']['rot90_ccw']} "
          f"mirrored={reg['orientation']['mirrored']}  "
          f"corners={[(c['n_sat']) for c in reg['corners_found']]} "
          f"inward_ok={reg['inward_diagonals_match']}")
    print(f"affine: px/dot x={reg['px_per_dot_x']:.5f} y={reg['px_per_dot_y']:.5f} "
          f"rot={reg['rotation_deg']:.3f} deg shear={reg['shear_deg']:.3f} deg")
    print(f"landmarks used {reg['n_landmarks_used']}/{reg['n_landmarks_total']}  "
          f"residual RMS={reg['residual_rms_dots']:.3f} dots "
          f"(corners+plus {reg['residual_rms_core_dots']:.3f}), "
          f"max={reg['residual_max_dots']:.3f}")
    print(f"ruler check: {reg['ruler_check']}")

    e = entry(scan["manifest"], demo_patch)
    v = patch_view(scan, e)
    # noise floor: same window correlated against a 16-dot-rolled WRONG template
    gt = load_gt(e)
    wrong = np.roll(np.roll(gt, 16, axis=0), 16, axis=1)
    v_null = patch_view(scan, e, template_dots=wrong)
    print(f"demo {demo_patch}: mode={v.local_mode} locked={v.local_locked} "
          f"offset=(dy {v.local_offset_dots[0]:+.2f}, dx {v.local_offset_dots[1]:+.2f}) dots "
          f"q={v.local_quality:.4f} vs shifted-template noise q={v_null.local_quality:.4f}")
    # naive decode + null control
    m = cell_means(v)
    bits = (m < np.median(m)).astype(np.uint8)
    gc = gt_cells(e)[: m.shape[0], : m.shape[1]]
    r = ber_with_null(bits, gc)
    print(f"naive decode: BER={r['ber']:.4f} on {r['n_cells']} cells, "
          f"null control={r['ber_null']:.4f} (ok={r['null_ok']})")
    return {"scan": scan, "reg": reg, "view": v, "q_null": v_null.local_quality,
            "naive": r}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="cal_core proof harness")
    ap.add_argument("scans", nargs="+", help="scan PNG path(s)")
    ap.add_argument("--demo-patch", default="K/encode_c3")
    args = ap.parse_args()
    for sp in args.scans:
        _demo(sp, args.demo_patch)
        print()
