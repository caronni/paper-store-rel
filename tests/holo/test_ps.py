"""holo.gen.ps tests: bit packing, DSC/guard structure, the dots->points
geometry seam, determinism, and a pixel-exact full-A4 Ghostscript render
(the repo-standard emission gate: addressed dots == input bitmap, zero ink
elsewhere)."""
import hashlib
from pathlib import Path


import shutil
import subprocess

import numpy as np
import pytest

from holo.gen.ps import (
    A4_DOTS_XY,
    HW_DPI,
    PSDoc,
    pack_bits_rows,
    pack_cmyk_rows,
    pack_index_rows,
)

JOBID = "0a1b2c3d"
GOLDEN_K_DOC_SHA256 = (
    "bfff5b7b330ea655d2bc2951fd24f0a8"
    "bb35f765c65629582ac7e19783128415"
)
GOLDEN_RGB_MASK_DOC_SHA256 = (
    "e6fe336bc798a738d1649cb70c4e94b0"
    "3c7ac43bcffa64e61fb05c2a0b2da3eb"
)
GOLDEN_INDEXED2_DOC_SHA256 = (
    "73f049b5a17867758864535fcede61f9"
    "3ea1b42e9662d254b3418b54906f3aa0"
)
GOLDEN_INDEXED8_DOC_SHA256 = (
    "f0792dbc5b1835020d950ae21917b35c"
    "430820fccad2b4f8c0cede4d50c894f4"
)
WCMY_LOOKUP = ((255, 255, 255), (0, 208, 255), (240, 0, 192), (255, 255, 0))


def _test_bits() -> np.ndarray:
    """Deterministic 64x64 pattern: isolated dots, runs, and pinned corners."""
    yy, xx = np.mgrid[0:64, 0:64]
    bits = (((yy * 13 + xx * 7) % 11 == 0)
            | ((yy % 16 == 0) & (xx % 5 < 2))).astype(np.uint8)
    for y, x in ((0, 0), (0, 63), (63, 0), (63, 63)):
        bits[y, x] = 1
    assert 0 < int(bits.sum()) < bits.size
    return bits


def _doc_with(bits: np.ndarray, x_dots: int, y_dots: int, **kw) -> PSDoc:
    doc = PSDoc(A4_DOTS_XY, JOBID, **kw)
    doc.begin_page()
    doc.put_bitmap(bits, x_dots, y_dots)
    doc.end_page()
    return doc


# -- packing -------------------------------------------------------------
def test_pack_bits_rows_msb_first_row_padded() -> None:
    bits = np.array([[1, 0, 1], [0, 1, 1]], dtype=np.uint8)
    assert pack_bits_rows(bits) == bytes([0b10100000, 0b01100000])
    # nonzero = ink, bool accepted
    assert pack_bits_rows(np.array([[2, 0, 1]])) == bytes([0b10100000])
    assert pack_bits_rows(np.eye(2, dtype=bool)) == bytes([0b10000000, 0b01000000])


def test_pack_bits_rows_rejects_non_2d() -> None:
    with pytest.raises(ValueError):
        pack_bits_rows(np.zeros(8, dtype=np.uint8))


def test_pack_cmyk_rows_component_order_and_zero_k() -> None:
    # Pixel 0 = C+Y -> 1010; pixel 1 = M -> 0100.  Four component bits
    # per pixel make this one exact byte with no ambiguity about plane order.
    cmy = np.asarray([[[1, 0, 1], [0, 1, 0]]], dtype=np.uint8)
    assert pack_cmyk_rows(cmy) == bytes([0b10100100])


@pytest.mark.parametrize("bad", (
    np.zeros((2, 2)),
    np.zeros((2, 2, 2)),
    np.zeros((2, 2, 4)),
    np.zeros((2, 2, 5)),
    np.full((2, 2, 3), 0.5),
))
def test_pack_cmyk_rows_rejects_bad_shape_or_values(bad) -> None:
    with pytest.raises(ValueError):
        pack_cmyk_rows(bad)


