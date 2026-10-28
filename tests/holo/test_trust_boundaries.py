"""Phase-7 trust-boundary guards (PAYLOAD-REWORK-PLAN 7.1d, lens-coverage:02).

Fast-pin ports of the orphaned 16-case ``qualify_runtime`` battery
(`_qualify_runtime_fixtures.py` — __main__-only since kiss e3026f1;
nothing ran it).  Each guard runs at the smallest scale that executes it,
on the synthetic runtime fixtures.  Already-ported siblings live in:
``test_receive_reauth_memo`` (source mutation, phase 3),
``test_receive_raster_pool`` (native/pooled raster lifetime),
``test_payload_nulls`` (persisted-state tamper + inline evidence), and
``test_receive_qualification`` (deferred-close family).
"""
from __future__ import annotations

import ast
import hashlib
import json
import textwrap
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from pyflakes.checker import Checker
from pyflakes.messages import UndefinedExport, UndefinedLocal, UndefinedName
import pytest

import _qualify_runtime_fixtures as fixtures
from holo.receive import tiles
from holo.receive.cascade import scale_plan
from holo.receive.diag import JsonlDiagnostics
from holo.receive.evidence_context import _select_lower_scale_evidence
from holo.receive.runtime import (
    LaneContext,
    ReceiveRequest,
    run_receive,
)
from holo.receive.scan import Raster, open_capture
from holo.receive.session import (
    CaptureConflictError,
    CaptureStatus,
    SessionIndex,
    SessionStatus,
    apply_close,
    authoritative_bytes,
    load_session,
    save_session,
    state_payload,
)
from holo.receive.session_validation import validate_attempt
from holo.receive.state_codec import encode_typed
from holo.receive.types import (
    AddressArtifact,
    AddressProduct,
    AttemptStage,
    AttemptState,
    CloseRecord,
    CloseStatus,
    Disposition,
    LosingHypothesis,
    PoseProposal,
    Stage,
    SurveyArtifact,
    SurveyProduct,
    TileAttemptRecord,
)


def _image(tmp_path: Path, seed: int, name: str = "capture.png") -> Path:
    path = tmp_path / name
    fixtures._write_image(path, seed)
    return path


# ---------------------------------------------------------------------------
# barrier restart: committed levels are skipped, evidence carries forward


def test_crash_between_barriers_resumes_exactly_after_committed_level(
    tmp_path,
) -> None:
    image = _image(tmp_path, 24_000)
    path = tmp_path / "restart.json"
    plan = scale_plan(1200, fixtures._spec().cell_dots)
    pipeline, calls = fixtures._pipeline(crash_lane=plan[1].lane_id)
    with pytest.raises(RuntimeError, match="between barriers"):
        run_receive(ReceiveRequest(
            fixtures._spec(), (fixtures._capture(image),), path,
            run_refine=True),
            pipeline=pipeline)
    state = load_session(path, format_row_id=fixtures._spec().spec_id)
    assert len(state.captures[0].levels) == 1
    first_calls = tuple(len(row) for row in calls)
    assert first_calls == (2, 2, 2)

    resumed_contexts: list[LaneContext] = []
    resumed, resume_calls = fixtures._pipeline(contexts=resumed_contexts)
    result = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(image),), path,
        run_refine=True),
        pipeline=resumed)
    assert result.captures[0].status is CaptureStatus.COMPLETE
    assert result.captures[0].barriers_committed == len(plan) - 1
    assert len(result.state.captures[0].levels) == len(plan)
    assert tuple(len(row) for row in resume_calls) == (
        len(plan) - 1, len(plan) - 1, len(plan) - 1)
    # The resumed second level sees the committed first level's evidence.
    assert {row.source_lane_id for row in
            resumed_contexts[0].evidence.proposals} == {plan[0].lane_id}
    assert {row.lane_id for row in
            resumed_contexts[0].evidence.losers} == {plan[0].lane_id}
    assert {(row.search_support, row.validation_support) for row in
            resumed_contexts[0].evidence.losers} == {(7, 3)}


# ---------------------------------------------------------------------------
# same-address lane frontier + attempt publication provenance


