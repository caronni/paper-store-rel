from __future__ import annotations

import collections
import dataclasses
import hashlib
import tempfile
from concurrent.futures import Future
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from holo.receiver import data, engine
from holo.receiver import operator as operator_doors
from holo.receiver import store as store_module
from holo.receiver.descriptor import (
    KEY_EVIDENCE_FIT,
    KEY_TILE,
    PluginDescriptor,
)
from holo.receiver.format import identity
from holo.receiver.plugins import refine
from holo.receiver.tests import _h3_facts, _h3_support

# PIN LEDGER -- the measured (`assert_measured`) pins of this module.
# 2026-10-03 S10: reclassified from assert_golden -- receiver-axis
# vocabulary, not printed format; values unchanged.  Pins in:
# `test_a_gate_that_stops_work_emits_no_job_at_all`,
# `test_complete_defers_every_mid_run_close_to_the_exhaustion_consult`,
# `test_default_mode_consults_the_close_on_every_certificate`,
# `test_each_scheduling_gate_stops_work_where_it_declares_it_does`,
# `test_every_descriptor_declares_its_produced_fact_types`,
# `test_no_close_observes_the_counts_and_never_solves`,
# `test_refine_fires_exactly_once_per_growth_of_its_certified_reach`,
# `test_the_engine_exports_only_its_declared_public_surface`,
# `test_the_frontier_pops_the_cheapest_ready_job_first`,
# `test_the_real_descriptor_set_passes_the_single_writer_check`.
# 2026-10-12 (CMY-RECEIVER-PLAN A6): `tiles.cond`, the conditioned label
# stream, joins the tiles. writers of AttemptFact and Certificate
# (`SHARED_FACT_TYPES`); the produced fact types are unmoved.

SCHEDULE_MD = _h3_support.HOLO3_ROOT / "docs" / "SCHEDULE.md"

FORMAT_REF = "L:c2-r0700@3392x2368"
ROW = identity.resolve_format_ref(FORMAT_REF)
STREAM_ID = ROW.streams[0].stream_id
USER_BITS = ROW.streams[0].user_bits

PAYLOAD = b"holo3-engine-contract-payload"
TILES: tuple[tuple[int, int], ...] = ((0, 0), (0, 1), (1, 0), (1, 1))
N_NEEDED = len(TILES)
CAPTURE_ID = "deadbeef" * 8
N_LEVELS = 2

DESCRIPTOR_HOOKS = (
    "subjects_of", "reads", "eligible", "stage", "cost", "retire",
    "prepare")

RUN_DIR_PRODUCTS = ("argv", "events.jsonl", "pane-page-0.png",
                    "pane-payload-0.png", "pane-pose-0.png", "report.json",
                    "tree")

PRODUCED_FACT_TYPES = (
    "AttemptFact", "CaptureSurvey", "Certificate", "ColorCtxPopulation",
    "ColorEvidenceRow", "ColorLaneFit", "CtxOutcome", "FieldObservations",
    "LatticeSeed", "PlaceOutcome", "Placement", "PlaneField",
    "PooledColorCtx", "RefineOutcome", "WindowEvidence")

SHARED_FACT_TYPES = {
    "AttemptFact": ("tiles.cond", "tiles.local", "tiles.planek",
                    "tiles.retry", "tiles.scan", "tiles.swim",
                    "tiles.union", "tiles.uplift"),
    "Certificate": ("tiles.cond", "tiles.local", "tiles.planek",
                    "tiles.retry", "tiles.scan", "tiles.swim",
                    "tiles.union", "tiles.uplift"),
    "RefineOutcome": ("refine", "refine.color"),
}

# Every descriptor declares what it writes.  `revisit` was the one row
# that declared four fact types it did not OWN -- it re-fired other
# rows' work as a subscription -- and it was dissolved 2026-09-21, so
# `Placement`, `LatticeSeed`, `PlaceOutcome` and `WindowEvidence` each
# have exactly one writer again.
SILENT_PRODUCERS: tuple[str, ...] = ()

SERIAL_JOBS_DEFAULT = {"survey": 1, "place": 1, "calibrate": 1,
                       "tiles.scan": 4}
SERIAL_COSTS_DEFAULT = (10, 60, 15, 20, 20, 20, 20)

CLOSE_STATUS_DEFAULT = ("open", "open", "open", "verified")
CLOSE_STATUS_COMPLETE = ("deferred", "deferred", "deferred", "deferred",
                         "verified")
CLOSE_STATUS_NO_CLOSE = ("open", "open", "open", "count_ready",
                         "count_ready")


def _levels() -> tuple[data.Level, ...]:
    return tuple(
        data.Level(index=index, ppc=Fraction(4 * (index + 1)),
                   scale=Fraction(1), shape_px=(64, 64), label=f"l{index}")
        for index in range(N_LEVELS))


def _capture(run_dir: Path) -> data.Capture:
    return data.Capture(
        capture_id=CAPTURE_ID, path=run_dir / "scan.tiff", dpi=1200.0,
        shape_px=(64, 64), channels=1, platen_backing=0.9, levels=_levels(),
        plane_dir=run_dir)


def _stub_intake(request: object, row: object) -> tuple:
    capture = _capture(request.run_dir)
    event = data.CaptureOpen(capture=capture.capture_id, dpi=capture.dpi,
                             shape_yx=capture.shape_px, channels=1,
                             duplicate=False)
    return (capture,), (), (event,)


def _stub_survey(store: object, subject: object, stage: str) -> object:
    region = data.Region(
        capture_id=str(subject), region_index=0, origin_yx=(0, 0),
        step_px=8, cells=np.ones((4, 4), bool), extent_px=(64, 64),
        area_mm2=10.0, median_tensor_score=1.0)
    survey = data.CaptureSurvey(capture_id=str(subject), regions=(region,),
                                pitch_class=Fraction(1, 300), pitch_px=4.0)
    event = data.SurveyDone(capture=str(subject), n_regions=1, regions=(),
                            pitch_class="c2", preview=None, preview_decim=1)
    return lambda: data.JobResult((survey,), (event,), 0.001)


def _stub_place(store: object, subject: object, stage: str) -> object:
    wid = subject
    cells = np.array([[ty * 64, tx * 64] for ty, tx in TILES], np.int64)
    placement = data.Placement(
        window_id=wid, capture_id=wid[0], level_index=wid[1],
        region_index=wid[2], patch_ordinal=0, page=0, rot_k=0,
        page_origin_yx=(0, 0),
        native_affine=(8.0, 0.0, 0.0, 0.0, 8.0, 0.0), pitch_px=8.0,
        route="word", local_cells_yx=cells)
    event = data.PoseCommitted(
        capture=wid[0], level_index=wid[1], region_index=wid[2],
        extent_cells=wid[3], page=0, route="word", mismatch=0.01,
        accepted=True)
    return lambda: data.JobResult((placement,), (event,), 0.002)


def _evidence_wid(ty: int, tx: int) -> tuple:
    return (CAPTURE_ID, 0, 0, (ty * 64, tx * 64, ty * 64 + 64,
                               tx * 64 + 64))


