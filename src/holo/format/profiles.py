"""Immutable numerical profiles for the K, CMY7, CMY8 and CMY tile codecs.

This module is deliberately small.  A format row selects one profile; the
profile states the codec family, physical alphabet, durable evidence
width, logical streams, dust law, and exact shortened LDPC bank for each
stream.  It does not contain generator or receiver policy.

FORMAT-SPACE P1: the codec FAMILY is a first-class enum carried by every
profile — the only dispatch key production code may use (identity
comparison against profile objects and codec-id string matching are
retired).  The frozen v1 singletons are module-private; the public way to
mint a profile is a family constructor in ``families.py``.  The dust base
cycle is a codec fact, not a dispatch branch.

``fountain_aux=None`` means the established K domains 7/8.  Color streams
use the frozen auxiliaries of domains 14/15.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from functools import lru_cache

from ..core import channel, keystream
from ..core.ldpc.frame import FecBankProfile, FecChildProfile

TILE_CELLS = 64 * 64
WORD_SITES = 100
METADATA_BITS = 1


class Family(str, enum.Enum):
    """The closed set of codec families (FORMAT-SPACE §5).

    The string values are format-frozen: they are the evidence-block
    kinds of the durable record (``receive/evidence_blocks.py``).
    """

    K = "k"
    CMY7 = "cmy7"
    CMY8 = "cmy8"
    CMY = "cmy"


@dataclass(frozen=True)
class StreamProfile:
    """One logical fountain/certificate stream within a physical tile."""

    stream_id: str
    fec: FecBankProfile
    fountain_aux: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.stream_id, str) or not self.stream_id:
            raise ValueError("stream_id must be a non-empty string")
        if self.fountain_aux is not None:
            expected = keystream.COLOR_STREAM_AUX.get(self.stream_id)
            if expected is None or self.fountain_aux != expected:
                raise ValueError(
                    f"{self.stream_id}: fountain_aux must be {expected}")
        if self.fec.user_bits <= METADATA_BITS:
            raise ValueError(
                f"{self.stream_id}: FEC user frame cannot hold metadata "
                "and a symbol")

    @property
    def user_bits(self) -> int:
        """CRC-protected bits: one metadata bit plus fountain symbol."""
        return self.fec.user_bits

    @property
    def symbol_bits(self) -> int:
        return self.user_bits - METADATA_BITS


@dataclass(frozen=True)
class CodecProfile:
    """The immutable format facts selected by a :class:`Coding`."""

    codec_id: str
    state_names: tuple[str, ...]
    word_states: tuple[int, int]
    n_sites: int
    n_dust: int
    evidence_values_per_cell: int
    bits_per_mapper_unit: int
    cells_per_mapper_unit: int
    streams: tuple[StreamProfile, ...]
    family: Family
    dust_base_cycle: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.codec_id, str) or not self.codec_id:
            raise ValueError("codec_id must be a non-empty string")
        if not isinstance(self.family, Family):
            raise ValueError(f"{self.codec_id}: family must be a Family")
        object.__setattr__(self, "state_names", tuple(self.state_names))
        object.__setattr__(self, "streams", tuple(self.streams))
        object.__setattr__(
            self, "dust_base_cycle", tuple(self.dust_base_cycle))
        if not 0 < len(self.state_names) <= len(channel.STATE_NAMES):
            raise ValueError(f"{self.codec_id}: invalid physical alphabet")
        expected_states = (
            ("W", "K") if self.family is Family.K
            else tuple(name for name in channel.STATE_NAMES
                       if name in self.state_names)
        )
        if self.state_names != expected_states:
            raise ValueError(
                f"{self.codec_id}: non-canonical physical alphabet")
        if self.word_states[0] not in self.state_ids \
                or self.word_states[1] not in self.state_ids:
            raise ValueError(f"{self.codec_id}: word states outside alphabet")
        if self.word_states[0] == self.word_states[1]:
            raise ValueError(f"{self.codec_id}: binary word states must differ")
        if not WORD_SITES <= self.n_sites < TILE_CELLS:
            raise ValueError(f"{self.codec_id}: invalid furniture count")
        if not 0 <= self.n_dust <= self.n_sites - WORD_SITES:
            raise ValueError(f"{self.codec_id}: invalid dust count")
        if self.n_dust > 0 and not self.dust_base_cycle \
                and self.family is not Family.CMY:
            raise ValueError(
                f"{self.codec_id}: dust sites need a dust base cycle")
        if any(state not in self.state_ids
               for state in self.dust_base_cycle):
            raise ValueError(f"{self.codec_id}: dust states outside alphabet")
        if self.family is Family.CMY and self.dust_base_cycle:
            raise ValueError(
                f"{self.codec_id}: cmy dust is the balance law, not a cycle")
        if self.evidence_values_per_cell < 1:
            raise ValueError(f"{self.codec_id}: invalid evidence width")
        if self.bits_per_mapper_unit < 1 or self.cells_per_mapper_unit < 1:
            raise ValueError(f"{self.codec_id}: invalid mapper dimensions")
        if not self.streams:
            raise ValueError(f"{self.codec_id}: at least one stream required")
        stream_ids = tuple(stream.stream_id for stream in self.streams)
        if len(set(stream_ids)) != len(stream_ids):
            raise ValueError(f"{self.codec_id}: duplicate stream IDs")

    @property
    def state_ids(self) -> tuple[int, ...]:
        """The alphabet's state ids: K's (0, 1), else presence ids."""
        if self.family is Family.K:
            return (0, 1)
        return tuple(channel.STATE_NAMES.index(name)
                     for name in self.state_names)

    @property
    def payload_cells(self) -> int:
        return TILE_CELLS - self.n_sites

    @property
    def stream_ids(self) -> tuple[str, ...]:
        return tuple(stream.stream_id for stream in self.streams)

    @property
    def common_user_bits(self) -> int:
        values = {stream.user_bits for stream in self.streams}
        if len(values) != 1:
            raise ValueError(f"{self.codec_id}: stream user widths differ")
        return next(iter(values))

    @property
    def common_symbol_bits(self) -> int:
        return self.common_user_bits - METADATA_BITS

    @property
    def symbol_bits(self) -> int:
        """The row's one fountain-symbol width: the widest stream's.

        Equal-width streams (every K, cmy7 and -v0 row, every uniform
        cmy8 triplet) share it outright; a cmy8 triplet whose rungs
        differ carries it as column groups, the narrower streams holding
        fewer groups per tile (docs/CMY8-COLUMN-GROUPS.md).
        """
        return max(stream.symbol_bits for stream in self.streams)


def _bank(profile_id: str, *children: tuple[str, int]) -> FecBankProfile:
    return FecBankProfile(
        profile_id,
        tuple(FecChildProfile(rate_id, shortened)
              for rate_id, shortened in children),
    )


@lru_cache(maxsize=None)
def k_profile(rate_id: str, n_sites: int) -> CodecProfile:
    """One exact K leaf profile; the established implementation stays put."""
    stream = StreamProfile(
        "main",
        _bank(f"k-{rate_id}-p{n_sites}-v1", (rate_id, n_sites)),
        None,
    )
    profile = CodecProfile(
        codec_id="k-v1",
        state_names=("W", "K"),
        word_states=(0, 1),
        n_sites=n_sites,
        n_dust=0,
        evidence_values_per_cell=1,
        bits_per_mapper_unit=1,
        cells_per_mapper_unit=1,
        streams=(stream,),
        family=Family.K,
        dust_base_cycle=(),
    )
    if stream.fec.transmitted_bits != profile.payload_cells:
        raise ValueError(f"{profile.codec_id}: K transmitted-cell mismatch")
    return profile


# Dust base CYCLES (canonical missing-state order).  The frozen v1 dust
# law tiles a cycle across the dust sites — full cycles plus, for CMY8,
# two address-keyed extras — before the domain-9 permutation; the cycle
# is a codec fact consumed by pilots.dust_state_values.
_CMY7_DUST_CYCLE: tuple[int, ...] = (
    int(channel.CMYState.C),
    int(channel.CMYState.M),
    int(channel.CMYState.Y),
    int(channel.CMYState.CY),
    int(channel.CMYState.MY),
)

_CMY8_DUST_CYCLE: tuple[int, ...] = (
    int(channel.CMYState.C),
    int(channel.CMYState.M),
    int(channel.CMYState.Y),
    int(channel.CMYState.CY),
    int(channel.CMYState.MY),
    int(channel.CMYState.CMY),
)

_CMY7_FEC = _bank(
    "cmy7-p120-v0",
    ("r0550", 0),
    ("r0625", 677),
    ("r0625", 677),
)

_CMY7_P120_V0 = CodecProfile(
    codec_id="cmy7-pack7-p120-v0",
    state_names=channel.CMY7_STATE_NAMES,
    word_states=(int(channel.CMYState.W), int(channel.CMYState.CM)),
    n_sites=120,
    n_dust=20,
    evidence_values_per_cell=6,
    bits_per_mapper_unit=11,
    cells_per_mapper_unit=4,
    streams=(
        StreamProfile(
            "main", _CMY7_FEC, keystream.COLOR_STREAM_MAIN),
    ),
    family=Family.CMY7,
    dust_base_cycle=_CMY7_DUST_CYCLE,
)

_CMY8_STREAMS = (
    StreamProfile(
        "C",
        _bank("cmy8-C-p120-v0", ("r0550", 120)),
        keystream.COLOR_STREAM_C,
    ),
    StreamProfile(
        "M",
        _bank("cmy8-M-p120-v0", ("r0550", 120)),
        keystream.COLOR_STREAM_M,
    ),
    StreamProfile(
        "Y",
        _bank("cmy8-Y-p120-v0", ("r0547", 120)),
        keystream.COLOR_STREAM_Y,
    ),
)

_CMY8_P120_V0 = CodecProfile(
    codec_id="cmy8-presence-p120-v0",
    state_names=channel.STATE_NAMES,
    word_states=(int(channel.CMYState.W), int(channel.CMYState.CM)),
    n_sites=120,
    n_dust=20,
    evidence_values_per_cell=3,
    bits_per_mapper_unit=3,
    cells_per_mapper_unit=1,
    streams=_CMY8_STREAMS,
    family=Family.CMY8,
    dust_base_cycle=_CMY8_DUST_CYCLE,
)

# The frozen 20-site dust base multisets of the v1 record, retained as
# cross-checks that the cycle law reproduces them bit-exactly.
_CMY7_DUST_BASE_STATES: tuple[int, ...] = _CMY7_DUST_CYCLE * 4
_CMY8_DUST_BASE_STATES: tuple[int, ...] = _CMY8_DUST_CYCLE


def _validate_frozen_profiles() -> None:
    if _CMY7_P120_V0.payload_cells != 3976:
        raise AssertionError("CMY7 p120 payload-cell arithmetic changed")
    if _CMY7_P120_V0.payload_cells % _CMY7_P120_V0.cells_per_mapper_unit:
        raise AssertionError("CMY7 p120 must contain complete four-cell packs")
    packs = (
        _CMY7_P120_V0.payload_cells
        // _CMY7_P120_V0.cells_per_mapper_unit
    )
    if packs != 994 or packs * _CMY7_P120_V0.bits_per_mapper_unit != 10934:
        raise AssertionError("CMY7 pack7 arithmetic changed")
    if _CMY7_FEC.transmitted_bits != 10934:
        raise AssertionError("CMY7 FEC bank does not fill pack7 input")
    if tuple(child.active_information_bits
             for child in _CMY7_FEC.children) != (2240, 1883, 1883):
        raise AssertionError("CMY7 active-information tuple changed")
    if _CMY7_FEC.user_bits != 5974 \
            or _CMY7_P120_V0.common_symbol_bits != 5973:
        raise AssertionError("CMY7 frame arithmetic changed")

    if _CMY8_P120_V0.payload_cells != 3976:
        raise AssertionError("CMY8 p120 payload-cell arithmetic changed")
    expected_codes = ("r0550", "r0550", "r0547")
    expected_aux = (
        keystream.COLOR_STREAM_C,
        keystream.COLOR_STREAM_M,
        keystream.COLOR_STREAM_Y,
    )
    if _CMY8_P120_V0.stream_ids != channel.PLANE_ORDER:
        raise AssertionError("CMY8 stream order differs from plane order")
    if tuple(keystream.COLOR_STREAM_AUX[stream_id]
             for stream_id in channel.PLANE_ORDER) != expected_aux:
        raise AssertionError("CMY8 auxiliary order differs from plane order")
    if tuple(stream.fec.children[0].code_id
             for stream in _CMY8_STREAMS) != expected_codes:
        raise AssertionError("CMY8 FEC tuple changed")
    if tuple(stream.fec.children[0].shortened_info_tail
             for stream in _CMY8_STREAMS) != (120, 120, 120):
        raise AssertionError("CMY8 shortening tuple changed")
    if tuple(stream.fountain_aux for stream in _CMY8_STREAMS) != expected_aux:
        raise AssertionError("CMY8 stream-domain tuple changed")
    if any(stream.fec.transmitted_bits != 3976
           or stream.user_bits != 2088
           or stream.symbol_bits != 2087
           for stream in _CMY8_STREAMS):
        raise AssertionError("CMY8 frame arithmetic changed")

    if _CMY7_P120_V0.family is not Family.CMY7 \
            or _CMY8_P120_V0.family is not Family.CMY8 \
            or k_profile("r0550", 100).family is not Family.K:
        raise AssertionError("frozen profile family tags changed")
    if _CMY7_DUST_CYCLE * 4 != _CMY7_DUST_BASE_STATES \
            or len(_CMY7_DUST_BASE_STATES) != 20:
        raise AssertionError("CMY7 dust quota changed")
    if _CMY8_DUST_CYCLE != _CMY8_DUST_BASE_STATES \
            or len(_CMY8_DUST_BASE_STATES) != 6:
        raise AssertionError("CMY8 dust base changed")


_validate_frozen_profiles()


__all__ = [
    "CodecProfile",
    "Family",
    "METADATA_BITS",
    "StreamProfile",
    "TILE_CELLS",
    "WORD_SITES",
    "k_profile",
]
