"""Committed-pose payload replay: the campaign's development signal.

One replay re-runs ONLY the payload side of an archived decode.  Survey,
address search, cold ladder and word routes never run: every lane's
geometry is the archived state's own committed ``PoseRecord`` rows,
reconstructed through the production seam ``place.place_committed`` (the
same audited re-derivation the v0.42 R level uses), and the payload
barrier is the production ``ProductionColorPayload`` processor itself —
not a re-implementation.  What a replay measures is therefore exactly the
payload/evidence axis this campaign changes.

Lane semantics mirrored from ``production_color`` / ``evidence_context``:

* ordinary lane ``Lk`` — ``place_committed`` over ``Lk``'s own committed
  poses and its own durable regions;
* mop-up lane ``M(Lk)`` — ``place_committed`` over ``M(Lk)``'s own minted
  poses with ``Lk``'s regions, plus ``Lk``'s poses reconstructed as D7
  label placements (pool law L3/L5), and the D5 supersession against the
  base lane's retained blocks;
* refinement lane ``R(Lk)`` — the production ``RefineAddressPlan`` path
  verbatim (``place_committed`` over ``Lk``'s poses, then
  ``refine_color_address_once`` and the affected-region delta);
* supplemental lane ``U(Lk, arm)`` (PK4.3) — the same plan shape, and
  the production leaf again: no pose refinement, one forced arm, and the
  uncertified residue as its domain.

THE PLAN COMES FROM PRODUCTION, NOT FROM THE ARCHIVE (PK4.3).
``replay_plan`` calls ``cascade.scale_plan`` for this capture's coding
and requires the archived plan to be an exact PREFIX of it; the entries
past that prefix are supplemental lanes the archived decode never ran,
and they are driven with a synthetic empty level.  So u-lanes appear in
a replay because the receiver schedules them, never because the harness
appended them, and a plan change in production cannot be measured
around.

Certificates accumulate lane by lane under the prior-barrier law: a
certificate minted in lane N first conditions and suppresses in lane
N+1.  Evidence-block retention mirrors ``append_level_barrier`` exactly
(a fully certified address leaves the frontier).

KNOWN REPLAY-FIDELITY LIMITS (report them, never paper over them):

1. ``place_committed`` re-derives the region aperture from the MEDIAN
   committed pose pitch and re-audits every window; a window whose
   support no longer re-derives is skipped.  The archived ordinary lane
   instead placed against its survey's own aperture.
2. Mop-up label placements come from ``place_committed`` and therefore
   skip ``_label_patch``'s candidate re-score gate, so the label pool may
   be a superset of the archived one.  The parked inventory that drove
   the archived mop-up is RETIRED from the state at its own barrier, so
   an exact mop-up address replay is structurally impossible from the
   state alone.
3. A replay conditions on certificates in the archived barrier order.
   For a stage that consumes certified content (P9/PK10) that is a KILL
   TEST only — see COLOR-UPLIFT-PLAN §4.

MEASURED (PK0, 2026-08-07): on xerox c3-cmy7 neither (1) nor (2) bit —
the baseline replay reproduced all twelve archived barriers cert-for-cert
(720/720, every lane exact, close VERIFIED to the emitted payload SHA).
The limits stay documented because they are structural, not because they
were observed.

``record_attempts`` retains each lane's own ``TileAttemptRecord`` rows on
the returned ``LaneReplay`` so a caller can compare TILE-LEVEL decode
margins (``n_iters`` against the 60/150 BP caps, ``syndrome_ok``,
``crc_ok``, per-child ``child_outcomes``) and not merely certificate
counts.  The rows are the payload stage's own durable records, passed
through untouched; retention is opt-in so established runs keep their
exact memory profile.

One lane's ``cpu_s`` includes its ``place_committed`` reconstruction,
which the archived run charged to its ADDRESS stage — replay CPU is
therefore comparable arm-to-arm but not directly to an archived payload
stage total.  ``build_address_s`` (PK2) reports that reconstruction's own
CPU separately, so an arm's PAYLOAD cost is ``cpu_s - build_address_s``:
the reconstruction is arm-invariant work and would otherwise dilute every
A/B cost comparison.  ``cpu_s`` keeps its combined meaning on purpose —
the archived baseline run JSONs predate this field and carry the combined
number, and no baseline was re-run to add it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Callable

from .state_cache import CaptureCache, LevelFacts


@dataclass(frozen=True, slots=True)
class LaneReplay:
    """One replayed barrier's measured outcome."""

    ordinal: int
    lane_id: str
    lane_kind: str
    evidence_lane_id: str
    placements: int
    label_placements: int
    prior_certificates: int
    blocks: int
    attempts: int
    certificates: tuple
    details: dict
    wall_s: float
    cpu_s: float
    # CPU spent reconstructing this lane's committed geometry, already
    # INCLUDED in ``cpu_s`` (see the module docstring).
    build_address_s: float = 0.0
    skipped: str | None = None
    # The lane's own ``TileAttemptRecord`` rows, retained only when the
    # caller asked for them (``record_attempts``).  These are the payload
    # stage's OWN durable rows, passed through untouched — the harness
    # neither derives nor reinterprets them.  Empty by default so the
    # established runs keep their exact memory profile.
    attempt_rows: tuple = ()


