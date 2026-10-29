"""Build feasibility of the overnight grid, seed 0 of every config (build only, no audit)."""
import sys, time, json, itertools
sys.path.insert(0, "scratch/rung-ladder-20260930/search")
import common
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp

def one(args):
    k, hd, hf, lt, pl = args
    c = common.recipe_cfg(k, hd, hf, lt, pl, 0)
    t = time.process_time()
    try:
        _, info = common.build(c)
        return (args, "ok", info["restart"], time.process_time() - t)
    except common.BuildFail as e:
        return (args, e.reason, None, time.process_time() - t)

if __name__ == "__main__":
    ks = [int(x) for x in sys.argv[1].split(",")]
    G = list(itertools.product(ks, (6, 8, 10, 12, 14, 16), (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8), (3, 4), ("uniform", "balanced")))
    with ProcessPoolExecutor(14, mp_context=mp.get_context("spawn")) as ex:
        res = list(ex.map(one, G))
    json.dump(res, open(sys.argv[2], "w"))
    from collections import Counter
    print(Counter(r[1] for r in res), "cpu total %.0f s" % sum(r[3] for r in res))
    for r in res:
        if r[1] != "ok" or r[3] > 10: print(r)
