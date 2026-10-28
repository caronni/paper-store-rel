"""Pure replay checks for address and compact E023b durable ledgers."""
from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np

from .evidence_blocks import EvidenceBlock, tile_attempt_view
from .payload_model import DivergenceRecord
from .types import (
    AddressArtifact,
    AttemptStage,
    AttemptState,
    PoseRecord,
    TileAttemptRecord,
    TileCertificateRecord,
)


DivergenceBlockIndex = dict[
    str,
    tuple[tuple[int, int, int], tuple[tuple[int, np.float32], ...]],
]


def validate_address_quarantine(
    artifact: AddressArtifact,
    poses: Iterable[PoseRecord],
) -> None:
    """Bind every quarantined patch to one retained accepted placement."""
    if not artifact.bch_conflicts:
        return
    placements: dict[int, PoseRecord] = {}
    for row in poses:
        if row.patch_id in placements:
            raise ValueError("address artifact repeats a placed patch identity")
        placements[row.patch_id] = row
    for conflict in artifact.bch_conflicts:
        for patch_id in conflict.contributor_patch_ids:
            placement = placements.get(patch_id)
            if (placement is None
                    or placement.placement_outcome != "accepted"):
                raise ValueError(
                    "BCH conflict contributor is not an accepted placement")
            if placement.page != conflict.page:
                raise ValueError(
                    "BCH conflict contributor belongs to another page")


def index_divergence_blocks(
    blocks: Mapping[str, EvidenceBlock] | tuple[EvidenceBlock, ...],
) -> DivergenceBlockIndex:
    """Index historical source observations, deduplicating frontier copies."""
    values = blocks.values() if isinstance(blocks, Mapping) else blocks
    pending: dict[
        str, tuple[tuple[int, int, int], dict[int, bytes]]
    ] = {}
    for block in values:
        address = block.address
        current = pending.setdefault(block.block_id, (address, {}))
        if current[0] != address:
            raise ValueError("one evidence id has conflicting tile addresses")
        for flat, llr in zip(
                block.observed_flat(), block.printed_llr(), strict=True):
            raw = np.asarray([llr], dtype="<f4").tobytes()
            previous = current[1].setdefault(int(flat), raw)
            if previous != raw:
                raise ValueError(
                    "one physical source has conflicting compact evidence")
    return {
        key: (
            address,
            tuple((flat, np.frombuffer(raw, "<f4")[0])
                  for flat, raw in sorted(rows.items())),
        )
        for key, (address, rows) in pending.items()
    }


def validate_attempt(
    attempt: TileAttemptRecord,
    blocks: Mapping[str, EvidenceBlock],
    certificates: Mapping[str, TileCertificateRecord],
    new_certificates: set[str] | None,
    prior_attempts: tuple[TileAttemptRecord, ...] = (),
    frontier_blocks: Mapping[tuple[str, str, int, int, int], str] | None = None,
    require_components: bool = True,
) -> None:
    """Replay exact component vectors, acquisition doctrine, and retries."""
    address = (attempt.page, *attempt.tile_yx)
    components = tuple(
        blocks[identity] for identity in attempt.component_block_ids
        if identity in blocks)
    missing_components = len(components) != len(attempt.component_block_ids)
    if missing_components and components:
        raise ValueError(
            "attempt has only part of its evidence components")
    if missing_components and require_components:
        raise ValueError("attempt references an unavailable evidence block")
    if missing_components:
        _validate_retry_and_certificate(
            attempt, certificates, new_certificates, prior_attempts)
        return
    view = tile_attempt_view(components)
    if (view.address != address
            or any(row.lane_id != attempt.lane_id for row in components)):
        raise ValueError("attempt component lies outside its lane/tile")
    if (attempt.stage is AttemptStage.SCAN and len(components) != 1
            or attempt.stage is AttemptStage.UNION and len(components) < 2):
        raise ValueError("attempt stage disagrees with capture components")
    if attempt.stage is AttemptStage.SCAN:
        if components[0].source_sha256 != attempt.source_sha256:
            raise ValueError(
                "scan attempt does not use the current acquisition")
        if (frontier_blocks is not None
                and frontier_blocks.get(components[0].key)
                != components[0].block_id):
            raise ValueError("scan attempt does not use the live component")
    elif attempt.stage is AttemptStage.UNION:
        current_components = tuple(
            row.block_id for row in components
            if row.source_sha256 == attempt.source_sha256)
        parent = next((
            row for row in reversed(prior_attempts)
            if (row.source_sha256 == attempt.source_sha256
                and row.lane_id == attempt.lane_id
                and (row.page, *row.tile_yx) == address
                and row.stream_id == attempt.stream_id
                and row.stage is AttemptStage.SCAN)
        ), None)
        if (len(current_components) != 1 or parent is None
                or parent.component_block_ids != current_components
                or parent.state is AttemptState.CERTIFIED):
            raise ValueError(
                "union attempt has no preceding current-acquisition scan")
        if frontier_blocks is not None:
            expected = tuple(
                identity
                for key, identity in sorted(frontier_blocks.items())
                if key[1] == attempt.lane_id and key[2:] == address)
            if expected != attempt.component_block_ids:
                raise ValueError(
                    "union attempt omits a live acquisition component")
    if view.component_block_ids != attempt.component_block_ids:
        raise ValueError("attempt provenance differs from its blocks")
    n_informative = (
        int(np.count_nonzero(view.llr_cells_f64))
        if view.kind == "k"
        else int(np.count_nonzero(view.observed_cells()))
    )
    if n_informative != attempt.n_informative:
        raise ValueError("attempt informative count differs from evidence")
    if (view.dependency_certificate_ids
            != attempt.dependency_certificate_ids):
        raise ValueError("attempt dependencies differ from its components")

    _validate_retry_and_certificate(
        attempt, certificates, new_certificates, prior_attempts)


