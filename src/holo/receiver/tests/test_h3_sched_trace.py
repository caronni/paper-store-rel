"""The scheduler trace: off by default, measurement only, atomic dumps.

Two lanes.  The fast one proves the mechanism — the null object, the env
door, the exclusive category clock, the digest, the atomic write and the
summary schema — without a decode.  The slow one (HOLO3_RUN_SLOW_TESTS)
runs the colour sim TWICE at workers=1, once traced and once not, and
asserts the run is the same run: same payload sha, same certificate
signature, same event sequence once the two CPU METER fields are
normalised away.

Why the meters are normalised and why workers=1: `JobDone.cpu_s` and
`EngineStat.consult_cpu_s` are `thread_time` readings, so no two runs of
anything ever carry the same bytes there — that is true of main against
itself.  And above one worker the run's STOP POINT is not deterministic
either: the close preempts at whichever merge batch crosses K, so two
untraced runs at workers=4 measurably differ (369 / 380 / 370 events,
three runs, 2026-09-17).  workers=1 with the meters normalised is the
sharpest identity this engine can be held to, and the trace meets it.
"""
from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo.receiver import (
    data,
    engine,
    sched_trace,
    sched_trace_folds,
    store_folds,
)
from holo.receiver.format import identity
from holo.receiver.tests import _h3_sims, _h3_support
from holo.receiver.tests._h3_fixture_build import DecodeRecord, _decode_once

#: `cpu_s` is a thread-time meter and never repeats across runs.
METER_FIELDS = ("cpu_s", "consult_cpu_s")


# ------------------------------------------------------------ the door


def test_the_trace_is_off_unless_the_environment_says_otherwise():
    assert sched_trace.enabled_by_env({}) is False
    for value in ("", " ", "0", "no", "off"):
        assert sched_trace.enabled_by_env(
            {sched_trace.ENV_ENABLE: value}) is False
    for value in ("1", "yes", "true", "on"):
        assert sched_trace.enabled_by_env(
            {sched_trace.ENV_ENABLE: value}) is True


def test_the_cadence_falls_back_to_the_default_on_junk():
    assert sched_trace.every_s_by_env({}) == sched_trace.DEFAULT_EVERY_S
    assert sched_trace.every_s_by_env(
        {sched_trace.ENV_EVERY_S: "60"}) == 60.0
    for junk in ("nonsense", "0", "-5"):
        assert sched_trace.every_s_by_env(
            {sched_trace.ENV_EVERY_S: junk}) == sched_trace.DEFAULT_EVERY_S


def test_an_engine_is_traceless_until_start_arms_it(monkeypatch):
    monkeypatch.delenv(sched_trace.ENV_ENABLE, raising=False)
    assert engine._Engine._trace_on is False
    assert engine._Engine._trace.enabled is False
    # the class attribute is what a hand-built engine inherits: the
    # contract tests and the measure/ harnesses build one with
    # object.__new__ and never set an instance attribute
    bare = object.__new__(engine._Engine)
    assert bare._trace_on is False
    bare._trace.note_input("anything", ())
    bare._trace.dump(bare)
    bare._trace.finish(bare)


def test_the_module_global_arms_and_disarms(tmp_path):
    assert sched_trace.TRACE.enabled is False
    trace = sched_trace.arm(tmp_path, workers=3, every_s=11.0)
    try:
        assert sched_trace.TRACE is trace
        assert trace.enabled is True
        assert trace.workers == 3
        assert (tmp_path / sched_trace.DIR_NAME).is_dir()
    finally:
        trace.finish(object())
        sched_trace.disarm()
    assert sched_trace.TRACE.enabled is False


# ----------------------------------------------------------- mechanism


def test_the_digest_is_a_function_of_the_bytes_not_the_object():
    values = np.arange(12, dtype=np.float32).reshape(4, 3)
    first = sched_trace.digest_of("tile_cut", ("scan", values))
    same = sched_trace.digest_of("tile_cut", ("scan", values.copy()))
    assert first == same and len(first) == 32
    moved = values.copy()
    moved[2, 1] += np.float32(1e-6)
    assert sched_trace.digest_of("tile_cut", ("scan", moved)) != first
    # dtype is part of the input: the same numbers at another width are
    # another decoder input
    assert sched_trace.digest_of(
        "tile_cut", ("scan", values.astype(np.float64))) != first
    # so is the stage and so is the kind
    assert sched_trace.digest_of("tile_cut", ("retry150", values)) != first
    assert sched_trace.digest_of("local_donors", ("scan", values)) != first


