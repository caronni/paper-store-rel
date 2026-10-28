"""W8 real-capture regression bars. Read-only, no writes.

Run from a tree that carries the W8a fix:
    PYTHONPATH=src env/bin/python scratch/e031/w8_verify_corners.py

Bars:
  e031 xerox B/W    must find all four corners (it refused with [3,4])
  e031 xerox colour must keep all four at unchanged centres
  e028 M281 B/W     must keep all four at unchanged centres

The two control sheets are the point: W8a must not move anything that
already worked.  Expected centres (thumb px, stock 300-dpi thumbnail) are
pinned below from the pre-fix run.
"""
import sys

sys.path.insert(0, "src")
from holo.characterize.geometry import (  # noqa: E402
    RasterSource, detect_chiral_corners,
)

ROOT = "<repo>"
CAPS = [
    ("e031 xerox B/W", f"{ROOT}/scratch/in/xerox-canon-cal-bw.tiff", None),
    ("e031 xerox colour", f"{ROOT}/scratch/in/xerox-canon-cal-color.tiff",
     {1: (151.0000, 172.0000), 2: (150.0000, 2301.0000),
      3: (3305.0000, 2308.0000), 4: (3312.0000, 181.0000)}),
    ("e028 M281 B/W",
     f"{ROOT}/scratch/e028/e028-m281-20260804-bw-01-canon-4800gray.tiff",
     {1: (158.5043, 187.0000), 2: (171.4643, 2313.0000),
      3: (3326.0000, 2296.0000), 4: (3316.4957, 167.5085)}),
]

failures = 0
for label, path, pinned in CAPS:
    src = RasterSource(path)
    grey, fx, fy = src.thumbnail_grey(4800.0, 4800.0, 300.0)
    rows = {int(r["satellites"]): r for r in detect_chiral_corners(
        grey, target_dpi=300.0, dpi_x=4800.0 / fx, dpi_y=4800.0 / fy)}
    got = sorted(rows)
    ok = got == [1, 2, 3, 4]
    print(f"\n{label}: corners {got} {'OK' if ok else 'FAIL'}")
    if not ok:
        failures += 1
    if pinned:
        for satellites, (py, px) in pinned.items():
            r = rows.get(satellites)
            if r is None:
                print(f"    corner {satellites}: MISSING (was pinned)")
                failures += 1
                continue
            dy = abs(r["y_thumb"] - py)
            dx = abs(r["x_thumb"] - px)
            moved = dy > 1e-3 or dx > 1e-3
            if moved:
                failures += 1
            print(f"    corner {satellites}: ({r['y_thumb']:.4f},"
                  f"{r['x_thumb']:.4f}) "
                  f"{'MOVED' if moved else 'unchanged'}")

print(f"\n{'ALL BARS PASS' if failures == 0 else f'{failures} BAR FAILURE(S)'}")
sys.exit(1 if failures else 0)
