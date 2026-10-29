# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/c1/sweep_c1.py
"""ONE run -> c1/results-c1.json.  (a) BSC and (b) BIAWGN adaptive walks (the old
harness's Walk/Point, imported unchanged: 0.005 p grid from the BSC-capacity point,
0.25 dB grid from the Shannon point; down until two consecutive 0/n, up until
BLER >= 0.5) and (c) erasure+error on eps {0.3,0.5,0.7} x p {0.02,0.05}, over the
ten c1 codes.  Seeds, chunking and decoder = the old harness (channels.run_task,
BASE bsc 100000 / awgn 200000 / eras 300000 + t)."""
from __future__ import annotations
import argparse, json, math, sys, time
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
C1 = Path(__file__).resolve().parent
sys.path.insert(0, str(C1))
import codes_c1  # noqa: E402
from codes_c1 import ch  # noqa: E402
import sweep as old  # noqa: E402  (../harness/sweep.py: Walk, Point, grid_round, CHUNK)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--no-eras", action="store_true")
    ap.add_argument("--out", default=str(C1 / "results-c1.json"))
    a = ap.parse_args(argv)
    rids = ["r0203", "r0281-f50"] if a.smoke else codes_c1.NEW
    NT = 20 if a.smoke else a.trials
    eps_grid, p_grid = ([0.5], [0.02]) if a.smoke else ([0.3, 0.5, 0.7], [0.02, 0.05])
    t_start = time.time()
    walks = []
    for rid in rids:
        R = codes_c1.codes.spec(rid).rate
        walks.append(old.Walk(rid, "bsc", old.grid_round(ch.bsc_capacity_p(R), 0.005), 0.005, True, NT, lambda p: {"p": p}))
        walks.append(old.Walk(rid, "awgn", old.grid_round(ch.biawgn_shannon_esn0_db(R), 0.25), 0.25, False, NT,
                              lambda db: {"esn0_db": db, "sigma": math.sqrt(1 / (2 * 10 ** (db / 10)))}))
    backlog = [] if a.no_eras else [old.Point(rid, "eras", {"eps": e, "p": p}, NT) for rid in rids for e in eps_grid for p in p_grid]
    points, futures = {}, {}
    log = open(C1 / ("sweep_progress_smoke.log" if a.smoke else "sweep_progress.log"), "a")

    def submit(ex, pt):
        points[pt.key] = pt
        for t0 in range(0, pt.n_trials, old.CHUNK):
            n = min(old.CHUNK, pt.n_trials - t0)
            futures[ex.submit(codes_c1.run_task, pt.rid, pt.channel, pt.params, t0, n)] = pt; pt.pending += 1

    def owner(pt):
        return next((w for w in walks if w.rid == pt.rid and w.channel == pt.channel), None)

    n_done = 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for w in walks:
            for pt in w.next_points():
                submit(ex, pt)
        while futures or backlog:
            while backlog and len(futures) < 2 * a.workers:
                submit(ex, backlog.pop(0))
            if not futures:
                continue
            done, _ = wait(list(futures), return_when=FIRST_COMPLETED)
            for f in done:
                pt = futures.pop(f); pt.add(f.result()); n_done += 1
                if pt.done:
                    print(f"[{time.time()-t_start:7.1f}s] {pt.rid:10s} {pt.channel:6s} {pt.params} fails {pt.fails}/{pt.n} und {pt.und} it {pt.iters/pt.n:.1f}", file=log, flush=True)
                    w = owner(pt)
                    if w is not None:
                        w.on_point_done(pt.params["p"] if w.channel == "bsc" else pt.params["esn0_db"])
                        for q in w.next_points():
                            submit(ex, q)
    wall = time.time() - t_start
    res = {"meta": {"trials_per_point": NT, "chunk": old.CHUNK, "workers": a.workers, "wall_seconds": wall,
                    "codes": rids, "seed_bases": ch.BASE, "smoke": a.smoke, "eps_grid": eps_grid, "p_grid": p_grid,
                    "command": "cd <repo> && PYTHONPATH=src:. env/bin/python measure/rung-ladder/c1/sweep_c1.py " + " ".join(argv or sys.argv[1:]),
                    "capacity": {r: {"rate": codes_c1.codes.spec(r).rate, "p_cap": ch.bsc_capacity_p(codes_c1.codes.spec(r).rate),
                                     "esn0_shannon_db": ch.biawgn_shannon_esn0_db(codes_c1.codes.spec(r).rate)} for r in rids}},
           "points": [pt.record() for pt in points.values()]}
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(f"done: {len(points)} points, {n_done} chunks, wall {wall:.0f} s -> {a.out}")


if __name__ == "__main__":
    main()
