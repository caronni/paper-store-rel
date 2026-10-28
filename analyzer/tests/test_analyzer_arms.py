"""W1d: the unmixing modes and the registration arms — DESIGN §4.4
(the delta frame), §4.6, and the parity leg of DESIGN §8.

Truth appears only as a SCORE: the parity leg hands GT to
`ladder.run_ladder`'s `truth_bits` (which `score_rung` applies strictly
after the certificate gate), and nothing the instrument computes has
seen it.
"""

from __future__ import annotations

import numpy as np
import pytest

from holo3.lib import local_affine, spectral
from holo3.plugins import calibrate as calibrate_plugin
from holo3.plugins import color_region_anchor as anchor
from holo3.plugins import plane_k, pose as pose_plugin

from analyzer import arms, calibrate as cal, combine as comb, unmix
from analyzer.types import KnownFrame, PLANE_OF

from ._analyzer_fixtures import i_inputs, needs_i_run


# ----------------------------------------------------- the delta frame

@pytest.mark.parametrize("rot_k", (0, 1, 2, 3))
def test_to_page_frame_reproduces_production_s_displacement(rot_k):
    """DESIGN §4.4's ruling, checked against the two real linear parts.

    Production shifts through ``pose_linear(window.affine)``, whose linear
    part is ``level_terms[:, :2] @ rotation(rot_k)``; this package shifts
    through ``level_terms[:, :2]``.  The same displacement must come out.
    """
    rng = np.random.default_rng(rot_k + 1)
    level_terms = rng.normal(0.0, 4.0, 6)
    page_linear = anchor.pose_linear(tuple(level_terms))
    rotation, _translation = pose_plugin.rotation_affine(rot_k, (128, 96))
    production_linear = page_linear @ rotation
    points = rng.normal(0.0, 50.0, (17, 2))
    delta_local = rng.normal(0.0, 1.5, (17, 2))
    want = anchor.shifted_points(points, production_linear, delta_local)
    got = anchor.shifted_points(points, page_linear,
                                arms.to_page_frame(delta_local, rot_k))
    assert np.allclose(want, got)


def test_to_page_frame_is_a_sign_flip_at_rot_k_2_and_identity_at_0():
    delta = np.array([[0.83, -0.2]])
    assert np.allclose(arms.to_page_frame(delta, 0), delta)
    assert np.allclose(arms.to_page_frame(delta, 2), -delta)
    assert np.allclose(arms.to_page_frame(arms.to_page_frame(delta, 1), 3),
                       delta)


def test_affine_terms_for_delta_is_exact_for_an_affine_delta():
    rng = np.random.default_rng(4)
    terms = tuple(rng.normal(0.0, 3.0, 6))
    cells = rng.integers(0, 200, (300, 2)).astype(np.int64)
    a0 = rng.normal(0.0, 0.4, 2)
    b = rng.normal(0.0, 0.002, (2, 2))
    delta = a0[None, :] + cells.astype(np.float64) @ b.T
    built, residual = arms.affine_terms_for_delta(terms, cells, delta)
    assert residual < 1e-9
    want = calibrate_plugin.scan_points_yx(
        terms, 1, cells.astype(np.float64) + delta)
    got = calibrate_plugin.scan_points_yx(built, 1, cells)
    assert np.allclose(want, got, atol=1e-8)


