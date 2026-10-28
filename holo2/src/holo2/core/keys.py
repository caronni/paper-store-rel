"""Resource keys: the naming vocabulary every durable fact is stored under.

Keys are core's, permanently — the store, the commit layer, the resource
table, the spend ledger and the trace all key on them, and none of those
may know what a tile or a survey region is. **Records** are not core's:
each package owns its own (``core.registry``), and this module is the
leaf both sides share.

The identity law, hash-free (root DESIGN §6, user ruling 2026-08-11)
--------------------------------------------------------------------
**A durable identity IS its defining values, kept structured.** A window
is named by ``(footing, region, extent)``, a pose by its window and its
parameters, a region by its capture and its support grid — as
:class:`ResourceKey` *parts*, never digested and never flattened into a
delimited string. Flattening is where injectivity died (the WorkId
kind-drop collision); a digest is an identity nobody can read back.
Hashing survives only where it IS the mechanism: blob content addresses,
the source-file SHA, the trace audit.

Two structural rules make injectivity a property of the construction,
not of a test:

1. **Every key has fixed arity per kind.** A composite embeds another
   id's parts wholesale (``window`` carries the six ``region`` parts),
   so the parse is positional and total.
2. **A variable-length component may only be the LAST of its owner's
   parts, and whatever a composite appends after an embedded id has
   fixed arity** — so the split is determined from the end and no
   escaping is ever needed. (Nothing in the tree needs rule 2 today;
   window splitting, OR-9, is where it would arrive.)

Both rules are now CONSTRUCTION, not convention: a kind declares its
shape as a :class:`KeySpec` of :class:`KeyField`/:class:`KeyEmbed` slots
and :func:`build_key`/:func:`parse_key` walk it, so the kind-and-arity
guard every composite builder used to re-spell is written once, here,
where the rules are stated. Named per-kind wrappers stay in the owning
package — they are what call sites read, and they hold the reasoning for
why each key is shaped the way it is.

Choices where §5 is silent (carried from the pre-R3 ``records`` module)
-----------------------------------------------------------------------
1. **ResourceKey.** §5 says "every durable record carries its (key,
   version) implicitly via the store" but does not give the key shape.
   A key is ``(kind, parts)`` with all parts as strings, encoded as the
   flat JSON array ``[kind, *parts]`` (no delimiter, so no escaping).
   Ordering is lexicographic over ``(kind, parts)`` — a total order used
   only for determinism, never for semantics, so the fact that ``"10"``
   sorts before ``"9"`` is harmless. Typed constructors/parsers (in the
   owning packages) are the only sanctioned way to build/read a key.
2. **Sorted-unique tuples.** Tuple fields that model *sets* are required
   sorted and unique. Reason: version-bump-iff-changed compares records
   for equality, so two orderings of one set must not look like a change.
   :func:`require_sorted_unique` is the shared check.

3. **Typed ids.** An id whose defining values are structured IS its
   ``ResourceKey`` — there is no second name for it, and the record that
   used to carry the id as a field carries the values instead (the key
   and the record agree, and the family's validator says so). The
   ``NewType`` aliases that remain are the ATOMS a key is made of: a
   capture SHA, a footing, a stream, a provider-minted subject. A *seam*
   — a record field, a key constructor, a protocol method — names the
   alias; locals need not.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Iterable, NewType, TypeAlias

import numpy as np

KIND_COLLECTION = "collection"

CaptureSha = NewType("CaptureSha", str)
"""SHA-256 of an acquisition's encoded source bytes — the capture identity (L1)."""

FootingId = NewType("FootingId", str)
"""``f"{capture_short}:{ppc_num}/{ppc_den}"`` — one (capture, aperture) pair."""

PoolId = NewType("PoolId", str)
"""A calibration reduce's label-pool scope."""

SubjectId = NewType("SubjectId", str)
"""A provider-minted subject (M3): a work subject that is itself a fact."""

