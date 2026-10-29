# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/de_profile.py
"""Tier B1: density-evolution-designed info-degree profiles for the e-IRA structure (scratch).

Pipeline (per k; n = 4096, Z = 64, kb = k/64 block columns, mb = (4096-k)/64 block rows):
  1. ENUMERATE every integer block-column profile with <= 3 distinct info degrees in DEG_SET
     (default 3..16; `--allow-d2` adds 2), then a 4-degree LOCAL SEARCH (move one block column
     between degrees) from the best profile of every total-edge level E_b.  Each profile's check
     side is the BALANCED placement's: E_b block edges over mb block rows -> x or x+1 info edges
     per check (+ the 2 accumulator edges).
  2. SCORE by the Gaussian-approximation DE threshold (de_engine.ga_threshold, Es/N0 dB); stability
     of the degree-2 subgraph is computed (automatic without degree-2 info columns).  The rate is
     fixed by k; E_b (the average check info degree a = E_b/mb) is the free outer variable and the
     GA-best profile is kept PER E_b level ("the LP over lambda for a fixed check profile").
  3. SELECT candidates across a-levels (the finite-length decoder does not share DE's preferred a,
     measured on Tier A: GA ranks f0.3/h12 first at k<=1280, screen 1 ranks f0.5 first), re-score
     them with population-dynamics DE (de_engine.mc_threshold, exact BP check rule).
  4. BUILD through common.Cfg (balanced placement, rule (e) restart, seeds 0..S-1) and run the
     common.Search screens into <out>/results.jsonl; the summary is common.summarize plus a DE
     section (GA/MC thresholds per profile, GA vs measured rank correlation over EVERY code in the
     run, Tier A included when merged).

  cd <repo>; S=measure/rung-ladder/search
  PYTHONPATH=src:. env/bin/python $S/de_profile.py --de-only            # DE tables only (seconds)
  PYTHONPATH=src:. env/bin/python $S/de_profile.py --smoke --workers 8
  PYTHONPATH=src:. env/bin/python $S/de_profile.py --trial --workers 12 [--secondary]
  nohup env PYTHONPATH=src:. env/bin/python $S/de_profile.py --overnight --workers 14 [--secondary] [--seeds 12] \
      [--min-w2 16] > $S/overnight-B1.log 2>&1 &
  PYTHONPATH=src:. env/bin/python $S/de_profile.py --summarize-only --out $S/overnight-B1 \
      --merge $S/overnight-A --merged-out $S/overnight-AB1        # Tier A + B1 in ONE ranked table
"""
from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import de_engine as de  # noqa: E402

N, Z = 4096, 64
TIER = "B1"


# ------------------------------------------------------------------ enumeration + GA
def spell(p: dict) -> str:
    return ".".join(f"{d}x{c}" for d, c in sorted(p.items(), reverse=True))


def unspell(s: str) -> dict:
    return {int(a): int(b) for a, b in (t.split("x") for t in s.split("."))}


def e_b(p: dict) -> int:
    return sum(d * c for d, c in p.items())


def enumerate_profiles(kb: int, degs, max_distinct: int = 3):
    out = []
    for r in range(1, max_distinct + 1):
        for ds in itertools.combinations(degs, r):
            # compositions of kb into r positive parts
            for cuts in itertools.combinations(range(1, kb), r - 1):
                parts = [b - a for a, b in zip((0,) + cuts, cuts + (kb,))]
                out.append(dict(zip(ds, parts)))
    return out


def _ga_chunk(args):
    profs, mb, tol, max_iter = args
    return de.ga_threshold(profs, mb, tol=tol, max_iter=max_iter).tolist()


def ga_many(profs, mb, workers, tol=0.005, max_iter=800, chunk=3000):
    if len(profs) <= chunk:
        return _ga_chunk((profs, mb, tol, max_iter))
    jobs = [(profs[i:i + chunk], mb, tol, max_iter) for i in range(0, len(profs), chunk)]
    with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn")) as ex:
        return [x for r in ex.map(_ga_chunk, jobs) for x in r]