def test_the_category_clock_is_exclusive_and_sums(tmp_path):
    clock = sched_trace._Clock()
    clock.enter("fill")
    clock.enter("push")
    clock.leave()
    clock.leave()
    clock.enter("wait")
    clock.leave()
    clock.settle()
    totals = clock.totals
    assert totals["push"] > 0 and totals["fill"] > 0
    assert totals["wait"] > 0
    # a leave with nothing to pop keeps the root category alive rather
    # than emptying the stack under a later enter
    clock.leave()
    clock.leave()
    clock.enter("fold")
    clock.leave()
    assert totals["fold"] >= 0


def test_a_redundant_input_is_recorded_and_never_acted_on(tmp_path):
    trace = sched_trace.arm(tmp_path, workers=1, every_s=3600.0)
    try:
        for ordinal in range(2):
            trace.clear_input()
            trace.note_input("tile_cut", ("scan", ("C",), b"same bytes"))
            trace.fire("tiles.scan", ("p", 0, 0), seq=ordinal, stage="scan",
                       cost=20, attempts=ordinal + 1, version=ordinal,
                       tried_version_before=ordinal - 1)
            trace.fire_done("tiles.scan", ("p", 0, 0), cpu_s=0.5,
                            n_certificates=0, n_poses=0, n_words=0)
        # the jsonl files are appended and flushed at a dump, so a
        # killed run loses at most one interval and never half a line
        assert (trace.out_dir / "fires.jsonl").read_text() == ""
        trace.dump(object())
        rows = [json.loads(line) for line
                in (trace.out_dir / "fires.jsonl").read_text().splitlines()]
        assert [row["redundant_input"] for row in rows] == [False, True]
        assert rows[0]["input_digest"] == rows[1]["input_digest"]
        assert rows[0]["input_digest_kind"] == "tile_cut"
        # both fires happened: the digest is a record, not a gate
        assert len(rows) == 2
        summary = json.loads((trace.out_dir / "summary.json").read_text())
        assert summary["by_plugin"]["redundant_fires"] == {"tiles.scan": 1}
        assert summary["by_plugin"]["redundant_cpu_s"] == {"tiles.scan": 0.5}
        assert summary["digest"]["by_kind"] == {"tile_cut": 2}
    finally:
        trace.finish(object())
        sched_trace.disarm()


def test_a_dump_is_atomic_and_keeps_a_whole_predecessor(tmp_path):
    trace = sched_trace.arm(tmp_path, workers=1, every_s=3600.0)
    try:
        trace.wake("tiles.swim", ("p", 1, 1, "C"), "lane_poses")
        trace.push("tiles.swim", ("p", 1, 1, "C"), "seat_stands")
        trace.dump(object())
        first = json.loads((trace.out_dir / "summary.json").read_text())
        assert first["wakes"] == 1
        assert not list(trace.out_dir.glob("*.tmp"))
        trace.wake("tiles.swim", ("p", 1, 1, "C"), "tile")
        trace.dump(object())
        second = json.loads((trace.out_dir / "summary.json").read_text())
        assert second["wakes"] == 2
        assert second["fan_out"]["lane_poses"] == {"tiles.swim": 1}
        assert second["fan_out"]["tile"] == {"tiles.swim": 1}
        assert not list(trace.out_dir.glob("*.tmp"))
    finally:
        trace.finish(object())
        sched_trace.disarm()


