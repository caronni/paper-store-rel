import sys, time
sys.path.insert(0, "scratch/rung-ladder-20260930/search")
import common
from dataclasses import replace
for k, hd, hf, pl in [(3520, 6, 0.3, "balanced"), (3520, 6, 0.3, "uniform"), (3520, 4, 0.3, "balanced"), (3200, 8, 0.3, "balanced"),
                      (2880, 10, 0.3, "balanced"), (2880, 16, 0.5, "balanced"), (2240, 10, 0.3, "balanced"), (2560, 14, 0.5, "uniform")]:
    c = replace(common.recipe_cfg(k, hd, hf, 3, pl, 0), max_build_s=30)
    t = time.time()
    try:
        _, info = common.build(c)
        print(k, hd, hf, pl, "ok restart", info["restart"], info["reasons"], f"{time.time()-t:.1f}s", flush=True)
    except common.BuildFail as e:
        print(k, hd, hf, pl, e.reason, e.info, f"{time.time()-t:.1f}s", flush=True)
