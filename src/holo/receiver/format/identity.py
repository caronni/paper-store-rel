from __future__ import annotations

import enum
import math
import re
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np

from . import fountain, keystream, pilots, tile_codec


class Family(str, enum.Enum):
    K = "k"
    CMY7 = "cmy7"
    CMY8 = "cmy8"
    CMY = "cmy"


L_PREFIX = "L:"
#: The two frozen markers that say which identity space a string
#: belongs to: `L:` on every legacy surface, `holo/v2/` as the v2 row
#: seed's own prefix.  The AES KDF label is unaffected — it stays
#: `holo/v1|` in both spaces (see keystream._KDF_PREFIX).
SEED_NAMESPACE = b"holo/v2/"
#: Shared with v1 ACROSS the namespace split, deliberately: the site
#: lattice is a frozen subsystem address, so equal-density sheets
#: share one measured layout and the E022/E023 placement lineage.  A
#: v2 row's site seed is still holo/v1/sites/pN; versioning it forks.
SITES_SEED_TEMPLATE = "holo/v1/sites/p{sites}"
#: v1 invariant: the mother-code length IS the tile slot count, so the
#: transmitted-position count and the non-site cell count coincide.
#: holo3 spells both numbers again in tile_codec (N_CELLS, CRC_BITS)
#: and asserts nothing — they must move together.
N_BITS = 4096
CRC_BITS = 32
METADATA_BITS_PER_TILE = 1
MAX_TILES = 1 << pilots.COUNTER_BITS
#: The EMISSION grid: both engines of the printed record are fixed-600
#: end to end.  It spells the legacy --coding/--printer field AND, via
#: color_sites.cell_dots_of, a row's printed cell_dots.  A capture's
#: px/cell is pitch_in x the DECLARED scan dpi -- never fit from a page.
HW_DPI = 600
MM_PER_INCH = 25.4
A4_MM: tuple[float, float] = (210.0, 297.0)
A3_MM: tuple[float, float] = (297.0, 420.0)

#: 6.0 mm is the policy margin; hp-m281-ink's 4.5 mm is the e028
#: ink-clip probe geometry (measured printable clip ~4.15-4.28 mm;
#: 4.5 selects the next 64-cell quantum).  Not a payload-safe
#: promotion (experiments/028-discovery-m281.md).
MARGIN_MM: dict[str, float] = {
    "default": 6.0,
    "hp-m281": 6.0,
    "hp-m281-ink": 4.5,
    "xerox-altalink-c8245": 6.0,
}

#: k_bits per rung; n_bits is 4096 for every rung, so a rung's name is
#: its target rate and the k is the Z-quantized snap.  r0547 and r0550
#: share k=2240 and are DISTINCT codes (independent construction
#: draws), not a duplicate (conversion_docs/04-format-identity.md:71).
LADDER: dict[str, int] = {
    "r0547": 2240,
    "r0550": 2240,
    "r0625": 2560,
    "r0700": 2880,
    "r0775": 3200,
    "r0850": 3520,
}

#: Names for exact rationals of an inch; append-only, and a number is
#: never reinterpreted.  No grid is privileged — the registry holds
#: 600-grid multiples only because those are the measured engines; a
#: 1200-dpi engine's 3-dot cell is spelled `1i400` and needs no entry.
PITCH_CLASSES: dict[str, Fraction] = {
    "c1": Fraction(1, 600),
    "c2": Fraction(1, 300),
    "c3": Fraction(1, 200),
    "c4": Fraction(1, 150),
}
_CLASS_BY_PITCH: dict[Fraction, str] = {
    pitch: name for name, pitch in PITCH_CLASSES.items()}