def test_the_summary_carries_every_promised_section(tmp_path):
    trace = sched_trace.arm(tmp_path, workers=2, every_s=3600.0)
    try:
        trace.birth("place", ("cap", 0, 0, (0, 0, 200, 200)), False)
        trace.seat("place", ("cap", 0, 0, (0, 0, 200, 200)), "ring", 40,
                   False)
        trace.pop("place", ("cap", 0, 0, (0, 0, 200, 200)), "fired")
        trace.fire("place", ("cap", 0, 0, (0, 0, 200, 200)), seq=1,
                   stage="ring", cost=40, attempts=1, version=3,
                   tried_version_before=0)
        trace.fire_done("place", ("cap", 0, 0, (0, 0, 200, 200)), 1.5, 0,
                        1, 1)
        trace.retire("place", ("cap", 0, 0, (0, 0, 200, 200)), "placed")
        trace.timed("stage", "place", lambda: None)
        trace.dump(object())
        summary = json.loads((trace.out_dir / "summary.json").read_text())
    finally:
        trace.finish(object())
        sched_trace.disarm()
    for section in ("schema", "notes", "wall_s", "workers", "job_cpu_s",
                    "worker_utilisation", "wakes", "fires", "main_thread_s",
                    "digest", "heap", "by_plugin", "pushes", "pops",
                    "callbacks", "fan_out", "retire_causes", "census",
                    "subscribers", "top_subjects"):
        assert section in summary, section
    assert summary["schema"] == sched_trace.SCHEMA
    assert set(summary["main_thread_s"]) == set(sched_trace.CATEGORIES)
    assert summary["callbacks"]["place"]["stage"]["calls"] == 1
    assert summary["retire_causes"] == {"placed": 1}
    census = summary["census"]["place"]
    assert census["bookmarks"] == 1 and census["fired"] == 1
    assert census["never_fired"] == 0 and census["retired"] == 1
    assert summary["top_subjects"]["place"][0]["fires"] == 1
    ladder = [json.loads(line) for line in
              (trace.out_dir / "place-ladder.jsonl").read_text().splitlines()]
    assert [row["kind"] for row in ladder] == ["seat", "fire", "retire"]


def test_the_engine_names_every_push_and_pop_exit_it_can_take():
    """The two funnels are enumerated against the engine's own source.

    A branch added to `_push_worker` or `_fill` without a counter would
    make the trace silently lie about where the pops went; this is the
    cheap guard for that.
    """
    source = (_h3_support.HOLO3_ROOT / "engine.py").read_text()
    for outcome in sched_trace.PUSH_OUTCOMES:
        assert f'"{outcome}"' in source, outcome
    for cause in sched_trace.POP_CAUSES:
        assert f'"{cause}"' in source, cause
    # that every exit of `_push_worker` and `_fill` is LABELLED by one of
    # these, in order, is structural since 2026-10-03 (S10): the AST law
    # in test_h3_lifecycle
    # (`test_every_exit_of_push_and_fill_is_an_enumerated_trace_reason`)
    # replaced the substring counts that stood here


# ------------------------------------------------------- the sim lane


def _events_without_meters(record: DecodeRecord) -> tuple[str, ...]:
    rows = []
    for event in record.events:
        row = {key: value for key, value
               in sorted(vars(event).items()) if key not in METER_FIELDS}
        rows.append(f"{type(event).__name__}:{row!r}")
    return tuple(rows)


@pytest.fixture(scope="module")
def traced_pair(sim_color: _h3_sims.SimCapture,
                decode_root: Path) -> tuple[DecodeRecord, DecodeRecord,
                                            Path]:
    _h3_support.skip_unless_slow_lane("the traced-vs-untraced sim decode")
    # BOTH arms set the door explicitly (review 2026-10-17 D10, R4): an
    # OFF arm that merely did not set it ran traced whenever the shell
    # exported HOLO3_SCHED_TRACE, and the pin then compared a traced run
    # with itself.  The ON arm declares `traced`, which is in its decode
    # key, and publication refuses a run dir that contradicts its key.
    with pytest.MonkeyPatch.context() as patch:
        patch.delenv(sched_trace.ENV_ENABLE, raising=False)
        off = _decode_once("sched-trace-off-w1", sim_color, decode_root,
                           workers=1, extra_argv=("--max-pages", "1"))
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(sched_trace.ENV_ENABLE, "1")
        try:
            on = _decode_once("sched-trace-on-w1", sim_color, decode_root,
                              workers=1, extra_argv=("--max-pages", "1"),
                              traced=True)
        finally:
            sched_trace.disarm()
    assert not (off.run_dir / sched_trace.DIR_NAME).exists(), (
        "the OFF arm's run dir holds a trace")
    return off, on, on.run_dir / sched_trace.DIR_NAME


