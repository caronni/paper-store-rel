"""Cross-tree pin: two implementations of ONE printed-format string law.

WP-1.2 (2026-08-22, RULINGS B8).  ``holo2.format.lattice`` is not a
carry — it is a REIMPLEMENTATION against a design (``docs/FORMAT-SPACE.md``
§6), because holo2 builds a different ``Coding``, has no ``CodecProfile``
hierarchy and has no ``FORMAT_ROWS`` route.  An AST carry pair would fail
on every function and force an ``ADAPTED`` entry apiece: guard mass with
no signal (L17).  What matters is not that the two trees share lines, it
is that they agree on the STRING LAW — and a behavioural oracle is the
right shape for that, exactly as ``test_oracle_tiles.py`` already uses
one for ``TileFormat`` vs ``FormatSpec``.

Five things are compared, in the order a decode meets them:

(a) the canonical spelling and the v2 row seed, over a battery of ids
    covering all three families, both pitch token forms, non-canonical
    spellings and mixed cmy8 triplets — because a seed IS an id and a
    one-character disagreement descrambles every pilot word to coin
    flips;
(b) the family seed, which must be the FROZEN v1 template on both sides
    under a v2 identity (P10) — the asymmetry the whole placement
    lineage rests on;
(c) for K ids, the codec facts a decode actually reads: the physical
    ``pitch`` (holo2 spells it ``pitch_in``; ``src/holo`` keeps a
    ``cell_dots`` beside it and this compares the PITCHES, which is the
    fact both trees agree on — C3, RULINGS G4, 2026-08-22),
    ``n_sites``, ``symbol_bits``, ``n_transmitted_slots``,
    ``fec_profile_id``, plus the tile-counter round trip;
(c2) for COLOUR ids, the same discipline over what a colour ROW carries
    (C2, 2026-08-22, RULINGS G2): stream ids, per-stream symbol widths
    and fountain domains, the pooled flag, the codec id, the FEC bank
    ids, the dust count and the dust base cycle.  holo2 builds these
    rows and refuses only the CODEC, so every fact on them is a fact
    two independent arithmetics must agree on;
(d) the legacy identities through the ``L:`` route, in both trees, with
    holo2's ``L:`` marker as the only difference between the two
    spellings — and refusal parity wherever the two trees state the
    same rule.

Nothing here is retyped: v1's values come from calling v1 (the e012
lesson — retyped ground truth forks silently).  Both packages may be
imported HERE, outside the holo2 tree, which is the standing every
oracle in this directory has.
"""
from __future__ import annotations

import pytest

from holo.format.lattice import parse_format_id as h_parse
from holo.format.resolve import resolve_format_ref as h_resolve

from holo2.format.format_v1 import coding_for as h2_coding_for
from holo2.format.format_v1 import tile_format as h2_tile_format
from holo2.format.fossils import FOSSILS as H2_FOSSILS
from holo2.format.lattice import parse_format_id as h2_parse
from holo2.format.registry_rows import tile_format_for as h2_tile_format_for
from holo2.format.resolve import format_row_for as h2_format_row_for
from holo2.format.resolve import resolve_format_ref as h2_resolve

# Every family, both pitch token forms, canonical and not, uniform and
# mixed cmy8 triplets, default and non-default site counts, and an
# off-600 pitch.  The GRAMMAR is total over all of these on both sides,
# and since C3b so is CONSTRUCTION: every member is in ``K_BUILDABLE``
# or ``COLOUR_BUILDABLE`` below.
IDENTITY_BATTERY = [
    # canonical, K
    "c2-k-r0700@53x37",
    "c3-k-r0550@10x10",
    "c2-k-r0550-p300@10x10",
    "c4-k-r0550@26x18",
    "c1-k-r0700@10x10",
    "c2-k-r0850@76x53",
    "1i400-k-r0700@40x28",
    # canonical, colour
    "c2-cmy7@52x36",
    "c3-cmy7@35x24",
    "c2-cmy8-r0700@53x37",
    "c2-cmy8-r0550x0550x0547@53x37",
    "c2-cmy8-r0550-p300@10x10",
    # ...and the two colour ids at pitches holo2 used to refuse.  They
    # BUILD since C3b (RULINGS H1(a), 2026-08-22): a pitch is data, and
    # the raster path — which has no family — reads any of them.
    "c1-cmy8-r0700@10x10",
    "1i400-cmy8-r0700@10x10",
    # NON-canonical spellings: both trees must normalize them the same
    # way or one of them stores a second seed for one format.
    "2i600-k-r0700@53x37",
    "c2-k-r0700-p100-v1@53x37",
    "c2-cmy8-r0700x0700x0700-p120-v1@53x37",
    "c2-cmy7-p120-v1@52x36",
    "1i200-k-r0550@10x10",
]