def local_search(p: dict, kb: int, mb: int, degs, same_eb: bool, steps: int = 12, tol=0.002):
    """Hill-climb over 'move one block column from degree d to d2' (up to 4 distinct degrees).
    same_eb: only moves that keep E_b (pairs of moves), else any move."""
    cur, cur_t = dict(p), float(de.ga_threshold([p], mb, tol=tol, max_iter=2000)[0])
    for _ in range(steps):
        nb = []
        if same_eb:
            src = [d for d, c in cur.items() for _ in range(min(c, 2))]
            for d1, d2 in set(itertools.combinations(sorted(src), 2)):
                for d3 in degs:
                    d4 = d1 + d2 - d3
                    if d4 not in degs or sorted((d3, d4)) == sorted((d1, d2)):
                        continue
                    q = dict(cur); q[d1] -= 1; q[d2] -= 1
                    q[d3] = q.get(d3, 0) + 1; q[d4] = q.get(d4, 0) + 1
                    q = {d: c for d, c in q.items() if c > 0}
                    if len(q) <= 4:
                        nb.append(q)
        else:
            for d1 in cur:
                for d3 in degs:
                    if d3 == d1:
                        continue
                    q = dict(cur); q[d1] -= 1; q[d3] = q.get(d3, 0) + 1
                    q = {d: c for d, c in q.items() if c > 0}
                    if len(q) <= 4:
                        nb.append(q)
        uniq = {spell(q): q for q in nb}
        if not uniq:
            break
        qs = list(uniq.values())
        th = de.ga_threshold(qs, mb, tol=tol, max_iter=2000)
        i = int(np.argmin(th))
        if th[i] < cur_t - 1e-4:
            cur, cur_t = qs[i], float(th[i])
        else:
            break
    return cur, cur_t


def recipe_profile(k: int, heavy_deg=10, heavy_frac=0.3, light=3) -> dict:
    kb = k // Z
    nh = round(heavy_frac * kb)
    return {heavy_deg: nh, light: kb - nh} if nh and nh < kb else {light if nh == 0 else heavy_deg: kb}


def _ls_job(args):
    p, kb, mb, degs = args
    return local_search(p, kb, mb, degs, same_eb=True)