def test_same_address_lanes_retain_components_and_bind_provenance(
    tmp_path,
) -> None:
    images = (_image(tmp_path, 24_000, "a.png"), _image(tmp_path, 24_001, "b.png"))
    path = tmp_path / "same-address-lanes.json"
    pipeline, _ = fixtures._pipeline(same_tile_across_lanes=True)
    first = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(images[0]),), path,
        run_refine=True),
        pipeline=pipeline)
    plan = scale_plan(1200, fixtures._spec().cell_dots)
    ladder = tuple(row for row in plan
                   if row.mopup_of is None and row.refine_of is None)
    assert len(ladder) >= 2
    assert len(first.state.blocks) == len(ladder)
    first_sha = first.state.captures[0].source_sha256
    second = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(images[1]),), path,
        run_refine=True),
        pipeline=pipeline)
    assert len(second.state.blocks) == 2 * len(ladder)
    second_sha = second.state.captures[-1].source_sha256
    assert {row.address for row in second.state.blocks} == {(0, 0, 0)}
    counters = second.state.counters
    assert counters.scan.evaluations == 2 * len(ladder)
    assert counters.union.evaluations == len(ladder)
    by_lane_source: dict[str, set[str]] = {}
    for row in second.state.blocks:
        by_lane_source.setdefault(row.lane_id, set()).add(row.source_sha256)
    assert all(sources == {first_sha, second_sha}
               for sources in by_lane_source.values())
    assert load_session(path) == second.state

    # validate_attempt probes: unpublished component blocks and cross-lane
    # components must refuse.
    block_by_id = {row.block_id: row for row in second.state.blocks}
    some_block = second.state.blocks[0]

    def probe_attempt(component_ids):
        return TileAttemptRecord(
            attempt_id=tiles.attempt_identity(
                (0, 0, 0), AttemptStage.SCAN.value,
                tiles.decoder_profile(
                    fixtures._spec().rate_id, tiles.BASELINE_BP_MAX_ITERS,
                    tiles.BP_ALPHA),
                component_ids),
            source_sha256=some_block.source_sha256,
            lane_id=some_block.lane_id,
            page=0, tile_yx=(0, 0),
            stage=AttemptStage.SCAN,
            state=AttemptState.BELOW_ATTEMPT_FLOOR,
            n_informative=0, n_iters=0,
            syndrome_ok=None, crc_ok=None,
            component_block_ids=component_ids,
            dependency_certificate_ids=())

    with pytest.raises(ValueError, match="unavailable evidence block"):
        validate_attempt(probe_attempt(("e" * 64,)), block_by_id, {}, set())
    other_lane = next(row for row in second.state.blocks
                      if row.lane_id != some_block.lane_id)
    with pytest.raises(
            ValueError, match="outside its lane|live component"):
        validate_attempt(
            probe_attempt((other_lane.block_id,)), block_by_id, {}, set(),
            frontier_blocks=SessionIndex(second.state).block_frontier)


# ---------------------------------------------------------------------------
# nearest-productive lower-scale evidence selection (no lane mixing)


def test_lower_scale_evidence_selection_never_mixes_lanes() -> None:
    affine = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)
    source_sha256 = hashlib.sha256(b"capture").hexdigest()
    other_sha256 = hashlib.sha256(b"other").hexdigest()

    def accepted(identity: str, lane: str,
                 capture: str = source_sha256) -> PoseProposal:
        return PoseProposal(
            identity, capture, lane, 0, 0, (0, 0), (10, 10),
            (0.0, 0.0), affine)

    def runner(identity: str, lane: str,
               capture: str = source_sha256) -> LosingHypothesis:
        return LosingHypothesis(
            identity, capture, lane, "region", 0, (0, 0), 0,
            (0, 0), (10, 10), (0.0, 0.0), affine,
            0.2, 0.3, 20, 10)

    old = accepted("old", "coarse")
    near = accepted("near", "near")
    middle_runner = runner("middle-runner", "middle")
    foreign = accepted("foreign", "near", other_sha256)
    blank = _select_lower_scale_evidence(
        (old, foreign), (), capture_id=source_sha256,
        prior_lane_ids=("coarse", "blank"))
    shadow = _select_lower_scale_evidence(
        (old, near), (), capture_id=source_sha256,
        prior_lane_ids=("coarse", "blank", "near"))
    runner_only = _select_lower_scale_evidence(
        (old,), (middle_runner,), capture_id=source_sha256,
        prior_lane_ids=("coarse", "middle", "blank"))
    same_lane = _select_lower_scale_evidence(
        (old, near), (runner("near-runner", "near"),),
        capture_id=source_sha256,
        prior_lane_ids=("coarse", "near"))
    assert tuple(row.proposal_id for row in blank[0]) == ("old",)
    assert tuple(row.proposal_id for row in shadow[0]) == ("near",)
    assert not runner_only[0]
    assert tuple(row.hypothesis_id for row in runner_only[1]) == (
        "middle-runner",)
    assert tuple(row.proposal_id for row in same_lane[0]) == ("near",)
    assert tuple(row.hypothesis_id for row in same_lane[1]) == (
        "near-runner",)


