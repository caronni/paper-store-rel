"""E022 v2: per-window native pose, parity-split placement, provenance.

The render helper generates scenes by FORWARD affine indexing (ground-truth
Jacobian + origin), never ndimage.rotate — the decoder side under test never
rotates or decimates a raster either.
"""
from __future__ import annotations

import dataclasses
import json
import pickle
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/022-pilot-tile-search"))

from paperholo import place, pilotsearch  # noqa: E402
from paperholo.formats import FormatDescriptor  # noqa: E402
from paperholo.platen import PayloadRegion, PayloadSurvey  # noqa: E402
import run_e022  # noqa: E402

INK, PAPER, BACK = 45.0, 205.0, 245.0


def _format(seed: bytes = b"paper-store/e022-test") -> FormatDescriptor:
    return FormatDescriptor("e022-test", seed, 3, "kcell-c3", (600, 480))


def _page_bits(descriptor: FormatDescriptor, rng: np.random.Generator
               ) -> np.ndarray:
    spec = descriptor.spec()
    values, sites = place.pilot_field(spec, descriptor.seed, 0)
    bits = rng.integers(0, 2, spec.page_cells_yx, dtype=np.uint8)
    bits[sites] = values[sites]
    return bits


def _fragment(
    page_bits: np.ndarray,
    origin_yx: tuple[int, int],
    shape: tuple[int, int],
    rot_k: int,
) -> tuple[np.ndarray, np.ndarray]:
    y, x = origin_yx
    h, w = shape
    bits = np.rot90(page_bits[y:y + h, x:x + w], -rot_k)
    return bits, 1.0 - 2.0 * bits.astype(np.float32)


def _gt_jacobian(pitch_v: float, pitch_u: float, angle_deg: float,
                 shear_deg: float = 0.0) -> np.ndarray:
    """Columns = lattice basis vectors b_v, b_u (the pose convention)."""
    a = np.deg2rad(angle_deg)
    s = np.deg2rad(angle_deg + shear_deg)
    b_v = pitch_v * np.array([np.cos(a), -np.sin(a)])
    b_u = pitch_u * np.array([np.sin(s), np.cos(s)])
    return np.stack([b_v, b_u], axis=1)


