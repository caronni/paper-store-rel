"""Parity-split Lane-C correlation, propagation, audit, and observations."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

import numpy as np
from scipy import ndimage
from scipy.fft import irfftn, next_fast_len, rfftn, set_workers
from scipy.signal import fftconvolve

from ...format import pilots
from .. import _parallel
from .geometry import (
    AddressPatch,
    RegionContext,
    SegmentSample,
    pose_metrics,
    sample_segment,
)
from .model import (
    AffinePose,
    AttemptBudget,
    CandidateScore,
    HISTORICAL_E022_GATE,
    HISTORICAL_MIN_SUPPORT,
    PilotObservation,
    PlacementGate,
    PlacementConfig,
)
from .reference import (
    ReferenceFieldProvider,
    overlap_slices,
    rotation_affine,
)


WHOLE_WORD_PARITY = 2
"""``parity_score`` sentinel: score ALL overlap sites, both parity classes.

v0.30 whole-word rival evaluation.  The d=27 address-code floor binds full
words; the parity split can concentrate a cross-page alias's difference
codeword into as few as 7 of 45 search-class bits (measured family floor
0.156 — docs/FULL-DOMAIN-RIVAL-ANALYSIS.md), so decoy questions are asked
on the whole word while the winner's own admission remains parity-split.
"""


def _rival_gate(
    best_mismatch: float,
    rival_mismatch: float,
    gate: PlacementGate = HISTORICAL_E022_GATE,
) -> bool:
    """Exact rival bar: strict decoy, inclusive qualified gap.

    Since v0.30 both inputs are WHOLE-WORD mismatches (all overlap sites,
    both parity classes): the decoy bar restores the d=27 argument against
    tile-lattice aliases, whose search-class mismatch is structurally
    below 0.20 at complete domains while their whole-word mismatch is
    >= 0.27.  The numeric bars are unchanged.
    """
    return (
        rival_mismatch > gate.rival_decoy
        and rival_mismatch - best_mismatch >= gate.minimum_gap
    )


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    accepted: bool
    best: CandidateScore | None
    runner_ups: tuple[CandidateScore, ...]
    hypotheses: int
    reason: str
    predicted_origin_yx: tuple[int, int] | None = None
    predicted_residual_cells: float | None = None
    bch_errors: int | None = None
    support_floor: int = HISTORICAL_MIN_SUPPORT
    rival: CandidateScore | None = None
    # Set only by the word route: the (tile_y, tile_x) whose BCH word the
    # seeder decoded to produce this address (v0.43 pane-C authority
    # tri-state).  Diagnostic provenance only — never read by admission.
    word_tile_yx: tuple[int, int] | None = None


@dataclass(frozen=True, slots=True)
class WindowRefinementOutcome:
    sample: SegmentSample
    delta_angle_deg: float
    delta_phase_yx: tuple[float, float]
    heldout_before: float
    heldout_after: float


class ScoreMemo:
    """Invocation-local, full-key, no-eviction memo for repeated probes."""

    def __init__(self, provider: ReferenceFieldProvider) -> None:
        self.provider = provider
        self._scores: dict[
            tuple[int, int, int, int, int, int],
            tuple[float, int, int, float],
        ] = {}
        self.requests = 0
        self.hits = 0

    def parity_score(
        self,
        sample_key: int,
        evidence: np.ndarray,
        bits: np.ndarray,
        mask: np.ndarray,
        page: int,
        origin_yx: tuple[int, int],
        rot_k: int,
        parity: int,
    ) -> tuple[float, int, int, float]:
        """Return weighted mismatch, hard errors, support, and soft z."""
        key = (
            int(sample_key), int(page), int(origin_yx[0]), int(origin_yx[1]),
            int(rot_k) % 4, int(parity),
        )
        self.requests += 1
        cached = self._scores.get(key)
        if cached is not None:
            self.hits += 1
            return cached
        reference = self.provider.page(page)
        observed = np.rot90(np.asarray(evidence, np.float32), rot_k)
        hard = np.rot90(np.asarray(bits, np.uint8), rot_k)
        keep = np.rot90(np.asarray(mask, bool), rot_k)
        slices = overlap_slices(
            origin_yx, observed.shape, reference.values.shape
        )
        if slices is None:
            result = (1.0, 0, 0, -np.inf)
            self._scores[key] = result
            return result
        page_y, page_x, frag_y, frag_x = slices
        selected = reference.sites[page_y, page_x] & keep[frag_y, frag_x]
        if parity != WHOLE_WORD_PARITY:
            selected &= parity_mask(
                selected.shape,
                (int(page_y.start or 0), int(page_x.start or 0)),
                parity,
            )
        support = int(selected.sum())
        if support == 0:
            result = (1.0, 0, 0, -np.inf)
            self._scores[key] = result
            return result
        expected_bits = reference.values[page_y, page_x][selected]
        observed_evidence = observed[frag_y, frag_x][selected]
        expected_sign = 1.0 - 2.0 * expected_bits.astype(np.float32)
        weights = np.abs(observed_evidence)
        correlation = float(np.sum(expected_sign * observed_evidence))
        total_weight = float(weights.sum())
        mismatch = (
            (total_weight - correlation) / (2.0 * total_weight)
            if total_weight > 0.0 else 1.0
        )
        observed_bits = hard[frag_y, frag_x][selected]
        errors = int(np.count_nonzero(observed_bits != expected_bits))
        z = correlation / np.sqrt(max(total_weight, 1e-9))
        result = (float(mismatch), errors, support, float(z))
        self._scores[key] = result
        return result

    def candidate(
        self,
        sample_key: int,
        evidence: np.ndarray,
        bits: np.ndarray,
        mask: np.ndarray,
        page: int,
        origin_yx: tuple[int, int],
        rot_k: int,
        budget: AttemptBudget,
        route: str,
    ) -> CandidateScore:
        search = self.parity_score(
            sample_key, evidence, bits, mask, page, origin_yx, rot_k, 0
        )
        validation = self.parity_score(
            sample_key, evidence, bits, mask, page, origin_yx, rot_k, 1
        )
        passes = (
            search[2] >= budget.search_min_support
            and validation[2] >= budget.validation_min_support
            and search[0] < budget.gate.search_true
            and validation[0] < budget.gate.validation_true
        )
        return CandidateScore(
            int(page), tuple(map(int, origin_yx)), int(rot_k) % 4,
            search[0], validation[0], search[1], validation[1],
            search[2], validation[2], search[3], passes, route,
        )


def parity_mask(
    shape: tuple[int, int], origin_yx: tuple[int, int], parity: int
) -> np.ndarray:
    """Frozen E022 split ``(131*y + 17*x)&1 == parity``."""
    height, width = shape
    y0, x0 = origin_yx
    rows = (np.arange(height, dtype=np.intp) + (y0 & 1)) & 1
    cols = (np.arange(width, dtype=np.intp) + (x0 & 1)) & 1
    return (rows[:, None] ^ cols[None, :]) == int(parity)


def hypothesis_count(
    fragment_shape: tuple[int, int],
    page_shape: tuple[int, int],
    pages: int,
    *,
    allow_overhang: bool,
) -> int:
    """Exact integer-offset x rot90 x page domain, before support pruning."""
    total = 0
    height, width = page_shape
    for rot_k in range(4):
        frag_height, frag_width = (
            fragment_shape if rot_k % 2 == 0 else fragment_shape[::-1]
        )
        if allow_overhang:
            positions = (height + frag_height - 1) * (width + frag_width - 1)
        else:
            positions = max(0, height - frag_height + 1) * max(
                0, width - frag_width + 1
            )
        total += positions
    return int(pages) * total


@dataclass(frozen=True, slots=True)
class _ColdMapGeometry:
    """Page-invariant operands for one Lane-C fragment orientation.

    ``fshape`` and ``kernel_rfft`` replicate exactly the padded transform
    ``scipy.signal.fftconvolve`` would compute for the soft convolution, so
    hoisting them across the page loop preserves bit-identical z maps
    (RECEIVE-DESIGN 5.3).  ``kernel_rfft`` is ``None`` for degenerate
    <2-cell axes, which take fftconvolve's broadcast special case instead.
    """

    work_sites: np.ndarray
    search_sites: np.ndarray
    soft_kernel: np.ndarray
    weight: np.ndarray
    eligible: np.ndarray
    pad_y: int
    pad_x: int
    fshape: tuple[int, int]
    kernel_rfft: np.ndarray | None


def _cold_map_geometries(
    evidence: np.ndarray,
    mask: np.ndarray,
    sites: np.ndarray,
    budget: AttemptBudget,
    *,
    allow_overhang: bool,
    fft_workers: int = 1,
) -> tuple[_ColdMapGeometry | None, ...]:
    """Prepare the four page-invariant Lane-C correlation geometries.

    V1's site mask and absolute search parity are identical on every page.
    Consequently the weight and support maps depend on fragment orientation,
    but not on page values.  Keeping them here, together with each
    orientation's soft-kernel transform, makes the complete cold search
    require eight invariant convolutions, four kernel transforms, one padded
    page-side transform per page and padding group, and one inverse FFT for
    each page/orientation trial.
    """
    evidence = np.asarray(evidence, np.float32)
    mask = np.asarray(mask, bool)
    sites = np.asarray(sites, bool)
    page_parity = parity_mask(sites.shape, (0, 0), 0)
    base_search_sites = sites & page_parity
    padded_sites: dict[
        tuple[int, int], tuple[np.ndarray, np.ndarray]
    ] = {}
    geometries: list[_ColdMapGeometry | None] = []
    for rot_k in range(4):
        observed = np.rot90(evidence, rot_k)
        keep = np.rot90(mask, rot_k).astype(np.float32)
        pad_y = pad_x = 0
        if allow_overhang:
            pad_y, pad_x = observed.shape[0] - 1, observed.shape[1] - 1
            padding = (pad_y, pad_x)
            prepared_sites = padded_sites.get(padding)
            if prepared_sites is None:
                prepared_sites = (
                    np.pad(sites, ((pad_y, pad_y), (pad_x, pad_x))),
                    np.pad(
                        base_search_sites,
                        ((pad_y, pad_y), (pad_x, pad_x)),
                    ),
                )
                padded_sites[padding] = prepared_sites
            work_sites, search_sites = prepared_sites
        elif (
            observed.shape[0] > sites.shape[0]
            or observed.shape[1] > sites.shape[1]
        ):
            geometries.append(None)
            continue
        else:
            work_sites, search_sites = sites, base_search_sites
        soft_kernel = (observed * keep)[::-1, ::-1]
        with set_workers(max(1, int(fft_workers))):
            weight = fftconvolve(
                search_sites.astype(np.float32),
                (np.abs(observed) * keep)[::-1, ::-1],
                mode="valid",
            )
            search_support = np.rint(fftconvolve(
                search_sites.astype(np.float32), keep[::-1, ::-1],
                mode="valid"
            )).astype(np.int32)
        eligible = (
            search_support >= budget.search_min_support
        ) & (weight > 0.0)
        # fftconvolve pads both operands to next_fast_len of the full linear
        # size; the identical fshape is what keeps the cached-transform soft
        # convolution bit-identical to the direct call.
        fshape = (
            next_fast_len(
                search_sites.shape[0] + soft_kernel.shape[0] - 1, True
            ),
            next_fast_len(
                search_sites.shape[1] + soft_kernel.shape[1] - 1, True
            ),
        )
        kernel_rfft = None
        if min(soft_kernel.shape) >= 2 and min(search_sites.shape) >= 2:
            kernel_rfft = rfftn(
                soft_kernel, fshape, axes=(0, 1),
                workers=max(1, int(fft_workers)))
        geometries.append(_ColdMapGeometry(
            work_sites,
            search_sites,
            soft_kernel,
            weight,
            eligible,
            pad_y,
            pad_x,
            fshape,
            kernel_rfft,
        ))
    return tuple(geometries)


def _signed_search_field(
    values: np.ndarray, geometry: _ColdMapGeometry
) -> np.ndarray:
    """Padded ``expected_sign x search_sites`` operand for one page."""
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
    return expected_sign * geometry.search_sites


def _page_candidate_map(
    values: np.ndarray,
    geometry: _ColdMapGeometry,
    page: int,
    page_transforms: dict[tuple[int, int, int, tuple[int, int]], np.ndarray],
    *,
    fft_workers: int = 1,
) -> np.ndarray:
    """Return one page's historical search-parity z map.

    Validation is evaluated only for the selected winner through
    :class:`ScoreMemo`, as in E022.  The soft convolution is the explicit
    product of the hoisted kernel transform and a page-side transform shared
    by every orientation map with equal padding and fshape, reproducing
    ``fftconvolve``'s fshape, dtype promotion, and valid slicing bit for
    bit; only the inverse FFT remains per page/orientation trial.
    ``fft_workers`` threads pocketfft's per-line parallelism through the
    transforms; every line transform is computed by the same serial kernel
    regardless of the worker count, so the maps stay bit-identical (pinned
    by ``tests/holo/test_parallel_exactness.py``).
    """
    if geometry.kernel_rfft is None:
        with set_workers(max(1, int(fft_workers))):
            soft_corr = fftconvolve(
                _signed_search_field(values, geometry),
                geometry.soft_kernel,
                mode="valid",
            )
    else:
        # The cache lives for one correlate_patch invocation, whose sites
        # are checked page-invariant, so the key needs no site identity.
        key = (int(page), geometry.pad_y, geometry.pad_x, geometry.fshape)
        transform = page_transforms.get(key)
        if transform is None:
            transform = rfftn(
                _signed_search_field(values, geometry),
                geometry.fshape,
                axes=(0, 1),
                workers=max(1, int(fft_workers)),
            )
            page_transforms[key] = transform
        full = irfftn(
            transform * geometry.kernel_rfft, geometry.fshape, axes=(0, 1),
            workers=max(1, int(fft_workers)),
        )
        kernel_height, kernel_width = geometry.soft_kernel.shape
        height, width = geometry.search_sites.shape
        soft_corr = full[kernel_height - 1:height, kernel_width - 1:width]
    with np.errstate(divide="ignore", invalid="ignore"):
        z = soft_corr / np.sqrt(geometry.weight)
    return np.where(geometry.eligible, z, -np.inf)


def correlate_patch(
    patch: AddressPatch,
    provider: ReferenceFieldProvider,
    pages: tuple[int, ...],
    budget: AttemptBudget,
    memo: ScoreMemo,
    *,
    sample_key: int,
    config: PlacementConfig,
    page_progress: Callable[[int, int], None] | None = None,
) -> SearchOutcome:
    """Complete Lane-C phase x address search with disjoint validation.

    ``page_progress`` is an optional observer-only heartbeat callback
    (RECEIVE-DESIGN §10.6, docs/PHASED-SCHEDULE.md D14c): it receives
    ``(page_ordinal, pages_total)`` at count-bounded points of the page
    sweep — at most 64 invocations per sweep, one every ``ceil(P/64)``
    pages.  The bounding is count-based (no clock reads), the callback
    touches no search state, and an absent callback adds zero numerical
    work; scores, ordering, and acceptance are pinned bit-identical by
    ``tests/holo/test_cold_search_exactness.py``.
    """
    if any(
        isinstance(page, (bool, np.bool_))
        or not isinstance(page, (int, np.integer))
        for page in pages
    ):
        raise TypeError("page hypotheses must be integers")
    pages = tuple(dict.fromkeys(int(page) for page in pages))
    if not pages:
        raise ValueError("Lane C needs at least one explicit page hypothesis")
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
    RawCandidate = tuple[float, int, tuple[int, int], int]
    # Keep one top per page/orientation map.  E022's rival set is the top of
    # every losing map plus the spatially distinct second peak of the winning
    # map only — seconds from losing maps were never part of the qualified
    # decision — so a single z map, the running best top's, is retained while
    # sweeping and losing maps never pay a copy + second argmax.  Strict
    # ``>`` replacement reproduces ``max``'s first-on-exact-tie winner in
    # caller page order, then orientation order, exactly as legacy E022 did.
    raw_tops: list[RawCandidate] = []
    winner_index = -1
    winner_z: np.ndarray | None = None
    winner_peak_yx = (0, 0)
    winner_pad_yx = (0, 0)
    page_transforms: dict[
        tuple[int, int, int, tuple[int, int]], np.ndarray
    ] = {}
    workers = _parallel.worker_count()
    first_reference = provider.page(pages[0])
    geometries = _cold_map_geometries(
        patch.evidence,
        patch.mask,
        first_reference.sites,
        budget,
        allow_overhang=config.allow_overhang,
        fft_workers=workers,
    )
    if not any(
        geometry is not None and bool(geometry.eligible.any())
        for geometry in geometries
    ):
        # Result-exact early-out: eligibility is page-invariant, so with no
        # origin reaching the support floor in any orientation every page
        # map would be all -inf and the sweep would end insufficient_support
        # anyway.  Measured motivation: 70-cell subdivision children each
        # paid a full 312-page FFT sweep before dying at the 55/parity
        # floor (docs/FULL-DOMAIN-RIVAL-ANALYSIS.md).
        return SearchOutcome(
            False, None, (), hypotheses, "insufficient_support",
            support_floor=budget.min_support,
        )
    progress_stride = 0
    if page_progress is not None:
        # §10.6 count-based bounding: ceil(P/64) pages per heartbeat.
        progress_stride = -(-len(pages) // 64)

    def _page_sweep(
        item: tuple[int, int],
        transforms: dict[
            tuple[int, int, int, tuple[int, int]], np.ndarray],
        fft_workers: int,
    ) -> tuple[
        list[RawCandidate], int,
        np.ndarray | None, tuple[int, int], tuple[int, int],
    ]:
        """All orientation maps of one page: tops + the page-local winner.

        The page-local winner uses the exact strict-``>`` first-on-tie
        rule of the global sweep, so the global winner is always some
        page's local winner and its retained z map is the one the
        sequential loop would have kept (the reduction below preserves
        the (page, orientation) visit order for ``raw_tops``).
        """
        page_index, page = item
        reference = (
            first_reference if page_index == 0 else provider.page(page)
        )
        if (
            reference.sites is not first_reference.sites
            and not np.array_equal(reference.sites, first_reference.sites)
        ):
            raise ValueError("v1 reference sites must be page-invariant")
        tops: list[RawCandidate] = []
        best_offset = -1
        best_z: np.ndarray | None = None
        best_peak = (0, 0)
        best_pad = (0, 0)
        for rot_k, geometry in enumerate(geometries):
            if geometry is None:
                continue
            z = _page_candidate_map(
                reference.values, geometry, page, transforms,
                fft_workers=fft_workers,
            )
            if z.size == 0 or not np.isfinite(z).any():
                continue
            flat = int(np.argmax(z))
            peak_y, peak_x = np.unravel_index(flat, z.shape)
            top: RawCandidate = (
                float(z[peak_y, peak_x]), int(page),
                (int(peak_y) - geometry.pad_y, int(peak_x) - geometry.pad_x),
                rot_k,
            )
            if best_offset < 0 or top[0] > tops[best_offset][0]:
                best_offset = len(tops)
                best_z = z
                best_peak = (int(peak_y), int(peak_x))
                best_pad = (geometry.pad_y, geometry.pad_x)
            tops.append(top)
        return tops, best_offset, best_z, best_peak, best_pad

    page_stream = None
    if workers > 1 and len(pages) > 1:
        page_tasks = min(workers, len(pages))
        task_fft_workers = max(1, workers // page_tasks)
        page_stream = _parallel.submit_map(
            lambda item: _page_sweep(item, {}, task_fft_workers),
            tuple(enumerate(pages)),
            workers=page_tasks,
        )
    if page_stream is not None:
        # Deterministic reduction in submission (= caller page) order:
        # per-map tops enter ``raw_tops`` in the sequential visit order,
        # the strict-``>`` winner update is unchanged, and the retained
        # z map is the winning page's local-winner map (see _page_sweep).
        for page_index, task in enumerate(page_stream):
            if (page_progress is not None
                    and page_index % progress_stride == 0):
                page_progress(page_index + 1, len(pages))
            tops, best_offset, best_z, best_peak, best_pad = task
            for offset, top in enumerate(tops):
                if winner_index < 0 or top[0] > raw_tops[winner_index][0]:
                    winner_index = len(raw_tops)
                    if offset == best_offset:
                        winner_z = best_z
                        winner_peak_yx = best_peak
                        winner_pad_yx = best_pad
                    else:
                        # Transient: superseded by this page's local
                        # winner before the page's tops are exhausted.
                        winner_z = None
                raw_tops.append(top)
    else:
        for page_index, page in enumerate(pages):
            if (page_progress is not None
                    and page_index % progress_stride == 0):
                page_progress(page_index + 1, len(pages))
            tops, best_offset, best_z, best_peak, best_pad = _page_sweep(
                (page_index, page), page_transforms, workers)
            for offset, top in enumerate(tops):
                if winner_index < 0 or top[0] > raw_tops[winner_index][0]:
                    winner_index = len(raw_tops)
                    if offset == best_offset:
                        winner_z = best_z
                        winner_peak_yx = best_peak
                        winner_pad_yx = best_pad
                    else:
                        winner_z = None
                raw_tops.append(top)
    if not raw_tops:
        return SearchOutcome(
            False, None, (), hypotheses, "insufficient_support",
            support_floor=budget.min_support,
        )
    winner_raw = raw_tops[winner_index]
    assert winner_z is not None
    # The retained map is not consulted after this second-peak recompute, so
    # blanking the winner's neighborhood in place is value-identical to the
    # legacy per-map ``z.copy()`` route.
    radius = config.neighbor_radius_cells
    peak_y, peak_x = winner_peak_yx
    winner_z[
        max(0, peak_y - radius):peak_y + radius + 1,
        max(0, peak_x - radius):peak_x + radius + 1,
    ] = -np.inf
    winner_second: RawCandidate | None = None
    if np.isfinite(winner_z).any():
        flat_second = int(np.argmax(winner_z))
        second_y, second_x = np.unravel_index(flat_second, winner_z.shape)
        winner_second = (
            float(winner_z[second_y, second_x]), winner_raw[1],
            (
                int(second_y) - winner_pad_yx[0],
                int(second_x) - winner_pad_yx[1],
            ),
            winner_raw[3],
        )
    best = memo.candidate(
        sample_key, patch.evidence, patch.bits, patch.mask,
        winner_raw[1], winner_raw[2], winner_raw[3], budget, "correlation",
    )
    runners: list[CandidateScore] = []
    seen: set[tuple[int, tuple[int, int], int]] = {
        (best.page, best.origin_yx, best.rot_k)
    }
    rival_rows: list[RawCandidate] = []
    for map_index, top in enumerate(raw_tops):
        if map_index == winner_index:
            if winner_second is not None:
                rival_rows.append(winner_second)
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
    # This is the exact decision rival used by historical E022.  The full
    # map-top spectrum remains qualification/search working state; downstream
    # semantic audit needs only the selected rival and the resulting gaps.
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
    # v0.30 whole-word rival evaluation: the decoy bar binds the MOST
    # DANGEROUS member of the historical rival set — the minimum
    # whole-word mismatch over all runners — and the winner gap compares
    # whole-word to whole-word.  The reported ``rival`` retains the
    # historical z-selected row (diagnostic identity); selection is
    # unchanged, only the decoy/gap arithmetic moved to whole words,
    # restoring the d=27 floor against parity-concentrated aliases.
    if runners:
        rival_mismatch = min(
            memo.parity_score(
                sample_key, patch.evidence, patch.bits, patch.mask,
                row.page, row.origin_yx, row.rot_k, WHOLE_WORD_PARITY,
            )[0]
            for row in runners
        )
        best_whole = memo.parity_score(
            sample_key, patch.evidence, patch.bits, patch.mask,
            best.page, best.origin_yx, best.rot_k, WHOLE_WORD_PARITY,
        )[0]
    else:
        rival_mismatch = 1.0
        best_whole = best.search_mismatch
    rival_ok = _rival_gate(
        best_whole, rival_mismatch, budget.gate
    )
    accepted = rival_ok
    return SearchOutcome(
        accepted,
        best,
        tuple(runners),
        hypotheses,
        (
            "accepted" if accepted
            else "rival_gap_failed"
        ),
        support_floor=budget.min_support,
        rival=rival,
    )


def local_search(
    patch: AddressPatch,
    page: int,
    rot_k: int,
    predicted: tuple[int, int],
    budget: AttemptBudget,
    memo: ScoreMemo,
    *,
    sample_key: int,
    config: PlacementConfig,
    route: str = "chain",
) -> SearchOutcome:
    """Full bounded neighborhood; no prefix/probe-count shortcut."""
    radius = config.neighbor_radius_cells
    hypotheses = (2 * radius + 1) ** 2
    if hypotheses > budget.max_hypotheses:
        return SearchOutcome(
            False, None, (), hypotheses, "attempt_budget_exceeded",
            support_floor=budget.min_support,
        )
    candidates = [
        memo.candidate(
            sample_key, patch.evidence, patch.bits, patch.mask,
            page, (predicted[0] + dy, predicted[1] + dx), rot_k,
            budget, route,
        )
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
    ]
    candidates.sort(key=lambda row: (
        -row.soft_z, row.origin_yx[0], row.origin_yx[1]
    ))
    if not candidates or not np.isfinite(candidates[0].soft_z):
        return SearchOutcome(
            False, None, tuple(candidates), hypotheses,
            "insufficient_support",
            support_floor=budget.min_support,
        )
    best = candidates[0]
    residual = max(
        abs(best.origin_yx[0] - predicted[0]),
        abs(best.origin_yx[1] - predicted[1]),
    )
    accepted = best.passes and residual <= config.consistency_cells
    return SearchOutcome(
        accepted, best, tuple(candidates[1:]), hypotheses,
        "accepted" if accepted else "local_validation_failed",
        predicted_origin_yx=predicted,
        predicted_residual_cells=float(residual),
        support_floor=budget.min_support,
    )


def predict_from_anchor(
    anchor_pose: AffinePose,
    anchor_shape: tuple[int, int],
    anchor_origin_yx: tuple[int, int],
    rot_k: int,
    target_pose: AffinePose,
    target_shape: tuple[int, int],
) -> tuple[int, int]:
    """Transport a target patch through an accepted full affine anchor."""
    delta_pixels = (
        np.asarray(target_pose.origin_yx) - np.asarray(anchor_pose.origin_yx)
    )
    delta_cells = np.linalg.solve(anchor_pose.matrix(), delta_pixels)
    matrix, anchor_translation = rotation_affine(rot_k, anchor_shape)
    _, target_translation = rotation_affine(rot_k, target_shape)
    origin = (
        matrix @ delta_cells + anchor_translation - target_translation
        + np.asarray(anchor_origin_yx, np.float64)
    )
    return int(round(origin[0])), int(round(origin[1]))


def refine_patch_pose(
    context: RegionContext,
    patch: AddressPatch,
    provider: ReferenceFieldProvider,
    page: int,
    patch_origin_yx: tuple[int, int],
    rot_k: int,
    config: PlacementConfig,
) -> WindowRefinementOutcome | None:
    """Run E022's bounded pose refinement on one accepted window."""
    if not config.refine:
        return None
    sample = patch.sample
    points, expected, absolute = fragment_reference_sites(
        sample.mask, provider, page,
        patch_origin_yx, rot_k,
    )
    if not expected.size:
        return None
    if expected.size < config.refine_min_total_sites:
        return None
    parity = (
        (absolute[:, 0] * 131 + absolute[:, 1] * 17) & 1
    ).astype(bool)
    train = ~parity
    heldout = parity
    if (
        int(train.sum()) < config.refine_min_sites_per_parity
        or int(heldout.sum()) < config.refine_min_sites_per_parity
    ):
        return None
    expected_sign = 1.0 - 2.0 * expected.astype(np.float64)
    midpoint = float(np.median(sample.means[sample.mask]))

    def evaluate(
        delta_angle_deg: float, delta_y: float, delta_x: float
    ) -> tuple[float, float]:
        angle = np.deg2rad(delta_angle_deg)
        rotation = np.array([
            [np.cos(angle), np.sin(angle)],
            [-np.sin(angle), np.cos(angle)],
        ])
        pose = sample.segment.pose
        jacobian0 = pose.matrix()
        jacobian = rotation @ jacobian0
        base = (
            np.asarray(pose.origin_yx, np.float64)
            - np.array([context.y0, context.x0], np.float64)
            + jacobian0 @ np.array([delta_y, delta_x])
        )
        scan_points = points.astype(np.float64) @ jacobian.T + base
        means = ndimage.map_coordinates(
            context.filtered, scan_points.T, order=1,
            cval=context.backing,
        )
        margin = float(np.mean(
            (midpoint - means[train]) * -expected_sign[train]
        ))
        heldout_mismatch = float(np.mean(
            (means[heldout] < midpoint) != (expected[heldout] > 0)
        ))
        return margin, heldout_mismatch

    _, baseline_heldout = evaluate(0.0, 0.0, 0.0)
    best: tuple[float, float, float, float, float] | None = None
    for delta_angle in np.arange(
        -config.refine_angle_deg,
        config.refine_angle_deg + 1e-9,
        config.refine_angle_step_deg,
    ):
        for delta_y in np.arange(
            -config.refine_phase_cells,
            config.refine_phase_cells + 1e-9,
            config.refine_phase_step_cells,
        ):
            for delta_x in np.arange(
                -config.refine_phase_cells,
                config.refine_phase_cells + 1e-9,
                config.refine_phase_step_cells,
            ):
                margin, heldout_mismatch = evaluate(
                    float(delta_angle), float(delta_y), float(delta_x)
                )
                if best is None or margin > best[0]:
                    best = (
                        margin, float(delta_angle), float(delta_y),
                        float(delta_x), heldout_mismatch,
                    )
    if best is None:
        return None
    _, delta_angle, delta_y, delta_x, heldout_after = best
    if heldout_after > baseline_heldout + config.refine_heldout_degrade:
        return None
    angle = np.deg2rad(delta_angle)
    rotation = np.array([
        [np.cos(angle), np.sin(angle)],
        [-np.sin(angle), np.cos(angle)],
    ])
    base_pose = sample.segment.pose
    jacobian0 = base_pose.matrix()
    jacobian = rotation @ jacobian0
    origin = (
        np.asarray(base_pose.origin_yx, np.float64)
        + jacobian0 @ np.array([delta_y, delta_x])
    )
    pitch_y, pitch_x, pose_angle, _ = pose_metrics(jacobian)
    pose = AffinePose(
        (float(origin[0]), float(origin[1])),
        (
            (float(jacobian[0, 0]), float(jacobian[0, 1])),
            (float(jacobian[1, 0]), float(jacobian[1, 1])),
        ),
        base_pose.phase_yx,
        float(0.5 * (pitch_y + pitch_x)),
        pose_angle,
    )
    refined = sample_segment(context, replace(sample.segment, pose=pose))
    if refined is None:
        return None
    return WindowRefinementOutcome(
        refined, delta_angle, (delta_y, delta_x),
        baseline_heldout, heldout_after,
    )


