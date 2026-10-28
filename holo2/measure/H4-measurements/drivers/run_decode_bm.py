"""A/B the LOCKSTEP BM card by swapping ``bch_batch`` whole, driver-side.

The lockstep card edits the LIVE arm in place, so "the baseline" is not
a config flip — it is the previous commit's code. This loads that code
from git (``BM_BASE:holo2/src/holo2/format/bch_batch.py``, default the
card's parent), compiles it in its own namespace, and binds its
``decode_many`` over the module's. So both legs of the A/B run the same
receiver, the same switch (``batched_word_sweep``, ON by ruling) and the
same everything else; the only difference is whether the twin's rule 2
is ``bch._berlekamp_massey`` per row or the lockstep.

Nothing is written to the tree under measurement and src grows no hatch
(L12): the substitution is one module attribute, in this process.

usage: BM_ARM=pre|post run_decode_bm.py DRIVER TREE SCAN DPI PORT NAME
                                        WORKERS [EXPECTED]
env:   BM_ARM   pre = the parent commit's twin, post = the working tree
       BM_BASE  the commit the "pre" arm is read from (default 6c241cd)
"""
import atexit
import dataclasses
import os
import runpy
import statistics
import subprocess
import sys
from pathlib import Path

base = Path(__file__).resolve().parent
driver = base / sys.argv[1]
tree = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(tree / "holo2" / "src"))

arm = os.environ.get("BM_ARM", "post")
commit = os.environ.get("BM_BASE", "6c241cd")
if arm not in ("pre", "post"):
    raise SystemExit("BM_ARM must be pre or post")

from holo2.format import bch, bch_batch                   # noqa: E402
from holo2.solve.place_model import PlacementConfig       # noqa: E402

# The switch is ON by ruling; assert rather than assume, because a
# baseline that quietly ran the scalar arm would look like a win.
names = [field.name for field in dataclasses.fields(PlacementConfig)]
defaults = list(PlacementConfig.__init__.__defaults__)
assert len(defaults) == len(names), (len(defaults), len(names))
assert PlacementConfig().batched_word_sweep is True, "the switch is OFF"

if arm == "pre":
    source = subprocess.run(
        ["git", "-C", str(tree), "show",
         f"{commit}:holo2/src/holo2/format/bch_batch.py"],
        capture_output=True, text=True, check=True).stdout
    assert source.count("from . import bch") == 1
    assert "berlekamp_massey_many" not in source, (
        f"{commit} already HAS the lockstep — pick an earlier BM_BASE")
    source = source.replace("from . import bch", "from holo2.format import bch")
    namespace = {"__name__": "bch_batch_pre"}
    exec(compile(source, f"<bch_batch@{commit}>", "exec"), namespace)
    bch_batch.decode_many = namespace["decode_many"]
    print(f"[bm] arm=pre — twin's rule 2 is bch._berlekamp_massey per row, "
          f"from {commit} ({len(source.splitlines())} lines)", flush=True)
else:
    assert hasattr(bch_batch, "berlekamp_massey_many"), "no lockstep here"
    print("[bm] arm=post — twin's rule 2 is the lockstep "
          "berlekamp_massey_many", flush=True)

# Which arm actually ran, counted rather than assumed.
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
        print("[bm] NO BATCHED DECODE RAN — the arm did not take", flush=True)
        return
    print(f"[bm] arm={arm}: batched blocks {len(shapes)} ({sum(shapes):,} "
          f"candidate rows); scalar rows {scalar_rows[0]:,}; H per block min "
          f"{min(shapes)} median {int(statistics.median(shapes))} max "
          f"{max(shapes)}", flush=True)


sys.argv = [str(driver)] + sys.argv[2:]
runpy.run_path(str(driver), run_name="__main__")
