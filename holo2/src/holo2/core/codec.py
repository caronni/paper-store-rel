"""Canonical JSON and the strict, type-driven codec for the §5 records.

Contracts:

- ``canonical_json_bytes(obj)`` is a deterministic byte string: keys
  sorted, no insignificant whitespace, ASCII-escaped, ``NaN``/``Infinity``
  refused. Two equal Python values always encode to equal bytes.
- ``encode_dataclass(obj)`` emits exactly the dataclass's fields, driven
  by their type hints; ``decode_dataclass(cls, raw)`` refuses unknown
  fields, missing fields (defaults do NOT fill a missing field — there
  are no migration decoders, DESIGN §10.4) and wrong types.
- Encoding rules: ``Enum`` by member NAME (numeric values stay internal),
  ``Fraction`` as ``[numerator, denominator]``, tuples as JSON arrays,
  ``X | None`` as ``null`` or the encoded ``X``, nested dataclasses as
  objects, and any type exposing ``to_json``/``from_json`` through those
  (``ResourceKey`` uses this to stay a flat array).
- ``int`` fields refuse ``bool``; ``float`` fields accept an integral JSON
  number and coerce (JSON has one number type).

The codec is **type-driven, never table-driven**: it encodes whatever
frozen dataclass it is handed and decodes into whatever class it is told.
Which classes those are is the record registry's answer (``registry.py``),
which is what lets a package change its own record shape without this
module — or any other core module — knowing the shape existed.

This module imports nothing from the rest of holo2 (leaf).
"""
from __future__ import annotations

import functools
import hashlib
import json
import types
from dataclasses import fields, is_dataclass
from enum import Enum
from fractions import Fraction
from typing import Any, Union, get_args, get_origin, get_type_hints


class CodecError(ValueError):
    """Strict refusal: unknown/missing field, bad type, unsupported hint."""


def canonical_json_bytes(obj: Any) -> bytes:
    """Deterministic UTF-8 JSON bytes for ``obj``."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("utf-8")


def _refuse_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """The read path's half of canonicality: one key, one value."""
    seen: dict[str, Any] = {}
    for name, value in pairs:
        if name in seen:
            raise CodecError(f"duplicate JSON key {name!r}")
        seen[name] = value
    return seen


def _refuse_nonfinite(token: str) -> Any:
    raise CodecError(f"JSON constant {token} is not a number")


