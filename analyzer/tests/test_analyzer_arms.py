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

from holo.receiver.lib import local_affine, page_map, spectral
from holo.receiver.plugins import calibrate as calibrate_plugin
from holo.receiver.plugins import color_region_anchor as anchor
from holo.receiver.plugins import plane_k, pose as pose_plugin, swim

from analyzer import arms, calibrate as cal, field2_kernel, sample, unmix
from analyzer.types import KnownFrame, PLANE_OF

from ._analyzer_fixtures import needs_sim, sim_run


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
    want = page_map.raster_points(points, production_linear, delta_local, 1)
    got = page_map.raster_points(points, page_linear,
                                 arms.to_page_frame(delta_local, rot_k), 1)
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


# The `smooth_offsets` pins went with the `smooth` arm on 2026-09-12
# (A3): a field per (lane, stream) with the page dropped from its key
# merged two physical faces on a duplex sheet.


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

    # `global` needs the lane mix and the patch family (W8) needs a read
    # context — both are enumerated through their own doors, not here.
    from analyzer import patch as patch_mod
    scores = {mode: arms.unmix_score(mode, 2, mix, values, frame)
              for mode in unmix.UNMIX_MODES
              if mode not in ("global",) + tuple(patch_mod.PATCH_MODES)}
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


# ---------------------------------------------- the colour sim's run dir
# TIER S (2026-10-09): the receiver's displaced 10x10 colour sim, Y two
# dots out of register along a one-cycle sinusoid down the page.  The
# sheet-I numbers these tests printed are records (PAGE-FIELD-PLAN A1b).

def _interior_certified(run, page: int, stream: str, count: int):
    keys = sorted(key for key in run.certificates
                  if key[0] == page and key[3] == stream
                  and 1 <= key[1] <= run.tiles_yx[0] - 2
                  and 1 <= key[2] <= run.tiles_yx[1] - 2)
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

# DELETED at A1b, 2026-09-12: `test_sheet_i_field_arm_needs_the_page_
# frame_at_rot_k_2`, the discriminating test of the RETIRED per-lane
# field.  It needed a rot-2 placement to discriminate a frame, and the
# fixture corpus has none — all 988 accepted placements of the
# single-capture run stand at rot_k 0, so there was nothing to
# re-measure and no honest way to flip its assertions.  The law it
# stood for is pinned offline, on both rotations, by
# `test_the_field_arm_reads_one_page_vector_on_every_rotation`.


@needs_sim
def test_the_offset_arm_lands_near_the_published_field_delta():
    """DESIGN §4.6's offset arm against the standing field, blind, on Y —
    the plane the sim displaces, so the field is not zero and the gap
    discriminates.  The published delta is read UNROTATED (A1): it is a
    page-axis vector at its source.  The assertion is loose on purpose:
    the two estimators are a whole-page smoothed fit and a per-footprint
    grid, and the number worth having is the DISTRIBUTION, which is
    printed (sheet I's C plane, the record: n=6, median 0.124 dots).
    """
    from analyzer import frame as frame_mod, sample
    from holo.receiver.plugins import color_sites
    run = sim_run()
    page = run.live_pages[0]
    plane = PLANE_OF["Y"]
    cell_dots = color_sites.cell_dots_of(run.row)
    gaps: list[float] = []
    chosen: list[tuple] = []
    for key in _interior_certified(run, page, "Y", 60):
        if len(gaps) >= 6:
            break
        for lane in sample.lanes_for_tile(run, *key[:3]):
            field = run.plane_fields.get((page, plane))
            if field is None:
                continue
            fp = frame_mod.tile_footprint(run.row, *key[:3], 16,
                                          geometry=run.geometry)
            lfp = sample.lane_footprint(lane, fp)
            if lfp is None or not np.any(lfp.observed):
                continue
            delta = np.asarray(
                plane_k.field_delta_dots(field, fp.page_cells_yx),
                np.float64)
            inside = np.asarray(fp.in_tile) & np.asarray(lfp.observed)
            want = np.median(delta[inside], axis=0)
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
        pytest.skip("no Y tile with a live plane field on the sim")
    array = np.asarray(gaps)
    print(f"\noffset vs rotated field delta (x axis, dots): "
          f"n={array.size} median={np.median(array):.3f} "
          f"max={array.max():.3f}\n  {chosen}")
    assert float(np.median(array)) <= 1.0