def _tile_evidence_fact(ty: int, tx: int) -> data.WindowEvidence:
    cells = np.stack(np.meshgrid(np.arange(ty * 64, ty * 64 + 64),
                                 np.arange(tx * 64, tx * 64 + 64),
                                 indexing="ij"),
                     axis=-1).reshape(-1, 2).astype(np.int64)
    n = cells.shape[0]
    return data.WindowEvidence(
        window_id=_evidence_wid(ty, tx), capture_id=CAPTURE_ID,
        level_index=0, region_index=0, patch_ordinal=ty * 2 + tx, page=0,
        page_cells_yx=cells, scores=np.zeros(n, np.float32),
        reference_values=np.zeros(n, np.int8),
        knots=np.zeros(2, np.float32), probs=np.zeros(2, np.float32),
        n_search=0, marginal_llr=np.zeros(n, np.float32),
        printed_llr=np.zeros(n, np.float32), accepted=True,
        refusal_reason="", heldout_logloss=0.1, ctx_adopted=False)


def _stub_calibrate(store: object, subject: object, stage: str) -> object:
    facts = tuple(_tile_evidence_fact(ty, tx) for ty, tx in TILES)
    return lambda: data.JobResult(facts, (), 0.003)


def _true_bits(ty: int, tx: int) -> np.ndarray:
    digest = hashlib.sha256(f"{ty}/{tx}".encode()).digest()
    rng = np.random.default_rng(int.from_bytes(digest[:8], "big"))
    bits = rng.integers(0, 2, size=USER_BITS, dtype=np.uint8)
    bits[0] = np.uint8((ty + tx) & 1)
    return bits


def _stub_scan(store: object, subject: object, stage: str) -> object:
    page, ty, tx, _capture_id, _level_index = subject
    if (page, ty, tx, STREAM_ID) in store._certificates:
        return None
    certificate = data.Certificate(
        page=page, ty=ty, tx=tx, stream_id=STREAM_ID,
        user_bits=_true_bits(ty, tx), source="tiles/scan")
    attempt = data.AttemptFact(
        page=page, ty=ty, tx=tx, stream_id=STREAM_ID, stage="scan",
        outcome="certified", n_informative=4096, n_iters=3,
        syndrome_ok=True, crc_ok=True)
    event = data.TileOutcome(
        page=page, ty=ty, tx=tx, stream_id=STREAM_ID, source="tiles/scan",
        result="certified", bp_iters=3)
    return lambda: data.JobResult((certificate, attempt), (event,), 0.004)


def _stub_idle(store: object, subject: object, stage: str) -> object:
    return None


STUB_PREPARES = {
    "survey": _stub_survey,
    "place": _stub_place,
    "calibrate": _stub_calibrate,
    "tiles.scan": _stub_scan,
}


class _StubCloseProgress:

    def __init__(self, row: object) -> None:
        self.row = row
        self.seen: set = set()
        self.last_attempt: int | None = None

    def absorb(self, certificates: dict) -> None:
        self.seen |= set(certificates)

    def count_progress(self) -> tuple:
        blocks = (data.CloseBlockRow(
            stream_id=None, block=0, have=len(self.seen), needed=N_NEEDED,
            rank=None, solved=False,
            short=max(0, N_NEEDED - len(self.seen)), groups_open=1,
            n_groups=1),)
        return len(self.seen) >= N_NEEDED, N_NEEDED, blocks

    @property
    def metadata_rank(self) -> int:
        return len(self.seen)

    @property
    def metadata_n_unique(self) -> int:
        return len(self.seen)

    def close_is_new(self) -> bool:
        return (self.last_attempt is None
                or len(self.seen) > self.last_attempt)

    def close(self) -> object:
        self.last_attempt = len(self.seen)
        if len(self.seen) >= N_NEEDED:
            return SimpleNamespace(
                status="verified", payload=PAYLOAD, k_total=1, blocks=(),
                symbols_used=len(self.seen), reason=None,
                metadata_version=0)
        return SimpleNamespace(
            status="open", payload=None, k_total=None, blocks=(),
            symbols_used=0, reason="short", metadata_version=None)


def _install(monkeypatch: pytest.MonkeyPatch,
             scan_prepare: object | None = None,
             extra: tuple[PluginDescriptor, ...] = ()) -> None:
    monkeypatch.setattr(engine, "_intake_run", _stub_intake)
    stubbed = []
    for descriptor in engine.DESCRIPTORS:
        prepare = STUB_PREPARES.get(descriptor.name, _stub_idle)
        if descriptor.name == "tiles.scan" and scan_prepare is not None:
            prepare = scan_prepare
        stubbed.append(dataclasses.replace(descriptor, prepare=prepare))
    descriptors = tuple(stubbed) + extra
    monkeypatch.setattr(engine, "DESCRIPTORS", descriptors)
    monkeypatch.setattr(
        engine, "DESCRIPTOR_BY_NAME",
        {descriptor.name: descriptor for descriptor in descriptors})
    monkeypatch.setattr(engine, "format_close", SimpleNamespace(
        CloseProgress=_StubCloseProgress))


@dataclasses.dataclass(frozen=True)
class StubRun:
    result: data.RunResult
    events: tuple
    run_dir: Path

    @property
    def jobs(self) -> tuple[data.JobDone, ...]:
        return tuple(event for event in self.events
                     if isinstance(event, data.JobDone))

    @property
    def job_counts(self) -> dict[str, int]:
        return dict(collections.Counter(job.plugin for job in self.jobs))

    @property
    def close_checks(self) -> tuple[data.CloseCheck, ...]:
        return tuple(event for event in self.events
                     if isinstance(event, data.CloseCheck))


def _run(**kwargs: object) -> StubRun:
    run_dir = Path(tempfile.mkdtemp(prefix="h3-contract-"))
    request = engine.DecodeRequest(
        scans=(run_dir / "scan.tiff",), dpis=(1200.0,),
        format_ref=FORMAT_REF,
        max_pages=1, workers=int(kwargs.get("workers", 1)),
        complete=bool(kwargs.get("complete", False)),
        no_close=bool(kwargs.get("no_close", False)), diag_port=None,
        run_dir=run_dir,
        snapshot_every_s=kwargs.get("snapshot_every_s", 1800.0),
        resume=kwargs.get("resume"))
    events: list = []
    result = engine.decode(request, events)
    return StubRun(result=result, events=tuple(events), run_dir=run_dir)


@pytest.fixture(scope="module")
def stub_runs() -> dict[str, StubRun]:
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch)
        yield {
            "default": _run(),
            "workers8": _run(workers=8),
            "complete": _run(complete=True),
            "no_close": _run(no_close=True),
        }


def _schedule_md_names() -> tuple[str, ...]:
    rows: list[str] = []
    inside = False
    for line in SCHEDULE_MD.read_text().splitlines():
        if line.startswith("descriptor rows"):
            inside = True
            continue
        if not inside:
            continue
        if not line.strip():
            break
        first = line.split()[0]
        if first == "name" or set(first) == {"-"}:
            continue
        rows.append(first)
    return tuple(rows)


def test_the_attempts_histogram_counts_each_worker_exactly_once():
    bare = _bare_engine()
    for n_attempts in range(1, 13):
        bare._note_attempt(n_attempts)
    assert bare._attempts_hist == {"1": 0, "2": 0, "3-5": 0, "6-10": 0,
                                   ">10": 1}
    other = _bare_engine()
    for worker_attempts in (1, 1, 2, 4, 9):
        for n_attempts in range(1, worker_attempts + 1):
            other._note_attempt(n_attempts)
    live = {label: count for label, count in other._attempts_hist.items()
            if count}
    assert live == {"1": 2, "2": 1, "3-5": 1, "6-10": 1}


