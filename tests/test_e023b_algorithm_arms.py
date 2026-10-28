"""Focused contracts for the explicit E023b algorithm arms."""
from __future__ import annotations

import pickle
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023b-integrated-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

from paperholo import (compose, ldpc, payloaddec, receiver,  # noqa: E402
                       receiverdiag)
import run_e023b  # noqa: E402
import test_e023 as t23  # noqa: E402
import test_e023b_session as session_test  # noqa: E402


def _demote_one_certificate(
    session: receiver.ReceiverSession,
) -> tuple[receiver.ReceiverSession, tuple[int, int, int],
           receiver.TileAttempt]:
    """Turn one clean baseline certificate into a consistent failed fixture."""
    working = session.fork()
    pos, parent = next(
        (pos, row) for pos, row in enumerate(working.attempts)
        if row.certified_new and row.stage == "scan")
    key = (parent.page, *parent.tile_yx)
    working.attempts[pos] = replace(
        parent, state="attempted_failed", certified_new=False,
        syndrome_ok=False, crc_ok=False)
    out = working.decode.tiles[key]
    out.state = "attempted_failed"
    out.user_bits = None
    out.certified_by = ""
    out.n_iters = 0
    out.divergence = {}
    working.validate_invariants()
    return working, key, working.attempts[pos]


def _controlled_failure(
    llr_values, payload_indices, spec, seed, tile_yx, ldpc_spec,
    *, max_iters=60, alpha=0.8,
) -> payloaddec.TileEvaluation:
    """Preserve the attempt floor but force every invoked decode to fail."""
    del alpha
    mask = ldpc.tile_shorten_mask(tile_yx, spec, seed)
    n_nonshort = int((~mask).sum())
    k_eff = max(ldpc_spec.k_bits - int(mask.sum()), 0)
    if ldpc.tile_user_capacity(mask, ldpc_spec) == 0:
        return payloaddec.TileEvaluation(
            "degenerate", False, k_eff, n_nonshort, 0, 0.0)
    gathered, _mask, coverage = ldpc.gather_tile_llrs(
        llr_values, payload_indices, spec, seed, tile_yx)
    n_informative = int((gathered[~mask] != 0.0).sum())
    if n_informative < k_eff:
        return payloaddec.TileEvaluation(
            "below_attempt_floor", False, k_eff, n_nonshort,
            n_informative, float(coverage),
            n_erased=n_nonshort - n_informative)
    return payloaddec.TileEvaluation(
        "attempted_failed", True, k_eff, n_nonshort, n_informative,
        float(coverage), n_iters=2 * int(max_iters),
        syndrome_ok=False, crc_ok=False,
        n_erased=n_nonshort - n_informative)


def _two_distinct_records(tmp_path: Path):
    descriptor = t23._descriptor(b"paper-store/e023b-bp-frontier")
    rng = np.random.default_rng(2315)
    values, _user, _framed = t23._coded_page(descriptor, rng)
    images = [t23._render_cells(values, rng) for _ in range(2)]
    rows = []
    for i, image in enumerate(images):
        scan_id = f"s{i:03d}"
        placements = [t23._placed_window(
            np.array(values.shape), y, x, h, w,
            origin_px=(y * t23.PITCH + t23.PITCH / 2 - 0.5,
                       x * t23.PITCH + t23.PITCH / 2 - 0.5),
            scan_id=scan_id)
            for y, x, h, w in t23._grid_windows(values.shape)]
        rows.append(t23._scan_row(
            tmp_path, scan_id, image, placements))
    upstream = payloaddec.load_e022_session(t23._write_state(
        tmp_path, t23._session_payload(descriptor, rows)))
    records = [session_test._record(descriptor, scan, image)
               for scan, image in zip(upstream.scans, images, strict=True)]
    assert records[0].source_sha256 != records[1].source_sha256
    return descriptor, records


