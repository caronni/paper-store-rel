"""The v2 identity grammar and the one coding constructor (WP-1.2).

FORMAT-SPACE §6 carried into holo2 (2026-08-22, RULINGS B1/B3/B5).
Named ``test_format_lattice`` rather than ``test_lattice`` because
``tests/holo/test_lattice.py`` already exists and one shared basename
anywhere under ``testpaths`` aborts the WHOLE repo's collection
(``test_conventions.py::test_test_module_basenames_are_unique``).

THE REFUSAL CATALOGUE — authored before the code it drives (P6: "a
reviewer finding a site missing from this table indicts the table's
generator, not the site").  ``G`` = token grammar, ``A`` = the family
algebra the frozen numbers impose, ``H`` = holo2's own scope, ``F`` =
FATAL (a lawful row holo2 can name and BUILD but never decode), ``R`` =
resolution (exercised in ``test_resolve.py``).  Every row raises a
BUILTIN: ``test_error_taxonomy.py`` derives the declared exception set
from a package's ``__all__``, so a custom class here would be API kept
alive by its own pin.

| id  | condition | raised by | message shape |
|-----|-----------|-----------|---------------|
| G1  | format id has no ``@`` | ``parse_format_id`` | ``format id {id!r} needs a tile matrix: coding@TYxTX`` |
| G2  | tile token not ``TYxTX`` | ``parse_format_id`` | ``format id {id!r}: tile matrix must be TYxTX`` |
| G3  | a tile axis < 1 | ``ParsedFormat`` | ``tile matrix {yx} must be at least 1x1`` |
| G4  | tiles exceed the counter space | ``ParsedFormat`` | ``tile matrix {yx} exceeds the counter space ({MAX_TILES} tiles)`` |
| G5  | fewer than two coding tokens | ``parse_coding_id`` | ``coding id {id!r} needs at least pitch and family`` |
| G6  | unregistered pitch class | ``parse_pitch`` | ``unregistered pitch class {tok!r}; registered: [...]`` |
| G7  | non-positive ``NiD`` rational | ``parse_pitch`` | ``pitch {tok!r} must be a positive rational`` |
| G8  | pitch token neither class nor ``NiD`` | ``parse_pitch`` | ``pitch token {tok!r} is neither a registered class nor NiD`` |
| G9  | unknown family — INCLUDING every legacy id | ``parse_coding_id`` | ``coding id {id!r}: unknown family {tok!r} (families: [...]; legacy ids resolve through the L: fossil catalogue, not this parser)`` |
| G10 | leftover or misordered token | ``parse_coding_id`` | ``coding id {id!r}: unrecognized or misordered token {tok!r} (order: rungs, sites, generation)`` |
| G11 | k or cmy8 without a rung | ``parse_coding_id`` | ``coding id {id!r}: {family} requires a rung token`` |
| G12 | cmy7 WITH a rung | ``parse_coding_id`` | ``coding id {id!r}: cmy7 rungs are baked per generation — no rung token`` |
| G13 | wrong rung arity | ``CodingParams`` | ``{family}: rung arity must be {n}, got {rungs}`` |
| G14 | non-positive pitch (hand-built) | ``CodingParams`` | ``pitch must be positive`` |
| A1  | rung not in ``LADDER`` | ``require_constructible`` | ``unknown LDPC rung {rung!r}; ladder: [...]`` |
| A2  | generation != 1 | ``require_constructible`` | ``{coding_id}: generation v{g} is not defined`` |
| A3  | p < 100 | ``require_constructible`` | ``{family}: p{p} is below the 100-site word floor (p<100 is reserved, FORMAT-SPACE §2)`` |
| A4  | cmy7 at p != 120 | ``require_constructible`` | ``cmy7 v1 bakes its joint pack7 bank at p120; other site counts need a new generation (FORMAT-SPACE §5)`` |
| A5  | cmy8 at p == 100 | ``require_constructible`` | ``cmy8 needs at least one dust site (p > 100): colour addressing and calibration consume the dust furniture`` |
| A6  | cmy8 triplet mixes user widths | ``require_constructible`` | ``cmy8 gen-v1 pools one symbol width; rung triplet {rungs} mixes user widths {widths} — a width-heterogeneous pool is a future generation (FORMAT-SPACE §5)`` |
| A7  | p leaves no room for metadata + symbol | ``require_constructible`` | ``{coding_id}: p{p} leaves {n} user bits in the {rung} frame — no room for metadata and a symbol`` |
| H5  | v2 coding id not in canonical form | ``Coding`` | ``{coding_id}: v2 coding ids are stored canonical only (this spells {canonical}) — two spellings of one format would be two seeds`` |
| H6  | coding id the grammar refuses | ``coding_for`` | ``unknown coding {id!r}: not a lawful v2 coding id ({diagnosis}); legacy identities are referenced as L:<legacy spec id>, whole and byte-exact`` |
| F1  | a lawful, BUILT colour row handed to the K tile chain | ``tile_format_for`` (also ``_k_coding``, unreachable in production) | ``{subject}: colour codecs arrive with the colour port; holo2 cannot decode {family}`` |
| R1  | unresolvable reference | ``resolve_format_ref`` | ``format reference {ref!r} is not a lawful v2 format id ({diagnosis}); legacy identities are referenced as L:<id>, matched byte-exactly: [...]`` |
| R2  | ``L:`` reference naming nothing | ``get_fossil`` (``KeyError``) | ``unknown legacy identity {key!r} (legacy identities match byte-exactly, they are never parsed); closest catalogue entries: [...]`` |
| R3  | ``strip_fossil_ref`` on a bare id | ``strip_fossil_ref`` | ``not an L:-prefixed legacy reference: {ref!r}`` |
| R4  | catalogue and recipe disagree | ``resolve_fossil_spec`` (``AssertionError``) | ``legacy identity {id}: reconstruction forked the frozen identity (...)`` |
| R5  | a BARE legacy spelling | ``resolve_format_ref`` | R1's message, with ``this one is L:{id}`` |

**N1 is the row that is NOT a refusal**: a non-canonical spelling
NORMALIZES.  ``parse_format_id`` returns the canonical identity, and
only canonical strings are ever serialized, so one format has exactly
one seed.  The operator-facing ``format <display> -> state <canonical>``
echo belongs to the ``--format`` CLI (WP-1.4), not to a format leaf,
which prints nothing.

One row deliberately lives at a DIFFERENT site than ``src/holo``'s and
is recorded here so the difference is not mistaken for drift: A7 is
``StreamProfile.__post_init__``'s frame check there and the site
algebra here (both refuse at ``parse_format_id``).

**H3 AND H4 ARE BOTH RETIRED, and no pitch is refused anywhere.**
H3 (RULINGS G4, C3, 2026-08-22) refused a lawful pitch that was not a
whole number of dots on a hard-coded 600-dpi grid — ``src/holo``'s
deviation §15.3-2, which holo2 had copied — and said raster support was
"pending"; C3 folded it into H4, the c2/c3 decode scope restated in
inches.  RULINGS H1(a) (the same day, evening) then deleted H4 itself:
"the c4 format is just ``1i150-k-r0550@26x18``… every registered pitch
class (c1..c4) and every lawful rational builds".  Once pitch was DATA
the survivor defended nothing constructible — px/cell is ``pitch_in x
dpi_true`` at any pitch and nothing below the survey's candidate set is
c2/c3-specific — so it was guard mass (L17) refusing a measured fact
(P11).  ``format_v1.SCOPE_PITCHES``, ``format_v1.scope_refusal``, both
refusal sites and the cross-tree pin ``test_oracle_lattice.
SCOPE_REFUSALS`` went together; the five identities that pin held are
now members of that oracle's ``K_BUILDABLE``/``COLOUR_BUILDABLE``
batteries, compared member by member against ``src/holo``.  Neither row
id is reused.

**H1 is RETIRED** (RULINGS G2, 2026-08-22, "ok for holo2 to implement
the color formats already; it will then fail fatally when trying to
instantiate the color codecs"): it refused a lawful colour identity at
the CONSTRUCTOR, so holo2 could name a colour sheet and not build its
row.  holo2 now builds every lawful colour row — streams, FEC bank ids,
furniture and all — and the refusal moved to the one place that is
really about decoding, as **F1**.  The row id is not reused; a stale
reference to "H1" fails loudly rather than silently meaning F1.

**H2 is RETIRED** (RULINGS G3, 2026-08-22, "if src/holo supports the
codes, so must src/holo2"): it named a lawful rung whose mother-code
data holo2 did not carry.  ``format/ldpc/data/`` now carries all six
``LADDER`` rungs, byte-identical to ``src/holo``'s, so the gap the
refusal described no longer exists; a refusal that defends no
constructible state is guard mass (L17), and it left with
``format_v1.CARRIED_RUNGS``.  The row id is not reused, so a stale
cross-reference to "H2" fails loudly rather than silently meaning
something else.  ``test_every_ladder_rung_loads`` below replaces it:
the fork it prevents is a rung on ``LADDER`` with no data behind it —
the same fork H2 used to catch, from the other direction.
"""
from __future__ import annotations