# ---------------------------------------------------------------------------
# duplicate capture: exact no-op; conflicting metadata: refusal


def test_duplicate_capture_is_exact_noop_and_metadata_conflict_refuses(
    tmp_path,
) -> None:
    image = _image(tmp_path, 24_000)
    path = tmp_path / "duplicate.json"
    pipeline, _ = fixtures._pipeline()
    first = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(image),), path),
        pipeline=pipeline)
    before = path.read_bytes()
    duplicate = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(image),), path),
        pipeline=pipeline)
    assert path.read_bytes() == before
    assert duplicate.captures[0].barriers_committed == 0
    assert not duplicate.state_changed
    assert (duplicate.captures[0].source_sha256
            == first.state.captures[0].source_sha256)
    with pytest.raises(CaptureConflictError):
        run_receive(ReceiveRequest(
            fixtures._spec(), (fixtures._capture(image, dpi=400),), path),
            pipeline=pipeline)
    assert authoritative_bytes(first.state) == authoritative_bytes(
        duplicate.state)


# ---------------------------------------------------------------------------
# interpretation envelope: policy, page domains, and page-bearing records
# are bound and fail closed


def test_interpretation_envelope_fails_closed(tmp_path) -> None:
    image = _image(tmp_path, 24_000)
    path = tmp_path / "interpretation.json"
    pipeline, _ = fixtures._pipeline(page_hypotheses=(0,))
    initial = ReceiveRequest(
        fixtures._spec(), (fixtures._capture(image),), path,
        page_hypotheses=(0,),
    )
    run_receive(initial, pipeline=pipeline)
    before = path.read_bytes()

    # Since the policy-detach ruling (v0.59, §9c) a policy change is
    # classified per SEGMENT: the payload/address/scheduler/close
    # components detach and continue (pinned in
    # test_receive_policy_detach.py), and the SURVEY component — whose
    # region ledger every retained level artifact names — is the one that
    # still fails closed here, together with any unreadable id.
    wrong_policy = replace(
        pipeline,
        lanes=replace(
            pipeline.lanes,
            survey=replace(
                pipeline.lanes.survey,
                policy_id="qualification/runtime-survey/other",
            ),
        ),
    )
    with pytest.raises(ValueError, match="different survey policy"):
        run_receive(initial, pipeline=wrong_policy)
    assert path.read_bytes() == before

    wrong_pages = replace(initial, page_hypotheses=(1,))
    with pytest.raises(
            ValueError, match="pipeline has a different page domain"):
        run_receive(wrong_pages, pipeline=pipeline)

    matching_wrong_pipeline, _ = fixtures._pipeline(page_hypotheses=(1,))
    with pytest.raises(
            ValueError, match="state belongs to a different page domain"):
        run_receive(wrong_pages, pipeline=matching_wrong_pipeline)

    invalid_path = tmp_path / "out-of-domain-delta.json"
    invalid_pipeline, _ = fixtures._pipeline(
        page_hypotheses=(0,), address_page=1)
    with pytest.raises(ValueError, match="outside the receive domain"):
        run_receive(
            replace(initial, state_path=invalid_path),
            pipeline=invalid_pipeline)
    assert not invalid_path.exists()

    retained_path = tmp_path / "out-of-domain-retained.json"
    retained = load_session(path)
    mutated = replace(
        retained,
        poses=(replace(retained.poses[0], page=1),) + retained.poses[1:],
    )
    save_session(retained_path, mutated, validate=False)
    retained_before = retained_path.read_bytes()
    # v0.33 structural load validation refuses the retained record before
    # any lane could consume it; the fail-closed intent is unchanged.
    with pytest.raises(ValueError, match="outside the receive"):
        run_receive(
            replace(initial, state_path=retained_path), pipeline=pipeline)
    assert retained_path.read_bytes() == retained_before

    from holo.receive.placement.defaults import (
        PROVISIONAL_V1_PLACEMENT_POLICY,
    )
    from holo.receive.production import production_pipeline
    candidate = production_pipeline(initial)
    changed_policy = replace(
        PROVISIONAL_V1_PLACEMENT_POLICY, support_margin_sites=99)
    changed = replace(
        candidate,
        lanes=replace(
            candidate.lanes,
            address=replace(
                candidate.lanes.address,
                budget_policy=changed_policy,
            ),
        ),
    )
    # Policy identity is a hand-bumped readable string (kiss G2 ruling),
    # never a constant fingerprint: numeric budget edits alone do not fork
    # the id — the wrong_policy probe above is what refuses a mismatch.
    assert changed.policy_id == candidate.policy_id
    assert "v6-phased-schedule" in candidate.policy_id
    assert path.read_bytes() == before


