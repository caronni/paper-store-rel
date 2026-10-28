"""The plane's memory model: one generation per fire (H4 W-S).

Before H4 the round barrier WAS this model — reader threads memoised the
derived views into the plane and ``warm()`` materialised them on the main
thread before each dispatch round. Under continuous admission commits
interleave with running fires, so the views became a generation-stamped
object the committer REPLACES and a fire PINS.

Three claims, and they are the whole design:

1. a pinned fire reads one generation, whatever lands while it runs —
   asserted deterministically against a commit made while the fire is
   parked, and then under real churn from reader threads;
2. the committing thread reads the NEW generation (its own pin died with
   the views it named, L11);
3. what a generation costs is what the barrier cost: views that do not
   die at a commit are carried into the next generation rather than
   rebuilt — the window lattices always, the done projections when the
   two monotone counts they are a function of did not move.
"""
from __future__ import annotations

from fractions import Fraction

import threading
from pathlib import Path

import pytest

from holo2.capture.ingest import ingest_capture
from holo2.core.commit import CommitBatch, CommitEngine, Write
from holo2.core.store import Store
from holo2.core.trace import TraceWriter
from holo2.format import FormatRowSpec
from holo2.format.close_spec import CloseStreamProfile
from holo2.solve import TileRecord, tile_key
from holo2.solve import tilemap
from holo2.solve.plane import open_plane
from holo2.solve.view import as_plane
from conftest import make_session, registry

DPI = 600.0

ROW = FormatRowSpec(
    row_id="c3-test@128x128", codec_id="k-v1", seed=b"holo/v1/test/128x128",
    tiles_yx=(2, 2), pitch_in=Fraction(1, 200),
    streams=(CloseStreamProfile("main", 32),), n_pages=1)

#: Reader threads, and the commits they run against. The readers fire
#: until the committer says stop — the committer waits for a fire between
#: every pair of commits, so the interleaving is a fact and not a timing
#: hope, and how MANY fires happen in between is the race. The cap is a
#: hang guard, never a target.
READERS = 4
COMMITS = 20
FIRE_CAP = 100_000


@pytest.fixture
def plane(tmp_path: Path, synthetic_print: Path):
    """A real plane over one ingested capture, and its commit authority.

    The ingest is DIRECT (H4 streaming ingestion): the survey left
    ``open_plane`` when it became scheduled work, so the fixture commits
    the capture facts the
    way an ingest fire's proposal would and lets the plane attach the
    pixels by reopen.
    """
    store = Store.open_or_create(tmp_path / "state", make_session(),
                                 registry(), fsync=False)
    engine = CommitEngine(store, trace=TraceWriter(store.trace_path))
    ingest_capture(engine, synthetic_print, DPI, ROW.pitch_in)
    yield open_plane(store, engine, ROW, ((synthetic_print, DPI),)), engine
    store.close()


