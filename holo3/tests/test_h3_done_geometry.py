"""DONE-GEOMETRY: the certified-done suppression gate.

THE LAW.  A window may be suppressed only when every tile it could
still contribute evidence to is certified in EVERY stream of the
coding.  Certification is terminal, so the verdict is monotone and the
suppression can never cost a certificate.  Two halves, one derivation
(`store.window_fully_done`): a placed window is judged on its exact
tile reach, an unplaced one on the pose-free projection of the region's
committed poses onto its supported extent.

WHAT THE GATE MAY NEVER TOUCH.  Rows that act on uncertified tiles
(`tiles.scan|union|retry`) are outside it — a tile row's own
subject-level "certified -> refuse" logic is the only gate there.  And
suppression is fire-only: a done window's standing evidence keeps
serving the region context fit and the tile cover, because stopping
future work must never remove a standing fact.

WHY NO UNCERTIFIED TILE CAN LOSE EVIDENCE.  The tiles a window's
evidence covers are cut from the same cells the reach is derived from
(`tiles.evidence_cover_cells` keeps a payload subset of
`page_cells_yx`), so cover ⊆ reach.  A done window therefore has every
tile it covers certified: the case "an open tile depended on a
suppressed window" does not exist.  `test_every_tile_the_evidence_
covers_lies_inside_the_gated_reach` pins that containment.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import tempfile
import textwrap
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from holo3 import data, engine
from holo3.descriptor import PluginDescriptor
from holo3.plugins import (
    calibrate,
    color_refine,
    place,
    place_sched,
    refine,
    revisit,
    tiles,
)
from holo3.tests import _h3_facts, _h3_sims, _h3_support

GATE = "window_fully_done"

# the gate lives in exactly these rows; a tile row appearing here is a
# charter violation, not a golden to update
GATE_CALL_SITES: dict[str, int] = {
    "plugins/calibrate.py": 1,
    "plugins/place_sched.py": 1,
    "plugins/revisit.py": 2,
}

A_EXTENT = (0, 0, 200, 200)
B_EXTENT = (0, 100, 200, 300)
C_EXTENT = (0, 0, 40, 40)
B_ORIGIN_YX = (0, 32)
REGION_KEY = (_h3_facts.CAPTURE_ID, 0, 0)


def _engine(format_ref: str = _h3_facts.FORMAT_REF) -> engine._Engine:
    request = data.DecodeRequest(
        scans=(Path("scan.tiff"),), dpis=(1200.0,), format_ref=format_ref,
        max_pages=1, workers=1, complete=False, no_close=False,
        diag_port=None,
        run_dir=Path(tempfile.mkdtemp(prefix="h3-donegeo-")))
    instance = engine._Engine(request, [])
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.survey())
    return instance


def _place(instance: engine._Engine, wid: tuple, ordinal: int,
           origin_yx: tuple[int, int] = (0, 0)) -> None:
    if instance.window(wid) is None:
        instance._ingest(_h3_facts.window(wid=wid, ordinal=ordinal))
    instance._ingest(replace(_h3_facts.placement(wid=wid),
                             page_origin_yx=origin_yx))
    instance._ingest(_h3_facts.evidence(wid=wid,
                                        cells=instance.page_cells(wid)))


def _neighbours() -> tuple[engine._Engine, tuple, tuple, tuple]:
    """A: reach {(0,0)} — certified.  B: reach {(0,0), (0,1)} — open.
    C: never placed, extent inside A's projected done cells."""
    instance = _engine()
    wid_a = instance.windows()[0]
    assert wid_a[3] == A_EXTENT
    wid_b = (_h3_facts.CAPTURE_ID, 0, 0, B_EXTENT)
    wid_c = (_h3_facts.CAPTURE_ID, 0, 0, C_EXTENT)
    _place(instance, wid_a, ordinal=0)
    _place(instance, wid_b, ordinal=1, origin_yx=B_ORIGIN_YX)
    instance._ingest(_h3_facts.window(wid=wid_c, ordinal=2))
    instance._ingest(_h3_facts.certificate(0, 0, 0))
    return instance, wid_a, wid_b, wid_c


