# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/fast/verify/verify_volume.py
"""Volume check at the search's operating regime (near-threshold BIAWGN/BSC/erasure,
seeds disjoint from the builder's) + run_chan_fast == common.run_chan on new t0s."""
from __future__ import annotations
import sys, json
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent; FAST = HERE.parent
sys.path.insert(0, str(FAST)); sys.path.insert(0, str(FAST.parents[1] / "harness")); sys.path.insert(0, str(FAST.parent))
import codes as hcodes  # noqa
import channels as hch
from holo.core.ldpc import construct
from holo.core.ldpc.decode import decode_soft, encode
from fastdecode import decode_batch
N = construct.N_BITS


def vol(rid, seed=31_337_000, n=240):
    code = construct.load_code(rid); k = code.spec.k_bits; R = k / N
    pc = hch.bsc_capacity_p(R); es = hch.biawgn_shannon_esn0_db(R)
    X = np.empty((n, N))
    for t in range(n):
        g = np.random.default_rng(seed + t); c = encode(g.integers(0, 2, k).astype(np.uint8), rid)
        m = t % 3
        if m == 0:
            s = np.sqrt(1 / (2 * 10 ** ((es + g.uniform(0.3, 1.2)) / 10)))
            X[t] = -2.0 * ((1.0 - 2.0 * c) + s * g.standard_normal(N)) / (s * s)
        elif m == 1:
            p = pc * g.uniform(0.55, 0.85); X[t] = hch.hard_llr(c ^ (g.random(N) < p), p)
        else:
            p = pc * 0.4; X[t] = hch.hard_llr(c ^ (g.random(N) < p), p); X[t][g.random(N) < 0.5 * (1 - R)] = 0.0
    ref = [decode_soft(x, rid) for x in X]
    bad = 0
    for B in (64, 240):
        for s in range(0, n, B):
            o = decode_batch(X[s:s + B], code, return_extrinsic=True)
            for j in range(o[0].size):
                r = ref[s + j]
                if (bool(o[0][j]) != r[0] or int(o[2][j]) != r[2] or not np.array_equal(o[1][j], r[1])
                        or o[3][j].tobytes() != r[3].tobytes()):
                    bad += 1
    it = np.array([r[2] for r in ref])
    return {"rid": rid, "n": n, "ok": int(sum(r[0] for r in ref)), "zero": int((it == 0).sum()),
            "sp": int((it > 60).sum()), "mean_it": float(it.mean()), "mismatch": bad}


def chan():
    import common
    from tasks_fast import run_chan_fast
    out = []
    for rid in ("r0547", "r0700"):
        R = construct.LADDER[rid].k_bits / N
        pc = hch.bsc_capacity_p(R); es = hch.biawgn_shannon_esn0_db(R)
        for chn, prm in (("bsc", {"p": 0.8 * pc}), ("awgn", {"sigma": common.sigma_of(es + 0.6)}),
                         ("eras", {"p": 0.4 * pc, "eps": 0.45 * (1 - R)}),
                         ("robust", {"sigma": common.sigma_of(es + 1.0), "f": 0.02})):
            a = common.run_chan(rid, chn, prm, 12_345, 45)
            b = run_chan_fast(rid, chn, prm, 12_345, 45, batch=16)
            out.append({"rid": rid, "ch": chn, "equal": a == b, "fails": a["fails"], "und": a["undetected"]})
    return out


if __name__ == "__main__":
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(4) as ex:
        f = [ex.submit(vol, r) for r in ("r0406", "r0550", "r0775")] + [ex.submit(chan)]
        res = [x.result() for x in f]
    for r in res: print(r)
    (HERE / "verify_volume.json").write_text(json.dumps(res, indent=1))