#: A cmy8 row's three streams ARE the planes, in this order.  Their
#: PLANE index is 0/1/2 and their fountain AUX is 1/2/3 — two
#: different numbers per stream (see _streams_for).  tile_codec spells
#: this order a second time as PLANE_ORDER; they must agree.
CMY_PLANE_ORDER: tuple[str, str, str] = ("C", "M", "Y")
#: Physical state ids of the presence alphabet (W=0 C=1 M=2 CM=3 Y=4
#: CY=5 MY=6 CMY=7), in canonical missing-state order.  CMY7 has no
#: CMY state — that is what makes it seven — so its cycle is one
#: shorter.  The cycle is a codec FACT, never a dispatch branch.
CMY7_DUST_CYCLE: tuple[int, ...] = (1, 2, 4, 5, 6)
CMY8_DUST_CYCLE: tuple[int, ...] = (1, 2, 4, 5, 6, 7)
#: The baked pack7 bank: one r0550 child plus two r0625 shortened to
#: 1883 active info bits each, so transmitted 4096+3419+3419 = 10,934
#: bits exactly fill 994 four-cell packs at 11 bits — 994*4 = 3,976 =
#: the p120 payload cells.  Baked per generation, hence data.
CMY7_BANK_CHILDREN: tuple[tuple[str, int], ...] = (
    ("r0550", 0), ("r0625", 677), ("r0625", 677))
#: The mapper's frozen dimensions.  CMY7 packs 11 bits into 4 cells
#: because 7^4 = 2401 > 2^11 = 2048; CMY8 carries 3 bits per cell —
#: one presence bit per plane, which is the same three bits its three
#: STREAMS each carry a cell's worth of.  (K is 1/1 and unspelled.)
CMY7_BITS_PER_MAPPER_UNIT = 11
CMY7_CELLS_PER_MAPPER_UNIT = 4
CMY8_BITS_PER_MAPPER_UNIT = 3
CMY8_CELLS_PER_MAPPER_UNIT = 1
#: cmy's cell carries one bit of each of its two LABEL streams.
CMY_BITS_PER_MAPPER_UNIT = 2
CMY_CELLS_PER_MAPPER_UNIT = 1

_PITCH_CLASS_RE = re.compile(r"^c[0-9]+$")
_PITCH_RATIONAL_RE = re.compile(r"^([0-9]+)i([0-9]+)$")
_RUNGS_TOKEN_RE = re.compile(r"^r[0-9]{4}(?:x[0-9]{4})*$")
_SITES_RE = re.compile(r"^p([0-9]+)$")
_GEN_RE = re.compile(r"^v([0-9]+)$")
_TILES_RE = re.compile(r"^([0-9]+)x([0-9]+)$")

_DEFAULT_SITES: dict[Family, int] = {
    Family.K: 100, Family.CMY7: 120, Family.CMY8: 120, Family.CMY: 120}
_DEFAULT_GEN = 1
_DEFINED_GENS: tuple[int, ...] = (1,)
assert _DEFAULT_GEN in _DEFINED_GENS
_RUNG_ARITY: dict[Family, int] = {
    Family.K: 1, Family.CMY7: 0, Family.CMY8: 3, Family.CMY: 2}
#: A family's alphabet: K's (W, K) as (0, 1), else presence ids.
_STATE_IDS: dict[Family, tuple[int, ...]] = {
    Family.K: (0, 1), Family.CMY7: tuple(range(7)),
    Family.CMY8: tuple(range(8)), Family.CMY: tile_codec.CMY_STATE_IDS}


def state_ids_of(family: Family) -> tuple[int, ...]:
    return _STATE_IDS[family]


#: The per-cell streams, one rung each: cmy8's are the toner planes,
#: cmy's the label bits.
_STREAM_IDS: dict[Family, tuple[str, ...]] = {
    Family.CMY8: CMY_PLANE_ORDER, Family.CMY: tile_codec.CMY_LABEL_STREAMS}


class StreamHasNoPlane(TypeError):
    pass


