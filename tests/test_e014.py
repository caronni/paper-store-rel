"""e014 preflight — the c2 archive pilot sheet (layout_version 3, ARCH-2).

Gates the office print: determinism, golden sha (the c2-page format
anchor — if it fails you changed the printed format: bump, never edit),
manifest geometry, payload bijection, gs pixel-exact render, pilot overlay
spot-check, and a GT-scored channel-sanity sim smoke (genie footing —
BLIND decode of c2 pages is deliberately deferred, see gen_e014 docstring).
"""
from __future__ import annotations

import hashlib
import pytest
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "014-c2-print"
BUILD = EXP / "build"

# 2026-09-06: every test here reads a build that a test regenerates in place.
# One xdist worker per build directory (pyproject: --dist loadgroup).
pytestmark = pytest.mark.xdist_group("build-014")
sys.path.insert(0, str(EXP))

from paperholo import compose, pilots  # noqa: E402
from paperholo.channel import ChannelParams, print_scan  # noqa: E402
from paperholo.modulation import rng  # noqa: E402

import gen_e014  # noqa: E402

Image.MAX_IMAGE_PIXELS = None

# layout_version-3 kcell-c2 page golden anchor (bump-don't-edit).
E014_PS_SHA256 = "eb2f8cbfb1c9f208472c52eeac30230bcfb9cea7481b722dfba9b93505fde153"

_cache: dict = {}


def _generate() -> tuple[bytes, dict]:
    subprocess.run([sys.executable, "gen_e014.py"], cwd=EXP, check=True,
                   capture_output=True, timeout=300)
    return (BUILD / "e014.ps").read_bytes(), json.loads(
        (BUILD / "e014_manifest.json").read_text())


def _built() -> tuple[bytes, dict]:
    if "built" not in _cache:
        _cache["built"] = _generate()
    return _cache["built"]


def _render() -> np.ndarray:
    if "render" not in _cache:
        _built()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "e014.png"
            subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                            "-sDEVICE=pnggray", "-r600",
                            "-o", str(out), str(BUILD / "e014.ps")],
                           check=True, capture_output=True, timeout=600)
            _cache["render"] = np.asarray(Image.open(out).convert("L"))
    return _cache["render"]


def test_determinism_and_golden_sha():
    ps1, mf1 = _built()
    ps2, mf2 = _generate()
    assert ps1 == ps2, "e014.ps must regenerate byte-identically"
    assert mf1["ps_sha256"] == mf2["ps_sha256"]
    got = hashlib.sha256(ps1).hexdigest()
    assert got == mf1["ps_sha256"] == E014_PS_SHA256, (
        f"format anchor broken: {got} != {E014_PS_SHA256} — the printed "
        "c2 format changed; bump the format entry, never edit the anchor")


def test_manifest_geometry():
    _, mf = _built()
    assert mf["layout_version"] == 3
    f = mf["patches"][0]
    assert f["params"]["encoding_id"] == "kcell-c2"
    assert f["params"]["cell_dots"] == 2
    assert f["params"]["pilot_layout"] == "p60b6.v3-k18"
    assert f["params"]["counter_tiles_x"] == 37
    assert f["params"]["counter_tiles_per_page"] == 2035
    assert (f["h_dots"], f["w_dots"]) == (6600, 4440)
    # >= 6 mm content margins on A4 (4960 x 7016 dots)
    margins = (f["x_dots"], 4960 - f["x_dots"] - f["w_dots"],
               f["y_dots"], 7016 - f["y_dots"] - f["h_dots"])
    assert min(margins) * 25.4 / 600.0 >= 6.0, margins


def test_capacity_and_bijection():
    spec = gen_e014.make_spec()
    cap = compose.payload_capacity(spec)
    assert cap == 3300 * 2220 - 2035 * 100 == 7_122_500
    payload = rng(gen_e014.SEED, b"e014/payload").integers(
        0, 2, size=cap, dtype=np.uint8)
    page = compose.compose_page(payload, spec, gen_e014.SEED, page=0)
    back = compose.extract_payload(page.cell_values, spec, gen_e014.SEED, 0)
    assert np.array_equal(back, payload)
    assert page.plane_bits.shape == (6600, 4440)


