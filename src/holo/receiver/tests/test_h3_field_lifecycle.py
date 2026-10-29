"""The page field's lifecycle: one revision, and who owes work when it moves.

W8 charter §3, items 1-6, written BEFORE the build (R-G).  Each test
drives the real store and the real two rows — no re-implementation of a
fold, a price or an eligibility rule — and each is seeded from the
external review's own reproductions
(`docs/reviews/page-field-receiver-2026-09-08/lifecycle_counterexamples.py`
and `color_assembly.py`), which run this same machinery on this tree.

The rule these seven express is R-D: the store keeps ONE integer
revision per (capture, page), advanced by every placement birth, change
or removal and by every certificate on that page; the collection's
ordinal IS that revision; a page whose last window left publishes an
EMPTY collection rather than leaving its rows standing; the solve runs on
a changed revision and publishes only if the field moved; and a consumer
carries the field revision it was fitted with, so a field-only change
still owes a refit.

Item 6b is the other half of that last rule and the reason W8 can afford
it: the revision is BOOKKEEPING, not a trigger.  W8 makes it move on
every certificate, so something has to say that ten advances buy one
collection and that a publication which moved nothing wakes nobody —
otherwise the honest ordinal buys a re-collection per certificate, which
is the expensive direction (design §2.7).  Those two are scheduler
claims, so they drive the engine's own queue and not the rows'
prepare functions.

The suite was written red under one strict `xfail` per test, removed
test by test as the build made each pass; the whole marker went at the
W8 integration, when the last of them did.

The collector fixtures come from `test_h3_plane_fields`, whose own
collector-internal tests this suite supersedes; when that module goes,
its builders move to `_h3_fixtures_field` and this import follows them.
"""

from __future__ import annotations

import dataclasses
from fractions import Fraction

import numpy as np

from holo.receiver import data, engine, snapshot
from holo.receiver.format import identity
from holo.receiver.lib import plane_field
from holo.receiver.plugins import (color_refine, color_region,
                                   fields, fields_collect)
from holo.receiver.tests import (_h3_facts, _h3_fixture_geometry,
                                 test_h3_plane_fields as fx)
from holo.receiver.tests.test_h3_scheduler_law import _Executor

#: printed dots per millimetre: the PRINTER's number, named where the
#: printer is named.  `lib/` names no printer, so design §2.4's two
#: lengths reach the solve as this scale and never by an import
#: (`test_h3_field_consumers` pins that boundary).
DOTS_PER_MM = identity.HW_DPI / identity.MM_PER_INCH


def prior(cell_dots: int) -> object:
    """The design's own prior at this pitch, with the printer's scale.

    Here because the other four modules already import from this one and
    the reverse direction would be an import cycle; it moves to
    `_h3_fixtures_field` with the builders.
    """
    return plane_field.default_prior(cell_dots, dots_per_mm=DOTS_PER_MM)

SUBJECT = (fx.CAPTURE_ID, fx.PAGE)
#: a tile the fixture's window does not cover: a certificate here is new
#: evidence to the STORE and no new measurement to the collection
UNCOVERED_TILE = (5, 5)


def _collect_fact(store: object) -> data.FieldObservations:
    job = fields_collect.prepare_collect(store, SUBJECT,
                                         fields_collect.STAGE_COLLECT)
    assert job is not None, "the page has a placement and no collection"
    fact, = job().facts
    return fact


def _solve_facts(store: object) -> tuple[data.PlaneField, ...]:
    job = fields.prepare_fields(store, fx.PAGE, fields.STAGE_SOLVE)
    assert job is not None, "the page has observations and no solve"
    return tuple(fact for fact in job().facts
                 if isinstance(fact, data.PlaneField))


def _finer_lane(store: object) -> tuple:
    """A second, finer level of the same capture, with the same rasters.

    The fixture's own page, read at a finer ladder: what changes is
    which window OWNS the tiles, which is the scale-space order the
    receiver runs in (coarse placed first, fine later).
    """
    capture = store._captures[fx.CAPTURE_ID]
    fine = dataclasses.replace(capture.levels[0], index=1, ppc=Fraction(8))
    store._captures[fx.CAPTURE_ID] = dataclasses.replace(
        capture, levels=capture.levels + (fine,))
    store._levels[(fx.CAPTURE_ID, 1)] = fine
    store._planes_by_lane[(fx.CAPTURE_ID, 1)] = store._planes_by_lane[
        (fx.CAPTURE_ID, 0)]
    return (fx.CAPTURE_ID, 1, 0, fx.WID[3])