StreamId = NewType("StreamId", str)
"""One logical payload stream of the printed row (``main``, ``C``, ...)."""


class MalformedKeyError(ValueError):
    """Malformed or mis-kinded resource key."""


@dataclass(frozen=True, order=True)
class ResourceKey:
    """A durable resource's name: ``kind`` plus string ``parts``."""

    kind: str
    parts: tuple[str, ...] = ()

    def to_json(self) -> list[str]:
        return [self.kind, *self.parts]

    @classmethod
    def from_json(cls, raw: Any) -> "ResourceKey":
        if (not isinstance(raw, list) or not raw
                or not all(isinstance(item, str) for item in raw)):
            raise MalformedKeyError(f"malformed resource key {raw!r}")
        return cls(raw[0], tuple(raw[1:]))

    def __str__(self) -> str:
        """DISPLAY only — readable, and never parsed back into an identity."""
        return "/".join((self.kind, *self.parts))


def key_parts(*values: Any) -> tuple[str, ...]:
    """Canonically stringify defining values into key parts.

    One renderer, so "the id IS its values" has exactly one spelling:
    integers as ``str(int)``, floats as ``repr(float)`` (which
    round-trips, so the parameter in the key is the parameter that was
    fitted), strings verbatim, numpy scalars coerced first — ``repr`` of
    a ``np.float64`` is not a number under numpy 2, and a silently
    different rendering is a silently different id. Booleans and
    non-finite floats are refused: neither is a defining value.
    """
    rendered: list[str] = []
    for value in values:
        if isinstance(value, str):
            rendered.append(value)
        elif isinstance(value, (bool, np.bool_)):
            raise TypeError("a boolean is not a key part")
        elif isinstance(value, (int, np.integer)):
            rendered.append(str(int(value)))
        elif isinstance(value, (float, np.floating)):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"{value!r} is not a finite key part")
            rendered.append(repr(number))
        else:
            raise TypeError(
                f"{type(value).__name__} is not a key part; pass its values")
    return tuple(rendered)


# ------------------------------------------------------- declarative keys


@dataclass(frozen=True)
class KeyField:
    """One of the owner's OWN defining values, ``arity`` parts wide.

    ``cast`` is how a parse reads the value back: ``str`` for a name,
    ``int`` for a coordinate. Only the values a parser actually recovers
    need one — a pose's affine terms are rendered by :func:`key_parts` and
    read back by nobody, so their cast is never exercised.
    """

    name: str
    arity: int = 1
    cast: Callable[[str], Any] = str


@dataclass(frozen=True)
class KeyEmbed:
    """Another id's parts, carried wholesale at a FIXED arity.

    This is rule 1 above made executable: the embedded id occupies a
    known slice of its container's parts, so the container's parse is
    positional and total, and the embedding is injective by construction
    rather than by a test over spellings.
    """

    name: str
    kind: str
    arity: int


@dataclass(frozen=True)
class KeySpec:
    """One kind's key, declared as an ordered tuple of slots.

    The four builders that embedded another id were each re-spelling the
    same two-line kind-and-arity guard, and two of the parsers the same
    slice-then-convert; the guard is the module's own central claim, so it
    is written ONCE here and every kind declares its shape instead. Slot
    ORDER is the spec's data because the tree's kinds genuinely differ: a
    window carries its embed in the middle, an evidence key at the end, a
    pose and a hint at the start.
    """

    kind: str
    slots: tuple[KeyField | KeyEmbed, ...]

    @property
    def arity(self) -> int:
        """This kind's fixed part count — what a parse checks first."""
        return sum(slot.arity for slot in self.slots)


def _article(kind: str) -> str:
    """``a``/``an`` for a kind name, so the refusals read as English."""
    return "an" if kind[:1] in "aeiou" else "a"


