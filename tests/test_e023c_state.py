"""Persistent-state and integrity contracts for the clean E023c cascade."""
from __future__ import annotations

import copy
import hashlib
import pickle
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023c-scale-space-receiver"
sys.path.insert(0, str(EXP))

import cascade_state as state  # noqa: E402
from paperholo import pilotsearch  # noqa: E402


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _envelope(*, manifest: bool = False) -> state.CascadeEnvelope:
    return state.CascadeEnvelope(
        algorithm_id=state.ALGORITHM_ID,
        format_id="e018b-v3-c2",
        seed=b"paper-store/e023c-state-test",
        cell_dots=2,
        page_cells_yx=(2220, 1500),
        pages=(0,),
        native_dpi=1200.0,
        rate_id="r0700",
        detector_profile="ctx-pava-v1",
        search_config_sha256=_sha("search-config"),
        scale_plan=(
            state.ScaleSpec(
                "ppc-2", 0, 2.0, 600.0,
                ((2, 1), (2, 1)), "area-rational-v1"),
            state.ScaleSpec(
                "ppc-4", 1, 4.0, 1200.0,
                ((1, 1), (1, 1)), "native-v1"),
        ),
        implementation_sha256=(("test:receiver", _sha("implementation")),),
        manifest_sha256=(_sha("manifest") if manifest else None),
    )


def _source(
    envelope: state.CascadeEnvelope,
    *,
    capture_id: str = "capture-0",
    content: str = "source-0",
) -> state.SourceIdentity:
    sha = _sha(content)
    shape = (4000, 3000)
    size = 12_000_000
    dtype = "uint8"
    identity = state.source_identity(
        source_sha256=sha, source_size=size, image_shape=shape,
        image_dtype=dtype, native_dpi=envelope.native_dpi)
    return state.SourceIdentity(
        identity, capture_id, f"/input/{content}.tiff", sha, size, shape,
        dtype, envelope.native_dpi)


@dataclass
class _OpaqueLane:
    scans: list[object]
    numeric: np.ndarray
    timings: dict = field(metadata={"semantic": False})
    diagnostics: dict = field(metadata={"semantic": False})
    search_result: object | None = None


@dataclass(frozen=True)
class _SkipScan:
    capture_id: str
    decode_skip_tiles: tuple[tuple[int, int, int], ...]


def _pilot(
    envelope: state.CascadeEnvelope,
    level_id: str,
) -> state.PilotKnowledgeSummary:
    return state.PilotKnowledgeSummary(
        (state.PilotPageSummary(0, 100, 10, 15, 75, 0),),
        _sha(f"pilot/{level_id}"),
        (level_id,),
    )


