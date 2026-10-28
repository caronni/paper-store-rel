# Verify P2+P3 (plugins pose/place/words/cold) against holo2 / src-holo oracles.
# Run: cd <checkout> && \
#   PYTHONPATH=.:src:holo2/src env314t/bin/python _distill/verify/verify_placement.py
from __future__ import annotations

import math
import sys
from fractions import Fraction

import numpy as np
from scipy import ndimage

from holo3 import data as h3data
from holo3.format import keystream as h3ks
from holo3.format.identity import resolve_format_ref
from holo3.lib import geometry as h3geom
from holo3.plugins import cold as h3cold
from holo3.plugins import place as h3place
from holo3.plugins import pose as h3pose
from holo3.plugins import words as h3words

CHECKS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append(name)
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not ok:
        print("verify_placement: FAILED at", name)
        sys.exit(1)


# ---------------------------------------------------------------- oracles
import holo2.solve.pose_fit as o_pose_fit
import holo2.solve.pose_audit as o_pose_audit
import holo2.solve.place_admission as o_admission
import holo2.solve.place_shared as o_place_shared
import holo2.solve.placement as o_placement
import holo2.solve.words as o_words
import holo2.solve.cold as o_cold
import holo2.solve.reference as o_reference
from holo2.solve.place_model import (AffinePose, AttemptBudget,
                                     PlacementConfig, PoseSegment,
                                     PoseWindow, WordAttemptBudget)

from holo.format.resolve import resolve_format_ref as v1_resolve
from holo.receive.placement.reference import V1ReferenceField as V1RefField

CONFIG = PlacementConfig()
RNG = np.random.default_rng(20260828)


class FakeSpec:
    def __init__(self, row):
        self.seed = row.seed
        self.family_seed = row.family_seed
        self.plane = h3words.addressing_plane(row)
        self.cells_yx = row.cells_yx
        self.tiles_yx = row.tiles_yx
        self.n_filler = row.n_sites - 100
        self.max_pages = row.max_pages
        self._row = row

    def tile_address(self, counter):
        return self._row.tile_address(counter)


# ------------------------------------------------- 1. reference field parity
def verify_reference():
    for ref in ("L:c2-r0700@3392x2368", "L:c3-cmy7-p120-v0@2240x1536",
                "L:c2-cmy8-p120-v0@3328x2304"):
        spec = v1_resolve(ref)
        field_v1 = V1RefField(spec)
        row = resolve_format_ref(ref, n_pages=2)
        field_h3 = h3words.ReferenceField(row)
        for page in (0, 1):
            p_v1 = field_v1.page(page)
            p_h3 = field_h3.page(page)
            check(f"reference values {ref} page {page}",
                  np.array_equal(p_v1.values, p_h3.values))
            check(f"reference sites {ref} page {page}",
                  np.array_equal(p_v1.sites, p_h3.sites))
    # K row with filler sites (n_filler > 0) vs the holo2 reference oracle.
    row = resolve_format_ref("c2-k-r0700-p110@4x4", n_pages=2)
    spec = FakeSpec(row)
    field_o = o_reference.V1ReferenceField(spec)
    field_h3 = h3words.ReferenceField(row)
    for page in (0, 1):
        p_o = field_o.page(page)
        p_h3 = field_h3.page(page)
        check(f"reference K-filler values page {page}",
              np.array_equal(p_o.values, p_h3.values))
        check(f"reference K-filler sites page {page}",
              np.array_equal(p_o.sites, p_h3.sites))


# ------------------------------------------ 2. admission algebra + budgets
def verify_admission():
    for h in (1, 2, 49, 98, 147456, 250530, 250531, 1_700_000):
        mine = h3place.identifiability_support_floor(h, 0.08)
        theirs = o_admission.identifiability_support_floor(h, 0.08)
        check(f"identifiability floor H={h}", mine == theirs,
              f"{mine}")
        budget = AttemptBudget(h, 1e-3, 0.08, "verify")
        check(f"min_support H={h}",
              h3place.min_support_for(h) == budget.min_support,
              f"{h3place.min_support_for(h)}")
    for frag in ((200, 200), (70, 70), (200, 137)):
        for pages in (1, 3):
            for overhang in (True, False):
                mine = h3cold.hypothesis_count(
                    frag, (256, 256), pages, allow_overhang=overhang)
                theirs = o_admission.hypothesis_count(
                    frag, (256, 256), pages, allow_overhang=overhang)
                check(f"hypothesis_count {frag} p{pages} o{overhang}",
                      mine == theirs, f"{mine}")
    import holo2.solve.place_job as o_place_job
    base = AttemptBudget(49, 1e-3, 0.08, "verify")
    for tried, offered in ((0, 0), (0, 3), (5, 2), (11, 8)):
        theirs = o_place_job.pass_budget(
            base, tried=tried, offered=offered, words_spent=0)
        mine = h3place.pass_budget_hypotheses(tried, offered)
        check(f"pass_budget tried={tried} offered={offered}",
              mine == theirs.max_hypotheses, f"{mine}")
    sphere = sum(math.comb(100, e) for e in range(14))
    p_word = math.ldexp(float(sphere), 18 - 100)
    wb = WordAttemptBudget(147456, 1e-3, "verify")
    check("single-word probability",
          h3words.SINGLE_WORD_PROBABILITY == wb.single_word_probability
          and h3words.SINGLE_WORD_PROBABILITY == p_word)


