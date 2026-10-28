"""What ``core.keys`` publishes: the field validators, and ``KeySpec``.

``require_sorted_unique`` was the first: a rule the records could not each
re-spell without one of them drifting. These are the other two the tree
was writing out by hand at every capture-identity wall — a scale that
must be a positive real, and the one lowercase 64-digit spelling of a
SHA-256. ``capture.CaptureRecord`` adopts both. ``capture/scan.py`` does
NOT and may not: it is a carried leaf whose executable code is pinned
byte-for-byte against the legacy receiver's
(``tests/holo2_oracles/test_oracle_carry_source``) and whose refusal TEXT is
compared string for string, so its two copies are the carry, not a
duplicate somebody forgot.

The second half pins the SLOT MODEL itself — that an embed is checked for
kind and arity, that a parse is total past the arity check, and that slot
order is honoured wherever a kind puts its embed. The byte-identity of
solve's own key spellings under it is pinned where those keys live
(``tests/solve/test_key_injectivity.py``).
"""
from __future__ import annotations

import numpy as np
import pytest

from holo2.core import MalformedKeyError, ResourceKey
from holo2.core.keys import (KeyEmbed, KeyField, KeySpec, build_key, parse_key,
                             require_finite_positive, require_sha256_hex,
                             require_sorted_unique)


@pytest.mark.parametrize("value", [1, 4800.0, np.float64(2.5), 1e-9])
def test_a_positive_real_scale_passes(value: float) -> None:
    require_finite_positive(value, "dpi")


@pytest.mark.parametrize("value", [
    0, -1.0, float("nan"), float("inf"), float("-inf"),
    True, np.bool_(True),
])
def test_a_scale_that_is_not_a_positive_real_is_refused(value: float) -> None:
    """A bool is not a number here, and NaN passes every bound silently."""
    with pytest.raises(ValueError, match="dpi must be finite and positive"):
        require_finite_positive(value, "dpi")


def test_the_one_sha256_spelling_passes() -> None:
    require_sha256_hex("ab" * 32, "source_sha256")


@pytest.mark.parametrize("value", [
    "AB" * 32,                      # uppercase is a different id
    "ab" * 31,                      # short
    "ab" * 32 + "cd",               # long
    "gg" * 32,                      # not hex
    "",
])
def test_anything_but_that_spelling_is_refused(value: str) -> None:
    with pytest.raises(ValueError, match="64 lowercase hex digits"):
        require_sha256_hex(value, "source_sha256")


def test_the_sorted_unique_rule_is_unchanged() -> None:
    require_sorted_unique(("a", "b"), "observed_by")
    with pytest.raises(ValueError, match="sorted and unique"):
        require_sorted_unique(("b", "a"), "observed_by")
    with pytest.raises(ValueError, match="sorted and unique"):
        require_sorted_unique(("a", "a"), "observed_by")


# --------------------------------------------------------------- KeySpec

INNER = KeySpec("inner", (KeyField("name"), KeyField("count", cast=int)))
#: The embed sits in the MIDDLE here on purpose: slot order is the spec's
#: data because the tree's real kinds disagree about it.
OUTER = KeySpec("outer", (
    KeyField("lead"), KeyEmbed("inner", "inner", INNER.arity),
    KeyField("extent", 2, cast=int)))


def test_a_spec_states_its_own_arity() -> None:
    assert INNER.arity == 2
    assert OUTER.arity == 1 + INNER.arity + 2


def test_an_embed_rides_at_its_declared_position() -> None:
    inner = build_key(INNER, name="a", count=3)
    outer = build_key(OUTER, lead="f", inner=inner, extent=(4, 5))
    assert outer == ResourceKey("outer", ("f", "a", "3", "4", "5"))
    assert parse_key(OUTER, outer) == {
        "lead": "f", "inner": inner, "extent": (4, 5)}


def test_a_mis_kinded_or_mis_sized_embed_is_refused_not_absorbed() -> None:
    """The guard the per-kind builders each used to spell out by hand."""
    with pytest.raises(MalformedKeyError, match="not an inner key"):
        build_key(OUTER, lead="f", inner=ResourceKey("other", ("a", "3")),
                  extent=(4, 5))
    with pytest.raises(MalformedKeyError, match="not an inner key"):
        build_key(OUTER, lead="f", inner=ResourceKey("inner", ("a",)),
                  extent=(4, 5))


def test_a_multi_part_field_must_bring_exactly_its_parts() -> None:
    with pytest.raises(MalformedKeyError, match="outer.extent is 2 values"):
        build_key(OUTER, lead="f", inner=build_key(INNER, name="a", count=3),
                  extent=(4, 5, 6))


def test_a_parse_checks_arity_first_and_kind_with_it() -> None:
    with pytest.raises(MalformedKeyError, match="not an outer key"):
        parse_key(OUTER, ResourceKey("outer", ("f",)))
    with pytest.raises(MalformedKeyError, match="not an outer key"):
        parse_key(OUTER, ResourceKey("inner", ("f", "a", "3", "4", "5")))


def test_a_part_that_is_not_the_number_its_slot_declares_is_malformed() -> None:
    """The one fallible step past the arity check, and it says so."""
    with pytest.raises(MalformedKeyError, match="not an inner key"):
        parse_key(INNER, ResourceKey("inner", ("a", "three")))
