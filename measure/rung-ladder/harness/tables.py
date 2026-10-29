# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/harness/tables.py
"""results.json + structure.json + build_log.json -> TABLES.md (and tables.json
with the markdown strings)."""
from __future__ import annotations
import json, math, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import codes, channels as ch  # noqa: E402
WORK = codes.WORK
h2 = ch.h2


def interp_x(pts: list[tuple[float, float, int]], target: float, harder_is_plus: bool) -> float | None:
    """pts = [(x, bler, n)], solve BLER(x) = target by linear interpolation in log BLER
    along the hardness direction. 0/n is floored at 0.5/n for the interpolation."""
    s = sorted(pts, key=lambda t: t[0] if harder_is_plus else -t[0])   # easy -> hard
    for (x0, b0, n0), (x1, b1, n1) in zip(s, s[1:]):
        if b0 <= target <= b1 and b1 > 0:
            lb0 = math.log(max(b0, 0.5 / n0)); lb1 = math.log(b1); lt = math.log(target)
            if lb1 == lb0:
                return x0
            return x0 + (x1 - x0) * (lt - lb0) / (lb1 - lb0)
    return None


def fmt(x, d=4):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{d}f}"


def main():
    res = json.loads((WORK / "results.json").read_text())
    st = json.loads((WORK / "structure.json").read_text())
    bl = {r["rate_id"]: r for r in json.loads((WORK / "build_log.json").read_text())}
    meta = res["meta"]; P = res["points"]
    rids = [r for r in codes.ALL if r in meta["codes"]]
    label = {r: ("existing" if r in codes.EXISTING else "candidate" if r in codes.CANDIDATES else "VARIANT") for r in rids}
    T = {}
    # --- structural
    L = ["| code | kind | k | R | kb/mb | nh×deg | restart | draw s | edges | chk deg min..max (mean) | checks w/o info edge | var deg hist | girth>4 | min w1 | min w2 (#≤8) | user bits p100 / p120 | S(p120) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rids:
        s = st[r]; b = bl.get(r, {})
        restart = b.get("restart", json.loads(((Path(__file__).resolve().parents[3] / "src/holo/core/ldpc/data") / f"{r}.json").read_text())["restart"] if r in codes.EXISTING else "?")
        vh = ", ".join(f"{d}:{c}" for d, c in sorted(s["var_deg_hist"].items(), key=lambda t: int(t[0])))
        L.append(f"| {r} | {label[r]} | {s['k_bits']} | {s['rate']:.4f} | {s['kb']}/{s['mb']} | {s['nh']}×{s['heavy_deg']} | {restart} | {b.get('seconds', 'frozen')} | {s['n_edges']} | "
                 f"{s['chk_deg_min']}..{s['chk_deg_max']} ({s['chk_deg_mean']:.2f}) | {s['n_chk_no_info_edge']} ({100*s['frac_chk_no_info_edge']:.1f}%) | {vh} | {s['girth_gt4']} (max {s['HHt_offdiag_max']}) | "
                 f"{s['min_w1']} | {s['min_w2']} ({s['n_w2_le8']}) | {s['user_bits_p100']} / {s['user_bits_p120']} | {s['S_p120']} |")
    T["structural"] = "\n".join(L)
    # --- BSC
    L = ["| code | kind | R | p_cap | p@1% | p@10% | gap@1% (bits) | p@1% detected-only | gap det-only | lowest p with an undetected | iters@1% (all / ok) | walk points | undetected/trials |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    grid_rows = ["| code | p : fails/n (undet) [mean iters] |", "|---|---|"]
    for r in rids:
        pts = [p for p in P if p["rid"] == r and p["channel"] == "bsc"]
        xs = [(p["params"]["p"], p["bler"], p["n"]) for p in pts]
        p1 = interp_x(xs, 0.01, True); p10 = interp_x(xs, 0.10, True)
        R = meta["capacity"][r]["rate"]; pc = meta["capacity"][r]["p_cap"]
        gap = (1 - h2(p1)) - R if p1 is not None else None
        near = min(pts, key=lambda p: abs(p["params"]["p"] - p1)) if p1 is not None else None
        it = f"{near['mean_iters']:.1f} / {fmt(near['mean_iters_ok'], 1)} (p={near['params']['p']})" if near else "—"
        und = sum(p["undetected"] for p in pts); nt = sum(p["n"] for p in pts)
        xd = [(p["params"]["p"], (p["fails"] - p["undetected"]) / p["n"], p["n"]) for p in pts]
        p1d = interp_x(xd, 0.01, True); gapd = (1 - h2(p1d)) - R if p1d is not None else None
        fl = [p["params"]["p"] for p in pts if p["undetected"]]
        L.append(f"| {r} | {label[r]} | {R:.4f} | {pc:.4f} | {fmt(p1)} | {fmt(p10)} | {fmt(gap, 3)} | {fmt(p1d)} | {fmt(gapd, 3)} | {fmt(min(fl), 3) if fl else '—'} | {it} | {len(pts)} | {und}/{nt} |")
        grid_rows.append(f"| {r} | " + "; ".join(f"{p['params']['p']:.3f}: {p['fails']}/{p['n']}" + (f" ({p['undetected']}u)" if p['undetected'] else "") + f" [{p['mean_iters']:.0f}]" for p in sorted(pts, key=lambda q: q['params']['p'])) + " |")
    T["bsc"] = "\n".join(L); T["bsc_grid"] = "\n".join(grid_rows)
    # --- AWGN
    L = ["| code | kind | R | Es/N0 Shannon (dB) | Es/N0@1% (dB) | gap (dB) | Es/N0@1% detected-only | gap det-only (dB) | Es/N0@10% | Eb/N0@1% (dB) | walk points | undetected/trials |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    grid_rows = ["| code | Es/N0 dB : fails/n (undet) [mean iters] |", "|---|---|"]
    for r in rids:
        pts = [p for p in P if p["rid"] == r and p["channel"] == "awgn"]
        xs = [(p["params"]["esn0_db"], p["bler"], p["n"]) for p in pts]
        e1 = interp_x(xs, 0.01, False); e10 = interp_x(xs, 0.10, False)
        R = meta["capacity"][r]["rate"]; sh = meta["capacity"][r]["esn0_shannon_db"]
        und = sum(p["undetected"] for p in pts); nt = sum(p["n"] for p in pts)
        eb = e1 - 10 * math.log10(R) if e1 is not None else None
        xd = [(p["params"]["esn0_db"], (p["fails"] - p["undetected"]) / p["n"], p["n"]) for p in pts]
        e1d = interp_x(xd, 0.01, False)
        L.append(f"| {r} | {label[r]} | {R:.4f} | {sh:.3f} | {fmt(e1, 3)} | {fmt(e1 - sh if e1 is not None else None, 2)} | {fmt(e1d, 3)} | {fmt(e1d - sh if e1d is not None else None, 2)} | {fmt(e10, 3)} | {fmt(eb, 3)} | {len(pts)} | {und}/{nt} |")
        grid_rows.append(f"| {r} | " + "; ".join(f"{p['params']['esn0_db']:.2f}: {p['fails']}/{p['n']}" + (f" ({p['undetected']}u)" if p['undetected'] else "") + f" [{p['mean_iters']:.0f}]" for p in sorted(pts, key=lambda q: q['params']['esn0_db'])) + " |")
    T["awgn"] = "\n".join(L); T["awgn_grid"] = "\n".join(grid_rows)
    # --- erasure + error
    pts = [p for p in P if p["channel"] == "eras"]
    eps_g = sorted({p["params"]["eps"] for p in pts}); p_g = sorted({p["params"]["p"] for p in pts})
    L = ["| code | R | p | " + " | ".join(f"ε={e}" for e in eps_g) + " | max ε @ BLER≤1% | (1−ε)(1−h2(p)) − R at that ε |", "|---|---|---|" + "---|" * len(eps_g) + "---|---|"]
    for r in rids:
        R = meta["capacity"][r]["rate"]
        for pp in p_g:
            row = {p["params"]["eps"]: p for p in pts if p["rid"] == r and p["params"]["p"] == pp}
            cells = []
            for e in eps_g:
                q = row.get(e)
                cells.append("—" if q is None else f"{q['fails']}/{q['n']}" + (f" ({q['undetected']}u)" if q["undetected"] else ""))
            ok = [e for e in eps_g if e in row and row[e]["bler"] <= 0.01]
            me = max(ok) if ok else None
            marg = (1 - me) * (1 - h2(pp)) - R if me is not None else None
            L.append(f"| {r} | {R:.3f} | {pp} | " + " | ".join(cells) + f" | {fmt(me, 1)} | {fmt(marg, 3)} |")
    T["erasure"] = "\n".join(L)
    # --- accommodation
    pts = [p for p in P if p["channel"] == "accom"]
    L = ["| code | k | variant | transmitted bits | user bits/tile | " + "BLER at p (fails/n) …" + " |", "|---|---|---|---|---|---|"]
    for r in rids:
        rp = [p for p in pts if p["rid"] == r]
        if not rp:
            continue
        k = codes.spec(r).k_bits
        for v, tx, ub in (("mother", 4096, k - 32), ("shorten", 3976, k - 32 - 120), ("punct_last", 3976, k - 32), ("punct_even", 3976, k - 32)):
            vv = sorted([p for p in rp if p["params"]["variant"] == v], key=lambda q: q["params"]["p"])
            L.append(f"| {r} | {k} | {v} | {tx} | {ub} | " + "; ".join(f"p={p['params']['p']:.3f}: {p['fails']}/{p['n']}" + (f" ({p['undetected']}u)" if p['undetected'] else "") + f" [{p['mean_iters']:.0f} it]" for p in vv) + " |")
    T["accom"] = "\n".join(L)
    # --- recorded battery replicate
    pts = [p for p in P if p["channel"] == "record"]
    recorded = {("r0700", 0.035): "1.5–1.8% (gate ≤3/200)", ("r0700", 0.015): "0/200", ("r0550", 0.055): "clean (0/100 gate ≤1)", ("r0547", 0.055): "(not recorded; r0550 twin)",
                ("r0625", 0.045): "0.5% (gate ≤2/100)", ("r0775", 0.020): "0.5% (gate ≤2/100)", ("r0850", 0.010): "3.5%", ("r0850", 0.005): "(gate ≤1/100)"}
    L = ["| code | p | recorded (FEC-DESIGN / test gate) | replicate mag 4.0, test seeds: fails/n (undet) | this sweep's log-LLR grid at same p |", "|---|---|---|---|---|"]
    for p in sorted(pts, key=lambda q: (codes.ALL.index(q["rid"]), q["params"]["p"])):
        r = p["rid"]; pp = p["params"]["p"]
        same = [q for q in P if q["rid"] == r and q["channel"] == "bsc" and abs(q["params"]["p"] - pp) < 1e-9]
        s = f"{same[0]['fails']}/{same[0]['n']}" if same else "(not on grid)"
        L.append(f"| {r} | {pp} | {recorded.get((r, pp), '')} | {p['fails']}/{p['n']} ({p['undetected']}u) | {s} |")
    T["record"] = "\n".join(L)
    # --- undetected summary
    L = ["| code | channel | undetected | of trials | at points |", "|---|---|---|---|---|"]
    for r in rids:
        for c in ("bsc", "awgn", "eras", "accom", "record"):
            pp = [p for p in P if p["rid"] == r and p["channel"] == c]
            u = sum(p["undetected"] for p in pp)
            if u:
                L.append(f"| {r} | {c} | {u} | {sum(p['n'] for p in pp)} | " + "; ".join(f"{p['params']}: {p['undetected']}/{p['n']}" for p in pp if p["undetected"]) + " |")
    if len(L) == 2:
        L.append("| (none) | | 0 | " + str(sum(p["n"] for p in P)) + " | |")
    T["undetected"] = "\n".join(L)
    (WORK / "tables.json").write_text(json.dumps(T, indent=1))
    md = [f"# Rung-ladder measurement — {WORK.name}", "",
          f"Command: `{meta['command']}`  ", f"Trials/point: {meta['trials_per_point']} (chunks of {meta['chunk']}), workers {meta['workers']}, wall {meta['wall_seconds']:.0f} s.  ",
          f"Seeds: trial t uses `np.random.default_rng(base + t)`, base = {meta['seed_bases']} (the 'record' channel uses the test's own 50_000/60_000 bases and magnitude 4.0).  ",
          "Decoder: `holo.core.ldpc.decode.decode` (production; min-sum α=0.8, 60 iters + one sum-product retry). Hard BSC LLR = ±log((1−p)/p) (tests/test_ldpc.py `_hard_llr` uses a FIXED magnitude 4.0, default, 8.0 in one identity check). Failure = not syndrome_ok or hard ≠ codeword; undetected = syndrome_ok and hard ≠ codeword.  ",
          "Walks: (a) from the BSC-capacity grid point (0.005 grid) down until two consecutive 0/200, up until BLER ≥ 0.5; (b) same on a 0.25 dB Es/N0 grid from the Shannon point. p@1%/p@10% by linear interpolation in log BLER (0/n floored at 0.5/n). Codes: existing six (frozen data), six candidates (frozen recipe), four VARIANTS (not the recipe).", "",
          "## Structural", "", T["structural"], "", "## (a) BSC frontier", "", T["bsc"], "", "### (a) raw grid", "", T["bsc_grid"], "",
          "## (b) BIAWGN frontier", "", T["awgn"], "", "### (b) raw grid", "", T["awgn_grid"], "",
          "## (c) Erasure + error (fragment regime), fails/n", "", T["erasure"], "",
          "## (d) Shorten vs puncture at the 120-site accommodation", "", T["accom"], "",
          "## (e) Recorded-battery cross-check", "", T["record"], "", "## Undetected (syndrome-valid wrong) decodes", "", T["undetected"], "",
          "### Undetected diagnostic (one fixed seed per code hits one low-weight word; common random numbers make it persist down the walk)", "", "```", (WORK / "undetected_diag.txt").read_text().strip(), "```", "",
          "## Run record", "", "Run 1 (same command) was ABORTED at ~13 min: an unrounded float key in `Walk.__init__` re-submitted r0625's hard BSC point on every completion (identical seeds, identical counts, never-terminating loop); fixed in harness/sweep.py line 51, run 2 is the one reported here (logs: run1_aborted.log, sweep_progress_run1_aborted.log). Build: harness/build.py (0.4 s, all ten at restart 0). Structure: harness/structure.py (2.4 s). Smoke: `sweep.py --smoke --workers 8` (9 s, results_smoke.json).", ""]
    (WORK / "TABLES.md").write_text("\n".join(md))
    print("wrote", WORK / "TABLES.md")


if __name__ == "__main__":
    main()