# ---------------------------------------------------------------------------
# evidence semantics: acquisitions remain components; SCAN-first doctrine


def test_acquisitions_remain_components_and_doctrine_probes_refuse(
    tmp_path,
) -> None:
    images = tuple(
        _image(tmp_path, 24_000 + index, f"capture-{index}.png")
        for index in range(3))
    path = tmp_path / "evidence.json"
    contexts: list[LaneContext] = []
    pipeline, _ = fixtures._pipeline(contexts=contexts)
    for image in images:
        run_receive(ReceiveRequest(
            fixtures._spec(), (fixtures._capture(image),), path,
            run_refine=True),
            pipeline=pipeline)
    plan = scale_plan(1200, fixtures._spec().cell_dots)
    lanes = len(plan)
    n_ladder = sum(1 for row in plan
                   if row.mopup_of is None and row.refine_of is None)
    second = contexts[lanes:2 * lanes]
    third = contexts[2 * lanes:3 * lanes]
    first_sha = contexts[0].capture.source_sha256
    second_sha = second[0].capture.source_sha256
    third_sha = third[0].capture.source_sha256
    second_ladder = tuple(
        row for row in second
        if row.lane.mopup_of is None and row.lane.refine_of is None)
    third_ladder = tuple(
        row for row in third
        if row.lane.mopup_of is None and row.lane.refine_of is None)
    assert len(second_ladder) == len(third_ladder) == n_ladder
    assert all(row.evidence.prior_capture_blocks for row in second_ladder)
    assert all({block.source_sha256 for block in
                row.evidence.prior_capture_blocks}
               == {first_sha} for row in second_ladder)
    assert all({block.source_sha256 for block in
                row.evidence.prior_capture_blocks}
               == {first_sha, second_sha} for row in third_ladder)
    state = load_session(path)
    assert state.counters.scan.evaluations == 3 * n_ladder
    assert state.counters.union.evaluations == 2 * n_ladder
    block_by_id = {row.block_id: row for row in state.blocks}
    one_lane = state.blocks[0].lane_id
    lane_blocks = tuple(sorted(
        (row for row in state.blocks
         if row.lane_id == one_lane and row.address == (0, 0, 0)),
        key=lambda row: row.source_sha256))
    assert {row.source_sha256 for row in lane_blocks} == {
        first_sha, second_sha, third_sha}

    from holo.receive.evidence_blocks import tile_attempt_view
    union_view = tile_attempt_view(lane_blocks)
    union_informative = int(np.count_nonzero(union_view.llr_cells_f64))

    def probe(stage, component_ids, n_informative):
        return TileAttemptRecord(
            attempt_id=tiles.attempt_identity(
                (0, 0, 0), stage.value,
                tiles.decoder_profile(
                    fixtures._spec().rate_id, tiles.BASELINE_BP_MAX_ITERS,
                    tiles.BP_ALPHA),
                component_ids),
            source_sha256=third_sha,
            lane_id=one_lane,
            page=0, tile_yx=(0, 0),
            stage=stage,
            state=AttemptState.ATTEMPTED_FAILED,
            n_informative=n_informative, n_iters=1,
            syndrome_ok=False, crc_ok=False,
            component_block_ids=component_ids,
            dependency_certificate_ids=(
                union_view.dependency_certificate_ids))

    # A union without its preceding current-acquisition scan refuses (the
    # SCAN-current-acquisition direction).
    union_probe = probe(
        AttemptStage.UNION, union_view.component_block_ids,
        union_informative)
    with pytest.raises(
            ValueError, match="no preceding current-acquisition scan"):
        validate_attempt(union_probe, block_by_id, {}, set())

    partial_ids = (
        union_view.component_block_ids[0], "d" * 64,
        union_view.component_block_ids[2])
    partial_probe = probe(
        AttemptStage.UNION, partial_ids, union_informative)
    with pytest.raises(ValueError, match="only part"):
        validate_attempt(
            partial_probe, block_by_id, {}, set(),
            require_components=False)


