"""The H3bis row constructor: one coding + one tile grid = one printed row.

Internal (holo2 only). Equivalence with v1's ``FormatSpec`` is pinned
outside, in ``tests/holo2_oracles/test_oracle_tiles.py``; what is checked
here is that the constructor says what the hardware record says — above
all that ``c2-r0700`` at 53x37 tiles is the e029/e032 geometry
``L:c2-r0700@3392x2368``, which is NOT the A4/6 mm registry row.

C2 (2026-08-22, RULINGS G1): every legacy identity is spelled ``L:``
here, because that is what the row itself now carries.

C4 (2026-08-22, RULINGS G5) deleted ``fossils._legacy_row``, the private
bridge these rows were built through, and with it the whole notion of a
SYNTHETIC legacy row — a catalogued coding on a grid nobody printed.
Each test below therefore says which kind of row it is about: a PRINTED
identity comes from ``fossils.resolve_fossil_spec`` (the hardware
geometry, the A4 row, the printed record's arithmetic), and a test that
only needed *some* row names a v2 one through ``format_row``, which takes
v2 coding ids only.
"""
from __future__ import annotations

from fractions import Fraction

import pytest

from holo2.format.close_spec import CloseStreamProfile
from holo2.format.families import colour_codec
from holo2.format.family import Family
from holo2.format.format_v1 import TileFormat, coding_for, tile_format
from holo2.format.fossils import resolve_fossil_spec
from holo2.format.lattice import canonical_coding_id, parse_coding_id
from holo2.format.registry_rows import (FormatRowSpec, format_row,
                                        native_cell_pitch_px, tile_format_for)

# The three K codings of the printed record, named by a PRINTED IDENTITY
# each (C4, RULINGS G5: a catalogued coding at an uncatalogued geometry
# is not a thing any more), with the numbers the format's own arithmetic
# fixes: user bits = k_bits - 32 (CRC) - 100 (sites); symbol = user - 1
# (metadata).
K_ROWS = (
    # legacy identity, pitch (inches), rate, symbol_bits, fec profile id
    ("c3-r0550@2240x1536", Fraction(1, 200), "r0550", 2107,
     "k-r0550-p100-v1"),
    ("c2-r0550@3328x2304", Fraction(1, 300), "r0550", 2107,
     "k-r0550-p100-v1"),
    ("c2-r0700@3328x2304", Fraction(1, 300), "r0700", 2747,
     "k-r0700-p100-v1"),
)


@pytest.mark.parametrize("spec_id,pitch_in,rate_id,symbol_bits,fec",
                         K_ROWS, ids=[row[0] for row in K_ROWS])
def test_coding_constants(spec_id: str, pitch_in: Fraction, rate_id: str,
                          symbol_bits: int, fec: str) -> None:
    """The printed record's arithmetic, through the legacy recipe.

    Read off the tile-chain view of a real legacy row rather than off a
    coding name: since RULINGS G1 a legacy coding name resolves nowhere
    on its own, and the parameters live in the catalogue's frozen
    bundle, which is the only place a printed sheet's numbers should
    come from.  Since C4 (RULINGS G5) the row is a CATALOGUED one, on
    its own printed geometry, for the same reason: the recipe's input
    is the record's, or the two witnesses are one.
    """
    coding = tile_format_for(resolve_fossil_spec(spec_id)).coding
    assert coding.pitch_in == pitch_in
    assert coding.rate_id == rate_id
    assert coding.n_filler == 0
    assert coding.n_sites == 100                  # the exact-100 word floor
    assert coding.tile_user_bits == symbol_bits + 1
    assert coding.symbol_bits == symbol_bits
    assert coding.n_transmitted_slots == 4096 - 100
    assert coding.fec_profile_id == fec
    assert coding.family_seed == b"holo/v1/sites/p100"
    assert coding.namespace == "v1"


def test_a_legacy_coding_name_is_not_a_v2_coding_id() -> None:
    """The mint path takes the GRAMMAR, and says where legacy lives.

    C2 (RULINGS G1) closed the second door ``coding_for`` used to have.
    The fork this prevents is the quiet one: a legacy name accepted by
    the grammar would have to mean a v2 lattice point, which is a
    different seed and therefore a different sheet from the one whose
    name it is.
    """
    with pytest.raises(ValueError, match="c2-r0700") as exc:
        coding_for("c2-r0700")
    assert "unknown family" in str(exc.value)    # the grammar's route
    assert "L:<legacy spec id>" in str(exc.value)   # ...and where to go


