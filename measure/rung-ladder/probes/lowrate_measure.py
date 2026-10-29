"""Read-only: build a candidate rung with paperholo's LIVE frozen recipe (in memory,
nothing written under src/), report its structure, then measure BSC and
erasure+error BLER with the exact hybrid decoder. Usage:
  lowrate_measure.py <k> [heavy_deg] [heavy_frac] [trials]
"""
import sys, json, math, time
import numpy as np
from paperholo import ldpc

k = int(sys.argv[1]); hd = int(sys.argv[2]) if len(sys.argv) > 2 else 10
hf = float(sys.argv[3]) if len(sys.argv) > 3 else 0.30
trials = int(sys.argv[4]) if len(sys.argv) > 4 else 100
ldpc.HEAVY_FRAC = hf
spec = ldpc.LdpcSpec(f"x{k}h{hd}f{hf}", k, heavy_deg=hd)
t0 = time.time()
code = ldpc.build_code(spec)
tb = time.time() - t0
m = spec.m_bits; n = spec.n_bits
chk_counts = np.bincount(code.edge_chk, minlength=m)
var_counts = np.bincount(code.edge_var, minlength=n)
E = code.n_edges
# degree distributions (edge perspective)
lam = {int(d): float(c * d) / E for d, c in zip(*np.unique(var_counts, return_counts=True))}
rho = {int(d): float(c * d) / E for d, c in zip(*np.unique(chk_counts, return_counts=True))}
lam2 = lam.get(2, 0.0) + lam.get(1, 0.0)
rho_p1 = sum(f * (d - 1) for d, f in rho.items())
prod = lam2 * rho_p1
# BSC stability bound: 2 sqrt(p(1-p)) < 1/prod
b = 1.0 / prod
p_stab = 0.5 * (1 - math.sqrt(max(0.0, 1 - b * b))) if b < 1 else 0.5
# capacity p*: 1 - H2(p) = R
R = k / n
def H2(p): return -p*math.log2(p) - (1-p)*math.log2(1-p)
lo, hi = 1e-6, 0.5
for _ in range(60):
    mid = (lo+hi)/2
    if 1 - H2(mid) > R: lo = mid
    else: hi = mid
p_cap = lo
zero_info_rows = int((chk_counts == 2).sum())
hist = {int(d): int(c) for d, c in zip(*np.unique(chk_counts, return_counts=True))}
out = dict(k=k, rate=R, heavy_deg=hd, heavy_frac=hf, restart=code.restart, build_s=round(tb, 1),
           n_edges=E, nh=int(code.heavy_rows.shape[0]), chk_deg_hist=hist,
           deg2_checks=zero_info_rows, deg2_check_blocks=zero_info_rows / 64,
           lambda2=round(lam2, 4), rho_prime1=round(rho_p1, 3), stability_product=round(prod, 3),
           p_stability_bound=round(p_stab, 4), p_capacity=round(p_cap, 4))
def hard_llr(bits, mag=4.0): return mag * (2.0 * bits.astype(np.float64) - 1.0)
def bsc(p, seedbase):
    fails = und = iters = 0
    for t in range(trials):
        g = np.random.default_rng(seedbase + t)
        info = g.integers(0, 2, k).astype(np.uint8)
        cw = ldpc.encode(info, spec)
        rx = cw ^ (g.random(n) < p)
        hard, ok, it = ldpc.decode(hard_llr(rx), spec)
        good = ok and np.array_equal(hard, cw)
        fails += int(not good); und += int(ok and not np.array_equal(hard, cw)); iters += it
    return dict(p=p, bler=fails / trials, undetected=und, mean_iters=round(iters / trials, 1))
def era(e, p, seedbase):
    fails = und = 0
    for t in range(trials):
        g = np.random.default_rng(seedbase + t)
        info = g.integers(0, 2, k).astype(np.uint8)
        cw = ldpc.encode(info, spec)
        u = g.random(n); erased = u < e
        flip = (u >= e) & (g.random(n) < p)
        llr = hard_llr(cw ^ flip); llr[erased] = 0.0
        hard, ok, _ = ldpc.decode(llr, spec)
        fails += int(not (ok and np.array_equal(hard, cw))); und += int(ok and not np.array_equal(hard, cw))
    return dict(e=e, p=p, bler=fails / trials, undetected=und)
grid = [0.04, 0.055, 0.07, 0.085, 0.10, 0.115, 0.13, 0.15, 0.17]
out["bsc"] = [bsc(p, 50_000 + 1000 * i) for i, p in enumerate(grid) ]
out["erasure"] = [era(e, p, 70_000 + 1000 * i) for i, (e, p) in enumerate(
    [(0.20, 0.02), (0.30, 0.02), (0.40, 0.02), (0.50, 0.02), (0.60, 0.01), (0.50, 0.0), (0.60, 0.0)])]
print(json.dumps(out))
