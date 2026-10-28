from __future__ import annotations

import heapq
from concurrent.futures import Future

import pytest

from holo3 import data, engine
from holo3.descriptor import (
    KEY_PAGE_CERTS,
    PluginDescriptor,
    WorkerBookmark,
)
from holo3.tests import _h3_facts, _h3_support

PROBE = "probe"
PEER = "peer"
CHEAP = "cheap"
DEAR = "dear"
PROBE_PRICES = {CHEAP: 20, DEAR: 200}

PEER_ARRIVALS = ("zeta", "alpha", "zeta", "mu")

ESCALATED_PUSHES = ((1, 20), (2, 40), (3, 60))
ESCALATED_PRICES = (40, 60, 80)


def _descriptor(name: str = PROBE, stage: str = CHEAP,
                prepare: object = None) -> PluginDescriptor:
    def default(store: object, subject: object, name: str) -> object:
        return lambda: data.JobResult((), (), 0.0)

    return PluginDescriptor(
        name=name, subject_kind="probe", born_by=(data.Capture,),
        subjects_of=lambda store, fact: (),
        reads=lambda store, subject: (),
        eligible=lambda store, subject: True,
        stage=lambda store, subject: stage,
        cost=lambda store, subject, named, attempts, last_cost: (
            PROBE_PRICES[named]),
        retire=lambda store, subject: False,
        prepare=default if prepare is None else prepare,
        produces=(), prices=tuple(sorted(PROBE_PRICES.items())))


def _recording_descriptor(seen: list, escalates: bool) -> PluginDescriptor:
    def cost(store: object, subject: object, named: str, attempts: int,
             last_cost: int) -> int:
        seen.append((attempts, last_cost))
        ordinal = attempts + 1 if escalates else 1
        return PROBE_PRICES[named] * ordinal

    return PluginDescriptor(**{**_descriptor().__dict__, "cost": cost})


class _Executor:

    def __init__(self) -> None:
        self.jobs: list = []

    def submit(self, job: object) -> Future:
        future: Future = Future()
        self.jobs.append((job, future))
        return future

    def finish(self, index: int = 0) -> Future:
        job, future = self.jobs[index]
        future.set_result(job())
        return future


def _bench(names: tuple[str, ...] = (PROBE,), stage: str = CHEAP,
           workers: int = 4) -> tuple[object, _Executor]:
    instance = _h3_facts.new_engine(workers=workers)
    rows = tuple(_descriptor(name, stage) for name in names)
    instance.__dict__["_probe_rows"] = rows
    engine_by_name = dict(engine.DESCRIPTOR_BY_NAME)
    engine_by_name.update({row.name: row for row in rows})
    instance.__dict__["_probe_by_name"] = engine_by_name
    return instance, _Executor()


def _worker(instance: object, plugin: str = PROBE,
            subject: object = "s") -> WorkerBookmark:
    worker = WorkerBookmark(plugin=plugin, subject=subject, reads=())
    instance._bookmarks[(plugin, subject)] = worker
    return worker


@pytest.fixture()
def bench(monkeypatch: pytest.MonkeyPatch) -> object:
    instance, executor = _bench()
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                        instance.__dict__["_probe_by_name"])
    return instance, executor


@pytest.fixture()
def peers(monkeypatch: pytest.MonkeyPatch) -> object:
    instance, executor = _bench(names=tuple(sorted(set(PEER_ARRIVALS))))
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                        instance.__dict__["_probe_by_name"])
    return instance, executor


def test_every_push_prices_at_the_declared_cost_and_nothing_else(bench):
    instance, executor = bench
    worker = _worker(instance)
    instance._push_worker(worker)
    prices = [instance._frontier[0][0]]
    for round_index in range(7):
        instance._fill(executor)
        instance._merge(executor.finish(round_index))
        worker.version += 1
        instance._push_worker(worker)
        prices.append(instance._frontier[0][0])
    assert prices == [PROBE_PRICES[CHEAP]] * 8, (
        "cost is a scheduling function of the plugin alone: the engine "
        "never re-prices a re-fired worker (ruling 2026-08-29)")


