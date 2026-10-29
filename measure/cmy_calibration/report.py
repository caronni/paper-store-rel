"""R11 stage 6 — report.md and the figures, rendered from the JSON of record (never hand-edited).

What: tables T0-T10 of the protocol's fixed layout (controls; page information and LDPC per band-capture; cold
information, LDPC and gates; two captures; dead Y; weighting; single pose; decisions) and fig01-fig11 as PNG.
Why: one reproducible rendering of cmy-calibration.json.  How: reads the JSON, formats; PIL charts (plots.py).

    cd <repo> && PYTHONPATH=src:. \\
        env/bin/python -m measure.cmy_calibration --stage report
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from measure.cmy_calibration.config import ARTEFACTS, DECISION_BCS, RUNGS
from measure.cmy_calibration.plots import heatmaps, line_chart, map_curves

CH = ("fallback", "lo-first", "hi-first", "six-maps", "lo-first/cb", "hi-first/cb", "oracle")


def f(v: Any, d: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, dict) and "est" in v:
        return f"{v['est']:.{d}f} [{v['lo']:.{d}f}, {v['hi']:.{d}f}]" if v.get("lo") is not None else \
            f"{v['est']:.{d}f}"
    if isinstance(v, float):
        return f"{v:.{d}f}"
    return str(v)


def table(head: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(f(x) if not isinstance(x, str) else x for x in r) + " |" for r in rows]
    return "\n".join(out)


def chain_label(r: dict[str, Any]) -> str:
    return r["chain"] + ("/cb" if r.get("weighting") == "cb" else "")


def page_row(doc: dict[str, Any], bc: int, label: str, pop: str, form: str, feats: str = "F"
             ) -> dict[str, Any] | None:
    for r in doc["page"]:
        if (r["bc"] == bc and chain_label(r) == label and r["population"] == pop and r["form"] == form
                and r["replicate"] == 0 and r["features"] == feats and r["regime"] == "page"):
            return r
    return None


def ld(doc: dict[str, Any], **kw: Any) -> dict[str, Any] | None:
    for r in doc["ldpc"]:
        if all(r.get(k) == v for k, v in kw.items()):
            return r
    return None


def rate(r: dict[str, Any] | None) -> str:
    if r is None:
        return "—"
    return f"{r['successes']}/{r['T']} [{r['wilson']['lo']:.2f}, {r['wilson']['hi']:.2f}]"


def yld(doc: dict[str, Any], **kw: Any) -> dict[str, Any] | None:
    for r in doc["yield"]:
        if all(r.get(k) == v for k, v in kw.items()):
            return r["bits_per_tile"]
    return None


def t0(doc: dict[str, Any]) -> str:
    c = doc["controls"]
    rows = []
    for r in c.get("C1", []):
        rows.append(["C1", f"bc{r['bc']} {r['band']}", "confusion == committed", f"max|diff| {r['max_abs_diff']}; "
                     f"err hi/lo {r['err_hi']:.3f}/{r['err_lo']:.3f} %", r["n_cells"], str(r["pass"])])
    for name in ("C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"):
        if name in c:
            v = c[name]
            summary = {k: v[k] for k in v if k not in ("rows", "_rows", "devs", "fallback_null_I", "real")
                       and not isinstance(v[k], (list, dict))}
            rows.append([name, "", "see protocol", json.dumps(summary)[:160], "", str(v.get("pass"))])
    return "## T0 Controls\n\n" + table(["control", "band-capture", "expected", "measured", "n", "pass"], rows)


def t1(doc: dict[str, Any], feats: str = "F", title: str = "T1 Page information") -> str:
    out = [f"## {title}"]
    for bc in sorted({r["bc"] for r in doc["page"] if r["features"] == feats and r["regime"] == "page"}):
        rows = []
        for lab in CH:
            for pop in ("P-a", "P-b"):
                g = {form: page_row(doc, bc, lab, pop, form, feats) for form in ("hi", "lo", "hi|lo", "lo|hi")}
                if g["lo"] is None:
                    continue
                I = {k: (v["I"] if v else None) for k, v in g.items()}
                s1 = I["lo"]["est"] + I["hi|lo"]["est"] if I["lo"] and I["hi|lo"] else None
                s2 = I["hi"]["est"] + I["lo|hi"]["est"] if I["hi"] and I["lo|hi"] else None
                rows.append([lab, pop, I["hi"], I["lo"], I["hi|lo"], I["lo|hi"], s1, s2, g["lo"]["hard_err"],
                             g["lo"]["ece"], g["lo"]["slope"]["a"], g["lo"]["n_cells"]])
        out.append(f"\n### bc{bc}\n\n" + table(["chain", "pop", "I_hi", "I_lo", "I_hi|lo", "I_lo|hi",
                                                  "I_lo+I_hi|lo", "I_hi+I_lo|hi", "err_lo", "ECE_lo", "slope_lo",
                                                  "n"], rows))
    return "\n".join(out)


def t2(doc: dict[str, Any], feats: str = "F", title: str = "T2 Page LDPC") -> str:
    out = [f"## {title} (page-final; c3 controls: P-a)"]
    for bc in sorted({r["bc"] for r in doc["ldpc"] if r.get("regime") == "page" and r.get("features") == feats}):
        pop = "final" if bc in DECISION_BCS else "P-a"
        rows = []
        for lab in CH:
            chain, wt = (lab.split("/")[0], "cb") if "/" in lab else (lab, "-" if lab == "fallback" else "w")
            base = {"regime": "page", "bc": bc, "features": feats, "chain": chain, "weighting": wt}
            cells: list[Any] = [lab]
            fa = 0
            T = None
            for r in RUNGS:
                a = ld(doc, **base, population=pop, stream="lo", mode="any", rung=r)
                cells += [rate(a), rate(ld(doc, **base, population=pop, stream="lo", mode="bicm", rung=r)),
                          rate(ld(doc, **base, population=pop, stream="hi", mode="bicm", rung=r)),
                          rate(ld(doc, **base, population=pop, stream="hi", mode="any", rung=r)),
                          yld(doc, **base, population=pop, pair=f"{r}x{r}")]
                T = a["T"] if a else T
            cells.append(yld(doc, **base, population=pop, pair="r0775xr0700"))
            fa = sum(r_["false_accepts"] for r_ in doc["ldpc"] if r_.get("regime") == "page" and r_["bc"] == bc
                     and r_.get("chain") == chain and r_.get("weighting") == wt)
            rows.append(cells + [fa, T])
        head = ["chain"] + [f"{r} {k}" for r in RUNGS for k in ("lo any", "lo BICM", "hi BICM", "hi any",
                                                                 "bits/tile")] + ["r0775x0700", "FA", "T"]
        out.append(f"\n### bc{bc}\n\n" + table(head, rows))
    return "\n".join(out)


def t3(doc: dict[str, Any]) -> str:
    out = ["## T3 Cold information (maps: q(i), q(ii), dI = I(ALWAYS map) - I(fallback piece))"]
    for bc in sorted({r["bc"] for r in doc["coldstart"]}):
        rows = []
        for r in doc["coldstart"]:
            if r["bc"] == bc and r.get("map") and r["features"] == "F":
                rows.append([r["n"], r["map"], r["qualified_frac"]["i"], r["qualified_frac"]["ii"], r["dI"],
                             r["n_draws"]])
        out.append(f"\n### bc{bc}\n\n" + table(["n", "map", "q(i)", "q(ii)", "dI [CI]", "n_draws"], rows))
    return "\n".join(out)


def t4(doc: dict[str, Any]) -> str:
    out = ["## T4 Cold LDPC (lo any-stage, bits/tile at the uniform rung)"]
    for bc in sorted({r["bc"] for r in doc["ldpc"] if r.get("regime") == "cold"}):
        rows = []
        for n in (1, 2, 3, 4, 8):
            for chain, wt, pols in (("fallback", "-", ("NEVER",)), ("lo-first", "w", None), ("hi-first", "w", None),
                                    ("six-maps", "w", None)):
                for pol in pols or ("ALWAYS", "D1-DEFAULT", "FLOORS(i)", "FLOORS(ii)"):
                    base = {"regime": "cold", "bc": bc, "n": n, "features": "F", "chain": chain, "weighting": wt,
                            "policy": pol}
                    a = [ld(doc, **base, stream="lo", mode="any", rung=r) for r in RUNGS]
                    if not any(a):
                        continue
                    rows.append([n, f"{chain} {pol}"] + [x for r, ar in zip(RUNGS, a) for x in
                                                          (rate(ar), yld(doc, **base, pair=f"{r}x{r}"))])
        head = ["n", "policy"] + [f"{r} {k}" for r in RUNGS for k in ("lo any", "bits/tile")]
        out.append(f"\n### bc{bc}\n\n" + table(head, rows))
    return "\n".join(out)


def t5(doc: dict[str, Any]) -> str:
    rows = [[r["bc"], r["n"], r["chain"], r["valsrc"], r["gate"], r["refusal"], r["dust_only_share"],
             r["false_refusal"], r["false_adoption"], r.get("policy_yield"), r["n_draws"]]
            for r in doc["gates"] if r["features"] == "F" and r["bc"] in DECISION_BCS]
    return "## T5 Gates\n\n" + table(["bc", "n", "chain", "v", "gate", "refusal", "dust-only share",
                                      "false refusal", "false adoption", "policy yield", "n_draws"], rows)


def t6(doc: dict[str, Any]) -> str:
    out = ["## T6 Two captures (replicate 0, P-a information; page-final LDPC)"]
    for band in sorted({r["band"] for r in doc["twocapture"]}):
        rows = []
        for chain in ("fallback", "lo-first", "hi-first", "six-maps", "recal"):
            for form in ("hi", "lo", "hi|lo", "lo|hi"):
                g = {r["mode"]: r for r in doc["twocapture"] if r["band"] == band and r["chain"] == chain
                     and r["form"] == form and r["replicate"] == 0 and r["population"] == "P-a"}
                if not g:
                    continue
                s = g.get("SUMMED")
                bc = (s or next(iter(g.values())))["bc"][0]
                lo_any = [rate(ld(doc, regime="twocapture", bc=bc, population="final", chain=chain,
                                  capmode="SUMMED", stream="lo", mode="any", rung=r)) for r in RUNGS]
                rows.append([chain, form] + [g[m]["I"] if m in g else None for m in
                                             ("SUMMED", "SUM-OF-FORMS", "BEST-SINGLE", "RECAL-ORACLE")]
                            + [s["dI_vs_sum_of_forms"] if s else None, s["slope"] if s else None,
                               str(s["loses"]) if s else "—"] + lo_any)
        out.append(f"\n### {band}\n\n" + table(["chain", "form", "SUMMED", "SUM-OF-FORMS", "BEST-SINGLE", "RECAL",
                                                  "dI SUMMED-SOF", "slope", "loses"] +
                                                 [f"lo any {r}" for r in RUNGS], rows))
    return "\n".join(out)


def t7(doc: dict[str, Any]) -> str:
    rows = []
    for r in doc["deadY"]:
        if r.get("replicate", 0) != 0:
            continue
        reg = "deadY-page" if r["regime"] == "page" else "deadY-cold"
        succ = [rate(ld(doc, regime=reg, bc=r["bc"], n=r.get("n"), arm=r["arm"], stream="hi", mode="bicm",
                        rung=rr)) for rr in RUNGS]
        rows.append([r["bc"], r["regime"], r.get("n"), r["arm"], r["I_hi"]] + succ +
                    [r.get("detect_rate", r.get("detect")), r.get("false_collapse_rate")])
    return "## T7 Dead Y\n\n" + table(["bc", "regime", "n", "arm", "I_hi [CI]"] + [f"hi {r}" for r in RUNGS] +
                                      ["detect", "false collapse"], rows)


def t8(doc: dict[str, Any]) -> str:
    rows = []
    for bc in DECISION_BCS:
        for chain, form in (("lo-first", "lo"), ("hi-first", "hi")):
            w, cb = page_row(doc, bc, chain, "P-a", form), page_row(doc, bc, chain + "/cb", "P-a", form)
            if w and cb:
                lo_any = [rate(ld(doc, regime="page", bc=bc, features="F", population="final", chain=chain,
                                  weighting=x, stream="lo", mode="any", rung=r)) for x in ("w", "cb") for r in RUNGS]
                rows.append([bc, "page", f"L_{form}", w["I"], cb["I"], w["I"]["est"] - cb["I"]["est"]] + lo_any)
        for r in doc["coldstart"]:
            if r["bc"] == bc and r.get("weighting") == "w-cb" and r["features"] == "F":
                rows.append([bc, f"cold n{r['n']}", f"{r['chain']} {r['form']}", None, None,
                             r["dI_w_minus_cb"]] + ["—"] * 6)
    return "## T8 Weighting (state-balanced w vs class-balanced cb)\n\n" + table(
        ["bc", "regime", "map", "I w", "I cb", "dI"] + [f"lo any {x} {r}" for x in ("w", "cb") for r in RUNGS], rows)


def t10(doc: dict[str, Any]) -> str:
    d = doc.get("decisions")
    if d is None and doc.get("decisions_unratified") is None:
        return f"## T10 Decisions\n\nNo verdict: the run stopped on control {doc.get('stopped_by')}."
    out = ["## T10 Decisions"]
    if d is None:
        d = doc["decisions_unratified"]
        out.append(f"\nNO VERDICT — controls failed: {doc.get('failed_controls')}. The tables below are the rules' "
                   "reading of a diagnostic run, unratified.")
    for k in ("D1", "D1b", "D2", "D3", "D4"):
        v = d[k]
        out.append(f"\n### {k}: {v.get('verdict', v.get('source'))}\n")
        if k == "D1":
            out.append(table(["cell", "use", "informative"] + list(("fallback", "lo-first", "hi-first", "six-maps")),
                             [[c["label"], c["use"], str(c["informative"])] +
                              [f"{c[ch]['k']}/{c[ch]['T']}" if ch in c else "—"
                               for ch in ("fallback", "lo-first", "hi-first", "six-maps")] for c in v["cells"]]))
        out.append("\n```\n" + json.dumps({kk: vv for kk, vv in v.items() if kk not in ("cells",)}, indent=1,
                                          default=str)[:6000] + "\n```")
    out.append("\n### Synthesis\n\n```\n" + json.dumps(d["synthesis"], indent=1, default=str) + "\n```")
    return "\n".join(out)


def figures(doc: dict[str, Any], art: Path) -> list[str]:
    made = []
    c1 = {r["bc"]: r for r in doc["controls"].get("C1", [])}
    mats = []
    for bc in (0, 1, 3):
        if bc in c1:
            mats += [(f"bc{bc} committed", np.array(c1[bc]["confusion_committed"])),
                     (f"bc{bc} reproduced", np.array(c1[bc]["confusion_reproduced"]))]
    if mats:
        heatmaps(art / "fig01-anchors.png", "C1 loo confusions (row %)", mats, ["W", "C", "M", "Y"])
        made.append("fig01-anchors.png")
    forms = ("hi", "lo", "hi|lo=0", "hi|lo=1", "lo|hi=0", "lo|hi=1", "hi|lo", "lo|hi")
    for bc in sorted({r["bc"] for r in doc["page"] if r["regime"] == "page"}):
        ser = []
        for lab in CH:
            ys = [page_row(doc, bc, lab, "P-a", fm) for fm in forms]
            if any(ys):
                ser.append({"label": lab, "y": [y["I"]["est"] if y else None for y in ys],
                            "lo": [y["I"]["lo"] if y else None for y in ys],
                            "hi": [y["I"]["hi"] if y else None for y in ys]})
        line_chart(art / f"fig02-page-info-{bc}.png", f"page information P-a, bc{bc}", forms, ser, "I (bits)")
        rel = [{"label": lab, "y": [(page_row(doc, bc, lab, "P-a", fm) or {}).get("slope", {}).get("a")
                                    for fm in forms]} for lab in CH]
        line_chart(art / f"fig03-reliability-{bc}.png", f"reliability slope a (1 = calibrated), bc{bc}", forms, rel,
                   "a")
        made += [f"fig02-page-info-{bc}.png", f"fig03-reliability-{bc}.png"]
        ser = []
        for lab in CH[:4]:
            wt = "-" if lab == "fallback" else "w"
            pop = "final" if bc in DECISION_BCS else "P-a"
            rs = [ld(doc, regime="page", bc=bc, features="F", population=pop, chain=lab, weighting=wt, stream="lo",
                     mode="any", rung=r) for r in RUNGS]
            ser.append({"label": f"{lab} lo any", "y": [r["successes"] / r["T"] if r else None for r in rs],
                        "lo": [r["wilson"]["lo"] if r else None for r in rs],
                        "hi": [r["wilson"]["hi"] if r else None for r in rs]})
        line_chart(art / f"fig04-ldpc-page-{bc}.png", f"page LDPC, binding stream lo, bc{bc}", RUNGS, ser,
                   "success", (0.0, 1.0))
        made.append(f"fig04-ldpc-page-{bc}.png")
    for band in sorted({r["band"] for r in doc["twocapture"]}):
        ser = []
        for mode in ("SUMMED", "SUM-OF-FORMS", "BEST-SINGLE", "RECAL-ORACLE"):
            ys = []
            for fm in forms:
                g = [r for r in doc["twocapture"] if r["band"] == band and r["mode"] == mode and r["form"] == fm
                     and r["chain"] in ("lo-first", "recal") and r["replicate"] == 0 and r["population"] == "P-a"]
                ys.append(g[0]["I"]["est"] if g else None)
            ser.append({"label": f"{mode} (lo-first)", "y": ys})
        line_chart(art / f"fig05-twocap-{band}.png", f"two captures {band}", forms, ser, "I (bits)")
        made.append(f"fig05-twocap-{band}.png")
    for bc in sorted({r["bc"] for r in doc["coldstart"]}):
        ser = []
        maps = sorted({r["map"] for r in doc["coldstart"] if r.get("map") and r["bc"] == bc})
        sizes = [1, 2, 3, 4, 8]
        for m in maps:
            rs = {r["n"]: r for r in doc["coldstart"] if r.get("map") == m and r["bc"] == bc and r["features"] == "F"}
            ser.append({"label": m, "y": [rs[n]["dI"]["est"] if n in rs else None for n in sizes],
                        "lo": [rs[n]["dI"]["lo"] if n in rs else None for n in sizes],
                        "hi": [rs[n]["dI"]["hi"] if n in rs else None for n in sizes]})
            ser.append({"label": f"{m} q(i)", "y": [rs[n]["qualified_frac"]["i"] if n in rs else None
                                                    for n in sizes]})
        line_chart(art / f"fig06-coldstart-dI-{bc}.png", f"cold dI and q(i), bc{bc}", [str(n) for n in sizes], ser,
                   "dI / q")
        ys = []
        for chain, wt, pol in (("fallback", "-", "NEVER"), ("lo-first", "w", "ALWAYS"), ("lo-first", "w", "D1-DEFAULT"),
                               ("lo-first", "w", "FLOORS(i)"), ("lo-first", "w", "FLOORS(ii)")):
            v = [yld(doc, regime="cold", bc=bc, n=n, features="F", chain=chain, weighting=wt, policy=pol,
                     pair="r0775xr0775") for n in sizes]
            ys.append({"label": f"{chain} {pol}", "y": [x["est"] if x else None for x in v],
                       "lo": [x["lo"] if x else None for x in v], "hi": [x["hi"] if x else None for x in v]})
        line_chart(art / f"fig07-coldstart-yield-{bc}.png", f"cold tile yield r0775, bc{bc}", [str(n) for n in sizes],
                   ys, "bits/tile")
        gs = []
        for g in ("G1", "G2", "G3"):
            rs = {r["n"]: r for r in doc["gates"] if r["bc"] == bc and r["gate"] == g and r["chain"] == "lo-first"
                  and r["valsrc"] == "i" and r["features"] == "F"}
            gs.append({"label": f"{g} refusal (lo-first, i)", "y": [rs[n]["refusal"]["est"] if n in rs else None
                                                                   for n in sizes]})
        line_chart(art / f"fig08-gates-{bc}.png", f"gate refusal, bc{bc}", [str(n) for n in sizes], gs, "rate",
                   (0.0, 1.0))
        made += [f"fig06-coldstart-dI-{bc}.png", f"fig07-coldstart-yield-{bc}.png", f"fig08-gates-{bc}.png"]
    for bc in sorted({r["bc"] for r in doc["deadY"]}):
        ser = []
        for arm in ("a", "b", "c", "c'"):
            xs = ["page", "1", "2", "3", "4", "8"]
            v = []
            for x in xs:
                g = [r for r in doc["deadY"] if r["bc"] == bc and r["arm"] == arm and r.get("replicate", 0) == 0
                     and ((x == "page" and r["regime"] == "page") or (r["regime"] == "cold" and str(r["n"]) == x))]
                v.append(g[0]["I_hi"]["est"] if g else None)
            ser.append({"label": arm, "y": v})
        line_chart(art / f"fig09-deadY-{bc}.png", f"dead Y: I_hi by arm, bc{bc}", ["page", "1", "2", "3", "4", "8"],
                   ser, "I_hi")
        made.append(f"fig09-deadY-{bc}.png")
    maps = doc.get("maps_B3") or {}
    if maps:
        curves = [(f"{k} {m} {w}", np.array(v["score_nodes"]), np.array(v["probability_nodes"]))
                  for k, mm in maps.items() for m, ww in mm.items() for w, v in ww.items() if v]
        map_curves(art / "fig10-pava-maps-B3.png", "B3 marginal maps: weighted vs class-balanced", curves)
        made.append("fig10-pava-maps-B3.png")
    c6 = doc["controls"].get("C6", {})
    c5 = doc["controls"].get("C5", {})
    ser = []
    if c6.get("devs"):
        keys = list(c6["devs"])
        ser.append({"label": "S1 chain - Bayes (bits)", "y": [c6["devs"][k] for k in keys]})
        line_chart(art / "fig11-controls.png", f"S1 deviations from Bayes; C5 pass {c5.get('pass')}",
                   [k.replace(" ", "\n")[:14] for k in keys], ser, "dI")
        made.append("fig11-controls.png")
    return made


def render(art: Path = ARTEFACTS, name: str = "cmy-calibration.json") -> Path:
    doc = json.loads((art / name).read_text())
    figs = figures(doc, art)
    meta = doc["meta"]
    parts = [f"# R11 calibration measurement — {meta['protocol_version']}",
             f"\nGenerated from `{name}` (head {meta.get('head_sha')}, code {meta['code_sha256'].get('_all', '')[:16]},"
             f" wall {meta.get('wall_s', 0) / 60:.1f} min). Params: `{json.dumps(meta['params'])}`.",
             "\nFigures: " + ", ".join(figs), t0(doc), t1(doc), t2(doc), t3(doc), t4(doc), t5(doc), t6(doc), t7(doc),
             t8(doc), t1(doc, "F1", "T9 Single pose — information"), t2(doc, "F1", "T9 Single pose — LDPC"), t10(doc),
             "\n## Deviations\n\n" + "\n".join(f"- {d}" for d in doc.get("deviations", []))]
    out = art / ("report.md" if name == "cmy-calibration.json" else name.replace(".json", ".md"))
    out.write_text("\n\n".join(parts) + "\n")
    return out

