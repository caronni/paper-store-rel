"""Atomic receive-session barriers, indexing, and persistence.

Each durable mutation is one completed ``(physical capture, scale level)``
barrier.  Capture scale plans and level histories are append-only prefixes;
stage-owned products live in typed ledgers and level artifacts summarize
them.  A transient :class:`SessionIndex` validates new deltas in work
proportional to the delta; loading validates the file STRUCTURALLY
(bindings, page domain, certificate identity/conflicts, the pending-block
invariant) without replaying barrier history (kiss). Attempt and
divergence ledgers are not persisted — they fold into counters.
The record/state shapes live in :mod:`holo.receive.session_model`.
"""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..format.descriptor import FormatSpec

from ..format.profiles import Family
from .evidence import certificate_work_index
from .session_model import (
    BarrierDelta,
    CaptureConflictError,
    CaptureFacts,
    CaptureRecord,
    CaptureStatus,
    LevelRecord,
    LevelStatus,
    SessionCounters,
    SessionState,
    SessionStatus,
    StageTally,
)
from .session_validation import (
    DivergenceBlockIndex,
    index_divergence_blocks,
    validate_address_quarantine,
    validate_attempt,
    validate_divergence,
)
from .state_codec import (
    authoritative_state_bytes,
    authoritative_state_sha256,
    canonical_bytes,
    encode_typed,
    load_typed,
    load_typed_with_digest,
    save_typed,
    save_typed_with_digest,
)
from .types import (
    CloseRecord,
    CloseStatus,
    DivergenceRecord,
    EvidenceBlock,
    LaneSpec,
    TileAttemptRecord,
    TileCertificateRecord,
)


STATE_MAGIC = "holo-receive-session"
STATE_SCHEMA_VERSION = 26   # policy lineage (the policy-detach ruling, v0.59)

# Older schemas this tree still READS, each lifted by one additive step
# (``state_codec._migrated``).  A migration only ever supplies keys a
# later field set added, at the dataclass default — the archive is the
# reason the policy gate was unlocked at all, so a state-shape change
# that orphans it would defeat its own purpose.  A state is rewritten at
# the current version by the first barrier that legitimately saves it.
STATE_MIGRATIONS = {
    # 25 -> 26: no session had run under more than one receiver policy,
    # because a differing one was refused outright.
    25: lambda document: {**document, "policy_lineage": []},
}