# --------------------------------------------------------------------
# 1. a fresh placement re-collects
# --------------------------------------------------------------------

def test_a_fresh_placement_on_a_collected_page_re_collects():
    """Review F4: a birth changes the ordinal, so the work is adopted.

    Every fresh placement stands at pose generation 0, so a collection
    ordinal made of a SUM of generations does not move when a window is
    added — and the fold refuses the re-collection that the new window
    made real.  Under R-D the store's own revision advances on the
    birth, so the second collection outranks the first.
    """
    store = fx._placed_store({})
    store._fold(_collect_fact(store))
    wid = _finer_lane(store)
    before = store.evidence_revision(fx.CAPTURE_ID, fx.PAGE)
    store._fold(dataclasses.replace(
        store.placement(fx.WID), window_id=wid, level_index=1,
        native_affine=_h3_fixture_geometry.page_native_affine(
            fx.PITCH_PX, 1.0)))
    assert store.evidence_revision(fx.CAPTURE_ID, fx.PAGE) > before
    adopted, _keys, _kind = store._fold(_collect_fact(store))
    assert adopted, "the re-collection a new window made real was refused"


def test_the_store_adopts_the_finer_owner_of_a_re_collected_tile():
    """The other half of F4: the finest level with a placement over a
    tile owns its measurement (design §2.5, rule 1), and the ownership
    handoff has to survive the FOLD, not only the collection."""
    store = fx._placed_store({})
    first = _collect_fact(store)
    store._fold(first)
    wid = _finer_lane(store)
    store._fold(dataclasses.replace(
        store.placement(fx.WID), window_id=wid, level_index=1,
        native_affine=_h3_fixture_geometry.page_native_affine(
            fx.PITCH_PX, 1.0)))
    second = _collect_fact(store)
    store._fold(second)
    standing, = store.field_observations(fx.PAGE)
    assert [window[1] for window in standing.window_ids] == [1]
    assert not np.array_equal(first.delta_dots_xy, second.delta_dots_xy), (
        "the finer owner measured the same numbers: the fixture is not "
        "exercising a real handoff")


# --------------------------------------------------------------------
# 2. the last window leaves
# --------------------------------------------------------------------

def test_the_last_window_to_leave_a_page_publishes_an_empty_collection():
    """Review F5: removal is a state transition, not an absence of work.

    The window moves to the other face.  Page 0 now has nothing standing
    on it, and its rows were measured through a window that is somewhere
    else — so the collection has to PUBLISH that emptiness under a new
    revision rather than become ineligible and leave the rows pooled.
    """
    store = fx._placed_store({})
    store._fold(_collect_fact(store))
    before = store.evidence_revision(fx.CAPTURE_ID, fx.PAGE)
    store._fold(dataclasses.replace(store.placement(fx.WID), page=1,
                                    route=data.ROUTE_REFINE))
    assert store.lane_page_windows(fx.CAPTURE_ID, 0, fx.PAGE) == ()
    assert store.evidence_revision(fx.CAPTURE_ID, fx.PAGE) > before
    empty = _collect_fact(store)
    assert len(np.asarray(empty.tile_code)) == 0
    store._fold(empty)
    rows, _captures = fields.page_observations(store, fx.PAGE)
    assert len(np.asarray(rows.tile_code)) == 0


def test_a_page_with_no_evidence_left_solves_to_the_pose():
    """The second half of F5: zero field, full uncertainty.

    "No evidence" is a state the solve has to reach, not one it may
    early-return out of: a page whose measurements have gone reads the
    POSE everywhere, and says so — the uncertainty is the prior's own,
    which is what "we know nothing here" means in dots.
    """
    store = fx._placed_store({})
    store._fold(_collect_fact(store))
    store._fold(dataclasses.replace(store.placement(fx.WID), page=1,
                                    route=data.ROUTE_REFINE))
    store._fold(_collect_fact(store))
    at = prior(fx.CELL_DOTS)
    published = _solve_facts(store)
    assert len(published) == 3
    for field in published:
        assert not np.any(np.asarray(field.delta_dots_xy))
        assert np.allclose(np.asarray(field.uncertainty_dots), at.sigma_dots)


# --------------------------------------------------------------------
# 3. the colour row's refit debt
# --------------------------------------------------------------------