class EventRecorder:
    """Headless observer: keeps the payload stage's own detail rows.

    When an ``EventSink`` is attached (``--diag``) every event is ALSO
    forwarded verbatim to it, so the production diagnostics/viewer see
    exactly the stage's own event stream.  The observer boundary is
    strictly downstream (RECEIVE-DESIGN §10): nothing here can change a
    decode outcome, only its wall time.
    """

    __slots__ = ("rows", "sink")

    def __init__(self, sink=None) -> None:
        self.rows: list[tuple[str, dict]] = []
        self.sink = sink

    def emit(self, name, stage, *, capture_id=None, message="",
             details=(), authority=None, snapshot_factory=None) -> None:
        self.rows.append(
            (name, {row.name: row.value for row in details}))
        if self.sink is not None:
            kwargs = {"capture_id": capture_id, "message": message,
                      "details": details,
                      "snapshot_factory": snapshot_factory}
            if authority is not None:
                kwargs["authority"] = authority
            self.sink.emit(name, stage, **kwargs)

    def observer_enabled(self) -> bool:
        return self.sink is not None and bool(self.sink.enabled)

    def snapshots_enabled(self) -> bool:
        return self.sink is not None and bool(self.sink.snapshots_enabled)

    def isolate(self, stage, capture_id):
        if self.sink is None:
            return lambda name, callback: None
        return lambda name, callback: self.sink.isolate_adapter(
            name, stage, capture_id, callback)

    def take(self) -> list[tuple[str, dict]]:
        rows = self.rows
        self.rows = []
        return rows


def _lane_kind(lane) -> str:
    """The production vocabulary, from the ONE implementation of it."""
    from holo.receive.cascade import lane_kind

    return lane_kind(lane)


