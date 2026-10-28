#!/usr/bin/env python
"""The Y-as-K battery: one case, five declared arms, one verdict.

    PYTHONPATH=. env/bin/python -m measure.yask.harness --case H-a
    PYTHONPATH=. env/bin/python -m measure.yask.harness --case all
    PYTHONPATH=. env/bin/python -m measure.yask.harness --case H-a \\
        --arms A0,A2 --shift-sweep

THE PRE-REGISTERED BAR, stated once and never moved: the experiment is
USEFUL if at least one Y-stream certificate passes the full codec gate
AND matches the emitted payload bit for bit, on a tile where the
production harvest left Y uncertified, with ZERO wrong certificates
anywhere. Everything else in the report is context for that one line.

THE ARMS (declared here, not chosen after the fact):

===  ==========================================================
A0   nominal — one capture, sibling-subtracted yellow, no shift.
A1   A0 plus a per-window sampling offset chosen BLIND on the
     window's own held-out yellow labels (dust-anchored).
A2   A1 unioned over every capture of the sheet, the way the
     receiver unions captures.
C0   control — the raw blue channel, one capture, no shift.
C1   control — the C/M-annihilating projection without per-cell
     sibling subtraction, one capture, no shift.
===  ==========================================================

and, reported apart and never counted toward the bar:

===  ==========================================================
X1   ORACLE — the per-window offset chosen on the emitted field
     instead of on labels. An upper bound on what a perfect
     registration estimator could buy this composition.
===  ==========================================================

WHAT IS BLIND AND WHAT IS NOT. Poses, addresses and sibling plane
values are ordinary receiver knowledge: the production harvest placed
and addressed this page through C and M, and a certified tile's cell
values follow from its certificate. Sibling values here are taken from
the emitted payload AT ADDRESSES THE PRODUCTION HARVEST CERTIFIED,
which is what that run's own certificates hold. The emitted CELL FIELD
is used for measurement only — d', cell error rate, and the X1 oracle —
and never on a path that can mint a certificate.

TWO ABLATIONS, deliberately independent, because a certified neighbour
does two different jobs here and the battery has to say which one
matters: ``--siblings furniture`` restricts what the MIXING MODEL may
use as regressors and what the per-cell subtraction may cancel;
``--labels furniture`` restricts what the CALIBRATION may use as
yellow labels. Either one alone answers a different question.
"""
from __future__ import annotations

import argparse
import json
import lzma
import sys
import time
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from . import _cases, _paths, _read, _spectral, _truth

ARMS = ("A0", "A1", "A2", "C0", "C1", "X1", "N0")
HW_DPI = 600


@dataclass(frozen=True)
class Arm:
    name: str
    mode: str
    shift: str          # "none" | "blind" | "oracle"
    captures: str       # "declared" | "all"
    counts: bool
    note: str
    #: (dty, dtx): decode each tile from its NEIGHBOUR's evidence. The
    #: false-accept probe; any certificate here is a correctness failure.
    misaddress: tuple[int, int] | None = None


ARM_TABLE: dict[str, Arm] = {
    "A0": Arm("A0", "subtract", "none", "declared", True,
              "nominal: sibling-subtracted yellow, one capture"),
    "A1": Arm("A1", "subtract", "blind", "declared", True,
              "A0 + blind per-window offset (dust-anchored)"),
    "A2": Arm("A2", "subtract", "blind", "all", True,
              "A1 unioned over every capture of the sheet"),
    "C0": Arm("C0", "rawb", "none", "declared", True,
              "control: the raw blue channel"),
    "C1": Arm("C1", "project", "none", "declared", True,
              "control: C/M annihilated, no per-cell subtraction"),
    "X1": Arm("X1", "subtract", "oracle", "declared", False,
              "ORACLE offset from the emitted field — never counted"),
    "N0": Arm("N0", "subtract", "none", "declared", False,
              "NULL: every tile decoded from its right-hand neighbour's "
              "evidence — must certify nothing", misaddress=(0, 1)),
}


# --------------------------------------------------------------------
# inputs
# --------------------------------------------------------------------


