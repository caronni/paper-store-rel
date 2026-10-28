"""JOB B — cProfile wrapper around ONE serial gen-clean decode.

Same decode the A/B driver drives (same DecodeRequest fields, same row,
same providers, same fsync/snapshot cadence), with cProfile wrapped
around the whole `decode(...)` call. `workers=1` takes
`Orchestrator._run_serial`, so EVERY frame — fire-side and commit-side —
runs on this thread and one profile captures the lot.

No instrumentation is added inside the profiled region on purpose: a
wrapper around `CommitEngine.apply` would steal exactly the cumtime the
attribution is about. Counts come out of the profile's own ncalls.

usage: run_decode_profile.py TREE SCAN DPI PORT NAME [EXPECTED_BIN]
"""
import cProfile
import hashlib
import sys
import time
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))

from holo2 import diag  # noqa: E402
from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.format import registry_rows  # noqa: E402

scan, dpi, port, name = (Path(sys.argv[2]), float(sys.argv[3]),
                         int(sys.argv[4]), sys.argv[5])
expected = Path(sys.argv[6]) if len(sys.argv) > 6 else None

base = Path(__file__).resolve().parent
out = base / f"{name}.bin"
state_dir = base / f"state-{name}"
pstats_path = base / "cards-profile.pstats"

row = registry_rows.format_row("c2-r0700", (53, 37), 1)
request = DecodeRequest(
    scans=((scan, dpi),), workers=1, diag_port=port,
    state_dir=state_dir, output=str(out), complete=False)
provider = diag.StatusProvider()
server = diag.serve(port, provider)

profiler = cProfile.Profile()
start = time.perf_counter()
try:
    profiler.enable()
    try:
        outcome, provider = decode(request, row, real_providers(row),
                                   status=provider, fsync=True,
                                   snapshot_every=512)
    finally:
        profiler.disable()
finally:
    diag.finalize(provider, state_dir)
    if server is not None:
        server.stop()
wall = time.perf_counter() - start

profiler.dump_stats(str(pstats_path))
print(f"[{name}] wrote {pstats_path}", flush=True)

print("\n".join(provider.status().get("rows", [])), flush=True)
print(f"[{name}] RESULT {outcome.status.upper()} "
      f"certified={outcome.certified} commits={outcome.commits} "
      f"fires={outcome.fires} wall={wall:.0f}s workers=1 "
      f"(PROFILED — wall is DISQUALIFIED as a timing number)", flush=True)
if outcome.verified and outcome.payload is not None:
    out.write_bytes(outcome.payload)
    got = hashlib.sha256(outcome.payload).hexdigest()
    print(f"[{name}] payload {len(outcome.payload)} B sha {got[:16]}",
          flush=True)
    if expected is not None:
        want = hashlib.sha256(expected.read_bytes()).hexdigest()
        verdict = "BYTE-IDENTICAL" if got == want else "MISMATCH"
        print(f"[{name}] vs {expected.name}: {verdict}", flush=True)
