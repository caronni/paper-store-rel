"""psgen tests: bit packing, document structure, and (if ghostscript is
installed) a pixel-exact render round-trip — the pre-flight that gates prints."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from paperholo.modulation import rng
from paperholo.psgen import CMYK, PSDoc, pack_bits_rows


def test_pack_bits_rows_pads_each_row() -> None:
    bits = np.array([[1, 0, 1], [0, 1, 1]], dtype=np.uint8)
    packed = pack_bits_rows(bits)
    assert packed == bytes([0b10100000, 0b01100000])


def test_render_structure() -> None:
    doc = PSDoc(hw_dpi=600, title="t")
    doc.begin_page()
    doc.put_bitmap(np.eye(8, dtype=np.uint8), 100, 200, CMYK["K"])
    doc.put_label("hello (x)", 100, 300, CMYK["C"])
    doc.end_page()
    ps = doc.render()
    assert ps.startswith("%!PS-Adobe-3.0")
    assert "/HWResolution [600 600]" in ps
    assert ps.count("imagemask") == 1
    assert ps.count("showpage") == 1
    assert r"hello \(x\)" in ps
    assert ps.rstrip().endswith("%%EOF")


def test_anisotropic_grid_and_optional_hw_request() -> None:
    bits = np.ones((20, 12), np.uint8)
    doc = PSDoc(
        hw_dpi=600,
        page_size_pt=(72, 72),
        title="anisotropic",
        request_hw_dpi=(1200, 2400),
    )
    doc.begin_page()
    doc.put_bitmap(bits, 120, 240, CMYK["K"], dpi=(1200, 2400))
    doc.end_page()
    ps = doc.render()
    assert "/HWResolution [1200 2400]" in ps
    # 120/1200 inch = 7.2 pt; 12/1200 and 20/2400 inch = 0.72/0.6 pt.
    assert "7.200000 64.200000 translate" in ps
    assert "0.720000 0.600000 scale" in ps

    portable = PSDoc(request_hw_dpi=None)
    portable.begin_page()
    portable.end_page()
    assert "/HWResolution" not in portable.render()


def test_cmyk_bitmap_rejects_shape_mismatch() -> None:
    doc = PSDoc()
    doc.begin_page()
    try:
        doc.put_cmyk_bitmap({"C": np.zeros((4, 4), np.uint8), "M": np.zeros((5, 4), np.uint8)}, 0, 0)
    except ValueError:
        return
    raise AssertionError("shape mismatch not rejected")


def test_gs_render_pixel_exact() -> None:
    """Render a random bitmap via gs at device resolution; require bit-exactness."""
    if shutil.which("gs") is None:
        print("SKIP (no ghostscript)")
        return
    bits = rng(b"psgen-test", b"bitmap").integers(0, 2, size=(64, 64), dtype=np.uint8)
    doc = PSDoc(hw_dpi=600, page_size_pt=(72, 72), title="gs-roundtrip")  # 1 inch page
    doc.begin_page()
    doc.put_bitmap(bits, 100, 100, CMYK["K"])
    doc.end_page()
    with tempfile.TemporaryDirectory() as td:
        ps = Path(td) / "t.ps"
        png = Path(td) / "t.png"
        ps.write_text(doc.render())
        subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=pnggray",
                        "-r600", "-o", str(png), str(ps)], check=True, timeout=60)
        from PIL import Image

        img = np.asarray(Image.open(png).convert("L"))
        got = (img[100:164, 100:164] < 128).astype(np.uint8)
    assert np.array_equal(got, bits), f"{int((got != bits).sum())} pixels differ"


if __name__ == "__main__":
    for fn in (test_pack_bits_rows_pads_each_row, test_render_structure,
               test_anisotropic_grid_and_optional_hw_request,
               test_cmyk_bitmap_rejects_shape_mismatch, test_gs_render_pixel_exact):
        fn()
        print(f"PASS {fn.__name__}")
    print("all psgen tests passed")