# ---------------------------------------------------------------------------
# terminal close statuses persist; terminal state refuses reopening


@pytest.mark.parametrize("failure", (False, True))
def test_terminal_close_status_persists(tmp_path, failure) -> None:
    image = _image(tmp_path, 24_000)
    pipeline, _ = fixtures._pipeline()
    pipeline = replace(pipeline, close=fixtures._TerminalClose(failure))
    path = tmp_path / f"close-{failure}.json"
    result = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(image),), path),
        pipeline=pipeline)
    expected = (SessionStatus.INTEGRITY_FAILURE if failure
                else SessionStatus.VERIFIED)
    assert result.state.status is expected
    if not failure:
        assert result.payload == b"payload"
        resumed = run_receive(ReceiveRequest(
            fixtures._spec(), (fixtures._capture(image),), path),
            pipeline=pipeline)
        assert resumed.payload == b"payload" and not resumed.state_changed
    assert load_session(path).status is expected


def test_unsupported_close_persists_and_terminal_refuses_reopen(
    tmp_path,
) -> None:
    image = _image(tmp_path, 24_000)
    pipeline, _ = fixtures._pipeline()

    class Unsupported:
        policy_id = "qualification/runtime-unsupported-close/v1"

        def process(self, context):
            from holo.receive.runtime import CloseExecution
            return CloseExecution(CloseRecord(
                CloseStatus.UNSUPPORTED,
                context.certificate_frontier_sha256,
                metadata_version=1,
                reason="unsupported metadata version 1"))

    pipeline = replace(pipeline, close=Unsupported())
    path = tmp_path / "close-unsupported.json"
    result = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(image),), path),
        pipeline=pipeline)
    assert result.state.status is SessionStatus.UNSUPPORTED
    retained = load_session(path)
    assert retained.close.metadata_version == 1
    with pytest.raises(ValueError):
        apply_close(retained, CloseRecord())


# ---------------------------------------------------------------------------
# observer isolation: off/on/failing observers never change authority


def test_observers_never_change_authoritative_state(tmp_path) -> None:
    image = _image(tmp_path, 24_000)
    outputs = []
    failures = []
    for name, observer in (
        ("off", None),
        ("on", JsonlDiagnostics(tmp_path / "diag")),
        ("failing", lambda event: (_ for _ in ()).throw(
            OSError("observer failure"))),
    ):
        pipeline, _ = fixtures._pipeline()
        result = run_receive(ReceiveRequest(
            fixtures._spec(), (fixtures._capture(image),),
            tmp_path / f"diag-{name}.json"), pipeline=pipeline,
            observer=observer)
        outputs.append(authoritative_bytes(result.state))
        failures.append(result.observer_failures)
    assert outputs[0] == outputs[1] == outputs[2]
    assert not failures[0] and not failures[1] and failures[2]
    pipeline, _ = fixtures._pipeline()
    resumed = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(image),),
        tmp_path / "diag-on.json"), pipeline=pipeline,
        observer=JsonlDiagnostics(tmp_path / "diag"))
    assert authoritative_bytes(resumed.state) == outputs[1]
    assert not resumed.state_changed and not resumed.observer_failures
    rows = tuple(json.loads(line) for line in (
        tmp_path / "diag" / "events.jsonl"
    ).read_text(encoding="utf-8").splitlines())
    assert [row["sequence"] for row in rows] == list(range(len(rows)))
    assert all("event_id" not in row and "run_id" not in row for row in rows)


# ---------------------------------------------------------------------------
# identity and derived views


def test_canonical_source_sha_is_the_sole_acquisition_identity(
    tmp_path,
) -> None:
    image = _image(tmp_path, 24_000)
    pipeline, _ = fixtures._pipeline()
    result = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(image, dpi=400),),
        tmp_path / "long.json"), pipeline=pipeline)
    expected = open_capture(image, 400).source.sha256
    assert result.state.captures[0].source_sha256 == expected
    assert result.captures[0].source_sha256 == expected


