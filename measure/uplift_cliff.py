"""Where does sibling conditioning move the codec's cliff?

A4b's claim is narrow and testable: a plane whose SOLO evidence fails a
tile can certify once its marginal is restricted to the states its
CERTIFIED siblings allow.  That is a statement about two decoding
thresholds, so this scans the starved plane's strength and reports both
curves — the ordinary one and the conditioned one — instead of hunting
for a single channel where the arm happens to fire.

The gap between the curves IS the arm's window.  Where the curves
coincide the arm cannot help by construction, and no amount of channel
tuning would change that.

THE SCAN RANGE MOVED 2026-08-31 — corner half-cell removed.  This used
to scan 0.20-0.50 because `uplift_fixture` aimed its sampler at cell
CORNERS, which cost a quarter of every plane's contrast and put the
codec's step at 0.400-0.420.  With the sampler on centres the step is at
0.210-0.220, so the old window sat almost entirely in the all-certify
regime and could not see the arm at all.  The range below is the band
where a residue actually exists.

Re-measured over that band (13 points, 0.100-0.220): the `a4b` column
equals the `off` column at EVERY point, gated and ungated alike.  The
measured negative therefore survived the fixture fix — and is now a
stronger statement than it was, because it is made where the residue is
real rather than where a sampling defect had flattened the channel.

RE-MEASURED 2026-09-12 on the REBUILT fixture — the starved plane
displaced by 2 px and the page field handed in (the tier's field is
now a required input, so this scan hands `fixture.plane_fields`):
equal at TWELVE of the thirteen points, and at plane scale 0.180 the
`off` arm certifies 2 where `a4b` and `a4b*` certify 0 — the
conditioning cost two tiles there.  The evidence margin the rebuild
proved (+143 starved cells, positive across the band) does not reach a
certificate on this fixture and once costs two; the arm's standing is
the design's §7.2 record and Germano's ruling.

Usage:

    PYTHONPATH=src:. env/bin/python measure/uplift_cliff.py <page000_gt.npy>
"""
from __future__ import annotations

import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from holo.receiver.plugins import color_arms, tiles

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uplift_existence as probe  # noqa: E402
import uplift_fixture as fixture  # noqa: E402

SCAN = tuple(round(0.10 + 0.01 * step, 3) for step in range(13))


def main() -> int:
    gt_path = Path(sys.argv[1])
    base = fixture.Channel(gain_sd=0.0, absorption=0.30, noise_sd=0.075)
    row, geometry = fixture.format_row_and_geometry()
    bits = fixture.page_bits(gt_path, row)
    windows = fixture.region_windows(row, base)
    all_streams = tuple(stream.stream_id for stream in row.streams)
    every_tile = tuple(
        (ty, tx, all_streams)
        for ty in range(base.tiles_side)
        for tx in range(base.tiles_side))
    n_tiles = base.tiles_side * base.tiles_side
    print("the starved plane is Y (stream index 2); C and M certify first "
          "and become the conditioning authority")
    print(f"{'y_scale':>8}  {'first pass':>10}  {'off':>5}  {'a4b':>5}  "
          f"{'a4b*':>5}  {'strata':>6}  {'arity2':>8}")
    for scale in SCAN:
        channel = replace(base, plane_scale=(1.0, 1.0, scale))
        gains, offsets = fixture.window_gains(channel)
        image = fixture.render(bits, channel, gains, offsets)
        with tempfile.TemporaryDirectory() as tmp:
            planes = fixture.plane_rasters(image, Path(tmp))
            fields = fixture.plane_fields(row, channel)
            frontier, _v, _i, _s = probe.run_tier(
                row, geometry, windows, planes, {}, every_tile,
                probe.ARM_OFF, fields)
            residue = tuple(
                entry for entry in (
                    (ty, tx, tuple(name for name in all_streams
                                   if (0, ty, tx, name) not in frontier))
                    for ty, tx, _s in every_tile)
                if entry[2])
            counts = {}
            strata = 0
            arity2 = 0
            for arm in (probe.ARM_OFF, color_arms.UPLIFT_ARM_A4B,
                        probe.ARM_A4B_UNGATED):
                gained, verdict, _inputs, _stack = probe.run_tier(
                    row, geometry, windows, planes, dict(frontier),
                    residue, arm, fields)
                counts[arm] = len(gained)
                if verdict is not None:
                    strata = verdict.strata_adopted
                    arity2 = verdict.cells_arity2
        print(f"{scale:>8.3f}  {len(frontier):>4}/{n_tiles * 3:<5} "
              f"{counts[probe.ARM_OFF]:>5}  "
              f"{counts[color_arms.UPLIFT_ARM_A4B]:>5}  "
              f"{counts[probe.ARM_A4B_UNGATED]:>5}  {strata:>6}  "
              f"{arity2:>8}")
    print(f"\nBP iterations per attempt: {tiles.RETRY_BP_MAX_ITERS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
