"""The total resolver: two routes, marked, byte-verified.

WP-1.2 (2026-08-22, RULINGS B2/B5), cut to two routes by C2 the same
day (RULINGS G1: "the only real legacy mechanism are the L: lines").
The refusal rows exercised here are R1-R5 of the catalogue in
``test_format_lattice.py``'s docstring.

What this file exists to prevent is one specific incident, recorded in
``experiments/033-xerox-rung-experiments.md`` §033.5: an off-catalog
resume that died at ``"stream 'M' is not declared"`` because a row id
only meant something if a table in that build still held the row.  The
log's epitaph — "K states at this geometry (e029) survived by luck" —
is the reason a resolver is worth a test module of its own: totality is
the property, not convenience.
"""
from __future__ import annotations

import dataclasses

import pytest

from holo2.format import fossils as fossils_module
from holo2.format import resolve as resolve_module
from holo2.format.fossils import FOSSILS, get_fossil
from holo2.format.lattice import strip_fossil_ref
from holo2.format.registry_rows import tile_format_for
from holo2.format.resolve import (ROUTE_FOSSIL, ROUTE_V2, format_row_for,
                                  resolve_format_ref)

#: The printed geometry: two hardware-certified volumes (e029 on the
#: M281, e032 on the AltaLink, 465,580 B byte-exact both times).  The
#: catalogue is keyed by the bare id; every REFERENCE to it is ``L:``.
PRINTED = "c2-r0700@3392x2368"
PRINTED_REF = "L:" + PRINTED


def test_the_two_routes_and_their_labels() -> None:
    """Each door answers, and says which door it was.

    Prevents the silent-route failure: a caller that cannot tell a
    legacy resolution from a v2 one cannot report the legacy route to an
    operator, and the visibility of that route is half the reason the
    ``L:`` prefix exists at all.
    """
    assert resolve_format_ref(PRINTED_REF).route == ROUTE_FOSSIL
    assert resolve_format_ref("c2-k-r0700@53x37").route == ROUTE_V2


def test_what_a_legacy_identity_resolves_to_is_a_reference() -> None:
    """``L:`` rides on the resolved spelling, so resolution is a fixed
    point (RULINGS G1, 2026-08-22).

    Prevents the round-trip fork: what a caller PERSISTS is
    ``ResolvedRef.spec_id``, and a resume feeds that string straight
    back in.  If the marker were stripped on the way out, the string
    holo2 wrote would be one holo2 refuses to read.
    """
    resolved = resolve_format_ref(PRINTED_REF)
    assert resolved.spec_id == PRINTED_REF
    assert resolve_format_ref(resolved.spec_id) == resolved
    assert resolved.seed == b"holo/v1/c2-r0700/3392x2368"
    assert resolved.coding_id == "c2-r0700"
    assert resolved.tiles_yx == (53, 37)


@pytest.mark.parametrize("spec_id", sorted(FOSSILS))
def test_totality_over_the_catalogue(spec_id: str) -> None:
    """Every catalogued identity resolves through its ``L:`` reference.

    Prevents a half-carried catalogue: an entry whose recipe no longer
    rebuilds it would be a printed sheet holo2 can name and cannot read.
    """
    ref = f"L:{spec_id}"
    resolved = resolve_format_ref(ref)
    assert resolved.spec_id == ref
    assert resolved.seed == FOSSILS[spec_id].seed
    row = format_row_for(ref, 1)
    assert row.row_id == ref
    assert row.seed == FOSSILS[spec_id].seed
    assert row.cells_yx == FOSSILS[spec_id].cells_yx


def test_a_bare_legacy_spelling_refuses_and_names_the_L_form() -> None:
    """R5: the one refusal that is not really an error (RULINGS G1).

    The string names a REAL printed sheet; it is simply spelled in the
    namespace holo2 stopped writing.  The fork this prevents is the
    opposite of a dead end: accepting it would mean every printed sheet
    keeps two names for ever, and the whole reason legacy ids are
    matched rather than parsed is that one sheet must have exactly one
    name.  So it refuses, and hands the operator the ``L:`` form.
    """
    with pytest.raises(ValueError) as exc:
        resolve_format_ref(PRINTED)
    message = str(exc.value)
    assert "legacy identities are referenced as L:<id>" in message
    assert PRINTED_REF in message
    # ...and the parser refused it on its own terms first, which is the
    # second line of defence, not the first.
    with pytest.raises(ValueError, match="unknown family"):
        from holo2.format.lattice import parse_format_id
        parse_format_id(PRINTED)


def test_the_row_is_byte_verified_against_the_route() -> None:
    """Two witnesses on every reference, not only on the catalogue.

    ``format_row_for`` resolves (the record) and then BUILDS (the
    recipe), and refuses if the two describe different sheets.  That is
    the class of fault that decodes a page to coin flips, so it is
    caught where both answers are still in hand.
    """
    row = format_row_for("c2-k-r0700@53x37", 1)
    resolved = resolve_format_ref("c2-k-r0700@53x37")
    assert row.row_id == resolved.spec_id
    assert row.seed == resolved.seed == \
        b"holo/v2/1i300-k-r0700-p100-v1@53x37"


def test_a_v2_reference_normalizes_on_the_way_through() -> None:
    """Non-canonical in, canonical out — and only canonical persists.

    Prevents the two-seeds-one-format fork: if a non-canonical spelling
    survived into a persisted ``format_row_id``, the same printed sheet
    would key two different AES keystreams depending on how an operator
    typed it.
    """
    resolved = resolve_format_ref("c2-k-r0700-p100-v1@53x37")
    assert resolved.spec_id == "1i300-k-r0700-p100-v1@53x37"
    assert resolved.display_id == "c2-k-r0700@53x37"
    assert format_row_for("2i600-k-r0700@53x37").row_id == \
        "1i300-k-r0700-p100-v1@53x37"


