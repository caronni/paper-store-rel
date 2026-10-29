"""R11 — furniture emulation, regions, and one calibration context (QDA + maps under every policy + the gates).

What: (1) a band-capture held in memory (cells, features F = per-plane pose and F1 = single pose, the manifest
state, windows) cut into REGIONS — c2: two horizontally adjacent 46 x 46 windows (4232 cells, ~1.03 tile),
c3: 2 x 2 windows of 31 x 31 (3844 cells, ~0.94 tile); a window with reg_ok False or reg_edge True drops its
region; (2) the p120 furniture law per emulated tile: search 53 word sites + 11 dust, held-out 47 + 9; a word
bit is Bernoulli(1/2), '1' = C, '0' = Y or W by a fair per-site draw (R10), dust = M (R3), drawn without
replacement from the region's cells of each state, the rest of the region being the payload; each held-out cell
gets u ~ U(0,1) from the validation rng, u < 1/3 = VALIDATION under source (i); (3) one calibration context:
the receiver's QDA on the search side, the six maps on the held-out side (the full half H and the fit part
H\\val), both weightings for the two marginal maps, and the five policies — NEVER (fallback), ALWAYS (every
fittable map), D1-DEFAULT (floors on H, the conditional 20-row validation counted on the fit set, no pre-gate),
FLOORS(ii) (D1-DEFAULT + A4b's pre-gate on H in-sample), FLOORS(i) (maps on H\\val, floors there, the 20 counted
on val, pre-gate on val); (4) the region gates of decision 4 (G0 always, G1 total, G2 total + word, G3 total +
word + dust, slack 1e-9, the 4-state NLL of fit_detector, an empty leg passing).
Why: the protocol's furniture emulation, floors and gates, in one place so every regime uses the same law.
How: imports the receiver's floors and losses (color_model, color_conditioning._binary_nll / _balanced_mean);
all randomness comes from rngs the caller builds from config.MASTER_SEED.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from holo.receiver.plugins.color_conditioning import _balanced_mean, _binary_nll
from holo.receiver.plugins.color_model import HEAD_GATE_SLACK, PavaMap, QdaModel
from measure.cmy_calibration.chains import (CHAIN_MAPS, MAP_SPECS, C, M, W, Y, ChainOut, bound_triple, chain_output,
                                            collapse_flags, demap, fit_map, fit_model, gate_triple, map_population,
                                            nll4, qualify_conditional, qualify_marginal, raw_scores)
from measure.cmy_calibration.config import (HELD_DUST, HELD_WORDS, POLICIES, SEARCH_DUST, SEARCH_WORDS)

ARM_CHAINS = (("fallback", "-"), ("lo-first", "w"), ("lo-first", "cb"), ("hi-first", "w"), ("hi-first", "cb"),
              ("six-maps", "w"))


# ---------------------------------------------------------------- band and regions

@dataclass
class Band:
    bc: int
    name: str
    cell_dots: int
    X: dict[str, np.ndarray]
    state: np.ndarray
    win: np.ndarray
    win_ids: np.ndarray
    regions: list[np.ndarray]
    region_windows: list[tuple[int, ...]]
    region_grid: np.ndarray
    excluded: dict[str, int]
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def n_regions(self) -> int:
        return len(self.regions)


def window_ok(arrays: dict[str, np.ndarray], w: int) -> tuple[bool, str | None]:
    if not bool(arrays["w_reg_ok"][w]):
        return False, "reg_nominal"
    if bool(arrays["w_reg_edge"][w]):
        return False, "reg_edge"
    return True, None


def build_band(arrays: dict[str, np.ndarray], meta: dict[str, Any], band: str, bc: int,
               drop_ids: frozenset[str] = frozenset()) -> Band:
    """The band's cells and regions from an extract npz; windows named in drop_ids are excluded too (the
    two-capture regime drops a window bad in either capture)."""
    bi = meta["band_names"].index(band)
    sel = np.flatnonzero(arrays["band"] == bi)
    cd = int(meta["bands"][band]["cell_dots"])
    win_all = arrays["win"][sel]
    wins = np.unique(win_all)
    excluded = {"reg_nominal": 0, "reg_edge": 0, "unpaired": 0, "other_capture": 0}
    good: dict[tuple[int, int], int] = {}
    for w in wins:
        ok, why = window_ok(arrays, int(w))
        if ok and str(arrays["w_id"][w]) in drop_ids:
            ok, why = False, "other_capture"
        if not ok:
            excluded[str(why)] += 1
            continue
        good[(int(arrays["w_grid_row"][w]), int(arrays["w_grid_col"][w]))] = int(w)
    rows = 1 + max((r for r, _ in good), default=-1)
    cols = 1 + max((c for _, c in good), default=-1)
    shape = (1, 2) if cd == 2 else (2, 2)
    grid = -np.ones((max(rows // shape[0], 0), max(cols // 2, 0)), np.int64)
    used: set[int] = set()
    region_windows: list[tuple[int, ...]] = []
    for gr in range(grid.shape[0]):
        for gc in range(grid.shape[1]):
            members = [good.get((gr * shape[0] + dr, gc * 2 + dc)) for dr in range(shape[0]) for dc in range(2)]
            if all(m is not None for m in members):
                grid[gr, gc] = len(region_windows)
                region_windows.append(tuple(int(m) for m in members if m is not None))
                used.update(int(m) for m in members if m is not None)
    excluded["unpaired"] = len(good) - len(used)
    keep_w = np.array(sorted(used), np.int64)
    local = -np.ones(int(arrays["win"].max()) + 1, np.int64)
    local[keep_w] = np.arange(keep_w.size)
    cells = sel[np.isin(win_all, keep_w)]
    win_local = local[arrays["win"][cells]]
    order = np.argsort(win_local, kind="stable")
    cells, win_local = cells[order], win_local[order]
    starts = np.searchsorted(win_local, np.arange(keep_w.size))
    ends = np.searchsorted(win_local, np.arange(keep_w.size), side="right")
    regions = [np.concatenate([np.arange(starts[local[w]], ends[local[w]]) for w in rw]) for rw in region_windows]
    X = {"F": arrays["x_pp"][cells].astype(np.float64), "F1": arrays["x_1"][cells].astype(np.float64)}
    return Band(bc=bc, name=band, cell_dots=cd, X=X, state=arrays["y"][cells].astype(np.int64), win=win_local,
                win_ids=arrays["w_id"][keep_w], regions=regions,
                region_windows=[tuple(int(local[w]) for w in rw) for rw in region_windows], region_grid=grid,
                excluded=excluded, meta={"cells_global": cells, "capture": meta.get("capture")})


def cluster_origins(band: Band, n: int, shapes: dict[int, tuple[int, int]]) -> list[tuple[int, ...]]:
    """Every rows x cols rectangle of regions (in region units) whose regions all exist."""
    rh, rw = shapes[n]
    g = band.region_grid
    out = []
    for r in range(g.shape[0] - rh + 1):
        for c in range(g.shape[1] - rw + 1):
            blk = g[r:r + rh, c:c + rw]
            if (blk >= 0).all():
                out.append(tuple(int(v) for v in blk.ravel()))
    return out


# ---------------------------------------------------------------- furniture

@dataclass
class Furniture:
    search: np.ndarray
    held: np.ndarray
    held_kind: np.ndarray          # 0 word, 1 dust, -1 certified (P-b)
    payload: np.ndarray
    payload_region: np.ndarray


def tile_counts(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """(search, held) state counts (W, C, M, Y) of one tile's p120 furniture."""
    out = []
    for n_words, n_dust in ((SEARCH_WORDS, SEARCH_DUST), (HELD_WORDS, HELD_DUST)):
        one = rng.random(n_words) < 0.5
        yel = rng.random(n_words) < 0.5
        out.append(np.array([int((~one & ~yel).sum()), int(one.sum()), n_dust, int((~one & yel).sum())]))
    return out[0], out[1]


