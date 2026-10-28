from __future__ import annotations

import ast
import io
import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from holo3 import data
from holo3.diag import model as diag_model
from holo3.diag import readout as diag_readout
from holo3.diag import report as diag_report
from holo3.diag import panes, server
from holo3.format import pilots
from holo3.plugins import place, place_sched
from holo3.plugins import tiles as tiles_plugin

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

CAP_A = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
FORMAT_ID = "holo3/v2/c2-cmy8-r0700@3x3"

EXTENT = (0, 0, 30, 30)
WID_L1 = (CAP_A, 1, 0, EXTENT)
WKEY_A = (CAP_A, 0, EXTENT)

# every settle is a REFUSAL that leaves the window live; suppression is
# not a settle (done-geometry retires at the scheduler door and arrives
# as a WindowRetired carrying its cause)
SETTLED_VOCABULARY = frozenset({
    "pose_refused", "insufficient_support", "nothing_to_try",
    "wide_refused", "consult_refused", "straddle_audit_refused",
    "cold_refused_cold_live", "cold_refused_cold_rest",
    "no_word_candidate_centre", "no_word_candidate_rest"})

RETIRE_VOCABULARY = frozenset({
    place_sched.RETIRE_PLACED, place_sched.RETIRE_EXHAUSTED,
    place_sched.RETIRE_DONE})

STATUS_KEYS = frozenset({
    "revision", "rows", "now", "last", "captures", "pages", "panes",
    "pane_revs", "scheduler", "close", "plane_certs", "replayed",
    "fold_errors"})
SCHEDULER_KEYS = frozenset({"plugins", "attempts_hist", "stale_skips",
                            "wakes", "available", "churn",
                            "consult_cpu_s", "retired", "retire_causes"})
CLOSE_KEYS = frozenset({"status", "consulted", "certified",
                        "symbols_used", "k_total", "counting",
                        "metadata_rank", "metadata_n_unique",
                        "blocks", "verified"})
PLUGIN_KEYS = frozenset({"plugin", "queued", "inflight", "jobs", "cpu_s",
                         "certificates", "poses", "words"})

ROW_PREFIXES = ("format   ", "capture  ", "frontier ", "work     ",
                "tiles    ", "close    ")


def _run(streams: tuple[str, ...] = ("K",),
         tiles_yx: tuple[int, int] = (3, 3), pages: int = 1,
         workers: int = 4) -> data.RunOpen:
    return data.RunOpen(format_id=FORMAT_ID, pages=pages, tiles_yx=tiles_yx,
                        stream_ids=streams, n_captures=1, workers=workers)


def _capture(capture: str, ordinal: int = 0,
             shape_yx: tuple[int, int] = (900, 900)) -> data.CaptureOpen:
    return data.CaptureOpen(capture=capture, dpi=2400.0, shape_yx=shape_yx,
                            channels=1, duplicate=False, ordinal=ordinal)


def _mark(region_index: int, support_cells: int = 300,
          origin_yx: tuple[int, int] = (100, 100),
          with_cells: bool = False) -> data.RegionMark:
    return data.RegionMark(
        region_index=region_index, origin_yx=origin_yx,
        shape_cells=(20, 20), pitch_px=8.0, support_cells=support_cells,
        cells=np.ones((20, 20), bool) if with_cells else None,
        step_px=10 if with_cells else 0)


def _survey(capture: str, marks: tuple[data.RegionMark, ...],
            preview: np.ndarray | None = None) -> data.SurveyDone:
    return data.SurveyDone(capture=capture, n_regions=len(marks),
                           regions=marks, pitch_class="c2", preview=preview,
                           preview_decim=4)


def _scheduled(stage: str, region_index: int = 0,
               extent: tuple[int, int, int, int] = EXTENT,
               level_index: int = 0) -> data.WindowScheduled:
    return data.WindowScheduled(capture=CAP_A, level_index=level_index,
                                region_index=region_index,
                                extent_cells=extent, stage=stage,
                                cost=place.STAGE_COST[stage])


def _settled(state: str, region_index: int = 0,
             extent: tuple[int, int, int, int] = EXTENT
             ) -> data.WindowSettled:
    return data.WindowSettled(capture=CAP_A, level_index=0,
                              region_index=region_index,
                              extent_cells=extent, state=state)


def _pose(region_index: int = 0,
          extent: tuple[int, int, int, int] = EXTENT, page: int = 0,
          origin_yx: tuple[int, int] = (0, 0), rot_k: int = 0,
          shape_yx: tuple[int, int] = (64, 64),
          accepted: bool = True,
          native_affine: tuple = (8.0, 0.0, 100.0, 0.0, 8.0, 100.0),
          ) -> data.PoseCommitted:
    return data.PoseCommitted(
        capture=CAP_A, level_index=0, region_index=region_index,
        extent_cells=extent, page=page, route=place.ROUTE_WORD,
        mismatch=0.1, accepted=accepted, page_origin_yx=origin_yx,
        rot_k=rot_k, pitch_px=8.0, native_affine=native_affine,
        shape_yx=shape_yx)


def _tile(stream_id: str, ty: int, tx: int, result: str,
          page: int = 0) -> data.TileOutcome:
    return data.TileOutcome(page=page, ty=ty, tx=tx, stream_id=stream_id,
                            source="tiles/scan", result=result, bp_iters=8)


def _job_done(plugin: str, subject: object, cpu_s: float,
              n_certificates: int = 0, n_poses: int = 0,
              n_words: int = 0, cost: int = 20) -> data.JobDone:
    return data.JobDone(plugin=plugin, subject=subject, cost=cost,
                        cpu_s=cpu_s, n_certificates=n_certificates,
                        n_poses=n_poses, n_words=n_words)


def _stat_inflight(*jobs: tuple) -> data.EngineStat:
    return data.EngineStat(queued=(), inflight=len(jobs), stale_skips=0,
                           retired=0, attempts_hist=(), wakes=0,
                           inflight_jobs=tuple(jobs))


