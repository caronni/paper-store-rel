# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/recipe_search.py
"""Tier A driver: the recipe space (k x heavy_deg x heavy_frac x light_deg x placement x seed)
through the three screens of common.Search, plus the frozen-recipe baselines as named rows.

  cd <repo>
  PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/recipe_search.py --smoke
  PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/recipe_search.py --trial --workers 13
  nohup env PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/recipe_search.py \
      --overnight --workers 14 > measure/rung-ladder/search/overnight-A.log 2>&1 &
  PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/recipe_search.py --summarize-only --out DIR

Resume is the default: a rerun with the same --out skips every (code, screen) line already in
results.jsonl (Ctrl-C / SIGTERM stop cleanly; finished lines are fsync'd).
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

GRID = {
    "overnight": dict(heavy_deg=(6, 8, 10, 12, 14, 16), heavy_frac=(0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8),
                      light=(3, 4), placement=("uniform", "balanced"), seeds=8),
    "trial": dict(heavy_deg=(8, 10, 12), heavy_frac=(0.3, 0.5, 0.7), light=(3, 4),
                  placement=("uniform", "balanced"), seeds=2),
}
# FROZEN RUNGS as full rows (owner's ruling 2026-09-30): the reduced sweep at k in common.FROZEN_RUNGS.
# heavy_deg <= mb - 3 (rule-(d)/(b) feasibility: r0850 mb=9 -> <= 6, r0775 mb=14 -> <= 11) is applied
# BEFORE building; where fewer than the six standard degrees survive, the six (or fewer) largest
# feasible integers >= 4 are swept instead (k=3200: 6..11, k=3520: 4..6).  light 3 only (trial:
# light 4 no help on average); heavy_frac 0.7/0.8 dropped (0.7 bad everywhere in the trials).
FROZEN_GRID = dict(heavy_frac=(0.2, 0.3, 0.4, 0.5, 0.6), light=(3,), placement=("uniform", "balanced"), seeds=4)
STD_HEAVY = (6, 8, 10, 12, 14, 16)


def frozen_heavy(k: int) -> tuple:
    hmax = (common.N - k) // common.Z - 3
    std = tuple(h for h in STD_HEAVY if h <= hmax)
    return std if len(std) == len(STD_HEAVY) else tuple(range(max(4, hmax - 5), hmax + 1))


def feasible_heavy(k: int, hd: int) -> bool:
    return hd <= (common.N - k) // common.Z - 3


SETTINGS = {
    "smoke": common.Settings(s1_trials=20, walk_trials=20, fine_trials=40, side_trials=20, n_finalists=1,
                             n_fine=1, seedvar_configs=0),
    "trial": common.Settings(s1_trials=100, walk_trials=100, fine_trials=500, side_trials=100, n_finalists=6,
                             n_fine=4, seedvar_configs=2),
    "overnight": common.Settings(s1_trials=100, walk_trials=200, fine_trials=500, side_trials=200,
                                 n_finalists=16, n_fine=4, seedvar_configs=2),
}


SMOKE_FROZEN = {2880: (10, 0.3, 3, "balanced"), 3520: (6, 0.3, 3, "balanced")}


def grid(mode: str, ks, seeds: int | None, frozen_seeds: int | None = None) -> list[common.Cfg]:
    """The search configs (no baselines).  Frozen-rung k get FROZEN_GRID; every combo whose heavy
    degree is infeasible at its k is dropped here, before anything is built."""
    out = []
    if mode == "smoke":
        out = [c for c in (common.recipe_cfg(1664, 10, 0.3, 3, "balanced", 0),
                           common.recipe_cfg(1280, 10, 0.5, 4, "uniform", 0),
                           common.recipe_cfg(1600, 12, 0.3, 3, "balanced", 0),
                           common.recipe_cfg(1216, 10, 0.5, 3, "balanced", 0)) if c.k in ks]
        return out + [common.recipe_cfg(k, *SMOKE_FROZEN[k], 0) for k in ks if k in SMOKE_FROZEN]
    for k in ks:
        if k in common.FROZEN_RUNGS:
            g, hds = FROZEN_GRID, frozen_heavy(k)
            S = frozen_seeds if frozen_seeds is not None else g["seeds"]
        else:
            g = GRID[mode]
            hds = g["heavy_deg"]
            S = seeds if seeds is not None else g["seeds"]
        for hd, hf, lt, pl, s in itertools.product(hds, g["heavy_frac"], g["light"], g["placement"], range(S)):
            if feasible_heavy(k, hd):
                out.append(common.recipe_cfg(k, hd, hf, lt, pl, s))
    return out


def load_infeasible(paths) -> set:
    """(k, heavy_deg, heavy_frac, light, placement) whose SEED-0 build failed (build_timeout /
    restarts_exhausted) in a feasibility scan (feasibility.py output): every seed of such a config
    is skipped up front instead of burning the 120 s build cap per seed."""
    bad = set()
    for p in paths:
        pp = Path(p) if Path(p).is_absolute() else common.SEARCH / p
        if not pp.exists():
            print(f"[infeasible] {pp} missing (nothing skipped from it)", file=sys.stderr)
            continue
        for key, verdict, *_ in json.loads(pp.read_text()):
            if verdict != "ok":
                k, hd, hf, lt, pl = key
                bad.add((int(k), int(hd), round(float(hf), 3), int(lt), pl))
    return bad


def cfg_key(c: common.Cfg) -> tuple:
    m = dict(c.meta)
    return (c.k, int(m["heavy_deg"]), round(float(m["heavy_frac"]), 3), int(m["light"]), c.placement)


def main(argv=None):
    common.term_as_interrupt()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m = ap.add_mutually_exclusive_group()
    m.add_argument("--smoke", action="store_true", help="2 configs + baselines, 20 trials everywhere")
    m.add_argument("--trial", action="store_true", help="h{8,10,12} x f{.3,.5,.7} x l{3,4} x both x 2 seeds")
    m.add_argument("--overnight", action="store_true", help="the full grid, N=16, 200/500 trials")
    ap.add_argument("--secondary", action="store_true", help="add k=1600 and k=1216")
    ap.add_argument("--primary", default="on", choices=("on", "off"),
                    help="include the primary k=1664, 1280 (off: e.g. a frozen-rungs-only run)")
    ap.add_argument("--frozen-rungs", default=None, choices=("on", "off"),
                    help="add k in {2240, 2560, 2880, 3200, 3520} with the six frozen production codes as named "
                         "baseline rows and the reduced FROZEN_GRID sweep (default: on for --overnight, off otherwise)")
    ap.add_argument("--frozen-seeds", type=int, default=None, help="override seeds per frozen-rung config (default 4)")
    ap.add_argument("--frozen-min-w2", default="incumbent",
                    help="screen-1 min(w1, w2) floor at the frozen-rung k: 'incumbent' (default) = the weakest frozen "
                         "production code's own min(w1, w2) at that k (r0547+r0550 6, r0625 6, r0700 7, r0775 5, r0850 4), "
                         "or an integer")
    ap.add_argument("--skip-infeasible", nargs="*", default=None,
                    help="feasibility.py JSON(s): skip every seed of a config whose seed-0 build failed "
                         "(default for --overnight: feasibility-*.json in search/)")
    ap.add_argument("--decoder", default="fast", choices=("fast", "prod"),
                    help="fast = fast/fastdecode batched bit-exact twin (default; start-up selfcheck, falls back "
                         "to prod on failure), prod = holo.core.ldpc.decode one trial at a time")
    ap.add_argument("--seeds", type=int, default=None, help="override seeds per config")
    ap.add_argument("--finalists", type=int, default=None, help="override N (walked finalists per k)")
    ap.add_argument("--n-fine", type=int, default=None, help="override the number of walked finalists per k measured "
                    "at the fine trial count (default 4)")
    ap.add_argument("--workers", type=int, default=13)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-resume", action="store_true", help="refuse to run into an existing results.jsonl")
    ap.add_argument("--summarize-only", action="store_true")
    ap.add_argument("--min-w2", type=int, default=None,
                    help="screen-1 eligibility floor on min(w1, w2) (protocol: 10; default 16 for --overnight "
                         "since the trials: a k=1280 code threw 19 wrong decodes on its weight-10 pair)")
    ap.add_argument("--min-w2-final", type=int, default=None,
                    help="stricter min w1/w2 floor for FINALIST selection only (screen 1 still sees --min-w2)")
    ap.add_argument("--max-build-s", type=float, default=None,
                    help="per-code build time cap in s (default 120; uniform h14-16 heavy grids time out)")
    ap.add_argument("--s1-anchor", default=None,
                    help="'frozen' (the frozen recipe's 10 %% points, the literal protocol) or a run DIR whose best "
                         "clean walked code per k supplies the 10 %% points; default: frozen for smoke/trial, "
                         "search/trial-A for --overnight (k without a walked code there falls back to frozen)")
    a = ap.parse_args(argv)
    mode = "smoke" if a.smoke else "overnight" if a.overnight else "trial"
    out = Path(a.out) if a.out else common.SEARCH / f"{mode}-A"
    if a.summarize_only:
        print(common.summarize(out))
        return
    if a.no_resume and (out / "results.jsonl").exists():
        sys.exit(f"{out}/results.jsonl exists and --no-resume was given")
    frozen_on = (a.frozen_rungs or ("on" if mode == "overnight" else "off")) == "on"
    ks = ((1664, 1280) if a.primary == "on" else ()) + ((1600, 1216) if a.secondary else ())
    if frozen_on:
        ks += tuple(common.FROZEN_RUNGS) if mode != "smoke" else tuple(SMOKE_FROZEN)
    if not ks:
        sys.exit("no k selected")
    S = SETTINGS[mode]
    S.workers, S.ks = a.workers, ks
    S.min_w2 = a.min_w2 if a.min_w2 is not None else (16 if mode == "overnight" else 10)
    fks = [k for k in ks if k in common.FROZEN_RUNGS]
    if fks:
        S.min_w2_by_k = {k: (common.incumbent_floor(k) if a.frozen_min_w2 == "incumbent" else int(a.frozen_min_w2))
                         for k in fks}
        print(f"screen-1 floor at the frozen rungs ({a.frozen_min_w2}): {S.min_w2_by_k}", file=sys.stderr, flush=True)
    S.min_w2_final = a.min_w2_final
    if a.finalists is not None:
        S.n_finalists = a.finalists
    if a.n_fine is not None:
        S.n_fine = a.n_fine
    anc_src = a.s1_anchor or ("trial-A" if mode == "overnight" else "frozen")
    if anc_src != "frozen":
        d = Path(anc_src) if Path(anc_src).is_absolute() else common.SEARCH / anc_src
        S.s1_anchor = common.anchor_from(d, ks) if (d / "results.jsonl").exists() else {}
        print(f"screen-1 anchor from {d}: {S.s1_anchor}", file=sys.stderr)
    t = time.time()
    for k in ks:                                   # the generalized draw reproduces the frozen recipe
        ok = common.verify_baseline(k)
        what = "frozen production codes " + "+".join(common.FROZEN_RUNGS[k]) + " re-keyed edge-identical" \
            if k in common.FROZEN_RUNGS else f"{common.BASELINE_RID[k]} edge-identical to harness data"
        print(f"baseline k={k} ({what}): {ok}", file=sys.stderr)
        if not ok:
            sys.exit("baseline rows do NOT reproduce the frozen codes — refusing to run")
    base = [c for k in ks for c in common.baseline_cfgs(k)]
    S.decoder = common.select_decoder(a.decoder, [base[0].name] + [c.name for c in base if c.k in (3520,)][:1])
    if mode == "smoke":
        ok = common.check_channels_vs_harness("r0313")
        print(f"run_chan counts == harness channels.run_task (bsc/awgn/eras, r0313): {ok}", file=sys.stderr)
        if not ok:
            sys.exit("channel wrapper diverges from the harness")
    cfgs = base + grid(mode, ks, a.seeds, a.frozen_seeds)
    skip = a.skip_infeasible if a.skip_infeasible is not None else (
        sorted(str(x.name) for x in common.SEARCH.glob("feasibility-*.json")) if mode == "overnight" else [])
    if skip:
        bad = load_infeasible(skip)
        n0 = len(cfgs)
        cfgs = [c for c in cfgs if c.baseline or cfg_key(c) not in bad]
        print(f"[infeasible] skipped {n0 - len(cfgs)} configs x seeds whose seed-0 build failed in {skip}",
              file=sys.stderr, flush=True)
    if a.max_build_s is not None:
        cfgs = [c if c.baseline else common.replace(c, max_build_s=a.max_build_s) for c in cfgs]
    print(f"mode {mode}: {len(cfgs)} configs over k={ks}, workers {S.workers}, out {out} "
          f"(verify {time.time() - t:.1f} s)", file=sys.stderr, flush=True)
    srch = common.Search(cfgs, S, out, mode)
    finished = srch.run()
    p = common.summarize(out)
    print(f"{'finished' if finished else 'STOPPED (rerun resumes)'}; errors {srch.errors}; summary -> {p}",
          file=sys.stderr)
    common.exit_status(finished, srch.errors)


if __name__ == "__main__":
    main()
