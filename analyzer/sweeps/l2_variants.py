"""Sweep the L2 (belief-propagation) variants of `analyzer.mother` (DESIGN §6).

A synthetic measurement, not a module of the package: it builds one frame per
rate with the test builder `analyzer.tests._synthetic`, pushes it through a
calibrated bi-AWGN channel at hard-error rates straddling each rate's
waterfall, and runs every (mode, lam, beta, iters) variant of `mother.bp` on
the SAME realizations, gated by `mother.gate` (syndrome + CRC).

The comparison is paired by construction: for a given (rate, p) every variant
sees the identical 20 LLR vectors, so a certify-count difference is the
decoder, never the draw.

Run:
    PYTHONPATH=src:. env/bin/python -m analyzer.sweeps.l2_variants \
        --out build/analyzer/l2-variants
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from analyzer import mother as M
from analyzer.types import Exposure

from analyzer.tests._synthetic import (
    R0700,
    R0850,
    build_frame,
    channel_llr,
    hard_error_of,
)

N_BITS = 4096  # both rates' mother code length; the bits-wrong denominator

# The waterfall brackets measured with production's minsum-then-sp@150 on this
# builder: r0850 certifies 8/8 at 2.5% and 1/8 at 3.5%; r0700 certifies 8/8 at
# 7% and 4/8 at 8%.
LEVELS: tuple[tuple[str, str, tuple[float, ...]], ...] = (
    ("r0850", R0850, (0.030, 0.035, 0.040, 0.045, 0.050)),
    ("r0700", R0700, (0.06, 0.07, 0.08, 0.09, 0.10)),
)

LAMS = (0.3, 0.5, 0.7, 0.9)
BETAS = (0.0, 0.1, 0.15, 0.25)
ITERS = (100, 300)

# The production reference: `tile_codec.decode_frame`'s schedule at its own
# iteration count.
BASELINE = ("minsum-then-sp", 1.0, 0.0, 150)

def variants() -> list[tuple[str, float, float, int]]:
    """(mode, lam, beta, iters), de-duplicated by what the code actually reads.

    `mother.bp` ignores lam and beta in modes "sp" and "minsum-then-sp" (they
    call `ldpc._bp_loop` directly), and "damped" is "damped-offset" at
    beta = 0 — the same `_flooding_loop` call.  Sweeping the full 5x4x4x2 cross
    would therefore run 160 configurations of which 68 are distinct; only the
    distinct ones are run, and the knob columns of a mode that ignores a knob
    are reported at their effective value (lam = 1, beta = 0).
    """
    out: list[tuple[str, float, float, int]] = []
    for iters in ITERS:
        for mode in ("minsum-then-sp", "sp"):
            out.append((mode, 1.0, 0.0, iters))
        for lam in LAMS:
            out.append(("damped", lam, 0.0, iters))
            for beta in BETAS:
                if beta:
                    out.append(("damped-offset", lam, beta, iters))
            for beta in BETAS:
                out.append(("layered", lam, beta, iters))
    return out


def _realizations(ref: str, p: float, n_seeds: int):
    """One frame per rate, `n_seeds` channel draws; shared by every variant."""
    frame = build_frame(ref)
    made = []
    for s in range(n_seeds):
        llr = channel_llr(frame.printed, p, seed=3000 + s)
        made.append((M.to_mother(llr, frame.row, frame.key, metadata_bit=None),
                     hard_error_of(llr, frame.printed)))
    return frame, made


def _run_cell(frame, made, variant) -> dict:
    mode, lam, beta, iters = variant
    certified = 0
    mask: list[int] = []
    unsat: list[int] = []
    wrong: list[int] = []
    seconds: list[float] = []
    for mother, _measured in made:
        t0 = time.perf_counter()
        out = M.bp(mother, None, iters, mode=mode, lam=lam, beta=beta)
        seconds.append(time.perf_counter() - t0)
        ok, _user = M.gate(out.hard, mother, frame.bank, Exposure())
        certified += int(ok)
        mask.append(int(ok))
        unsat.append(out.unsat)
        wrong.append(int(np.count_nonzero(out.hard != frame.codeword)))
    return {
        "mode": mode, "lam": lam, "beta": beta, "iters": iters,
        "certified": certified, "n_seeds": len(made),
        # Per-seed, so a cascade's union coverage can be computed exactly
        # (every variant saw the identical realizations).
        "certified_mask": mask,
        "mean_unsat": float(np.mean(unsat)),
        "mean_bits_wrong": float(np.mean(wrong)),
        "bits_wrong_denominator": N_BITS,
        "mean_seconds": float(np.mean(seconds)),
    }


def sweep(n_seeds: int, workers: int) -> dict:
    plan = variants() + [BASELINE]
    rows: list[dict] = []
    started = time.time()
    for rate_id, ref, ps in LEVELS:
        for p in ps:
            frame, made = _realizations(ref, p, n_seeds)
            measured = float(np.mean([m for _mo, m in made]))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                cells = list(pool.map(
                    lambda v: _run_cell(frame, made, v), plan))
            for cell in cells:
                cell.update(rate_id=rate_id, ref=ref, p=p,
                            measured_hard_error=measured,
                            baseline=(cell["mode"], cell["lam"], cell["beta"],
                                      cell["iters"]) == BASELINE)
                rows.append(cell)
            print(f"{rate_id} p={p:.3f} measured={measured:.4f} "
                  f"({len(cells)} variants, {time.time() - started:.0f}s)",
                  flush=True)
    return {
        "n_seeds": n_seeds, "workers": workers,
        "n_variants": len(plan),
        "baseline": {"mode": BASELINE[0], "lam": BASELINE[1],
                     "beta": BASELINE[2], "iters": BASELINE[3]},
        "wall_seconds": time.time() - started,
        "rows": rows,
    }


def _key(row) -> tuple:
    return (row["mode"], row["lam"], row["beta"], row["iters"])


def _label(key) -> str:
    mode, lam, beta, iters = key
    if mode in ("sp", "minsum-then-sp"):
        return f"{mode}@{iters}"
    if mode == "damped":
        return f"{mode}@{iters} lam={lam}"
    return f"{mode}@{iters} lam={lam} beta={beta}"


def markdown(result: dict) -> str:
    rows = result["rows"]
    out = ["# L2 decoder-variant sweep (synthetic, `analyzer.mother.bp`)",
           "",
           f"{result['n_seeds']} seeds per cell, {result['n_variants']} "
           f"distinct variants, {result['workers']} threads, "
           f"{result['wall_seconds']:.0f} s wall.",
           "Bits wrong are counted against the ground-truth mother codeword "
           f"out of {N_BITS}.  Seconds are per decode under "
           f"{result['workers']}-way thread contention (relative, not "
           "single-thread cost).",
           ""]
    groups: dict[tuple[str, float], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["rate_id"], row["p"]), []).append(row)

    out += ["## Best variant per (rate, p) vs production minsum-then-sp@150",
            "",
            "| rate | p | best variant | cert/N | baseline cert/N | "
            "best bits wrong | baseline bits wrong | best s | baseline s |",
            "|---|---|---|---|---|---|---|---|---|"]
    for (rate_id, p), cells in groups.items():
        base = next(c for c in cells if c["baseline"])
        # Ties go to the baseline: in a cell where nothing certifies, the
        # "winner" would otherwise be whichever variant happened to be
        # fastest, which says nothing about decoding.
        best = max(cells, key=lambda c: (c["certified"], c["baseline"],
                                         -c["mean_bits_wrong"],
                                         -c["mean_seconds"]))
        out.append(
            f"| {rate_id} | {p:.3f} | {_label(_key(best))} | "
            f"{best['certified']}/{best['n_seeds']} | "
            f"{base['certified']}/{base['n_seeds']} | "
            f"{best['mean_bits_wrong']:.1f} | {base['mean_bits_wrong']:.1f} | "
            f"{best['mean_seconds']:.3f} | {base['mean_seconds']:.3f} |")

    out += ["", "## Greedy cascade (cumulative union coverage over all cells)",
            "",
            "The gate makes a union safe, so the ladder's L2 tier should run "
            "an ordered SET, not one variant.",
            "",
            "| # | variant | cumulative certified | mean s |",
            "|---|---|---|---|"]
    n_total = len(groups) * result["n_seeds"]
    for i, (key, cum, sec) in enumerate(cascade(result), 1):
        out.append(f"| {i} | {_label(key)} | {cum}/{n_total} | {sec:.3f} |")

    out += ["", "## Every cell", "",
            "| rate | p | mode | lam | beta | iters | cert/N | mean unsat | "
            "mean bits wrong | mean s |", "|---|---|---|---|---|---|---|---|"
            "---|---|"]
    for row in rows:
        out.append(
            f"| {row['rate_id']} | {row['p']:.3f} | {row['mode']} | "
            f"{row['lam']} | {row['beta']} | {row['iters']} | "
            f"{row['certified']}/{row['n_seeds']} | {row['mean_unsat']:.1f} | "
            f"{row['mean_bits_wrong']:.1f} | {row['mean_seconds']:.3f} |")
    return "\n".join(out) + "\n"


def totals(result: dict) -> list[tuple[tuple, int, float]]:
    """Certify total over all (rate, p) cells, per variant — the ranking."""
    agg: dict[tuple, list[int]] = {}
    secs: dict[tuple, list[float]] = {}
    for row in result["rows"]:
        agg.setdefault(_key(row), []).append(row["certified"])
        secs.setdefault(_key(row), []).append(row["mean_seconds"])
    return sorted(((k, int(sum(v)), float(np.mean(secs[k])))
                   for k, v in agg.items()),
                  key=lambda t: (-t[1], t[2]))


def cascade(result: dict, depth: int = 5) -> list[tuple[tuple, int, float]]:
    """Greedy union coverage: the ladder's L2 tier is a CASCADE, not a pick.

    DESIGN §6 runs several BP variants on the same residue and keeps whichever
    certifies; the certificate gate makes a union safe (a wrong hard vector
    cannot pass the syndrome + CRC).  So the figure of merit is not "which
    single variant certifies most" but "which small ORDERED set covers most
    realizations", and the answer is driven by complementarity.  Greedy is
    exact for the first pick and near-optimal after.
    """
    masks: dict[tuple, list[int]] = {}
    for row in result["rows"]:
        masks.setdefault(_key(row), []).extend(row["certified_mask"])
    secs: dict[tuple, list[float]] = {}
    for row in result["rows"]:
        secs.setdefault(_key(row), []).append(row["mean_seconds"])
    covered = np.zeros(len(next(iter(masks.values()))), bool)
    chosen: list[tuple[tuple, int, float]] = []
    for _ in range(depth):
        best_key, best_gain = None, 0
        for key, mask in masks.items():
            gain = int(np.count_nonzero(np.asarray(mask, bool) & ~covered))
            if gain > best_gain or (
                    gain == best_gain and best_key is not None
                    and np.mean(secs[key]) < np.mean(secs[best_key])
                    and gain > 0):
                best_key, best_gain = key, gain
        if best_key is None:
            break
        covered |= np.asarray(masks[best_key], bool)
        chosen.append((best_key, int(covered.sum()), float(
            np.mean(secs[best_key]))))
        del masks[best_key]
    return chosen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=pathlib.Path, required=True)
    args = ap.parse_args()
    result = sweep(args.seeds, args.workers)
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "l2_variants.json").write_text(json.dumps(result, indent=1))
    (out_dir / "l2_variants.md").write_text(markdown(result))
    print(f"\nwrote {out_dir / 'l2_variants.json'} and "
          f"{out_dir / 'l2_variants.md'}")
    print("\ntop variants by total certified (of "
          f"{10 * args.seeds} decodes over all cells):")
    for key, total, sec in totals(result)[:12]:
        print(f"  {total:4d}  {sec:.3f}s  {_label(key)}")
    base_total = next(t for k, t, _s in totals(result) if k == BASELINE)
    print(f"\n  baseline minsum-then-sp@150: {base_total}")
    print("\ngreedy cascade (cumulative union coverage):")
    for key, cum, sec in cascade(result):
        print(f"  {cum:4d}  {sec:.3f}s  {_label(key)}")


if __name__ == "__main__":
    main()
