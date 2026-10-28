"""Typed durable evidence supplied to one Track-3 receiver lane.

Every prior physical acquisition remains one independent same-lane component.
Internally generated scale lanes never contribute raw cells across lanes.
"""
from __future__ import annotations

from dataclasses import dataclass

from .session import CaptureFacts, SessionIndex
from .types import (
    EvidenceBlock,
    LaneSpec,
    LosingHypothesis,
    ParkedWindowRecord,
    PoseProposal,
    SurveyRegionRecord,
    TileCertificateRecord,
)


@dataclass(frozen=True, slots=True)
class EvidenceContext:
    """The only durable evidence exposed to one lane.

    Certificates and spatial pose facts may cross correlated scale barriers.
    Raw cells come only from prior physical captures at this lane identity.
    Each block keeps its capture component; consumers may sum different
    captures but never different lanes.
    """

    certificates: tuple[TileCertificateRecord, ...] = ()
    proposals: tuple[PoseProposal, ...] = ()
    losers: tuple[LosingHypothesis, ...] = ()
    prior_capture_blocks: tuple[EvidenceBlock, ...] = ()
    parked: tuple[ParkedWindowRecord, ...] = ()
    regions: tuple[SurveyRegionRecord, ...] = ()
    patch_ordinal_watermark: int = 0
    label_poses: tuple = ()
    own_committed_blocks: tuple[EvidenceBlock, ...] = ()

    def __post_init__(self) -> None:
        if len({row.key for row in self.prior_capture_blocks}) != len(
                self.prior_capture_blocks):
            raise ValueError("prior capture blocks repeat a frontier key")


def _select_lower_scale_evidence(
    proposals: tuple[PoseProposal, ...],
    losers: tuple[LosingHypothesis, ...],
    *,
    capture_id: str,
    prior_lane_ids: tuple[str, ...],
) -> tuple[tuple[PoseProposal, ...], tuple[LosingHypothesis, ...]]:
    """Select exactly the nearest productive prior lane for E023c."""
    accepted_by_lane: dict[str, list[PoseProposal]] = {}
    runners_by_lane: dict[str, list[LosingHypothesis]] = {}
    prior = set(prior_lane_ids)
    for row in proposals:
        if row.capture_id == capture_id and row.source_lane_id in prior:
            accepted_by_lane.setdefault(row.source_lane_id, []).append(row)
    for row in losers:
        if row.capture_id == capture_id and row.lane_id in prior:
            runners_by_lane.setdefault(row.lane_id, []).append(row)
    for lane_id in reversed(prior_lane_ids):
        accepted = tuple(accepted_by_lane.get(lane_id, ()))
        runners = tuple(runners_by_lane.get(lane_id, ()))
        if accepted or runners:
            return accepted, runners
    return (), ()


