"""Format-bound validation for the receive runtime's durable state.

The generic session replay validates graph integrity.  These checks bind the
lean durable records back to facts derived from the active format row and the
receive algorithms before the runtime consumes or commits them.

The two load-time CONTINUATION rules live here together because they have
the same shape — an archived state is bound to today's world, in memory,
before the run starts, writing nothing until a barrier legitimately does:
:func:`adopt_current_scale_plans` (the plan half, RECEIVE-DESIGN §8) and
:func:`policy_detach` (the id half, §9c).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction

import numpy as np

from ..format.descriptor import FormatSpec
from .scale_space import AreaPixelTransform
from .session import (
    BarrierDelta,
    CaptureFacts,
    CaptureRecord,
    LevelRecord,
    SessionState,
)
from .types import (
    AddressArtifact,
    EvidenceBlock,
    LaneSpec,
    TileCertificateRecord,
)


def validate_lane_request(
    request: object,
    facts: CaptureFacts,
    expected_lane: LaneSpec,
) -> None:
    """Bind a transient lane view to its authoritative plan position."""
    from .runtime import LaneRequest

    if not isinstance(request, LaneRequest):
        raise TypeError("scheduler returned a non-LaneRequest")
    if request.spec != expected_lane:
        raise ValueError("lane request differs from the scale plan")
    if request.raster.source_sha256 != facts.source_sha256:
        raise ValueError("lane request belongs to another source")
    if str(np.dtype(request.raster.native_dtype)) != facts.dtype:
        raise ValueError("lane request dtype differs from the source")
    transform = AreaPixelTransform(Fraction(
        expected_lane.native_per_view_num,
        expected_lane.native_per_view_den,
    ))
    if tuple(request.raster.shape) != transform.output_shape(facts.shape_yx):
        raise ValueError("lane request shape differs from the scale plan")
    expected_dpi = float(
        Fraction(str(facts.dpi))
        * expected_lane.native_per_view_den
        / expected_lane.native_per_view_num
    )
    if float(request.raster.dpi) != expected_dpi:
        raise ValueError("lane request dpi differs from the scale plan")


def validate_certificates(
    certificates: tuple[TileCertificateRecord, ...], spec: FormatSpec,
) -> None:
    """Reconstruct and verify the exact E023/E023c certificate identity."""
    from .records import validate_certificate_record

    for row in certificates:
        validate_certificate_record(row, spec)


def validate_attempts(
    attempts: tuple[object, ...], spec: FormatSpec,
) -> None:
    """Bind retained attempt policy/counters to the requested format row."""
    from ..format.profiles import Family
    from .color_attempts import effective_demap_iterations
    from .records import (
        validate_attempt_record_identity,
    )
    from .tiles import (
        BASELINE_BP_MAX_ITERS,
        RETRY_BP_MAX_ITERS,
        k_eff_bits,
    )
    from .types import AttemptStage, AttemptState, TileAttemptRecord

    for value in attempts:
        if not isinstance(value, TileAttemptRecord):
            raise TypeError("attempt ledger contains a foreign record")
        expected_iters = (RETRY_BP_MAX_ITERS
                          if value.stage is AttemptStage.RETRY150
                          else BASELINE_BP_MAX_ITERS)
        spec.tile_counter(
            value.page, value.tile_yx[0], value.tile_yx[1])
        # Same EFFECTIVE budget the minting call read, for the same
        # reason the iteration bound below reads it: the demap count is
        # part of a CMY7 attempt's decoder identity.
        validate_attempt_record_identity(
            value, spec, demap_iterations=effective_demap_iterations())
        profile = spec.stream_profile(value.stream_id)
        if spec.codec_family is Family.K:
            k_eff = k_eff_bits(spec)
            n_nonshort = spec.n_transmitted_slots
        else:
            # Color evidence counts physical payload cells. CMY7's mapper
            # expands four complete observed cells to eleven code LLRs, so
            # its decoder floor cannot be reconstructed from this scalar.
            k_eff = None
            n_nonshort = spec.payload_cells
        if value.n_informative > n_nonshort:
            raise ValueError("attempt policy or address differs from format")
        expected_children = len(profile.fec.children)
        if spec.codec_family is Family.K:
            if value.child_outcomes:
                raise ValueError("K attempt unexpectedly carries child rows")
            if (value.state is AttemptState.ATTEMPTED_FAILED
                    and type(value.crc_ok) is not bool):
                raise ValueError(
                    "K failed attempt must retain its CRC result")
        elif (value.state is AttemptState.BELOW_ATTEMPT_FLOOR
              and value.child_outcomes):
            raise ValueError("below-floor color attempt has child outcomes")
        elif (value.state is not AttemptState.BELOW_ATTEMPT_FLOOR
              and len(value.child_outcomes) != expected_children):
            raise ValueError(
                "color attempt child count differs from its FEC bank")
        # A CMY7 attempt may run its demapper and the frame decoder more
        # than once (color-uplift P3: soft iteration inside ONE attempt),
        # and `n_iters` is the BP work summed over those inner decodes.  It
        # reads the EFFECTIVE budget, so a force-null run is validated
        # against the pre-campaign bound it actually executed.  At one
        # iteration both bounds are exactly the historical ones, including
        # the rule that a failed child spent both passes; above one a child
        # can succeed under one prior and fail under the next, so only the
        # budget bound survives.
        passes = (
            effective_demap_iterations()
            if spec.codec_family is Family.CMY7
            else 1
        )
        iteration_limit = 2 * expected_iters * expected_children * passes
        if spec.codec_family is not Family.K:
            child_limit = 2 * expected_iters * passes
            for child_iters, child_syndrome in value.child_outcomes:
                if (child_iters > child_limit
                        or (not child_syndrome and passes == 1
                            and child_iters != child_limit)):
                    raise ValueError(
                        "color child iteration count differs from decoder "
                        "execution")
        if (value.n_iters > iteration_limit
                or (spec.codec_family is Family.K
                    and value.syndrome_ok is False
                    and value.n_iters != iteration_limit)):
            raise ValueError(
                "attempt iteration count differs from decoder execution")
        if k_eff is None:
            continue
        if value.state is AttemptState.BELOW_ATTEMPT_FLOOR:
            valid = value.n_informative < k_eff
        else:
            valid = value.n_informative >= k_eff
        if not valid:
            raise ValueError("attempt state differs from format attempt floor")


def validate_blocks_for_spec(
    blocks: tuple[EvidenceBlock, ...], spec: FormatSpec,
) -> None:
    """Bind compact payload slots and tile addresses to the format row."""
    from .payload import format_reference_values

    height, width = spec.layout.cells_yx
    tiles_y, tiles_x = spec.layout.tiles_yx
    expected_kind = spec.codec_family.value
    for block in blocks:
        if block.kind != expected_kind:
            raise ValueError(
                f"{spec.codec_id}: {block.kind} evidence kind is invalid")
        if (not 0 <= block.page < spec.max_pages
                or not 0 <= block.tile_yx[0] < tiles_y
                or not 0 <= block.tile_yx[1] < tiles_x):
            raise ValueError("payload block address is outside the format")
        flat = block.observed_flat().astype(np.int64)
        cells = np.column_stack((
            block.tile_yx[0] * 64 + flat // 64,
            block.tile_yx[1] * 64 + flat % 64,
        )).astype(np.int32)
        if (np.any(cells < 0) or np.any(cells[:, 0] >= height)
                or np.any(cells[:, 1] >= width)):
            raise ValueError("payload block cell lies outside the format")
        expected = format_reference_values(spec, block.page, cells)
        if np.any(expected != -1):
            raise ValueError(
                "payload block retains a format-predictable site")


def validate_bch_conflicts_for_spec(
    artifact: AddressArtifact | None,
    page_hypotheses: tuple[int, ...] | None,
    spec: FormatSpec,
) -> None:
    """Bind durable BCH contradictions to exact format-v1 addresses."""
    if artifact is None:
        return
    allowed = None if page_hypotheses is None else frozenset(page_hypotheses)
    tiles_y, tiles_x = spec.layout.tiles_yx
    for row in artifact.bch_conflicts:
        if (not 0 <= row.page < spec.max_pages
                or (allowed is not None and row.page not in allowed)):
            raise ValueError("BCH conflict page is outside the receive domain")
        if (not 0 <= row.tile_yx[0] < tiles_y
                or not 0 <= row.tile_yx[1] < tiles_x):
            raise ValueError("BCH conflict tile is outside the format")
        expected_counter = spec.tile_counter(
            row.page, row.tile_yx[0], row.tile_yx[1])
        if row.decoded_counter == expected_counter:
            raise ValueError("BCH conflict decoded counter matches the format")
        if row.decoded_counter >= spec.max_tiles_addressable:
            raise ValueError("BCH conflict decoded counter is outside the format")


def validate_page_domain_records(
    records: SessionState | BarrierDelta,
    page_hypotheses: tuple[int, ...] | None,
    spec: FormatSpec,
) -> None:
    """Bind every durable page-bearing record to the declared search domain."""
    allowed = None if page_hypotheses is None else frozenset(page_hypotheses)

    def require(label: str, page: int) -> None:
        if not 0 <= page < spec.max_pages:
            raise ValueError(f"{label} page is outside the format")
        if allowed is not None and page not in allowed:
            raise ValueError(f"{label} page is outside the receive domain")

    for attribute, label in (
        ("poses", "pose"),
        ("proposals", "pose proposal"),
        ("losers", "losing hypothesis"),
        ("blocks", "evidence block"),
        ("attempts", "tile attempt"),       # BarrierDelta only (transient)
        ("certificates", "tile certificate"),
    ):
        for row in getattr(records, attribute, ()):
            require(label, row.page)


def policy_scale_plan(dpi: float, spec: FormatSpec) -> tuple[LaneSpec, ...]:
    """Today's lane plan for one capture under this format row."""
    from .cascade import scale_plan

    return scale_plan(
        dpi, spec.cell_dots,
        codec_family=spec.codec_family, n_streams=spec.n_streams)


