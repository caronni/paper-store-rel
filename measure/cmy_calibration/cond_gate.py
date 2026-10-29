"""G13's channel — the construction constant alpha* of the conditioned-decode gate (CMY-RECEIVER-PLAN A6).

What: one TRIAL is one fresh tile of a cmy row `c2-cmy-r{hi}x{lo}@10x10` built by G13's own stimulus
(`holo.receiver.tests.test_h3_cmy_cond.g13_tile`, imported, so the calibrated channel IS the test's): random user
bits per label stream through the receiver's frame encoder XOR the row's dither, the two label bits to a state per
payload cell, every state READ through the hard-decision channel
    C_alpha = (1 - alpha) * I + alpha * C_hat,
C_hat e043c sheet 3's row-normalised state confusion of one c2 band (B1 or B14, W C M Y; the counts are the test
module's `E043C_CONFUSION_COUNTS`, checked here against the readout's `summary.json`), each cell scored by the
channel's exact log-likelihood ratios against W, the scores through the tile's cell permutation onto its payload
cells.  The cut is attempted by the PRODUCTION `tiles.attempt_tile`: the SIBLING stream plain at the scan budget
(60), the TARGET stream BICM at 60 and at the retry budget (150), and the target CONDITIONED on the sibling's true
label bits (`cmy_soft_demap(scores, stream, sibling)`) at 60 and 150.  Two orders: HI given LO (the target hi, the
row's hi rung above its lo rung) and LO given HI.  A CRC-passing attempt whose user bits differ is a FALSE ACCEPT;
a syndrome-valid attempt the CRC refuses is counted.
Why: on a measured confusion the conditioning gain is under one rung step (CMY-DESIGN §11 G13), so a fixed rung
rarely separates the two decodes; G13 needs a channel on which BICM fails and the conditioned attempt certifies,
with rung and alpha chosen BEFORE the test and on seeds disjoint from its own (CAL_ROOT here, the test's root in
test_h3_cmy_cond).  The construction criteria: target BICM BLER >= 0.9 at 150 (success at 60 implies success at
150: BP is deterministic and stops at the first valid syndrome, so failing at 150 is failing both unconditioned
stages), conditioned BLER <= 0.1 at the cond budget, sibling BLER <= 0.05 at 60.
How: common random numbers -- a trial's entropy is (root, index), its user bits and its one uniform per cell drawn
from it, read through each C_alpha's inverse CDF, so every alpha of a trial shares its bits and noise; trials on a
thread pool (the free-threaded interpreter runs the decoder in parallel).  Stages, each on its own seed root:
  sweep    every candidate row of both orders x the coarse alpha grid x both shapes, 24 trials -> cond_gate.json
  refine   per order the rows with a NEAR-feasible coarse cell (both shapes: BICM >= 0.75, cond <= 0.25, sibling
           <= 0.10), a 1/32 alpha grid from 1/8 below the first such cell to 1/8 above the last, 64 trials
           -> cond_gate_refine.json, and THE PICK
  confirm  per order the refine's picked row over its whole feasible alpha window, 256 trials
           -> cond_gate_confirm.json, and ALPHA*
  report   the tables of the RESULTS file from the three JSONs
The refine's pick (written before the refine ran, after a pilot of the sweep stage -- scratch2/e043c/cond/pilot-v1-*
-- showed single-point feasible windows): over the refine grid, the cell pair (both shapes) with the largest MARGIN,
the smaller over its shapes of min(BICM - 0.9, 0.1 - cond) at the cond budget, a cell whose sibling misses 0.05 out;
feasible iff the margin is >= 0; ties: the higher target rung, then the median tied alpha.  ALPHA* (written after a
first confirm of the refine's single alpha missed the sibling criterion on one shape, 15/256 against 0.05 --
scratch2/e043c/cond/first-confirm-*; G13's seeds untouched): over the confirm cells, the largest FULL margin
min(BICM - 0.9, 0.1 - cond, 0.05 - sibling) on both shapes; ties: the median tied alpha.

    cd <repo> && PYTHONPATH=src:. \\
        env/bin/python -u -m measure.cmy_calibration.cond_gate --stage sweep --workers 8
    ... --stage refine --workers 8
    ... --stage confirm --workers 8
    ... --stage report
Artefacts: scratch2/e043c/cond/ (cond_gate.json, cond_gate_refine.json,
cond_gate_confirm.json, the logs).
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from holo.receiver.format import identity
from holo.receiver.plugins import tiles
from holo.receiver.tests import test_h3_cmy_cond as g13

REPO_MAIN = Path("<repo>")
READOUT = REPO_MAIN / "scratch2" / "e043c" / "readout" / "summary.json"
ART = REPO_MAIN / "scratch2" / "e043c" / "cond"
SHAPES = g13.SHAPES
ORDERS = g13.ORDERS
#: (hi rung, lo rung): the target's rung above the sibling's, both orders mirrored.
ROWS: dict[str, tuple[tuple[str, str], ...]] = {
    "hi|lo": (("r0625", "r0547"), ("r0700", "r0547"), ("r0700", "r0625"), ("r0775", "r0625"),
              ("r0775", "r0700"), ("r0850", "r0700"), ("r0850", "r0775")),
    "lo|hi": (("r0547", "r0625"), ("r0547", "r0700"), ("r0625", "r0700"), ("r0625", "r0775"),
              ("r0700", "r0775"), ("r0700", "r0850"), ("r0775", "r0850")),
}
ALPHAS = tuple(round(0.25 + 0.125 * step, 3) for step in range(23))
FINE_STEP = 1.0 / 32.0
FINE_PAD = 0.125
CAL_ROOT = 20261012_13
CONFIRM_ROOT = 20261012_14
REFINE_ROOT = 20261012_15
SWEEP_TRIALS = 24
REFINE_TRIALS = 64
CONFIRM_TRIALS = 256
BICM_MIN_BLER = 0.9
COND_MAX_BLER = 0.1
SIBLING_MAX_BLER = 0.05
#: A coarse cell worth refining around: (BICM >=, cond <=, sibling <=) on both shapes.
NEAR = (0.75, 0.25, 0.10)
Rec = dict[str, Any]


def confusion(shape: str, readout: Path = READOUT) -> np.ndarray:
    """One band's state confusion counts (true W C M Y x read W C M Y) from the readout of record."""
    bands = {band["name"]: band for band in json.loads(readout.read_text())["scans"][0]["bands"]}
    return np.asarray(bands[shape]["confusion"], np.int64)


