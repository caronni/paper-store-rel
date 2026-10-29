#!/usr/bin/env python3
"""e039 — run holo3 `decode` with the survey's pitch vote suppressed.

On the VersaLink's PDF route a colour page carries the engine's line screen
and a strong one-axis structure at 300/in down the page (scan n, sheet F
c3-cmy8: edge spectrum 41x median at 300/in in y, 6.3x at the true 200/in
grid in x).  The survey votes that 1/300 in and refuses the declared
1/200 in c3 row.  This harness makes `survey._pitch_vote` return no vote,
so the survey takes its ruled fallback (RULINGS D5): the DECLARED pitch.
Nothing else changes.  DIAGNOSTIC, not the production path — a run under
it is not promotable.

    PYTHONPATH=src env/bin/python experiments/039-xerox-versalink/decode_declared_pitch.py \
        --format … --dpi … --out … scans…
"""
from __future__ import annotations

import sys

from holo.receiver.cli import main
from holo.receiver.plugins import survey


def _no_vote(crop, dpi, pitches):
    return None


survey._pitch_vote = _no_vote

if __name__ == "__main__":
    raise SystemExit(main(["decode", *sys.argv[1:]]))