def test_descriptor_names_are_unique_and_indexed_by_name():
    names = tuple(descriptor.name for descriptor in engine.DESCRIPTORS)
    assert len(set(names)) == len(names)
    assert set(engine.DESCRIPTOR_BY_NAME) == set(names)
    for name, descriptor in engine.DESCRIPTOR_BY_NAME.items():
        assert descriptor.name == name


def test_the_descriptor_table_is_exactly_the_rows_schedule_md_declares():
    names = {descriptor.name for descriptor in engine.DESCRIPTORS}
    assert set(_schedule_md_names()) == names, (
        "src/holo/receiver/docs/SCHEDULE.md and engine.DESCRIPTORS disagree — that is a "
        "doc-or-code drift finding, never an auto-fix")


def test_every_descriptor_declares_a_callable_for_every_scheduling_hook():
    checks = _h3_support.Checks("descriptor totality")
    for descriptor in engine.DESCRIPTORS:
        for hook in DESCRIPTOR_HOOKS:
            checks.check(f"{descriptor.name}.{hook} is callable",
                         callable(getattr(descriptor, hook)))
        checks.check(f"{descriptor.name}.born_by is a tuple of types",
                     isinstance(descriptor.born_by, tuple)
                     and all(isinstance(kind, type)
                             for kind in descriptor.born_by)
                     and bool(descriptor.born_by))
        checks.check(f"{descriptor.name}.produces is a tuple of types",
                     isinstance(descriptor.produces, tuple)
                     and all(isinstance(kind, type)
                             for kind in descriptor.produces))
        checks.check(f"{descriptor.name} declares a subject kind",
                     bool(descriptor.subject_kind))
    checks.assert_clean()


def _producers() -> dict[str, tuple[str, ...]]:
    found: dict[str, set[str]] = {}
    for descriptor in engine.DESCRIPTORS:
        for produced in descriptor.produces:
            found.setdefault(produced.__name__, set()).add(descriptor.name)
    return {name: tuple(sorted(writers))
            for name, writers in sorted(found.items())}


def test_the_real_descriptor_set_passes_the_single_writer_check():
    engine.check_single_writer(engine.DESCRIPTORS)
    producers = _producers()
    _h3_support.assert_measured("produced fact types", tuple(producers),
                               PRODUCED_FACT_TYPES)
    shared = {name: writers for name, writers in producers.items()
              if len(writers) > 1}
    assert set(shared) == set(SHARED_FACT_TYPES)
    for name, writers in sorted(shared.items()):
        assert writers == SHARED_FACT_TYPES[name], name
        assert len({writer.split(".")[0] for writer in writers}) == 1, name


def test_every_descriptor_declares_its_produced_fact_types():
    silent = tuple(descriptor.name for descriptor in engine.DESCRIPTORS
                   if not descriptor.produces)
    _h3_support.assert_measured(
        "descriptors declaring produces=()", silent, SILENT_PRODUCERS)
    assert all(len({name.split(".")[0] for name in writers}) == 1
               for writers in SHARED_FACT_TYPES.values()), (
        "a shared fact type is shared inside ONE domain now: no row is "
        "exempt from the single-writer check")


def test_two_domains_writing_one_fact_type_is_refused_at_startup():
    rogue = dataclasses.replace(
        engine.DESCRIPTOR_BY_NAME["refine"], name="rogue",
        produces=(data.Placement,))
    with pytest.raises(data.IntegrityError, match="multiple writer domains"):
        engine.check_single_writer(engine.DESCRIPTORS + (rogue,))


def test_same_prefix_rows_may_share_a_produced_fact_type():
    twin = dataclasses.replace(
        engine.DESCRIPTOR_BY_NAME["tiles.scan"], name="tiles.twin")
    engine.check_single_writer(engine.DESCRIPTORS + (twin,))
    assert data.AttemptFact in twin.produces
    stranger = dataclasses.replace(twin, name="stranger.twin")
    with pytest.raises(data.IntegrityError, match="AttemptFact"):
        engine.check_single_writer(engine.DESCRIPTORS + (stranger,))


def test_certificate_has_no_carve_out_the_prefix_rule_already_admits_it():
    writers = {descriptor.name for descriptor in engine.DESCRIPTORS
               if data.Certificate in descriptor.produces}
    assert len(writers) > 1
    assert {name.split(".")[0] for name in writers} == {"tiles"}
    source = (_h3_support.HOLO3_ROOT / "engine.py").read_text()
    body = source.split("def check_single_writer")[1].split("\ndef ")[0]
    assert "Certificate" not in body, (
        "the single-writer check names a fact type again: Certificate "
        "passes on the shared tiles. prefix alone")
    stranger = dataclasses.replace(
        engine.DESCRIPTOR_BY_NAME["tiles.scan"], name="stranger.certifier",
        produces=(data.Certificate,))
    with pytest.raises(data.IntegrityError, match="Certificate"):
        engine.check_single_writer(engine.DESCRIPTORS + (stranger,))


def test_the_stubbed_run_verifies_and_publishes_the_exact_payload(stub_runs):
    run = stub_runs["default"]
    assert run.result.status == "verified"
    assert run.result.payload == PAYLOAD
    assert run.result.payload_sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert run.result.certified == N_NEEDED


def test_the_engine_emits_one_run_done_and_it_agrees_with_the_result(
        stub_runs):
    run = stub_runs["default"]
    run_done = [event for event in run.events
                if isinstance(event, data.RunDone)]
    assert len(run_done) == 1
    assert run_done[0].status == run.result.status
    assert run_done[0].certified == run.result.certified
    assert run_done[0].n_bytes == len(PAYLOAD)


def test_births_come_from_the_born_by_fact_types_alone(stub_runs):
    counts = stub_runs["complete"].job_counts
    assert counts["survey"] == 1
    assert counts["place"] == 1
    assert counts["calibrate"] == 1
    assert counts["tiles.scan"] == N_NEEDED


def test_done_coverage_retires_the_second_window_before_it_fires(stub_runs):
    assert N_LEVELS == 2
    assert stub_runs["complete"].job_counts["place"] < N_LEVELS


def test_the_serial_run_is_bit_for_bit_repeatable(stub_runs):
    def signature(run: StubRun) -> tuple:
        return tuple((job.plugin, job.subject, job.cost) for job in run.jobs)

    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch)
        repeats = {signature(_run()) for _ in range(2)}
    repeats.add(signature(stub_runs["default"]))
    assert len(repeats) == 1


def test_the_frontier_pops_the_cheapest_ready_job_first(stub_runs):
    costs = tuple(job.cost for job in stub_runs["default"].jobs)
    _h3_support.assert_measured("serial default job costs", costs,
                               SERIAL_COSTS_DEFAULT)
    assert costs[0] == min(costs)


