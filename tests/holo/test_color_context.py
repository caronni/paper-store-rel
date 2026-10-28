"""PK5 (P2): the neighbourhood corrector, arm A5 (the multi-state matrix).

RECEIVE-DESIGN §6.2a.  What these tests pin, in the order the campaign
cares about it:

1. THE EXACT NULLS.  A refused curve is exactly zero, a refused region
   emits the pre-P2 arrays value for value, and force-null never fits an
   arm (risk R1/R3).
2. THE CROSS-PATHOLOGY LAW (PK4's shape, one arm lower).  On a channel
   with real neighbour bleed the arm adopts and improves; on the SAME
   channel without it it refuses, and its evidence is bit-identical to
   force-null's.
3. THE MECHANISM.  Curve direction is read off the state's plane bit and
   every curve is zero-anchored.
4. THE GEOMETRY.  Neighbour counts are cross-window correct and exact
   KnownField bits overwrite the provisional reading.

THE PER-PLANE K PORT IS RETIRED (PK-CLEAN).  It was the comparison arm
and it lost on paper: 0 of 17 lanes adopted on the uplift target
(MEASUREMENTS §11.4, retirement record §12), so its fitter, its
plane-composition sum, its marginal application locus and every test that
exercised them are gone.  The matrix's own generalization claim survives
in the CROSS-PLANE fixture, which is the channel only a per-state
factorization can express.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from _color_stack_fixtures import (
    CMY7_ROW,
    IDENTITY_MIX,
    build_context_fixture,
    build_head_fixture,
)
from holo.core import channel
from holo.receive import (
    color_context,
    color_neighbourhood,
    color_payload,
    color_stack,
    detect,
)
from holo.receive.color_context import (
    CONTEXT_REASON_ADOPTED,
    CONTEXT_REASON_GATE_FAILED,
    CONTEXT_REASON_NO_CURVE,
    CONTEXT_REASON_SEARCH_CLASS,
    CONTEXT_VARIANT_MATRIX,
    CONTEXT_VARIANT_OFF,
    LOCUS_STATES,
    ContextConfig,
    ContextError,
    ContextHead,
    ContextSummary,
)
from holo.receive.color_payload import collect_color_evidence
from holo.receive.color_stack import StackConfig

CMY8_ROW = "c3-cmy8-p120-v0@2240x1536"
# The pathology, and its absence.  6 px per cell at this footing, so a
# 0.5 px spread stays inside the cell and a 3.0 px one does not.
CLEAN_BLUR = 0.5
BLEED_BLUR = 3.0
NOISE = 0.01
# Cyan additionally subtracts GREEN: plane C's bleed lands in the channel
# plane M is read from.  This is the only fixture axis that separates the
# two variants by construction rather than by fit quality.
CROSS_MIX = ((1.0, 0.55, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _config(variant: str) -> StackConfig:
    """A5's configuration as an ARGUMENT (PK-CLEAN): ``matrix|off`` with
    optional ``:SEARCH,PER_CLASS,VALIDATION,PER_CLASS`` floors, in the
    spelling the retired environment hatch used, so the swept cases below
    still read the way the campaign ran them."""
    name, _, floors = variant.partition(":")
    if not floors:
        return StackConfig(context=ContextConfig(variant=name))
    parts = [int(item) for item in floors.split(",")]
    return StackConfig(context=ContextConfig(
        variant=name, min_search=parts[0], min_search_per_class=parts[1],
        min_validation=parts[2], min_validation_per_class=parts[3]))


def _regions(fixture, variant: str, monkeypatch) -> tuple[list, object]:
    del monkeypatch
    rows: list = []
    evidence = collect_color_evidence(
        fixture.raster, fixture.source, fixture.address, fixture.spec,
        region_progress=rows.append, stack_config=_config(variant))
    return rows, evidence


def _evidence_by_patch(evidence) -> dict[int, np.ndarray]:
    return {int(window.patch_id): np.asarray(window.evidence_values)
            for window in evidence.windows}


# ------------------------------------------------------------- the config
def test_the_config_states_what_the_arm_read_and_refuses_what_it_cannot(
) -> None:
    """A swept run cannot claim a variant or a floor it did not use."""
    assert StackConfig().context == ContextConfig()
    assert ContextConfig().policy_token == (
        "ctxmatrix-9bin-zeroanchor-sweeps3-floors80-20-40-10")
    assert ContextConfig(variant=CONTEXT_VARIANT_OFF).policy_token == "ctxoff"
    assert not ContextConfig(variant=CONTEXT_VARIANT_OFF).enabled
    swept = _config("matrix:50,9,20,4").context
    assert swept.variant == CONTEXT_VARIANT_MATRIX
    assert (swept.min_search, swept.min_search_per_class) == (50, 9)
    assert (swept.min_validation, swept.min_validation_per_class) == (20, 4)
    assert swept.policy_token == (
        "ctxmatrix-9bin-zeroanchor-sweeps3-floors50-9-20-4")
    # The retired per-plane port is not a variant any more, and neither
    # is anything else outside the registry.
    for name in ("planes", "isotonic"):
        with pytest.raises(ContextError):
            ContextConfig(variant=name)
    with pytest.raises(ContextError):
        ContextConfig(sweeps=0)


def test_the_module_reads_no_environment_variable() -> None:
    """No sweep hatch in a production path (PK-CLEAN item 5)."""
    source = pathlib.Path(color_context.__file__).read_text()
    assert "os.environ" not in source and "getenv" not in source


# -------------------------------------------------------------- the head
def _states_head(offsets: np.ndarray, applied: np.ndarray) -> ContextHead:
    return ContextHead(LOCUS_STATES, CONTEXT_VARIANT_MATRIX, offsets, applied)


def test_a_head_cannot_carry_an_offset_it_did_not_adopt() -> None:
    """The invariant behind every exact-null claim in this module."""
    offsets = np.zeros((6, 3, 9))
    applied = np.zeros((6, 3), bool)
    _states_head(offsets, applied)                       # the empty head
    offsets[2, 1, 4] = -0.5
    with pytest.raises(ContextError):
        _states_head(offsets, applied)
    applied[2, 1] = True
    head = _states_head(offsets, applied)
    assert head.n_applied == 1
    assert not head.offsets.flags.writeable
    with pytest.raises(ContextError):                    # wrong locus
        ContextHead("marginals", CONTEXT_VARIANT_MATRIX, offsets, applied)
    with pytest.raises(ContextError):                    # wrong shape
        _states_head(np.zeros((3, 8)), np.zeros(3, bool))


def test_an_incomplete_neighbourhood_receives_exactly_zero() -> None:
    """K's ``-1`` rule: no valid context, no correction, bit for bit."""
    offsets = np.zeros((6, 3, 9))
    offsets[:, :, :] = np.linspace(0.4, -0.4, 9)
    head = _states_head(offsets, np.ones((6, 3), bool))
    scores = np.arange(12, dtype=np.float64).reshape(2, 6)
    bins = np.array([[-1, -1, -1], [0, 0, 0]], np.int8)
    out = head.apply_states(scores, bins)
    assert np.array_equal(out[0], scores[0])
    assert np.all(out[1] > scores[1])
    with pytest.raises(ContextError):
        head.apply_states(scores, np.full((2, 3), 9, np.int8))


