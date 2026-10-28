"""Four-pane observer and integrated-chain tests for E023b."""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
import urllib.request
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments/023b-integrated-receiver"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(EXP))

from paperholo import (formats, payloaddec, pilotcombine, pilotdiag,  # noqa:E402
                       pilotsearch, platen, receiver, receiverdiag)
import e023b_diag  # noqa:E402
import run_e023b  # noqa:E402
import test_e023 as t23  # noqa:E402


def _one_record(tmp_path: Path):
    descriptor = t23._descriptor(b"paper-store/e023b-diag")
    rng = np.random.default_rng(2313)
    values, user, framed = t23._coded_page(descriptor, rng)
    image = t23._render_cells(values, rng)
    placements = [t23._placed_window(
        np.array(values.shape), y, x, h, w,
        origin_px=(y * t23.PITCH + t23.PITCH / 2 - 0.5,
                   x * t23.PITCH + t23.PITCH / 2 - 0.5))
        for y, x, h, w in t23._grid_windows(values.shape)[:5]]
    source = t23._scan_row(tmp_path, "s000", image, placements)
    e022 = payloaddec.load_e022_session(t23._write_state(
        tmp_path, t23._session_payload(descriptor, [source])))
    mask = np.ones(image.shape, bool)
    survey = platen.PayloadSurvey((platen.PayloadRegion(
        (0, 0, *image.shape), mask, 100.0, 0.0, 1.0),), 3, t23.PITCH)
    scan = e022.scans[0]
    record = receiver.make_scan_record(
        scan_id=scan.scan_id, source_path=scan.source_path,
        source_sha256=scan.source_sha256,
        source_size=Path(scan.source_path).stat().st_size, dpi=scan.dpi,
        image=image, capture_id=scan.source_sha256, survey=survey,
        result=scan.result, descriptor=descriptor, pages=(0,))
    return descriptor, image, survey, record, user, framed


def test_four_pane_png_and_headless_frame_persistence(tmp_path: Path) -> None:
    descriptor, image, survey, record, _user, _framed = _one_record(tmp_path)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(session, record)
    combined = pilotcombine.combine_search_results(
        [pilotcombine.SearchResultPart("s000", 1, record.result)],
        descriptor, pages=(0,), decode_words=False)
    png = receiverdiag.diagnostic_png_bytes(
        image, survey, record.result, combined, descriptor, session,
        page=0, panel_width=140)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    canvas = Image.open(__import__("io").BytesIO(png))
    assert canvas.width == 4 * 140

    viewer = e023b_diag.DiagViewer(tmp_path / "frames", 0, serve=False)
    viewer.publish({0: png}, {
        "phase": "scan_committed", "scan_id": "s000",
        "regions_done": 1, "regions": 1, "certified": 2,
        "attempts": 3})
    files = list((tmp_path / "frames").glob("frame_*_p0000.png"))
    assert len(files) == 1 and files[0].read_bytes() == png
    assert viewer._meta["pages"] == [0]
    assert viewer._meta["phase"] == "scan_committed"


def test_page_filtered_b_and_c_do_not_overlay_pages() -> None:
    descriptor = t23._descriptor(b"paper-store/e023b-pages")
    result = pilotsearch.SearchResult()
    p0 = t23._placed_window(
        np.array(descriptor.page_cells_yx), 20, 20, 60, 60,
        origin_px=(100.0, 100.0))
    p1 = replace(p0, page=1, origin_yx=(300, 300),
                 page_cells_yx=p0.page_cells_yx + np.array([280, 280]))
    result.placements = [p0, p1]
    result.tiles[(0, 0, 0)] = pilotsearch.PilotTileEvidence(
        0, 0, 0, np.zeros(100, np.uint8))
    result.tiles[(1, 1, 1)] = pilotsearch.PilotTileEvidence(
        1, 1, 1, np.zeros(100, np.uint8))
    b0 = pilotdiag.placement_panel(
        result, descriptor.spec(), width=180, page=0).tobytes()
    b1 = pilotdiag.placement_panel(
        result, descriptor.spec(), width=180, page=1).tobytes()
    c0 = pilotdiag.pilot_panel(
        result, descriptor.spec(), width=180, page=0).tobytes()
    c1 = pilotdiag.pilot_panel(
        result, descriptor.spec(), width=180, page=1).tobytes()
    assert b0 != b1
    assert c0 != c1


def test_diag_attempt_hook_does_not_change_authoritative_state(
        tmp_path: Path) -> None:
    descriptor, _image, _survey, record, _user, _framed = _one_record(tmp_path)
    plain = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    plain, _ = receiver.apply_scan(plain, record)

    observed = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    before_render = pickle.dumps(observed, protocol=pickle.HIGHEST_PROTOCOL)
    receiverdiag.ldpc_panel(observed, width=120, page=0)
    assert (pickle.dumps(observed, protocol=pickle.HIGHEST_PROTOCOL)
            == before_render)
    rendered = 0

    def hook(state, row):
        nonlocal rendered
        if len(state.attempts) == 1 or len(state.attempts) % 50 == 0:
            receiverdiag.ldpc_panel(state, width=120, page=0)
            rendered += 1

    observed, _ = receiver.apply_scan(observed, record, on_attempt=hook)
    assert rendered >= 1
    assert (receiver.authoritative_digest(observed)
            == receiver.authoritative_digest(plain))
    plain_path = tmp_path / "plain.pkl"
    observed_path = tmp_path / "observed.pkl"
    receiver.save_session(plain_path, plain)
    receiver.save_session(observed_path, observed)
    assert plain_path.read_bytes() == observed_path.read_bytes()


