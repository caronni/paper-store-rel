"""The cold-search exactness contract, pinned inside holo2's own tree.

W0 sub-wave A2 (H4-PLAN §3-W0).  ``solve/cold.py`` is a REFACTORED port
of v1's cold correlation (R4: the code is free, the arithmetic is not),
and the cached-transform path there reproduces
``scipy.signal.fftconvolve`` bit for bit.  These are the pins the
refactoring may not move:

* the padded shape (``next_fast_len``) and the valid slice, checked
  against a DIRECT ``fftconvolve`` on hand-sized fixtures;
* the degenerate ``<2``-cell-axis fallback, which must take the direct
  call and leave the transform cache untouched;
* ``np.rint(...).astype(np.int32)`` for the search support, checked
  against an exact integer correlation at the support floor — the
  boundary a truncation would move;
* the strict-``>`` tie-break, which reproduces ``max``'s first-on-tie
  choice in CALLER-page order and then orientation order;
* the page-invariance refusal the transform cache's site-free key
  stands on;
* the result-exact early-out, which must not touch the provider or the
  scorer once eligibility is empty.

The scorer is a TEST DOUBLE standing in for ``pose_audit``'s
``ScoreMemo`` (another W0-A2 target): it implements v1's parity score
faithfully so the outcome reasons mean what they say.  W0-B reconciled
``correlate_patch`` itself onto the real ``ScoreMemo``/``AddressPatch``/
``ReferenceFieldProvider`` types, but kept this file's own double rather
than importing ``ScoreMemo`` here — the double lets this exactness
contract stand on its own, independent of ``pose_audit``'s test suite.
The cross-tree differential against ``src/holo``'s own
``correlate_patch`` is a scratch instrument, not a committed test — the
firewall keeps ``holo`` imports out of this tree.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pytest
from scipy.fft import next_fast_len
from scipy.signal import fftconvolve

from holo2.solve.cold import (
    WHOLE_WORD_PARITY, PageTransforms, SearchOutcome, _cold_map_geometries,
    _ColdMapGeometry, _page_candidate_map, _rival_gate,
    _signed_search_field, correlate_patch)
from holo2.solve.place_model import (
    AttemptBudget, CandidateScore, PlacementConfig)
from holo2.solve.pose_audit import parity_mask

# max_hypotheses 100,000 -> identifiability floor 28, so min_support is
# E022's carried 30 (place_model's max(...) picks the larger).
BUDGET = AttemptBudget(
    max_hypotheses=100_000,
    familywise_false_accept=1e-3,
    max_true_error_rate=0.08,
    qualification_id="holo2/w0-a2/cold-exactness-fixture",
)
PAGE_SHAPE = (24, 30)


# ------------------------------------------------------------- the doubles

@dataclass(frozen=True)
class _Page:
    values: np.ndarray
    sites: np.ndarray


@dataclass(frozen=True)
class _Spec:
    """The one member ``correlate_patch`` reads off ``provider.spec``."""

    cells_yx: tuple[int, int]


class _Provider:
    """Minimal :class:`~holo2.solve.reference.ReferenceFieldProvider`."""

    def __init__(self, values_by_page: list[np.ndarray],
                 sites_by_page: list[np.ndarray]) -> None:
        self._pages = [_Page(values, sites) for values, sites
                       in zip(values_by_page, sites_by_page, strict=True)]
        self.page_calls = 0
        shape = self._pages[0].values.shape
        self.spec = _Spec((int(shape[0]), int(shape[1])))

    def page(self, page: int) -> _Page:
        self.page_calls += 1
        return self._pages[int(page)]


def _overlap_slices(origin_yx, fragment_shape, page_shape):
    """Clip a possibly overhanging rotated fragment against a page."""
    origin_y, origin_x = origin_yx
    height, width = page_shape
    frag_height, frag_width = fragment_shape
    page_y0, page_x0 = max(0, origin_y), max(0, origin_x)
    page_y1, page_x1 = (min(height, origin_y + frag_height),
                        min(width, origin_x + frag_width))
    if page_y0 >= page_y1 or page_x0 >= page_x1:
        return None
    return (slice(page_y0, page_y1), slice(page_x0, page_x1),
            slice(page_y0 - origin_y, page_y1 - origin_y),
            slice(page_x0 - origin_x, page_x1 - origin_x))


class _Scorer:
    """Test double for pose_audit's ``ScoreMemo`` (v1's parity score)."""

    def __init__(self, provider: _Provider) -> None:
        self.provider = provider
        self.parity_calls = 0
        self.candidate_calls = 0

    def parity_score(self, sample_key, evidence, bits, mask, page,
                     origin_yx, rot_k, parity):
        self.parity_calls += 1
        reference = self.provider._pages[int(page)]
        observed = np.rot90(np.asarray(evidence, np.float32), rot_k)
        hard = np.rot90(np.asarray(bits, np.uint8), rot_k)
        keep = np.rot90(np.asarray(mask, bool), rot_k)
        slices = _overlap_slices(
            origin_yx, observed.shape, reference.values.shape)
        if slices is None:
            return (1.0, 0, 0, -np.inf)
        page_y, page_x, frag_y, frag_x = slices
        selected = reference.sites[page_y, page_x] & keep[frag_y, frag_x]
        if parity != WHOLE_WORD_PARITY:
            selected = selected & parity_mask(
                selected.shape,
                (int(page_y.start or 0), int(page_x.start or 0)), parity)
        support = int(selected.sum())
        if support == 0:
            return (1.0, 0, 0, -np.inf)
        expected_bits = reference.values[page_y, page_x][selected]
        observed_evidence = observed[frag_y, frag_x][selected]
        expected_sign = 1.0 - 2.0 * expected_bits.astype(np.float32)
        total_weight = float(np.abs(observed_evidence).sum())
        correlation = float(np.sum(expected_sign * observed_evidence))
        mismatch = ((total_weight - correlation) / (2.0 * total_weight)
                    if total_weight > 0.0 else 1.0)
        errors = int(np.count_nonzero(
            hard[frag_y, frag_x][selected] != expected_bits))
        return (float(mismatch), errors, support,
                float(correlation / np.sqrt(max(total_weight, 1e-9))))

    def candidate(self, sample_key, evidence, bits, mask, page, origin_yx,
                  rot_k, budget, route):
        self.candidate_calls += 1
        search = self.parity_score(
            sample_key, evidence, bits, mask, page, origin_yx, rot_k, 0)
        validation = self.parity_score(
            sample_key, evidence, bits, mask, page, origin_yx, rot_k, 1)
        passes = (search[2] >= budget.min_support
                  and validation[2] >= budget.min_support
                  and search[0] < budget.gate.search_true
                  and validation[0] < budget.gate.validation_true)
        return CandidateScore(
            int(page), (int(origin_yx[0]), int(origin_yx[1])),
            int(rot_k) % 4, search[0], validation[0], search[1],
            validation[1], search[2], validation[2], search[3], passes,
            route)


@dataclass(frozen=True)
class _Patch:
    evidence: np.ndarray
    bits: np.ndarray
    mask: np.ndarray


def _patch_from_bits(rng, bits, mask=None):
    """Evidence follows the E022 sign convention with amplitude jitter."""
    bits = np.ascontiguousarray(bits, np.uint8)
    amplitude = rng.uniform(0.6, 1.0, bits.shape).astype(np.float32)
    evidence = ((1.0 - 2.0 * bits.astype(np.float32))
                * amplitude).astype(np.float32)
    return _Patch(evidence, bits,
                  np.ones(bits.shape, bool) if mask is None else mask)


def _world(seed, page_count=3, shape=PAGE_SHAPE, density=0.85):
    rng = np.random.default_rng(seed)
    sites = rng.random(shape) < density
    values = [rng.integers(0, 2, shape).astype(np.uint8)
              for _ in range(page_count)]
    return rng, sites, values


def _provider(values, sites):
    return _Provider(values, [sites] * len(values))


def _true_patch(rng, values, origin_yx, crop_shape, rot_k, flips=0.0):
    """A patch whose ``rot_k`` orientation map aligns at ``origin_yx``."""
    oy, ox = origin_yx
    crop = values[oy:oy + crop_shape[0], ox:ox + crop_shape[1]].copy()
    if flips:
        crop ^= (rng.random(crop.shape) < flips).astype(np.uint8)
    return _patch_from_bits(rng, np.rot90(crop, -rot_k))


def _forced_eligible(geometry: _ColdMapGeometry) -> _ColdMapGeometry:
    """The same geometry with only the support floor lifted.

    ``weight > 0`` stays, so the ``-inf`` fill still covers the origins
    whose z would be a division by zero; what goes is the site-count
    floor, which on a hand-sized fixture would refuse every origin and
    make a map comparison vacuous.
    """
    return replace(geometry, eligible=geometry.weight > 0.0)


def _same(left: np.ndarray, right: np.ndarray) -> bool:
    return (left.dtype == right.dtype and left.shape == right.shape
            and bool(np.array_equal(left, right)))


# ------------------------------------- the padded shape and the valid slice

def test_fshape_is_next_fast_len_of_the_full_linear_size() -> None:
    """A hand fixture: 8x9 page, 3x4 fragment, no overhang."""
    rng = np.random.default_rng(3)
    sites = np.ones((8, 9), bool)
    patch = _patch_from_bits(rng, rng.integers(0, 2, (3, 4)))
    geometries = _cold_map_geometries(
        patch.evidence, patch.mask, sites, BUDGET, allow_overhang=False)
    geometry = geometries[0]
    assert geometry is not None
    # search_sites is the 8x9 parity plane, soft_kernel the 3x4 reversed
    # fragment: full linear sizes 8+3-1 = 10 and 9+4-1 = 12.
    assert geometry.search_sites.shape == (8, 9)
    assert geometry.soft_kernel.shape == (3, 4)
    assert geometry.fshape == (next_fast_len(10, True), next_fast_len(12, True))
    assert geometry.fshape == (10, 12)
    # The valid slice full[kh-1:h, kw-1:w] has fftconvolve's own extent.
    z = _page_candidate_map(
        np.zeros((8, 9), np.uint8), geometry, 0, {})
    assert z.shape == (8 - 3 + 1, 9 - 4 + 1)


@pytest.mark.parametrize("frag_shape,allow_overhang", [
    ((3, 4), False),        # hand-sized, no padding
    ((3, 4), True),         # hand-sized, overhang padding
    ((4, 4), True),         # square: one padding group for all four
    ((12, 12), True),       # realistic window, overhang
    ((12, 16), False),      # rot 1/3 exceed the page -> None geometries
])
def test_cached_transform_matches_a_direct_fftconvolve(
        frag_shape, allow_overhang) -> None:
    """The exactness contract itself: cached product == direct call."""
    rng, sites, values = _world(seed=7)
    patch = _patch_from_bits(
        rng, rng.integers(0, 2, frag_shape),
        mask=rng.random(frag_shape) < 0.95)
    geometries = _cold_map_geometries(
        patch.evidence, patch.mask, sites, BUDGET,
        allow_overhang=allow_overhang)
    transforms: PageTransforms = {}
    compared = 0
    for geometry in geometries:
        if geometry is None:
            continue
        geometry = _forced_eligible(geometry)
        for page, page_values in enumerate(values):
            direct = fftconvolve(
                _signed_search_field(page_values, geometry),
                geometry.soft_kernel, mode="valid")
            with np.errstate(divide="ignore", invalid="ignore"):
                expected = np.where(
                    geometry.eligible, direct / np.sqrt(geometry.weight),
                    -np.inf)
            observed = _page_candidate_map(
                page_values, geometry, page, transforms)
            assert _same(observed, expected)
            assert observed.dtype == np.float32
            compared += 1
    assert compared > 0
    if any(g is not None and g.kernel_rfft is not None for g in geometries):
        # The page-side transform is shared across orientation maps of
        # equal padding: strictly fewer cached transforms than maps.
        assert 0 < len(transforms) < compared


@pytest.mark.parametrize("frag_shape", [(1, 4), (4, 1), (1, 1)])
def test_degenerate_axis_takes_the_direct_fallback(frag_shape) -> None:
    """<2-cell axes keep fftconvolve's broadcast case and cache nothing."""
    rng = np.random.default_rng(11)
    sites = np.ones((8, 9), bool)
    values = rng.integers(0, 2, (8, 9)).astype(np.uint8)
    patch = _patch_from_bits(rng, rng.integers(0, 2, frag_shape))
    geometries = _cold_map_geometries(
        patch.evidence, patch.mask, sites, BUDGET, allow_overhang=True)
    transforms: PageTransforms = {}
    for geometry in geometries:
        assert geometry is not None
        assert geometry.kernel_rfft is None
        geometry = _forced_eligible(geometry)
        direct = fftconvolve(
            _signed_search_field(values, geometry), geometry.soft_kernel,
            mode="valid")
        with np.errstate(divide="ignore", invalid="ignore"):
            expected = np.where(
                geometry.eligible, direct / np.sqrt(geometry.weight),
                -np.inf)
        assert _same(
            _page_candidate_map(values, geometry, 0, transforms), expected)
    assert transforms == {}


