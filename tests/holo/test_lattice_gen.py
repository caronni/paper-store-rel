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
from holo.format.fossils import resolve_fossil_spec
from holo.format.lattice import parse_format_id
from holo.format.layout import MEDIA_MM, derive_field
from holo.format.layout import page_dots_xy as frozen_page_dots_xy
from holo.format.profiles import Family
from holo.gen import sheet as sheet_mod
from holo.gen.emit import emit_volume
from holo.gen.plan import max_payload_bytes, plan_volume
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
def test_fit_matrix_lands_where_the_v1_derivation_lands(
    paper: str, pitch: str, tiles_yx: tuple[int, int],
) -> None:
    """The demotion is arithmetic-preserving: placing the fitted matrix
    reproduces derive_field's page, field, origin and borders exactly."""
    # What fit() itself answers, folded in 2026-09-20 from test_fit_table,
    # which was this same table read one line shorter.
    assert fit(paper, pitch) == tiles_yx, "fit() must land on the table row"
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
    with pytest.raises(ValueError):
        sheet_layout(resolve_fossil_spec("c3-r0550@2240x1536"), "A4-6mm")


def test_paper_profiles_are_the_documented_bundles() -> None:
    assert sheet_mod.DEFAULT_PAPER == "A4-6mm"
    assert {name: (p.media_id, p.margin_mm)
            for name, p in PAPER_PROFILES.items()} == {
        "A4-6mm": ("a4", 6.0),
        "A4-4mm": ("a4", 4.0),
        "A3-6mm": ("a3", 6.0),
        "A3-4mm": ("a3", 4.0),
    }


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
    spec = resolve_fossil_spec("c3-r0550@2240x1536")
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


# -- the furniture density axis: capacity and generate agree ------------
#
# ``p`` — the site cells a tile spends on furniture — is part of every
# identity the lattice mints, and ``capacity`` has always priced any
# lawful one.  ``generate`` could not emit them: the colour composer's
# furniture derivation hardcoded 20 dust, so a cmy8 row at p != 120 was
# priced and then refused at emission with a shape mismatch between the
# codec's ``4096 - p`` states and 3,976 offered cells.  K was never
# affected (its filler count already came from the row), which is what
# made the disagreement a FAMILY asymmetry rather than a missing feature
# — the two doors of one generator answering differently about the same
# identity.  One row per family per sampled p, priced and then emitted at
# exactly the price.
P_AXIS_EMISSION_ROWS = (
    "c3-k-r0550-p100@10x10",                  # the printed K density
    "c3-k-r0550-p150@10x10",
    "c3-k-r0550-p300@10x10",
    "c2-cmy8-r0550-p101@10x10",               # one dust cell per tile
    "c2-cmy8-r0550@10x10",                    # p120, the printed density
    "c2-cmy8-r0550-p172@10x10",
    "c2-cmy8-r0550-p300@10x10",
    "c2-cmy8-r0700x0700x0547-p300@10x10",     # uneven triplet x p300
    "c2-cmy-r0700-p101@10x10",                # cmy: M in one dust cell
    "c2-cmy-r0700@10x10",
    "c3-cmy-r0850@10x10",
    "c2-cmy-r0700-p300@10x10",
    "c2-cmy-r0775x0700@10x10",                # the uneven probe pair
    "c2-cmy-r0775x0700-p300@10x10",
)


@pytest.mark.parametrize("format_id", P_AXIS_EMISSION_ROWS)
def test_capacity_and_generate_agree_at_every_lawful_furniture_density(
    tmp_path: Path, format_id: str,
) -> None:
    """What ``capacity`` prices, ``generate`` emits — for every family.

    The payload is exactly ``max_payload_bytes(spec, q, 1)``, so this
    also pins the price as the real one-page ceiling and not an
    optimistic estimate: one byte of the planner's arithmetic wrong in
    either direction and the volume comes back on two pages.
    """
    spec = parse_format_id(format_id)
    assert spec.payload_cells == 4096 - spec.n_sites
    assert spec.n_sites == 100 + spec.n_filler
    cap = max_payload_bytes(spec, 0.5, 1)
    assert cap > 0

    vol = emit_volume(spec, bytes(i % 251 for i in range(cap)), 0.5,
                      tmp_path / "v", paper="A4-4mm")
    assert vol.plan.n_pages == 1
    assert len(vol.pages) == 1
    page = vol.pages[0]
    assert page.ps_path.read_text(encoding="ascii").strip().endswith("%%EOF")
    packed = np.load(page.gt_path)
    if spec.codec_family is Family.K:
        assert packed.ndim == 2
    else:
        assert packed.ndim == 3 and packed.shape[0] == 3


