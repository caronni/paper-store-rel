# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/cost_fit.py
import time, numpy as np
from holo.core.ldpc.construct import LADDER, load_code
from holo.core.ldpc.decode import decode
rng = np.random.default_rng(1)
rows = []
for rid in LADDER:
    code = load_code(rid); m = code.spec.m_bits
    llr = rng.normal(0, 0.3, 4096)
    t = []
    for _ in range(7):
        t0 = time.perf_counter(); decode(llr, rid, max_iters=60, alpha=0.8); t.append(time.perf_counter()-t0)
    rows.append((rid, code.n_edges, m, np.median(t)*1e3))
    print(f"{rid}: E={code.n_edges} m={m} median {np.median(t)*1e3:.1f} ms (60 min-sum iters, no convergence, + 1 sum-product retry)")
# fit t = a*E + b*m + c
A = np.array([[e, m, 1.0] for _, e, m, _ in rows]); y = np.array([t for *_, t in rows])
coef, *_ = np.linalg.lstsq(A, y, rcond=None)
print(f"fit t_ms = {coef[0]*1e3:.4f}*E/1000 + {coef[1]*1e3:.4f}*m/1000 + {coef[2]:.2f}")
def E_of(k, hd=10):
    kb=k//64; m=4096-k; nh=round(0.3*kb); return 64*(hd*nh+3*(kb-nh)) + 2*m-1, m
print("\npredicted full-budget attempt cost (ms, 60 iters) and ratio vs r0547:")
base = coef @ np.array([*E_of(2240), 1])
for k, hd in ((1024,10),(1280,10),(1600,10),(2240,10),(2880,10),(3520,6)):
    e, m = E_of(k, hd); t = coef @ np.array([e, m, 1])
    print(f"  k={k}: E={e} m={m} t={t:.1f} ms ratio {t/base:.3f}")
print("\nreceiver attempt floor k_eff = k_bits - n_sites (tiles.py:143-145), as a fraction of the 4096-p payload cells:")
for k in (1024,1280,1600,2240,2880,3520):
    for p in (100,120):
        print(f"  k={k} p={p}: floor {k-p} informative cells of {4096-p} = {(k-p)/(4096-p):.3f}; a tile may lose up to {4096-k} cells ({(4096-k)/(4096-p):.1%}) and still be attempted")