def test_pages_ride_on_the_row_not_on_the_identity() -> None:
    """A page count is not identity in either namespace (§11.5).

    Same reference, different ``--pages``: one seed, two declared
    domains.  Prevents the reverse mistake — folding the page count into
    the id and forking every multi-page sheet's keystream.
    """
    one = format_row_for(PRINTED_REF, 1)
    four = format_row_for(PRINTED_REF, 4)
    assert one.seed == four.seed and one.row_id == four.row_id
    assert one.page_domain == (0,) and four.page_domain == (0, 1, 2, 3)


# ------------------------------------------------------------- refusals

def test_an_unresolvable_reference_names_every_route_it_tried() -> None:
    """R1: the diagnosis, not just the verdict."""
    with pytest.raises(ValueError) as exc:
        resolve_format_ref("not-a-format")
    message = str(exc.value)
    assert "lawful v2 format id" in message      # the route that answered
    assert "L:<id>" in message                   # ...and the one that did not


def test_a_near_miss_lists_the_closest_catalogue_entries() -> None:
    """R2: byte-exact matching is unhelpful without a hint.

    A mistyped geometry on a real coding is the likely operator error,
    so the refusal shows which geometries of that coding DO exist.
    """
    with pytest.raises(KeyError, match="closest catalogue entries"):
        get_fossil("c2-r0700@9999x9999")
    with pytest.raises(KeyError) as exc:
        get_fossil("L:c2-r0700@9999x9999")
    assert "c2-r0700@3392x2368" in str(exc.value)


def test_stripping_a_bare_id_refuses() -> None:
    """R3: ``L:`` means the route was chosen, so it is not optional."""
    with pytest.raises(ValueError, match="not an L:-prefixed"):
        strip_fossil_ref(PRINTED)


def test_a_synthetic_legacy_geometry_refuses_by_name() -> None:
    """The DECLARED limit of RULINGS B2/G1, pinned so it stays declared.

    Legacy identities are matched, never inverse-parsed, so a legacy
    coding at an uncatalogued geometry does not resolve, in either
    spelling.  ``src/holo``'s resolver refuses the same class
    (``c2-r0550@3392x2368`` is a legal legacy identity there too, and is
    equally unresolvable).

    NOTHING MINTS ONE ANY MORE (C4, RULINGS G5, 2026-08-22).  Until then
    holo2's own synthetic fixtures did, through the private
    ``fossils._legacy_row`` bridge, and this refusal was the declared
    edge of a class the tree was itself producing.  The fixtures are v2
    identities now and the bridge is deleted, so the string below names
    nothing anybody can build — which is why the refusal is still pinned
    rather than dropped: a resume reading a stale identity back through
    this module is exactly where it becomes load-bearing.
    """
    with pytest.raises(ValueError, match="lawful v2 format id"):
        resolve_format_ref("c3-r0550@512x512")
    with pytest.raises(KeyError, match="unknown legacy identity"):
        resolve_format_ref("L:c3-r0550@512x512")


def test_a_forked_catalogue_entry_refuses_when_it_is_resolved(
        monkeypatch: pytest.MonkeyPatch) -> None:
    """R4: the byte-verify that fires when record and recipe part ways.

    The only way this message is ever SEEN, and therefore the only way it
    is known to be reachable.  ``_self_check`` proves recipe/record
    agreement for the shipped catalogue at import, so for a real entry
    R4 is unreachable afterwards — which is exactly why it needs a
    deliberately forked entry to be exercised at all.  The fork it
    prevents is a catalogue whose recipe has quietly moved under it: a
    printed identity that still resolves, and builds a different sheet.

    Patched at each module's attribute rather than in the table:
    ``FOSSILS`` is a read-only proxy on purpose (R2), and a test that
    could write to it would be pinning a mutability the surface does not
    have.  Both bindings, so the refusal is proved at its own site AND
    through the door that now delegates to it.
    """
    forked = dataclasses.replace(FOSSILS[PRINTED], seed=b"holo/v1/nope/1x1")
    monkeypatch.setattr(fossils_module, "FOSSILS", {PRINTED: forked})
    monkeypatch.setattr(resolve_module, "FOSSILS", {PRINTED: forked})
    with pytest.raises(AssertionError, match="reconstruction forked"):
        fossils_module.resolve_fossil_spec(PRINTED)
    with pytest.raises(AssertionError, match="reconstruction forked"):
        format_row_for(PRINTED_REF)


def test_a_lawful_colour_reference_builds_its_row() -> None:
    """Resolution is total, and so is CONSTRUCTION (RULINGS G2).

    holo2 can name sheet I's twin and now build its row: three streams,
    their frozen fountain domains, the pooled outer code.  What it
    cannot do is decode one, and that refusal lives at the K tile chain
    (``tile_format_for``), not here — which is the seam the colour port
    fills.
    """
    resolved = resolve_format_ref("c2-cmy8-r0700@53x37")
    assert resolved.route == ROUTE_V2
    assert resolved.seed == b"holo/v2/1i300-cmy8-r0700-p120-v1@53x37"
    row = format_row_for("c2-cmy8-r0700@53x37")
    assert row.stream_ids == ("C", "M", "Y")
    assert row.pooled_fountain is True
    with pytest.raises(ValueError, match="colour codecs arrive"):
        tile_format_for(row)