#: A stream is named by its id.  A TONER stream (K's and cmy7's
#: "main" on PLANE_K, cmy8's C/M/Y on planes 0/1/2) carries one
#: toner's presence and has a `plane`; a LABEL stream (cmy's hi/lo,
#: label bits 0/1) carries one bit of the cell's state label, belongs
#: to no toner, and its `plane` RAISES -- never a None sentinel, which
#: numpy would read as a new axis (`x[:, None]`).  `dither_aux` is the
#: domain-13 per-stream dither aux, the stream index + 1 (cmy8 1/2/3,
#: cmy 1/2); K and cmy7 have none (CMY-RECEIVER-PLAN I-2).
@dataclass(frozen=True)
class StreamFact:
    stream_id: str
    plane_index: int | None
    fountain_aux: int | None
    rung_children: tuple[tuple[str, int], ...]
    user_bits: int
    symbol_bits: int
    label_index: int | None
    dither_aux: int | None

    def __post_init__(self) -> None:
        if (self.plane_index is None) == (self.label_index is None):
            raise ValueError(
                f"stream {self.stream_id!r}: exactly one of plane_index "
                f"({self.plane_index}) and label_index "
                f"({self.label_index}) -- a stream is a toner stream or "
                f"a label stream")

    @property
    def plane(self) -> int:
        if self.plane_index is None:
            raise StreamHasNoPlane(
                f"stream {self.stream_id!r} is label stream "
                f"{self.label_index}: it carries a state-label bit, not "
                f"a toner, and has no plane")
        return self.plane_index


@dataclass(frozen=True)
class FormatRow:
    row_id: str
    display_id: str
    seed: bytes
    sites_seed: bytes
    family: Family
    tiles_yx: tuple[int, int]
    pitch_in: Fraction
    n_sites: int
    n_dust: int
    dust_base_cycle: tuple[int, ...]
    word_states: tuple[int, int]
    streams: tuple[StreamFact, ...]
    pooled_fountain: bool
    bits_per_mapper_unit: int
    cells_per_mapper_unit: int

    @property
    def state_ids(self) -> tuple[int, ...]:
        return state_ids_of(self.family)

    @property
    def cells_yx(self) -> tuple[int, int]:
        return (self.tiles_yx[0] * pilots.TILE_CELLS,
                self.tiles_yx[1] * pilots.TILE_CELLS)

    @property
    def tiles_per_page(self) -> int:
        return self.tiles_yx[0] * self.tiles_yx[1]

    @property
    def max_pages(self) -> int:
        return MAX_TILES // self.tiles_per_page

    @property
    def payload_cells(self) -> int:
        return N_BITS - self.n_sites

    @property
    def n_transmitted_slots(self) -> int:
        return N_BITS - self.n_sites

    def tile_counter(self, page: int, ty: int, tx: int) -> int:
        return page * self.tiles_per_page + ty * self.tiles_yx[1] + tx

    def tile_address(self, counter: int) -> tuple[int, int, int]:
        page, rem = divmod(counter, self.tiles_per_page)
        ty, tx = divmod(rem, self.tiles_yx[1])
        return page, ty, tx


@dataclass(frozen=True)
class SiteGeometry:
    word_cells_yx: np.ndarray
    extra_cells_yx: np.ndarray
    shorten_flat: np.ndarray
    payload_flat: np.ndarray
    slot_a: np.ndarray
    slot_b: np.ndarray
    _scramble: dict[int, np.ndarray] = field(
        default_factory=dict, repr=False, compare=False)


def _bank_user_bits(children: tuple[tuple[str, int], ...]) -> int:
    return sum(LADDER[rung] - shortened
               for rung, shortened in children) - CRC_BITS


def _streams_for(family: Family, rungs: tuple[str, ...],
                 sites: int) -> tuple[StreamFact, ...]:
    if family is Family.K:
        children = ((rungs[0], sites),)
        user = _bank_user_bits(children)
        return (StreamFact("main", keystream.PLANE_K, None, children, user,
                           user - METADATA_BITS_PER_TILE,
                           label_index=None, dither_aux=None),)
    if family is Family.CMY7:
        user = _bank_user_bits(CMY7_BANK_CHILDREN)
        return (StreamFact("main", keystream.PLANE_K, 0,
                           CMY7_BANK_CHILDREN, user,
                           user - METADATA_BITS_PER_TILE,
                           label_index=None, dither_aux=None),)
    toner = family is Family.CMY8
    out: list[StreamFact] = []
    for index, (stream_id, rung) in enumerate(
            zip(_STREAM_IDS[family], rungs, strict=True)):
        children = ((rung, sites),)
        user = _bank_user_bits(children)
        out.append(StreamFact(
            stream_id, index if toner else None,
            keystream.COLOR_STREAM_AUX[stream_id] if toner else None,
            children, user, user - METADATA_BITS_PER_TILE,
            label_index=None if toner else index, dither_aux=index + 1))
    return tuple(out)


