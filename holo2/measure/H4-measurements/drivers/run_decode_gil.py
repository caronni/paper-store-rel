"""GIL-contention diagnosis driver for the holo2 pull-model pool.

Everything is driver-side (L12): the pinned worktree under measurement is
never touched. Wraps ``Orchestrator._propose`` (the pooled fire) and the
main-thread commit path, and runs ONE monitor thread that does double
duty:

  * **GIL-latency probe** — ``time.sleep(5ms)`` in a loop; the overshoot
    past the requested sleep is (near enough) the time spent queuing for
    the GIL after the timer fired. Under GIL queuing it grows with the
    number of runnable threads and with ``sys.setswitchinterval``.
  * **stack sampler** — ``sys._current_frames()``, leaf frame of every
    pool thread. A thread sitting in a numpy C call shows the PYTHON
    frame that called it, which is exactly the "which kernel" attribution
    wanted.

THE DISCRIMINATOR (per fire, both clocks on the same thread):
  wall  = time.perf_counter delta      (elapsed)
  cpu   = time.thread_time delta       (this thread ON a core)
  wall - cpu = off-core time = GIL queuing + preemption.
GIL queuing inflates wall while cpu stays flat; memory-bandwidth
contention inflates cpu too; a main-thread bottleneck shows idle slots
and a growing commit share.

usage: run_decode_gil.py TREE SCAN DPI PORT NAME WORKERS [EXPECTED_BIN]
env:   GIL_SWITCH_MS  — sys.setswitchinterval(ms/1000) before the decode
       GIL_SAMPLE_MS  — monitor period in ms (default 5)
State + output land in THIS file's directory.
"""
import hashlib
import json
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))

from holo2 import diag  # noqa: E402
from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.engine.orchestrator import Orchestrator  # noqa: E402
from holo2.engine.session import SessionContext  # noqa: E402
from holo2.format import registry_rows  # noqa: E402

scan, dpi, port, name, workers = (Path(sys.argv[2]), float(sys.argv[3]),
                                  int(sys.argv[4]), sys.argv[5],
                                  int(sys.argv[6]))
expected = Path(sys.argv[7]) if len(sys.argv) > 7 else None

switch_ms = float(os.environ.get("GIL_SWITCH_MS", "0") or 0)
if switch_ms > 0:
    sys.setswitchinterval(switch_ms / 1000.0)
sample_ms = float(os.environ.get("GIL_SAMPLE_MS", "5") or 5)

# ---- per-fire records ---------------------------------------------------
# (family, route, source?, wall, cpu, concurrency-at-entry, thread name)
records: list[tuple[str, str, int, float, float, int, str]] = []
_lock = threading.Lock()
_inflight = 0

_orig_propose = Orchestrator._propose


def _timed_propose(self, armed):
    global _inflight
    desc = armed.descriptor
    family = getattr(desc, "family", "?")
    route = getattr(desc, "route", "?")
    is_source = 1 if armed.source is not None else 0
    with _lock:
        _inflight += 1
        conc = _inflight
    t0 = time.perf_counter()
    c0 = time.thread_time()
    try:
        return _orig_propose(self, armed)
    finally:
        wall_d = time.perf_counter() - t0
        cpu_d = time.thread_time() - c0
        tname = threading.current_thread().name
        with _lock:
            _inflight -= 1
            records.append((family, route, is_source, wall_d, cpu_d,
                            conc, tname))


Orchestrator._propose = _timed_propose  # type: ignore[method-assign]

# ---- main-thread phases -------------------------------------------------
mains: dict[str, list[float]] = defaultdict(list)   # wall
mains_cpu: dict[str, float] = defaultdict(float)    # thread cpu


def _wrap_main(cls, attr, label):
    orig = getattr(cls, attr)

    def wrapper(self, *a, **kw):
        t0 = time.perf_counter()
        c0 = time.thread_time()
        try:
            return orig(self, *a, **kw)
        finally:
            mains[label].append(time.perf_counter() - t0)
            mains_cpu[label] += time.thread_time() - c0

    setattr(cls, attr, wrapper)


_wrap_main(Orchestrator, "_apply", "apply")        # commit + consult
_wrap_main(Orchestrator, "_is_current", "is_current")
_wrap_main(Orchestrator, "_fill", "fill")          # pop-and-arm + submit
_wrap_main(Orchestrator, "_admit_completed", "admit")   # incl. the wait()
_wrap_main(SessionContext, "apply", "ctx.apply")

# ---- the monitor: GIL latency + stack sampler ---------------------------
lat: list[float] = []
leaves: Counter = Counter()
stacks: Counter = Counter()
main_leaves: Counter = Counter()
main_stacks: Counter = Counter()
busy_threads: Counter = Counter()
_stop = threading.Event()
_period = sample_ms / 1000.0
_self_id = None