def test_a_dear_worker_waits_behind_every_cheaper_one_it_was_pushed_before():
    fired: list[str] = []
    subjects = ("dear", "cheap-b", "cheap-a")
    stages = {"dear": "refine", "cheap-b": "payload", "cheap-a": "payload"}

    def prepare(store: object, subject: object, stage: str) -> object:
        fired.append(str(subject))
        return lambda: data.JobResult((), (), 0.0)

    probe = _probe_descriptor(subjects, lambda store, subject: (),
                              lambda store, subject: stages[subject],
                              prepare)
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch, extra=(probe,))
        run = _run(complete=True)
    assert fired == ["cheap-b", "cheap-a", "dear"]
    dear_cost = next(job.cost for job in run.jobs if job.subject == "dear")
    assert dear_cost == max(job.cost for job in run.jobs)


PROBE_PRICES: dict[str, int] = {"payload": 20, "refine": 200}


def _probe_descriptor(subjects: tuple[str, ...], reads: object,
                      stage: object, prepare: object) -> PluginDescriptor:
    return PluginDescriptor(
        name="probe", subject_kind="probe", born_by=(data.Capture,),
        subjects_of=lambda store, fact: subjects, reads=reads,
        eligible=lambda store, subject: True, stage=stage,
        cost=lambda store, subject, name, attempts, last_cost: (
            PROBE_PRICES[name]),
        retire=lambda store, subject: None, prepare=prepare, produces=(),
        prices=tuple(sorted(PROBE_PRICES.items())))


PROBE_EVIDENCE = "evidence-probe"
PROBE_TILE = "tile-probe"
PROBE_SUBJECTS = (PROBE_EVIDENCE, PROBE_TILE)

FLOORLESS_FIRES = 1 + N_NEEDED
PROBE_FIRES_WITH_FLOOR = 2


def _probe_reads(store: object, subject: object) -> tuple:
    if subject == PROBE_EVIDENCE:
        return tuple((KEY_EVIDENCE_FIT, _evidence_wid(ty, tx))
                     for ty, tx in TILES)
    return tuple((KEY_TILE, 0, ty, tx, STREAM_ID) for ty, tx in TILES)


@pytest.fixture(scope="module")
def probe_fires() -> collections.Counter:
    fired: list[str] = []

    def prepare(store: object, subject: object, stage: str) -> object:
        fired.append(str(subject))
        return lambda: data.JobResult((), (), 0.0)

    probe = _probe_descriptor(
        PROBE_SUBJECTS, _probe_reads,
        lambda store, subject: "payload", prepare)
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch, extra=(probe,))
        _run(complete=True)
    return collections.Counter(fired)


@pytest.mark.parametrize("subject", PROBE_SUBJECTS)
def test_a_subscribed_worker_is_woken_by_facts_it_never_produced(
        probe_fires, subject):
    assert probe_fires[subject] > 1, (
        "the worker fired only at birth: the inverted subscription index "
        "delivered no wake at all")


@pytest.mark.parametrize("subject", PROBE_SUBJECTS)
def test_the_version_floor_collapses_repeated_wakes_into_one_refire(
        probe_fires, subject):
    assert probe_fires[subject] == PROBE_FIRES_WITH_FLOOR
    assert probe_fires[subject] < FLOORLESS_FIRES, (
        f"a floorless scheduler fires {FLOORLESS_FIRES} times here — once "
        f"at birth and once per touch")


GATE_DEAF = "probe.deaf"
GATE_RETIRED = "probe.retired"
GATE_INELIGIBLE = "probe.ineligible"
GATE_NO_STAGE = "probe.no-stage"
GATE_NO_JOB = "probe.no-job"

GATE_PREPARES_EXPECTED = {
    GATE_DEAF: 1, GATE_RETIRED: 0, GATE_INELIGIBLE: 0, GATE_NO_STAGE: 0,
    GATE_NO_JOB: PROBE_FIRES_WITH_FLOOR * len(PROBE_SUBJECTS)}

GATE_JOBS_EXPECTED = {
    GATE_DEAF: 1, GATE_RETIRED: 0, GATE_INELIGIBLE: 0, GATE_NO_STAGE: 0,
    GATE_NO_JOB: 0}


@pytest.fixture(scope="module")
def gate_run() -> tuple[collections.Counter, collections.Counter]:
    prepared: list[str] = []

    def counting(name: str) -> object:
        def prepare(store: object, subject: object, stage: str) -> object:
            prepared.append(name)
            return lambda: data.JobResult((), (), 0.0)

        return prepare

    def refusing(name: str) -> object:
        def prepare(store: object, subject: object, stage: str) -> object:
            prepared.append(name)
            return None

        return prepare

    def payload_stage(store: object, subject: object) -> str:
        return "payload"

    probes = (
        dataclasses.replace(
            _probe_descriptor(("deaf",), lambda store, subject: (),
                              payload_stage, counting(GATE_DEAF)),
            name=GATE_DEAF),
        dataclasses.replace(
            _probe_descriptor(PROBE_SUBJECTS, _probe_reads, payload_stage,
                              counting(GATE_RETIRED)),
            name=GATE_RETIRED, retire=lambda store, subject: "probed"),
        dataclasses.replace(
            _probe_descriptor(PROBE_SUBJECTS, _probe_reads, payload_stage,
                              counting(GATE_INELIGIBLE)),
            name=GATE_INELIGIBLE, eligible=lambda store, subject: False),
        dataclasses.replace(
            _probe_descriptor(PROBE_SUBJECTS, _probe_reads,
                              lambda store, subject: None,
                              counting(GATE_NO_STAGE)),
            name=GATE_NO_STAGE),
        dataclasses.replace(
            _probe_descriptor(PROBE_SUBJECTS, _probe_reads, payload_stage,
                              refusing(GATE_NO_JOB)),
            name=GATE_NO_JOB),
    )
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch, extra=probes)
        run = _run(complete=True)
    return (collections.Counter(prepared),
            collections.Counter(job.plugin for job in run.jobs))


@pytest.mark.parametrize("name", sorted(GATE_PREPARES_EXPECTED))
def test_each_scheduling_gate_stops_work_where_it_declares_it_does(
        gate_run, name):
    prepared, _jobs = gate_run
    _h3_support.assert_measured(f"{name} prepare calls", prepared[name],
                               GATE_PREPARES_EXPECTED[name])


@pytest.mark.parametrize("name", sorted(GATE_JOBS_EXPECTED))
def test_a_gate_that_stops_work_emits_no_job_at_all(gate_run, name):
    _prepared, jobs = gate_run
    _h3_support.assert_measured(f"{name} jobs", jobs[name],
                               GATE_JOBS_EXPECTED[name])


def test_an_unsubscribed_worker_fires_once_at_birth_and_is_never_woken(
        gate_run):
    prepared, jobs = gate_run
    assert prepared[GATE_DEAF] == 1 and jobs[GATE_DEAF] == 1


def test_a_prepare_that_declines_does_not_age_the_price_it_declined_at(
        gate_run):
    prepared, _jobs = gate_run
    assert (prepared[GATE_NO_JOB]
            == PROBE_FIRES_WITH_FLOOR * len(PROBE_SUBJECTS)), (
        "a declined prepare must stay a costless skip, never an attempt")


def test_the_merge_tallies_certificates_poses_and_words_per_plugin(
        stub_runs):
    rows = {row.plugin: row for row in stub_runs["default"].result.plugin_rows}
    assert set(rows) == set(SERIAL_JOBS_DEFAULT)
    assert rows["tiles.scan"].certificates == N_NEEDED
    assert rows["tiles.scan"].jobs == N_NEEDED
    assert rows["place"].poses == 1 and rows["place"].words == 1
    assert rows["survey"].certificates == 0
    assert all(row.cpu_seconds > 0.0 for row in rows.values())


