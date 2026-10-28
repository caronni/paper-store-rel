"""Placement-scoped known-position BCH quarantine regressions."""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from holo.devices.profiles import make_spec
from holo.format import pilots
from holo.gen.compose import compose_page_cells
from holo.receive import certified_refine, payload, tiles
from holo.receive.cascade import scale_plan
from holo.receive.certified_cascade import refine_address_once
from holo.receive.discovery import DiscoveryReceiveRequest
from holo.receive.discovery_state import (
    DiscoverySurvey,
    load_discovery,
    save_discovery,
)
from holo.receive.evidence_blocks import (
    EvidenceBlock,
    EvidenceOrigin,
    _block_from_rows,
    blocks_from_frontier,
)
from holo.receive.observer import ReceiverQualificationStatus
from holo.receive._runtime_validation import validate_bch_conflicts_for_spec
from holo.receive.place import placement_hint
from holo.receive.placement.model import (
    AddressResult,
    AffinePose,
    CandidateScore,
    KnownWord,
    PilotObservation,
    PlacedPatch,
    PlacedSegment,
    PoseSegment,
    PoseWindow,
    promoted_continuation_hints,
)
from _e023c_fixtures import (
    _certificates_for_segment,
    _page_fixture,
    _segment_fixture,
)
from holo.receive.scan import open_capture
from holo.receive.session import (
    STATE_SCHEMA_VERSION,
    BarrierDelta,
    CaptureFacts,
    LevelRecord,
    SessionIndex,
    SessionState,
    append_level_barrier,
    load_session,
    save_session,
    validate_session,
)
from holo.receive.session_validation import (
    validate_address_quarantine,
    validate_attempt,
)
from holo.receive.types import (
    AddressArtifact,
    AttemptStage,
    AttemptState,
    BchConflictRecord,
    CaptureInput,
    LaneSpec,
    PayloadArtifact,
    PoseRecord,
    SupportRun,
    SurveyArtifact,
    SurveyRegionRecord,
    TileAttemptRecord,
)
from holo.receive.words import known_position_words


FORMAT_LANE = "l00-2ppc-400dpi"


def _grid(height: int = 64, width: int = 64) -> np.ndarray:
    yy, xx = np.meshgrid(
        np.arange(height), np.arange(width), indexing="ij")
    return np.stack((yy, xx), axis=-1).reshape(-1, 2).astype(np.int32)


def _candidate(page: int = 0, origin_yx: tuple[int, int] = (0, 0)
               ) -> CandidateScore:
    return CandidateScore(
        page, origin_yx, 0, 0.0, 0.0, 0, 0, 50, 50, 10.0, True,
        "qualification")


def _patch(patch_id: int, *, window_id: int | None = None) -> PlacedPatch:
    cells = _grid()
    pose = AffinePose(
        (1.5, 1.5), ((4.0, 0.0), (0.0, 4.0)), (0.5, 0.5),
        4.0, 0.0)
    window = PoseWindow(
        patch_id if window_id is None else window_id,
        0, (0, 0), (64, 64))
    segment = PoseSegment(window, pose, len(cells), 1.0, (4.0, 4.0), 0.0)
    placed = PlacedSegment(segment, (0, 0), 0, cells)
    return PlacedPatch(
        patch_id, 0, 0, "qualification", _candidate(), (),
        placed, (), False, cells)


def _conflict(*contributors: int) -> KnownWord:
    return KnownWord(
        0, (0, 0), 0, 1, 0, 0, tuple(contributors))


def test_selected_same_scan_observations_own_conflict_quarantine() -> None:
    spec = make_spec("c3-r0550")
    expected_counter = spec.tile_counter(0, 0, 0)
    decoded_counter = expected_counter + 1
    decoded = pilots.word_values(
        spec.seed, (decoded_counter,), spec.plane)[0]
    positions = pilots.word_site_cells_yx(spec.family_seed)
    observations: list[PilotObservation] = []
    for site, _point in enumerate(positions):
        observations.append(PilotObservation(
            0, (0, 0), site, int(decoded[site]), 2.0, "scan-a", 1))
        # This placement touches every site but never wins the same-scan vote.
        observations.append(PilotObservation(
            0, (0, 0), site, int(decoded[site]), 1.0, "scan-a", 2))
    # A stronger selected site makes patch 3 a real contributor.
    selected_site = 7
    observations.append(PilotObservation(
        0, (0, 0), selected_site, int(decoded[selected_site]),
        3.0, "scan-a", 3))
    # Equal strength is deliberately stable: the earlier patch-1 read wins.
    tie_site = 8
    observations.append(PilotObservation(
        0, (0, 0), tie_site, int(decoded[tie_site]),
        2.0, "scan-a", 4))

    word, = known_position_words(tuple(observations), spec)

    assert word.conflict
    assert word.decoded_counter == decoded_counter
    assert word.contributor_patch_ids == (1, 3)