@pytest.fixture()
def neighbours() -> tuple:
    return _neighbours()


def _production_files() -> tuple[Path, ...]:
    return _h3_support.source_files(
        _h3_support.HOLO3_ROOT,
        exclude_dirs=("__pycache__", "conversion_docs", "tests", "measure"))


def _gate_uses(path: Path) -> int:
    tree = ast.parse(path.read_text(), filename=str(path))
    return sum(1 for node in ast.walk(tree)
               if isinstance(node, ast.Attribute) and node.attr == GATE)


def _gate_definitions(path: Path) -> int:
    tree = ast.parse(path.read_text(), filename=str(path))
    return sum(1 for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef) and node.name == GATE)


def test_the_gate_is_wired_into_the_declared_window_rows_and_nowhere_else():
    found = {}
    definitions = {}
    for path in _production_files():
        rel = str(path.relative_to(_h3_support.HOLO3_ROOT))
        uses = _gate_uses(path)
        if uses:
            found[rel] = uses
        if _gate_definitions(path):
            definitions[rel] = _gate_definitions(path)
    _h3_support.assert_golden("done-gate call sites", found, GATE_CALL_SITES)
    _h3_support.assert_golden("done-gate derivations", definitions,
                              {"store.py": 1})
    assert "plugins/tiles.py" not in found, (
        "the payload rows act on uncertified tiles: the done gate must "
        "never reach them")


def test_the_gate_holds_only_when_every_stream_of_the_tile_is_certified():
    instance = _engine(_h3_sims.COLOR_FORMAT_REF)
    wid = instance.windows()[0]
    _place(instance, wid, ordinal=0)
    assert instance.window_reach(wid) == ((0, 0),)
    verdicts = []
    for stream in instance.row.streams:
        instance._ingest(data.Certificate(
            page=0, ty=0, tx=0, stream_id=stream.stream_id,
            user_bits=np.zeros(8, np.uint8), source="probe"))
        verdicts.append(instance.window_fully_done(wid))
    assert [stream.stream_id for stream in instance.row.streams] == [
        "C", "M", "Y"]
    assert verdicts == [False, False, True], (
        "a tile with C and M certified and Y open is NOT done: the gate "
        "is the AND across streams")


def test_a_window_with_one_open_tile_in_its_reach_is_never_done(neighbours):
    instance, wid_a, wid_b, _wid_c = neighbours
    assert instance.window_reach(wid_a) == ((0, 0),)
    assert instance.window_reach(wid_b) == ((0, 0), (0, 1))
    assert instance.window_fully_done(wid_a) is True
    assert instance.window_fully_done(wid_b) is False
    instance._ingest(_h3_facts.certificate(0, 0, 1))
    assert instance.window_fully_done(wid_b) is True


def test_the_gate_is_shut_while_no_certificate_exists():
    instance = _engine()
    wid = instance.windows()[0]
    _place(instance, wid, ordinal=0)
    assert instance.window_fully_done(wid) is False
    assert instance.window_extent_done(wid) is False


def test_done_ness_is_monotone_through_further_folds(neighbours):
    instance, wid_a, wid_b, wid_c = neighbours
    assert instance.window_fully_done(wid_a) is True
    assert instance.window_extent_done(wid_c) is True
    instance._ingest(_h3_facts.certificate(0, 0, 1))
    instance._ingest(_h3_facts.certificate(0, 1, 1))
    instance._ingest(_h3_facts.evidence(
        wid=wid_a, cells=instance.page_cells(wid_a), score=0.5))
    instance._ingest(_h3_facts.evidence(
        wid=wid_b, cells=instance.page_cells(wid_b), score=0.5))
    assert instance.window_fully_done(wid_a) is True, (
        "certificates are terminal, so a done window stays done through "
        "any later fold at a fixed pose")
    assert instance.window_extent_done(wid_c) is True


