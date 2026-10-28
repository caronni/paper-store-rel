# Verify holo3/plugins/color_region{,_ctx,_anchor}.py against src/holo
# oracles in one process.  Run from the worktree root:
#   PYTHONPATH=.:src:holo2/src env314t/bin/python _distill/verify/verify_color_region.py
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import numpy as np

os.environ.pop("HOLO_COLOR_STACK_FORCE_NULL", None)

from holo3 import data as h3_data
from holo3.format import identity as h3_identity
from holo3.format import tile_codec as h3_tile_codec
from holo3.lib.geometry import site_parity as h3_site_parity
from holo3.plugins import color_model as cm
from holo3.plugins import color_region as cr
from holo3.plugins import color_region_anchor as cra
from holo3.plugins import color_region_ctx as crc

from holo.core import color_tile as o_color_tile
from holo.core import keystream as o_keystream
from holo.core.ldpc.frame import encode_frame as o_encode_frame
from holo.format import pilots as o_pilots
from holo.format.resolve import resolve_format_ref as o_resolve
from holo.receive import color_anchoring as o_anchor
from holo.receive import color_fitting as o_fitting
from holo.receive import color_neighbourhood as o_neigh
from holo.receive import color_pool as o_pool
from holo.receive import color_registration as o_reg
from holo.receive import color_sampling as o_sampling
from holo.receive import color_stack as o_stack
from holo.receive import detect as o_detect
from holo.receive.placement.model import AffinePose

CHECKS = 0
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILS.append(f"{name}: {detail}")
        print(f"FAIL {name} {detail}")


def eq_arr(name: str, a, b) -> None:
    a = np.asarray(a)
    b = np.asarray(b)
    same = a.shape == b.shape and np.array_equal(a, b)
    detail = f"shapes {a.shape}/{b.shape}"
    if a.shape == b.shape and a.size and not same:
        detail += (" maxdiff "
                   f"{np.max(np.abs(np.asarray(a, np.float64) - np.asarray(b, np.float64)))}")
    check(name, same, detail)


rng = np.random.default_rng(20260829)

# =====================================================================
# 1. ctx primitives: solve_offset chain, ordered_offsets, anchor_curve,
#    one_versus_rest, plane_marginals, provisional ink, stride_select.
# =====================================================================
for trial in range(8):
    n = int(rng.integers(30, 400))
    logits = rng.normal(0.0, 2.0, n)
    labels = rng.random(n) < rng.uniform(0.2, 0.8)
    weights = rng.uniform(0.1, 3.0, n)
    bins = rng.integers(0, 9, n).astype(np.int64)
    for direction in (True, False):
        mine = crc.ordered_offsets(logits, labels, weights, bins, direction)
        oracle = o_neigh.ordered_offsets(
            logits, labels, weights, bins, non_increasing=direction)
        eq_arr(f"ordered_offsets[{trial},{direction}]", mine, oracle)
    curve = crc.ordered_offsets(logits, labels, weights, bins, True)
    eq_arr(f"anchor_curve[{trial}]",
           crc.anchor_curve(curve, bins, weights),
           o_neigh.anchor_curve(curve, bins, weights))

scores7 = rng.normal(0.0, 3.0, (200, 7))
for column in range(7):
    eq_arr(f"one_versus_rest[{column}]",
           crc.one_versus_rest(scores7, column),
           o_neigh.one_versus_rest(scores7, column))
eq_arr("plane_marginals7", crc.plane_marginals(scores7),
       o_neigh.plane_marginals(scores7))
scores8 = rng.normal(0.0, 3.0, (200, 8))
eq_arr("plane_marginals8", crc.plane_marginals(scores8),
       o_neigh.plane_marginals(scores8))
eq_arr("state_bits7", crc.state_bits(7), o_neigh.state_bits(7))
eq_arr("state_bits8", crc.state_bits(8), o_neigh.state_bits(8))
rel6 = rng.normal(0.0, 4.0, (150, 6))
eq_arr("augment", crc.augment(rel6), o_neigh.augment(rel6))
eq_arr("provisional_ink_cmy7", crc.provisional_ink(rel6, False),
       o_neigh.provisional_ink(rel6, cmy8=False))
llr3 = rng.normal(0.0, 4.0, (150, 3))
eq_arr("provisional_ink_cmy8", crc.provisional_ink(llr3, True),
       o_neigh.provisional_ink(llr3, cmy8=True))
for count, limit in ((10, 40000), (50000, 40000), (40001, 40000)):
    eq_arr(f"stride_select[{count}]", crc.stride_select(count, limit),
           o_neigh.stride_select(count, limit))