def test_tracing_changes_no_byte_of_the_decode(traced_pair):
    off, on, _out = traced_pair
    assert off.exit_code == 0 and on.exit_code == 0
    assert on.payload_sha256 == off.payload_sha256
    assert on.certified == off.certified
    assert on.certificate_signature == off.certificate_signature
    assert _events_without_meters(on) == _events_without_meters(off)


def test_the_traced_run_writes_the_promised_files(traced_pair):
    _off, on, out = traced_pair
    assert out.is_dir()
    for name in ("summary.json", "subscribers.json", "fires.jsonl",
                 "timeline.jsonl", "place-ladder.jsonl", "folds.jsonl"):
        assert (out / name).is_file(), name
    summary = json.loads((out / "summary.json").read_text())
    assert summary["schema"] == sched_trace.SCHEMA
    assert summary["workers"] == 1
    assert summary["fires"] > 0
    assert summary["wakes"] > 0
    fires = [json.loads(line) for line
             in (out / "fires.jsonl").read_text().splitlines()]
    assert len(fires) == summary["fires"]
    for row in fires:
        for column in ("seq", "plugin", "subject", "stage", "cost",
                       "attempts", "version_at_fire",
                       "tried_version_before", "wakes_since_last_fire",
                       "wake_kinds_since_last_fire", "cpu_s",
                       "wall_started_s", "wall_ended_s", "n_certificates",
                       "n_poses", "n_words", "n_facts",
                       "n_facts_refused", "redundant_input",
                       "input_digest", "input_digest_kind",
                       "input_digest_bare"):
            assert column in row, column
        assert row["wall_s"] >= 0.0
    # the fire ledger and the event log agree on the job count
    assert len(fires) == sum(1 for event in on.events
                             if type(event).__name__ == "JobDone")


def test_the_tile_rows_carry_a_real_cut_digest(traced_pair):
    _off, on, out = traced_pair
    fires = [json.loads(line) for line
             in (out / "fires.jsonl").read_text().splitlines()]
    scans = [row for row in fires if row["plugin"] == "tiles.scan"]
    assert scans, "the colour sim fires tiles.scan"
    assert all(row["input_digest_kind"] == "tile_cut" for row in scans)
    assert all(row["redundant_input"] in (True, False) for row in scans)
    # the bare digest is the cut WITHOUT the stage, so a retry and the
    # scan that armed it can be joined on it offline
    assert all(row["input_digest_bare"] for row in scans)
    assert any(row["input_digest_bare"] != row["input_digest"]
               for row in scans)
    # a row with no digest hook says so rather than claiming False
    others = [row for row in fires
              if row["plugin"] in ("survey", "place")]
    assert all(row["input_digest"] is None for row in others)
    assert all(row["redundant_input"] is None for row in others)


def test_the_fan_out_matrix_and_the_funnels_add_up(traced_pair):
    _off, on, out = traced_pair
    summary = json.loads((out / "summary.json").read_text())
    fan_out = sum(count for row in summary["fan_out"].values()
                  for count in row.values())
    assert fan_out == summary["wakes"]
    stat = next(event for event in reversed(on.events)
                if type(event).__name__ == "EngineStat")
    assert summary["wakes"] == stat.wakes
    fired = sum(row.get("fired", 0) for row in summary["pops"].values())
    assert fired == summary["fires"]
    stale = sum(row.get("stale_seq", 0) + row.get("version_floor", 0)
                for row in summary["pops"].values())
    assert stale == stat.stale_skips


# ------------------------------------------------------- the fold trace


