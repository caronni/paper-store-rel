# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/c1/floor_diag.py
"""Floor diagnostic: at the recipe codes' near-1% floor points, which trial ids fail
(common random numbers), how many bits are wrong, and whether max_iters 200/500
(production default 60 + retry) clears them.  Same seeds as the sweep."""
from __future__ import annotations
import json, math, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import numpy as np
C1 = Path(__file__).resolve().parent
sys.path.insert(0, str(C1))
import codes_c1  # noqa: E402
from codes_c1 import ch  # noqa: E402
from holo.core.ldpc.decode import decode, encode  # noqa: E402

CASES = [("r0203", "bsc", 0.150), ("r0203", "bsc", 0.160), ("r0203", "awgn", -5.25), ("r0203", "awgn", -5.0),
         ("r0250", "bsc", 0.150), ("r0250", "awgn", -4.0), ("r0250", "awgn", -3.75),
         ("r0203-f50", "bsc", 0.185), ("r0234", "awgn", -5.0), ("r0281", "awgn", -4.0)]


def one(case):
    rid, chan, x = case; k = codes_c1.codes.spec(rid).k_bits; out = []
    for t in range(200):
        g = np.random.default_rng(ch.BASE[chan] + t)
        info = g.integers(0, 2, k).astype(np.uint8); cw = encode(info, rid)
        if chan == "bsc":
            llr = ch.hard_llr(cw ^ (g.random(4096) < x), x)
        else:
            s = math.sqrt(1 / (2 * 10 ** (x / 10))); y = (1.0 - 2.0 * cw) + s * g.standard_normal(4096); llr = -2.0 * y / (s * s)
        ok, h, it = decode(llr, rid)
        if ok and (h == cw).all():
            continue
        rec = {"t": t, "ok60": ok, "biterr60": int((h != cw).sum())}
        for mi in (200, 500):
            ok2, h2_, it2 = decode(llr, rid, max_iters=mi)
            rec[f"good{mi}"] = bool(ok2 and (h2_ == cw).all()); rec[f"biterr{mi}"] = int((h2_ != cw).sum())
        out.append(rec)
    return {"rid": rid, "channel": chan, "x": x, "fails": out}


if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(one, CASES))
    for r in res:
        print(r["rid"], r["channel"], r["x"], "fails", len(r["fails"]), [(f["t"], f["biterr60"], f["good200"], f["good500"]) for f in r["fails"]])
    (C1 / "floor_diag.json").write_text(json.dumps(res, indent=1) + "\n")
