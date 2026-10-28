"""Cold correlation: the complete Lane-C phase x address search.

Ported from ``src/holo/receive/placement/search.py`` at 594a465 — the
COLD half of that module: ``correlate_patch`` (:429-729) with its nested
``_page_sweep`` (:515-568), ``_ColdMapGeometry`` (:235-254),
``_cold_map_geometries`` (:257-352), ``_signed_search_field`` (:355-373),
``_page_candidate_map`` (:376-426), ``_rival_gate`` (:49-65),
``WHOLE_WORD_PARITY`` (:38) and ``SearchOutcome`` (:68-88).  Refactored
per H4-PLAN R4: the CODE is holo2's own, the ARITHMETIC is v1's to the
bit.  W0 sub-wave A2 — nothing imports this module yet, and no behaviour
changes anywhere.

**The exactness contract, which is the strictest in the tree.**  The
cached-transform path reproduces ``scipy.signal.fftconvolve`` BIT FOR
BIT, and ``tests/holo/test_cold_search_exactness.py`` is what that means
in practice.  Preserved here verbatim, and never to be "cleaned up":

* the padded shape (``next_fast_len(n + m - 1, True)`` per axis) and the
  ``full[kh - 1:h, kw - 1:w]`` valid slice that reproduces
  ``fftconvolve``'s own padding, dtype promotion and slicing;
* the degenerate ``<2``-cell-axis fallback to a direct ``fftconvolve``
  (``kernel_rfft is None``) — pocketfft's broadcast special case;
* ``np.rint(...).astype(np.int32)`` for ``search_support`` (not
  ``np.ceil``, not ``int()``);
* the z map's ``soft_corr / np.sqrt(weight)`` under ``errstate`` with an
  ``-inf`` fill on the ineligible support (float32 in, float32 out);
* the strict ``>`` winner replacement, which reproduces ``max``'s
  first-on-exact-tie choice in caller-page order, then orientation
  order;
* the ``(observed * keep)[::-1, ::-1]`` kernel reversal, the absolute
  ``parity_mask(sites.shape, (0, 0), 0)`` search parity, and the
  page-invariant site/weight/eligibility maps hoisted out of the page
  loop.

**THE ONE STRUCTURAL ADAPTATION (declared).**  v1's ``_parallel``
env-hatch fan-out over pages (``worker_count()`` at :486,
``submit_map`` at :574-578, and the second copy of the reduction it
forced) becomes an INLINE SEQUENTIAL page loop: concurrency is the
engine's business (W4 leases), not the kernel's — the declared
precedent is ``capture/_survey_tensor``'s pool->sequential adaptation.
The per-task-fresh ``page_transforms`` semantics survive the flattening
EXACTLY: the cache key carries the PAGE (:392-395's invariance claim),
so a fresh dict per page-task and one dict shared by the whole
invocation memoise the same values under the same keys — v1's own
sequential arm already passed the shared dict, and it is the arm the
default worker count (1) has always taken.

**The ``set_workers`` decision: DROPPED, wholesale.**  v1 threaded
``fft_workers`` into ``set_workers``/``rfftn(workers=...)`` so a
page-parallel task could subdivide pocketfft's per-line parallelism.
With the fan-out gone there is no worker count to spend, the plan's
library-threading policy is explicit ("kernels serial inside a fire,
parallelism lives in the pool", H4-PLAN W-S), and v1's own pin
(``tests/holo/test_parallel_exactness.py``, and the :312-321 claim) is
that every line transform is computed by the same serial kernel
whatever the worker count — so removing the knob cannot move a value.
The transforms now run at ``scipy.fft``'s ambient default; no context
manager is entered and no ``workers=`` argument is passed.

**R4 freedoms exercised (code only, arithmetic untouched):** the two
byte-identical reduction loops (parallel arm + sequential arm) collapse
into one; ``_page_sweep`` becomes a module-level function over explicit
operands instead of a closure, returning a named :class:`_PageSweep`
instead of a five-tuple, and the page-invariance check moves to the
caller loop immediately before it (same order: resolve, check, then
maps); the anonymous ``RawCandidate`` four-tuple becomes
:class:`_MapTop`, so ``top[0] > raw_tops[winner_index][0]`` reads
``top.z > ...``; the three identical no-candidate refusals become
:func:`_refused`; ``budget.search_min_support`` becomes A1's collapsed
``budget.min_support`` and ``HISTORICAL_MIN_SUPPORT`` becomes
``E022_SUPPORT_FLOOR_SITES``; the page-domain validation's explicit
``np.bool_`` arm goes, exactly as A1 dropped it in ``_int_at_least``
(``np.bool_`` is an instance of neither ``int`` nor ``np.integer``, so
the second clause still raises); the transform cache's key and dict
types get the names :data:`PageTransformKey` / :data:`PageTransforms`,
which is the seam W4 swaps for a leased resource.

**Where three shared names live — RECONCILED by W0-B.**

* ``_rival_gate`` stayed here through W4 — its only consumer in the whole
  v1 tree is ``correlate_patch``, and H4-PLAN's module map said so too.
  **W5's L8 rule change gave it a SECOND consumer** (the word route's
  decoded candidates), so the function moved to ``pose_audit`` with the
  rest of the shared kernel and this module re-binds the private name.
* ``WHOLE_WORD_PARITY`` and ``SearchOutcome`` are now imported from
  ``pose_audit`` (its :meth:`~holo2.solve.pose_audit.ScoreMemo.parity_score`
  is what interprets the sentinel, and ``local_search`` is the first
  primitive to return the outcome type); this module's duplicate
  declarations are deleted.
* ``parity_mask`` is imported from ``pose_audit`` too; this module's
  private ``_search_parity_mask`` copy is deleted.

**The Protocol seams — RECONCILED by W0-B.**  The four structural
Protocols (``ColdReferencePage``, ``ColdReferenceField``, ``ColdPatch``,
``ColdScorer``) are gone.  ``correlate_patch`` now takes
``reference.ReferenceFieldProvider``, ``pose_fit.AddressPatch`` and
``pose_audit.ScoreMemo`` directly.  The one adaptation the Protocols
used to paper over is now a call-site change instead of a shape
difference: v1 read the page extent as ``provider.spec.layout.cells_yx``;
holo2's ``TileFormat`` has no ``layout`` nesting, so this module reads
``provider.spec.cells_yx``.

**NOT PORTED here** (they belong to the other W0-A2 targets, and this
module must not grow a second copy): ``ScoreMemo`` and ``parity_mask``,
``audit_segment``, ``fragment_reference_sites``, ``refine_patch_pose``,
``WindowRefinementOutcome``, ``observations_for_segment``,
``predict_from_anchor``, ``local_search`` (pose_audit); ``AddressPatch``
and the geometry kernel (pose_fit); ``ReferencePage``/``V1ReferenceField``
and ``overlap_slices`` (reference); ``hypothesis_count``, imported from
``place_model`` where A1 declared it.  Also not ported, deliberately:
``holo.receive._parallel`` in any form, and the ``fft_workers``
plumbing that existed only to serve it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence, TypeAlias

import numpy as np
from scipy.fft import irfftn, next_fast_len, rfftn
from scipy.signal import fftconvolve

from .place_model import (
    HISTORICAL_E022_GATE,
    AttemptBudget,
    CandidateScore,
    CellYX,
    PlacementConfig,
    PlacementGate,
    hypothesis_count,
)
from .pose_audit import (SearchOutcome, WHOLE_WORD_PARITY, ScoreMemo,
                         parity_mask, rival_gate)
from .pose_fit import AddressPatch
from .reference import ReferenceFieldProvider

#: One page-side transform: ``(page, pad_y, pad_x, fshape)``.  NO site
#: identity — the cache lives for exactly one :func:`correlate_patch`
#: invocation, whose reference sites are proven page-invariant below
#: (v1 ``search.py:392-395``).  W4 leases this dict from the engine;
#: here it stays caller-owned, created and dropped by the invocation.
PageTransformKey: TypeAlias = tuple[int, int, int, tuple[int, int]]
PageTransforms: TypeAlias = dict[PageTransformKey, np.ndarray]


# ------------------------------------------------------------- the rival bar
#
# ``_rival_gate`` MOVED TO ``pose_audit`` at H4 W5, where the L8 rule
# change gave it its second consumer: the word route now asks the same
# bar of its decoded candidates (``placement.decode_word_address``), so
# the function belongs with the rest of the shared placement kernel —
# ``ScoreMemo``, ``WHOLE_WORD_PARITY``, ``SearchOutcome``, ``parity_mask``
# — exactly as W0-B reconciled those three.  The name is re-bound here
# because this module's own call site and its unit test read it here.
_rival_gate = rival_gate


# ------------------------------------------------- page-invariant geometries

@dataclass(frozen=True, slots=True)
class _ColdMapGeometry:
    """Page-invariant operands for one Lane-C fragment orientation.

    ``fshape`` and ``kernel_rfft`` replicate exactly the padded
    transform ``scipy.signal.fftconvolve`` would compute for the soft
    convolution, so hoisting them across the page loop preserves
    bit-identical z maps (RECEIVE-DESIGN 5.3).  ``kernel_rfft`` is
    ``None`` for degenerate <2-cell axes, which take fftconvolve's
    broadcast special case instead.
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
) -> tuple[_ColdMapGeometry | None, ...]:
    """Prepare the four page-invariant Lane-C correlation geometries.

    V1's site mask and absolute search parity are identical on every
    page.  Consequently the weight and support maps depend on fragment
    orientation, but not on page values.  Keeping them here, together
    with each orientation's soft-kernel transform, makes the complete
    cold search require eight invariant convolutions, four kernel
    transforms, one padded page-side transform per page and padding
    group, and one inverse FFT for each page/orientation trial.
    """
    evidence = np.asarray(evidence, np.float32)
    mask = np.asarray(mask, bool)
    sites = np.asarray(sites, bool)
    page_parity = parity_mask(
        (int(sites.shape[0]), int(sites.shape[1])), (0, 0), 0)
    base_search_sites = sites & page_parity
    # OR-11's shape, keyed by padding only: rot90 leaves the padded site
    # planes equal for equal (pad_y, pad_x), so the two square-padding
    # orientations share one pair.  W4 rules the parent/child variant.
    padded_sites: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
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
        weight = fftconvolve(
            search_sites.astype(np.float32),
            (np.abs(observed) * keep)[::-1, ::-1],
            mode="valid",
        )
        search_support = np.rint(fftconvolve(
            search_sites.astype(np.float32), keep[::-1, ::-1],
            mode="valid"
        )).astype(np.int32)
        eligible = (search_support >= budget.min_support) & (weight > 0.0)
        # fftconvolve pads both operands to next_fast_len of the full
        # linear size; the identical fshape is what keeps the
        # cached-transform soft convolution bit-identical to the direct
        # call.
        fshape = (
            next_fast_len(
                search_sites.shape[0] + soft_kernel.shape[0] - 1, True
            ),
            next_fast_len(
                search_sites.shape[1] + soft_kernel.shape[1] - 1, True
            ),
        )
        kernel_rfft: np.ndarray | None = None
        if min(soft_kernel.shape) >= 2 and min(search_sites.shape) >= 2:
            kernel_rfft = rfftn(soft_kernel, fshape, axes=(0, 1))
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
    field: np.ndarray = expected_sign * geometry.search_sites
    return field


