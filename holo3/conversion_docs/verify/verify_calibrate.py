# Wave-2 P4 verify: holo3/plugins/calibrate.py vs the src/holo oracles.
# Run: cd <checkout> && \
#   PYTHONPATH=.:src:holo2/src env314t/bin/python _distill/verify/verify_calibrate.py
from __future__ import annotations

import hashlib
from dataclasses import replace
from fractions import Fraction
from types import SimpleNamespace

import numpy as np

from holo3.data import Placement, WindowEvidence
from holo3.format.identity import SiteGeometry, resolve_format_ref
from holo3.format import pilots as h3_pilots
from holo3.lib import pava as h3_pava
from holo3.plugins import calibrate as cal

from holo.format.resolve import resolve_format_ref as v1_resolve
from holo.receive import detect as v1_detect
from holo.receive import _payload_context as v1_ctx
from holo.receive import _payload_sampling as v1_sampling
from holo.receive import payload as v1_payload
from holo.receive import payload_model as v1_model

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if ok:
        print(f"  ok   {name}")
    else:
        FAILURES.append(f"{name} {detail}")
        print(f"  FAIL {name} {detail}")


def same(name: str, a, b) -> None:
    a = np.asarray(a)
    b = np.asarray(b)
    ok = a.shape == b.shape and a.dtype == b.dtype and np.array_equal(a, b)
    check(name, ok, f"(shapes {a.shape}/{b.shape} dtypes {a.dtype}/{b.dtype})")


# ---------------------------------------------------------------- fixtures
RNG = np.random.default_rng(20260828)

H3_ROW = resolve_format_ref("L:c2-r0700@3392x2368")
V1_SPEC = v1_resolve("L:c2-r0700@3392x2368")
WORD = h3_pilots.word_site_cells_yx(H3_ROW.family_seed)
FILLER = h3_pilots.filler_site_cells_yx(
    H3_ROW.family_seed, H3_ROW.n_sites - h3_pilots.N_WORD_SITES, WORD)
EMPTY = np.zeros(0, np.int64)
GEOMETRY = SiteGeometry(WORD, FILLER, EMPTY, EMPTY, EMPTY, EMPTY,
                        np.zeros((0, 1, 1), np.uint8))
LOOKUP = cal.build_site_lookup(GEOMETRY)


def section(title: str) -> None:
    print(f"\n== {title}")


# ------------------------------------------------------- 1. format truth
section("format reference labels / payload mask")
check("seed parity", H3_ROW.seed == V1_SPEC.seed,
      f"{H3_ROW.seed!r} vs {V1_SPEC.seed!r}")
check("family seed parity", H3_ROW.family_seed == V1_SPEC.family_seed)
check("tiles parity", H3_ROW.tiles_yx == V1_SPEC.layout.tiles_yx)
check("cells parity", H3_ROW.cells_yx == V1_SPEC.layout.cells_yx)

v1_kind, v1_index = v1_sampling._site_lookup(
    V1_SPEC.family_seed, V1_SPEC.n_filler)
same("site lookup kind", LOOKUP.kind, v1_kind)
same("site lookup index", LOOKUP.index, v1_index)

