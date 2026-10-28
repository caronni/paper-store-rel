"""Format identity, split along the axes the record keeps separate.

A CODING is printer-independent (HOLO-DESIGN §3/§8, reshaped 2026-07-19;
FORMAT-SPACE 2026-08-19): physical cell pitch, immutable tile-codec
profile, and furniture density.  Its facts are per-tile — payload cells,
logical streams, FEC, physical pitch — and hold on any engine.  The
established ``rate_id`` remains populated for K.

Two identity namespaces coexist until the fossil sunset:

- ``v1`` (legacy): the frozen printed record.  Geometry is derived from
  media minus margins; the row seed is
  ``holo/v1/<coding_id>/<cells_y>x<cells_x>``.  Append-only and closed —
  new v1 rows are never minted.
- ``v2`` (the lattice, FORMAT-SPACE §6): identity = coding x tile
  matrix; the canonical format id IS the seed payload under
  ``holo/v2/``.  Codings are minted by ``lattice.parse_format_id`` /
  ``make_format`` through the family constructors.

Both namespaces share the frozen family seed
``holo/v1/sites/p<n_sites>`` — site placement law is a frozen subsystem
address, so equal-density sheets share their measured site layout across
namespaces.

A wrong-identity hypothesis descrambles every pilot word to coin flips
and refuses at the word gate (HOLO-DESIGN §4.5).
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from functools import cached_property
from types import MappingProxyType

from ..core.column_groups import ColumnGroups, column_groups
from ..core.ldpc.construct import LADDER
from . import layout as layout_mod
from . import pilots
from .layout import (
    FieldLayout,
    MM_PER_DOT,
    TILE_CELLS,
    VALID_CELL_DOTS,
    derive_field,
)
from .profiles import (
    CodecProfile,
    Family,
    StreamProfile,
    _CMY7_P120_V0,
    _CMY8_P120_V0,
    k_profile,
)

V2_SEED_NAMESPACE = b"holo/v2/"


@dataclass(frozen=True)
class Coding:
    coding_id: str
    cell_dots: int | None   # dots/cell on the 600 grid; None = off-600 (v2)
    rate_id: str | None     # established scalar K rung
    n_filler: int = 0       # known sites above the 100-site word floor
    codec: CodecProfile | None = None
    # Pooled outer code (docs/CMY8-POOLED-FOUNTAIN.md): ONE fountain over
    # esi = counter*n_streams + stream_idx with stream-exact block quotas
    # on the K domains 7/8, and per-stream metadata equations.  The TILE
    # codec is identical to the per-stream rows; under a pooled row the
    # StreamProfile.fountain_aux values are a -v0-fountain fact and are
    # deliberately unused.
    pooled_fountain: bool = False
    pitch_in: Fraction | None = None    # exact physical pitch (v2)
    namespace: str = "v1"
    # Short spelling for people (class names, defaults omitted).  Minted
    # alongside the canonical id; NEVER stored and never seeded
    # (FORMAT-SPACE §6/§16).  None on v1 rows: their id is already frozen.
    display_coding_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.coding_id, str) or not self.coding_id:
            raise ValueError("coding_id must be a non-empty string")
        if self.n_filler < 0:
            raise ValueError("n_filler must be >= 0")
        if self.namespace == "v1":
            self._validate_v1()
        elif self.namespace == "v2":
            self._validate_v2()
        else:
            raise ValueError(f"unknown identity namespace {self.namespace!r}")
        if self.pooled_fountain:
            assert self.codec is not None
            if len(self.codec.streams) < 2:
                raise ValueError(
                    f"{self.coding_id}: a pooled fountain needs at least "
                    f"two streams")
        if self.payload_bits_per_tile < 1:
            raise ValueError(
                f"{self.coding_id}: n_filler={self.n_filler} leaves "
                f"{self.payload_bits_per_tile} payload bits/tile — the "
                f"density dial cannot consume the tile")
        if self.codec is None:  # object.__setattr__ above is load-bearing
            raise AssertionError("codec profile initialization failed")

    def _validate_v1(self) -> None:
        if self.pitch_in is not None:
            raise ValueError(
                f"{self.coding_id}: v1 codings derive pitch from cell_dots")
        if self.cell_dots not in VALID_CELL_DOTS:
            raise ValueError(
                f"v1 supports cell_dots {VALID_CELL_DOTS}, "
                f"got {self.cell_dots}")
        if self.codec is None:
            if self.rate_id not in LADDER:
                raise ValueError(f"unknown rate {self.rate_id}")
            object.__setattr__(
                self, "codec", k_profile(self.rate_id, self.n_sites))
        else:
            if self.rate_id is not None:
                raise ValueError(
                    f"{self.coding_id}: non-K codec has no scalar rate_id")
            if self.codec.n_sites != self.n_sites:
                raise ValueError(
                    f"{self.coding_id}: codec has {self.codec.n_sites} "
                    f"sites but coding declares {self.n_sites}")

    def _validate_v2(self) -> None:
        if not isinstance(self.pitch_in, Fraction) or self.pitch_in <= 0:
            raise ValueError(
                f"{self.coding_id}: v2 codings carry an exact positive "
                f"rational pitch")
        if self.codec is None:
            raise ValueError(
                f"{self.coding_id}: v2 codings are minted through a "
                f"family constructor")
        dots600 = self.pitch_in * 600
        expected_dots = int(dots600) if dots600.denominator == 1 else None
        if self.cell_dots != expected_dots:
            raise ValueError(
                f"{self.coding_id}: cell_dots {self.cell_dots} disagrees "
                f"with pitch {self.pitch_in} on the 600 grid")
        if self.codec.family is Family.K:
            if self.rate_id is None or self.rate_id not in LADDER:
                raise ValueError(
                    f"{self.coding_id}: v2 K coding needs its scalar rung")
            child = self.codec.streams[0].fec.children[0]
            if child.code_id != self.rate_id:
                raise ValueError(
                    f"{self.coding_id}: rate_id {self.rate_id} != codec "
                    f"rung {child.code_id}")
        elif self.rate_id is not None:
            raise ValueError(
                f"{self.coding_id}: non-K codec has no scalar rate_id")
        if self.codec.n_sites != self.n_sites:
            raise ValueError(
                f"{self.coding_id}: codec has {self.codec.n_sites} sites "
                f"but coding declares {self.n_sites}")
        if self.pooled_fountain != (self.codec.family is Family.CMY8):
            raise ValueError(
                f"{self.coding_id}: v2 pooling is a family fact "
                f"(cmy8 = pooled, others not)")

    @property
    def n_sites(self) -> int:
        return pilots.N_WORD_SITES + self.n_filler

    @property
    def pitch(self) -> Fraction:
        """Exact physical cell pitch in inches."""
        if self.pitch_in is not None:
            return self.pitch_in
        assert self.cell_dots is not None
        return Fraction(self.cell_dots, 600)

    @property
    def codec_family(self) -> Family:
        assert self.codec is not None
        return self.codec.family

    @property
    def pilot_density(self) -> float:
        return self.n_sites / 4096.0

    @property
    def tile_user_bits(self) -> int:
        """The one per-stream user width (including the metadata bit)
        the v1 receiver reads tiles at.  Every row it decodes has one;
        a cmy8 triplet whose rungs differ has more than one, and the
        property raises — that receiver does not decode column-group
        rows (docs/CMY8-COLUMN-GROUPS.md §9, ruling 7).
        """
        assert self.codec is not None
        return self.codec.common_user_bits

    @property
    def payload_bits_per_tile(self) -> int:
        """The fountain-symbol width — the widest stream's; a narrower
        stream's tile carries column groups of it (profiles.symbol_bits).
        """
        assert self.codec is not None
        return self.codec.symbol_bits

    @property
    def ldpc_parity_bits(self) -> int:
        """Aggregate mother-code parity bits across the row's FEC banks.

        For K this is the established scalar value.  Color callers should
        normally inspect the ordered stream/child profiles directly.
        """
        assert self.codec is not None
        return sum(
            LADDER[child.code_id].m_bits
            for stream in self.codec.streams
            for child in stream.fec.children
        )

    @property
    def codec_id(self) -> str:
        assert self.codec is not None
        return self.codec.codec_id

    @property
    def stream_profiles(self) -> tuple[StreamProfile, ...]:
        assert self.codec is not None
        return self.codec.streams

    @property
    def stream_ids(self) -> tuple[str, ...]:
        assert self.codec is not None
        return self.codec.stream_ids

    @property
    def stream_symbol_bits(self) -> tuple[int, ...]:
        """Ordered fountain-symbol widths, one per logical stream."""
        return tuple(stream.symbol_bits for stream in self.stream_profiles)

    @property
    def aggregate_symbol_bits(self) -> int:
        """Envelope bits per source-symbol index across all streams:
        ``n_streams`` symbols of the one symbol width (the sum of the
        stream widths whenever they are equal; a column-group row's
        narrower streams carry less than this per tile, and its
        envelope is still ``k_total`` symbols of the full width —
        docs/CMY8-COLUMN-GROUPS.md §3.4)."""
        return self.n_streams * self.payload_bits_per_tile

    @property
    def n_dust(self) -> int:
        assert self.codec is not None
        return self.codec.n_dust

    @property
    def payload_cells(self) -> int:
        assert self.codec is not None
        return self.codec.payload_cells

    @property
    def rate_ids(self) -> tuple[tuple[str, ...], ...]:
        """Ordered mother-code IDs, grouped by logical stream."""
        return tuple(
            tuple(child.code_id for child in stream.fec.children)
            for stream in self.stream_profiles
        )

    @property
    def n_streams(self) -> int:
        assert self.codec is not None
        return len(self.codec.streams)

    @property
    def family_seed(self) -> bytes:
        return f"holo/v1/sites/p{self.n_sites}".encode()


def _build_codings(*codings: Coding) -> Mapping[str, Coding]:
    out: dict[str, Coding] = {}
    for c in codings:
        if c.coding_id in out:
            raise ValueError(f"duplicate coding id {c.coding_id!r}")
        out[c.coding_id] = c
    return MappingProxyType(out)


# The CLOSED legacy catalog: the nine v1 rows the printed record and the
# golden suite pin.  New codings are minted in the v2 lattice; the three
# branch-era v1 codings (c4-r0550, the -x1 rows) resolve through the
# fossil catalogue, never through this table.
CODINGS: Mapping[str, Coding] = _build_codings(
    Coding("c3-r0550", cell_dots=3, rate_id="r0550"),
    Coding("c2-r0550", cell_dots=2, rate_id="r0550"),
    Coding("c2-r0700", cell_dots=2, rate_id="r0700"),
    Coding(
        "c2-cmy7-p120-v0", cell_dots=2, rate_id=None, n_filler=20,
        codec=_CMY7_P120_V0),
    Coding(
        "c3-cmy7-p120-v0", cell_dots=3, rate_id=None, n_filler=20,
        codec=_CMY7_P120_V0),
    Coding(
        "c2-cmy8-p120-v0", cell_dots=2, rate_id=None, n_filler=20,
        codec=_CMY8_P120_V0),
    Coding(
        "c3-cmy8-p120-v0", cell_dots=3, rate_id=None, n_filler=20,
        codec=_CMY8_P120_V0),
    # Pooled-fountain CMY8 (docs/CMY8-POOLED-FOUNTAIN.md; adopted
    # 2026-08-13): identical tile codec, pooled outer code + per-stream
    # metadata equations.  Append-only; the printed -v0 sheets (e030/e032)
    # stay on their rows forever.
    Coding(
        "c2-cmy8-p120-v1", cell_dots=2, rate_id=None, n_filler=20,
        codec=_CMY8_P120_V0, pooled_fountain=True),
    Coding(
        "c3-cmy8-p120-v1", cell_dots=3, rate_id=None, n_filler=20,
        codec=_CMY8_P120_V0, pooled_fountain=True),
)


def get_coding(coding_id: str) -> Coding:
    try:
        return CODINGS[coding_id]
    except KeyError:
        raise KeyError(f"unknown coding {coding_id!r}; "
                       f"known: {sorted(CODINGS)}") from None


@dataclass(frozen=True)
class FormatSpec:
    """One printed format: coding x geometry.

    Exactly one geometry source, matching the coding's namespace:

    - v1: media minus per-edge margin (the legacy derivation).
    - v2: the tile matrix directly (FORMAT-SPACE §7); media, margins and
      placement are emission-side presentation, not identity.
    """

    coding: Coding
    media_id: str | None = None
    media_mm: tuple[float, float] | None = None
    margin_mm: float | None = None
    plane: int = pilots.PLANE_K
    tiles_yx: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        media_given = (self.media_id is not None
                       or self.media_mm is not None
                       or self.margin_mm is not None)
        if self.coding.namespace == "v1":
            if self.tiles_yx is not None or not media_given:
                raise ValueError(
                    f"{self.coding.coding_id}: v1 geometry derives from "
                    f"media x margin")
            if (self.media_id is None or self.media_mm is None
                    or self.margin_mm is None):
                raise ValueError(
                    f"{self.coding.coding_id}: v1 needs media_id, "
                    f"media_mm and margin_mm")
        else:
            if media_given or self.tiles_yx is None:
                raise ValueError(
                    f"{self.coding.coding_id}: v2 identity is the tile "
                    f"matrix; media/margins are emission facts")
            ty, tx = self.tiles_yx
            if ty < 1 or tx < 1:
                raise ValueError(f"tile matrix {self.tiles_yx} invalid")
            if ty * tx > layout_mod.MAX_TILES:
                raise ValueError(
                    f"tile matrix {self.tiles_yx} exceeds the "
                    f"{layout_mod.COUNTER_BITS}-bit counter space")

    @cached_property
    def layout(self) -> FieldLayout:
        if self.coding.namespace == "v1":
            assert self.media_mm is not None and self.margin_mm is not None
            assert self.coding.cell_dots is not None
            return derive_field(media_mm=self.media_mm,
                                margin_mm=self.margin_mm,
                                cell_dots=self.coding.cell_dots)
        if self.coding.cell_dots is None:
            raise ValueError(
                f"{self.spec_id}: pitch {self.coding.pitch} is off the "
                f"600 grid — raster/receive support for off-600 pitches "
                f"is pending (identity and planning stay valid)")
        assert self.tiles_yx is not None
        ty, tx = self.tiles_yx
        cells = (ty * TILE_CELLS, tx * TILE_CELLS)
        dots = (cells[0] * self.coding.cell_dots,
                cells[1] * self.coding.cell_dots)
        return FieldLayout(
            cell_dots=self.coding.cell_dots,
            cells_yx=cells,
            tiles_yx=(ty, tx),
            origin_dots_yx=(0, 0),
            field_dots_yx=dots,
            page_dots_xy=(dots[1], dots[0]),
            border_top_mm=0.0,
            border_bottom_mm=0.0,
            border_left_mm=0.0,
            border_right_mm=0.0,
            tile_pitch_mm=float(
                TILE_CELLS * self.coding.pitch * Fraction(254, 10)),
        )

    @property
    def _tiles_yx(self) -> tuple[int, int]:
        if self.tiles_yx is not None:
            return self.tiles_yx
        return self.layout.tiles_yx

    @property
    def cells_yx(self) -> tuple[int, int]:
        if self.tiles_yx is not None:
            ty, tx = self.tiles_yx
            return ty * TILE_CELLS, tx * TILE_CELLS
        return self.layout.cells_yx

    @property
    def spec_id(self) -> str:
        if self.coding.namespace == "v2":
            ty, tx = self._tiles_yx
            return f"{self.coding.coding_id}@{ty}x{tx}"
        y, x = self.layout.cells_yx
        return f"{self.coding.coding_id}@{y}x{x}"

    @property
    def display_id(self) -> str:
        short = self.coding.display_coding_id
        if self.coding.namespace != "v2" or short is None:
            return self.spec_id
        ty, tx = self._tiles_yx
        return f"{short}@{ty}x{tx}"

    @property
    def seed(self) -> bytes:
        if self.coding.namespace == "v2":
            return V2_SEED_NAMESPACE + self.spec_id.encode()
        y, x = self.layout.cells_yx
        return f"holo/v1/{self.coding.coding_id}/{y}x{x}".encode()

    @property
    def family_seed(self) -> bytes:
        return self.coding.family_seed

    # coding pass-throughs (the names call sites actually use)
    @property
    def cell_dots(self) -> int:
        dots = self.coding.cell_dots
        if dots is None:
            raise ValueError(
                f"{self.spec_id}: pitch {self.coding.pitch} is off the "
                f"600 grid — dot-grid consumers pending")
        return dots

    @property
    def pitch(self) -> Fraction:
        return self.coding.pitch

    @property
    def codec_family(self) -> Family:
        return self.coding.codec_family

    @property
    def rate_id(self) -> str | None:
        return self.coding.rate_id

    @property
    def rate_ids(self) -> tuple[tuple[str, ...], ...]:
        return self.coding.rate_ids

    @property
    def n_filler(self) -> int:
        return self.coding.n_filler

    @property
    def n_sites(self) -> int:
        return self.coding.n_sites

    @property
    def n_dust(self) -> int:
        return self.coding.n_dust

    @property
    def codec(self) -> CodecProfile:
        assert self.coding.codec is not None
        return self.coding.codec

    @property
    def codec_id(self) -> str:
        return self.coding.codec_id

    @property
    def stream_profiles(self) -> tuple[StreamProfile, ...]:
        return self.coding.stream_profiles

    def stream_profile(self, stream_id: str) -> StreamProfile:
        """The one declared profile for ``stream_id`` (or ValueError)."""
        matches = tuple(
            profile for profile in self.stream_profiles
            if profile.stream_id == stream_id
        )
        if len(matches) != 1:
            raise ValueError(
                f"stream {stream_id!r} is not declared by {self.spec_id}")
        return matches[0]

    @property
    def stream_ids(self) -> tuple[str, ...]:
        return self.coding.stream_ids

    @property
    def stream_symbol_bits(self) -> tuple[int, ...]:
        return self.coding.stream_symbol_bits

    @property
    def aggregate_symbol_bits(self) -> int:
        return self.coding.aggregate_symbol_bits

    @cached_property
    def column_groups(self) -> ColumnGroups:
        """How the row's streams share its one symbol width: one group
        at equal widths, the ruled column groups otherwise
        (docs/CMY8-COLUMN-GROUPS.md)."""
        return column_groups(self.stream_symbol_bits)

    @property
    def pooled_fountain(self) -> bool:
        return self.coding.pooled_fountain

    @property
    def n_streams(self) -> int:
        return self.coding.n_streams

    @property
    def payload_cells(self) -> int:
        return self.coding.payload_cells

    @property
    def n_transmitted_slots(self) -> int:
        return 4096 - self.coding.n_sites

    @property
    def tile_user_bits(self) -> int:
        return self.coding.tile_user_bits

    @property
    def symbol_bits(self) -> int:
        return self.coding.payload_bits_per_tile

    @property
    def tiles_per_page(self) -> int:
        ty, tx = self._tiles_yx
        return ty * tx

    @property
    def max_tiles_addressable(self) -> int:
        return 1 << pilots.COUNTER_BITS

    @property
    def max_pages(self) -> int:
        return self.max_tiles_addressable // self.tiles_per_page

    def tile_counter(self, page: int, ty: int, tx: int) -> int:
        return layout_mod.tile_counter(page, ty, tx, self._tiles_yx)

    def tile_address(self, counter: int) -> tuple[int, int, int]:
        return layout_mod.tile_address(counter, self._tiles_yx)