def _make_row(row_id: str, display_id: str, seed: bytes, family: Family,
              pitch_in: Fraction, rungs: tuple[str, ...], sites: int,
              tiles_yx: tuple[int, int], pooled: bool) -> FormatRow:
    if family is Family.K:
        n_dust = 0
        cycle: tuple[int, ...] = ()
        word_states = (0, 1)
        bits_unit, cells_unit = 1, 1
    elif family is Family.CMY7:
        n_dust = sites - pilots.N_WORD_SITES
        cycle = CMY7_DUST_CYCLE
        word_states = (0, 3)
        bits_unit = CMY7_BITS_PER_MAPPER_UNIT
        cells_unit = CMY7_CELLS_PER_MAPPER_UNIT
    elif family is Family.CMY8:
        n_dust = sites - pilots.N_WORD_SITES
        cycle = CMY8_DUST_CYCLE
        word_states = (0, 3)
        bits_unit = CMY8_BITS_PER_MAPPER_UNIT
        cells_unit = CMY8_CELLS_PER_MAPPER_UNIT
    elif family is Family.CMY:
        # word '1' prints C, '0' W or the keyed Y (pilots); the dust is
        # the per-tile balance law, not a cycle
        n_dust = sites - pilots.N_WORD_SITES
        cycle = ()
        word_states = (0, 1)
        bits_unit = CMY_BITS_PER_MAPPER_UNIT
        cells_unit = CMY_CELLS_PER_MAPPER_UNIT
    else:
        raise KeyError(family)
    return FormatRow(
        row_id=row_id,
        display_id=display_id,
        seed=seed,
        sites_seed=SITES_SEED_TEMPLATE.format(sites=sites).encode(),
        family=family,
        tiles_yx=tiles_yx,
        pitch_in=pitch_in,
        n_sites=sites,
        n_dust=n_dust,
        dust_base_cycle=cycle,
        word_states=word_states,
        streams=_streams_for(family, rungs, sites),
        pooled_fountain=pooled,
        bits_per_mapper_unit=bits_unit,
        cells_per_mapper_unit=cells_unit)


#: Y is r0547, NOT r0550: same k_bits, different parity matrix.
#: Swapping them decodes Y to garbage while C and M stay green — a
#: failure that looks like a dead yellow plane
#: (conversion_docs/04-format-identity.md:448-450).
_CMY8_V01_RUNGS: tuple[str, ...] = ("r0550", "r0550", "r0547")