#: The battery members holo2 builds a K codec for.
#:
#: **This is now the WHOLE K half of the battery** (C3b, RULINGS H1(a),
#: 2026-08-22 evening).  Two rungs joined in one day: ``c2-k-r0850@76x53``
#: under G3 (rung parity — ``r0850`` was an uncarried rung, refusal H2,
#: retired the day its mother-code data landed), and then the three
#: PITCHES ``c4-k-r0550@26x18``, ``c1-k-r0700@10x10`` and
#: ``1i400-k-r0700@40x28`` under H1(a) ("every registered pitch class
#: (c1..c4) and every lawful rational builds"), which retired H4 and
#: with it the ``SCOPE_REFUSALS`` table that used to sit below.  They did
#: not move into a weaker comparison: every one of them is now compared
#: member by member against ``src/holo``'s own codec facts, which is a
#: strictly stronger statement than "holo2 refuses this by name".
K_BUILDABLE = [
    "c2-k-r0700@53x37",
    "c3-k-r0550@10x10",
    "c2-k-r0550-p300@10x10",
    "c4-k-r0550@26x18",
    "c1-k-r0700@10x10",
    "c2-k-r0850@76x53",
    "1i400-k-r0700@40x28",
    "2i600-k-r0700@53x37",
    "c2-k-r0700-p100-v1@53x37",
    "1i200-k-r0550@10x10",
]

#: The battery members that are lawful COLOUR identities: holo2 builds
#: a full row for each (RULINGS G2) and refuses only the codec.  The
#: last two joined at C3b with their K siblings above — a pitch outside
#: the old scope was refused on the ROW, before the family mattered.
COLOUR_BUILDABLE = [
    "c2-cmy7@52x36",
    "c3-cmy7@35x24",
    "c2-cmy8-r0700@53x37",
    "c2-cmy8-r0550x0550x0547@53x37",
    "c2-cmy8-r0550-p300@10x10",
    "c1-cmy8-r0700@10x10",
    "1i400-cmy8-r0700@10x10",
    "c2-cmy8-r0700x0700x0700-p120-v1@53x37",
    "c2-cmy7-p120-v1@52x36",
]

#: The legacy identities holo2 carries, keyed as the two catalogues key
#: them: BARE.  ``src/holo`` resolves that string directly; holo2 takes
#: it only behind ``L:`` and returns it marked (RULINGS G1).  Derived
#: from holo2's own catalogue so a carried entry cannot be forgotten
#: here — what it is checked against is ``src/holo``'s live answer.
LEGACY_IDENTITIES = sorted(H2_FOSSILS)


# ------------------------------- (a) canonical spelling and the v2 seed

@pytest.mark.parametrize("format_id", IDENTITY_BATTERY)
def test_the_two_grammars_agree_on_identity(format_id: str) -> None:
    """Same canonical id, same seed bytes, same tile matrix."""
    theirs, ours = h_parse(format_id), h2_parse(format_id)
    assert ours.spec_id == theirs.spec_id
    assert ours.display_id == theirs.display_id
    assert ours.seed == theirs.seed
    assert ours.tiles_yx == theirs.tiles_yx
    assert ours.seed == b"holo/v2/" + ours.spec_id.encode()


# ------------------------------------------------------ (b) family seed

@pytest.mark.parametrize("format_id", IDENTITY_BATTERY)
def test_the_two_grammars_agree_on_the_frozen_family_seed(
        format_id: str) -> None:
    """P10 on both sides: a v2 identity's family seed is still v1."""
    ours = h2_parse(format_id)
    assert ours.family_seed == h_parse(format_id).family_seed
    assert ours.family_seed.startswith(b"holo/v1/sites/p")


# ------------------------------------------------------- (c) codec facts

