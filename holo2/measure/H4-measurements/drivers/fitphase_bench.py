"""The _FIT_PHASE BATCHING card, benched: decompose + whole + 4-thread f.

Measure-only, driver-side, one capture for both tables (the capture is
the expensive part).  Same method as ``bm2_bench.py``: intercept the real
kernel during a real decode, keep the first CALLS argument tuples, check
BOTH ARMS BIT-IDENTICAL on every one of them before anything is timed —
a speedup between two answers that differ is not a speedup — and only
then clock.

The decompose table splits the objective into the three things it does,
timed as the driver's own reconstruction of each arm's stages:

  * COORDS      — build the 64 hypotheses' read points.  Both arms run
                  the SAME expression per hypothesis; the batched one
                  additionally copies each into a ``(2, H, N)`` stack.
  * INTERPOLATE — 128 ``map_coordinates`` calls against 2.
  * REDUCE      — the per-hypothesis compressed ``mean``, which is the
                  part that does NOT batch (variable-length subsets) and
                  is therefore identical work in both arms.
  * WHOLE       — the shipped functions, and ``_fit_phase`` around them
                  (its shared preamble and its argmax/parabola tail are
                  in neither arm and pay in both).

usage: fitphase_bench.py TREE SCAN DPI [CALLS] [WORKERS] [REPS]
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
CALLS = int(sys.argv[4]) if len(sys.argv) > 4 else 12
W = int(sys.argv[5]) if len(sys.argv) > 5 else 4
REPS = int(sys.argv[6]) if len(sys.argv) > 6 else 3

import numpy as np  # noqa: E402
from scipy import ndimage  # noqa: E402

from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.format import registry_rows  # noqa: E402
from holo2.solve import pose_fit  # noqa: E402

SCALAR = pose_fit._scalar_phase_scores
BATCHED = pose_fit._batched_phase_scores
FIT_PHASE = pose_fit._fit_phase

captured: list = []


class Enough(Exception):
    """Stop the decode: we have the calls."""


def grab(region, jacobian, window, config):
    result = FIT_PHASE(region, jacobian, window, config)
    captured.append((region, jacobian, window, config))
    print(f"  captured {len(captured)}/{CALLS}: window "
          f"{window.shape_yx_cells} at {window.origin_yx_px}", flush=True)
    if len(captured) >= CALLS:
        raise Enough()
    return result


pose_fit._fit_phase = grab
base = Path(__file__).resolve().parent
row = registry_rows.format_row("c2-r0700", (53, 37), 1)
print(f"[capture] decoding {scan.name} @{dpi:g} until {CALLS} fits…",
      flush=True)
started = time.perf_counter()
try:
    decode(DecodeRequest(scans=((scan, dpi),), workers=1, diag_port=0,
                         state_dir=base / "state-fitphase-bench",
                         output=str(base / "fitphase-bench.bin"),
                         complete=False),
           row, real_providers(row), fsync=False, snapshot_every=4096)
except Enough:
    pass
except BaseException as error:                        # noqa: BLE001
    if not isinstance(error.__cause__, Enough) and not isinstance(
            getattr(error, "__context__", None), Enough):
        raise
pose_fit._fit_phase = FIT_PHASE
if not captured:
    raise SystemExit("nothing captured")
print(f"[capture] {len(captured)} fits in "
      f"{time.perf_counter() - started:.0f}s", flush=True)


# ---- the arms' shared preamble, lifted so the stages can be timed ------
def preamble(region, jacobian, window, config):
    """``_fit_phase``'s own setup — what both arms are handed."""
    wy, wx = window.origin_yx_px
    cells_y, cells_x = window.shape_yx_cells
    stride = max(1, int(round(max(cells_y, cells_x) / 40.0)))
    gy, gx = np.meshgrid(np.arange(0, cells_y, stride),
                         np.arange(0, cells_x, stride), indexing="ij")
    grid = np.stack([gy.ravel(), gx.ravel()], axis=1).astype(np.float64)
    base_yx = np.array([wy, wx], np.float64)
    py1 = min(region.filtered.shape[0],
              wy + int(round(cells_y * region.pitch_prior)))
    px1 = min(region.filtered.shape[1],
              wx + int(round(cells_x * region.pitch_prior)))
    local = region.filtered[wy:py1:4, wx:px1:4]
    local_mask = region.support[wy:py1:4, wx:px1:4] > 0.5
    midpoint = float(np.median(local[local_mask]))
    offsets = np.arange(0.5, 1.5 - 1e-9, config.phase_step_cells)
    return grid, base_yx, midpoint, offsets


# ---- equivalence first, on every captured call ------------------------
for region, jacobian, window, config in captured:
    stages = preamble(region, jacobian, window, config)
    one = SCALAR(region, jacobian, *stages)
    other = BATCHED(region, jacobian, *stages)
    assert np.array_equal(one, other, equal_nan=True), "PHASE ARMS DIFFER"
    off = FIT_PHASE(region, jacobian, window,
                    replace(config, batched_fit_phase=False))
    on = FIT_PHASE(region, jacobian, window,
                   replace(config, batched_fit_phase=True))
    assert off == on, "_fit_phase ARMS DIFFER"
print("[check] both arms bit-identical on every captured call, at the "
      "score matrix AND the returned phase", flush=True)

sizes = []
for region, jacobian, window, config in captured:
    grid, _, _, offsets = preamble(region, jacobian, window, config)
    sizes.append((grid.shape[0], offsets.size ** 2))
