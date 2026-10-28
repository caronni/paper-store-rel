"""Generation on the v2 lattice (FORMAT-SPACE §7/§9): paper profiles,
sheet placement, the ``fit`` derivation, v2 emission + manifest, and the
PostScript engine-grid seam.

Two laws are pinned here:

- the ``fit`` table of docs/FORMAT-SPACE.md §7 (the six machine-checked
  geometries), and its agreement with the v1 ``derive_field`` placement —
  a v2 field sized by ``fit`` lands exactly where the legacy row lands;
- byte-identical regeneration of a v2 volume (format law: the same id and
  the same payload produce the same sheet forever).
"""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo import cli
from holo.format.lattice import parse_format_id
from holo.format.layout import MEDIA_MM, derive_field
from holo.format.layout import page_dots_xy as frozen_page_dots_xy
from holo.gen import sheet as sheet_mod
from holo.gen.emit import emit_volume
from holo.gen.ps import PSDoc
from holo.gen.sheet import (
    PAPER_PROFILES,
    dots_per_cell,
    fit,
    page_dots_xy,
    sheet_layout,
)

# FORMAT-SPACE §7, machine-checked against derive_field.
FIT_TABLE = [
    ("A4-6mm", "c2", (52, 36)),
    ("A4-6mm", "c3", (35, 24)),
    ("A4-6mm", "c4", (26, 18)),
    ("A4-4mm", "c2", (53, 37)),
    ("A4-4mm", "c3", (35, 24)),      # 4 mm and 6 mm quantize to one field
    ("A3-4mm", "c2", (76, 53)),
]


@pytest.mark.parametrize("paper,pitch,tiles_yx", FIT_TABLE)
def test_fit_table(paper: str, pitch: str, tiles_yx: tuple[int, int]) -> None:
    assert fit(paper, pitch) == tiles_yx


@pytest.mark.parametrize("paper,pitch,tiles_yx", FIT_TABLE)
def test_fit_matrix_lands_where_the_v1_derivation_lands(
    paper: str, pitch: str, tiles_yx: tuple[int, int],
) -> None:
    """The demotion is arithmetic-preserving: placing the fitted matrix
    reproduces derive_field's page, field, origin and borders exactly."""
    profile = PAPER_PROFILES[paper]
    cell_dots = dots_per_cell(pitch, 600)
    legacy = derive_field(media_mm=profile.media_mm,
                          margin_mm=profile.margin_mm, cell_dots=cell_dots)
    spec = parse_format_id(
        f"{pitch}-k-r0550@{tiles_yx[0]}x{tiles_yx[1]}")
    placed = sheet_layout(spec, paper)
    assert legacy.tiles_yx == tiles_yx
    assert placed.page_dots_xy == legacy.page_dots_xy
    assert placed.field_dots_yx == legacy.field_dots_yx
    assert placed.origin_dots_yx == legacy.origin_dots_yx
    assert placed.dots_per_cell == legacy.cell_dots
    assert (placed.border_top_mm, placed.border_bottom_mm,
            placed.border_left_mm, placed.border_right_mm) == \
        (legacy.border_top_mm, legacy.border_bottom_mm,
         legacy.border_left_mm, legacy.border_right_mm)


@pytest.mark.parametrize("media_id", sorted(MEDIA_MM))
def test_page_raster_at_600_is_the_frozen_one(media_id: str) -> None:
    """Generalizing the raster over the engine grid keeps 600 exact."""
    assert page_dots_xy(MEDIA_MM[media_id]) == \
        frozen_page_dots_xy(MEDIA_MM[media_id])
    assert page_dots_xy(MEDIA_MM[media_id], 600) == \
        frozen_page_dots_xy(MEDIA_MM[media_id])


def test_page_raster_scales_with_the_engine_grid() -> None:
    assert page_dots_xy(MEDIA_MM["a4"], 1200) == (9920, 14032)
    assert page_dots_xy(MEDIA_MM["a4"], 300) == (2480, 3504)