def test_stage_view_derives_from_artifacts_and_is_not_persisted(
    tmp_path,
) -> None:
    image = _image(tmp_path, 24_000)
    pipeline, _ = fixtures._pipeline()
    result = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(image, dpi=400),),
        tmp_path / "minimal-stages.json"), pipeline=pipeline)
    level = result.state.captures[0].levels[0]
    assert level.stage_dispositions == (
        (Stage.SURVEY, Disposition.COMPLETE),
        (Stage.ADDRESS, Disposition.COMPLETE),
        (Stage.PAYLOAD, Disposition.COMPLETE),
    )
    durable = state_payload(result.state)["captures"][0]["levels"][0]
    assert "stages" not in durable


def test_native_lane_reuses_authenticated_raster_exactly(tmp_path) -> None:
    image = _image(tmp_path, 24_000)
    contexts: list[LaneContext] = []
    pipeline, _ = fixtures._pipeline(contexts=contexts)
    run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(image),),
        tmp_path / "native-no-copy.json", run_refine=True),
        pipeline=pipeline)
    plan = scale_plan(1200, fixtures._spec().cell_dots)
    assert len(contexts) == len(plan)
    assert isinstance(contexts[-1].raster, Raster)
    for context, lane in zip(contexts, plan, strict=True):
        native_view = lane.native_per_view_num == lane.native_per_view_den
        assert isinstance(context.raster, Raster) == native_view
    points = np.asarray(((0.0, 0.0), (3.25, 7.5)), np.float64)
    affine = np.asarray(((2.0, 0.1, 4.0), (-0.2, 1.5, 8.0)), np.float64)
    for context in contexts:
        assert np.allclose(context.lane_to_native_points(
            context.native_to_lane_points(points)), points)
        assert np.allclose(context.lane_to_native_affine(
            context.native_to_lane_affine(affine)), affine)
    native = open_capture(image, 1200)
    height, width = native.shape
    assert np.array_equal(
        contexts[-1].raster.crop_luma(0, height, 0, width),
        native.crop_luma(0, height, 0, width))


def test_transient_products_are_non_authoritative() -> None:
    survey_artifact = SurveyArtifact("survey-product-test", ())
    left = SurveyProduct(survey_artifact, (), transient=object())
    right = SurveyProduct(survey_artifact, (), transient=object())
    assert left == right and "transient" not in repr(left)
    assert "transient" not in encode_typed(left)
    address_artifact = AddressArtifact(
        "address-product-test", survey_artifact.survey_id, (), ())
    address = AddressProduct(
        address_artifact, (), (), transient=object())
    assert "transient" not in repr(address)
    assert "transient" not in encode_typed(address)


# ---------------------------------------------------------------------------
# acquisition retention: distinct captures stay durable pending components


def test_distinct_acquisitions_remain_durable_pending_components(
    tmp_path,
) -> None:
    images = (_image(tmp_path, 24_000, "a.png"),
              _image(tmp_path, 24_001, "b.png"))
    path = tmp_path / "acquisition-retention.json"
    pipeline, _ = fixtures._pipeline()
    first = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(images[0], dpi=400),), path,
        run_refine=True),
        pipeline=pipeline).state
    old_block = first.blocks[0].block_id
    assert first.counters.scan.evaluations == 1
    second = run_receive(ReceiveRequest(
        fixtures._spec(), (fixtures._capture(images[1], dpi=400),), path,
        run_refine=True),
        pipeline=pipeline).state
    assert len(second.blocks) == 2
    assert old_block in {row.block_id for row in second.blocks}
    assert second.counters.scan.evaluations == 2
    assert second.counters.union.evaluations == 1
    assert {row.source_sha256 for row in second.blocks} == {
        row.source_sha256 for row in second.captures}
    loaded = load_session(path)
    assert loaded.blocks == second.blocks
    assert loaded.counters == second.counters


# ---------------------------------------------------------------------------
# static invariants over the receive package sources