def row_ref(rungs: tuple[str, str]) -> str:
    return f"c2-cmy-{rungs[0]}x{rungs[1][1:]}@10x10"


def row_and_geometry(rungs: tuple[str, str]) -> tuple[identity.FormatRow, identity.SiteGeometry]:
    row = identity.resolve_format_ref(row_ref(rungs))
    return row, identity.build_site_geometry(row)


def attempt_outcome(row: identity.FormatRow, geometry: identity.SiteGeometry, cut: tiles.TileCut, stream_id: str,
                    user: np.ndarray, sibling: np.ndarray | None = None) -> Rec:
    """60 first, 150 only after a failure at 60 (the stage names select the budget alone); ok = certified with the
    true user bits."""
    out: Rec = {}
    for budget, stage in ((60, tiles.STAGE_SCAN), (150, tiles.STAGE_RETRY150)):
        result = tiles.attempt_tile(row, geometry, (cut,), stream_id, stage, sibling=sibling)
        ok = result.certificate is not None and np.array_equal(result.certificate.user_bits, user)
        out[f"ok{budget}"] = bool(ok)
        out[f"false_accept{budget}"] = bool(result.certificate is not None and not ok)
        out[f"crc_refused{budget}"] = bool(result.fact.syndrome_ok and result.fact.crc_ok is False)
        if result.certificate is not None:
            out.update({f"ok{150}": bool(ok), f"false_accept{150}": out[f"false_accept{budget}"],
                        f"crc_refused{150}": False})
            break
    return out