def test_a_two_cell_axis_is_not_degenerate() -> None:
    """The floor is ``min(shape) >= 2`` on BOTH operands, not a heuristic."""
    rng = np.random.default_rng(13)
    sites = np.ones((8, 9), bool)
    patch = _patch_from_bits(rng, rng.integers(0, 2, (2, 4)))
    geometries = _cold_map_geometries(
        patch.evidence, patch.mask, sites, BUDGET, allow_overhang=False)
    assert all(g is not None and g.kernel_rfft is not None
               for g in geometries)


# ----------------------------------------------------- the support rounding

def test_search_support_is_rint_not_truncation() -> None:
    """``np.rint`` at the floor: FFT support carries float error.

    The eligibility map must equal the EXACT integer site count rule.
    The same map built by truncating the convolution would differ, and
    the fixture proves the difference is real by exhibiting it.
    """
    rng, sites, _values = _world(seed=19, density=0.92)
    patch = _patch_from_bits(rng, rng.integers(0, 2, (8, 8)))
    geometries = _cold_map_geometries(
        patch.evidence, patch.mask, sites, BUDGET, allow_overhang=False)
    geometry = geometries[0]
    assert geometry is not None
    keep = np.asarray(patch.mask, bool)
    raw = fftconvolve(geometry.search_sites.astype(np.float32),
                      keep[::-1, ::-1].astype(np.float32), mode="valid")
    exact = np.zeros(raw.shape, np.int64)
    for oy in range(raw.shape[0]):
        for ox in range(raw.shape[1]):
            window = geometry.search_sites[oy:oy + 8, ox:ox + 8]
            exact[oy, ox] = int(np.count_nonzero(window & keep))
    assert np.array_equal(np.rint(raw).astype(np.int32), exact)
    assert BUDGET.min_support == 30
    assert np.array_equal(
        geometry.eligible, (exact >= 30) & (geometry.weight > 0.0))
    # The floor is actually straddled, and truncation would move it.
    assert bool((exact == 30).any()) and bool((exact < 30).any())
    assert not np.array_equal(np.floor(raw).astype(np.int32), exact)
    assert not np.array_equal(
        geometry.eligible, (np.floor(raw) >= 30) & (geometry.weight > 0.0))


