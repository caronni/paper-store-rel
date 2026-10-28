"""State, replay, and fail-closed integrity contracts for E024."""
from __future__ import annotations

import copy
import hashlib
import json
import pickle
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023b-integrated-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

from paperholo import compose, feedback, feedbackstate, payloaddec, receiver  # noqa: E402
import merge_e023b  # noqa: E402
import test_e023 as t23  # noqa: E402
import test_e023b_session as session_test  # noqa: E402


@pytest.fixture(scope="module")
def baseline_state(tmp_path_factory):
    """A real, partially recovered E023b state with known printed truth."""
    tmp_path = tmp_path_factory.mktemp("e024-state")
    descriptor, upstream, image, user, framed = session_test._fixture(
        tmp_path, partial=True)
    baseline = receiver.ReceiverSession.create(
        descriptor, (0,), 1600.0)
    baseline, _counts = receiver.apply_scan(
        baseline,
        session_test._record(
            descriptor, upstream.scans[0], image))
    path = tmp_path / "e023b.pkl"
    receiver.save_session(path, baseline)
    expected_cells = compose.compose_page(
        framed["payload_bits"], descriptor.spec(),
        descriptor.seed, page=0).cell_values
    per_tile_user = t23._per_tile_user(user, framed)
    return path, baseline, expected_cells, per_tile_user


def _control(path: Path, baseline: receiver.ReceiverSession):
    return feedback.create_session(
        path, baseline, profile=feedbackstate.PROFILE_CONTROL)


def _validate_without_artifact(
    session: feedbackstate.E024Session,
    baseline: receiver.ReceiverSession,
) -> None:
    feedbackstate.validate_session(
        session, baseline, check_baseline_artifact=False,
        validate_baseline=False)


def test_control_import_is_exact_generation_zero_and_true_noop(
        baseline_state) -> None:
    path, baseline, _expected, _per_tile = baseline_state
    session = _control(path, baseline)
    baseline_certificates = {
        key: outcome for key, outcome in baseline.decode.tiles.items()
        if outcome.state == "certified"
    }

    assert session.head.ordinal == 0
    assert session.head.parent_generation_id is None
    assert session.head.fixed_point
    assert session.head.active_revisions == ()
    assert session.head.statistics == {
        "imported_e023b_certificates": len(baseline_certificates),
        "external_seed_certificates": 0,
    }
    assert set(session.certificates) == set(baseline_certificates)
    assert all(
        row.source == "e023b-generation0"
        and row.born_generation == 0
        and row.origin_attempt_id
        for row in session.certificates.values())

    before = pickle.dumps(session, protocol=pickle.HIGHEST_PROTOCOL)
    result, report = feedback.run_feedback(
        session, baseline, baseline_path=path)
    assert result is session
    assert report["noop"]
    assert report["generations_run"] == 0
    assert pickle.dumps(
        result, protocol=pickle.HIGHEST_PROTOCOL) == before


def test_generation_zero_rejects_fatal_e023b_footing(
        baseline_state) -> None:
    path, baseline, _expected, _per_tile = baseline_state
    fatal = baseline.fork()
    fatal.decode.fatal.append("injected fatal integrity record")
    with pytest.raises(
            ValueError, match="baseline carries fatal integrity"):
        feedback.create_session(
            path, fatal, profile=feedbackstate.PROFILE_CONTROL)


def test_overlay_save_load_roundtrip_and_baseline_path_override(
        baseline_state, tmp_path: Path) -> None:
    baseline_path, baseline, _expected, _per_tile = baseline_state
    session = _control(baseline_path, baseline)
    state_path = tmp_path / "e024.pkl"
    feedbackstate.save_session(
        state_path, session, baseline, baseline_path=baseline_path)

    loaded, loaded_baseline = feedbackstate.load_session(state_path)
    assert feedbackstate.authoritative_digest(loaded) == (
        feedbackstate.authoritative_digest(session))
    assert receiver.authoritative_digest(loaded_baseline) == (
        receiver.authoritative_digest(baseline))

    relocated = tmp_path / "relocated-e023b.pkl"
    shutil.copyfile(baseline_path, relocated)
    moved, moved_baseline = feedbackstate.load_session(
        state_path, baseline_path=relocated)
    assert moved.baseline.path == str(baseline_path.resolve())
    assert feedbackstate.authoritative_digest(moved) == (
        feedbackstate.authoritative_digest(session))
    assert receiver.authoritative_digest(moved_baseline) == (
        receiver.authoritative_digest(baseline))

    # pickle.loads accepts trailing bytes, so this remains a readable E023b
    # payload while proving that E024 checks the complete artifact hash.
    relocated.write_bytes(relocated.read_bytes() + b"artifact-tamper")
    with pytest.raises(
            ValueError, match="generation-0 E023b artifact changed"):
        feedbackstate.load_session(
            state_path, baseline_path=relocated)


