"""The binary two-step BM card, benched: decompose + whole + 4-thread f.

Measure-only, driver-side, one capture for all three tables (the capture
is the expensive part). Same method as ``chien_decompose.py`` and
``chien_kernels.py``, extended with the card's own A/B:

  * BM 26-STEP — the general recurrence, rebuilt from the SHIPPED source
    by the same two substitutions the equivalence harness uses
    (``bch_equivalence.GENERAL``). It is not in src: nothing in
    production would call a general batched arm, so the pre-card arm
    lives as a source reconstruction, here and in the harness.
  * BM 13-STEP — the shipped arm, which skips the 13 provably-zero
    steps.

Both are checked bit-identical on every captured block before anything
is timed: a speedup between two answers that differ is not a speedup.

usage: bm2_bench.py TREE SCAN DPI [CALLS] [WORKERS] [REPS]
"""
import statistics
import sys
import threading
import time
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))
scan, dpi = Path(sys.argv[2]), float(sys.argv[3])
CALLS = int(sys.argv[4]) if len(sys.argv) > 4 else 10
W = int(sys.argv[5]) if len(sys.argv) > 5 else 4
REPS = int(sys.argv[6]) if len(sys.argv) > 6 else 3

import numpy as np  # noqa: E402

from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.format import bch, bch_batch  # noqa: E402
from holo2.format import registry_rows  # noqa: E402

SCALAR = bch.decode_many
BATCHED = bch_batch.decode_many
TWO_STEP = bch_batch.berlekamp_massey_many


# ---- the pre-card arm, rebuilt from the shipped source -----------------
def _general_from_source():
    """26-step general BM: the shipped file, two substitutions."""
    source = Path(bch_batch.__file__).read_text()
    for found, replacement in (
            ("for step in range(0, 2 * bch.T, 2)",
             "for step in range(0, 2 * bch.T, 1)"),
            ("np.where(change, np.int16(2), shift + 2)",
             "np.where(change, np.int16(1), shift + 1)")):
        assert source.count(found) == 1, found
        source = source.replace(found, replacement)
    source = source.replace("from . import bch", "from holo2.format import bch")
    namespace = {"__name__": "bch_batch_general"}
    exec(compile(source, "<bch_batch 26-step>", "exec"), namespace)
    return namespace["berlekamp_massey_many"]


GENERAL = _general_from_source()

captured: list = []


class Enough(Exception):
    """Stop the decode: we have the blocks."""


def grab(words):
    result = SCALAR(words)
    captured.append(words.copy())
    print(f"  captured {len(captured)}/{CALLS}: H={words.shape[0]}", flush=True)
    if len(captured) >= CALLS:
        raise Enough()
    return result


bch.decode_many = grab
bch_batch.decode_many = grab
base = Path(__file__).resolve().parent
row = registry_rows.format_row("c2-r0700", (53, 37), 1)
print(f"[capture] decoding {scan.name} @{dpi:g} until {CALLS} blocks…",
      flush=True)
started = time.perf_counter()
try:
    decode(DecodeRequest(scans=((scan, dpi),), workers=1, diag_port=0,
                         state_dir=base / "state-bm2-bench",
                         output=str(base / "bm2-bench.bin"), complete=False),
           row, real_providers(row), fsync=False, snapshot_every=4096)
except Enough:
    pass
except BaseException as error:                        # noqa: BLE001
    if not isinstance(error.__cause__, Enough) and not isinstance(
            getattr(error, "__context__", None), Enough):
        raise
bch.decode_many = SCALAR
bch_batch.decode_many = BATCHED
if not captured:
    raise SystemExit("nothing captured")
print(f"[capture] {len(captured)} blocks in {time.perf_counter() - started:.0f}s",
      flush=True)

# ---- equivalence first, on every captured block ------------------------
for block in captured:
    words = bch._as_words(block, bch.N_WORD)
    synd = bch._syndromes_many_words(words)
    dirty = synd[synd.any(axis=1)]
    left, right = GENERAL(dirty), TWO_STEP(dirty)
    assert all(np.array_equal(a, b) for a, b in zip(left, right)), "BM ARMS DIFFER"
    one, other = SCALAR(block), BATCHED(block)
    assert len(one) == len(other)
    for a, b in zip(one, other):
        assert (a is None) == (b is None)
        if a is not None:
            assert a[1] == b[1] and bool((a[0] == b[0]).all())
