"""The colour family constructors: what a cmy7/cmy8 row is made of.

FORMAT-SPACE §5, carried into holo2 by the catch-up wave's C2
(2026-08-22, RULINGS G2: "ok for holo2 to implement the color formats
already; it will then fail fatally when trying to instantiate the color
codecs").  The origin is ``src/holo/format/families.py`` plus the frozen
numbers its profiles read out of ``src/holo/format/profiles.py``; this
is holo2's narrow restatement of the same arithmetic, in holo2's shape.

**A family is a FUNCTION from parameters to immutable facts**, never a
singleton to compare against.  The origin measured the cost of the
alternative: an identity compare (``codec in (CMY7_P120_V0,
CMY8_P120_V0)``) handed a freshly built ``-x1`` colour row the K
reference field — no dust — silently, and the dispatch table annotates
that site "the c4-row branch bug site, now unrepresentable".  Dispatch
here is on :class:`~holo2.format.family.Family` and nothing else
(FORMAT-SPACE P1).

Numerical law shared by K and CMY8 (all LDPC mothers are n=4096):
shortening equals the site count p, so transmitted bits = 4096 - p =
payload cells per stream, and user bits = k_bits(rung) - p - CRC32.
CMY7 is the exception the pack7 mapper forces: its joint bank is baked
(three children, two of them shortened to fit), and its payload cells
carry 11 bits per 4 cells rather than one bit each.

**What is here and what is not.**  Here: the stream layout (ids, FEC
banks, fountain auxiliaries, symbol widths), the derived codec/bank id
grammar, and the furniture facts a colour sheet's addressing depends on
(site count, dust count, dust base cycle, per-plane rungs).  Not here:
the physical alphabet, the evidence width, the mappers, the dust VALUE
law — every one of those is read by a colour RECEIVER, and holo2 has
none.  They arrive with the colour port, which also brings
``pilots``'s six uncarried colour functions.  Carrying them now would
be a codec nobody can call sitting in a package that refuses to call it.

**Why the row exists at all, if nothing decodes it.**  Because an
identity that cannot be NAMED cannot be planned, capacity-checked,
persisted or resumed, and the e033 §033.5 incident is what that costs:
an off-catalog colour resume died at "stream 'M' is not declared"
because a row id only meant something if a table in that build still
held the row.  holo2 names every lawful colour format, builds its row,
and refuses exactly one thing — a colour CODEC — by name, at
``registry_rows.tile_format_for``.

Every refusal here is a builtin ``ValueError``: the family algebra's own
rows (A1-A7) are ``lattice.require_constructible``'s, checked once at
the door below, and the rest are frozen-arithmetic asserts that fire
only if a carried number moved.
"""
from __future__ import annotations

from dataclasses import dataclass

from .close_spec import CloseStreamProfile
from .family import Family
from .keystream import (COLOR_STREAM_C, COLOR_STREAM_M, COLOR_STREAM_MAIN,
                        COLOR_STREAM_Y)
from .lattice import (METADATA_BITS_PER_TILE, CodingParams,
                      require_constructible, rung_token)
from .ldpc.construct import LADDER
from .ldpc.tile import CRC_BITS, N_CELLS
from .pilots import N_WORD_SITES

#: The canonical plane order of the printed record: a CMY8 row's three
#: streams ARE the planes, in this order, and their fountain auxiliaries
#: are the frozen domains 1/2/3.  Frozen alongside the alphabet it
#: indexes (``src/holo/core/channel.py:46``); holo2 has no channel module
#: because it decodes K, so the order is carried here as the one datum
#: the colour FORMAT needs from it.
CMY_PLANE_ORDER: tuple[str, ...] = ("C", "M", "Y")

#: Dust base CYCLES, as physical state ids of the frozen presence
#: alphabet (W=0, C=1, M=2, CM=3, Y=4, CY=5, MY=6, CMY=7).  The v1 dust
#: law tiles a cycle across the dust sites before the domain-9
#: permutation; the cycle is a CODEC FACT consumed by the colour
#: pilots, not a dispatch branch (FORMAT-SPACE §5, and the origin's own
#: "the dust law: a dispatch turned into a fact").  CMY7 has no CMY
#: state — that is what makes it seven — so its cycle is one shorter.
CMY7_DUST_CYCLE: tuple[int, ...] = (1, 2, 4, 5, 6)          # C M Y CY MY
CMY8_DUST_CYCLE: tuple[int, ...] = (1, 2, 4, 5, 6, 7)       # ... + CMY

