"""Flip ``PlacementConfig.batched_refine`` ON, driver-side, then run a driver.

The switch's DEFAULT in ``src`` is OFF and stays OFF until the numbers
are ruled on; experiment instrumentation is allowed to monkeypatch, src
is not allowed to grow a hatch (L12). Every ``PlacementConfig`` field has
a default, so the generated ``__init__``'s ``__defaults__`` tuple lines
up one-for-one with ``fields()`` — rewriting the one entry makes every
bare ``PlacementConfig()`` in the tree construct with the batched arm on,
and ``dataclasses.replace`` (which passes every init field explicitly)
carries it through untouched.

Wraps ``run_decode_ab.py`` / ``run_decode_gil.py`` rather than
duplicating them, and reports the refinement's real site counts on the
way out.

usage: run_decode_refine.py DRIVER TREE SCAN DPI PORT NAME WORKERS [EXPECTED]
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

from holo2.solve import pose_audit                        # noqa: E402
from holo2.solve.place_model import PlacementConfig       # noqa: E402

names = [field.name for field in dataclasses.fields(PlacementConfig)]
defaults = list(PlacementConfig.__init__.__defaults__)
assert len(defaults) == len(names), (len(defaults), len(names))
defaults[names.index("batched_refine")] = True
PlacementConfig.__init__.__defaults__ = tuple(defaults)
assert PlacementConfig().batched_refine is True
assert dataclasses.replace(PlacementConfig(), refine=True).batched_refine

# Which arm actually ran, counted rather than assumed, plus the site
# counts the batched kernel saw — the shape the micro-bench is timing.
_batched = pose_audit._batched_refine_scan
_scalar = pose_audit._scalar_refine_scan
sites: list[int] = []
scalar_calls = [0]


def _count_batched(context, pose, points, *rest):
    sites.append(int(points.shape[0]))
    return _batched(context, pose, points, *rest)


def _count_scalar(config, evaluate):
    scalar_calls[0] += 1
    return _scalar(config, evaluate)


pose_audit._batched_refine_scan = _count_batched
pose_audit._scalar_refine_scan = _count_scalar


@atexit.register
def _report() -> None:
    if not sites:
        print("[refine] NO BATCHED SCAN RAN — the switch did not take",
              flush=True)
        return
    print(f"[refine] batched scans {len(sites)} (scalar {scalar_calls[0]}); "
          f"sites per scan min {min(sites)} median "
          f"{int(statistics.median(sites))} max {max(sites)}", flush=True)


print(f"[refine] batched_refine forced ON in {tree}", flush=True)
sys.argv = [str(driver)] + sys.argv[2:]
runpy.run_path(str(driver), run_name="__main__")