def _color_lane(store: object, color_fx: object,
                raster_dir: object) -> tuple:
    """The review's own colour bench: one fitted head, one new window.

    Everything here is `color_assembly.py`'s construction — the same
    fixture rasters, the same two placements, the same real first fire
    — with the scheduler restricted to the colour row so that only its
    own wake can do the work.

    The first placement is INGESTED and not written into the store's
    own dicts.  The colour row is born by `Placement`, so a direct write
    leaves no bookmark, no read index and no worker, and every wake this
    module sends afterwards reaches nobody — measured at the W8 build,
    2026-09-08: `store._bookmarks` empty, frontier 0, and
    `_run_the_queue` returning zero jobs whatever the stage rule says.
    """
    row = store.row
    cells = color_fx._page_cells(row)
    states, _ = color_fx.color_model.reference_states(
        row, store.geometry, 0, cells)
    rng = np.random.default_rng(20260908)
    full = np.where(states >= 0, states,
                    rng.integers(0, 8, len(states))).astype(np.uint8)
    planes = color_fx._printed_planes(row, full, raster_dir)
    store._planes_by_lane[("cap", 0)] = dict(zip("rgb", planes))
    store._levels[("cap", 0)] = data.Level(
        index=0, ppc=Fraction(color_fx.RASTER_PPC), scale=Fraction(1),
        shape_px=planes[0].shape_px, label="l0")
    lane = ("cap", 0, 0)
    native = _h3_fixture_geometry.page_native_affine(
        color_fx.RASTER_PPC, color_fx.RASTER_MARGIN_PX)
    first = _h3_fixture_geometry.window_placement(
        ("cap", 0, 0, (0, 0, *row.cells_yx)), native, cells)
    second = _h3_fixture_geometry.window_placement(
        ("cap", 0, 1, (0, 0, *row.cells_yx)), native, cells,
        patch_ordinal=1, region_index=1)
    store._ingest(first)
    for fact in color_region.prepare_color(store, lane,
                                           color_region.STAGE_COLOR)().facts:
        store._ingest(fact)
    return lane, second


def _run_the_queue(store: object) -> _Executor:
    executor = _Executor()
    store._fill(executor)
    for index in range(len(executor.jobs)):
        store._merge(executor.finish(index))
    store._fill(executor)
    return executor


def test_a_new_window_and_a_new_field_make_the_colour_row_refit(
        monkeypatch, tmp_path):
    """Review F6: assembly may clear window debt, never refit debt.

    A new window and a field publication arrive together.  Assembly is
    the cheap stage and it covers the new window, and clearing that debt
    emits no wake — so the head that reads the page goes on reading it
    through the geometry it was fitted in.  Under R-D the refit debt is
    its own state and the field revision is what clears it.
    """
    from holo.receiver.tests import test_h3_plugins_color as color_fx

    monkeypatch.setattr(engine, "DESCRIPTORS",
                        (color_region.COLOR_DESCRIPTOR,))
    store = fx._engine(color_fx.CMY8_TINY)
    lane, arriving = _color_lane(store, color_fx, tmp_path)
    fits_before = store.color_lane_head_fits(lane)
    store._placements[arriving.window_id] = arriving
    store._lane_page_wids[lane].add(arriving.window_id)
    store._ingest(_h3_facts.plane_field(delta_dots=1.0,
                                        tiles_yx=store.row.tiles_yx))
    _run_the_queue(store)
    assert store.color_lane_head_fits(lane) > fits_before


def test_the_colour_head_records_the_field_revision_it_was_fitted_with(
        monkeypatch, tmp_path):
    """R-D's consumer clause: a fitted input has a version.

    The head carries the frame it was fitted in so a later window can be
    read without re-fitting; the page's registration is part of that
    frame, so the revision it was fitted with belongs beside the pitch
    and the divisor.  Without it "is a refit owed?" is not a question
    this store can answer.
    """
    from holo.receiver.tests import test_h3_plugins_color as color_fx

    monkeypatch.setattr(engine, "DESCRIPTORS",
                        (color_region.COLOR_DESCRIPTOR,))
    store = fx._engine(color_fx.CMY8_TINY)
    lane, _arriving = _color_lane(store, color_fx, tmp_path)
    head = store.color_lane_head(lane)
    assert head is not None
    assert head.field_revision == store.field_revision(0)


# --------------------------------------------------------------------
# 4. refinement after a field-only change
# --------------------------------------------------------------------