def _page_candidate_map(
    values: np.ndarray,
    geometry: _ColdMapGeometry,
    page: int,
    page_transforms: PageTransforms,
) -> np.ndarray:
    """Return one page's historical search-parity z map.

    Validation is evaluated only for the selected winner through the
    scorer, as in E022.  The soft convolution is the explicit product of
    the hoisted kernel transform and a page-side transform shared by
    every orientation map with equal padding and fshape, reproducing
    ``fftconvolve``'s fshape, dtype promotion, and valid slicing bit for
    bit; only the inverse FFT remains per page/orientation trial.
    """
    if geometry.kernel_rfft is None:
        soft_corr = fftconvolve(
            _signed_search_field(values, geometry),
            geometry.soft_kernel,
            mode="valid",
        )
    else:
        # The cache lives for one correlate_patch invocation, whose
        # sites are checked page-invariant, so the key needs no site
        # identity.
        key = (int(page), geometry.pad_y, geometry.pad_x, geometry.fshape)
        transform = page_transforms.get(key)
        if transform is None:
            transform = rfftn(
                _signed_search_field(values, geometry),
                geometry.fshape,
                axes=(0, 1),
            )
            page_transforms[key] = transform
        full = irfftn(
            transform * geometry.kernel_rfft, geometry.fshape, axes=(0, 1),
        )
        kernel_height, kernel_width = geometry.soft_kernel.shape
        height, width = geometry.search_sites.shape
        soft_corr = full[kernel_height - 1:height, kernel_width - 1:width]
    with np.errstate(divide="ignore", invalid="ignore"):
        z = soft_corr / np.sqrt(geometry.weight)
    z_map: np.ndarray = np.where(geometry.eligible, z, -np.inf)
    return z_map


