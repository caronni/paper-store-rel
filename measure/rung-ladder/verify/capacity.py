# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/verify/capacity.py
"""Independent checks of the harness's arithmetic: BSC capacity p, BIAWGN
Shannon Es/N0 (scipy.integrate.quad, not Gauss-Hermite), the p@1% / Es/N0@1%
log-linear interpolation recomputed from the raw grid, the erasure capacity
margin, and the 'record' replicate's seed/trial-count claim."""
from __future__ import annotations
import json, math
from pathlib import Path
import numpy as np
from scipy.integrate import quad
from scipy.optimize import brentq
WORK = Path(__file__).resolve().parents[1]
res = json.loads((WORK / "results.json").read_text()); meta = res["meta"]; P = res["points"]


def h2(p):
    return 0.0 if p <= 0 or p >= 1 else -p * math.log2(p) - (1 - p) * math.log2(1 - p)


def biawgn_C(sigma):
    # C = 1 - E_y[log2(1+exp(-2y/s^2))], y ~ N(1, s^2)
    f = lambda y: math.exp(-(y - 1) ** 2 / (2 * sigma ** 2)) / math.sqrt(2 * math.pi) / sigma * np.logaddexp(0.0, -2 * y / sigma ** 2) / math.log(2)
    return 1 - quad(f, 1 - 12 * sigma, 1 + 12 * sigma, limit=400)[0]


out = {}
for rid, c in meta["capacity"].items():
    R = c["rate"]
    p_cap = brentq(lambda p: 1 - h2(p) - R, 1e-6, 0.5 - 1e-9)
    s = brentq(lambda s: biawgn_C(s) - R, 0.1, 4.0)
    es = 10 * math.log10(1 / (2 * s * s))
    out[rid] = {"R": R, "p_cap_mine": round(p_cap, 5), "p_cap_harness": round(c["p_cap"], 5),
                "esn0_mine": round(es, 3), "esn0_harness": round(c["esn0_shannon_db"], 3)}
print(json.dumps(out, indent=1))


def interp(pts, target, harder_plus):
    s = sorted(pts, key=lambda t: t[0] if harder_plus else -t[0])
    for (x0, b0, n0), (x1, b1, n1) in zip(s, s[1:]):
        if b0 <= target <= b1 and b1 > 0:
            lb0 = math.log(max(b0, 0.5 / n0)); lb1 = math.log(b1); lt = math.log(target)
            return x0 if lb1 == lb0 else x0 + (x1 - x0) * (lt - lb0) / (lb1 - lb0)
    return None


tab = json.loads((WORK / "tables.json").read_text())
chk = {}
for rid in ["r0547", "r0550", "r0313", "r0250", "r0391-f50"]:
    b = [(p["params"]["p"], p["fails"] / p["n"], p["n"]) for p in P if p["rid"] == rid and p["channel"] == "bsc"]
    a = [(p["params"]["esn0_db"], p["fails"] / p["n"], p["n"]) for p in P if p["rid"] == rid and p["channel"] == "awgn"]
    p1 = interp(b, 0.01, True); e1 = interp(a, 0.01, False)
    # also a plain LINEAR-in-BLER interpolation for contrast
    chk[rid] = {"p@1%_recomputed": round(p1, 4) if p1 else None, "gap_bits": round((1 - h2(p1)) - out[rid]["R"], 3) if p1 else None,
                "esn0@1%_recomputed": round(e1, 3) if e1 else None, "gap_db": round(e1 - out[rid]["esn0_mine"], 2) if e1 else None,
                "grid_around_1pct": sorted([(x, f"{int(bb*n)}/{n}") for x, bb, n in b if abs(x - (p1 or 0)) <= 0.0051])}
print(json.dumps(chk, indent=1))
# record replicate: n per point and seed base
rec = [(p["rid"], p["params"], p["n"], p["fails"]) for p in P if p["channel"] == "record"]
print("record points:", rec)
# erasure margin sanity at one cell: r0313 eps 0.5 p 0.02
print("r0313 margin eps=0.5 p=0.02:", round((1 - 0.5) * (1 - h2(0.02)) - 0.3125, 3))
(Path(__file__).resolve().parent / "capacity_results.json").write_text(json.dumps({"capacity": out, "interp": chk}, indent=1) + "\n")