@needs_sim
def test_the_word_arm_decodes_a_certified_c_tile_blind():
    """DESIGN §4.6's `word` arm: the 100 sites must decode to the counter."""
    from analyzer import frame as frame_mod, sample
    from holo.receiver.plugins import color_sites
    run = sim_run()
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


@needs_sim
def test_the_word_arm_refuses_on_the_yellow_plane():
    """C and M only — Y is 0 at every word site (DESIGN §1)."""
    from analyzer import frame as frame_mod, sample
    from holo.receiver.plugins import color_sites
    run = sim_run()
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


@needs_sim
def test_the_field_arm_refuses_a_field_from_another_plane_on_a_real_run():
    """AI4 on a published field: another plane is the one other refusal.

    The offline half is `test_the_field_arm_refuses_another_page_and_
    another_plane`; this is the same law over a `PlaneField` the receiver
    published for C on the sim, off a real footprint, so the refusal
    cannot be an artefact of the synthetic fact's shape.
    """
    from analyzer import frame as frame_mod, sample
    run = sim_run()
    page = run.live_pages[0]
    plane = PLANE_OF["C"]
    field = run.plane_fields[(page, plane)]
    for key in _interior_certified(run, page, "C", 4):
        for lane in sample.lanes_for_tile(run, *key[:3]):
            fp = frame_mod.tile_footprint(run.row, *key[:3], 16,
                                          geometry=run.geometry)
            lfp = sample.lane_footprint(lane, fp)
            if lfp is None or not np.any(lfp.observed):
                continue
            other, detail = arms._field_delta(field, lfp, PLANE_OF["Y"])
            assert other is None
            assert detail["field_applied"] is False
            assert detail["field_reason"] == \
                f"field_is_for_plane_{plane}_not_{PLANE_OF['Y']}"
            return
    pytest.fail("no lane observes an interior certified C tile of the sim")


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


def test_the_lane_mix_tile_sample_is_the_same_in_every_process():
    """DESIGN §0's determinism rule: no salted `hash` in a seed.

    The seed drove a `fold_hash` draw over the page's tiles, so a salted
    hash would give every process a different lane-scope mixing model.
    """
    seed = unmix._stable_seed(("0123456789ab", 2), 0, "C")
    assert seed == 4085383775088843719
    assert unmix._stable_seed(("0123456789ab", 2), 0, "M") != seed


# ------------------------------------------ the production field, offline
# AB1/AI1/AI3/AI4, over a synthetic `holo.receiver.data.PlaneField` — a
# plain frozen dataclass — so the three laws are pinned on this machine
# whether or not a run dir is.

FIELD_TILES_YX = (37, 53)
FIELD_CELL_DOTS = 2


def _plane_field(delta_xy, *, page=0, plane=0, uncertainty=0.4, ordinal=17):
    from holo.receiver import data
    delta = np.zeros(FIELD_TILES_YX + (2,), np.float64)
    delta[..., 0], delta[..., 1] = delta_xy
    return data.PlaneField(
        page=page, plane=plane, delta_dots_xy=delta,
        support=np.ones(FIELD_TILES_YX, np.float64),
        uncertainty_dots=np.full(FIELD_TILES_YX, float(uncertainty)),
        n_observations=int(np.prod(FIELD_TILES_YX)), n_captures=2,
        ordinal=int(ordinal))


def _field_footprint(owner_index, *, page=0, ty=4, tx=6):
    """One tile's worth of cells, owned by the placements named."""
    from analyzer.types import LaneFootprint, TileFootprint
    owners = np.asarray(owner_index, np.int64)
    cells = np.stack((np.full(owners.size, ty * 64 + 10, np.int64),
                      tx * 64 + np.arange(owners.size, dtype=np.int64)),
                     axis=1)
    fp = TileFootprint(page=page, ty=ty, tx=tx, halo_cells=0,
                       page_cells_yx=cells,
                       in_tile=np.ones(owners.size, bool),
                       cargo=np.ones(owners.size, bool),
                       page_shape_cells_yx=(64 * FIELD_TILES_YX[0],
                                            64 * FIELD_TILES_YX[1]))
    return LaneFootprint(lane=("cap", 0), tile=fp,
                         observed=np.ones(owners.size, bool),
                         owner_index=owners,
                         points_yx=np.zeros((owners.size, 2), np.float64))