def _monitor():
    while not _stop.is_set():
        t0 = time.perf_counter()
        time.sleep(_period)
        lat.append(time.perf_counter() - t0 - _period)
        frames = sys._current_frames()
        n_busy = 0
        for tid, frame in frames.items():
            if tid == _self_id:
                continue
            nm = _thread_names.get(tid)
            if nm is None:
                continue
            if nm.startswith("holo2-propose"):
                leaf_sink, stack_sink = leaves, stacks
                n_busy += 1
            elif nm == "MainThread":
                leaf_sink, stack_sink = main_leaves, main_stacks
            else:
                continue
            f = frame
            leaf_sink[f"{Path(f.f_code.co_filename).stem}:"
                      f"{f.f_code.co_name}:{f.f_lineno}"] += 1
            chain = []
            walk = f
            while walk is not None and len(chain) < 40:
                stem = Path(walk.f_code.co_filename).stem
                chain.append(f"{stem}:{walk.f_code.co_name}")
                walk = walk.f_back
            holo = [c for c in chain if not c.startswith(("threading:",
                                                          "_base:",
                                                          "run_decode"))]
            stack_sink[" < ".join(holo[:6])] += 1
        busy_threads[n_busy] += 1


_thread_names: dict[int, str] = {}


def _refresh_names():
    while not _stop.is_set():
        for th in threading.enumerate():
            if th.ident is not None:
                _thread_names[th.ident] = th.name
        _stop.wait(2.0)


base = Path(__file__).resolve().parent
out = base / f"{name}.bin"
state_dir = base / f"state-{name}"

row = registry_rows.format_row("c2-r0700", (53, 37), 1)
request = DecodeRequest(
    scans=((scan, dpi),), workers=workers, diag_port=port,
    state_dir=state_dir, output=str(out), complete=False)
provider = diag.StatusProvider()
server = diag.serve(port, provider)

namer = threading.Thread(target=_refresh_names, daemon=True, name="gil-names")
namer.start()
mon = threading.Thread(target=_monitor, daemon=True, name="gil-monitor")
mon.start()
_self_id = mon.ident

main_c0 = time.thread_time()
start = time.perf_counter()
try:
    outcome, provider = decode(request, row, real_providers(row),
                               status=provider, fsync=True,
                               snapshot_every=512)
finally:
    _stop.set()
    diag.finalize(provider, state_dir)
    if server is not None:
        server.stop()
wall = time.perf_counter() - start
main_cpu = time.thread_time() - main_c0
mon.join(timeout=2.0)

# Raw dump FIRST: a reporting bug must never cost a 9-minute run.
import pickle  # noqa: E402
(base / f"{name}.raw.pkl").write_bytes(pickle.dumps({
    "records": records, "mains": dict(mains), "mains_cpu": dict(mains_cpu),
    "lat": lat, "leaves": leaves, "stacks": stacks,
    "main_leaves": main_leaves, "main_stacks": main_stacks,
    "busy_threads": busy_threads, "wall": wall, "main_cpu": main_cpu,
    "workers": workers, "switch_ms": switch_ms}))

print("\n".join(provider.status().get("rows", [])), flush=True)
print(f"[{name}] RESULT {outcome.status.upper()} "
      f"certified={outcome.certified} commits={outcome.commits} "
      f"fires={outcome.fires} wall={wall:.0f}s workers={workers} "
      f"switch_ms={switch_ms or sys.getswitchinterval() * 1000:.1f}",
      flush=True)
if outcome.verified and outcome.payload is not None:
    out.write_bytes(outcome.payload)
    got = hashlib.sha256(outcome.payload).hexdigest()
    print(f"[{name}] payload {len(outcome.payload)} B sha {got[:16]}",
          flush=True)
    if expected is not None:
        want = hashlib.sha256(expected.read_bytes()).hexdigest()
        verdict = "BYTE-IDENTICAL" if got == want else "MISMATCH"
        print(f"[{name}] vs {expected.name}: {verdict}", flush=True)


def _pct(xs, q):
    if not xs:
        return 0.0
    s = sorted(xs)
    return s[min(len(s) - 1, int(len(s) * q))]


# ---- the discriminator --------------------------------------------------
tot_wall = sum(r[3] for r in records)
tot_cpu = sum(r[4] for r in records)
print(f"[{name}] FIRES {len(records)} wall {tot_wall:.1f}s cpu {tot_cpu:.1f}s "
      f"offcore {tot_wall - tot_cpu:.1f}s "
      f"({100 * (tot_wall - tot_cpu) / max(tot_wall, 1e-9):.1f}% of fire wall) "
      f"| fire-cpu/wall {tot_cpu / wall:.3f} cores", flush=True)
print(f"[{name}] FIRE wall p50 {_pct([r[3] for r in records], .5) * 1e3:.2f}ms "
      f"p90 {_pct([r[3] for r in records], .9) * 1e3:.2f}ms "
      f"| cpu p50 {_pct([r[4] for r in records], .5) * 1e3:.2f}ms "
      f"p90 {_pct([r[4] for r in records], .9) * 1e3:.2f}ms", flush=True)

