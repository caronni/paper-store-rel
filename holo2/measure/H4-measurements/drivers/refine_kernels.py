"""Old vs new refine-grid kernel, at the REAL shapes, plus its GIL fraction.

Measure-only, driver-side (L12: clocks never in src). It does not
synthesise a workload: it starts a real decode of a real capture,
INTERCEPTS the first K ``refine_patch_pose`` calls, captures both arms'
exact arguments (the scalar arm's ``(config, evaluate)`` closure and the
batched arm's array bundle), stops the decode, and then times the two
kernels on those captured arguments in the same process — the memmapped
region planes the closures hold are still open, so the pixels are the
real ones.

Then the same 1-vs-W scaling method as ``gil_kernels.py``: run the SAME
total work serially and split across W threads. Under a GIL a kernel that
releases it for a fraction f scales as S = W/((1-f)W + f), so

    f = W (1 - 1/S) / (W - 1)

usage: refine_kernels.py TREE SCAN DPI [CALLS] [WORKERS] [REPS]
"""
import statistics
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))
scan, dpi = Path(sys.argv[2]), float(sys.argv[3])
CALLS = int(sys.argv[4]) if len(sys.argv) > 4 else 8
W = int(sys.argv[5]) if len(sys.argv) > 5 else 4
REPS = int(sys.argv[6]) if len(sys.argv) > 6 else 2

from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.format import registry_rows  # noqa: E402
from holo2.solve import pose_audit  # noqa: E402

ORACLE = pose_audit.refine_patch_pose
SCALAR = pose_audit._scalar_refine_scan
BATCHED = pose_audit._batched_refine_scan

captured: list[dict] = []
slot: dict = {}


class Enough(Exception):
    """Stop the decode: we have all the argument sets we need."""


def grab_scalar(config, evaluate):
    slot["scalar"] = (config, evaluate)
    return SCALAR(config, evaluate)


def grab_batched(context, pose, points, *rest):
    slot["batched"] = (context, pose, points, *rest)
    slot["sites"] = int(points.shape[0])
    slot["plane"] = tuple(context.filtered.shape)
    return BATCHED(context, pose, points, *rest)


def probe(context, patch, provider, page, origin_yx, rot_k, config, *,
          resample):
    slot.clear()
    outcome = ORACLE(context, patch, provider, page, origin_yx, rot_k,
                     replace(config, batched_refine=False), resample=resample)
    ORACLE(context, patch, provider, page, origin_yx, rot_k,
           replace(config, batched_refine=True), resample=resample)
    if "scalar" in slot and "batched" in slot:
        captured.append(dict(slot))
        print(f"  captured {len(captured)}/{CALLS}: {slot['sites']} sites, "
              f"region {slot['plane'][0]}x{slot['plane'][1]} px", flush=True)
        if len(captured) >= CALLS:
            raise Enough()
    return outcome


pose_audit._scalar_refine_scan = grab_scalar
pose_audit._batched_refine_scan = grab_batched
pose_audit.refine_patch_pose = probe

base = Path(__file__).resolve().parent
row = registry_rows.format_row("c2-r0700", (53, 37), 1)
state = base / "state-refine-kernels"
print(f"[capture] decoding {scan.name} @{dpi:g} until {CALLS} refine calls…",
      flush=True)
started = time.perf_counter()
try:
    decode(DecodeRequest(scans=((scan, dpi),), workers=1, diag_port=0,
                         state_dir=state, output=str(base / "kern.bin"),
                         complete=False),
           row, real_providers(row), fsync=False, snapshot_every=4096)
except Enough:
    pass
except BaseException as error:                        # noqa: BLE001
    if not isinstance(error.__cause__, Enough) and not isinstance(
            getattr(error, "__context__", None), Enough):
        raise
print(f"[capture] {len(captured)} argument sets in "
      f"{time.perf_counter() - started:.0f}s", flush=True)
if not captured:
    raise SystemExit("nothing captured — the decode never refined")

sites = [row_["sites"] for row_ in captured]
print(f"[shapes] sites per call: min {min(sites)} median "
      f"{int(statistics.median(sites))} max {max(sites)}; grid 7x9x9 = 567 "
      f"hypotheses; stacked points {567 * int(statistics.median(sites)):,}",
      flush=True)


def clocked(fn, reps=3):
    """Best-of-``reps`` wall per call (best-of rejects scheduler noise)."""
    fn()
    return min(_one(fn) for _ in range(reps))


def _one(fn):
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


print(f"\n{'sites':>6} {'scalar ms':>11} {'batched ms':>11} {'speedup':>8}")
scalar_total = batched_total = 0.0
for row_ in captured:
    old = clocked(lambda r=row_: SCALAR(*r["scalar"]))
    new = clocked(lambda r=row_: BATCHED(*r["batched"]))
    scalar_total += old
    batched_total += new
    print(f"{row_['sites']:>6} {old * 1e3:>11.1f} {new * 1e3:>11.1f} "
          f"{old / new:>7.1f}x", flush=True)
print(f"{'TOTAL':>6} {scalar_total * 1e3:>11.1f} {batched_total * 1e3:>11.1f} "
      f"{scalar_total / batched_total:>7.1f}x", flush=True)


def scale(label, fn, reps):
    """gil_kernels.py's method, verbatim: same total work, 1 vs W threads."""
    fn()
    t0 = time.perf_counter()
    for _ in range(reps * W):
        fn()
    serial = time.perf_counter() - t0

    def loop():
        for _ in range(reps):
            fn()

    threads = [threading.Thread(target=loop) for _ in range(W)]
    t0 = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    parallel = time.perf_counter() - t0
    speedup = serial / parallel
    f = W * (1 - 1 / speedup) / (W - 1)
    print(f"{label:40} serial {serial:6.2f}s  {W}-thread {parallel:6.2f}s  "
          f"speedup {speedup:4.2f}x  GIL-free f~"
          f"{max(0.0, min(1.0, f)):.2f}", flush=True)


print(f"\n[scaling] {W} threads, {REPS} reps each vs {REPS * W} serial")
median_row = sorted(captured, key=lambda r: r["sites"])[len(captured) // 2]
print(f"          on the median-site call ({median_row['sites']} sites)")
scale("refine grid — SCALAR (567 calls)",
      lambda: SCALAR(*median_row["scalar"]), REPS)
scale("refine grid — BATCHED (1 call)",
      lambda: BATCHED(*median_row["batched"]), REPS)
