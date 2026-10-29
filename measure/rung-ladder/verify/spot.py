# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/verify/spot.py
"""Independent spot re-measurement with the OTHER decoder port (paperholo.ldpc),
own seeds (base 900_000 + t), 200 trials, hard LLR = +-log((1-p)/p) (the
harness's convention) — read-only, nothing from the harness imported."""
from __future__ import annotations
import json, math, sys, time
from pathlib import Path
import numpy as np
from scipy.stats import beta
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from paperholo import ldpc

OUT = Path(__file__).resolve().parent / "spot_results.json"
N = 4096


def cp95(f: int, n: int) -> tuple[float, float]:
    lo = 0.0 if f == 0 else float(beta.ppf(0.025, f, n - f + 1))
    hi = 1.0 if f == n else float(beta.ppf(0.975, f + 1, n - f))
    return lo, hi


def hard_llr(rx, p):
    return math.log((1 - p) / p) * (2.0 * rx.astype(np.float64) - 1.0)


def run(spec, p, eps, n=200, base=900_000):
    fails = und = 0; it_sum = 0
    for t in range(n):
        g = np.random.default_rng(base + t)
        info = g.integers(0, 2, spec.k_bits).astype(np.uint8)
        cw = ldpc.encode(info, spec)
        rx = cw ^ (g.random(N) < p)
        llr = hard_llr(rx, p)
        if eps:
            llr[g.random(N) < eps] = 0.0
        hard, ok, n_it = ldpc.decode(llr, spec)
        good = ok and np.array_equal(hard, cw)
        fails += int(not good); und += int(ok and not good); it_sum += n_it
    return fails, und, it_sum / n


if __name__ == "__main__":
    pts = [("r0547", ldpc.LDPC_LADDER["r0547"], 0.055, 0.0, "record: clean; harness log-LLR grid 0/200"),
           ("r0700", ldpc.LDPC_LADDER["r0700"], 0.035, 0.0, "record 1.5-1.8%; harness 1/200 (log-LLR), 2/200 (mag 4)"),
           ("r0313", ldpc.LdpcSpec("r0313", 1280), 0.120, 0.0, "harness p@1% grid point: 2/200 (1 undetected)"),
           ("r0313", ldpc.LdpcSpec("r0313", 1280), 0.020, 0.5, "harness eps=0.5 p=0.02: 0/200")]
    out = []
    for rid, spec, p, eps, note in pts:
        t0 = time.perf_counter()
        code = ldpc.build_code(spec)
        f, u, it = run(spec, p, eps)
        lo, hi = cp95(f, 200)
        rec = {"rid": rid, "k": spec.k_bits, "seed_label": spec.seed_label.decode(), "restart": int(code.restart),
               "p": p, "eps": eps, "fails": f, "n": 200, "undetected": u, "mean_iters": round(it, 1),
               "cp95": [round(lo, 4), round(hi, 4)], "harness": note, "seconds": round(time.perf_counter() - t0, 1)}
        print(rec, flush=True); out.append(rec)
    OUT.write_text(json.dumps(out, indent=1) + "\n")