def test_certificate_export_reconstructs_exact_printed_cells(
        baseline_state) -> None:
    path, baseline, expected_cells, _per_tile = baseline_state
    session = _control(path, baseline)
    labels = feedback.export_certified_labels(session, baseline)
    known = labels.values[0] >= 0

    assert known.any()
    assert np.array_equal(
        labels.values[0][known].astype(np.uint8),
        expected_cells[known].astype(np.uint8))
    assert set(labels.certificate_ids) == set(session.certificates)
    assert all(
        row.ndim == 1 and row.size > 0
        for row in labels.payload_indices.values())

    one = next(iter(session.certificates.values()))
    selected = feedback.export_certified_labels(
        session, baseline, certificate_ids=(one.certificate_id,))
    assert set(selected.certificate_ids) == {one.tile_key}
    assert int((selected.values[0] >= 0).sum()) == (
        selected.payload_indices[one.tile_key].size)
    with pytest.raises(ValueError, match="unknown certificates"):
        feedback.export_certified_labels(
            session, baseline, certificate_ids=("0" * 64,))


def test_dependency_index_and_attempt_target_tamper_are_rejected(
        baseline_state) -> None:
    path, baseline, _expected, _per_tile = baseline_state
    session = _control(path, baseline)
    empty_id = feedbackstate.dependency_identity(())

    malformed = copy.deepcopy(session)
    malformed.dependency_sets[empty_id] = replace(
        malformed.dependency_sets[empty_id],
        tile_keys=((0, 0, 0),))
    with pytest.raises(ValueError, match="dependency tile index mismatch"):
        _validate_without_artifact(malformed, baseline)

    targeted = copy.deepcopy(session)
    target, certificate = next(iter(targeted.certificates.items()))
    dependency_id = feedbackstate.intern_dependency_set(
        targeted, (certificate.certificate_id,))
    numeric_sha256 = hashlib.sha256(b"tampered evidence").hexdigest()
    decoder_profile = "tampered-target-profile"
    attempt_id = feedbackstate.attempt_identity(
        target, decoder_profile, numeric_sha256)
    attempt = feedbackstate.FeedbackAttempt(
        attempt_id=attempt_id, generation=0, tile_key=target,
        stage="tampered", source="tampered",
        decoder_profile=decoder_profile,
        numeric_evidence_sha256=numeric_sha256,
        component_sha256=(), input_revision_ids=(),
        dependency_set_id=dependency_id,
        state="below_attempt_floor", decoder_invoked=False,
        k_eff=0, n_nonshort=0, n_informative=0, coverage=0.0,
        n_iters=0, syndrome_ok=None, crc_ok=None, n_erased=0,
        certified_new=False)
    targeted.attempts.append(attempt)
    targeted.attempt_ids.add(attempt_id)
    with pytest.raises(ValueError, match="depends on its target tile"):
        _validate_without_artifact(targeted, baseline)


def test_transitive_certificate_dependency_cycle_is_rejected(
        baseline_state) -> None:
    path, baseline, _expected, _per_tile = baseline_state
    session = _control(path, baseline)
    first, second = list(session.certificates)[:2]
    first_certificate = session.certificates[first]
    second_certificate = session.certificates[second]
    first_dep = feedbackstate.intern_dependency_set(
        session, (second_certificate.certificate_id,))
    second_dep = feedbackstate.intern_dependency_set(
        session, (first_certificate.certificate_id,))
    session.certificates[first] = replace(
        first_certificate, dependency_set_id=first_dep)
    session.certificates[second] = replace(
        second_certificate, dependency_set_id=second_dep)

    with pytest.raises(
            ValueError,
            match="cycle|generation-zero|dependency closure"):
        _validate_without_artifact(session, baseline)


