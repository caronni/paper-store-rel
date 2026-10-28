"""JOB B analysis — attribute the profiled serial decode's main-thread CPU.

Reads cards-profile.pstats and answers, in order:
  (a) ENCODE+DIGEST share of main-thread CPU (both sites: the fire-side
      `batch_id` and the wall-side `digest_json` inside CommitEngine.apply)
  (b) top-level decomposition: fire side vs commit side vs the rest
  (c) top commit-path functions by cumtime, with percall
  (d) per-commit CPU cost, and the counts the card is priced from.

Edge-level attribution: pstats keeps, per callee, a `callers` mapping
caller -> (cc, nc, tt, ct) where `ct` is the cumulative time on THAT
edge. That is what splits a shared helper (`digest_json`, `to_json`)
between the propose side and the wall side without guessing.
"""
from __future__ import annotations

import pstats
import sys
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "scratch/holo2-demo/cards-profile.pstats")
st = pstats.Stats(str(path))
S = st.stats  # func -> (cc, nc, tt, ct, callers)


def find(name: str, file_frag: str = "") -> list:
    hits = [f for f in S
            if f[2] == name and (not file_frag or file_frag in f[0])]
    return hits


MISSING: list[str] = []


def one(name: str, file_frag: str = ""):
    """The single (file, line, name) triple, or None with a warning."""
    hits = find(name, file_frag)
    if len(hits) != 1:
        MISSING.append(f"{name!r}/{file_frag!r} -> {len(hits)} hits: "
                       f"{[f'{h[0]}:{h[1]}' for h in hits][:4]}")
        return hits[0] if hits else None
    return hits[0]


def label(f) -> str:
    return "?" if f is None else f"{Path(f[0]).name}:{f[1]}:{f[2]}"


def cum(f) -> float:
    return 0.0 if f is None else S[f][3]


def ncalls(f) -> int:
    return 0 if f is None else S[f][1]


def edge_ct(callee, caller) -> float:
    """Cumulative time on the caller->callee edge."""
    if callee is None or caller is None:
        return 0.0
    for f, rec in S[callee][4].items():
        if f == caller:
            return rec[3]
    return 0.0


def edge_nc(callee, caller) -> int:
    if callee is None or caller is None:
        return 0
    for f, rec in S[callee][4].items():
        if f == caller:
            return rec[1]
    return 0


total_tt = sum(rec[2] for rec in S.values())
print(f"profiled main-thread CPU (sum tottime) = {total_tt:.1f} s")
print(f"primitive calls {st.prim_calls:,} / total calls {st.total_calls:,}")
print()

# ---- top-level decomposition (serial: everything is on this thread) -----
run_serial = one("_run_serial", "orchestrator")
propose = one("_propose", "orchestrator")
apply_orch = one("_apply", "orchestrator")
commit_orch = one("_commit", "orchestrator")
sess_apply = one("apply", "session.py")
eng_apply = one("apply", "core/commit.py")
maybe_consult = one("_maybe_consult", "orchestrator")

print("=== top-level decomposition ===")
rows = [
    ("_run_serial (whole scheduling loop)", cum(run_serial), ncalls(run_serial)),
    ("  _propose  (FIRE side)", edge_ct(propose, run_serial), edge_nc(propose, run_serial)),
    ("  _apply    (COMMIT side + close consult)", cum(apply_orch), ncalls(apply_orch)),
    ("    _commit", cum(commit_orch), ncalls(commit_orch)),
    ("    _maybe_consult", cum(maybe_consult), ncalls(maybe_consult)),
    ("      SessionContext.apply", cum(sess_apply), ncalls(sess_apply)),
    ("        CommitEngine.apply", cum(eng_apply), ncalls(eng_apply)),
]
for name, ct, nc in rows:
    print(f"{ct:9.1f} s  {100 * ct / total_tt:5.1f}%  n={nc:<7}  {name}")
