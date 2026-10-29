"""run_chan vs run_chan_fast where syndrome-valid WRONG decodes happen (the und_w path test_tasks_fast
never exercised): base-r0550 (frozen, error floor) on bsc p=0.05 and awgn -1.25 dB, 400 trials each."""
import sys
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, "scratch/rung-ladder-20260930/search")
import common

CASES = [("bsc", {"p": 0.05}, 0), ("bsc", {"p": 0.05}, 400), ("awgn", {"esn0_db": -1.25, "sigma": common.sigma_of(-1.25)}, 0),
         ("awgn", {"esn0_db": -1.25, "sigma": common.sigma_of(-1.25)}, 400), ("bsc", {"p": 0.035}, 0),
         ("robust", {"esn0_db": -1.0, "sigma": common.sigma_of(-1.0), "f": 0.002}, 0)]


def one(c):
    ch, prm, t0 = c
    rid = common.register(common.frozen_cfg("r0550"))
    a = common.run_chan(rid, ch, prm, t0, 400)
    b = common._fast().run_chan_fast(rid, ch, prm, t0, 400, batch=50)
    return c, a == b, a["fails"], a["undetected"], len(a["und_w"])


if __name__ == "__main__":
    bad = 0
    with ProcessPoolExecutor(6) as ex:
        for c, ok, f, u, nw in ex.map(one, CASES):
            print("OK " if ok else "MISMATCH", c[0], {k: v for k, v in c[1].items() if k != "sigma"}, "t0", c[2],
                  "fails", f, "undetected", u, "und_w entries", nw)
            bad += not ok
    print("UND-IDENTITY: PASS" if not bad else f"UND-IDENTITY: FAIL {bad}")
