"""Observer, scale-event, and four-pane pins for fresh E023c diagnostics."""
from __future__ import annotations

import io
import json
import pickle
import sys
import urllib.request
from pathlib import Path

import pytest
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023c-scale-space-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

import e023c_diag  # noqa: E402
from paperholo import formats, pilotdiag, pilotsearch, platen  # noqa: E402


def _encoded_image(
    color: tuple[int, int, int],
    size: tuple[int, int] = (32, 20),
    *,
    format: str = "PNG",
) -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", size, color).save(stream, format=format)
    return stream.getvalue()


def _panes(tmp_path: Path):
    path = tmp_path / "pane-c.jpg"
    path.write_bytes(_encoded_image((70, 80, 90), (20, 32), format="JPEG"))
    return {
        "A": Image.new("RGB", (28, 20), (10, 20, 30)),
        "B": _encoded_image((40, 50, 60), (16, 20)),
        "C": path,
        "D": None,
    }


def test_four_pane_accepts_pil_bytes_path_and_none_deterministically(
    tmp_path: Path,
) -> None:
    panes = _panes(tmp_path)
    before = panes["A"].tobytes()
    first = e023c_diag.diagnostic_png_bytes(panes, panel_width=100)
    second = e023c_diag.diagnostic_png_bytes(panes, panel_width=100)
    assert first == second
    assert first.startswith(e023c_diag.PNG_SIGNATURE)
    with Image.open(io.BytesIO(first)) as canvas:
        assert canvas.mode == "RGB"
        assert canvas.width == 400
        # The portrait path-backed pane determines body height; a title band
        # is added above it without cropping any pane.
        assert canvas.height > 160
    assert panes["A"].tobytes() == before


def test_publish_detaches_images_metadata_and_persists_scale_event(
    tmp_path: Path,
) -> None:
    out = tmp_path / "frames"
    viewer = e023c_diag.DiagViewer(
        out, 0, serve=False, panel_width=80)
    image = Image.new("RGB", (30, 20), (7, 8, 9))
    meta = {
        "capture_id": "capture-a",
        "level_index": 0,
        "levels_total": 3,
        "ppc": 2.0,
        "effective_dpi": 400.0,
        "regions_done": 1,
        "regions": 2,
        "pilots_solved": 91,
        "certified": 17,
        "attempts": 23,
        "scale_ladder": [
            {"ppc": 2.0, "status": "active"},
            {"ppc": 3.0, "status": "pending"},
            {"ppc": 6.0, "status": "pending"},
        ],
    }
    assert viewer.publish_event(
        "pilot_level_final", {0: image, 2: _panes(tmp_path)}, meta)

    # Mutating caller-owned objects after publication cannot alter the viewer.
    image.paste((255, 0, 0), (0, 0, image.width, image.height))
    meta["scale_ladder"][0]["status"] = "tampered"
    status = viewer.status()
    assert status["event"] == status["phase"] == "pilot_level_final"
    assert status["pages"] == [0, 2]
    assert status["scale_ladder"][0]["status"] == "active"
    assert status["frame"] == 1
    assert viewer.latest(0).startswith(e023c_diag.PNG_SIGNATURE)

    page_files = sorted(out.glob("frame_00001_p*.png"))
    assert [path.name for path in page_files] == [
        "frame_00001_p0000.png", "frame_00001_p0002.png"]
    sidecar = json.loads((out / "frame_00001.json").read_text())
    assert sidecar == status


def test_frames_continue_across_headless_invocations(tmp_path: Path) -> None:
    out = tmp_path / "frames"
    page = Image.new("RGB", (12, 8), (1, 2, 3))
    first = e023c_diag.DiagViewer(out, 0, serve=False)
    assert first.publish({0: page}, {"event": "level_open"})
    first.close()

    second = e023c_diag.DiagViewer(out, 0, serve=False)
    assert second.status()["frame"] == 1
    assert second.publish(
        {0: page}, {"level_index": 1}, event="level_complete")
    assert second.status()["frame"] == 2
    assert (out / "frame_00002_p0000.png").exists()
    assert (out / "frame_00002.json").exists()