# ---------------------------------------------------------- the geometry
def test_provisional_ink_is_the_emitted_marginal_sign_for_both_kinds() -> None:
    cmy8 = np.array([[1.0, -1.0, 0.0], [-3.0, 2.0, 5.0]])
    assert np.array_equal(
        color_neighbourhood.provisional_ink(cmy8, cmy8=True),
        np.array([[True, False, False], [False, True, True]]))
    # cmy7: six W-relative logits, one state overwhelmingly favoured, so
    # the plane marginals must agree with that state's own bits.
    for state in range(1, 7):
        scores = np.full((1, 6), -30.0)
        scores[0, state - 1] = 30.0
        expected = channel.states_to_planes(
            np.array([state], np.uint8)).astype(bool)
        assert np.array_equal(
            color_neighbourhood.provisional_ink(scores, cmy8=False), expected)
    with pytest.raises(color_neighbourhood.NeighbourhoodError):
        color_neighbourhood.provisional_ink(cmy8, cmy8=False)


def test_the_bins_are_cross_window_correct_and_exact_bits_win() -> None:
    """Two adjacent windows: the seam keeps its neighbours, and the
    KnownField's bits outrank the detector's provisional reading."""
    fixture = build_context_fixture(CLEAN_BLUR, NOISE, row_id=CMY8_ROW)
    rows = tuple(
        color_payload._window_rows(patch, fixture.spec)
        for patch in fixture.address.placements[:2])

    class _Row:
        def __init__(self, patch, aligned, ink):
            self.patch = patch
            self.page_cells_yx = aligned.page_cells_yx
            self.known_component_mask = np.zeros(
                (aligned.page_cells_yx.shape[0], 3), bool)
            self.known_component_bits = np.zeros(
                (aligned.page_cells_yx.shape[0], 3), np.uint8)
            self._ink = ink

    windows = tuple(
        _Row(patch, aligned, ink)
        for patch, aligned, ink in zip(
            fixture.address.placements[:2], rows, (True, True), strict=True))
    # Every cell inked in every plane: an interior cell then has 8
    # neighbours and a seam cell only keeps its 8 if the other window is
    # in the same map.
    def evidence(ordinal: int) -> np.ndarray:
        return np.ones((windows[ordinal].page_cells_yx.shape[0], 3))

    both = color_neighbourhood.region_context_bins(
        windows, evidence, cmy8=True)
    single = color_neighbourhood.region_context_bins(
        windows[:1], evidence, cmy8=True)
    # The seam column, minus its two ends (which have no neighbour above
    # or below in EITHER map — the region's outer boundary, not the seam).
    seam = ((windows[0].page_cells_yx[:, 1] == 63)
            & (windows[0].page_cells_yx[:, 0] > 0)
            & (windows[0].page_cells_yx[:, 0] < 63))
    assert np.all(both[0][seam] == 8)          # the neighbour window helps
    assert np.all(single[0][seam] == -1)       # alone, the seam is invalid

    # And the exact bits win: mark one window's cells KNOWN and white
    # while the detector still reads ink everywhere.
    windows[0].known_component_mask[:] = True
    known = color_neighbourhood.region_context_bins(
        windows, evidence, cmy8=True)
    interior = ((windows[1].page_cells_yx[:, 1] == 64)
                & (windows[1].page_cells_yx[:, 0] > 0)
                & (windows[1].page_cells_yx[:, 0] < 63))
    assert np.all(both[1][interior, 0] == 8)
    assert np.all(known[1][interior, 0] == 5)   # the three white neighbours