def de_table(k: int, degs, workers: int, max_distinct: int = 3, ls_levels: int = 40) -> dict:
    """GA over every profile; best per E_b; 4-degree local search per E_b level. Cached per k."""
    kb, mb = k // Z, (N - k) // Z
    t = time.time()
    profs = enumerate_profiles(kb, degs, max_distinct)
    th = ga_many(profs, mb, workers)
    best_eb: dict[int, tuple] = {}
    for p, x in zip(profs, th):
        eb = e_b(p)
        if eb not in best_eb or x < best_eb[eb][1]:
            best_eb[eb] = (p, x)
    best_eb4: dict[int, tuple] = {}
    for p, x in zip(profs, th):
        if min(p) >= 4:
            eb = e_b(p)
            if eb not in best_eb4 or x < best_eb4[eb][1]:
                best_eb4[eb] = (p, x)
    # refine the per-E_b winners at fine tolerance and add a 4-degree local search at fixed E_b
    levels = sorted(best_eb)
    fine = de.ga_threshold([best_eb[e][0] for e in levels], mb, tol=0.001, max_iter=4000)
    per_eb = {}
    for e, x in zip(levels, fine):
        per_eb[e] = {"profile": spell(best_eb[e][0]), "ga": float(x)}
    order = sorted(levels, key=lambda e: per_eb[e]["ga"])
    lv = order[:ls_levels]                        # the best levels get the 4-degree search (parallel)
    with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn")) as ex:
        lsr = list(ex.map(_ls_job, [(best_eb[e][0], kb, mb, tuple(degs)) for e in lv]))
    for e, (q, x) in zip(lv, lsr):
        if x < per_eb[e]["ga"] - 1e-4:
            per_eb[e]["ls4"] = {"profile": spell(q), "ga": x}
    # per-dmax and per-min-degree optima (<=3 distinct), for the variants
    by_dmax, by_dmin = {}, {}
    for p, x in zip(profs, th):
        dm, dn = max(p), min(p)
        if dm not in by_dmax or x < by_dmax[dm][1]:
            by_dmax[dm] = (spell(p), x)
        if dn not in by_dmin or x < by_dmin[dn][1]:
            by_dmin[dn] = (spell(p), x)
    ref = {"recipe_h10_f0.3_l3": recipe_profile(k)}
    for hd, hf in ((8, 0.5), (10, 0.5), (12, 0.5), (12, 0.3)):
        ref[f"tierA_h{hd}_f{hf}_l3"] = recipe_profile(k, hd, hf, 3)
    ref["tierA_h12_f0.3_l4"] = recipe_profile(k, 12, 0.3, 4)
    rth = de.ga_threshold(list(ref.values()), mb, tol=0.001, max_iter=4000)
    return {"k": k, "kb": kb, "mb": mb, "degs": list(degs), "max_distinct": max_distinct, "n_profiles": len(profs),
            "seconds": round(time.time() - t, 1),
            "shannon_db": common.ch.biawgn_shannon_esn0_db(k / N),
            "per_eb": {str(e): v for e, v in per_eb.items()},
            "per_eb_m4": {str(e): {"profile": spell(p), "ga": float(x)} for e, (p, x) in sorted(best_eb4.items())},
            "by_dmax": {str(d): {"profile": s, "ga": x} for d, (s, x) in sorted(by_dmax.items())},
            "by_dmin": {str(d): {"profile": s, "ga": x} for d, (s, x) in sorted(by_dmin.items())},
            "refs": {n: {"profile": spell(p), "ga": float(x), "E_b": e_b(p)} for (n, p), x in zip(ref.items(), rth)}}