def scale_plan_tail(
    stored: tuple[LaneSpec, ...], policy: tuple[LaneSpec, ...],
) -> tuple[LaneSpec, ...]:
    """The lanes today's plan APPENDS to one stored capture plan.

    The plan-prefix rule.  A capture recorded before a lane family joined
    the ladder carries a plan that is a strict PREFIX of today's — the
    PLANE-FIELDS ``u0x-field`` arm is the case that forced this, exactly
    as the ``off``/``a3``/``a4b`` arms would have.  The phased schedule
    already treats a capture's completed lanes as a prefix (its phase
    cursor is DERIVED from per-capture prefix lengths and never stored —
    docs/PHASED-SCHEDULE.md D1; RECEIVE-DESIGN §8), so an appended tail
    is a capture with work still owed, not a corrupt record.

    Accepted: the stored entries are today's first entries, in order.
    Refused, naming the first offending lane: any stored entry that
    differs (the STANDARD ladder moved, so the retained levels no longer
    correspond to the lanes that produced them) and any stored plan
    LONGER than today's (a lane was retired under a live state).  This is
    the rule the replay instruments have run against this archive since
    PK4.3 (``tests/holo/_color_uplift_harness/replay.replay_plan``,
    ``measure/plane_fields/_swim_inputs.require_plan_prefix``); by
    construction of :func:`cascade._scale_plan` the accepted tail can only
    be supplemental lanes, because any ladder change moves an ``l``/``m``/
    ``r`` entry and breaks the prefix.
    """
    if len(stored) > len(policy):
        raise ValueError(
            "capture scale plan is longer than format policy: stored lane "
            f"{stored[len(policy)].lane_id!r} has no counterpart in the "
            f"{len(policy)}-lane policy plan")
    for ordinal, (old, new) in enumerate(zip(stored, policy)):
        if old == new:
            continue
        detail = (
            f"lane {old.lane_id!r} geometry differs"
            if old.lane_id == new.lane_id
            else f"stored {old.lane_id!r}, policy schedules {new.lane_id!r}")
        raise ValueError(
            "capture scale plan differs from format policy at lane "
            f"{ordinal}: {detail}")
    return policy[len(stored):]


