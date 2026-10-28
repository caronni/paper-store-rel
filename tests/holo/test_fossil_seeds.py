"""FORMAT-SPACE P0 goldens: the fossil AES seed strings, frozen as bytes.

The golden dict below is a deliberate second copy of the catalogue —
never regenerate it from the module under test. A mismatch on any byte
is a printed-format fork.
"""
from __future__ import annotations

import hashlib

import pytest

from holo.format import fossils
from holo.format.descriptor import CODINGS

GOLDEN_SEEDS: dict[str, bytes] = {
    "c3-r0550@2240x1536": b"holo/v1/c3-r0550/2240x1536",
    "c2-r0550@3328x2304": b"holo/v1/c2-r0550/3328x2304",
    "c2-r0700@3328x2304": b"holo/v1/c2-r0700/3328x2304",
    "c2-r0700@3392x2368": b"holo/v1/c2-r0700/3392x2368",
    "c2-cmy7-p120-v0@3328x2304": b"holo/v1/c2-cmy7-p120-v0/3328x2304",
    "c3-cmy7-p120-v0@2240x1536": b"holo/v1/c3-cmy7-p120-v0/2240x1536",
    "c2-cmy8-p120-v0@3328x2304": b"holo/v1/c2-cmy8-p120-v0/3328x2304",
    "c3-cmy8-p120-v0@2240x1536": b"holo/v1/c3-cmy8-p120-v0/2240x1536",
    "c2-cmy8-p120-v1@3328x2304": b"holo/v1/c2-cmy8-p120-v1/3328x2304",
    "c3-cmy8-p120-v1@2240x1536": b"holo/v1/c3-cmy8-p120-v1/2240x1536",
    "c2-cmy8-p120-v1@3392x2368": b"holo/v1/c2-cmy8-p120-v1/3392x2368",
    "c4-r0550@1664x1152": b"holo/v1/c4-r0550/1664x1152",
    "c2-cmy8-r0700-p120-x1@3392x2368":
        b"holo/v1/c2-cmy8-r0700-p120-x1/3392x2368",
    "c2-cmy8-r0850-p120-x1@3392x2368":
        b"holo/v1/c2-cmy8-r0850-p120-x1/3392x2368",
}

GOLDEN_FAMILY_SEEDS = {
    100: b"holo/v1/sites/p100",
    120: b"holo/v1/sites/p120",
}

# Frozen derived-name strings for the three branch-minted fossil codings
# (hashed into persisted certificate/decoder identities — renames fork
# sheet-I state replay).
GOLDEN_FOSSIL_CODING_NAMES = {
    "c4-r0550": ("k-v1", ("k-r0550-p100-v1",)),
    "c2-cmy8-r0700-p120-x1": (
        "cmy8-presence-r0700-p120-x1",
        ("cmy8-C-r0700-p120-x1", "cmy8-M-r0700-p120-x1",
         "cmy8-Y-r0700-p120-x1")),
    "c2-cmy8-r0850-p120-x1": (
        "cmy8-presence-r0850-p120-x1",
        ("cmy8-C-r0850-p120-x1", "cmy8-M-r0850-p120-x1",
         "cmy8-Y-r0850-p120-x1")),
}


def test_catalogue_matches_goldens_exactly() -> None:
    assert set(fossils.FOSSILS) == set(GOLDEN_SEEDS)
    for spec_id, seed in GOLDEN_SEEDS.items():
        fossil = fossils.FOSSILS[spec_id]
        assert fossil.seed == seed, f"{spec_id}: seed byte fork"
        assert fossil.spec_id == spec_id


def test_family_seeds_frozen() -> None:
    assert fossils.FAMILY_SEED_P100 == GOLDEN_FAMILY_SEEDS[100]
    assert fossils.FAMILY_SEED_P120 == GOLDEN_FAMILY_SEEDS[120]


def test_catalog_backed_fossils_reconstruct() -> None:
    """Recipe/record agreement, asserted independently of the module's
    own import-time self-check."""
    from holo.format.descriptor import FormatSpec
    from holo.format.layout import MEDIA_MM
    checked = 0
    for fossil in fossils.FOSSILS.values():
        coding = CODINGS.get(fossil.coding_id)
        if coding is None:
            continue
        spec = FormatSpec(coding=coding, media_id="a4",
                          media_mm=MEDIA_MM["a4"],
                          margin_mm=fossil.margin_mm)
        assert spec.seed == fossil.seed
        assert spec.layout.cells_yx == fossil.cells_yx
        checked += 1
    assert checked == 11  # three branch codings resolve via FOSSIL_CODINGS


def test_branch_fossil_codings_frozen() -> None:
    assert set(fossils.FOSSIL_CODINGS) == set(GOLDEN_FOSSIL_CODING_NAMES)
    for coding_id, (codec_id, bank_ids) in \
            GOLDEN_FOSSIL_CODING_NAMES.items():
        fc = fossils.FOSSIL_CODINGS[coding_id]
        assert fc.codec_id == codec_id
        assert fc.bank_ids == bank_ids
    x1 = fossils.FOSSIL_CODINGS["c2-cmy8-r0700-p120-x1"]
    assert x1.pooled and x1.n_filler == 20 and x1.cell_dots == 2
    c4 = fossils.FOSSIL_CODINGS["c4-r0550"]
    assert not c4.pooled and c4.n_filler == 0 and c4.cell_dots == 4