def fragment_reference_sites(
    mask: np.ndarray,
    provider: ReferenceFieldProvider,
    page: int,
    origin_yx: tuple[int, int],
    rot_k: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Local points, expected bits, and absolute page points under a pose."""
    reference = provider.page(page)
    rotated_mask = np.rot90(np.asarray(mask, bool), rot_k)
    slices = overlap_slices(origin_yx, rotated_mask.shape, reference.values.shape)
    if slices is None:
        empty = np.zeros((0, 2), np.int64)
        return empty, np.zeros(0, np.uint8), empty
    page_y, page_x, frag_y, frag_x = slices
    selected_rotated = np.zeros(rotated_mask.shape, bool)
    selected_rotated[frag_y, frag_x] = (
        reference.sites[page_y, page_x] & rotated_mask[frag_y, frag_x]
    )
    ry, rx = np.nonzero(selected_rotated)
    absolute = np.stack([
        ry + int(origin_yx[0]), rx + int(origin_yx[1])
    ], axis=1)
    expected = reference.values[absolute[:, 0], absolute[:, 1]]
    # Invert the rotation while preserving correspondence order.
    index = np.full(rotated_mask.shape, -1, np.int64)
    index[ry, rx] = np.arange(ry.size)
    unrotated = np.rot90(index, -rot_k)
    local_y, local_x = np.nonzero(unrotated >= 0)
    order = unrotated[local_y, local_x]
    return (
        np.stack([local_y, local_x], axis=1),
        expected[order],
        absolute[order],
    )


def audit_segment(
    sample: SegmentSample,
    core: np.ndarray,
    provider: ReferenceFieldProvider,
    page: int,
    origin_yx: tuple[int, int],
    rot_k: int,
    config: PlacementConfig,
    *,
    min_support: int = HISTORICAL_MIN_SUPPORT,
) -> tuple[np.ndarray, bool, int, float]:
    """E022-v2 binomial-impurity change-point straddle audit."""
    if isinstance(min_support, (bool, np.bool_)) or not isinstance(
            min_support, (int, np.integer)) or int(min_support) < 1:
        raise ValueError("audit min_support must be a positive integer")
    min_support = int(min_support)
    points, expected, absolute = fragment_reference_sites(
        core, provider, page, origin_yx, rot_k
    )
    parity = (
        (absolute[:, 0] * 131 + absolute[:, 1] * 17) & 1
    ).astype(bool)

    def below_population_floor(selected: np.ndarray) -> bool:
        return (
            int(np.count_nonzero(selected & ~parity)) < min_support
            or int(np.count_nonzero(selected & parity)) < min_support
        )

    if points.shape[0] < 2 * config.audit_min_sites:
        support = int(points.shape[0])
        selected = np.ones(support, bool)
        return (
            np.asarray(core, bool), below_population_floor(selected),
            support, 0.0,
        )
    wrong = (
        sample.bits[points[:, 0], points[:, 1]] != expected
    ).astype(np.float64)
    good = np.asarray(core, bool).copy()
    keep = np.ones(points.shape[0], bool)
    for axis in (0, 1, 0, 1):
        active = np.flatnonzero(keep)
        if active.size < 2 * config.audit_min_sites:
            break
        coordinates = points[active, axis]
        order = np.argsort(coordinates, kind="stable")
        coordinates = coordinates[order]
        errors = wrong[active][order]
        cumulative = np.concatenate([[0.0], np.cumsum(errors)])
        best: tuple[float, float, float, float] | None = None
        size = coordinates.size
        for split in range(config.audit_min_sites, size - config.audit_min_sites):
            if coordinates[split] == coordinates[split - 1]:
                continue
            low = cumulative[split] / split
            high = (cumulative[size] - cumulative[split]) / (size - split)
            impurity = (
                split * low * (1.0 - low)
                + (size - split) * high * (1.0 - high)
            )
            if best is None or impurity < best[0]:
                best = (
                    float(impurity), float(low), float(high),
                    float(0.5 * (coordinates[split - 1] + coordinates[split])),
                )
        if best is None:
            continue
        _, low, high, cut = best
        bad_low = low > high
        bad_rate, kept_rate = (low, high) if bad_low else (high, low)
        if not (bad_rate > config.audit_bad and kept_rate < config.audit_good):
            continue
        edge = int(np.ceil(cut))
        if axis == 0:
            if bad_low:
                good[:edge, :] = False
            else:
                good[edge:, :] = False
        else:
            if bad_low:
                good[:, :edge] = False
            else:
                good[:, edge:] = False
        keep &= good[points[:, 0], points[:, 1]]
    kept = int(keep.sum())
    residual = float(wrong[keep].mean()) if kept else 1.0
    refused = (
        below_population_floor(keep)
        or residual > config.audit_post_bar
    )
    return good, refused, kept, residual


def observations_for_segment(
    sample: SegmentSample,
    audited: np.ndarray,
    provider: ReferenceFieldProvider,
    page: int,
    origin_yx: tuple[int, int],
    rot_k: int,
    *,
    scan_id: str,
    patch_id: int,
) -> tuple[PilotObservation, ...]:
    """Retain every authoritative pilot bit/evidence read under the core."""
    local, _expected, absolute = fragment_reference_sites(
        audited, provider, page, origin_yx, rot_k
    )
    if not local.size:
        return ()
    site_positions = pilots.word_site_cells_yx(provider.spec.family_seed)
    site_index = {tuple(map(int, row)): index for index, row in enumerate(site_positions)}
    rows: list[PilotObservation] = []
    for point, page_point in zip(local, absolute, strict=True):
        page_y, page_x = map(int, page_point)
        tile_y, site_y = divmod(page_y, pilots.TILE_CELLS)
        tile_x, site_x = divmod(page_x, pilots.TILE_CELLS)
        word_index = site_index.get((site_y, site_x))
        # Future filler labels participate in Lane C but are not BCH word
        # observations; their calibration path will consume them separately.
        if word_index is None:
            continue
        local_y, local_x = map(int, point)
        rows.append(PilotObservation(
            int(page), (tile_y, tile_x), word_index,
            int(sample.bits[local_y, local_x]),
            float(sample.evidence[local_y, local_x]),
            str(scan_id), int(patch_id),
        ))
    return tuple(rows)
