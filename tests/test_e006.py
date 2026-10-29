"""E006 pre-flight (simulation before toner — gates the TWO authorized prints).

Checks, in order: byte-identical regeneration of both pages (sha gates
reuse), manifest geometry (bounds, rect disjointness with composite_of rects
shared, band skeleton on the 360-dot pitch, emission-path split: BW payloads
single-K masks, C payloads cmyk composites), ground-truth file integrity,
gs render fidelity (pnggray pixel-exact for the BW clean masks incl. sync
strips and every probe patch, tiffsep separations pixel-exact for one A3
band — gs does not screen, so the render must equal the addressed bitmaps
exactly), and a measured-channel simulator smoke test on the canary B1 patch.

Runs under pytest, or standalone: python tests/test_e006.py
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
EXP = HERE.parent / "experiments" / "006-loop-pages"
BUILD = EXP / "build"

# 2026-09-06: every test here reads a build that a test regenerates in place.
# One xdist worker per build directory (pyproject: --dist loadgroup).
pytestmark = pytest.mark.xdist_group("build-006")
MM_DOT = 600.0 / 25.4
PAGES = ("bw", "c")

Image.MAX_IMAGE_PIXELS = None
_cache: dict = {}

BW_MASK_CHECKS = ("bw/band00", "bw/rll10", "bw/i3w3", "bw/fill75",
                  "bw/aniso_w2h3", "bw/aniso_w3h2", "bw/grey_c3", "bw/grey_c4",
                  "bw/strip00", "bw/strip16")
C_SEP_BAND = "c/band03"

# 2026-09-05: the frozen stimulus shas, all four artifacts of both pages.  The
# determinism test used to run gen_e006.py TWICE (~4.5 s each) and compare the
# two runs, which pins only run-to-run agreement inside one process; one run
# compared against these literals pins the stimulus across time, which is what
# the sha gate asks for.  Regenerated and verified 2026-09-05.
SHA256 = {
    "e006bw.ps":
        "797232ee1a51a3c8c0ddb173ee98a7f1a249e009f9cf3543adc95bf34c4c129e",
    "e006bw_manifest.json":
        "1cab720e3db20389ff222b34ac7285e2e96c62c01a175cc838dbb4ab5a1a32d9",
    "e006c.ps":
        "15e27c95d81c7a0f703147c8d783569ebc34e60818484c88b1fd2a6c9d6d960b",
    "e006c_manifest.json":
        "64551e277536a5c5de613a598d5ec6f016e619b689e2122bc064b827f131da67",
}


def _run_gen() -> None:
    subprocess.run([sys.executable, "gen_e006.py"], cwd=EXP, check=True,
                   capture_output=True)


def _sha256(name: str) -> str:
    return hashlib.sha256((BUILD / name).read_bytes()).hexdigest()


@contextlib.contextmanager
def _gen_lock(timeout: float = 600.0):
    """gen_e006.py writes into a fixed build/ directory and takes no output
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


def _manifest(tag: str) -> dict:
    _ensure_build()
    return json.loads((BUILD / f"e006{tag}_manifest.json").read_text())


def _patch(mf: dict, name: str) -> dict:
    return next(p for p in mf["patches"] if p["name"] == name)


def _render_gray(tag: str, dpi: int = 600) -> np.ndarray:
    _ensure_build()
    key = ("gray", tag, dpi)
    if key not in _cache:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "page.png"
            subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                            "-sDEVICE=pnggray", f"-r{dpi}",
                            "-o", str(out), str(BUILD / f"e006{tag}.ps")],
                           check=True, capture_output=True)
            _cache[key] = np.asarray(Image.open(out).convert("L"))
    return _cache[key]


def _render_tiffsep(tag: str, dpi: int = 600) -> dict[str, np.ndarray]:
    """Boolean ink maps per plane (tiffsep polarity: ink = 0/dark)."""
    _ensure_build()
    key = ("sep", tag, dpi)
    if key not in _cache:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET",
                            "-sDEVICE=tiffsep", f"-r{dpi}",
                            "-o", str(Path(td) / "sep_%d.tif"),
                            str(BUILD / f"e006{tag}.ps")],
                           check=True, capture_output=True)
            seps = {}
            for plane, name in (("C", "Cyan"), ("M", "Magenta"),
                                ("Y", "Yellow"), ("K", "Black")):
                f = Path(td) / f"sep_1({name}).tif"
                seps[plane] = np.asarray(Image.open(f)) < 128
            _cache[key] = seps
    return _cache[key]


def test_determinism_byte_identical() -> None:
    with _gen_lock():
        _run_gen()
        for name, sha in SHA256.items():
            assert _sha256(name) == sha, name
    _cache["build_ok"] = True