def test_atomic_save_failure_preserves_previous_overlay(
        baseline_state, tmp_path: Path, monkeypatch) -> None:
    baseline_path, baseline, _expected, _per_tile = baseline_state
    original = _control(baseline_path, baseline)
    replacement = feedback.create_session(
        baseline_path, baseline, profile=feedbackstate.PROFILE_RECAL)
    state_path = tmp_path / "atomic.pkl"
    feedbackstate.save_session(
        state_path, original, baseline,
        baseline_path=baseline_path)
    before = state_path.read_bytes()

    def fail_replace(_source, _target):
        raise OSError("injected pre-commit failure")

    monkeypatch.setattr(feedbackstate.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected pre-commit failure"):
        feedbackstate.save_session(
            state_path, replacement, baseline,
            baseline_path=baseline_path)
    assert state_path.read_bytes() == before


def test_optional_certificate_union_seeds_only_certified_truth(
        baseline_state, tmp_path: Path) -> None:
    baseline_path, baseline, expected_cells, per_tile_user = baseline_state
    selected = baseline.fork()
    position, parent = next(
        (position, row)
        for position, row in enumerate(selected.attempts)
        if row.certified_new and row.stage == "scan")
    key = (
        int(parent.page), int(parent.tile_yx[0]),
        int(parent.tile_yx[1]))
    selected.attempts[position] = replace(
        parent, state="attempted_failed", certified_new=False,
        syndrome_ok=False, crc_ok=False)
    outcome = selected.decode.tiles[key]
    outcome.state = "attempted_failed"
    outcome.user_bits = None
    outcome.certified_by = ""
    outcome.n_iters = 0
    outcome.divergence = {}
    selected.validate_invariants()
    selected_path = tmp_path / "selected-demoted.pkl"
    receiver.save_session(selected_path, selected)

    bits = np.asarray(per_tile_user[key[1:]], np.uint8)
    union_path = tmp_path / "union.json"
    sources = merge_e023b.load_sources([
        merge_e023b.SourceSpec("selected", selected_path.resolve()),
        merge_e023b.SourceSpec("independent", baseline_path.resolve()),
    ])
    merge_e023b.write_json_atomic(
        union_path, merge_e023b.build_union(sources),
        source_paths=tuple(row.path for row in sources))

    session = feedback.create_session(
        selected_path, selected, profile=feedbackstate.PROFILE_CONTROL,
        certificate_union=union_path)
    seeded = session.certificates[key]
    assert seeded.source == "certificate-union"
    assert seeded.born_generation == 0
    assert session.head.statistics["external_seed_certificates"] == 1
    assert session.envelope.certificate_seed_sha256 == hashlib.sha256(
        union_path.read_bytes()).hexdigest()
    assert np.array_equal(seeded.user_bits, bits)
    assert session.tiles[key].state == "certified"
    assert session.envelope.certificate_seed_payload == (
        union_path.read_bytes())

    state_path = tmp_path / "union-seeded-e024.pkl"
    feedbackstate.save_session(
        state_path, session, selected,
        baseline_path=selected_path)
    feedback._TRUSTED_UNION_PROOFS.clear()
    loaded, loaded_baseline = feedbackstate.load_session(state_path)
    assert np.array_equal(
        loaded.certificates[key].user_bits, bits)
    assert receiver.authoritative_digest(loaded_baseline) == (
        receiver.authoritative_digest(selected))

    third = selected.fork()
    third_dpi = third.envelope.dpi + 1.0
    third.envelope = replace(
        third.envelope, dpi=third_dpi)
    third.scans = [
        replace(scan, dpi=third_dpi) for scan in third.scans]
    third_path = tmp_path / "compatible-third.pkl"
    receiver.save_session(third_path, third)
    rebound = copy.deepcopy(session)
    rebound.baseline = feedbackstate.baseline_reference(
        third_path, third)
    feedback._TRUSTED_UNION_PROOFS.clear()
    with pytest.raises(
        ValueError, match="not an exact source artifact"
    ):
        feedbackstate.validate_session(
            rebound, third, baseline_path=third_path,
            validate_baseline=False)

    labels = feedback.export_certified_labels(
        session, selected, certificate_ids=(seeded.certificate_id,))
    known = labels.values[key[0]] >= 0
    assert np.array_equal(
        labels.values[key[0]][known].astype(np.uint8),
        expected_cells[known].astype(np.uint8))

    forged = copy.deepcopy(session)
    old = forged.certificates[key]
    forged_bits = np.asarray(old.user_bits, np.uint8).copy()
    forged_bits[0] ^= np.uint8(1)
    forged_id, forged_bits_sha = feedbackstate.certificate_identity(
        forged.baseline.format_id, forged.baseline.seed,
        key, forged.baseline.rate_id, forged_bits)
    forged.certificates[key] = replace(
        old, certificate_id=forged_id,
        user_bits=forged_bits,
        user_bits_sha256=forged_bits_sha)
    frontier = tuple(sorted(
        row.certificate_id for row in forged.certificates.values()))
    frontier_sha = feedback._hash_parts(
        b"e024/label-frontier/v1",
        *[value.encode("ascii") for value in frontier])
    generation = replace(
        forged.generations[0],
        label_frontier_ids=frontier,
        label_frontier_sha256=frontier_sha)
    generation = replace(
        generation,
        generation_id=feedbackstate.generation_identity(
            generation.ordinal,
            generation.parent_generation_id,
            generation.label_frontier_sha256,
            generation.active_revisions,
            generation.accepted_revision_ids,
            generation.refused_revision_ids,
            generation.patch_ids,
            generation.attempt_ids,
            generation.new_certificate_ids,
            generation.active_projection_sha256,
            generation.fixed_point,
            generation.statistics))
    forged.generations[0] = generation
    with pytest.raises(
        ValueError, match="differs from the embedded union"
    ):
        _validate_without_artifact(forged, selected)