class _Placement:
    def __init__(self, native_affine, rot_k):
        self.native_affine = tuple(native_affine)
        self.rot_k = int(rot_k)


class _Lane:
    """The two attributes `sample._level_terms` reads, and nothing else."""

    def __init__(self, placements):
        from fractions import Fraction
        self.frame = Fraction(1)
        self.placements = tuple(placements)


#: A rot-0 page-cell -> pixel affine, and the SAME window placed 180
#: degrees round: production folds the quarter-turn into `native_affine`,
#: so at rot 2 the linear part is negated.
ROT0_TERMS = (6.0, 0.4, 120.0, -0.3, 6.1, 340.0)
ROT2_TERMS = (-6.0, -0.4, 980.0, 0.3, -6.1, 770.0)


def test_the_field_arm_reads_one_page_vector_on_every_rotation():
    """AB1: a published delta is page-frame AT ITS SOURCE.

    `_field_delta` returns the field's own value on a rot-0 owner and on
    a rot-2 owner alike — no quarter-turn — and pushing that value
    through `_override_for_delta` displaces each owner's sample points
    by the SAME vector in PAGE CELLS, which is what "one page vector"
    means once the two owners' poses differ.
    """
    from holo.receiver.plugins import calibrate as calibrate_plugin
    from holo.receiver.plugins import color_region_anchor as anchor

    field = _plane_field((0.7, -0.3))
    lfp = _field_footprint([0, 0, 1, 1])
    lane = _Lane((_Placement(ROT0_TERMS, 0), _Placement(ROT2_TERMS, 2)))

    delta, detail = arms._field_delta(field, lfp, 0)
    assert detail["field_applied"] is True
    assert np.allclose(delta, np.array([[0.7, -0.3]] * 4)), (
        "the arm rotated a page-axis delta")
    assert not np.allclose(delta, arms.to_page_frame(delta, 2))

    override, _residual = arms._override_for_delta(lane, lfp, delta,
                                                   FIELD_CELL_DOTS)
    cells = np.asarray(lfp.tile.page_cells_yx, np.float64)
    want = np.asarray((-0.3, 0.7), np.float64) / FIELD_CELL_DOTS  # (y, x)
    for index in (0, 1):
        rows = np.flatnonzero(np.asarray(lfp.owner_index) == index)
        terms = (ROT0_TERMS, ROT2_TERMS)[index]
        before = calibrate_plugin.scan_points_yx(terms, 1, cells[rows])
        after = calibrate_plugin.scan_points_yx(override[index], 1,
                                                cells[rows])
        moved_cells = np.linalg.solve(anchor.pose_linear(terms),
                                      (after - before).T).T
        assert np.allclose(moved_cells, want, atol=1e-9), (
            f"owner {index} moved {moved_cells[0]} page cells, not {want}")


def test_the_field_arm_applies_on_any_lane_of_its_page():
    """AI4: the key is (page, plane), so every lane of the page reads it.

    The lane the footprint names is deliberately not the one any field
    was fitted on — there is no such thing any more — and the read has
    to succeed anyway.
    """
    field = _plane_field((0.5, 0.0))
    for lane_id in (("capA", 2), ("capB", 8), ("cap", 0)):
        lfp = _field_footprint([0, 0])
        lfp = type(lfp)(lane=lane_id, tile=lfp.tile, observed=lfp.observed,
                        owner_index=lfp.owner_index,
                        points_yx=lfp.points_yx)
        delta, detail = arms._field_delta(field, lfp, 0)
        assert detail["field_applied"] is True, lane_id
        assert np.allclose(delta, np.array([[0.5, 0.0]] * 2))


