"""_FIT_PHASE A/B driver: run_decode_ab.py plus the card's switch.

PINNED TO THE PRE-DELETION TREE (2026-08-17).  It produced the card's
A/B — serial 115 s OFF / 116 s ON, W4 51 / 48 s, all VERIFIED
byte-identical — and then the arm and its switch were DELETED from src
on that measurement.  It will NOT run against the tree as it stands:
there is no ``batched_fit_phase`` and no ``_batched_phase_scores`` any
more.  Kept as the record of how those numbers were made; to re-measure,
drive the arm from ``measure/fit_phase_equivalence.py``'s reconstruction
instead of from a config flag.

Clocks live HERE, never in src (L12).  The only thing this adds to
``run_decode_ab.py`` is the ARM: ``PlacementConfig.batched_fit_phase``
defaults OFF in the tree, so the ON arm is selected driver-side by
wrapping the one place a default config is built
(``place_sched.PlacementScheduler.__init__``), and PROVEN live by
counting the batched scans the decode actually ran — an A/B whose switch
silently did nothing is the failure mode worth spending three lines on.

usage: run_decode_fitphase.py TREE SCAN DPI PORT NAME WORKERS on|off
                              [EXPECTED_BIN]
"""
import hashlib
import sys
import time
from dataclasses import replace
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))

from holo2 import diag  # noqa: E402
from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.engine.orchestrator import Orchestrator  # noqa: E402
from holo2.format import registry_rows  # noqa: E402
from holo2.solve import place_sched, pose_fit  # noqa: E402

scan, dpi, port, name, workers, arm = (
    Path(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4]), sys.argv[5],
    int(sys.argv[6]), sys.argv[7].lower())
expected = Path(sys.argv[8]) if len(sys.argv) > 8 else None
if arm not in ("on", "off"):
    raise SystemExit("arm must be 'on' or 'off'")

# ---- the arm ------------------------------------------------------------
_config = place_sched.PlacementConfig
if arm == "on":
    place_sched.PlacementConfig = (            # type: ignore[assignment]
        lambda *a, **k: replace(_config(*a, **k), batched_fit_phase=True))

scans = [0]
_batched = pose_fit._batched_phase_scores


def _counted(*args):
    scans[0] += 1
    return _batched(*args)


pose_fit._batched_phase_scores = _counted

fires: list[tuple[float, float]] = []
_orig_propose = Orchestrator._propose


def _timed_propose(self, item):
    t0 = time.perf_counter()
    try:
        return _orig_propose(self, item)
    finally:
        fires.append((t0, time.perf_counter() - t0))


Orchestrator._propose = _timed_propose  # type: ignore[method-assign]

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
print(f"[{name}] ARM batched_fit_phase={arm.upper()} — batched scans run: "
      f"{scans[0]} (OFF must be 0, ON must be > 0)", flush=True)
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
        verdict = "BYTE-IDENTICAL" if got == want else "MISMATCH"
        print(f"[{name}] vs {expected.name}: {verdict}", flush=True)

busy = sum(dur for _, dur in fires)
print(f"[{name}] FIRES {len(fires)} busy {busy:.1f}s "
      f"wall*W {wall * workers:.1f}s "
      f"utilisation {100 * busy / (wall * workers):.1f}%", flush=True)
if fires:
    durs = sorted(dur for _, dur in fires)
    n = len(durs)
    print(f"[{name}]   fire wall: median {durs[n // 2] * 1000:.1f}ms "
          f"p90 {durs[int(n * 0.9)] * 1000:.1f}ms "
          f"max {durs[-1] * 1000:.1f}ms", flush=True)
