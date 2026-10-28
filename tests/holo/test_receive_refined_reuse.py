"""Exact-work reuse for the post-E023c payload delta (v0.42 R-level seam).

The historical generation-swap contract (an adopted refinement replaced
the whole inline payload generation) dissolved with RECEIVE-DESIGN v0.42:
refinement now runs in its own R(Lk) level and emits an
affected-regions-only delta.  Its replacement differential, pinned here:
``collect_refined_region_delta`` equals a FORCED FULL RECOMPUTE of the
same regions at the refined poses (``collect_capture_evidence`` over the
refined address restricted to the affected regions) — the same exactness
discipline at the new seam, byte-for-byte through windows, owner freeze,
compact blocks, attempts, certificates, and divergences.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import pickle

import numpy as np
import pytest

from holo.receive import (
    _payload_reuse,
    _payload_sampling,
    certified_cascade,
    payload,
    payload_engine,
    production_payload,
)
from holo.receive.certified_cascade import refine_address_once
from holo.receive.certified_refine import SegmentRefinementRequest
from holo.receive.evidence_blocks import blocks_from_frontier
from holo.receive.payload_engine import run_attempts
from holo.receive.payload_model import EvidenceSource, PlacementModelError
from holo.receive.placement.model import (
    AddressResult,
    CandidateScore,
    PlacedPatch,
)
from _e023c_fixtures import (
    _page_fixture,
    _segment_fixture,
)
from holo.receive.records import (
    certificate_divergence as records_certificate_divergence,
    CertificateStore,
    certificate_record_from_user_bits,
)
from holo.receive.session import BarrierDelta
from holo.receive.state_codec import canonical_bytes, encode_typed


class _CountingRaster:
    def __init__(self, raster: object) -> None:
        self.raster = raster
        self.shape = raster.shape
        self.dpi = raster.dpi
        self.calls = 0

    def crop_luma(
        self, r0: int, r1: int, c0: int, c1: int
    ) -> np.ndarray:
        self.calls += 1
        return self.raster.crop_luma(r0, r1, c0, c1)


def _patch(fixture: object, patch_id: int, *, redundant: bool) -> PlacedPatch:
    placed = fixture.request.placed
    candidate = CandidateScore(
        0, placed.page_origin_yx, 0,
        0.0, 0.0, 0, 0, 100, 100, 10.0, True, "reuse-test",
    )
    cells = (
        placed.audited_cells_yx.astype(np.int64)
        + np.asarray(placed.page_origin_yx, np.int64)
    ).astype(np.int32)
    return PlacedPatch(
        patch_id,
        placed.segment.window.region_index,
        0,
        "reuse-test",
        candidate,
        (),
        placed,
        (),
        redundant,
        cells,
    )


def _fixture() -> tuple[object, _CountingRaster, EvidenceSource, AddressResult]:
    page = _page_fixture()
    segments = (
        _segment_fixture(
            page,
            window_id=0,
            region_index=0,
            page_origin_yx=(0, 0),
            shift_yx_cells=(0.125, -0.125),
        ),
        _segment_fixture(
            page,
            window_id=1,
            region_index=0,
            page_origin_yx=(128, 0),
            shift_yx_cells=(0.0, 0.0),
        ),
        _segment_fixture(
            page,
            window_id=2,
            region_index=1,
            page_origin_yx=(0, 128),
            shift_yx_cells=(0.0, 0.0),
        ),
    )
    patches = tuple(
        _patch(row, index, redundant=index != 0)
        for index, row in enumerate(segments)
    )
    address = AddressResult(
        patches, (), (), ((0, "accepted"), (1, "accepted")), 3)
    source = EvidenceSource(
        hashlib.sha256(b"refined-reuse").hexdigest(), "reuse-lane")
    return page, _CountingRaster(page.raster), source, address


def _run_k(
    spec: object,
    blocks: tuple,
    source: EvidenceSource,
    store: CertificateStore | None = None,
) -> tuple[object, CertificateStore]:
    """Run the unified K attempt schedule; the leaf's rows ARE the records."""
    store = store if store is not None else CertificateStore(spec)

    class _Leaf:
        def __init__(self) -> None:
            self.attempts, self.certificates, self.views = [], [], []
            self._seen: set[str] = set()

        def unresolved_streams(self, address):
            return store.unresolved_streams(address)

        def attempt(self, view, stream_id, stage):
            record, certificate = payload.attempt_k_tile(
                view.llr_cells_f64, spec, view.address, stage,
                source_sha256=source.source_sha256,
                lane_id=source.lane_id,
                component_block_ids=view.component_block_ids,
                dependency_certificate_ids=view.dependency_certificate_ids)
            if record.attempt_id in self._seen:
                return None
            self._seen.add(record.attempt_id)
            store.record_attempt(record, certificate)
            self.attempts.append(record)
            self.views.append(view)
            if certificate is not None:
                self.certificates.append(certificate)
            return record

    leaf = _Leaf()
    run_attempts(blocks, blocks, lane_id=source.lane_id, leaf=leaf)
    return leaf, store