# --------------------------------------------- 3. synthetic lattice texture
def render_lattice(bits: np.ndarray, jacobian: np.ndarray,
                   origin_yx: tuple[float, float],
                   shape_px: tuple[int, int],
                   paper: float = 235.0, ink: float = 80.0,
                   noise: float = 3.0, seed: int = 7) -> np.ndarray:
    inv = np.linalg.inv(jacobian)
    yy, xx = np.meshgrid(np.arange(shape_px[0], dtype=np.float64),
                         np.arange(shape_px[1], dtype=np.float64),
                         indexing="ij")
    py = yy - origin_yx[0]
    px = xx - origin_yx[1]
    cy = inv[0, 0] * py + inv[0, 1] * px
    cx = inv[1, 0] * py + inv[1, 1] * px
    iy = np.floor(cy).astype(np.int64)
    ix = np.floor(cx).astype(np.int64)
    inside = ((iy >= 0) & (iy < bits.shape[0])
              & (ix >= 0) & (ix < bits.shape[1]))
    img = np.full(shape_px, paper, np.float64)
    img[inside] = np.where(bits[iy[inside], ix[inside]] > 0, ink, paper)
    rng = np.random.default_rng(seed)
    img = img + rng.normal(0.0, noise, shape_px)
    return np.clip(np.rint(img), 0, 255).astype(np.uint8)


def make_pixels(luma_u8: np.ndarray, support: np.ndarray,
                origin_yx: tuple[int, int], cells: tuple[int, int],
                pitch: float, backing: float):
    luma = np.asarray(luma_u8, np.float32)
    mine = h3pose.window_pixels(luma, support, origin_yx, cells, pitch,
                                backing)
    theirs = o_pose_fit.PreparedRegion(
        0, 0, 0, mine.filled, mine.filtered, mine.support,
        float(backing), float(pitch), mine.aperture_px)
    # independent recomputation of the fill+filter chain
    filled = np.where(support, luma, np.float32(backing)).astype(
        np.float32, copy=False)
    aperture = max(1, int(round(CONFIG.aperture_cells * pitch)))
    filtered = np.asarray(ndimage.uniform_filter(
        filled, size=aperture, mode="nearest"))
    check("window_pixels fill/filter chain",
          np.array_equal(mine.filled, filled)
          and np.array_equal(mine.filtered, filtered)
          and mine.aperture_px == aperture)
    return mine, theirs