def parse_json_bytes(payload: bytes) -> Any:
    """Parse UTF-8 JSON bytes, as strictly as ``canonical_json_bytes`` writes.

    ``json.loads`` is permissive where the writer is not — a duplicate
    object key silently keeps the last value, ``NaN``/``Infinity`` parse
    as floats ``allow_nan=False`` would never emit — so both are refused
    rather than read back as an envelope this build could not write.
    """
    try:
        return json.loads(payload.decode("utf-8"),
                          object_pairs_hook=_refuse_duplicate_keys,
                          parse_constant=_refuse_nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CodecError(f"unparseable JSON: {exc}") from exc


def sha256_hex(payload: bytes) -> str:
    """Content address of ``payload`` (lowercase hex)."""
    return hashlib.sha256(payload).hexdigest()


def digest_json(obj: Any) -> str:
    """Content digest of the canonical encoding of ``obj``."""
    return sha256_hex(canonical_json_bytes(obj))


@functools.lru_cache(maxsize=None)
def _hints(cls: type) -> dict[str, Any]:
    return get_type_hints(cls)


def encode_dataclass(obj: Any) -> dict[str, Any]:
    """Encode a frozen dataclass instance to a JSON-able dict."""
    cls = type(obj)
    if not is_dataclass(cls):
        raise CodecError(f"{cls.__name__} is not a dataclass")
    hints = _hints(cls)
    return {
        f.name: encode_value(getattr(obj, f.name), hints[f.name])
        for f in fields(cls)
    }


def encode_typed_record(record: Any) -> dict[str, Any]:
    """A record encoded as ``{type, value}`` — the polymorphic entry shape.

    Durable and digested places that hold "some record" (the store's
    envelope entries, a proposed :class:`~holo2.core.commit.Write`, the
    trace's sampled output digest) all need the class NAME beside the
    fields, because ``encode_dataclass`` alone does not carry it: two
    different record types at one key with coincidentally equal fields
    encode identically. One spelling, so a site cannot drop the tag by
    omission — which is exactly what the sampled trace digest did before
    this helper existed.
    """
    return {"type": type(record).__name__, "value": encode_dataclass(record)}


def decode_dataclass(cls: type, raw: Any) -> Any:
    """Decode ``raw`` into ``cls``; strict on unknown/missing fields."""
    if not isinstance(raw, dict):
        raise CodecError(
            f"{cls.__name__}: expected object, got {type(raw).__name__}")
    hints = _hints(cls)
    names = [f.name for f in fields(cls)]
    unknown = sorted(set(raw) - set(names))
    if unknown:
        raise CodecError(f"{cls.__name__}: unknown field(s) {unknown}")
    missing = [name for name in names if name not in raw]
    if missing:
        raise CodecError(f"{cls.__name__}: missing field(s) {missing}")
    return cls(**{name: decode_value(raw[name], hints[name]) for name in names})


def _optional_arg(hint: Any) -> Any | None:
    """The single non-None member of an optional hint, else None."""
    origin = get_origin(hint)
    if origin is not Union and origin is not types.UnionType:
        return None
    args = [arg for arg in get_args(hint) if arg is not type(None)]
    if len(args) != 1 or len(get_args(hint)) != 2:
        raise CodecError(f"unsupported union hint {hint!r}")
    return args[0]


def _erased(hint: Any) -> Any:
    """A ``NewType``'s supertype; anything else unchanged.

    R1's typed ids (``WindowId``, ``FootingId``, ...) are ``NewType``
    aliases: they exist for the type checker and erase to ``str`` at
    runtime. The codec follows that erasure exactly, so a typed id
    serialises as the string it IS and the envelope is byte-identical to
    the untyped one.
    """
    supertype = getattr(hint, "__supertype__", None)
    return hint if supertype is None else _erased(supertype)


def encode_value(value: Any, hint: Any) -> Any:
    """Encode ``value`` according to its declared ``hint``."""
    hint = _erased(hint)
    inner = _optional_arg(hint)
    if inner is not None:
        return None if value is None else encode_value(value, inner)
    origin = get_origin(hint)
    if origin is tuple:
        args = get_args(hint)
        if len(args) == 2 and args[1] is Ellipsis:
            return [encode_value(item, args[0]) for item in value]
        return [
            encode_value(item, arg)
            for item, arg in zip(value, args, strict=True)
        ]
    if hint is bool:
        _require(isinstance(value, bool), hint, value)
        return value
    if hint is int:
        _require(isinstance(value, int) and not isinstance(value, bool),
                 hint, value)
        return value
    if hint is float:
        _require(isinstance(value, (int, float)) and not isinstance(value, bool),
                 hint, value)
        return float(value)
    if hint is str:
        _require(isinstance(value, str), hint, value)
        return value
    if hint is Fraction:
        _require(isinstance(value, Fraction), hint, value)
        return [value.numerator, value.denominator]
    if isinstance(hint, type):
        if issubclass(hint, Enum):
            _require(isinstance(value, hint), hint, value)
            return value.name
        if hasattr(hint, "to_json"):
            _require(isinstance(value, hint), hint, value)
            return value.to_json()
        if is_dataclass(hint):
            _require(isinstance(value, hint), hint, value)
            return encode_dataclass(value)
    raise CodecError(f"unsupported type hint {hint!r}")


def decode_value(raw: Any, hint: Any) -> Any:
    """Decode ``raw`` according to its declared ``hint``."""
    hint = _erased(hint)
    inner = _optional_arg(hint)
    if inner is not None:
        return None if raw is None else decode_value(raw, inner)
    origin = get_origin(hint)
    if origin is tuple:
        args = get_args(hint)
        _require(isinstance(raw, list), hint, raw)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(decode_value(item, args[0]) for item in raw)
        if len(raw) != len(args):
            raise CodecError(f"{hint!r}: expected {len(args)} items, got {len(raw)}")
        return tuple(
            decode_value(item, arg) for item, arg in zip(raw, args, strict=True)
        )
    if hint is bool:
        _require(isinstance(raw, bool), hint, raw)
        return raw
    if hint is int:
        _require(isinstance(raw, int) and not isinstance(raw, bool), hint, raw)
        return raw
    if hint is float:
        _require(isinstance(raw, (int, float)) and not isinstance(raw, bool),
                 hint, raw)
        return float(raw)
    if hint is str:
        _require(isinstance(raw, str), hint, raw)
        return raw
    if hint is Fraction:
        _require(isinstance(raw, list) and len(raw) == 2, hint, raw)
        _require(all(isinstance(item, int) and not isinstance(item, bool)
                     for item in raw), hint, raw)
        return Fraction(raw[0], raw[1])
    if isinstance(hint, type):
        if issubclass(hint, Enum):
            _require(isinstance(raw, str), hint, raw)
            try:
                return hint[raw]
            except KeyError:
                raise CodecError(f"{hint.__name__}: unknown member {raw!r}") from None
        if hasattr(hint, "from_json"):
            return hint.from_json(raw)
        if is_dataclass(hint):
            return decode_dataclass(hint, raw)
    raise CodecError(f"unsupported type hint {hint!r}")


def _require(condition: bool, hint: Any, value: Any) -> None:
    if not condition:
        raise CodecError(
            f"expected {getattr(hint, '__name__', hint)!s}, "
            f"got {type(value).__name__}: {value!r}")
