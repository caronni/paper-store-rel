# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/variants_search.py
"""Tier B2 driver: ARA-precoded e-IRA and IRAA (doubly-accumulated parity) over Tier A's winning
recipe configs, through the three screens of common.Search (same JSONL / resume / summarize flow),
paired against the plain e-IRA on the same outer config and seed.  Constructions: variants.py.

  cd <repo>
  S=measure/rung-ladder/search
  PYTHONPATH=src:. env/bin/python $S/variants_search.py --smoke --workers 8
  PYTHONPATH=src:. env/bin/python $S/variants_search.py --trial --workers 12            # -> $S/trial-B2
  nohup env PYTHONPATH=src:. env/bin/python $S/variants_search.py --overnight --workers 14 \
      > $S/overnight-B2.log 2>&1 &                                                         # -> $S/overnight-B2
  PYTHONPATH=src:. env/bin/python $S/variants_search.py --summarize-only --out $S/trial-B2

Plain e-IRA rows of the same configs are part of every run (family "plain"); their s0/s1 lines (and
s2 lines when the trial counts match) are COPIED from Tier A's trial-A2 run when present — every
screen is deterministic (fixed seeds, common random numbers), so a copy equals a recomputation.
Screen 1 hangs off trial-A's best clean code per k (as Tier A's trial-A2 and overnight default), so
screen-1 scores are directly comparable with trial-A2's.  Finalists: the top N per (k, family) by
screen-1 score, plus every plain row already walked (Tier A's winners) and the frozen recipe.
Resume is the default; SIGINT/SIGTERM stop cleanly (common.Search).
"""
from __future__ import annotations

import argparse
import itertools
import json
import signal
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import variants as V  # noqa: E402

# Tier A trial-A2 winners (clean, best Es/N0@1 %) per k: (heavy_deg, heavy_frac, light), balanced
BASES = {
    "trial": {1664: [(8, 0.5, 3), (10, 0.3, 3)], 1600: [(12, 0.3, 3), (10, 0.5, 3)],
              1280: [(12, 0.5, 3), (8, 0.5, 3)], 1216: [(12, 0.3, 4), (8, 0.5, 3)]},
    "overnight": {1664: [(8, 0.5, 3), (10, 0.3, 3), (12, 0.3, 3), (6, 0.3, 3)],
                  1600: [(12, 0.3, 3), (10, 0.5, 3), (8, 0.5, 3), (6, 0.3, 3)],
                  1280: [(12, 0.5, 3), (8, 0.5, 3), (10, 0.5, 3), (6, 0.3, 3)],
                  1216: [(12, 0.3, 4), (8, 0.5, 3), (12, 0.5, 3), (6, 0.3, 3)]},
}
# (variant, knobs)
VARIANT_GRID = {
    "smoke": [("ara", dict(pre_frac=0.25, pre_sel="light")), ("iraa", dict(iraa_frac=0.5))],
    "trial": [("ara", dict(pre_frac=f, pre_sel=s)) for f in (0.25, 0.5) for s in ("heavy", "light")]
    + [("ara", dict(pre_frac=1.0, pre_sel="heavy"))]
    + [("iraa", dict(iraa_frac=0.25, iraa_links="all")), ("iraa", dict(iraa_frac=0.25, iraa_links="one")),
       ("iraa", dict(iraa_frac=0.5, iraa_links="all"))],
    # trial-B2: precoding ~1/4-1/2 of the info columns taken from the HEAVY end wins everywhere on screen 1;
    # light-end precoding is neutral, IRAA loses on screen 1 at every k (x1 = least bad, most robust)
    "overnight": [("ara", dict(pre_frac=f, pre_sel="heavy")) for f in (0.125, 0.1875, 0.25, 0.3125, 0.375, 0.5)]
    + [("ara", dict(pre_frac=0.25, pre_sel="light"))]
    + [("iraa", dict(iraa_frac=f, iraa_links="one")) for f in (0.125, 0.25)],
}
SEEDS = {"smoke": 1, "trial": 4, "overnight": 8}
SETTINGS = {
    "smoke": common.Settings(s1_trials=20, walk_trials=20, fine_trials=40, side_trials=20, n_finalists=1,
                             n_fine=99, seedvar_configs=0),
    "trial": common.Settings(s1_trials=100, walk_trials=100, fine_trials=500, side_trials=100, n_finalists=2,
                             n_fine=99, seedvar_configs=0),
    "overnight": common.Settings(s1_trials=100, walk_trials=200, fine_trials=500, side_trials=200,
                                 n_finalists=4, n_fine=99, seedvar_configs=2),
}
SRC_A = common.SEARCH / "trial-A2"