cells_all = np.stack(np.meshgrid(np.arange(120, 260, dtype=np.int64),
                                 np.arange(64, 200, dtype=np.int64),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
for page in (0, 1):
    same(f"format_reference_values page={page}",
         cal.format_reference_values(H3_ROW, LOOKUP, page, cells_all),
         v1_sampling.format_reference_values(V1_SPEC, page, cells_all))
same("payload_cell_mask",
     cal.payload_cell_mask(LOOKUP, cells_all),
     v1_payload.payload_cell_mask(V1_SPEC, cells_all))
check("reference labels are non-trivial",
      int(np.count_nonzero(
          cal.format_reference_values(H3_ROW, LOOKUP, 0, cells_all) >= 0)) > 200)

# a K coding with fillers exercises the DOMAIN_FILLER_VALUES branch
try:
    h3_filler_row = resolve_format_ref("c2-k-r0700-p120@53x37")
    v1_filler_spec = v1_resolve("c2-k-r0700-p120@53x37")
except Exception as exc:  # noqa: BLE001 - reported, not swallowed
    check("filler-row resolution", False, repr(exc))
else:
    check("filler row seeds agree", h3_filler_row.seed == v1_filler_spec.seed)
    f_word = h3_pilots.word_site_cells_yx(h3_filler_row.family_seed)
    f_extra = h3_pilots.filler_site_cells_yx(
        h3_filler_row.family_seed,
        h3_filler_row.n_sites - h3_pilots.N_WORD_SITES, f_word)
    f_geometry = SiteGeometry(f_word, f_extra, EMPTY, EMPTY, EMPTY, EMPTY,
                              np.zeros((0, 1, 1), np.uint8))
    f_lookup = cal.build_site_lookup(f_geometry)
    same("filler lookup kind", f_lookup.kind,
         v1_sampling._site_lookup(v1_filler_spec.family_seed,
                                  v1_filler_spec.n_filler)[0])
    f_values = cal.format_reference_values(h3_filler_row, f_lookup, 1,
                                           cells_all)
    same("format_reference_values with fillers", f_values,
         v1_sampling.format_reference_values(v1_filler_spec, 1, cells_all))
    check("filler branch exercised",
          int(np.count_nonzero(f_lookup.kind == 1)) == 20)

# --------------------------------------------------------- 2. region pitch
section("region pitch")
for values in ([8.0], [8.0, 7.5, 9.25], [6.0, 6.5, 7.0, 7.25]):
    patches = tuple(
        SimpleNamespace(segment=SimpleNamespace(
            segment=SimpleNamespace(pose=SimpleNamespace(pitch_px=value))))
        for value in values)
    check(f"region pitch {values}",
          cal.region_pitch_px(values) == v1_sampling._region_pitch(patches))


# ------------------------------------------------------ 3. crop / sampling
section("crop, filter and cell sampling")


class _Pose:
    def __init__(self, matrix: np.ndarray, origin: np.ndarray,
                 pitch_px: float) -> None:
        self.matrix = matrix
        self.origin = origin
        self.pitch_px = pitch_px

    def points(self, cells_yx: np.ndarray) -> np.ndarray:
        return np.asarray(cells_yx, np.float64) @ self.matrix.T + self.origin


def make_raster(shape_yx: tuple[int, int]) -> np.ndarray:
    return RNG.integers(0, 256, size=shape_yx, dtype=np.uint8)


def sampling_case(pitch_px: float, angle_deg: float, cells_yx: tuple[int, int],
                  origin: tuple[float, float], shape_yx: tuple[int, int],
                  tag: str) -> None:
    theta = np.deg2rad(angle_deg)
    matrix = pitch_px * np.asarray(((np.cos(theta), -np.sin(theta)),
                                   (np.sin(theta), np.cos(theta))), np.float64)
    pose = _Pose(matrix, np.asarray(origin, np.float64), pitch_px)
    ny, nx = cells_yx
    local = np.stack(np.meshgrid(np.arange(ny, dtype=np.int64),
                                 np.arange(nx, dtype=np.int64),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    points = pose.points(local.astype(np.float64))
    image = make_raster(shape_yx)
    raster = SimpleNamespace(
        shape=shape_yx,
        crop_luma=lambda y0, y1, x0, x1: image[y0:y1, x0:x1])
    patch = SimpleNamespace(segment=SimpleNamespace(
        segment=SimpleNamespace(window=SimpleNamespace(shape_yx_cells=(ny, nx)),
                                pose=pose)))
    v1_crop = v1_sampling._window_crop(raster, patch, pitch_px)
    rows = v1_sampling._WindowRows(0, local.astype(np.int32),
                                   local.astype(np.int32), points)
    v1_means = v1_sampling._sample_rows(v1_crop, rows, shape_yx)
    h3_crop = cal.window_crop([image], points, shape_yx, pitch_px)
    h3_means = cal.sample_points(h3_crop, points)
    same(f"sampled means [{tag}]", h3_means, v1_means)
    check(f"aperture integers [{tag}]",
          v1_sampling._filter_signature((patch,))
          == (int(np.ceil(cal.APERTURE_CELLS * pitch_px)) + 2,
              max(1, int(round(cal.APERTURE_CELLS * pitch_px)))))
    same(f"scores [{tag}]", cal.window_scores(h3_means),
         v1_sampling._scores(v1_means))
    check(f"scores stay float32 [{tag}]",
          cal.window_scores(h3_means).dtype == np.float32)


sampling_case(8.0, 0.0, (40, 50), (60.0, 70.0), (700, 800), "p8 straight")
sampling_case(7.9375, 0.35, (48, 64), (33.25, 41.5), (900, 1000), "p7.94 tilted")
sampling_case(2.0, -0.2, (60, 90), (12.5, 9.25), (300, 400), "p2 coarse")
sampling_case(16.25, 1.1, (24, 30), (80.5, 55.0), (900, 900), "p16 fine")

section("K-on-RGB luma law")
rgb = RNG.integers(0, 256, size=(40, 50, 3), dtype=np.uint8)
grey = RNG.integers(0, 256, size=(40, 50), dtype=np.uint8)
same("rgb crop luma == v1 ColorScaleRaster.crop_luma",
     cal.crop_luma([rgb[..., 0], rgb[..., 1], rgb[..., 2]], 3, 30, 5, 40),
     rgb[3:30, 5:40].mean(axis=2, dtype=np.float32))
same("grey crop luma == v1 GreyScaleRaster.crop_luma",
     cal.crop_luma([grey], 3, 30, 5, 40),
     grey[3:30, 5:40].astype(np.float32))

section("_scores edge cases")
for tag, means in (
    ("random", RNG.normal(128.0, 40.0, size=4096).astype(np.float32)),
    ("constant", np.full(512, 200.0, np.float32)),
    ("bimodal", np.where(RNG.random(4096) < 0.4, 20.0, 230.0).astype(np.float32)),
    ("tiny", np.asarray([1.0, 1.0, 1.0000001], np.float32)),
):
    same(f"_scores [{tag}]", cal.window_scores(means),
         v1_sampling._scores(means))


# --------------------------------------------------- 4. window calibration
section("per-window PAVA calibration")


def v1_window_fit(scores: np.ndarray, labels: np.ndarray,
                  page_cells: np.ndarray, page: int):
    parity = ((131 * page_cells[:, 0] + 17 * page_cells[:, 1]) & 1).astype(bool)
    known = labels >= 0
    search_mask = known & ~parity
    heldout_mask = known & parity
    ids = v1_sampling._site_ids(V1_SPEC, page, page_cells)
    search = v1_detect.CalibrationObservations(
        "w", scores[search_mask], labels[search_mask], ids[search_mask])
    heldout = v1_detect.CalibrationObservations(
        "w", scores[heldout_mask], labels[heldout_mask], ids[heldout_mask])
    fit = v1_detect.fit_calibration(search, heldout)
    if not fit.accepted:
        return fit, None, None, None
    llr = np.asarray(fit.calibration.llr(scores), np.float32)
    probability = fit.calibration.probability(scores[heldout_mask])
    heldout_labels = labels[heldout_mask].astype(np.float64)
    loss = float(-np.mean(
        heldout_labels * np.log(probability)
        + (1.0 - heldout_labels) * np.log(1.0 - probability)))
    return fit, llr, loss, fit.calibration


def calibration_case(n_cells: int, ink_bias: float, page: int, tag: str,
                     starve: str = "") -> None:
    cells = np.stack(np.meshgrid(
        np.arange(200, 200 + int(np.sqrt(n_cells)), dtype=np.int64),
        np.arange(300, 300 + int(np.sqrt(n_cells)), dtype=np.int64),
        indexing="ij"), axis=-1).reshape(-1, 2)
    labels = cal.format_reference_values(H3_ROW, LOOKUP, page, cells)
    if starve == "class":
        known = labels >= 0
        labels = np.where(known, np.int8(1), np.int8(-1)).astype(np.int8)
    if starve == "none":
        labels = np.full(labels.size, -1, np.int8)
    truth = labels.astype(np.float64)
    scores = (RNG.normal(0.0, 1.0, size=cells.shape[0])
              + ink_bias * np.where(truth > 0, 1.0, -1.0)).astype(np.float32)
    v1_fit, v1_llr, v1_loss, _cal = v1_window_fit(scores, labels, cells, page)
    h3_fit = cal.fit_window_calibration(scores, labels, cells)
    check(f"accepted [{tag}]", h3_fit.accepted == v1_fit.accepted,
          f"{h3_fit.accepted} vs {v1_fit.accepted}")
    reason = "accepted" if h3_fit.accepted else h3_fit.reason
    check(f"reason [{tag}]", reason == v1_fit.reason,
          f"{reason} vs {v1_fit.reason}")
    if not v1_fit.accepted:
        return
    same(f"knots [{tag}]", h3_fit.knots, v1_fit.calibration.knots)
    same(f"probs [{tag}]", h3_fit.probs, v1_fit.calibration.probabilities)
    check(f"n_search [{tag}]", h3_fit.n_search == v1_fit.n_search)
    same(f"marginal llr [{tag}]", h3_fit.marginal_llr, v1_llr)
    check(f"heldout logloss [{tag}]",
          h3_fit.heldout_logloss == v1_loss,
          f"{h3_fit.heldout_logloss!r} vs {v1_loss!r}")
    bound = v1_detect.clamp_for(h3_fit.n_search)
    check(f"PAVA bound holds [{tag}]",
          float(np.max(np.abs(h3_fit.marginal_llr))) <= bound + 1e-6)


calibration_case(65536, 1.4, 0, "256x256 strong")
calibration_case(16384, 0.35, 1, "128x128 weak")
calibration_case(4096, 3.0, 0, "64x64 clean")
calibration_case(4096, 1.0, 0, "one-class", starve="class")
calibration_case(4096, 1.0, 0, "no labels", starve="none")

section("small-window starvation gates")
small = np.stack(np.meshgrid(np.arange(64, 70, dtype=np.int64),
                             np.arange(64, 70, dtype=np.int64),
                             indexing="ij"), axis=-1).reshape(-1, 2)
small_labels = cal.format_reference_values(H3_ROW, LOOKUP, 0, small)
small_scores = RNG.normal(size=small.shape[0]).astype(np.float32)
v1_small = v1_window_fit(small_scores, small_labels, small, 0)[0]
h3_small = cal.fit_window_calibration(small_scores, small_labels, small)
check("tiny window refuses identically",
      (not h3_small.accepted and h3_small.reason == v1_small.reason),
      f"{h3_small.reason} vs {v1_small.reason}")


# -------------------------------------------------------- 5. ctx primitives
section("context neighbour counts / bins / apply")
for tag, keep in (("dense", 1.0), ("holes", 0.85), ("sparse", 0.5)):
    grid = np.stack(np.meshgrid(np.arange(30, 70, dtype=np.int64),
                                np.arange(50, 95, dtype=np.int64),
                                indexing="ij"), axis=-1).reshape(-1, 2)
    keep_mask = RNG.random(grid.shape[0]) < keep
    cells = grid[keep_mask]
    ink = RNG.random(cells.shape[0]) < 0.45
    h3_counts, h3_valid = cal.context_neighbour_counts(cells, ink)
    v1_counts, v1_valid = v1_detect.context_neighbour_counts(cells, ink)
    same(f"neighbour counts [{tag}]", h3_counts, v1_counts)
    same(f"neighbour valid [{tag}]", h3_valid, v1_valid)
    bins = np.where(h3_valid, h3_counts, -1).astype(np.int8)
    same(f"context bins [{tag}]", bins,
         v1_detect.context_bins(v1_counts, valid=v1_valid))
    llr = RNG.normal(0.0, 6.0, size=cells.shape[0])
    offsets = np.sort(RNG.uniform(-4.0, 4.0, size=9))[::-1].copy()
    same(f"apply_context_offsets [{tag}]",
         cal.apply_context_offsets(llr, bins, offsets),
         v1_detect.apply_context_offsets(llr, bins, offsets))

def _capture(fn):
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        return exc
    return None


dup_cells = np.asarray([[1, 1], [1, 1], [2, 2]], np.int64)
dup_exc = _capture(lambda: cal.context_neighbour_counts(
    dup_cells, np.zeros(3, bool)))
v1_dup_exc = _capture(lambda: v1_detect.context_neighbour_counts(
    dup_cells, np.zeros(3, bool)))
check("duplicate page cell raises (C-7)",
      isinstance(dup_exc, ValueError) and isinstance(v1_dup_exc, ValueError),
      f"{dup_exc!r} / {v1_dup_exc!r}")


# ------------------------------------------------------- 6. ctx region fit
section("region context fit: weights, support, offsets, gate")


def ctx_population(n_sites: int, duplicate_fraction: float, signal: float,
                   ink_rate: float, ctx_slope: float = -0.35):
    ids = np.arange(n_sites, dtype=np.int64)
    n_dup = int(n_sites * duplicate_fraction)
    ids = np.concatenate((ids, ids[:n_dup]))
    labels = (RNG.random(n_sites) < ink_rate)
    labels = np.concatenate((labels, labels[:n_dup]))
    counts = RNG.integers(0, 9, size=ids.size).astype(np.int8)
    llr = (signal * np.where(labels, 1.0, -1.0)
           + RNG.normal(0.0, 1.5, size=ids.size)
           + ctx_slope * counts.astype(np.float64))
    order = RNG.permutation(ids.size)
    return llr[order], counts[order], labels[order], ids[order]


ADOPTIONS: list[bool] = []


def ctx_case(tag: str, search_args, validation_args) -> None:
    search = ctx_population(*search_args)
    validation = ctx_population(*validation_args)
    validation = (validation[0], validation[1], validation[2],
                  validation[3] + 10 ** 6)
    h3 = cal.context_decision(search, validation)
    h3_offsets, h3_adopted, h3_reason, h3_base, h3_cand = h3
    ADOPTIONS.append(h3_adopted)
    s_obs = v1_detect.ContextObservations(
        "r", search[0], search[1], search[2].astype(np.uint8), search[3])
    v_obs = v1_detect.ContextObservations(
        "r", validation[0], validation[1], validation[2].astype(np.uint8),
        validation[3])
    same(f"site weights [{tag}]", cal.site_weights(search[3]), s_obs.weights)
    check(f"unique class support [{tag}]",
          cal.unique_class_support(search[2], search[3])
          == s_obs.unique_class_support)
    fit = v1_detect.fit_context(s_obs, v_obs)
    if fit.eligible:
        base = v1_ctx._binary_logloss(
            v_obs.baseline_llr, v_obs.labels, v_obs.weights)
        cand = v1_ctx._binary_logloss(
            v_obs.baseline_llr + fit.offsets[v_obs.neighbour_count],
            v_obs.labels, v_obs.weights)
        adopted = cand < base
        reason = "adopted" if adopted else "validation_gate_failed"
    else:
        base = cand = None
        adopted = False
        reason = fit.reason
    same(f"ctx offsets [{tag}]", h3_offsets, fit.offsets)
    check(f"ctx adopted [{tag}]", h3_adopted == adopted,
          f"{h3_adopted} vs {adopted}")
    check(f"ctx reason [{tag}]", h3_reason == reason,
          f"{h3_reason} vs {reason}")
    check(f"ctx baseline loss [{tag}]", h3_base == base,
          f"{h3_base!r} vs {base!r}")
    check(f"ctx candidate loss [{tag}]", h3_cand == cand,
          f"{h3_cand!r} vs {cand!r}")
    if fit.eligible:
        check(f"offsets non-increasing [{tag}]",
              bool(np.all(np.diff(h3_offsets) <= 1e-12)))


ctx_case("wide", (900, 0.25, 1.1, 0.5), (500, 0.2, 1.1, 0.5))
ctx_case("noisy", (400, 0.4, 0.15, 0.45), (260, 0.35, 0.15, 0.45))
ctx_case("balanced-strong", (1200, 0.1, 2.4, 0.5), (700, 0.1, 2.4, 0.5))
ctx_case("gate should fail", (600, 0.0, 1.0, 0.5, -0.5),
         (600, 0.0, 1.0, 0.5, 0.9))
check("at least one synthetic ctx fit adopts", any(ADOPTIONS), repr(ADOPTIONS))
check("at least one synthetic ctx fit refuses adoption",
      not all(ADOPTIONS), repr(ADOPTIONS))

section("ctx floor cascade")
for tag, s_args, v_args, want in (
    ("search total", (40, 0.0, 1.0, 0.5), (300, 0.0, 1.0, 0.5),
     "insufficient_search_support"),
    ("search class", (300, 0.0, 1.0, 0.02), (300, 0.0, 1.0, 0.5),
     "search_class_starved"),
    ("validation total", (300, 0.0, 1.0, 0.5), (20, 0.0, 1.0, 0.5),
     "insufficient_validation_support"),
    ("validation class", (300, 0.0, 1.0, 0.5), (300, 0.0, 1.0, 0.01),
     "validation_class_starved"),
):
    search = ctx_population(*s_args)
    validation = ctx_population(*v_args)
    validation = (validation[0], validation[1], validation[2],
                  validation[3] + 10 ** 6)
    offsets, adopted, reason, base, cand = cal.context_decision(
        search, validation)
    check(f"floor reason [{tag}]", reason == want, f"{reason} vs {want}")
    check(f"floor refuses [{tag}]",
          (not adopted) and base is None and cand is None
          and not np.any(offsets))

empty = (np.zeros(0, np.float64), np.zeros(0, np.int8), np.zeros(0, bool),
         np.zeros(0, np.int64))
for tag, s_side, v_side, want in (
    ("empty search", empty, ctx_population(300, 0.0, 1.0, 0.5),
     "insufficient_search_support"),
    ("empty validation", ctx_population(300, 0.0, 1.0, 0.5), empty,
     "insufficient_validation_support"),
):
    reason = cal.context_decision(s_side, v_side)[2]
    check(f"empty side reason [{tag}]", reason == want, f"{reason} vs {want}")


# --------------------------------------------- 7. physical cell identities
section("physical cell ids across a region")
row_cells = []
for start_y, start_x, ny, nx, page in ((10, 20, 12, 15, 0), (18, 26, 14, 11, 0),
                                       (40, 60, 9, 9, 1)):
    cells = np.stack(np.meshgrid(
        np.arange(start_y, start_y + ny, dtype=np.int64),
        np.arange(start_x, start_x + nx, dtype=np.int64),
        indexing="ij"), axis=-1).reshape(-1, 2)
    row_cells.append((page, cells.astype(np.int32)))
fake_rows = tuple(SimpleNamespace(page=page, page_cells_yx=cells)
                  for page, cells in row_cells)
h3_ids = cal.physical_cell_ids(fake_rows)
v1_ids = v1_ctx._physical_cell_ids(fake_rows)
check("physical id row count", len(h3_ids) == len(v1_ids))
for index, (a, b) in enumerate(zip(h3_ids, v1_ids)):
    same(f"physical cell ids row {index}", a, b)


# ------------------------------------------------- 8. end-to-end K window
section("end-to-end synthetic K window")
PITCH_PX = 8.0
ORIGIN = (37.0, 23.0)
CELL_Y0, CELL_X0, NY, NX = 128, 192, 132, 148
page_cells = np.stack(np.meshgrid(
    np.arange(CELL_Y0, CELL_Y0 + NY, dtype=np.int64),
    np.arange(CELL_X0, CELL_X0 + NX, dtype=np.int64),
    indexing="ij"), axis=-1).reshape(-1, 2)
reference = cal.format_reference_values(H3_ROW, LOOKUP, 0, page_cells)
truth_bits = RNG.integers(0, 2, size=page_cells.shape[0]).astype(np.int8)
truth_bits = np.where(reference >= 0, reference, truth_bits).astype(np.int8)

grid = np.zeros((NY, NX), np.uint8)
grid[page_cells[:, 0] - CELL_Y0, page_cells[:, 1] - CELL_X0] = truth_bits
sheet = np.kron(grid, np.ones((int(PITCH_PX), int(PITCH_PX)), np.uint8))
image = np.full((int(ORIGIN[0]) + sheet.shape[0] + 60,
                 int(ORIGIN[1]) + sheet.shape[1] + 60), 235, np.uint8)
image[int(ORIGIN[0]):int(ORIGIN[0]) + sheet.shape[0],
      int(ORIGIN[1]):int(ORIGIN[1]) + sheet.shape[1]] = np.where(
          sheet > 0, 45, 235)
image = np.clip(image.astype(np.float64)
                + RNG.normal(0.0, 6.0, size=image.shape), 0, 255).astype(np.uint8)

# Cell-EDGE convention (contract 07-2): the placement affine maps cell index
# to the cell's top-left corner; samplers read at cells + 0.5.
affine = (PITCH_PX, 0.0,
          ORIGIN[0] - 0.5 - CELL_Y0 * PITCH_PX,
          0.0, PITCH_PX,
          ORIGIN[1] - 0.5 - CELL_X0 * PITCH_PX)
placement = Placement(
    window_id=("cap", 0, 0, (0, 0, NY, NX)), capture_id="cap", level_index=0,
    region_index=0, patch_ordinal=0, page=0, rot_k=0,
    page_origin_yx=(CELL_Y0, CELL_X0), native_affine=affine, pitch_px=PITCH_PX,
    route="payload",
    local_cells_yx=(page_cells - np.asarray((CELL_Y0, CELL_X0), np.int64)))
evidence = cal.calibrate_window(
    [image], placement, (NY, NX), H3_ROW, LOOKUP, PITCH_PX, Fraction(1))
check("e2e accepted", evidence.accepted, evidence.refusal_reason)
same("e2e page cells", evidence.page_cells_yx, page_cells.astype(np.int32))
agreement = float(np.mean((evidence.printed_llr > 0) == (truth_bits > 0)))
check("e2e printed llr signs match truth > 99%", agreement > 0.99,
      f"{agreement:.5f}")
bound = h3_pava.clamp_for(evidence.n_search)
check("e2e PAVA bound",
      float(np.max(np.abs(evidence.marginal_llr))) <= bound + 1e-6,
      f"{float(np.max(np.abs(evidence.marginal_llr)))} vs {bound}")
check("e2e heldout logloss small", evidence.heldout_logloss < 0.05,
      f"{evidence.heldout_logloss}")

resampled = cal.resample_window(
    [image], placement, evidence, H3_ROW, LOOKUP, PITCH_PX, Fraction(1))
same("resample reproduces scores", resampled.scores, evidence.scores)
same("resample reproduces llr", resampled.printed_llr, evidence.printed_llr)

shifted = replace(placement, native_affine=(
    affine[0], affine[1], affine[2] + 1.5, affine[3], affine[4],
    affine[5] - 1.0))
moved = cal.resample_window(
    [image], shifted, evidence, H3_ROW, LOOKUP, PITCH_PX, Fraction(1))
check("resample at a revised pose changes evidence",
      not np.array_equal(moved.scores, evidence.scores))
check("resample keeps the window identity",
      moved.window_id == evidence.window_id)

off_page = replace(placement, native_affine=(
    affine[0], affine[1], affine[2] - 5000.0, affine[3], affine[4], affine[5]))
refused = cal.calibrate_window(
    [image], off_page, (NY, NX), H3_ROW, LOOKUP, PITCH_PX, Fraction(1))
check("out-of-raster window refuses",
      (not refused.accepted) and refused.refusal_reason == "outside_raster",
      refused.refusal_reason)


# ------------------------------------------- 9. region ctx flow vs v1 flow
section("apply_region_context flow parity")
FLOW_ADOPTIONS: list[bool] = []


def to_v1_window(evi: WindowEvidence, source, patch_id: int):
    n = evi.page_cells_yx.shape[0]
    return v1_model.WindowEvidence(
        source=source, placement_id=f"p{patch_id}", patch_id=patch_id,
        region_id="region-0", page=evi.page, redundant=False, segment_id=0,
        segment_local_cells_yx=evi.page_cells_yx.astype(np.int32),
        page_cells_yx=evi.page_cells_yx.astype(np.int32),
        scan_points_yx=np.zeros((n, 2), np.float64),
        raw_means=np.zeros(n, np.float32), scores=evi.scores,
        reference_values=evi.reference_values,
        calibration_score_nodes=evi.knots,
        calibration_probability_nodes=evi.probs,
        baseline_printed_llr=evi.marginal_llr, printed_llr=evi.printed_llr,
        accepted=evi.accepted, refusal_reason=evi.refusal_reason,
        n_search_0=0, n_search_1=evi.n_search, n_heldout=0,
        heldout_logloss=evi.heldout_logloss)


def region_window(patch_ordinal: int, cell_y0: int, cell_x0: int, ny: int,
                  nx: int, ink_bias: float, noise: float) -> WindowEvidence:
    cells = np.stack(np.meshgrid(
        np.arange(cell_y0, cell_y0 + ny, dtype=np.int64),
        np.arange(cell_x0, cell_x0 + nx, dtype=np.int64),
        indexing="ij"), axis=-1).reshape(-1, 2)
    labels = cal.format_reference_values(H3_ROW, LOOKUP, 0, cells)
    bits = RNG.integers(0, 2, size=cells.shape[0]).astype(np.int8)
    bits = np.where(labels >= 0, labels, bits)
    neighbour = np.zeros(cells.shape[0], np.float64)
    dense = np.zeros((ny, nx), np.int8)
    dense[cells[:, 0] - cell_y0, cells[:, 1] - cell_x0] = bits
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == 0 and dx == 0:
                continue
            neighbour += np.roll(np.roll(dense, dy, axis=0), dx,
                                 axis=1).reshape(-1).astype(np.float64)
    scores = (ink_bias * np.where(bits > 0, 1.0, -1.0)
              + 0.22 * neighbour
              + RNG.normal(0.0, noise, size=cells.shape[0])).astype(np.float32)
    fit = cal.fit_window_calibration(scores, labels, cells)
    place = Placement(
        window_id=("cap", 0, 0, (cell_y0, cell_x0, cell_y0 + ny, cell_x0 + nx)),
        capture_id="cap", level_index=0, region_index=0,
        patch_ordinal=patch_ordinal, page=0, rot_k=0,
        page_origin_yx=(cell_y0, cell_x0), native_affine=affine,
        pitch_px=PITCH_PX, route="payload",
        local_cells_yx=np.zeros((0, 2), np.int64))
    return cal._evidence(place, cells, scores, labels, fit)


for tag, rows_spec in (
    ("two overlapping windows",
     ((0, 300, 400, 70, 80, 1.2, 1.0), (1, 340, 430, 70, 80, 1.2, 1.0))),
    ("three windows + weak signal",
     ((0, 500, 600, 60, 64, 0.35, 1.4), (1, 540, 630, 60, 64, 0.35, 1.4),
      (2, 560, 600, 48, 52, 0.35, 1.4))),
):
    rows = tuple(region_window(*spec) for spec in rows_spec)
    source = v1_model.EvidenceSource(hashlib.sha256(b"cap").hexdigest(),
                                     "native")
    v1_rows = tuple(to_v1_window(row, source, row.patch_ordinal)
                    for row in rows)
    v1_out, v1_decisions = v1_ctx.apply_region_context(v1_rows)
    h3_out, h3_ctx = cal.apply_region_context(rows)
    check(f"ctx adopted [{tag}]", h3_ctx.adopted == v1_decisions[0].adopted,
          f"{h3_ctx.adopted} vs {v1_decisions[0].adopted}")
    check(f"ctx reason [{tag}]", h3_ctx.reason == v1_decisions[0].reason,
          f"{h3_ctx.reason} vs {v1_decisions[0].reason}")
    same(f"ctx offsets [{tag}]", h3_ctx.offsets, v1_decisions[0].offsets)
    for index, (a, b) in enumerate(zip(h3_out, v1_out)):
        same(f"printed llr window {index} [{tag}]", a.printed_llr, b.printed_llr)
        check(f"heldout logloss window {index} [{tag}]",
              a.heldout_logloss == b.heldout_logloss,
              f"{a.heldout_logloss!r} vs {b.heldout_logloss!r}")
        check(f"ctx clamp window {index} [{tag}]",
              float(np.max(np.abs(a.printed_llr))) <= 12.0 + 1e-6)
    check(f"ctx flagged on rows [{tag}]",
          all(row.ctx_adopted == h3_ctx.adopted for row in h3_out))
    FLOW_ADOPTIONS.append(h3_ctx.adopted)

check("a region-flow case adopts the ctx arm (apply path exercised)",
      any(FLOW_ADOPTIONS), repr(FLOW_ADOPTIONS))

section("label rows join the fit")
rows = tuple(region_window(*spec) for spec in
             ((0, 700, 800, 56, 60, 0.8, 1.2), (1, 730, 840, 56, 60, 0.8, 1.2)))
labels_only = (region_window(2, 760, 800, 40, 44, 0.8, 1.2),)
source = v1_model.EvidenceSource(hashlib.sha256(b"cap2").hexdigest(), "native")
v1_out, v1_decisions = v1_ctx.apply_region_context(
    tuple(to_v1_window(row, source, row.patch_ordinal) for row in rows),
    tuple(to_v1_window(row, source, row.patch_ordinal) for row in labels_only))
h3_out, h3_ctx = cal.apply_region_context(rows, labels_only)
check("label-pooled adoption", h3_ctx.adopted == v1_decisions[0].adopted,
      f"{h3_ctx.adopted} vs {v1_decisions[0].adopted}")
same("label-pooled offsets", h3_ctx.offsets, v1_decisions[0].offsets)
for index, (a, b) in enumerate(zip(h3_out, v1_out)):
    same(f"label-pooled printed llr {index}", a.printed_llr, b.printed_llr)
    check(f"label-pooled heldout loss {index}",
          a.heldout_logloss == b.heldout_logloss)
check("label rows are not returned", len(h3_out) == len(rows))

section("unadopted regions keep their marginal objects")
solo = (region_window(0, 900, 1000, 20, 22, 0.5, 1.0),)
solo_out, solo_ctx = cal.apply_region_context(solo)
check("small region refuses ctx", not solo_ctx.adopted, solo_ctx.reason)
check("marginal identity preserved", solo_out[0] is solo[0])


# ------------------------------------------------------ 10. ownership freeze
section("ownership freeze")
freeze_rows = tuple(region_window(*spec) for spec in
                    ((0, 1200, 1300, 96, 100, 1.4, 0.9),
                     (1, 1250, 1340, 96, 100, 0.9, 1.3),
                     (2, 1400, 1500, 80, 80, 1.1, 1.0)))
check("freeze rows accepted", all(row.accepted for row in freeze_rows),
      repr(tuple(row.refusal_reason for row in freeze_rows)))
freeze_rows = tuple(replace(row, heldout_logloss=loss)
                    for row, loss in zip(freeze_rows, (0.21, 0.09, 0.4)))
owned = cal.freeze_owners(freeze_rows, H3_ROW.cells_yx, LOOKUP, "cap", 0)


def v1_candidates():
    order = sorted(range(len(freeze_rows)),
                   key=lambda index: (float(freeze_rows[index].heldout_logloss),
                                      freeze_rows[index].patch_ordinal))
    for index in order:
        row = freeze_rows[index]
        selected = np.flatnonzero(
            v1_payload.payload_cell_mask(V1_SPEC, row.page_cells_yx)
        ).astype(np.int32, copy=False)
        yield (index, row.page, row.page_cells_yx[selected], selected,
               row.printed_llr[selected].reshape(-1, 1))


v1_frozen = v1_model.freeze_page_owners(v1_candidates(), V1_SPEC.layout.cells_yx)
check("frozen page count", len(owned) == len(v1_frozen),
      f"{len(owned)} vs {len(v1_frozen)}")
for index, (page_evidence, v1_page) in enumerate(zip(owned, v1_frozen)):
    v1_page_no, v1_cells, v1_values, v1_windows, _v1_rows = v1_page
    check(f"owned page number {index}", page_evidence.page == v1_page_no)
    same(f"owned cells {index}", page_evidence.cells_yx, v1_cells)
    same(f"owned llr {index}", page_evidence.printed_llr, v1_values[:, 0])
    same(f"owner window {index}", page_evidence.owner_window, v1_windows)
    order = np.lexsort((page_evidence.cells_yx[:, 1],
                        page_evidence.cells_yx[:, 0]))
    check(f"owned cells are row-major unique {index}",
          np.array_equal(order, np.arange(order.size)))
    check(f"owners are payload cells only {index}",
          bool(np.all(cal.payload_cell_mask(LOOKUP, page_evidence.cells_yx))))

check("refused windows never own",
      len(cal.freeze_owners(
          tuple(replace(row, accepted=False, heldout_logloss=None)
                for row in freeze_rows),
          H3_ROW.cells_yx, LOOKUP, "cap", 0)) == 0)

section("events")
window_event = cal.window_event(evidence)
region_ev = cal.region_event(solo_ctx)
check("window event shape",
      window_event.capture == "cap" and window_event.adopted
      and window_event.reason == "accepted", repr(window_event))
check("region event shape",
      region_ev.capture == "cap" and not region_ev.adopted
      and region_ev.reason == solo_ctx.reason, repr(region_ev))

print(f"\n{CHECKS - len(FAILURES)}/{CHECKS} checks passed")
if FAILURES:
    print("FAILURES:")
    for line in FAILURES:
        print(f"  - {line}")
    raise SystemExit(1)
print("VERIFY GREEN")