def verify_pose_kernel():
    global RENDER_BITS, RENDER_ORIGIN
    pitch = 7.83
    angle = np.deg2rad(0.4)
    jac = pitch * np.array([[np.cos(angle), -np.sin(angle)],
                            [np.sin(angle), np.cos(angle)]])
    bits = (RNG.random((260, 260)) < 0.5).astype(np.uint8)
    RENDER_BITS = bits
    RENDER_ORIGIN = (12.3, 9.7)
    img = render_lattice(bits, jac, RENDER_ORIGIN, (1900, 1900))
    support = np.ones(img.shape, bool)
    support[:, 1750:] = False
    wy, wx = 40, 52
    cells = (200, 200)
    mine, theirs = make_pixels(img, support, (wy, wx), cells, pitch, 231.0)
    window = PoseWindow(0, 0, (wy, wx), cells, 0, 0)
    fit_o = o_pose_fit.fit_window_pose(theirs, window, config=CONFIG,
                                       lattice_seed=None)
    fit_m = h3pose.fit_window_pose(mine, None)
    check("fit segment presence",
          (fit_o.segment is None) == (fit_m.segment is None))
    assert fit_o.segment is not None
    po, pm = fit_o.segment.pose, fit_m.segment.pose
    check("fit pose origin", po.origin_yx == pm.origin_yx,
          f"{pm.origin_yx}")
    check("fit pose jacobian", po.jacobian_yx == pm.jacobian_yx)
    check("fit pose phase/pitch/angle",
          po.phase_yx == pm.phase_yx and po.pitch_px == pm.pitch_px
          and po.angle_deg == pm.angle_deg)
    check("fit segment metrics",
          fit_o.segment.phase_contrast == fit_m.segment.phase_contrast
          and fit_o.segment.pitch_yx_px == fit_m.segment.pitch_yx_px
          and (fit_o.segment.orthogonality_error_deg
               == fit_m.segment.orthogonality_error_deg))
    check("fit seed rows",
          np.array_equal(fit_o.lattice_seed.matrix(), fit_m.lattice_seed)
          and np.array_equal(fit_o.unconditioned_seed.matrix(),
                             fit_m.unconditioned_seed))
    sample_o = o_pose_fit.sample_segment(theirs, fit_o.segment)
    sample_m = h3pose.sample_segment(mine, fit_m.segment)
    check("sample means", np.array_equal(sample_o.means, sample_m.means))
    check("sample mask/bits/evidence/midpoint",
          np.array_equal(sample_o.mask, sample_m.mask)
          and np.array_equal(sample_o.bits, sample_m.bits)
          and np.array_equal(sample_o.evidence, sample_m.evidence)
          and sample_o.midpoint == sample_m.midpoint)
    check("sample support cells",
          sample_o.segment.support_cells == sample_m.segment.support_cells)
    # offsets door: None is bit-identical, a zero array too
    zero = np.zeros((cells[0] * cells[1], 2), np.float64)
    sample_z = h3pose.sample_segment(mine, fit_m.segment, offsets_px=zero)
    check("offsets door zero-identical",
          np.array_equal(sample_z.means, sample_m.means))
    # prior_f arm, both sides, on the raw crop
    py1 = wy + int(round(cells[0] * pitch))
    px1 = wx + int(round(cells[1] * pitch))
    spectral = mine.filled[wy:py1, wx:px1]
    prior_rows = np.array([[1.0 / pitch, 0.0], [0.0, 1.0 / pitch]])
    rec_o = o_pose_fit.lattice_reciprocal(spectral, pitch,
                                          prior_f=prior_rows)
    rec_m = h3pose.lattice_reciprocal(spectral, pitch, prior_f=prior_rows)
    check("lattice_reciprocal prior_f arm", np.array_equal(rec_o, rec_m))
    rec_o2 = o_pose_fit.lattice_reciprocal(spectral, pitch)
    rec_m2 = h3pose.lattice_reciprocal(spectral, pitch)
    check("lattice_reciprocal blind arm", np.array_equal(rec_o2, rec_m2))
    # edge window (crop < 12 * prior px on a side): seed-only fit
    small = (10, 10)
    mine_s, theirs_s = make_pixels(img, support, (wy, wx), small, pitch,
                                   231.0)
    seed_o = fit_o.lattice_seed
    fit_os = o_pose_fit.fit_window_pose(
        theirs_s, PoseWindow(0, 0, (wy, wx), small, 0, 0), config=CONFIG,
        lattice_seed=seed_o)
    fit_ms = h3pose.fit_window_pose(mine_s, fit_m.lattice_seed)
    check("edge-window seeded fit",
          (fit_os.segment is None) == (fit_ms.segment is None)
          and (fit_os.segment is None
               or (fit_os.segment.pose.origin_yx
                   == fit_ms.segment.pose.origin_yx
                   and fit_os.segment.pose.jacobian_yx
                   == fit_ms.segment.pose.jacobian_yx)))
    check("edge-window proposes no unconditioned seed",
          fit_ms.unconditioned_seed is None
          and fit_os.unconditioned_seed is None)
    return mine, theirs, fit_m, sample_m, sample_o, img, jac


# ---------------------------------------- 4. scorer / search / audit / refine
class FakeProviderPair:
    def __init__(self, row, pages: int):
        self.h3 = h3words.ReferenceField(row)
        spec = FakeSpec(row)
        self.o = o_reference.V1ReferenceField(spec)


class ArrayProviderH3:
    def __init__(self, values: np.ndarray, sites: np.ndarray) -> None:
        self.cells_yx = values.shape
        self._page = h3words.ReferencePage(0, values, sites)

    def page(self, page: int):
        return self._page


class ArrayProviderO:
    def __init__(self, values: np.ndarray, sites: np.ndarray) -> None:
        self._page = o_reference.ReferencePage(0, values, sites)

    def page(self, page: int):
        return self._page


RENDER_BITS: np.ndarray = np.zeros((1, 1), np.uint8)
RENDER_ORIGIN: tuple[float, float] = (0.0, 0.0)