def test_quarantine_is_exact_and_cannot_leak_a_continuation_hint() -> None:
    patches = (_patch(0), _patch(1))
    conflict = _conflict(0)
    hints = tuple(
        placement_hint(
            f"hint-{patch_id}", _candidate(), patches[0].segment.segment,
            (0, 0), kind=kind, patch_id=patch_id)
        for patch_id, kind in (
            (0, "accepted"), (1, "accepted"), (9, "runner_up")))

    retained = promoted_continuation_hints(hints, (conflict,))
    result = AddressResult(
        patches, (), (conflict,), ((0, "accepted"),), 1, retained)

    assert result.quarantined_patch_ids == (0,)
    assert tuple(row.patch_id for row in result.payload_placements) == (1,)
    assert tuple(row.patch_id for row in retained) == (1, 9)
    with pytest.raises(ValueError, match="continuation"):
        AddressResult(
            patches, (), (conflict,), ((0, "accepted"),), 1, hints)
    with pytest.raises(ValueError, match="unknown"):
        AddressResult(
            patches, (), (_conflict(7),), ((0, "accepted"),), 1)
    assert not replace(_conflict(0), decoded_counter=0).conflict
    with pytest.raises(ValueError, match="must coexist"):
        replace(_conflict(0), errors=None)
    foreign = PilotObservation(
        0, (0, 0), 0, 0, 1.0, "scan-a", 1)
    with pytest.raises(ValueError, match="another owner"):
        replace(patches[0], observations=(foreign,))
    with pytest.raises(ValueError, match="another owner"):
        replace(patches[0], observations=(replace(foreign, patch_id=None),))


def test_quarantine_withholds_llrs_while_clean_and_fresh_placements_work() -> None:
    spec = make_spec("c3-r0550")
    rng = np.random.default_rng(22025)
    symbols = rng.integers(
        0, 2, (spec.tiles_per_page, spec.symbol_bits), dtype=np.uint8)
    field = compose_page_cells(spec, 0, symbols, 1)
    tile = field[:64, :64]
    image = np.kron(
        np.where(tile != 0, np.float32(0), np.float32(255)),
        np.ones((4, 4), np.float32))
    raster = open_capture(image, 2400.0)
    source = payload.EvidenceSource(
        raster.source.sha256, "native")

    mixed = AddressResult(
        (_patch(0), _patch(1)), (), (_conflict(0),),
        ((0, "accepted"),), 1)
    evidence = payload.collect_capture_evidence(
        raster, source, mixed, spec, detector_profile=payload.PAVA_PROFILE)
    assert tuple(row.patch_id for row in evidence.windows) == (1,)
    assert evidence.pages
    assert {
        evidence.windows[int(index)].patch_id
        for page in evidence.pages for index in page.window_indices
    } == {1}

    quarantine_only = replace(mixed, placements=(mixed.placements[0],))
    withheld = payload.collect_capture_evidence(
        raster, source, quarantine_only, spec,
        detector_profile=payload.PAVA_PROFILE)
    withheld_blocks = blocks_from_frontier(withheld)
    staged = _run_k_schedule(spec, withheld_blocks, source)
    assert not withheld.windows
    assert not withheld.pages
    assert not staged.attempts
    assert not staged.certificates

    fresh = AddressResult(
        (_patch(2),), (), (), ((0, "accepted"),), 1)
    recovered = payload.collect_capture_evidence(
        raster, source, fresh, spec, detector_profile=payload.PAVA_PROFILE)
    recovered_blocks = blocks_from_frontier(recovered)
    staged = _run_k_schedule(spec, recovered_blocks, source)
    assert tuple(row.patch_id for row in recovered.windows) == (2,)
    assert len(staged.certificates) == 1
    assert (staged.certificates[0].page,
            *staged.certificates[0].tile_yx) == (0, 0, 0)