def test_geometry_bands_and_emission() -> None:
    for tag in PAGES:
        mf = _manifest(tag)
        x0, y0, x1, y1 = [round(v * MM_DOT) for v in mf["content_bounds_mm"]]
        rects: dict[tuple, list[str]] = {}
        for e in mf["patches"] + mf["infrastructure"]:
            rx, ry, rw, rh = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
            assert x0 <= rx and rx + rw <= x1 and y0 <= ry and ry + rh <= y1, \
                e["name"]
            rects.setdefault((rx, ry, rw, rh), []).append(e["name"])
        keys = list(rects)
        for i, a in enumerate(keys):      # distinct rects must not intersect
            for b in keys[i + 1:]:
                if not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                        or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1]):
                    raise AssertionError(f"overlap: {rects[a]} vs {rects[b]}")
        for key, names in rects.items():  # shared rects only via composite_of
            if len(names) > 1:
                owners = {_patch(mf, n).get("composite_of") for n in names}
                assert len(owners) == 1 and None not in owners, names

        # band skeleton: 17 strips on the exact 360-dot pitch, payload flush
        g = mf["band_geometry"]
        assert g["n_data_bands"] == 16 and g["canary_band"] == 16
        for i in range(17):
            s = _patch(mf, f"{tag}/strip{i:02d}")
            assert s["kind"] == "sync_strip" and s["planes"] == ["K"]
            assert s["x_dots"] == g["x0_dots"]
            assert s["y_dots"] == g["y0_dots"] + i * g["strip_pitch_dots"]
            assert s["w_dots"] == g["content_w_dots"]
            assert s["h_dots"] == g["strip_h_dots"]
        assert len(mf["bands"]) == 17
        for b in mf["bands"]:
            assert b["strip_y_dots"] == g["y0_dots"] + b["band"] * g["strip_pitch_dots"]
            assert b["y_dots"] == b["strip_y_dots"] + g["strip_h_dots"]

        # emission-path split per page
        if tag == "bw":
            for b in mf["bands"]:
                if b["kind"] in ("encoding_patch", "constrained_field"):
                    e = _patch(mf, b["name"])
                    assert e["planes"] == ["K"], e["name"]
                    assert e["w_dots"] == g["content_w_dots"]
                    assert e["h_dots"] == g["payload_h_dots"]
            for e in mf["patches"]:      # only refs go down the cmyk path
                if "composite_of" in e:
                    assert e["composite_of"].startswith("ref_cmyk_"), e["name"]
        else:
            for b in mf["bands"]:
                if b["kind"] != "state_field":
                    continue
                planes = [e for e in mf["patches"]
                          if e.get("composite_of") == b["name"]]
                assert {e["planes"][0] for e in planes} == {"C", "M", "Y"}, \
                    b["name"]
                for e in planes:
                    assert e["params"]["emission"] == "cmyk_image", e["name"]
            train = [b["band"] for b in mf["bands"]
                     if b.get("params", {}).get("purpose") == "training"]
            assert train == [0, 7, 15], train


def test_gt_files_load_and_match() -> None:
    seen: dict[str, str] = {}            # GT dir is shared across both pages
    for tag in PAGES:
        mf = _manifest(tag)
        for e in mf["patches"]:
            if e["gt"] is None:
                continue
            assert seen.setdefault(e["gt"], e["name"]) == e["name"]
            gt = np.load(BUILD / e["gt"])
            assert gt.shape == (e["h_dots"], e["w_dots"]), e["name"]
        for e in mf["patches"]:          # cell/state-level ground truths
            if "states_gt" in e["params"]:
                cell = e["params"]["cell_dots"]
                st = np.load(BUILD / e["params"]["states_gt"])
                assert st.shape == (e["h_dots"] // cell, e["w_dots"] // cell)
                assert st.max() < e["params"]["n_states"], e["name"]
            if "levels_gt" in e["params"]:
                cell = e["params"]["cell_dots"]
                lv = np.load(BUILD / e["params"]["levels_gt"])
                assert lv.shape == (e["h_dots"] // cell, e["w_dots"] // cell)
                assert lv.max() < e["params"]["n_levels"], e["name"]


def test_gs_gt_fidelity_bw_masks() -> None:
    mf = _manifest("bw")
    img = _render_gray("bw")
    for name in BW_MASK_CHECKS:
        e = _patch(mf, name)
        x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
        gt = np.load(BUILD / e["gt"])
        crop = (img[y: y + h, x: x + w] < 128).astype(np.uint8)
        assert np.array_equal(crop, gt), \
            f"{name}: {int((crop != gt).sum())}/{gt.size} px differ"


def test_gs_gt_fidelity_c_composite() -> None:
    mf = _manifest("c")
    seps = _render_tiffsep("c")
    checked = 0
    for p in mf["patches"]:
        if p.get("composite_of") != C_SEP_BAND:
            continue
        plane = p["planes"][0]
        x, y, w, h = p["x_dots"], p["y_dots"], p["w_dots"], p["h_dots"]
        gt = np.load(BUILD / p["gt"]).astype(bool)
        crop = seps[plane][y: y + h, x: x + w]
        assert np.array_equal(crop, gt), \
            f"{p['name']}: {int((crop != gt).sum())}/{gt.size} px differ"
        checked += 1
    assert checked == 3, checked


def test_sim_smoke_canary_b1() -> None:
    """Measured-channel simulator round-trip on the BW canary B1 patch: naive
    hard c2 decode must beat the 0.5 null decisively (plumbing check, not
    physics — the sim's c2 regime is dev-morphology-dominated by construction)."""
    from paperholo.channel import ChannelParams, print_scan
    from paperholo.metrics import ber
    from paperholo.modulation import dots_to_cells_hard

    mf = _manifest("bw")
    e = _patch(mf, "bw/canary_b1")
    bits = np.load(BUILD / e["gt"])
    p = ChannelParams(seed=11, geometry=False)
    scan = print_scan(bits, p)
    rx = dots_to_cells_hard(scan, 2 * p.scan_oversample)
    gt_cells = bits[::2, ::2]
    err = ber(gt_cells, rx)
    print(f"  canary B1 sim naive hard BER = {err:.4f}")
    assert 0.005 < err < 0.30, err


if __name__ == "__main__":
    fns = [test_determinism_byte_identical,
           test_geometry_bands_and_emission,
           test_gt_files_load_and_match,
           test_gs_gt_fidelity_bw_masks,
           test_gs_gt_fidelity_c_composite,
           test_sim_smoke_canary_b1]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"{len(fns)} tests passed")