def test_gs_render_pixel_exact():
    _, mf = _built()
    img = _render()
    f = mf["patches"][0]
    y, x, h, w = f["y_dots"], f["x_dots"], f["h_dots"], f["w_dots"]
    ink = (img[y:y + h, x:x + w] < 128).astype(np.uint8)
    gt = np.load(BUILD / f["gt"]) if isinstance(f.get("gt"), str) and \
        (BUILD / f["gt"]).exists() else None
    if gt is None:  # GT path relative to manifest dir
        gt = np.load((BUILD / "e014_gt" / "K__e014_field.npy"))
    assert ink.shape == gt.shape
    diff = int((ink != gt).sum())
    assert diff == 0, f"{diff} differing dots — RIP not bit-exact"
    outside = img.copy()
    outside[y:y + h, x:x + w] = 255
    assert (outside < 128).sum() == 0, "ink outside the field rect"


def test_pilot_overlay_spot_check():
    """Expected v3 word bits appear as 2x2-dot cells in the render."""
    _, mf = _built()
    img = _render()
    f = mf["patches"][0]
    spec = gen_e014.make_spec()
    lay = spec.pilot
    pos = pilots.site_positions_tile(lay, gen_e014.SEED)
    for ty, tx in ((0, 0), (27, 18), (54, 36)):
        word = pilots.encode_word(lay, gen_e014.SEED, "K", 0, ty, tx,
                                  tiles_x=37, tiles_per_page=2035)
        for s in (0, 41, 99):
            cy = ty * 60 + int(pos[s, 0])
            cx = tx * 60 + int(pos[s, 1])
            y0 = f["y_dots"] + cy * 2
            x0 = f["x_dots"] + cx * 2
            cell_ink = (img[y0:y0 + 2, x0:x0 + 2] < 128).mean()
            assert (cell_ink > 0.5) == bool(word[s]), (ty, tx, s)


def test_sim_channel_sanity_genie_footing():
    """GT-scored genie-grid smoke (blind decode deferred by user decision):
    c2 sim regime is the known-conservative model (sim ~15% vs hw 11.1%)."""
    spec = gen_e014.make_spec()
    payload = rng(gen_e014.SEED, b"e014/payload").integers(
        0, 2, size=compose.payload_capacity(spec), dtype=np.uint8)
    page = compose.compose_page(payload, spec, gen_e014.SEED, page=0)
    win_cells = 240
    y0c, x0c = 900, 600
    win = page.plane_bits[y0c * 2:(y0c + win_cells) * 2,
                          x0c * 2:(x0c + win_cells) * 2]
    scan = print_scan(win, ChannelParams(seed=3, geometry=False))
    # aligned block means at 4 px/cell, median threshold (scramble => ~50%)
    m = scan.reshape(win_cells, 4, win_cells, 4).mean(axis=(1, 3))
    bits = (m < np.median(m)).astype(np.uint8)
    gt = page.cell_values[y0c:y0c + win_cells, x0c:x0c + win_cells]
    ber = float((bits != gt).mean())
    null = float((bits != np.roll(gt, 7, axis=0)).mean())
    print(f"e014 c2 sim smoke: BER {ber:.3f}, null {null:.3f}")
    assert 0.02 < ber < 0.30, ber      # c2 sim regime, loose envelope
    assert abs(null - 0.5) < 0.03, null


if __name__ == "__main__":
    for t in (test_determinism_and_golden_sha, test_manifest_geometry,
              test_capacity_and_bijection, test_gs_render_pixel_exact,
              test_pilot_overlay_spot_check,
              test_sim_channel_sanity_genie_footing):
        t()
        print(f"PASS {t.__name__}")