def test_an_adopted_colour_pose_becomes_refinable_after_a_field_change():
    """Review F10: "same inputs" has to include the field.

    The anti-churn rule is right — a window whose certificate set has
    not grown has nothing new to fit a pose against.  But the sampling
    geometry changed under it, so the inputs are not the same, and a
    partially decoded window with cargo left is refusable only until
    something moves.
    """
    store = fx._placed_store(fx._tile_certificates(0, 0))
    reach = store.window_reach(fx.WID)
    assert reach, "the fixture placement declared no reach to refine over"
    basis = color_refine.reach_certified(store, fx.PAGE, reach)
    assert basis, "no certificate stands in the window's reach"
    store._fold(dataclasses.replace(store.placement(fx.WID),
                                    refine_basis=basis))
    assert not color_refine._color_refine_eligible(store, fx.WID)
    store._fold(_h3_facts.plane_field(page=fx.PAGE, plane=2, ordinal=7,
                                      tiles_yx=fx.TILES_YX))
    assert color_refine._color_refine_eligible(store, fx.WID)


# --------------------------------------------------------------------
# 5. what advances the revision
# --------------------------------------------------------------------

def test_every_placement_and_certificate_advances_the_pages_revision():
    """The middle step improves the held-out quality as well as the pose.

    REPAIRED at the build (2026-09-08, measured): as written the step
    replaced the affine alone, and `data.placement_ordinal` was (adopted
    revision, basis depth, -quality) — since R6 it is (adopted revision,
    field revision, certificate count, -quality), and the tie stands
    either way — so that fact tied the standing one
    and `store_folds._adopts` refused it outright — the store kept the
    old pose, nothing changed, and the revision was right not to move
    (seen `[1, 4, 4, 5]`).  A pose that moves is a pose the store
    adopts, which in production is a refinement or a better fit; the
    lower quality is the shortest spelling of that here.
    """
    store = fx._placed_store({})
    seen = [store.evidence_revision(fx.CAPTURE_ID, fx.PAGE)]
    for certificate in fx._tile_certificates(*UNCOVERED_TILE).values():
        store._fold(certificate)
    seen.append(store.evidence_revision(fx.CAPTURE_ID, fx.PAGE))
    store._fold(dataclasses.replace(
        store.placement(fx.WID), quality=store.placement(fx.WID).quality - 1.0,
        native_affine=_h3_fixture_geometry.page_native_affine(
            fx.PITCH_PX, 1.0)))
    seen.append(store.evidence_revision(fx.CAPTURE_ID, fx.PAGE))
    store._fold(dataclasses.replace(store.placement(fx.WID), page=1,
                                    route=data.ROUTE_REFINE))
    seen.append(store.evidence_revision(fx.CAPTURE_ID, fx.PAGE))
    assert seen == sorted(set(seen)), seen


def test_nothing_but_placements_and_certificates_advances_it():
    """The revision is the collection's INPUTS and nothing else: a fact
    that cannot change a measurement must not re-price one."""
    store = fx._placed_store({})
    standing = store.evidence_revision(fx.CAPTURE_ID, fx.PAGE)
    store._fold(_h3_facts.color_row())
    store._fold(_h3_facts.plane_field(page=fx.PAGE, plane=2, ordinal=3,
                                      tiles_yx=fx.TILES_YX))
    assert store.evidence_revision(fx.CAPTURE_ID, fx.PAGE) == standing


def test_a_resume_restores_the_revision(tmp_path):
    """The revision counts EVENTS, and a resume cannot recount them.

    The interrupted run refined its placement and then moved it to the
    other face, so page 0's own history is three events long and the
    facts that survive it record ONE of them: a refined placement is
    snapshotted once, and a placement that left page 0 leaves page 0
    nothing at all.  A resumed run that recounted would come back LOWER
    than the run it resumed — and the collection fact it restored beside
    it carries the higher number, so every fresh collection would be
    outranked by a restored one.  The number is carried, not derived
    (design §2.7).
    """
    store = fx._placed_store(fx._tile_certificates(0, 0))
    store._fold(dataclasses.replace(
        store.placement(fx.WID),
        native_affine=_h3_fixture_geometry.page_native_affine(
            fx.PITCH_PX, 1.0)))
    store._fold(dataclasses.replace(store.placement(fx.WID), page=1,
                                    route=data.ROUTE_REFINE))
    expected = store.evidence_revision(fx.CAPTURE_ID, fx.PAGE)
    path = tmp_path / snapshot.NAME
    snapshot.write(path, snapshot.collect(store))
    resumed = fx._engine()
    # the capture through its own fold, as a resume declares it: the
    # placement fold reads the lane's level scale (2026-10-03)
    resumed._fold(_h3_facts.capture())
    assert fx.CAPTURE_ID in resumed._captures
    for fact in snapshot.read(path):
        resumed._fold(fact)
    assert resumed.evidence_revision(fx.CAPTURE_ID, fx.PAGE) == expected


