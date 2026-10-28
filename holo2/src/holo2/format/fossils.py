"""The legacy (v1-namespace) identity catalogue — frozen AES row seeds.

FORMAT-SPACE §8, carried by WP-1.2 (2026-08-22, RULINGS B2) and
completed by C2 (RULINGS G1/G2/G8, same day).  Every printed or
golden-bearing v1 identity holo2 can name is listed here verbatim: the
exact row-seed byte strings that key the AES-CTR keystream of the
printed record, each with the frozen parameter bundle its sheet was
printed under.

**The catalogue is the whole of the legacy mechanism** (RULINGS G1:
"the only real legacy mechanism are the L: lines; we don't need legacy
support beyond what the src/holo legacy table enumerates").  There is no
legacy coding-NAME table any more: a coding without its geometry never
selected a printed sheet, so a table of half-identities could only ever
build sheets nobody printed.  What the record holds is whole
identities, and they live here.

**Legacy ids never reach the v2 parser.**  They are opaque keys, matched
BYTE-EXACTLY against this table and resolved directly onto their frozen
seeds — no grammar, no normalization.  The ruling's own reason is the
one that matters: *a legacy string re-parsed under new rules could
normalize into a different seed*, and byte-matching makes that
unrepresentable.  Three more reasons ride with it: the ``L:`` prefix
makes the legacy route visible at the call site, the two namespaces then
cannot collide even in principle, and an opaque prefix-marked route is a
clean cut line at the user-declared sunset.  The table MECHANISM
survives that sunset and is reused for convenience aliases; only the
data goes.

**Two witnesses, and the record wins.**  The catalogue is the authority,
the recipe merely rebuilds the object.  The record's side is LITERAL:
every ``spec_id`` and every ``seed`` below is written out, never derived
by a helper in this module (RULINGS G1), so the recipe
(``format_v1.legacy_identity``, one spelling for every family) and the
record are genuinely independent derivations of one byte string.
:func:`resolve_fossil_spec` rebuilds through the ordinary constructor
and then asserts the frozen bytes back; :func:`_self_check` does the
same for every entry at import, so a change to the seed law, to the
64-cell tile, or to a coding's pitch refuses this module rather than
silently forking a printed sheet.  ``holo2/tests/format/
test_legacy_seeds.py`` carries a deliberate SECOND COPY of every byte
string, never regenerated from here.

**Why each entry carries a full bundle.**  A ``-x1`` row's codec and FEC
bank id strings (``cmy8-presence-r0700-p120-x1``) have no v2 spelling —
the mint dropped the ``presence`` token and never had an ``x``
generation — and the ``-p120-v0`` colour banks carry no rung token at
all.  Those strings are hashed into persisted certificate and decoder
identities, so sheet I's 2.85 GB verified state replays bit-identically
only while they are carried as DATA.  Deriving them would be exactly the
fork the ``L:`` ruling exists to prevent.

**Twelve entries: ``src/holo``'s fourteen minus two**, both dropped by
ruling.  The count is pinned by the second copy —
``holo2/tests/format/test_legacy_seeds.py`` asserts SET equality against
its own twelve goldens, so an entry appearing or vanishing here is a
test failure, not a silent drift.  The two absences:

* ``c2-cmy8-p120-v0@3328x2304`` and ``c3-cmy8-p120-v0@2240x1536`` are
  ABSENT by the user's sunset ruling (RULINGS G8, 2026-08-22): cmy8-v0
  — three independent per-stream fountains — "goes away".  holo2
  reaches parity with ``src/holo`` and supersedes it; ``src/holo``
  reads those two sheets until the sunset, and after it they have no
  reader BY DESIGN.  A deliberate archive decision, not an oversight:
  e030's partial (663 certificates, Y empty) and e032's VERIFIED
  718,413 B are both already recovered, and the pooled ``-v1`` twins
  carry the identical tile codec forward.

``c4-r0550@1664x1152`` (e033 sheet A) is the TWELFTH ENTRY, landed by
package C3b (RULINGS H1, 2026-08-22 evening: "the c4 format is just
1i150-k-r0550@26x18, and the actual c4 line for sheet A may or may not
need to go into an L: line").  It does need one.  The printed sheet is
keyed by the v1 seed ``holo/v1/c4-r0550/1664x1152`` while its v2 twin
``c4-k-r0550@26x18`` seeds under ``holo/v2/`` — one physical format,
two keystreams — which is exactly why this catalogue is byte-matched
and never parsed.  It could not land any earlier: until H1(a) deleted
``format_v1.SCOPE_PITCHES`` this module would have listed an identity
the row constructor refused to build.

Deferred imports below are the same trick ``src/holo`` uses: this module
is pure data plus a string law, and the row constructor is needed only
to prove recipe/record agreement.  Importing it at module level would
close the cycle ``registry_rows -> ... -> fossils``.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from types import MappingProxyType
from typing import TYPE_CHECKING

from .family import Family
from .lattice import L_PREFIX, CodingParams, is_fossil_ref, strip_fossil_ref

if TYPE_CHECKING:                       # the deferred import, for types
    from .registry_rows import FormatRowSpec

#: The frozen family-seed strings of the printed record.  Named here
#: because they are goldens of the same kind as the row seeds: the site
#: lattice is a frozen subsystem address, shared across the namespace
#: split (FORMAT-SPACE §6).
FAMILY_SEED_P100 = b"holo/v1/sites/p100"
FAMILY_SEED_P120 = b"holo/v1/sites/p120"

_C2 = Fraction(1, 300)
_C3 = Fraction(1, 200)
_C4 = Fraction(1, 150)


@dataclass(frozen=True)
class LegacyCoding:
    """The frozen parameter bundle one legacy CODING was printed under.

    Everything the recipe needs to rebuild that coding's codec exactly,
    including the frozen derived NAMES: a ``-x1`` row's
    ``cmy8-presence-r0700-p120-x1`` has no v2 spelling (the mint dropped
    the ``presence`` token and never had an ``x`` generation), the
    ``-p120-v0`` colour banks carry no rung token, and those strings are
    hashed into persisted certificate and decoder identities.  Carried as
    DATA for exactly that reason (FORMAT-SPACE §8).

    One object per coding, referenced by every identity printed at it —
    so "one coding, one meaning" is structural here rather than a rule
    the entries have to keep agreeing on.
    """

    coding_id: str
    params: CodingParams         # the lattice point the sheet was printed at
    #: EMISSION EVIDENCE, and the only place ``cell_dots`` survives in
    #: ``holo2/src`` (RULINGS G4, C3, 2026-08-22).  Dots are what the
    #: ENGINE laid down, and they mean nothing without the engine that
    #: laid them: both grids in the printed record are FIXED-600 devices
    #: end to end (HP CLJ Pro M281fdw, Xerox AltaLink C8245 — CLAUDE.md's
    #: channel facts), so ``engine_dpi`` defaults to their 600 while every
    #: entry stays free to say otherwise.  Nothing DERIVES from this pair:
    #: the row's pitch is ``params.pitch``, and ``_self_check`` compares
    #: the two as independent witnesses of one printed cell.
    cell_dots: int
    codec_id: str
    bank_ids: tuple[str, ...]
    engine_dpi: int = 600

    @property
    def emitted_pitch_in(self) -> Fraction:
        """The pitch the frozen emission evidence describes."""
        return Fraction(self.cell_dots, self.engine_dpi)


@dataclass(frozen=True)
class Fossil:
    """One frozen v1 identity: the record, plus the bundle that rebuilds it.

    ``spec_id`` and ``seed`` are the RECORD: literal, written out, never
    computed here.  The rest is the recipe's INPUT, frozen alongside —
    because a recipe fed from the record's own geometry can only ever
    agree with it.  ``tiles_yx`` in particular is stored rather than
    divided out of ``cells_yx``: deriving tiles from cells and comparing
    ``tiles * TILE_CELLS`` back against those cells cancels the constant
    and asserts nothing (measured, WP-1.2 review).  With both frozen, a
    changed ``TILE_CELLS`` moves the rebuilt geometry and not the
    record, and a changed ``params.pitch`` moves the rebuilt row's pitch
    away from the bundle's frozen emission evidence
    (``LegacyCoding.emitted_pitch_in``) and not the record; each refuses
    at import.
    """

    spec_id: str                 # legacy "coding@cells_y x cells_x", LITERAL
    seed: bytes                  # verbatim frozen AES row seed, LITERAL
    coding: LegacyCoding
    cells_yx: tuple[int, int]
    tiles_yx: tuple[int, int]    # the recipe's input, frozen alongside
    evidence: str
    #: The identity as every holo2 surface spells it (RULINGS G1).
    ref: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ref", L_PREFIX + self.spec_id)

    @property
    def coding_id(self) -> str:
        return self.coding.coding_id


# --- K: the derived bank names ARE the v2 ones (same mathematical
# object, same id — FORMAT-SPACE §6), which the recipe asserts.
_C3_R0550 = LegacyCoding(
    coding_id="c3-r0550",
    params=CodingParams(_C3, Family.K, ("r0550",), 100, 1),
    cell_dots=3, codec_id="k-v1", bank_ids=("k-r0550-p100-v1",))
_C2_R0550 = LegacyCoding(
    coding_id="c2-r0550",
    params=CodingParams(_C2, Family.K, ("r0550",), 100, 1),
    cell_dots=2, codec_id="k-v1", bank_ids=("k-r0550-p100-v1",))
_C2_R0700 = LegacyCoding(
    coding_id="c2-r0700",
    params=CodingParams(_C2, Family.K, ("r0700",), 100, 1),
    cell_dots=2, codec_id="k-v1", bank_ids=("k-r0700-p100-v1",))
# Minted on the isolated c4-row branch and frozen by the e033 sheet-A
# print, which is why ``src/holo`` keeps it in ``FOSSIL_CODINGS`` and
# not in its legacy ``CODINGS`` either.  Its FEC bank id is the string
# the v2 grammar derives for ``c4-k-r0550``: the same mathematical
# object at a different pitch, and a pitch is not part of a bank name.
_C4_R0550 = LegacyCoding(
    coding_id="c4-r0550",
    params=CodingParams(_C4, Family.K, ("r0550",), 100, 1),
    cell_dots=4, codec_id="k-v1", bank_ids=("k-r0550-p100-v1",))

# --- CMY7: one joint pack7 bank, baked per generation, so the legacy
# codec id keeps the ``pack7`` token the v2 mint dropped.
_C2_CMY7_P120_V0 = LegacyCoding(
    coding_id="c2-cmy7-p120-v0",
    params=CodingParams(_C2, Family.CMY7, (), 120, 1),
    cell_dots=2, codec_id="cmy7-pack7-p120-v0",
    bank_ids=("cmy7-p120-v0",))
_C3_CMY7_P120_V0 = LegacyCoding(
    coding_id="c3-cmy7-p120-v0",
    params=CodingParams(_C3, Family.CMY7, (), 120, 1),
    cell_dots=3, codec_id="cmy7-pack7-p120-v0",
    bank_ids=("cmy7-p120-v0",))

# --- CMY8 -v1: the POOLED rows.  Their tile codec is the -v0 object
# (same banks, same three streams, same rungs — Y on r0547, which is a
# distinct code at the same k_bits as r0550); what ``-v1`` names is the
# OUTER code, one fountain over esi = counter*3 + stream.  That is P13's
# sharpest exemption made concrete: pooling is not derivable from the
# family in v1, which is why the codec ids of the two generations are
# the same string and their identities are not.
_C2_CMY8_P120_V1 = LegacyCoding(
    coding_id="c2-cmy8-p120-v1",
    params=CodingParams(_C2, Family.CMY8, ("r0550", "r0550", "r0547"),
                        120, 1),
    cell_dots=2, codec_id="cmy8-presence-p120-v0",
    bank_ids=("cmy8-C-p120-v0", "cmy8-M-p120-v0", "cmy8-Y-p120-v0"))
_C3_CMY8_P120_V1 = LegacyCoding(
    coding_id="c3-cmy8-p120-v1",
    params=CodingParams(_C3, Family.CMY8, ("r0550", "r0550", "r0547"),
                        120, 1),
    cell_dots=3, codec_id="cmy8-presence-p120-v0",
    bank_ids=("cmy8-C-p120-v0", "cmy8-M-p120-v0", "cmy8-Y-p120-v0"))

# --- CMY8 -x1: minted on the isolated c4-row branch and frozen by the
# e033 prints.  ``x1`` is a generation token no grammar has, and
# ``presence`` a codec token the mint dropped — carried as data because
# these strings are hashed into persisted certificate and decoder
# identities (sheet I's 2.85 GB VERIFIED state replays through them).
_C2_CMY8_R0700_X1 = LegacyCoding(
    coding_id="c2-cmy8-r0700-p120-x1",
    params=CodingParams(_C2, Family.CMY8, ("r0700", "r0700", "r0700"),
                        120, 1),
    cell_dots=2, codec_id="cmy8-presence-r0700-p120-x1",
    bank_ids=("cmy8-C-r0700-p120-x1", "cmy8-M-r0700-p120-x1",
              "cmy8-Y-r0700-p120-x1"))
_C2_CMY8_R0850_X1 = LegacyCoding(
    coding_id="c2-cmy8-r0850-p120-x1",
    params=CodingParams(_C2, Family.CMY8, ("r0850", "r0850", "r0850"),
                        120, 1),
    cell_dots=2, codec_id="cmy8-presence-r0850-p120-x1",
    bank_ids=("cmy8-C-r0850-p120-x1", "cmy8-M-r0850-p120-x1",
              "cmy8-Y-r0850-p120-x1"))


_FOSSIL_LIST = (
    Fossil(
        spec_id="c3-r0550@2240x1536",
        seed=b"holo/v1/c3-r0550/2240x1536",
        coding=_C3_R0550, cells_yx=(2240, 1536), tiles_yx=(35, 24),
        evidence="catalog; printed e033 A2 (6mm), G (4mm, same cells)"),
    Fossil(
        spec_id="c2-r0550@3328x2304",
        seed=b"holo/v1/c2-r0550/3328x2304",
        coding=_C2_R0550, cells_yx=(3328, 2304), tiles_yx=(52, 36),
        evidence="catalog; goldens, unprinted"),
    Fossil(
        spec_id="c2-r0700@3328x2304",
        seed=b"holo/v1/c2-r0700/3328x2304",
        coding=_C2_R0700, cells_yx=(3328, 2304), tiles_yx=(52, 36),
        evidence="catalog; goldens, unprinted"),
    Fossil(
        spec_id="c2-r0700@3392x2368",
        seed=b"holo/v1/c2-r0700/3392x2368",
        coding=_C2_R0700, cells_yx=(3392, 2368), tiles_yx=(53, 37),
        evidence="e029 VERIFIED 465,580 B (4.5mm, same cells); "
                 "e032 VERIFIED; e033 B, C"),
    Fossil(
        spec_id="c2-cmy7-p120-v0@3328x2304",
        seed=b"holo/v1/c2-cmy7-p120-v0/3328x2304",
        coding=_C2_CMY7_P120_V0, cells_yx=(3328, 2304), tiles_yx=(52, 36),
        evidence="e032 print; failed live, closed 686,859 B by the uplift "
                 "campaign"),
    Fossil(
        spec_id="c3-cmy7-p120-v0@2240x1536",
        seed=b"holo/v1/c3-cmy7-p120-v0/2240x1536",
        coding=_C3_CMY7_P120_V0, cells_yx=(2240, 1536), tiles_yx=(35, 24),
        evidence="e032 VERIFIED 301,600 B"),
    Fossil(
        spec_id="c2-cmy8-p120-v1@3328x2304",
        seed=b"holo/v1/c2-cmy8-p120-v1/3328x2304",
        coding=_C2_CMY8_P120_V1, cells_yx=(3328, 2304), tiles_yx=(52, 36),
        evidence="catalog; sim + emit goldens"),
    Fossil(
        spec_id="c3-cmy8-p120-v1@2240x1536",
        seed=b"holo/v1/c3-cmy8-p120-v1/2240x1536",
        coding=_C3_CMY8_P120_V1, cells_yx=(2240, 1536), tiles_yx=(35, 24),
        evidence="catalog goldens; printed e033 F (4mm, same cells)"),
    Fossil(
        spec_id="c2-cmy8-p120-v1@3392x2368",
        seed=b"holo/v1/c2-cmy8-p120-v1/3392x2368",
        coding=_C2_CMY8_P120_V1, cells_yx=(3392, 2368), tiles_yx=(53, 37),
        evidence="e033 D, E printed"),
    Fossil(
        spec_id="c4-r0550@1664x1152",
        seed=b"holo/v1/c4-r0550/1664x1152",
        coding=_C4_R0550, cells_yx=(1664, 1152), tiles_yx=(26, 18),
        evidence="e033 A printed (c4-row branch coding)"),
    Fossil(
        spec_id="c2-cmy8-r0700-p120-x1@3392x2368",
        seed=b"holo/v1/c2-cmy8-r0700-p120-x1/3392x2368",
        coding=_C2_CMY8_R0700_X1, cells_yx=(3392, 2368), tiles_yx=(53, 37),
        evidence="e033 I VERIFIED 1,798,761 B"),
    Fossil(
        spec_id="c2-cmy8-r0850-p120-x1@3392x2368",
        seed=b"holo/v1/c2-cmy8-r0850-p120-x1/3392x2368",
        coding=_C2_CMY8_R0850_X1, cells_yx=(3392, 2368), tiles_yx=(53, 37),
        evidence="e033 H printed (holo3-max twin)"),
)

FOSSILS: Mapping[str, Fossil] = MappingProxyType(
    {fossil.spec_id: fossil for fossil in _FOSSIL_LIST})

#: Every legacy identity as a holo2 surface spells it, sorted — the
#: listing a refusal shows an operator who typed a bare legacy id.
LEGACY_REFS: tuple[str, ...] = tuple(
    sorted(fossil.ref for fossil in _FOSSIL_LIST))

#: The codings the catalogue holds, DERIVED from the entries rather than
#: listed a second time: an index, not a table of names.  It is what
#: lets a legacy ROW be turned back into a codec — ``registry_rows.
#: tile_format_for`` on a v1 row cannot go through the v2 grammar, and
#: the bundle is where the printed parameters actually live.
_CODING_BUNDLES: Mapping[str, LegacyCoding] = MappingProxyType(
    {fossil.coding.coding_id: fossil.coding for fossil in _FOSSIL_LIST})


def legacy_bundle_for(coding_id: str) -> LegacyCoding:
    """The frozen bundle of a CATALOGUED legacy coding.

    The permanent legacy route: a row already spelled ``L:`` names a
    coding the record holds, and this is where its printed parameters
    are.  A coding the catalogue does not hold is not a legacy coding at
    all — nothing was ever printed at it — so this refuses rather than
    inventing one.
    """
    try:
        return _CODING_BUNDLES[coding_id]
    except KeyError:
        raise KeyError(
            f"no legacy identity uses coding {coding_id!r}; the "
            f"catalogue's codings are {sorted(_CODING_BUNDLES)}") from None


def get_fossil(spec_id: str) -> Fossil:
    """Byte-exact lookup of a catalogue KEY (bare, or behind one ``L:``).

    The convenience of taking either spelling is deliberate and pinned
    (``test_resolve.py``): the catalogue is keyed BARE — that is the
    printed record's own string — while every reference to it carries
    the marker, so both spellings arrive here.  It strips at most one
    prefix, which means ``resolve_format_ref``'s own strip makes the
    ``L:L:`` spelling resolve; that redundancy is inherited verbatim
    from ``src/holo/format/fossils.py`` and kept for cross-tree
    behavioural parity (review note, 2026-08-22).  The ROUTE SELECTOR is
    ``resolve_format_ref``'s prefix test, not this function; what is
    byte-exact is the KEY, which is never parsed, normalized or
    near-matched — only compared.
    """
    key = strip_fossil_ref(spec_id) if is_fossil_ref(spec_id) else spec_id
    try:
        return FOSSILS[key]
    except KeyError:
        near = sorted(s for s in FOSSILS
                      if s.split("@")[0] == key.split("@")[0])
        hint = f"; closest catalogue entries: {near}" if near else ""
        raise KeyError(
            f"unknown legacy identity {key!r} (legacy identities match "
            f"byte-exactly, they are never parsed){hint}") from None


def _row_from_bundle(coding: LegacyCoding, tiles_yx: tuple[int, int],
                     pages: int) -> FormatRowSpec:
    """The recipe: one frozen bundle on one grid -> the row it describes."""
    from .registry_rows import legacy_row
    return legacy_row(
        coding_id=coding.coding_id, params=coding.params, tiles_yx=tiles_yx,
        pages=pages, codec_id=coding.codec_id, bank_ids=coding.bank_ids)


def resolve_fossil_spec(spec_id: str, pages: int = 1) -> FormatRowSpec:
    """A legacy id -> its exact printed row (seed byte-verified).

    Accepts a bare catalogue key or an ``L:`` reference; the row it
    returns spells its identity the ``L:`` way, because that is what
    every holo2 surface stores (RULINGS G1).  The reconstruction must
    reproduce the frozen seed bytes or this refuses — the catalogue is
    the authority, the recipe merely rebuilds the object.
    """
    fossil = get_fossil(spec_id)
    row = _row_from_bundle(fossil.coding, fossil.tiles_yx, pages)
    if row.seed != fossil.seed or row.row_id != fossil.ref:
        raise AssertionError(
            f"legacy identity {fossil.spec_id}: reconstruction forked the "
            f"frozen identity ({row.row_id}, {row.seed!r})")
    return row


# ``_legacy_row(coding_id, tiles_yx, pages)`` and its tile-chain twin
# ``_legacy_tile_format`` stood here from WP-1.2 until C4 (RULINGS G5,
# 2026-08-22).  They built a catalogued legacy CODING at an UNCATALOGUED
# geometry — ``c3-r0550`` on 2x2 tiles — which is a sheet nobody ever
# printed, and they existed for exactly one reason: the synthetic
# fixtures were v1 identities and needed a way to mint small ones.  The
# user's ruling removed the reason ("migrate these to the new syntax and
# regenerate the fixtures"), so the bridge went with its 66 call sites:
# a synthetic page is a v2 identity now, and a printed one is a whole
# ``L:`` line resolved by :func:`resolve_fossil_spec`.
#
# THE ASYMMETRY THAT REMAINS IS DELIBERATE: a legacy identity can still
# only be built from its frozen bundle, and that is what the catalogue
# is.  What is gone is HALF an identity — a coding name plus a grid
# chosen by a caller — which RULINGS G1 had already ruled is not a way
# to name a printed sheet.


def _self_check() -> None:
    """Recipe/record agreement for every entry, at import.

    Four independent comparisons, because the recipe is fed from frozen
    inputs rather than from the record's own geometry: the SEED LAW
    (``row.seed`` against literal bytes), the ``L:`` SPELLING
    (``row.row_id`` against the literal spec id plus the one prefix
    constant), the 64-CELL TILE (``row.cells_yx``, which is ``frozen
    tiles x TILE_CELLS``, against the frozen cells) and the CELL SIZE
    (``row.pitch_in``, which the recipe takes from ``params.pitch``,
    against the bundle's independent EMISSION evidence — the dots the
    engine laid down, over the dpi of the engine that laid them).  The
    frozen codec and FEC bank names
    are checked by the recipe itself for K (they must be the ones the
    coding derives) and carried as data for colour, where the cross-tree
    oracle is what compares them with ``src/holo``.  Each refuses the
    module here rather than decoding a printed sheet to coin flips.
    """
    if len(_FOSSIL_LIST) != len(FOSSILS):
        raise AssertionError("duplicate legacy spec ids")
    for fossil in _FOSSIL_LIST:
        row = _row_from_bundle(fossil.coding, fossil.tiles_yx, 1)
        if row.row_id != fossil.ref or row.seed != fossil.seed:
            raise AssertionError(
                f"legacy identity {fossil.spec_id}: frozen record "
                f"disagrees with the reconstruction recipe "
                f"({row.row_id}, {row.seed!r})")
        if row.cells_yx != fossil.cells_yx:
            raise AssertionError(
                f"legacy identity {fossil.spec_id}: cells {row.cells_yx} "
                f"!= frozen {fossil.cells_yx}")
        if row.pitch_in != fossil.coding.emitted_pitch_in:
            raise AssertionError(
                f"legacy identity {fossil.spec_id}: coding builds pitch "
                f"{row.pitch_in} in != the frozen emission evidence "
                f"c{fossil.coding.cell_dots} at "
                f"{fossil.coding.engine_dpi} dpi "
                f"({fossil.coding.emitted_pitch_in} in)")


_self_check()


__all__ = [
    "FAMILY_SEED_P100", "FAMILY_SEED_P120", "FOSSILS", "Fossil",
    "LEGACY_REFS", "LegacyCoding", "get_fossil", "legacy_bundle_for",
    "resolve_fossil_spec",
]
