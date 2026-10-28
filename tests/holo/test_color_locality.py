"""PK4: the A3 arm — per-window photometric maps.

The load-bearing claim of this packet is NOT "photometric maps improve a
fit".  It is the cross-pathology law:

    a treatment engages where its disease exists, and nowhere else.

So the fixtures come in a MATCHED PAIR, identical in every parameter but
one — a spatially varying gain.  On the gradient channel A3 must adopt
and the region model must strictly improve; on its twin A3 must refuse
every window and the emitted evidence must be BIT-IDENTICAL to the
force-null receiver.  One fixture could prove neither claim: a channel
that adopts says nothing about restraint, and a channel that refuses says
nothing about capability.

SINCE PK-CLEAN THE ARM IS OVERRIDE-ONLY, so every end-to-end test here
drives it through ``arm_override='a3'`` — its supplemental lane's
identity — and the standard ladder never fits a window map at all.  That
reachability is pinned structurally in ``test_color_uplift_lanes``; what
this module pins is the arm's own behaviour once a lane forces it.

The two REGION applicability floors PK4.1 and PK4.2 built here (raw map
dispersion and its normalized variance-ratio successor) are RETIRED and
their cross-pathology channels with them: measured on all 27 lanes of two
captures, neither separates the lanes A3 helps from the lanes it taxes
(COLOR-UPLIFT-MEASUREMENTS §6.3/§7.4, retirement record §12).  The
matched pair survives because it still states the arm's own gates: on the
gradient channel A3 adopts and the region model strictly improves; on its
twin every window refuses and the emitted evidence is BIT-IDENTICAL to
the force-null receiver.

The rest pins the mechanism: the synthetic gradient's all-zero default is
a bit-exact no-op (so every pre-PK4 fixture is untouched), the halo is
rows-only geometry and is pooled ONLY on starvation, the balanced weights
generalize PK3's exactly, the shrinkage really does move toward identity,
and a refused arm passes the caller's OWN array objects (risk R3).
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from _color_stack_fixtures import (
    NO_GAIN_GRADIENT,
    build_fixture,
    build_locality_fixture,
)
from holo.qualification.color_synthetic import (
    ColorChannelParameters,
    render_color_scan,
)
from holo.receive import (
    color_context,
    color_detect,
    color_locality,
    color_stack,
)
from holo.receive.color_calibration import class_balanced_weights
from holo.receive.color_locality import (
    REASON_ADOPTED,
    REASON_GATE_FAILED,
    REASON_HELDOUT_STARVED,
    REASON_NO_WINDOW_MAPS,
    REASON_SEARCH_STARVED,
    REASON_STATE_SUPPORT,
    WindowPhotometryConfig,
    _halo_membership,
    _window_bboxes,
    balanced_base_weights,
    fit_window_photometry,
)
from holo.receive.color_payload import collect_color_evidence
from holo.receive.color_stack import StackConfig, UPLIFT_ARM_A3


# The cross-pathology pair.  Same blur, same noise, same seeded field,
# same faint-print tone; the ONLY difference is the gain ramp.  The
# per-channel directions differ (R in y, G in x, B diagonal) so a map that
# only ever fitted one shared gain could not pass.
LOCALITY_BLUR = 1.0
LOCALITY_NOISE = 0.10
GAIN_GRADIENT = ((0.40, 0.0), (0.0, 0.40), (0.28, 0.28))
# PK4.1's third channel: a real photometric gain with ZERO spatial
# structure.  Same blur/noise/field/tone; the gain is page-wide, so every
# window that earns a map earns the SAME map and the dispersion floor
# must refuse the arm.
UNIFORM_GAIN = (0.86, 0.90, 0.94)
UNIFORM_NOISE = 0.15
# The CMY8 row has no A4 head at all, so a force-null comparison against
# it differs in A3 and in nothing else (the cmy7 rows would also switch
# the head off with the ladder).
UNIFORM_ROW = "c3-cmy8-p120-v0@2240x1536"
# The frozen A3 configuration, named so the mechanism tests below read
# the same object the supplemental lane hands the arm.
FROZEN = WindowPhotometryConfig()


# A5 SWITCHED OFF, so a force-null comparison isolates A3 again.  PK5
# landed a second LIVE arm below A3 in the ladder, and force-null
# switches off the WHOLE stack — so "A3 refused, therefore the evidence
# equals the force-null receiver's" stopped being a statement about A3
# the moment a context head could adopt on the same fixture.  Every
# exact-null claim about ONE arm has to name the arms it is holding
# still; this is that name, and since PK-CLEAN it is lane-scoped
# configuration rather than an environment variable.
A5_OFF = StackConfig(
    context=color_context.ContextConfig(
        variant=color_context.CONTEXT_VARIANT_OFF))


def _regions(fixture, *, arm: str | None = UPLIFT_ARM_A3, config=None):
    """Collect one fixture's regions, by default through A3's own lane.

    ``arm=None`` is the STANDARD ladder, where since PK-CLEAN A3 is
    unreachable — used here only for the force-null and standard-ladder
    comparisons.
    """
    rows: list = []
    evidence = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec,
        region_progress=rows.append, arm_override=arm, stack_config=config)
    return rows, evidence


def _evidence_by_patch(evidence) -> dict[int, np.ndarray]:
    return {int(window.patch_id): np.asarray(window.evidence_values)
            for window in evidence.windows}


# ---------------------------------------------------------------- forward
def test_zero_gain_gradient_is_a_bit_exact_render_no_op() -> None:
    """An unset gradient must not perturb one bit of any fixture."""
    source = np.zeros((24, 24, 3), np.float64)
    source[4:12, 4:12, 0] = 1.0
    source[8:20, 10:22, 1] = 0.6
    default = render_color_scan(
        source, ColorChannelParameters(noise_std_rgb=(0.01,) * 3, seed=7))
    explicit = render_color_scan(
        source,
        ColorChannelParameters(
            noise_std_rgb=(0.01,) * 3, seed=7,
            gain_gradient=NO_GAIN_GRADIENT))
    assert np.array_equal(default.rgb, explicit.rgb)
    assert np.array_equal(default.truth.clean_rgb, explicit.truth.clean_rgb)
    assert not np.any(default.truth.gain_gradient)
    # ...and a real gradient DOES move the image, in the declared
    # direction: channel 0 ramps in y, channel 1 in x.
    ramped = render_color_scan(
        source,
        ColorChannelParameters(
            noise_std_rgb=(0.0,) * 3, seed=7,
            gain_gradient=((0.4, 0.0), (0.0, 0.4), (0.0, 0.0))))
    clean = render_color_scan(
        source, ColorChannelParameters(noise_std_rgb=(0.0,) * 3, seed=7))
    top = ramped.truth.clean_rgb[0].mean(axis=0)
    bottom = ramped.truth.clean_rgb[-1].mean(axis=0)
    assert bottom[0] > top[0]
    assert np.array_equal(ramped.truth.clean_rgb[:, :, 2],
                          clean.truth.clean_rgb[:, :, 2])
    assert np.array_equal(ramped.truth.gain_gradient,
                          np.asarray(((0.4, 0.0), (0.0, 0.4), (0.0, 0.0))))


def test_gain_gradient_refuses_a_negative_canvas_gain() -> None:
    source = np.zeros((8, 8, 3), np.float64)
    with pytest.raises(ValueError, match="gain_gradient"):
        render_color_scan(
            source,
            ColorChannelParameters(
                gain_gradient=((0.7, 0.4), (0.0, 0.0), (0.0, 0.0))))


# ------------------------------------------------------------- primitives
def test_balanced_base_weights_generalize_pk3_exactly() -> None:
    """With every base weight 1 this IS color_calibration's function."""
    states = np.asarray([0, 0, 0, 0, 1, 1, 2, 3, 3, 3, 5, 6], np.int64)
    base = np.ones(states.size, np.float64)
    assert np.array_equal(
        balanced_base_weights(states, base), class_balanced_weights(states))
    # Halo mass discounts a row without breaking the class balance: every
    # represented state still carries equal total weight, and the total is
    # preserved at the base mass (so n_eff means the same before/after).
    base = np.where(np.arange(states.size) % 2 == 0, 1.0, 0.5)
    weights = balanced_base_weights(states, base)
    per_state = np.bincount(states, weights=weights)
    represented = np.unique(states)
    assert np.allclose(per_state[represented], per_state[represented][0])
    assert np.isclose(weights.sum(), base.sum())