def load_context(case: _cases.Case) -> dict:
    from holo3.data import Certificate
    from holo3.format.identity import build_site_geometry, resolve_format_ref
    from measure.crop_parity import _gt as gt_module

    sheet = _cases.SHEETS[case.sheet]
    _paths.refuse_if_absent((sheet.events_xz, sheet.gen_dir,
                             sheet.certified_tiles_json))
    row = resolve_format_ref(sheet.format_ref)
    geometry = build_site_geometry(row)
    payload = _truth.load_payload(sheet.gen_dir)
    field = _truth.load_emitted_field(sheet.gen_dir)
    truth = gt_module.reconstruct(sheet.format_ref, payload)
    certmap = _cases.certified_map(sheet)

    # THE RECONSTRUCTION GATE: user bits -> cells must equal the emitted
    # field on every tile this case will look at that is fully certified.
    probes = [pos for pos in
              [(ty, tx) for ty in range(case.crop_tiles[0], case.crop_tiles[1])
               for tx in range(case.crop_tiles[2], case.crop_tiles[3])]
              if len(certmap.get(pos, ())) == 3][:12]
    if not probes:
        probes = [(case.crop_tiles[0], case.crop_tiles[2])]
    gate = _truth.check_projection_against_field(
        row, geometry, truth.user_bits, field, 0, probes)

    certificates: dict = {}
    for (ty, tx), streams in certmap.items():
        for stream in streams:
            bits = truth.user_bits.get((0, ty, tx, stream))
            if bits is not None:
                certificates[(0, ty, tx, stream)] = Certificate(
                    page=0, ty=ty, tx=tx, stream_id=stream,
                    user_bits=np.asarray(bits, np.uint8),
                    source="production")
    poses = read_poses(sheet)
    return {"sheet": sheet, "row": row, "geometry": geometry,
            "field": field, "truth": truth, "certmap": certmap,
            "certificates": certificates, "poses": poses,
            "gt_gate": gate, "payload_bytes": len(payload),
            "cell_dots": int(row.pitch_in * HW_DPI)}


def read_poses(sheet: _cases.Sheet) -> list[dict]:
    rows: list[dict] = []
    with lzma.open(sheet.events_xz, "rt", encoding="utf-8") as handle:
        for line in handle:
            if '"PoseCommitted"' in line:
                rows.append(json.loads(line))
    return rows


def capture_lanes(sheet: _cases.Sheet, case: _cases.Case, which: str,
                  override: str | None = None,
                  ) -> list[tuple[str, Path, str, int]]:
    """(label, path, capture sha, finest level index) per capture used."""
    declared = override or case.capture
    keys = [declared] if which == "declared" else sorted(sheet.captures)
    out = []
    for key in keys:
        path, _dpi, sha = sheet.captures[key]
        if not path.is_file():
            continue
        out.append((key, path, sha, -1))
    return out


def finest_level(poses: list[dict], capture_id: str) -> int | None:
    levels = {int(event["level_index"]) for event in poses
              if event.get("capture") == capture_id and event.get("accepted")}
    return max(levels) if levels else None


# --------------------------------------------------------------------
# one arm
# --------------------------------------------------------------------


