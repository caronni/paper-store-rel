"""Chain length, composed drift, and the lost-tile join — per archived run.

One streaming pass over each ``events.jsonl[.xz]`` and, where one
stands beside it, one read of ``facts.npz``.  Nothing is decoded.

    PYTHONPATH=src:. <python> -m measure.refine_chains.census \\
        --evidence-root <evidence> --out build/refine-chains
    PYTHONPATH=src:. <python> -m measure.refine_chains.census --run sheet-I \\
        --evidence-root <evidence> --out build/refine-chains

The report is written to ``--out``/census.json and printed as the
tables ``README.md`` carries.
"""
from __future__ import annotations

import argparse
import json
import lzma
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import numpy as np

from measure import _evidence

from . import _sources

TILE_CELLS = 16 * 4
LANES = ("refine", "refine.color")

WindowKey = tuple[str, int, int, tuple[int, int, int, int]]
Address = tuple[int, int, int, str]


@dataclass
class Pose:
    """One accepted placement, as `PoseCommitted` carries it."""
    route: str
    page: int
    mismatch: float
    affine: tuple[float, ...]
    page_origin_yx: tuple[int, int]
    rot_k: int
    shape_yx: tuple[int, int]


@dataclass
class RunFacts:
    """Everything one pass over a stream collects."""
    format_id: str = ""
    stream_ids: tuple[str, ...] = ()
    captures: int = 0
    workers: int = 0
    poses: dict[WindowKey, list[Pose]] = field(default_factory=dict)
    fires: Counter = field(default_factory=Counter)
    adoptions: dict[str, Counter] = field(default_factory=dict)
    certified: set[Address] = field(default_factory=set)
    touched: set[Address] = field(default_factory=set)
    events: int = 0
    payload_sha256: str | None = None


def _rows(path: Path) -> Iterator[dict]:
    opener = lzma.open if path.suffix == ".xz" else open
    with opener(path, "rt") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def _window_key(subject: object) -> WindowKey | None:
    if not isinstance(subject, list) or len(subject) != 4:
        return None
    capture, level, region, extent = subject
    if not isinstance(extent, list) or len(extent) != 4:
        return None
    return (str(capture), int(level), int(region),
            (int(extent[0]), int(extent[1]), int(extent[2]),
             int(extent[3])))


def read_stream(path: Path) -> RunFacts:
    facts = RunFacts()
    for lane in LANES:
        facts.adoptions[lane] = Counter()
    for row in _rows(path):
        facts.events += 1
        kind = row.get("type")
        if kind == "RunOpen":
            facts.format_id = str(row.get("format_id", ""))
            facts.stream_ids = tuple(row.get("stream_ids") or ())
            facts.captures = int(row.get("n_captures") or 0)
            facts.workers = int(row.get("workers") or 0)
        elif kind == "RunDone":
            facts.payload_sha256 = row.get("payload_sha256")
        elif kind == "PoseCommitted":
            key = (str(row["capture"]), int(row["level_index"]),
                   int(row["region_index"]),
                   tuple(int(one) for one in row["extent_cells"]))
            facts.poses.setdefault(key, []).append(Pose(
                route=str(row.get("route", "")), page=int(row["page"]),
                mismatch=float(row.get("mismatch", 0.0)),
                affine=tuple(float(one) for one in row["native_affine"]),
                page_origin_yx=tuple(int(one)
                                     for one in row["page_origin_yx"]),
                rot_k=int(row.get("rot_k", 0)),
                shape_yx=tuple(int(one) for one in row.get("shape_yx",
                                                           (0, 0)))))
        elif kind == "TileOutcome":
            address = (int(row["page"]), int(row["ty"]), int(row["tx"]),
                       str(row["stream_id"]))
            facts.touched.add(address)
            if row.get("result") == "certified":
                facts.certified.add(address)
        elif kind == "JobDone":
            plugin = str(row.get("plugin", ""))
            if plugin not in LANES:
                continue
            key = _window_key(row.get("subject"))
            if key is None:
                continue
            facts.fires[plugin] += 1
            if int(row.get("n_poses") or 0) > 0:
                facts.adoptions[plugin][key] += 1
    return facts


def read_placements(path: Path) -> dict[WindowKey, tuple[float, ...]]:
    """The final standing native affine per window, from a snapshot."""
    import sys

    root = str(_sources.WORKTREE)
    if root not in sys.path:
        sys.path.insert(0, root)
    from holo.receiver import data, snapshot

    standing: dict[WindowKey, tuple[float, ...]] = {}
    for fact in snapshot.read(path):
        if isinstance(fact, data.Placement):
            standing[fact.window_id] = tuple(
                float(term) for term in fact.native_affine)
    return standing


def _matrix(affine: tuple[float, ...]) -> np.ndarray:
    return np.asarray(affine, np.float64).reshape(2, 3)


