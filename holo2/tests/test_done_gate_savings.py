"""Pins the silent classifiers in ``holo2/measure/done_gate_savings.py``
(W5, RULINGS I7, 2026-08-23).

The driver's headline numbers come from a finished real-sheet state and
cannot be pinned here (``scratch/holo2-catchup/real/done-gate.md`` is
the artifact). These three derivations can, and each one is silent when
wrong — it produces a plausible-looking count either way:

**Fork 1 — folding ``done_covered`` into "retired" generally.** The
whole point of the driver is the ONE gate reason; a classifier that
counted every ``RETIRED`` window as gated (or that never separated
reasons at all) would report a number for every fixture, correct-looking
on a state where ``done_covered`` happens to be the only reason ever
seen (both real states below — see the module docstring) and wrong the
moment a second reason appears.

**Fork 2 — grouping rungs by the WHOLE footing id instead of its ppc
suffix.** ``WindowRecord.footing_id`` is
``f"{capture_short}:{num}/{den}"`` (``capture/ingest.py::footing_id_for``);
two windows of the SAME rung on two different captures share the ppc
suffix but not the prefix. A grouper keyed on the whole string would
silently multiply one rung into several, invisible on every fixture and
every real state used here (a single-capture decode), because a
single-capture population has no way to expose it — so this file forces
the case with two capture prefixes on one ppc.

**Fork 3 — re-sorting the window population before slicing the
tail/deciles.** ``StoreIndex.windows`` is commit order (``tilemap.py``
choice 8); ``done_gate_savings.build_report`` must consume it AS
IS. ``sorted(index.windows.items())`` sorts by ``ResourceKey``, which
sorts by its string parts — for this driver's own fixture that is NOT
the insertion order (constructed so the two disagree), so a mutant that
re-sorts before slicing would move the fixture's gated window from the
tail decile to an earlier one.

No decode, no ``Store``, no journal: ``build_report`` reads its input
through one method, ``.records() -> dict[ResourceKey, Record]``, so a
plain dict-backed stub is the whole fixture.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
for _path in (_ROOT / "holo2" / "src", _ROOT / "holo2" / "measure"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import done_gate_savings as dgs                                # noqa: E402

from holo2.capture.records import region_key                   # noqa: E402
from holo2.solve.keys import window_key                        # noqa: E402
from holo2.solve.records import WindowRecord, WindowStatus     # noqa: E402


class _StoreStub:
    """The one method ``StoreIndex.build`` reads off a store."""

    def __init__(self, records: dict) -> None:
        self._records = records

    def records(self) -> dict:
        return self._records


def _region():
    return region_key("ab" * 32, (0, 0), 8, (512, 512))


def _window(footing: str, extent: tuple[int, int, int, int]):
    return window_key(footing, _region(), extent)


def _active(footing: str, extent: tuple[int, int, int, int]) -> WindowRecord:
    return WindowRecord(footing_id=footing, region_id=_region(),
                        extent_cells=extent, status=WindowStatus.ACTIVE)


def _retired(footing: str, extent: tuple[int, int, int, int],
            reason: str) -> WindowRecord:
    return WindowRecord(footing_id=footing, region_id=_region(),
                        extent_cells=extent, status=WindowStatus.RETIRED,
                        retired_reason=reason)


#: Six windows, inserted in an order that is DELIBERATELY not the order
#: ``sorted()`` on their keys would produce (verified below) — the
#: fixture fork 3 needs. Two footings (rungs), two capture prefixes on
#: the SAME rung (fork 2), one non-``done_covered`` retirement (fork 1).
_FOOTING_A_CAP1 = "cap1aabbcc:2/1"
_FOOTING_A_CAP2 = "cap2ddeeff:2/1"      # same rung, different capture
_FOOTING_B = "cap1aabbcc:8/1"

_ORDERED = [
    ("w_active_b", _FOOTING_B, (40, 40, 60, 60),
     _active(_FOOTING_B, (40, 40, 60, 60))),
    ("w_active_a1", _FOOTING_A_CAP1, (0, 0, 10, 10),
     _active(_FOOTING_A_CAP1, (0, 0, 10, 10))),
    ("w_other_a1", _FOOTING_A_CAP1, (20, 0, 40, 20),
     _retired(_FOOTING_A_CAP1, (20, 0, 40, 20), "unschedulable_region")),
    ("w_gated_a2", _FOOTING_A_CAP2, (10, 10, 20, 20),
     _retired(_FOOTING_A_CAP2, (10, 10, 20, 20), dgs.DONE_GATE_REASON)),
    ("w_active_a2", _FOOTING_A_CAP2, (5, 30, 15, 40),
     _active(_FOOTING_A_CAP2, (5, 30, 15, 40))),
    # LAST inserted: the one window this fixture wants in the tail.
    ("w_gated_b", _FOOTING_B, (60, 60, 70, 70),
     _retired(_FOOTING_B, (60, 60, 70, 70), dgs.DONE_GATE_REASON)),
]


def _records() -> dict:
    return {_window(footing, extent): record
            for _name, footing, extent, record in _ORDERED}


def test_the_fixtures_key_order_is_not_its_insertion_order() -> None:
    """The premise fork 3's mutation check needs — verified, not assumed."""
    keys = list(_records().keys())
    assert keys != sorted(keys), (
        "fixture must disagree with sorted order or fork 3 is untestable")