# =====================================================================
# 2. neighbour counts + bins on a random sparse cell set.
# =====================================================================
for trial in range(4):
    n = int(rng.integers(50, 900))
    cells = np.unique(
        rng.integers(0, 60, (n, 2)).astype(np.int64), axis=0)
    ink = rng.random(cells.shape[0]) < 0.5
    counts_m, valid_m = crc.context_neighbour_counts(cells, ink)
    counts_o, valid_o = o_detect.context_neighbour_counts(cells, ink)
    eq_arr(f"neigh_counts[{trial}]", counts_m, counts_o)
    eq_arr(f"neigh_valid[{trial}]", valid_m, valid_o)
    eq_arr(f"context_bins[{trial}]",
           np.where(valid_m, counts_m, np.int8(-1)),
           o_detect.context_bins(counts_o, valid=valid_o))

# =====================================================================
# 3. ownership + deterministic split (incl. one-tile sparse repair).
# =====================================================================


def make_src_rows(rows3, poses=None):
    out = []
    for index, row in enumerate(rows3):
        pose = None if poses is None else poses[index]
        patch = SimpleNamespace(
            patch_id=row.patch_ordinal,
            candidate=SimpleNamespace(page=row.page),
            segment=SimpleNamespace(
                segment=SimpleNamespace(pose=pose)))
        out.append(o_anchor._Rows(
            patch, row.local_cells_yx, row.page_cells_yx,
            row.scan_points_yx, row.states, row.furniture_kind,
            row.known_component_bits, row.known_component_mask,
            o_anchor._neighbor_rows(row.local_cells_yx), ()))
    return tuple(out)


def make_window(patch_ordinal, page, oy, ox, height, width, states,
                kinds, scan_scale=4.0):
    yy, xx = np.mgrid[0:height, 0:width]
    local = np.stack((yy.ravel(), xx.ravel()), axis=1).astype(np.int64)
    page_cells = local + np.asarray((oy, ox), np.int64)
    scan = local.astype(np.float64) * scan_scale + 30.0
    bits = np.zeros((local.shape[0], 3), np.uint8)
    mask = np.zeros((local.shape[0], 3), np.bool_)
    labelled = states >= 0
    bits[labelled] = h3_tile_codec.states_to_planes(states[labelled])
    mask[labelled] = True
    return h3_data.WindowRows(
        patch_ordinal=patch_ordinal, window_id=("cap", 0, 0, (0, 0, 0, 0)),
        page=page, local_cells_yx=local, page_cells_yx=page_cells,
        scan_points_yx=scan, states=states, furniture_kind=kinds,
        known_component_bits=bits, known_component_mask=mask,
        heldout_logloss=None)


def synth_labels(n, n_states, rng, label_fraction=0.6):
    states = np.full(n, -1, np.int8)
    kinds = np.full(n, -1, np.int8)
    labelled = rng.random(n) < label_fraction
    states[labelled] = rng.integers(
        0, n_states, int(labelled.sum())).astype(np.int8)
    role = rng.random(n)
    kinds[labelled & (role < 0.45)] = 0
    kinds[labelled & (role >= 0.45) & (role < 0.85)] = 1
    return states, kinds


for trial in range(3):
    windows3 = []
    for index in range(3):
        n_states = 7 if trial < 2 else 8
        states, kinds = synth_labels(600, n_states, rng)
        windows3.append(make_window(
            index * 7 + 1, 0, int(rng.integers(0, 40)),
            int(rng.integers(0, 40)), 20, 30, states, kinds))
    rows3 = tuple(windows3)
    sel_m = cr.owner_selection(rows3)
    sel_o = o_fitting._owner_selection(make_src_rows(rows3))
    for field in ("window_ordinals", "row_indices", "states", "kinds",
                  "keys", "search"):
        eq_arr(f"owner_{field}[{trial}]", getattr(sel_m, field),
               getattr(sel_o, field))
    features = tuple(rng.normal(0.5, 0.2, (600, 3)) for _ in range(3))
    eq_arr(f"owner_gather[{trial}]", sel_m.gather(features),
           sel_o.gather(features))

states_sparse = np.asarray([0, 0, 1, 1, 2, 2, 3, 4, 5, 6, 3, 4, 5, 6],
                           np.int64)
keys_sparse = np.asarray(
    [(0, y, x) for y, x in
     [(0, 0), (2, 0), (0, 2), (1, 1), (4, 0), (2, 4), (0, 1), (1, 0),
      (1, 2), (3, 0), (0, 3), (1, 4), (3, 2), (5, 0)]], np.int64)
eq_arr("sparse_split",
       cr.deterministic_fit_split(states_sparse, keys_sparse),
       o_fitting._deterministic_fit_split(states_sparse, keys_sparse))
one_side_states = np.asarray([5, 5, 5], np.int64)
one_side_keys = np.asarray([(0, 0, 0), (0, 2, 0), (0, 0, 2)], np.int64)
eq_arr("sparse_split_repair",
       cr.deterministic_fit_split(one_side_states, one_side_keys),
       o_fitting._deterministic_fit_split(one_side_states, one_side_keys))