def _commit_first_level(
    session: state.CascadeSession,
    *,
    completion: state.CompletionCheck | None = None,
) -> tuple[str, str]:
    """Install one real lane, attempt, certificate, and level barrier."""
    capture_id = session.captures[0].source.capture_id
    level_id = session.envelope.scale_plan[0].level_id
    lane_id = state.attach_lane_session(
        session, level_id=level_id, lane_kind="primary",
        lane_session=_OpaqueLane(
            scans=[capture_id], numeric=np.arange(8, dtype=np.float32),
            timings={"elapsed_s": 10.0}, diagnostics={"frame": 7}),
    )
    empty_dependencies = state.dependency_identity(())
    evidence = _sha("numeric-evidence")
    attempt_id = state.attempt_identity(
        (0, 3, 4), capture_id, level_id, lane_id, "baseline",
        "bp60-a08", evidence, empty_dependencies)
    bits = np.resize(np.array([0, 1, 1], np.uint8), 137)
    certificate_id, bits_sha, packed = state.certificate_identity(
        session.envelope.format_id, session.envelope.seed, (0, 3, 4),
        session.envelope.rate_id, bits)
    attempt = state.AttemptRecord(
        attempt_id=attempt_id, tile_key=(0, 3, 4), capture_id=capture_id,
        level_id=level_id, lane_id=lane_id, stage="baseline",
        source="level-primary", decoder_profile="bp60-a08",
        numeric_evidence_sha256=evidence,
        component_sha256=(("capture", _sha("component")),),
        dependency_set_id=empty_dependencies, state="certified",
        decoder_invoked=True, k_eff=100, n_nonshort=137,
        n_informative=137, coverage=1.0, n_iters=14,
        syndrome_ok=True, crc_ok=True, n_erased=0,
        certified_new=True, output_certificate_id=certificate_id,
        metrics={"ber_proxy": 0.01}, timings={"elapsed_s": 2.0})
    certificate = state.PayloadCertificate(
        certificate_id=certificate_id, tile_key=(0, 3, 4),
        rate_id=session.envelope.rate_id, n_user_bits=bits.size,
        packed_user_bits=packed, user_bits_sha256=bits_sha,
        origin_attempt_id=attempt_id, born_capture_id=capture_id,
        born_level_id=level_id, born_lane_id=lane_id,
        dependency_set_id=empty_dependencies,
        provenance={"scale": 2.0})
    session.attempts.append(attempt)
    session.attempt_ids.add(attempt_id)
    session.certificate_union[certificate.tile_key] = certificate

    pilot = _pilot(session.envelope, level_id)
    artifacts = {
        "survey": {"regions": 2},
        "pilot_result": {"placements": 449},
        "continuation": np.arange(6, dtype=np.float64).reshape(3, 2),
    }
    artifacts_sha = state.semantic_digest(artifacts)
    before = state.certificate_union_digest({})
    after = state.certificate_union_digest(session.certificate_union)
    opened = state.make_checkpoint(
        ordinal=0, stage="level_open",
        input_certificate_sha256=before,
        output_certificate_sha256=before,
        pilot_knowledge_sha256=pilot.knowledge_sha256,
        artifacts_sha256=artifacts_sha,
        statistics={"regions": 2}, timings={"elapsed_s": 1.0},
        diagnostics={"frame": 1})
    final = state.make_checkpoint(
        ordinal=1, stage="level_complete",
        input_certificate_sha256=before,
        output_certificate_sha256=after,
        pilot_knowledge_sha256=pilot.knowledge_sha256,
        artifacts_sha256=artifacts_sha,
        attempt_ids=(attempt_id,), new_certificate_ids=(certificate_id,),
        statistics={"certified": 1})
    checkpoints = [opened, final]
    if completion is not None:
        checkpoints.append(state.make_checkpoint(
            ordinal=2, stage="fountain_check",
            input_certificate_sha256=before,
            output_certificate_sha256=after,
            pilot_knowledge_sha256=pilot.knowledge_sha256,
            artifacts_sha256=artifacts_sha,
            attempt_ids=(attempt_id,),
            new_certificate_ids=(certificate_id,),
            statistics={"completion": completion.status}))
    previous = session.captures[0].levels[0]
    complete = replace(
        previous, status="complete", view_sha256=_sha("view-ppc-2"),
        view_shape=(2000, 1500), view_dtype="float32",
        input_certificate_sha256=before, output_certificate_sha256=after,
        checkpoints=tuple(checkpoints), pilot_knowledge=pilot,
        attempt_ids=(attempt_id,), new_certificate_ids=(certificate_id,),
        completion=completion, artifacts=artifacts,
        artifacts_sha256=artifacts_sha)
    capture = session.captures[0]
    session.captures[0] = replace(
        capture, status="in_progress",
        levels=(complete, capture.levels[1]))
    session.pilot_knowledge = pilot
    return attempt_id, certificate_id


def _pending_session(*, manifest: bool = False) -> state.CascadeSession:
    envelope = _envelope(manifest=manifest)
    return state.create_session(envelope, (_source(envelope),))


def test_clean_pending_state_roundtrip_and_old_pickles_refused(
    tmp_path: Path,
) -> None:
    session = _pending_session()
    state.validate_session(session)
    path = tmp_path / "cascade.pkl"
    state.save_session(path, session)
    loaded = state.load_session(path)

    assert state.authoritative_digest(loaded) == state.authoritative_digest(
        session)
    assert loaded.envelope.scale_plan[-1].scale_yx == (1, 1)
    assert loaded.captures[0].levels[0].status == "pending"

    old = tmp_path / "old.pkl"
    old.write_bytes(pickle.dumps({
        "magic": "e023b-session-v2", "version": 2, "session": session}))
    with pytest.raises(ValueError, match="not an E023c"):
        state.load_session(old)
    path.write_bytes(path.read_bytes() + b"trailing-corruption")
    with pytest.raises(ValueError, match="trailing bytes"):
        state.load_session(path)


