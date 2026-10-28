#!/usr/bin/env python
"""Done-gate savings — the W5 measurement (RULINGS I7, 2026-08-23).

    env/bin/python holo2/measure/done_gate_savings.py \\
        --state e029=scratch/holo2-catchup/real/parity/h2-e029 \\
        --state xerox=scratch/holo2-catchup/real/parity/h2-xerox \\
        --out scratch/holo2-catchup/real/done-gate.md

NOT A TEST and not collectable as one — the same standing as
``tile_differential.py``, ``rf1_resume.py`` and ``parity_k.py``
(``holo2/measure/README.md``). READ-ONLY: it opens a finished holo2
state directory (``tile_differential.open_h2_store`` — ``Store.open``
directly, never ``cli.open_receiver``) and counts what is already
durable. Nothing is decoded, nothing is written.

WHAT THIS ANSWERS, and in WHOSE TERMS. ``docs/DONE-GEOMETRY.md`` §8a
measured v1's e029 harvest (2026-08-05, `holo` git ancestor) at **719 of
1,479 committed placements (48.6%) pixel-gated**, with the m00 completion
tail at **85-90% gateable** — and that number is itself a SIMULATED
counterfactual, not a realized rate: v1 never built the gate, so §8a's
harness re-derives, per placement, whether its extent WOULD have been
fully done ("every approximation biases AGAINST gating", §8a). holo2's
number below is the OPPOSITE kind of quantity: a working, deployed gate's
REALIZED retirements. The two are not commensurable as a ratio (see the
rendering note below) — a gate that works necessarily drives the realized
share down, because a window it catches never reaches the population v1
simulated over.

holo2 has TWO door-exit sites for "this window's extent is already fully
done", and this driver can only see one of them:

* ``place_job.py:606-608`` — a ``PlaceWindowJob`` that already fired
  discovers ``plane.window_is_done(plan)`` and calls ``self._retire(...,
  "done_covered")``, which writes a durable ``WindowRecord`` (status
  ``RETIRED``, reason ``"done_covered"``). This is the ONLY site this
  driver counts.
* ``place_sched.py:478-480`` — the scheduler's own admission door
  (``_Scheduler._consider``) checks ``view.window_is_done(plan)`` BEFORE
  a ``_Slot`` (and therefore a job) is ever created, and on a hit sets
  ``self._exited[plan.window_id] = "done_covered"`` and returns. Per its
  own docstring (:441-443): "a done-covered window ... is never created,
  never posed and never woken." ``_exited`` is an in-memory dict
  (``_Scheduler.__init__``); NOTHING converts a door-exit into a durable
  ``WindowRecord``. This is almost certainly the PRIMARY site by volume
  — a window plan whose extent is already done at admission time never
  becomes a job at all — and it is completely invisible to a census over
  a finished ``Store``.

So the counts below are **committed placements = every durable
``WindowRecord``** — a window that fired ``PlaceWindowJob.run`` and
reached a terminal outcome — which is NOT the direct analog of v1's
"placements" column, because v1's ladder had no admission-time gate at
all (the gate was unbuilt) while holo2's most common gate exit leaves no
record to count. It carries the SAME limitation W1 named for the reverse
direction: a window that never reaches a terminal outcome (goes dormant
and is never re-offered again) also leaves no record. So this driver's
denominator is a LOWER BOUND on "windows this run touched" for TWO
independent reasons, not one, and the gated share computed from it is a
LOWER BOUND on the gate's real activity, not "the gate's share".

**The off-census population, bounded from what the state DOES expose.**
A window plan's FULL extent (``WINDOW_CELLS`` x ``WINDOW_CELLS``,
``holo2.solve.geometry``) is laid out identically at every rung of one
region's lattice (one region per footing on both real captures here), so
the finer rungs' full-extent record count is a floor on how many
full-extent plans the coarsest rung also had — anything short of that
floor at the coarsest rung is plans that resolved at the door and left
no record. This driver reports that floor per report (``unattributed``
in the per-rung table) alongside the recorded ``gated`` count; on e029
the floor is 44 at rung 2/1 against 45 recorded gate hits at that
rung — a population the SAME ORDER as the census this driver can see,
sitting entirely outside it. Subdivision children (``child_window_plans``,
a different, smaller extent) are reported as their own line since they
have no such floor to compare against (a region's subdivision demand is
not uniform across rungs).

The rest of this driver's terms, unchanged by the above:

* **per-rung breakdown** groups by ``WindowRecord.footing_id``'s ppc
  suffix (``capture.ingest.footing_id_for``: ``f"{short}:{num}/{den}"``)
  — the closest durable analog to v1's per-LEVEL table (l00 2ppc, l01
  4ppc, ...), since footing IS the coarse-to-native rung ladder
  (``capture/scale_space.py::auto_ppc_levels``) in both trees, even
  though holo2 runs the rungs as PRICED work, not phased passes.
* **the tail** has no phase boundary to key on (no m00, no barrier), so
  it is defined POSITIONALLY: ``StoreIndex.windows`` iterates in
  FIRST-WRITE order (``tilemap.py`` choice 8 — the same guarantee W3's
  ``live_poses`` relies on, and exact here because a window key is
  written EXACTLY ONCE, ``records.py``'s "OUTCOME ONLY" ruling, so
  first-write order IS the window's one and only commit position). This
  driver reports the gated share by DECILE of that commit order, plus
  the last 10/20/30% as three fixed cuts — a positional proxy for v1's
  phase-based tail, named as a proxy and not asserted to be the same
  thing. See the module-level finding recorded in
  ``scratch/holo2-catchup/real/done-gate.md`` for what it actually shows
  on the two real sheets (concentration is real and it IS in the last
  decile, but the recorded magnitude is a lower bound below v1's
  85-90%, for the same off-census reason).

WHAT THIS DOES NOT ANSWER. Whether a `done_covered` retirement actually
SAVED wall-clock or worker time (no attribution/timing harness here —
DONE-GEOMETRY's own doctrine: "counts are the currency"); whether the
theoretical total window POPULATION (including windows this run never
touched) would change the share (unknowable from a finished state alone
— it would need the scheduler's own plan enumeration, which this
read-only census does not reconstruct); and whether the v1 vintage this
compares against is representative (it is the SAME vintage confound W4
named — v1's 48.6%/85-90% is 2026-08-05's ``rung-major-v2-r-lanes``
scheduler segment, and this driver makes no attempt to re-derive it).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# Self-locating, like every other by-path driver here (``confetti.py``'s
# own reason): neither package is pip-installed, and an operator running
# this by path should not also have to spell a PYTHONPATH.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent.parent
for _path in (_HERE, _ROOT / "src", _ROOT / "holo2" / "src"):
    _str = str(_path)
    if _str not in sys.path:
        sys.path.insert(0, _str)

import tile_differential                                        # noqa: E402

from holo2.solve import StoreIndex                               # noqa: E402
from holo2.solve.geometry import WINDOW_CELLS                    # noqa: E402
from holo2.solve.records import WindowRecord, WindowStatus       # noqa: E402

#: The one outcome string the gate uses (``place_job.py:608``,
#: ``place_sched.py:479``) — neither site exports it as a constant, so
#: this driver names it once rather than repeat the literal.
DONE_GATE_REASON = "done_covered"

#: v1's e029 census (``docs/DONE-GEOMETRY.md`` §8a, measured 2026-08-05,
#: scheduler segment ``rung-major-v2-r-lanes``) — the number this driver
#: measures holo2 against. Quoted, not re-derived.
V1_CENSUS_TOTAL = 1_479
V1_CENSUS_GATED = 719
V1_CENSUS_SHARE = V1_CENSUS_GATED / V1_CENSUS_TOTAL       # 0.4862...
V1_CENSUS_TAIL_LOW = 0.85
V1_CENSUS_TAIL_HIGH = 0.90


@dataclass(frozen=True)
class RungGate:
    """One footing's window population, split full-extent vs child.

    ``full_*`` counts windows at the plan's laid-out extent
    (``WINDOW_CELLS`` x ``WINDOW_CELLS``); ``child_*`` counts subdivision
    children (``child_window_plans`` — a different, smaller extent, no
    lineage field to key on, classified by size alone). ``total``/
    ``placed``/``gated``/``other_retired`` are the two summed, kept for
    anything that wants the un-split view. ``unattributed`` is the
    off-census floor for THIS rung's full-extent population (see the
    module docstring): 0 unless this rung's recorded full-extent count
    falls short of the max recorded full-extent count over all rungs of
    the same report.
    """

    ppc: str                     # e.g. "2/1" — the footing's rung
    total: int
    placed: int
    gated: int
    other_retired: int
    other_reasons: tuple[tuple[str, int], ...]
    full_total: int
    full_placed: int
    full_gated: int
    child_total: int
    child_placed: int
    child_gated: int
    unattributed: int = 0


@dataclass(frozen=True)
class DecileGate:
    decile: int                  # 0..9, over commit order
    total: int
    gated: int


@dataclass(frozen=True)
class TailCut:
    fraction: float              # 0.1, 0.2, 0.3
    total: int
    gated: int


@dataclass(frozen=True)
class DoneGateReport:
    label: str
    state_dir: Path
    total_windows: int
    placed: int
    gated: int
    other_retired: int
    other_reasons: tuple[tuple[str, int], ...]
    by_rung: tuple[RungGate, ...]
    by_decile: tuple[DecileGate, ...]
    tail_cuts: tuple[TailCut, ...]
    certified: int
    open_tiles: int

    @property
    def gated_share(self) -> float:
        return self.gated / self.total_windows if self.total_windows else 0.0

    @property
    def unattributed_floor(self) -> int:
        """Sum of the per-rung off-census floors (see the module
        docstring and :class:`RungGate`) — plans that resolved at
        ``place_sched.py:478-480``'s admission door and left no
        ``WindowRecord``, recoverable only as a per-rung LOWER BOUND
        from the finer rungs' recorded full-extent counts."""
        return sum(rung.unattributed for rung in self.by_rung)


