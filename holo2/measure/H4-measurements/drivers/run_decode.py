"""H3bis demo driver: cli.main's real path + OR-6 cadence (512) + finalize.

usage: run_decode.py SCAN DPI PORT NAME [EXPECTED_BIN]
"""
import hashlib
import sys
import time
from pathlib import Path

sys.path.insert(0, "<checkout>/holo2/src")

from holo2 import diag  # noqa: E402
from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.format import registry_rows  # noqa: E402

format_row = registry_rows.format_row

scan, dpi, port, name = (Path(sys.argv[1]), float(sys.argv[2]),
                         int(sys.argv[3]), sys.argv[4])
expected = Path(sys.argv[5]) if len(sys.argv) > 5 else None
base = Path("scratch/holo2-demo")
out = base / f"{name}.bin"
state_dir = base / f"state-{name}"

row = format_row("c2-r0700", (53, 37), 1)
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
    print(f"[{name}] diag finalize: {final.notice()}", flush=True)
    if server is not None:
        server.stop()
wall = time.perf_counter() - start
print("\n".join(provider.status().get("rows", [])), flush=True)
print(f"[{name}] RESULT {outcome.status.upper()} "
      f"certified={outcome.certified} commits={outcome.commits} "
      f"fires={outcome.fires} wall={wall:.0f}s reason={outcome.reason}",
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