# ---------------------------------------------------------- the tie-breaks

def test_exact_tie_keeps_the_first_page_in_CALLER_order() -> None:
    """Duplicated pages tie exactly; the caller's order decides."""
    rng, sites, values = _world(seed=23)
    values[2] = values[0].copy()
    provider = _provider(values, sites)
    patch = _true_patch(rng, values[0], (4, 8), (16, 16), 0)
    outcome = correlate_patch(
        patch, provider, (2, 0, 1), BUDGET, _Scorer(provider),
        sample_key=11, config=PlacementConfig())
    assert outcome.best is not None
    assert (outcome.best.page, outcome.best.origin_yx) == (2, (4, 8))
    # The identical page-0 placement is the rival the decoy bar refuses.
    assert outcome.rival is not None and outcome.rival.page == 0
    assert not outcome.accepted and outcome.reason == "rival_gap_failed"


def test_exact_tie_keeps_the_first_orientation() -> None:
    """A rot180-symmetric patch ties rot 0 against rot 2; 0 wins."""
    rng, sites, values = _world(seed=29)
    raw = rng.integers(0, 2, (16, 16)).astype(np.uint8)
    bits = raw | np.rot90(raw, 2)
    patch = _patch_from_bits(rng, bits)
    patch = _Patch(
        (patch.evidence + np.rot90(patch.evidence, 2)) / np.float32(2.0),
        patch.bits, patch.mask)
    assert np.array_equal(patch.evidence, np.rot90(patch.evidence, 2))
    provider = _provider(values, sites)
    outcome = correlate_patch(
        patch, provider, (0, 1, 2), BUDGET, _Scorer(provider),
        sample_key=11, config=PlacementConfig())
    assert outcome.best is not None and outcome.best.rot_k == 0
    assert outcome.rival is not None and outcome.rival.rot_k == 2
    assert outcome.rival.origin_yx == outcome.best.origin_yx


