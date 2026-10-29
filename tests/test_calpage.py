"""Exp 002 calibration page: determinism, geometry, gs preflight round-trip.

The gs round-trip is the pre-flight that gates printing (CLAUDE.md: simulation
before toner): it renders build/calpage.ps and decodes BOTH machine strips with
the reference decoder, which exercises the entire print-time query/payload/CRC
path on a real interpreter.

Observed ghostscript 10.07 resolution behavior (documented per task): with
`-rN` on the command line, gs KEEPS N dpi — the job's `/HWResolution [600 600]`
request inside setpagedevice does not override the CLI value (PageSize [595 842]
from the same setpagedevice IS honored). The strip therefore reports RD=RE=NxN
and the module formula max(4, round(dpi/100)) scales the strip physically
1:1 — which is exactly what the round-trip below asserts, without hard-coding
either behavior: the granted resolution is inferred from the raster width.
"""
from __future__ import annotations

import hashlib
import pytest
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "002-calibration-page"
BUILD = EXP / "build"

# 2026-09-06: every test here reads a build that a test regenerates in place;
# test_composite_probe.py, test_modprobe.py, test_overlap2.py write the same
# directory.  One xdist worker per build directory (pyproject: --dist
# loadgroup).
pytestmark = pytest.mark.xdist_group("build-002-003-probes")

sys.path.insert(0, str(EXP))
import stripdec  # noqa: E402

_STATE: dict = {}


def _generate() -> tuple[str, str]:
    r = subprocess.run([sys.executable, str(EXP / "gen_calpage.py")],
                       capture_output=True, text=True, timeout=600, cwd=str(EXP))
    assert r.returncode == 0, f"gen_calpage.py failed:\n{r.stdout}\n{r.stderr}"
    ps_sha = hashlib.sha256((BUILD / "calpage.ps").read_bytes()).hexdigest()
    mf_sha = hashlib.sha256((BUILD / "calpage_manifest.json").read_bytes()).hexdigest()
    return ps_sha, mf_sha


def _built() -> None:
    if "sha" not in _STATE:
        _STATE["sha"] = _generate()


def _render(dpi: int, extra: tuple[str, ...] = ()) -> np.ndarray:
    _built()
    assert shutil.which("gs") is not None, "ghostscript required for preflight"
    png = BUILD / f"preflight_{dpi}{'_' + '_'.join(extra) if extra else ''}.png"
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=pnggray",
                    f"-r{dpi}", *extra, "-o", str(png), str(BUILD / "calpage.ps")],
                   check=True, timeout=600)
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None  # A4 at 1200 dpi exceeds PIL's default limit
    return np.asarray(Image.open(png).convert("L"))


def _manifest() -> dict:
    _built()
    return json.loads((BUILD / "calpage_manifest.json").read_text())


# -- 1. determinism ---------------------------------------------------------

def test_determinism_byte_identical() -> None:
    a = _generate()
    b = _generate()
    assert a == b, f"regeneration not byte-identical: {a} vs {b}"
    _STATE["sha"] = b


# -- 2. geometry ------------------------------------------------------------