def _packed(bits: object) -> bytes:
    mask = np.zeros(pilots.N_WORD_SITES, bool)
    mask[list(bits)] = True
    return np.packbits(mask).tobytes()


def _fold(events: tuple) -> diag_model.DiagModel:
    return diag_model.fold(diag_model.empty(), events)


def _raster(model: diag_model.DiagModel, pane: str,
            selector: int) -> np.ndarray:
    png = panes.render_pane(model, pane, selector)
    assert png is not None and png[:8] == PNG_MAGIC
    return np.asarray(Image.open(io.BytesIO(png)).convert("RGB"))


def _rgb(pixel: np.ndarray) -> tuple[int, int, int]:
    return tuple(int(v) for v in pixel)


PREFIX_EXPANSIONS = {
    "cold_refused_": tuple(place.COLD_STAGES),
    "no_word_candidate_": tuple(place_sched.WORD_STAGE_OF.values()),
}


def _literal_states(node: ast.expr) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _literal_states(node.body) | _literal_states(node.orelse)
    if isinstance(node, ast.JoinedStr):
        head = node.values[0]
        assert isinstance(head, ast.Constant), ast.dump(node)
        return {head.value + suffix
                for suffix in PREFIX_EXPANSIONS[head.value]}
    raise AssertionError(f"unrecognized settled state: {ast.dump(node)}")


def place_settled_vocabulary() -> frozenset[str]:
    tree = ast.parse(Path(place.__file__).read_text())
    states: set[str] = set()
    reasons: set[str] = set()
    saw_reason_arg = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "reason" in names:
                reasons |= _literal_states(node.value)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "_settled" and len(node.args) > 1):
            arg = node.args[1]
            if isinstance(arg, ast.Name):
                saw_reason_arg = True
            else:
                states |= _literal_states(arg)
    return frozenset(states | (reasons if saw_reason_arg else set()))


PRE_EVENTS: tuple = (_run(streams=("C", "M", "Y")), _capture(CAP_A))

ROWS_EVENTS: tuple = PRE_EVENTS + (
    _survey(CAP_A, (_mark(0, support_cells=300),
                    _mark(1, support_cells=200, origin_yx=(400, 400)))),
    data.CalibrateAdopted(capture=CAP_A, pool_id="pool-0", adopted=True,
                          reason="adopted"),
    data.CalibrateAdopted(capture=CAP_A, pool_id="pool-1", adopted=False,
                          reason="thin_support"),
    data.EngineStat(queued=(("place", 3), ("tiles", 5)), inflight=2,
                    stale_skips=7, retired=1,
                    attempts_hist=(("1", 4), ("2", 1)),
                    consult_cpu_s=1.5),
    _job_done("tiles", "page0", cpu_s=1.25, n_certificates=2),
    _job_done("place", WID_L1, cpu_s=0.85, n_poses=1, n_words=1),
    _tile("C", 0, 0, tiles_plugin.OUTCOME_CERTIFIED),
    _tile("M", 0, 1, tiles_plugin.OUTCOME_CERTIFIED),
    _tile("Y", 1, 0, tiles_plugin.OUTCOME_BELOW_FLOOR),
    _tile("C", 1, 1, tiles_plugin.OUTCOME_FAILED),
    data.CloseCheck(
        certified=2, symbols_used=380, k_total=400, metadata_rank=21,
        metadata_n_unique=40,
        blocks=(data.CloseBlockRow(stream_id="C", block=0, have=9,
                                   needed=50, rank=20, solved=False,
                                   short=30, groups_open=1, n_groups=1),
                data.CloseBlockRow(stream_id="M", block=1, have=200,
                                   needed=200, rank=24, solved=True,
                                   short=0, groups_open=0, n_groups=1)),
        status="open"),
)

VERIFIED_EVENTS: tuple = ROWS_EVENTS + (
    data.CloseCheck(
        certified=27, symbols_used=400, k_total=400, metadata_rank=24,
        metadata_n_unique=48,
        blocks=(data.CloseBlockRow(stream_id="C", block=0, have=50,
                                   needed=50, rank=24, solved=True,
                                   short=0, groups_open=0, n_groups=1),
                data.CloseBlockRow(stream_id="M", block=1, have=200,
                                   needed=200, rank=24, solved=True,
                                   short=0, groups_open=0, n_groups=1)),
        status="verified"),
    data.RunDone(status="verified", payload_sha256="ab" * 32,
                 n_bytes=465580, certified=27),
)

LIFE_EVENTS: tuple = (_run(), _capture(CAP_A),
                      _scheduled(place.STAGE_RING))


@pytest.fixture(scope="module")
def model_pre() -> diag_model.DiagModel:
    return _fold(PRE_EVENTS)


@pytest.fixture(scope="module")
def model_rows() -> diag_model.DiagModel:
    return _fold(ROWS_EVENTS)


@pytest.fixture(scope="module")
def model_verified() -> diag_model.DiagModel:
    return _fold(VERIFIED_EVENTS)


@pytest.fixture(scope="module")
def model_life() -> diag_model.DiagModel:
    return _fold(LIFE_EVENTS)


def test_the_settled_vocabulary_greps_to_the_frozen_production_set():
    assert place_settled_vocabulary() == SETTLED_VOCABULARY


def test_every_production_settled_state_folds_without_an_error():
    states = sorted(SETTLED_VOCABULARY)
    events: list = [_run(), _capture(CAP_A)]
    for index, state in enumerate(states):
        events.append(_scheduled(place.STAGE_RING, region_index=index))
        events.append(_settled(state, region_index=index))
    model = _fold(tuple(events))
    assert model.fold_errors == 0
    for index, state in enumerate(states):
        assert model.windows[(CAP_A, index, EXTENT)].cause == state
    assert model.settle_causes[CAP_A] == {state: 1 for state in states}