def _run_k_schedule(spec, blocks, source):
    """Family-unified K schedule: shared engine + the K leaf."""
    from holo.receive.payload_engine import run_attempts
    from holo.receive.records import CertificateStore

    store = CertificateStore(spec)

    class _Leaf:
        def __init__(self):
            self.attempts = []
            self.certificates = []
            self._seen = set()

        def unresolved_streams(self, address):
            return store.unresolved_streams(address)

        def attempt(self, view, _stream_id, stage):
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
            if certificate is not None:
                self.certificates.append(certificate)
            return record

    leaf = _Leaf()
    run_attempts(blocks, blocks, lane_id=source.lane_id, leaf=leaf)
    return leaf


def _durable_pose(
    patch_id: int = 0,
    *,
    placement_outcome: str = "accepted",
    page: int = 0,
    lane_id: str = "native",
) -> PoseRecord:
    return PoseRecord(
        "pose-0", "a" * 64, lane_id, "region-0",
        patch_id, placement_outcome, page, (0, 0),
        (4.0, 0.0, 1.5, 0.0, 4.0, 1.5), 0, 1.0,
        0, (0, 0), (64, 64), 0,
        (0.0, 0.0), (4.0, 0.0, 0.0, 4.0), (0.0, 0.0), 4.0, 0.0,
        100, 1.0, (4.0, 4.0), 0.0)


def _state_with_conflict() -> SessionState:
    spec = make_spec("c3-r0550")
    source_sha = "a" * 64
    plan = scale_plan(400.0, spec.cell_dots)
    lane = plan[0]
    region = SurveyRegionRecord(
        "region-0", source_sha, lane.lane_id, (0, 0), (256, 256),
        1, (1, 1), (SupportRun(0, 1),), 1.0, 1.0)
    survey = SurveyArtifact("survey-0", (region.region_id,))
    pose = _durable_pose(lane_id=lane.lane_id)
    conflict = BchConflictRecord(
        0, (0, 0), 1, 0, 0, (0,))
    address = AddressArtifact(
        "address-0", survey.survey_id, (pose.pose_id,),
        bch_conflicts=(conflict,))
    level = LevelRecord(survey, address)
    facts = CaptureFacts(
        source_sha, 400.0,
        "float32", (256, 256), 1)
    state = SessionState.create(
        spec.spec_id, "qualification/bch-quarantine-v1", (0,))
    return append_level_barrier(
        state, SessionIndex(state), facts, plan, level,
        BarrierDelta(regions=(region,), poses=(pose,)))


def _quarantined_block() -> EvidenceBlock:
    origin = EvidenceOrigin(
        f"{'a' * 64}/{FORMAT_LANE}/patch-0", 0, 0.1)
    return _block_from_rows(
        "a" * 64, FORMAT_LANE, 0, (0, 0),
        ((0, np.float32(1.0).tobytes(), origin),),
    )


def test_retry_parent_is_scoped_to_its_lane() -> None:
    source_sha256 = "a" * 64
    address = (0, 0, 0)

    def failed(
        lane_id: str,
        stage: AttemptStage,
        component_block_id: str,
    ) -> TileAttemptRecord:
        max_iters = (
            tiles.RETRY_BP_MAX_ITERS
            if stage is AttemptStage.RETRY150
            else tiles.BASELINE_BP_MAX_ITERS
        )
        profile = tiles.decoder_profile("r0550", max_iters, tiles.BP_ALPHA)
        return TileAttemptRecord(
            attempt_id=tiles.attempt_identity(
                address, stage.value, profile, (component_block_id,)),
            source_sha256=source_sha256,
            lane_id=lane_id,
            page=0,
            tile_yx=(0, 0),
            stage=stage,
            state=AttemptState.ATTEMPTED_FAILED,
            n_informative=1,
            n_iters=1,
            syndrome_ok=False,
            crc_ok=False,
            component_block_ids=(component_block_id,),
            dependency_certificate_ids=(),
        )

    lane_1 = failed("lane-1", AttemptStage.SCAN, "1" * 64)
    lane_2 = failed("lane-2", AttemptStage.SCAN, "2" * 64)
    retry_lane_1 = failed("lane-1", AttemptStage.RETRY150, "1" * 64)
    validate_attempt(
        retry_lane_1,
        {},
        {},
        set(),
        prior_attempts=(lane_1, lane_2),
        require_components=False,
    )


