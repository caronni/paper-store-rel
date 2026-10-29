from __future__ import annotations

import dataclasses
import inspect
from fractions import Fraction

import numpy as np
import pytest

from holo.receiver.format import identity, keystream, pilots

from holo.receiver.tests import _h3_fixture_geometry, _h3_support

K = identity.Family.K
CMY7 = identity.Family.CMY7
CMY8 = identity.Family.CMY8
CMY = identity.Family.CMY

V01 = ("r0550", "r0550", "r0547")

# hand-copied second copy of src/holo/receiver/format/identity._FOSSILS (2026-08-29):
# row_id -> (seed, tiles_yx, pitch, family, rungs, n_sites, pooled)
FOSSILS: dict[str, tuple] = {
    "c3-r0550@2240x1536": (
        b"holo/v1/c3-r0550/2240x1536", (35, 24), Fraction(1, 200),
        K, ("r0550",), 100, False),
    "c2-r0550@3328x2304": (
        b"holo/v1/c2-r0550/3328x2304", (52, 36), Fraction(1, 300),
        K, ("r0550",), 100, False),
    "c2-r0700@3328x2304": (
        b"holo/v1/c2-r0700/3328x2304", (52, 36), Fraction(1, 300),
        K, ("r0700",), 100, False),
    "c2-r0700@3392x2368": (
        b"holo/v1/c2-r0700/3392x2368", (53, 37), Fraction(1, 300),
        K, ("r0700",), 100, False),
    "c2-cmy7-p120-v0@3328x2304": (
        b"holo/v1/c2-cmy7-p120-v0/3328x2304", (52, 36), Fraction(1, 300),
        CMY7, (), 120, False),
    "c3-cmy7-p120-v0@2240x1536": (
        b"holo/v1/c3-cmy7-p120-v0/2240x1536", (35, 24), Fraction(1, 200),
        CMY7, (), 120, False),
    "c2-cmy8-p120-v0@3328x2304": (
        b"holo/v1/c2-cmy8-p120-v0/3328x2304", (52, 36), Fraction(1, 300),
        CMY8, V01, 120, False),
    "c3-cmy8-p120-v0@2240x1536": (
        b"holo/v1/c3-cmy8-p120-v0/2240x1536", (35, 24), Fraction(1, 200),
        CMY8, V01, 120, False),
    "c2-cmy8-p120-v1@3328x2304": (
        b"holo/v1/c2-cmy8-p120-v1/3328x2304", (52, 36), Fraction(1, 300),
        CMY8, V01, 120, True),
    "c3-cmy8-p120-v1@2240x1536": (
        b"holo/v1/c3-cmy8-p120-v1/2240x1536", (35, 24), Fraction(1, 200),
        CMY8, V01, 120, True),
    "c2-cmy8-p120-v1@3392x2368": (
        b"holo/v1/c2-cmy8-p120-v1/3392x2368", (53, 37), Fraction(1, 300),
        CMY8, V01, 120, True),
    "c4-r0550@1664x1152": (
        b"holo/v1/c4-r0550/1664x1152", (26, 18), Fraction(1, 150),
        K, ("r0550",), 100, False),
    "c2-cmy8-r0700-p120-x1@3392x2368": (
        b"holo/v1/c2-cmy8-r0700-p120-x1/3392x2368", (53, 37),
        Fraction(1, 300), CMY8, ("r0700", "r0700", "r0700"), 120, True),
    "c2-cmy8-r0850-p120-x1@3392x2368": (
        b"holo/v1/c2-cmy8-r0850-p120-x1/3392x2368", (53, 37),
        Fraction(1, 300), CMY8, ("r0850", "r0850", "r0850"), 120, True),
    # the one v2-namespace seed: FORMAT-SPACE §8 row 15, e035 sheet J
    "c2-cmy8-r0547@53x37": (
        b"holo/v2/c2-cmy8-r0547@53x37", (53, 37),
        Fraction(1, 300), CMY8, ("r0547", "r0547", "r0547"), 120, True),
}

