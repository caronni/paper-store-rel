# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/confirm.py
"""Stage 3 — CONFIRMATION of the cross-tier finalists at fresh trials (scratch; added by the
2026-09-30 prep review).

Why: the tiers' finalists differ by 0.02-0.10 dB at 1 % BLER, the same order as the seed spread and
the 500-trial fine stage's resolution, and every finalist was SELECTED on trials 0..499 (winner's
curse).  This stage takes, per k, the top-N clean codes by BIAWGN Es/N0 @ 1 % over the union of the
Tier A / B1 / B2 runs (+ the top-M by BSC p @ 1 % not already in, + the frozen recipe), and measures
each on a fine grid around ITS OWN 1 % point with FRESH trial indices (t0 = 20_000: no screen ever
used them), so the ranking it prints is an unbiased re-measurement.

  Grid: awgn 0.05 dB, bsc 0.0025; start at the code's earlier 1 % point rounded to the grid, the
  points either side, then extend one step at a time until the 1 % point is bracketed (max 7 per
  channel).  Paired: every code sees the same trial seeds (common random numbers) at a shared grid.
  Eligibility: clean (0 syndrome-valid wrong decodes in s1/walk/fine), s0 pass, min w1/w2 >= --floor.
  Output: <out>/results.jsonl, one "s3conf" line per code (resume skips done codes; SIGINT/SIGTERM
  stop cleanly), and <out>/TABLES-confirm.md.

  cd <repo>; S=measure/rung-ladder/search
  PYTHONPATH=src:. env/bin/python $S/confirm.py --runs overnight-A overnight-B1 overnight-B2 \
      --out overnight-CONF --top 8 --top-hard 2 --trials 2000 --workers 14
"""
from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import variants_search as VS  # noqa: E402

T0_CONF = 20_000
STEP = {"awgn": 0.05, "bsc": 0.0025}
BSC_FINE_BELOW, BSC_FINE_STEP = 0.02, 0.0005   # r0775/r0850-class codes: p@1 % ~0.008-0.021 (TABLES.md)


def steps(start: dict) -> dict:
    """Grid per code: 0.0025 on BSC is 30 % of r0850's p@1 % and put its first point at p <= 0
    (smoke 2026-09-30: ZeroDivisionError / negative p in hard_llr) -> 0.0005 below p 0.02."""
    b = start.get("bsc")
    return {"awgn": STEP["awgn"], "bsc": BSC_FINE_STEP if b is not None and b < BSC_FINE_BELOW else STEP["bsc"]}
MAX_PTS = 7


def _best(done, rid):
    return done.get((rid, "s2fine")) or done.get((rid, "s2walk"))


def union(runs: list[Path]) -> dict:
    done: dict = {}
    for r in runs:
        if (r / "results.jsonl").exists():
            d, _ = common.load(r)
            for key, rec in d.items():
                done[key] = dict(rec, _src=r.name)
    return done


def select(done: dict, k: int, n_top: int, n_hard: int, floor: int) -> list[dict]:
    s0 = {rid: r for (rid, s), r in done.items() if s == "s0" and r["k"] == k}
    cands, base = [], []
    for (rid, s), r in done.items():
        if s != "s2walk" or r["k"] != k or rid not in s0:
            continue
        z = s0[rid]
        b = _best(done, rid)
        if z.get("baseline"):
            base.append(rid)
            continue
        st = z.get("struct", {})
        ok = z.get("status") == "pass" or (z.get("status") == "reject" and all(x.startswith("min_w2=") for x in z.get("reasons", [])))
        if not ok or min(st.get("min_w2") or 0, st.get("min_w1") or 0) < floor:
            continue
        if common.undetected(done, rid)[0] or b["es1"] is None:
            continue
        cands.append((b["es1"], -(b["p1"] or 0), rid))
    cands.sort()
    chosen = [rid for _, _, rid in cands[:n_top]]
    by_p = sorted(cands, key=lambda t: t[1])
    chosen += [rid for _, _, rid in by_p if rid not in chosen][:n_hard]
    chosen += base                       # every named baseline row (k=2240 has two frozen codes)
    return [s0[rid] for rid in chosen]


def _interp(pts, chn):
    rows = [((p["params"]["p"] if chn == "bsc" else p["params"]["esn0_db"]), p["fails"] / p["n"], p["n"])
            for p in pts if p["channel"] == chn]
    return common.htables.interp_x(rows, 0.01, chn == "bsc")