# -- structure / guard ---------------------------------------------------
def test_render_structure_guard_and_resolution() -> None:
    doc = _doc_with(_test_bits(), 600, 900, title="holo-test")
    ps = doc.render()
    assert ps.startswith("%!PS-Adobe-3.0")
    assert f"%%Title: holo-test J={JOBID}" in ps
    assert "%%LanguageLevel: 2" in ps
    assert "%%BoundingBox: 0 0 596 842" in ps  # ceil of 595.20 x 841.92
    assert "%%Pages: 1" in ps
    assert ps.count("showpage") == 1
    assert ps.count("imagemask") == 1
    assert ps.rstrip().endswith("%%EOF")
    # setpagedevice: guarded, requesting [600 600] exactly once
    assert ps.count("setpagedevice") == 1
    assert ps.count("/HWResolution [600 600]") == 1
    assert ps.count("/HWResolution") == 1
    spd_line = next(ln for ln in ps.splitlines() if "setpagedevice" in ln)
    assert spd_line.startswith("{ <<") and spd_line.endswith("} stopped { } if")
    assert "/PageSize [595.20 841.92]" in spd_line and "/Duplex false" in spd_line


def test_unguarded_setpagedevice_is_bare() -> None:
    ps = _doc_with(_test_bits(), 0, 0, guard_setpagedevice=False).render()
    assert "stopped" not in ps
    assert ps.count("/HWResolution [600 600]") == 1
    spd_line = next(ln for ln in ps.splitlines() if "setpagedevice" in ln)
    assert spd_line.startswith("<<") and spd_line.endswith("setpagedevice")


def test_multi_page_numbering() -> None:
    doc = PSDoc(A4_DOTS_XY, JOBID)
    for _ in range(3):
        doc.begin_page()
        doc.put_bitmap(np.ones((4, 4), np.uint8), 100, 100)
        doc.end_page()
    ps = doc.render()
    assert "%%Pages: 3" in ps
    assert ps.count("showpage") == 3
    assert "%%Page: 2 2" in ps
    assert ps.count("setpagedevice") == 1  # job-level, not per page


# -- determinism ---------------------------------------------------------
# The byte-identity of two renders was its own test until 2026-09-20; the
# frozen sha below entails it.
def test_existing_k_postscript_bytes_are_frozen() -> None:
    raw = _doc_with(_test_bits(), 600, 900).render().encode("ascii")
    assert hashlib.sha256(raw).hexdigest() == GOLDEN_K_DOC_SHA256


def test_composite_cmyk_structure_and_bytes() -> None:
    cmy = np.asarray([
        [[1, 0, 0], [0, 1, 0]],
        [[0, 0, 1], [1, 1, 1]],
    ], dtype=np.uint8)
    doc = PSDoc(A4_DOTS_XY, JOBID)
    doc.begin_page()
    doc.put_cmyk_bitmap(cmy, 600, 900)
    doc.end_page()
    ps = doc.render()
    assert ps.count("/DeviceCMYK setcolorspace") == 1
    assert ps.count(">> image") == 1
    assert "imagemask" not in ps
    assert "/Width 2 /Height 2 /BitsPerComponent 1" in ps
    assert "/Decode [0 1 0 1 0 1 0 1]" in ps
    assert "/ImageMatrix [2 0 0 -2 0 2]" in ps
    # Rows are C/M/Y/K interleaved: C=1000, M=0100 then
    # Y=0010, CMY=1110.
    assert "\n842e\n" in ps
    assert "72.000000 733.680000 translate" in ps
    assert "0.240000 0.240000 scale" in ps


def test_composite_cmyk_protocol_and_bounds() -> None:
    bits = np.zeros((4, 4, 3), dtype=np.uint8)
    doc = PSDoc(A4_DOTS_XY, JOBID)
    with pytest.raises(RuntimeError):
        doc.put_cmyk_bitmap(bits, 0, 0)
    doc.begin_page()
    doc.put_cmyk_bitmap(bits, 4956, 7012)
    for x, y in ((-1, 0), (0, -1), (4957, 0), (0, 7013)):
        with pytest.raises(ValueError):
            doc.put_cmyk_bitmap(bits, x, y)
    doc.end_page()