# ------------------------------------------------- the hardware geometry

def test_c2_r0700_at_53x37_is_the_e029_e032_row() -> None:
    """The row two hardware-certified volumes were recovered from.

    e029 (M281, 465,580 B) and e032 (AltaLink, the same 465,580 B) both
    printed ``c2-r0700`` on the ``hp-m281-ink`` 4.5 mm probe geometry:
    53x37 tiles = 3392x2368 cells. The A4/6 mm registry row is 52x36 =
    3328x2304 — a different seed, hence a different scramble, hence not
    the same sheet. This is the whole reason dimensions are arguments.
    """
    row = resolve_fossil_spec("c2-r0700@3392x2368")
    assert row.row_id == "L:c2-r0700@3392x2368"
    assert row.seed == b"holo/v1/c2-r0700/3392x2368"
    assert row.codec_id == "k-v1"
    assert row.pitch_in == Fraction(1, 300)
    assert row.tiles_yx == (53, 37)
    assert row.cells_yx == (3392, 2368)
    assert row.n_pages == 1
    assert row.page_domain == (0,)
    assert row.stream_ids == ("main",)
    assert row.streams[0].symbol_bits == 2747
    assert row.streams[0].fountain_aux is None
    # 1,961 tiles is the e029 count (1,940 of them certified on paper).
    assert row.tiles_yx[0] * row.tiles_yx[1] == 1961


def test_the_a4_row_is_a_different_sheet() -> None:
    """Same coding, registry geometry: a different seed, deliberately."""
    a4 = resolve_fossil_spec("c2-r0700@3328x2304")
    assert a4.row_id == "L:c2-r0700@3328x2304"
    assert a4.seed != resolve_fossil_spec("c2-r0700@3392x2368").seed


def test_close_spec_carries_the_row_identity() -> None:
    row = format_row("c3-k-r0550", (8, 8), 2)
    spec = row.close_spec()
    assert spec.spec_id == row.row_id == "1i200-k-r0550-p100-v1@8x8"
    assert spec.seed == row.seed and spec.tiles_yx == (8, 8)
    assert spec.codec_id == "k-v1"
    assert spec.stream_profiles == row.streams
    assert row.page_domain == (0, 1)


@pytest.mark.parametrize("coding_id",
                         ("c3-k-r0550", "c2-k-r0550", "c2-k-r0700"))
def test_row_and_tile_format_are_one_description(coding_id: str) -> None:
    row = format_row(coding_id, (5, 7), 3)
    fmt = tile_format_for(row)
    assert row.coding_id == canonical_coding_id(parse_coding_id(coding_id))
    assert fmt.spec_id == row.row_id
    assert fmt.seed == row.seed
    assert fmt.pitch_in == row.pitch_in
    assert fmt.stream_ids == row.stream_ids
    assert fmt.symbol_bits == row.streams[0].symbol_bits
    assert fmt.cells_yx == row.cells_yx


def test_tile_format_refuses_a_row_that_disagrees_with_its_coding() -> None:
    """Two descriptions of one sheet must not be allowed to differ."""
    row = format_row("c2-k-r0700", (53, 37), 1)
    doctored = type(row)(**{**row.__dict__, "seed": b"holo/v2/other@1x1"})
    with pytest.raises(ValueError, match="does not describe this sheet"):
        tile_format_for(doctored)
    mismatched = type(row)(**{**row.__dict__, "pitch_in": Fraction(1, 200)})
    with pytest.raises(ValueError, match="declares pitch 1/200 in"):
        tile_format_for(mismatched)


def test_a_row_that_names_no_coding_has_no_tile_view() -> None:
    """A hand-built row (an oracle fixture) names no coding."""
    row = format_row("c2-k-r0550", (2, 2), 1)
    bare = type(row)(**{**row.__dict__, "coding_id": ""})
    with pytest.raises(ValueError, match="names no coding"):
        tile_format_for(bare)


# ------------------------------------------------------------- addressing

def test_tile_counter_is_the_flat_raster_counter() -> None:
    fmt = tile_format_for(resolve_fossil_spec("c2-r0700@3392x2368"))
    assert fmt.tiles_per_page == 1961
    assert fmt.tile_counter(0, 0, 0) == 0
    assert fmt.tile_counter(0, 1, 0) == 37
    assert fmt.tile_counter(0, 52, 36) == 1960
    assert fmt.tile_counter(1, 0, 0) == 1961
    for page in (0, 1, 7):
        for ty, tx in ((0, 0), (1, 5), (52, 36)):
            counter = fmt.tile_counter(page, ty, tx)
            assert fmt.tile_address(counter) == (page, ty, tx)