def test_the_field_arm_refuses_another_page_and_another_plane():
    """AI4's two refusals, and the only two."""
    lfp = _field_footprint([0, 0], page=0)
    delta, detail = arms._field_delta(_plane_field((0.5, 0.0), page=1), lfp,
                                      0)
    assert delta is None
    assert detail == {"field_applied": False,
                      "field_reason": "field_is_for_page_1_not_0"}

    delta, detail = arms._field_delta(_plane_field((0.5, 0.0), plane=2), lfp,
                                      0)
    assert delta is None
    assert detail["field_reason"] == "field_is_for_plane_2_not_0"

    delta, detail = arms._field_delta(None, lfp, 0)
    assert delta is None and detail["field_reason"] == "no_field"

    # target_plane None: the arm was not told which plane it is reading,
    # so the plane clause has nothing to compare and does not fire.
    delta, _detail = arms._field_delta(_plane_field((0.5, 0.0), plane=2),
                                       lfp, None)
    assert delta is not None


def test_a_field_that_reads_zero_collapses_by_name_and_still_reports():
    """AI3: a zero delta renames the row; it never duplicates `committed`.

    `no_support` is gone with production's support gate (design I6/I8) —
    an unsupported tile reads the pose, which IS zero — so the collapse
    is made on the VALUE, and it carries the two things a reader wants
    to know about the field that stood there, and (F4, 2026-09-13) which
    cells decided it.
    """
    lfp = _field_footprint([0, 0, 1])
    zero = _plane_field((0.0, 0.0), uncertainty=0.62, ordinal=41906)
    delta, detail = arms._field_delta(zero, lfp, 0)
    assert delta is None
    assert detail["field_applied"] is False
    assert detail["field_reason"] == "field_reads_zero_here"
    assert detail["field_collapse_over"] == "observed"
    assert detail["field_uncertainty_dots"] == pytest.approx(0.62)
    assert detail["field_ordinal"] == 41906

    live = _plane_field((0.0, -0.25), uncertainty=0.11, ordinal=7)
    delta, detail = arms._field_delta(live, lfp, 0)
    assert delta is not None
    assert detail["field_applied"] is True
    assert detail["field_uncertainty_dots"] == pytest.approx(0.11)
    assert detail["field_ordinal"] == 7
    assert detail["field_median_dots_xy"] == pytest.approx((0.0, -0.25))
    assert "field_rot_k" not in detail and "no_support" not in str(detail)


def test_the_reported_uncertainty_is_the_median_over_the_footprints_tiles():
    """A footprint spanning four tiles reports THEIR median, not the
    page's: the number is about where this row read."""
    from analyzer.types import LaneFootprint, TileFootprint
    field = _plane_field((0.4, 0.0))
    grid = np.asarray(field.uncertainty_dots)
    grid[4, 6], grid[4, 7], grid[5, 6], grid[5, 7] = 0.1, 0.2, 0.8, 0.9
    cells = np.array([[4 * 64 + 1, 6 * 64 + 1], [4 * 64 + 1, 7 * 64 + 1],
                      [5 * 64 + 1, 6 * 64 + 1], [5 * 64 + 1, 7 * 64 + 1]],
                     np.int64)
    fp = TileFootprint(page=0, ty=4, tx=6, halo_cells=64,
                       page_cells_yx=cells, in_tile=np.ones(4, bool),
                       cargo=np.ones(4, bool),
                       page_shape_cells_yx=(64 * FIELD_TILES_YX[0],
                                            64 * FIELD_TILES_YX[1]))
    lfp = LaneFootprint(lane=("cap", 0), tile=fp,
                        observed=np.ones(4, bool),
                        owner_index=np.zeros(4, np.int64),
                        points_yx=np.zeros((4, 2), np.float64))
    _delta, detail = arms._field_delta(field, lfp, 0)
    assert detail["field_uncertainty_dots"] == pytest.approx(0.5)


# ------------------------------- the crop the standing field reaches (F3)
# On the review's own fixture (`docs/reviews/page-field-analyzer-2026-09-13/
# probes/sampling.py`): one rot-0 placement over a 900x900 synthetic
# raster at 8 px per cell, so a bound in dots grows the crop by four
# times as many pixels at c2 and by 2.67 at c3.  The bound the arms cut
# at counted the offset search and the patch window and NOT the standing
# field, so the field spent the aperture margin instead.