def run_lane(arm: Arm, planes, poses, ctx, pitch_px: float,
             frame: Fraction, shifts, field,
             labels_from: str = "certified",
             siblings: str = "certified") -> tuple[list, dict]:
    row, geometry = ctx["row"], ctx["geometry"]
    cell_dots = ctx["cell_dots"]
    certificates = ctx["certificates"]
    base = _read.read_windows(planes, poses, row, geometry, frame, pitch_px,
                              cell_dots, certificates, 0.0, labels_from)
    if not base:
        return [], {"reason": "no_window_inside_raster"}
    unmix = _spectral.fit_unmix(
        np.concatenate([read.values for read in base]),
        np.concatenate([read.bits for read in base]),
        np.concatenate([read.sibling_mask(siblings) for read in base]))
    detail = {"unmix": unmix_record(unmix)}
    if not unmix.accepted:
        return [], detail | {"reason": f"unmix_{unmix.reason}"}
    if arm.shift == "none":
        reads = base
        detail["shift_table"] = [{"window": list(r.pose.page_origin_yx),
                                  "shift_dots": 0.0} for r in base]
    elif arm.shift == "blind":
        reads, table = _read.read_windows_best_shift(
            planes, poses, row, geometry, frame, pitch_px, cell_dots,
            certificates, unmix, arm.mode, shifts, labels_from, siblings)
        detail["shift_table"] = table
    else:
        chosen: dict[int, object] = {}
        best: dict[int, float] = {}
        table: dict[int, float] = {}
        for shift in shifts:
            for read in _read.read_windows(planes, poses, row, geometry,
                                           frame, pitch_px, cell_dots,
                                           certificates, float(shift),
                                           labels_from):
                score = _spectral.y_score(unmix, read.values, read.bits,
                                          read.sibling_mask(siblings),
                                          arm.mode)
                bits = field.bits_at(read.page_cells_yx)[:, _read.Y_PLANE]
                stats = _spectral.separation(score[read.cargo_mask],
                                             bits[read.cargo_mask])
                value = -1.0 if stats["dprime"] is None else stats["dprime"]
                if read.ordinal not in best or value > best[read.ordinal]:
                    best[read.ordinal] = value
                    table[read.ordinal] = float(shift)
                    chosen[read.ordinal] = read
        reads = [chosen[key] for key in sorted(chosen)]
        detail["shift_table"] = [
            {"window": list(chosen[key].pose.page_origin_yx),
             "shift_dots": table[key], "dprime": best[key]}
            for key in sorted(chosen)]
    if not reads:
        return [], detail | {"reason": "no_window_survived_shift_choice"}
    corrected, region_ctx = _read.calibrate_reads(reads, unmix, arm.mode,
                                                  siblings)
    detail["ctx"] = {"adopted": bool(region_ctx.adopted),
                     "reason": str(region_ctx.reason)}
    detail["windows"] = {
        "read": len(reads),
        "accepted": sum(1 for e in corrected if e.accepted),
        "label_priors": [None if (p := _read.label_prior(e)) is None
                         else round(p, 4) for e in corrected]}
    # How much sibling knowledge this lane actually had — the premise
    # the ablations of section 4.3 test, reported rather than assumed.
    detail["coverage"] = _spectral.sibling_coverage(
        np.concatenate([read.sibling_mask(siblings) for read in reads]))
    detail["coverage"]["y_labelled"] = int(sum(
        int(np.count_nonzero(read.labels >= 0)) for read in reads))
    detail["unmix"] = unmix_record(unmix)
    detail["_unmix"] = unmix
    return reads, detail


def unmix_record(unmix) -> dict:
    return {"accepted": bool(unmix.accepted), "reason": unmix.reason,
            "n_full_rows": unmix.n_full_rows,
            "m0": [round(float(v), 3) for v in unmix.m0],
            "coef_channel_by_plane": [[round(float(v), 3) for v in rowv]
                                      for rowv in unmix.coef],
            "residual_sd": [round(float(v), 3)
                            for v in np.sqrt(np.diag(unmix.covariance))],
            "projection": [round(float(v), 5) for v in unmix.projection],
            "plane_snr": [round(v, 3) for v in unmix.channel_snr()]}


def separations(reads, unmix, mode, field, certmap, targets,
                siblings: str = "certified") -> dict:
    cells = np.concatenate([r.page_cells_yx for r in reads])
    cargo = np.concatenate([r.cargo_mask for r in reads])
    score = np.concatenate([
        _spectral.y_score(unmix, r.values, r.bits,
                          r.sibling_mask(siblings), mode)
        for r in reads])
    y_true = field.bits_at(cells)[:, _read.Y_PLANE]
    tile_y = cells[:, 0] // _read.TILE
    tile_x = cells[:, 1] // _read.TILE
    in_target = np.array([(int(a), int(b)) in targets
                          for a, b in zip(tile_y, tile_x)])
    live = np.array([("Y" in certmap.get((int(a), int(b)), frozenset()))
                     for a, b in zip(tile_y, tile_x)])
    out = {}
    for label, selected in (("target", cargo & in_target),
                            ("live", cargo & live),
                            ("all_cargo", cargo)):
        if not np.any(selected):
            out[label] = None
            continue
        out[label] = _spectral.separation(score[selected], y_true[selected])
    return out


# --------------------------------------------------------------------
# the battery
# --------------------------------------------------------------------