def _validate_retry_and_certificate(
    attempt: TileAttemptRecord,
    certificates: Mapping[str, TileCertificateRecord],
    new_certificates: set[str] | None,
    prior_attempts: tuple[TileAttemptRecord, ...],
) -> None:
    address = (attempt.page, *attempt.tile_yx)
    for identity in attempt.dependency_certificate_ids:
        dependency = certificates.get(identity)
        if dependency is None:
            raise ValueError("attempt references an unknown dependency")
        if ((dependency.page, *dependency.tile_yx) == address
                and dependency.stream_id == attempt.stream_id):
            raise ValueError("attempt depends on its target tile stream")
    if attempt.stage is AttemptStage.RETRY150:
        baselines = [
            row for row in prior_attempts
            if (row.page, *row.tile_yx) == address
            and row.lane_id == attempt.lane_id
            and row.stream_id == attempt.stream_id
            and row.stage in (AttemptStage.SCAN, AttemptStage.UNION)
        ]
        if not baselines:
            raise ValueError("retry has no baseline parent")
        parent = baselines[-1]
        if (parent.state is not AttemptState.ATTEMPTED_FAILED
                or parent.component_block_ids != attempt.component_block_ids
                or parent.dependency_certificate_ids
                != attempt.dependency_certificate_ids):
            raise ValueError("retry tunnels past its latest failed baseline")

    if attempt.certificate_id is not None:
        certificate = certificates.get(attempt.certificate_id)
        if certificate is None:
            raise ValueError("attempt references an unknown certificate")
        if (certificate.page != attempt.page
                or certificate.tile_yx != attempt.tile_yx
                or certificate.stream_id != attempt.stream_id):
            raise ValueError(
                "attempt certificate belongs to another tile stream")
        if (new_certificates is not None
                and attempt.certificate_id not in new_certificates):
            raise ValueError("attempt certificate is not new at this barrier")
        if certificate.origin_attempt_id != attempt.attempt_id:
            raise ValueError("minting attempt is not certificate origin")


def validate_divergence(
    divergence: DivergenceRecord,
    certificates: Mapping[str, TileCertificateRecord],
    evidence_index: DivergenceBlockIndex,
    printed_cells: Mapping[str, np.ndarray] | None = None,
    require_evidence: bool = True,
) -> None:
    """Replay source counts and, when a spec is available, disagreements."""
    certificate = certificates.get(divergence.certificate_id)
    if certificate is None:
        raise ValueError("divergence references an unknown certificate")
    indexed = evidence_index.get(divergence.evidence_block_id)
    if indexed is None and not require_evidence:
        return
    if indexed is None:
        selected = ()
    else:
        address, selected = indexed
        if address != (certificate.page, *certificate.tile_yx):
            raise ValueError(
                "divergence evidence belongs to another certificate tile")
    if len(selected) != divergence.n_observed:
        raise ValueError("divergence observation count disagrees with source")
    if printed_cells is None:
        return
    expected = printed_cells.get(divergence.certificate_id)
    if expected is None or np.asarray(expected).shape != (64, 64):
        raise ValueError("divergence certificate field is unavailable")
    flat_expected = np.asarray(expected, bool).reshape(-1)
    disagreements = sum((float(llr) > 0.0) != bool(flat_expected[flat])
                        for flat, llr in selected)
    if disagreements != divergence.n_disagree:
        raise ValueError("divergence disagreement count is not replayable")


__all__ = [
    "DivergenceBlockIndex", "index_divergence_blocks",
    "validate_address_quarantine", "validate_attempt", "validate_divergence",
]
