"""WP-1.2 goldens: the legacy AES seed strings, frozen as bytes.

The golden dict below is a deliberate second copy of the catalogue —
never regenerate it from the module under test.  A mismatch on any byte
is a printed-format fork.

That warning is ``tests/holo/test_fossil_seeds.py``'s, verbatim, and it
is the half of the two-witness discipline that lives outside the code:
``fossils._self_check()`` proves the RECIPE still rebuilds the RECORD at
import, and this file proves the record itself has not been edited to
match a moved recipe.  Twelve identities across FOUR KINDS of golden —
seed bytes, tile matrix, cell size, and the frozen codec/bank name
strings — each of which fails differently and none of which the others
would catch: L17's "bright-line identity anchors, kept rare so movement
stays alarming".

TWELVE entries: ``src/holo``'s fourteen minus ONLY the two
``cmy8-p120-v0`` rows (RULINGS G8, 2026-08-22 — cmy8-v0's three
independent fountains "go away", and after the sunset those two sheets
have no reader by design).  ``c4-r0550@1664x1152`` joined at C3b
(RULINGS H1): e033 sheet A is keyed by a v1 seed its v2 twin
``c4-k-r0550@26x18`` does not share, so it needs an ``L:`` line of its
own.  Seven of the twelve are COLOUR, and they carry a second kind of
golden: the frozen codec and FEC BANK id strings.  Those are not
decoration — they are hashed into persisted certificate and decoder
identities, so sheet I's VERIFIED state replays
bit-identically only while they are exactly these characters, and no
grammar can respell ``cmy8-presence-r0700-p120-x1``.

C2 (2026-08-22, RULINGS G1) added the ``L:`` marker to what a ROW
spells, and this file keeps the two apart on purpose: the catalogue is
KEYED by the bare spec id (that is the printed record's own string) and
every REFERENCE to it, including ``row_id``, carries the prefix.  The
goldens below are the bare record; ``LEGACY_REF`` builds the reference
from it, so a change to either half shows up here.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from holo2.format import fossils
from holo2.format.registry_rows import legacy_row

#: The one prefix, spelled here rather than imported: this file is the
#: second witness, and a witness that reads the code under test proves
#: nothing (the same reason every seed byte below is written out).
LEGACY_REF = "L:"

GOLDEN_SEEDS: dict[str, bytes] = {
    "c3-r0550@2240x1536": b"holo/v1/c3-r0550/2240x1536",
    "c2-r0550@3328x2304": b"holo/v1/c2-r0550/3328x2304",
    "c2-r0700@3328x2304": b"holo/v1/c2-r0700/3328x2304",
    "c2-r0700@3392x2368": b"holo/v1/c2-r0700/3392x2368",
    "c4-r0550@1664x1152": b"holo/v1/c4-r0550/1664x1152",
    "c2-cmy7-p120-v0@3328x2304":
        b"holo/v1/c2-cmy7-p120-v0/3328x2304",
    "c3-cmy7-p120-v0@2240x1536":
        b"holo/v1/c3-cmy7-p120-v0/2240x1536",
    "c2-cmy8-p120-v1@3328x2304":
        b"holo/v1/c2-cmy8-p120-v1/3328x2304",
    "c3-cmy8-p120-v1@2240x1536":
        b"holo/v1/c3-cmy8-p120-v1/2240x1536",
    "c2-cmy8-p120-v1@3392x2368":
        b"holo/v1/c2-cmy8-p120-v1/3392x2368",
    "c2-cmy8-r0700-p120-x1@3392x2368":
        b"holo/v1/c2-cmy8-r0700-p120-x1/3392x2368",
    "c2-cmy8-r0850-p120-x1@3392x2368":
        b"holo/v1/c2-cmy8-r0850-p120-x1/3392x2368",
}

GOLDEN_FAMILY_SEEDS = {
    100: b"holo/v1/sites/p100",
    120: b"holo/v1/sites/p120",
}

#: The tile matrix each frozen cell geometry is: 64 cells to a tile,
#: exactly, which is what makes holo2's recipe (``format_row`` on a tile
#: grid) able to rebuild a record ``src/holo`` derives from media minus
#: margins.  Written out rather than divided, so a changed tile size
#: shows up as a disagreement rather than as a quietly different grid.
GOLDEN_TILES = {
    "c3-r0550@2240x1536": (35, 24),
    "c2-r0550@3328x2304": (52, 36),
    "c2-r0700@3328x2304": (52, 36),
    "c2-r0700@3392x2368": (53, 37),
    "c4-r0550@1664x1152": (26, 18),
    "c2-cmy7-p120-v0@3328x2304": (52, 36),
    "c3-cmy7-p120-v0@2240x1536": (35, 24),
    "c2-cmy8-p120-v1@3328x2304": (52, 36),
    "c3-cmy8-p120-v1@2240x1536": (35, 24),
    "c2-cmy8-p120-v1@3392x2368": (53, 37),
    "c2-cmy8-r0700-p120-x1@3392x2368": (53, 37),
    "c2-cmy8-r0850-p120-x1@3392x2368": (53, 37),
}

#: What each printed sheet's cell PHYSICALLY MEASURES, as the exact
#: rational of an inch identity carries (C3, RULINGS G4, 2026-08-22 — it
#: was a count of dots on a hard-coded 600 grid).  A third independent
#: copy, for the same reason as the tile matrix: nothing in a v1
#: ``row_id`` or seed spells the cell size, so a repointed pitch in a
#: catalogue bundle would fork the printed sheet's raster while every
#: seed byte stayed green (measured, WP-1.2 review 2026-08-22).  Written
#: out per entry as ``Fraction(1, 300)``/``Fraction(1, 200)`` rather than
#: as a shared name, so a moved pitch class cannot move twelve goldens
#: at once — a golden that imports what it guards proves nothing.
GOLDEN_PITCH_IN = {
    "c3-r0550@2240x1536": Fraction(1, 200),
    "c2-r0550@3328x2304": Fraction(1, 300),
    "c2-r0700@3328x2304": Fraction(1, 300),
    "c2-r0700@3392x2368": Fraction(1, 300),
    "c4-r0550@1664x1152": Fraction(1, 150),
    "c2-cmy7-p120-v0@3328x2304": Fraction(1, 300),
    "c3-cmy7-p120-v0@2240x1536": Fraction(1, 200),
    "c2-cmy8-p120-v1@3328x2304": Fraction(1, 300),
    "c3-cmy8-p120-v1@2240x1536": Fraction(1, 200),
    "c2-cmy8-p120-v1@3392x2368": Fraction(1, 300),
    "c2-cmy8-r0700-p120-x1@3392x2368": Fraction(1, 300),
    "c2-cmy8-r0850-p120-x1@3392x2368": Fraction(1, 300),
}

#: The frozen DERIVED NAMES, per coding: (codec id, FEC bank ids).  A
#: third second-copy, and the one with no other witness in-tree: they
#: are hashed into persisted certificate and decoder identities, and the
#: v2 grammar cannot respell any of the colour ones (``pack7`` and
#: ``presence`` are tokens the mint dropped, ``x1`` a generation it
#: never had).  The K rows' bank ids are the SAME strings the v2 grammar
#: derives, which is correct and deliberate — same mathematical object,
#: same name (FORMAT-SPACE §6).
GOLDEN_CODEC_NAMES = {
    "c3-r0550": ("k-v1", ("k-r0550-p100-v1",)),
    "c2-r0550": ("k-v1", ("k-r0550-p100-v1",)),
    "c2-r0700": ("k-v1", ("k-r0700-p100-v1",)),
    "c4-r0550": ("k-v1", ("k-r0550-p100-v1",)),
    "c2-cmy7-p120-v0": ("cmy7-pack7-p120-v0", ("cmy7-p120-v0",)),
    "c3-cmy7-p120-v0": ("cmy7-pack7-p120-v0", ("cmy7-p120-v0",)),
    "c2-cmy8-p120-v1": ("cmy8-presence-p120-v0",
                        ("cmy8-C-p120-v0", "cmy8-M-p120-v0",
                         "cmy8-Y-p120-v0")),
    "c3-cmy8-p120-v1": ("cmy8-presence-p120-v0",
                        ("cmy8-C-p120-v0", "cmy8-M-p120-v0",
                         "cmy8-Y-p120-v0")),
    "c2-cmy8-r0700-p120-x1": ("cmy8-presence-r0700-p120-x1",
                              ("cmy8-C-r0700-p120-x1",
                               "cmy8-M-r0700-p120-x1",
                               "cmy8-Y-r0700-p120-x1")),
    "c2-cmy8-r0850-p120-x1": ("cmy8-presence-r0850-p120-x1",
                              ("cmy8-C-r0850-p120-x1",
                               "cmy8-M-r0850-p120-x1",
                               "cmy8-Y-r0850-p120-x1")),
}

#: The two entries of ``src/holo``'s fourteen that holo2 does NOT carry,
#: written out so their absence is asserted rather than assumed.
#: RULINGS G8 (2026-08-22): cmy8-v0 goes away, and after the sunset
#: nothing reads those two printed sheets.  They are now the ONLY two:
#: ``c4-r0550@1664x1152`` landed at C3b (RULINGS H1).
DROPPED_IDENTITIES = (
    "c2-cmy8-p120-v0@3328x2304",
    "c3-cmy8-p120-v0@2240x1536",
)


def test_catalogue_matches_goldens_exactly() -> None:
    """The record itself, against a copy that never imported it.

    Prevents the edit-the-record fork: a catalogue entry quietly adjusted
    to match a moved recipe would decode a printed sheet under a
    keystream nobody printed.  Every frozen field is compared — seed,
    spec id, tile matrix, cell pitch — because the last two are the
    recipe's INPUTS, and a wrong input forks the sheet as surely as a
    wrong seed byte does.  The cell size is compared through the
    bundle's EMISSION evidence (``cell_dots`` over ``engine_dpi``),
    which is the one thing in the bundle that is not the pitch the
    recipe reads — comparing ``params.pitch`` with itself would assert
    nothing (C3, RULINGS G4).
    """
    assert set(fossils.FOSSILS) == set(GOLDEN_SEEDS)
    for spec_id, seed in GOLDEN_SEEDS.items():
        fossil = fossils.FOSSILS[spec_id]
        assert fossil.seed == seed, f"{spec_id}: seed byte fork"
        assert fossil.spec_id == spec_id
        assert fossil.tiles_yx == GOLDEN_TILES[spec_id]
        assert fossil.coding.emitted_pitch_in == GOLDEN_PITCH_IN[spec_id]
        assert fossil.ref == LEGACY_REF + spec_id
        codec_id, bank_ids = GOLDEN_CODEC_NAMES[fossil.coding_id]
        assert fossil.coding.codec_id == codec_id
        assert fossil.coding.bank_ids == bank_ids


def test_the_dropped_identities_are_dropped() -> None:
    """RULINGS G8: cmy8-v0 goes away, and that is a DECISION.

    Asserted rather than assumed, because an absence is exactly what a
    later carry restores by accident.  ``src/holo`` reads these two
    sheets until the sunset; holo2 supersedes ``src/holo`` and does not,
    so after the sunset e030's and e032's -v0 CMY8 prints have no reader
    by design.  If one of them ever needs to come back, it comes back as
    a ruling and a diff, not as a quiet append.
    """
    assert not set(DROPPED_IDENTITIES) & set(fossils.FOSSILS)
    assert not {"c2-cmy8-p120-v0", "c3-cmy8-p120-v0"} & {
        fossil.coding_id for fossil in fossils.FOSSILS.values()}


def test_family_seeds_frozen() -> None:
    """The site-lattice seed, shared across the namespace split (P10).

    Prevents the tidy-looking fork: versioning the family seed to
    ``holo/v2/`` alongside the row seed would move every equal-density
    sheet off the measured E022/E023 site layout it was printed with.
    """
    assert fossils.FAMILY_SEED_P100 == GOLDEN_FAMILY_SEEDS[100]
    assert fossils.FAMILY_SEED_P120 == GOLDEN_FAMILY_SEEDS[120]


@pytest.mark.parametrize("spec_id", sorted(GOLDEN_SEEDS))
def test_the_recipe_rebuilds_the_record(spec_id: str) -> None:
    """Recipe/record agreement, asserted independently of the module's
    own import-time self-check.

    Two derivations of one byte string: the frozen table above, and the
    ordinary row constructor run on the frozen tile matrix.  A change to
    the v1 seed law, to a coding's pitch or to the 64-cell tile moves
    one and not the other — and each is checked, because each fails
    differently: the seed law changes the bytes, the tile size changes
    the cells the tile matrix rebuilds to, and the PITCH changes NEITHER
    (it is invisible to a v1 identity, which spells only coding name and
    cells) and so needs its own assertion.
    """
    tiles_yx = GOLDEN_TILES[spec_id]
    bundle = fossils.legacy_bundle_for(spec_id.split("@")[0])
    # THE RECIPE, spelled from the bundle rather than through a helper
    # (C4, RULINGS G5, 2026-08-22: ``fossils._legacy_row`` is deleted).
    # The input is this file's own golden tile matrix, which is what
    # keeps this a SECOND derivation and not a reading of the record.
    row = legacy_row(coding_id=bundle.coding_id, params=bundle.params,
                     tiles_yx=tiles_yx, pages=1,
                     codec_id=bundle.codec_id, bank_ids=bundle.bank_ids)
    assert row.row_id == LEGACY_REF + spec_id
    assert row.seed == GOLDEN_SEEDS[spec_id]      # ...and its cells, in it
    assert row.pitch_in == GOLDEN_PITCH_IN[spec_id]


@pytest.mark.parametrize("spec_id", sorted(GOLDEN_SEEDS))
def test_every_legacy_identity_resolves_to_its_frozen_row(
        spec_id: str) -> None:
    """The production route, byte-verified against the same goldens."""
    row = fossils.resolve_fossil_spec(spec_id)
    assert row.seed == GOLDEN_SEEDS[spec_id]
    assert row.row_id == LEGACY_REF + spec_id
    assert row.tiles_yx == GOLDEN_TILES[spec_id]
    codec_id, bank_ids = GOLDEN_CODEC_NAMES[spec_id.split("@")[0]]
    assert row.codec_id == codec_id
    if row.codec is not None:                     # colour carries them
        assert row.codec.fec_profile_ids == bank_ids
    prefixed = fossils.resolve_fossil_spec(LEGACY_REF + spec_id)
    assert prefixed == row


def test_sheet_a_needs_its_own_l_line_because_the_v2_twin_seeds_apart(
        ) -> None:
    """RULINGS H1 (2026-08-22), stated as an assertion rather than prose.

    "The c4 format is just ``1i150-k-r0550@26x18``" is true of the
    FORMAT and false of the IDENTITY: e033 sheet A was printed under the
    v1 seed, and the v2 twin of the same physical format seeds under
    ``holo/v2/``.  Two seeds are two AES-CTR keystreams, so reading the
    printed sheet through the twin descrambles every pilot word to coin
    flips.

    The fork this prevents is exactly the "it is just the v2 row"
    shortcut: an entry deleted from the catalogue as redundant, with the
    twin offered in its place.  Both spellings resolve here, and the
    test says out loud that they are not the same sheet.
    """
    from holo2.format.lattice import parse_format_id

    fossil = fossils.FOSSILS["c4-r0550@1664x1152"]
    twin = parse_format_id("c4-k-r0550@26x18")
    assert twin.tiles_yx == fossil.tiles_yx        # the same geometry...
    assert twin.params.pitch == GOLDEN_PITCH_IN[fossil.spec_id]  # ...pitch
    assert twin.seed == b"holo/v2/1i150-k-r0550-p100-v1@26x18"
    assert twin.seed != fossil.seed                # ...and NOT the sheet


def test_the_e029_e032_identity_carries_its_evidence() -> None:
    """The catalogue is the only place the code states which sheets exist.

    Prevents the silent trim: an entry deleted as "unused" would take
    the printed record's provenance with it, and this identity is the
    one two hardware-certified volumes were recovered from.
    """
    fossil = fossils.FOSSILS["c2-r0700@3392x2368"]
    assert "e029 VERIFIED 465,580 B" in fossil.evidence
    assert "e032 VERIFIED" in fossil.evidence