def _render_affine(
    bits: np.ndarray,
    jac: np.ndarray,
    origin_px: tuple[float, float],
    out_shape: tuple[int, int],
    rng: np.random.Generator,
    *,
    blur: float = 1.1,
    noise: float = 2.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Forward-render a cell-bit scrap under a ground-truth affine pose.

    Returns (image, support mask) — the mask is what e021 would deliver."""
    yy, xx = np.indices(out_shape)
    rel = (np.stack([yy.ravel(), xx.ravel()], axis=1).astype(np.float64)
           - np.asarray(origin_px, np.float64))
    cells = np.rint(rel @ np.linalg.inv(jac).T).astype(np.int64)
    inside = ((cells[:, 0] >= 0) & (cells[:, 0] < bits.shape[0])
              & (cells[:, 1] >= 0) & (cells[:, 1] < bits.shape[1]))
    flat = np.full(out_shape[0] * out_shape[1], BACK, np.float32)
    flat[inside] = np.where(
        bits[cells[inside, 0], cells[inside, 1]] > 0, INK, PAPER)
    img = flat.reshape(out_shape)
    img = ndimage.gaussian_filter(img, blur)
    img += rng.normal(0.0, noise, img.shape).astype(np.float32)
    return np.clip(img, 0.0, 255.0), inside.reshape(out_shape)


def _survey_for(img_shape: tuple[int, int], pitch_px: float,
                mask: np.ndarray | None = None) -> PayloadSurvey:
    region = PayloadRegion(
        (0, 0, img_shape[0], img_shape[1]),
        np.ones(img_shape, bool) if mask is None else mask,
        area_mm2=1000.0, angle_hint_deg=None, score=40.0,
    )
    return PayloadSurvey((region,), c_dots=3, cell_pitch_px=pitch_px)


def _mapping_error_cells(
    result: pilotsearch.SearchResult,
    jac_gt: np.ndarray,
    origin_gt_px: tuple[float, float],
    scrap_origin_cells: tuple[int, int],
    pitch: float,
) -> float:
    """Max |pose-mapped - GT| scan error over placed support, in cells.

    Only valid for rot_k == 0 placements (asserted by the callers)."""
    worst = 0.0
    for placed in result.placements:
        assert placed.rot_k == 0
        sample = placed.page_cells_yx[:: max(1, len(placed.page_cells_yx) // 64)]
        window_cells = sample - np.asarray(placed.origin_yx, np.int64)
        got = placed.pose.points(window_cells)
        gt_rel = sample - np.asarray(scrap_origin_cells, np.int64)
        want = (gt_rel.astype(np.float64) @ np.asarray(jac_gt).T
                + np.asarray(origin_gt_px, np.float64))
        worst = max(worst, float(np.max(np.hypot(*(got - want).T))) / pitch)
    return worst


# ---------------------------------------------------------------------------
# correlation core (unchanged API, kept as regression)
# ---------------------------------------------------------------------------

def test_soft_field_correlation_all_rotations_and_four_tile_straddle() -> None:
    descriptor = _format(b"paper-store/e022-correlation")
    spec = descriptor.spec()
    page_bits = _page_bits(descriptor, np.random.default_rng(2201))
    config = pilotsearch.SearchConfig(min_support=8, gate_gap=0.06)
    origin = (175, 177)  # crosses both 60-cell boundaries at 180
    for rot_k in range(4):
        bits, evidence = _fragment(page_bits, origin, (90, 90), rot_k)
        result = pilotsearch.correlate_fragment(
            evidence, np.ones(bits.shape, bool), spec, descriptor.seed,
            pages=(0,), pending_cell_mask=None, config=config,
        )
        assert result.ok
        assert result.page == 0
        assert result.origin_yx == origin
        assert result.rot_k == rot_k
        assert result.mismatch < 1e-5
        assert result.diagnostics["validation_mismatch"] < 1e-5
        assert result.diagnostics["rival_searched"] is True


def test_random_field_refuses() -> None:
    descriptor = _format(b"paper-store/e022-null")
    rng = np.random.default_rng(2202)
    bits = rng.integers(0, 2, (120, 130), dtype=np.uint8)
    result = pilotsearch.correlate_fragment(
        1.0 - 2.0 * bits.astype(np.float32), np.ones(bits.shape, bool),
        descriptor.spec(), descriptor.seed, pages=(0,),
        pending_cell_mask=None, config=pilotsearch.SearchConfig(min_support=15),
    )
    assert not result.ok


# ---------------------------------------------------------------------------
# rot90 bookkeeping pins
# ---------------------------------------------------------------------------

def test_rot_affine_matches_rotated_points_all_k_asymmetric() -> None:
    shape = (7, 11)
    pts = np.array([[0, 0], [3, 5], [6, 10], [2, 9]], np.int64)
    for k in range(4):
        want = pilotsearch._rotated_points(pts, shape, k)
        s, t = pilotsearch._rot_affine(k, shape)
        got = np.rint(pts @ s.T + t).astype(np.int64)
        assert np.array_equal(got, want), k


def test_predict_from_anchor_pure_translation() -> None:
    """A window offset purely along the lattice predicts origin exactly."""
    jac = _gt_jacobian(8.0, 8.0, 0.0)
    pose_a = pilotsearch.AffinePose(
        (100.0, 200.0), tuple(map(tuple, jac)), 0.0, 8.0, (0.0, 0.0))
    for rot_k in range(4):
        anchor = pilotsearch.PlacedWindow(
            region_index=0, window=pilotsearch.Window(0, 0, 50, 60, 3000),
            page=0, origin_yx=(40, 70), rot_k=rot_k, method="correlation",
            mismatch=0.0, validation_mismatch=0.0, rival_mismatch=0.5,
            support=100, pose=pose_a, elapsed_s=0.0,
        )
        d_cells = np.array([10.0, 25.0])
        pose_w = pilotsearch.AffinePose(
            tuple(np.array([100.0, 200.0]) + jac @ d_cells),
            tuple(map(tuple, jac)), 0.0, 8.0, (0.0, 0.0))
        got = pilotsearch.predict_from_anchor(anchor, pose_w, (50, 60))
        s, t_a = pilotsearch._rot_affine(rot_k, (50, 60))
        _, t_w = pilotsearch._rot_affine(rot_k, (50, 60))
        want = s @ d_cells + t_a - t_w + np.array([40.0, 70.0])
        assert got == (int(round(want[0])), int(round(want[1]))), rot_k


# ---------------------------------------------------------------------------
# parity discipline (the v1 leak, structurally regressed)
# ---------------------------------------------------------------------------

def test_parity_mask_preserves_frozen_split() -> None:
    rng = np.random.default_rng(2211)
    mask = rng.random((37, 43)) > 0.2
    yy, xx = np.indices(mask.shape)
    for parity in (0, 1):
        want = mask & (((yy * 131 + xx * 17) & 1) == parity)
        got = pilotsearch._split_mask(mask, parity)
        assert np.array_equal(got, want)

    origin = (173, 119)
    for parity in (0, 1):
        want = (((yy + origin[0]) * 131
                 + (xx + origin[1]) * 17) & 1) == parity
        got = pilotsearch._parity_mask(mask.shape, origin, parity)
        assert np.array_equal(got, want)


def test_score_known_splits_only_the_overlap(monkeypatch) -> None:
    """Local scoring must not allocate page-sized parity arrays per probe."""
    descriptor = _format(b"paper-store/e022-local-parity")
    spec = descriptor.spec()
    rng = np.random.default_rng(2212)
    evidence = rng.normal(size=(137, 149)).astype(np.float32)
    mask = rng.random(evidence.shape) > 0.15

    def reference(
        origin_yx: tuple[int, int], rot_k: int, parity: int
    ) -> tuple[float, int, float]:
        values, sites = place.pilot_field(spec, descriptor.seed, 0)
        yy, xx = np.indices(sites.shape)
        sites = sites & (((yy * 131 + xx * 17) & 1) == parity)
        obs = np.rot90(evidence, rot_k)
        keep = np.rot90(mask, rot_k)
        sl = place.overlap_slices(
            origin_yx, obs.shape, values.shape
        )
        if sl is None:
            return 1.0, 0, -np.inf
        pys, pxs, fys, fxs = sl
        selected = sites[pys, pxs] & keep[fys, fxs]
        if not selected.any():
            return 1.0, 0, -np.inf
        expected = 1.0 - 2.0 * values[pys, pxs].astype(np.float32)
        weights = np.abs(obs[fys, fxs][selected])
        corr = float(np.sum(expected[selected] * obs[fys, fxs][selected]))
        total = float(weights.sum())
        mismatch = (total - corr) / (2.0 * total) if total > 0 else 1.0
        return (
            float(mismatch),
            int(selected.sum()),
            corr / np.sqrt(max(total, 1e-9)),
        )

    cases = (
        ((173, 119), 0),
        ((-31, 401), 1),
        ((542, -29), 3),
    )
    expected = {
        (origin, rot_k, parity): reference(origin, rot_k, parity)
        for origin, rot_k in cases
        for parity in (0, 1)
    }

    def full_page_split_is_forbidden(*_args, **_kwargs):
        raise AssertionError("_score_known rebuilt full-page parity")

    monkeypatch.setattr(
        pilotsearch, "_split_mask", full_page_split_is_forbidden
    )
    for origin, rot_k in cases:
        for parity in (0, 1):
            got = pilotsearch._score_known(
                evidence, mask, spec, descriptor.seed, 0,
                origin, rot_k, parity=parity,
            )
            want = expected[(origin, rot_k, parity)]
            np.testing.assert_allclose(got, want, rtol=0.0, atol=0.0)


def test_place_by_prediction_search_and_validation_parities_disjoint() -> None:
    descriptor = _format(b"paper-store/e022-parity")
    spec = descriptor.spec()
    page_bits = _page_bits(descriptor, np.random.default_rng(2210))
    origin = (120, 96)
    bits, evidence = _fragment(page_bits, origin, (130, 140), 0)
    mask = np.ones(bits.shape, bool)
    config = pilotsearch.SearchConfig(min_support=15)
    placed = pilotsearch.place_by_prediction(
        evidence, mask, spec, descriptor.seed, 0, 0, origin, config)
    assert placed is not None and placed.ok
    assert placed.origin_yx == origin
    assert placed.diagnostics["rival_searched"] is False

    # corrupt ONLY the validation-parity page sites: search still argmaxes
    # to the true origin, but acceptance must fail on the disjoint check
    yy, xx = np.indices(bits.shape)
    page_parity = (((yy + origin[0]) * 131 + (xx + origin[1]) * 17) & 1) == 1
    corrupted = np.where(page_parity, -evidence, evidence)
    rejected = pilotsearch.place_by_prediction(
        corrupted, mask, spec, descriptor.seed, 0, 0, origin, config)
    assert rejected is None

    # corrupt ONLY the search-parity sites: the argmax input is destroyed;
    # a survivor (if any) must never be a wrong-address acceptance
    corrupted = np.where(~page_parity, -evidence, evidence)
    stray = pilotsearch.place_by_prediction(
        corrupted, mask, spec, descriptor.seed, 0, 0, origin, config)
    assert stray is None or stray.origin_yx == origin


# ---------------------------------------------------------------------------
# end-to-end: native pose recovery, subpixel placement, chain provenance
# ---------------------------------------------------------------------------

def _window_progress_scene():
    """Small deterministic field with one correlation anchor and chains."""
    descriptor = _format(b"paper-store/e022-window-progress")
    rng = np.random.default_rng(2299)
    page_bits = _page_bits(descriptor, rng)
    scrap = page_bits[120:220, 90:190]
    pitch = 4.0
    jac = _gt_jacobian(pitch, pitch, -2.0)
    canvas, support = _render_affine(
        scrap, jac, (50.0, 50.0), (520, 520), rng,
        blur=0.7, noise=1.0,
    )
    cells = np.argwhere(support)
    y0, x0 = cells.min(axis=0)
    y1, x1 = cells.max(axis=0) + 1
    region = PayloadRegion(
        (int(y0), int(x0), int(y1 - y0), int(x1 - x0)),
        support[y0:y1, x0:x1], 100.0, None, 40.0,
    )
    survey = PayloadSurvey((region,), c_dots=3, cell_pitch_px=pitch)
    config = pilotsearch.SearchConfig(
        window_cells=100, overlap_cells=20, min_window_cells=40,
        bch_first=False, min_support=15,
    )
    return descriptor, canvas, survey, config


def test_search_survey_window_progress_reports_pose_route_and_completion(
) -> None:
    descriptor, canvas, survey, config = _window_progress_scene()
    events: list[pilotsearch.WindowProgress] = []

    result = pilotsearch.search_survey(
        canvas, survey, descriptor, config=config,
        on_window=lambda _current, progress: events.append(progress),
    )

    assert result.region_states == {0: "accepted"}
    terminal = [row for row in events if row.stage == "window_complete"]
    assert len(terminal) == sum(
        len(rows) for rows in result.diagnostics["window_audit"].values()
    )
    assert [row.ordinal for row in terminal] == list(
        range(1, len(terminal) + 1)
    )
    assert {row.method for row in terminal} >= {"correlation", "chain"}
    assert {row.outcome for row in terminal} <= {
        "accepted", "redundant_skipped"
    }

    first_open = next(row for row in events if row.stage == "window_open")
    assert first_open.pose_origin_yx is None
    assert first_open.jacobian_yx is None
    assert first_open.angle_deg is None
    assert first_open.pitch_px is None
    assert first_open.attempted_routes == ()
    assert first_open.window_shape_yx_cells == (100, 100)

    posed = next(row for row in events if row.stage == "pose_fitted")
    pose_numbers = [
        posed.angle_deg, posed.pitch_px, posed.pitch_v_px,
        posed.pitch_u_px, posed.ortho_dev_deg, posed.phase_conf,
        *posed.pose_origin_yx, *posed.phase_yx,
        *(value for axis in posed.jacobian_yx for value in axis),
    ]
    assert np.isfinite(pose_numbers).all()
    y, x, h, w = posed.scan_bbox_yxhw_px
    assert 0 <= y < canvas.shape[0] and 0 <= x < canvas.shape[1]
    assert 0 < h <= canvas.shape[0] - y
    assert 0 < w <= canvas.shape[1] - x

    stages = [row.stage for row in events]
    assert "correlation" in stages
    assert "chain" in stages
    assert "refine" in stages
    for row in terminal:
        assert row.placement_page == 0
        assert row.placement_origin_yx is not None
        assert row.placement_rot_k in range(4)
        assert row.support is not None and row.support >= config.min_support
        assert row.elapsed_s >= 0.0
        # Observer snapshots promise plain JSON values and no NaN/Infinity.
        json.dumps(dataclasses.asdict(row), allow_nan=False)


def test_search_survey_window_progress_is_timing_and_state_neutral(
        monkeypatch) -> None:
    descriptor, canvas, survey, config = _window_progress_scene()

    class Clock:
        def __init__(self) -> None:
            self.now = 0.0

        def __call__(self) -> float:
            return self.now

        def advance(self, seconds: float) -> None:
            self.now += seconds

    plain_clock = Clock()
    monkeypatch.setattr(pilotsearch, "perf_counter", plain_clock)
    plain = pilotsearch.search_survey(
        canvas, survey, descriptor, config=config)

    observed_clock = Clock()
    monkeypatch.setattr(pilotsearch, "perf_counter", observed_clock)
    snapshots = []

    def slow_observer(_current, progress) -> None:
        snapshots.append(progress)
        observed_clock.advance(3.25)

    observed = pilotsearch.search_survey(
        canvas, survey, descriptor, config=config,
        on_window=slow_observer,
    )

    assert snapshots
    assert observed_clock.now == 3.25 * len(snapshots)
    assert plain.timings == observed.timings
    assert all(row.elapsed_s == 0.0 for row in observed.placements)
    # Window snapshots are transient: even deliberately expensive observers
    # leave the complete SearchResult byte-identical under a fixed clock.
    assert pickle.dumps(plain) == pickle.dumps(observed)


def test_search_survey_recovers_affine_pose_subpixel() -> None:
    """Rotation + anisotropy + shear + subpixel origin at a NON-integer
    pitch, angle hint withheld — the v1 failure class."""
    descriptor = _format(b"paper-store/e022-pose")
    rng = np.random.default_rng(2203)
    page_bits = _page_bits(descriptor, rng)
    scrap_origin = (120, 90)
    scrap = page_bits[120:340, 90:310]           # 220x220 cells
    pitch = 11.7
    jac_gt = _gt_jacobian(pitch * 1.004, pitch, -3.6, shear_deg=0.25)
    origin_gt = (140.37, 130.61)
    span = int(np.ceil(220 * pitch * 1.15)) + 280
    canvas, support = _render_affine(scrap, jac_gt, origin_gt,
                                     (span, span), rng)
    survey = _survey_for(canvas.shape, pitch, support)
    config = pilotsearch.SearchConfig(bch_first=False, min_support=20)
    result = pilotsearch.search_survey(
        canvas, survey, descriptor, config=config)
    assert result.region_states == {0: "accepted"}
    assert len(result.placements) >= 3
    methods = {row.method for row in result.placements}
    assert "chain" in methods
    for row in result.placements:
        if row.method == "chain":
            assert row.rival_searched is False
            assert row.rival_mismatch is None
            assert row.predicted_residual_cells is not None
        else:
            assert row.rival_searched is True
        assert row.component == 0
        assert row.validation_mismatch < 0.15
        jac = row.pose.matrix()
        assert np.max(np.abs(jac - jac_gt)) < 0.012 * pitch
    err = _mapping_error_cells(
        result, jac_gt, origin_gt, scrap_origin, pitch)
    assert err < 0.35, f"mapping error {err:.3f} cells"
    assert any(tile.bch_ok for tile in result.tiles.values())


def test_search_survey_native_24px_per_cell() -> None:
    """The 200-cpi print / 4800-dpi scan class: ~24 px/cell sampled
    natively — no internal predecimation path exists to fall back on."""
    descriptor = _format(b"paper-store/e022-native")
    rng = np.random.default_rng(2204)
    page_bits = _page_bits(descriptor, rng)
    scrap_origin = (180, 120)
    scrap = page_bits[180:300, 120:240]           # 120x120 cells
    pitch = 23.85
    jac_gt = _gt_jacobian(pitch, pitch * 0.997, 2.4)
    origin_gt = (90.25, 110.75)
    span = int(np.ceil(120 * pitch * 1.1)) + 200
    canvas, support = _render_affine(scrap, jac_gt, origin_gt,
                                     (span, span), rng, blur=2.2, noise=2.0)
    survey = _survey_for(canvas.shape, pitch, support)
    result = pilotsearch.search_survey(
        canvas, survey, descriptor,
        config=pilotsearch.SearchConfig(bch_first=False, min_support=20))
    assert result.region_states == {0: "accepted"}
    err = _mapping_error_cells(
        result, jac_gt, origin_gt, scrap_origin, pitch)
    assert err < 0.35, f"mapping error {err:.3f} cells"


def test_y_step_splits_components_and_places_both_sides() -> None:
    """A 5-cell scanner y-jump breaks one rigid pose; both sides must place
    correctly as separate components with correct page origins."""
    descriptor = _format(b"paper-store/e022-step")
    rng = np.random.default_rng(2205)
    page_bits = _page_bits(descriptor, rng)
    pitch = 8.0
    jac = _gt_jacobian(pitch, pitch, 0.0)
    top = page_bits[60:180, 96:296]               # 120x200 cells
    bottom = page_bits[180:300, 96:296]
    step_cells = 5
    h_px = int((240 + step_cells) * pitch) + 160
    w_px = int(200 * pitch) + 160
    canvas = np.full((h_px, w_px), BACK, np.float32)
    img_top, sup_top = _render_affine(top, jac, (80.0, 80.0),
                                      canvas.shape, rng)
    split_px = int(80 + 120 * pitch)
    img_bot, sup_bot = _render_affine(
        bottom, jac, (80.0 + (120 + step_cells) * pitch, 80.0),
        canvas.shape, rng)
    canvas[:split_px] = img_top[:split_px]
    canvas[split_px:] = img_bot[split_px:]
    support = np.zeros(canvas.shape, bool)
    support[:split_px] = sup_top[:split_px]
    support[split_px:] = sup_bot[split_px:]
    survey = _survey_for(canvas.shape, pitch, support)
    result = pilotsearch.search_survey(
        canvas, survey, descriptor,
        config=pilotsearch.SearchConfig(bch_first=False, min_support=20))
    assert result.region_states == {0: "accepted"}
    assert len({row.component for row in result.placements}) >= 2
    # both page mappings must be recovered: mapping offset = page cell of
    # window cell (0,0) minus its scan position in prior-pitch cells
    offsets = {
        int(round(row.origin_yx[0] - (row.pose.origin_yx[0] - 80.0) / pitch))
        for row in result.placements
    }
    assert offsets == {60, 60 - step_cells}, offsets
    # and no observation may be emitted under the wrong side's mapping:
    # on this clean render, correctly mapped sites agree ~perfectly while a
    # wrong-side site is a coin flip (the block audit strips those)
    agree = total = 0
    for tile in result.tiles.values():
        for observations in tile.observations.values():
            for obs in observations:
                agree += int(obs.bit == obs.expected)
                total += 1
    assert total > 300
    assert agree / total > 0.97, agree / total


def test_bch_seed_recovers_origin_with_parity_checks() -> None:
    descriptor = _format(b"paper-store/e022-bch")
    rng = np.random.default_rng(2206)
    page_bits = _page_bits(descriptor, rng)
    origin = (173, 119)
    bits, evidence = _fragment(page_bits, origin, (150, 160), 0)
    placement, errors, elapsed = pilotsearch.try_bch_seed(
        bits, evidence, np.ones(bits.shape, bool),
        descriptor.spec(), descriptor.seed, pages=(0,),
        config=pilotsearch.SearchConfig(min_support=20),
    )
    assert placement is not None and placement.ok
    assert placement.origin_yx == origin
    assert errors == 0
    assert elapsed > 0
    assert placement.diagnostics["bch_seed"] is True
    assert placement.diagnostics["rival_searched"] is False


def test_cross_scrap_fill_of_partially_observed_tiles() -> None:
    """A second scrap lying ENTIRELY inside already-found tiles must still
    be admitted when it covers those tiles' unobserved sites, and the
    union must decode words the first scrap alone could not — the design's
    cross-scrap resurrection contract. (The v2 tile-granular need mask
    measurably rejected exactly this scrap: every tile it touches is
    'found' at >=20 sites, yet the four hole quadrants are unobserved.)"""
    descriptor = _format(b"paper-store/e022-halves")
    rng = np.random.default_rng(2209)
    page_bits = _page_bits(descriptor, rng)
    pitch = 8.0
    jac = _gt_jacobian(pitch, pitch, 0.0)
    # scrap A: page cells 96..236 square, with a 60x60-cell hole at
    # 150..210 straddling the shared corner of tiles (2,2)(2,3)(3,2)(3,3):
    # each of the four tiles keeps ~75 observed sites (found) and loses
    # one ~25-site quadrant.
    a_bits = page_bits[96:236, 96:236]
    img_a, sup_a = _render_affine(a_bits, jac, (60.0, 60.0),
                                  (int(140 * pitch) + 120,
                                   int(140 * pitch) + 120), rng)
    hole = (slice(int(60 + 54 * pitch), int(60 + 114 * pitch)),
            slice(int(60 + 54 * pitch), int(60 + 114 * pitch)))
    img_a[hole] = BACK
    sup_a[hole] = False
    # scrap B: cells 130..230 — the hole plus a generous rim, entirely
    # within already-found tiles. (A minimal 70-cell fill measures the
    # small-support rival-floor limit instead: at 61 search-parity sites a
    # decoy dipped to 0.166 < the 0.20 bar frozen at >=135-site support,
    # an honest refusal recorded as a registered open item.)
    b_bits = page_bits[130:230, 130:230]
    img_b, sup_b = _render_affine(b_bits, jac, (60.0, 60.0),
                                  (int(100 * pitch) + 120,
                                   int(100 * pitch) + 120), rng)
    canvas = np.full((img_a.shape[0],
                      img_a.shape[1] + img_b.shape[1] + 160), BACK,
                     np.float32)
    canvas[:img_a.shape[0], :img_a.shape[1]] = img_a
    bx0 = img_a.shape[1] + 160
    canvas[:img_b.shape[0], bx0:bx0 + img_b.shape[1]] = img_b
    regions = (
        PayloadRegion((0, 0, *img_a.shape), sup_a, 500.0, 0.0, 40.0),
        PayloadRegion((0, bx0, *img_b.shape), sup_b, 100.0, 0.0, 40.0),
    )
    result = pilotsearch.search_survey(
        canvas, PayloadSurvey(regions, 3, pitch), descriptor,
        config=pilotsearch.SearchConfig(bch_first=False),
    )
    assert result.region_states == {0: "accepted", 1: "accepted"}
    assert {row.region_index for row in result.placements} == {0, 1}
    for key in ((0, 2, 2), (0, 2, 3), (0, 3, 2), (0, 3, 3)):
        tile = result.tiles[key]
        contributing = {obs.region_index
                        for observations in tile.observations.values()
                        for obs in observations}
        assert 1 in contributing, key           # scrap B filled the hole
        assert tile.observed_sites >= 80, key   # union crosses 2e+f<=26
        assert tile.bch_ok is True, key


def test_missing_survey_pitch_falls_back_to_descriptor_prior() -> None:
    """A survey without a measured pitch uses scan_dpi x c / 600 (the
    section-2 contract); the per-window spectral fit re-measures locally."""
    descriptor = _format(b"paper-store/e022-nopitch")
    rng = np.random.default_rng(2211)
    page_bits = _page_bits(descriptor, rng)
    pitch = 8.0
    jac = _gt_jacobian(pitch, pitch, 4.0)
    scrap = page_bits[120:280, 96:256]
    img, support = _render_affine(scrap, jac, (60.0, 60.0),
                                  (int(160 * pitch * 1.1) + 120,
                                   int(160 * pitch * 1.1) + 120), rng)
    region = PayloadRegion((0, 0, *img.shape), support, 500.0, None, 40.0)
    survey = PayloadSurvey((region,), c_dots=None, cell_pitch_px=None)
    import pytest
    with pytest.raises(ValueError, match="pitch"):
        pilotsearch.search_survey(img, survey, descriptor)
    result = pilotsearch.search_survey(
        img, survey, descriptor, scan_dpi=1600.0,
        config=pilotsearch.SearchConfig(bch_first=False, min_support=20))
    assert result.diagnostics["pitch_prior_source"] == "descriptor"
    assert result.region_states == {0: "accepted"}


def test_redundant_windows_are_recorded_not_silently_dropped() -> None:
    descriptor = _format(b"paper-store/e022-needed")
    rng = np.random.default_rng(2207)
    page_bits = _page_bits(descriptor, rng)
    pitch = 8.0
    jac = _gt_jacobian(pitch, pitch, 0.0)
    scrap = page_bits[173:323, 119:279]
    img, _sup = _render_affine(scrap, jac, (80.0, 80.0),
                               (int(150 * pitch) + 160,
                                int(160 * pitch) + 160), rng)
    canvas = np.full((img.shape[0], img.shape[1] * 2 + 120), BACK,
                     np.float32)
    canvas[:, :img.shape[1]] = img
    canvas[:, img.shape[1] + 120:] = img
    regions = (
        PayloadRegion((0, 0, *img.shape), np.ones(img.shape, bool),
                      500.0, 0.0, 40.0),
        PayloadRegion((0, img.shape[1] + 120, *img.shape),
                      np.ones(img.shape, bool), 400.0, 0.0, 40.0),
    )
    result = pilotsearch.search_survey(
        canvas, PayloadSurvey(regions, 3, pitch), descriptor,
        config=pilotsearch.SearchConfig(
            bch_first=False, found_tile_min_sites=1, min_support=15),
    )
    assert result.diagnostics["region_order"] == [0, 1]
    assert result.region_states[0] == "accepted"
    # the duplicate region places but adds no unobserved pilot site
    assert result.region_states[1] == "redundant"
    audit = result.diagnostics["window_audit"][1]
    assert any(row.get("outcome") == "redundant_skipped" for row in audit)
    # v2.2 (the E023 seam): redundant windows are recorded as FULL gated
    # placements — payload need != pilot need, and the payload pass samples
    # through every gated pose — while pilot emission stays suppressed.
    non_redundant = [row for row in result.placements if not row.redundant]
    redundant = [row for row in result.placements if row.redundant]
    assert {row.region_index for row in non_redundant} == {0}
    assert redundant and {row.region_index for row in redundant} == {1}
    for row in redundant:
        assert row.page_cells_yx.size > 0          # audited payload core
        assert np.isfinite(row.pose.matrix()).all()
        assert row.component == -1                 # never an anchor
        assert row.validation_mismatch < 0.15      # gated like any placement
    contributing = {
        obs.region_index
        for tile in result.tiles.values()
        for observations in tile.observations.values()
        for obs in observations
    }
    assert contributing == {0}                     # no redundant emission


def test_observations_are_rim_eroded() -> None:
    """No emitted pilot observation may sit within erode_cells of the
    window-support boundary (the measured 016.7 rim-poison class)."""
    descriptor = _format(b"paper-store/e022-rim")
    rng = np.random.default_rng(2208)
    page_bits = _page_bits(descriptor, rng)
    pitch = 8.0
    jac = _gt_jacobian(pitch, pitch, 0.0)
    scrap = page_bits[120:280, 96:256]            # 160x160 cells
    img, support = _render_affine(scrap, jac, (60.0, 60.0),
                                  (int(160 * pitch) + 120,
                                   int(160 * pitch) + 120), rng)
    survey = _survey_for(img.shape, pitch, support)
    config = pilotsearch.SearchConfig(bch_first=False, min_support=20)
    result = pilotsearch.search_survey(img, survey, descriptor,
                                       config=config)
    assert result.placements
    n_obs = 0
    for tile in result.tiles.values():
        for observations in tile.observations.values():
            for obs in observations:
                n_obs += 1
                # scan coordinate must sit at least erode_cells inside the
                # rendered scrap extent
                margin = config.erode_cells * pitch * 0.99
                assert obs.scan_yx[0] > 60.0 - pitch + margin
                assert obs.scan_yx[1] > 60.0 - pitch + margin
    assert n_obs > 100


def test_three_pane_png_smoke(tmp_path: Path) -> None:
    descriptor = _format(b"paper-store/e022-png")
    image = np.full((320, 480), 220.0, np.float32)
    region = PayloadRegion(
        (40, 50, 160, 200), np.ones((160, 200), bool),
        area_mm2=20.0, angle_hint_deg=None, score=10.0,
    )
    survey = PayloadSurvey((region,), c_dots=3, cell_pitch_px=8.0)
    result = pilotsearch.SearchResult(region_states={0: "unresolved"})
    out = tmp_path / "e022.png"
    run_e022.render_diagnostic(image, survey, result, descriptor, out,
                               panel_width=240)
    assert out.exists()
    rendered = Image.open(out)
    assert rendered.width == 720
    assert rendered.height > 200