def test_value_stats_differences_only_the_cells_both_rows_carry():
    old_cells = np.array([[0, 0], [0, 1], [0, 2]], np.int64)
    old_values = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0],
                           [7.0, 8.0, 9.0]], np.float32)
    # the new row drops (0,2), keeps (0,0) byte-identical, moves (0,1)
    # by 0.5 and adds (0,3)
    new_cells = np.array([[0, 0], [0, 1], [0, 3]], np.int64)
    new_values = np.array([[1.0, 2.0, 3.0], [4.5, 5.0, 6.0],
                           [0.0, 0.0, 0.0]], np.float32)
    stats = sched_trace_folds.value_stats(old_cells, old_values,
                                          new_cells, new_values)
    assert stats["n_values"] == 3 and stats["n_common"] == 2
    assert stats["values_changed_fraction"] == pytest.approx(0.5)
    assert stats["values_max_abs_delta"] == pytest.approx(0.5)
    assert stats["values_mean_abs_delta"] == pytest.approx(0.5 / 6.0)
    assert stats["cells_changed"] is True
    assert stats["n_cells_added"] == 1 and stats["n_cells_removed"] == 1
    # a first row has no predecessor to difference against
    first = sched_trace_folds.value_stats(None, None, new_cells, new_values)
    assert first["values_changed_fraction"] is None
    assert first["n_cells_added"] == 3 and first["cells_changed"] is True
    # NaN on both sides is not a change, NaN against a number is
    nan_old = np.array([[np.nan, 1.0, 1.0]], np.float32)
    nan_new = np.array([[np.nan, 1.0, 1.0]], np.float32)
    one = np.array([[5, 5]], np.int64)
    assert sched_trace_folds.value_stats(
        one, nan_old, one, nan_new)["values_changed_fraction"] == 0.0
    assert sched_trace_folds.value_stats(
        one, nan_old, one, np.array([[0.0, 1.0, 1.0]], np.float32),
    )["values_changed_fraction"] == 1.0