def draw_region(rng: np.random.Generator, cells: np.ndarray, state: np.ndarray
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(search, held, held_kind, payload) cell indices of one region (one emulated tile)."""
    ns, nh = tile_counts(rng)
    st = state[cells]
    search, held, kind = [], [], []
    for s in (W, C, M, Y):
        pool = cells[st == s]
        need = int(ns[s] + nh[s])
        if pool.size < need:
            raise ValueError(f"region has {pool.size} cells of state {s}, furniture needs {need}")
        pick = rng.choice(pool, need, replace=False)
        search.append(pick[:ns[s]])
        held.append(pick[ns[s]:])
        kind.append(np.full(int(nh[s]), 1 if s == M else 0, np.int8))
    search_a, held_a = np.concatenate(search), np.concatenate(held)
    payload = np.setdiff1d(cells, np.concatenate([search_a, held_a]), assume_unique=True)
    return search_a, held_a, np.concatenate(kind), payload


def draw_furniture(rng: np.random.Generator, band: Band, region_ids: tuple[int, ...] | list[int]) -> Furniture:
    parts = [draw_region(rng, band.regions[g], band.state) for g in region_ids]
    return Furniture(search=np.concatenate([p[0] for p in parts]), held=np.concatenate([p[1] for p in parts]),
                     held_kind=np.concatenate([p[2] for p in parts]),
                     payload=np.concatenate([p[3] for p in parts]),
                     payload_region=np.concatenate([np.full(p[3].size, i, np.int64) for i, p in enumerate(parts)]))


def shuffle_labels(rng: np.random.Generator, band: Band, fur: Furniture, region_ids: list[int] | tuple[int, ...]
                   ) -> np.ndarray:
    """A copy of band.state with the furniture labels permuted within each region (the C5 null)."""
    st = band.state.copy()
    for g in region_ids:
        cells = band.regions[g]
        f = np.concatenate([np.intersect1d(fur.search, cells), np.intersect1d(fur.held, cells)])
        st[f] = st[f][rng.permutation(f.size)]
    return st


# ---------------------------------------------------------------- one calibration context

@dataclass
class MapDiag:
    fitted: bool
    qualified: dict[str, bool]
    pregate: dict[str, bool | None]
    reason: dict[str, str | None]


@dataclass
class Context:
    refused: str | None
    model: QdaModel | None = None
    collapse: dict[str, Any] = field(default_factory=lambda: {"lo": False, "hi": False, "pairs": []})
    pieces: dict[tuple[str, str], dict[int, PavaMap | None]] = field(default_factory=dict)
    diag: dict[int, MapDiag] = field(default_factory=dict)
    maps: dict[tuple[str, str, int], PavaMap | None] = field(default_factory=dict)
    r_held: np.ndarray | None = None
    held_state: np.ndarray | None = None
    held_kind: np.ndarray | None = None
    val: np.ndarray | None = None


def _pregate(pmap: PavaMap, k: int, stat: np.ndarray, fb: np.ndarray, state: np.ndarray) -> bool | None:
    """A4b's stratum pre-gate: balanced binary NLL(fallback piece) - NLL(map) > slack on the given rows."""
    spec = MAP_SPECS[k]
    member, label = map_population(spec, state)
    if not member.any():
        return None
    cand = _balanced_mean(_binary_nll(pmap.llrs(stat[member, k]), label[member]), label[member])
    inc = _balanced_mean(_binary_nll(fb[member, k], label[member]), label[member])
    return bool(inc - cand > HEAD_GATE_SLACK)


def fit_context(X_search: np.ndarray, s_search: np.ndarray, X_held: np.ndarray, s_held: np.ndarray,
                kind_held: np.ndarray, val: np.ndarray, policies: tuple[str, ...] = POLICIES,
                weightings: tuple[str, ...] = ("w", "cb")) -> Context:
    """QDA on the search side, maps on the held-out side, the pieces of every (policy, weighting)."""
    if np.any(np.bincount(s_search, minlength=4) == 0):
        return Context(refused="search_split_missing_state")
    if np.any(np.bincount(s_held, minlength=4) == 0):
        return Context(refused="heldout_split_missing_state")
    model = fit_model(X_search, s_search)
    if model is None:
        return Context(refused="detector_fit_failed")
    ctx = Context(refused=None, model=model, collapse=collapse_flags(X_search, s_search, model))
    r = raw_scores(model, X_held)
    stat, fb = demap(r), demap(bound_triple(r)[0])
    ctx.r_held, ctx.held_state, ctx.held_kind, ctx.val = r, s_held, kind_held, val
    pops = {"H": np.ones(s_held.size, bool), "Hfit": ~val}
    for pop, mask in pops.items():
        if pop == "Hfit" and "FLOORS(i)" not in policies:
            continue
        for k, spec in enumerate(MAP_SPECS):
            for wt in (weightings if spec.marginal else ("w",)):
                ctx.maps[(pop, wt, k)] = fit_map(spec, stat[mask, k], s_held[mask], wt)
    for k, spec in enumerate(MAP_SPECS):
        q: dict[str, bool] = {}
        pg: dict[str, bool | None] = {}
        why: dict[str, str | None] = {}
        for pol, pop, vmask in (("H", "H", pops["H"]), ("Hfit", "Hfit", val)):
            if (pop, "w", k) not in ctx.maps:
                continue
            fit_states = s_held[pops[pop]]
            if spec.marginal:
                q[pol], why[pol] = qualify_marginal(spec, fit_states)
            else:
                n_val = int(map_population(spec, s_held[vmask])[0].sum())
                q[pol], why[pol] = qualify_conditional(spec, fit_states, n_val)
            pm = ctx.maps[(pop, "w", k)]
            pg[pol] = None if (spec.marginal or pm is None) else _pregate(pm, k, stat[vmask], fb[vmask],
                                                                          s_held[vmask])
        ctx.diag[k] = MapDiag(fitted=ctx.maps.get(("H", "w", k)) is not None, qualified=q, pregate=pg, reason=why)
    for pol in policies:
        for wt in weightings:
            ctx.pieces[(pol, wt)] = {k: policy_piece(ctx, pol, wt, k) for k in range(6)}
    return ctx


def policy_piece(ctx: Context, policy: str, weighting: str, k: int) -> PavaMap | None:
    spec = MAP_SPECS[k]
    wt = weighting if spec.marginal else "w"
    d = ctx.diag[k]
    if policy == "NEVER":
        return None
    if policy == "ALWAYS":
        return ctx.maps.get(("H", wt, k))
    pop = "Hfit" if policy == "FLOORS(i)" else "H"
    side = "Hfit" if policy == "FLOORS(i)" else "H"
    pm = ctx.maps.get((pop, wt, k))
    if pm is None or not d.qualified.get(side, False):
        return None
    if policy.startswith("FLOORS") and not spec.marginal and d.pregate.get(side) is not True:
        return None
    return pm


def apply_context(ctx: Context, X_eval: np.ndarray, arms: list[tuple[str, str, str]]
                  ) -> tuple[np.ndarray | None, dict[tuple[str, str, str], ChainOut]]:
    """(raw r, arm -> ChainOut) on evaluation cells; a refused region emits zeros for every arm."""
    n = X_eval.shape[0]
    if ctx.refused is not None or ctx.model is None:
        z = np.zeros((n, 6))
        return None, {a: ChainOut(z, np.zeros((n, 3)), np.zeros(n, bool)) for a in arms}
    r = raw_scores(ctx.model, X_eval)
    return r, apply_pieces(ctx, r, arms)


def apply_pieces(ctx: Context, r: np.ndarray, arms: list[tuple[str, str, str]]
                 ) -> dict[tuple[str, str, str], ChainOut]:
    stat = demap(r)
    cache: dict[int, np.ndarray] = {}
    out = {}
    for chain, wt, pol in arms:
        if chain == "fallback":
            pieces: dict[int, np.ndarray | None] = {}
        else:
            src = ctx.pieces[(pol, wt if wt != "-" else "w")]
            pieces = {}
            for k in CHAIN_MAPS[chain]:
                pm = src[k]
                if pm is not None and id(pm) not in cache:
                    cache[id(pm)] = pm.llrs(stat[:, k])
                pieces[k] = None if pm is None else cache[id(pm)]
        out[(chain, wt, pol)] = chain_output(chain, pieces, r, bool(ctx.collapse["lo"]), bool(ctx.collapse["hi"]))
    return out


# ---------------------------------------------------------------- region gates (decision 4)

def gate_losses(s: np.ndarray, state: np.ndarray, kind: np.ndarray) -> dict[str, float]:
    """total / word / dust mean 4-state NLL (fit_detector :254-266; empty leg = inf) + a state-balanced total."""
    nll = nll4(s, state)
    out = {"total": float(nll.mean()) if nll.size else float("inf")}
    for name, kd in (("word", 0), ("dust", 1)):
        sel = kind == kd
        out[name] = float(nll[sel].mean()) if sel.any() else float("inf")
    present = [s_ for s_ in range(4) if (state == s_).any()]
    out["balanced"] = float(np.mean([nll[state == s_].mean() for s_ in present])) if present else float("inf")
    return out


def gate_decisions(cand: dict[str, float], inc: dict[str, float], slack: float = HEAD_GATE_SLACK
                   ) -> dict[str, bool]:
    total = cand["total"] + slack < inc["total"]
    word = cand["word"] <= inc["word"] + slack
    dust = cand["dust"] <= inc["dust"] + slack
    return {"G0": True, "G1": total, "G2": total and word, "G3": total and word and dust,
            "G3_dust_only_refusal": total and word and not dust}


def region_gates(ctx: Context, chains: tuple[str, ...]) -> dict[tuple[str, str], dict[str, Any]]:
    """Per (chain, source v) the gate decisions on the source's validation cells: (i) = val, (ii) = all held."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    if ctx.refused is not None or ctx.r_held is None:
        return out
    for v, pol, mask in (("i", "FLOORS(i)", ctx.val), ("ii", "FLOORS(ii)", np.ones(ctx.val.size, bool))):
        if (pol, "w") not in ctx.pieces:
            continue
        r = ctx.r_held[mask]
        st, kd = ctx.held_state[mask], ctx.held_kind[mask]
        inc = gate_losses(bound_triple(r)[0], st, kd)
        outs = apply_pieces(ctx, r, [(c, "w", pol) for c in chains])
        for c in chains:
            cand = gate_losses(gate_triple(c, outs[(c, "w", pol)]), st, kd)
            out[(c, v)] = {"cand": cand, "inc": inc, **gate_decisions(cand, inc), "n_val": int(mask.sum())}
    return out