def adopt_current_scale_plans(
    state: SessionState, spec: FormatSpec,
) -> SessionState:
    """Bind every retained capture to TODAY's lane plan (the prefix rule).

    The driver half of :func:`scale_plan_tail`.  The runtime already
    SCHEDULES from today's plan — ``_CaptureSlot.plan`` is recomputed at
    ingest and the phase cursor is the retained prefix length — but the
    capture RECORD is what says how many lanes the capture owes
    (``CaptureRecord.status``) and what the barrier and cascade tripwires
    compare against.  Adopting today's plan at load, with the retained
    levels untouched, is therefore "schedule from today's plan with the
    stored prefix completed" expressed in the one place the code reads it.

    Flag-free by construction (the invocation's ``--refine``/``--mopup``
    bound decides how far the tail is DRIVEN, never what the record says
    is owed).  Nothing is written: the on-disk record changes only when a
    barrier legitimately rewrites that capture.
    """
    captures = []
    adopted = False
    for capture in state.captures:
        policy = policy_scale_plan(capture.dpi, spec)
        if scale_plan_tail(capture.plan, policy):
            capture = replace(capture, plan=policy)
            adopted = True
        captures.append(capture)
    if not adopted:
        return state
    return replace(state, captures=tuple(captures))


@dataclass(frozen=True, slots=True)
class PolicyDetach:
    """What one policy-epoch change kept, dropped, and recorded.

    The derivation publishes its own census (nothing downstream has to
    diff two states to find out what happened).  ``kept``/``dropped`` are
    ``(ledger, rows)`` pairs in state-model order.
    """

    state: SessionState
    previous_policy_id: str
    segments_moved: tuple[str, ...]
    kept: tuple[tuple[str, int], ...]
    dropped: tuple[tuple[str, int], ...]

    @staticmethod
    def _census(rows: tuple[tuple[str, int], ...]) -> str:
        listed = ", ".join(
            f"{count} {label}" for label, count in rows if count)
        return listed if listed else "nothing"

    @property
    def message(self) -> str:
        """The one operator line, emitted once at load."""
        return (
            f"policy detach: {', '.join(self.segments_moved)} moved; "
            f"kept {self._census(self.kept)}; "
            f"dropped {self._census(self.dropped)}; continuing as policy "
            f"epoch {len(self.state.policy_lineage) + 1} "
            "(previous id in the state's policy lineage)")