def test_dots_per_cell_gate_is_integrality_only() -> None:
    # 1 dot/cell is lawful format (FORMAT-SPACE ruling 7: no floor).
    assert dots_per_cell(Fraction(1, 600), 600) == 1
    assert dots_per_cell("c2", 600) == 2
    assert dots_per_cell("c2", 1200) == 4
    assert dots_per_cell("1i400", 1200) == 3
    with pytest.raises(ValueError) as exc:
        dots_per_cell("1i400", 600)
    message = str(exc.value)
    assert "1/400" in message and "600" in message


def test_fit_off_grid_pitch_refuses_naming_the_grid() -> None:
    with pytest.raises(ValueError):
        fit("A4-6mm", "1i400", 600)
    # 3 dots/cell on the 1200 grid = a 63.5 um cell, finer than c3
    assert fit("A4-6mm", "1i400", 1200) == (70, 48)


def test_sheet_refuses_a_field_larger_than_the_paper() -> None:
    spec = parse_format_id("c2-k-r0700@53x37")       # the 4 mm matrix
    with pytest.raises(ValueError) as exc:
        sheet_layout(spec, "A4-6mm")
    message = str(exc.value)
    assert "7016" in message and "A4-6mm" in message


def test_sheet_layout_refuses_v1_specs() -> None:
    from holo.devices.profiles import make_spec
    with pytest.raises(ValueError):
        sheet_layout(make_spec("c3-r0550"), "A4-6mm")


def test_paper_profiles_are_the_documented_bundles() -> None:
    assert sheet_mod.DEFAULT_PAPER == "A4-6mm"
    assert {name: (p.media_id, p.margin_mm)
            for name, p in PAPER_PROFILES.items()} == {
        "A4-6mm": ("a4", 6.0),
        "A4-4mm": ("a4", 4.0),
        "A3-6mm": ("a3", 6.0),
        "A3-4mm": ("a3", 4.0),
    }
    assert "unprinted" in PAPER_PROFILES["A3-6mm"].note
    assert "e033" in PAPER_PROFILES["A4-4mm"].note


# -- emission ------------------------------------------------------------
V2_GOLDEN_ID = "c3-k-r0550@10x10"
V2_GOLDEN_PAYLOAD = bytes(range(256)) * 4       # 1,024 fixed bytes
# v2 emit golden — byte-identical regeneration is format law.
# RE-FROZEN 2026-09-02 (amendment dated 2026-08-30): a DECLARED v2 format
# fork, FORMAT-SPACE §16 — the canonical id (and therefore the AES row
# seed) became the explicit
# spelling, so every v2 emission changes.  No printed sheet is affected:
# the physical record is entirely legacy/fossil identities on holo/v1/
# seeds.  This is the only lawful reason to edit this constant.
V2_GOLDEN_PS_SHA256 = (
    "cf1772b3e33e93b4c51f5a8f0ebb1a51"
    "6841cdc18f32daf20f5d177daae48331")
V2_GOLDEN_GT_SHA256 = (
    "64facb04c8d6d341decf6196e36d0dda"
    "10bdda6042975d21f65c4875ecbb5070")


def test_v2_emit_golden_is_byte_stable(tmp_path: Path) -> None:
    spec = parse_format_id(V2_GOLDEN_ID)
    first = emit_volume(spec, V2_GOLDEN_PAYLOAD, 0.5, tmp_path / "a",
                        paper="A4-6mm")
    second = emit_volume(spec, V2_GOLDEN_PAYLOAD, 0.5, tmp_path / "b",
                         paper="A4-6mm")
    assert [p.ps_sha256 for p in first.pages] == \
        [p.ps_sha256 for p in second.pages]
    assert [p.gt_sha256 for p in first.pages] == \
        [p.gt_sha256 for p in second.pages]
    assert first.plan.n_pages == 1
    page = first.pages[0]
    assert page.ps_sha256 == V2_GOLDEN_PS_SHA256
    assert page.gt_sha256 == V2_GOLDEN_GT_SHA256
    assert hashlib.sha256(page.ps_path.read_bytes()).hexdigest() == \
        page.ps_sha256
    packed_gt = np.load(page.gt_path)
    assert hashlib.sha256(packed_gt.tobytes(order="C")).hexdigest() == \
        page.gt_sha256
    # the field sits centered on a full A4 raster, not on its own bbox
    assert packed_gt.shape == (1920, 240)
    manifest = json.loads((tmp_path / "a" / "manifest.json").read_text())
    assert manifest["holo"] == "v2"
    canonical = parse_format_id(V2_GOLDEN_ID).spec_id
    assert manifest["format_id"] == canonical
    assert manifest["spec_id"] == canonical
    assert manifest["seed"] == "holo/v2/" + canonical
    assert manifest["paper"] == "A4-6mm"
    assert manifest["media_id"] == "a4" and manifest["margin_mm"] == 6.0
    assert manifest["engine_dpi"] == 600
    assert manifest["dots_per_cell"] == 3
    assert manifest["pitch"] == "1/200"
    assert manifest["page_dots_xy"] == [4960, 7016]
    assert manifest["origin_dots_yx"] == [2548, 1520]
    assert manifest["page_cells_yx"] == [640, 640]
    assert manifest["tiles_yx"] == [10, 10]