from fractions import Fraction
from types import MappingProxyType

import pytest

from holo2.format.family import Family
from holo2.format.format_v1 import coding_for
from holo2.format.fossils import FOSSILS, resolve_fossil_spec
from holo2.format.lattice import (PITCH_CLASSES, CodingParams,
                                  canonical_coding_id, parse_coding_id,
                                  display_pitch_token, parse_format_id,
                                  parse_pitch)
from holo2.format import lattice as h2_lattice
from holo2.format.registry_rows import format_row, tile_format_for

# The battery of CANONICAL v2 format ids: each must parse to an identity
# whose spec_id is exactly the input string (the input is already the
# explicit canonical spelling) and whose seed is the v2-namespaced encoding of it.
# All three families, because the grammar is total over the string space
# even where holo2 builds no codec (RULINGS B1).
ROUND_TRIP_IDS = [
    "1i300-k-r0700-p100-v1@53x37",
    "1i200-k-r0550-p100-v1@10x10",
    "1i150-k-r0550-p100-v1@26x18",
    "1i300-cmy8-r0700-p120-v1@53x37",
    "1i300-cmy8-r0550x0550x0547-p120-v1@53x37",
    "1i300-cmy7-p120-v1@52x36",
    "1i300-k-r0550-p300-v1@10x10",
    "1i400-k-r0700-p100-v1@40x28",
]