def _ppc_sort_key(ppc: str) -> float:
    num, den = ppc.split("/")
    return int(num) / int(den)


def build_report(store, label: str, state_dir: Path) -> DoneGateReport:
    """One pass over the finished store's window population.

    ``StoreIndex.windows`` is built by the SAME first-write walk
    ``StoreIndex.build`` uses for ``live_poses`` (``tilemap.py`` choice
    8: the pass walks ``store.records()`` in commit order and every dict
    it builds along the way inherits that order because nothing re-sorts
    it before returning) — so ``index.windows.items()`` is commit order
    for free, no separate journal replay needed. A window key is written
    EXACTLY ONCE (``records.py``'s v5 "OUTCOME ONLY" ruling, enforced by
    ``WindowRecord.__post_init__``), so this driver's decile/tail split
    over that iteration is the window's own one and only commit position
    — not an approximation the way it would be for a record type (like
    ``TileRecord``) that is written many times before its final value.
    """
    index = StoreIndex.build(store)
    items: list[tuple[object, WindowRecord]] = list(index.windows.items())
    n = len(items)

    placed = 0
    gated = 0
    other_reasons: dict[str, int] = {}
    rungs: dict[str, dict[str, object]] = {}

    def _bucket(ppc: str) -> dict[str, object]:
        return rungs.setdefault(ppc, {
            "total": 0, "placed": 0, "gated": 0, "other_retired": 0,
            "other_reasons": {},
            "full_total": 0, "full_placed": 0, "full_gated": 0,
            "child_total": 0, "child_placed": 0, "child_gated": 0})

    decile_total = [0] * 10
    decile_gated = [0] * 10

    for i, (_key, record) in enumerate(items):
        ppc = record.footing_id.split(":")[-1]
        bucket = _bucket(ppc)
        bucket["total"] += 1
        y0, x0, y1, x1 = record.extent_cells
        is_full = (y1 - y0) == WINDOW_CELLS and (x1 - x0) == WINDOW_CELLS
        size_prefix = "full" if is_full else "child"
        decile = min(9, i * 10 // n) if n else 0
        decile_total[decile] += 1
        if record.status is WindowStatus.ACTIVE:
            placed += 1
            bucket["placed"] += 1
            bucket[f"{size_prefix}_placed"] += 1
            bucket[f"{size_prefix}_total"] += 1
            continue
        # RETIRED: __post_init__ guarantees retired_reason is not None.
        reason = record.retired_reason
        assert reason is not None
        bucket[f"{size_prefix}_total"] += 1
        if reason == DONE_GATE_REASON:
            gated += 1
            bucket["gated"] += 1
            bucket[f"{size_prefix}_gated"] += 1
            decile_gated[decile] += 1
        else:
            other_reasons[reason] = other_reasons.get(reason, 0) + 1
            bucket["other_retired"] += 1
            bucket_reasons = bucket["other_reasons"]
            assert isinstance(bucket_reasons, dict)
            bucket_reasons[reason] = bucket_reasons.get(reason, 0) + 1

    # The off-census floor (module docstring): the max recorded
    # full-extent count over all rungs of THIS report is a floor on how
    # many full-extent plans every rung had (one region's lattice lays
    # the same full-extent grid at every rung), so a rung short of that
    # floor has that many plans that resolved at the door
    # (``place_sched.py:478-480``) and left no ``WindowRecord``.
    full_floor = max((int(b["full_total"]) for b in rungs.values()), default=0)

    by_rung = tuple(
        RungGate(ppc=ppc, total=int(b["total"]), placed=int(b["placed"]),
                 gated=int(b["gated"]), other_retired=int(b["other_retired"]),
                 other_reasons=tuple(sorted(b["other_reasons"].items())),  # type: ignore[union-attr]
                 full_total=int(b["full_total"]), full_placed=int(b["full_placed"]),
                 full_gated=int(b["full_gated"]), child_total=int(b["child_total"]),
                 child_placed=int(b["child_placed"]), child_gated=int(b["child_gated"]),
                 unattributed=max(0, full_floor - int(b["full_total"])))
        for ppc, b in sorted(rungs.items(), key=lambda kv: _ppc_sort_key(kv[0])))

    by_decile = tuple(
        DecileGate(decile=d, total=decile_total[d], gated=decile_gated[d])
        for d in range(10))

    tail_cuts = []
    for frac in (0.1, 0.2, 0.3):
        cut = int(n * (1 - frac))
        tail = items[cut:]
        tail_gated = sum(
            1 for _k, r in tail
            if r.status is WindowStatus.RETIRED
            and r.retired_reason == DONE_GATE_REASON)
        tail_cuts.append(TailCut(fraction=frac, total=len(tail),
                                 gated=tail_gated))

    return DoneGateReport(
        label=label, state_dir=state_dir, total_windows=n, placed=placed,
        gated=gated, other_retired=sum(other_reasons.values()),
        other_reasons=tuple(sorted(other_reasons.items())),
        by_rung=by_rung, by_decile=by_decile, tail_cuts=tuple(tail_cuts),
        certified=index.certified, open_tiles=len(index.open_tiles))


def run(state_dir: Path, label: str) -> DoneGateReport:
    with tile_differential.open_h2_store(state_dir) as store:
        return build_report(store, label, state_dir)


# -- rendering ---------------------------------------------------------

def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({n / d * 100:.1f}%)" if d else f"{n}/0 (n/a)"


def render_report(reports: Sequence[DoneGateReport]) -> str:
    lines = ["# Done-gate savings — W5 (RULINGS I7, 2026-08-23)", ""]
    lines.append(
        "v1's own census (`docs/DONE-GEOMETRY.md` §8a, e029, "
        f"2026-08-05, scheduler `rung-major-v2-r-lanes`): "
        f"**{V1_CENSUS_GATED} of {V1_CENSUS_TOTAL} committed placements "
        f"({V1_CENSUS_SHARE * 100:.1f}%) pixel-gated**; the m00 "
        f"completion tail **{V1_CENSUS_TAIL_LOW * 100:.0f}-"
        f"{V1_CENSUS_TAIL_HIGH * 100:.0f}% gateable** — and that number "
        "is a SIMULATED counterfactual over a receiver that had no "
        "gate, not a realized rate (module docstring). Everything below "
        "is holo2's DEPLOYED gate, read from a finished `--complete` "
        "state, in the terms the module docstring defines. **The two "
        "are not a ratio of savings** — do not divide one by the "
        "other; a working gate drives its own realized share DOWN "
        "relative to what a no-gate simulation would find, because a "
        "window it catches never reaches the population being counted.")
    lines.append("")
    lines.append(
        "| sheet | committed placements (recorded) | placed | "
        "pixel-gated (recorded) | gated share (lower bound) | "
        "off-census floor, same mechanism |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in reports:
        lines.append(
            f"| {r.label} | {r.total_windows} | {r.placed} | {r.gated} | "
            f"{r.gated_share * 100:.1f}% | +{r.unattributed_floor} "
            "(place_sched.py:478-480, no WindowRecord) |")
    lines.append("")

    for r in reports:
        lines.append(f"## {r.label}")
        lines.append("")
        lines.append(
            f"State: `{r.state_dir}`. Certified tiles: {r.certified}. "
            f"Open (uncertified) tile keys: {r.open_tiles}.")
        lines.append("")
        lines.append(
            f"Committed placements: **{r.total_windows}** "
            f"(placed {r.placed}, retired {r.total_windows - r.placed}). "
            f"Pixel-gated (`done_covered`): **{_pct(r.gated, r.total_windows)}**.")
        if r.other_reasons:
            reasons = ", ".join(f"`{k}`: {v}" for k, v in r.other_reasons)
            lines.append(
                f"Other retirement reasons ({r.other_retired} total): "
                f"{reasons}.")
        else:
            lines.append(
                "No retirement reason other than `done_covered` was "
                "observed on this state.")
        lines.append("")

        lines.append("### Per rung (footing ppc — the level analog)")
        lines.append("")
        lines.append(
            "Full-extent (`WINDOW_CELLS`) and subdivision-child windows "
            "are DIFFERENT populations (a child has no lineage field, "
            "classified by extent size alone) and are reported "
            "separately rather than pooled into one denominator. "
            "`unattributed` is the off-census floor for the full-extent "
            "row only (see the module docstring) — plans the same size "
            "as every other rung's full-extent population that this "
            "rung is short of, which resolved at the scheduler's "
            "admission door (`place_sched.py:478-480`) and left no "
            "durable record; 0 means no deficit was detected, not that "
            "none occurred.")
        lines.append("")
        lines.append(
            "| ppc | population | recorded | placed | gated | "
            "gated share | unattributed floor |")
        lines.append("|---|---|---:|---:|---:|---:|---:|")
        for rung in r.by_rung:
            lines.append(
                f"| {rung.ppc} | full-extent | {rung.full_total} | "
                f"{rung.full_placed} | {rung.full_gated} | "
                f"{_pct(rung.full_gated, rung.full_total)} | "
                f"{'+' + str(rung.unattributed) if rung.unattributed else '0'} |")
            if rung.child_total:
                lines.append(
                    f"| {rung.ppc} | subdivision child | {rung.child_total} | "
                    f"{rung.child_placed} | {rung.child_gated} | "
                    f"{_pct(rung.child_gated, rung.child_total)} | n/a |")
        lines.append("")
        lines.append(
            f"Sum of unattributed floors, this sheet: "
            f"**+{r.unattributed_floor}** windows the same order of "
            "magnitude as the recorded gated count "
            f"({r.gated}) — a population this driver can bound but not "
            "attribute individually, entirely outside the summary "
            "table above.")
        lines.append("")

        lines.append(
            "### Tail (positional — commit-order decile, no phase "
            "boundary exists to key on)")
        lines.append("")
        lines.append("| decile of commit order | placements | gated | gated share |")
        lines.append("|---:|---:|---:|---:|")
        for dec in r.by_decile:
            lines.append(
                f"| {dec.decile} | {dec.total} | {dec.gated} | "
                f"{_pct(dec.gated, dec.total)} |")
        lines.append("")
        lines.append("| tail cut | placements | gated | gated share |")
        lines.append("|---|---:|---:|---:|")
        for cut in r.tail_cuts:
            lines.append(
                f"| last {int(cut.fraction * 100)}% | {cut.total} | "
                f"{cut.gated} | {_pct(cut.gated, cut.total)} |")
        lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--state", action="append", required=True, metavar="LABEL=PATH",
        help="a finished holo2 state, e.g. e029=scratch/.../h2-e029; "
             "repeatable")
    parser.add_argument("--out", type=Path, default=None,
                        help="write the markdown report here (also "
                             "printed to stdout)")
    args = parser.parse_args(argv)

    reports = []
    for spec in args.state:
        label, _, path_str = spec.partition("=")
        if not path_str:
            parser.error(f"--state {spec!r} is not LABEL=PATH")
        reports.append(run(Path(path_str), label))

    text = render_report(reports)
    print(text)
    if args.out is not None:
        args.out.write_text(text, encoding="utf-8")
        print(f"\nwrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
