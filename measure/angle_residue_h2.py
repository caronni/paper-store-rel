#!/usr/bin/env python
"""holo2 decode with a placement census attached — read-only wrapper.

    PYTHONPATH=holo2/src:. env/bin/python -m measure.angle_residue_h2 \\
        --census-out <run>/h2-census.json -- --scan ... --dpi ... ...

WHY A WRAPPER.  ``holo2``'s observer publishes only three placement
numbers (ready / windows / retired); the residue question needs the
per-tier fire ledger, the settle census and the end-state slot table,
none of which is durable (the pull model's set is in memory by design,
``solve/place_sched.py`` header).  So this entry wraps four seams of
``PlacementScheduler`` and one of ``WindowJob`` from the OUTSIDE, runs
holo2's own ``cli.main`` on the argv it was handed, and dumps the census
the scheduler was holding when the run ended.

Nothing in ``holo2/`` is edited or imported-and-patched permanently: the
wrappers are installed on the class objects of THIS process only.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path


CENSUS: dict = {
    "fires": [], "settles": [], "exits": [], "slots_end": [],
    "counts_end": {}, "claims": 0}
_SCHEDULERS: list = []


def _install() -> None:
    from holo2.solve import place_job, place_sched

    scheduler_cls = place_sched.PlacementScheduler
    original_init = scheduler_cls.__init__
    original_claim = scheduler_cls.claim
    original_settle = scheduler_cls.settle
    original_exit = scheduler_cls._exit
    original_run = place_job.WindowJob.run

    pending: dict = {}

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _SCHEDULERS.append(self)

    def claim(self, view, subject):
        slot = self._slots.get(subject)
        tier = None if slot is None else slot.tier()
        price = None if (slot is None or tier is None) else slot.price(tier)
        lane = None if slot is None else slot.lane_depth
        depth = None if slot is None else slot.depth
        job = original_claim(self, view, subject)
        if job is not None:
            CENSUS["claims"] += 1
            pending[subject] = (tier, price, lane, depth)
        return job

    def settle(self, view, subject, result):
        tier, price, lane, depth = pending.pop(
            subject, (None, None, None, None))
        outcome = None if result is None else str(result.outcome)
        CENSUS["settles"].append(
            {"window": str(subject), "tier": tier, "price": price,
             "lane_depth": lane, "depth": depth, "outcome": outcome})
        return original_settle(self, view, subject, result)

    def exit_(self, subject, reason):
        CENSUS["exits"].append({"window": str(subject),
                                "reason": str(reason)})
        return original_exit(self, subject, reason)

    def run(self, view, identity, progress):
        started = time.thread_time()
        try:
            return original_run(self, view, identity, progress)
        finally:
            CENSUS["fires"].append(
                {"window": str(self.plan.window_id),
                 "wide": bool(self.wide), "cold": self.cold,
                 "stage": None if self.stage is None else str(self.stage),
                 "cpu_s": time.thread_time() - started})

    scheduler_cls.__init__ = init
    scheduler_cls.claim = claim
    scheduler_cls.settle = settle
    scheduler_cls._exit = exit_
    place_job.WindowJob.run = run


def _harvest() -> None:
    for scheduler in _SCHEDULERS:
        try:
            CENSUS["counts_end"] = dict(scheduler.counters())
            for window_id, slot in scheduler._slots.items():
                CENSUS["slots_end"].append({
                    "window": str(window_id),
                    "lane_depth": slot.lane_depth, "depth": slot.depth,
                    "ready": bool(slot.ready),
                    "in_flight": bool(slot.in_flight),
                    "tier": slot.tier(), "n_tried": len(slot.tried),
                    "centre_spent": bool(slot.centre_spent),
                    "rest_spent": bool(slot.rest_spent),
                    "wide_spent": bool(slot.wide_spent),
                    "cold_armed": bool(slot.cold_armed),
                    "cold_live_spent": bool(slot.cold_live_spent),
                    "cold_rest_spent": bool(slot.cold_rest_spent),
                    "subdivided": bool(slot.subdivided),
                    "cold_parked": bool(slot.cold_parked)})
        except Exception as exc:                      # census is inert
            CENSUS.setdefault("harvest_error", str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--census-out", type=Path, required=True)
    parser.add_argument("decode_argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    decode_argv = [item for item in args.decode_argv if item != "--"]
    _install()
    from holo2 import cli

    started = time.perf_counter()
    try:
        code = cli.main(decode_argv)
    except SystemExit as exc:
        code = int(exc.code or 0)
    wall = time.perf_counter() - started
    _harvest()
    CENSUS["wall_seconds"] = wall
    CENSUS["exit_code"] = int(code)
    CENSUS["settle_outcomes"] = dict(Counter(
        row["outcome"] for row in CENSUS["settles"]))
    CENSUS["settle_tiers"] = dict(Counter(
        str(row["tier"]) for row in CENSUS["settles"]))
    CENSUS["exit_reasons"] = dict(Counter(
        row["reason"] for row in CENSUS["exits"]))
    args.census_out.parent.mkdir(parents=True, exist_ok=True)
    args.census_out.write_text(json.dumps(CENSUS) + "\n")
    print(f"census: {len(CENSUS['fires'])} fires, "
          f"{len(CENSUS['slots_end'])} slots left, exit {code}",
          file=sys.stderr)
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