def test_affine_terms_for_delta_reports_the_residual_of_a_curved_field():
    rng = np.random.default_rng(6)
    terms = tuple(rng.normal(0.0, 3.0, 6))
    cells = np.stack(np.meshgrid(np.arange(64), np.arange(64),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    curved = np.stack((0.001 * cells[:, 0] * cells[:, 1] / 64.0,
                       np.zeros(cells.shape[0])), axis=1)
    _built, residual = arms.affine_terms_for_delta(terms, cells, curved)
    assert residual > 0.0


# ------------------------------------------------------------ smoothing

def test_smooth_offsets_normalise_by_support_and_refuse_where_there_is_none():
    """DESIGN §4.6: zero weights must never pull a solution toward 0."""
    offsets = {(4, tx): (1.0, -0.5) for tx in range(3, 9)}
    weights = {key: 10.0 for key in offsets}
    grid, support = arms.smooth_offsets(offsets, weights, (30, 30),
                                        bandwidth_tiles=2.0)
    live = np.asarray([grid[4, tx] for tx in range(3, 9)])
    assert np.allclose(live[:, 0], 1.0, atol=1e-9), (
        "support normalisation must return the solution, not a fraction "
        "of it, on a band with no neighbours")
    assert np.allclose(live[:, 1], -0.5, atol=1e-9)
    assert np.all(np.isnan(grid[25, 25])), "no support, no delta"
    assert support[4, 5] > 0.0
    assert support[25, 25] == 0.0


def test_smooth_offsets_weight_a_confident_tile_more():
    offsets = {(2, 2): (2.0, 0.0), (2, 3): (0.0, 0.0)}
    grid, _support = arms.smooth_offsets(
        offsets, {(2, 2): 100.0, (2, 3): 1.0}, (6, 6), bandwidth_tiles=2.0)
    assert grid[2, 3][0] > 1.5


# ----------------------------------------------- the unmixing seam

def _mix_and_frame(n: int = 2000, seed: int = 3, noise: float = 0.05):
    """A synthetic three-plane page under `spectral`'s own model."""
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, (n, 3), dtype=np.uint8)
    m0 = np.array([0.95, 0.95, 0.95])
    coef = np.array([[-0.40, -0.05, -0.02],
                     [-0.06, -0.38, -0.09],
                     [-0.03, -0.23, -0.39]])
    values = m0 + bits.astype(np.float64) @ coef.T
    values = values + rng.normal(0.0, noise, values.shape)
    known = np.ones((n, 3), bool)
    mix = spectral.fit_plane_mix(values, bits, known)
    frame = KnownFrame(bits=bits, known=known, furniture=np.zeros(n, bool),
                       metadata_cell=None, regressors=known.all(axis=1),
                       labels=known[:, 2], siblings=known[:, 0] & known[:, 1],
                       n_discriminating=0, furniture_kind=None,
                       target=(0, 0, 0, "Y"), detail={})
    return mix, frame, values, bits


def test_subtract_matches_plane_k_isolated_scores_exactly():
    """The seam DESIGN §4.1 asks be reused, pinned.

    `unmix_score` returns PRESENCE and `calibrate` standardises it; the
    production arm fuses the two in `plane_k.isolated_scores`.  The two
    paths must be the same arithmetic.
    """
    mix, frame, values, _bits = _mix_and_frame()
    cells = np.zeros((values.shape[0], 2), np.int64)
    presence = arms.unmix_score("subtract", 2, mix, values, frame)
    ours = calibrate_plugin.window_scores(np.asarray(-presence, np.float32))
    theirs = arms.isolated_scores(mix, frame, values, cells, 2)
    assert np.array_equal(np.asarray(ours, np.float32),
                          np.asarray(theirs, np.float32))


def test_unmix_modes_rank_the_way_the_measured_ladder_says():
    """`measure/yask`: raw is the naive read, project cancels in the mean,
    subtract cleans per cell.  Higher d' is better."""
    mix, frame, values, bits = _mix_and_frame(noise=0.05)
    target = np.asarray(bits[:, 2], bool)

    def d_prime(score):
        one, zero = score[target], score[~target]
        spread = np.sqrt(0.5 * (one.var() + zero.var()))
        return abs(one.mean() - zero.mean()) / max(spread, 1e-12)

    scores = {mode: arms.unmix_score(mode, 2, mix, values, frame)
              for mode in unmix.UNMIX_MODES if mode != "global"}
    ranked = {mode: float(d_prime(value)) for mode, value in scores.items()}
    print(f"\nd' per unmix mode (synthetic, sigma 0.05): {ranked}")
    assert ranked["project"] > ranked["raw"]
    assert ranked["subtract"] >= ranked["project"]
    assert ranked["head"] > ranked["raw"]
    assert ranked["conditional"] > ranked["raw"]


def test_head_uses_two_of_three_where_only_two_planes_are_known():
    """The relaxation DESIGN §4.6 names: a cell proving two planes is a
    two-hypothesis test, not a fall-back to the projection."""
    mix, frame, values, bits = _mix_and_frame(noise=0.12)
    from dataclasses import replace
    known = np.asarray(frame.known, bool).copy()
    known[:, 2] = False                       # the target is never known
    partial = replace(frame, known=known, siblings=known[:, 0] & known[:, 1],
                      labels=known[:, 2])
    blind = replace(partial, known=np.zeros_like(known),
                    siblings=np.zeros(known.shape[0], bool))
    target = np.asarray(bits[:, 2], bool)

    def d_prime(score):
        one, zero = score[target], score[~target]
        return abs(one.mean() - zero.mean()) / max(
            np.sqrt(0.5 * (one.var() + zero.var())), 1e-12)

    with_siblings = d_prime(arms.unmix_score("head", 2, mix, values, partial))
    without = d_prime(arms.unmix_score("head", 2, mix, values, blind))
    print(f"\nhead d' with two-of-three {with_siblings:.3f} vs "
          f"blind {without:.3f}")
    assert with_siblings > without


def test_fit_mix_falls_back_to_the_lane_scope_and_names_the_scope():
    mix, _big_frame, _big_values, _bits = _mix_and_frame(n=2000)
    _small_mix, frame, values, _bits = _mix_and_frame(
        n=120, seed=8)                                 # under MIN_FULL_ROWS
    got, scope = arms.fit_mix(values, frame, scope_ladder=("footprint",))
    assert not got.accepted and scope == "footprint"
    assert got.reason == spectral.REASON_FEW_ROWS
    got, scope = arms.fit_mix(values, frame,
                              scope_ladder=("footprint", "lane"),
                              lane_mix=mix)
    assert got.accepted and scope == "lane"
    assert arms.mix_detail(got, scope)["mix_scope"] == "lane"


def test_parse_arm_refuses_a_name_that_is_not_an_arm():
    assert arms.parse_arm("subtract+committed") == ("subtract", "committed")
    assert arms.parse_arm("head+field+offset")[1] == "field+offset"
    for bad in ("subtract", "nonsense+committed", "subtract+nonsense"):
        with pytest.raises(arms.ArmError):
            arms.parse_arm(bad)


def test_local_affine_objective_is_the_swim_s_correlation_ratio():
    """Pins the reuse: the affine arm's score IS `correlation_ratios`."""
    states = np.array([0, 0, 1, 1, 0, 1, 1, 0], np.int64)
    groups = local_affine.state_groups(states)
    perfect = states.astype(np.float64)[None, :]
    flat = np.ones((1, states.size))
    assert local_affine.correlation_ratios(groups, perfect)[0] == \
        pytest.approx(1.0)
    assert local_affine.correlation_ratios(groups, flat)[0] == 0.0


# ------------------------------------------------------------- sheet I

def _interior_certified(run, page: int, stream: str, count: int):
    keys = sorted(key for key in run.certificates
                  if key[0] == page and key[3] == stream
                  and 6 <= key[1] <= run.tiles_yx[0] - 7
                  and 6 <= key[2] <= run.tiles_yx[1] - 7)
    if len(keys) < count:
        pytest.skip(f"fewer than {count} interior certified {stream} tiles")
    step = max(1, len(keys) // count)
    return [keys[index * step] for index in range(count)]


#: The parity leg's configurations.  `subtract+committed` with no context
#: is DESIGN §4.8's PINNED DEFAULT; `subtract+offset` with production's
#: context is what `plugins/plane_k` actually composes (a blind offset
#: search, then `apply_region_context`), so it is the configuration the
#: >= 80% re-derivation gate of DESIGN §8 is a gate ON.
PARITY_CONFIGURATIONS: tuple[tuple[str, str], ...] = (
    ("subtract+committed", "none"),
    ("subtract+committed", "production"),
    ("subtract+offset", "production"),
)
PARITY_GATE_CONFIGURATION = ("subtract+offset", "production")
PARITY_TILES_PER_STREAM = 5


@needs_i_run
def test_sheet_i_parity_re_derives_production_certificates():
    """DESIGN §8's parity sample, at W1d scale (5 tiles per stream).

    The target's own certificate is hidden from the frame by
    `frame.known_frame`, so every certificate here is re-derived BLIND;
    GT enters only as `truth_bits`, which `ladder.score_rung` applies
    strictly after the certificate gate.  Zero-wrong is asserted on every
    configuration; the >= 80% re-derivation gate is asserted on the
    production-equivalent one and the whole table is PRINTED, because the
    spread between the rows is the measurement (2026-09-03: the pinned
    default with no context re-derives C 3/5, M 5/5, Y 0/5, and adding
    production's own context takes it to 5/5, 5/5, 3/5).
    """
    from analyzer import ladder, sample
    from ._analyzer_fixtures import i_truth
    run = i_inputs()
    truth = i_truth()
    page = run.live_pages[0]
    table: dict[tuple[str, str], dict[str, tuple[int, int]]] = {}
    for arm, ctx_mode in PARITY_CONFIGURATIONS:
        report: dict[str, tuple[int, int]] = {}
        for stream in ("C", "M", "Y"):
            certified = attempted = 0
            for key in _interior_certified(run, page, stream,
                                           PARITY_TILES_PER_STREAM):
                lanes = sample.lanes_for_tile(run, *key[:3])
                evidence = [
                    arms.evidence_for(
                        run, run.certificates, key, lane, arm,
                        knobs={"mix_scope_ladder": ("footprint",),
                               "ctx_mode": ctx_mode, "seed": 17})
                    for lane in lanes]
                usable = [item for item in evidence
                          if item.blind.get("refusal") is None]
                attempted += 1
                if not usable:
                    continue
                combined = comb.combine(usable, "sum")
                results = ladder.run_ladder(
                    combined, run, key, rungs=("L0", "L1"),
                    truth_bits=np.asarray(truth.user_bits[key], np.uint8))
                verdicts = {item.verdict for item in results}
                assert "wrong" not in verdicts, (arm, ctx_mode, key, results)
                assert "false_accept" not in verdicts, (arm, key, results)
                if "certified" in verdicts:
                    certified += 1
            report[stream] = (certified, attempted)
        table[(arm, ctx_mode)] = report
    print("\nparity re-derivation, sheet I, 5 interior certified tiles per "
          "stream (certified/attempted):")
    for (arm, ctx_mode), report in table.items():
        print(f"  {arm:20s} ctx={ctx_mode:11s} "
              + "  ".join(f"{stream} {value[0]}/{value[1]}"
                          for stream, value in report.items()))
    gate = table[PARITY_GATE_CONFIGURATION]
    for stream, (certified, attempted) in gate.items():
        assert certified >= 4, (
            f"{PARITY_GATE_CONFIGURATION}: {stream} {certified}/{attempted}")


ROT2_FIELD_TILES = 8


@needs_i_run
def test_sheet_i_field_arm_needs_the_page_frame_at_rot_k_2():
    """DESIGN §4.4's mandatory discriminating test.

    Sheet I's capture `5d242053` is placed 180 degrees round — EVERY one
    of its accepted placements is rot_k 2 (the other three captures are
    all rot_k 0), and the run publishes a plane field for the C plane on
    each of them.  Applying that field's delta rotated into the PAGE frame
    must lower the search-fold log loss; applying it as production stores
    it (window-local, un-rotated) must raise it.  Measured 2026-09-03 over
    ten such tiles: page frame 0.150 mean, un-rotated 0.398, committed
    0.181 — the un-rotated delta is 2.7x worse than the rotated one.

    Sheet I publishes a C field only, so C is the subject; the DESIGN
    §4.4 claim is about the FRAME, which is plane-independent.
    """
    from analyzer import frame as frame_mod, sample
    from holo3.plugins import color_sites
    run = i_inputs()
    page = run.live_pages[0]
    plane = PLANE_OF["C"]
    cell_dots = color_sites.cell_dots_of(run.row)
    rows: list[tuple] = []
    for key in _interior_certified(run, page, "C", 60):
        if len(rows) >= ROT2_FIELD_TILES:
            break
        for lane in sample.lanes_for_tile(run, *key[:3]):
            field = run.plane_fields.get(
                (lane.capture_id, lane.level_index, page, plane))
            if field is None:
                continue
            fp = frame_mod.tile_footprint(run.row, *key[:3], 16,
                                          geometry=run.geometry)
            lfp = sample.lane_footprint(lane, fp)
            if lfp is None or not np.any(lfp.observed):
                continue
            rots = {int(lane.placements[int(index)].rot_k)
                    for index in np.unique(
                        lfp.owner_index[lfp.observed]).tolist()}
            delta = plane_k.field_delta_dots(field, fp.page_cells_yx)
            if rots != {2} or delta is None:
                continue
            if float(np.max(np.abs(delta))) < 0.15:
                continue           # a null delta cannot discriminate
            folds = cal.split_folds(fp.page_cells_yx, 17)
            frame = frame_mod.known_frame(run, run.certificates, fp, key,
                                          metadata_known=False)
            crops = sample.open_crops(
                lane, lfp, bound_dots=float(cell_dots) + 2.5,
                cell_dots=cell_dots)
            mix, _scope = arms.fit_mix(
                sample.read_rgb(crops, lfp).values_rgb, frame,
                scope_ladder=("footprint",), cells_yx=fp.page_cells_yx,
                usable=np.asarray(lfp.observed, bool))
            if not mix.accepted:
                continue

            def loss_for(page_delta, *, _lane=lane, _lfp=lfp, _crops=crops,
                         _frame=frame, _folds=folds, _mix=mix) -> float:
                if page_delta is None:
                    read = sample.read_rgb(_crops, _lfp)
                else:
                    override, _residual = arms._override_for_delta(
                        _lane, _lfp, page_delta, cell_dots)
                    read = sample.read_rgb(_crops, _lfp,
                                           affine_override=override)
                assert read.refusal is None, read.refusal
                score = arms.unmix_score("subtract", plane, _mix,
                                         read.values_rgb, _frame)
                value = cal.fold_logloss(
                    score, _frame, plane, _folds,
                    usable=np.asarray(_lfp.observed, bool))
                assert value is not None
                return value

            rows.append((
                key[1], key[2], int(lane.level_index), loss_for(None),
                loss_for(arms.to_page_frame(delta, 2)),
                loss_for(np.asarray(delta, np.float64)),
                tuple(np.round(np.median(delta, axis=0), 3))))
            break
    if not rows:
        pytest.skip("no rot_k == 2 placement with a live C field on sheet I")
    table = np.asarray([[row[3], row[4], row[5]] for row in rows])
    print(f"\nrot_k 2 field arm on {len(rows)} certified C tiles "
          f"(search-fold log loss): committed {table[:, 0].mean():.4f}, "
          f"page frame {table[:, 1].mean():.4f}, "
          f"un-rotated {table[:, 2].mean():.4f}; page frame beats committed "
          f"on {int((table[:, 1] < table[:, 0]).sum())}/{len(rows)}")
    for row in rows:
        print(f"  ty={row[0]:3d} tx={row[1]:3d} L{row[2]} "
              f"committed {row[3]:.4f} page {row[4]:.4f} "
              f"un-rotated {row[5]:.4f} median delta {row[6]}")
    assert np.all(table[:, 1] < table[:, 2]), (
        "the un-rotated production delta must be worse on EVERY tile")
    assert table[:, 1].mean() < table[:, 0].mean(), (
        "the page-frame field must help on average")


@needs_i_run
def test_sheet_i_offset_arm_lands_near_the_rotated_field_delta():
    """DESIGN §4.6's offset arm against the standing field, blind.

    The brief asks this on Y; sheet I publishes a plane field for the C
    plane ONLY (13 fields, all plane 0 — `test_analyzer_inputs`), so the
    measurement is made on C and the deviation is recorded.  The
    assertion is loose on purpose: the two estimators are a whole-page
    smoothed fit and a per-footprint grid, and the number worth having is
    the DISTRIBUTION, which is printed.
    """
    from analyzer import frame as frame_mod, sample
    from holo3.plugins import color_sites
    run = i_inputs()
    page = run.live_pages[0]
    plane = PLANE_OF["C"]
    cell_dots = color_sites.cell_dots_of(run.row)
    gaps: list[float] = []
    chosen: list[tuple] = []
    for key in _interior_certified(run, page, "C", 60):
        if len(gaps) >= 6:
            break
        for lane in sample.lanes_for_tile(run, *key[:3]):
            field = run.plane_fields.get(
                (lane.capture_id, lane.level_index, page, plane))
            if field is None:
                continue
            fp = frame_mod.tile_footprint(run.row, *key[:3], 16,
                                          geometry=run.geometry)
            lfp = sample.lane_footprint(lane, fp)
            if lfp is None or not np.any(lfp.observed):
                continue
            delta = plane_k.field_delta_dots(field, fp.page_cells_yx)
            if delta is None:
                continue
            rot = {int(lane.placements[int(index)].rot_k)
                   for index in np.unique(
                       lfp.owner_index[lfp.observed]).tolist()}
            if len(rot) != 1:
                continue
            inside = np.asarray(fp.in_tile) & np.asarray(lfp.observed)
            want = np.median(arms.to_page_frame(delta[inside],
                                                rot.pop()), axis=0)
            folds = cal.split_folds(fp.page_cells_yx, 17)
            frame = frame_mod.known_frame(run, run.certificates, fp, key,
                                         metadata_known=False)
            crops = sample.open_crops(
                lane, lfp, bound_dots=float(cell_dots) + 2.5,
                cell_dots=cell_dots)
            mix, _scope = arms.fit_mix(
                sample.read_rgb(crops, lfp).values_rgb, frame,
                scope_ladder=("footprint",), cells_yx=fp.page_cells_yx,
                usable=np.asarray(lfp.observed, bool))
            if not mix.accepted:
                continue
            _read, detail = arms.register(
                "offset", lane, crops, lfp, frame, plane, "subtract",
                folds, mix=mix, cell_dots=cell_dots)
            got = np.asarray(detail["offset_dots_xy"], np.float64)
            gaps.append(float(abs(got[0] - want[0])))
            chosen.append((key[1], key[2], tuple(np.round(got, 3)),
                           tuple(np.round(want, 3))))
            break
    if not gaps:
        pytest.skip("no C tile with a live plane field on sheet I")
    array = np.asarray(gaps)
    print(f"\noffset vs rotated field delta (x axis, dots): "
          f"n={array.size} median={np.median(array):.3f} "
          f"max={array.max():.3f}\n  {chosen}")
    assert float(np.median(array)) <= 1.0


@needs_i_run
def test_sheet_i_word_arm_decodes_a_certified_c_tile_blind():
    """DESIGN §4.6's `word` arm: the 100 sites must decode to the counter."""
    from analyzer import frame as frame_mod, sample
    from holo3.plugins import color_sites
    run = i_inputs()
    page = run.live_pages[0]
    plane = PLANE_OF["C"]
    cell_dots = color_sites.cell_dots_of(run.row)
    outcomes: list[tuple] = []
    for key in _interior_certified(run, page, "C", 4):
        lane = sample.lanes_for_tile(run, *key[:3])[0]
        fp = frame_mod.tile_footprint(run.row, *key[:3], 16,
                                      geometry=run.geometry)
        lfp = sample.lane_footprint(lane, fp)
        if lfp is None or not np.any(lfp.observed):
            continue
        frame = frame_mod.known_frame(run, run.certificates, fp, key,
                                     metadata_known=False)
        frame = arms._with_format(frame, run)
        crops = sample.open_crops(lane, lfp,
                                  bound_dots=float(cell_dots) + 2.5,
                                  cell_dots=cell_dots)
        mix, _scope = arms.fit_mix(
            sample.read_rgb(crops, lfp).values_rgb, frame,
            scope_ladder=("footprint",), cells_yx=fp.page_cells_yx,
            usable=np.asarray(lfp.observed, bool))
        if not mix.accepted:
            continue
        _read, detail = arms.word_pose(lane, crops, lfp, frame, plane,
                                       mix=mix, cell_dots=cell_dots)
        outcomes.append((key[1], key[2], detail.get("word_decoded_counter"),
                         detail.get("word_counter"),
                         detail.get("word_erasures"),
                         detail.get("refusal")))
    print(f"\nword arm on certified C tiles "
          f"(ty, tx, decoded, counter, erasures, refusal): {outcomes}")
    assert outcomes, "no certified C tile could be read at all"
    decoded = [row for row in outcomes if row[2] is not None
               and row[2] == row[3]]
    assert decoded, f"the word decoded on none of them: {outcomes}"


@needs_i_run
def test_sheet_i_word_arm_refuses_on_the_yellow_plane():
    """C and M only — Y is 0 at every word site (DESIGN §1)."""
    from analyzer import frame as frame_mod, sample
    from holo3.plugins import color_sites
    run = i_inputs()
    page = run.live_pages[0]
    key = _interior_certified(run, page, "Y", 1)[0]
    lane = sample.lanes_for_tile(run, *key[:3])[0]
    cell_dots = color_sites.cell_dots_of(run.row)
    fp = frame_mod.tile_footprint(run.row, *key[:3], 32,
                                  geometry=run.geometry)
    lfp = sample.lane_footprint(lane, fp)
    frame = arms._with_format(
        frame_mod.known_frame(run, run.certificates, fp, key,
                              metadata_known=False), run)
    crops = sample.open_crops(lane, lfp, bound_dots=float(cell_dots) + 2.5,
                              cell_dots=cell_dots)
    _read, detail = arms.word_pose(lane, crops, lfp, frame, PLANE_OF["Y"],
                                   mix=None, cell_dots=cell_dots)
    assert detail["refusal"] == "word_is_cm_only"


def test_head_never_reads_the_target_plane_off_the_frame():
    """The circularity that made `head` score 0.0000 on labels.

    Restricting the head's state hypotheses on the TARGET plane's own
    known bit turns the score into the label; only the SIBLINGS may
    restrict it.  Caught on sheet I, 2026-09-03.
    """
    mix, frame, values, bits = _mix_and_frame(noise=0.6)
    score = arms.unmix_score("head", 2, mix, values, frame)
    target = np.asarray(bits[:, 2], bool)
    err = float(np.mean((score > 0) != target))
    assert err > 0.0, "the head is reading its own labels"
    # and it must be no better on labelled cells than on unlabelled ones
    from dataclasses import replace
    hidden = np.asarray(frame.known, bool).copy()
    hidden[:, 2] = False
    blind = arms.unmix_score(
        "head", 2, mix, values, replace(frame, known=hidden))
    assert np.allclose(score, blind)


@pytest.mark.parametrize("module", ("arms", "unmix", "calibrate", "combine"))
def test_w1d_modules_are_blind(module):
    """DESIGN §0 / PLAN §0: the import-set test, for W1d's four modules.

    `mother` and `ladder` already carry one; W1d's modules did not, and
    the blindness rule names them explicitly ("unmix, register,
    calibrate, combine ... never import truth or oracle").
    """
    import ast
    import importlib
    import pathlib
    loaded = importlib.import_module(f"analyzer.{module}")
    tree = ast.parse(pathlib.Path(loaded.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add("." * node.level + (node.module or ""))
    assert not any("truth" in name or "oracle" in name
                   for name in imported), sorted(imported)


def test_the_lane_mix_tile_sample_is_the_same_in_every_process():
    """DESIGN §0's determinism rule: no salted `hash` in a seed.

    The seed drove a `fold_hash` draw over the page's tiles, so a salted
    hash would give every process a different lane-scope mixing model.
    """
    seed = unmix._stable_seed(("0123456789ab", 2), 0, "C")
    assert seed == 4085383775088843719
    assert unmix._stable_seed(("0123456789ab", 2), 0, "M") != seed


@needs_i_run
def test_the_field_arm_refuses_a_field_from_another_plane():
    """The `field` arm must not apply a field it was not handed for.

    Sheet I publishes a C-plane field only; asking for it on the Y
    stream (or on another lane) has to collapse to `committed` with a
    reason, never move the points by another plane's registration.
    """
    from analyzer import frame as frame_mod, sample
    run = i_inputs()
    page = run.live_pages[0]
    plane = PLANE_OF["C"]
    for key in _interior_certified(run, page, "C", 20):
        for lane in sample.lanes_for_tile(run, *key[:3]):
            field = run.plane_fields.get(
                (lane.capture_id, lane.level_index, page, plane))
            if field is None:
                continue
            fp = frame_mod.tile_footprint(run.row, *key[:3], 16,
                                          geometry=run.geometry)
            lfp = sample.lane_footprint(lane, fp)
            if lfp is None or not np.any(lfp.observed):
                continue
            mine, _detail = arms._field_delta(field, lane, lfp, plane)
            if mine is None:
                continue
            other, detail = arms._field_delta(field, lane, lfp,
                                              PLANE_OF["Y"])
            assert other is None
            assert detail["field_applied"] is False
            assert "field_is_for_" in detail["field_reason"]
            return
    pytest.skip("no certified C tile of this page carries a plane field")
