#!/usr/bin/env python
"""E9, K instance — LOCAL vs PAGE-GLOBAL calibration on the e029 residue.

docs/TOOLBOX-INVENTORY.md §6.13 carries "local per-state calibration" as
the one entry with no number at all: **UNMEASURED**, "named in the brief;
there is no E9 in the record".  This instrument gives it one, on the
subject whose failure pattern is the idea's own best case — e029, the
first physical holo-v1 print, where the 21 uncertified tiles sit on HP
M281 weak-horizontal-line development banding and on the two extreme
columns, i.e. on UNEVEN TONER.

It runs the ordinary receiver, at the archived committed poses, over the
COMPLETE residue, and changes exactly one thing per arm: the population
of labels the marginal PAVA head is fitted on (window-only, +1 halo,
+2 halo, page-global; certified payload cells as labels against the
incumbent's format-known-only population).  Every attempt is EXTRA: the
archived state is opened read-only and never written, and the ordinary
certificate gate decides.

    cd <checkout>
    PYTHONPATH=src:measure env/bin/python \
        -m calibration.e9_k [--lanes l00-2ppc-600dpi,l01-4ppc-1200dpi] \
                            [--out-dir DIR] [--reduce-only]

MEMORY.  The finer ladder lanes are NOT in the default set and that is a
measurement, not an oversight: with the native capture released after
decimation, one lane's peak RSS is 3.5 GB at 2 ppc, 4.6 GB at 4 ppc,
~12 GB at 8 ppc and 31 GB at 16 ppc, because `placement.geometry.
prepare_region` materializes five float32 arrays the size of the whole
region.  Pass them explicitly if the budget allows.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_LANES = ("l00-2ppc-600dpi", "l01-4ppc-1200dpi")


def main(argv: list[str] | None = None) -> int:
    from . import _inputs
    from ._figures import draw_lane
    from ._reduce import group_of, reduce_file
    from ._run import run

    parser = argparse.ArgumentParser(
        prog="calibration.e9_k", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lanes", default=",".join(DEFAULT_LANES))
    parser.add_argument("--out-dir", type=Path, default=_inputs.OUT_DIR)
    parser.add_argument("--reduce-only", action="store_true",
                        help="rebuild e9-k.json + the figures from an "
                             "existing e9-k-raw.json")
    parser.add_argument("--no-verify-archived", action="store_true",
                        help="skip the arm-R bit-exactness check against "
                             "the archived evidence blocks")
    args = parser.parse_args(argv)

    lanes = tuple(name for name in args.lanes.split(",") if name)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "e9-k-raw.json"
    if not args.reduce_only:
        run(lanes, out_dir, verify_archived=not args.no_verify_archived)
    if not raw_path.is_file():
        raise SystemExit(f"no raw record at {raw_path}")

    report = reduce_file(raw_path, out_dir / "e9-k.json")
    raw = json.loads(raw_path.read_text())
    residue = [tuple(entry) for entry in raw["residue"]]
    for lane_id, lane in raw["lanes"].items():
        draw_lane(out_dir / f"e9-k-{lane_id}.png", lane, residue,
                  tuple(raw["tiles_yx"]), ("R", "W", "H1", "H2", "G"),
                  group_of=group_of)

    for lane_id, lane in report["lanes"].items():
        print(f"\n=== {lane_id} ===")
        print(" reproduction control:", lane["reproduction_control"])
        print(f" {'arm':<4}{'certs':>6}{'medBER%':>9}{'ΔvsR pp':>9}"
              f"{'better':>8}{'worse':>7}{'labels':>10}{'cpu s':>8}")
        for arm, row in lane["arm_summary"].items():
            print(f" {arm:<4}{row['certificates']:>6}"
                  f"{row['median_residue_ber_pct']:>9.2f}"
                  f"{row['mean_delta_vs_R_pp']:>9.2f}"
                  f"{row['tiles_better_than_R']:>8}"
                  f"{row['tiles_worse_than_R']:>7}"
                  f"{row['median_fit_labels']:>10.0f}"
                  f"{row['arm_cpu_s']:>8.1f}")
    print(f"\nartifacts: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