def candidate_tuple(c) -> tuple:
    return (c.page, c.origin_yx, c.rot_k, c.search_mismatch,
            c.validation_mismatch, c.search_errors, c.validation_errors,
            c.search_support, c.validation_support, c.soft_z, c.passes,
            c.route)


def make_o_patch(means, mask, bits, evidence, midpoint, core):
    window = PoseWindow(0, 0, (0, 0), means.shape, 0, 0)
    pose = AffinePose((0.0, 0.0), ((1.0, 0.0), (0.0, 1.0)), (0.5, 0.5),
                      1.0, 0.0)
    segment = PoseSegment(window, pose, int(mask.sum()), 0.0, (1.0, 1.0),
                          0.0)
    sample = o_pose_fit.SegmentSample(segment, means, mask, bits,
                                      evidence, float(midpoint))
    return o_pose_fit.AddressPatch(sample, core)


def synth_fragment(row, providers, page: int, oy: int, ox: int,
                   shape: tuple[int, int], rot_k: int, flip: float,
                   seed: int):
    ref = providers.h3.page(page)
    rng = np.random.default_rng(seed)
    frag = np.zeros(shape, np.uint8)
    sl = h3pose.overlap_slices((oy, ox), shape, ref.values.shape)
    page_y, page_x, frag_y, frag_x = sl
    frag[frag_y, frag_x] = ref.values[page_y, page_x]
    noise = rng.random(shape) < flip
    frag = frag ^ noise.astype(np.uint8)
    frag = np.rot90(frag, -rot_k).copy()
    evidence = np.where(frag > 0, np.float32(-0.82), np.float32(0.82))
    evidence = evidence * (0.6 + 0.4 * rng.random(
        frag.shape).astype(np.float32))
    bits = frag
    mask = np.ones(frag.shape, bool)
    return evidence.astype(np.float32), bits, mask


def verify_scorer():
    row = resolve_format_ref("c2-k-r0550@4x4", n_pages=3)
    providers = FakeProviderPair(row, 3)
    shape = (90, 90)
    evidence, bits, mask = synth_fragment(
        row, providers, 1, 33, 71, shape, 0, 0.04, 11)
    memo_m = h3pose.ScoreMemo(providers.h3)
    memo_o = o_pose_audit.ScoreMemo(providers.o)
    probes = []
    for _ in range(200):
        probes.append((int(RNG.integers(0, 3)),
                       int(RNG.integers(-95, 260)),
                       int(RNG.integers(-95, 260)),
                       int(RNG.integers(0, 4)),
                       int(RNG.integers(0, 2))))
    probes.append((1, 33, 71, 0, 0))
    probes.append((1, 33, 71, 0, 1))
    probes.append((1, 33, 71, 0, 2))
    for page, oy, ox, rot_k, parity in probes:
        par = h3pose.WHOLE_WORD_PARITY if parity == 2 else parity
        mine = memo_m.parity_score(evidence, bits, mask, page, (oy, ox),
                                   rot_k, par)
        theirs = memo_o.parity_score(0, evidence, bits, mask, page,
                                     (oy, ox), rot_k, par)
        check_ok = mine == theirs
        if not check_ok:
            check(f"parity_score {page},{oy},{ox},{rot_k},{par}", False,
                  f"{mine} vs {theirs}")
    check("parity_score 203 probes", True)
    budget = AttemptBudget(49, 1e-3, 0.08, "verify")
    mine_c = memo_m.candidate(evidence, bits, mask, 1, (33, 71), 0,
                              budget.min_support, 0.20, 0.24, "chain")
    theirs_c = memo_o.candidate(0, evidence, bits, mask, 1, (33, 71), 0,
                                budget, "chain")
    check("candidate row", candidate_tuple(mine_c)
          == candidate_tuple(theirs_c))
    for best, rival in ((0.03, 0.31), (0.03, 0.19), (0.15, 0.22),
                        (0.13, 0.21), (0.10, 0.21)):
        check(f"rival_gate {best}/{rival}",
              h3pose.rival_gate(best, rival, 0.20, 0.08)
              == o_pose_audit.rival_gate(best, rival))
    # local search parity
    patch_o = make_o_patch(
        np.zeros(shape, np.float32), mask, bits, evidence, 0.0, mask)
    out_o = o_pose_audit.local_search(
        patch_o, 1, 0, (34, 70), budget, memo_o, sample_key=0,
        config=CONFIG)
    out_m = h3place.local_search(
        h3pose.ScoreMemo(providers.h3), evidence, bits, mask, 1, 0,
        (34, 70), budget.min_support, budget.max_hypotheses)
    check("local_search verdict",
          out_o.accepted == out_m.accepted and out_o.reason == out_m.reason
          and out_o.hypotheses == out_m.hypotheses)
    check("local_search best",
          candidate_tuple(out_o.best) == candidate_tuple(out_m.best))
    check("local_search runner order",
          tuple(candidate_tuple(c) for c in out_o.runner_ups)
          == tuple(candidate_tuple(c) for c in out_m.runner_ups))
    return row, providers