FOSSIL_IDS = tuple(FOSSILS)


def test_fossil_catalogue_key_set_is_exactly_the_frozen_rows():
    _h3_support.assert_golden("fossil key set",
                              sorted(identity._FOSSILS), sorted(FOSSILS))
    assert len(identity._FOSSILS) == 15


def test_exactly_one_fossil_is_a_v2_namespace_row():
    v2 = sorted(row_id for row_id, entry in identity._FOSSILS.items()
                if entry[0].startswith(b"holo/v2/"))
    _h3_support.assert_golden("v2-namespace fossils", v2,
                              ["c2-cmy8-r0547@53x37"])


def test_the_bare_spelling_no_longer_reaches_sheet_j_s_printed_seed():
    frozen = FOSSILS["c2-cmy8-r0547@53x37"][0]
    bare = identity.resolve_format_ref("c2-cmy8-r0547@53x37")
    assert bare.display_id == "c2-cmy8-r0547@53x37"
    assert bare.row_id == "1i300-cmy8-r0547-p120-v1@53x37"
    assert bare.seed != frozen, (
        "the bare spelling reaches the printed seed again — if the "
        "canonical rule was reverted the fossil is redundant; if it was "
        "not, this test is broken")
    fossil = identity.resolve_format_ref("L:c2-cmy8-r0547@53x37")
    assert fossil.seed == frozen
    assert dataclasses.replace(bare, row_id=fossil.row_id,
                               display_id=fossil.display_id,
                               seed=fossil.seed) == fossil


@pytest.mark.parametrize("row_id", FOSSIL_IDS)
def test_fossil_identity_is_seed_byte_frozen(row_id: str):
    seed, tiles_yx, pitch, family, rungs, sites, pooled = FOSSILS[row_id]
    row = identity.resolve_format_ref("L:" + row_id)
    _h3_support.assert_golden(f"{row_id} seed", row.seed, seed)
    assert row.row_id == "L:" + row_id
    assert row.tiles_yx == tiles_yx
    assert row.pitch_in == pitch
    assert row.family is family
    assert row.n_sites == sites
    assert row.pooled_fountain is pooled
    assert row.n_dust == (0 if family is K else sites - 100)
    assert row.sites_seed == f"holo/v1/sites/p{sites}".encode()
    assert row.display_id == row.row_id
    assert row.cells_yx == (tiles_yx[0] * 64, tiles_yx[1] * 64)
    assert tuple(child[0] for stream in row.streams
                 for child in stream.rung_children) == (
        rungs if family is not CMY7 else ("r0550", "r0625", "r0625"))


@pytest.mark.parametrize("row_id", FOSSIL_IDS)
def test_fountain_aux_dispatch_uses_none_for_k_never_zero(row_id: str):
    _seed, _tiles, _pitch, family, _rungs, _sites, _pooled = FOSSILS[row_id]
    auxes = tuple(stream.fountain_aux for stream in
                  identity.resolve_format_ref("L:" + row_id).streams)
    if family is K:
        assert auxes == (None,)
        assert auxes[0] is None
        assert auxes[0] != 0
    elif family is CMY7:
        assert auxes == (0,)
        assert auxes[0] is not None
    else:
        assert auxes == (1, 2, 3)
        assert all(aux is not None for aux in auxes)


@pytest.mark.parametrize("ref", [
    "c3-k-r0550@7x7",
    "c2-k-r0700@53x37",
    "1i200-k-r0550@7x7",
])
def test_v2_grammar_k_rows_also_carry_none_aux(ref: str):
    row = identity.resolve_format_ref(ref)
    assert row.family is K
    assert row.streams[0].fountain_aux is None


@pytest.mark.parametrize("ref,auxes", [
    ("c2-cmy7@52x36", (0,)),
    ("c3-cmy8-r0550@10x10", (1, 2, 3)),
    ("c3-cmy8-r0550x0550x0547@10x10", (1, 2, 3)),
])
def test_v2_grammar_colour_rows_carry_integer_aux(ref: str, auxes: tuple):
    row = identity.resolve_format_ref(ref)
    assert tuple(s.fountain_aux for s in row.streams) == auxes


