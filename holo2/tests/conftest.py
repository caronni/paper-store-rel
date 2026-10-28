"""Shared builders for the data-model tests — and the tests' composition root.

Two jobs, both deliberate:

1. **Composition.** R3 made core generic over a record REGISTRY: each
   package declares the families it writes, and somebody has to put them
   together. That is ``holo2.cli.record_registry``, and ``registry()``
   below CALLS it rather than restating it — two composition roots that
   must agree, or every store refuses at open, is a defect waiting. A
   test that only exercises core's machinery still needs a vocabulary to
   exercise it WITH, so the record types it uses are re-exported from
   here rather than imported out of another package — which is what
   keeps ``tests/test_layering.py``'s test-tree DAG honest: a core test
   names core and this module, nothing else.
2. **Builders.** No RNG anywhere in the record builders: every "property"
   here is exhaustive over enumerated cases (all groupings, all
   permutations), which is what determinism makes possible. The one
   seeded draw is :func:`synthetic_print`, the small synthetic "print"
   the ingest, plans and session tests share — a fixture input, never a
   receiver path.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from typing import Callable

import numpy as np
import pytest

from holo2.capture import (CaptureRecord, FootingSpec, RegionRecord,
                           capture_key, region_key)
from holo2.cli import record_registry
from holo2.core import RecordRegistry, WorkId, WorkScope
from holo2.engine import RECIPE_V1, Recipe
from holo2.engine.recipe import GATE_EXHAUSTION, TASK_CLOSE, PriceTable
from holo2.core.blobs import stage_array
from holo2.core.commit import CommitBatch, CommitEngine, Subscription, Write
from holo2.core.records import (BlobRef, CLOSE_KEY, CloseRecord, CloseStatus,
                                ResourceKey, SubjectSpec, subject_key)
from holo2.core.store import Store
from holo2.engine import SessionIdentity
from holo2.solve.contradiction import WordContradiction, contradiction_key
from holo2.solve.lattice_seed import LatticeSeedRecord, lattice_seed_key
from holo2.solve import (COLLECTION_CERTIFIED, CalibrationRecord,
                         EvidenceObservation, HeldoutGate, LabelPool, MintRef,
                         PoseRecord, TileRecord,
                         WindowRecord, WindowStatus,
                         calibration_key, evidence_collection_key,
                         evidence_key, pack_observed_cells,
                         parse_evidence_key, parse_tile_key, pool_key,
                         pose_collection_key, pose_key,
                         region_evidence_collection_key, tile_key,
                         unpack_observed_cells, window_key)

#: The page domain every fixture session declares (§5.1). Poses outside it
#: are refused by solve's structural validator, so every sample record and
#: every test worker stays inside it.
PAGE_DOMAIN = (0, 1)


def registry(page_domain: tuple[int, ...] = PAGE_DOMAIN) -> RecordRegistry:
    """The full composed record vocabulary — literally ``cli``'s.

    Not a copy of it. The registry manifest is the store's schema
    identity, so two roots that drift apart make every fixture store
    refuse at open; the only thing this adds is the page domain the
    fixtures declare, which production takes from the printed row.
    """
    return record_registry(page_domain)


#: The fixture capture and the region/window/pose keys derived from it.
#: Since the identity law an id IS its values, so a test that wants "some
#: pose" builds the values it is a pose OF — these are those values, in
#: one place, so a test names ``POSE`` rather than restating six floats.
CAPTURE_SHA = "ab" * 32
FOOTING = "cap:8/1"
REGION = region_key(CAPTURE_SHA, (64, 96), 8, (320, 480))
WINDOW = window_key(FOOTING, REGION, (0, 0, 160, 160))
AFFINE = (1.0, 0.0, 3.5, 0.0, 1.0, -2.5)
POSE = pose_key(WINDOW, 0, AFFINE)


def make_session(recipe: Recipe = RECIPE_V1,
                 providers: tuple[str, ...] = ("fixture-v0",)) -> SessionIdentity:
    """The lineage a fixture store is opened under.

    The recipe's ENTRIES and the ordered provider ids are the identity
    (there is no recipe label in it), so a test that wants a different
    lineage passes a different policy rather than a different name.
    """
    return SessionIdentity(
        format_row_id="c2-r0700",
        receiver_policy_id="policy-h1",
        recipe_entries=recipe.entries,
        providers=providers,
        page_domain=PAGE_DOMAIN,
    )


#: Policies that differ from :func:`make_session`'s in exactly one value:
#: a moved gate, a moved price, a moved provider binding and a re-ORDERED
#: one. The executable policy binds BY VALUE, so a test that wants "a
#: different lineage" picks one of these — and a core test can do that
#: without naming ``engine``, which this module composes for it.
MOVED_POLICIES: tuple[SessionIdentity, ...] = (
    SessionIdentity(
        format_row_id="c2-r0700", receiver_policy_id="policy-h1",
        # The moved gate is the CLOSE entry's since 2026-08-17: with the
        # quiescent gate deleted the work vocabulary is one value wide,
        # so the only gate a legal recipe can still move is that one.
        recipe_entries=tuple(
            replace(entry, gate=GATE_EXHAUSTION)
            if entry.task_class == TASK_CLOSE else entry
            for entry in RECIPE_V1.entries),
        providers=("fixture-v0",), page_domain=PAGE_DOMAIN),
    SessionIdentity(
        format_row_id="c2-r0700", receiver_policy_id="policy-h1",
        recipe_entries=tuple(
            replace(entry, prices=PriceTable(max_fires_per_worker=7))
            for entry in RECIPE_V1.entries),
        providers=("fixture-v0",), page_domain=PAGE_DOMAIN),
    make_session(providers=("other-v0",)),
    make_session(providers=("second-v0", "fixture-v0")),
)


def wid(name: str, route: str = "route") -> WorkId:
    """A work id for a test worker: a structure, like every other id."""
    return WorkId("test", ResourceKey("worker", (name,)), route, WorkScope())


@pytest.fixture
def session() -> SessionIdentity:
    return make_session()


@pytest.fixture
def new_store(tmp_path: Path) -> Callable[..., Store]:
    """Factory: ``new_store("a", snapshot_every=1)`` -> a fresh Store."""

    def factory(name: str = "state", **kwargs: object) -> Store:
        return Store.create(tmp_path / name, make_session(), registry(),
                            **kwargs)

    return factory


@pytest.fixture
def engine(new_store: Callable[..., Store]) -> CommitEngine:
    return CommitEngine(new_store())


SYNTHETIC_DPI = 600.0
SYNTHETIC_CELL_PX = 3
SYNTHETIC_ORIGIN = (100, 120)


@pytest.fixture(scope="session")
def synthetic_print(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A small synthetic "print": a binary cell field on paper white.

    Enough real structure for the carried survey to find a region and vote
    a pitch; nothing here is a channel claim. Shared by the ingest
    (capture), plan (solve) and session (engine) tests, which used to
    build it three ways inside one god-module's test file.
    """
    from PIL import Image

    rng = np.random.default_rng(20260809)
    cells = rng.random((128, 128)) < 0.5
    field = np.kron(cells, np.ones((SYNTHETIC_CELL_PX, SYNTHETIC_CELL_PX),
                                   bool))
    page = np.full((600, 600), 235, np.uint8)
    page[SYNTHETIC_ORIGIN[0]:SYNTHETIC_ORIGIN[0] + field.shape[0],
         SYNTHETIC_ORIGIN[1]:SYNTHETIC_ORIGIN[1] + field.shape[1]] = np.where(
             field, 30, 235)
    path = tmp_path_factory.mktemp("capture") / "scan.png"
    Image.fromarray(page).save(path)
    return path


