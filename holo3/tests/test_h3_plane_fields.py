"""The per-plane registration field: numerics, cell, dial, read side.

Everything here is synthetic and takes milliseconds — the end-to-end
yield case (a displaced plane costing certificates and the field buying
them back) is the widened-lane module test_h3_color_field_yield.py,
because that pair of decodes alone costs more wall than the whole slow
lane's budget.
"""

from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

import numpy as np
import pytest

from holo3 import data, engine
from holo3.descriptor import KEY_PLANE_FIELD
from holo3.lib import plane_field
from holo3.lib.geometry import TILE_CELLS
from holo3.plugins import color_region, field_tiers, fields
from holo3.plugins import color_region_anchor as anchor
from holo3.tests import _h3_facts, _h3_support

TILES_YX = (6, 5)
CELL_DOTS = 3
FORMAT_REF = "c3-k-r0550@7x7"


def _engine(plane_fields_on: bool) -> engine._Engine:
    request = data.DecodeRequest(
        scans=(Path("scan.tiff"),), dpis=(1200.0,), format_ref=FORMAT_REF,
        max_pages=1, workers=1, complete=False, no_close=False,
        diag_port=None,
        run_dir=Path(tempfile.mkdtemp(prefix="h3-fields-")),
        plane_fields=plane_fields_on)
    return engine._Engine(request, [])


def _cells(tiles_yx: tuple[int, int] = TILES_YX,
           step: int = 8) -> np.ndarray:
    ys = np.arange(0, tiles_yx[0] * TILE_CELLS, step)
    xs = np.arange(0, tiles_yx[1] * TILE_CELLS, step)
    grid = np.stack(np.meshgrid(ys, xs, indexing="ij"), axis=-1)
    return grid.reshape(-1, 2).astype(np.int64)