def test_replay_rejects_quarantine_and_blocks_cannot_mix_captures() -> None:
    state = _state_with_conflict()
    block = _quarantined_block()
    with pytest.raises(ValueError, match="quarantined placement"):
        SessionIndex(replace(state, blocks=(block,)))

    with pytest.raises(ValueError):
        _block_from_rows(
            "not-a-sha", "native", 0, (0, 0),
            ((0, np.float32(1.0).tobytes(),
              EvidenceOrigin(
                  f"{'a' * 64}/native/patch-0", 0, 0.1)),),
        )

    current_block = _block_from_rows(
        "b" * 64, "native", 0, (0, 0),
        ((0, np.float32(1.0).tobytes(),
          EvidenceOrigin(
              f"{'b' * 64}/native/patch-1", 1, 0.1)),),
    )
    source_sha = "b" * 64
    lane = LaneSpec("native", 4, 1, 1, 1)
    survey = SurveyArtifact("survey-1", ())
    address = AddressArtifact("address-1", survey.survey_id, (), ())
    payload_artifact = PayloadArtifact(
        "payload-1", address.address_id, (), n_blocks=1)
    level = LevelRecord(survey, address, payload_artifact)
    facts = CaptureFacts(
        source_sha, 2400.0,
        "float32", (256, 256), 1)
    updated = append_level_barrier(
        state, SessionIndex(state), facts, (lane,), level,
        BarrierDelta(blocks=(current_block,)))
    assert updated.blocks == (current_block,)


def test_conflict_audit_round_trips_and_reports_exact_quarantine(
    tmp_path,
) -> None:
    state = _state_with_conflict()
    path = tmp_path / "session.json"

    assert STATE_SCHEMA_VERSION == 26
    assert save_session(path, state)
    assert '"observed_sites"' not in path.read_text(encoding="utf-8")
    assert '"expected_counter"' not in path.read_text(encoding="utf-8")
    assert '"stages"' not in path.read_text(encoding="utf-8")
    loaded = load_session(path)
    assert loaded == state
    conflict, = loaded.captures[0].levels[0].address.bch_conflicts
    assert conflict == BchConflictRecord(
        0, (0, 0), 1, 0, 0, (0,))



def test_discovery_load_rejects_derived_bch_nonconflict(tmp_path) -> None:
    """A lean conflict record is rebound to its format on discovery load."""
    import holo.receive.discovery as discovery

    spec = make_spec("c3-r0550")
    state = _state_with_conflict()
    level = state.captures[0].levels[0]
    assert level.address is not None
    conflict, = level.address.bch_conflicts
    address = replace(
        level.address,
        bch_conflicts=(replace(conflict, decoded_counter=0),),
    )
    capture = replace(
        state.captures[0],
        levels=(replace(level, address=address),),
    )
    corrupted_branch = replace(
        state,
        captures=(capture,),
    )
    with pytest.raises(ValueError, match="matches the format"):
        validate_session(corrupted_branch)

    seed = CaptureInput(np.zeros((1, 1), np.uint8), 600.0)
    root, _pipelines = discovery._new_state(DiscoveryReceiveRequest(
        (seed,), candidate_row_ids=(spec.spec_id,)))
    corrupted = replace(
        root,
        branches=(corrupted_branch,),
        surveys=(DiscoverySurvey(CaptureFacts(
            "a" * 64, 400.0, "float32", (256, 256), 1), 3),),
    )
    path = tmp_path / "corrupt-discovery.json"
    save_discovery(path, corrupted, validate=False)

    with pytest.raises(ValueError, match="matches the format"):
        load_discovery(path)