# --------------------------------------------------------------------
# 6. a solve publishes only what moved — and publishes the PAGE
# --------------------------------------------------------------------

#: The external review's publication bench (`publication.py`), moved
#: onto the fixture's page and into the store: C and M displaced against
#: each other along page x by this much, which is the word planes' own
#: gauge and what a solve of it reads back (0.1999 dots after the
#: prior's shrinkage) — INSIDE `plane_field.FIELD_NOISE_DOTS`, so the
#: displacement alone never publishes and the support mask is what
#: carries these tests (design §2.7, R1).
SHIFT_DOTS = 0.2
PAGE_TILES = tuple(range(fx.TILES_YX[0] * fx.TILES_YX[1]))
PLANES = (0, 1, 2)


def _collection(revision: int, *, shift_dots: float = 0.0,
                planes: tuple[int, ...] = PLANES,
                unmeasured: tuple[tuple[int, int], ...] = (),
                capture_id: str = fx.CAPTURE_ID,
                ) -> data.FieldObservations:
    """One capture's measurements of the whole page, as a collection.

    Every tile of the page on every plane in `planes`, from one window
    at unit weight; `unmeasured` drops single (plane, tile) rows, which
    is how a support-PRESENCE mask moves while nothing else does.  The
    collection is folded rather than measured, so what the tests below
    drive is the publisher and the fold — the collector has its own
    module and its own fixtures.
    """
    dropped = set(unmeasured)
    entries = [(plane, code) for plane in planes for code in PAGE_TILES
               if (plane, code) not in dropped]
    plane_column = np.asarray([plane for plane, _code in entries], np.int64)
    delta = np.zeros((len(entries), 2), np.float64)
    delta[:, 0] = np.where(plane_column == 0, shift_dots,
                           np.where(plane_column == 1, -shift_dots, 0.0))
    return data.FieldObservations(
        capture_id=capture_id, page=fx.PAGE,
        tile_code=np.asarray([code for _plane, code in entries], np.int64),
        plane=plane_column, delta_dots_xy=delta,
        measured_xy=np.ones((len(entries), 2), bool),
        weight=np.ones(len(entries), np.float64),
        source=np.full(len(entries), plane_field.SOURCE_ANCHOR, np.int64),
        window=np.zeros(len(entries), np.int64), window_ids=(fx.WID,),
        window_generation=np.zeros(1, np.int64), revision=int(revision))


def _publish(store: object) -> tuple[data.PlaneField, ...]:
    """Solve the page and fold whatever it published."""
    facts = _solve_facts(store)
    for fact in facts:
        store._fold(fact)
    return facts


def _standing_store(*collections: data.FieldObservations) -> object:
    store = fx._engine()
    for collection in collections:
        store._fold(collection)
    return store


def test_a_solve_publishes_every_plane_of_the_page_or_none_of_them():
    """Review R1: the three fields are ONE statement, so is the wake.

    The gauge makes M exactly -C (`lib/plane_field.solve`), and the
    shipped rule asked the question per plane: the review's own
    counterexample restored one C tile's evidence and moved C/M by
    +-0.2 dots, C published on its changed support mask, M did not
    because 0.1999 dots is inside the noise scale — and the durable
    pair, one plane from each of two solves, read C+M = 0.1999 where
    every solve reads exactly 0.  A reader sampling that pair is
    standing in no frame at all.  One decision for the page repairs it:
    all three facts, one revision, and the gauge survives publication.
    """
    store = _standing_store(_collection(1, unmeasured=((0, 0),)))
    first = _publish(store)
    assert [fact.plane for fact in first] == list(PLANES)
    store._fold(_collection(2, shift_dots=SHIFT_DOTS))
    published = _publish(store)
    assert [fact.plane for fact in published] == list(PLANES)
    assert {fact.ordinal for fact in published} == {
        store.page_evidence_revision(fx.PAGE)}
    assert store.field_revision(fx.PAGE) == published[0].ordinal
    cyan, magenta, _yellow = store.page_plane_fields(fx.PAGE)
    assert np.max(np.abs(np.asarray(cyan.delta_dots_xy))) > 0.0, (
        "the bench published nothing to break the gauge with")
    assert np.max(np.abs(np.asarray(cyan.delta_dots_xy)
                         + np.asarray(magenta.delta_dots_xy))) == 0.0


def test_the_same_measurements_again_publish_nothing():
    """The other side of R1: coherent does not mean noisy.

    A publication re-arms every colour window of the page, so a solve
    that repeats itself must stay silent — the anti-churn clause of
    design §2.7, which the joint decision has to keep rather than trade
    away for the gauge.
    """
    store = _standing_store(_collection(1, shift_dots=SHIFT_DOTS))
    assert _publish(store)
    store._fold(_collection(2, shift_dots=SHIFT_DOTS))
    assert _solve_facts(store) == ()


