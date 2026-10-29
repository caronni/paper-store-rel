from __future__ import annotations

import ast
import dataclasses
import typing
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from holo.receiver import data, descriptor as descriptor_module, engine
from holo.receiver import store as store_module
from holo.receiver.tests import _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_a_fresh_worker_bookmark_starts_at_the_declared_defaults`,
# `test_each_record_is_frozen_as_declared_and_carries_its_field_set`,
# `test_fact_key_vocabulary_is_closed_at_nineteen_kinds`,
# `test_the_event_union_is_exactly_the_declared_types`.

HOLO3_ROOT = _h3_support.HOLO3_ROOT

# dpi_forced joined it 2026-10-02 with `--dpi-force` (the c2-at-4800
# harmonic): per scan, whether the survey takes the declared pitch.
DECODE_REQUEST_FIELDS = (
    "scans", "dpis", "format_ref", "max_pages", "workers", "complete",
    "no_close", "diag_port", "run_dir", "pooled_color_context",
    "resume", "snapshot_every_s", "refine_gate", "dpi_forced")

WORKER_BOOKMARK_FIELDS = (
    "plugin", "subject", "reads", "version", "tried_version", "attempts",
    "last_cost", "retired", "inflight", "pending", "seat_seq", "seat_cost")

WORKER_BOOKMARK_DEFAULTS = {
    "version": 0, "tried_version": -1,
    "attempts": 0, "last_cost": 0, "retired": False,
    "inflight": False, "pending": False, "seat_seq": -1, "seat_cost": 0}

COST_PARAMETERS = ("store", "subject", "stage", "attempts", "last_cost")

KEY_KINDS_GOLDEN = (
    # `place_settled` left the vocabulary 2026-09-21: the parent's
    # afterlife is routed by the store to the parent's OWN place_stage
    # key, so nothing subscribed to it any more.
    "pose_affine", "pose_route", "place_stage",
    "evidence_fit",
    "evidence_read", "color_row", "color_pop", "pooled_ctx",
    "region_pitch", "region_ctx",
    "lattice_seed", "lane_poses", "page_certs", "tile", "live_pages",
    # `attempt` joined the vocabulary 2026-09-21: a tile-stream's
    # VERDICT at one stage on one lane, which is what turns the residue
    # ladder from a birth-time fan-out into a subscription.
    "plane_field", "field_obs", "attempt",
    # `window_done` joined 2026-10-03: an unplaced window's done verdict
    # re-opened by a pose revision -- the done gate suppresses through
    # `place`'s stage now, and this is the key that lifts it.
    "window_done")

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
    "KEY_PLANE_FIELD": "plane_field",
    "KEY_FIELD_OBS": "field_obs",
    "KEY_ATTEMPT": "attempt",
    "KEY_WINDOW_DONE": "window_done"}

CERTIFICATE_FIELDS = (
    "page", "ty", "tx", "stream_id", "user_bits", "source")

ATTEMPT_FACT_FIELDS = (
    "page", "ty", "tx", "stream_id", "stage", "outcome", "n_informative",
    # `generation` joined 2026-09-21: the tile-lane counter the decode
    # read, reported back by the job so a rung can tell a live verdict
    # from one taken off evidence that has since moved.
    "n_iters", "syndrome_ok", "crc_ok", "components", "generation")

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
    # SurveyPitchFallback joined it 2026-09-04 with the D5 port: a
    # survey that votes no pitch warns and works at the declared one.
    "SurveyPitchFallback",
    "PoseCommitted", "WindowSettled",
    # WorkerSeated/WorkerRetired replaced WindowScheduled/WindowRetired
    # 2026-09-21: every row is seated and retired through one pair of
    # generic events, and the window views filter on plugin == "place".
    "WorkerSeated", "WorkerRetired", "EngineStat",
    # Contradiction joined it 2026-09-04 with the address-word alarm
    # (ruling D1): the place fold is its producer and it is diagnostic
    # only — nothing consumes it, and no quarantine came with it.
    "WordOutcome", "AddressCoverage", "Contradiction", "CalibrateAdopted",
    "TileOutcome",
    # FieldSolved joins the union with the FIELD band's producer: the
    # `fields` row emits one bounded event per PAGE SOLVE, carrying every
    # plane's field and the per-capture residual energies against it.
    "JobDone", "CloseCheck", "RunDone", "FieldSolved")

MUTABLE_BY_DESIGN = ("WorkerBookmark", "WindowState", "StatBoard")

PLUGIN_DESCRIPTOR_FIELDS = (
    # No read-set field: a worker's reads are FIXED AT BIRTH and grown
    # only by a re-birth (`engine._births`).  `rederive_on` was here for
    # one day, 2026-09-21, and the amendment took it out again.
    "name", "subject_kind", "born_by", "subjects_of", "reads", "eligible",
    "stage", "cost", "retire", "prepare", "produces", "prices")

def _data_dataclasses() -> tuple[tuple[str, type], ...]:
    found = []
    for name in sorted(dir(data)):
        member = getattr(data, name)
        if isinstance(member, type) and dataclasses.is_dataclass(member):
            found.append((name, member))
    return tuple(found)


#: (record, frozen, declared fields).  Certificate is pinned hard
#: because it is the C6 subject; WorkerBookmark is the one mutable
#: scheduling record; PluginDescriptor is the declared contract and
#: nothing else.  A move in any row is a contract change.
RECORD_GOLDENS = (
    (data.DecodeRequest, True, DECODE_REQUEST_FIELDS),
    (descriptor_module.WorkerBookmark, False, WORKER_BOOKMARK_FIELDS),
    (data.Certificate, True, CERTIFICATE_FIELDS),
    (data.AttemptFact, True, ATTEMPT_FACT_FIELDS),
    (data.JobResult, True, JOB_RESULT_FIELDS),
    (data.RunResult, True, RUN_RESULT_FIELDS),
    (data.PluginRow, True, PLUGIN_ROW_FIELDS),
    (descriptor_module.PluginDescriptor, True, PLUGIN_DESCRIPTOR_FIELDS),
)


@pytest.mark.parametrize("record,frozen,fields", RECORD_GOLDENS,
                         ids=[row[0].__name__ for row in RECORD_GOLDENS])
def test_each_record_is_frozen_as_declared_and_carries_its_field_set(
        record, frozen, fields):
    assert record.__dataclass_params__.frozen is frozen
    _h3_support.assert_measured(
        f"{record.__name__} fields",
        tuple(f.name for f in dataclasses.fields(record)), fields)


def test_decode_request_is_the_same_object_the_engine_exports():
    assert engine.DecodeRequest is data.DecodeRequest


def test_fact_key_vocabulary_is_closed_at_nineteen_kinds():
    _h3_support.assert_measured("KEY_KINDS", descriptor_module.KEY_KINDS,
                               KEY_KINDS_GOLDEN)
    assert len(set(descriptor_module.KEY_KINDS)) == 19


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


def test_a_fresh_worker_bookmark_starts_at_the_declared_defaults():
    bookmark = descriptor_module.WorkerBookmark(
        plugin="probe", subject="s", reads=())
    for name, expected in sorted(WORKER_BOOKMARK_DEFAULTS.items()):
        _h3_support.assert_measured(f"WorkerBookmark.{name} default",
                                   getattr(bookmark, name), expected)


def test_the_engine_consults_exactly_this_version_floor_predicate():
    source = (_h3_support.HOLO3_ROOT / "engine.py").read_text()
    assert "worker.tried_version == worker.version" in source, (
        "the engine no longer skips on an equal version floor: retarget "
        "the bookmark state-machine pin at whatever replaced it")
    assert "worker.tried_version = worker.version" in source
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


#: (reader, the lane's planes, the planes the reader returns in order).
LANE_PLANES = (
    ("grey", _sampling_planes, ("g",), ("g",)),
    ("k-on-rgb", _sampling_planes, ("r", "g", "b", "y"), ("y",)),
    ("rgb", _sampling_planes, ("r", "g", "b"), ("r", "g", "b")),
    ("rgb-order", _rgb_planes, ("b", "g", "r", "y"), ("r", "g", "b")),
)


@pytest.mark.parametrize("reader,planes,expected",
                         [row[1:] for row in LANE_PLANES],
                         ids=[row[0] for row in LANE_PLANES])
def test_the_reader_returns_the_declared_planes_in_the_declared_order(
        reader, planes, expected):
    built = {name: _plane(name) for name in planes}
    assert reader(_store(built), ("c", 0)) == tuple(
        built[name] for name in expected)


def test_every_cross_plugin_fact_in_data_is_a_frozen_dataclass():
    checks = _h3_support.Checks("data.py frozen surface")
    for name, klass in _data_dataclasses():
        if name in MUTABLE_BY_DESIGN:
            continue
        checks.check(f"data.{name} is frozen",
                     klass.__dataclass_params__.frozen,
                     "facts cross plugin boundaries and must be immutable")
    checks.assert_clean()


def test_integrity_error_is_a_plain_exception_holo3_raises_and_never_catches():
    assert issubclass(data.IntegrityError, Exception)
    assert not issubclass(data.IntegrityError, (ValueError, OSError))


def test_attempt_fact_carries_the_retry_arming_inputs():
    fact = data.AttemptFact(
        page=0, ty=0, tx=0, stream_id="main", stage="scan",
        outcome="attempted_failed", n_informative=4096, n_iters=60,
        syndrome_ok=False, crc_ok=None)
    assert fact.components == () and fact.generation == 0
    assert (fact.stage, fact.outcome) == ("scan", "attempted_failed")


def test_the_event_union_is_exactly_the_declared_types():
    members = tuple(member.__name__ for member in typing.get_args(data.Event))
    _h3_support.assert_measured("data.Event union", members,
                               EVENT_UNION_GOLDEN)


def test_job_result_and_run_result_are_the_only_job_and_run_returns():
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


def test_the_contract_module_names_no_tier_at_all():
    source = (_h3_support.HOLO3_ROOT / "descriptor.py").read_text()
    assert "tier" not in source.lower()