def test_all_fossils_resolve_to_specs() -> None:
    """Every fossil rebuilds a full FormatSpec whose seed byte-matches."""
    for spec_id, seed in GOLDEN_SEEDS.items():
        spec = fossils.resolve_fossil_spec(spec_id)
        assert spec.seed == seed
        assert spec.spec_id == spec_id
    x1 = fossils.resolve_fossil_spec("L:c2-cmy8-r0700-p120-x1@3392x2368")
    assert tuple(p.fec.profile_id for p in x1.stream_profiles) == \
        GOLDEN_FOSSIL_CODING_NAMES["c2-cmy8-r0700-p120-x1"][1]
    assert x1.codec_id == \
        GOLDEN_FOSSIL_CODING_NAMES["c2-cmy8-r0700-p120-x1"][0]
    assert x1.pooled_fountain and x1.tiles_per_page == 1961
    c4 = fossils.resolve_fossil_spec("c4-r0550@1664x1152")
    assert c4.rate_id == "r0550" and c4.cell_dots == 4
    assert c4.tiles_per_page == 468


def test_l_prefix_helpers() -> None:
    ref = "L:c2-cmy8-r0700-p120-x1@3392x2368"
    assert fossils.is_fossil_ref(ref)
    assert fossils.strip_fossil_ref(ref) == \
        "c2-cmy8-r0700-p120-x1@3392x2368"
    assert fossils.get_fossil(ref) is fossils.get_fossil(
        "c2-cmy8-r0700-p120-x1@3392x2368")
    with pytest.raises(ValueError):
        fossils.strip_fossil_ref("c2-r0700@3328x2304")
    with pytest.raises(KeyError, match="closest catalogue entries"):
        fossils.get_fossil("c2-r0700@9999x9999")


# Fossil EMISSION goldens: the branch-minted rows' printed bits, pinned
# on main.  The c4 cells digest is copied VERBATIM from the c4-row
# branch's committed golden (tests/holo/test_roundtrip.py at 97e59e1);
# the -x1 emit digests were computed on main and verified byte-identical
# against the c4-row tree's own emission (2026-08-19) — the branch never
# pinned them (its F7 debt, closed here).
GOLDEN_C4_CELLS_PAGE0 = ("133ff5f65685a9625012830e2cf0d9d6"
                         "a0d9bc6268dfbaf00f935e2cdf826cff")
GOLDEN_X1_EMIT = {
    "c2-cmy8-r0700-p120-x1@3392x2368": (
        b"holo-x1-r0700",
        "348083d2afac16758ff92a92ae65026c44cd4cf7ddc34ac67b29ea643eda747a",
        "eb064ce03a7d7f3d65ca463d162b1a228c8b49d0bcbe83dff6e16a4b0ba5a79c"),
    "c2-cmy8-r0850-p120-x1@3392x2368": (
        b"holo-x1-r0850",
        "f49d80329352bbdc01e7eb9c6b872fc629645e692001a9855f32bd4341600b36",
        "ad2b8d5577ee1065af2946593bb852ab4cbf5d148899c60cd763d42476c3ddc7"),
}


def test_fossil_c4_emission_golden() -> None:
    import numpy as np
    from holo.core import fountain
    from holo.gen import plan
    from holo.gen.compose import compose_page_cells
    from holo.gen.emit import METADATA_VERSION, source_packed_for
    spec = fossils.resolve_fossil_spec("c4-r0550@1664x1152")
    payload = hashlib.sha256(b"holo-c4").digest() * 200
    vplan = plan.plan_volume(spec, len(payload), 0.35)
    source = source_packed_for(payload, vplan)
    code = fountain.VolumeCode(
        vplan.k_total, vplan.symbol_bits, spec.seed,
        tiles_per_page=spec.tiles_per_page)
    esis = np.arange(spec.tiles_per_page, dtype=np.int64)
    cells = compose_page_cells(
        spec, 0, code.encode_symbols(source, esis), vplan.k_total,
        version=METADATA_VERSION)
    digest = hashlib.sha256(np.packbits(cells).tobytes()).hexdigest()
    assert digest == GOLDEN_C4_CELLS_PAGE0, "c4 printed-format fork"


@pytest.mark.parametrize("spec_id", sorted(GOLDEN_X1_EMIT))
def test_fossil_x1_emission_goldens(spec_id, tmp_path) -> None:
    from holo.gen.emit import emit_volume
    seed_bytes, ps_sha, gt_sha = GOLDEN_X1_EMIT[spec_id]
    spec = fossils.resolve_fossil_spec(spec_id)
    payload = hashlib.sha256(seed_bytes).digest() * 200
    volume = emit_volume(spec, payload, 0.5, tmp_path / "v")
    page = volume.pages[0]
    assert page.ps_sha256 == ps_sha, f"{spec_id}: PS fork"
    assert page.gt_sha256 == gt_sha, f"{spec_id}: GT fork"