def test_agreeing_evidence_that_moves_only_the_metadata_publishes_nothing():
    """I8's counts and uncertainty are reported, never sampled through.

    A second capture measuring the page the same way doubles the
    observations and every tile's support MAGNITUDE and lowers the
    uncertainty everywhere — the control store below solves exactly that
    and says so, plane by plane — while the displacement comes back
    bit-identical and every tile that carried it still does.  Nothing a
    reader samples through moved, so nothing publishes and no head
    refits.

    The bench measures ZERO displacement because that is the only way
    the metadata can move by itself: the prior's shrinkage is a function
    of the evidence count, so a displaced field always shifts a little
    when the evidence doubles (5.9e-05 dots on this page's +-0.2-dot
    gauge, measured).  That case is held by the threshold in
    `fields.moved` and is not this clause; this test is the metadata
    clause alone, and it is exact.

    The page's field revision is the last line because suppressing the
    WAKE alone would not be enough: a consumer compares the ordinal the
    standing facts carry with the revision it was fitted at, so an
    advanced ordinal would be found by the next unrelated wake and
    charged as a refit then (review R1's corrected reading).
    """
    collections = (_collection(1),
                   _collection(2, capture_id=fx.OTHER_CAPTURE))
    store = _standing_store(collections[0])
    standing = _publish(store)
    assert [fact.plane for fact in standing] == list(PLANES)
    store._fold(collections[1])
    control = _solve_facts(_standing_store(*collections))
    for before, after in zip(standing, control, strict=True):
        assert np.array_equal(np.asarray(after.delta_dots_xy),
                              np.asarray(before.delta_dots_xy)), (
            "the bench moved the field, so it is not metadata alone")
        assert after.n_observations > before.n_observations
        assert after.n_captures > before.n_captures
        assert np.all(np.asarray(after.support)
                      > np.asarray(before.support))
        assert np.all(np.asarray(after.uncertainty_dots)
                      < np.asarray(before.uncertainty_dots))
    assert _solve_facts(store) == ()
    assert store.field_revision(fx.PAGE) == standing[0].ordinal


def test_a_plane_that_loses_its_last_evidence_publishes_the_loss():
    """I13, through the publisher: unknown is not zero.

    Y was measured at zero everywhere and now nothing reaches it.  Its
    displacement does not move — it was zero and it stays zero — so the
    displacement clause cannot carry this, and a rule made of that
    clause alone would leave readers sampling a measured zero that no
    longer has any evidence under it.  The support mask carries it: the
    page publishes, Y's support goes to zero and its uncertainty back
    to the prior's own.
    """
    store = _standing_store(_collection(1))
    before = _publish(store)
    assert np.count_nonzero(before[2].support) == len(PAGE_TILES)
    store._fold(_collection(2, planes=(0, 1)))
    published = _publish(store)
    assert [fact.plane for fact in published] == list(PLANES)
    assert not np.any(np.asarray(published[2].delta_dots_xy))
    assert not np.any(np.asarray(published[2].support))
    assert np.allclose(np.asarray(published[2].uncertainty_dots),
                       prior(fx.CELL_DOTS).sigma_dots)


def test_an_empty_page_and_its_recovery_both_publish():
    """The whole-page shape of the same transition (I13, §2.5).

    A page whose last window left publishes an EMPTY collection, and
    the solve behind it has to reach the readers — otherwise they go on
    sampling a field whose evidence has gone.  The recovery is the
    other direction and publishes too, on the same mask.
    """
    store = _standing_store(_collection(1, shift_dots=SHIFT_DOTS))
    assert _publish(store)
    store._fold(_collection(2, planes=()))
    emptied = _publish(store)
    assert [fact.plane for fact in emptied] == list(PLANES)
    assert not any(np.any(np.asarray(fact.support)) for fact in emptied)
    store._fold(_collection(3, shift_dots=SHIFT_DOTS))
    recovered = _publish(store)
    assert [fact.plane for fact in recovered] == list(PLANES)
    assert all(np.all(np.asarray(fact.support) > 0.0)
               for fact in recovered)