# =====================================================================
# 4. registration: fit_plane_residual branches, NCC, full harvest.
# =====================================================================
for trial, n in enumerate((3, 10, 30, 120)):
    y_frac = rng.uniform(0.0, 1.0 if trial != 1 else 0.1, n)
    offsets = rng.normal(0.0, 0.4, (n, 2))
    offsets[rng.random(n) < 0.1] = np.nan
    quality = rng.uniform(-0.1, 0.9, n)
    mine = cra.fit_plane_residual(y_frac, offsets, quality)
    oracle = o_reg.fit_plane_residual(y_frac, offsets, quality)
    check(f"plane_residual[{trial}]",
          mine.intercept_xy == oracle.intercept_xy
          and mine.slope_xy == oracle.slope_xy
          and mine.n_anchors == oracle.n_anchors,
          f"{mine} vs {oracle}")

for trial in range(4):
    window = rng.normal(0.5, 0.2, (24, 24))
    template = (rng.random((12, 12)) < 0.5).astype(np.float64)
    weight = rng.uniform(0.05, 1.0, (12, 12))
    mine = cra.xcorr_offset_ncc(window, template, weight)
    oracle = o_anchor._xcorr_offset_ncc(window, template, weight)
    check(f"xcorr[{trial}]", mine == oracle, f"{mine} vs {oracle}")

H_PX, W_PX = 420, 400
smooth = rng.integers(30, 220, (H_PX, W_PX, 3)).astype(np.uint8)
from scipy import ndimage as _ndimage
for channel in range(3):
    smooth[..., channel] = _ndimage.uniform_filter(
        smooth[..., channel], size=3, mode="nearest")
planes_t = (smooth[..., 0], smooth[..., 1], smooth[..., 2])
raster_o = SimpleNamespace(
    shape=(H_PX, W_PX),
    crop_native=lambda r0, r1, c0, c1: smooth[r0:r1, c0:c1])
jac = ((4.02, 0.03), (-0.02, 3.98))
pose = AffinePose((33.0, 31.0), jac, (0.0, 0.0), 4.0, 0.0)
affine_t = (jac[0][0], jac[0][1], 33.0, jac[1][0], jac[1][1], 31.0)
spec_stub = SimpleNamespace(
    cell_dots=2, layout=SimpleNamespace(cells_yx=(3328, 2304)))

states_r, kinds_r = synth_labels(40 * 40, 8, rng, 0.7)
win_r = make_window(3, 0, 8, 6, 40, 40, states_r, kinds_r)
win_r = h3_data.WindowRows(**{
    **{f: getattr(win_r, f) for f in (
        "patch_ordinal", "window_id", "page", "local_cells_yx",
        "page_cells_yx", "states", "furniture_kind",
        "known_component_bits", "known_component_mask",
        "heldout_logloss")},
    "scan_points_yx": pose.points(win_r.local_cells_yx.astype(np.float64)),
})
rows_r3 = (win_r,)
rows_ro = make_src_rows(rows_r3, poses=(pose,))
base_r = (rng.normal(0.5, 0.22, (1600, 3)),)

res_m = cra.fit_registration(
    planes_t, rows_r3, (cra.neighbor_rows(win_r.local_cells_yx),),
    (affine_t,), base_r, 2, 3328)
res_o, _anchors_o = o_anchor._fit_registration(
    raster_o, rows_ro, base_r, spec_stub)
for plane in range(3):
    check(f"fit_registration[{plane}]",
          res_m[plane].intercept_xy == res_o[plane].intercept_xy
          and res_m[plane].slope_xy == res_o[plane].slope_xy
          and res_m[plane].n_anchors == res_o[plane].n_anchors,
          f"{res_m[plane]} vs {res_o[plane]}")

corr_m = cra.features_with_page_fraction(
    planes_t, win_r, affine_t, res_m, 2, 3328, 4.0, 255.0)
corr_o = o_anchor._features_with_page_fraction(
    raster_o, rows_ro[0], res_o, spec_stub, 4.0, 255.0)
check("corrected_features_both_present",
      (corr_m is None) == (corr_o is None), f"{corr_m is None}")
if corr_m is not None and corr_o is not None:
    eq_arr("corrected_features", corr_m, corr_o)

override = tuple(rng.normal(0.0, 0.3, (1600, 2)) for _ in range(3))
corr_mo = cra.features_with_page_fraction(
    planes_t, win_r, affine_t, res_m, 2, 3328, 4.0, 255.0,
    offsets_override=override)
corr_oo = o_anchor._features_with_page_fraction(
    raster_o, rows_ro[0], res_o, spec_stub, 4.0, 255.0,
    offsets_override=override)
eq_arr("corrected_features_override", corr_mo, corr_oo)

