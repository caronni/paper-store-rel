#!/usr/bin/env python3
"""Conditional-on-correct-acquisition FEC study; not photo qualification."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import platform
import time
from typing import NamedTuple

from common import ROOT
import numpy as np
import scipy
from scipy.special import logsumexp, ndtri
from holo.receiver.format import tile_codec
from holo.receiver.lib import ldpc

RATE = "r0775"
SEED = 20260909
N_SITES = 100
MAX_ITERS = 60
ALPHA = 0.8
# For IID channels, the locations and the permutation are immaterial.
SITES = np.arange(N_SITES)
ACTIVE = np.arange(N_SITES, tile_codec.N_CELLS)
CHANNELS = {
    "bit_flips": [0.005, 0.01, 0.015, 0.02, 0.025, 0.03],
    "gaussian_soft": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
    "known_cell_erasures": [0.01, 0.02, 0.05, 0.10, 0.15, 0.18, 0.20],
}


class TrialResult(NamedTuple):
    success: bool
    wrong_certificate: bool
    iterations: int
    hard_errors: int


def rs_log_success(p: float, erasures: bool = False) -> float:
    """Log probability that every v40-L RS block is within its radius.

    Keeping a log probability distinguishes tiny probabilities from impossible
    events, even when the ordinary probability underflows to zero.
    """
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("bit error/erasure probability must be in [0, 1]")
    if p == 0:
        return 0.0
    if p == 1:
        return -math.inf
    # v40-L: 19 RS(148,118), 6 RS(149,119), 30 parity bytes each.
    # A byte is bad/erased when any one of its eight bits is bad/erased.
    log_good_byte = 8 * math.log1p(-p)
    log_bad_byte = math.log(-math.expm1(log_good_byte))
    limit = 30 if erasures else 15

    def block_log_cdf(length: int) -> float:
        return float(logsumexp([
            math.log(math.comb(length, errors)) + errors * log_bad_byte
            + (length - errors) * log_good_byte
            for errors in range(limit + 1)
        ]))

    # Roundoff at extremely small p can put log(CDF) just above zero.
    return min(0.0, 19 * block_log_cdf(148) + 6 * block_log_cdf(149))


def rs_success(p: float, erasures: bool = False) -> float:
    """Ordinary RS probability; may underflow for very difficult channels."""
    return math.exp(rs_log_success(p, erasures))


def trial(args: tuple[str, float, np.random.SeedSequence]) -> TrialResult:
    channel, p, seed = args
    if channel not in CHANNELS:
        raise ValueError(f"unknown channel: {channel}")
    if not math.isfinite(p) or not 0 <= p <= 1:
        raise ValueError("channel probability must be in [0, 1]")
    if channel != "known_cell_erasures" and not 0 < p < 0.5:
        raise ValueError("bit-flip and Gaussian channels require 0 < p < 0.5")
    rng = np.random.default_rng(seed)
    user = rng.integers(0, 2, tile_codec.tile_capacity(RATE, N_SITES),
                        dtype=np.uint8)
    bits = tile_codec.encode_tile(user, RATE, SITES, 1, 0)
    signs = 2.0 * bits - 1.0
    if channel == "gaussian_soft":
        sigma = 1 / ndtri(1 - p)
        observations = signs + rng.normal(0, sigma, len(bits))
        llr = 2 * observations / (sigma * sigma)
        hard_errors = np.count_nonzero((llr[ACTIVE] > 0) != bits[ACTIVE])
    elif channel == "bit_flips":
        flips = rng.random(len(bits)) < p
        llr = signs * math.log((1 - p) / p) * np.where(flips, -1, 1)
        hard_errors = np.count_nonzero(flips[ACTIVE])
    else:
        erased = rng.random(len(bits)) < p
        llr = signs * ldpc.LLR_CLIP
        llr[erased] = 0.0
        hard_errors = np.count_nonzero(erased[ACTIVE])
    ok, recovered, iterations, _, _ = tile_codec.decode_tile(
        llr, RATE, SITES, 1, 0, MAX_ITERS, ALPHA)
    wrong = bool(ok and not np.array_equal(recovered, user))
    return TrialResult(bool(ok and not wrong), wrong, iterations,
                       int(hard_errors))


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """Pointwise 95% interval for a binomial success probability."""
    if trials < 1 or not 0 <= successes <= trials:
        raise ValueError("require 0 <= successes <= trials and trials >= 1")
    proportion = successes / trials
    z = 1.959963984540054
    centre = (proportion + z * z / (2 * trials)) / (1 + z * z / trials)
    margin = (z * math.sqrt(proportion * (1 - proportion) / trials
                           + z * z / (4 * trials * trials))
              / (1 + z * z / trials))
    low = 0.0 if successes == 0 else max(0.0, centre - margin)
    high = 1.0 if successes == trials else min(1.0, centre + margin)
    return low, high


def provenance() -> dict[str, object]:
    files = [Path(__file__).resolve(), Path(tile_codec.__file__),
             Path(ldpc.__file__),
             Path(ldpc.__file__).parent / "ldpc_data" / f"{RATE}.json"]
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files
        },
    }


def run(out: Path, trials: int, workers: int) -> dict[str, object]:
    if any(isinstance(n, bool) or not isinstance(n, int) or n < 1
           for n in (trials, workers)):
        raise ValueError("positive integer trials and workers required")
    out.mkdir(parents=True, exist_ok=False)
    rows: list[dict[str, object]] = []
    report: dict[str, object] = {
        "rate": RATE, "sites": N_SITES, "seed": SEED,
        "trials_per_point": trials, "workers": workers,
        "bp_max_iters_per_algorithm": MAX_ITERS, "alpha": ALPHA,
        "finite_llr_clip": ldpc.LLR_CLIP,
        "scope": ("Correct acquisition; IID data-cell channel; no pilot/acquisition "
                  "failures. Actual receiver LDPC+CRC. QR is bounded-distance RS "
                  "calculation, not a QR decoder run."),
        "full_object_model": (
            "Ten independent LDPC tiles all succeed; conservative sufficient "
            "condition for K=8 systematic source symbols plus two repair symbols. "
            "Format, version, addresses and K=8 are supplied out of band; this "
            "does not meet production metadata recovery requirements. Fountain "
            "itself not simulated."),
        "repository": str(ROOT), "provenance": provenance(), "rows": rows,
    }
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for ci, (channel, probabilities) in enumerate(CHANNELS.items()):
            for pi, p in enumerate(probabilities):
                jobs = [(channel, p, np.random.SeedSequence([SEED, ci, pi, t]))
                        for t in range(trials)]
                results = list(pool.map(trial, jobs))
                successes = sum(result.success for result in results)
                proportion = successes / trials
                low, high = wilson_interval(successes, trials)
                qr_log = rs_log_success(p, channel == "known_cell_erasures")
                row = {
                    "channel": channel, "p": p, "successes": successes,
                    "trials": trials,
                    "wrong_certificates": sum(r.wrong_certificate for r in results),
                    "mean_iterations": float(np.mean([r.iterations for r in results])),
                    "mean_observed_error_or_erasure_fraction": (
                        sum(r.hard_errors for r in results) / (trials * len(ACTIVE))),
                    "tile_success": proportion, "tile_wilson95": [low, high],
                    "ten_tile_all_success_estimate": proportion ** 10,
                    "ten_tile_all_success_interval": [low ** 10, high ** 10],
                    "qr_whole_rs_success": math.exp(qr_log),
                    "qr_whole_rs_log10_success": qr_log / math.log(10),
                }
                rows.append(row)
                report["elapsed_seconds"] = time.monotonic() - started
                (out / "results.json").write_text(
                    json.dumps(report, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")
                print(f"{channel:20s} p={p:.3f}: LDPC {successes}/{trials}, "
                      f"ten-tile all-success estimate={proportion ** 10:.5g}, "
                      f"QR log10(P)={row['qr_whole_rs_log10_success']:.5g}; "
                      f"elapsed={report['elapsed_seconds']:.1f}s", flush=True)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    try:
        run(args.out, args.trials, args.workers)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"resilience: {exc}\n")


if __name__ == "__main__":
    main()