def trial(rungs: tuple[str, str], order: str, shape: str, alphas: tuple[float, ...], root: int, index: int,
          row: identity.FormatRow, geometry: identity.SiteGeometry) -> list[Rec]:
    address = g13.g13_address(index, row)
    target, sibling = g13.TARGET_OF[order]
    records = []
    for alpha in alphas:
        tile = g13.g13_tile(row, geometry, address, g13.g13_channel(shape, alpha), (root, index))
        sib = attempt_outcome(row, geometry, tile.cut, sibling, tile.users[sibling])
        bicm = attempt_outcome(row, geometry, tile.cut, target, tile.users[target])
        cond = attempt_outcome(row, geometry, tile.cut, target, tile.users[target], sibling=tile.labels[sibling])
        records.append({"rungs": list(rungs), "order": order, "shape": shape, "alpha": alpha, "index": index,
                        "sibling": sib, "bicm": bicm, "cond": cond})
    return records


def summarise(records: list[Rec]) -> list[Rec]:
    cells: dict[tuple, list[Rec]] = {}
    for rec in records:
        cells.setdefault((tuple(rec["rungs"]), rec["order"], rec["shape"], rec["alpha"]), []).append(rec)
    out = []
    for (rungs, order, shape, alpha), group in sorted(cells.items()):
        n = len(group)

        def bler(arm: str, budget: int) -> float:
            return 1.0 - sum(rec[arm][f"ok{budget}"] for rec in group) / n

        out.append({"rungs": list(rungs), "order": order, "shape": shape, "alpha": alpha, "n": n,
                    "sibling_bler60": bler("sibling", 60), "bicm_bler60": bler("bicm", 60),
                    "bicm_bler150": bler("bicm", 150), "cond_bler60": bler("cond", 60),
                    "cond_bler150": bler("cond", 150),
                    "false_accepts": sum(rec[arm][f"false_accept{b}"] for rec in group
                                         for arm in ("sibling", "bicm", "cond") for b in (60, 150)),
                    "crc_refused": sum(rec[arm][f"crc_refused{b}"] for rec in group
                                       for arm in ("sibling", "bicm", "cond") for b in (60, 150))})
    return out


def margin(cell: Rec, cond_budget: int) -> float:
    """How far a cell clears the two decode criteria; -inf where the sibling does not certify plainly."""
    if cell["sibling_bler60"] > SIBLING_MAX_BLER:
        return float("-inf")
    return min(cell["bicm_bler150"] - BICM_MIN_BLER, COND_MAX_BLER - cell[f"cond_bler{cond_budget}"])


def target_rung(order: str, rungs: tuple[str, str]) -> str:
    return rungs[0] if order == "hi|lo" else rungs[1]


def pairs(summary: list[Rec], order: str) -> dict[tuple[tuple[str, str], float], dict[str, Rec]]:
    """(rungs, alpha) -> shape -> cell, for the cells measured on every shape."""
    out: dict[tuple[tuple[str, str], float], dict[str, Rec]] = {}
    for cell in summary:
        if cell["order"] == order:
            out.setdefault((tuple(cell["rungs"]), cell["alpha"]), {})[cell["shape"]] = cell
    return {key: cells for key, cells in out.items() if set(cells) == set(SHAPES)}


def near_windows(summary: list[Rec]) -> dict[str, list[tuple[tuple[str, str], tuple[float, ...]]]]:
    """Per order, each row's fine alpha grid around its near-feasible coarse cells."""
    out: dict[str, list[tuple[tuple[str, str], tuple[float, ...]]]] = {}
    for order in ORDERS:
        near: dict[tuple[str, str], list[float]] = {}
        for (rungs, alpha), cells in pairs(summary, order).items():
            if all(c["bicm_bler150"] >= NEAR[0] and c["cond_bler150"] <= NEAR[1] and c["sibling_bler60"] <= NEAR[2]
                   for c in cells.values()):
                near.setdefault(rungs, []).append(alpha)
        for rungs in ROWS[order]:
            if rungs in near:
                low = max(FINE_STEP, min(near[rungs]) - FINE_PAD)
                count = int(round((max(near[rungs]) + FINE_PAD - low) / FINE_STEP)) + 1
                out.setdefault(order, []).append(
                    (rungs, tuple(round(low + FINE_STEP * step, 5) for step in range(count))))
    return out