@pytest.mark.parametrize("format_id", ROUND_TRIP_IDS)
def test_round_trip_battery(format_id: str) -> None:
    """The canonical id IS the seed payload (FORMAT-SPACE P1).

    Prevents the fork where a parse round-trip re-spells an id: the
    seed keys the AES-CTR address keystream, so one changed character
    descrambles every pilot word to coin flips.
    """
    parsed = parse_format_id(format_id)
    assert parsed.spec_id == format_id
    assert parsed.seed == b"holo/v2/" + format_id.encode()


def test_round_trip_battery_facts() -> None:
    """The identity axes a battery id actually carries.

    Prevents the silent-default fork: the round-trip above would still
    pass if a default moved (k -> p120, cmy8 -> p100) as long as the
    canonical spelling moved with it, so the DEFAULTS themselves are
    read out here — they are frozen numbers, and a changed one renames
    every id that elides it.
    """
    parsed = parse_format_id("c2-k-r0700@53x37")
    assert parsed.tiles_yx == (53, 37)
    assert parsed.params.family is Family.K
    assert parsed.params.rungs == ("r0700",)
    assert parsed.params.sites == 100 and parsed.params.gen == 1
    assert parsed.params.pitch == Fraction(1, 300)

    colour = parse_format_id("c2-cmy8-r0700@53x37")
    assert colour.params.family is Family.CMY8
    assert colour.params.rungs == ("r0700", "r0700", "r0700")
    assert colour.params.sites == 120


NORMALIZATION_CASES = [
    ("c2-cmy8-r0700x0700x0700-p120-v1@53x37",
     "1i300-cmy8-r0700-p120-v1@53x37"),
    ("c2-cmy8-r0700@53x37", "1i300-cmy8-r0700-p120-v1@53x37"),
    ("2i600-k-r0700@53x37", "1i300-k-r0700-p100-v1@53x37"),
    ("c2-k-r0700-p100-v1@53x37", "1i300-k-r0700-p100-v1@53x37"),
    ("c2-cmy7-p120-v1@52x36", "1i300-cmy7-p120-v1@52x36"),
]


@pytest.mark.parametrize("spelling,canonical", NORMALIZATION_CASES)
def test_normalization(spelling: str, canonical: str) -> None:
    """N1: non-canonical spellings normalize, they do not refuse.

    Prevents the fork where two spellings of one format both reach a
    serialization point and become two seeds — the reason canonical
    form exists at all.
    """
    parsed = parse_format_id(spelling)
    assert parsed.spec_id == canonical
    assert parsed.seed == parse_format_id(canonical).seed
    assert parsed.seed == b"holo/v2/" + canonical.encode()


