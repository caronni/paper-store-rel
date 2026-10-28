#!/usr/bin/env python
"""E8 — the NON-ORACLE Y-context loop, at two geometries.

docs/INDEPENDENT-PLANES §2.10's E4 priced the Y-context circularity with
an ORACLE: replacing Y's column of A5's ink map with the printed truth
moved the six dead tiles −2.43 pp and the two controls −2.45, flipped
three of six dead tiles to CERTIFIED, and closed NONE of the 2.15 pp
dead-vs-control gap.  A receiver cannot know Y's printed bits, so that
number is a size, not a gain.  E8 asks what a receiver CAN take, on the
same eight tiles, the same three sha-pinned captures and the same lane.

Eight configurations of the same one column — baseline, the E4 oracle and
its method control for calibration, ONE fixed-point iteration on the
decoder's own final decisions, a second iteration, the self-column
REMOVED (Y's bin counting C-or-M neighbours, the non-circular model
class), the three-capture CONSENSUS decision, and a SOFT column carrying
the baseline posterior into the neighbourhood count.

Two geometries, because the answer to "is this an available gain?" is not
the answer to "is this real?":

* **G1**, E1's REFIT footing — the supervised affine, bins recut.
  Directly comparable to E4's table, and a ceiling.
* **G2**, PRODUCTION-like — the committed pose plus the field the shipped
  ``TILE_FRAGMENT`` probe pass builds, applied to every window through
  the ``offsets_override`` seam the ``uF`` arm samples at.  No
  supervision.  G2 is the number that says whether anything here is
  available.

THE PRE-REGISTERED BAR (written to ``e8-bar.json`` before the first
capture is opened): a configuration earns a production-change proposal if
it captures ≥ 50 % of the oracle gain at G1 with no regression on the
certified clean-column references, OR if it certifies any dead-band tile
at G2 under the ordinary certificate gate.

Everything is READ-ONLY: the W6 state, the three sha-pinned captures,
``gt-affine-final2.json`` and ``e3e4/e4.json`` are opened for reading, and
nothing is written outside ``scratch/plane-fields/p2/e8/``.

    cd <checkout>
    PYTHONPATH=src:measure env/bin/python \
        -m plane_fields.context_loop
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    from ._context_loop_run import run

    parser = argparse.ArgumentParser(
        prog="plane_fields.context_loop", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tiles", type=int, default=10)
    parser.add_argument("--clear-band-targets", type=int, default=3)
    parser.add_argument("--reproduction-controls", type=int, default=2)
    parser.add_argument("--reference-tiles", type=int, default=6,
                        help="certified clean-column tiles used as the "
                             "no-regression control (no certificate is "
                             "possible: they are emission-suppressed)")
    parser.add_argument("--fit-radius", type=int, default=3)
    parser.add_argument("--q", type=float, default=0.9)
    parser.add_argument("--lane", default=None)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--workers", type=int, default=1,
                        help="holo.receive worker threads; results are "
                             "bit-identical for any count (the _parallel "
                             "determinism contract) — 1 keeps this run "
                             "byte-comparable with e3e4/e4.json")
    parser.add_argument("--geometries", default="G1,G2",
                        help="G1 = E1's supervised refit footing, "
                             "G2 = the production-like field footing")
    parser.add_argument("--configs", default="a,b,c,z,e1,e2,f,g,h")
    parser.add_argument("--limit", type=int, default=0,
                        help="measure only the first N of the eight tiles")
    parser.add_argument("--captures", type=int, default=3,
                        help="measure only the first N captures; a UNION "
                             "attempt names at least two blocks, so 1 is a "
                             "smoke test and never a verdict")
    parser.add_argument("--rebuild-cache", action="store_true")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