def family(c) -> str:
    return "baseline" if getattr(c, "baseline", False) else (c.variant if isinstance(c, V.VCfg) else "plain")


def grid(mode: str, ks, seeds: int | None, bases_mode: str | None = None):
    bm = BASES[bases_mode or ("trial" if mode == "smoke" else mode)]
    S = seeds if seeds is not None else SEEDS[mode]
    out = []
    for k in ks:
        bl = bm[k][:1] if mode == "smoke" else bm[k]
        for (hd, hf, lt), s in itertools.product(bl, range(S)):
            o = common.recipe_cfg(k, hd, hf, lt, "balanced", s)
            out.append(o)
            for var, kw in VARIANT_GRID[mode]:
                out.append(V.VCfg(outer=o, variant=var, **kw))
    return out


def seed_from(src: Path, out: Path, rids: set[str], S: common.Settings, anchor: dict) -> int:
    """Copy Tier A's lines for the plain rows (s0, s1 under the same anchor; s2 only when the
    source ran the same trial counts).  Deterministic screens -> a copy equals a recomputation."""
    if not (src / "results.jsonl").exists():
        return 0
    done, metas = common.load(src)
    ms = metas[-1]["settings"] if metas else {}
    same_s2 = all(ms.get(x) == getattr(S, x) for x in ("walk_trials", "fine_trials", "side_trials"))
    have = set()
    if (out / "results.jsonl").exists():
        have = set(common.load(out)[0])
    lines = []
    for (rid, scr), r in done.items():
        if rid not in rids or (rid, scr) in have:
            continue
        if scr == "s1":
            a, b = r.get("anchor") or {}, anchor.get(r["k"]) or {}
            if not a or not b or abs(a["es10"] - b["es10"]) > 1e-9 or abs(a["p10"] - b["p10"]) > 1e-9:
                continue
        if scr.startswith("s2") and not same_s2:
            continue
        lines.append(dict(r, copied_from=src.name))
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "results.jsonl", "a") as fh:
        for r in lines:
            fh.write(json.dumps(r, default=float) + "\n")
    return len(lines)


class VRunner(common.Runner):
    def _fill(self):
        while self.queue and len(self.inflight) < 3 * self.workers and not self.stop:
            prio, _, job, rq, tn = common.heapq.heappop(self.queue)
            if job.dead:
                continue
            if isinstance(rq, common.Call):
                f = self.ex.submit(rq.fn, *rq.args)
            else:
                f = self.ex.submit(V.task_chan_any, job.cfgd, job.restart, rq.channel, rq.params, tn[0], tn[1])
            self.inflight[f] = (job, rq)