print(f"{total_tt - cum(run_serial):9.1f} s  "
      f"{100 * (total_tt - cum(run_serial)) / total_tt:5.1f}%          "
      f"everything outside the loop (ingest, open, close, publish)")
print()

# ---- (a) encode + digest of batches -------------------------------------
digest_json = one("digest_json", "codec")
canon = one("canonical_json_bytes", "codec")
batch_id = one("batch_id", "core/commit.py")
batch_to_json = one("to_json", "core/commit.py")   # may be several
print("=== (a) ENCODE + DIGEST of batches ===")
dj_from_batchid = edge_ct(digest_json, batch_id)
dj_from_apply = edge_ct(digest_json, eng_apply)
bid_ct = cum(batch_id)
# CommitBatch.to_json edges
to_json_batch = [f for f in find("to_json", "core/commit.py")
                 if "CommitBatch" in str(f) or True]
canon_batch = one("canonical", "core/commit.py")
print(f"  batch_id() total (fire side, PRE-merge id) : {bid_ct:8.2f} s "
      f"({100 * bid_ct / total_tt:.1f}% of main-thread CPU), n={ncalls(batch_id)}")
print(f"    of which digest_json                     : {dj_from_batchid:8.2f} s")
print(f"    of which CommitBatch.canonical()         : "
      f"{edge_ct(canon_batch, batch_id):8.2f} s")
print(f"  digest_json() inside CommitEngine.apply    : {dj_from_apply:8.2f} s "
      f"({100 * dj_from_apply / total_tt:.1f}%)")
print(f"  CommitBatch.canonical() inside apply       : "
      f"{edge_ct(canon_batch, eng_apply):8.2f} s")
enc_dig = bid_ct + dj_from_apply + edge_ct(canon_batch, eng_apply)
print(f"  TOTAL encode+digest+canonicalise of batches: {enc_dig:8.2f} s "
      f"= {100 * enc_dig / total_tt:.1f}% of main-thread CPU")
print(f"  canonical_json_bytes total {cum(canon):.2f} s "
      f"(n={ncalls(canon)}), of which from digest_json "
      f"{edge_ct(canon, digest_json):.2f} s")
print()

# ---- (b) is canonical_json_bytes on the stdlib C encoder? ---------------
print("=== (b) what canonical_json_bytes actually spends on ===")
for f, rec in sorted(S[canon][4].items(), key=lambda kv: -kv[1][3]):
    pass
callees = [(g, edge_ct(g, canon), edge_nc(g, canon)) for g in S
           if canon in S[g][4]]
for g, ct, nc in sorted(callees, key=lambda t: -t[1]):
    print(f"    {ct:8.2f} s  n={nc:<8} {label(g)}")
print()

