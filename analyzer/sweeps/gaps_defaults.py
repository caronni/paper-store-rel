"""The no-regression gate for the GAPS-2026-09-03 default change.

`analyzer/GAPS-2026-09-03.md` §1/§4 nominate `halo 48 (C, M) + pooled
branches` as the default configuration and §3 nominates the pooled
fallback for a starved branch.  DESIGN §8's rule is that a default moves
only when it costs no certificate anywhere, so this measures the SAME
keys under the old and the new defaults, per key, on both sheets:

  H  the 60-tile band-stratified C sample of `c_parity_gap` phase A,
     plus a 20-per-stream M/Y parity;
  I  a 20-per-stream parity over all three streams.

Every configuration runs in ONE process per sheet (the H mirror costs
~12 GB to load), and the comparison is by KEY — a count that is equal
while the membership moved is a regression, not a wash.

Run:
    PYTHONPATH=. env/bin/python -m analyzer.sweeps.gaps_defaults --sheet H
    PYTHONPATH=. env/bin/python -m analyzer.sweeps.gaps_defaults --sheet I

2026-09-04 NOTE.  This sweep is the RECORD of a finished measurement.
The ruling that took ground truth out of the run removed the oracle
columns it used to read off a ledger row (`R`, cell error, the GT
certificate check); the call sites below are kept running and the
oracle buckets simply come back EMPTY.  Re-measuring any of them now
means `analyzer score --ledger … --payload … --run-dir …` beside the
pass, not a truth argument to the driver.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from analyzer import controls as ctl
from analyzer import fixedpoint as fp
from analyzer import inputs as inputs_mod
from analyzer import residue as residue_mod
from analyzer import truth as truth_mod
from analyzer.types import (DEFAULT_ARMS, DEFAULT_LADDER_RUNGS,
                            VERDICT_CERTIFIED,
                            VERDICT_CERTIFIED_LIST)

from .c_parity_gap import OUT, SEED, base_config, c_sample, jsonable, write

I_RUN_DIR = "/tmp/I/holo3-I-resume-3-run"
I_GT_DIR = "scratch/xerox-v1-20260818/I-c2-cmy8r0700-q090-4mm"

H_RUN_DIR = "scratch/analyzer/H7-mirror"
H_GT_DIR = "scratch/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm"

#: The four configurations the gate compares.  `proposed` is what the
#: package adopts; the two middles isolate which half of it moved a key.
CONFIGURATIONS: tuple[tuple[str, dict], ...] = (
    ("default", dict()),
    ("old_default", dict(knobs={"branches": "subtract",
                                "starved_fallback": False})),
    ("fallback_only", dict(knobs={"starved_fallback": True})),
    ("pooled_only", dict(knobs={"branches": "pooled"})),
    ("proposed", dict(halo_cells={"C": 48, "M": 48, "Y": 32},
                      knobs={"branches": "pooled",
                             "starved_fallback": True})),
    ("pooled_fallback", dict(knobs={"branches": "pooled",
                                    "starved_fallback": True})),
    ("halo48_only", dict(halo_cells={"C": 48, "M": 48, "Y": 32})),
)


def load(run_dir: str, gt_dir: str, *, check_rank: bool) -> tuple:
    run = inputs_mod.load_run(run_dir)
    truth = truth_mod.load_truth(gt_dir, gt_dir + "/payload-counting.bin",
                                 run.row, max(run.live_pages) + 1,
                                 format_ref=run.format_ref)
    rows = residue_mod.census(run, events=None, check_rank=check_rank)
    return run, truth, rows


def certified_keys(ledger) -> set:
    return {row.key for row in ledger.rows
            if row.verdict in (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST)}


def wrong_rows(ledger) -> list:
    out = []
    for row in ledger.rows:
        # The GT check of a certificate is `analyzer score`'s now; a
        # run's row cannot answer it, so this column is honestly None.
        matches = None
        if row.verdict in (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST) \
                and matches is False:
            out.append(list(row.key))
    return out


def one(run, truth, rows, targets, label: str, overrides: dict) -> dict:
    started = time.perf_counter()
    ledger = fp.run(run, targets, base_config(**overrides),
                    census_rows=rows, exposure=fp.shared_exposure())
    got = certified_keys(ledger)
    by_stream: dict[str, list[int]] = {}
    for row in ledger.rows:
        entry = by_stream.setdefault(row.stream_id, [0, 0])
        entry[0] += int(row.key in got)
        entry[1] += 1
    return {
        "label": label, "overrides": jsonable(overrides),
        "seconds": time.perf_counter() - started,
        "n_targets": len(targets), "n_certified": len(got),
        "certified": sorted([list(k) for k in got]),
        "by_stream": {k: {"re_derived": v[0], "n": v[1],
                          "rate": v[0] / v[1] if v[1] else None}
                      for k, v in sorted(by_stream.items())},
        "wrong": wrong_rows(ledger),
        "certifying_arms": sorted({str(row.certifying_arm)
                                   for row in ledger.rows
                                   if getattr(row, "certifying_arm", None)}),
    }


def compare(results: dict) -> dict:
    base = {tuple(k) for k in map(tuple, results["default"]["certified"])}
    out = {}
    for label, result in results.items():
        if label == "default":
            continue
        got = {tuple(k) for k in map(tuple, result["certified"])}
        out[label] = {
            "gained": sorted([list(k) for k in got - base]),
            "lost": sorted([list(k) for k in base - got]),
            "n_gained": len(got - base), "n_lost": len(base - got),
            "no_regression": not (base - got),
        }
    return out


def reroll_phase(run, truth, rows) -> dict:
    """What the re-roll buys, isolated (GAPS §7).

    The C60 sample under the ADOPTED defaults names its own misses; those
    keys then get the full battery twice — once with the selection alone
    (`reroll=False`, one arm per lane, exactly as before) and once with the
    re-roll on.  The difference is the re-roll's yield and nothing else:
    the same evidence, the same rules, the same two rungs.
    """
    sample = c_sample(rows)
    base = one(run, truth, rows, sample, "default", dict())
    got = {tuple(k) for k in map(tuple, base["certified"])}
    missed = [row for row in sample if tuple(row.key) not in got]
    out: dict[str, Any] = {"default": base,
                           "missed": [list(row.key) for row in missed],
                           "runs": {}}
    for label, overrides in (
            ("battery_no_reroll", dict(arms=DEFAULT_ARMS, reroll=False)),
            ("battery_reroll", dict(arms=DEFAULT_ARMS, reroll=True)),
            ("ladder_no_reroll", dict(arms=DEFAULT_ARMS, reroll=False,
                                      rungs=DEFAULT_LADDER_RUNGS)),
            ("ladder_reroll", dict(arms=DEFAULT_ARMS, reroll=True,
                                   rungs=DEFAULT_LADDER_RUNGS,
                                   reroll_rungs=("L0", "L1", "L2")))):
        result = one(run, truth, rows, missed, label, overrides)
        out["runs"][label] = result
        print(f"  {label}: {result['n_certified']}/{len(missed)} in "
              f"{result['seconds']:.0f}s arms={result['certifying_arms']}",
              flush=True)
    out["compare"] = {}
    for pair in ("battery", "ladder"):
        off = {tuple(k) for k in map(
            tuple, out["runs"][f"{pair}_no_reroll"]["certified"])}
        on = {tuple(k) for k in map(
            tuple, out["runs"][f"{pair}_reroll"]["certified"])}
        out["compare"][pair] = {
            "n_off": len(off), "n_on": len(on),
            "gained": sorted([list(k) for k in on - off]),
            "lost": sorted([list(k) for k in off - on])}
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="gate", choices=("gate", "reroll"))
    parser.add_argument("--sheet", default="H", choices=("H", "I"))
    parser.add_argument("--only", default=None,
                        help="comma-separated configuration labels")
    parser.add_argument("--n-per-stream", type=int, default=20)
    parser.add_argument("--suffix", default="")
    args = parser.parse_args()

    if args.sheet == "H":
        run, truth, rows = load(H_RUN_DIR, H_GT_DIR, check_rank=False)
    else:
        run, truth, rows = load(I_RUN_DIR, I_GT_DIR, check_rank=False)
    print("loaded", flush=True)

    if args.phase == "reroll":
        write(f"reroll-{args.sheet}.json", reroll_phase(run, truth, rows))
        return 0

    wanted = None if args.only is None else set(args.only.split(","))
    configurations = [(name, over) for name, over in CONFIGURATIONS
                      if wanted is None or name in wanted]
    payload: dict[str, Any] = {"sheet": args.sheet, "seed": SEED,
                               "samples": {}, "results": {}, "compare": {}}

    samples: dict[str, list] = {}
    if args.sheet == "H":
        samples["c60"] = c_sample(rows)
        samples["parity_MY"] = ctl.stratified_sample(
            [row for row in rows if row.certified_by_production],
            int(args.n_per_stream), SEED, streams=("M", "Y"))
    else:
        samples["parity_CMY"] = ctl.stratified_sample(
            [row for row in rows if row.certified_by_production],
            int(args.n_per_stream), SEED, streams=("C", "M", "Y"))

    for sample_name, sample in samples.items():
        payload["samples"][sample_name] = [
            {"key": list(row.key), "band": row.band, "source": row.source}
            for row in sample]
        payload["results"][sample_name] = {}
        for label, overrides in configurations:
            result = one(run, truth, rows, sample, label, overrides)
            payload["results"][sample_name][label] = result
            print(f"  {sample_name}/{label}: {result['n_certified']}"
                  f"/{len(sample)} in {result['seconds']:.0f}s "
                  f"{result['by_stream']}", flush=True)
        if "default" in payload["results"][sample_name]:
            payload["compare"][sample_name] = compare(
                payload["results"][sample_name])

    OUT.mkdir(parents=True, exist_ok=True)
    name = f"gate-{args.sheet}{args.suffix}.json"
    write(name, payload)
    print(json.dumps(jsonable(payload["compare"]), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
