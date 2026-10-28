"""The v2 identity grammar: parse format ids over the coding lattice.

FORMAT-SPACE §6, carried into holo2 by the catch-up wave's WP-1.2
(2026-08-22, RULINGS B1; the user's ruling that holo2 carries the FULL
grammar — families k/cmy7/cmy8 included — because the colour port needs
to be able to NAME a row before it can decode one, and a value invented
later would be a fork).

  format-id  = coding-id "@" tiles_y "x" tiles_x
  coding-id  = pitch "-" family [ "-" rungs ] "-p" sites "-v" gen

  pitch      = reduced rational "NiD" (n/d inch).  Class names (c1..c4)
               are input/display sugar, never canonical (FORMAT-SPACE §16).
  family     = "k" | "cmy7" | "cmy8"
  rungs      = k: required single rung; cmy8: required, uniform
               shorthand "r0700" or mixed "r0700x0700x0550" (C,M,Y
               order); cmy7: forbidden (baked per generation)
  sites      = always spelled canonically; omitted on input fills frozen
               defaults k -> p100, cmy7/cmy8 -> p120
  gen        = always spelled canonically; omitted on input fills frozen
               default v1

**Identity is a string, and the string is the seed** (FORMAT-SPACE P1).
The canonical string is fully explicit and reads no mutable table.
The short spelling is ``display_id``.  The parser NORMALIZES either
spelling; every serialization point stores canonical form only, so the
seed <-> parameter map stays bijective — if two spellings could both
be stored, one format would have two seeds, two keystreams, and a
printed-format fork.  :class:`ParsedFormat` asserts
that bijectivity as a type invariant (its ``spec_id`` re-derives from
the params it carries), which is the one place holo2 deliberately does
MORE than ``src/holo``: there, canonicality of a v2 seed is call-site
discipline (``lattice.coding_for`` being the sole mint path) and nothing
compares a ``Coding``'s id against ``canonical_coding_id``.

**This module is PURE GRAMMAR and builds no codec.**  That is the seam
RULINGS B1 draws: the string space is total over all three families and
over every lattice point the algebra admits, and *construction* is
per-family, in ``registry_rows.make_format`` — K mints a ``Coding``
through ``format_v1.coding_for``, cmy7/cmy8 mint ``families.CodecFacts``
(C2, RULINGS G2, 2026-08-22).  Keeping the two apart is what let the
colour FORMATS land without touching a character of the naming law, and
it is why this module imports neither ``format_v1`` nor ``keystream``:
it names formats, it does not read sheets.  The one refusal left on the
far side of the seam is F1, at the K TILE CHAIN: holo2 builds a colour
row and dies fatally when a decode asks it for a colour codec.

**The frozen identity MARKERS are declared here, once each**
(``SEED_NAMESPACE`` = ``holo/v2/``, ``L_PREFIX`` = ``L:``,
``FAMILY_SEED_TEMPLATE`` = ``holo/v1/sites/p{sites}``).  The last two
are v1 strings in a module named for the v2 grammar, and that is the
point: this is where a frozen identity string has its ONE home, so that
no two modules can spell one of them differently.  What is deliberately
NOT here is the v1 SEED LAW itself — the record (``fossils``) and the
recipe (``format_v1.legacy_identity``) spell that independently, which
is exactly what makes them two witnesses.

**The seed namespace is declared here, ONCE** (``SEED_NAMESPACE``).
``src/holo`` spells the same eight bytes twice — ``lattice.SEED_NAMESPACE``
and ``descriptor.V2_SEED_NAMESPACE``, in modules that import each other,
with nothing checking agreement; a one-character divergence there would
silently fork every v2 seed while every v1 golden stayed green.
``format_v1.TileFormat.seed`` imports this constant rather than
repeating it — and so does ``format_v1.Coding.family_seed`` with
:data:`FAMILY_SEED_TEMPLATE`, the OTHER frozen seed string, which the
WP-1.2 review caught spelled a second time in that very module.  Both
frozen strings now have exactly one home; the goldens in
:mod:`holo2.format.fossils` are the deliberate second copy, and a
golden that imports its subject proves nothing.

**Legacy (v1) identities never pass through this parser.**  They are
matched byte-exactly in :mod:`holo2.format.fossils` (``L:`` prefix,
FORMAT-SPACE §8): a legacy string re-parsed under new rules could
normalize into a *different* seed, and byte-matching makes that
unrepresentable.  The unknown-family refusal below carries the route
in its own message so an operator who types one is told where it lives.

The refusal catalogue (authored before this code, P6) is the table in
``holo2/tests/format/test_format_lattice.py``'s docstring; the rows
raised here are G1-G14 (grammar) and A1-A7 (the family algebra the
frozen numbers impose).  Every refusal is a builtin ``ValueError`` —
``holo2/tests/test_error_taxonomy.py`` derives the declared exception
set from a package's ``__all__``, so a custom class here would be API
kept alive by its own pin.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

from .close_spec import MAX_TILES
from .family import Family
from .ldpc.construct import LADDER
from .ldpc.tile import CRC_BITS
from .pilots import N_WORD_SITES as WORD_SITES

#: The v2 row-seed namespace, declared once for the whole tree.
SEED_NAMESPACE = b"holo/v2/"

#: The prefix a LEGACY (v1) identity carries on every holo2 surface —
#: ``--format``, a persisted ``format_row_id``, a ``row_id``, a
#: ``CloseSpec.spec_id``, a policy id, diag (RULINGS G1, 2026-08-22:
#: "the only real legacy mechanism are the L: lines").  It lives beside
#: :data:`SEED_NAMESPACE` because the two are the same kind of thing —
#: the frozen markers that say which identity space a string belongs to
#: — and because BOTH witnesses of the legacy catalogue need this one:
#: the record (``fossils``) and the recipe (``format_v1``) must spell
#: the prefix identically or one sheet would have two names.  The SEED
#: law is deliberately NOT here: record and recipe spell that one twice,
#: independently, which is what makes them two witnesses at all.
L_PREFIX = "L:"

#: The frozen family-seed template, shared with v1 ACROSS THE NAMESPACE
#: SPLIT (FORMAT-SPACE §6, the deliberate asymmetry): site placement is a
#: frozen subsystem address like a domain byte, so equal-density sheets
#: share their measured site layout — and the E022/E023 placement lineage
#: — whether they were printed under v1 or v2.  A v2 spec's family seed
#: is still ``holo/v1/sites/pN``; versioning it would be a fork.
FAMILY_SEED_TEMPLATE = "holo/v1/sites/p{sites}"

#: One LDPC user bit per tile per stream, subtracted from the FEC user
#: frame alongside the CRC to leave the fountain symbol.  Frozen
#: substrate (FORMAT-SPACE §2), and therefore identity algebra: it lives
#: HERE, at the bottom of the dependency order, and ``format_v1``
#: imports it rather than declaring a second 1 (the same rule that keeps
#: ``COUNTER_BITS`` to one home).
METADATA_BITS_PER_TILE = 1

#: ``WORD_SITES`` (imported above as ``pilots.N_WORD_SITES``) is the
#: exact-100 word-site floor: p<100 is RESERVED — the e026 subsampling
#: line, FORMAT-SPACE §2 — not merely unimplemented, which is why the
#: refusal below says "reserved" rather than "unsupported".

#: Frozen registered pitch classes: names for exact rationals of an
#: inch.  Append-only; numbers are never reinterpreted (FORMAT-SPACE §4).
#: No grid is privileged — the registry happens to hold 600-grid
#: multiples because those are the measured engines, and a 1200-dpi
#: engine needs no registry change (its 3-dot cell is ``1i400``).
PITCH_CLASSES: Mapping[str, Fraction] = MappingProxyType({
    "c1": Fraction(1, 600),
    "c2": Fraction(1, 300),
    "c3": Fraction(1, 200),
    "c4": Fraction(1, 150),
})
_CLASS_BY_PITCH: Mapping[Fraction, str] = MappingProxyType(
    {pitch: name for name, pitch in PITCH_CLASSES.items()})

_PITCH_CLASS_RE = re.compile(r"^c[0-9]+$")
_PITCH_RATIONAL_RE = re.compile(r"^([0-9]+)i([0-9]+)$")
_RUNGS_TOKEN_RE = re.compile(r"^r[0-9]{4}(?:x[0-9]{4})*$")
_SITES_RE = re.compile(r"^p([0-9]+)$")
_GEN_RE = re.compile(r"^v([0-9]+)$")
_TILES_RE = re.compile(r"^([0-9]+)x([0-9]+)$")

_DEFAULT_SITES: Mapping[Family, int] = MappingProxyType(
    {Family.K: 100, Family.CMY7: 120, Family.CMY8: 120})
_DEFAULT_GEN = 1
_DEFINED_GENS: tuple[int, ...] = (1,)
assert _DEFAULT_GEN in _DEFINED_GENS
_RUNG_ARITY: Mapping[Family, int] = MappingProxyType(
    {Family.K: 1, Family.CMY7: 0, Family.CMY8: 3})


def is_fossil_ref(format_ref: str) -> bool:
    """Is this reference spelled in the LEGACY namespace (``L:``)?"""
    return format_ref.startswith(L_PREFIX)


def strip_fossil_ref(format_ref: str) -> str:
    """The catalogue key an ``L:`` reference names (refuses a bare id)."""
    if not is_fossil_ref(format_ref):
        raise ValueError(
            f"not an L:-prefixed legacy reference: {format_ref!r}")
    return format_ref[len(L_PREFIX):]


def parse_pitch(token: str) -> Fraction:
    """A pitch token -> its exact rational of an inch.

    Exact rationals, never floats and never metric: 1/600 in is
    42333.3... nm, and the only fraction-free representation of this
    lattice is the rational itself (FORMAT-SPACE §4).
    """
    if _PITCH_CLASS_RE.match(token):
        pitch = PITCH_CLASSES.get(token)
        if pitch is None:
            raise ValueError(
                f"unregistered pitch class {token!r}; registered: "
                f"{sorted(PITCH_CLASSES)}")
        return pitch
    rational = _PITCH_RATIONAL_RE.match(token)
    if rational:
        n, d = int(rational.group(1)), int(rational.group(2))
        if n < 1 or d < 1:
            raise ValueError(f"pitch {token!r} must be a positive rational")
        return Fraction(n, d)
    raise ValueError(
        f"pitch token {token!r} is neither a registered class nor NiD")


def canonical_pitch_token(pitch: Fraction) -> str:
    """The CANONICAL token for a pitch: always the reduced rational.

    Never a class name.  A class registry is append-only, so preferring a
    registered name here would let an append re-spell an already-minted
    identity — and the canonical string IS the AES row seed
    (FORMAT-SPACE §16, 2026-08-30).  Class names are display sugar; see
    :func:`display_pitch_token`.
    """
    if pitch <= 0:
        raise ValueError("pitch must be positive")
    return f"{pitch.numerator}i{pitch.denominator}"


def display_pitch_token(pitch: Fraction) -> str:
    """The token a person sees: class name where registered."""
    name = _CLASS_BY_PITCH.get(pitch)
    if name is not None:
        return name
    return canonical_pitch_token(pitch)


def rung_token(rungs: tuple[str, ...]) -> str:
    """The grammar's rung token: contracted when uniform (canonical)."""
    if not rungs:
        raise ValueError("empty rung tuple")
    if len(set(rungs)) == 1:
        return rungs[0]
    return "r" + "x".join(rung.removeprefix("r") for rung in rungs)