print("[check] 26-step == 13-step on every block, and both arms of "
      "decode_many bit-identical", flush=True)

block = sorted(captured, key=lambda b: b.shape[0])[len(captured) // 2]
words = bch._as_words(block, bch.N_WORD)
syndromes = bch._syndromes_many_words(words)
dirty = np.flatnonzero(syndromes.any(axis=1))
lists = [[int(s) for s in syndromes[i]] for i in dirty]
sigmas = [bch._berlekamp_massey(row_) for row_ in lists]
live = [sigma for sigma, length in sigmas
        if length <= bch.T and len(sigma) - 1 == length]
print(f"[census] median block H={block.shape[0]}: {len(dirty)} nonzero-"
      f"syndrome rows, {len(live)} reach Chien; locator degrees median "
      f"{int(statistics.median([len(s) - 1 for s in live]))}", flush=True)


def clocked(fn, reps=5):
    fn()
    return min(_one(fn) for _ in range(reps))


def _one(fn):
    t0 = time.perf_counter()
    fn()
    return time.perf_counter() - t0


# ---- the decompose table, with the card's column added -----------------
def whole_with(arm):
    def run():
        bch_batch.berlekamp_massey_many = arm
        try:
            return bch_batch.decode_many(block)
        finally:
            bch_batch.berlekamp_massey_many = TWO_STEP
    return run


rows = [
    ("validate  (_as_words / isin)",
     lambda: bch._as_words(block, bch.N_WORD),
     lambda: bch_batch._as_words(block),
     lambda: bch_batch._as_words(block)),
    ("syndromes (batched both arms)",
     lambda: bch._syndromes_many_words(words),
     lambda: bch._syndromes_many_words(words),
     lambda: bch._syndromes_many_words(words)),
    ("BM input  (int() vs the rows)",
     lambda: [[int(s) for s in syndromes[i]] for i in dirty],
     lambda: syndromes[dirty],
     lambda: syndromes[dirty]),
    ("BM        (26-step -> 13-step)",
     lambda: [bch._berlekamp_massey(row_) for row_ in lists],
     lambda: GENERAL(syndromes[dirty]),
     lambda: TWO_STEP(syndromes[dirty])),
    ("CHIEN     (unchanged here)",
     lambda: [bch._chien_roots(sigma) for sigma in live],
     lambda: bch_batch.chien_root_mask(
         np.array([sigma + [0] * (bch.T + 1 - len(sigma)) for sigma in live],
                  np.uint8)),
     lambda: bch_batch.chien_root_mask(
         np.array([sigma + [0] * (bch.T + 1 - len(sigma)) for sigma in live],
                  np.uint8))),
]

print(f"\n{'stage':32} {'scalar ms':>10} {'26-step ms':>11} "
      f"{'13-step ms':>11} {'vs 26':>7} {'vs scalar':>10}")
for label, old, general, two_step in rows:
    a, b, c = clocked(old), clocked(general), clocked(two_step)
    print(f"{label:32} {a * 1e3:>10.1f} {b * 1e3:>11.1f} {c * 1e3:>11.1f} "
          f"{b / c:>6.2f}x {a / c:>9.1f}x", flush=True)

whole_scalar = clocked(lambda: bch.decode_many(block))
whole_general = clocked(whole_with(GENERAL))
whole_two = clocked(whole_with(TWO_STEP))
print(f"{'WHOLE decode_many':32} {whole_scalar * 1e3:>10.1f} "
      f"{whole_general * 1e3:>11.1f} {whole_two * 1e3:>11.1f} "
      f"{whole_general / whole_two:>6.2f}x {whole_scalar / whole_two:>9.1f}x")

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


print(f"\n[scaling] {W} threads, {REPS} reps each vs {REPS * W} serial, on "
      f"the median block (H={block.shape[0]})")
scale("Stage-A decode_many — 13-step BM", lambda: BATCHED(block), REPS)
print(f"          BM alone on {len(dirty)} nonzero-syndrome rows")
scale("  Berlekamp-Massey — 26-step", lambda: GENERAL(syndromes[dirty]), REPS)
scale("  Berlekamp-Massey — 13-step", lambda: TWO_STEP(syndromes[dirty]), REPS)