def test_static_source_invariants() -> None:
    import holo.receive as receive_package
    directory = Path(receive_package.__file__).resolve().parent
    sources = "\n".join(
        (directory / name).read_text(encoding="utf-8")
        for name in ("evidence.py", "types.py", "state_codec.py",
                     "session.py", "session_validation.py",
                     "evidence_blocks.py", "runtime.py", "cascade.py"))
    forbidden = (
        "NativeLaneScheduler", "RetainableProduct", "code_fingerprint",
        "MAX_STATE", "paperholo", "track2", "source_view",
        "holo-tile-certificate-v1",
    )
    assert all(value not in sources for value in forbidden)
    assert "block_frontier" in sources and "blob_items" in sources
    production_sources = tuple(
        path for path in directory.rglob("*.py")
        if "qualification" not in path.parts
        and "__pycache__" not in path.parts)
    oversized = {
        str(path.relative_to(directory))
        for path in production_sources
        if len(path.read_text(encoding="utf-8").splitlines()) >= 1000}
    # The battery only REPORTED this debt; the pin freezes the known set
    # (pre-phase-4 files outside the payload stage) so it cannot grow.
    assert oversized <= {
        "place.py", "placement/search.py"}, oversized


# ---------------------------------------------------------------------------
# fast static undefined-name guard (pyflakes-F821-class) over all of
# src/holo
#
# 2026-08-20 PLANE-FIELDS W2 (0700596) split color_region_details out of
# runtime.py into the new _production_diagnostics.py; the `channel` import
# its body needed stayed behind.  The module still imported cleanly --
# nothing calls color_region_details except the a4b full-tail arm -- so the
# suite stayed green and the NameError only fired live, mid an hours-long
# decode.  Fixed same-day in c79323f (one added import).  This guard is the
# fast (<2s) net for that whole bug class: an undefined name that only a
# rarely-exercised branch reaches.  Engine: pyflakes (installed,
# requirements.txt / pyproject dev extra) via its Checker on the parsed
# AST.
#
# 2026-08-22 widened (holo2 catch-up, RULINGS.md §D) from UndefinedName
# alone to (UndefinedName, UndefinedExport, UndefinedLocal): measured free
# in this tree (zero new findings) and UndefinedExport is exactly what
# turned up a real bug in holo2's carry of this gate (a stale __all__
# entry naming something never imported).  UnusedImport/RedefinedWhileUnused
# etc. stay out of scope -- they are wide enough to hit existing benign
# code (fixture-shadowing, leftover refactor imports) and are a different,
# weaker problem than "this code will crash if it ever runs".

_STATIC_NAME_CLASSES = (UndefinedName, UndefinedExport, UndefinedLocal)


def _undefined_names(source: str, filename: str) -> list[UndefinedName]:
    tree = ast.parse(source, filename=filename)
    checker = Checker(tree, filename=filename)
    return [message for message in checker.messages
            if isinstance(message, _STATIC_NAME_CLASSES)]


def _undefined_name_args(source: str) -> set[str]:
    return {message.message_args[0]
            for message in _undefined_names(textwrap.dedent(source), "<snippet>")}


def test_undefined_name_checker_semantics_on_inline_snippets() -> None:
    """Pin the pyflakes UndefinedName scoping this guard relies on."""
    # comprehension scopes: iterable + loop variable both resolve.
    assert _undefined_name_args("""
        data = [1, 2, 3]
        result = [x for x in data]
    """) == set()

    # class-body statements see module globals directly.
    assert _undefined_name_args("""
        MOD = 1
        class C:
            w = MOD
    """) == set()

    # ...but a *method* does NOT see the class body as an enclosing scope
    # (real Python scoping): a bare class-attribute reference from inside a
    # method is a genuine NameError and must be flagged.
    assert _undefined_name_args("""
        class C:
            z = 1
            def m(self):
                return z
    """) == {"z"}

    # nested functions resolve enclosing-function bindings (closures)
    # across more than one level.
    assert _undefined_name_args("""
        def outer():
            y = 1
            def inner():
                def innermost():
                    return y
                return innermost
            return inner
    """) == set()

    # TYPE_CHECKING-guarded imports are statically bound (symtable/pyflakes
    # see the import regardless of the runtime guard) and must not flag --
    # this is the exact idiom the two real-tree fixes below now use.
    assert _undefined_name_args("""
        from typing import TYPE_CHECKING
        if TYPE_CHECKING:
            import os
        def f() -> "os.PathLike":
            pass
    """) == set()

    # walrus assignments bind in the containing (function) scope.
    assert _undefined_name_args("""
        def f():
            if (n := 10) > 5:
                return n
    """) == set()

    # decorators are ordinary references to a module-level name.
    assert _undefined_name_args("""
        def deco(fn):
            return fn
        @deco
        def f():
            pass
    """) == set()

    # `del`: a documented pyflakes conservative spot, not a bug in this
    # checker -- don't overthink it, per the plan.  A name deleted anywhere
    # later in a scope reads as possibly-unbound for every reference in
    # that scope, including one that already executed earlier.
    assert _undefined_name_args("""
        def f():
            x = 1
            del x
            return x
    """) == {"x"}

    # The same mechanism reaches into a closure that runs to completion
    # BEFORE the `del` -- this is the exact shape of the one real-tree
    # finding this guard allowlists below (color_payload.py:359: `crops`
    # is read inside a lambda that _parallel.ordered_map calls and fully
    # consumes, wrapped in `tuple(...)`, three lines before `del crops`).
    assert _undefined_name_args("""
        def f(rows):
            crops = {1: 2}
            base = tuple(
                (lambda row: crops[row])(row) for row in rows)
            del crops
            return base
    """) == {"crops"}


