from __future__ import annotations

import ast
import dataclasses
import typing
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from holo3 import data, descriptor as descriptor_module, engine
from holo3 import store as store_module
from holo3.tests import _h3_support

HOLO3_ROOT = _h3_support.HOLO3_ROOT

DECODE_REQUEST_FIELDS = (
    "scans", "dpis", "format_ref", "max_pages", "workers", "complete",
    "no_close", "diag_port", "run_dir", "pooled_color_context",
    "plane_fields", "resume", "snapshot_every_s")

WORKER_BOOKMARK_FIELDS = (
    "plugin", "subject", "reads", "version", "tried_version", "attempts",
    "last_cost", "retired", "inflight", "pending", "seat_seq", "seat_cost")

WORKER_BOOKMARK_DEFAULTS = {
    "version": 0, "tried_version": -1,
    "attempts": 0, "last_cost": 0, "retired": False,
    "inflight": False, "pending": False, "seat_seq": -1, "seat_cost": 0}

COST_PARAMETERS = ("store", "subject", "stage", "attempts", "last_cost")

KEY_KINDS_GOLDEN = (
    "pose_affine", "pose_route", "place_stage", "evidence_fit",
    "evidence_read", "color_row", "color_pop", "pooled_ctx",
    "region_pitch", "region_ctx",
    "lattice_seed", "lane_poses", "page_certs", "tile", "live_pages",
    "plane_field")

KEY_CONSTANTS_GOLDEN = {
    "KEY_POSE_AFFINE": "pose_affine",
    "KEY_POSE_ROUTE": "pose_route",
    "KEY_PLACE_STAGE": "place_stage",
    "KEY_EVIDENCE_FIT": "evidence_fit",
    "KEY_EVIDENCE_READ": "evidence_read",
    "KEY_COLOR_ROW": "color_row",
    "KEY_COLOR_POP": "color_pop",
    "KEY_POOLED_CTX": "pooled_ctx",
    "KEY_REGION_PITCH": "region_pitch",
    "KEY_REGION_CTX": "region_ctx",
    "KEY_LATTICE_SEED": "lattice_seed",
    "KEY_LANE_POSES": "lane_poses",
    "KEY_PAGE_CERTS": "page_certs",
    "KEY_TILE": "tile",
    "KEY_LIVE_PAGES": "live_pages",
    "KEY_PLANE_FIELD": "plane_field"}

CERTIFICATE_FIELDS = (
    "page", "ty", "tx", "stream_id", "user_bits", "source")

ATTEMPT_FACT_FIELDS = (
    "page", "ty", "tx", "stream_id", "stage", "outcome", "n_informative",
    "n_iters", "syndrome_ok", "crc_ok", "components")

JOB_RESULT_FIELDS = ("facts", "events", "cpu_s")

RUN_RESULT_FIELDS = ("status", "payload", "payload_sha256", "certified",
                     "plugin_rows")

PLUGIN_ROW_FIELDS = ("plugin", "jobs", "cpu_seconds", "certificates",
                     "poses", "words")

# the event contract is the producer bill (docs/DIAG-DESIGN.md §4): a
# move here is a deliberate contract change, never a test to update in
# passing. SnapshotReplayed joined it 2026-08-30 with the resume ruling.
EVENT_UNION_GOLDEN = (
    "RunOpen", "CaptureOpen", "SnapshotReplayed", "SurveyDone",
    "PoseCommitted", "WindowSettled",
    "WindowScheduled", "WindowRetired", "EngineStat",
    "WordOutcome", "AddressCoverage", "CalibrateAdopted", "TileOutcome",
    # FieldFitted joins the union with the FIELD band's producer (the
    # `fields` row now emits one bounded fit event per lane-page).
    "JobDone", "CloseCheck", "RunDone", "FieldFitted")

MUTABLE_BY_DESIGN = ("WorkerBookmark", "WindowState", "StatBoard")

PLUGIN_DESCRIPTOR_FIELDS = (
    "name", "subject_kind", "born_by", "subjects_of", "reads", "eligible",
    "stage", "cost", "retire", "prepare", "produces", "prices")

