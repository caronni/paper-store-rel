"""verify_refine.py — P8 (holo3/plugins/refine.py) RF1.

Run:
  cd <checkout> && \
    PYTHONPATH=.:src:holo2/src env314t/bin/python _distill/verify/verify_refine.py

Sections:
  A  constants vs both oracles (src/holo certified_refine, holo2 refine_fit)
  B  kernel-by-kernel bit parity vs both oracles on synthetic populations
  C  label join parity vs holo2 collect_labels (duck-typed providers)
  D  geometry parity (local_segment / native_terms / sample_at) vs holo2 + v1
  E  full-flow parity: refine_window vs a v1-KERNEL-DRIVEN transcription of
     certified_refine.refine_segment (v1 owns every numeric step)
  F  e2e mini on a rendered synthetic K window from format truth
"""
from __future__ import annotations

import sys
import types
from fractions import Fraction

import numpy as np
from scipy import ndimage

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


# --------------------------------------------------------------- P7 surface
STUB_CALLS: list[tuple[int, int, int]] = []


def _stub_printed_cells_for(row, geometry, page, ty, tx, user_bits):
    STUB_CALLS.append((int(page), int(ty), int(tx)))
    rng = np.random.default_rng(page * 1000003 + ty * 1009 + tx * 9177)
    return rng.integers(0, 2, size=(64, 64), dtype=np.uint8)


TILES_REAL = True
try:
    import holo3.plugins.tiles as _tiles  # noqa: F401
    TILES_REAL = hasattr(_tiles, "printed_cells_for")
except Exception:
    TILES_REAL = False
if not TILES_REAL:
    _mod = types.ModuleType("holo3.plugins.tiles")
    _mod.printed_cells_for = _stub_printed_cells_for
    sys.modules["holo3.plugins.tiles"] = _mod

from holo3.data import Certificate, Placement, WindowEvidence  # noqa: E402
from holo3.format.identity import (  # noqa: E402
    build_site_geometry, resolve_format_ref,
)
from holo3.format import keystream, pilots as h3pilots  # noqa: E402
from holo3.lib import pava as h3pava  # noqa: E402
from holo3.plugins import refine  # noqa: E402

from holo2.solve import refine_fit as h2  # noqa: E402
from holo2.solve.place_model import AffinePose as H2Pose  # noqa: E402
from holo2.solve.reference import ReferencePage  # noqa: E402
from holo2.capture.footing_raster import (  # noqa: E402
    AreaPixelTransform, FootingFrame,
)
from holo.receive import certified_refine as v1  # noqa: E402
from holo.receive import detect as v1detect  # noqa: E402
from holo.receive.placement.model import AffinePose as V1Pose  # noqa: E402


# ------------------------------------------------------------- A: constants

def section_constants() -> None:
    print("A. constants")
    names = ["BLOCK_CELLS", "VALIDATION_MODULUS", "MIN_PAYLOAD_TRAIN",
             "MIN_PAYLOAD_VALIDATION", "MIN_TRAIN_PER_CLASS",
             "MIN_VALIDATION_PER_CLASS", "MIN_CERTIFIED_BLOCKS",
             "MIN_POSE_PILOTS", "MIN_HELDOUT_GAIN", "PILOT_MISMATCH_SLACK",
             "ANGLE_LIMIT_DEG", "ANGLE_COARSE_STEP_DEG", "ANGLE_FINE_STEP_DEG",
             "PHASE_LIMIT_CELLS", "PHASE_COARSE_STEP_CELLS",
             "PHASE_FINE_STEP_CELLS", "POSE_SITE_CAP_TRAIN",
             "POSE_SITE_CAP_VALIDATION"]
    bad = [n for n in names
           if not (getattr(refine, n) == getattr(v1, n) == getattr(h2, n))]
    check("constants == v1 == holo2", not bad, str(bad))
    check("SCORE_SPREAD_FLOOR == v1",
          refine.SCORE_SPREAD_FLOOR == h2.SCORE_SPREAD_FLOOR == 1e-6)
    check("stripe coefficients (odd 9177 ruling)",
          (refine.STRIPE_PAGE_COEFFICIENT, refine.STRIPE_Y_COEFFICIENT,
           refine.STRIPE_X_COEFFICIENT) == (104729, 1009, 9177))
    check("cap hash constants",
          (refine.CAP_HASH_Y, refine.CAP_HASH_X)
          == (11400714819323198485, 14029467366897019727))


# ---------------------------------------------------------------- fixtures

def make_labels(seed: int, n: int, page: int = 2):
    rng = np.random.default_rng(seed)
    cells = np.stack([rng.integers(0, 400, n), rng.integers(0, 400, n)],
                     axis=1).astype(np.int64)
    cells = np.unique(cells, axis=0)
    n = cells.shape[0]
    rows = np.arange(n, dtype=np.int64)
    is_pilot = rng.random(n) < 0.35
    values = rng.integers(0, 2, n).astype(np.uint8)
    validation = np.empty(n, bool)
    validation[is_pilot] = np.asarray(
        (cells[is_pilot, 0] * 131 + cells[is_pilot, 1] * 17) & 1, bool)
    validation[~is_pilot] = v1._block_validation(page, cells[~is_pilot])
    by = cells[:, 0] // 16
    bx = cells[:, 1] // 16
    block_ids = (is_pilot.astype(np.int64) * 10**12
                 + page * 10**9 + by * 10**4 + bx)
    weights = np.zeros(n, np.float64)
    weights[~validation] = v1._block_weights(block_ids[~validation])
    weights[validation] = v1._block_weights(block_ids[validation])
    mine = refine.SegmentLabels(rows, cells, values, validation, weights,
                                is_pilot, block_ids)
    theirs2 = h2.SegmentLabels(rows, cells, values, validation, weights,
                               is_pilot, block_ids)
    theirs1 = v1.SegmentLabels(rows, cells, values, validation, weights,
                               is_pilot, block_ids,
                               tuple(None if p else "a" * 64
                                     for p in is_pilot))
    return mine, theirs2, theirs1


