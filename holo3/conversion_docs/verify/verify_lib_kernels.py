# Verify holo3/lib/{pava,geometry,decimate,owners}.py bit-exactly against
# the src/holo (v1) and holo2 oracles, in ONE process.
#
# Run: cd <checkout> && \
#   PYTHONPATH=.:src:holo2/src env314t/bin/python _distill/verify/verify_lib_kernels.py
from __future__ import annotations

import sys
from fractions import Fraction

import numpy as np

import holo3.lib.pava as pava3
import holo3.lib.geometry as geom3
import holo3.lib.decimate as dec3
import holo3.lib.owners as own3

from holo.receive import detect as v1_detect
from holo.receive import _payload_context as v1_ctx
from holo.receive import _payload_sampling as v1_samp
from holo.receive import color_calibration as v1_colcal
from holo.receive import payload_model as v1_pm
from holo2.solve import geometry as h2_geom
from holo2.solve import place_shared as h2_ps
from holo2.capture import scale_space as h2_ss
from holo2.capture import scan as h2_scan

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{name}: {detail}")
        print(f"FAIL {name} {detail}")
    else:
        print(f"ok   {name}")


def eq_arrays(a: np.ndarray, b: np.ndarray) -> bool:
    a, b = np.asarray(a), np.asarray(b)
    return (a.dtype == b.dtype and a.shape == b.shape
            and np.array_equal(a, b))


rng = np.random.default_rng(20260828)

# ---------------------------------------------------------------- pava nodes
for trial in range(30):
    n = int(rng.integers(20, 400))
    scores = rng.normal(size=n).astype(np.float32).astype(np.float64)
    # include ties to exercise the stable-order tie pooling
    if trial % 3 == 0:
        scores = np.round(scores, 1)
    labels = rng.integers(0, 2, size=n).astype(bool)
    if labels.sum() < 2 or (~labels).sum() < 2:
        continue
    k3, p3 = pava3._pava_nodes(scores, labels)
    kV, pV = v1_detect._pava_nodes(scores, labels)
    if not (eq_arrays(k3, kV) and eq_arrays(p3, pV)):
        check("pava_nodes", False, f"trial {trial}")
        break
else:
    check("pava_nodes", True)

# interp+logit llr map vs detect.Calibration
n = 200
scores = rng.normal(size=n)
labels = (scores + rng.normal(scale=0.5, size=n)) > 0
knots, probs = v1_detect._pava_nodes(scores, labels)
cal = v1_detect.Calibration("w1", knots, probs, n)
query = rng.normal(size=500) * 2.0
check("calibration_probability",
      eq_arrays(pava3.calibration_probability(query, cal.knots,
                                              cal.probabilities),
                cal.probability(query)))
check("calibration_llr",
      eq_arrays(pava3.calibration_llr(query, cal.knots, cal.probabilities),
                cal.llr(query)))
check("clamp_for", all(
    pava3.clamp_for(k) == v1_detect.clamp_for(k)
    for k in (1, 2, 10, 100, 4096)))

# ------------------------------------------------------------- solve_offset
ok = True
for trial in range(60):
    m = int(rng.integers(3, 200))
    llr = rng.normal(scale=3.0, size=m)
    lab = rng.integers(0, 2, size=m).astype(bool)
    w = rng.uniform(0.1, 1.0, size=m)
    mine = pava3._solve_offset(llr, lab, w)
    theirs = v1_detect._solve_offset(llr, lab, w)
    if mine != theirs:
        ok = False
        check("solve_offset", False, f"trial {trial}: {mine} != {theirs}")
        break
# boundary shortcuts
for lab_all in (False, True):
    m = 40
    llr = rng.normal(size=m)
    lab = np.full(m, lab_all)
    w = np.ones(m)
    if pava3._solve_offset(llr, lab, w) != v1_detect._solve_offset(
            llr, lab, w):
        ok = False
if ok:
    check("solve_offset", True)