#: The printed record: e029/e030/e032 and e033 sheets A-I.  Fossil ids
#: are MATCHED byte-exactly, never parsed — a legacy string re-parsed
#: under v2 rules could normalize into a different seed, forking a
#: whole sheet (conversion_docs/04-format-identity.md:127-169, :344-345).
_FOSSILS: dict[str, tuple[bytes, tuple[int, int], Fraction, Family,
                          tuple[str, ...], int, bool]] = {
    "c3-r0550@2240x1536": (
        b"holo/v1/c3-r0550/2240x1536", (35, 24), Fraction(1, 200),
        Family.K, ("r0550",), 100, False),
    "c2-r0550@3328x2304": (
        b"holo/v1/c2-r0550/3328x2304", (52, 36), Fraction(1, 300),
        Family.K, ("r0550",), 100, False),
    "c2-r0700@3328x2304": (
        b"holo/v1/c2-r0700/3328x2304", (52, 36), Fraction(1, 300),
        Family.K, ("r0700",), 100, False),
    "c2-r0700@3392x2368": (
        b"holo/v1/c2-r0700/3392x2368", (53, 37), Fraction(1, 300),
        Family.K, ("r0700",), 100, False),
    "c2-cmy7-p120-v0@3328x2304": (
        b"holo/v1/c2-cmy7-p120-v0/3328x2304", (52, 36), Fraction(1, 300),
        Family.CMY7, (), 120, False),
    "c3-cmy7-p120-v0@2240x1536": (
        b"holo/v1/c3-cmy7-p120-v0/2240x1536", (35, 24), Fraction(1, 200),
        Family.CMY7, (), 120, False),
    "c2-cmy8-p120-v0@3328x2304": (
        b"holo/v1/c2-cmy8-p120-v0/3328x2304", (52, 36), Fraction(1, 300),
        Family.CMY8, _CMY8_V01_RUNGS, 120, False),
    "c3-cmy8-p120-v0@2240x1536": (
        b"holo/v1/c3-cmy8-p120-v0/2240x1536", (35, 24), Fraction(1, 200),
        Family.CMY8, _CMY8_V01_RUNGS, 120, False),
    "c2-cmy8-p120-v1@3328x2304": (
        b"holo/v1/c2-cmy8-p120-v1/3328x2304", (52, 36), Fraction(1, 300),
        Family.CMY8, _CMY8_V01_RUNGS, 120, True),
    "c3-cmy8-p120-v1@2240x1536": (
        b"holo/v1/c3-cmy8-p120-v1/2240x1536", (35, 24), Fraction(1, 200),
        Family.CMY8, _CMY8_V01_RUNGS, 120, True),
    "c2-cmy8-p120-v1@3392x2368": (
        b"holo/v1/c2-cmy8-p120-v1/3392x2368", (53, 37), Fraction(1, 300),
        Family.CMY8, _CMY8_V01_RUNGS, 120, True),
    "c4-r0550@1664x1152": (
        b"holo/v1/c4-r0550/1664x1152", (26, 18), Fraction(1, 150),
        Family.K, ("r0550",), 100, False),
    "c2-cmy8-r0700-p120-x1@3392x2368": (
        b"holo/v1/c2-cmy8-r0700-p120-x1/3392x2368", (53, 37),
        Fraction(1, 300), Family.CMY8, ("r0700", "r0700", "r0700"),
        120, True),
    "c2-cmy8-r0850-p120-x1@3392x2368": (
        b"holo/v1/c2-cmy8-r0850-p120-x1/3392x2368", (53, 37),
        Fraction(1, 300), Family.CMY8, ("r0850", "r0850", "r0850"),
        120, True),
    "c2-cmy8-r0547@53x37": (
        b"holo/v2/c2-cmy8-r0547@53x37", (53, 37), Fraction(1, 300),
        Family.CMY8, ("r0547", "r0547", "r0547"), 120, True),
}


def _parse_pitch(token: str) -> Fraction:
    if _PITCH_CLASS_RE.match(token):
        pitch = PITCH_CLASSES.get(token)
        if pitch is None:
            raise ValueError(f"unregistered pitch class {token!r}; "
                             f"registered: {sorted(PITCH_CLASSES)}")
        return pitch
    rational = _PITCH_RATIONAL_RE.match(token)
    if rational:
        n, d = int(rational.group(1)), int(rational.group(2))
        if n < 1 or d < 1:
            raise ValueError(f"pitch {token!r} must be a positive rational")
        return Fraction(n, d)
    raise ValueError(
        f"pitch token {token!r} is neither a registered class nor NiD")


def _canonical_pitch_token(pitch: Fraction) -> str:
    if pitch <= 0:
        raise ValueError(f"pitch {pitch} must be a positive rational")
    return f"{pitch.numerator}i{pitch.denominator}"


def _display_pitch_token(pitch: Fraction) -> str:
    name = _CLASS_BY_PITCH.get(pitch)
    if name is not None:
        return name
    return _canonical_pitch_token(pitch)


