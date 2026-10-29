#!/usr/bin/env python
"""What the per-plane lane comparison measured, and what survives it.

    cd <repo>
    PYTHONPATH=src:. env/bin/python -m measure.page_field.lane_gauge \\
        --fields build/page-field/H/fields.json \\
        --lane-fields <evidence>/page-field/H7-mirror/plane_fields.npz \\
        --dpi af580c3cf54f=1200 --dpi d792e00a45e7=1200 \\
        --dpi 68c16fcbf29b=2400 --dpi 4fddac74cef1=2400 \\
        --dpi f6920518c82a=4800 --dpi 9c022bd308ae=4800 \\
        --dpi f642cab0416c=4800

Three tables over one page's archived per-lane fields and the page field
solved from the same facts:

 1. the PER-PLANE lane-vs-page numbers W5 reported, RETRACTED at W6 —
    two gauges, since the page field drops the word-ink common mode and
    an archived single-plane fit had nothing subtracted at all (the
    pre-W2 ``plane_relative`` only fired where all three planes fitted);
 2. the GAUGE-FREE pairs the corpus carries, scored the way
    ``compare.py --lane-fields`` scores them, so the correction is
    legible beside what it corrects;
 3. LANE AGAINST LANE on one plane, which touches no page field and is
    where ``PAGE-FIELD-DESIGN.md`` §7's "sign-inconsistent between
    footings" reading comes from.

The npz carries no dpi, so table 3's footings are DECLARED: ``--dpi``
per capture, and a lane whose capture is undeclared is refused rather
than silently binned.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from holo.receiver.format import identity

from . import products
from .compare import LANE_PAIRS, spearman


def _lanes(path: Path, page_index: int) -> tuple[dict, ...]:
    with np.load(path) as held:
        return tuple(
            {"capture": str(held["capture_id"][i]),
             "level_index": int(held["level_index"][i]),
             "plane": identity.CMY_PLANE_ORDER[int(held["plane"][i])],
             "delta_dots_xy": np.asarray(held["delta_dots_xy"][i]),
             "support": np.asarray(held["support"][i])}
            for i in range(held["page"].shape[0])
            if int(held["page"][i]) == page_index)


def _page_grids(page: dict) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    return {entry["plane_name"]: (np.asarray(entry["delta_dots_xy"]),
                                  np.asarray(entry["support"]) > 0)
            for entry in page["planes"]}


def _differential(grids: dict, pair: tuple[str, str]):
    if not set(pair) <= set(grids):
        return None
    (left, left_live), (right, right_live) = grids[pair[0]], grids[pair[1]]
    return left - right, left_live & right_live


def _score(ours, our_live, theirs, their_live) -> str:
    live = our_live & their_live
    gap = ours - theirs
    return (f"{int(live.sum()):>5} tiles  "
            f"med|d| {np.median(np.linalg.norm(gap, axis=-1)[live]):.4f}  "
            f"med|dx| {np.median(np.abs(gap[..., 0])[live]):.4f}  "
            f"spearman "
            f"{spearman(products.column_profile(ours, our_live), products.column_profile(theirs, their_live)):+.4f}")


def report(fields: Path, lane_fields: Path, page_index: int,
           dpi_of: dict[str, int]) -> None:
    page = next(entry for entry in json.loads(fields.read_text())["pages"]
                if entry["page"] == page_index)
    mine = _page_grids(page)
    lanes = _lanes(lane_fields, page_index)
    undeclared = sorted({lane["capture"][:12] for lane in lanes}
                        - set(dpi_of))
    if undeclared:
        raise SystemExit(
            f"no --dpi declared for {', '.join(undeclared)}: table 3 bins "
            "lanes by footing and cannot guess one")

    print("== 1. per-plane lane vs page field (RETRACTED: two gauges) ==")
    for lane in lanes:
        ours, our_live = mine[lane["plane"]]
        print(f"  {lane['capture'][:12]} l{lane['level_index']} "
              f"{lane['plane']} {dpi_of[lane['capture'][:12]]:>4}dpi  "
              + _score(ours, our_live, lane["delta_dots_xy"],
                       lane["support"] > 0))

    print("\n== 2. the gauge-free pairs: lane vs page field ==")
    by_lane: dict[tuple[str, int], dict] = {}
    for lane in lanes:
        by_lane.setdefault((lane["capture"], lane["level_index"]), {})[
            lane["plane"]] = (lane["delta_dots_xy"], lane["support"] > 0)
    for pair in LANE_PAIRS:
        ours = _differential(mine, pair)
        for (capture, level), grids in sorted(by_lane.items()):
            theirs = _differential(grids, pair)
            if ours is None or theirs is None:
                continue
            print(f"  {capture[:12]} l{level} {pair[0]}-{pair[1]} "
                  f"{dpi_of[capture[:12]]:>4}dpi  "
                  + _score(*ours, *theirs))

    print("\n== 3. lane against lane, plane C, no page field involved ==")
    on_c = [lane for lane in lanes if lane["plane"] == "C"]
    for index, left in enumerate(on_c):
        for right in on_c[index + 1:]:
            left_dpi, right_dpi = (dpi_of[left["capture"][:12]],
                                   dpi_of[right["capture"][:12]])
            if left["capture"] == right["capture"]:
                continue
            tag = (f"same dpi ({left_dpi})" if left_dpi == right_dpi
                   else f"{left_dpi} vs {right_dpi}")
            print(f"  {left['capture'][:12]} l{left['level_index']} vs "
                  f"{right['capture'][:12]} l{right['level_index']}  "
                  f"{tag:<16} "
                  + _score(left["delta_dots_xy"], left["support"] > 0,
                           right["delta_dots_xy"], right["support"] > 0))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fields", type=Path, required=True,
                        help="estimate.py's fields.json")
    parser.add_argument("--lane-fields", dest="lane_fields", type=Path,
                        required=True, help="extract.py's plane_fields.npz")
    parser.add_argument("--page", type=int, default=0)
    parser.add_argument("--dpi", action="append", default=[],
                        metavar="CAPTURE_PREFIX=DPI",
                        help="the footing of one capture, repeatable")
    args = parser.parse_args()
    dpi_of = {}
    for declaration in args.dpi:
        prefix, _, value = declaration.partition("=")
        dpi_of[prefix] = int(value)
    report(args.fields, args.lane_fields, args.page, dpi_of)


if __name__ == "__main__":
    main()