# -- geometry seam -------------------------------------------------------
def test_geometry_seam_top_left_y_down() -> None:
    # 64x64 dots at (x=600, y=900) from the page's TOP-left corner:
    # x_pt = 600*72/600 = 72; bottom edge y_pt = 841.92 - (900+64)*72/600
    # (page height in pt derives EXACTLY from the 7016-dot raster).
    ps = _doc_with(_test_bits(), 600, 900).render()
    assert "72.000000 726.240000 translate" in ps
    assert "7.680000 7.680000 scale" in ps  # 64 dots = 7.68 pt each axis
    assert "64 64 true [64 0 0 -64 0 64]" in ps  # raster row order restored


def test_page_extent_dots_and_bounds() -> None:
    doc = PSDoc(A4_DOTS_XY, JOBID)
    assert (doc.page_w_dots, doc.page_h_dots) == (4960, 7016)
    assert doc.page_size_pt == (595.2, 841.92)  # exact: dots * 0.12
    doc.begin_page()
    doc.put_bitmap(np.ones((4, 4), np.uint8), 4956, 7012)  # flush fit ok
    for x, y in ((-1, 0), (0, -1), (4957, 0), (0, 7013)):
        with pytest.raises(ValueError):
            doc.put_bitmap(np.ones((4, 4), np.uint8), x, y)
    with pytest.raises(ValueError):
        doc.put_bitmap(np.ones((0, 4), np.uint8), 0, 0)
    doc.end_page()


# -- protocol / validation ----------------------------------------------
def test_page_protocol_errors() -> None:
    doc = PSDoc(A4_DOTS_XY, JOBID)
    with pytest.raises(RuntimeError):
        doc.put_bitmap(np.ones((2, 2), np.uint8), 0, 0)  # no page begun
    with pytest.raises(RuntimeError):
        doc.end_page()
    doc.begin_page()
    with pytest.raises(RuntimeError):
        doc.begin_page()
    with pytest.raises(RuntimeError):
        doc.render()  # page still open
    doc.end_page()
    with pytest.raises(RuntimeError):
        PSDoc(A4_DOTS_XY, JOBID).render()  # no pages


def test_rejects_bad_jobid_media_title() -> None:
    for bad in ("0a1b2c3", "0a1b2c3dd", "0A1B2C3D", "0a1b2c3g", ""):
        with pytest.raises(ValueError):
            PSDoc(A4_DOTS_XY, bad)
    for media in ((4960.5, 7016), (0, 7016), (4960, -1)):
        with pytest.raises(ValueError):
            PSDoc(media, JOBID)
    with pytest.raises(ValueError):
        PSDoc(A4_DOTS_XY, JOBID, title="two\nlines")


# -- Ghostscript emission gate ------------------------------------------
@pytest.mark.skipif(shutil.which("gs") is None, reason="ghostscript not installed")
def test_gs_render_pixel_exact_page_clean(tmp_path: Path) -> None:
    from PIL import Image

    bits = _test_bits()
    x_dots, y_dots = 1200, 1000
    ps_path = tmp_path / "t.ps"
    png = tmp_path / "t.png"
    ps_path.write_text(_doc_with(bits, x_dots, y_dots).render())
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=pnggray",
                    f"-r{HW_DPI}", "-o", str(png), str(ps_path)],
                   check=True, timeout=300)
    page = np.asarray(Image.open(png).convert("L")).copy()
    h, w = bits.shape
    assert page.shape[0] >= y_dots + h and page.shape[1] >= x_dots + w
    got = (page[y_dots:y_dots + h, x_dots:x_dots + w] < 128).astype(np.uint8)
    assert np.array_equal(got, bits), f"{int((got != bits).sum())} dots differ"
    page[y_dots:y_dots + h, x_dots:x_dots + w] = 255
    assert not np.any(page < 128), "ink outside the addressed rectangle"