def _state_delta_bytes(
    evidence: object,
    spec: object,
    source: EvidenceSource,
) -> bytes:
    dependency = hashlib.sha256(b"refinement-certificate").hexdigest()
    dependencies = {
        row.placement_id: ((dependency,) if row.patch_id == 0 else ())
        for row in evidence.windows
    }
    blocks = blocks_from_frontier(evidence, dependencies)
    leaf, store = _run_k(spec, blocks, source)
    assert blocks
    assert leaf.attempts
    assert leaf.certificates
    delta = BarrierDelta(
        blocks=blocks,
        attempts=tuple(leaf.attempts),
        certificates=tuple(leaf.certificates),
        divergences=records_certificate_divergence(
            blocks, store.certificates(), spec),
    )
    return canonical_bytes(encode_typed(delta))


def test_refine_delta_equals_forced_full_recompute_of_affected_regions() -> None:
    """The v0.42 replacement differential for the old generation swap."""
    page, raster, source, address = _fixture()
    generation0 = payload.collect_capture_evidence(
        raster,
        source,
        address,
        page.spec,
        detector_profile=payload.CONTEXT_PROFILE,
    )
    # Region 0 starts context-adopted, exercising exact restoration of its
    # unchanged window to marginal PAVA before the revised region is replayed.
    assert generation0.context_decisions[0].adopted
    refinement = refine_address_once(
        raster, address, generation0, page.spec, page.certificates)
    changed = tuple(
        row.patch_id for row in refinement.summaries
        if row.metrics.adopted)
    assert changed == (0,)

    # Forced full recompute of exactly the affected regions: the ordinary
    # generation-zero path over the REFINED address, restricted to region
    # 0's placements (patch 0 adopted, patch 1 region-coupled).
    raster.calls = 0
    oracle = payload.collect_capture_evidence(
        raster,
        source,
        refinement.address,
        page.spec,
        included_patch_ids=frozenset((0, 1)),
        detector_profile=payload.CONTEXT_PROFILE,
    )
    oracle_calls = raster.calls
    raster.calls = 0
    delta = payload.collect_refined_region_delta(
        raster,
        source,
        address,
        refinement.address,
        generation0,
        page.spec,
        changed_patch_ids=changed,
        detector_profile=payload.CONTEXT_PROFILE,
    )

    # Oracle samples both region-0 windows; the delta resamples only the
    # adopted patch and restores its sibling from retained work.
    assert oracle_calls == 2
    assert raster.calls == 1
    # The delta covers ONLY the affected region: region 1 (unchanged)
    # contributes nothing at the R barrier.
    assert tuple(row.patch_id for row in delta.windows) == (0, 1)
    assert {row.region_id.rsplit("/", 1)[1]
            for row in delta.windows} == {"region-0"}
    assert len(delta.context_decisions) == 1
    assert pickle.dumps(delta, protocol=5) == pickle.dumps(
        oracle, protocol=5)
    assert _state_delta_bytes(
        delta, page.spec, source) == _state_delta_bytes(
            oracle, page.spec, source)

    progress: list[tuple[str, tuple[int, ...]]] = []
    payload.collect_refined_region_delta(
        raster,
        source,
        address,
        refinement.address,
        generation0,
        page.spec,
        changed_patch_ids=changed,
        detector_profile=payload.CONTEXT_PROFILE,
        region_progress=lambda region_id, windows, _decision: progress.append(
            (region_id, tuple(row.patch_id for row in windows))),
    )
    assert len(progress) == 1
    assert progress[0][0].endswith("/region-0")
    # Patch 0 was resampled; patch 1 shares its coupled context fit.  The
    # unaffected region 1 emits no delta progress callback at all.
    assert progress[0][1] == (0, 1)


