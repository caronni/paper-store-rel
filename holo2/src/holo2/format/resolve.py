"""One total resolver from a format reference to the printed row.

FORMAT-SPACE §10, carried by WP-1.2 (2026-08-22, RULINGS B5) and cut
down to TWO ROUTES by C2 the same day (RULINGS G1).  Every identity
string holo2 can meet resolves here:

1. ``L:<legacy-spec-id>`` — the legacy namespace: a byte-exact
   catalogue match, never parsed.
2. Anything else — the v2 grammar (normalizing parse).

**The bare-legacy route is gone**, and that is the ruling, not an
omission: "the only real legacy mechanism are the L: lines".  A legacy
identity is spelled ``L:`` on every holo2 surface — the CLI, a
``row_id``, a persisted ``SessionIdentity.format_row_id``, a
``CloseSpec.spec_id``, a policy id, diag — so a bare legacy spelling
cannot arrive from anywhere holo2 wrote it, and accepting one would
mean maintaining a second spelling of every printed sheet for the sake
of strings holo2 no longer produces.  A bare spelling therefore refuses
BY NAME, with the ``L:`` form it should have had.

The freshness consequence is stated and accepted (RULINGS G1, "happy
with the freshness doctrine"): a holo2 state directory written before
2026-08-22 stores a bare ``format_row_id`` and will refuse at identity
when a resume reads it back.  Every such state is regenerable —
holo2 has no archived sessions, only re-runnable ones — and the
alternative is a permanent second name for every sheet.

**Precedence is still the load-bearing mechanism.**  ``src/holo``'s
docstring argues the namespaces cannot shadow each other because the v2
grammar "refuses legacy spellings (no family token)"; that is true of
legacy K ids and false of legacy COLOUR ids, which do carry a family
token and are refused for other reasons.  holo2 states the honest
version: the ``L:`` marker selects the route before any parsing
happens, so a legacy string can never reach the parser at all.

**Why totality matters.**  The e033 §033.5 incident: an off-catalog
colour resume died at "stream 'M' is not declared" because a row id
only meant something if a table in that build still held the row, and
the log's own epitaph is that "K states at this geometry (e029)
survived by luck".  A resolver total over every identity holo2 can
WRITE is what lets session state stay schema-7 — a persisted
``format_row_id`` alone reconstructs the row.

Two functions, two jobs.  :func:`resolve_format_ref` answers *which
identity is this, and by which route* without building anything: the
canonical spelling it returns is what a caller must persist, what an
operator should be shown when their spelling was not canonical (the
``format <display> -> state <canonical>`` echo is the CLI's), and —
because it carries the ``L:`` marker for a legacy identity — a valid
reference in its own right, so resolving a resolved id is a fixed point.
:func:`format_row_for` is the door: resolve, build through the ordinary
constructor, and byte-verify the result against the route's answer —
the two-witness discipline applied to every reference, not only to the
catalogue's own entries.  For the legacy route that build-and-verify
already exists, as ``fossils.resolve_fossil_spec``, so the door
delegates to it rather than spelling a second one.

Refusals are builtins (``ValueError``/``KeyError``) carrying the failing
route's diagnosis; ``holo2/tests/test_error_taxonomy.py`` derives the
declared exception set from a package's ``__all__``, so a custom class
here would be API kept alive by its own pin.
"""
from __future__ import annotations

from dataclasses import dataclass

from .fossils import FOSSILS, LEGACY_REFS, get_fossil, resolve_fossil_spec
from .lattice import is_fossil_ref, parse_format_id, strip_fossil_ref
from .registry_rows import FormatRowSpec, make_format

#: The two routes, as data a caller can branch on or print.  The legacy
#: route's label IS its prefix: there is one legacy spelling now, and
#: naming the route after it keeps the two the same fact (RULINGS G1).
ROUTE_FOSSIL = "L:"
ROUTE_V2 = "v2"


