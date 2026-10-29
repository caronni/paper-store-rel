"""What reads the page field, and what the run says about it.

W8 charter §3, items 17-19, written BEFORE the build (R-G).

Item 17's own behaviour — every reader samples where the mapping says —
is `test_h3_page_map.test_only_the_mapping_turns_a_standing_field_into_dots`,
which the charter KEEPS and this module does not duplicate.  What is new
here is the layer the evidence table joins: `lib/` is the bottom of the
receiver and imports neither the plugins that produce facts nor the
format that names them, and the new solve has a millimetre in it, so
that boundary is worth a pin of its own before the build meets it.

Item 18 is the plane-as-K read's pose candidate (review F9): a fallback
that only exists after an admission condition the field itself can fail
is not a fallback.  Item 19 is R-F: residuals per capture AND plane, in
the solve, in the event and in the readout — the aggregate hid a Y
plane whose evidence disagreed by a factor of 8 behind two healthy word
planes (review F11).

R6 (external review, 2026-09-09) adds the consumer the charter did not
name: the colour refinement, which reads the field to sample through it
and CARRIES the revision it read in its basis.  W8 made such a window
eligible again when the field moved; this section is the rest of that
lifecycle — prepare, gate, fold, and eligibility after the fold.  The
rank law itself is `test_h3_cell_classes`, where the placement cell's
schema lives.
"""

from __future__ import annotations

import ast
import dataclasses

import numpy as np
import pytest

from holo.receiver import data, snapshot
from holo.receiver.descriptor import KEY_POSE_AFFINE
from holo.receiver.diag import model as diag_model, readout
from holo.receiver.lib import evidence, plane_field
from holo.receiver.plugins import (color_refine, color_region, fields,
                                   plane_k, refine)
from holo.receiver.tests import (_h3_facts, _h3_fixture_geometry, _h3_support,
                                 test_h3_field_pane as pane_fx,
                                 test_h3_plane_fields as plane_fx,
                                 test_h3_plugins_planek as planek_fx)
from holo.receiver.tests.test_h3_field_evidence import rows
from holo.receiver.tests.test_h3_field_lifecycle import prior

LIB_DIR = _h3_support.HOLO3_ROOT / "lib"
FORBIDDEN_IMPORTS = ("holo.receiver.plugins", "holo.receiver.format")

#: item 19's stimulus, the review's own (F11): the word planes explained
#: perfectly on every tile of the page, and one plane given two rows on
#: ONE tile that no field can satisfy at once.  Two rather than the
#: review's single row because a penalised fit with a free tile can
#: explain one row exactly, and then all three residuals are 0.0 and
#: "the loudest plane" is whichever key the dictionary happened to yield.
RESIDUAL_TILES = pane_fx.TILES_YX[0] * pane_fx.TILES_YX[1]
Y_RESIDUAL_DOTS = 1.0


# --------------------------------------------------------------------
# 17. the layer the evidence table joins
# --------------------------------------------------------------------

def _imported_modules(source: str, filename: str) -> tuple[str, ...]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.append(node.module)
    return tuple(found)


def test_the_evidence_layer_imports_no_plugin_and_no_format():
    """API.md's module map, in the one direction it does not spell out.

    A plugin may read `lib/`; `lib/` may read nothing of the receiver
    above it.  The solve's prior is stated in millimetres and the printed
    dot pitch is the format's constant, so this is the boundary the build
    will push against first — it may pass the scale in, and it may not
    reach up for it.
    """
    checks = _h3_support.Checks("lib layering")
    for path in _h3_support.source_files(LIB_DIR):
        imported = _imported_modules(path.read_text(), str(path))
        checks.check(
            f"{path.name} imports no plugin and no format module",
            not [name for name in imported
                 if name.startswith(FORBIDDEN_IMPORTS)],
            str(imported))
    checks.assert_clean()