@pytest.mark.skipif(shutil.which("gs") is None,
                    reason="ghostscript not installed")
def test_gs_composite_cmyk_separations_equal_authored_planes(
        tmp_path: Path) -> None:
    """The production composite operation carries exact C/M/Y and zero K."""
    from PIL import Image

    cmy = np.zeros((8, 8, 3), dtype=np.uint8)
    cmy[:4, :4, 0] = 1
    cmy[:4, 4:, 1] = 1
    cmy[4:, :4, 2] = 1
    cmy[4:, 4:, :] = 1
    x_dots, y_dots = 5, 7
    doc = PSDoc((32, 32), JOBID)
    doc.begin_page()
    doc.put_cmyk_bitmap(cmy, x_dots, y_dots)
    doc.end_page()
    ps_path = tmp_path / "cmyk.ps"
    ps_path.write_text(doc.render())
    out = tmp_path / "sep.tif"
    subprocess.run([
        "gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=tiffsep",
        f"-r{HW_DPI}", f"-sOutputFile={out}", str(ps_path),
    ], check=True, timeout=300)

    expected = {"Cyan": cmy[..., 0], "Magenta": cmy[..., 1],
                "Yellow": cmy[..., 2],
                "Black": np.zeros(cmy.shape[:2], dtype=np.uint8)}
    for name, plane in expected.items():
        image = np.asarray(
            Image.open(tmp_path / f"sep({name}).tif").convert("L")).copy()
        got = (image[y_dots:y_dots + 8, x_dots:x_dots + 8] < 128) \
            .astype(np.uint8)
        assert np.array_equal(got, plane), name
        image[y_dots:y_dots + 8, x_dots:x_dots + 8] = 255
        assert not np.any(image < 128), f"unexpected {name} outside field"


# -- colour masks and Indexed images (docs/CMY-PROBE-M281.md W0) ---------
def _test_indices() -> np.ndarray:
    """Deterministic 5x7 lookup indices 0..3: width 7 pads every 2-bit row."""
    yy, xx = np.mgrid[0:5, 0:7]
    return ((yy * 3 + xx * 5 + (yy * xx) % 3) % 4).astype(np.uint8)


def _indexed_doc(bpc: int, **kw) -> PSDoc:
    doc = PSDoc(A4_DOTS_XY, JOBID)
    doc.begin_page()
    doc.put_indexed_image(_test_indices(), WCMY_LOOKUP, 600, 900, bpc=bpc, **kw)
    doc.end_page()
    return doc


def test_put_bitmap_defaults_are_the_k_bytes() -> None:
    doc = PSDoc(A4_DOTS_XY, JOBID)
    doc.begin_page()
    doc.put_bitmap(_test_bits(), 600, 900, rgb=None, filt="ASCIIHex")
    doc.end_page()
    raw = doc.render().encode("ascii")
    assert hashlib.sha256(raw).hexdigest() == GOLDEN_K_DOC_SHA256


def test_rgb_mask_colour_line_and_bytes_are_frozen() -> None:
    doc = PSDoc(A4_DOTS_XY, JOBID)
    doc.begin_page()
    doc.put_bitmap(_test_bits(), 600, 900, rgb=(240, 0, 192))
    doc.end_page()
    ps = doc.render()
    assert "\n0.941176 0.000000 0.752941 setrgbcolor\n" in ps
    assert "setcmykcolor" not in ps
    assert hashlib.sha256(ps.encode("ascii")).hexdigest() == \
        GOLDEN_RGB_MASK_DOC_SHA256