def _angle_deg(affine: tuple[float, ...]) -> float:
    linear = _matrix(affine)[:, :2]
    return float(np.degrees(np.arctan2(linear[0, 1], linear[1, 1])))


def _pitch_px(affine: tuple[float, ...]) -> float:
    linear = _matrix(affine)[:, :2]
    return 0.5 * (float(np.hypot(*linear[:, 0]))
                  + float(np.hypot(*linear[:, 1])))


def _box_cells(pose: Pose) -> tuple[int, int, int, int]:
    """The window's page-cell box: origin y, x and extent y, x."""
    height, width = pose.shape_yx
    if pose.rot_k % 2:
        height, width = width, height
    return (pose.page_origin_yx[0], pose.page_origin_yx[1],
            max(int(height), 1), max(int(width), 1))


def _probe_cells(pose: Pose) -> np.ndarray:
    oy, ox, height, width = _box_cells(pose)
    return np.asarray(
        [(oy, ox), (oy, ox + width - 1), (oy + height - 1, ox),
         (oy + height - 1, ox + width - 1),
         (oy + height / 2.0, ox + width / 2.0)], np.float64)


def _apply(affine: tuple[float, ...], cells_yx: np.ndarray) -> np.ndarray:
    matrix = _matrix(affine)
    return (cells_yx + 0.5) @ matrix[:, :2].T + matrix[:, 2]


def drift(pose: Pose, final: tuple[float, ...]) -> tuple[float, float]:
    """Composed (translation in cells, rotation in degrees)."""
    cells = _probe_cells(pose)
    moved = _apply(final, cells) - _apply(pose.affine, cells)
    span = float(np.max(np.hypot(moved[:, 0], moved[:, 1])))
    return span / _pitch_px(pose.affine), (_angle_deg(final)
                                           - _angle_deg(pose.affine))