def test_two_identical_collections_publish_one_field():
    """R-D's second clause, and the review's trigger criticism answered
    from the other side: solve whenever the evidence revision moved —
    solving is 1:2,800 to 1:18,000 of a collection (design B6) — and let
    the PUBLICATION carry the "did anything change" question, which is
    the one a residual statistic could never answer honestly.
    """
    store = fx._placed_store({})
    store._fold(_collect_fact(store))
    for field in _solve_facts(store):
        store._fold(field)
    solved_at = store.field_revision(fx.PAGE)
    for certificate in fx._tile_certificates(*UNCOVERED_TILE).values():
        store._fold(certificate)
    store._fold(_collect_fact(store))
    assert _solve_facts(store) == ()
    assert store.field_revision(fx.PAGE) == solved_at

# --------------------------------------------------------------------
# 6b. the revision is bookkeeping, not a trigger
# --------------------------------------------------------------------

#: ten certificates on ten tiles the fixture's window does not cover:
#: each is new evidence to the STORE and none of them is a reason to
#: measure ten times
CHURN_TILES = tuple((ty, tx) for ty in range(2, 4) for tx in range(2, 7))


def test_ten_certificates_between_two_admissions_buy_one_collection(
        monkeypatch):
    """Charter item 6b, first clause, and W8's own cost.

    W8 is the wave that makes the revision move on EVERY certificate
    (the F4 fix), so the cheap way to read R-D is "re-collect per
    certificate", which on a real sheet is thousands of collections of a
    page that changed by one tile.  The revision says what a collection
    would be measuring; the LADDER says when.  Driven through the
    engine's own queue, because coalescing is a scheduling claim and the
    row's prepare function cannot make it.

    REPAIRED at the build (2026-09-08, measured): the certificates were
    handed to `_fold`, which writes the store and stops — births and
    wakes are `_ingest`'s (`engine._ingest`) — so no collect worker was
    ever born and the fill produced 0 jobs, not 10.  Ingest is what a
    scheduling claim has to drive.
    """
    monkeypatch.setattr(engine, "DESCRIPTORS",
                        (fields_collect.COLLECT_DESCRIPTOR,))
    store = fx._placed_store({})
    before = store.evidence_revision(fx.CAPTURE_ID, fx.PAGE)
    for ty, tx in CHURN_TILES:
        certificate = next(iter(fx._tile_certificates(ty, tx).values()))
        store._ingest(certificate)
    assert store.evidence_revision(fx.CAPTURE_ID, fx.PAGE) == \
        before + len(CHURN_TILES)
    executor = _run_the_queue(store)
    assert len(executor.jobs) == 1, (
        f"{len(CHURN_TILES)} certificates bought {len(executor.jobs)} "
        f"collections")


def test_a_second_publication_of_the_same_field_wakes_no_reader(
        monkeypatch, tmp_path):
    """Charter item 6b, third clause: the colour head refits once per
    REAL field change.

    The head is expensive and the field is republished whenever the page
    re-solves, so "the revision moved" may not be what wakes it — a
    publication that moved the field is.  The head records the revision
    it was fitted with, and the same field arriving again leaves it
    alone.
    """
    from holo.receiver.tests import test_h3_plugins_color as color_fx

    monkeypatch.setattr(engine, "DESCRIPTORS",
                        (color_region.COLOR_DESCRIPTOR,))
    store = fx._engine(color_fx.CMY8_TINY)
    lane, arriving = _color_lane(store, color_fx, tmp_path)
    store._placements[arriving.window_id] = arriving
    store._lane_page_wids[lane].add(arriving.window_id)
    field = _h3_facts.plane_field(delta_dots=1.0,
                                  tiles_yx=store.row.tiles_yx)
    store._ingest(field)
    _run_the_queue(store)
    settled = store.color_lane_head_fits(lane)
    assert store.color_lane_head(lane).field_revision == \
        store.field_revision(0)
    store._ingest(field)
    _run_the_queue(store)
    assert store.color_lane_head_fits(lane) == settled


def test_a_pages_three_fields_buy_one_refit_and_not_three(
        monkeypatch, tmp_path):
    """R1's scheduling half: publishing the page may not cost 3x.

    The joint decision publishes three facts where the per-plane rule
    published one or two, and the colour head is the expensive reader —
    so the three have to arrive as ONE wake.  They do, and for the
    reason the revision exists: the head records the field revision it
    was fitted with, all three facts carry the same one, and the lane's
    bookmark coalesces the wakes they arm.  A count that scaled with
    the planes would make the gauge repair cost three head fits per
    real field change.
    """
    from holo.receiver.tests import test_h3_plugins_color as color_fx

    monkeypatch.setattr(engine, "DESCRIPTORS",
                        (color_region.COLOR_DESCRIPTOR,))
    store = fx._engine(color_fx.CMY8_TINY)
    lane, arriving = _color_lane(store, color_fx, tmp_path)
    store._placements[arriving.window_id] = arriving
    store._lane_page_wids[lane].add(arriving.window_id)
    settled = store.color_lane_head_fits(lane)
    for plane in PLANES:
        store._ingest(_h3_facts.plane_field(
            plane=plane, delta_dots=1.0, ordinal=3,
            tiles_yx=store.row.tiles_yx))
    _run_the_queue(store)
    assert store.color_lane_head_fits(lane) == settled + 1
    assert not color_region.refit_owed(store.color_lane_head(lane),
                                       store.field_revision(fx.PAGE))


