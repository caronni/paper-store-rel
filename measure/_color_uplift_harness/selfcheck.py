"""PK0 acceptance runner (NOT pytest — never profile through pytest).

    PYTHONPATH=src:measure env/bin/python \
        -m _color_uplift_harness.selfcheck [--skip-replays] [--json OUT]

Four checks, in order:

a. provenance verify — every corpus artifact hashes to its frozen value;
b. truth path — the certified tiles of xerox c3-cmy7 (720) and hp c3-cmy8
   (663) re-encode through ``project_certified_color_tile`` and agree with
   the emitted ground truth;
c. baseline replay of xerox c3-cmy7 under the CURRENT, unmodified code
   with ``--force-null`` — the acceptance target is the archived
   per-stream CRC-pass certificate set reproduced CERT-FOR-CERT
   (identical certificate ids, addresses and streams).  Anything short of
   that is reported as the measured fidelity with its set difference, NOT
   redefined away;
d. the per-packet replay set — hp c3-cmy8 and xerox c2-cmy8 baselines
   cached and replayed, with their wall/CPU cost recorded.

The replays are the expensive part (tens of minutes each on the 6.9 GB
captures); ``--skip-replays`` re-reads the run JSONs already on disk
instead of re-running them.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from . import corpus, gt_score, provenance, state_cache

REPLAY_SET = ("xerox-c3-cmy7", "hp-c3-cmy8", "xerox-c2-cmy8")
TRUTH_SET = (("xerox-c3-cmy7", 720), ("hp-c3-cmy8", 663))


def _print(text: str = "") -> None:
    print(text, flush=True)


def check_provenance(keys: tuple[str, ...] | None) -> dict:
    started = time.perf_counter()
    problems = provenance.verify(keys)
    seconds = time.perf_counter() - started
    _print(f"(a) provenance verify: "
           f"{'OK' if not problems else 'FAILED'} "
           f"({len(corpus.CAPTURES)} captures, {seconds:.0f}s)")
    for line in problems:
        _print(f"    MISMATCH {line}")
    return {"ok": not problems, "problems": problems,
            "seconds": round(seconds, 1)}


def check_truth_path() -> dict:
    rows = {}
    for key, expected in TRUTH_SET:
        row = corpus.capture(key)
        cache = state_cache.load(row, verbose=False)
        state_cache.verify_against_provenance(row, cache)
        spec = corpus.resolve_spec(row, cache.format_row_id)
        truth = gt_score.load_ground_truth(row)
        certificates = list(cache.certificates_by_id.values())
        started = time.perf_counter()
        audit = gt_score.audit_certificates(certificates, spec, truth)
        seconds = time.perf_counter() - started
        ok = (audit["disagreeing_addresses"] == 0
              and audit["cells_compared"] > 0
              and len(certificates) == expected)
        rows[key] = {
            "ok": ok,
            "certificates": len(certificates),
            "expected_certificates": expected,
            "addresses": audit["addresses"],
            "cells_compared": audit["cells_compared"],
            "agreement": audit["agreement"],
            "disagreeing_addresses": audit["disagreeing_addresses"],
            "owned_cells_by_stream": audit["owned_cells_by_stream"],
            "seconds": round(seconds, 1),
        }
        _print(f"(b) truth path {key}: "
               f"{'OK' if ok else 'FAILED'} — {len(certificates)} "
               f"certificates (expected {expected}), "
               f"{audit['addresses']} addresses, "
               f"{audit['cells_compared']} certified cells compared, "
               f"agreement {audit['agreement']:.9f}, "
               f"{audit['disagreeing_addresses']} disagreeing "
               f"({seconds:.0f}s)")
        if audit["disagreeing_addresses"]:
            _print("    CAMPAIGN-STOP: certified content disagrees with GT")
    return rows


def check_force_null_hygiene() -> dict:
    """Every runner binds the null hatch to its FLAG — both directions.

    Cheap, deterministic, and it runs before the expensive checks because
    it protects all of them: an INHERITED
    ``HOLO_COLOR_STACK_FORCE_NULL`` silently nulls the arms while every
    artifact a run writes still says ``force_null: false``.  Exporting on
    request was always covered by use; this is the inverse, in the
    harness's own refuse-don't-ignore style, and it is the only
    pytest-free place the harness validates its own entry points.
    """
    from argparse import Namespace

    from . import ab_runner, patch_runner

    entries = (
        ("ab_runner", lambda flag: ab_runner._apply_force_null(flag)),
        ("patch_runner", lambda flag: patch_runner._apply_hatches(
            Namespace(force_null=flag))),
    )
    saved = os.environ.get(ab_runner.FORCE_NULL_ENV)
    rows: dict[str, str] = {}
    try:
        for name, call in entries:
            os.environ[ab_runner.FORCE_NULL_ENV] = "1"
            try:
                call(False)
            except SystemExit as refusal:
                rows[name] = f"refused: {refusal}"
            else:
                rows[name] = "ACCEPTED an inherited hatch"
            os.environ.pop(ab_runner.FORCE_NULL_ENV, None)
            call(True)          # …and the flag itself still exports it
            if os.environ.get(ab_runner.FORCE_NULL_ENV) != "1":
                rows[name] = "did NOT export the hatch on --force-null"
    finally:
        os.environ.pop(ab_runner.FORCE_NULL_ENV, None)
        if saved is not None:
            os.environ[ab_runner.FORCE_NULL_ENV] = saved
    ok = all(value.startswith("refused") for value in rows.values())
    _print(f"(a0) force-null hygiene: {'OK' if ok else 'FAILED'}")
    for name, value in sorted(rows.items()):
        _print(f"    {name}: {value}")
    return {"ok": ok, "runners": rows}


def _replay_path(key: str) -> Path:
    return corpus.work_root() / "runs" / f"{key}-replay-baseline-forcenull.json"


def run_replay(key: str, *, diag_port: int | None) -> dict:
    out = _replay_path(key)
    command = [
        str(Path(sys.executable)), "-m",
        "_color_uplift_harness.ab_runner", "replay",
        "--capture", key, "--arm", "baseline", "--force-null", "--close",
    ]
    if diag_port is not None:
        command += ["--diag", "--diag-port", str(diag_port)]
    env = dict(os.environ)
    env["PYTHONPATH"] = "src:measure"
    started = time.perf_counter()
    completed = subprocess.run(
        command, cwd=Path(__file__).resolve().parents[2],
        capture_output=True, text=True, env=env)
    seconds = time.perf_counter() - started
    if completed.returncode != 0:
        _print(completed.stdout[-2000:])
        _print(completed.stderr[-4000:])
        raise SystemExit(f"{key}: replay failed ({completed.returncode})")
    return {"seconds": round(seconds, 1), "out": str(out)}


def check_replay_fidelity(key: str) -> dict:
    """Cert-for-cert comparison of one replay against its archived state."""
    path = _replay_path(key)
    if not path.is_file():
        return {"ok": False, "reason": f"no run JSON at {path}"}
    run = json.loads(path.read_text())
    diff = gt_score.set_difference(run)
    row = corpus.capture(key)
    spec = corpus.resolve_spec(row, run["format_row_id"])
    truth = gt_score.load_ground_truth(row)
    certificates = gt_score.certificates_from_run(run["certificates"])
    audit = gt_score.audit_certificates(certificates, spec, truth)
    lanes = [
        {
            "lane_id": lane["lane_id"],
            "kind": lane["lane_kind"],
            "replayed": lane["certificates"],
            "archived": lane["archived_certificates"],
            "delta": lane["certificates"] - lane["archived_certificates"],
            "placements": lane["placements"],
            "cpu_s": lane["cpu_s"],
        }
        for lane in run["lanes"]
    ]
    totals = run["totals"]
    result = {
        "ok": bool(diff.get("identical")),
        "certificate_set": diff,
        "by_stream": totals["by_stream"],
        "archived_by_stream": run["archived"]["by_stream"],
        "wrong_certificates": audit["disagreeing_addresses"],
        "certified_cell_agreement": audit["agreement"],
        "wall_s": totals["wall_s"],
        "cpu_s": totals["cpu_s"],
        "peak_rss_mib": totals["peak_rss_mib"],
        "close": run.get("close"),
        "lanes": lanes,
        "diag_enabled": run.get("diagnostics", {}).get("enabled", False),
    }
    verdict = "CERT-FOR-CERT IDENTICAL" if result["ok"] else "NOT identical"
    _print(f"    {key}: {verdict} — replayed {diff.get('produced')} vs "
           f"archived {diff.get('archived')} "
           f"(missing {diff.get('missing')}, extra {diff.get('extra')}), "
           f"streams {totals['by_stream']} vs "
           f"{run['archived']['by_stream']}, "
           f"wrong certs {audit['disagreeing_addresses']}, "
           f"wall {totals['wall_s']}s cpu {totals['cpu_s']}s")
    if not result["ok"]:
        for lane in lanes:
            if lane["delta"]:
                _print(f"      lane {lane['lane_id']} ({lane['kind']}): "
                       f"{lane['replayed']} vs archived {lane['archived']} "
                       f"({lane['delta']:+d})")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="_color_uplift_harness.selfcheck", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-provenance", action="store_true")
    parser.add_argument("--skip-replays", action="store_true",
                        help="score the run JSONs already on disk")
    parser.add_argument("--only", action="append", default=[],
                        help="restrict the replay set")
    parser.add_argument("--diag-port", type=int, default=None)
    parser.add_argument("--json", default=None)
    args = parser.parse_args(argv)

    report: dict = {"schema": "color-uplift-selfcheck-1"}
    report["force_null_hygiene"] = check_force_null_hygiene()
    if not args.skip_provenance:
        report["provenance"] = check_provenance(None)
    else:
        _print("(a) provenance verify: SKIPPED")
    report["truth_path"] = check_truth_path()

    keys = tuple(args.only) if args.only else REPLAY_SET
    _print("(c/d) baseline replays (force-null, current code):")
    replays: dict[str, dict] = {}
    for key in keys:
        if not args.skip_replays:
            _print(f"    running {key} …")
            replays[key] = {"run": run_replay(key, diag_port=args.diag_port)}
        else:
            replays[key] = {"run": {"skipped": True}}
        replays[key]["fidelity"] = check_replay_fidelity(key)
    report["replays"] = replays

    acceptance = replays.get("xerox-c3-cmy7", {}).get("fidelity", {})
    report["acceptance"] = {
        "target": ("xerox c3-cmy7 baseline replay reproduces the archived "
                   "per-stream CRC-pass certificate set cert-for-cert"),
        "met": bool(acceptance.get("ok")),
        "measured": acceptance.get("certificate_set"),
    }
    wrong = sum(
        row.get("fidelity", {}).get("wrong_certificates", 0) or 0
        for row in replays.values())
    report["wrong_certificates_total"] = wrong
    _print()
    _print(f"acceptance (c): "
           f"{'MET' if report['acceptance']['met'] else 'NOT MET'}")
    _print(f"wrong certificates across every replay: {wrong} "
           f"(bar B5: any non-zero stops the campaign)")
    if args.json:
        Path(args.json).write_text(
            json.dumps(report, indent=1, sort_keys=True) + "\n")
    failed = (
        (not report["force_null_hygiene"]["ok"])
        or (not report.get("provenance", {"ok": True})["ok"])
        or any(not row["ok"] for row in report["truth_path"].values())
        or not report["acceptance"]["met"]
        or wrong)
    return 1 if failed else 0


if __name__ == "__main__":
    from _color_uplift_harness import selfcheck as _module

    raise SystemExit(_module.main())
