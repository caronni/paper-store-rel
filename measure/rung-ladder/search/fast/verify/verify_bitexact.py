# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/fast/verify/verify_bitexact.py
"""Independent bit-exactness check of fastdecode.decode_batch vs production
decode_soft (reviewer's script; seeds/channels disjoint from test_fastdecode.py).

Per code: a pool of adversarial + channel LLR vectors, production reference one
call per vector, then decode_batch at B=1, B=200 (shuffled order, mixed rows),
B=37, plus decode_batch_simple, plus max_iters in {0,1,2,7} and alpha 0.75/1.0.
Compares ok, n_iters, hard, extrinsic BYTES.  Exit 0 iff zero mismatches.
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
FAST = HERE.parent
sys.path.insert(0, str(FAST)); sys.path.insert(0, str(FAST.parents[1] / "harness"))
import codes as hcodes  # noqa  (registers r0406 etc.)
from holo.core.ldpc import construct
from holo.core.ldpc.decode import decode, decode_soft, encode
from fastdecode import decode_batch, decode_batch_simple

N = construct.N_BITS


def pool(rid: str, seed: int):
    sp = construct.LADDER[rid]; k = sp.k_bits; R = k / N
    g = np.random.default_rng(seed)
    X, lab = [], []
    def add(x, l): X.append(np.asarray(x, np.float64)); lab.append(l)
    cw = lambda: encode(g.integers(0, 2, k).astype(np.uint8), rid)
    # --- adversarial
    add(np.zeros(N), "all-zero")
    add(np.full(N, -0.0), "all-negzero")
    add(np.full(N, np.inf), "all+inf")
    add(np.full(N, -np.inf), "all-inf")
    add(np.where(g.random(N) < .5, np.inf, -np.inf), "rand+-inf")
    for _ in range(3):
        c = cw(); x = np.where(c == 1, np.inf, -np.inf); x[g.integers(N)] = 0.0
        add(x, "cw-inf-1erased")
        c = cw(); x = 3.0 * (2.0 * c - 1); x[g.integers(N)] = 0.0
        add(x, "cw-3-1erased")
        c = cw(); x = 3.0 * (2.0 * c - 1); j = g.integers(N); x[j] = -x[j] * 0.5
        add(x, "cw-3-1flipped")
    c = cw(); add(1e300 * (2.0 * c - 1), "huge-finite")
    c = cw(); add(5e-320 * (2.0 * c - 1), "denormal")
    c = cw(); x = 2.0 * c - 1; x[g.random(N) < 0.5] = 0.0; add(x, "half-erased")
    # --- channels (distinct from builder's: Laplace noise, quantized LLRs with ties,
    #     Rayleigh-faded AWGN, burst erasures, sign-flip at +-20 exactly)
    for t in range(40):
        c = cw(); b = 1.0 - 2.0 * c
        kind = t % 5
        if kind == 0:   # Laplace noise
            y = b + g.laplace(0, 0.55 + 0.1 * (R > .6), N); x = -2.0 * y / 0.5
            add(x, "laplace")
        elif kind == 1:  # quantized 3-bit LLRs (massive ties -> first-argmin rule)
            y = b + (0.75 + 0.2 * (R > .6)) * g.standard_normal(N)
            x = -np.clip(np.round(2 * y), -3, 3)
            add(x + 0.0, "quant3")
        elif kind == 2:  # Rayleigh fading
            a = g.rayleigh(0.8, N); s = 0.6 + 0.15 * (R > .6)
            y = a * b + s * g.standard_normal(N); x = -2.0 * a * y / (s * s)
            add(x, "rayleigh")
        elif kind == 3:  # burst erasures + BSC
            p = 0.03 + 0.03 * (R < .6); x = 2.2 * (2.0 * (c ^ (g.random(N) < p)) - 1)
            st = g.integers(0, N - 300); x[st:st + int(g.integers(50, 300))] = 0.0
            add(x, "burst")
        else:  # confidently wrong at exactly +-20 and beyond (clip boundary)
            s = 0.7; y = b + s * g.standard_normal(N); x = -2.0 * y / (s * s)
            bad = g.random(N) < 0.01; x[bad] = np.where(c[bad] == 1, -20.0, 25.0)
            add(x, "clip20")
    return np.stack(X), lab


def cmp(a, b):
    r_ok, r_h, r_n, r_e = a; ok, h, n, e = b
    if bool(ok) != bool(r_ok): return f"ok {ok} vs {r_ok}"
    if int(n) != int(r_n): return f"n_iters {n} vs {r_n}"
    if not np.array_equal(h, r_h): return "hard"
    if np.asarray(e, np.float64).tobytes() != np.asarray(r_e, np.float64).tobytes(): return "extrinsic bytes"
    return None


def check(rid: str, seed: int) -> dict:
    code = construct.load_code(rid)
    X, lab = pool(rid, seed)
    P = len(X)
    t0 = time.perf_counter()
    ref = [decode_soft(x, rid) for x in X]
    t_ref = time.perf_counter() - t0
    for i in range(0, P, 7):  # decode() == decode_soft()[:3]
        a = decode(X[i], rid)
        assert a[0] == ref[i][0] and a[2] == ref[i][2] and np.array_equal(a[1], ref[i][1])
    mism = []
    g = np.random.default_rng(seed + 1)
    # B=1
    for i in range(P):
        o = decode_batch(X[i], code, return_extrinsic=True)
        w = cmp(ref[i], [v[0] for v in o])
        if w: mism.append(("B1", i, lab[i], w))
    # B=200: shuffle and pad the pool to 200 rows (duplicates allowed) so fast
    # 0-iteration rows sit beside never-converging rows in one batch
    idx = g.permutation(np.r_[np.arange(P), g.integers(0, P, max(0, 200 - P))])[:200]
    o = decode_batch(X[idx], code, return_extrinsic=True)
    for j, i in enumerate(idx):
        w = cmp(ref[i], [v[j] for v in o])
        if w: mism.append(("B200", int(i), lab[i], w))
    for s in range(0, P, 37):
        o = decode_batch(X[s:s + 37], code, return_extrinsic=True)
        for j in range(o[0].size):
            w = cmp(ref[s + j], [v[j] for v in o])
            if w: mism.append(("B37", s + j, lab[s + j], w))
    o = decode_batch_simple(X, code, return_extrinsic=True)
    for i in range(P):
        w = cmp(ref[i], [v[i] for v in o])
        if w: mism.append(("simple", i, lab[i], w))
    extra = 0
    sub = np.r_[0:17, 17:P:4]
    for mi, al in ((0, .8), (1, .8), (2, .8), (7, .8), (60, .75), (60, 1.0)):
        o = decode_batch(X[sub], code, max_iters=mi, alpha=al, return_extrinsic=True)
        for j, i in enumerate(sub):
            r = decode_soft(X[i], rid, max_iters=mi, alpha=al); extra += 1
            w = cmp(r, [v[j] for v in o])
            if w: mism.append((f"mi{mi}a{al}", int(i), lab[i], w))
    it = np.array([r[2] for r in ref]); oks = np.array([r[0] for r in ref])
    by = {}
    for l, r in zip(lab, ref): by.setdefault(l, []).append((bool(r[0]), int(r[2])))
    return {"rid": rid, "k": code.spec.k_bits, "E": int(code.edge_chk.size), "pool": P,
            "ref_ok": int(oks.sum()), "zero_iter": int((it == 0).sum()), "sp_ran": int((it > 60).sum()),
            "full_budget_fail": int((it == 120).sum()),
            "comparisons": 3 * P + 200 + extra, "mismatches": mism, "ref_s": round(t_ref, 1),
            "by_label": {l: v for l, v in by.items() if not l.startswith(("laplace","quant","rayl","burst","clip"))}}


if __name__ == "__main__":
    codes = sys.argv[1:] or ["r0406", "r0547", "r0700", "r0850"]
    from concurrent.futures import ProcessPoolExecutor
    with ProcessPoolExecutor(len(codes)) as ex:
        res = list(ex.map(check, codes, [424242 + 17 * i for i in range(len(codes))]))
    bad = 0
    for r in res:
        bad += len(r["mismatches"])
        print({k: v for k, v in r.items() if k not in ("mismatches", "by_label")}, "mismatches", len(r["mismatches"]))
        print("   adversarial (ok, n_iters):", r["by_label"])
        for m in r["mismatches"][:10]: print("   MISMATCH", m)
    (HERE / "verify_bitexact.json").write_text(json.dumps(res, indent=1, default=str))
    print("PASS" if bad == 0 else f"FAIL {bad}")
    sys.exit(0 if bad == 0 else 1)
