#!/usr/bin/env python
"""The pooled-context arm's decode evidence: null proof and existence.

    cd <worktree>
    PYTHONPATH=src:. env/bin/python -m measure.pooled_ctx.harness \\
        --artefacts <dir> --case null-color --out <dir>/null-color.json

    # the null proof runs the SAME command against an unmodified tree:
    PYTHONPATH=<baseline>:<baseline>/src env/bin/python \\
        -m measure.pooled_ctx.harness --artefacts <dir> --case null-color \\
        --out <dir>/null-color-baseline.json
    # (the baseline copy needs this driver on its PYTHONPATH too:
    #  PYTHONPATH=<baseline>:<baseline>/src:<worktree>)

    ... --compare a.json b.json      # payload, certificates, job counts

CASES
  null-k        the single-capture K sim — the arm cannot exist here
  null-color    the single-capture colour sim — no second capture, so
                no population is published and no pooled row is born
  mixed         the two-capture K sim (K again: the arm is colour-only)
  pair          the complementary colour pair (measure/pooled_ctx/sims),
                with --pooled/--no-pooled as the arm dial

Every record carries the payload sha, the certificate signature, the
per-address certificate set, the per-plugin job counts and the pooled
arm's own counters, so two records can be diffed without re-running.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

COLOR_FORMAT_REF = "c3-cmy8-r0550x0550x0547@10x10"
K_FORMAT_REF = "c3-k-r0550@7x7"
DPI = 1200.0
UPSAMPLE = 2
COLOR_BORDER_DOTS = 60


def _sims_module():
    from holo.receiver.tests import _h3_sims

    return _h3_sims


def build_artefacts(artefacts: Path) -> dict[str, Path]:
    sims = _sims_module()
    reason = sims.producer_unavailable_reason()
    if reason is not None:
        raise SystemExit(f"cannot build the sims: {reason}")
    artefacts.mkdir(parents=True, exist_ok=True)
    k_dir = artefacts / "k"
    color_dir = artefacts / "color"
    if sims.verify(k_dir, sims.EXPECTED_K) is not None:
        sims.make_k(k_dir)
    if sims.verify(color_dir, sims.EXPECTED_COLOR) is not None:
        sims.make_color(color_dir)
    for name, target, expected in (("k", k_dir, sims.EXPECTED_K),
                                   ("color", color_dir,
                                    sims.EXPECTED_COLOR)):
        problem = sims.verify(target, expected)
        if problem is not None:
            raise SystemExit(f"{name} sim does not match its frozen "
                             f"artefacts: {problem}")
    mixed_dir = artefacts / "k-mixed"
    if sims.verify(mixed_dir, sims.EXPECTED_MIXED) is not None:
        sims.make_k_mixed(k_dir / sims.K_TIFF_NAME, mixed_dir)
    return {
        "k": k_dir / sims.K_TIFF_NAME,
        "color": color_dir / sims.COLOR_TIFF_NAME,
        "k-payload": k_dir / sims.K_PAYLOAD_NAME,
        "color-payload": color_dir / sims.COLOR_PAYLOAD_NAME,
        "mixed-a": mixed_dir / sims.MIXED_A_TIFF_NAME,
        "mixed-b": mixed_dir / sims.MIXED_B_TIFF_NAME,
    }


def build_pair(artefacts: Path, base: Path, spec) -> tuple[Path, Path]:
    from measure.pooled_ctx import sims as pair_sims

    from holo.receiver.format import identity

    row = identity.resolve_format_ref(COLOR_FORMAT_REF)
    cell_px = float(row.pitch_in * DPI)
    border_px = float(COLOR_BORDER_DOTS * UPSAMPLE)
    return pair_sims.make_pair(base, artefacts / "pair", cell_px, border_px,
                               spec)


def decode(scans: tuple[Path, ...], format_ref: str, run_dir: Path,
           out_path: Path, workers: int, pooled: bool,
           dpis: tuple[float, ...]) -> dict:
    from holo.receiver import data, engine

    run_dir.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    fields = {"scans": scans, "dpis": dpis, "format_ref": format_ref,
              "max_pages": 1, "workers": workers, "complete": True,
              "no_close": False, "diag_port": None, "run_dir": run_dir}
    # the null proof runs this driver against a tree that predates the
    # arm, whose DecodeRequest has no dial at all
    if "pooled_color_context" in data.DecodeRequest.__dataclass_fields__:
        fields["pooled_color_context"] = pooled
    elif not pooled:
        raise SystemExit("this holo3 tree has no pooled-context dial to "
                         "turn off")
    request = data.DecodeRequest(**fields)
    events: list = []
    instance = engine._Engine(request, events)
    started = time.monotonic()
    result = instance.run()
    wall_s = time.monotonic() - started
    certificates = dict(instance._certificates)
    signature = hashlib.sha256()
    for key in sorted(certificates):
        signature.update(repr(key).encode())
        signature.update(
            np.asarray(certificates[key].user_bits, np.uint8).tobytes())
    pooled_cells = {f"{key[0]}|{key[1]}": {
        "adopted": bool(cell.adopted), "reason": cell.reason,
        "n_lanes": int(cell.n_lanes), "n_rows": int(cell.n_rows),
        "validation_logloss": (None if cell.validation_logloss is None
                               else float(cell.validation_logloss))}
        for key, cell in sorted(getattr(instance, "_pooled_ctx", {}).items())}
    lane_events = [event for event in events
                   if type(event).__name__ == "CalibrateAdopted"]
    populations = getattr(instance, "_color_pops", {})
    pop_bytes = sum(
        int(sum(np.asarray(getattr(row, name)).nbytes
                for name in ("keys_pyx", "scores", "states", "kinds",
                             "bins", "search")))
        for row in populations.values())
    return {
        "status": result.status,
        "payload_sha256": result.payload_sha256,
        "payload_bytes": (None if result.payload is None
                          else len(result.payload)),
        "certified": int(result.certified),
        "certificate_signature": signature.hexdigest(),
        "certificates": sorted(f"{key[0]}/{key[1]}/{key[2]}/{key[3]}"
                               for key in certificates),
        "jobs": {row.plugin: int(row.jobs) for row in result.plugin_rows},
        "cpu_s": {row.plugin: round(float(row.cpu_seconds), 3)
                  for row in result.plugin_rows},
        "pooled_cells": pooled_cells,
        "pooled_lane_adoptions": sum(
            1 for event in lane_events if event.reason == "pooled_head"),
        "pooled_lane_ids": sorted({
            event.pool_id for event in lane_events
            if event.reason == "pooled_head"}),
        "lane_refusals": sorted({
            f"{event.pool_id}:{event.reason}" for event in lane_events
            if not event.adopted}),
        "pooled_fits_offered": sum(
            1 for event in lane_events
            if event.capture == "color.pooled_ctx"),
        "pooled_fits_adopted": sum(
            1 for event in lane_events
            if event.capture == "color.pooled_ctx" and event.adopted),
        "population_lanes": len(populations),
        "population_rows": {f"{key[0][:12]}|l{key[1]}|p{key[2]}":
                            int(np.asarray(row.states).size)
                            for key, row in sorted(populations.items())},
        "population_bytes": pop_bytes,
        "wall_s": round(wall_s, 2),
        "workers": workers,
        "pooled_dial": pooled,
    }


def run_case(args: argparse.Namespace) -> dict:
    artefacts = Path(args.artefacts).resolve()
    paths = build_artefacts(artefacts)
    run_root = artefacts / "runs" / args.label
    if args.case == "null-k":
        scans, ref, dpis = (paths["k"],), K_FORMAT_REF, (DPI,)
    elif args.case == "null-color":
        scans, ref, dpis = (paths["color"],), COLOR_FORMAT_REF, (DPI,)
    elif args.case == "mixed":
        scans = (paths["mixed-a"], paths["mixed-b"])
        ref, dpis = K_FORMAT_REF, (DPI, DPI / 2)
    elif args.case == "pair":
        from measure.pooled_ctx.sims import PairSpec

        spec = PairSpec(band_tiles=args.band_tiles,
                        band_rows=args.band_rows,
                        blur_a_px=args.blur_a_px,
                        noise_b_sd=args.noise_sd, blur_b_px=args.blur_px,
                        noise_b_sd_top=args.noise_sd_top,
                        blur_b_px_top=args.blur_px_top,
                        contrast_b=args.contrast,
                        contrast_b_top=args.contrast_top)
        scans = build_pair(artefacts, paths["color"], spec)
        ref, dpis = COLOR_FORMAT_REF, (DPI, DPI)
    else:
        raise SystemExit(f"unknown case {args.case}")
    record = decode(tuple(scans), ref, run_root / "run",
                    run_root / "payload.bin", args.workers, args.pooled,
                    dpis)
    record["case"] = args.case
    record["label"] = args.label
    record["scans"] = [str(path) for path in scans]
    if args.case == "pair":
        record["pair"] = {"band_tiles": args.band_tiles,
                          "band_rows": args.band_rows,
                          "blur_a_px": args.blur_a_px,
                          "noise_sd": args.noise_sd,
                          "blur_px": args.blur_px,
                          "noise_sd_top": args.noise_sd_top,
                          "blur_px_top": args.blur_px_top,
                          "contrast": args.contrast,
                          "contrast_top": args.contrast_top}
    return record


def compare(left: Path, right: Path) -> int:
    a = json.loads(Path(left).read_text())
    b = json.loads(Path(right).read_text())
    same_payload = a["payload_sha256"] == b["payload_sha256"]
    same_certs = a["certificate_signature"] == b["certificate_signature"]
    only_a = sorted(set(a["certificates"]) - set(b["certificates"]))
    only_b = sorted(set(b["certificates"]) - set(a["certificates"]))
    print(f"payload   {a['payload_sha256']}  vs  {b['payload_sha256']}  "
          f"{'IDENTICAL' if same_payload else 'DIFFERENT'}")
    print(f"certs     {a['certified']} vs {b['certified']}  signature "
          f"{'IDENTICAL' if same_certs else 'DIFFERENT'}")
    if only_a:
        print(f"only in {a['label']} ({len(only_a)}): "
              f"{', '.join(only_a[:12])}")
    if only_b:
        print(f"only in {b['label']} ({len(only_b)}): "
              f"{', '.join(only_b[:12])}")
    for name in sorted(set(a["jobs"]) | set(b["jobs"])):
        left_jobs, right_jobs = a["jobs"].get(name, 0), b["jobs"].get(name, 0)
        flag = "" if left_jobs == right_jobs else "   <-- moved"
        print(f"jobs      {name:<18} {left_jobs:>6} {right_jobs:>6}{flag}")
    for key in ("pooled_fits_offered", "pooled_fits_adopted",
                "pooled_lane_adoptions"):
        print(f"arm       {key:<18} {a.get(key, 0):>6} {b.get(key, 0):>6}")
    return 0 if same_payload else 1


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="measure.pooled_ctx.harness")
    parser.add_argument("--artefacts",
                        help="stimulus + run directory (required with --case; "
                             "the decode states are multi-GB)")
    parser.add_argument("--case", choices=("null-k", "null-color", "mixed",
                                           "pair"))
    parser.add_argument("--label")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--band-tiles", dest="band_tiles", type=int,
                        default=3)
    parser.add_argument("--noise-sd", dest="noise_sd", type=float,
                        default=10.0)
    parser.add_argument("--blur-px", dest="blur_px", type=float, default=1.4)
    parser.add_argument("--band-rows", dest="band_rows", type=int)
    parser.add_argument("--blur-a-px", dest="blur_a_px", type=float,
                        default=0.0)
    parser.add_argument("--contrast", type=float, default=1.0)
    parser.add_argument("--contrast-top", dest="contrast_top", type=float)
    parser.add_argument("--noise-sd-top", dest="noise_sd_top", type=float)
    parser.add_argument("--blur-px-top", dest="blur_px_top", type=float)
    parser.add_argument("--no-pooled", dest="pooled", action="store_false")
    parser.add_argument("--compare", nargs=2, type=Path)
    args = parser.parse_args(argv)
    if args.compare is not None:
        return compare(*args.compare)
    if args.case is None:
        parser.error("--case or --compare is required")
    if args.artefacts is None:
        parser.error("--artefacts is required with --case")
    if args.label is None:
        args.label = f"{args.case}-{'on' if args.pooled else 'off'}"
    record = run_case(args)
    text = json.dumps(record, indent=2, sort_keys=True)
    if args.out is not None:
        Path(args.out).write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
