# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/c1/tables_c1.py
"""results-c1.json (+ ../results.json continuity rows) -> ../TABLES-c1.md and
c1/tables-c1.json.  Reuses ../harness/tables.py interp_x/fmt unchanged."""
from __future__ import annotations
import json, math, sys
from pathlib import Path
from statistics import NormalDist
C1 = Path(__file__).resolve().parent
WORK = C1.parent
sys.path.insert(0, str(C1))
import codes_c1  # noqa: E402
from codes_c1 import ch  # noqa: E402
import tables as oldt  # noqa: E402  (../harness/tables.py)
interp_x, fmt, h2 = oldt.interp_x, oldt.fmt, ch.h2
ND = NormalDist()
OVERHEAD = 132                       # p100: 100 word sites + 32 CRC
C2 = {"c2-r0850": (3520 - OVERHEAD) / 4096, "c2-r0700": (2880 - OVERHEAD) / 4096}
CONT = codes_c1.CONTINUITY           # r0250, r0313, r0313-f50 (reused, not re-run)
EXTRA = ["r0297", "r0391-f50"]       # previous run, c1-vs-c2 table only
CHANNELS = [("VersaLink E RGB", 0.220), ("VersaLink E grey", 0.215), ("Canon E whole", 0.213),
            ("Canon per-tile p5", 0.184), ("Canon per-tile median", 0.202), ("Canon per-tile p95", 0.264)]
CANON_Q = [(0.0, 0.173), (0.05, 0.184), (0.5, 0.202), (0.95, 0.264), (1.0, 0.353)]   # e040 §040.4c


def p_of_esn0(db):            # hard error of the same BIAWGN channel: p = Q(sqrt(2 Es/N0)) = Q(1/sigma)
    return 1 - ND.cdf(math.sqrt(2 * 10 ** (db / 10)))


def esn0_of_p(p):             # inverse: Es/N0 = Qinv(p)^2 / 2
    return 10 * math.log10(ND.inv_cdf(1 - p) ** 2 / 2)


def cap_soft(p):              # BIAWGN capacity of the channel whose hard error is p
    return ch.biawgn_capacity(1 / ND.inv_cdf(1 - p))


def canon_tile_frac(p):       # fraction of Canon tiles with raw error <= p, piecewise-linear through the quantiles
    if p <= CANON_Q[0][1]:
        return 0.0
    for (q0, x0), (q1, x1) in zip(CANON_Q, CANON_Q[1:]):
        if p <= x1:
            return q0 + (q1 - q0) * (p - x0) / (x1 - x0)
    return 1.0


def rate_at_gap(esn0_db, gap_db):   # largest R whose Shannon Es/N0 + gap <= the channel's Es/N0
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if ch.biawgn_shannon_esn0_db(mid) + gap_db <= esn0_db:
            lo = mid
        else:
            hi = mid
    return lo