# ------------------------------------------------- the page-invariance rule

def test_page_variant_sites_refuse_loudly() -> None:
    """The transform key carries no site identity, so this must raise."""
    rng, sites, values = _world(seed=31)
    other = sites.copy()
    other[0, 0] = not other[0, 0]
    provider = _Provider(values, [sites, other, sites])
    patch = _true_patch(rng, values[0], (4, 8), (16, 16), 0)
    with pytest.raises(ValueError, match="page-invariant"):
        correlate_patch(
            patch, provider, (0, 1, 2), BUDGET, _Scorer(provider),
            sample_key=11, config=PlacementConfig())


def test_an_equal_but_distinct_site_array_is_accepted() -> None:
    """Page-invariance is a VALUE rule; identity is only the fast path."""
    rng, sites, values = _world(seed=37)
    provider = _Provider(values, [sites, sites.copy(), sites.copy()])
    patch = _true_patch(rng, values[1], (4, 8), (16, 16), 0, flips=0.04)
    outcome = correlate_patch(
        patch, provider, (0, 1, 2), BUDGET, _Scorer(provider),
        sample_key=11, config=PlacementConfig())
    assert outcome.accepted and outcome.best is not None
    assert (outcome.best.page, outcome.best.origin_yx) == (1, (4, 8))


