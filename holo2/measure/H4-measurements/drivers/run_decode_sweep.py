"""Flip ``PlacementConfig.batched_word_sweep`` ON, driver-side, then run a driver.

The switch's DEFAULT in ``src`` is OFF and stays OFF until the numbers
are ruled on; experiment instrumentation is allowed to monkeypatch, src
is not allowed to grow a hatch (L12). Every ``PlacementConfig`` field has
a default, so the generated ``__init__``'s ``__defaults__`` tuple lines
up one-for-one with ``fields()`` — rewriting the one entry makes every
bare ``PlacementConfig()`` in the tree construct with the batched word
sweep on, and ``dataclasses.replace`` (which passes every init field
explicitly) carries it through untouched.

Same shape as ``run_decode_refine.py``, one field over. Reports which arm
actually ran and the candidate-block shapes the batched decoder saw — the
H the micro-bench is timing.

usage: run_decode_sweep.py DRIVER TREE SCAN DPI PORT NAME WORKERS [EXPECTED]
"""
import atexit
import dataclasses
import runpy
import statistics
import sys
from pathlib import Path

base = Path(__file__).resolve().parent
driver = base / sys.argv[1]
tree = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))

from holo2.format import bch, bch_batch                   # noqa: E402
from holo2.solve.place_model import PlacementConfig       # noqa: E402

names = [field.name for field in dataclasses.fields(PlacementConfig)]
defaults = list(PlacementConfig.__init__.__defaults__)
assert len(defaults) == len(names), (len(defaults), len(names))
defaults[names.index("batched_word_sweep")] = True
PlacementConfig.__init__.__defaults__ = tuple(defaults)
assert PlacementConfig().batched_word_sweep is True
assert dataclasses.replace(PlacementConfig(), refine=True).batched_word_sweep

# Which arm actually ran, counted rather than assumed, plus the batch
# shapes the batched kernel saw — what the micro-bench is timing.
_batched = bch_batch.decode_many
_scalar = bch.decode_many
shapes: list[int] = []
scalar_rows = [0]


def _count_batched(words):
    shapes.append(int(words.shape[0]))
    return _batched(words)


def _count_scalar(words):
    scalar_rows[0] += int(words.shape[0])
    return _scalar(words)


bch_batch.decode_many = _count_batched
bch.decode_many = _count_scalar


@atexit.register
def _report() -> None:
    if not shapes:
        print("[sweep] NO BATCHED DECODE RAN — the switch did not take",
              flush=True)
        return
    print(f"[sweep] batched blocks {len(shapes)} ({sum(shapes):,} candidate "
          f"rows); scalar rows {scalar_rows[0]:,}; H per block min "
          f"{min(shapes)} median {int(statistics.median(shapes))} max "
          f"{max(shapes)}", flush=True)


print(f"[sweep] batched_word_sweep forced ON in {tree}", flush=True)
sys.argv = [str(driver)] + sys.argv[2:]
runpy.run_path(str(driver), run_name="__main__")
