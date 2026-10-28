"""The v2 identity grammar: parse/mint format ids over the coding lattice.

FORMAT-SPACE §6/§16.  A canonical format id fully describes a printed
format and IS the AES row-seed payload under the ``holo/v2/`` namespace:

  format-id  = coding-id "@" tiles_y "x" tiles_x
  coding-id  = pitch "-" family [ "-" rungs ] "-p" sites "-v" gen

  pitch      = reduced rational "NiD" (n/d inch).  Class names (c1..c4)
               are input/display sugar, never canonical.
  family     = "k" | "cmy7" | "cmy8"
  rungs      = k: required single rung; cmy8: required, uniform
               shorthand "r0700" or mixed "r0700x0700x0550" (C,M,Y
               order); cmy7: forbidden (baked per generation)
  sites      = always spelled canonically; omitted on input fills the
               frozen defaults k -> p100, cmy7/cmy8 -> p120
  gen        = always spelled canonically; omitted on input fills the
               frozen default v1

The canonical string is fully explicit and reads no mutable table.
The short spelling is ``display_id``: class names, defaults omitted,
uniform triplets contracted.  The parser accepts either; every
serialization point stores canonical form only.

Public doors: ``parse_format_id`` (string) and ``mint`` / ``make_format``
(parameters).  The seed is ``FormatSpec.seed``; there is no ``str ->
bytes`` seeder.  Fossils never pass through this parser — they are
matched byte-exactly in ``fossils.py`` (L: prefix, FORMAT-SPACE §8).
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from types import MappingProxyType

from .descriptor import Coding, FormatSpec
from .families import cmy7_codec, cmy8_codec, k_codec, rung_token
from .layout import MAX_TILES, TILE_CELLS
from .profiles import Family

SEED_NAMESPACE = b"holo/v2/"

#: Frozen registered pitch classes: names for exact rationals of an
#: inch.  Append-only; numbers are never reinterpreted (FORMAT-SPACE §4).
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
_RUNG_RE = re.compile(r"^r[0-9]{4}$")
_RUNGS_TOKEN_RE = re.compile(r"^r[0-9]{4}(?:x[0-9]{4})*$")
_SITES_RE = re.compile(r"^p([0-9]+)$")
_GEN_RE = re.compile(r"^v([0-9]+)$")
_TILES_RE = re.compile(r"^([0-9]+)x([0-9]+)$")

_DEFAULT_SITES = {Family.K: 100, Family.CMY7: 120, Family.CMY8: 120}
_DEFAULT_GEN = 1
_DEFINED_GENS: tuple[int, ...] = (1,)
assert _DEFAULT_GEN in _DEFINED_GENS


def parse_pitch(token: str) -> Fraction:
    """A pitch token -> its exact rational of an inch."""
    if _PITCH_CLASS_RE.match(token):
        pitch = PITCH_CLASSES.get(token)
        if pitch is None:
            raise ValueError(
                f"unregistered pitch class {token!r}; registered: "
                f"{sorted(PITCH_CLASSES)}")
        return pitch
    m = _PITCH_RATIONAL_RE.match(token)
    if m:
        n, d = int(m.group(1)), int(m.group(2))
        if n < 1 or d < 1:
            raise ValueError(f"pitch {token!r} must be a positive rational")
        return Fraction(n, d)
    raise ValueError(
        f"pitch token {token!r} is neither a registered class nor NiD")


def canonical_pitch_token(pitch: Fraction) -> str:
    """The CANONICAL token: always the reduced rational, never a class.

    A class registry is append-only, so preferring a registered name here
    would let an append re-spell an already-minted identity — and the
    canonical string IS the AES row seed (FORMAT-SPACE §16).
    """
    if pitch <= 0:
        raise ValueError("pitch must be positive")
    return f"{pitch.numerator}i{pitch.denominator}"


def display_pitch_token(pitch: Fraction) -> str:
    """The token a person sees: class name where registered."""
    if pitch <= 0:
        raise ValueError("pitch must be positive")
    name = _CLASS_BY_PITCH.get(pitch)
    if name is not None:
        return name
    return canonical_pitch_token(pitch)


@dataclass(frozen=True)
class CodingParams:
    """One point of the coding lattice (identity axes only)."""

    pitch: Fraction
    family: Family
    rungs: tuple[str, ...]
    sites: int
    gen: int

    def __post_init__(self) -> None:
        if self.pitch <= 0:
            raise ValueError("pitch must be positive")
        expected_arity = {Family.K: 1, Family.CMY7: 0, Family.CMY8: 3}
        if len(self.rungs) != expected_arity[self.family]:
            raise ValueError(
                f"{self.family.value}: rung arity must be "
                f"{expected_arity[self.family]}, got {self.rungs}")


def canonical_coding_id(params: CodingParams) -> str:
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
    """Parse (normalizing) a v2 coding id.  Never accepts fossil ids."""
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
    if idx < len(rest) and _SITES_RE.match(rest[idx]):
        sites = int(_SITES_RE.match(rest[idx]).group(1))
        idx += 1
    if idx < len(rest) and _GEN_RE.match(rest[idx]):
        gen = int(_GEN_RE.match(rest[idx]).group(1))
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


@lru_cache(maxsize=None)
def _coding_for_id(canonical_id: str) -> Coding:
    params = parse_coding_id(canonical_id)
    if canonical_coding_id(params) != canonical_id:
        # The coding id becomes the seed payload verbatim; only the
        # canonical spelling may get here (a display spelling would mint
        # a second seed for one format).
        raise ValueError(
            f"{canonical_id!r} is not a canonical coding id "
            f"(canonical: {canonical_coding_id(params)!r})")
    if params.gen not in _DEFINED_GENS:
        raise ValueError(
            f"{canonical_id}: generation v{params.gen} is not defined")
    if params.family is Family.K:
        codec = k_codec(params.rungs[0], params.sites)
        rate_id = params.rungs[0]
    elif params.family is Family.CMY7:
        codec = cmy7_codec(params.sites, params.gen)
        rate_id = None
    else:
        codec = cmy8_codec(params.rungs, params.sites)
        rate_id = None
    dots600 = params.pitch * 600
    return Coding(
        coding_id=canonical_id,
        display_coding_id=display_coding_id(params),
        cell_dots=int(dots600) if dots600.denominator == 1 else None,
        rate_id=rate_id,
        n_filler=params.sites - 100,
        codec=codec,
        pooled_fountain=params.family is Family.CMY8,
        pitch_in=params.pitch,
        namespace="v2",
    )


def coding_for(params: CodingParams) -> Coding:
    return _coding_for_id(canonical_coding_id(params))


def make_format(params: CodingParams,
                tiles_yx: tuple[int, int]) -> FormatSpec:
    """One lattice point x tile matrix -> the v2 printed-format identity."""
    ty, tx = tiles_yx
    if ty < 1 or tx < 1:
        raise ValueError(f"tile matrix {tiles_yx} must be at least 1x1")
    if ty * tx > MAX_TILES:
        raise ValueError(
            f"tile matrix {tiles_yx} exceeds the counter space "
            f"({MAX_TILES} tiles)")
    return FormatSpec(coding=coding_for(params), tiles_yx=(ty, tx))


def mint(*, pitch: Fraction, family: Family, rungs: tuple[str, ...],
         sites: int, gen: int, tiles_yx: tuple[int, int]) -> FormatSpec:
    """Parameter door: the dual of ``parse_format_id``.  Explicit; no
    display sugar.  Seed is ``FormatSpec.seed``."""
    return make_format(CodingParams(pitch=pitch, family=family, rungs=rungs,
                                    sites=sites, gen=gen), tiles_yx)


def parse_format_id(format_id: str) -> FormatSpec:
    """Parse (normalizing) a full v2 format id ``coding@TYxTX``."""
    if "@" not in format_id:
        raise ValueError(
            f"format id {format_id!r} needs a tile matrix: coding@TYxTX")
    coding_part, _, tiles_part = format_id.rpartition("@")
    m = _TILES_RE.match(tiles_part)
    if not m:
        raise ValueError(
            f"format id {format_id!r}: tile matrix must be TYxTX")
    params = parse_coding_id(coding_part)
    return make_format(params, (int(m.group(1)), int(m.group(2))))


def cells_for_tiles(tiles_yx: tuple[int, int]) -> tuple[int, int]:
    return tiles_yx[0] * TILE_CELLS, tiles_yx[1] * TILE_CELLS


__all__ = [
    "CodingParams",
    "PITCH_CLASSES",
    "SEED_NAMESPACE",
    "canonical_coding_id",
    "canonical_pitch_token",
    "cells_for_tiles",
    "display_coding_id",
    "display_pitch_token",
    "coding_for",
    "make_format",
    "mint",
    "parse_coding_id",
    "parse_format_id",
    "parse_pitch",
]