def test_v2_emit_honors_the_paper_and_engine_grid(tmp_path: Path) -> None:
    spec = parse_format_id(V2_GOLDEN_ID)
    vol = emit_volume(spec, V2_GOLDEN_PAYLOAD, 0.5, tmp_path / "v",
                      paper="A4-4mm", engine_dpi=1200)
    manifest = json.loads((tmp_path / "v" / "manifest.json").read_text())
    assert manifest["engine_dpi"] == 1200
    assert manifest["dots_per_cell"] == 6          # 1/200 in x 1200 dpi
    assert manifest["page_dots_xy"] == [9920, 14032]
    ps = vol.pages[0].ps_path.read_text(encoding="ascii")
    assert "/HWResolution [1200 1200]" in ps
    assert np.load(vol.pages[0].gt_path).shape == (3840, 480)


def test_v1_row_refuses_paper_and_dpi(tmp_path: Path) -> None:
    from holo.devices.profiles import make_spec
    spec = make_spec("c3-r0550")
    with pytest.raises(ValueError) as exc:
        emit_volume(spec, b"legacy", 0.5, tmp_path / "v", paper="A4-4mm")
    assert "v2" in str(exc.value)
    with pytest.raises(ValueError):
        emit_volume(spec, b"legacy", 0.5, tmp_path / "w", engine_dpi=1200)


@pytest.mark.parametrize("format_id", [
    "c2-cmy8-r0550x0550x0547@10x10",
    "c2-cmy7@10x10",
])
def test_v2_colour_emit_smoke(tmp_path: Path, format_id: str) -> None:
    spec = parse_format_id(format_id)
    vol = emit_volume(spec, b"colour smoke" * 8, 0.5, tmp_path / "v",
                      paper="A4-4mm")
    page = vol.pages[0]
    assert page.gt_plane_sha256 is not None
    assert len(set(page.gt_plane_sha256)) == 3     # C/M/Y differ
    packed = np.load(page.gt_path)
    assert packed.shape == (3, 1280, 160)          # 640 cells x 2 dots
    for plane in range(3):
        assert hashlib.sha256(
            packed[plane].tobytes(order="C")).hexdigest() == \
            page.gt_plane_sha256[plane]
    ps = page.ps_path.read_text(encoding="ascii")
    assert "/DeviceCMYK setcolorspace" in ps and "imagemask" not in ps
    manifest = json.loads((tmp_path / "v" / "manifest.json").read_text())
    assert manifest["holo"] == "v2"
    assert manifest["format_id"] == parse_format_id(format_id).spec_id
    assert manifest["paper"] == "A4-4mm"
    assert manifest["engine_dpi"] == 600
    assert manifest["dots_per_cell"] == 2
    assert manifest["pitch"] == "1/300"
    assert manifest["pages"][0]["gt_plane_sha256"] == \
        list(page.gt_plane_sha256)
    assert manifest["codec"]["codec_id"] == spec.codec_id


