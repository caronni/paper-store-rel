"""Headless tests for e023 ``--diag`` (experiments/023-payload-tiles/e023_diag.py).

Proves:
  (1) the observer renders PNG frames to disk AND the web server serves the
      latest frame + status JSON;
  (2) ``payloaddec.run_session`` is byte-identical with the diag hook off vs
      on — the hook is a read-only observer.

Run under PYTHONPATH=src.
"""
from __future__ import annotations

import json
import pickle
import sys
import urllib.request
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/022-pilot-tile-search"))
sys.path.insert(0, str(ROOT / "experiments/023-payload-tiles"))

from paperholo import payloaddec  # noqa: E402
import e023_diag  # noqa: E402
import run_e023  # noqa: E402
import session_e022  # noqa: E402
import test_e023 as t23  # noqa: E402


def _synthetic_session(tmp_path: Path):
    descriptor = t23._descriptor(b"paper-store/e023-diag")
    rng = np.random.default_rng(4230)
    values, user, framed = t23._coded_page(descriptor, rng)
    image = t23._render_cells(values, rng)
    placements = [
        t23._placed_window(np.array(values.shape), y, x, h, w,
                           origin_px=(y * t23.PITCH + t23.PITCH / 2 - 0.5,
                                      x * t23.PITCH + t23.PITCH / 2 - 0.5))
        for (y, x, h, w) in t23._grid_windows(values.shape, span=120,
                                              stride=100)[:6]
    ]
    payload = t23._session_payload(
        descriptor, [t23._scan_row(tmp_path, "s000", image, placements)])
    session = payloaddec.load_e022_session(t23._write_state(tmp_path, payload))
    return descriptor, session, user, framed


def _state_payload(path: Path) -> dict:
    return pickle.loads(path.read_bytes())


def test_diag_viewer_serves_frame_and_status(tmp_path: Path) -> None:
    descriptor, session, _user, _framed = _synthetic_session(tmp_path)
    state = payloaddec.run_session(session, descriptor)
    e022_view = run_e023._as_e022_session_obj(session)
    combined = session_e022.combine_results(
        e022_view, descriptor, decode_words=False)

    viewer = e023_diag.DiagViewer(tmp_path / "frames", port=0)
    try:
        png = run_e023.diagnostic_png_bytes(state, combined, descriptor)
        viewer.publish(png, run_e023.diag_meta(
            state, step="s000", scans_done=1, scans_total=1))
        assert list((tmp_path / "frames").glob("frame_*.png"))
        with urllib.request.urlopen(
                f"http://127.0.0.1:{viewer.port}/frame.png", timeout=5) as resp:
            served = resp.read()
        assert served[:8] == b"\x89PNG\r\n\x1a\n"
        with urllib.request.urlopen(
                f"http://127.0.0.1:{viewer.port}/status.json", timeout=5) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
        assert meta["certified"] >= 1
        assert meta["step"] == "s000"
    finally:
        viewer.close(grace_s=0.0)


def _tile_rows(payload: dict) -> dict:
    """Normalize tile dict for equality (user_bits are packed uint8)."""
    out = {}
    for key, row in payload["tiles"].items():
        out[key] = {
            "state": row["state"],
            "certified_by": row["certified_by"],
            "k_eff": row["k_eff"],
            "n_informative_best": row["n_informative_best"],
            "n_nonshort": row["n_nonshort"],
            "n_iters": row["n_iters"],
            "attempts": row["attempts"],
            "n_user_bits": row["n_user_bits"],
            "user_bits": (None if row["user_bits"] is None
                          else bytes(np.asarray(row["user_bits"], np.uint8))),
        }
    return out


def test_run_session_byte_identical_with_diag_hook(tmp_path: Path) -> None:
    descriptor, session, _user, _framed = _synthetic_session(tmp_path)
    e022_view = run_e023._as_e022_session_obj(session)
    combined = session_e022.combine_results(
        e022_view, descriptor, decode_words=False)

    plain = tmp_path / "plain.pkl"
    hooked = tmp_path / "hooked.pkl"
    viewer = e023_diag.DiagViewer(tmp_path / "diag", port=0)

    def publish(st, scan_id, counts, elapsed):
        png = run_e023.diagnostic_png_bytes(st, combined, descriptor)
        viewer.publish(png, run_e023.diag_meta(
            st, step=scan_id, scans_done=1, scans_total=1))

    try:
        st_plain = payloaddec.run_session(session, descriptor)
        payloaddec.save_state(plain, st_plain)
        st_hook = payloaddec.run_session(session, descriptor, on_scan=publish)
        payloaddec.save_state(hooked, st_hook)
    finally:
        viewer.close(grace_s=0.0)

    # observer must not change decode outcomes
    p_plain = _state_payload(plain)
    p_hook = _state_payload(hooked)
    st_plain = payloaddec.load_state(plain, descriptor)
    st_hook = payloaddec.load_state(hooked, descriptor)
    assert _tile_rows(p_plain) == _tile_rows(p_hook)
    assert p_plain["n_attempts"] == p_hook["n_attempts"]
    assert st_plain.summary() == st_hook.summary()