# ----------------------------------------------------------------- B: kernels

def section_kernels() -> None:
    print("B. kernels")
    rng = np.random.default_rng(7)
    cells = np.stack([rng.integers(0, 3000, 5000),
                      rng.integers(0, 3000, 5000)], axis=1).astype(np.int64)
    for page in (0, 1, 5, 17):
        mine = refine.block_validation(page, cells)
        check(f"block_validation page={page}",
              eq(mine, v1._block_validation(page, cells))
              and eq(mine, h2.block_validation(page, cells)))
    ids = rng.integers(0, 40, 4000).astype(np.int64)
    check("block_weights",
          eq(refine.block_weights(ids), v1._block_weights(ids))
          and eq(refine.block_weights(ids), h2.block_weights(ids)))
    check("block_weights empty",
          eq(refine.block_weights(np.zeros(0, np.int64)),
             v1._block_weights(np.zeros(0, np.int64))))

    mine, l2, l1 = make_labels(11, 6000)
    ok, reason, counts = refine.support_metrics(mine)
    ok1, reason1, counts1 = v1._support_metrics(l1)
    ok2, reason2, counts2 = h2.support_metrics(l2)
    check("support_metrics",
          (ok, reason, counts) == (ok1, reason1, counts1) == (ok2, reason2,
                                                              counts2),
          f"{(ok, reason, counts)} vs {(ok1, reason1, counts1)}")
    for starved_n in (40, 200, 900):
        s_mine, s2, s1 = make_labels(starved_n, starved_n)
        check(f"support_metrics floors n={starved_n}",
              refine.support_metrics(s_mine)
              == v1._support_metrics(s1) == h2.support_metrics(s2))

    positions = np.flatnonzero(~mine.is_pilot)
    for cap in (0, 10, 500, positions.size, positions.size + 5):
        got = refine.deterministic_cap(positions, mine.page_cells_yx, cap)
        check(f"deterministic_cap cap={cap}",
              eq(got, v1._deterministic_cap(positions, l1, cap))
              and eq(got, h2.deterministic_cap(positions,
                                               l2.page_cells_yx, cap)))
    for validation in (False, True):
        got = refine.select_pose_sites(mine, validation)
        check(f"select_pose_sites validation={validation}",
              eq(got, v1.select_pose_sites(l1, validation))
              and eq(got, h2.select_pose_sites(l2, validation)))

    jac = ((6.9931, 0.0812), (-0.0812, 6.9931))
    matrix = np.asarray(jac, np.float64)
    base = refine.LocalPose(
        (13.25, -7.5), jac, (0.5, 0.75),
        0.5 * (float(np.hypot(*matrix[:, 0])) + float(np.hypot(*matrix[:, 1]))),
        float(np.degrees(np.arctan2(matrix[0, 1], matrix[1, 1]))))
    b2 = H2Pose(base.origin_yx, base.jacobian_yx, base.phase_yx,
                base.pitch_px, base.angle_deg)
    b1 = V1Pose(base.origin_yx, base.jacobian_yx, base.phase_yx,
                base.pitch_px, base.angle_deg)
    for key in ((0.0, 0.0, 0.0), (0.15, -0.25, 0.0625), (-0.05, 0.125, -0.1875),
                (0.0333, -0.0001, 0.2499)):
        mine_p = refine.pose_candidate(base, *key)
        p2 = h2.pose_candidate(b2, *key)
        p1 = v1._pose_candidate(b1, *key)
        same = (mine_p.origin_yx == p2.origin_yx == p1.origin_yx
                and mine_p.jacobian_yx == p2.jacobian_yx == p1.jacobian_yx
                and mine_p.phase_yx == p2.phase_yx == p1.phase_yx
                and mine_p.pitch_px == p2.pitch_px == p1.pitch_px
                and mine_p.angle_deg == p2.angle_deg == p1.angle_deg)
        check(f"pose_candidate {key}", same)
    check("pose_candidate zero is identity",
          refine.pose_candidate(base, 0.0, 0.0, 0.0) == base)

    means = rng.normal(180.0, 40.0, 3000)
    values = rng.integers(0, 2, 3000).astype(np.uint8)
    weights = rng.random(3000) + 0.1
    check("pose_objective",
          refine.pose_objective(means, values, weights)
          == v1._pose_objective(means, values, weights)
          == h2.pose_objective(means, values, weights))
    check("pose_objective one-class",
          refine.pose_objective(means, np.zeros(3000, np.uint8), weights)
          == v1._pose_objective(means, np.zeros(3000, np.uint8), weights)
          == -np.inf)
    logits = rng.normal(0.0, 4.0, 3000)
    check("weighted_logloss",
          refine.weighted_logloss(logits, values, weights)
          == v1._weighted_logloss(logits, values, weights)
          == h2.weighted_logloss(logits, values, weights))

    check("candidate_grid", refine.candidate_grid() == h2.candidate_grid())
    check("candidate_grid holds exact zero",
          (0.0, 0.0, 0.0) in refine.candidate_grid())
    check("candidate_grid size 27", len(refine.candidate_grid()) == 27)
    for coarse in refine.candidate_grid():
        if refine.fine_grid(coarse) != h2.fine_grid(coarse):
            check(f"fine_grid {coarse}", False)
            break
    else:
        check("fine_grid over every coarse key", True)

    keys = refine.candidate_grid()
    for trial in range(5):
        r = np.random.default_rng(100 + trial)
        table = {k: (float(r.normal()), float(r.normal())) for k in keys}
        tied = dict(table)
        for k in keys[:4]:
            tied[k] = (2.5, table[k][1])
        for name, tbl in (("plain", table), ("tied", tied)):
            check(f"select_best {name} {trial}",
                  refine.select_best(tbl, keys) == h2.select_best(tbl, keys))

    for a in (0.0, 0.1, -0.2):
        for b in (0.0, 0.005, -0.006):
            for c in (0.0, 0.004, 0.006):
                check_ok = (refine.adoption_gate(1.0, 1.0 - a, 0.1, 0.1 + b,
                                                 0.2, 0.2 + c)
                            == v1._adoption_gate(1.0, 1.0 - a, 0.1, 0.1 + b,
                                                 0.2, 0.2 + c))
                if not check_ok:
                    check(f"adoption_gate {a},{b},{c}", False)
                    return
    check("adoption_gate exhaustive vs v1", True)
    check("adoption_gate clause 1 binding",
          not refine.adoption_gate(1.0, 1.0 - 1e-5, 0.1, 0.1, 0.2, 0.2))
    check("adoption_gate clause 2 binding",
          not refine.adoption_gate(1.0, 0.5, 0.1, 0.1051, 0.2, 0.2))
    check("adoption_gate clause 3 (detector-free) binding",
          not refine.adoption_gate(1.0, 0.5, 0.1, 0.1, 0.2, 0.2051))
    check("adoption_gate passes all three",
          refine.adoption_gate(1.0, 0.5, 0.1, 0.1049, 0.2, 0.2049))


