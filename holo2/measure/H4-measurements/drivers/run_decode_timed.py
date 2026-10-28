"""run_decode + a driver-side consult timer (P3-1 measure-first gate).

Clocks live HERE, never in src (L12): VolumeClose.consult is wrapped at
the driver, recording (certified-at-consult, seconds, decided) per call.

usage: run_decode_timed.py SCAN DPI PORT NAME [EXPECTED_BIN]
"""
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, "holo2/src")

from holo2 import diag  # noqa: E402
from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.format import registry_rows  # noqa: E402
from holo2.solve.close import VolumeClose  # noqa: E402

consults: list[tuple[int, float, bool]] = []
_orig_consult = VolumeClose.consult


def _timed_consult(self, view, *, mode):
    t0 = time.perf_counter()
    verdict = _orig_consult(self, view, mode=mode)
    dt = time.perf_counter() - t0
    report = verdict.report or {}
    consults.append((int(report.get("certified", -1)), dt,
                     bool(verdict.writes)))
    return verdict


VolumeClose.consult = _timed_consult  # type: ignore[method-assign]

scan, dpi, port, name = (Path(sys.argv[1]), float(sys.argv[2]),
                         int(sys.argv[3]), sys.argv[4])
expected = Path(sys.argv[5]) if len(sys.argv) > 5 else None
base = Path("scratch/holo2-demo")
out = base / f"{name}.bin"
state_dir = base / f"state-{name}"

row = registry_rows.format_row("c2-r0700", (53, 37), 1)
request = DecodeRequest(
    scans=((scan, dpi),), workers=8, diag_port=port,
    state_dir=state_dir, output=str(out), complete=False)
provider = diag.StatusProvider()
server = diag.serve(port, provider)
print(f"[{name}] diag: http://127.0.0.1:{port}/" if server else
      f"[{name}] diag port busy", flush=True)
start = time.perf_counter()
try:
    outcome, provider = decode(request, row, real_providers(row),
                               status=provider, fsync=True,
                               snapshot_every=512)
finally:
    final = diag.finalize(provider, state_dir)
    if server is not None:
        server.stop()
wall = time.perf_counter() - start
print("\n".join(provider.status().get("rows", [])), flush=True)
print(f"[{name}] RESULT {outcome.status.upper()} "
      f"certified={outcome.certified} commits={outcome.commits} "
      f"fires={outcome.fires} wall={wall:.0f}s", flush=True)
if outcome.verified and outcome.payload is not None:
    out.write_bytes(outcome.payload)
    got = hashlib.sha256(outcome.payload).hexdigest()
    print(f"[{name}] payload {len(outcome.payload)} B sha {got[:16]}",
          flush=True)
    if expected is not None:
        want = hashlib.sha256(expected.read_bytes()).hexdigest()
        verdict = "BYTE-IDENTICAL" if got == want else "MISMATCH"
        print(f"[{name}] vs {expected.name}: {verdict}", flush=True)

# ---- the P3-1 measurement ------------------------------------------------
counting = [(n, dt) for n, dt, decided in consults if not decided]
deciding = [(n, dt) for n, dt, decided in consults if decided]
total = sum(dt for _, dt, _ in consults)
print(f"[{name}] CONSULTS {len(consults)} total, {total:.2f}s "
      f"({100 * total / wall:.1f}% of wall)", flush=True)
if counting:
    counting.sort(key=lambda t: t[1])
    n_ = len(counting)
    print(f"[{name}]   counting: {n_} calls, "
          f"{sum(dt for _, dt in counting):.2f}s; per-call "
          f"median {counting[n_ // 2][1] * 1000:.1f}ms, "
          f"p90 {counting[int(n_ * 0.9)][1] * 1000:.1f}ms, "
          f"max {counting[-1][1] * 1000:.1f}ms at n={counting[-1][0]}",
          flush=True)
    lo = [dt for n, dt in counting if 0 <= n <= 400]
    hi = [dt for n, dt in counting if n > 900]
    if lo and hi:
        print(f"[{name}]   growth: mean {sum(lo) / len(lo) * 1000:.1f}ms at "
              f"n<=400 vs {sum(hi) / len(hi) * 1000:.1f}ms at n>900",
              flush=True)
for n, dt in deciding:
    print(f"[{name}]   deciding consult at n={n}: {dt * 1000:.0f}ms",
          flush=True)