@dataclass(frozen=True)
class CodingParams:
    """One point of the coding lattice (identity axes only).

    Deliberately holds no codec, no geometry and no media: these five
    fields are what a coding id spells, and nothing else enters a seed.
    """

    pitch: Fraction
    family: Family
    rungs: tuple[str, ...]
    sites: int
    gen: int

    def __post_init__(self) -> None:
        if self.pitch <= 0:
            raise ValueError("pitch must be positive")
        expected_arity = _RUNG_ARITY[self.family]
        if len(self.rungs) != expected_arity:
            raise ValueError(
                f"{self.family.value}: rung arity must be "
                f"{expected_arity}, got {self.rungs}")


def canonical_coding_id(params: CodingParams) -> str:
    """The EXPLICIT spelling of a lattice point — the seed payload.

    Rational pitch, sites and generation always spelled, uniform triplets
    contracted.  Reads no mutable table, so no registry append or default
    move can re-key a printed sheet (FORMAT-SPACE §6/§16).
    """
    parts = [canonical_pitch_token(params.pitch), params.family.value]
    if params.rungs:
        parts.append(rung_token(params.rungs))
    parts.append(f"p{params.sites}")
    parts.append(f"v{params.gen}")
    return "-".join(parts)


def display_coding_id(params: CodingParams) -> str:
    """The shortest spelling: class names, defaults omitted.  Shown to
    people, accepted as input, never stored and never seeded."""
    parts = [display_pitch_token(params.pitch), params.family.value]
    if params.rungs:
        parts.append(rung_token(params.rungs))
    if params.sites != _DEFAULT_SITES[params.family]:
        parts.append(f"p{params.sites}")
    if params.gen != _DEFAULT_GEN:
        parts.append(f"v{params.gen}")
    return "-".join(parts)


