"""Seed-0 screen 0 (build + structural audit) of recipe_search's grid at the given k (overnight prep
2026-09-30): which configs build within the 120 s cap, and their min w1 / w2 (for the per-k floor).
Output rows: [[k, heavy_deg, heavy_frac, light, placement], verdict, restart, cpu_s, min_w1, min_w2]
(verdict 'ok' = built; the first four fields are feasibility.py's format, so recipe_search
--skip-infeasible reads either).

  PYTHONPATH=src:. env/bin/python $S/feasibility2.py 2240,2560,2880,3200,3520 $S/feasibility-frozen-seed0.json
"""
import json
import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import recipe_search as RS  # noqa: E402


def one(cfgd):
    t = time.process_time()
    r = common.screen0(cfgd)
    st = r.get("struct", {})
    verdict = "ok" if "restart" in r.get("build", {}) else r["reasons"][0]
    return verdict, r.get("build", {}).get("restart"), round(time.process_time() - t, 2), st.get("min_w1"), st.get("min_w2")


if __name__ == "__main__":
    ks = [int(x) for x in sys.argv[1].split(",")]
    cfgs = [c for c in RS.grid("overnight", ks, 1, 1) if c.seed == 0]
    w = int(sys.argv[3]) if len(sys.argv) > 3 else 14
    t0 = time.time()
    with ProcessPoolExecutor(w, mp_context=mp.get_context("spawn")) as ex:
        res = list(ex.map(one, [c.to_dict() for c in cfgs]))
    out = [[list(RS.cfg_key(c)), *r] for c, r in zip(cfgs, res)]
    Path(sys.argv[2]).write_text(json.dumps(out) + "\n")
    from collections import Counter
    print(Counter(r[1] for r in out), f"wall {time.time() - t0:.0f} s")
    for k in ks:
        rr = [r for r in out if r[0][0] == k and r[1] == "ok"]
        ws = sorted(min(r[4] or 0, r[5] or 0) for r in rr)
        print(k, "built", len(rr), "min(w1,w2) distribution", ws)
    for r in out:
        if r[1] != "ok":
            print(r)