def test_a85_mask_data_decodes_to_the_packed_rows() -> None:
    import base64

    bits = _test_bits()
    doc = PSDoc(A4_DOTS_XY, JOBID)
    doc.begin_page()
    doc.put_bitmap(bits, 600, 900, rgb=(0, 208, 255), filt="ASCII85")
    doc.end_page()
    lines = doc.render().splitlines()
    i = lines.index("currentfile /ASCII85Decode filter imagemask")
    j = lines.index("grestore", i)
    data = lines[i + 1:j]
    assert data[-1].endswith("~>") and ">" not in data[:-1]
    assert all(len(ln) <= 128 for ln in data[:-1])
    assert base64.a85decode("".join(data)[:-2], adobe=False) == \
        pack_bits_rows(bits)


@pytest.mark.parametrize("bad", ((0, 0), (0, 0, 256), (-1, 0, 0), (0.5, 0, 0)))
def test_put_bitmap_rejects_bad_rgb_and_filter(bad) -> None:
    doc = PSDoc(A4_DOTS_XY, JOBID)
    doc.begin_page()
    with pytest.raises(ValueError):
        doc.put_bitmap(_test_bits(), 0, 0, rgb=bad)
    with pytest.raises(ValueError):
        doc.put_bitmap(_test_bits(), 0, 0, filt="Flate")


def test_pack_index_rows_msb_first_row_padded() -> None:
    assert pack_index_rows(np.array([[1, 2, 3]]), 2) == bytes([0b01101100])
    assert pack_index_rows(np.array([[1, 0, 1]]), 1) == bytes([0b10100000])
    assert pack_index_rows(np.array([[15, 1], [2, 0]]), 4) == bytes([0xf1, 0x20])
    assert pack_index_rows(np.array([[7, 200]]), 8) == bytes([7, 200])