def select(tab: dict, n_cand: int, a_step: float, n_ladder4: int = 0, a_step4: float = 0.3) -> list[dict]:
    """Candidates across a-levels: the global GA optimum (+ its 4-degree local-search variant when that
    is >= 0.02 dB better), then the per-E_b optimum on a SYMMETRIC a-ladder (+-1, +-2, ... steps of
    a_step; Tier A's finite-length winners sit BELOW the GA-optimal a at k=1664 and ABOVE it at k=1280),
    then the variants: dmax <= 10, min degree 4 (and dmax <= 12 when n_cand >= 10).  n_ladder4 > 0
    replaces the single min-degree-4 variant by a ladder of per-E_b optima with every info degree >= 4
    (the k=1216 trial winner, 0 undetected, min w2 ~40), a_step4 apart around their own optimum."""
    mb = tab["mb"]
    per = {int(e): v for e, v in tab["per_eb"].items()}
    best_e = min(per, key=lambda e: per[e]["ga"])
    out, seen = [], set()

    def add(why, prof, ga):
        if prof in seen or len(out) >= n_cand:
            return
        seen.add(prof)
        p = unspell(prof)
        out.append({"why": why, "profile": prof, "E_b": e_b(p), "a": round(e_b(p) / mb, 3), "ga": ga})

    variants = []
    dm = {int(d): v for d, v in tab["by_dmax"].items()}
    dn = {int(d): v for d, v in tab["by_dmin"].items()}
    if any(d <= 10 for d in dm):
        variants.append(("best with dmax<=10", min((v for d, v in dm.items() if d <= 10), key=lambda v: v["ga"])))
    if any(d >= 4 for d in dn) and not n_ladder4:
        variants.append(("best with min degree 4", min((v for d, v in dn.items() if d >= 4), key=lambda v: v["ga"])))
    if n_cand >= 10 and any(d <= 12 for d in dm):
        variants.append(("best with dmax<=12", min((v for d, v in dm.items() if d <= 12), key=lambda v: v["ga"])))
    n_ladder = max(1, n_cand - len(variants) - n_ladder4)
    add("GA optimum", per[best_e]["profile"], per[best_e]["ga"])
    if "ls4" in per[best_e] and per[best_e]["ls4"]["ga"] < per[best_e]["ga"] - 0.02:
        add("GA optimum, 4 degrees", per[best_e]["ls4"]["profile"], per[best_e]["ls4"]["ga"])
    for o in itertools.chain.from_iterable((i, -i) for i in range(1, 40)):
        if len(out) >= n_ladder:
            break
        e = best_e + round(o * a_step * mb)
        cands = [x for x in per if abs(x - e) <= max(1, round(0.05 * mb))]
        if not cands:
            continue
        e2 = min(cands, key=lambda x: per[x]["ga"])
        v = per[e2]["ls4"] if "ls4" in per[e2] and per[e2]["ls4"]["ga"] < per[e2]["ga"] - 0.02 else per[e2]
        add(f"best at a={e2 / mb:.2f} ({'+' if o > 0 else ''}{o * a_step:.2f})", v["profile"], v["ga"])
    per4 = {int(e): v for e, v in tab.get("per_eb_m4", {}).items()}
    if n_ladder4 and per4:
        b4 = min(per4, key=lambda e: per4[e]["ga"])
        stop = len(out) + n_ladder4
        add(f"min-degree-4 optimum a={b4 / mb:.2f}", per4[b4]["profile"], per4[b4]["ga"])
        for o in itertools.chain.from_iterable((i, -i) for i in range(1, 40)):
            if len(out) >= stop:
                break
            e = b4 + round(o * a_step4 * mb)
            cands = [x for x in per4 if abs(x - e) <= max(1, round(0.05 * mb))]
            if cands:
                e2 = min(cands, key=lambda x: per4[x]["ga"])
                add(f"min-degree-4 at a={e2 / mb:.2f} ({'+' if o > 0 else ''}{o * a_step4:.2f})",
                    per4[e2]["profile"], per4[e2]["ga"])
    for why, v in variants:
        add(why, v["profile"], v["ga"])
    for e in sorted(per, key=lambda e: per[e]["ga"]):          # fill from the next-best levels
        if len(out) >= n_cand:
            break
        add(f"next per-E_b optimum a={e / mb:.2f}", per[e]["profile"], per[e]["ga"])
    return out


def _mc_job(args):
    prof, mb, start, ns = args
    t = time.process_time()
    x = de.mc_threshold(unspell(prof), mb, start, ns=ns, max_iter=300, tol=0.01, span=0.3)
    return prof, x, time.process_time() - t


def mc_many(items, workers, ns):
    with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn")) as ex:
        return list(ex.map(_mc_job, [(p, mb, s, ns) for p, mb, s in items]))


# ------------------------------------------------------------------ search configs
def b1_cfg(k: int, prof: str, seed: int, *, gap_min=24, slack=1) -> common.Cfg:
    p = unspell(prof)
    degs = tuple(d for d, c in sorted(p.items(), reverse=True) for _ in range(c))   # heavy first, as the recipe
    tag = f"k{k}-{TIER}-{prof}-bal-g{gap_min}-d{slack}"
    return common.Cfg(k=k, degs=degs, tag=tag, seed=seed, gap_min=gap_min, slack=slack, placement="balanced")