huge = (np.full((1600, 2), 1.0e5), None, None)
check("corrected_features_out_of_raster",
      cra.features_with_page_fraction(
          planes_t, win_r, affine_t, res_m, 2, 3328, 4.0, 255.0,
          offsets_override=huge) is None, "expected None")

# sampling kernels
crop_m = cra.native_crop(planes_t, win_r.scan_points_yx, cra.window_halo(4.0))
crop_o = o_sampling.native_crop(
    raster_o, win_r.scan_points_yx, o_sampling.window_halo(4.0))
check("native_crop_origin", crop_m[:2] == crop_o[:2],
      f"{crop_m[:2]} vs {crop_o[:2]}")
eq_arr("native_crop_raw", crop_m[2], crop_o[2])
feat_m = cra.crop_features(crop_m, win_r.scan_points_yx, 4.0, 255.0)
feat_o = o_sampling.crop_features(crop_o, win_r.scan_points_yx, 4.0, 255.0)
eq_arr("crop_features", feat_m, feat_o)

# =====================================================================
# 5. format-truth: reference states, label rows, pool masks, projection.
# =====================================================================
spec8 = o_resolve("L:c3-cmy8-p120-v0@2240x1536")
row8 = h3_identity.resolve_format_ref("L:c3-cmy8-p120-v0@2240x1536")
geom8 = h3_identity.build_site_geometry(row8)
spec7 = o_resolve("L:c3-cmy7-p120-v0@2240x1536")
row7 = h3_identity.resolve_format_ref("L:c3-cmy7-p120-v0@2240x1536")
geom7 = h3_identity.build_site_geometry(row7)
check("fossil_seed8", spec8.seed == row8.seed, "seed mismatch")
check("fossil_seed7", spec7.seed == row7.seed, "seed mismatch")
check("cell_dots", cr.cell_dots_of(row8) == spec8.cell_dots,
      f"{cr.cell_dots_of(row8)}")

yy, xx = np.mgrid[30:150, 20:140]
cells_ref = np.stack((yy.ravel(), xx.ravel()), axis=1).astype(np.int64)
for spec_o, row_h, geom_h, tag in ((spec8, row8, geom8, "8"),
                                   (spec7, row7, geom7, "7")):
    states_o, kinds_o = o_anchor.color_reference_states(
        spec_o, 0, cells_ref)
    states_m, kinds_m = cm.reference_states(row_h, geom_h, 0, cells_ref)
    eq_arr(f"reference_states[{tag}]", states_m, states_o)
    eq_arr(f"reference_kinds[{tag}]", kinds_m, kinds_o)

# label rows vs oracle _label_site_rows
aligned_stub = SimpleNamespace(
    local_cells_yx=cells_ref - cells_ref.min(axis=0),
    page_cells_yx=cells_ref,
    scan_points_yx=cells_ref.astype(np.float64) * 4.0)
patch_stub = SimpleNamespace(
    patch_id=5, candidate=SimpleNamespace(page=0))
label_o = o_anchor._label_site_rows(spec8, 0, patch_stub, aligned_stub, {})
label_win = cr.RegionWindow(
    5, ("cap", 0, 0, (0, 0, 0, 0)), 0, aligned_stub.local_cells_yx,
    cells_ref, aligned_stub.scan_points_yx, (120, 120),
    (4.0, 0.0, 0.0, 0.0, 4.0, 0.0), 4.0)
label_m = cr.build_label_rows(row8, geom8, label_win)
check("label_rows_present", (label_m is None) == (label_o is None), "")
if label_m is not None and label_o is not None:
    eq_arr("label_cells", label_m.page_cells_yx, label_o.page_cells_yx)
    eq_arr("label_states", label_m.states, label_o.states)
    eq_arr("label_kinds", label_m.furniture_kind, label_o.furniture_kind)
    eq_arr("label_bits", label_m.known_component_bits,
           label_o.known_component_bits)
    eq_arr("label_mask", label_m.known_component_mask,
           label_o.known_component_mask)

# pool masks
mask_o = o_pool._payload_cell_mask(spec8, cells_ref)
mask_m = cr.cargo_cell_mask(cr.cargo_site_mask(geom8), cells_ref)
eq_arr("cargo_mask", mask_m, mask_o)
codes = np.asarray([1, 26], np.int64)
emit_o = o_pool._emission_mask(spec8, 0, cells_ref, {0: codes})
emit_m = cr.emission_mask(row8, cells_ref, codes)
eq_arr("emission_mask", emit_m, emit_o)

# projection oracle via src core kernels
counter = row8.tile_counter(0, 1, 2)
users8 = tuple(
    rng.integers(0, 2, fact.user_bits).astype(np.uint8)
    for fact in row8.streams)
certs8 = {
    (0, 1, 2, fact.stream_id): h3_data.Certificate(
        0, 1, 2, fact.stream_id, users8[index], "test")
    for index, fact in enumerate(row8.streams)}
