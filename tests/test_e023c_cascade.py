"""Focused contracts for the fresh E023c cascade orchestrator."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023c-scale-space-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

import cascade  # noqa: E402
import scale_space  # noqa: E402
from paperholo import formats, payloaddec, pilotsearch  # noqa: E402


# The e018b stop oracle is a sha-gated BUILD artifact (experiments/*/build/
# is gitignored), so the historical hard-coded build path broke on every
# fresh checkout.  Regenerate it once per module from a deterministic
# payload — gen_e018b is payload-independent in format terms, so any
# one-page c3 manifest is a valid descriptor/stop oracle here.
_MANIFEST_PAYLOAD = b"e023c cascade stop-oracle fixture\n" * 64


@pytest.fixture(scope="module")
def manifest_path(tmp_path_factory) -> Path:
    build = tmp_path_factory.mktemp("e018b-build")
    payload = build / "payload.bin"
    payload.write_bytes(_MANIFEST_PAYLOAD)
    generated = subprocess.run(
        [sys.executable,
         str(ROOT / "experiments/018b-payload-sheet/gen_e018b.py"),
         "emit", "c3", str(payload), "-o", str(build / "oracle.ps")],
        capture_output=True, text=True)
    assert generated.returncode == 0, generated.stderr
    manifest = build / "oracle_manifest.json"
    assert manifest.is_file()
    return manifest


def _placed(*, pose, method="correlation", page=0, origin=(100, 120)):
    return pilotsearch.PlacedWindow(
        region_index=0,
        window=pilotsearch.Window(10, 20, 80, 90, 400),
        page=page, origin_yx=origin, rot_k=0, method=method,
        mismatch=0.1, validation_mismatch=0.12, rival_mismatch=0.3,
        support=100, pose=pose, elapsed_s=0.1, component=0,
        rival_searched=True, scan_id="lower")


def test_continuation_hint_preserves_native_physical_pose() -> None:
    schedule = scale_space.ScaleSchedule.auto(1200, 3)
    lower, upper = schedule.levels[0], schedule.levels[1]
    pose = pilotsearch.AffinePose(
        origin_yx=(100.25, 80.75),
        jacobian_yx=((2.0, 0.05), (-0.03, 2.0)),
        angle_deg=0.0, pitch_px=2.0, phase_yx=(0.5, 0.5))
    result = pilotsearch.SearchResult(
        placements=[_placed(pose=pose)],
        diagnostics={"window_audit": {}, "scan_id": "lower"})

    hint, = cascade.continuation_hints(result, lower, upper)
    old_native = lower.transform.from_view_pose(pose)
    new_native = upper.transform.from_view_pose(hint.pose)

    assert hint.method == "lower_accepted"
    assert np.allclose(old_native.origin_yx, new_native.origin_yx)
    assert np.allclose(old_native.matrix(), new_native.matrix())
    assert hint.page_cells_yx.shape == (0, 2)


def test_continuation_retains_bounded_runner_up() -> None:
    schedule = scale_space.ScaleSchedule.auto(1200, 3)
    lower, upper = schedule.levels[:2]
    pose_field = {
        "origin_yx": (30.0, 40.0),
        "jacobian_yx": ((2.0, 0.0), (0.0, 2.0)),
        "angle_deg": 0.0, "pitch_px": 2.0, "phase_yx": (0.5, 0.5),
    }
    rows = []
    for index in range(4):
        rows.append({
            "window": [index, 2 * index, 80, 80], "depth": 0,
            "outcome": "unresolved", "pose_field": pose_field,
            "mismatch": 0.1 + index / 100,
            "best_candidate": {
                "page": 0, "origin_yx": [100 + index, 120], "rot_k": 0,
                "support": 80, "rival_mismatch": 0.4,
                "validation_mismatch": 0.2 + index / 100,
                "mismatch_gap": 0.1,
            },
        })
    result = pilotsearch.SearchResult(diagnostics={
        "window_audit": {0: rows}, "scan_id": "lower"})

    hints = cascade.continuation_hints(
        result, lower, upper, runner_up_per_region=2)

    assert len(hints) == 2
    assert all(row.method == "lower_runner_up" for row in hints)
    assert [row.origin_yx[0] for row in hints] == [100, 101]


def test_lower_hint_bound_reserves_nearest_runner_up_tail() -> None:
    pose = pilotsearch.AffinePose(
        origin_yx=(100.0, 100.0),
        jacobian_yx=((2.0, 0.0), (0.0, 2.0)),
        angle_deg=0.0, pitch_px=2.0, phase_yx=(0.5, 0.5))
    accepted = [
        _placed(
            pose=replace(pose, origin_yx=(100.0, 100.0 + index)),
            method="lower_accepted", origin=(index, 0))
        for index in range(12)
    ]
    runners = [
        _placed(
            pose=replace(pose, origin_yx=(100.0 + index / 10, 100.0)),
            method="lower_runner_up", origin=(100 + index, 0))
        for index in range(4)
    ]

    ranked = pilotsearch._rank_lower_hints(accepted + runners, pose)

    assert len(ranked) == pilotsearch.LOWER_HINT_LIMIT
    assert [row.method for _index, row in ranked[:6]] == [
        "lower_accepted"] * 6
    assert [row.method for _index, row in ranked[6:]] == [
        "lower_runner_up"] * 2
    assert [row.origin_yx[0] for _index, row in ranked[6:]] == [100, 101]


def test_lower_hint_bound_backfills_missing_hint_class() -> None:
    pose = pilotsearch.AffinePose(
        origin_yx=(0.0, 0.0),
        jacobian_yx=((2.0, 0.0), (0.0, 2.0)),
        angle_deg=0.0, pitch_px=2.0, phase_yx=(0.5, 0.5))
    runners = [
        _placed(
            pose=replace(pose, origin_yx=(float(index), 0.0)),
            method="lower_runner_up", origin=(index, 0))
        for index in range(12)
    ]

    ranked = pilotsearch._rank_lower_hints(runners, pose)

    assert len(ranked) == pilotsearch.LOWER_HINT_LIMIT
    assert all(row.method == "lower_runner_up" for _index, row in ranked)


def test_certificate_portfolio_agrees_or_fails_closed() -> None:
    key = (0, 2, 3)
    bits = np.array([0, 1, 1, 0], np.uint8)
    a = cascade.Certificate(key, bits, ("ppc-2-1",), ("s0",))
    b = cascade.Certificate(key, bits.copy(), ("ppc-4-1",), ("s0",))
    merged = cascade.merge_certificates({key: a}, {key: b})
    assert merged[key].lanes == ("ppc-2-1", "ppc-4-1")
    assert merged[key].sources == ("s0",)

    wrong = replace(b, user_bits=np.array([1, 1, 1, 0], np.uint8))
    with pytest.raises(payloaddec.FatalIntegrityError, match="conflicting"):
        cascade.merge_certificates({key: a}, {key: wrong})


def test_lane_names_are_ppc_not_capture_or_dpi_aliases() -> None:
    schedule = scale_space.ScaleSchedule.auto(1200, 3)
    assert [cascade.lane_key(level) for level in schedule.levels] == [
        "ppc-2-1", "ppc-3-1", "ppc-6-1"]


def test_process_level_without_observer_disables_all_fine_callbacks(
        tmp_path: Path, monkeypatch) -> None:
    """Headless runs must not build per-window/per-attempt diagnostics."""
    from PIL import Image
    from paperholo import receiver

    descriptor = next(
        row for row in formats.FORMAT_REGISTRY
        if row.format_id == "e018b-v3-c3")
    level = scale_space.ScaleSchedule.auto(600, 3).levels[-1]
    source = tmp_path / "blank.png"
    image = np.full((96, 128), 240, np.uint8)
    Image.fromarray(image, mode="L").save(source)
    lane = receiver.ReceiverSession.create(
        descriptor, (0,), float(level.dpi))

    real_search = cascade.pilotsearch.search_survey
    real_record = cascade.receiver.make_scan_record
    real_apply = cascade.receiver.apply_scan
    real_retry = cascade.receiver.retry_failed_bp
    real_refine = cascade.refine_result_from_certificates

    def checked_search(*args, **kwargs):
        assert kwargs.get("on_window") is None
        assert kwargs.get("on_region") is None
        return real_search(*args, **kwargs)

    def checked_record(*args, **kwargs):
        assert kwargs.get("on_payload_region") is None
        assert kwargs.get("on_context") is None
        return real_record(*args, **kwargs)

    def checked_apply(*args, **kwargs):
        assert kwargs.get("on_attempt") is None
        return real_apply(*args, **kwargs)

    def checked_retry(*args, **kwargs):
        assert kwargs.get("on_attempt") is None
        return real_retry(*args, **kwargs)

    def checked_refine(*args, **kwargs):
        assert kwargs.get("on_window") is None
        return real_refine(*args, **kwargs)

    monkeypatch.setattr(cascade.pilotsearch, "search_survey", checked_search)
    monkeypatch.setattr(cascade.receiver, "make_scan_record", checked_record)
    monkeypatch.setattr(cascade.receiver, "apply_scan", checked_apply)
    monkeypatch.setattr(cascade.receiver, "retry_failed_bp", checked_retry)
    monkeypatch.setattr(
        cascade, "refine_result_from_certificates", checked_refine)

    run = cascade.process_level(
        image=image, source_path=source, level=level,
        descriptor=descriptor, pages=(0,), capture_id="headless",
        lane_session=lane, bp_retry=True, observer=None)
    assert run.result.placements == []


def test_production_entrypoint_empty_scan_commits_and_resumes(
    tmp_path: Path, monkeypatch,
) -> None:
    """Exercise the real CLI/state/lane barrier without costly E022 work."""
    import cascade_state
    import run_e023c
    from PIL import Image

    source = tmp_path / "blank.png"
    Image.fromarray(np.full((256, 320), 240, np.uint8), mode="L").save(source)
    state = tmp_path / "state.pkl"
    report = tmp_path / "report.json"
    out = tmp_path / "out.png"
    diag = tmp_path / "diag"
    argv = [
        "run_e023c.py", str(source), "--dpi", "600",
        "--format", "e018b-v3-c3", "--pages", "0",
        "--capture-groups", "blank-capture", "--ppc-levels", "2,3",
        "--state", str(state), "--report", str(report),
        "--out", str(out), "--diag", str(diag), "--diag-port", "0",
        "--panel-width", "120", "--fresh",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    assert run_e023c.main() == 0
    session = cascade_state.load_session(state)
    assert session.captures[0].status == "exhausted"
    assert len(session.decoder_lanes) == 2
    assert all(len(lane.scans) == 1
               for lane in session.lane_sessions.values())
    assert report.exists()
    assert out.exists()
    assert list(diag.glob("frame_*.json"))

    # Reinvocation of the same exact source/capture is an authoritative no-op.
    monkeypatch.setattr(sys, "argv", [value for value in argv if value != "--fresh"])
    assert run_e023c.main() == 0
    resumed = cascade_state.load_session(state)
    assert cascade_state.authoritative_digest(resumed) == (
        cascade_state.authoritative_digest(session))


def test_production_diagnostics_are_authoritatively_neutral(
        tmp_path: Path, monkeypatch) -> None:
    import cascade_state
    import run_e023c
    from PIL import Image

    source = tmp_path / "neutral.png"
    Image.fromarray(
        np.full((128, 160), 240, np.uint8), mode="L").save(source)

    def invoke(name: str, *, diagnostics: bool) -> object:
        state = tmp_path / f"{name}.pkl"
        argv = [
            "run_e023c.py", str(source), "--dpi", "600",
            "--format", "e018b-v3-c3", "--pages", "0",
            "--capture-groups", "neutral-capture", "--ppc-levels", "3",
            "--state", str(state), "--report", str(tmp_path / f"{name}.json"),
            "--out", str(tmp_path / f"{name}.png"), "--fresh",
        ]
        if diagnostics:
            argv.extend([
                "--diag", str(tmp_path / f"{name}-diag"),
                "--diag-port", "0", "--diag-interval", "0",
                "--panel-width", "120",
            ])
        monkeypatch.setattr(sys, "argv", argv)
        assert run_e023c.main() == 0
        return cascade_state.load_session(state)

    plain = invoke("plain", diagnostics=False)
    observed = invoke("observed", diagnostics=True)
    assert cascade_state.authoritative_digest(observed) == (
        cascade_state.authoritative_digest(plain))


def _force_completion(report: dict, *, verified: bool) -> dict:
    payload = report["payload"]
    expected_sha = report["manifest"]["expected_data_sha256"]
    expected_len = report["manifest"]["expected_data_len_bytes"]
    payload.update({
        "recovered": True,
        "actual_len_bytes": expected_len,
        "length_matches": True,
        "actual_sha256": expected_sha if verified else "0" * 64,
        "sha256_matches": verified,
        "verified": verified,
    })
    fountain = report["fountain"]
    for block in fountain["blocks"]:
        block["rank"] = block["needed"]
        block["solved"] = True
    fountain["rank"] = fountain["source_symbols_needed"]
    fountain["rank_shortfall"] = 0
    fountain["solved_all"] = True
    report["status"] = "verified" if verified else "hash_mismatch"
    return report


def test_early_stop_can_resume_to_native_with_complete_and_no_images(
    tmp_path: Path, monkeypatch, manifest_path: Path,
) -> None:
    import cascade_state
    import run_e023c
    from PIL import Image

    source = tmp_path / "blank.png"
    Image.fromarray(np.full((256, 320), 240, np.uint8), mode="L").save(source)
    state = tmp_path / "state.pkl"
    real_completion = run_e023c.completion.completion_report

    def verified(certificates, manifest):
        return _force_completion(
            real_completion(certificates, manifest), verified=True)

    monkeypatch.setattr(run_e023c.completion, "completion_report", verified)
    first = [
        "run_e023c.py", str(source), "--dpi", "600",
        "--format", "e018b-v3-c3", "--pages", "0",
        "--capture-groups", "blank-capture", "--ppc-levels", "2,3",
        "--manifest", str(manifest_path), "--state", str(state),
        "--out", str(tmp_path / "early.png"), "--fresh",
    ]
    monkeypatch.setattr(sys, "argv", first)
    assert run_e023c.main() == 0
    early = cascade_state.load_session(state)
    assert early.status == "early_stopped"
    assert [row.status for row in early.captures[0].levels] == [
        "complete", "skipped_volume_verified"]

    # The persisted source path is sufficient; --complete is an execution
    # policy, not a new numerical envelope.
    second = [
        "run_e023c.py", "--dpi", "600", "--format", "e018b-v3-c3",
        "--pages", "0", "--ppc-levels", "2,3",
        "--manifest", str(manifest_path), "--state", str(state),
        "--out", str(tmp_path / "complete.png"), "--complete",
    ]
    monkeypatch.setattr(sys, "argv", second)
    assert run_e023c.main() == 0
    complete = cascade_state.load_session(state)
    assert complete.status == "exhausted"
    assert complete.captures[0].status == "exhausted"
    assert all(row.status == "complete"
               for row in complete.captures[0].levels)
    assert (tmp_path / "complete.png").is_file()


def test_recovered_volume_with_wrong_sha_is_integrity_fatal(
    tmp_path: Path, monkeypatch, manifest_path: Path,
) -> None:
    import run_e023c
    from PIL import Image

    source = tmp_path / "blank.png"
    Image.fromarray(np.full((128, 160), 240, np.uint8), mode="L").save(source)
    state = tmp_path / "state.pkl"
    real_completion = run_e023c.completion.completion_report

    def mismatch(certificates, manifest):
        return _force_completion(
            real_completion(certificates, manifest), verified=False)

    monkeypatch.setattr(run_e023c.completion, "completion_report", mismatch)
    monkeypatch.setattr(sys, "argv", [
        "run_e023c.py", str(source), "--dpi", "600",
        "--format", "e018b-v3-c3", "--pages", "0",
        "--capture-groups", "blank-capture", "--ppc-levels", "3",
        "--manifest", str(manifest_path), "--state", str(state),
        "--out", str(tmp_path / "bad.png"), "--fresh",
    ])
    assert run_e023c.main() == 2
    assert not state.exists()


def test_pilot_summary_uses_mutually_exclusive_combined_statuses(
    monkeypatch,
) -> None:
    import run_e023c

    descriptor = run_e023c.resolve_format("e018b-v3-c3")
    solved = pilotsearch.PilotTileEvidence(
        0, 0, 0, np.zeros(100, np.uint8), bch_ok=True)
    conflicted = pilotsearch.PilotTileEvidence(
        0, 0, 1, np.zeros(100, np.uint8), bch_ok=False)
    addressed = pilotsearch.PilotTileEvidence(
        0, 0, 2, np.zeros(100, np.uint8), bch_ok=None)
    combined = pilotsearch.SearchResult(tiles={
        (0, 0, 0): solved, (0, 0, 1): conflicted,
        (0, 0, 2): addressed})
    monkeypatch.setattr(
        run_e023c, "_combined_pilots",
        lambda _session, _descriptor: combined)
    session = SimpleNamespace(
        decoder_lanes={}, lane_sessions={},
        envelope=SimpleNamespace(pages=(0,)))
    summary = run_e023c._pilot_summary(session, descriptor)
    row = summary.pages[0]
    assert (row.bch_solved, row.conflicted, row.addressed) == (1, 1, 1)
    assert row.unseen + row.addressed + row.bch_solved + row.conflicted == (
        row.total)