def build_key(spec: KeySpec, **values: Any) -> ResourceKey:
    """The key a spec's slots name, refusing an ill-shaped component.

    Embedded ids are checked for kind AND arity here — the one guard the
    per-kind builders used to repeat — and everything else goes through
    :func:`key_parts`, so a spec cannot invent a second rendering.
    """
    parts: list[str] = []
    for slot in spec.slots:
        value = values[slot.name]
        if isinstance(slot, KeyEmbed):
            if (not isinstance(value, ResourceKey) or value.kind != slot.kind
                    or len(value.parts) != slot.arity):
                raise MalformedKeyError(
                    f"not {_article(slot.kind)} {slot.kind} key: {value}")
            parts.extend(value.parts)
        elif slot.arity == 1:
            parts.extend(key_parts(value))
        else:
            items = tuple(value)
            if len(items) != slot.arity:
                raise MalformedKeyError(
                    f"{spec.kind}.{slot.name} is {slot.arity} values, "
                    f"got {len(items)}")
            parts.extend(key_parts(*items))
    return ResourceKey(spec.kind, tuple(parts))


def parse_key(spec: KeySpec, key: ResourceKey) -> dict[str, Any]:
    """Read a key back into its slots: total, positional, fallible once.

    The arity check is the whole parse — past it every slice is known —
    so the only way this fails afterwards is a part that does not read as
    the number its slot declares, which is a malformed key and says so.
    """
    if key.kind != spec.kind or len(key.parts) != spec.arity:
        raise MalformedKeyError(
            f"not {_article(spec.kind)} {spec.kind} key: {key}")
    values: dict[str, Any] = {}
    offset = 0
    for slot in spec.slots:
        chunk = key.parts[offset:offset + slot.arity]
        offset += slot.arity
        if isinstance(slot, KeyEmbed):
            values[slot.name] = ResourceKey(slot.kind, chunk)
            continue
        try:
            read = tuple(slot.cast(part) for part in chunk)
        except ValueError as exc:
            raise MalformedKeyError(
                f"not {_article(spec.kind)} {spec.kind} key: {key}") from exc
        values[slot.name] = read[0] if slot.arity == 1 else read
    return values


@dataclass(frozen=True, order=True)
class WorkScope:
    """What a descriptor is about beyond its subject and route.

    Two data fields, both optional, neither of which the engine reads:

    * ``arm`` — a recipe-supplied override that must ride the descriptor
      rather than an ambient flag (M9), so a resumed state reads it from
      the work it belongs to and its spends stay independent;
    * ``profile`` — a provider-owned discriminator for work that is
      otherwise identical (a stratum, a page domain, a size class).

    ``arm``'s consumers arrive with the calibration providers (H4/H5); the
    field exists now because it is written today (``ExpansionRequest.mint``
    lifts the request's arm onto every descriptor). M8's ``incumbent`` —
    the id a non-monotone improvement would be measured against — was
    declared here and never set or read, and was DELETED under the
    2026-08-12 ruling (W-B/B2): re-adding an optional-empty field stays
    free until its first writer, because :attr:`tag` skips empty parts and
    a work id is a structure of values rather than a rendering. The intent
    it recorded lives in ``solve/PROVIDERS.md``.
    """

    arm: str = ""
    profile: str = ""

    @property
    def tag(self) -> str:
        """DISPLAY only: the readable discriminator, in reading order."""
        return "/".join(part for part in (self.profile, self.arm) if part)