def test_colour_stream_aux_matches_the_keystream_domain_constants():
    row = identity.resolve_format_ref("L:c2-cmy8-p120-v1@3392x2368")
    assert tuple(s.stream_id for s in row.streams) == ("C", "M", "Y")
    assert tuple(s.fountain_aux for s in row.streams) == (
        keystream.COLOR_STREAM_C, keystream.COLOR_STREAM_M,
        keystream.COLOR_STREAM_Y)
    assert tuple(s.plane for s in row.streams) == (0, 1, 2)
    cmy7 = identity.resolve_format_ref("L:c2-cmy7-p120-v0@3328x2304")
    assert cmy7.streams[0].fountain_aux == keystream.COLOR_STREAM_MAIN
    assert cmy7.streams[0].plane == keystream.PLANE_K


# I-2 (CMY-RECEIVER-PLAN, A0 2026-10-12): a stream is named by its id and
# a plane is a property only toner streams have.  No row carries a label
# stream until Family.CMY lands (A1), so the label stream here is built
# by hand, as cmy's hi will be: label 0, dither aux 1, no plane, no
# fountain aux (the -v1 pool).
def _label_stream(stream_id: str = "hi", label_index: int = 0,
                  ) -> identity.StreamFact:
    return identity.StreamFact(stream_id, None, None, (("r0700", 120),),
                               2768, 2767, label_index=label_index,
                               dither_aux=label_index + 1)


@pytest.mark.parametrize("stream_id,label_index", [("hi", 0), ("lo", 1)])
def test_plane_raises_on_a_label_stream_naming_it(stream_id: str,
                                                  label_index: int):
    stream = _label_stream(stream_id, label_index)
    assert stream.plane_index is None
    with pytest.raises(identity.StreamHasNoPlane, match=repr(stream_id)):
        _ = stream.plane
    with pytest.raises(TypeError):
        _ = stream.plane


@pytest.mark.parametrize("row_id", FOSSIL_IDS)
def test_every_toner_stream_keeps_its_plane_and_carries_no_label(row_id):
    _seed, _tiles, _pitch, family, _rungs, _sites, _pooled = FOSSILS[row_id]
    streams = identity.resolve_format_ref("L:" + row_id).streams
    assert all(s.label_index is None for s in streams)
    assert tuple(s.plane for s in streams) == tuple(
        s.plane_index for s in streams)
    if family is CMY8:
        assert tuple(s.plane for s in streams) == (0, 1, 2)
        assert tuple(s.dither_aux for s in streams) == tuple(
            keystream.COLOR_STREAM_AUX[s.stream_id] for s in streams)
        assert tuple(s.dither_aux for s in streams) == (1, 2, 3)
    else:
        assert tuple(s.plane for s in streams) == (keystream.PLANE_K,)
        assert tuple(s.dither_aux for s in streams) == (None,)


@pytest.mark.parametrize("plane_index,label_index", [(None, None), (0, 0)])
def test_a_stream_is_a_toner_stream_or_a_label_stream_never_both(
        plane_index, label_index):
    with pytest.raises(ValueError, match="exactly one"):
        identity.StreamFact("x", plane_index, None, (("r0700", 120),),
                            2768, 2767, label_index=label_index,
                            dither_aux=None)