def test_halo_is_rows_only_geometry_with_own_extent_dilation() -> None:
    # A 3x3 tile field of 64-cell windows: each window's bbox dilated by
    # its own 63-cell extent reaches its 8 neighbours and nothing else,
    # so the corner windows see 3, the edges 5, the centre 8.
    bounds = _window_bboxes(
        tuple(_FakeRows(np.stack(np.meshgrid(
            np.arange(ty * 64, ty * 64 + 64),
            np.arange(tx * 64, tx * 64 + 64), indexing="ij"),
            axis=-1).reshape(-1, 2))
            for ty in range(3) for tx in range(3)))
    halo = _halo_membership(bounds)
    assert not np.any(np.diag(halo))
    assert halo.sum(axis=1).tolist() == [3, 5, 3, 5, 8, 5, 3, 5, 3]
    assert np.array_equal(halo, halo.T)


class _FakeRows:
    """Only ``page_cells_yx`` is read by the halo geometry."""

    def __init__(self, cells: np.ndarray) -> None:
        self.page_cells_yx = cells


def test_window_map_shrinks_toward_identity_with_the_prior() -> None:
    """More prior = closer to identity; the family is the same one."""
    identity = color_locality.WindowMap(np.ones(3), np.zeros(3))
    features = np.linspace(0.0, 1.0, 30).reshape(10, 3)
    assert np.array_equal(identity.apply(features), features)
    strong = WindowPhotometryConfig(1e9)
    weak = WindowPhotometryConfig(1e-6)
    fixture = build_locality_fixture(
        LOCALITY_BLUR, LOCALITY_NOISE, GAIN_GRADIENT)
    _inputs, maps_strong = _fit_maps(fixture, strong)
    _inputs, maps_weak = _fit_maps(fixture, weak)
    strong_gains = np.concatenate([
        fit.window_map.gains for fit in maps_strong.fits if fit.accepted])
    weak_gains = np.concatenate([
        fit.window_map.gains for fit in maps_weak.fits
        if fit.accepted])
    assert np.max(np.abs(strong_gains - 1.0)) < 1e-4
    assert np.max(np.abs(weak_gains - 1.0)) > 0.05


