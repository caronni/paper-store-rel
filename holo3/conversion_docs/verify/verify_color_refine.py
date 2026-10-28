"""verify_color_refine.py — the colour refinement lane (holo3/plugins/color_refine.py).

Run:
  cd <checkout> && \
    PYTHONPATH=.:src env314t/bin/python _distill/verify/verify_color_refine.py

Sections:
  A  constants vs the v1 oracle (src/holo color_refine)
  B  label flattening parity vs v1 collect_color_refinement_labels on a real
     fossil row with REAL v1 certificate records (full / partial / none)
  C  support ladder + pose-site cap parity
  D  sampling parity (filtered crop + mode-nearest plane sampling)
  E  full-flow parity: refine_color_window vs a v1-KERNEL-DRIVEN
     transcription of color_refine.refine_color_window (v1 owns every
     numeric step)
  F  e2e mini on a rendered synthetic CMY8 window from format truth
  G  native-affine recomposition round-trips through region_window
  H  scheduling: reach key, eligibility gates
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from holo3 import data as h3_data  # noqa: E402
from holo3.format import identity as h3_identity  # noqa: E402
from holo3.format import tile_codec as h3_tile_codec  # noqa: E402
from holo3.plugins import color_model as cm  # noqa: E402
from holo3.plugins import color_refine as mine  # noqa: E402
from holo3.plugins import color_region as cr  # noqa: E402
from holo3.plugins import color_region_anchor as anchor  # noqa: E402
from holo3.plugins import refine as h3_refine  # noqa: E402

from holo.format.resolve import resolve_format_ref as o_resolve  # noqa: E402
from holo.receive import certified_refine as v1  # noqa: E402
from holo.receive import color_refine as v1c  # noqa: E402
from holo.receive import color_sampling as o_sampling  # noqa: E402
from holo.receive._payload_sampling import _WindowRows  # noqa: E402
from holo.receive.placement.model import AffinePose as V1Pose  # noqa: E402
from holo.receive.records import (  # noqa: E402
    certificate_record_from_user_bits,
)

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL {name} {detail}")
    else:
        print(f"  ok   {name}")


def eq(a, b) -> bool:
    return np.array_equal(np.asarray(a), np.asarray(b))


ROW8 = h3_identity.resolve_format_ref("L:c3-cmy8-p120-v0@2240x1536")
GEOM8 = h3_identity.build_site_geometry(ROW8)
SPEC8 = o_resolve("L:c3-cmy8-p120-v0@2240x1536")
ROW7 = h3_identity.resolve_format_ref("L:c3-cmy7-p120-v0@2240x1536")
GEOM7 = h3_identity.build_site_geometry(ROW7)
SPEC7 = o_resolve("L:c3-cmy7-p120-v0@2240x1536")
PAGE = 0
PITCH = 7.0
PAPER = 232.0
INK = 46.0


# ------------------------------------------------------------- A: constants

def section_constants() -> None:
    print("A. constants")
    check("FURNITURE_LOSS_SLACK == v1",
          mine.FURNITURE_LOSS_SLACK == v1c.FURNITURE_LOSS_SLACK == 1e-9)
    check("plane token mix == v1",
          np.uint64(mine.PLANE_TOKEN_MIX) == v1c._PLANE_TOKEN_MIX)
    shared = ["BLOCK_CELLS", "MIN_CERTIFIED_BLOCKS", "MIN_HELDOUT_GAIN",
              "MIN_PAYLOAD_TRAIN", "MIN_PAYLOAD_VALIDATION",
              "MIN_POSE_PILOTS", "MIN_TRAIN_PER_CLASS",
              "MIN_VALIDATION_PER_CLASS", "POSE_SITE_CAP_TRAIN",
              "POSE_SITE_CAP_VALIDATION"]
    bad = [n for n in shared
           if getattr(mine, n) != getattr(v1c, n)]
    check("shared floors == v1 colour namespace", not bad, str(bad))
    grid = ["ANGLE_LIMIT_DEG", "ANGLE_COARSE_STEP_DEG", "ANGLE_FINE_STEP_DEG",
            "PHASE_LIMIT_CELLS", "PHASE_COARSE_STEP_CELLS",
            "PHASE_FINE_STEP_CELLS"]
    bad = [n for n in grid if getattr(h3_refine, n) != getattr(v1c, n)]
    check("grid constants (imported from K row) == v1 colour namespace",
          not bad, str(bad))
    check("SCORE_SPREAD_FLOOR == v1 _payload_sampling",
          mine.SCORE_SPREAD_FLOOR == 1e-6)
    check("cap hash constants shared with K",
          (mine.CAP_HASH_Y, mine.CAP_HASH_X)
          == (11400714819323198485, 14029467366897019727))


# ---------------------------------------------------------------- fixtures

def mint_pair(row, spec, page, ty, tx, stream_ids, rng):
    """Matching (holo3 Certificate dict, v1 TileCertificateRecord tuple)."""
    h3_certs = {}
    v1_records = []
    for fact in row.streams:
        if fact.stream_id not in stream_ids:
            continue
        user = rng.integers(0, 2, fact.user_bits).astype(np.uint8)
        h3_certs[(page, ty, tx, fact.stream_id)] = h3_data.Certificate(
            page, ty, tx, fact.stream_id, user, "test")
        v1_records.append(certificate_record_from_user_bits(
            spec, page=page, tile_yx=(ty, tx), stream_id=fact.stream_id,
            user_bits=user, origin_attempt_id="verify-color-refine"))
    return h3_certs, tuple(v1_records)


def window_cells(ty0, tx0, tiles_y, tiles_x):
    yy, xx = np.mgrid[ty0 * 64:(ty0 + tiles_y) * 64,
                      tx0 * 64:(tx0 + tiles_x) * 64]
    return np.stack((yy.ravel(), xx.ravel()), axis=1).astype(np.int64)


def region_window_for(cells, affine, pitch):
    local = cells - cells.min(axis=0)
    shape = (int(local[:, 0].max()) + 1, int(local[:, 1].max()) + 1)
    return cr.RegionWindow(
        0, ("cap", 0, 0, (0, 0, shape[0], shape[1])), PAGE, local, cells,
        anchor.pose_points(affine, local), shape, affine, pitch)


def labels_pair(row, geom, spec, cells, h3_certs, v1_records_by_tile):
    window = region_window_for(cells, (PITCH, 0.0, 40.0, 0.0, PITCH, 40.0),
                               PITCH)
    rows = cr.build_window_rows(row, geom, window, h3_certs, {})
    labels_m = mine.collect_labels(PAGE, rows.page_cells_yx,
                                   rows.furniture_kind,
                                   rows.known_component_bits,
                                   rows.known_component_mask)
    rows_v1 = _WindowRows(0, window.local_cells_yx, cells,
                          window.scan_points_yx)
    labels_o = v1c.collect_color_refinement_labels(
        spec, PAGE, rows_v1, v1_records_by_tile)
    return labels_m, labels_o


def compare_labels(tag, labels_m, labels_o) -> None:
    check(f"labels[{tag}].row_indices",
          eq(labels_m.row_indices, labels_o.row_indices))
    check(f"labels[{tag}].planes", eq(labels_m.planes, labels_o.planes))
    check(f"labels[{tag}].cells",
          eq(labels_m.page_cells_yx, labels_o.page_cells_yx))
    check(f"labels[{tag}].bits", eq(labels_m.bits, labels_o.bits))
    check(f"labels[{tag}].validation",
          eq(labels_m.validation, labels_o.validation))
    check(f"labels[{tag}].weights", eq(labels_m.weights, labels_o.weights))
    check(f"labels[{tag}].is_furniture",
          eq(labels_m.is_furniture, labels_o.is_furniture))
    check(f"labels[{tag}].block_ids",
          eq(labels_m.block_ids, labels_o.block_ids))


def section_labels() -> None:
    print("B. label flattening vs v1 collect_color_refinement_labels")
    rng = np.random.default_rng(8291)
    cells = window_cells(3, 4, 2, 2)

    full_h3 = {}
    full_v1 = {}
    for ty, tx in ((3, 4), (3, 5), (4, 4)):
        certs, records = mint_pair(ROW8, SPEC8, PAGE, ty, tx,
                                   ("C", "M", "Y"), rng)
        full_h3.update(certs)
        full_v1[(PAGE, ty, tx)] = records
    compare_labels("cmy8-full", *labels_pair(ROW8, GEOM8, SPEC8, cells,
                                             full_h3, full_v1))

    part_h3, part_records = mint_pair(ROW8, SPEC8, PAGE, 3, 4, ("M",), rng)
    compare_labels("cmy8-partial",
                   *labels_pair(ROW8, GEOM8, SPEC8, cells, part_h3,
                                {(PAGE, 3, 4): part_records}))

    compare_labels("furniture-only",
                   *labels_pair(ROW8, GEOM8, SPEC8, cells, {}, {}))

    certs7, records7 = mint_pair(ROW7, SPEC7, PAGE, 3, 4, ("main",), rng)
    compare_labels("cmy7", *labels_pair(ROW7, GEOM7, SPEC7, cells, certs7,
                                        {(PAGE, 3, 4): records7}))


# ------------------------------------------------------- C: floors and caps

def as_v1_labels(labels_m):
    return v1c.ColorRefinementLabels(
        labels_m.row_indices, labels_m.planes, labels_m.page_cells_yx,
        labels_m.bits, labels_m.validation, labels_m.weights,
        labels_m.is_furniture, labels_m.block_ids, ())


def section_floors() -> None:
    print("C. support ladder + pose-site cap")
    rng = np.random.default_rng(31)
    cells = window_cells(3, 4, 2, 2)
    full_h3 = {}
    full_v1 = {}
    for ty, tx in ((3, 4), (3, 5), (4, 4)):
        certs, records = mint_pair(ROW8, SPEC8, PAGE, ty, tx,
                                   ("C", "M", "Y"), rng)
        full_h3.update(certs)
        full_v1[(PAGE, ty, tx)] = records
    labels_m, _ = labels_pair(ROW8, GEOM8, SPEC8, cells, full_h3, full_v1)
    labels_o = as_v1_labels(labels_m)
    got = mine.support_metrics(labels_m)
    want = v1c._support_metrics(labels_o)
    check("support_metrics rich", got == want[:2], f"{got} vs {want[:2]}")
    for validation in (False, True):
        check(f"select_pose_sites validation={validation}",
              eq(mine.select_pose_sites(labels_m, validation),
                 v1c.select_color_pose_sites(labels_o, validation)))

    part_h3, part_records = mint_pair(ROW8, SPEC8, PAGE, 3, 4, ("Y",), rng)
    labels_m, _ = labels_pair(ROW8, GEOM8, SPEC8, cells, part_h3,
                              {(PAGE, 3, 4): part_records})
    labels_o = as_v1_labels(labels_m)
    got = mine.support_metrics(labels_m)
    want = v1c._support_metrics(labels_o)
    check("support_metrics single-stream", got == want[:2],
          f"{got} vs {want[:2]}")
    labels_m, _ = labels_pair(ROW8, GEOM8, SPEC8, cells, {}, {})
    labels_o = as_v1_labels(labels_m)
    got = mine.support_metrics(labels_m)
    want = v1c._support_metrics(labels_o)
    check("support_metrics furniture-only refuses payload floor",
          got == want[:2] and got[1] == "insufficient_payload_train",
          f"{got} vs {want[:2]}")


# ------------------------------------------------------------- D: sampling

def section_sampling() -> None:
    print("D. sampling parity")
    rng = np.random.default_rng(5)
    raw = rng.integers(20, 240, (300, 320, 3)).astype(np.uint8)
    planes = (raw[..., 0], raw[..., 1], raw[..., 2])
    points = np.stack((rng.uniform(-10.0, 320.0, 900),
                       rng.uniform(-10.0, 340.0, 900)), axis=1)
    y0, x0, cropped = anchor.native_crop(planes, points, 9)
    crop_o = o_sampling.filtered_crop(y0, x0, cropped, PITCH, 1.0)
    filtered_m = anchor.filtered_rgb(cropped, PITCH, 1.0)
    check("filtered crop bit-exact", eq(filtered_m, crop_o.filtered))
    got = anchor.sample_rgb(filtered_m, y0, x0, points)
    want = v1c._sample_planes(crop_o, points)
    check("mode-nearest plane sampling bit-exact", eq(got, want))


# -------------------------------------------- synthetic CMY8 window render

def window_truth_bits(row, geom, cells, h3_certs, rng):
    states, kinds = cm.reference_states(row, geom, PAGE, cells)
    bits = rng.integers(0, 2, (cells.shape[0], 3)).astype(np.uint8)
    furniture = kinds >= 0
    bits[furniture] = h3_tile_codec.states_to_planes(states[furniture])
    tiles_x = row.tiles_yx[1]
    code = (cells[:, 0] // 64) * tiles_x + cells[:, 1] // 64
    for one in np.unique(code):
        ty, tx = divmod(int(one), tiles_x)
        projection = cr.certified_projection(row, geom, PAGE, ty, tx,
                                             h3_certs)
        if projection is None:
            continue
        projected_bits, projected_known = projection
        selected = np.flatnonzero(code == one)
        ly = cells[selected, 0] % 64
        lx = cells[selected, 1] % 64
        tile_bits = projected_bits[ly, lx]
        tile_known = projected_known[ly, lx]
        current = bits[selected]
        current[tile_known] = tile_bits[tile_known]
        bits[selected] = current
    return bits, kinds


def build_color_window(seed=21, n_certified=3, angle_deg=0.35, noise=18.0,
                       cargo_shift_cells=(0.0, 0.0)):
    rng = np.random.default_rng(seed)
    ty0, tx0 = 3, 4
    cells = window_cells(ty0, tx0, 2, 2)
    addresses = [(ty0, tx0), (ty0, tx0 + 1), (ty0 + 1, tx0),
                 (ty0 + 1, tx0 + 1)]
    h3_certs = {}
    v1_index = {}
    for ty, tx in addresses[:n_certified]:
        certs, records = mint_pair(ROW8, SPEC8, PAGE, ty, tx,
                                   ("C", "M", "Y"), rng)
        h3_certs.update(certs)
        v1_index[(PAGE, ty, tx)] = records
    bits, kinds = window_truth_bits(ROW8, GEOM8, cells, h3_certs, rng)
    local = cells - cells.min(axis=0)
    height, width = 128, 128
    bit_page = np.zeros((height, width, 3), np.uint8)
    bit_page[local[:, 0], local[:, 1]] = bits
    cargo_page = np.zeros((height, width), bool)
    cargo_page[local[:, 0], local[:, 1]] = kinds < 0

    theta = np.deg2rad(angle_deg)
    linear = PITCH * np.asarray(((np.cos(theta), np.sin(theta)),
                                 (-np.sin(theta), np.cos(theta))),
                                np.float64)
    corners = np.asarray(((0, 0), (0, width), (height, 0), (height, width)),
                         np.float64) @ linear.T
    halo = 14.0
    offset = np.asarray((-np.floor(corners[:, 0].min()) + halo,
                         -np.floor(corners[:, 1].min()) + halo), np.float64)
    affine = (float(linear[0, 0]), float(linear[0, 1]), float(offset[0]),
              float(linear[1, 0]), float(linear[1, 1]), float(offset[1]))
    shape = (int(np.ceil(corners[:, 0].max() - corners[:, 0].min()
                         + 2 * halo)),
             int(np.ceil(corners[:, 1].max() - corners[:, 1].min()
                         + 2 * halo)))
    ys, xs = np.meshgrid(np.arange(shape[0], dtype=np.float64),
                         np.arange(shape[1], dtype=np.float64),
                         indexing="ij")
    inverse = np.linalg.inv(linear)
    dy = ys - offset[0]
    dx = xs - offset[1]
    cy = inverse[0, 0] * dy + inverse[0, 1] * dx
    cx = inverse[1, 0] * dy + inverse[1, 1] * dx
    rgb = np.full(shape + (3,), PAPER, np.float64)
    gy = np.rint(cy - cargo_shift_cells[0]).astype(np.int64)
    gx = np.rint(cx - cargo_shift_cells[1]).astype(np.int64)
    inside = ((gy >= 0) & (gy < height) & (gx >= 0) & (gx < width))
    sy = np.clip(gy, 0, height - 1)
    sx = np.clip(gx, 0, width - 1)
    gy0 = np.rint(cy).astype(np.int64)
    gx0 = np.rint(cx).astype(np.int64)
    inside0 = ((gy0 >= 0) & (gy0 < height) & (gx0 >= 0) & (gx0 < width))
    sy0 = np.clip(gy0, 0, height - 1)
    sx0 = np.clip(gx0, 0, width - 1)
    furniture_px = inside0 & ~cargo_page[sy0, sx0]
    for plane in range(3):
        cargo_ink = (inside & cargo_page[sy, sx]
                     & (bit_page[sy, sx, plane] == 1))
        rgb[cargo_ink, plane] = INK
        rgb[furniture_px & (bit_page[sy0, sx0, plane] == 1), plane] = INK
        rgb[furniture_px & (bit_page[sy0, sx0, plane] == 0), plane] = PAPER
    for plane in range(3):
        rgb[..., plane] = ndimage.gaussian_filter(
            rgb[..., plane], 0.25 * PITCH, mode="nearest")
    rgb = rgb + rng.normal(0.0, noise, rgb.shape)
    planes = (rgb[..., 0], rgb[..., 1], rgb[..., 2])
    return dict(cells=cells, local=local, affine=affine, planes=planes,
                h3_certs=h3_certs, v1_index=v1_index)


def perturbed_affine(affine, dtheta_deg, du, dv):
    moved = h3_refine.pose_candidate(mine.window_pose(affine), dtheta_deg,
                                     du, dv)
    jac = moved.matrix()
    return (float(jac[0, 0]), float(jac[0, 1]), float(moved.origin_yx[0]),
            float(jac[1, 0]), float(jac[1, 1]), float(moved.origin_yx[1]))


def make_placement(window: cr.RegionWindow, affine) -> h3_data.Placement:
    return h3_data.Placement(window.window_id, "cap", 0, 0, 0, PAGE, 0,
                             (192, 256), affine, PITCH, "chain",
                             np.asarray(window.local_cells_yx, np.int64))


def run_mine(fixture, affine):
    window = region_window_for(fixture["cells"], affine, PITCH)
    placement = make_placement(window, affine)
    return mine.refine_color_window(ROW8, GEOM8, window, fixture["planes"],
                                    fixture["h3_certs"], placement,
                                    Fraction(1), PITCH)


# -------------------------------------------- the v1-kernel reference flow

def v1_reference_flow(fixture, affine):
    """color_refine.refine_color_window's body, on v1's own kernels."""
    cells = fixture["cells"]
    local = (cells - cells.min(axis=0)).astype(np.float64)
    rows_v1 = _WindowRows(0, local.astype(np.int64), cells,
                          anchor.pose_points(affine, local))
    labels = v1c.collect_color_refinement_labels(SPEC8, PAGE, rows_v1,
                                                 fixture["v1_index"])
    supported, reason, _counts = v1c._support_metrics(labels)
    if not supported:
        return (False, reason, None, 0.0, 0.0, 0.0, None, None, 0)
    base = mine.window_pose(affine)
    pose0 = V1Pose(base.origin_yx, base.jacobian_yx, base.phase_yx,
                   base.pitch_px, base.angle_deg)
    y0, x0, raw = anchor.native_crop(
        fixture["planes"],
        anchor.window_points((128, 128), affine),
        anchor.window_halo(PITCH))
    crop = o_sampling.filtered_crop(y0, x0, raw, PITCH, 1.0)
    baseline_points = pose0.points(local)
    inside = ((baseline_points[:, 0] >= crop.y0)
              & (baseline_points[:, 1] >= crop.x0)
              & (baseline_points[:, 0] <= crop.y0 + crop.filtered.shape[0]
                 - 1)
              & (baseline_points[:, 1] <= crop.x0 + crop.filtered.shape[1]
                 - 1))
    if not bool(np.all(inside)):
        return (False, "baseline_outside_crop", None, 0.0, 0.0, 0.0, None,
                None, 0)
    baseline_all = v1c._sample_planes(crop, baseline_points)
    midpoint = np.median(baseline_all, axis=0)
    spread = np.maximum(np.mean(np.abs(baseline_all - midpoint), axis=0),
                        1e-6)
    train_pos = v1c.select_color_pose_sites(labels, validation=False)
    valid_pos = v1c.select_color_pose_sites(labels, validation=True)
    train_furniture = train_pos[labels.is_furniture[train_pos]]
    valid_furniture = valid_pos[labels.is_furniture[valid_pos]]
    if (train_furniture.size < v1c.MIN_POSE_PILOTS
            or valid_furniture.size < v1c.MIN_POSE_PILOTS):
        return (False, "insufficient_pose_pilot_validation", None, 0.0,
                0.0, 0.0, None, None, 0)

    def flat_scores(samples_by_row, row_lookup, positions):
        planes_sel = labels.planes[positions]
        values = samples_by_row[row_lookup, planes_sel]
        return (midpoint[planes_sel] - values) / spread[planes_sel]

    train_rows_idx = labels.row_indices[train_pos]
    train_unique, train_inverse = np.unique(train_rows_idx,
                                            return_inverse=True)
    train_local = local[train_unique]
    train_bits = labels.bits[train_pos]
    train_weights = labels.weights[train_pos]
    valid_rows_idx = labels.row_indices[valid_pos]
    valid_bits = labels.bits[valid_pos]
    valid_weights = labels.weights[valid_pos]
    furniture_in_valid = labels.is_furniture[valid_pos]
    furniture_bits = valid_bits[furniture_in_valid]
    furniture_weights = valid_weights[furniture_in_valid]
    base_valid_scores = flat_scores(baseline_all, valid_rows_idx, valid_pos)
    base_loss = v1._weighted_logloss(base_valid_scores, valid_bits,
                                     valid_weights)
    base_furniture_loss = v1._weighted_logloss(
        base_valid_scores[furniture_in_valid], furniture_bits,
        furniture_weights)

    candidates: dict = {}

    def score_candidate(dtheta, du, dv):
        key = tuple(round(float(value), 12) for value in (dtheta, du, dv))
        if key in candidates:
            return
        pose = v1._pose_candidate(pose0, *key)
        samples = v1c._sample_planes(crop, pose.points(train_local))
        scores = flat_scores(samples, train_inverse, train_pos)
        contrast = v1._pose_objective(-scores, train_bits, train_weights)
        loss = v1._weighted_logloss(scores, train_bits, train_weights)
        candidates[key] = contrast, loss

    def select_best(keys):
        rows_ = tuple(keys)
        maximum = max(candidates[key][0] for key in rows_)
        near = [key for key in rows_
                if maximum - candidates[key][0] <= 1e-9]
        return min(near, key=lambda key: (candidates[key][1],
                                          sum(v * v for v in key),
                                          tuple(abs(v) for v in key), key))

    coarse_angles = np.arange(-v1c.ANGLE_LIMIT_DEG,
                              v1c.ANGLE_LIMIT_DEG + 1e-12,
                              v1c.ANGLE_COARSE_STEP_DEG)
    coarse_phase = np.arange(-v1c.PHASE_LIMIT_CELLS,
                             v1c.PHASE_LIMIT_CELLS + 1e-12,
                             v1c.PHASE_COARSE_STEP_CELLS)
    for dtheta in coarse_angles:
        for du in coarse_phase:
            for dv in coarse_phase:
                score_candidate(float(dtheta), float(du), float(dv))
    best_coarse = select_best(candidates)
    fine_angles = np.arange(best_coarse[0] - v1c.ANGLE_COARSE_STEP_DEG,
                            best_coarse[0] + v1c.ANGLE_COARSE_STEP_DEG
                            + 1e-12, v1c.ANGLE_FINE_STEP_DEG)
    fine_du = np.arange(best_coarse[1] - v1c.PHASE_COARSE_STEP_CELLS,
                        best_coarse[1] + v1c.PHASE_COARSE_STEP_CELLS
                        + 1e-12, v1c.PHASE_FINE_STEP_CELLS)
    fine_dv = np.arange(best_coarse[2] - v1c.PHASE_COARSE_STEP_CELLS,
                        best_coarse[2] + v1c.PHASE_COARSE_STEP_CELLS
                        + 1e-12, v1c.PHASE_FINE_STEP_CELLS)
    for dtheta in fine_angles:
        if abs(dtheta) > v1c.ANGLE_LIMIT_DEG + 1e-12:
            continue
        for du in fine_du:
            if abs(du) > v1c.PHASE_LIMIT_CELLS + 1e-12:
                continue
            for dv in fine_dv:
                if abs(dv) <= v1c.PHASE_LIMIT_CELLS + 1e-12:
                    score_candidate(float(dtheta), float(du), float(dv))
    best = select_best(candidates)
    pose = v1._pose_candidate(pose0, *best)
    if pose == pose0:
        return (False, "active_pose_selected", None, 0.0, 0.0, 0.0,
                base_loss, None, len(candidates))
    valid_unique, valid_inverse = np.unique(valid_rows_idx,
                                            return_inverse=True)
    samples = v1c._sample_planes(crop, pose.points(local[valid_unique]))
    scores = flat_scores(samples, valid_inverse, valid_pos)
    loss = v1._weighted_logloss(scores, valid_bits, valid_weights)
    furniture_loss = v1._weighted_logloss(scores[furniture_in_valid],
                                          furniture_bits, furniture_weights)
    adopted = bool(
        loss + v1c.MIN_HELDOUT_GAIN < base_loss
        and furniture_loss
        <= base_furniture_loss + v1c.FURNITURE_LOSS_SLACK)
    return (adopted, "adopted" if adopted else "pose_gate_failed", pose,
            float(best[0]), float(best[1]), float(best[2]), base_loss, loss,
            len(candidates))


def section_flow() -> None:
    print("E. full-flow parity vs the v1-kernel reference")
    fixture = build_color_window(seed=31)
    standing = perturbed_affine(fixture["affine"], 0.08, 0.12, -0.12)
    got = run_mine(fixture, standing)
    want = v1_reference_flow(fixture, standing)
    check("flow: adopted", got.adopted == want[0], f"{got}")
    check("flow: reason", got.reason == want[1],
          f"{got.reason} vs {want[1]}")
    check("flow: deltas",
          (got.dtheta_deg, got.du_cells, got.dv_cells) == want[3:6],
          f"{(got.dtheta_deg, got.du_cells, got.dv_cells)} vs {want[3:6]}")
    check("flow: baseline logloss bit-exact",
          got.baseline_logloss == want[6],
          f"{got.baseline_logloss!r} vs {want[6]!r}")
    check("flow: candidate logloss bit-exact",
          got.candidate_logloss == want[7],
          f"{got.candidate_logloss!r} vs {want[7]!r}")
    check("flow: candidate count", got.candidates == want[8],
          f"{got.candidates} vs {want[8]}")
    if want[2] is not None and got.affine is not None:
        adopted_pose = mine.window_pose(standing)
        adopted_pose = h3_refine.pose_candidate(
            adopted_pose, got.dtheta_deg, got.du_cells, got.dv_cells)
        check("flow: adopted pose == v1 pose",
              adopted_pose.origin_yx == want[2].origin_yx
              and adopted_pose.jacobian_yx == want[2].jacobian_yx)


# ------------------------------------------------------------------ F: e2e

def section_e2e() -> None:
    print("F. e2e mini")
    fixture = build_color_window(seed=77)
    truth = fixture["affine"]
    standing = perturbed_affine(truth, 0.08, 0.12, -0.12)
    revision = run_mine(fixture, standing)
    print(f"     perturbed -> {revision.reason} deltas="
          f"{revision.dtheta_deg, revision.du_cells, revision.dv_cells}"
          f" loss {revision.baseline_logloss} -> "
          f"{revision.candidate_logloss}")
    check("e2e: perturbed pose adopts", revision.adopted, revision.reason)
    check("e2e: validation loss improves by the gain",
          revision.adopted
          and revision.candidate_logloss + mine.MIN_HELDOUT_GAIN
          < revision.baseline_logloss)
    check("e2e: revision undoes the perturbation direction",
          revision.adopted and revision.dtheta_deg < 0.0
          and revision.du_cells < 0.0 and revision.dv_cells > 0.0,
          f"{revision.dtheta_deg, revision.du_cells, revision.dv_cells}")
    if revision.adopted:
        base_true = mine.window_pose(truth)
        local = np.asarray(fixture["local"], np.float64)
        reference = base_true.points(local)

        def drift(affine) -> float:
            pose = mine.window_pose(affine)
            return float(np.hypot(
                *(pose.points(local) - reference).T).mean())

        window = region_window_for(fixture["cells"], standing, PITCH)
        placement = make_placement(window, standing)
        revised = h3_refine.revised_placement(placement, revision)
        store = SimpleNamespace(
            _placements={window.window_id: revised},
            _levels={("cap", 0): SimpleNamespace(scale=Fraction(1))},
            _row=ROW8)
        replayed = cr.region_window(store, window.window_id)
        was, now = drift(standing), drift(replayed.affine)
        print(f"     mean cell drift from truth {was:.4f} -> {now:.4f} px")
        check("e2e: revised placement replays materially closer to truth",
              now < was / 3.0, f"{now:.4f} vs {was:.4f}")
        check("e2e: revised placement carries the refine route",
              revised.route == mine.ROUTE_REFINE)

    at_truth = run_mine(fixture, truth)
    print(f"     unperturbed -> {at_truth.reason}")
    check("e2e: unperturbed pose refuses active_pose_selected",
          at_truth.reason == "active_pose_selected"
          and not at_truth.adopted, at_truth.reason)

    skew = build_color_window(seed=91, cargo_shift_cells=(0.0, 0.5))
    degraded = run_mine(skew, skew["affine"])
    print(f"     cargo/furniture skew -> {degraded.reason} deltas="
          f"{degraded.dtheta_deg, degraded.du_cells, degraded.dv_cells}")
    check("e2e: cargo-skew candidate refused at the gate",
          not degraded.adopted and degraded.reason == "pose_gate_failed",
          degraded.reason)
    skew_want = v1_reference_flow(skew, skew["affine"])
    check("e2e: skew refusal matches the v1-kernel reference",
          (degraded.adopted, degraded.reason,
           degraded.baseline_logloss, degraded.candidate_logloss)
          == (skew_want[0], skew_want[1], skew_want[6], skew_want[7]),
          f"{skew_want[:2]} {skew_want[6:8]}")

    empty = build_color_window(seed=55, n_certified=0)
    refused = run_mine(empty, empty["affine"])
    check("e2e: no certified cargo refuses on the payload floor",
          refused.reason == "insufficient_payload_train"
          and not refused.adopted, refused.reason)


# ----------------------------------------------------------- G: round trips

def section_roundtrip() -> None:
    print("G. native-affine recomposition through region_window")
    rng = np.random.default_rng(6)
    for rot_k in (0, 1, 2, 3):
        for scale in (Fraction(1), Fraction(2), Fraction(3)):
            shape = (128, 128)
            local = np.stack(np.meshgrid(np.arange(shape[0]),
                                         np.arange(shape[1]),
                                         indexing="ij"),
                             axis=-1).reshape(-1, 2).astype(np.int64)
            native = (6.9931, 0.0812, 921.5 + float(rng.uniform(-3, 3)),
                      -0.0812, 6.9931, 655.25 + float(rng.uniform(-3, 3)))
            placement = h3_data.Placement(
                ("cap", 0, 0, (0, 0, shape[0], shape[1])), "cap", 0, 0, 0,
                PAGE, rot_k, (192, 256), native, 6.9936, "chain", local)
            store = SimpleNamespace(
                _placements={placement.window_id: placement},
                _levels={("cap", 0): SimpleNamespace(scale=scale)},
                _row=ROW8)
            window = cr.region_window(store, placement.window_id)
            base = mine.window_pose(window.affine)
            moved = h3_refine.pose_candidate(base, 0.05, -0.125, 0.0625)
            native2 = mine.revised_native_affine(
                moved, rot_k, shape, placement.page_origin_yx, scale)
            store._placements[placement.window_id] = h3_data.Placement(
                placement.window_id, "cap", 0, 0, 0, PAGE, rot_k,
                (192, 256), native2, 6.9936, mine.ROUTE_REFINE, local)
            replayed = cr.region_window(store, placement.window_id)
            back = mine.window_pose(replayed.affine)
            check(f"round-trip rot_k={rot_k} scale={scale}",
                  np.allclose(back.origin_yx, moved.origin_yx, rtol=0.0,
                              atol=1e-8)
                  and np.allclose(back.jacobian_yx, moved.jacobian_yx,
                                  rtol=0.0, atol=1e-9),
                  f"{back.origin_yx} vs {moved.origin_yx}")
            identity = mine.revised_native_affine(
                base, rot_k, shape, placement.page_origin_yx, scale)
            check(f"identity recomposition rot_k={rot_k} scale={scale}",
                  np.allclose(identity, native, rtol=0.0, atol=1e-8),
                  f"{identity} vs {native}")


# ------------------------------------------------------------ H: scheduling

def section_scheduling() -> None:
    print("H. scheduling keys")
    cells = window_cells(3, 4, 2, 2)
    rng = np.random.default_rng(404)
    certs = {}
    for ty, tx in ((3, 4), (9, 9)):
        pair, _records = mint_pair(ROW8, SPEC8, PAGE, ty, tx, ("C", "Y"),
                                   rng)
        certs.update(pair)
    reach = mine.reach_streams(PAGE, cells, certs)
    check("reach_streams keeps only covered tiles, per stream",
          reach == ((PAGE, 3, 4, "C"), (PAGE, 3, 4, "Y")), str(reach))
    check("reach_streams sorted-stable",
          reach == tuple(sorted(reach)))
    suppressed = cr.suppressed_tile_codes(ROW8, certs, PAGE)
    check("partial streams never suppress a tile", suppressed.size == 0)
    full, _records = mint_pair(ROW8, SPEC8, PAGE, 3, 4, ("C", "M", "Y"),
                               rng)
    certs.update(full)
    suppressed = cr.suppressed_tile_codes(ROW8, certs, PAGE)
    check("fully-certified tile suppressed",
          suppressed.tolist() == [3 * ROW8.tiles_yx[1] + 4])
    emit = cr.emission_mask(ROW8, cells, suppressed)
    cargo = cr.cargo_cell_mask(cr.cargo_site_mask(GEOM8), cells)
    check("open cargo remains with one tile suppressed",
          bool(np.any(cargo & emit)))
    all_certs = {}
    for ty, tx in ((3, 4), (3, 5), (4, 4), (4, 5)):
        pair, _records = mint_pair(ROW8, SPEC8, PAGE, ty, tx,
                                   ("C", "M", "Y"), rng)
        all_certs.update(pair)
    suppressed = cr.suppressed_tile_codes(ROW8, all_certs, PAGE)
    emit = cr.emission_mask(ROW8, cells, suppressed)
    check("certified_complete: no open cargo when all four tiles close",
          not bool(np.any(cargo & emit)))


def main() -> int:
    section_constants()
    section_labels()
    section_floors()
    section_sampling()
    section_flow()
    section_e2e()
    section_roundtrip()
    section_scheduling()
    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    for failure in FAILURES:
        print(f"  FAILED {failure}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
