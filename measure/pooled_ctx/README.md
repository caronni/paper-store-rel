# measure/pooled_ctx — the pooled colour context arm's decode evidence

The arm itself is `src/holo/receiver/plugins/color_pooled.py` (`color.pooled_ctx`).
This directory holds the driver that produced the numbers below and the
stimulus builder for the capture pair it needed.

    PYTHONPATH=src:. env/bin/python -m measure.pooled_ctx.harness \
        --artefacts <dir> --case null-color --out <dir>/null-color.json

`--case` is one of `null-k`, `null-color`, `mixed`, `pair`;
`--no-pooled` is the arm-off control lane. `--compare a.json b.json`
diffs two records (payload, certificate set, per-plugin job counts, arm
counters) without re-running anything.

## The null proof (2026-08-30)

Same driver, same artefacts, two trees: this branch, and a pristine copy
of `main` at 259e622 (`git archive` into a scratch dir, holo3 tree
byte-identical to the `holo3` worktree). The baseline is reached with
`PYTHONSAFEPATH=1 PYTHONPATH=<baseline>:<baseline>/src:<worktree>` — the
driver comes from the branch, `holo3` from the baseline.

| case | payload sha | certificates | job counts |
|---|---|---|---|
| `null-k` (single K capture) | identical | 49/49, signature identical | identical, row for row |
| `null-color` (single colour capture) | identical | 279/279, signature identical | identical, row for row |
| `mixed` (two K captures) | identical | 49/49, signature identical | identical, row for row |

In all three the arm offers zero fits: K has no colour lane, and a
single-capture run publishes no context population at all, so the row is
never born. The multi-capture sim holo3 already had is a K sim — the
colour pair below is the branch's own multi-capture colour evidence.

## The capture pair

`sims.py` derives two captures from the frozen colour sim render, so both
see the SAME printed page and every label is the same format truth.
Capture A keeps the page except a band of tile columns (wiped to the
render's own paper level); capture B keeps only that band. Knobs: band
width and height, a shared blur for both captures (one channel seen
twice), and B's blur / noise / contrast, each optionally ramped down B's
tile rows.

## What the decode runs measured

Arm on, two captures, page 0, workers 1 unless stated:

| configuration | certs off | certs on | pooled fits offered / adopted | lanes adopting |
|---|---|---|---|---|
| B blur 1.4, noise 10 | 300 | 300 | 5 / 0 | 0 |
| B blur/noise ramp 2.0→3.6 / 14→34 | 300 | 300 | 5 / 3 | 0 |
| B contrast ramp 1.0→0.18, noise 12→60 | 282 | 282 | 11 / 7 | 0 |
| shared blur 2.0, B contrast ramp →0.20, noise →55 | 291 | 291 | 9 / 7 | 1 |
| shared blur 2.0, B contrast ramp →0.24, noise →50 | 291 | 291 | 11 / 9 | 1 |
| the same, workers 8 | — | 291 | 10 / 8 | 1 |

Workers 1 against workers 8 on the last row: payload sha identical, and
here even the certificate signature identical, with the job counts moving
as a different interleaving must (`place` 424→378, `revisit` 15→74,
`refine.color` 8→38, `color.pooled_ctx` 11→10). The pooled cells differ
in the evidence they saw at fire time (39,133 vs 52,134 rows at ppc 2) —
which is what a fire-time consult under a different interleaving means,
and why attribution questions are asked at workers 1.

Repeating that workers-1 run reproduces it exactly — payload sha,
certificate signature, every job count, every arm counter.

The arm runs end to end: it is born on the second capture's population,
fits at every rung the two captures share, its cells adopt through the
store's ordinal, an adopted cell re-fires the colour lanes through the
declared read, and a lane takes the pooled head. The payload closes
byte-exact in every run and the certificate set never moves — in either
direction.

**No decode-level tile was recovered, and the sim says why.** Two
measured reasons, both worth carrying:

1. **This sim has no marginal-readout regime.** Degrade the weak capture
   and it goes from "certifies every tile it sees" to "never placed",
   with nothing in between: uniform blur 3.0 px certifies the whole band,
   3.2 px certifies none of it; contrast 0.70 certifies the single-tile
   capture's tile, 0.55 does not place it at all. What fails first is
   placement, not cell readout. The context matrix corrects READOUT, so
   the sim cannot pose the question the arm answers. (The uplift
   campaign's colour gains were measured against real captures carrying
   18% cell error with a healthy address ledger — the opposite regime.)
2. **Where a lane CAN fit its own head, its own head wins.** With the two
   captures under different optics, no lane took the pooled candidate at
   all; giving both captures the same blur was what let a lane adopt it.
   That is INDEPENDENT-PLANES §2.12 (g) — "the ink map has to describe
   THAT capture's neighbourhood optics" — reappearing one level up, at
   the correction rather than the ink map, and it is exactly what the
   per-lane three-way gate is for.

The mechanism's existence proof therefore lives at unit scale, where the
starved lane can be built exactly:
`src/holo/receiver/tests/test_h3_plugins_color_pooled.py` — a 120-row lane refuses
its own matrix on the search floor while the pooled fit over it and a
2400-row lane adopts, and the starved lane's OWN held-out labels rate the
pooled head strictly better than nothing.

## What the published populations cost

Measured on the last row above (100-tile page, two captures, three rungs
each): six lane-page populations, 247,547 rows, **15.35 MB, exactly 62.0
bytes per labelled row** (scores 8 x float32, keys 3 x int64, states,
kinds, three bins, the split bit). The finest lane of the strong capture
carries 114,268 rows on a 100-tile page — 1,143 per tile against 120
furniture sites — so it is certified cargo, not furniture, that makes
these arrays big.

Scaled to sheet H's shape (1,961 tiles, seven captures) that is on the
order of **1 GB held in the store** while the page is partly certified,
against a colour decode that already peaks near 22 GB. Emission
suppression prunes a fully certified tile out of the lane, so the number
falls as the page closes — but only when the lane next fires, since the
standing population is whatever it last published. If it ever binds, the
cheap lever is to publish furniture rows only and measure what the lost
cargo labels were worth.

The real-sheet yield case is the seven-capture sheet-H stack and sheet I.
Neither is run here.