def run_case(case: _cases.Case, arms: list[str], siblings: str,
             shifts, prior_correction: bool, capture: str | None = None,
             labels: str = "certified") -> dict:
    import tifffile
    from measure.crop_parity import _gt as gt_module

    started = time.perf_counter()
    ctx = load_context(case)
    sheet = ctx["sheet"]
    row, geometry = ctx["row"], ctx["geometry"]
    certmap, truth, field = ctx["certmap"], ctx["truth"], ctx["field"]
    targets = set(case.target_positions)
    ty0, ty1, tx0, tx1 = case.crop_tiles
    positions = [(ty, tx) for ty in range(ty0, ty1) for tx in range(tx0, tx1)]
    rect = (ty0 * _read.TILE, ty1 * _read.TILE,
            tx0 * _read.TILE, tx1 * _read.TILE)

    report = {
        "case": case.case_id, "sheet": sheet.key,
        "capture": capture or case.capture,
        "format_ref": sheet.format_ref, "note": case.note,
        "crop_tiles": list(case.crop_tiles),
        "target_tiles": list(case.target_tiles),
        "siblings": siblings, "labels": labels,
        "prior_correction": bool(prior_correction),
        "shifts_dots": [float(v) for v in shifts],
        "gt_gate": ctx["gt_gate"], "payload_bytes": ctx["payload_bytes"],
        "production": production_census(certmap, positions, targets),
        "arms": {},
    }

    for name in arms:
        arm = ARM_TABLE[name]
        lanes: list[_read.Lane] = []
        arm_detail: dict = {"note": arm.note, "mode": arm.mode,
                            "shift": arm.shift, "captures": arm.captures,
                            "counts_toward_bar": arm.counts, "lanes": {}}
        seps = None
        for label, path, sha, _unused in capture_lanes(
                sheet, case, arm.captures, capture):
            level = finest_level(ctx["poses"], sha)
            if level is None:
                arm_detail["lanes"][label] = {"reason": "no_archived_pose"}
                continue
            poses_all = _read.poses_from_events(ctx["poses"], sha, level)
            poses = _read.poses_overlapping(poses_all, rect)
            if not poses:
                arm_detail["lanes"][label] = {"reason": "no_pose_over_case"}
                continue
            pitch_px = _read.region_pitch_px(poses_all)
            handle = tifffile.memmap(str(path), mode="r")
            try:
                planes = (handle[..., 0], handle[..., 1], handle[..., 2])
                reads, detail = run_lane(arm, planes, poses, ctx, pitch_px,
                                         Fraction(1), shifts, field,
                                         labels, siblings)
            finally:
                del handle
            if not reads:
                arm_detail["lanes"][label] = detail
                continue
            unmix = detail.pop("_unmix")
            detail["poses"] = len(poses)
            detail["pitch_px"] = round(pitch_px, 5)
            detail["level_index"] = level
            # Per-lane separation, and the SUMMARY row quotes the case's
            # declared capture — a union arm's d' is a per-capture number,
            # so quoting whichever lane ran first would compare a 1200 dpi
            # read against a 2400 dpi one.
            detail["separation"] = separations(reads, unmix, arm.mode,
                                               field, certmap, targets,
                                               siblings)
            if seps is None or label == (capture or case.capture):
                seps = detail["separation"]
                arm_detail["separation"] = seps
                arm_detail["separation_lane"] = label
            arm_detail["lanes"][label] = detail
            lanes.append(_read.Lane(sha, level, label, reads))
        if not lanes:
            arm_detail["verdict"] = "no lane produced evidence"
            report["arms"][name] = arm_detail
            continue
        outcome = _read.attempt_all(lanes, row, geometry, 0, positions,
                                    prior_correction, arm.misaddress)
        arm_detail["decode"] = tally(outcome, truth, certmap, arm,
                                     gt_module)
        arm_detail["decode"]["wall_seconds"] = round(
            outcome["wall_seconds"], 1)
        report["arms"][name] = arm_detail
    report["wall_seconds"] = round(time.perf_counter() - started, 1)
    return report


def production_census(certmap, positions, targets) -> dict:
    def census(rows):
        out = {"tiles": len(rows), "C": 0, "M": 0, "Y": 0, "all_three": 0}
        for pos in rows:
            streams = certmap.get(pos, frozenset())
            for stream in ("C", "M", "Y"):
                out[stream] += int(stream in streams)
            out["all_three"] += int(len(streams) == 3)
        return out

    return {"crop": census(positions), "target": census(sorted(targets))}


