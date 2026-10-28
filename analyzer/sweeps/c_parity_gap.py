"""Why the analyzer's default arm re-derives only 11/16 of production's C
certificates on sheet H — a measurement, not a module (PLAN §6 sweeps).

Phases:
  A  a 60-tile band-stratified C sample of production-certified tiles,
     re-derived with the DEFAULT configuration; the missed keys named.
  B  one-factor-at-a-time ablations over the missed keys.
  C  what production's own record says minted each missed key.
  D  the page-scope context fit against the per-footprint fit.

Run:
    PYTHONPATH=. env/bin/python \
        -m analyzer.sweeps.c_parity_gap --phase A

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
from dataclasses import replace as dc_replace
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from analyzer import controls as ctl
from analyzer import fixedpoint as fp
from analyzer import inputs as inputs_mod
from analyzer import residue as residue_mod
from analyzer import truth as truth_mod
from analyzer.types import (DEFAULT_ARMS, AnalyzerConfig, VERDICT_CERTIFIED,
                            VERDICT_CERTIFIED_LIST)

RUN_DIR = "scratch/analyzer/H7-mirror"
GT_DIR = "scratch/xerox-v1-20260818/H-c2-cmy8r0850-q090-4mm"
PAYLOAD = GT_DIR + "/payload-counting.bin"
OUT = Path("scratch/analyzer/sweeps/C-parity-gap")
SEED = 20260903
WORKERS = 6


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Fraction):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def load() -> tuple[Any, Any, list]:
    run = inputs_mod.load_run(RUN_DIR)
    truth = truth_mod.load_truth(GT_DIR, PAYLOAD, run.row,
                                 max(run.live_pages) + 1,
                                 format_ref=run.format_ref)
    rows = residue_mod.census(run, events=None, check_rank=False)
    return run, truth, rows


# ------------------------------------------------------------- the sample

ALLOCATION = {"dead": 2, "marginal": 25, "live": 33}


def c_sample(rows: list, n_total: int = 60) -> list:
    """Band-stratified over production-certified C rows, hash-ordered.

    The allocation is a superset of `controls.stratified_sample`'s own
    top-of-hash picks in each band, so the 16-tile control sample is
    contained in this one.
    """
    certified = [row for row in rows
                 if row.certified_by_production and row.stream_id == "C"]
    by_band: dict[str, list] = {}
    for row in certified:
        by_band.setdefault(row.band, []).append(row)
    picked: list = []
    short = 0
    for band in ("dead", "marginal", "live"):
        pool = sorted(by_band.get(band, ()),
                      key=lambda row: ctl._hash_rank(SEED, row.key))
        want = ALLOCATION[band]
        take = pool[:want]
        short += want - len(take)
        picked.extend(take)
    if short:                                  # top up from `live`
        pool = sorted(by_band.get("live", ()),
                      key=lambda row: ctl._hash_rank(SEED, row.key))
        for row in pool[ALLOCATION["live"]:]:
            if short <= 0:
                break
            picked.append(row)
            short -= 1
    assert len(picked) == n_total, len(picked)
    return sorted(picked, key=lambda row: row.key)


# ------------------------------------------------------------ the configs

def base_config(**overrides: Any) -> AnalyzerConfig:
    base = dict(arms=("subtract+offset",), rules=("sum",),
                rungs=("L0", "L1"), workers=WORKERS, seed=SEED,
                halo_cells=None, cover_fraction=0.9, max_generations=1,
                all_rules=True, metadata_known=True, ctx_mode="production",
                mix_scope_ladder=("footprint", "lane"), lane_mix_tiles=12,
                refused_arms=(), targets_from="sweep:c_parity_gap")
    base.update(overrides)
    return AnalyzerConfig(**base)


def certified_keys(ledger) -> set:
    return {row.key for row in ledger.rows
            if row.verdict in (VERDICT_CERTIFIED, VERDICT_CERTIFIED_LIST)}


def row_digest(row) -> dict:
    """The blind + oracle columns this measurement reads off one row."""
    out: dict[str, Any] = {
        "key": list(row.key), "band": row.band, "tx": row.tx, "ty": row.ty,
        "verdict": row.verdict, "certifying_rung": row.certifying_rung,
        "certifying_rule": row.certifying_rule,
        "source": row.source,
        "known_cells_in_halo": row.known_cells_in_halo,
        "n_discriminating_labels": row.n_discriminating_labels,
        "neighbours_certified": row.neighbours_certified,
        "siblings_certified": list(row.siblings_certified),
        "lanes": {}, "combined": {}, "rungs": {}, "oracle_lanes": {},
    }
    for name, blind in row.evidence.items():
        if name == "_selected":
            out["selected"] = jsonable(blind)
            continue
        out["lanes"][name] = {
            k: jsonable(v) for k, v in blind.items()
            if k in ("refusal", "offset_dots_xy", "mix_scope", "n_labels",
                     "n_labels_fit", "n_labels_search", "n_labels_select",
                     "n_discriminating", "n_observed", "n_calibrated",
                     "n_observed_cargo", "n_cargo_observed",
                     "ctx_adopted", "ctx_reason", "ctx_baseline_logloss",
                     "ctx_candidate_logloss",
                     "heldout_logloss_search", "heldout_logloss_select",
                     "offset_search_logloss", "mix_reason", "mix_accepted",
                     "field_applied", "field_reason", "extrapolating",
                     "labels_cleanable_fraction", "cargo_cleanable_fraction")}
    for rule, summary in row.combined.items():
        out["combined"][rule] = {
            k: jsonable(v) for k, v in summary.items()
            if k in ("n_captures", "levels_kept", "levels_dropped",
                     "n_paired_labels", "n_observed", "rule_effective",
                     "best_lane", "platt_weights", "error_correlation",
                     "n_disagreeing", "coefficients")}
    for rule, batch in row.rungs.items():
        if rule == "user_bits":
            continue
        out["rungs"][rule] = [
            {k: jsonable(v) for k, v in item.items()
             if k in ("rung", "verdict", "unsat_at_exit", "n_iters",
                      "syndrome_ok")} for item in batch]
    for name, scored in (row.diag or {}).get("evidence", {}).items():
        out["oracle_lanes"][name] = {
            k: jsonable(v) for k, v in scored.items()
            if k in ("auc", "d_prime", "R", "R_upper", "n_observed",
                     "cell_error_map", "cell_error_median", "I_hat",
                     "hard_error", "n_wrong")}
    return out


def run_config(run, truth, rows, targets, config, label: str) -> dict:
    started = time.perf_counter()
    ledger = fp.run(run, targets, config, census_rows=rows,
                    exposure=fp.shared_exposure())
    got = certified_keys(ledger)
    return {
        "label": label,
        "seconds": time.perf_counter() - started,
        "n_targets": len(targets),
        "n_certified": len(got),
        "certified": sorted([list(k) for k in got]),
        "rows": [row_digest(row) for row in ledger.rows],
    }


def write(name: str, payload: Any) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(json.dumps(jsonable(payload), indent=1), "utf-8")
    print(f"wrote {path}", flush=True)


# ---------------------------------------------------------------- phase A

def phase_a(run, truth, rows) -> dict:
    sample = c_sample(rows)
    result = run_config(run, truth, rows, sample, base_config(), "default")
    got = {tuple(k) for k in map(tuple, result["certified"])}
    missed = [list(row.key) for row in sample if tuple(row.key) not in got]
    result["sample"] = [{"key": list(row.key), "band": row.band,
                         "tx": row.tx, "ty": row.ty, "source": row.source}
                        for row in sample]
    result["missed"] = missed
    by_band: dict[str, list[int]] = {}
    for row in sample:
        hit = tuple(row.key) in got
        entry = by_band.setdefault(row.band, [0, 0])
        entry[0] += int(hit)
        entry[1] += 1
    result["by_band"] = {k: {"re_derived": v[0], "n": v[1],
                             "rate": v[0] / v[1]} for k, v in by_band.items()}
    return result


# ---------------------------------------------------------------- phase B

def ppc_filtered(run, ppc: int):
    """A `RunInputs` whose only lanes are the level at `ppc` (DESIGN §4.2)."""
    lanes = tuple(lane for lane in run.lanes if lane.ppc == Fraction(ppc))
    cache = {k: v for k, v in run._cache.items()
             if k not in ("page_tile_coverage",)}
    return dc_replace(run, lanes=lanes, _cache=cache)


def ablations() -> list[tuple[str, dict]]:
    """One factor at a time from the default, plus two upper bounds."""
    return [
        ("halo32", dict(halo_cells={"C": 32, "M": 32, "Y": 32})),
        ("halo48", dict(halo_cells={"C": 48, "M": 48, "Y": 48})),
        ("mix_lane12", dict(mix_scope_ladder=("lane",), lane_mix_tiles=12)),
        ("mix_lane40", dict(mix_scope_ladder=("lane",), lane_mix_tiles=40)),
        ("ctx_known", dict(ctx_mode="ctx-known")),
        ("ctx_none", dict(ctx_mode="none")),
        ("rules_all", dict(rules=("sum", "best", "platt", "corr"))),
        ("arm_committed", dict(arms=("subtract+committed",))),
        ("arm_head_offset", dict(arms=("head+offset",))),
        ("arm_global_offset", dict(arms=("global+offset",))),
        ("arm_conditional_offset", dict(arms=("conditional+offset",))),
        ("arm_field_offset", dict(arms=("subtract+field+offset",))),
        ("arm_affine", dict(arms=("subtract+affine",))),
        ("arm_word", dict(arms=("subtract+word",))),
        ("l2_on", dict(rungs=("L0", "L1", "L2"))),
        ("ladder_full", dict(rungs=("L0", "L1", "L2", "L4", "L3", "L7"))),
        ("battery_all", dict(arms=DEFAULT_ARMS,
                             rules=("sum", "best", "platt", "corr"),
                             rungs=("L0", "L1", "L2", "L4", "L3", "L7"))),
    ]


def extra_ablations() -> list[tuple[str, dict]]:
    """Round two: the branch split of DESIGN §4.7, and the pairs it enters."""
    pooled = {"branches": "pooled"}
    return [
        ("branches_pooled", dict(knobs=pooled)),
        ("branches_pooled_halo32", dict(knobs=pooled,
                                        halo_cells={"C": 32, "M": 32,
                                                    "Y": 32})),
        ("branches_pooled_halo48", dict(knobs=pooled,
                                        halo_cells={"C": 48, "M": 48,
                                                    "Y": 48})),
        ("halo48_rules_all", dict(halo_cells={"C": 48, "M": 48, "Y": 48},
                                  rules=("sum", "best", "platt", "corr"))),
        ("halo48_ctx_none", dict(halo_cells={"C": 48, "M": 48, "Y": 48},
                                 ctx_mode="none")),
        ("halo48_pooled_rules_all",
         dict(knobs=pooled, halo_cells={"C": 48, "M": 48, "Y": 48},
              rules=("sum", "best", "platt", "corr"))),
        ("halo64", dict(halo_cells={"C": 64, "M": 64, "Y": 64})),
        ("halo48_head_offset", dict(halo_cells={"C": 48, "M": 48, "Y": 48},
                                    arms=("head+offset",))),
    ]


def phase_b(run, truth, rows, missed: list, only: str | None = None,
            table: str = "b") -> dict:
    by_key = {row.key: row for row in rows}
    targets = [by_key[tuple(k)] for k in missed]
    out: dict[str, Any] = {"n_missed": len(targets), "runs": {}}
    for label, overrides in (ablations() if table == "b"
                             else extra_ablations()):
        if only is not None and label != only:
            continue
        result = run_config(run, truth, rows, targets,
                            base_config(**overrides), label)
        out["runs"][label] = result
        print(f"  {label}: {result['n_certified']}/{len(targets)} "
              f"in {result['seconds']:.0f}s", flush=True)
    for ppc in ((8, 4) if table == "b" else ()):
        label = f"lanes_ppc{ppc}"
        if only is not None and label != only:
            continue
        filtered = ppc_filtered(run, ppc)
        result = run_config(filtered, truth, rows, targets,
                            base_config(), label)
        out["runs"][label] = result
        print(f"  {label}: {result['n_certified']}/{len(targets)} "
              f"in {result['seconds']:.0f}s", flush=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="A")
    parser.add_argument("--only", default=None)
    args = parser.parse_args()
    run, truth, rows = load()
    print("loaded", flush=True)
    if args.phase == "A":
        write("phase-A.json", phase_a(run, truth, rows))
    elif args.phase in ("B", "B2"):
        missed = json.loads((OUT / "phase-A.json").read_text())["missed"]
        stem = "phase-" + args.phase
        name = (f"{stem}.json" if args.only is None
                else f"{stem}-{args.only}.json")
        write(name, phase_b(run, truth, rows, missed, only=args.only,
                            table="b" if args.phase == "B" else "b2"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