def test_a_v2_row_stores_only_the_canonical_spelling() -> None:
    """P9 end to end: a non-canonical id never reaches durable state."""
    row = format_row("c2-k-r0700-p100-v1", (53, 37), 1)
    assert row.coding_id == "1i300-k-r0700-p100-v1"
    assert row.row_id == "1i300-k-r0700-p100-v1@53x37"
    assert row.seed == b"holo/v2/1i300-k-r0700-p100-v1@53x37"


def test_canonical_ids_and_seeds_ignore_the_pitch_class_table(
        monkeypatch: pytest.MonkeyPatch) -> None:
    refs = ROUND_TRIP_IDS + [spelling for spelling, _ in NORMALIZATION_CASES]
    refs = refs + ["1i120-k-r0550@7x7"]
    before = {ref: parse_format_id(ref) for ref in refs}
    monkeypatch.setattr(h2_lattice, "PITCH_CLASSES", MappingProxyType(
        {**dict(PITCH_CLASSES), "c5": Fraction(1, 120)}))
    monkeypatch.setattr(h2_lattice, "_CLASS_BY_PITCH", MappingProxyType(
        {**dict(h2_lattice._CLASS_BY_PITCH), Fraction(1, 120): "c5"}))
    for ref in refs:
        parsed = parse_format_id(ref)
        assert parsed.spec_id == before[ref].spec_id, ref
        assert parsed.seed == before[ref].seed, ref
    assert parse_format_id("1i120-k-r0550@7x7").display_id == \
        "c5-k-r0550@7x7"


def test_a_canonical_id_survives_a_defaults_change(
        monkeypatch: pytest.MonkeyPatch) -> None:
    parsed = parse_format_id("c3-k-r0550@10x10")
    monkeypatch.setattr(h2_lattice, "_DEFAULT_SITES", MappingProxyType(
        {**dict(h2_lattice._DEFAULT_SITES), Family.K: 120}))
    monkeypatch.setattr(h2_lattice, "_DEFAULT_GEN", 2)
    again = parse_format_id(parsed.spec_id)
    assert again.spec_id == parsed.spec_id
    assert again.seed == parsed.seed
    assert again.params.sites == parsed.params.sites


# ------------------------------------------------- the refusal catalogue

GRAMMAR_REFUSALS = [
    ("G1", "c2-k-r0700", "needs a tile matrix"),
    ("G2", "c2-k-r0700@axb", "tile matrix must be TYxTX"),
    ("G3", "c2-k-r0700@0x10", "must be at least 1x1"),
    ("G4", "c2-k-r0700@512x513", "exceeds the counter space"),
    ("G5", "c2@10x10", "needs at least pitch and family"),
    ("G6", "c9-k-r0700@10x10", "unregistered pitch class"),
    ("G7", "0i300-k-r0700@10x10", "must be a positive rational"),
    ("G8", "zz-k-r0700@10x10", "neither a registered class nor NiD"),
    ("G9", "c2-r0700@52x36", "unknown family"),
    ("G10", "c2-k-p100-r0700@10x10", "unrecognized or misordered token"),
    ("G11", "c2-k@10x10", "requires a rung token"),
    ("G12", "c2-cmy7-r0550@52x36", "baked per generation"),
    ("G13", "c2-cmy8-r0550x0550@53x37", "rung arity must be 3"),
    ("A1", "c2-k-r0300@10x10", "unknown LDPC rung"),
    ("A2", "c2-k-r0700-v2@10x10", "generation v2 is not defined"),
    ("A3", "c2-k-r0700-p99@10x10", "below the 100-site word floor"),
    ("A4", "c2-cmy7-p140@52x36", "bakes its joint pack7 bank at p120"),
    ("A5", "c2-cmy8-r0700-p100@53x37", "at least one dust site"),
    ("A6", "c2-cmy8-r0700x0700x0550@53x37", "mixes user widths"),
    ("A7", "c2-k-r0550-p2210@1x1", "no room for metadata and a symbol"),
]


@pytest.mark.parametrize("row,format_id,fragment", GRAMMAR_REFUSALS,
                         ids=[row[0] for row in GRAMMAR_REFUSALS])