def _fit_maps(fixture, config: WindowPhotometryConfig):
    """Run the A3 fit alone on one fixture's first region.

    Returns ``(inputs, result)`` so a caller can assert OBJECT identity
    between what the ladder handed the arm and what the arm handed back.
    """
    captured: list = []
    original = color_stack.fit_window_photometry

    def recording(model, selection, row_tuple, features, cfg):
        del cfg
        result = original(model, selection, row_tuple, features, config)
        captured.append((features, result))
        return result

    color_stack.fit_window_photometry = recording  # type: ignore[assignment]
    try:
        collect_color_evidence(
            fixture.raster, fixture.source, fixture.address, fixture.spec,
            arm_override=UPLIFT_ARM_A3)
    finally:
        color_stack.fit_window_photometry = original  # type: ignore[assignment]
    return captured[0]


# --------------------------------------------------------- cross-pathology
def test_a3_adopts_and_improves_where_the_gain_varies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_locality_fixture(
        LOCALITY_BLUR, LOCALITY_NOISE, GAIN_GRADIENT)
    rows, evidence = _regions(fixture)
    assert len(rows) == 1
    row = rows[0]
    assert row.accepted
    maps = row.window_photometry
    assert maps.accepted > 0
    assert maps.adopted is True
    assert maps.reason == REASON_ADOPTED
    # The region model really is better, not merely different.
    assert row.selected_heldout_logloss < row.baseline_heldout_logloss
    assert maps.reasons
    assert dict(maps.reasons)[REASON_ADOPTED] == maps.accepted
    assert evidence.windows
    # ...and the arm reaches EMISSION: the evidence a decode would consume
    # differs from the force-null receiver's on this channel.
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    _null_rows, null = _regions(fixture, arm=None)
    live_by_patch = _evidence_by_patch(evidence)
    null_by_patch = _evidence_by_patch(null)
    assert any(
        not np.array_equal(values, null_by_patch[patch_id])
        for patch_id, values in live_by_patch.items())