# -- the PostScript engine-grid seam -------------------------------------
def test_psdoc_engine_dpi_scales_points_and_requests_the_grid() -> None:
    bits = np.ones((8, 8), dtype=np.uint8)
    rendered = {}
    for dpi in (600, 300):
        doc = PSDoc((1200, 1200), "0a1b2c3d", engine_dpi=dpi)
        doc.begin_page()
        doc.put_bitmap(bits, x_dots=600, y_dots=600)
        doc.end_page()
        rendered[dpi] = doc.render()
        assert doc.page_size_pt == (1200 * 72.0 / dpi, 1200 * 72.0 / dpi)
    assert "/HWResolution [600 600]" in rendered[600]
    assert "/HWResolution [300 300]" in rendered[300]
    assert "/PageSize [144.00 144.00]" in rendered[600]
    assert "/PageSize [288.00 288.00]" in rendered[300]   # halved dpi, 2x pt
    # the same dot geometry, twice the points
    assert "72.000000 71.040000 translate" in rendered[600]
    assert "144.000000 142.080000 translate" in rendered[300]


# -- CLI -----------------------------------------------------------------
def test_cli_fit_prints_matrix_and_skeleton_ids(capsys) -> None:
    assert cli.main(["fit", "--paper", "A4-4mm", "--pitch", "2i600"]) == 0
    out = capsys.readouterr().out
    assert "2 dots/cell" in out
    assert "53x37 tiles" in out
    assert "c2-k-<rung>@53x37" in out          # canonical pitch token
    assert "c2-cmy7@53x37" in out
    assert "c2-cmy8-<rung>@53x37" in out
    assert "r0700" in out                      # the ladder, no invented rung


def test_cli_generate_on_a_format_id(tmp_path: Path, capsys) -> None:
    payload = tmp_path / "p.bin"
    payload.write_bytes(V2_GOLDEN_PAYLOAD)
    out_dir = tmp_path / "vol"
    assert cli.main(["generate", "--format",
                     "c3-k-r0550-p100-v1@10x10",      # non-canonical
                     "--source-fraction", "0.5",
                     "--paper", "A4-4mm", str(payload),
                     "-o", str(out_dir)]) == 0
    out = capsys.readouterr().out
    assert V2_GOLDEN_ID in out                        # echoed DISPLAY id
    assert "A4-4mm" in out and "3 dots/cell" in out
    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["format_id"] == parse_format_id(V2_GOLDEN_ID).spec_id
    assert manifest["paper"] == "A4-4mm"
    assert manifest["printer_id"] is None


def test_cli_capacity_on_a_format_id(capsys) -> None:
    assert cli.main(["capacity", "--format", "c2-k-r0700@53x37",
                     "--paper", "A4-4mm", "--source-fraction", "0.7",
                     "--pages", "2", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["paper"] == "A4-4mm"
    assert out["engine_dpi"] == 600 and out["dots_per_cell"] == 2
    assert out["spec_id"] == "1i300-k-r0700-p100-v1@53x37"
    assert out["display_id"] == "c2-k-r0700@53x37"
    assert out["field_cells"] == "3392x2368"
    assert out["max_payload_bytes"] > 0


def test_cli_selector_exclusions(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):        # --format is the whole identity
        cli.main(["capacity", "--format", "c3-k-r0550@10x10",
                  "--coding", "c3-r0550", "--source-fraction", "0.5"])
    with pytest.raises(SystemExit):        # printers left the v2 path
        cli.main(["capacity", "--format", "c3-k-r0550@10x10",
                  "--printer", "default", "--source-fraction", "0.5"])
    with pytest.raises(SystemExit):        # dial parity with --coding
        cli.main(["capacity", "--format", "c3-k-r0550@10x10"])
    with pytest.raises(SystemExit):        # paper is a v2 control
        cli.main(["capacity", "--profile", "resilient", "--paper", "A4-4mm"])
    with pytest.raises(SystemExit):        # legacy spelling -> fossil hint
        cli.main(["capacity", "--format", "c3-r0550@2240x1536",
                  "--source-fraction", "0.5"])


def test_cli_legacy_paths_still_resolve(capsys) -> None:
    assert cli.main(["capacity", "--profile", "resilient",
                     "--payload-bytes", "100000"]) == 0
    out = capsys.readouterr().out
    assert "printer: default" in out
    assert "net_area_basis: media" in out