def _rung_token(rungs: tuple[str, ...]) -> str:
    if len(set(rungs)) == 1:
        return rungs[0]
    return "r" + "x".join(rung.removeprefix("r") for rung in rungs)


def _parse_coding(coding_id: str) -> tuple[Fraction, Family,
                                           tuple[str, ...], int, int]:
    tokens = coding_id.split("-")
    if len(tokens) < 2:
        raise ValueError(
            f"coding id {coding_id!r} needs at least pitch and family")
    pitch = _parse_pitch(tokens[0])
    try:
        family = Family(tokens[1])
    except ValueError:
        raise ValueError(
            f"coding id {coding_id!r}: unknown family {tokens[1]!r} "
            f"(legacy identities resolve through the L: fossil catalogue)"
        ) from None
    rungs: tuple[str, ...] = ()
    sites = _DEFAULT_SITES[family]
    gen = _DEFAULT_GEN
    rest = tokens[2:]
    idx = 0
    if idx < len(rest) and _RUNGS_TOKEN_RE.match(rest[idx]):
        body = rest[idx][1:]
        rungs = tuple(f"r{part}" for part in body.split("x"))
        if len(rungs) == 1 and _RUNG_ARITY[family] > 1:
            rungs = rungs * _RUNG_ARITY[family]
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
            f"coding id {coding_id!r}: unrecognized or misordered token "
            f"{rest[idx]!r} (order: rungs, sites, generation)")
    if len(rungs) != _RUNG_ARITY[family]:
        raise ValueError(
            f"coding id {coding_id!r}: {family.value} rung arity must be "
            f"{_RUNG_ARITY[family]}, got {rungs}")
    return pitch, family, rungs, sites, gen


#: p < 100 is RESERVED, not unimplemented — it is the e026
#: site-count line.  The cmy8 triplet no longer needs one shared
#: k_bits: fountain.column_groups validates any width mix is
#: poolable (CMY8-COLUMN-GROUPS.md; width classes, 2026-09-04).
def _require_constructible(coding_id: str, family: Family,
                           rungs: tuple[str, ...], sites: int,
                           gen: int) -> None:
    for rung in rungs:
        if rung not in LADDER:
            raise ValueError(f"{coding_id}: unknown LDPC rung {rung!r}; "
                             f"ladder: {sorted(LADDER)}")
    if gen not in _DEFINED_GENS:
        raise ValueError(f"{coding_id}: generation v{gen} is not defined")
    if sites < pilots.N_WORD_SITES:
        raise ValueError(
            f"{coding_id}: p{sites} is below the "
            f"{pilots.N_WORD_SITES}-site word floor (p<100 is reserved)")
    if family is Family.CMY7 and sites != 120:
        raise ValueError(
            f"{coding_id}: cmy7 v1 bakes its joint pack7 bank at p120")
    if family is Family.CMY8 and sites == pilots.N_WORD_SITES:
        raise ValueError(
            f"{coding_id}: cmy8 needs at least one dust site (p > 100)")
    if family is Family.CMY and sites == pilots.N_WORD_SITES:
        raise ValueError(
            f"{coding_id}: cmy needs at least one dust site (p > 100): "
            f"word '1' is C and word '0' W or Y, so M is printed only in "
            f"dust and p100 leaves it no anchor")
    for rung in rungs:
        user_bits = LADDER[rung] - CRC_BITS - sites
        if user_bits <= METADATA_BITS_PER_TILE:
            raise ValueError(
                f"{coding_id}: p{sites} leaves {user_bits} user bits in "
                f"the {rung} frame — no room for metadata and a symbol")
    if _RUNG_ARITY[family] > 1:
        fountain.column_groups(tuple(
            stream.symbol_bits
            for stream in _streams_for(family, rungs, sites)))