def _unique_rects(mf: dict) -> list[tuple[str, int, int, int, int]]:
    """One rect per element; composite planes share a rect (put_multi)."""
    seen: dict[str, tuple] = {}
    for e in mf["patches"] + mf["infrastructure"]:
        key = e.get("composite_of") or e["name"]
        seen[key] = (key, e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"])
    return list(seen.values())


def test_geometry_no_overlaps_labels_clear_bounds() -> None:
    mf = _manifest()
    rects = _unique_rects(mf)
    for i in range(len(rects)):
        ni, xi, yi, wi, hi = rects[i]
        for j in range(i + 1, len(rects)):
            nj, xj, yj, wj, hj = rects[j]
            assert not (xi < xj + wj and xj < xi + wi and yi < yj + hj and yj < yi + hi), \
                f"{ni} overlaps {nj}"
    dpm = mf["hw_dpi"] / 25.4
    x0b, y0b, x1b, y1b = 6 * dpm - 1, 6 * dpm - 1, 204 * dpm + 1, 291 * dpm + 1
    for n, x, y, w, h in rects:
        assert x >= x0b and y >= y0b and x + w <= x1b and y + h <= y1b, \
            f"{n} outside Tier-0/1 bounds"
    for lb in mf["labels"]:
        lx, ly, lw, lh = lb["x_dots"], lb["y_dots"], lb["w_dots"], lb["h_dots"]
        assert lx >= x0b and ly >= y0b and lx + lw <= x1b and ly + lh <= y1b, \
            f"label {lb['text']!r} outside bounds"
        for n, x, y, w, h in rects:
            assert not (lx < x + w and x < lx + lw and ly < y + h and y < ly + lh), \
                f"label {lb['text']!r} intersects {n}"


# -- 3. gs preflight round-trip ----------------------------------------------

def _check_strips(img: np.ndarray, mf: dict) -> list[dict]:
    strips = stripdec.decode_image(img)
    assert len(strips) == 2, f"expected 2 strips, decoded {len(strips)}"
    granted = round(img.shape[1] / (595 / 72))  # dpi implied by raster width
    for s in strips:
        assert s["magic_ok"], "strip magic PHCAL1 missing"
        assert s["crc_ok"], "strip CRC-16 mismatch"
        f = s["fields"]
        assert f["S"] == mf["seed"]
        assert f["J"] == mf["jobid"]
        assert f["LAY"] == "1"
        assert f["PS"] == "595x842", f"PageSize not honored: {f['PS']}"
        assert f["RE"] == f"{granted}x{granted}", \
            f"RE={f['RE']} but raster implies {granted} dpi"
        assert "ghostscript" in f["PR"].lower(), f"PR not Ghostscript-ish: {f['PR']!r}"
    return strips


def test_gs_roundtrip_600() -> None:
    mf = _manifest()
    img = _render(600)
    strips = _check_strips(img, mf)
    for s in strips:
        # gs -r600 default == our request: both snapshots read 600x600
        assert s["fields"]["RD"] == "600x600"
        assert s["fields"]["RE"] == "600x600"
        mx, my = s["module_px"]
        assert abs(mx - 6) < 0.1 and abs(my - 6) < 0.1


def test_gs_roundtrip_1200() -> None:
    """gs 10.07 keeps the CLI -r1200 (does not downgrade to the requested 600);
    RD (default snapshot, pre-setpagedevice) must equal the CLI value and RE
    whatever was granted — stripdec self-scales off the printed geometry."""
    mf = _manifest()
    img = _render(1200)
    strips = _check_strips(img, mf)
    granted = round(img.shape[1] / (595 / 72))
    for s in strips:
        assert s["fields"]["RD"] == "1200x1200", \
            f"default snapshot lost the CLI resolution: RD={s['fields']['RD']}"
        mx, _ = s["module_px"]
        assert abs(mx - max(4, round(granted / 100))) < 0.2, \
            f"module {mx:.2f} px inconsistent with granted {granted} dpi"


# -- 4. ground-truth fidelity -------------------------------------------------

def test_gt_shapes_whole_manifest() -> None:
    """Every gt .npy loads and matches its manifest rect (catches filename
    collisions between patch families — the Y/density vs Y_density class)."""
    mf = _manifest()
    seen: dict[str, str] = {}
    for e in mf["patches"]:
        if e["gt"] is None:
            continue
        assert seen.setdefault(e["gt"], e["name"]) == e["name"], \
            f"gt file {e['gt']} shared by {seen[e['gt']]} and {e['name']}"
        gt = np.load(BUILD / e["gt"])
        assert gt.shape == (e["h_dots"], e["w_dots"]), \
            f"{e['name']}: gt {gt.shape} vs manifest ({e['h_dots']},{e['w_dots']})"


def test_gt_fidelity_pixel_exact() -> None:
    mf = _manifest()
    img = _render(600)
    byname = {e["name"]: e for e in mf["patches"]}
    for nm in ("K/density_50", "K/encode_c3", "warp_field"):
        e = byname[nm]
        x, y, w, h = e["x_dots"], e["y_dots"], e["w_dots"], e["h_dots"]
        gt = np.load(BUILD / e["gt"])
        crop = (img[y: y + h, x: x + w] < 128).astype(np.uint8)
        assert crop.shape == gt.shape, f"{nm}: crop {crop.shape} vs gt {gt.shape}"
        assert np.array_equal(crop, gt), \
            f"{nm}: {int((crop != gt).sum())}/{gt.size} pixels differ"


if __name__ == "__main__":
    for fn in (test_determinism_byte_identical,
               test_geometry_no_overlaps_labels_clear_bounds,
               test_gs_roundtrip_600, test_gs_roundtrip_1200,
               test_gt_shapes_whole_manifest, test_gt_fidelity_pixel_exact):
        fn()
        print(f"PASS {fn.__name__}")
    print("all calpage tests passed")