MODES = {
    "smoke": dict(ls_levels=3, n_cand=2, seeds=1, a_step=0.4, mc_ns=20_000,
                  settings=common.Settings(s1_trials=20, walk_trials=20, fine_trials=40, side_trials=20,
                                           n_finalists=1, n_fine=1, seedvar_configs=0)),
    "trial": dict(ls_levels=40, n_cand=7, seeds=4, a_step=0.3, mc_ns=50_000,
                  settings=common.Settings(s1_trials=100, walk_trials=100, fine_trials=500, side_trials=100,
                                           n_finalists=2, n_fine=2, seedvar_configs=1)),
    "overnight": dict(ls_levels=80, n_cand=20, n_ladder4=6, a_step4=0.25, seeds=8, a_step=0.15, mc_ns=50_000,
                      settings=common.Settings(s1_trials=100, walk_trials=200, fine_trials=500, side_trials=200,
                                               n_finalists=16, n_fine=4, seedvar_configs=2)),
}


def de_candidates(out: Path, ks, mode: str, workers: int, degs, max_distinct: int) -> dict:
    """DE tables + candidates + MC re-score, cached in <out>/de-candidates.json (resume-stable names)."""
    path = out / "de-candidates.json"
    if path.exists():
        cached = json.loads(path.read_text())
        if all(str(k) in cached["k"] for k in ks):
            want = {"mode": mode, "degs": list(degs), "max_distinct": max_distinct}
            have = {x: cached.get(x) for x in want}
            ncand = {k: len(cached["k"][str(k)]["candidates"]) for k in ks}
            if have != want or any(n != MODES[mode]["n_cand"] for n in ncand.values()):
                print(f"[DE] WARNING: reusing {path} made with {have}, candidates {ncand}; this run asked "
                      f"{want}, n_cand {MODES[mode]['n_cand']} — delete the file to recompute (names change)",
                      file=sys.stderr, flush=True)
            return cached
    M = MODES[mode]
    res = {"mode": mode, "degs": list(degs), "max_distinct": max_distinct, "k": {}}
    for k in ks:
        tab = de_table(k, degs, workers, max_distinct, M["ls_levels"])
        cands = select(tab, M["n_cand"], M["a_step"], M.get("n_ladder4", 0), M.get("a_step4", 0.3))
        print(f"[DE] k={k}: {tab['n_profiles']} profiles in {tab['seconds']} s; Shannon {tab['shannon_db']:.3f} dB; "
              f"candidates {[(c['profile'], round(c['ga'], 3)) for c in cands]}", file=sys.stderr, flush=True)
        res["k"][str(k)] = {"table": tab, "candidates": cands}
    items = []
    for k in ks:
        r = res["k"][str(k)]
        mb = r["table"]["mb"]
        for c in r["candidates"]:
            items.append((c["profile"], mb, c["ga"]))
        for v in r["table"]["refs"].values():
            items.append((v["profile"], mb, v["ga"]))
    t = time.time()
    mc = mc_many(items, workers, M["mc_ns"])
    print(f"[DE] MC-DE re-score of {len(items)} profiles in {time.time() - t:.0f} s", file=sys.stderr, flush=True)
    i = 0
    for k in ks:
        r = res["k"][str(k)]
        for c in r["candidates"] + list(r["table"]["refs"].values()):
            c["mc"] = mc[i][1]; c["mc_ns"] = M["mc_ns"]; i += 1
    out.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(res, indent=1) + "\n")
    return res


# ------------------------------------------------------------------ summary (DE section)
def _sp(a, b):
    from scipy.stats import spearmanr
    if len(a) < 3:
        return None
    return float(spearmanr(np.asarray(a, float), np.asarray(b, float))[0])


