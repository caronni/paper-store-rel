"""Plugin wake hygiene and record-keeping (2026-10-03, stage S9).

Five re-review findings in the plugins area, each pinned here over the
in-memory engine pattern of test_h3_store_wakes / test_h3_lifecycle (a
store with no executor: pushes are dropped, folds, births and wakes run):

(a) the residue rows read the chain head's verdicts only
    (`local_ctx.READ_STAGES`): a failed retry150 verdict arms them but
    wakes none of them;
(b) `tiles.scan` does not re-decode a cut it already read at the
    tile-lane's current generation (the stale evidence key's wake), and
    `tiles.union` does not re-decode a summed cut it already read at the
    footing's current generation (review 2026-10-17 D2, R2);
(c) the `HOLO3_COLOR_ROW_ADOPT` hatch is recorded (RunOpen, the run
    dir's tree record, a banner) and refused by the fixture builder;
(d) `tiles.planek` and `tiles.swim` stamp a one-lane verdict with that
    lane's generation (`local_ctx.Generations`);
(e) `tiles.local`'s colour arm subscribes to the covering windows' poses.
"""
from __future__ import annotations

import dataclasses
from fractions import Fraction
from pathlib import Path

import numpy as np
import pytest

from holo.receiver import data, engine, store_folds
from holo.receiver.descriptor import KEY_ATTEMPT, KEY_POSE_AFFINE
from holo.receiver.format import identity
from holo.receiver.plugins import local_ctx, plane_k, swim, tiles, tiles_sched
from holo.receiver.tests import _h3_facts, _h3_fixture_build

CAPTURE_ID = _h3_facts.CAPTURE_ID
PPC = Fraction(4)
COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
RESIDUE_ROWS = ("tiles.local", "tiles.planek", "tiles.swim")
LANE = (CAPTURE_ID, 0)


def _engine(format_ref: str | None = None) -> engine._Engine:
    instance = _h3_facts.new_engine()
    if format_ref is not None:
        instance = engine._Engine(dataclasses.replace(
            instance._request, format_ref=format_ref), [])
    instance._push_worker = lambda worker: None
    return instance


def _rows(monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...]) -> None:
    rows = tuple(engine.DESCRIPTOR_BY_NAME[name] for name in names)
    monkeypatch.setattr(engine, "DESCRIPTORS", rows)
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                        {row.name: row for row in rows})


def _verdict(stream_id: str, stage: str, outcome: str,
             components: tuple = (LANE,),
             generation: int = 0) -> data.AttemptFact:
    return dataclasses.replace(
        _h3_facts.attempt(outcome), stream_id=stream_id, stage=stage,
        components=components, generation=generation)


def _streams() -> tuple[str, ...]:
    row = identity.resolve_format_ref(COLOR_FORMAT_REF)
    return tuple(stream.stream_id for stream in row.streams)


# ---------------------------------------------------------------------------
# (a) + (e): the residue rows on a cmy8 page.