# ------------------------------------------------------------ the early-out

def test_result_exact_early_out_touches_nothing() -> None:
    """No eligible origin anywhere: refuse before the first page map."""
    rng, sites, values = _world(seed=41)
    provider = _provider(values, sites)
    patch = _true_patch(rng, values[0], (3, 3), (6, 6), 0)
    scorer = _Scorer(provider)
    outcome = correlate_patch(
        patch, provider, (0, 1, 2), BUDGET, scorer,
        sample_key=11, config=PlacementConfig())
    assert outcome == SearchOutcome(
        False, None, (), outcome.hypotheses, "insufficient_support",
        support_floor=BUDGET.min_support)
    # One provider read (the geometries' page), and no scoring at all.
    assert provider.page_calls == 1
    assert (scorer.parity_calls, scorer.candidate_calls) == (0, 0)


def test_attempt_budget_refuses_before_searching() -> None:
    rng, sites, values = _world(seed=43)
    provider = _provider(values, sites)
    patch = _true_patch(rng, values[0], (4, 8), (16, 16), 0)
    budget = replace(BUDGET, max_hypotheses=1_000)
    outcome = correlate_patch(
        patch, provider, (0, 1, 2), budget, _Scorer(provider),
        sample_key=11, config=PlacementConfig())
    assert not outcome.accepted and outcome.best is None
    assert outcome.reason == "attempt_budget_exceeded"
    assert outcome.hypotheses > budget.max_hypotheses
    assert provider.page_calls == 0