def test_every_tile_the_evidence_covers_lies_inside_the_gated_reach(
        neighbours):
    instance, wid_a, wid_b, _wid_c = neighbours
    for wid in (wid_a, wid_b):
        cover = {(key[1], key[2])
                 for key in instance.window_cover_tiles(wid)}
        reach = set(instance.window_reach(wid)) | set(
            instance.evidence_reach(wid))
        assert cover, wid
        assert cover <= reach, (
            "the gate requires every reach tile certified; if a covered "
            "tile could sit outside the reach, an open tile could lose "
            "the evidence of a suppressed window")


def test_a_done_window_keeps_its_evidence_its_cover_and_its_certainty(
        neighbours):
    instance, wid_a, _wid_b, _wid_c = neighbours
    standing = instance.evidence(wid_a)
    cover = instance.window_cover_tiles(wid_a)
    assert calibrate._window_eligible(instance, wid_a) is False
    assert revisit._revisit_eligible(instance, wid_a) is False
    assert place_sched._place_retire(instance, wid_a) is True
    assert instance.evidence(wid_a) is standing, (
        "suppression stops future work; it never removes a standing fact")
    assert instance.window_cover_tiles(wid_a) == cover
    assert wid_a in instance.evidences()
    shared = (0, 0, 0, _h3_facts.CAPTURE_ID, 0)
    assert wid_a in instance.tile_cover(shared)[0]
    candidates, _order = tiles._tile_candidates(
        instance, 0, 0, 0, _h3_facts.CAPTURE_ID, 0)
    assert len(candidates) == len(instance.tile_cover(shared)[0])
    assert all(row[2].shape[0] for row in candidates), (
        "the assembly of a tile this done window covers still cuts its "
        "cells out of the standing evidence")


def test_the_region_context_fit_still_pools_a_done_windows_evidence(
        neighbours):
    instance, wid_a, wid_b, _wid_c = neighbours
    assert instance.window_fully_done(wid_a) is True
    assert calibrate._ctx_eligible(instance, REGION_KEY) is True
    job = calibrate.prepare_ctx(instance, REGION_KEY, "calibrate")
    assert job is not None
    pooled = {row.window_id for row in
              tuple(instance.evidence(wid) for wid in instance.evidences()
                    if wid[:3] == REGION_KEY)}
    assert pooled == {wid_a, wid_b}, (
        "the done window's evidence keeps serving the live neighbour "
        "through the shared region fit")


def test_a_neighbour_window_with_an_open_tile_keeps_every_row(neighbours):
    instance, _wid_a, wid_b, _wid_c = neighbours
    assert instance.window_fully_done(wid_b) is False
    assert calibrate._window_eligible(instance, wid_b) is True
    assert refine._refine_eligible(instance, wid_b) is True
    assert place_sched._place_retire(instance, wid_b) is True, (
        "an accepted placement retires the place row on its own flag, "
        "not on the done gate")


def test_the_payload_rows_stay_live_while_a_neighbour_window_is_done(
        neighbours):
    instance, wid_a, _wid_b, _wid_c = neighbours
    open_tile = (0, 0, 1, _h3_facts.CAPTURE_ID, 0)
    certified_tile = (0, 0, 0, _h3_facts.CAPTURE_ID, 0)
    assert instance.window_fully_done(wid_a) is True
    assert tiles.SCAN_DESCRIPTOR.eligible(instance, open_tile) is True
    assert tiles.SCAN_DESCRIPTOR.retire(instance, open_tile) is False
    assert tiles.SCAN_DESCRIPTOR.eligible(instance, certified_tile) is False