def _fire_rounds(instance: object, executor: _Executor,
                 worker: WorkerBookmark, seen: list,
                 n_rounds: int) -> tuple[tuple, tuple]:
    pushes: list = []
    prices: list = []
    for round_index in range(n_rounds):
        instance._fill(executor)
        instance._merge(executor.finish(round_index))
        worker.version += 1
        instance._push_worker(worker)
        pushes.append(seen[-1])
        prices.append(instance._frontier[0][0])
    return tuple(pushes), tuple(prices)


def test_the_engine_hands_a_row_its_fire_ordinal_and_its_last_push_price(
        monkeypatch):
    instance, executor = _bench()
    seen: list[tuple[int, int]] = []
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                        {PROBE: _recording_descriptor(seen, False)})
    worker = _worker(instance)
    instance._push_worker(worker)
    assert seen[0] == (0, 0), (
        "a bookmark that has never fired arrives at cost() with fire "
        "ordinal 0 and no previous price")
    pushes, prices = _fire_rounds(instance, executor, worker, seen, 3)
    assert pushes == ((1, 20), (2, 20), (3, 20)), (
        "attempts is the bookmark's fire ordinal and last_cost the price "
        "this worker was last pushed at — both passed verbatim")
    assert prices == (20, 20, 20)
    assert worker.last_cost == 20


def test_a_row_that_prices_by_its_own_fire_ordinal_escalates_untouched(
        monkeypatch):
    instance, executor = _bench()
    seen: list[tuple[int, int]] = []
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                        {PROBE: _recording_descriptor(seen, True)})
    worker = _worker(instance)
    instance._push_worker(worker)
    pushes, prices = _fire_rounds(instance, executor, worker, seen, 3)
    assert pushes == ESCALATED_PUSHES
    assert prices == ESCALATED_PRICES, (
        "the escalation is the plugin's arithmetic alone: the engine pushes "
        "exactly what cost() returned (ruling 2026-08-29 night)")
    assert worker.last_cost == ESCALATED_PRICES[-1]


def test_a_dear_row_pushes_at_its_own_declared_price(monkeypatch):
    instance, _executor = _bench(stage=DEAR)
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                        instance.__dict__["_probe_by_name"])
    worker = _worker(instance)
    instance._push_worker(worker)
    assert [entry[0] for entry in instance._frontier] == [PROBE_PRICES[DEAR]]


def test_a_worker_whose_stage_is_none_is_priced_out_and_never_queued(
        monkeypatch):
    instance, _executor = _bench()
    row = _descriptor()
    silent = PluginDescriptor(**{**row.__dict__,
                                 "stage": lambda store, subject: None})
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", {PROBE: silent})
    worker = _worker(instance)
    instance._push_worker(worker)
    assert instance._frontier == []


def test_same_price_peers_pop_in_arrival_order_and_never_by_name(peers):
    instance, _executor = peers
    for index, name in enumerate(PEER_ARRIVALS):
        instance._push_worker(_worker(instance, plugin=name,
                                      subject=f"s{index}"))
    popped = []
    while instance._frontier:
        popped.append(heapq.heappop(instance._frontier)[2])
    _h3_support.assert_golden("same-price pop order", tuple(popped),
                              PEER_ARRIVALS)
    assert tuple(popped) != tuple(sorted(PEER_ARRIVALS)), (
        "a collision broken by name would starve the late half of the "
        "alphabet: same-price rows are deliberate round-robin peers")


def test_the_collision_tie_break_is_the_arrival_sequence_alone(peers):
    instance, _executor = peers
    for index, name in enumerate(PEER_ARRIVALS):
        instance._push_worker(_worker(instance, plugin=name,
                                      subject=f"s{index}"))
    prices = {entry[0] for entry in instance._frontier}
    sequences = [entry[1] for entry in instance._frontier]
    assert len(prices) == 1
    assert len(set(sequences)) == len(sequences), (
        "the sequence number must be unique, or the heap falls through to "
        "comparing plugin names")