# ----------------------------------------------------------- the page sweep

@dataclass(frozen=True, slots=True)
class _MapTop:
    """The peak of one (page, orientation) z map, in page coordinates."""

    z: float
    page: int
    origin_yx: CellYX
    rot_k: int


@dataclass(frozen=True, slots=True)
class _PageSweep:
    """Every orientation map of one page, plus that page's local winner.

    ``best_offset`` indexes :attr:`tops`; ``best_z`` is the retained map
    of that local winner (the only map any second peak is ever taken
    from), and ``best_pad_yx`` is its padding, needed to put
    ``best_peak_yx`` back into page coordinates.
    """

    tops: tuple[_MapTop, ...]
    best_offset: int
    best_z: np.ndarray | None
    best_peak_yx: CellYX
    best_pad_yx: CellYX


def _page_sweep(
    values: np.ndarray,
    geometries: tuple[_ColdMapGeometry | None, ...],
    page: int,
    page_transforms: PageTransforms,
) -> _PageSweep:
    """All orientation maps of one page: tops + the page-local winner.

    The page-local winner uses the exact strict-``>`` first-on-tie rule
    of the global sweep, so the global winner is always some page's
    local winner and its retained z map is the one a flat sequential
    loop would have kept.
    """
    tops: list[_MapTop] = []
    best_offset = -1
    best_z: np.ndarray | None = None
    best_peak = (0, 0)
    best_pad = (0, 0)
    for rot_k, geometry in enumerate(geometries):
        if geometry is None:
            continue
        z = _page_candidate_map(values, geometry, page, page_transforms)
        if z.size == 0 or not np.isfinite(z).any():
            continue
        flat = int(np.argmax(z))
        peak_y, peak_x = np.unravel_index(flat, z.shape)
        top = _MapTop(
            float(z[peak_y, peak_x]), int(page),
            (int(peak_y) - geometry.pad_y, int(peak_x) - geometry.pad_x),
            rot_k,
        )
        if best_offset < 0 or top.z > tops[best_offset].z:
            best_offset = len(tops)
            best_z = z
            best_peak = (int(peak_y), int(peak_x))
            best_pad = (geometry.pad_y, geometry.pad_x)
        tops.append(top)
    return _PageSweep(tuple(tops), best_offset, best_z, best_peak, best_pad)