by: dict[tuple[str, str, int], list[tuple[float, float]]] = defaultdict(list)
for fam, route, src, w, c, _conc, _t in records:
    by[(fam, route, src)].append((w, c))
print(f"[{name}] --- per family/route ---", flush=True)
for key in sorted(by, key=lambda k: -sum(c for _, c in by[k])):
    fam, route, src = key
    vals = by[key]
    ws = [w for w, _ in vals]
    cs = [c for _, c in vals]
    print(f"[{name}]   {fam}/{route}{'/source' if src else '':10} "
          f"n={len(vals):5d} cpu={sum(cs):8.1f}s ({100 * sum(cs) / max(tot_cpu, 1e-9):5.1f}%) "
          f"wall={sum(ws):8.1f}s cpu-p50={_pct(cs, .5) * 1e3:8.2f}ms "
          f"cpu-p90={_pct(cs, .9) * 1e3:9.2f}ms "
          f"wall-p90={_pct(ws, .9) * 1e3:9.2f}ms", flush=True)

print(f"[{name}] MAIN thread cpu {main_cpu:.1f}s of wall {wall:.1f}s "
      f"({100 * main_cpu / wall:.1f}%)", flush=True)
for label in ("fill", "admit", "apply", "ctx.apply", "is_current"):
    xs = mains.get(label, [])
    print(f"[{name}]   main.{label:10} n={len(xs):6d} "
          f"wall={sum(xs):8.1f}s cpu={mains_cpu.get(label, 0.0):8.1f}s "
          f"p50={_pct(xs, .5) * 1e3:7.2f}ms p90={_pct(xs, .9) * 1e3:8.2f}ms",
          flush=True)

if lat:
    print(f"[{name}] GIL-LATENCY probe n={len(lat)} period={sample_ms:.1f}ms "
          f"mean={sum(lat) / len(lat) * 1e3:.2f}ms "
          f"p50={_pct(lat, .5) * 1e3:.2f}ms p90={_pct(lat, .9) * 1e3:.2f}ms "
          f"p99={_pct(lat, .99) * 1e3:.2f}ms max={max(lat) * 1e3:.1f}ms",
          flush=True)
tot_samples = sum(busy_threads.values())
if tot_samples:
    hist = ", ".join(f"{k}:{100 * v / tot_samples:.0f}%"
                     for k, v in sorted(busy_threads.items()))
    print(f"[{name}] IN-FIRE THREADS per sample: {hist}", flush=True)

n_leaf = sum(leaves.values())
print(f"[{name}] --- stack sampler: {n_leaf} pool-thread samples ---",
      flush=True)
for leaf, n in leaves.most_common(20):
    print(f"[{name}]   {100 * n / max(n_leaf, 1):5.2f}%  {leaf}", flush=True)
print(f"[{name}] --- top stacks ---", flush=True)
for st, n in stacks.most_common(12):
    print(f"[{name}]   {100 * n / max(n_leaf, 1):5.2f}%  {st}", flush=True)

n_main = sum(main_leaves.values())
print(f"[{name}] --- stack sampler: {n_main} MAIN-thread samples ---",
      flush=True)
for leaf, n in main_leaves.most_common(20):
    print(f"[{name}]   {100 * n / max(n_main, 1):5.2f}%  {leaf}", flush=True)
for st, n in main_stacks.most_common(8):
    print(f"[{name}]   S {100 * n / max(n_main, 1):5.2f}%  {st}", flush=True)

(base / f"{name}.gil.json").write_text(json.dumps({
    "name": name, "workers": workers, "wall": wall, "switch_ms": switch_ms,
    "fire_wall": tot_wall, "fire_cpu": tot_cpu, "main_cpu": main_cpu,
    "n_fires": len(records),
    "by_route": {f"{k[0]}/{k[1]}{'/source' if k[2] else ''}":
                 {"n": len(v), "wall": sum(w for w, _ in v),
                  "cpu": sum(c for _, c in v)} for k, v in by.items()},
    "main": {k: {"n": len(v), "wall": sum(v), "cpu": mains_cpu.get(k, 0.0)}
             for k, v in mains.items()},
    "gil_latency_ms": {"n": len(lat),
                       "mean": (sum(lat) / len(lat) * 1e3) if lat else 0.0,
                       "p50": _pct(lat, .5) * 1e3, "p90": _pct(lat, .9) * 1e3,
                       "p99": _pct(lat, .99) * 1e3,
                       "max": (max(lat) * 1e3) if lat else 0.0},
    "busy_threads": dict(busy_threads),
    "leaves": dict(leaves.most_common(60)),
    "stacks": dict(stacks.most_common(30)),
    "main_leaves": dict(main_leaves.most_common(40)),
    "main_stacks": dict(main_stacks.most_common(20)),
}, indent=1))
print(f"[{name}] wrote {name}.gil.json", flush=True)