def test_every_place_stage_name_folds_as_a_scheduled_window():
    stages = tuple(place.STAGE_COST)
    events = (_run(), _capture(CAP_A)) + tuple(
        _scheduled(stage, region_index=index)
        for index, stage in enumerate(stages))
    model = _fold(events)
    assert model.fold_errors == 0
    for index, stage in enumerate(stages):
        rec = model.windows[(CAP_A, index, EXTENT)]
        assert rec.stage == stage
        assert rec.cost == place.STAGE_COST[stage]


def test_the_tile_state_ranks_speak_the_tiles_plugin_vocabulary():
    assert set(diag_model.TILE_RANKS) == {
        tiles_plugin.OUTCOME_BELOW_FLOOR, tiles_plugin.OUTCOME_FAILED,
        tiles_plugin.OUTCOME_CERTIFIED}


def test_the_status_block_is_always_exactly_six_rows(model_pre, model_rows):
    assert len(diag_readout.six_row_status(diag_model.empty())) == 6
    assert len(diag_readout.six_row_status(model_pre)) == 6
    assert len(diag_readout.six_row_status(model_rows)) == 6


def test_every_row_keeps_its_template_prefix(model_pre, model_rows):
    for model in (model_pre, model_rows):
        rows = diag_readout.six_row_status(model)
        for row, prefix in zip(rows, ROW_PREFIXES):
            assert row.startswith(prefix), row


def test_unavailable_facts_are_named_never_printed_as_zero(model_pre):
    rows = diag_readout.six_row_status(model_pre)
    assert "regions unavailable before survey" in rows[1]
    assert "support unavailable before survey" in rows[1]
    assert "calibrated unavailable before calibrate" in rows[1]
    assert rows[2] == "frontier unavailable before the first merge"
    assert rows[3] == "work     unavailable before the first completed job"
    assert rows[5] == "close    unavailable before the first close consult"


def test_the_format_row_is_verbatim(model_rows):
    assert diag_readout.six_row_status(model_rows)[0] == (
        f"format   {FORMAT_ID} · 3x3 tiles · 1 possible"
        " · streams C,M,Y · PROVISIONAL")


def test_the_format_row_shows_the_display_spelling_when_recorded():
    run = data.RunOpen(format_id="1i300-cmy8-r0700-p120-v1@3x3", pages=1,
                       tiles_yx=(3, 3), stream_ids=("C", "M", "Y"),
                       n_captures=1, workers=1,
                       display_id="c2-cmy8-r0700@3x3")
    model = _fold((run,))
    assert diag_readout.six_row_status(model)[0].startswith(
        "format   c2-cmy8-r0700@3x3 ·")
    assert model.run.format_id == "1i300-cmy8-r0700-p120-v1@3x3"


def test_the_capture_row_is_verbatim(model_rows):
    assert diag_readout.six_row_status(model_rows)[1] == (
        f"capture  1 ingested · {CAP_A[:12]}… · regions 2"
        " · support 500 cells · calibrated 1/2")


def test_the_frontier_row_is_verbatim(model_rows):
    assert diag_readout.six_row_status(model_rows)[2] == (
        "frontier queued 8 [place 3 · tiles 5] · in flight 2 · workers 4")


def test_the_work_row_is_verbatim(model_rows):
    assert diag_readout.six_row_status(model_rows)[3] == (
        "work     jobs 2 · cpu 2.1s · certs by plugin [place:0 · tiles:2]")


def test_the_tile_row_counts_floor_and_attempted_separately(model_rows):
    assert diag_readout.six_row_status(model_rows)[4] == (
        "tiles    UNKNOWN 23 · ADDRESSED 0 · FLOOR 1 · ATTEMPTED 1"
        " · CERTIFIED 2 [C 1 · M 1 · Y 0]")


def test_the_close_row_is_verbatim(model_rows):
    assert diag_readout.six_row_status(model_rows)[5] == (
        "close    open · K 380/400 · metadata rank 21/24"
        " · equations 40/48 · blocks 1/2")


def test_the_close_row_headlines_the_verified_sha(model_verified):
    row = diag_readout.six_row_status(model_verified)[5]
    assert row.startswith(f"close    VERIFIED sha {'ab' * 8}…")
    assert "blocks 2/2" in row


def test_a_single_stream_run_prints_no_per_stream_split(model_life):
    row = diag_readout.six_row_status(model_life)[4]
    assert "[" not in row


def test_plane_cert_counts_split_certified_by_stream(model_rows):
    assert diag_readout.plane_cert_counts(model_rows) == (
        ("C", 1), ("M", 1), ("Y", 0))


REPLAYED = data.SnapshotReplayed(
    facts=(("CaptureSurvey", 1), ("Certificate", 5370), ("Placement", 921),
           ("Window", 925)),
    certified=5370)

# the engine emits the replay once the captures are in, ahead of any of
# this run's own work
RESUMED_EVENTS: tuple = PRE_EVENTS + (REPLAYED,) + ROWS_EVENTS[2:]
RESUMED_IDLE: tuple = PRE_EVENTS + (REPLAYED,)

REPLAY_LINE = ("snapshot replayed · CaptureSurvey 1 · Certificate 5370"
               " · Placement 921 · Window 925"
               " · the marks here are this run's own work")


@pytest.fixture(scope="module")
def model_resumed() -> diag_model.DiagModel:
    return _fold(RESUMED_EVENTS)


def test_the_tile_row_names_what_the_resume_replayed(model_resumed):
    assert diag_readout.six_row_status(model_resumed)[4] == (
        "tiles    replayed 5370 certificates · this run UNKNOWN 23"
        " · ADDRESSED 0 · FLOOR 1 · ATTEMPTED 1 · CERTIFIED 2"
        " [C 1 · M 1 · Y 0]")


