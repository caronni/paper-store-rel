"""Strict canonical JSON codec and atomic transport for typed state.

One state = ONE file (holo-v1-kiss). Content-addressed evidence items are
inlined into the manifest as compressed base64 with their SHA-256 and raw
size; the envelope digest therefore covers evidence bytes too, and there
is no sibling blob directory to keep consistent.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import tempfile
import types
import zlib
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Union, get_args, get_origin, get_type_hints


_BLOB_ITEMS = "blob_items"

# Persist blob cache (growth-audit row 3 / PAYLOAD-REWORK-PLAN 3.6): blocks
# are immutable and content-addressed, so their compressed inline form is a
# pure function of ``block_id``.  Entries are ``(raw size, base64 text)``.
# The cache is armed only while ``_save_typed`` encodes (``_blob_touched``
# is the tracking set) and is pruned to the just-persisted live block set
# after every save, which bounds it at one barrier's blocks.
_blob_cache: dict[str, tuple[int, str]] = {}
_blob_touched: set[str] | None = None


def _blob_inline(value: Any) -> dict[str, Any]:
    try:
        identity = value.block_id
    except AttributeError as exc:
        raise TypeError(
            "blob field contains a non-content-addressed value") from exc
    if (not isinstance(identity, str) or len(identity) != 64
            or any(char not in "0123456789abcdef" for char in identity)):
        raise ValueError("blob field has an invalid content address")
    touched = _blob_touched
    if touched is not None:
        cached = _blob_cache.get(identity)
        if cached is not None:
            touched.add(identity)
            size, packed = cached
            return {"sha256": identity, "size": size, "data": packed}
    try:
        data = value.to_bytes()
    except AttributeError as exc:
        raise TypeError(
            "blob field contains a non-content-addressed value") from exc
    if not isinstance(data, bytes):
        raise ValueError("blob field has an invalid content address")
    packed = base64.b64encode(zlib.compress(data, 6)).decode("ascii")
    if touched is not None:
        _blob_cache[identity] = (len(data), packed)
        touched.add(identity)
    return {"sha256": identity, "size": len(data), "data": packed}


def _encode_for_persist(value: Any) -> Any:
    """Encode with the blob cache armed; prune it to the live block set."""
    global _blob_touched
    _blob_touched = set()
    try:
        return encode_typed(value)
    finally:
        touched = _blob_touched
        _blob_touched = None
        for identity in [key for key in _blob_cache if key not in touched]:
            del _blob_cache[identity]


def encode_typed(value: Any) -> Any:
    if is_dataclass(value):
        output: dict[str, Any] = {}
        for field in fields(value):
            if not field.metadata.get("persist", True):
                continue
            item = getattr(value, field.name)
            if field.metadata.get(_BLOB_ITEMS, False):
                if not isinstance(item, tuple):
                    raise TypeError("blob-items field must be a tuple")
                output[field.name] = [_blob_inline(row) for row in item]
            else:
                output[field.name] = encode_typed(item)
        return output
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, tuple):
        return [encode_typed(row) for row in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"cannot encode authoritative {type(value).__name__}")


def _decode_blob_items(value: Any, annotation: Any,
                       label: str) -> tuple[Any, ...]:
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if (origin is not tuple or len(arguments) != 2
            or arguments[1] is not Ellipsis or not isinstance(value, list)):
        raise ValueError(f"{label} is not a blob tuple")
    kind = arguments[0]
    output: list[Any] = []
    seen: set[str] = set()
    for index, ref in enumerate(value):
        item_label = f"{label}[{index}]"
        if not isinstance(ref, dict) or set(ref) != {"sha256", "size", "data"}:
            raise ValueError(f"{item_label} has an invalid inline blob")
        identity, size, packed = ref["sha256"], ref["size"], ref["data"]
        if (not isinstance(identity, str) or len(identity) != 64
                or any(char not in "0123456789abcdef" for char in identity)
                or type(size) is not int or size < 0 or identity in seen
                or not isinstance(packed, str)):
            raise ValueError(f"{item_label} has a non-canonical inline blob")
        seen.add(identity)
        try:
            data = zlib.decompress(base64.b64decode(
                packed.encode("ascii"), validate=True))
        except (ValueError, zlib.error) as exc:
            raise ValueError(f"{item_label} inline blob is undecodable") from exc
        if len(data) != size:
            raise ValueError(f"{item_label} inline blob size disagrees")
        # Mint-once (rework Phase 3.1): the ONE load-boundary digest check
        # is ``from_bytes`` (body vs 32-byte trailer, evidence_blocks); the
        # ``block_id`` comparison below then binds that verified content
        # address to the manifest identity, so no separate pre-hash runs.
        try:
            item = kind.from_bytes(data)
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"{item_label} inline blob is invalid") from exc
        if getattr(item, "block_id", None) != identity:
            raise ValueError(f"{item_label} content address changed")
        output.append(item)
    return tuple(output)


def decode_typed(value: Any, annotation: Any, label: str = "state") -> Any:
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin in (Union, types.UnionType):
        if value is None and type(None) in arguments:
            return None
        failures: list[Exception] = []
        for choice in arguments:
            if choice is type(None):
                continue
            try:
                return decode_typed(value, choice, label)
            except (TypeError, ValueError) as exc:
                failures.append(exc)
        raise ValueError(
            f"{label} does not match its union type") from failures[-1]
    if origin is tuple:
        if not isinstance(value, list):
            raise ValueError(f"{label} must be an array")
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(decode_typed(row, arguments[0], label)
                         for row in value)
        if len(value) != len(arguments):
            raise ValueError(f"{label} has the wrong tuple length")
        return tuple(decode_typed(row, kind, label)
                     for row, kind in zip(value, arguments, strict=True))
    if annotation is bytes:
        if not isinstance(value, str) or len(value) % 2:
            raise ValueError(f"{label} must be even-length hexadecimal text")
        try:
            result = bytes.fromhex(value)
        except ValueError as exc:
            raise ValueError(f"{label} is not hexadecimal") from exc
        if result.hex() != value:
            raise ValueError(f"{label} is not canonical lowercase hexadecimal")
        return result
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, dict):
            raise ValueError(f"{label} must be an object")
        persisted = tuple(row for row in fields(annotation)
                          if row.metadata.get("persist", True))
        expected = {row.name for row in persisted}
        if set(value) != expected:
            raise ValueError(f"{label} has unexpected or missing keys")
        hints = get_type_hints(annotation)
        decoded: dict[str, Any] = {}
        for row in persisted:
            field_label = f"{label}.{row.name}"
            if row.metadata.get(_BLOB_ITEMS, False):
                decoded[row.name] = _decode_blob_items(
                    value[row.name], hints[row.name], field_label)
            else:
                decoded[row.name] = decode_typed(
                    value[row.name], hints[row.name], field_label)
        return annotation(**decoded)
    if annotation is str:
        if type(value) is not str:
            raise ValueError(f"{label} must be text")
        return value
    if annotation is bool:
        if type(value) is not bool:
            raise ValueError(f"{label} must be boolean")
        return value
    if annotation is int:
        if type(value) is not int:
            raise ValueError(f"{label} must be an integer")
        return value
    if annotation is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{label} must be a number")
        return float(value)
    if annotation is Any:
        return value
    raise TypeError(f"unsupported persisted annotation {annotation!r}")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def _check_wire_contract(magic: str, schema: int) -> None:
    if not isinstance(magic, str) or not magic:
        raise ValueError("state magic must be non-empty text")
    if type(schema) is not int or schema < 1:
        raise ValueError("state schema must be a positive integer")


def authoritative_state_bytes(value: Any, *, magic: str, schema: int) -> bytes:
    """Domain-separate one encoded state value by its wire contract."""
    _check_wire_contract(magic, schema)
    return canonical_bytes({
        "magic": magic,
        "schema_version": schema,
        "state": value,
    })


def authoritative_state_sha256(value: Any, *, magic: str, schema: int) -> str:
    return hashlib.sha256(
        authoritative_state_bytes(value, magic=magic, schema=schema)
    ).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _prior_manifest_bytes(
    target: Path, expected_size: int | None = None,
) -> bytes | None:
    """Read the existing manifest for the no-op comparison.

    ``expected_size`` short-circuits the read: mid-session states grow
    monotonically, so a size mismatch already proves the write is not a
    no-op without paying an O(state) read (growth audit 2026-07-31).
    """
    try:
        status = target.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(status.st_mode):
        raise ValueError("existing receive manifest is not a regular file")
    if expected_size is not None and status.st_size != expected_size:
        return None
    return target.read_bytes()


def _envelope_documents(payload: Any, *, magic: str,
                        schema: int) -> tuple[bytes, str]:
    """Envelope bytes + digest around ONE payload serialization.

    Canonical dumps are compositional (``sort_keys``/``separators``/
    ``ensure_ascii`` apply per node), so serializing the payload once and
    splicing that string into both the digest preimage and the envelope is
    byte-identical to dumping each document whole.  Keys are spliced in
    canonical sorted order (``"magic" < "schema_version" < "state" <
    "state_sha256"``).
    """
    _check_wire_contract(magic, schema)
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                              ensure_ascii=False, allow_nan=False)
    magic_json = json.dumps(magic, ensure_ascii=False)
    prefix = (f'{{"magic":{magic_json},"schema_version":{schema},'
              f'"state":{payload_json}')
    state_sha256 = hashlib.sha256((prefix + "}\n").encode()).hexdigest()
    data = (prefix + f',"state_sha256":"{state_sha256}"}}\n').encode()
    return data, state_sha256


def _save_typed(path: str | Path, value: Any, *, magic: str, schema: int,
                validate: Callable[[Any], None] | None = None
                ) -> tuple[bool, str]:
    if validate is not None:
        validate(value)
    target = Path(path)
    payload = _encode_for_persist(value)
    data, state_sha256 = _envelope_documents(
        payload, magic=magic, schema=schema)
    target.parent.mkdir(parents=True, exist_ok=True)
    if _prior_manifest_bytes(target, expected_size=len(data)) == data:
        return False, state_sha256
    descriptor, name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        try:
            directory = os.open(target.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            pass
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return True, state_sha256


def save_typed(path: str | Path, value: Any, *, magic: str, schema: int,
               validate: Callable[[Any], None] | None = None) -> bool:
    return _save_typed(
        path, value, magic=magic, schema=schema, validate=validate)[0]


def save_typed_with_digest(
    path: str | Path,
    value: Any,
    *,
    magic: str,
    schema: int,
    validate: Callable[[Any], None] | None = None,
) -> tuple[bool, str]:
    return _save_typed(
        path, value, magic=magic, schema=schema, validate=validate)


def _migrated(document: Any, stored: int, schema: int,
              migrations: Mapping[int, Callable[[Any], Any]] | None) -> Any:
    """Lift one older document to ``schema`` through the declared steps.

    A migration step is ADDITIVE ONLY: it supplies the keys a later field
    set added, at the defaults the dataclass declares.  It never rewrites
    a stored value — a change needing that is a new state identity, not a
    migration, and the older version simply stops being accepted.
    """
    if stored == schema:
        return document
    for version in range(stored, schema):
        step = None if migrations is None else migrations.get(version)
        if step is None:
            raise ValueError(
                f"receive state schema {stored} cannot be lifted to "
                f"{schema}: no migration is declared from {version}")
        document = step(document)
    return document


def _load_typed(path: str | Path, kind: type, *, magic: str, schema: int,
                validate: Callable[[Any], None] | None = None,
                migrations: Mapping[int, Callable[[Any], Any]] | None = None,
                ) -> tuple[Any, str]:
    source = Path(path)
    try:
        envelope = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=lambda value: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number {value}")),
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid receive state JSON: {exc}") from exc
    if not isinstance(envelope, dict) or set(envelope) != {
            "magic", "schema_version", "state_sha256", "state"}:
        raise ValueError("invalid receive state envelope")
    stored = envelope["schema_version"]
    if (envelope["magic"] != magic or type(stored) is not int
            or stored < 1 or stored > schema):
        raise ValueError("receive state magic or schema is unsupported")
    expected = envelope["state_sha256"]
    if (not isinstance(expected, str) or len(expected) != 64
            or any(char not in "0123456789abcdef" for char in expected)):
        raise ValueError("invalid receive state envelope digest")
    # The digest covers the version the file was WRITTEN under; a migrated
    # document is authenticated as its stored self before it is lifted.
    if authoritative_state_sha256(
            envelope["state"], magic=magic, schema=stored) != expected:
        raise ValueError("receive state authoritative digest mismatch")
    result = decode_typed(
        _migrated(envelope["state"], stored, schema, migrations), kind)
    if validate is not None:
        validate(result)
    return result, expected


def load_typed(path: str | Path, kind: type, *, magic: str, schema: int,
               validate: Callable[[Any], None] | None = None,
               migrations: Mapping[int, Callable[[Any], Any]] | None = None,
               ) -> Any:
    return _load_typed(
        path, kind, magic=magic, schema=schema, validate=validate,
        migrations=migrations)[0]


def load_typed_with_digest(
    path: str | Path,
    kind: type,
    *,
    magic: str,
    schema: int,
    validate: Callable[[Any], None] | None = None,
    migrations: Mapping[int, Callable[[Any], Any]] | None = None,
) -> tuple[Any, str]:
    return _load_typed(
        path, kind, magic=magic, schema=schema, validate=validate,
        migrations=migrations)


__all__ = [
    "authoritative_state_bytes", "authoritative_state_sha256",
    "canonical_bytes", "decode_typed", "encode_typed",
    "load_typed", "load_typed_with_digest", "save_typed",
    "save_typed_with_digest",
]