def tile_write(page: int, ty: int, tx: int, stream: str = "K",
               **kwargs: object) -> Write:
    return Write(tile_key(page, ty, tx, stream), TileRecord(**kwargs))


def make_region(support_mask_ref: BlobRef,
                pitch_in_vote: Fraction | None = Fraction(1, 100),
                **kwargs: object) -> RegionRecord:
    """A RegionRecord with plausible R3 lattice geometry filled in.

    Only the fields a test is ABOUT belong in that test; the survey-grid
    geometry OR-12 added is fixture noise everywhere else, so it has one
    home here. Its key is ``record.resource_key()`` — the geometry IS the
    name, so a test that wants a second region moves the origin.
    """
    fields: dict[str, object] = {
        "capture_sha256": CAPTURE_SHA,
        "support_origin_px": (64, 96),
        "support_step_px": 8,
        "support_extent_px": (320, 480),
    }
    fields.update(kwargs)
    return RegionRecord(support_mask_ref=support_mask_ref,
                        pitch_in_vote=pitch_in_vote, **fields)


def make_pose(window_id: ResourceKey = WINDOW, footing_id: str = FOOTING,
              native_affine: tuple[float, ...] = AFFINE,
              page: int = 0) -> PoseRecord:
    """A PoseRecord on page 0 of the fixture page domain (R3)."""
    return PoseRecord(window_id=window_id, footing_id=footing_id, page=page,
                      native_affine=native_affine)