# --------------------------------------------------------------- C: labels

class _Provider:
    def __init__(self, page_obj: ReferencePage) -> None:
        self._page = page_obj

    def page(self, page: int) -> ReferencePage:
        return self._page


def section_labels() -> None:
    print("C. label join")
    rng = np.random.default_rng(3)
    page = 3
    height, width = 256, 256
    base_sites = rng.random((height, width)) < 0.03
    base_values = rng.integers(0, 2, (height, width)).astype(np.uint8)
    certified = {(0, 0), (1, 2), (2, 1), (3, 3), (0, 2)}
    printed = {(page, ty, tx): rng.integers(0, 2, (64, 64), dtype=np.uint8)
               for ty, tx in certified}
    cargo_mask = np.zeros((height, width), bool)
    rich_values = base_values.copy()
    for ty, tx in certified:
        y0, x0 = ty * 64, tx * 64
        block = np.ones((64, 64), bool)
        block &= ~base_sites[y0:y0 + 64, x0:x0 + 64]
        cargo_mask[y0:y0 + 64, x0:x0 + 64] = block
        field = printed[(page, ty, tx)]
        target = rich_values[y0:y0 + 64, x0:x0 + 64]
        target[block] = field[block]
    rich_sites = base_sites | cargo_mask

    cells = np.stack(np.meshgrid(np.arange(30, 230), np.arange(20, 220),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    cells = cells.astype(np.int64)
    reference = np.where(base_sites[cells[:, 0], cells[:, 1]],
                         base_values[cells[:, 0], cells[:, 1]].astype(np.int8),
                         np.int8(-1))

    mine = refine.collect_labels(page, cells, reference, printed)
    theirs = h2.collect_labels(
        page, cells, _Provider(ReferencePage(page, base_values, base_sites)),
        _Provider(ReferencePage(page, rich_values, rich_sites)))
    for field in ("rows", "page_cells_yx", "values", "validation", "weights",
                  "is_pilot", "block_ids"):
        check(f"collect_labels.{field}",
              eq(getattr(mine, field), getattr(theirs, field)))
    check("collect_labels weights positive", bool((mine.weights > 0).all()))
    check("collect_labels pilot half non-empty and cargo present",
          bool(mine.is_pilot.any() and (~mine.is_pilot).any()))
    frac = float(np.mean(mine.validation[~mine.is_pilot]))
    check("cargo holdout fraction ~ 1/4", 0.2 < frac < 0.3, f"{frac:.4f}")

    hits = refine.collect_labels(page, cells, reference, {})
    check("no certified tiles -> pilots only", not (~hits.is_pilot).any())


# ------------------------------------------------------------- D: geometry

def section_geometry() -> None:
    print("D. geometry")
    native = (6.9931, 0.0812, 921.5, -0.0812, 6.9931, 655.25)
    cells = np.stack(np.meshgrid(np.arange(64, 192), np.arange(128, 256),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    cells = cells.astype(np.int64)
    for scale in (Fraction(1), Fraction(2), Fraction(5, 2)):
        frame = (FootingFrame.native((4000, 4000)) if scale == 1
                 else FootingFrame(AreaPixelTransform(scale), (4000, 4000)))
        pose, local = refine.local_segment(native, scale, cells)
        segment, local2 = h2.local_segment(native, frame, cells)
        # Cell-EDGE convention (contract 07-2): holo3's local pose samples
        # cell CENTRES, so its origin is holo2's corner origin plus half a
        # cell through the level-frame jacobian.
        half = np.asarray(segment.pose.jacobian_yx,
                          np.float64) @ np.array([0.5, 0.5])
        expected = np.asarray(segment.pose.origin_yx, np.float64) + half
        check(f"local_segment origin == holo2 + half-cell s={scale}",
              np.allclose(pose.origin_yx, expected, rtol=0.0, atol=1e-9),
              f"{pose.origin_yx} vs {tuple(expected)}")
        check(f"local_segment jacobian s={scale}",
              pose.jacobian_yx == segment.pose.jacobian_yx)
        check(f"local_segment pitch/angle s={scale}",
              pose.pitch_px == segment.pose.pitch_px
              and pose.angle_deg == segment.pose.angle_deg)
        check(f"local_segment local cells s={scale}", eq(local, local2))
        back = refine.native_terms(pose, cells, scale)
        check(f"native_terms recovers the input s={scale}",
              np.allclose(back, native, rtol=0.0, atol=1e-9), f"{back}")
        moved = refine.pose_candidate(pose, 0.05, -0.125, 0.0625)
        rebuilt, _ = refine.local_segment(
            refine.native_terms(moved, cells, scale), scale, cells)
        check(f"native_terms/local_segment round-trip of candidate s={scale}",
              np.allclose(rebuilt.origin_yx, moved.origin_yx,
                          rtol=0.0, atol=1e-8)
              and np.allclose(rebuilt.jacobian_yx, moved.jacobian_yx,
                              rtol=0.0, atol=1e-9))

    rng = np.random.default_rng(5)
    filtered = rng.random((300, 400)).astype(np.float32) * 255.0
    pose = refine.LocalPose((12.5, 9.25), ((6.9931, 0.0812),
                                           (-0.0812, 6.9931)),
                            (0.0, 0.0), 6.9935, 0.665)
    small = np.stack(np.meshgrid(np.arange(30), np.arange(40),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    small = small.astype(np.int64)
    crop = (7, 11)
    got = refine.sample_at(filtered, crop, 231.0, pose, small)
    h2pose = H2Pose(pose.origin_yx, pose.jacobian_yx, pose.phase_yx,
                    pose.pitch_px, pose.angle_deg)
    check("sample_at == holo2 sample_at",
          eq(got, h2.sample_at(filtered, crop, 231.0, h2pose, small)))
    image = v1.RefinementRegionImage(0, crop[0], crop[1], (400, 500),
                                     filtered, 231.0)
    v1pose = V1Pose(pose.origin_yx, pose.jacobian_yx, pose.phase_yx,
                    pose.pitch_px, pose.angle_deg)
    check("sample_at == v1 _sample widened",
          eq(got.astype(np.float32), v1._sample(image, v1pose, small)))
    off = rng.normal(0.0, 0.4, (small.shape[0], 2))
    check("offsets door: None is the identity",
          eq(refine.sample_at(filtered, crop, 231.0, pose, small, None), got))
    check("offsets door moves the read",
          not eq(refine.sample_at(filtered, crop, 231.0, pose, small, off),
                 got))


# ----------------------------------------------- the v1-kernel reference flow

def v1_reference_flow(image, base_pose_v1, local, labels_v1, calibration,
                      baseline_means):
    """certified_refine.refine_segment's body, on v1's own kernels."""
    supported, reason, _counts = v1._support_metrics(labels_v1)
    if not supported:
        return (False, reason, None, 0.0, 0.0, 0.0, None, None, 0)
    train_positions = v1.select_pose_sites(labels_v1, validation=False)
    valid_positions = v1.select_pose_sites(labels_v1, validation=True)
    train_rows = labels_v1.generation_rows[train_positions]
    valid_rows = labels_v1.generation_rows[valid_positions]
    train_local = local[train_rows]
    train_values = labels_v1.values[train_positions]
    train_weights = labels_v1.weights[train_positions]
    valid_values = labels_v1.values[valid_positions]
    valid_weights = labels_v1.weights[valid_positions]
    train_pilots = train_positions[labels_v1.is_pilot[train_positions]]
    valid_pilots = valid_positions[labels_v1.is_pilot[valid_positions]]
    if (train_pilots.size < v1.MIN_POSE_PILOTS
            or valid_pilots.size < v1.MIN_POSE_PILOTS):
        return (False, "insufficient_pose_pilot_validation", None,
                0.0, 0.0, 0.0, None, None, 0)
    pilot_valid_rows = labels_v1.generation_rows[valid_pilots]
    pilot_values = labels_v1.values[valid_pilots]

    midpoint = float(np.median(baseline_means))
    spread = max(float(np.abs(baseline_means - midpoint).mean()),
                 v1.SCORE_SPREAD_FLOOR)

    def logits_of(means):
        raw = np.asarray(means, np.float32)
        scores = ((np.float32(midpoint) - raw)
                  / np.float32(spread)).astype(np.float32, copy=False)
        return np.asarray(calibration.llr(scores), np.float64)

    base_logits = logits_of(baseline_means)
    base_loss = v1._weighted_logloss(base_logits[valid_rows], valid_values,
                                     valid_weights)
    base_pilot = float(np.mean(
        (base_logits[pilot_valid_rows] > 0.0) != (pilot_values > 0)))
    base_raw = float(np.mean(
        (baseline_means[pilot_valid_rows] < midpoint) != (pilot_values > 0)))

    candidates: dict = {}

    def score_candidate(dtheta, du, dv):
        key = tuple(round(float(value), 12) for value in (dtheta, du, dv))
        if key in candidates:
            return
        pose = v1._pose_candidate(base_pose_v1, *key)
        means = v1._sample(image, pose, train_local)
        contrast = v1._pose_objective(means, train_values, train_weights)
        scores = (midpoint - means) / spread
        loss = v1._weighted_logloss(calibration.llr(scores), train_values,
                                    train_weights)
        candidates[key] = contrast, loss

    def select_best(keys):
        rows = tuple(keys)
        maximum = max(candidates[key][0] for key in rows)
        near = [k for k in rows if maximum - candidates[k][0] <= 1e-9]
        return min(near, key=lambda k: (candidates[k][1],
                                        sum(v * v for v in k),
                                        tuple(abs(v) for v in k), k))

    coarse_angles = np.arange(-v1.ANGLE_LIMIT_DEG,
                              v1.ANGLE_LIMIT_DEG + 1e-12,
                              v1.ANGLE_COARSE_STEP_DEG)
    coarse_phase = np.arange(-v1.PHASE_LIMIT_CELLS,
                             v1.PHASE_LIMIT_CELLS + 1e-12,
                             v1.PHASE_COARSE_STEP_CELLS)
    for dtheta in coarse_angles:
        for du in coarse_phase:
            for dv in coarse_phase:
                score_candidate(float(dtheta), float(du), float(dv))
    best_coarse = select_best(candidates)
    fine_angles = np.arange(best_coarse[0] - v1.ANGLE_COARSE_STEP_DEG,
                            best_coarse[0] + v1.ANGLE_COARSE_STEP_DEG + 1e-12,
                            v1.ANGLE_FINE_STEP_DEG)
    fine_du = np.arange(best_coarse[1] - v1.PHASE_COARSE_STEP_CELLS,
                        best_coarse[1] + v1.PHASE_COARSE_STEP_CELLS + 1e-12,
                        v1.PHASE_FINE_STEP_CELLS)
    fine_dv = np.arange(best_coarse[2] - v1.PHASE_COARSE_STEP_CELLS,
                        best_coarse[2] + v1.PHASE_COARSE_STEP_CELLS + 1e-12,
                        v1.PHASE_FINE_STEP_CELLS)
    for dtheta in fine_angles:
        if abs(dtheta) > v1.ANGLE_LIMIT_DEG + 1e-12:
            continue
        for du in fine_du:
            if abs(du) > v1.PHASE_LIMIT_CELLS + 1e-12:
                continue
            for dv in fine_dv:
                if abs(dv) <= v1.PHASE_LIMIT_CELLS + 1e-12:
                    score_candidate(float(dtheta), float(du), float(dv))
    best = select_best(candidates)
    pose = v1._pose_candidate(base_pose_v1, *best)
    if pose == base_pose_v1:
        return (False, "active_pose_selected", None, 0.0, 0.0, 0.0,
                base_loss, None, len(candidates))
    means = v1._sample(image, pose, local)
    logits = logits_of(means)
    loss = v1._weighted_logloss(logits[valid_rows], valid_values,
                                valid_weights)
    pilot = float(np.mean(
        (logits[pilot_valid_rows] > 0.0) != (pilot_values > 0)))
    raw = float(np.mean((means[pilot_valid_rows] < midpoint)
                        != (pilot_values > 0)))
    adopted = v1._adoption_gate(base_loss, loss, base_pilot, pilot, base_raw,
                                raw)
    return (adopted, "adopted" if adopted else "pose_gate_failed", pose,
            float(best[0]), float(best[1]), float(best[2]), base_loss, loss,
            len(candidates))


# ------------------------------------------------------- synthetic K window

ROW = resolve_format_ref("L:c2-r0700@3392x2368")
GEOMETRY = build_site_geometry(ROW)
PAGE = 0
PITCH_PX = 7.0
PAPER = 232.0
INK = 46.0


def format_reference_values(page: int, cells: np.ndarray) -> np.ndarray:
    """v1 _payload_sampling.format_reference_values, on holo3 format code."""
    values = np.full(cells.shape[0], -1, np.int8)
    word_cells = np.asarray(GEOMETRY.word_cells_yx)
    kind = np.full((64, 64), -1, np.int64)
    site_index = np.zeros((64, 64), np.int64)
    kind[word_cells[:, 0], word_cells[:, 1]] = 0
    site_index[word_cells[:, 0], word_cells[:, 1]] = np.arange(
        word_cells.shape[0])
    extra = np.asarray(GEOMETRY.extra_cells_yx)
    if extra.size:
        kind[extra[:, 0], extra[:, 1]] = 1
    local_y = cells[:, 0] % 64
    local_x = cells[:, 1] % 64
    classes = kind[local_y, local_x]
    word_rows = np.flatnonzero(classes == 0)
    if word_rows.size:
        ty = cells[word_rows, 0] // 64
        tx = cells[word_rows, 1] // 64
        code = ty * ROW.tiles_yx[1] + tx
        for one in np.unique(code):
            selected = word_rows[code == one]
            cy, cx = divmod(int(one), ROW.tiles_yx[1])
            counter = ROW.tile_counter(page, cy, cx)
            word = h3pilots.word_values(ROW.seed, (counter,),
                                        keystream.PLANE_K)[0]
            values[selected] = word[site_index[local_y[selected],
                                               local_x[selected]]]
    filler_rows = np.flatnonzero(classes == 1)
    if filler_rows.size:
        values[filler_rows] = keystream.bits(
            ROW.seed, keystream.DOMAIN_FILLER_VALUES, keystream.PLANE_K, page,
            cells[filler_rows, 0], cells[filler_rows, 1]).astype(np.int8)
    return values


def build_window(tiles_y: int = 2, tiles_x: int = 2, ty0: int = 3,
                 tx0: int = 4, n_certified: int = 2, angle_deg: float = 0.35,
                 noise: float = 26.0, seed: int = 21,
                 mtf_cells: float = 0.25,
                 cargo_shift_cells: tuple[float, float] = (0.0, 0.0)):
    rng = np.random.default_rng(seed)
    cy0, cx0 = ty0 * 64, tx0 * 64
    height, width = tiles_y * 64, tiles_x * 64
    cells = np.stack(np.meshgrid(np.arange(cy0, cy0 + height),
                                 np.arange(cx0, cx0 + width),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    cells = cells.astype(np.int64)
    reference = format_reference_values(PAGE, cells)

    addresses = [(ty0 + i, tx0 + j) for i in range(tiles_y)
                 for j in range(tiles_x)]
    printed = {}
    for ty, tx in addresses[:n_certified]:
        printed[(PAGE, ty, tx)] = rng.integers(0, 2, (64, 64), dtype=np.uint8)

    ink_page = rng.integers(0, 2, (height, width)).astype(np.uint8)
    for (_p, ty, tx), field in printed.items():
        ink_page[(ty - ty0) * 64:(ty - ty0) * 64 + 64,
                 (tx - tx0) * 64:(tx - tx0) * 64 + 64] = field
    local = cells - np.asarray((cy0, cx0), np.int64)
    known = reference >= 0
    ink_page[local[known, 0], local[known, 1]] = reference[known].astype(
        np.uint8)
    cargo_flag = np.zeros((height, width), bool)
    cargo_flag[local[~known, 0], local[~known, 1]] = True

    theta = np.deg2rad(angle_deg)
    linear = PITCH_PX * np.asarray(((np.cos(theta), np.sin(theta)),
                                    (-np.sin(theta), np.cos(theta))),
                                   np.float64)
    corners = np.asarray(((0, 0), (0, width), (height, 0), (height, width)),
                         np.float64) @ linear.T
    halo = 12.0
    y0 = float(np.floor(corners[:, 0].min()) - halo)
    x0 = float(np.floor(corners[:, 1].min()) - halo)
    offset = np.asarray((-y0, -x0), np.float64)
    # Cell-EDGE convention (contract 07-2): the rendering below puts cell c's
    # centre at linear@c + offset, so the placement affine (corner map) is
    # that minus half a cell.
    native = (float(linear[0, 0]), float(linear[0, 1]),
              float(offset[0] - (linear @ np.asarray((cy0 + 0.5, cx0 + 0.5),
                                                     np.float64))[0]),
              float(linear[1, 0]), float(linear[1, 1]),
              float(offset[1] - (linear @ np.asarray((cy0 + 0.5, cx0 + 0.5),
                                                     np.float64))[1]))

    shape = (int(np.ceil(corners[:, 0].max() - corners[:, 0].min()
                         + 2 * halo)),
             int(np.ceil(corners[:, 1].max() - corners[:, 1].min()
                         + 2 * halo)))
    ys, xs = np.meshgrid(np.arange(shape[0], dtype=np.float64),
                         np.arange(shape[1], dtype=np.float64), indexing="ij")
    inverse = np.linalg.inv(linear)
    dy = ys - offset[0]
    dx = xs - offset[1]
    cy = inverse[0, 0] * dy + inverse[0, 1] * dx
    cx = inverse[1, 0] * dy + inverse[1, 1] * dx
    luma = np.full(shape, PAPER, np.float64)
    for shift, want_cargo in (((0.0, 0.0), False), (cargo_shift_cells, True)):
        gy = np.rint(cy - shift[0]).astype(np.int64)
        gx = np.rint(cx - shift[1]).astype(np.int64)
        inside = ((gy >= 0) & (gy < height) & (gx >= 0) & (gx < width))
        sy = np.clip(gy, 0, height - 1)
        sx = np.clip(gx, 0, width - 1)
        select = (inside & (cargo_flag[sy, sx] == want_cargo)
                  & (ink_page[sy, sx] == 1))
        luma[select] = INK
    luma = ndimage.gaussian_filter(luma, mtf_cells * PITCH_PX, mode="nearest")
    luma = luma + rng.normal(0.0, noise, shape)
    aperture = max(1, int(round(0.7 * PITCH_PX)))
    filtered = ndimage.uniform_filter(luma.astype(np.float32), size=aperture,
                                      mode="nearest")
    backing = float(np.median(luma[:8, :]))
    return dict(cells=cells, reference=reference, printed=printed,
                native=native, filtered=filtered, backing=backing,
                crop=(0, 0), ink_page=ink_page, local=local)


def fit_calibration(scores: np.ndarray, labels: np.ndarray):
    knots, probs = h3pava._pava_nodes(scores, labels)
    return knots, probs, int(scores.size)


def make_evidence(window, knots, probs, n_search) -> WindowEvidence:
    zero = np.zeros(0, np.float64)
    return WindowEvidence(
        ("cap", 0, 0, (0, 0, 0, 0)), "cap", 0, 0, 0, PAGE,
        window["cells"], zero, window["reference"], knots, probs, n_search,
        zero, zero, True, "", None, False)


def make_placement(window, affine) -> Placement:
    return Placement(("cap", 0, 0, (0, 0, 0, 0)), "cap", 0, 0, 0, PAGE, 0,
                     (0, 0), affine, PITCH_PX, "chain",
                     window["local"].astype(np.int64))


def perturbed_affine(window, dtheta_deg: float, du: float, dv: float):
    pose, _local = refine.local_segment(window["native"], Fraction(1),
                                        window["cells"])
    moved = refine.pose_candidate(pose, dtheta_deg, du, dv)
    return refine.native_terms(moved, window["cells"], Fraction(1))


def calibrated(window, affine):
    pose, local = refine.local_segment(affine, Fraction(1), window["cells"])
    means = refine.sample_at(window["filtered"], window["crop"],
                             window["backing"], pose, local)
    midpoint, spread = refine.score_reference(means)
    scores = refine.window_scores(means, midpoint, spread)
    labels = window["ink_page"][window["local"][:, 0],
                                window["local"][:, 1]].astype(np.float64)
    return means, scores, labels


# ---------------------------------------------------------------- E: flow

def section_flow() -> None:
    print("E. full-flow parity vs the v1-kernel reference")
    window = build_window(seed=31)
    truth = window["native"]
    standing = perturbed_affine(window, 0.08, 0.12, -0.12)
    _means, scores, labels = calibrated(window, truth)
    knots, probs, n_search = fit_calibration(scores, labels)
    evidence = make_evidence(window, knots, probs, n_search)
    placement = make_placement(window, standing)
    got = refine.refine_window(placement, evidence, window["filtered"],
                               window["crop"], window["backing"], Fraction(1),
                               window["printed"])

    labels_mine = refine.collect_labels(PAGE, window["cells"],
                                        window["reference"],
                                        window["printed"])
    labels_v1 = v1.SegmentLabels(
        labels_mine.rows, labels_mine.page_cells_yx, labels_mine.values,
        labels_mine.validation, labels_mine.weights, labels_mine.is_pilot,
        labels_mine.block_ids,
        tuple(None if p else "b" * 64 for p in labels_mine.is_pilot))
    pose, local = refine.local_segment(standing, Fraction(1), window["cells"])
    image = v1.RefinementRegionImage(0, 0, 0, window["filtered"].shape,
                                     window["filtered"], window["backing"])
    v1pose = V1Pose(pose.origin_yx, pose.jacobian_yx, pose.phase_yx,
                    pose.pitch_px, pose.angle_deg)
    baseline = v1._sample(image, v1pose, local)
    calibration = v1detect.Calibration("w", knots, probs, n_search)
    want = v1_reference_flow(image, v1pose, local, labels_v1, calibration,
                             baseline)

    check("flow: adopted", got.adopted == want[0], f"{got}")
    check("flow: reason", got.reason == want[1], f"{got.reason} vs {want[1]}")
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
        rebuilt = refine.native_terms(
            refine.LocalPose(want[2].origin_yx, want[2].jacobian_yx,
                             want[2].phase_yx, want[2].pitch_px,
                             want[2].angle_deg),
            window["cells"], Fraction(1))
        check("flow: adopted affine bit-exact", got.affine == rebuilt,
              f"{got.affine} vs {rebuilt}")


# ------------------------------------------------------------------ F: e2e

def gate_numbers(window, affine, evidence, best):
    pose, local = refine.local_segment(affine, Fraction(1), window["cells"])
    baseline = refine.sample_at(window["filtered"], window["crop"],
                                window["backing"], pose, local)
    midpoint, spread = refine.score_reference(baseline)
    knots = np.asarray(evidence.knots, np.float64)
    probs = np.asarray(evidence.probs, np.float64)
    labels = refine.collect_labels(PAGE, window["cells"], window["reference"],
                                   window["printed"])
    valid = refine.select_pose_sites(labels, validation=True)
    valid_pilots = valid[labels.is_pilot[valid]]
    valid_rows = labels.rows[valid]
    pilot_rows = labels.rows[valid_pilots]
    pilot_values = labels.values[valid_pilots]

    def numbers(means):
        logits = np.asarray(h3pava.calibration_llr(
            refine.window_scores(means, midpoint, spread), knots, probs),
            np.float64)
        loss = refine.weighted_logloss(logits[valid_rows],
                                       labels.values[valid],
                                       labels.weights[valid])
        pilot = float(np.mean(
            (logits[pilot_rows] > 0.0) != (pilot_values > 0)))
        raw = float(np.mean(
            (np.asarray(means, np.float32)[pilot_rows] < midpoint)
            != (pilot_values > 0)))
        return loss, pilot, raw

    candidate = refine.pose_candidate(pose, *best)
    means = refine.sample_at(window["filtered"], window["crop"],
                             window["backing"], candidate, local)
    return numbers(baseline), numbers(means)


def section_e2e() -> None:
    print("F. e2e mini")
    window = build_window(seed=77)
    truth = window["native"]
    _m, scores, labels = calibrated(window, truth)
    knots, probs, n_search = fit_calibration(scores, labels)
    evidence = make_evidence(window, knots, probs, n_search)

    standing = perturbed_affine(window, 0.08, 0.12, -0.12)
    placement = make_placement(window, standing)
    revision = refine.refine_window(placement, evidence, window["filtered"],
                                    window["crop"], window["backing"],
                                    Fraction(1), window["printed"])
    print(f"     perturbed -> {revision.reason} "
          f"deltas={revision.dtheta_deg, revision.du_cells, revision.dv_cells}"
          f" loss {revision.baseline_logloss} -> {revision.candidate_logloss}")
    check("e2e: perturbed pose adopts", revision.adopted, revision.reason)
    check("e2e: adopted loss improves by the gain",
          revision.adopted
          and revision.candidate_logloss + refine.MIN_HELDOUT_GAIN
          < revision.baseline_logloss)
    check("e2e: revision undoes the perturbation direction",
          revision.adopted and revision.dtheta_deg < 0.0
          and revision.du_cells < 0.0 and revision.dv_cells > 0.0,
          f"{revision.dtheta_deg, revision.du_cells, revision.dv_cells}")
    check("e2e: proposal inside the bound",
          abs(revision.dtheta_deg) <= refine.ANGLE_LIMIT_DEG + 1e-12
          and abs(revision.du_cells) <= refine.PHASE_LIMIT_CELLS + 1e-12
          and abs(revision.dv_cells) <= refine.PHASE_LIMIT_CELLS + 1e-12)
    if revision.adopted:
        exact, local = refine.local_segment(truth, Fraction(1),
                                            window["cells"])
        reference = exact.points(local.astype(np.float64))

        def drift(affine) -> float:
            pose = refine.local_segment(affine, Fraction(1),
                                        window["cells"])[0]
            return float(np.hypot(*(pose.points(local.astype(np.float64))
                                    - reference).T).mean())

        was, now = drift(standing), drift(revision.affine)
        print(f"     mean cell drift from truth {was:.4f} -> {now:.4f} px")
        check("e2e: revised geometry is materially closer to truth",
              now < was / 3.0, f"{now:.4f} vs {was:.4f}")
        check("e2e: revised placement carries the new affine",
              refine.revised_placement(placement, revision).native_affine
              == revision.affine)
        check("e2e: revised placement is otherwise the same window",
              refine.revised_placement(placement, revision).window_id
              == placement.window_id)

    at_truth = refine.refine_window(make_placement(window, truth), evidence,
                                    window["filtered"], window["crop"],
                                    window["backing"], Fraction(1),
                                    window["printed"])
    print(f"     unperturbed -> {at_truth.reason}")
    check("e2e: unperturbed pose refuses active_pose_selected",
          at_truth.reason == "active_pose_selected" and not at_truth.adopted,
          at_truth.reason)

    skew = build_window(seed=91, cargo_shift_cells=(0.0, 0.5))
    _m2, scores2, labels2 = calibrated(skew, skew["native"])
    knots2, probs2, n2 = fit_calibration(scores2, labels2)
    evidence2 = make_evidence(skew, knots2, probs2, n2)
    placement2 = make_placement(skew, skew["native"])
    degraded = refine.refine_window(placement2, evidence2, skew["filtered"],
                                    skew["crop"], skew["backing"],
                                    Fraction(1), skew["printed"])
    print(f"     pilot/cargo skew -> {degraded.reason} "
          f"deltas={degraded.dtheta_deg, degraded.du_cells, degraded.dv_cells}")
    check("e2e: pilot/cargo-skew candidate refused at the gate",
          not degraded.adopted and degraded.reason == "pose_gate_failed",
          degraded.reason)
    if degraded.reason == "pose_gate_failed":
        before, after = gate_numbers(
            skew, skew["native"], evidence2,
            (degraded.dtheta_deg, degraded.du_cells, degraded.dv_cells))
        print(f"     gate: loss {before[0]:.6f} -> {after[0]:.6f}"
              f"  pilot {before[1]:.4f} -> {after[1]:.4f}"
              f"  raw {before[2]:.4f} -> {after[2]:.4f}")
        check("e2e: the gate function refuses those exact numbers",
              not refine.adoption_gate(before[0], after[0], before[1],
                                       after[1], before[2], after[2]))
        clauses = (after[0] + refine.MIN_HELDOUT_GAIN < before[0],
                   after[1] <= before[1] + refine.PILOT_MISMATCH_SLACK,
                   after[2] <= before[2] + refine.PILOT_MISMATCH_SLACK)
        print(f"     binding clauses (gain, pilot, raw-pilot): {clauses}")
        check("e2e: at least one gate clause bound", not all(clauses))

    starved = build_window(seed=55, n_certified=0)
    _m3, scores3, labels3 = calibrated(starved, starved["native"])
    k3, p3, n3 = fit_calibration(scores3, labels3)
    empty = refine.refine_window(make_placement(starved, starved["native"]),
                                 make_evidence(starved, k3, p3, n3),
                                 starved["filtered"], starved["crop"],
                                 starved["backing"], Fraction(1),
                                 starved["printed"])
    check("e2e: no certified cargo refuses on the payload floor",
          empty.reason == "insufficient_payload_train" and not empty.adopted,
          empty.reason)


# ------------------------------------------------------------ G: scheduling

def section_scheduling() -> None:
    print("G. eligibility / tried key")
    cells = np.stack(np.meshgrid(np.arange(120, 260), np.arange(60, 200),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    cells = cells.astype(np.int64)
    reach = refine.reach_tiles(cells)
    check("reach_tiles", reach == ((1, 0), (1, 1), (1, 2), (1, 3), (2, 0),
                                   (2, 1), (2, 2), (2, 3), (3, 0), (3, 1),
                                   (3, 2), (3, 3), (4, 0), (4, 1), (4, 2),
                                   (4, 3)), str(reach))
    everything = frozenset((0, ty, tx) for ty, tx in reach)
    some = frozenset(list(everything)[:5])
    check("eligible needs an open tile",
          not refine.refine_eligible(0, cells, everything, False))
    check("eligible needs a certified tile",
          not refine.refine_eligible(0, cells, frozenset(), False))
    check("eligible with both", refine.refine_eligible(0, cells, some, False))
    check("a revision is never eligible",
          not refine.refine_eligible(0, cells, some, True))
    key_a = refine.attempt_key(("cap", 0, 0, (0, 0, 0, 0)), 0, cells, some)
    key_b = refine.attempt_key(("cap", 0, 0, (0, 0, 0, 0)), 0, cells,
                               frozenset(list(some) + [(0, 4, 3)]))
    check("attempt key is the certificate set", key_a != key_b)
    check("attempt key is stable and sorted",
          key_a == refine.attempt_key(("cap", 0, 0, (0, 0, 0, 0)), 0, cells,
                                      frozenset(reversed(list(some))))
          and list(key_a[1]) == sorted(key_a[1]))

    rng = np.random.default_rng(404)
    n_user = ROW.streams[0].user_bits
    stream = ROW.streams[0].stream_id
    certificates = [
        Certificate(0, ty, tx, stream,
                    rng.integers(0, 2, n_user, dtype=np.uint8), "tiles/scan")
        for ty, tx in ((1, 1), (1, 1), (2, 3))]
    STUB_CALLS.clear()
    fields = refine.certified_fields(ROW, GEOMETRY, certificates)
    check("certified_fields dedups by address",
          sorted(fields) == [(0, 1, 1), (0, 2, 3)])
    check("certified_fields yields 64x64 u8 bits",
          all(v.shape == (64, 64) and v.dtype == np.uint8
              and bool(np.isin(v, (0, 1)).all()) for v in fields.values()))
    if not TILES_REAL:
        check("certified_fields mints once per address",
              STUB_CALLS == [(0, 1, 1), (0, 2, 3)])
    else:
        from holo3.plugins.tiles import printed_cells_for
        check("certified_fields carries P7's printed field verbatim",
              eq(fields[(0, 1, 1)],
                 printed_cells_for(ROW, GEOMETRY, 0, 1, 1,
                                   certificates[0].user_bits))
              and eq(fields[(0, 2, 3)],
                     printed_cells_for(ROW, GEOMETRY, 0, 2, 3,
                                       certificates[2].user_bits)))


def main() -> int:
    print(f"P7 tiles module: {'real' if TILES_REAL else 'STUBBED (not built)'}")
    section_constants()
    section_kernels()
    section_labels()
    section_geometry()
    section_flow()
    section_e2e()
    section_scheduling()
    print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
    for failure in FAILURES:
        print(f"  FAILED {failure}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