_SEARCH_EXTREME_DOTS = arms.OFFSET_X_MAX


def _standing_world(halo: int = 8):
    from .test_analyzer_sample import _footprint, _lane, _placement
    lane = _lane(_placement())
    return lane, sample.lane_footprint(lane, _footprint(halo))


def _search_bound_dots(cell_dots: int) -> float:
    """The bound `evidence_for` cut at before F3 — search and cell only."""
    return max(abs(arms.OFFSET_X_MIN), abs(arms.OFFSET_X_MAX),
               float(cell_dots)) + 0.5


def _field_read(lane, lfp, field, cell_dots, *, reach: bool,
                offset_dots_x: float = 0.0):
    bound = _search_bound_dots(cell_dots)
    if reach:
        bound += arms.field_reach_dots("field", lfp, 0, plane_field=field)
    crops = sample.open_crops(lane, lfp, bound_dots=bound,
                              cell_dots=cell_dots)
    delta, _detail = arms._field_delta(field, lfp, 0)
    override, _residual = arms._override_for_delta(lane, lfp, delta,
                                                   cell_dots)
    read = sample.read_rgb(crops, lfp, offset_dots_xy=(offset_dots_x, 0.0),
                           affine_override=override, arm="field")
    return read, crops


def test_the_crop_bound_carries_the_standing_fields_reach_at_c2():
    """F3: a field past the old bound refused; it reads now.

    MEASURED on this fixture at c2, 8 px per cell: the bare `field` arm
    refused past 4.25 dots of constant field and the crop only reached
    that far because it borrows `anchor.points_halo` (8 px here, 2 dots)
    — so a 4.5-dot field was a lost arm and a 3.0-dot one was a read
    with 5 px of margin where the aperture alone wants 8.  With the
    reach in the bound both read, and the 3.0-dot read sits 14 px from
    the edge: the aperture's margin is the aperture's again.
    """
    lane, lfp = _standing_world()
    past = _plane_field((4.5, 0.0))
    refused, _crops = _field_read(lane, lfp, past, 2, reach=False)
    assert refused.refusal == "outside_crop:72"
    read, _crops = _field_read(lane, lfp, past, 2, reach=True)
    assert read.refusal is None
    assert arms.field_reach_dots("field", lfp, 0, plane_field=past) == 4.5

    inside = _plane_field((3.0, 0.0))
    tight, tight_crops = _field_read(lane, lfp, inside, 2, reach=False)
    wide, wide_crops = _field_read(lane, lfp, inside, 2, reach=True)
    assert tight.refusal is None and wide.refusal is None
    assert sample.read_headroom_px(tight_crops, lfp, tight) == 5.0
    assert sample.read_headroom_px(wide_crops, lfp, wide) == 14.0
    assert 5.0 < anchor.points_halo(8.0) <= 14.0


def test_the_crop_bound_carries_the_standing_fields_reach_at_c3():
    """The same at c3, where the cell is the wider term of the bound.

    The old bound refused past 6.25 dots of constant field (the same
    fixture, 8 px per cell), so 6.5 is the smallest quarter-dot step
    that was a lost arm.
    """
    lane, lfp = _standing_world()
    past = _plane_field((6.5, 0.0))
    refused, _crops = _field_read(lane, lfp, past, 3, reach=False)
    assert refused.refusal == "outside_crop:72"
    read, _crops = _field_read(lane, lfp, past, 3, reach=True)
    assert read.refusal is None


