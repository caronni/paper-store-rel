# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/verify/punct.py
"""Is 'punct_last kills every code (200/200)' a code property or the decoder's
iteration budget?  The accumulator is a BIT-SERIAL chain (parity bit j in
checks j, j+1; construct._expand_edges), so a run of 120 punctured tail
parity bits is a 120-long serial erasure: flooding BP peels ONE bit per
iteration, i.e. >= 120 iterations AFTER the info bits have converged; the
production decoder gives 60 min-sum + 60 sum-product FROM SCRATCH.  Test:
noiseless and at the harness's own p with the harness's own seeds, count
(a) syndrome ok, (b) INFO bits correct, at max_iters 60 / 200 / 400."""
from __future__ import annotations
import json, math, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[3]; WORK = ROOT / "measure" / "rung-ladder"
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(WORK / "harness"))
import codes  # noqa: E402
from holo.core.ldpc.decode import decode, encode  # noqa: E402
N = 4096


def hard_llr(rx, p):
    return math.log((1 - p) / p) * (2.0 * rx.astype(np.float64) - 1.0)


def trial(rid, t, p, variant, max_iters):
    k = codes.spec(rid).k_bits; m = codes.spec(rid).m_bits
    g = np.random.default_rng(400_000 + t)          # the harness's accom seeds
    info = g.integers(0, 2, k).astype(np.uint8)
    cw = encode(info, rid)
    rx = cw ^ (g.random(N) < p) if p > 0 else cw.copy()
    llr = hard_llr(rx, max(p, 0.01))
    if variant == "punct_last":
        llr[N - 120:] = 0.0
    elif variant == "punct_even":
        llr[k + ((np.arange(120) + 0.5) * m / 120).astype(np.int64)] = 0.0
    ok, hard, n_it = decode(llr, rid, max_iters=max_iters)
    return ok, bool(np.array_equal(hard[:k], cw[:k])), bool(np.array_equal(hard, cw)), n_it


out = {}
for rid in ["r0547", "r0313"]:
    for variant in ["punct_last", "punct_even"]:
        for p in [0.0, 0.060 if rid == "r0547" else 0.120]:
            for mi in [60, 200, 400]:
                n = 20 if mi >= 200 else 50
                oks = infos = alls = 0; its = 0
                for t in range(n):
                    ok, info_ok, all_ok, n_it = trial(rid, t, p, variant, mi)
                    oks += ok; infos += info_ok; alls += all_ok; its += n_it
                key = f"{rid} {variant} p={p} max_iters={mi}"
                out[key] = {"n": n, "syndrome_ok": oks, "info_bits_correct": infos, "whole_cw_correct": alls, "mean_iters": its / n}
                print(key, out[key], flush=True)
(Path(__file__).resolve().parent / "punct_results.json").write_text(json.dumps(out, indent=1) + "\n")