def job(z0: dict, n: int):
    """Generator for common.Runner: both channels, grid walk until the 1 % point is bracketed."""
    rid, k = z0["rid"], z0["k"]
    start = {"awgn": z0["_es1"], "bsc": z0["_p1"]}
    pts: list[dict] = []
    measured = {"awgn": {}, "bsc": {}}
    step = steps(start)

    def req(chn, x):
        x = round(x, 6)
        prm = {"p": x} if chn == "bsc" else {"esn0_db": x, "sigma": common.sigma_of(x)}
        return common.Req(chn, prm, n, t0=T0_CONF)

    todo = []
    for chn in ("awgn", "bsc"):
        if start[chn] is None:
            continue
        g = common.hsweep.grid_round(start[chn], step[chn])
        todo += [(chn, round(g + d * step[chn], 6)) for d in (-1, 0, 1)
                 if chn != "bsc" or 0 < round(g + d * step[chn], 6) < 0.5]
    while todo:
        reqs = [req(c, x) for c, x in todo]
        yield reqs
        for (c, x), r in zip(todo, reqs):
            rec = r.rec()
            pts.append(rec)
            measured[c][x] = rec["fails"] / rec["n"]
        todo = []
        for chn in ("awgn", "bsc"):
            m = measured[chn]
            if not m or _interp(pts, chn) is not None or len(m) >= MAX_PTS:
                continue
            harder_plus = chn == "bsc"
            xs = sorted(m)
            easiest = xs[0] if harder_plus else xs[-1]
            hardest = xs[-1] if harder_plus else xs[0]
            sgn = 1 if harder_plus else -1
            if all(b > 0.01 for b in m.values()):          # everything too hard: step easier
                nx = round(easiest - sgn * step[chn], 6)
            else:                                           # everything at or below 1 %: step harder
                nx = round(hardest + sgn * step[chn], 6)
            if chn == "bsc" and not 0 < nx < 0.5:
                continue
            todo.append((chn, nx))
    fr = common.frontier(pts, k)
    und = sum(p["und"] for p in pts)
    return {"rid": rid, "screen": "s3conf", "k": k, "tag": z0["tag"], "seed": z0["seed"],
            "tier": common.tier_of(z0), "src": z0.get("_src"), "t0": T0_CONF, "trials": n,
            "start": start, "step": step, "points": pts, **fr, "und": und,
            "und_w": [[p["channel"], p["params"].get("p", p["params"].get("esn0_db"))] + w
                      for p in pts for w in p.get("und_w", [])],
            "cpu": sum(p["cpu"] for p in pts)}