def verify_refine_audit(pose_bundle):
    mine, theirs, fit_m, sample_m, sample_o, img, jac = pose_bundle
    # build a reference field whose page 0 matches the rendered bits over a
    # 4x4-tile K row: instead render a REAL page (done in e2e); here compare
    # the two implementations on the SAME synthetic provider.
    row = resolve_format_ref("c2-k-r0550@4x4", n_pages=2)
    providers = FakeProviderPair(row, 2)
    core_m = h3pose.address_core(sample_m.mask)
    core_o = o_place_shared.address_core(sample_o.mask, CONFIG.erode_cells)
    check("address_core", np.array_equal(core_m, core_o))
    page, oy, ox, rot_k = 0, 21, 17, 1
    f_m = h3pose.fragment_reference_sites(sample_m.mask, providers.h3,
                                          page, (oy, ox), rot_k)
    f_o = o_pose_audit.fragment_reference_sites(sample_o.mask, providers.o,
                                                page, (oy, ox), rot_k)
    check("fragment_reference_sites",
          all(np.array_equal(a, b) for a, b in zip(f_m, f_o)))
    ref_o = o_pose_audit.refine_patch_pose(
        theirs, o_pose_fit.make_address_patch(sample_o, core_o),
        providers.o, page, (oy, ox), rot_k, CONFIG,
        resample=o_pose_fit.sample_segment)
    ref_m = h3pose.refine_patch_pose(mine, sample_m, providers.h3, page,
                                     (oy, ox), rot_k)
    check("refine presence", (ref_o is None) == (ref_m is None))
    # matched reference: the render's own bits as page values, so the
    # correspondence is real and the batched 7x9x9 scan actually runs.
    page_values = np.ascontiguousarray(RENDER_BITS)
    site_mask = np.ascontiguousarray(RNG.random(page_values.shape) < 0.3)
    prov_m = ArrayProviderH3(page_values, site_mask)
    prov_o = ArrayProviderO(page_values, site_mask)
    inv = np.linalg.inv(np.asarray(jac))
    origin_cells = inv @ (np.asarray(fit_m.segment.pose.origin_yx)
                          - np.asarray(RENDER_ORIGIN))
    true_off = (int(math.floor(float(origin_cells[0]))),
                int(math.floor(float(origin_cells[1]))))
    ref_o = o_pose_audit.refine_patch_pose(
        theirs, o_pose_fit.make_address_patch(sample_o, core_o),
        prov_o, 0, true_off, 0, CONFIG,
        resample=o_pose_fit.sample_segment)
    ref_m = h3pose.refine_patch_pose(mine, sample_m, prov_m, 0, true_off,
                                     0)
    check("refine matched presence",
          ref_o is not None and ref_m is not None)
    if ref_o is not None:
        check("refine deltas",
              ref_o.delta_angle_deg == ref_m.delta_angle_deg
              and ref_o.delta_phase_yx == ref_m.delta_phase_yx
              and ref_o.heldout_before == ref_m.heldout_before
              and ref_o.heldout_after == ref_m.heldout_after)
        check("refine resample",
              np.array_equal(ref_o.sample.means, ref_m.sample.means)
              and np.array_equal(ref_o.sample.mask, ref_m.sample.mask)
              and (ref_o.sample.segment.pose.origin_yx
                   == ref_m.sample.segment.pose.origin_yx)
              and (ref_o.sample.segment.pose.jacobian_yx
                   == ref_m.sample.segment.pose.jacobian_yx))
    aud_o = o_pose_audit.audit_segment(
        sample_o, core_o, providers.o, page, (oy, ox), rot_k, CONFIG,
        min_support=30)
    aud_m = h3pose.audit_segment(sample_m, core_m, providers.h3, page,
                                 (oy, ox), rot_k, 30)
    check("audit_segment",
          np.array_equal(aud_o[0], aud_m[0]) and aud_o[1] == aud_m[1]
          and aud_o[2] == aud_m[2] and aud_o[3] == aud_m[3])
    # audit with an injected bad stripe over a well-overlapped placement
    page2, oy2, ox2, rot2 = 0, 5, 9, 0
    bits2 = sample_m.bits.copy()
    bits2[:60, :] ^= (RNG.random((60, bits2.shape[1])) < 0.45).astype(
        np.uint8)
    sample_m2 = h3pose.SegmentSample(
        sample_m.segment, sample_m.means, sample_m.mask, bits2,
        sample_m.evidence, sample_m.midpoint)
    sample_o2 = o_pose_fit.SegmentSample(
        sample_o.segment, sample_o.means, sample_o.mask, bits2,
        sample_o.evidence, sample_o.midpoint)
    aud_o2 = o_pose_audit.audit_segment(
        sample_o2, core_o, providers.o, page2, (oy2, ox2), rot2, CONFIG,
        min_support=30)
    aud_m2 = h3pose.audit_segment(sample_m2, core_m, providers.h3, page2,
                                  (oy2, ox2), rot2, 30)
    check("audit_segment stripe case",
          np.array_equal(aud_o2[0], aud_m2[0]) and aud_o2[1] == aud_m2[1]
          and aud_o2[2] == aud_m2[2] and aud_o2[3] == aud_m2[3])