# ----------------------------------------------------------- the mechanism
def _fit(fixture, variant: str, monkeypatch):
    rows, evidence = _regions(fixture, variant, monkeypatch)
    return rows[0].context, evidence


def test_the_curve_direction_is_read_off_the_state_plane_bit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bleed over-evidences the states that print the plane and
    under-evidences the ones that do not, so the two curve families run in
    opposite directions — and the family is never fitted, it is read."""
    captured: list = []
    original = color_context._fit_matrix_curves

    def spy(search, validation, config, *, pinned_reference):
        offsets, curves = original(
            search, validation, config, pinned_reference=pinned_reference)
        captured.append((offsets, pinned_reference))
        return offsets, curves

    monkeypatch.setattr(color_context, "_fit_matrix_curves", spy)
    fixture = build_context_fixture(BLEED_BLUR, NOISE, row_id=CMY8_ROW)
    summary, _ = _fit(fixture, CONTEXT_VARIANT_MATRIX, monkeypatch)
    assert summary.adopted
    offsets, pinned = captured[0]
    assert not pinned                                   # cmy8: no reference
    bits = channel.states_to_planes(
        np.arange(8, dtype=np.uint8)).astype(bool)
    checked = 0
    for state in range(8):
        for plane in range(3):
            curve = offsets[state, plane]
            if not np.any(curve):
                continue
            checked += 1
            difference = np.diff(curve)
            if bits[state, plane]:
                assert np.all(difference <= 1e-10), (state, plane)
            else:
                assert np.all(difference >= -1e-10), (state, plane)
    assert checked >= 12


def test_every_fitted_curve_carries_shape_and_never_a_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The identification condition, measured on the curve itself."""
    weights = np.array([1.0, 1.0, 2.0, 2.0, 4.0])
    bins = np.array([0, 1, 4, 4, 8])
    raw = np.array([0.9, 0.7, 0.3, 0.1, -0.2, -0.4, -0.6, -0.8, -1.0])
    anchored = color_neighbourhood.anchor_curve(raw, bins, weights)
    assert float(np.sum(weights * anchored[bins])) == pytest.approx(0.0)
    assert np.all(np.diff(anchored) <= np.diff(raw) + 1e-12)
    assert np.allclose(np.diff(anchored), np.diff(raw))