def test_conflicting_certificates_at_one_address_refuse_the_whole_run():
    def conflicting(store: object, subject: object, stage: str) -> object:
        inner = _stub_scan(store, subject, stage)
        if inner is None:
            return None
        page, ty, tx, _capture_id, _level_index = subject
        flipped = _true_bits(ty, tx).copy()
        flipped[5] ^= 1
        rogue = data.Certificate(
            page=page, ty=ty, tx=tx, stream_id=STREAM_ID, user_bits=flipped,
            source="tiles/union")

        def job() -> data.JobResult:
            base = inner()
            return data.JobResult(base.facts + (rogue,), base.events,
                                  base.cpu_s)

        return job

    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch, scan_prepare=conflicting)
        with pytest.raises(data.IntegrityError,
                           match=r"conflicting certificates at "
                                 r"\(0, 0, 0, 'main'\)"):
            _run()


def test_an_identical_duplicate_certificate_is_a_no_op():
    def duplicating(store: object, subject: object, stage: str) -> object:
        inner = _stub_scan(store, subject, stage)
        if inner is None:
            return None

        def job() -> data.JobResult:
            base = inner()
            return data.JobResult(base.facts + base.facts, base.events,
                                  base.cpu_s)

        return job

    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch, scan_prepare=duplicating)
        run = _run()
    assert run.result.status == "verified"
    assert run.result.certified == N_NEEDED


class _CollidingRow(identity.FormatRow):

    def tile_counter(self, page: int, ty: int, tx: int) -> int:
        return 0


def test_opposite_metadata_bits_at_one_equation_index_are_terminal():
    bits = {tile: int(_true_bits(*tile)[0]) for tile in TILES}
    assert len(set(bits.values())) == 2, (
        f"the stub mints one metadata bit per tile and they no longer "
        f"disagree ({bits}): the collision below would never be reached")
    colliding = _CollidingRow(
        *[getattr(ROW, field.name) for field in dataclasses.fields(ROW)])
    stub_identity = SimpleNamespace(
        resolve_format_ref=lambda ref: colliding,
        build_site_geometry=identity.build_site_geometry)
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch)
        monkeypatch.setattr(store_module, "identity", stub_identity)
        with pytest.raises(data.IntegrityError,
                           match=r"opposite metadata bits at equation "
                                 r"index 0"):
            _run()


def test_default_mode_consults_the_close_on_every_certificate(stub_runs):
    statuses = tuple(check.status
                     for check in stub_runs["default"].close_checks)
    _h3_support.assert_measured("default close statuses", statuses,
                               CLOSE_STATUS_DEFAULT)
    certified = tuple(check.certified
                      for check in stub_runs["default"].close_checks)
    assert certified == (1, 2, 3, 4)


def test_complete_defers_every_mid_run_close_to_the_exhaustion_consult(
        stub_runs):
    statuses = tuple(check.status
                     for check in stub_runs["complete"].close_checks)
    _h3_support.assert_measured("--complete close statuses", statuses,
                               CLOSE_STATUS_COMPLETE)
    assert stub_runs["complete"].result.status == "verified"


def test_no_close_observes_the_counts_and_never_solves(stub_runs):
    statuses = tuple(check.status
                     for check in stub_runs["no_close"].close_checks)
    _h3_support.assert_measured("--no-close close statuses", statuses,
                               CLOSE_STATUS_NO_CLOSE)
    assert stub_runs["no_close"].result.status == "open"
    assert stub_runs["no_close"].result.payload is None
    assert stub_runs["no_close"].result.certified == N_NEEDED


def test_a_verified_close_preempts_the_mid_run_consults(stub_runs):
    assert len(stub_runs["default"].close_checks) < len(
        stub_runs["complete"].close_checks)
    assert stub_runs["default"].close_checks[-1].status == "verified"


class _GatedCloseProgress(_StubCloseProgress):
    calls: list = []

    def count_progress(self) -> tuple:
        blocks = (data.CloseBlockRow(
            stream_id=None, block=0, have=len(self.seen), needed=1,
            rank=None, solved=False, short=max(0, 1 - len(self.seen)),
            groups_open=1, n_groups=1),)
        return len(self.seen) >= 1, 1, blocks

    def close_is_new(self) -> bool:
        return self.last_attempt is None

    def close(self) -> object:
        self.last_attempt = len(self.seen)
        self.calls.append(len(self.seen))
        return SimpleNamespace(
            status="open", payload=None, k_total=1, blocks=(),
            symbols_used=len(self.seen), reason="short",
            metadata_version=0)


@pytest.fixture(scope="module")
def gated_close() -> tuple[StubRun, list]:
    calls: list = _GatedCloseProgress.calls
    calls.clear()
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch)
        monkeypatch.setattr(engine, "format_close", SimpleNamespace(
            CloseProgress=_GatedCloseProgress))
        run = _run()
    return run, calls


def test_an_open_solve_is_not_reattempted_without_a_new_answer(gated_close):
    run, calls = gated_close
    assert calls == [1, N_NEEDED]
    statuses = tuple(check.status for check in run.close_checks)
    assert statuses == ("open", "count_ready", "count_ready",
                        "count_ready", "open")
    assert all(check.blocks_counting for check in run.close_checks[1:4])
    assert all(check.blocks[0].rank is None
               for check in run.close_checks[1:4])


def test_the_final_consult_ignores_the_close_is_new_gate(gated_close):
    run, calls = gated_close
    assert len(calls) == 2
    assert calls[-1] == N_NEEDED
    final = run.close_checks[-1]
    assert final.certified == N_NEEDED
    assert not final.blocks_counting


def test_the_close_consult_reports_the_metadata_rank_it_solved(stub_runs):
    last = stub_runs["default"].close_checks[-1]
    assert last.metadata_rank == N_NEEDED
    assert last.metadata_n_unique == N_NEEDED


def test_worker_count_never_changes_the_payload_or_the_certificate_count(
        stub_runs):
    serial = stub_runs["default"].result
    pooled = stub_runs["workers8"].result
    assert pooled.payload == serial.payload == PAYLOAD
    assert pooled.status == serial.status == "verified"
    assert pooled.certified == serial.certified == N_NEEDED


