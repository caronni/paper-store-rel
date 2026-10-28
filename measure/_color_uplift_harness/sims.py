"""B7/B8 baseline sims — pack7 thresholds under the pre-registered protocol.

Lead-owned (COLOR-UPLIFT-PLAN §4 bars B7/B8): baselines are pinned from THIS
module BEFORE any P3/P4 candidate exists; candidates later rerun the same
protocol and are judged against these JSONs.

B7 channel (honest per-plane BSC): every C/M/Y presence bit flips
independently with probability p; the six W-relative state scores are the
exact log-likelihoods of that model. Protocol: per (p, seed) decode
``TILES_PER_BATCH`` tiles through the real format path (interleave, dither,
codebook, three-child LDPC bank, BASELINE_BP_MAX_ITERS/BP_ALPHA); a seed
PASSES iff all tiles certify (CRC). p* = max p with >= ``SEED_PASS_FLOOR``
of ``N_SEEDS`` seeds passing.

B8 channel (erasure sim, lead-defined 2026-08-07): B7's BSC(p) plus
independent per-CELL erasure with probability f (cell unobserved); the
demapper's CURRENT whole-pack semantics apply (any unobserved slot erases
the 11-bit pack). Baseline = current code; the PK9 candidate must strictly
dominate on the same grid.

Determinism: every RNG is seeded from (BASE_SEED, channel, p-index,
f-index, seed-index). No timestamps, no unseeded draws.

CANDIDATE ARMS (PK8/PK9). ``--demap-iters N`` runs P3's demap<->BP loop
through the PRODUCTION function the receiver calls
(``color_tile.cmy7_iterated_decode``) rather than a sim-side copy.
``--erasure-floor X`` runs P4's margin gate, which is RETIRED from the
receiver as a measured negative (MEASUREMENTS 13.10) and therefore lives
HERE, in the harness, three lines over the surviving primitive
``channel.state_score_margins`` — a retired arm keeps its sweep
reproducible without keeping its seam in production.
``--demap-iters 1 --erasure-floor 0`` is the pinned baseline and reproduces
``sims-baseline.json`` exactly: the channel draws are untouched, in the same
order, so an arm differs from the baseline only where the codec does.

Run (from the worktree root, ~15-40 min at 8 workers for the full grid):
  PYTHONPATH=src:measure env/bin/python \
      -m _color_uplift_harness.sims --workers 8 \
      --out scratch/color-uplift/runs/sims-baseline.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import resource
import time
from pathlib import Path

import numpy as np

from holo.core import channel, color_tile, keystream
from holo.core.ldpc.frame import decode_frame
from holo.format.registry import get_format_row
from holo.receive import tiles

SPEC_ID = "c2-cmy7-p120-v0@3328x2304"
BASE_SEED = 20260807
TILES_PER_BATCH = 24
N_SEEDS = 20
SEED_PASS_FLOOR = 19
B7_P_GRID = (0.010, 0.015, 0.020, 0.0225, 0.025, 0.0275, 0.030, 0.035)
B8_P_GRID = (0.010, 0.020)
B8_F_GRID = (0.00, 0.05, 0.10, 0.20, 0.30)

_STATE_BITS = np.array(
    [[(s >> k) & 1 for k in range(3)] for s in range(7)], np.int8)


_SRC_HOLO = Path(__file__).resolve().parents[2] / "src" / "holo"


def _receiver_tree_sha256() -> str:
    """SHA-256 over every source file under ``src/holo`` — content only.

    A shared worktree can move under a run (COLOR-UPLIFT-MEASUREMENTS 8.5),
    so an arm's numbers carry the code that produced them.
    """
    digest = hashlib.sha256()
    for path in sorted(_SRC_HOLO.rglob("*.py")):
        digest.update(str(path.relative_to(_SRC_HOLO)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _decode_batch(p: float, f: float, seed: int,
                  demap_iters: int = 1, erasure_floor: float = 0.0) -> dict:
    """Decode one 24-tile batch; return per-batch facts."""
    spec = get_format_row(SPEC_ID)
    profile = spec.stream_profiles[0]
    n_code = profile.fec.transmitted_bits
    rng = np.random.default_rng((BASE_SEED, int(p * 1e6), int(f * 1e6), seed))
    lam = float(np.log((1.0 - p) / p)) if p > 0 else 30.0
    crc_ok = 0
    floor_refused = 0
    cell_errors = 0
    cells = 0
    margin_erased = 0
    bp_iters = 0
    for tile in range(TILES_PER_BATCH):
        counter = tile
        interleave = keystream.cmy7_interleave_permutation(
            spec.seed, counter, n_code)
        dither = keystream.cmy7_dither_bits(spec.seed, counter, n_code)
        user = rng.integers(0, 2, profile.fec.user_bits, dtype=np.uint8)
        states = color_tile.cmy7_encode_payload(
            user, profile.fec, interleave, dither)
        truth = _STATE_BITS[states]
        observed_bits = truth ^ (rng.random(truth.shape) < p).astype(np.int8)
        signed = np.where(observed_bits == 1, lam, -lam)
        scores = signed @ _STATE_BITS[1:].T.astype(np.float64)
        observed_slots = (
            rng.random(states.size) >= f).astype(np.uint8)
        pred = np.argmax(np.concatenate(
            [np.zeros((scores.shape[0], 1)), scores], axis=1), axis=1)
        keep = observed_slots.astype(bool)
        cell_errors += int((pred[keep] != states[keep]).sum())
        cells += int(keep.sum())
        # P4 (RETIRED, harness-only): erase a slot whose winner is not
        # `erasure_floor` ahead, into a COPY -- the physical observation is
        # never rewritten, which is what kept `n_informative` honest when
        # this still had a production seam.
        demap_slots = observed_slots
        if erasure_floor > 0.0:
            demap_slots = observed_slots.copy()
            demap_slots[
                channel.state_score_margins(scores) < erasure_floor] = 0
        margin_erased += int(np.count_nonzero(
            observed_slots.astype(bool) & ~demap_slots.astype(bool)))
        try:
            llrs = color_tile.cmy7_demap_payload(
                scores, demap_slots, profile.fec, interleave, dither)
        except ValueError:
            floor_refused += 1
            continue
        if demap_iters == 1:
            outcome = decode_frame(
                llrs, profile.fec, max_iters=tiles.BASELINE_BP_MAX_ITERS,
                alpha=tiles.BP_ALPHA)
        else:
            outcome = color_tile.cmy7_iterated_decode(
                llrs, scores, demap_slots, profile.fec, interleave, dither,
                max_iters=tiles.BASELINE_BP_MAX_ITERS, alpha=tiles.BP_ALPHA,
                demap_iterations=demap_iters)
        bp_iters += sum(child.n_iters for child in outcome.children)
        crc_ok += bool(outcome.crc_ok)
    return {
        "p": p, "f": f, "seed": seed, "crc_ok": crc_ok,
        "tiles": TILES_PER_BATCH, "all_pass": crc_ok == TILES_PER_BATCH,
        "floor_refused": floor_refused,
        "cell_error_rate": cell_errors / max(cells, 1),
        "margin_erased": margin_erased,
        "bp_iters": bp_iters,
    }


def _point(args: tuple) -> dict:
    return _decode_batch(*args)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--demap-iters", type=int, default=1,
        help="P3 candidate: demap<->BP iterations inside one attempt "
             "(1 = the pinned baseline path)")
    parser.add_argument(
        "--erasure-floor", type=float, default=0.0,
        help="P4 candidate: erase a slot whose top1-top2 state margin is "
             "below this (0 = the pinned baseline path)")
    parser.add_argument(
        "--grid", choices=("both", "b7", "b8"), default="both",
        help="which pinned grid to run; the grids themselves never change")
    parser.add_argument(
        "--arm", default=None,
        help="label recorded in the run JSON")
    args = parser.parse_args()

    knobs = (args.demap_iters, args.erasure_floor)
    work: list[tuple] = []
    if args.grid in ("both", "b7"):
        for p in B7_P_GRID:
            work += [(p, 0.0, s, *knobs) for s in range(N_SEEDS)]
    if args.grid in ("both", "b8"):
        for p in B8_P_GRID:
            for f in B8_F_GRID:
                if f == 0.0:
                    continue  # covered by the B7 grid at p in B8_P_GRID
                work += [(p, f, s, *knobs) for s in range(N_SEEDS)]

    start = time.process_time()
    # The work happens in pool CHILDREN, whose CPU `process_time` cannot
    # see (it reads this thread only, so it used to report ~0 and made the
    # honest cost look free).  RUSAGE_CHILDREN accumulates every reaped
    # child, which is exactly the pool.
    children0 = resource.getrusage(resource.RUSAGE_CHILDREN)
    wall0 = time.monotonic()
    with multiprocessing.Pool(args.workers) as pool:
        rows = pool.map(_point, work)
    children1 = resource.getrusage(resource.RUSAGE_CHILDREN)

    def _summary(grid_rows: list[dict]) -> dict:
        keyed: dict = {}
        for row in grid_rows:
            keyed.setdefault((row["p"], row["f"]), []).append(row)
        out = {}
        for (p, f), batch in sorted(keyed.items()):
            passes = sum(row["all_pass"] for row in batch)
            out[f"p={p:.4f},f={f:.2f}"] = {
                "seeds_all_pass": passes,
                "seeds": len(batch),
                "meets_floor": passes >= SEED_PASS_FLOOR,
                "crc_ok_total": sum(row["crc_ok"] for row in batch),
                "tiles_total": sum(row["tiles"] for row in batch),
                "mean_cell_error": float(np.mean(
                    [row["cell_error_rate"] for row in batch])),
                "margin_erased": sum(
                    row.get("margin_erased", 0) for row in batch),
                "bp_iters": sum(row.get("bp_iters", 0) for row in batch),
            }
        return out

    b7_rows = [row for row in rows if row["f"] == 0.0]
    b7 = _summary(b7_rows)
    passing = [row["p"] for row in b7_rows
               if b7[f"p={row['p']:.4f},f=0.00"]["meets_floor"]]
    b7_p_star = max(passing) if passing else None

    result = {
        "spec_id": SPEC_ID,
        "base_seed": BASE_SEED,
        "protocol": {
            "tiles_per_batch": TILES_PER_BATCH, "n_seeds": N_SEEDS,
            "seed_pass_floor": SEED_PASS_FLOOR,
            "b7_p_grid": B7_P_GRID,
            "b8_p_grid": B8_P_GRID, "b8_f_grid": B8_F_GRID,
        },
        "candidate": {
            "demap_iters": int(args.demap_iters),
            "erasure_floor": float(args.erasure_floor),
            "grid": args.grid,
        },
        "b7": b7,
        "b7_baseline_p_star": b7_p_star,
        "b8": _summary([row for row in rows if row["f"] > 0.0]),
        # Total CPU = this process plus every pool child.  The parent-only
        # number is kept beside it so an old row stays comparable.
        "cpu_s": (
            (time.process_time() - start)
            + (children1.ru_utime - children0.ru_utime)
            + (children1.ru_stime - children0.ru_stime)),
        "cpu_s_parent_only": time.process_time() - start,
        "wall_s": time.monotonic() - wall0,
        "workers": int(args.workers),
        "arm": args.arm or (
            "baseline"
            if (args.demap_iters, args.erasure_floor) == (1, 0.0)
            else f"demapiters{args.demap_iters}-floor{args.erasure_floor}"),
        "receiver_tree_sha256": _receiver_tree_sha256(),
    }
    Path(args.out).write_text(json.dumps(result, indent=1))
    print(json.dumps({"b7_p_star": b7_p_star, "arm": result["arm"],
                      "points": len(rows), "wall_s": result["wall_s"]}))


if __name__ == "__main__":
    main()