def test_addressing_refusals() -> None:
    fmt = tile_format("c3-k-r0550", (8, 8))
    assert fmt.max_pages == (1 << 18) // 64
    with pytest.raises(ValueError, match="outside grid"):
        fmt.tile_counter(0, 8, 0)
    with pytest.raises(ValueError, match="negative page"):
        fmt.tile_counter(-1, 0, 0)
    with pytest.raises(ValueError, match="exceeds 18 bits"):
        fmt.tile_counter(fmt.max_pages, 0, 0)
    with pytest.raises(ValueError, match="outside 0.."):
        fmt.tile_address(1 << 18)


def test_a_grid_larger_than_the_counter_space_is_refused() -> None:
    with pytest.raises(ValueError, match="counter space"):
        TileFormat(coding_for("c2-k-r0550"), (600, 600))


# ------------------------------------------------------- the row itself
# R2 moved FormatRowSpec here from engine/runtime.py; these two came with
# it. The row is printed-format truth, so its refusals are format's.

def test_format_row_is_the_minimum_holo2_needs() -> None:
    row = FormatRowSpec(
        row_id="c3-test@128x128", codec_id="k-v1",
        seed=b"holo/v1/test/128x128", tiles_yx=(2, 2),
        pitch_in=Fraction(1, 200),
        streams=(CloseStreamProfile("main", 32),), n_pages=1)
    assert row.page_domain == (0,)
    assert row.cells_yx == (128, 128)
    assert row.stream_ids == ("main",)
    assert row.close_spec().tile_counter(0, 1, 1) == 3
    assert row.coding_id == ""              # hand-built: no v1 coding


def test_the_cell_pitch_is_capture_arithmetic_not_row_state() -> None:
    """The caller supplies the SURVEYED pitch — a module function,
    deliberately not a row method (the bridge died with its last caller).

    The second half is C3's arithmetic pin (RULINGS G4, 2026-08-22):
    ``pitch_in x dpi_true`` is the SAME NUMBER the old
    ``c_dots * dpi / 600`` produced at every 600-grid pitch, exactly,
    in Fractions.  The fork it prevents is a silent renumbering of every
    footing id and every window lattice on the day the 600 left — a
    change no golden seed would have caught, because a footing is not
    part of an identity.

    The third half is the UNIT's guard (review fix, C3, 2026-08-22): the
    fork it prevents is a caller left on the OLD unit — passing the dot
    count this argument used to be — getting a pixel pitch 600x too large
    in silence.  The old signature refused a pitch loudly; without this
    the safety is one-way.
    """
    assert not hasattr(FormatRowSpec, "native_cell_pitch_px")
    assert native_cell_pitch_px(600.0, Fraction(1, 200)) == Fraction(3)
    assert native_cell_pitch_px(1200.0, Fraction(1, 300)) == Fraction(4)
    for dots in (1, 2, 3, 4, 8):
        for dpi in (600.0, 1200.0, 1197.6, 2400.0, 4800.0):
            assert (native_cell_pitch_px(dpi, Fraction(dots, 600))
                    == Fraction(dots) * Fraction(str(dpi)) / 600)
    for dots in (1, 2, 3):
        with pytest.raises(ValueError, match="not a printed cell"):
            native_cell_pitch_px(600.0, Fraction(dots))