# ------------------------------------------------------------ the cold route

def _page_hypotheses(pages: Sequence[int]) -> tuple[int, ...]:
    """v1's page-domain validation: integers only, order-preserving dedupe."""
    for page in pages:
        value: object = page
        if isinstance(value, bool) or not isinstance(
                value, (int, np.integer)):
            raise TypeError("page hypotheses must be integers")
    unique = tuple(dict.fromkeys(int(page) for page in pages))
    if not unique:
        raise ValueError(
            "Lane C needs at least one explicit page hypothesis")
    return unique


def _refused(
    hypotheses: int, reason: str, budget: AttemptBudget
) -> SearchOutcome:
    """A refusal with no candidate at all — v1's three identical rows."""
    return SearchOutcome(
        False, None, (), hypotheses, reason,
        support_floor=budget.min_support,
    )


def correlate_patch(
    patch: AddressPatch,
    provider: ReferenceFieldProvider,
    pages: Sequence[int],
    budget: AttemptBudget,
    memo: ScoreMemo,
    *,
    sample_key: int,
    config: PlacementConfig,
    page_progress: Callable[[int, int], None] | None = None,
) -> SearchOutcome:
    """Complete Lane-C phase x address search with disjoint validation.

    ``page_progress`` is an optional observer-only heartbeat callback
    (RECEIVE-DESIGN §10.6): it receives ``(page_ordinal, pages_total)``
    at count-bounded points of the page sweep — at most 64 invocations
    per sweep, one every ``ceil(P/64)`` pages.  The bounding is
    count-based (no clock reads), the callback touches no search state,
    and an absent callback adds zero numerical work.
    """
    domain = _page_hypotheses(pages)
    fragment_shape = (int(patch.mask.shape[0]), int(patch.mask.shape[1]))
    hypotheses = hypothesis_count(
        fragment_shape, provider.spec.cells_yx, len(domain),
        allow_overhang=config.allow_overhang,
    )
    if hypotheses > budget.max_hypotheses:
        return _refused(hypotheses, "attempt_budget_exceeded", budget)
    # Keep one top per page/orientation map.  E022's rival set is the
    # top of every losing map plus the spatially distinct second peak of
    # the winning map only — seconds from losing maps were never part of
    # the qualified decision — so a single z map, the running best top's,
    # is retained while sweeping and losing maps never pay a copy +
    # second argmax.  Strict ``>`` replacement reproduces ``max``'s
    # first-on-exact-tie winner in caller page order, then orientation
    # order, exactly as legacy E022 did.
    raw_tops: list[_MapTop] = []
    winner_index = -1
    winner_z: np.ndarray | None = None
    winner_peak_yx = (0, 0)
    winner_pad_yx = (0, 0)
    page_transforms: PageTransforms = {}
    first_reference = provider.page(domain[0])
    geometries = _cold_map_geometries(
        patch.evidence,
        patch.mask,
        first_reference.sites,
        budget,
        allow_overhang=config.allow_overhang,
    )
    if not any(
        geometry is not None and bool(geometry.eligible.any())
        for geometry in geometries
    ):
        # Result-exact early-out: eligibility is page-invariant, so with
        # no origin reaching the support floor in any orientation every
        # page map would be all -inf and the sweep would end
        # insufficient_support anyway.  Measured motivation: 70-cell
        # subdivision children each paid a full 312-page FFT sweep
        # before dying at the 55/parity floor.
        return _refused(hypotheses, "insufficient_support", budget)
    progress_stride = 0
    if page_progress is not None:
        # §10.6 count-based bounding: ceil(P/64) pages per heartbeat.
        progress_stride = -(-len(domain) // 64)
    for page_index, page in enumerate(domain):
        if (page_progress is not None
                and page_index % progress_stride == 0):
            page_progress(page_index + 1, len(domain))
        reference = (
            first_reference if page_index == 0 else provider.page(page)
        )
        if (
            reference.sites is not first_reference.sites
            and not np.array_equal(reference.sites, first_reference.sites)
        ):
            raise ValueError("v1 reference sites must be page-invariant")
        sweep = _page_sweep(
            reference.values, geometries, page, page_transforms)
        for offset, top in enumerate(sweep.tops):
            if winner_index < 0 or top.z > raw_tops[winner_index].z:
                winner_index = len(raw_tops)
                if offset == sweep.best_offset:
                    winner_z = sweep.best_z
                    winner_peak_yx = sweep.best_peak_yx
                    winner_pad_yx = sweep.best_pad_yx
                else:
                    # Transient: superseded by this page's local winner
                    # before the page's tops are exhausted.
                    winner_z = None
            raw_tops.append(top)
    if not raw_tops:
        return _refused(hypotheses, "insufficient_support", budget)
    winner_raw = raw_tops[winner_index]
    assert winner_z is not None
    # The retained map is not consulted after this second-peak recompute,
    # so blanking the winner's neighborhood in place is value-identical
    # to the legacy per-map ``z.copy()`` route.
    radius = config.neighbor_radius_cells
    peak_y, peak_x = winner_peak_yx
    winner_z[
        max(0, peak_y - radius):peak_y + radius + 1,
        max(0, peak_x - radius):peak_x + radius + 1,
    ] = -np.inf
    winner_second: _MapTop | None = None
    if np.isfinite(winner_z).any():
        flat_second = int(np.argmax(winner_z))
        second_y, second_x = np.unravel_index(flat_second, winner_z.shape)
        winner_second = _MapTop(
            float(winner_z[second_y, second_x]), winner_raw.page,
            (
                int(second_y) - winner_pad_yx[0],
                int(second_x) - winner_pad_yx[1],
            ),
            winner_raw.rot_k,
        )
    best = memo.candidate(
        sample_key, patch.evidence, patch.bits, patch.mask,
        winner_raw.page, winner_raw.origin_yx, winner_raw.rot_k, budget,
        "correlation",
    )
    runners: list[CandidateScore] = []
    seen: set[tuple[int, CellYX, int]] = {
        (best.page, best.origin_yx, best.rot_k)
    }
    rival_rows: list[_MapTop] = []
    for map_index, top in enumerate(raw_tops):
        if map_index == winner_index:
            if winner_second is not None:
                rival_rows.append(winner_second)
        else:
            rival_rows.append(top)
    for contender in rival_rows:
        identity = (contender.page, contender.origin_yx, contender.rot_k)
        if identity in seen:
            continue
        if (
            contender.page == best.page and contender.rot_k == best.rot_k
            and max(abs(contender.origin_yx[0] - best.origin_yx[0]),
                    abs(contender.origin_yx[1] - best.origin_yx[1]))
            <= config.neighbor_radius_cells
        ):
            continue
        seen.add(identity)
        runners.append(memo.candidate(
            sample_key, patch.evidence, patch.bits, patch.mask,
            contender.page, contender.origin_yx, contender.rot_k, budget,
            "correlation_runner_up",
        ))
    # This is the exact decision rival used by historical E022.  The full
    # map-top spectrum remains qualification/search working state;
    # downstream semantic audit needs only the selected rival and the
    # resulting gaps.
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
    accepted = _rival_gate(best_whole, rival_mismatch, budget.gate)
    return SearchOutcome(
        accepted,
        best,
        tuple(runners),
        hypotheses,
        "accepted" if accepted else "rival_gap_failed",
        support_floor=budget.min_support,
        rival=rival,
    )


__all__ = [
    "PageTransformKey", "PageTransforms", "SearchOutcome",
    "WHOLE_WORD_PARITY", "correlate_patch",
]
