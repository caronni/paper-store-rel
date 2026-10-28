"""analyze_motif1.py — score a scanned MOTIF-1 sheet and emit the Q2 go/no-go.

The decisive question (Q2, exp010): 004.0a showed the B2/RLL trellis gains
~zero because the dominant channel error is a constraint-CONSISTENT
whole-feature dropout (an isolated 2-dot ink run fades to legal white, which
the trellis cannot even flag). The motif frame trades a little rate for
LOCALITY: each B x B block carries one symbol (which of D=1170 legal motifs it
is), detected by a MATCHED FILTER over the whole block. Q2 asks whether the
~47 surviving dots pin the symbol so a dropped 2-dot run is recovered, or
whether the drop flips a source motif i to its legal dropout-twin j (the 788
confusion pairs).

Three regions make it measurable (see gen_motif1.py):
  main     random over the full D=1170 dictionary — headline capacity number.
  dropout  ONLY the 622 dropout-SOURCE motifs {i} — the load-bearing field:
           how often does a sent i get DETECTED as one of its twins {j}?
  control  ONLY the 548 dropout-IMMUNE motifs — baseline symbol error, the
           discriminating control for the dropout number.

Pipeline: register on the 4 chiral corner marks (component-based affine, the
proven analyze_ores.register adapted to this manifest's corner_marks list) ->
bilinear-sample the b*b dot grid of every block AT the dot coordinate (the
documented no-+0.5 rule) -> vectorized matched-filter detect against the whole
dictionary -> per-region symbol error / MI (bits/motif -> b/dot -> b/mm2) /
null control, plus the dropout-confusion rate.

SIM ROUND-TRIP (the M0 gate AND the real Q2 PREDICTION): build the full-page
dot field from the GT, push it through the measured M281 print_scan (which
models ink>=2 / white>=3 development + white-fill = the dropout mechanism),
analyze the simulated scan. Reported by --sim / sim_roundtrip(); a clean
positive control (GT field, no channel) must decode at ~0 symbol error.

Usage: analyze_motif1.py <scan.png> [--json out.json]
       analyze_motif1.py --sim [--json out.json]   (no scan; simulate + score)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import (center_of_mass, find_objects, label,
                           map_coordinates)

Image.MAX_IMAGE_PIXELS = None

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _p in (str(_ROOT / "src"),
           str(_ROOT / "experiments" / "002-calibration-page"),
           str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import motif_codec as mc  # noqa: E402

BUILD = _HERE / "build"

# Areal constant: dots per mm^2 at 600 dpi. The 557.4 anchor value is the
# CLAUDE.md convention for reporting b/mm^2 (600/25.4)^2 ~= 558; the small
# difference is immaterial to a go/no-go and keeps numbers comparable to the
# 82-86 anchor which was reported on the same constant.
DOTS_PER_MM2 = 557.4

# Pre-registered decision thresholds (frozen BEFORE any MOTIF-1 scan exists).
ANCHOR_B_PER_MM2 = 82.0        # the B2 82-86 anchor; usable rate must CLEAR it
CLEAN_CTRL_MAX_SYMERR = 1e-6   # positive control must be effectively 0
NULL_SYMERR_MIN = 0.90         # a rolled-GT null must be near chance (D>>1)


# --------------------------------------------------------------------------
# image loading
# --------------------------------------------------------------------------

def load_grey(path: str) -> np.ndarray:
    """Ink-is-large float array in [0,1] (1 = full ink)."""
    a = np.asarray(Image.open(path).convert("L")).astype(np.float64)
    return 1.0 - a / 255.0


def refl_to_grey(refl: np.ndarray) -> np.ndarray:
    """Convert a simulator reflectance array (paper bright ~0.92, ink dark) to
    the same ink-is-large [0,1] convention load_grey produces from a PNG."""
    return 1.0 - np.clip(refl, 0.0, 1.0)


# --------------------------------------------------------------------------
# registration (component-based affine — copied from analyze_ores.register,
# adapted to this manifest's `corner_marks` list + page_size_pt)
# --------------------------------------------------------------------------

def _by_quadrant(pts: np.ndarray) -> dict:
    """Assign points to page corners by x+-y extremes (near-UPRIGHT scan)."""
    return {"TL": pts[np.argmin(pts[:, 0] + pts[:, 1])],
            "BR": pts[np.argmax(pts[:, 0] + pts[:, 1])],
            "TR": pts[np.argmax(pts[:, 0] - pts[:, 1])],
            "BL": pts[np.argmin(pts[:, 0] - pts[:, 1])]}


def _page_dots(manifest: dict) -> tuple[int, int]:
    """(page_w_dots, page_h_dots) from page_size_pt at hw_dpi."""
    wpt, hpt = manifest["page_size_pt"]
    dpi = manifest["hw_dpi"]
    return round(wpt / 72.0 * dpi), round(hpt / 72.0 * dpi)


def register(grey: np.ndarray, manifest: dict) -> np.ndarray:
    """Affine (dots -> px) 2x3 [[a,b,tx],[c,d,ty]] from the 4 corner crosses.

    The corner marks are the only ISOLATED, low-fill (cross ~6-9% ink),
    ~123-dot-square connected components; the dense motif regions are one huge
    ~50%-fill component each. Label components, keep the mark-shaped ones, take
    centroids by quadrant, least-squares fit the affine. (analyze_ores.register
    verbatim in method; only the manifest field access differs: this manifest
    exposes corner_marks with cx_dots/cy_dots and page_size_pt.)"""
    corners = manifest["corner_marks"]
    pw, ph = _page_dots(manifest)
    ink = grey > (0.5 * grey.max())
    ys, xs = np.where(ink)
    scale = (((xs.max() - xs.min()) / pw) + ((ys.max() - ys.min()) / ph)) / 2.0
    side = 123 * scale

    lab, _ = label(ink)
    slices = find_objects(lab)
    cand: list[tuple[float, float]] = []
    for i, sl in enumerate(slices, start=1):
        if sl is None:
            continue
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        comp = lab[sl] == i
        fill = comp.mean()
        if (0.6 * side < h < 1.6 * side and 0.6 * side < w < 1.6 * side
                and 0.02 < fill < 0.22):
            cy, cx = center_of_mass(comp)
            cand.append((sl[1].start + cx, sl[0].start + cy))
    if len(cand) < 4:
        raise RuntimeError(f"found {len(cand)} corner-mark candidates (need 4)")
    cand_a = np.array(cand, float)
    if len(cand_a) > 4:
        bbox = _by_quadrant(np.array([[xs.min(), ys.min()],
                                      [xs.max(), ys.max()],
                                      [xs.max(), ys.min()],
                                      [xs.min(), ys.max()]]))
        chosen = []
        for k in ("TL", "TR", "BR", "BL"):
            dst = np.hypot(cand_a[:, 0] - bbox[k][0], cand_a[:, 1] - bbox[k][1])
            chosen.append(cand_a[int(np.argmin(dst))])
        cand_a = np.array(chosen)

    det = _by_quadrant(cand_a)
    man = _by_quadrant(np.array(
        [[c["cx_dots"], c["cy_dots"]] for c in corners], float))
    S = np.array([man[k] for k in ("TL", "TR", "BR", "BL")])
    D = np.array([det[k] for k in ("TL", "TR", "BR", "BL")])
    A = np.hstack([S, np.ones((len(S), 1))])
    coef_x, *_ = np.linalg.lstsq(A, D[:, 0], rcond=None)
    coef_y, *_ = np.linalg.lstsq(A, D[:, 1], rcond=None)
    return np.array([coef_x, coef_y])


def affine_identity(x_dots: int = 0, y_dots: int = 0) -> np.ndarray:
    """A trivial 1:1 dot->px affine with optional offset (tx,ty)=(x_dots,
    y_dots): used for the clean positive control, where the grey IS at dot
    resolution and no registration warp exists, so dot (cx,cy) maps straight to
    pixel (cx+tx, cy+ty). (The region's own x_dots/y_dots are added inside
    region_blocks, so the default zero offset is what callers use.)"""
    return np.array([[1.0, 0.0, float(x_dots)],
                     [0.0, 1.0, float(y_dots)]])


# --------------------------------------------------------------------------
# dot-grid sampling (analyze_ores._sample_grid: bilinear, AT the dot coord)
# --------------------------------------------------------------------------

def _sample_grid(grey: np.ndarray, coef: np.ndarray, cx: np.ndarray,
                 cy: np.ndarray) -> np.ndarray:
    """Bilinear-sample `grey` at dot-space points (cx, cy) mapped through the
    affine. Bilinear (not nearest+round) avoids half-integer jitter on 2-3 px
    dots; sample AT the dot coordinate (NOT +0.5 — the half-integer offset
    lands on pixel boundaries and 50/50-blurs, documented in analyze_ores)."""
    px = coef[0, 0] * cx + coef[0, 1] * cy + coef[0, 2]
    py = coef[1, 0] * cx + coef[1, 1] * cy + coef[1, 2]
    return map_coordinates(grey, [py.ravel(), px.ravel()], order=1,
                           mode="nearest").reshape(cx.shape)


def region_blocks(grey: np.ndarray, coef: np.ndarray, region: dict,
                  b: int) -> np.ndarray:
    """Soft (grey, ink-large) blocks of a region: sample every dot centre of
    the rows*b x cols*b field, reshape to (rows, cols, b, b). Sample coords
    are region-relative dot coords offset by the region's (x_dots, y_dots),
    mapped through the affine."""
    rows, cols = region["rows"], region["cols"]
    ny, nx = rows * b, cols * b
    ii, jj = np.mgrid[0:ny, 0:nx].astype(np.float64)
    dots = _sample_grid(grey, coef, region["x_dots"] + jj, region["y_dots"] + ii)
    return dots.reshape(rows, b, cols, b).transpose(0, 2, 1, 3)


# --------------------------------------------------------------------------
# matched-filter detection (vectorized over the whole dictionary)
# --------------------------------------------------------------------------

def dict_pm(dictionary: np.ndarray) -> np.ndarray:
    """Dictionary as (D, b*b) in +-1 form (2*motif-1): ink=+1, white=-1."""
    D, b, _ = dictionary.shape
    return (2.0 * dictionary.reshape(D, b * b) - 1.0)


def detect_blocks(blocks: np.ndarray, dpm: np.ndarray) -> np.ndarray:
    """Matched-filter detect: score each (rows,cols,b,b) soft block against the
    whole (D,b*b) +-1 dictionary and return argmax motif index per block.

    Vectorized: flatten blocks to (N, b*b), mean-center each block (so DC / a
    uniform density offset does not bias the correlation toward heavy or light
    motifs), correlate N x D = blocks_c @ dpm.T, argmax over D. Returns
    (rows, cols) int64 detected indices."""
    rows, cols, b, _ = blocks.shape
    N = rows * cols
    X = blocks.reshape(N, b * b)
    Xc = X - X.mean(axis=1, keepdims=True)
    scores = Xc @ dpm.T                          # (N, D)
    det = np.argmax(scores, axis=1).astype(np.int64)
    return det.reshape(rows, cols)


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------

def mutual_information_bits(sent: np.ndarray, detected: np.ndarray,
                            n_symbols: int) -> float:
    """MI(sent; detected) in bits, MILLER-MADOW-corrected. Both arrays are flat
    int index arrays of equal length.

    The plug-in MI is badly upward-biased here (D=1170 alphabet, N~1.8e5 samples
    -> plug-in bias ~5 bits, so a rolled-GT null reads ~1.8 bits instead of 0).
    Miller-Madow subtracts (m_XY - m_X - m_Y + 1)/(2 N ln2), where m_* are the
    counts of OBSERVED-nonzero support cells of the joint / each marginal. This
    drives the null to ~0 and makes the usable-rate b/mm^2 honest. Clamped at 0
    (a negative corrected MI = no information)."""
    s = sent.ravel()
    d = detected.ravel()
    n = s.size
    joint = np.zeros((n_symbols, n_symbols), np.float64)
    np.add.at(joint, (s, d), 1.0)
    joint /= n
    ps = joint.sum(axis=1)
    pd = joint.sum(axis=0)
    nz = joint > 0
    outer = ps[:, None] * pd[None, :]
    plug_in = float(np.sum(joint[nz] * np.log2(joint[nz] / outer[nz])))
    m_xy = int(np.count_nonzero(joint))
    m_x = int(np.count_nonzero(ps))
    m_y = int(np.count_nonzero(pd))
    bias = (m_xy - m_x - m_y + 1) / (2.0 * n * np.log(2.0))
    return max(0.0, plug_in - bias)


def _areal(mi_bits_per_motif: float, b: int) -> tuple[float, float]:
    """(b/dot, b/mm^2) from MI in bits/motif at cell side b."""
    b_per_dot = mi_bits_per_motif / (b * b)
    return b_per_dot, b_per_dot * DOTS_PER_MM2


def score_region(sent: np.ndarray, detected: np.ndarray, dictionary: np.ndarray,
                 b: int) -> dict:
    """Symbol error, MI (bits/motif, b/dot, b/mm^2), and a rolled-GT null
    control (symbol error ~ (D-1)/D, MI ~ 0) for one region."""
    D = len(dictionary)
    sym_err = float(np.mean(detected != sent))
    mi = mutual_information_bits(sent, detected, D)
    # PERMUTATION-NULL DEBIAS: even Miller-Madow leaves a large residual bias
    # here (D=1170, N~1.8e5, non-uniform detector output -> a rolled-GT null
    # still reads >1 bit). The null MI is the empirical estimator floor for
    # THIS marginal structure; subtract it. Average several deterministic rolls
    # to cut the null's own variance. usable = max(0, MI - mean_null_MI) = the
    # information actually DELIVERED per motif, which the anchor is compared to.
    null_offsets = (3, 7, 17, 53)
    null_mis = [mutual_information_bits(sent, np.roll(detected, k, axis=0), D)
                for k in null_offsets]
    null_mi = float(np.mean(null_mis))
    null_sym_err = float(np.mean(np.roll(detected, null_offsets[0], axis=0)
                                 != sent))
    usable_mi = max(0.0, mi - null_mi)
    b_per_dot, b_per_mm2 = _areal(usable_mi, b)
    return {"n_symbols": int(sent.size),
            "symbol_error": sym_err,
            "mi_bits_per_motif": mi,
            "null_mi_bits_per_motif": null_mi,
            "usable_mi_bits_per_motif": usable_mi,
            "usable_b_per_dot": b_per_dot,
            "usable_b_per_mm2": b_per_mm2,
            "null_symbol_error": null_sym_err,
            "dictionary_size": D}


def dropout_confusion(sent: np.ndarray, detected: np.ndarray,
                      twins: dict[int, set[int]]) -> dict:
    """For the dropout region: fraction of blocks whose detected motif is one
    of the GT source motif's dropout-twins {j} specifically (the Q2 number),
    vs the generic error rate (detected != sent AND not a twin)."""
    s = sent.ravel()
    d = detected.ravel()
    n = s.size
    twin_hits = 0
    generic_err = 0
    for si, di in zip(s.tolist(), d.tolist()):
        if di == si:
            continue
        if di in twins.get(si, ()):  # a dropped-run confusion onto a legal twin
            twin_hits += 1
        else:
            generic_err += 1
    total_err = twin_hits + generic_err
    return {"dropout_confusion_rate": twin_hits / n if n else 0.0,
            "generic_error_rate": generic_err / n if n else 0.0,
            "total_error_rate": total_err / n if n else 0.0,
            "twin_share_of_errors": (twin_hits / total_err) if total_err else 0.0,
            "n_twin_hits": twin_hits, "n_generic_errors": generic_err,
            "n_blocks": n}


def build_twins(pairs: list) -> dict[int, set[int]]:
    """source motif index i -> set of its legal dropout-twin indices {j}."""
    twins: dict[int, set[int]] = {}
    for i, j in pairs:
        twins.setdefault(int(i), set()).add(int(j))
    return twins


# --------------------------------------------------------------------------
# verdict
# --------------------------------------------------------------------------

def verdict(dropout_usable_b_per_mm2: float, drop_conf: dict,
            anchor: float = ANCHOR_B_PER_MM2) -> tuple[str, str]:
    """GO iff the dropout-region usable rate clears the anchor AND dropout
    twins are not the dominant error; NO-GO otherwise. Returns (verdict, why)."""
    clears = dropout_usable_b_per_mm2 >= anchor
    twins_dominant = drop_conf["twin_share_of_errors"] >= 0.5
    if clears and not twins_dominant:
        return ("GO",
                f"dropout usable {dropout_usable_b_per_mm2:.1f} b/mm2 >= "
                f"{anchor:.0f} anchor and dropout twins are only "
                f"{drop_conf['twin_share_of_errors']*100:.0f}% of errors — "
                "matched filtering recovers the whole-feature dropout.")
    reasons = []
    if not clears:
        reasons.append(
            f"dropout usable {dropout_usable_b_per_mm2:.1f} b/mm2 < "
            f"{anchor:.0f} anchor")
    if twins_dominant:
        reasons.append(
            f"dropout twins are {drop_conf['twin_share_of_errors']*100:.0f}% "
            "of errors (single-run dropout still flips the motif)")
    return "NO-GO", "; ".join(reasons) + "."


# --------------------------------------------------------------------------
# top-level scoring of an already-loaded grey image
# --------------------------------------------------------------------------

def _load_context() -> tuple[dict, np.ndarray, list, dict]:
    """(manifest, dictionary, pairs, twins) — dictionary rebuilt + sha-checked
    against the manifest so the index space matches the GT exactly."""
    manifest = json.loads((BUILD / "motif1_manifest.json").read_text())
    dictionary = mc.build_dictionary(manifest["b"])
    import hashlib
    got = hashlib.sha256(dictionary.tobytes()).hexdigest()
    assert got == manifest["dictionary_sha256"], \
        "rebuilt dictionary sha mismatch vs manifest (index space diverged)"
    pairs = mc.dropout_pairs(dictionary, manifest["b"])
    twins = build_twins(pairs)
    return manifest, dictionary, pairs, twins


def score_grey(grey: np.ndarray, coef: np.ndarray, manifest: dict,
               dictionary: np.ndarray, twins: dict[int, set[int]]) -> dict:
    """Score all three regions of an ink-large grey image given the affine."""
    b = manifest["b"]
    dpm = dict_pm(dictionary)
    regions = {r["name"]: r for r in manifest["regions"]}
    out: dict = {}
    for name, r in regions.items():
        sent = np.load(BUILD / r["gt_file"])
        blocks = region_blocks(grey, coef, r, b)
        detected = detect_blocks(blocks, dpm)
        m = score_region(sent, detected, dictionary, b)
        if name == "dropout":
            m["dropout_confusion"] = dropout_confusion(sent, detected, twins)
        out[name] = m
    return out


def analyze_scan(scan_path: str) -> dict:
    manifest, dictionary, pairs, twins = _load_context()
    grey = load_grey(scan_path)
    coef = register(grey, manifest)
    regions = score_grey(grey, coef, manifest, dictionary, twins)
    dc = regions["dropout"]["dropout_confusion"]
    v, why = verdict(regions["dropout"]["usable_b_per_mm2"], dc)
    return {"scan": scan_path, "source": "scan", "regions": regions,
            "verdict": v, "verdict_reason": why,
            "anchor_b_per_mm2": ANCHOR_B_PER_MM2}


# --------------------------------------------------------------------------
# clean positive control + simulator round-trip (the real Q2 prediction)
# --------------------------------------------------------------------------

def _assemble_page_field(manifest: dict, dictionary: np.ndarray,
                         with_corners: bool = False) -> np.ndarray:
    """Rasterize the full page's motif regions into a single dot bitmap
    (ink=1) at the manifest's page dot size, each region placed at its
    (x_dots, y_dots). If `with_corners`, also stamp the 4 chiral corner marks
    at their manifest positions so the simulated scan can be corner-REGISTERED
    exactly like a real scan (mirrors analyze_scan; needed once the geometry
    warp is on)."""
    b = manifest["b"]
    pw, ph = _page_dots(manifest)
    field = np.zeros((ph, pw), np.uint8)
    for r in manifest["regions"]:
        sent = np.load(BUILD / r["gt_file"])
        rf = mc.symbols_to_field(sent, dictionary, b)
        y, x = r["y_dots"], r["x_dots"]
        field[y:y + rf.shape[0], x:x + rf.shape[1]] = rf
    if with_corners:
        import gen_calpage  # noqa: PLC0415  (byte-identical corner_mark)
        inward = {1: (1, 1), 2: (1, -1), 3: (-1, -1), 4: (-1, 1)}
        for c in manifest["corner_marks"]:
            n_sat = c["satellites"]
            mark = gen_calpage.corner_mark(n_sat, inward[n_sat])
            y, x = c["y_dots"], c["x_dots"]
            field[y:y + mark.shape[0], x:x + mark.shape[1]] = mark
    return field


def _score_field_direct(grey: np.ndarray, manifest: dict,
                        dictionary: np.ndarray,
                        twins: dict[int, set[int]],
                        px_per_dot: int = 1) -> dict:
    """Score a page-sized ink-large grey using each region's KNOWN dot offset
    (a pure-scale affine, dot -> pixel = px_per_dot * dot) — no corner-mark
    registration. Used for the clean positive control (px_per_dot=1, grey is
    already at dot pitch) and the simulated scan (px_per_dot=oversample, the
    grey is the oversampled reflectance and dots are bilinear-sampled at their
    centres — the SAME operator the real corner-registered path uses)."""
    b = manifest["b"]
    dpm = dict_pm(dictionary)
    coef = np.array([[float(px_per_dot), 0.0, 0.0],
                     [0.0, float(px_per_dot), 0.0]])
    out: dict = {}
    for r in manifest["regions"]:
        sent = np.load(BUILD / r["gt_file"])
        blocks = region_blocks(grey, coef, r, b)
        detected = detect_blocks(blocks, dpm)
        m = score_region(sent, detected, dictionary, b)
        if r["name"] == "dropout":
            m["dropout_confusion"] = dropout_confusion(sent, detected, twins)
        out[r["name"]] = m
    return out


def clean_positive_control() -> dict:
    """Rasterize the GT field with NO channel and score it — symbol error must
    be ~0 in every region (proves detector + sampling are correct)."""
    manifest, dictionary, _pairs, twins = _load_context()
    field = _assemble_page_field(manifest, dictionary)
    grey = field.astype(np.float64)               # ink=1, white=0 (ink-large)
    return _score_field_direct(grey, manifest, dictionary, twins)


def sim_roundtrip(seed: int = 0, scan_seed: int | None = None,
                  geometry: bool = False) -> dict:
    """Push the GT page field through the measured M281 print_scan (clean-mask
    K path: models ink>=2 / white>=3 development + edge gain + PSF = the
    development physics that produces the dropout mechanism), then score with
    the SAME sampling the real path uses. This is the Q2 PREDICTION before
    paper.

    geometry=False (default): the printer wander / y-scale / scanner steps are
    OFF, so the scan is at a clean 2 px/dot and the pure-scale affine is exact.
    This ISOLATES the development/dropout physics — the actual Q2 mechanism
    (warp tracking is L1-sync's separate job) — and is the headline sim number.
    geometry=True: the full warp is on and the scan is corner-REGISTERED
    exactly like a real scan (analyze_scan path), i.e. only the global affine
    is removed and residual ~1-dot wander/steps remain — an un-tracked bound.

    NOTE on sim FIDELITY (why the sim is a PESSIMISTIC bound, not calibrated):
    the M281 PlaneParams PSF sigma ~1.0-1.06 dots blurs a 7-dot motif heavily
    and the model over-inks (measured main dot-fill ~0.78 vs GT ~0.42; per-dot
    hard BER ~35% vs the measured i2w3 anchor ~13%). The 2-dot-white
    context-dependent attenuation is an open M0 TODO (CLAUDE.md), and hard
    white-closure was measured WRONG at c2. So the sim's ABSOLUTE symbol error
    is a worst-case bound; the DISCRIMINATING output is the dropout-confusion
    twin share (channel-model-robust: it asks WHICH errors happen, not how
    many)."""
    from paperholo.channel.simulator import ChannelParams, print_scan

    manifest, dictionary, _pairs, twins = _load_context()
    field = _assemble_page_field(manifest, dictionary, with_corners=geometry)
    p = ChannelParams(plane="K", emission="clean_mask", seed=seed,
                      scan_seed=scan_seed, geometry=geometry)
    refl = print_scan(field, p)                   # (H*os, W*os) reflectance
    os = p.scan_oversample
    grey_os = refl_to_grey(refl)
    if geometry:
        # mirror the real scan path: corner-register, then score via that affine
        coef = register(grey_os, manifest)
        regions = score_grey(grey_os, coef, manifest, dictionary, twins)
    else:
        # clean 2 px/dot: sample each dot centre (dot d -> pixel d*os), bilinear
        regions = _score_field_direct(grey_os, manifest, dictionary, twins,
                                      px_per_dot=os)
    dc = regions["dropout"]["dropout_confusion"]
    v, why = verdict(regions["dropout"]["usable_b_per_mm2"], dc)
    return {"source": "sim", "seed": seed, "geometry": geometry,
            "regions": regions, "verdict": v, "verdict_reason": why,
            "anchor_b_per_mm2": ANCHOR_B_PER_MM2}


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------

def _print_report(r: dict) -> None:
    src = r["source"]
    if src == "sim":
        head = ("SIMULATED M281 print_scan  geometry="
                + ("ON (corner-registered)" if r.get("geometry")
                   else "OFF (development-only)"))
    else:
        head = r.get("scan", "scan")
    print(f"MOTIF-1  [{src}]  {head}")
    print(f"  {'region':8s} {'symErr%':>8s} {'MIraw':>7s} {'MInull':>7s} "
          f"{'usable':>7s} {'b/dot':>7s} {'b/mm2':>8s}")
    for name in ("main", "dropout", "control"):
        m = r["regions"][name]
        print(f"  {name:8s} {m['symbol_error']*100:8.2f} "
              f"{m['mi_bits_per_motif']:7.3f} {m['null_mi_bits_per_motif']:7.3f} "
              f"{m['usable_mi_bits_per_motif']:7.3f} {m['usable_b_per_dot']:7.3f} "
              f"{m['usable_b_per_mm2']:8.1f}")
    dc = r["regions"]["dropout"]["dropout_confusion"]
    print(f"  dropout-confusion: {dc['dropout_confusion_rate']*100:.2f}%  "
          f"(twins = {dc['twin_share_of_errors']*100:.0f}% of errors; "
          f"generic {dc['generic_error_rate']*100:.2f}%)")
    print(f"  VERDICT: {r['verdict']}  — {r['verdict_reason']}")


def main() -> None:
    ap = argparse.ArgumentParser(description="score a scanned MOTIF-1 sheet")
    ap.add_argument("scan", nargs="?", help="scan .png (omit with --sim)")
    ap.add_argument("--sim", action="store_true",
                    help="no scan: simulate M281 print_scan + score (Q2 pred)")
    ap.add_argument("--seed", type=int, default=0, help="sim print seed")
    ap.add_argument("--geometry", action="store_true",
                    help="sim: enable printer/scanner warp + corner-register "
                         "(default OFF = isolate the development/dropout physics)")
    ap.add_argument("--json")
    a = ap.parse_args()

    if a.sim:
        r = sim_roundtrip(seed=a.seed, geometry=a.geometry)
        ctrl = clean_positive_control()
        r["clean_control_symbol_error"] = {
            k: ctrl[k]["symbol_error"] for k in ("main", "dropout", "control")}
    elif a.scan:
        r = analyze_scan(a.scan)
    else:
        ap.error("give a scan path or --sim")

    _print_report(r)
    if a.sim:
        ce = r["clean_control_symbol_error"]
        print(f"  clean positive control symErr: "
              f"main {ce['main']*100:.4f}%  dropout {ce['dropout']*100:.4f}%  "
              f"control {ce['control']*100:.4f}%  (must be ~0)")
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1))
        print(f"  -> {a.json}")


if __name__ == "__main__":
    main()