# D6 addendum 5/10 + the 2026-08-29 ruling: every pricing name is gone
# from the contract seam — cost is a scheduling function of the plugins
PRICE_MECHANISM_GONE = (
    "TIER_COST", "job_price", "TIER_SURVEY", "TIER_CALIBRATE",
    "TIER_PAYLOAD", "TIER_RING", "TIER_WORD_CENTRE", "TIER_WORD_REST",
    "TIER_WIDE", "TIER_COLD_LIVE", "TIER_COLD_REST", "TIER_REFINE",
    "LANE_COST_PER_RUNG", "COLD_COST_PER_RUNG", "CHILD_PREMIUM",
    "REWORK_BASE", "REWORK_STEP", "REWORK_FLOOR", "REWORK_SLOPE")


def _data_dataclasses() -> tuple[tuple[str, type], ...]:
    found = []
    for name in sorted(dir(data)):
        member = getattr(data, name)
        if isinstance(member, type) and dataclasses.is_dataclass(member):
            found.append((name, member))
    return tuple(found)


def test_decode_request_is_a_frozen_record_with_the_declared_field_set():
    assert data.DecodeRequest.__dataclass_params__.frozen
    _h3_support.assert_golden(
        "DecodeRequest fields",
        tuple(f.name for f in dataclasses.fields(
            data.DecodeRequest)),
        DECODE_REQUEST_FIELDS)


def test_decode_request_carries_no_validation_of_its_own():
    request = data.DecodeRequest(
        scans=(Path("a.tiff"),), dpis=(1200.0,), format_ref="L:nope",
        max_pages=0, workers=0, complete=False, no_close=False,
        diag_port=None, run_dir=Path("run"))
    assert request.workers == 0 and request.max_pages == 0
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.workers = 8


def test_decode_request_is_the_same_object_the_engine_exports():
    assert engine.DecodeRequest is data.DecodeRequest


def test_fact_key_vocabulary_is_closed_at_sixteen_kinds():
    _h3_support.assert_golden("KEY_KINDS", descriptor_module.KEY_KINDS,
                              KEY_KINDS_GOLDEN)
    assert len(set(descriptor_module.KEY_KINDS)) == 16


@pytest.mark.parametrize("name,value", sorted(KEY_CONSTANTS_GOLDEN.items()))
def test_each_key_constant_holds_its_frozen_kind_string(name, value):
    _h3_support.assert_golden(name, getattr(descriptor_module, name), value)


def test_key_kinds_lists_exactly_the_key_constants():
    declared = {getattr(descriptor_module, name)
                for name in KEY_CONSTANTS_GOLDEN}
    assert declared == set(descriptor_module.KEY_KINDS)


