"""Result-exactness pins for the cold-search FFT-caching rewrite.

RECEIVE-DESIGN 5.3 sanctions caching/batching in the cold search "only
while preserving exact scores, candidate ordering, and acceptance".  The
PLACEMENT-IMPROVEMENTS 2.1-2.3 rewrite replaced the per-map ``z.copy()`` +
second argmax with a winner-only second peak, and the inner ``fftconvolve``
with an explicit rfftn/irfftn product that hoists the kernel transform per
orientation and shares the page-side transform across orientation maps.
Every z map and the complete :class:`SearchOutcome` must remain
bit-identical to the original three-convolution form, reimplemented
privately below from the pre-rewrite source.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.signal import fftconvolve

from holo.receive.placement.model import AttemptBudget, PlacementConfig
from holo.receive.placement.reference import ReferencePage
from holo.receive.placement.search import (
    ScoreMemo,
    SearchOutcome,
    _cold_map_geometries,
    _page_candidate_map,
    _rival_gate,
    correlate_patch,
    hypothesis_count,
    parity_mask,
)

_PAGE_SHAPE = (24, 30)
_BUDGET = AttemptBudget(
    max_hypotheses=1_000_000,
    familywise_false_accept=1e-3,
    max_true_error_rate=0.08,
    qualification_id="cold-search-exactness-fixture",
)


# --- verbatim pre-rewrite reference implementation ------------------------


@dataclass(frozen=True)
class _ReferenceGeometry:
    """Original page-invariant operand set (no cached transforms)."""

    work_sites: np.ndarray
    search_sites: np.ndarray
    soft_kernel: np.ndarray
    weight: np.ndarray
    eligible: np.ndarray
    pad_y: int
    pad_x: int


def _reference_geometries(evidence, mask, sites, budget, *, allow_overhang):
    """Original ``_cold_map_geometries`` (two invariant fftconvolves)."""
    evidence = np.asarray(evidence, np.float32)
    mask = np.asarray(mask, bool)
    sites = np.asarray(sites, bool)
    page_parity = parity_mask(sites.shape, (0, 0), 0)
    base_search_sites = sites & page_parity
    padded_sites: dict = {}
    geometries: list[_ReferenceGeometry | None] = []
    for rot_k in range(4):
        observed = np.rot90(evidence, rot_k)
        keep = np.rot90(mask, rot_k).astype(np.float32)
        pad_y = pad_x = 0
        if allow_overhang:
            pad_y, pad_x = observed.shape[0] - 1, observed.shape[1] - 1
            padding = (pad_y, pad_x)
            prepared = padded_sites.get(padding)
            if prepared is None:
                prepared = (
                    np.pad(sites, ((pad_y, pad_y), (pad_x, pad_x))),
                    np.pad(
                        base_search_sites, ((pad_y, pad_y), (pad_x, pad_x))
                    ),
                )
                padded_sites[padding] = prepared
            work_sites, search_sites = prepared
        elif (
            observed.shape[0] > sites.shape[0]
            or observed.shape[1] > sites.shape[1]
        ):
            geometries.append(None)
            continue
        else:
            work_sites, search_sites = sites, base_search_sites
        soft_kernel = (observed * keep)[::-1, ::-1]
        weight = fftconvolve(
            search_sites.astype(np.float32),
            (np.abs(observed) * keep)[::-1, ::-1],
            mode="valid",
        )
        search_support = np.rint(fftconvolve(
            search_sites.astype(np.float32), keep[::-1, ::-1], mode="valid"
        )).astype(np.int32)
        eligible = (
            search_support >= budget.search_min_support
        ) & (weight > 0.0)
        geometries.append(_ReferenceGeometry(
            work_sites, search_sites, soft_kernel, weight, eligible,
            pad_y, pad_x,
        ))
    return tuple(geometries)


def _reference_map(values, geometry):
    """Original ``_page_candidate_map`` (direct soft fftconvolve)."""
    work_values = np.asarray(values, np.uint8)
    if geometry.pad_y or geometry.pad_x:
        work_values = np.pad(
            work_values,
            (
                (geometry.pad_y, geometry.pad_y),
                (geometry.pad_x, geometry.pad_x),
            ),
        )
    expected_sign = np.where(
        geometry.work_sites,
        1.0 - 2.0 * work_values.astype(np.float32),
        0.0,
    )
    soft_corr = fftconvolve(
        expected_sign * geometry.search_sites,
        geometry.soft_kernel,
        mode="valid",
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        z = soft_corr / np.sqrt(geometry.weight)
    return np.where(geometry.eligible, z, -np.inf)


def _reference_correlate(
    patch, provider, pages, budget, memo, *, sample_key, config
):
    """Original ``correlate_patch`` (every map pays copy + second argmax)."""
    pages = tuple(dict.fromkeys(int(page) for page in pages))
    page_shape = provider.spec.layout.cells_yx
    hypotheses = hypothesis_count(
        patch.mask.shape, page_shape, len(pages),
        allow_overhang=config.allow_overhang,
    )
    if hypotheses > budget.max_hypotheses:
        return SearchOutcome(
            False, None, (), hypotheses, "attempt_budget_exceeded",
            support_floor=budget.min_support,
        )
    raw_maps = []
    first_reference = provider.page(pages[0])
    geometries = _reference_geometries(
        patch.evidence, patch.mask, first_reference.sites, budget,
        allow_overhang=config.allow_overhang,
    )
    for page_index, page in enumerate(pages):
        reference = (
            first_reference if page_index == 0 else provider.page(page)
        )
        for rot_k, geometry in enumerate(geometries):
            if geometry is None:
                continue
            z = _reference_map(reference.values, geometry)
            pad_y, pad_x = geometry.pad_y, geometry.pad_x
            if z.size == 0 or not np.isfinite(z).any():
                continue
            flat = int(np.argmax(z))
            iy, ix = np.unravel_index(flat, z.shape)
            top = (
                float(z[iy, ix]), int(page),
                (int(iy) - pad_y, int(ix) - pad_x), rot_k,
            )
            z_without_peak = z.copy()
            radius = config.neighbor_radius_cells
            z_without_peak[
                max(0, iy - radius):iy + radius + 1,
                max(0, ix - radius):ix + radius + 1,
            ] = -np.inf
            second = None
            if np.isfinite(z_without_peak).any():
                flat_second = int(np.argmax(z_without_peak))
                sy, sx = np.unravel_index(flat_second, z_without_peak.shape)
                second = (
                    float(z_without_peak[sy, sx]), int(page),
                    (int(sy) - pad_y, int(sx) - pad_x), rot_k,
                )
            raw_maps.append((top, second))
    if not raw_maps:
        return SearchOutcome(
            False, None, (), hypotheses, "insufficient_support",
            support_floor=budget.min_support,
        )
    winner_index, winner_map = max(
        enumerate(raw_maps), key=lambda row: row[1][0][0]
    )
    winner_raw = winner_map[0]
    best = memo.candidate(
        sample_key, patch.evidence, patch.bits, patch.mask,
        winner_raw[1], winner_raw[2], winner_raw[3], budget, "correlation",
    )
    runners = []
    seen = {(best.page, best.origin_yx, best.rot_k)}
    rival_rows = []
    for map_index, (top, second) in enumerate(raw_maps):
        if map_index == winner_index:
            if second is not None:
                rival_rows.append(second)
        else:
            rival_rows.append(top)
    for _, page, origin, rot_k in rival_rows:
        identity = (page, origin, rot_k)
        if identity in seen:
            continue
        if (
            page == best.page and rot_k == best.rot_k
            and max(abs(origin[0] - best.origin_yx[0]),
                    abs(origin[1] - best.origin_yx[1]))
            <= config.neighbor_radius_cells
        ):
            continue
        seen.add(identity)
        runners.append(memo.candidate(
            sample_key, patch.evidence, patch.bits, patch.mask,
            page, origin, rot_k, budget, "correlation_runner_up",
        ))
    rival = max(
        runners,
        key=lambda row: (row.soft_z, row.search_mismatch),
        default=None,
    )
    if not best.passes:
        return SearchOutcome(
            False, best, tuple(runners), hypotheses,
            "winner_failed_heldout_gate",
            support_floor=budget.min_support,
            rival=rival,
        )
    rival_mismatch = 1.0 if rival is None else rival.search_mismatch
    accepted = _rival_gate(best.search_mismatch, rival_mismatch, budget.gate)
    return SearchOutcome(
        accepted, best, tuple(runners), hypotheses,
        "accepted" if accepted else "rival_gap_failed",
        support_floor=budget.min_support,
        rival=rival,
    )


# --- synthetic fixtures ---------------------------------------------------


@dataclass
class _Patch:
    """Duck-typed stand-in for the AddressPatch fields the search reads."""

    evidence: np.ndarray
    bits: np.ndarray
    mask: np.ndarray


class _Provider:
    def __init__(self, values_by_page, sites):
        height, width = np.asarray(sites).shape
        self.spec = SimpleNamespace(
            layout=SimpleNamespace(cells_yx=(int(height), int(width)))
        )
        self._pages = {
            page: ReferencePage(page, values, sites)
            for page, values in enumerate(values_by_page)
        }

    def page(self, page):
        return self._pages[int(page)]


def _make_world(seed, page_count=3):
    rng = np.random.default_rng(seed)
    sites = rng.random(_PAGE_SHAPE) < 0.85
    values = [
        rng.integers(0, 2, _PAGE_SHAPE).astype(np.uint8)
        for _ in range(page_count)
    ]
    return rng, sites, values


def _patch_from_bits(rng, bits, mask=None):
    """Evidence follows the E022 sign convention with amplitude jitter."""
    bits = np.ascontiguousarray(bits, np.uint8)
    amplitude = rng.uniform(0.6, 1.0, bits.shape).astype(np.float32)
    evidence = ((1.0 - 2.0 * bits.astype(np.float32)) * amplitude).astype(
        np.float32
    )
    if mask is None:
        mask = np.ones(bits.shape, bool)
    return _Patch(evidence, bits, mask)


def _true_patch(rng, values, origin_yx, crop_shape, rot_k, flip_fraction=0.0):
    """A patch whose rot_k orientation map aligns at ``origin_yx``."""
    oy, ox = origin_yx
    crop = values[oy:oy + crop_shape[0], ox:ox + crop_shape[1]].copy()
    if flip_fraction:
        crop ^= (rng.random(crop.shape) < flip_fraction).astype(np.uint8)
    return _patch_from_bits(rng, np.rot90(crop, -rot_k))


def _overhang_patch(rng, values, embed_yx, frag_shape, rot_k):
    """A fragment strictly larger than the page: true origin is negative."""
    canvas = rng.integers(0, 2, frag_shape).astype(np.uint8)
    ey, ex = embed_yx
    height, width = values.shape
    canvas[ey:ey + height, ex:ex + width] = values
    return _patch_from_bits(rng, np.rot90(canvas, -rot_k))


def _both(patch, provider, pages, config, sample_key=11):
    new = correlate_patch(
        patch, provider, pages, _BUDGET, ScoreMemo(provider),
        sample_key=sample_key, config=config,
    )
    old = _reference_correlate(
        patch, provider, pages, _BUDGET, ScoreMemo(provider),
        sample_key=sample_key, config=config,
    )
    return new, old


# --- (a) z maps bit-for-bit ----------------------------------------------


@pytest.mark.parametrize(
    "frag_shape,allow_overhang",
    [
        ((14, 14), True),     # square, overhang padding
        ((14, 18), True),     # non-square: two padding groups
        ((34, 38), True),     # fragment strictly larger than the page
        ((14, 14), False),    # no padding
        ((10, 26), False),    # rot 1/3 exceed the page: None geometries
    ],
)
def test_z_maps_bit_identical(frag_shape, allow_overhang):
    rng, sites, values = _make_world(seed=7)
    provider = _Provider(values, sites)
    bits = rng.integers(0, 2, frag_shape).astype(np.uint8)
    mask = rng.random(frag_shape) < 0.95
    patch = _patch_from_bits(rng, bits, mask)
    new_geometries = _cold_map_geometries(
        patch.evidence, patch.mask, sites, _BUDGET,
        allow_overhang=allow_overhang,
    )
    old_geometries = _reference_geometries(
        patch.evidence, patch.mask, sites, _BUDGET,
        allow_overhang=allow_overhang,
    )
    transforms: dict = {}
    compared = 0
    for rot_k in range(4):
        new_geometry = new_geometries[rot_k]
        old_geometry = old_geometries[rot_k]
        assert (new_geometry is None) == (old_geometry is None)
        if new_geometry is None:
            continue
        assert new_geometry.weight.dtype == old_geometry.weight.dtype
        assert np.array_equal(new_geometry.weight, old_geometry.weight)
        assert np.array_equal(new_geometry.eligible, old_geometry.eligible)
        for page in range(len(values)):
            z_new = _page_candidate_map(
                provider.page(page).values, new_geometry, page, transforms
            )
            z_old = _reference_map(provider.page(page).values, old_geometry)
            assert z_new.dtype == z_old.dtype
            assert z_new.shape == z_old.shape
            assert np.array_equal(z_new, z_old)
            compared += 1
    assert compared > 0
    # The page-side transform must actually be shared across orientation
    # maps: strictly fewer cached transforms than maps computed.
    assert 0 < len(transforms) < compared


# --- (b) SearchOutcome identical ------------------------------------------


@pytest.mark.parametrize("rot_k", [0, 1, 2, 3])
def test_accepted_outcome_identical_each_rotation(rot_k):
    rng, sites, values = _make_world(seed=17)
    provider = _Provider(values, sites)
    patch = _true_patch(
        rng, values[1], (4, 8), (16, 16), rot_k, flip_fraction=0.04
    )
    new, old = _both(patch, provider, (0, 1, 2), PlacementConfig())
    assert new == old
    assert new.accepted and new.reason == "accepted"
    assert new.best is not None
    assert (new.best.page, new.best.origin_yx, new.best.rot_k) == (
        1, (4, 8), rot_k
    )


def test_exact_tie_tops_keep_first_page_winner():
    """Duplicated pages force exact-tie map tops; first page must win."""
    rng, sites, values = _make_world(seed=23)
    values[1] = values[0].copy()
    provider = _Provider(values, sites)
    patch = _true_patch(rng, values[0], (5, 7), (14, 14), 0)
    new, old = _both(patch, provider, (0, 1, 2), PlacementConfig())
    assert new == old
    assert new.best is not None and new.best.page == 0
    # The identical page-1 placement is the rival: decoy bar refuses it.
    assert new.rival is not None and new.rival.page == 1
    assert not new.accepted and new.reason == "rival_gap_failed"


def test_winner_second_peak_from_duplicated_motif():
    """An in-page duplicate makes the winning map's second peak decisive."""
    rng, sites, values = _make_world(seed=31)
    values[0][6:18, 3:15] = values[0][6:18, 17:29]
    provider = _Provider(values, sites)
    patch = _true_patch(rng, values[0], (6, 17), (12, 12), 0)
    new, old = _both(patch, provider, (0, 1, 2), PlacementConfig())
    assert new == old
    assert new.best is not None and new.best.page == 0
    assert new.rival is not None
    assert new.rival.origin_yx in ((6, 3), (6, 17))
    assert not new.accepted and new.reason == "rival_gap_failed"