@pytest.mark.parametrize("ref,user_bits,symbol_bits,children", [
    ("L:c2-r0700@3392x2368", 2748, 2747, (("r0700", 100),)),
    ("L:c2-cmy8-p120-v0@3328x2304", 2088, 2087, (("r0550", 120),)),
    ("L:c2-cmy8-r0700-p120-x1@3392x2368", 2728, 2727, (("r0700", 120),)),
    ("L:c2-cmy8-r0850-p120-x1@3392x2368", 3368, 3367, (("r0850", 120),)),
    ("L:c2-cmy7-p120-v0@3328x2304", 5974, 5973,
     (("r0550", 0), ("r0625", 677), ("r0625", 677))),
])
def test_stream_bank_algebra(ref: str, user_bits: int, symbol_bits: int,
                             children: tuple):
    row = identity.resolve_format_ref(ref)
    assert all(s.user_bits == user_bits for s in row.streams)
    assert all(s.symbol_bits == symbol_bits for s in row.streams)
    assert row.streams[0].rung_children == children
    assert all(s.symbol_bits == s.user_bits - 1 for s in row.streams)


def test_cmy8_v0_third_stream_rides_the_narrow_r0547_rung():
    row = identity.resolve_format_ref("L:c2-cmy8-p120-v0@3328x2304")
    assert row.streams[2].rung_children == (("r0547", 120),)
    assert identity.LADDER["r0547"] == identity.LADDER["r0550"] == 2240


def test_v2_row_id_is_canonical_and_the_seed_is_the_row_id():
    row = identity.resolve_format_ref("c3-k-r0550-p100-v1@7x7")
    assert row.row_id == "1i200-k-r0550-p100-v1@7x7"
    assert row.seed == b"holo/v2/1i200-k-r0550-p100-v1@7x7"
    assert row.seed == identity.SEED_NAMESPACE + row.row_id.encode()
    assert identity.resolve_format_ref("c3-k-r0550@7x7").row_id == row.row_id
    assert identity.resolve_format_ref("1i200-k-r0550@7x7").row_id \
        == row.row_id


def test_display_id_is_the_short_spelling_and_round_trips():
    row = identity.resolve_format_ref("c3-k-r0550-p100-v1@7x7")
    assert row.display_id == "c3-k-r0550@7x7"
    assert identity.resolve_format_ref(row.display_id).row_id == row.row_id
    assert identity.resolve_format_ref(row.row_id).row_id == row.row_id
    assert identity.resolve_format_ref(row.row_id).seed == row.seed
    fossil = identity.resolve_format_ref("L:c2-r0700@3392x2368")
    assert fossil.display_id == fossil.row_id


def test_mint_format_is_the_parameter_door_and_equals_resolve():
    minted = identity.mint_format(
        pitch=Fraction(1, 200), family=identity.Family.K,
        rungs=("r0550",), sites=100, gen=1, tiles_yx=(7, 7))
    resolved = identity.resolve_format_ref("c3-k-r0550@7x7")
    assert minted.row_id == resolved.row_id == "1i200-k-r0550-p100-v1@7x7"
    assert minted.display_id == resolved.display_id == "c3-k-r0550@7x7"
    assert minted.seed == resolved.seed
    assert minted.sites_seed == resolved.sites_seed
    with pytest.raises(ValueError, match="rung arity must be 3"):
        identity.mint_format(
            pitch=Fraction(1, 300), family=identity.Family.CMY8,
            rungs=("r0550",), sites=120, gen=1, tiles_yx=(10, 10))


@pytest.mark.parametrize("pitch", (Fraction(0), Fraction(-1, 300)))
def test_mint_format_refuses_a_non_positive_pitch(pitch):
    with pytest.raises(ValueError, match="positive rational"):
        identity.mint_format(
            pitch=pitch, family=identity.Family.K, rungs=("r0550",),
            sites=100, gen=1, tiles_yx=(7, 7))


def test_canonical_ids_and_seeds_ignore_the_pitch_class_table(monkeypatch):
    refs = ("c3-k-r0550@7x7", "1i200-k-r0550@7x7", "c2-cmy7@52x36",
            "c3-cmy8-r0550@10x10", "c3-cmy8-r0550x0550x0547@10x10",
            "1i120-k-r0550@7x7", "L:c2-r0700@3392x2368")
    before = {ref: identity.resolve_format_ref(ref) for ref in refs}
    monkeypatch.setitem(identity.PITCH_CLASSES, "c5", Fraction(1, 120))
    monkeypatch.setitem(identity._CLASS_BY_PITCH, Fraction(1, 120), "c5")
    for ref in refs:
        row = identity.resolve_format_ref(ref)
        assert row.row_id == before[ref].row_id, ref
        assert row.seed == before[ref].seed, ref
    assert identity.resolve_format_ref("1i120-k-r0550@7x7").display_id \
        == "c5-k-r0550@7x7"


