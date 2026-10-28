"""Printed-format codings and one tile format: the K constructor.

This is NOT a carry — it is holo2's own, deliberately narrow restatement
of the facts ``holo.format.{registry,descriptor,layout,profiles}`` spread
over four modules and a codec-profile hierarchy.  Every VALUE below is the
v1 value, cross-checked against the real ``FormatSpec`` in
``tests/holo2_oracles/test_oracle_tiles.py``; what is missing is everything the K
tile decode chain never reads (media/margin derivation, codec profiles,
the color alphabet, discovery hypothesis sets).

**TWO IDENTITY NAMESPACES, ONE GRAMMAR, ONE CATALOGUE** (WP-1.2 and
C2, 2026-08-22; FORMAT-SPACE §6/§8, RULINGS B1/B3 as amended by G1):

* ``v1`` (legacy): the frozen printed record.  Geometry is *cells* and
  the row seed is ``holo/v1/<coding_id>/<cells_y>x<cells_x>``.  A v1
  identity is spelled ``L:<coding>@<cells>`` on every holo2 surface and
  exists only as a byte-matched entry of :mod:`holo2.format.fossils` —
  whole identities, never half of one.  Closed: no new v1 identity is
  ever minted.
* ``v2`` (the lattice): identity is coding x TILE matrix, and the
  canonical format id IS the seed payload under ``holo/v2/``.

:func:`coding_for` mints from the GRAMMAR alone.  The three-name alias
table that used to sit beside it (``LEGACY_CODINGS``, WP-1.2's
reshape of the older registry) is DELETED: RULINGS G1 —
"the only real legacy mechanism are the L: lines; we don't need legacy
support beyond what the src/holo legacy table enumerates".  A coding
NAME without its geometry never selected a printed sheet anyway, so a
table of them was a second identity mechanism (L16) that could only
ever build sheets nobody printed.  What the printed record holds is
fourteen whole identities, each with its own frozen bundle;
:mod:`holo2.format.fossils` is that catalogue, and it carries twelve of
the fourteen — only the two cmy8-v0 rows are dropped, by the sunset
ruling (G8).  The module states the reason for each absence.

**IDENTITY CARRIES PITCH, NOT DOTS** (RULINGS G4, C3, 2026-08-22).
``Coding.pitch_in`` is an exact rational of an inch on every row of both
namespaces; ``cell_dots`` and the ``_PITCH_DPI = 600`` that derived it
are gone from this module.  A dot count is grid-relative — it needs an
engine dpi to mean anything — and holo2's receive path never has one:
what it has is a capture's declared dpi, and px/cell is
``pitch_in x dpi_true`` (``registry_rows.native_cell_pitch_px``, exact
Fraction).  Dots survive where a raster is EMITTED (the fixture
renders, with an explicit ``engine_dpi``) and as frozen emission
evidence on a fossil entry, and nowhere else.

**THE PITCH SCOPE IS GONE** (RULINGS H1(a), 2026-08-22 evening: "the
c4 format is just ``1i150-k-r0550@26x18``" — "every registered pitch
class (c1..c4) and every lawful rational builds").  This constructor
carried a ``SCOPE_PITCHES = {1/300, 1/200}`` refusal, DESIGN §7's
c2/c3 clean-break scope restated in inches by C3.  Once C3 made pitch
DATA it defended nothing: a cell size stopped being a receiver concept
the day the 600 left the receive path, px/cell is ``pitch_in x
dpi_true`` at any pitch, and nothing below the survey's candidate set
is c2/c3-specific.  A refusal whose only remaining ground was "holo2
has never read one of those" is guard mass (L17) over measured facts
that do not refuse (P11), so it went, with the off-600 refusal it had
absorbed.  What the K constructor still refuses is the family (below)
and what the ALGEBRA imposes (``lattice.require_constructible``).
A colour identity now BUILDS (RULINGS G2):
``registry_rows.make_format`` mints its row through
``families.colour_codec``, and it is the K TILE CHAIN that refuses it,
fatally, at ``registry_rows.tile_format_for``.  This module stays K:
``Coding`` is the K codec's arithmetic and nothing else.

A fourth refusal this constructor used to carry — a rung whose
mother-code data holo2 does not carry — is GONE (RULINGS G3, "if
src/holo supports the codes, so must src/holo2", 2026-08-22):
``format/ldpc/data/`` now holds all six ``LADDER`` rungs
(r0547/r0550/r0625/r0700/r0775/r0850), copied byte-for-byte from
``src/holo/core/ldpc/data/`` and pinned by
``tests/holo2_oracles/test_oracle_tiles.py::
test_the_ldpc_data_is_byte_identical``. ``LADDER`` was the one mechanism
all along (L16); a second one (``CARRIED_RUNGS``, a subset table this
constructor also policed) is guard mass once every rung it could have
distinguished is actually on the ladder (L17) — deleted along with the
refusal it drove, rather than left to describe a limit that no longer
exists.

Two shape decisions, both forced by the record:

* **Page geometry arrives as ``tiles_yx``, not as media + margin.** The
  hardware-certified rows are not the A4/6 mm rows: e029's and e032's
  ``c2-r0700@3392x2368`` (53x37 tiles) comes from the ``hp-m281-ink``
  4.5 mm probe and is deliberately absent from ``FORMAT_ROWS``, which is
  exactly why a real decode must be told the coding *and* the dimensions
  — as one string since C5 (``--format L:c2-r0700@3392x2368``, RULINGS
  G6), which is the same two facts with no way to disagree about them.
  holo2 therefore takes the grid as data and derives the seed from it —
  which is what v1 does too, one step further down (``seed`` embeds the
  derived cell field, HOLO-DESIGN §4.5), so a wrong-geometry hypothesis
  still descrambles every word to coin flips and refuses at the word
  gate.  Deriving ``cells_yx = 64 * tiles_yx`` is exact: ``derive_field``
  quantises the field to whole tiles before anything else sees it.
* **One coding constant per row, no profile tree.** A K row is
  (pitch, LDPC rung, filler count); its stream algebra
  (``user_bits = k_bits - 32 - n_sites``, one metadata bit, the rest
  symbol) is arithmetic, not a registry.  The color rows are NOT here:
  they need the codec-profile machinery, and they arrive with the color
  leaves (H7).

Codings are append-only and immutable once printed; a filler-density rung
above the 100-site floor would get a NEW coding id, never a new meaning
for an old one.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from . import keystream, metadata, pilots
from .family import Family
from .lattice import (FAMILY_SEED_TEMPLATE, L_PREFIX,
                      METADATA_BITS_PER_TILE, SEED_NAMESPACE, CodingParams,
                      canonical_coding_id, display_coding_id,
                      parse_coding_id, require_constructible)
from .ldpc.construct import LADDER
from .ldpc.tile import CRC_BITS, N_CELLS

# One tile geometry, one counter width: the leaves own the values and this
# module re-exports them, so a fork can only ever be a deliberate edit to
# the leaf (house precedent: ``ldpc/tile.py``'s mother-code assert).
TILE_CELLS = pilots.TILE_CELLS
assert pilots.COUNTER_BITS == metadata.COUNTER_BITS

CODEC_ID_K = "k-v1"
STREAM_MAIN = "main"


@dataclass(frozen=True)
class Coding:
    """One printer-independent K coding (HOLO-DESIGN §3/§8).

    ``fec_profile_id`` is the v1 spelling ``k-<rate>-p<n_sites>-v1``
    (``holo.format.profiles.k_profile``), carried for ``src/holo``
    parity: nothing in holo2 reads it but the oracle, which checks it
    against v1's own profile id.

    WP-1.2 (2026-08-22) added the three identity axes the lattice needs.
    All three DEFAULT to the legacy answer, so every row the legacy
    recipe mints — and therefore every seed, and every ``policy_id``
    that embeds a row id — is byte-identical to what it was (the row
    IDS themselves gained the ``L:`` marker at C2; the seeds did not):

    * ``family`` — the ONE legal dispatch key (FORMAT-SPACE P1).  Always
      ``Family.K`` on a ``Coding``: colour rows do not have one, they
      carry ``families.CodecFacts`` instead, because a colour codec is
      three banks and a dust law rather than one rung.  The field is
      what ``tile_format_for``'s family cross-check compares against the
      row's own declaration, so a hand-built row that lies is caught.
    * ``pitch_in`` — the exact physical pitch in inches, carried by
      EVERY coding in both namespaces (RULINGS G4, 2026-08-22: "we
      wanted to move away from literal 600 dpi hardcoding").  Identity
      carries PITCH, not dots: a dot count is grid-relative, and
      "c2@600" and "c1@300" are the same sheet (FORMAT-SPACE §4).  It
      used to be ``None`` on a v1 row beside a required ``cell_dots``,
      on the reasoning that "a legacy identity never carried a pitch" —
      but a printed sheet has a physical cell whatever string names it,
      and the legacy pitch is FROZEN DATA in the catalogue's bundle
      (``fossils.LegacyCoding.params.pitch``), not a runtime derivation
      from a hard-coded engine grid.  ``cell_dots`` is gone from this
      type with the ``_PITCH_DPI = 600`` that derived it: dots are an
      EMISSION fact (they need an engine dpi to mean anything), and
      nothing on holo2's receive path wants them — px/cell is
      ``pitch_in x dpi_true`` from the capture's own declared dpi
      (``registry_rows.native_cell_pitch_px``).
    * ``namespace`` — ``"v1"`` or ``"v2"``, the one thing ``spec_id``
      and ``seed`` branch on.  ``family_seed`` deliberately does NOT
      branch (P10).

    :func:`coding_for` is the only production construction site, so
    ``__post_init__`` keeps the capacity floor and adds the canonicality
    assert ``src/holo`` lacks: a v2 ``coding_id`` must BE
    ``canonical_coding_id`` of what it spells, or one format would have
    two seeds.
    """

    coding_id: str
    pitch_in: Fraction
    rate_id: str
    n_filler: int = 0
    family: Family = Family.K
    namespace: str = "v1"
    #: The short spelling for people (class names, defaults omitted),
    #: minted beside the canonical id and NEVER stored or seeded
    #: (FORMAT-SPACE §6/§16).  Empty on a v1 row: its id is frozen.
    display_coding_id: str = ""

    def __post_init__(self) -> None:
        if self.tile_user_bits <= METADATA_BITS_PER_TILE:
            raise ValueError(
                f"{self.coding_id}: n_filler={self.n_filler} leaves no "
                "room for metadata and a symbol")
        if not isinstance(self.pitch_in, Fraction) or self.pitch_in <= 0:
            raise ValueError(
                f"{self.coding_id}: a coding carries an exact positive "
                f"rational pitch (inches)")
        if self.namespace == "v2":
            self._validate_v2()
        elif self.namespace != "v1":
            raise ValueError(
                f"unknown identity namespace {self.namespace!r}")

    def _validate_v2(self) -> None:
        canonical = canonical_coding_id(parse_coding_id(self.coding_id))
        if self.coding_id != canonical:
            raise ValueError(
                f"{self.coding_id}: v2 coding ids are stored canonical "
                f"only (this spells {canonical}) — two spellings of one "
                f"format would be two seeds")

    @property
    def n_sites(self) -> int:
        return pilots.N_WORD_SITES + self.n_filler

    @property
    def tile_user_bits(self) -> int:
        """CRC-protected bits per tile: one metadata bit plus the symbol."""
        return LADDER[self.rate_id].k_bits - CRC_BITS - self.n_sites

    @property
    def symbol_bits(self) -> int:
        return self.tile_user_bits - METADATA_BITS_PER_TILE

    @property
    def n_transmitted_slots(self) -> int:
        return N_CELLS - self.n_sites

    @property
    def fec_profile_id(self) -> str:
        return f"k-{self.rate_id}-p{self.n_sites}-v1"

    @property
    def family_seed(self) -> bytes:
        """The frozen site-lattice seed, from ``lattice``'s ONE template.

        Spelled once, like ``SEED_NAMESPACE``: a second f-string of the
        same frozen bytes in a module that already imports the first is
        precisely the fragility this wave came to close (WP-1.2 review,
        2026-08-22).  ``fossils.FAMILY_SEED_P100``/``_P120`` stay a
        separate spelling on purpose — they are goldens, and a golden
        that imports the code under test proves nothing.
        """
        return FAMILY_SEED_TEMPLATE.format(sites=self.n_sites).encode()


def legacy_identity(coding_id: str,
                    cells_yx: tuple[int, int]) -> tuple[str, bytes]:
    """The v1 identity law: how a legacy coding on a cell field is named.

    Returns ``(spec_id, seed)`` where the spec id carries the ``L:``
    prefix every holo2 surface spells a legacy identity with (RULINGS
    G1, 2026-08-22) and the seed is the FROZEN legacy byte string —
    which does NOT move: the printed record is keyed by it, and a
    prefix is a name, not a keystream.

    Spelled ONCE, here, and used by every family: the K tile chain
    below and the colour row builder in ``registry_rows``.  It is the
    RECIPE half of the two-witness discipline; the RECORD half is the
    literal byte strings in :mod:`holo2.format.fossils`, written out
    rather than derived so that the two are genuinely independent
    (WP-1.2 review, 2026-08-22, and RULINGS G1's "LITERAL seed bytes —
    no helper derivation in the module").
    """
    cells_y, cells_x = cells_yx
    return (f"{L_PREFIX}{coding_id}@{cells_y}x{cells_x}",
            f"holo/v1/{coding_id}/{cells_y}x{cells_x}".encode())


def colour_codec_refusal(subject: str, family: Family) -> str:
    """The ONE named fatal message for "holo2 cannot decode this family".

    RULINGS G2 (2026-08-22): holo2 implements the colour FORMATS — every
    lawful cmy7/cmy8 identity names a row, carries its streams, its FEC
    bank ids and its furniture — and fails FATALLY when a colour CODEC
    is asked for.  Two sites raise it (``registry_rows.tile_format_for``,
    the K tile chain's door, and ``_k_coding`` below, which is only
    reachable by an internal routing error), and one message serves
    both: an operator meets the same sentence wherever they arrive, and
    the sentence names the port that will lift the limit rather than the
    line that hit it.
    """
    return (f"{subject}: colour codecs arrive with the colour port; "
            f"holo2 cannot decode {family.value}")


def _k_coding(coding_id: str, params: CodingParams, namespace: str) -> Coding:
    """The K family constructor: one lattice point -> one ``Coding``.

    IT REFUSES NOTHING BUT THE FAMILY NOW.  Two refusals stood here and
    both are gone in one day: a rung whose mother-code data holo2 did
    not carry (RULINGS G3 — the data directory carries every ``LADDER``
    rung), and a pitch outside holo2's decode scope (RULINGS H1(a) —
    below).  Each was a P12-shaped refusal at the right place, and each
    stopped describing anything constructible; a refusal kept past that
    point is guard mass (L17).  What still refuses at a constructor is
    the ALGEBRA the frozen numbers impose
    (``lattice.require_constructible``), which is a different kind of
    statement: it is about sheets that cannot exist, not about sheets
    this tree has not met.

    The pitch one, in full, because it took two steps: C3 folded an
    off-600 refusal ("raster/receive support is pending",
    ``src/holo``'s deviation §15.3-2, carried honestly) into a
    cell-size refusal, and RULINGS H1(a) then deleted the survivor —
    "every registered pitch class (c1..c4) and every lawful rational
    builds".  What the survivor still defended was "holo2 has never
    read one of those", which is not a state: px/cell is ``pitch_in x
    dpi_true`` at any pitch, and the one stage that ever enumerated
    pitches is the blind survey's candidate set
    (``capture.survey.CANDIDATE_PITCHES_IN``) — a hypothesis ladder,
    not a scope.

    The family guard is NOT one of them.  A colour identity has a real
    row (``registry_rows.make_format``, RULINGS G2) and is refused only
    where a K CODEC is actually wanted, so reaching this function with
    one is a routing error inside ``format`` — it raises with the same
    named fatal message ``tile_format_for`` uses, because from the
    caller's side the two are one event: holo2 was asked to decode a
    colour sheet.
    """
    if params.family is not Family.K:
        raise ValueError(colour_codec_refusal(coding_id, params.family))
    rung = params.rungs[0]
    return Coding(
        coding_id=coding_id,
        pitch_in=params.pitch,
        rate_id=rung,
        n_filler=params.sites - pilots.N_WORD_SITES,
        family=params.family,
        namespace=namespace,
        display_coding_id=(display_coding_id(params)
                           if namespace == "v2" else ""),
    )


def _legacy_coding(coding_id: str, params: CodingParams) -> Coding:
    """A frozen catalogue bundle -> its v1-namespace ``Coding``.

    The ONE construction site for a legacy K coding, and deliberately
    private: its only lawful caller is the legacy recipe in
    ``registry_rows``, driven by a bundle that ``fossils`` froze
    (RULINGS G1, 2026-08-22).  It takes params rather than a name
    because there is no table of legacy names any more — the catalogue
    holds whole identities, each carrying the parameters its sheet was
    printed under.
    """
    return _k_coding(coding_id, params, "v1")


@lru_cache(maxsize=None)
def coding_for(coding_id: str) -> Coding:
    """A V2 coding id -> its ``Coding``.  One namespace, one grammar.

    RULINGS G1 (2026-08-22) closed the second door this used to have.
    A legacy coding NAME (``c2-r0700``) is no longer a thing you can
    ask for: legacy identities are the ``L:`` lines and nothing else,
    they are matched byte-exactly against the catalogue as WHOLE
    identities (coding *and* geometry), and they are built by
    ``fossils.resolve_fossil_spec`` from their frozen bundles.  A name
    that is only half an identity cannot select a printed sheet, so it
    is not a route.

    The refusal below therefore has to say where legacy lives, or an
    operator holding the name of a printed sheet is at a dead end.
    """
    try:
        parsed = parse_coding_id(coding_id)
    except ValueError as exc:
        raise ValueError(
            f"unknown coding {coding_id!r}: not a lawful v2 coding id "
            f"({exc}); legacy identities are referenced as "
            f"L:<legacy spec id>, whole and byte-exact") from None
    require_constructible(parsed)
    return _k_coding(canonical_coding_id(parsed), parsed, "v2")


@dataclass(frozen=True)
class TileFormat:
    """coding x tile grid = one printed format, as the tile chain sees it.

    The exact surface ``tiles.py`` reads off v1's ``FormatSpec``, and
    nothing else — the same restriction ``CloseSpec`` applies to the
    close.  Field names and semantics are v1's, so the carried chain runs
    on it unchanged.
    """

    coding: Coding
    tiles_yx: tuple[int, int]
    plane: int = keystream.PLANE_K

    def __post_init__(self) -> None:
        tiles_y, tiles_x = self.tiles_yx
        if tiles_y <= 0 or tiles_x <= 0:
            raise ValueError(f"invalid tiles_yx {self.tiles_yx}")
        if tiles_y * tiles_x > self.max_tiles_addressable:
            raise ValueError(
                f"tiles {self.tiles_yx} exceed the "
                f"{pilots.COUNTER_BITS}-bit counter space on a single page")

    # -- identity ----------------------------------------------------------

    @property
    def cells_yx(self) -> tuple[int, int]:
        return (self.tiles_yx[0] * TILE_CELLS, self.tiles_yx[1] * TILE_CELLS)

    @property
    def spec_id(self) -> str:
        """The canonical row id — TILES under v2, ``L:``+CELLS under v1.

        The two namespaces spell geometry differently on purpose: it is
        the second, independent collision defence beside the ``holo/v1/``
        vs ``holo/v2/`` prefix (FORMAT-SPACE §6).  Under v1 the id also
        carries the ``L:`` marker, so the route is legible wherever the
        string lands — a row id, a persisted ``format_row_id``, a policy
        id, a diag pane (RULINGS G1, 2026-08-22).  The SEED does not
        take the prefix: the printed sheet is keyed by the frozen bytes,
        and a name is not a keystream.
        """
        if self.coding.namespace == "v2":
            tiles_y, tiles_x = self.tiles_yx
            return f"{self.coding.coding_id}@{tiles_y}x{tiles_x}"
        return legacy_identity(self.coding.coding_id, self.cells_yx)[0]

    @property
    def display_id(self) -> str:
        """The short spelling shown to people; never stored, never
        seeded (FORMAT-SPACE §6).  A v1 id is already its own display."""
        short = self.coding.display_coding_id
        if self.coding.namespace != "v2" or not short:
            return self.spec_id
        tiles_y, tiles_x = self.tiles_yx
        return f"{short}@{tiles_y}x{tiles_x}"

    @property
    def seed(self) -> bytes:
        """The AES row seed: under v2 the canonical format id IS the
        payload (FORMAT-SPACE P1); under v1 the frozen legacy string."""
        if self.coding.namespace == "v2":
            return SEED_NAMESPACE + self.spec_id.encode()
        return legacy_identity(self.coding.coding_id, self.cells_yx)[1]

    @property
    def family_seed(self) -> bytes:
        """FROZEN AT v1 IN BOTH NAMESPACES (P10) — see ``Coding``."""
        return self.coding.family_seed

    @property
    def codec_id(self) -> str:
        return CODEC_ID_K

    @property
    def codec_family(self) -> Family:
        """The row's family — the ONE legal dispatch key (FORMAT-SPACE P1).

        WP-1.1 (2026-08-22) landed it as a constant ``Family.K`` because
        no ``Coding`` carried a family yet; WP-1.2 gave ``Coding`` the
        field, so this reads it and ``registry_rows.tile_format_for``'s
        cross-check now compares two independent sources instead of a
        constant against itself.  Still K for every coding holo2 builds
        — the constructor refuses the other two — but the seam is the
        coding's now, which is where the colour port needs it.
        """
        return self.coding.family

    @property
    def stream_ids(self) -> tuple[str, ...]:
        return (STREAM_MAIN,)

    # -- coding pass-throughs (the v1 names the carried chain calls) -------

    @property
    def pitch_in(self) -> Fraction:
        """The printed cell's PHYSICAL pitch, in inches (RULINGS G4).

        Was ``cell_dots``.  The tile chain never wanted dots: what it
        wants is a pixel pitch, and that is this rational times the
        capture's own declared dpi — which is what the receive path now
        asks for (``registry_rows.native_cell_pitch_px``).
        """
        return self.coding.pitch_in

    @property
    def rate_id(self) -> str:
        return self.coding.rate_id

    @property
    def n_filler(self) -> int:
        return self.coding.n_filler

    @property
    def n_sites(self) -> int:
        return self.coding.n_sites

    @property
    def n_transmitted_slots(self) -> int:
        return self.coding.n_transmitted_slots

    @property
    def tile_user_bits(self) -> int:
        return self.coding.tile_user_bits

    @property
    def symbol_bits(self) -> int:
        return self.coding.symbol_bits

    @property
    def fec_profile_id(self) -> str:
        return self.coding.fec_profile_id

    # -- addressing (v1 layout.py, restricted to a known grid) -------------

    @property
    def tiles_per_page(self) -> int:
        return self.tiles_yx[0] * self.tiles_yx[1]

    @property
    def max_tiles_addressable(self) -> int:
        return 1 << pilots.COUNTER_BITS

    @property
    def max_pages(self) -> int:
        return self.max_tiles_addressable // self.tiles_per_page

    def tile_counter(self, page: int, ty: int, tx: int) -> int:
        """Flat counter c = page*tiles_per_page + ty*tiles_x + tx (§4.3)."""
        tiles_y, tiles_x = self.tiles_yx
        if not (0 <= ty < tiles_y and 0 <= tx < tiles_x):
            raise ValueError(f"tile ({ty},{tx}) outside grid {self.tiles_yx}")
        if page < 0:
            raise ValueError(f"negative page {page}")
        counter = page * self.tiles_per_page + ty * tiles_x + tx
        if counter >= self.max_tiles_addressable:
            raise ValueError(
                f"tile counter {counter} exceeds "
                f"{pilots.COUNTER_BITS} bits (F12)")
        return counter

    def tile_address(self, counter: int) -> tuple[int, int, int]:
        """Inverse of :meth:`tile_counter`: counter -> (page, ty, tx)."""
        if not 0 <= counter < self.max_tiles_addressable:
            raise ValueError(
                f"counter {counter} outside "
                f"0..{self.max_tiles_addressable - 1}")
        page, rem = divmod(counter, self.tiles_per_page)
        ty, tx = divmod(rem, self.tiles_yx[1])
        return page, ty, tx


def tile_format(coding_id: str, tiles_yx: tuple[int, int]) -> TileFormat:
    """The tile-chain format for one coding on one declared tile grid.

    V2 IDENTITIES ONLY, through :func:`coding_for` (RULINGS G1,
    2026-08-22).  A legacy coding name refuses here, with the sentence
    that says where legacy lives: the record is keyed by whole ``L:``
    identities, and a v1 row's tile format is rebuilt from its frozen
    catalogue bundle by ``registry_rows._tile_format_of``, which is the
    permanent legacy route.
    """
    return TileFormat(coding_for(coding_id), (int(tiles_yx[0]),
                                              int(tiles_yx[1])))


# ``METADATA_BITS_PER_TILE`` is deliberately absent: it lives in
# ``lattice`` (one home), this module only consumes it, and the package
# surface imports it from there — a re-export would be a second
# publication point for one constant.
# ``SCOPE_PITCHES`` and ``scope_refusal`` stood here until C3b (RULINGS
# H1(a), 2026-08-22): one tuple and one sentence naming the pitches
# holo2 would build a codec for.  Both are DELETED, not widened — the
# set had no member left to exclude that describes an unconstructible
# state.  ``colour_codec_refusal`` stays: ``registry_rows`` imports it
# from here to raise the colour half of F1 at its own door.
# Intra-package, so no package surface or ``test_surfaces`` row is owed
# (B4).
__all__ = [
    "CODEC_ID_K", "Coding", "STREAM_MAIN", "TILE_CELLS",
    "TileFormat", "coding_for", "colour_codec_refusal", "legacy_identity",
    "tile_format",
]