@pytest.fixture
def residue(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Stream C of tile (0, 0) fails its scan on lane A; the three residue
    rows are born on it.  The covering colour window is placed."""
    _rows(monkeypatch, RESIDUE_ROWS)
    instance = _engine(COLOR_FORMAT_REF)
    wid = (CAPTURE_ID, 0, 0, _h3_facts.EXTENT)
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window(wid=wid, ordinal=0))
    instance._ingest(_h3_facts.placement(wid, quality=1.0))
    instance._ingest(_h3_facts.color_row())
    streams = _streams()
    instance._ingest(_verdict(streams[0], tiles.STAGE_SCAN,
                              tiles.OUTCOME_FAILED))
    subjects = {
        "tiles.local": (0, 0, 0, PPC),
        "tiles.swim": (0, 0, 0, PPC),
        "tiles.planek": (0, 0, 0, streams[0], PPC),
    }
    workers = {name: instance._bookmarks[(name, subject)]
               for name, subject in subjects.items()}
    return {"engine": instance, "workers": workers, "streams": streams,
            "wid": wid}


def _versions(residue: dict) -> dict[str, int]:
    return {name: worker.version
            for name, worker in residue["workers"].items()}


def test_read_stages_are_the_chain_head_and_arming_keeps_the_retry():
    assert local_ctx.READ_STAGES == (tiles.STAGE_SCAN, tiles.STAGE_UNION)
    assert tiles.STAGE_RETRY150 in local_ctx.ARMING_STAGES
    assert tiles.STAGE_RETRY150 in plane_k.ARMING_STAGES
    assert {tiles.STAGE_RETRY150, tiles.STAGE_LOCAL150} \
        <= set(swim.ARMING_STAGES)


@pytest.mark.parametrize("name", RESIDUE_ROWS)
def test_the_residue_reads_name_no_retry_or_local_verdict(residue, name):
    stages = {read[5] for read in residue["workers"][name].reads
              if read[0] == KEY_ATTEMPT}
    assert stages == {tiles.STAGE_SCAN, tiles.STAGE_UNION}, (
        "a retry or local verdict follows a scan/union failure that "
        "already armed and woke the row; it carries no input the row "
        "reads, so it is not a read")


@pytest.mark.parametrize("lane", (LANE, PPC), ids=("lane", "footing"))
def test_a_failed_retry_verdict_wakes_no_residue_row(residue, lane):
    instance = residue["engine"]
    components = ((LANE,) if lane == LANE
                  else (LANE, ("decafbad" * 8, 0)))
    if lane == PPC:
        instance._ingest(dataclasses.replace(_h3_facts.capture(),
                                             capture_id="decafbad" * 8))
    before = _versions(residue)
    instance._ingest(_verdict(residue["streams"][0], tiles.STAGE_RETRY150,
                              tiles.OUTCOME_FAILED, components))
    assert _versions(residue) == before


def test_a_failed_local_verdict_does_not_wake_the_swim(residue):
    before = _versions(residue)
    residue["engine"]._ingest(_verdict(
        residue["streams"][0], tiles.STAGE_LOCAL150, tiles.OUTCOME_FAILED))
    assert _versions(residue)["tiles.swim"] == before["tiles.swim"]


def test_a_failed_scan_verdict_still_wakes_every_residue_row(residue):
    before = _versions(residue)
    residue["engine"]._ingest(_verdict(
        residue["streams"][0], tiles.STAGE_SCAN, tiles.OUTCOME_FAILED,
        generation=1))
    after = _versions(residue)
    assert all(after[name] > before[name] for name in RESIDUE_ROWS), after


def test_a_retry_certificate_still_wakes_every_residue_row(residue):
    before = _versions(residue)
    residue["engine"]._ingest(dataclasses.replace(
        _h3_facts.certificate(0, 0, 0), stream_id=residue["streams"][0],
        source="tiles/retry150"))
    after = _versions(residue)
    assert all(after[name] > before[name] for name in RESIDUE_ROWS), after


def test_the_colour_local_arm_subscribes_to_its_covering_poses(residue):
    worker = residue["workers"]["tiles.local"]
    assert (KEY_POSE_AFFINE, residue["wid"]) in worker.reads, (
        "the colour arm samples the raster through the covering "
        "windows' placements (color_region.region_window)")
    before = worker.version
    residue["engine"]._ingest(_h3_facts.placement(
        residue["wid"], origin_yx=(1.5, 0.0), quality=0.5))
    assert worker.version > before, (
        "a pose revision of a covering colour window wakes the local row")


def test_the_k_local_arm_reads_no_pose(monkeypatch):
    _rows(monkeypatch, ("tiles.local",))
    instance = _engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window())
    instance._ingest(_h3_facts.placement())
    instance._ingest(_h3_facts.evidence())
    instance._ingest(_verdict("main", tiles.STAGE_SCAN, tiles.OUTCOME_FAILED))
    worker = instance._bookmarks[("tiles.local", (0, 0, 0, PPC))]
    assert not any(read[0] == KEY_POSE_AFFINE for read in worker.reads), (
        "the K arm reads WindowEvidence, already sampled: a K pose reaches "
        "it as new evidence, i.e. as a new chain-head verdict")


# ---------------------------------------------------------------------------
# (b): tiles.scan and the stale evidence key.

WID_STAYS = _h3_facts.WINDOW_ID
WID_LEAVES = (CAPTURE_ID, 0, 1, (0, 64, 64, 128))
TILE_T = (0, 0, 0, CAPTURE_ID, 0)


def _record_scan(instance: engine._Engine) -> None:
    """What the scan job would merge: a failed verdict at the tile-lane's
    current generation."""
    generation = instance.tile_lane_generation(TILE_T)
    instance._ingest(_verdict("main", tiles.STAGE_SCAN, tiles.OUTCOME_FAILED,
                              generation=generation))


def test_a_stale_evidence_wake_does_not_re_decode_the_same_cut(monkeypatch):
    _rows(monkeypatch, (tiles_sched.PLUGIN_SCAN,))
    instance = _engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window(wid=WID_STAYS))
    instance._ingest(_h3_facts.window(wid=WID_LEAVES, ordinal=1))
    instance._ingest(_h3_facts.evidence(wid=WID_STAYS))
    instance._ingest(_h3_facts.evidence(wid=WID_LEAVES))
    worker = instance._bookmarks[(tiles_sched.PLUGIN_SCAN, TILE_T)]
    assert tiles_sched.prepare_scan(instance, TILE_T, "payload") is not None
    _record_scan(instance)
    assert tiles_sched.prepare_scan(instance, TILE_T, "payload") is None, (
        "every pending stream already holds a verdict at this generation")
    # WID_LEAVES re-fits off tile T: T's cut moved (it lost a component)
    off_t = _h3_facts.tile_cells() + np.array([64, 0])
    instance._ingest(_h3_facts.evidence(wid=WID_LEAVES, cells=off_t))
    assert tiles_sched.prepare_scan(instance, TILE_T, "payload") is not None
    _record_scan(instance)
    generation = instance.tile_lane_generation(TILE_T)
    # ... and re-fits again, still off T: the stale key wakes T's scan
    before = worker.version
    instance._ingest(_h3_facts.evidence(wid=WID_LEAVES, cells=off_t,
                                        score=0.5))
    assert worker.version > before, "the stale subscription stays"
    assert instance.tile_lane_generation(TILE_T) == generation
    assert tiles_sched.prepare_scan(instance, TILE_T, "payload") is None, (
        "the identical cut at the same generation: nothing to read")
    # a real move of T's cut: the window that stays re-fits
    instance._ingest(_h3_facts.evidence(wid=WID_STAYS, score=0.25))
    assert instance.tile_lane_generation(TILE_T) > generation
    assert tiles_sched.prepare_scan(instance, TILE_T, "payload") is not None


def test_a_verdict_at_an_older_generation_does_not_hold_the_scan(
        monkeypatch):
    _rows(monkeypatch, (tiles_sched.PLUGIN_SCAN,))
    instance = _engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window())
    instance._ingest(_h3_facts.evidence())
    instance._ingest(_verdict("main", tiles.STAGE_SCAN, tiles.OUTCOME_FAILED,
                              generation=0))
    assert instance.tile_lane_generation(TILE_T) != 0
    assert tiles_sched.prepare_scan(instance, TILE_T, "payload") is not None


# ---------------------------------------------------------------------------
# (b'): tiles.union and the stale evidence key (review 2026-10-17 D2, R2).

CAPTURE_B = "decafbad" * 8
WID_B = (CAPTURE_B, 0, 0, _h3_facts.EXTENT)
TILE_U = (0, 0, 0, PPC)


def _union_engine(monkeypatch: pytest.MonkeyPatch) -> engine._Engine:
    """Two captures at one footing, each with evidence over tile (0, 0):
    an ARMED union."""
    _rows(monkeypatch, (tiles_sched.PLUGIN_UNION,))
    instance = _engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(dataclasses.replace(_h3_facts.capture(),
                                         capture_id=CAPTURE_B,
                                         path=Path("scan-b.tiff")))
    instance._ingest(_h3_facts.window())
    instance._ingest(_h3_facts.window(wid=WID_B, ordinal=1))
    instance._ingest(_h3_facts.evidence())
    instance._ingest(_h3_facts.evidence(wid=WID_B))
    return instance


def _record_union(instance: engine._Engine, generation: int) -> None:
    """What the union job would merge: a failed summed verdict."""
    instance._ingest(_verdict("main", tiles.STAGE_UNION,
                              tiles.OUTCOME_FAILED,
                              components=(LANE, (CAPTURE_B, 0)),
                              generation=generation))


def test_one_capture_arms_no_union(monkeypatch):
    _rows(monkeypatch, (tiles_sched.PLUGIN_UNION,))
    instance = _engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window())
    instance._ingest(_h3_facts.evidence())
    assert tiles_sched.prepare_union(instance, TILE_U, "payload") is None


def test_a_stale_evidence_wake_does_not_re_decode_the_same_summed_cut(
        monkeypatch):
    instance = _union_engine(monkeypatch)
    assert tiles_sched.prepare_union(instance, TILE_U, "payload") is not None
    generation = instance.union_generation(0, 0, 0, PPC)
    _record_union(instance, generation)
    assert instance.attempt_verdict(0, 0, 0, "main", tiles.STAGE_UNION,
                                    PPC) == (tiles.OUTCOME_FAILED,
                                             generation)
    assert tiles_sched.prepare_union(instance, TILE_U, "payload") is None, (
        "every pending stream already holds a union verdict at the "
        "footing's current generation")
    # a real move of the summed cut: lane B's evidence re-fits
    instance._ingest(_h3_facts.evidence(wid=WID_B, score=0.5))
    assert instance.union_generation(0, 0, 0, PPC) > generation
    assert tiles_sched.prepare_union(instance, TILE_U, "payload") is not None


def test_a_verdict_at_an_older_generation_does_not_hold_the_union(
        monkeypatch):
    instance = _union_engine(monkeypatch)
    _record_union(instance, 0)
    assert instance.union_generation(0, 0, 0, PPC) != 0
    assert tiles_sched.prepare_union(instance, TILE_U, "payload") is not None


# ---------------------------------------------------------------------------
# (d): one-lane residue verdicts carry their lane's generation.

LANE_B = ("decafbad" * 8, 0)
STAMPS = local_ctx.Generations(union=7, lanes=((LANE, 3), (LANE_B, 5)))


def _cut(lane: tuple[str, int]) -> tiles.TileCut:
    return tiles.TileCut(lane[0], lane[1], 0, 0, 0,
                         np.zeros((1, 1), np.float32),
                         np.zeros(1, np.uint16))


@pytest.fixture
def stamped(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Every attempt as (component count, stamped generation)."""
    seen: list[tuple[int, int]] = []

    def attempt_tile(row, geometry, components, stream_id, stage,
                     generation=0):
        seen.append((len(components), int(generation)))
        fact = dataclasses.replace(_h3_facts.attempt(), stage=stage,
                                   generation=int(generation))
        return tiles.TileAttemptResult(fact, None, None)

    monkeypatch.setattr(tiles, "attempt_tile", attempt_tile)
    monkeypatch.setattr(plane_k, "lane_cut",
                        lambda row, geometry, plan, *rest: _cut(plan))
    monkeypatch.setattr(swim, "swim_components",
                        lambda row, geometry, plan, *rest: ([_cut(plan)], []))
    return seen


@pytest.mark.parametrize("plans, expected", (
    ((LANE,), 3), ((LANE_B,), 5), ((LANE, LANE_B), 7)),
    ids=("lane-a", "lane-b", "summed"))
def test_planek_stamps_a_one_lane_verdict_with_its_lane(stamped, plans,
                                                        expected):
    plane_k.planek_job(None, None, plans, {}, 0, 0, 0, "C", 0, STAMPS)
    assert stamped == [(len(plans), expected)]


@pytest.mark.parametrize("plans, expected", (
    ((LANE,), 3), ((LANE_B,), 5), ((LANE, LANE_B), 7)),
    ids=("lane-a", "lane-b", "summed"))
def test_swim_stamps_a_one_lane_verdict_with_its_lane(stamped, plans,
                                                      expected):
    swim.swim_job(None, None, plans, {}, 0, 0, 0, ("C", "M"), STAMPS)
    assert stamped == [(len(plans), expected)] * 2


def test_lane_generations_reads_the_footing_and_every_cover_lane():
    instance = _engine()
    instance._ingest(_h3_facts.capture())
    instance._ingest(_h3_facts.window())
    instance._ingest(_h3_facts.evidence())
    instance._ingest(_h3_facts.evidence(score=0.5))
    stamps = local_ctx.lane_generations(instance, 0, 0, 0, PPC)
    assert stamps.union == instance.union_generation(0, 0, 0, PPC)
    assert stamps.lanes == ((LANE, instance.tile_lane_generation(TILE_T)),)
    assert stamps.of((_cut(LANE),)) == instance.tile_lane_generation(TILE_T)


# ---------------------------------------------------------------------------
# (c): the colour-row adoption hatch is visible.


def _started(monkeypatch: pytest.MonkeyPatch, mode: str | None,
             tmp_path: Path) -> engine._Engine:
    if mode is None:
        monkeypatch.delenv(store_folds.ENV_COLOR_ROW_ADOPT, raising=False)
    else:
        monkeypatch.setenv(store_folds.ENV_COLOR_ROW_ADOPT, mode)
    monkeypatch.setattr(engine, "_intake_run",
                        lambda request, row: ((), (), ()))
    instance = _h3_facts.new_engine()
    instance = engine._Engine(dataclasses.replace(
        instance._request, run_dir=tmp_path / "run"), [])
    instance._start()
    return instance


@pytest.mark.parametrize("mode", store_folds.COLOR_ROW_ADOPT_MODES)
def test_the_run_records_the_effective_adoption_mode(monkeypatch, tmp_path,
                                                     capsys, mode):
    instance = _started(monkeypatch, mode, tmp_path)
    opened = [event for event in instance._events
              if isinstance(event, data.RunOpen)]
    assert [event.color_row_adopt for event in opened] == [mode]
    tree = (tmp_path / "run" / "tree").read_text().splitlines()
    assert f"{store_folds.ENV_COLOR_ROW_ADOPT}={mode}" in tree
    banner = capsys.readouterr().err
    if mode == store_folds.ADOPT_LAST:
        assert store_folds.ENV_COLOR_ROW_ADOPT not in banner
    else:
        assert f"{store_folds.ENV_COLOR_ROW_ADOPT}={mode}" in banner


def test_an_unset_hatch_records_the_shipped_mode(monkeypatch, tmp_path):
    instance = _started(monkeypatch, None, tmp_path)
    opened = [event for event in instance._events
              if isinstance(event, data.RunOpen)]
    assert opened[0].color_row_adopt == store_folds.ADOPT_LAST
    assert data.RunOpen.__dataclass_fields__[
        "color_row_adopt"].default == store_folds.ADOPT_LAST


@pytest.mark.parametrize("declared", (None, "", "last", " LAST "))
def test_the_fixture_builder_accepts_the_shipped_mode(declared):
    environ = ({} if declared is None
               else {store_folds.ENV_COLOR_ROW_ADOPT: declared})
    _h3_fixture_build.refuse_non_default_adopt(environ)


@pytest.mark.parametrize("declared", ("improve", "nonworse", "junk"))
def test_the_fixture_builder_refuses_any_other_mode(declared):
    with pytest.raises(RuntimeError, match=store_folds.ENV_COLOR_ROW_ADOPT):
        _h3_fixture_build.refuse_non_default_adopt(
            {store_folds.ENV_COLOR_ROW_ADOPT: declared})


def test_a_decode_under_the_hatch_is_refused_before_any_cache(monkeypatch,
                                                              tmp_path):
    monkeypatch.setenv(store_folds.ENV_COLOR_ROW_ADOPT, "improve")
    monkeypatch.setattr(_h3_fixture_build._h3_support,
                        "skip_unless_slow_lane", lambda what: None)

    def no_cache(*args: object, **kwargs: object) -> None:
        raise AssertionError("the cache was consulted")

    monkeypatch.setattr(_h3_fixture_build, "_decode_cache_dir", no_cache)
    monkeypatch.setattr(_h3_fixture_build, "_run_decode", no_cache)
    with pytest.raises(RuntimeError, match="improve"):
        _h3_fixture_build._decode_group("s9-refusal", (), tmp_path)
