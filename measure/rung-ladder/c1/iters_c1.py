# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/c1/iters_c1.py
"""SUPPLEMENT (not the production decoder setting): re-run every (a)/(b) walk point of
the c1 codes (+ r0250, whose previous-run 3.06 dB gap is floor-driven) with
max_iters=200 (min-sum 200 + sum-product retry 200) instead of production's 60.
Same seeds/trials as the sweep (common random numbers) -> c1/iters-c1.json."""
from __future__ import annotations
import functools, json, sys, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
C1 = Path(__file__).resolve().parent
sys.path.insert(0, str(C1))
import codes_c1  # noqa: E402
from codes_c1 import ch  # noqa: E402
MI = 200


def task(rid, channel, params, t0, n):
    from holo.core.ldpc import decode as D
    ch.decode = functools.partial(D.decode, max_iters=MI)
    return ch.run_task(rid, channel, params, t0, n)


if __name__ == "__main__":
    t_start = time.time()
    new = json.loads((C1 / "results-c1-raw.json").read_text())["points"]
    old = json.loads((C1.parent / "results.json").read_text())["points"]
    pts = [p for p in new if p["channel"] in ("bsc", "awgn")] + [p for p in old if p["rid"] == "r0250" and p["channel"] in ("bsc", "awgn")]
    pts = [p for p in pts if 0 < p["bler"] < 0.6 or p["fails"] == 0]      # skip the dead 1.0 tail
    jobs = [(p["rid"], p["channel"], p["params"], t0, 50) for p in pts for t0 in range(0, 200, 50)]
    with ProcessPoolExecutor(max_workers=14) as ex:
        rs = list(ex.map(task, *zip(*jobs)))
    agg = {}
    for r in rs:
        key = (r["rid"], r["channel"], json.dumps(r["params"], sort_keys=True))
        a = agg.setdefault(key, {"rid": r["rid"], "channel": r["channel"], "params": r["params"], "n": 0, "fails": 0, "undetected": 0, "iters": 0})
        a["n"] += r["n"]; a["fails"] += r["fails"]; a["undetected"] += r["undetected"]; a["iters"] += r["iters"]
    out = []
    for a in agg.values():
        a["bler"] = a["fails"] / a["n"]; a["mean_iters"] = a["iters"] / a["n"]; out.append(a)
    wall = time.time() - t_start
    (C1 / "iters-c1.json").write_text(json.dumps({"meta": {"max_iters": MI, "wall_seconds": wall, "command": "cd <repo> && PYTHONPATH=src:. env/bin/python measure/rung-ladder/c1/iters_c1.py"}, "points": out}, indent=1) + "\n")
    print(f"done {len(out)} points wall {wall:.0f} s")