def test_grammar_refusal_catalogue(row: str, format_id: str,
                                   fragment: str) -> None:
    """Every G/A row refuses at ``parse_format_id``, by its own message.

    Prevents two forks at once: a malformed id silently becoming a
    LAWFUL neighbouring identity (G3/G10/G13 all sit next to a real
    format), and a refusal losing the diagnosis that tells an operator
    which axis was wrong.
    """
    with pytest.raises(ValueError, match=fragment):
        parse_format_id(format_id)


def test_the_legacy_refusal_names_its_route() -> None:
    """G9 is the row an operator hits by typing a printed sheet's name.

    Prevents the support dead end: ``c2-r0700@3392x2368`` is a REAL
    identity — two verified volumes — that this parser must refuse, so
    the refusal has to point at the catalogue that does hold it.
    """
    with pytest.raises(ValueError) as exc:
        parse_format_id("c2-r0700@3392x2368")
    message = str(exc.value)
    assert "L:" in message and "fossil catalogue" in message


def test_hand_built_params_still_refuse_their_arity_and_pitch() -> None:
    """G13/G14 at the dataclass, not only through the parser.

    Prevents the bypass fork: the colour port constructs ``CodingParams``
    directly, so an arity or pitch invariant that lived only in
    ``parse_coding_id`` would be one a hand-built lattice point could
    walk straight past.
    """
    with pytest.raises(ValueError, match="rung arity must be 1"):
        CodingParams(Fraction(1, 300), Family.K, ("r0550", "r0550"), 100, 1)
    with pytest.raises(ValueError, match="pitch must be positive"):
        CodingParams(Fraction(-1, 300), Family.K, ("r0550",), 100, 1)


#: One id per registered pitch class, plus a lawful rational that is no
#: class at all — the set the retired H4 refused all but two of.
EVERY_PITCH_BUILDS = [
    "c1-k-r0700",
    "c2-k-r0700",
    "c3-k-r0550",
    "c4-k-r0550",
    "1i400-k-r0700",
]


@pytest.mark.parametrize("coding_id", EVERY_PITCH_BUILDS)
def test_every_registered_pitch_class_and_a_lawful_rational_build(
        coding_id: str) -> None:
    """H1(a) executed, from the constructor's side (2026-08-22 evening).

    "Every registered pitch class (c1..c4) and every lawful rational
    builds."  This is the deleted ``HOLO2_SCOPE_REFUSALS`` catalogue
    inverted: three of these five used to raise here, and the fork it
    prevents is the refusal coming back — as a tuple membership test, a
    ``pitch_token`` whitelist, or a raster path that quietly assumes two
    or three dots.  A codec is actually BUILT (not merely parsed),
    because the scope refusal lived inside the constructor and a parse
    would have walked past it.

    The cross-tree half is ``tests/holo2_oracles/test_oracle_lattice.py``,
    where these ids sit in ``K_BUILDABLE`` and every codec fact is
    compared member by member against ``src/holo``'s own answer.
    """
    coding = coding_for(coding_id)
    assert coding.coding_id == canonical_coding_id(
        parse_coding_id(coding_id))
    assert coding.pitch_in == parse_coding_id(coding_id).pitch
    assert coding.namespace == "v2"


def test_a_name_the_grammar_refuses_names_the_legacy_route() -> None:
    """H6, kept out of the table above because it is the one row that
    does NOT parse: ``c2-r0625`` is a coding that never existed.

    Prevents the support dead end: the mint path takes the grammar only
    (RULINGS G1), so an operator holding a legacy-shaped string has to
    be told, in the refusal itself, that legacy identities live behind
    ``L:`` and are whole identities rather than coding names.
    """
    with pytest.raises(ValueError, match="unknown coding") as exc:
        coding_for("c2-r0625")
    assert "unknown family" in str(exc.value)       # the grammar's route
    assert "L:<legacy spec id>" in str(exc.value)   # ...and where legacy is


def test_every_ladder_rung_loads() -> None:
    """G3 rung parity (RULINGS, 2026-08-22): every ``LADDER`` rung has
    frozen mother-code data behind it, and every one of those codes has
    the tile-format block length.

    Replaces H2 (retired): the fork this prevents is the same one H2
    used to catch from the refusal side — a rung on the ladder with no
    data file — now caught from the construction side: a rung that
    parses, is not in ``CARRIED_RUNGS`` (deleted), and silently returns
    a ``Coding`` nobody can actually decode with would be worse than the
    ``FileNotFoundError`` H2 pre-empted.
    """
    from holo2.format.ldpc.construct import LADDER, load_code

    assert sorted(LADDER) == ["r0547", "r0550", "r0625", "r0700", "r0775",
                              "r0850"]
    for rate_id in LADDER:
        code = load_code(rate_id)
        assert code.spec.n_bits == 4096