def test_the_matrix_contains_the_per_plane_form_as_a_special_case() -> None:
    """``f_{s,k} = bit_k(s)·g_k`` is inside the family, not beside it.

    The retired per-plane port fitted ONE curve per plane; the matrix's
    parameter space contains that object exactly — set every state's
    curve for plane k to the same ``g_k`` wherever the state prints k —
    so nothing was lost with the port's fitter.  What the composition
    COSTS is the second half, and it is why the port could not reach
    cmy7 cleanly: shifting the states that print plane k moves THAT
    plane's marginal by exactly the curve (the two logsumexp sides
    separate the shifted states perfectly) and perturbs the SIBLING
    marginals, whose sides each mix shifted and unshifted states.
    """
    curve = np.linspace(0.3, -0.3, 9)
    bits = color_neighbourhood.state_bits(8)
    composed = np.zeros((8, 3, 9))
    applied = np.zeros((8, 3), bool)
    for state in range(8):
        if bits[state, 1]:
            composed[state, 1] = curve
            applied[state, 1] = True
    head = _states_head(composed, applied)
    rng = np.random.default_rng(0x5C5)
    scores = rng.normal(0.0, 2.0, (9, 8))
    bins = np.tile(np.arange(9, dtype=np.int8)[:, None], (1, 3))
    before = color_neighbourhood.plane_marginals(scores)
    after = color_neighbourhood.plane_marginals(head.apply_states(scores, bins))
    assert np.allclose(after[:, 1] - before[:, 1], curve[bins[:, 1]])
    assert not np.allclose(after[:, 0], before[:, 0])
    assert not np.allclose(after[:, 2], before[:, 2])


# ------------------------------------------------- the cross-pathology law
@pytest.mark.parametrize("row_id", (CMY7_ROW, CMY8_ROW))
@pytest.mark.parametrize("variant", (CONTEXT_VARIANT_MATRIX,))
def test_the_clean_channel_refuses_and_the_refusal_is_bit_identical(
    monkeypatch: pytest.MonkeyPatch, variant: str, row_id: str,
) -> None:
    """No bleed, no arm — and no evidence change, for either variant."""
    fixture = build_context_fixture(CLEAN_BLUR, NOISE, row_id=row_id)
    summary, live = _fit(fixture, variant, monkeypatch)
    assert not summary.adopted
    assert summary.reason in (
        CONTEXT_REASON_NO_CURVE, "region_gate_failed")
    assert summary.labels_word > 0 and summary.labels_dust > 0
    assert summary.labels_cert == 0            # no certificates in fixtures
    _null_rows, null = _regions(fixture, CONTEXT_VARIANT_OFF, monkeypatch)
    live_by_patch = _evidence_by_patch(live)
    null_by_patch = _evidence_by_patch(null)
    assert live_by_patch.keys() == null_by_patch.keys()
    for patch_id, values in live_by_patch.items():
        assert np.array_equal(values, null_by_patch[patch_id]), patch_id


@pytest.mark.parametrize("row_id", (CMY7_ROW, CMY8_ROW))
@pytest.mark.parametrize("variant", (CONTEXT_VARIANT_MATRIX,))
def test_the_bleeding_channel_adopts_wins_and_reaches_emission(
    monkeypatch: pytest.MonkeyPatch, variant: str, row_id: str,
) -> None:
    """Same field, same noise, same tone — only the spread differs."""
    fixture = build_context_fixture(BLEED_BLUR, NOISE, row_id=row_id)
    summary, live = _fit(fixture, variant, monkeypatch)
    assert summary.adopted and summary.reason == CONTEXT_REASON_ADOPTED
    assert summary.curves_adopted > 0
    assert summary.candidate_nll < summary.incumbent_nll
    assert summary.word_candidate_nll <= summary.word_incumbent_nll
    assert summary.dust_candidate_nll <= summary.dust_incumbent_nll
    assert summary.binned_fraction > 0.9
    _null_rows, null = _regions(fixture, CONTEXT_VARIANT_OFF, monkeypatch)
    live_by_patch = _evidence_by_patch(live)
    null_by_patch = _evidence_by_patch(null)
    assert all(
        not np.array_equal(values, null_by_patch[patch_id])
        for patch_id, values in live_by_patch.items())


