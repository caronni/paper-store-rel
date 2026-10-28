"""One total resolver from a format reference to its FormatSpec.

FORMAT-SPACE §10.  Every identity string the system can meet resolves
here, in strict precedence order:

1. ``L:<legacy-spec-id>`` — explicit fossil reference: byte-exact
   catalogue match (never parsed).
2. A bare legacy spec id — accepted for compatibility with persisted
   state files and the catalog registry (old sessions store bare ids);
   resolved through FORMAT_ROWS or the fossil catalogue, byte-exactly.
3. Anything else — the v2 grammar (normalizing parse).

Because fossil matching is byte-exact and the v2 grammar refuses legacy
spellings (no family token), the namespaces cannot shadow each other.
The resolver is total over every identity ever persisted, which is why
session state needs no schema change: ``format_row_id`` alone
reconstructs the spec.
"""
from __future__ import annotations

from .descriptor import FormatSpec
from .fossils import FOSSILS, is_fossil_ref, resolve_fossil_spec, \
    strip_fossil_ref
from .lattice import parse_format_id
from .registry import FORMAT_ROWS


def resolve_format_ref(ref: str) -> FormatSpec:
    """A format reference (L: fossil, legacy spec id, or v2 format id)
    -> its exact FormatSpec.  Raises ValueError with the failing route's
    diagnosis."""
    if is_fossil_ref(ref):
        return resolve_fossil_spec(strip_fossil_ref(ref))
    row = FORMAT_ROWS.get(ref)
    if row is not None:
        return row
    if ref in FOSSILS:
        return resolve_fossil_spec(ref)
    try:
        return parse_format_id(ref)
    except ValueError as exc:
        raise ValueError(
            f"format reference {ref!r} is neither a fossil (L:), a "
            f"catalog row, nor a lawful v2 format id: {exc}") from None


__all__ = ["resolve_format_ref"]