bits_m, known_m = cr.certified_projection(row8, geom8, 0, 1, 2, certs8)
order_o = o_keystream.color_cell_permutation(
    spec8.seed, counter, spec8.payload_cells)
payload_flat_o = o_pilots.color_payload_cell_indices(spec8.family_seed)
flat_bits_m = bits_m.reshape(4096, 3)
flat_known_m = known_m.reshape(4096, 3)
for plane, profile in enumerate(spec8.stream_profiles):
    seq = o_encode_frame(users8[plane], profile.fec)
    seq = seq ^ o_keystream.cmy8_dither_bits(
        spec8.seed, profile.stream_id, counter,
        profile.fec.transmitted_bits)
    eq_arr(f"projection_cmy8_plane[{plane}]",
           flat_bits_m[payload_flat_o, plane], seq[order_o])
check("projection_cmy8_known", bool(flat_known_m.all()), "")
word_o, dust_o = o_pilots.color_site_cells_yx(spec8.family_seed)
word_states_o = o_pilots.color_word_states(spec8.seed, (counter,))[0]
eq_arr("projection_word_states",
       h3_tile_codec.planes_to_states(bits_m[word_o[:, 0], word_o[:, 1]]),
       word_states_o)
dust_states_o = o_pilots.dust_state_values(
    spec8.seed, (counter,), spec8.codec)[0]
eq_arr("projection_dust_states",
       h3_tile_codec.planes_to_states(bits_m[dust_o[:, 0], dust_o[:, 1]]),
       dust_states_o)

counter7 = row7.tile_counter(0, 2, 3)
user7 = rng.integers(0, 2, row7.streams[0].user_bits).astype(np.uint8)
certs7 = {(0, 2, 3, "main"): h3_data.Certificate(
    0, 2, 3, "main", user7, "test")}
bits7_m, known7_m = cr.certified_projection(row7, geom7, 0, 2, 3, certs7)
fec7 = spec7.stream_profiles[0].fec
seq7 = o_color_tile.cmy7_encode_payload(
    user7, fec7,
    o_keystream.cmy7_interleave_permutation(
        spec7.seed, counter7, fec7.transmitted_bits),
    o_keystream.cmy7_dither_bits(
        spec7.seed, counter7, fec7.transmitted_bits))
order7 = o_keystream.color_cell_permutation(
    spec7.seed, counter7, spec7.payload_cells)
payload_flat7 = o_pilots.color_payload_cell_indices(spec7.family_seed)
eq_arr("projection_cmy7_states",
       h3_tile_codec.planes_to_states(
           bits7_m.reshape(4096, 3)[payload_flat7]),
       seq7[order7])
check("projection_cmy7_known",
      bool(known7_m.reshape(4096, 3)[payload_flat7].all()), "")

# build_window_rows overlay wiring on a certified tile
tile_cells_yy, tile_cells_xx = np.mgrid[64:128, 128:192]
tile_cells = np.stack(
    (tile_cells_yy.ravel(), tile_cells_xx.ravel()), axis=1).astype(np.int64)
win_c = cr.RegionWindow(
    2, ("cap", 0, 0, (0, 0, 0, 0)), 0, tile_cells - (64, 128), tile_cells,
    tile_cells.astype(np.float64), (64, 64),
    (4.0, 0.0, 0.0, 0.0, 4.0, 0.0), 4.0)
rows_c = cr.build_window_rows(row8, geom8, win_c, certs8, {})
check("window_rows_all_known",
      bool(rows_c.known_component_mask.all())
      and bool((rows_c.states >= 0).all()), "")
eq_arr("window_rows_states_match_projection",
       rows_c.states,
       h3_tile_codec.planes_to_states(bits_m.reshape(4096, 3)).astype(
           np.int8))
partial_certs = {(0, 1, 2, "C"): certs8[(0, 1, 2, "C")]}
rows_p = cr.build_window_rows(row8, geom8, win_c, partial_certs, {})
cargo = cr.cargo_cell_mask(cr.cargo_site_mask(geom8), tile_cells)
check("window_rows_partial_state",
      bool((rows_p.states[cargo] == -1).all()), "")
eq_arr("window_rows_partial_mask",
       rows_p.known_component_mask[cargo],
       np.stack((np.ones(cargo.sum(), bool),
                 np.zeros(cargo.sum(), bool),
                 np.zeros(cargo.sum(), bool)), axis=1))

# =====================================================================
# 6. full ladder parity, cmy7 and cmy8 (incl. dead plane).
# =====================================================================
STATE_BITS8 = ((np.arange(8)[:, None] >> np.arange(3)[None, :]) & 1)


