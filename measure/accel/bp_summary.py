"""Merge the CPU and GPU throughput runs and find the break-even batch.

The two runs live in different interpreters — the CPU engines belong in
the working free-threaded venv, mlx in the scratch venv — so the join
happens here, on the JSON they each wrote, rather than inside one
process that would have to host both.

Break-even is reported as the smallest batch size whose GPU tiles/s
reaches the CPU engine's, per rate and per cohort, against ``cpu1`` and
against ``cpu8`` separately.  "Never" is a legitimate answer and is
printed as such.

    PYTHONPATH=<worktree> <python> measure/accel/bp_summary.py \\
        --cpu OUT/throughput-cpu.json --gpu OUT/throughput-gpu.json \\
        --out OUT
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def break_even(gpu_rows: dict, target: float) -> str:
    for size in sorted((int(key) for key in gpu_rows), key=int):
        if gpu_rows[str(size)]["tiles_per_s"] >= target:
            return str(size)
    return "never in the swept range"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=Path, required=True)
    parser.add_argument("--gpu", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    cpu = json.loads(args.cpu.read_text())
    gpu = json.loads(args.gpu.read_text())
    merged: dict = {
        "cpu_run": {"interpreter": cpu["interpreter"],
                    "free_threaded": cpu["free_threaded"],
                    "loadavg_before": cpu["loadavg_before"],
                    "loadavg_after": cpu["loadavg_after"]},
        "gpu_run": {"interpreter": gpu["interpreter"],
                    "loadavg_before": gpu["loadavg_before"],
                    "loadavg_after": gpu["loadavg_after"]},
        "max_iters": cpu["max_iters"],
        "rates": {},
    }
    for rate_id, cpu_rate in cpu["rates"].items():
        gpu_rate = gpu["rates"][rate_id]
        rate_out: dict = {"cohort_sizes": cpu_rate["cohort_sizes"]}
        for cohort, cpu_entry in cpu_rate.items():
            if cohort == "cohort_sizes":
                continue
            gpu_rows = gpu_rate[cohort]["gpu"]
            cpu1 = cpu_entry["cpu1"]["tiles_per_s"]
            cpu8 = cpu_entry["cpu8"]["tiles_per_s"]
            best_size = max(gpu_rows, key=lambda key: gpu_rows[key][
                "tiles_per_s"])
            best = gpu_rows[best_size]["tiles_per_s"]
            rate_out[cohort] = {
                "cpu1_tiles_per_s": cpu1,
                "cpu8_tiles_per_s": cpu8,
                "cpu8_over_cpu1": cpu8 / cpu1,
                "gpu_best_tiles_per_s": best,
                "gpu_best_batch": best_size,
                "gpu_best_over_cpu1": best / cpu1,
                "gpu_best_over_cpu8": best / cpu8,
                "break_even_vs_cpu1": break_even(gpu_rows, cpu1),
                "break_even_vs_cpu8": break_even(gpu_rows, cpu8),
                "gpu_fixed_per_batch_ms":
                    gpu_rate[cohort]["gpu_fit"]["per_batch_fixed_s"] * 1e3,
                "gpu_marginal_per_tile_ms":
                    gpu_rate[cohort]["gpu_fit"]["per_tile_s"] * 1e3,
                "gpu_transfer_at_1024_ms":
                    gpu_rows["1024"]["transfer_best_s"] * 1e3,
                "gpu_batch_wall_at_1024_ms":
                    gpu_rows["1024"]["per_batch_best_ms"],
                "tiles_per_s_by_batch": {
                    size: row["tiles_per_s"]
                    for size, row in gpu_rows.items()},
            }
        merged["rates"][rate_id] = rate_out
    text = json.dumps(merged, indent=2, sort_keys=True)
    if args.out is not None:
        (args.out / "throughput-summary.json").write_text(text + "\n")
    for rate_id, rate in merged["rates"].items():
        print(f"== {rate_id} == {rate['cohort_sizes']}")
        for cohort, row in rate.items():
            if cohort == "cohort_sizes":
                continue
            print(f"  {cohort:>5}: cpu1 {row['cpu1_tiles_per_s']:8.2f}  "
                  f"cpu8 {row['cpu8_tiles_per_s']:8.2f} "
                  f"({row['cpu8_over_cpu1']:.2f}x)  "
                  f"gpu best {row['gpu_best_tiles_per_s']:8.2f} "
                  f"@B={row['gpu_best_batch']} "
                  f"({row['gpu_best_over_cpu1']:.2f}x cpu1, "
                  f"{row['gpu_best_over_cpu8']:.2f}x cpu8)")
            print(f"         break-even vs cpu1 at B="
                  f"{row['break_even_vs_cpu1']}, vs cpu8 at B="
                  f"{row['break_even_vs_cpu8']}; "
                  f"fixed {row['gpu_fixed_per_batch_ms']:.1f} ms/batch, "
                  f"marginal {row['gpu_marginal_per_tile_ms']:.3f} ms/tile, "
                  f"transfer at B=1024 "
                  f"{row['gpu_transfer_at_1024_ms']:.2f} ms of "
                  f"{row['gpu_batch_wall_at_1024_ms']:.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