def tally(outcome, truth, certmap, arm: Arm, gt_module) -> dict:
    """Certificates, ground-truth verdicts, and the additive count.

    An ADD is a Y certificate that (a) matches the emitted payload
    exactly and (b) sits on a tile the production harvest left
    Y-uncertified. A certificate that does NOT match ground truth is a
    WRONG certificate whatever else is true of it — including in the
    null arm, where any certificate at all is a failure.
    """
    certificates = []
    n_wrong = 0
    n_adds = 0
    outcomes: dict[str, int] = {}
    for (ty, tx), result in sorted(outcome["results"].items()):
        if result is None:
            outcomes["no_cut"] = outcomes.get("no_cut", 0) + 1
            continue
        outcomes[result.fact.outcome] = outcomes.get(
            result.fact.outcome, 0) + 1
        if result.certificate is None:
            continue
        matched, n_bad = gt_module.check_bits(
            truth, (0, ty, tx, "Y"), result.certificate.user_bits)
        production_has_y = "Y" in certmap.get((ty, tx), frozenset())
        if arm.misaddress is not None or not matched:
            n_wrong += 1
        elif not production_has_y:
            n_adds += 1
        certificates.append({
            "tile": [ty, tx], "gt_match": bool(matched),
            "gt_bits_differing": int(n_bad),
            "production_has_y": production_has_y,
            "counts_as_add": bool(matched and not production_has_y
                                  and arm.misaddress is None),
            "bp_iters": int(result.fact.n_iters),
            "n_informative": int(result.fact.n_informative)})
    return {"certificates": len(certificates), "gt_exact":
            sum(1 for row in certificates if row["gt_match"]),
            "wrong": n_wrong, "adds": n_adds,
            "outcomes": outcomes, "detail": certificates}


# --------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------