def make_seed(support_cells: int = 1, footing_id: str = FOOTING,
              window_id: ResourceKey = WINDOW) -> LatticeSeedRecord:
    """R5's lattice seed, keyed ``lattice_seed_key(footing_id, REGION)``.

    The fixtures' MOVING record: engine tests need a write whose content
    changes fire after fire, and this family's law is strict improvement
    (``solve/lattice_seed.py`` — a better-SUPPORTED source replaces the
    standing seed), so "different" means "better". A growing
    ``support_cells`` is how a fixture says the fire measured the lattice
    on more cells, which is exactly what a real proposal does.

    It took this job from the hint state when H4 W2's clean-slate sweep
    deleted that family: the two are the tree's only improve-only
    records, so the fixture needed no new shape, only the other one.
    """
    return LatticeSeedRecord(
        footing_id=footing_id, region_id=REGION, rows=(0.25, 0.0, 0.0, 0.25),
        source_window_id=window_id, source_support_cells=support_cells)


def make_window(status: WindowStatus = WindowStatus.ACTIVE,
                extent_cells: tuple[int, int, int, int] = (0, 0, 160, 160),
                **kwargs: object) -> WindowRecord:
    """A WindowRecord whose key is ``record.resource_key()``."""
    fields: dict[str, object] = {"footing_id": FOOTING, "region_id": REGION}
    fields.update(kwargs)
    return WindowRecord(extent_cells=extent_cells, status=status, **fields)


# -------------------------------------------------------------- the ground
#
# F-07's relational half (2026-08-13): a record may not name a record
# nobody committed. The fixture keys above are a CHAIN — a region stands
# on its capture, a window on its region, a pose on its window, a piece on
# its pose and its calibration — so a test that commits anywhere along it
# needs the ground under it, exactly as every real writer already puts it
# there (one batch, or an earlier commit). This is that ground, once, so
# no test grows its own spelling of a capture record.

#: Staged because they must really be in the sidecar: the region's support
#: mask, and the calibration's fitted parameters — whose content address
#: is part of the calibration's own name.
GROUND_MASK = stage_array(np.zeros(4, np.uint8))
GROUND_PARAMS = stage_array(np.zeros(2, np.float64))

#: The fixture calibration: one PAVA fit over ``WINDOW``.
CALIBRATION = calibration_key(WINDOW, "pava-v1", GROUND_PARAMS.ref.sha256)

#: The chain, in the order the references run.
GROUND_ORDER = ("capture", "region", "window", "pose", "calibration")


def ground_batch(upto: str = "calibration") -> CommitBatch:
    """The fixture ground as ONE batch: the chain's prefix up to ``upto``.

    ``ground_batch("capture")`` is just the acquisition; the default is
    the whole chain a piece of evidence or a certificate stands on. The
    records are the same builders every test uses, so a test may also
    commit its OWN region or window on top — as long as it stops the
    chain before the one it wants to write itself (an F-08 frozen family
    refuses a differing second write, which is a different law).
    """
    if upto not in GROUND_ORDER:
        raise AssertionError(f"unknown ground stage {upto!r}")
    wanted = GROUND_ORDER[:GROUND_ORDER.index(upto) + 1]
    writes: list[Write] = []
    blobs = []
    if "capture" in wanted:
        writes.append(Write(capture_key(CAPTURE_SHA), CaptureRecord(
            source_sha256=CAPTURE_SHA, dpi_true=4800.0, shape_px=(100, 200),
            dtype="uint8", channels=3, platen_backing=200.0,
            footings=(FootingSpec("cap:2/1", Fraction(2, 1), CAPTURE_SHA),
                      FootingSpec(FOOTING, Fraction(8, 1), CAPTURE_SHA)))))
    if "region" in wanted:
        writes.append(Write(REGION, make_region(GROUND_MASK.ref)))
        blobs.append(GROUND_MASK)
    if "window" in wanted:
        writes.append(Write(WINDOW, make_window()))
    if "pose" in wanted:
        writes.append(Write(POSE, make_pose()))
    if "calibration" in wanted:
        writes.append(Write(CALIBRATION, CalibrationRecord(
            scope=WINDOW, algorithm="pava-v1", params_ref=GROUND_PARAMS.ref,
            heldout=HeldoutGate(adopted=True, logloss_delta=-0.031))))
        blobs.append(GROUND_PARAMS)
    return CommitBatch(writes=tuple(writes), blobs=tuple(blobs))