# ------------------------------------------------------- 5. words stage A
def verify_words():
    row = resolve_format_ref("c2-k-r0550@6x4", n_pages=3)
    providers = FakeProviderPair(row, 3)
    spec = FakeSpec(row)
    ref = providers.h3.page(1)
    shape = (200, 200)
    oy, ox = 97, 45
    rng = np.random.default_rng(5)
    frag = ref.values[oy:oy + shape[0], ox:ox + shape[1]].copy()
    flips = (rng.random(shape) < 0.02).astype(np.uint8)
    frag ^= flips
    mask = np.ones(shape, bool)
    mask[:, 190:] = False
    for rot_k in range(4):
        bits_r = np.rot90(frag, -rot_k).copy()
        mask_r = np.rot90(mask, -rot_k).copy()
        for stage in ("all", "centre", "rest"):
            wb = WordAttemptBudget(
                o_words.stage_a_hypotheses(bits_r.shape), 1e-3, "verify")
            out_o = o_words.stage_a(bits_r, mask_r, spec, wb, slots=stage)
            out_m = h3words.stage_a(bits_r, mask_r, row, stage)
            check(f"stage_a hypotheses rot{rot_k} {stage}",
                  out_o.hypotheses == out_m.hypotheses
                  and out_o.reason == out_m.reason)
            rows_o = tuple(
                (c.oriented_origin_yx, c.rot_k, c.counter, c.page,
                 c.tile_yx, c.errors, c.page_origin_yx)
                for c in out_o.candidates)
            rows_m = tuple(
                (c.oriented_origin_yx, c.rot_k, c.counter, c.page,
                 c.tile_yx, c.errors, c.page_origin_yx)
                for c in out_m.candidates)
            check(f"stage_a candidates rot{rot_k} {stage}",
                  rows_o == rows_m, f"n={len(rows_m)}")
    # rival-set law vs holo2 placement._rivals
    out_m = h3words.stage_a(frag, mask, row, "all")
    cands_m = out_m.candidates
    wb = WordAttemptBudget(o_words.stage_a_hypotheses(frag.shape), 1e-3,
                           "verify")
    cands_o = o_words.stage_a(frag, mask, spec, wb, slots="all").candidates
    if cands_m:
        winner_m, winner_o = cands_m[0], cands_o[0]
        rows_m = h3words.word_rival_rows(winner_m, cands_m, (0, 1, 2), 3)
        rows_o = o_placement._rivals(winner_o, cands_o, (0, 1, 2), 3)
        check("word rival rows", rows_m == rows_o, f"n={len(rows_m)}")
    check("words produced candidates", bool(cands_m),
          f"n={len(cands_m)}")