def replay_plan(cache: CaptureCache, spec):
    """``(plan, levels)`` — the PRODUCTION plan, with archived levels.

    PK4.3: the replay no longer walks the archived plan.  It asks the
    production plan builder what this capture's plan IS today
    (``cascade.scale_plan``, codec-aware) and requires the archived plan
    to be an exact PREFIX of it; the entries beyond that prefix are the
    supplemental tail the archived decode never ran, and they get a
    synthetic empty level so the replay drives them like any other.

    Driving the real builder (rather than appending u-lanes in the
    harness) is what makes the measurement mean something: if production
    changes which supplemental lanes exist, at which footing, or in which
    order, the replay changes with it and cannot silently measure a plan
    the receiver would not schedule.  The prefix check is the tripwire —
    any change to the STANDARD ladder invalidates the archived levels and
    must stop the run rather than re-index them.
    """
    from holo.receive.cascade import scale_plan

    plan = scale_plan(
        cache.capture_dpi, spec.cell_dots,
        codec_family=spec.codec_family, n_streams=spec.n_streams)
    archived = tuple(cache.plan)
    if plan[:len(archived)] != archived:
        raise SystemExit(
            f"{cache.key}: the archived plan is not a prefix of the "
            "production plan — the standard ladder moved, so the archived "
            "levels cannot be replayed against it")
    levels = list(cache.levels)
    for ordinal in range(len(levels), len(plan)):
        lane = plan[ordinal]
        if lane.uplift_of is None:
            raise SystemExit(
                f"{cache.key}: plan entry {lane.lane_id} has no archived "
                "level and is not a supplemental lane")
        levels.append(LevelFacts(
            ordinal=ordinal,
            lane_id=lane.lane_id,
            survey_id=None,
            address_id=f"{cache.capture_sha256}/{lane.lane_id}/address",
            # Non-None so the replay RUNS this level: there is no
            # archived payload to compare against, which is the point.
            payload_id=f"{cache.capture_sha256}/{lane.lane_id}/payload",
            certificate_ids=(),
            quarantined_patch_ids=(),
            pose_ids=(),
            n_blocks=0,
            n_attempts=0,
        ))
    return plan, tuple(levels)


def _capture_facts(cache: CaptureCache):
    from holo.receive.session import CaptureFacts

    return CaptureFacts(
        cache.capture_sha256, cache.capture_dpi, cache.capture_dtype,
        cache.capture_shape_yx, cache.capture_channels)


class LaneRasterFactory:
    """Exact per-lane derived rasters, pooled for the native's lifetime.

    Reuses the production cascade: the same exact-rational area
    decimation, the same disk-backed mmap pooling, keyed by the lane's
    BASE lane label so mop-up and refinement levels reuse their base
    derivation exactly as the scheduler does.
    """

    def __init__(self, native, spec, facts) -> None:
        from holo.receive.runtime_model import ScheduleContext
        from holo.receive.scale_space import ScaleSchedule

        self._native = native
        self._schedule = ScaleSchedule.auto(native.dpi, spec.cell_dots)
        self._levels = {level.label: level for level in self._schedule.levels}
        self._context = ScheduleContext(
            spec, native, facts, None,
            _unsupported, _unsupported, _unsupported,
            lambda *args, **kwargs: None, lambda: False)

    def for_lane(self, lane):
        from holo.receive.cascade import _materialize

        return _materialize(self._context, self._levels[lane.base_lane_id])

    def release(self) -> None:
        from holo.receive.cascade import release_derived_lanes

        release_derived_lanes(self._native)


def _unsupported(*args, **kwargs):
    raise RuntimeError("a replay drives no lanes, evidence, or barriers")


def _lane_snapshot(raster, facts, lane, evidence):
    """The production lane snapshot (pane A seed) — real inputs only."""
    from holo.receive import _diagnostic_snapshots as snapshots

    return snapshots.lane(raster, facts, lane, evidence)


def _survey_product(cache: CaptureCache, lane, regions):
    from holo.receive.types import SurveyArtifact, SurveyProduct

    return SurveyProduct(
        SurveyArtifact(
            f"{cache.capture_sha256}/{lane.lane_id}/survey",
            tuple(row.region_id for row in regions)),
        tuple(regions))


def _ordered_poses(poses, placements) -> tuple:
    """Archived pose rows in the exact order ``place_committed`` placed."""
    by_patch = {int(row.patch_id): row for row in poses}
    return tuple(by_patch[int(patch.patch_id)] for patch in placements)


def _address_product(cache: CaptureCache, lane, survey, poses, transient):
    from holo.receive.types import AddressArtifact, AddressProduct

    prefix = f"{cache.capture_sha256}/{lane.lane_id}"
    return AddressProduct(
        AddressArtifact(
            f"{prefix}/address", survey.artifact.survey_id,
            tuple(row.pose_id for row in poses)),
        tuple(poses),
        transient=transient,
    )


