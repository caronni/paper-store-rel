"""Headless tests for the e018 --diag live viewer (experiments/018-confetti-
c3-play/diag.py).

Two things are proven, both without a display (the "live window" is a stdlib
web view):
  (1) the observer hook renders per-piece PNG frames to disk AND the web
      server serves the latest frame + page + status;
  (2) the WIRED driver is byte-identical with the flag off vs on — a plain
      run and a --diag run produce the same session_state.pkl (the hook is a
      read-only observer).

Reuses the failure-class render machinery in test_session_anchor.py (pieces
rendered from the composed e018 cell field). Run under PYTHONPATH=src (the
worktree editable-install gotcha).
"""
import json
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments/018-confetti-c3-play"))

import test_session_anchor as tsa          # noqa: E402  (render machinery)
from paperholo import compose, segment, tilemap  # noqa: E402
from paperholo.modulation import keystream  # noqa: E402
import diag as diag_mod                     # noqa: E402

Image.MAX_IMAGE_PIXELS = None
sd = tsa.sd


def _small_canvas():
    """A 2-piece confetti canvas (one big multi-window piece + one steeply
    rotated smaller piece) — enough to exercise placement, multi-window
    emission, the site overlay, and LDPC certification, kept small for speed."""
    gen = np.random.default_rng(4188)
    H_C, M = tsa.H_C, tsa.MARGIN_CELLS
    pcs = [
        tsa.render_piece((M + 700, M + 500, 300, 300), -9.0, gen)[0],
        tsa.render_piece((M + 300, M + 950, 150, 150), 22.0, gen)[0],
    ]
    return tsa._canvas(pcs)


def _drive(canvas, dv, pds):
    """Run the anchor chain over a canvas, calling the diag hook (or not, if
    dv is None) at the same points the driver does. Returns the piece count."""
    pieces = segment.segment_pieces(canvas, cell_px=8.0, dpi=1600.0)
    backing = segment.estimate_backing(canvas)
    pend = {0: np.ones(tuple(sd.spec.page_cells_yx), bool)}
    pim = compose.payload_index_map(sd.spec, sd.SEED)
    ks = keystream(sd.SEED, 3, 0, tuple(sd.spec.page_cells_yx))
    if dv is not None:
        dv.begin_scan("t.tiff", canvas, pieces, pds)
    for i, p in enumerate(sorted(pieces, key=lambda q: -q.area_mm2)):
        sid = f"t.tiff/p{i}"
        if dv is not None:
            dv.on_piece(p, sid, "in_progress", p.angle_deg,
                        None, None, None, pds)
        res = sd.anchor_place_piece(p, backing, pend, 1600.0, 4)
        if res is None:
            if dv is not None:
                dv.on_piece(p, sid, "failed", p.angle_deg,
                            None, None, None, pds)
            continue
        dA, bits, mcell, cllr, means, placed = res
        core = sd._core(mcell, 4)
        n_em = 0
        for j, (wy, wx, h, w, pl) in enumerate(placed):
            n_em += sd._emit_placed(
                pds, f"{sid}/w{j}", bits[wy:wy + h, wx:wx + w],
                core[wy:wy + h, wx:wx + w], cllr[wy:wy + h, wx:wx + w],
                pl, pim, ks, {"dA": dA})
        if dv is not None:
            dv.on_piece(p, sid, "placed" if n_em > 0 else "failed",
                        p.angle_deg + dA, placed, bits, core, pds)
    pds.decode_tiles("r0550", policy="weighted_sum")
    if dv is not None:
        dv.end_scan("t.tiff", pds)
    return len(pieces)


def test_diag_frames_and_web_view(tmp_path):
    canvas = _small_canvas()
    pds = tilemap.PageDecodeState(sd.spec, sd.SEED, page=0)
    dv = diag_mod.DiagViewer(tmp_path / "diag", 0, sd.spec, sd.SEED, 1600.0)
    try:
        n_pieces = _drive(canvas, dv, pds)
        assert n_pieces >= 2

        # numbered PNG frames on disk (begin + per-piece + end)
        frames = sorted((tmp_path / "diag").glob("frame_*.png"))
        assert len(frames) >= n_pieces + 2, f"too few frames: {len(frames)}"
        for f in frames:
            assert f.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

        # the web server serves the latest frame, the page, and status
        base = f"http://127.0.0.1:{dv.port}"
        png = urllib.request.urlopen(base + "/frame.png", timeout=5).read()
        assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 1000
        assert png == frames[-1].read_bytes()   # served == newest on disk
        html = urllib.request.urlopen(base + "/", timeout=5).read()
        assert b"/frame.png" in html
        st = json.loads(
            urllib.request.urlopen(base + "/status.json", timeout=5).read())
        assert st["done"] == n_pieces == st["pieces"]
        assert st["word"] + st["placed"] + st["failed"] == n_pieces
        assert st["placed"] >= 1                  # at least one piece landed
    finally:
        dv.close()


def test_driver_default_off_byte_identical(tmp_path):
    """The wired driver: a plain run and a --diag run over the same canvas
    write byte-identical session_state.pkl (the observer never touches the
    decode state) — the default-off regression guarantee."""
    canvas = _small_canvas()
    png = tmp_path / "canvas.png"
    Image.fromarray(np.clip(canvas, 0, 255).astype(np.uint8)).save(png)
    off = tmp_path / "off.pkl"
    on = tmp_path / "on.pkl"

    argv0 = sys.argv
    try:
        sys.argv = ["session_decode.py", str(png), "--dpi", "1600",
                    "--fresh", "--state", str(off)]
        assert sd.main() == 0
        sys.argv = ["session_decode.py", str(png), "--dpi", "1600",
                    "--fresh", "--state", str(on),
                    "--diag", str(tmp_path / "diag"), "--diag-port", "0"]
        assert sd.main() == 0
    finally:
        sys.argv = argv0

    assert off.read_bytes() == on.read_bytes(), \
        "diag observer perturbed the decode state"
    assert list((tmp_path / "diag").glob("frame_*.png")), \
        "the --diag run wrote no frames"


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        test_diag_frames_and_web_view(Path(d))
        print("PASS frames + web view")
    with tempfile.TemporaryDirectory() as d:
        test_driver_default_off_byte_identical(Path(d))
        print("PASS driver default-off byte-identical")