def test_a_canonical_id_survives_a_defaults_change(monkeypatch):
    row = identity.resolve_format_ref("c3-k-r0550@7x7")
    monkeypatch.setitem(identity._DEFAULT_SITES, identity.Family.K, 120)
    monkeypatch.setattr(identity, "_DEFAULT_GEN", 2)
    again = identity.resolve_format_ref(row.row_id)
    assert again.row_id == row.row_id
    assert again.seed == row.seed
    assert again.n_sites == row.n_sites


def test_cmy8_single_rung_token_broadcasts_to_the_triplet():
    broadcast = identity.resolve_format_ref("c3-cmy8-r0550@10x10")
    explicit = identity.resolve_format_ref("c3-cmy8-r0550x0550x0547@10x10")
    assert broadcast.row_id == "1i200-cmy8-r0550-p120-v1@10x10"
    assert explicit.row_id == "1i200-cmy8-r0550x0550x0547-p120-v1@10x10"
    assert broadcast.display_id == "c3-cmy8-r0550@10x10"
    assert explicit.display_id == "c3-cmy8-r0550x0550x0547@10x10"
    assert tuple(s.rung_children[0][0] for s in broadcast.streams) == (
        "r0550", "r0550", "r0550")
    assert tuple(s.rung_children[0][0] for s in explicit.streams) == V01
    assert broadcast.seed != explicit.seed


def test_v2_grammar_pooling_and_sites_defaults():
    assert identity.resolve_format_ref("c3-cmy8-r0550@10x10").pooled_fountain
    assert not identity.resolve_format_ref("c3-k-r0550@7x7").pooled_fountain
    assert not identity.resolve_format_ref("c2-cmy7@52x36").pooled_fountain
    assert identity.resolve_format_ref("c3-k-r0550@7x7").n_sites == 100
    assert identity.resolve_format_ref("c2-cmy7@52x36").n_sites == 120
    assert identity.resolve_format_ref("c3-cmy8-r0550@10x10").n_sites == 120


REFUSALS = [
    ("c2-cmy8-r0700x0700x0547-p2208@10x10", "no room for metadata and a symbol"),
    ("c2-cmy7-r0550@10x10", "cmy7 rung arity must be 0"),
    ("c2-k@7x7", "k rung arity must be 1"),
    ("c2-k-r0700@600x600", "counter space"),
    ("c2-cmy8-r0700-p100@10x10", "needs at least one dust site"),
    ("c2-cmy-r0700-p100@10x10", "M is printed only in dust"),
    ("c2-cmy-r0700x0700x0700@10x10", "cmy rung arity must be 2"),
    ("L:c2-cmy-r0700@10x10", "never parsed"),
    ("c2-k-r0700-p99@7x7", "below the 100-site word floor"),
    ("c2-cmy7-p130@10x10", "bakes its joint pack7 bank at p120"),
    ("c2-k-r0700-v2@7x7", "generation v2 is not defined"),
    ("c2-k-r0700-p100-r0550@7x7", "unrecognized or misordered token"),
    ("c2-k-r9999@7x7", "unknown LDPC rung"),
    ("c2-r0700@3392x2368", "unknown family"),
    ("c9-k-r0700@7x7", "unregistered pitch class"),
    ("x2-k-r0700@7x7", "neither a registered class nor NiD"),
    ("c2-k-r0700", "needs a tile matrix"),
    ("c2-k-r0700@7by7", "tile matrix must be TYxTX"),
    ("c2-k-r0700@0x7", "must be at least 1x1"),
    ("c2-k-r0700@7x0", "must be at least 1x1"),
    ("c2@7x7", "needs at least pitch and family"),
]