def test_a_row_at_an_unregistered_pitch_is_a_row(  # H1(a), 2026-08-22
        ) -> None:
    """The colour half of the deleted scope refusal, inverted.

    ``FormatRowSpec.__post_init__`` raised H4 here — the K
    constructor's sentence with the row id as its subject — for any
    pitch but c2 and c3.  RULINGS H1(a) deleted the set, so a row at a
    lawful rational is simply a row.  The fork this prevents is the
    refusal returning on the row while the constructor stays open,
    which would make a c4 or ``1i400`` identity buildable as a CODING
    and unbuildable as a ROW — half-executed, and visible only to
    whichever caller happened to want the row.

    The declared-domain refusals that share this constructor are
    unaffected and still pinned (next test); ``n_pages=0`` is checked
    here because it is the one that used to sit beside the pitch.

    So is the pitch's own FLOOR (review fix, C3b-c4, 2026-08-22).  A
    second fork this test now prevents is the deletion taking the floor
    with it: a row at pitch 0 laying a zero-step cell lattice, which
    ``native_cell_pitch_px`` turned into ``0`` px/cell in silence (and
    ``-1/300`` into ``-4``).  A non-positive pitch is a sheet that
    CANNOT EXIST; the deleted set refused sheets holo2 had merely not
    MET.  The two now live one line apart in ``__post_init__`` and must
    not be mistaken for each other.
    """
    row = FormatRowSpec("x", "k-v1", b"s", (1, 1), Fraction(1, 400),
                        (CloseStreamProfile("main", 8),))
    assert row.pitch_in == Fraction(1, 400)
    with pytest.raises(ValueError, match="at least one page"):
        FormatRowSpec("x", "k-v1", b"s", (1, 1), Fraction(1, 200),
                      (CloseStreamProfile("main", 8),), n_pages=0)
    for unprintable in (Fraction(0), Fraction(-1, 300)):
        with pytest.raises(ValueError, match="is not a printed cell"):
            FormatRowSpec("x", "k-v1", b"s", (1, 1), unprintable,
                          (CloseStreamProfile("main", 8),))
        with pytest.raises(ValueError, match="is not a printed cell"):
            native_cell_pitch_px(1200.0, unprintable)


def test_the_whole_declared_domain_is_validated_at_the_row() -> None:
    """F-15: 200 pages of the e029 grid is not a sheet, and says so here.

    The old failure was late and unhelpful — the row was accepted and the
    counter blew up on whichever tile first crossed 2^18.
    """
    with pytest.raises(ValueError, match="18-bit tile counter"):
        FormatRowSpec("x", "k-v1", b"s", (53, 37), Fraction(1, 300),
                      (CloseStreamProfile("main", 8),), n_pages=200)
    with pytest.raises(ValueError, match="invalid tiles_yx"):
        FormatRowSpec("x", "k-v1", b"s", (0, 37), Fraction(1, 300),
                      (CloseStreamProfile("main", 8),))


# ------------------------------- the two constructor cross-checks that
# only a HAND-BUILT input can reach (review fix, 2026-08-22)
#
# Both guards below are structurally unreachable from the production
# path: ``_colour_row`` fills the row's family, codec id, streams and
# pooled flag FROM the same ``CodecFacts`` it then stores, and
# ``colour_codec``'s bank-id override is passed only by ``fossils``,
# from bundles the import-time self-check already proved. That is
# exactly why they need a pin rather than a deletion — the customer of
# each is an input written BY HAND: the oracle/fixture shape here, and
# the next frozen bundle a colour fossil arrives with. Without a pin,
# L17 would be right that they defend no constructible state.

def test_a_row_that_lies_about_its_family_is_refused() -> None:
    """The fork: a row whose ``codec_family`` contradicts its codec.

    ``codec_family`` is the ONE legal dispatch key (FORMAT-SPACE P1) and
    the codec is what actually describes the sheet. A row carrying K
    over a cmy8 codec would send a colour sheet down the K tile chain
    with the fatal refusal (F1) bypassed — the one way a colour page
    could reach a decode instead of dying at the door.
    """
    codec = colour_codec(parse_coding_id("c2-cmy8-r0700"))
    with pytest.raises(ValueError, match="row declares family 'k'"):
        FormatRowSpec(
            row_id="L:lying@1x1", codec_id=codec.codec_id, seed=b"s",
            tiles_yx=(1, 1), pitch_in=Fraction(1, 300),
            streams=codec.close_profiles,
            pooled_fountain=codec.pooled_fountain, codec=codec)


def test_a_bank_id_override_that_names_one_bank_three_times_is_refused(
        ) -> None:
    """The fork: a colour fossil bundle whose frozen bank ids collapsed.

    The override exists only so a legacy row can carry bank id STRINGS
    the v2 grammar cannot spell, and those strings are hashed into
    persisted certificate and decoder identities. Three planes sharing
    one bank id would give C, M and Y one FEC identity — a silent
    identity merge, not a decode failure.
    """
    params = parse_coding_id("c2-cmy8-r0700-p120")
    with pytest.raises(ValueError, match="must name 3 distinct bank"):
        colour_codec(params, _bank_ids=("a", "a", "a"))
    assert colour_codec(params).family is Family.CMY8   # the control
