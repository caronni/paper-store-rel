"""The reading set as POLICY DATA (H4-LANES stage 1).

The engine's half of the wall ``test_cost_vocabulary`` already guards:
which rungs of a capture actually place is declared on the recipe's
placement entries, and ``solve`` reads it without being allowed to import
the word. So the same two obligations apply — the spellings must be one
vocabulary, and the value must be identity-bearing — plus one that is
this field's own: a recipe may not declare two of them.

WHY IT IS IDENTITY-BEARING AND NOT A KNOB. The entries land in
``SessionIdentity`` as data (the hash-free identity law, 2026-08-11), so
a run that starts reading two rungs is a whole-value mismatch against a
state built reading one, and ``Store.open`` refuses it rather than
reinterpreting the evidence under a policy it was not built with. That is
the difference between this and ``working_footing_id``, which made the
same decision silently, once, for every lineage, with nothing durable
saying which decision it was.
"""
from __future__ import annotations

from dataclasses import replace

import pytest

from holo2.engine import recipe
from holo2.format.registry_rows import format_row
from holo2.solve import place_shared


def test_the_two_spellings_of_the_reading_set_are_one_vocabulary() -> None:
    """The third wall-crossing of ``test_cost_vocabulary``'s kind.

    ``solve.place_shared`` decides per window whether a rung places and
    may not import the engine to learn the word; a drift here would make
    every reading set unknown, and an unknown reading set places NOTHING
    — the whole receiver would go quietly dark rather than loudly wrong.
    """
    assert place_shared.READING_FINEST == recipe.READING_FINEST
    assert place_shared.READING_ALL == recipe.READING_ALL
    assert place_shared.READING_SETS == {recipe.READING_FINEST,
                                         recipe.READING_ALL}


def test_recipe_v1_reads_the_whole_ladder() -> None:
    """Stage 2's default flip, which is the wave.

    MOVED PIN, and the cause is the wave itself: stage 1 declared
    ``finest`` so the plumbing could land behaviour-neutral, and stage 2
    turns the cascade on. What did NOT move is that the value is DATA —
    the assertion is still over the entries, not over a constant.
    """
    assert recipe.RECIPE_V1.reading_set == recipe.READING_ALL
    assert all(entry.reading_set == recipe.READING_ALL
               for entry in recipe.RECIPE_V1.entries)


def test_the_finest_only_lineage_survives_the_default_flip() -> None:
    """The reading the receiver had before this wave is still SAYABLE.

    A default that deletes its predecessor is a default that cannot be
    compared against, and this one has to be: ``RECIPE_V1_FINEST`` is
    the configuration v1's own placement is measured against and the one
    a run reaches for when a coarse lane is known to be worthless. It is
    the same recipe with one field moved on the placement entries, so it
    forks by value like any other policy change.
    """
    finest = recipe.RECIPE_V1_FINEST
    assert finest.reading_set == recipe.READING_FINEST
    assert finest.entries != recipe.RECIPE_V1.entries
    assert finest.label != recipe.RECIPE_V1.label
    # Nothing ELSE moved: same task classes, selectors, gates and prices.
    for narrow, wide in zip(finest.entries, recipe.RECIPE_V1.entries):
        assert replace(narrow, reading_set=wide.reading_set) == wide
    # And the composition root really binds it FROM the recipe: hand it
    # this one and the scheduler reads one lane.
    from holo2.cli import real_source
    row = format_row("c3-k-r0550", (2, 2), 1)
    assert real_source(row, finest).reading_set == recipe.READING_FINEST
    assert real_source(row).reading_set == recipe.READING_ALL


def test_a_moved_reading_set_forks_the_lineage_by_value() -> None:
    """No label to remember to bump: the entries ARE the identity."""
    narrowed = recipe.Recipe(label=recipe.RECIPE_V1.label, entries=tuple(
        replace(entry, reading_set=recipe.READING_FINEST)
        if entry.task_class == recipe.TASK_PLACE else entry
        for entry in recipe.RECIPE_V1.entries))
    assert narrowed.reading_set == recipe.READING_FINEST
    # The whole-value compare ``Store.open`` makes on resume.
    assert narrowed.entries != recipe.RECIPE_V1.entries


def test_a_recipe_declares_one_reading_set_for_placement() -> None:
    """Which rungs are read is a property of the RUN, not of an entry.

    The scheduler is composed ONCE and admits from every placement entry,
    so two entries disagreeing is a recipe that cannot be executed — not
    a precedence puzzle for the composition root to guess at.
    """
    place = [index for index, entry in enumerate(recipe.RECIPE_V1.entries)
             if entry.task_class == recipe.TASK_PLACE]
    assert len(place) == 2, "recipe v1 declares two placement entries"
    entries = list(recipe.RECIPE_V1.entries)
    entries[place[0]] = replace(entries[place[0]],
                                reading_set=recipe.READING_FINEST)
    with pytest.raises(ValueError, match="ONE reading set"):
        recipe.Recipe(label="split", entries=tuple(entries))


def test_an_unknown_reading_set_is_refused_at_construction() -> None:
    """The vocabulary is validated where the gate and the selector are."""
    entries = list(recipe.RECIPE_V1.entries)
    entries[1] = replace(entries[1], reading_set="every-other-tuesday")
    with pytest.raises(ValueError, match="reading set"):
        recipe.Recipe(label="bogus", entries=tuple(entries))


def test_a_recipe_that_places_nothing_answers_the_default() -> None:
    """What a scheduler over no placement entries would read anyway.

    MOVED PIN, same cause as the flip above: "the default" is one answer
    everywhere, and it is the cascade now.
    """
    close = recipe.RECIPE_V1.close_entry
    ingest = recipe.RECIPE_V1.entries[0]
    assert recipe.Recipe(label="no-placement",
                         entries=(ingest, close)).reading_set == (
        recipe.READING_ALL)
