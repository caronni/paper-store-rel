"""VERDICT 8 (run subdivision): the set GROWS, and only where it must.

W3/PL5. Every other verdict in this file reads a scheduling set that can
only shrink; this one reads the one decode in which a window's ladder
runs out and four corner windows join the set behind it. What it asks is
the ruled shape, in four sentences over ONE run:

* children exist, and exist ONLY under a window that failed whole (the
  negative asserted on every window that placed);
* the page still closes BYTE-EXACT — subdivision is a recovery route and
  may never move a healthy answer;
* a child's ``WindowRecord`` is an ORDINARY window record, field for
  field, because the no-lineage ruling says provenance is the ordering
  journal's and not a schema change;
* a page that needs no subdivision gets none (read off run banded, whose
  every window places — the childless arm).

NOTHING HERE MONKEYPATCHES THE SCHEDULER. A child is named by its extent
like every window (``records.window_key``), and its extent is a pure
function of its parent's (``pose_fit.subdivision_child_extents``), so the
parent/child structure is RE-DERIVED from the durable state: the plane's
own window plans, the store's window records, and the committed poses.
That is a stronger check than watching the run — it asserts the naming
law the ruling actually made, and it would catch a child that was minted
under a name nothing could reconstruct.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any

from conftest import PageRun

from holo2.capture.catalog import catalog_captures
from holo2.solve.place_model import PlacementConfig
from holo2.solve.plane import capture_view
from holo2.solve.plans import WindowPlan, window_plans_for
from holo2.solve.pose_fit import (SUBDIVISION_MAX_DEPTH,
                                  subdivision_child_extents)
from holo2.solve.records import WindowRecord, WindowStatus, window_key
from holo2.solve.tilemap import StoreIndex

#: MEASURED on this arm (the coverage ramp at 0.85 over 11x11 tiles, one
#: 1200-dpi capture, serial, ``--complete``). Exact by house rule: these
#: are a schedule's integers on the reference lane, so a change that
#: moves them re-declares them once with its cause.
#:
#: RE-MEASURED, and UNCHANGED, by the identity migration (2026-08-22,
#: RULINGS G5).  The arm's page moved 12x12 -> 11x11 because the v2 page
#: at 12x12 subdivides nothing at all — the non-vacuity assertions below
#: caught that, which is what they are for — and ``_fixtures``'
#: :data:`SUBDIVISION_FORMAT` carries the whole field-size sweep that
#: chose 11x11.  All three integers here are the ones this arm always
#: had, on a page that reproduces the same phenomenon by the same route
#: (two corners by the wide consult, one by its own word centre).
EXPECTED_PARENTS = 1
EXPECTED_CHILDREN = 3
#: HOW MANY COLD PASSES THE PARENT MAKES before its corners are born
#: (W4). One, and the arithmetic says why: this row declares ONE page,
#: so the moment anything places, ``live`` is the whole domain and
#: ``rest`` is empty — the parent is offered its live flavour, sweeps
#: the page, refuses, and has nothing left to be offered.
EXPECTED_PARENT_COLD_PASSES = 1


@dataclass(frozen=True)
class Families:
    """One run's window population, split into laid-out and subdivided."""

    #: Every window the LAYOUT plans, by key — re-derived from the store.
    plans: dict[Any, WindowPlan]
    #: Every name a planned window's corner geometry could produce.
    parent_of: dict[Any, WindowPlan]
    #: Every window RECORD the run left, by key.
    records: dict[Any, WindowRecord]
    #: Window key -> its committed poses.
    poses: dict[Any, tuple]

    @property
    def children(self) -> dict[Any, WindowRecord]:
        return {key: record for key, record in self.records.items()
                if key not in self.plans}


def families(session, row) -> Families:
    """Re-derive the window population from DURABLE STATE alone.

    Not from the plane: a VERIFIED session is terminal, and a terminal
    plane is deliberately empty (``plane.open_plane`` — it opens nothing
    and reads no file). The records are still there, and so is
    everything the layout is a function of, so the population is rebuilt
    the way the plane would have: catalogue the captures, view their
    regions, lay out each footing's windows. That the population IS
    reconstructible from records is half of what this verdict asserts.
    """
    plans: dict[Any, WindowPlan] = {}
    for ingested in catalog_captures(session.store):
        view = capture_view(row, ingested, ingested.record.dpi_true)
        for footing in view.footings:
            for plan in window_plans_for(footing, view.regions):
                plans[plan.window_id] = plan
    parent_of: dict[Any, WindowPlan] = {}
    for plan in plans.values():
        for extent in subdivision_child_extents(plan.extent_cells, depth=0,
                                                config=PlacementConfig()):
            parent_of[window_key(plan.footing_id, plan.region_id,
                                 extent)] = plan
    records = {key: record for key, record in session.store.records().items()
               if key.kind == "window"}
    poses = dict(StoreIndex.build(session.store).poses_by_window)
    return Families(plans, parent_of, records, poses)