def test_a_v2_coding_id_must_be_canonical() -> None:
    """H5: the assert ``src/holo`` lacks (its canonicality is call-site
    discipline; ``Coding(coding_id='TOTALLY-BOGUS', namespace='v2')``
    yields ``b'holo/v2/TOTALLY-BOGUS@10x10'`` there).

    Prevents the fork where a hand-built or future v2 coding carries a
    non-canonical id into a seed — one format, two keystreams.
    """
    from holo2.format.format_v1 import Coding

    with pytest.raises(ValueError, match="canonical"):
        Coding(coding_id="c2-k-r0700-p100-v1", rate_id="r0700",
               pitch_in=Fraction(1, 300), namespace="v2")
    with pytest.raises(ValueError, match="unknown identity namespace"):
        Coding(coding_id="c2-r0700", rate_id="r0700",
               pitch_in=Fraction(1, 300), namespace="v3")


# --------------------------------------------------------- the seed laws

def test_pitch_tokens() -> None:
    """The pitch registry is FROZEN: names append, numbers never move."""
    assert parse_pitch("c2") == Fraction(1, 300)
    assert parse_pitch("2i600") == Fraction(1, 300)
    assert display_pitch_token(Fraction(1, 300)) == "c2"
    assert display_pitch_token(Fraction(1, 400)) == "1i400"
    with pytest.raises(ValueError):
        parse_pitch("c7")
    assert dict(PITCH_CLASSES) == {
        "c1": Fraction(1, 600),
        "c2": Fraction(1, 300),
        "c3": Fraction(1, 200),
        "c4": Fraction(1, 150),
    }


def test_family_seed_carries_the_frozen_v1_template() -> None:
    """P10: the family seed does NOT move to v2.

    Site placement is a frozen subsystem address, and sharing it is what
    keeps the E022/E023 placement lineage valid across the namespace
    split.  Versioning it would strand every measured site layout.
    """
    assert parse_format_id("c2-cmy8-r0700@53x37").family_seed == \
        b"holo/v1/sites/p120"
    assert parse_format_id("c2-k-r0550-p300@10x10").family_seed == \
        b"holo/v1/sites/p300"
    assert format_row("c2-k-r0700", (53, 37), 1).seed.startswith(b"holo/v2/")
    assert tile_format_for(format_row("c2-k-r0700", (53, 37), 1)) \
        .family_seed == b"holo/v1/sites/p100"


#: A HAND-WRITTEN sample of v1 seed strings, one per printed K coding —
#: not imported from ``fossils`` and not generated (C4, RULINGS G5,
#: 2026-08-22: it used to be a projection of ``LEGACY_ROW_GOLDENS``,
#: which went with the synthetic legacy rows; the reason it is spelled
#: out is unchanged and is stated in the test below).
LEGACY_SEED_SAMPLE = (
    b"holo/v1/c3-r0550/2240x1536",
    b"holo/v1/c2-r0550/3328x2304",
    b"holo/v1/c2-r0700/3328x2304",
    b"holo/v1/c2-r0700/3392x2368",
)


def test_seed_namespaces_are_disjoint() -> None:
    """v2 seeds and legacy seeds cannot collide, twice over.

    Different prefix AND different geometry units (``/``-joined CELLS vs
    ``@``-joined TILES).  The fork this prevents is the worst one in the
    tree: two different sheets keyed by one AES seed.

    Checked against the hand-written seeds above rather than against
    ``fossils.FOSSILS``, deliberately: this is the GRAMMAR's test, and it
    should not need the catalogue module to state a law about the shape
    of a seed.
    """
    legacy_seeds = set(LEGACY_SEED_SAMPLE)
    for format_id in ROUND_TRIP_IDS:
        seed = parse_format_id(format_id).seed
        assert seed.startswith(b"holo/v2/")
        assert seed not in legacy_seeds
    for seed in legacy_seeds:
        assert seed.startswith(b"holo/v1/")