# The receiver's p300 volume e2e
# (src/holo/receiver/tests/test_h3_e2e_p_axis.py) renders THIS row at
# THIS dial and payload size.  The sizing is a claim about the planner,
# so it is pinned here, where the planner lives: that module may not
# import src/holo at all (the receiver import firewall,
# test_h3_hygiene.py), and a stimulus sized at its one-page ceiling
# would report a planner error as a second page and a confusing sha
# mismatch rather than as a failed assertion.
P_AXIS_E2E_ROW = "c2-cmy8-r0550-p300@10x10"
P_AXIS_E2E_SOURCE_FRACTION = 0.35
P_AXIS_E2E_PAYLOAD_BYTES = 12_000


def test_the_p300_e2e_payload_sits_under_its_one_page_ceiling() -> None:
    spec = parse_format_id(P_AXIS_E2E_ROW)
    ceiling = max_payload_bytes(spec, P_AXIS_E2E_SOURCE_FRACTION, 1)
    assert ceiling == 20_702
    assert P_AXIS_E2E_PAYLOAD_BYTES < 0.75 * ceiling
    assert plan_volume(spec, P_AXIS_E2E_PAYLOAD_BYTES,
                       P_AXIS_E2E_SOURCE_FRACTION).n_pages == 1


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
    assert "c2-cmy-<rung>@53x37" in out        # design §6: cmy's skeleton
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
    # R21 (2026-10-12): --printer default is a lawful engine for K, and
    # the manifest records it; it carries no colour record.
    assert cli.main(["generate", "--format", V2_GOLDEN_ID,
                     "--source-fraction", "0.5", "--printer", "default",
                     str(payload), "-o", str(tmp_path / "named")]) == 0
    assert "engine default" in capsys.readouterr().out
    named = json.loads((tmp_path / "named" / "manifest.json").read_text())
    assert named["printer_id"] == "default"


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
    payload = tmp_path / "p.bin"
    payload.write_bytes(b"x")
    # 2026-10-12 (cmy generator W2b, CMY-DESIGN R21): --coding survives on
    # `generate` alone, as the evidence recipes' door, and still refuses
    # beside --format; on `capacity` it is no option at all.
    with pytest.raises(SystemExit):        # --format is the whole identity
        cli.main(["generate", "--format", "c3-k-r0550@10x10",
                  "--coding", "c3-r0550", "--source-fraction", "0.5",
                  str(payload)])
    with pytest.raises(SystemExit):
        cli.main(["capacity", "--coding", "c3-r0550",
                  "--source-fraction", "0.5"])
    # 2026-10-11 (cmy generator W2a, CMY-DESIGN R21): --printer beside
    # --format names the EMISSION engine, never a geometry — lawful for a
    # registry id; what refuses now is an engine the registry lacks.
    with pytest.raises(SystemExit, match="unknown emission engine"):
        cli.main(["capacity", "--format", "c3-k-r0550@10x10",
                  "--printer", "no-such-engine", "--source-fraction", "0.5"])
    with pytest.raises(SystemExit):        # dial parity, v2 and fossil
        cli.main(["capacity", "--format", "c3-k-r0550@10x10"])
    with pytest.raises(SystemExit):
        cli.main(["capacity", "--format", "L:c3-r0550@2240x1536"])
    # 2026-10-12 (W2b, R21): `--profile resilient --paper A4-4mm` -> the
    # profile flag is gone; paper stays a v2 control, a fossil refuses it.
    with pytest.raises(SystemExit):
        cli.main(["capacity", "--profile", "resilient",
                  "--source-fraction", "0.5"])
    with pytest.raises(SystemExit, match="carries its own page"):
        cli.main(["capacity", "--format", "L:c3-r0550@2240x1536",
                  "--source-fraction", "0.5", "--paper", "A4-4mm"])
    # a bare legacy id refuses with the L: spelling it wants
    with pytest.raises(SystemExit, match="L:c3-r0550@2240x1536"):
        cli.main(["capacity", "--format", "c3-r0550@2240x1536",
                  "--source-fraction", "0.5"])
    with pytest.raises(SystemExit, match="unknown fossil"):
        cli.main(["capacity", "--format", "L:c3-r0550@9x9",
                  "--source-fraction", "0.5"])


def test_cli_legacy_paths_still_resolve(capsys) -> None:
    # 2026-10-12 (W2b, R21): `capacity --profile resilient` -> its row's
    # L: fossil; no printer is named unless --printer says so.
    head = ["capacity", "--format", "L:c3-r0550@2240x1536",
            "--source-fraction", "0.5", "--payload-bytes", "100000"]
    assert cli.main(head) == 0
    out = capsys.readouterr().out
    assert "printer" not in out
    assert "net_area_basis: media" in out
    assert cli.main([*head, "--printer", "default"]) == 0
    assert "printer: default" in capsys.readouterr().out
