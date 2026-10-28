"""Persistent state, cross-scan provenance, and live diagnostics for E022."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / "experiments/022-pilot-tile-search"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from paperholo import pilotsearch  # noqa: E402
import e022_diag  # noqa: E402
import run_e022  # noqa: E402
import session_e022  # noqa: E402


def _result(scan_id: str, bit: int) -> pilotsearch.SearchResult:
    pose = pilotsearch.AffinePose(
        origin_yx=(10.0, 20.0),
        jacobian_yx=((8.0, 0.0), (0.0, 8.0)),
        angle_deg=0.0, pitch_px=8.0, phase_yx=(0.0, 0.0),
        footing_factor=3,
    )
    placed = pilotsearch.PlacedWindow(
        region_index=0,
        window=pilotsearch.Window(0, 0, 60, 60, 3600),
        page=0, origin_yx=(0, 0), rot_k=0, method="correlation",
        mismatch=0.05, validation_mismatch=0.04, rival_mismatch=0.30,
        support=100, pose=pose, elapsed_s=0.1, scan_id=scan_id,
        page_cells_yx=np.array([[0, 0], [1, 1]], np.int32),
    )
    observation = pilotsearch.PilotObservation(
        region_index=0, window_yx=(0, 0), scan_yx=(10.0, 20.0),
        bit=bit, expected=bit, weight=1.0, method="correlation",
        scan_id=scan_id,
    )
    tile = pilotsearch.PilotTileEvidence(
        page=0, tile_y=0, tile_x=0,
        expected_bits=np.zeros(100, np.uint8),
        observations={0: [observation]},
    )
    return pilotsearch.SearchResult(
        placements=[placed], tiles={(0, 0, 0): tile},
        region_states={0: "accepted"}, timings={"total_s": 1.0},
        diagnostics={"scan_id": scan_id},
    )


def _scan(scan_id: str, sha: str, bit: int) -> session_e022.SessionScan:
    return session_e022.SessionScan(
        scan_id=scan_id, source_path=f"/scan/{scan_id}.tiff",
        source_sha256=sha, source_size=123, dpi=4800.0,
        region_count=1, c_dots=3, cell_pitch_px=24.0,
        angle_hints=1, result=_result(scan_id, bit),
    )


def test_state_roundtrip_and_cross_scan_union(tmp_path: Path) -> None:
    descriptor = run_e022.E018
    session = session_e022._new_session(descriptor, (0,), 4800.0)
    session.scans.extend([
        _scan("s000", "a" * 64, 0),
        _scan("s001", "b" * 64, 1),
    ])
    state_path = tmp_path / "session.pkl"
    session_e022.save_session(state_path, session)
    loaded = session_e022.load_session(
        state_path, descriptor, (0,), 4800.0
    )
    assert [scan.scan_id for scan in loaded.scans] == ["s000", "s001"]
    assert state_path.with_suffix(".pkl.tmp").exists() is False

    combined = session_e022.combine_results(loaded, descriptor)
    assert [row.scan_id for row in combined.placements] == ["s000", "s001"]
    assert [row.region_index for row in combined.placements] == [0, 1]
    observations = combined.tiles[(0, 0, 0)].observations[0]
    assert {row.scan_id for row in observations} == {"s000", "s001"}
    assert {row.region_index for row in observations} == {0, 1}
    assert combined.diagnostics["scan_count"] == 2

    report_path = tmp_path / "session.json"
    session_e022.save_report(
        report_path, session_e022.session_report(loaded, descriptor, combined)
    )
    report = json.loads(report_path.read_text())
    assert len(report["scans"]) == 2
    assert len(report["combined"]["placements"]) == 2


def test_state_rejects_dpi_or_format_mismatch(tmp_path: Path) -> None:
    descriptor = run_e022.E018
    state_path = tmp_path / "session.pkl"
    session_e022.save_session(
        state_path, session_e022._new_session(descriptor, (0,), 4800.0)
    )
    try:
        session_e022.load_session(state_path, descriptor, (0,), 1600.0)
    except ValueError as exc:
        assert "mismatch" in str(exc)
    else:
        raise AssertionError("mixed-DPI state was accepted")


def test_live_view_serves_latest_frame_and_continues_numbering(
    tmp_path: Path,
) -> None:
    out = tmp_path / "diag"
    first = e022_diag.DiagViewer(out, 0)
    try:
        png = _png_bytes((40, 90, 150))
        first.publish(png, {
            "scan": "one.tiff", "scan_id": "s000", "scans": 1,
            "regions_done": 1, "regions": 2, "placements": 3,
            "tiles": 4, "bch_matching": 1, "bch_contradictory": 0,
            "bch_refused": 2,
        })
        base = f"http://127.0.0.1:{first.port}"
        assert urllib.request.urlopen(base + "/frame.png", timeout=5).read() == png
        html = urllib.request.urlopen(base + "/", timeout=5).read()
        assert b"/frame.png" in html
        status = json.loads(urllib.request.urlopen(
            base + "/status.json", timeout=5
        ).read())
        assert status["frame"] == 1 and status["tiles"] == 4
    finally:
        first.close(grace_s=0.0)

    second = e022_diag.DiagViewer(out, 0)
    try:
        second.publish(_png_bytes((100, 40, 40)), {})
    finally:
        second.close(grace_s=0.0)
    assert (out / "frame_00002.png").exists()


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    import io

    stream = io.BytesIO()
    Image.new("RGB", (80, 50), color).save(stream, format="PNG")
    return stream.getvalue()
