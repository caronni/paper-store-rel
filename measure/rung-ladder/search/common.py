# Historical record of the 2026-09-30 rung-ladder study (docs/RUNG-LADDER-STUDY-2026-09-30.md), retired from
# machine-4-salvage/scratch/rung-ladder-20260930/ 2026-10-09; its data is in results/ beside this tree (2026-10-11; results/README.md).
# Regenerates its study outputs beside it (as on 2026-09-30; gitignored here) with: PYTHONPATH=src:. env/bin/python measure/rung-ladder/search/common.py
"""Shared evaluation library for the r0400ish / r0300ish construction search
(scratch; nothing here is a format row).

(i)   draw()        GENERALIZED e-IRA draw derived from paperholo.ldpc._draw_h_blocks:
                    per-block-column DEGREE LIST, gap_min, rule-(d) cap slack,
                    PLACEMENT {uniform = the recipe's stream, balanced = least-
                    loaded block rows first}, seed label b"search/<tag>/<seed>"
                    via paperholo.modulation.rng, restart loop as the recipe.
                    Rule (b) and Fisher-Yates are paperholo's own functions
                    (imported). A search config additionally RESTARTS on an
                    info-free block row (rule (e), info_rows="restart"); the
                    baselines keep the frozen recipe exactly (info_rows="audit")
                    and are verified edge-identical to harness/data (smoke).
(ii)  build/register: expansion -> holo construct.Code -> construct.LADDER /
                    _CODE_CACHE, deterministically re-built from the config in
                    every worker (the restart index rides along as a hint).
(iii) audit():      harness/structure.stats (imported) + the block-row view.
(iv)  channels/walks/interp: harness/channels.run_task, sweep.Walk,
                    tables.interp_x (imported); the confidently-wrong robustness
                    channel is added here (BASE 500_000 + t).
(v)   Search:       the three screens of the EVALUATION PROTOCOL on one process
                    pool, generator jobs, JSONL checkpoint (one line per
                    (rid, screen), fsync'd), resume by skipping done lines,
                    progress on stderr, SIGINT/SIGTERM-safe.
(vi)  summarize():  -> <out>/TABLES-search.md.
"""
from __future__ import annotations

import hashlib
import heapq
import itertools
import json
import math
import multiprocessing as mp
import os
import signal
import statistics
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

