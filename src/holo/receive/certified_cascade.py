"""One faithful E023c certified forward-refinement opportunity.

The current-lane E023b generation zero is immutable input, and only
certificates committed before the lane barrier may label a proposal.  Each
accepted pose segment is refined independently with the historical bounded
pose-only primitive.  Adoption changes only that segment's continuous pose;
the caller then reruns ordinary E023b from current pixels over the
affected regions.  Since RECEIVE-DESIGN v0.42 the one production caller is
the R(Lk) refinement level (:mod:`production_refine` for K,
:mod:`color_refine` for color) — refinement no longer runs inline in the
ordinary payload schedule.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from ..format.descriptor import FormatSpec
from .evidence import TileCertificateRecord
from . import tiles
from .certified_refine import (
    CertificateFrontier,
    RefinementMetrics,
    SegmentRefinementRequest,
    prepare_region_image,
    refine_segment,
)
from .place import placement_hint
from .payload_model import CaptureEvidence, ContextDecision, RawLumaRaster
from .placement.model import (
    AddressResult,
    AffinePose,
    PlacedPatch,
    PlacedSegment,
    PoseSegment,
)
@dataclass(frozen=True, slots=True)
class SegmentRefinementSummary:
    """Small transient audit row; arrays remain in generation zero."""

    patch_id: int
    segment_id: int
    frontier_id: str
    dependency_certificate_ids: tuple[str, ...]
    baseline_pose: AffinePose
    adopted_pose: AffinePose | None
    metrics: RefinementMetrics

    def __post_init__(self) -> None:
        if not isinstance(self.baseline_pose, AffinePose):
            raise TypeError("refinement summary needs its baseline pose")
        if self.adopted_pose is not None and not isinstance(
                self.adopted_pose, AffinePose):
            raise TypeError("refinement summary adopted pose is malformed")
        if self.metrics.adopted != (self.adopted_pose is not None):
            raise ValueError("refinement summary geometry disagrees with adoption")


@dataclass(frozen=True, slots=True)
class ForwardRefinement:
    """Final address geometry plus exact adopted certificate dependencies."""

    address: AddressResult
    summaries: tuple[SegmentRefinementSummary, ...]
    patch_dependencies: tuple[tuple[int, tuple[str, ...]], ...]

    @property
    def eligible(self) -> int:
        """Number of E022 placement windows eligible for refinement."""
        return sum(1 for row in self.summaries if row.metrics.eligible)

    @property
    def adopted(self) -> int:
        """Number of E022 placement windows whose pose was adopted."""
        return sum(1 for row in self.summaries if row.metrics.adopted)


def _context_by_id(
    generation0: CaptureEvidence,
) -> dict[str, ContextDecision]:
    rows = {row.decision_id: row for row in generation0.context_decisions}
    if len(rows) != len(generation0.context_decisions):
        raise ValueError("generation zero repeats a context decision identity")
    return rows


def _replace_hints(
    address: AddressResult,
    replacements: dict[int, PlacedSegment],
) -> tuple:
    """Regenerate accepted continuation geometry for adopted placements."""
    patch_by_id = {row.patch_id: row for row in address.placements}
    output = []
    for hint in address.continuation_hints:
        if hint.kind != "accepted":
            output.append(hint)
            continue
        patch_id = hint.patch_id
        if patch_id is None:
            raise ValueError("accepted continuation hint has no patch identity")
        revised = replacements.get(patch_id)
        patch = patch_by_id.get(patch_id)
        if patch is None:
            raise ValueError("accepted continuation hint names no placement")
        if revised is None:
            output.append(hint)
            continue
        output.append(placement_hint(
            hint.hint_id, patch.candidate, revised.segment,
            revised.page_origin_yx, kind="accepted",
            patch_id=patch_id,
        ))
    return tuple(output)


def refine_address_once(
    raster: RawLumaRaster,
    address: AddressResult,
    generation0: CaptureEvidence,
    spec: FormatSpec,
    prior_certificates: "Iterable[TileCertificateRecord]",
    *,
    included_patch_ids: frozenset[int] | None = None,
    pool_patch_ids: frozenset[int] | None = None,
) -> ForwardRefinement:
    """Apply one prior-frontier pose proposal to each accepted segment.

    When ``adopted`` is nonzero, the caller recomputes the affected
    regions' numerical emission at the revised address (v0.42: the
    R-level delta) and binds ``patch_dependencies`` to the new
    evidence/attempt/certificate provenance.

    ``pool_patch_ids`` names the placements whose segments join each
    region's aperture pool (pool law L5: the pool is generation zero's —
    placements UNION labels, including label-only windows absent from
    ``generation0``); the address's ``label_placements`` always join.  It
    defaults to the refine domain and must contain it.
    """
    if not isinstance(address, AddressResult):
        raise TypeError("forward refinement needs AddressResult")
    if not isinstance(generation0, CaptureEvidence):
        raise TypeError("forward refinement needs CaptureEvidence")
    if generation0.spec_id != spec.spec_id:
        raise ValueError("generation zero belongs to another format")
    prior_rows = tuple(prior_certificates)
    if (
        included_patch_ids is not None
        and not isinstance(included_patch_ids, frozenset)
    ):
        raise TypeError(
            "forward refinement included patch ids must be a frozenset")
    included = (
        None
        if included_patch_ids is None
        else frozenset(int(value) for value in included_patch_ids)
    )
    all_promoted = address.payload_placements
    all_patch_ids = {int(row.patch_id) for row in all_promoted}
    if included is not None and (
        any(value < 0 for value in included)
        or not included.issubset(all_patch_ids)
    ):
        raise ValueError(
            "forward refinement included patch ids are outside the "
            "promoted domain")
    promoted = tuple(
        row for row in all_promoted
        if included is None or int(row.patch_id) in included
    )
    windows = {row.patch_id: row for row in generation0.windows}
    if len(windows) != len(generation0.windows):
        raise ValueError("generation zero repeats a patch identity")
    patch_ids = {row.patch_id for row in promoted}
    missing = patch_ids - set(windows)
    if missing:
        raise ValueError("generation zero omitted a promoted placement window")
    if set(windows) - patch_ids:
        raise ValueError("generation zero contains a foreign placement window")
    # Empty-domain early-out ABOVE frontier construction (Phase 3.2,
    # refinement:06): an empty-promoted or certificate-less lane builds no
    # frontier, so no certificate is LDPC-re-encoded for a refinement that
    # cannot run.  A frontier from nonempty rows is never tile-empty, so
    # ``not prior_rows`` is exactly the old ``not frontier.tiles``.
    if not prior_rows or not promoted:
        return ForwardRefinement(address, (), ())
    frontier = CertificateFrontier.from_certificates(spec, prior_rows)
    if (
        pool_patch_ids is not None
        and not isinstance(pool_patch_ids, frozenset)
    ):
        raise TypeError(
            "forward refinement pool patch ids must be a frozenset")
    refine_domain = frozenset(int(row.patch_id) for row in promoted)
    pool = (
        refine_domain
        if pool_patch_ids is None
        else frozenset(int(value) for value in pool_patch_ids)
    )
    if any(value < 0 for value in pool) or not pool.issubset(all_patch_ids):
        raise ValueError(
            "forward refinement pool patch ids are outside the "
            "promoted domain")
    if not refine_domain.issubset(pool):
        raise ValueError(
            "forward refinement pool must contain the refine domain")
    decisions = _context_by_id(generation0)
    segments_by_region: dict[int, list[PoseSegment]] = {}
    for patch in promoted:
        placed = patch.segment
        segments_by_region.setdefault(
            patch.region_index, []).append(placed.segment)
    # Pool law L5: the aperture pool is generation zero's region pool —
    # pooled placements UNION label placements — so certified-refinement
    # replay reproduces generation zero's crop/filter policy exactly even
    # when label-only windows carry no generation-zero evidence.
    pool_segments_by_region: dict[int, list[PoseSegment]] = {}
    for patch in all_promoted:
        if int(patch.patch_id) in pool:
            pool_segments_by_region.setdefault(
                patch.region_index, []).append(patch.segment.segment)
    for patch in address.label_placements:
        pool_segments_by_region.setdefault(
            patch.region_index, []).append(patch.segment.segment)
    images = {
        region: prepare_region_image(
            raster, region, pool_segments_by_region[region])
        for region in segments_by_region
    }

    summaries: list[SegmentRefinementSummary] = []
    replacements: dict[int, PlacedSegment] = {}
    revised_by_id: dict[int, PlacedPatch] = {}
    dependencies_by_patch: dict[int, tuple[str, ...]] = {}
    for patch in promoted:
        window = windows.get(patch.patch_id)
        assert window is not None
        placed = patch.segment
        if (window.page != patch.candidate.page
                or placed.rot_k != patch.candidate.rot_k):
            raise ValueError(
                "generation zero changed the frozen page/orientation")
        segment_id = placed.segment.window.window_id
        if window.segment_id != segment_id:
            raise ValueError(
                "generation zero violates one-window placement ownership"
            )
        decision = (None if window.context_decision_id is None else
                    decisions.get(window.context_decision_id))
        if window.context_decision_id is not None and decision is None:
            raise ValueError("generation zero omitted its context decision")
        if not window.accepted:
            # A starved-refused generation-zero window carries no detector
            # to refine (SegmentRefinementRequest enforces acceptance).
            # It stays a pool/aperture member; its region's Lk evidence
            # stands, and the explicit summary keeps per-patch accounting.
            summaries.append(SegmentRefinementSummary(
                patch.patch_id, segment_id, frontier.frontier_id,
                (), placed.segment.pose, None,
                RefinementMetrics(False, False, "refused_generation0"),
            ))
            continue
        fitted = refine_segment(
            images[patch.region_index],
            SegmentRefinementRequest(placed, window, decision),
            spec,
            frontier,
        )
        summaries.append(SegmentRefinementSummary(
            patch.patch_id, segment_id, fitted.frontier_id,
            fitted.dependency_certificate_ids, placed.segment.pose,
            (fitted.refined_segment.pose if fitted.metrics.adopted else None),
            fitted.metrics,
        ))
        if fitted.metrics.adopted:
            revised = replace(placed, segment=fitted.refined_segment)
            replacements[patch.patch_id] = revised
            dependencies_by_patch[patch.patch_id] = (
                fitted.dependency_certificate_ids
            )
            revised_by_id[patch.patch_id] = replace(
                patch, segment=revised,
            )

    patch_dependencies = tuple(sorted(dependencies_by_patch.items()))
    if not replacements:
        revised_address = address
    else:
        provisional = replace(address, placements=tuple(
            revised_by_id.get(patch.patch_id, patch)
            for patch in address.placements
        ))
        revised_address = replace(
            provisional,
            continuation_hints=_replace_hints(provisional, replacements),
        )
    return ForwardRefinement(
        revised_address, tuple(summaries), patch_dependencies)


__all__ = [
    "ForwardRefinement", "SegmentRefinementSummary", "refine_address_once",
]