def _full_and_partial_records(tmp_path: Path):
    """One full scan followed by a distinct sub-floor single-window scan."""
    descriptor = t23._descriptor(b"paper-store/e023b-bp-below-frontier")
    rng = np.random.default_rng(2316)
    values, _user, _framed = t23._coded_page(descriptor, rng)
    images = [t23._render_cells(values, rng) for _ in range(2)]
    rows = []
    window_sets = [t23._grid_windows(values.shape), [(128, 128, 40, 40)]]
    for i, (image, windows) in enumerate(zip(
            images, window_sets, strict=True)):
        scan_id = f"s{i:03d}"
        placements = [t23._placed_window(
            np.array(values.shape), y, x, h, w,
            origin_px=(y * t23.PITCH + t23.PITCH / 2 - 0.5,
                       x * t23.PITCH + t23.PITCH / 2 - 0.5),
            scan_id=scan_id)
            for y, x, h, w in windows]
        rows.append(t23._scan_row(
            tmp_path, scan_id, image, placements))
    upstream = payloaddec.load_e022_session(t23._write_state(
        tmp_path, t23._session_payload(descriptor, rows)))
    records = [session_test._record(descriptor, scan, image)
               for scan, image in zip(upstream.scans, images, strict=True)]
    return descriptor, records


def _replace_attempt(
    session: receiver.ReceiverSession,
    position: int,
    **changes,
) -> receiver.ReceiverSession:
    """Tamper one immutable ledger row while keeping its identity index sane."""
    working = session.fork()
    row = replace(working.attempts[position], **changes)
    key = (row.page, *row.tile_yx)
    row = replace(row, attempt_id=receiver._attempt_identity(
        key, row.stage, row.decoder_profile, row.evidence_digest))
    working.attempts[position] = row
    working.attempt_ids = {attempt.attempt_id
                           for attempt in working.attempts}
    return working


