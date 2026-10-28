"""W1 field-core unit tests (docs/PLANE-FIELDS.md §3, §3c, §6.2 W1).

Every bound here is a pre-registered number on seeded synthetic data:
the sinusoid case is the measured AltaLink Y-registration signal
(0.8 dot peak, ~100 mm = 18.5 tiles at c2) at a plausible probe scatter,
and the shrinkage cases are the 2026-08-22 law (INDEPENDENT-PLANES §6
P1): each plane's posterior is INDEPENDENT and shrinks toward the
natural zero, so thin evidence decays to zero and declares a large
uncertainty rather than borrowing another plane's field.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from holo.format.layout import TILE_CELLS
from holo.receive.plane_fields import (
    FieldEvidence,
    PlaneDeltaField,
    SOURCE_CERTIFIED,
    SOURCE_DUST,
    SOURCE_PROBE,
    SOURCE_WORD,
)

SINUSOID_PERIOD_TILES = 18.5
SINUSOID_AMPLITUDE_DOTS = 0.8


def _sinusoid_dots(tile_x: float) -> float:
    return SINUSOID_AMPLITUDE_DOTS * math.sin(
        2.0 * math.pi * tile_x / SINUSOID_PERIOD_TILES)


def _scatter_sinusoid(
    n_planes: int,
    tiles_yx: tuple[int, int],
    signal_plane: int,
    *,
    seed: int,
    coverage: float = 0.6,
    sigma_dots: float = 0.3,
) -> list[FieldEvidence]:
    rng = np.random.default_rng(seed)
    evidence: list[FieldEvidence] = []
    for tile_y in range(tiles_yx[0]):
        for tile_x in range(tiles_yx[1]):
            if rng.random() > coverage:
                continue
            truth = _sinusoid_dots(tile_x + 0.5)
            for plane in range(n_planes):
                offset = truth if plane == signal_plane else 0.0
                evidence.append(FieldEvidence(
                    page=0,
                    tile_yx=(tile_y + 0.5, tile_x + 0.5),
                    plane_index=plane,
                    offset_dots_xy=(
                        offset + rng.normal(0.0, sigma_dots),
                        rng.normal(0.0, sigma_dots),
                    ),
                    weight=1.0,
                    source=SOURCE_CERTIFIED,
                ))
    return evidence


def _sinusoid_amplitude_dots(column_profile: np.ndarray) -> float:
    """Amplitude of the signal's own harmonic in a column profile.

    Isolates the field's sinusoid content from smoother noise, which the
    row average alone does not (neighbouring columns share samples).
    """
    tile_x = np.arange(column_profile.size) + 0.5
    basis = np.stack((
        np.sin(2.0 * np.pi * tile_x / SINUSOID_PERIOD_TILES),
        np.cos(2.0 * np.pi * tile_x / SINUSOID_PERIOD_TILES),
        np.ones_like(tile_x),
    ), axis=1)
    coefficients, *_ = np.linalg.lstsq(basis, column_profile, rcond=None)
    return float(math.hypot(coefficients[0], coefficients[1]))


def _delta_grid(
    field: PlaneDeltaField, tiles_yx: tuple[int, int]
) -> np.ndarray:
    grid = np.zeros((field.n_planes, tiles_yx[0], tiles_yx[1], 2))
    for tile_y in range(tiles_yx[0]):
        for tile_x in range(tiles_yx[1]):
            for plane_affine in field.lookup_tile_index(0, tile_y, tile_x):
                grid[plane_affine.plane_index, tile_y, tile_x] = (
                    plane_affine.delta_dots_xy)
    return grid


def test_sinusoid_recovery_leaves_the_silent_planes_flat() -> None:
    tiles_yx = (24, 40)
    field = PlaneDeltaField(3, tiles_yx)
    field.add(_scatter_sinusoid(3, tiles_yx, 2, seed=20260820))
    field.solve()

    grid = _delta_grid(field, tiles_yx)
    truth = np.array([
        _sinusoid_dots(tile_x + 0.5) for tile_x in range(tiles_yx[1])
    ])
    error = grid[2, :, :, 0] - truth[None, :]
    assert math.sqrt(float((error ** 2).mean())) < 0.15
    # the signal plane's orthogonal component carries no signal either
    assert math.sqrt(float((grid[2, :, :, 1] ** 2).mean())) < 0.15

    for plane in (0, 1):
        for axis in (0, 1):
            assert math.sqrt(
                float((grid[plane, :, :, axis] ** 2).mean())) < 0.10
        # and next to no sinusoid bleeds through the pooled common field
        assert _sinusoid_amplitude_dots(
            grid[plane, :, :, 0].mean(axis=0)) < 0.08

    # the smoother keeps ~90% of a 18.5-tile signal at a 2-tile bandwidth
    assert 0.65 < _sinusoid_amplitude_dots(
        grid[2, :, :, 0].mean(axis=0)) < 0.85


def test_single_plane_k_instance_recovers_the_same_field() -> None:
    tiles_yx = (24, 40)
    field = PlaneDeltaField(1, tiles_yx)
    field.add(_scatter_sinusoid(1, tiles_yx, 0, seed=20260820))
    field.solve()

    grid = _delta_grid(field, tiles_yx)
    truth = np.array([
        _sinusoid_dots(tile_x + 0.5) for tile_x in range(tiles_yx[1])
    ])
    error = grid[0, :, :, 0] - truth[None, :]
    assert math.sqrt(float((error ** 2).mean())) < 0.15
    stats = field.stats()
    assert stats.n_planes == 1
    assert stats.coverage_fraction == (1.0,)


def _ramp_dots(tile_x: float) -> float:
    return -0.4 + 0.05 * tile_x


def _ramp_evidence(
    tiles_yx: tuple[int, int],
    *,
    seed: int,
    planes: tuple[int, ...],
) -> list[FieldEvidence]:
    rng = np.random.default_rng(seed)
    evidence: list[FieldEvidence] = []
    for tile_y in range(tiles_yx[0]):
        for tile_x in range(tiles_yx[1]):
            for plane in planes:
                evidence.append(FieldEvidence(
                    page=0,
                    tile_yx=(tile_y + 0.5, tile_x + 0.5),
                    plane_index=plane,
                    offset_dots_xy=(
                        _ramp_dots(tile_x + 0.5) + rng.normal(0.0, 0.05),
                        0.0,
                    ),
                    weight=1.0,
                    source=SOURCE_WORD,
                ))
    return evidence


NOISY_SAMPLES = (
    ((4, 4), 2.5),
    ((8, 9), -2.0),
    ((12, 13), 2.2),
)


def _sparse_noisy_plane_field(**kwargs: float) -> PlaneDeltaField:
    tiles_yx = (16, 16)
    field = PlaneDeltaField(3, tiles_yx, **kwargs)
    field.add(_ramp_evidence(tiles_yx, seed=99, planes=(0, 1)))
    field.add([
        FieldEvidence(
            page=0,
            tile_yx=(tile[0] + 0.5, tile[1] + 0.5),
            plane_index=2,
            offset_dots_xy=(_ramp_dots(tile[1] + 0.5) + error, 0.0),
            # sparse AND noisy: a low-confidence observation declares it
            weight=0.1,
            source=SOURCE_DUST,
        )
        for tile, error in NOISY_SAMPLES
    ])
    field.solve()
    return field


def test_thin_evidence_decays_to_zero_and_declares_its_doubt() -> None:
    """The 2026-08-22 law: the shrinkage target is the NATURAL ZERO.

    Was ``test_thin_evidence_collapses_onto_the_common_field``, which
    pinned the retired cross-plane law: plane 2's three noisy samples
    used to be pulled onto the RAMP that planes 0 and 1 agree on, and
    the plane read that ramp exactly where it had no samples of its own.
    Borrowing another plane's field is the bug (§6.5.4b) -- planes are
    different by construction -- so the assertions move to what the new
    law owes: away from its own evidence the plane is zero, and where its
    evidence is thin the posterior says so out loud instead of quietly
    answering with someone else's number.
    """
    field = _sparse_noisy_plane_field()
    free = _sparse_noisy_plane_field(plane_sigma_dots=50.0)

    shrunk = []
    unshrunk = []
    for tile, error in NOISY_SAMPLES:
        thin = field.lookup_tile_index(0, tile[0], tile[1])[2]
        loose = free.lookup_tile_index(0, tile[0], tile[1])[2]
        shrunk.append(thin)
        unshrunk.append(loose)
        # the ridge pulls a weight-0.1 sample well inside its own error
        assert abs(thin.delta_dots_xy[0]) < abs(error) * 0.75
        # and it is not mistaken for knowledge: the sd dwarfs the gate
        assert thin.uncertainty_dots > 0.5
        # the same evidence with no ridge keeps nearly all of its noise
        assert abs(loose.delta_dots_xy[0]) > abs(error) * 0.9

    dense = field.lookup_tile_index(0, 8, 8)[0]
    assert dense.uncertainty_dots < 0.1 * min(
        row.uncertainty_dots for row in shrunk)

    # far from its three samples the plane is the NATURAL ZERO -- not
    # the ramp the other two planes carry right there
    far = field.lookup_tile_index(0, 15, 0)[2]
    assert abs(far.delta_dots_xy[0]) < 0.05
    assert abs(_ramp_dots(0.5)) > 0.3          # the ramp really is there
    assert abs(
        field.lookup_tile_index(0, 15, 0)[0].delta_dots_xy[0]
        - _ramp_dots(0.5)) < 0.15


def test_an_uncovered_plane_is_zero_not_another_plane_s_field() -> None:
    """One plane's evidence never becomes another plane's answer."""
    tiles_yx = (16, 16)
    field = PlaneDeltaField(3, tiles_yx)
    field.add(_ramp_evidence(tiles_yx, seed=4, planes=(1,)))
    field.solve()

    stats = field.stats()
    assert stats.samples_by_plane == (0, tiles_yx[0] * tiles_yx[1], 0)
    for tile_y, tile_x in ((8, 8), (0, 0), (15, 15)):
        evidenced, *silent = (
            field.lookup_tile_index(0, tile_y, tile_x)[plane]
            for plane in (1, 0, 2))
        assert evidenced.covered
        assert evidenced.delta_dots_xy[0] == pytest.approx(
            _ramp_dots(tile_x + 0.5), abs=0.1)
        for affine in silent:
            assert not affine.covered
            assert affine.delta_dots_xy == (0.0, 0.0)
            assert affine.jacobian_dots_per_cell == ((0.0, 0.0), (0.0, 0.0))
            assert affine.uncertainty_dots == pytest.approx(
                math.sqrt(field.prior_variance))
    assert stats.rms_dots[0] == 0.0 and stats.rms_dots[2] == 0.0
    assert stats.coverage_fraction[0] == 0.0
    assert stats.coverage_fraction[2] == 0.0


def test_an_antisymmetric_pair_no_longer_shrinks_the_third_plane() -> None:
    """§6.5.4b, the sheet-I bug, as a unit: C = +d, M = -d, Y = y.

    The committed pose sits at the C/M mean, so C and M carry equal and
    opposite deltas -- and they CANCEL in a signed cross-plane mean.
    Under the retired law the pooled "common field" came out at about
    y/3 and Y was shrunk toward a third of itself; the fix is that Y's
    posterior does not know C and M exist.
    """
    tiles_yx = (16, 16)
    differential = 0.6
    yellow = 0.75
    field = PlaneDeltaField(3, tiles_yx)
    field.add([
        FieldEvidence(
            page=0,
            tile_yx=(tile_y + 0.5, tile_x + 0.5),
            plane_index=plane,
            offset_dots_xy=(offset, 0.0),
            weight=weight,
            source=SOURCE_CERTIFIED,
        )
        for tile_y in range(tiles_yx[0])
        for tile_x in range(tiles_yx[1])
        # C and M are word-anchored and dense; Y is dust-thin, which is
        # the regime the cancellation used to bite hardest in.
        for plane, offset, weight in (
            (0, +differential, 1.0), (1, -differential, 1.0),
            (2, yellow, 0.05))
    ])
    field.solve()

    centre = field.lookup_tile_index(0, 8, 8)
    assert centre[0].delta_dots_xy[0] == pytest.approx(
        +differential, abs=0.05)
    assert centre[1].delta_dots_xy[0] == pytest.approx(
        -differential, abs=0.05)
    # THE FIX: Y reads its own evidence, not a third of it.
    assert centre[2].delta_dots_xy[0] == pytest.approx(yellow, abs=0.1)
    assert centre[2].delta_dots_xy[0] > 0.5 * yellow

    # and it stays true with the sign of the C/M pair flipped, which a
    # signed pooled mean would have moved
    mirrored = PlaneDeltaField(3, tiles_yx)
    mirrored.add([
        FieldEvidence(
            page=0,
            tile_yx=(row.tile_yx),
            plane_index=row.plane_index,
            offset_dots_xy=(
                -row.offset_dots_xy[0] if row.plane_index < 2
                else row.offset_dots_xy[0], 0.0),
            weight=row.weight,
            source=row.source,
        )
        for row in _antisymmetric_rows(tiles_yx, differential, yellow)
    ])
    mirrored.solve()
    assert mirrored.lookup_tile_index(0, 8, 8)[2].delta_dots_xy[
        0] == pytest.approx(centre[2].delta_dots_xy[0], abs=1e-9)


def _antisymmetric_rows(
    tiles_yx: tuple[int, int], differential: float, yellow: float,
) -> list[FieldEvidence]:
    return [
        FieldEvidence(
            page=0,
            tile_yx=(tile_y + 0.5, tile_x + 0.5),
            plane_index=plane,
            offset_dots_xy=(offset, 0.0),
            weight=weight,
            source=SOURCE_CERTIFIED,
        )
        for tile_y in range(tiles_yx[0])
        for tile_x in range(tiles_yx[1])
        for plane, offset, weight in (
            (0, +differential, 1.0), (1, -differential, 1.0),
            (2, yellow, 0.05))
    ]


def test_dense_high_confidence_evidence_floats_free_of_the_ridge() -> None:
    tiles_yx = (16, 16)
    field = PlaneDeltaField(3, tiles_yx)
    field.add(_ramp_evidence(tiles_yx, seed=7, planes=(0, 1)))
    field.add([
        FieldEvidence(
            page=0,
            tile_yx=(tile_y + 0.5, tile_x + 0.5),
            plane_index=2,
            offset_dots_xy=(0.9, 0.0),
            weight=1.0,
            source=SOURCE_CERTIFIED,
        )
        for tile_y in range(tiles_yx[0])
        for tile_x in range(tiles_yx[1])
    ])
    field.solve()
    got = field.lookup_tile_index(0, 8, 8)[2]
    assert abs(got.delta_dots_xy[0] - 0.9) < 0.10


def test_extrapolation_is_smooth_and_declares_larger_uncertainty() -> None:
    tiles_yx = (12, 24)
    field = PlaneDeltaField(2, tiles_yx)
    field.add([
        FieldEvidence(
            page=0,
            tile_yx=(tile_y + 0.5, tile_x + 0.5),
            plane_index=plane,
            offset_dots_xy=(0.5, -0.2),
            weight=1.0,
            source=SOURCE_CERTIFIED,
        )
        for tile_y in range(tiles_yx[0])
        for tile_x in range(12)
        for plane in range(2)
    ])
    field.solve()

    covered = field.lookup_tile_index(0, 6, 5)[0]
    boundary = field.lookup_tile_index(0, 6, 12)[0]
    far = field.lookup_tile_index(0, 6, 23)[0]

    assert covered.covered and not far.covered
    assert abs(covered.delta_dots_xy[0] - 0.5) < 0.05
    # the continuation is smooth: still near the boundary value one tile
    # out, decaying monotonically toward the natural zero further out
    assert abs(boundary.delta_dots_xy[0] - 0.5) < 0.15
    profile = [
        field.lookup_tile_index(0, 6, tile_x)[0].delta_dots_xy[0]
        for tile_x in range(12, 24)
    ]
    assert all(
        later <= earlier + 1e-9
        for earlier, later in zip(profile, profile[1:]))
    assert abs(far.delta_dots_xy[0]) < 0.05

    uncertainty = [
        field.lookup_tile_index(0, 6, tile_x)[0].uncertainty_dots
        for tile_x in range(24)
    ]
    assert covered.uncertainty_dots < boundary.uncertainty_dots
    assert boundary.uncertainty_dots < far.uncertainty_dots
    assert all(
        later >= earlier - 1e-9
        for earlier, later in zip(uncertainty[5:], uncertainty[6:]))
    assert all(math.isfinite(value) for value in uncertainty)


def test_linear_ramp_yields_the_constant_jacobian_and_zero_elsewhere() -> None:
    tiles_yx = (20, 20)
    slope_dots_per_tile = 0.03
    field = PlaneDeltaField(2, tiles_yx)
    field.add([
        FieldEvidence(
            page=0,
            tile_yx=(tile_y + 0.5, tile_x + 0.5),
            plane_index=plane,
            offset_dots_xy=(slope_dots_per_tile * (tile_x + 0.5), 0.0),
            weight=1.0,
            source=SOURCE_CERTIFIED,
        )
        for tile_y in range(tiles_yx[0])
        for tile_x in range(tiles_yx[1])
        for plane in range(2)
    ])
    field.solve()

    expected = slope_dots_per_tile / TILE_CELLS
    for tile_y in (7, 10, 13):
        for tile_x in (7, 10, 13):
            for plane_affine in field.lookup_tile_index(0, tile_y, tile_x):
                jac = plane_affine.jacobian_dots_per_cell
                assert jac[0][0] == pytest.approx(expected, rel=0.05)
                assert abs(jac[0][1]) < 0.05 * expected
                assert abs(jac[1][0]) < 0.05 * expected
                assert abs(jac[1][1]) < 0.05 * expected

    centre = field.lookup_tile_index(0, 10, 10)[0]
    # the local affine walked one whole tile in x moves by one ramp step
    walked = centre.delta_dots_at((float(TILE_CELLS), 0.0))
    assert walked[0] - centre.delta_dots_xy[0] == pytest.approx(
        slope_dots_per_tile, rel=0.05)
    assert walked[1] == pytest.approx(centre.delta_dots_xy[1], abs=1e-6)


def test_cell_and_tile_lookups_agree_and_pages_are_independent() -> None:
    tiles_yx = (8, 8)
    field = PlaneDeltaField(1, tiles_yx, bins_per_tile=2)
    field.add([
        FieldEvidence.from_cell_yx(
            page=0,
            cell_yx=(tile_y * TILE_CELLS + 32.0, tile_x * TILE_CELLS + 32.0),
            plane_index=0,
            offset_dots_xy=(0.25, 0.1),
            weight=1.0,
            source=SOURCE_PROBE,
        )
        for tile_y in range(tiles_yx[0])
        for tile_x in range(tiles_yx[1])
    ])
    field.solve()

    by_tile = field.lookup(0, (4.5, 4.5))[0]
    by_cell = field.lookup_cells(0, (4.5 * TILE_CELLS, 4.5 * TILE_CELLS))[0]
    assert by_cell.delta_dots_xy == by_tile.delta_dots_xy
    assert by_tile.delta_dots_xy[0] == pytest.approx(0.25, abs=0.02)

    # a page with no evidence is the natural zero at the prior uncertainty
    empty = field.lookup(1, (4.5, 4.5))[0]
    assert empty.delta_dots_xy == (0.0, 0.0)
    assert empty.jacobian_dots_per_cell == ((0.0, 0.0), (0.0, 0.0))
    assert empty.uncertainty_dots == pytest.approx(
        math.hypot(field.plane_sigma_dots, field.prior_sigma_dots))
    assert not empty.covered
    assert empty.uncertainty_dots > by_tile.uncertainty_dots


def test_stats_counts_by_tag_and_reports_per_plane_magnitudes() -> None:
    tiles_yx = (10, 10)
    field = PlaneDeltaField(3, tiles_yx)
    field.add([
        FieldEvidence(
            page=0,
            tile_yx=(tile_y + 0.5, tile_x + 0.5),
            plane_index=plane,
            offset_dots_xy=(0.4 if plane == 1 else 0.0, 0.0),
            weight=1.0,
            source=SOURCE_CERTIFIED if plane else SOURCE_WORD,
        )
        for tile_y in range(tiles_yx[0])
        for tile_x in range(tiles_yx[1])
        for plane in range(3)
    ])
    field.add([FieldEvidence(
        page=1,
        tile_yx=(1.5, 1.5),
        plane_index=0,
        offset_dots_xy=(0.0, 0.0),
        weight=0.5,
        source=SOURCE_DUST,
    )])
    field.solve()

    stats = field.stats()
    assert stats.n_samples == 301
    assert stats.samples_by_source == {
        SOURCE_WORD: 100, SOURCE_CERTIFIED: 200, SOURCE_DUST: 1}
    assert stats.samples_by_plane == (101, 100, 100)
    assert stats.weight_by_plane == (100.5, 100.0, 100.0)
    assert stats.pages == (0, 1)
    assert stats.peak_dots[1] > stats.peak_dots[0]
    assert stats.rms_dots[1] == pytest.approx(0.4, abs=0.05)
    assert stats.rms_dots[2] < 0.05
    # page 1 carries one plane-0 sample: coverage counts both pages' grids
    assert 0.45 < stats.coverage_fraction[0] < 0.75
    assert 0.45 < stats.coverage_fraction[1] < 0.55


def test_json_round_trip_reproduces_the_solution() -> None:
    tiles_yx = (12, 12)
    field = PlaneDeltaField(3, tiles_yx, bandwidth_tiles=1.5, bins_per_tile=2)
    field.add(_scatter_sinusoid(3, tiles_yx, 1, seed=5))
    field.solve()

    revived = PlaneDeltaField.from_json(field.to_json())
    assert not revived.solved
    revived.solve()
    for tile_y in (2, 6, 9):
        for tile_x in (2, 6, 9):
            for original, copy in zip(
                field.lookup_tile_index(0, tile_y, tile_x),
                revived.lookup_tile_index(0, tile_y, tile_x),
            ):
                assert copy == original
    assert revived.stats() == field.stats()


def test_api_rejects_bad_units_indices_and_use_order() -> None:
    field = PlaneDeltaField(3, (8, 8))
    with pytest.raises(ValueError, match="weight"):
        FieldEvidence(
            page=0, tile_yx=(1.0, 1.0), plane_index=0,
            offset_dots_xy=(0.0, 0.0), weight=-0.1)
    with pytest.raises(ValueError, match="offset_dots_xy"):
        FieldEvidence(
            page=0, tile_yx=(1.0, 1.0), plane_index=0,
            offset_dots_xy=(float("nan"), 0.0))
    with pytest.raises(ValueError, match="plane_index"):
        FieldEvidence(
            page=0, tile_yx=(1.0, 1.0), plane_index=-1,
            offset_dots_xy=(0.0, 0.0))
    with pytest.raises(ValueError, match="source"):
        FieldEvidence(
            page=0, tile_yx=(1.0, 1.0), plane_index=0,
            offset_dots_xy=(0.0, 0.0), source="")

    good = FieldEvidence(
        page=0, tile_yx=(1.0, 1.0), plane_index=0,
        offset_dots_xy=(0.0, 0.0), weight=0.0)
    with pytest.raises(RuntimeError, match="solve"):
        field.lookup(0, (1.0, 1.0))
    with pytest.raises(RuntimeError, match="solve"):
        field.stats()

    with pytest.raises(ValueError, match="outside n_planes"):
        field.add([FieldEvidence(
            page=0, tile_yx=(1.0, 1.0), plane_index=3,
            offset_dots_xy=(0.0, 0.0))])
    with pytest.raises(ValueError, match="outside tiles_yx"):
        field.add([FieldEvidence(
            page=0, tile_yx=(1.0, 9.0), plane_index=0,
            offset_dots_xy=(0.0, 0.0))])

    assert field.add([good]) == 1
    field.solve()
    assert field.solved
    with pytest.raises(ValueError, match="outside n_planes"):
        field.lookup_plane(0, (1.0, 1.0), 3)
    assert field.lookup_plane(0, (1.0, 1.0), 2).plane_index == 2

    # adding evidence invalidates the solution
    field.add([good])
    assert not field.solved
    with pytest.raises(RuntimeError, match="solve"):
        field.lookup(0, (1.0, 1.0))


def test_constructor_validates_its_units() -> None:
    with pytest.raises(ValueError, match="n_planes"):
        PlaneDeltaField(0, (4, 4))
    with pytest.raises(ValueError, match="tiles_yx"):
        PlaneDeltaField(1, (4, 0))
    with pytest.raises(ValueError, match="bandwidth_tiles"):
        PlaneDeltaField(1, (4, 4), bandwidth_tiles=0.0)
    with pytest.raises(ValueError, match="plane_sigma_dots"):
        PlaneDeltaField(1, (4, 4), plane_sigma_dots=-1.0)
    with pytest.raises(ValueError, match="sample_sigma_dots"):
        PlaneDeltaField(1, (4, 4), sample_sigma_dots=0.0)
    with pytest.raises(ValueError, match="prior_sigma_dots"):
        PlaneDeltaField(1, (4, 4), prior_sigma_dots=0.0)
    with pytest.raises(ValueError, match="bins_per_tile"):
        PlaneDeltaField(1, (4, 4), bins_per_tile=0)
