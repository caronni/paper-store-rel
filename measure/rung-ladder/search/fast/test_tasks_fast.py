# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/fast/test_tasks_fast.py
"""tasks_fast == the trial loops it twins, dict for dict, on every channel:
run_chan_fast vs search/common.run_chan (bsc/awgn/eras/robust, und_w included),
run_task_fast vs harness/channels.run_task (every harness channel).

Run:  cd <repo> && PYTHONPATH=src:. env/bin/python \
      measure/rung-ladder/search/fast/test_tasks_fast.py
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import tasks_fast as tf  # noqa: E402
import channels as ch  # noqa: E402
import common  # noqa: E402  (search/common.py, read-only use)

N_T = 48
CASES = []
for rid in ("r0406", "r0550", "r0313"):
    k = tf.construct.LADDER[rid].k_bits
    R = k / tf.N
    pc = ch.bsc_capacity_p(R)
    sh = ch.biawgn_shannon_esn0_db(R)
    CASES += [
        (rid, "bsc", {"p": 0.8 * pc}),
        (rid, "awgn", {"esn0_db": sh + 0.8, "sigma": common.sigma_of(sh + 0.8)}),
        (rid, "eras", {"p": 0.02, "eps": 0.3}),
        (rid, "accom", {"p": 0.6 * pc, "variant": "shorten"}),
        (rid, "accom", {"p": 0.6 * pc, "variant": "punct_last"}),
        (rid, "accom", {"p": 0.6 * pc, "variant": "punct_even"}),
        (rid, "accom", {"p": 0.6 * pc, "variant": "mother"}),
        (rid, "record", {"p": 0.7 * pc, "mag": 3.0, "seed_base": 50_000}),
    ]
    CASES += [(rid, "chan:" + c, prm) for c, prm in (
        ("bsc", {"p": 0.85 * pc}),
        ("awgn", {"esn0_db": sh + 0.6, "sigma": common.sigma_of(sh + 0.6)}),
        ("eras", {"p": 0.03, "eps": 0.3}),
        ("robust", {"sigma": common.sigma_of(sh + 1.0), "f": 0.01}))]


def one(case) -> tuple:
    rid, chan, prm = case
    for b in (7, 64):
        if chan.startswith("chan:"):
            a = common.run_chan(rid, chan[5:], prm, 3, N_T)
            f = tf.run_chan_fast(rid, chan[5:], prm, 3, N_T, batch=b)
        else:
            a = ch.run_task(rid, chan, prm, 3, N_T)
            f = tf.run_task_fast(rid, chan, prm, 3, N_T, batch=b)
        if a != f:
            return case, b, a, f
    return case, None, a, f


def main() -> int:
    assert tf.BASE_ROBUST == common.BASE_ROBUST
    bad = 0
    with ProcessPoolExecutor(8) as ex:
        for case, b, a, f in ex.map(one, CASES):
            tag = "OK " if b is None else f"MISMATCH (batch {b})"
            print(tag, case[0], case[1], {k: v for k, v in case[2].items() if k != "sigma"},
                  {k: a[k] for k in ("fails", "undetected", "iters", "n_ok")},
                  "und_w=%d" % len(a.get("und_w", [])))
            if b is not None:
                bad += 1
                print("   harness:", a, "\n   fast:   ", f)
    print("TASKS: PASS" if bad == 0 else f"TASKS: FAIL ({bad})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
