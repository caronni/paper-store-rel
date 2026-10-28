#!/usr/bin/env python
"""Parity: does the production row reproduce the experiment's ladder?

    PYTHONPATH=. env/bin/python -m measure.planek_parity --marginal
    PYTHONPATH=. env/bin/python -m measure.planek_parity --case H-d --all

THE QUESTION, and it is the only one that matters about this row.
`measure/yask` measured, on sheet H's own crops and against a
seven-capture production harvest of the same sheet, an additive ladder
ending in **32 yellow tiles the harvest did not have, zero wrong**.
`holo3/plugins/plane_k` is that experiment as a scheduled row.  This
instrument runs THE PRODUCTION ROW'S OWN ASSEMBLY over the experiment's
own crops, with the experiment's own archived poses and the same
production certificate baseline, and reports its adds beside the
experiment's.

WHAT IS SHARED WITH THE EXPERIMENT, deliberately and by import: the
crops (`yask._cases`), the archived harvest's poses and certificate map,
the ground truth and its reconstruction gate (`yask._truth`,
`crop_parity._gt`), and the add/wrong accounting.  What is NOT shared is
the read: every certificate here comes out of `plane_k.lane_read` and
`plane_k.attempt_components`, unchanged production code, reached through
a read-only shim over the archived poses.

WHAT A DELTA MEANS.  A small one was expected and named in advance: the
row's assembly is not the harness's script, and its eligibility is the
scheduler's rather than the case's.  A large one is a defect in the row,
not a fact about the sheet.

MEASURED 2026-08-31, and the delta is zero on both arms:

    arm                      certs  GT-exact  WRONG  adds   experiment
    one capture (2400a)         47        47      0    15     47 / 15
    seven-capture union        116       116      0    32    116 / 32

per crop, certificates one capture / union, adds one capture / union:
    H-m1   9 / 12   adds 1 / 0     H-m4   6 / 14   adds 3 / 1
    H-m2  13 / 25   adds 8 / 9     H-d    5 / 24   adds 1 / 7
    H-m3   5 / 28   adds 0 / 12    H-c    9 / 13   adds 2 / 3

H-m1 reproduces even the experiment's one recorded ANOMALY — the union
gains three certificates there and loses the single add — which is a
stronger statement than the totals: the two runs agree tile by tile,
including where the union rule costs a tile.

Nothing here is production and nothing here can mint a certificate that
the codec did not: every attempt goes through `tiles.attempt_tile`, and
every certificate is ALSO checked against the emitted payload.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from holo3.data import Placement
from holo3.plugins import color_region, plane_k

from measure.yask import _cases, _paths, _read
from measure.yask import harness as yask_harness

#: The six crops the experiment's headline was counted over: the four
#: marginal blocks chosen by rule, plus H-d and H-c.  The three cut
#: around fully dead bands contribute nothing to either arm and are
#: available with --case.
MARGINAL_CASES: tuple[str, ...] = ("H-m1", "H-m2", "H-m3", "H-m4", "H-d",
                                   "H-c")

#: The measured ladder this instrument is compared against
#: (measure/yask/README.md §1), over exactly those six crops.
YASK_ONE_CAPTURE_CERTS: int = 47
YASK_ONE_CAPTURE_ADDS: int = 15
YASK_UNION_CERTS: int = 116
YASK_UNION_ADDS: int = 32

Y_PLANE: int = 2
PAGE: int = 0


# --------------------------------------------------------------------
# the archived harvest, as something production code can read
# --------------------------------------------------------------------


@dataclass(frozen=True)
class PoseShim:
    """The three accessors `color_region.region_window` actually uses.

    Poses come from the production harvest's own `PoseCommitted` events,
    so the geometry under test is the one that run committed and not a
    crop's re-derivation of it.  The archive does not record the
    support-masked local cell list, so the full window rectangle is
    used: a SUPERSET of what the run sampled, whose extra cells are
    dropped by `region_window`'s own page test.  It can cost coverage,
    never invent it.
    """

    row: object
    placements: dict

    def placement(self, wid) -> Placement:
        return self.placements[wid]

    def level(self, capture_id: str, level_index: int):
        return _Level()


@dataclass(frozen=True)
class _Level:
    #: the archived poses are read at the capture's finest level, whose
    #: `native_affine` is already a native-pixel map
    scale: Fraction = Fraction(1)


def placement_of(pose: _read.Pose, patch_ordinal: int) -> Placement:
    height, width = pose.shape_yx_cells
    grid_y, grid_x = np.meshgrid(np.arange(height, dtype=np.int64),
                                 np.arange(width, dtype=np.int64),
                                 indexing="ij")
    local = np.stack((grid_y.ravel(), grid_x.ravel()), axis=1)
    return Placement(
        window_id=pose.window_id, capture_id=pose.capture_id,
        level_index=pose.level_index, region_index=pose.region_index,
        patch_ordinal=patch_ordinal, page=pose.page, rot_k=pose.rot_k,
        page_origin_yx=pose.page_origin_yx,
        native_affine=pose.native_affine, pitch_px=pose.pitch_px,
        route=pose.route, local_cells_yx=local)


@dataclass(frozen=True)
class MemmapRaster:
    """A `PlaneRaster`-shaped view of one channel of a memmapped scan.

    The row calls `.open()` on whatever it is handed, so one channel of
    a read-only memmap is all a `LanePlan` needs.  No sheet is ever
    loaded: every pixel the row reads is a window off this map.
    """

    array: object

    def open(self):
        return self.array


def lane_plan_of(row: object, poses: list[_read.Pose], planes,
                 capture_id: str, level_index: int) -> plane_k.LanePlan:
    placements = {pose.window_id: placement_of(pose, ordinal)
                  for ordinal, pose in enumerate(poses)}
    shim = PoseShim(row=row, placements=placements)
    windows = tuple(color_region.region_window(shim, pose.window_id)
                    for pose in poses)
    return plane_k.LanePlan(
        lane=(capture_id, level_index), windows=windows,
        placements=tuple(placements[pose.window_id] for pose in poses),
        region_indices=tuple(pose.region_index for pose in poses),
        planes=tuple(MemmapRaster(plane) for plane in planes),
        field=None)


# --------------------------------------------------------------------
# one case
# --------------------------------------------------------------------


def crop_rect(case: _cases.Case) -> tuple[int, int, int, int]:
    ty0, ty1, tx0, tx1 = case.crop_tiles
    return (ty0 * _read.TILE, ty1 * _read.TILE,
            tx0 * _read.TILE, tx1 * _read.TILE)


def case_positions(case: _cases.Case) -> list[tuple[int, int]]:
    ty0, ty1, tx0, tx1 = case.crop_tiles
    return [(ty, tx) for ty in range(ty0, ty1) for tx in range(tx0, tx1)]


def run_case(case: _cases.Case, which: str, stream_id: str) -> dict:
    import tifffile

    from measure.crop_parity import _gt as gt_module

    started = time.perf_counter()
    context = yask_harness.load_context(case)
    sheet = context["sheet"]
    row, geometry = context["row"], context["geometry"]
    certmap, truth = context["certmap"], context["truth"]
    certificates = context["certificates"]
    positions = case_positions(case)
    rect = crop_rect(case)

    reads: list[plane_k.LaneRead] = []
    lanes: list[dict] = []
    handles = []
    try:
        for label, path, sha, _unused in yask_harness.capture_lanes(
                sheet, case, which):
            level = yask_harness.finest_level(context["poses"], sha)
            if level is None:
                lanes.append({"capture": label,
                              "reason": "no_archived_pose"})
                continue
            poses_all = _read.poses_from_events(context["poses"], sha, level)
            poses = _read.poses_overlapping(poses_all, rect)
            if not poses:
                lanes.append({"capture": label, "reason": "no_pose_over_case"})
                continue
            handle = tifffile.memmap(str(path), mode="r")
            handles.append(handle)
            planes = (handle[..., 0], handle[..., 1], handle[..., 2])
            plan = lane_plan_of(row, poses, planes, sha, level)
            read = plane_k.lane_read(row, geometry, plan, certificates,
                                     Y_PLANE)
            record = {"capture": label, "level_index": level,
                      "poses": len(poses)}
            if read is None:
                record["reason"] = "lane_read_refused"
                lanes.append(record)
                continue
            record["mix"] = {
                "accepted": bool(read.mix.accepted),
                "reason": read.mix.reason,
                "n_full_rows": int(read.mix.n_full_rows),
                "coef_channel_by_plane": [
                    [round(float(value), 3) for value in channel]
                    for channel in read.mix.coef],
                "plane_snr": [round(value, 3)
                              for value in read.mix.plane_snr()]}
            record["windows"] = len(read.rows)
            record["offsets"] = [
                {"patch": patch, "source": source, "shift_dots": shift}
                for patch, source, shift in read.offsets]
            lanes.append(record)
            reads.append(read)
        outcome = attempt_positions(reads, row, geometry, positions,
                                    stream_id)
    finally:
        for handle in handles:
            del handle
    return {
        "case": case.case_id, "sheet": sheet.key, "captures": which,
        "format_ref": sheet.format_ref, "note": case.note,
        "crop_tiles": list(case.crop_tiles),
        "gt_gate": context["gt_gate"],
        "production": census(certmap, positions),
        "lanes": lanes,
        "decode": tally(outcome, truth, certmap, gt_module, stream_id),
        "wall_seconds": round(time.perf_counter() - started, 1),
    }


def attempt_positions(reads, row, geometry, positions, stream_id) -> dict:
    """The production attempt, tile by tile, over the lanes' reads.

    `plane_k.cut_of` and `plane_k.attempt_components` are the row's own:
    several lanes are the ordinary multi-capture union, summed by
    `tiles._combine` exactly as the receiver sums them.
    """
    results: dict = {}
    for ty, tx in positions:
        components = []
        for read in reads:
            cut = plane_k.cut_of(read, row, geometry, PAGE, ty, tx)
            if cut is not None:
                components.append(cut)
        facts, _events = plane_k.attempt_components(
            row, geometry, components, stream_id)
        results[(ty, tx)] = facts
    return results


def census(certmap, positions) -> dict:
    out = {"tiles": len(positions), "C": 0, "M": 0, "Y": 0, "all_three": 0}
    for position in positions:
        streams = certmap.get(position, frozenset())
        for stream in ("C", "M", "Y"):
            out[stream] += int(stream in streams)
        out["all_three"] += int(len(streams) == 3)
    return out


def tally(outcome, truth, certmap, gt_module, stream_id: str) -> dict:
    """Certificates, ground-truth verdicts, and the additive count.

    An ADD is a certificate that (a) matches the emitted payload exactly
    and (b) sits on a tile the production harvest left uncertified in
    this stream.  A certificate that does NOT match ground truth is
    WRONG whatever else is true of it.
    """
    detail = []
    n_wrong = 0
    n_adds = 0
    outcomes: dict[str, int] = {}
    for (ty, tx), facts in sorted(outcome.items()):
        certificate = None
        for fact in facts:
            if hasattr(fact, "outcome"):
                outcomes[fact.outcome] = outcomes.get(fact.outcome, 0) + 1
            if hasattr(fact, "user_bits"):
                certificate = fact
        if not facts:
            outcomes["no_cut"] = outcomes.get("no_cut", 0) + 1
        if certificate is None:
            continue
        matched, n_bad = gt_module.check_bits(
            truth, (PAGE, ty, tx, stream_id), certificate.user_bits)
        production_has = stream_id in certmap.get((ty, tx), frozenset())
        if not matched:
            n_wrong += 1
        elif not production_has:
            n_adds += 1
        detail.append({"tile": [ty, tx], "gt_match": bool(matched),
                       "gt_bits_differing": int(n_bad),
                       "production_has": production_has,
                       "counts_as_add": bool(matched and not production_has)})
    return {"certificates": len(detail),
            "gt_exact": sum(1 for entry in detail if entry["gt_match"]),
            "wrong": n_wrong, "adds": n_adds, "outcomes": outcomes,
            "detail": detail}


# --------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------


def render(reports: list[dict], which: str) -> list[str]:
    lines = ["# planek parity — the production row on the experiment's crops",
             "",
             "| case | tiles | production Y | certs | GT-exact | WRONG | "
             "**adds** |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    totals = {"tiles": 0, "Y": 0, "certificates": 0, "gt_exact": 0,
              "wrong": 0, "adds": 0}
    for report in reports:
        decode = report["decode"]
        production = report["production"]
        totals["tiles"] += production["tiles"]
        totals["Y"] += production["Y"]
        for key in ("certificates", "gt_exact", "wrong", "adds"):
            totals[key] += decode[key]
        lines.append(
            f"| {report['case']} | {production['tiles']} | "
            f"{production['Y']} | {decode['certificates']} | "
            f"{decode['gt_exact']} | {decode['wrong']} | "
            f"**{decode['adds']}** |")
    lines.append(
        f"| **total** | {totals['tiles']} | {totals['Y']} | "
        f"{totals['certificates']} | {totals['gt_exact']} | "
        f"{totals['wrong']} | **{totals['adds']}** |")
    lines.append("")
    cases = {report["case"] for report in reports}
    if cases == set(MARGINAL_CASES):
        experiment = ((YASK_UNION_CERTS, YASK_UNION_ADDS, "A2, seven captures")
                      if which == "all"
                      else (YASK_ONE_CAPTURE_CERTS, YASK_ONE_CAPTURE_ADDS,
                            "A1, one capture"))
        lines.append(f"Experiment ({experiment[2]}) over the same six "
                     f"crops: {experiment[0]} certificates, "
                     f"{experiment[1]} adds.")
        lines.append(f"This row: {totals['certificates']} certificates, "
                     f"{totals['adds']} adds "
                     f"({totals['adds'] - experiment[1]:+d}).")
        lines.append("")
    for report in reports:
        lines.append(f"## {report['case']} — {report['note']}")
        lines.append("")
        production = report["production"]
        lines.append(
            f"crop tiles {report['crop_tiles']}; production certified "
            f"C {production['C']}/{production['tiles']}, "
            f"M {production['M']}/{production['tiles']}, "
            f"**Y {production['Y']}/{production['tiles']}**; ground-truth "
            f"gate {report['gt_gate']['tiles']} tiles / "
            f"{report['gt_gate']['cells']} cells exact; "
            f"{report['wall_seconds']} s.")
        lines.append("")
        for lane in report["lanes"]:
            if "mix" not in lane:
                lines.append(f"* {lane['capture']}: "
                             f"{lane.get('reason', 'no read')}")
                continue
            blind = [entry["shift_dots"] for entry in lane["offsets"]
                     if entry["source"] == "blind"]
            mean_shift = (0.0 if not blind
                          else sum(blind) / float(len(blind)))
            lines.append(
                f"* {lane['capture']} (level {lane['level_index']}): "
                f"{lane['poses']} poses, {lane['windows']} calibrated "
                f"windows, plane SNR {lane['mix']['plane_snr']}, "
                f"mean blind offset {mean_shift:+.3f} dots")
        lines.append("")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", action="append", default=[],
                        help="case id from measure.yask._cases")
    parser.add_argument("--marginal", action="store_true",
                        help=f"the six crops the experiment's headline was "
                             f"counted over: {', '.join(MARGINAL_CASES)}")
    parser.add_argument("--all-captures", action="store_true",
                        help="every capture of the sheet (the union arm; "
                             "minutes per case, not seconds)")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    _paths.install_src()
    wanted = list(MARGINAL_CASES) if args.marginal else list(args.case)
    if not wanted:
        raise SystemExit("planek_parity: name --case ids or pass --marginal")
    unknown = [name for name in wanted if name not in _cases.CASES_BY_ID]
    if unknown:
        raise SystemExit(f"planek_parity: unknown case(s) {unknown}; "
                         f"declared: {sorted(_cases.CASES_BY_ID)}")
    which = "all" if args.all_captures else "declared"
    reports = []
    for name in wanted:
        print(f"planek_parity: {name} ({which}) …", file=sys.stderr,
              flush=True)
        report = run_case(_cases.CASES_BY_ID[name], which, "Y")
        reports.append(report)
        decode = report["decode"]
        print(f"  certs {decode['certificates']} adds {decode['adds']} "
              f"wrong {decode['wrong']} ({report['wall_seconds']} s)",
              file=sys.stderr, flush=True)

    out_dir = args.out or (_paths.WORKTREE / "scratch/planek/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = "-".join(wanted)[:80] + f"--{which}"
    (out_dir / f"planek-parity-{stamp}.json").write_text(
        json.dumps(reports, indent=1, default=str) + "\n", encoding="utf-8")
    text = "\n".join(render(reports, which)) + "\n"
    (out_dir / f"planek-parity-{stamp}.md").write_text(text,
                                                       encoding="utf-8")
    print(text)
    wrong = sum(report["decode"]["wrong"] for report in reports)
    if wrong:
        print(f"planek_parity: {wrong} WRONG certificate(s) — correctness "
              f"failure", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
