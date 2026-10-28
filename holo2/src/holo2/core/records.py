"""core's OWN durable records — and only those (R3).

Until R3 this module held every record in the tree. It now holds the two
that are core's by ownership, plus the bulk-value reference every package
uses; everything else moved to the package that WRITES it:

* ``capture`` — ``CaptureRecord``, ``FootingSpec``, ``RegionRecord``;
* ``solve`` — the tile map, poses, hints, windows, evidence, label pools,
  calibrations;
* ``engine`` — ``SessionIdentity``.

RECORDS core owns
-----------------
* :class:`SubjectSpec` — a provider-minted work subject (M3). The
  *mechanism* is core's work protocol: a subject the session did not
  start with has to BE a fact before work can be offered on it, and core
  never interprets the parameters a provider put in it.
* :class:`CloseRecord` — the session's terminality. Its content is
  produced by the close provider (``solve``) out of format math, but the
  law it carries is core's: a terminal close freezes every later commit
  (``commit.TerminalSessionError``) and the engine's lifecycle reads it
  (``engine.SessionContext.close_record``). Both of those may not import
  ``solve``, so ownership by "who writes it" would need a hook that lets a
  downstream family declare session terminality. That hook is integrity
  semantics, which R3 deliberately leaves to the review round — recorded
  here as the reason, not hidden as an accident.

Choices where §5 is silent, for the records below
-------------------------------------------------
* **MintRef / HeldoutGate** are referenced by §5 but not defined; both now
  live with the solve records that use them.
* **BlobRef** is the bulk-value reference: content address plus the numpy
  ``dtype``/``shape`` needed to reinterpret the raw bytes (both ``None``
  for opaque byte blobs).
* **CloseRecord** is one record with a ``CloseStatus`` plus the
  status-specific fields of §5.5 (sha, bytes ref, reason). Terminal =
  ``status is not OPEN``; the commit layer refuses every later write.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any
from .keys import (AttemptIdentity, KIND_COLLECTION, MalformedKeyError, Record,
                   ResourceKey, SubjectId, collection_key,
                   require_sorted_unique)
from .registry import RecordFamily, RegistryError

KIND_SUBJECT = "subject"
KIND_CLOSE = "close"

CLOSE_KEY = ResourceKey(KIND_CLOSE, ())


def subject_key(subject_id: SubjectId) -> ResourceKey:
    """A provider-minted subject (M3)."""
    return ResourceKey(KIND_SUBJECT, (subject_id,))


def subject_collection_key(family: str) -> ResourceKey:
    """Every provider-minted subject of one task family (M3)."""
    return collection_key("subjects", family)


# --------------------------------------------------------------------------
# value types (nested; not resources of their own)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BlobRef:
    """Reference into the append-only content-addressed blob sidecar."""

    sha256: str
    length_bytes: int
    dtype: str | None = None          # numpy dtype str incl. byte order
    shape: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.length_bytes < 0:
            raise ValueError("BlobRef.length_bytes must be >= 0")
        if (self.dtype is None) != (self.shape is None):
            raise ValueError("BlobRef: dtype and shape come as a pair")


def blob_refs(value: Any) -> tuple[BlobRef, ...]:
    """Every ``BlobRef`` reachable from one record, in field order.

    THE walker: the commit wall, the store's load-time check and the
    provider contract battery all ask this question, and three copies of
    it was three chances to miss a case — as one did (the dataclass arm
    must exclude a dataclass TYPE, or a class-valued field walks its own
    declaration).
    """
    if isinstance(value, BlobRef):
        return (value,)
    if isinstance(value, tuple):
        return tuple(ref for item in value for ref in blob_refs(item))
    if is_dataclass(value) and not isinstance(value, type):
        return tuple(ref for field_ in fields(value)
                     for ref in blob_refs(getattr(value, field_.name)))
    return ()


def require_own_key(key: ResourceKey, record: Record) -> None:
    """THE key⇔record identity check (F-07), published for every family.

    Since the identity law (root DESIGN §6) a durable id IS its defining
    values, so a record that cannot rebuild the key it is stored under is
    a durable state nothing could have minted — a piece of geometry,
    provenance or scope that would be read back as something it is not.
    Family ``validate`` callbacks are key-AWARE precisely so this is
    catchable (``registry.RecordFamily.validate``), and they run at the
    commit wall and at load: under the publication-order law the check
    belongs before anything moves, not after the store is durable, which
    is what closed HARDENING-SYSTEMIC-REVIEW P0-1.

    It is published from core because nine families in three packages
    state the same law, and three copies of one sentence were three
    chances to word it differently. A family whose record cannot name its
    WHOLE key proves the half it can and says so; solve's hint family was
    the tree's one example, until H4 W2 made the window the hint state's
    SUBJECT rather than its addressee and it joined the adopters here.
    """
    if key != record.resource_key():
        raise ValueError(
            f"record identifies {record.resource_key()}, not {key}")


class CloseStatus(Enum):
    """§5.5; everything but OPEN is terminal and immutable."""

    OPEN = "open"
    VERIFIED = "verified"
    INTEGRITY_FAILURE = "integrity_failure"
    UNSUPPORTED = "unsupported"


TERMINAL_CLOSE_STATUSES = frozenset(
    {CloseStatus.VERIFIED, CloseStatus.INTEGRITY_FAILURE,
     CloseStatus.UNSUPPORTED})


# --------------------------------------------------------------------------
# durable records
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SubjectSpec:
    """A provider-minted work subject (M3), durable so expansion resumes.

    The engine's authoritative domain is the durable state, so a subject
    the session did not start with — a subdivision child, a capture that
    arrived later — has to BE a fact before work can be offered on it.
    ``parameters`` is a sorted key/value tuple the minting provider reads
    back; core never interprets it (it is the provider's own schema, and
    keeping it opaque is what stops core from growing a subdivision
    algorithm it has no business owning).

    DECLARED, UNBUILT: no production provider mints one yet — PL5 (H4)
    owns that, and solve's ledger carries it as F-04 with its B8 row.
    """

    subject_id: SubjectId
    family: str
    parent: str | None = None
    parameters: tuple[tuple[str, str], ...] = ()

    def resource_key(self) -> ResourceKey:
        return subject_key(self.subject_id)

    def __post_init__(self) -> None:
        require_sorted_unique(tuple(name for name, _ in self.parameters),
                              "SubjectSpec.parameters")

    def parameter(self, name: str) -> str | None:
        return dict(self.parameters).get(name)


@dataclass(frozen=True)
class CloseRecord:
    """§5.5. Terminal statuses are immutable (the commit layer enforces)."""

    status: CloseStatus
    payload_sha256: str | None = None
    bytes_ref: BlobRef | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        # F-13's residue, made unrepresentable instead of runtime-checked
        # (user ruling 2026-08-13): the record names ONE payload two ways
        # — the end-to-end envelope sha and the sidecar content address —
        # and they are hashes of the same bytes, so a record where they
        # disagree is a state nothing could have minted. With this
        # invariant (enforced at construction = commit AND load), the
        # verify=True read at the one operator-handoff materialisation IS
        # the payload-sha check; no comparison machinery exists anywhere.
        if (self.payload_sha256 is not None and self.bytes_ref is not None
                and self.payload_sha256 != self.bytes_ref.sha256):
            raise ValueError(
                "CloseRecord names one payload two ways and they must "
                f"agree: payload_sha256 {self.payload_sha256} vs "
                f"bytes_ref {self.bytes_ref.sha256}")

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_CLOSE_STATUSES


# --------------------------------------------------------------------------
# core's record families (registered by the composition root)
# --------------------------------------------------------------------------


def _subject_collections(key: ResourceKey,
                         record: SubjectSpec) -> tuple[ResourceKey, ...]:
    return (subject_collection_key(record.family),)


def _subject_transition(key: ResourceKey, current: Record,
                        proposed: Record) -> None:
    """F-08: a minted subject is FROZEN under its name.

    Work identities and spends stand on the subject a descriptor names
    (M3); parameters that move under a standing id would silently re-aim
    every one of them. A provider that derives a different subject mints
    a different id. Raises ``RegistryError`` — the registry's own refusal
    type — because this module sits below ``commit`` in core's import
    order and a transition refusal is a registry-declared rule anyway.
    """
    if isinstance(current, SubjectSpec) and proposed != current:
        raise RegistryError(
            f"{key}: a minted subject is frozen (F-08); a different "
            "subject is a different id")


#: NEITHER family declares references (F-07's relational half), and both
#: reasons are structural rather than "not yet". ``SubjectSpec.parent`` is
#: an opaque ``str`` a provider chose (core never interprets a subject's
#: parameters, and the parent rides the same rule) — there is no key here
#: to resolve, and inventing one would be core growing an opinion about a
#: provider's subdivision algebra. ``CloseRecord`` names a payload by
#: content address, which is BULK: dangling bulk is the wall's own
#: separate check (``commit._require_bulk_present``), and the record names
#: no keyed record at all.
#: ``CloseRecord`` declares NO transition on purpose (F-08): its law —
#: OPEN is replaceable, a terminal status freezes the whole session — is
#: the commit wall's own terminality check (§5.5), one wall, stated once.
#: ``SubjectSpec`` adopts :func:`require_own_key` (F-07): the subject id
#: IS the key, and a subject stored under someone else's name would
#: re-aim every descriptor and spend that resolves it (M3). ``CloseRecord``
#: takes no key check because it HAS no key parts — the session's close is
#: the singleton ``CLOSE_KEY``, and the kind guard at the wall is already
#: the whole of its identity.
RECORD_FAMILIES: tuple[RecordFamily, ...] = (
    RecordFamily(SubjectSpec, KIND_SUBJECT, version=1, structural=True,
                 validate=require_own_key,
                 transition=_subject_transition,
                 collections=_subject_collections),
    RecordFamily(CloseRecord, KIND_CLOSE, version=1),
)

__all__ = [
    "AttemptIdentity", "BlobRef", "CLOSE_KEY", "CloseRecord", "CloseStatus",
    "KIND_CLOSE", "KIND_COLLECTION", "KIND_SUBJECT", "MalformedKeyError",
    "RECORD_FAMILIES", "Record", "ResourceKey", "SubjectSpec",
    "TERMINAL_CLOSE_STATUSES", "blob_refs", "collection_key",
    "require_own_key", "require_sorted_unique", "subject_collection_key",
    "subject_key",
]