# ------------------------------------------------------- the page domain

def test_page_domain_validation() -> None:
    rng, sites, values = _world(seed=47)
    provider = _provider(values, sites)
    patch = _true_patch(rng, values[0], (4, 8), (16, 16), 0)
    scorer = _Scorer(provider)

    def run(pages):
        return correlate_patch(
            patch, provider, pages, BUDGET, scorer, sample_key=11,
            config=PlacementConfig())

    for bad in ((True,), (np.True_,), (1.0,), ("0",)):
        with pytest.raises(TypeError, match="page hypotheses"):
            run(bad)
    with pytest.raises(ValueError, match="at least one"):
        run(())
    # Duplicates collapse in first-seen order: the domain is two pages.
    assert run((1, 1, 0)).hypotheses == run((1, 0)).hypotheses
    assert run((1, 1, 0)).hypotheses == 2 * run((1,)).hypotheses


# -------------------------------------------------------- the whole search

@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_accepted_at_every_orientation(rot_k) -> None:
    rng, sites, values = _world(seed=53)
    provider = _provider(values, sites)
    patch = _true_patch(rng, values[1], (4, 8), (16, 16), rot_k, flips=0.04)
    outcome = correlate_patch(
        patch, provider, (0, 1, 2), BUDGET, _Scorer(provider),
        sample_key=11, config=PlacementConfig())
    assert outcome.accepted and outcome.reason == "accepted"
    assert outcome.best is not None
    assert (outcome.best.page, outcome.best.origin_yx,
            outcome.best.rot_k) == (1, (4, 8), rot_k)
    assert outcome.support_floor == BUDGET.min_support


def test_overhanging_fragment_places_at_a_negative_origin() -> None:
    rng, sites, values = _world(seed=59)
    provider = _provider(values, sites)
    canvas = rng.integers(0, 2, (34, 38)).astype(np.uint8)
    canvas[5:5 + PAGE_SHAPE[0], 4:4 + PAGE_SHAPE[1]] = values[2]
    patch = _patch_from_bits(rng, np.rot90(canvas, -2))
    outcome = correlate_patch(
        patch, provider, (0, 1, 2), BUDGET, _Scorer(provider),
        sample_key=11, config=PlacementConfig())
    assert outcome.accepted and outcome.best is not None
    assert (outcome.best.page, outcome.best.origin_yx,
            outcome.best.rot_k) == (2, (-5, -4), 2)


def test_oversized_orientations_are_skipped_without_overhang() -> None:
    rng, sites, values = _world(seed=61)
    provider = _provider(values, sites)
    patch = _true_patch(rng, values[0], (7, 2), (10, 26), 0, flips=0.03)
    config = PlacementConfig(allow_overhang=False)
    geometries = _cold_map_geometries(
        patch.evidence, patch.mask, sites, BUDGET, allow_overhang=False)
    assert [g is None for g in geometries] == [False, True, False, True]
    outcome = correlate_patch(
        patch, provider, (0, 1, 2), BUDGET, _Scorer(provider),
        sample_key=11, config=config)
    assert outcome.accepted and outcome.best is not None
    assert (outcome.best.page, outcome.best.origin_yx,
            outcome.best.rot_k) == (0, (7, 2), 0)


def test_unrelated_fragment_fails_the_heldout_gate() -> None:
    rng, sites, values = _world(seed=67)
    provider = _provider(values, sites)
    patch = _patch_from_bits(rng, rng.integers(0, 2, (16, 16)))
    outcome = correlate_patch(
        patch, provider, (0, 1, 2), BUDGET, _Scorer(provider),
        sample_key=11, config=PlacementConfig())
    assert not outcome.accepted
    assert outcome.reason == "winner_failed_heldout_gate"
    assert outcome.best is not None and not outcome.best.passes