@pytest.mark.parametrize("bpc", (1, 2, 4, 8))
def test_pack_index_rows_unpacks_round_trip(bpc: int) -> None:
    rng = np.random.default_rng(7)
    v = rng.integers(0, 1 << bpc, size=(9, 13), dtype=np.uint8)
    packed = np.frombuffer(pack_index_rows(v, bpc), np.uint8)
    per_row = -(-13 * bpc // 8)
    bits = np.unpackbits(packed.reshape(9, per_row), axis=1)[:, :13 * bpc]
    weights = 1 << np.arange(bpc - 1, -1, -1)
    got = (bits.reshape(9, 13, bpc) * weights).sum(axis=2)
    assert np.array_equal(got, v)


@pytest.mark.parametrize("bad, bpc", (
    (np.array([[4]]), 2), (np.array([[-1]]), 8), (np.array([[0.0]]), 8),
    (np.zeros((2, 0), np.uint8), 2), (np.zeros(3, np.uint8), 2),
    (np.zeros((1, 1), np.uint8), 3),
))
def test_pack_index_rows_rejects(bad, bpc: int) -> None:
    with pytest.raises(ValueError):
        pack_index_rows(bad, bpc)


def test_indexed_2bit_structure_and_bytes_are_frozen() -> None:
    ps = _indexed_doc(2).render()
    lines = ps.splitlines()
    i = lines.index("gsave")
    assert lines[i + 1] == ("[/Indexed /DeviceRGB 3 <ffffff00d0fff000c0ffff00>]"
                            " setcolorspace")
    assert lines[i + 2:i + 9] == [
        "72.000000 733.320000 translate", "0.840000 0.600000 scale",
        "<< /ImageType 1", "   /Width 7 /Height 5 /BitsPerComponent 2",
        "   /Decode [0 3]", "   /ImageMatrix [7 0 0 -5 0 5]",
        "   /DataSource currentfile /ASCII85Decode filter"]
    assert lines[i + 9] == ">> image"
    assert lines[i + 10].endswith("~>") and lines[i + 11] == "grestore"
    assert hashlib.sha256(ps.encode("ascii")).hexdigest() == \
        GOLDEN_INDEXED2_DOC_SHA256


def test_indexed_8bit_hex_prelude_and_bytes_are_frozen() -> None:
    prelude = ("/HPColorTrapping where { pop Off HPColorTrapping } if",)
    ps = _indexed_doc(8, filt="ASCIIHex", prelude=prelude).render()
    lines = ps.splitlines()
    i = lines.index("gsave")
    assert lines[i + 2] == prelude[0]
    assert "   /Decode [0 255]" in lines
    assert "   /DataSource currentfile /ASCIIHexDecode filter" in lines
    j = lines.index(">> image")
    assert "".join(lines[j + 1:j + 2]) == _test_indices().tobytes().hex()
    assert lines[j + 2:j + 4] == [">", "grestore"]
    assert hashlib.sha256(_indexed_doc(8).render().encode("ascii")) \
        .hexdigest() == GOLDEN_INDEXED8_DOC_SHA256


def test_indexed_rejects_lookup_and_bounds() -> None:
    doc = PSDoc(A4_DOTS_XY, JOBID)
    idx = np.zeros((4, 4), np.uint8)
    with pytest.raises(RuntimeError):
        doc.put_indexed_image(idx, WCMY_LOOKUP, 0, 0)
    doc.begin_page()
    doc.put_indexed_image(idx, WCMY_LOOKUP, 4956, 7012)
    for x, y in ((-1, 0), (0, -1), (4957, 0), (0, 7013)):
        with pytest.raises(ValueError):
            doc.put_indexed_image(idx, WCMY_LOOKUP, x, y)
    with pytest.raises(ValueError):  # index beyond the lookup
        doc.put_indexed_image(idx + 2, WCMY_LOOKUP[:2], 0, 0)
    with pytest.raises(ValueError):  # five entries cannot be 2-bit
        doc.put_indexed_image(idx, WCMY_LOOKUP + ((0, 0, 0),), 0, 0)
    with pytest.raises(ValueError):
        doc.put_indexed_image(idx, [], 0, 0)
    with pytest.raises(ValueError):
        doc.put_indexed_image(idx, WCMY_LOOKUP, 0, 0, bpc=3)
    with pytest.raises(ValueError):
        doc.put_indexed_image(idx, WCMY_LOOKUP, 0, 0, prelude=("a\nb",))
    doc.end_page()


@pytest.mark.skipif(shutil.which("gs") is None, reason="ghostscript missing")
def test_gs_rgb_mask_and_2bit_image_threshold_to_their_planes(
        tmp_path: Path) -> None:
    """R/G/B < 128 reads back C/M/Y: one magenta mask, one 2-bit W/C/M/Y
    image, nothing painted elsewhere."""
    from holo.core.channel import states_to_planes

    rng = np.random.default_rng(11)
    mask = (rng.random((24, 40)) < 0.5).astype(np.uint8)
    idx = rng.integers(0, 4, size=(30, 37), dtype=np.uint8)
    doc = PSDoc((160, 120), JOBID)
    doc.begin_page()
    doc.put_bitmap(mask, 9, 5, rgb=WCMY_LOOKUP[2], filt="ASCII85")
    doc.put_indexed_image(idx, WCMY_LOOKUP, 101, 70, bpc=2)
    doc.end_page()
    ps_path = tmp_path / "rgb.ps"
    ps_path.write_text(doc.render())
    out = tmp_path / "rgb.ppm"
    subprocess.run(["gs", "-dNOPAUSE", "-dBATCH", "-dQUIET", "-sDEVICE=ppmraw",
                    f"-r{HW_DPI}", "-o", str(out), str(ps_path)],
                   check=True, timeout=300)
    from PIL import Image

    page = np.asarray(Image.open(out).convert("RGB")).copy()
    planes = (page < 128).astype(np.uint8)
    want = np.zeros_like(planes)
    want[5:29, 9:49, 1] = mask
    want[70:100, 101:138] = states_to_planes(np.array((0, 1, 2, 4))[idx])
    assert np.array_equal(planes, want), f"{int((planes != want).sum())} differ"
    page[70:100, 101:138] = 255
    page[5:29, 9:49][mask == 1] = 255
    assert (page == 255).all(), "paint outside the planned rectangles"