def _lane_poses(cache: CaptureCache, lane_id: str,
                quarantined: frozenset[int]) -> tuple:
    return tuple(
        row for row in cache.poses_by_lane.get(lane_id, ())
        if int(row.patch_id) not in quarantined)


def _quarantined(cache: CaptureCache, lane_id: str) -> frozenset[int]:
    """Union quarantine at one EVIDENCE lane (mirrors _quarantine_index)."""
    values: set[int] = set()
    for level, lane in zip(cache.levels, cache.plan, strict=False):
        if lane.evidence_lane_id == lane_id:
            values.update(level.quarantined_patch_ids)
    return frozenset(values)


def build_address(cache: CaptureCache, spec, lane, level, raster,
                  prior_certificates: tuple):
    """Return (survey_product, address_product, label_count) for one lane."""
    from holo.receive.place import place_committed
    from holo.receive.placement.model import AddressResult
    from holo.receive.types import RefineAddressPlan

    base_lane_id = lane.base_lane_id
    regions = cache.regions_by_lane.get(base_lane_id, ())
    if not regions:
        raise ValueError(
            f"{lane.lane_id}: base lane {base_lane_id} has no durable regions")
    survey = _survey_product(cache, lane, regions)
    # ``_quarantine_index`` keys on the EVIDENCE lane, and a mop-up or
    # refinement level's base lane IS that key (evidence_context.py:117,
    # :159): a quarantined placement never re-enters the payload domain.
    base_quarantined = _quarantined(cache, base_lane_id)

    if lane.refine_of is not None or lane.uplift_of is not None:
        # The R level's own address stage mints nothing; the payload stage
        # consumes the typed plan (production.py:650).  PK4.3: a U level
        # takes exactly the same shape from the same base lane — the two
        # differ only in what their payload leaves do with it.
        plan = RefineAddressPlan(
            base_lane_id=base_lane_id,
            poses=_lane_poses(cache, base_lane_id, base_quarantined),
            regions=tuple(regions),
            certificates=prior_certificates,
        )
        return survey, _address_product(cache, lane, survey, (), plan), 0

    own = _lane_poses(cache, lane.lane_id, frozenset(
        level.quarantined_patch_ids))
    result = place_committed(
        raster, spec, poses=own, regions=tuple(regions))
    labels = 0
    if lane.mopup_of is not None:
        # D7 pool law: the base pass's placed poses reconstruct as
        # calibration labels at the M level.
        base_poses = _lane_poses(cache, lane.mopup_of, base_quarantined)
        placed_ids = {int(row.patch_id) for row in result.placements}
        label_result = place_committed(
            raster, spec,
            poses=tuple(row for row in base_poses
                        if int(row.patch_id) not in placed_ids),
            regions=tuple(regions))
        label_rows = tuple(
            replace(patch, route="label", redundant=True, observations=())
            for patch in label_result.placements)
        result = replace(result, label_placements=label_rows)
        labels = len(label_rows)
    if not isinstance(result, AddressResult):
        raise TypeError("place_committed returned a foreign result")
    poses = _ordered_poses(own, result.placements)
    return survey, _address_product(cache, lane, survey, poses, result), labels