#: The pack7 mapper's frozen dimensions: 11 bits per 4 payload cells
#: (7**4 = 2401 tuples > 2**11 = 2048 words).
CMY7_BITS_PER_MAPPER_UNIT = 11
CMY7_CELLS_PER_MAPPER_UNIT = 4

#: CMY8's: 3 bits per cell — one presence bit per plane, which is the
#: same three bits its three STREAMS carry a cell's worth of each.  (K's
#: is 1/1; a K row has no ``CodecFacts``, so it is not spelled here.)
CMY8_BITS_PER_MAPPER_UNIT = 3
CMY8_CELLS_PER_MAPPER_UNIT = 1

#: The frozen pack7 FEC bank: one r0550 child plus two r0625 children
#: shortened to 1883 active information bits each, so the bank's
#: transmitted bits (10,934) exactly fill 994 four-cell packs at 11
#: bits.  Baked per generation, hence carried as data.
CMY7_BANK_CHILDREN: tuple[tuple[str, int], ...] = (
    ("r0550", 0), ("r0625", 677), ("r0625", 677))


@dataclass(frozen=True)
class FecBankFacts:
    """An ordered set of mother-code children sharing one outer CRC frame.

    The origin's ``FecBankProfile``, restated as the arithmetic holo2
    needs: a bank id and the ordered (rung, shortened information tail)
    pairs.  Every derived width is COMPUTED from ``LADDER`` rather than
    typed, so a moved mother code shows up as a disagreement with
    ``src/holo`` in the cross-tree oracle instead of as two frozen
    numbers that quietly stopped describing the same code.
    """

    profile_id: str
    children: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("an FEC bank needs a profile id")
        if not self.children:
            raise ValueError(f"{self.profile_id}: an FEC bank needs a child")
        for rung, shortened in self.children:
            if rung not in LADDER:
                raise ValueError(
                    f"unknown LDPC rung {rung!r}; ladder: {sorted(LADDER)}")
            if not 0 <= shortened < LADDER[rung].k_bits:
                raise ValueError(
                    f"{self.profile_id}: {rung} shortened_info_tail="
                    f"{shortened} must be in [0, {LADDER[rung].k_bits})")
        if self.active_information_bits <= CRC_BITS:
            raise ValueError(
                f"{self.profile_id}: active information cannot hold a CRC")

    @property
    def active_information_bits(self) -> int:
        return sum(LADDER[rung].k_bits - shortened
                   for rung, shortened in self.children)

    @property
    def transmitted_bits(self) -> int:
        return sum(LADDER[rung].n_bits - shortened
                   for rung, shortened in self.children)

    @property
    def user_bits(self) -> int:
        """Bits protected by the bank CRC: metadata and symbol together."""
        return self.active_information_bits - CRC_BITS


@dataclass(frozen=True)
class StreamFacts:
    """One logical fountain/certificate stream of a physical tile.

    The origin's ``StreamProfile``, member for member: the stream id, its
    FEC bank, and its fountain auxiliary (the keystream domain that
    separates one plane's symbol draws from another's).  ``None`` means
    the established K domains 7/8.
    """

    stream_id: str
    fec: FecBankFacts
    fountain_aux: int | None

    @property
    def user_bits(self) -> int:
        return self.fec.user_bits

    @property
    def symbol_bits(self) -> int:
        return self.user_bits - METADATA_BITS_PER_TILE

    @property
    def close_profile(self) -> CloseStreamProfile:
        """The narrow view a volume close reads (``close_spec``).

        The close sees a stream id, a symbol width and a domain — never
        a FEC bank, because assembling symbols is not decoding tiles.
        ``CloseStreamProfile`` re-checks the auxiliary against the frozen
        ``COLOR_STREAM_AUX`` table, so a mistyped domain here cannot
        reach a fountain.
        """
        return CloseStreamProfile(self.stream_id, self.symbol_bits,
                                  self.fountain_aux)


