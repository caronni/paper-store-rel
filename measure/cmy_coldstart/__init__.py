"""measure/cmy_coldstart — the c2 cmy stimulus and its cold start, as records (CMY-RECEIVER-PLAN A9).

The questions (CMY-DESIGN §11 G12; R17, R19): what the suite's c2 page reads like next to the paper it imitates, and
what the production receiver does with a 1x2, 2x2 or 2x3-tile scrap of it, nothing certified, M and Y out of
register by Z (0, 0), A (0.5, -0.5), B (1.0, 1.0) dots with a +-0.5-dot drift and its same-blur control, and C (2.5,
-2.5).  The tests decode Z, A and C on 2x3 (src/holo/receiver/tests/test_h3_e2e_cmy_c2.py); everything else is here.

Modules (each its own driver, `python -m measure.cmy_coldstart.<module> --out DIR`):
  confusion  the stimulus's supervised context-free confusion at its true poses, per dot gain, beside the committed
             e041 S14 B3 / S17 U12 confusions and the e043c / e044 W rows
  grid       the 21 scraps decoded at one worker: true counters, certificates against the generator's, minting
             rows, the field against the plant, the CRC exposure
  lean       Y's lean toward M on the raw field measurement of the tested 2x3 scrap, before any solve, under four
             arms (shipped, no dot gain, M's ink cleared, no cross-talk weights)
Results: RESULTS-2026-10-12.md.  Artefacts: the --out directory, never committed.
"""
