"""State/scheduling tests for the integrated E023b receiver."""
from __future__ import annotations

import pickle
import sys
import copy
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023b-integrated-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

from paperholo import ldpc, payloaddec, platen, receiver  # noqa: E402
import run_e023b  # noqa: E402
import test_e023 as t23  # noqa: E402


def _survey(image: np.ndarray) -> platen.PayloadSurvey:
    mask = np.ones(image.shape, bool)
    region = platen.PayloadRegion(
        bbox=(0, 0, image.shape[0], image.shape[1]), mask=mask,
        area_mm2=123.0, angle_hint_deg=0.0, score=4.5)
    return platen.PayloadSurvey(
        regions=(region,), c_dots=3, cell_pitch_px=t23.PITCH,
        pitch_votes=((3, 1.0),), diagnostics={"fixture": True})


def _record(descriptor, scan, image, survey=None):
    path = Path(scan.source_path)
    return receiver.make_scan_record(
        scan_id=scan.scan_id, source_path=path,
        source_sha256=scan.source_sha256, source_size=path.stat().st_size,
        dpi=scan.dpi, image=image, capture_id=scan.source_sha256,
        survey=_survey(image) if survey is None else survey,
        result=scan.result, descriptor=descriptor, pages=(0,))


def _fixture(tmp_path: Path, *, n_scans: int = 1, partial: bool = False):
    descriptor = t23._descriptor(b"paper-store/e023b-session")
    rng = np.random.default_rng(2311)
    values, user, framed = t23._coded_page(descriptor, rng)
    image = t23._render_cells(values, rng)
    windows = (t23._grid_windows(values.shape)[:2] if partial
               else t23._grid_windows(values.shape))
    scans = []
    for i in range(n_scans):
        scan_id = f"s{i:03d}"
        placements = [t23._placed_window(
            np.array(values.shape), y, x, h, w,
            origin_px=(y * t23.PITCH + t23.PITCH / 2 - 0.5,
                       x * t23.PITCH + t23.PITCH / 2 - 0.5),
            scan_id=scan_id) for y, x, h, w in windows]
        scans.append(t23._scan_row(tmp_path, scan_id, image, placements))
    payload = t23._session_payload(descriptor, scans)
    upstream = payloaddec.load_e022_session(
        t23._write_state(tmp_path, payload))
    return descriptor, upstream, image, user, framed


def _certified_bits(state) -> dict:
    return {
        key: bytes(np.packbits(out.user_bits))
        for key, out in state.tiles.items() if out.state == "certified"
    }


def test_packed_survey_roundtrip_exact() -> None:
    image = np.zeros((17, 23), np.uint8)
    survey = _survey(image)
    packed = receiver.PackedSurvey.pack(survey)
    restored = packed.unpack()
    assert restored.c_dots == survey.c_dots
    assert restored.cell_pitch_px == survey.cell_pitch_px
    assert restored.pitch_votes == survey.pitch_votes
    assert restored.diagnostics == survey.diagnostics
    assert np.array_equal(restored.regions[0].mask, survey.regions[0].mask)