def test_the_cross_plane_channel_is_the_variants_discriminator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Off the diagonal, C's bleed lands in M's channel — a correction
    the retired per-plane form could not write down at all.  The fixture
    pair differs ONLY in the mix, so the arm's behaviour on it is a
    statement about the pathology and not about the render."""
    diagonal = build_context_fixture(
        BLEED_BLUR, NOISE, IDENTITY_MIX, row_id=CMY8_ROW)
    crossed = build_context_fixture(
        BLEED_BLUR, NOISE, CROSS_MIX, row_id=CMY8_ROW)
    assert diagonal.raster.source.sha256 != crossed.raster.source.sha256
    assert np.array_equal(diagonal.field, crossed.field)
    matrix, _ = _fit(crossed, CONTEXT_VARIANT_MATRIX, monkeypatch)
    assert matrix.adopted
    # Recorded, not asserted as a winner: the head-to-head verdict was a
    # certificate count on real captures (COLOR-UPLIFT-MEASUREMENTS §11),
    # never a synthetic fit loss (the l00 lesson).
    assert matrix.candidate_nll < matrix.incumbent_nll


# ------------------------------------------------------------ the nulls
def test_force_null_never_fits_a_context_arm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = build_context_fixture(BLEED_BLUR, NOISE, row_id=CMY8_ROW)
    monkeypatch.setenv(color_stack.FORCE_NULL_ENV, "1")
    rows, _evidence = _regions(fixture, CONTEXT_VARIANT_MATRIX, monkeypatch)
    assert rows[0].context == ContextSummary()
    assert rows[0].context.reason == ""


def test_a_starved_curve_is_exactly_zero_in_ks_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Floors that no real population can clear: every curve refuses with
    K's own word, the region reports it, and nothing is emitted."""
    fixture = build_context_fixture(BLEED_BLUR, NOISE, row_id=CMY8_ROW)
    summary, live = _fit(
        fixture, "matrix:100000,20,40,10", monkeypatch)
    assert summary.reason == "insufficient_search_support"
    assert summary.curves_total == 0 and not summary.adopted
    summary, live = _fit(fixture, "matrix:80,100000,40,10", monkeypatch)
    assert dict(summary.curve_reasons) == {
        CONTEXT_REASON_SEARCH_CLASS: summary.curves_total}
    assert summary.reason == CONTEXT_REASON_NO_CURVE
    _null_rows, null = _regions(fixture, CONTEXT_VARIANT_OFF, monkeypatch)
    null_by_patch = _evidence_by_patch(null)
    for patch_id, values in _evidence_by_patch(live).items():
        assert np.array_equal(values, null_by_patch[patch_id]), patch_id


def test_the_region_summary_defaults_are_append_only(
) -> None:
    """Risk R4: an old caller constructs the summary without A5."""
    row = color_payload.ColorRegionSummary(
        region_id="r", page=0, accepted=True, reason="accepted",
        n_patches=1, n_train=1, n_heldout=1, class_counts=(),
        baseline_heldout_logloss=None, selected_heldout_logloss=None,
        registration_adopted=False,
        residuals=tuple(  # type: ignore[arg-type]
            __import__("holo.receive.color_registration", fromlist=["x"])
            .PlaneResidual((0.0, 0.0), (0.0, 0.0), 0) for _ in range(3)))
    assert row.context == ContextSummary()
    with pytest.raises(TypeError):
        color_payload.ColorRegionSummary(
            region_id="r", page=0, accepted=True, reason="accepted",
            n_patches=1, n_train=1, n_heldout=1, class_counts=(),
            baseline_heldout_logloss=None, selected_heldout_logloss=None,
            registration_adopted=False, residuals=row.residuals,
            context="nope")  # type: ignore[arg-type]