def _id_map(rows: tuple[Any, ...], attribute: str, label: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for row in rows:
        identity = getattr(row, attribute)
        if identity in out:
            raise ValueError(f"duplicate {label} id {identity!r}")
        out[identity] = row
    return out


def _quarantine_index(
    state: SessionState,
) -> dict[tuple[str, str], frozenset[int]]:
    # v0.33: keyed by EVIDENCE lane and union-accumulated, so a mop-up
    # level's quarantine joins its base lane's.  One evidence lane is one
    # patch-ordinal space — the mop-up continues the base pass's ordinals,
    # never restarts them, so the union cannot misattribute a patch.
    out: dict[tuple[str, str], frozenset[int]] = {}
    for capture in state.captures:
        for ordinal, level in enumerate(capture.levels):
            if level.address is None:
                continue
            key = (capture.source_sha256,
                   capture.plan[ordinal].evidence_lane_id)
            out[key] = out.get(key, frozenset()) | frozenset(
                level.address.quarantined_patch_ids)
    return out


class SessionIndex:
    """Transient indexes for barrier validation and compact-frontier lookup."""

    def __init__(self, state: SessionState, *,
                 spec: FormatSpec | None = None,
                 validate: bool = True) -> None:
        from ..format.resolve import resolve_format_ref

        self.state = state
        if spec is not None:
            # An in-request spec (e.g. a qualification-geometry row absent
            # from the registry) gives the index FULL stream/record
            # validation instead of the opaque one-stream fallback.  It must
            # be the state's own format, never a substitute.
            if spec.spec_id != state.format_row_id:
                raise ValueError(
                    "session index spec differs from the state format row")
            self.spec = spec
        else:
            try:
                # Total over every persisted identity: catalog rows,
                # fossils (bare or L:), and v2 format ids (FORMAT-SPACE
                # §10) — the off-catalog one-stream fallback class of
                # bug is gone.
                self.spec = resolve_format_ref(state.format_row_id)
            except (KeyError, ValueError):
                # A few detached diagnostic fixtures deliberately use an
                # opaque format label and carry no color state.  Such a state
                # retains the established one-stream vocabulary; any non-main
                # record is refused below.
                self.spec = None
        self.stream_ids = (
            ("main",) if self.spec is None else self.spec.stream_ids)
        self.captures = _id_map(
            state.captures, "source_sha256", "capture")
        self.regions = _id_map(state.regions, "region_id", "region")
        self.poses = _id_map(state.poses, "pose_id", "pose")
        self.proposals = _id_map(state.proposals, "proposal_id", "proposal")
        self.losers = _id_map(state.losers, "hypothesis_id", "hypothesis")
        self.parked = _id_map(state.parked, "parked_id", "parked window")
        self.blocks = _id_map(state.blocks, "block_id", "evidence block")
        self.certificates = _id_map(
            state.certificates, "certificate_id", "certificate")
        self.quarantined_patches = _quarantine_index(state)
        self.block_frontier: dict[tuple[str, str, int, int, int], str] = {}
        self.certificate_tiles: dict[tuple[int, int, int, str], str] = {}
        if validate:
            self._validate_full()
        else:
            self._rebuild_derived()

    def _rebuild_derived(self) -> None:
        # The divergence-block index is deliberately NOT a derived member:
        # delta validation builds its own delta-local index only when a
        # divergence actually needs it (growth audit 2026-07-31 — the
        # eagerly rebuilt member had zero readers and cost O(N*V) at every
        # barrier accept).
        from .evidence_blocks import merge_block_sets
        self.block_frontier = {
            row.key: row.block_id for row in merge_block_sets(self.blocks.values())}
        self.certificate_tiles = certificate_work_index(
            self.state.certificates)

    def _validate_stream_record(
        self,
        row: TileAttemptRecord | TileCertificateRecord,
    ) -> None:
        if row.stream_id not in self.stream_ids:
            raise ValueError(
                f"stream {row.stream_id!r} is not declared by "
                f"{self.state.format_row_id}")
        if self.spec is None:
            if row.stream_id != "main":
                raise ValueError("opaque format state supports only main")
            return
        from .color_attempts import effective_demap_iterations
        from .records import (
            validate_attempt_record_identity,
            validate_certificate_record,
        )
        if isinstance(row, TileAttemptRecord):
            # The CMY7 demap budget is part of the decoder identity, so
            # the reconstruction reads the same EFFECTIVE count the
            # minting call did (``_runtime_validation`` does likewise).
            validate_attempt_record_identity(
                row, self.spec,
                demap_iterations=effective_demap_iterations())
        else:
            validate_certificate_record(row, self.spec)

    def _validate_full(self) -> None:
        self._rebuild_derived()
        self._validate_structural()

    def _validate_structural(self) -> None:
        """Validate a loaded state without replaying barrier history."""
        state = self.state
        allowed = (None if state.page_hypotheses is None
                   else frozenset(state.page_hypotheses))
        lanes = {(row.source_sha256, lane.lane_id)
                 for row in state.captures for lane in row.plan}
        for region in state.regions:
            if (region.capture_id, region.lane_id) not in lanes:
                raise ValueError("region is not bound to a capture lane")
        regions = set(self.regions)
        for pose in state.poses:
            if pose.region_id not in regions:
                raise ValueError("pose references an unknown region")
        for row in state.parked:
            if (row.capture_id, row.lane_id) not in lanes:
                raise ValueError("parked window is not bound to a capture lane")
            if row.region_id not in regions:
                raise ValueError("parked window references an unknown region")
            capture = self.captures.get(row.capture_id)
            if capture is None:
                raise ValueError("parked window names an unknown capture")
            position = next(
                (ordinal for ordinal, spec in enumerate(capture.plan)
                 if spec.mopup_of == row.lane_id), None)
            if position is None:
                raise ValueError("parked window's lane has no mop-up level")
            if len(capture.levels) > position:
                raise ValueError("parked window survived its mop-up level")
        for rows in (state.poses, state.proposals, state.losers,
                     state.blocks, state.certificates):
            if allowed is not None and any(
                    row.page not in allowed for row in rows):
                raise ValueError(
                    "persisted record lies outside the receive page domain")
        for certificate in state.certificates:
            self._validate_stream_record(certificate)
        for capture in state.captures:
            for level in capture.levels:
                if level.survey is not None:
                    for region_id in level.survey.region_ids:
                        if region_id not in regions:
                            raise ValueError(
                                "survey artifact names an unknown region")
                if level.address is not None:
                    for pose_id in level.address.pose_ids:
                        if pose_id not in self.poses:
                            raise ValueError(
                                "address artifact names an unknown pose")
                    validate_address_quarantine(
                        level.address,
                        tuple(self.poses[p]
                              for p in level.address.pose_ids))
                if level.payload is not None:
                    for identity in level.payload.certificate_ids:
                        if identity not in self.certificates:
                            raise ValueError(
                                "payload artifact names an unknown "
                                "certificate")
        certified = {row.work_key for row in state.certificates}
        quarantined = self.quarantined_patches
        prior_certificates = set(self.certificates)
        for block in state.blocks:
            if (block.source_sha256, block.lane_id) not in lanes:
                raise ValueError("evidence block is not bound to a lane")
            if all((*block.address, stream_id) in certified
                   for stream_id in self.stream_ids):
                raise ValueError(
                    "persisted evidence block is not pending (its tile is "
                    "fully certified)")
            for origin in block.origins:
                if origin.patch_id in quarantined.get(
                        (block.source_sha256, block.lane_id), frozenset()):
                    raise ValueError(
                        "evidence originated from a quarantined placement")
                if any(dep not in prior_certificates
                       for dep in origin.dependency_certificate_ids):
                    raise ValueError(
                        "evidence block dependency is not certified")
        if (state.close.status is not CloseStatus.OPEN
                and state.close.certificate_frontier_sha256
                != certificate_frontier_sha256(state.certificates)):
            raise ValueError(
                "terminal close frontier disagrees with certificates")

    def validate_barrier(
        self, facts: CaptureFacts, plan: tuple[LaneSpec, ...],
        level: LevelRecord, delta: BarrierDelta,
    ) -> None:
        # v0.33: multiple ACTIVE captures are legal — the phased driver
        # advances every capture rung-major.  The resume duty ("a resume
        # request must include every ACTIVE capture") is enforced at
        # runtime ingest, not per barrier.
        existing = self.captures.get(facts.source_sha256)
        if existing is None:
            ordinal = 0
        else:
            _bind_facts(existing, facts)
            if existing.status is CaptureStatus.COMPLETE:
                raise ValueError("cannot append to a completed capture")
            if existing.plan != plan:
                raise CaptureConflictError("capture scale plan changed")
            ordinal = len(existing.levels)
        if ordinal >= len(plan):
            raise ValueError("level is beyond the scale plan")
        self._validate_delta(facts, plan[ordinal], level, delta)

    def _validate_delta(self, facts: CaptureFacts, lane: LaneSpec,
                        level: LevelRecord,
                        delta: BarrierDelta) -> None:
        from .evidence_blocks import (
            merge_block_sets,
            validate_block_supersession,
        )
        groups = (
            (delta.regions, "region_id", self.regions),
            (delta.poses, "pose_id", self.poses),
            (delta.proposals, "proposal_id", self.proposals),
            (delta.losers, "hypothesis_id", self.losers),
            (delta.parked, "parked_id", self.parked),
            (delta.blocks, "block_id", self.blocks),
            (delta.certificates, "certificate_id", self.certificates),
        )
        local: dict[str, dict[str, Any]] = {}
        for rows, attribute, old in groups:
            mapping = _id_map(rows, attribute, attribute)
            if set(mapping) & set(old):
                raise ValueError(f"barrier repeats a durable {attribute}")
            local[attribute] = mapping
        # Attempt/divergence ledgers are transient: unique within the delta,
        # folded into counters at commit, never persisted (kiss).
        local["attempt_id"] = _id_map(
            delta.attempts, "attempt_id", "attempt_id")
        local["divergence_id"] = _id_map(
            delta.divergences, "divergence_id", "divergence_id")
        allowed_pages = self.state.page_hypotheses
        if allowed_pages is not None:
            allowed = frozenset(allowed_pages)
            for rows in (
                delta.poses, delta.proposals,
                delta.losers, delta.blocks, delta.attempts,
                delta.certificates,
            ):
                if any(row.page not in allowed for row in rows):
                    raise ValueError(
                        "barrier record lies outside the receive page domain")
            if (level.address is not None and any(
                    row.page not in allowed
                    for row in level.address.bch_conflicts)):
                raise ValueError(
                    "BCH conflict lies outside the receive page domain")
        lane_id = lane.lane_id
        if level.survey is not None:
            if level.survey.region_ids != tuple(
                    row.region_id for row in delta.regions):
                raise ValueError("survey artifact differs from barrier regions")
        elif delta.regions:
            raise ValueError("barrier has regions without a survey artifact")
        if level.address is not None:
            expected = (
                (level.address.pose_ids, tuple(row.pose_id for row in delta.poses)),
                (level.address.proposal_ids,
                 tuple(row.proposal_id for row in delta.proposals)),
                (level.address.loser_ids,
                 tuple(row.hypothesis_id for row in delta.losers)),
                (level.address.parked_ids,
                 tuple(row.parked_id for row in delta.parked)),
            )
            if any(left != right for left, right in expected):
                raise ValueError("address artifact differs from barrier records")
            if (level.survey is None
                    or level.address.survey_id != level.survey.survey_id):
                raise ValueError("address does not consume this survey")
            validate_address_quarantine(
                level.address, delta.poses)
        elif any((delta.poses, delta.proposals, delta.losers, delta.parked)):
            raise ValueError("barrier has address records without artifact")
        if lane.mopup_of is not None and delta.parked:
            raise ValueError("a mop-up level cannot park windows")
        if lane.refine_of is not None and delta.parked:
            raise ValueError("a refinement level cannot park windows")
        # PK4.3: a supplemental level places nothing new and refines
        # nothing, so it can no more park than it can mint a pose.
        if lane.uplift_of is not None and (delta.parked or delta.poses):
            raise ValueError(
                "a supplemental level cannot park or mint windows")
        if level.payload is not None:
            if (level.payload.certificate_ids
                    != tuple(row.certificate_id
                             for row in delta.certificates)
                    or level.payload.n_blocks != len(delta.blocks)
                    or level.payload.n_attempts != len(delta.attempts)
                    or level.payload.n_divergences != len(delta.divergences)):
                raise ValueError("payload artifact differs from barrier records")
            if (level.address is None
                    or level.payload.address_id != level.address.address_id):
                raise ValueError("payload does not consume this address")
        elif any((delta.blocks, delta.attempts,
                  delta.certificates, delta.divergences)):
            raise ValueError("barrier has payload records without artifact")
        evidence_lane_id = lane.evidence_lane_id
        for rows in (delta.regions, delta.poses,
                     delta.proposals, delta.losers, delta.parked):
            for row in rows:
                if getattr(row, "capture_id") != facts.source_sha256:
                    raise ValueError("barrier record has another capture id")
                actual_lane = getattr(row, "lane_id",
                                      getattr(row, "source_lane_id", lane_id))
                if actual_lane != lane_id:
                    raise ValueError("barrier record has another lane id")
        for attempt in delta.attempts:
            self._validate_stream_record(attempt)
            if (attempt.source_sha256 != facts.source_sha256
                    or attempt.lane_id != evidence_lane_id):
                raise ValueError("barrier attempt has another source or lane")
        regions = self.regions | local["region_id"]
        for pose in delta.poses:
            if pose.region_id not in regions:
                raise ValueError("pose references an unknown region")
        prior_certificates = set(self.certificates)
        for row in (*delta.poses, *delta.losers):
            if any(dep not in prior_certificates
                   for dep in row.dependency_certificate_ids):
                raise ValueError("pose dependency is not a prior barrier")
        for proposal in delta.proposals:
            if any(dep not in prior_certificates
                   for dep in proposal.dependency_certificate_ids):
                raise ValueError("proposal dependency is not a prior barrier")
        if lane.mopup_of is not None:
            # One evidence lane is one patch-ordinal namespace (v0.33).  A
            # parked window keeps its base-pass ordinal — those rows retire
            # at this very barrier, so they are the legal re-use set; what
            # must never collide is the base pass's accepted/quarantined
            # ordinals (fresh mop-up work mints strictly above them).
            durable_ordinals = {
                row.patch_id for row in self.poses.values()
                if row.capture_id == facts.source_sha256
                and row.lane_id == lane.mopup_of}
            durable_ordinals |= self.quarantined_patches.get(
                (facts.source_sha256, lane.mopup_of), frozenset())
            fresh_ordinals = {row.patch_id for row in delta.poses}
            if level.address is not None:
                fresh_ordinals |= set(level.address.quarantined_patch_ids)
            if fresh_ordinals & durable_ordinals:
                raise ValueError(
                    "mop-up patch ordinals collide with the evidence lane")
        quarantined = dict(self.quarantined_patches)
        quarantine_key = (facts.source_sha256, evidence_lane_id)
        quarantined[quarantine_key] = quarantined.get(
            quarantine_key, frozenset()) | (
            frozenset() if level.address is None
            else frozenset(level.address.quarantined_patch_ids))
        for block in delta.blocks:
            if (block.source_sha256 != facts.source_sha256
                    or block.lane_id != evidence_lane_id):
                raise ValueError(
                    "barrier block has another capture or lane")
            if any(origin.patch_id in quarantined.get(
                       (block.source_sha256, block.lane_id), frozenset())
                   for origin in block.origins):
                raise ValueError(
                    "payload evidence originated from a quarantined placement")
            for origin in block.origins:
                if any(dep not in prior_certificates
                       for dep in origin.dependency_certificate_ids):
                    raise ValueError("block dependency is not a prior barrier")
        # v0.33: a mop-up delta may supersede live same-key blocks under the
        # extension-only rule; the superseded contents leave the frontier.
        superseded_ids: set[str] = set()
        if lane.mopup_of is not None and delta.blocks:
            live_by_key = {row.key: row for row in self.blocks.values()}
            for block in delta.blocks:
                old_block = live_by_key.get(block.key)
                if old_block is not None:
                    validate_block_supersession(old_block, block)
                    superseded_ids.add(old_block.block_id)
        all_blocks = {
            block_id: row
            for block_id, row in (self.blocks | local["block_id"]).items()
            if block_id not in superseded_ids}
        frontier = {
            row.key: row.block_id
            for row in merge_block_sets(all_blocks.values())}
        # O(N*V) with a Python-per-observation constant: build only when a
        # k-v1 divergence in this delta actually consumes it.
        divergence_index: DivergenceBlockIndex | None = None
        all_certificates = self.certificates | local["certificate_id"]
        # Retry/union parents live inside the same payload barrier, so the
        # delta-local prefix is the complete lineage the rules need.
        prior_attempts: list[TileAttemptRecord] = []
        for attempt in delta.attempts:
            if any(dep not in prior_certificates
                   for dep in attempt.dependency_certificate_ids):
                raise ValueError("attempt dependency is not a prior barrier")
            validate_attempt(
                attempt, all_blocks, all_certificates,
                new_certificates=set(local["certificate_id"]),
                prior_attempts=tuple(prior_attempts),
                frontier_blocks=frontier)
            if attempt.certificate_id is not None:
                certificate = local["certificate_id"].get(
                    attempt.certificate_id or "")
                if certificate is None:
                    raise ValueError("minting attempt omitted its certificate")
            prior_attempts.append(attempt)
        tiles = dict(self.certificate_tiles)
        for certificate in delta.certificates:
            self._validate_stream_record(certificate)
            if any(dep not in prior_certificates
                   for dep in certificate.dependency_certificate_ids):
                raise ValueError("certificate dependency is not a prior barrier")
            attempt = local["attempt_id"].get(certificate.origin_attempt_id)
            if (attempt is None
                    or attempt.certificate_id != certificate.certificate_id
                    or certificate.dependency_certificate_ids
                    != attempt.dependency_certificate_ids):
                raise ValueError("certificate has no minting attempt")
            work_key = certificate.work_key
            old = tiles.get(work_key)
            if old is not None and old != certificate.certificate_id:
                raise ValueError(
                    "conflicting certificate for a tile stream")
            tiles[work_key] = certificate.certificate_id
        for divergence in delta.divergences:
            block = all_blocks.get(divergence.evidence_block_id)
            if block is None or block.lane_id != evidence_lane_id:
                raise ValueError("divergence record has another lane id")
            certificate = all_certificates.get(
                divergence.certificate_id)
            if certificate is None:
                raise ValueError(
                    "divergence references an unknown certificate")
            if self.spec is not None and self.spec.codec_family is not Family.K:
                # Pairing is the loop above (block and certificate fetched
                # by the record's own ids); replay consumes the ONE color
                # comparison kernel — the same leaf the records pairing
                # loop runs — and checks the durable counters against it.
                from .color_divergence import color_divergence_counts

                n_observed, n_disagree = color_divergence_counts(
                    block, certificate, self.spec)
                if divergence.n_observed != n_observed:
                    raise ValueError(
                        "divergence observation count disagrees with source")
                if divergence.n_disagree != n_disagree:
                    raise ValueError(
                        "divergence disagreement count is not replayable")
            else:
                if divergence_index is None:
                    divergence_index = index_divergence_blocks(all_blocks)
                validate_divergence(
                    divergence, all_certificates, divergence_index)

    def accept(self, state: SessionState, delta: BarrierDelta) -> None:
        """Advance indexes only after the candidate was durably saved."""
        self.state = state
        self.captures = {
            row.source_sha256: row for row in state.captures}
        self.quarantined_patches = _quarantine_index(state)
        for rows, attribute, mapping in (
            (delta.regions, "region_id", self.regions),
            (delta.poses, "pose_id", self.poses),
            (delta.proposals, "proposal_id", self.proposals),
            (delta.losers, "hypothesis_id", self.losers),
            (delta.certificates, "certificate_id", self.certificates),
        ):
            mapping.update((getattr(row, attribute), row) for row in rows)
        self.blocks = {row.block_id: row for row in state.blocks}
        self.parked = {row.parked_id: row for row in state.parked}
        self._rebuild_derived()


def _bind_facts(existing: CaptureRecord, facts: CaptureFacts) -> None:
    old = (existing.source_sha256, existing.dpi, existing.dtype,
           existing.shape_yx, existing.channels)
    new = (facts.source_sha256, facts.dpi, facts.dtype,
           facts.shape_yx, facts.channels)
    if old != new:
        raise CaptureConflictError("capture immutable facts changed")


def append_level_barrier(
    state: SessionState, index: SessionIndex, facts: CaptureFacts,
    plan: tuple[LaneSpec, ...], level: LevelRecord, delta: BarrierDelta,
) -> SessionState:
    """Return a validated candidate containing exactly one new barrier."""
    if index.state is not state:
        raise ValueError("session index is not synchronized with state")
    index.validate_barrier(facts, plan, level, delta)
    old = index.captures.get(facts.source_sha256)
    lane = plan[0 if old is None else len(old.levels)]
    if old is None:
        capture = facts.as_record(plan, level)
        captures = state.captures + (capture,)
    else:
        levels = old.levels + (level,)
        capture = replace(old, levels=levels)
        captures = tuple(
            capture if row.source_sha256 == facts.source_sha256 else row
                         for row in state.captures)
    live_blocks = {row.key: row for row in state.blocks}
    for block in delta.blocks:
        # A mop-up block at a live key is a validated extension-only
        # supersession (v0.33); the committed content leaves the frontier.
        live_blocks[block.key] = block
    certified = {
        row.work_key
        for row in (*state.certificates, *delta.certificates)}
    required_streams = index.stream_ids
    retained_blocks = tuple(
        block for _key, block in sorted(live_blocks.items())
        if not all((*block.address, stream_id) in certified
                   for stream_id in required_streams))
    if lane.mopup_of is not None:
        # The mop-up barrier retires its (capture, base-lane) parked rows.
        retained_parked = tuple(
            row for row in state.parked
            if not (row.capture_id == facts.source_sha256
                    and row.lane_id == lane.mopup_of))
    else:
        retained_parked = state.parked + delta.parked
    return replace(
        state, captures=captures,
        regions=state.regions + delta.regions,
        poses=state.poses + delta.poses,
        proposals=state.proposals + delta.proposals,
        losers=state.losers + delta.losers,
        parked=retained_parked,
        blocks=retained_blocks,
        certificates=state.certificates + delta.certificates,
        counters=state.counters.fold(
            delta.attempts, delta.divergences,
            delta.mopup_dropped_observations,
            delta.mopup_winner_flips),
    )


def apply_close(state: SessionState, close: CloseRecord) -> SessionState:
    """Apply the sole legal close transition: open to one terminal result.

    Numerical evidence keeps the same ordinary live-frontier retention rule
    for every registered format.  Terminal close changes no evidence policy.
    """
    if state.close == close:
        return state
    if state.close.status is not CloseStatus.OPEN:
        raise ValueError("terminal close state is immutable")
    if close.status is CloseStatus.OPEN:
        if close != CloseRecord():
            raise ValueError("open close processor output must be empty")
        return state
    if close.certificate_frontier_sha256 != certificate_frontier_sha256(
            state.certificates):
        raise ValueError("close certificate frontier disagrees with state")
    return replace(state, close=close)


def detach_close(state: SessionState) -> SessionState:
    """The deliberate inverse of :func:`apply_close` (--no-close ruling,
    2026-08-19): remove a terminal close record so accumulation can
    continue.  A close is a pure derivation from the certificate set —
    any later closing run recomputes it (and re-verifies byte-exactly
    when the certificates still solve).  ``apply_close``'s "terminal
    close state is immutable" doctrine governs *close transitions*; this
    is not a transition to another close but an explicit reopening,
    reachable only through the --no-close run mode.  Returns the state
    unchanged when already OPEN."""
    if state.close.status is CloseStatus.OPEN:
        return state
    return replace(state, close=CloseRecord())


def certificate_frontier_sha256(
    certificates: tuple[TileCertificateRecord, ...],
) -> str:
    # Keep the established all-main frontier byte-exact.  A multistream
    # frontier includes the additional coordinate that makes sibling
    # certificates distinct.
    if all(row.stream_id == "main" for row in certificates):
        rows = sorted((row.page, row.tile_yx[0], row.tile_yx[1],
                       row.certificate_id) for row in certificates)
    else:
        rows = sorted((row.page, row.tile_yx[0], row.tile_yx[1],
                       row.stream_id, row.certificate_id)
                      for row in certificates)
    return hashlib.sha256(canonical_bytes(rows)).hexdigest()


def validate_session(
    state: SessionState,
    *,
    defer_fountain_validation: bool = False,
) -> None:
    """Replay one session and reproduce its close contract.

    A deferred invocation structurally validates every status immediately but
    postpones its numerical fountain reproduction until the invocation's final
    close phase. Ordinary validation always reproduces the close here.
    """
    if type(defer_fountain_validation) is not bool:
        raise TypeError("defer_fountain_validation must be bool")
    index = SessionIndex(state, validate=True)
    if index.spec is None:
        return
    from ._runtime_validation import validate_state_for_spec

    validate_state_for_spec(state, index.spec)
    # --complete defers every numerical fountain check, including reproduction
    # of an already terminal close, until the invocation's final close phase.
    # Structural replay above remains immediate for every status.
    if defer_fountain_validation:
        return

    from .fountain_close import close_record_from_result, close_volume
    from .records import certificate_for_close

    result = close_volume(
        tuple(certificate_for_close(row, index.spec)
              for row in state.certificates),
        index.spec,
    )
    expected = close_record_from_result(
        result,
        (None if result.status == "open"
         else certificate_frontier_sha256(state.certificates)),
    )
    if state.close != expected:
        raise ValueError(
            "registered receive state close does not reproduce from "
            "its certified frontier")


def state_payload(state: SessionState) -> dict[str, Any]:
    return encode_typed(state)


def authoritative_bytes(state: SessionState) -> bytes:
    return authoritative_state_bytes(
        state_payload(state),
        magic=STATE_MAGIC,
        schema=STATE_SCHEMA_VERSION,
    )


def authoritative_sha256(state: SessionState) -> str:
    return authoritative_state_sha256(
        state_payload(state),
        magic=STATE_MAGIC,
        schema=STATE_SCHEMA_VERSION,
    )


def save_session(path: str | Path, state: SessionState, *,
                 validate: bool = True) -> bool:
    """Atomically persist state; return false for a byte-identical no-op.

    Runtime barrier commits pass ``validate=False`` because their delta was
    already checked against a synchronized :class:`SessionIndex`.  Public
    callers retain the defensive full validation default.
    """
    return save_typed(
        path, state, magic=STATE_MAGIC, schema=STATE_SCHEMA_VERSION,
        validate=validate_session if validate else None)


def save_session_with_digest(
    path: str | Path,
    state: SessionState,
    *,
    validate: bool = True,
) -> tuple[bool, str]:
    """Persist once and return its already-computed authoritative digest."""
    return save_typed_with_digest(
        path, state, magic=STATE_MAGIC, schema=STATE_SCHEMA_VERSION,
        validate=validate_session if validate else None)


def load_session(
    path: str | Path,
    *,
    format_row_id: str | None = None,
    defer_fountain_validation: bool = False,
) -> SessionState:
    if type(defer_fountain_validation) is not bool:
        raise TypeError("defer_fountain_validation must be bool")
    validator = (
        (lambda state: validate_session(
            state, defer_fountain_validation=True))
        if defer_fountain_validation else validate_session
    )
    state = load_typed(
        path, SessionState, magic=STATE_MAGIC,
        schema=STATE_SCHEMA_VERSION, validate=validator,
        migrations=STATE_MIGRATIONS)
    if format_row_id is not None and state.format_row_id != format_row_id:
        raise ValueError(
            f"receive state format {state.format_row_id!r} != requested "
            f"{format_row_id!r}")
    return state


def load_session_with_digest(
    path: str | Path,
    *,
    format_row_id: str | None = None,
    defer_fountain_validation: bool = False,
) -> tuple[SessionState, str]:
    """Load/validate once while retaining the verified envelope digest."""
    if type(defer_fountain_validation) is not bool:
        raise TypeError("defer_fountain_validation must be bool")
    validator = (
        (lambda state: validate_session(
            state, defer_fountain_validation=True))
        if defer_fountain_validation else validate_session
    )
    state, digest = load_typed_with_digest(
        path, SessionState, magic=STATE_MAGIC,
        schema=STATE_SCHEMA_VERSION, validate=validator,
        migrations=STATE_MIGRATIONS)
    if format_row_id is not None and state.format_row_id != format_row_id:
        raise ValueError(
            f"receive state format {state.format_row_id!r} != requested "
            f"{format_row_id!r}")
    return state, digest


__all__ = [
    "STATE_MAGIC", "STATE_MIGRATIONS", "STATE_SCHEMA_VERSION", "BarrierDelta",
    "CaptureConflictError", "CaptureFacts", "CaptureRecord",
    "CaptureStatus", "LevelRecord", "LevelStatus", "SessionCounters",
    "SessionIndex", "StageTally",
    "SessionState", "SessionStatus", "append_level_barrier",
    "apply_close", "authoritative_bytes", "authoritative_sha256",
    "detach_close",
    "certificate_frontier_sha256", "load_session",
    "load_session_with_digest", "save_session", "save_session_with_digest",
    "state_payload", "validate_session",
]