def test_the_run_dir_carries_the_declared_products(stub_runs):
    run_dir = stub_runs["default"].run_dir
    for name in RUN_DIR_PRODUCTS:
        assert (run_dir / name).is_file(), name
    assert (run_dir / "argv").read_text().strip()
    assert (run_dir / "pane-page-0.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_the_run_dir_report_agrees_with_the_run_result(stub_runs):
    import json

    run = stub_runs["default"]
    report = json.loads((run.run_dir / "report.json").read_text())
    assert len(report["rows"]) == 6
    assert report["fold_errors"] == 0
    assert report["run_done"]["status"] == run.result.status
    assert (report["run_done"]["payload_sha256"]
            == run.result.payload_sha256)
    assert report["run_done"]["certified"] == run.result.certified
    assert report["run_done"]["n_bytes"] == len(PAYLOAD)


def test_the_events_jsonl_holds_one_line_per_emitted_event(stub_runs):
    run = stub_runs["default"]
    lines = (run.run_dir / "events.jsonl").read_text().splitlines()
    assert len(lines) == len(run.events)


def _bare_engine() -> engine._Engine:
    bare = object.__new__(engine._Engine)
    bare._frontier = []
    bare._seq = 0
    bare._inflight = {}
    bare._bookmarks = {}
    bare._index = {}
    bare._account = {}
    bare._events = []
    bare._queued = {}
    bare._stale_skips = 0
    bare._retired_count = 0
    bare._attempts_hist = {}
    bare._sched_emitted = {}
    bare._wakes = 0
    bare._stat_board = engine.data.StatBoard()
    return bare


def _bookmark(bare: engine._Engine) -> object:
    from holo.receiver.descriptor import WorkerBookmark

    worker = WorkerBookmark(plugin="survey", subject="cap", reads=())
    bare._bookmarks[("survey", "cap")] = worker
    return worker


def test_a_repush_on_an_inflight_worker_defers_instead_of_stacking():
    bare = _bare_engine()
    worker = _bookmark(bare)
    worker.inflight = True
    before = worker.version
    bare._repush("survey", "cap")
    assert worker.version == before + 1
    assert worker.pending is True
    assert bare._frontier == []


def test_the_engine_exports_only_its_declared_public_surface():
    _h3_support.assert_measured(
        "engine.__all__", tuple(engine.__all__),
        ("DESCRIPTORS", "DESCRIPTOR_BY_NAME", "DecodeRequest",
         "decode"))


LIFT_WID = (_h3_facts.CAPTURE_ID, 0, 0, (0, 0, 128, 128))
LIFT_REACH = ((0, 0), (0, 1), (1, 0), (1, 1))
LIFT_STEPS = ("born", "first", "duplicate", "second", "full")
LIFT_FIRES = {"born": 0, "first": 1, "duplicate": 1, "second": 2,
              "full": 2}
LIFT_BASES = {"born": (), "first": ((0, 0, 0),),
              "duplicate": ((0, 0, 0),),
              "second": ((0, 0, 0), (0, 0, 1)),
              "full": ((0, 0, 0), (0, 0, 1))}


class _ImmediateExecutor:

    def submit(self, job: object) -> Future:
        future: Future = Future()
        future.set_result(job())
        return future


def _lift_cells(size: int = 128) -> np.ndarray:
    grid = np.stack(np.meshgrid(np.arange(size), np.arange(size),
                                indexing="ij"), axis=-1)
    return grid.reshape(-1, 2).astype(np.int64)


def _lift_prepare(fired: list) -> object:
    def prepare(store: object, subject: object, stage: str) -> object:
        placement = store.placement(subject)
        evidence = store.evidence(subject)
        basis = tuple(sorted(refine.reach_certified(
            store, placement.page, evidence.page_cells_yx)))
        fired.append(basis)
        shift = float(len(fired))
        revision = refine.Revision(
            True, refine.OUTCOME_ADOPTED,
            (4.0, 0.0, shift, 0.0, 4.0, shift), basis=basis)
        outcome = refine.RefineOutcome(subject, revision)
        return lambda: data.JobResult((outcome,), (), 0.0)

    return prepare


def _lift_drain(instance: object, executor: _ImmediateExecutor) -> None:
    while instance._frontier:
        instance._fill(executor)
        for future in list(instance._inflight):
            instance._merge(future)


@pytest.fixture(scope="module")
def refine_lift() -> dict:
    assert refine.reach_tiles(_lift_cells()) == LIFT_REACH, (
        "a single-tile reach can never be partly certified, so the bench "
        "would pin nothing at all"
    )
    fired: list = []
    row = dataclasses.replace(engine.DESCRIPTOR_BY_NAME["refine"],
                              prepare=_lift_prepare(fired))
    steps: dict = {}
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(engine, "DESCRIPTORS", (row,))
        monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", {"refine": row})
        instance = _h3_facts.new_engine()
        executor = _ImmediateExecutor()
        instance._ingest(_h3_facts.capture())
        instance._ingest(_h3_facts.window(wid=LIFT_WID))
        instance._ingest(dataclasses.replace(
            _h3_facts.placement(wid=LIFT_WID),
            local_cells_yx=_lift_cells()))
        instance._ingest(_h3_facts.evidence(wid=LIFT_WID,
                                            cells=_lift_cells()))
        arrivals = {
            "born": (),
            "first": (_h3_facts.certificate(0, 0, 0),),
            "duplicate": (_h3_facts.certificate(0, 0, 0),),
            "second": (_h3_facts.certificate(0, 0, 1, bit=1),),
            "full": (_h3_facts.certificate(0, 1, 0),
                     _h3_facts.certificate(0, 1, 1, bit=1)),
        }
        for label in LIFT_STEPS:
            for certificate in arrivals[label]:
                instance._ingest(certificate)
            _lift_drain(instance, executor)
            placement = instance.placement(LIFT_WID)
            steps[label] = {
                "fires": tuple(fired),
                "route": placement.route,
                "basis": placement.refine_basis,
                "retired": instance._bookmarks[("refine",
                                                LIFT_WID)].retired,
            }
    return steps


@pytest.mark.parametrize("label", LIFT_STEPS)
def test_refine_fires_exactly_once_per_growth_of_its_certified_reach(
        refine_lift, label):
    _h3_support.assert_measured(f"refine fires after {label}",
                               len(refine_lift[label]["fires"]),
                               LIFT_FIRES[label])


def test_the_first_certificate_in_reach_buys_one_fit_and_one_adoption(
        refine_lift):
    assert refine_lift["born"]["route"] == "word"
    assert refine_lift["first"]["fires"] == (((0, 0, 0),),)
    assert refine_lift["first"]["route"] == refine.ROUTE_REFINE
    assert refine_lift["first"]["basis"] == ((0, 0, 0),)


def test_an_adoption_never_re_arms_the_window_it_revised(refine_lift):
    assert refine_lift["duplicate"]["fires"] == refine_lift["first"][
        "fires"], (
        "the adopted pose wakes the refine worker through its own "
        "pose_affine key: a basis-free gate would loop here forever"
    )
    assert refine_lift["duplicate"]["basis"] == ((0, 0, 0),)


def test_a_second_certificate_re_arms_refine_and_chains_a_second_adoption(
        refine_lift):
    fires = refine_lift["second"]["fires"]
    assert len(fires) == len(refine_lift["duplicate"]["fires"]) + 1
    assert fires[-1] == ((0, 0, 0), (0, 0, 1))
    assert refine_lift["second"]["basis"] == ((0, 0, 0), (0, 0, 1)), (
        "the chained adoption must publish the grown basis, or the next "
        "certificate re-fits against a stale gate"
    )


@pytest.mark.parametrize("label", LIFT_STEPS)
def test_the_published_basis_is_the_reach_the_last_adoption_fitted_on(
        refine_lift, label):
    assert refine_lift[label]["basis"] == LIFT_BASES[label]


def test_a_fully_certified_reach_retires_the_refine_worker(refine_lift):
    assert refine_lift["full"]["fires"] == refine_lift["second"]["fires"]
    assert refine_lift["full"]["retired"] is True
    assert refine_lift["second"]["retired"] is False
    assert refine_lift["born"]["retired"] is False


def test_the_store_consults_the_schema_ordinals_as_the_one_gatekeeper(
        monkeypatch):
    calls: list[str] = []

    def spy(name: str, ordinal: object) -> object:
        def wrapped(value: object) -> tuple:
            calls.append(name)
            return ordinal(value)

        return wrapped

    monkeypatch.setattr(data, "placement_ordinal",
                        spy("placement", data.placement_ordinal))
    monkeypatch.setattr(data, "region_ctx_ordinal",
                        spy("region_ctx", data.region_ctx_ordinal))
    monkeypatch.setattr(data, "lattice_seed_ordinal",
                        spy("lattice_seed", data.lattice_seed_ordinal))
    instance = _h3_facts.seeded_engine("Placement")
    instance._ingest(_h3_facts.placement())
    instance._ingest(_h3_facts.placement(origin_yx=(8.0, 8.0)))
    instance._ingest(_h3_facts.lattice_seed(support_cells=10))
    instance._ingest(_h3_facts.lattice_seed(support_cells=9))
    instance._ingest(_h3_facts.ctx_outcome())
    instance._ingest(_h3_facts.ctx_outcome(offset=0.25))
    assert set(calls) == {"placement", "region_ctx", "lattice_seed"}, (
        "every decision cell's mutator consults the ordinal its schema "
        "declares in holo.receiver.data: one gatekeeper shape, three cells")


def test_an_adopted_revision_publishes_its_held_out_loss_as_quality():
    instance = _h3_facts.seeded_engine("RefineOutcome")
    revision = refine.Revision(
        adopted=True, reason=refine.OUTCOME_ADOPTED,
        affine=(4.0, 0.0, 9.0, 0.0, 4.0, 9.0), candidate_logloss=0.42,
        basis=((0, 0, 0),))
    instance._ingest(refine.RefineOutcome(_h3_facts.WINDOW_ID, revision))
    placement = instance.placement(_h3_facts.WINDOW_ID)
    assert placement.quality == 0.42
    assert placement.route == refine.ROUTE_REFINE
    assert placement.refine_basis == ((0, 0, 0),)


# ------------------------------------------------ the operator's doors
# (2026-09-03): SIGUSR1 dumps the facts and prints the rows, SIGINFO
# prints the rows, SIGINT/SIGTERM stop the run at the next consistent
# point with every product written, and a safety snapshot lands on a
# cadence.  All served at the loop top by the merge thread.  The doors
# themselves left engine.py for operator.py at the 1000-line seam
# (2026-09-17) — the behaviour pinned here did not move with them, so
# these still drive the engine and only the patch targets changed.


def test_the_operator_signals_are_armed_for_the_run_and_restored_after():
    import signal as signal_module

    armed: dict = {}
    originals = {signum: signal_module.getsignal(signum)
                 for signum in operator_doors.OPERATOR_SIGNALS}
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch)
        real_signal = signal_module.signal

        def recording_signal(signum, handler):
            armed.setdefault(signum, []).append(handler)
            return real_signal(signum, handler)

        monkeypatch.setattr(operator_doors.signal, "signal",
                            recording_signal)
        _run()
    assert set(armed) == set(operator_doors.OPERATOR_SIGNALS)
    for signum in operator_doors.OPERATOR_SIGNALS:
        assert signal_module.getsignal(signum) == originals[signum]


