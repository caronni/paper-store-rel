"""E004 pre-flight (simulation before toner — gates the ONE authorized print).

Checks, in order: byte-identical regeneration (sha gates reuse), manifest
geometry (bounds, rect disjointness, 4x16 balanced class map, emission-path
separation between screened composites and clean masks), ground-truth file
integrity, gs render fidelity (pnggray pixel-exact for the clean K masks,
tiffsep separations pixel-exact for the cmyk composites — gs does not screen,
so the render must equal the addressed bitmaps exactly), and a measured-
channel simulator smoke test on a B1 tile.

Runs under pytest, or standalone: python tests/test_e004.py
"""
from __future__ import annotations

import contextlib
import pytest
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

HERE = Path(__file__).resolve().parent
EXP = HERE.parent / "experiments" / "004-finalists-checkerboard"
BUILD = EXP / "build"

# 2026-09-06: every test here reads a build that a test regenerates in place.
# One xdist worker per build directory (pyproject: --dist loadgroup).
pytestmark = pytest.mark.xdist_group("build-004")
MM_DOT = 600.0 / 25.4

Image.MAX_IMAGE_PIXELS = None
_cache: dict = {}

# 2026-09-05: the frozen stimulus shas.  The determinism test used to run
# gen_e004.py TWICE (~4.3 s each) and compare the two runs, which pins only
# run-to-run agreement inside one process; one run compared against these
# literals pins the stimulus across time, which is what the sha gate asks for.
# Regenerated and verified 2026-09-05; e004.ps also equals the manifest's own
# ps_sha256, so the two literals cross-check each other.
SHA256 = {
    "e004.ps":
        "c5c35d94c0940b82a612dc48c7721130240709cce094a3438fce790d08f9ca68",
    "e004_manifest.json":
        "ade87708bf3def753bbe2c18affc3e05b9fdc553b2cf3ec8b685f952994c60dc",
}


def _run_gen() -> None:
    subprocess.run([sys.executable, "gen_e004.py"], cwd=EXP, check=True,
                   capture_output=True)


def _sha256(name: str) -> str:
    return hashlib.sha256((BUILD / name).read_bytes()).hexdigest()


@contextlib.contextmanager
def _gen_lock(timeout: float = 600.0):
    """gen_e004.py writes into a fixed build/ directory and takes no output
    argument, so concurrent xdist workers must not generate into it at once."""
    BUILD.mkdir(parents=True, exist_ok=True)
    path = BUILD / ".gen.lock"
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() > deadline:
                raise RuntimeError(f"stale generator lock: {path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        path.unlink(missing_ok=True)


def _ensure_build() -> None:
    """Own the build every other test reads (2026-09-05): they used to read a
    BUILD that only the determinism test created, which is an ordering hazard
    on a clean tree and under -n 8.  Generates only on a sha miss."""
    if _cache.get("build_ok"):
        return
    with _gen_lock():
        if any(not (BUILD / name).exists() or _sha256(name) != sha
               for name, sha in SHA256.items()):
            _run_gen()
    _cache["build_ok"] = True


def _manifest() -> dict:
    _ensure_build()
    return json.loads((BUILD / "e004_manifest.json").read_text())


def _render_gray(dpi: int) -> np.ndarray:
    _ensure_build()
    key = ("gray", dpi)
    if key not in _cache:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "page.png"
            subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                            "-sDEVICE=pnggray", f"-r{dpi}",
                            "-o", str(out), str(BUILD / "e004.ps")],
                           check=True, capture_output=True)
            _cache[key] = np.asarray(Image.open(out).convert("L"))
    return _cache[key]


def _render_tiffsep(dpi: int = 600) -> dict[str, np.ndarray]:
    """Boolean ink maps per plane (tiffsep polarity: ink = 0/dark)."""
    _ensure_build()
    key = ("sep", dpi)
    if key not in _cache:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                            "-sDEVICE=tiffsep", f"-r{dpi}",
                            "-o", str(Path(td) / "sep_%d.tif"),
                            str(BUILD / "e004.ps")],
                           check=True, capture_output=True)
            seps = {}
            for plane, name in (("C", "Cyan"), ("M", "Magenta"),
                                ("Y", "Yellow"), ("K", "Black")):
                f = Path(td) / f"sep_1({name}).tif"
                seps[plane] = np.asarray(Image.open(f)) < 128
            _cache[key] = seps
    return _cache[key]


def _tile(mf: dict, cls: str) -> dict:
    return next(t for t in mf["tiles"] if t["class"] == cls)


def _tile_rect(mf: dict, tile: dict) -> tuple[int, int, int, int]:
    e = next(p for p in mf["patches"]
             if p.get("composite_of", p["name"]) == tile["name"])
    return e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]


def test_determinism_byte_identical() -> None:
    with _gen_lock():
        _run_gen()
        for name, sha in SHA256.items():
            assert _sha256(name) == sha, name
    _cache["build_ok"] = True