class VSearch(common.Search):
    def __init__(self, cfgs, settings, out, mode, n_ref_plain: int = 1):
        super().__init__(cfgs, settings, out, mode)
        self.n_ref_plain = n_ref_plain

    def _eligible(self, cfg):
        """common's rule + the SINGLE-bit weight under the same floor (trial-B2: an IRAA x1 code with
        min w1 = 10 passed the pair floor and threw a weight-10, one-info-bit wrong decode)."""
        if not super()._eligible(cfg) or cfg.baseline:
            return super()._eligible(cfg)
        st = self.done[(cfg.name, "s0")]["struct"]
        return (st.get("min_w1") or 0) >= self.floor(cfg.k)

    def _job_s0(self, cfg):
        c = common.Call(V.screen0_any, (cfg.to_dict(),))
        yield [c]
        return c.result

    def finalists(self, k):
        cs = [c for c in self.by_k[k] if (c.name, "s1") in self.done and self._valid("s1", c, self.done[(c.name, "s1")])]
        base = [c for c in cs if c.baseline]
        sc = lambda c: (self.done[(c.name, "s1")]["score"], c.name)  # noqa: E731
        top = []
        for fam in V.VARIANTS:
            top += sorted([c for c in cs if family(c) == fam and self._final_ok(c)], key=sc)[: self.S.n_finalists]
        plain = [c for c in cs if family(c) == "plain"]
        refs = [c for c in plain if (c.name, "s2walk") in self.done]
        refs += [c for c in sorted([c for c in plain if self._final_ok(c)], key=sc)[: self.n_ref_plain] if c not in refs]
        extra = []
        if self.S.seedvar_configs:
            groups: dict[str, list] = {}
            for c in self.by_k[k]:
                if isinstance(c, V.VCfg):
                    groups.setdefault(c.tag, []).append(c)
            full = {t: g for t, g in groups.items() if len(g) > 1 and all((c.name, "s1") in self.done for c in g)}
            order = sorted(full, key=lambda t: statistics.mean(self.done[(c.name, "s1")]["score"] for c in full[t]))
            extra = [c for t in order[: self.S.seedvar_configs] for c in full[t] if c not in top]
        return top + refs + base, extra

    def run(self):
        self.runner = VRunner(self.S.workers, self.S.chunk)

        def handler(signum, frame):
            print(f"\n[signal {signum}] stopping: completed lines are on disk, rerun resumes", file=sys.stderr,
                  flush=True)
            self.runner.stop = True
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)
        for k in self.S.ks:
            self.stage[k] = "screen0/1"
            self._stage_a(k)
        self.runner.loop(self.progress)
        self.progress()
        self.fh.close()
        self.errors = self.runner.errors
        print(f"wall {time.time() - self.t0:.0f} s; stopped={self.runner.stop}; errors={self.errors}",
              file=sys.stderr, flush=True)
        return not self.runner.stop


# ---------------------------------------------------------------- summary
def _f(x, d=3):
    return common._f(x, d)


def _suffix(z0: dict) -> str:
    c = z0.get("cfg", {})
    if "variant" not in c:
        return "plain"
    v = V.VCfg.from_dict(c)
    return v.suffix


def _base_tag(z0: dict) -> str:
    c = z0.get("cfg", {})
    return c["outer"]["tag"] if "variant" in c else c.get("tag", "")


def summarize_v(out: Path) -> Path:
    out = Path(out)
    path = common.summarize(out)
    path.write_text(path.read_text() + "\n".join(b2_section(out)) + "\n")
    return path