def policy_detach(
    state: SessionState, policy_id: str,
) -> "PolicyDetach | None":
    """Continue one archived session under TODAY's receiver policy.

    The id half of archive compatibility (user ruling 2026-08-23);
    sibling of the ``--no-close`` ``session.detach_close`` and of the
    plan half directly above, :func:`adopt_current_scale_plans`, whose
    load-time placement and write-nothing discipline it shares.  A
    receiver policy id is a READABLE five-component composition
    (``runtime_model._semantic_pipeline_policy_id``), so a state whose id
    differs is not opaquely foreign: exactly which semantic components
    moved is legible, and each durable ledger belongs to exactly one of
    them.  Returns ``None`` when the state already runs today's policy —
    the fixed point, byte-identical behaviour.

    Keep / drop, and why (the state model is
    :mod:`holo.receive.session_model`):

    ``certificates``  KEPT always.  A certificate is CRC+LDPC-verified
      against the FORMAT and its identity is re-validated against the
      format row at every load (``SessionIndex._validate_stream_record``).
      It is gate-verified truth, not a policy opinion; no receiver policy
      can make a solved tile unsolved.  Keeping them is what makes a
      detached resume monotone.
    ``captures``  KEPT always: authenticated source SHA, dpi, dtype,
      shape, channels, the lane plan (already rebound to today's ladder
      by the plan-prefix repair, which runs BEFORE this and refuses an
      incompatible ladder), and the retained level prefix — the record of
      which lanes have run.  Rung correspondence is by ppc, never
      ordinal (RECEIVE-DESIGN v0.33).
    ``regions``, ``poses``  KEPT unless their owning segment moved.
      A region is the survey's support mask, a pose is a placement the
      BCH address words VALIDATED — physical facts about the sheet.  They
      are also the referents the retained level artifacts name
      (``_validate_structural``), so keeping the levels means keeping
      them.
    ``proposals``, ``losers``, ``parked``  DROPPED when the ADDRESS
      segment moved.  These are search state, scored and priced by the
      address policy that produced them: retained candidates for exact
      revisit, and parked windows carrying the old policy's
      ``attempted_routes`` for a mop-up level that will run under the new
      one.  Dropping forfeits future yield, never a certificate.  The
      retained address artifacts stop naming them, so the state stays
      internally consistent.
    ``blocks``  DROPPED when the PAYLOAD segment moved.  An evidence
      block holds float32 LLRs/state scores minted by the detector,
      calibration and demapper the payload segment names; summing them
      with values from a different demapper is exactly the cross-policy
      mixing the id exists to prevent.  Certificates already carry
      everything a solved tile proved.
    ``close``  KEPT.  A terminal close is a pure derivation from the
      certificate set and is re-reproduced numerically at load
      (:func:`validate_session`); ``--no-close`` detaches it as today,
      and a later closing run recomputes it.
    ``counters``  KEPT: monotone work tallies (advice, never a gate).
      They now span epochs, which is what the lineage records.
    BCH quarantine (inside the retained address artifacts)  KEPT.  "When
      in doubt, drop" applies to derived YIELD; a quarantine is a
      REFUSAL, minted from contradictory decoded words, and dropping one
      would widen the accepted set.

    Refused, because the model cannot detach them safely:

    * the SURVEY segment moved — regions are its durable product, every
      retained level names them through its survey artifact, and poses
      reference them; there is no keep-the-levels detach.  The answer
      when that day comes is a full re-derivation detach (drop the level
      histories too, keep the certificates), which is a bigger ruling
      than this one.
    * either id is not a kiss-v1 five-component composition (a hashed,
      truncated or foreign id) — a detach that cannot classify the change
      cannot be safe.

    Refusals that still stand ahead of this one, unchanged: a format row
    or page domain that differs, a stored lane plan that is not a prefix
    of today's, and any state whose structure does not validate.
    """
    from .runtime_model import parse_pipeline_policy_id

    previous = state.receiver_policy_id
    if previous == policy_id:
        return None
    stored = parse_pipeline_policy_id(previous)
    today = parse_pipeline_policy_id(policy_id)
    moved = tuple(
        label for label, identity in stored.items()
        if today[label] != identity)
    if "survey" in moved:
        raise ValueError(
            "receive state belongs to a different survey policy: its "
            "region ledger cannot be detached while its level histories "
            "name it")
    address_moved = "address" in moved
    payload_moved = "payload" in moved
    captures = (
        _forget_address_search(state.captures) if address_moved
        else state.captures)
    detached = replace(
        state,
        receiver_policy_id=policy_id,
        policy_lineage=state.policy_lineage + (previous,),
        captures=captures,
        proposals=() if address_moved else state.proposals,
        losers=() if address_moved else state.losers,
        parked=() if address_moved else state.parked,
        blocks=() if payload_moved else state.blocks,
    )
    return PolicyDetach(
        detached, previous, moved,
        # The census names the ledgers a detach REASONS about; the
        # capture records it always keeps whole are already reported by
        # ``session.open`` (``captures.retained``).
        kept=(("certificates", len(detached.certificates)),
              ("poses", len(detached.poses)),
              ("regions", len(detached.regions))),
        dropped=(
            ("proposals", len(state.proposals) - len(detached.proposals)),
            ("losing hypotheses", len(state.losers) - len(detached.losers)),
            ("parked windows", len(state.parked) - len(detached.parked)),
            ("evidence blocks", len(state.blocks) - len(detached.blocks))),
    )