def build_ladder_region(n_states, rng, noise=0.05, dead_plane=None,
                        sep=0.55, heldout_noise=None,
                        payload_ambiguous=False):
    windows3 = []
    features = []
    for index, (oy, ox) in enumerate(((0, 0), (0, 45))):
        height, width = 60, 50
        n = height * width
        hidden = rng.integers(0, n_states, n).astype(np.int64)
        states, kinds = synth_labels(n, n_states, rng, 0.6)
        labelled = states >= 0
        hidden[labelled] = states[labelled]
        window = make_window(index + 1, 0, oy, ox, height, width,
                             states, kinds)
        bits = STATE_BITS8[hidden % 8].astype(np.float64)
        if dead_plane is not None:
            bits[:, dead_plane] = 0.0
        means = 0.9 - sep * bits
        if heldout_noise is None:
            cell_noise = np.full(n, noise)
        else:
            parity = h3_site_parity(window.page_cells_yx[:, 0],
                                    window.page_cells_yx[:, 1]) == 0
            cell_noise = np.where(parity, noise, heldout_noise)
        feats = means + rng.normal(0.0, 1.0, (n, 3)) * cell_noise[:, None]
        if payload_ambiguous:
            ambiguous = ~labelled
            feats[ambiguous] = 0.9 - sep * rng.uniform(
                0.35, 0.65, (int(ambiguous.sum()), 3))
        windows3.append(window)
        features.append(feats)
    return tuple(windows3), tuple(features)


def run_ladder_parity(tag, spec_o, row_h, n_states, rng, noise=0.05,
                      dead_plane=None, sep=0.55, heldout_noise=None,
                      payload_ambiguous=False):
    rows3, base = build_ladder_region(
        n_states, rng, noise, dead_plane, sep, heldout_noise,
        payload_ambiguous)
    rows_o = make_src_rows(rows3)
    masks = tuple(np.ones(r.states.size, bool) for r in rows3)
    sel3 = cr.owner_selection(rows3)
    sel_o = o_fitting._owner_selection(rows_o)
    eq_arr(f"{tag}_sel_search", sel3.search, sel_o.search)
    stack3 = cr.fit_region_stack(
        row_h, sel3, rows3, base, None, masks, cr.StackConfig())
    arms = o_stack.ArmFeatures(base=base, corrected=None)
    zero3 = tuple(o_reg.PlaneResidual((0.0, 0.0), (0.0, 0.0), 0)
                  for _ in range(3))
    result_o = o_stack.fit_region_stack(
        spec_o, sel_o, rows_o, arms, zero3, emission_masks=masks)
    fit_o = result_o.selected_fit
    fit_m = stack3.selected
    check(f"{tag}_fit_present", (fit_m is None) == (fit_o is None), "")
    if fit_m is None or fit_o is None:
        return
    eq_arr(f"{tag}_qda_means", fit_m.model.means, fit_o.model.means)
    check(f"{tag}_heldout_loss",
          fit_m.heldout_loss == fit_o.heldout_loss,
          f"{fit_m.heldout_loss} vs {fit_o.heldout_loss}")
    check(f"{tag}_word_dust_loss",
          fit_m.word_heldout_loss == fit_o.word_heldout_loss
          and fit_m.dust_heldout_loss == fit_o.dust_heldout_loss, "")
    head_m = fit_m.cmy7_head
    head_o = fit_o.cmy7_head
    check(f"{tag}_head_present", (head_m is None) == (head_o is None),
          f"{stack3.head_reason} vs {result_o.head_reason}")
    if head_m is not None and head_o is not None:
        check(f"{tag}_head_scale", head_m.scale == head_o.scale,
              f"{head_m.scale} vs {head_o.scale}")
        eq_arr(f"{tag}_head_offsets", head_m.offsets, head_o.offsets)
    check(f"{tag}_head_saturation",
          stack3.head_saturation == result_o.head_saturation_fraction,
          f"{stack3.head_saturation} vs "
          f"{result_o.head_saturation_fraction}")
    ctx_m = fit_m.context
    ctx_o = fit_o.context
    check(f"{tag}_ctx_present", (ctx_m is None) == (ctx_o is None),
          f"{stack3.ctx_verdict and stack3.ctx_verdict.reason} vs "
          f"{result_o.context.reason}")
    if ctx_m is not None and ctx_o is not None:
        eq_arr(f"{tag}_ctx_offsets", ctx_m.offsets, ctx_o.offsets)
        eq_arr(f"{tag}_ctx_applied", ctx_m.applied, ctx_o.applied)
    bins_m = stack3.context_bins
    bins_o = result_o.context_bins
    check(f"{tag}_bins_present", (bins_m is None) == (bins_o is None), "")
    if bins_m is not None and bins_o is not None:
        for index in range(len(bins_m)):
            eq_arr(f"{tag}_bins[{index}]", bins_m[index], bins_o[index])
    for index, (row3, feats, emit) in enumerate(zip(rows3, base, masks)):
        bins_row = None if bins_m is None else bins_m[index][emit]
        values_m, div_m = cr.evidence_with_divisor(
            fit_m, feats[emit], bins_row)
        values_o, div_o = fit_o.evidence_with_divisor(
            feats[emit], None, None,
            None if bins_o is None else bins_o[index][emit])
        eq_arr(f"{tag}_evidence[{index}]", values_m, values_o)
        check(f"{tag}_divisor[{index}]",
              (div_m is None) == (div_o is None)
              and (div_m is None or np.array_equal(div_m, div_o)), "")
        loss_m = cr.window_loss(fit_m.model, row3, feats,
                                fit_m.heldout_loss)
        loss_o = o_fitting._window_loss(fit_o.model, rows_o[index], feats,
                                        fit_o.heldout_loss)
        check(f"{tag}_window_loss[{index}]", loss_m == loss_o,
              f"{loss_m} vs {loss_o}")
    if dead_plane is not None and fit_m.detector is not None:
        check(f"{tag}_dead_plane_unsupported",
              not fit_m.detector.supported_planes[dead_plane], "")
        values_m, _div = cr.evidence_with_divisor(
            fit_m, base[0], None if bins_m is None else bins_m[0])
        check(f"{tag}_dead_plane_zero",
              bool((values_m[:, dead_plane] == 0.0).all()), "")


