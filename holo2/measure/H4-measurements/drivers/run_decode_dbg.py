"""w8-anomaly debugging driver: stale attribution + contention discriminators.

Decomposes the 8-worker slowdown into its suspected halves:
  (1) churn — which key KINDS drift under in-flight proposals (is it the
      pull-era region-broad read-sets?), counted per stale discard;
  (2) contention — per-fire cost vs EXECUTING concurrency, controlled by
      a driver-side semaphore around _propose (slots stay armed, only K
      bodies run), plus main-thread _is_current/_apply timers (starved?);
  (3) GIL scheduling — optional sys.setswitchinterval override.

All clocks driver-side (L12). usage:
  run_decode_dbg.py TREE SCAN DPI PORT NAME WORKERS CAP SWITCH_MS
CAP: 0 = no cap; K = at most K concurrent _propose bodies.
SWITCH_MS: 0 = leave default (5 ms); else sys.setswitchinterval(ms/1000).
"""
import gc
import hashlib
import sys
import threading
import time
from collections import Counter
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))

from holo2 import diag  # noqa: E402
from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.engine.orchestrator import Orchestrator  # noqa: E402
from holo2.format import registry_rows  # noqa: E402

scan, dpi, port, name = (Path(sys.argv[2]), float(sys.argv[3]),
                         int(sys.argv[4]), sys.argv[5])
workers, cap, switch_ms = (int(sys.argv[6]), int(sys.argv[7]),
                           float(sys.argv[8]))
if switch_ms > 0:
    sys.setswitchinterval(switch_ms / 1000.0)

fires: list[float] = []
fire_cpu: list[float] = []      # per-fire thread CPU (time.thread_time)
drift_kinds: Counter = Counter()
drift_shapes: Counter = Counter()
timers = {"is_current_s": 0.0, "is_current_n": 0, "apply_s": 0.0,
          "apply_n": 0}
gc_stats = {"n": 0, "wall_s": 0.0, "_t0": 0.0}
_lock = threading.Lock()
_sem = threading.BoundedSemaphore(cap) if cap > 0 else None


def _gc_cb(phase, info):
    if phase == "start":
        gc_stats["_t0"] = time.perf_counter()
    else:
        gc_stats["n"] += 1
        gc_stats["wall_s"] += time.perf_counter() - gc_stats["_t0"]


gc.callbacks.append(_gc_cb)

_orig_propose = Orchestrator._propose


def _dbg_propose(self, item):
    if _sem is not None:
        _sem.acquire()
    t0 = time.perf_counter()
    c0 = time.thread_time()
    try:
        return _orig_propose(self, item)
    finally:
        wall_d = time.perf_counter() - t0
        cpu_d = time.thread_time() - c0
        if _sem is not None:
            _sem.release()
        with _lock:
            fires.append(wall_d)
            fire_cpu.append(cpu_d)


Orchestrator._propose = _dbg_propose  # type: ignore[method-assign]

_orig_current = Orchestrator._is_current


def _dbg_current(self, armed):
    t0 = time.perf_counter()
    ok = _orig_current(self, armed)
    timers["is_current_s"] += time.perf_counter() - t0
    timers["is_current_n"] += 1
    if not ok:
        # Attribute the drift: which kinds moved/appeared/vanished.
        old = dict(armed.identity)
        keys = armed.worker.read_keys(self._view)
        new = dict(self._ctx.engine.attempt_identity(keys))
        moved = {k for k in old.keys() & new.keys() if old[k] != new[k]}
        added = new.keys() - old.keys()
        gone = old.keys() - new.keys()
        for k in moved:
            drift_kinds[f"moved:{getattr(k, 'kind', type(k).__name__)}"] += 1
        for k in added:
            drift_kinds[f"added:{getattr(k, 'kind', type(k).__name__)}"] += 1
        for k in gone:
            drift_kinds[f"gone:{getattr(k, 'kind', type(k).__name__)}"] += 1
        shape = (len(moved), len(added), len(gone))
        drift_shapes[f"m{shape[0]}/a{shape[1]}/g{shape[2]}"] += 1
    return ok


Orchestrator._is_current = _dbg_current  # type: ignore[method-assign]

_orig_apply = Orchestrator._apply


def _dbg_apply(self, proposal):
    t0 = time.perf_counter()
    try:
        return _orig_apply(self, proposal)
    finally:
        timers["apply_s"] += time.perf_counter() - t0
        timers["apply_n"] += 1


Orchestrator._apply = _dbg_apply  # type: ignore[method-assign]

# ---- apply-segment attribution: name the 17.7->50ms owner ----------------
from holo2.engine.session import SessionContext  # noqa: E402