def test_the_two_refine_rows_already_refuse_every_done_window(neighbours):
    instance, wid_a, wid_b, _wid_c = neighbours
    assert refine._refine_eligible(instance, wid_a) is False, (
        "refine's own reach predicate subsumes the done gate: adding a "
        "second call would be a second implementation of one fact")
    assert refine._refine_retire(instance, wid_a) is True
    assert refine._refine_eligible(instance, wid_b) is True
    colour = _engine(_h3_sims.COLOR_FORMAT_REF)
    wid = colour.windows()[0]
    _place(colour, wid, ordinal=0)
    for stream in colour.row.streams:
        colour._ingest(data.Certificate(
            page=0, ty=0, tx=0, stream_id=stream.stream_id,
            user_bits=np.zeros(8, np.uint8), source="probe"))
    assert colour.window_fully_done(wid) is True
    assert color_refine._color_refine_retire(colour, wid) is True, (
        "the colour refinement row retires on the same fact, and retire "
        "runs before eligible at every pop")


def test_the_pose_free_branch_retires_a_never_placed_covered_window(
        neighbours):
    instance, _wid_a, _wid_b, wid_c = neighbours
    assert instance.placement(wid_c) is None
    assert instance.window_fully_done(wid_c) is True
    assert place_sched._place_retire(instance, wid_c) is True
    assert revisit._revisit_eligible(instance, wid_c) is False
    assert revisit.prepare_revisit(instance, wid_c, refine.STAGE_REFINE) \
        is None


def test_the_pose_free_branch_keeps_a_window_reaching_open_cells(
        neighbours):
    instance, _wid_a, _wid_b, _wid_c = neighbours
    wid = (_h3_facts.CAPTURE_ID, 0, 0, (0, 0, 80, 80))
    instance._ingest(_h3_facts.window(wid=wid, ordinal=3))
    assert instance.window_extent_done(wid) is False, (
        "the extent runs past the cells the certified tile projects to"
    )
    assert place_sched._place_retire(instance, wid) is False
    assert revisit._revisit_eligible(instance, wid) is True


# ---------------------------------------------------------------- the door
#
# The gate has exactly ONE door and it is the scheduler's, not the pass's.
# `engine._fill` consults `descriptor.retire` before `descriptor.prepare`,
# so a done window is retired before its job exists — which is why a
# second copy of the test inside `place.run_window_pass` was unreachable
# by construction and is gone.  These four pins are the "did it bite?"
# evidence at the seam: the door fires, the door does NOT fire on an open
# window, the cause reaches the record, and the second copy cannot come
# back.  Real-sheet evidence for the same claim:
# `measure/donegeo_realstate.py` (sheet I, 2026-08-31 — the gate's verdict
# reproduced the run's 240 suppressed / 62 fired split exactly, both ways,
# on two archived resume runs).


class _RecordingExecutor:
    """Enough executor for `_fill`; it records what was submitted."""

    def __init__(self) -> None:
        self.submitted: list = []

    def submit(self, job: object) -> Future:
        self.submitted.append(job)
        future: Future = Future()
        future.set_result(data.JobResult((), (), 0.0))
        return future


def _door_probe(calls: list) -> PluginDescriptor:
    """The real place descriptor, with retire/prepare made audible.

    `prepare` is stubbed to None so the pass is never built (it would
    want rasters); the pin is the ORDER of the two consults, which is
    what makes a pass-side gate unreachable.
    """
    base = place_sched.PLACE_DESCRIPTOR

    def retire(store: object, subject: object) -> bool:
        calls.append("retire")
        return base.retire(store, subject)

    def prepare(store: object, subject: object, stage: str) -> None:
        calls.append("prepare")
        return None

    return replace(base, retire=retire, prepare=prepare)


def _pop_once(instance: engine._Engine, wid: tuple, calls: list,
              monkeypatch: pytest.MonkeyPatch) -> _RecordingExecutor:
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                        {"place": _door_probe(calls)})
    instance._frontier = []
    worker = instance._bookmarks[("place", wid)]
    worker.seat_seq = -1
    worker.version += 1
    instance._push_worker(worker)
    assert instance._frontier, "the window must be seated to be popped"
    executor = _RecordingExecutor()
    instance._fill(executor)
    return executor