@pytest.mark.parametrize("format_id", K_BUILDABLE)
def test_the_k_codec_facts_are_identical(format_id: str) -> None:
    """Member by member, on the surface a decode actually reads.

    The same shape ``test_oracle_tiles.py`` uses for the legacy rows,
    applied to the v2 namespace: two independent arithmetics for one
    printed sheet, so a fork in either shows up as a disagreement rather
    than as a silently different keystream.
    """
    theirs = h_parse(format_id)
    coding_id, _, tiles = theirs.spec_id.partition("@")
    tiles_y, tiles_x = (int(part) for part in tiles.split("x"))
    ours = h2_tile_format(coding_id, (tiles_y, tiles_x))

    assert ours.spec_id == theirs.spec_id
    assert ours.seed == theirs.seed
    assert ours.family_seed == theirs.family_seed
    assert ours.pitch_in == theirs.pitch
    assert ours.rate_id == theirs.rate_id
    assert ours.n_sites == theirs.n_sites
    assert ours.n_filler == theirs.n_filler
    assert ours.tile_user_bits == theirs.tile_user_bits
    assert ours.symbol_bits == theirs.symbol_bits
    assert ours.n_transmitted_slots == theirs.n_transmitted_slots
    assert ours.codec_id == theirs.codec_id
    assert ours.codec_family.value == theirs.codec_family.value
    assert ours.fec_profile_id == \
        theirs.stream_profile("main").fec.profile_id
    assert ours.stream_ids == theirs.stream_ids
    assert ours.cells_yx == theirs.cells_yx
    assert ours.tiles_per_page == theirs.tiles_per_page
    assert ours.max_pages == theirs.max_pages
    for counter in (0, 1, ours.tiles_per_page - 1):
        assert ours.tile_address(counter) == theirs.tile_address(counter)
        assert ours.tile_counter(*theirs.tile_address(counter)) == counter


# EVERY BATTERY MEMBER IS NOW BUILDABLE IN BOTH TREES (C3b, RULINGS
# H1(a), 2026-08-22 evening).  A ``SCOPE_REFUSALS`` table and a
# ``test_what_holo2_names_but_will_not_build`` stood here: five lawful
# identities ``src/holo`` builds and holo2 refused by name, four of them
# for their PITCH and one (``c2-k-r0850``) for a rung.  Both causes are
# gone — G3 carried the rungs, H1(a) deleted the pitch scope — so the
# declared divergence they pinned no longer exists, and the ids they
# named moved up into ``K_BUILDABLE``/``COLOUR_BUILDABLE`` where the
# full member-by-member comparison covers them.  The table is DELETED
# rather than emptied: a parametrization over an empty list is a skip
# wearing a test's name, and this file's whole claim is that the two
# trees name and build the same string space.


# ------------------------------------------------ (c2) the colour facts

@pytest.mark.parametrize("format_id", COLOUR_BUILDABLE)
def test_the_colour_row_facts_are_identical(format_id: str) -> None:
    """Member by member, on everything a colour ROW carries.

    RULINGS G2 (2026-08-22): holo2 implements the colour FORMATS and
    fails fatally only at the codec.  So every fact below is one two
    independent arithmetics compute — the stream layout, the frozen
    fountain domains, the pooled outer code, the derived codec and bank
    names, the furniture — and a disagreement in any of them would be a
    colour port built on a different sheet than the one ``src/holo``
    emits.  The bank IDS matter as much as the widths: they are hashed
    into persisted certificate and decoder identities.
    """
    theirs = h_parse(format_id).coding
    row = h2_format_row_for(format_id, 1)
    codec = row.codec
    assert codec is not None                      # colour rows carry one
    assert row.row_id == h_parse(format_id).spec_id
    assert row.seed == h_parse(format_id).seed
    assert row.codec_family.value == theirs.codec_family.value
    assert row.codec_id == theirs.codec.codec_id == codec.codec_id
    assert row.pooled_fountain == theirs.pooled_fountain
    assert row.pitch_in == theirs.pitch
    assert codec.n_sites == theirs.codec.n_sites
    assert codec.n_dust == theirs.codec.n_dust
    assert codec.dust_base_cycle == theirs.codec.dust_base_cycle
    assert codec.bits_per_mapper_unit == theirs.codec.bits_per_mapper_unit
    assert (codec.cells_per_mapper_unit
            == theirs.codec.cells_per_mapper_unit)
    assert codec.payload_cells == theirs.codec.payload_cells
    assert row.stream_ids == theirs.codec.stream_ids == codec.stream_ids
    assert (codec.fec_profile_ids
            == tuple(stream.fec.profile_id for stream in theirs.codec.streams))
    for mine, stream in zip(row.streams, theirs.codec.streams):
        assert mine.stream_id == stream.stream_id
        assert mine.symbol_bits == stream.symbol_bits
        assert mine.fountain_aux == stream.fountain_aux
    for mine, stream in zip(codec.streams, theirs.codec.streams):
        assert mine.fec.user_bits == stream.fec.user_bits
        assert (mine.fec.transmitted_bits
                == stream.fec.transmitted_bits)
        assert mine.fec.children == tuple(
            (child.code_id, child.shortened_info_tail)
            for child in stream.fec.children)