# --------------------------------------------------------------------
# 7. the two rows on the ENGINE's own path
# --------------------------------------------------------------------

#: Every certificate of a 10x10 page: what a decode that reads its page
#: whole leaves behind, and what the collection in flight above does not
#: know is coming.
def _certify_the_whole_page(store: object) -> None:
    for ty in range(fx.TILES_YX[0]):
        for tx in range(fx.TILES_YX[1]):
            for certificate in fx._tile_certificates(ty, tx).values():
                store._ingest(certificate)


def _drain_the_queue(store: object) -> tuple[str, ...]:
    """Fill and merge until the engine has nothing left to submit.

    `_run_the_queue` above fills once more than it merges — which is
    what its own claims want, and exactly what hides a row that is born
    by another row's RESULT.  The solve is such a row, so its two tests
    have to run the queue to a standstill.
    """
    executor = _Executor()
    merged = 0
    while True:
        store._fill(executor)
        if merged == len(executor.jobs):
            return tuple(event.plugin for event in store._events
                         if isinstance(event, data.JobDone))
        while merged < len(executor.jobs):
            store._merge(executor.finish(merged))
            merged += 1


def test_the_engine_fires_the_collection_and_then_the_solve(monkeypatch):
    """The path the five behaviour modules never drove.

    Every other test here reaches the rows through `prepare_collect` and
    `prepare_fields` directly, or drives the queue with ONE descriptor
    installed; nothing asked the engine to birth the solve off the
    collection's own fact and then fire it, which is the only place
    `retire`, the version floor and `eligible` are ever consulted.  Two
    jobs, in that order, one field published.
    """
    monkeypatch.setattr(engine, "DESCRIPTORS",
                        (fields_collect.COLLECT_DESCRIPTOR,
                         fields.FIELDS_DESCRIPTOR))
    store = fx._placed_store({})
    certificate = next(iter(fx._tile_certificates(*UNCOVERED_TILE).values()))
    store._ingest(certificate)
    assert _drain_the_queue(store) == (fields_collect.PLUGIN, fields.PLUGIN)
    assert store.field_observations(fx.PAGE)
    assert all(field is not None
               for field in store.page_plane_fields(fx.PAGE))
    assert [event for event in store._events
            if isinstance(event, data.FieldSolved)]


def test_a_page_that_finishes_under_a_collection_still_solves_it(
        monkeypatch):
    """The W8 defect, at the engine, in the order production met it.

    The collection is a whole page of correlations and the run does not
    wait for it: on the clean colour sim it is the LAST job of the run
    and the page is complete 43 seconds before it lands (measured
    2026-09-08 — `fields.collect` 1, `fields` 0 on all four field-frame
    arms, no `FieldSolved`, no `plane_fields`, 71 CPU-seconds spent for
    nothing).  The solve retired on the page's done grid, and the engine
    asks `retire` before the version floor and before eligibility, so
    the row was retired at the very pop its own collection had born it
    on.  The done grid is the PAYLOAD's statement; the collector obeys
    it and stops measuring, and the solve turns what was already paid
    for into the page's field.
    """
    monkeypatch.setattr(engine, "DESCRIPTORS",
                        (fields_collect.COLLECT_DESCRIPTOR,
                         fields.FIELDS_DESCRIPTOR))
    store = fx._placed_store({})
    store._ingest(next(iter(fx._tile_certificates(*UNCOVERED_TILE).values())))
    executor = _Executor()
    store._fill(executor)
    assert len(executor.jobs) == 1, "the collection did not go in flight"
    _certify_the_whole_page(store)
    assert store.done_grid(fx.PAGE).all()
    store._merge(executor.finish(0))
    assert fields.PLUGIN in _drain_the_queue(store)
    assert all(field is not None
               for field in store.page_plane_fields(fx.PAGE))
    assert [event for event in store._events
            if isinstance(event, data.FieldSolved)]