def test_gate_share_counts_only_done_covered_never_every_retirement() -> None:
    """Fork 1: one non-gate retirement must not join the gated count."""
    report = dgs.build_report(_StoreStub(_records()), "fixture", Path("."))
    assert report.total_windows == 6
    assert report.placed == 3          # w_active_b, w_active_a1, w_active_a2
    assert report.gated == 2           # w_gated_a2, w_gated_b
    assert report.other_retired == 1   # w_other_a1
    assert report.other_reasons == (("unschedulable_region", 1),)


def test_rungs_group_by_the_ppc_suffix_not_the_whole_footing_id() -> None:
    """Fork 2: two capture prefixes on rung 2/1 must fold into one row."""
    report = dgs.build_report(_StoreStub(_records()), "fixture", Path("."))
    ppcs = {rung.ppc for rung in report.by_rung}
    assert ppcs == {"2/1", "8/1"}, ppcs
    rung_2_1 = next(r for r in report.by_rung if r.ppc == "2/1")
    # cap1's active + cap1's other-retired + cap2's gated + cap2's active
    assert rung_2_1.total == 4
    assert rung_2_1.gated == 1
    assert rung_2_1.other_retired == 1
    rung_8_1 = next(r for r in report.by_rung if r.ppc == "8/1")
    assert rung_8_1.total == 2
    assert rung_8_1.gated == 1


def test_the_tail_is_the_LAST_committed_windows_not_the_first_or_a_sort() -> None:
    """Fork 3: the tail cut must read commit order, mutation-checked."""
    report = dgs.build_report(_StoreStub(_records()), "fixture", Path("."))
    # n=6, last 30% -> int(6*0.7)=4 -> items[4:] = the last TWO inserted:
    # w_active_a2 (placed) and w_gated_b (gated).
    last_30 = next(c for c in report.tail_cuts if c.fraction == 0.3)
    assert last_30.total == 2
    assert last_30.gated == 1
    # last 10% -> items[5:] = exactly w_gated_b, the fixture's final
    # commit, and it IS gated. THIS is the discriminating cut: sorted by
    # key, w_gated_b sorts FIRST among the six (see the premise test),
    # so a sort-before-slice mutant's last 10% is w_active_b (sorts
    # last) instead and reports 0 gated here — verified by folding this
    # fixture through a sorted dict, which reproduces the true 1/1, 2/1
    # last-20%/last-30% counts (they do not discriminate the mutant) but
    # the last-10% cut moves from 1/1 to 1/0.
    last_10 = next(c for c in report.tail_cuts if c.fraction == 0.1)
    assert last_10.total == 1
    assert last_10.gated == 1
