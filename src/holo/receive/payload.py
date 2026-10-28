"""E023/E023b payload emission over authoritative E022 window poses.

This is the photometric/merge seam between placement and the tile decoder:

* one raw-luma crop and one 0.7-cell box prefilter per E021 region;
* one order-1 read for every E022-audited cell through its window pose;
* per-window PAVA with the exact absolute-cell parity split;
* the registered per-region context arm, adopted only on held-out gain;
* one owner per physical capture/page/payload cell; and
* one scan attempt per physical acquisition before certificate union,
  followed by an LLR sum of same-lane acquisition stragglers.

LLRs are in the PRINTED-CELL domain, positive for ink. Descrambling and slot
inversion belong to ``receive.tiles``; refused windows emit no evidence.
"""
from __future__ import annotations

from typing import Callable, Iterable

import numpy as np

from ..core.ldpc import tile as ldpc_tile
from ..format.descriptor import FormatSpec
from . import tiles
from ._payload_context import apply_region_context
from ._payload_reuse import sample_refined_reusing_generation
from ._payload_sampling import (
    APERTURE_CELLS,
    _site_lookup,
    _window_rows,
    format_reference_values,
    rotated_points,
    sample_and_calibrate,
)
from .evidence_blocks import EvidenceBlock, TileAttemptView, tile_attempt_view
from .evidence import (
    AttemptStage,
    AttemptState,
    TileAttemptRecord,
    TileCertificateRecord,
)
from .payload_model import (
    CONTEXT_PROFILE,
    PAVA_PROFILE,
    CaptureEvidence,
    ContextDecision,
    DetectorProfile,
    DivergenceRecord,
    EvidenceSource,
    OwnedPageEvidence,
    PlacementModelError,
    RawLumaRaster,
    WindowEvidence,
    divergence_identity,
    freeze_page_owners,
)
from .placement.model import AddressResult, PlacedPatch
from .records import (
    certificate_record_from_user_bits,
    printed_cells_from_record,
    stream_attempt_identity,
)


def payload_cell_mask(spec: FormatSpec, cells_yx: np.ndarray) -> np.ndarray:
    """Return the exact format-v1 cargo mask for absolute page cells."""
    kind, _index = _site_lookup(spec.family_seed, spec.n_filler)
    cells = np.asarray(cells_yx, np.int64)
    return kind[cells[:, 0] % 64, cells[:, 1] % 64] < 0