def test_a_dearer_arrival_never_overtakes_a_cheap_one_that_arrived_later(
        monkeypatch):
    instance, _executor = _bench(names=(DEAR, CHEAP))
    rows = {DEAR: _descriptor(DEAR, DEAR), CHEAP: _descriptor(CHEAP, CHEAP)}
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME", rows)
    instance._push_worker(_worker(instance, plugin=DEAR, subject="d"))
    instance._push_worker(_worker(instance, plugin=CHEAP, subject="c"))
    popped = [heapq.heappop(instance._frontier)[2]
              for _ in range(len(instance._frontier))]
    assert popped == [CHEAP, DEAR]


def test_one_job_in_flight_a_second_frontier_entry_for_it_fires_nothing(
        bench):
    instance, executor = bench
    worker = _worker(instance)
    instance._push_worker(worker)
    worker.version += 1
    instance._push_worker(worker)
    assert len(instance._frontier) == 1, (
        "replace-on-push: a bookmark holds at most one live frontier "
        "entry, so a same-price re-push keeps the standing seat")
    instance._fill(executor)
    assert len(executor.jobs) == 1
    assert worker.inflight is True
    assert instance._frontier == []


def test_a_superseded_entry_pops_as_a_token_discard_never_a_fire(bench):
    instance, executor = bench
    worker = _worker(instance)
    instance._push_worker(worker)
    dead_seq = worker.seat_seq
    worker.seat_cost = PROBE_PRICES[DEAR]
    worker.version += 1
    instance._push_worker(worker)
    assert worker.seat_seq != dead_seq
    assert len(instance._frontier) == 2
    assert instance._queued[PROBE] == 1, (
        "a superseded entry is discounted the moment its seat moves, "
        "not at its pop")
    instance._fill(executor)
    assert len(executor.jobs) == 1
    assert instance._stale_skips == 1, (
        "the dead entry costs one token check, never a retire or an "
        "eligibility adjudication")
    assert instance._frontier == []


def test_a_stranded_entry_popped_during_flight_defers_it_never_fires(
        monkeypatch):
    instance, executor = _bench(names=(PROBE, PEER), workers=2)
    monkeypatch.setattr(engine, "DESCRIPTOR_BY_NAME",
                        instance.__dict__["_probe_by_name"])
    worker = _worker(instance, subject="w")
    peer = _worker(instance, plugin=PEER, subject="p")
    instance._push_worker(worker)
    instance._push_worker(peer)
    instance._fill(executor)
    assert worker.inflight is True and peer.inflight is True
    instance._seq += 1
    worker.seat_seq = instance._seq
    worker.seat_cost = PROBE_PRICES[CHEAP]
    heapq.heappush(instance._frontier, (PROBE_PRICES[CHEAP], instance._seq,
                                        PROBE, CHEAP, "w"))
    instance._queued[PROBE] = instance._queued.get(PROBE, 0) + 1
    assert len(instance._frontier) == 1, (
        "a live entry stranded on the frontier across its own worker's "
        "flight — the state the pop-side one-in-flight rule exists for")
    instance._repush(PROBE, "w")
    assert worker.pending is True and len(instance._frontier) == 1
    instance._merge(executor.finish(1))
    instance._fill(executor)
    live = [row[:2] for row in instance._inflight.values()]
    assert live.count((PROBE, "w")) == 1, (
        "a stranded pre-fire entry popped while its worker is in flight "
        "must defer, not start a second concurrent job (one job in flight "
        "per worker, D6 addendum 8a)")
    assert worker.attempts == 1, (
        "the deferred pop is not a fire: attempts stays the bookmark's "
        "true fire ordinal, which plugin-owned escalation prices from")
    assert worker.pending is True
    instance._merge(executor.finish(0))
    assert worker.inflight is False and worker.pending is False
    assert len(instance._frontier) == 1, (
        "the deferred wake is not lost: the merge re-pushes it once")


