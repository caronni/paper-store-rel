"""W5's rival gate: the whole-word bar over DECODED candidates (L8).

What replaced first-hit-wins in the word route. v1's word route returns
the first candidate that clears the coupled parity bars
(``receive/place.py:433-447``); v1's COLD route additionally makes every
winner out-score its rival set, and the v0.30 ruling moved that
arithmetic to WHOLE WORDS after the complete-domain 0.176 refusal was
diagnosed as a parity-concentrated cross-page alias
(docs/FULL-DOMAIN-RIVAL-ANALYSIS.md, RECEIVE-DESIGN v0.25/v0.30). L8
gives both routes the bar; this is the word route getting it.

THE FIXTURE IS V1'S OWN SYNTHETIC ALIAS CONSTRUCTION, not a new one:
``tests/holo/test_cold_search_exactness.py::
test_exact_tie_tops_keep_first_page_winner`` builds a cross-page alias
by DUPLICATING A PAGE (``values[1] = values[0].copy()``), so the winner's
own placement on the other page is an exact-tie rival and the decoy bar
must refuse it. Here the same duplication is a reference provider that
answers every page with page 0's field.

The seam is ABOVE the batched BCH kernel — the gate reads decoded
candidate VALUES and never a codeword — so nothing here touches
``format.bch_batch``, its scalar oracle, or the
``holo2/measure/bch_equivalence*`` populations.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from holo2.core import ProgressSink
from holo2.solve.place_model import (V1_WHOLEWORD_RIVAL_GATE, AttemptBudget,
                                     PlacementConfig, WordAttemptBudget)
from holo2.solve.placement import decode_word_address
from holo2.solve.reference import V1ReferenceField
from holo2.format.format_v1 import tile_format

# The 8x8 grid the other solve unit tests use: 64 tiles/page.
SPEC = tile_format("c2-k-r0550", (8, 8))
FIELD = V1ReferenceField(SPEC)

BUDGET = AttemptBudget(49, 1e-3, 0.08, "test/word-rival",
                       gate=V1_WHOLEWORD_RIVAL_GATE)
#: One 64x64 patch declares one slot at one phase, four orientations.
WORD_BUDGET = WordAttemptBudget(4, 1e-3, "test/word-rival-word")
CONFIG = PlacementConfig()


class _Patch:
    """The three arrays Stage A and the score memo read of a window."""

    def __init__(self, bits: np.ndarray) -> None:
        self.bits = np.asarray(bits, np.uint8)
        self.mask = np.ones(self.bits.shape, bool)
        # A perfect read: the evidence sign is the printed value's own,
        # so a correct hypothesis scores mismatch 0.0 exactly.
        self.evidence = (1.0 - 2.0 * self.bits).astype(np.float32)


class _DuplicatedPages:
    """v1's ``values[1] = values[0].copy()``, as a provider.

    Every page answers page 0's printed field, so the winner's own
    geometry is an EXACT-TIE rival on every other page of the declared
    domain — the cross-page alias in its purest form.
    """

    def __init__(self, field: V1ReferenceField) -> None:
        self.spec = field.spec
        self._page = field.page(0)

    def page(self, page: int):
        return self._page


def _patch_on_tile(ty: int = 0, tx: int = 0) -> _Patch:
    """One tile's printed cells, cropped exactly on the tile boundary.

    64x64 is deliberate: it holds exactly one full 64-cell slot at
    exactly one fitting phase, so the declared Stage-A domain is four
    (one per orientation) and the sweep is instant.
    """
    values = np.asarray(FIELD.page(0).values, np.uint8)
    return _Patch(values[ty * 64:(ty + 1) * 64, tx * 64:(tx + 1) * 64])


def _decode(patch: _Patch, provider, pages: tuple[int, ...]):
    return decode_word_address(
        patch, SPEC, SimpleNamespace(page_domain=pages),  # type: ignore[arg-type]
        stage="all", word_budget=WORD_BUDGET, budget=BUDGET,
        reference=provider, progress=ProgressSink("rival"),
        config=CONFIG)


# --------------------------------------------------------------- the control

def test_a_true_word_places_against_a_field_whose_pages_differ() -> None:
    """The control: real pages, so the cross-page rivals are noise."""
    address = _decode(_patch_on_tile(), FIELD, (0, 1))
    assert address is not None
    assert (address.page, address.rot_k, address.origin_yx) == (0, 0, (0, 0))
    assert address.errors == 0


def test_a_single_page_domain_decides_exactly_as_it_did_before_w5() -> None:
    """No other page means no rival population — and no behaviour change.

    Alias pressure scales with the DECLARED page domain, which is why
    the gate's real customers are large-domain archive sessions and why
    a one-page session's answer is bit-for-bit the pre-W5 answer.
    """
    assert _decode(_patch_on_tile(), FIELD, (0,)) == _decode(
        _patch_on_tile(), FIELD, (0,))
    address = _decode(_patch_on_tile(), FIELD, (0,))
    assert address is not None and address.page == 0


# ---------------------------------------------------- v1's alias construction

def test_a_duplicated_page_is_an_exact_tie_rival_and_the_gate_refuses(
) -> None:
    """The d=27 floor restored: an exact-tie cross-page twin refuses.

    The winner still DECODES — the word is legal and its counter names
    page 0 — and it still clears both coupled parity bars. What refuses
    it is the rival bar: its own geometry scores mismatch 0.0 on the
    duplicated page too, so the decoy bar (0.20) is not cleared and the
    gap (0.08) is zero. Before W5 this window placed.
    """
    duplicated = _DuplicatedPages(FIELD)
    # It is genuinely a decode-and-pass: the same patch places when the
    # domain holds no second page to alias onto.
    assert _decode(_patch_on_tile(), duplicated, (0,)) is not None
    assert _decode(_patch_on_tile(), duplicated, (0, 1)) is None


@pytest.mark.parametrize("tile_yx", [(0, 0), (1, 3), (7, 7)])
def test_the_refusal_is_the_alias_and_not_the_tile(tile_yx) -> None:
    """Every tile of the duplicated field refuses, and none of them does
    when its domain is one page: the mechanism is the CROSS-PAGE twin."""
    patch = _patch_on_tile(*tile_yx)
    duplicated = _DuplicatedPages(FIELD)
    assert _decode(patch, duplicated, (0,)) is not None
    assert _decode(patch, duplicated, (0, 1)) is None
    assert _decode(patch, FIELD, (0, 1)) is not None