@pytest.mark.parametrize("ref,reason", REFUSALS)
def test_v2_grammar_refusals_name_their_reason(ref: str, reason: str):
    with pytest.raises(ValueError, match=reason):
        identity.resolve_format_ref(ref)


# CMY-DESIGN §2.4 (R1, R12): the canonical id spells pitch, the rung pair
# (contracted when uniform), sites and generation; display drops defaults.
CMY_SPELLINGS = [
    ("c2-cmy-r0775x0700@53x37", "1i300-cmy-r0775x0700-p120-v1@53x37"),
    ("c3-cmy-r0850@35x24", "1i200-cmy-r0850-p120-v1@35x24"),
    ("c2-cmy-r0700-p300@10x10", "1i300-cmy-r0700-p300-v1@10x10"),
]


@pytest.mark.parametrize("display,canonical", CMY_SPELLINGS)
def test_cmy_display_and_canonical_spellings_round_trip(display: str,
                                                        canonical: str):
    row = identity.resolve_format_ref(display)
    assert (row.row_id, row.display_id) == (canonical, display)
    assert row.seed == identity.SEED_NAMESPACE + canonical.encode()
    again = identity.resolve_format_ref(canonical)
    assert (again.row_id, again.display_id, again.seed) == (
        canonical, display, row.seed)


def test_a_cmy_row_is_two_label_streams_over_the_four_state_alphabet():
    row = identity.resolve_format_ref("c2-cmy-r0700@10x10")
    assert row.family is CMY and row.pooled_fountain
    assert row.row_id == "1i300-cmy-r0700-p120-v1@10x10"
    assert tuple(s.rung_children for s in row.streams) == (
        (("r0700", 120),), (("r0700", 120),))
    assert tuple((s.stream_id, s.plane_index, s.label_index, s.dither_aux,
                  s.fountain_aux) for s in row.streams) == (
        ("hi", None, 0, 1, None), ("lo", None, 1, 2, None))
    assert (row.state_ids, row.word_states, row.dust_base_cycle,
            row.n_dust) == ((0, 1, 2, 4), (0, 1), (), 20)
    with pytest.raises(identity.StreamHasNoPlane, match="'hi'"):
        _ = row.streams[0].plane


def test_unknown_fossil_never_falls_through_to_the_grammar():
    with pytest.raises(ValueError, match="unknown fossil id"):
        identity.resolve_format_ref("L:c2-r0700@9999x9999")
    with pytest.raises(ValueError, match="never parsed"):
        identity.resolve_format_ref("L:c3-k-r0550@7x7")


def test_resolve_format_ref_takes_only_the_id():
    assert tuple(inspect.signature(identity.resolve_format_ref).parameters
                 ) == ("ref",)


def test_max_pages_is_the_counter_space_floor_division():
    row = identity.resolve_format_ref("c3-k-r0550@7x7")
    assert row.max_pages == 5349
    assert identity.MAX_TILES == 1 << 18 == 262144
    assert row.max_pages == identity.MAX_TILES // row.tiles_per_page
    assert row.max_pages * row.tiles_per_page <= identity.MAX_TILES
    assert (row.max_pages + 1) * row.tiles_per_page > identity.MAX_TILES


def test_ladder_pitch_classes_and_margins_are_frozen_tables():
    _h3_support.assert_golden("LADDER", dict(identity.LADDER), {
        "r0547": 2240, "r0550": 2240, "r0625": 2560,
        "r0700": 2880, "r0775": 3200, "r0850": 3520})
    _h3_support.assert_golden("PITCH_CLASSES", dict(identity.PITCH_CLASSES), {
        "c1": Fraction(1, 600), "c2": Fraction(1, 300),
        "c3": Fraction(1, 200), "c4": Fraction(1, 150)})
    _h3_support.assert_golden("MARGIN_MM", dict(identity.MARGIN_MM), {
        "default": 6.0, "hp-m281": 6.0, "hp-m281-ink": 4.5,
        "xerox-altalink-c8245": 6.0})
    assert identity.HW_DPI == 600
    assert identity.A4_MM == (210.0, 297.0)
    assert identity.A3_MM == (297.0, 420.0)
    assert identity.N_BITS == 4096 and identity.CRC_BITS == 32
    assert identity.METADATA_BITS_PER_TILE == 1