def unresolved_region_patch_ids(
    address: AddressResult,
    spec: FormatSpec,
    terminal_addresses: frozenset[tuple[int, int, int]],
) -> frozenset[int]:
    """Select complete regions that can still emit unresolved K payload.

    Context fitting is region-coupled, so a mixed region keeps every one of
    its patches.  A region whose payload cells all belong to terminal tiles
    is validated geometrically here, then removed before raster sampling,
    context fitting, certified refinement, and transient progress.

    Interior helper: the terminal set is minted upstream from the durable
    certificate index (mint-once, kiss validation-boundary ruling).
    """
    by_region: dict[int, list[PlacedPatch]] = {}
    for patch in address.payload_placements:
        by_region.setdefault(int(patch.region_index), []).append(patch)
    included: set[int] = set()
    tiles_x = spec.layout.tiles_yx[1]
    for patches in by_region.values():
        unresolved = False
        for patch in patches:
            page = int(patch.candidate.page)
            aligned = _window_rows(patch, spec)
            cells = np.asarray(aligned.page_cells_yx, np.int64)
            cells = cells[payload_cell_mask(spec, cells)]
            if not cells.size:
                continue
            tile_codes = np.unique(
                (cells[:, 0] // 64) * tiles_x + cells[:, 1] // 64
            )
            if any(
                (page, *divmod(int(code), tiles_x))
                not in terminal_addresses
                for code in tile_codes
            ):
                unresolved = True
                break
        if unresolved:
            included.update(int(patch.patch_id) for patch in patches)
    return frozenset(included)


def freeze_capture_evidence(
    source: EvidenceSource,
    spec: FormatSpec,
    windows: Iterable[WindowEvidence],
    context_decisions: Iterable[ContextDecision] = (),
) -> CaptureEvidence:
    """Freeze one deterministic owner per payload cell; retain all windows."""
    rows = tuple(windows)
    decisions = tuple(context_decisions)
    if any(row.source != source for row in rows):
        raise ValueError("payload: cannot freeze another source's windows")
    if len({row.patch_id for row in rows}) != len(rows):
        raise ValueError("payload: windows repeat a numeric patch ordinal")
    if len({row.placement_id for row in rows}) != len(rows):
        raise ValueError("payload: windows repeat a placement identity")
    index_by_identity = {id(row): index for index, row in enumerate(rows)}

    # Best held-out loss, then numeric E022 patch ordinal; refused rows
    # lose.  The competition itself is the shared K/color one-owner core.
    def candidates() -> Iterable[
        tuple[int, int, np.ndarray, np.ndarray, np.ndarray]
    ]:
        order = sorted(
            (row for row in rows if row.accepted),
            key=lambda row: (float(row.heldout_logloss), int(row.patch_id)))
        for row in order:
            row_indices = np.flatnonzero(
                payload_cell_mask(spec, row.page_cells_yx)
            ).astype(np.int32, copy=False)
            if not row_indices.size:
                continue
            yield (
                index_by_identity[id(row)],
                row.page,
                row.page_cells_yx[row_indices],
                row_indices,
                row.printed_llr[row_indices].reshape(-1, 1),
            )

    pages = tuple(
        OwnedPageEvidence(
            page_number, cells, values[:, 0], window_indices, row_indices)
        for page_number, cells, values, window_indices, row_indices
        in freeze_page_owners(candidates(), spec.layout.cells_yx))
    return CaptureEvidence(
        source, spec.spec_id, rows, decisions, pages)


def collect_capture_evidence(
    raster: RawLumaRaster,
    source: EvidenceSource,
    address: AddressResult,
    spec: FormatSpec,
    *,
    detector_profile: DetectorProfile = CONTEXT_PROFILE,
    included_patch_ids: frozenset[int] | None = None,
    terminal_addresses: frozenset[tuple[int, int, int]] = frozenset(),
    region_progress: Callable[
        [str, tuple[WindowEvidence, ...], ContextDecision | None], None
    ] | None = None,
) -> CaptureEvidence:
    """Complete sampling -> calibration -> optional context -> owner path.

    ``region_progress`` observes completed, independently profiled regions.
    It runs before the one global owner freeze, so it cannot expose or affect
    provisional ownership.  Splitting the context call is exact because the
    registered context model has always fitted each region independently.
    """
    if detector_profile not in (PAVA_PROFILE, CONTEXT_PROFILE):
        raise ValueError("payload: unknown detector profile")
    profiled_by_id: dict[str, WindowEvidence] = {}
    decisions: list[ContextDecision] = []

    def complete_region(
        rows: tuple[WindowEvidence, ...],
        label_rows: tuple[WindowEvidence, ...] = (),
    ) -> None:
        if not rows:
            return
        region_id = rows[0].region_id
        if any(row.region_id != region_id
               for row in (*rows, *label_rows)):
            raise ValueError("payload: sampled region identities disagree")
        if detector_profile == CONTEXT_PROFILE:
            # v0.33 D7: label rows join the region's fit populations and
            # are never profiled, owned, or returned.
            profiled, region_decisions = apply_region_context(
                rows, label_rows)
            if len(region_decisions) != 1:
                raise ValueError("payload: one region produced multiple decisions")
            decision: ContextDecision | None = region_decisions[0]
            decisions.append(decision)
        else:
            profiled = rows
            decision = None
        profiled_by_id.update((row.placement_id, row) for row in profiled)
        if region_progress is not None:
            region_progress(region_id, tuple(profiled), decision)
    baseline = sample_and_calibrate(
        raster,
        source,
        address,
        spec,
        included_patch_ids=included_patch_ids,
        terminal_addresses=terminal_addresses,
        region_progress=complete_region,
    )
    profiled_rows = tuple(
        profiled_by_id[row.placement_id] for row in baseline)
    # The historical whole-capture context call traversed region identities
    # lexicographically.  Sampling stays in physical region order, while the
    # durable decision ledger preserves that exact historical ordering.
    ordered_decisions = tuple(sorted(
        decisions, key=lambda row: row.region_id))
    return freeze_capture_evidence(
        source, spec, profiled_rows, ordered_decisions)


def collect_refined_region_delta(
    raster: RawLumaRaster,
    source: EvidenceSource,
    baseline_address: AddressResult,
    refined_address: AddressResult,
    generation0: CaptureEvidence,
    spec: FormatSpec,
    *,
    changed_patch_ids: Iterable[int],
    included_patch_ids: frozenset[int] | None = None,
    terminal_addresses: frozenset[tuple[int, int, int]] = frozenset(),
    detector_profile: DetectorProfile = CONTEXT_PROFILE,
    region_progress: Callable[
        [str, tuple[WindowEvidence, ...], ContextDecision | None], None
    ] | None = None,
) -> CaptureEvidence:
    """Collect the R-level payload delta: affected regions ONLY (v0.42).

    Pose refinement changes only named patch poses.  A region containing a
    revised pose re-derives completely — its changed patches resample (or
    the whole region, if its integer filter policy changed), its unchanged
    windows restore to their retained marginal PAVA state, and the
    region-coupled context path reruns over the pool law's full population
    (placements UNION labels, L5).  Regions without an adopted pose
    contribute NOTHING: the returned evidence contains exactly the
    affected regions' windows and decisions, owner-frozen WITHIN this
    delta.  The base lane's committed evidence stands untouched (its own
    namespace; only certificates cross lanes), so the delta is the entire
    R-barrier payload emission.

    Successor seam of the retired whole-capture
    ``collect_refined_capture_evidence`` (its unchanged-region reuse
    dissolves with the inline refinement schedule); the exactness
    discipline is unchanged and pinned by the re-scoped refined-reuse
    differential: this delta equals a forced full recompute of the same
    regions at the refined poses.
    """
    if not isinstance(generation0, CaptureEvidence):
        raise TypeError("payload: refined collection needs CaptureEvidence")
    if generation0.source != source or generation0.spec_id != spec.spec_id:
        raise ValueError(
            "payload: generation zero belongs to another source or format")
    if detector_profile not in (PAVA_PROFILE, CONTEXT_PROFILE):
        raise ValueError("payload: unknown detector profile")

    baseline_regions = {row.region_id for row in generation0.windows}
    old_decisions = {
        row.region_id: row for row in generation0.context_decisions}
    if len(old_decisions) != len(generation0.context_decisions):
        raise ValueError("payload: generation zero repeats a context region")
    if detector_profile == CONTEXT_PROFILE:
        if set(old_decisions) != baseline_regions:
            raise ValueError(
                "payload: context generation zero omitted a region decision")
    elif old_decisions or any(
            row.detector_profile != PAVA_PROFILE
            for row in generation0.windows):
        raise ValueError(
            "payload: PAVA generation zero contains context profiling")

    sampled, affected_regions, _resampled_patch_ids, refined_label_rows = (
        sample_refined_reusing_generation(
            raster, source, baseline_address, refined_address,
            generation0.windows, spec,
            changed_patch_ids=changed_patch_ids,
            included_patch_ids=included_patch_ids,
            terminal_addresses=terminal_addresses,
        )
    )
    labels_by_region: dict[str, list[WindowEvidence]] = {}
    for row in refined_label_rows:
        labels_by_region.setdefault(row.region_id, []).append(row)
    by_region: dict[str, list[WindowEvidence]] = {}
    for row in sampled:
        by_region.setdefault(row.region_id, []).append(row)
    if set(by_region) != baseline_regions:
        raise ValueError("payload: refined sampling changed the region domain")

    profiled_by_id: dict[str, WindowEvidence] = {}
    decisions: list[ContextDecision] = []
    for region_id in sorted(affected_regions):
        region_rows = tuple(by_region[region_id])
        if detector_profile == CONTEXT_PROFILE:
            profiled, region_decisions = apply_region_context(
                region_rows,
                tuple(labels_by_region.get(region_id, ())))
            if len(region_decisions) != 1:
                raise ValueError(
                    "payload: one region produced multiple decisions")
            decision: ContextDecision | None = region_decisions[0]
            decisions.append(decision)
        else:
            profiled = region_rows
            decision = None
        profiled_by_id.update(
            (row.placement_id, row) for row in profiled)
        if region_progress is not None:
            region_progress(region_id, tuple(profiled), decision)

    profiled_rows = tuple(
        profiled_by_id[row.placement_id] for row in sampled
        if row.region_id in affected_regions)
    ordered_decisions = tuple(sorted(
        decisions, key=lambda row: row.region_id))
    return freeze_capture_evidence(
        source, spec, profiled_rows, ordered_decisions)


def attempt_k_tile(
    llr_cells: np.ndarray,
    spec: FormatSpec,
    address: tuple[int, int, int],
    stage: AttemptStage,
    *,
    source_sha256: str,
    lane_id: str,
    component_block_ids: tuple[str, ...],
    dependency_certificate_ids: tuple[str, ...] = (),
) -> tuple[TileAttemptRecord, TileCertificateRecord | None]:
    """The K/main numerical leaf: one tile evaluation to durable records.

    Mirrors :func:`~holo.receive.color_attempts.attempt_color_tile` — same
    identity/minting family, same record shapes (family unification
    2026-07-30).  Never exposes uncertified payload bits.
    """
    page, ty, tx = address
    counter, page, ty, tx = tiles._validate_tile_address(
        spec, spec.tile_counter(page, ty, tx), page, ty, tx)
    attempt_id = stream_attempt_identity(
        spec, address, "main", stage, component_block_ids)
    max_iters = (
        tiles.RETRY_BP_MAX_ITERS
        if stage is AttemptStage.RETRY150
        else tiles.BASELINE_BP_MAX_ITERS
    )
    x = tiles._as_tile_llrs(llr_cells)
    n_informative = tiles._informative_count(x, spec)
    common = dict(
        attempt_id=attempt_id,
        source_sha256=source_sha256,
        lane_id=lane_id,
        page=page,
        tile_yx=(ty, tx),
        stage=stage,
        n_informative=n_informative,
        component_block_ids=component_block_ids,
        dependency_certificate_ids=dependency_certificate_ids,
        stream_id="main",
    )
    if n_informative < tiles.k_eff_bits(spec):
        return TileAttemptRecord(
            **common, state=AttemptState.BELOW_ATTEMPT_FLOOR,
            n_iters=0, syndrome_ok=None, crc_ok=None), None
    llr = tiles._descramble_validated(x, spec, page, ty, tx)
    a_t, b_t = tiles._slot_permutation(
        spec.seed, counter, spec.n_transmitted_slots)
    fr = ldpc_tile.decode_tile(
        llr.ravel(), spec.rate_id, tiles._geometry(spec).site_flat,
        a_t, b_t, max_iters=max_iters, alpha=tiles.BP_ALPHA)
    # decode_tile documents ok == syndrome_ok AND crc_ok; VERIFIED here
    # because `ok` is all that stands between a BP fixed point and a
    # certificate.
    if not (fr.ok and fr.syndrome_ok and fr.crc_ok
            and fr.user_bits is not None):
        return TileAttemptRecord(
            **common, state=AttemptState.ATTEMPTED_FAILED,
            n_iters=fr.n_iters, syndrome_ok=fr.syndrome_ok,
            crc_ok=fr.crc_ok), None
    certificate = certificate_record_from_user_bits(
        spec,
        page=page,
        tile_yx=(ty, tx),
        stream_id="main",
        user_bits=np.asarray(fr.user_bits, np.uint8),
        origin_attempt_id=attempt_id,
        dependency_certificate_ids=dependency_certificate_ids,
    )
    return TileAttemptRecord(
        **common, state=AttemptState.CERTIFIED,
        n_iters=fr.n_iters, syndrome_ok=True, crc_ok=True,
        certificate_id=certificate.certificate_id), certificate


__all__ = ["APERTURE_CELLS", "CONTEXT_PROFILE", "PAVA_PROFILE",
           "CaptureEvidence", "ContextDecision",
           "DetectorProfile", "DivergenceRecord",
           "EvidenceSource",
           "OwnedPageEvidence", "PlacementModelError",
           "RawLumaRaster",
           "WindowEvidence", "apply_region_context", "attempt_k_tile",
           "collect_capture_evidence", "collect_refined_region_delta",
           "format_reference_values",
           "freeze_capture_evidence", "rotated_points", "divergence_identity",
           "sample_and_calibrate",
           "unresolved_region_patch_ids"]
