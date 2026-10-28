"""JOB B (second pass) — direct, profiler-free commit-path accounting.

cProfile ranks, but it also taxes every Python call, which inflates
exactly the Python-heavy code the attribution is about. This driver
measures the same chain with `time.thread_time` around a handful of
wrappers and counts the two things the card is priced from:

  * the wall-side encode+digest cost per commit, separately from the
    fire-side `batch_id` the worker already pays;
  * how often the POST-merge batch differs in VALUE from the PRE-merge
    batch — i.e. how often the wall's re-encode is actually necessary
    rather than merely unconditional.

Everything is driver-side (L12): the pinned tree is never edited.

usage: run_decode_commitcost.py TREE SCAN DPI PORT NAME WORKERS [EXPECTED]
"""
import hashlib
import json
import sys
import time
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))

from holo2 import diag  # noqa: E402
from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.core import blobs as blobs_mod  # noqa: E402
from holo2.core import commit as commit_mod  # noqa: E402
from holo2.core import journal as journal_mod  # noqa: E402
from holo2.core import store as store_mod  # noqa: E402
from holo2.engine import orchestrator as orch_mod  # noqa: E402
from holo2.engine.orchestrator import Orchestrator  # noqa: E402
from holo2.format import registry_rows  # noqa: E402
from holo2.solve import tilemap as tilemap_mod  # noqa: E402

scan, dpi, port, name, workers = (Path(sys.argv[2]), float(sys.argv[3]),
                                  int(sys.argv[4]), sys.argv[5],
                                  int(sys.argv[6]))
expected = Path(sys.argv[7]) if len(sys.argv) > 7 else None

C: dict[str, float] = {}
N: dict[str, int] = {}


def bump(tag: str, dt: float) -> None:
    C[tag] = C.get(tag, 0.0) + dt
    N[tag] = N.get(tag, 0) + 1


def timed(tag, fn):
    def wrapper(*a, **kw):
        t0 = time.thread_time()
        try:
            return fn(*a, **kw)
        finally:
            bump(tag, time.thread_time() - t0)
    return wrapper


# ---- the wall ------------------------------------------------------------
_in_apply = False
_orig_apply = commit_mod.CommitEngine.apply


def _apply(self, batch):
    global _in_apply
    _in_apply = True
    t0 = time.thread_time()
    try:
        return _orig_apply(self, batch)
    finally:
        bump("wall.CommitEngine.apply", time.thread_time() - t0)
        _in_apply = False


commit_mod.CommitEngine.apply = _apply

# ---- the merge settle: does the wall's re-encode change anything? -------
_orig_settle = commit_mod.CommitEngine._settle_merges
_merge_equal = 0
_merge_differs = 0
_merge_same_object = 0


def _settle(self, canonical):
    global _merge_equal, _merge_differs, _merge_same_object
    t0 = time.thread_time()
    try:
        out = _orig_settle(self, canonical)
    finally:
        bump("wall._settle_merges", time.thread_time() - t0)
    if out is canonical:
        _merge_same_object += 1
    elif out == canonical:
        _merge_equal += 1
    else:
        _merge_differs += 1
    return out


commit_mod.CommitEngine._settle_merges = _settle

# ---- encode + digest, split by side -------------------------------------
_orig_digest = commit_mod.digest_json


def _digest(obj):
    t0 = time.thread_time()
    try:
        return _orig_digest(obj)
    finally:
        bump("digest_json.wall" if _in_apply else "digest_json.fire",
             time.thread_time() - t0)


commit_mod.digest_json = _digest

_orig_canonical = commit_mod.CommitBatch.canonical
commit_mod.CommitBatch.canonical = timed("batch.canonical", _orig_canonical)

# `batch_id` was imported INTO the orchestrator's namespace: patch it there
# (this is the per-fire digest whose result nothing in production reads).
_orig_batch_id = orch_mod.batch_id
orch_mod.batch_id = timed("fire.batch_id", _orig_batch_id)

# ---- the other main-thread commit-path costs ----------------------------
blobs_mod.BlobSidecar.put = timed("wall.blobs.put", blobs_mod.BlobSidecar.put)
journal_mod.Journal.append = timed("wall.journal.append",
                                   journal_mod.Journal.append)
store_mod.Store._frame = timed("wall.store._frame", store_mod.Store._frame)
store_mod.Store.mark_start = timed("sched.store.mark_start",
                                   store_mod.Store.mark_start)
tilemap_mod.StoreIndex.build = timed("view.StoreIndex.build",
                                     tilemap_mod.StoreIndex.build.__func__)
tilemap_mod.StoreIndex.build = classmethod(tilemap_mod.StoreIndex.build)
Orchestrator._propose = timed("fire._propose", Orchestrator._propose)
Orchestrator._apply = timed("wall._apply(total)", Orchestrator._apply)
Orchestrator._maybe_consult = timed("wall._maybe_consult",
                                    Orchestrator._maybe_consult)

base = Path(__file__).resolve().parent
out = base / f"{name}.bin"
state_dir = base / f"state-{name}"

row = registry_rows.format_row("c2-r0700", (53, 37), 1)
request = DecodeRequest(
    scans=((scan, dpi),), workers=workers, diag_port=port,
    state_dir=state_dir, output=str(out), complete=False)
provider = diag.StatusProvider()
server = diag.serve(port, provider)
t_wall0 = time.perf_counter()
c_main0 = time.thread_time()
try:
    outcome, provider = decode(request, row, real_providers(row),
                               status=provider, fsync=True,
                               snapshot_every=512)
finally:
    diag.finalize(provider, state_dir)
    if server is not None:
        server.stop()
wall = time.perf_counter() - t_wall0
main_cpu = time.thread_time() - c_main0

print("\n".join(provider.status().get("rows", [])), flush=True)
print(f"[{name}] RESULT {outcome.status.upper()} "
      f"certified={outcome.certified} commits={outcome.commits} "
      f"fires={outcome.fires} wall={wall:.0f}s workers={workers}", flush=True)
if outcome.verified and outcome.payload is not None:
    out.write_bytes(outcome.payload)
    got = hashlib.sha256(outcome.payload).hexdigest()
    print(f"[{name}] payload {len(outcome.payload)} B sha {got[:16]}",
          flush=True)
    if expected is not None:
        want = hashlib.sha256(expected.read_bytes()).hexdigest()
        print(f"[{name}] vs {expected.name}: "
              f"{'BYTE-IDENTICAL' if got == want else 'MISMATCH'}", flush=True)

print(f"[{name}] main-thread CPU {main_cpu:.1f}s of wall {wall:.1f}s "
      f"({100 * main_cpu / wall:.1f}%)", flush=True)
for tag in sorted(C, key=lambda t: -C[t]):
    print(f"[{name}]   {C[tag]:8.2f} s  n={N[tag]:<7} "
          f"percall {1e3 * C[tag] / max(N[tag], 1):7.3f} ms  {tag}", flush=True)
print(f"[{name}] MERGE SETTLE: same-object {_merge_same_object} · "
      f"new-object-but-EQUAL {_merge_equal} · VALUE-DIFFERS {_merge_differs}",
      flush=True)
(base / f"{name}.commitcost.json").write_text(json.dumps(
    {"wall": wall, "main_cpu": main_cpu, "cpu": C, "n": N,
     "merge_same_object": _merge_same_object, "merge_equal": _merge_equal,
     "merge_differs": _merge_differs, "workers": workers,
     "commits": outcome.commits, "fires": outcome.fires}, indent=1))