def test_refine_skips_refused_generation_zero_window() -> None:
    """A starved-refused gen-0 window is pool bookkeeping, not a detector.

    Second regression pin of the refused-ledger class (2026-08-02):
    ``refine_address_once`` built a ``SegmentRefinementRequest`` for every
    promoted patch, and the request constructor correctly refuses a
    non-accepted generation zero — so one starved window killed the whole
    R level.  The refused patch must instead be skipped with an explicit
    summary; accepted siblings refine byte-identically.
    """
    page, raster, source, address = _fixture()
    generation0 = payload.collect_capture_evidence(
        raster,
        source,
        address,
        page.spec,
        detector_profile=payload.CONTEXT_PROFILE,
    )
    baseline = refine_address_once(
        raster, address, generation0, page.spec, page.certificates)

    victim = {int(row.patch_id): row for row in generation0.windows}[1]
    refused = replace(
        victim,
        accepted=False,
        refusal_reason="search_class_starved",
        heldout_logloss=None,
        calibration_score_nodes=np.zeros(0),
        calibration_probability_nodes=np.zeros(0),
        baseline_printed_llr=np.zeros(0, np.float32),
        printed_llr=np.zeros(0, np.float32),
        detector_profile=payload.PAVA_PROFILE,
        context_decision_id=None,
    )
    # The constructor invariant stands; the cascade must route around it.
    placed = {
        int(row.patch_id): row for row in address.payload_placements
    }[1].segment
    with pytest.raises(ValueError, match="accepted generation-zero"):
        SegmentRefinementRequest(placed, refused, None)

    capture = payload.freeze_capture_evidence(
        source,
        page.spec,
        tuple(refused if int(row.patch_id) == 1 else row
              for row in generation0.windows),
        generation0.context_decisions,
    )
    refinement = refine_address_once(
        raster, address, capture, page.spec, page.certificates)

    summaries = {int(row.patch_id): row for row in refinement.summaries}
    promoted_ids = {int(row.patch_id) for row in address.payload_placements}
    assert set(summaries) == promoted_ids
    skipped = summaries[1]
    assert skipped.metrics.reason == "refused_generation0"
    assert not skipped.metrics.eligible
    assert skipped.adopted_pose is None
    assert skipped.dependency_certificate_ids == ()
    baseline_rows = {int(row.patch_id): row for row in baseline.summaries}
    for patch_id in sorted(promoted_ids - {1}):
        assert summaries[patch_id].metrics == baseline_rows[patch_id].metrics
        assert (summaries[patch_id].adopted_pose
                == baseline_rows[patch_id].adopted_pose)
        assert (summaries[patch_id].dependency_certificate_ids
                == baseline_rows[patch_id].dependency_certificate_ids)
    assert refinement.adopted == baseline.adopted


