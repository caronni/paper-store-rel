"""Preflight for experiment 009 ORES-1 (PJL/PCL resolution-unlock jobs).

Validates the composed jobs WITHOUT an external PCL renderer (gpcl6 has no
fonts on this box): PCL rasters are self-parsed back to the ground-truth
bitmap; the PS path is gs-rendered pixel-exact; the analyzer is exercised on
noise-free synthetic scans built from the bitmaps (renderer-independent).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

Image.MAX_IMAGE_PIXELS = None

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / "experiments" / "009-office-resolution"
BUILD = EXP / "build"
sys.path.insert(0, str(EXP))
sys.path.insert(0, str(ROOT / "src"))

import gen_ores as G  # noqa: E402
import analyze_ores as A  # noqa: E402

UEL = b"\x1b%-12345X"


@pytest.fixture(scope="module", autouse=True)
def _built():
    G.main()   # deterministic; regenerates build/


def _job(name: str) -> bytes:
    return (BUILD / name).read_bytes()


def test_byte_identical_regen():
    m1 = (BUILD / "ores_manifest.json").read_bytes()
    G.main()
    assert (BUILD / "ores_manifest.json").read_bytes() == m1


def _parse_pcl(data: bytes):
    res = int(re.search(rb"\x1b\*t(\d+)R", data).group(1))
    rows = [data[m.end():m.end() + int(m.group(1))]
            for m in re.finditer(rb"\x1b\*b(\d+)W", data)]
    nbytes = int(re.search(rb"\x1b\*b(\d+)W", data).group(1))
    arr = np.zeros((len(rows), nbytes * 8), np.uint8)
    for r, rb in enumerate(rows):
        arr[r, :len(rb) * 8] = np.unpackbits(np.frombuffer(rb, np.uint8))
    return res, arr


@pytest.mark.parametrize("job,bmpf,res", [
    ("ores_pcl1200.pcl", "ores_bitmap_1200.npy", 1200),
    ("ores_pcl1200_pjlres.pcl", "ores_bitmap_1200.npy", 1200),
    ("ores_pcl2400.pcl", "ores_bitmap_2400.npy", 2400),
])
def test_pcl_selfparse_exact(job, bmpf, res):
    r, arr = _parse_pcl(_job(job))
    bmp = np.load(BUILD / bmpf)
    assert r == res
    assert np.array_equal(arr[:bmp.shape[0], :bmp.shape[1]], bmp)


def test_structural_lint():
    for name in ("ores_query.pjl", "ores_pspjl1200.job", "ores_pcl1200.pcl",
                 "ores_pcl1200_pjlres.pcl", "ores_pcl2400.pcl"):
        d = _job(name)
        assert d.startswith(UEL) and d.rstrip(b"\r\n").endswith(UEL), name
    # J0 prints nothing: no language enter, no raster, no showpage
    q = _job("ores_query.pjl")
    assert b"ENTER LANGUAGE" not in q and b"\x1b*r" not in q and b"showpage" not in q
    assert b"@PJL DINQUIRE RESOLUTION" in q
    # J1 = one PostScript enter, guarded PageSize, RESOLUTION=1200, backchannel probe
    j1 = _job("ores_pspjl1200.job")
    assert j1.count(b"ENTER LANGUAGE=POSTSCRIPT") == 1
    assert b"@PJL SET RESOLUTION=1200" in j1
    assert b"ORES HWResolution" in j1
    assert b"showpage" in j1
    # PCL jobs: exactly one raster resolution, formfeed present, one PCL enter
    for name, want in (("ores_pcl1200.pcl", 1200), ("ores_pcl2400.pcl", 2400)):
        d = _job(name)
        assert d.count(b"ENTER LANGUAGE=PCL") == 1
        assert re.search(rb"\x1b\*t%dR" % want, d)
        assert b"\x0c" in d and b"\x1b*rC" in d
    assert b"@PJL SET RESOLUTION=1200" in _job("ores_pcl1200_pjlres.pcl")
    assert b"@PJL SET RESOLUTION" not in _job("ores_pcl1200.pcl")


def _synth_scan(grid: int, margin: int = 40, upscale: int = 1) -> str:
    """Noise-free 'scan': the GT bitmap on a white canvas (ink dark). `upscale`
    pixel-replicates the bitmap to simulate a printer that imaged the raster at
    a COARSER device grid (each grid-dot -> upscale device dots), i.e. the
    AltaLink PCL-at-600 'scaled-not-denser' behaviour."""
    bmp = np.load(BUILD / f"ores_bitmap_{grid}.npy")
    if upscale > 1:
        bmp = np.repeat(np.repeat(bmp, upscale, 0), upscale, 1)
    H, W = bmp.shape
    canvas = np.full((H + 2 * margin, W + 2 * margin), 255, np.uint8)
    canvas[margin:margin + H, margin:margin + W] = (1 - bmp) * 255
    out = f"/tmp/ores_synth_{grid}_{upscale}.png"
    Image.fromarray(canvas, "L").save(out)
    return out


def test_positive_control_grid_honored():
    """A truly grid-imaged 1200 print (1 device-dot per grid-dot) scanned well
    (2 px/grid-dot => scan_dpi 2400): geometry honored, both fields UNLOCKED,
    600 controls ~0. This is the shape a REAL unlock must produce."""
    scan = _synth_scan(1200, upscale=2)          # 2 scan-px per grid-dot
    r = A.analyze(scan, 1200, scan_dpi=2400)     # device = 2400/2 = 1200 = grid -> honored
    assert r["geometry"]["grid_honored"] is True, r["geometry"]
    for k in ("pn_c3_600", "pn_c2_600"):
        assert r["pn"][k]["ber"] < 0.02, (k, r["pn"][k])
        assert r["pn"][k]["null"] > 0.40
    assert r["verdicts"]["c3"] == "UNLOCKED", r["verdicts"]
    assert r["verdicts"]["c2"] == "UNLOCKED", r["verdicts"]


def test_scaled_not_denser_is_not_unlocked():
    """The key hardware finding (2026-07-07 photo): the AltaLink imaged the PCL
    1200-raster at 600 dpi -> content 2x oversize, decodes fine but NO density
    gain. SAME image as the honored test (2 px per grid-dot), but now claim the
    scan was 1200 dpi -> device = 1200/2 = 600 => the absolute-scale gate must
    catch it and report SCALED, never UNLOCKED, even though the cells decode."""
    scan = _synth_scan(1200, upscale=2)
    r = A.analyze(scan, 1200, scan_dpi=1200)     # device = 1200/2 = 600 << grid
    assert r["geometry"]["grid_honored"] is False, r["geometry"]
    assert r["pn"]["pn_c3_grid"]["ber"] < 0.05   # decodes fine...
    assert r["verdicts"]["c3"].startswith("SCALED"), r["verdicts"]  # ...but NOT unlocked
    assert r["verdicts"]["c2"].startswith("SCALED"), r["verdicts"]


def test_underresolved_scan_is_indeterminate():
    """1200 grid scanned at exactly 1200 dpi = 1 px/grid-dot: c2@1200 is only
    2 px/cell (< MIN_PX_PER_CELL) so its verdict is withheld as INDETERMINATE
    even though geometry is honored — the scanner-Nyquist guard."""
    r = A.analyze(_synth_scan(1200, upscale=1), 1200, scan_dpi=1200)
    assert r["geometry"]["grid_honored"] is True, r["geometry"]
    assert r["verdicts"]["c2"].startswith("INDETERMINATE"), r["verdicts"]


def test_geometry_unchecked_without_scan_dpi():
    """Omitting --scan-dpi must NOT silently emit an unlock claim: geometry is
    None and the tool cannot distinguish a real unlock from a scaled print."""
    r = A.analyze(_synth_scan(1200, upscale=1), 1200)
    assert r["geometry"]["device_dpi_inferred"] is None
    assert r["geometry"]["grid_honored"] is None


def test_ps_path_gs_render():
    """gs-render J1's PostScript (PJL stripped) at 1200 and confirm the fields
    decode — proves the PS bitmap content is correct and gs-renderable."""
    data = _job("ores_pspjl1200.job")
    i = data.find(b"%!PS"); j = data.rfind(UEL)
    Path("/tmp/ores_j1.ps").write_bytes(data[i:j])
    out = "/tmp/ores_j1.png"
    p = subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=pnggray",
                        "-r1200", "-o", out, "/tmp/ores_j1.ps"],
                       capture_output=True)
    assert p.returncode == 0, p.stderr.decode()[-500:]
    # backchannel probe present in the job stream
    assert b"ORES HWResolution" in data
    r = A.analyze(out, 1200, scan_dpi=1200)
    assert r["pn"]["pn_c3_600"]["ber"] < 0.03
    assert r["verdicts"]["c3"] == "UNLOCKED"