@pytest.mark.parametrize("format_id", COLOUR_BUILDABLE)
def test_a_colour_row_refuses_the_k_tile_chain_by_name(
        format_id: str) -> None:
    """F1: the ONE thing holo2 will not do with a colour row.

    Every decode composition asks for the tile-chain view in a provider
    constructor, so this fires before the first fire.  The fork it
    prevents is the ``-x1`` dust bug's class, one level up: a colour row
    read by the K chain would be a three-stream sheet decoded as one
    stream of the wrong width, silently.
    """
    row = h2_format_row_for(format_id, 1)
    with pytest.raises(ValueError, match="colour codecs arrive with the "
                                         "colour port"):
        h2_tile_format_for(row)


# ----------------------------------------------- (d) legacy identities

@pytest.mark.parametrize("spec_id", LEGACY_IDENTITIES)
def test_the_legacy_route_agrees_byte_for_byte(spec_id: str) -> None:
    """One route, two trees, one seed.

    These are the printed and golden-bearing record; the seed keys the
    AES-CTR keystream that a real scan is descrambled with, so this is
    the tightest cross-tree assertion in the wave.  holo2 takes the
    identity only behind ``L:`` and returns it marked (RULINGS G1);
    ``src/holo`` accepts both spellings and returns the bare one.  The
    marker is a NAME — the seed, the geometry and every codec fact
    below are compared unmarked.
    """
    theirs = h_resolve(f"L:{spec_id}")
    ours = h2_resolve(f"L:{spec_id}")
    assert theirs.spec_id == spec_id
    assert ours.spec_id == "L:" + spec_id
    assert ours.seed == theirs.seed
    row = h2_format_row_for(f"L:{spec_id}", 1)
    assert row.row_id == "L:" + theirs.spec_id
    assert row.seed == theirs.seed
    assert row.cells_yx == theirs.layout.cells_yx
    assert row.pitch_in == theirs.pitch
    assert row.codec_family.value == theirs.codec_family.value
    assert row.codec_id == theirs.codec_id
    assert row.pooled_fountain == theirs.coding.pooled_fountain
    assert row.stream_ids == theirs.stream_ids
    for mine, stream in zip(row.streams, theirs.stream_profiles):
        assert mine.stream_id == stream.stream_id
        assert mine.symbol_bits == stream.symbol_bits
        assert mine.fountain_aux == stream.fountain_aux
    if row.codec is None:                         # K: no CodecFacts
        assert theirs.codec_family.value == "k"
        return
    # COLOUR: the frozen derived NAMES and the furniture, which is where
    # a branch-era identity actually lives.  ``cmy8-presence-r0700-p120-x1``
    # has no v2 spelling and is hashed into persisted certificate and
    # decoder identities — sheet I's VERIFIED state replays through
    # exactly these characters.
    assert row.codec.fec_profile_ids == tuple(
        stream.fec.profile_id for stream in theirs.coding.codec.streams)
    assert row.codec.n_dust == theirs.coding.codec.n_dust
    assert row.codec.n_sites == theirs.coding.codec.n_sites
    assert (row.codec.dust_base_cycle
            == theirs.coding.codec.dust_base_cycle)
    for mine, stream in zip(row.codec.streams, theirs.coding.codec.streams):
        assert mine.fec.children == tuple(
            (child.code_id, child.shortened_info_tail)
            for child in stream.fec.children)
    # The rung TOKEN is per-family: cmy8 spells a triplet, cmy7 spells
    # none at all (its joint bank is baked per generation, which is the
    # whole reason the grammar refuses a cmy7 rung token).
    if row.codec_family.value == "cmy8":
        assert row.codec.rungs == tuple(
            stream.fec.children[0].code_id
            for stream in theirs.coding.codec.streams)
    else:
        assert row.codec.rungs == ()