def test_certified_k_tiles_prune_before_blocks_and_attempt_views(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, raster, source, address = _fixture()
    evidence = payload.collect_capture_evidence(
        raster,
        source,
        address,
        page.spec,
        detector_profile=payload.CONTEXT_PROFILE,
    )
    full_blocks = blocks_from_frontier(evidence)
    assert len(full_blocks) > 1
    certified_address = full_blocks[0].address
    certificate = next(
        row for row in page.certificates
        if (row.page, *row.tile_yx) == certified_address
    )
    certified = frozenset((certified_address,))

    unresolved = production_payload._prune_certified_k_owners(
        evidence, certified)
    pruned_blocks = blocks_from_frontier(unresolved)
    expected_blocks = tuple(
        row for row in full_blocks if row.address != certified_address)

    # The cut happens after owner freeze, so every unresolved compact block is
    # byte-identical to the unpruned oracle and no terminal block is retained.
    assert tuple(row.to_bytes() for row in pruned_blocks) == tuple(
        row.to_bytes() for row in expected_blocks)
    assert all(row.address != certified_address for row in pruned_blocks)
    fully_terminal = production_payload._prune_certified_k_owners(
        evidence,
        frozenset(row.address for row in full_blocks),
    )
    assert fully_terminal.pages == ()
    assert blocks_from_frontier(fully_terminal) == ()

    def seeded_store() -> CertificateStore:
        store = CertificateStore(page.spec)
        assert store.add(certificate)
        return store

    oracle_leaf, oracle_store = _run_k(
        page.spec, full_blocks, source, store=seeded_store())

    materialized: list[tuple[int, int, int]] = []
    actual_tile_attempt_view = payload_engine.tile_attempt_view

    def tracked_tile_attempt_view(rows):
        selected = tuple(rows)
        materialized.append(selected[0].address)
        return actual_tile_attempt_view(selected)

    monkeypatch.setattr(
        payload_engine, "tile_attempt_view", tracked_tile_attempt_view)
    actual_leaf, actual_store = _run_k(
        page.spec, pruned_blocks, source, store=seeded_store())

    assert materialized
    assert certified_address not in materialized
    # All unresolved decoding products remain exactly unchanged.
    assert pickle.dumps(
        tuple(actual_leaf.attempts), protocol=5) == pickle.dumps(
            tuple(oracle_leaf.attempts), protocol=5)
    assert pickle.dumps(
        tuple(actual_leaf.views), protocol=5) == pickle.dumps(
            tuple(oracle_leaf.views), protocol=5)
    assert pickle.dumps(
        tuple(actual_leaf.certificates), protocol=5) == pickle.dumps(
            tuple(oracle_leaf.certificates), protocol=5)

    # Divergence auditing intentionally disappears with terminal blocks —
    # both stores hold identical certified truth, so the only missing audit
    # rows are exactly those of the pruned terminal block(s).
    assert oracle_store.certificates() == actual_store.certificates()
    oracle_divergences = records_certificate_divergence(
        full_blocks, oracle_store.certificates(), page.spec)
    actual_divergences = records_certificate_divergence(
        pruned_blocks, actual_store.certificates(), page.spec)
    terminal_ids = {
        row.block_id for row in full_blocks
        if (row.page, *row.tile_yx) == certified_address
    }
    assert terminal_ids & {
        row.evidence_block_id for row in oracle_divergences}
    assert actual_divergences == tuple(
        row for row in oracle_divergences
        if row.evidence_block_id not in terminal_ids)


def test_terminal_k_region_stops_before_numerics_and_mixed_region_is_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, raster, source, address = _fixture()

    def payload_addresses(patch: PlacedPatch) -> set[tuple[int, int, int]]:
        rows = _payload_sampling._window_rows(patch, page.spec)
        cells = rows.page_cells_yx[
            payload.payload_cell_mask(page.spec, rows.page_cells_yx)
        ]
        return {
            (int(patch.candidate.page), int(y) // 64, int(x) // 64)
            for y, x in cells
        }

    patches = {int(row.patch_id): row for row in address.payload_placements}
    # Region 1 is wholly terminal.  Region 0 is deliberately mixed: one of
    # patch 0's tiles is terminal while its other tiles remain unresolved.
    terminal = payload_addresses(patches[2])
    terminal.add(sorted(payload_addresses(patches[0]))[0])
    included = payload.unresolved_region_patch_ids(
        address, page.spec, frozenset(terminal))
    assert included == frozenset((0, 1))

    raster.calls = 0
    oracle_generation = payload.collect_capture_evidence(
        raster,
        source,
        address,
        page.spec,
        detector_profile=payload.CONTEXT_PROFILE,
    )
    assert raster.calls == 3
    raster.calls = 0
    oracle_refinement = refine_address_once(
        raster,
        address,
        oracle_generation,
        page.spec,
        page.certificates,
    )
    assert raster.calls == 2
    oracle_changed = tuple(
        row.patch_id for row in oracle_refinement.summaries
        if row.metrics.adopted
    )

    context_regions: list[str] = []
    actual_apply_region_context = payload.apply_region_context

    def tracked_apply_region_context(rows, label_rows=()):
        selected = tuple(rows)
        context_regions.append(selected[0].region_id)
        return actual_apply_region_context(selected, label_rows)

    prepared_regions: list[int] = []
    actual_prepare_region_image = certified_cascade.prepare_region_image

    def tracked_prepare_region_image(actual_raster, region_index, segments):
        prepared_regions.append(int(region_index))
        return actual_prepare_region_image(
            actual_raster, region_index, segments)

    monkeypatch.setattr(
        payload, "apply_region_context", tracked_apply_region_context)
    monkeypatch.setattr(
        certified_cascade,
        "prepare_region_image",
        tracked_prepare_region_image,
    )

    generation_progress: list[str] = []
    raster.calls = 0
    generation = payload.collect_capture_evidence(
        raster,
        source,
        address,
        page.spec,
        included_patch_ids=included,
        detector_profile=payload.CONTEXT_PROFILE,
        region_progress=lambda region_id, _windows, _decision:
            generation_progress.append(region_id),
    )
    assert raster.calls == 2
    assert tuple(row.patch_id for row in generation.windows) == (0, 1)
    assert len(context_regions) == 1
    assert generation_progress == context_regions
    assert context_regions[0].endswith("/region-0")

    included_region_ids = {
        row.region_id for row in oracle_generation.windows
        if row.patch_id in included
    }
    expected_generation = payload.freeze_capture_evidence(
        source,
        page.spec,
        tuple(
            row for row in oracle_generation.windows
            if row.patch_id in included
        ),
        tuple(
            row for row in oracle_generation.context_decisions
            if row.region_id in included_region_ids
        ),
    )
    assert pickle.dumps(generation, protocol=5) == pickle.dumps(
        expected_generation, protocol=5)

    raster.calls = 0
    refinement = certified_cascade.refine_address_once(
        raster,
        address,
        generation,
        page.spec,
        page.certificates,
        included_patch_ids=included,
    )
    assert raster.calls == 1
    assert prepared_regions == [0]
    assert tuple(row.patch_id for row in refinement.summaries) == (0, 1)
    changed = tuple(
        row.patch_id for row in refinement.summaries
        if row.metrics.adopted
    )
    assert changed == tuple(
        patch_id for patch_id in oracle_changed if patch_id in included)

    refined_progress: list[str] = []
    raster.calls = 0
    refined = payload.collect_refined_region_delta(
        raster,
        source,
        address,
        refinement.address,
        generation,
        page.spec,
        changed_patch_ids=changed,
        included_patch_ids=included,
        terminal_addresses=frozenset(terminal),
        detector_profile=payload.CONTEXT_PROFILE,
        region_progress=lambda region_id, _windows, _decision:
            refined_progress.append(region_id),
    )
    assert raster.calls == 1
    assert refined_progress == generation_progress
    assert context_regions == generation_progress + refined_progress

    # Forced full recompute of the affected region under the SAME
    # terminal set: the ordinary generation-zero path over the refined
    # address restricted to the included (mixed-region) domain.
    forced = payload.collect_capture_evidence(
        raster,
        source,
        refinement.address,
        page.spec,
        included_patch_ids=included,
        terminal_addresses=frozenset(terminal),
        detector_profile=payload.CONTEXT_PROFILE,
    )
    assert {row.region_id for row in refined.windows} <= included_region_ids
    assert pickle.dumps(refined, protocol=5) == pickle.dumps(
        forced, protocol=5)


def test_terminal_k_pruning_still_validates_complete_placement_geometry() -> None:
    page, _raster, _source, address = _fixture()
    terminal = frozenset(
        (page_index, tile_y, tile_x)
        for page_index in range(page.spec.max_pages)
        for tile_y in range(page.spec.layout.tiles_yx[0])
        for tile_x in range(page.spec.layout.tiles_yx[1])
    )
    first = address.payload_placements[0]
    malformed = replace(
        first,
        segment=replace(
            first.segment,
            rot_k=(first.segment.rot_k + 1) % 4,
        ),
    )
    malformed_address = replace(
        address,
        placements=(
            malformed,
            *address.placements[1:],
        ),
    )

    with pytest.raises(
        PlacementModelError,
        match="inconsistent window orientation",
    ):
        payload.unresolved_region_patch_ids(
            malformed_address, page.spec, terminal)


def test_filter_policy_change_resamples_only_its_complete_region() -> None:
    page, raster, source, address = _fixture()
    generation0 = payload.collect_capture_evidence(
        raster,
        source,
        address,
        page.spec,
        detector_profile=payload.PAVA_PROFILE,
    )
    patch = address.payload_placements[0]
    pose = patch.segment.segment.pose
    revised_pose = replace(
        pose,
        jacobian_yx=((10.0, 0.0), (0.0, 10.0)),
        pitch_px=10.0,
    )
    revised_patch = replace(
        patch,
        segment=replace(
            patch.segment,
            segment=replace(patch.segment.segment, pose=revised_pose),
        ),
    )
    refined = replace(
        address,
        placements=(revised_patch, *address.placements[1:]),
    )

    raster.calls = 0
    oracle = payload.collect_capture_evidence(
        raster,
        source,
        refined,
        page.spec,
        detector_profile=payload.PAVA_PROFILE,
    )
    assert raster.calls == 3
    raster.calls = 0
    sampled, affected, resampled, _label_rows = (
        _payload_reuse.sample_refined_reusing_generation(
            raster,
            source,
            address,
            refined,
            generation0.windows,
            page.spec,
            changed_patch_ids=(0,),
        )
    )
    reused = payload.freeze_capture_evidence(source, page.spec, sampled)

    assert len(affected) == 1
    assert resampled == frozenset((0, 1))
    assert raster.calls == 2
    assert pickle.dumps(reused, protocol=5) == pickle.dumps(
        oracle, protocol=5)