def test_the_affine_arms_corner_reach_is_twice_the_translation_bound():
    """M1: the factor `field_reach_dots`'s last paragraph states.

    `local_affine.search` halves the translation bound before it opens
    the linear terms and clips each of them there, and the normalised
    coordinates run to +-1, so an axis's two terms add one more
    translation bound where they meet at the corner — 2x, not the
    review's 3x, which read `search_linear`'s own signature.  Driven to
    its extreme by a score that wants the largest displacement there is,
    and held at both rungs; then the ruling that keeps it out of the
    crop bound, measured: a CONSTANT delta of that size, which is worse
    than an affine reaching it at one corner, still reads.
    """
    cells = np.stack(np.meshgrid(np.arange(8), np.arange(8), indexing="ij"),
                     -1).reshape(-1, 2)
    unit = local_affine.unit_coordinates(cells, (8, 8))
    lane, lfp = _standing_world()
    for cell_dots in (2, 3):
        crops = sample.open_crops(lane, lfp, cell_dots=cell_dots,
                                  bound_dots=_search_bound_dots(cell_dots))
        bound = swim.translation_bound_dots(arms.lane_row_of(crops))
        assert bound == float(cell_dots)
        result = local_affine.search(
            lambda candidates: np.array([one.magnitude_dots()
                                         for one in candidates], np.float64),
            local_affine.Affine.zero(), bound, 0.05, 64)
        reach = np.abs(result.affine.offsets_dots_xy(unit)).max()
        assert reach == pytest.approx(2.0 * bound)

        read, wide = _field_read(lane, lfp, _plane_field((2.0 * bound, 0.0)),
                                 cell_dots, reach=False)
        assert read.refusal is None
        assert sample.read_headroom_px(wide, lfp, read) == 1.0


def test_the_field_and_the_offset_search_extreme_share_one_crop():
    """`field+offset` at the winner's +2-dot extreme, the tight corner.

    The search and the field both move the points, so the reach the
    crop needs is their SUM: at c2 the old bound refused past 2.25 dots
    of field once the offset sat at its own limit, against 4.25 with the
    offset at zero.
    """
    lane, lfp = _standing_world()
    field = _plane_field((2.5, 0.0))
    refused, _crops = _field_read(lane, lfp, field, 2, reach=False,
                                  offset_dots_x=_SEARCH_EXTREME_DOTS)
    assert refused.refusal == "outside_crop:72"
    read, _crops = _field_read(lane, lfp, field, 2, reach=True,
                               offset_dots_x=_SEARCH_EXTREME_DOTS)
    assert read.refusal is None


def test_a_field_that_leaves_the_raster_is_still_a_correct_refusal():
    """The bound cannot buy pixels that were never scanned.

    A field pushing 6 dots off the raster's own origin maps points to
    x = -8 px; the crop is clipped there because that is where the
    capture ends, so `outside_crop` is the right answer and the reach
    does not paper over it.
    """
    lane, lfp = _standing_world()
    off = _plane_field((-6.0, 0.0))
    read, crops = _field_read(lane, lfp, off, 2, reach=True)
    assert read.refusal == "outside_crop:72"
    assert (crops.y0, crops.x0) == (0, 0)
    delta, _detail = arms._field_delta(off, lfp, 0)
    mapped = page_map.raster_points(
        lfp.points_yx, np.eye(2, dtype=np.float64) * 8.0,
        np.asarray(delta, np.float64), 2)
    assert mapped[:, 1].min() == pytest.approx(-8.0)


def test_the_reach_is_quantised_to_the_search_step_and_scoped_by_arm():
    """One bound per lane, so the memo's cut count does not fragment.

    Rounding UP to `OFFSET_STEP_DOTS` keeps arms that read the same
    field over the same footprint asking for the same crop; the arms
    that read no field ask for the bound they always asked for, and the
    `field2` arms take field2's own clamp, which is all that is known
    before the fit.
    """
    lane, lfp = _standing_world()
    field = _plane_field((1.1, 0.0))
    assert arms.field_reach_dots("field", lfp, 0, plane_field=field) == 1.25
    assert arms.field_reach_dots("field+offset", lfp, 0,
                                 plane_field=field) == 1.25
    for arm in ("committed", "offset", "affine", "word"):
        assert arms.field_reach_dots(arm, lfp, 0, plane_field=field) == 0.0
    for arm in arms.FIELD2_ARMS:
        assert arms.field_reach_dots(arm, lfp, 0) == field2_kernel.BOUND_DOTS
    # nothing stands, or what stands is not this page's: nothing to add
    assert arms.field_reach_dots("field", lfp, 0, plane_field=None) == 0.0
    assert arms.field_reach_dots(
        "field", lfp, 0, plane_field=_plane_field((3.0, 0.0), page=1)) == 0.0
    assert arms.field_reach_dots(
        "field", lfp, 0, plane_field=_plane_field((0.0, 0.0))) == 0.0