def _commit(engine: CommitEngine, plane, nth: int) -> None:
    """One commit the derived views can SEE, then the invalidation.

    A tile record per page/row/column of the fixture row, each one gaining
    a footing in ``observed_by`` on every later pass, so the signature
    below moves at every single commit — a generation that is not a new
    number is not a generation this test can prove anything about.
    """
    page, ty, tx = (nth // 4) % 2, (nth // 2) % 2, nth % 2
    key = tile_key(page, ty, tx, "main")
    current = engine.store.get(key)
    observed = () if current is None else current.observed_by
    record = TileRecord(observed_by=tuple(
        sorted({*observed, f"cap:{nth}/1"})))
    engine.apply(CommitBatch(writes=(Write(key, record),)))
    plane.invalidate()


def _signature(plane) -> tuple[int, int]:
    """What this reader's generation says, in two numbers."""
    index = plane.index()
    return (len(index.tiles),
            sum(len(record.observed_by) for record in index.tiles.values()))


def _fire(plane) -> tuple[tuple[int, int], bool]:
    """One fire: pin, read everything a worker reads, re-read the lot.

    The pin is taken exactly where a worker's is — ``as_plane``, the seam
    the engine hands its view through — so what this exercises is the
    production path, not a test-only entry point.
    """
    view = as_plane(plane)
    index = view.index()
    tiles = view.tiles()
    before = _signature(view)
    for footing_id in view.footing_ids("all"):
        view.window_plans(footing_id)
    for capture in view.captures:
        for region in capture.regions:
            view.done(region.region_id)
    coherent = (view.index() is index and view.tiles() is tiles
                and _signature(view) == before)
    return before, coherent


def test_a_pinned_fire_never_sees_a_commit_that_lands_under_it(plane) -> None:
    """Claim 1 and 2, deterministically: the fire is parked at the wall."""
    view, engine = plane
    pinned, released = threading.Event(), threading.Event()
    seen: dict[str, object] = {}

    def fire() -> None:
        as_plane(view)
        seen["index"] = view.index()
        seen["before"] = _signature(view)
        pinned.set()
        released.wait(10)
        seen["after"] = _signature(view)
        seen["same_index"] = view.index() is seen["index"]

    thread = threading.Thread(target=fire, name="pinned-fire")
    thread.start()
    assert pinned.wait(10), "the fire never pinned"
    _commit(engine, view, 0)
    committer = _signature(view)
    released.set()
    thread.join(10)
    assert not thread.is_alive()

    assert seen["after"] == seen["before"], "a fire saw two generations"
    assert seen["same_index"], "the pinned index was rebuilt under the fire"
    assert committer != seen["before"], (
        "the committing thread must read the generation it just made")


def test_reader_threads_stay_coherent_while_the_committer_commits(
        plane) -> None:
    """Claim 1 under the real shape: readers pin while commits land."""
    view, engine = plane
    start = threading.Barrier(READERS + 1)
    incoherent: list[str] = []
    observed: list[set[tuple[int, int]]] = [set() for _ in range(READERS)]
    fires = [0] * READERS
    stop, fired = threading.Event(), threading.Event()

    def reader(slot: int) -> None:
        start.wait(10)
        while not stop.is_set() and fires[slot] < FIRE_CAP:
            signature, coherent = _fire(view)
            observed[slot].add(signature)
            fires[slot] += 1
            fired.set()
            if not coherent:
                incoherent.append(f"reader {slot} saw a torn view")

    threads = [threading.Thread(target=reader, args=(slot,),
                                name=f"reader-{slot}")
               for slot in range(READERS)]
    for thread in threads:
        thread.start()
    start.wait(10)
    # The handshake makes the interleaving a FACT rather than a hope: one
    # fire lands before any commit does, and one lands between every pair
    # of commits. What the readers race over is everything else.
    assert fired.wait(10), "no reader fired"
    for nth in range(COMMITS):
        _commit(engine, view, nth + 1)
        fired.clear()
        assert fired.wait(10), "a reader must fire between two commits"
    stop.set()
    for thread in threads:
        thread.join(10)
        assert not thread.is_alive()

    assert not incoherent, incoherent[:4]
    assert sum(fires) > COMMITS, "the readers did not fire across the churn"
    assert len(set().union(*observed)) > 1, (
        "no reader ever saw the store move: the churn did not interleave")
    # The committer holds no pin outside a fire, so it is never behind a
    # reader: both signature components only grow.
    assert _signature(view) >= max(signature for seen in observed
                                   for signature in seen)


def test_the_window_lattice_survives_every_generation(plane) -> None:
    """Claim 3, the unconditional half: window plans never die."""
    view, engine = plane
    footing_id = view.footing_ids("all")[0]
    plans = view.window_plans(footing_id)
    index = view.index()
    _commit(engine, view, 7)
    assert view.index() is not index, "the store-derived views did die"
    assert view.window_plans(footing_id) is plans, (
        "a window lattice is a function of footing and region, not of the "
        "store: rebuilding it at a commit is cost the barrier never paid")


def test_a_done_projection_is_carried_while_its_counts_stand(plane) -> None:
    """Claim 3, the conditional half: the §6 cache key is an inheritance."""
    view, engine = plane
    region_id = view.captures[0].regions[0].region_id
    projection = view.done(region_id)
    _commit(engine, view, 3)         # a tile write moves neither count
    assert view.done(region_id) is projection, (
        "equal (poses, certified) counts mean an equal projection")


def test_the_carry_survives_a_generation_nobody_touched(plane) -> None:
    """Which generations got touched is a scheduling accident, not a cost."""
    view, engine = plane
    region_id = view.captures[0].regions[0].region_id
    projection = view.done(region_id)
    _commit(engine, view, 1)
    view.window_plans(view.footing_ids("all")[0])   # index never built here
    _commit(engine, view, 2)
    assert view.done(region_id) is projection, (
        "an untouched generation ended the inheritance chain")


def test_an_unpinned_reader_follows_the_generation(plane) -> None:
    """The other side of the pin: no pin, no staleness."""
    view, engine = plane
    before = _signature(view)
    _commit(engine, view, 5)
    assert _signature(view) != before


def test_a_commit_that_says_what_moved_advances_the_index(
        plane, monkeypatch) -> None:
    """Claim 3, the third carry (F-17): a told commit never rebuilds.

    The index used to be rebuilt from the store's sorted keys at every
    commit — 26.3% of a serial decode's wall. Told what moved, the plane
    hands the next generation the SAME index advanced by that delta; the
    from-scratch builder survives as the resume seed and the oracle
    (``holo2/measure/index_equivalence.py``), and here as the thing that
    must not run.
    """
    view, engine = plane
    builds = []
    build = tilemap.StoreIndex.build.__func__
    monkeypatch.setattr(tilemap.StoreIndex, "build", classmethod(
        lambda cls, store: (builds.append(1), build(cls, store))[1]))
    signature = _signature(view)                     # the seed build
    assert builds == [1]
    for nth in range(4):
        key = tile_key((nth // 4) % 2, (nth // 2) % 2, nth % 2, "main")
        current = engine.store.get(key)
        observed = () if current is None else current.observed_by
        result = engine.apply(CommitBatch(writes=(Write(key, TileRecord(
            observed_by=tuple(sorted({*observed, f"cap:{nth}/1"})))),)))
        view.invalidate(result.changed_keys)
        assert _signature(view) != signature, "the generation did not move"
        signature = _signature(view)
    assert builds == [1], "a told commit rebuilt the index from the store"
    # And an UNTOLD one is honest about it: no delta, full rebuild.
    view.invalidate()
    _signature(view)
    assert builds == [1, 1]


# ------------------------------------------------ the pixel memos (H4 W1a)

def test_the_pixel_memo_outlives_every_generation(plane, monkeypatch) -> None:
    """Claim 4: what the PIXELS are is not a function of the store.

    The prepared plane is a function of the raster and the survey — both
    fixed at session open — so it is a session memo, not a derived view.
    Keying it by generation would re-run a full-resolution pass at every
    commit, which is precisely the per-fire cost W1a removed; this asserts
    the opposite happens, by counting the builds while the generation
    moves under them.

    THE BACKING IS NO LONGER A MEMO HERE (2026-08-17): it is
    ``CaptureRecord.platen_backing``, read off the record, so what this
    once counted (one border pass per session) is now zero passes and one
    attribute read. Its own pins moved to the producer
    (``tests/capture/test_ingest.py``) and to the bit-equality check
    against the carried kernel (``tests/solve/test_pose_fit.py``); what
    stays here is that the value the plane serves IS the record's.
    """
    # The pixel side moved to ``plane_pixels`` at H4-LANES stage 2 (the
    # opener split); the memo it is patched through is that module's
    # import of ``prepared_region`` now, and nothing else about this
    # count changed.
    from holo2.solve import plane_pixels as plane_module
    from holo2.solve import prepared as prepared_module
    from holo2.solve.place_model import PlacementConfig

    view, engine = plane
    region = view.captures[0].regions[0]
    config = PlacementConfig()
    builds = {"prepared": 0}
    inner_prepared = plane_module.prepared_region

    def counted_prepared(*args, **kwargs):
        builds["prepared"] += 1
        return inner_prepared(*args, **kwargs)

    monkeypatch.setattr(plane_module, "prepared_region", counted_prepared)
    recorded = view.captures[0].record.platen_backing
    first = view.prepared_region(region, config=config)
    assert first is not None
    for nth in range(4):
        _commit(engine, view, nth)
        assert view.index() is not None                  # a live generation
        assert view.prepared_region(region, config=config) is first, (
            "a commit rebuilt the region's pixels")
        assert view.platen_backing(region.capture_sha256) == recorded
    assert builds == {"prepared": 1}
    # And the files are a SIBLING of the state directory, never inside it.
    directory = prepared_module.prepared_directory(engine.store.state_dir)
    assert directory.parent == engine.store.state_dir.parent
    assert len(list(directory.iterdir())) == 3


# --- descriptor headroom (the fd budget, user ruling 2026-08-17) ----------

def test_the_fd_budget_is_generous_monotone_and_floored() -> None:
    """The mapped-object arithmetic: floor for small sessions, generous
    per-region term (lanes multiply planes), monotone in both counts."""
    from holo2.solve.plane_views import (FD_FLOOR, fd_budget)
    assert fd_budget(0, 0) == FD_FLOOR
    assert fd_budget(1, 1) == FD_FLOOR          # one sheet rides the floor
    demo = fd_budget(9, 180)                     # the scrap demo that died
    assert demo > 540, "nine platens' ~540 real mappings must fit"
    assert demo == fd_budget(9, 180) <= fd_budget(9, 181) <= fd_budget(10, 181)


def test_headroom_raises_only_clamps_and_advises(
        monkeypatch: "pytest.MonkeyPatch", capsys: "pytest.CaptureFixture[str]",
        ) -> None:
    """Raise-only to the hard limit; one stderr advisory past it; a soft
    limit already above the budget is left exactly alone."""
    import holo2.solve.plane_views as plane_module
    calls: list[tuple[int, int]] = []
    limits = {"soft": 256, "hard": 1024}

    def fake_get(which: int) -> tuple[int, int]:
        return (limits["soft"], limits["hard"])

    def fake_set(which: int, pair: tuple[int, int]) -> None:
        calls.append(pair)
        limits["soft"] = pair[0]

    monkeypatch.setattr(plane_module.resource, "getrlimit", fake_get)
    monkeypatch.setattr(plane_module.resource, "setrlimit", fake_set)
    # Below the hard limit: raised exactly to the budget, silently.
    plane_module.ensure_fd_headroom(512)
    assert calls == [(512, 1024)] and capsys.readouterr().err == ""
    # Past the hard limit: clamped, and the advisory names both numbers.
    plane_module.ensure_fd_headroom(4096)
    assert calls[-1] == (1024, 1024)
    err = capsys.readouterr().err
    assert "4096" in err and "1024" in err and "hard limit" in err
    # Already sufficient: no syscall, no output (raise-only).
    before = list(calls)
    plane_module.ensure_fd_headroom(512)
    assert calls == before and capsys.readouterr().err == ""