#: Amendment A-1 (2026-08-30): the canonical id — which IS the AES
#: seed — is the FULLY EXPLICIT spelling.  The earlier shortest form
#: read mutable tables, so a sanctioned edit to them re-keyed printed
#: sheets.  The short form survives as display_id, never seeded.
def _canonical_coding_id(pitch: Fraction, family: Family,
                         rungs: tuple[str, ...], sites: int,
                         gen: int) -> str:
    parts = [_canonical_pitch_token(pitch), family.value]
    if rungs:
        parts.append(_rung_token(rungs))
    parts.append(f"p{sites}")
    parts.append(f"v{gen}")
    return "-".join(parts)


def _display_coding_id(pitch: Fraction, family: Family,
                       rungs: tuple[str, ...], sites: int,
                       gen: int) -> str:
    parts = [_display_pitch_token(pitch), family.value]
    if rungs:
        parts.append(_rung_token(rungs))
    if sites != _DEFAULT_SITES[family]:
        parts.append(f"p{sites}")
    if gen != _DEFAULT_GEN:
        parts.append(f"v{gen}")
    return "-".join(parts)


#: POOLING IS DATA, NOT FAMILY: every v2 row of rung arity > 1 (cmy8,
#: cmy) pools, but the v1 `-v0` fossils on paper (e030, e032) are
#: UNPOOLED and carry the flag from their own bundle.  Deriving
#: pooled-ness from the family reads those sheets with the wrong outer
#: code and never closes.
def mint_format(*, pitch: Fraction, family: Family,
                rungs: tuple[str, ...], sites: int, gen: int,
                tiles_yx: tuple[int, int]) -> FormatRow:
    if tiles_yx[0] < 1 or tiles_yx[1] < 1:
        raise ValueError(f"tile matrix {tiles_yx} must be at least 1x1")
    if tiles_yx[0] * tiles_yx[1] > MAX_TILES:
        raise ValueError(
            f"tile matrix {tiles_yx} exceeds the "
            f"{pilots.COUNTER_BITS}-bit counter space")
    if len(rungs) != _RUNG_ARITY[family]:
        raise ValueError(
            f"{family.value} rung arity must be {_RUNG_ARITY[family]}, "
            f"got {rungs}")
    coding = _canonical_coding_id(pitch, family, rungs, sites, gen)
    _require_constructible(coding, family, rungs, sites, gen)
    matrix = f"@{tiles_yx[0]}x{tiles_yx[1]}"
    row_id = coding + matrix
    display_id = _display_coding_id(pitch, family, rungs, sites, gen) + matrix
    return _make_row(row_id, display_id, SEED_NAMESPACE + row_id.encode(),
                     family, pitch, rungs, sites, tiles_yx,
                     _RUNG_ARITY[family] > 1)


def resolve_format_ref(ref: str) -> FormatRow:
    if ref.startswith(L_PREFIX):
        key = ref[len(L_PREFIX):]
        entry = _FOSSILS.get(key)
        if entry is None:
            raise ValueError(
                f"unknown fossil id {key!r} (fossils match byte-exactly, "
                f"they are never parsed)")
        seed, tiles_yx, pitch, family, rungs, sites, pooled = entry
        row_id = L_PREFIX + key
        if tiles_yx[0] * tiles_yx[1] > MAX_TILES:
            raise ValueError(
                f"{ref!r}: {tiles_yx} tiles exceed the "
                f"{pilots.COUNTER_BITS}-bit counter space")
        return _make_row(row_id, row_id, seed, family, pitch, rungs, sites,
                         tiles_yx, pooled)
    if "@" not in ref:
        raise ValueError(
            f"format id {ref!r} needs a tile matrix: coding@TYxTX")
    coding_part, _, tiles_part = ref.rpartition("@")
    tiles = _TILES_RE.match(tiles_part)
    if not tiles:
        raise ValueError(
            f"format id {ref!r}: tile matrix must be TYxTX")
    pitch, family, rungs, sites, gen = _parse_coding(coding_part)
    return mint_format(pitch=pitch, family=family, rungs=rungs, sites=sites,
                       gen=gen, tiles_yx=(int(tiles.group(1)),
                                          int(tiles.group(2))))