def test_a_resume_before_its_first_outcome_never_reads_as_an_empty_run():
    """The never-print-zero law over a resume: the tile map is this
    run's own, and a resumed run that has not certified anything YET
    still has 5370 certificates standing behind its close."""
    row = diag_readout.six_row_status(_fold(RESUMED_IDLE))[4]
    assert row == ("tiles    replayed 5370 certificates · this run"
                   " UNKNOWN 27 · ADDRESSED 0 · FLOOR 0 · ATTEMPTED 0"
                   " · CERTIFIED 0 [C 0 · M 0 · Y 0]")
    assert row.index("replayed 5370") < row.index("CERTIFIED 0")


def test_a_run_that_replayed_nothing_says_nothing(model_rows):
    assert model_rows.replayed is None
    assert diag_readout.replay_line(model_rows) is None
    assert diag_readout.status(model_rows)["replayed"] is None
    assert "replayed" not in diag_readout.six_row_status(model_rows)[4]


def test_the_replay_rides_the_status_dict_and_the_report(model_resumed):
    assert diag_readout.status(model_resumed)["replayed"] == {
        "certified": 5370,
        "facts": [["CaptureSurvey", 1], ["Certificate", 5370],
                  ["Placement", 921], ["Window", 925]]}
    assert diag_report.build_report(model_resumed)["replayed"] is not None


def test_the_replay_wakes_the_panes_that_draw_certificates():
    before = _fold(PRE_EVENTS)
    after = diag_model.fold(before, PRE_EVENTS + (REPLAYED,))
    for pane in diag_model.PANE_NAMES:
        moved = after.pane_revs.get(pane, 0) - before.pane_revs.get(pane, 0)
        assert moved == (1 if pane in ("capture", "payload") else 0), pane


def test_the_payload_pane_of_a_resumed_run_carries_the_replay_footer(
        model_rows, model_resumed):
    plain = _raster(model_rows, "payload", 0)
    resumed = _raster(model_resumed, "payload", 0)
    assert resumed.shape[0] == plain.shape[0] + panes.REPLAY_FOOTER_H
    assert np.array_equal(resumed[:plain.shape[0]], plain)
    assert diag_readout.replay_line(model_resumed) == REPLAY_LINE


def test_the_capture_pane_of_a_resumed_run_names_the_replay(model_resumed):
    lines = [text for text, _colour in
             panes._capture_text(model_resumed, CAP_A)]
    assert lines[0] == REPLAY_LINE
    assert panes.render_pane(model_resumed, "capture", 0)[:8] == PNG_MAGIC


def test_an_uneven_row_reports_its_scarcest_group_everywhere():
    grouped = _fold(ROWS_EVENTS + (
        data.CloseCheck(
            certified=300, symbols_used=300, k_total=237, metadata_rank=24,
            metadata_n_unique=300,
            blocks=(data.CloseBlockRow(stream_id=None, block=0, have=300,
                                       needed=237, rank=None, solved=False,
                                       short=19, groups_open=3,
                                       n_groups=17),),
            status="open"),))
    assert diag_readout.close_shortfall_line(grouped) == (
        "open · block #0 short 19 rows in 3/17 groups")
    (block,) = diag_readout.status(grouped)["close"]["blocks"]
    assert (block["short"], block["groups_open"], block["n_groups"]) == (
        19, 3, 17)
    assert diag_readout.six_row_status(grouped)[5].endswith("blocks 0/1")


def test_the_close_shortfall_line_names_the_worst_unsolved_block(
        model_pre, model_rows, model_verified):
    assert diag_readout.close_shortfall_line(model_pre) is None
    assert diag_readout.close_shortfall_line(model_rows) == (
        "open · block C#0 needs 30 more symbols")
    assert diag_readout.close_shortfall_line(model_verified) is None


def test_a_scheduled_window_appears_with_its_stage_and_cost(model_life):
    rec = model_life.windows[WKEY_A]
    assert rec.stage == place.STAGE_RING
    assert rec.cost == place.STAGE_COST[place.STAGE_RING]


def test_an_inflight_place_job_marks_the_window_active_across_levels(
        model_life):
    started = diag_model.fold(model_life, LIFE_EVENTS + (
        _stat_inflight(("place", WID_L1, place.STAGE_RING)),))
    assert set(started.windows) == {WKEY_A}
    assert diag_readout.active_place_windows(started) == {WKEY_A}
    assert diag_readout.now_lines(started) == [
        "place · window 0.0 (0, 0, 30, 30) · ring"]


def test_an_empty_stat_clears_active_but_keeps_the_window(model_life):
    events = LIFE_EVENTS + (
        _stat_inflight(("place", WID_L1, place.STAGE_RING)),
        _stat_inflight(),
        _job_done("place", WID_L1, cpu_s=0.9, n_certificates=2),)
    model = diag_model.fold(model_life, events)
    assert diag_readout.active_place_windows(model) == set()
    assert WKEY_A in model.windows
    assert diag_readout.now_lines(model) == []
    last = diag_readout.last_line(model)
    assert last is not None and last.startswith("place · ")
    assert "+2 certs" in last


def test_an_accepted_pose_removes_the_window_and_counts_the_placement(
        model_life):
    model = diag_model.fold(model_life, LIFE_EVENTS + (_pose(),))
    assert WKEY_A not in model.windows
    assert model.region_placements[(CAP_A, 0)] == 1


def test_a_declined_pose_neither_removes_nor_counts(model_life):
    model = diag_model.fold(model_life,
                            LIFE_EVENTS + (_pose(accepted=False),))
    assert WKEY_A in model.windows
    assert model.region_placements.get((CAP_A, 0), 0) == 0


@pytest.mark.parametrize("cause", sorted(RETIRE_VOCABULARY))
def test_window_retired_removes_the_window_without_a_cause_tally(
        model_life, cause):
    model = diag_model.fold(model_life, LIFE_EVENTS + (
        data.WindowRetired(capture=CAP_A, level_index=0, region_index=0,
                           extent_cells=EXTENT, cause=cause),))
    assert WKEY_A not in model.windows
    assert model.settle_causes.get(CAP_A, {}) == {}, (
        "a retirement is not a refusal: it never joins the settle tally")