def de_section(run_dir: Path, de_dirs) -> list[str]:
    """GA threshold of every built code in run_dir (its ACTUAL check info-degree histogram) vs its
    screen-1 score and walk 10 % point; the B1 candidate table from each de-candidates.json."""
    done, _ = common.load(run_dir)
    L = ["## Tier B1 — density evolution vs measurement", "",
         "GA = Gaussian-approximation DE threshold (Es/N0 dB, BIAWGN, infinite length) of the code's info-degree "
         "profile with its ACTUAL built check info-degree histogram; MC = population-dynamics DE (exact BP "
         "check rule) of the balanced profile. Spearman ρ over codes of the run (Tier A codes included when merged): "
         "GA vs screen-1 score and GA vs walk Es/N0@10 % (lower = better on every axis, so ρ > 0 = DE ordering "
         "survives).", ""]
    # plain e-IRA codes only: a B2 variant's mother graph (punctured / doubly accumulated) is not the
    # GA model's structure (prep review 2026-09-30: merged runs fed them into the "all" correlation)
    s0 = {rid: r for (rid, s), r in done.items() if s == "s0" and r.get("struct") and "variant" not in r
          and "variant" not in r.get("cfg", {})}
    ks = sorted({r["k"] for r in s0.values()}, reverse=True)
    ga_of = {}
    for k in ks:
        mb = (N - k) // Z
        recs = [r for r in s0.values() if r["k"] == k]
        profs = [dict(Counter(r["cfg"]["degs"])) for r in recs]
        hists = [{int(d) - 2: c for d, c in r["struct"]["chk_deg_hist"].items()} for r in recs]
        th = de.ga_threshold(profs, mb, hists, tol=0.002, max_iter=2000)
        for r, x in zip(recs, th):
            ga_of[r["rid"]] = float(x)
        for tier, pred in (("all", lambda r: True), ("non-B1 (Tier A + baseline)", lambda r: f"-{TIER}-" not in r["tag"]),
                           ("B1", lambda r: f"-{TIER}-" in r["tag"])):
            rr = [r for r in recs if pred(r) and (r["rid"], "s1") in done]
            ww = [r for r in recs if pred(r) and (r["rid"], "s2walk") in done and done[(r["rid"], "s2walk")]["es10"] is not None]
            if not rr:
                continue
            a = _sp([ga_of[r["rid"]] for r in rr], [done[(r["rid"], "s1")]["score"] for r in rr])
            b = _sp([ga_of[r["rid"]] for r in ww], [done[(r["rid"], "s2walk")]["es10"] for r in ww])
            L.append(f"- k={k} {tier}: ρ(GA, s1 score) = {common._f(a, 2)} over {len(rr)} codes; "
                     f"ρ(GA, walk Es/N0@10 %) = {common._f(b, 2)} over {len(ww)} walked codes.")
    L.append("")
    for dd in de_dirs:
        p = Path(dd) / "de-candidates.json"
        if not p.exists():
            continue
        dc = json.loads(p.read_text())
        for ks_, r in sorted(dc["k"].items(), key=lambda kv: -int(kv[0])):
            k = int(ks_); tab = r["table"]; mb = tab["mb"]
            L += [f"### k = {k}: DE candidates ({Path(dd).name}; {tab['n_profiles']} profiles with ≤{tab['max_distinct']} "
                  f"distinct degrees in {tab['degs'][0]}..{tab['degs'][-1]}; Shannon {tab['shannon_db']:.3f} dB)", "",
                  "| profile (deg x block cols) | why | E_b | a = E_b/mb | GA dB | MC dB | GA − Shannon | seeds: s1 score | "
                  "mean s1 | walk Es/N0@10 % | Es/N0@1 % (fine where run) | p@1 % | undet |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            rows = [(c, "cand") for c in r["candidates"]] + [({**v, "why": n}, "ref") for n, v in tab["refs"].items()]
            for c, kind in rows:
                prof = c["profile"]
                tag = f"k{k}-{TIER}-{prof}-bal-g24-d1"
                codes = sorted([x for x in s0.values() if x["tag"] == tag], key=lambda x: x["seed"]) if kind == "cand" else []
                if kind == "ref":
                    # the Tier A config with this profile (balanced) if the run has it
                    codes = sorted([x for x in s0.values() if x["k"] == k and f"-{TIER}-" not in x["tag"]
                                    and x["cfg"]["placement"] == "balanced" and not x.get("baseline")
                                    and spell(dict(Counter(x["cfg"]["degs"]))) == prof], key=lambda x: x["seed"])
                s1s = [done[(x["rid"], "s1")]["score"] for x in codes if (x["rid"], "s1") in done]
                wk = [done[(x["rid"], "s2walk")] for x in codes if (x["rid"], "s2walk") in done]
                bf = [done.get((w["rid"], "s2fine")) or w for w in wk]
                und = sum(common.undetected(done, x["rid"])[0] for x in codes)
                L.append(f"| {prof} | {c['why']} | {e_b(unspell(prof))} | {e_b(unspell(prof)) / mb:.2f} | {c['ga']:.3f} | "
                         f"{common._f(c.get('mc'))} | {c['ga'] - tab['shannon_db']:.2f} | "
                         f"{', '.join(f'{s:.2f}' for s in s1s) or '—'} | {common._f(statistics.mean(s1s) if s1s else None, 2)} | "
                         f"{', '.join(common._f(w['es10']) for w in wk) or '—'} | {', '.join(common._f(b['es1']) for b in bf) or '—'} | "
                         f"{', '.join(common._f(b['p1'], 4) for b in bf) or '—'} | {und if codes else '—'} |")
            L.append("")
            # the GA landscape over E_b
            per = sorted(((int(e), v) for e, v in tab["per_eb"].items()), key=lambda t: t[0])
            best = min(v["ga"] for _, v in per)
            L.append("GA optimum per total info-edge level within 0.15 dB of the best (a = E_b/mb): " + "; ".join(
                f"a={e / mb:.2f} {v['ga']:.3f}" + (f" (4-deg {v['ls4']['ga']:.3f})" if 'ls4' in v else "")
                for e, v in per if v["ga"] < best + 0.15) + "  ")
            L.append("GA optimum per max degree: " + "; ".join(f"≤{d}: {v['ga']:.3f} ({v['profile']})"
                                                             for d, v in tab["by_dmax"].items()) + "")
            L.append("")
    return L


def summarize(out: Path, merge=(), merged_out: Path | None = None) -> Path:
    run = out
    if merge:
        run = merged_out or out.parent / (out.name + "+merged")
        common.merge_runs([Path(m) for m in merge] + [out], run)
    p = common.summarize(run)
    L = de_section(run, [out] + [Path(m) for m in merge])
    p.write_text(p.read_text() + "\n" + "\n".join(L) + "\n")
    return p


# ------------------------------------------------------------------ main
def main(argv=None):
    common.term_as_interrupt()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m = ap.add_mutually_exclusive_group()
    m.add_argument("--smoke", action="store_true")
    m.add_argument("--trial", action="store_true")
    m.add_argument("--overnight", action="store_true")
    ap.add_argument("--de-only", action="store_true", help="DE tables + candidates of the chosen mode only (no decoding)")
    ap.add_argument("--secondary", action="store_true", help="add k=1600 and k=1216")
    ap.add_argument("--ks", default=None, help="explicit k list, e.g. 1664,1280")
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--candidates", type=int, default=None, help="DE candidates per k")
    ap.add_argument("--finalists", type=int, default=None)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--dmax", type=int, default=16, help="max info degree (rule (b) budget fails above ~16)")
    ap.add_argument("--allow-d2", action="store_true", help="admit degree-2 info columns in the DE search")
    ap.add_argument("--max-distinct", type=int, default=None, help="distinct degrees in the enumeration (default 3; smoke 2)")
    ap.add_argument("--min-w2", type=int, default=None, help="screen-1 floor on min(w1, w2) (10; 16 for --overnight)")
    ap.add_argument("--min-w2-final", type=int, default=None,
                    help="stricter min w1/w2 floor for FINALIST selection only (screen 1 still sees --min-w2)")
    ap.add_argument("--s1-anchor", default="trial-A",
                    help="'frozen' or a run DIR (default trial-A = the SAME anchor as Tier A's trial-A2 and overnight "
                         "runs, so screen-1 scores rank together)")
    ap.add_argument("--decoder", default="fast", choices=("fast", "prod"),
                    help="fast = fast/fastdecode batched bit-exact twin (default; start-up selfcheck, falls back "
                         "to prod on failure), prod = holo.core.ldpc.decode one trial at a time")
    ap.add_argument("--no-baselines", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--summarize-only", action="store_true")
    ap.add_argument("--merge", action="append", default=[], help="run DIR(s) to rank together with --out")
    ap.add_argument("--merged-out", default=None)
    a = ap.parse_args(argv)
    mode = "smoke" if a.smoke else "overnight" if a.overnight else "trial"
    out = Path(a.out) if a.out else common.SEARCH / f"{mode}-{TIER}"
    if a.summarize_only:
        print(summarize(out, a.merge, Path(a.merged_out) if a.merged_out else None))
        return
    ks = tuple(int(x) for x in a.ks.split(",")) if a.ks else (1664, 1280) + ((1600, 1216) if a.secondary else ())
    degs = tuple(range(2 if a.allow_d2 else 3, a.dmax + 1))
    M = dict(MODES[mode])
    if a.candidates is not None:
        M["n_cand"] = a.candidates
    MODES[mode] = M
    out.mkdir(parents=True, exist_ok=True)
    maxd = a.max_distinct or (2 if mode == "smoke" else 3)
    dc = de_candidates(out, ks, mode, a.workers, degs, maxd)
    if a.de_only:
        for k in ks:
            r = dc["k"][str(k)]
            print(f"k={k} Shannon {r['table']['shannon_db']:.3f}")
            for c in r["candidates"] + [{**v, "why": n} for n, v in r["table"]["refs"].items()]:
                print(f"  {c['profile']:>24} a={e_b(unspell(c['profile'])) / r['table']['mb']:.2f} "
                      f"GA {c['ga']:.3f} MC {common._f(c.get('mc'))}  {c['why']}")
        return
    S = M["settings"]
    S.workers, S.ks = a.workers, ks
    S.min_w2 = a.min_w2 if a.min_w2 is not None else (16 if mode == "overnight" else 10)
    S.min_w2_final = a.min_w2_final
    if a.finalists is not None:
        S.n_finalists = a.finalists
    if a.s1_anchor != "frozen":
        d = Path(a.s1_anchor) if Path(a.s1_anchor).is_absolute() else common.SEARCH / a.s1_anchor
        S.s1_anchor = common.anchor_from(d, ks) if (d / "results.jsonl").exists() else {}
        print(f"screen-1 anchor from {d}: {S.s1_anchor}", file=sys.stderr)
    for k in ks:
        if not common.verify_baseline(k):
            sys.exit(f"generalized draw does NOT reproduce the frozen recipe at k={k} — refusing to run")
    S.decoder = common.select_decoder(a.decoder, [common.baseline_cfg(ks[0]).name])
    seeds = a.seeds if a.seeds is not None else M["seeds"]
    cfgs = [] if a.no_baselines else [common.baseline_cfg(k) for k in ks]
    for k in ks:
        for c in dc["k"][str(k)]["candidates"]:
            cfgs += [b1_cfg(k, c["profile"], s) for s in range(seeds)]
    print(f"mode {mode}: {len(cfgs)} configs over k={ks}, workers {S.workers}, out {out}", file=sys.stderr, flush=True)
    srch = common.Search(cfgs, S, out, f"{mode}-{TIER}")
    finished = srch.run()
    p = summarize(out)
    print(f"{'finished' if finished else 'STOPPED (rerun resumes)'}; errors {srch.errors}; summary -> {p}",
          file=sys.stderr)
    common.exit_status(finished, srch.errors)


if __name__ == "__main__":
    main()