# ------------------------------ the collapse over the consumed cells (F4)

def _corner_field(value_dots_x: float = 2.0):
    """Zero over tile (0, 0)'s own cells, non-zero past the next centre.

    A 3x3 grid whose right column alone is displaced: the target tile's
    cells all lie between the centres of tiles 0 and 1, which are both
    zero, so they read EXACTLY zero however large the corner is — and a
    cell past centre 1 (page cell 96) interpolates toward it.
    """
    from holo.receiver import data
    grid = np.zeros((3, 3, 2), np.float64)
    grid[:, 2, 0] = float(value_dots_x)
    return data.PlaneField(
        page=0, plane=0, delta_dots_xy=grid,
        support=np.ones((3, 3), np.float64),
        uncertainty_dots=np.full((3, 3), 0.4), n_observations=9,
        n_captures=1, ordinal=11)


def _halo_world(halo: int):
    """A window wide enough for a halo to pass the next tile centre.

    The sample module's own placement stops at 96 cells — exactly the
    centre — so a footprint that reaches page cell 97, the first cell
    that can read a field the target's own cells cannot, needs a wider
    one.  The raster is 900 px at 8 px per cell, which is what caps this
    at 104.
    """
    from .test_analyzer_sample import _footprint, _lane, _placement
    lane = _lane(_placement(extent=(0, 0, 104, 104)))
    return lane, sample.lane_footprint(lane, _footprint(halo))


def test_a_zero_target_with_a_live_halo_no_longer_collapses():
    """F4: the collapse is over the cells the arm CONSUMES.

    The target's own cells read exactly zero and the halo's do not — and
    the halo is not a spectator: `_override_for_delta` fits each owner's
    affine over its observed cells, halo included, so the corrections
    the old predicate discarded moved the TARGET's sample points too.
    Under it this row collapsed to `committed` and called itself
    byte-identical to it; the count below is what that claim cost.
    """
    lane, lfp = _halo_world(40)
    field = _corner_field()
    delta, detail = arms._field_delta(field, lfp, 0)
    assert detail["field_applied"] is True
    in_tile = np.asarray(lfp.tile.in_tile, bool)
    observed = np.asarray(lfp.observed, bool)
    assert not np.any(delta[in_tile & observed])
    assert np.count_nonzero(
        np.any(delta[~in_tile & observed], axis=1)) == 728

    override, _residual = arms._override_for_delta(lane, lfp, delta, 2)
    bound = _search_bound_dots(2) + arms.field_reach_dots(
        "field", lfp, 0, plane_field=field)
    crops = sample.open_crops(lane, lfp, bound_dots=bound, cell_dots=2)
    committed = sample.read_rgb(crops, lfp, arm="reference")
    applied = sample.read_rgb(crops, lfp, affine_override=override,
                              arm="field")
    assert committed.refusal is None and applied.refusal is None
    target = in_tile & observed
    moved = np.any(applied.points_yx != committed.points_yx, axis=1) & target
    assert int(np.count_nonzero(moved)) == int(np.count_nonzero(target))


def test_the_default_halo_cannot_reach_the_cells_that_change_the_answer():
    """The scope of F4: the divergence needs a halo past the next centre.

    At the default halos (16 for C and M, 32 for Y) the footprint stops
    inside the same tile-centre interval as its target, so a target that
    reads zero forces a halo that reads zero and the collapse IS
    byte-identical — 33 cells of halo still are, 34 is not.  Only
    `wide-halo` (48) reaches that far by default, which is why widening
    the predicate costs the twin reuse nothing anyone was paid.
    """
    field = _corner_field()
    for halo in (arms.HALO_CELLS["C"], arms.HALO_CELLS["Y"], 33):
        _lane_unused, lfp = _halo_world(halo)
        delta, detail = arms._field_delta(field, lfp, 0)
        assert delta is None, halo
        assert detail["field_reason"] == "field_reads_zero_here"
        assert detail["field_collapse_over"] == "observed"
    _lane_unused, lfp = _halo_world(34)
    delta, detail = arms._field_delta(field, lfp, 0)
    assert delta is not None and detail["field_applied"] is True