def pick(summary: list[Rec], cond_budget: int) -> dict[str, Rec]:
    """Per order: the largest margin over both shapes; ties the higher target rung, then the median tied alpha."""
    chosen: dict[str, Rec] = {}
    for order in ORDERS:
        scored = sorted(((min(margin(c, cond_budget) for c in cells.values()), target_rung(order, rungs), rungs,
                          alpha) for (rungs, alpha), cells in pairs(summary, order).items()), reverse=True)
        if not scored or scored[0][0] < 0.0:
            continue
        best_margin, best_rung, rungs, _alpha = scored[0]
        tied = sorted(alpha for m, r, rr, alpha in scored if m == best_margin and r == best_rung and rr == rungs)
        feasible = sorted(alpha for m, _r, rr, alpha in scored if rr == rungs and m >= 0.0)
        chosen[order] = {"rungs": list(rungs), "row": row_ref(rungs), "alpha": tied[(len(tied) - 1) // 2],
                         "margin": best_margin, "tied_alphas": tied, "feasible_alphas": feasible}
    return chosen


def check_confusions() -> None:
    """The test's literal counts are the readout's, band for band."""
    for shape in SHAPES:
        if not np.array_equal(confusion(shape), np.asarray(g13.E043C_CONFUSION_COUNTS[shape], np.int64)):
            raise SystemExit(f"{shape}: test_h3_cmy_cond.E043C_CONFUSION_COUNTS differs from {READOUT}")


def run_trials(jobs: list[tuple], workers: int) -> list[Rec]:
    records: list[Rec] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for batch in pool.map(lambda job: trial(*job), jobs):
            records.extend(batch)
    return records


def stage_sweep(art: Path, n_trials: int, workers: int) -> Rec:
    started = time.time()
    check_confusions()
    built = {rungs: row_and_geometry(rungs) for order in ORDERS for rungs in ROWS[order]}
    jobs = [(rungs, order, shape, ALPHAS, CAL_ROOT, index, *built[rungs])
            for order in ORDERS for rungs in ROWS[order] for shape in SHAPES for index in range(n_trials)]
    summary = summarise(run_trials(jobs, workers))
    doc = {"stage": "sweep", "root": CAL_ROOT, "n_trials": n_trials, "alphas": list(ALPHAS),
           "readout": str(READOUT), "confusions": {s: confusion(s).tolist() for s in SHAPES},
           "test_roots": {"g13": g13.G13_SEED_ROOT}, "summary": summary, "near": near_windows(summary),
           "wall_s": round(time.time() - started, 1)}
    (art / "cond_gate.json").write_text(json.dumps(doc, indent=1))
    return doc


def stage_refine(art: Path, n_trials: int, workers: int, cond_budget: int) -> Rec:
    started = time.time()
    near = {order: [(tuple(rungs), tuple(alphas)) for rungs, alphas in windows]
            for order, windows in json.loads((art / "cond_gate.json").read_text())["near"].items()}
    check_confusions()
    built = {rungs: row_and_geometry(rungs) for windows in near.values() for rungs, _alphas in windows}
    jobs = [(rungs, order, shape, alphas, REFINE_ROOT, index, *built[rungs])
            for order, windows in near.items() for rungs, alphas in windows for shape in SHAPES
            for index in range(n_trials)]
    summary = summarise(run_trials(jobs, workers))
    doc = {"stage": "refine", "root": REFINE_ROOT, "n_trials": n_trials, "cond_budget": cond_budget,
           "near": {order: [[list(r), list(a)] for r, a in w] for order, w in near.items()}, "summary": summary,
           "pick": pick(summary, cond_budget), "pick_cond60": pick(summary, 60),
           "wall_s": round(time.time() - started, 1)}
    (art / "cond_gate_refine.json").write_text(json.dumps(doc, indent=1))
    return doc


def full_margin(cell: Rec, cond_budget: int) -> float:
    return min(cell["bicm_bler150"] - BICM_MIN_BLER, COND_MAX_BLER - cell[f"cond_bler{cond_budget}"],
               SIBLING_MAX_BLER - cell["sibling_bler60"])


def alpha_star(summary: list[Rec], cond_budget: int) -> dict[str, Rec]:
    """Per order: the confirm cell with the largest full margin on both shapes; ties the median tied alpha."""
    chosen: dict[str, Rec] = {}
    for order in ORDERS:
        scored = sorted((min(full_margin(c, cond_budget) for c in cells.values()), alpha, rungs)
                        for (rungs, alpha), cells in pairs(summary, order).items())
        if not scored or scored[-1][0] < 0.0:
            continue
        best = scored[-1][0]
        tied = sorted(alpha for m, alpha, _rungs in scored if m == best)
        chosen[order] = {"rungs": list(scored[-1][2]), "row": row_ref(scored[-1][2]),
                         "alpha": tied[(len(tied) - 1) // 2], "full_margin": best, "tied_alphas": tied}
    return chosen


def stage_confirm(art: Path, n_trials: int, workers: int) -> Rec:
    started = time.time()
    refine = json.loads((art / "cond_gate_refine.json").read_text())
    picked = refine["pick"]
    check_confusions()
    built = {order: row_and_geometry(tuple(choice["rungs"])) for order, choice in picked.items()}
    jobs = [(tuple(choice["rungs"]), order, shape, tuple(choice["feasible_alphas"]), CONFIRM_ROOT, index,
             *built[order])
            for order, choice in picked.items() for shape in SHAPES for index in range(n_trials)]
    summary = summarise(run_trials(jobs, workers))
    doc = {"stage": "confirm", "root": CONFIRM_ROOT, "n_trials": n_trials, "cond_budget": refine["cond_budget"],
           "pick": picked, "summary": summary, "alpha_star": alpha_star(summary, refine["cond_budget"]),
           "wall_s": round(time.time() - started, 1)}
    (art / "cond_gate_confirm.json").write_text(json.dumps(doc, indent=1))
    return doc


HEAD = ("| order | row | shape | alpha | sibling@60 | BICM@60 | BICM@150 | cond@60 | cond@150 | false accepts | "
        "CRC-refused |")


def table(summary: list[Rec]) -> list[str]:
    out = [HEAD, "|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in summary:
        out.append(f"| {c['order']} | {row_ref(tuple(c['rungs']))} | {c['shape']} | {c['alpha']} | "
                   f"{c['sibling_bler60']:.3f} | {c['bicm_bler60']:.3f} | {c['bicm_bler150']:.3f} | "
                   f"{c['cond_bler60']:.3f} | {c['cond_bler150']:.3f} | {c['false_accepts']} | {c['crc_refused']} |")
    return out


def report(art: Path, full: bool = False) -> str:
    out: list[str] = []
    for name in ("cond_gate.json", "cond_gate_refine.json", "cond_gate_confirm.json"):
        path = art / name
        if not path.exists():
            continue
        doc = json.loads(path.read_text())
        out.append(f"\n## {doc['stage']}: root {doc['root']}, {doc['n_trials']} trials per cell, {doc['wall_s']} s")
        if "near" in doc:
            out.append(f"near-feasible windows: {json.dumps(doc['near'])}")
        if "pick" in doc:
            out.append(f"pick: {json.dumps(doc['pick'])}")
        if "pick_cond60" in doc:
            out.append(f"pick at cond budget 60: {json.dumps(doc['pick_cond60'])}")
        if "alpha_star" in doc:
            out.append(f"alpha*: {json.dumps(doc['alpha_star'])}")
        rows = doc["summary"] if full or doc["stage"] != "sweep" else [
            c for c in doc["summary"] if 0.0 < c["bicm_bler150"] and c["cond_bler150"] < 1.0]
        out += table(rows)
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True, choices=("sweep", "refine", "confirm", "report"))
    ap.add_argument("--art", type=Path, default=ART)
    ap.add_argument("--trials", type=int, default=None,
                    help=f"per cell (sweep {SWEEP_TRIALS}, refine {REFINE_TRIALS}, confirm {CONFIRM_TRIALS})")
    ap.add_argument("--cond-budget", type=int, default=150, choices=(60, 150), help="refine: the pick's budget")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--full", action="store_true", help="report: every sweep cell (default: the informative ones)")
    a = ap.parse_args()
    a.art.mkdir(parents=True, exist_ok=True)
    if a.stage == "sweep":
        stage_sweep(a.art, a.trials or SWEEP_TRIALS, a.workers)
    elif a.stage == "refine":
        stage_refine(a.art, a.trials or REFINE_TRIALS, a.workers, a.cond_budget)
    elif a.stage == "confirm":
        stage_confirm(a.art, a.trials or CONFIRM_TRIALS, a.workers)
    print(report(a.art, a.full))


if __name__ == "__main__":
    main()
