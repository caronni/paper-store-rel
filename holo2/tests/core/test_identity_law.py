"""The identity law, hash-free: a work id is values, and values injure no one.

Root DESIGN §6 (user ruling 2026-08-11): a durable identity IS its
defining values, kept structured, never digested and never flattened
into a delimited string. This file is the adversarial half for core's own
id — the ``WorkId`` the spend ledger, the subscription index and the
ready queue key on — and for :func:`key_parts`, the one renderer every
structured key is built with. The record keys' half is
``tests/solve/test_key_injectivity.py``, where the packages that own
those records live.

Two collision families, both verified against the pre-law code:

1. **the kind drop** — the old ``work_id`` fell back to the subject's
   KIND when its parts were empty, so a close descriptor
   (``close`` / no parts) and a tile-shaped subject whose single part
   was the word ``close`` rendered identically;
2. **the unescaped join** — parts were joined with ``/``, and the scope
   tag with ``/`` again, so ``("a/b",)`` and ``("a", "b")`` were one
   name, as were ``profile="a/b"`` and ``profile="a", arm="b"``.

Each test builds the pair whose FLAT rendering still coincides — the
display rendering is allowed to, and does — and asserts that the
identity does not.
"""
from __future__ import annotations

import math

import pytest

from holo2.core import ResourceKey, WorkId, WorkScope, key_parts
from holo2.core.work import WorkDescriptor


def _flat(work_id: WorkId) -> str:
    """The DISPLAY rendering — collision-free is not promised here."""
    return str(work_id)


def test_the_kind_drop_collision_is_unrepresentable() -> None:
    """The review's own pair (P1): two KINDS, one set of parts.

    ``ResourceKey("tile", ("same",))`` and
    ``ResourceKey("window", ("same",))`` rendered as one name, because the
    old id dropped the kind whenever the key had parts.
    """
    tile = WorkDescriptor(family="f", subject=ResourceKey("tile", ("same",)),
                          route="r")
    window = WorkDescriptor(family="f",
                            subject=ResourceKey("window", ("same",)),
                            route="r")
    assert _flat(tile.work_id) == _flat(window.work_id)    # the OLD id, equal
    assert tile.work_id != window.work_id                  # the identity, not
    assert len({tile.work_id, window.work_id}) == 2        # and it hashes so


def test_the_empty_parts_fallback_collision_is_unrepresentable() -> None:
    """The same drop from the other side: no parts fell back to the kind."""
    close = WorkDescriptor(family="f", subject=ResourceKey("close", ()),
                           route="r")
    named = WorkDescriptor(family="f", subject=ResourceKey("tile", ("close",)),
                           route="r")
    assert _flat(close.work_id) == _flat(named.work_id)
    assert close.work_id != named.work_id


@pytest.mark.parametrize("left,right", [
    (("a/b", "c"), ("a", "b/c")),      # the review's own pair, verbatim
    (("a/b",), ("a", "b")),
])
def test_the_unescaped_join_collision_is_unrepresentable(
        left: tuple[str, ...], right: tuple[str, ...]) -> None:
    """Review pair 2: the parts were joined with an unescaped delimiter."""
    first = WorkDescriptor(family="f", subject=ResourceKey("k", left),
                           route="r")
    second = WorkDescriptor(family="f", subject=ResourceKey("k", right),
                            route="r")
    assert _flat(first.work_id) == _flat(second.work_id)
    assert first.work_id != second.work_id


def test_deleting_the_unwritten_scope_field_renamed_no_work() -> None:
    """W-B/B2: ``incumbent`` left, and every id in flight kept its spelling.

    The ruling's whole premise — deleting a declared-but-never-written
    scope field is FREE — rests on :attr:`WorkScope.tag` skipping empty
    parts, so a scope that never set the field rendered then exactly as it
    renders now. The literals below are the pre-deletion spellings,
    transcribed from the three-field build; if a future field lands in the
    middle of the tag or the id, this is where it shows.
    """
    scope = WorkScope(profile="p7", arm="a1")
    assert scope.tag == "p7/a1"
    assert WorkScope().tag == ""
    assert WorkScope(profile="p7").tag == "p7"
    work_id = WorkId("payload", ResourceKey("tile", ("0", "12", "40", "K")),
                     "scan", scope)
    assert str(work_id) == "payload:0/12/40/K@scan#p7/a1"
    assert str(WorkId("close", ResourceKey("close", ()), "consult")) == (
        "close:close@consult")