def test_semantic_digest_excludes_explicit_observer_and_timing_fields(
    tmp_path: Path,
) -> None:
    session = _pending_session()
    _commit_first_level(session)
    state.validate_session(session)
    baseline = state.authoritative_digest(session)

    observer = copy.deepcopy(session)
    observer.timings["wall_s"] = 999.0
    observer.observer_state["last_frame"] = 123
    observer.captures[0].timings["elapsed_s"] = 8.0
    observer.captures[0].diagnostics["pane"] = "D"
    observer.captures[0].levels[0].timings["cpu_s"] = 7.0
    observer.captures[0].levels[0].diagnostics["frame"] = 99
    opaque = next(iter(observer.lane_sessions.values()))
    opaque.timings["elapsed_s"] = 800.0
    opaque.diagnostics["frame"] = 800
    assert state.authoritative_digest(observer) == baseline
    state.validate_session(observer)

    changed = copy.deepcopy(session)
    changed.captures[0].levels[0].artifacts["survey"]["regions"] = 3
    assert state.authoritative_digest(changed) != baseline
    with pytest.raises(ValueError, match="level artifacts digest"):
        state.validate_session(changed)

    path = tmp_path / "committed.pkl"
    state.save_session(path, session)
    assert state.load_session(path).certified_count == 1


def test_window_audit_is_authenticated_inside_opaque_lane(
    tmp_path: Path,
) -> None:
    session = _pending_session()
    search_result = pilotsearch.SearchResult(diagnostics={
        "window_audit": {
            0: [{
                "outcome": "unresolved",
                "window": [10, 20, 80, 80],
                "best_candidate": {"support": 83, "mismatch_gap": 0.12},
            }],
        },
    })
    lane_id = state.attach_lane_session(
        session, level_id="ppc-2", lane_kind="primary",
        lane_session=_OpaqueLane(
            scans=["capture-0"], numeric=np.arange(4, dtype=np.float32),
            timings={"elapsed_s": 1.0}, diagnostics={"frame": 2},
            search_result=search_result),
    )
    baseline = state.authoritative_digest(session)
    path = tmp_path / "window-audit.pkl"
    state.save_session(path, session)
    assert state.authoritative_digest(state.load_session(path)) == baseline

    changed = copy.deepcopy(session)
    changed_result = changed.lane_sessions[lane_id].search_result
    changed_result.diagnostics["window_audit"][0][0][
        "best_candidate"]["support"] = 84
    assert state.authoritative_digest(changed) != baseline
    with pytest.raises(ValueError, match="lane session digest"):
        state.validate_session(changed)

    # Preserve the stored lane and outer digests while changing precisely the
    # algorithm-consumed runner-up substrate.  Loading must authenticate the
    # opaque session before making the state available to the runner.
    payload = pickle.loads(path.read_bytes())
    tampered = payload["session"].lane_sessions[lane_id].search_result
    tampered.diagnostics["window_audit"][0][0][
        "best_candidate"]["mismatch_gap"] = 0.11
    path.write_bytes(pickle.dumps(payload, protocol=pickle.HIGHEST_PROTOCOL))
    with pytest.raises(ValueError, match="lane session digest"):
        state.load_session(path)


def test_shared_scale_lane_accumulates_independent_captures() -> None:
    envelope = _envelope()
    session = state.create_session(envelope, (
        _source(envelope, capture_id="cap-a", content="a"),
        _source(envelope, capture_id="cap-b", content="b"),
    ))
    lane = _OpaqueLane(
        scans=["cap-a"], numeric=np.array([1.0]), timings={}, diagnostics={})
    lane_id = state.attach_lane_session(
        session, level_id="ppc-2", lane_kind="primary",
        lane_session=lane)
    lane.scans.append("cap-b")
    with pytest.raises(ValueError, match="lane session digest"):
        state.validate_session(session)

    same_id = state.attach_lane_session(
        session, level_id="ppc-2", lane_kind="primary",
        lane_session=lane)
    assert same_id == lane_id
    assert len(session.decoder_lanes) == 1
    state.validate_session(session)

    other_scale = state.attach_lane_session(
        session, level_id="ppc-4", lane_kind="primary",
        lane_session=_OpaqueLane(
            scans=["cap-a", "cap-b"], numeric=np.array([2.0]),
            timings={}, diagnostics={}))
    assert other_scale != lane_id
    assert len(session.decoder_lanes) == 2
    state.validate_session(session)


def test_lane_decode_skip_marker_requires_strictly_earlier_certificate() -> None:
    session = _pending_session()
    _commit_first_level(session)
    certified_key = next(iter(session.certificate_union))

    state.attach_lane_session(
        session, level_id="ppc-4", lane_kind="primary",
        lane_session=_OpaqueLane(
            scans=[_SkipScan("capture-0", (certified_key,))],
            numeric=np.array([4.0]), timings={}, diagnostics={}))
    state.validate_session(session)

    same_barrier = copy.deepcopy(session)
    coarse_lane_id = state.lane_identity("ppc-2", "primary")
    coarse_lane = same_barrier.lane_sessions[coarse_lane_id]
    coarse_lane.scans = [_SkipScan("capture-0", (certified_key,))]
    state.attach_lane_session(
        same_barrier, level_id="ppc-2", lane_kind="primary",
        lane_session=coarse_lane)
    with pytest.raises(ValueError, match="strictly-earlier"):
        state.validate_session(same_barrier)

    uncertified = copy.deepcopy(session)
    fine_lane_id = state.lane_identity("ppc-4", "primary")
    fine_lane = uncertified.lane_sessions[fine_lane_id]
    fine_lane.scans = [_SkipScan("capture-0", ((0, 9, 9),))]
    state.attach_lane_session(
        uncertified, level_id="ppc-4", lane_kind="primary",
        lane_session=fine_lane)
    with pytest.raises(ValueError, match="strictly-earlier"):
        state.validate_session(uncertified)