def tiles_of(pose: Pose) -> set[tuple[int, int, int]]:
    """The tiles the window's page-cell box touches.

    An over-approximation of the audited-cell reach `refine.reach_tiles`
    computes: the box is what the event stream carries, and it is the
    same over-approximation for every window, chained or not.
    """
    oy, ox, height, width = _box_cells(pose)
    return {(pose.page, ty, tx)
            for ty in range(oy // TILE_CELLS,
                            (oy + height - 1) // TILE_CELLS + 1)
            for tx in range(ox // TILE_CELLS,
                            (ox + width - 1) // TILE_CELLS + 1)}


def _quantiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    rows = np.asarray(values, np.float64)
    return {"n": int(rows.size), "median": float(np.median(rows)),
            "p90": float(np.quantile(rows, 0.9)),
            "max": float(np.max(np.abs(rows)))}


def standing_base_pose(poses: list[Pose]) -> Pose:
    """The accepted placement a chain departs from.

    `place` is the only writer of `PoseCommitted` and it writes one per
    committed placement, adopted or not; the store keeps the best
    mismatch and first-wins on a tie (`placement_ordinal`), so that is
    the pose the first revision is fitted from.
    """
    return min(enumerate(poses),
               key=lambda row: (row[1].mismatch, row[0]))[1]


def census(run: _sources.Run) -> dict:
    facts = read_stream(run.events)
    adoptions: Counter = Counter()
    for lane in LANES:
        adoptions.update(facts.adoptions[lane])
    histogram = Counter(min(count, 3) for count in adoptions.values())
    report: dict = {
        "run": run.name, "volume": run.volume, "note": run.note,
        "events": facts.events, "format_id": facts.format_id,
        "captures": facts.captures, "workers": facts.workers,
        "payload_sha256": facts.payload_sha256,
        "placed_windows": len(facts.poses),
        "fires": dict(facts.fires),
        "adopting_windows": len(adoptions),
        "adoptions_total": int(sum(adoptions.values())),
        "chain_1": int(histogram.get(1, 0)),
        "chain_2": int(histogram.get(2, 0)),
        "chain_3plus": int(histogram.get(3, 0)),
        "chain_max": int(max(adoptions.values(), default=0)),
        "certified": len(facts.certified),
        "touched": len(facts.touched),
        "facts_npz": str(run.facts) if run.facts else None,
    }
    if run.facts is not None:
        standing = read_placements(run.facts)
        chained: list[float] = []
        chained_deg: list[float] = []
        once: list[float] = []
        once_deg: list[float] = []
        missing = 0
        for key, count in adoptions.items():
            final = standing.get(key)
            poses = facts.poses.get(key)
            if final is None or not poses:
                missing += 1
                continue
            cells, degrees = drift(standing_base_pose(poses), final)
            (chained if count > 1 else once).append(cells)
            (chained_deg if count > 1 else once_deg).append(degrees)
        report["drift"] = {
            "unmatched_windows": missing,
            "once_cells": _quantiles(once), "once_deg": _quantiles(once_deg),
            "chained_cells": _quantiles(chained),
            "chained_deg": _quantiles(chained_deg)}
    report["lost"] = _lost_join(facts, adoptions)
    return report


def _lost_join(facts: RunFacts, adoptions: Counter) -> dict:
    """Certified share of the addresses each window class covers.

    A tile is assigned the HIGHEST class among the windows that cover
    it, so `chained` reads "a chained window had a hand in this tile".
    """
    classes = {"chained": 2, "revised": 1, "plain": 0}
    rank: dict[tuple[int, int, int], int] = {}
    for key, poses in facts.poses.items():
        level = min(adoptions.get(key, 0), 2)
        for tile in tiles_of(standing_base_pose(poses)):
            if rank.get(tile, -1) < level:
                rank[tile] = level
    streams = facts.stream_ids or ("main",)
    out: dict = {}
    for name, level in classes.items():
        tiles = [tile for tile, value in rank.items() if value == level]
        addresses = [(page, ty, tx, stream) for page, ty, tx in tiles
                     for stream in streams]
        touched = [one for one in addresses if one in facts.touched]
        won = [one for one in touched if one in facts.certified]
        out[name] = {
            "tiles": len(tiles), "addresses_touched": len(touched),
            "certified": len(won),
            "lost_rate": (1.0 - len(won) / len(touched)) if touched else None}
    plain = out["plain"]["lost_rate"]
    chained = out["chained"]["lost_rate"]
    out["chained_over_plain"] = (
        chained / plain if plain not in (None, 0.0) and chained is not None
        else None)
    return out


def _table(reports: list[dict]) -> str:
    lines = ["", "## chains", "",
             "| run | events | placed | fires | adoptions | refused | "
             "adopting | 1 | 2 | 3+ | longest |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in reports:
        fires = sum(row["fires"].values())
        refused = (f"{100.0 * (1.0 - row['adoptions_total'] / fires):.1f}%"
                   if fires else "—")
        lines.append(
            f"| {row['run']} | {row['events']} | {row['placed_windows']} | "
            f"{fires} | {row['adoptions_total']} | {refused} | "
            f"{row['adopting_windows']} | "
            f"{row['chain_1']} | {row['chain_2']} | {row['chain_3plus']} | "
            f"{row['chain_max']} |")
    lines += ["", "## composed drift, accepted placement to final pose", "",
              "| run | class | n | median cells | p90 cells | max cells | "
              "max deg |", "|---|---|---:|---:|---:|---:|---:|"]
    for row in reports:
        drifts = row.get("drift")
        if not drifts:
            continue
        for name in ("once", "chained"):
            cells = drifts[f"{name}_cells"]
            degrees = drifts[f"{name}_deg"]
            if not cells:
                continue
            lines.append(
                f"| {row['run']} | {name} | {cells['n']} | "
                f"{cells['median']:.4f} | {cells['p90']:.4f} | "
                f"{cells['max']:.4f} | {degrees['max']:.5f} |")
    lines += ["", "## lost-tile join", "",
              "| run | class | tiles | addresses | certified | lost rate |",
              "|---|---|---:|---:|---:|---:|"]
    for row in reports:
        for name in ("chained", "revised", "plain"):
            cell = row["lost"][name]
            rate = cell["lost_rate"]
            lines.append(
                f"| {row['run']} | {name} | {cell['tiles']} | "
                f"{cell['addresses_touched']} | {cell['certified']} | "
                f"{'—' if rate is None else f'{rate:.4f}'} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", default=None,
                        help="census only these runs (repeatable)")
    _evidence.add_argument(parser)
    parser.add_argument("--out", type=Path, required=True,
                        help="directory census.json and census.md land in")
    args = parser.parse_args(argv)
    root = _evidence.resolve(args.evidence_root, tool="refine_chains")
    roster = _sources.roster(root)
    if not roster:
        raise _evidence.withdrawn(
            *(str(root / path) for path in _sources.WITHDRAWN),
            tool="refine_chains",
            why="tier delete: holo3 event journals and fact snapshots "
                "excluded by rule; nothing in the record rebuilds them")
    runs = [run for run in roster
            if args.run is None or run.name in args.run]
    if not runs:
        print("no archived run matched")
        return 2
    reports = []
    for run in runs:
        report = census(run)
        reports.append(report)
        print(f"{run.name:16s} events {report['events']:>9d} "
              f"adopting {report['adopting_windows']:>5d} "
              f"chains2+ {report['chain_2'] + report['chain_3plus']:>4d}")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "census.json").write_text(
        json.dumps(reports, indent=2, sort_keys=True, default=_plain))
    (args.out / "census.md").write_text(_table(reports) + "\n")
    print(f"\nwrote {args.out / 'census.json'} and census.md")
    print(_table(reports))
    return 0


def _plain(value: object) -> object:
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    raise TypeError(f"cannot serialise {type(value).__name__}")


if __name__ == "__main__":
    raise SystemExit(main())