def test_no_legacy_coding_name_builds_a_v2_coding() -> None:
    """The catalogue's codings and the grammar name disjoint spaces —
    but NOT for the reason the headline suggests.

    ``src/holo``'s resolver docstring argues the namespaces cannot
    shadow each other because a legacy spelling has "no family token".
    That is true of the legacy K ids (``c2-r0700`` dies on "unknown
    family") and FALSE of the legacy COLOUR ids, which do carry one:
    ``c2-cmy7-p120-v0`` tokenizes cleanly as pitch/family/sites/gen and
    reaches the ALGEBRA, where generation v0 is not defined.  So the
    honest statement is the weaker one — no legacy coding name BUILDS —
    and the mechanism that actually holds is precedence (the ``L:``
    marker selects the route before any parsing happens).  Pinned in
    both halves so the difference is never mistaken for drift.
    """
    for fossil in FOSSILS.values():
        with pytest.raises(ValueError):
            coding_for(fossil.coding_id)
    with pytest.raises(ValueError, match="unknown family"):
        parse_coding_id("c2-r0700")               # K: dies in the parser
    assert parse_coding_id("c2-cmy7-p120-v0").gen == 0   # colour: parses
    with pytest.raises(ValueError, match="generation v0 is not defined"):
        coding_for("c2-cmy7-p120-v0")             # ...and dies in the algebra


def test_a_legacy_lattice_point_and_its_v2_twin_are_two_sheets() -> None:
    """The catalogue's frozen params spell the coding they belong to.

    A legacy name is NOT the canonical v2 spelling of its lattice point
    (``c2-r0700`` vs ``c2-k-r0700``) — that is the whole reason the
    catalogue carries params rather than a name — but the params must
    still describe the same CODEC, or the printed sheet and its v2 twin
    would be different codings under one number.  And the two must
    still be different SHEETS, because a namespace is a keystream.
    """
    for fossil in FOSSILS.values():
        params = fossil.coding.params
        if params.family is not Family.K:
            # A colour legacy row has no ``Coding`` at all — that IS the
            # fatal refusal (F1), and its facts are compared against
            # ``src/holo`` in the cross-tree oracle instead.
            continue
        # ON THE FOSSIL'S OWN PRINTED GEOMETRY (C4, RULINGS G5,
        # 2026-08-22).  This used to build the legacy coding at an
        # arbitrary 8x8 grid through the private bridge; there is no
        # such thing as a synthetic legacy row any more, and the
        # catalogued geometry is the better comparison anyway — the two
        # sheets below are then the SAME tile matrix under two
        # namespaces, which is exactly the claim.
        legacy = tile_format_for(resolve_fossil_spec(fossil.spec_id)).coding
        modern = coding_for(canonical_coding_id(params))
        assert legacy.pitch_in == modern.pitch_in
        assert legacy.rate_id == modern.rate_id
        assert legacy.n_sites == modern.n_sites
        assert legacy.family_seed == modern.family_seed
        assert legacy.tile_user_bits == modern.tile_user_bits
        assert legacy.namespace == "v1" and modern.namespace == "v2"
        assert (tile_format_for(resolve_fossil_spec(fossil.spec_id)).seed
                != format_row(canonical_coding_id(params),
                              fossil.tiles_yx).seed)


# --------------------------------------- the legacy rows have not moved
#
# ``LEGACY_ROW_GOLDENS`` and
# ``test_every_legacy_row_is_byte_identical_to_before_the_lattice`` stood
# here until C4 (RULINGS G5, 2026-08-22).  They pinned the spec id and
# row seed each legacy CODING produced at four tile grids — twelve rows,
# of which only four were catalogued identities; the other eight
# (``@64x64``, ``@128x128``, ``@512x512``, ``@768x768``, ``@320x448``)
# were SYNTHETIC legacy rows, a catalogued coding on a grid nobody ever
# printed, reachable only through ``fossils._legacy_row``.  G5 deleted
# that bridge and, with it, the subject: "no synthetic legacy row exists
# any more".
#
# The four that survive are pinned STRICTLY HARDER, and elsewhere:
# ``test_legacy_seeds.py`` carries a deliberate second copy of all TWELVE
# catalogued identities across four kinds of golden (seed bytes, tile
# matrix, pitch, and the frozen codec/bank name strings), builds each one
# through the recipe AND through ``resolve_fossil_spec``, and asserts set
# equality against the catalogue so an entry can neither appear nor
# vanish.  Acceptance bar 1 — not one seed byte of an existing holo2
# decode moved — is therefore intact; what is gone is a table of sheets
# that never existed.  Nothing else changed here.