def test_map_empty_insufficient_support_identical():
    """A fragment below the parity floor leaves every map empty."""
    rng, sites, values = _make_world(seed=41)
    provider = _Provider(values, sites)
    patch = _true_patch(rng, values[0], (3, 3), (6, 6), 0)
    new, old = _both(patch, provider, (0, 1, 2), PlacementConfig())
    assert new == old
    assert not new.accepted and new.best is None
    assert new.reason == "insufficient_support"


def test_overhang_fragment_larger_than_page_identical():
    rng, sites, values = _make_world(seed=47)
    provider = _Provider(values, sites)
    patch = _overhang_patch(rng, values[2], (5, 4), (34, 38), 2)
    new, old = _both(patch, provider, (0, 1, 2), PlacementConfig())
    assert new == old
    assert new.accepted
    assert new.best is not None
    assert (new.best.page, new.best.origin_yx, new.best.rot_k) == (
        2, (-5, -4), 2
    )


def test_non_overhang_skipped_orientations_identical():
    rng, sites, values = _make_world(seed=53)
    provider = _Provider(values, sites)
    patch = _true_patch(
        rng, values[0], (7, 2), (10, 26), 0, flip_fraction=0.03
    )
    config = PlacementConfig(allow_overhang=False)
    new, old = _both(patch, provider, (0, 1, 2), config)
    assert new == old
    assert new.accepted
    assert new.best is not None
    assert (new.best.page, new.best.origin_yx, new.best.rot_k) == (
        0, (7, 2), 0
    )