# ----------------------------------------------------------- 6. cold sweep
def verify_cold():
    row = resolve_format_ref("c2-k-r0550@4x4", n_pages=3)
    providers = FakeProviderPair(row, 3)
    shape = (140, 140)
    page, oy, ox, rot_k = 2, 61, 88, 3
    evidence, bits, mask = synth_fragment(
        row, providers, page, oy, ox, shape, rot_k, 0.05, 23)
    mask = mask.copy()
    mask[:, :6] = False
    pages = (0, 1, 2)
    declared = h3cold.hypothesis_count(
        (200, 200), row.cells_yx, len(pages), allow_overhang=True)
    budget = AttemptBudget(declared, 1e-3, 0.08, "verify")
    patch_o = make_o_patch(np.zeros(shape, np.float32), mask, bits,
                           evidence, 0.0, mask)
    out_o = o_cold.correlate_patch(patch_o, providers.o, pages, budget,
                                   o_pose_audit.ScoreMemo(providers.o),
                                   sample_key=0, config=CONFIG)
    out_m = h3cold.correlate_patch(
        evidence, bits, mask, providers.h3, pages, declared,
        budget.min_support, h3pose.ScoreMemo(providers.h3),
        0.20, 0.24, 0.20, 0.08)
    check("cold verdict",
          out_o.accepted == out_m.accepted and out_o.reason == out_m.reason
          and out_o.hypotheses == out_m.hypotheses)
    check("cold best",
          (out_o.best is None) == (out_m.best is None)
          and (out_o.best is None
               or candidate_tuple(out_o.best) == candidate_tuple(
                   out_m.best)))
    check("cold runners",
          tuple(candidate_tuple(c) for c in out_o.runner_ups)
          == tuple(candidate_tuple(c) for c in out_m.runner_ups))
    check("cold recovered address",
          out_m.accepted and out_m.best.page == page
          and out_m.best.rot_k == rot_k
          and out_m.best.origin_yx == (oy, ox))
    # early-out: a fragment too small for the floor pays no page FFT
    tiny_e = evidence[:9, :9].copy()
    tiny_b = bits[:9, :9].copy()
    tiny_m = np.ones((9, 9), bool)
    out_o2 = o_cold.correlate_patch(
        make_o_patch(np.zeros((9, 9), np.float32), tiny_m, tiny_b, tiny_e,
                     0.0, tiny_m),
        providers.o, pages, budget,
        o_pose_audit.ScoreMemo(providers.o), sample_key=0, config=CONFIG)
    out_m2 = h3cold.correlate_patch(
        tiny_e, tiny_b, tiny_m, providers.h3, pages, declared,
        budget.min_support, h3pose.ScoreMemo(providers.h3),
        0.20, 0.24, 0.20, 0.08)
    check("cold early-out",
          out_o2.reason == out_m2.reason == "insufficient_support"
          and out_o2.hypotheses == out_m2.hypotheses)


# ------------------------------------------------------ 7. frame bridge
def verify_bridge():
    pose = AffinePose((311.7, 254.2),
                      ((7.91, -0.052), (0.049, 7.88)), (0.7, 1.1),
                      7.895, 0.36)
    shape = (200, 137)
    for rot_k in range(4):
        for origin in ((-15, 22), (0, 0), (130, -7)):
            theirs = o_place_shared.page_affine_terms(
                pose, shape, rot_k, origin, None)
            mine = h3place.page_affine_terms(
                pose.matrix(), pose.origin_yx, shape, rot_k, origin, 1)
            check(f"page_affine_terms rot{rot_k} {origin}", mine == theirs)
            rk_o, pred_o = o_place_shared.predict_from_page_affine(
                theirs, pose, shape, None)
            rk_m, pred_m = h3place.predict_from_page_affine(
                mine, pose.matrix(), pose.origin_yx, shape, 1)
            check(f"predict rot{rot_k} {origin}",
                  rk_o == rk_m == rot_k and pred_o == pred_m == origin)
    # rung round trip at scale 4: terms composed to native and predicted
    # back through the same scale must recover the address exactly.
    native = h3place.page_affine_terms(
        pose.matrix(), pose.origin_yx, shape, 1, (40, -3), 4)
    rk, pred = h3place.predict_from_page_affine(
        native, pose.matrix(), pose.origin_yx, shape, 4)
    check("rung bridge round-trip", rk == 1 and pred == (40, -3))
    check("window_starts flush shift",
          h3geom.window_starts(451) == (0, 160, 251)
          and h3geom.window_starts(545) == (0, 160, 320, 345)
          and h3geom.window_starts(7) == ()
          and h3geom.window_starts(200) == (0,))
    ring = h3place.ring_neighbour_extents((545, 451), (160, 160, 360, 360))
    check("ring neighbours", ring == (
        (0, 0, 200, 200), (0, 160, 200, 360), (0, 251, 200, 451),
        (160, 0, 360, 200), (160, 251, 360, 451),
        (320, 0, 520, 200), (320, 160, 520, 360), (320, 251, 520, 451)))