@dataclass(frozen=True)
class ResolvedRef:
    """What a format reference names, before any row is built.

    ``spec_id`` is CANONICAL — and, for a legacy identity, ``L:``-marked
    — while ``seed`` is the row seed that spelling implies: the pair a
    caller persists and a caller verifies against.  ``display_id`` is the
    short spelling a person reads (FORMAT-SPACE §6): shown, never stored.  Because the marker
    rides on ``spec_id``, what this returns is itself a valid reference,
    so persisting it and resolving it again is a fixed point.  ``route``
    says which of the two doors answered, so a call site can report the
    legacy route rather than hide it.
    """

    route: str
    coding_id: str
    tiles_yx: tuple[int, int]
    spec_id: str
    display_id: str
    seed: bytes


def resolve_format_ref(format_ref: str) -> ResolvedRef:
    """A format reference -> the identity it names, by its marked route.

    Raises ``ValueError`` with the failing route's diagnosis (or the
    catalogue's ``KeyError`` with its near-miss list, for an ``L:``
    reference that names nothing).
    """
    if is_fossil_ref(format_ref):
        # The tile matrix is FROZEN DATA on the entry, not divided out
        # of its cells: a derivation from the record cancels the tile
        # constant and asserts nothing (``fossils`` states the argument).
        fossil = get_fossil(strip_fossil_ref(format_ref))
        return ResolvedRef(ROUTE_FOSSIL, fossil.coding_id, fossil.tiles_yx,
                           fossil.ref, fossil.ref, fossil.seed)
    try:
        parsed = parse_format_id(format_ref)
    except ValueError as exc:
        raise ValueError(
            f"format reference {format_ref!r} is not a lawful v2 format "
            f"id ({exc}){_legacy_hint(format_ref)}") from None
    return ResolvedRef(ROUTE_V2, parsed.coding_id, parsed.tiles_yx,
                       parsed.spec_id, parsed.display_id, parsed.seed)


def _legacy_hint(format_ref: str) -> str:
    """The sentence an operator holding a printed sheet's name needs.

    A bare legacy spelling is the ONE refusal that is not really an
    error: the string names a real sheet, it is simply spelled in the
    namespace holo2 stopped writing.  Saying so — and showing the
    ``L:`` forms — is the difference between a ruling and a dead end.
    """
    if format_ref in FOSSILS:
        return (f"; legacy identities are referenced as L:<id> — this one "
                f"is L:{format_ref}")
    near = sorted(ref for ref in LEGACY_REFS
                  if ref.split("@")[0] == "L:" + format_ref.split("@")[0])
    listing = near or list(LEGACY_REFS)
    return (f"; legacy identities are referenced as L:<id>, matched "
            f"byte-exactly: {listing}")


def format_row_for(format_ref: str, pages: int = 1) -> FormatRowSpec:
    """A format reference + a declared page count -> the printed row.

    The ``L:`` / v2 door.  The row is built through the ordinary
    constructor and then byte-verified against what the reference
    resolved to: if the recipe and the record ever disagree, the
    reference names one sheet and the row describes another, which is
    the class of fault that decodes a page to coin flips.

    ONE implementation per route (WP-1.2 review, 2026-08-22): the legacy
    route delegates to ``fossils.resolve_fossil_spec``, which is the
    catalogue's own build-and-verify and the site refusal row R4 names —
    the same delegation ``src/holo/format/resolve.py:32-38`` makes.
    Only the v2 route builds here, because only it has no catalogue to
    verify against.  It builds through ``make_format``, so a lawful
    COLOUR identity produces its row here like any other and is refused
    only where a colour codec is wanted (RULINGS G2).
    """
    resolved = resolve_format_ref(format_ref)
    if resolved.route != ROUTE_V2:
        return resolve_fossil_spec(resolved.spec_id, pages)
    row = make_format(parse_format_id(format_ref), pages)
    if row.row_id != resolved.spec_id or row.seed != resolved.seed:
        raise ValueError(
            f"format reference {format_ref!r} resolved to "
            f"{resolved.spec_id} ({resolved.seed!r}) but the row builds "
            f"{row.row_id} ({row.seed!r}) — one of them does not describe "
            f"this sheet")
    return row


__all__ = ["ROUTE_FOSSIL", "ROUTE_V2", "ResolvedRef", "format_row_for",
           "resolve_format_ref"]