def _linear_evidence(cells: np.ndarray, truth_dots_xy: np.ndarray,
                     gain: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    """A response that is exactly linear in the offset, so the solve has
    a known right answer.

    The per-cell gradient sweeps every direction: a tile whose cells all
    responded identically would be telling the fit nothing, because a
    common response inside a tile is exactly what the accumulator centres
    away as a brightness offset.  Real cells disagree the same way — a
    left ink edge and a right ink edge move opposite ways under the same
    displacement.
    """
    phase = 2.0 * np.pi * (np.arange(cells.shape[0]) % 8) / 8.0
    gradient = gain * np.stack((np.cos(phase), np.sin(phase)), axis=1)
    residual = (gradient * truth_dots_xy).sum(axis=1)
    return gradient, residual


def _uniform_truth(cells: np.ndarray, dx: float,
                   dy: float) -> np.ndarray:
    truth = np.empty((cells.shape[0], 2), np.float64)
    truth[:, 0] = dx
    truth[:, 1] = dy
    return truth


def _fit(cells: np.ndarray, truth: np.ndarray,
         tiles_yx: tuple[int, int] = TILES_YX) -> np.ndarray:
    codes = plane_field.tile_codes(cells, tiles_yx, TILE_CELLS)
    gradient, residual = _linear_evidence(cells, truth)
    equations = plane_field.accumulate(codes, gradient, residual, tiles_yx)
    delta, _support = plane_field.solve(equations)
    return delta


def test_a_uniform_displacement_comes_back_as_that_displacement():
    cells = _cells()
    delta = _fit(cells, _uniform_truth(cells, 0.6, -0.4))
    interior = delta[1:-1, 1:-1]
    assert np.allclose(interior[..., 0], 0.6, atol=0.05), interior[..., 0]
    assert np.allclose(interior[..., 1], -0.4, atol=0.05), interior[..., 1]


def test_a_ramp_comes_back_as_a_ramp_that_keeps_its_order():
    cells = _cells()
    truth = np.zeros((cells.shape[0], 2), np.float64)
    truth[:, 0] = cells[:, 0] / (TILES_YX[0] * TILE_CELLS) * 1.2 - 0.6
    delta = _fit(cells, truth)
    rows = delta[..., 0].mean(axis=1)
    assert np.all(np.diff(rows) > 0.0), rows
    assert rows[0] < -0.2 and rows[-1] > 0.2, rows


def test_a_tile_out_of_the_kernel_s_reach_returns_exactly_zero():
    far = (16, 5)
    cells = _cells(far)
    near = cells[cells[:, 0] < TILE_CELLS]
    delta = _fit(near, _uniform_truth(near, 1.0, 1.0), far)
    assert np.all(delta[-1] == 0.0), delta[-1]
    assert np.all(np.abs(delta[0]) > 0.1), delta[0]


def _one_tile(information: float, truth_dx: float) -> object:
    a = np.zeros((1, 1, 2, 2), np.float64)
    a[0, 0] = np.eye(2) * information
    b = np.zeros((1, 1, 2), np.float64)
    b[0, 0, 0] = information * truth_dx
    return plane_field.NormalEquations(a=a, b=b, mass=np.ones((1, 1)),
                                       total_square=1.0)


def test_the_ridge_shrinks_weak_evidence_toward_zero_and_never_past_it():
    weak = plane_field.solve(_one_tile(0.25, 1.0), passes=0)[0]
    strong = plane_field.solve(_one_tile(400.0, 1.0), passes=0)[0]
    assert weak[0, 0, 0] == pytest.approx(0.25 / 1.25)
    assert weak[0, 0, 1] == 0.0
    assert strong[0, 0, 0] == pytest.approx(400.0 / 401.0, abs=1e-3)
    assert 0.0 < weak[0, 0, 0] < strong[0, 0, 0] < 1.0


def test_twicing_buys_back_the_amplitude_the_shrinkage_took():
    once = plane_field.solve(_one_tile(0.25, 1.0), passes=1)[0]
    assert once[0, 0, 0] == pytest.approx(0.36)
    assert once[0, 0, 0] > 0.25 / 1.25


def test_a_per_tile_brightness_offset_cannot_move_the_delta():
    cells = _cells()
    codes = plane_field.tile_codes(cells, TILES_YX, TILE_CELLS)
    truth = _uniform_truth(cells, 0.5, 0.25)
    gradient, residual = _linear_evidence(cells, truth)
    banded = residual + 0.37 * (codes % 3).astype(np.float64)
    plain = plane_field.solve(
        plane_field.accumulate(codes, gradient, residual, TILES_YX))[0]
    lifted = plane_field.solve(
        plane_field.accumulate(codes, gradient, banded, TILES_YX))[0]
    assert np.allclose(plain, lifted, rtol=0.0, atol=1e-9)


def test_the_fit_is_bit_identical_for_identical_inputs():
    cells = _cells()
    truth = _uniform_truth(cells, 0.44, -0.19)
    first = _fit(cells, truth)
    second = _fit(cells, truth)
    assert first.tobytes() == second.tobytes()


def test_the_residual_reports_what_the_fit_explained():
    cells = _cells()
    codes = plane_field.tile_codes(cells, TILES_YX, TILE_CELLS)
    truth = _uniform_truth(cells, 0.8, 0.0)
    gradient, residual = _linear_evidence(cells, truth)
    equations = plane_field.accumulate(codes, gradient, residual, TILES_YX)
    delta, _support = plane_field.solve(equations)
    assert plane_field.fit_residual(equations, delta) < 0.2
    assert plane_field.fit_residual(equations, np.zeros_like(delta)) == 1.0


def test_a_delta_is_clamped_to_the_declared_maximum():
    delta = np.zeros((2, 2, 2), np.float64)
    delta[0, 0] = (9.0, 12.0)
    delta[1, 1] = (0.3, -0.4)
    clamped = plane_field.clamp(delta, 2.0)
    assert np.hypot(*clamped[0, 0]) == pytest.approx(2.0)
    assert np.allclose(clamped[1, 1], (0.3, -0.4))


def test_lookup_is_bilinear_between_tile_centres_and_clamps_at_the_edge():
    delta = np.zeros((3, 3, 2), np.float64)
    delta[..., 0] = np.asarray([[0.0, 0.0, 0.0], [1.0, 1.0, 1.0],
                                [2.0, 2.0, 2.0]])
    centre = plane_field.evaluate(
        delta, np.asarray([[TILE_CELLS + TILE_CELLS // 2, 0]]), TILE_CELLS)
    between = plane_field.evaluate(
        delta, np.asarray([[TILE_CELLS, 0]]), TILE_CELLS)
    beyond = plane_field.evaluate(
        delta, np.asarray([[10 * TILE_CELLS, 0]]), TILE_CELLS)
    assert centre[0, 0] == pytest.approx(1.0)
    assert between[0, 0] == pytest.approx(0.5)
    assert beyond[0, 0] == pytest.approx(2.0)


def test_the_median_magnitude_counts_only_tiles_with_evidence():
    delta = np.zeros((2, 2, 2), np.float64)
    delta[..., 0] = 0.8
    support = np.asarray([[1.0, 0.0], [0.0, 0.0]])
    assert plane_field.median_magnitude_dots(delta, support) == \
        pytest.approx(0.8)
    assert plane_field.median_magnitude_dots(
        delta, np.zeros((2, 2))) == 0.0


# --------------------------------------------------------------------
# the evidence tiers, and the attribution law
# --------------------------------------------------------------------

def _known_cells(n: int = 240) -> tuple[np.ndarray, np.ndarray]:
    """Kinds and page cells for a mixed population of known cells."""
    rng = np.random.default_rng(11)
    cells = np.stack((rng.integers(0, 64, n), rng.integers(0, 64, n)),
                     axis=1).astype(np.int64)
    kinds = np.full(n, field_tiers.KIND_PAYLOAD, np.int64)
    kinds[: n // 3] = field_tiers.KIND_WORD
    kinds[n // 3: 2 * (n // 3)] = field_tiers.KIND_DUST
    return kinds, cells


def test_the_three_tiers_partition_the_known_cells_exactly():
    kinds, cells = _known_cells()
    known = np.ones(kinds.size, bool)
    known[:5] = False
    partition = field_tiers.partition_sites(kinds, known, cells)
    field_tiers.assert_partition(partition, known)
    counts = partition.counts
    assert sum(counts.values()) == int(known.sum())


def test_a_site_that_reaches_two_tiers_is_refused_loudly():
    kinds, cells = _known_cells(60)
    known = np.ones(kinds.size, bool)
    partition = field_tiers.partition_sites(kinds, known, cells)
    broken = dataclasses.replace(
        partition,
        blind=np.concatenate((partition.blind, partition.anchor[:1])))
    with pytest.raises(ValueError, match="attribution law"):
        field_tiers.assert_partition(broken, known)


def test_the_furniture_halves_both_carry_word_and_dust():
    """Splitting by KIND would starve Y, because no word site carries it."""
    kinds, cells = _known_cells(600)
    known = np.ones(kinds.size, bool)
    partition = field_tiers.partition_sites(kinds, known, cells)
    for half in (partition.anchor, partition.blind):
        assert np.any(kinds[half] == field_tiers.KIND_WORD)
        assert np.any(kinds[half] == field_tiers.KIND_DUST)
    assert not np.any(kinds[partition.photometric] >= 0)


def test_a_rank_two_observation_comes_back_as_that_observation():
    codes = np.zeros(4, np.int64)
    delta = np.tile(np.asarray([[0.7, -0.3]]), (4, 1))
    equations = plane_field.observe(codes, delta, np.full(4, 25.0), (1, 1))
    fitted, _support = plane_field.solve(equations, bandwidth_tiles=1e-6,
                                         passes=0)
    assert fitted[0, 0, 0] == pytest.approx(0.7, abs=0.02)
    assert fitted[0, 0, 1] == pytest.approx(-0.3, abs=0.02)


def test_an_observation_tier_is_not_tile_centred():
    """Centring would subtract the very quantity an anchor measures."""
    codes = np.zeros(6, np.int64)
    delta = np.tile(np.asarray([[0.5, 0.0]]), (6, 1))
    observed = plane_field.observe(codes, delta, np.full(6, 40.0), (1, 1))
    assert observed.b[0, 0, 0] > 0.0
    gradient = np.tile(np.asarray([[1.0, 0.0]]), (6, 1))
    centred = plane_field.accumulate(codes, gradient,
                                     np.full(6, 0.5), (1, 1))
    assert centred.b[0, 0, 0] == pytest.approx(0.0)


def test_two_tiers_equations_add_to_the_joint_fit():
    codes = np.zeros(3, np.int64)
    left = plane_field.observe(codes, np.tile([[1.0, 0.0]], (3, 1)),
                               np.full(3, 2.0), (1, 1))
    right = plane_field.observe(codes, np.tile([[0.0, 1.0]], (3, 1)),
                                np.full(3, 6.0), (1, 1))
    both = plane_field.observe(
        np.zeros(6, np.int64),
        np.concatenate((np.tile([[1.0, 0.0]], (3, 1)),
                        np.tile([[0.0, 1.0]], (3, 1)))),
        np.concatenate((np.full(3, 2.0), np.full(3, 6.0))), (1, 1))
    joint = plane_field.combine(left, right)
    assert np.allclose(joint.a, both.a)
    assert np.allclose(joint.b, both.b)
    assert joint.total_square == pytest.approx(both.total_square)


def test_leaving_a_tier_out_is_the_same_as_never_adding_it():
    codes = np.zeros(4, np.int64)
    tiers = {
        field_tiers.TIER_ANCHOR: plane_field.observe(
            codes, np.tile([[1.0, 0.0]], (4, 1)), np.full(4, 10.0), (1, 1)),
        field_tiers.TIER_BLIND: plane_field.observe(
            codes, np.tile([[0.0, 0.5]], (4, 1)), np.full(4, 10.0), (1, 1)),
    }

    def solve(equations):
        return plane_field.solve(equations, bandwidth_tiles=1e-6, passes=0)

    report = field_tiers.leave_one_out(tiers, solve)
    assert set(report) == set(tiers)
    without_anchor, _ = solve(tiers[field_tiers.TIER_BLIND])
    joint, _ = solve(plane_field.combine(*tiers.values()))
    expected = float(np.median(np.hypot(
        joint[..., 0] - without_anchor[..., 0],
        joint[..., 1] - without_anchor[..., 1])))
    assert report[field_tiers.TIER_ANCHOR]["median_effect_dots"] == \
        pytest.approx(expected)
    assert report[field_tiers.TIER_ANCHOR]["sites"] == 4


def test_per_tier_accounting_sums_to_the_joint_fit_s_own_mass():
    codes = np.zeros(4, np.int64)
    tiers = {
        field_tiers.TIER_ANCHOR: plane_field.observe(
            codes, np.tile([[1.0, 0.0]], (4, 1)), np.full(4, 3.0), (1, 1)),
        field_tiers.TIER_BLIND: plane_field.observe(
            codes[:2], np.tile([[0.0, 1.0]], (2, 1)), np.full(2, 5.0),
            (1, 1)),
    }
    joint = plane_field.combine(*tiers.values())
    assert float(joint.mass.sum()) == sum(
        float(tier.mass.sum()) for tier in tiers.values())
    assert float(joint.a[..., 0, 0].sum()) == pytest.approx(
        sum(float(tier.a[..., 0, 0].sum()) for tier in tiers.values()))


def _synthetic_sampler(true_delta_dots_xy, bits: np.ndarray):
    """A plane whose value at a site is 1 - bit, displaced by a truth."""
    truth = np.asarray(true_delta_dots_xy, np.float64)

    def sample(offsets: np.ndarray) -> np.ndarray:
        grid = np.atleast_2d(np.asarray(offsets, np.float64))
        error = np.hypot(grid[:, 0] - truth[0], grid[:, 1] - truth[1])
        blend = np.clip(1.0 - error / 1.5, 0.0, 1.0)[:, None]
        centre = float(np.mean(1.0 - bits))
        return centre + blend * ((1.0 - bits)[None, :] - centre)

    return sample


def test_the_anchor_kernel_returns_the_displacement_it_was_shown():
    bits = np.asarray([0, 1] * 32, np.float64)
    weights = np.ones(bits.size)
    for truth in ((0.5, 0.0), (-0.75, 0.25), (0.0, 0.0)):
        measured = field_tiers.anchor_offsets(
            _synthetic_sampler(truth, bits), bits, weights, 1.5)
        assert measured is not None
        assert measured[0][0] == pytest.approx(truth[0], abs=0.13)
        assert measured[0][1] == pytest.approx(truth[1], abs=0.13)


def test_the_anchor_kernel_refuses_a_template_with_one_polarity():
    """The Y word lattice, exactly: every site blank, nothing to lock on."""
    bits = np.zeros(64, np.float64)
    assert field_tiers.anchor_offsets(
        _synthetic_sampler((0.5, 0.0), bits), bits,
        np.ones(bits.size), 1.5) is None


def test_the_anchor_kernel_refuses_a_template_with_too_few_sites():
    bits = np.asarray([0, 1] * 4, np.float64)
    assert field_tiers.anchor_offsets(
        _synthetic_sampler((0.5, 0.0), bits), bits,
        np.ones(bits.size), 1.5) is None


def test_a_measurement_at_the_wall_is_reported_as_saturated():
    assert field_tiers.saturated(np.asarray([1.4, 0.0]), 1.5) is True
    assert field_tiers.saturated(np.asarray([0.4, 0.2]), 1.5) is False


def test_the_anchor_tier_declines_when_it_cannot_check_its_own_gain():
    tiles = (4, 4)
    codes = np.arange(16, dtype=np.int64)
    anchor_tier = plane_field.observe(
        codes, np.tile([[0.5, 0.0]], (16, 1)), np.ones(16), tiles)
    thin = plane_field.observe(
        codes[:3], np.tile([[0.5, 0.0]], (3, 1)), np.ones(3), tiles)
    check = field_tiers.gain_check({field_tiers.TIER_ANCHOR: anchor_tier,
                                    field_tiers.TIER_PHOTOMETRIC: thin})
    assert check["refused"] is True and check["overlap_tiles"] == 3
    assert "declines" in check["reason"]
    wide = plane_field.observe(
        codes, np.tile([[0.5, 0.0]], (16, 1)), np.ones(16), tiles)
    assert field_tiers.gain_check(
        {field_tiers.TIER_ANCHOR: anchor_tier,
         field_tiers.TIER_PHOTOMETRIC: wide})["refused"] is False


def test_the_anchor_tier_declines_a_page_with_no_photometric_evidence():
    tiles = (2, 2)
    anchor_tier = plane_field.observe(
        np.arange(4, dtype=np.int64), np.tile([[0.5, 0.0]], (4, 1)),
        np.ones(4), tiles)
    check = field_tiers.gain_check({field_tiers.TIER_ANCHOR: anchor_tier})
    assert check["refused"] is True
    assert "no photometric evidence" in check["reason"]


def test_the_blind_estimator_picks_the_offset_that_reads_best():
    rng = np.random.default_rng(5)
    labels = rng.integers(0, 2, 200).astype(np.uint8)
    split = field_tiers.split_key(
        np.stack((np.arange(200), np.arange(200) * 3), axis=1))
    truth = 0.5

    def sample(offset: np.ndarray) -> np.ndarray:
        error = abs(float(np.asarray(offset).ravel()[0]) - truth)
        clarity = max(0.0, 1.0 - error)
        return (1.0 - labels) * clarity + rng.normal(0.0, 0.05, labels.size)

    measured = field_tiers.blind_offset(sample, labels, split, 1.5)
    assert measured is not None
    assert measured[0][0] == pytest.approx(truth, abs=0.26)
    assert measured[1] > 0.0


def test_a_blind_observation_is_not_judged_by_an_ncc_quality_floor():
    """The two tiers' weights are different quantities.

    An anchor's weight is a correlation coefficient (0.5-1.0, floored at
    0.10); a blind offset's is a held-out log-loss improvement spread
    over a window's tiles, orders of magnitude smaller.  Routing the
    second through the first's floor silently discarded every blind
    observation ever made -- 163 real offsets on the displaced sim, none
    of which reached the fit.
    """
    observations = tuple(
        field_tiers.AnchorObservation(
            tile_code=code, delta_dots_xy=np.asarray([0.4, 0.0]),
            quality=0.002, n_sites=56, saturated=False)
        for code in range(4))
    blind = field_tiers.blind_equations(observations, (2, 2))
    assert float(blind.mass.sum()) == 4.0, "the blind tier dropped them"
    through_anchor = field_tiers.anchor_equations(observations, (2, 2))
    assert float(through_anchor.mass.sum()) == 0.0, (
        "the anchor floor is supposed to reject a 0.002 correlation")


def test_each_tier_reaches_the_solve_through_its_own_floor():
    """The PLUMBING, not just the function.

    `blind_equations` having the right floor is not enough: `fit_page`
    builds its equations through `relative_equations`, and an earlier
    version inferred the floor from the gain instead of being handed it.
    That inference survived a merge while the branch it relied on did
    not, and the blind tier went silently unweighted a second time.  This
    pins the path the fit actually takes.
    """
    observations = tuple(
        field_tiers.AnchorObservation(
            tile_code=code, delta_dots_xy=np.asarray([0.4, 0.0]),
            quality=0.002, n_sites=56, saturated=False)
        for code in range(4))
    as_blind = fields.relative_equations(
        observations, None, (2, 2), 1.0, field_tiers.BLIND_MIN_WEIGHT)
    as_anchor = fields.relative_equations(
        observations, None, (2, 2), field_tiers.ANCHOR_GAIN,
        field_tiers.ANCHOR_MIN_QUALITY)
    assert float(as_blind.mass.sum()) == 4.0, (
        "a log-loss weight was judged by the anchor's correlation floor")
    assert float(as_anchor.mass.sum()) == 0.0


def test_the_blind_estimator_declines_when_nothing_beats_the_centre():
    labels = np.random.default_rng(9).integers(0, 2, 200).astype(np.uint8)
    split = field_tiers.split_key(
        np.stack((np.arange(200), np.arange(200) * 3), axis=1))

    def flat(offset: np.ndarray) -> np.ndarray:
        return (1.0 - labels).astype(np.float64)

    measured = field_tiers.blind_offset(flat, labels, split, 1.0)
    assert measured is not None
    assert measured[0].tolist() == [0.0, 0.0] and measured[1] == 0.0



def test_the_common_part_comes_out_as_a_median_not_a_mean_of_others():
    """The publication form, pinned on the case that separates them.

    Truth (0, 0, D): the mean of the other two planes returns
    (-D/2, -D/2, D) and redistributes Y's displacement onto C and M --
    measured on the displaced sim at C/M 0.45-0.56 against Y 1.117.  The
    median returns (0, 0, D).  Both must still cancel a common bias.
    """
    shape = (2, 2, 2)
    displaced = [np.zeros(shape), np.zeros(shape), np.zeros(shape)]
    displaced[2][..., 0] = 1.2
    out = fields.plane_relative(displaced)
    assert np.allclose(out[0], 0.0), out[0]
    assert np.allclose(out[1], 0.0), out[1]
    assert np.allclose(out[2][..., 0], 1.2), out[2]

    biased = [np.full(shape, 0.4) for _ in range(3)]
    for field in fields.plane_relative(biased):
        assert np.allclose(field, 0.0)


def test_a_page_without_all_three_planes_publishes_nothing_relative():
    shape = (2, 2, 2)
    out = fields.plane_relative([np.zeros(shape), None, np.zeros(shape)])
    assert out[1] is None
    assert out[0] is not None


def test_the_order_is_subtract_then_clamp():
    """`settle` takes the common part out BEFORE the clamp.

    With a common bias big enough to clip, clamping first would clip
    each plane by a different amount and leave a residue the subtraction
    can no longer remove; subtracting first leaves the clamp acting on
    exactly what gets written.
    """
    shape = (1, 1, 2)
    big = plane_field.MAX_DELTA_DOTS * 1.5
    fits = [np.zeros(shape), np.zeros(shape), np.zeros(shape)]
    for field in fits:
        field[..., 0] = big
    fits[2][..., 0] = big + 0.5
    settled = fields.settle(fits)
    # the common part is gone, so nothing is near the ceiling any more
    assert np.allclose(settled[0][..., 0], 0.0)
    assert np.allclose(settled[1][..., 0], 0.0)
    assert settled[2][0, 0, 0] == pytest.approx(0.5)
    # clamp-first would have clipped all three to the ceiling and left
    # a per-plane residue of zero
    clipped = [plane_field.clamp(field) for field in fits]
    assert np.allclose(
        [f[0, 0, 0] for f in fields.plane_relative(clipped)], 0.0)


def _field(**kwargs: object) -> data.PlaneField:
    return _h3_facts.plane_field(**kwargs)


def test_a_better_fit_adopts_and_a_worse_one_is_a_no_op():
    store = _engine(True)
    first = _field(n_certificates=10, residual=0.6)
    changed, keys, _kind = store._fold(first)
    assert changed and keys == ((KEY_PLANE_FIELD, _h3_facts.CAPTURE_ID, 0,
                                0, 2),)
    weaker, _keys, _kind = store._fold(
        _field(n_certificates=9, residual=0.1))
    assert weaker is False
    scruffier, _keys, _kind = store._fold(
        _field(n_certificates=10, residual=0.9))
    assert scruffier is False
    assert store._plane_fields[
        (_h3_facts.CAPTURE_ID, 0, 0, 2)] is first
    better, keys, _kind = store._fold(
        _field(n_certificates=10, residual=0.5))
    assert better and keys
    best, _keys, _kind = store._fold(
        _field(n_certificates=11, residual=0.95))
    assert best is True


def test_the_ordinal_is_certificates_then_the_smaller_residual():
    assert data.plane_field_ordinal(
        _field(n_certificates=4, residual=0.5)) == (4, -0.5)
    assert (data.plane_field_ordinal(_field(n_certificates=5,
                                            residual=0.9))
            > data.plane_field_ordinal(_field(n_certificates=4,
                                              residual=0.1)))


def test_the_accessor_is_shut_while_the_dial_is_off():
    off = _engine(False)
    off._fold(_field())
    key = (_h3_facts.CAPTURE_ID, 0, 0, 2)
    assert off._plane_fields[key] is not None
    assert off.plane_field(key) is None
    assert off.lane_plane_fields(_h3_facts.CAPTURE_ID, 0, 0) == (None,
                                                                 None, None)
    assert off.plane_fields_enabled() is False


def test_the_accessor_serves_the_standing_cell_while_the_dial_is_on():
    on = _engine(True)
    on._fold(_field())
    key = (_h3_facts.CAPTURE_ID, 0, 0, 2)
    assert on.plane_field(key) is not None
    served = on.lane_plane_fields(_h3_facts.CAPTURE_ID, 0, 0)
    assert served[0] is None and served[1] is None
    assert served[2] is on.plane_field(key)
    assert on.plane_fields_enabled() is True


def test_no_field_worker_is_ever_born_while_the_dial_is_off():
    off = _engine(False)
    assert fields._fields_subjects(off, _h3_facts.certificate()) == ()
    on = _engine(True)
    assert fields._fields_subjects(on, _h3_facts.certificate()) == ()


def test_a_colour_lane_on_the_page_is_the_subject_a_certificate_births():
    on = _engine(True)
    on._lanes_on_page[0] = {("cap-b", 1), ("cap-a", 0)}
    on.row = dataclasses.replace(on.row, family=fields.Family.CMY8)
    assert fields._fields_subjects(on, _h3_facts.certificate()) == (
        ("cap-a", 0, 0), ("cap-b", 1, 0))
    on.row = dataclasses.replace(on.row, family=fields.Family.K)
    assert fields._fields_subjects(on, _h3_facts.certificate()) == ()


def test_the_row_subscribes_to_its_page_and_its_lane_poses():
    on = _engine(True)
    keys = fields._fields_reads(on, ("cap", 0, 3))
    assert keys == (("page_certs", 3), ("lane_poses", "cap", 0, 3))


def test_the_row_prices_its_own_re_fits_by_fire_ordinal():
    on = _engine(True)
    prices = [fields._fields_cost(on, ("cap", 0, 0), fields.STAGE_FIELDS,
                                  attempt, 0)
              for attempt in (1, 2, 3)]
    assert prices == [180, 360, 540]
    assert fields._fields_cost(on, ("cap", 2, 0), fields.STAGE_FIELDS,
                               1, 0) == 184


def test_a_field_is_published_only_when_it_has_something_to_say():
    strong = plane_field.FieldFit(
        delta_dots_xy=np.zeros((2, 2, 2)), support=np.ones((2, 2)),
        residual=0.7, median_delta_dots=0.4, n_sites=1000)
    assert fields.publishable(strong) is True
    assert fields.publishable(
        dataclasses.replace(strong, median_delta_dots=0.05)) is False
    assert fields.publishable(
        dataclasses.replace(strong, n_sites=8)) is False
    assert fields.publishable(
        dataclasses.replace(strong, residual=1.0)) is False


def test_the_level_table_is_a_median_per_state_and_skips_thin_states():
    states = np.concatenate((np.zeros(40, np.int64),
                             np.full(40, 5, np.int64),
                             np.full(3, 7, np.int64)))
    values = np.zeros((states.size, 3), np.float64)
    values[states == 0] = 0.9
    values[states == 5] = 0.2
    values[states == 7] = 0.5
    levels, live = fields.state_levels(states, values)
    assert live.tolist() == [True, False, False, False, False, True,
                             False, False]
    assert levels[0].tolist() == [0.9, 0.9, 0.9]
    assert levels[5].tolist() == [0.2, 0.2, 0.2]
    assert levels[7].tolist() == [0.0, 0.0, 0.0]


def _ramp_site(cell_dots: int, px_per_dot: int,
               ) -> tuple[fields.WindowSites, np.ndarray]:
    """A window on a raster that is exactly linear in x.

    A linear raster has one gradient and it is known in closed form, so
    whatever `measure_window` returns names its own denominator: the
    same number read per DOT and per CELL differs by exactly cell_dots.
    """
    pitch_px = float(cell_dots * px_per_dot)
    cells = np.stack(np.meshgrid(np.arange(4), np.arange(4),
                                 indexing="ij"), axis=-1).reshape(-1, 2)
    points = (cells.astype(np.float64) + 0.5) * pitch_px + 8.0
    n = cells.shape[0]
    site = fields.WindowSites(
        page_cells_yx=cells.astype(np.int64),
        states=np.zeros(n, np.int64),
        scan_points_yx=points,
        pose_linear=np.asarray(((pitch_px, 0.0), (0.0, pitch_px))),
        window=None,
        known_bits=np.zeros((n, 3), np.uint8),
        # these cases pin the PHOTOMETRIC measurement, so every cell is
        # that tier's; the other two tiers are exercised on their own
        # sites below.
        partition=field_tiers.SitePartition(
            photometric=np.arange(n, dtype=np.int64),
            anchor=np.zeros(0, np.int64), blind=np.zeros(0, np.int64)))
    width = int(np.ceil(points[:, 1].max())) + 16
    height = int(np.ceil(points[:, 0].max())) + 16
    ramp = (np.arange(width, dtype=np.float64)[None, :] * RAMP_SLOPE_PER_PX
            + np.zeros((height, 1)))
    return site, np.repeat(ramp[..., None], 3, axis=2).astype(np.float32)


RAMP_SLOPE_PER_PX = 0.01


@pytest.mark.parametrize("cell_dots,px_per_dot", [(2, 2), (3, 2), (4, 3)])
def test_the_fitter_reads_its_gradient_per_dot_and_not_per_cell(
        cell_dots, px_per_dot):
    """RE-PINNED 2026-08-31 with the plane-field units fix.

    This case used to read `fields._shifted(points, pose, delta)` and
    pin 1.0 -> 6.0 px on a 6 px/cell pose: the fitter put a delta the
    schema calls DOTS through a CELL->pixel matrix without dividing by
    `cell_dots`, so one "dot" moved a whole cell and the fitted field
    was really in cells.  The fitter now shares
    `anchor.shifted_points` with the read side, so the gradient it
    measures — and therefore the delta the solve returns — is per DOT.
    """
    site, filtered = _ramp_site(cell_dots, px_per_dot)
    _centres, gradients = fields.measure_window(
        site, (0, 0, filtered), (None, None, None), cell_dots)
    measured = float(np.median(gradients[:, 0, 0]))
    per_dot = RAMP_SLOPE_PER_PX * px_per_dot
    assert measured == pytest.approx(per_dot, rel=1e-6), (
        f"{measured} is not the slope per dot {per_dot}; per cell would "
        f"be {per_dot * cell_dots}")


def test_the_fitter_and_the_read_side_move_a_point_the_same_way():
    """One delta, one displacement — the two sides cannot drift again.

    `fields` no longer owns a shifting function: it calls the read
    side's `anchor.shifted_points` with the same `/ cell_dots` the
    colour lane and `plane_k` apply, so a field that says one dot moves
    every sampler in the tree by one dot.
    """
    cell_dots, px_per_dot = 3, 2
    site, filtered = _ramp_site(cell_dots, px_per_dot)
    field = np.zeros((1, 1, 2), np.float64)
    field[0, 0, 0] = 1.0
    centres, _gradients = fields.measure_window(
        site, (0, 0, filtered), (None, None, field), cell_dots)
    lane = anchor.shifted_points(
        site.scan_points_yx, site.pose_linear,
        np.tile((1.0, 0.0), (site.scan_points_yx.shape[0], 1)) / cell_dots)
    expected = anchor.sample_rgb(filtered, 0, 0, lane)[:, 2]
    assert np.allclose(centres[:, 2], expected)
    # and one dot really is one dot: px_per_dot pixels of the ramp
    plain = anchor.sample_rgb(filtered, 0, 0, site.scan_points_yx)[:, 2]
    assert np.allclose(centres[:, 2] - plain,
                       RAMP_SLOPE_PER_PX * px_per_dot)


def test_the_read_side_offers_nothing_when_no_plane_has_a_field():
    cells = _cells()
    assert color_region.field_offsets(None, cells) is None
    assert color_region.field_offsets((None, None, None), cells) is None


def test_the_read_side_serves_dots_per_cell_for_the_planes_that_have_one():
    cells = _cells((2, 2))
    field = _field(plane=2, delta_dots=0.75, tiles_yx=(2, 2))
    offsets = color_region.field_offsets((None, None, field), cells)
    assert offsets[0] is None and offsets[1] is None
    assert offsets[2].shape == (cells.shape[0], 2)
    assert np.allclose(offsets[2][:, 0], 0.75)
    assert np.allclose(offsets[2][:, 1], 0.0)


def test_an_explicit_override_still_wins_over_the_standing_field():
    cells = _cells((2, 2))
    rows = data.WindowRows(
        patch_ordinal=7, window_id=("cap", 0, 0, (0, 0, 8, 8)), page=0,
        local_cells_yx=cells, page_cells_yx=cells,
        scan_points_yx=cells.astype(np.float64),
        states=np.zeros(cells.shape[0], np.int8),
        furniture_kind=np.zeros(cells.shape[0], np.int8),
        known_component_bits=np.zeros((cells.shape[0], 3), np.uint8),
        known_component_mask=np.ones((cells.shape[0], 3), bool),
        heldout_logloss=None)
    explicit = (None, None, np.zeros((cells.shape[0], 2)))
    field = _field(plane=2, delta_dots=0.75, tiles_yx=(2, 2))
    served = color_region.row_offsets({7: explicit}, (None, None, field),
                                      rows)
    assert served is explicit
    served = color_region.row_offsets(None, (None, None, field), rows)
    assert np.allclose(served[2][:, 0], 0.75)


def test_the_engine_carries_the_row_and_only_it_writes_the_family():
    names = tuple(descriptor.name for descriptor in engine.DESCRIPTORS)
    assert "fields" in names
    writers = tuple(descriptor.name for descriptor in engine.DESCRIPTORS
                    if data.PlaneField in descriptor.produces)
    _h3_support.assert_golden("PlaneField writers", writers, ("fields",))