def parse_coding_id(coding_id: str) -> CodingParams:
    """Parse (normalizing) a v2 coding id.  Never accepts legacy ids.

    Token ORDER is normative: a misordered spelling is refused, not
    re-sorted, because normalization must not become a permissive
    re-sorter that admits two spellings of one canonical string.
    """
    tokens = coding_id.split("-")
    if len(tokens) < 2:
        raise ValueError(
            f"coding id {coding_id!r} needs at least pitch and family")
    pitch = parse_pitch(tokens[0])
    try:
        family = Family(tokens[1])
    except ValueError:
        raise ValueError(
            f"coding id {coding_id!r}: unknown family {tokens[1]!r} "
            f"(families: {[f.value for f in Family]}; legacy ids resolve "
            f"through the L: fossil catalogue, not this parser)") from None
    rungs: tuple[str, ...] = ()
    sites = _DEFAULT_SITES[family]
    gen = _DEFAULT_GEN
    rest = tokens[2:]
    idx = 0
    if idx < len(rest) and _RUNGS_TOKEN_RE.match(rest[idx]):
        body = rest[idx][1:]
        rungs = tuple(f"r{part}" for part in body.split("x"))
        if family is Family.CMY8 and len(rungs) == 1:
            rungs = rungs * 3
        idx += 1
    site_token = _SITES_RE.match(rest[idx]) if idx < len(rest) else None
    if site_token is not None:
        sites = int(site_token.group(1))
        idx += 1
    gen_token = _GEN_RE.match(rest[idx]) if idx < len(rest) else None
    if gen_token is not None:
        gen = int(gen_token.group(1))
        idx += 1
    if idx != len(rest):
        raise ValueError(
            f"coding id {coding_id!r}: unrecognized or misordered "
            f"token {rest[idx]!r} (order: rungs, sites, generation)")
    if family in (Family.K, Family.CMY8) and not rungs:
        raise ValueError(
            f"coding id {coding_id!r}: {family.value} requires a rung token")
    if family is Family.CMY7 and rungs:
        raise ValueError(
            f"coding id {coding_id!r}: cmy7 rungs are baked per "
            f"generation — no rung token")
    return CodingParams(pitch=pitch, family=family, rungs=rungs,
                        sites=sites, gen=gen)