def test_durable_quarantine_rejects_unbound_or_malformed_contributors() -> None:
    pose = _durable_pose()
    conflict = BchConflictRecord(
        0, (0, 0), 1, 0, 0, (7,))
    artifact = AddressArtifact(
        "address-0", "survey-0", (),
        bch_conflicts=(conflict,))
    with pytest.raises(ValueError, match="not an accepted placement"):
        validate_address_quarantine(artifact, (pose,))
    with pytest.raises(ValueError, match="not an accepted placement"):
        validate_address_quarantine(
            replace(
                artifact,
                bch_conflicts=(replace(conflict, contributor_patch_ids=(0,)),),
            ),
            (replace(pose, placement_outcome="redundant"),),
        )
    with pytest.raises(ValueError, match="another page"):
        validate_address_quarantine(
            replace(
                artifact,
                bch_conflicts=(replace(conflict, contributor_patch_ids=(0,)),),
            ),
            (replace(pose, page=1),),
        )
    with pytest.raises(ValueError, match="sorted and unique"):
        BchConflictRecord(
            0, (0, 0), 1, 0, 0, (1, 1))
    with pytest.raises(ValueError, match="decoder budget"):
        BchConflictRecord(
            0, (0, 0), 1, 13, 2, (0,))
    spec = make_spec("c3-r0550")
    with pytest.raises(ValueError, match="matches"):
        validate_bch_conflicts_for_spec(
            replace(
                artifact,
                bch_conflicts=(replace(conflict, decoded_counter=0),),
            ),
            (0,),
            spec,
        )
    validate_bch_conflicts_for_spec(
        replace(
            artifact,
            bch_conflicts=(replace(
                conflict, contributor_patch_ids=(0,),
                decoded_counter=spec.max_tiles_addressable - 1,
            ),),
        ),
        (0,),
        spec,
    )
    with pytest.raises(ValueError, match="decoded counter"):
        validate_bch_conflicts_for_spec(
            replace(
                artifact,
                bch_conflicts=(replace(
                    conflict, contributor_patch_ids=(0,),
                    decoded_counter=spec.max_tiles_addressable,
                ),),
            ),
            (0,),
            spec,
        )


def test_refinement_uses_promoted_subset_and_retains_quarantine() -> None:
    page = _page_fixture()
    quarantined_fixture = _segment_fixture(
        page, window_id=31, region_index=31,
        page_origin_yx=(0, 0), shift_yx_cells=(0.0, 0.0))
    clean_fixture = _segment_fixture(
        page, window_id=32, region_index=31,
        page_origin_yx=(128, 0), shift_yx_cells=(0.125, -0.125))

    def placed(fixture, patch_id: int) -> tuple[PlacedPatch, object]:
        segment = fixture.request.placed
        candidate = _candidate(0, segment.page_origin_yx)
        cells = (
            segment.audited_cells_yx.astype(np.int64)
            + np.asarray(segment.page_origin_yx, np.int64)
        ).astype(np.int32)
        patch = PlacedPatch(
            patch_id, 31, 0, "qualification", candidate, (), segment, (),
            False, cells)
        hint = placement_hint(
            f"hint-{patch_id}", candidate, segment.segment,
            segment.page_origin_yx, kind="accepted",
            patch_id=patch_id)
        return patch, hint

    quarantined_patch, _quarantined_hint = placed(quarantined_fixture, 31)
    clean_patch, clean_hint = placed(clean_fixture, 32)
    address = AddressResult(
        (quarantined_patch, clean_patch), (), (
            KnownWord(
                0, (0, 0), 0, 1, 0, 0, (31,)),
        ), ((31, "accepted"),), 2, (clean_hint,))
    generation0 = payload.collect_capture_evidence(
        page.raster, clean_fixture.request.generation0.source,
        address, page.spec, detector_profile=payload.PAVA_PROFILE)

    result = refine_address_once(
        page.raster, address, generation0, page.spec,
        _certificates_for_segment(page, (128, 0)))

    assert tuple(row.patch_id for row in generation0.windows) == (32,)
    assert {row.patch_id for row in result.summaries} == {32}
    assert result.address.placements[0] is quarantined_patch
    assert result.address.quarantined_patch_ids == (31,)
    assert tuple(row.patch_id for row in result.address.payload_placements) == (32,)
    assert all(row.patch_id != 31
               for row in result.address.continuation_hints)


def test_refinement_rejects_noncanonical_frozen_orientation() -> None:
    page = _page_fixture()
    fixture = _segment_fixture(
        page, window_id=41, region_index=41,
        page_origin_yx=(0, 0), shift_yx_cells=(0.0, 0.0))
    request = replace(
        fixture.request,
        placed=replace(fixture.request.placed, rot_k=4),
    )

    with pytest.raises(
            certified_refine.RefinementIntegrityError,
            match="invalid frozen orientation"):
        certified_refine._request_rows(request, page.spec)