def test_winner_second_peak_is_the_rival() -> None:
    """An in-page duplicate motif makes the winning map's second peak win."""
    rng, sites, values = _world(seed=71)
    values[0][2:18, 2:18] = values[0][6:22, 12:28]
    provider = _provider(values, sites)
    patch = _true_patch(rng, values[0], (6, 12), (16, 16), 0)
    outcome = correlate_patch(
        patch, provider, (0, 1, 2), BUDGET, _Scorer(provider),
        sample_key=11, config=PlacementConfig())
    assert outcome.best is not None and outcome.best.page == 0
    assert outcome.rival is not None and outcome.rival.page == 0
    assert {outcome.best.origin_yx, outcome.rival.origin_yx} == {
        (2, 2), (6, 12)}
    assert not outcome.accepted and outcome.reason == "rival_gap_failed"


# ---------------------------------------------------------- the heartbeat

def _wide_world(pages):
    rng = np.random.default_rng(73)
    sites = np.ones((20, 20), bool)
    values = [rng.integers(0, 2, (20, 20)).astype(np.uint8)
              for _ in range(pages)]
    patch = _true_patch(rng, values[0], (5, 5), (10, 10), 0)
    provider = _provider(values, sites)
    budget = replace(BUDGET, max_hypotheses=100_000_000)
    return patch, provider, budget


def test_progress_is_count_bounded_and_outcome_neutral() -> None:
    patch, provider, budget = _wide_world(130)
    calls: list[tuple[int, int]] = []
    observed = correlate_patch(
        patch, provider, tuple(range(130)), budget, _Scorer(provider),
        sample_key=11, config=PlacementConfig(),
        page_progress=lambda ordinal, total: calls.append((ordinal, total)))
    silent = correlate_patch(
        patch, provider, tuple(range(130)), budget, _Scorer(provider),
        sample_key=11, config=PlacementConfig())
    assert observed == silent
    stride = -(-130 // 64)
    assert calls == [(page + 1, 130) for page in range(0, 130, stride)]
    assert len(calls) <= 64


@pytest.mark.parametrize("count", [1, 63, 64, 65])
def test_progress_bound_holds_around_the_knee(count) -> None:
    patch, provider, budget = _wide_world(count)
    calls: list[tuple[int, int]] = []
    correlate_patch(
        patch, provider, tuple(range(count)), budget, _Scorer(provider),
        sample_key=11, config=PlacementConfig(),
        page_progress=lambda ordinal, total: calls.append((ordinal, total)))
    stride = -(-count // 64)
    assert len(calls) == -(-count // stride) <= 64
    assert all(total == count for _ordinal, total in calls)


# ---------------------------------------------------------- the rival bar

def test_rival_gate_bars_are_strict_decoy_inclusive_gap() -> None:
    gate = BUDGET.gate
    assert gate.rival_decoy == 0.20 and gate.minimum_gap == 0.08
    # Decoy bar is STRICT: a rival exactly at the bar is no decoy.
    assert not _rival_gate(0.0, gate.rival_decoy, gate)
    assert _rival_gate(0.0, gate.rival_decoy + 1e-9, gate)
    # Gap is INCLUSIVE: exactly the minimum gap qualifies.  The boundary
    # is asked on binary-exact bars, so what it pins is the rule and not
    # the rounding of a decimal literal (0.22 - 0.08 != 0.14 in float64).
    exact = replace(gate, rival_decoy=0.25, minimum_gap=0.0625)
    assert _rival_gate(0.4375, 0.5, exact)
    assert not _rival_gate(float(np.nextafter(0.4375, 1.0)), 0.5, exact)


def test_the_whole_word_parity_sentinel_is_the_third_class() -> None:
    """0 and 1 are the split; 2 means every overlap site."""
    assert WHOLE_WORD_PARITY == 2
    mask = parity_mask((6, 6), (0, 0), 0)
    assert np.array_equal(mask, ~parity_mask((6, 6), (0, 0), 1))
    assert not parity_mask((6, 6), (0, 0), WHOLE_WORD_PARITY).any()
