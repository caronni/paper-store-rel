"""Family constructors — the public way to mint tile-codec profiles.

FORMAT-SPACE §5.  Each family is a *function* from parameters to an
immutable :class:`~holo.format.profiles.CodecProfile` carrying its
:class:`~holo.format.profiles.Family` tag.  Derived names (codec ids,
FEC bank ids) follow the v2 grammar mechanically; the frozen v1
singletons keep their frozen names inside ``profiles.py`` and are not
reachable from here.

Numerical law shared by K, CMY8 and CMY (all LDPC mothers are n=4096):
shortening equals the site count p, so transmitted bits = 4096 − p =
payload cells per stream, and user bits = k_bits(rung) − p − CRC32.

Gen-v1 constraints stated where the frozen algebra imposes them:

- cmy7: the pack7 FEC is a joint baked bank — rungs and sites are fixed
  per generation (v1: p120, the frozen v0-numerics bank under its v1
  name).
- cmy8: any rung triplet.  The pooled fountain has ONE symbol width —
  the widest stream's — and a narrower stream carries column groups of
  it (docs/CMY8-COLUMN-GROUPS.md, ruling 2026-09-04: gen-v1 semantics;
  equal-width triplets are the one-group case, bit-identical to the
  frozen pool).
- cmy: any rung pair (hi, lo), pooled exactly as cmy8 (docs/CMY-DESIGN.md).
"""
from __future__ import annotations

from functools import lru_cache

from ..core import channel, keystream
from ..core.ldpc.construct import LADDER
from .profiles import (
    CodecProfile,
    Family,
    StreamProfile,
    WORD_SITES,
    _bank,
    _CMY7_DUST_CYCLE,
    _CMY7_FEC,
    _CMY8_DUST_CYCLE,
    k_profile,
)


def _require_rung(rung: str) -> None:
    if rung not in LADDER:
        raise ValueError(
            f"unknown LDPC rung {rung!r}; ladder: {sorted(LADDER)}")


def _require_sites(p: int, family: Family) -> None:
    if p < WORD_SITES:
        raise ValueError(
            f"{family.value}: p{p} is below the {WORD_SITES}-site word "
            f"floor (p<100 is reserved, FORMAT-SPACE §2)")


def rung_token(rungs: tuple[str, ...]) -> str:
    """The grammar's rung token: contracted when uniform (canonical)."""
    if not rungs:
        raise ValueError("empty rung tuple")
    if len(set(rungs)) == 1:
        return rungs[0]
    return "r" + "x".join(r.removeprefix("r") for r in rungs)


@lru_cache(maxsize=None)
def k_codec(rung: str, p: int = 100) -> CodecProfile:
    """K family: 1 stream, W/K alphabet, no dust; sites free >= 100.

    Numerically the established K path (``k_profile``); the minted bank
    id ``k-{rung}-p{p}-v1`` coincides with the frozen legacy form for
    identical parameters — same mathematical object, same name.
    """
    _require_rung(rung)
    _require_sites(p, Family.K)
    return k_profile(rung, p)


@lru_cache(maxsize=None)
def cmy7_codec(p: int = 120, gen: int = 1) -> CodecProfile:
    """CMY7 family: 1 stream, 7-state pack7; rungs/sites baked per gen."""
    if gen != 1:
        raise ValueError(f"cmy7 generation v{gen} is not defined")
    if p != 120:
        raise ValueError(
            "cmy7 v1 bakes its joint pack7 bank at p120; other site "
            "counts need a new generation (FORMAT-SPACE §5)")
    return CodecProfile(
        codec_id="cmy7-p120-v1",
        state_names=channel.CMY7_STATE_NAMES,
        word_states=(int(channel.CMYState.W), int(channel.CMYState.CM)),
        n_sites=120,
        n_dust=20,
        evidence_values_per_cell=6,
        bits_per_mapper_unit=11,
        cells_per_mapper_unit=4,
        streams=(
            StreamProfile(
                "main",
                _bank("cmy7-p120-v1",
                      *((child.code_id, child.shortened_info_tail)
                        for child in _CMY7_FEC.children)),
                keystream.COLOR_STREAM_MAIN),
        ),
        family=Family.CMY7,
        dust_base_cycle=_CMY7_DUST_CYCLE,
    )