def test_status_only_update_detaches_without_advancing_frame_or_disk(
    tmp_path: Path,
) -> None:
    out = tmp_path / "status"
    viewer = e023c_diag.DiagViewer(out, 0, serve=False)
    pages = {
        0: Image.new("RGB", (12, 8), (10, 20, 30)),
        2: Image.new("RGB", (12, 8), (40, 50, 60)),
    }
    assert viewer.publish(
        pages, {"detail": "level opened"}, event="level_open")
    latest = {page: viewer.latest(page) for page in pages}
    sidecars = sorted(out.glob("frame_*.json"))
    page_files = sorted(out.glob("frame_*_p*.png"))
    assert len(sidecars) == 1
    rendered_sidecar = sidecars[0].read_bytes()

    meta = {
        "detail": "window 3/9 · pose_fitted · angle -2.125°",
        "window": {
            "ordinal": 3,
            "stage": "pose_fitted",
            "pose": {"angle_deg": -2.125, "pitch_px": 4.01},
        },
        # Status-only updates cannot take ownership of frame/page identity.
        "frame": 999,
        "pages": [999],
    }
    assert viewer.update_status(meta, event=" e022_window_progress ")
    meta["detail"] = "mutated"
    meta["window"]["pose"]["angle_deg"] = 99.0

    status = viewer.status()
    assert status["event"] == status["phase"] == "e022_window_progress"
    assert status["detail"] == (
        "window 3/9 · pose_fitted · angle -2.125°")
    assert status["window"]["pose"] == {
        "angle_deg": -2.125, "pitch_px": 4.01}
    assert status["frame"] == 1
    assert status["pages"] == [0, 2]
    assert {page: viewer.latest(page) for page in pages} == latest
    assert sorted(out.glob("frame_*.json")) == sidecars
    assert sorted(out.glob("frame_*_p*.png")) == page_files
    assert sidecars[0].read_bytes() == rendered_sidecar

    # A new causal event cannot inherit a stale active-window record.
    assert viewer.update_status(
        {"detail": "region complete"}, event="e022_region_complete")
    cleared = viewer.status()
    assert cleared["window"] is None
    assert cleared["ldpc"] is None
    assert cleared["context"] is None
    assert cleared["pose_refine"] is None
    viewer.close()


def test_progress_throttle_first_interval_boundary_and_force() -> None:
    times = iter((100.0, 101.0, 102.0, 103.0, 104.0, 106.0, 107.0))
    throttle = e023c_diag.ProgressThrottle(
        3.0, clock=lambda: next(times))

    assert throttle.allow()                    # first event always renders
    assert not throttle.allow()                # one second after render
    assert not throttle.allow()                # two seconds after render
    assert throttle.allow()                    # exact interval boundary
    assert throttle.allow(force=True)          # force also resets the clock
    assert not throttle.allow()                # two seconds after force
    assert throttle.allow()                    # exact interval after force

    with pytest.raises(ValueError, match="non-negative"):
        e023c_diag.ProgressThrottle(-0.01)


def test_progress_throttle_interval_starts_after_slow_render() -> None:
    now = [10.0]
    throttle = e023c_diag.ProgressThrottle(3.0, clock=lambda: now[0])
    assert throttle.allow()
    # The render itself takes longer than the interval. Completion becomes
    # the new anchor, preventing an immediate render on the next callback.
    now[0] = 18.0
    throttle.mark_rendered()
    now[0] = 18.1
    assert not throttle.allow()
    now[0] = 21.0
    assert throttle.allow()


def test_window_pose_and_candidate_overlays_are_visual_and_read_only() -> None:
    descriptor = next(
        row for row in formats.FORMAT_REGISTRY
        if row.format_id == "e018b-v3-c2")
    image = np.tile(np.arange(160, dtype=np.uint8), (120, 1))
    region = platen.PayloadRegion(
        (10, 15, 80, 120), np.ones((80, 120), bool),
        100.0, 0.0, 4.0)
    survey = platen.PayloadSurvey((region,), 2, 4.0)
    result = pilotsearch.SearchResult()
    before = pickle.dumps(result)
    progress = {
        "ordinal": 7, "queue_total": 20, "depth": 0,
        "stage": "refine", "scan_bbox_yxhw_px": (20, 30, 60, 80),
        "pose_origin_yx": (32.0, 42.0),
        "jacobian_yx": ((4.0, 0.2), (-0.1, 4.0)),
        "window_shape_yx_cells": (80, 90),
        "placement_page": 0, "placement_origin_yx": (1000, 1200),
        "placement_rot_k": 1, "method": "lower_chain",
    }

    scan = pilotdiag.scan_panel(
        image, survey, result, width=320, active_region=0,
        window_progress=progress)
    scan_pixels = np.asarray(scan)
    assert np.any(np.all(scan_pixels == (20, 225, 235), axis=2))
    assert np.any(np.all(scan_pixels == (255, 90, 185), axis=2))
    assert np.any(np.all(scan_pixels == (80, 245, 125), axis=2))

    placement = pilotdiag.placement_panel(
        result, descriptor.spec(), width=320, page=0,
        window_progress=progress)
    assert np.any(np.all(
        np.asarray(placement) == (190, 45, 230), axis=2))
    assert pickle.dumps(result) == before