def test_an_unresolved_refusal_stays_live_through_the_next_stage(
        model_life):
    model = diag_model.fold(model_life, LIFE_EVENTS + (
        _settled("pose_refused"),
        _scheduled(place.STAGE_WORD_CENTRE),))
    rec = model.windows[WKEY_A]
    assert rec.cause == "pose_refused"
    assert rec.stage == place.STAGE_WORD_CENTRE
    assert model.settle_causes[CAP_A] == {"pose_refused": 1}


WASH_BASE: tuple = (
    _run(), _capture(CAP_A),
    _survey(CAP_A, (_mark(0, with_cells=True),)))
WASH_PIXEL_YX = (164, 164)
WASH_RGB = tuple(int(v) for v in (
    0.65 * np.asarray(panes.BG, np.float32)
    + 0.35 * np.asarray(panes.GREEN, np.float32)).astype(np.uint8))


def test_certified_tiles_wash_back_onto_the_scrap():
    model = _fold(WASH_BASE + (_pose(), _tile("K", 0, 0, "certified")))
    raster = _raster(model, "capture", 0)
    assert _rgb(raster[WASH_PIXEL_YX]) == WASH_RGB


def test_overlapping_placements_wash_in_one_shade():
    once = _fold(WASH_BASE + (_pose(), _tile("K", 0, 0, "certified")))
    twice = _fold(WASH_BASE + (_pose(), _pose(),
                               _tile("K", 0, 0, "certified")))
    assert (_rgb(_raster(once, "capture", 0)[WASH_PIXEL_YX])
            == _rgb(_raster(twice, "capture", 0)[WASH_PIXEL_YX])
            == WASH_RGB)


def test_uncertified_tiles_leave_the_scrap_bare():
    model = _fold(WASH_BASE + (_pose(),))
    raster = _raster(model, "capture", 0)
    assert _rgb(raster[WASH_PIXEL_YX]) == panes.BG


def test_the_wash_applies_the_placements_own_affine():
    events = WASH_BASE + (
        _pose(extent=(0, 0, 64, 128), shape_yx=(64, 128),
              native_affine=(8.0, 0.0, 100.0, 0.0, 8.0, -412.0)),
        _tile("K", 0, 1, "certified"))
    raster = _raster(_fold(events), "capture", 0)
    assert _rgb(raster[164, 164]) == WASH_RGB
    assert _rgb(raster[164, 676]) == panes.BG


ADDR_BASE: tuple = (_run(), _capture(CAP_A))
COVER_TWO: tuple = ADDR_BASE + (
    data.AddressCoverage(page=0, tiles=((1, 1, _packed(range(8))),)),
    data.AddressCoverage(page=0, tiles=((1, 1, _packed(range(4, 12))),)))
COVER_UNION: tuple = ADDR_BASE + (
    data.AddressCoverage(page=0, tiles=((1, 1, _packed(range(12))),)),)
COVER_SUM: tuple = ADDR_BASE + (
    data.AddressCoverage(page=0, tiles=((1, 1, _packed(range(16))),)),)


def test_address_masks_or_together_never_add():
    model = _fold(COVER_TWO)
    popcount = int(np.unpackbits(model.address_bits[0][1, 1]).sum())
    assert popcount == 12


def test_the_page_pane_prints_the_popcount_of_the_union():
    two = panes.render_pane(_fold(COVER_TWO), "page", 0)
    union = panes.render_pane(_fold(COVER_UNION), "page", 0)
    summed = panes.render_pane(_fold(COVER_SUM), "page", 0)
    assert two == union
    assert two != summed


def test_a_solved_word_turns_the_tile_border_green():
    box = panes.TileGrid(700, 700, (3, 3)).box(1, 1)
    mid_x = (box[0] + box[2]) // 2
    covered = _raster(_fold(COVER_TWO), "page", 0)
    assert _rgb(covered[box[1], mid_x]) == panes.CHIP_REACH[1]
    solved = _raster(_fold(COVER_TWO + (
        data.WordOutcome(page=0, ty=1, tx=1, errors=2, sites=64),)),
        "page", 0)
    assert _rgb(solved[box[1], mid_x]) == panes.GREEN


ROT_EVENTS: tuple = (_run(), _capture(CAP_A), _pose(
    origin_yx=(64, 0), rot_k=1, shape_yx=(64, 128)))
PAGE_BLEND = tuple(int(v) for v in (
    0.78 * np.asarray(panes.CHIP_UNSEEN[0], np.float32)
    + 0.22 * np.asarray(panes.HUES[0], np.float32)).astype(np.uint8))


def test_an_odd_rotation_addresses_the_rotated_tile_footprint():
    arr = _fold(ROT_EVENTS).tile_states[0]
    assert arr[0, 1, 0] == panes.TILE_ADDRESSED
    assert arr[0, 2, 0] == panes.TILE_ADDRESSED
    assert arr[0, 0, 0] == panes.TILE_UNKNOWN
    assert arr[0, 1, 1] == panes.TILE_UNKNOWN


def test_the_page_pane_paints_the_rotated_shape_at_the_page_origin():
    raster = _raster(_fold(ROT_EVENTS), "page", 0)
    assert raster.shape == (700, 700, 3)
    assert _rgb(raster[350, 116]) == PAGE_BLEND
    assert _rgb(raster[583, 116]) == PAGE_BLEND
    assert _rgb(raster[350, 350]) == panes.CHIP_UNSEEN[0]


def test_the_payload_pane_washes_the_rotated_footprint_as_addressed():
    raster = _raster(_fold(ROT_EVENTS), "payload", 0)
    assert _rgb(raster[350, 116]) == panes.CHIP_REACH[0]
    assert _rgb(raster[350, 350]) == panes.CHIP_UNSEEN[0]