rng_l = np.random.default_rng(7)
run_ladder_parity("ladder7", spec7, row7, 7, rng_l, noise=0.05)
rng_l2 = np.random.default_rng(11)
run_ladder_parity("ladder7_noisy", spec7, row7, 7, rng_l2, noise=0.28)
rng_l3 = np.random.default_rng(13)
run_ladder_parity("ladder8", spec8, row8, 8, rng_l3, noise=0.07)
rng_l4 = np.random.default_rng(17)
run_ladder_parity("ladder8_dead", spec8, row8, 8, rng_l4, noise=0.07,
                  dead_plane=2)
rng_l5 = np.random.default_rng(41)
run_ladder_parity("ladder7_head", spec7, row7, 7, rng_l5, noise=0.05,
                  heldout_noise=0.16)
rng_l6 = np.random.default_rng(43)
run_ladder_parity("ladder7_satfloor", spec7, row7, 7, rng_l6, noise=0.06,
                  sep=0.20, heldout_noise=0.15, payload_ambiguous=True)

# exact-null identity: a refused corrected arm keeps the base tuple object
rng_n = np.random.default_rng(23)
rows_n, base_n = build_ladder_region(7, rng_n, 0.05)
sel_n = cr.owner_selection(rows_n)
masks_n = tuple(np.ones(r.states.size, bool) for r in rows_n)
bad = tuple(rng_n.normal(0.5, 0.5, f.shape) for f in base_n)
stack_n = cr.fit_region_stack(
    row7, sel_n, rows_n, base_n, bad, masks_n, cr.StackConfig())
check("refused_arm_same_object", stack_n.features is base_n,
      f"adopted={stack_n.adopted}")

# improves() parity on synthetic loss triples
for trial in range(30):
    a = SimpleNamespace(
        heldout_loss=float(rng.normal(1.0, 0.001)),
        word_heldout_loss=float(rng.normal(1.0, 0.001)),
        dust_heldout_loss=float(rng.normal(1.0, 0.001)))
    b = SimpleNamespace(
        heldout_loss=float(rng.normal(1.0, 0.001)),
        word_heldout_loss=float(rng.normal(1.0, 0.001)),
        dust_heldout_loss=float(rng.normal(1.0, 0.001)))
    check(f"improves[{trial}]",
          cr.improves(a, b) == o_stack._improves(a, b), "")

# =====================================================================
# 7. region_job end-to-end smoke on a painted synthetic capture.
# =====================================================================
scratch = Path(tempfile.mkdtemp(prefix="verify-color-region-",
                                dir=os.environ.get("TMPDIR", "/tmp")))
CELLS = 128
PX_PER_CELL = 4
BORDER = 32
SIZE = CELLS * PX_PER_CELL + 2 * BORDER
truth = np.zeros((CELLS, CELLS), np.uint8)
ref_yy, ref_xx = np.mgrid[0:CELLS, 0:CELLS]
ref_cells = np.stack((ref_yy.ravel(), ref_xx.ravel()), axis=1).astype(
    np.int64)
ref_states, ref_kinds = cm.reference_states(row8, geom8, 0, ref_cells)
rng_p = np.random.default_rng(31)
grid_states = rng_p.integers(0, 8, CELLS * CELLS).astype(np.int64)
grid_states[ref_states >= 0] = ref_states[ref_states >= 0]
cert_c = {(0, 0, 0, "C"): h3_data.Certificate(
    0, 0, 0, "C",
    rng_p.integers(0, 2, row8.streams[0].user_bits).astype(np.uint8),
    "test")}