@lru_cache(maxsize=None)
def cmy8_codec(rungs: tuple[str, str, str], p: int = 120,
               *,
               _codec_id: str | None = None,
               _bank_ids: tuple[str, str, str] | None = None,
               ) -> CodecProfile:
    """CMY8 family: three independent per-plane streams, pooled outer code.

    ``rungs`` is the (r_C, r_M, r_Y) triplet, uneven or not: the pool's
    symbol width is the widest plane's and a narrower plane carries
    column groups of it (``core.column_groups.column_groups``).  The private
    ``_codec_id``/``_bank_ids`` overrides exist solely for fossil
    resolution (frozen ``-x1`` names); production mints grammar names.
    """
    if len(rungs) != 3:
        raise ValueError("cmy8 takes a (r_C, r_M, r_Y) rung triplet")
    for rung in rungs:
        _require_rung(rung)
    _require_sites(p, Family.CMY8)
    if p == WORD_SITES:
        # Colour furniture includes dust: the reference field, colour
        # anchoring and the dust value law all assume at least one dust
        # site.  A dust-free colour row would parse as lawful and then
        # die deep in emission/receive — refuse it at the constructor.
        raise ValueError(
            "cmy8 needs at least one dust site (p > 100): colour "
            "addressing and calibration consume the dust furniture")
    if _bank_ids is not None and (
            len(_bank_ids) != 3 or len(set(_bank_ids)) != 3):
        raise ValueError(
            "cmy8 _bank_ids override must name three distinct banks "
            "(C, M, Y)")
    token = rung_token(rungs)
    codec_id = _codec_id or f"cmy8-{token}-p{p}-v1"
    bank_ids = _bank_ids or tuple(
        f"cmy8-{plane}-{rung}-p{p}-v1"
        for plane, rung in zip(channel.PLANE_ORDER, rungs))
    aux = (keystream.COLOR_STREAM_C, keystream.COLOR_STREAM_M,
           keystream.COLOR_STREAM_Y)
    streams = tuple(
        StreamProfile(plane, _bank(bank_id, (rung, p)), stream_aux)
        for plane, rung, bank_id, stream_aux
        in zip(channel.PLANE_ORDER, rungs, bank_ids, aux))
    profile = CodecProfile(
        codec_id=codec_id,
        state_names=channel.STATE_NAMES,
        word_states=(int(channel.CMYState.W), int(channel.CMYState.CM)),
        n_sites=p,
        n_dust=p - WORD_SITES,
        evidence_values_per_cell=3,
        bits_per_mapper_unit=3,
        cells_per_mapper_unit=1,
        streams=streams,
        family=Family.CMY8,
        dust_base_cycle=_CMY8_DUST_CYCLE,
    )
    for stream in profile.streams:
        if stream.fec.transmitted_bits != profile.payload_cells:
            raise AssertionError(
                f"{codec_id}: plane transmitted-cell mismatch")
    return profile


@lru_cache(maxsize=None)
def cmy_codec(rungs: tuple[str, str], p: int = 120) -> CodecProfile:
    """CMY family: two label-bit streams over the {W, C, M, Y} alphabet.

    ``rungs`` is the (r_hi, r_lo) pair in stream order; an uneven pair
    pools through column groups as an uneven cmy8 triplet does.  A cell's
    two dithered bits pick its state through the frozen label table
    (``channel.cmy_label_states``); word '1' prints C, word '0' the site's
    keyed W or Y, the dust follows the per-tile balance law
    (``pilots.color_word_states`` / ``dust_state_values``).
    """
    if len(rungs) != 2:
        raise ValueError("cmy takes a (r_hi, r_lo) rung pair")
    for rung in rungs:
        _require_rung(rung)
    _require_sites(p, Family.CMY)
    if p == WORD_SITES:
        raise ValueError(
            "cmy needs at least one dust site (p > 100): word '1' is C "
            "and word '0' W or Y, so M appears only in dust and p100 "
            "leaves the M plane no anchor")
    token = rung_token(rungs)
    streams = tuple(
        StreamProfile(stream_id, _bank(f"cmy-{stream_id}-{rung}-p{p}-v1",
                                       (rung, p)), None)
        for stream_id, rung in zip(channel.CMY_LABEL_STREAMS, rungs))
    profile = CodecProfile(
        codec_id=f"cmy-{token}-p{p}-v1",
        state_names=("W", "C", "M", "Y"),
        word_states=(int(channel.CMYState.W), int(channel.CMYState.C)),
        n_sites=p,
        n_dust=p - WORD_SITES,
        evidence_values_per_cell=3,
        bits_per_mapper_unit=2,
        cells_per_mapper_unit=1,
        streams=streams,
        family=Family.CMY,
        dust_base_cycle=(),
    )
    for stream in profile.streams:
        if stream.fec.transmitted_bits != profile.payload_cells:
            raise AssertionError(
                f"{profile.codec_id}: stream transmitted-cell mismatch")
    return profile


__all__ = [
    "cmy_codec",
    "cmy7_codec",
    "cmy8_codec",
    "k_codec",
    "rung_token",
]