def test_a_wake_during_flight_defers_and_the_merge_re_pushes_it_once(bench):
    instance, executor = bench
    worker = _worker(instance)
    instance._push_worker(worker)
    instance._fill(executor)
    assert worker.inflight is True and instance._frontier == []
    instance._touch(())
    worker.version += 1
    instance._push_worker(worker)
    assert worker.pending is True and instance._frontier == []
    instance._merge(executor.finish())
    assert worker.inflight is False and worker.pending is False
    assert len(instance._frontier) == 1
    instance._fill(executor)
    assert len(executor.jobs) == 2


def test_a_worker_is_never_in_flight_twice_over_a_whole_wake_storm(bench):
    instance, executor = bench
    worker = _worker(instance)
    instance._push_worker(worker)
    seen = []
    for round_index in range(5):
        instance._fill(executor)
        seen.append(len([row for row in instance._inflight.values()
                         if row[:2] == (PROBE, "s")]))
        worker.version += 1
        instance._push_worker(worker)
        seen.append(len([row for row in instance._inflight.values()
                         if row[:2] == (PROBE, "s")]))
        instance._merge(executor.finish(round_index))
    assert set(seen) == {1}
    assert len(executor.jobs) == 5


def test_a_stale_result_cannot_land_because_a_stale_job_is_never_started(
        bench):
    instance, executor = bench
    worker = _worker(instance)
    instance._push_worker(worker)
    instance._fill(executor)
    prepared_at = worker.tried_version
    for _ in range(3):
        worker.version += 1
        instance._push_worker(worker)
    assert len(executor.jobs) == 1, (
        "three wakes arrived mid-flight and started nothing: the older job "
        "is the only one running, so merge order is preparation order and "
        "there is no stale write to guard against"
    )
    instance._merge(executor.finish())
    assert worker.version > prepared_at
    assert len(instance._frontier) == 1


def test_a_pending_bit_collapses_a_wake_storm_into_one_re_push(bench):
    instance, executor = bench
    worker = _worker(instance)
    instance._push_worker(worker)
    instance._fill(executor)
    for _ in range(6):
        worker.version += 1
        instance._push_worker(worker)
    instance._merge(executor.finish())
    assert len(instance._frontier) == 1


def test_the_version_floor_swallows_the_re_push_when_nothing_really_changed(
        bench):
    instance, executor = bench
    worker = _worker(instance)
    instance._push_worker(worker)
    instance._fill(executor)
    worker.pending = True
    instance._merge(executor.finish())
    assert len(instance._frontier) == 1
    instance._fill(executor)
    assert len(executor.jobs) == 1, (
        "the pending bit was set without a version bump: the floor at pop "
        "must swallow it")


def test_the_lane_generation_guard_is_gone_and_one_in_flight_replaced_it():
    source = (_h3_support.HOLO3_ROOT / "engine.py").read_text()
    store_source = (_h3_support.HOLO3_ROOT / "store.py").read_text()
    for dead in ("lane_generation", "_freeze_epoch", "_extra", "_digest",
                 "tobytes"):
        assert dead not in source, dead
        assert dead not in store_source, dead
    assert "hashlib" not in store_source, (
        "the store hashes nothing: change detection is value-compare at the "
        "written cell, never a content digest (D6 addendum 6)")
    assert "worker.inflight" in source and "worker.pending" in source


def test_the_engine_wakes_only_through_the_inverted_index(bench):
    instance, _executor = bench
    worker = _worker(instance)
    instance._register_reads(worker, ((KEY_PAGE_CERTS, 0),))
    worker.reads = ((KEY_PAGE_CERTS, 0),)
    instance._touch(((KEY_PAGE_CERTS, 0),))
    assert worker.version == 1
    instance._touch(((KEY_PAGE_CERTS, 1),))
    assert worker.version == 1
