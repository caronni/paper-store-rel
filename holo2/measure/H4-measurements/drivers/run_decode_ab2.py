"""run_decode_ab + index-build attribution (the F-17 discriminator).

Wraps StoreIndex.build and TileMap.__init__ driver-side (L12: clocks
stay out of src) to count rebuilds and their total wall, split by
thread (main = arming/admission path, pool = inside fire walls).

usage: run_decode_ab2.py TREE SCAN DPI PORT NAME WORKERS [EXPECTED_BIN]
"""
import hashlib
import sys
import threading
import time
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))

from holo2 import diag  # noqa: E402
from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.engine.orchestrator import Orchestrator  # noqa: E402
from holo2.format import registry_rows  # noqa: E402
from holo2.solve import tilemap  # noqa: E402

scan, dpi, port, name, workers = (Path(sys.argv[2]), float(sys.argv[3]),
                                  int(sys.argv[4]), sys.argv[5],
                                  int(sys.argv[6]))
expected = Path(sys.argv[7]) if len(sys.argv) > 7 else None

fires: list[float] = []
builds = {"index_n": 0, "index_s": 0.0, "index_pool_n": 0,
          "tilemap_n": 0, "tilemap_s": 0.0, "tilemap_pool_n": 0}
_lock = threading.Lock()
_MAIN = threading.main_thread()

_orig_propose = Orchestrator._propose


def _timed_propose(self, item):
    t0 = time.perf_counter()
    try:
        return _orig_propose(self, item)
    finally:
        with _lock:
            fires.append(time.perf_counter() - t0)


Orchestrator._propose = _timed_propose  # type: ignore[method-assign]

_orig_build = tilemap.StoreIndex.build.__func__


def _timed_build(cls, store):
    t0 = time.perf_counter()
    try:
        return _orig_build(cls, store)
    finally:
        dt = time.perf_counter() - t0
        with _lock:
            builds["index_n"] += 1
            builds["index_s"] += dt
            if threading.current_thread() is not _MAIN:
                builds["index_pool_n"] += 1


tilemap.StoreIndex.build = classmethod(_timed_build)  # type: ignore

_orig_tm = tilemap.TileMap.__init__


def _timed_tm(self, *a, **k):
    t0 = time.perf_counter()
    try:
        return _orig_tm(self, *a, **k)
    finally:
        dt = time.perf_counter() - t0
        with _lock:
            builds["tilemap_n"] += 1
            builds["tilemap_s"] += dt
            if threading.current_thread() is not _MAIN:
                builds["tilemap_pool_n"] += 1


tilemap.TileMap.__init__ = _timed_tm  # type: ignore

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
      f"fires={outcome.fires} wall={wall:.0f}s workers={workers}",
      flush=True)
if outcome.verified and outcome.payload is not None:
    got = hashlib.sha256(outcome.payload).hexdigest()
    print(f"[{name}] payload {len(outcome.payload)} B sha {got[:16]}",
          flush=True)
    if expected is not None:
        want = hashlib.sha256(expected.read_bytes()).hexdigest()
        print(f"[{name}] vs {expected.name}: "
              f"{'BYTE-IDENTICAL' if got == want else 'MISMATCH'}",
              flush=True)

busy = sum(fires)
print(f"[{name}] FIRES {len(fires)} busy {busy:.1f}s "
      f"utilisation {100 * busy / (wall * workers):.1f}%", flush=True)
print(f"[{name}] INDEX builds {builds['index_n']} "
      f"({builds['index_pool_n']} on pool threads) "
      f"total {builds['index_s']:.1f}s; "
      f"TILEMAP builds {builds['tilemap_n']} "
      f"({builds['tilemap_pool_n']} on pool threads) "
      f"total {builds['tilemap_s']:.1f}s", flush=True)
print(f"[{name}] build share of busy: "
      f"{100 * (builds['index_s'] + builds['tilemap_s']) / max(busy, 1e-9):.1f}%",
      flush=True)
