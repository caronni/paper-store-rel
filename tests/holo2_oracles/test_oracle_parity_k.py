"""Pins the SILENT classifiers in ``holo2/measure/parity_k{,_report}.py``.

Lives here and not under ``holo2/tests`` for the same reason
``test_oracle_tile_differential.py`` does: ``parity_k`` imports ``holo``
at module level (it READS v1 states — RULING I5), and only
``tests/holo2_oracles/`` and ``measure/verdicts/test_v1_parity.py`` may
reach v1 (RULINGS §F). Self-contained: it builds its own minimal v1
``SessionState`` and reads the harness's own declared list; it never
decodes anything and never opens a state on disk.

THE TWO FORKS THIS PINS. Both are silent — they produce a
plausible-looking parity table on the real corpus and are wrong about
what the table MEANS.

1. **The flags column read off ONE capture's plan.** RULING I5 asks the
   harness to "record the run flags the state records", and v1 records
   them structurally: ``--mopup`` puts ``mopup`` lanes in a capture's
   plan and ``--refine`` puts ``refine`` lanes in it
   (``holo.receive.cascade.lane_kind``). A census that walked only
   ``state.captures[0].plan`` — the obvious shape, and indistinguishable
   from the right one on both single-capture real sheets — would report
   the NINE-capture demo state as ordinary-only, i.e. would claim v1 was
   NOT driven at full harvest on the one row where the claim decides
   whether the comparison is fair at all. The fixture below has two
   captures whose plans differ exactly there.

2. **A three-valued correctness statement collapsed to a boolean.**
   ``_zero_wrong`` answers ``None`` when there is no golden or no
   published payload — an arm whose volume cannot close (a two-sheet
   volume with one sheet on the platen) never claimed to close, and
   reporting it as ``False`` would print a WRONG-payload verdict against
   a run that behaved correctly, while reporting ``True`` would claim a
   sha comparison nobody made. Either collapse passes every test that
   only ever feeds it two equal shas.

3. **``_epilogue_int``'s ANCHOR** (added by the W4 review fixes,
   2026-08-23). It is the third silent classifier and it feeds two
   PUBLISHED columns of the refine-off table — commits and done cells.
   The done-cell count is the numerator inside the parentheses on the
   capture row (``capture … done coverage 97.4% (7823516/8030805
   cells)``), so the anchor must be the bracket: anchoring on the word
   ``coverage`` reads the PERCENT's leading digits instead and quietly
   publishes ``97`` where ``7823516`` belongs. Both mutants are
   plausible and neither is visible in the rendered table.

A fourth assertion pins the DECLARED LIST's own consistency rather than a
function: an arm may not carry both an archived v1 state and a fixture
recipe, because the two name different pixels (the archived state's
capture versus a freshly rendered page) and the harness would then
compare v1's harvest of one sheet against holo2's decode of another —
a parity row that looks ordinary and compares nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_ROOT / "src", _ROOT / "holo2" / "src",
              _ROOT / "holo2" / "measure"):
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

from holo.receive.session_model import CaptureRecord as V1Capture   # noqa: E402
from holo.receive.session_model import SessionState                 # noqa: E402
from holo.receive.types import LaneSpec                             # noqa: E402

import parity_k                                                     # noqa: E402
import parity_k_report                                              # noqa: E402

_SHA_A = "ab" * 32
_SHA_B = "cd" * 32


def _lane(lane_id: str, *, parent: str | None = None,
          mopup_of: str | None = None,
          refine_of: str | None = None) -> LaneSpec:
    """One plan row. ``parent`` is not decoration: ``CaptureRecord``
    validates that a persisted plan is ONE ordered parent chain
    (``session_model.py:149``), which is itself the reason the census
    below cannot be replaced by "look at the last lane" — the chain is
    ordered by lane, not by kind."""
    return LaneSpec(lane_id=lane_id, target_ppc_num=2, target_ppc_den=1,
                    native_per_view_num=1, native_per_view_den=1,
                    parent_lane_id=parent, mopup_of=mopup_of,
                    refine_of=refine_of)


def _capture(sha: str, plan: tuple[LaneSpec, ...]) -> V1Capture:
    return V1Capture(source_sha256=sha, dpi=600.0, dtype="uint8",
                     shape_yx=(100, 100), channels=1, plan=plan, levels=())


def _two_capture_state() -> SessionState:
    """Capture A: ordinary only. Capture B: the full harvest's three kinds.

    This is the demo state's shape in miniature — nine captures whose
    plans were built independently — and the shape on which "read the
    first plan" and "read every plan" disagree.
    """
    return SessionState(
        format_row_id="fixture@2x2", receiver_policy_id="policy-test",
        page_hypotheses=(0,),
        captures=(
            _capture(_SHA_A, (_lane("l00"),)),
            _capture(_SHA_B, (_lane("l00"),
                              _lane("m00", parent="l00", mopup_of="l00"),
                              _lane("r00", parent="m00", refine_of="l00"))),
        ))


def test_the_lane_kind_census_reads_every_capture_plan() -> None:
    """Fork 1: a census over ``captures[0]`` alone reports no harvest."""
    census = parity_k._lane_kind_census(_two_capture_state())
    assert census == {"mopup": 1, "ordinary": 2, "refine": 1}, census
    # The mutant's answer, stated so the difference is on the page and a
    # future reader cannot mistake this for a tautology.
    first_only = {"ordinary": 1}
    assert census != first_only


def test_the_lane_kind_census_of_a_captureless_state_is_empty() -> None:
    """A state that ingested nothing declares no plan — EMPTY, not absent.

    A capture with an empty plan is unrepresentable (``CaptureRecord``
    refuses it: "a persisted capture needs a complete scale plan"), so
    the only way to reach an empty census is a state with no captures at
    all. The report prints this dict as the flags column, and "{}" has
    to be distinguishable there from an ordinary-only plan rather than
    raising.
    """
    state = SessionState(
        format_row_id="fixture@2x2", receiver_policy_id="policy-test",
        page_hypotheses=(0,), captures=())
    assert parity_k._lane_kind_census(state) == {}


@pytest.mark.parametrize("observed,golden,expected", [
    ("aa", "aa", True),        # published, matches the golden
    ("bb", "aa", False),       # published, does NOT match: a real failure
    (None, "aa", None),        # nothing published: no statement was made
    ("aa", None, None),        # no golden declared: nothing to compare to
    (None, None, None),
])
def test_zero_wrong_is_three_valued_and_never_collapses(
        observed: str | None, golden: str | None,
        expected: bool | None) -> None:
    """Fork 2: ``None`` is the ABSENCE of a correctness statement."""
    assert parity_k._zero_wrong(observed, golden) is expected


def test_the_report_marks_the_three_values_apart() -> None:
    """The collapse must not sneak back in at the rendering step."""
    marks = {parity_k_report._mark(True), parity_k_report._mark(False),
             parity_k_report._mark(None)}
    assert len(marks) == 3, marks


#: One real epilogue tuple, verbatim from the e029 row of
#: ``scratch/holo2-catchup/real/parity-k.md`` — the shape the two
#: published columns are read out of.
_EPILOGUE = (
    "capture 1 ingested · done coverage 97.4% (7823516/8030805 cells)",
    "work commits 13297 · fires 13911 · ATTEMPTED 51",
)


@pytest.mark.parametrize("prefix,after,expected", [
    # The two readings the refine-off table publishes.
    ("capture ", "(", 7823516),
    ("work ", "commits", 13297),
    # THE MUTANT: anchoring the done-cell read on the word instead of the
    # bracket returns the percent's leading digits, and 97 renders as a
    # cell count without looking wrong.
    ("capture ", "coverage", 97),
    # No such row, and a row without the anchor: both are None, never 0.
    ("close ", "(", None),
    ("work ", "revisions", None),
])
def test_the_epilogue_anchor_is_the_bracket_not_the_word(
        prefix: str, after: str, expected: int | None) -> None:
    """Fork 3: the anchor decides which integer gets published."""
    assert parity_k_report._epilogue_int(_EPILOGUE, prefix, after) == expected


def test_the_declared_list_cannot_mix_an_archived_state_with_a_rendered_page(
        ) -> None:
    """Fork 3: one arm, one set of pixels — and one v1 source."""
    labels = [sheet.label for sheet in parity_k.SHEETS]
    assert len(labels) == len(set(labels)), labels
    for sheet in parity_k.SHEETS:
        if sheet.kind == "fixture":
            assert sheet.fixture, f"{sheet.label}: fixture arm names none"
            assert sheet.v1_state is None, (
                f"{sheet.label}: a rendered page cannot be compared against "
                "a v1 harvest of a DIFFERENT capture")
            assert not sheet.scans, (
                f"{sheet.label}: a fixture arm renders its own capture")
        else:
            assert not sheet.fixture, f"{sheet.label}: not a fixture arm"
            assert sheet.scans, f"{sheet.label}: declares no capture"
            assert sheet.v1_state is not None, (
                f"{sheet.label}: an archived arm needs a state to read")
        assert sheet.pages >= 1