def table(out: Path, done_src: dict | None = None) -> list[str]:
    """Markdown: per k, the confirmed ranking (clean first, by Es/N0 @ 1 %)."""
    recs = {}
    if (out / "results.jsonl").exists():
        d, _ = common.load(out)
        recs = {rid: r for (rid, s), r in d.items() if s == "s3conf"}
    if not recs:
        return []
    L = ["# Confirmed ranking (stage 3: fresh trials t >= 20000, never used for selection)", "",
         "Per k: the top clean finalists across Tier A / B1 / B2 and the frozen recipe, re-measured on a "
         "0.05 dB / 0.0025 grid (0.0005 where p@1 % < 0.02) around their own 1 % points, `trials` per point, common random numbers. "
         "`und` = syndrome-valid wrong decodes in THIS stage (any > 0 disqualifies); `prior und` = those of "
         "s1/walk/fine.  Δ is against the recipe's confirmed point.", ""]
    for k in sorted({r["k"] for r in recs.values()}, reverse=True):
        rs = [r for r in recs.values() if r["k"] == k]
        base = next((r for r in rs if r["tier"] == "recipe"), None)
        R = k / common.N
        L += [f"## k = {k} (R = {R:.4f}); Shannon {common._f(common.ch.biawgn_shannon_esn0_db(R))} dB, "
              f"p_cap {common._f(common.ch.bsc_capacity_p(R), 4)}", "",
              "| # | tier | code | Es/N0@1% | Δ vs recipe dB | gap dB | p@1% | Δp vs recipe | gap bit | "
              "earlier Es/N0@1% (src) | trials/pt | und | prior und | awgn pts | bsc pts |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        rs.sort(key=lambda r: (r["und"] > 0 and r["tier"] != "recipe", r["es1"] if r["es1"] is not None else 99))
        for i, r in enumerate(rs, 1):
            prior = common.undetected(done_src, r["rid"])[0] if done_src else "—"
            aw = sorted((p["params"]["esn0_db"], p["fails"], p["n"]) for p in r["points"] if p["channel"] == "awgn")
            bs = sorted((p["params"]["p"], p["fails"], p["n"]) for p in r["points"] if p["channel"] == "bsc")
            L.append(
                f"| {i} | {r['tier']} | {r['rid']} | {common._f(r['es1'])} | "
                f"{common._f(None if not base or base['es1'] is None or r['es1'] is None else r['es1'] - base['es1'], 3)} | "
                f"{common._f(r['gap_db'], 2)} | {common._f(r['p1'], 4)} | "
                f"{common._f(None if not base or base['p1'] is None or r['p1'] is None else r['p1'] - base['p1'], 4)} | "
                f"{common._f(r['gap_bit'], 3)} | {common._f(r['start']['awgn'])} ({r['src']}) | {r['trials']} | "
                f"{r['und']}{' ⚠' if r['und'] else ''} | {prior} | "
                f"{', '.join(f'{x:.2f}:{f}' for x, f, _ in aw)} | {', '.join(f'{x:.4f}:{f}' for x, f, _ in bs)} |")
        L.append("")
    return L


def main(argv=None):
    common.term_as_interrupt()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", nargs="+", default=["overnight-A", "overnight-AF", "overnight-B1", "overnight-B2"])
    ap.add_argument("--out", default="overnight-CONF")
    ap.add_argument("--ks", default="1664,1280,1600,1216,2240,2560,2880,3200,3520")
    ap.add_argument("--top", type=int, default=8, help="top N clean codes per k by Es/N0 @ 1 %%")
    ap.add_argument("--top-hard", type=int, default=2, help="plus the top M by BSC p @ 1 %% not already in")
    ap.add_argument("--floor", type=int, default=16, help="min w1 / w2 of a confirmed code")
    ap.add_argument("--floor-frozen", default="incumbent",
                    help="min w1 / w2 at the frozen-rung k: 'incumbent' (default) = the weakest named baseline's own "
                         "min(w1, w2) at that k, as Tier A-frozen's screen 1; or an integer")
    ap.add_argument("--trials", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--chunk", type=int, default=50)
    ap.add_argument("--table-only", action="store_true")
    ap.add_argument("--decoder", default="fast", choices=("fast", "prod"),
                    help="fast = fast/fastdecode batched bit-exact twin (default; start-up selfcheck, falls back "
                         "to prod on failure), prod = holo.core.ldpc.decode one trial at a time")
    a = ap.parse_args(argv)
    sp = lambda x: Path(x) if Path(x).is_absolute() else common.SEARCH / x  # noqa: E731
    runs, out = [sp(r) for r in a.runs], sp(a.out)
    done = union(runs)
    if a.table_only:
        p = out / "TABLES-confirm.md"
        p.write_text("\n".join(table(out, done)) + "\n")
        print(p)
        return
    out.mkdir(parents=True, exist_ok=True)
    have = {}
    if (out / "results.jsonl").exists():
        d, _ = common.load(out)
        have = {rid: r for (rid, s), r in d.items() if s == "s3conf" and r.get("trials") == a.trials
                and r.get("t0") == T0_CONF}
    todo = []
    for k in [int(x) for x in a.ks.split(",")]:
        fl = a.floor
        if k in common.FROZEN_RUNGS:
            bs = [r["struct"] for (rid, sc), r in done.items() if sc == "s0" and r["k"] == k and r.get("baseline") and r.get("struct")]
            fl = (min(min(x["min_w1"], x["min_w2"]) for x in bs) if bs else 0) if a.floor_frozen == "incumbent" \
                else int(a.floor_frozen)
        for z in select(done, k, a.top, a.top_hard, fl):
            b = _best(done, z["rid"])
            z = dict(z, _es1=b["es1"], _p1=b["p1"])
            if z["rid"] not in have:
                todo.append(z)
    print(f"[confirm] {len(todo)} codes to measure ({len(have)} done) from {[r.name for r in runs]} -> {out}",
          file=sys.stderr, flush=True)
    fh = open(out / "results.jsonl", "a")
    fh.write(json.dumps({"rid": "__meta__", "screen": f"run@{time.strftime('%Y-%m-%dT%H:%M:%S')}", "mode": "confirm",
                         "args": vars(a), "t0": T0_CONF}) + "\n")
    fh.flush()
    common.select_decoder(a.decoder, ["r0406"])
    runner = VS.VRunner(a.workers, a.chunk)
    t0 = time.time()
    cnt = [0, len(todo)]

    def on_done(rec):
        fh.write(json.dumps(rec, default=float) + "\n")
        fh.flush()
        cnt[0] += 1
        print(f"[{time.time() - t0:7.0f}s] confirm {cnt[0]}/{cnt[1]} {rec['rid']} es1 {common._f(rec['es1'])} "
              f"p1 {common._f(rec['p1'], 4)} und {rec['und']}", file=sys.stderr, flush=True)

    def on_error(e):
        cnt[0] += 1

    for z in todo:
        b = z.get("build", {})
        hint = [b["restart"], b["edge_sha"]] if b.get("edge_sha") else b.get("restart")
        runner.start(job(z, a.trials), 0, z["cfg"], hint, on_done, on_error)

    def handler(signum, frame):
        print(f"\n[signal {signum}] stopping: completed lines are on disk, rerun resumes", file=sys.stderr, flush=True)
        runner.stop = True
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    def tick():
        el = time.time() - t0
        print(f"[{el:7.0f}s] confirm {cnt[0]}/{cnt[1]} | decodes {runner.decodes} ({runner.decodes / max(el, 1):.0f}/s) "
              f"queue {len(runner.queue)} errors {runner.errors}", file=sys.stderr, flush=True)
    runner.loop(tick)
    fh.close()
    p = out / "TABLES-confirm.md"
    p.write_text("\n".join(table(out, done)) + "\n")
    print(f"{'finished' if not runner.stop else 'STOPPED (rerun resumes)'}; errors {runner.errors}; -> {p}",
          file=sys.stderr)
    common.exit_status(not runner.stop, runner.errors)


if __name__ == "__main__":
    main()
