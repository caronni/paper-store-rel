#!/usr/bin/env python
"""OR-5's per-key BP budget and OR-7's consult radius, on real decodes — BY PATH.

    env/bin/python holo2/measure/or5_or7_census.py [--arms A,B,...]
                                                   [--rows N] [--quiet]

NOT A TEST and not collectable as one: no ``test_`` name, no pytest
fixtures, a ``__main__`` entry point, and it lives outside ``testpaths``.
Same standing as ``index_equivalence.py`` — it runs REAL decodes and
counts what they did, which is a measurement, not a unit.

It answers the two numbers H4-PLAN §4 item 4 owes, and it answers them on
ONE set of decodes, because both questions are about the same passes (the
verdicts' own law: "many execute the same things — run once, check
multiple things after the run").

OR-5 — THE PER-KEY BP CEILING UNDER RE-ARMING FRONTIERS
-------------------------------------------------------
M-3.5 measured the eager/phased half of OR-5 on toys and recorded that
the other half was not answerable there: *"a per-key attempt ceiling under
re-arming frontiers is about a decoder that FAILS and is retried; the toy
decoder either decides every bit or does not, so it never exercises a BP
budget."* The real chain does. A payload work key is re-armed whenever
its evidence collection gains a piece or its ``baselined`` set grows
(``solve.payload``: eligibility, not ordering), so one key can reach the
LDPC decoder several times over its lifetime — once per footing that
scanned it, once per baselined footing that failed, once per ppc two
distinct captures both reached. This driver counts the belief-propagation
iterations each of those attempts actually burned and sums them per key.

**THE OBSERVABILITY FINDING, recorded rather than worked around.** holo2
does NOT make the iteration count durable. ``tiles.TileAttempt.n_iters``
is transient by DESIGN §5.5, and what survives a fire is the SpendRecord's
outcome (``crc_passed`` / ``crc_failed`` / ``below_floor`` /
``already_certified``) plus the monotone ``exposure`` flag — the CRC
budget L5 cares about, not the iteration budget OR-5 asks for. v1, by
contrast, folds ``StageTally.bp_iterations`` into its durable
``SessionCounters`` per stage. So the count here is INTERCEPTED at
``solve.tiles.attempt_k_tile`` (driver-side, read-only, argument- and
result-preserving, exactly as ``record_placement_routes`` intercepts the
pull job) and attributed to the work key by wrapping
``RealPayloadWorker.run`` around it. Nothing in ``src`` changed to make
this measurable, and nothing in ``src`` can read the ITERATION count back
afterwards.

CORRECTED 2026-08-19, because H5 made the distinction load-bearing: the
spend row also carries ``attempts``, a monotone count per
``(work_id, route)`` that the fold maintains and the cache restores. So
the ATTEMPT ordinal was durable all along and is what the re-work aging
prices on (``engine.recipe.work_price``); the iteration budget is the
half that is not, and it stays the first prerequisite of any ceiling.
This harness is the aging's ACCEPTANCE instrument — the before/after it
produced is the OR-5 addendum in ``docs/MEASUREMENTS.md`` — and it was
repaired to run at all on the way there: it still imported
``solve.payload_h3bis``, which H4 W6 renamed to ``solve.payload``, so the
script had been unrunnable since that commit. Rename only; every number
it reports is computed exactly as before, which the before column proves
by reproducing the 2026-08-18 row (11,820 / 61 / 548) on the pre-change
tree.

OR-7 — THE CHAIN-HINT RADIUS, IN ITS CURRENT FORM
--------------------------------------------------
OR-7 was born as the push era's wake-amplification bucket question and got
its motivating measurement there (M-3.2 on toys: the DONE-GATE/sibling
subscription, whose own caveat says the chain radius is a different
dependency and must be measured separately). The pull model deleted the
durable hint outright, so there is no bucket left to size — what replaced
it is a FIRE-TIME query with two parameters, and those are what can be
measured now:

* the ratified DISTANCE (``place_job.hint_distance``): centre-to-centre
  cells at the consulting footing over the window stride, so an adjacent
  window scores exactly 1.0 and a colocated coarser-footing donor 0.0;
* the TRUNCATION (``CONSULT_KEEP`` = 8, and ``WIDE_ANCHORS`` = 8 at the
  wide tier): sort by that distance, keep 8, and let the caller subtract
  its tried set.

So the measurable question is: **at what distance were the offers that
were actually ACCEPTED, and did keeping only 8 ever starve a placement?**
Both are read off the passes: the driver reconstructs the UNTRUNCATED
consult beside the shipped one (an oracle, checked for faithfulness on
every single call — a reconstruction that has drifted proves nothing),
and identifies the accepted seed by counting ``pose_audit.local_search``
calls inside ``WindowJob._search``, whose loop returns on the first seed
that accepts.

THE ARMS (all serial, all ``--complete``, all seeded)
-----------------------------------------------------
* ``channel`` — run channel's page and render, parameter for parameter
  (c2-r0700, 8x8 tiles, the measured e032 anisotropic warp, 2% cell
  error), on the FINEST-ONLY reading set, which is the configuration
  ``verdicts/conftest.py`` decodes it under.
* ``banded`` — run banded's page and render (16% cell error over the
  right quarter, which kills the t=13 word code in those columns), on the
  DEFAULT reading set. THE OR-5 ARM: it is the only single-capture
  fixture where scans genuinely fail, so ``baselined`` footings appear
  and ``retry150`` descriptors are minted.
* ``two-capture`` — the banded page declared TWICE: same print seed, a
  different sensor draw (``_fixtures.render``'s print/noise split), which
  is run streaming's sheet-0 rescan shape transplanted onto a single
  sheet so it can be decoded SERIALLY. Two DISTINCT captures reach one
  ppc, so ``union`` descriptors become legal and reachable, and a key can
  be re-armed by an acquisition rather than only by its own failure. The
  pooled run streaming cannot be used for this: R9 commits in completion
  order, so its per-key attempt counts would be a race.

THE POOLED SECTION ROLLS PER (ARM, KEY), NOT PER KEY. All three arms
decode the SAME page, so ``tile/0/2/6/main`` exists in every one of them;
a roll that dropped the arm would sum three independent lifetimes into a
number no key ever spent. (The first cut of this driver did exactly that
and reported a 15,017-iteration "lifetime" that was three arms added
together. The arm rides every attempt row now.)

WHAT IT DOES NOT CLAIM. These are small synthetic pages under seeded
channel models; they bound the SHAPE of the two distributions and the
mechanism behind them, not a population. The real sheet's own census is
the echo chain's, and the recommended ceiling below is stated as a
headroom over an observed maximum, which is the only form a
gate-constants-vs-construction-floors argument can take from evidence
this size.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Self-locating, like ``./confetti.py``: neither package is pip-installed
# (env honesty), and a driver the operator runs BY PATH should not also
# demand a ``PYTHONPATH=`` prefix to find the tree it lives in.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE / "verdicts", _ROOT / "src", _ROOT / "holo2" / "src"):
    sys.path.insert(0, str(_path))

from _fixtures import (CHANNEL_ROTATION_DEG, CHANNEL_SCALE_YX,  # noqa: E402
                       build_page, render)

from holo2 import cli                                           # noqa: E402
from holo2.cli import real_providers                            # noqa: E402
from holo2.engine.recipe import RECIPE_V1, RECIPE_V1_FINEST     # noqa: E402
from holo2.solve import payload, place_job, pose_audit    # noqa: E402
from holo2.solve import tiles as tile_chain                     # noqa: E402
from holo2.solve.geometry import WINDOW_STEP_CELLS              # noqa: E402
from holo2.solve.place_job import (CONSULT_KEEP, Seed,          # noqa: E402
                                   WIDE_ANCHORS, WindowJob,
                                   hint_distance, window_centre_cells)
from holo2.solve.quarantine import is_quarantined               # noqa: E402
from holo2.solve.records import PoseRecord                      # noqa: E402
from holo2.solve.tilemap import StoreIndex                      # noqa: E402

#: A 1200-dpi capture of a 600-dpi print — the whole measure tree's
#: footing, and ``verdicts/conftest.py``'s own constant.
PX_PER_DOT = 2

#: run channel's arm, verbatim from ``verdicts/conftest.py`` (re-declared
#: rather than imported, following ``index_equivalence.py``: a pytest
#: ``conftest`` is not a module a by-path driver should import).
CHANNEL_FORMAT = "c2-k-r0700@8x8"
CHANNEL_NOISE = 2.0
CHANNEL_CELL_ERROR_RATE = 0.02

#: run banded's band, verbatim from ``verdicts/conftest.py``.
BAND_ERROR_RATE = 0.16
BAND_COLUMNS = (0.75, 1.0)
BAND_WARP: dict[str, Any] = dict(rotation_deg=0.3, pitch_scale=1.003,
                                 noise_sigma=2.0)

#: The rescan's sensor draw — run streaming's own second-scan seed, so the
#: two captures of the two-capture arm differ in the SENSOR and not in the
#: ink (the multi-scan law's whole subject: errors are print-correlated).
PRINT_SEED = 20260809
RESCAN_NOISE_SEED = 20260818

#: Snapshot cadence, from ``verdicts/conftest.py``. Small enough that a
#: run frames several times; irrelevant to every count here.
CADENCE = 32


# ------------------------------------------------------------- OR-5's census

class BpCensus:
    """Every ``attempt_k_tile`` call of a run, attributed to its work key.

    The attribution is the wrapping order: ``RealPayloadWorker.run``
    names the (key, route, scope) triple, the attempt runs inside it, so
    the innermost record can be bound to the outermost frame without the
    chain having to carry an identity it has no business knowing (DESIGN
    §5.5 keeps ``TileAttempt`` transient on purpose).
    """

    def __init__(self, arm: str = "?") -> None:
        #: WHICH DECODE these attempts belong to. Every arm here decodes
        #: the SAME page, so ``tile/0/2/6/main`` exists in all three — a
        #: per-key roll that did not carry the arm would SUM three
        #: independent lifetimes into one invented number.
        self.arm = arm
        #: One row per attempt that reached ``attempt_k_tile``.
        self.attempts: list[dict[str, Any]] = []
        #: Set while a payload worker is on the stack: its work key, its
        #: route, its scope and the (page, ty, tx) that key parses to —
        #: taken from the WORKER, which parsed it once at construction.
        self._current: tuple[str, str, str, tuple[int, int, int]] | None = None
        #: Attempts observed with no worker frame around them — a hole in
        #: the attribution, reported rather than silently dropped.
        self.unattributed = 0

    # -- reading it back ---------------------------------------------------

    @property
    def decoder_calls(self) -> list[dict[str, Any]]:
        """Attempts that actually ran BP (a below-floor attempt does not)."""
        return [row for row in self.attempts if row["ran_decoder"]]

    def per_key(self) -> dict[tuple[str, str], dict[str, Any]]:
        """One row per (ARM, work key): that key's whole lifetime, in
        iterations. Keyed on the arm as well, because one page decoded
        three ways is three lifetimes and not one."""
        rolled: dict[tuple[str, str], dict[str, Any]] = {}
        for row in self.attempts:
            entry = rolled.setdefault((row["arm"], row["key"]), {
                "iters": 0, "attempts": 0, "decoder_calls": 0,
                "below_floor": 0, "routes": Counter(), "certified": False,
                "max_single": 0})
            entry["iters"] += row["n_iters"]
            entry["attempts"] += 1
            entry["certified"] |= row["certified"]
            entry["max_single"] = max(entry["max_single"], row["n_iters"])
            if row["ran_decoder"]:
                entry["decoder_calls"] += 1
                # Only BP-RUNNING attempts are routed here: a below-floor
                # attempt refused before a decoder existed, so counting it
                # under a route would price work nobody did.
                entry["routes"][row["route"]] += 1
            else:
                entry["below_floor"] += 1
        return rolled


def install_bp_census(census: BpCensus) -> Any:
    """Wrap the payload worker and the tile chain. READ-ONLY, both."""
    worker_run = payload.RealPayloadWorker.run
    attempt = tile_chain.attempt_k_tile

    def wrapped_run(self: Any, view: Any, identity: Any,
                    progress: Any) -> Any:
        previous = census._current
        census._current = (str(self.key), self.route, self.scope,
                           tuple(self.address))
        try:
            return worker_run(self, view, identity, progress)
        finally:
            census._current = previous

    def wrapped_attempt(llr_cells: Any, spec: Any, address: Any,
                        stage: Any) -> Any:
        result = attempt(llr_cells, spec, address, stage)
        if census._current is None:
            census.unattributed += 1
            return result
        key, route, scope, worker_address = census._current
        assert worker_address == tuple(address), (
            f"attempt at {address} attributed to key {key}")
        assert route == stage.value, f"{route} attributed to {stage}"
        census.attempts.append({
            "arm": census.arm,
            "key": key, "route": route, "scope": scope,
            "n_iters": int(result.n_iters),
            "state": result.state.value,
            "ran_decoder": result.state is not
            tile_chain.AttemptState.BELOW_ATTEMPT_FLOOR,
            "certified": bool(result.certified),
            "n_informative": int(result.n_informative),
        })
        return result

    payload.RealPayloadWorker.run = wrapped_run
    tile_chain.attempt_k_tile = wrapped_attempt

    def undo() -> None:
        payload.RealPayloadWorker.run = worker_run
        tile_chain.attempt_k_tile = attempt

    return undo


# ------------------------------------------------------------- OR-7's census

def untruncated_consult(view: Any, plan: Any, row: Any, *,
                        wide: bool) -> tuple[Seed, ...]:
    """THE ORACLE: ``place_job.consult`` without its ``[:K]``.

    A source reconstruction, in the ``fit_phase_equivalence`` sense — the
    shipped expression minus exactly the clause under measurement. It is
    checked against the shipped answer on EVERY call (the shipped list
    must be this list's own prefix), because a reconstruction that has
    drifted from the code it reconstructs measures nothing.
    """
    here = window_centre_cells(plan.extent_cells)
    stride = float(WINDOW_STEP_CELLS)
    seeds: list[Seed] = []
    for anchor in place_job._anchor_plans(view, plan, wide=wide):
        distance = hint_distance(
            window_centre_cells(anchor.extent_cells), here, stride)
        for pose_id in view.poses_of_window(anchor.window_id):
            pose = view.record(pose_id)
            if not isinstance(pose, PoseRecord):
                continue
            if is_quarantined(pose):
                continue
            if pose.page not in row.page_domain:
                continue
            seeds.append(Seed(str(pose_id), pose.page, distance,
                              tuple(pose.native_affine)))
    seeds.sort(key=Seed.order_key)
    return tuple(seeds)


class ConsultCensus:
    """Every consult of a run: what it could see, kept, tried, accepted."""

    def __init__(self) -> None:
        #: One row per pass that reached the consult.
        self.rows: list[dict[str, Any]] = []
        #: Calls on which the oracle was checked against the shipped list.
        self.checked = 0
        #: Faithfulness failures — the oracle drifting from ``consult``.
        self.drift: list[str] = []
        self._shipped: tuple[Seed, ...] | None = None
        self._pending: dict[str, Any] | None = None
        self._in_search = False
        self._search_calls = 0


def install_consult_census(census: ConsultCensus) -> Any:
    """Wrap the consult, the seed step, the search and the job. READ-ONLY."""
    real_consult = place_job.consult
    real_seeds = WindowJob._seeds
    real_search = WindowJob._search
    real_run = WindowJob.run
    real_local = pose_audit.local_search

    def wrapped_consult(view: Any, plan: Any, row: Any, *,
                        wide: bool = False) -> tuple[Seed, ...]:
        shipped = real_consult(view, plan, row, wide=wide)
        census._shipped = shipped
        return shipped

    def wrapped_seeds(self: Any, view: Any) -> tuple[Seed, ...]:
        keep = WIDE_ANCHORS if self.wide else CONSULT_KEEP
        oracle = untruncated_consult(view, self.plan, self._row,
                                     wide=self.wide)
        census._shipped = None
        seeds = real_seeds(self, view)
        shipped = census._shipped
        if shipped is None:
            census.drift.append(
                f"{self.plan.window_id}: the consult was not called")
        else:
            census.checked += 1
            if tuple(oracle[:keep]) != tuple(shipped):
                census.drift.append(
                    f"{self.plan.window_id}: oracle prefix "
                    f"{[s.candidate_id for s in oracle[:keep]]} != shipped "
                    f"{[s.candidate_id for s in shipped]}")
        census._pending = {
            "window": str(self.plan.window_id),
            "wide": bool(self.wide),
            "visible": len(oracle),
            "kept": 0 if shipped is None else len(shipped),
            "keep_limit": keep,
            "truncated": 0 if shipped is None else max(
                0, len(oracle) - len(shipped)),
            "tried_before": len(self._tried),
            "offered": len(seeds),
            # The regional affine is not a consult offer: the wide tier
            # appends it after the truncation, so it must not be counted
            # against the radius.
            "regional_added": int(self.wide and any(
                seed.candidate_id.startswith(place_job.REGIONAL_SEED)
                for seed in seeds)),
            "visible_distances": [seed.distance for seed in oracle],
            "offered_distances": [seed.distance for seed in seeds],
            "accepted_distance": None,
            "accepted_rank": None,
            # R-B's regional affine is a fit over the whole region, not an
            # offer AT a distance (``Seed.distance`` is ``inf`` for it by
            # construction), so an acceptance of it is counted apart from
            # the radius rather than folded into it as a huge number.
            "accepted_regional": False,
            "searched": 0,
            "route": None,
            "outcome": None,
            "cold": self.cold,
        }
        return seeds

    def wrapped_local(*args: Any, **kwargs: Any) -> Any:
        outcome = real_local(*args, **kwargs)
        if census._in_search:
            census._search_calls += 1
        return outcome

    def wrapped_search(self: Any, patch: Any, frame: Any, seeds: Any,
                       budget: Any, progress: Any) -> Any:
        census._in_search, census._search_calls = True, 0
        try:
            address = real_search(self, patch, frame, seeds, budget, progress)
        finally:
            census._in_search = False
        row = census._pending
        if row is not None:
            row["searched"] = census._search_calls
            if address is not None:
                # ``_search`` returns on the FIRST seed that accepts, so
                # the accepted seed is the one the last call scored.
                index = census._search_calls - 1
                assert 0 <= index < len(seeds), (
                    f"{census._search_calls} searches over {len(seeds)} seeds")
                accepted = seeds[index]
                assert accepted.page == address[0], (
                    "the accepted seed's page is not the address's page")
                row["accepted_distance"] = float(accepted.distance)
                row["accepted_rank"] = index
                row["accepted_regional"] = accepted.candidate_id.startswith(
                    place_job.REGIONAL_SEED)
        return address

    def wrapped_job_run(self: Any, view: Any, identity: Any,
                        progress: Any) -> Any:
        census._pending = None
        result = real_run(self, view, identity, progress)
        row = census._pending
        if row is not None:
            row["route"] = self.route_taken
            row["outcome"] = result.outcome
            census.rows.append(row)
        census._pending = None
        return result

    place_job.consult = wrapped_consult
    pose_audit.local_search = wrapped_local
    WindowJob._seeds = wrapped_seeds
    WindowJob._search = wrapped_search
    WindowJob.run = wrapped_job_run

    def undo() -> None:
        place_job.consult = real_consult
        pose_audit.local_search = real_local
        WindowJob._seeds = real_seeds
        WindowJob._search = real_search
        WindowJob.run = real_run

    return undo


# ---------------------------------------------------------------- the arms

def arms(work: Path, names: tuple[str, ...]) -> list[dict[str, Any]]:
    """The decodes, built from ``verdicts/_fixtures.py``'s own builders.

    Renders are content-addressed by that module, so the channel and
    banded captures here are BYTE-IDENTICAL to the ones the verdicts
    decode — the same cache entry, not a re-rendering.
    """
    page = build_page(CHANNEL_FORMAT)
    built: list[dict[str, Any]] = []
    if "channel" in names:
        capture = render(page.dots, work / "channel.png",
                         px_per_dot=PX_PER_DOT, cell_dots=page.cell_dots,
                         rotation_deg=CHANNEL_ROTATION_DEG,
                         pitch_scale=CHANNEL_SCALE_YX,
                         noise_sigma=CHANNEL_NOISE,
                         cell_error_rate=CHANNEL_CELL_ERROR_RATE)
        built.append({"name": "channel", "row": page.row,
                      "scans": ((capture.path, capture.dpi),),
                      "recipe": RECIPE_V1_FINEST})
    banded = None
    if {"banded", "two-capture"} & set(names):
        banded = render(page.dots, work / "banded.png",
                        px_per_dot=PX_PER_DOT, cell_dots=page.cell_dots,
                        cell_error_rate=BAND_ERROR_RATE,
                        cell_error_band=BAND_COLUMNS, **BAND_WARP)
    if "banded" in names:
        assert banded is not None
        built.append({"name": "banded", "row": page.row,
                      "scans": ((banded.path, banded.dpi),),
                      "recipe": RECIPE_V1})
    if "two-capture" in names:
        assert banded is not None
        rescan = render(page.dots, work / "banded-rescan.png",
                        px_per_dot=PX_PER_DOT, cell_dots=page.cell_dots,
                        cell_error_rate=BAND_ERROR_RATE,
                        cell_error_band=BAND_COLUMNS,
                        print_seed=PRINT_SEED,
                        noise_seed=RESCAN_NOISE_SEED, **BAND_WARP)
        built.append({"name": "two-capture", "row": page.row,
                      "scans": ((banded.path, banded.dpi),
                                (rescan.path, rescan.dpi)),
                      "recipe": RECIPE_V1})
    return built


def run_decode(work: Path, arm: dict[str, Any]) -> tuple[Any, int]:
    """One SERIAL, ``--complete`` decode; returns its outcome and pose count."""
    state = work / f"state-{arm['name']}"
    request = cli.DecodeRequest(
        scans=arm["scans"], workers=1, diag_port=0, state_dir=state,
        output=work / f"recovered-{arm['name']}.bin", complete=True)
    outcome, _observer = cli.decode(
        request, arm["row"], real_providers(arm["row"], request.scans),
        recipe=arm["recipe"], fsync=False, snapshot_every=CADENCE)
    with cli.open_receiver(
            request, arm["row"], recipe=arm["recipe"],
            providers=real_providers(arm["row"], request.scans),
            source=cli.real_source(arm["row"], arm["recipe"]),
            fsync=False) as session:
        poses = len(StoreIndex.build(session.store).poses)
    return outcome, poses


# --------------------------------------------------------------- the report

def quantiles(values: list[float]) -> dict[str, float]:
    """max / p99 / median / mean, or zeros for an empty population.

    p99 is the NEAREST-RANK order statistic (``ceil(0.99 n)``), not an
    interpolation: with populations this size an interpolated quantile
    would invent a value no attempt ever produced, and a ceiling argued
    from an invented value is not an argument.
    """
    if not values:
        return {"n": 0, "max": 0.0, "p99": 0.0, "median": 0.0, "mean": 0.0}
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * 99 // 100))
    return {"n": len(ordered), "max": ordered[-1], "p99": ordered[rank - 1],
            "median": statistics.median(ordered),
            "mean": sum(ordered) / len(ordered)}


def _row(label: str, stats: dict[str, Any]) -> str:
    return (f"    {label:<22} n={stats['n']:<6d} max={stats['max']:<8.6g} "
            f"p99={stats['p99']:<8.6g} median={stats['median']:<8.6g} "
            f"mean={stats['mean']:.6g}")


def report_or5(name: str, census: BpCensus, rows: int) -> None:
    print(f"\n  OR-5 — BP iterations, arm '{name}'")
    calls = census.decoder_calls
    if not calls:
        print("    NO DECODER CALL AT ALL — this arm measures nothing for OR-5")
        return
    print(f"    attempts {len(census.attempts)} "
          f"({len(calls)} ran BP, "
          f"{len(census.attempts) - len(calls)} below the attempt floor"
          f"{f', {census.unattributed} unattributed' if census.unattributed else ''})")
    print("    PER ATTEMPT:")
    print(_row("all routes", quantiles([r["n_iters"] for r in calls])))
    for route in ("scan", "union", "retry150"):
        subset = [r["n_iters"] for r in calls if r["route"] == route]
        if subset:
            print(_row(f"route {route}", quantiles(subset)))
    by_outcome = Counter(r["state"] for r in calls)
    print(f"    outcomes: {dict(by_outcome)}")
    for state in sorted(by_outcome):
        subset = [r["n_iters"] for r in calls if r["state"] == state]
        print(_row(f"state {state}", quantiles(subset)))
    keyed = census.per_key()
    live = {key: entry for key, entry in keyed.items()
            if entry["decoder_calls"]}
    print(f"    PER KEY (lifetime), {len(live)} (arm, key) lifetimes "
          f"reached BP:")
    print(_row("iterations/key", quantiles(
        [float(entry["iters"]) for entry in live.values()])))
    print(_row("BP attempts/key", quantiles(
        [float(entry["decoder_calls"]) for entry in live.values()])))
    print(_row("max single/key", quantiles(
        [float(entry["max_single"]) for entry in live.values()])))
    # What BOUNDS a key's lifetime is how many DESCRIPTORS it can mint,
    # and that is data-dependent (one scan per footing with evidence, one
    # retry per baselined footing, one union per ppc two distinct captures
    # both reached) — which is precisely why the ceiling OR-5 asks for
    # cannot be derived and has to be measured.
    for route in ("scan", "union", "retry150"):
        counts = [float(entry["routes"].get(route, 0))
                  for entry in live.values() if entry["routes"].get(route)]
        if counts:
            print(_row(f"{route} attempts/key", quantiles(counts)))
    rearmed = {key: entry for key, entry in live.items()
               if entry["decoder_calls"] > 1}
    print(f"    RE-ARMED (more than one BP attempt): {len(rearmed)} "
          f"lifetimes of {len(live)}")
    if rearmed:
        print(_row("iterations/re-armed", quantiles(
            [float(entry["iters"]) for entry in rearmed.values()])))
        shapes = Counter(
            "+".join(f"{route}x{count}" for route, count
                     in sorted(entry["routes"].items()))
            for entry in rearmed.values())
        for shape, count in shapes.most_common(rows):
            print(f"      {count:>4d} lifetimes: {shape}")
    worst = sorted(live.items(), key=lambda item: -item[1]["iters"])[:rows]
    print("    the heaviest keys:")
    for (arm, key), entry in worst:
        print(f"      {entry['iters']:>6d} iters over "
              f"{entry['decoder_calls']} BP attempts "
              f"(+{entry['below_floor']} below floor) "
              f"({'certified' if entry['certified'] else 'OPEN'}) "
              f"{dict(entry['routes'])}  [{arm}] {key}")


def report_or7(name: str, census: ConsultCensus, rows: int) -> None:
    print(f"\n  OR-7 — consult radius, arm '{name}'")
    if census.drift:
        print(f"    ORACLE DRIFT ({len(census.drift)}): "
              f"{census.drift[0][:120]}")
    print(f"    passes with a consult {len(census.rows)} "
          f"({census.checked} faithfulness checks)")
    landed = [row for row in census.rows
              if row["accepted_distance"] is not None]
    regional = [row for row in landed if row["accepted_regional"]]
    accepted = [row for row in landed if not row["accepted_regional"]]
    print(f"    consult-accepted passes {len(landed)} "
          f"({len(accepted)} at a distance, {len(regional)} by R-B's "
          f"regional affine, which HAS no distance)")
    if accepted:
        print(_row("accepted distance",
                   quantiles([row["accepted_distance"] for row in accepted])))
        print(_row("accepted rank",
                   quantiles([float(row["accepted_rank"])
                              for row in accepted])))
        histogram = Counter(round(row["accepted_distance"], 4)
                            for row in accepted)
        print("    accepted-distance histogram (strides: passes):")
        for distance, count in sorted(histogram.items()):
            print(f"      {distance:>8.4f} : {count}")
    offered = [row for row in census.rows if row["offered"]]
    if offered:
        print(_row("offered/pass", quantiles(
            [float(row["offered"]) for row in offered])))
        print(_row("visible/pass", quantiles(
            [float(row["visible"]) for row in census.rows])))
        every = [distance for row in census.rows
                 for distance in row["offered_distances"]
                 if distance != float("inf")]
        print(_row("offered distance", quantiles(every)))
    # THE TWO TIERS SEPARATELY, because they truncate at different reaches:
    # the ring/donor consult sees a bounded neighbourhood (8 lattice
    # neighbours plus the coarser-footing windows covering this one), while
    # the WIDE consult sees every window of the region on every footing —
    # so it is the wide tier where ``WIDE_ANCHORS`` can actually bind, and a
    # census that pooled them would hide that.
    for label, subset in (("ring/donor",
                           [row for row in census.rows if not row["wide"]]),
                          ("wide",
                           [row for row in census.rows if row["wide"]])):
        if not subset:
            print(f"    tier {label}: NO PASS — this fixture never reached it")
            continue
        landed_here = [row for row in subset
                       if row["accepted_distance"] is not None
                       and not row["accepted_regional"]]
        print(f"    tier {label}: {len(subset)} passes, "
              f"{len(landed_here)} accepted at a distance, "
              f"{sum(1 for row in subset if row['truncated'])} truncated")
        print(_row(f"  {label} visible/pass", quantiles(
            [float(row["visible"]) for row in subset])))
        if landed_here:
            print(_row(f"  {label} accepted dist", quantiles(
                [row["accepted_distance"] for row in landed_here])))
    truncated = [row for row in census.rows if row["truncated"]]
    print(f"    TRUNCATION: {len(truncated)} of {len(census.rows)} passes saw "
          f"more than their keep limit "
          f"(max visible {max((row['visible'] for row in census.rows), default=0)}, "
          f"keep {CONSULT_KEEP}/{WIDE_ANCHORS})")
    if truncated:
        print(_row("dropped/pass", quantiles(
            [float(row["truncated"]) for row in truncated])))
        starved = [row for row in truncated
                   if row["accepted_distance"] is None
                   and row["route"] != "word" and row["route"] != "correlation"]
        print(f"    STARVED (truncated AND the pass reached no address at all): "
              f"{len(starved)}")
        for row in starved[:rows]:
            print(f"      {row['window']} wide={row['wide']} "
                  f"visible={row['visible']} kept={row['kept']} "
                  f"offered={row['offered']} outcome={row['outcome']}")
        beyond = [row for row in truncated
                  if row["accepted_distance"] is not None
                  and row["accepted_rank"] is not None
                  and row["accepted_rank"] >= row["keep_limit"] - 1]
        print(f"    accepted AT the truncation boundary (rank == keep-1): "
              f"{len(beyond)}")
    routes = Counter(row["route"] or "none" for row in census.rows)
    print(f"    pass routes: {dict(routes)}")


# ------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--arms", default="channel,banded,two-capture",
        help="comma-separated arm names to decode "
             "(channel, banded, two-capture; default: all three)")
    parser.add_argument(
        "--rows", type=int, default=8, metavar="N",
        help="how many rows each 'heaviest'/'starved' listing prints "
             "(default: 8)")
    parser.add_argument(
        "--quiet", action="store_true",
        help="omit the per-arm listings; print the summary tables only")
    args = parser.parse_args(argv)

    names = tuple(name.strip() for name in args.arms.split(",") if name.strip())
    unknown = set(names) - {"channel", "banded", "two-capture"}
    if unknown:
        parser.error(f"unknown arm(s): {', '.join(sorted(unknown))}")

    print("OR-5 / OR-7 CENSUS — real decodes, SERIAL, --complete, seeded.")
    print(f"  arms: {', '.join(names)}")
    print(f"  keep limits: CONSULT_KEEP={CONSULT_KEEP}, "
          f"WIDE_ANCHORS={WIDE_ANCHORS}")
    print(f"  BP max_iters: baseline={tile_chain.BASELINE_BP_MAX_ITERS}, "
          f"retry150={tile_chain.RETRY_BP_MAX_ITERS} — but ONE attempt's "
          f"structural cap is TWICE that "
          f"({2 * tile_chain.BASELINE_BP_MAX_ITERS} / "
          f"{2 * tile_chain.RETRY_BP_MAX_ITERS}): ``ldpc.decode`` runs the "
          f"normalized min-sum pass and, on syndrome failure, ONE exact "
          f"sum-product retry from the channel LLRs, and ``n_iters`` is "
          f"the sum over both.")

    failures: list[str] = []
    totals_bp = BpCensus("pooled")
    totals_consult = ConsultCensus()
    with tempfile.TemporaryDirectory(prefix="or5-or7-") as raw:
        work = Path(raw)
        built = arms(work, names)
        for arm in built:
            bp = BpCensus(arm["name"])
            consult_census = ConsultCensus()
            undo_bp = install_bp_census(bp)
            undo_consult = install_consult_census(consult_census)
            started = time.perf_counter()
            try:
                outcome, poses = run_decode(work, arm)
            finally:
                undo_consult()
                undo_bp()
            wall = time.perf_counter() - started
            print(f"\n  arm '{arm['name']}': {outcome.status}, "
                  f"{outcome.certified} certified, {poses} poses, "
                  f"{outcome.commits} commits, {outcome.fires} fires, "
                  f"{wall:.1f} s")
            if not args.quiet:
                report_or5(arm["name"], bp, args.rows)
                report_or7(arm["name"], consult_census, args.rows)
            if consult_census.drift:
                failures.append(
                    f"arm '{arm['name']}': the consult oracle drifted "
                    f"({len(consult_census.drift)} calls)")
            if bp.unattributed:
                failures.append(
                    f"arm '{arm['name']}': {bp.unattributed} attempts had no "
                    "payload worker frame around them")
            totals_bp.attempts.extend(bp.attempts)
            totals_consult.rows.extend(consult_census.rows)
            totals_consult.checked += consult_census.checked

    print("\n" + "=" * 72)
    print("POOLED OVER EVERY ARM")
    print("=" * 72)
    report_or5("pooled", totals_bp, args.rows)
    report_or7("pooled", totals_consult, args.rows)

    calls = totals_bp.decoder_calls
    if not calls:
        failures.append("NOTHING COUNTED — no attempt reached the decoder")
    keyed = {key: entry for key, entry in totals_bp.per_key().items()
             if entry["decoder_calls"]}
    if keyed and max(entry["decoder_calls"] for entry in keyed.values()) < 2:
        failures.append(
            "NO KEY WAS EVER RE-ARMED — the arms do not exercise OR-5's "
            "question at all")
    if not any(row["accepted_distance"] is not None
               for row in totals_consult.rows):
        failures.append(
            "NO CONSULT OFFER WAS EVER ACCEPTED — OR-7 measured nothing")

    if keyed:
        observed = max(entry["iters"] for entry in keyed.values())
        deepest = max(entry["decoder_calls"] for entry in keyed.values())
        print(f"\n  OR-5 headline: the heaviest key burned {observed} BP "
              f"iterations over its whole lifetime, across at most "
              f"{deepest} BP attempts; the heaviest SINGLE attempt burned "
              f"{max(row['n_iters'] for row in calls)} of the "
              f"{2 * tile_chain.RETRY_BP_MAX_ITERS} a retry150 attempt may "
              f"structurally spend.")
    if totals_consult.rows:
        accepted = [row["accepted_distance"] for row in totals_consult.rows
                    if row["accepted_distance"] is not None
                    and not row["accepted_regional"]]
        if accepted:
            print(f"  OR-7 headline: {len(accepted)} accepted offers, "
                  f"distances {min(accepted):.4f}..{max(accepted):.4f} "
                  f"strides; truncation bit on "
                  f"{sum(1 for row in totals_consult.rows if row['truncated'])}"
                  f" of {len(totals_consult.rows)} passes.")

    if failures:
        print("\nFAILED:")
        for line in failures:
            print(f"  {line}")
        return 1
    print("\nCENSUS COMPLETE — oracle faithful on every consult, every "
          "attempt attributed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