def main():
    new = json.loads((C1 / "results-c1-raw.json").read_text())   # the sweep output, copied verbatim
    oldr = json.loads((WORK / "results.json").read_text())
    rows_old = CONT + EXTRA
    P = new["points"] + [p for p in oldr["points"] if p["rid"] in rows_old and p["channel"] in ("bsc", "awgn", "eras")]
    cap = dict(new["meta"]["capacity"]); cap.update({r: oldr["meta"]["capacity"][r] for r in rows_old})
    st = json.loads((C1 / "structure-c1.json").read_text()); st_old = json.loads((WORK / "structure.json").read_text())
    st.update({r: st_old[r] for r in rows_old})
    bl = {r["rate_id"]: r for r in json.loads((C1 / "build_log.json").read_text())}
    bl.update({r["rate_id"]: r for r in json.loads((WORK / "build_log.json").read_text()) if r["rate_id"] in rows_old})
    order = sorted(codes_c1.NEW + CONT, key=lambda r: (st[r]["k_bits"], r))
    kind = {r: ("recipe (new)" if r in codes_c1.CANDIDATES else "VARIANT (new)" if r in codes_c1.VARIANTS
                else "recipe (prev run)" if "-" not in r else "VARIANT (prev run)") for r in order + EXTRA}
    hf = {r: bl[r]["heavy_frac"] for r in order + EXTRA}
    T, fr = {}, {}
    # structural
    L = ["| code | kind | k | R | HEAVY_FRAC | kb/mb | nh×deg | restart | rule-(d) cap | edges | chk deg min..max (mean) | checks w/o info edge | var deg hist | girth>4 | min w1 | min w2 (#≤8) | user bits p100 / p120 |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in order:
        s = st[r]; b = bl[r]
        vh = ", ".join(f"{d}:{c}" for d, c in sorted(s["var_deg_hist"].items(), key=lambda t: int(t[0])))
        L.append(f"| {r} | {kind[r]} | {s['k_bits']} | {s['rate']:.4f} | {b['heavy_frac']} | {s['kb']}/{s['mb']} | {s['nh']}×{s['heavy_deg']} | {b['restart']} | {b['deg_cap_rule_d']} | {s['n_edges']} | "
                 f"{s['chk_deg_min']}..{s['chk_deg_max']} ({s['chk_deg_mean']:.2f}) | {s['n_chk_no_info_edge']} ({100*s['frac_chk_no_info_edge']:.1f}%) | {vh} | {s['girth_gt4']} (max {s['HHt_offdiag_max']}) | "
                 f"{s['min_w1']} | {s['min_w2']} ({s['n_w2_le8']}) | {s['user_bits_p100']} / {s['user_bits_p120']} |")
    T["structural"] = "\n".join(L)
    # BSC
    L = ["| code | kind | R | p_cap | p@1% | p@10% | gap@1% (bits) | p@1%/p_cap | p@1% detected-only | lowest p with an undetected | iters@1% (all / ok) | walk pts | undetected/trials |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    G = ["| code | p : fails/n (undet) [mean iters] |", "|---|---|"]
    for r in order + EXTRA:
        pts = [p for p in P if p["rid"] == r and p["channel"] == "bsc"]
        xs = [(p["params"]["p"], p["bler"], p["n"]) for p in pts]
        p1 = interp_x(xs, 0.01, True); p10 = interp_x(xs, 0.10, True)
        R = cap[r]["rate"]; pc = cap[r]["p_cap"]
        xd = [(p["params"]["p"], (p["fails"] - p["undetected"]) / p["n"], p["n"]) for p in pts]
        p1d = interp_x(xd, 0.01, True)
        near = min(pts, key=lambda p: abs(p["params"]["p"] - p1)) if p1 is not None else None
        it = f"{near['mean_iters']:.1f} / {fmt(near['mean_iters_ok'], 1)} (p={near['params']['p']})" if near else "—"
        fl = [p["params"]["p"] for p in pts if p["undetected"]]
        und = sum(p["undetected"] for p in pts); nt = sum(p["n"] for p in pts)
        fr.setdefault(r, {}).update({"R": R, "p_cap": pc, "p1_hard": p1, "p10_hard": p10, "p1_hard_det": p1d, "bsc_und": und, "bsc_trials": nt})
        if r in EXTRA:
            continue
        L.append(f"| {r} | {kind[r]} | {R:.4f} | {pc:.4f} | {fmt(p1)} | {fmt(p10)} | {fmt((1 - h2(p1)) - R if p1 else None, 3)} | {fmt(p1 / pc if p1 else None, 3)} | {fmt(p1d)} | {fmt(min(fl), 3) if fl else '—'} | {it} | {len(pts)} | {und}/{nt} |")
        G.append(f"| {r} | " + "; ".join(f"{p['params']['p']:.3f}: {p['fails']}/{p['n']}" + (f" ({p['undetected']}u)" if p['undetected'] else "") + f" [{p['mean_iters']:.0f}]" for p in sorted(pts, key=lambda q: q['params']['p'])) + " |")
    T["bsc"] = "\n".join(L); T["bsc_grid"] = "\n".join(G)
    # AWGN
    L = ["| code | kind | R | Es/N0 Shannon (dB) | Es/N0@1% (dB) | gap (dB) | Es/N0@1% det-only | Es/N0@10% | Eb/N0@1% (dB) | walk pts | undetected/trials |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    G = ["| code | Es/N0 dB : fails/n (undet) [mean iters] |", "|---|---|"]
    for r in order + EXTRA:
        pts = [p for p in P if p["rid"] == r and p["channel"] == "awgn"]
        xs = [(p["params"]["esn0_db"], p["bler"], p["n"]) for p in pts]
        e1 = interp_x(xs, 0.01, False); e10 = interp_x(xs, 0.10, False)
        xd = [(p["params"]["esn0_db"], (p["fails"] - p["undetected"]) / p["n"], p["n"]) for p in pts]
        e1d = interp_x(xd, 0.01, False)
        R = cap[r]["rate"]; sh = cap[r]["esn0_shannon_db"]
        und = sum(p["undetected"] for p in pts); nt = sum(p["n"] for p in pts)
        fr[r].update({"esn0_shannon_db": sh, "esn0_1pct_db": e1, "gap_db": e1 - sh if e1 is not None else None, "p1_soft": p_of_esn0(e1) if e1 is not None else None,
                      "awgn_und": und, "awgn_trials": nt})
        if r in EXTRA:
            continue
        L.append(f"| {r} | {kind[r]} | {R:.4f} | {sh:.3f} | {fmt(e1, 3)} | {fmt(e1 - sh if e1 is not None else None, 2)} | {fmt(e1d, 3)} | {fmt(e10, 3)} | {fmt(e1 - 10 * math.log10(R) if e1 is not None else None, 3)} | {len(pts)} | {und}/{nt} |")
        G.append(f"| {r} | " + "; ".join(f"{p['params']['esn0_db']:.2f}: {p['fails']}/{p['n']}" + (f" ({p['undetected']}u)" if p['undetected'] else "") + f" [{p['mean_iters']:.0f}]" for p in sorted(pts, key=lambda q: q['params']['esn0_db'])) + " |")
    T["awgn"] = "\n".join(L); T["awgn_grid"] = "\n".join(G)
    # erasure + error
    eps_g, p_g = [0.3, 0.5, 0.7], [0.02, 0.05]
    L = ["| code | R | p | " + " | ".join(f"ε={e}" for e in eps_g) + " | max ε @ BLER≤1% | (1−ε)(1−h2(p)) − R at that ε |", "|---|---|---|" + "---|" * len(eps_g) + "---|---|"]
    for r in order:
        R = cap[r]["rate"]
        for pp in p_g:
            row = {p["params"]["eps"]: p for p in P if p["rid"] == r and p["channel"] == "eras" and p["params"]["p"] == pp}
            cells = ["—" if row.get(e) is None else f"{row[e]['fails']}/{row[e]['n']}" + (f" ({row[e]['undetected']}u)" if row[e]["undetected"] else "") for e in eps_g]
            ok = [e for e in eps_g if e in row and row[e]["bler"] <= 0.01]
            me = max(ok) if ok else None
            fr[r][f"eras_p{pp}"] = {str(e): [row[e]["fails"], row[e]["n"], row[e]["undetected"]] for e in eps_g if e in row}
            L.append(f"| {r} | {R:.3f} | {pp} | " + " | ".join(cells) + f" | {fmt(me, 1)} | {fmt((1 - me) * (1 - h2(pp)) - R if me is not None else None, 3)} |")
    T["erasure"] = "\n".join(L)
    # capacity check
    L = ["| raw hard p | source | 1−h2(p) (hard) | Es/N0 = Qinv(p)²/2 (dB) | BIAWGN C (soft) | ×4 per c2 area: hard / soft | ÷ c2-r0850 0.827: hard / soft | R closable at 1.0 / 1.5 / 2.0 / 3.0 dB gap | net bits per c2 area at those R ((4096R−132)/1024) |",
         "|---|---|---|---|---|---|---|---|---|"]
    srcs = {0.173: "Canon per-tile min", 0.184: "Canon per-tile p5", 0.202: "Canon per-tile median", 0.21: "orchestrator", 0.213: "Canon whole-sheet", 0.215: "VersaLink grey",
            0.22: "VersaLink RGB", 0.264: "Canon per-tile p95", 0.15: "(reference)", 0.10: "(reference)", 0.058: "VersaLink D c2 (per c2 cell)"}
    capchk = []
    for p in sorted(srcs):
        hc = 1 - h2(p); es = esn0_of_p(p); sc = cap_soft(p)
        rs = [rate_at_gap(es, g) for g in (1.0, 1.5, 2.0, 3.0)]
        capchk.append({"p": p, "source": srcs[p], "hard_cap": hc, "esn0_db": es, "soft_cap": sc, "rate_at_gap_1_1.5_2_3": rs})
        L.append(f"| {p} | {srcs[p]} | {hc:.3f} | {es:.2f} | {sc:.3f} | {4*hc:.2f} / {4*sc:.2f} | {4*hc/C2['c2-r0850']:.2f} / {4*sc/C2['c2-r0850']:.2f} | "
                 + " / ".join(f"{x:.3f}" for x in rs) + " | " + " / ".join(f"{(4096*x - OVERHEAD)/1024:.2f}" for x in rs) + " |")
    T["capacity"] = "\n".join(L)
    # supplement: max_iters 200
    it200 = json.loads((C1 / "iters-c1.json").read_text()) if (C1 / "iters-c1.json").exists() else None
    L = ["| code | p@1% hard, 60 it → 200 it | p@10% hard 60 → 200 | Es/N0@1% 60 → 200 (dB) | gap dB 60 → 200 | p@1% soft 60 → 200 | Es/N0@10% 60 → 200 | mean iters at the 200-it p@1% point | undetected (200 it) |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in order + EXTRA:
        if not it200:
            break
        pb = [q for q in it200["points"] if q["rid"] == r and q["channel"] == "bsc"]
        pa = [q for q in it200["points"] if q["rid"] == r and q["channel"] == "awgn"]
        if not pb:
            continue
        # points skipped as dead (BLER 1.0 at 60 it) stay dead: add them from the 60-it record
        dead_b = [q for q in P if q["rid"] == r and q["channel"] == "bsc" and q["bler"] >= 0.6 and q["fails"] > 0]
        dead_a = [q for q in P if q["rid"] == r and q["channel"] == "awgn" and q["bler"] >= 0.6 and q["fails"] > 0]
        xb = [(q["params"]["p"], q["bler"], q["n"]) for q in pb + [d for d in dead_b if all(abs(d["params"]["p"] - e["params"]["p"]) > 1e-9 for e in pb)]]
        xa = [(q["params"]["esn0_db"], q["bler"], q["n"]) for q in pa + [d for d in dead_a if all(abs(d["params"]["esn0_db"] - e["params"]["esn0_db"]) > 1e-9 for e in pa)]]
        p1 = interp_x(xb, 0.01, True); p10 = interp_x(xb, 0.10, True); e1 = interp_x(xa, 0.01, False); e10 = interp_x(xa, 0.10, False)
        f = fr[r]; sh = f["esn0_shannon_db"]
        f.update({"it200_p1_hard": p1, "it200_p10_hard": p10, "it200_esn0_1pct_db": e1, "it200_gap_db": e1 - sh if e1 is not None else None,
                  "it200_p1_soft": p_of_esn0(e1) if e1 is not None else None, "it200_esn0_10pct_db": e10})
        xs60 = [(q["params"]["esn0_db"], q["bler"], q["n"]) for q in P if q["rid"] == r and q["channel"] == "awgn"]
        e10_60 = interp_x(xs60, 0.10, False)
        near = min(pb, key=lambda q: abs(q["params"]["p"] - p1)) if p1 else None
        und = sum(q["undetected"] for q in pb + pa)
        L.append(f"| {r} | {fmt(f['p1_hard'])} → {fmt(p1)} | {fmt(f['p10_hard'])} → {fmt(p10)} | {fmt(f['esn0_1pct_db'], 3)} → {fmt(e1, 3)} | {fmt(f['gap_db'], 2)} → {fmt(f['it200_gap_db'], 2)} | "
                 f"{fmt(f['p1_soft'])} → {fmt(f['it200_p1_soft'])} | {fmt(e10_60, 3)} → {fmt(e10, 3)} | {near['mean_iters']:.0f} (p={near['params']['p']}) | {und}/{sum(q['n'] for q in pb + pa)} |")
    T["iters200"] = "\n".join(L)
    fd = json.loads((C1 / "floor_diag.json").read_text()) if (C1 / "floor_diag.json").exists() else []
    L = ["| code | channel | point | failing trial ids (bit errors at 60 it; clears at 200 / 500 it?) |", "|---|---|---|---|"]
    for d in fd:
        L.append(f"| {d['rid']} | {d['channel']} | {d['x']} | " + "; ".join(f"t={q['t']} ({q['biterr60']} b; {'yes' if q['good200'] else 'no'} / {'yes' if q['good500'] else 'no'})" for q in d["fails"]) + " |")
    T["floor_diag"] = "\n".join(L)
    # c1 vs c2
    L = ["| code | kind | k | R | p@1% HARD (a) | p@1% SOFT = Q(√(2·Es/N0@1%)) (b) | net bits / c1 cell (k−132)/4096 | per c2 area (×4) | ÷ c2-r0850 (0.827) | ÷ c2-r0700 (0.671) | "
         + " | ".join(f"{n} {p*100:.1f}%" for n, p in CHANNELS) + " | Canon tiles closable hard / soft (interp.) | p@1% hard / soft at 200 it (supplement) |",
         "|---|---|---|---|---|---|---|---|---|---|" + "---|" * len(CHANNELS) + "---|---|"]
    for r in order + EXTRA:
        f = fr[r]; k = st[r]["k_bits"] if r in st else codes_c1.codes.spec(r).k_bits
        net = (k - OVERHEAD) / 4096; area = 4 * net
        f.update({"k": k, "net_per_c1_cell": net, "net_per_c2_area": area, "ratio_c2_r0850": area / C2["c2-r0850"], "ratio_c2_r0700": area / C2["c2-r0700"]})
        marks = []
        for n, pc in CHANNELS:
            h = f["p1_hard"] is not None and f["p1_hard"] >= pc; s = f["p1_soft"] is not None and f["p1_soft"] >= pc
            marks.append("hard+soft" if h else "soft only" if s else "no")
        f["fits"] = dict(zip([n for n, _ in CHANNELS], marks))
        th = canon_tile_frac(f["p1_hard"]) if f["p1_hard"] else 0.0; ts = canon_tile_frac(f["p1_soft"]) if f["p1_soft"] else 0.0
        f["canon_tile_frac_hard"], f["canon_tile_frac_soft"] = th, ts
        L.append(f"| {r} | {kind.get(r, '')} | {k} | {k/4096:.4f} | {fmt(f['p1_hard'])} | {fmt(f['p1_soft'])} | {net:.4f} | {area:.3f} | {area/C2['c2-r0850']:.2f} | {area/C2['c2-r0700']:.2f} | "
                 + " | ".join(marks) + f" | {100*th:.1f}% / {100*ts:.1f}% | {fmt(f.get('it200_p1_hard'))} / {fmt(f.get('it200_p1_soft'))} |")
    T["c1_vs_c2"] = "\n".join(L)
    und_rows = ["| code | channel | undetected/trials | at points |", "|---|---|---|---|"]
    for r in order:
        for c in ("bsc", "awgn", "eras"):
            pp = [p for p in P if p["rid"] == r and p["channel"] == c]
            u = sum(p["undetected"] for p in pp)
            if u:
                und_rows.append(f"| {r} | {c} | {u}/{sum(p['n'] for p in pp)} | " + "; ".join(f"{ {k_: v for k_, v in p['params'].items() if k_ != 'sigma'} }: {p['undetected']}" for p in pp if p["undetected"]) + " |")
    T["undetected"] = "\n".join(und_rows)
    out = {"meta": new["meta"], "continuity_from": str(WORK / "results.json"), "continuity_codes": rows_old,
           "structure": {r: st[r] for r in order}, "build": {r: bl[r] for r in order + EXTRA}, "frontier": fr, "capacity_check": capchk,
           "overhead_bits": OVERHEAD, "c2_net_per_c2_cell": C2, "channels": CHANNELS, "canon_tile_quantiles": CANON_Q,
           "points": new["points"]}
    (C1 / "results-c1.json").write_text(json.dumps(out, indent=1, default=str) + "\n")
    (C1 / "tables-c1.json").write_text(json.dumps(T, indent=1))
    return T, new["meta"]


def write_md(T, meta):
    bl = json.loads((C1 / "build_log.json").read_text())
    head = (C1 / "headline.md").read_text().strip() if (C1 / "headline.md").exists() else "(headline pending)"
    md = ["# Rung-ladder measurement, c1 extension (sub-r0300) — rung-ladder-20260930", "", head, "",
          "## Run record", "",
          f"- Sweep: `{meta['command']}` — {meta['trials_per_point']} trials/point (chunks of {meta['chunk']}), {meta['workers']} workers, wall {meta['wall_seconds']:.0f} s.",
          "- Build: `cd <repo> && PYTHONPATH=src:. env/bin/python measure/rung-ladder/c1/build_c1.py` (0.2 s; frozen recipe via ../harness/build.py build_one, seed label `ldpc-v1/<rid>`; restarts: "
          + ", ".join(f"{b['rate_id']} {b['restart']}" for b in bl) + ").",
          "- Structure: `... c1/structure_c1.py` (0.7 s, ../harness/structure.py stats unchanged). Tables: `... c1/tables_c1.py`. Smoke: `c1/sweep_c1.py --smoke --workers 8` (10 s, results-c1-smoke.json).",
          f"- Seeds: trial t uses `np.random.default_rng(base + t)`, base = {meta['seed_bases']} (the previous run's; common random numbers across codes). Decoder: `holo.core.ldpc.decode.decode` (production, min-sum α=0.8, 60 iters + one sum-product retry). Hard LLR ±log((1−p)/p); BIAWGN LLR −2y/σ², x = 1−2c, Es/N0 = 1/(2σ²).",
          "- Walks as the previous run: (a) 0.005 p grid from the BSC-capacity point, (b) 0.25 dB grid from the Shannon point; easy side until two consecutive 0/200, hard side until BLER ≥ 0.5; p@1% by linear interpolation in log BLER (0/n floored at 0.5/n). (c) fixed grid ε ∈ {0.3, 0.5, 0.7} × p ∈ {0.02, 0.05}.",
          "- Supplement: `... c1/iters_c1.py` (max_iters=200 on every live (a)/(b) walk point of the ten new codes + r0250, same seeds, 14 workers, wall 185 s -> iters-c1.json); `... c1/floor_diag.py` (failing trial ids at ten near-1 % points, re-decoded at 200/500 iters, 6 s -> floor_diag.json). Total wall of this extension ~6.5 min of compute.",
          "- Continuity rows r0250, r0313, r0313-f50 (and r0297, r0391-f50 in the c1-vs-c2 table) are the previous run's results.json entries, NOT re-run.",
          "- SOFT conversion: an Es/N0@1% threshold on BIAWGN is mapped to the raw hard error of the same channel, p = Q(√(2·Es/N0)) = Q(1/σ). This assumes the cell channel is two equal-variance Gaussians (symmetric); the recorded c1 channels have unequal means and unmeasured variances, and NO c1 soft/context/multi-capture measurement exists.",
          "- Net bits: K family p100, (k − 100 sites − 32 CRC)/4096 per c1 cell, ×4 per c2 cell area; c2-r0850 = 3388/4096 = 0.827, c2-r0700 = 2748/4096 = 0.671 per c2 cell.", "",
          "## c1 vs c2 (the deliverable)", "", T["c1_vs_c2"], "",
          "Marks: `hard+soft` = p@1% HARD ≥ the channel's raw error; `soft only` = only the Gaussian-soft threshold reaches it; `no` = neither. Canon tile fractions: piecewise-linear CDF through e040's per-tile quantiles (min 17.3, p5 18.4, median 20.2, p95 26.4, max 35.3 %) evaluated at the code's p@1% — an interpolation, not a count.", "",
          "## Supplement: decoder iterations (max_iters 200 vs production 60, same seeds; NOT the production setting)", "", T["iters200"], "",
          "### Floor diagnostic (c1/floor_diag.py): the near-1% failures of the recipe codes are a few persistent trials (common random numbers)", "", T["floor_diag"], "",
          "## Capacity check (orchestrator's soft numbers)", "", T["capacity"], "",
          "## Structural", "", T["structural"], "", "## (a) BSC frontier", "", T["bsc"], "", "### (a) raw grid", "", T["bsc_grid"], "",
          "## (b) BIAWGN frontier", "", T["awgn"], "", "### (b) raw grid", "", T["awgn_grid"], "",
          "## (c) Erasure + error, fails/n", "", T["erasure"], "", "## Undetected (syndrome-valid wrong) decodes", "", T["undetected"], ""]
    (WORK / "TABLES-c1.md").write_text("\n".join(md))


if __name__ == "__main__":
    T, meta = main()
    write_md(T, meta)
    print("\n\n".join(T.values()))