#: Nearest multiple of 8 dots per axis: byte-aligned rows for the
#: 1-bit PostScript imagemask (F15).  A4 -> (4960, 7016), which
#: reproduces paperholo compose.py's frozen A4_W_DOTS/A4_H_DOTS
#: exactly (conversion_docs/04-format-identity.md:197-198).
def page_dots_xy(media_mm: tuple[float, float]) -> tuple[int, int]:
    w_mm, h_mm = media_mm
    return (8 * int(math.floor(w_mm / MM_PER_INCH * HW_DPI / 8 + 0.5)),
            8 * int(math.floor(h_mm / MM_PER_INCH * HW_DPI / 8 + 0.5)))


#: The v1 legacy field law, kept only to spell the e029 sugar's
#: identity: at hp-m281-ink c2 it lands 3392x2368 cells = 53x37 tiles,
#: which IS fossil c2-r0700@3392x2368.  The emission-side slack split
#: is dropped (conversion_docs/04-format-identity.md:192-211).
def derive_field(media_mm: tuple[float, float], margin_mm: float,
                 cell_dots: int) -> tuple[int, int]:
    page_x, page_y = page_dots_xy(media_mm)
    margin_dots = math.ceil(margin_mm / MM_PER_INCH * HW_DPI)
    cells_y = ((page_y - 2 * margin_dots) // cell_dots
               // pilots.TILE_CELLS * pilots.TILE_CELLS)
    cells_x = ((page_x - 2 * margin_dots) // cell_dots
               // pilots.TILE_CELLS * pilots.TILE_CELLS)
    return cells_y, cells_x


def coding_printer_ref(coding_id: str, printer_id: str) -> str:
    margin_mm = MARGIN_MM[printer_id]
    pitch = PITCH_CLASSES[coding_id.split("-")[0]]
    cell_dots = int(pitch * HW_DPI)
    cells_y, cells_x = derive_field(A4_MM, margin_mm, cell_dots)
    return f"{L_PREFIX}{coding_id}@{cells_y}x{cells_x}"


#: Slot parameters are drawn ONCE for every counter the page geometry
#: can address, at startup, and frozen read-only: it removes the only
#: rejection loop from the hot path and avoids a shared mutable cache
#: under free threading (conversion_docs/04-format-identity.md:479-484).
def build_site_geometry(row: FormatRow) -> SiteGeometry:
    word = pilots.word_site_cells_yx(row.sites_seed)
    if row.family is Family.K:
        extra = pilots.filler_site_cells_yx(
            row.sites_seed, row.n_sites - pilots.N_WORD_SITES, word)
    else:
        extra = pilots.dust_site_cells_yx(row.sites_seed, row.n_dust)
    cells = np.concatenate([word, extra], axis=0)
    flat = cells[:, 0] * pilots.TILE_CELLS + cells[:, 1]
    shorten_flat = np.sort(flat)
    occupied = np.zeros(N_BITS, dtype=bool)
    occupied[flat] = True
    payload_flat = np.flatnonzero(~occupied).astype(np.int64, copy=False)
    tile_counters = np.arange(row.max_pages * row.tiles_per_page,
                              dtype=np.int64)
    slot_a, slot_b = keystream.slot_perm_params(
        row.seed, tile_counters, row.n_transmitted_slots)
    for arr in (word, extra, shorten_flat, payload_flat, slot_a, slot_b):
        arr.setflags(write=False)
    return SiteGeometry(word, extra, shorten_flat, payload_flat,
                        slot_a, slot_b)


#: Per-page memo on the frozen geometry (compare/repr excluded), not a
#: module cache: the planes are large, page-global and read-only, so a
#: racing rebuild yields an identical array.  Site cells stay
#: scrambled here; the erasure to exactly 0.0 happens in the LLR path.
def scramble_plane(row: FormatRow, geometry: SiteGeometry,
                   page: int) -> np.ndarray:
    memo = geometry._scramble
    key = int(page)
    cached = memo.get(key)
    if cached is None:
        cached = keystream.payload_bits(
            row.seed, keystream.PLANE_K, key, row.cells_yx)
        cached.setflags(write=False)
        memo[key] = cached
    return cached
