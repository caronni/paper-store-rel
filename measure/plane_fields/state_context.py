#!/usr/bin/env python
"""E3' + E4 — the head's own per-state numbers, and the Y-context loop.

docs/INDEPENDENT-PLANES §6 P2b asks two cheap discriminators of the
2.15 pp dead-vs-control residue P2 left unattributed, both answerable
from the archived captures with no toner and no new state.  This
instrument answers both in ONE pass over the three 2400 dpi captures,
because the expensive part — placing the committed poses and re-fitting
the restricted region AT THE SUPERVISED AFFINE (E1's REFIT arm) — is
shared.

**E3', THE PER-STATE PRODUCTION-vs-ORACLE TABLE.**  §2.8's CORRECTION
retracted E3's "a per-state threshold is worth 4-5 pp" as a lever claim:
that was measured against a SINGLE threshold, and the production head is
an eight-state full-covariance QDA with per-state means, shrunk per-state
covariances, marginalization and a PAVA calibration — a baseline that is
already past it.  What remained open is narrower and is what this
measures: per state ``k``, the TRAINING count ``n_k`` the QDA saw, the
covariance-shrinkage factor ``a_k = min(1, (D+2)/n_k)`` that count
implies, the state's Y moments, the calibration and validation
populations, and — on the six dead tiles, the two reproduction controls
and the certified clean-column references — the production head's Y
error CONDITIONAL ON THE GT STATE next to a per-(C, M)-stratum ORACLE
threshold on the same samples.  Plus A3's per-window verdict split dead
vs clean, which is the "does the window-photometry gate fail
preferentially in dead bands?" question.

**E4, THE Y-CONTEXT CIRCULARITY TEST.**  A5 builds each cell's
neighbourhood bin from the region's PROVISIONAL per-plane ink, and in a
dead band Y's provisional ink is the broken quantity — so Y's context
column is computed from Y's own broken decisions.  Four configurations
(baseline / Y = GT / C,M = GT / all = GT), two arms each (swap the bins;
swap the bins and refit the curve on them), on the same eight tiles at
the same footing.  Configuration (c) is the METHOD CONTROL: C and M are
certified on these tiles, so it must move almost nothing.

Everything is READ-ONLY: the W6 state, the three sha-pinned captures and
``gt-affine-final2.json`` are opened for reading, and nothing is written
outside ``scratch/plane-fields/p2/e3e4/``.

    cd <checkout>
    PYTHONPATH=src:measure env/bin/python \
        -m plane_fields.state_context
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    from ._state_context_run import run

    parser = argparse.ArgumentParser(
        prog="plane_fields.state_context", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tiles", type=int, default=10)
    parser.add_argument("--clear-band-targets", type=int, default=3)
    parser.add_argument("--reproduction-controls", type=int, default=2)
    parser.add_argument("--reference-tiles", type=int, default=6,
                        help="certified clean-column tiles that get the E3' "
                             "per-state table (no E4: they are suppressed)")
    parser.add_argument("--fit-radius", type=int, default=3)
    parser.add_argument("--q", type=float, default=0.9)
    parser.add_argument("--lane", default=None)
    parser.add_argument("--seed", type=int, default=20260821)
    parser.add_argument("--workers", type=int, default=1,
                        help="holo.receive worker threads; results are "
                             "bit-identical for any count (the _parallel "
                             "determinism contract) — 1 keeps this run "
                             "byte-comparable with e1-refit.json")
    parser.add_argument("--limit", type=int, default=0,
                        help="measure only the first N of the eight tiles")
    parser.add_argument("--captures", type=int, default=3,
                        help="measure only the first N captures; a UNION "
                             "attempt names at least two blocks, so 1 is a "
                             "smoke test and never a verdict")
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--from-raw", action="store_true",
                        help="skip the captures and rebuild the summaries, "
                             "files and figures from e3e4/raw.json — the "
                             "expensive rows are written there BEFORE any "
                             "summary runs")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
