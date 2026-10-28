"""Old vs new Stage-A word decoder, at the REAL shapes, plus its GIL fraction.

Measure-only, driver-side (L12: clocks never in src). It does not
synthesise a workload: it starts a real decode of a real capture,
INTERCEPTS the first K ``bch.decode_many`` calls the Stage-A sweep makes,
keeps their exact candidate blocks, stops the decode, and then times the
two arms on those blocks in the same process. The blocks are plain uint8
arrays, so unlike the refine bench nothing here depends on a still-open
memmap — but they are still the real sweep's real hypotheses, at the real
H, not a synthesised batch.

Then the same 1-vs-W scaling method as ``gil_kernels.py`` /
``refine_kernels.py``: run the SAME total work serially and split across
W threads. Under a GIL a kernel that releases it for a fraction f scales
as S = W/((1-f)W + f), so

    f = W (1 - 1/S) / (W - 1)

usage: chien_kernels.py TREE SCAN DPI [CALLS] [WORKERS] [REPS]
"""
import statistics
import sys
import threading
import time
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))
scan, dpi = Path(sys.argv[2]), float(sys.argv[3])
CALLS = int(sys.argv[4]) if len(sys.argv) > 4 else 8
W = int(sys.argv[5]) if len(sys.argv) > 5 else 4
REPS = int(sys.argv[6]) if len(sys.argv) > 6 else 2

from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.format import bch, bch_batch  # noqa: E402
from holo2.format import registry_rows  # noqa: E402

SCALAR = bch.decode_many
BATCHED = bch_batch.decode_many

captured: list = []


class Enough(Exception):
    """Stop the decode: we have all the candidate blocks we need."""


def grab(words):
    result = SCALAR(words)
    captured.append(words.copy())
    print(f"  captured {len(captured)}/{CALLS}: H={words.shape[0]}, "
          f"{sum(1 for r in result if r is not None)} decoded", flush=True)
    if len(captured) >= CALLS:
        raise Enough()
    return result


# BOTH seams: ``batched_word_sweep`` defaults ON since 2026-08-17, so the
# real sweep calls the TWIN and hooking only the scalar captures nothing.
bch.decode_many = grab
bch_batch.decode_many = grab

base = Path(__file__).resolve().parent
row = registry_rows.format_row("c2-r0700", (53, 37), 1)
state = base / "state-chien-kernels"
print(f"[capture] decoding {scan.name} @{dpi:g} until {CALLS} Stage-A blocks…",
      flush=True)
started = time.perf_counter()
try:
    decode(DecodeRequest(scans=((scan, dpi),), workers=1, diag_port=0,
                         state_dir=state, output=str(base / "chien.bin"),
                         complete=False),
           row, real_providers(row), fsync=False, snapshot_every=4096)
except Enough:
    pass
except BaseException as error:                        # noqa: BLE001
    if not isinstance(error.__cause__, Enough) and not isinstance(
            getattr(error, "__context__", None), Enough):
        raise
bch.decode_many = SCALAR
bch_batch.decode_many = BATCHED
print(f"[capture] {len(captured)} candidate blocks in "
      f"{time.perf_counter() - started:.0f}s", flush=True)
if not captured:
    raise SystemExit("nothing captured — the decode never swept a word")

heights = [block.shape[0] for block in captured]
print(f"[shapes] H per block: min {min(heights)} median "
      f"{int(statistics.median(heights))} max {max(heights)}; "
      f"{sum(heights):,} candidate words in the captured set", flush=True)

# The arms must agree on the captured blocks before either is timed —
# a fast wrong answer is not a result.
for block in captured:
    left, right = SCALAR(block), BATCHED(block)
    assert len(left) == len(right)
    for one, other in zip(left, right):
        assert (one is None) == (other is None)
        if one is not None:
            assert one[1] == other[1] and bool((one[0] == other[0]).all())
print("[check] both arms bit-identical on every captured block", flush=True)


def clocked(fn, reps=3):
    """Best-of-``reps`` wall per call (best-of rejects scheduler noise)."""
    fn()
    return min(_one(fn) for _ in range(reps))


def _one(fn):
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


print(f"\n{'H':>6} {'scalar ms':>11} {'batched ms':>11} {'speedup':>8}")
scalar_total = batched_total = 0.0
for block in captured:
    old = clocked(lambda b=block: SCALAR(b))
    new = clocked(lambda b=block: BATCHED(b))
    scalar_total += old
    batched_total += new
    print(f"{block.shape[0]:>6} {old * 1e3:>11.1f} {new * 1e3:>11.1f} "
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
median_block = sorted(captured, key=lambda b: b.shape[0])[len(captured) // 2]
print(f"          on the median block (H={median_block.shape[0]})")
scale("Stage-A decode_many — SCALAR", lambda: SCALAR(median_block), REPS)
scale("Stage-A decode_many — BATCHED", lambda: BATCHED(median_block), REPS)

# BM on its own, both arms: the scalar one is pure python and holds the
# GIL for all of it, so its f is the floor the whole sweep was pinned to.
_words = bch._as_words(median_block, bch.N_WORD)
_synd = bch._syndromes_many_words(_words)
_dirty = _synd.any(axis=1)
_lists = [[int(s) for s in row] for row in _synd[_dirty]]
print(f"          BM alone on {len(_lists)} nonzero-syndrome rows")
scale("  Berlekamp-Massey — SCALAR per row",
      lambda: [bch._berlekamp_massey(row) for row in _lists], REPS)
scale("  Berlekamp-Massey — LOCKSTEP",
      lambda: bch_batch.berlekamp_massey_many(_synd[_dirty]), REPS)