def test_attempt_certificate_and_dependency_tampering_fail_closed() -> None:
    session = _pending_session()
    attempt_id, certificate_id = _commit_first_level(session)
    state.validate_session(session)

    bad_bits = copy.deepcopy(session)
    certificate = next(iter(bad_bits.certificate_union.values()))
    bad_bits.certificate_union[certificate.tile_key] = replace(
        certificate,
        packed_user_bits=bytes([certificate.packed_user_bits[0] ^ 1])
        + certificate.packed_user_bits[1:])
    with pytest.raises(ValueError, match="certificate identity"):
        state.validate_session(bad_bits)

    bad_attempt = copy.deepcopy(session)
    bad_attempt.attempts[0] = replace(
        bad_attempt.attempts[0], numeric_evidence_sha256=_sha("changed"))
    with pytest.raises(ValueError, match="attempt identity"):
        state.validate_session(bad_attempt)

    self_dependent = copy.deepcopy(session)
    dependency_id = state.dependency_identity((certificate_id,))
    self_dependent.dependency_sets[dependency_id] = state.DependencySet(
        dependency_id, (certificate_id,), ((0, 3, 4),))
    original = self_dependent.attempts[0]
    new_attempt_id = state.attempt_identity(
        original.tile_key, original.capture_id, original.level_id,
        original.lane_id, original.stage, original.decoder_profile,
        original.numeric_evidence_sha256, dependency_id)
    self_dependent.attempts[0] = replace(
        original, attempt_id=new_attempt_id, dependency_set_id=dependency_id)
    self_dependent.attempt_ids = {new_attempt_id}
    cert = next(iter(self_dependent.certificate_union.values()))
    self_dependent.certificate_union[cert.tile_key] = replace(
        cert, origin_attempt_id=new_attempt_id,
        dependency_set_id=dependency_id)
    level = self_dependent.captures[0].levels[0]
    # Bring the denormalized ledgers and checkpoint identities along so the
    # dependency target check is the first remaining fault.
    final = replace(
        level.checkpoints[-1], checkpoint_id="",
        attempt_ids=(new_attempt_id,))
    final = replace(final, checkpoint_id=state.checkpoint_identity(final))
    level = replace(
        level, attempt_ids=(new_attempt_id,), checkpoints=(
            level.checkpoints[0], final))
    self_dependent.captures[0] = replace(
        self_dependent.captures[0], levels=(
            level, self_dependent.captures[0].levels[1]))
    with pytest.raises(ValueError, match="depends on its target tile"):
        state.validate_session(self_dependent)

    same_barrier = copy.deepcopy(session)
    dependency_id = state.intern_dependency_set(
        same_barrier, (certificate_id,))
    base = same_barrier.attempts[0]
    evidence = _sha("same-barrier-evidence")
    late_id = state.attempt_identity(
        (0, 9, 9), base.capture_id, base.level_id, base.lane_id,
        "feedback", base.decoder_profile, evidence, dependency_id)
    same_barrier.attempts.append(state.AttemptRecord(
        attempt_id=late_id, tile_key=(0, 9, 9),
        capture_id=base.capture_id, level_id=base.level_id,
        lane_id=base.lane_id, stage="feedback", source="known-cells",
        decoder_profile=base.decoder_profile,
        numeric_evidence_sha256=evidence, component_sha256=(),
        dependency_set_id=dependency_id, state="below_attempt_floor",
        decoder_invoked=False, k_eff=100, n_nonshort=137,
        n_informative=80, coverage=80 / 137, n_iters=0,
        syndrome_ok=None, crc_ok=None, n_erased=57,
        certified_new=False))
    same_barrier.attempt_ids.add(late_id)
    with pytest.raises(ValueError, match="earlier barrier"):
        state.validate_session(same_barrier)

    duplicate = copy.deepcopy(session)
    duplicate.attempts.append(duplicate.attempts[0])
    with pytest.raises(ValueError, match="attempt ledger contains duplicates"):
        state.validate_session(duplicate)


