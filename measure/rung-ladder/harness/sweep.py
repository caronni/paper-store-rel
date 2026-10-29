# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/harness/sweep.py
"""ONE run -> results.json.  Adaptive walks for (a) BSC and (b) BIAWGN per
code, fixed grid for (c) erasure+error, (d) shorten-vs-puncture bracketing
each code's (a) 1 % point, and (e) an exact replicate of the recorded
battery in tests/test_ldpc.py (mag 4.0 hard LLRs, seeds 50_000/60_000 + t).
12-process pool over (code, channel, point, 50-trial chunk) tasks."""
from __future__ import annotations
import json, math, sys, time, argparse
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import codes, channels as ch  # noqa: E402

WORK = codes.WORK
CHUNK = 50


def grid_round(x: float, step: float) -> float:
    return round(round(x / step) * step, 6)


class Point:
    def __init__(self, rid, channel, params, n_trials):
        self.rid, self.channel, self.params, self.n_trials = rid, channel, params, n_trials
        self.n = self.fails = self.und = self.iters = self.iters_ok = self.n_ok = 0
        self.pending = 0
        self.key = (rid, channel, json.dumps(params, sort_keys=True))

    def add(self, r):
        self.n += r["n"]; self.fails += r["fails"]; self.und += r["undetected"]
        self.iters += r["iters"]; self.iters_ok += r["iters_ok"]; self.n_ok += r["n_ok"]; self.pending -= 1

    @property
    def done(self): return self.pending == 0 and self.n >= self.n_trials
    @property
    def bler(self): return self.fails / self.n if self.n else float("nan")

    def record(self):
        return {"rid": self.rid, "channel": self.channel, "params": self.params, "n": self.n,
                "fails": self.fails, "bler": self.bler, "undetected": self.und,
                "mean_iters": self.iters / self.n if self.n else None,
                "mean_iters_ok": self.iters_ok / self.n_ok if self.n_ok else None}