def test_the_door_retires_a_done_window_before_a_job_can_exist(
        neighbours, monkeypatch):
    instance, _wid_a, _wid_b, wid_c = neighbours
    calls: list = []
    before = len(instance._events)
    executor = _pop_once(instance, wid_c, calls, monkeypatch)
    assert calls == ["retire"], (
        "retire runs first and short-circuits: prepare is never reached, "
        "so a done gate inside the pass could never fire")
    assert executor.submitted == []
    assert instance._bookmarks[("place", wid_c)].retired is True
    retired = [event for event in instance._events[before:]
               if isinstance(event, data.WindowRetired)]
    assert [(event.extent_cells, event.cause) for event in retired] == [
        (C_EXTENT, place_sched.RETIRE_DONE)]


def test_the_door_lets_an_open_window_through_to_its_pass(
        neighbours, monkeypatch):
    instance, _wid_a, _wid_b, _wid_c = neighbours
    wid = (_h3_facts.CAPTURE_ID, 0, 0, (0, 0, 80, 80))
    instance._ingest(_h3_facts.window(wid=wid, ordinal=3))
    assert instance.window_extent_done(wid) is False
    calls: list = []
    before = len(instance._events)
    _pop_once(instance, wid, calls, monkeypatch)
    assert calls == ["retire", "prepare"], (
        "the control: a window the gate leaves open reaches its pass")
    assert instance._bookmarks[("place", wid)].retired is False
    assert not [event for event in instance._events[before:]
                if isinstance(event, data.WindowRetired)]


def test_the_retirement_cause_names_the_clause_that_fired(neighbours):
    instance, wid_a, _wid_b, wid_c = neighbours
    assert place_sched.place_retire_cause(instance, wid_a) == \
        place_sched.RETIRE_PLACED
    assert place_sched.place_retire_cause(instance, wid_c) == \
        place_sched.RETIRE_DONE
    open_wid = (_h3_facts.CAPTURE_ID, 0, 0, (150, 150, 190, 190))
    instance._ingest(_h3_facts.window(wid=open_wid, ordinal=4))
    assert place_sched.place_retire_cause(instance, open_wid) is None
    state = instance.place_stage(open_wid)
    state.tried |= {seed.candidate_id for seed in
                    place_sched.untried_consult(instance, state, wide=True)}
    state.centre_spent = True
    state.rest_spent = True
    state.wide_spent = True
    state.cold_armed = True
    state.cold_live_spent = True
    assert place_sched.ladder_stage(instance, state, open_wid) is None
    instance._place_repush(state)
    assert state.retired is True and not state.children, (
        "a 40-cell window is under the subdivision floor: the exhausted "
        "ladder is the terminal clause")
    assert place_sched.place_retire_cause(instance, open_wid) == \
        place_sched.RETIRE_EXHAUSTED


def test_the_placement_pass_carries_no_second_copy_of_the_gate():
    fields = {field.name for field in dataclasses.fields(place.WindowPass)}
    assert "done_cells" not in fields, (
        "the pass takes no done input: the door already answered")
    source = inspect.getsource(place.run_window_pass)
    assert "done_covers" not in source and "done_cells" not in source, (
        "an unreachable duplicate of the gate is worse than none — it "
        "reads as a live gate that never fires (2026-08-31 finding)")


def _emitted_outcome_forms() -> tuple[set[str], set[tuple[str, str]]]:
    """Every `WindowPassResult.outcome` `place` can construct.

    Read off the source, not declared: the two constructors are
    `_settled(job, <outcome>, ...)` and the accepted tail's direct
    `WindowPassResult(<outcome>, ...)`.  Plain literals come back as
    themselves; the f-string families come back as (prefix, suffix), so
    a store branch naming one of their members still matches.
    """
    tree = ast.parse(inspect.getsource(place), filename="place.py")
    literals: set[str] = set()
    patterns: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) \
                or not isinstance(node.func, ast.Name):
            continue
        if node.func.id == "_settled" and len(node.args) > 1:
            argument = node.args[1]
        elif node.func.id == "WindowPassResult" and node.args:
            argument = node.args[0]
        else:
            continue
        if isinstance(argument, ast.Constant) \
                and isinstance(argument.value, str):
            literals.add(argument.value)
        elif isinstance(argument, ast.JoinedStr):
            parts = ["", ""]
            side = 0
            for piece in argument.values:
                if isinstance(piece, ast.FormattedValue):
                    side = 1
                elif isinstance(piece, ast.Constant):
                    parts[side] += piece.value
            patterns.add((parts[0], parts[1]))
    return literals, patterns