def _key_names_referenced(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id.startswith("KEY_"):
            found.add(node.id)
        if isinstance(node, ast.Attribute) and node.attr.startswith("KEY_"):
            found.add(node.attr)
        if isinstance(node, ast.alias) and node.name.startswith("KEY_"):
            found.add(node.name)
    return found


def _referenced_across(root: Path) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for path in _h3_support.source_files(root):
        if "conversion_docs" in path.parts or "tests" in path.parts:
            continue
        names = _key_names_referenced(path)
        if names:
            index[path.name] = names
    return index


def test_no_module_invents_a_key_kind_outside_the_closed_vocabulary():
    known = set(KEY_CONSTANTS_GOLDEN) | {"KEY_KINDS"}
    checks = _h3_support.Checks("closed FactKey vocabulary")
    for filename, names in sorted(_referenced_across(HOLO3_ROOT).items()):
        checks.equal(f"{filename} references only declared key constants",
                     tuple(sorted(names - known)), ())
    checks.assert_clean()


def test_the_key_kinds_plugins_subscribe_are_a_subset_of_the_vocabulary():
    subscribed: set[str] = set()
    for names in _referenced_across(HOLO3_ROOT / "plugins").values():
        subscribed |= names
    assert subscribed <= set(KEY_CONSTANTS_GOLDEN)
    assert subscribed, "no plugin subscribes to any FactKey at all"


def test_worker_bookmark_is_the_mutable_scheduling_record():
    assert not descriptor_module.WorkerBookmark.__dataclass_params__.frozen
    _h3_support.assert_golden(
        "WorkerBookmark fields",
        tuple(f.name for f in dataclasses.fields(
            descriptor_module.WorkerBookmark)),
        WORKER_BOOKMARK_FIELDS)
    bookmark = descriptor_module.WorkerBookmark(
        plugin="probe", subject="s", reads=())
    for name, expected in sorted(WORKER_BOOKMARK_DEFAULTS.items()):
        _h3_support.assert_golden(f"WorkerBookmark.{name} default",
                                  getattr(bookmark, name), expected)


def _is_due(bookmark: descriptor_module.WorkerBookmark) -> bool:
    return bookmark.tried_version != bookmark.version


def test_a_fresh_bookmark_is_below_its_version_floor_so_it_fires_once():
    bookmark = descriptor_module.WorkerBookmark(
        plugin="probe", subject="s", reads=())
    assert bookmark.tried_version < bookmark.version
    assert _is_due(bookmark) is True
    bookmark.tried_version = bookmark.version
    assert _is_due(bookmark) is False
    bookmark.version += 1
    assert _is_due(bookmark) is True
    bookmark.tried_version = bookmark.version
    for _ in range(3):
        assert _is_due(bookmark) is False


def test_the_engine_consults_exactly_this_version_floor_predicate():
    source = (_h3_support.HOLO3_ROOT / "engine.py").read_text()
    assert "worker.tried_version == worker.version" in source, (
        "the engine no longer skips on an equal version floor: retarget "
        "the bookmark state-machine pin at whatever replaced it")
    assert "worker.tried_version = worker.version" in source
    assert source.count("worker.version += 1") == 2
    assert "worker.pending = True" in source
    assert "worker.inflight = True" in source


def _plane(plane: str) -> data.PlaneRaster:
    return data.PlaneRaster(capture_id="c", level_index=0, plane=plane,
                            path=Path(f"{plane}.npy"), shape_px=(4, 4))


def _store(planes: dict[str, data.PlaneRaster]) -> object:
    by_lane = {("c", 0): planes}
    return SimpleNamespace(lane_planes=by_lane.__getitem__)


def _sampling_planes(store: object, lane: tuple[str, int]) -> tuple:
    return store_module._Store.sampling_planes(store, lane)


def _rgb_planes(store: object, lane: tuple[str, int]) -> tuple:
    return store_module._Store.rgb_planes(store, lane)


def test_sampling_planes_returns_the_single_plane_of_a_grey_capture():
    grey = _plane("g")
    result = _sampling_planes(_store({"g": grey}), ("c", 0))
    assert result == (grey,)


def test_sampling_planes_prefers_the_luma_plane_of_a_k_on_rgb_capture():
    planes = {"r": _plane("r"), "g": _plane("g"), "b": _plane("b"),
              "y": _plane("y")}
    result = _sampling_planes(_store(planes), ("c", 0))
    assert result == (planes["y"],)


def test_sampling_planes_returns_rgb_when_no_luma_plane_exists():
    planes = {"r": _plane("r"), "g": _plane("g"), "b": _plane("b")}
    result = _sampling_planes(_store(planes), ("c", 0))
    assert result == (planes["r"], planes["g"], planes["b"])


def test_rgb_planes_is_always_r_then_g_then_b():
    planes = {"b": _plane("b"), "g": _plane("g"), "r": _plane("r"),
              "y": _plane("y")}
    result = _rgb_planes(_store(planes), ("c", 0))
    assert result == (planes["r"], planes["g"], planes["b"])


def test_every_cross_plugin_fact_in_data_is_a_frozen_dataclass():
    checks = _h3_support.Checks("data.py frozen surface")
    for name, klass in _data_dataclasses():
        if name in MUTABLE_BY_DESIGN:
            continue
        checks.check(f"data.{name} is frozen",
                     klass.__dataclass_params__.frozen,
                     "facts cross plugin boundaries and must be immutable")
    checks.assert_clean()


def test_certificate_is_pinned_hard_because_it_is_the_c6_subject():
    assert data.Certificate.__dataclass_params__.frozen
    _h3_support.assert_golden(
        "Certificate fields",
        tuple(f.name for f in dataclasses.fields(data.Certificate)),
        CERTIFICATE_FIELDS)


def test_certificate_identity_is_page_ty_tx_stream_and_nothing_else():
    import numpy as np

    bits = np.zeros(4, np.uint8)
    one = data.Certificate(page=0, ty=1, tx=2, stream_id="main",
                           user_bits=bits, source="tiles/scan")
    key = (one.page, one.ty, one.tx, one.stream_id)
    assert key == (0, 1, 2, "main")
    with pytest.raises(dataclasses.FrozenInstanceError):
        one.user_bits = bits


def test_integrity_error_is_a_plain_exception_holo3_raises_and_never_catches():
    assert issubclass(data.IntegrityError, Exception)
    assert not issubclass(data.IntegrityError, (ValueError, OSError))


def test_attempt_fact_carries_the_retry_arming_inputs():
    assert data.AttemptFact.__dataclass_params__.frozen
    _h3_support.assert_golden(
        "AttemptFact fields",
        tuple(f.name for f in dataclasses.fields(data.AttemptFact)),
        ATTEMPT_FACT_FIELDS)
    fact = data.AttemptFact(
        page=0, ty=0, tx=0, stream_id="main", stage="scan",
        outcome="attempted_failed", n_informative=4096, n_iters=60,
        syndrome_ok=False, crc_ok=None)
    assert fact.components == ()
    assert (fact.stage, fact.outcome) == ("scan", "attempted_failed")


def test_the_event_union_is_exactly_the_declared_types():
    members = tuple(member.__name__ for member in typing.get_args(data.Event))
    _h3_support.assert_golden("data.Event union", members,
                              EVENT_UNION_GOLDEN)


def test_every_event_type_is_a_frozen_dataclass():
    for member in typing.get_args(data.Event):
        assert member.__dataclass_params__.frozen, member.__name__


def test_job_result_and_run_result_are_the_only_job_and_run_returns():
    assert data.JobResult.__dataclass_params__.frozen
    assert data.RunResult.__dataclass_params__.frozen
    _h3_support.assert_golden(
        "JobResult fields",
        tuple(f.name for f in dataclasses.fields(data.JobResult)),
        JOB_RESULT_FIELDS)
    _h3_support.assert_golden(
        "RunResult fields",
        tuple(f.name for f in dataclasses.fields(data.RunResult)),
        RUN_RESULT_FIELDS)
    _h3_support.assert_golden(
        "PluginRow fields",
        tuple(f.name for f in dataclasses.fields(data.PluginRow)),
        PLUGIN_ROW_FIELDS)
    result = data.RunResult(status="open", payload=None,
                            payload_sha256=None, certified=0)
    assert result.plugin_rows == ()
    assert (typing.get_type_hints(engine.decode)["return"]
            is data.RunResult)


def test_level_ppc_and_scale_are_exact_rationals_not_floats():
    level = data.Level(index=0, ppc=Fraction(2), scale=Fraction(4),
                       shape_px=(8, 8), label="l00")
    assert isinstance(level.ppc, Fraction)
    assert isinstance(level.scale, Fraction)


def test_the_descriptor_is_the_declared_contract_and_nothing_else():
    assert descriptor_module.PluginDescriptor.__dataclass_params__.frozen
    _h3_support.assert_golden(
        "PluginDescriptor fields",
        tuple(f.name for f in dataclasses.fields(
            descriptor_module.PluginDescriptor)),
        PLUGIN_DESCRIPTOR_FIELDS)


def test_every_row_takes_the_two_accounting_parameters_as_data():
    import inspect

    checks = _h3_support.Checks("cost() signature")
    for descriptor in engine.DESCRIPTORS:
        parameters = tuple(
            inspect.signature(descriptor.cost).parameters)
        checks.equal(f"{descriptor.name}.cost parameters", parameters,
                     COST_PARAMETERS)
    checks.assert_clean()


def test_the_engine_reads_neither_accounting_parameter_it_passes():
    source = (_h3_support.HOLO3_ROOT / "engine.py").read_text()
    assert "worker.attempts," in source and "worker.last_cost)" in source
    for arithmetic in ("cost *", "cost +", "cost -", "max(cost",
                       "min(cost"):
        assert arithmetic not in source, (
            f"the engine does arithmetic on a price ({arithmetic}): cost is "
            f"a scheduling function of the plugins alone")


def test_no_prose_field_survives_on_any_descriptor_row():
    declared = {f.name for f in dataclasses.fields(
        descriptor_module.PluginDescriptor)}
    assert not {name for name in declared if name.endswith("_doc")}, (
        "D6.2 deleted the *_doc prose fields: the schedule table is "
        "computed truth now")


@pytest.mark.parametrize("name", PRICE_MECHANISM_GONE)
def test_the_price_scale_no_longer_lives_beside_the_contract(name):
    assert not hasattr(descriptor_module, name), (
        f"{name} is back in the contract module: prices belong to the "
        f"plugins alone (D6 addendum 10; engine aging deleted 2026-08-29)")


def test_the_contract_module_names_no_tier_at_all():
    source = (_h3_support.HOLO3_ROOT / "descriptor.py").read_text()
    assert "tier" not in source.lower()
