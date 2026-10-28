"""JOB B — drill into what actually dominates the main thread.

The top-level pass showed the commit path is NOT the encode+digest of
batches. This pass ranks the `_absorb`/`_refresh` subtree and the derived
view rebuild against everything else, with edge-level attribution.
"""
from __future__ import annotations

import pstats
import sys
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "scratch/holo2-demo/cards-profile.pstats")
st = pstats.Stats(str(path))
S = st.stats
TOTAL = st.total_tt


def find(name, frag=""):
    return [f for f in S if f[2] == name and (not frag or frag in f[0])]


def pick(name, frag=""):
    hits = find(name, frag)
    return hits[0] if len(hits) == 1 else (hits[0] if hits else None)


def lab(f):
    return "?" if f is None else f"{Path(f[0]).name}:{f[1]}:{f[2]}"


def cum(f):
    return 0.0 if f is None else S[f][3]


def nc(f):
    return 0 if f is None else S[f][1]


def edge(callee, caller):
    if callee is None or caller is None:
        return (0.0, 0)
    for f, rec in S[callee][4].items():
        if f == caller:
            return (rec[3], rec[1])
    return (0.0, 0)


print(f"pstats total_tt = {TOTAL:.1f} s (profiled main-thread CPU)")
print(f"NOTE: cProfile taxes every Python CALL, so Python-heavy code is "
      f"over-weighted vs numpy C kernels. Shares, not seconds.\n")

# ---- the _absorb / _refresh subtree --------------------------------------
absorb = pick("_absorb", "orchestrator")
refresh = pick("_refresh", "orchestrator")
offer = pick("_offer", "orchestrator")
commit_o = pick("_commit", "orchestrator")
apply_o = pick("_apply", "orchestrator")
propose = pick("_propose", "orchestrator")
consult = pick("_maybe_consult", "orchestrator")
eng_apply = pick("apply", "core/commit.py")
build = pick("build", "tilemap.py")
skeys = pick("keys", "core/store.py")

print("=== the main thread, top down ===")
chain = [
    ("_propose  FIRE side", propose),
    ("_apply    (commit + consult)", apply_o),
    ("  _commit", commit_o),
    ("    _absorb  (wake + re-enumerate)", absorb),
    ("      _refresh (provider expansion)", refresh),
    ("        _offer (mint/decline one descriptor)", offer),
    ("    CommitEngine.apply (THE TRANSACTION)", eng_apply),
    ("  _maybe_consult (the close)", consult),
]
for name, f in chain:
    print(f"  {cum(f):8.1f} s {100 * cum(f) / TOTAL:5.1f}%  n={nc(f):<8} {name}")
print()

print("=== the derived-view rebuild (commit-INDUCED, charged to its reader) ===")
for name, f in [("StoreIndex.build", build),
                ("  store.keys()  [tuple(sorted(entries))]", skeys),
                ("plane.index()", pick("index", "plane.py")),
                ("plane.tiles()", pick("tiles", "plane.py"))]:
    percall = cum(f) / nc(f) * 1e3 if nc(f) else 0
    print(f"  {cum(f):8.1f} s {100 * cum(f) / TOTAL:5.1f}%  n={nc(f):<9} "
          f"percall {percall:7.3f} ms  {name}")
if build is not None:
    print("  callers of StoreIndex.build:")
    for f, rec in sorted(S[build][4].items(), key=lambda kv: -kv[1][3]):
        print(f"    {rec[3]:8.1f} s  n={rec[1]:<6} <- {lab(f)}")
print()

# ---- key machinery, the true hot list ------------------------------------
print("=== key machinery (construct/parse/compare) — exclusive time ===")
KEYFUNCS = [("parse_key", "core/keys.py"), ("build_key", "core/keys.py"),
            ("key_parts", "core/keys.py"), ("arity", "core/keys.py"),
            ("<genexpr>", "core/keys.py"), ("__lt__", "<string>"),
            ("__hash__", "<string>"), ("__init__", "<string>"),
            ("parse_evidence_key", "solve/keys.py"),
            ("tile_key", "solve/keys.py"), ("evidence_key", "solve/keys.py")]
tot_key = 0.0
seen = set()
for name, frag in KEYFUNCS:
    for f in find(name, frag):
        if f in seen:
            continue
        seen.add(f)
        tt = S[f][2]
        tot_key += tt
        print(f"  tot {tt:7.2f} s ({100 * tt / TOTAL:4.1f}%)  "
              f"cum {S[f][3]:8.2f} s  n={S[f][1]:<11} {lab(f)}")
print(f"  ---- key machinery EXCLUSIVE total: {tot_key:.1f} s "
      f"= {100 * tot_key / TOTAL:.1f}% of profiled main-thread CPU")
print()

# ---- who calls parse_evidence_key / tile_key 12M times? -----------------
for name, frag in (("parse_evidence_key", "solve/keys.py"),
                   ("tile_key", "solve/keys.py"),
                   ("build_key", "core/keys.py")):
    f = pick(name, frag)
    if f is None:
        continue
    print(f"=== callers of {lab(f)} (n={nc(f):,}) ===")
    for g, rec in sorted(S[f][4].items(), key=lambda kv: -kv[1][3])[:6]:
        print(f"  {rec[3]:8.1f} s  n={rec[1]:<10} <- {lab(g)}")
    print()

# ---- the fire side, for contrast ----------------------------------------
print("=== fire-side kernels (post-cards), for contrast ===")
for name, frag in (("berlekamp_massey_many", "bch_batch"),
                   ("chien_root_mask", "bch_batch"),
                   ("decode_many", "bch"), ("refine_patch_pose", "pose_audit"),
                   ("_fit_phase", "pose_fit")):
    f = pick(name, frag)
    if f is not None:
        print(f"  tot {S[f][2]:7.2f} s ({100 * S[f][2] / TOTAL:4.1f}%)  "
              f"cum {S[f][3]:8.2f} s  n={S[f][1]:<8} {lab(f)}")
