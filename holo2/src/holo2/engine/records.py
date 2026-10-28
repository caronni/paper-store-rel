"""RECORDS engine owns: the session identity (§5.1).

One family, and it is not a keyed resource — it is the **envelope
header**, frozen when the session is created and never rewritten. The
engine writes it (``open_session`` names the lineage a run belongs to), so
the engine owns its schema; the store reads it back through the registry
like any other record and refuses a state whose identity differs from the
one a run declares (there are no migration decoders, §10.4).

``kind=None`` on the family is what marks it as the header: it has no
``ResourceKey``, exactly one family in a registry may claim that, and the
store uses it to decode ``envelope["session"]``.

**It binds the executable policy BY VALUE** (the hash-free identity law,
2026-08-11). The recipe's entries — task classes, footing selectors,
gates, prices, arms — and the ORDERED provider ids are fields here, so
resuming under a moved policy is a whole-value mismatch the store
refuses by itself, exactly as the declared page domain and the format row
already were. What died with it is the ``recipe_id``/``Recipe.identity``
duality: there is no hand-bumped label to forget to bump, and no digest
standing in for data the record can simply hold.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core import RecordFamily
from .recipe import RecipeEntry


@dataclass(frozen=True)
class SessionIdentity:
    """§5.1. Not a resource: the envelope header, frozen at creation."""

    format_row_id: str
    receiver_policy_id: str
    recipe_entries: tuple[RecipeEntry, ...]
    providers: tuple[str, ...]
    page_domain: tuple[int, ...]


#: The header declares no references (F-07's relational half) because it
#: is not stored at a key at all: it is frozen at creation, before any
#: record exists, and it names its lineage BY VALUE — recipe entries,
#: provider ids, page domain — rather than by pointing at records. There
#: is nothing here that could dangle.
RECORD_FAMILIES: tuple[RecordFamily, ...] = (
    RecordFamily(SessionIdentity, None, version=2),
)

__all__ = ["RECORD_FAMILIES", "SessionIdentity"]