segs = {"ctx_apply_s": 0.0, "ctx_apply_n": 0, "absorb_s": 0.0,
        "absorb_n": 0, "consult_s": 0.0, "consult_n": 0}

_orig_ctx_apply = SessionContext.apply


def _dbg_ctx_apply(self, batch):
    t0 = time.perf_counter()
    try:
        return _orig_ctx_apply(self, batch)
    finally:
        segs["ctx_apply_s"] += time.perf_counter() - t0
        segs["ctx_apply_n"] += 1


SessionContext.apply = _dbg_ctx_apply  # type: ignore[method-assign]

_orig_absorb = Orchestrator._absorb


def _dbg_absorb(self, commit):
    t0 = time.perf_counter()
    try:
        return _orig_absorb(self, commit)
    finally:
        segs["absorb_s"] += time.perf_counter() - t0
        segs["absorb_n"] += 1


Orchestrator._absorb = _dbg_absorb  # type: ignore[method-assign]

_orig_consult = Orchestrator._maybe_consult


def _dbg_consult(self):
    t0 = time.perf_counter()
    try:
        return _orig_consult(self)
    finally:
        segs["consult_s"] += time.perf_counter() - t0
        segs["consult_n"] += 1


Orchestrator._maybe_consult = _dbg_consult  # type: ignore[method-assign]

base = Path(__file__).resolve().parent
out = base / f"{name}.bin"
state_dir = base / f"state-{name}"

row = registry_rows.format_row("c2-r0700", (53, 37), 1)
request = DecodeRequest(
    scans=((scan, dpi),), workers=workers, diag_port=port,
    state_dir=state_dir, output=str(out), complete=False)
provider = diag.StatusProvider()
server = diag.serve(port, provider)
start = time.perf_counter()
try:
    outcome, provider = decode(request, row, real_providers(row),
                               status=provider, fsync=True,
                               snapshot_every=512)
finally:
    diag.finalize(provider, state_dir)
    if server is not None:
        server.stop()
wall = time.perf_counter() - start

print(f"[{name}] RESULT {outcome.status.upper()} "
      f"certified={outcome.certified} commits={outcome.commits} "
      f"fires={outcome.fires} wall={wall:.0f}s "
      f"workers={workers} cap={cap} switch_ms={switch_ms}", flush=True)
if outcome.verified and outcome.payload is not None:
    got = hashlib.sha256(outcome.payload).hexdigest()
    print(f"[{name}] payload sha {got[:16]}", flush=True)

busy = sum(fires)
cpu = sum(fire_cpu)
durs = sorted(fires)
n = len(durs)
print(f"[{name}] FIRES {n} busy(wall) {busy:.1f}s busy(cpu) {cpu:.1f}s "
      f"wait-share {100 * (busy - cpu) / max(busy, 1e-9):.1f}% "
      f"median {durs[n // 2] * 1000:.1f}ms p90 "
      f"{durs[int(n * 0.9)] * 1000:.1f}ms", flush=True)
print(f"[{name}] GC {gc_stats['n']} collections, "
      f"{gc_stats['wall_s']:.1f}s inside GC", flush=True)
print(f"[{name}] MAIN-THREAD is_current {timers['is_current_n']} calls "
      f"{timers['is_current_s']:.1f}s "
      f"({timers['is_current_s'] * 1000 / max(timers['is_current_n'], 1):.2f}"
      f"ms/call); apply {timers['apply_n']} calls {timers['apply_s']:.1f}s "
      f"({timers['apply_s'] * 1000 / max(timers['apply_n'], 1):.2f}ms/call)",
      flush=True)
print(f"[{name}] SEGMENTS ctx.apply {segs['ctx_apply_n']} x "
      f"{segs['ctx_apply_s'] * 1000 / max(segs['ctx_apply_n'], 1):.2f}ms "
      f"(total {segs['ctx_apply_s']:.1f}s); absorb {segs['absorb_n']} x "
      f"{segs['absorb_s'] * 1000 / max(segs['absorb_n'], 1):.2f}ms "
      f"(total {segs['absorb_s']:.1f}s); consult {segs['consult_n']} x "
      f"{segs['consult_s'] * 1000 / max(segs['consult_n'], 1):.2f}ms "
      f"(total {segs['consult_s']:.1f}s)", flush=True)
print(f"[{name}] DRIFT kinds: "
      + ", ".join(f"{k}={v}" for k, v in drift_kinds.most_common(10)),
      flush=True)
print(f"[{name}] DRIFT shapes: "
      + ", ".join(f"{k}={v}" for k, v in drift_shapes.most_common(6)),
      flush=True)