# ---------------------------------------------- ordered context offsets fit
ok = True
for trial in range(20):
    m = int(rng.integers(200, 800))
    llr = rng.normal(scale=2.0, size=m)
    bins = rng.integers(0, 9, size=m).astype(np.int64)
    n_sites = max(10, m // 2)
    site_ids = rng.integers(0, n_sites, size=m).astype(np.int64)
    site_labels = rng.integers(0, 2, size=n_sites).astype(bool)
    lab = site_labels[site_ids]
    obs = v1_detect.ContextObservations(
        "r1", llr, bins, lab, site_ids)
    mine = pava3._ordered_context_offsets(
        obs.baseline_llr, obs.neighbour_count, obs.labels, obs.weights)
    theirs = v1_detect._ordered_context_offsets(obs)
    if not eq_arrays(mine, theirs):
        ok = False
        check("ordered_context_offsets", False, f"trial {trial}")
        break
if ok:
    check("ordered_context_offsets", True)

# ------------------------------------------------------------------ losses
m = 300
llr = rng.normal(scale=4.0, size=m)
lab = rng.integers(0, 2, size=m).astype(bool)
w = rng.uniform(0.1, 2.0, size=m)
check("logloss_weighted",
      pava3._logloss(llr, lab, w) == v1_detect._logloss(llr, lab, w))
check("binary_logloss",
      pava3._binary_logloss(llr, lab) == v1_ctx._binary_logloss(llr, lab)
      and pava3._binary_logloss(llr, lab, w)
      == v1_ctx._binary_logloss(llr, lab, w))
p = np.clip(rng.uniform(size=m), 1e-4, 1.0 - 1e-4)
y = lab.astype(np.float64)
oracle_prob_loss = float(-np.mean(
    y * np.log(p) + (1.0 - y) * np.log(1.0 - p)))
check("probability_logloss",
      pava3.probability_logloss(p, lab) == oracle_prob_loss)

# ------------------------------------------------- class balanced weights
ok = True
for trial in range(20):
    m = int(rng.integers(5, 300))
    states = rng.integers(0, 7, size=m)
    if not eq_arrays(pava3.class_balanced_weights(states),
                     v1_colcal.class_balanced_weights(states)):
        ok = False
        check("class_balanced_weights", False, f"trial {trial}")
        break
check("class_balanced_weights_empty",
      eq_arrays(pava3.class_balanced_weights(np.zeros(0, np.int64)),
                v1_colcal.class_balanced_weights(np.zeros(0, np.int64))))
if ok:
    check("class_balanced_weights", True)

# ------------------------------------------------------- geometry: affines
ok = True
for trial in range(40):
    terms = tuple(float(v) for v in rng.normal(scale=5.0, size=6))
    if abs(terms[0] * terms[4] - terms[1] * terms[3]) < 1e-6:
        continue
    if geom3.affine_terms(geom3.affine_matrix(terms)) != \
            h2_geom.affine_terms(h2_geom.affine_matrix(terms)):
        ok = False
        break
    if geom3.invert_affine(terms) != h2_geom.invert_affine(terms):
        ok = False
        break
    ys = rng.normal(scale=100.0, size=50)
    xs = rng.normal(scale=100.0, size=50)
    m_y, m_x = geom3.apply_affine(terms, ys, xs)
    o_y, o_x = h2_geom.apply_affine(terms, ys, xs)
    if not (eq_arrays(m_y, o_y) and eq_arrays(m_x, o_x)):
        ok = False
        break
    dy, dx = float(rng.normal()), float(rng.normal())
    if geom3.shift_affine(terms, dy, dx) != h2_geom.shift_affine(
            terms, dy, dx):
        ok = False
        break
check("affine_family", ok)

# ------------------------------------------------ geometry: rescale law
ok = True
scales = [Fraction(2), Fraction(3), Fraction(4), Fraction(16),
          Fraction(8, 3), Fraction(12, 5), Fraction(1)]
for trial in range(20):
    terms = tuple(float(v) for v in rng.normal(scale=7.0, size=6))
    for s in scales:
        if geom3.rescale_pixels(terms, s) != h2_ps._rescale_pixels(terms, s):
            ok = False
        # compose_to_native == rescale by s; compose_from_native by 1/s
        if geom3.compose_to_native(terms, s) != (
                tuple(float(t) for t in terms) if s == 1
                else h2_ps._rescale_pixels(terms, s)):
            ok = False
        if geom3.compose_from_native(terms, s) != (
                tuple(float(t) for t in terms) if s == 1
                else h2_ps._rescale_pixels(terms, 1 / s)):
            ok = False
check("rescale_pixels_compose", ok)

# ------------------------------------------------ geometry: window starts
check("window_starts", all(
    geom3.window_starts(n) == h2_geom.window_starts(n)
    for n in range(1, 601)))
check("window_starts_constants",
      (geom3.WINDOW_CELLS, geom3.WINDOW_STEP_CELLS,
       geom3.LAYOUT_MIN_WINDOW_CELLS, geom3.TILE_CELLS)
      == (h2_geom.WINDOW_CELLS, h2_geom.WINDOW_STEP_CELLS,
          h2_geom.LAYOUT_MIN_WINDOW_CELLS, h2_geom.TILE_CELLS))

# ------------------------------------------------ geometry: parity family
cells = rng.integers(0, 5000, size=(4000, 2)).astype(np.int64)
y, x = cells[:, 0], cells[:, 1]
check("site_parity_literal",
      eq_arrays(geom3.site_parity(y, x), (131 * y + 17 * x) & 1))
keys = np.column_stack((np.zeros(y.size, np.int64), y, x))
check("site_hash_and2",
      eq_arrays((geom3.site_hash(y, x) & 2) == 0,
                v1_colcal.head_sub_split(keys)))
check("site_hash_and4_and8",
      eq_arrays(geom3.site_hash(y, x) & 12, (131 * y + 17 * x) & 12))

# ------------------------------------------------ geometry: rotated points
ok = True
for rot_k in range(4):
    pts = rng.integers(0, 300, size=(500, 2)).astype(np.int64)
    shape = (int(rng.integers(300, 400)), int(rng.integers(300, 400)))
    if not eq_arrays(geom3.rotated_points(pts, shape, rot_k),
                     v1_samp.rotated_points(pts, shape, rot_k)):
        ok = False
check("rotated_points", ok)

ty3, tx3 = geom3.tile_of_cell(y, x)
tyH, txH = h2_geom.tile_of_cell(y, x)
check("tile_of_cell", eq_arrays(ty3, tyH) and eq_arrays(tx3, txH))

# --------------------------------------------------- decimate: ppc ladder
pairs = [
    (2400, Fraction(2, 600)), (4800, Fraction(2, 600)),
    (1200, Fraction(3, 600)), (2400, Fraction(3, 600)),
    (1200, Fraction(2, 600)), (4800, Fraction(3, 600)),
    (1200.0, Fraction(3, 600)), ("2400", Fraction(2, 600)),
    (1600, Fraction(2, 600)), (600, Fraction(3, 600)),
]
ok = True
for dpi, pitch in pairs:
    mine = dec3.auto_ppc_levels(dpi, pitch)
    theirs = h2_ss.auto_ppc_levels(dpi, pitch)
    if mine != theirs:
        ok = False
        check("auto_ppc_levels", False, f"{dpi}@{pitch}: {mine} != {theirs}")
        break
    if dec3.native_pixels_per_cell(dpi, pitch) != \
            h2_ss.native_pixels_per_cell(dpi, pitch):
        ok = False
        break
if ok:
    check("auto_ppc_levels", True)
check("auto_ppc_expected",
      dec3.auto_ppc_levels(2400, Fraction(2, 600))
      == (Fraction(2), Fraction(4), Fraction(8))
      and dec3.auto_ppc_levels(4800, Fraction(2, 600))
      == (Fraction(2), Fraction(4), Fraction(8), Fraction(16))
      and dec3.auto_ppc_levels(2400, Fraction(3, 600))
      == (Fraction(2), Fraction(4), Fraction(6), Fraction(12))
      and dec3.auto_ppc_levels(1200, Fraction(3, 600))
      == (Fraction(2), Fraction(3), Fraction(6)))
# Fraction(str(float)) seam: 1200.0 must equal 1200 exactly
check("fraction_seam",
      dec3.as_fraction(1200.0) == Fraction(1200)
      and dec3.as_fraction(0.1) == Fraction(1, 10))

# ------------------------------------------- decimate: AreaPixelTransform
ok = True
for s in (Fraction(2), Fraction(3), Fraction(16), Fraction(8, 3),
          Fraction(1)):
    t3 = dec3.AreaPixelTransform(s)
    tH = h2_ss.AreaPixelTransform(s)
    for length in (0, 1, 7, 100, 4801):
        if t3.output_length(length) != tH.output_length(length):
            ok = False
    pts = rng.normal(scale=1000.0, size=(200, 2))
    if not eq_arrays(t3.source_to_view_points(pts),
                     tH.source_to_view_points(pts)):
        ok = False
    if not eq_arrays(t3.view_to_source_points(pts),
                     tH.view_to_source_points(pts)):
        ok = False
    aff = rng.normal(scale=8.0, size=(2, 3))
    if not eq_arrays(t3.source_to_view_affine(aff),
                     tH.source_to_view_affine(aff)):
        ok = False
    if not eq_arrays(t3.view_to_source_affine(aff),
                     tH.view_to_source_affine(aff)):
        ok = False
check("area_pixel_transform", ok)

# ----------------------------------------------- decimate: u8 box kernels
ok = True
for factor in (2, 3, 4, 6, 8, 16):
    h = int(rng.integers(3 * factor + 1, 6 * factor + 5))
    w = int(rng.integers(3 * factor + 1, 6 * factor + 5))
    grey = rng.integers(0, 256, size=(h, w)).astype(np.uint8)
    rgb = rng.integers(0, 256, size=(h, w, 3)).astype(np.uint8)
    t3 = dec3.AreaPixelTransform(Fraction(factor))
    tH = h2_ss.AreaPixelTransform(Fraction(factor))
    if not eq_arrays(dec3.area_decimate(grey, t3),
                     h2_ss.area_decimate(grey, tH)):
        ok = False
        check("u8_box", False, f"grey factor {factor}")
        break
    # K-on-RGB luma law: 3-D source through the scalar path
    if not eq_arrays(dec3.area_decimate(rgb, t3),
                     h2_ss.area_decimate(rgb, tH)):
        ok = False
        check("u8_box", False, f"k-luma factor {factor}")
        break
    if not eq_arrays(dec3.area_decimate_rgb(rgb, t3),
                     h2_ss.area_decimate_rgb(rgb, tH)):
        ok = False
        check("u8_box", False, f"rgb factor {factor}")
        break
    # chunk-size invariance of my path (value-neutral row chunking)
    if not eq_arrays(dec3.area_decimate(grey, t3, chunk_rows=1),
                     dec3.area_decimate(grey, t3)):
        ok = False
        check("u8_box", False, f"chunk invariance factor {factor}")
        break
else:
    check("u8_box", True)

# non-integer factor refuses (contract C-10)
try:
    dec3.area_decimate(np.zeros((12, 12), np.uint8),
                       dec3.AreaPixelTransform(Fraction(8, 3)))
    check("non_integer_refuses", False, "no raise")
except ValueError:
    check("non_integer_refuses", True)

# ------------------------------------------------------- decimate: luma
rgb = rng.integers(0, 256, size=(64, 48, 3)).astype(np.uint8)
grey = rng.integers(0, 256, size=(64, 48)).astype(np.uint8)
check("luma_grey", eq_arrays(dec3.luma_f32(grey), h2_scan._raw_luma(grey)))
check("luma_rgb", eq_arrays(dec3.luma_f32(rgb), h2_scan._raw_luma(rgb)))
check("plane_mean_luma",
      eq_arrays(dec3.plane_mean_luma_f32(
          rgb[..., 0], rgb[..., 1], rgb[..., 2]),
          rgb.mean(axis=2, dtype=np.float32)))

# --------------------------------------------------------------- owners
def synth_candidates(seed: int, n_windows: int, pages: int,
                     shape: tuple[int, int]):
    r = np.random.default_rng(seed)
    cands = []
    for wi in range(n_windows):
        page = int(r.integers(0, pages))
        n = int(r.integers(0, 200))
        cells = np.column_stack((
            r.integers(0, shape[0], size=n),
            r.integers(0, shape[1], size=n))).astype(np.int64)
        cells = np.unique(cells, axis=0)
        rows = np.arange(cells.shape[0], dtype=np.int32)
        vals = r.normal(size=(cells.shape[0], 1)).astype(np.float32)
        cands.append((wi, page, cells, rows, vals))
    return cands


def owners_equal(a, b) -> bool:
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b):
        if ra[0] != rb[0]:
            return False
        for va, vb in zip(ra[1:], rb[1:]):
            if not eq_arrays(va, vb):
                return False
    return True