def require_constructible(params: CodingParams) -> None:
    """The family algebra the FROZEN numbers impose (A1-A7).

    Separate from :func:`parse_coding_id` because the token grammar and
    the algebra fail for different reasons: ``c2-cmy8-r0700x0700x0550``
    is a well-formed id naming a pool the frozen fountain cannot carry,
    and the message has to say so rather than "bad token".  Refused
    HERE — at the earliest point that knows — rather than deep in
    emission or receive, which is the ruling the ``-x1`` dust bug
    produced (``src/holo/format/families.py:127-134``).
    """
    for rung in params.rungs:
        if rung not in LADDER:
            raise ValueError(
                f"unknown LDPC rung {rung!r}; ladder: {sorted(LADDER)}")
    if params.gen not in _DEFINED_GENS:
        raise ValueError(
            f"{canonical_coding_id(params)}: generation v{params.gen} is "
            f"not defined")
    if params.sites < WORD_SITES:
        raise ValueError(
            f"{params.family.value}: p{params.sites} is below the "
            f"{WORD_SITES}-site word floor (p<100 is reserved, "
            f"FORMAT-SPACE §2)")
    if params.family is Family.CMY7 and params.sites != 120:
        raise ValueError(
            "cmy7 v1 bakes its joint pack7 bank at p120; other site "
            "counts need a new generation (FORMAT-SPACE §5)")
    if params.family is Family.CMY8:
        if params.sites == WORD_SITES:
            # Colour furniture includes dust: the reference field, colour
            # anchoring and the dust value law all assume at least one
            # dust site.  A dust-free colour row would parse as lawful
            # and then die deep in emission/receive.
            raise ValueError(
                "cmy8 needs at least one dust site (p > 100): colour "
                "addressing and calibration consume the dust furniture")
        widths = {LADDER[rung].k_bits for rung in params.rungs}
        if len(widths) != 1:
            raise ValueError(
                f"cmy8 gen-v1 pools one symbol width; rung triplet "
                f"{params.rungs} mixes user widths {sorted(widths)} — a "
                f"width-heterogeneous pool is a future generation "
                f"(FORMAT-SPACE §5)")
    for rung in params.rungs:
        user_bits = LADDER[rung].k_bits - CRC_BITS - params.sites
        if user_bits <= METADATA_BITS_PER_TILE:
            raise ValueError(
                f"{canonical_coding_id(params)}: p{params.sites} leaves "
                f"{user_bits} user bits in the {rung} frame — no room for "
                f"metadata and a symbol")


