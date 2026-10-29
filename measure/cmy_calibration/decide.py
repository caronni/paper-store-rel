"""R11 — the pre-registered reading rules (the protocol's 'Decision map'), coded before the run and hashed into
meta.code_sha256.

What: decide(doc) -> {D1, D1b, D2, D3, D4, synthesis} from the JSON of record (its ldpc rows carry each cell's
per-trial outcomes as packed bits, so every paired bootstrap is rebuilt here).  Cell comparisons: X beats Y in a
cell iff their Wilson 95 % intervals are disjoint with X higher; a cell where every arm is >= 0.99 or every arm
is <= 0.01 is not informative; X dominates Y iff X beats Y in >= 1 cell and Y beats X in none.  The exact
McNemar p against the fallback is reported per cell and never decides.
D1 reads the binding stream's (lo) any-stage success: use (a) = page-final on band-captures 0-3 at three rungs
plus the two-capture U12 SUMMED page-final (six-maps: SUM-OF-FORMS, its only summed mode); use (b) = cold start
n = 1, 2, 3 under D1-DEFAULT.  Undominated survivors are separated by the half-and-half tile-yield score (mean
bits per tile at the uniform rung over each use's cells, averaged) with a paired trial bootstrap; ties break to
fewer stored columns, then lo-first, hi-first, fallback.  D1b weighted vs class-balanced; D2 dead-Y (a) vs (b);
D3 floors and validation source; D4 the region gate; the synthesis answers the owner's question.
Why: pre-registration.  How: pure functions; the bootstrap rng is default_rng([MASTER_SEED, 10, 99, k]).
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from measure.cmy_calibration.config import DECISION_BCS, FOUNTAIN_BITS, MASTER_SEED, RUNGS
from measure.cmy_calibration.estimators import mcnemar_exact
from measure.cmy_calibration.ldpc_sim import unpack_bits

CHAINS = ("fallback", "lo-first", "hi-first", "six-maps")
COLUMNS = {"fallback": 3, "lo-first": 3, "hi-first": 3, "six-maps": 6}
TIE_ORDER = ("lo-first", "hi-first", "fallback", "six-maps")
B_DECIDE = 2000
Cell = dict[str, Any]


def wt(chain: str) -> str:
    return "-" if chain == "fallback" else "w"


def index_ldpc(rows: list[dict[str, Any]]) -> dict[tuple[Any, ...], dict[str, Any]]:
    out = {}
    for r in rows:
        key = (r.get("regime"), r.get("bc"), r.get("n"), r.get("features"), r.get("population"), r.get("chain"),
               r.get("weighting"), r.get("policy"), r.get("capmode"), r.get("arm"), r["stream"], r["mode"], r["rung"])
        out[key] = r
    return out


def get(ix: dict[tuple[Any, ...], dict[str, Any]], **kw: Any) -> dict[str, Any] | None:
    key = (kw.get("regime"), kw.get("bc"), kw.get("n"), kw.get("features"), kw.get("population"), kw.get("chain"),
           kw.get("weighting"), kw.get("policy"), kw.get("capmode"), kw.get("arm"), kw["stream"], kw["mode"],
           kw["rung"])
    return ix.get(key)


def bits(row: dict[str, Any] | None) -> np.ndarray | None:
    return None if row is None else unpack_bits(row["outcomes"], row["T"])


# ---------------------------------------------------------------- cells

def d1_cells(ix: dict[tuple[Any, ...], dict[str, Any]], features: str = "F", uses: tuple[str, ...] = ("a", "b"),
             bcs: tuple[int, ...] = DECISION_BCS, chains: tuple[str, ...] = CHAINS,
             weighting: Callable[[str], str] = wt, page_population: str = "final") -> list[Cell]:
    """Each cell: {'use', 'label', 'rung', arms: chain -> (lo any bits, hi any bits)}."""
    cells: list[Cell] = []
    for use in uses:
        specs: list[tuple[str, dict[str, Any], str]] = []
        if use == "a":
            for bc in bcs:
                for r in RUNGS:
                    specs.append((f"page bc{bc} {r}", {"regime": "page", "bc": bc, "features": features,
                                                       "population": page_population, "policy": "D1-DEFAULT"}, r))
            if features == "F" and page_population == "final":
                for r in RUNGS:
                    specs.append((f"twocap U12 {r}", {"regime": "twocapture", "bc": 1, "features": "F",
                                                      "population": "final", "policy": "D1-DEFAULT"}, r))
        else:
            for n in (1, 2, 3):
                for bc in bcs:
                    for r in RUNGS:
                        specs.append((f"cold n{n} bc{bc} {r}", {"regime": "cold", "bc": bc, "n": n,
                                                                  "features": features, "population": "cold"}, r))
        for label, base, r in specs:
            arms = {}
            for c in chains:
                kw = dict(base, chain=c, weighting=weighting(c))
                if base["regime"] == "cold":
                    kw["policy"] = "NEVER" if c == "fallback" else "D1-DEFAULT"
                if base["regime"] == "twocapture":
                    kw["capmode"] = "SUM-OF-FORMS" if c == "six-maps" else "SUMMED"
                lo = bits(get(ix, **kw, stream="lo", mode="any", rung=r))
                hi = bits(get(ix, **kw, stream="hi", mode="any", rung=r))
                if lo is not None and hi is not None:
                    arms[c] = (lo, hi)
            if len(arms) >= 2:
                cells.append({"use": use, "label": label, "rung": r, "arms": arms})
    return cells


def wilson(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def informative(cell: Cell, which: int = 0) -> bool:
    rates = [v[which].mean() for v in cell["arms"].values()]
    return not (all(x >= 0.99 for x in rates) or all(x <= 0.01 for x in rates))


def beats(cell: Cell, x: str, y: str, which: int = 0) -> bool:
    if x not in cell["arms"] or y not in cell["arms"] or not informative(cell, which):
        return False
    a, b = cell["arms"][x][which], cell["arms"][y][which]
    return wilson(int(a.sum()), a.size)[0] > wilson(int(b.sum()), b.size)[1]


def dominance(cells: list[Cell], chains: tuple[str, ...], which: int = 0) -> dict[str, Any]:
    beat = {(x, y): [c["label"] for c in cells if beats(c, x, y, which)] for x in chains for y in chains if x != y}
    dominated = {y: [x for x in chains if x != y and beat[(x, y)] and not beat[(y, x)]] for y in chains}
    return {"beats": {f"{x}>{y}": v for (x, y), v in beat.items() if v}, "dominated_by": dominated}


def cell_yield(cell: Cell, chain: str) -> np.ndarray:
    lo, hi = cell["arms"][chain]
    s = FOUNTAIN_BITS[cell["rung"]]
    return s * hi.astype(np.float64) + s * lo.astype(np.float64)


def score(cells: list[Cell], chain: str, idx: dict[int, np.ndarray] | None = None) -> float:
    """Half-and-half: mean over use-(a) cells and over use-(b) cells of the mean tile yield, averaged."""
    parts = []
    for use in ("a", "b"):
        vals = []
        for i, c in enumerate(cells):
            if c["use"] != use or chain not in c["arms"]:
                continue
            y = cell_yield(c, chain)
            vals.append(float(y[idx[i]].mean()) if idx is not None else float(y.mean()))
        if vals:
            parts.append(float(np.mean(vals)))
    return float(np.mean(parts)) if parts else float("nan")


def paired_lead(cells: list[Cell], x: str, y: str, k: int) -> dict[str, float]:
    rng = np.random.default_rng([MASTER_SEED, 10, 99, k])
    lead = score(cells, x) - score(cells, y)
    boots = []
    for _ in range(B_DECIDE):
        idx = {i: rng.integers(0, c["arms"][x][0].size, c["arms"][x][0].size) for i, c in enumerate(cells)
               if x in c["arms"]}
        boots.append(score(cells, x, idx) - score(cells, y, idx))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return {"est": lead, "lo": float(lo), "hi": float(hi)}


def pick(cells: list[Cell], chains: tuple[str, ...], k: int = 0) -> dict[str, Any]:
    """Dominance, then the half-and-half yield lead, then the tie order."""
    dom = dominance(cells, chains)
    left = [c for c in chains if not dom["dominated_by"][c]]
    out: dict[str, Any] = {"dominance": dom, "undominated": left}
    if len(left) == 1:
        out.update(winner=left[0], how="the only undominated chain")
        return out
    if not left:
        left = list(chains)
    scores = {c: score(cells, c) for c in left}
    ranked = sorted(left, key=lambda c: -scores[c])
    out["scores"] = scores
    lead = paired_lead(cells, ranked[0], ranked[1], k)
    out["lead"] = {"leader": ranked[0], "runner_up": ranked[1], **lead}
    if lead["lo"] > 0:
        out.update(winner=ranked[0], how="tile-yield lead with paired CI excluding 0")
        return out
    tie = sorted(left, key=lambda c: (COLUMNS[c], TIE_ORDER.index(c)))
    out.update(winner=tie[0], how="tie: fewest stored columns, then lo-first, hi-first")
    return out


# ---------------------------------------------------------------- D1

def page_ilo(doc: dict[str, Any], chain: str, bc: int) -> dict[str, float] | None:
    for r in doc["page"]:
        if (r["bc"] == bc and r["chain"] == chain and r["weighting"] == wt(chain) and r["population"] == "P-a"
                and r["replicate"] == 0 and r["features"] == "F" and r["form"] == "lo" and r["regime"] == "page"):
            return r["I"]
    return None


def d1(doc: dict[str, Any], ix: dict[tuple[Any, ...], dict[str, Any]]) -> dict[str, Any]:
    cells = d1_cells(ix)
    res = pick(cells, CHAINS, 1)
    dom = res["dominance"]
    fb_beats = {c: dom["beats"].get(f"fallback>{c}", []) for c in CHAINS if c != "fallback"}
    refused = [c for c in CHAINS if c != "fallback" and fb_beats[c] and not dom["beats"].get(f"{c}>fallback")]
    fb_ties_all = not dom["dominated_by"]["fallback"] and all(
        not dom["beats"].get(f"fallback>{c}") and not dom["beats"].get(f"{c}>fallback") for c in CHAINS[1:])
    verdict = res["winner"]
    notes = []
    if fb_ties_all:
        best = None
        cal = ("lo-first", "hi-first", "six-maps")
        for c in cal:
            sep = True
            for bc in DECISION_BCS:
                me = page_ilo(doc, c, bc)
                for o in cal:
                    other = page_ilo(doc, o, bc)
                    if o != c and (me is None or other is None or me["lo"] <= other["hi"]):
                        sep = False
            if sep:
                best = c
        verdict = best or "lo-first"
        notes.append("calibration buys no measured yield on these sheets; the W3a fallback -> W5 build order "
                     f"stands; chain by page I_lo: {verdict}")
    if verdict == "six-maps":
        notes.append("six-maps recommended at a cost for the owner's ruling: a 6-column evidence KIND and "
                     "conditioned forms read from stored columns instead of a linear 3-score demap")
    must = d1_cells(ix, bcs=(4, 5, 6, 7, 8, 9), uses=("a",), page_population="P-a")
    caveat = [f"{o} beats {verdict} in {c['label']}" for c in must for o in CHAINS if o != verdict
              and beats(c, o, verdict)]
    u13 = []
    for r in RUNGS:
        arms = {}
        for ch in CHAINS:
            kw = {"regime": "twocapture", "bc": 7, "features": "F", "population": "final", "policy": "D1-DEFAULT",
                  "chain": ch, "weighting": wt(ch), "capmode": "SUM-OF-FORMS" if ch == "six-maps" else "SUMMED"}
            lo, hi = bits(get(ix, **kw, stream="lo", mode="any", rung=r)), bits(get(ix, **kw, stream="hi",
                                                                                  mode="any", rung=r))
            if lo is not None and hi is not None:
                arms[ch] = (lo, hi)
        if len(arms) >= 2:
            u13.append({"use": "a", "label": f"twocap U13 {r}", "rung": r, "arms": arms})
    caveat += [f"{o} beats {verdict} in {c['label']}" for c in u13 for o in CHAINS if o != verdict
               and beats(c, o, verdict)]
    rs_cells = d1_cells(ix, features="F1")
    rs = pick(rs_cells, CHAINS, 2) if rs_cells else {"winner": None}
    if rs.get("winner") and rs["winner"] != verdict:
        notes.append(f"the verdict depends on registration quality (single pose picks {rs['winner']})")
    cell_matrix = [{"label": c["label"], "use": c["use"], "informative": informative(c),
                    **{ch: {"k": int(v[0].sum()), "T": int(v[0].size)} for ch, v in c["arms"].items()},
                    "mcnemar_p_vs_fallback": {ch: mcnemar_exact(v[0], c["arms"]["fallback"][0])
                                              for ch, v in c["arms"].items()
                                              if ch != "fallback" and "fallback" in c["arms"]}}
                   for c in cells]
    return {"cells": cell_matrix, "n_cells": len(cells), "pick": strip_pick(res), "refused_vs_fallback": refused,
            "fallback_ties_all": fb_ties_all, "verdict": verdict, "notes": notes, "must_not_lose_caveats": caveat,
            "single_pose": strip_pick(rs) if rs_cells else None}


def strip_pick(p: dict[str, Any]) -> dict[str, Any]:
    return dict(p)


def d1b(doc: dict[str, Any], ix: dict[tuple[Any, ...], dict[str, Any]]) -> dict[str, Any]:
    cells = d1_cells_weighting(ix)
    dom = dominance(cells, ("w", "cb"))
    cold = [r for r in doc["coldstart"] if r.get("weighting") == "w-cb" and r["chain"] == "lo-first"
            and r["form"] == "lo" and r["bc"] in DECISION_BCS and r["features"] == "F" and r["n"] in (1, 2, 3)]
    cb_better_info = any(r["dI_w_minus_cb"]["hi"] < 0 for r in cold)
    cb_wins = bool(dom["dominated_by"]["w"] == ["cb"] or (cb_better_info and not dom["beats"].get("w>cb")))
    return {"n_cells": len(cells), "dominance": dom, "cold_dI_w_minus_cb": cold,
            "verdict": "fit_component_pava (drop the weighted entry)" if cb_wins else "build the weighted entry"}


def d1_cells_weighting(ix: dict[tuple[Any, ...], dict[str, Any]]) -> list[Cell]:
    """lo-first weighted vs class-balanced on the page and cold cells (the two-capture regime has no cb arm)."""
    out = []
    for label, base, r in ([(f"page bc{bc} {r}", {"regime": "page", "bc": bc, "features": "F", "population": "final",
                                                  "policy": "D1-DEFAULT"}, r) for bc in DECISION_BCS for r in RUNGS]
                           + [(f"cold n{n} bc{bc} {r}", {"regime": "cold", "bc": bc, "n": n, "features": "F",
                                                          "population": "cold", "policy": "D1-DEFAULT"}, r)
                              for n in (1, 2, 3) for bc in DECISION_BCS for r in RUNGS]):
        arms = {}
        for w in ("w", "cb"):
            kw = dict(base, chain="lo-first", weighting=w)
            lo, hi = bits(get(ix, **kw, stream="lo", mode="any", rung=r)), bits(get(ix, **kw, stream="hi",
                                                                                  mode="any", rung=r))
            if lo is not None and hi is not None:
                arms[w] = (lo, hi)
        if len(arms) == 2:
            out.append({"use": "a" if base["regime"] == "page" else "b", "label": label, "rung": r, "arms": arms})
    return out


# ---------------------------------------------------------------- D2

def d2(doc: dict[str, Any], ix: dict[tuple[Any, ...], dict[str, Any]]) -> dict[str, Any]:
    cells: list[Cell] = []
    for regime, ns in (("deadY-page", (None,)), ("deadY-cold", (1, 2, 3))):
        for n in ns:
            for bc in DECISION_BCS:
                for r in RUNGS:
                    arms = {}
                    for a in ("a", "b", "c"):
                        row = get(ix, regime=regime, bc=bc, n=n, features="F",
                                  population="page" if regime == "deadY-page" else "cold", chain=None,
                                  weighting="w", policy=None, arm=a, stream="hi", mode="bicm", rung=r)
                        if row is not None:
                            v = bits(row)
                            arms[a] = (v, v)
                    if "a" in arms and "b" in arms:
                        cells.append({"use": "a" if n is None else "b", "label": f"{regime} n{n} bc{bc} {r}",
                                      "rung": r, "arms": arms})
    dom = dominance(cells, ("a", "b"))
    if dom["dominated_by"]["b"] == ["a"]:
        verdict, how = "build the 4th PAVA", "(a) dominates (b)"
    elif dom["dominated_by"]["a"] == ["b"]:
        verdict, how = "use the fallback", "(b) dominates (a)"
    else:
        rng = np.random.default_rng([MASTER_SEED, 10, 99, 3])

        def tot(arm: str, idx: dict[int, np.ndarray] | None) -> float:
            return float(sum(FOUNTAIN_BITS[c["rung"]] * (c["arms"][arm][0][idx[i]] if idx else c["arms"][arm][0])
                             .mean() for i, c in enumerate(cells)))
        lead = tot("a", None) - tot("b", None)
        boots = []
        for _ in range(B_DECIDE):
            idx = {i: rng.integers(0, c["arms"]["a"][0].size, c["arms"]["a"][0].size) for i, c in enumerate(cells)}
            boots.append(tot("a", idx) - tot("b", idx))
        lo, hi = np.percentile(boots, [2.5, 97.5]) if boots else (float("nan"), float("nan"))
        if lo > 0:
            verdict, how = "build the 4th PAVA", f"paired summed hi lead {lead:.1f} bits [{lo:.1f}, {hi:.1f}]"
        else:
            verdict, how = "use the fallback", f"neither dominates; lead {lead:.1f} bits [{lo:.1f}, {hi:.1f}]"
    findings = []
    det = [r for r in doc["deadY"] if r.get("regime") == "cold" and r["arm"] == "a" and r["bc"] in DECISION_BCS]
    if any(r["detect_rate"] < 0.95 for r in det if r["n"] <= 3):
        findings.append("the collapse test is unreliable cold; the erasure must not wait for it")
    fc = [c for c in doc.get("collapse", []) if c and c.get("bc") in DECISION_BCS and c.get("features") == "F"]
    if any(c["any"] > 0.01 for c in fc):
        findings.append("the collapse test erases healthy lo")
    for c in cells:
        if c["rung"] == "r0775" and "c" in c["arms"]:
            pc = c["arms"]["c"][0].mean()
            if pc - c["arms"]["a"][0].mean() > 0.10 or pc - c["arms"]["b"][0].mean() > 0.10:
                findings.append("a dead Y costs hi")
                break
    return {"n_cells": len(cells), "dominance": dom, "verdict": verdict, "how": how, "findings": findings,
            "detect_rates": [{k: r[k] for k in ("bc", "n", "detect_rate")} for r in det]}


# ---------------------------------------------------------------- D3 / D4

def cold_yield_trials(ix: dict[tuple[Any, ...], dict[str, Any]], bc: int, n: int, chain: str, policy: str,
                      weighting: str = "w") -> np.ndarray | None:
    """Per trial the tile yield averaged over the three uniform rungs (any-stage hi + lo)."""
    per = []
    for r in RUNGS:
        kw = {"regime": "cold", "bc": bc, "n": n, "features": "F", "population": "cold", "chain": chain,
              "weighting": weighting, "policy": policy}
        lo, hi = bits(get(ix, **kw, stream="lo", mode="any", rung=r)), bits(get(ix, **kw, stream="hi", mode="any",
                                                                              rung=r))
        if lo is None or hi is None:
            return None
        per.append(FOUNTAIN_BITS[r] * (lo.astype(float) + hi.astype(float)))
    return np.mean(per, 0)


def pooled_lead(a: list[np.ndarray], b: list[np.ndarray], k: int) -> dict[str, float]:
    """Paired bootstrap of sum over groups of (mean a - mean b), resampling trials within each group."""
    rng = np.random.default_rng([MASTER_SEED, 10, 99, k])
    est_ = float(sum(x.mean() - y.mean() for x, y in zip(a, b)))
    boots = []
    for _ in range(B_DECIDE):
        tot = 0.0
        for x, y in zip(a, b):
            i = rng.integers(0, x.size, x.size)
            tot += float(x[i].mean() - y[i].mean())
        boots.append(tot)
    lo, hi = np.percentile(boots, [2.5, 97.5]) if boots else (float("nan"), float("nan"))
    return {"est": est_, "lo": float(lo), "hi": float(hi)}


def d3(doc: dict[str, Any], ix: dict[tuple[Any, ...], dict[str, Any]], winner: str) -> dict[str, Any]:
    chain = winner if winner in ("lo-first", "hi-first") else "lo-first"
    maps = ("L_hi|lo=0", "L_hi|lo=1") if chain == "lo-first" else ("L_lo|hi=0", "L_lo|hi=1")
    sizes = (1, 2, 3, 4, 8)
    mrows = {(r["bc"], r["n"], r["map"]): r for r in doc["coldstart"] if r.get("map") and r["features"] == "F"}
    per_n: dict[int, dict[str, Any]] = {}
    for n in sizes:
        info_ok = all(mrows.get((bc, n, m)) is not None and mrows[(bc, n, m)]["dI"]["lo"] > 0
                      for bc in DECISION_BCS for m in maps)
        q = {v: {m: float(np.mean([mrows[(bc, n, m)]["qualified_frac"][v] for bc in DECISION_BCS
                                   if (bc, n, m) in mrows] or [float("nan")])) for m in maps} for v in ("i", "ii")}
        ys = {}
        for pol in ("NEVER", "ALWAYS", "FLOORS(i)", "FLOORS(ii)"):
            ys[pol] = [cold_yield_trials(ix, bc, n, "fallback" if pol == "NEVER" else chain, pol,
                                         "-" if pol == "NEVER" else "w") for bc in DECISION_BCS]
        avail = all(all(y is not None for y in v) for v in ys.values())
        yrow = {pol: float(np.mean([y.mean() for y in v])) for pol, v in ys.items()} if avail else None
        lead = pooled_lead(ys["ALWAYS"], ys["NEVER"], 10 + n) if avail else None
        per_n[n] = {"info_ok": info_ok, "q": q, "yield": yrow, "always_vs_never": lead, "_ys": ys if avail else None}
    n_info = next((n for n in sizes if per_n[n]["info_ok"]), None)
    n_yield = next((n for n in sizes if per_n[n]["always_vs_never"] and per_n[n]["always_vs_never"]["lo"] > 0), None)
    src = "i"
    src_lead = None
    if all(per_n[n]["_ys"] for n in (1, 2, 3, 4)):
        a = [y for n in (1, 2, 3, 4) for y in per_n[n]["_ys"]["FLOORS(ii)"]]
        b = [y for n in (1, 2, 3, 4) for y in per_n[n]["_ys"]["FLOORS(i)"]]
        src_lead = pooled_lead(a, b, 30)
        src = "ii" if src_lead["lo"] > 0 else "i"
    floor = next((n for n in sizes if min(per_n[n]["q"][src].values()) >= 0.9), None)
    findings = []
    for n in sizes:
        ys = per_n[n]["_ys"]
        if ys:
            ld = pooled_lead(ys["ALWAYS"], ys[f"FLOORS({src})"], 50 + n)
            if ld["lo"] > 0:
                findings.append(f"the floors are too high, costing {ld['est'] / len(DECISION_BCS):.1f} bits/tile "
                                f"at n = {n}")
        for m in maps:
            rows = [mrows.get((bc, n, m)) for bc in DECISION_BCS]
            if per_n[n]["q"][src][m] >= 0.5 and any(r is not None and r["dI"]["hi"] < 0 for r in rows):
                findings.append(f"the floors are too low ({m} adopted at n = {n} where dI < 0)")
    if n_info == 1 and all(per_n[1]["q"][v][m] < 0.5 for v in ("i", "ii") for m in maps) and per_n[1]["yield"]:
        cost = per_n[1]["yield"]["ALWAYS"] - per_n[1]["yield"][f"FLOORS({src})"]
        findings.append(f"1-tile fragments: both sources refuse; the cost is {cost:.1f} bits/tile")
    for n in sizes:
        per_n[n].pop("_ys")
    return {"chain": chain, "maps": maps, "per_n": per_n, "n_star_info": n_info, "n_star_yield": n_yield,
            "source": src, "source_lead_ii_minus_i": src_lead, "tile_floor": floor, "findings": findings}


def d4(doc: dict[str, Any], chain: str, src: str) -> dict[str, Any]:
    chain = chain if chain in ("lo-first", "hi-first", "six-maps") else "lo-first"
    g = [r for r in doc["gates"] if r["chain"] == chain and r["valsrc"] == src and r["bc"] in DECISION_BCS
         and r["features"] == "F" and r["regime"] == "cold"]
    tri: dict[str, list[np.ndarray]] = {}
    table = []
    for r in g:
        table.append({k: r.get(k) for k in ("bc", "n", "gate", "refusal", "dust_only_share", "false_refusal",
                                            "false_adoption", "policy_yield", "n_draws")})
        if r.get("policy_yield_trials"):
            tri.setdefault(r["gate"], []).append(np.asarray(r["policy_yield_trials"]))
    out: dict[str, Any] = {"chain": chain, "source": src, "table": table}
    verdict = "G1 (single, total only)"
    if "G1" in tri and "G3" in tri and len(tri["G1"]) == len(tri["G3"]):
        out["G3_vs_G1"] = pooled_lead(tri["G3"], tri["G1"], 70)
        if out["G3_vs_G1"]["lo"] > 0:
            verdict = "G3 (three-way)"
    if "G2" in tri and "G1" in tri and len(tri["G1"]) == len(tri["G2"]):
        out["G2_vs_G1"] = pooled_lead(tri["G2"], tri["G1"], 71)
        if out["G2_vs_G1"]["lo"] > 0 and verdict.startswith("G1"):
            verdict = "G2 (total + word)"
    shares = [r["dust_only_share"] for r in g if r["gate"] == "G3" and r["dust_only_share"] is not None]
    out["dust_only_share_mean"] = float(np.mean(shares)) if shares else None
    out["verdict"] = verdict
    return out


def per_use(ix: dict[tuple[Any, ...], dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for use in ("a", "b"):
        cells = d1_cells(ix, uses=(use,))
        if cells:
            p = pick(cells, CHAINS, 40 + (use == "b"))
            out[{"a": "pages", "b": "fragments"}[use]] = {"winner": p["winner"], "how": p["how"],
                                                          "scores": p.get("scores")}
    return out


def decide(doc: dict[str, Any]) -> dict[str, Any]:
    ix = index_ldpc(doc["ldpc"])
    D1 = d1(doc, ix)
    D1b = d1b(doc, ix)
    D2 = d2(doc, ix)
    D3 = d3(doc, ix, D1["verdict"])
    D4 = d4(doc, D1["verdict"], D3["source"])
    uses = per_use(ix)
    uses["dead Y"] = {"winner": D2["verdict"]}
    return {"D1": D1, "D1b": D1b, "D2": D2, "D3": D3, "D4": D4,
            "synthesis": {"chain": D1["verdict"], "weighting": D1b["verdict"], "dead_y": D2["verdict"],
                          "validation_source": D3["source"], "tile_floor": D3["tile_floor"], "gate": D4["verdict"],
                          "per_use": uses}}