def test_split_emission_is_qualified_path_and_retains_raw_evidence(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(tmp_path)
    scan = upstream.scans[0]
    evidence = payloaddec.collect_window_evidence(
        scan, image, descriptor.spec(), descriptor.seed, (0,))
    split = payloaddec.freeze_scan_emission(scan, evidence,
                                            descriptor.spec())
    original = payloaddec.emit_scan(
        scan, image, descriptor.spec(), descriptor.seed, (0,))
    assert len(evidence) == len(scan.result.placements)
    assert all(row.raw_means.size == row.page_cells_yx.shape[0]
               for row in evidence)
    assert all(row.calibration_score_nodes.size > 0 for row in evidence)
    assert split.window_rows == original.window_rows
    for page in split.pages:
        for key in ("index", "llr", "owner"):
            assert np.array_equal(split.pages[page][key],
                                  original.pages[page][key])


def test_e023b_single_scan_matches_e023_certificates_and_skips_duplicate_union(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(tmp_path)
    old = payloaddec.run_session(upstream, descriptor,
                                 image_loader=lambda _path: image)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    record = _record(descriptor, upstream.scans[0], image)
    session, counts = receiver.apply_scan(session, record)
    assert _certified_bits(session.decode) == _certified_bits(old)
    assert counts["union"]["evaluated"] == 0
    assert all(row.stage == "scan" for row in session.attempts)
    assert session.decode.n_attempts <= old.n_attempts


def test_append_batching_is_identical_and_duplicate_sha_is_true_noop(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(
        tmp_path, n_scans=2, partial=True)
    records = [_record(descriptor, scan, image) for scan in upstream.scans]

    one = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    for record in records:
        one, _counts = receiver.apply_scan(one, record)

    separate = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    separate, _ = receiver.apply_scan(separate, records[0])
    state_path = tmp_path / "e023b.pkl"
    receiver.save_session(state_path, separate)
    separate = receiver.load_session(state_path)
    separate, _ = receiver.apply_scan(separate, records[1])

    assert receiver.authoritative_digest(one) == receiver.authoritative_digest(
        separate)
    before = pickle.dumps(one, protocol=pickle.HIGHEST_PROTOCOL)
    same, counts = receiver.apply_scan(one, records[0])
    assert same is one
    assert counts["noop"]
    assert pickle.dumps(same, protocol=pickle.HIGHEST_PROTOCOL) == before


def test_empty_skip_set_is_the_exact_default_path(tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(tmp_path)
    record = _record(descriptor, upstream.scans[0], image)
    default = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    explicit = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)

    default, default_counts = receiver.apply_scan(default, record)
    explicit, explicit_counts = receiver.apply_scan(
        explicit, record, skip_tiles=())

    assert receiver.authoritative_digest(default) == (
        receiver.authoritative_digest(explicit))
    assert default_counts == explicit_counts
    assert default_counts["skipped_candidates"] == 0
    assert default.scans[0].decode_skip_tiles == ()


def test_skip_tiles_omits_only_matching_stage1_candidates(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(
        tmp_path, partial=True)
    record = _record(descriptor, upstream.scans[0], image)
    candidates = set(record.tile_evidence_digests)
    skipped = tuple(sorted(candidates)[:3])
    legal = {(0, *tile) for tile in ldpc.tile_grid(
        descriptor.spec().page_cells_yx)}
    noncandidate = min(legal - candidates)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)

    session, counts = receiver.apply_scan(
        session, record, skip_tiles=(*skipped, noncandidate))

    assert counts["skipped_candidates"] == len(skipped)
    assert counts["stage1"]["evaluated"] == len(candidates) - len(skipped)
    assert session.scans[0].decode_skip_tiles == skipped
    assert session.scans[0].emission is record.emission
    assert session.scans[0].tile_evidence_digests == (
        record.tile_evidence_digests)
    attempted = {(row.page, *row.tile_yx) for row in session.attempts}
    assert not attempted.intersection(skipped)


def test_prepopulated_decode_skip_marker_requires_explicit_authorization(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(
        tmp_path, partial=True)
    record = _record(descriptor, upstream.scans[0], image)
    skipped = (min(record.tile_evidence_digests),)
    prepopulated = replace(record, decode_skip_tiles=skipped)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)

    with pytest.raises(ValueError, match="requires explicit matching"):
        receiver.apply_scan(session, prepopulated)
    with pytest.raises(ValueError, match="requires explicit matching"):
        receiver.apply_scan(
            session, prepopulated,
            skip_tiles=(max(record.tile_evidence_digests),))

    applied, counts = receiver.apply_scan(
        session, prepopulated, skip_tiles=skipped)
    assert counts["skipped_candidates"] == 1
    assert applied.scans[0].decode_skip_tiles == skipped
    with pytest.raises(ValueError, match="requires explicit matching"):
        receiver.apply_scan(applied, prepopulated)
    duplicate, duplicate_counts = receiver.apply_scan(
        applied, prepopulated, skip_tiles=skipped)
    assert duplicate is applied
    assert duplicate_counts["noop"]


def test_skip_tiles_omits_changed_union_and_marks_its_frontier(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(
        tmp_path, n_scans=2, partial=True)
    first = _record(descriptor, upstream.scans[0], image)
    second_scan = replace(upstream.scans[1], source_sha256="f" * 64)
    second = _record(descriptor, second_scan, image)
    initial = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    initial, _ = receiver.apply_scan(initial, first)

    baseline, _ = receiver.apply_scan(initial, second)
    union_rows = [row for row in baseline.attempts
                  if row.source == f"union@{second.scan_id}"]
    assert union_rows
    skipped = (union_rows[0].page, *union_rows[0].tile_yx)
    before = [row.attempt_id for row in initial.attempts
              if (row.page, *row.tile_yx) == skipped]

    scheduled, counts = receiver.apply_scan(
        initial, second, skip_tiles=(skipped,))

    after = [row.attempt_id for row in scheduled.attempts
             if (row.page, *row.tile_yx) == skipped]
    assert after == before
    assert counts["skipped_candidates"] == 1
    assert len(scheduled.scans) == 2
    assert scheduled.scans[-1].emission is second.emission
    assert scheduled.scans[-1].decode_skip_tiles == (skipped,)
    scheduled.validate_invariants()

    baseline_for_key = [row for row in baseline.attempts
                        if (row.page, *row.tile_yx) == skipped]
    assert baseline_for_key[-1].stage == "union"


def test_decode_skip_marker_tamper_is_authoritative_and_rejected(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(
        tmp_path, n_scans=2, partial=True)
    first = _record(descriptor, upstream.scans[0], image)
    second = _record(
        descriptor, replace(upstream.scans[1], source_sha256="f" * 64),
        image)
    initial = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    initial, _ = receiver.apply_scan(initial, first)
    baseline, _ = receiver.apply_scan(initial, second)
    union = next(row for row in baseline.attempts
                 if row.source == f"union@{second.scan_id}")
    skipped = (union.page, *union.tile_yx)
    session, _ = receiver.apply_scan(
        initial, second, skip_tiles=(skipped,))
    digest = receiver.authoritative_digest(session)

    tampered = pickle.loads(pickle.dumps(session))
    tampered.scans[-1] = replace(
        tampered.scans[-1], decode_skip_tiles=())
    assert receiver.authoritative_digest(tampered) != digest
    with pytest.raises(ValueError, match="current evidence frontier"):
        tampered.validate_invariants()

    malformed = pickle.loads(pickle.dumps(session))
    other = next(key for key in malformed.scans[-1].tile_evidence_digests
                 if key != skipped)
    malformed.scans[-1] = replace(
        malformed.scans[-1],
        decode_skip_tiles=tuple(sorted((other, skipped), reverse=True)))
    with pytest.raises(ValueError, match="skip marker is not canonical"):
        malformed.validate_invariants()


@pytest.mark.parametrize("skip_tiles", [
    [(0, 0)],
    [[0, 0, 0]],
    [(False, 0, 0)],
    [(0, 0, 0.0)],
    [(1, 0, 0)],
    [(0, 999, 0)],
    [(0, 0, 0), (0, 0, 0)],
])
def test_skip_tiles_rejects_ambiguous_or_illegal_keys(
        tmp_path: Path, skip_tiles) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(tmp_path)
    record = _record(descriptor, upstream.scans[0], image)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    with pytest.raises(ValueError, match="skip_tiles"):
        receiver.apply_scan(session, record, skip_tiles=skip_tiles)


def test_below_floor_decision_is_ledgered_not_crc_exposure(
        tmp_path: Path) -> None:
    descriptor = t23._descriptor(b"paper-store/e023b-floor")
    rng = np.random.default_rng(2312)
    values, _user, _framed = t23._coded_page(descriptor, rng)
    image = t23._render_cells(values, rng)
    placement = t23._placed_window(
        np.array(values.shape), 137, 137, 46, 46,
        origin_px=(137 * t23.PITCH + t23.PITCH / 2 - 0.5,
                   137 * t23.PITCH + t23.PITCH / 2 - 0.5))
    row = t23._scan_row(tmp_path, "s000", image, [placement])
    upstream = payloaddec.load_e022_session(t23._write_state(
        tmp_path, t23._session_payload(descriptor, [row])))
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(
        session, _record(descriptor, upstream.scans[0], image))
    assert session.attempts
    assert all(not row.decoder_invoked for row in session.attempts)
    assert all(row.state == "below_attempt_floor" for row in session.attempts)
    assert session.decode.n_attempts == 0


def test_state_envelope_refuses_dpi_and_implementation_drift(
        tmp_path: Path) -> None:
    descriptor, _upstream, _image, _user, _framed = _fixture(tmp_path)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session.validate(descriptor, (0,), 1600.0)
    with pytest.raises(ValueError, match="mismatch"):
        session.validate(descriptor, (0,), 4800.0)
    broken = session.fork()
    broken.envelope = replace(
        broken.envelope, implementation_sha256=(("bad", "0" * 64),))
    with pytest.raises(ValueError, match="implementation changed"):
        broken.validate(descriptor, (0,), 1600.0)


def test_authoritative_digest_covers_replay_substrate(tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(tmp_path)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(
        session, _record(descriptor, upstream.scans[0], image))
    baseline = receiver.authoritative_digest(session)

    survey_changed = pickle.loads(pickle.dumps(session))
    survey_changed.scans[0].survey.diagnostics["tampered"] = True
    assert receiver.authoritative_digest(survey_changed) != baseline

    result_changed = pickle.loads(pickle.dumps(session))
    result_changed.scans[0].result.region_states[999] = "tampered"
    assert receiver.authoritative_digest(result_changed) != baseline

    emission_changed = pickle.loads(pickle.dumps(session))
    vector = next(iter(emission_changed.scans[0].emission.pages.values()))
    vector["llr"][0] += np.float32(123.0)
    assert receiver.authoritative_digest(emission_changed) != baseline


def test_atomic_save_failure_preserves_previous_session(
        tmp_path: Path, monkeypatch) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(
        tmp_path, n_scans=2, partial=True)
    records = [_record(descriptor, scan, image) for scan in upstream.scans]
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(session, records[0])
    state_path = tmp_path / "atomic.pkl"
    receiver.save_session(state_path, session)
    before = state_path.read_bytes()
    working, _ = receiver.apply_scan(session, records[1])

    def fail_replace(_source, _target):
        raise OSError("injected pre-commit failure")

    monkeypatch.setattr(receiver.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        receiver.save_session(state_path, working)
    assert state_path.read_bytes() == before


def test_reloaded_state_replays_window_freeze_attempt_and_provenance(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(tmp_path)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    record = _record(descriptor, upstream.scans[0], image)
    session, _ = receiver.apply_scan(session, record)
    state_path = tmp_path / "replay.pkl"
    receiver.save_session(state_path, session)
    loaded = receiver.load_session(state_path)
    stored = loaded.scans[0]

    e022_scan = payloaddec.E022Scan(
        stored.scan_id, stored.source_path, stored.source_sha256,
        stored.dpi, stored.result)
    frozen = payloaddec.freeze_scan_emission(
        e022_scan, list(stored.window_evidence), descriptor.spec())
    assert frozen.window_rows == stored.emission.window_rows
    for page in frozen.pages:
        for key in ("index", "llr", "owner"):
            assert np.array_equal(frozen.pages[page][key],
                                  stored.emission.pages[page][key])
    assert stored.placement_ids == receiver.placement_ids_for_result(
        stored.source_sha256, stored.result)
    assert stored.tile_evidence_digests == receiver.tile_evidence_digests(
        stored.emission, descriptor.spec(), descriptor.seed)

    attempt = loaded.attempts[0]
    vector = stored.emission.pages[attempt.page]
    evaluation = payloaddec.evaluate_tile(
        vector["llr"], vector["index"], descriptor.spec(), descriptor.seed,
        attempt.tile_yx, loaded.decode.ldpc_spec)
    assert evaluation.state == attempt.state
    assert evaluation.decoder_invoked == attempt.decoder_invoked
    assert evaluation.n_informative == attempt.n_informative


def test_capture_alias_is_rejected_before_correlated_sum(tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(tmp_path)
    first = _record(descriptor, upstream.scans[0], image)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(session, first)
    alias = replace(first, scan_id="s001", source_sha256="f" * 64)
    with pytest.raises(ValueError, match="capture_id"):
        receiver.apply_scan(session, alias)


def test_record_derivation_tamper_is_rejected(tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(tmp_path)
    record = _record(descriptor, upstream.scans[0], image)
    vector = next(iter(record.emission.pages.values()))
    vector["llr"][0] += np.float32(0.5)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    with pytest.raises(ValueError, match="window evidence"):
        receiver.apply_scan(session, record)


def test_two_pages_remain_separate_in_emissions_attempts_and_tiles(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(tmp_path)
    source = upstream.scans[0]
    result = copy.deepcopy(source.result)
    result.placements.extend(
        replace(row, page=1) for row in list(result.placements))
    scan = replace(source, result=result)
    session = receiver.ReceiverSession.create(
        descriptor, (0, 1), 1600.0)
    record = receiver.make_scan_record(
        scan_id=scan.scan_id, source_path=scan.source_path,
        source_sha256=scan.source_sha256,
        source_size=Path(scan.source_path).stat().st_size,
        dpi=scan.dpi, image=image, capture_id=scan.source_sha256,
        survey=_survey(image), result=scan.result,
        descriptor=descriptor, pages=(0, 1))
    session, _ = receiver.apply_scan(session, record)
    assert set(record.emission.pages) == {0, 1}
    assert {row.page for row in session.attempts} == {0, 1}
    assert {key[0] for key in session.decode.tiles} == {0, 1}


def test_cli_batch_equals_reinvocation_and_duplicate_is_file_noop(
        tmp_path: Path, monkeypatch) -> None:
    descriptor, upstream, image, _user, _framed = _fixture(
        tmp_path, n_scans=2, partial=True)
    records = [_record(descriptor, scan, image) for scan in upstream.scans]
    by_path = {Path(row.source_path): row for row in records}
    results = {row.scan_id: row.result for row in records}

    monkeypatch.setattr(run_e023b, "resolve_format", lambda _name: descriptor)
    monkeypatch.setattr(receiver, "file_identity", lambda path: (
        by_path[Path(path)].source_sha256,
        by_path[Path(path)].source_size))
    monkeypatch.setattr(receiver, "load_image", lambda _path: image)
    monkeypatch.setattr(platen, "detect_payload_regions",
                        lambda _image, dpi: _survey(image))
    monkeypatch.setattr(
        run_e023b.pilotsearch, "search_survey",
        lambda _image, _survey_value, _descriptor, *, scan_id, **_kwargs:
        results[scan_id])

    def make_record(**kwargs):
        template = by_path[Path(kwargs["source_path"])]
        assert template.scan_id == kwargs["scan_id"]
        return replace(template, capture_id=kwargs["capture_id"])

    monkeypatch.setattr(receiver, "make_scan_record", make_record)
    monkeypatch.setattr(run_e023b, "render_final", lambda *_a, **_k: [])

    def invoke(paths, state, report, *, fresh, groups):
        argv = ["run_e023b.py", *(str(path) for path in paths),
                "--dpi", "1600", "--state", str(state),
                "--out", str(tmp_path / "out.png"),
                "--report", str(report), "--capture-groups", groups]
        if fresh:
            argv.append("--fresh")
        monkeypatch.setattr(sys, "argv", argv)
        assert run_e023b.main() == 0

    paths = list(by_path)
    batch_state = tmp_path / "batch.pkl"
    split_state = tmp_path / "split.pkl"
    invoke(paths, batch_state, tmp_path / "batch.json",
           fresh=True, groups="cap-0,cap-1")
    invoke(paths[:1], split_state, tmp_path / "split-0.json",
           fresh=True, groups="cap-0")
    invoke(paths[1:], split_state, tmp_path / "split-1.json",
           fresh=False, groups="cap-1")
    batch = receiver.load_session(batch_state)
    split = receiver.load_session(split_state)
    assert receiver.authoritative_digest(batch) == receiver.authoritative_digest(
        split)

    before = split_state.read_bytes()
    invoke(paths[:1], split_state, tmp_path / "noop.json",
           fresh=False, groups="cap-0")
    assert split_state.read_bytes() == before