@dataclass(frozen=True, order=True)
class WorkId:
    """A work descriptor's durable name: the descriptor's own values.

    What the spend ledger, the subscription index and the ready queue key
    on. It is a STRUCTURE, not a rendering: the review's collision pair
    (a subject whose kind was dropped when its parts were empty, and a
    ``/``-join that could not tell ``a/b`` + ``c`` from ``a`` + ``b/c``)
    is unrepresentable here, because the family, the subject's kind, its
    parts, the route and the scope stay separate values.

    ``__str__`` is the display rendering. Nothing parses it back.
    """

    family: str
    subject: ResourceKey
    route: str
    scope: WorkScope = WorkScope()

    def to_json(self) -> list[Any]:
        return [self.family, self.subject.to_json(), self.route,
                [self.scope.arm, self.scope.profile]]

    @classmethod
    def from_json(cls, raw: Any) -> "WorkId":
        if (not isinstance(raw, list) or len(raw) != 4
                or not isinstance(raw[0], str) or not isinstance(raw[2], str)
                or not isinstance(raw[3], list) or len(raw[3]) != 2
                or not all(isinstance(item, str) for item in raw[3])):
            raise MalformedKeyError(f"malformed work id {raw!r}")
        return cls(raw[0], ResourceKey.from_json(raw[1]), raw[2],
                   WorkScope(*raw[3]))

    def __str__(self) -> str:
        """DISPLAY only — collisions here cost readability, never identity."""
        subject = "/".join(self.subject.parts) or self.subject.kind
        tag = self.scope.tag
        return (f"{self.family}:{subject}@{self.route}"
                + (f"#{tag}" if tag else ""))


#: A durable fact. core stores records **generically**: what it may assume
#: is that a record is a frozen dataclass its registry declared a family
#: for (``core.registry``), and nothing about its fields. Typing it as a
#: closed union is what used to force every package's schema through core.
Record: TypeAlias = Any

#: §5.5 / §7. The read frontier an attempt was taken against. Declared
#: here because it is a tuple of keys and ``identity.py`` needs the type;
#: the machinery that builds, spends and compares identities is there.
AttemptIdentity: TypeAlias = tuple[tuple[ResourceKey, int], ...]


def collection_key(name: str, *parts: str) -> ResourceKey:
    """A membership resource (M4): version = member count, no record.

    A worker names a collection when it depends on *membership* ("the
    evidence on this tile", "the certified frontier") rather than on a key
    it can already name — the case a subscriber index cannot express
    otherwise, because a key that does not exist yet has no version to
    bump. The resource table derives collection versions from the durable
    records, so they are rebuildable and carry no authority.
    """
    return ResourceKey(KIND_COLLECTION, (name, *parts))


def require_sorted_unique(values: Iterable[Any], name: str) -> None:
    """Refuse a set-modelling tuple that is unsorted or holds duplicates."""
    items = tuple(values)
    if any(b <= a for a, b in zip(items, items[1:])):
        raise ValueError(f"{name} must be sorted and unique, got {items!r}")


def require_finite_positive(value: float, name: str) -> None:
    """Refuse a scale that is not a positive real number.

    A DPI, a pitch, a pixels-per-cell: the same three-clause check the
    capture boundary was writing out at each of its walls (a bool is not a
    number even though Python says it is one, and NaN compares false
    against every bound it would later be checked with).
    """
    if (isinstance(value, (bool, np.bool_))
            or not math.isfinite(float(value)) or float(value) <= 0):
        raise ValueError(f"{name} must be finite and positive, got {value!r}")


def require_sha256_hex(value: str, name: str) -> None:
    """Refuse anything that is not a lowercase 64-digit SHA-256 rendering.

    Content addresses are compared as strings and sort as strings, so one
    spelling is the whole contract: an uppercase digest of the same bytes
    is a different id.
    """
    if (not isinstance(value, str) or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)):
        raise ValueError(
            f"{name} must be 64 lowercase hex digits, got {value!r}")


__all__ = ["AttemptIdentity", "CaptureSha", "FootingId", "KIND_COLLECTION",
           "KeyEmbed", "KeyField", "KeySpec", "MalformedKeyError", "PoolId",
           "Record", "ResourceKey", "StreamId", "SubjectId", "WorkId",
           "WorkScope", "build_key", "collection_key", "key_parts",
           "parse_key", "require_finite_positive", "require_sha256_hex",
           "require_sorted_unique"]