@dataclass(frozen=True)
class CodecFacts:
    """The immutable tile-codec facts one colour coding selects.

    The origin's ``CodecProfile``, restricted to what holo2 has a use
    for: identity (``codec_id``, ``family``), the stream layout, the
    outer-code axis, and the furniture a colour sheet's addressing
    stands on.  The alphabet, evidence width and dust VALUE law are the
    colour port's — see the module docstring.

    ``pooled_fountain`` is a SEPARATE field and not derived from the
    family (P13, the sharpest of the origin's four "do not convert this
    to dispatch" exemptions): pooling is a family fact in the v2 space
    (every v2 cmy8 row is pooled) and is NOT one in v1, where the
    printed ``-v0`` sheets are unpooled CMY8 and their ``-v1`` twins are
    pooled with the identical tile codec.  A receiver that derived one
    from the other would read e030/e032's sheets with the wrong outer
    code.
    """

    codec_id: str
    family: Family
    n_sites: int
    n_dust: int
    dust_base_cycle: tuple[int, ...]
    rungs: tuple[str, ...]
    bits_per_mapper_unit: int
    cells_per_mapper_unit: int
    streams: tuple[StreamFacts, ...]
    pooled_fountain: bool

    def __post_init__(self) -> None:
        if not self.streams:
            raise ValueError(f"{self.codec_id}: at least one stream required")
        if len({stream.stream_id for stream in self.streams}) \
                != len(self.streams):
            raise ValueError(f"{self.codec_id}: duplicate stream ids")
        if not N_WORD_SITES <= self.n_sites < N_CELLS:
            raise ValueError(f"{self.codec_id}: invalid furniture count")
        if not 0 <= self.n_dust <= self.n_sites - N_WORD_SITES:
            raise ValueError(f"{self.codec_id}: invalid dust count")
        if self.n_dust and not self.dust_base_cycle:
            raise ValueError(
                f"{self.codec_id}: dust sites need a dust base cycle")
        if self.payload_cells % self.cells_per_mapper_unit:
            raise ValueError(
                f"{self.codec_id}: {self.payload_cells} payload cells do "
                f"not fill whole {self.cells_per_mapper_unit}-cell packs")
        # The frozen arithmetic, asserted rather than trusted: what the
        # banks transmit across ALL streams must be exactly what the
        # payload cells carry.  It is the one check that ties the FEC
        # ladder, the site count and the mapper together — and it is why
        # the widths are computed from LADDER instead of typed.  Stated
        # over the SUM because that is the form both families satisfy:
        # cmy7 puts 11 bits on every 4 cells through one joint bank,
        # cmy8 puts one presence bit per plane on every cell through
        # three independent ones.
        carried = (self.payload_cells // self.cells_per_mapper_unit
                   * self.bits_per_mapper_unit)
        transmitted = sum(stream.fec.transmitted_bits
                          for stream in self.streams)
        if transmitted != carried:
            raise ValueError(
                f"{self.codec_id}: the streams transmit {transmitted} bits, "
                f"the tile's payload cells carry {carried}")
        for stream in self.streams:
            if stream.symbol_bits < 1:
                raise ValueError(
                    f"{self.codec_id}: stream {stream.stream_id} has no "
                    f"room for metadata and a symbol")
        if self.pooled_fountain and len(self.streams) < 2:
            raise ValueError(
                f"{self.codec_id}: a pooled fountain needs >= 2 streams")

    @property
    def payload_cells(self) -> int:
        return N_CELLS - self.n_sites

    @property
    def stream_ids(self) -> tuple[str, ...]:
        return tuple(stream.stream_id for stream in self.streams)

    @property
    def fec_profile_ids(self) -> tuple[str, ...]:
        return tuple(stream.fec.profile_id for stream in self.streams)

    @property
    def close_profiles(self) -> tuple[CloseStreamProfile, ...]:
        return tuple(stream.close_profile for stream in self.streams)


def _cmy7_facts(params: CodingParams, codec_id: str | None,
                bank_ids: tuple[str, ...] | None) -> CodecFacts:
    """CMY7: ONE stream over a joint base-7 pack, no per-plane fallback.

    The rung axis is coarser by nature — pack7's FEC is a joint 3-child
    bank whose shortening is baked to the payload cell count — so rung
    and site variation mean a new baked bank, which is a new GENERATION
    and not a new lattice point.  That is why the grammar refuses a
    cmy7 rung token outright, and why ``p`` is pinned at 120 here.
    """
    bank = FecBankFacts(
        profile_id=(bank_ids or (f"cmy7-p{params.sites}-v{params.gen}",))[0],
        children=CMY7_BANK_CHILDREN)
    return CodecFacts(
        codec_id=codec_id or f"cmy7-p{params.sites}-v{params.gen}",
        family=Family.CMY7,
        n_sites=params.sites,
        n_dust=params.sites - N_WORD_SITES,
        dust_base_cycle=CMY7_DUST_CYCLE,
        rungs=(),
        bits_per_mapper_unit=CMY7_BITS_PER_MAPPER_UNIT,
        cells_per_mapper_unit=CMY7_CELLS_PER_MAPPER_UNIT,
        streams=(StreamFacts("main", bank, COLOR_STREAM_MAIN),),
        pooled_fountain=False)


