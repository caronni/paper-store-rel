"""Where the Stage-A word decode's time goes, stage by stage, both arms.

Measure-only, driver-side. Captures real candidate blocks the same way
``chien_kernels.py`` does, then times the FOUR stages of
``bch._decode_syndromes``'s routing separately — validation, syndromes,
Berlekamp-Massey, Chien+correct+recheck — on the scalar arm and on the
twin. The point is not the totals (``chien_kernels.py`` has those) but
the SPLIT: it is what said the next card was BM (89 ms of the batched
decode's 106), and it is what says what is left after it.

usage: chien_decompose.py TREE SCAN DPI [CALLS]
"""
import statistics
import sys
import time
from pathlib import Path

tree = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))
scan, dpi = Path(sys.argv[2]), float(sys.argv[3])
CALLS = int(sys.argv[4]) if len(sys.argv) > 4 else 4

import numpy as np  # noqa: E402

from holo2.cli import DecodeRequest, decode, real_providers  # noqa: E402
from holo2.format import bch, bch_batch  # noqa: E402
from holo2.format import registry_rows  # noqa: E402

SCALAR = bch.decode_many
BATCHED = bch_batch.decode_many
captured: list = []


class Enough(Exception):
    """Stop the decode: we have the blocks."""


def grab(words):
    result = SCALAR(words)
    captured.append(words.copy())
    if len(captured) >= CALLS:
        raise Enough()
    return result


# BOTH seams: ``batched_word_sweep`` defaults ON since 2026-08-17, so the
# real sweep calls the TWIN and hooking only the scalar captures nothing.
bch.decode_many = grab
bch_batch.decode_many = grab
base = Path(__file__).resolve().parent
row = registry_rows.format_row("c2-r0700", (53, 37), 1)
print(f"[capture] decoding until {CALLS} Stage-A blocks…", flush=True)
try:
    decode(DecodeRequest(scans=((scan, dpi),), workers=1, diag_port=0,
                         state_dir=base / "state-chien-decompose",
                         output=str(base / "chien-dec.bin"), complete=False),
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
block = sorted(captured, key=lambda b: b.shape[0])[len(captured) // 2]
print(f"[capture] {len(captured)} blocks; timing the median, H="
      f"{block.shape[0]}", flush=True)


def clocked(fn, reps=5):
    fn()
    best = None
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        span = time.perf_counter() - t0
        best = span if best is None else min(best, span)
    return best


# ---- the four stages, scalar arm ---------------------------------------
words = bch._as_words(block, bch.N_WORD)
syndromes = bch._syndromes_many_words(words)
dirty = np.flatnonzero(syndromes.any(axis=1))
lists = [[int(s) for s in syndromes[i]] for i in dirty]
sigmas = [bch._berlekamp_massey(row_) for row_ in lists]
live = [sigma for sigma, length in sigmas
        if length <= bch.T and len(sigma) - 1 == length]

rows = [
    ("validate  (_as_words / isin)",
     lambda: bch._as_words(block, bch.N_WORD),
     lambda: bch_batch._as_words(block)),
    ("syndromes (batched both arms)",
     lambda: bch._syndromes_many_words(words),
     lambda: bch._syndromes_many_words(words)),
    ("BM input  (int() vs the rows)",
     lambda: [[int(s) for s in syndromes[i]] for i in dirty],
     lambda: syndromes[dirty]),
    ("BM        (the LOCKSTEP card)",
     lambda: [bch._berlekamp_massey(row_) for row_ in lists],
     lambda: bch_batch.berlekamp_massey_many(syndromes[dirty])),
    ("CHIEN     (the earlier card)",
     lambda: [bch._chien_roots(sigma) for sigma in live],
     lambda: bch_batch.chien_root_mask(
         np.array([sigma + [0] * (bch.T + 1 - len(sigma)) for sigma in live],
                  np.uint8))),
]

print(f"\n{'stage':32} {'scalar ms':>11} {'batched ms':>11} {'speedup':>9}")
for label, old, new in rows:
    a, b = clocked(old), clocked(new)
    print(f"{label:32} {a * 1e3:>11.1f} {b * 1e3:>11.1f} {a / b:>8.1f}x",
          flush=True)

whole_old = clocked(lambda: bch.decode_many(block))
whole_new = clocked(lambda: bch_batch.decode_many(block))
print(f"{'WHOLE decode_many':32} {whole_old * 1e3:>11.1f} "
      f"{whole_new * 1e3:>11.1f} {whole_old / whole_new:>8.1f}x")
print(f"\n[census] H={block.shape[0]} rows: {len(dirty)} with a nonzero "
      f"syndrome, {len(live)} reach Chien "
      f"({100.0 * len(live) / block.shape[0]:.1f}%); locator degrees "
      f"median {int(statistics.median([len(s) - 1 for s in live]))}")