def test_bp_retry_is_separate_ledgered_idempotent_action(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = session_test._fixture(
        tmp_path)
    baseline = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    baseline, _ = receiver.apply_scan(
        baseline, session_test._record(
            descriptor, upstream.scans[0], image))
    baseline, key, parent = _demote_one_certificate(baseline)
    before_attempts = baseline.decode.n_attempts
    observed = []

    retried, counts = receiver.retry_failed_bp(
        baseline, on_attempt=lambda _state, row: observed.append(row))
    assert counts == {
        "noop": False, "frontier": 1, "eligible": 1,
        "skipped_failed": 0, "attempted": 1, "certified": 1,
        "total_certified": 72,
    }
    assert len(observed) == 1
    row = observed[0]
    assert (row.page, *row.tile_yx) == key
    assert row.stage == "retry150"
    assert row.decoder_profile.endswith("decode_tile-max150-alpha0.8")
    assert row.evidence_digest == parent.evidence_digest
    assert row.scan_ids == parent.scan_ids
    assert row.capture_ids == parent.capture_ids
    assert row.attempt_id != parent.attempt_id
    assert row.decoder_invoked and row.certified_new
    assert retried.decode.n_attempts == before_attempts + 1
    assert retried.decode.tiles[key].state == "certified"
    assert set(retried.decode.tiles[key].divergence) == set(row.scan_ids)

    path = tmp_path / "retried.pkl"
    receiver.save_session(path, retried)
    loaded = receiver.load_session(path)
    before = pickle.dumps(loaded, protocol=pickle.HIGHEST_PROTOCOL)
    same, again = receiver.retry_failed_bp(loaded)
    assert same is loaded and again["noop"] and again["attempted"] == 0
    assert pickle.dumps(same, protocol=pickle.HIGHEST_PROTOCOL) == before


def test_bp_retry_skips_globally_certified_failed_frontier(
        tmp_path: Path) -> None:
    descriptor, upstream, image, _user, _framed = session_test._fixture(
        tmp_path)
    baseline = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    baseline, _ = receiver.apply_scan(
        baseline, session_test._record(
            descriptor, upstream.scans[0], image))
    baseline, key, _parent = _demote_one_certificate(baseline)
    before = pickle.dumps(baseline, protocol=pickle.HIGHEST_PROTOCOL)

    same, counts = receiver.retry_failed_bp(
        baseline, skip_tiles=(key,))

    assert same is baseline
    assert counts == {
        "noop": True, "frontier": 1, "eligible": 0,
        "skipped_failed": 1, "attempted": 0, "certified": 0,
        "total_certified": 71,
    }
    assert pickle.dumps(same, protocol=pickle.HIGHEST_PROTOCOL) == before


def test_bp_retry_uses_latest_union_frontier_and_retries_new_evidence(
        tmp_path: Path, monkeypatch) -> None:
    descriptor, records = _two_distinct_records(tmp_path)
    monkeypatch.setattr(payloaddec, "evaluate_tile", _controlled_failure)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(session, records[0])
    once, first = receiver.retry_failed_bp(session)
    assert first["attempted"] > 0 and first["certified"] == 0
    same, unchanged = receiver.retry_failed_bp(once)
    assert same is once and unchanged["noop"]

    advanced, _ = receiver.apply_scan(once, records[1])
    before = len(advanced.attempts)
    twice, second = receiver.retry_failed_bp(advanced)
    retry_rows = twice.attempts[before:]
    assert second["attempted"] > 0 and second["certified"] == 0
    assert len(retry_rows) == second["attempted"]
    assert all(row.stage == "retry150" for row in retry_rows)
    assert all(row.scan_ids == ("s000", "s001") for row in retry_rows)
    assert all(row.source == "union@s001" for row in retry_rows)
    assert all(row.decoder_profile.endswith(
        "decode_tile-max150-alpha0.8") for row in retry_rows)
    assert all(row.n_iters == 300 for row in retry_rows)

    # Baseline rows are an append-only scan/union chronology.  Moving an old
    # scan evaluation behind the current union must not make stale evidence
    # appear to be the retry frontier.
    current_union = next(
        row for row in advanced.attempts
        if row.stage == "union" and row.source == "union@s001")
    current_key = (current_union.page, *current_union.tile_yx)
    old_scan_pos = next(
        i for i, row in enumerate(advanced.attempts)
        if row.stage == "scan" and row.source == "s001"
        and (row.page, *row.tile_yx) == current_key)
    reordered_baseline = advanced.fork()
    moved = reordered_baseline.attempts.pop(old_scan_pos)
    current_union_pos = next(
        i for i, row in enumerate(reordered_baseline.attempts)
        if row.attempt_id == current_union.attempt_id)
    reordered_baseline.attempts.insert(current_union_pos + 1, moved)
    with pytest.raises(ValueError, match="chronology"):
        reordered_baseline.validate_invariants()

    scan_pos = next(i for i, row in enumerate(twice.attempts)
                    if row.stage == "scan")
    bad_scan_digest = _replace_attempt(
        twice, scan_pos, evidence_digest="0" * 64)
    with pytest.raises(ValueError, match="baseline attempt evidence"):
        bad_scan_digest.validate_invariants()

    bad_scan_record = twice.fork()
    stored = bad_scan_record.scans[0]
    stored_digests = dict(stored.tile_evidence_digests)
    stored_key = next(iter(stored_digests))
    stored_digests[stored_key] = "0" * 64
    bad_scan_record.scans[0] = replace(
        stored, tile_evidence_digests=stored_digests)
    with pytest.raises(ValueError, match="tile evidence digest mismatch"):
        bad_scan_record.validate_invariants()

    bad_profile = _replace_attempt(
        twice, scan_pos,
        decoder_profile=receiver.decoder_profile(
            descriptor.ldpc_rate, receiver.RETRY_BP_MAX_ITERS,
            receiver.BP_ALPHA))
    with pytest.raises(ValueError, match="wrong decoder profile"):
        bad_profile.validate_invariants()

    union_pos = next(i for i, row in enumerate(twice.attempts)
                     if row.stage == "union")
    union = twice.attempts[union_pos]
    bad_union_order = _replace_attempt(
        twice, union_pos,
        scan_ids=tuple(reversed(union.scan_ids)),
        capture_ids=tuple(reversed(union.capture_ids)))
    with pytest.raises(ValueError, match="baseline attempt evidence"):
        bad_union_order.validate_invariants()
    bad_union_digest = _replace_attempt(
        twice, union_pos, evidence_digest="f" * 64)
    with pytest.raises(ValueError, match="baseline attempt evidence"):
        bad_union_digest.validate_invariants()

    retry_pos = next(
        i for i in range(len(twice.attempts) - 1, -1, -1)
        if twice.attempts[i].stage == "retry150"
        and len(twice.attempts[i].scan_ids) > 1)
    retry = twice.attempts[retry_pos]
    bad_retry_source = _replace_attempt(
        twice, retry_pos, source="union@s000")
    with pytest.raises(ValueError, match="failed baseline parent"):
        bad_retry_source.validate_invariants()

    parent_pos = next(
        i for i in range(retry_pos - 1, -1, -1)
        if twice.attempts[i].stage == "union"
        and (twice.attempts[i].page, *twice.attempts[i].tile_yx)
        == (retry.page, *retry.tile_yx)
        and twice.attempts[i].evidence_digest == retry.evidence_digest)
    reordered = twice.fork()
    moved = reordered.attempts.pop(retry_pos)
    reordered.attempts.insert(parent_pos, moved)
    with pytest.raises(ValueError, match="failed baseline parent"):
        reordered.validate_invariants()


def test_bp_retry_never_tunnels_through_newer_below_floor_baseline(
        tmp_path: Path, monkeypatch) -> None:
    descriptor, records = _full_and_partial_records(tmp_path)
    monkeypatch.setattr(payloaddec, "evaluate_tile", _controlled_failure)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(session, records[0])

    # Append the second frozen scan, then reproduce just its scan-stage row.
    # This isolates the frontier contract from the normal following union.
    frontier = session.fork()
    partial = records[1]
    frontier.scans.append(partial)
    frontier.decode.scans.append(partial.emission)
    frontier.decode.upstream = tuple(
        (scan.scan_id, scan.source_sha256) for scan in frontier.scans)
    candidates = []
    vec = partial.emission.pages[0]
    for key, digest in partial.tile_evidence_digests.items():
        evaluation = _controlled_failure(
            vec["llr"], vec["index"], frontier.decode.spec,
            frontier.decode.seed, key[1:], frontier.decode.ldpc_spec)
        if (evaluation.state == "below_attempt_floor"
                and frontier.decode.tiles[key].state == "attempted_failed"):
            candidates.append((key, digest))
    assert candidates
    key, digest = candidates[0]
    row, certified = receiver._apply_evaluation(
        frontier, key=key, stage="scan", source=partial.scan_id,
        evidence_digest=digest, scan_ids=(partial.scan_id,),
        capture_ids=(partial.capture_id,), llr_values=vec["llr"],
        payload_indices=vec["index"])
    assert row is not None and row.state == "below_attempt_floor"
    assert not row.decoder_invoked and not certified

    # With two contributing scans the current-scan row is intermediate; the
    # transaction-final union cannot be omitted from a valid state.
    with pytest.raises(ValueError, match="current evidence frontier"):
        frontier.validate_invariants()

    components = [
        scan for scan in frontier.scans if key in scan.tile_evidence_digests
    ]
    evidence_digest = receiver._sha256_bytes(
        b"e023b/union-tile-evidence/v1",
        *(f"{scan.scan_id}:{scan.tile_evidence_digests[key]}".encode(
            "ascii") for scan in components))
    capacity = compose.payload_capacity(frontier.decode.spec)
    acc = np.zeros(capacity, np.float64)
    touched = np.zeros(capacity, bool)
    for component in components:
        vec = component.emission.pages[key[0]]
        acc[vec["index"]] += vec["llr"]
        touched[vec["index"]] = True
    index = np.flatnonzero(touched)

    def forced_below(*_args, **_kwargs):
        mask = frontier.decode.shorten_mask(key[1:])
        n_nonshort = int((~mask).sum())
        k_eff = max(frontier.decode.ldpc_spec.k_bits - int(mask.sum()), 0)
        n_info = max(k_eff - 1, 0)
        return payloaddec.TileEvaluation(
            "below_attempt_floor", False, k_eff, n_nonshort, n_info, 0.5,
            n_erased=n_nonshort - n_info)

    monkeypatch.setattr(payloaddec, "evaluate_tile", forced_below)
    union_row, union_certified = receiver._apply_evaluation(
        frontier, key=key, stage="union", source="union@s001",
        evidence_digest=evidence_digest,
        scan_ids=tuple(scan.scan_id for scan in components),
        capture_ids=tuple(scan.capture_id for scan in components),
        llr_values=acc[index], payload_indices=index)
    assert union_row is not None and not union_certified
    assert union_row.state == "below_attempt_floor"
    frontier.validate_invariants()

    monkeypatch.setattr(payloaddec, "evaluate_tile", _controlled_failure)
    retried, counts = receiver.retry_failed_bp(frontier)
    target_retries = [attempt for attempt in retried.attempts
                      if attempt.stage == "retry150"
                      and (attempt.page, *attempt.tile_yx) == key]
    assert counts["attempted"] > 0
    assert not target_retries
    assert retried.decode.tiles[key].state == "attempted_failed"

    below_pos = next(i for i, attempt in enumerate(frontier.attempts)
                     if attempt is union_row)
    impossible_below = _replace_attempt(
        frontier, below_pos, n_informative=union_row.k_eff,
        n_erased=union_row.n_nonshort - union_row.k_eff)
    with pytest.raises(ValueError, match="state semantics"):
        impossible_below.validate_invariants()


def test_bp_retry_diagnostic_uses_parent_scan_or_latest_union_view() -> None:
    scans = [SimpleNamespace(scan_id="s000"),
             SimpleNamespace(scan_id="s001")]
    session = SimpleNamespace(scans=scans)
    scan_parent = SimpleNamespace(scan_ids=("s000",))
    union_parent = SimpleNamespace(scan_ids=("s000", "s001"))
    assert run_e023b._bp_retry_display_scan(
        session, scan_parent).scan_id == "s000"
    assert run_e023b._bp_retry_display_scan(
        session, union_parent).scan_id == "s001"
    assert run_e023b._bp_retry_display_scan(session, None).scan_id == "s001"


def test_detector_profile_and_context_sidecar_are_frozen_and_replayed(
        tmp_path: Path, monkeypatch) -> None:
    descriptor, upstream, image, _user, _framed = session_test._fixture(
        tmp_path)
    scan = upstream.scans[0]
    record = receiver.make_scan_record(
        scan_id=scan.scan_id, source_path=scan.source_path,
        source_sha256=scan.source_sha256,
        source_size=Path(scan.source_path).stat().st_size,
        dpi=scan.dpi, image=image, capture_id=scan.source_sha256,
        survey=session_test._survey(image), result=scan.result,
        descriptor=descriptor, pages=(0,),
        detector_profile=payloaddec.DETECTOR_CTX_PAVA_V1)
    assert record.detector_profile == payloaddec.DETECTOR_CTX_PAVA_V1
    assert len(record.context_fits) == 1
    assert record.context_fits[0].region_index == 0
    # This fixture fails the held-out gate: the complete rejected decision is
    # still retained while every baseline evidence object remains baseline.
    assert not record.context_fits[0].adopted
    assert {row.detector_profile for row in record.window_evidence} == {
        payloaddec.DETECTOR_PAVA_V1}

    session = receiver.ReceiverSession.create(
        descriptor, (0,), 1600.0,
        detector_profile=payloaddec.DETECTOR_CTX_PAVA_V1)
    assert "production:e023b-entrypoint" in dict(
        session.envelope.implementation_sha256)
    session, _ = receiver.apply_scan(session, record)
    state_path = tmp_path / "ctx.pkl"
    receiver.save_session(state_path, session)
    loaded = receiver.load_session(state_path)
    loaded.validate(
        descriptor, (0,), 1600.0,
        detector_profile=payloaddec.DETECTOR_CTX_PAVA_V1)
    with pytest.raises(ValueError, match="mismatch"):
        loaded.validate(
            descriptor, (0,), 1600.0,
            detector_profile=payloaddec.DETECTOR_PAVA_V1)

    report = run_e023b.report_dict(loaded)
    assert report["detector_profile"] == payloaddec.DETECTOR_CTX_PAVA_V1
    assert report["scans"][0]["detector_profile"] == report[
        "detector_profile"]
    assert len(report["scans"][0]["context_fits"]) == 1
    assert report["decoder_profiles"]["baseline"].endswith(
        "decode_tile-max60-alpha0.8")

    fit = record.context_fits[0]
    tampered = replace(
        record, context_fits=(replace(fit, reason="tampered"),))
    fresh = receiver.ReceiverSession.create(
        descriptor, (0,), 1600.0,
        detector_profile=payloaddec.DETECTOR_CTX_PAVA_V1)
    with pytest.raises(ValueError, match="context fit sidecar"):
        receiver.apply_scan(fresh, tampered)

    cli_state = tmp_path / "ctx-cli.pkl"
    monkeypatch.setattr(run_e023b, "resolve_format", lambda _name: descriptor)
    monkeypatch.setattr(run_e023b, "render_final", lambda *_a, **_k: [])
    monkeypatch.setattr(sys, "argv", [
        "run_e023b.py", "--dpi", "1600", "--state", str(cli_state),
        "--out", str(tmp_path / "ctx.png"), "--fresh",
        "--detector-profile", payloaddec.DETECTOR_CTX_PAVA_V1,
    ])
    assert run_e023b.main() == 0
    assert (receiver.load_session(cli_state).envelope.detector_profile
            == payloaddec.DETECTOR_CTX_PAVA_V1)


def test_cli_bp_retry_is_state_only_and_commits_once(
        tmp_path: Path, monkeypatch) -> None:
    descriptor, upstream, image, _user, _framed = session_test._fixture(
        tmp_path)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(
        session, session_test._record(
            descriptor, upstream.scans[0], image))
    session, key, _parent = _demote_one_certificate(session)
    state_path = tmp_path / "bp-cli.pkl"
    report_path = tmp_path / "bp-cli.json"
    receiver.save_session(state_path, session)
    monkeypatch.setattr(run_e023b, "resolve_format", lambda _name: descriptor)
    monkeypatch.setattr(run_e023b, "render_final", lambda *_a, **_k: [])
    monkeypatch.setattr(sys, "argv", [
        "run_e023b.py", "--dpi", "1600", "--state", str(state_path),
        "--out", str(tmp_path / "bp.png"), "--report", str(report_path),
        "--bp-retry",
    ])
    assert run_e023b.main() == 0
    loaded = receiver.load_session(state_path)
    assert loaded.decode.tiles[key].state == "certified"
    assert loaded.attempts[-1].stage == "retry150"
    report = __import__("json").loads(report_path.read_text())
    assert report["attempt_ledger"][-1]["decoder_profile"].endswith(
        "decode_tile-max150-alpha0.8")

    before = state_path.read_bytes()
    monkeypatch.setattr(sys, "argv", [
        "run_e023b.py", "--dpi", "1600", "--state", str(state_path),
        "--out", str(tmp_path / "bp.png"), "--report", str(report_path),
        "--bp-retry",
    ])
    assert run_e023b.main() == 0
    assert state_path.read_bytes() == before

    monkeypatch.setattr(sys, "argv", [
        "run_e023b.py", str(upstream.scans[0].source_path),
        "--dpi", "1600", "--state", str(state_path), "--bp-retry",
    ])
    assert run_e023b.main() == 2
    assert state_path.read_bytes() == before


def test_cli_bp_retry_diag_failure_is_observer_only(
        tmp_path: Path, monkeypatch) -> None:
    descriptor, upstream, image, _user, _framed = session_test._fixture(
        tmp_path)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(
        session, session_test._record(
            descriptor, upstream.scans[0], image))
    session, _key, _parent = _demote_one_certificate(session)
    expected, counts = receiver.retry_failed_bp(session)
    assert counts["certified"] == 1

    state_path = tmp_path / "bp-diag.pkl"
    receiver.save_session(state_path, session)

    class BrokenViewer:
        instance = None

        def __init__(self, *_args, **_kwargs):
            self.disabled = False
            self.closed = False
            BrokenViewer.instance = self

        def publish(self, *_args, **_kwargs):
            raise AssertionError("progress failure should disable first")

        def disable(self, _exc):
            self.disabled = True

        def close(self):
            self.closed = True
            raise RuntimeError("observer close failure")

    monkeypatch.setitem(
        sys.modules, "e023b_diag",
        SimpleNamespace(DiagViewer=BrokenViewer))
    monkeypatch.setattr(run_e023b, "resolve_format", lambda _name: descriptor)
    monkeypatch.setattr(run_e023b, "render_final", lambda *_a, **_k: [])

    def broken_progress(*_args, **_kwargs):
        raise RuntimeError("observer progress failure")

    monkeypatch.setattr(receiverdiag, "work_plan_progress", broken_progress)
    monkeypatch.setattr(sys, "argv", [
        "run_e023b.py", "--dpi", "1600", "--state", str(state_path),
        "--out", str(tmp_path / "bp.png"), "--bp-retry",
        "--diag", str(tmp_path / "diag"),
    ])
    assert run_e023b.main() == 0
    observed = receiver.load_session(state_path)
    assert (receiver.authoritative_digest(observed)
            == receiver.authoritative_digest(expected))
    assert BrokenViewer.instance is not None
    assert BrokenViewer.instance.disabled
    assert BrokenViewer.instance.closed