def test_cold_progress_callback_bounded_and_outcome_neutral():
    """v0.33 D14c: the optional page-progress heartbeat is count-bounded
    (<= 64 invocations per sweep, one every ceil(P/64) pages) and adds no
    numerical work — the SearchOutcome is identical with and without it."""
    rng, sites, values = _make_world(seed=17, page_count=200)
    provider = _Provider(values, sites)
    patch = _true_patch(
        rng, values[1], (4, 8), (16, 16), 0, flip_fraction=0.04
    )
    budget = AttemptBudget(
        max_hypotheses=100_000_000,
        familywise_false_accept=1e-3,
        max_true_error_rate=0.08,
        qualification_id="cold-progress-bounding-fixture",
    )
    calls: list[tuple[int, int]] = []
    observed = correlate_patch(
        patch, provider, tuple(range(200)), budget, ScoreMemo(provider),
        sample_key=11, config=PlacementConfig(),
        page_progress=lambda ordinal, total: calls.append((ordinal, total)),
    )
    silent = correlate_patch(
        patch, provider, tuple(range(200)), budget, ScoreMemo(provider),
        sample_key=11, config=PlacementConfig(),
    )
    assert observed == silent
    assert observed.best is not None and observed.best.page == 1
    stride = -(-200 // 64)
    assert calls == [(page + 1, 200) for page in range(0, 200, stride)]
    assert len(calls) <= 64

    # The bound holds pointwise around the 64-page knee.
    for count in (1, 63, 64, 65, 128):
        calls.clear()
        correlate_patch(
            patch, provider, tuple(range(count)), budget,
            ScoreMemo(provider), sample_key=11, config=PlacementConfig(),
            page_progress=lambda ordinal, total: calls.append(
                (ordinal, total)),
        )
        stride = -(-count // 64)
        assert len(calls) == -(-count // stride), count
        assert len(calls) <= 64, count
        assert all(total == count for _ordinal, total in calls)


def test_unrelated_fragment_fails_heldout_gate_identically():
    rng, sites, values = _make_world(seed=59)
    provider = _Provider(values, sites)
    bits = rng.integers(0, 2, (14, 14)).astype(np.uint8)
    patch = _patch_from_bits(rng, bits)
    new, old = _both(patch, provider, (0, 1, 2), PlacementConfig())
    assert new == old
    assert not new.accepted
    assert new.reason == "winner_failed_heldout_gate"