def render(reports: list[dict]) -> list[str]:
    lines: list[str] = []
    lines.append("# Y-as-K battery")
    lines.append("")
    lines.append("| case | arm | counts | Y certs | GT-exact | WRONG | "
                 "**adds** | target d' | target cell err | live d' |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for report in reports:
        for name, arm in report["arms"].items():
            decode = arm.get("decode")
            sep = arm.get("separation") or {}
            target = sep.get("target") or {}
            live = sep.get("live") or {}
            if decode is None:
                lines.append(f"| {report['case']} | {name} | "
                             f"{'yes' if ARM_TABLE[name].counts else 'no'} | "
                             f"— | — | — | — | — | — | — |")
                continue
            lines.append(
                "| {case} | {arm} | {counts} | {certs} | {gt} | {wrong} | "
                "**{adds}** | {td} | {te} | {ld} |".format(
                    case=report["case"], arm=name,
                    counts="yes" if ARM_TABLE[name].counts else "no",
                    certs=decode["certificates"], gt=decode["gt_exact"],
                    wrong=decode["wrong"], adds=decode["adds"],
                    td=fmt(target.get("dprime")),
                    te=fmt(target.get("cell_error"), 4),
                    ld=fmt(live.get("dprime"))))
    lines.append("")
    for report in reports:
        production = report["production"]
        lines.append(f"## {report['case']} — {report['note']}")
        lines.append("")
        lines.append(
            f"crop tiles {report['crop_tiles']}, target tiles "
            f"{report['target_tiles']}; production certified "
            f"C {production['target']['C']}/{production['target']['tiles']}, "
            f"M {production['target']['M']}/{production['target']['tiles']}, "
            f"**Y {production['target']['Y']}/"
            f"{production['target']['tiles']}** on the target tiles; "
            f"ground-truth gate {report['gt_gate']['tiles']} tiles / "
            f"{report['gt_gate']['cells']} cells exact.")
        lines.append("")
        for name, arm in report["arms"].items():
            unmix = None
            for lane in arm.get("lanes", {}).values():
                unmix = lane.get("unmix") or unmix
            decode = arm.get("decode") or {}
            lines.append(
                f"* **{name}** ({arm['note']}): "
                f"{decode.get('certificates', 0)} Y certificates, "
                f"{decode.get('adds', 0)} on production-uncertified tiles, "
                f"{decode.get('wrong', 0)} wrong"
                + (f"; plane SNR {unmix['plane_snr']}" if unmix else ""))
        lines.append("")
    return lines


def fmt(value, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


# --------------------------------------------------------------------
# entry
# --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", action="append", default=[],
                        help="case id, or 'all'")
    parser.add_argument("--arms", default="A0,A1,A2,C0,C1",
                        help=f"comma separated; known: {','.join(ARMS)}")
    parser.add_argument("--siblings", choices=("certified", "furniture"),
                        default="certified",
                        help="what the MIXING FIT and the per-cell "
                             "subtraction may know")
    parser.add_argument("--labels", choices=("certified", "furniture"),
                        default="certified",
                        help="what the CALIBRATION may use as yellow "
                             "labels — the ablation that separates the "
                             "two jobs a certified neighbour does")
    parser.add_argument("--capture", default=None,
                        help="override the case's declared capture key "
                             "(the multi-capture arms are unaffected)")
    parser.add_argument("--prior-correction", action="store_true",
                        help="re-base the calibrated LLRs on the payload's "
                             "own 1/2 prior (a declared deviation)")
    parser.add_argument("--shift-min", type=float, default=-2.0)
    parser.add_argument("--shift-max", type=float, default=2.0)
    parser.add_argument("--shift-step", type=float, default=0.25)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)

    _paths.install_src()
    wanted = args.case or ["all"]
    cases = (list(_cases.CASES) if "all" in wanted
             else [_cases.CASES_BY_ID[name] for name in wanted])
    unknown = [name for name in wanted
               if name != "all" and name not in _cases.CASES_BY_ID]
    if unknown:
        raise SystemExit(f"yask: unknown case(s) {unknown}; declared: "
                         f"{sorted(_cases.CASES_BY_ID)}")
    arms = [name.strip() for name in args.arms.split(",") if name.strip()]
    bad = [name for name in arms if name not in ARM_TABLE]
    if bad:
        raise SystemExit(f"yask: unknown arm(s) {bad}; known: {list(ARMS)}")
    shifts = tuple(round(float(v), 4) for v in np.arange(
        args.shift_min, args.shift_max + 1e-9, args.shift_step))

    reports = []
    for case in cases:
        print(f"yask: {case.case_id} …", file=sys.stderr, flush=True)
        if args.capture is not None:
            known = _cases.SHEETS[case.sheet].captures
            if args.capture not in known:
                raise SystemExit(f"yask: unknown --capture {args.capture!r}; "
                                 f"declared: {sorted(known)}")
        report = run_case(case, arms, args.siblings, shifts,
                          args.prior_correction, args.capture, args.labels)
        reports.append(report)
        decode_lines = [
            f"  {name}: certs {arm.get('decode', {}).get('certificates', 0)}"
            f" adds {arm.get('decode', {}).get('adds', 0)}"
            f" wrong {arm.get('decode', {}).get('wrong', 0)}"
            for name, arm in report["arms"].items()]
        print("\n".join(decode_lines), file=sys.stderr, flush=True)

    out_dir = args.out or (_paths.SCRATCH / "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    # The arm set is part of the name: two invocations over the same
    # cases with different arms are two measurements, not one that
    # silently overwrites the other.
    stamp = ("-".join(report["case"] for report in reports)[:80]
             + "--" + "".join(arms)
             + ("" if args.capture is None else f"--{args.capture}")
             + ("" if args.siblings == "certified" else "--sibfurn")
             + ("" if args.labels == "certified" else "--labfurn")
             + ("--prior" if args.prior_correction else ""))
    (out_dir / f"yask-{stamp}.json").write_text(
        json.dumps(reports, indent=1, default=str) + "\n", encoding="utf-8")
    text = "\n".join(render(reports)) + "\n"
    (out_dir / f"yask-{stamp}.md").write_text(text, encoding="utf-8")
    print(text)
    wrong = sum(arm.get("decode", {}).get("wrong", 0)
                for report in reports for arm in report["arms"].values())
    if wrong:
        print(f"yask: {wrong} WRONG certificate(s) — correctness failure",
              file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
