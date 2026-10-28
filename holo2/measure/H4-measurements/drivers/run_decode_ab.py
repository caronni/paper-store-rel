"""W-S barrier A/B driver: run_decode + fire/round instrumentation.

Clocks live HERE, never in src (L12). Wraps Orchestrator._propose (per-
fire wall) and, when the barrier still exists, Orchestrator._round
(round spans) — the barrier side reports per-round idle-slot-seconds
exactly; the continuous side reports busy/wall*W utilisation.

usage: run_decode_ab.py TREE SCAN DPI PORT NAME WORKERS [EXPECTED_BIN]
  TREE = repo root whose holo2/src to run (main = barrier, paper-h4 =
  continuous). State + output land in THIS file's directory.
"""
import hashlib
import sys
import time
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))

from holo2 import diag  # noqa: E402
from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.engine.orchestrator import Orchestrator  # noqa: E402
from holo2.format import registry_rows  # noqa: E402

scan, dpi, port, name, workers = (Path(sys.argv[2]), float(sys.argv[3]),
                                  int(sys.argv[4]), sys.argv[5],
                                  int(sys.argv[6]))
expected = Path(sys.argv[7]) if len(sys.argv) > 7 else None

fires: list[tuple[float, float]] = []      # (start, duration)
rounds: list[tuple[float, float, int]] = []  # (start, duration, n_armed)

_orig_propose = Orchestrator._propose


def _timed_propose(self, item):
    t0 = time.perf_counter()
    try:
        return _orig_propose(self, item)
    finally:
        fires.append((t0, time.perf_counter() - t0))


Orchestrator._propose = _timed_propose  # type: ignore[method-assign]

if hasattr(Orchestrator, "_round"):
    _orig_round = Orchestrator._round

    def _timed_round(self, pool, armed):
        t0 = time.perf_counter()
        try:
            return _orig_round(self, pool, armed)
        finally:
            rounds.append((t0, time.perf_counter() - t0, len(armed)))

    Orchestrator._round = _timed_round  # type: ignore[method-assign]

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

print("\n".join(provider.status().get("rows", [])), flush=True)
print(f"[{name}] RESULT {outcome.status.upper()} "
      f"certified={outcome.certified} commits={outcome.commits} "
      f"fires={outcome.fires} wall={wall:.0f}s workers={workers}",
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

# ---- the A/B numbers ----------------------------------------------------
busy = sum(dur for _, dur in fires)
print(f"[{name}] FIRES {len(fires)} busy {busy:.1f}s "
      f"wall*W {wall * workers:.1f}s "
      f"utilisation {100 * busy / (wall * workers):.1f}% "
      f"(residual = idle + main-thread phases)", flush=True)
if fires:
    durs = sorted(dur for _, dur in fires)
    n = len(durs)
    print(f"[{name}]   fire wall: median {durs[n // 2] * 1000:.1f}ms "
          f"p90 {durs[int(n * 0.9)] * 1000:.1f}ms "
          f"max {durs[-1] * 1000:.1f}ms", flush=True)
if rounds:
    idle = 0.0
    for r_start, r_dur, n_armed in rounds:
        in_round = [dur for f_start, dur in fires
                    if r_start <= f_start < r_start + r_dur]
        idle += max(0.0, r_dur * min(workers, max(n_armed, 1))
                    - sum(in_round))
    spans = sum(r_dur for _, r_dur, _ in rounds)
    armed = [n for _, _, n in rounds]
    print(f"[{name}] ROUNDS {len(rounds)} span {spans:.1f}s "
          f"idle-slot-seconds {idle:.1f}s "
          f"mean-armed {sum(armed) / len(armed):.2f}/{workers}",
          flush=True)
else:
    print(f"[{name}] ROUNDS none (continuous admission)", flush=True)