cert_full = {
    (0, 0, 1, fact.stream_id): h3_data.Certificate(
        0, 0, 1, fact.stream_id,
        rng_p.integers(0, 2, fact.user_bits).astype(np.uint8), "test")
    for fact in row8.streams}
all_certs = dict(cert_c)
all_certs.update(cert_full)
proj_c = cr.certified_projection(row8, geom8, 0, 0, 0, all_certs)
proj_full = cr.certified_projection(row8, geom8, 0, 0, 1, all_certs)
grid_bits = STATE_BITS8[grid_states].astype(np.uint8).reshape(
    CELLS, CELLS, 3)
grid_bits[0:64, 0:64, 0] = proj_c[0][..., 0]
grid_bits[0:64, 64:128, :] = proj_full[0]
paint = np.empty((SIZE, SIZE, 3), np.uint8)
for plane in range(3):
    cell_values = np.where(grid_bits[..., plane] > 0, 60, 230).astype(
        np.uint8)
    block = np.kron(cell_values,
                    np.ones((PX_PER_CELL, PX_PER_CELL), np.uint8))
    page = np.full((SIZE, SIZE), 235, np.uint8)
    page[BORDER:BORDER + CELLS * PX_PER_CELL,
         BORDER:BORDER + CELLS * PX_PER_CELL] = block
    noise = rng_p.integers(-6, 7, (SIZE, SIZE)).astype(np.int16)
    paint[..., plane] = np.clip(
        page.astype(np.int16) + noise, 0, 255).astype(np.uint8)
plane_rasters = []
for index, name in enumerate(("r", "g", "b")):
    path = scratch / f"l00-{name}.npy"
    np.save(path, paint[..., index])
    plane_rasters.append(h3_data.PlaneRaster("cap0", 0, name, path,
                                             (SIZE, SIZE)))
affine_job = (float(PX_PER_CELL), 0.0, BORDER + PX_PER_CELL / 2.0,
              0.0, float(PX_PER_CELL), BORDER + PX_PER_CELL / 2.0)
job_window = cr.RegionWindow(
    1, ("cap0", 0, 0, (0, 0, CELLS, CELLS)), 0, ref_cells, ref_cells,
    cra.pose_points(affine_job, ref_cells.astype(np.float64)),
    (CELLS, CELLS), affine_job, float(PX_PER_CELL))
result = cr.region_job(
    row8, geom8, (job_window,), (), tuple(plane_rasters), all_certs,
    cr.StackConfig(), "cap0", 0)
evidence_rows = [fact for fact in result.facts
                 if isinstance(fact, h3_data.ColorEvidenceRow)]
models = [fact for fact in result.facts
          if isinstance(fact, cr.RegionColorModel)]
check("job_emits", len(evidence_rows) == 1 and len(models) == 1,
      f"{len(evidence_rows)} rows {len(models)} models")
if evidence_rows and models:
    model = models[0]
    check("job_accepted", model.accepted, model.reason)
    rowfact = evidence_rows[0]
    emitted_tiles = np.unique(
        (rowfact.page_cells_yx[:, 0] // 64) * row8.tiles_yx[1]
        + rowfact.page_cells_yx[:, 1] // 64)
    check("job_suppresses_certified_tile",
          1 not in emitted_tiles.tolist(), f"{emitted_tiles}")
    cargo_rows = cr.cargo_row_indices(geom8, rowfact.page_cells_yx)
    cargo_cells = rowfact.page_cells_yx[cargo_rows]
    cargo_values = rowfact.values[cargo_rows]
    painted = grid_bits[cargo_cells[:, 0], cargo_cells[:, 1]]
    live = [plane for plane in range(3)
            if models[0].detector.supported_planes[plane]]
    agree = np.mean([
        np.mean((cargo_values[:, plane] > 0) == (painted[:, plane] > 0))
        for plane in live]) if live else 0.0
    check("job_sign_agreement", agree > 0.8,
          f"agreement {agree:.3f} live={live}")
    check("job_values_finite_f32",
          rowfact.values.dtype == np.float32
          and bool(np.isfinite(rowfact.values).all()), "")

prune = cr.region_job(
    row8, geom8, (job_window,), (), tuple(plane_rasters),
    {(0, ty, tx, fact.stream_id): h3_data.Certificate(
        0, ty, tx, fact.stream_id,
        np.zeros(fact.user_bits, np.uint8), "test")
     for ty in range(2) for tx in range(2) for fact in row8.streams},
    cr.StackConfig(), "cap0", 0)
check("job_terminal_prune",
      not prune.facts and len(prune.events) == 1
      and prune.events[0].reason == "fully_certified_pruned", "")

print(f"{CHECKS} checks, {len(FAILS)} failures")
if FAILS:
    raise SystemExit(1)
print("verify_color_region: ALL GREEN")