def test_page_dots_xy_anchors():
    assert identity.page_dots_xy((210.0, 297.0)) == (4960, 7016)
    assert identity.page_dots_xy((297.0, 420.0)) == (7016, 9920)
    assert all(value % 8 == 0
               for value in identity.page_dots_xy((210.0, 297.0)))


# frozen 2026-08-29 from tests/holo (verify_pilots_identity FIELD_TABLE)
FIELD_TABLE = [
    ((210.0, 297.0), 6.0, 2, (3328, 2304)),
    ((210.0, 297.0), 6.0, 3, (2240, 1536)),
    ((210.0, 297.0), 6.0, 4, (1664, 1152)),
    ((210.0, 297.0), 4.0, 2, (3392, 2368)),
    ((210.0, 297.0), 4.0, 3, (2240, 1536)),
    ((210.0, 297.0), 4.5, 2, (3392, 2368)),
    ((297.0, 420.0), 4.0, 2, (4864, 3392)),
]


@pytest.mark.parametrize("media,margin,cell_dots,cells_yx", FIELD_TABLE)
def test_derive_field(media: tuple, margin: float, cell_dots: int,
                      cells_yx: tuple):
    assert identity.derive_field(media, margin, cell_dots) == cells_yx
    assert all(value % pilots.TILE_CELLS == 0 for value in cells_yx)


@pytest.mark.parametrize("coding_id,printer_id,ref", [
    ("c2-r0700", "hp-m281-ink", "L:c2-r0700@3392x2368"),
    ("c2-r0700", "default", "L:c2-r0700@3328x2304"),
    ("c3-r0550", "default", "L:c3-r0550@2240x1536"),
    ("c2-r0550", "xerox-altalink-c8245", "L:c2-r0550@3328x2304"),
    ("c4-r0550", "hp-m281", "L:c4-r0550@1664x1152"),
])
def test_coding_printer_ref_resolves_to_the_same_row_as_the_l_spelling(
        coding_id: str, printer_id: str, ref: str):
    assert identity.coding_printer_ref(coding_id, printer_id) == ref
    sugar = identity.resolve_format_ref(
        identity.coding_printer_ref(coding_id, printer_id))
    assert sugar.seed == identity.resolve_format_ref(ref).seed
    assert sugar.row_id == ref


def test_addressing_round_trips_over_the_whole_counter_space():
    row = identity.resolve_format_ref("L:c2-r0700@3392x2368")
    assert row.tiles_per_page == 1961
    assert row.max_pages == 133
    assert row.payload_cells == 3996
    assert row.n_transmitted_slots == 3996
    rng = np.random.default_rng(20260829)
    for _ in range(64):
        page = int(rng.integers(0, row.max_pages))
        ty = int(rng.integers(0, 53))
        tx = int(rng.integers(0, 37))
        counter = row.tile_counter(page, ty, tx)
        assert counter == page * 1961 + ty * 37 + tx
        assert row.tile_address(counter) == (page, ty, tx)


def test_colour_rows_leave_3976_payload_cells():
    row = identity.resolve_format_ref("L:c2-cmy8-p120-v1@3392x2368")
    assert row.n_sites == 120
    assert row.payload_cells == 3976
    assert row.dust_base_cycle == (1, 2, 4, 5, 6, 7)
    assert row.word_states == (0, 3)
    assert row.bits_per_mapper_unit == 3
    assert row.cells_per_mapper_unit == 1
    cmy7 = identity.resolve_format_ref("L:c2-cmy7-p120-v0@3328x2304")
    assert cmy7.dust_base_cycle == (1, 2, 4, 5, 6)
    assert cmy7.bits_per_mapper_unit == 11
    assert cmy7.cells_per_mapper_unit == 4
    k_row = identity.resolve_format_ref("L:c2-r0700@3392x2368")
    assert k_row.dust_base_cycle == ()
    assert k_row.word_states == (0, 1)
    assert (k_row.bits_per_mapper_unit, k_row.cells_per_mapper_unit) == (1, 1)