def _store_outcome_branches() -> set[str]:
    """Every literal `_Store._fold_place_outcome` compares `outcome` to."""
    source = textwrap.dedent(
        inspect.getsource(engine._Store._fold_place_outcome))
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Compare):
            continue
        if not isinstance(node.left, ast.Name) or node.left.id != "outcome":
            continue
        for value in node.comparators:
            if isinstance(value, ast.Constant) \
                    and isinstance(value.value, str):
                found.add(value.value)
    return found


def test_the_store_folds_only_outcomes_the_placement_pass_can_produce():
    """The second unreachable copy, and the pin that keeps it gone.

    `store._fold_place_outcome` carried `outcome == "done_covered" ->
    retire` — dead the moment the pass stopped emitting it, and dead
    before that too, since the door retires first.  This checks the
    direction that matters in BOTH senses: no fold branch names an
    outcome placement cannot emit (a dead branch reads as a live one),
    and the check is derived from the source rather than declared, so a
    new outcome cannot quietly appear on one side only.
    """
    literals, patterns = _emitted_outcome_forms()
    assert "accepted" in literals and "pose_refused" in literals, (
        "the extractor found nothing: it is reading the wrong source")

    def emitted(name: str) -> bool:
        return name in literals or any(
            name.startswith(head) and name.endswith(tail)
            and len(name) > len(head) + len(tail)
            for head, tail in patterns)

    branches = _store_outcome_branches()
    assert branches, "the extractor found no fold branches"
    unreachable = {name for name in branches if not emitted(name)}
    assert unreachable == set(), (
        f"the fold branches on outcomes placement cannot produce: "
        f"{sorted(unreachable)}")
    assert not emitted("done_covered"), (
        "done_covered is not a pass outcome — leaving the frontier is a "
        "retirement, not a settle")


def test_no_placement_outcome_can_retire_a_window_for_being_done(
        neighbours):
    """DID IT BITE: the door is the ONLY door.

    A done window is driven through the fold with every outcome the pass
    can produce.  None of them may retire it — the two that DO retire
    (`insufficient_support`, and exhaustion via the repush tail) are
    ladder facts, not done-ness.  The door then retires the same window
    on the first pop, naming done-geometry.
    """
    instance, _wid_a, _wid_b, wid_c = neighbours
    assert instance.window_fully_done(wid_c) is True
    for outcome in ("accepted", "pose_refused", "straddle_audit_refused",
                    "consult_refused", "wide_refused", "nothing_to_try",
                    "no_word_candidate_centre", "no_word_candidate_rest",
                    "cold_refused_cold_live", "cold_refused_cold_rest"):
        state = place_sched.WindowState(window=instance.window(wid_c))
        instance._place_stages[wid_c] = state
        # stated so a fixture drift fails on the PRECONDITION rather
        # than reading as the conclusion: this window still has ladder
        # left, so any retirement here would have to be done-ness
        assert place_sched.ladder_stage(instance, state, wid_c) is not None
        instance._fold(_h3_facts.place_outcome(outcome=outcome, wid=wid_c))
        assert state.retired is False, (
            f"{outcome!r} retired a done window through the fold: the "
            f"done gate has grown a second door")
    # `insufficient_support` is deliberately absent: it retires on a
    # LADDER fact (less paper cannot help), which is not done-ness
    assert place_sched.place_retire_cause(instance, wid_c) == \
        place_sched.RETIRE_DONE, (
        "and the one door still answers for this window")