def test_no_undefined_names_across_src_holo() -> None:
    """The fast static undefined-name guard, run for real.

    Self-test first (mandatory): a synthetic module reproducing the
    c79323f shape -- a function body reaching for ``channel.X`` with no
    ``channel`` binding anywhere -- must be flagged with exactly that
    name.  Then the real src/holo tree, which must come back clean modulo
    the one documented pyflakes false positive above.
    """
    landmine = textwrap.dedent("""
        from __future__ import annotations

        from .format.descriptor import FormatSpec

        def color_region_details(spec: FormatSpec) -> str:
            return channel.PLANE_ORDER[0]
    """)
    assert {message.message_args[0]
            for message in _undefined_names(landmine, "<landmine>")} == {"channel"}

    # (relative path, name) -- see the del-closure self-test above for why
    # this one is a pyflakes false positive, not a real bug.
    allowlist = {
        ("color_payload.py", "crops"),
    }

    import holo.receive as receive_package
    holo_root = Path(receive_package.__file__).resolve().parent.parent
    source_paths = tuple(
        path for path in sorted(holo_root.rglob("*.py"))
        if "__pycache__" not in path.parts)

    start = time.perf_counter()
    findings: list[str] = []
    for path in source_paths:
        source = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(holo_root))
        for message in _undefined_names(source, str(path)):
            name = message.message_args[0]
            if (path.name, name) in allowlist:
                continue
            findings.append(
                f"{relative}:{message.lineno} undefined name {name!r}")
    elapsed = time.perf_counter() - start
    print(f"undefined-name sweep: {len(source_paths)} files in "
          f"{elapsed:.3f}s")  # visible with pytest -s; not asserted (perf
                               # varies by machine -- the plan's <2s target
                               # is a report, not a pin).

    assert not findings, findings


def test_no_undefined_names_across_measure_instruments() -> None:
    """The same guard over ``measure/`` — the measurement instruments.

    User ruling 2026-08-21: measurement-instrument code lives in neither
    ``tests/`` nor ``scratch/``, so the plane-fields drivers moved to
    ``measure/plane_fields/`` (the ``holo2/measure`` precedent).  Nothing
    under ``measure/`` is pytest-collected — it is outside ``testpaths``
    and its entry points cost hours and multi-GB states — which is
    exactly the code the a4b landmine class hides in best: an undefined
    name on a branch nobody takes until the run is four hours old.  This
    sweep is the only automatic check those files get.

    Kept separate from the ``src/holo`` sweep above (its own root, its
    own allowlist) so a finding names which tree it came from.
    """
    measure_root = Path(__file__).resolve().parents[2] / "measure"
    if not measure_root.is_dir():                          # pragma: no cover
        pytest.skip("no measure/ tree in this checkout")
    source_paths = tuple(
        path for path in sorted(measure_root.rglob("*.py"))
        if "__pycache__" not in path.parts)
    assert source_paths, "measure/ has no sources — did the tree move?"

    findings = [
        f"{path.relative_to(measure_root)}:{message.lineno} undefined name "
        f"{message.message_args[0]!r}"
        for path in source_paths
        for message in _undefined_names(
            path.read_text(encoding="utf-8"), str(path))]
    assert not findings, findings