def test_a3_refuses_the_same_channel_without_a_gain_gradient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The opposite pathology: noise, no gain drift, and NO evidence change.

    Same blur, same noise, same field, same tone — only the gradient is
    gone.  Every window must refuse, the arm must never be attempted, and
    the emitted evidence must be bit-identical to the force-null
    receiver's (which is today's receiver by construction).
    """
    fixture = build_locality_fixture(
        LOCALITY_BLUR, LOCALITY_NOISE, NO_GAIN_GRADIENT)
    rows, live = _regions(fixture, config=A5_OFF)
    row = rows[0]
    maps = row.window_photometry
    assert maps.accepted == 0
    assert maps.refused > 0
    assert maps.adopted is False
    assert maps.reason == REASON_NO_WINDOW_MAPS
    assert dict(maps.reasons) == {REASON_GATE_FAILED: maps.refused}
    # The head, already floored by PK3.1, refuses here too — so the whole
    # comparison below is A0/A1 against A0/A1.
    assert not row.cmy7_head_adopted

    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    null_rows, null = _regions(fixture, arm=None, config=A5_OFF)
    assert null_rows[0].window_photometry.accepted == 0
    live_by_patch = _evidence_by_patch(live)
    null_by_patch = _evidence_by_patch(null)
    assert live_by_patch.keys() == null_by_patch.keys()
    for patch_id, values in live_by_patch.items():
        assert np.array_equal(values, null_by_patch[patch_id]), patch_id


def test_the_pair_differs_only_in_the_gradient() -> None:
    """The fixtures would prove nothing if they differed elsewhere."""
    with_gradient = build_locality_fixture(
        LOCALITY_BLUR, LOCALITY_NOISE, GAIN_GRADIENT)
    without = build_locality_fixture(
        LOCALITY_BLUR, LOCALITY_NOISE, NO_GAIN_GRADIENT)
    assert with_gradient.row_id == without.row_id
    assert with_gradient.spec is without.spec
    assert np.array_equal(with_gradient.field, without.field)
    assert with_gradient.pitch_px == without.pitch_px
    assert with_gradient.raster.source.sha256 != without.raster.source.sha256


# ---------------------------------------------------------------- refusals
def test_refused_windows_pass_the_caller_s_own_arrays() -> None:
    """R3: an unattempted arm is a null, not a tuple of identical copies."""
    fixture = build_locality_fixture(
        LOCALITY_BLUR, LOCALITY_NOISE, NO_GAIN_GRADIENT)
    inputs, result = _fit_maps(fixture, FROZEN)
    assert result.accepted == 0
    assert all(not fit.accepted for fit in result.fits)
    # The caller's OWN tuple object, not a rebuilt one holding the same
    # arrays — so the ladder cannot even be tempted to refit.
    assert result.features is inputs
    # On a channel where SOME windows adopt, the refused ones still hand
    # back their own arrays object-for-object.
    adopted = build_locality_fixture(
        LOCALITY_BLUR, LOCALITY_NOISE, GAIN_GRADIENT)
    partial_inputs, partial = _fit_maps(adopted, FROZEN)
    assert 0 < partial.accepted < len(partial.fits)
    assert partial.features is not partial_inputs
    for fit in partial.fits:
        got = partial.features[fit.ordinal]
        want = partial_inputs[fit.ordinal]
        if fit.accepted:
            assert got is not want
            assert np.array_equal(got, want * fit.window_map.gains
                                  + fit.window_map.offsets)
        else:
            assert fit.window_map is None
            assert got is want


def test_the_floors_name_their_own_refusals() -> None:
    """Each floor produces its K-vocabulary reason, on its own population."""
    means = np.asarray(
        [[0.9, 0.9, 0.9], [0.5, 0.9, 0.9], [0.9, 0.5, 0.9],
         [0.5, 0.5, 0.9], [0.9, 0.9, 0.5], [0.5, 0.9, 0.5],
         [0.9, 0.5, 0.5]], np.float64)
    model = _FakeModel(means)
    config = FROZEN

    # Too few labels: 20 rows in a lone window with no neighbours.
    result = fit_window_photometry(
        model, *_synthetic_region(n_windows=1, per_state=3), config)
    assert [fit.reason for fit in result.fits] == [REASON_SEARCH_STARVED]

    # Enough labels, but only two states — six parameters are not
    # identifiable from two class means.
    result = fit_window_photometry(
        model, *_synthetic_region(n_windows=1, per_state=40, states=(0, 1)),
        config)
    assert [fit.reason for fit in result.fits] == [REASON_STATE_SUPPORT]

    # Search population and state coverage both fine, but no OWN
    # held-out population to gate the map on.
    result = fit_window_photometry(
        model, *_synthetic_region(n_windows=1, per_state=20, heldout=2),
        config)
    assert [fit.reason for fit in result.fits] == [REASON_HELDOUT_STARVED]


def test_the_halo_is_pooled_only_when_a_window_is_starved() -> None:
    """PK4.1: own labels first; neighbours ONLY when six params cannot fit.

    The measured reason (COLOR-UPLIFT-MEASUREMENTS §5.2/§5.3): a
    neighbour's cells are evidence about the NEIGHBOUR's photometry, so a
    standing halo dilutes exactly the window-scale drift A3 exists to
    track — the swept halo axis was monotone and its out-of-grid zero
    point was the best of all ten.  The machinery survives for the case
    the corpus never produced: a window too label-poor to identify its
    own map.
    """
    # A REAL QDA here, not the floors test's stub: these windows clear
    # every floor and go on to be scored, which is the point.
    model = _real_model()

    # Two neighbouring windows, both rich: neither borrows anything.
    rich = fit_window_photometry(
        model, *_synthetic_region(n_windows=2, per_state=10), FROZEN)
    assert [fit.n_halo for fit in rich.fits] == [0, 0]
    assert rich.pooled == 0

    # The same geometry with window 0 starved (3 labels per state = 21,
    # under the 40-label floor): it pools, its rich neighbour does not.
    mixed = fit_window_photometry(
        model,
        *_synthetic_region(n_windows=2, per_state=10, per_window={0: 3}),
        FROZEN)
    starved, neighbour = mixed.fits
    assert starved.n_own == 21 and starved.n_halo == 70
    assert starved.pooled and not neighbour.pooled
    assert mixed.pooled == 1
    # Pooling is what SAVED it: the same window alone is refused.
    alone = fit_window_photometry(
        model, *_synthetic_region(n_windows=1, per_state=3), FROZEN)
    assert [fit.reason for fit in alone.fits] == [REASON_SEARCH_STARVED]


def test_the_cert_preview_is_reported_whole_and_scored_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The P6 preview publishes the WHOLE population and scores a slice.

    Measured (COLOR-UPLIFT-MEASUREMENTS §6.6): a late-lane three-plane
    cmy8 region carries ~4M certified payload cells, and scoring all of
    them through two QDAs costs about a GiB of transient per worker —
    which a report-only diagnostic may not spend.  The published
    `cert_cells` stays the true count; only the NLL estimate is
    subsampled, by a deterministic stride.
    """
    from holo.receive.color_fitting import _OwnerSelection

    n_rows = color_locality.CERT_PREVIEW_MAX_CELLS * 3 + 7
    states = np.tile(np.arange(7), n_rows // 7 + 1)[:n_rows]
    selection = _OwnerSelection(
        np.zeros(n_rows, np.int64), np.arange(n_rows),
        states.astype(np.int64),
        np.full(n_rows, -1, np.int8),          # every row CERT-labelled
        np.stack([np.zeros(n_rows), np.arange(n_rows),
                  np.zeros(n_rows)], axis=1).astype(np.int64),
        np.zeros(n_rows, np.bool_))
    features = (np.full((n_rows, 3), 0.5, np.float64),)
    scored: list[int] = []
    original = color_locality._balanced_nll
    monkeypatch.setattr(
        color_locality, "_balanced_nll",
        lambda model, rows, labels, weights: (
            scored.append(rows.shape[0]) or original(
                model, rows, labels, weights)))
    model = _real_model()
    cells, incumbent, mapped = color_locality.cert_population_preview(
        model, model, selection, features, features)
    assert cells == n_rows
    # An integer stride, so the cap is an upper bound (and never so
    # coarse that half the budget goes unused).
    cap = color_locality.CERT_PREVIEW_MAX_CELLS
    assert len(scored) == 2 and scored[0] == scored[1]
    assert cap // 2 < scored[0] <= cap
    assert incumbent == mapped        # same model, same rows
    # A population under the cap is scored whole.
    scored.clear()
    small = 900
    selection = _OwnerSelection(
        np.zeros(small, np.int64), np.arange(small),
        states[:small].astype(np.int64), np.full(small, -1, np.int8),
        np.stack([np.zeros(small), np.arange(small),
                  np.zeros(small)], axis=1).astype(np.int64),
        np.zeros(small, np.bool_))
    features = (np.full((small, 3), 0.5, np.float64),)
    cells, _incumbent, _mapped = color_locality.cert_population_preview(
        model, model, selection, features, features)
    assert cells == small and scored == [small, small]


def _real_model() -> color_detect.ColorQDAModel:
    """A scoreable 7-state QDA around the fixtures' canonical means."""
    means = np.asarray(
        [[0.9, 0.9, 0.9], [0.5, 0.9, 0.9], [0.9, 0.5, 0.9],
         [0.5, 0.5, 0.9], [0.9, 0.9, 0.5], [0.5, 0.9, 0.5],
         [0.9, 0.5, 0.5]], np.float64)
    generator = np.random.default_rng(0xA3)
    rows = np.repeat(means, 40, axis=0) + generator.normal(
        0.0, 0.02, (means.shape[0] * 40, 3))
    return color_detect.fit_equal_prior_qda(
        rows, np.repeat(np.arange(means.shape[0]), 40), n_states=7)


class _FakeModel:
    """Just enough QDA for the FLOORS: the class means, nothing else.

    A window that clears every floor goes on to score its held-out rows
    through the real ``qda_log_scores``, which this object cannot serve —
    so if a floor ever stopped firing, this test would fail loudly rather
    than quietly pass on a weaker assertion.
    """

    def __init__(self, means: np.ndarray) -> None:
        self.means = means


def _synthetic_region(
    *, n_windows: int, per_state: int, states: tuple[int, ...] = tuple(range(7)),
    heldout: int = 40, per_window: dict[int, int] | None = None,
):
    """Build (selection, row_tuple, features) with controlled populations.

    The split is stated directly in the ``_OwnerSelection`` (as the real
    one is, after ``_deterministic_fit_split``'s sparse-state repair), so
    a floor can be starved exactly rather than by hunting for coordinates
    whose ``(131y + 17x) & 1`` happens to land right.  Cells are laid
    inside each window's own 64x64 page block, so consecutive windows are
    genuine bbox neighbours and the halo geometry is exercisable;
    ``per_window`` overrides ``per_state`` for named windows, which is how
    one starved window next to a rich one is built.
    """
    from holo.receive.color_fitting import _OwnerSelection

    keys: list[tuple[int, int, int]] = []
    labels: list[int] = []
    search: list[bool] = []
    ordinals: list[int] = []
    row_indices: list[int] = []
    for window in range(n_windows):
        count = (per_state if per_window is None
                 else per_window.get(window, per_state))
        cell = 0

        def place(state: int, is_search: bool) -> None:
            nonlocal cell
            keys.append(
                (0, (cell // 64) % 64, window * 64 + cell % 64))
            labels.append(state)
            search.append(is_search)
            ordinals.append(window)
            row_indices.append(len(row_indices))
            cell += 1

        for state in states:
            for _index in range(count):
                place(state, True)
        for index in range(heldout):
            place(states[index % len(states)], False)
    n_rows = len(keys)
    selection = _OwnerSelection(
        np.asarray(ordinals, np.int64),
        np.asarray(row_indices, np.int64),
        np.asarray(labels, np.int64),
        np.zeros(n_rows, np.int8),
        np.asarray(keys, np.int64),
        np.asarray(search, np.bool_),
    )
    features = tuple(
        np.full((n_rows, 3), 0.5, np.float64) for _ in range(n_windows))
    rows = tuple(
        _FakeRows(np.asarray(
            [(key[1], key[2]) for key, ordinal in zip(keys, ordinals)
             if ordinal == window], np.int64))
        for window in range(n_windows))
    return selection, rows, features


# ------------------------------------------- reachability and the config
def test_force_null_never_fits_a_window_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    fixture = build_locality_fixture(
        LOCALITY_BLUR, LOCALITY_NOISE, GAIN_GRADIENT)
    for arm in (None, UPLIFT_ARM_A3):
        rows, _evidence = _regions(fixture, arm=arm)
        maps = rows[0].window_photometry
        assert maps.accepted == 0
        assert maps.refused == 0
        assert maps.reasons == ()
        assert maps.reason == ""
        assert maps.adopted is False
        assert maps.prior_labels == 0.0


def test_the_standard_ladder_never_fits_a_window_map() -> None:
    """OVERRIDE-ONLY (PK-CLEAN): no lane but ``u*-a3`` can reach the arm.

    The channel is the one A3 DOES adopt on under its own override
    (asserted above), so this cannot pass vacuously: the same fixture
    that produces nine accepted maps in the supplemental lane produces
    not one on the standard ladder, and the summary is the default
    instance rather than a refusal record.
    """
    fixture = build_locality_fixture(
        LOCALITY_BLUR, LOCALITY_NOISE, GAIN_GRADIENT)
    forced = _regions(fixture)[0][0].window_photometry
    assert forced.accepted > 0 and forced.adopted is True
    standard = _regions(fixture, arm=None)[0][0].window_photometry
    assert standard == color_locality.WindowPhotometrySummary()


def test_the_stack_config_carries_the_prior_and_validates_it() -> None:
    """PK-CLEAN: the swept constant is an ARGUMENT, not an environment read.

    The module reads no environment variable at all — grep is the pin
    below — so a sweep reaches the arm only as
    ``StackConfig(window_photometry=…)``, threaded from the harness
    entry point the way ``arm_override`` already was.
    """
    assert StackConfig().window_photometry == WindowPhotometryConfig()
    assert StackConfig(
        window_photometry=WindowPhotometryConfig(80.0),
    ).window_photometry.prior_labels == 80.0
    for bad in (0.0, -1.0, float("nan")):
        with pytest.raises(ValueError, match="prior labels"):
            WindowPhotometryConfig(bad)


def test_the_module_reads_no_environment_variable() -> None:
    """No sweep hatch in a production path (PK-CLEAN item 5)."""
    source = pathlib.Path(color_locality.__file__).read_text()
    assert "os.environ" not in source and "getenv" not in source


def test_the_policy_token_is_generated_from_the_frozen_constant() -> None:
    """Token and constant cannot drift: one is a function of the other."""
    assert WindowPhotometryConfig().policy_token == (
        "winphot-gainoffset-adaptivehalo-shrink20")
    assert WindowPhotometryConfig(40.0).policy_token == (
        "winphot-gainoffset-adaptivehalo-shrink40")
    assert (WindowPhotometryConfig().policy_token
            == WindowPhotometryConfig(
                color_locality.WINDOW_PHOT_PRIOR_LABELS).policy_token)


def test_the_effective_constant_is_published_on_every_region() -> None:
    """A swept run states its own constant; the token cannot cover for it."""
    fixture = build_locality_fixture(
        LOCALITY_BLUR, LOCALITY_NOISE, GAIN_GRADIENT)
    rows: list = []
    collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec,
        region_progress=rows.append, arm_override=UPLIFT_ARM_A3,
        stack_config=StackConfig(
            window_photometry=WindowPhotometryConfig(80.0)))
    assert rows[0].window_photometry.prior_labels == 80.0


# ------------------------------------------------------------ kind-agnostic
@pytest.mark.parametrize("key", ("cmy7-clean", "cmy8-clean"))
def test_the_arm_runs_for_both_kinds(key: str) -> None:
    """A3 transforms FEATURES, so cmy8 is not a no-op scope like A4."""
    fixture = build_fixture(key)
    rows, _evidence = _regions(fixture)
    maps = rows[0].window_photometry
    assert maps.accepted + maps.refused == 9