def b2_section(out: Path) -> list[str]:
    """The Tier B2 part of the summary (paired screen 1 + compact screen 2) over <out>/results.jsonl;
    with a merged run dir it covers every tier's rows (the combined summary, summarize_all.py)."""
    out = Path(out)
    done, metas = common.load(out)
    s0 = {rid: r for (rid, s), r in done.items() if s == "s0"}
    s1 = {rid: r for (rid, s), r in done.items() if s == "s1"}
    ks = sorted({r["k"] for r in s0.values()}, reverse=True)
    L = ["", "---", "", "# Tier B2 — ARA-precoded e-IRA and IRAA vs the plain e-IRA", "",
         "Suffixes: `ara-pF{h|l}` = fraction F of info block-columns precoded (h = heavy/first columns, "
         "l = light/last), punctured intermediate bits, exclusive anchor block row per precoded column "
         "(rule f); `iraa-qF` = fraction F of parity block rows are second-accumulator outputs, every "
         "first-accumulator block linked; `x1` = one linked block per second-accumulator block row. "
         "Constructions: variants.py docstring.", ""]
    for k in ks:
        L += [f"## k = {k}", "",
              "### Screen 1, PAIRED on (base config, seed) against the plain e-IRA row of the same config and seed "
              "(Δ = variant − plain; negative = better; common random numbers)", "",
              "| variant | n pairs | mean Δ s1 | SD Δ | better / worse | mean s1 | best s1 | s0 verdicts | "
              "min w1 (min) | min w2 mean / min | chk deg | parity deg-2 frac | punct 1-SR | CPU s / 100 decodes |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        plain = {(_base_tag(z), z["seed"]): s1[r]["score"] for r, z in s0.items()
                 if z["k"] == k and _suffix(z) == "plain" and r in s1 and not z.get("baseline")}
        groups: dict[str, list] = {}
        for rid, z in s0.items():
            if z["k"] != k or z.get("baseline"):
                continue
            if "-B1-" in z.get("tag", ""):
                continue                      # merged runs: B1 profiles have no plain pair
            groups.setdefault(_suffix(z), []).append(z)
        for suf in sorted(groups, key=lambda x: (x != "plain", x)):
            zs = groups[suf]
            verd: dict[str, int] = {}
            for z in zs:
                for x in z.get("reasons") or ["pass"]:
                    verd[x.split("=")[0]] = verd.get(x.split("=")[0], 0) + 1
            sc = [(z, s1[z["rid"]]["score"]) for z in zs if z["rid"] in s1]
            d = [s - plain[(_base_tag(z), z["seed"])] for z, s in sc if (_base_tag(z), z["seed"]) in plain]
            st = [z.get("struct", {}) for z in zs if z.get("struct")]
            w1 = [x["min_w1"] for x in st if x.get("min_w1") is not None]
            w2 = [x["min_w2"] for x in st if x.get("min_w2") is not None]
            cd = f"{min(x['chk_deg_min'] for x in st)}..{max(x['chk_deg_max'] for x in st)}" if st else "—"
            p2 = [x.get("parity_deg2_frac") for x in st if x.get("parity_deg2_frac") is not None]
            sr = [x.get("frac_1sr") for x in st if x.get("frac_1sr") is not None]
            cpu = [s1[z["rid"]]["cpu"] / sum(p["n"] for p in s1[z["rid"]]["points"]) * 100 for z, _ in sc]
            L.append(f"| {suf} | {len(d)} | {_f(statistics.mean(d), 2) if d else '—'} | "
                     f"{_f(statistics.pstdev(d), 2) if len(d) > 1 else '—'} | "
                     f"{sum(x < 0 for x in d)} / {sum(x > 0 for x in d)} | "
                     f"{_f(statistics.mean([s for _, s in sc]), 2) if sc else '—'} | "
                     f"{_f(min([s for _, s in sc]), 2) if sc else '—'} | {json.dumps(verd)} | "
                     f"{min(w1) if w1 else '—'} | {_f(statistics.mean(w2), 1) if w2 else '—'} / {min(w2) if w2 else '—'} | "
                     f"{cd} | {_f(statistics.mean(p2), 2) if p2 else '—'} | {_f(statistics.mean(sr), 2) if sr else '—'} | "
                     f"{_f(statistics.mean(cpu), 1) if cpu else '—'} |")
        # compact screen-2 comparison
        fz = next((m["frozen"][str(k)] for m in reversed(metas) if str(k) in m.get("frozen", {})), {})
        walked = [r for (rid, s), r in done.items() if s == "s2walk" and r["k"] == k]

        def best(rid):
            return done.get((rid, "s2fine")) or done.get((rid, "s2walk"))
        base_es = next((best(r["rid"])["es1"] for r in walked if s0.get(r["rid"], {}).get("baseline")), None)
        pl = [best(r["rid"])["es1"] for r in walked if _suffix(s0.get(r["rid"], {})) == "plain"
              and not s0[r["rid"]].get("baseline") and best(r["rid"])["es1"] is not None
              and common.undetected(done, r["rid"])[0] == 0]
        best_plain = min(pl) if pl else None
        L += ["", f"### Screen 2 (walks; `fine` = 500 trials around the 1 % point). Recipe {fz.get('rid')} and the "
              f"best clean plain e-IRA (Tier A winner) Es/N0@1% = {_f(best_plain)} dB are the references", "",
              "| code | family | Es/N0@1% | src | Δ vs best plain | Δ vs recipe | gap dB | p@1% | gap bit | min w2 | "
              "undet/trials | robust f0.1% | mean iters @ awgn pt nearest 1 % |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        rows = []
        for r in walked:
            rid = r["rid"]; z = s0.get(rid, {}); b = best(rid)
            und, ntr, _ = common.undetected(done, rid)
            side = done.get((rid, "s2side"))
            rob = "—"
            if side:
                q = next((p for p in side["points"] if p["channel"] == "robust" and abs(p["params"]["f"] - 0.001) < 1e-9), None)
                rob = f"{q['fails']}/{q['n']}" if q else "—"
            aw = [p for p in (done.get((rid, "s2fine"), {}).get("points", []) + r["points"]) if p["channel"] == "awgn"]
            it = None
            if aw and b["es1"] is not None:
                p = min(aw, key=lambda p: abs(p["params"]["esn0_db"] - b["es1"]))
                it = p.get("mean_iters")
            fam = "baseline" if z.get("baseline") else _suffix(z)
            rows.append((b["es1"] if b["es1"] is not None else 99,
                         f"| {rid} | {fam} | {_f(b['es1'])} | {'fine' if (rid, 's2fine') in done else 'walk'} | "
                         f"{_f(None if best_plain is None or b['es1'] is None else b['es1'] - best_plain, 2)} | "
                         f"{_f(None if base_es is None or b['es1'] is None else b['es1'] - base_es, 2)} | "
                         f"{_f(b['gap_db'], 2)} | {_f(b['p1'], 4)} | {_f(b['gap_bit'], 3)} | "
                         f"{z.get('struct', {}).get('min_w2')} | {und}/{ntr}{' ⚠' if und else ''} | {rob} | {_f(it, 1)} |"))
        L += [x for _, x in sorted(rows, key=lambda t: t[0])] + [""]
    return L


def main(argv=None):
    common.term_as_interrupt()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    m = ap.add_mutually_exclusive_group()
    m.add_argument("--smoke", action="store_true")
    m.add_argument("--trial", action="store_true")
    m.add_argument("--overnight", action="store_true")
    ap.add_argument("--primary-only", action="store_true", help="k in {1664, 1280} only (default: all four k)")
    ap.add_argument("--seeds", type=int, default=None)
    ap.add_argument("--finalists", type=int, default=None, help="top N per (k, family) walked")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-resume", action="store_true")
    ap.add_argument("--summarize-only", action="store_true")
    ap.add_argument("--min-w2", type=int, default=None, help="screen-1 floor on min(w1, w2) (10; 16 for --overnight)")
    ap.add_argument("--min-w2-final", type=int, default=None,
                    help="stricter min w1/w2 floor for FINALIST selection only (screen 1 still sees --min-w2)")
    ap.add_argument("--no-copy", action="store_true", help="do not copy Tier A's plain-row lines")
    ap.add_argument("--copy-from", default="trial-A2",
                    help="run DIR (under search/ or absolute) whose plain-row lines are copied (default trial-A2; "
                         "the overnight script passes overnight-A, whose walk/fine/side counts match)")
    ap.add_argument("--s1-anchor", default="trial-A")
    ap.add_argument("--ref-plain", type=int, default=None,
                    help="plain rows walked as references besides those already walked (default 1 trial, 2 overnight)")
    ap.add_argument("--s0-only", action="store_true", help="build + audit the grid (screen 0) and stop")
    ap.add_argument("--decoder", default="fast", choices=("fast", "prod"),
                    help="fast = fast/fastdecode batched bit-exact twin (default; start-up selfcheck, falls back "
                         "to prod on failure), prod = holo.core.ldpc.decode one trial at a time")
    a = ap.parse_args(argv)
    mode = "smoke" if a.smoke else "overnight" if a.overnight else "trial"
    out = Path(a.out) if a.out else common.SEARCH / f"{mode}-B2"
    if a.summarize_only:
        print(summarize_v(out))
        return
    if a.no_resume and (out / "results.jsonl").exists():
        sys.exit(f"{out}/results.jsonl exists and --no-resume was given")
    ks = (1664, 1280) if (a.primary_only or mode == "smoke") else (1664, 1280, 1600, 1216)
    S = SETTINGS[mode]
    S.workers, S.ks = a.workers, ks
    S.min_w2 = a.min_w2 if a.min_w2 is not None else (16 if mode == "overnight" else 10)
    S.min_w2_final = a.min_w2_final
    if a.finalists is not None:
        S.n_finalists = a.finalists
    if a.s1_anchor != "frozen":
        d = Path(a.s1_anchor) if Path(a.s1_anchor).is_absolute() else common.SEARCH / a.s1_anchor
        S.s1_anchor = common.anchor_from(d, ks) if (d / "results.jsonl").exists() else {}
        print(f"screen-1 anchor from {d}: {S.s1_anchor}", file=sys.stderr)
    t = time.time()
    for k in ks:
        ok = common.verify_baseline(k)
        print(f"baseline k={k} ({common.BASELINE_RID[k]}) edge-identical to harness data: {ok}", file=sys.stderr)
        if not ok:
            sys.exit("generalized draw does NOT reproduce the frozen recipe — refusing to run")
    if mode == "smoke":
        print(f"variant self-checks: {self_check()}", file=sys.stderr)
    S.decoder = common.select_decoder(a.decoder, [common.baseline_cfg(ks[0]).name])
    if S.decoder == "fast" and not V.selfcheck_v_fast():
        print("\n" + "!" * 100 + "\n[decoder] run_chan_v_fast != run_chan_v on the variant self-check -- FALLING BACK TO "
              "THE PRODUCTION DECODER\n" + "!" * 100, file=sys.stderr, flush=True)
        S.decoder = common.select_decoder("prod", [])
    cfgs = [common.baseline_cfg(k) for k in ks] + grid(mode, ks, a.seeds)
    if not a.no_copy:
        plain = {c.name for c in cfgs if not isinstance(c, V.VCfg)}
        src = Path(a.copy_from) if Path(a.copy_from).is_absolute() else common.SEARCH / a.copy_from
        n = seed_from(src, out, plain, S, S.s1_anchor or {})
        print(f"copied {n} plain/baseline lines from {src.name}", file=sys.stderr)
    print(f"mode {mode}: {len(cfgs)} configs over k={ks}, workers {S.workers}, out {out} "
          f"(verify {time.time() - t:.1f} s)", file=sys.stderr, flush=True)
    if a.s0_only:
        S.ks = ()
        vs = VSearch(cfgs, S, out, mode)
        vs.runner = VRunner(S.workers, S.chunk)
        for c in cfgs:
            vs._launch("s0", c, lambda r: None)
        vs.runner.loop(vs.progress)
        vs.fh.close()
        print(f"screen 0 done -> {out}", file=sys.stderr)
        return
    nref = a.ref_plain if a.ref_plain is not None else (2 if mode == "overnight" else 1)
    vs = VSearch(cfgs, S, out, mode, n_ref_plain=nref)
    finished = vs.run()
    p = summarize_v(out)
    print(f"{'finished' if finished else 'STOPPED (rerun resumes)'}; errors {vs.errors}; summary -> {p}", file=sys.stderr)
    common.exit_status(finished, vs.errors)


def self_check() -> dict:
    """(1) the variant channel wrapper equals common.run_chan when given a plain code wrapped as a
    zero-precoding mother (same generator consumption), checked on counts; (2) every variant family
    encodes to H c == 0 and decodes noiselessly (screen0_v does this per code)."""
    o = common.recipe_cfg(1664, 8, 0.5, 3, "balanced", 0)
    rid = common.register(o)
    code = common.construct._CODE_CACHE[rid]
    M = V.Mother(rid, "plain", 1664, common.N, code.edge_chk.astype(int), code.edge_var.astype(int),
                 code.enc_info_col, code.enc_rows, code.enc_row_starts)
    M.encode = lambda info: common.encode(info, rid)          # type: ignore[method-assign]
    V._MOTHER[rid] = M
    res = {}
    for chn, prm in (("bsc", {"p": 0.115}), ("awgn", {"esn0_db": -3.2, "sigma": common.sigma_of(-3.2)}),
                     ("eras", {"eps": 0.3, "p": 0.05}), ("robust", {"esn0_db": -3.0, "sigma": common.sigma_of(-3.0), "f": 0.001})):
        x = V.run_chan_v(rid, chn, prm, 0, 20)
        y = common.run_chan(rid, chn, prm, 0, 20)
        res[chn] = all(x[f] == y[f] for f in ("fails", "undetected", "iters", "iters_ok", "n_ok"))
    del V._MOTHER[rid]
    if not all(res.values()):
        sys.exit(f"run_chan_v diverges from common.run_chan: {res}")
    return res


if __name__ == "__main__":
    main()
