"""Scratch probe: where does the cold pair fire, and what does it cost?

Not a verdict and not a battery — a throwaway driver used while building
H4 W4, kept out of ``verdicts/`` deliberately. It replays one of the
verdict arms, prints every cold pass the run made, and (for OR-11)
records the SHAPE CLASS each cold sweep would have keyed a shared
transform store by, so the parent-shape-vs-own-shape question can be
answered from counts rather than from taste.
"""
from __future__ import annotations

import shutil
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "verdicts"))

import pytest                                              # noqa: E402

from _fixtures import (CHANNEL_ROTATION_DEG, SUBDIVISION_FORMAT,
                       SUBDIVISION_RAMP, build_page,
                       record_window_passes, render)       # noqa: E402
from conftest import (BAND_COLUMNS, BAND_ERROR_RATE, BAND_WARP,
                      CHANNEL_FORMAT, CHANNEL_NOISE,
                      PX_PER_DOT, decode)                  # noqa: E402

#: The coding half of :data:`CHANNEL_FORMAT`, for the arms that sweep the
#: TILE MATRIX (C4, RULINGS G5, 2026-08-22).  Composing ``coding@TYxTX``
#: is the grammar's own spelling, not a second identity mechanism: the
#: string still goes through the one resolver, which is what refuses it
#: if the sweep ever names something unlawful.
CHANNEL_CODING = CHANNEL_FORMAT.split("@")[0]
from holo2.engine.recipe import RECIPE_V1, RECIPE_V1_FINEST  # noqa: E402

ARMS = {
    # the W3 fixture, verbatim: the faded page whose corners subdivide
    "subdivision": dict(format_ref=SUBDIVISION_FORMAT,
                        ink_ramp=SUBDIVISION_RAMP,
                        rotation_deg=CHANNEL_ROTATION_DEG,
                        noise_sigma=CHANNEL_NOISE),
    # the banded page, verbatim
    "banded": dict(format_ref=CHANNEL_FORMAT,
                   cell_error_rate=BAND_ERROR_RATE,
                   cell_error_band=BAND_COLUMNS, **BAND_WARP),
}


def _time_sweeps(patch, sweeps: list[float]) -> None:
    """Wall per correlation, so cold's cost is separable from the run's."""
    from holo2.solve import place_job, place_cold

    original = place_cold.cold_address

    def timed(*args, **kwargs):
        began = time.time()
        try:
            return original(*args, **kwargs)
        finally:
            sweeps.append(time.time() - began)

    patch.setattr(place_job.place_cold, "cold_address", timed)


def _shape_classes(passes: list[dict]) -> None:
    """OR-11 from counts: how many distinct shapes do cold sweeps key on?

    Own-shape keys a store per (patch extent, page set); parent-shape
    would zero-pad every child into its parent's 200-cell extent, so all
    children of one page set collapse into the whole-window class. The
    hit rate of a SHARED store is (requests - distinct classes) / requests
    under each policy, which is what decides the question.
    """
    own = Counter((row["extent"], row["cold"]) for row in passes)
    parent = Counter(((200, 200), row["cold"]) for row in passes)
    for name, classes in (("own-shape", own), ("parent-shape", parent)):
        requests = sum(classes.values())
        hits = requests - len(classes)
        rate = hits / requests if requests else 0.0
        print(f"   {name:13s} sweeps={requests} classes={len(classes)} "
              f"reuse={hits} ({rate:.0%})")
        for key, count in sorted(classes.items(), key=lambda kv: str(kv[0])):
            print(f"        {key}: {count}")


def main() -> int:
    arm = sys.argv[1] if len(sys.argv) > 1 else "subdivision"
    complete = "--open" not in sys.argv
    recipe = RECIPE_V1_FINEST if "--finest" in sys.argv else RECIPE_V1
    if arm.startswith("ramp"):
        # ramp:<value>:<tiles> — the FADED page, W3's fixture pushed
        # further: falling ink contrast across x, so there is a band
        # where the address word dies and the cells are still readable.
        _, value, side = arm.split(":")
        spec = dict(ink_ramp=float(value), rotation_deg=CHANNEL_ROTATION_DEG,
                    noise_sigma=CHANNEL_NOISE)
        format_ref = f"{CHANNEL_CODING}@{side}x{side}"
    elif arm.startswith("flat"):
        # flat:<rate>:<tiles> — the word-dead page: uniform cell error
        # high enough that no tile's address word survives anywhere, so
        # nothing ever places and no window is ever seeded. That is
        # cold's ruled customer, and the regime the record calls
        # unmeasured.
        _, rate, side = arm.split(":")
        spec = dict(cell_error_rate=float(rate),
                    rotation_deg=CHANNEL_ROTATION_DEG,
                    noise_sigma=CHANNEL_NOISE)
        format_ref = f"{CHANNEL_CODING}@{side}x{side}"
    else:
        spec = dict(ARMS[arm])
        format_ref = spec.pop("format_ref")
    work = Path("scratch/w4-cold") / arm.replace(":", "-")
    if work.exists():
        shutil.rmtree(work)          # never resume: each probe is a run
    work.mkdir(parents=True, exist_ok=True)
    for blocks in (40, 16, 8, 4, 2):
        try:
            page = build_page(format_ref, payload_blocks=blocks)
            break
        except AssertionError:
            continue
    else:
        raise SystemExit(f"no one-page payload fits {format_ref}")
    print(f"page {page.spec.layout.cells_yx} cells, k={page.k_total}, "
          f"blocks={blocks}")
    capture = render(page.dots, work / "arm.png", px_per_dot=PX_PER_DOT,
                     cell_dots=page.cell_dots, **spec)
    started = time.time()
    sweeps: list[float] = []
    with pytest.MonkeyPatch.context() as patch:
        passes = record_window_passes(patch)
        _time_sweeps(patch, sweeps)
        outcome, _observer = decode(work / "state", page.row,
                                    ((capture.path, capture.dpi),),
                                    complete=complete, recipe=recipe)
    wall = time.time() - started
    for row in passes:
        extent = row["window"].parts[-4:]
        row["extent"] = (int(extent[2]) - int(extent[0]),
                         int(extent[3]) - int(extent[1]))
    cold = [row for row in passes if row["cold"]]
    swept = [row for row in cold if row["cold_spent"] and row["cold_pages"]]
    print(f"\n=== {arm} complete={complete} recipe={recipe.label} "
          f"wall={wall:.1f}s")
    print("status", outcome.status, "payload-ok",
          outcome.payload == page.payload)
    print("passes", len(passes), "cold claims", len(cold),
          "cold sweeps", len(swept))
    for row in cold:
        print(f"   {row['cold']:10s} extent={row['extent']} "
              f"pages={row['cold_pages']} -> {row['outcome']}")
    print("cold ACCEPTED", sum(row["outcome"] == "accepted" for row in cold))
    if sweeps:
        print(f"correlation wall {sum(sweeps):.1f}s over {len(sweeps)} "
              f"sweeps (mean {sum(sweeps) / len(sweeps):.2f}s, "
              f"max {max(sweeps):.2f}s) = {sum(sweeps) / wall:.0%} of the run")
    if swept:
        _shape_classes(swept)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