def test_c2_partial_edge_tile_overlay_renders_at_400px() -> None:
    descriptor = next(
        row for row in formats.FORMAT_REGISTRY
        if row.format_id == "e018b-v3-c2"
    )
    session = receiver.ReceiverSession.create(descriptor, (0,), 1200.0)
    edge = (0, 51, 34)
    progress = receiverdiag.DiagProgress(
        phase="feedback-scan60",
        tile_coverage={edge: 1.0},
        attempt_ready={edge},
        active_tiles={edge},
    )
    before = receiver.authoritative_digest(session)

    panel = receiverdiag.ldpc_panel(
        session, width=400, page=0, progress=progress)

    assert panel.width == 400
    assert receiver.authoritative_digest(session) == before


def test_full_chain_e021_e022_e023b(tmp_path: Path) -> None:
    descriptor = t23._descriptor(b"paper-store/e023b-chain")
    rng = np.random.default_rng(2314)
    values, user, framed = t23._coded_page(descriptor, rng)
    piece = values[60:420, 60:420]
    px = int(t23.PITCH)
    field = np.where(np.kron(piece, np.ones((px, px), np.uint8)) > 0,
                     t23.INK, t23.PAPER).astype(np.float32)
    canvas = np.full((field.shape[0] + 320, field.shape[1] + 320),
                     t23.BACK, np.float32)
    canvas[160:160 + field.shape[0], 160:160 + field.shape[1]] = field
    canvas = ndi.gaussian_filter(canvas, 1.1)
    canvas += rng.normal(0.0, 2.0, canvas.shape).astype(np.float32)
    canvas = np.clip(canvas, 0.0, 255.0)
    survey = platen.detect_payload_regions(canvas, dpi=1600.0)
    result = pilotsearch.search_survey(
        canvas, survey, descriptor, pages=(0,), scan_dpi=1600.0,
        config=pilotsearch.SearchConfig(bch_first=False, min_support=20),
        scan_id="s000")
    path = tmp_path / "chain.png"
    Image.fromarray(canvas.astype(np.uint8)).save(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    session = receiver.ReceiverSession.create(
        descriptor, (0,), 1600.0,
        search_config=pilotsearch.SearchConfig(
            bch_first=False, min_support=20))
    record = receiver.make_scan_record(
        scan_id="s000", source_path=path, source_sha256=sha,
        source_size=path.stat().st_size, dpi=1600.0, image=canvas,
        capture_id=sha, survey=survey, result=result,
        descriptor=descriptor, pages=(0,))
    session, _ = receiver.apply_scan(session, record)
    gt = t23._per_tile_user(user, framed)
    certified = [out for out in session.decode.tiles.values()
                 if out.state == "certified"]
    assert len(certified) >= 10
    for out in certified:
        assert np.array_equal(out.user_bits, gt[out.tile_yx])
    assert session.decode.fatal == []


def test_live_diag_serves_page_tabs_status_and_continues_frames(
        tmp_path: Path) -> None:
    import io

    def png(color):
        stream = io.BytesIO()
        Image.new("RGB", (24, 16), color).save(stream, format="PNG")
        return stream.getvalue()

    out = tmp_path / "live"
    first = e023b_diag.DiagViewer(out, 0)
    try:
        pages = {0: png((10, 20, 30)), 2: png((40, 50, 60))}
        first.publish(pages, {
            "phase": "pilot_final", "scan_id": "s000",
            "regions_done": 3, "regions": 3, "certified": 7,
            "attempts": 11})
        base = f"http://127.0.0.1:{first.port}"
        assert urllib.request.urlopen(
            base + "/frame.png?page=2", timeout=5).read() == pages[2]
        status = json.loads(urllib.request.urlopen(
            base + "/status.json", timeout=5).read())
        assert status["pages"] == [0, 2]
        assert status["phase"] == "pilot_final"
        assert b"function choose" in urllib.request.urlopen(
            base + "/", timeout=5).read()
    finally:
        first.close(grace_s=0.0)
    second = e023b_diag.DiagViewer(out, 0, serve=False)
    second.publish({0: png((70, 80, 90))}, {})
    assert (out / "frame_00002_p0000.png").exists()


def test_report_is_strictly_ldpc_and_below(tmp_path: Path) -> None:
    descriptor, _image, _survey, record, _user, _framed = _one_record(
        tmp_path)
    session = receiver.ReceiverSession.create(descriptor, (0,), 1600.0)
    session, _ = receiver.apply_scan(session, record)
    report = run_e023b.report_dict(session)
    encoded = json.dumps(report, sort_keys=True).lower()
    assert "fountain" not in encoded
    assert "raptor" not in encoded
    assert "stop_condition" not in encoded