# ------------------------------------------------------------- 8. e2e mini
def build_frame(row, image_shape, pitch_native: float, step: int = 32):
    cells = np.ones((image_shape[0] // step + 1,
                     image_shape[1] // step + 1), bool)
    region = h3data.Region(
        capture_id="sim", region_index=0, origin_yx=(0, 0), step_px=step,
        cells=cells, extent_px=image_shape, area_mm2=0.0,
        median_tensor_score=0.0)
    level = h3data.Level(index=0, ppc=Fraction(8), scale=Fraction(1),
                         shape_px=image_shape, label="native")
    return h3place.region_frame(region, level, Fraction(1, 300), 2400.0,
                                236.0)


def page_bits(row, page: int) -> np.ndarray:
    ref = h3words.ReferenceField(row).page(page)
    payload = h3ks.payload_bits(row.seed, h3words.addressing_plane(row),
                                page, row.cells_yx)
    bits = np.where(ref.sites, ref.values, payload).astype(np.uint8)
    return bits


def run_e2e(rot_input: int) -> None:
    row = resolve_format_ref("c2-k-r0700@6x4", n_pages=1)
    bits = page_bits(row, 0)
    angle = np.deg2rad(0.3)
    jac = 8.0 * np.array([[np.cos(angle), -np.sin(angle)],
                          [np.sin(angle), np.cos(angle)]])
    img = render_lattice(bits, jac, (44.5, 38.5), (3260, 2260),
                         noise=4.0, seed=99)
    if rot_input:
        img = np.ascontiguousarray(np.rot90(img, rot_input))
    frame = build_frame(row, img.shape, 8.0)
    windows = h3place.window_plan(frame, 0)
    check(f"e2e rot{rot_input} windows laid out", len(windows) > 0,
          f"n={len(windows)}")
    window = windows[0]
    reference = h3words.ReferenceField(row)
    job = h3place.WindowPass(
        window=window, frame=frame, planes=(img,), row=row,
        reference=reference, page_domain=(0,), stage="centre", wide=False,
        cold_flavour=None, cold_pages=(), seeds=(), tried_count=0,
        lattice_seed=None, patch_ordinal=0)
    result = h3place.run_window_pass(job)
    check(f"e2e rot{rot_input} accepted", result.outcome == "accepted",
          result.outcome)
    placement = result.placement
    check(f"e2e rot{rot_input} page/route",
          placement.page == 0 and placement.route == "word")
    # re-read the page through the committed native affine: sites of the
    # audited reach must reproduce the reference bits.
    ref = reference.page(0)
    matrix = h3geom.affine_matrix(placement.native_affine)
    linear, offset = matrix[:, :2], matrix[:, 2]
    sy, sx = np.nonzero(ref.sites)
    oy0, ox0 = placement.page_origin_yx
    in_window = ((sy >= oy0) & (sy < oy0 + 200)
                 & (sx >= ox0) & (sx < ox0 + 200))
    sy, sx = sy[in_window], sx[in_window]
    pts = np.stack([sy + 0.5, sx + 0.5], axis=1) @ linear.T + offset
    inside = ((pts[:, 0] > 2) & (pts[:, 0] < img.shape[0] - 3)
              & (pts[:, 1] > 2) & (pts[:, 1] < img.shape[1] - 3))
    reads = ndimage.map_coordinates(
        np.asarray(img, np.float32), pts[inside].T, order=1)
    midpoint = 0.5 * (235.0 + 80.0)
    read_bits = (reads < midpoint).astype(np.uint8)
    expected = ref.values[sy[inside], sx[inside]]
    mismatch = float(np.mean(read_bits != expected))
    check(f"e2e rot{rot_input} reprojection mismatch < 0.02",
          mismatch < 0.02, f"{mismatch:.4f} over {int(inside.sum())}")
    # chain route: a second window seeded from the committed pose
    second = None
    for cand in windows:
        if cand.extent_cells != window.extent_cells:
            second = cand
            break
    if second is not None:
        anchor = h3place.AnchorPose(
            pose_id="pose/0", extent_cells=window.extent_cells,
            page=placement.page, native_affine=placement.native_affine)
        seeds = h3place.consult_seeds(
            second.extent_cells, (anchor,), (0,), False)
        job2 = h3place.WindowPass(
            window=second, frame=frame, planes=(img,), row=row,
            reference=reference, page_domain=(0,), stage=None, wide=False,
            cold_flavour=None, cold_pages=(), seeds=seeds, tried_count=0,
            lattice_seed=(tuple(np.asarray(result.lattice_seed.rows)
                                .reshape(4))
                          if result.lattice_seed is not None else None),
            patch_ordinal=1)
        result2 = h3place.run_window_pass(job2)
        check(f"e2e rot{rot_input} chain window",
              result2.outcome == "accepted"
              and result2.route == "chain", result2.outcome)


def main() -> None:
    verify_reference()
    verify_admission()
    bundle = verify_pose_kernel()
    verify_scorer()
    verify_refine_audit(bundle)
    verify_words()
    verify_cold()
    verify_bridge()
    run_e2e(0)
    run_e2e(1)
    print(f"verify_placement: ALL {len(CHECKS)} checks green")


if __name__ == "__main__":
    main()