def test_a_bare_legacy_spelling_refuses_on_the_holo2_side(
        ) -> None:
    """The declared divergence, pinned so it stays declared.

    ``src/holo`` keeps a bare-legacy route because ITS persisted states
    hold bare ids; holo2 deleted it (RULINGS G1) because holo2 writes
    the ``L:`` form everywhere, so a bare string can only come from
    outside.  A refusal here that stopped being a refusal would quietly
    give every printed sheet two names again.
    """
    for spec_id in LEGACY_IDENTITIES:
        assert h_resolve(spec_id).spec_id == spec_id      # theirs: fine
        with pytest.raises(ValueError, match="L:<id>"):
            h2_resolve(spec_id)


# ------------------------------------------------------ refusal parity

#: One id per refusal class both trees state the same rule for — and
#: since C3b (2026-08-22) that is EVERY refusal holo2 has on this axis.
#: Three rows that used to be holo2-only are retired outright: H1
#: (colour construction) under RULINGS G2, H2 (uncarried rungs) under
#: G3, and H3/H4 (holo2's pitch scope) under G4 and then H1(a).  What is
#: left below is the grammar and the family algebra, which both trees
#: derive from the same frozen numbers, so a one-sided refusal here
#: would be a genuine fork rather than a declared divergence.
SHARED_REFUSALS = [
    ("G1", "c2-k-r0700"),
    ("G2", "c2-k-r0700@axb"),
    ("G3", "c2-k-r0700@0x10"),
    ("G4", "c2-k-r0700@512x513"),
    ("G5", "c2@10x10"),
    ("G6", "c9-k-r0700@10x10"),
    ("G7", "0i300-k-r0700@10x10"),
    ("G8", "zz-k-r0700@10x10"),
    ("G9", "c2-r0700@52x36"),
    ("G10", "c2-k-p100-r0700@10x10"),
    ("G11", "c2-k@10x10"),
    ("G12", "c2-cmy7-r0550@52x36"),
    ("G13", "c2-cmy8-r0550x0550@53x37"),
    ("A1", "c2-k-r0300@10x10"),
    ("A2", "c2-k-r0700-v2@10x10"),
    ("A3", "c2-k-r0700-p99@10x10"),
    ("A4", "c2-cmy7-p140@52x36"),
    ("A5", "c2-cmy8-r0700-p100@53x37"),
    ("A7", "c2-k-r0550-p2210@1x1"),
]

# Ruling 2026-09-04 (docs/CMY8-COLUMN-GROUPS.md; scope ruled to src/holo
# generation + the holo3 receiver, holo2 untouched): src/holo ACCEPTS an
# uneven cmy8 triplet as a column-group pool, holo2 keeps refusing it —
# a documented divergence, not a fork: holo2 has no colour receive, so
# there is no sheet it could read differently.
INTENDED_DIVERGENCES = [
    ("A6", "c2-cmy8-r0700x0700x0550@53x37", "mixes user widths"),
]


@pytest.mark.parametrize("row,format_id", SHARED_REFUSALS,
                         ids=[row[0] for row in SHARED_REFUSALS])
def test_refusal_parity(row: str, format_id: str) -> None:
    """A string one tree refuses and the other accepts is a fork.

    It would mean one receiver can be handed an identity the other
    cannot name — and since the id IS the seed, "cannot name" and
    "cannot read" are the same sentence.
    """
    with pytest.raises(ValueError):
        h_parse(format_id)
    with pytest.raises(ValueError):
        h2_parse(format_id)


@pytest.mark.parametrize("row,format_id,holo2_reason", INTENDED_DIVERGENCES,
                         ids=[row[0] for row in INTENDED_DIVERGENCES])
def test_intended_divergence(row: str, format_id: str,
                             holo2_reason: str) -> None:
    """The one string the trees are RULED to disagree on (2026-09-04)."""
    assert h_parse(format_id).pooled_fountain
    with pytest.raises(ValueError, match=holo2_reason):
        h2_parse(format_id)


def test_a_legacy_coding_name_parses_in_neither_tree() -> None:
    """The namespaces are disjoint by grammar as well as by precedence.

    Both trees route a legacy K name to the catalogue with a message
    that says so, rather than parsing it into a NEIGHBOURING v2
    identity — which is the fork the ``L:`` ruling exists to make
    unrepresentable.
    """
    for coding_id in ("c2-r0700", "c3-r0550", "c2-r0550"):
        with pytest.raises(ValueError, match="unknown family"):
            h_parse(f"{coding_id}@10x10")
        with pytest.raises(ValueError, match="unknown family"):
            h2_parse(f"{coding_id}@10x10")
        with pytest.raises(ValueError):
            h2_coding_for(f"{coding_id}-bogus")