def test_the_fold_recorder_writes_every_promised_column(tmp_path):
    recorder = sched_trace_folds.FoldRecorder(tmp_path)
    cells = np.array([[0, 0], [0, 1]], np.int64)
    standing = data.ColorEvidenceRow(
        capture_id="cap", level_index=0, patch_ordinal=7, page=0,
        page_cells_yx=cells,
        values=np.zeros((2, 3), np.float32), heldout_logloss=0.40)
    fact = replace(standing, values=np.ones((2, 3), np.float32),
                   heldout_logloss=0.30)
    key = ("cap", 0, 0, 7)
    keys = (("color_row",) + key,)
    recorder.note(kind="color_row", key=key, changed=True,
                  standing=standing, fact=fact,
                  standing_cells=cells, standing_values=standing.values,
                  new_cells=cells, new_values=fact.values,
                  keys=keys, reason="adopted", wall_s=1.5)
    recorder.flush({keys[0]: {("tiles.scan", 1), ("tiles.retry", 2)}})
    recorder.close()
    rows = [json.loads(line) for line
            in (tmp_path / "folds.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    row = rows[0]
    for column in ("wall_s", "kind", "key", "changed", "reason",
                   "standing_loss", "new_loss", "loss_delta",
                   "loss_direction", "values_changed_fraction",
                   "values_max_abs_delta", "values_mean_abs_delta",
                   "n_values", "n_common", "cells_changed",
                   "n_cells_added", "n_cells_removed", "n_subscribers",
                   "cover"):
        assert column in row, column
    assert row["kind"] == "color_row" and row["changed"] is True
    assert row["loss_direction"] == "improved"
    assert row["loss_delta"] == pytest.approx(-0.10)
    assert row["values_changed_fraction"] == pytest.approx(1.0)
    assert row["cells_changed"] is False
    assert row["n_subscribers"] == 2


def test_the_fold_recorder_counts_a_refusal_as_a_record(tmp_path):
    recorder = sched_trace_folds.FoldRecorder(tmp_path)
    cells = np.array([[1, 1]], np.int64)
    standing = data.ColorEvidenceRow(
        capture_id="cap", level_index=0, patch_ordinal=1, page=0,
        page_cells_yx=cells, values=np.zeros((1, 3), np.float32),
        heldout_logloss=0.2)
    recorder.note(kind="color_row", key=("cap", 0, 0, 1), changed=False,
                  standing=standing, fact=standing,
                  standing_cells=cells, standing_values=standing.values,
                  new_cells=cells, new_values=standing.values,
                  keys=(), reason="identical", wall_s=0.5)
    summary = recorder.summary()
    recorder.close()
    assert summary["by_kind"]["color_row"] == {"records": 1, "refused": 1}
    assert summary["loss_direction"]["color_row"] == {"equal": 1}
    row = json.loads((tmp_path / "folds.jsonl").read_text().strip())
    assert row["changed"] is False and row["n_subscribers"] is None


def _bare_color_store() -> object:
    """A store with only the cells `_fold_color_row` touches.

    The colour fold needs the site geometry and four dicts and nothing
    else, so the real fold can be driven in milliseconds -- the colour
    SIM decode that exercises it end to end is a slow-lane fixture
    (`traced_pair`), and this keeps the hook itself on the fast lane.
    """
    store = object.__new__(engine._Engine)
    store.row = identity.resolve_format_ref("c2-cmy8-r0700@10x10")
    store.geometry = identity.build_site_geometry(store.row)
    store._color_rows = {}
    store._tile_cover_color = {}
    store._color_row_cover = {}
    store._tile_lane_generation = {}
    # the footing counter beside the lane one, and the level the fold
    # reads to name the footing (store_folds._advance_tile_lanes)
    store._union_generation = {}
    store._levels = {("cap", 0): data.Level(
        index=0, ppc=Fraction(8), scale=Fraction(1), shape_px=(8, 8),
        label="l0")}
    return store


def test_the_colour_fold_records_adoption_refusal_and_the_loss(tmp_path):
    store = _bare_color_store()
    cells = np.array([[y, x] for y in range(8) for x in range(8)], np.int64)
    first = data.ColorEvidenceRow(
        capture_id="cap", level_index=0, patch_ordinal=3, page=0,
        page_cells_yx=cells,
        values=np.zeros((len(cells), 3), np.float32),
        heldout_logloss=0.50)
    worse = replace(first, values=np.full((len(cells), 3), 0.25, np.float32),
                    heldout_logloss=0.70)
    trace = sched_trace.arm(tmp_path, workers=1, every_s=3600.0)
    try:
        assert store._fold_color_row(first)[0] is True
        assert store._fold_color_row(worse)[0] is True
        # the third fold is the second fact again: nothing changed
        assert store._fold_color_row(worse)[0] is False
        trace.folds.flush(None)
        trace.finish(object())
        rows = [json.loads(line) for line in
                (trace.out_dir / "folds.jsonl").read_text().splitlines()]
    finally:
        sched_trace.disarm()
    assert [row["kind"] for row in rows] == ["color_row"] * 3
    assert [row["loss_direction"] for row in rows] == [
        "first", "worsened", "equal"]
    assert [row["changed"] for row in rows] == [True, True, False]
    # THE MEASUREMENT THIS EXISTS FOR: the middle fold's loss got worse
    # and the fold adopted it anyway, with every value moved
    assert rows[1]["loss_delta"] == pytest.approx(0.20)
    assert rows[1]["values_changed_fraction"] == pytest.approx(1.0)
    assert rows[1]["values_max_abs_delta"] == pytest.approx(0.25)
    assert rows[1]["cells_changed"] is False
    # the cover is what makes the ownership question answerable offline
    assert all(row["cover"] for row in rows)
    assert rows[0]["cover"] == rows[2]["cover"]


def test_the_fold_trace_is_silent_when_the_instrument_is_off(tmp_path):
    store = _bare_color_store()
    cells = np.array([[0, 0], [0, 1]], np.int64)
    fact = data.ColorEvidenceRow(
        capture_id="cap", level_index=0, patch_ordinal=0, page=0,
        page_cells_yx=cells, values=np.zeros((2, 3), np.float32),
        heldout_logloss=0.1)
    assert sched_trace.TRACE.enabled is False
    assert store._fold_color_row(fact)[0] is True
    assert not list(tmp_path.iterdir())
    # the null recorder answers every door the armed one does
    sched_trace.TRACE.folds.note()
    sched_trace.TRACE.folds.flush(None)
    assert sched_trace.TRACE.folds.summary() == {}


def test_the_colour_sim_writes_colour_row_folds(traced_pair):
    """The end-to-end half of the fold trace: a real colour decode."""
    _off, on, out = traced_pair
    rows = [json.loads(line) for line
            in (out / "folds.jsonl").read_text().splitlines()]
    colour = [row for row in rows if row["kind"] == "color_row"]
    assert colour, "the colour sim folds ColorEvidenceRow"
    assert all(row["loss_direction"] in
               ("first", "improved", "worsened", "equal", "unknown")
               for row in colour)
    assert all(row["n_values"] > 0 for row in colour)
    # every adopted row names the key it moved and the subscribers it woke
    adopted = [row for row in colour if row["changed"]]
    assert adopted and all(row["keys"] for row in adopted)
    assert all(row["n_subscribers"] is not None for row in adopted)
    summary = json.loads((out / "summary.json").read_text())
    assert summary["folds"]["rows"] >= len(rows)
    assert "color_row" in summary["folds"]["by_kind"]


# ------------------------------------------- the colour adoption hatch


def test_the_adoption_hatch_defaults_to_the_shipped_fold():
    assert store_folds.color_row_adopt_by_env({}) == store_folds.ADOPT_LAST
    for junk in ("", " ", "nonsense", "IMPROVE!", "0"):
        assert store_folds.color_row_adopt_by_env(
            {store_folds.ENV_COLOR_ROW_ADOPT: junk}) == \
            store_folds.ADOPT_LAST
    for mode in store_folds.COLOR_ROW_ADOPT_MODES:
        assert store_folds.color_row_adopt_by_env(
            {store_folds.ENV_COLOR_ROW_ADOPT: mode.upper()}) == mode
    # a hand-built store folds as shipped: the class attribute is the
    # default and only `_Store.__init__` ever reads the environment
    assert store_folds._Folds._color_row_adopt == store_folds.ADOPT_LAST


def _colour_row(loss: float, fill: float, cells: np.ndarray):
    return data.ColorEvidenceRow(
        capture_id="cap", level_index=0, patch_ordinal=3, page=0,
        page_cells_yx=cells,
        values=np.full((len(cells), 3), fill, np.float32),
        heldout_logloss=loss)


@pytest.mark.parametrize("mode,adopts", [
    (store_folds.ADOPT_LAST, (True, True, True)),
    (store_folds.ADOPT_IMPROVE, (True, False, False)),
    (store_folds.ADOPT_NONWORSE, (True, False, True)),
])
def test_the_hatch_decides_only_on_the_loss_when_the_cells_stand(
        mode, adopts):
    store = _bare_color_store()
    store._color_row_adopt = mode
    cells = np.array([[y, x] for y in range(8) for x in range(8)], np.int64)
    # better, then worse, then equal to the row standing at each point
    assert store._fold_color_row(_colour_row(0.50, 0.0, cells))[0] is True
    assert store._fold_color_row(
        _colour_row(0.40, 0.1, cells))[0] is adopts[0]
    standing = store._color_rows[("cap", 0, 0, 3)].heldout_logloss
    assert store._fold_color_row(
        _colour_row(standing + 0.2, 0.2, cells))[0] is adopts[1]
    standing = store._color_rows[("cap", 0, 0, 3)].heldout_logloss
    assert store._fold_color_row(
        _colour_row(standing, 0.3, cells))[0] is adopts[2]


@pytest.mark.parametrize("mode", store_folds.COLOR_ROW_ADOPT_MODES)
def test_no_mode_ever_refuses_a_row_that_carries_different_cells(mode):
    store = _bare_color_store()
    store._color_row_adopt = mode
    small = np.array([[0, 0], [0, 1]], np.int64)
    wide = np.array([[0, 0], [0, 1], [0, 2]], np.int64)
    assert store._fold_color_row(_colour_row(0.10, 0.0, small))[0] is True
    # a much worse loss over a wider cell set still adopts: the cells
    # are the row's contribution to the tile cover
    assert store._fold_color_row(_colour_row(9.00, 0.0, wide))[0] is True


def test_the_hatch_records_its_refusal_in_the_fold_trace(tmp_path):
    store = _bare_color_store()
    store._color_row_adopt = store_folds.ADOPT_IMPROVE
    cells = np.array([[0, 0], [0, 1]], np.int64)
    trace = sched_trace.arm(tmp_path, workers=1, every_s=3600.0)
    try:
        store._fold_color_row(_colour_row(0.20, 0.0, cells))
        store._fold_color_row(_colour_row(0.90, 0.5, cells))
        trace.folds.flush(None)
        trace.finish(object())
        rows = [json.loads(line) for line in
                (trace.out_dir / "folds.jsonl").read_text().splitlines()]
    finally:
        sched_trace.disarm()
    assert [row["changed"] for row in rows] == [True, False]
    assert rows[1]["reason"] == "refused_improve"
    # the refused row's numbers are still recorded, so the A/B can say
    # what it turned down
    assert rows[1]["loss_delta"] == pytest.approx(0.70)
    assert rows[1]["values_changed_fraction"] == pytest.approx(1.0)