#: The sheet's own identity, 2026-09-05: the slot redraw and the
#: scramble comparison left here (0.36 s of 0.47 s) were SELF-comparisons,
#: and the wiring they state is pinned below on c3-k-r0550@7x7 and against
#: the independent v1 kernels on THIS row in test_h3_drift_format.
def test_build_site_geometry_k_row():
    row = identity.resolve_format_ref("L:c2-r0700@3392x2368")
    geo = identity.build_site_geometry(row)
    assert row.cells_yx == (3392, 2368)
    assert geo.word_cells_yx.shape == (100, 2)
    assert geo.extra_cells_yx.shape == (0, 2)
    assert np.array_equal(geo.word_cells_yx,
                          pilots.word_site_cells_yx(row.sites_seed))
    assert np.array_equal(geo.shorten_flat,
                          pilots.site_cell_indices(row.sites_seed, 0))
    assert geo.payload_flat.size == 3996
    assert np.array_equal(
        np.sort(np.concatenate([geo.shorten_flat, geo.payload_flat])),
        np.arange(4096))
    assert geo.slot_a.shape == (row.max_pages * row.tiles_per_page,)
    for arr in (geo.word_cells_yx, geo.shorten_flat, geo.payload_flat,
                geo.slot_a, geo.slot_b):
        assert not arr.flags.writeable


def test_build_site_geometry_colour_row_shapes():
    row = identity.resolve_format_ref("L:c2-cmy8-r0700-p120-x1@3392x2368")
    geo = identity.build_site_geometry(row)
    assert geo.word_cells_yx.shape == (100, 2)
    assert geo.extra_cells_yx.shape == (20, 2)
    assert np.array_equal(geo.extra_cells_yx,
                          pilots.dust_site_cells_yx(row.sites_seed, 20))
    assert np.array_equal(
        geo.payload_flat,
        pilots.color_payload_cell_indices(row.sites_seed))
    assert geo.payload_flat.size == 3976


#: The UNCACHED builder, 2026-09-05: this is the one test that reads a
#: geometry's FRESH `_scramble`, so the session memo in
#: _h3_fixture_geometry must not hand it a row the lane already scrambled.
def test_build_site_geometry_slots_span_counter_space_and_scramble_is_lazy():
    row = identity.resolve_format_ref("c3-k-r0550@7x7")
    geo = _h3_fixture_geometry.build_site_geometry_uncached(row)
    n_counters = row.max_pages * row.tiles_per_page
    assert geo.slot_a.size == n_counters
    slot_a, slot_b = keystream.slot_perm_params(
        row.seed, np.arange(n_counters, dtype=np.int64), 3996)
    assert np.array_equal(geo.slot_a, slot_a)
    assert np.array_equal(geo.slot_b, slot_b)
    for page in (0, 1, 2, row.max_pages - 1):
        assert np.array_equal(
            identity.scramble_plane(row, geo, page),
            keystream.payload_bits(row.seed, keystream.PLANE_K, page,
                                   (448, 448)))
    assert sorted(geo._scramble) == [0, 1, 2, row.max_pages - 1]


def test_a_directly_constructed_geometry_still_memos_scramble():
    row = identity.resolve_format_ref("c3-k-r0550@7x7")
    built = identity.build_site_geometry(row)
    forked = identity.SiteGeometry(
        built.word_cells_yx, built.extra_cells_yx, built.shorten_flat,
        built.payload_flat, built.slot_a, built.slot_b)
    assert forked._scramble == {}
    plane = identity.scramble_plane(row, forked, 0)
    assert 0 in forked._scramble
    assert np.array_equal(plane, forked._scramble[0])