def build_evidence_context(
    index: SessionIndex,
    facts: CaptureFacts,
    lane: LaneSpec,
    plan: tuple[LaneSpec, ...],
) -> EvidenceContext:
    """Build explicit scale-crossing and same-lane capture views."""
    frontier = tuple(
        index.blocks[identity]
        for key, identity in sorted(index.block_frontier.items())
        if key[1] == lane.evidence_lane_id
        and key[0] != facts.source_sha256)
    positions = {row.lane_id: position for position, row in enumerate(plan)}
    if lane.lane_id not in positions:
        raise ValueError("lane is absent from the capture scale plan")
    if lane.mopup_of is not None:
        # v0.33 mop-up inventory (PHASED-SCHEDULE D7): every accepted pose
        # of the capture (via its durable proposal rows) plus every losing
        # hypothesis, across all lanes — the loser-revisit channel lives
        # here now that every cold runs at an M-level.  The per-window
        # nearest-first 8-hint portfolio bounds the attempted domain as
        # ever.
        proposals = tuple(
            row for row in index.proposals.values()
            if row.capture_id == facts.source_sha256)
        losers = tuple(
            row for row in index.losers.values()
            if row.capture_id == facts.source_sha256)
        parked = tuple(
            row for row in index.parked.values()
            if row.capture_id == facts.source_sha256
            and row.lane_id == lane.mopup_of)
        region_rows = tuple(
            row for row in index.regions.values()
            if row.capture_id == facts.source_sha256
            and row.lane_id == lane.mopup_of)
        # One evidence lane = one patch-ordinal namespace: fresh mop-up
        # work (subdivision children) mints strictly above the durable
        # maximum; parked rows re-use their own ordinals.
        durable = [
            row.patch_id for row in index.poses.values()
            if row.capture_id == facts.source_sha256
            and row.lane_id == lane.mopup_of]
        durable.extend(row.patch_ordinal for row in parked)
        durable.extend(index.quarantined_patches.get(
            (facts.source_sha256, lane.mopup_of), frozenset()))
        watermark = 1 + max(durable, default=-1)
        # D7: the base pass's placed poses reconstruct as calibration
        # labels at the M-level (accepted and redundant alike — the
        # pooled fit trained on both).
        label_poses = tuple(
            row for row in index.poses.values()
            if row.capture_id == facts.source_sha256
            and row.lane_id == lane.mopup_of)
        # D5: this capture's committed base blocks at the evidence lane —
        # the mop-up payload materializes superset blocks against them.
        own_committed = tuple(
            index.blocks[identity]
            for key, identity in sorted(index.block_frontier.items())
            if key[1] == lane.evidence_lane_id
            and key[0] == facts.source_sha256)
    elif lane.refine_of is not None or lane.uplift_of is not None:
        # v0.42 refinement inventory: the base lane Lk's committed poses
        # (accepted AND redundant — both trained the pooled fit; base-
        # quarantined placements EXCLUDED, stage C: a quarantined
        # placement must never re-enter the payload domain, and the R
        # delta would otherwise emit through it as region context)
        # exposed through the label channel, plus Lk's durable regions
        # for region-coupled context.  The R level's evidence namespace
        # is its OWN lane id (only certificates cross lanes), so its
        # block frontier and patch-ordinal watermark key on the R lane
        # itself.
        #
        # PK4.3: a SUPPLEMENTAL level takes literally the same inventory
        # from its own base lane (``uplift_of``) — same committed poses,
        # same durable regions, same own evidence namespace.  It differs
        # only in what its payload leaf does with them (one forced arm,
        # no pose refinement), which is a payload-stage fact, not an
        # evidence-context one.
        base_lane_id = (
            lane.refine_of if lane.refine_of is not None else lane.uplift_of)
        proposals = ()
        losers = ()
        parked = ()
        region_rows = tuple(
            row for row in index.regions.values()
            if row.capture_id == facts.source_sha256
            and row.lane_id == base_lane_id)
        durable = [
            row.patch_id for row in index.poses.values()
            if row.capture_id == facts.source_sha256
            and row.lane_id == lane.lane_id]
        durable.extend(index.quarantined_patches.get(
            (facts.source_sha256, lane.lane_id), frozenset()))
        watermark = 1 + max(durable, default=-1)
        base_quarantined = index.quarantined_patches.get(
            (facts.source_sha256, base_lane_id), frozenset())
        label_poses = tuple(
            row for row in index.poses.values()
            if row.capture_id == facts.source_sha256
            and row.lane_id == base_lane_id
            and row.patch_id not in base_quarantined)
        own_committed = tuple(
            index.blocks[identity]
            for key, identity in sorted(index.block_frontier.items())
            if key[1] == lane.evidence_lane_id
            and key[0] == facts.source_sha256)
    else:
        proposals, losers = _select_lower_scale_evidence(
            tuple(index.proposals.values()), tuple(index.losers.values()),
            capture_id=facts.source_sha256,
            prior_lane_ids=tuple(
                row.lane_id for row in plan[:positions[lane.lane_id]]))
        parked = ()
        region_rows = ()
        watermark = 0
        label_poses = ()
        own_committed = ()
    return EvidenceContext(
        certificates=tuple(index.certificates.values()),
        proposals=proposals,
        losers=losers,
        prior_capture_blocks=frontier,
        parked=parked,
        regions=region_rows,
        patch_ordinal_watermark=watermark,
        label_poses=label_poses,
        own_committed_blocks=own_committed,
    )


__all__ = ["EvidenceContext", "build_evidence_context"]