def test_geometry_balance_and_emission_separation() -> None:
    mf = _manifest()
    x0, y0, x1, y1 = [round(v * MM_DOT) for v in mf["content_bounds_mm"]]
    rects: dict[tuple, list[str]] = {}
    for e in mf["patches"] + mf["infrastructure"]:
        rx, ry, rw, rh = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
        assert x0 <= rx and rx + rw <= x1 and y0 <= ry and ry + rh <= y1, e["name"]
        rects.setdefault((rx, ry, rw, rh), []).append(e["name"])
    keys = list(rects)
    for i, a in enumerate(keys):          # distinct rects must not intersect
        for b in keys[i + 1:]:
            if not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                    or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]):
                raise AssertionError(f"overlap: {rects[a]} vs {rects[b]}")

    g = mf["grid"]
    cm = g["class_map"]
    assert all(v == 16 for v in g["per_class_tiles"].values())
    for i in range(g["n"]):
        for cls in g["classes"]:
            assert [r[i] for r in cm].count(cls) == 2
            assert cm[i].count(cls) == 2

    # emission-path separation: >= 1.5 mm between any screened-composite tile
    # and any clean-mask tile (002.2 measured region-disjointness condition)
    gap = round(1.5 * MM_DOT)
    a_rects, b_rects = [], []
    for t in mf["tiles"]:
        r = _tile_rect(mf, t)
        (a_rects if t["class"].startswith("A") else b_rects).append((t, r))
    for t, e in a_rects:
        for u, f in b_rects:
            if not (e[0] + e[2] + gap <= f[0] or f[0] + f[2] + gap <= e[0]
                    or e[1] + e[3] + gap <= f[1] or f[1] + f[3] + gap <= e[1]):
                raise AssertionError(f"{t['name']} within 1.5mm of {u['name']}")
    for t, _ in a_rects:                 # A tiles must be cmyk_image emission
        for p in mf["patches"]:
            if p.get("composite_of") == t["name"]:
                assert p["params"]["emission"] == "cmyk_image", p["name"]
    for t, _ in b_rects:                 # B tiles: single K imagemask
        e = next(p for p in mf["patches"] if p["name"] == t["name"])
        assert e["planes"] == ["K"], e["name"]


def test_gt_files_load_and_match() -> None:
    mf = _manifest()
    seen: dict[str, str] = {}
    for e in mf["patches"]:
        if e["gt"] is None:
            continue
        assert seen.setdefault(e["gt"], e["name"]) == e["name"]
        gt = np.load(BUILD / e["gt"])
        assert gt.shape == (e["h_dots"], e["w_dots"]), e["name"]
    for t in mf["tiles"]:                # state GTs match the cell grid
        if not t["class"].startswith("A"):
            continue
        e = next(p for p in mf["patches"] if p.get("composite_of") == t["name"])
        cell = e["params"]["cell_dots"]
        st = np.load(BUILD / e["params"]["states_gt"])
        assert st.shape == (e["h_dots"] // cell, e["w_dots"] // cell), t["name"]
        assert st.max() < e["params"]["n_states"]


def test_gs_gt_fidelity_clean_masks() -> None:
    mf = _manifest()
    img = _render_gray(600)
    for cls in ("B1", "B2"):
        t = _tile(mf, cls)
        e = next(p for p in mf["patches"] if p["name"] == t["name"])
        x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
        gt = np.load(BUILD / e["gt"])
        crop = (img[y: y + h, x: x + w] < 128).astype(np.uint8)
        assert np.array_equal(crop, gt), \
            f"{t['name']}: {int((crop != gt).sum())}/{gt.size} px differ"


def test_gs_gt_fidelity_cmyk_composites() -> None:
    mf = _manifest()
    seps = _render_tiffsep(600)
    for cls in ("A3", "A4"):
        t = _tile(mf, cls)
        for p in mf["patches"]:
            if p.get("composite_of") != t["name"]:
                continue
            plane = p["planes"][0]
            x, y, w, h = p["x_dots"], p["y_dots"], p["w_dots"], p["h_dots"]
            gt = np.load(BUILD / p["gt"]).astype(bool)
            crop = seps[plane][y: y + h, x: x + w]
            assert np.array_equal(crop, gt), \
                f"{p['name']}: {int((crop != gt).sum())}/{gt.size} px differ"


def test_sim_smoke_b1_tile() -> None:
    """Measured-channel simulator round-trip on one B1 tile: naive hard c2
    decode must beat the 0.5 null decisively (plumbing check, not physics —
    the sim's c2 regime is dev-morphology-dominated by construction)."""
    from paperholo.channel import ChannelParams, print_scan
    from paperholo.metrics import ber
    from paperholo.modulation import dots_to_cells_hard

    mf = _manifest()
    t = _tile(mf, "B1")
    e = next(p for p in mf["patches"] if p["name"] == t["name"])
    bits = np.load(BUILD / e["gt"])
    p = ChannelParams(seed=11, geometry=False)
    scan = print_scan(bits, p)
    rx = dots_to_cells_hard(scan, 2 * p.scan_oversample)
    gt_cells = bits[::2, ::2]
    err = ber(gt_cells, rx)
    print(f"  B1 sim naive hard BER = {err:.4f}")
    assert 0.005 < err < 0.30, err


if __name__ == "__main__":
    fns = [test_determinism_byte_identical,
           test_geometry_balance_and_emission_separation,
           test_gt_files_load_and_match,
           test_gs_gt_fidelity_clean_masks,
           test_gs_gt_fidelity_cmyk_composites,
           test_sim_smoke_b1_tile]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