@dataclass(frozen=True)
class ParsedFormat:
    """One v2 identity, parsed: lattice point x tile matrix, canonical.

    The identity half of a printed format and nothing more — no codec,
    no cell size, no page.  ``spec_id`` IS the seed payload under
    :data:`SEED_NAMESPACE`; ``family_seed`` is the FROZEN v1 template
    (P10), shared with every equal-density sheet ever printed.
    """

    params: CodingParams
    tiles_yx: tuple[int, int]

    def __post_init__(self) -> None:
        tiles_y, tiles_x = self.tiles_yx
        if tiles_y < 1 or tiles_x < 1:
            raise ValueError(
                f"tile matrix {self.tiles_yx} must be at least 1x1")
        if tiles_y * tiles_x > MAX_TILES:
            raise ValueError(
                f"tile matrix {self.tiles_yx} exceeds the counter space "
                f"({MAX_TILES} tiles)")
        require_constructible(self.params)

    @property
    def coding_id(self) -> str:
        return canonical_coding_id(self.params)

    @property
    def spec_id(self) -> str:
        tiles_y, tiles_x = self.tiles_yx
        return f"{self.coding_id}@{tiles_y}x{tiles_x}"

    @property
    def display_id(self) -> str:
        tiles_y, tiles_x = self.tiles_yx
        return f"{display_coding_id(self.params)}@{tiles_y}x{tiles_x}"

    @property
    def seed(self) -> bytes:
        return SEED_NAMESPACE + self.spec_id.encode()

    @property
    def family_seed(self) -> bytes:
        return FAMILY_SEED_TEMPLATE.format(sites=self.params.sites).encode()


def parse_format_id(format_id: str) -> ParsedFormat:
    """Parse (normalizing) a full v2 format id ``coding@TYxTX``.

    Total over the three families: a lawful cmy7/cmy8 id parses here and
    is refused only when somebody asks for a CODEC (``format_v1``).
    """
    if "@" not in format_id:
        raise ValueError(
            f"format id {format_id!r} needs a tile matrix: coding@TYxTX")
    coding_part, _, tiles_part = format_id.rpartition("@")
    tiles = _TILES_RE.match(tiles_part)
    if not tiles:
        raise ValueError(
            f"format id {format_id!r}: tile matrix must be TYxTX")
    params = parse_coding_id(coding_part)
    return ParsedFormat(params, (int(tiles.group(1)), int(tiles.group(2))))


# ``WORD_SITES`` is absent on purpose: it is this module's LOCAL alias
# for ``pilots.N_WORD_SITES`` (kept because the carried refusal messages
# read that way, as ``src/holo``'s do), and every other site in the tree
# spells the pilots name.  Advertising the alias would publish a second
# name for one constant — L16's "one mechanism over parallel paths".
__all__ = [
    "CodingParams", "FAMILY_SEED_TEMPLATE", "L_PREFIX",
    "METADATA_BITS_PER_TILE", "PITCH_CLASSES", "ParsedFormat",
    "SEED_NAMESPACE", "canonical_coding_id", "display_coding_id",
    "is_fossil_ref",
    "canonical_pitch_token", "display_pitch_token",
    "parse_coding_id", "parse_format_id", "parse_pitch",
    "require_constructible", "rung_token", "strip_fossil_ref",
]