def replay_lanes(
    cache: CaptureCache,
    spec,
    native,
    *,
    defer_fountain_close: bool,
    lane_filter: Callable[[object], bool] | None = None,
    progress: Callable[[str], None] | None = None,
    sink=None,
    record_attempts: bool = False,
    seed_archived_certificates: bool = False,
    stack_config=None,
) -> tuple[list[LaneReplay], list]:
    """Replay every archived payload barrier; return lanes + certificates.

    ``stack_config`` (``holo.receive.color_stack.StackConfig``) is the
    campaign's SWEEP record, threaded explicitly into the production
    payload processor.  ``None`` is the frozen constants the policy id
    names.  PK-CLEAN removed the environment hatches that used to carry
    these values, so a swept replay states its configuration at this one
    seam and nowhere else; the FULL-decode path (``run_receive``) has no
    such seam and therefore no sweep, which its entry point refuses
    loudly rather than ignoring.

    ``seed_archived_certificates`` is THE KILL TEST and only that
    (COLOR-UPLIFT-PLAN §4, and limit 3 above).  An ordinary replay
    accumulates its own certificates in barrier order, so a stage that
    conditions on certified content sees at lane 0 exactly what a fresh
    decode would: nothing.  Seeding hands every lane the archived FINAL
    frontier as PRIORS instead — maximal conditioning, unreachable in
    deployment — so the run answers one question: with all the certified
    sibling knowledge this capture will ever have, does the conditioned
    stage gain anything at all?  A null answer kills a packet; a positive
    one measures nothing, and the run JSON must say so.

    The seeds are priors ONLY: they are never counted as minted, never
    enter ``certified_work``, and never join the returned certificate
    list — so a seeded run's certificate set stays directly comparable to
    an unseeded one's, and its suppression behaviour is the one the
    archived frontier implies.

    ``sink`` is an optional production :class:`holo.receive.observer.
    EventSink` (``--diag``): when present the replay emits the same
    scaffolding the runtime emits for the work it ACTUALLY does — level
    open, lane open, the payload stage open/complete pair — and the
    payload stage's own events flow through untouched.  Stages the replay
    does not run (survey, address search) emit nothing; a pane with no
    events shows nothing.
    """
    from holo.receive.evidence_context import EvidenceContext
    from holo.receive.evidence_blocks import merge_block_sets
    from holo.receive.production_color import ProductionColorPayload
    from holo.receive.runtime_model import LaneContext
    from holo.receive.types import Detail, EventAuthority, Stage

    facts = _capture_facts(cache)
    rasters = LaneRasterFactory(native, spec, facts)
    processor = ProductionColorPayload(stack_config=stack_config)
    recorder = EventRecorder(sink)
    stream_ids = tuple(spec.stream_ids)
    plan, levels = replay_plan(cache, spec)
    levels_total = len(plan)

    def emit(name: str, stage, **kwargs) -> None:
        if sink is not None:
            sink.emit(name, stage, capture_id=cache.capture_sha256, **kwargs)

    certificates: list = []
    seeded: tuple = ()
    if seed_archived_certificates:
        seeded = tuple(
            cache.certificates_by_id[key]
            for key in sorted(cache.certificates_by_id))
    certified_work: set[tuple[int, int, int, str]] = set()
    live_blocks: dict[tuple, object] = {}
    outcomes: list[LaneReplay] = []
    # Two true scaffolding facts so an attached viewer can name what it is
    # showing: one capture is requested, and its archived committed work
    # is retained.  No durable session is created and none is claimed.
    emit("session.open", Stage.SCHEDULE,
         details=(Detail("captures.requested", 1),
                  Detail("captures.retained", 1)))
    emit("capture.open", Stage.INGEST,
         details=(Detail("source.sha256", cache.capture_sha256),
                  Detail("source.dpi", cache.capture_dpi)))
    try:
        for ordinal, level in enumerate(levels):
            lane = plan[ordinal]
            if level.payload_id is None:
                continue
            if lane_filter is not None and not lane_filter(lane):
                continue
            if progress is not None:
                progress(f"lane {lane.lane_id} "
                         f"(prior certs {len(certificates)})")
            # The kill test's whole mechanism, in one line: the lane's
            # PRIORS gain the archived final frontier; nothing else about
            # the replay changes, and `certificates` still holds only
            # what this run minted.
            prior = tuple({
                row.certificate_id: row
                for row in (*seeded, *certificates)}.values())
            evidence_lane = lane.evidence_lane_id
            own_committed = tuple(
                row for key, row in sorted(live_blocks.items())
                if key[1] == evidence_lane and key[0] == cache.capture_sha256)
            prior_capture = tuple(
                row for key, row in sorted(live_blocks.items())
                if key[1] == evidence_lane and key[0] != cache.capture_sha256)
            level_details = (
                Detail("lane.id", lane.lane_id),
                Detail("lane.parent_id", lane.parent_lane_id),
                Detail("lane.kind", _lane_kind(lane)),
                Detail("lane.arm_override", lane.arm_override),
                Detail("level.ordinal", ordinal),
                Detail("level.total", levels_total),
                Detail("level.ppc.num", lane.target_ppc_num),
                Detail("level.ppc.den", lane.target_ppc_den),
                Detail("lane.native_per_view.num", lane.native_per_view_num),
                Detail("lane.native_per_view.den", lane.native_per_view_den),
            )
            emit("level.open", Stage.SCHEDULE, details=level_details)
            raster = rasters.for_lane(lane)
            wall = time.perf_counter()
            cpu = time.process_time()
            address_cpu = time.process_time()
            survey, address, labels = build_address(
                cache, spec, lane, level, raster, prior)
            address_cpu = time.process_time() - address_cpu
            transient = address.transient
            placements = (
                len(getattr(transient, "payload_placements", ()) or ())
                if not hasattr(transient, "base_lane_id")
                else len(transient.poses))
            evidence = EvidenceContext(
                certificates=prior,
                prior_capture_blocks=prior_capture,
                regions=tuple(cache.regions_by_lane.get(
                    lane.base_lane_id, ())),
                label_poses=(),
                own_committed_blocks=own_committed,
            )
            emit("lane.open", Stage.SCHEDULE,
                 details=level_details + (
                     Detail("lane.effective_dpi", float(raster.dpi)),),
                 snapshot_factory=lambda lane=lane, raster=raster,
                 evidence=evidence: _lane_snapshot(
                     raster, facts, lane, evidence))
            emit("stage.open", Stage.PAYLOAD,
                 details=(Detail("lane.id", lane.lane_id),))
            context = LaneContext(
                Stage.PAYLOAD, lane, spec, raster, facts, evidence,
                recorder.observer_enabled, recorder.snapshots_enabled,
                recorder.emit,
                recorder.isolate(Stage.PAYLOAD, cache.capture_sha256),
                defer_fountain_close)
            output = processor.process(context, survey, address)
            product = output.product
            wall = time.perf_counter() - wall
            cpu = time.process_time() - cpu
            emit("stage.complete", Stage.PAYLOAD,
                 details=(Detail("lane.id", lane.lane_id),
                          Detail("timing.processor_seconds", wall)))
            minted = tuple(product.certificates)
            certificates.extend(minted)
            certified_work.update(row.work_key for row in minted)
            for block in product.blocks:
                live_blocks[block.key] = block
            live_blocks = {
                key: block for key, block in live_blocks.items()
                if not all((*block.address, stream) in certified_work
                           for stream in stream_ids)}
            details = {name: row for name, row in recorder.take()}
            outcomes.append(LaneReplay(
                ordinal=ordinal,
                lane_id=lane.lane_id,
                lane_kind=_lane_kind(lane),
                evidence_lane_id=evidence_lane,
                placements=placements,
                label_placements=labels,
                prior_certificates=len(prior),
                blocks=len(product.blocks),
                attempts=len(product.attempts),
                certificates=minted,
                details=details,
                wall_s=wall,
                cpu_s=cpu,
                build_address_s=address_cpu,
                attempt_rows=(tuple(product.attempts) if record_attempts
                              else ()),
            ))
            emit("level.complete", Stage.SCHEDULE,
                 details=(Detail("lane.id", lane.lane_id),
                          Detail("level.ordinal", ordinal)),
                 authority=EventAuthority.TRANSIENT)
        # Frontier consistency guard: merge_block_sets refuses duplicate
        # keys, so a broken retention mirror surfaces here, not silently.
        merge_block_sets(tuple(live_blocks.values()))
    finally:
        rasters.release()
    return outcomes, certificates


__all__ = [
    "EventRecorder", "LaneRasterFactory", "LaneReplay", "build_address",
    "replay_lanes", "replay_plan",
]