def _cmy8_facts(params: CodingParams, codec_id: str | None,
                bank_ids: tuple[str, ...] | None) -> CodecFacts:
    """CMY8: three per-plane presence streams, one pooled outer code.

    Per-plane independent LDPC is the graceful-degradation axis — a dead
    plane costs its own stream and no other, which is how e032's CMY8
    volume closed on paper where its CMY7 twin did not — and the pooled
    fountain (one fountain over esi = counter*3 + stream, stream-exact
    quotas) is what turns three streams back into one volume.  Rung
    triplets are the format-side lever the measured Xerox Y-registration
    sinusoid asks for; gen-v1 pools ONE symbol width, so a triplet must
    share ``k_bits`` (``lattice.require_constructible`` refuses the rest).
    """
    if bank_ids is None:
        bank_ids = tuple(
            f"cmy8-{plane}-{rung}-p{params.sites}-v{params.gen}"
            for plane, rung in zip(CMY_PLANE_ORDER, params.rungs))
    aux = (COLOR_STREAM_C, COLOR_STREAM_M, COLOR_STREAM_Y)
    streams = tuple(
        StreamFacts(plane, FecBankFacts(bank_id, ((rung, params.sites),)),
                    stream_aux)
        for plane, rung, bank_id, stream_aux
        in zip(CMY_PLANE_ORDER, params.rungs, bank_ids, aux))
    return CodecFacts(
        codec_id=codec_id or (f"cmy8-{rung_token(params.rungs)}-"
                              f"p{params.sites}-v{params.gen}"),
        family=Family.CMY8,
        n_sites=params.sites,
        n_dust=params.sites - N_WORD_SITES,
        dust_base_cycle=CMY8_DUST_CYCLE,
        rungs=params.rungs,
        bits_per_mapper_unit=CMY8_BITS_PER_MAPPER_UNIT,
        cells_per_mapper_unit=CMY8_CELLS_PER_MAPPER_UNIT,
        streams=streams,
        pooled_fountain=True)


def colour_codec(params: CodingParams, *,
                 _codec_id: str | None = None,
                 _bank_ids: tuple[str, ...] | None = None) -> CodecFacts:
    """One colour lattice point -> its frozen codec facts.

    Dispatch is on the family enum (FORMAT-SPACE P1), and the family
    algebra is checked ONCE at this door
    (``lattice.require_constructible``, rows A1-A7) rather than in each
    branch — the same reason the origin refuses at the constructor: a
    dust-free colour row parses as lawful and then dies deep in
    emission or receive.

    The two private overrides exist SOLELY for legacy resolution
    (``fossils``).  The branch-minted ``-x1`` rows and the catalogue's
    ``-v0``/``-v1`` rows carry codec and bank id strings the v2 grammar
    has no spelling for — ``cmy8-presence-r0700-p120-x1`` keeps a
    ``presence`` token the mint dropped, and the ``-p120-v0`` banks
    carry no rung token at all — and those strings are hashed into
    persisted certificate and decoder identities, so sheet I's verified
    state replays bit-identically only if they are carried as DATA.
    There is deliberately no ``pooled`` override: every cmy8 identity
    holo2 can name is pooled, because the unpooled ``-v0`` rows are the
    two entries the sunset ruling drops (RULINGS G8), and an override
    that no constructible state needs is guard mass (L17).
    """
    if params.family is Family.K:
        raise ValueError(
            "k is not a colour family: a K coding is minted by "
            "format_v1.coding_for")
    require_constructible(params)
    if _bank_ids is not None:
        expected = 1 if params.family is Family.CMY7 else len(CMY_PLANE_ORDER)
        if len(_bank_ids) != expected or len(set(_bank_ids)) != expected:
            raise ValueError(
                f"{params.family.value}: bank id override must name "
                f"{expected} distinct bank(s)")
    if params.family is Family.CMY7:
        return _cmy7_facts(params, _codec_id, _bank_ids)
    return _cmy8_facts(params, _codec_id, _bank_ids)


__all__ = [
    "CMY7_BANK_CHILDREN", "CMY7_BITS_PER_MAPPER_UNIT",
    "CMY7_CELLS_PER_MAPPER_UNIT", "CMY7_DUST_CYCLE",
    "CMY8_BITS_PER_MAPPER_UNIT", "CMY8_CELLS_PER_MAPPER_UNIT",
    "CMY8_DUST_CYCLE", "CMY_PLANE_ORDER", "CodecFacts", "FecBankFacts",
    "StreamFacts", "colour_codec",
]