def test_render_or_metadata_failure_disables_only_observer(
    tmp_path: Path,
) -> None:
    authoritative = {"generation": 4, "certificates": [1, 2, 3]}
    before = json.dumps(authoritative, sort_keys=True)
    viewer = e023c_diag.DiagViewer(tmp_path / "bad", 0, serve=False)

    # An authoritative object is deliberately not a valid JSON status value.
    # Publication contains the failure and never retains or mutates it.
    assert not viewer.publish(
        {0: Image.new("RGB", (8, 8))},
        {"receiver_state": object()},
        event="level_complete",
    )
    assert viewer.broken
    assert json.dumps(authoritative, sort_keys=True) == before
    assert viewer.status()["frame"] == 0
    assert not list((tmp_path / "bad").glob("frame_*"))

    # Once isolated, even malformed rendered bytes are harmless no-ops.
    assert not viewer.publish({0: b"not an image"}, {})
    assert viewer.status()["frame"] == 0


def test_filesystem_failure_disables_only_disk_and_keeps_live_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    viewer = e023c_diag.DiagViewer(tmp_path / "io", 0, serve=False)
    calls = 0

    def fail_write(_path, _payload):
        nonlocal calls
        calls += 1
        raise OSError("diagnostic disk unavailable")

    monkeypatch.setattr(e023c_diag, "_atomic_write", fail_write)
    assert viewer.publish(
        {0: Image.new("RGB", (8, 8))},
        {"certified": 999},
        event="ldpc_batch",
    )
    assert calls == 1
    assert not viewer.broken
    assert not viewer.disk_enabled
    assert viewer.status()["certified"] == 999
    assert viewer.status()["frame"] == 1
    assert viewer.latest(0).startswith(e023c_diag.PNG_SIGNATURE)


def test_optional_localhost_server_has_page_tabs_scale_status_and_fallback(
    tmp_path: Path,
) -> None:
    viewer = e023c_diag.DiagViewer(
        tmp_path / "live", 0, panel_width=64)
    if not viewer.server_enabled:
        pytest.skip("sandbox does not permit a localhost diagnostic socket")
    try:
        pages = {
            1: Image.new("RGB", (18, 12), (20, 30, 40)),
            3: Image.new("RGB", (18, 12), (50, 60, 70)),
        }
        assert viewer.publish(pages, {
            "capture_id": "capture-b",
            "level_index": 1,
            "levels_total": 3,
            "ppc": 3.0,
            "effective_dpi": 600.0,
            "scale_ladder": [
                {"ppc": 2.0, "status": "complete"},
                {"ppc": 3.0, "status": "active"},
                {"ppc": 6.0, "status": "pending"},
            ],
        }, event="e022_region_complete")
        base = f"http://127.0.0.1:{viewer.port}"
        status = json.loads(urllib.request.urlopen(
            base + "/status.json", timeout=5).read())
        assert status["pages"] == [1, 3]
        assert status["event"] == "e022_region_complete"
        assert status["ppc"] == 3.0
        assert status["scale_ladder"][1]["status"] == "active"
        assert urllib.request.urlopen(
            base + "/frame.png?page=3", timeout=5).read() == viewer.latest(3)
        # An invalid/missing page request falls back to the first legal tab.
        assert urllib.request.urlopen(
            base + "/frame.png?page=bad", timeout=5).read() == viewer.latest(1)
        html = urllib.request.urlopen(base + "/", timeout=5).read()
        assert b"scale-space receiver" in html
        assert b"replaceChildren" in html  # page-tab implementation
        assert b"scale_ladder" in html
    finally:
        viewer.close(grace_s=0.0)
        viewer.close(grace_s=0.0)


def test_registered_scale_events_cover_level_and_completion_barriers() -> None:
    required = {
        "capture_open", "level_open", "e021_complete",
        "e022_window_progress", "e022_region_complete",
        "pilot_level_final", "context_region_complete",
        "pose_refine_window_progress", "payload_region_emitted",
        "level_owner_frozen", "ldpc_attempt", "bp_retry_attempt",
        "bp_retry_complete", "ldpc_batch", "level_complete",
        "fountain_check", "capture_committed", "session_complete",
    }
    assert required <= set(e023c_diag.SCALE_EVENTS)