#: One run, two subjects, 2026-09-05: the cadence and the engine-side
#: wiring of the atomic write into the run dir used to share one name.
#: One `_run(snapshot_every_s=1e-9)` behind the fixture serves both.
@pytest.fixture(scope="module")
def cadence_run() -> tuple[StubRun, list]:
    calls: list = []
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch)
        real_write = operator_doors._write_snapshot

        def counting_write(path, store):
            calls.append(len(store._certificates))
            real_write(path, store)

        monkeypatch.setattr(operator_doors, "_write_snapshot",
                            counting_write)
        run = _run(snapshot_every_s=1e-9)
    return run, calls


def test_the_safety_snapshot_lands_on_its_cadence_before_the_finish(
        cadence_run):
    run, calls = cadence_run
    assert run.result.status == "verified"
    assert len(calls) >= 2, calls
    assert calls[-1] == N_NEEDED


def test_the_cadence_snapshot_lands_in_the_run_dir_atomically(cadence_run):
    run, _calls = cadence_run
    assert (run.run_dir / "facts.npz").exists()
    assert (run.run_dir / "facts.npz.bak").exists()
    assert not (run.run_dir / "facts.npz.tmp").exists()


def test_a_snapshot_write_keeps_its_predecessor_and_never_a_half_file(
        tmp_path):
    store = SimpleNamespace(
        captures=lambda: (), windows=lambda: (), placements=lambda: (),
        live_pages=lambda: (), certificates=lambda: {})
    path = tmp_path / "facts.npz"
    operator_doors._write_snapshot(path, store)
    first = path.read_bytes()
    assert not (tmp_path / "facts.npz.bak").exists()
    operator_doors._write_snapshot(path, store)
    assert (tmp_path / "facts.npz.bak").read_bytes() == first
    assert not (tmp_path / "facts.npz.tmp").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "facts.npz", "facts.npz.bak"]


def test_sigusr1_dumps_the_facts_and_prints_the_rows(capsys):
    import os
    import signal as signal_module

    writes: list = []

    def signalling_scan(store, subject, stage):
        if not writes:
            writes.append("sent")
            os.kill(os.getpid(), signal_module.SIGUSR1)
        return _stub_scan(store, subject, stage)

    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch, scan_prepare=signalling_scan)
        real_write = operator_doors._write_snapshot

        def counting_write(path, store):
            writes.append(len(store._certificates))
            real_write(path, store)

        monkeypatch.setattr(operator_doors, "_write_snapshot",
                            counting_write)
        run = _run()
    assert run.result.status == "verified"
    assert len([w for w in writes if w != "sent"]) >= 2
    err = capsys.readouterr().err
    assert "snapshot:" in err
    assert "tiles    " in err


def test_sigint_stops_the_run_at_a_consistent_point_with_its_products():
    import os
    import signal as signal_module

    sent: list = []

    def interrupting_scan(store, subject, stage):
        if not sent:
            sent.append(subject)
            os.kill(os.getpid(), signal_module.SIGINT)
        return _stub_scan(store, subject, stage)

    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch, scan_prepare=interrupting_scan)
        run = _run()
    assert run.result.status == "open"
    assert run.result.certified < N_NEEDED
    assert (run.run_dir / "facts.npz").exists()
    assert (run.run_dir / "report.json").exists()
    done = [event for event in run.events if isinstance(event, data.RunDone)]
    assert len(done) == 1 and done[0].status == "open"


# --------------------------------- the orderly stop drains (2026-10-03, S8)
# A stop used to break the loop with jobs still in flight: `cancel_futures`
# cancelled nothing (every in-flight job is already running), `_finish`
# wrote the snapshot without their facts, and concurrent.futures' exit
# join then waited for exactly the work it had thrown away.  The stop now
# stops SCHEDULING and drains; a second signal abandons the drain.  The
# executor and `wait` are the test's hand here: nothing runs until `wait`
# asks, and the signals are delivered through the real doors' handler
# while the jobs are held, i.e. while the run is blocked in its wait.