def test_the_scope_tag_collision_is_unrepresentable() -> None:
    """The same join, one level in: the scope's two fields stay two."""
    subject = ResourceKey("k", ("s",))
    one = WorkDescriptor(family="f", subject=subject, route="r",
                         scope=WorkScope(profile="a/b"))
    two = WorkDescriptor(family="f", subject=subject, route="r",
                         scope=WorkScope(profile="a", arm="b"))
    assert _flat(one.work_id) == _flat(two.work_id)
    assert one.work_id != two.work_id


@pytest.mark.parametrize("family,route,scope", [
    ("f@r", "x", WorkScope()),                 # the route delimiter, in a family
    ("f", "r#p", WorkScope()),                 # the tag delimiter, in a route
    ("f", "r", WorkScope(profile="p@q")),      # and in the scope
])
def test_a_delimiter_inside_a_field_names_nothing_else(
        family: str, route: str, scope: WorkScope) -> None:
    """Every field stays a field: there is nothing for a delimiter to split."""
    subject = ResourceKey("k", ("s",))
    mine = WorkDescriptor(family=family, subject=subject, route=route,
                          scope=scope).work_id
    plain = WorkDescriptor(family="f", subject=subject, route="r").work_id
    assert mine != plain
    assert WorkId.from_json(mine.to_json()) == mine       # and it round-trips


def test_a_malformed_work_id_is_refused_on_the_way_in() -> None:
    from holo2.core import MalformedKeyError

    # The scope arity is part of the wire (W-B/B2 narrowed it from three
    # fields to two): a three-part scope is a foreign state, not a work id
    # this build can mint.
    for raw in ([], ["f", ["k"], "r"], ["f", ["k"], "r", ["a"]],
                ["f", ["k"], "r", ["a", "b", "c"]],
                ["f", ["k"], 3, ["a", "b"]]):
        with pytest.raises(MalformedKeyError):
            WorkId.from_json(raw)


def test_the_recipe_entry_is_provenance_and_not_identity() -> None:
    """A subject offered by two entries is ONE piece of work (M1)."""
    subject = ResourceKey("k", ("s",))
    first = WorkDescriptor(family="f", subject=subject, route="r", entry="a")
    second = WorkDescriptor(family="f", subject=subject, route="r", entry="b")
    assert first.work_id == second.work_id


def test_work_ids_order_and_hash_as_values() -> None:
    """The queue heaps them and the ledger keys on them (§7)."""
    subject = ResourceKey("k", ("s",))
    ids = [WorkId("b", subject, "r"), WorkId("a", subject, "r"),
           WorkId("a", subject, "q")]
    assert sorted(ids) == [WorkId("a", subject, "q"),
                           WorkId("a", subject, "r"),
                           WorkId("b", subject, "r")]
    assert len(set(ids)) == 3


def test_key_parts_render_values_canonically() -> None:
    assert key_parts("s", 12, -3) == ("s", "12", "-3")
    assert key_parts(0.1 + 0.2) == (repr(0.30000000000000004),)
    assert float(key_parts(1 / 3)[0]) == 1 / 3         # repr round-trips
    with pytest.raises(TypeError):
        key_parts(True)                                # a flag is not a value
    with pytest.raises(TypeError):
        key_parts(object())
    with pytest.raises(ValueError):
        key_parts(math.nan)


def test_providers_identity_is_ordered_and_refuses_a_duplicate() -> None:
    """Order is arbitration (first-wins), so the identity keeps it."""
    from holo2.core import ProtocolViolation, providers_identity

    class _Provider:
        family = "f"
        sources = ()

        def __init__(self, provider_id: str) -> None:
            self.provider_id = provider_id

        def expand(self, view, request):        # pragma: no cover - unused
            return ()

        def worker(self, view, descriptor):     # pragma: no cover - unused
            return None

    assert providers_identity(
        [_Provider("b"), _Provider("a")]) == ("b", "a")
    with pytest.raises(ProtocolViolation, match="bound twice"):
        providers_identity([_Provider("a"), _Provider("a")])