print(f"[census] sites per hypothesis {min(s for s, _ in sizes)}-"
      f"{max(s for s, _ in sizes)} (median "
      f"{int(statistics.median([s for s, _ in sizes]))}), hypotheses "
      f"{sizes[0][1]} -> {2 * sizes[0][1]} interpolation calls per fit "
      f"on the scalar arm", flush=True)

region, jacobian, window, config = sorted(
    captured, key=lambda row_: preamble(*row_)[0].shape[0])[len(captured) // 2]
grid, base_yx, midpoint, offsets = preamble(region, jacobian, window, config)
H = offsets.size ** 2
N = grid.shape[0]
print(f"[bench] median call: N={N} sites, H={H} hypotheses", flush=True)


def clocked(fn, reps=5):
    fn()
    return min(_one(fn) for _ in range(reps))


def _one(fn):
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


# ---- the stage reconstructions ----------------------------------------
def coords_scalar():
    out = []
    for phase_y in offsets:
        for phase_x in offsets:
            out.append(
                (grid + np.array([phase_y, phase_x])) @ jacobian.T + base_yx)
    return out


def coords_batched():
    points_all = np.empty((2, H, N), np.float64)
    index = 0
    for phase_y in offsets:
        for phase_x in offsets:
            points = (grid + np.array([phase_y, phase_x])) @ jacobian.T + base_yx
            points_all[:, index, :] = points.T
            index += 1
    return points_all


POINTS = coords_scalar()
STACK = coords_batched()


def interpolate_scalar():
    for points in POINTS:
        ndimage.map_coordinates(region.filtered, points.T, order=1,
                                cval=region.backing)
        ndimage.map_coordinates(region.support, points.T, order=1, cval=0.0)


def interpolate_batched():
    ndimage.map_coordinates(region.filtered, STACK, order=1,
                            cval=region.backing)
    ndimage.map_coordinates(region.support, STACK, order=1, cval=0.0)


MEANS = ndimage.map_coordinates(region.filtered, STACK, order=1,
                                cval=region.backing)
COVER = ndimage.map_coordinates(region.support, STACK, order=1, cval=0.0)
SELECTED = COVER > 0.9


def reduce_loop():
    scores = np.full((offsets.size, offsets.size), -np.inf)
    counts = SELECTED.sum(axis=1)
    index = 0
    for row_ in range(offsets.size):
        for column in range(offsets.size):
            if int(counts[index]) >= 16:
                chosen = SELECTED[index]
                scores[row_, column] = float(
                    np.abs(MEANS[index][chosen] - midpoint).mean())
            index += 1
    return scores


rows = [
    ("COORDS      (+stack on the twin)", coords_scalar, coords_batched),
    ("INTERPOLATE (128 calls -> 2)", interpolate_scalar, interpolate_batched),
    ("REDUCE      (never batched)", reduce_loop, reduce_loop),
]
print(f"\n{'stage':34} {'scalar ms':>10} {'batched ms':>11} {'gain':>7}")
for label, old, new in rows:
    a, b = clocked(old), clocked(new)
    print(f"{label:34} {a * 1e3:>10.2f} {b * 1e3:>11.2f} {a / b:>6.2f}x",
          flush=True)

whole_scalar = clocked(
    lambda: SCALAR(region, jacobian, grid, base_yx, midpoint, offsets))
whole_batched = clocked(
    lambda: BATCHED(region, jacobian, grid, base_yx, midpoint, offsets))
print(f"{'WHOLE phase scores':34} {whole_scalar * 1e3:>10.2f} "
      f"{whole_batched * 1e3:>11.2f} {whole_scalar / whole_batched:>6.2f}x")
fit_off = clocked(lambda: FIT_PHASE(region, jacobian, window,
                                    replace(config, batched_fit_phase=False)))
fit_on = clocked(lambda: FIT_PHASE(region, jacobian, window,
                                   replace(config, batched_fit_phase=True)))
print(f"{'WHOLE _fit_phase':34} {fit_off * 1e3:>10.2f} {fit_on * 1e3:>11.2f} "
      f"{fit_off / fit_on:>6.2f}x")

# ---- every captured call, not only the median one ---------------------
print(f"\n{'call':>4} {'N':>6} {'scalar ms':>10} {'batched ms':>11} "
      f"{'gain':>7}")
gains = []
for index, (r, j, w, c) in enumerate(captured):
    g, b_, m, o = preamble(r, j, w, c)
    a = clocked(lambda: SCALAR(r, j, g, b_, m, o), reps=3)
    b = clocked(lambda: BATCHED(r, j, g, b_, m, o), reps=3)
    gains.append(a / b)
    print(f"{index:>4} {g.shape[0]:>6} {a * 1e3:>10.2f} {b * 1e3:>11.2f} "
          f"{a / b:>6.2f}x", flush=True)
print(f"gain over {len(gains)} captured calls: min {min(gains):.2f}x "
      f"median {statistics.median(gains):.2f}x max {max(gains):.2f}x")


# ---- the GIL-free fraction, gil_kernels.py's method verbatim -----------
def scale(label, fn, reps):
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


print()
reps = max(1, int(0.5 / max(whole_batched, 1e-6)))
scale("_scalar_phase_scores", lambda: SCALAR(
    region, jacobian, grid, base_yx, midpoint, offsets), reps)
scale("_batched_phase_scores", lambda: BATCHED(
    region, jacobian, grid, base_yx, midpoint, offsets), reps)
scale("np.exp control (known GIL-free)",
      lambda: np.exp(np.empty(N * H, np.float64)), reps)
print("BENCH DONE", flush=True)