def ground(engine: CommitEngine, upto: str = "calibration") -> None:
    """Commit :func:`ground_batch` — one commit, before the test's own.

    IDEMPOTENT, and it has to be: a resumed fixture session lays the same
    ground, and an accepted batch bumps ``commit_seq`` even when every
    write in it is a no-change (L10), which would make a resume that
    changes nothing look like work. So the writes are filtered against
    the store first and a fully-standing ground commits nothing at all.
    """
    batch = ground_batch(upto)
    pending = tuple(write for write in batch.writes
                    if engine.store.get(write.key) != write.record)
    if pending:
        engine.apply(CommitBatch(writes=pending, blobs=batch.blobs))


def sample_records() -> dict[ResourceKey, object]:
    """One instance of every durable record family, at a legal key."""
    ref = BlobRef("00" * 32, 8, dtype="<f4", shape=(2,))
    opaque = BlobRef("11" * 32, 4)
    mask = BlobRef("22" * 32, 512, dtype="|u1", shape=(512,))
    return {
        capture_key("ab" * 32): CaptureRecord(
            source_sha256="ab" * 32, dpi_true=4800.0, shape_px=(100, 200),
            dtype="uint8", channels=3, platen_backing=200.0,
            footings=(FootingSpec("cap:2/1", Fraction(2, 1), "ab" * 32),
                      FootingSpec("cap:8/1", Fraction(8, 1), "ab" * 32))),
        tile_key(0, 1, 2, "K"): TileRecord(
            minting=MintRef(POSE, "scan", "fixture-decoder"),
            bits_ref=ref, metadata_bit=1, observed_by=("cap:2/1", "cap:8/1")),
        REGION: make_region(opaque),
        POSE: make_pose(),
        lattice_seed_key(FOOTING, REGION): make_seed(),
        WINDOW: make_window(retired_reason=None),
        evidence_key(FOOTING, 0, 1, 2, "K", POSE): EvidenceObservation(
            footing_id=FOOTING, page=0, ty=1, tx=2, stream="K",
            pose_id=POSE, llr_ref=ref, observed_ref=mask,
            calibration_id=calibration_key(WINDOW, "pava-v1", ref.sha256)),
        pool_key("pool-1"): LabelPool(
            "pool-1", tuple(sorted((WINDOW, window_key(
                FOOTING, REGION, (0, 128, 160, 288))))),
            (("certified", 12), ("filler", 40), ("word", 3))),
        calibration_key(WINDOW, "pava-v1", ref.sha256): CalibrationRecord(
            WINDOW, "pava-v1", ref,
            HeldoutGate(adopted=True, logloss_delta=-0.031),
            shrinkage_lambda=0.25),
        subject_key("subject-1"): SubjectSpec(
            "subject-1", "place", parent=str(WINDOW),
            parameters=(("reason", "subdivide"),)),
        CLOSE_KEY: CloseRecord(
            # payload_sha256 must equal the bytes_ref address (the
            # CloseRecord names one payload two ways — construction law).
            status=CloseStatus.VERIFIED, payload_sha256="11" * 32,
            bytes_ref=opaque, reason=None),
    }


def subscribe(worker_id: str | WorkId, *keys: ResourceKey) -> Subscription:
    return Subscription(
        worker_id if isinstance(worker_id, WorkId) else wid(worker_id),
        tuple(keys))


def crash(state_dir):
    """Simulate a process death mid-run (F-19-aware).

    A real crash kills the pid, so the single-writer lock's holder reads
    as dead and the next open takes it over. In one test process the pid
    stays alive, so simulating the crash means simulating ALL of it: the
    handles drop un-closed AND the lock dies with the process.
    """
    from holo2.core.store import LOCK_NAME

    (Path(state_dir) / LOCK_NAME).unlink(missing_ok=True)


def spy_on_commits(orchestrator, hook) -> None:
    """Call ``hook(proposal)`` right after each proposal is committed.

    An observer, not state: it runs on the main thread inside the wall,
    which is exactly where a pool test needs to release a fire that must
    still be in flight. Shared by engine/test_pool.py and
    engine/test_pool_wall.py (split 2026-08-17): both need to stage a
    commit-time interleaving deterministically rather than hope for one.
    """
    original = orchestrator._apply

    def spy(proposal):
        outcome = original(proposal)
        hook(proposal)
        return outcome

    orchestrator._apply = spy
