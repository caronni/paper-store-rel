"""Overnight sizing (prep 2026-09-30): decodes per stage from the grids (after the seed-0 infeasibility
skip) and the per-code decode counts of the protocol, CPU from the MEASURED fast-decoder cost per
decode per screen (chk/calib-fast: trial grid seed 0, k=1664/1280, 14 workers, 81,100 decodes, pool
utilisation 0.96), wall = CPU / (workers x util).  No decoding.

  PYTHONPATH=src:. env/bin/python $S/sizing.py [--util 0.85] [--seeds N] [--frozen-seeds N] [--finalists N] ...
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import recipe_search as RS  # noqa: E402
import de_profile as DP  # noqa: E402
import variants_search as VS  # noqa: E402

MS = {"s1": 29.4, "walk": 19.1, "fine": 13.3, "side": 24.9, "conf": 13.3}   # fast, ms CPU / decode (calib-fast)
B2_SLOW = 1.15          # mother-graph decodes (trial-B2 vs trial-A2, production decoder): +10-15 %
ELIG = {1664: 54 / 71, 1280: 62 / 72, 1600: 0.72, 1216: 0.9}   # share with min(w1, w2) >= 16 (trial-A2 / scan)
FROZEN_ELIG = 0.88      # seed-0 scan: share of built codes at or above the incumbent floor


def per_code(a):
    return {"s1": 4 * a.s1_trials, "walk": 12.5 * a.walk_trials, "fine": 2600 * a.fine_trials / 500,
            "side": 6 * a.side_trials}


def cpu_h(dec: dict) -> float:
    return sum(dec[s] * MS[s] for s in dec) / 1000 / 3600


def tier_a(a, ks, skip, seeds, nfin_main, nfine):
    pc = per_code(a)
    out = []
    for k in ks:
        fz = k in common.FROZEN_RUNGS
        cf = [c for c in RS.grid("overnight", (k,), seeds, a.frozen_seeds) if RS.cfg_key(c) not in skip]
        nb = len(common.baseline_cfgs(k))
        seeds_k = a.frozen_seeds if fz else seeds
        nfin = a.frozen_finalists if fz else nfin_main
        walked = nfin + 2 * seeds_k + nb
        el = FROZEN_ELIG if fz else ELIG[k]
        dec = {"s1": len(cf) * el * pc["s1"], "walk": walked * pc["walk"], "fine": ((4 if fz else nfine) + nb) * pc["fine"],
               "side": (nfin + nb) * pc["side"]}
        out.append((k, len(cf), walked, dec))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=14)
    ap.add_argument("--util", type=float, default=0.85)
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--secondary-seeds", type=int, default=8)
    ap.add_argument("--secondary-finalists", type=int, default=16)
    ap.add_argument("--n-fine", type=int, default=4)
    ap.add_argument("--confirm-hard", type=int, default=2)
    ap.add_argument("--frozen-seeds", type=int, default=4)
    ap.add_argument("--finalists", type=int, default=16)
    ap.add_argument("--frozen-finalists", type=int, default=16)
    ap.add_argument("--s1-trials", type=int, default=100)
    ap.add_argument("--walk-trials", type=int, default=200)
    ap.add_argument("--fine-trials", type=int, default=500)
    ap.add_argument("--side-trials", type=int, default=200)
    ap.add_argument("--b1-seeds", type=int, default=8)
    ap.add_argument("--b2-seeds", type=int, default=8)
    ap.add_argument("--confirm-trials", type=int, default=2000)
    ap.add_argument("--confirm-top", type=int, default=8)
    a = ap.parse_args()
    skip = RS.load_infeasible(sorted(str(x.name) for x in common.SEARCH.glob("feasibility-*.json")))
    pc = per_code(a)
    rate = a.workers * a.util
    rows = []
    for name, ks, sd, nf, nfi in (("A-primary", (1664, 1280), a.seeds, a.finalists, a.n_fine),
                                  ("A-frozen", tuple(common.FROZEN_RUNGS), a.frozen_seeds, a.frozen_finalists, 4),
                                  ("A-secondary", (1600, 1216), a.secondary_seeds, a.secondary_finalists, 4)):
        r = tier_a(a, ks, skip, sd, nf, nfi)
        dec = {s: sum(x[3][s] for x in r) for s in pc}
        rows.append((name, sum(x[1] for x in r), sum(x[2] for x in r), dec, ", ".join(f"{x[0]}:{x[1]}" for x in r)))
    M = DP.MODES["overnight"]; S = M["settings"]
    n = 4 * (M["n_cand"] * a.b1_seeds + 1); wk = 4 * (S.n_finalists + 2 * a.b1_seeds + 1)
    rows.append(("B1", n, wk, {"s1": n * 0.8 * pc["s1"], "walk": wk * pc["walk"], "fine": 4 * 5 * pc["fine"],
                               "side": 4 * (S.n_finalists + 1) * pc["side"]}, "+ DE tables"))
    S = VS.SETTINGS["overnight"]
    n = 4 * 4 * a.b2_seeds * len(VS.VARIANT_GRID["overnight"]); wk = 4 * (2 * S.n_finalists + 3 + 2 * a.b2_seeds)
    rows.append(("B2", n, wk, {s: v * B2_SLOW for s, v in {"s1": n * 0.8 * pc["s1"], "walk": wk * pc["walk"],
                                                        "fine": wk * pc["fine"], "side": wk * pc["side"]}.items()},
                 "variants only (plain rows copied from overnight-A)"))
    nconf = 9 * (a.confirm_top + a.confirm_hard) + 6
    rows.append(("confirm", nconf, nconf, {"conf": nconf * 8 * a.confirm_trials}, f"~8 grid points x {a.confirm_trials}"))
    tot_c = tot_w = 0
    print(f"| stage | codes | walked | decodes (M) | CPU h | wall h (14 x {a.util}) | notes |\n|---|---|---|---|---|---|---|")
    for name, n, wk, dec, note in rows:
        c = cpu_h(dec); w = c / rate
        tot_c += c; tot_w += w
        print(f"| {name} | {n} | {wk} | {sum(dec.values()) / 1e6:.2f} | {c:.1f} | {w:.2f} | {note} |")
    print(f"| TOTAL | | | | {tot_c:.1f} | {tot_w:.2f} | +20 % margin -> {tot_w * 1.2:.2f} h |")