def test_the_children_are_exactly_the_windows_that_failed_whole(
        run_subdivision: PageRun) -> None:
    """The positive and the negative in one read of the final state.

    Every window record that is not a PLANNED window is a child of some
    planned window — the naming law — and every one of those parents is
    a window with no committed pose. The negative rides the same loop
    from the other side: no window that placed has a child anywhere.
    """
    with run_subdivision.open() as session:
        found = families(session, run_subdivision.page.row)
        children = found.children
        assert len(children) == EXPECTED_CHILDREN, (
            "the subdivision arm produced no children — this verdict has "
            f"no subject: {sorted(str(key) for key in children)}")
        assert set(children) <= set(found.parent_of), (
            "a window record was minted under a name no planned window's "
            "corner geometry can reconstruct")

        parents = {found.parent_of[key].window_id for key in children}
        assert len(parents) == EXPECTED_PARENTS
        # THE NEGATIVE, over the whole sheet and not only over the one
        # parent: a window that PLACED has no child anywhere, so
        # subdivision fired exactly where the whole window failed.
        for key in found.plans:
            has_child = any(child in children
                            for child, owner in found.parent_of.items()
                            if owner.window_id == key)
            assert not (has_child and found.poses.get(key)), (
                f"a placed window has children: {key}")
        assert all(not found.poses.get(parent) for parent in parents)


def test_a_child_is_an_ordinary_window_record(
        run_subdivision: PageRun) -> None:
    """THE NO-LINEAGE RULING, as the record shape it declined to change.

    A child gets a ``WindowRecord`` exactly as any window does —
    outcome-only, at placement or retirement — with no field naming its
    parent, its depth or its provenance. The pin is field-for-field
    against the class, so an added field fails here even if nothing
    reads it: provenance is the ordering journal's.
    """
    fields = tuple(field.name for field in dataclasses.fields(WindowRecord))
    assert fields == ("footing_id", "region_id", "extent_cells", "status",
                      "retired_reason"), fields
    with run_subdivision.open() as session:
        found = families(session, run_subdivision.page.row)
        children = found.children
        assert children
        for key, record in children.items():
            parent = found.parent_of[key]
            assert isinstance(record, WindowRecord)
            assert record.footing_id == parent.footing_id
            assert record.region_id == parent.region_id
            assert record.status in (WindowStatus.ACTIVE, WindowStatus.RETIRED)
            assert (record.retired_reason is None) == (
                record.status is WindowStatus.ACTIVE)
            side = record.extent_cells[2] - record.extent_cells[0]
            assert side == record.extent_cells[3] - record.extent_cells[1]
            assert side < (parent.extent_cells[2] - parent.extent_cells[0])


def test_the_corners_placed_where_the_whole_window_could_not(
        run_subdivision: PageRun) -> None:
    """The claim the arm exists to make, and the depth cap beside it.

    The parent's own passes are in the run's pass census: it spent both
    word stages and the wide consult and reached no address, which is
    the ladder running out. Its children then placed on the same pixels
    at a hundred cells — and none of THEM subdivided, because the depth
    cap is one and the growth is one generation deep.
    """
    assert SUBDIVISION_MAX_DEPTH == 1
    with run_subdivision.open() as session:
        found = families(session, run_subdivision.page.row)
        children = found.children
        placed = [key for key, record in children.items()
                  if record.status is WindowStatus.ACTIVE]
        assert len(placed) == EXPECTED_CHILDREN, (
            "no corner placed: the arm no longer shows what it exists for")
        for key in placed:
            assert found.poses.get(key), (
                "an ACTIVE window record with no committed pose")

        # No grandchildren: a child's own corner names appear nowhere,
        # which is the depth cap read off the durable state.
        for key, record in children.items():
            for extent in subdivision_child_extents(
                    record.extent_cells, depth=0, config=PlacementConfig()):
                assert window_key(record.footing_id, record.region_id,
                                  extent) not in found.records

        parents = {found.parent_of[key].window_id for key in children}

    spent = {(row["stage_spent"], row["wide"])
             for row in run_subdivision.passes if row["window"] in parents}
    assert ("centre", False) in spent and ("rest", False) in spent, (
        "the parent never spent its word stages, so its ladder did not "
        f"run out: {sorted(map(str, spent))}")
    assert (None, True) in spent, "the parent never reached the wide consult"
    assert not any(row["outcome"] == "accepted"
                   for row in run_subdivision.passes
                   if row["window"] in parents)