# Worker BLAS threads: this numpy links Apple Accelerate (VECLIB_*), OMP/OPENBLAS are defensive.
# Set in the PARENT at import, before any pool spawns (the DE pools of Tier B1 spawn before
# Runner); spawned workers inherit os.environ (overnight prep 2026-09-30, fast/README).
for _v in ("VECLIB_MAXIMUM_THREADS", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SEARCH = Path(__file__).resolve().parent
WORK = SEARCH.parent
HARNESS = WORK / "harness"
for _p in (ROOT / "src", HARNESS, SEARCH):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from paperholo.modulation import rng  # noqa: E402
from paperholo import ldpc as pldpc  # noqa: E402  (_fisher_yates, _column_tap_weight_ok)
from holo.core.ldpc import construct  # noqa: E402
from holo.core.ldpc.decode import encode  # noqa: E402
import codes as hcodes  # noqa: E402  (harness: registers the 16 measured codes)
import channels as ch  # noqa: E402
import structure as hstruct  # noqa: E402
import sweep as hsweep  # noqa: E402
import tables as htables  # noqa: E402

Z = 64
N = 4096
BASE_ROBUST = 500_000
BASELINE_RID = {1664: "r0406", 1280: "r0313", 1600: "r0391", 1216: "r0297"}
# The FROZEN production rungs (src/holo/core/ldpc/data), searched as full rows (owner's ruling
# 2026-09-30).  The first rid per k is the SCREEN-1 ANCHOR and the Δ reference: at k=2240 that is
# r0547 (clean, p@10% 0.0726) rather than r0550 (error floor: 8 undetected / 2000 on awgn, 22 / 3600
# on bsc in TABLES.md) — both are named baseline rows.
FROZEN_RUNGS = {2240: ("r0547", "r0550"), 2560: ("r0625",), 2880: ("r0700",), 3200: ("r0775",), 3520: ("r0850",)}


def ref_rid(k: int) -> str:
    """The frozen code whose measured 10 % points anchor screen 1 at k (harness results.json)."""
    return BASELINE_RID[k] if k in BASELINE_RID else FROZEN_RUNGS[k][0]
# Screen-1 offsets from the frozen recipe's 10 % point (literal protocol: awgn +0.25 dB = EASIER,
# bsc +0.005 = HARDER).  Kept as constants so a re-score of stored counts is possible.
S1_AWGN_OFFSETS_DB = (0.0, 0.25)
S1_BSC_OFFSETS = (0.0, 0.005)
ROBUST_F = (0.001, 0.002, 0.005, 0.01)   # protocol: 0.5 %, 1 %; 0.1 %, 0.2 % added (the protocol points saturate, smoke)
ERAS_POINT = {"eps": 0.3, "p": 0.02}


# ---------------------------------------------------------------- (i) draw
@dataclass(frozen=True)
class Cfg:
    k: int
    degs: tuple            # per info block-column degree, in column order
    tag: str               # config identity WITHOUT the seed (seed label b"search/<tag>/<seed>")
    seed: int = 0
    gap_min: int = 24
    slack: int = 1         # rule (d): cap = ceil(sum(degs)/mb) + slack
    placement: str = "uniform"   # uniform | balanced
    info_rows: str = "restart"   # restart (rule e) | audit (frozen recipe: never restart on it)
    label: str = ""        # explicit seed label (baselines: "ldpc-v1/<rid>")
    rid: str = ""          # registry name; default f"{tag}-s{seed}"
    baseline: bool = False
    meta: tuple = ()       # (("heavy_deg",10),("heavy_frac",0.3),("light",3)) informational
    max_restarts: int = 2048
    max_col_attempts: int = 65536
    max_build_s: float = 120.0
    frozen: str = ""       # production rate id: the code IS construct.load_code(frozen) (no draw)

    @property
    def name(self) -> str:
        return self.rid or f"{self.tag}-s{self.seed}"

    @property
    def seed_label(self) -> bytes:
        return (self.label or f"search/{self.tag}/{self.seed}").encode()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["degs"] = list(self.degs)
        d["meta"] = [list(x) for x in self.meta]
        return d

    @staticmethod
    def from_dict(d: dict) -> "Cfg":
        d = dict(d)
        d["degs"] = tuple(d["degs"])
        d["meta"] = tuple(tuple(x) for x in d.get("meta", ()))
        return Cfg(**d)


def recipe_cfg(k: int, heavy_deg: int, heavy_frac: float, light: int, placement: str,
               seed: int, *, gap_min: int = 24, slack: int = 1) -> Cfg:
    """The recipe family: nh = round(heavy_frac*kb) heavy columns FIRST, the rest `light`."""
    kb = k // Z
    nh = round(heavy_frac * kb)
    degs = tuple([heavy_deg] * nh + [light] * (kb - nh))
    tag = f"k{k}-h{heavy_deg}-f{heavy_frac:.1f}-l{light}-{placement[:3]}-g{gap_min}-d{slack}"
    return Cfg(k=k, degs=degs, tag=tag, seed=seed, gap_min=gap_min, slack=slack,
               placement=placement,
               meta=(("heavy_deg", heavy_deg), ("heavy_frac", heavy_frac), ("light", light)))


def baseline_cfg(k: int) -> Cfg:
    """The FROZEN recipe exactly (label ldpc-v1/<rid>, HEAVY_FRAC 0.30, heavy 10, light 3,
    uniform, no rule (e)) -> must be edge-identical to harness/data/<rid>.json."""
    rid = BASELINE_RID[k]
    c = recipe_cfg(k, 10, 0.30, 3, "uniform", 0)
    return replace(c, label=f"ldpc-v1/{rid}", info_rows="audit", rid=f"base-{rid}", baseline=True,
                   tag="baseline-" + c.tag)


def frozen_cfg(rid: str) -> Cfg:
    """A frozen production code as a named baseline row (base-<rid>): loaded, never drawn."""
    d = json.loads((ROOT / "src/holo/core/ldpc/data" / f"{rid}.json").read_text())
    k, hd = int(d["k_bits"]), int(d["heavy_deg"])
    nh, kb = len(d["heavy_rows"]), k // Z
    return Cfg(k=k, degs=tuple([hd] * nh + [3] * (kb - nh)), tag=f"frozen-{rid}", seed=0,
               gap_min=int(d["gap_min"]), placement="uniform", info_rows="audit", rid=f"base-{rid}",
               baseline=True, frozen=rid,
               meta=(("heavy_deg", hd), ("heavy_frac", round(nh / kb, 3)), ("light", 3)))


class BuildFail(Exception):
    def __init__(self, reason: str, info: dict):
        super().__init__(reason)
        self.reason, self.info = reason, info


def _pspec(cfg: Cfg) -> pldpc.LdpcSpec:
    return pldpc.LdpcSpec("search", cfg.k, gap_min=cfg.gap_min)


def draw(cfg: Cfg, restart: int):
    """One restart. Returns (pi, rows_list, shifts_list, row_deg) or a failure string."""
    k, m = cfg.k, N - cfg.k
    mb, kb = m // Z, k // Z
    degs = cfg.degs
    if len(degs) != kb or min(degs) < 2 or max(degs) > mb:
        raise ValueError(f"bad degree list for k={k}: {degs}")
    deg_cap = -(-sum(degs) // mb) + cfg.slack
    spec = _pspec(cfg)
    g = rng(cfg.seed_label, b"eira-H/restart" + str(restart).encode())
    pi = pldpc._fisher_yates(g, m)
    used: dict[tuple[int, int], set[int]] = {}
    row_deg = np.zeros(mb, np.int64)
    rows_l, shifts_l = [], []
    balanced = cfg.placement == "balanced"
    for d in degs:
        for att in range(cfg.max_col_attempts):
            if balanced:
                # least-loaded rows first (noise < 1 load unit never reorders load levels),
                # ties by the generator; after 256 failed attempts the window widens slowly
                key = g.random(mb)
                w = 1.0 if att < 256 else 1.0 + (att - 256) / 1024.0
                rows = np.argsort(row_deg + w * key, kind="stable")[:d].astype(np.int64)
                shifts = g.integers(0, Z, size=d)
            else:
                rows = g.integers(0, mb, size=d)
                shifts = g.integers(0, Z, size=d)
                if len({int(r) for r in rows}) != d:                   # rule (a)
                    continue
            order = np.argsort(rows)
            rows, shifts = rows[order], shifts[order]
            if (row_deg[rows] + 1 > deg_cap).any():                    # rule (d)
                continue
            bad = False
            for a in range(d):                                         # rule (c)
                for b in range(a + 1, d):
                    if (int(shifts[a]) - int(shifts[b])) % Z in used.get((int(rows[a]), int(rows[b])), ()):
                        bad = True
                        break
                if bad:
                    break
            if bad:
                continue
            if not pldpc._column_tap_weight_ok(pi, rows, shifts, spec):  # rule (b)
                continue
            for a in range(d):
                for b in range(a + 1, d):
                    used.setdefault((int(rows[a]), int(rows[b])), set()).add(
                        (int(shifts[a]) - int(shifts[b])) % Z)
            row_deg[rows] += 1
            rows_l.append(rows)
            shifts_l.append(shifts)
            break
        else:
            return "col_exhausted"
    return pi, rows_l, shifts_l, row_deg


def expand(cfg: Cfg, pi, rows_l, shifts_l):
    """paperholo/holo _expand_edges generalized to a per-column list."""
    k, m = cfg.k, N - cfg.k
    a = np.arange(Z, dtype=np.int64)
    chk_l, var_l = [], []
    for j, (rows, shifts) in enumerate(zip(rows_l, shifts_l)):
        for r, s in zip(rows, shifts):
            chk_l.append(pi[int(r) * Z + a])
            var_l.append(j * Z + (a + int(s)) % Z)
    jj = np.arange(m, dtype=np.int64)
    chk_l += [jj, jj[1:]]
    var_l += [k + jj, k + jj[:-1]]
    return np.concatenate(chk_l).astype(np.int32), np.concatenate(var_l).astype(np.int32)


def make_code(cfg: Cfg, chk, var) -> construct.Code:
    """Edge arrays -> holo construct.Code (same post-processing as construct.load_code)."""
    k, m, n = cfg.k, N - cfg.k, N
    spec = construct.LdpcSpec(cfg.name, k, n_bits=n, heavy_deg=max(cfg.degs), gap_min=cfg.gap_min)
    order = np.lexsort((var, chk))
    chk, var = chk[order], var[order]
    cc = np.bincount(chk, minlength=m)
    assert cc.min() >= 2
    chk_starts = np.concatenate(([0], np.cumsum(cc)[:-1]))
    var_order = np.argsort(var, kind="stable")
    vc = np.bincount(var, minlength=n)
    assert vc.min() >= 1
    var_starts = np.concatenate(([0], np.cumsum(vc)[:-1]))
    is_info = var < k
    ic, iv = chk[is_info].astype(np.int64), var[is_info].astype(np.int64)
    io = np.argsort(ic, kind="stable")
    ic, iv = ic[io], iv[io]
    enc_rows, first = np.unique(ic, return_index=True)
    return construct.Code(spec=spec, edge_chk=chk, edge_var=var,
                          chk_starts=chk_starts.astype(np.int64),
                          var_order=var_order.astype(np.int64),
                          var_starts=var_starts.astype(np.int64),
                          enc_info_col=iv, enc_rows=enc_rows,
                          enc_row_starts=first.astype(np.int64))


def build(cfg: Cfg, restart_hint: int | None = None):
    """Restart loop as the recipe (+ rule (e) for info_rows=restart). Returns (Code, info)."""
    m = N - cfg.k
    t0 = time.perf_counter()
    if cfg.frozen:
        return _build_frozen(cfg, t0)
    reasons = {"col_exhausted": 0, "deg1_check": 0, "info_free_block_row": 0}
    rng_iter = [restart_hint] if restart_hint is not None else range(cfg.max_restarts)
    for restart in rng_iter:
        if time.perf_counter() - t0 > cfg.max_build_s:
            raise BuildFail("build_timeout", {"reasons": reasons, "restarts_tried": restart,
                                              "seconds": time.perf_counter() - t0})
        out = draw(cfg, restart)
        if isinstance(out, str):
            reasons[out] += 1
            continue
        pi, rows_l, shifts_l, row_deg = out
        chk, var = expand(cfg, pi, rows_l, shifts_l)
        if int(np.bincount(chk, minlength=m).min()) < 2:
            reasons["deg1_check"] += 1
            continue
        n_free = int((row_deg == 0).sum())
        if n_free and cfg.info_rows == "restart":
            reasons["info_free_block_row"] += 1
            continue
        info = {"restart": restart, "reasons": reasons, "seconds": round(time.perf_counter() - t0, 3),
                "block_row_deg_hist": {int(a): int(b) for a, b in zip(*np.unique(row_deg, return_counts=True))},
                "info_free_block_rows": n_free, "n_edges": int(chk.size),
                "deg_cap": -(-sum(cfg.degs) // (m // Z)) + cfg.slack}
        return make_code(cfg, chk, var), info
    raise BuildFail("restarts_exhausted" if restart_hint is None else "restart_hint_failed",
                    {"reasons": reasons, "seconds": round(time.perf_counter() - t0, 3)})


def _build_frozen(cfg: Cfg, t0: float):
    """The production code itself (construct.load_code), re-keyed under the row's registry name."""
    src = construct.load_code(cfg.frozen)
    d = json.loads((ROOT / "src/holo/core/ldpc/data" / f"{cfg.frozen}.json").read_text())
    mb = (N - cfg.k) // Z
    row_deg = np.bincount(np.concatenate([np.asarray(d["heavy_rows"]).ravel(), np.asarray(d["light_rows"]).ravel()]),
                          minlength=mb)
    spec = construct.LdpcSpec(cfg.name, cfg.k, n_bits=N, heavy_deg=src.spec.heavy_deg, gap_min=src.spec.gap_min)
    code = construct.Code(spec=spec, edge_chk=src.edge_chk, edge_var=src.edge_var, chk_starts=src.chk_starts,
                          var_order=src.var_order, var_starts=src.var_starts, enc_info_col=src.enc_info_col,
                          enc_rows=src.enc_rows, enc_row_starts=src.enc_row_starts)
    info = {"restart": int(d.get("restart", 0)), "reasons": {"col_exhausted": 0, "deg1_check": 0, "info_free_block_row": 0},
            "seconds": round(time.perf_counter() - t0, 3), "frozen": cfg.frozen,
            "block_row_deg_hist": {int(a): int(b) for a, b in zip(*np.unique(row_deg, return_counts=True))},
            "info_free_block_rows": int((row_deg == 0).sum()), "n_edges": int(code.edge_chk.size),
            "deg_cap": None}
    return code, info


_BUILT: dict[str, dict] = {}
_CFG: dict[str, object] = {}


def edge_sha(code: construct.Code) -> str:
    """Digest of the sorted edge arrays: the identity of the decoding graph (prep review 2026-09-30:
    the parent's audit and every worker's rebuild are compared on it)."""
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(code.edge_chk, np.int64).tobytes())
    h.update(np.ascontiguousarray(code.edge_var, np.int64).tobytes())
    return h.hexdigest()[:20]


def split_hint(hint):
    """A job's restart hint: None | restart | [restart, edge_sha] (the latter from s0 lines written
    since the 2026-09-30 prep review)."""
    if isinstance(hint, (list, tuple)):
        return hint[0], hint[1]
    return hint, None


def check_registered(rid: str, cfg, sha: str | None) -> None:
    """Refuse to decode with a code that is not the one audited: a registry name reused for a
    different config in this process, or a rebuild whose edges differ from the audited draw."""
    if _CFG.get(rid) is not None and _CFG[rid] != cfg:
        raise RuntimeError(f"registry name collision in worker: {rid} registered for a different config")
    if sha is not None and _BUILT[rid].get("edge_sha") != sha:
        raise RuntimeError(f"{rid}: worker rebuild edge digest {_BUILT[rid].get('edge_sha')} != audited {sha}")


def register(cfg: Cfg, restart_hint: int | None = None, sha: str | None = None) -> str:
    """Build (once per process) and register into holo's LADDER/_CODE_CACHE."""
    rid = cfg.name
    if not (rid in construct._CODE_CACHE and rid in _BUILT):
        code, info = build(cfg, restart_hint)
        info["edge_sha"] = edge_sha(code)
        construct.LADDER[rid] = code.spec
        construct._CODE_CACHE[rid] = code
        _BUILT[rid] = info
        _CFG[rid] = cfg
    check_registered(rid, cfg, sha)
    return rid


# ---------------------------------------------------------------- (iii) audit
def screen0(cfgd: dict) -> dict:
    """Build + structural audit + constraint verdict (runs in a worker)."""
    cfg = Cfg.from_dict(cfgd)
    t = time.process_time()
    rec = {"rid": cfg.name, "screen": "s0", "k": cfg.k, "tag": cfg.tag, "seed": cfg.seed,
           "baseline": cfg.baseline, "cfg": cfg.to_dict()}
    try:
        rid = register(cfg)
    except BuildFail as e:
        rec.update(status="reject", reasons=[e.reason], build=e.info, cpu=time.process_time() - t)
        return rec
    info = _BUILT[rid]
    st = hstruct.stats(rid)
    keep = ("n_edges", "chk_deg_hist", "chk_deg_min", "chk_deg_max", "chk_deg_mean", "n_chk_no_info_edge",
            "var_deg_hist", "girth_gt4", "HHt_offdiag_max", "min_w1", "w1_le8", "min_w2", "argmin_w2", "n_w2_le8")
    reasons = []
    if not st["girth_gt4"]:
        reasons.append("girth<=4")
    if info["info_free_block_rows"]:
        reasons.append(f"info_free_block_rows={info['info_free_block_rows']}")
    if st["min_w2"] is not None and st["min_w2"] < 10:
        reasons.append(f"min_w2={st['min_w2']}<10")
    rec.update(status="reject" if reasons else "pass", reasons=reasons, build=info,
               struct={kk: st[kk] for kk in keep}, cpu=time.process_time() - t)
    return rec


def verify_baseline(k: int) -> bool:
    """The generalized draw reproduces the frozen recipe edge-for-edge (harness data)."""
    if k in FROZEN_RUNGS:          # the rows ARE the production codes: check the re-keyed copy
        ok = True
        for fr in FROZEN_RUNGS[k]:
            rid = register(frozen_cfg(fr))
            a, b = construct._CODE_CACHE[rid], construct.load_code(fr)
            ok &= bool(np.array_equal(a.edge_chk, b.edge_chk) and np.array_equal(a.edge_var, b.edge_var))
        return ok
    cfg = baseline_cfg(k)
    rid = register(cfg)
    a, b = construct._CODE_CACHE[rid], hcodes.code(BASELINE_RID[k])
    return bool(np.array_equal(a.edge_chk, b.edge_chk) and np.array_equal(a.edge_var, b.edge_var))


def incumbent_floor(k: int) -> int:
    """min(w1, w2) of the WEAKEST frozen production code at a frozen-rung k (harness structure.stats on
    the registered base row): the screen-1 floor there, so a searched code is never structurally weaker
    than a code already in production.  The fixed floor 16 (or 10) would leave these rows empty: seed-0
    feasibility scan 2026-09-30, max min(w1, w2) over all built configs 17 / 13 / 12 / 8 / 6 at
    k = 2240 / 2560 / 2880 / 3200 / 3520."""
    ws = []
    for fr in FROZEN_RUNGS[k]:
        st = hstruct.stats(register(frozen_cfg(fr)))
        ws.append(min(st["min_w1"], st["min_w2"]))
    return min(ws)


def baseline_cfgs(k: int) -> list[Cfg]:
    """The named baseline rows at k: the frozen recipe draw (primary/secondary k) or the frozen
    production codes (FROZEN_RUNGS)."""
    return [frozen_cfg(r) for r in FROZEN_RUNGS[k]] if k in FROZEN_RUNGS else [baseline_cfg(k)]


# ---------------------------------------------------------------- (iv) channels
def sigma_of(db: float) -> float:
    return math.sqrt(1 / (2 * 10 ** (db / 10)))


def run_chan(rid: str, channel: str, params: dict, t0: int, n: int) -> dict:
    """harness channels.run_task for bsc / awgn / eras (SAME generator consumption per trial, so the
    same counts — checked against it in --smoke) plus the robustness channel, and a diagnostic of
    every syndrome-valid wrong decode: (trial, total error weight, info error weight)."""
    from holo.core.ldpc.decode import decode
    k = construct.LADDER[rid].k_bits
    base = BASE_ROBUST if channel == "robust" else ch.BASE[channel]
    fails = und = iters = iters_ok = n_ok = 0
    und_w = []
    for t in range(t0, t0 + n):
        g = np.random.default_rng(base + t)
        info = g.integers(0, 2, k).astype(np.uint8)
        cw = encode(info, rid)
        if channel == "bsc":
            p = params["p"]
            llr = ch.hard_llr(cw ^ (g.random(N) < p), p)
        elif channel == "awgn":
            s = params["sigma"]
            llr = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
        elif channel == "eras":
            p, eps = params["p"], params["eps"]
            llr = ch.hard_llr(cw ^ (g.random(N) < p), p)
            llr[g.random(N) < eps] = 0.0
        elif channel == "robust":
            # BIAWGN + a Bernoulli(f) set of cells given a CONFIDENTLY WRONG LLR of magnitude 20
            s, f = params["sigma"], params["f"]
            llr = -2.0 * ((1.0 - 2.0 * cw) + s * g.standard_normal(N)) / (s * s)
            bad = g.random(N) < f
            llr[bad] = 20.0 * (1.0 - 2.0 * cw[bad])      # bit 1 -> -20, bit 0 -> +20 (house: + = 1)
        else:
            raise ValueError(channel)
        ok, hard, n_it = decode(llr, rid)
        good = ok and np.array_equal(hard, cw)
        if not good:
            fails += 1
            if ok:
                und += 1
                e = hard ^ cw
                und_w.append([t, int(e.sum()), int(e[:k].sum())])
        else:
            iters_ok += n_it
            n_ok += 1
        iters += n_it
    return {"n": n, "fails": fails, "undetected": und, "iters": iters, "iters_ok": iters_ok, "n_ok": n_ok,
            "und_w": und_w}


# ---------------------------------------------------------------- decoder selection
# prod = holo.core.ldpc.decode.decode one trial at a time (run_chan); fast = fast/fastdecode.decode_batch
# over the whole chunk (fast/tasks_fast.run_chan_fast), bit-exact twin (fast/README, test_fastdecode.py,
# test_tasks_fast.py).  The PARENT decides (select_decoder, incl. the start-up selfcheck) and hands the
# verdict to the spawned workers through the environment; a worker never re-decides.
FAST_DIR = SEARCH / "fast"
DECODER_ENV = "SEARCH_DECODER"


def decoder() -> str:
    return os.environ.get(DECODER_ENV, "fast")


def _fast():
    if str(FAST_DIR) not in sys.path:
        sys.path.insert(0, str(FAST_DIR))
    import tasks_fast  # noqa: PLC0415
    return tasks_fast


def select_decoder(requested: str, rids) -> str:
    """Parent only, BEFORE any decoding pool spawns: `fast` needs fastdecode.selfcheck (24 trials vs
    production decode) to pass on every rid given (the run's first registered codes); on a failure the
    run falls back to `prod` with a loud line.  Sets SEARCH_DECODER for the workers; returns the verdict."""
    use = requested
    if requested == "fast":
        _fast()
        import fastdecode  # noqa: PLC0415
        for rid in rids:
            t = time.time()
            ok = fastdecode.selfcheck(rid)
            print(f"[decoder] fastdecode.selfcheck({rid}) = {ok} ({time.time() - t:.1f} s)", file=sys.stderr, flush=True)
            if not ok:
                print("\n" + "!" * 100 + f"\n[decoder] FAST DECODER SELFCHECK FAILED on {rid} -- FALLING BACK TO THE "
                      "PRODUCTION DECODER (about 1.5x slower; the run's wall estimate no longer holds)\n" + "!" * 100,
                      file=sys.stderr, flush=True)
                use = "prod"
                break
    os.environ[DECODER_ENV] = use
    print(f"[decoder] using {use} (requested {requested})", file=sys.stderr, flush=True)
    return use


def run_chan_any(rid: str, channel: str, params: dict, t0: int, n: int) -> dict:
    if decoder() == "fast":
        return _fast().run_chan_fast(rid, channel, params, t0, n, batch=min(n, 64))
    return run_chan(rid, channel, params, t0, n)


def task_chan(cfgd: dict, restart: int, channel: str, params: dict, t0: int, n: int) -> dict:
    t = time.process_time()
    restart, sha = split_hint(restart)
    rid = register(Cfg.from_dict(cfgd), restart, sha)
    r = run_chan_any(rid, channel, params, t0, n)
    return {"n": r["n"], "fails": r["fails"], "und": r["undetected"], "iters": r["iters"],
            "iters_ok": r["iters_ok"], "n_ok": r["n_ok"], "und_w": r["und_w"], "cpu": time.process_time() - t}


def check_channels_vs_harness(rid: str = "r0313") -> bool:
    """run_chan == harness channels.run_task on counts (bsc/awgn/eras), one chunk each."""
    ok = True
    for chn, prm in (("bsc", {"p": 0.13}), ("awgn", {"esn0_db": -4.0, "sigma": sigma_of(-4.0)}),
                     ("eras", {"eps": 0.3, "p": 0.05})):
        a = run_chan(rid, chn, prm, 0, 30)
        b = ch.run_task(rid, chn, prm, 0, 30)
        ok &= all(a[x] == b[x] for x in ("fails", "undetected", "iters", "iters_ok", "n_ok"))
    return ok


def frozen_points(k: int) -> dict:
    """The frozen recipe's measured 10 % points (harness results.json, 200 trials/pt)."""
    rid = ref_rid(k)
    res = json.loads((WORK / "results.json").read_text())
    P = [p for p in res["points"] if p["rid"] == rid]
    aw = [(p["params"]["esn0_db"], p["bler"], p["n"]) for p in P if p["channel"] == "awgn"]
    bs = [(p["params"]["p"], p["bler"], p["n"]) for p in P if p["channel"] == "bsc"]
    R = k / N
    return {"rid": rid, "es10": htables.interp_x(aw, 0.10, False), "p10": htables.interp_x(bs, 0.10, True),
            "es1": htables.interp_x(aw, 0.01, False), "p1": htables.interp_x(bs, 0.01, True),
            "shannon_db": ch.biawgn_shannon_esn0_db(R), "p_cap": ch.bsc_capacity_p(R)}


# ---------------------------------------------------------------- (v) engine
@dataclass
class Req:
    channel: str
    params: dict
    n: int
    t0: int = 0
    fails: int = 0
    und: int = 0
    iters: int = 0
    iters_ok: int = 0
    n_ok: int = 0
    got: int = 0
    cpu: float = 0.0
    und_w: list = field(default_factory=list)

    def add(self, r):
        self.und_w += r.get("und_w", [])
        self.fails += r["fails"]; self.und += r["und"]; self.iters += r["iters"]
        self.iters_ok += r["iters_ok"]; self.n_ok += r["n_ok"]; self.got += r["n"]; self.cpu += r["cpu"]

    @property
    def x(self):
        return self.params["p"] if self.channel in ("bsc",) else self.params.get("esn0_db")

    def rec(self):
        return {"channel": self.channel, "params": self.params, "t0": self.t0, "n": self.got,
                "fails": self.fails, "und": self.und, "bler": self.fails / self.got if self.got else None,
                "mean_iters": self.iters / self.got if self.got else None, "cpu": round(self.cpu, 3),
                "und_w": self.und_w}


@dataclass
class Call:
    fn: object
    args: tuple
    result: object = None


class Job:
    def __init__(self, gen, prio: int, cfgd: dict, restart: int, on_done, on_error=None):
        self.gen, self.prio, self.cfgd, self.restart, self.on_done = gen, prio, cfgd, restart, on_done
        self.on_error = on_error
        self.reqs: list = []
        self.pending = 0
        self.dead = False


def _winit():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


class Runner:
    def __init__(self, workers: int, chunk: int):
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        os.environ.setdefault("OMP_NUM_THREADS", "1")
        os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")   # this numpy links Apple Accelerate (fast/README)
        self.workers, self.chunk = workers, chunk
        self.ex = ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"),
                                      initializer=_winit)
        self.queue: list = []
        self.seq = itertools.count()
        self.inflight: dict = {}
        self.stop = False
        self.errors = 0
        self.chunks_done = 0
        self.decodes = 0

    def start(self, gen, prio, cfgd, restart, on_done, on_error=None):
        job = Job(gen, prio, cfgd, restart, on_done, on_error)
        self._advance(job, None)

    def _advance(self, job: Job, value):
        try:
            reqs = job.gen.send(value)
        except StopIteration as e:
            job.on_done(e.value)
            return
        job.reqs = reqs
        job.pending = 0
        for rq in reqs:
            if isinstance(rq, Call):
                heapq.heappush(self.queue, (job.prio, next(self.seq), job, rq, None))
                job.pending += 1
            else:
                for t0 in range(rq.t0, rq.t0 + rq.n, self.chunk):
                    n = min(self.chunk, rq.t0 + rq.n - t0)
                    heapq.heappush(self.queue, (job.prio, next(self.seq), job, rq, (t0, n)))
                    job.pending += 1
        if job.pending == 0:
            self._advance(job, reqs)

    def _fill(self):
        while self.queue and len(self.inflight) < 3 * self.workers and not self.stop:
            prio, _, job, rq, tn = heapq.heappop(self.queue)
            if job.dead:
                continue
            if isinstance(rq, Call):
                f = self.ex.submit(rq.fn, *rq.args)
            else:
                f = self.ex.submit(task_chan, job.cfgd, job.restart, rq.channel, rq.params, tn[0], tn[1])
            self.inflight[f] = (job, rq)

    def loop(self, tick=None, tick_s: float = 30.0):
        last = time.time()
        while not self.stop:
            self._fill()
            if not self.inflight:
                break
            done, _ = wait(list(self.inflight), timeout=5, return_when=FIRST_COMPLETED)
            for f in done:
                job, rq = self.inflight.pop(f)
                try:
                    r = f.result()
                except Exception as e:  # noqa: BLE001
                    self.errors += 1
                    first = not job.dead
                    job.dead = True
                    print(f"[error] {job.cfgd.get('rid') or job.cfgd['tag']}: {e!r}", file=sys.stderr, flush=True)
                    # prep review 2026-09-30: a dead job used to vanish without calling back, so its
                    # stage counter never reached 0 and the WHOLE k silently skipped screen 2 while
                    # the run reported "finished".  Now the stage proceeds without the code (no line is
                    # written, so a rerun retries it) and the driver exits non-zero.
                    if first and job.on_error is not None and not self.stop:
                        job.on_error(e)
                    continue
                if job.dead:
                    continue
                if isinstance(rq, Call):
                    rq.result = r
                else:
                    rq.add(r)
                    self.decodes += r["n"]
                self.chunks_done += 1
                job.pending -= 1
                if job.pending == 0:
                    self._advance(job, job.reqs)
            if tick and time.time() - last > tick_s:
                tick()
                last = time.time()
        if self.stop:
            self.ex.shutdown(wait=False, cancel_futures=True)
        else:
            self.ex.shutdown(wait=True)


@dataclass
class Settings:
    s1_trials: int = 100
    walk_trials: int = 200
    fine_trials: int = 500
    side_trials: int = 200
    n_finalists: int = 16
    n_fine: int = 4
    seedvar_configs: int = 2
    chunk: int = 50
    workers: int = 13
    ks: tuple = (1664, 1280)
    min_w2: int = 10                # screen-0 pair-weight floor (protocol 10; trial-A2 saw w10..w26 two-info-bit words hit)
    min_w2_final: int | None = None  # floor for FINALIST selection (None -> min_w2); also floors min w1
    max_walk_pts: int = 40          # per channel: an error-floor code never reads 0/n twice on the easy awgn side
    s1_anchor: dict | None = None   # {k: {"es10", "p10", "src"}}; None -> the frozen recipe's 10 % points
    min_w2_by_k: dict | None = None  # per-k override of min_w2 (frozen rungs: high-rate e-IRA pair weights are low)
    decoder: str = "fast"           # recorded in the run's meta line; the workers read SEARCH_DECODER


def anchor_from(out: Path, ks) -> dict:
    """Screen-1 anchor from an earlier run: the 10 % points of its best CLEAN walked code per k
    (lowest Es/N0@1 %, no undetected decode in any screen). The frozen recipe's 10 % points
    saturate screen 1 once codes are ~0.4 dB better (trial-A, k=1280: 0/100 at all four points)."""
    done, _ = load(out)
    res = {}
    for k in ks:
        cands = []
        for (rid, scr), r in done.items():
            if scr != "s2walk" or r["k"] != k or rid.startswith("base-") or r["es1"] is None:
                continue
            if undetected(done, rid)[0]:
                continue
            b = done.get((rid, "s2fine")) or r
            cands.append((b["es1"], rid, r))
        if cands:
            _, rid, r = min(cands)
            res[k] = {"es10": r["es10"], "p10": r["p10"], "src": f"{out.name}:{rid}"}
    return res


SWEEPS = ("s1", "s2walk", "s2fine")   # the protocol's "finalist sweeps"; s2side (adversarial) reported apart


def undetected(done: dict, rid: str, screens=SWEEPS) -> tuple[int, int, list]:
    und = ntr = 0
    ws = []
    for s in screens:
        for p in done.get((rid, s), {}).get("points", []):
            und += p["und"]; ntr += p["n"]
            ws += [[p["channel"], p["params"].get("p", p["params"].get("esn0_db"))] + w for w in p.get("und_w", [])]
    return und, ntr, ws


def s1_points(fz: dict, trials: int) -> list[Req]:
    """fz = the anchor: {"es10", "p10"}."""
    out = []
    for off in S1_AWGN_OFFSETS_DB:
        db = round(fz["es10"] + off, 4)
        out.append(Req("awgn", {"esn0_db": db, "sigma": sigma_of(db)}, trials))
    for off in S1_BSC_OFFSETS:
        out.append(Req("bsc", {"p": round(fz["p10"] + off, 5)}, trials))
    return out


def s1_score(pts: list[dict]) -> float:
    return float(np.mean([math.log(max(p["fails"] / p["n"], 0.5 / p["n"])) for p in pts]))


def frontier(points: list[dict], k: int) -> dict:
    """1 % / 10 % points + gaps from a list of point records (bsc and awgn)."""
    R = k / N
    aw = [(p["params"]["esn0_db"], p["fails"] / p["n"], p["n"]) for p in points if p["channel"] == "awgn"]
    bs = [(p["params"]["p"], p["fails"] / p["n"], p["n"]) for p in points if p["channel"] == "bsc"]
    e1, e10 = htables.interp_x(aw, 0.01, False), htables.interp_x(aw, 0.10, False)
    p1, p10 = htables.interp_x(bs, 0.01, True), htables.interp_x(bs, 0.10, True)
    sh = ch.biawgn_shannon_esn0_db(R)
    return {"es1": e1, "es10": e10, "p1": p1, "p10": p10,
            "gap_db": None if e1 is None else e1 - sh,
            "gap_bit": None if p1 is None else (1 - ch.h2(p1)) - R}


def _merge_points(base: list[dict], extra: list[dict]) -> list[dict]:
    """Merge continuation trials into the walk's points (same channel + x)."""
    def key(p):
        return (p["channel"], round(p["params"].get("p", p["params"].get("esn0_db")), 6))
    out = {key(p): dict(p) for p in base}
    for q in extra:
        kq = key(q)
        if kq in out and q["t0"] > 0:
            a = out[kq]
            a["fails"] += q["fails"]; a["und"] += q["und"]; a["n"] += q["n"]
            a["bler"] = a["fails"] / a["n"]
        else:
            out[kq] = dict(q)
    return list(out.values())


class Search:
    def __init__(self, cfgs: list[Cfg], settings: Settings, out: Path, mode: str):
        self.S, self.out, self.mode = settings, Path(out), mode
        self.out.mkdir(parents=True, exist_ok=True)
        self.jsonl = self.out / "results.jsonl"
        self.done: dict[tuple[str, str], dict] = {}
        if self.jsonl.exists():
            for line in self.jsonl.read_text().splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self.done[(r["rid"], r["screen"])] = r
        self.cfgs = {c.name: c for c in cfgs}
        if len(self.cfgs) != len(cfgs):
            dup = sorted({c.name for c in cfgs if sum(1 for d in cfgs if d.name == c.name) > 1})
            raise ValueError(f"duplicate registry names in one search (configs would share a code): {dup[:5]}")
        self.by_k = {k: [c for c in cfgs if c.k == k] for k in settings.ks}
        self.fz = {k: frozen_points(k) for k in settings.ks}
        anc = settings.s1_anchor or {}
        self.anchor = {k: (anc.get(k) or {"es10": self.fz[k]["es10"], "p10": self.fz[k]["p10"],
                                           "src": f"frozen {self.fz[k]['rid']}"}) for k in settings.ks}
        self.fh = open(self.jsonl, "a")
        self.t0 = time.time()
        self.cnt = {s: [0, 0] for s in ("s0", "s1", "s2walk", "s2fine", "s2side")}
        self.pend: dict = {}
        self.stage: dict[int, str] = {}
        meta = {"rid": "__meta__", "screen": f"run@{time.strftime('%Y-%m-%dT%H:%M:%S')}", "mode": mode,
                "settings": {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(settings).items()},
                "n_cfgs": len(cfgs), "frozen": {str(k): v for k, v in self.fz.items()},
                "anchor": {str(k): v for k, v in self.anchor.items()},
                "s1_offsets": {"awgn_db": S1_AWGN_OFFSETS_DB, "bsc": S1_BSC_OFFSETS},
                "argv": sys.argv}
        self._write(meta)

    def _write(self, rec: dict):
        self.fh.write(json.dumps(rec, default=float) + "\n")
        self.fh.flush()
        os.fsync(self.fh.fileno())
        if rec["rid"] != "__meta__":
            self.done[(rec["rid"], rec["screen"])] = rec

    # -------------------------------------------------------------- jobs
    def _job_s0(self, cfg: Cfg):
        c = Call(screen0, (cfg.to_dict(),))
        yield [c]
        return c.result

    def _job_s1(self, cfg: Cfg):
        reqs = s1_points(self.anchor[cfg.k], self.S.s1_trials)
        yield reqs
        pts = [r.rec() for r in reqs]
        return {"rid": cfg.name, "screen": "s1", "k": cfg.k, "tag": cfg.tag, "seed": cfg.seed,
                "anchor": self.anchor[cfg.k], "points": pts, "score": s1_score(pts), "cpu": sum(p["cpu"] for p in pts)}

    def _job_walk(self, cfg: Cfg):
        fz, n = self.anchor[cfg.k], self.S.walk_trials
        walks = [hsweep.Walk(cfg.name, "bsc", hsweep.grid_round(fz["p10"], 0.005), 0.005, True, n,
                             lambda p: {"p": p}),
                 hsweep.Walk(cfg.name, "awgn", hsweep.grid_round(fz["es10"], 0.25), 0.25, False, n,
                             lambda db: {"esn0_db": db, "sigma": sigma_of(db)})]
        allpts: list[dict] = []
        while True:
            batch = []
            for w in walks:
                if w.finished:
                    continue
                for pt in w.next_points():
                    batch.append((w, pt, Req(w.channel, pt.params, n)))
            if not batch:
                break
            for w in walks:                      # cap (prep review 2026-09-30): see Settings.max_walk_pts
                if not w.finished and len(w.points) > self.S.max_walk_pts:
                    w.finished = w.easy_done = w.hard_done = True
            batch = [b for b in batch if len(b[0].points) <= self.S.max_walk_pts]
            if not batch:
                break
            yield [b[2] for b in batch]
            for w, pt, rq in batch:
                pt.n, pt.fails, pt.und = rq.got, rq.fails, rq.und
                pt.iters, pt.iters_ok, pt.n_ok = rq.iters, rq.iters_ok, rq.n_ok
                allpts.append(rq.rec())
                w.on_point_done(round(rq.x, 6))
        fr = frontier(allpts, cfg.k)
        return {"rid": cfg.name, "screen": "s2walk", "k": cfg.k, "tag": cfg.tag, "seed": cfg.seed,
                "points": allpts, **fr, "cpu": sum(p["cpu"] for p in allpts)}

    def _job_fine(self, cfg: Cfg):
        walk = self.done[(cfg.name, "s2walk")]
        nf = self.S.fine_trials
        reqs = []
        for chn, harder_plus in (("awgn", False), ("bsc", True)):
            xs = sorted([(p["params"]["p"] if chn == "bsc" else p["params"]["esn0_db"], p["fails"] / p["n"], p)
                         for p in walk["points"] if p["channel"] == chn],
                        key=lambda t: t[0] if harder_plus else -t[0])
            br = next(((a, b) for a, b in zip(xs, xs[1:]) if a[1] <= 0.01 <= b[1] and b[1] > 0), None)
            if br is None:
                continue
            for x, _, p in br:
                if nf > p["n"]:
                    reqs.append(Req(chn, p["params"], nf - p["n"], t0=p["n"]))
            mid = round((br[0][0] + br[1][0]) / 2, 6)
            reqs.append(Req(chn, {"p": mid} if chn == "bsc" else {"esn0_db": mid, "sigma": sigma_of(mid)}, nf))
        yield reqs
        pts = [r.rec() for r in reqs]
        merged = _merge_points(walk["points"], pts)
        return {"rid": cfg.name, "screen": "s2fine", "k": cfg.k, "tag": cfg.tag, "seed": cfg.seed,
                "points": pts, **frontier(merged, cfg.k), "cpu": sum(p["cpu"] for p in pts)}

    def _job_side(self, cfg: Cfg):
        walk = self.done[(cfg.name, "s2walk")]
        es = walk["es1"] if walk["es1"] is not None else self.anchor[cfg.k]["es10"]
        n = self.S.side_trials
        reqs = [Req("robust", {"esn0_db": round(es, 4), "sigma": sigma_of(es), "f": f}, n) for f in ROBUST_F]
        reqs.append(Req("awgn", {"esn0_db": round(es, 4), "sigma": sigma_of(es)}, n))
        reqs.append(Req("eras", dict(ERAS_POINT), n))
        yield reqs
        pts = [r.rec() for r in reqs]
        return {"rid": cfg.name, "screen": "s2side", "k": cfg.k, "tag": cfg.tag, "seed": cfg.seed,
                "points": pts, "esn0_db": es, "cpu": sum(p["cpu"] for p in pts)}

    # -------------------------------------------------------------- orchestration
    def _restart(self, cfg):
        s0 = self.done.get((cfg.name, "s0"))
        if not (s0 and "restart" in s0.get("build", {})):
            return None
        b = s0["build"]
        return [b["restart"], b["edge_sha"]] if b.get("edge_sha") else b["restart"]

    def _launch(self, screen, cfg, then):
        key = (cfg.name, screen)
        if key in self.done and self._valid(screen, cfg, self.done[key]):
            then(self.done[key])
            return
        gen = {"s0": self._job_s0, "s1": self._job_s1, "s2walk": self._job_walk,
               "s2fine": self._job_fine, "s2side": self._job_side}[screen](cfg)
        prio = {"s0": 3, "s1": 2, "s2walk": 1, "s2fine": 0, "s2side": 0}[screen]
        self.cnt[screen][1] += 1

        def done(rec):
            self._write(rec)
            self.cnt[screen][0] += 1
            then(rec)

        def err(e):
            self.cnt[screen][0] += 1
            then(None)            # every `then` of the stage machine tolerates a missing record
        self.runner.start(gen, prio, cfg.to_dict(), self._restart(cfg), done, err)

    def _valid(self, screen, cfg, rec) -> bool:
        """An s1 line is only reusable under the same anchor (older lines without one = frozen), and
        every screen-1/2 line only at this run's trial counts (prep review 2026-09-30: a rerun into the
        same --out with other counts, or a copied line, reused walks/fine/side of another size)."""
        if screen == "s0":
            return True
        pts = rec.get("points") or []
        want = {"s1": self.S.s1_trials, "s2walk": self.S.walk_trials, "s2side": self.S.side_trials,
                "s2fine": self.S.fine_trials}[screen]
        if screen == "s2fine":
            if pts and max(p["n"] for p in pts) != want:
                return False
        elif any(p["n"] != want for p in pts):
            return False
        if screen != "s1":
            return True
        a = rec.get("anchor") or {"es10": self.fz[cfg.k]["es10"], "p10": self.fz[cfg.k]["p10"]}
        b = self.anchor[cfg.k]
        return abs(a["es10"] - b["es10"]) < 1e-9 and abs(a["p10"] - b["p10"]) < 1e-9

    def _clean(self, c) -> bool:
        return undetected(self.done, c.name)[0] == 0

    def _dec(self, k, stage):
        self.pend[(k, stage)] -= 1
        if self.pend[(k, stage)] == 0:
            {"a": self._stage_walk, "w": self._stage_final, "f": self._stage_done}[stage](k)

    def _eligible(self, cfg):
        s0 = self.done.get((cfg.name, "s0"))
        if s0 is None:
            return False
        if cfg.baseline:
            return "restart" in s0["build"]
        st = s0.get("struct", {})
        # the single-info-bit weight is floored with the pair weight (B2 trial: a min-w1-10 code threw a
        # weight-10 one-info-bit wrong decode; plain e-IRA codes measured min w1 >= 25, so no effect there)
        ok = s0["status"] == "pass" or (s0["status"] == "reject" and all(x.startswith("min_w2=") for x in s0["reasons"]))
        return ok and min(st.get("min_w2") or 0, st.get("min_w1") or 0) >= self.floor(cfg.k)

    def floor(self, k: int) -> int:
        """Screen-1 eligibility floor on min(w1, w2) at k (Settings.min_w2, per-k override)."""
        return int((self.S.min_w2_by_k or {}).get(k, (self.S.min_w2_by_k or {}).get(str(k), self.S.min_w2)))

    def _final_ok(self, cfg) -> bool:
        """Finalist floor (Settings.min_w2_final): screen 1 measures every code over the protocol floor,
        finalist slots go only to codes whose min w1/w2 clear the stricter floor."""
        if cfg.baseline or self.S.min_w2_final is None:
            return True
        st = self.done.get((cfg.name, "s0"), {}).get("struct", {})
        return min(st.get("min_w2") or 0, st.get("min_w1") or 0) >= self.S.min_w2_final

    def _stage_a(self, k):
        cs = self.by_k[k]
        self.pend[(k, "a")] = len(cs) + 1
        for c in cs:
            def after_s0(rec, c=c):
                if self._eligible(c):
                    self._launch("s1", c, lambda r: self._dec(k, "a"))
                else:
                    self._dec(k, "a")
            self._launch("s0", c, after_s0)
        self._dec(k, "a")

    def finalists(self, k) -> tuple[list[Cfg], list[Cfg]]:
        cs = [c for c in self.by_k[k] if (c.name, "s1") in self.done and self._valid("s1", c, self.done[(c.name, "s1")])]
        base = [c for c in cs if c.baseline]
        ranked = sorted([c for c in cs if not c.baseline and self._final_ok(c)],
                        key=lambda c: (self.done[(c.name, "s1")]["score"], c.name))
        top = ranked[: self.S.n_finalists]
        groups: dict[str, list[Cfg]] = {}
        for c in [c for c in self.by_k[k] if not c.baseline]:
            groups.setdefault(c.tag, []).append(c)
        full = {t: g for t, g in groups.items() if len(g) > 1 and all((c.name, "s1") in self.done for c in g)}
        order = sorted(full, key=lambda t: statistics.mean(self.done[(c.name, "s1")]["score"] for c in full[t]))
        extra = [c for t in order[: self.S.seedvar_configs] for c in full[t] if c not in top]
        return top + base, extra

    def _stage_walk(self, k):
        self.stage[k] = "walk"
        top, extra = self.finalists(k)
        todo = top + extra
        self.pend[(k, "w")] = len(todo) + 1
        for c in todo:
            self._launch("s2walk", c, lambda r: self._dec(k, "w"))
        self._dec(k, "w")

    def _stage_final(self, k):
        self.stage[k] = "final"
        top, extra = self.finalists(k)
        walked = [c for c in top if (c.name, "s2walk") in self.done]
        cand = sorted([c for c in walked if not c.baseline],
                      key=lambda c: (not self._clean(c), self.done[(c.name, "s2walk")]["es1"] or 99,
                                     -(self.done[(c.name, "s2walk")]["p1"] or 0)))
        fine = cand[: self.S.n_fine] + [c for c in walked if c.baseline]
        self.pend[(k, "f")] = len(fine) + len(walked) + 1
        for c in fine:
            self._launch("s2fine", c, lambda r: self._dec(k, "f"))
        for c in walked:
            self._launch("s2side", c, lambda r: self._dec(k, "f"))
        self._dec(k, "f")

    def _stage_done(self, k):
        self.stage[k] = "done"
        print(f"[{time.time() - self.t0:7.0f}s] k={k} DONE", file=sys.stderr, flush=True)

    def progress(self):
        el = time.time() - self.t0
        c = " ".join(f"{s} {a}/{b}" for s, (a, b) in self.cnt.items())
        rate = self.runner.decodes / el if el else 0
        print(f"[{el:7.0f}s] {c} | stages {self.stage} | decodes {self.runner.decodes} ({rate:.0f}/s) "
              f"queue {len(self.runner.queue)} errors {self.runner.errors}", file=sys.stderr, flush=True)

    def run(self):
        self.runner = Runner(self.S.workers, self.S.chunk)

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


EXIT_STOPPED, EXIT_ERRORS = 130, 3


def term_as_interrupt() -> None:
    """Before Search.run installs its clean-stop handler (baseline verification, B1's DE stage), a
    SIGTERM would kill the driver outright and orphan pool workers; raise KeyboardInterrupt instead so
    context-managed pools shut down.  Search.run replaces this with the clean stop."""
    def h(signum, frame):
        raise KeyboardInterrupt(f"signal {signum}")
    signal.signal(signal.SIGTERM, h)
    signal.signal(signal.SIGINT, h)


def exit_status(finished: bool, errors: int) -> None:
    """Driver exit code for run_overnight.sh: 0 done, 130 stopped by a signal (rerun resumes),
    3 finished with worker errors (the codes that failed wrote no line: a rerun retries them)."""
    if not finished:
        sys.exit(EXIT_STOPPED)
    if errors:
        sys.exit(EXIT_ERRORS)


# ---------------------------------------------------------------- (vi) summarize
def _f(x, d=3):
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{d}f}"


def _cfg_short(c: dict) -> str:
    m = dict(tuple(x) for x in c.get("meta", []))
    if m:
        return f"h{m['heavy_deg']} f{m['heavy_frac']:.1f} l{m['light']} {c['placement'][:3]} s{c['seed']}"
    return f"{c['tag']} s{c['seed']}"


def tier_of(z0: dict) -> str:
    """Which search a code came from: recipe (frozen baseline), A (recipe space), B1 (DE profile),
    B2 (ARA/IRAA variant of an A config)."""
    if z0.get("baseline"):
        return "recipe"
    if "variant" in z0 or "variant" in z0.get("cfg", {}):
        return "B2"
    return "B1" if "-B1-" in z0.get("tag", "") else "A"


def load(out: Path) -> tuple[dict, list[dict]]:
    done, metas = {}, []
    for line in (Path(out) / "results.jsonl").read_text().splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r["rid"] == "__meta__":
            metas.append(r)
        else:
            done[(r["rid"], r["screen"])] = r
    return done, metas


def summarize(out: Path) -> Path:
    out = Path(out)
    done, metas = load(out)
    meta = metas[-1] if metas else {}
    ks = sorted({r["k"] for r in done.values()}, reverse=True)
    s0 = {rid: r for (rid, s), r in done.items() if s == "s0"}
    L = [f"# Construction search — {out.name}", "",
         f"Mode `{meta.get('mode')}`; settings `{json.dumps(meta.get('settings'))}`; runs logged: {len(metas)}.  ",
         f"Decoder: production schedule `holo.core.ldpc.decode` (min-sum α 0.8, 60 it + one sum-product retry); "
         f"runs executed with {sorted({str((m.get('settings') or {}).get('decoder', 'prod')) for m in metas})} "
         "(fast = fast/fastdecode.py, the bit-exact batched twin: identical outcomes).  "
         "Seeds: bsc 100000+t, awgn 200000+t, eras 300000+t, robust 500000+t (common random numbers across codes).  ",
         f"Screen 1 = 4 points at the frozen recipe's 10 % points: awgn +{S1_AWGN_OFFSETS_DB} dB, bsc +{S1_BSC_OFFSETS}; "
         "score = mean ln BLER (0/n floored at 0.5/n), lower is better.  ",
         "Walks start at the frozen 10 % grid point (0.25 dB / 0.005 grids of the harness), easy side until two "
         "consecutive 0/n, hard side until BLER ≥ 0.5; 1 %/10 % by log-linear interpolation (harness tables.interp_x). "
         "`fine` = top-N at the fine trial count on the bracketing grid points + midpoint.  ",
         "Constraints: girth > 4, no info-free block row; screen 1 only for codes with min(w1, w2) ≥ the run's floor "
         f"(settings `min_w2` {(meta.get('settings') or {}).get('min_w2')}, per-k `min_w2_by_k` "
         f"{(meta.get('settings') or {}).get('min_w2_by_k')}; the `reject` column shows the protocol's fixed w2 < 10 flag). "
         "Search configs RESTART on an info-free block row (rule e); baselines are the frozen recipe exactly.", ""]
    cpu_total = sum(r.get("cpu", 0) or 0 for r in done.values())
    L.append(f"Total worker CPU recorded: {cpu_total / 3600:.2f} h over {len(s0)} built configs.\n")
    for k in ks:
        fz = next((m["frozen"][str(k)] for m in reversed(metas) if str(k) in m.get("frozen", {})), {})
        R = k / N
        L += [f"## k = {k} (R = {R:.4f}); Shannon {_f(fz.get('shannon_db'))} dB, p_cap {_f(fz.get('p_cap'), 4)}; "
              f"frozen recipe ({fz.get('rid')}, harness 200/pt): Es/N0@1% {_f(fz.get('es1'))}, @10% {_f(fz.get('es10'))}, "
              f"p@1% {_f(fz.get('p1'), 4)}, p@10% {_f(fz.get('p10'), 4)}", ""]
        # finalists
        walked = [r for (rid, s), r in done.items() if s == "s2walk" and r["k"] == k]
        base = [r for r in walked if s0.get(r["rid"], {}).get("baseline")]
        base.sort(key=lambda r: r["rid"] != f"base-{fz.get('rid')}")      # the anchor's frozen code is the Δ reference
        b_es = None
        if base:
            bf = done.get((base[0]["rid"], "s2fine")) or base[0]
            b_es = bf["es1"]

        def best(rid):
            return done.get((rid, "s2fine")) or done.get((rid, "s2walk"))
        walked.sort(key=lambda r: (undetected(done, r["rid"])[0] > 0 and not r["rid"].startswith("base-"),
                                   best(r["rid"])["es1"] if best(r["rid"])["es1"] is not None else 99,
                                   -(best(r["rid"])["p1"] or 0)))
        anc = next((m.get("anchor", {}).get(str(k)) for m in reversed(metas) if m.get("anchor", {}).get(str(k))), None)
        if anc:
            L += [f"Screen-1 anchor (10 % points the four screen-1 points hang off): Es/N0 {_f(anc['es10'])} dB, "
                  f"p {_f(anc['p10'], 4)} — from {anc.get('src')}", ""]
        L += ["### Finalists (screen 2), ranked by BIAWGN Es/N0 @ 1 % BLER — codes with any syndrome-valid wrong "
              "decode (⚠, DISQUALIFIED by the protocol) ranked last; `seedvar` = walked for the seed-variance table only", "",
              "| # | tier | code | config | restart (info-free restarts) | chk deg | min w1 / w2 | reject | s1 score | "
              "Es/N0@1% | @10% | gap dB | Δ vs recipe dB | p@1% | p@10% | gap bit | src | undet/trials | "
              "robust f0.1% / 0.2% / 0.5% / 1% (at own 1 % pt; clean) | eras ε0.3 p0.02 |",
              "|" + "---|" * 20]
        for i, r in enumerate(walked, 1):
            rid = r["rid"]; z0 = s0.get(rid, {}); b = best(rid); side = done.get((rid, "s2side"))
            st = z0.get("struct", {}); bd = z0.get("build", {})
            und, ntr, _ = undetected(done, rid)
            und_side = undetected(done, rid, ("s2side",))[0]
            rob = "—"; er = "—"
            if side:
                rp = {p["params"].get("f", 0): p for p in side["points"] if p["channel"] in ("robust", "awgn")}
                rob = " / ".join(f"{rp[f]['fails']}/{rp[f]['n']}" for f in ROBUST_F if f in rp) + \
                    (f" ({rp[0]['fails']}/{rp[0]['n']})" if 0 in rp else "") + (f" [{und_side} undet]" if und_side else "")
                e = next((p for p in side["points"] if p["channel"] == "eras"), None)
                er = f"{e['fails']}/{e['n']}" if e else "—"
            s1 = done.get((rid, "s1"), {}).get("score")
            name = ("**" + rid + "**") if z0.get("baseline") else rid
            L.append(f"| {i} | {tier_of(z0) if z0 else '?'} | {name} | {_cfg_short(z0.get('cfg', {}))} | {bd.get('restart')} "
                     f"({bd.get('reasons', {}).get('info_free_block_row', 0)}) | {st.get('chk_deg_min')}..{st.get('chk_deg_max')} | "
                     f"{st.get('min_w1')} / {st.get('min_w2')} | {'; '.join(z0.get('reasons', [])) or '—'} | {_f(s1, 2)} | "
                     f"{_f(b['es1'])} | {_f(b['es10'])} | {_f(b['gap_db'], 2)} | "
                     f"{_f(None if b_es is None or b['es1'] is None else b['es1'] - b_es, 2)} | {_f(b['p1'], 4)} | "
                     f"{_f(b['p10'], 4)} | {_f(b['gap_bit'], 3)} | {'fine' if (rid, 's2fine') in done else 'walk' if side else 'seedvar'} | "
                     f"{und}/{ntr}{' ⚠' if und else ''} | {rob} | {er} |")
        L.append("")
        uw = [(r["rid"], w) for r in walked for w in undetected(done, r["rid"], SWEEPS + ("s2side",))[2]]
        if uw:
            L += ["Syndrome-valid wrong decodes (channel, x, trial, error weight total / info): " +
                  "; ".join(f"{rid} {w[0]} {w[1]} t{w[2]} w{w[3]}/{w[4]}" for rid, w in uw[:40]) +
                  (" …" if len(uw) > 40 else ""), ""]
        # screen-1 ranking
        s1 = sorted([r for (rid, s), r in done.items() if s == "s1" and r["k"] == k], key=lambda r: r["score"])
        L += [f"### Screen 1 ranking (top 25 of {len(s1)} + baseline)", "",
              "| # | tier | code | config | score | awgn es10 / +0.25 | bsc p10 / +0.005 | min w2 | chk deg |", "|---|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(s1, 1):
            if i > 25 and not s0.get(r["rid"], {}).get("baseline"):
                continue
            z0 = s0.get(r["rid"], {}); st = z0.get("struct", {})
            pts = r["points"]
            L.append(f"| {i} | {tier_of(z0) if z0 else '?'} | {r['rid']} | {_cfg_short(z0.get('cfg', {}))} | {r['score']:.2f} | "
                     f"{pts[0]['fails']}/{pts[0]['n']} / {pts[1]['fails']}/{pts[1]['n']} | "
                     f"{pts[2]['fails']}/{pts[2]['n']} / {pts[3]['fails']}/{pts[3]['n']} | {st.get('min_w2')} | "
                     f"{st.get('chk_deg_min')}..{st.get('chk_deg_max')} |")
        L.append("")
        # screen-0 summary + factor marginals
        zk = [r for r in s0.values() if r["k"] == k and not r.get("baseline")]
        reasons: dict[str, int] = {}
        for r in zk:
            for x in r.get("reasons", []) or ["pass"]:
                reasons[x.split("=")[0]] = reasons.get(x.split("=")[0], 0) + 1
        L += [f"### Screen 0: {len(zk)} built/attempted; verdicts {json.dumps(reasons)}", ""]
        rows = []
        for fac in ("placement", "light", "heavy_frac", "heavy_deg"):
            groups: dict = {}
            for r in s1:
                z0 = s0.get(r["rid"], {})
                if z0.get("baseline"):
                    continue
                c = z0["cfg"]; m = dict(tuple(x) for x in c.get("meta", []))
                v = c["placement"] if fac == "placement" else m.get(fac)
                groups.setdefault(v, []).append(r["score"])
            for v in sorted(groups, key=str):
                g = groups[v]
                rows.append(f"| {fac} | {v} | {len(g)} | {statistics.mean(g):.2f} | {min(g):.2f} |")
        # info-free restarts by placement
        ifr: dict = {}
        for r in zk:
            if "restart" in r.get("build", {}):
                ifr.setdefault(r["cfg"]["placement"], []).append(r["build"]["reasons"]["info_free_block_row"])
        L += ["| factor | value | n | mean s1 score | best |", "|---|---|---|---|---|"] + rows + [""]
        L += ["Restarts rejected for an info-free block row (rule e), per placement: " +
              "; ".join(f"{p}: mean {statistics.mean(v):.1f}, max {max(v)}, zero in {sum(1 for x in v if x == 0)}/{len(v)}"
                        for p, v in ifr.items()), ""]
        # seed variance
        tags: dict = {}
        for r in s1:
            if not s0.get(r["rid"], {}).get("baseline"):
                tags.setdefault(r["tag"], []).append(r)
        within = [statistics.pstdev([x["score"] for x in g]) for g in tags.values() if len(g) > 1]
        means = [statistics.mean([x["score"] for x in g]) for g in tags.values() if len(g) > 1]
        L += ["### Seed variance", "",
              f"Screen-1 score: mean within-config SD {(_f(statistics.mean(within), 3) if within else '—')} "
              f"(over {len(within)} configs with ≥2 seeds) vs between-config SD of the config means "
              f"{(_f(statistics.pstdev(means), 3) if len(means) > 1 else '—')}.", "",
              "| config | seeds | s1 scores | Es/N0@10% per seed (walk) | spread dB | Es/N0@1% per seed (fine where run) | p@10% per seed | spread |",
              "|---|---|---|---|---|---|---|---|"]
        for t, g in sorted(tags.items(), key=lambda kv: statistics.mean(x["score"] for x in kv[1])):
            ws = [done.get((x["rid"], "s2fine")) and {**done[(x["rid"], "s2walk")], "es1": done[(x["rid"], "s2fine")]["es1"]}
                  or done.get((x["rid"], "s2walk")) for x in g]
            if sum(w is not None for w in ws) < 2:
                continue
            ws2 = [w for w in ws if w]
            e10 = [w["es10"] for w in ws2]; p10 = [w["p10"] for w in ws2]; e1 = [w["es1"] for w in ws2]
            ev = [x for x in e10 if x is not None]; pv = [x for x in p10 if x is not None]
            L.append(f"| {t} | {','.join(str(w['seed']) for w in ws2)} | {', '.join(f'{x['score']:.2f}' for x in g)} | "
                     f"{', '.join(_f(x) for x in e10)} | {_f(max(ev) - min(ev) if len(ev) > 1 else None, 3)} | "
                     f"{', '.join(_f(x) for x in e1)} | {', '.join(_f(x, 4) for x in p10)} | "
                     f"{_f(max(pv) - min(pv) if len(pv) > 1 else None, 4)} |")
        L.append("")
    path = out / "TABLES-search.md"
    path.write_text("\n".join(L) + "\n")
    return path


# ---------------------------------------------------------------- (vii) merge (appended by Tier B1)
def merge_runs(srcs, dest: Path) -> Path:
    """Union of several runs' results.jsonl into dest/results.jsonl (meta lines of every run kept in
    order; for a (rid, screen) present in more than one run the LAST source wins — identical rids are
    identical codes under common random numbers).  Screen-1 scores rank together only under the same
    anchor: a differing anchor per k is reported on stderr."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    metas, recs = [], {}
    anchors: dict[str, set] = {}
    for s in srcs:
        d, m = load(Path(s))
        metas += m
        recs.update(d)
        for mm in m:
            for k, v in (mm.get("anchor") or {}).items():
                anchors.setdefault(k, set()).add((round(v["es10"], 9), round(v["p10"], 9)))
    for k, v in anchors.items():
        if len(v) > 1:
            print(f"[merge] WARNING k={k}: runs used {len(v)} different screen-1 anchors {sorted(v)}; "
                  "screen-1 scores do not rank together", file=sys.stderr)
    with open(dest / "results.jsonl", "w") as fh:
        for m in metas:
            fh.write(json.dumps(m, default=float) + "\n")
        for r in recs.values():
            fh.write(json.dumps(r, default=float) + "\n")
    return dest