def test_the_evidence_table_is_immutable_and_concatenable():
    """The two things R-C promises of the table itself, so that a row
    cannot be edited in place by whatever holds it.

    The COLUMNS, not only the attribute names: the table is handed to
    the solve and to whatever counts it, and a weight or a delta written
    in place under one of them would change the evidence of a page that
    had already been solved.
    """
    table = rows([[1.0, 0.0]], plane=2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        table.weight = np.zeros(1)
    with pytest.raises(ValueError):
        table.weight[0] = 99.0
    with pytest.raises(ValueError):
        table.delta_dots_xy[0, 0] = -7.0
    joined = evidence.Rows.concat(table, table)
    assert len(joined) == 2 * len(table)
    assert not joined.weight.flags.writeable


def test_no_published_fact_carries_a_window_nuisance():
    """R-A's guard against a per-window field coming back by the back
    door (design §2.3, §2.6).

    The solve estimates one translation per window and RETURNS it for
    the diagnostics; the moment a fact carried it, it would be a
    per-window field with another name and the next reader would sample
    through it.  Cheap to state, and the only thing standing between
    that ruling and an implementation detail.
    """
    published = [name.name for fact in (data.PlaneField, data.FieldSolved)
                 for name in dataclasses.fields(fact)]
    assert not [name for name in published if "nuisance" in name], published


# --------------------------------------------------------------------
# 18. the plane-as-K read's pose candidate
# --------------------------------------------------------------------

def _edge_page() -> tuple:
    """The sweep's own c3 page, flush with the raster's edge.

    The margin comes off both the render and the placement, so the page
    sits at the border production meets on a real scan; the pose is the
    production composer's, from a Placement, as the pose gate requires.
    """
    row = planek_fx._row(planek_fx.SWEEP_FORMAT_REF)
    geometry = _h3_fixture_geometry.memoised_site_geometry(row)
    cells, states, full = planek_fx._page_states(row, geometry)
    margin = planek_fx.SWEEP_MARGIN_PX
    planes = tuple(image[margin:-margin, margin:-margin] for image in
                   planek_fx._displaced_page(row, full, 0.0,
                                             planek_fx.SWEEP_PLANE))
    height, width = row.cells_yx
    placement = _h3_fixture_geometry.window_placement(
        ("cap", 0, 0, (0, 0, height, width)),
        _h3_fixture_geometry.page_native_affine(planek_fx.SWEEP_PPC, 0.0),
        cells[states >= 0])
    window = _h3_fixture_geometry.window_pose(row, placement)
    return row, geometry, placement, window, planes


def test_the_plane_as_k_read_survives_a_field_that_falls_off_the_raster():
    """Review F9: the fallback is unreachable through the door.

    `read_window` refuses the whole window when the FIELD-shifted sample
    points leave the raster, and only afterwards does the sweep consider
    the zero-field candidate — so a field wrong by a cell at a page-edge
    window takes away the pose that would have read it.  R-E: the pose
    candidate has to be reachable.

    ONE PRINTED CELL leftward, which is a magnitude from the raster's own
    geometry: the margin comes off both the render and the placement, so
    the page is flush with the raster and any leftward field takes the
    first column off it.  (It used to be `measurement_reach_dots`, which
    W8 retires with the publication bound — a test may not be sized by a
    constant the wave deletes.)
    """
    row, geometry, placement, window, planes = _edge_page()
    cell_dots = color_region.cell_dots_of(row)
    off_page = planek_fx._field_xy(-float(cell_dots), 0.0, row.tiles_yx)
    nominal = plane_k.read_window(row, geometry, window, placement, 0,
                                  planes, cell_dots, {}, {}, None,
                                  planek_fx.SWEEP_PLANE)
    assert nominal is not None, "the fixture page is unreadable at the pose"
    shifted = plane_k.read_window(row, geometry, window, placement, 0,
                                  planes, cell_dots, {}, {}, off_page,
                                  planek_fx.SWEEP_PLANE)
    assert shifted is not None
    assert nominal[0].offset_source == plane_k.SOURCE_NOMINAL
    assert shifted[0].offset_source == plane_k.SOURCE_POSE_ONLY, (
        "the rescue and the sweep's PREFERENCE for the pose are "
        "different events and an operator counts them apart")


# --------------------------------------------------------------------
# 19. residuals per capture AND plane
# --------------------------------------------------------------------

def _one_plane_disagrees(loud: int = 2) -> evidence.Rows:
    """Every plane measured on every tile, and `loud` given two rows on
    one tile that no single value can satisfy.  `loud = -1` is the
    control: the same page, all of it explained."""
    codes = np.arange(RESIDUAL_TILES, dtype=np.int64)
    parts = [rows(np.zeros((RESIDUAL_TILES, 2)), plane=plane,
                  tile_code=codes) for plane in range(3)]
    if loud >= 0:
        parts.append(rows([[Y_RESIDUAL_DOTS, 0.0], [-Y_RESIDUAL_DOTS, 0.0]],
                          plane=loud, tile_code=0))
    return evidence.Rows.concat(*parts)


def _solution(loud: int = 2) -> object:
    return plane_field.solve(
        _one_plane_disagrees(loud), pane_fx.TILES_YX, cell_dots=2,
        prior=prior(2))


def test_the_residual_is_reported_per_capture_and_plane():
    """Review F11: summing the three planes hid the one that disagreed.

    One capture, two word planes explained exactly on every tile, and one
    plane carrying two rows on one tile that contradict each other.
    Summed over the planes that capture looks healthy; per plane it says
    which one to look at, which is the question the page field's
    diagnostics exist to answer.
    """
    residual = _solution().residual_by_capture_plane
    assert {key[1] for key in residual} == {0, 1, 2}
    assert residual[(0, 2)].energy > residual[(0, 0)].energy
    assert residual[(0, 2)].energy > residual[(0, 1)].energy
    loudest = max(residual, key=lambda key: residual[key].energy)
    assert loudest[1] == 2


def _field_row(loud: int) -> str:
    event = fields.solved_event(0, _solution(loud), (pane_fx.CAP_A,))
    model = diag_model.fold(diag_model.empty(),
                            [pane_fx._run(), pane_fx._capture(), event])
    lines = readout.field_rows(model)
    assert lines, "the readout printed no field row at all"
    row, = lines
    return row


def test_the_readout_names_the_plane_that_disagrees():
    """R-F's third place: the event, the readout and the report.  A run
    whose Y evidence fights its Y field has to say so on the status
    block, not only in a pane nobody opens on a headless run.

    Asked as a discrimination, because "the row mentions Y" is true of
    every colour row this readout has ever printed and could not fail:
    the row for a Y disagreement must differ from the row for the same
    page with the disagreement on C, and both must differ from the row
    for a page whose evidence fits.  The spelling itself is the build's,
    and `test_h3_field_pane` is where the string is frozen.
    """
    loud_y = _field_row(2)
    loud_c = _field_row(0)
    quiet = _field_row(-1)
    assert loud_y != quiet, "a plane at odds with its field is invisible"
    assert loud_y != loud_c, "the row does not say WHICH plane disagrees"
    assert all(name in loud_y for name in "CMY"), loud_y


# --------------------------------------------------------------------
# R6. the refinement the newer field re-opens
# --------------------------------------------------------------------

#: The review's own case: an accepted field-7 pose at 0.30, whose
#: baseline under field 8 is 0.50, and a candidate the gate approves at
#: 0.40.  The 0.30 is not a rival — it was measured through a sampling
#: geometry the page no longer has.
STANDING_LOGLOSS = 0.30
BASELINE_LOGLOSS = 0.50
CANDIDATE_LOGLOSS = 0.40


def _refined_colour_window(field_revision: int) -> tuple:
    """A placed colour window with one adopted refinement standing.

    Production's own store and fold: the certificates are the fixture's,
    the reach is the placement's, and the basis is built by the row that
    builds it in the run.
    """
    store = plane_fx._placed_store(plane_fx._tile_certificates(0, 0))
    reach = color_refine.reach_certified(store, plane_fx.PAGE,
                                         store.window_reach(plane_fx.WID))
    assert reach, "the fixture placement certified nothing to refine over"
    placement = dataclasses.replace(
        store.placement(plane_fx.WID), route=data.ROUTE_REFINE,
        quality=STANDING_LOGLOSS,
        refine_basis=color_refine.refine_basis(reach, field_revision))
    assert store._fold(placement)[0], "the standing refinement did not land"
    return store, reach, placement


def _moved(placement: data.Placement) -> tuple[float, ...]:
    terms = list(float(term) for term in placement.native_affine)
    terms[2] += 0.1
    return tuple(terms)


def _field(store: object, ordinal: int) -> None:
    store._ingest(_h3_facts.plane_field(page=plane_fx.PAGE, ordinal=ordinal,
                                        tiles_yx=plane_fx.TILES_YX))


def test_a_gate_approved_refinement_lands_under_the_newer_field():
    """Review R6, end to end: eligible, gated, folded, and then done.

    The refinement is approved against the pose it replaces UNDER field
    8 — 0.50 to 0.40 — and the 0.30 it is compared with at the merge was
    measured through field 7.  Before this the fold ranked those two
    losses against each other, kept the old affine and left the window
    eligible, so the lane refitted the same window for the rest of the
    run and never adopted anything.  The last assertion is the one that
    says the churn stopped.
    """
    store, reach, placement = _refined_colour_window(7)
    _field(store, 8)
    assert color_refine._color_refine_eligible(store, plane_fx.WID)
    revision = refine.Revision(
        True, refine.OUTCOME_ADOPTED, _moved(placement),
        baseline_logloss=BASELINE_LOGLOSS,
        candidate_logloss=CANDIDATE_LOGLOSS,
        basis=color_refine.refine_basis(reach, 8))
    _changed, keys, _kind = store._fold(
        refine.RefineOutcome(plane_fx.WID, revision))
    standing = store.placement(plane_fx.WID)
    assert (KEY_POSE_AFFINE, plane_fx.WID) in keys, (
        "the pose moved and nothing was woken to read it again")
    assert standing.native_affine == _moved(placement)
    assert standing.quality == CANDIDATE_LOGLOSS, (
        "the fold carries the candidate's TRUE held-out loss, not a "
        "number chosen to win the comparison")
    assert data.basis_field_revision(standing.refine_basis) == 8
    assert not color_refine._color_refine_eligible(store, plane_fx.WID), (
        "same certificates, same field: there is nothing left to fit")


def test_a_refused_candidate_is_still_refused_when_the_field_moved():
    """R6 moves the ORDER, never the gate.

    A newer basis is not evidence of a better pose; the held-out
    comparison is.  A refusal under field 8 leaves the field-7 pose
    standing untouched — and leaves the window eligible, because the
    field it was fitted through is still not the one the page has.
    """
    store, _reach, placement = _refined_colour_window(7)
    _field(store, 8)
    revision = refine.Revision(
        False, "pose_gate_failed", None,
        baseline_logloss=BASELINE_LOGLOSS,
        candidate_logloss=BASELINE_LOGLOSS + 0.1)
    store._fold(refine.RefineOutcome(plane_fx.WID, revision))
    standing = store.placement(plane_fx.WID)
    assert standing.native_affine == placement.native_affine
    assert standing.quality == STANDING_LOGLOSS
    assert data.basis_field_revision(standing.refine_basis) == 7
    assert color_refine._color_refine_eligible(store, plane_fx.WID)


def test_a_field_that_lands_during_a_job_is_not_lost():
    """The race the ordinal does not settle, at the bookmark.

    A solve can publish while a refinement job is in flight: the job was
    prepared through field 8 and folds a field-8 basis into a page whose
    field is 9.  The fold is right to take it — the gate proved it — and
    the run must still come back, which is the scheduler's business and
    not the cell's.  The field fact woke the worker's subscription while
    it was inflight, so BOTH halves of the return are set when the job
    merges — the pending bit, the only thing `engine._merge` re-pushes
    on, and a version above the floor a re-fire is skipped at — and the
    next prepare reads 9.
    """
    store, reach, placement = _refined_colour_window(7)
    _field(store, 8)
    store._births(placement)
    worker = store._bookmarks[(color_refine.PLUGIN, plane_fx.WID)]
    # what `engine._fill` does at the fire that prepares the job
    worker.tried_version = worker.version
    worker.inflight = True
    assert color_refine.prepare_color_refine(
        store, plane_fx.WID, refine.STAGE_REFINE) is not None
    _field(store, 9)
    store._ingest(refine.RefineOutcome(plane_fx.WID, refine.Revision(
        True, refine.OUTCOME_ADOPTED, _moved(placement),
        baseline_logloss=BASELINE_LOGLOSS,
        candidate_logloss=CANDIDATE_LOGLOSS,
        basis=color_refine.refine_basis(reach, 8))))
    worker.inflight = False
    assert data.basis_field_revision(
        store.placement(plane_fx.WID).refine_basis) == 8
    assert worker.pending is True, (
        "`engine._merge` re-pushes only a pending worker, so without the "
        "bit the row leaves the queue and nothing fires it again")
    assert worker.version > worker.tried_version, (
        "and the re-fire would be skipped at the version floor, so the "
        "field the solve published during the job would never be fitted")
    assert color_refine._color_refine_eligible(store, plane_fx.WID)
    assert store.field_revision(plane_fx.PAGE) == 9, (
        "the field the next prepare hands the job is the page's latest")


def test_a_resumed_placement_is_ranked_on_the_field_it_was_fitted_through(
        tmp_path):
    """The ordinal is durable because the BASIS is durable.

    A snapshot carries the placement, marker and all — the marker is the
    one string-headed entry in a tuple of int keys, and the spine encodes
    tuples and strings alike — so a resumed run ranks the standing pose
    exactly as the run that wrote it did.  Nothing new is stored for R6;
    this says so out loud, because an ordinal that changed across a
    resume would re-open every refined window on the page.
    """
    basis = color_refine.refine_basis(((0, 0, 0, "c"), (0, 0, 1, "m")), 8)
    placement = dataclasses.replace(
        _h3_facts.placement(), route=data.ROUTE_REFINE,
        quality=CANDIDATE_LOGLOSS, refine_basis=basis)
    path = tmp_path / snapshot.NAME
    snapshot.write(path, (placement,))
    restored, = snapshot.read(path)
    assert restored.refine_basis == basis
    assert data.basis_field_revision(restored.refine_basis) == 8
    assert data.placement_ordinal(restored) == data.placement_ordinal(
        placement)