def test_verified_early_stop_requires_explicit_skipped_tail() -> None:
    session = _pending_session(manifest=True)
    output = None
    # The completion certificate digest is known after the fixture commits;
    # build the level once, then attach and re-identify its final checkpoint.
    _commit_first_level(session)
    output = state.certificate_union_digest(session.certificate_union)
    verified = state.CompletionCheck(
        status="volume_verified", certificate_union_sha256=output,
        manifest_sha256=session.envelope.manifest_sha256,
        block_rank=(("block-0", 737, 737),), shortfall=0,
        volume_sha256=_sha("volume"),
        expected_volume_sha256=_sha("volume"),
        details={"sha_pass": True})
    capture = session.captures[0]
    first = capture.levels[0]
    final = state.make_checkpoint(
        ordinal=2, stage="fountain_check",
        input_certificate_sha256=first.input_certificate_sha256,
        output_certificate_sha256=first.output_certificate_sha256,
        pilot_knowledge_sha256=first.pilot_knowledge.knowledge_sha256,
        artifacts_sha256=first.artifacts_sha256,
        attempt_ids=first.attempt_ids,
        new_certificate_ids=first.new_certificate_ids,
        statistics={"completion": "volume_verified"})
    first = replace(first, completion=verified,
                    checkpoints=first.checkpoints + (final,))
    skipped = replace(
        capture.levels[1], status="skipped_volume_verified",
        skip_reason="volume bytes and manifest SHA verified at ppc-2")
    session.captures[0] = replace(
        capture, status="early_stopped", levels=(first, skipped),
        first_verified_level_id="ppc-2")
    session.status = "early_stopped"
    session.first_verified_at = (capture.source.capture_id, "ppc-2")
    state.validate_session(session)

    implicit = copy.deepcopy(session)
    implicit.captures[0] = replace(
        implicit.captures[0], levels=(
            implicit.captures[0].levels[0],
            state.pending_level(implicit.envelope.scale_plan[1])))
    with pytest.raises(ValueError, match="marked skipped"):
        state.validate_session(implicit)

    wrong_sha = copy.deepcopy(session)
    level = wrong_sha.captures[0].levels[0]
    level = replace(
        level, completion=replace(
            level.completion, expected_volume_sha256=_sha("different")))
    wrong_sha.captures[0] = replace(
        wrong_sha.captures[0], levels=(
            level, wrong_sha.captures[0].levels[1]))
    with pytest.raises(ValueError, match="volume_verified lacks"):
        state.validate_session(wrong_sha)


def test_scale_source_checkpoint_and_pilot_invariants() -> None:
    envelope = _envelope()
    source = _source(envelope)
    session = state.create_session(envelope, (source,))

    non_native = replace(
        envelope,
        scale_plan=(envelope.scale_plan[0], replace(
            envelope.scale_plan[1], native_per_view_yx=((2, 1), (2, 1)),
            effective_dpi=600.0, target_ppc=2.0)))
    with pytest.raises(ValueError, match="increase strictly|final"):
        state.create_session(non_native, (_source(non_native),))

    wrong_source = replace(source, image_shape=(4001, 3000))
    with pytest.raises(ValueError, match="source identity"):
        state.create_session(envelope, (wrong_source,))

    bad_pilot = replace(
        session.pilot_knowledge,
        pages=(state.PilotPageSummary(0, 10, 2, 3, 4, 0),))
    session.pilot_knowledge = bad_pilot
    with pytest.raises(ValueError, match="does not partition"):
        state.validate_session(session)

    valid = _pending_session()
    _commit_first_level(valid)
    reordered = copy.deepcopy(valid)
    level = reordered.captures[0].levels[0]
    level = replace(
        level, checkpoints=tuple(reversed(level.checkpoints)))
    reordered.captures[0] = replace(
        reordered.captures[0], levels=(
            level, reordered.captures[0].levels[1]))
    with pytest.raises(ValueError, match="ordinals|stage order"):
        state.validate_session(reordered)


def test_atomic_save_failure_preserves_previous_state(
    tmp_path: Path, monkeypatch,
) -> None:
    original = _pending_session()
    path = tmp_path / "atomic.pkl"
    state.save_session(path, original)
    before = path.read_bytes()
    changed = copy.deepcopy(original)
    changed.observer_state["nonsemantic"] = True

    def fail_replace(_source, _target):
        raise OSError("injected replace failure")

    monkeypatch.setattr(state.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        state.save_session(path, changed)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".atomic.pkl.*.tmp"))