def test_the_pose_band_sets_its_glyph_on_the_rotated_centre():
    raster = _raster(_fold(ROT_EVENTS), "pose", 0)
    assert _rgb(raster[932, 232]) == panes.TICK_GREY
    assert _rgb(raster[700, 466]) == panes.POSE_BG


def test_the_payload_pane_gives_each_stream_its_own_segment(model_rows):
    box = panes.TileGrid(700, 700, (3, 3)).box(0, 0)
    raster = _raster(model_rows, "payload", 0)
    mid_y = (box[1] + box[3]) // 2
    third = (box[2] - box[0]) // 3
    assert _rgb(raster[mid_y, box[0] + third // 2]) == panes.CHIP_GREEN[0]
    assert _rgb(raster[mid_y, box[0] + third + third // 2]) == (
        panes.CHIP_NEUTRAL[0])


def test_the_status_dict_carries_exactly_the_pinned_keys(model_rows):
    status = diag_readout.status(model_rows)
    assert set(status) == STATUS_KEYS
    assert set(status["scheduler"]) == SCHEDULER_KEYS
    assert set(status["close"]) == CLOSE_KEYS
    for row in status["scheduler"]["plugins"]:
        assert set(row) == PLUGIN_KEYS


def test_the_scheduler_row_names_the_clause_that_retired_each_window():
    """A run must answer "did the done gate bite?" from its own report.

    That is the whole 2026-08-31 finding: for a month the gate's only
    door emitted a causeless `WindowRetired`, so four real-sheet runs
    read as "never fires" while it was suppressing hundreds of windows.
    A tally the run writes itself is what keeps that from recurring.
    """
    model = _fold(ROWS_EVENTS + (
        data.EngineStat(
            queued=(), inflight=0, stale_skips=0, retired=3,
            attempts_hist=(),
            retire_causes=((place_sched.RETIRE_DONE, 2),
                           (place_sched.RETIRE_PLACED, 1))),))
    assert diag_readout.status(model)["scheduler"]["retire_causes"] == [
        [place_sched.RETIRE_DONE, 2], [place_sched.RETIRE_PLACED, 1]]


def test_the_scheduler_row_refuses_to_invent_a_tally_before_the_first_stat():
    assert diag_readout.status(_fold(PRE_EVENTS))["scheduler"][
        "retire_causes"] is None


def test_the_revision_is_the_event_count_never_a_clock(model_rows):
    assert diag_readout.status(model_rows)["revision"] == len(ROWS_EVENTS)


def test_now_and_last_follow_the_job_lifecycle(model_life):
    started = diag_model.fold(model_life, LIFE_EVENTS + (
        _stat_inflight(("place", WID_L1, place.STAGE_RING)),))
    status = diag_readout.status(started)
    assert status["now"] == ["place · window 0.0 (0, 0, 30, 30) · ring"]
    done = diag_model.fold(started, LIFE_EVENTS + (
        _stat_inflight(("place", WID_L1, place.STAGE_RING)),
        _stat_inflight(),
        _job_done("place", WID_L1, cpu_s=0.9),))
    status = diag_readout.status(done)
    assert status["now"] == []
    assert status["last"] == (
        "place · window 0.0 (0, 0, 30, 30) · +0 certs · 0.9s")


def test_the_scheduler_block_reports_the_engine_stat_numbers(model_rows):
    scheduler = diag_readout.status(model_rows)["scheduler"]
    assert scheduler["stale_skips"] == 7
    assert scheduler["retired"] == 1
    assert scheduler["attempts_hist"] == [["1", 4], ["2", 1]]
    by_name = {row["plugin"]: row for row in scheduler["plugins"]}
    assert by_name["place"]["queued"] == 3
    assert by_name["tiles"]["queued"] == 5
    assert by_name["tiles"]["certificates"] == 2


CHURN_DONE = data.RunDone(status="verified", payload_sha256="cd" * 32,
                          n_bytes=6000, certified=2)

CHURN_PRICED: tuple = PRE_EVENTS + (
    _job_done("place", ("w", 0), cpu_s=0.10, cost=40),
    _job_done("place", ("w", 1), cpu_s=0.10, cost=40),
    _job_done("tiles.scan", ("t", 0), cpu_s=0.05, cost=20),
    _job_done("tiles.scan", ("t", 1), cpu_s=0.05, cost=20),
)

CHURN_HEALTHY: tuple = CHURN_PRICED + (CHURN_DONE,)

CHURN_OUTLIERS: tuple = CHURN_PRICED + tuple(
    _job_done("color", ("lane", 0), cpu_s=3.2, cost=15) for _ in range(4)
) + tuple(
    _job_done("ctx", ("region", 0), cpu_s=0.001, cost=15) for _ in range(8)
) + (CHURN_DONE,)

CHURN_LINE = ("color: 3.2 cpu-s/fire at price 15 · 4.0 fires/subject; "
              "ctx: 0.001 cpu-s/fire at price 15 · 8.0 fires/subject")


def test_the_churn_advisory_names_the_dear_row_and_the_chatty_row():
    assert diag_readout.churn_advisory(_fold(CHURN_OUTLIERS)) == CHURN_LINE


def test_the_churn_advisory_is_silent_on_a_healthy_run():
    assert diag_readout.churn_advisory(_fold(CHURN_HEALTHY)) is None


def test_the_churn_advisory_waits_for_the_end_of_the_run():
    assert diag_readout.churn_advisory(_fold(CHURN_PRICED + tuple(
        _job_done("color", ("lane", 0), cpu_s=3.2, cost=15)
        for _ in range(4)))) is None


def test_churn_rows_carry_the_per_row_arithmetic():
    rows = diag_readout.churn_rows(_fold(CHURN_OUTLIERS))
    assert [row[0] for row in rows] == ["color", "ctx", "place", "tiles.scan"]
    assert [row[1:] for row in rows] == [
        pytest.approx((3.2, 15.0, 4.0)), pytest.approx((0.001, 15.0, 8.0)),
        pytest.approx((0.1, 40.0, 1.0)), pytest.approx((0.05, 20.0, 1.0))]


def test_the_churn_advisory_rides_the_status_dict_and_the_report(
        tmp_path: Path):
    outliers = _fold(CHURN_OUTLIERS)
    assert diag_readout.status(outliers)["scheduler"]["churn"] == CHURN_LINE
    path = tmp_path / "report.json"
    diag_report.write_report(path, outliers)
    assert json.loads(path.read_text())["scheduler"]["churn"] == CHURN_LINE
    healthy = tmp_path / "healthy.json"
    diag_report.write_report(healthy, _fold(CHURN_HEALTHY))
    assert json.loads(healthy.read_text())["scheduler"]["churn"] is None


def test_counting_rows_show_symbols_and_ready_never_rank(model_rows):
    counting = _fold(ROWS_EVENTS + (
        data.CloseCheck(
            certified=5, symbols_used=120, k_total=400, metadata_rank=24,
            metadata_n_unique=200,
            blocks=(data.CloseBlockRow(stream_id="C", block=0, have=120,
                                       needed=200, rank=None, solved=False,
                                       short=80, groups_open=1, n_groups=1),
                    data.CloseBlockRow(stream_id="M", block=1, have=200,
                                       needed=200, rank=None, solved=False,
                                       short=0, groups_open=0, n_groups=1)),
            status="open", blocks_counting=True),))
    row = diag_readout.six_row_status(counting)[5]
    assert row == ("close    open · symbols 120/400 · metadata rank 24/24"
                   " · equations 200/48 · blocks ready 1/2")
    status = diag_readout.status(counting)["close"]
    assert status["counting"] is True
    assert [block["rank"] for block in status["blocks"]] == [None, None]
    assert diag_readout.close_shortfall_line(counting) == (
        "open · block C#0 needs 80 more symbols")
    solved = diag_readout.status(model_rows)["close"]
    assert solved["counting"] is False


def test_the_scheduler_block_carries_the_consult_cpu_gauge(model_rows,
                                                           model_pre):
    assert diag_readout.status(model_rows)["scheduler"]["consult_cpu_s"] == 1.5
    assert diag_readout.status(model_pre)["scheduler"]["consult_cpu_s"] is None


def test_the_verified_close_carries_bytes_and_sha16(model_verified):
    close = diag_readout.status(model_verified)["close"]
    assert close["verified"] == {"n_bytes": 465580, "sha16": "ab" * 8}


def test_plane_certs_ride_the_status_dict(model_rows):
    assert diag_readout.status(model_rows)["plane_certs"] == [
        ["C", 1], ["M", 1], ["Y", 0]]


def test_page_selectors_are_live_union_the_zero_prior():
    empty = _fold((_run(pages=133),))
    assert diag_readout.page_selectors(empty) == (0,)
    posed = _fold((_run(pages=133), _pose(page=2)))
    assert diag_readout.page_selectors(posed) == (0, 2)
    clipped = _fold((_run(pages=1), _pose(page=2)))
    assert diag_readout.page_selectors(clipped) == (0,)


def test_the_pane_index_lists_every_valid_selector(model_rows):
    status = diag_readout.status(model_rows)
    assert status["captures"] == [{"ordinal": 0, "sha12": CAP_A[:12]}]
    # "field" lists no page: the FIELD band appears only where a fit
    # landed, so a run without the plane-field arm indexes exactly the
    # four panes it always did.
    assert status["panes"] == {"capture": [0], "page": [0],
                               "payload": [0], "pose": [0], "field": []}


def test_render_pane_returns_none_for_unknown_pane_or_selector(model_rows):
    assert panes.render_pane(model_rows, "capture", 9) is None
    assert panes.render_pane(model_rows, "page", 9) is None
    assert panes.render_pane(model_rows, "frame", 0) is None


def test_pin_panes_covers_every_pane_selector_pair(model_rows):
    pinned = panes.pin_panes(model_rows)
    assert set(pinned) == {("capture", 0), ("page", 0), ("payload", 0),
                           ("pose", 0)}
    for png in pinned.values():
        assert png[:8] == PNG_MAGIC


SERIAL_EVENTS: tuple = (
    _run(), _capture(CAP_A),
    _survey(CAP_A, (_mark(0, with_cells=True),),
            preview=np.ones((8, 8), np.float32)),
    data.AddressCoverage(page=0, tiles=((1, 1, _packed(range(8))),)),
    _pose(),
    _tile("K", 0, 0, tiles_plugin.OUTCOME_CERTIFIED),
)


def test_events_jsonl_writes_parseable_lines_for_bytes_and_arrays(
        tmp_path: Path):
    path = tmp_path / "events.jsonl"
    diag_report.write_events_jsonl(path, SERIAL_EVENTS)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(lines) == len(SERIAL_EVENTS)
    assert [line["type"] for line in lines[:2]] == ["RunOpen", "CaptureOpen"]
    survey = next(line for line in lines if line["type"] == "SurveyDone")
    assert survey["preview"] == {"shape": [8, 8], "dtype": "float32"}
    assert survey["regions"][0]["cells"] == {"shape": [20, 20],
                                             "dtype": "bool"}
    coverage = next(line for line in lines
                    if line["type"] == "AddressCoverage")
    assert coverage["tiles"][0] == [1, 1, _packed(range(8)).hex()]


def test_the_report_round_trips_through_json(tmp_path: Path, model_rows):
    path = tmp_path / "report.json"
    diag_report.write_report(path, model_rows)
    report = json.loads(path.read_text())
    assert report == json.loads(json.dumps(
        diag_report.build_report(model_rows), default=str))
    # all_rows, not six_row_status: the report carries the conditional
    # rows too (here the dial-off plane-field row on a colour run).
    assert report["rows"] == list(diag_readout.all_rows(model_rows))
    assert report["rows"][:6] == list(
        diag_readout.six_row_status(model_rows))
    assert len(report["capture_facts"]) == 1
    facts = report["capture_facts"][0]
    assert facts["capture"] == CAP_A
    assert facts["regions"][0]["support_cells"] == 300


POISON = data.WindowSettled(capture=CAP_A, level_index=0, region_index=0,
                            extent_cells=None, state="pose_refused")


def test_a_poisoned_event_bumps_fold_errors_and_nothing_else_breaks():
    model = _fold(WASH_BASE + (_pose(), POISON))
    assert model.cursor == len(WASH_BASE) + 2
    assert model.fold_errors == 1
    assert diag_readout.status(model)["fold_errors"] == 1
    for pane, selector in (("capture", 0), ("page", 0), ("payload", 0),
                           ("pose", 0)):
        assert panes.render_pane(model, pane, selector)[:8] == PNG_MAGIC


def test_fold_returns_the_same_object_when_nothing_new_arrived(model_rows):
    assert diag_model.fold(model_rows, ROWS_EVENTS) is model_rows


def test_fold_copies_on_write_and_leaves_the_old_model_untouched(
        model_life):
    grown = diag_model.fold(model_life, LIFE_EVENTS + (
        data.WindowRetired(capture=CAP_A, level_index=0, region_index=0,
                           extent_cells=EXTENT,
                           cause=place_sched.RETIRE_DONE),
        _tile("K", 0, 0, tiles_plugin.OUTCOME_CERTIFIED),))
    assert WKEY_A not in grown.windows
    assert WKEY_A in model_life.windows
    assert grown.tile_states[0][0, 0, 0] == panes.TILE_CERTIFIED
    assert 0 not in model_life.tile_states


SERVER_EVENTS: tuple = WASH_BASE + (
    _pose(),
    data.AddressCoverage(page=0, tiles=((1, 1, _packed(range(8))),)),
    data.WordOutcome(page=0, ty=1, tx=1, errors=0, sites=80),
    _tile("K", 0, 0, tiles_plugin.OUTCOME_CERTIFIED),
    _job_done("tiles", "page0", cpu_s=0.4, n_certificates=1),
)


@pytest.fixture(scope="module")
def live_server() -> Iterator[tuple[server.DiagServer, list]]:
    live: list = list(SERVER_EVENTS)
    instance = server.serve(0, live)
    assert instance is not None
    try:
        yield instance, live
    finally:
        instance.stop()


def _get(instance: server.DiagServer, path: str,
         headers: dict | None = None) -> tuple[int, bytes, dict]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{instance.port}{path}", headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers or {})


def test_the_home_shell_names_every_pane_img(live_server):
    instance, _live = live_server
    code, body, _headers = _get(instance, "/")
    assert code == 200
    for pane in ("capture", "page", "payload", "pose"):
        assert f'id="img-{pane}"'.encode() in body


def test_status_serves_the_seam_dict_at_the_event_count(live_server):
    instance, live = live_server
    code, body, headers = _get(instance, "/status")
    assert code == 200
    assert headers.get("Cache-Control") == "no-store"
    status = json.loads(body)
    assert set(status) == STATUS_KEYS
    assert status["revision"] == len(live)


def test_every_pane_route_serves_a_png(live_server):
    instance, _live = live_server
    for pane in ("capture", "page", "payload", "pose"):
        code, body, headers = _get(instance, f"/pane/{pane}-0.png")
        assert code == 200, pane
        assert body[:8] == PNG_MAGIC
        assert headers.get("Content-Type") == "image/png"


def test_unknown_panes_and_selectors_get_a_naming_404(live_server):
    instance, _live = live_server
    assert _get(instance, "/pane/frame-0.png")[0] == 404
    assert _get(instance, "/pane/page-9.png")[0] == 404
    assert _get(instance, "/pane/capture-x.png")[0] == 404
    assert _get(instance, "/nope")[0] == 404


def test_a_busy_port_returns_none_with_a_stderr_line(live_server, capsys):
    instance, _live = live_server
    assert server.serve(instance.port, []) is None
    assert "diag: port" in capsys.readouterr().err


def test_a_pane_rev_bump_invalidates_only_that_pane():
    live: list = list(WASH_BASE + (_pose(),))
    cache = server.FrameCache(live)
    cache.status()
    pose_before = cache.pane("pose", 0)
    payload_before = cache.pane("payload", 0)
    live.append(_tile("K", 0, 0, tiles_plugin.OUTCOME_CERTIFIED))
    cache.status()
    assert cache.pane("pose", 0) is pose_before
    payload_after = cache.pane("payload", 0)
    assert payload_after is not payload_before
    assert payload_after != payload_before


def test_the_scheduler_block_is_unavailable_before_the_first_merge(
        model_pre):
    scheduler = diag_readout.status(model_pre)["scheduler"]
    assert scheduler["available"] is False
    assert scheduler["stale_skips"] is None
    assert scheduler["retired"] is None
    assert scheduler["wakes"] is None


def test_a_pin_freezes_the_frames_against_later_events():
    live: list = list(SERVER_EVENTS)
    instance = server.serve(0, live)
    assert instance is not None
    try:
        pinned = instance.pin()
        assert ("capture", 0) in pinned
        live.append(_job_done("tiles", "late", cpu_s=0.1))
        _code, body, _headers = _get(instance, "/status")
        assert json.loads(body)["revision"] == len(SERVER_EVENTS)
        code, body, _headers = _get(instance, "/pane/capture-0.png")
        assert code == 200 and body[:8] == PNG_MAGIC
    finally:
        instance.stop()


def test_finish_pins_then_stops_and_stop_is_idempotent():
    live: list = list(SERVER_EVENTS)
    instance = server.serve(0, live)
    assert instance is not None
    _code, body, _headers = _get(instance, "/status")
    assert json.loads(body)["revision"] == len(live)
    instance.finish()
    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(
            f"http://127.0.0.1:{instance.port}/status", timeout=2)
    instance.stop()