def _forget_address_search(
    captures: tuple[CaptureRecord, ...],
) -> tuple[CaptureRecord, ...]:
    """Stop the retained address artifacts naming dropped search records.

    The barrier invariant is that an address artifact names EXACTLY its
    barrier's records (``_validate_delta``); a detach that drops the
    proposal/loser/parked ledgers keeps that shape by clearing the three
    id lists.  Poses, the survey binding, and the BCH quarantine — the
    parts that survive the detach — are untouched.
    """
    output: list[CaptureRecord] = []
    for capture in captures:
        levels: list[LevelRecord] = []
        for level in capture.levels:
            address = level.address
            if address is not None and (
                    address.proposal_ids or address.loser_ids
                    or address.parked_ids):
                level = replace(level, address=replace(
                    address, proposal_ids=(), loser_ids=(), parked_ids=()))
            levels.append(level)
        rewritten = tuple(levels)
        output.append(
            capture if rewritten == capture.levels
            else replace(capture, levels=rewritten))
    return tuple(output)


def validate_state_for_spec(state: SessionState, spec: FormatSpec) -> None:
    """Bind every format-derived fact omitted from one lean session."""
    from .scale_space import ScaleSchedule
    if (state.page_hypotheses is not None
            and any(page >= spec.max_pages for page in state.page_hypotheses)):
        raise ValueError("state page domain exceeds the format counter range")
    validate_page_domain_records(state, state.page_hypotheses, spec)
    for capture in state.captures:
        scale_plan_tail(capture.plan, policy_scale_plan(capture.dpi, spec))
        schedule = ScaleSchedule.auto(capture.dpi, spec.cell_dots)
        by_label = {row.label: row for row in schedule.levels}
        # v0.33/v0.42: every retained level validates against its plan
        # entry's BASE lane geometry (mop-up and refinement levels share
        # their base lane's exact transform), and the loop covers the
        # whole retained prefix — the former ladder zip silently truncated.
        for ordinal, level in enumerate(capture.levels):
            lane = capture.plan[ordinal]
            expected = by_label.get(lane.base_lane_id)
            if expected is None:
                raise ValueError("capture level has no ladder geometry")
            if min(expected.transform.output_shape(capture.shape_yx)) < 1:
                raise ValueError("retained scale has no complete source pixel")
            validate_bch_conflicts_for_spec(
                level.address, state.page_hypotheses, spec)
    validate_blocks_for_spec(state.blocks, spec)
    validate_certificates(state.certificates, spec)


__all__: list[str] = []