ok = True
for trial in range(10):
    shape = (192, 256)
    cands = synth_candidates(1000 + trial, 12, 3, shape)
    mine = own3.freeze_page_owners(cands, shape)
    theirs = v1_pm.freeze_page_owners(cands, shape)
    if not owners_equal(mine, theirs):
        ok = False
        check("freeze_page_owners", False, f"trial {trial}")
        break
if ok:
    check("freeze_page_owners", True)

# order_keys parameter: shuffled candidates + content keys == oracle on the
# key-sorted list (the C-12 content-derived competition order)
shape = (192, 256)
cands = synth_candidates(77, 12, 3, shape)
keys = [(float(i % 5) * 0.25, (i % 3, i % 4, 7, 9), "g") for i in
        range(len(cands))]
perm = list(np.random.default_rng(5).permutation(len(cands)))
shuffled = [cands[i] for i in perm]
shuffled_keys = [keys[i] for i in perm]
sorted_cands = [c for _, c in
                sorted(zip(shuffled_keys, shuffled),
                       key=lambda pair: pair[0])]
check("freeze_page_owners_order_keys",
      owners_equal(
          own3.freeze_page_owners(shuffled, shape, shuffled_keys),
          v1_pm.freeze_page_owners(sorted_cands, shape)))

print()
print(f"{CHECKS} checks, {len(FAILURES)} failures")
if FAILURES:
    for line in FAILURES:
        print("FAILED:", line)
    sys.exit(1)
print("VERIFY GREEN: holo3/lib/{pava,geometry,decimate,owners} bit-exact "
      "vs src/holo + holo2 oracles")