class _HeldExecutor:
    """Submits without running; `_held_wait` runs one job per call."""

    def __init__(self, max_workers: int) -> None:
        self.max_workers = max_workers
        self.jobs: dict[Future, object] = {}
        self.order: list[Future] = []
        self.shutdowns: list[tuple[bool, bool]] = []

    def submit(self, job: object) -> Future:
        future: Future = Future()
        future.set_running_or_notify_cancel()
        self.jobs[future] = job
        self.order.append(future)
        return future

    def shutdown(self, wait: bool = True,
                 cancel_futures: bool = False) -> None:
        self.shutdowns.append((wait, cancel_futures))


@dataclasses.dataclass
class _StopHarness:
    signals: int
    executors: list = dataclasses.field(default_factory=list)
    doors: list = dataclasses.field(default_factory=list)
    scan_jobs: set = dataclasses.field(default_factory=set)
    submitted_at_stop: int | None = None
    held_at_stop: int | None = None


def _stop_run(monkeypatch: pytest.MonkeyPatch, harness: _StopHarness,
              workers: int, **kwargs: object) -> StubRun:
    import signal as signal_module

    def tagged_scan(store, subject, stage):
        job = _stub_scan(store, subject, stage)
        if job is not None:
            harness.scan_jobs.add(job)
        return job

    def executor_factory(max_workers: int) -> _HeldExecutor:
        executor = _HeldExecutor(max_workers)
        harness.executors.append(executor)
        return executor

    class RecordingDoors(operator_doors.OperatorDoors):
        def __init__(self) -> None:
            super().__init__()
            harness.doors.append(self)

    def held_wait(futures, return_when=None, timeout=None):
        executor = harness.executors[-1]
        pending = [future for future in executor.order
                   if future in futures and not future.done()]
        scans = [future for future in pending
                 if executor.jobs[future] in harness.scan_jobs]
        if harness.submitted_at_stop is None and len(scans) == workers:
            harness.submitted_at_stop = len(executor.order)
            harness.held_at_stop = len(scans)
            for _ in range(harness.signals):
                harness.doors[-1]._on_operator_signal(
                    signal_module.SIGINT, None)
        first = pending[0]
        first.set_result(executor.jobs[first]())
        return {first}, set(futures) - {first}

    _install(monkeypatch, scan_prepare=tagged_scan)
    monkeypatch.setattr(engine, "ThreadPoolExecutor", executor_factory)
    monkeypatch.setattr(engine, "wait", held_wait)
    monkeypatch.setattr(operator_doors, "OperatorDoors", RecordingDoors)
    return _run(workers=workers, **kwargs)


def _after_last_job(run: StubRun) -> tuple:
    last = max(index for index, event in enumerate(run.events)
               if isinstance(event, data.JobDone))
    return run.events[last + 1:]


@pytest.mark.parametrize("complete", (False, True))
def test_a_stop_drains_every_job_in_flight_into_the_snapshot(
        complete, capsys):
    from holo.receiver import snapshot

    harness = _StopHarness(signals=1)
    with pytest.MonkeyPatch.context() as monkeypatch:
        run = _stop_run(monkeypatch, harness, workers=3, complete=complete)
    executor = harness.executors[-1]
    assert harness.held_at_stop == 3
    # Nothing scheduled after the stop, and every fired job merged.
    assert len(executor.order) == harness.submitted_at_stop
    assert all(future.done() for future in executor.order)
    assert run.job_counts["tiles.scan"] == 3
    assert run.result.status == "open"
    assert run.result.certified == 3
    replayed = snapshot.read(run.run_dir / snapshot.NAME)
    assert sum(isinstance(fact, data.Certificate)
               for fact in replayed) == 3
    # The deciding consult ran once, at the end, after the drain --
    # under --complete it is the only one that decided at all.
    deciding = [event for event in run.close_checks
                if not event.blocks_counting]
    assert len(deciding) == 1
    assert deciding[0] in _after_last_job(run)
    assert deciding[0] is run.close_checks[-1]
    if complete:
        assert {event.status for event in run.close_checks[:-1]} == {
            "deferred"}
    err = capsys.readouterr().err
    assert "stop requested: draining 2 in-flight jobs" in err
    assert "abandoning" not in err


def test_a_second_signal_abandons_the_drain(capsys):
    harness = _StopHarness(signals=2)
    with pytest.MonkeyPatch.context() as monkeypatch:
        run = _stop_run(monkeypatch, harness, workers=3)
    executor = harness.executors[-1]
    assert harness.held_at_stop == 3
    assert len(executor.order) == harness.submitted_at_stop
    # The wait that saw the signals finished its one job; the other two
    # were left running, never merged.
    assert run.job_counts["tiles.scan"] == 1
    assert sum(not future.done() for future in executor.order) == 2
    assert executor.shutdowns == [(False, True)]
    assert run.result.certified == 1
    assert not [event for event in run.close_checks
                if not event.blocks_counting]
    err = capsys.readouterr().err
    assert "stop: abandoning 2 in-flight jobs" in err


# ---------------------- a resume that already closes consults (2026-10-03, S8)
# The in-loop consult runs only after a merge that MINTED, so a snapshot
# whose replayed certificates close the volume used to schedule the whole
# residue until a new mint or exhaustion.


#: The residue the old loop would have scheduled: one payload-priced row
#: born by the capture, as every residue row is reachable from one.
RESIDUE_PROBE = "residue-probe"


@pytest.fixture(scope="module")
def closed_resumes() -> dict[str, tuple[StubRun, int]]:
    fired: list[str] = []

    def prepare(store: object, subject: object, stage: str) -> object:
        fired.append(str(subject))
        return lambda: data.JobResult((), (), 0.0)

    probe = _probe_descriptor((RESIDUE_PROBE,), lambda store, subject: (),
                              lambda store, subject: "payload", prepare)
    runs: dict[str, tuple[StubRun, int]] = {}
    with pytest.MonkeyPatch.context() as monkeypatch:
        _install(monkeypatch, extra=(probe,))
        for name, kwargs in (("first", {}), ("default", {"resume": True}),
                             ("complete", {"resume": True,
                                           "complete": True})):
            if kwargs.pop("resume", False):
                kwargs["resume"] = runs["first"][0].run_dir / "facts.npz"
            before = len(fired)
            run = _run(**kwargs)
            runs[name] = (run, len(fired) - before)
    return runs


def test_a_resume_that_already_closes_consults_once_and_schedules_nothing(
        closed_resumes):
    first, first_fires = closed_resumes["first"]
    run, fires = closed_resumes["default"]
    assert first.result.status == "verified"
    assert first_fires == 1
    assert run.result.status == "verified"
    assert run.result.payload == PAYLOAD
    assert run.result.certified == N_NEEDED
    assert fires == 0
    assert run.jobs == ()
    assert [event.status for event in run.close_checks] == ["verified"]
    replayed = [index for index, event in enumerate(run.events)
                if isinstance(event, data.SnapshotReplayed)]
    checked = [index for index, event in enumerate(run.events)
               if isinstance(event, data.CloseCheck)]
    assert replayed and checked and replayed[0] < checked[0]


def test_a_complete_resume_counts_after_replay_and_decides_at_the_end(
        closed_resumes):
    run, fires = closed_resumes["complete"]
    assert run.close_checks[0].status == "deferred"
    assert run.close_checks[0].certified == N_NEEDED
    assert fires == 1
    assert run.close_checks[-1].status == "verified"
    assert run.result.status == "verified"