def test_the_parent_correlated_before_it_was_quartered(
        run_subdivision: PageRun) -> None:
    """W4: THE COLD PAIR IS WHAT QUARTERS A WINDOW, and it really fires.

    v1 reaches subdivision from ``run_cold`` -> ``refuse_unplaced``
    (``place.py:1495`` -> :1126) and from nowhere else on the ladder's
    exhaustion path; W3 wired the trigger at the wide refusal only
    because cold did not exist. This reads the restoration off the same
    decode the arm already runs: the parent's LAST pass before its
    corners were born is a cold pass, claimed as a flavour, sweeping a
    real page set, and refusing.

    NON-VACUITY IS THE POINT. A cold check that passed on a run where
    cold never fired would pin nothing, so the census is asserted by
    count: this arm's parent makes :data:`EXPECTED_PARENT_COLD_PASSES`
    cold pass(es), each of them a real sweep over the row's one declared
    page. Measured on this arm; exact by this file's house rule.
    """
    with run_subdivision.open() as session:
        found = families(session, run_subdivision.page.row)
        parents = {found.parent_of[key].window_id
                   for key in found.children}
        kids = set(found.children)
        assert parents, "no parent: the arm has nothing to say about cold"

    passes = run_subdivision.passes
    cold = [row for row in passes
            if row["window"] in parents and row["cold"]]
    assert len(cold) == EXPECTED_PARENT_COLD_PASSES, (
        f"the parent's cold census moved: {[row['outcome'] for row in cold]}")
    for row in cold:
        assert row["cold_spent"] == row["cold"], "a claimed flavour was skipped"
        assert row["cold_pages"] == len(run_subdivision.page.row.page_domain)
        assert row["outcome"] == f"cold_refused_{row['cold']}", row["outcome"]

    # THE ORDER, read off the census rather than asserted about the code:
    # the parent's LAST pass is a cold refusal, and every pass a corner
    # made comes after it — which is what "the correlation bore them"
    # means when the only evidence allowed is the run's own record.
    last_parent = max(index for index, row in enumerate(passes)
                      if row["window"] in parents)
    assert passes[last_parent]["cold"], (
        "the parent's ladder ended somewhere other than its correlation")
    first_child = min((index for index, row in enumerate(passes)
                       if row["window"] in kids), default=None)
    assert first_child is not None and first_child > last_parent, (
        "a corner ran before its parent's correlation refused")


def test_the_faded_page_still_closes_byte_exact(
        run_subdivision: PageRun) -> None:
    """Subdivision is a RECOVERY route: the answer is the emitted bytes."""
    outcome = run_subdivision.outcome
    assert outcome.status == "verified", outcome.reason
    assert outcome.payload == run_subdivision.page.payload
    assert outcome.close is not None
    assert outcome.close["k_total"] == run_subdivision.page.k_total


def test_a_page_that_needs_no_subdivision_gets_none(
        run_banded: PageRun) -> None:
    """THE CHILDLESS ARM, on a run that already exists.

    Run banded places every window it plans (``test_seeded``'s own
    verdict), so nothing there may ever go dormant on an eligible
    refusal — and therefore nothing may be named a corner. This is the
    pin that says subdivision costs a healthy page NOTHING: not a
    window, not a record, not a pass.

    SINCE W4 IT SAYS THE SAME OF COLD, on the same run and for the same
    reason: correlation is the tier BEHIND which subdivision now sits, so
    a page with no children is also a page with no sweeps. The dear tier
    that a healthy page never reaches is the whole point of pricing it
    dearly.
    """
    with run_banded.open() as session:
        found = families(session, run_banded.page.row)
        assert found.plans, "the population did not rebuild from records"
        assert not found.children, (
            "a page every window of which places produced a child: "
            f"{sorted(str(key) for key in found.children)}")
        assert not set(found.parent_of) & set(found.records)
    assert not [row for row in run_banded.passes if row["cold"]], (
        "a healthy page paid for a correlation sweep")