class Walk:
    """Down/up frontier walk over a 1-D grid.  'down' = the harder side
    (higher p / lower Es/N0) is where the walk starts (capacity point)."""
    def __init__(self, rid, channel, start, step, harder_is_plus, n_trials, mk):
        self.rid, self.channel, self.step, self.mk = rid, channel, step, mk
        self.sign = 1 if harder_is_plus else -1   # +step = harder
        self.n_trials = n_trials
        self.easy_next = round(start, 6); self.hard_next = round(start + self.sign * step, 6)   # rounded: an unrounded key re-submitted r0625's hard point on every easy step in the 2026-09-30 run (identical seeds, CPU waste only)
        self.easy_zero_run = 0; self.easy_done = False; self.hard_done = False
        self.points: dict[float, Point] = {}
        self.finished = False

    def next_points(self):
        out = []
        if not self.easy_done and self.easy_next not in self.points:
            out.append(self.easy_next)
        if not self.hard_done and self.hard_next not in self.points:
            out.append(self.hard_next)
        pts = []
        for x in out:
            x = round(x, 6)
            if (self.channel == "bsc" and x <= 0) or (self.channel == "bsc" and x >= 0.5):
                continue
            pt = Point(self.rid, self.channel, self.mk(x), self.n_trials); self.points[x] = pt; pts.append(pt)
        return pts

    def on_point_done(self, x):
        pt = self.points[x]
        if x == self.easy_next:
            self.easy_zero_run = self.easy_zero_run + 1 if pt.fails == 0 else 0
            if self.easy_zero_run >= 2 or self.easy_next - self.sign * self.step <= 0 and self.channel == "bsc":
                self.easy_done = True
            else:
                self.easy_next = round(self.easy_next - self.sign * self.step, 6)
        if x == self.hard_next:
            if pt.bler >= 0.5:
                self.hard_done = True
            else:
                self.hard_next = round(self.hard_next + self.sign * self.step, 6)
        self.finished = self.easy_done and self.hard_done


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="tiny grid: 2 codes, 20 trials")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--out", default=str(WORK / "results.json"))
    a = ap.parse_args(argv)
    rids = ["r0313", "r0547"] if a.smoke else codes.ALL
    NT = 20 if a.smoke else a.trials
    eps_grid = [0.2, 0.5] if a.smoke else [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    p_grid = [0.02] if a.smoke else [0.01, 0.02, 0.05]
    t_start = time.time()
    walks: list[Walk] = []
    for rid in rids:
        R = codes.spec(rid).rate
        p_cap = ch.bsc_capacity_p(R)
        walks.append(Walk(rid, "bsc", grid_round(p_cap, 0.005), 0.005, True, NT, lambda p: {"p": p}))
        es = ch.biawgn_shannon_esn0_db(R)
        walks.append(Walk(rid, "awgn", grid_round(es, 0.25), 0.25, False, NT,
                          lambda db: {"esn0_db": db, "sigma": math.sqrt(1 / (2 * 10 ** (db / 10)))}))
    backlog: list[Point] = []          # fixed grids, throttled
    for rid in rids:
        for eps in eps_grid:
            for p in p_grid:
                backlog.append(Point(rid, "eras", {"eps": eps, "p": p}, NT))
    # (e) recorded-battery replicate (exact test conditions)
    rec = [("r0700", 0.035, 50_000), ("r0700", 0.015, 50_000), ("r0550", 0.055, 60_000),
           ("r0547", 0.055, 60_000), ("r0625", 0.045, 60_000), ("r0775", 0.020, 60_000),
           ("r0850", 0.010, 60_000), ("r0850", 0.005, 60_000)]
    for rid, p, sb in rec:
        if rid in rids:
            backlog.append(Point(rid, "record", {"p": p, "mag": 4.0, "seed_base": sb}, NT))
    accom_rids = [r for r in ["r0313", "r0391", "r0547"] if r in rids]
    accom_started: set[str] = set()
    points: dict[tuple, Point] = {}
    futures = {}
    log = open(WORK / "sweep_progress.log", "a")

    def submit(ex, pt: Point):
        points[pt.key] = pt
        for t0 in range(0, pt.n_trials, CHUNK):
            n = min(CHUNK, pt.n_trials - t0)
            f = ex.submit(ch.run_task, pt.rid, pt.channel, pt.params, t0, n)
            futures[f] = pt; pt.pending += 1

    def walk_owner(pt):
        for w in walks:
            if w.rid == pt.rid and w.channel == pt.channel:
                return w
        return None

    def bler_1pct_grid(w: Walk):
        """largest-p (bsc) / smallest-Es/N0 (awgn) grid point with BLER <= 1%."""
        ok = [x for x, pt in w.points.items() if pt.bler <= 0.01]
        if not ok:
            return None
        return max(ok) if w.channel == "bsc" else min(ok)

    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for w in walks:
            for pt in w.next_points():
                submit(ex, pt)
        n_done = 0
        while futures or backlog:
            while backlog and len(futures) < 2 * a.workers:
                submit(ex, backlog.pop(0))
            if not futures:
                continue
            done, _ = wait(list(futures), return_when=FIRST_COMPLETED)
            for f in done:
                pt = futures.pop(f); r = f.result(); pt.add(r); n_done += 1
                if pt.done:
                    print(f"[{time.time()-t_start:7.1f}s] {pt.rid:10s} {pt.channel:6s} {pt.params} "
                          f"fails {pt.fails}/{pt.n} und {pt.und} it {pt.iters/pt.n:.1f}", file=log, flush=True)
                    w = walk_owner(pt)
                    if w is not None:
                        x = pt.params["p"] if w.channel == "bsc" else pt.params["esn0_db"]
                        w.on_point_done(x)
                        for np_ in w.next_points():
                            submit(ex, np_)
                        if w.channel == "bsc" and w.finished and pt.rid in accom_rids and pt.rid not in accom_started:
                            accom_started.add(pt.rid)
                            p1 = bler_1pct_grid(w)
                            if p1 is not None:
                                for p in (round(p1 - 0.005, 6), p1, round(p1 + 0.005, 6)):
                                    for v in ("mother", "shorten", "punct_last", "punct_even"):
                                        backlog.append(Point(pt.rid, "accom", {"p": p, "variant": v}, NT))
        wall = time.time() - t_start
    res = {"meta": {"trials_per_point": NT, "chunk": CHUNK, "workers": a.workers, "wall_seconds": wall,
                    "codes": rids, "seed_bases": ch.BASE, "smoke": a.smoke,
                    "command": "cd <repo> && PYTHONPATH=src:. env/bin/python "
                               "measure/rung-ladder/harness/sweep.py " + " ".join(argv or sys.argv[1:]),
                    "capacity": {rid: {"rate": codes.spec(rid).rate, "p_cap": ch.bsc_capacity_p(codes.spec(rid).rate),
                                       "esn0_shannon_db": ch.biawgn_shannon_esn0_db(codes.spec(rid).rate)} for rid in rids}},
           "points": [pt.record() for pt in points.values()]}
    Path(a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(f"done: {len(points)} points, {n_done} chunks, wall {wall:.0f} s -> {a.out}")


if __name__ == "__main__":
    main()