# ---- (c) the commit path, ranked ----------------------------------------
print("=== (c) commit-path functions ranked by cumtime under the wall ===")
NAMES = [
    ("_admit_completed", "orchestrator"), ("_apply", "orchestrator"),
    ("_commit", "orchestrator"), ("_settle", "orchestrator"),
    ("_note", "orchestrator"), ("_absorb", "orchestrator"),
    ("_disarm", "orchestrator"), ("_dispatch", "orchestrator"),
    ("_maybe_consult", "orchestrator"),
    ("apply", "session.py"), ("apply", "core/commit.py"),
    ("_settle_merges", "core/commit.py"), ("_merged", "core/commit.py"),
    ("_adjudicate_writes", "core/commit.py"),
    ("_adjudicate_spends", "core/commit.py"),
    ("_require_references", "core/commit.py"),
    ("_require_bulk_present", "core/commit.py"),
    ("_record_trace", "core/commit.py"),
    ("canonical", "core/commit.py"), ("batch_id", "core/commit.py"),
    ("digest_json", "codec"), ("canonical_json_bytes", "codec"),
    ("sha256_hex", "codec"), ("encode_dataclass", "codec"),
    ("encode_value", "codec"), ("encode_typed_record", "codec"),
    ("apply_committed", "store.py"), ("append", "journal.py"),
    ("_frame", "store.py"), ("append", "cache.py"), ("_append", "cache.py"),
    ("mark_start", "store.py"), ("settle_start", "store.py"),
    ("record", "core/work.py"), ("is_spent", "core/work.py"),
    ("publish_write", "resources.py"), ("subscribe", "resources.py"),
    ("wakes_for", "resources.py"), ("joined_collections", "resources.py"),
    ("versions", "resources.py"), ("attempt_identity", "core/"),
    ("invalidate", None), ("to_json", "core/commit.py"),
    ("to_json", "core/keys.py"),
    # the commit's DOWNSTREAM cost: invalidate() kills the derived views
    # and the next reader rebuilds them (charged to the fire side).
    ("build", "tilemap.py"), ("index", "plane.py"), ("tiles", "plane.py"),
    ("_derived", "plane.py"), ("keys", "store.py"), ("get", "store.py"),
    ("key_parts", "solve/keys.py"), ("build_key", "solve/keys.py"),
    ("tile_key", "solve/keys.py"), ("parse_evidence_key", "solve/keys.py"),
    ("parse_key", "solve/keys.py"),
]
seen = set()
rows = []
for name, frag in NAMES:
    for f in find(name, frag or ""):
        if f in seen:
            continue
        seen.add(f)
        cc, nc, tt, ct, _ = S[f]
        rows.append((ct, tt, nc, label(f)))
for ct, tt, nc, lab in sorted(rows, reverse=True)[:28]:
    pc = ct / nc if nc else 0.0
    print(f"  cum {ct:8.2f} s ({100 * ct / total_tt:4.1f}%)  tot {tt:7.2f} s  "
          f"n={nc:<8} percall {pc * 1e3:7.3f} ms  {lab}")
print()

print("=== overall top-20 by tottime (the honest hot list) ===")
for f, rec in sorted(S.items(), key=lambda kv: -kv[1][2])[:20]:
    cc, nc, tt, ct, _ = rec
    print(f"  tot {tt:8.2f} s ({100 * tt / total_tt:4.1f}%)  cum {ct:8.2f} s  "
          f"n={nc:<9} {label(f)}")
print()

# ---- (d) counts the card is priced from ---------------------------------
print("=== (d) counts + per-commit cost ===")
commits = ncalls(eng_apply)
merged_f = one("_merged", "core/commit.py")
writes_total = ncalls(merged_f)
merge_at = one("merge_at", "registry.py")
joins = edge_nc(merge_at, merged_f)
join_ct = edge_ct(merge_at, merged_f)
replace_f = one("replace", "dataclasses.py")
settle_f = one("_settle_merges", "core/commit.py")
batches_with_join = edge_nc(replace_f, settle_f)
print(f"  commits (CommitEngine.apply)          : {commits}")
print(f"  writes seen by _settle_merges         : {writes_total} "
      f"({writes_total / max(commits, 1):.2f}/commit)")
print(f"  writes that actually JOINED (merge_at): {joins} "
      f"({100 * joins / max(writes_total, 1):.1f}% of writes), "
      f"{join_ct:.2f} s")
print(f"  batches whose writes changed on merge : {batches_with_join} "
      f"({100 * batches_with_join / max(commits, 1):.1f}% of commits)")
commit_ct = cum(apply_orch)
print(f"  commit-path CPU (Orchestrator._apply) : {commit_ct:.1f} s "
      f"=> {1e3 * commit_ct / max(commits, 1):.1f} ms/commit")
print(f"  wall-side encode+digest per commit    : "
      f"{1e3 * (dj_from_apply + edge_ct(canon_batch, eng_apply)) / max(commits, 1):.2f} ms")
print(f"  fire-side batch_id per fire           : "
      f"{1e3 * bid_ct / max(ncalls(batch_id), 1):.2f} ms")
if MISSING:
    print()
    print("=== names the attribution could not resolve uniquely ===")
    for line in MISSING:
        print("  " + line)
